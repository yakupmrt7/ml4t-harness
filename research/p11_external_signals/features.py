"""p11 external features (PLAN amendment 1), evaluated at 5 m bar closes t. Causal by construction:
every source is aligned to its assumed publication time and only values published <= t are used.

26 features: DVOL (6), options flow (8), ATM IV (2), funding dispersion (4), cross-venue basis (6).
NAN_TOLERANT: skew / ATM-IV columns (NaN when too few trades); LightGBM handles NaN natively.
"""
from __future__ import annotations

import glob
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from harness.data import asof_join, load_funding

D = Path("data/collector/p11")
MIN, HOUR, DAY = pd.Timedelta("1min"), pd.Timedelta("1h"), pd.Timedelta("1D")
NAN_TOLERANT = ["opt_skew_4h", "opt_skew_1d", "atm_iv_4h", "atm_iv_minus_dvol"]
MONTHS = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def asof_series(values: pd.Series, avail: pd.DatetimeIndex, at: pd.DatetimeIndex) -> np.ndarray:
    """Value of the last observation with availability time <= t, for each t in `at`."""
    s = pd.Series(values.to_numpy(), index=avail).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    i = s.index.searchsorted(at, side="right") - 1
    out = np.where(i >= 0, s.to_numpy()[np.maximum(i, 0)], np.nan)
    return out


# ---------------------------------------------------------------- DVOL
def dvol_features(at, close):
    d = pd.DataFrame(json.load(open(D / "deribit_www/dvol_1h.json")), columns=["t", "o", "h", "l", "c"])
    d = d.drop_duplicates("t").sort_values("t")
    opn = pd.to_datetime(d["t"], unit="ms", utc=True)
    c = pd.Series(d["c"].to_numpy(float), index=opn)
    avail = opn + HOUR + MIN                                   # the candle [T, T+1h) is final at T+1h; allow 1 min
    z = (c - c.rolling(720, min_periods=600).mean()) / c.rolling(720, min_periods=600).std()
    f = pd.DataFrame(index=at)
    f["dvol"] = asof_series(c, avail, at)
    f["dvol_chg_4h"] = f["dvol"] - asof_series(c, avail, at - 4 * HOUR)
    f["dvol_chg_1d"] = f["dvol"] - asof_series(c, avail, at - DAY)
    f["dvol_z30d"] = asof_series(z, avail, at)
    lr = np.log(close).diff()
    ann = np.sqrt(365 * 288)
    f["ivrv_1d"] = f["dvol"] / 100 - (lr.rolling(288).std() * ann).reindex(at).to_numpy()
    f["ivrv_7d"] = f["dvol"] / 100 - (lr.rolling(2016).std() * ann).reindex(at).to_numpy()
    return f


# ---------------------------------------------------------------- Deribit options
def parse_instr(names: pd.Series):
    """BTC-12MAR24-70000-C -> expiry (08:00 UTC), strike, is_call."""
    m = names.str.extract(r"BTC-(\d{1,2})([A-Z]{3})(\d{2})-(\d+)-([CP])")
    exp = pd.to_datetime(dict(year=2000 + m[2].astype(int), month=m[1].map(MONTHS), day=m[0].astype(int)), utc=True) + pd.Timedelta("8h")
    return exp, m[3].astype(float), m[4] == "C"


def load_options():
    fs = sorted(glob.glob(str(D / "deribit_opt/opt_*.parquet")))
    o = pd.concat(pd.read_parquet(f) for f in fs)
    o = o.drop_duplicates("trade_id")
    o["ts"] = pd.to_datetime(o["timestamp"], unit="ms", utc=True)
    o["expiry"], o["strike"], o["is_call"] = parse_instr(o["instrument_name"])
    o["mny"] = o["strike"] / o["index_price"]
    o["dte"] = (o["expiry"] - o["ts"]) / DAY
    o["buy"] = o["direction"] == "buy"
    return o.sort_values("ts").reset_index(drop=True), len(fs)


def _window_median(ts_ns, vals, at_ns, w_ns, min_n=5):
    lo = np.searchsorted(ts_ns, at_ns - w_ns, side="left")
    hi = np.searchsorted(ts_ns, at_ns, side="left")                # trades strictly before t
    out = np.full(len(at_ns), np.nan)
    for k in np.nonzero(hi - lo >= min_n)[0]:
        out[k] = np.median(vals[lo[k]:hi[k]])
    return out


def option_features(at, dvol):
    o, nfiles = load_options()
    o = o[o["iv"] > 0]
    at_ns = at.as_unit("ns").asi8
    bucket = pd.DatetimeIndex((o["ts"].dt.floor("5min") + pd.Timedelta("5min")))  # bucket t holds trades in [t-5m, t)
    amt = o["amount"].to_numpy()
    call, buy = o["is_call"].to_numpy(), o["buy"].to_numpy()
    g = pd.DataFrame({"tot": amt, "call": np.where(call, amt, 0), "put": np.where(~call, amt, 0),
                      "buyv": np.where(buy, amt, 0), "sellv": np.where(~buy, amt, 0),
                      "netcall": np.where(call, np.where(buy, amt, -amt), np.where(buy, -amt, amt))},
                     index=bucket).groupby(level=0).sum()
    grid = pd.date_range(at[0] - 2 * DAY, at[-1], freq="5min")
    g = g.reindex(grid).fillna(0.0)
    f = pd.DataFrame(index=at)
    for name, n in (("4h", 48), ("1d", 288)):
        r = g.rolling(n, min_periods=n).sum().reindex(at)
        tot = r["tot"].replace(0, np.nan)
        f[f"opt_callput_{name}"] = ((r["call"] - r["put"]) / tot).to_numpy()
        f[f"opt_buysell_{name}"] = ((r["buyv"] - r["sellv"]) / tot).to_numpy()
        f[f"opt_netcall_{name}"] = (r["netcall"] / tot).to_numpy()
    ts_ns = o["ts"].dt.as_unit("ns").astype("int64").to_numpy()
    tenor = (o["dte"] >= 1) & (o["dte"] <= 45)
    otm_put = (tenor & ~o["is_call"] & o["mny"].between(0.85, 0.97)).to_numpy()
    otm_call = (tenor & o["is_call"] & o["mny"].between(1.03, 1.15)).to_numpy()
    atm = (tenor & o["mny"].between(0.97, 1.03)).to_numpy()
    iv = o["iv"].to_numpy()
    for name, w in (("4h", 4 * HOUR), ("1d", DAY)):
        w_ns = w.value
        pmed = _window_median(ts_ns[otm_put], iv[otm_put], at_ns, w_ns)
        cmed = _window_median(ts_ns[otm_call], iv[otm_call], at_ns, w_ns)
        f[f"opt_skew_{name}"] = pmed - cmed
    f["atm_iv_4h"] = _window_median(ts_ns[atm], iv[atm], at_ns, (4 * HOUR).value)
    f["atm_iv_minus_dvol"] = f["atm_iv_4h"] - dvol
    return f, {"option_files": nfiles, "option_trades": int(len(o))}


# ---------------------------------------------------------------- funding dispersion
def funding_features(at):
    bin_f = load_funding("data/raw/BTCUSDT-fundingRate-*.zip")
    by = pd.read_parquet(D / "bybit/funding.parquet")
    by = pd.Series(by["fundingRate"].astype(float).to_numpy(),
                   index=pd.to_datetime(by["fundingRateTimestamp"].astype("int64"), unit="ms", utc=True)).sort_index()
    de = pd.DataFrame(json.load(open(D / "deribit_www/deribit_funding_1h.json"))).drop_duplicates("timestamp")
    de_s = pd.Series(de["interest_8h"].astype(float).to_numpy(), index=pd.to_datetime(de["timestamp"], unit="ms", utc=True))
    b = asof_join(at, bin_f, tolerance="9h").to_numpy()           # strict: first used by the bar closing after the stamp
    y = asof_join(at, by, tolerance="9h").to_numpy()
    d = asof_series(de_s, de_s.index + MIN, at)                    # hourly row usable from stamp + 1 min
    M = np.vstack([b, y, d])
    f = pd.DataFrame(index=at)
    f["fund_disp"] = M.std(axis=0)
    f["fund_bin_minus_mean"] = b - M.mean(axis=0)
    f["fund_bybit_minus_bin"] = y - b
    f["fund_deribit_minus_bin"] = d - b
    return f


# ---------------------------------------------------------------- cross-venue basis
def basis_features(at, close):
    by = pd.read_parquet(D / "bybit/klines_5m.parquet")
    byc = pd.Series(by["close"].astype(float).to_numpy(),
                    index=pd.to_datetime(by["start"].astype("int64"), unit="ms", utc=True) + pd.Timedelta("5min")).sort_index()
    ok = pd.read_parquet(D / "okx/candles_5m.parquet")
    okc = pd.Series(ok["close"].astype(float).to_numpy(),
                    index=pd.to_datetime(ok["ts"].astype("int64"), unit="ms", utc=True) + pd.Timedelta("5min")).sort_index()
    f = pd.DataFrame(index=close.index)
    for name, s in (("bybit", byc), ("okx", okc)):
        s = s[~s.index.duplicated()]
        b = np.log(s.reindex(close.index) / close)                  # candle closing at t, used at t
        f[f"basis_{name}"] = b
        f[f"basis_{name}_1h"] = b.rolling(12, min_periods=12).mean()
        f[f"basis_{name}_chg_4h"] = b - b.shift(48)
    return f.reindex(at)


def external_features(bars: pd.DataFrame, at: pd.DatetimeIndex):
    close = bars["close"]
    fd = dvol_features(at, close)
    fo, info = option_features(at, fd["dvol"].to_numpy())
    X = pd.concat([fd, fo, funding_features(at), basis_features(at, close)], axis=1)
    assert X.shape[1] == 26, X.shape
    return X, info
