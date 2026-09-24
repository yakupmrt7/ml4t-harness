"""p10 pre-OOS selection (PLAN.md): labels with t0 AND t1 < OOS start only; PurgedKFold(5, 0.01);
uniqueness weights. 8 configurations {A-basic, A-flow, A-both, B-TCN} x {P1, P2}, each a row in
selection_trials.json. Kill / gate check at the end. No OOS data is read (flow days >= the OOS
start date are never loaded).

All configurations use ONE common sample: labels where basic features, flow features and a complete
240-minute TCN window all exist, so the ablation compares like with like.

Run from the repo root:  PYTHONPATH=.:research/p10_orderflow_1h python research/p10_orderflow_1h/selection.py [--no-log]
"""
import argparse
import json
import time

import lightgbm  # noqa: F401  must load before torch: torch-first import segfaults LightGBM on macOS (OpenMP clash)

import numpy as np
import pandas as pd

from harness.backtest import CostModel, hysteresis_position, run_backtest, signal_to_position
from harness.costs import TableCostModel, load_cost_table
from harness.cv import PurgedKFold
from harness.features import basic_features
from harness.metrics import periods_per_year, sharpe
from harness.nulls import circular_shift_null, feature_lookahead_audit
from harness.pipeline import oos_auc, oos_predict

import tcn as T
from common import OOS_START, OUT, flow_features, load_bars, load_flow, p01_labels, tcn_channels

SPLITTER = PurgedKFold(5, embargo_frac=0.01)
P1 = {"mode": "sign", "threshold": 0.02, "smooth": 12}
P2 = {"theta_in": 0.05, "theta_out": 0.0, "min_hold": 24}
AUC_MIN, BE_MIN = 0.52, 4.0
GROSS = CostModel(0, 0)


def positions(p, rule):
    return signal_to_position(p, **P1) if rule == "P1" else hysteresis_position(p, **P2)


def nw_t(d, lags=10):
    r = d - d.mean()
    acov = sum((1 - k / (lags + 1)) * 2 * (r[k:] * r[:-k].to_numpy()).mean() for k in range(1, lags + 1))
    return float(d.mean() / np.sqrt((r.var() + acov) / len(d)))


def evaluate(p, close, costs, rule):
    tgt = positions(p, rule)
    c = close.loc[tgt.index[0]:tgt.index[-1]]
    out = {}
    bt = {}
    for d in (1, 2):
        bt[("gross", d)] = run_backtest(c, tgt, GROSS, delay=d)
        for name, cm in costs.items():
            bt[(name, d)] = run_backtest(c, tgt, cm, delay=d)
    g = bt[("gross", 1)]
    ppy = periods_per_year(g.index)
    turnover = g["held"].diff().abs().fillna(g["held"].abs()).sum()
    dg = g["gross"].groupby(g.index.floor("1D")).sum()
    out["sharpe_gross"] = sharpe(g["gross"], ppy)
    out["sharpe_gross_d2"] = sharpe(bt[("gross", 2)]["gross"], ppy)
    for name in costs:
        out[f"sharpe_net_{name}"] = sharpe(bt[(name, 1)]["net"], ppy)
        out[f"sharpe_net_{name}_d2"] = sharpe(bt[(name, 2)]["net"], ppy)
    years = len(g) / ppy
    out["turnover_per_year"] = float(turnover / years)
    out["breakeven_bps"] = float(g["gross"].sum() / turnover * 1e4)
    out["breakeven_se_bps"] = float(dg.std() * np.sqrt(len(dg)) / turnover * 1e4)
    out["breakeven_minus_1se"] = out["breakeven_bps"] - out["breakeven_se_bps"]
    out["nw10_t_daily_gross"] = nw_t(dg)
    out["exposure"] = float((g["held"] != 0).mean())
    out["shift_null_p_gross"] = float(circular_shift_null(c, tgt, GROSS, n=200)[2])
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-log", action="store_true")
    a = ap.parse_args()
    t_start = time.time()
    log = lambda s: print(s, flush=True)   # noqa: E731
    bars = load_bars()
    close = bars["close"]
    labels, u = p01_labels(bars)
    pre = (labels.index < OOS_START) & (labels["t1"] < OOS_START)
    labels = labels[pre]
    assert labels["t1"].max() < OOS_START and labels.index.max() < OOS_START
    flow = load_flow(pre_oos_only=True)
    assert flow.index.max() <= OOS_START.floor("D") + pd.Timedelta("1D")
    Xb = basic_features(bars).reindex(labels.index)
    Xf = flow_features(flow, labels.index)
    C = tcn_channels(flow)
    M = C.to_numpy(np.float32)
    end = T.valid_end_rows(C.index, M, labels.index)
    common = Xb.notna().all(1) & Xf.notna().all(1) & pd.Series(end >= 0, index=labels.index)
    info = {"labels_pre_oos": int(len(labels)), "common_sample": int(common.sum()),
            "dropped_basic_nan": int((~Xb.notna().all(1)).sum()), "dropped_flow_nan": int((~Xf.notna().all(1)).sum()),
            "dropped_tcn_window": int((end < 0).sum()), "first": str(labels.index[common.to_numpy()][0]),
            "last": str(labels.index[common.to_numpy()][-1]), "n_flow_features": Xf.shape[1]}
    labels, Xb, Xf, end = labels[common], Xb[common], Xf[common], end[common.to_numpy()]
    uu = u.reindex(labels.index)
    info["effective_n"] = float(uu.sum())
    log(json.dumps(info))
    aud = feature_lookahead_audit(pd.concat([Xb, Xf], axis=1), close)
    info["lookahead_suspects"] = list(aud.index[aud["suspect"]])
    log(f"lookahead suspects: {info['lookahead_suspects']}")

    table = load_cost_table()
    costs = {"maker": TableCostModel(table, "BTCUSDT", "maker_all_in_bps"),
             "taker": TableCostModel(table, "BTCUSDT", "taker_all_in_bps")}
    preds, rows, results = {}, [], {}
    for name, X in (("A-basic", Xb), ("A-flow", Xf), ("A-both", pd.concat([Xb, Xf], axis=1))):
        t = time.time()
        preds[name] = oos_predict(X, labels, SPLITTER, weights=uu)
        log(f"{name}: AUC {oos_auc(preds[name], labels):.4f} ({time.time() - t:.0f}s)")
    t = time.time()
    preds["B-TCN"], tcn_info = T.tcn_oos_predict(T.Windows(M, end), labels, uu, SPLITTER, log=log)
    info["tcn_folds"] = tcn_info
    log(f"B-TCN: AUC {oos_auc(preds['B-TCN'], labels):.4f} ({time.time() - t:.0f}s)")
    pd.DataFrame(preds).rename_axis("t0").to_parquet(OUT / "preds_selection.parquet")

    for name, p in preds.items():
        auc = oos_auc(p, labels)
        for rule in ("P1", "P2"):
            r = {"model": name, "positions": rule, "auc": auc, **evaluate(p, close, costs, rule)}
            results[f"{name}/{rule}"] = r
            log(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}))
            rows.append({"kind": "model", "name": f"p10 {name} {rule}",
                         "params": {"model": name, "positions": P1 if rule == "P1" else P2, "cv": "PurgedKFold(5, 0.01)",
                                    "labels": "p01 triple_barrier H=12", "weights": "average_uniqueness",
                                    "sample": "pre-OOS common sample"},
                         "auc": auc, "breakeven_bps": r["breakeven_bps"], "breakeven_se_bps": r["breakeven_se_bps"],
                         "sharpe_gross": r["sharpe_gross"], "sharpe_net_maker": r["sharpe_net_maker"],
                         "turnover_per_year": r["turnover_per_year"], "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})

    eligible = {k: v for k, v in results.items() if v["auc"] >= AUC_MIN}
    best = max(eligible, key=lambda k: eligible[k]["breakeven_bps"]) if eligible else None
    if best is None:
        decision = "KILL: pooled AUC < 0.52 for every configuration"
    elif eligible[best]["breakeven_bps"] < BE_MIN:
        decision = f"KILL: best configuration {best} breakeven {eligible[best]['breakeven_bps']:.2f} < {BE_MIN} bps"
    elif eligible[best]["breakeven_minus_1se"] >= BE_MIN:
        decision = f"GATE: {best} breakeven - 1 s.e. = {eligible[best]['breakeven_minus_1se']:.2f} >= {BE_MIN}; ask owner"
    else:
        decision = f"STOP: {best} breakeven {eligible[best]['breakeven_bps']:.2f} >= {BE_MIN} but - 1 s.e. < {BE_MIN}"
    out = {"info": info, "results": results, "best": best, "decision": decision}
    (OUT / "selection.json").write_text(json.dumps(out, indent=1, default=str))
    if not a.no_log:
        path = OUT / "selection_trials.json"
        prev = json.loads(path.read_text()) if path.exists() else []
        path.write_text(json.dumps(prev + rows, indent=1, default=str))
    log(f"DECISION: {decision}  ({time.time() - t_start:.0f}s)")
