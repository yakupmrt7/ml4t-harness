"""p05 follow-up (review fix): taker cost by ORDER size, not the
volume-weighted average of everyone's trades.

A taker order is approximated by the aggTrades sharing one transact_time and
aggressor side (a market order sweeping several levels prints one aggTrade
per level, all at the same ms). Its effective half-spread = side * (VWAP -
mid) / mid, with mid the bookTicker quote strictly before the order.
Also: the quoted half-spread at those moments vs time-weighted.

Days: 2023-06-10 and 2024-01-10 (bookTicker days), assets with thin or
tick-bound books plus SOL and ADA for contrast.

Run from the repo root:  PYTHONPATH=.:research/p05_costs python research/p05_costs/impact_check.py
  [--assets A B ...] [--out path.json]   (defaults: the 6 below -> impact_check.json)
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import measure as M
from harness.costs import half_spread_bps, load_agg_trades, load_book_ticker, quote_asof, time_weighted_half_spread

ASSETS = ["ETCUSDT", "OPUSDT", "UNFIUSDT", "APEUSDT", "SOLUSDT", "ADAUSDT"]
DAYS = ["2023-06-10", "2024-01-10"]
BUCKETS = [0, 1e3, 1e4, 5e4, 1e5, np.inf]
LABELS = ["<1k", "1-10k", "10-50k", "50-100k", ">100k"]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets", nargs="+", default=ASSETS)
    ap.add_argument("--out", default=str(M.HERE / "impact_check.json"))
    args = ap.parse_args()
    rows, quoted = [], []
    cache = Path("data/bars/p05_impact")          # per (asset, day), so a failed run resumes
    cache.mkdir(parents=True, exist_ok=True)
    for a in args.assets:
        for d in DAYS:
            f_rows, f_q = cache / f"{a}_{d}.parquet", cache / f"{a}_{d}.json"
            if f_rows.exists() and f_q.exists():
                rows.append(pd.read_parquet(f_rows))
                quoted.append(json.loads(f_q.read_text()))
                continue
            day = pd.Timestamp(d)
            _, ag, bt = M.download((a, day, True))
            tr, q = load_agg_trades(ag), load_book_ticker(bt)
            start, end = pd.Timestamp(d, tz="UTC"), pd.Timestamp(d, tz="UTC") + pd.Timedelta(days=1)
            tr = tr[(tr.index >= start) & (tr.index < end)]
            tr["side"] = np.where(tr["buyer_maker"], -1.0, 1.0)
            tr["notional"] = tr["price"] * tr["qty"]
            g = tr.assign(pq=tr["price"] * tr["qty"]).groupby([tr.index, "side"]).agg(
                qty=("qty", "sum"), pq=("pq", "sum"), notional=("notional", "sum"), n_levels=("price", "nunique"))
            g = g.reset_index().rename(columns={"level_0": "t"})
            g["vwap"] = g["pq"] / g["qty"]
            before = quote_asof(q, pd.DatetimeIndex(g["t"]) - pd.Timedelta(1, "ms"))
            g["mid"] = before["mid"].to_numpy()
            g["quoted_hs"] = half_spread_bps(before).to_numpy()
            g["eff_hs"] = g["side"] * (g["vwap"] - g["mid"]) / g["mid"] * 1e4
            g["bucket"] = pd.cut(g["notional"], BUCKETS, labels=LABELS, right=False)
            g["asset"], g["day"] = a, d
            g = g.dropna(subset=["eff_hs"])
            qrow = {"asset": a, "day": d, "tw_quoted_hs": time_weighted_half_spread(q, start, end),
                    "quoted_hs_at_orders": float(g["quoted_hs"].mean())}
            g.assign(bucket=g["bucket"].astype(str)).to_parquet(f_rows)
            f_q.write_text(json.dumps(qrow))
            rows.append(g)
            quoted.append(qrow)
            ag.unlink(); bt.unlink()
    df = pd.concat(rows)
    df["bucket"] = pd.Categorical(df["bucket"].astype(str), categories=LABELS)
    tab = df.pivot_table(index="asset", columns="bucket", values="eff_hs", aggfunc="mean", observed=False).round(2)
    cnt = df.pivot_table(index="asset", columns="bucket", values="eff_hs", aggfunc="count", observed=False)
    med = df.groupby("asset")["eff_hs"].median().round(2)
    lv = df.pivot_table(index="asset", columns="bucket", values="n_levels", aggfunc="mean", observed=False).round(2)
    qt = pd.DataFrame(quoted).groupby("asset")[["tw_quoted_hs", "quoted_hs_at_orders"]].mean().round(3)
    pd.set_option("display.width", 200)
    print("mean effective half-spread (bps) by taker order notional:\n", tab)
    print("\norders per bucket:\n", cnt)
    print("\nmean price levels swept:\n", lv)
    print("\nmedian order effective half-spread:\n", med)
    print("\nquoted half-spread, time-weighted vs at order times:\n", qt)
    out = {"days": DAYS, "eff_hs_by_bucket": tab.reset_index().astype(str).to_dict(orient="records"),
           "count_by_bucket": cnt.reset_index().astype(str).to_dict(orient="records"),
           "levels_by_bucket": lv.reset_index().astype(str).to_dict(orient="records"),
           "median_eff_hs": med.to_dict(), "quoted": qt.reset_index().to_dict(orient="records")}
    Path(args.out).write_text(json.dumps(out, indent=1))
