"""Multi-asset (pooled) extension: risk-budgeted portfolio backtest, a
portfolio-level shift null and a portfolio validation_report.

Conventions, on top of backtest.py:
  * closes[a] is asset a's LIVE close series (cut at its last traded bar).
    An asset whose series ends before the others is DELISTED: its target is
    forced to 0 from its last bar, and it is padded with `delay` bars at the
    frozen last price, so the exit fills at the last traded close and pays
    normal costs. After that the asset is flat, with no successor spliced in.
  * Portfolio P&L = sum over assets of per-asset P&L, on the union bar grid.
  * Pooled predictions are Series on a (t0, asset) MultiIndex sorted by t0
    (see harness.cv for how the splitters purge on time across assets).
"""
from __future__ import annotations

from functools import reduce
from typing import Callable

import numpy as np
import pandas as pd
from scipy import stats

from .backtest import CostModel
from .metrics import max_drawdown, periods_per_year, psr, sharpe
from .nulls import feature_lookahead_audit, print_report, purge_probe, verdicts
from .pipeline import align, default_model, oos_auc, oos_predict


def risk_scale(pos: pd.Series, vol: pd.Series, target_vol: float, cap: float) -> pd.Series:
    """pos * min(cap, target_vol / vol), with the scale LATCHED at the bar where
    pos changes and held until the next change. Re-scaling every bar would
    trade on vol drift alone. vol must be known at t (e.g. annualised
    ewm_vol). Non-finite or zero vol at an entry -> flat until the next change."""
    p = pos.to_numpy(dtype=float)
    v = vol.reindex(pos.index).to_numpy(dtype=float)
    prev = np.concatenate([[0.0], p[:-1]])
    change = p != prev
    with np.errstate(divide="ignore", invalid="ignore"):
        s = np.where(np.isfinite(v) & (v > 0), np.minimum(cap, target_vol / v), 0.0)
    latched = pd.Series(np.where(change, s, np.nan), index=pos.index).ffill().fillna(0.0).to_numpy()
    return pd.Series(p * latched, index=pos.index)


def _panel(closes: dict, targets: dict, delay: int):
    """-> grid, assets, C (T,A closes; NaN when not listed; frozen padding
    after a delisting), live (T,A bool: tradable, target may be != 0), W (T,A)."""
    assets = list(closes)
    starts = [targets[a].index[0] for a in assets if len(targets.get(a, ()))]
    ends = [targets[a].index[-1] for a in assets if len(targets.get(a, ()))]
    start, end = min(starts), max(ends)
    grid = reduce(lambda x, y: x.union(y), [closes[a].loc[start:end].index for a in assets])
    T, A = len(grid), len(assets)
    C = np.full((T, A), np.nan)
    live = np.zeros((T, A), bool)
    W = np.zeros((T, A))
    for j, a in enumerate(assets):
        c = closes[a].loc[start:end]
        if not len(c):
            continue
        i0, i1 = grid.get_indexer([c.index[0], c.index[-1]])
        C[:, j] = c.reindex(grid).to_numpy()
        live[i0 : i1 + 1, j] = np.isfinite(C[i0 : i1 + 1, j])
        if i1 < T - 1:                        # delisted inside the window
            live[i1, j] = False               # flat from the last traded bar
            C[i1 + 1 : i1 + 1 + delay, j] = C[i1, j]
        if a in targets:
            W[:, j] = targets[a].reindex(grid).fillna(0.0).to_numpy()
    W[~live] = 0.0
    return grid, assets, C, live, W


def _pnl(C, W, cost_per_unit: float, delay: int):
    """Same arithmetic as backtest.run_backtest, column-wise. -> held, gross, cost."""
    with np.errstate(invalid="ignore"):
        R = np.vstack([np.zeros((1, C.shape[1])), C[1:] / C[:-1] - 1])
    R = np.nan_to_num(R, nan=0.0)
    H = np.vstack([np.zeros((delay, W.shape[1])), W[:-delay]])
    trade = np.abs(np.diff(H, axis=0, prepend=0.0))
    return H, H * R, trade * cost_per_unit


def _cost_matrix(costs, grid, assets, traded, when):
    """Per-unit cost per bar and asset. costs: one CostModel for all assets, or
    {asset: cost model}. Time-varying models (per_unit_at, e.g.
    harness.costs.TableCostModel) are asked ONLY about bars where that asset
    trades (traded[:, j]), at time when[:, j] (epoch ns: the bar time, or the last listed
    bar for the exit fill after a delisting). A missing month on a traded bar
    raises; bars without trades cost nothing anyway."""
    def one(cm, j):
        out = np.zeros(len(grid))
        if hasattr(cm, "per_unit_at"):
            rows = traded[:, j]
            if rows.any():
                out[rows] = cm.per_unit_at(pd.to_datetime(when[rows, j], unit="ns", utc=True))
        else:
            out[:] = cm.per_unit_turnover
        return out
    return np.column_stack([one(costs[a] if isinstance(costs, dict) else costs, j) for j, a in enumerate(assets)])


def run_portfolio_backtest(closes: dict, targets: dict, costs: CostModel = CostModel(), delay: int = 1):
    """Sum of per-asset bar-level P&L. Funding is NOT included, whatever
    costs.include_funding says: add it separately from parts['held'].

    closes  : {asset: live close Series}
    targets : {asset: target weight Series} (already risk-scaled if wanted)
    costs   : a CostModel for all assets, or {asset: cost model}
    Returns (pf, parts). pf: per-bar gross, cost, net, turnover (sum |dw|),
    gross_exposure, net_exposure, equity. parts: {'held','gross','cost','net'}
    -> DataFrames (grid x assets)."""
    if delay < 1:
        raise ValueError("delay must be >= 1; delay=0 is lookahead")
    grid, assets, C, _, W = _panel(closes, targets, delay)
    H, G, _ = _pnl(C, W, 0.0, delay)
    trade = np.abs(np.diff(H, axis=0, prepend=0.0))
    g_ns = grid.as_unit("ns").asi8
    when = np.repeat(g_ns[:, None], len(assets), axis=1)     # epoch ns
    for j, a in enumerate(assets):          # exit fill after a delisting: price it at the last listed bar
        last = closes[a].loc[: grid[-1]].index
        if len(last) and last[-1] < grid[-1]:
            i1 = grid.get_loc(last[-1])
            when[i1 + 1:, j] = g_ns[i1]
    K = trade * _cost_matrix(costs, grid, assets, trade > 0, when)
    N = G - K
    parts = {k: pd.DataFrame(v, index=grid, columns=assets) for k, v in
             (("held", H), ("gross", G), ("cost", K), ("net", N))}
    pf = pd.DataFrame({
        "gross": G.sum(1), "cost": K.sum(1), "net": N.sum(1),
        "turnover": np.abs(np.diff(H, axis=0, prepend=0.0)).sum(1),
        "gross_exposure": np.abs(H).sum(1), "net_exposure": H.sum(1),
    }, index=grid)
    pf["equity"] = (1 + pf["net"]).cumprod()
    return pf, parts


def funding_pnl(held: pd.DataFrame, funding: dict) -> pd.DataFrame:
    """Funding CHARGE per bar and asset (subtract it from P&L), same arithmetic
    as backtest.run_backtest: the weight held into the first bar at or after a
    settlement pays weight * rate (longs pay positive rates).

    held    : parts['held'] from run_portfolio_backtest (grid x assets)
    funding : {asset: Series of settled rates indexed by settlement time}"""
    out = pd.DataFrame(0.0, index=held.index, columns=held.columns)
    for a in held.columns:
        f = funding.get(a)
        if f is None or not len(f):
            continue
        f = f.sort_index()
        f = f[(f.index >= held.index[0]) & (f.index <= held.index[-1])]
        pos = np.minimum(held.index.searchsorted(f.index, side="left"), len(held) - 1)
        charge = np.zeros(len(held))
        np.add.at(charge, pos, f.to_numpy())
        out[a] = held[a].to_numpy() * charge
    return out


def portfolio_stats(pf: pd.DataFrame) -> dict:
    ppy = periods_per_year(pf.index)
    years = len(pf) / ppy
    to = pf["turnover"].sum()
    sr_pp = sharpe(pf["net"])
    return {
        "years": years,
        "sharpe_gross": sharpe(pf["gross"], ppy),
        "sharpe_net": sharpe(pf["net"], ppy),
        "psr_vs_0": psr(sr_pp, len(pf), float(stats.skew(pf["net"])), float(stats.kurtosis(pf["net"], fisher=False))),
        "breakeven_cost_bps": float(pf["gross"].sum() / to * 1e4) if to else np.nan,
        "turnover_per_year": float(to / years),
        "mean_gross_exposure": float(pf["gross_exposure"].mean()),
        "mean_net_exposure": float(pf["net_exposure"].mean()),
        "ann_return_net": float(pf["net"].mean() * ppy),
        "ann_vol": float(pf["net"].std() * np.sqrt(ppy)),
        "max_drawdown": max_drawdown(pf["equity"]),
    }


def portfolio_shift_null(closes, targets, costs=CostModel(0, 0), n=300, min_shift=None, seed=0, delay=1):
    """Circular shift of ALL assets' targets by the SAME random offset. Keeps
    each asset's turnover and exposure and the cross-asset correlation of
    positions; destroys timing. Positions shifted onto bars where an asset is
    not listed are dropped (flat), so with delisted / late-listed assets the
    shifted books carry somewhat LESS exposure than the real one (a smaller
    gross Sharpe spread for the null). p = fraction of shifted Sharpes >= actual."""
    rng = np.random.default_rng(seed)
    grid, _, C, live, W = _panel(closes, targets, delay)
    c = costs.per_unit_turnover
    ppy = periods_per_year(grid)
    m = len(grid)
    min_shift = min_shift or max(1, m // 20)

    def sr(Wk):
        _, G, K = _pnl(C, Wk, c, delay)
        return sharpe(pd.Series((G - K).sum(1)), ppy)

    actual = sr(W)
    null = np.empty(n)
    for i in range(n):
        Wk = np.roll(W, int(rng.integers(min_shift, m - min_shift)), axis=0)
        Wk[~live] = 0.0
        null[i] = sr(Wk)
    return actual, null, float((null >= actual).mean())


def _split_by_asset(preds: pd.Series) -> dict:
    return {a: s.droplevel(1) for a, s in preds.groupby(level=1, sort=False)}


def portfolio_validation_report(
    X: pd.DataFrame, labels: pd.DataFrame, closes: dict, splitter, position_fn: Callable,
    costs: dict, weights=None, model_factory=default_model, n_perm=8, n_shift=300,
    too_good_sharpe=4.0, verbose=True, seed=0,
):
    """validation_report for a pooled model traded as a portfolio.

    X, labels : (t0, asset) MultiIndex, sorted by t0.
    position_fn(preds) -> {asset: target weight Series}; preds is the pooled
                 P(up) Series on the same MultiIndex.
    costs     : {name: CostModel}. Everything cost-independent (fits,
                permutations, shift null, purge probe) runs once.
    Same verdicts as nulls.validation_report (shared code), at portfolio level:
    AUC is pooled; Sharpe, PSR, breakeven, delay and cost sweeps are on the
    summed portfolio P&L; the shift null moves all assets by one offset.
    Returns {name: res}; each res also has 'backtest', 'parts', 'preds'."""
    X, labels = align(X, labels)
    common = {}
    sus = []
    for a, xa in X.groupby(level=1, sort=False):
        aud = feature_lookahead_audit(xa.droplevel(1), closes[a])
        sus += [f"{f}@{a}" for f in aud.index[aud["suspect"]]]
    common["lookahead_suspects"] = sus

    preds = oos_predict(X, labels, splitter, model_factory, weights)
    targets = position_fn(preds)
    common["oos_auc"] = oos_auc(preds, labels)
    common["oos_auc_by_asset"] = {a: oos_auc(p, labels.xs(a, level=1)) for a, p in _split_by_asset(preds).items()}

    rng = np.random.default_rng(seed)
    y = (labels["label"].to_numpy() > 0).astype(int)
    aucs, srs = [], []
    for _ in range(n_perm):
        pp = oos_predict(X, labels, splitter, model_factory, weights, y_override=rng.permutation(y))
        aucs.append(oos_auc(pp, labels))
        pfp, _ = run_portfolio_backtest(closes, position_fn(pp), CostModel(0, 0))
        srs.append(sharpe(pfp["gross"], periods_per_year(pfp.index)))
    aucs, srs = np.array(aucs), np.array(srs)
    common["perm_auc_mean"], common["perm_sharpe_mean"], common["perm_sharpe_std"] = (
        float(np.nanmean(aucs)), float(srs.mean()), float(srs.std()))
    common["shift_null_p_gross"] = portfolio_shift_null(closes, targets, CostModel(0, 0), n_shift)[2]
    common["purge_probe_naive_auc"], common["purge_probe_purged_auc"] = purge_probe(X, labels, model_factory)

    def sr_at(cm, d=1, part="net"):
        pf, _ = run_portfolio_backtest(closes, targets, cm, delay=d)
        return sharpe(pf[part], periods_per_year(pf.index))

    common["delay_sharpe_gross"] = {d: sr_at(CostModel(0, 0), d) for d in (1, 2, 3)}
    common["cost_sweep"] = {b: round(sr_at(CostModel(fee_bps=b, slippage_bps=0)), 2) for b in (0, 1, 2, 4, 6, 8, 12)}

    out = {}
    for name, cm in costs.items():
        pf, parts = run_portfolio_backtest(closes, targets, cm)
        st = portfolio_stats(pf)
        res = dict(common)
        res.update({"sharpe_gross": st["sharpe_gross"], "sharpe_net": st["sharpe_net"], "psr_net": st["psr_vs_0"],
                    "breakeven_cost_bps": st["breakeven_cost_bps"], "turnover_per_year": st["turnover_per_year"],
                    "delay_sharpe": {d: sr_at(cm, d) for d in (1, 2, 3)}, "oos_years": st["years"]})
        res["verdicts"] = verdicts(res, n_perm, too_good_sharpe)
        res.update({"backtest": pf, "parts": parts, "preds": preds, "stats": st})
        if verbose:
            print(f"\n=== portfolio validation_report, {name} cost ({cm.fee_bps}+{cm.slippage_bps} bps) ===")
            print_report(res)
        out[name] = res
    return out
