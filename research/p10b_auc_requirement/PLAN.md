# p10b What AUC would a 1 h BTC direction model need to beat costs?

Written 2026-09-24, before any computation. This is the "Next" in
`research/p10_orderflow_1h/REVIEW.md`, run as written. The owner added one
thing: also report the AUC needed for 3.4 bps (bare maker cost) and 5.5 bps
(taker). Nothing below changes after numbers are seen.

## Hypothesis
At H = 12 with P2 on the pre-OOS sample, a 4 bps breakeven needs pooled
AUC ≥ 0.58 (+0.035 over A-basic).

## Method (no new features, no new model, no selection)
- **Sample:** p10's pre-OOS common sample: 156,943 labels, t0 and t1 <
  2024-04-07 09:15, p01 triple-barrier H = 12.
- **Base predictions:** p10's saved A-basic PurgedKFold predictions
  (`preds_selection.parquet`).
- **Synthetic predictions:** p_k = sigmoid(logit(p_A-basic) + k · s), with
  a noisy copy of the label sign:
  - s = sign(label) + ε, ε ~ N(0, 1), seed 0;
  - label-0 rows get s = ε only.
- **Target AUCs** {0.55, 0.56, …, 0.65}: for each, k is found by bisection,
  so AUC is hit to ±0.0005. AUC is on nonzero labels, as `oos_auc`. The k
  grid is fixed by the targets, so nothing is selected.
- **Positions:** P2 exactly as p02 runs it: `hysteresis_position(θin
  0.05, θout 0, min_hold 24)` applied to the predictions reindexed onto the
  full 5 m bar grid. A bar without a prediction holds, and min_hold counts
  bars.
- **Costs:** the p05 `TableCostModel` (maker all-in) for net Sharpe;
  breakeven is cost-free by definition. Delay 1.
- **Report per target AUC:**
  - gross breakeven (Σ gross / Σ turnover) ± s.e.
    (std(daily gross) · √days / turnover);
  - **de-meaned breakeven**: gross recomputed with held × (ret − mean bar
    return over the sample), which removes the net-long drift;
  - turnover, gross SR, net SR (maker).
- **Required AUC** for 3.4 bps (bare maker), **4.0 bps** (the p10 gate) and
  5.5 bps (taker): linear interpolation of the breakeven-vs-AUC curve, on
  both the plain and the de-meaned breakeven. The **plain** breakeven
  decides the kill, as in p10's gate. The de-meaned one is reported next
  to it.
- **Robustness only, not selection:** the same curve for noise seeds 1
  and 2.
- **Caveat, stated up front:** a label-derived signal predicts barrier
  *direction*, not move size. It approximates what a real feature with
  that AUC could deliver. A real feature might be better or worse on
  magnitude.

## Kill (fixed in the p10 REVIEW; this plan only restates it)
- AUC needed for 4 bps **≥ 0.58**: abandon the 1 h / 4 h BTC bar-direction
  line for good. No flow v2, no TCN retune, no stacking.
- **< 0.56**: a flow v2 PLAN is allowed (rank/regime-normalised features,
  off-kline filtering, VPIN fix), with its own kill: A-both AUC ≥ A-basic
  + 0.01 pre-OOS and breakeven ≥ 4 bps.
- **0.56 – 0.58**: abandon, unless the owner explicitly funds v2.

## Bookkeeping
- 0 OOS trials; `trials.json` untouched.
- One `measurement` row per (target AUC, seed) in
  `research/p10b_auc_requirement/selection_trials.json`.
