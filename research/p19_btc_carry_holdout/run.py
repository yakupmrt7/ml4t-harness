"""p19 (PLAN.md): BTC short HL perp / long Binance spot, frozen p18 book B for BTC.

  python research/p19_btc_carry_holdout/run.py             # dev reference (2024-01-01 -> 2026-01-12), no holdout data
  python research/p19_btc_carry_holdout/run.py --holdout   # ONE run after the owner's "go"; logs one trial to trials_hl.json
"""
import argparse
import json
import pathlib
import sys
import time

import numpy as np
import pandas as pd
import requests

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from harness.metrics import TrialLog  # noqa: E402

DATA = ROOT / "data/hl/funding"
DEV = (pd.Timestamp("2024-01-01", tz="UTC"), pd.Timestamp("2026-01-12", tz="UTC"))
HOLD = (pd.Timestamp("2026-01-12", tz="UTC"), pd.Timestamp("2026-09-27", tz="UTC"))
L_SHORT = 3.894                               # frozen from p18 dev (BTC)
CAPITAL = 1 / L_SHORT + 1.0
LIQ_UP = 1 / L_SHORT - 0.05                   # 20.7%
C_HL, C_SPOT = 5e-4, 10.5e-4
BAR = 6.0


def fetch_hl_ohlc(span, path):
    body = {"type": "candleSnapshot", "req": {"coin": "BTC", "interval": "1d", "startTime": int(span[0].timestamp() * 1000),
                                              "endTime": int(span[1].timestamp() * 1000) - 1}}
    for k in range(6):
        r = requests.post("https://api.hyperliquid.xyz/info", json=body, timeout=30)
        if r.status_code == 200:
            break
        time.sleep(5 * (k + 1))
    c = r.json()
    pd.DataFrame({"date": pd.to_datetime([x["t"] for x in c], unit="ms", utc=True), "high": [float(x["h"]) for x in c],
                  "low": [float(x["l"]) for x in c], "close": [float(x["c"]) for x in c]}).to_parquet(path)


def fetch_spot_ohlc(span, path):
    k = requests.get("https://api.binance.com/api/v3/klines",
                     params={"symbol": "BTCUSDT", "interval": "1d", "startTime": int(span[0].timestamp() * 1000),
                             "endTime": int(span[1].timestamp() * 1000) - 1, "limit": 1000}, timeout=30).json()
    pd.DataFrame({"date": pd.to_datetime([x[0] for x in k], unit="ms", utc=True), "high": [float(x[2]) for x in k],
                  "low": [float(x[3]) for x in k], "close": [float(x[4]) for x in k]}).to_parquet(path)


def load(span, holdout):
    """Funding cut to the span (plus the day before for returns); candles fetched or loaded for the span only."""
    pre = span[0] - pd.Timedelta(days=1)
    f = pd.read_parquet(DATA / "hl_funding_BTC.parquet").set_index("time")["rate"]
    f = f[(f.index >= span[0]) & (f.index < span[1])].resample("1D").sum(min_count=1)
    if holdout:
        hp, sp = HERE / "hl_ohlc_BTC_holdout.parquet", HERE / "bn_spot_ohlc_BTC_holdout.parquet"
        if not hp.exists():
            fetch_hl_ohlc((pre, span[1]), hp)
        if not sp.exists():
            fetch_spot_ohlc((pre, span[1]), sp)
        hl, sp_ = pd.read_parquet(hp).set_index("date"), pd.read_parquet(sp).set_index("date")
    else:
        hl = pd.read_parquet(DATA / "hl_ohlc_BTC.parquet").set_index("date")
        sp_ = pd.read_parquet(DATA / "bn_spot_ohlc_BTC.parquet").set_index("date")
    hl, sp_ = (x[(x.index >= pre) & (x.index < span[1])] for x in (hl, sp_))
    return f, hl, sp_


def book(span, holdout):
    f, hl, sp = load(span, holdout)
    idx = pd.date_range(span[0], span[1] - pd.Timedelta(days=1), freq="D", tz="UTC")
    r_hl = hl.close.pct_change().reindex(idx)
    r_sp = sp.close.pct_change().reindex(idx)
    assert r_hl.notna().all() and r_sp.notna().all(), "missing candles in the span"
    fund = f.reindex(idx).fillna(0)
    reset = r_hl.abs() * C_HL + r_sp.abs() * C_SPOT
    pnl = fund - (r_hl - r_sp) - reset
    pnl.iloc[0] -= C_HL + C_SPOT
    pnl.iloc[-1] -= C_HL + C_SPOT
    up = (hl.high / hl.close.shift(1) - 1).reindex(idx)
    return pnl, fund, -(r_hl - r_sp), reset, up


def nw_se_annual(x, lags=30):
    e = x - x.mean()
    n = len(e)
    v = float(e @ e / n)
    for L in range(1, lags + 1):
        v += 2 * (1 - L / (lags + 1)) * float(e[L:] @ e[:-L]) / n
    return 365 * np.sqrt(v / n)


def evaluate(pnl, fund, basis, reset, up):
    r = pnl / CAPITAL
    m = r.groupby(r.index.tz_localize(None).to_period("M")).sum()
    f5 = r.rolling(5).sum().dropna()
    ann = 36500 * float(r.mean())
    t_m = float(m.mean() / (m.std(ddof=1) / np.sqrt(len(m))))
    w5 = float(-f5.min() / f5.mean()) if f5.mean() > 0 else None
    liq = [str(d.date()) for d, u in up.items() if u > LIQ_UP]
    kills = {"k1_return_below_6": ann < BAR, "k2_monthly_t_below_2": not (t_m >= 2),
             "k3_tail": not (w5 is not None and w5 <= 12), "k4_liquidation": bool(liq)}
    return {"days": int(len(r)), "months": int(len(m)), "ann_on_capital_%": ann, "nw_se_%": 100 * nw_se_annual(r.to_numpy()),
            "monthly_t": t_m, "worst5d_over_mean5d": w5, "worst_day_%_capital": 100 * float(r.min()),
            "worst_day": str(r.idxmin().date()), "max_hl_up_move_%": 100 * float(up.max()), "liquidation_days": liq,
            "decomposition_%yr_on_notional": {"hl_funding": 36500 * float(fund.mean()), "basis": 36500 * float(basis.mean()),
                                              "reset_cost": -36500 * float(reset.mean())},
            "kills": kills, "pass": not any(kills.values())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdout", action="store_true")
    a = ap.parse_args()
    if a.holdout:
        out = HERE / "holdout.json"
        assert not out.exists(), "the holdout was already run once; never re-run"
        res = {"span": [str(HOLD[0].date()), str(HOLD[1].date())], "capital": CAPITAL, "L_short": L_SHORT,
               **evaluate(*book(HOLD, True))}
        out.write_text(json.dumps(res, indent=1, default=str))
        pnl = book(HOLD, True)[0] / CAPITAL
        TrialLog(str(ROOT / "trials_hl.json")).log("p19_btc_short_hl_perp_long_bn_spot", pd.DataFrame({"net": pnl}),
                                                   {"L_short": L_SHORT, "capital": CAPITAL, "span": res["span"]})
    else:
        res = {"capital": CAPITAL, "L_short": L_SHORT}
        pnl, fund, basis, reset, up = book(DEV, False)
        res["dev"] = evaluate(pnl, fund, basis, reset, up)
        for y in (2024, 2025):
            s = (pd.Timestamp(f"{y}-01-01", tz="UTC"), pd.Timestamp(f"{y + 1}-01-01", tz="UTC"))
            sel = (pnl.index >= s[0]) & (pnl.index < s[1])
            res[str(y)] = evaluate(pnl[sel], fund[sel], basis[sel], reset[sel], up[sel])
        (HERE / "dev_reference.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
