# Review: p18_carry_on_capital (dev only; holdout sealed)
**Decision:** ACCEPT WITH FIXES. Rule 1 fires as registered and the carry line stays closed. The fixes are wording and
disclosure only. None changes the decision.
**One line:** On capital that survives every dev day, an 8-coin HL carry book earned 2.7% (A) / 4.2% (B) in 2025.
Perfect-foresight timing adds about 0.8 pt (5.0%). Counting T-bill interest on the oracle's idle capital puts the
ceiling right at the 6% bar (6.2%). A real forecast would have to capture about 90% of perfect foresight's gain to clear it.

## What I checked, and found clean
- **Process.** PLAN.md was committed at 17:15:58 and run.py plus the tests at 17:17:03. The new candle files were
  fetched between 17:17:04 and 17:17:14, and results.json is stamped 17:17:14. That is one computation, after
  pre-registration.
  - `trials_hl.json` is absent, as it should be.
  - selection_trials.json has 4 entries.
  - harness/, tests and selftest are unchanged, and no threshold was touched.
  - test_oracle.py passes.
  - My re-run reproduces results.json: 2.74 / 4.21 / 3.76 / 5.01.
- **Holdout cut.** Every loader filters `index < 2026-01-12`. Both new files (hl_ohlc_*, bn_spot_ohlc_*) end at
  2026-01-11 on disk. bn_ohlc_* and the funding files run to 2026-09 on disk, but they are cut at load. My diagnostics
  used the same loaders.
- **Funding signs.** A positive rate means longs pay shorts. So the short HL leg receives f_HL, the long BN perp leg
  pays f_BN, and the spot leg pays nothing. The basis terms are −(r_HL − r_BN) and −(r_HL − r_spot).
  - B on notional in 2025, 8-coin mean: HL funding +8.37, basis −0.25, reset cost −1.79 → ≈6.3%/yr. Divided by 1.51
    capital this gives 4.2%/yr, which matches.
- **Candle alignment.** HL, BN perp and BN spot 1d candles all open at 00:00 UTC. Each coin has 742 rows and no gaps.
  Close ratios across venues are HL/BN within 0.3–0.8% and spot/perp within 0.1–0.4%, so none is off by a day.
- **Oracle DP.**
  - It starts flat and ends flat.
  - A switch is charged on the day its new position earns.
  - The reset cost is charged only while in position.
  - Per-coin DPs are additive, so they give the portfolio optimum at fixed capital.
  - Partial positions cannot help: payoffs and costs are linear in the position, so the optimum sits at {−1, 0, +1}.
  - −B (short spot) is correctly excluded: it needs a borrow. Its economic twin is −A, which is allowed.
- **Leverage rule.** L = 1/(1.5M + 0.05) leaves equity 0.5M + 0.05 after the worst move, which is above maintenance.
  - For B, the HL short leg needs the same L as in A: its risk does not depend on the hedge venue.
  - Spot at 1.0 is right. Levered spot would pay a borrow rate of about 5–10%/yr, which is worse.
- **Rule 1 evaluation.** C is the better of oracle A and oracle B on 2025 capital return. C = 5.01 < 6, so the rule
  fires as registered. The margin is 1.05 NW s.e.

## Blocking issues (wording only; the decision stands)
1. **The oracle is not a strict ceiling, and RESULTS says it is.** The claim "no forecast of these books can beat the
   oracle" ignores that the oracle's capital earns 0 on its flat days (18.8% of capital-days in 2025 for oracle B).
   Idle cash would earn T-bills, and the 6% bar is itself T-bill + 2.
   - I re-ran the DP with the flat state earning 4.2%/yr on capital: **C = 6.18%/yr**, i.e. at the bar.
   - Rule 1 as registered still fires. Changing the ceiling definition now to "pass" would be a post-hoc loosening, so
     it does not overturn anything.
   - The honest reason for the closure is different: static B earns 4.21, so a forecast needs (6.0 − 4.21)/(6.18 −
     4.21) ≈ **91% of perfect foresight's timing gain**. No realistic funding or basis forecast gets near that.
   - RESULTS must state this number and reword the verdict's "no forecast … can beat the oracle" accordingly.
2. **The closure covers less than "NEWPLAN #3 entirely".** #3 is cross-sectional: every HL coin plus a CEX, delisted
   coins included, and Boros swaps. The oracle bounds only the *timing* of a fixed, equal-notional 8-coin book.
   - Per-coin book choice gives an oracle of 5.03.
   - But coin selection is unbounded by this experiment: BTC alone reaches 8.9.
   - RESULTS must say that #3 is closed **by the pre-registered decision**, not by a proof. The "Not covered"
     paragraph half-says this already, and the verdict line should too.
3. **The biggest cost is not reported.** The daily-reset cost is 1.79%/yr on notional for B and 1.21 for A, about
   1.2%/yr on capital. That is larger than the whole oracle gain. Add a robustness line to RESULTS (reviewer
   diagnostics on dev, 2025, C = max(oracle A, oracle B)):

   | change (one at a time) | A | B | oA | oB (C) |
   |---|---:|---:|---:|---:|
   | registered | 2.74 | 4.21 | 3.76 | **5.01** |
   | buffer 1.25 / **1.0** | 3.24 / 3.95 | 4.43 / 4.67 | 4.45 / 5.43 | 5.27 / **5.56** |
   | no daily-reset cost | 3.64 | 5.39 | 4.59 | **5.98** |
   | maker-level fees (HL 2, BN perp 2.5, spot 8 bps) | 3.25 | 4.63 | 5.59 | 5.50 |
   | cross-margined legs per venue, buffer 1.5 | 3.16 | 4.74 | 4.34 | 5.64 |
   | T-bill 4.2% on flat days (DP re-optimised) | – | – | – | **6.18** |
   | cross-margin + buffer 1.0 (two loosenings) | 4.55 | 5.11 | 6.24 | 6.08 |
   | buffer 1.0 + no reset + maker fees (three) | 5.26 | 5.99 | 8.61 | 6.82 |

   - Every single change except idle T-bills keeps C < 6, with a margin of 0.02–1.0 pt.
   - Combinations of two or more loosenings cross 6.
   - No static book reaches 6 under any single change. Only B with three loosenings stacked gets to 5.99.
   - So the verdict "carry pays about T-bill + 0–2 pt on this universe in 2025" is robust. The claim "the oracle is
     1 pt below the bar" is not.

## Non-blocking issues
- **The look-ahead in sizing is described backwards for a closure.** PLAN calls it "conservative for a pass", but it
  is *generous* to the books. Sized on 2024 only (what an operator knew on 2025-01-01), the BN long legs of XRP,
  DOGE, LINK, AVAX and SUI, and the HL short of SOL, would have been liquidated in 2025, mostly on 10-10. BTC and ETH
  survive at 2024 sizing. The closure is therefore robust to this point.
- **The −A oracle state uses A's capital.** The reversed legs (long HL on HL lows, short BN on BN highs) need
  0.56–1.94 capital, against 0.55–1.95 for A. The difference is immaterial.
- **2025 static numbers include no entry or exit.** Those fall on 2024-01-01 and 2026-01-11. This is generous by at
  most about 0.2%/yr.
- **The BTC explanation is half right.**
  - For A, leverage is the reason: capital 0.55 against a 5.5%/yr spread.
  - For B, BTC's capital is 1.26 against a 1.51 mean. Its lead comes from the second-highest HL funding (10.6%/yr)
    and the lowest reset cost (0.89 against 1.79, because BTC's daily moves are smaller).
- **Bookkeeping.** run.py *overwrites* selection_trials.json and records no timestamp. Append the reviewer
  diagnostics above as `kind: "review_diagnostic"` entries: they are dev evaluations.
- **Operations.** B's daily reset means selling spot on Binance, converting USDT to USDC and depositing on HL, every
  day. Transfer delay is the real risk for B's short leg, and it is not modelled (disclosed).

## What the evidence supports
- The HL funding premium over T-bills is real but small on survivable capital: 2025 A 2.74 ± 0.84, B 4.21 ± 1.21
  (%/yr, NW).
- The premium fell by more than half from 2024: B went from 9.4 (dev-wide) to 4.2 (2025).
- Timing is worth little. Round trips cost 10.5–15.5 bps per side, while the daily basis moves a few bps. The oracle
  is flat on 19% of capital-days, and that flat time is worth only its T-bill.
- Rule 1 fires as registered. Line closed. Carry on this universe is a yield product, not alpha.
- **BTC-only is correctly framed as post-hoc.** Facts for the owner:
  - A: 8.87 ± 1.51 in 2025, about 1.9 s.e. above 6; 20.4 in 2024.
  - B: 7.76 ± 0.98, about 1.8 s.e. above 6; 18.2 in 2024. Monthly t 6.4, tail ratio 1.1.
  - BTC was the lowest-wick coin on both legs ex ante (2024), and 2024-sized BTC legs survive 10-10. A "lowest wick"
    rule could therefore have chosen BTC in advance. But that rule is one of several I could name after seeing the
    table, so it is not evidence.
  - The premium more than halved in a year. p14's holdout covers about 8.5 months, where the s.e. is about 1.2–1.8%/yr.
    A single holdout look could not tell 6% from 8%.

## What the owner should do with BTC-only
Do not reopen carry as research. BTC carry at about T-bill + 3–4 pt (2025), decaying, with two-venue, USDC/USDT, ADL
and exchange-default risk, is a **treasury or investment decision, not a research finding**.

Spend the holdout on it only if both of these hold:
- the owner would actually deploy capital on a pass;
- the owner explicitly reverses the pre-registered closure in writing.

If both hold, the procedure is:
1. Write a new PLAN: BTC-only B, this spec frozen, 6% on capital, monthly t ≥ 2 on the months available, tail rule,
   zero liquidations.
2. Get a review.
3. Spend one trial in `trials_hl.json`.

The holdout has no competing claimant in the carry line, so the cost is only the precedent of reopening after a kill.

## Proposed next experiment
All NEWPLAN ideas are closed: #1 (p15), #2 (p16), #3 (p14 + p18), #4 (p17). Stop opening crypto lines.

**First, the write-up.** Do ROADMAP §9 (no trial), extended to p12–p18: "the harness said there is nothing here", with
every kill and its number.

**Second, and only if the owner wants one more line: p19, the Polymarket politics favourite–longshot bias.** This is
the parked ROADMAP §10 item and the only idea left with an external prior (arxiv 2609.12878).

The market logic: buying "No" on a longshot ties up about 90–97¢ per share until resolution. So even a real bias must
beat T-bills over that lock-up, not merely show a calibration gap.

- **Hypothesis:** on resolved Polymarket politics markets, contracts priced ≤ 10¢ at T−30 days resolve YES at least
  2 pp less often than their price implies. Buying NO at the ask then earns at least 6%/yr on locked capital.
- **Exact change vs p15:** a new market (politics, not crypto thresholds) and a benchmark of calibration only. There
  is no option leg and no model.
- **Pre-OOS plan:**
  - Write PLAN.md before reading any fills. It must fix:
    - dev = markets resolved before a fixed date, holdout = after;
    - price = the last trade or mid at T−30 days;
    - costs = the measured spread plus Polymarket's fee for that category;
    - effective n = the number of independent **events**, not contracts (one election spawns dozens of correlated
      markets);
    - s.e. clustered by event.
  - Every dev run goes into selection_trials.json.
- **Kill criteria (fixed in advance):** on dev, abandon if either holds:
  - the ≤ 10¢ bin's gap is < 2 pp, or its event-clustered t < 2;
  - the NO-buyer's annualised return on locked capital, after spread, is < 6%/yr.
- **Expected cost:** 0 OOS trials. About 2 days for data (Goldsky / poly_data on-chain fills) and 1 day for analysis.
