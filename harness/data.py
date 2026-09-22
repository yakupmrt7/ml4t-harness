"""Loaders: Binance public archive klines, and trades -> bars for your own
collector output.

Binance publishes years of free history at https://data.binance.vision
(spot and USD-M futures klines, aggTrades, funding rates, daily zip files).
Use that for training depth; use your own collector for things the archive
doesn't have (order book, Polymarket, Chainlink).
"""
from __future__ import annotations

import glob

import numpy as np
import pandas as pd

KLINE_COLS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
]


def load_binance_klines(pattern: str) -> pd.DataFrame:
    """Read data.binance.vision kline CSVs/zips (e.g. 'BTCUSDT-5m-2025-*.zip').
    Index = bar CLOSE time, so a feature stamped at t only uses the finished bar."""
    frames = []
    for f in sorted(glob.glob(pattern)):
        df = pd.read_csv(f, header=None, names=KLINE_COLS)
        if not str(df.iloc[0, 0]).isdigit():   # newer files have a header row
            df = df.iloc[1:]
        frames.append(df)
    df = pd.concat(frames).astype({c: float for c in KLINE_COLS[1:6] + KLINE_COLS[7:11]})
    df.index = _epoch_to_utc(df["close_time"], plus_one=True)
    df = df[~df.index.duplicated()].sort_index()
    return df[["open", "high", "low", "close", "volume", "quote_volume", "count", "taker_buy_volume"]]


def _epoch_to_utc(t: pd.Series, plus_one: bool = False) -> pd.DatetimeIndex:
    """Epoch ms or us -> UTC, decided PER ROW: spot archive files switched to
    microseconds in 2025 while futures stayed in ms, so one glob can mix both.
    plus_one turns Binance's inclusive close_time (..999) into the bar edge."""
    t = pd.to_numeric(t).astype("int64").to_numpy() + (1 if plus_one else 0)
    ns = np.where(t > 10**14, t * 1_000, t * 1_000_000)
    return pd.DatetimeIndex(pd.to_datetime(ns, utc=True))


def load_funding(pattern: str) -> pd.Series:
    """data.binance.vision fundingRate monthly CSVs -> Series(rate) by funding time.

    Every row is a SETTLED rate (last_funding_rate at calc_time); the archive
    has no predicted/next rate. calc_time can be a few ms after the 8h mark,
    so join with asof_join (strict): usable from the first bar closing after it."""
    df = pd.concat(pd.read_csv(f) for f in sorted(glob.glob(pattern)))
    idx = _epoch_to_utc(df["calc_time"])
    return pd.Series(df["last_funding_rate"].to_numpy(float), idx).sort_index()


METRIC_COLS = [
    "sum_open_interest", "sum_open_interest_value", "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio", "count_long_short_ratio", "sum_taker_long_short_vol_ratio",
]


def load_metrics(pattern: str) -> pd.DataFrame:
    """data.binance.vision USD-M daily `metrics` CSVs -> DataFrame by create_time (UTC).

    A row stamped T summarises the 5-min period ENDING at T (checked: its taker
    long/short volume ratio matches the kline bar closing at T, median log
    difference 0.0006). Binance publishes it some time after T, so join with
    asof_join (strict): usable from the first bar closing after T.
    Open interest of exactly 0 is a bad print -> NaN. Empty ratios -> NaN
    (top-trader ratios are missing for BTCUSDT until 2022-12-14)."""
    df = pd.concat(pd.read_csv(f) for f in sorted(glob.glob(pattern)))
    df.index = pd.DatetimeIndex(pd.to_datetime(df["create_time"], utc=True))
    df = df[METRIC_COLS].apply(pd.to_numeric, errors="coerce")
    df = df[~df.index.duplicated()].sort_index()
    for c in ("sum_open_interest", "sum_open_interest_value"):
        df[c] = df[c].where(df[c] > 0)
    return df


def asof_join(
    index: pd.DatetimeIndex,
    snaps: pd.DataFrame | pd.Series,
    tolerance: str | pd.Timedelta | None = None,
    allow_exact: bool = False,
) -> pd.DataFrame | pd.Series:
    """For each bar close t in `index`, the last snapshot row stamped STRICTLY
    before t (<= t if allow_exact). Rows older than `tolerance` -> NaN.

    Strict is the default because a snapshot stamped t is usually published
    after t (Binance metrics), or its stamp jitters around t (funding)."""
    is_series = isinstance(snaps, pd.Series)
    right = snaps.to_frame() if is_series else snaps
    right = right.sort_index()
    left = pd.DataFrame({"_t": index.as_unit("ns")})
    right = right.rename_axis("_ts").reset_index()
    right["_ts"] = pd.DatetimeIndex(right["_ts"]).as_unit("ns")
    out = pd.merge_asof(left, right, left_on="_t", right_on="_ts", direction="backward",
                        allow_exact_matches=allow_exact,
                        tolerance=pd.Timedelta(tolerance) if tolerance is not None else None)
    out = out.drop(columns=["_t", "_ts"]).set_axis(index)
    return out.iloc[:, 0] if is_series else out


def check_close_alignment(a: pd.Series, b: pd.Series, max_lag: int = 2) -> dict:
    """Two price series of the same asset indexed by bar CLOSE time (e.g. perp
    and spot) must have their return correlation peak at lag 0. A peak
    elsewhere means one of them is indexed by open time or otherwise shifted.
    Raises if not. Returns {lag: corr}."""
    ra, rb = np.log(a).diff(), np.log(b.reindex(a.index)).diff()
    corr = {k: float(ra.corr(rb.shift(k))) for k in range(-max_lag, max_lag + 1)}
    best = max(corr, key=corr.get)
    if best != 0:
        raise ValueError(f"series misaligned: return correlation peaks at lag {best}: {corr}")
    return corr


def trades_to_bars(
    trades: pd.DataFrame,
    freq: str = "5min",
    ts="ts", price="price", qty="qty", is_buyer_maker="is_buyer_maker",
) -> pd.DataFrame:
    """Aggregate raw trades (e.g. your collector's aggTrade stream) into time
    bars labelled by their CLOSE time (right edge). Map your column names via
    the keyword args. is_buyer_maker=True means the aggressor SOLD."""
    t = trades[[ts, price, qty, is_buyer_maker]].copy()
    if not pd.api.types.is_datetime64_any_dtype(t[ts]):
        unit = "us" if t[ts].iloc[0] > 1e14 else "ms"
        t[ts] = pd.to_datetime(t[ts], unit=unit, utc=True)
    t = t.set_index(ts).sort_index()
    t["notional"] = t[price] * t[qty]
    t["buy_qty"] = t[qty].where(~t[is_buyer_maker].astype(bool), 0.0)
    g = t.resample(freq, label="right", closed="left")
    bars = pd.DataFrame({
        "open": g[price].first(), "high": g[price].max(), "low": g[price].min(),
        "close": g[price].last(), "volume": g[qty].sum(), "quote_volume": g["notional"].sum(),
        "count": g[price].count(), "taker_buy_volume": g["buy_qty"].sum(),
    })
    bars["close"] = bars["close"].ffill()
    for c in ("open", "high", "low"):
        bars[c] = bars[c].fillna(bars["close"])
    return bars.dropna(subset=["close"])
