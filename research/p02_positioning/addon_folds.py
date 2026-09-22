"""p02 add-on (reporting only, no trial, no refit): gross Sharpe per
WalkForward fold and the long vs short gross P&L split, from p01's saved OOS
predictions and p02's selected hysteresis params.

Run from the repo root:  python research/p02_positioning/addon_folds.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from harness.backtest import CostModel, hysteresis_position, run_backtest
from harness.metrics import periods_per_year, sharpe

OUT = Path(__file__).parent
N_SPLITS = 8   # p01's WalkForward(8, 0.4)

if __name__ == "__main__":
    r = json.loads((OUT / "results.json").read_text())
    cfg = r["selection"]["selected_params"]
    close = pd.read_parquet("data/bars/BTCUSDT-5m-2022-08_2026-08.parquet")["close"]
    preds = pd.read_parquet("research/p01_baseline/preds.parquet")["prob_up"]
    c = close.loc[preds.index[0]:preds.index[-1]]
    target = hysteresis_position(preds.reindex(c.index), **cfg)
    bt = run_backtest(c, target, CostModel(2, 0.5))
    ppy = periods_per_year(c.index)
    sr = sharpe(bt["gross"], ppy)
    assert np.isclose(sr, r["comparison"]["p02"]["sharpe_gross"], rtol=0, atol=1e-9), "does not reproduce p02"

    # oos_predict fills WalkForward test positions pos[start:] of the aligned
    # label index, split N_SPLITS ways, so the fold blocks are exactly these:
    starts = [b[0] for b in np.array_split(preds.index, N_SPLITS)]
    fold = np.searchsorted(np.array(starts), bt.index, side="right") - 1
    rows = []
    for k in range(N_SPLITS):
        b = bt[fold == k]
        rows.append({"fold": k + 1, "start": str(b.index[0].date()), "end": str(b.index[-1].date()),
                     "days": round(len(b) / 288, 1), "sharpe_gross": sharpe(b["gross"], ppy),
                     "sharpe_net_maker": sharpe(b["net"], ppy), "exposure": float((b["held"] != 0).mean()),
                     "btc_return": float(c.loc[b.index[-1]] / c.loc[b.index[0]] - 1)})
    folds = pd.DataFrame(rows).set_index("fold")

    long_, short_ = bt["held"] > 0, bt["held"] < 0
    years = len(bt) / ppy
    split = {
        leg: {"bars_frac": float(m.mean()), "gross_sum": float(bt.loc[m, "gross"].sum()),
              "gross_ann": float(bt.loc[m, "gross"].sum() / years),
              "hit_rate": float((bt.loc[m, "gross"] > 0).mean())}
        for leg, m in (("long", long_), ("short", short_))
    }
    split["total"] = {"gross_sum": float(bt["gross"].sum()), "gross_ann": float(bt["gross"].sum() / years)}
    split["btc_buy_hold"] = float(c.iloc[-1] / c.iloc[0] - 1)
    out = {"sharpe_gross_check": sr, "folds": folds.reset_index().to_dict(orient="records"), "long_short": split}
    (OUT / "addon_folds.json").write_text(json.dumps(out, indent=1))
    print(folds.round(3).to_string())
    print(json.dumps(split, indent=1))
