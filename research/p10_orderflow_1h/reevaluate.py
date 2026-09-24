"""p10 re-evaluation of the saved pre-OOS predictions (no refit): positions HOLD across bars
dropped from the common sample (p02's rule: a bar with no prediction keeps the current position).
selection.py let run_backtest treat those bars as flat, which added a flat-and-back round trip at
every dropped bar (~7% of bars, clustered in quiet periods) and inflated turnover. Same models, same
predictions, same position rules. Appends corrected rows to selection_trials.json (originals kept).

Run from the repo root:  PYTHONPATH=.:research/p10_orderflow_1h python research/p10_orderflow_1h/reevaluate.py
"""
import json
import time

import lightgbm  # noqa: F401  (import order, see selection.py)
import pandas as pd

import selection as S
from common import OUT, load_bars

if __name__ == "__main__":
    close = load_bars()["close"]
    preds = pd.read_parquet(OUT / "preds_selection.parquet")
    sel = json.loads((OUT / "selection.json").read_text())
    table = S.load_cost_table()
    costs = {"maker": S.TableCostModel(table, "BTCUSDT", "maker_all_in_bps"),
             "taker": S.TableCostModel(table, "BTCUSDT", "taker_all_in_bps")}
    orig_positions = S.positions

    def held_positions(p, rule):
        tgt = orig_positions(p, rule)
        grid = close.loc[tgt.index[0]:tgt.index[-1]].index
        return tgt.reindex(grid).ffill()
    S.positions = held_positions
    results, rows = {}, []
    for name in preds.columns:
        p = preds[name].dropna()
        for rule in ("P1", "P2"):
            r = {"model": name, "positions": rule, "auc": sel["results"][f"{name}/{rule}"]["auc"],
                 **S.evaluate(p, close, costs, rule)}
            results[f"{name}/{rule}"] = r
            print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}), flush=True)
            rows.append({"kind": "model", "name": f"p10 {name} {rule} (held across dropped bars)",
                         "params": {"model": name, "positions": rule, "fix": "positions held across dropped bars",
                                    "refit": False}, "auc": r["auc"], "breakeven_bps": r["breakeven_bps"],
                         "breakeven_se_bps": r["breakeven_se_bps"], "sharpe_gross": r["sharpe_gross"],
                         "sharpe_net_maker": r["sharpe_net_maker"], "turnover_per_year": r["turnover_per_year"],
                         "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})
    elig = {k: v for k, v in results.items() if v["auc"] >= S.AUC_MIN}
    best = max(elig, key=lambda k: elig[k]["breakeven_bps"])
    be = elig[best]["breakeven_bps"]
    decision = (f"KILL: best configuration {best} breakeven {be:.2f} < {S.BE_MIN} bps" if be < S.BE_MIN else
                f"GATE: {best}" if elig[best]["breakeven_minus_1se"] >= S.BE_MIN else f"STOP: {best}")
    sel["results_held"], sel["best_held"], sel["decision_held"] = results, best, decision
    (OUT / "selection.json").write_text(json.dumps(sel, indent=1, default=str))
    tr = json.loads((OUT / "selection_trials.json").read_text())
    (OUT / "selection_trials.json").write_text(json.dumps(tr + rows, indent=1, default=str))
    print("DECISION (held):", decision)
