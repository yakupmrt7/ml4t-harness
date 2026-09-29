"""p14 amendment 1: the STATIC book (short Hyperliquid perp / long Binance USDT perp, all 8 coins, 2x per leg,
weekly Monday reset). Dev by default; the holdout run needs --holdout and is the one logged trial (trials_hl.json).

  python research/p14_hl_funding_carry/static.py            # dev (2024-01-01 -> 2026-01-12)
  python research/p14_hl_funding_carry/static.py --holdout  # ONLY after the owner's "go"
"""
import argparse
import json
import pathlib
import sys

import numpy as np
import pandas as pd
import requests

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from harness.metrics import TrialLog, tail_report  # noqa: E402

DATA = HERE.parents[1] / "data/hl/funding"
COINS = ["BTC", "ETH", "SOL", "XRP", "DOGE", "LINK", "AVAX", "SUI"]
DEV = (pd.Timestamp("2024-01-01", tz="UTC"), pd.Timestamp("2026-01-12", tz="UTC"))
HOLD = (pd.Timestamp("2026-01-12", tz="UTC"), pd.Timestamp("2026-09-27", tz="UTC"))
PAIR_SIDE = (4.5 + 5 + 2 * 0.5) * 1e-4          # PLAN taker cost per pair side
RESET = 5.5e-4                                   # taker on each leg's |drift| at the weekly reset
HL_SIDE = (4.5 + 0.5) * 1e-4                     # re-establishing the HL leg after ADL
LIQ_MOVE = 0.45                                  # 2x: 1/L - ~5% maintenance
ADL_DAY = pd.Timestamp("2025-10-10", tz="UTC")


def daily_funding(venue, coin):
    f = pd.read_parquet(DATA / f"{venue}_funding_{coin}.parquet")
    return f.set_index("time")["rate"].resample("1D").sum(min_count=1)


def closes(venue, coin):
    return pd.read_parquet(DATA / f"{venue}_daily_{coin}.parquet").set_index("date")["close"]


def bn_ohlc(coin):
    f = DATA / f"bn_ohlc_{coin}.parquet"
    if not f.exists():
        rows, start = [], int(DEV[0].timestamp() * 1000)
        while True:
            k = requests.get("https://fapi.binance.com/fapi/v1/klines",
                             params={"symbol": coin + "USDT", "interval": "1d", "startTime": start, "limit": 1500},
                             timeout=30).json()
            if not k:
                break
            rows += k
            start = k[-1][0] + 86_400_000
            if len(k) < 1500:
                break
        d = pd.DataFrame({"date": pd.to_datetime([r[0] for r in rows], unit="ms", utc=True),
                          "high": [float(r[2]) for r in rows], "low": [float(r[3]) for r in rows],
                          "close": [float(r[4]) for r in rows]})
        d.to_parquet(f)
    return pd.read_parquet(f).set_index("date")


def adl_scenario(coin, hl_close):
    """HL short fully ADL'd at the median ADL fill price on 2025-10-10 (shorts buying to close), re-shorted at the
    day's close with one HL side. Returns the day's P&L change per unit notional vs holding through the close."""
    f = HERE.parents[1] / "data/hl/p13_fills/liq/20251010.parquet"
    if not f.exists():
        return np.nan, 0
    d = pd.read_parquet(f, columns=["coin", "side", "dir", "px", "sz"])
    a = d[(d.coin == coin) & (d.side == "B") & (d.dir == "Auto-Deleveraging")]
    if a.empty:
        return 0.0, 0
    p_adl = float(np.median(a.px.astype(float)))
    prev = float(hl_close.loc[:ADL_DAY - pd.Timedelta(days=1)].iloc[-1])
    close = float(hl_close.loc[ADL_DAY])
    return (close - p_adl) / prev - HL_SIDE, len(a)     # short closed at p_adl instead of the close


def coin_book(coin, span):
    s = daily_funding("hl", coin) - daily_funding("bn", coin)
    hc, bc = closes("hl", coin), closes("bn", coin)
    idx = pd.date_range(span[0], span[1] - pd.Timedelta(days=1), freq="D", tz="UTC")
    r_hl, r_bn = hc.pct_change().reindex(idx), bc.pct_change().reindex(idx)
    fund = s.reindex(idx).fillna(0)
    basis = -(r_hl - r_bn).fillna(0)
    # weekly reset on Mondays: pay taker on each leg's drift since the previous reset
    wk = (1 + r_hl.fillna(0)).groupby(idx.to_period("W-SUN")).prod() - 1
    wb = (1 + r_bn.fillna(0)).groupby(idx.to_period("W-SUN")).prod() - 1
    reset_cost = pd.Series(0.0, idx)
    mondays = idx[idx.dayofweek == 0][1:]
    for m in mondays:
        p = (m - pd.Timedelta(days=1)).to_period("W-SUN")
        reset_cost[m] = RESET * (abs(wk.get(p, 0)) + abs(wb.get(p, 0)))
    pnl = fund + basis - reset_cost
    pnl.iloc[0] -= PAIR_SIDE
    pnl.iloc[-1] -= PAIR_SIDE
    # margin survival at 2x from the last reset, Binance daily high (short leg proxy) and low (long leg)
    o = bn_ohlc(coin).reindex(idx)
    ref, worst_short, worst_long, liq_days = None, 0.0, 0.0, []
    for d in idx:
        if ref is None or d.dayofweek == 0:
            ref = float(bc.loc[:d - pd.Timedelta(days=1)].iloc[-1]) if (bc.index < d).any() else float(bc.iloc[0])
        up, dn = o.high.get(d, np.nan) / ref - 1, 1 - o.low.get(d, np.nan) / ref
        worst_short, worst_long = max(worst_short, up if up == up else 0), max(worst_long, dn if dn == dn else 0)
        if up > LIQ_MOVE or dn > LIQ_MOVE:
            liq_days.append(str(d.date()))
    adl = (np.nan, 0)
    if span[0] <= ADL_DAY < span[1]:
        adl = adl_scenario(coin, hc)
    return pnl, {"fund_ann%": 365e2 * fund.mean(), "basis_ann%": 365e2 * basis.mean(),
                 "reset_cost_ann%": -365e2 * reset_cost.mean(), "net_ann%": 365e2 * pnl.mean(),
                 "worst_adverse_move_short_leg": worst_short, "worst_adverse_move_long_leg": worst_long,
                 "liquidation_days_2x": liq_days, "adl_day_delta_pct": 100 * adl[0] if adl[0] == adl[0] else None,
                 "adl_fills": adl[1]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdout", action="store_true")
    a = ap.parse_args()
    span = HOLD if a.holdout else DEV
    per, books = {}, {}
    for c in COINS:
        if not (DATA / f"hl_funding_{c}.parquet").exists():
            sys.exit(f"missing {c}: finish fetch.py first")
        books[c], per[c] = coin_book(c, span)
    port = pd.concat(books, axis=1).mean(axis=1)
    weekly = port.groupby(port.index.to_period("W-SUN")).sum()
    five = port.rolling(5).sum().dropna()
    t_week = float(weekly.mean() / (weekly.std(ddof=1) / np.sqrt(len(weekly))))
    ann = 365e2 * port.mean()
    tail = tail_report(port)
    adl_delta = np.nanmean([v["adl_day_delta_pct"] for v in per.values() if v["adl_day_delta_pct"] is not None]) \
        if any(v["adl_day_delta_pct"] is not None for v in per.values()) else None
    res = {"span": [str(span[0].date()), str(span[1].date())], "days": int(len(port)), "weeks": int(len(weekly)),
           "net_ann%_per_unit_notional": ann, "return_on_capital_ann%_at_2x": ann,  # capital = 1x notional at 2x/leg
           "t_weekly": t_week, "sharpe_annual": float(np.sqrt(365) * port.mean() / port.std()),
           "mean_5d": float(five.mean()), "worst_5d": float(five.min()), "worst_5d_when": str(five.idxmin().date()),
           "worst5d_over_mean5d": float(-five.min() / five.mean()) if five.mean() > 0 else None,
           "cvar5_daily": tail["cvar_5"], "max_drawdown": tail["max_drawdown"],
           "by_quarter_ann%": (port.groupby(port.index.tz_localize(None).to_period("Q").astype(str)).mean() * 365e2).round(2).to_dict(),
           "liquidations_2x": {c: v["liquidation_days_2x"] for c, v in per.items() if v["liquidation_days_2x"]},
           "adl_2025-10-10_portfolio_day_delta_pct": adl_delta}
    if adl_delta is not None and ADL_DAY in port.index:        # amendment 1: ADL must not turn kill 3 on
        pa = port.copy()
        pa[ADL_DAY] += adl_delta / 100
        f5 = pa.rolling(5).sum().dropna()
        res["with_adl_worst5d_over_mean5d"] = float(-f5.min() / f5.mean()) if f5.mean() > 0 else None
        res["with_adl_net_ann%"] = 365e2 * pa.mean()
    k = {"k1_econ": ann <= 5, "k2_t": not (t_week >= 2),
         "k3_tail": not (res["worst5d_over_mean5d"] is not None and res["worst5d_over_mean5d"] <= 12),
         "k4_survival": bool(res["liquidations_2x"])}
    res["kills"] = {**k, "killed": any(k.values())}
    res["per_coin"] = per
    print(json.dumps(res, indent=1, default=str))
    out = HERE / ("static_holdout.json" if a.holdout else "static_dev.json")
    out.write_text(json.dumps(res, indent=1, default=str))
    if a.holdout:
        bt = pd.DataFrame({"net": port})
        TrialLog(str(HERE.parents[1] / "trials_hl.json")).log("p14_static_short_hl_long_bn_2x", bt,
                                                           {"coins": COINS, "span": res["span"]})


if __name__ == "__main__":
    main()
