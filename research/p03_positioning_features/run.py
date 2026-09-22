"""p03 OOS: the H, features and hysteresis chosen by selection.py (pre-OOS
only), run ONCE on WalkForward OOS. Test blocks start exactly at p01's OOS
start (2024-04-07 09:15), so p01/p02/p03 share the OOS period.

validation_report at taker and maker cost; one trial "p03_positioning_H<H>"
(maker backtest). Also: funding-inclusive net, per-fold gross Sharpe, LightGBM
gain importance and OOS permutation importance (basic vs positioning groups).

Run from the repo root:  python research/p03_positioning_features/run.py [--no-log]
OOS predictions -> preds.parquet (gitignored).
"""
import argparse
import json
import time

import numpy as np
import pandas as pd

from harness.backtest import run_backtest
from harness.cv import WalkForward
from harness.metrics import TrialLog, periods_per_year, sharpe, summarize
from harness.nulls import validation_report
from harness.pipeline import align, default_model, oos_auc
from harness.weights import average_uniqueness, effective_n

from common import (MAKER, OOS_START, OUT, TAKER, bt_stats, build_features, hyst_fn, load_inputs,
                    make_labels, subgroup)

N_SPLITS = 8
N_REPEATS = 3

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-log", action="store_true")
    args = ap.parse_args()
    t = time.time()
    sel = json.loads((OUT / "selection.json").read_text())
    H, cfg = sel["chosen_H"], sel["hysteresis"]
    bars, metrics, funding, spot, prem, info = load_inputs()
    close = bars["close"]
    X, cols_basic, cols_pos = build_features(bars, metrics, funding, spot, prem)
    X, labels = align(X, make_labels(close, H))
    u = average_uniqueness(close.index, labels)
    k = int(np.searchsorted(labels.index, OOS_START))
    splitter = WalkForward(n_splits=N_SPLITS, min_train_frac=(k + 0.5) / len(labels))
    first_test = next(iter(splitter.split(labels["t1"])))[1][0]
    assert labels.index[first_test] == OOS_START, (labels.index[first_test], OOS_START)
    print(f"H={H} hysteresis={cfg}  labels {len(labels):,} ({labels.index[0]} ..), effective n "
          f"{effective_n(u):,.0f}, OOS from {OOS_START}")

    pos_fn = hyst_fn(close, cfg)
    res = {}
    for name, costs in (("taker", TAKER), ("maker", MAKER)):
        print(f"\n=== OOS validation_report, {name} cost ({costs.fee_bps}+{costs.slippage_bps} bps) ===")
        res[name] = validation_report(X, labels, close, splitter, costs=costs, weights=u, position_fn=pos_fn)
    preds = res["maker"]["preds"]
    assert preds.equals(res["taker"]["preds"]), "refits are not deterministic"
    preds.rename("prob_up").rename_axis("t0").to_frame().to_parquet(OUT / "preds.parquet")

    c = close.loc[preds.index[0]:preds.index[-1]]
    ppy = periods_per_year(c.index)
    target = pos_fn(preds)
    bt_m, bt_t = res["maker"]["backtest"], res["taker"]["backtest"]
    stats = bt_stats(bt_m, ppy)
    stats["sharpe_net_maker"] = stats.pop("sharpe_net")
    stats["sharpe_net_taker"] = res["taker"]["sharpe_net"]
    fund = {}
    for name, costs in (("taker", TAKER), ("maker", MAKER)):
        bf = run_backtest(c, target, costs, funding=funding)
        fund[name] = {"sharpe_net_with_funding": sharpe(bf["net"], ppy),
                      "funding_drag_ann": float(bf["funding"].mean() * ppy)}
    stats["mean_position"] = float(bt_m["held"].mean())

    # per-fold gross Sharpe (fold blocks = WalkForward test blocks)
    starts = [labels.index[te[0]] for _, te in splitter.split(labels["t1"])]
    fold = np.searchsorted(np.array(starts), bt_m.index, side="right") - 1
    folds = [{"fold": i + 1, "start": str(bt_m.index[fold == i][0].date()), "end": str(bt_m.index[fold == i][-1].date()),
              "sharpe_gross": sharpe(bt_m["gross"][fold == i], ppy), "sharpe_net_maker": sharpe(bt_m["net"][fold == i], ppy),
              "exposure": float((bt_m["held"][fold == i] != 0).mean())} for i in range(N_SPLITS)]

    # importance: refit the same folds (asserted identical), gain + OOS permutation
    y = (labels["label"].to_numpy() > 0).astype(int)
    nonzero = labels["label"].to_numpy() != 0
    w = u.reindex(labels.index).fillna(0).to_numpy()
    Xv = X.to_numpy()
    cols = list(X.columns)
    groups = {"basic": cols_basic, "positioning": cols_pos}
    for g in sorted({subgroup(c_) for c_ in cols_pos}):
        groups[f"pos:{g}"] = [c_ for c_ in cols_pos if subgroup(c_) == g]
    gain = np.zeros(len(cols))
    test_idx, base_p, models_ = [], [], []
    for tr, te in splitter.split(labels["t1"]):
        tr = tr[nonzero[tr]]
        m = default_model()
        m.fit(Xv[tr], y[tr], sample_weight=w[tr])
        g_ = m.booster_.feature_importance("gain")
        gain += g_ / g_.sum() / N_SPLITS
        test_idx.append(te)
        base_p.append(m.predict_proba(Xv[te])[:, 1])
        models_.append(m)
    te_all = np.concatenate(test_idx)
    assert np.array_equal(np.concatenate(base_p), preds.to_numpy()) and labels.index[te_all].equals(preds.index)
    lab_te = labels.iloc[te_all]
    base_auc = oos_auc(preds, labels)
    rng = np.random.default_rng(0)

    def perm_auc(col_names):
        ci = [cols.index(c_) for c_ in col_names]
        drops = []
        for _ in range(N_REPEATS):
            ps = []
            for m, te in zip(models_, test_idx):
                Xp = Xv[te].copy()
                Xp[:, ci] = Xp[rng.permutation(len(te))][:, ci]   # joint shuffle keeps within-group structure
                ps.append(m.predict_proba(Xp)[:, 1])
            drops.append(base_auc - oos_auc(pd.Series(np.concatenate(ps), lab_te.index), labels))
        return float(np.mean(drops)), float(np.std(drops))

    imp_groups = []
    for g, cs in groups.items():
        d, s = perm_auc(cs)
        imp_groups.append({"group": g, "n_features": len(cs),
                           "gain_share": float(gain[[cols.index(c_) for c_ in cs]].sum()),
                           "perm_auc_drop": d, "perm_auc_drop_sd": s})
    imp_feat = []
    for c_ in cols:
        d, s = perm_auc([c_])
        imp_feat.append({"feature": c_, "group": subgroup(c_), "gain_share": float(gain[cols.index(c_)]),
                         "perm_auc_drop": d, "perm_auc_drop_sd": s})
    imp_groups, imp_feat = pd.DataFrame(imp_groups), pd.DataFrame(imp_feat).sort_values("perm_auc_drop", ascending=False)

    trials = TrialLog("trials.json")
    if not args.no_log:
        trials.log(f"p03_positioning_H{H}", bt_m, {
            "features": f"basic_features ({len(cols_basic)}) + positioning_features ({len(cols_pos)})",
            "labels": f"triple_barrier H={H} pt=sl=1 width=ewm_vol(288)*sqrt(H)", "model": "default_model",
            "weights": "average_uniqueness", "cv": f"WalkForward({N_SPLITS}) from {OOS_START}",
            "position": "hysteresis_position", **cfg, "costs": [MAKER.fee_bps, MAKER.slippage_bps],
            "selection": "pre-OOS (t0, t1 < 2024-04-07): H by PurgedKFold gross Sharpe, hysteresis by maker net Sharpe"})
    summ = {"maker": summarize(bt_m, trials), "taker": summarize(bt_t, trials)}

    out = {"H": H, "hysteresis": cfg, "labels": len(labels), "effective_n": effective_n(u),
           "label_start": str(labels.index[0]), "oos_start": str(c.index[0]), "oos_end": str(c.index[-1]),
           "stats": stats, "funding": fund, "summary": summ, "folds": folds,
           "importance_groups": imp_groups.to_dict(orient="records"),
           "importance_features": imp_feat.to_dict(orient="records"), "oos_auc": base_auc,
           "validation": {k_: {kk: vv for kk, vv in r.items() if kk not in ("backtest", "preds")} for k_, r in res.items()}}
    (OUT / "results.json").write_text(json.dumps(out, indent=1, default=str))
    print("\n=== stats ===\n" + json.dumps({**stats, **{f"{k_}_{kk}": vv for k_, d in fund.items() for kk, vv in d.items()}}, indent=1))
    for k_, s in summ.items():
        print(f"{k_}: sharpe_net {s['sharpe_net']:+.3f}  psr {s['psr_vs_0']:.3f}  dsr {s.get('dsr', np.nan):.3f}  "
              f"n_trials {s.get('n_trials', len(trials))}")
    print("\n=== folds ===\n" + pd.DataFrame(folds).round(3).to_string(index=False))
    print("\n=== importance (groups) ===\n" + imp_groups.round(4).to_string(index=False))
    print("\n=== importance (top 15 features by permutation AUC drop) ===\n" + imp_feat.head(15).round(4).to_string(index=False))
    print(f"({time.time() - t:.0f}s)")
