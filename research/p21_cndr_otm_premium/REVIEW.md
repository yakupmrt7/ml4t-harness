# Review: p21_cndr_otm_premium
**Decision:** ACCEPT WITH FIXES
**One line:** The monthly 20/5-delta SPX iron condor (CNDR) has no alpha over 1986–2021 as a whole: net +0.75%/yr, NW t 0.61, and Sharpe 0.31 against the market's 0.57. That pooled number hides a split. Before 2010 the alpha is +3.3%/yr (t 2.3, on back-filled mid prices with costs understated); since 2010 it is −3.8%/yr (t −1.7). The break is t −3.4, on a split chosen after seeing the decades. The kill stands. Several sentences in RESULTS overclaim.

Independent checks (dev months only; nothing from 2022 onward was read):
- The French CSV parse is correct. Monthly rows are the 6-digit ones and the columns are `,Mkt-RF,SMB,HML,RF`, so p[1] is Mkt-RF and p[4] is RF.
- The CNDR daily file has no gaps other than the 2001-09 closure. There are no duplicate dates.
- The flat 100.00 values run from 1986-06-20 to 06-30. They are the base period: the first return is 1986-07 measured from 100. At most one month is affected.
- Commit order was PLAN (dd99851), then run.py (bef6e5e), then results (a898c3b). run.py is unchanged since it was committed.
- `trials_eqvol.json` is absent. No harness files were touched.

## Blocking issues (these fix the text of RESULTS.md; the KILL does not change)
1. **The bootstrap run is not a zero-premium null. Relabel it and drop the phrase "below both (t −0.28 and −2.75)".**
   - The bootstrap prices options by Black–Scholes at the flat, unconditional 15.5% vol. It then settles them against the actual monthly returns.
   - Real monthly returns are more peaked than a lognormal with that vol: 66.9% of months finish between the short strikes, against 59.6% under the lognormal.
   - So a short condor priced this way collects a real premium. It is the premium you would earn if the market priced options at historical vol with no smile. A single pass over the actual months reproduces it: alpha +3.96%/yr.
   - What 4.2%/yr measures is "flat-vol pricing vs fat-tailed reality". It is not "zero premium". Kill 2 was correctly specified on the lognormal run, and only that run should be quoted as the benchmark.
2. **The simulated condor carries about 2× CNDR's risk. Disclose this and re-quote the benchmark at CNDR's scale.**
   - With flat vol there is no skew, so the 5-delta put sits close and the wing is narrow. The result:

     | | Simulation | Measured (SPY 2010–21) |
     |---|---:|---:|
     | Credit / T-bill account | 2.71% | 1.27% |
     | Monthly sd | 4.3% | 2.0% |
     | Beta | −0.22 | +0.16 |

   - The sim's alpha sd of "±2.50%/yr" is therefore about twice CNDR's NW s.e. of 1.24%/yr.
   - Scaled to CNDR's vol, the benchmark alpha is about +0.5%/yr, not +1.1%. Kill 2 still fires, with (0.75 − 0.5)/1.24 ≈ 0.2 against a bar of 2.
   - Kill 2 is redundant here anyway: kill 1 fires on its own whatever the benchmark is.
3. **Pre-2010 statement.** RESULTS says the premium "was below the t ≥ 2 bar in each decade". That is true decade by decade, but it hides that the pooled pre-2010 number clears the bar:

   | Period | Net alpha, %/yr | NW t |
   |---|---:|---:|
   | 1986-07 → 2009-12 | +3.19 | 2.28 |
   | 1990 → 2009 | +3.63 | 2.55 |

   Report these numbers and label the 2010 split as post-hoc. Add two caveats that both push the pre-2010 figure down:
   - (a) **Costs.** Pre-2010 costs are understated. SPY options did not exist before 2005, and SPX spreads in the 1980s–2000s traded in 1/16–1/8 ticks. The 2010–21 SPY median (4.2% of credit) is the cheapest possible assumption for exactly the period where the alpha sits.
   - (b) **Back-filled prices.** CNDR before 2015 is a back-fill at 11:00 mid prices from an undocumented source. 1986–89 has 3–9 zero-return days a year.
4. **"Reversed after 2010" / "negative since 2010".** The post-2010 level is −3.76%/yr with t −1.74, which is not significantly below zero. The *change* is significant: −7.6%/yr, t −3.4 (NW, dummy regression). Say "vanished (point estimate negative, t −1.7)".

## Non-blocking issues
- **Sharpe s.e. is missing (rule 7).** Each Sharpe has s.e. ≈ 0.17 over 35.5 years. The gap CNDR − market is −0.26 with s.e. ≈ 0.19 (correlation 0.35), so t ≈ −1.4. Kill 3 is a pre-registered point rule and stands, but quote the s.e.
- **DSR is not reported**, though PLAN lists it. PSR of 0.95 on a skew −2.0 / kurtosis 8.5 series should carry that caveat. The Sharpe of a short-option book overstates it.
- **Timing mismatch.** CNDR rolls on the third Friday, but the sim cycles and the regression use calendar months. So the actual CNDR month spans two option cycles, while in the sim the payoff lines up exactly with the regressor. The "convexity alpha" depends on that alignment. A daily-path, third-Friday sim would be the fair version. It is not worth doing, since kill 1 decides.
- **Cost mapping.** The ratio c = Σ(half-spread + fee) / (10 × max loss) is dimensionless, so computing it in SPY units is correct as a *fraction of NAV*. The small error is that NAV is 10·ML − credit, not 10·ML (about 1%).
  - This is the cost of a SPY replica, not of CNDR. SPX spreads are wider as a share of the underlying and its fees are lower per notional. SPY also carries early-assignment risk on short calls near ex-dividend dates. None of this matters for a KILL.
- **RF subtraction is correct.** The T-bill account is 10·ML ≈ NAV + credit, so CNDR − RF leaves a residual of about rf·credit/NAV ≈ 0.03%/yr.
  - `condor_excess` returns (credit − payoff)/(10·ML) where the exact form is (credit·(1+rf) − payoff)/(10·ML − credit). The gap is about 0.04%/yr plus 1% in scale. Negligible.
  - CBOE uses the 4-week bill; French uses the Ibbotson 1-month bill. Negligible.
- **Benchmark changed from the proposal.** The p20 review proposed SPX total-return excess; PLAN switched to French Mkt-RF (CRSP value-weighted). This was fixed before any computation. Harmless.
- **CLAUDE.md status line** was edited inside the PLAN commit (dd99851). It is a status-only change and nothing is loosened, but status edits should go in their own commit.

## What the evidence supports
- Over 1986–2021 a monthly 20/5-delta SPX condor with 10× collateral earned about beta × market plus nothing. Net alpha is +0.75%/yr, t 0.61, beta 0.16. The appraisal ratio is about 0.11 (0.75% alpha over 6.6% residual vol), so adding it to a market portfolio does not help.
- The pre-2010 alpha (about +3%/yr, t about 2.3) is a post-hoc subperiod result on back-filled mid prices with the cheapest possible costs. It is not investable evidence for today. Since 2010 the point estimate is negative. The disclosed prior knowledge (CNDR about −0.7%/yr compound, 2010–2024) points the same way.
- Scope: this covers **one** structure, a monthly 20/5 condor with 10× collateral. It does **not** cover:
  - put-writing (PUT index),
  - naked strangles,
  - weekly or 0DTE options,
  - delta-hedged variance,
  - VIX-futures roll-down.

  RESULTS says "the equity index option premium … is not tradeable as a stand-alone strategy for a retail account today". Replace it with "this defined-risk OTM structure shows no alpha since 2010 (t −1.7), and its pre-2010 alpha rests on generous costs".
- "Three pre-registered short-vol failures" (p16 BTC straddle kill 3, p20 SPY ATM levered beta, p21 SPX OTM condor) is accurate. The p20 review's pre-registered rule applies: **abandon short volatility.** Do not open PUT, BXM or VIX-roll variants.

## Proposed next experiment
**p22 — pre-earnings long straddles (NEWPLAN2 #2), step-0 screen on free single-stock chains**

**Hypothesis.** An ATM straddle bought at the close 3 trading days before an earnings announcement and sold at the close before it has a positive mean return after the full quoted spread, beyond the same trade in matched non-earnings windows. Clustered t ≥ 2 on dev.

**Market reasoning.** Implied vol rises into a known event because the event's variance gets packed into fewer remaining days. If buyers under-anticipate that rise, the straddle gains vega. Exiting *before* the announcement avoids the post-event vol crush. The position is long vol, so there is no crash tail. The cost that matters is the bid–ask spread, paid twice.

**Exact change vs p21.** A new line (long single-stock vol), so this is not a one-variable change. It needs a new trial log, `trials_earn.json`, created only at the holdout.

**Pre-OOS selection plan (write PLAN.md before reading any straddle price):**
- **Step 0:** get the free optionsDX 10-ticker EOD chains (2010–2023). Take earnings dates from a free calendar, stamped before/after market, so it is clear which close is "the day before".
- **Split:** dev = 2010-01 → 2018-12; holdout = 2019-01 → 2023-12.
- **Fixed rules:**
  - Nearest expiry ≥ 5 trading days past the announcement.
  - Strike nearest spot.
  - Enter at the ask, exit at the bid (both legs), plus $0.65 per contract.
- **Placebo:** the same trade in every 3-day window of the same ticker with no earnings within ±10 trading days, and the same days-to-expiry.
- **Nothing is tuned.** Report entry lags 1, 3 and 5 days as measurements only; 3 is the rule, taken from Gao–Xing–Zhang 2018.

**Kill criteria (decided in advance, dev):**
1. Net mean ≤ 0, or t < 2 clustered by announcement week → KILL.
2. Net earnings minus net placebo, t < 2 → KILL. This checks that the gain is the event effect and not generic vega drift.
3. Median round-trip spread ≥ gross mean → KILL. This is the breakeven test.

**Caveat.** These 10 mega-caps are where the published effect is weakest (it is strongest in small, illiquid names), so the screen is biased against the idea. A pass justifies the paid broad dataset (a few hundred $). A fail on gross (mid-to-mid) mean ≤ 0 kills the line without buying anything. A fail only on costs should be reported as "mega-cap costs too high" and handed to the owner to decide on the paid data. Neither outcome is a new trial on the same data.

**Expected cost:** 0 logged trials on dev. At most 1 holdout trial, only after review and the owner's "go". Compute is trivial; about a day, mostly the earnings-timing join.
