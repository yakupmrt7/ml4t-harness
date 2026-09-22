"""Tests that try to make your result disappear.

A result is worth nothing until it has survived these. Each returns plain
numbers; `validation_report` bundles them with pass/fail verdicts.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.model_selection import KFold

from .backtest import CostModel, run_backtest, signal_to_position
from .cv import PurgedKFold
from .metrics import sharpe, periods_per_year, summarize
from .pipeline import oos_predict, oos_auc, align, default_model


def feature_lookahead_audit(X: pd.DataFrame, close: pd.Series, flag_ic: float = 0.10) -> pd.DataFrame:
    """Correlation of each feature at t with the NEXT bar's return and with
    the CURRENT bar's return. Real predictive features on crypto bars have
    next-bar |IC| well under 0.05. Anything above `flag_ic`  almost certainly
    peeks at the future (centred windows, t1-aligned joins, resample labels
    at the wrong edge...)."""
    r = np.log(close).diff()
    nxt = r.shift(-1).reindex(X.index)
    cur = r.reindex(X.index)
    rows = []
    for c in X.columns:
        rows.append(
            {
                "feature": c,
                "ic_next_bar": X[c].corr(nxt, method="spearman"),
                "ic_same_bar": X[c].corr(cur, method="spearman"),
            }
        )
    df = pd.DataFrame(rows).set_index("feature")
    df["suspect"] = df["ic_next_bar"].abs() > flag_ic
    return df.sort_values("ic_next_bar", key=np.abs, ascending=False)


def shuffled_label_test(
    X, labels, splitter, close, costs=CostModel(), n_perm=10, model_factory=default_model,
    weights=None, pos_kwargs=None, seed=0, position_fn=None,
):
    """Train on permuted labels. A correct pipeline must then show AUC ~0.5
    and gross Sharpe centred on 0. If not, something other than the labels
    (timing, a join, the backtester) is leaking returns into the P&L."""
    rng = np.random.default_rng(seed)
    X, labels = align(X, labels)
    y = (labels["label"].to_numpy() > 0).astype(int)
    pos_kwargs = pos_kwargs or {}
    aucs, srs = [], []
    ppy = periods_per_year(close.index)
    for _ in range(n_perm):
        yp = rng.permutation(y)
        p = oos_predict(X, labels, splitter, model_factory, weights, y_override=yp)
        aucs.append(oos_auc(p, labels))
        target = position_fn(p) if position_fn else signal_to_position(p, **pos_kwargs)
        bt = run_backtest(close.loc[p.index[0]: p.index[-1]], target, costs)
        srs.append(sharpe(bt["gross"], ppy))
    return np.array(aucs), np.array(srs)


def circular_shift_null(close, target, costs=CostModel(), n=300, min_shift=None, seed=0):
    """Slide the position series against returns by random offsets. Keeps the
    strategy's turnover, exposure and autocorrelation; destroys its timing.
    p-value = fraction of shifted strategies that beat the real one."""
    rng = np.random.default_rng(seed)
    close = close.loc[target.index[0]: target.index[-1]]
    tgt = target.reindex(close.index).fillna(0.0).to_numpy()
    m = len(tgt)
    min_shift = min_shift or max(1, m // 20)
    ppy = periods_per_year(close.index)
    actual = sharpe(run_backtest(close, pd.Series(tgt, close.index), costs)["net"], ppy)
    null = np.empty(n)
    for i in range(n):
        k = int(rng.integers(min_shift, m - min_shift))
        null[i] = sharpe(run_backtest(close, pd.Series(np.roll(tgt, k), close.index), costs)["net"], ppy)
    return actual, null, float((null >= actual).mean())


def purge_probe(X, labels, model_factory=default_model, n_splits=5, embargo_frac=0.01, seed=0):
    """AUC under naive shuffled KFold vs PurgedKFold. A large gap means your
    features + overlapping labels let the model memorise neighbours; the
    naive number is fiction."""
    X, labels = align(X, labels)

    class _Shuffled:
        def split(self, t1):
            return KFold(n_splits, shuffle=True, random_state=seed).split(np.arange(len(t1)))

    naive = oos_auc(oos_predict(X, labels, _Shuffled(), model_factory), labels)
    purged = oos_auc(oos_predict(X, labels, PurgedKFold(n_splits, embargo_frac), model_factory), labels)
    return naive, purged


def cost_sweep(close, target, bps=(0, 1, 2, 4, 6, 8, 12), delay=1):
    close = close.loc[target.index[0]: target.index[-1]]
    ppy = periods_per_year(close.index)
    rows = []
    for b in bps:
        bt = run_backtest(close, target, CostModel(fee_bps=b, slippage_bps=0), delay=delay)
        rows.append({"cost_bps": b, "sharpe_net": sharpe(bt["net"], ppy)})
    return pd.DataFrame(rows).set_index("cost_bps")


def delay_check(close, target, costs=CostModel()):
    close = close.loc[target.index[0]: target.index[-1]]
    ppy = periods_per_year(close.index)
    return {d: sharpe(run_backtest(close, target, costs, delay=d)["net"], ppy) for d in (1, 2, 3)}


def validation_report(
    X, labels, close, splitter, costs=CostModel(), weights=None, model_factory=default_model,
    pos_kwargs=None, n_perm=8, n_shift=300, too_good_sharpe=4.0, verbose=True, position_fn=None,
):
    """Run the full gauntlet on one configuration. Returns dict of results.

    position_fn(prob_up) -> target replaces signal_to_position(**pos_kwargs),
    both for the headline backtest and the permuted-label null."""
    pos_kwargs = pos_kwargs or {}
    X, labels = align(X, labels)
    res = {}

    audit = feature_lookahead_audit(X, close)
    res["lookahead_suspects"] = audit.index[audit["suspect"]].tolist()

    preds = oos_predict(X, labels, splitter, model_factory, weights)
    target = position_fn(preds) if position_fn else signal_to_position(preds, **pos_kwargs)
    c = close.loc[preds.index[0]: preds.index[-1]]
    bt = run_backtest(c, target, costs)
    ppy = periods_per_year(c.index)
    res["oos_auc"] = oos_auc(preds, labels)
    res["sharpe_gross"] = sharpe(bt["gross"], ppy)
    res["sharpe_net"] = sharpe(bt["net"], ppy)

    aucs, srs = shuffled_label_test(X, labels, splitter, close, costs, n_perm, model_factory, weights, pos_kwargs,
                                    position_fn=position_fn)
    res["perm_auc_mean"], res["perm_sharpe_mean"], res["perm_sharpe_std"] = (
        float(np.nanmean(aucs)), float(srs.mean()), float(srs.std()))

    # Shift null on GROSS returns tests timing skill. (On net returns it is
    # misleading: shifted copies pay the same costs, so beating them does not
    # mean you make money.) Net profitability is tested with PSR instead.
    res["shift_null_p_gross"] = circular_shift_null(c, target, CostModel(0, 0), n_shift)[2]
    s = summarize(bt)
    res["psr_net"] = s["psr_vs_0"]
    res["breakeven_cost_bps"] = s["breakeven_cost_bps"]
    res["turnover_per_year"] = s["turnover_per_year"]
    res["purge_probe_naive_auc"], res["purge_probe_purged_auc"] = purge_probe(X, labels, model_factory)
    res["delay_sharpe"] = delay_check(c, target, costs)
    # Delay verdict uses GROSS Sharpe: net fails at every delay whenever costs
    # dominate, which says nothing about whether the edge is microstructure.
    res["delay_sharpe_gross"] = delay_check(c, target, CostModel(0, 0))
    sweep = cost_sweep(c, target)
    res["cost_sweep"] = sweep["sharpe_net"].round(2).to_dict()

    res["oos_years"] = len(c) / ppy
    res["verdicts"] = verdicts(res, n_perm, too_good_sharpe)
    res["backtest"] = bt
    res["preds"] = preds
    if verbose:
        print_report(res)
    return res


def verdicts(res, n_perm, too_good_sharpe=4.0):
    """Pass/fail block shared by validation_report and
    portfolio.portfolio_validation_report. Sets res['sharpe_se']."""
    # Annualised Sharpe standard error is ~1/sqrt(years). On 1-2 months of
    # out-of-sample data that is ~3, so "too good" must scale with it.
    res["sharpe_se"] = 1 / np.sqrt(res["oos_years"])
    too_good = max(too_good_sharpe, 4 * res["sharpe_se"])
    v = {
        "no lookahead-looking features": not res["lookahead_suspects"],
        "not implausibly good (gross Sharpe < %.1f)" % too_good: abs(res["sharpe_gross"]) < too_good,
        "pipeline clean (permuted labels -> AUC~0.5, Sharpe~0)": (
            abs(res["perm_auc_mean"] - 0.5) < 0.01
            and abs(res["perm_sharpe_mean"]) < 3 * res["perm_sharpe_std"] / np.sqrt(n_perm) + 0.25),
        "timing edge beats shifted nulls (gross, p<0.05)": res["shift_null_p_gross"] < 0.05,
        "net Sharpe > 0 with PSR > 0.95": res["psr_net"] > 0.95,
        "gross edge survives 1 extra bar (d=2 keeps >50% of d=1)": (
            res["delay_sharpe_gross"][1] > 0
            and res["delay_sharpe_gross"][2] > 0.5 * res["delay_sharpe_gross"][1]),
    }
    return {k: bool(x) for k, x in v.items()}   # numpy bools -> JSON true/false


def print_report(res):
    f = lambda v: f"{v:+.3f}" if isinstance(v, float) else str(v)
    print(f"  OOS span                {res['oos_years']*365.25:.0f} days (annualised Sharpe s.e. ~{res['sharpe_se']:.1f})")
    print(f"  OOS AUC                 {f(res['oos_auc'])}")
    print(f"  Sharpe gross / net      {f(res['sharpe_gross'])} / {f(res['sharpe_net'])}")
    print(f"  permuted labels         AUC {f(res['perm_auc_mean'])}, Sharpe {f(res['perm_sharpe_mean'])} ± {res['perm_sharpe_std']:.2f}")
    print(f"  shift-null p (gross)    {res['shift_null_p_gross']:.3f}")
    print(f"  PSR(net SR > 0)         {res['psr_net']:.3f}   breakeven cost {res['breakeven_cost_bps']:.2f} bps/turnover")
    print(f"  purge probe AUC         naive {f(res['purge_probe_naive_auc'])} vs purged {f(res['purge_probe_purged_auc'])}")
    print(f"  Sharpe by delay (net)   " + ", ".join(f"d={k}: {v:+.2f}" for k, v in res["delay_sharpe"].items()))
    print(f"  Sharpe by delay (gross) " + ", ".join(f"d={k}: {v:+.2f}" for k, v in res["delay_sharpe_gross"].items()))
    print(f"  Sharpe by cost (bps)    " + ", ".join(f"{k}:{v:+.2f}" for k, v in res["cost_sweep"].items()))
    if res["lookahead_suspects"]:
        print(f"  LOOKAHEAD SUSPECTS      {res['lookahead_suspects']}")
    for k, ok in res["verdicts"].items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {k}")
