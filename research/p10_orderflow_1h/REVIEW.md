# Review: p10_orderflow_1h
**Decision:** ACCEPT WITH FIXES. The KILL is valid and robust. Four claims in RESULTS.md go beyond the evidence and must be reworded (see Blocking). No OOS data was touched.
**One line:** Trade-level flow adds no 1 h directional information beyond p01's kline features. The extra flow columns are mostly regime *levels*: they identify the CV fold with 94% accuracy and make the tree mis-set the base rate. The TCN failed to fit its own inputs, so it says nothing about sequence models. The best configuration is still p01+p02 at 1.3–1.9 bps, and about a sixth of that is net-long beta.

## Verification done by this review (own code, pre-OOS only; every script asserts t0, t1 < 2024-04-07 09:15)
- **Git order.** PLAN 09f4c93 (11:25) → A1 + reducer 991ddf5 (11:28) → features/TCN/selection code 66e1621 (11:46) → validation fails 5bb40b3 (12:00) → A2 9e24337 (12:14) → lightgbm import fix acff131 (17:48) → selection rows 18:21, reevaluate rows 18:22 → results 7ea5a8f (18:23).
  - After 66e1621, the code changed only in the TCN's on-device batching and float32 casts, plus the import order. No feature, label, config or threshold changed.
  - `common.py` mtime 11:45, so the 00:00-minute fix predates the code commit.
  - `trials.json`: 3 entries, and it has no diff since the PLAN, nor has `harness/`.
  - `selection_trials.json` has 16 rows: 8 original + 8 "held".
- **Feature spot-check.** 6 random 5m closes (2023-01..03), 10 features each (imb, msize, big, VPIN, runmean, runmax, lcnt, Kyle λ, rv, intensity at w = 60), recomputed by hand from the raw 1-minute parquet. All match to ≤ 2e-13 relative. The TCN channels `intens` (baseline ending t−1) and `imb` match exactly.
  - Bar close = `px_last` of the minute ending at t on all 6 closes and at 00:00/00:05 across a day boundary.
  - The 5-min flow volume equals bar volume on 5/6 bars. The sixth is off by 0.029 of 5,156 BTC, a boundary spill.
  - Minute-END labelling, the 00:00 day assignment, the intensity baseline shift (`base.shift(w)`: 30 d ending at the window start) and the missing-day mask are correct. All 1,492 days are present, so the mask is moot.
- **Numbers reproduced** from `preds_selection.parquet`: A-basic/P2 breakeven 1.531 bps, and the AUCs.

## Blocking issues (RESULTS.md wording; the KILL itself stands)
1. **TCN reading (Reading 2) overclaims.** "The raw 1-minute flow does not carry enough 1 h directional signal for a small TCN to find" is not supported.
   - The TCN's own window contains p01's strongest feature exactly: ret_48 = 48 bars × 5 min = 240 min = the sum of its `ret1` channel.
   - The unfitted rule −ret_48 alone has weighted AUC **0.527** on the same sample. The TCN reaches **0.510**, and its pooled log-loss is **0.6943**, *worse* than a constant (0.6930).
   - So the TCN failed to fit a linear function of one input channel. That is a failed fit, not a measurement of the flow. Reword to: "the TCN underfit (below a one-feature rule computable from its own input); uninformative about sequence models."
2. **"Validation loss never moved away from ln 2" is presented as evidence of no learning. It is not diagnostic.** The best model (A-basic) improves pooled log-loss over a constant by only **0.0005** (0.69249 vs 0.69299).
   - The TCN's per-fold best val losses (0.6917–0.6930) are inside that range.
   - With ~12 k val labels (~1.2 k effective), early stopping on a 1e-5 improvement is picking epochs on noise.
   - Report AUC and log-loss vs constant instead.
3. **Reading 3, "the only real signal", must disclose its composition.** For A-basic/P2 (held rule):
   - The mean position is **+0.09 long**, while BTC gained +123% (log) over the window. The net-long part is 0.129 of 0.726 gross (18%). **Beta-adjusted breakeven: 1.26 bps**.
   - Long leg +79%, short leg −6.8%.
   - Per fold: **−1.95**, 3.38, 3.55, 1.12, 1.28 bps. Fold 1 (Sep–Dec 2022, the bear leg) loses.
   - Shift-null p = 0.050 is the max over 16 rows, and gross SR 1.20 ± 0.79 is t ≈ 1.5.
   - For the owner: a model that is slightly net long in a strongly rising market earns part of its "timing" P&L just from being long. Only the de-meaned part is skill.
4. **Reading 1 calls the drift hypothesis "not tested". It is now supported. Replace that sentence with these numbers:**
   - An adversarial LightGBM predicting the CV fold id (2-fold CV, 20 k rows, chance 0.20) reaches **0.936 from the flow features** vs 0.416 from the basic features.
   - Share of rank variance explained by fold (η²): msize_240 0.76, runmean_240 0.74, medsize_240 0.61, vpin_240 0.33. The median is 0.080 for flow vs 0.0004 for basic.
   - Mean predicted P(up) in fold 1: A-flow 0.556, A-both 0.556, actual 0.505. In fold 5: 0.527/0.524 vs 0.516. The edge folds are extrapolations in PurgedKFold, and the level features move the model's base rate there.
   - A-flow and A-both log-loss (0.6969, 0.6954) are **worse than a constant**. The dilution is miscalibration by regime, not only noise features.

## Non-blocking issues
- **The flow's directional content was already in p01.** `imb_5` and `taker_imb_1` have identical per-fold IC (to 4 decimals). This is the same quantity, and it also cross-validates the reducer.
  - In market terms: the kline archive already records taker-buy volume. The standard order-flow signal was never new.
  - What p10 actually added was size, runs, VPIN, λ and intensity. Their univariate ICs are ≤ 0.025 (intens_240, lcnt_240, rv_240), the same size as `vol_48`, which p01 already has.
- **reevaluate.py is legitimate but is not exactly p02's rule.** It forward-fills targets computed on the prediction series, so `min_hold` = 24 counts predictions, not bars, and P1's smooth-12 spans gaps.
  - p02-exact (NaN predictions fed through `hysteresis_position` on the full bar grid): **1.86 bps**, turnover ≈ 3,050/yr. The kill is unaffected.
  - Treating the fix as a new selection trial (positions changed), in `selection_trials.json`, with the originals kept, is correct under CLAUDE.md. My 1.86 number is a reviewer diagnostic, not a trial.
  - The fix was motivated by turnover disagreeing with p02 (11,181 vs 5,312), not by the result. The decision is the same either way.
- **`selection.py` overwrites `selection_trials.json`** (`write_text(rows)`). A re-run without `--no-log` would delete the 8 "held" rows. Make it append.
- **TCN inputs are unclipped.** l_hilo max|z| 411 (kurtosis 32,837), ret1 78 (kurtosis 234), intens 62. As a result the predictions range 0.029–0.996.
  - Standardisation uses the fit labels' bar-close rows, not all training minutes as the PLAN says. Immaterial.
  - Label/weight alignment (`wf[perm]`), the window (off −239..0 ending at the t0 minute) and the inner-val purge (t1 < val start) are correct. There is no embargo between fit and val. Minor.
- **The aggTrades archive has prints outside the kline range.** On 2022-09-06 17:11–17:13, prints at 17,597, 19,904 and 28,368 sit against a kline range of 19,068–19,372.
  - 22 pre-OOS 5m bars have an aggTrade high/low > 0.1% outside the kline.
  - A volume-only validation cannot see this. flow_v2 needs a price-range check vs klines. It hits the TCN's l_hilo channel and the notional-based columns (big, VPIN) in those minutes.
- **VPIN completion is stamped at the bucket's last trade.** Completion is only knowable at the next (crossing) trade, so there is a look-ahead of ≤ 1 trade in `vpin_done` and in whether `vpin_5` is NaN. It could only help, the audit is clean, and the effect is negligible. Fix it in any v2.
- **Common sample.** 6.7% of bars are dropped by the pre-registered `vpin_5` NaN rule: 9,542 gaps, median 1 bar, max 52. This is a sample choice driven by a feature definition. Fill it in a v2 (e.g. with the last completed bucket) instead of dropping.
- **Funding is not in the backtests.** With a net-long position in 2023–24, when funding was mostly positive (longs pay), including it lowers the breakeven further.
- **Amendments.**
  - A1 set the data criterion after looking at one day (2023-06-15) of the validation month.
  - A2 relaxed that criterion after it failed on 18/30 days: 1e-9 → 1e-5 volume, count dropped, spills unrestricted.
  - Both are data-integrity gates, not outcome thresholds. Both are diagnosed, owner-accepted, committed before any label or model evaluation, and disclosed. That is acceptable hygiene, and rule 5 is not engaged.
  - The residuals are ≤ 1.05e-6 of volume and an unused count. The off-kline prints above are the part the validation missed.
- **The killed `nohup` run (~5.5 h) is undocumented.** RESULTS should state that it produced no metrics that were seen. `selection.log` holds only the final run.
- **The reversal signal decays monotonically across pre-OOS folds.** ret_12 IC goes −0.086 → −0.051, imb_60 −0.074 → −0.037, and A-basic AUC 0.541 → 0.524. This is relevant to anyone tempted to reuse p01's signal.

## What the evidence supports
- **KILL is valid.** The best row is 1.53 ± 0.87 bps; +2 s.e. = 3.27 is still below the 3.38 maker cost and far from the 4 bps gate.
  - The alternatives all agree: p02-exact positions 1.86, beta-adjusted 1.26, and the first (flat-on-gap) run 0.47.
  - No bug that I could find hides a flow signal. The features match the raw table exactly, and the 1-minute data reproduces the klines.
- **The flow features (size/runs/VPIN/λ/intensity at 5–240 min) add no 1 h direction information in this form.** In raw level form they hurt through regime drift. Effective n = 16,181, pre-OOS 1.60 y, Sharpe s.e. ≈ 0.79.
- **The TCN arm is inconclusive.** It is not a negative result on sequence models; it is a failed fit.
- **The p01 signal is 1 h reversal:** negative IC on ret_6..ret_48 and taker imbalance, the same sign in 5/5 folds. It is decaying over time, and 18% of the best configuration's gross is net-long beta.

## Proposed next experiment
The 1 h / 4 h BTC (and perp) bar-direction line has now failed its kill or cost bar in p02, p03 (2.5 bps ≈ cost), p04, p05 and p10. That is 3+ in a row, so **propose abandoning it.** Before closing it, spend zero OOS trials to turn "feature tweaks won't get there" from an opinion into a number. This one experiment also kills the rank-transformed-flow follow-up, TCN retuning and the Model-C stack at once.

- **Hypothesis:** at H = 12 with P2 on the pre-OOS sample, reaching a 4 bps breakeven needs pooled AUC ≥ 0.58. That is +0.035 over A-basic. No feature addition in p01–p10 has raised AUC at all (p03's positioning features and p10's flow features both lowered it), so no feature experiment on this label can plausibly pass.
- **Exact change vs p10:** no new features and no new model. Build synthetic predictions: logit(p_A-basic) + k·s, where s is a noisy copy of the pre-OOS label sign. Choose k on a grid so that AUC ∈ {0.55, 0.56, …, 0.65}. Run the unchanged P2 rule (p02-exact hold) and cost model, then read off the breakeven-vs-AUC curve, reported with the de-meaned (beta-adjusted) breakeven.
  - Caveat to state: a label-derived signal predicts barrier direction, not magnitude. It is an approximation of what a real feature could deliver.
- **Pre-OOS selection plan:** everything on labels with t0, t1 < 2024-04-07 09:15. There is no selection (a fixed grid of k), and each k is a `measurement` row in `selection_trials.json`.
- **Kill (decided now):** if the AUC needed for 4 bps is ≥ 0.58, abandon 1 h BTC direction for good: no flow v2, no TCN retune, no stack. If it is < 0.56, a flow v2 PLAN, with rank/regime-normalised features, off-kline price filtering and VPIN fixes, is allowed, with its own kill "A-both AUC ≥ A-basic + 0.01 pre-OOS and breakeven ≥ 4 bps". Between 0.56 and 0.58: abandon, unless the owner explicitly funds v2.
- **Expected cost:** 0 OOS trials, `trials.json` unchanged; about 11 measurement rows; minutes of CPU on the saved predictions.
- **Pivot after it:** proceed with the queued p11 (the RTDS settlement check). The reason is market structure: that edge, if any, comes from how the contract settles, not from forecasting direction.
  - Do not reuse p01's signal as an "execution overlay" (timing trades one has to make anyway, where it is worth its ~1.3 bps without paying extra cost). No surviving strategy needs to trade, so there is nothing to overlay.
