"""p02 positioning: same data/features/labels/model/costs as p01; only the
prediction -> position mapping changes (hysteresis_position).

1. Selection on PRE-OOS data only (label t0 < 2024-04-07): PurgedKFold(5)
   predictions, grid over theta_in x theta_out x min_hold, pick the best net
   Sharpe at maker cost. Grid runs go to selection_trials.json.
2. The chosen config is run ONCE on p01's OOS predictions (preds.parquet, no
   refit), through validation_report at taker and maker cost. One trial,
   "p02_hysteresis" (maker backtest), is logged to trials.json.

Run from the repo root:  python research/p02_positioning/run.py [--no-log]
--no-log re-runs an identical config without logging to trials.json or
selection_trials.json. Selection predictions are saved to
preds_selection.parquet (gitignored). The OOS predictions are p01's.
"""
import argparse
import itertools
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from harness.backtest import CostModel, hysteresis_position, run_backtest, signal_to_position
from harness.cv import PurgedKFold, WalkForward
from harness.data import load_binance_klines
from harness.features import basic_features
from harness.labeling import ewm_vol, triple_barrier
from harness.metrics import TrialLog, periods_per_year, sharpe, summarize
from harness.nulls import validation_report
from harness.pipeline import oos_auc, oos_predict
from harness.weights import average_uniqueness, effective_n

OUT = Path(__file__).parent
P01 = Path("research/p01_baseline")
START, END = "2022-09-01", "2026-09-01"   # label t0 window [START, END), as p01
SEL_END = pd.Timestamp("2024-04-07", tz="UTC")   # selection uses label t0 < SEL_END only
H = 12
TAKER = CostModel(fee_bps=5, slippage_bps=0.5)
MAKER = CostModel(fee_bps=2, slippage_bps=0.5)
SPLITTER = WalkForward(n_splits=8, min_train_frac=0.4)   # p01's, for validation_report's refits
P01_POS = {"mode": "sign", "threshold": 0.02, "smooth": H}
GRID = [
    {"theta_in": ti, "theta_out": round(f * ti, 4), "min_hold": mh}
    for ti, f, mh in itertools.product((0.01, 0.02, 0.03, 0.05), (0.0, 0.5), (1, 6, 12, 24))
]


def load_bars():
    cache = Path("data/bars/BTCUSDT-5m-2022-08_2026-08.parquet")
    if cache.exists():
        return pd.read_parquet(cache)
    files = [f"data/raw/BTCUSDT-5m-{y}-{m:02d}.zip" for y in range(2022, 2027) for m in range(1, 13)]
    files = [f for f in files if "2022-08" <= f[-11:-4] <= "2026-08" and Path(f).exists()]
    bars = pd.concat(load_binance_klines(f) for f in files)
    bars = bars[~bars.index.duplicated()].sort_index()
    bars.to_parquet(cache)
    return bars


def hyst_fn(close, cfg):
    """preds -> hysteresis target on the full bar grid (bars with no
    prediction hold the current position instead of forcing flat)."""
    return lambda p: hysteresis_position(p.reindex(close.loc[p.index[0]:p.index[-1]].index), **cfg)


def stats(bt, ppy):
    held = bt["held"]
    turnover = held.diff().abs().fillna(held.abs()).sum()
    years = len(bt) / ppy
    return {
        "sharpe_gross": sharpe(bt["gross"], ppy),
        "sharpe_net": sharpe(bt["net"], ppy),
        "turnover_per_year": float(turnover / years),
        "breakeven_bps": float(bt["gross"].sum() / turnover * 1e4) if turnover else np.nan,
        "exposure": float((held != 0).mean()),
        # a unit of position is opened and closed once per 2 units of turnover
        "avg_hold_hours": float(2 * held.abs().sum() / turnover / 12) if turnover else np.nan,
    }


def evaluate(close, target, ppy):
    bt_t = run_backtest(close, target, TAKER)
    bt_m = run_backtest(close, target, MAKER)
    s = stats(bt_m, ppy)
    s["sharpe_net_maker"] = s.pop("sharpe_net")
    s["sharpe_net_taker"] = sharpe(bt_t["net"], ppy)
    return s, bt_t, bt_m


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-log", action="store_true", help="identical re-run: skip all trial logging")
    args = ap.parse_args()
    t = time.time()
    bars = load_bars()
    close = bars["close"]
    X = basic_features(bars)
    labels = triple_barrier(close, H, ewm_vol(close, 288) * np.sqrt(H), pt_mult=1.0, sl_mult=1.0)
    labels = labels.loc[START:END]
    labels = labels[labels.index < pd.Timestamp(END, tz="UTC")]
    X = X.loc[labels.index[0]:]
    u = average_uniqueness(close.index, labels)

    preds01 = pd.read_parquet(P01 / "preds.parquet")["prob_up"]
    assert preds01.index[0] >= SEL_END, "selection segment overlaps p01's OOS"

    # ---- 1. selection on pre-OOS data ------------------------------------
    lab_pre = labels[labels.index < SEL_END]
    u_pre = average_uniqueness(close.index, lab_pre)
    preds_sel = oos_predict(X, lab_pre, PurgedKFold(5, embargo_frac=0.01), weights=u_pre)
    preds_sel.rename("prob_up").rename_axis("t0").to_frame().to_parquet(OUT / "preds_selection.parquet")
    c_pre = close.loc[preds_sel.index[0]:preds_sel.index[-1]]
    ppy = periods_per_year(c_pre.index)
    sel_info = {"sel_labels": len(lab_pre), "sel_effective_n": effective_n(u_pre),
                "sel_start": str(c_pre.index[0]), "sel_end": str(c_pre.index[-1]),
                "sel_years": len(c_pre) / ppy, "sel_auc": oos_auc(preds_sel, lab_pre)}
    print(f"selection segment {sel_info['sel_start']} .. {sel_info['sel_end']} "
          f"({sel_info['sel_years']:.2f}y), labels {len(lab_pre):,}, effective n "
          f"{sel_info['sel_effective_n']:,.0f}, PurgedKFold AUC {sel_info['sel_auc']:.4f}")

    rows, sel_nets = [], []   # grid runs are logged at the end, once everything succeeded
    s, *_ = evaluate(c_pre, signal_to_position(preds_sel, **P01_POS), ppy)
    rows.append({"config": "p01 rule (sign, 0.02, smooth 12)", **s})
    for cfg in GRID:
        s, _, bt_m = evaluate(c_pre, hyst_fn(close, cfg)(preds_sel), ppy)
        rows.append({"config": f"in={cfg['theta_in']} out={cfg['theta_out']} hold={cfg['min_hold']}", **cfg, **s})
        sel_nets.append(("p02_sel " + rows[-1]["config"], bt_m[["net"]], cfg))
    grid = pd.DataFrame(rows).set_index("config")
    best_key = grid.iloc[1:]["sharpe_net_maker"].idxmax()
    best = {k: (int(v) if k == "min_hold" else float(v)) for k, v in grid.loc[best_key, ["theta_in", "theta_out", "min_hold"]].items()}
    cols = ["sharpe_gross", "sharpe_net_maker", "sharpe_net_taker", "turnover_per_year",
            "breakeven_bps", "exposure", "avg_hold_hours"]
    with pd.option_context("display.width", 200, "display.max_rows", 50):
        print(grid[cols].round(3))
    print(f"SELECTED: {best_key}  {best}")

    # ---- 2. OOS: chosen config once, on p01's predictions ----------------
    pos_fn = hyst_fn(close, best)
    oos = {}
    for name, costs in (("taker", TAKER), ("maker", MAKER)):
        print(f"\n=== OOS validation_report, {name} cost ({costs.fee_bps}+{costs.slippage_bps} bps) ===")
        res = validation_report(X, labels, close, SPLITTER, costs=costs, weights=u, position_fn=pos_fn)
        p = res["preds"]
        if not (p.index.equals(preds01.index) and np.array_equal(p.to_numpy(), preds01.to_numpy())):
            raise SystemExit("validation_report's refit predictions differ from p01 preds.parquet: stop")
        oos[name] = res
    c_oos = close.loc[preds01.index[0]:preds01.index[-1]]
    ppy = periods_per_year(c_oos.index)
    p02, bt_t, bt_m = evaluate(c_oos, pos_fn(preds01), ppy)
    p01, *_ = evaluate(c_oos, signal_to_position(preds01, **P01_POS), ppy)
    p01_json = json.loads((P01 / "results.json").read_text())
    assert np.isclose(p01["sharpe_net_taker"], p01_json["sharpe_net"], rtol=0, atol=1e-9), "p01 reference mismatch"
    assert np.isclose(p02["sharpe_net_maker"], oos["maker"]["sharpe_net"], rtol=0, atol=1e-9)
    assert np.isclose(p02["sharpe_net_taker"], oos["taker"]["sharpe_net"], rtol=0, atol=1e-9)

    trials = TrialLog("trials.json")
    if not args.no_log:
        sel_log = TrialLog(str(OUT / "selection_trials.json"))
        for name, net, cfg in sel_nets:
            sel_log.log(name, net, {**cfg, "costs": [MAKER.fee_bps, MAKER.slippage_bps],
                                    "segment": "pre-OOS PurgedKFold(5)"})
        trials.log("p02_hysteresis", bt_m, {
            "base": "p01 config and OOS preds (research/p01_baseline/preds.parquet)",
            "position": "hysteresis_position", **best,
            "selection": "pre-OOS (t0 < 2024-04-07) PurgedKFold(5, 0.01), max net Sharpe at maker cost",
            "costs": [MAKER.fee_bps, MAKER.slippage_bps]})
    summ = {"maker": summarize(bt_m, trials), "taker": summarize(bt_t, trials)}

    out = {
        "selection": {**sel_info, "grid": grid.reset_index().to_dict(orient="records"),
                      "selected": best_key, "selected_params": best},
        "oos_start": str(c_oos.index[0]), "oos_end": str(c_oos.index[-1]),
        "comparison": {"p01": p01, "p02": p02},
        "summary": summ,
        "validation": {k: {kk: vv for kk, vv in r.items() if kk not in ("backtest", "preds")}
                       for k, r in oos.items()},
    }
    (OUT / "results.json").write_text(json.dumps(out, indent=1, default=str))
    print("\n=== OOS comparison (p01 preds, p01 rule vs hysteresis) ===")
    print(pd.DataFrame({"p01": p01, "p02": p02}).round(3))
    for k, s in summ.items():
        print(f"{k}: sharpe_net {s['sharpe_net']:+.3f}  psr {s['psr_vs_0']:.3f}  "
              f"dsr {s.get('dsr', float('nan')):.3f}  n_trials {s.get('n_trials', len(trials))}")
    print(f"({time.time() - t:.0f}s)")
