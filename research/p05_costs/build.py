"""p05 step 4: aggregate measure.py output into
  * data/bars/costs.parquet (+ research/p05_costs/costs_table.csv): per asset,
    per month, from the 4h-grid orders (strategy-agnostic, full span);
  * results.json: cross-checks (bookTicker vs trade proxy vs Roll / Corwin-
    Schultz), and the per-asset DECISION table over the pre-OOS months
    (2022-08 -> 2024-03): costs at p04's actual trade times and directions vs
    p04's pre-OOS breakeven (unscaled +-1, not recomputed).

Run from the repo root:  PYTHONPATH=. python research/p05_costs/build.py [--no-log]
"""
import argparse
import glob
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from harness.costs import (COST_TABLE_PATH, T_LIST, corwin_schultz_half_spread, monthly_cost_table,
                           overlap_calibration, roll_half_spread)
from harness.data import load_binance_klines

HERE = Path(__file__).parent
UNIVERSE = json.loads(Path("research/p04_multiasset/universe.json").read_text())["universe"]
P04 = json.loads(Path("research/p04_multiasset/selection.json").read_text())
PRE_LAST_MONTH = "2024-03"
MARKOUT = (5, 30, 240)


def load():
    days = pd.DataFrame([json.loads(Path(f).read_text()) for f in sorted(glob.glob("data/bars/p05/*/*.json"))])
    orders = pd.concat([pd.read_parquet(f).reset_index() for f in sorted(glob.glob("data/bars/p05/*/*.parquet"))],
                       ignore_index=True)
    return orders, days


def kline_estimators():
    rows = []
    for a in UNIVERSE:
        k = load_binance_klines(f"data/raw/klines1m/{a}-1m-*.zip")
        for m, g in k.groupby(k.index.strftime("%Y-%m")):
            g = g[g["count"] > 0]
            if len(g) < 1000:
                continue
            rows.append({"asset": a, "month": m, "roll_hs_bps": roll_half_spread(g["close"]),
                         "cs_hs_bps": corwin_schultz_half_spread(g["high"], g["low"])})
    return pd.DataFrame(rows)


def per_asset(tab, cols):
    """n_orders-weighted mean over months, per asset."""
    w = tab["n_orders"]
    return pd.DataFrame({c: (tab[c] * w).groupby(tab["asset"]).sum() / w.groupby(tab["asset"]).sum() for c in cols})


def chosen_orders(orders, days, cal, kind):
    """Order-level rows behind monthly_cost_table: bookTicker quotes on
    bookTicker days, else the trade proxy (+ the calibration shift for assets
    whose proxy is off by > 25%)."""
    o = orders[orders["kind"] == kind]
    btd = set(zip(days.loc[days["has_bookticker"], "asset"], days.loc[days["has_bookticker"], "date"]))
    day = pd.DatetimeIndex(o["t"]).strftime("%Y-%m-%d")
    on_bt = np.array([(a, d) in btd for a, d in zip(o["asset"], day)])
    keep = np.where(on_bt, o["quotes"] == "bookTicker", o["quotes"] == "proxy")
    c = o[keep].copy()
    for T in T_LIST:
        shift = c["asset"].map(lambda a: cal.loc[a, f"maker_all_in_{T}_bt_minus_proxy"]
                               if a in cal.index and abs(cal.loc[a, "hs_ratio_bt_over_proxy"] - 1) > 0.25 else 0.0)
        c[f"all_in_{T}"] = c[f"all_in_{T}"] + np.where(c["quotes"] == "proxy", shift, 0.0)
    return c


def mean_se(c, col):
    g = c.groupby("asset")[col]
    return pd.DataFrame({col: g.mean(), f"{col}_se": g.std() / np.sqrt(g.count())})


def markouts(o):
    """The spec's view, per asset, T = 5 min: fill rate, markouts after posting
    (all orders) and after fill (filled), adverse selection = difference, and
    cost = fill*(2 + AS_h - half-spread captured) + (1-fill)*unfilled all-in."""
    rows = []
    for a, g in o.groupby("asset"):
        f = g["filled_5"].astype(bool)
        r = {"asset": a, "n": len(g), "fill_rate_T5": f.mean(), "hs_captured_filled": g.loc[f, "hs_bps"].mean(),
             "unfilled_all_in_T5": g.loc[~f, "all_in_5"].mean() if (~f).any() else 0.0,
             "shortfall_all_in_T5": g["all_in_5"].mean()}
        for h in MARKOUT:
            r[f"mo_post_{h}"] = g[f"mo_post_{h}"].mean()
            r[f"mo_fill_{h}"] = g.loc[f, f"mo_fill_5_{h}"].mean()
            r[f"AS_{h}"] = r[f"mo_fill_{h}"] - r[f"mo_post_{h}"]
            r[f"spec_cost_{h}"] = r["fill_rate_T5"] * (2 + r[f"AS_{h}"] - r["hs_captured_filled"]) + \
                (1 - r["fill_rate_T5"]) * r["unfilled_all_in_T5"]
        rows.append(r)
    return pd.DataFrame(rows).set_index("asset")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-log", action="store_true")
    args = ap.parse_args()
    orders, days = load()
    orders["month"] = pd.DatetimeIndex(orders["t"]).strftime("%Y-%m")
    out = {"n_days": len(days), "n_days_bookticker": int(days["has_bookticker"].sum()), "n_orders": len(orders),
           "days_per_asset": days.groupby("asset").size().to_dict()}
    print(json.dumps(out))

    # ---- cross-checks on the bookTicker overlap -------------------------------
    cal_grid = overlap_calibration(orders, "grid")
    cal_p04 = overlap_calibration(orders, "p04")
    bt_days = days[days["has_bookticker"]]
    xday = bt_days.groupby("asset")[["tw_hs_bt", "eff_hs_bt_vw", "eff_hs_bt_tw", "eff_hs_proxy_vw", "eff_hs_proxy_tw",
                                     "tick_bps_quotes", "tick_bps_trades", "frac_time_one_tick"]].mean()
    kl = kline_estimators()
    kl_bt = kl[kl["month"].isin(bt_days["month"].unique())].groupby("asset")[["roll_hs_bps", "cs_hs_bps"]].mean()
    cross = cal_grid[["n_matched", "hs_bt", "hs_proxy", "hs_ratio_bt_over_proxy"]].join(xday).join(kl_bt)
    out["crosscheck"] = cross.reset_index().to_dict(orient="records")
    out["calibration_grid"] = cal_grid.reset_index().to_dict(orient="records")
    out["calibration_p04"] = cal_p04.reset_index().to_dict(orient="records")
    pd.set_option("display.width", 250)
    print("\nCROSS-CHECK on bookTicker days (bps):\n" + cross.round(3).to_string())
    print("\nCALIBRATION grid (maker all-in, bookTicker minus proxy):\n" + cal_grid.round(3).to_string())

    # ---- the cost table (grid orders, full span) -----------------------------
    tab = monthly_cost_table(orders, days, cal_grid, kind="grid").merge(kl, on=["asset", "month"], how="left")
    Path(COST_TABLE_PATH).parent.mkdir(parents=True, exist_ok=True)
    tab.to_parquet(COST_TABLE_PATH)
    tab.to_csv(HERE / "costs_table.csv", index=False, float_format="%.4f")
    out["cost_table_methods"] = tab["method"].value_counts().to_dict()
    print(f"\ncost table: {len(tab)} rows -> {COST_TABLE_PATH}; methods {out['cost_table_methods']}")

    # ---- decision table: p04 trade times, pre-OOS months ----------------------
    pre = orders[orders["month"] <= PRE_LAST_MONTH]
    tp = monthly_cost_table(pre, days[days["month"] <= PRE_LAST_MONTH], cal_p04, kind="p04")
    tg = monthly_cost_table(pre, days[days["month"] <= PRE_LAST_MONTH], cal_grid, kind="grid")
    cols = ["half_spread_bps", "taker_all_in_bps", "maker_all_in_bps"] + \
           [f"maker_all_in_bps_T{T}" for T in T_LIST] + [f"fill_rate_T{T}" for T in T_LIST]
    dec = per_asset(tp, cols)
    dec["maker_all_in_bps_grid"] = per_asset(tg, ["maker_all_in_bps"])["maker_all_in_bps"]
    dec["n_orders_p04"] = tp.groupby("asset")["n_orders"].sum()
    depth = tp.dropna(subset=["top_depth_usd_median"]).groupby("asset")[
        ["top_depth_usd_median", "frac_10k_exceeds_top", "frac_100k_exceeds_top"]].mean() \
        if "top_depth_usd_median" in tp else pd.DataFrame()
    dec = dec.join(depth)
    be = {r["asset"]: r["breakeven_bps"] for r in P04["per_asset"]}
    dec["p04_breakeven_bps"] = pd.Series(be)
    # breakeven s.e. ~ breakeven / t, t = gross SR * sqrt(years) (bar P&L ~ uncorrelated)
    t_gross = pd.Series({r["asset"]: r["sharpe_gross"] for r in P04["per_asset"]}) * np.sqrt(P04["portfolio"]["years"])
    dec["p04_breakeven_se"] = (dec["p04_breakeven_bps"] / t_gross).abs()
    # order-level standard errors of the T=5 maker cost (p04 times and grid)
    cp = chosen_orders(pre, days, cal_p04, "p04")
    cg = chosen_orders(pre, days, cal_grid, "grid")
    dec["maker_all_in_bps_se"] = mean_se(cp, "all_in_5")["all_in_5_se"]
    dec["maker_all_in_bps_order_mean"] = mean_se(cp, "all_in_5")["all_in_5"]
    dec["maker_all_in_bps_grid_se"] = mean_se(cg, "all_in_5")["all_in_5_se"]
    # sensitivity to the calibration choice (review): grid-fitted shift, or none
    empty = cal_p04.iloc[:0]
    dec["maker_T5_cal_grid"] = mean_se(chosen_orders(pre, days, cal_grid, "p04"), "all_in_5")["all_in_5"]
    dec["maker_T5_no_cal"] = mean_se(chosen_orders(pre, days, empty, "p04"), "all_in_5")["all_in_5"]
    # size-weighted (a flip trades 2 units)
    tt = pd.read_parquet(HERE / "p04_trade_times.parquet")
    szm = cp.merge(tt.rename(columns={"side": "side_tt"}), on=["asset", "t"], how="left")
    szm["size"] = szm["size"].fillna(1.0)
    dec["maker_T5_size_weighted"] = (szm["all_in_5"] * szm["size"]).groupby(szm["asset"]).sum() / \
        szm["size"].where(szm["all_in_5"].notna()).groupby(szm["asset"]).sum()
    for c_ in ("maker_T5_cal_grid", "maker_T5_no_cal", "maker_T5_size_weighted"):
        out.setdefault("sensitivity_pass_count", {})[c_] = int((dec["p04_breakeven_bps"] > dec[c_]).sum())
    dec["edge_minus_maker_z"] = (dec["p04_breakeven_bps"] - dec["maker_all_in_bps"]) / np.sqrt(
        dec["maker_all_in_bps_se"] ** 2 + dec["p04_breakeven_se"] ** 2)
    dec["edge_gt_maker_cost"] = dec["p04_breakeven_bps"] > dec["maker_all_in_bps"]
    dec["edge_gt_taker_cost"] = dec["p04_breakeven_bps"] > dec["taker_all_in_bps"]
    dec["best_T_maker_bps"] = dec[[f"maker_all_in_bps_T{T}" for T in T_LIST]].min(axis=1)
    out["decision_table"] = dec.reset_index().to_dict(orient="records")
    mo = markouts(pre[(pre["kind"] == "p04") & (pre["quotes"] == "bookTicker")])
    out["markouts_p04_bookticker"] = mo.reset_index().to_dict(orient="records")
    print("\nDECISION TABLE (pre-OOS months, p04 trade times; bps per unit traded):\n" + dec.round(2).to_string())
    print("\nMARKOUTS (p04 trade times, bookTicker days, T=5):\n" + mo.round(2).to_string())

    btc_eth = dec.loc[["BTCUSDT", "ETHUSDT"], "maker_all_in_bps"]
    kill = bool((btc_eth >= 2.5).all() and not dec["edge_gt_maker_cost"].any())
    # p04 REVIEW's kill, committed before p05 (the p05 PLAN rule above added a
    # second condition, which loosened it; the review flagged this)
    kill_p04_review = bool((btc_eth >= 2.5).all())
    out["decision"] = {"assets_edge_gt_maker": dec.index[dec["edge_gt_maker_cost"]].tolist(),
                       "assets_edge_gt_taker": dec.index[dec["edge_gt_taker_cost"]].tolist(),
                       "btc_eth_maker_all_in": btc_eth.to_dict(), "abandon_family_p05_plan_rule": kill,
                       "abandon_family_p04_review_rule": kill_p04_review,
                       "max_z": float(dec["edge_minus_maker_z"].max()), "mean_z": float(dec["edge_minus_maker_z"].mean())}
    print("\nDECISION:", json.dumps(out["decision"]))

    # monthly series for the writeup
    out["monthly"] = tab[["asset", "month", "method", "half_spread_bps", "taker_all_in_bps", "maker_all_in_bps",
                          "fill_rate_T5", "roll_hs_bps", "cs_hs_bps"]].to_dict(orient="records")
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    if not args.no_log:
        path = HERE / "selection_trials.json"
        prev = json.loads(path.read_text()) if path.exists() else []
        prev.append({"kind": "measurement", "name": "p05 cost table + decision table", "params": {
            "days": "3/10/17/24 each month", "T_minutes": list(T_LIST), "markout_minutes": list(MARKOUT)},
            "n_days": len(days), "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})
        path.write_text(json.dumps(prev, indent=1, default=str))
