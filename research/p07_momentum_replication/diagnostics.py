"""p07 diagnostics on the new window (reporting only, no selection): P&L by asset and
leg, delay=2, concentration in the best days, and a scan for suspicious 5m prints at
the 04:00 fill bars. Writes diagnostics.json.

Run from the repo root:  PYTHONPATH=.:research/p07_momentum_replication python research/p07_momentum_replication/diagnostics.py
"""
import json

import numpy as np
import pandas as pd

from harness.backtest import CostModel
from harness.portfolio import funding_pnl, run_portfolio_backtest
from selection import DAY, HERE, MIN_LIVE, UNIVERSE, WINDOWS, daily, load, momentum, sr, weights

out = {}
for win in WINDOWS:
    closes, funding = load(win)
    first, last = WINDOWS[win]
    times = pd.date_range(first, last, freq="1D")
    vals = pd.DataFrame({a: momentum(closes[a], times) for a in UNIVERSE}, index=times)
    ok = vals.notna().sum(axis=1) >= MIN_LIVE
    w = weights(vals.where(ok, np.nan, axis=0), +1)
    keep = pd.DatetimeIndex(times[ok.to_numpy()].normalize())
    grid = {a: c.loc[first:last + DAY] for a, c in closes.items()}
    tg = {a: w[a].reindex(grid[a].index, method="ffill").fillna(0.0) for a in UNIVERSE}
    r = {}
    for d in (1, 2):
        pf, parts = run_portfolio_backtest(grid, tg, CostModel(0, 0), delay=d)
        g = parts["gross"] - funding_pnl(parts["held"], funding)
        dg = daily(g.sum(axis=1)).reindex(keep)
        r[f"sr_gross_delay{d}"] = sr(dg)
        if d == 1:
            held = parts["held"]
            r["pnl_by_asset_pct_of_total"] = (g.sum() / g.sum().sum() * 100).round(1).sort_values().to_dict()
            r["long_leg_sum"] = float(g.where(held > 0, 0).sum().sum())
            r["short_leg_sum"] = float(g.where(held < 0, 0).sum().sum())
            r["days_long_by_asset"] = (w > 0).sum().to_dict()
            srt = dg.sort_values(ascending=False)
            r["top10_days_share_of_total"] = float(srt.iloc[:10].sum() / dg.sum())
            r["sr_without_top10_days"] = sr(dg.drop(srt.index[:10]))
            r["sr_without_top10_and_bottom10"] = sr(dg.drop(srt.index[:10]).drop(srt.index[-10:]))
            # sign flip test for fill-price errors: P&L of the first bar after each fill vs the rest
            fill = pd.Series(False, index=g.index)
            fill.loc[fill.index.isin(times + pd.Timedelta("5min"))] = True
            r["pnl_on_first_bar_after_fill_share"] = float(g.sum(axis=1)[fill].sum() / g.sum().sum())
    # bad-print scan: 5m |return| > 20% on any bar, and at the 04:00 bars
    big = {}
    for a, c in grid.items():
        ret = c.pct_change(fill_method=None).abs()
        big[a] = int((ret > 0.2).sum())
    r["n_5m_abs_ret_gt20pct"] = big
    out[win] = r
    print(win, json.dumps(r, indent=1, default=str))
(HERE / "diagnostics.json").write_text(json.dumps(out, indent=1, default=str))
