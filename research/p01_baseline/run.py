"""p01 baseline: basic_features -> 1h triple-barrier on BTCUSDT perp 5m bars.

Last 4 years of the archive (2022-09-01 .. 2026-08-31). 2022-08 is loaded
only as warm-up for the 288-bar feature/vol windows; no label starts before
2022-09-01. Config follows the README baseline recipe.

Run from the repo root:  python research/p01_baseline/run.py [--no-log]
--no-log re-runs an identical config without adding a trial to trials.json.
OOS predictions are saved to preds.parquet (gitignored) for later re-evaluation.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from harness.backtest import CostModel, run_backtest, signal_to_position
from harness.cv import WalkForward
from harness.data import load_binance_klines, load_funding
from harness.features import basic_features
from harness.labeling import ewm_vol, triple_barrier
from harness.metrics import TrialLog, periods_per_year, sharpe, summarize
from harness.nulls import validation_report
from harness.weights import average_uniqueness, effective_n

OUT = Path(__file__).parent
START, END = "2022-09-01", "2026-09-01"   # label t0 window [START, END)
H = 12
COSTS = CostModel(fee_bps=5, slippage_bps=0.5)
SPLITTER = WalkForward(n_splits=8, min_train_frac=0.4)
POS = {"mode": "sign", "threshold": 0.02, "smooth": H}


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


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-log", action="store_true", help="identical re-run: skip TrialLog.log")
    args = ap.parse_args()
    t = time.time()
    bars = load_bars()
    close = bars["close"]
    gaps = close.index.to_series().diff().dt.total_seconds().div(300)
    print(f"bars {len(bars):,}  {bars.index[0]} .. {bars.index[-1]}  "
          f"gaps>1 bar: {(gaps > 1).sum()} (missing {int((gaps[gaps > 1] - 1).sum())} bars)")

    X = basic_features(bars)
    labels = triple_barrier(close, H, ewm_vol(close, 288) * np.sqrt(H), pt_mult=1.0, sl_mult=1.0)
    labels = labels.loc[START:END]
    labels = labels[labels.index < pd.Timestamp(END, tz="UTC")]
    X = X.loc[labels.index[0]:]
    u = average_uniqueness(close.index, labels)
    n_eff = effective_n(u)
    print(f"labels {len(labels):,}  effective n {n_eff:,.0f}  "
          f"barriers {labels['barrier'].value_counts(normalize=True).round(3).to_dict()}")

    res = validation_report(X, labels, close, SPLITTER, costs=COSTS, weights=u, pos_kwargs=POS)
    bt = res["backtest"]
    res["preds"].rename("prob_up").rename_axis("t0").to_frame().to_parquet(OUT / "preds.parquet")

    # Perp funding: validation_report ignores it, so rerun the same positions with it.
    funding = load_funding("data/raw/BTCUSDT-fundingRate-*.zip")
    target = signal_to_position(res["preds"], **POS)
    bt_f = run_backtest(close.loc[bt.index[0]:bt.index[-1]], target, COSTS, delay=1, funding=funding)
    ppy = periods_per_year(bt.index)

    trials = TrialLog("trials.json")
    params = {"symbol": "BTCUSDT-perp", "bar": "5m", "window": [START, END], "H": H,
              "labels": "triple_barrier pt=sl=1 width=ewm_vol(288)*sqrt(H)", "features": "basic_features",
              "model": "default_model", "weights": "average_uniqueness",
              "cv": "WalkForward(8, 0.4)", "pos": POS, "costs": [COSTS.fee_bps, COSTS.slippage_bps]}
    if not args.no_log:
        trials.log("baseline_5m_1h", bt, params)
    s = summarize(bt, trials)
    if "dsr" not in s:   # single trial: nothing to deflate against, DSR == PSR
        s["n_trials"], s["dsr"] = len(trials), s["psr_vs_0"]

    out = {k: v for k, v in res.items() if k not in ("backtest", "preds")}
    out.update({
        "n_labels": len(labels), "effective_n": n_eff, "oos_start": str(bt.index[0]),
        "oos_end": str(bt.index[-1]), "summary": s,
        "sharpe_net_with_funding": sharpe(bt_f["net"], ppy),
        "funding_drag_ann": float(bt_f["funding"].mean() * ppy),
        "mean_abs_position": float(bt["held"].abs().mean()),
        "net_long_frac": float(bt["held"].mean()),
    })
    (OUT / "results.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: out[k] for k in ("n_labels", "effective_n", "oos_start", "oos_end",
                                          "sharpe_net_with_funding", "funding_drag_ann",
                                          "mean_abs_position", "net_long_frac")}, indent=1, default=str))
    print(json.dumps(s, indent=1, default=str))
    print(f"({time.time() - t:.0f}s)")
