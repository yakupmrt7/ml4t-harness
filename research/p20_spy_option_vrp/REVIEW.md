# Review: p20_spy_option_vrp
**Decision:** ACCEPT WITH FIXES (the kill stands; three explanatory claims in RESULTS.md are wrong and must be corrected)
**One line:** A monthly SPY 100/90 put spread in 2010–2021 earned exactly what a put spread with **zero** volatility premium
would have earned given SPY's +14.6%/yr realised drift, so there is no detectable premium. The ML "win" in the vol forecast
comes from the implied-vol features, not from ML. The fold-id test as run cannot tell these features apart from persistent noise.

Reviewer diagnostics below were run from scratch (nothing in the repo was modified except this file). Holdout files were not opened.

## Blocking issues (fix RESULTS.md before this enters README/CLAUDE.md lessons)
1. **"ML adds to the volatility forecast" is false.** Kill (a) compared LightGBM on six features that include implied vol
   (VIX z, VIX3M/VIX, VIX²/RV) with a HAR that has none. The design confounds model class with information set. Same
   OOS cycles, same expanding-window protocol (QLIKE, lower is better):
   | forecast | QLIKE |
   |---|---:|
   | HAR (as run) | 0.762 |
   | LightGBM, 6 features (as run) | 0.514 |
   | **OLS on the same 6 features** | **0.509** (LightGBM − OLS paired t 0.12) |
   | HAR + log(VIX²/RV₂₁) only | **0.472** |
   | the option's own IV_ATM² (no model) | **0.355** |
   The gain is from putting implied vol into the model. A linear model ties LightGBM, and the raw implied variance beats
   both (it is biased high by the VRP, mean log(RV/IV²) = −0.21, and QLIKE penalises under-forecasts more heavily). Required
   wording: "adding implied-vol features improves the forecast; LightGBM adds nothing over OLS on the same features."
   Kill (a) passed on the letter of the PLAN; say that the kill was confounded.
2. **The fold-id reading is wrong.** 56.5% is an artefact of shuffled 5-fold CV on daily rows with 21–252-day overlapping
   windows: neighbouring days are near-duplicates. Six AR(1) noise series with the features' lag-1 autocorrelations
   (0.84–0.98) score **57.4%**, the same as the real features. With CV grouped by calendar month, features 27.4% vs noise
   28.1%. So the features encode time no more than persistent noise does, and "VIX term slope and IV/RV drift by year"
   is untested (no importance or per-feature check was run; single-feature accuracies are 14–24%). Replace the sentence
   and report the noise baseline. This is also a **harness gap**: a rule-10 number without a matched-persistence noise
   baseline (or grouped CV) cannot be read. p10/p11's 0.94/0.998 were far above any such baseline, but future borderline
   values will not be.
3. **The mechanism given for the timing failure is wrong.** RESULTS says skipped cycles were "high forecast volatility …
   after sell-offs". Of the 24 skipped cycles, **18 had trailing RV₂₁ below IV²**. These were calm, low-IV months (mostly
   2014 and 2017, IV² ≈ 0.005–0.013), where the forecast's mean reversion put RV̂² just above IV². Only 6 (2015-10,
   2016-08, 2016-12, 2017-08, 2018-05, 2019-02) followed a vol spike. The skipped cycles paid +6.5%/cycle vs +5.0% for traded
   ones because SPY drifted up in calm months. Also, the paired t −2.9 of "timed − untimed" with r = 0 when flat mostly
   tests "were the 24 skipped cycles' returns positive" (20/24 were), not timing skill. The right statement is: "the rule
   selected slightly *worse* cycles (5.0% vs 6.5% mean), so there is no timing skill; timed Sharpe 0.70 vs 0.94 untimed."

## Non-blocking issues
- **The test's power should be stated next to the kill.** A Black–Scholes simulation of the same 100/90 structure,
  26-day expiry, n = 143, no jumps, 90% put priced 5 vol points over ATM (skew) and realised vol 16%: P(alpha t ≥ 2) is
  2% if ATM IV = RV, 10% at +1 vol point, 27% at +2 and 78% at +4. So "no premium" means "ATM IV − RV below ~3–4 vol
  points, undetectable in 12 years". It does not mean zero.
- **Linear alpha is biased upward for a short put in a bull market, so the kill was lenient and still fired.** In the
  same BS world with **no VRP** and dev-period SPY drift/vol (μ 14.6%, σ 17%), the put spread earns 54.9%/yr with beta
  3.87 and **alpha +6.5%/yr**. The observed values are 57.5%/yr, beta 3.51, alpha +6.5%/yr. The whole record is
  reproduced with zero premium. This is the strongest single sentence the result supports; add it.
- **Overgeneralisation in "What this means".** Every structure tested sells the ATM put. P also **buys** the 90% put,
  which is where the index VRP is concentrated (skew: OTM puts are the expensive crash insurance), so P is net long the
  richest part of the premium. The result closes "monthly ATM-short SPY structures, 2010–2021". It does not close
  "index option VRP" in general. "NEWPLAN2 #1 is closed" should read "#1 as pre-registered (ATM put spread + ML timing)
  is closed".
- **The headline 57.5%/yr is arithmetic.** Committing all capital at risk each month compounds to **10.8%/yr**, below SPY's
  13.8%/yr compounded excess on the same cycles. Additive max drawdown is −114% of capital, and four cycles lost 76–81%.
  P's Sharpe 0.77 ± 0.29 is below SPY's 0.84 on the same cycles, so the book is dominated before any alpha test. State
  this in the verdict paragraph.
- **Stability:** P's alpha is −15.4%/yr (t −1.07) in 2010–15 and +22.0%/yr (t 1.07) in 2016–21. There is no stable sign.
- **Bug-fix disclosure is incomplete (the fix itself is fine).** I re-ran the pre-fix `step1.py` (3a611d8). Run 1
  **dropped** the 2015-12 (−27.9%) and **2018-12 (−80.4%)** cycles, picked a 2016-06-16 Thursday label, and **added a fake
  11-day cycle** 2021-12-20 → 2021-12-31 on the 2022-01 expiry (+18.2%). This happened because months past the data end
  were not excluded. The fixed run has exactly 143 cycles = every month 2010-02..2021-12, each settling on the third
  Friday (Thursday on Good Friday 2014 and 2019). The 3 delayed entries match the chain's missing days (2011-01-24/25,
  2011-08-22, 2016-04-18). The fix is mechanical, verifiable against the calendar, and moved alpha **down** (14.5 →
  6.5%/yr), i.e. against the hypothesis. It could not have been chosen for effect. Say which cycles changed.
- `selection_trials.json` is rewritten by each step-1 run, so the run-1 rule row is lost. Append it back as a
  `measurement` (bug run).
- **Step-2 feature timing:** VIX/VIX3M closes are 16:15 ET, but the option snapshot and decision are at ~16:00. That is a
  15-minute look-ahead. It is immaterial here because timing failed, but use the previous day's VIX next time.
- Log-target forecasts are exponentiated without a Jensen correction. The measured bias is small (mean log(RV/RV̂) +0.009
  for LightGBM), so this is fine.
- `step0.graupe_dates` streams the 2020–2022 CSV, so 2022 (holdout-year, same optionsDX origin) rows passed through
  memory. They were filtered by date and nothing was computed. Note it in PLAN. The loader guard in `common.py` is correct.
- **Holdout power:** after the shanker source failed, the holdout is 24 cycles. Its annual Sharpe s.e. is ≈ 0.71, so
  "kill 2 on the holdout" (alpha t ≥ 2 in 24 months) would almost never pass even with a real premium. Any future
  SPY-chain experiment on this data has **no usable holdout**. Record this.
- The post-commit edit to `step2.py` (`astype(float)`) is a dtype fix with no effect on the method. Fine.

## Verified (hand checks and re-computation)
- **P accounting.** 2011-08-19: (2.96 − 0.50 − 0.013 − [(131 − 112.64) − (118 − 112.64)]) / 13 = −0.8118 ✓. 2020-03-20:
  (7.56 − 1.50 − 0.013 − 32) / 32 = −0.8110 ✓ (S_T 228.80 = SPY close). 2018-12-21: (6.13 − 0.83 − 0.013 − 27.0) / 27 =
  −0.8042 ✓. Credit is taken at the bid and the wing paid at the ask. Width is 9.3–11.0% of spot. The short strike is
  within 0.4% of spot. Capital = width is conservative (true max loss = width − credit).
- **SPY excess** = adjclose ratio (dividends included) minus DTB3 compounded act/360. The 2020-03 cycle −28.66% includes
  the 3/20 ex-dividend ✓. The DTB3 end-of-interval/discount-basis detail is immaterial.
- **NW alpha/t** recomputed independently: P +6.49%/yr, t 0.423 ✓. CSP −1.20, t −0.556 ✓. Straddle +0.31, t 0.383 ✓.
- **Independent data check:** the chain-built cash-secured ATM put tracks the CBOE PUT index (a separate source) with
  **correlation 0.97** per cycle and mean |diff| 0.48%. It is good evidence that the chain prices are sane.
- **Delta-hedged straddle:** hedge sign correct (+h shares against a short straddle), sold at bids, 1 bp per unit
  traded. Interest on hedge financing and dividends on hedge shares are omitted (small, since h ≈ 0 on average).
- **Step-2 purging** (`target_end < test start`), the forward target (t+1..t+21), trailing features and the QLIKE formula
  are correct. The target (21 trading days) is a few days shorter than the ~18–25-day cycle, which is immaterial.
- **Hygiene:** PLAN → amendment 1 → amendment 2 + `step1.py` → step-1 results → step-2 results, in that commit order.
  No harness, `trials.json` or `trials_hl.json` changes. `trials_eqvol.json` is absent, correctly, because there was no
  holdout run. No thresholds were loosened.

## What the evidence supports
- Over 2010–2021, P's return is fully explained by 3.5× equity beta (the spread's ~0.35 delta per unit of spot divided by
  a 10% width) plus the nonlinearity bias of a short put in a strong bull market. Alpha is +6.5 ± 15.4%/yr (1 s.e.) on
  capital, i.e. +0.65 ± 1.5%/yr of spot notional. That is not distinguishable from zero, and it equals the zero-VRP BS
  prediction.
- The pure ATM variance premium was small: delta-hedged straddle +1.4%/yr of spot, t 1.46. The ATM put-write (chain CSP
  and CBOE PUT) shows alpha −1.2 and −1.8%/yr.
- Adding implied-vol inputs improves 1-month RV forecasts. ML does not improve on OLS. Better RV forecasts did not select
  better short-put months.
- It does **not** show anything about OTM put-selling, iron condors, weekly cycles, or 2022+.

## Proposed next experiment
The PLAN-level question left open is whether the premium lives in OTM wings, where the literature puts it. The SPY chain
cannot answer that with a usable holdout (24 months). One cheap trial can answer it over ~35 years.

**p21 — defined-risk OTM premium from CBOE strategy-index history (closes NEWPLAN2 #1 for good, or not)**
- **Hypothesis:** the Cboe S&P 500 Iron Condor index (CNDR: short ~20-delta put and call, long ~5-delta wings, monthly)
  earns a positive alpha vs SPX total-return excess, net of estimated costs, with NW t ≥ 2 over 1986-06 → 2021-12.
- **Change vs p20:** ATM put spread on SPY chains 2010–2021 → OTM defined-risk index, 1986–2021 dev / 2022–2025 holdout.
  The data source is Cboe's free daily index history, the same place as PUT. BFLY is reported only.
- **Pre-OOS plan (step 0 before any return is read):** confirm that the CNDR history starts ≤ 2000 and confirm the
  index's capital definition (return on max loss). Measure leg costs from the dudesurfin dev chain: median half-spread of
  20-delta and 5-delta 1-month SPY puts/calls, as a fraction of the condor credit, plus $0.65/contract. Deduct them from
  the index's monthly return. Use dev = ≤ 2021-12 and holdout = 2022-01 → 2025-12 (48 months). Nothing is tuned: one
  structure, one cost number, fixed before reading returns.
- **Kill (fixed in advance):** on dev, alpha ≤ 0 or NW t < 2 → KILL. Also KILL if the alpha does not exceed the zero-VRP
  BS benchmark alpha, simulated for the same structure with the realised SPX drift and vol (the bias measured in this
  review), by t ≥ 2. Also KILL if Sharpe ≤ SPX TR excess Sharpe over the same months. If the dev kill fires: abandon
  short-vol entirely. That makes three failures (p16 BTC, p20 SPY ATM, p21 SPX OTM). Then pivot to **NEWPLAN2 #2
  (earnings straddles, long vol)**, which is the other side of the trade and has a spread-driven kill the harness
  measures well. Holdout (one run, `trials_eqvol.json`): alpha > 0 after costs. Report the t, but do not gate on it,
  since 48 months give no power.
- **Cost:** ≤ 1 logged trial. Compute is trivial. Expect about half a day, mostly the cost measurement and the index
  methodology check.
- If the owner prefers to leave short vol now: go straight to #2 with a free 10-ticker optionsDX step-0 screen. Skip
  #4 (weak prior: 0DTE dampening) until #2 and #3 are resolved.
