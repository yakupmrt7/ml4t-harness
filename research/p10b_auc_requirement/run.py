"""p10b (PLAN.md): breakeven vs pooled AUC for synthetic predictions on p10's pre-OOS sample.
p_k = sigmoid(logit(p_A-basic) + k * (sign(label) + N(0,1))), k bisected per target AUC; P2 exactly as
p02 runs it (hysteresis on the full bar grid); plain and de-meaned breakeven; required AUC for
3.4 / 4.0 / 5.5 bps by linear interpolation. Pre-OOS only; no refit; 0 OOS trials.

Run from the repo root:  PYTHONPATH=.:research/p10_orderflow_1h python research/p10b_auc_requirement/run.py
"""
import json
import time
from pathlib import Path

import lightgbm  # noqa: F401  (import order: see p10 selection.py)
import numpy as np
import pandas as pd

from harness.backtest import CostModel, hysteresis_position, run_backtest
from harness.costs import TableCostModel, load_cost_table
from harness.metrics import periods_per_year, sharpe
from harness.pipeline import oos_auc

import selection as S10
from common import OOS_START, load_bars, p01_labels

HERE = Path(__file__).parent
P2 = {"theta_in": 0.05, "theta_out": 0.0, "min_hold": 24}
TARGETS = [round(0.55 + 0.01 * i, 2) for i in range(11)]
LEVELS = {"bare_maker_3.4": 3.4, "gate_4.0": 4.0, "taker_5.5": 5.5}
SEEDS = [0, 1, 2]
GROSS = CostModel(0, 0)


def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def evaluate(p, close, maker):
    grid = close.loc[p.index[0]:p.index[-1]]
    tgt = hysteresis_position(p.reindex(grid.index), **P2)          # p02-exact: NaN bars hold, min_hold in bars
    g = run_backtest(grid, tgt, GROSS)
    n = run_backtest(grid, tgt, maker)
    ppy = periods_per_year(g.index)
    turnover = g["held"].diff().abs().fillna(g["held"].abs()).sum()
    gross_dm = g["held"] * (g["ret"] - g["ret"].mean())
    dg = g["gross"].groupby(g.index.floor("1D")).sum()
    return {"turnover_per_year": float(turnover / (len(g) / ppy)),
            "breakeven_bps": float(g["gross"].sum() / turnover * 1e4),
            "breakeven_se_bps": float(dg.std() * np.sqrt(len(dg)) / turnover * 1e4),
            "breakeven_demeaned_bps": float(gross_dm.sum() / turnover * 1e4),
            "sharpe_gross": sharpe(g["gross"], ppy), "sharpe_net_maker": sharpe(n["net"], ppy),
            "mean_position": float(g["held"].mean())}


def required(aucs, bes, level):
    a, b = np.array(aucs), np.array(bes)
    above = np.where(b >= level)[0]
    if not len(above):
        return f"> {a.max():.2f}"
    i = above[0]
    if i == 0:
        return f"<= {a[0]:.2f}"
    return float(a[i - 1] + (level - b[i - 1]) * (a[i] - a[i - 1]) / (b[i] - b[i - 1]))


if __name__ == "__main__":
    t_start = time.time()
    bars = load_bars()
    close = bars["close"]
    labels, _ = p01_labels(bars)
    base = pd.read_parquet("research/p10_orderflow_1h/preds_selection.parquet")["A-basic"].dropna()
    labels = labels.loc[base.index]
    assert labels.index.max() < OOS_START and labels["t1"].max() < OOS_START
    maker = TableCostModel(load_cost_table(), "BTCUSDT", "maker_all_in_bps")
    lb = logit(base.to_numpy())
    sgn = np.sign(labels["label"].to_numpy())
    out = {"n_labels": len(labels), "base_auc": oos_auc(base, labels), "base": evaluate(base, close, maker), "curves": {}}
    print(json.dumps({k: out[k] for k in ("n_labels", "base_auc")}), json.dumps(out["base"]), flush=True)

    # ---- row zero (amendment 1): k = 0 through the synthetic path, two P2 implementations, exact
    p0 = pd.Series(1 / (1 + np.exp(-(lb + 0.0 * sgn))), base.index)
    ref = json.loads(Path("research/p10_orderflow_1h/selection.json").read_text())["results_held"]["A-basic/P2"]
    orig = S10.positions
    S10.positions = lambda p, rule: (lambda t: t.reindex(close.loc[t.index[0]:t.index[-1]].index).ffill())(orig(p, rule))
    table = load_cost_table()
    ra = S10.evaluate(p0, close, {"maker": maker, "taker": TableCostModel(table, "BTCUSDT", "taker_all_in_bps")}, "P2")
    S10.positions = orig
    rb = evaluate(p0, close, maker)
    auc0 = oos_auc(p0, labels)
    row0 = {"a_p10_rule": {"auc": auc0, "breakeven_bps": ra["breakeven_bps"], "turnover_per_year": ra["turnover_per_year"],
                           "ref_auc": ref["auc"], "ref_breakeven_bps": ref["breakeven_bps"], "ref_turnover_per_year": ref["turnover_per_year"]},
            "b_p02_exact": {"auc": auc0, "breakeven_bps": rb["breakeven_bps"], "turnover_per_year": rb["turnover_per_year"],
                            "ref_breakeven_bps": 1.864324984464265}}
    ok_a = all(abs(row0["a_p10_rule"][k] - row0["a_p10_rule"]["ref_" + k]) <= 1e-9 * max(1, abs(row0["a_p10_rule"]["ref_" + k]))
               for k in ("auc", "breakeven_bps", "turnover_per_year"))
    ok_b = abs(rb["breakeven_bps"] - 1.864324984464265) <= 1e-9
    row0["pass"] = bool(ok_a and ok_b)
    out["row_zero"] = row0
    print("ROW ZERO", json.dumps(row0), flush=True)
    if not row0["pass"]:
        (HERE / "results_rowzero_FAIL.json").write_text(json.dumps(row0, indent=1))
        raise SystemExit("STOP: row zero does not reproduce p10 -> synthetic machinery wrong")

    rows = []
    absr = labels["ret"].abs().to_numpy()
    arms = {"direction": sgn, "magnitude": sgn * absr / absr.std()}
    for arm, sig in arms.items():
      for seed in SEEDS:
        s = sig + np.random.default_rng(seed).standard_normal(len(sgn))
        curve = []
        for target in TARGETS:
            lo, hi = 0.0, 2.0
            for _ in range(60):
                k = (lo + hi) / 2
                auc = oos_auc(pd.Series(1 / (1 + np.exp(-(lb + k * s))), base.index), labels)
                if abs(auc - target) <= 0.0005:
                    break
                lo, hi = (k, hi) if auc < target else (lo, k)
            p = pd.Series(1 / (1 + np.exp(-(lb + k * s))), base.index)
            r = {"target_auc": target, "auc": auc, "k": k, **evaluate(p, close, maker)}
            curve.append(r)
            print(arm, seed, json.dumps({kk: round(v, 4) for kk, v in r.items()}), flush=True)
            rows.append({"kind": "measurement", "name": f"p10b synthetic AUC {target:.2f} seed {seed}" + ("" if arm == "direction" else " magnitude-arm"), "params": {
                "target_auc": target, "seed": seed, "k": k, "positions": "P2 p02-exact", "costs": "p05 maker table"},
                "auc": auc, "breakeven_bps": r["breakeven_bps"], "breakeven_demeaned_bps": r["breakeven_demeaned_bps"],
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})
        req = {f"{name}_{kind}": required([c["auc"] for c in curve], [c[col] for c in curve], lvl)
               for name, lvl in LEVELS.items() for kind, col in (("plain", "breakeven_bps"), ("demeaned", "breakeven_demeaned_bps"))}
        (out["curves"] if arm == "direction" else out.setdefault("curves_magnitude", {}))[f"seed{seed}"] = {"points": curve, "required_auc": req}
        print("REQUIRED", arm, "seed", seed, json.dumps(req), flush=True)
    r0 = out["curves"]["seed0"]["required_auc"]["gate_4.0_plain"]
    num = r0 if isinstance(r0, float) else (1.0 if r0.startswith(">") else 0.0)
    out["decision"] = ("KILL: AUC needed for 4 bps >= 0.58 -> 1h/4h BTC bar-direction line closed for good" if num >= 0.58 else
                       "flow v2 PLAN allowed (< 0.56)" if num < 0.56 else "0.56-0.58: abandon unless the owner funds v2")
    out["required_auc_for_4bps_seed0"] = r0
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    (HERE / "selection_trials.json").write_text(json.dumps(rows, indent=1, default=str))
    print("DECISION:", out["decision"], f"({time.time() - t_start:.0f}s)")
