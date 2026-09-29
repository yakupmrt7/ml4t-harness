# p20 — SPY option variance risk premium (defined-risk put spread + ML volatility timing): KILLED on dev

**Verdict: in 2010–2021 SPY options, selling the ATM put earned equity beta, not a premium beyond it, and the timing
rule showed no skill.** Book P (monthly short ATM put / long 90% put, taker prices, IBKR fees) returned **57.5%/yr on capital at
risk** with Sharpe 0.77, but its beta to SPY is **3.5** and its alpha is **+6.5%/yr with Newey–West t 0.42**: kill 2
("premium, not beta": alpha > 0 with t ≥ 2) fires. The ML-timed book fails too (alpha +0.6%/yr, t 0.03) and is
**significantly worse** than the untimed book on the same cycles (−17.3%/yr, paired t −2.9). Per PLAN, **no holdout
run** (neither book passed); `trials_eqvol.json` is not created.

Plan: `PLAN.md` (50c308a), amendment 1 (46b0738, after data validation), amendment 2 (3a611d8, before any P&L).

## Data (step 0; `step0.json`)
- Dev chains: Kaggle `dudesurfin` (optionsDX schema), 3,002 of 3,021 SPY trading days (99.3%); underlying vs Yahoo's
  SPY close: median 1.3 bp. Three closure days with stale rows dropped; crossed quotes excluded from leg selection.
- Cross-source: identical to Kaggle `kylegraupe` (same optionsDX origin); **the independent 2014–2025 set
  (`shankerabhigyan`) failed** (median mid difference 2.5 ¢, 62% within 5 ¢), so per PLAN the holdout would have been
  2022–2023 only. The holdout was not needed.

## Step 1 — unconditional books, 143 monthly cycles (settlement 2010-02 → 2021-12)
Returns are excess returns (collateral earns T-bills); alpha/beta from a regression on SPY's excess return over the same
cycle, Newey–West lag 3.

| book | %/yr | Sharpe | t(mean) | beta | alpha %/yr | alpha t | worst cycle |
|---|---:|---:|---:|---:|---:|---:|---:|
| **P: put spread 100/90, taker (kill book)** | **57.5** | 0.77 | 2.67 | **3.51** | **+6.5** | **0.42** | −81% (2011-08) |
| P at mid prices | 59.0 | 0.79 | 2.73 | 3.52 | +7.8 | 0.51 | −81% |
| put spread 100/95 | 73.5 | 0.68 | 2.33 | 4.73 | +4.7 | 0.17 | −86% (2018-10) |
| P, entry +1 day | 60.3 | 0.82 | 2.82 | 3.38 | +11.1 | 0.71 | −85% |
| cash-secured ATM put | 6.9 | 0.62 | 2.13 | 0.56 | −1.2 | −0.56 | −27% (2020-03) |
| CBOE PUT index − T-bill (same cycles) | 7.3 | 0.61 | 2.10 | 0.63 | −1.8 | −0.91 | −26% (2020-03) |
| delta-hedged ATM straddle (per unit spot) | 1.4 | 0.42 | 1.46 | 0.07 | +0.3 | 0.38 | −3.8% (2020-03) |
| SPY excess (reference) | 14.6 | 0.84 | 2.91 | 1 | — | — | −29% (2020-03) |

- **Kill 1 (≥ 3%/yr on capital): passes. Kill 2 (alpha > 0, t ≥ 2): FIRES.** The put spread's return is ~3.5× levered
  S&P exposure (≈ 0.35 delta per unit of spot over a 10% strike width); after beta, nothing significant is left in any
  variant. **A Black–Scholes simulation with no volatility premium at all**, at SPY's realised 2010–2021 drift (14.6%/yr)
  and volatility (17%), reproduces P almost exactly: 54.9%/yr, beta 3.87, alpha +6.5%/yr (review). The +6.5% "alpha" is
  what a straight-line regression gives a short put in a bull market, not a premium; kill 2 was lenient and still fired.
- **The 57.5%/yr headline is arithmetic on capital at risk:** with all capital at risk every month it compounds to
  10.8%/yr (below SPY's 13.8%); the additive max drawdown is −114% of capital; P's Sharpe (0.77 ± 0.29) is below SPY's
  (0.84) on the same cycles; its alpha has no stable sign (2010–15: −15.4%/yr, t −1.07; 2016–21: +22.0%/yr, t 1.07).
- **The pure variance premium is small here:** the delta-hedged straddle earned 1.4%/yr of spot (1.7% of premium per
  cycle), t 1.46; the cash-secured put and CBOE's own put-write index both show *negative* alpha over 2010–2021.
- Tail of P (capital-at-risk units): CVaR(5%) −65% per cycle, worst cycle −81%, hit rate 78%; stress cycles: 2011-08
  −57% (12 mean cycles), 2015-08 −35%, 2018-02 −12%, 2020-03 −38%. PSR 0.98, DSR 0.94 — high, but for the beta.
- **Bug fix disclosed:** the first run resolved expiry labels wrongly: it **dropped the 2015-12 (−27.9%) and 2018-12
  (−80.4%) cycles and added a fake 11-day cycle ending 2021-12-31 (+18.2%)**, and counted 13 non-cycles. Fixed by
  resolving the label per entry day (143 cycles, all third Fridays, Thursday on Good Friday 2014 and 2019). The fix
  moved alpha from +14.5%/yr (t 1.01, `step1_run1.json`) down to +6.5%/yr, against the hypothesis; both runs fail kill 2.

## Step 2 — ML volatility timing, out-of-sample 2013–2021 (108 cycles, `step2.json`)
- **Forecast:** LightGBM beats HAR on out-of-sample QLIKE (0.514 vs 0.762; paired t −1.76), so kill (a) did not fire
  as written — **but the comparison was unfair and the conclusion "ML adds to the forecast" is wrong** (review):
  LightGBM had implied-vol inputs (VIX z-score, VIX3M/VIX, VIX²/RV) and HAR had none. On the same cycles, OLS on the same
  six features scores 0.509 (ties LightGBM, paired t 0.12); HAR plus VIX²/RV alone 0.472 (better); **the option's own
  implied variance with no model 0.355, better than every model.** The information is in implied vol, not in the model.
- **Timing:** trading P only when IV_ATM² exceeds the forecast (77.8% of cycles) returns 46.7%/yr vs 63.9% untimed on
  the same cycles; alpha +0.6%/yr, t 0.03; paired difference **−17.3%/yr, t −2.9**. Kill (b) fires on both parts.
  With HAR instead: 32.5%/yr, alpha −11.0%/yr. **Which cycles were skipped (review):** 18 of the 24 were calm, low-IV
  months (mostly 2014 and 2017) where trailing realised variance was below IV² and the forecast still exceeded it; the
  skipped cycles averaged +6.5% vs +5.0% for traded ones and 20 of 24 made money. The rule showed no timing skill; the
  paired t −2.9 mostly says that the months it sat out were profitable. (An earlier draft said the skipped cycles came
  after sell-offs; that was wrong.)
- **Rule 10:** the features identify the calendar year with 56.5% accuracy (chance 11.1%) under 5-fold *shuffled* CV of
  daily rows. **This does not show that the features encode the year** (review): six random AR(1) series with the same
  day-to-day persistence (lag-1 autocorrelation 0.84–0.98) score 57.4%, and with whole calendar months held out the real
  features score 28.1% vs 27.4% for the noise. Shuffled CV on persistent daily rows inflates the fold-id test; a noise
  baseline and grouped CV are needed to read it (a proposed amendment to CLAUDE.md rule 10, for the owner).

## What this means
- Selling the ATM put on SPY in 2010–2021 was a way to hold leveraged equity beta with a crash tail: a no-premium
  simulation reproduces its return, beta and "alpha"; the cash-secured put and CBOE's PUT index show negative alpha.
- The forecasting information is in implied volatility itself; neither LightGBM nor any model beat the option's implied
  variance, and the timing rule showed no skill.
- **Scope:** every structure sold the ATM put, and P *bought* the 90% put, which is where the index premium is thought
  to be concentrated. This closes the pre-registered ATM version, not "short index volatility" in general.
- The holdout could not have decided anything: with the independent source failed it shrank to 24 months, where an
  alpha t ≥ 2 is out of reach even for a real premium; these chains have no usable holdout for a follow-up.
- Minor, disclosed: CBOE's VIX closes at 16:15 ET, 15 minutes after the 16:00 chain snapshot (a small look-ahead in the
  timing features); `selection_trials.json` was overwritten by the second run and lost run 1's row (run 1 is in
  `step1_run1.json`); step 0's cross-check streamed 2022 rows of the independent file through memory and discarded
  them unread.

## Files
`PLAN.md` (+ amendments 1–2) · `common.py` · `step0.py/.json/.log` · `step1.py`, `step1.json`, `step1_run1.json`,
`step1.log`, `step1_cycles.csv` · `step2.py`, `step2.json`, `step2.log`, `step2_cycles.csv` · `selection_trials.json`.
