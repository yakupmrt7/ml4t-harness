# Review: p15_pm_deribit_threshold
**Decision:** ACCEPT WITH FIXES (the kill stands; the fixes are wording and reproducibility in RESULTS.md)
**One line:** In 2025, Polymarket BTC terminal threshold and range prices sit within about 1 pp of the Deribit risk-neutral probability, and within about 0.5 pp of realised outcomes for longshots. I found no pipeline error that shrinks the gap, so KILL C is sound. The sample is effectively 2025 only, not "2023–2025".

## What I checked, and how
- **Git order.** Commits ran in this order: PLAN (baf4903), step 0 and amendment 1 (f66d9c9), split (f8a8832), then step 1/2 code (7cbd757) before any price, then amendment 2 (150bb9a, 10:40) and the step 1 run (log about 10:50). The only change to `step1.py` after 7cbd757 is a dtype fix in the `searchsorted` for the causal basis, with the same semantics. `harness/` has not changed since 2026-09-22. `test_surface.py` passes 7/7. `trials_pm.json` and `selection_trials.json` are both absent, which is correct because nothing reached a rule or the holdout.
- **Reproduction.** I rebuilt P_RN from `step1.prob_event` for 300 random low-bucket main rows. The maximum difference from the panel is 0.00 pp.
- **Independent P_RN** on the same 300 rows. It changes three things at once:
  - Deribit's own trade `iv` instead of mark inversion;
  - a piecewise-linear smile instead of the vega-weighted quadratic;
  - a forward from per-strike parity under the other inverse convention (USD = BTC price × index).

  Result: independent − panel = **−0.06 pp median** (mean +0.06, IQR −1.06/+0.91). The median D on those rows is 0.78 pp with the panel's P_RN and 1.05 pp with the independent one. So the P_RN noise is about ±1 pp per row with no sign. Hand spot-checks of 4 rows differed by −3.1, −1.0, +1.5 and +3.9 pp. That scatter is two-sided, and it comes from thin one-hour windows and a large forward sensitivity for narrow near-expiry range buckets (0.4% of F is half the width of a $1k bucket).
- **Definitions, each checked in code:**
  - **YES mapping.** o0 → p, o1 → 1 − q. Within the same market-hour, p_yes from outcome-0 trades minus p_yes from outcome-1 trades is +0.5 ¢ median (IQR 0 / 1.5 ¢; 95% of hours within 5 ¢). That is the bid-ask, not a flip. PM's Brier of 0.1426 would be impossible with a flipped mapping.
  - **Strike basis.** K_D = K(1+b) with b = index/Binance − 1. The direction is correct: S_Binance > K ⇔ S_index > K(1+b).
  - **Digital.** −dC/dK through the smile, with C = F·c_fwd, includes the skew term.
  - **Maturity interpolation.** w is linear in τ at fixed k, and ln(F/index) is linear in τ.
  - **Range mapping.** below = 1 − P(K_hi), above = P(K_lo), between = difference. Correct.
  - **Ties.** Immaterial for a continuous distribution. Settlement uses the candle opening at T, rebuilt with 100% agreement.
  - **Windows.** PM uses `ceil('h')`, i.e. (t−60, t]. Deribit uses (t−60, t]. They are aligned.
- **Two biases that do work against the kill, both below 0.2 pp:**
  - If Deribit divides USD by the index rather than F, the mark-convention error is second order: F/index − 1 is 1–9 bp here.
  - Marks up to 60 min old are treated as if they had the τ of time t. That overstates total variance by about 2% for 1-day tenors, which inflates a 5% OTM digital by about 0.15 pp and so lowers D by at most about 0.2 pp.
- **Biases that work for the hypothesis, i.e. make the measured gap larger:**
  - **Bucketing on noisy P_RN.** Regression to the mean pushes the low bucket's D up. Bucketing on PM < 15% instead gives a median D of **0.53 pp [0.42, 0.63]**.
  - **VWAP includes taker buys at the ask.** A YES seller receives the bid, which is lower.
  - **PM averages over the hour while P_RN is taken at the end of the hour.** In the low bucket this selects rows where P_RN has just fallen and PM has not caught up yet.
- **Outcome check, which does not depend on any Deribit code.** In P_RN < 15% main rows, the mean PM − realised is **+0.48 pp [−1.52, +2.66]** (fixing-date bootstrap). By sub-bucket: 0–5% gives +1.47 [0.07, 2.55]; 5–15% gives −0.08 [−3.1, +2.8]. That is at the VWAP, before a fee of about 0.2–0.8 ¢ and before the half-spread. No bug in the P_RN pipeline can hide a longshot overpricing larger than about 2.7 pp.
- **KILL C was evaluated exactly as registered.** It is the row-level median of D over main rows (k inside both smiles, basis defined) with P_RN < 15%: +0.75 pp [0.64, 0.88] against 2 pp. Other ways of aggregating also stay below 2 pp:
  - one value per market: 0.91 pp [0.75, 1.08];
  - extrapolated-strike rows in the low bucket: 0.40 pp, n = 7,759 (the RESULTS number is correct but is not in `step1.json`);
  - τ ≥ 7 d, all buckets: 0.65 pp [0.04, 1.79], 97 markets, 30 dates.

## Blocking issues
None for the verdict. The kill holds under reproduction, an independent recompute, an outcome-only check, and every alternative aggregation I tried.

## Non-blocking issues (fix in RESULTS.md)
1. **The false statement "no cell with ≥ 100 rows reaches 2 pp".** The cell P_RN 15–35% × τ > 7 d has 220 rows and a median of **+2.47 pp [2.04, 2.82]** (53 markets, 23 dates). The cell 5–15% × < 1 d has 990 rows at +1.91 [1.59, 2.25], and its CI crosses 2 pp. Every > 7 d cell with P_RN < 35% is at 2.2–2.6 pp. That matches the prior paper's "largest at long maturity" and should be stated, with its limits:
   - 1,094 rows, 97 markets and 30 dates in total;
   - the pooled > 7 d median is 0.65 pp;
   - it lies outside the registered kill bucket.
2. **The "first observation per market (916 low-bucket markets)" figure is mislabelled.** 12.9 / 10.6 / 10.8 is the first row at which each market is in the low bucket, not its first observation. That choice selects rows where P_RN has just crossed below 15% while the hour-averaged PM lags, so D is mechanically positive. The true first observation of markets whose first main row is in the low bucket gives:
   - n = 496;
   - PM 10.5%, P_RN 9.1%, realised 9.3%;
   - median D 0.69 pp, mean D 1.42 pp [0.98, 1.92].

   Also, thin hours (≤ 2 trades) have a *smaller* median D (0.57 pp) than the rest (0.85 pp). So "early, thin prices are richer" is not supported and should not be carried forward as a hypothesis.
3. **The headline span overclaims.** The text says "4,907 dev markets (2023-04 → 2025-09)", but:
   - 2023 has 3 markets with zero trades;
   - 2024 has 42 panel markets;
   - 97% of main rows are in 2025, and 4,482 of 4,907 dev markets fix in 2025-Q3.

   The dev set is effectively **2025-Q2/Q3**. The sentence "the prior paper's 2023 sample predates the compression" has no 2023 data behind it. The 2024 figure of +2.75 pp comes from 15 markets and has no CI. Say "2024 → 2025 (effectively 2025)". Also note that the calendar-75% rule left the holdout (6,354 markets, about 10 dense months) larger than dev.
4. **Post-hoc numbers are not reproducible from committed code.** This covers the 2024/2025 split, first-observation, extrapolated low-bucket and last-day coverage numbers. Add them to `step1.py --report-only` or to a small `posthoc.py`, and commit it.
5. **Short tenors.** The < 1 d cells show the largest |D| in both directions (+1.9 pp longshots, −2.8 pp at 65–85%). That fits PM's hour-average lagging a high-gamma P_RN taken at the end of the hour. It is a timing artefact, not a price level to sell into. The 39,884 rows with no bracketing expiry (median 0.9 d to fixing) are unmeasured. The selection therefore removes the last day, but not in a direction that hides a sell-longshot edge.
6. **Amendment 2 is acceptable.** It changes the scope of a data-quality gate, not a kill or verdict threshold. It is disclosed and owner-approved, and dev passes by a wide margin (99.35%). The holdout condition is appropriately stricter. Minor points:
   - `both0` (zero counter and zero trades) counts as a pass, which is harmless;
   - it would have been cleaner to register the gate per span in amendment 1.
7. **The 0b parser fixes were found by outcome mismatches.** The rules themselves use metadata only (anchor the year on `created_at`; exclude a 12 AM title with T ≠ end_date). They cannot have changed any verdict, because the first run already passed KILL A (99.90% ≥ 99.5%). RESULTS should say the 12 AM exclusion was discovered through misses.
8. **No `selection_trials.json`.** PLAN §Selection hygiene asks for one row per computed configuration. Step 1 is a single measurement, so one `measurement` row should be logged for completeness.

## What the evidence supports
- There is no systematic PM-over-Deribit longshot gap worth trading on 2025 BTC terminal and range markets. Longshots are +0.5 to +0.9 pp; favourites are −0.9 to −1.4 pp. That is a favourite–longshot tilt about one tenth of the 6–11 pp prior. A YES seller pays a fee of about 0.6–1.2 ¢ plus a half-spread of about 0.5 ¢, which already exceeds it.
- Polymarket is as well calibrated as Deribit here: Brier difference t = 0.23 by fixing date. Against outcomes alone, a naive longshot seller at the VWAP earns +0.5 pp [−1.5, +2.7] before costs.
- Not tested: Rule R's conditional P&L (4.6% of low rows have D ≥ 5 pp and 13% have D ≥ 3 pp). Given about ±1 pp of P_RN row noise and the hour-average lag, those rows are mostly measurement and timing noise. Trading them would be a latency strategy, which is p09's failure mode. The pre-registered gate correctly stopped this. Do not run `step2.py` on this dev set now.
- Kept: `surface.py`, a tested Deribit digital pricer that I reproduced and cross-checked; the settlement parser; and the finding that the HF on-chain table has unreliable timestamps.

## Proposed next experiment
Idea #1 (segmented-market gap) is dead on its main form. Its remaining variants are unlikely to clear costs:
- ETH markets have the same structure.
- "Hit $K" touch markets need a model-dependent barrier fair value, and model error of 2–3 pp is the same size as the bar.

Pivot to **NEWPLAN #2 (variance risk premium)**. It reuses `surface.py` and the Deribit data on disk. Market reasoning: option sellers are paid for bearing crash and squeeze risk, so implied volatility usually exceeds the volatility that later realises. The question is whether that spread survives Deribit costs and hedging.

- **Hypothesis:** a weekly short 7-day ATM BTC straddle on Deribit, delta-hedged daily in the perpetual, earns positive mean P&L after fees and measured spreads on dev.
- **Exact change vs p15:** new target. The measured quantity is the realised P&L of an unconditional short-vol position, not a probability gap. There is no ML at step 1. The HAR-RV + LightGBM timing model is added only if the unconditional book passes.
- **Pre-OOS plan:**
  - Before any P&L, add CVaR(5%), max drawdown and stress-window reporting to the harness, and run the tests and selftest.
  - Fix the dev/holdout calendar split (75/25) over 2022-08 → 2026-08.
  - Measure costs before P&L: Deribit fee of 0.03% of underlying capped at 12.5% of premium per leg, plus the ATM half-spread from Tardis free first-of-month days.
  - Entry: Friday 08:00 expiry cycle at mark ± measured half-spread. Non-overlapping weeks, clustered by week.
- **Kill criteria, fixed in advance:**
  - kill if dev mean net P&L < +2% of premium per week, or if t < 2 over about 130 dev weeks;
  - kill if the worst week loses more than 12 weeks of mean P&L (tail check).
- **Expected cost:** 0 trials in the trial log until one holdout run. Compute is a few CPU-hours over the existing `deribit_opt` files and Binance klines. The harness addition is the main effort.
