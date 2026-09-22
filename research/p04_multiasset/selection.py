"""p04 selection, PRE-OOS ONLY (label t0 and t1 < 2024-04-07). No trial.

Config fixed from p03 (PLAN.md). The only choice made here: whether to add a
one-hot asset id. Rule, fixed in PLAN.md: include it iff it raises the pooled
PurgedKFold AUC by >= 0.002 AND raises the portfolio gross Sharpe.

Then, for the chosen config: pooled AUC, per-asset table, portfolio gross /
net Sharpe, breakeven, correlation of per-asset gross P&L and effective N,
and the KILL CHECK: stop if pooled AUC < 0.52 or portfolio breakeven < 3.5 bps.

Writes selection.json; appends to selection_trials.json (skipped with
--no-log); selection predictions -> preds_selection.parquet.

Run from the repo root:  PYTHONPATH=. python research/p04_multiasset/selection.py [--no-log]
"""
import argparse
import json
import sys
import time

import numpy as np
import pandas as pd

from harness.cv import PurgedKFold
from harness.nulls import feature_lookahead_audit
from harness.pipeline import align, oos_auc, oos_predict
from harness.portfolio import portfolio_stats, run_portfolio_backtest

from common import (GROSS, MAKER, OUT, SEL_END, TAKER, UNIVERSE, add_asset_id, by_asset, correlation_stats,
                    load_all, make_position_fn, per_asset_table, pre_oos)

AUC_MIN, BREAKEVEN_MIN = 0.52, 3.5
ID_AUC_GAIN = 0.002


def log_row(rows, name, params, extra, net):
    from harness.metrics import sharpe
    rows.append({"kind": "model", "name": name, "params": params, **extra,
                 "sr_per_period": sharpe(net), "n": int(len(net)), "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})


def evaluate(X, lab, u, closes, pos_fn):
    p = oos_predict(X, lab, PurgedKFold(5, embargo_frac=0.01), weights=u)
    tg = pos_fn(p)
    res = {"auc": oos_auc(p, lab)}
    bts = {}
    for name, cm in (("gross", GROSS), ("maker", MAKER), ("taker", TAKER)):
        pf, parts = run_portfolio_backtest(closes, tg, cm)
        bts[name] = (pf, parts)
        s = portfolio_stats(pf)
        res[f"sharpe_{name}"] = s["sharpe_net"]
        if name == "gross":
            res.update({k: s[k] for k in ("breakeven_cost_bps", "turnover_per_year", "mean_gross_exposure",
                                          "mean_net_exposure", "years")})
    return p, res, bts


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-log", action="store_true")
    args = ap.parse_args()
    t = time.time()
    closes, X, labels, u, info = load_all()
    X, labels = align(X, labels)
    lab = pre_oos(labels)
    Xp, lab = align(X, lab)
    up = u.reindex(lab.index)
    print(f"pre-OOS pooled labels {len(lab):,}, effective n {up.sum():,.0f} "
          f"(sum over assets), {lab.index.get_level_values(0).min()} .. {lab['t1'].max()}")
    out = {"assets": info, "pre_oos_labels": len(lab), "pre_oos_effective_n": float(up.sum()),
           "pre_oos_effective_n_by_asset": {a: float(x.sum()) for a, x in by_asset(up).items()},
           "sel_end": str(SEL_END)}
    log = []

    # ---- lookahead audit, every asset -------------------------------------
    worst = {}
    for a, xa in by_asset(Xp).items():
        aud = feature_lookahead_audit(xa, closes[a])
        worst[a] = float(aud["ic_next_bar"].abs().max())
        if aud["suspect"].any():
            print(aud.round(4).to_string())
            raise SystemExit(f"lookahead suspects on {a}: stop and investigate")
    out["lookahead_max_abs_ic_next_by_asset"] = worst
    print("lookahead audit: no suspects; max |IC next bar| by asset:",
          {a: round(v, 4) for a, v in worst.items()})

    # ---- asset-id decision --------------------------------------------------
    pos_fn = make_position_fn(closes)
    cand = {}
    for name, Xc in (("no_id", Xp), ("asset_id", add_asset_id(Xp))):
        p, res, bts = evaluate(Xc, lab, up, closes, pos_fn)
        cand[name] = (p, res, bts)
        print(f"{name:9s} " + "  ".join(f"{k} {v:+.4f}" for k, v in res.items()))
        log_row(log, f"pooled {name}", {"features": f"scale_free_basic_features{' + asset one-hot' if name == 'asset_id' else ''}",
                "H": 48, "cv": "PurgedKFold(5, 0.01) pooled", "position": "hysteresis 0.05/0.025/48, risk-scaled",
                "costs": "maker 2+0.5 portfolio"}, res, bts["maker"][0]["net"])
    a0, a1 = cand["no_id"][1], cand["asset_id"][1]
    use_id = bool(a1["auc"] - a0["auc"] >= ID_AUC_GAIN and a1["sharpe_gross"] > a0["sharpe_gross"])
    chosen = "asset_id" if use_id else "no_id"
    out["asset_id_rule"] = f"include iff AUC gain >= {ID_AUC_GAIN} and portfolio gross Sharpe higher"
    out["asset_id_candidates"] = {k: v[1] for k, v in cand.items()}
    out["use_asset_id"] = use_id
    print(f"asset id: AUC gain {a1['auc'] - a0['auc']:+.4f}, gross Sharpe {a0['sharpe_gross']:+.3f} -> "
          f"{a1['sharpe_gross']:+.3f}  => use_asset_id = {use_id}")

    # ---- chosen config: full pre-OOS report --------------------------------
    p, res, bts = cand[chosen]
    p.rename("prob_up").to_frame().to_parquet(OUT / "preds_selection.parquet")
    pa = per_asset_table(p, lab, closes)
    corr = correlation_stats(bts["gross"][1]["gross"], closes)
    single = {a: float(s) for a, s in pa["sharpe_gross"].items()}
    out.update({"chosen": chosen, "portfolio": res, "per_asset": pa.reset_index().to_dict(orient="records"),
                "correlation": corr, "mean_single_asset_gross_sharpe_unscaled": float(np.mean(list(single.values())))})
    pf_g = bts["gross"][0]
    out["long_short_gross_share"] = {
        "long": float(bts["gross"][1]["gross"].where(bts["gross"][1]["held"] > 0, 0).sum().sum() / pf_g["gross"].sum()),
        "short": float(bts["gross"][1]["gross"].where(bts["gross"][1]["held"] < 0, 0).sum().sum() / pf_g["gross"].sum())}

    kill = {"pooled_auc": res["auc"], "auc_min": AUC_MIN, "portfolio_breakeven_bps": res["breakeven_cost_bps"],
            "breakeven_min": BREAKEVEN_MIN}
    kill["killed"] = bool(res["auc"] < AUC_MIN or res["breakeven_cost_bps"] < BREAKEVEN_MIN)
    out["kill_check"] = kill

    print("\nPER ASSET (pre-OOS PurgedKFold, unscaled +-1 hysteresis; net at maker):")
    print(pa.round(3).to_string())
    print("\nPORTFOLIO (pre-OOS, risk-scaled):", json.dumps({k: round(v, 4) for k, v in res.items()}))
    print("CORRELATION:", json.dumps(corr))
    print("LONG/SHORT gross share:", out["long_short_gross_share"])
    print(f"\nKILL CHECK: pooled AUC {res['auc']:.4f} (min {AUC_MIN}), breakeven {res['breakeven_cost_bps']:.2f} bps "
          f"(min {BREAKEVEN_MIN})  =>  {'KILLED: do not run OOS' if kill['killed'] else 'passes'}")

    (OUT / "selection.json").write_text(json.dumps(out, indent=1, default=str))
    if not args.no_log:
        path = OUT / "selection_trials.json"
        prev = json.loads(path.read_text()) if path.exists() else []
        path.write_text(json.dumps(prev + log, indent=1, default=str))
    print(f"({time.time() - t:.0f}s)")
