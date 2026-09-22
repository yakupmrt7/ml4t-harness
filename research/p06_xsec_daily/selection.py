"""p06 pre-OOS: four pre-registered cross-sectional daily sorts (PLAN.md).
No model, no fitting. Each factor = one selection trial (selection_trials.json).

Decision at the 04:00 UTC 5m close, daily 2022-08-01 -> 2024-03-31; top-3 long,
bottom-3 short, +-1 unit ($10k) each; delay=1 on the 5m grid; costs = p05
taker table + per-asset impact add-on; funding P&L included in gross.

Run from the repo root:  PYTHONPATH=. python research/p06_xsec_daily/selection.py [--no-log]
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from harness.backtest import CostModel
from harness.costs import TableCostModel, load_cost_table
from harness.data import asof_join, load_binance_klines, load_funding
from harness.portfolio import funding_pnl, run_portfolio_backtest

HERE = Path(__file__).parent
UNIVERSE = json.loads(Path("research/p04_multiasset/universe.json").read_text())["universe"]
FIRST, LAST = pd.Timestamp("2022-08-01 04:00", tz="UTC"), pd.Timestamp("2024-03-31 04:00", tz="UTC")
PNL_END = LAST + pd.Timedelta(days=1)
N_LEG = 3
FACTORS = {"carry": -1, "basis_change": -1, "reversal_1d": -1, "momentum_28d_skip1": +1}   # +1: long the highest
PASS_T, PASS_BE_MULT = 2.0, 2.0
DAY = pd.Timedelta(days=1)


def load():
    closes, funding, prem = {}, {}, {}
    for a in UNIVERSE:
        b = pd.read_parquet(f"data/bars/{a}-5m-2022-06_2026-08.parquet")
        closes[a] = b["close"].loc[: PNL_END]
        funding[a] = load_funding(f"data/raw/{a}-fundingRate-*.zip").loc[: PNL_END]
        prem[a] = load_binance_klines(f"data/raw/premiumIndexKlines/{a}-5m-*.zip")["close"].loc[: PNL_END]
    return closes, funding, prem


def factor_values(close, fund, prem, times):
    """All four factors for one asset at decision times (data up to each t only)."""
    c = close.reindex(times)
    c_1d = close.reindex(times - DAY).to_numpy()
    c_28d = close.reindex(times - 28 * DAY).to_numpy()
    cum9 = fund.sort_index().rolling(9).sum()
    carry = asof_join(times, cum9, tolerance="9h")                  # strictly before t
    pm = prem.rolling(12, min_periods=10).mean()
    basis = pm.reindex(times).to_numpy() - pm.reindex(times - DAY).to_numpy()
    return pd.DataFrame({"carry": carry.to_numpy(), "basis_change": basis,
                         "reversal_1d": c.to_numpy() / c_1d - 1, "momentum_28d_skip1": c_1d / c_28d - 1},
                        index=times)


def weights(values: pd.DataFrame, sign: int) -> pd.DataFrame:
    """values: times x assets. Long the N_LEG highest sign*value, short the N_LEG lowest; ties by symbol."""
    w = pd.DataFrame(0.0, index=values.index, columns=values.columns)
    for t, row in values.iterrows():
        s = (sign * row).dropna()
        if len(s) < 2 * N_LEG:
            continue
        order = sorted(s.index, key=lambda a: (-s[a], a))
        w.loc[t, order[:N_LEG]] = 1.0
        w.loc[t, order[-N_LEG:]] = -1.0
    return w


def daily(x: pd.Series) -> pd.Series:
    """Sum bar P&L into 24h windows (d 04:00, d+1 04:00], labelled by decision day d."""
    return x.groupby((x.index - pd.Timedelta("4h5min")).floor("1D")).sum()


def sr(d):
    return float(d.mean() / d.std() * np.sqrt(365)) if d.std() > 0 else 0.0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-log", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    closes, funding, prem = load()
    times = pd.date_range(FIRST, LAST, freq="1D")
    vals = {f: pd.DataFrame(index=times) for f in FACTORS}
    for a in UNIVERSE:
        fv = factor_values(closes[a], funding[a], prem[a], times)
        for f in FACTORS:
            vals[f][a] = fv[f]
    # causality: factors at t are identical when computed from data truncated at t
    rng = np.random.default_rng(0)
    for t in rng.choice(times, 5, replace=False):
        t = pd.Timestamp(t)
        for a in UNIVERSE[:5]:
            cut = factor_values(closes[a].loc[:t], funding[a].loc[:t], prem[a].loc[:t], pd.DatetimeIndex([t]))
            full = factor_values(closes[a], funding[a], prem[a], pd.DatetimeIndex([t]))
            assert np.allclose(cut.to_numpy(), full.to_numpy(), equal_nan=True), (a, t)
    coverage = {f: float(v.notna().mean().mean()) for f, v in vals.items()}
    print("factor coverage:", {f: round(x, 4) for f, x in coverage.items()}, "| causality check ok")

    # impact add-on per asset: eff half-spread at $10-50k minus quoted at order times (floored at 0)
    imp = {}
    for path in ("research/p05_costs/impact_check.json", HERE / "impact_other9.json"):
        j = json.loads(Path(path).read_text())
        q = {r["asset"]: r["quoted_hs_at_orders"] for r in j["quoted"]}
        for r in j["eff_hs_by_bucket"]:
            imp[r["asset"]] = max(0.0, float(r["10-50k"]) - q[r["asset"]])
    assert set(imp) == set(UNIVERSE), set(UNIVERSE) - set(imp)
    table = load_cost_table()
    costs = {a: TableCostModel(table, a, "taker_all_in_bps", add_bps=imp[a]) for a in UNIVERSE}

    out = {"decisions": len(times), "first": str(FIRST), "last": str(LAST), "coverage": coverage,
           "impact_addon_bps": imp, "factors": {}}
    grid_closes = {a: c.loc[FIRST:PNL_END] for a, c in closes.items()}
    log = []
    for f, sign in FACTORS.items():
        w = weights(vals[f], sign)
        tg = {a: w[a].reindex(grid_closes[a].index, method="ffill").fillna(0.0) for a in UNIVERSE}
        pf_g, parts = run_portfolio_backtest(grid_closes, tg, CostModel(0, 0))
        pf_n, _ = run_portfolio_backtest(grid_closes, tg, costs)
        fch = funding_pnl(parts["held"], funding)
        price = pf_g["gross"]
        fund_pnl = -fch.sum(axis=1)
        gross = price + fund_pnl
        net = gross - pf_n["cost"]
        dg, dn, dp = daily(gross), daily(net), daily(price)
        years = len(dg) / 365
        turnover = pf_g["turnover"].sum()
        held = parts["held"]
        leg_long = daily((parts["gross"] - fch).where(held > 0, 0).sum(axis=1))
        leg_short = daily((parts["gross"] - fch).where(held < 0, 0).sum(axis=1))
        per_year = {}
        for y, m in (("2022", dg.index.year == 2022), ("2023", dg.index.year == 2023), ("2024Q1", dg.index.year == 2024)):
            per_year[y] = {"sr_gross": sr(dg[m]), "sr_net": sr(dn[m]), "days": int(m.sum())}
        r = {"sign": sign, "days": len(dg), "sr_gross": sr(dg), "t_gross": sr(dg) / np.sqrt(365) * np.sqrt(len(dg)),
             "sr_net": sr(dn), "sr_price_only": sr(dp), "ann_gross_bps_per_unit": float(dg.mean() * 365 * 1e4),
             "funding_share_of_gross": float(fund_pnl.sum() / gross.sum()) if gross.sum() else np.nan,
             "turnover_units_per_year": float(turnover / years),
             "breakeven_bps": float(gross.sum() / turnover * 1e4), "traded_cost_bps": float(pf_n["cost"].sum() / turnover * 1e4),
             "sr_long_leg": sr(leg_long), "sr_short_leg": sr(leg_short),
             "gross_long_share": float(leg_long.sum() / dg.sum()) if dg.sum() else np.nan, "per_year": per_year,
             "mean_legs_changed_per_day": float((w.diff().abs().sum(axis=1) > 0).mean())}
        r["passes"] = bool(r["t_gross"] >= PASS_T and r["breakeven_bps"] >= PASS_BE_MULT * r["traded_cost_bps"])
        out["factors"][f] = r
        log.append({"kind": "factor", "name": f"p06 {f}", "params": {"sign": sign, "legs": N_LEG, "decision": "04:00 UTC daily",
                    "costs": "p05 taker table + impact add-on, funding in gross"},
                    "t_gross": r["t_gross"], "breakeven_bps": r["breakeven_bps"], "traded_cost_bps": r["traded_cost_bps"],
                    "sr_per_period": float(dn.mean() / dn.std()), "n": int(len(dn)), "period": "daily net",
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})
        print(f"\n{f} (sign {sign:+d}): t_gross {r['t_gross']:+.2f}  SR gross {r['sr_gross']:+.2f} net {r['sr_net']:+.2f} "
              f"price-only {r['sr_price_only']:+.2f}  breakeven {r['breakeven_bps']:+.2f} vs cost {r['traded_cost_bps']:.2f} bps  "
              f"turnover {r['turnover_units_per_year']:.0f}/yr  long/short SR {r['sr_long_leg']:+.2f}/{r['sr_short_leg']:+.2f}  "
              f"funding share {r['funding_share_of_gross']:+.2f}  => {'PASS' if r['passes'] else 'fail'}")
        print("   per year:", json.dumps({k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in per_year.items()}))

    # cross-sectional rank correlation between factors (information only)
    sc = {f: (s * vals[f]).rank(axis=1) for f, s in FACTORS.items()}
    names = list(FACTORS)
    rc = pd.DataFrame(index=names, columns=names, dtype=float)
    for i in names:
        for j in names:
            rc.loc[i, j] = float(sc[i].T.corrwith(sc[j].T).mean())
    out["rank_corr"] = rc.round(3).to_dict()
    print("\nmean daily cross-sectional rank correlation (signed scores):\n" + rc.round(2).to_string())

    passing = [f for f, r in out["factors"].items() if r["passes"]]
    out["passing"] = passing
    out["decision"] = ("STOP: no factor passes; no OOS" if not passing else
                       f"propose ONE combination (equal-weight rank average of {passing}) for a single OOS trial; stop at gate")
    print("\nKILL CHECK: passing =", passing, "=>", out["decision"])
    (HERE / "selection.json").write_text(json.dumps(out, indent=1, default=str))
    if not args.no_log:
        path = HERE / "selection_trials.json"
        prev = json.loads(path.read_text()) if path.exists() else []
        path.write_text(json.dumps(prev + log, indent=1, default=str))
    print(f"({time.time() - t0:.0f}s)")
