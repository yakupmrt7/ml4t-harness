"""p03 step 1 (diagnostic, PRE-OOS only, no trial): how fast does the p01/p02
model's edge decay? Spearman IC of (prob_up - 0.5) vs the forward log return
log(close[t+h] / close[t]) for several h, on p02's PurgedKFold selection
predictions. A position decided at the close of t and filled there (delay=1)
earns exactly this forward return.

Forward windows are cut so t+h <= 2024-04-07: no OOS return is read.
s.e. ~ 1/sqrt(N/h): overlapping h-bar windows give ~N/h independent ones.
That is still optimistic when the predictions themselves are persistent.

Run from the repo root:  python research/p03_positioning_features/decay.py
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

OUT = Path(__file__).parent
SEL_END = pd.Timestamp("2024-04-07", tz="UTC")
HORIZONS = (1, 3, 6, 12, 24, 48, 96, 288)
INK, MUTED, GRID, SURFACE, SERIES = "#1f1f1e", "#6b6a64", "#e4e3dd", "#fcfcfb", "#2a78d6"

if __name__ == "__main__":
    close = pd.read_parquet("data/bars/BTCUSDT-5m-2022-08_2026-08.parquet")["close"]
    p = pd.read_parquet("research/p02_positioning/preds_selection.parquet")["prob_up"]
    lc = np.log(close)
    rows = []
    for h in HORIZONS:
        fwd = (lc.shift(-h) - lc).reindex(p.index)
        end = pd.Series(close.index, close.index).shift(-h).reindex(p.index)
        m = fwd.notna() & (end <= SEL_END)
        ic = (p[m] - 0.5).corr(fwd[m], method="spearman")
        n_eff = m.sum() / h
        rows.append({"h_bars": h, "h_hours": h / 12, "ic": ic, "n": int(m.sum()), "n_eff": n_eff,
                     "se": 1 / np.sqrt(n_eff), "t": ic * np.sqrt(n_eff)})
    df = pd.DataFrame(rows).set_index("h_bars")
    (OUT / "decay.json").write_text(json.dumps(df.reset_index().to_dict(orient="records"), indent=1))
    print(df.round(4).to_string())

    fig, ax = plt.subplots(figsize=(7.2, 4.0), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    x = df.index.to_numpy()
    ax.fill_between(x, df["ic"] - 2 * df["se"], df["ic"] + 2 * df["se"], color=SERIES, alpha=0.15, lw=0)
    ax.plot(x, df["ic"], color=SERIES, lw=2, marker="o", ms=5)
    ax.axhline(0, color=MUTED, lw=1)
    ax.set_xscale("log")
    ax.set_xticks(x, [f"{h}\n{h * 5}m" if h < 12 else f"{h}\n{h / 12:g}h" for h in x])
    ax.minorticks_off()
    for h in (1, 12, 288):
        v = df.loc[h, "ic"]
        ax.annotate(f"{v:+.3f}", (h, v), textcoords="offset points", xytext=(0, 9), ha="center",
                    fontsize=9, color=INK)
    ax.set_xlabel("horizon (5-min bars / hours)", color=MUTED, fontsize=9)
    ax.set_ylabel("Spearman IC", color=MUTED, fontsize=9)
    ax.set_title("Signal decay of the p01/p02 model, pre-OOS (shaded: ±2 s.e., n_eff = N/h)",
                 color=INK, fontsize=10, loc="left")
    ax.grid(axis="y", color=GRID, lw=0.8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "decay.png", facecolor=SURFACE)
