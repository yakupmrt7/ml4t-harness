"""p03 selection, PRE-OOS ONLY (label t0 and t1 < 2024-04-07). No trial.

1. Lookahead audit of every feature (basic + positioning) on pre-OOS rows.
2. Univariate screening: Spearman IC of each feature vs the forward log return
   at H = 12, 48, 288 bars; t = IC * sqrt(n_eff), n_eff = sum of uniqueness of
   the H-bar forward windows (~N/H).
3. Choice of H in {48, 288}: PurgedKFold(5, 0.01) predictions of the full
   model (basic + positioning), triple-barrier labels at H. Pre-declared rule:
   the higher pre-OOS GROSS Sharpe wins (positions: sign, threshold 0.02,
   smoothed over H bars = the p01 rule scaled to H); AUC reported alongside.
   Basic-only models at each H are run too, for attribution only.
4. Hysteresis thresholds for the chosen H (min_hold scaled to H), selected by
   net Sharpe at maker cost, as in p02.

Writes selection.json and appends everything to selection_trials.json
(skipped with --no-log). Selection predictions -> preds_selection_H<H>.parquet.

Run from the repo root:  python research/p03_positioning_features/selection.py [--no-log]
"""
import argparse
import itertools
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from harness.backtest import run_backtest, signal_to_position
from harness.cv import PurgedKFold
from harness.labeling import fixed_horizon_labels
from harness.metrics import periods_per_year, sharpe
from harness.nulls import feature_lookahead_audit
from harness.pipeline import align, oos_auc, oos_predict
from harness.weights import average_uniqueness, effective_n

from common import (MAKER, OUT, SEL_END, TAKER, bt_stats, build_features, hyst_fn, load_inputs,
                    make_labels, pre_oos, subgroup)

SCREEN_H = (12, 48, 288)
CANDIDATE_H = (48, 288)


def log_row(rows, kind, name, params, extra=None, net=None):
    r = {"kind": kind, "name": name, "params": params, **(extra or {}),
         "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if net is not None:   # TrialLog-compatible fields
        r["sr_per_period"], r["n"] = sharpe(net), int(len(net))
    rows.append(r)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-log", action="store_true")
    args = ap.parse_args()
    t = time.time()
    bars, metrics, funding, spot, prem, info = load_inputs()
    close = bars["close"]
    X, cols_basic, cols_pos = build_features(bars, metrics, funding, spot, prem)
    X = X.dropna()
    X_pre = X[X.index < SEL_END]
    X_pre = X_pre.loc[X_pre.index >= pd.Timestamp("2022-09-01", tz="UTC")]
    log = []
    out = {"data": info, "n_features": {"basic": len(cols_basic), "positioning": len(cols_pos)},
           "pre_oos_rows": len(X_pre), "pre_oos_start": str(X_pre.index[0]), "pre_oos_end": str(X_pre.index[-1])}
    print(f"pre-OOS feature rows {len(X_pre):,}: {X_pre.index[0]} .. {X_pre.index[-1]}")

    # ---- 1. lookahead audit ------------------------------------------------
    audit = feature_lookahead_audit(X_pre, close)
    audit["group"] = [subgroup(c) for c in audit.index]
    out["lookahead_audit"] = audit.reset_index().to_dict(orient="records")
    print("\nLOOKAHEAD AUDIT (pre-OOS): suspects =", audit.index[audit["suspect"]].tolist())
    print(audit.round(4).to_string())
    if audit["suspect"].any():
        raise SystemExit("lookahead suspects: stop and investigate before anything else")

    # ---- 2. univariate IC screening ---------------------------------------
    lc = np.log(close)
    scr = []
    for H in SCREEN_H:
        fwd = (lc.shift(-H) - lc).reindex(X_pre.index)
        end = pd.Series(close.index, close.index).shift(-H).reindex(X_pre.index)
        m = fwd.notna() & (end < SEL_END)
        fh = fixed_horizon_labels(close, H).reindex(X_pre.index[m])
        n_eff = effective_n(average_uniqueness(close.index, fh))
        for c in X_pre.columns:
            ic = X_pre.loc[m, c].corr(fwd[m], method="spearman")
            scr.append({"feature": c, "group": subgroup(c), "H": H, "ic": ic, "n": int(m.sum()),
                        "n_eff": n_eff, "t_eff": ic * np.sqrt(n_eff)})
            log_row(log, "ic", f"ic {c} H={H}", {"feature": c, "H": H}, {"ic": ic, "t_eff": ic * np.sqrt(n_eff)})
    scr = pd.DataFrame(scr)
    out["screening"] = scr.to_dict(orient="records")
    piv = scr.pivot(index="feature", columns="H", values="t_eff")
    piv["group"] = [subgroup(c) for c in piv.index]
    print("\nIC SCREENING t-stats (effective n):")
    print(piv.sort_values(288, key=np.abs, ascending=False).round(2).to_string())

    # ---- 3. choose H -------------------------------------------------------
    models, preds_full = [], {}
    for H in CANDIDATE_H:
        lab = pre_oos(make_labels(close, H))
        Xa, lab = align(X_pre, lab)
        u = average_uniqueness(close.index, lab)
        for fs, cols in (("basic", cols_basic), ("basic+positioning", cols_basic + cols_pos)):
            p = oos_predict(Xa[cols], lab, PurgedKFold(5, embargo_frac=0.01), weights=u)
            c = close.loc[p.index[0]:p.index[-1]]
            ppy = periods_per_year(c.index)
            pos = signal_to_position(p, mode="sign", threshold=0.02, smooth=H)
            bt_m = run_backtest(c, pos, MAKER)
            s = bt_stats(bt_m, ppy)
            row = {"H": H, "features": fs, "labels": len(lab), "effective_n": effective_n(u),
                   "auc": oos_auc(p, lab), "sharpe_gross": s["sharpe_gross"], "sharpe_net_maker": s["sharpe_net"],
                   "sharpe_net_taker": sharpe(run_backtest(c, pos, TAKER)["net"], ppy),
                   "turnover_per_year": s["turnover_per_year"], "breakeven_bps": s["breakeven_bps"]}
            models.append(row)
            log_row(log, "model", f"model H={H} {fs}", {"H": H, "features": fs, "cv": "PurgedKFold(5, 0.01)",
                    "pos": {"mode": "sign", "threshold": 0.02, "smooth": H}, "costs": "maker 2+0.5"},
                    {k: row[k] for k in ("auc", "sharpe_gross")}, net=bt_m["net"])
            if fs == "basic+positioning":
                preds_full[H] = p
    models = pd.DataFrame(models)
    out["models"] = models.to_dict(orient="records")
    print("\nMODELS (pre-OOS, PurgedKFold):")
    print(models.round(3).to_string(index=False))
    full = models[models["features"] == "basic+positioning"].set_index("H")
    H = int(full["sharpe_gross"].idxmax())
    out["chosen_H"] = H
    out["chosen_H_rule"] = "max pre-OOS gross Sharpe of the full model (sign, 0.02, smooth H)"
    out["chosen_H_auc_above_half"] = bool(full.loc[H, "auc"] > 0.5)
    print(f"\nCHOSEN H = {H}  (AUC {full.loc[H, 'auc']:.4f}, gross Sharpe {full.loc[H, 'sharpe_gross']:+.3f})")

    # ---- 4. hysteresis thresholds for H ------------------------------------
    p = preds_full[H]
    p.rename("prob_up").rename_axis("t0").to_frame().to_parquet(OUT / f"preds_selection_H{H}.parquet")
    c = close.loc[p.index[0]:p.index[-1]]
    ppy = periods_per_year(c.index)
    grid = []
    for ti, f, mh in itertools.product((0.01, 0.02, 0.03, 0.05), (0.0, 0.5), (H // 12, H // 2, H, 2 * H)):
        cfg = {"theta_in": ti, "theta_out": round(f * ti, 4), "min_hold": mh}
        pos = hyst_fn(close, cfg)(p)
        bt_m = run_backtest(c, pos, MAKER)
        s = bt_stats(bt_m, ppy)
        grid.append({**cfg, "sharpe_gross": s["sharpe_gross"], "sharpe_net_maker": s["sharpe_net"],
                     "sharpe_net_taker": sharpe(run_backtest(c, pos, TAKER)["net"], ppy),
                     **{k: s[k] for k in ("turnover_per_year", "breakeven_bps", "exposure", "avg_hold_hours")}})
        log_row(log, "positioning", f"hyst H={H} in={ti} out={cfg['theta_out']} hold={mh}", {"H": H, **cfg,
                "costs": "maker 2+0.5"}, {"sharpe_gross": s["sharpe_gross"]}, net=bt_m["net"])
    grid = pd.DataFrame(grid)
    best = grid.loc[grid["sharpe_net_maker"].idxmax()]
    out["hysteresis_grid"] = grid.to_dict(orient="records")
    out["hysteresis"] = {"theta_in": float(best["theta_in"]), "theta_out": float(best["theta_out"]),
                         "min_hold": int(best["min_hold"])}
    print("\nHYSTERESIS GRID (pre-OOS):")
    print(grid.sort_values("sharpe_net_maker", ascending=False).round(3).to_string(index=False))
    print("SELECTED:", out["hysteresis"])

    (OUT / "selection.json").write_text(json.dumps(out, indent=1, default=str))
    if not args.no_log:
        path = OUT / "selection_trials.json"
        prev = json.loads(path.read_text()) if path.exists() else []
        path.write_text(json.dumps(prev + log, indent=1, default=str))
    print(f"({time.time() - t:.0f}s)")
