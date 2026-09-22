"""p06 review follow-ups (reporting only, no selection): breakeven s.e. per
factor, market beta of each book, Newey-West t, and a portfolio shift null
for momentum. Writes followups.json.

Run from the repo root:  PYTHONPATH=.:research/p06_xsec_daily python research/p06_xsec_daily/followups.py
"""
import json

import numpy as np
import pandas as pd

from harness.backtest import CostModel
from harness.portfolio import funding_pnl, portfolio_shift_null, run_portfolio_backtest

from selection import (FACTORS, FIRST, HERE, LAST, PNL_END, UNIVERSE, daily, factor_values, load, sr, weights)

if __name__ == "__main__":
    closes, funding, prem = load()
    times = pd.date_range(FIRST, LAST, freq="1D")
    vals = {f: pd.DataFrame(index=times) for f in FACTORS}
    for a in UNIVERSE:
        fv = factor_values(closes[a], funding[a], prem[a], times)
        for f in FACTORS:
            vals[f][a] = fv[f]
    grid = {a: c.loc[FIRST:PNL_END] for a, c in closes.items()}
    # equal-weight universe daily return, the "market" for these 15 perps
    mkt = daily(pd.concat([c.pct_change().fillna(0.0) for c in grid.values()], axis=1).mean(axis=1))
    out = {"n_decisions": len(times), "n_daily_buckets": None, "market": "equal-weight 15 perps"}
    for f, sign in FACTORS.items():
        w = weights(vals[f], sign)
        tg = {a: w[a].reindex(grid[a].index, method="ffill").fillna(0.0) for a in UNIVERSE}
        pf, parts = run_portfolio_backtest(grid, tg, CostModel(0, 0))
        gross = pf["gross"] - funding_pnl(parts["held"], funding).sum(axis=1)
        dg = daily(gross)
        out["n_daily_buckets"] = len(dg)
        turnover = pf["turnover"].sum()
        be = gross.sum() / turnover * 1e4
        be_se = dg.std() * np.sqrt(len(dg)) / turnover * 1e4          # s.e. of sum(gross) / turnover
        x = mkt.reindex(dg.index).fillna(0.0)
        beta = float(np.polyfit(x, dg, 1)[0])
        hedged = dg - beta * x
        r = dg - dg.mean()
        nw = sum((1 - k / 11) * 2 * (r[k:] * r[:-k if k else None].to_numpy()).mean() for k in range(1, 11))
        var_nw = r.var() + nw
        out[f] = {"breakeven_bps": float(be), "breakeven_se_bps": float(be_se),
                  "breakeven_minus_1se": float(be - be_se), "beta_to_market": beta,
                  "sr_gross": sr(dg), "sr_gross_beta_hedged": sr(hedged),
                  "t_iid": sr(dg) / np.sqrt(365) * np.sqrt(len(dg)),
                  "t_newey_west_10": float(dg.mean() / np.sqrt(var_nw / len(dg))),
                  "daily_autocorr_1": float(dg.autocorr(1))}
        if f == "momentum_28d_skip1":
            actual, null, p = portfolio_shift_null(grid, tg, CostModel(0, 0), n=300)
            out[f].update({"shift_null_actual_sr": float(actual), "shift_null_p_gross": p,
                           "shift_null_mean": float(null.mean()), "shift_null_std": float(null.std())})
        print(f, json.dumps({k: round(v, 3) for k, v in out[f].items()}))
    (HERE / "followups.json").write_text(json.dumps(out, indent=1, default=str))
