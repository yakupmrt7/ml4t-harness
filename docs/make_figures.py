"""Build every figure in the README from committed result files only (no data download needed).

    python docs/make_figures.py        -> docs/figures/*.png

Where a number exists only in a RESULTS.md table (not in a JSON), it is transcribed here with the
file it comes from, so every point on every chart can be traced back.
"""
import json
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
R = ROOT / "research"
OUT = ROOT / "docs" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

# validated categorical palette (light surface), slots in fixed order
EDGE, COST, AQUA, YELLOW, VIOLET = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#4a3aa7"
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e0", "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": MUTED, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "axes.titleweight": "bold",
    "axes.titlesize": 12, "axes.titlelocation": "left", "font.size": 10, "legend.frameon": False,
    "lines.linewidth": 2, "figure.dpi": 110, "savefig.dpi": 160, "savefig.bbox": "tight",
})


def load(p):
    return json.load(open(R / p))


def save(fig, name):
    fig.savefig(OUT / name)
    plt.close(fig)
    print("wrote", OUT / name)


# ------------------------------------------------------------------ 1. edge vs cost, every experiment
def fig_edge_vs_cost():
    # (label, breakeven bps per unit traded, s.e. or None, cost bps per unit traded, cost label, source)
    rows = [
        ("p01  1h LightGBM, BTC (OOS)", 0.68, None, 3.38, "maker", "p01/RESULTS.md; cost p05"),
        ("p02  + hysteresis (OOS)", 1.07, None, 3.38, "maker", "p02/RESULTS.md"),
        ("p03  4h + positioning data (OOS)", 2.50, None, 3.38, "maker", "p03/RESULTS.md"),
        ("p04  15 perps, pooled (pre-OOS)", 2.51, None, 3.5, "kill line", "p04/RESULTS.md"),
        ("p06  daily basis-change sort", 4.7, 2.9, 9.0, "taker $10k", "p06/RESULTS.md"),
        ("p06  daily momentum sort", 21.0, 17.1, 8.8, "taker $10k", "p06/RESULTS.md"),
        ("p07b momentum, point-in-time universe", 20.7, 14.5, 12.0, "flat 12", "p07b/RESULTS.md"),
        ("p10  + 44 order-flow features, best", 1.53, 0.87, 3.38, "maker", "p10/RESULTS.md"),
        ("p11  + 26 external features, best", 2.85, 0.96, 3.38, "maker", "p11/RESULTS.md"),
    ]
    p13 = load("p13_hl_liquidation_history/step2.json")["all"]
    lo, hi = p13["rev300_ci"]
    rows.append(("p13  fade HL liquidations, 300 s", p13["rev300_p50"] / 2, (hi - lo) / 4,
                 p13["cost10k_rt_p50"] / 2, "taker $10k", "p13/step2.json (round trip / 2)"))
    rows = rows[::-1]
    fig, ax = plt.subplots(figsize=(9, 5.6))
    y = np.arange(len(rows))
    for i, (lab, be, se, cost, _, _) in enumerate(rows):
        ax.plot([cost, cost], [i - 0.32, i + 0.32], color=COST, lw=3, solid_capstyle="round", zorder=2)
        if se:
            ax.plot([be - se, be + se], [i, i], color=EDGE, lw=1.5, alpha=0.55, zorder=3)
        ax.plot(be, i, "o", ms=8, color=EDGE, mec=SURFACE, mew=2, zorder=4)
    ax.set_yticks(y, [r[0] for r in rows])
    ax.set_xlim(-2, 40)
    ax.set_xlabel("bps per unit of notional traded")
    ax.grid(axis="y", visible=False)
    ax.plot([], [], "o", color=EDGE, label="edge: breakeven cost (± 1 s.e. where measured)")
    ax.plot([], [], color=COST, lw=3, label="cost it has to beat (measured, per experiment)")
    ax.legend(loc="lower right")
    ax.annotate("same book on a hindsight universe (p07):\n125 ± 35 bps. Survivorship, removed in p07b",
                xy=(39.5, 3.55), ha="right", va="center", fontsize=8.5, color=INK2)
    ax.set_title("Every line of research: the edge never cleared its cost")
    save(fig, "edge_vs_cost.png")


# ------------------------------------------------------------------ 2. IC decay (p03 step 1)
def fig_ic_decay():
    d = pd.DataFrame(load("p03_positioning_features/decay.json"))
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    ax.fill_between(d.h_hours, d.ic - 2 * d.se, d.ic + 2 * d.se, color=EDGE, alpha=0.15, lw=0)
    ax.plot(d.h_hours, d.ic, "-o", color=EDGE, ms=6, mec=SURFACE, mew=1.5)
    ax.axhline(0, color=MUTED, lw=1)
    ax.set_xscale("log")
    ax.set_xticks(d.h_hours, ["5m", "15m", "30m", "1h", "2h", "4h", "8h", "24h"])
    ax.minorticks_off()
    ax.set_ylabel("Spearman IC (prediction vs forward return)")
    ax.set_xlabel("forward horizon")
    ax.set_title("p03: the 1h model's information builds for an hour and is gone by a day")
    save(fig, "ic_decay.png")


# ------------------------------------------------------------------ 3. positioning grid (p02)
def fig_p02_grid():
    g = pd.DataFrame(load("p02_positioning/results.json")["selection"]["grid"])
    sel = g.config.str.contains("in=0.05 out=0.0 hold=24")
    ref = g.config.str.startswith("p01")
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    ax.scatter(g.turnover_per_year[~sel & ~ref], g.breakeven_bps[~sel & ~ref], s=40, color=EDGE, alpha=0.75,
               edgecolor=SURFACE, lw=1.5, label="32 hysteresis configs (pre-OOS)")
    ax.scatter(g.turnover_per_year[ref], g.breakeven_bps[ref], s=70, marker="s", color=MUTED,
               edgecolor=SURFACE, lw=1.5, label="p01's rule (reference)")
    ax.scatter(g.turnover_per_year[sel], g.breakeven_bps[sel], s=110, marker="D", color=VIOLET,
               edgecolor=SURFACE, lw=1.5, label="selected")
    ax.axhline(2.5, color=COST, lw=2)
    ax.text(23000, 2.62, "modelled maker cost 2.5 bps", color=COST, ha="right", fontsize=9)
    ax.set_xlabel("turnover (× notional per year)")
    ax.set_ylabel("breakeven (bps per unit traded)")
    ax.set_ylim(-0.6, 3.0)
    ax.legend(loc="lower right")
    ax.set_title("p02: no way of turning the predictions into positions reaches cost")
    save(fig, "p02_positioning_grid.png")


# ------------------------------------------------------------------ 4. per-asset edge vs measured cost (p05)
def fig_p05():
    # p05/RESULTS.md decision table: asset, maker all-in (T=5) ± se, p04 breakeven ± se, taker all-in
    t = [("BTC", 3.38, .30, 0.34, 1.64, 5.02), ("ETH", 2.86, .36, 0.62, 1.96, 5.03), ("BNB", 4.18, .56, 1.96, 1.84, 5.19),
         ("ETC", 2.62, .45, 5.81, 2.68, 5.29), ("SOL", 2.72, .43, 5.16, 3.86, 5.42), ("OP", 3.18, .54, 6.32, 3.84, 5.37),
         ("AVAX", 4.88, 1.24, 4.94, 2.88, 5.70), ("MATIC", 3.88, .62, 4.08, 2.70, 5.71), ("DOT", 4.19, .62, 3.01, 2.38, 5.95),
         ("UNFI", 3.99, 1.48, 3.41, 4.13, 6.09), ("SAND", 4.17, .61, 5.97, 2.89, 6.05), ("XRP", 2.97, .40, 2.82, 2.43, 6.10),
         ("ADA", 4.47, .74, 5.12, 2.41, 6.41), ("GMT", 6.68, 1.41, 1.80, 3.41, 6.81), ("APE", 4.79, .77, 6.16, 3.19, 7.03)]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    x = np.arange(len(t))
    for i, (a, mk, mks, be, bes, tk) in enumerate(t):
        ax.plot([i - .3, i + .3], [mk, mk], color=COST, lw=3, solid_capstyle="round")
        ax.plot([i, i], [be - bes, be + bes], color=EDGE, lw=1.5, alpha=.55)
        ax.plot(i, be, "o", color=EDGE, ms=7, mec=SURFACE, mew=1.5)
    ax.set_xticks(x, [r[0] for r in t])
    ax.grid(axis="x", visible=False)
    ax.plot([], [], "o", color=EDGE, label="p04 pre-OOS breakeven ± 1 s.e.")
    ax.plot([], [], color=COST, lw=3, label="measured maker all-in cost (fills + missed fills)")
    ax.legend(loc="upper left", ncols=2)
    ax.set_ylabel("bps per unit traded")
    ax.set_ylim(-2, 11)
    ax.set_title("p05: once costs are measured, no asset's edge is distinguishable from its cost")
    save(fig, "p05_edge_vs_measured_cost.png")


# ------------------------------------------------------------------ 5. survivorship (p07 vs p07b)
def fig_survivorship():
    periods = ["2020-Q4", "2021", "2022 H1", "2022-08→12", "2023", "2024-Q1"]
    hind = [5.69, 3.38, 0.26, 0.24, 2.07, -2.89]      # p07/RESULTS.md (the last three = p06's window, same book)
    pit = [3.96, 0.32, -0.80, 0.24, 2.07, -2.89]      # p07b/RESULTS.md
    fig, ax = plt.subplots(figsize=(8.5, 3.9))
    x = np.arange(len(periods)); w = 0.38
    ax.bar(x - w / 2 - .01, hind, w, color=MUTED, label="universe picked with hindsight (p07)", lw=0, zorder=2)
    ax.bar(x + w / 2 + .01, pit, w, color=EDGE, label="point-in-time universe (p07b)", lw=0, zorder=2)
    ax.axhline(0, color=INK2, lw=1)
    ax.axvspan(2.5, 5.5, color=GRID, alpha=.5, lw=0, zorder=-1)
    ax.text(4, 5.4, "p06's window: identical universe", ha="center", fontsize=9, color=INK2)
    ax.text(1, 5.4, "replication window", ha="center", fontsize=9, color=INK2)
    ax.set_xticks(x, periods)
    ax.grid(axis="x", visible=False)
    ax.set_ylabel("gross Sharpe (annualised)")
    ax.legend(loc="lower left")
    ax.set_title("p07 vs p07b: a hindsight universe was worth ~2 Sharpe (pooled t 3.72 → 1.43)")
    save(fig, "survivorship.png")


# ------------------------------------------------------------------ 6. required AUC (p10b)
def fig_required_auc():
    d = load("p10b_auc_requirement/results.json")
    fig, ax = plt.subplots(figsize=(8, 4.4))
    for key, color, lab in (("curves", EDGE, "direction-only signal (decides the kill)"),
                            ("curves_magnitude", AQUA, "magnitude-weighted signal (reported)")):
        for j, seed in enumerate(("seed0", "seed1", "seed2")):
            pts = pd.DataFrame(d[key][seed]["points"])
            ax.plot(pts.auc, pts.breakeven_bps, color=color, alpha=1 if j == 0 else .45, lw=2 if j == 0 else 1.2,
                    label=lab if j == 0 else None)
    for lvl, lab in ((3.4, "maker cost 3.4"), (4.0, "gate 4.0"), (5.5, "taker 5.5")):
        ax.axhline(lvl, color=COST, lw=1.5, alpha=.9 if lvl == 4.0 else .55)
        ax.text(0.5465, lvl + (0.12 if lvl != 3.4 else -0.42), lab, color=COST, ha="left", fontsize=9)
    ax.axvline(d["base_auc"], color=INK2, lw=1.2, ls="--")
    ax.text(d["base_auc"] + .0015, 9.3, f"best real model\nAUC {d['base_auc']:.4f}", fontsize=9, color=INK2)
    ax.axvspan(0.559, 0.591, color=EDGE, alpha=.08, lw=0)
    ax.set_xlabel("AUC of a synthetic model (the real one + a planted signal)")
    ax.set_ylabel("breakeven (bps per unit traded)")
    ax.legend(loc="upper left")
    ax.set_title("p10b: a 4 bps breakeven needs AUC 0.56–0.59; four years of features reached 0.545")
    save(fig, "required_auc.png")


# ------------------------------------------------------------------ 7. why raw levels fail (p03 + p11)
def fig_regime_features():
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.8), gridspec_kw={"width_ratios": [1.25, 1]})
    groups = ["basic (15)", "positioning (25)"]            # p03/RESULTS.md feature importance
    gain, drop = [29.5, 70.5], [0.0207, 0.0030]
    x = np.arange(2); w = .38
    a1.bar(x - w / 2 - .01, gain, w, color=MUTED, edgecolor=SURFACE, lw=2, label="share of LightGBM gain (%)")
    a1.bar(x + w / 2 + .01, [v * 1000 for v in drop], w, color=EDGE, edgecolor=SURFACE, lw=2,
           label="OOS AUC lost when shuffled (× 1000)")
    for i in range(2):
        a1.text(i - w / 2, gain[i] + 1.5, f"{gain[i]:.0f}%", ha="center", fontsize=9, color=INK2)
        a1.text(i + w / 2, drop[i] * 1000 + 1.5, f"{drop[i]:.3f}", ha="center", fontsize=9, color=INK2)
    a1.set_xticks(x, groups); a1.grid(axis="x", visible=False); a1.set_ylim(0, 85)
    a1.legend(loc="upper left", fontsize=8.5)
    a1.set_title("p03: trees split on slow levels, which don't generalise", fontsize=10.5)
    labs = ["basic features", "external raw levels"]     # p11/RESULTS.md adversarial fold-id test
    acc = [0.47, 0.998]
    a2.bar([0, 1], acc, .55, color=[EDGE, COST], edgecolor=SURFACE, lw=2)
    a2.axhline(0.2, color=INK2, lw=1, ls="--"); a2.text(1.45, 0.215, "chance (5 folds)", ha="right", fontsize=8.5, color=INK2)
    for i, v in enumerate(acc):
        a2.text(i, v + 0.02, f"{v:.1%}", ha="center", fontsize=9.5, color=INK)
    a2.set_xticks([0, 1], labs); a2.set_ylim(0, 1.1); a2.grid(axis="x", visible=False)
    a2.set_ylabel("accuracy predicting the CV fold id")
    a2.set_title("p11: the features encode *when*, not *what next*", fontsize=10.5)
    fig.suptitle("Why raw-level features fail: the model learns the regime, then mispredicts the base rate",
                 x=0.01, ha="left", fontweight="bold", fontsize=12)
    fig.tight_layout()
    save(fig, "regime_features.png")


# ------------------------------------------------------------------ 10. p15-p19: each result vs its pre-registered bar
def fig_later_lines():
    """One panel per experiment, in its own unit (no shared axis): measured value with its interval (blue) and the
    pre-registered bar (orange). Sources: the committed JSON of each experiment."""
    p15 = load("p15_pm_deribit_threshold/step1.json")["kill_C"]
    p16 = load("p16_deribit_vrp/step1.json")["main"]["tail"]
    p17 = load("p17_pm_maker_bound/descriptive.json")["fee_0.07"]
    p18 = load("p18_carry_on_capital/results.json")["C"]
    p19 = load("p19_btc_carry_holdout/holdout.json")
    s17 = p17["bound_c_equal_weight"] / p17["t_iid_by_market"]
    panels = [
        ("p15  Polymarket − Deribit gap,\nlongshots (pp, median, 95% CI)", p15["D_median_pp"], tuple(p15["ci"]),
         2.0, "bar ≥ 2 pp", "higher needed"),
        ("p16  short-vol week: worst week\n÷ mean week (×)", p16["worst_over_mean"], None, 12.0, "bar ≤ 12×",
         "lower needed"),
        ("p17  maker P&L, verified fee\n(¢/share, ± 2 s.e.)", p17["bound_c_equal_weight"],
         (p17["bound_c_equal_weight"] - 2 * s17, p17["bound_c_equal_weight"] + 2 * s17), 0.0, "bar: interval > 0",
         "higher needed"),
        ("p18  carry, perfect timing, 2025\n(%/yr on capital, ± 2 s.e.)", p18["ann_on_capital_%"],
         (p18["ann_on_capital_%"] - 2 * p18["nw_se_%"], p18["ann_on_capital_%"] + 2 * p18["nw_se_%"]), 6.0,
         "bar ≥ 6%", "higher needed"),
        ("p19  BTC carry, HOLDOUT 2026\n(%/yr on capital, ± 2 s.e.)", p19["ann_on_capital_%"],
         (p19["ann_on_capital_%"] - 2 * p19["nw_se_%"], p19["ann_on_capital_%"] + 2 * p19["nw_se_%"]), 6.0,
         "bar ≥ 6%", "higher needed"),
    ]
    fig, axes = plt.subplots(1, 5, figsize=(13, 3.1))
    for ax, (title, v, ci, bar, blab, direction) in zip(axes, panels):
        lo, hi = ci if ci else (v, v)
        span = max(hi, bar, v) - min(lo, bar, v, 0)
        ax.axvline(bar, color=COST, lw=3, solid_capstyle="round", zorder=2)
        if ci:
            ax.plot([lo, hi], [0, 0], color=EDGE, lw=2, alpha=0.6, solid_capstyle="round", zorder=3)
        ax.plot(v, 0, "o", ms=9, color=EDGE, mec=SURFACE, mew=2, zorder=4)
        ax.set_xlim(min(lo, bar, v, 0) - 0.25 * span, max(hi, bar, v) + 0.25 * span)
        ax.set_ylim(-1, 1)
        ax.set_yticks([])
        ax.grid(axis="y", visible=False)
        ax.spines["left"].set_visible(False)
        ax.set_title(title, fontsize=9.5)
        ax.annotate(f"{v:.2f}", (v, 0), xytext=(0, 12), textcoords="offset points", ha="center", fontsize=9,
                    color=INK, bbox=dict(boxstyle="round,pad=0.15", fc=SURFACE, ec="none"), zorder=6)
        ax.annotate(f"{blab}\n({direction})", (bar, -0.9), xytext=(4, 0), textcoords="offset points", ha="left",
                    va="bottom", fontsize=8, color=INK2)
    fig.suptitle("After the direction line: every result against the bar it had to clear (blue = measured, "
                 "orange = pre-registered bar)", x=0.01, ha="left", fontsize=11, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    save(fig, "later_lines_vs_bar.png")


# ------------------------------------------------------------------ 11. p19: the carry decayed year by year
def fig_p19_decay():
    dev = load("p19_btc_carry_holdout/dev_reference.json")
    ho = load("p19_btc_carry_holdout/holdout.json")
    tbill = 3.67        # FRED DTB3 mean over 2026-01-12..09-27, p19 RESULTS.md (final review)
    rows = [("2024 (dev)", dev["2024"]), ("2025 (dev)", dev["2025"]), ("2026 holdout\n(one look)", ho)]
    fig, ax = plt.subplots(figsize=(7.5, 4))
    x = np.arange(len(rows))
    for i, (lab, r) in enumerate(rows):
        v, se = r["ann_on_capital_%"], r["nw_se_%"]
        ax.bar(i, v, width=0.55, color=EDGE, zorder=3)
        ax.plot([i, i], [v - 2 * se, v + 2 * se], color=INK2, lw=1.5, zorder=4)
        ax.annotate(f"{v:.1f}%", (i + 0.3, v), xytext=(4, 0), textcoords="offset points", ha="left",
                    va="center", fontsize=10, color=INK)
    ax.axhline(6.0, color=COST, lw=2.5, zorder=5, label="pre-registered bar, 6%/yr")
    ax.axhline(tbill, color=MUTED, lw=1.5, ls=(0, (4, 3)), zorder=5,
               label=f"3-month T-bill over the holdout, {tbill}%")
    ax.legend(loc="upper right", fontsize=9)
    ax.set_xlim(-0.5, 2.75)
    ax.set_ylim(0, 27)
    ax.set_xticks(x, [r[0] for r in rows])
    ax.set_ylabel("%/yr on capital (± 2 Newey–West s.e.)")
    ax.grid(axis="x", visible=False)
    ax.set_title("p19: BTC funding carry (short HL perp / long Binance spot) decayed below its bar")
    save(fig, "p19_carry_decay.png")


# ------------------------------------------------------------------ 8. p13 price path around a liquidation
def fig_p13_path():
    d = pd.read_csv(R / "p13_hl_liquidation_history" / "event_path.csv")
    cost = load("p13_hl_liquidation_history/step2.json")["all"]["cost10k_rt_p50"]
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    a = d[d.group == "all"]
    t = d[d.group == "top_known_decile"]
    ax.fill_between(a.second, a.p25_bps, a.p75_bps, color=EDGE, alpha=.12, lw=0, label="all events, interquartile range")
    ax.plot(a.second, a.median_bps, color=EDGE, label="all events, median (39,079 windows)")
    ax.plot(t.second, t.median_bps, color=VIOLET, lw=1.6, label="largest decile by size known at entry, median")
    ax.axvline(0, color=INK2, lw=1)
    ax.axvline(2, color=INK2, lw=1, ls=":")
    ax.text(3, -24, "entry\n(t0 + 2 s)", fontsize=8.5, color=INK2)
    ax.text(-58, 6, "first liquidation\nprints at t0 →", fontsize=8.5, color=INK2)
    ax.plot([2, 300], [-cost, -cost], color=COST, lw=2, ls="--")
    ax.text(298, -cost - 1.6, f"a fade pays only below this line: back ≥ {cost:.1f} bps (round-trip cost)",
            ha="right", fontsize=8.5, color=COST)
    ax.set_xlim(-60, 300)
    ax.set_xlabel("seconds from the first liquidation in the cluster")
    ax.set_ylabel("price move in the liquidation's direction (bps)")
    ax.legend(loc="lower right", fontsize=8.5)
    ax.set_title("p13: the move happens before the liquidation; afterwards the price just stops")
    save(fig, "p13_event_path.png")


# ------------------------------------------------------------------ 9. p13 size deciles: look-ahead vs causal
def fig_p13_deciles():
    reg = load("p13_hl_liquidation_history/step2.json")["deciles"]
    cau = load("p13_hl_liquidation_history/causal_size.json")["deciles_known_at_entry"]
    fig, ax = plt.subplots(figsize=(8.5, 4))
    x = np.arange(10)
    ax.plot(x, [d["rev300_p50"] for d in reg], "-o", color=MUTED, ms=6, mec=SURFACE, mew=1.5,
            label="size = whole cluster (registered; includes liquidations after entry)")
    ax.plot(x, [d["rev300"] for d in cau], "-o", color=EDGE, ms=7, mec=SURFACE, mew=1.5,
            label="size = what is known at entry (causal)")
    ax.plot(x, [d["cost"] for d in cau], color=COST, lw=2, label="round-trip cost, $10k taker")
    ax.axhline(0, color=INK2, lw=1)
    ax.set_xticks(x, [f"D{i + 1}" for i in x])
    ax.grid(axis="x", visible=False)
    ax.set_xlabel("decile of liquidated notional (small → large)")
    ax.set_ylabel("median reversion at 300 s (bps)")
    ax.legend(loc="lower left", fontsize=8.5)
    ax.set_title("p13: the 'large liquidations continue' pattern was look-ahead")
    save(fig, "p13_size_deciles.png")


if __name__ == "__main__":
    for f in (fig_edge_vs_cost, fig_ic_decay, fig_p02_grid, fig_p05, fig_survivorship, fig_required_auc,
              fig_regime_features, fig_p13_path, fig_p13_deciles, fig_later_lines, fig_p19_decay):
        f()
