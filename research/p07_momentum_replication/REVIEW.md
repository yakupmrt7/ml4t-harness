# Review: p07_momentum_replication

**Decision:** ACCEPT WITH FIXES (the numbers are correct and the kill/gate code matches PLAN.md, but the GATE does not count: do **not** spend the OOS trial on it)
**One line:** p06's 3v3 momentum book reproduces as SR +2.67 ± 0.75 (t 3.58, breakeven 125 ± 35 bps) on 2020-10 → 2022-07, but the 15-perp universe was ranked on 2022-07 volume, which is look-ahead for this window. Hindsight-free subsets of the same universe give SR 1.9 (9 names) and 1.5 (6 names), so the clean new-window Sharpe is unknown. It is probably above 0 and probably well below 2.67.

Verification done by this review (not taken from the report):
- **Independent implementation** on daily 04:00 closes (no harness, own weights, own funding bucketing): SR 2.56, t 3.44, breakeven 124.9 bps, 657 days. Per period: 2020-Q4 5.89 / 2021 3.13 / 2022 0.31 (script: 5.69 / 3.38 / 0.26). The gap is 5m-summed vs daily-compounded arithmetic, as in p06. No sign, alignment or bucketing error.
- **Funding:** my own daily bucketing gives a net funding charge of +0.055 units against 14.67 units of price P&L (0.37%, the script says 0.37%). In 2021 the longs paid 1.12 and the shorts received 1.07. Funding was high everywhere (6–13 bps/day), and a dollar-neutral book pays it on one leg and collects it on the other, so it nets out.
- **Largest asset-days are real events, not bad prints:** SAND +98% on 2021-10-30 and +68% on 2021-11-01 (the Facebook → Meta rename), MATIC +67% on 2021-03-11. SAND's two Meta days alone are **11% of total P&L**.
- **Kill/gate/underpowered logic:** read line by line against PLAN.md. It matches (details below).
- Harness: `git diff HEAD -- harness` is empty, so no tests or selftest were owed. `trials.json` is untouched. `selection_trials.json` has exactly 1 row.

## Blocking issues
1. **The GATE is mechanically valid but must not be credited, and the OOS trial must not be spent on it.** PLAN.md itself says "the p06 window is not a clean sample … **the new window is the clean test**". The new window is not clean. p04's rule (listed by 2022-06, ranked on 2022-07 quote volume) is point-in-time for a window *starting* 2022-08. For a window *ending* 2022-07, it selects the coins that were still among the most traded at the end. I rebuilt p04's rule point-in-time from the archive, using **volume only and no returns**, with 1d files (same quote-volume totals):
   - Ranked on **2020-09** (listed by 2020-08; 43 eligible perps): BTC ETH LINK TRX BNB YFI DOT BCH XRP EOS SXP LTC ADA NEO OMG. **6 of 15 overlap with p07's universe.**
   - Ranked on 2021-03: 6/15 overlap. 2021-09: 8/15. 2022-01: 8/15 (LUNA, FTM, ATOM, NEAR, DOGE, LINK, SHIB are in; LUNA was delisted in 2022-05).
   - 6 of p07's 15 names (MATIC, SAND, UNFI, GMT, APE, OP) had **not yet listed** when the window started. They enter only because they survived to rank in 2022-07. Coins listed in 2021 that pumped and then faded or were delisted can never be in this universe. Those names carry **38%** of the window's P&L (MATIC 17, SAND 23, OP 4, APE 2, GMT 1, UNFI −9).
2. **How big is the bias?** Cheap bounds from data on disk. These are reviewer diagnostics on the already-read window, not trials, and no choice rests on them:
   | book (daily-close impl.) | days | SR | t | 2020-Q4 | 2021 | 2022 |
   |---|---:|---:|---:|---:|---:|---:|
   | p07 as run, 15 names, 3v3 | 657 | 2.56 | 3.44 | 5.89 | 3.13 | 0.31 |
   | only the 9 listed before the window, 3v3, ≥8 live | 647 | 1.92 | 2.55 | 5.96 | 2.11 | −0.56 |
   | only the 6 also in the 2020-09 point-in-time top 15, 2v2 | 659 | 1.47 | 1.97 | 3.47 | 1.82 | −0.88 |
   | same 6, 1v1 | 659 | 0.74 | 0.99 | 4.02 | 0.88 | −2.68 |

   So roughly **1 unit of SR of the 2.6 comes from names added with hindsight**. The subsets are still survivors, since they exclude LINK, YFI, SXP, EOS and the rest, so even 1.5 is not clean. The bias does **not** come from average drift. Splitting P&L into Σw·μ_i (ex-post mean return per asset) plus timing, the μ part is only 5 of 223 bps/day in the new window. (In the p06 window it is 25 of 47, and the timing-only SR is 0.46.) The channel is *path*: the universe is guaranteed to contain the coins whose 2021 pumps momentum rode (SAND in Oct–Nov 2021, MATIC, AVAX), and it cannot contain the ones where momentum bought the top and rode the collapse.
   A pooled t without the new window is p06's t = 1.23, so no gate. **The gate outcome rests entirely on a biased input.**
3. **Fix the RESULTS.md verdict line** to: "Gate passes mechanically; not credited because the universe is look-ahead for the new window; OOS not spent; p07b (point-in-time universe) pre-registered." Right now it reads "the pre-registered gate passes" first, and a reader skimming trial rows sees `decision: "GATE: proceed to OOS gate"`. Add a `note` field to *that same* row only if the owner allows an annotation. Otherwise put it in RESULTS.md. Never edit the logged numbers.

## Non-blocking issues
- **Overclaims in RESULTS.md "Evidence consistent with this":**
  - "Long leg +19.5, short −4.9: the book's money is in being long the eventual winners." In a market that rose a lot, any dollar-neutral book's long leg wins and its short leg loses. p06's REVIEW made exactly this point. Beta is +0.12. This split is not evidence of survivorship. Delete it, or replace it with the Σw·μ decomposition above, which actually *contradicts* the "long the eventual winners" story in the static-drift sense.
  - "The edge fades as the window approaches the ranking month (5.7 → 3.4 → 0.26)." The hindsight-free 6-name subset fades the same way (3.47 → 1.82 → −0.88), and p06's point-in-time window starts at 0.24 for 2022-08..12. The fade is the 2022 bear-market regime (momentum crashes at trend reversals), not proximity to the ranking month. Remove it as evidence of bias.
  - "Published crypto cross-sectional momentum results are strong for exactly this period." No citation, and it is not relevant to the claim. Cite or cut.
  - "2.67 is an upper bound, not an estimate." Directionally right, but it is not a bound in any formal sense. Say "biased upward by an unknown amount; subset diagnostics suggest ~1 SR".
- **Archive holes** in the monthly 5m files: SOL, SAND, UNFI, XRP are missing 2022-02-26 00:00 → 03-01 00:05, and SOL, SAND, UNFI, XRP, GMT are missing 2022-04-01 → 04-03 (BTC, ETH and others are complete). In the harness the asset is non-live there. The position is force-closed and reopened, costing turnover, and the return across the hole is set to 0 (e.g. UNFI +10%, SOL +8%). Momentum is NaN for about 28 days later too. This affects 2022 only (SR ~0.3 either way), so it cannot change any conclusion. Fill the holes from the daily files in p07b.
- **Effective n:** NW(10) t 3.34 vs iid 3.58, so n_eff ≈ 0.87·n. Fine and reported. Fat tails: without the 10 best days, SR is 1.77. The 2020-Q4 SR of 5.69 is over 80 days, so its s.e. is ~2.1. Do not quote it without the s.e.
- **PLAN edit after download:** 9bd5432 (11:31:55) changed the "live" definition *after* the raw 2020–22 zips were downloaded (11:28–11:30) but before the caches were built (11:32) and before any run. It aligns the wording with p06's frozen code and involves no discretion, so it is acceptable. Say so in RESULTS.md.
- **Run history is not stated.** RESULTS.md has mtime 11:50, but the logged run finished at 11:54 (882 s, so it started ~11:39, after the last edit of selection.py at 11:38). The numbers therefore came from an earlier run. State how many times selection.py was run on the new window and whether the code changed between runs. With zero free parameters this is not a hygiene failure, but it has to be on record.
- Pooled turnover omits the final exit of each window (6 units of 2,466). This is negligible.
- **Accountability:** the "same universe" instruction came from p06's REVIEW (this role). The error was the reviewer's, not the implementer's.

## Selection hygiene
- PLAN.md was committed at 890910c, 11:27:52. The earliest new-window raw file is from 11:28:00. The factor, book, window, costs, kill, gate and underpowered band are all fixed in the plan. Zero free parameters were chosen on the new window. The code implements the plan:
  - kill = `new SR ≤ 0 or new BE < 12`
  - gate = `not killed and both SR ≥ 0.5 and pooled t ≥ 2.0 and pooled (BE − 1 s.e.) ≥ 12`
  - underpowered = `not killed, not gate, both SR > 0, 1.5 ≤ pooled t < 2.0`
  - else fail

  Pooled t = SR·√(n/365) on the concatenated daily series. Pooled breakeven = Σgross/Σturnover, with s.e. = std·√n/Σturnover as planned. The <8-live days are dropped (asserted zero P&L on them). p06's stub bucket is dropped. p06's numbers reproduce exactly (0.951, t 1.229, 21.0 ± 17.1, shift-null p 0.087). **The logic is exactly as PLAN.md states.**
- 1 row in `selection_trials.json`. `trials.json` untouched. Correct.
- The rank-demeaned book is reported as a diagnostic only and was not used for the decision. Correct.

## What the evidence supports
- In 2020-10 → 2022-07, among coins that were liquid perps by 2022-07, 28d/skip-1 momentum earned SR ~2.6 gross, with a breakeven far above any plausible cost (125 bps vs 12). Funding nets out. Beta is ~0.
- It does **not** establish that the factor would have earned that on a universe knowable in 2020. The restricted subsets (1.9, 1.5) say "probably positive". Their t values (2.55, 1.97) are on books that were not pre-registered and are still survivors.
- Across both windows, the per-period SRs (5.7, 3.4, 0.3 | 0.2, 2.1, −2.9) show a regime-dependent factor. It works in trending bull phases (2020-Q4, 2021, 2023) and loses at reversals (2022, 2024-Q1). That is the textbook momentum profile. For the OOS trial it means the outcome will depend largely on which regime 2024-04 → 2026-08 happens to be.

## Proposed next experiment (p07b): the same replication on a point-in-time universe
- **Hypothesis (falsifiable):** p06's 3v3 28d/skip-1 momentum book, run on a universe chosen by p04's rule *as of the month before the window*, has gross SR > 0 and breakeven ≥ 12 bps on 2020-10 → 2022-07. Falsified if SR ≤ 0 or breakeven < 12.
- **Exact change vs p07:** one variable, the universe *date*. Apply p04's rule unchanged with the dates shifted to one month before the window, exactly as p04 did for p06: eligible = a 2020-08 5m file exists; rank by 2020-09 quote volume; exclude stable-vs-stable pairs; one contract per underlying (highest volume); top 15; BTCUSDT must be in it. Delistings follow p04's last-trade-count>0 rule, with no successor splicing. It is **static** for the whole window, like p04's universe for p06. Expected membership (volume only, computed here): BTC ETH LINK TRX BNB YFI DOT BCH XRP EOS SXP LTC ADA NEO OMG. It must be re-derived by the script and archived with sha256, as p04 did. **Monthly reconstitution is not allowed.** It would be a second free choice made after this window has been seen. Book, costs (flat 12), ≥8-live rule (it will not bind) and p06 window: all unchanged. Also fill the 2022-02-26 / 04-01 archive holes from daily files, as a pre-registered data fix.
- **Is it allowed before OOS given "zero free parameters"?** Yes, as long as it is written into a PLAN.md and committed before any kline of the 9 new symbols is downloaded. It corrects a misapplied rule (a universe date that was point-in-time for one window and not the other). It does not tune anything, and the rule has no parameters left once "month before the window" is fixed, which is also how p04 was built. Two caveats go in the PLAN. (a) The window is no longer untouched: p07 and this review both read it, so p07b is a de-biased re-estimate and not a pristine replication. Mechanically fixing the rule before seeing its output is what keeps it honest. (b) p07's row stays in `selection_trials.json`, p07b adds a second row, and a gate pass on p07b is interpreted knowing it is the second look at the window.
- **Pre-OOS selection plan:** nothing is selected. Report exactly p07's table for p07b's universe, plus the list and live count.
- **Kill criterion, fixed now** (same thresholds as p07, not loosened):
  - KILL the daily cross-sectional momentum line if the p07b new-window gross SR ≤ 0 or its breakeven < 12 bps.
  - GATE only if both windows' SR ≥ 0.5, pooled t ≥ 2.0 (p07b window + p06 window), and pooled breakeven − 1 s.e. ≥ 12.
  - Underpowered band 1.5 ≤ t < 2 with both SR > 0: STOP, report it, and write nothing new.
  - If it GATEs, rebuild costs for the new window's names before the OOS trial, because 2020 spreads on SXP, OMG and NEO may exceed 12 bps. Then spend the single OOS trial on the p06 book (p04 universe, 2024-04 →) and log it in `trials.json` with DSR.
  - If p07b fails, that is the daily xsec line's second failure (p06, p07b). Per the p06 REVIEW, the next failure means pivoting to the collector data, and the rank-demeaned/breadth variant is the only remaining shot.
- **Expected cost:** 1 selection trial and 0 OOS trials. Downloads: 9 new symbols × ~24 monthly 5m files, plus funding and ~6 daily files for the holes (~250 zips). Compute: one ~15 min run.
