"""NOT RUN: p04 was killed on pre-OOS (RESULTS.md). Kept as the script that
was prepared for the OOS gate.

p04 OOS: the fixed config (+ the asset-id choice from selection.py, pre-OOS
only), pooled WalkForward(8), run ONCE. Test blocks start exactly at p01's OOS
start (2024-04-07 09:15), so p01-p04 share the OOS period.

portfolio_validation_report at taker and maker cost; one trial
"p04_multiasset_H48" (maker portfolio backtest), DSR with the trial count in
trials.json (4 after logging). Also: per-asset table (BTCUSDT vs p03),
correlation of per-asset gross P&L and effective N, per-fold portfolio
Sharpe, long/short split, funding.

Run from the repo root:  PYTHONPATH=. python research/p04_multiasset/run.py [--no-log]
OOS predictions -> preds.parquet (gitignored).
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from harness.cv import WalkForward
from harness.data import load_funding
from harness.metrics import TrialLog, dsr, periods_per_year, sharpe
from harness.pipeline import align
from harness.portfolio import portfolio_stats, portfolio_validation_report

from common import (MAKER, OOS_START, OUT, TAKER, UNIVERSE, add_asset_id, by_asset, correlation_stats,
                    load_all, make_position_fn, per_asset_table)

N_SPLITS = 8


def funding_charge(held, sym):
    """Funding paid per bar by the held weight (longs pay positive rates), as in
    backtest.run_backtest: the position held INTO the funding time pays."""
    f = load_funding(f"data/raw/{sym}-fundingRate-*.zip").sort_index()
    f = f[(f.index >= held.index[0]) & (f.index <= held.index[-1])]
    pos = np.minimum(held.index.searchsorted(f.index, side="left"), len(held) - 1)
    charge = np.zeros(len(held))
    np.add.at(charge, pos, f.to_numpy())
    return held.to_numpy() * charge


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-log", action="store_true")
    args = ap.parse_args()
    t = time.time()
    sel = json.loads((OUT / "selection.json").read_text())
    closes, X, labels, u, info = load_all()
    if sel["use_asset_id"]:
        X = add_asset_id(X)
    X, labels = align(X, labels)
    t0 = labels.index.get_level_values(0)
    k = int(np.searchsorted(t0, OOS_START))
    splitter = WalkForward(n_splits=N_SPLITS, min_train_frac=(k + 0.5) / len(labels))
    first_test = next(iter(splitter.split(labels["t1"])))[1][0]
    assert t0[first_test] == OOS_START, (t0[first_test], OOS_START)
    print(f"assets {len(UNIVERSE)}, asset id {sel['use_asset_id']}, pooled labels {len(labels):,}, "
          f"effective n {u.reindex(labels.index).sum():,.0f}, OOS from {OOS_START}")

    pos_fn = make_position_fn(closes)
    res = portfolio_validation_report(X, labels, closes, splitter, pos_fn, {"taker": TAKER, "maker": MAKER},
                                      weights=u)
    preds = res["maker"]["preds"]
    preds.rename("prob_up").to_frame().to_parquet(OUT / "preds.parquet")
    pf_m, parts_m = res["maker"]["backtest"], res["maker"]["parts"]
    pf_t = res["taker"]["backtest"]
    ppy = periods_per_year(pf_m.index)

    # per-asset (unscaled +-1, comparable to p03) and BTC vs p03
    pa = per_asset_table(preds, labels, closes)
    p03 = json.loads(Path("research/p03_positioning_features/results.json").read_text())
    btc_vs_p03 = {"p04_BTCUSDT": pa.loc["BTCUSDT"].to_dict(),
                  "p03": {"auc": p03["oos_auc"], "sharpe_gross": p03["stats"]["sharpe_gross"],
                          "sharpe_net_maker": p03["stats"]["sharpe_net_maker"],
                          "breakeven_bps": p03["stats"]["breakeven_bps"],
                          "turnover_per_year": p03["stats"]["turnover_per_year"]}}

    # correlation / effective N on scaled gross P&L
    gross_parts = res["taker"]["parts"]["gross"]   # gross is cost-independent
    corr = correlation_stats(gross_parts, closes)
    scaled_single = {a: sharpe(gross_parts[a].loc[closes[a].index[0]:closes[a].index[-1]], ppy) for a in gross_parts}

    # per fold (WalkForward test blocks), long/short split
    starts = [t0[te[0]] for _, te in splitter.split(labels["t1"])]
    fold = np.searchsorted(np.array(starts), pf_m.index, side="right") - 1
    folds = [{"fold": i + 1, "start": str(pf_m.index[fold == i][0].date()), "end": str(pf_m.index[fold == i][-1].date()),
              "sharpe_gross": sharpe(pf_m["gross"][fold == i], ppy), "sharpe_net_maker": sharpe(pf_m["net"][fold == i], ppy),
              "sharpe_net_taker": sharpe(pf_t["net"][fold == i], ppy),
              "assets_live": int(sum(closes[a].index[-1] >= pf_m.index[fold == i][0] for a in UNIVERSE))}
             for i in range(N_SPLITS)]
    held, g = parts_m["held"], parts_m["gross"]
    long_g, short_g = g.where(held > 0, 0).sum(1), g.where(held < 0, 0).sum(1)
    long_short = {"sharpe_gross_long_leg": sharpe(long_g, ppy), "sharpe_gross_short_leg": sharpe(short_g, ppy),
                  "gross_share_long": float(long_g.sum() / pf_m["gross"].sum()),
                  "mean_net_exposure": float(pf_m["net_exposure"].mean()),
                  "mean_gross_exposure": float(pf_m["gross_exposure"].mean()),
                  "frac_bars_net_long": float((held.sum(1) > 0).mean())}

    fund = np.zeros(len(pf_m))
    for a in UNIVERSE:
        fund += funding_charge(held[a], a)
    funding = {f"sharpe_net_{n}_with_funding": sharpe(pf["net"] - fund, ppy) for n, pf in (("maker", pf_m), ("taker", pf_t))}
    funding["funding_drag_ann"] = float(fund.mean() * ppy)

    trials = TrialLog("trials.json")
    if not args.no_log:
        trials.log("p04_multiasset_H48", pf_m, {
            "universe": UNIVERSE, "features": "scale_free_basic_features (15)" + (" + asset one-hot" if sel["use_asset_id"] else ""),
            "labels": "triple_barrier H=48 pt=sl=1 width=ewm_vol(288)*sqrt(H), per asset", "model": "default_model, pooled",
            "weights": "average_uniqueness per asset", "cv": f"WalkForward({N_SPLITS}) pooled from {OOS_START}",
            "position": "hysteresis 0.05/0.025/48, risk_scale(0.5, cap 3)/15 latched", "costs": [MAKER.fee_bps, MAKER.slippage_bps],
            "selection": "pre-OOS: asset id only (selection.py); everything else fixed from p03"})
    summ = {}
    for name, pf in (("maker", pf_m), ("taker", pf_t)):
        s = portfolio_stats(pf)
        r = pf["net"]
        s["n_trials"] = len(trials)
        s["dsr"] = dsr(sharpe(r), len(r), float(stats.skew(r)), float(stats.kurtosis(r, fisher=False)),
                       len(trials), trials.var_sr()) if len(trials) >= 2 else np.nan
        summ[name] = s

    out = {"use_asset_id": sel["use_asset_id"], "labels": len(labels), "effective_n": float(u.reindex(labels.index).sum()),
           "oos_start": str(pf_m.index[0]), "oos_end": str(pf_m.index[-1]),
           "summary": summ, "per_asset": pa.reset_index().to_dict(orient="records"), "btc_vs_p03": btc_vs_p03,
           "correlation": corr, "scaled_single_asset_gross_sharpe": scaled_single, "folds": folds,
           "long_short": long_short, "funding": funding,
           "validation": {k_: {kk: vv for kk, vv in r_.items() if kk not in ("backtest", "parts", "preds", "stats")}
                          for k_, r_ in res.items()}}
    (OUT / "results.json").write_text(json.dumps(out, indent=1, default=str))
    for k_, s in summ.items():
        print(f"{k_}: sharpe_net {s['sharpe_net']:+.3f}  psr {s['psr_vs_0']:.3f}  dsr {s['dsr']:.3f}  n_trials {s['n_trials']}")
    print("\n=== per asset (unscaled +-1, maker) ===\n" + pa.round(3).to_string())
    print("\n=== BTCUSDT vs p03 ===\n" + json.dumps(btc_vs_p03, indent=1, default=str))
    print("\n=== correlation / effective N ===\n" + json.dumps(corr, indent=1))
    print("\n=== folds ===\n" + pd.DataFrame(folds).round(3).to_string(index=False))
    print("\n=== long/short ===\n" + json.dumps(long_short, indent=1))
    print("\n=== funding ===\n" + json.dumps(funding, indent=1))
    print(f"({time.time() - t:.0f}s)")
