"""p04's pre-OOS trade times and directions (input to measure.py).

From research/p04_multiasset/preds_selection.parquet (PurgedKFold, no refit):
the unscaled +-1 hysteresis position per asset; every bar where it changes
is a trade at that bar's close, side = sign of the change, size = |change|
(2 = a flip).

Run from the repo root:  PYTHONPATH=.:research/p04_multiasset python research/p05_costs/make_p04_trade_times.py
"""
import numpy as np
import pandas as pd

from common import OUT, UNIVERSE, load_bars, unit_positions

if __name__ == "__main__":
    closes = {a: load_bars(a)["close"] for a in UNIVERSE}
    p = pd.read_parquet(OUT / "preds_selection.parquet")["prob_up"]
    rows = []
    for a, pos in unit_positions(p, closes).items():
        d = pos.diff().fillna(pos)
        ch = d[d != 0]
        rows.append(pd.DataFrame({"asset": a, "t": ch.index, "side": np.sign(ch.to_numpy()), "size": ch.abs().to_numpy()}))
    df = pd.concat(rows, ignore_index=True)
    df.to_parquet("research/p05_costs/p04_trade_times.parquet")
    print(len(df), df["t"].min(), df["t"].max())
