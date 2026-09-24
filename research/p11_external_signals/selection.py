"""p11 pre-OOS (PLAN.md + amendment 1): IC screen, then LightGBM basic / external / both at H = 48
(primary) and H = 288 (secondary); kill / gate at H = 48. Labels t0 AND t1 < OOS start only;
PurgedKFold(5, 0.01); uniqueness weights; P2 = hysteresis(0.05, 0, 24) p02-exact; p05 cost table.
No OOS data is used for anything (features are computed on the full grid but only pre-OOS rows are read).

Run from the repo root:  PYTHONPATH=.:research/p11_external_signals python research/p11_external_signals/selection.py [--no-log]
"""
import argparse
import json
import time
from pathlib import Path

import lightgbm  # noqa: F401  (import order, see p10)
import numpy as np
import pandas as pd
from scipy import stats

from harness.backtest import CostModel, hysteresis_position, run_backtest
from harness.costs import TableCostModel, load_cost_table
from harness.cv import PurgedKFold
from harness.features import basic_features
from harness.labeling import ewm_vol, triple_barrier
from harness.metrics import periods_per_year, sharpe
from harness.nulls import circular_shift_null, feature_lookahead_audit
from harness.pipeline import default_model, oos_auc
from harness.weights import average_uniqueness

from features import NAN_TOLERANT, external_features

HERE = Path(__file__).parent
OOS_START = pd.Timestamp(json.loads(Path("research/p01_baseline/results.json").read_text())["oos_start"])
START, END = "2022-09-01", "2026-09-01"
P2 = {"theta_in": 0.05, "theta_out": 0.0, "min_hold": 24}
SPLITTER = PurgedKFold(5, embargo_frac=0.01)
GROSS = CostModel(0, 0)
AUC_MIN, BE_MIN, AUC_GAIN = 0.52, 4.0, 0.01


def oos_predict_nan(X, labels, weights):
    """harness.pipeline.oos_predict without the NaN row drop (LightGBM handles NaN natively)."""
    y = (labels["label"].to_numpy() > 0).astype(int)
    nonzero = labels["label"].to_numpy() != 0
    w = weights.reindex(labels.index).fillna(0).to_numpy()
    preds = pd.Series(np.nan, index=labels.index)
    Xv = X.to_numpy(dtype=float)
    for train, test in SPLITTER.split(labels["t1"]):
        train = train[nonzero[train]]
        m = default_model()
        m.fit(Xv[train], y[train], sample_weight=w[train])
        preds.iloc[test] = m.predict_proba(Xv[test])[:, 1]
    return preds.dropna()


def nw_t(d, lags=10):
    r = d - d.mean()
    acov = sum((1 - k / (lags + 1)) * 2 * (r[k:] * r[:-k].to_numpy()).mean() for k in range(1, lags + 1))
    return float(d.mean() / np.sqrt((r.var() + acov) / len(d)))


def evaluate(p, close, costs):
    grid = close.loc[p.index[0]:p.index[-1]]
    tgt = hysteresis_position(p.reindex(grid.index), **P2)          # p02-exact: bars without a prediction hold
    ppy = periods_per_year(grid.index)
    g = run_backtest(grid, tgt, GROSS)
    out = {"sharpe_gross": sharpe(g["gross"], ppy), "sharpe_gross_d2": sharpe(run_backtest(grid, tgt, GROSS, delay=2)["gross"], ppy)}
    for name, cm in costs.items():
        out[f"sharpe_net_{name}"] = sharpe(run_backtest(grid, tgt, cm)["net"], ppy)
        out[f"sharpe_net_{name}_d2"] = sharpe(run_backtest(grid, tgt, cm, delay=2)["net"], ppy)
    turnover = g["held"].diff().abs().fillna(g["held"].abs()).sum()
    dg = g["gross"].groupby(g.index.floor("1D")).sum()
    out.update({"turnover_per_year": float(turnover / (len(g) / ppy)),
                "breakeven_bps": float(g["gross"].sum() / turnover * 1e4),
                "breakeven_se_bps": float(dg.std() * np.sqrt(len(dg)) / turnover * 1e4),
                "breakeven_demeaned_bps": float((g["held"] * (g["ret"] - g["ret"].mean())).sum() / turnover * 1e4),
                "nw10_t_daily_gross": nw_t(dg), "mean_position": float(g["held"].mean()),
                "shift_null_p_gross": float(circular_shift_null(grid, tgt, GROSS, n=200)[2])})
    out["breakeven_minus_1se"] = out["breakeven_bps"] - out["breakeven_se_bps"]
    return out


def paired_auc_diff(pa, pb, labels, n_boot=200, seed=0):
    """AUC(pa) - AUC(pb) on the same labels, with a day-block bootstrap s.e."""
    lab = labels.loc[pa.index, "label"]
    k = lab != 0
    y, a, b = (lab[k] > 0).astype(int).to_numpy(), pa[k].to_numpy(), pb.reindex(pa.index)[k].to_numpy()
    from sklearn.metrics import roc_auc_score
    d0 = roc_auc_score(y, a) - roc_auc_score(y, b)
    day = pa.index[k.to_numpy()].floor("1D")
    udays = np.unique(day)
    pos = {d: np.nonzero(day == d)[0] for d in udays}
    rng = np.random.default_rng(seed)
    ds = []
    for _ in range(n_boot):
        idx = np.concatenate([pos[d] for d in rng.choice(udays, len(udays))])
        if len(np.unique(y[idx])) < 2:
            continue
        ds.append(roc_auc_score(y[idx], a[idx]) - roc_auc_score(y[idx], b[idx]))
    return float(d0), float(np.std(ds))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-log", action="store_true")
    a = ap.parse_args()
    t_start = time.time()
    log = lambda s: print(s, flush=True)   # noqa: E731
    bars = pd.read_parquet("data/bars/BTCUSDT-5m-2022-08_2026-08.parquet")
    close = bars["close"]
    pre_idx = close.loc[pd.Timestamp(START, tz="UTC"):OOS_START].index
    pre_idx = pre_idx[pre_idx < OOS_START]
    Xb_all = basic_features(bars)
    Xe, info = external_features(bars, pre_idx)                     # evaluated on pre-OOS bar closes only
    log(json.dumps(info))
    table = load_cost_table()
    costs = {"maker": TableCostModel(table, "BTCUSDT", "maker_all_in_bps"),
             "taker": TableCostModel(table, "BTCUSDT", "taker_all_in_bps")}
    out = {"info": info, "screen": {}, "models": {}, "sample": {}}
    rows = []
    req_cols = [c for c in Xe.columns if c not in NAN_TOLERANT]
    for H in (48, 288):
        lab = triple_barrier(close, H, ewm_vol(close, 288) * np.sqrt(H), pt_mult=1.0, sl_mult=1.0)
        lab = lab.loc[START:END]
        lab = lab[(lab.index < OOS_START) & (lab["t1"] < OOS_START)]
        u = average_uniqueness(close.index, lab)
        Xb, X = Xb_all.reindex(lab.index), Xe.reindex(lab.index)
        common = Xb.notna().all(axis=1) & X[req_cols].notna().all(axis=1)
        out["sample"][H] = {"labels_pre_oos": int(len(lab)), "common": int(common.sum()),
                            "first": str(lab.index[common.to_numpy()][0]), "effective_n": float(u.reindex(lab.index[common]).sum()),
                            "dropped_by_col": {c: int(X[c].isna().sum()) for c in X.columns if X[c].isna().any()},
                            "nan_tolerant_share_nan": {c: float(X.loc[common, c].isna().mean()) for c in NAN_TOLERANT}}
        lab, Xb, X = lab[common], Xb[common], X[common]
        uu = u.reindex(lab.index)
        log(f"H={H}: " + json.dumps(out["sample"][H]))
        # ---- screen: Spearman IC vs realised label return, t on effective n
        scr = {}
        for c in X.columns:
            k = X[c].notna()
            ic = stats.spearmanr(X.loc[k, c], lab.loc[k, "ret"]).statistic
            neff = float(uu[k].sum())
            t = ic * np.sqrt(max(neff - 2, 1)) / np.sqrt(max(1 - ic * ic, 1e-12))
            scr[c] = {"ic": float(ic), "t_eff": float(t), "n": int(k.sum()), "n_eff": neff}
            rows.append({"kind": "ic_screen", "name": f"p11 IC {c} H={H}", "ic": float(ic), "t_eff": float(t), "n_eff": neff,
                         "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})
        out["screen"][H] = scr
        log(f"H={H} screen |t|>=2: " + json.dumps({c: round(v["t_eff"], 2) for c, v in scr.items() if abs(v["t_eff"]) >= 2}))
        if H == 48:
            aud = feature_lookahead_audit(pd.concat([Xb, X.fillna(X.median())], axis=1), close)
            out["lookahead_suspects"] = list(aud.index[aud["suspect"]])
            log(f"lookahead suspects: {out['lookahead_suspects']}")
        # ---- models
        preds = {}
        for name, XX in (("basic", Xb), ("external", X), ("both", pd.concat([Xb, X], axis=1))):
            p = oos_predict_nan(XX, lab, uu)
            preds[name] = p
            r = {"auc": oos_auc(p, lab), **evaluate(p, close, costs)}
            out["models"][f"H{H}/{name}"] = r
            log(f"H={H} {name}: " + json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}))
            rows.append({"kind": "model", "name": f"p11 H={H} {name}", "params": {"H": H, "features": name, "positions": P2,
                         "cv": "PurgedKFold(5, 0.01)", "costs": "p05 table"}, "auc": r["auc"], "breakeven_bps": r["breakeven_bps"],
                         "breakeven_se_bps": r["breakeven_se_bps"], "sharpe_gross": r["sharpe_gross"],
                         "sharpe_net_maker": r["sharpe_net_maker"], "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})
        d, se = paired_auc_diff(preds["both"], preds["basic"], lab)
        out["models"][f"H{H}/both_minus_basic_auc"] = {"diff": d, "boot_se": se}
        log(f"H={H} AUC(both) - AUC(basic) = {d:+.4f} (day-block bootstrap s.e. {se:.4f})")
        pd.DataFrame(preds).rename_axis("t0").to_parquet(HERE / f"preds_selection_H{H}.parquet")

    m = out["models"]
    best = max(("H48/basic", "H48/external", "H48/both"), key=lambda k: m[k]["breakeven_bps"])
    ext_auc, gain = m["H48/external"]["auc"], m["H48/both_minus_basic_auc"]["diff"]
    if m[best]["breakeven_bps"] < BE_MIN or ext_auc < AUC_MIN:
        decision = (f"KILL: best H=48 configuration {best} breakeven {m[best]['breakeven_bps']:.2f} bps"
                    f"{' < 4' if m[best]['breakeven_bps'] < BE_MIN else ''}; external-only AUC {ext_auc:.4f}"
                    f"{' < 0.52' if ext_auc < AUC_MIN else ''}")
    elif m[best]["breakeven_minus_1se"] >= BE_MIN and gain >= AUC_GAIN:
        decision = f"GATE: {best} breakeven - 1 s.e. {m[best]['breakeven_minus_1se']:.2f} >= 4 and both - basic AUC {gain:+.4f} >= 0.01"
    else:
        decision = (f"STOP (no gate): {best} breakeven - 1 s.e. {m[best]['breakeven_minus_1se']:.2f}, "
                    f"both - basic AUC {gain:+.4f}")
    out["best_H48"], out["decision"] = best, decision
    (HERE / "selection.json").write_text(json.dumps(out, indent=1, default=str))
    if not a.no_log:
        path = HERE / "selection_trials.json"
        prev = json.loads(path.read_text()) if path.exists() else []
        path.write_text(json.dumps(prev + rows, indent=1, default=str))
    log(f"DECISION: {decision}  ({time.time() - t_start:.0f}s)")
