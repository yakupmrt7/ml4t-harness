# Review: p16_deribit_vrp
**Decision:** ACCEPT WITH FIXES (the kill stands; the fixes are to RESULTS.md wording and labels)
**One line:** The unconditional weekly short ATM BTC straddle, hedged daily, fails the pre-registered tail rule
in every unit and every variant (13.1x in USD, 18.7x in return on notional). Its positive mean is marginal:
t 2.17, which falls to 1.7–1.9 under plausible valuation, cost or entry-time choices. Implied variance did not
exceed 5-minute realised variance on average (t −0.14).

## Blocking issues (fix in RESULTS.md; the verdict does not depend on them)
1. **The funding sign is mislabelled.** `funding` in step1 is *received* funding. Its sum is −0.43% of premium,
   so funding was **paid**, not received. My hand-check agrees: 2025-02-28 paid $18.2 and 2023-01-13 paid $38.6.
   Total costs are 4.54 pts (gross 13.67 − net 9.13), not "4.6". The listed components add up to 4.54 only
   when funding counts as +0.43 paid. The market reason: the short straddle's hedge is long after up-moves, BTC
   rose about 5x over dev, and perp funding is mostly positive (longs pay), so the hedge pays funding.
2. **"The premium is real" and "implied vol does exceed realised vol on average" overclaim.**
   - Measured as IV − RV, the mean gap is 1.25 vol points with t 1.03.
   - Measured in variance, which is the unit a delta-hedged straddle actually earns on, the gap disappears:
     IV² − RV²(5m) has mean −0.002, t −0.14. Against daily-sampled RV² it is +0.019, t 0.98.
   - "68% of weeks" is a median statement. RV is right-skewed, so the median gap is positive while the mean
     gap is about 0.
   - Part of the gross P&L comes from sampling, not from implied vol being high. Daily RV² is 0.91x the 5m RV²
     (intraday mean reversion), and a book hedged once a day collects that gap.
   - The t-stat of 2.17 is fragile:

     | slice or variant | t |
     |---|---:|
     | first half | 1.35 |
     | second half | 1.74 |
     | 2023 | 0.28 |
     | 2024 | 0.87 |
     | entry at 09:05 | 1.71 |
     | stressed spread | 1.89 |
     | valued at raw marks (non-blocking item 1) | 1.91 |

   Replace both claims with "a marginal positive mean, not robust to entry time, costs or valuation".

## Non-blocking issues
1. **The smile overstates the premium.** The quadratic total-variance smile values the ATM straddle 0.9% above
   the raw last ATM marks × index at 08:05 (median of 149 weeks; IQR −0.1% to +2.0%). The likely cause: a
   parabola fitted through a V-shaped smile sits above the vertex. Re-valued at the marks, the book gives 8.2% of
   premium, t **1.91** (kill 2 would also fire), and worst/mean 14.7x (USD) or 21.4x (return). This biases
   toward a pass. Disclose it.
2. **The spread is probably understated.** Deribit BTC options trade on a 0.0005 BTC tick above 0.005 BTC.
   Every print checked on 2025-02-28 was a multiple of it. At 80k that tick is about $40, or 1.2–1.5% of an ATM
   weekly leg's mark (e.g. 79000-P marked at 0.033). If the book is one tick wide around the mark, the
   half-spread is about 0.6–0.75%. The measured median is 0.55%, and 30–47% of prints sit on the "wrong" side of
   mark. The stressed variant fails kill 2 (t 1.89). "The maker variant shows the spread is not the problem" is
   therefore an overclaim. This bias pushes kills 1–2 toward a pass and kill 3 toward a kill.
3. **In USD, kill 3 depends on the hedge-cost assumption.** This is post-hoc and descriptive only.

   | hedge cost | worst/mean, USD | worst/mean, return |
   |---|---:|---:|
   | 5.5 bp taker (registered) | 13.1x | 18.7x |
   | 2.5 bp | 11.4x (would pass) | 16.0x |
   | 0 bp | 10.2x (would pass) | 14.3x |
   | gross, no costs at all | 8.1x | 10.8x |

   - USD units give the 2024–25 weeks (BTC at 60–100k) more weight than the 2022–23 weeks (BTC at 16–30k).
     Return on notional is the scale-free unit, and there the rule fires under every hedge cost.
   - "Narrowly" is true only in USD at the taker cost.
   - 5.5 bp is the registered cost, and it is realistic for a retail Binance taker (5.0 bp fee + 0.5 bp slippage).
     The verdict stands.
4. **Kill 3 rests on a single week.** The second-worst week is 10.7x and six weeks are worse than 8x.
   CVaR(5%)/mean = 9.1x. A rule built on one order statistic is noisy by construction. Say so. Do not use this
   to re-read the kill.
5. **Converting the premium at F instead of the index** overstates it by F/index − 1 ≈ 11 bp, about $5/week
   (2% of the mean). This biases toward a pass. Negligible.
6. **"The worst weeks are rallies" is only partly supported.**
   - In return terms, 8 of the 10 worst weeks are up-weeks, against a 58% base rate of up-weeks. In USD terms it
     is 5 of 10.
   - 2025-02-28 was a whipsaw, not a clean rally. The hedge-time prices ran 79.3k → 92.4k (Monday, the reserve
     spike) → 83.3k (Tuesday) → 88.3k.
   - 2025-04-04, the second-worst week, lost $4.6k on the hedge on a −3.4% week (the tariff crash and rebound).
   - A symmetric straddle losing more often on up-moves, in a sample where BTC rose 5x, cannot tell you where
     the premium sits. Delete the literature sentence or mark it as speculation.
7. **"~$1,700–2,900 premium" is wrong.** The actual IQR is $1,370–4,286, median $2,817.
8. **The harness edit in e17354f is not in RESULTS.md.** e17354f changed `tail_report` so that a date-only
   window end includes the whole day. It was made after the P&L existed. It is a reporting-only fix (stress
   windows), no threshold changed, and a test was added. I re-ran the checks: tests pass and selftest ends
   `HARNESS OK`. RESULTS.md cites only 9075fcf; add e17354f.
9. **DSR is not a real multiple-testing correction here.** It is computed over 5 highly correlated
   cost/robustness variants, so it is roughly the PSR. Do not cite it as evidence.
10. **The follow-up in "Not tested" contradicts the plan.** The PLAN (line 100) made the HAR-RV/LightGBM timing
    layer conditional on this book passing. RESULTS.md lists it under "Not tested" as if it were the natural
    next step. Say that the plan rules it out.
11. **The holdout could hardly have passed kill 2.** The holdout is 53 weeks. At the dev weekly Sharpe of 0.174,
    P(t ≥ 2) on the holdout ≈ 0.23. Even a true edge of the dev size would usually have failed. Future plans
    should state holdout power before fixing holdout kills.

## What the evidence supports
- **The accounting is correct.** I recomputed four weeks independently (2025-02-28, 2023-01-13, 2024-08-02,
  2023-10-20), with my own zip reader and hedge loop. Premium, payoff, hedge P&L, hedge cost and funding all
  match step1 to $0.1. The signs are right: the short book holds +(2N(d1)−1) BTC of perp, positive funding is
  paid by longs, and the delivery price is keyed by expiry date (1.6 bp from the index TWAP).
  - The worst week decomposes as premium $5,597 − payoff $9,286 + hedge $480 − costs $235 = −$3,444.
  - At the smile, the premium equals the raw marks of the same strike to within 0.6%.
- **No look-ahead found.**
  - The smile uses marks in (t−60 min, t], and the strike is chosen from strikes that traded before t.
  - The half-spread h is a trailing 3-month median of trades strictly before Friday 08:00.
  - Perp bars are indexed by close time.
  - Funding in (t_i, t_{i+1}] is the settled rate.
  - The hedge closes at the 08:00 bar.
  - No holdout-week P&L was computed. Step 0 read holdout-period costs, coverage and settlement, which was
    declared.
- **Order and bookkeeping are clean.** Commits run plan 11:17 → harness 11:19 → step 0 and split 11:20 →
  amendment 11:21 → P&L 11:26. Selection rows are in `selection_trials.json`, and `trials_vrp.json` is correctly
  absent.
- **Kill 3 fires exactly as registered** (USD per 1 BTC, the plan's accounting unit): 13.08x > 12x. It also
  fires in return units (18.7x), in % of premium (25.5x), and in all four variants (12.3–15.2x). **KILLED on dev
  stands.**
- What was learned: an unconditional short straddle on Deribit BTC weeklies in 2022-08 → 2025-08 has a mean of
  about +$260/BTC-week with Sharpe 1.26 ± 0.58. The mean is not distinguishable from zero under reasonable
  perturbations. It pays for tails of 10–13 mean weeks and a 27-mean-week drawdown.

## Proposed next experiment
The VRP line should not continue on this data:
- the plan made timing conditional on a pass;
- the unconditional variance premium is t −0.14;
- the 53-week holdout can only confirm a Sharpe above about 2.

Pivot to **NEWPLAN #4, step 0 (free)**: an upper bound on maker P&L in the Polymarket 5-minute BTC markets.
- **Hypothesis (one sentence, falsifiable):** a maker filled at the recorded trade prices (maker side from the
  `last_trade_price` side and fee fields), marked to settlement, with 0 fee and a 20% rebate, earns a positive
  mean per contract.
- **Exact change:** new venue and new target. It measures a counterfactual upper bound. No model, no parameters.
- **Pre-OOS plan:**
  - PLAN.md committed before any data is read.
  - Use only days after 2026-09-20. The p09 dev span (07-25 → 09-05) is spent, and 09-06 → 09-20 stays untouched.
  - Cluster by market. Report fills by price bucket.
  - Check the RTDS Chainlink settlement agreement once 7 days exist (around 2026-10-01).
- **Kill criterion (fixed in advance):** abandon #4 if the upper-bound maker P&L after fees and rebates is ≤ 0,
  or its market-clustered t < 2. It is an upper bound (fast makers cancel stale quotes, so a slow maker gets
  worse fills), so a fail kills the idea outright. A pass only earns a step 1 with an adverse-selection haircut.
- **Expected cost:** 0 trials in any trial log. A few CPU-hours on collector data already on disk.

The alternative, if the owner insists on VRP, is a dev-only falsification with zero holdout: does entry
IV² − trailing 30-day RV² predict weekly gross return? Kill if the slope t < 3. The bar is stricter because the
dev P&L has already been seen. It can only kill, and the plan's own rule argues against it.
