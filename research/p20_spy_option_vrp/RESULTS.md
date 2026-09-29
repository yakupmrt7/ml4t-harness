# p20 — SPY option variance risk premium (defined-risk put spread + ML volatility timing): KILLED on dev

**Verdict: in 2010–2021 SPY options, selling puts earned equity beta, not a premium beyond it, and ML timing made it
worse.** Book P (monthly short ATM put / long 90% put, taker prices, IBKR fees) returned **57.5%/yr on capital at
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
  S&P exposure (capital at risk = a 10% strike width); after beta, nothing significant is left in any variant.
- **The pure variance premium is small here:** the delta-hedged straddle earned 1.4%/yr of spot (1.7% of premium per
  cycle), t 1.46; the cash-secured put and CBOE's own put-write index both show *negative* alpha over 2010–2021.
- Tail of P (capital-at-risk units): CVaR(5%) −65% per cycle, worst cycle −81%, hit rate 78%; stress cycles: 2011-08
  −57% (12 mean cycles), 2015-08 −35%, 2018-02 −12%, 2020-03 −38%. PSR 0.98, DSR 0.94 — high, but for the beta.
- **Bug fix disclosed:** the first run chose the wrong expiry label in some months (a Thursday could win over the third
  Friday; the Dec-2015 monthly carried two labels) and counted 13 non-cycles; fixed by resolving the label per entry day
  (143 cycles, 0 skipped). The first run (`step1_run1.json`: alpha +14.5%/yr, t 1.01) also fails kill 2.

## Step 2 — ML volatility timing, out-of-sample 2013–2021 (108 cycles, `step2.json`)
- **Forecast:** LightGBM beats HAR on out-of-sample QLIKE (0.514 vs 0.762; paired t −1.76), so kill (a) does not fire:
  ML adds to the *volatility forecast*.
- **Timing:** trading P only when IV_ATM² exceeds the forecast (77.8% of cycles) returns 46.7%/yr vs 63.9% untimed on
  the same cycles; alpha +0.6%/yr, t 0.03; paired difference **−17.3%/yr, t −2.9**. Kill (b) fires on both parts.
  With HAR instead: 32.5%/yr, alpha −11.0%/yr. The skipped cycles (high forecast volatility) are disproportionately the
  profitable ones: after sell-offs, implied vol is high, the market rebounds and short puts pay.
- **Rule 10:** the features identify the calendar year with **56.5%** accuracy (chance 11.1%) — they encode the regime
  despite the ratio/z-score construction (VIX term slope and IV/RV ratio drift by year), another reason not to trust
  the timing.

## What this means
- SPY put-selling in 2010–2021 was a way to hold leveraged equity beta with a crash tail, not a separate premium: every
  construction's alpha is indistinguishable from zero (or negative), consistent with the post-publication decline
  literature for US anomalies.
- Machine learning *can* forecast volatility better than HAR, but a better volatility forecast did not produce a
  better short-volatility book; the premium is not where the forecast error is.
- NEWPLAN2 #1 is closed on dev; the holdout (2022–2023) stays unread.

## Files
`PLAN.md` (+ amendments 1–2) · `common.py` · `step0.py/.json/.log` · `step1.py`, `step1.json`, `step1_run1.json`,
`step1.log`, `step1_cycles.csv` · `step2.py`, `step2.json`, `step2.log`, `step2_cycles.csv` · `selection_trials.json`.
