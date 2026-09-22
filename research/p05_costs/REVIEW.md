# Review: p05_costs
**Decision:** ACCEPT WITH FIXES
**One line:** On BTC/ETH, realistic maker execution costs 3.4 / 2.9 bps per unit traded (±0.3), not 2.5. That fires the kill criterion written in p04's REVIEW, so 5m bar-close mean reversion on Binance perps is abandoned. No asset's pre-OOS edge is distinguishable from its cost (max z 1.18 across 15 assets). The 2025–26 half of the cost table understates spreads and needs fixing before anyone uses it.

## Blocking issues
1. **The kill rule was weakened compared with the one it cites.** p04 REVIEW.md: "if the measured all-in maker cost is ≥ 2.5 bps … abandon 5m bar-close mean reversion on Binance entirely." p05 PLAN.md presents its rule as coming "from p04 REVIEW.md", but it adds a condition: "AND no asset has edge > realistic cost". The PLAN was committed before any data, so this is not snooping. But it does loosen an earlier commitment (the spirit of rule 5). Under the original rule, BTC 3.38 and ETH 2.86 (shortfall), or 3.70 / 3.80 under p04's own markout formula, both pass 2.5, so **the kill fires**. RESULTS.md must say this, and must drop "do not formally abandon the family". This is also the 4th of 4 experiments on this idea to end "not tradable" (p01–p04).
2. **The cost table breaks the tick floor.** The half-spread can never be below tick/2, because the spread is at least one tick. In `costs_table.csv`, 160 of 690 rows have `half_spread_bps < 0.9·tick_bps/2`: 101 in 2025–26, 32 before OOS. The cause is that the overlap ratio (proxy/true ≈ 0.5–0.6, fitted in 2023-05→2024-03 while these assets were not tick-bound) is applied to later months in which falling prices made them tick-bound. Example: OP 2026 is listed at 1.97 bps against a tick of 7.97 bps, i.e. a floor of about 4.0. RESULTS' "OP's half-spread went from 0.3 to 2.0 bps" therefore understates OP by about 2×, and `taker_all_in_bps` is too low exactly in the OOS months where `TableCostModel` would be used. Fix: `half_spread = max(tick/2, calibrated proxy)`, or skip the ratio once `tick/2 ≥ proxy×ratio`. Then rebuild the table and state the count of rows that change.
3. **The effective-spread paragraph claims too much.** "This is the impact that the taker all-in column does not include" is not supported, for two reasons. (a) The volume-weighted effective spread is the market-wide average, dominated by *other people's* large sweeps, not the impact of an order of our size. (b) It is compared with a *time-weighted* quoted spread, and spreads are wider at the moments trades happen. I checked one day (ETCUSDT 2023-06-10, bookTicker + aggTrades). The median trade's effective half-spread is 0.36 bps against 0.27 quoted, and the average quoted half-spread at trade times is 0.94. Grouping trades into same-ms, same-side taker events and bucketing by size, the mean effective half-spread is <$1k 0.93, $1–10k 1.7, $10–50k 5.6, >$50k 14.4 bps. So the conclusion "ETC/OP taker cost is understated at $10k" is probably right, and understated by several bps. But the evidence for it is a size-bucketed curve, not the 1.8–70× ratio. Replace the paragraph with that, or soften it.

## Non-blocking issues
- **The calibration choice favours the survivors.** The decision table uses additive maker shifts fitted on about 150 matched *p04* orders (ETC −1.33, AVAX −0.96, UNFI −1.95; AVAX T60 −13.0, which is why AVAX's T=60 cost is −1.5). PLAN only specified the half-spread ratio. With the grid calibration, or no calibration: AVAX 5.23 / 5.33 > BE 4.94, so it drops out and **7, not 8** assets pass. ETC's cost rises 2.62 → 3.35. The s.e. values do not include calibration uncertainty. The T=60 column should not be quoted.
- Orders are unweighted by size. There are 1,930 flips of size 2 (4.6%). Weighting by size moves costs by ≤0.33 bps and leaves the same 7 assets passing.
- `p04_trade_times.parquet` has no committed derivation script. I rebuilt ADA from `preds_selection.parquet` + `hysteresis_position`: 2,823 of 2,823 times match, and `t` is the target-change bar, which is the correct post time for delay=1. Commit the snippet.
- `run_portfolio_backtest` with `{asset: TableCostModel}` will raise KeyError for MATIC after 2024-09 and UNFI after 2024-10, because the grid is the union across assets and the table has no rows there. The raise should only apply to bars with trade ≠ 0 (or to the asset's live window).
- The fill model has no order size. Assuming a full fill on a trade-through is optimistic whenever the order is larger than the top level (median top depth: ETC $1.7k, OP $1.6k, UNFI $0.5k).
- "Filled orders cost about 2 bps" holds only for the majors. For the tick-bound alts a filled order costs 2 − half-spread ≈ −0.5 to +1 bps.
- The explanation of why Roll/CS fail is speculative ("they measure short-horizon volatility"). The fact that they fail is shown; the reason is not.
- For BTC, `tick_bps_trades` (0.004–0.013) disagrees with `tick_bps_quotes` (0.024). Trade-derived tick estimates are unreliable for BTC.
- Table values are monthly means that include days after any given bar. That is fine for costing and a leak if used as a feature or a trade gate. Say so in the `TableCostModel` docstring.
- `trade_proxy_quotes` + `quote_asof(t)` also uses trades stamped exactly at t, which belong to the next kline. That is 1 ms of look-ahead, negligible.

## What the evidence supports
- **The cost definition is correct.** The backtest (delay=1) fills at close[t] of the decision bar. After the fill, a maker position earns exactly the backtest's returns. So the implementation shortfall against mid_t, with unfilled orders completed at the t+T quote, is exactly the extra cost per unit traded. Adding the post-fill markout on top counts it twice, as RESULTS says. Mid vs close at p04 trade times: side·(close−mid) has mean ≤0.24 bps in absolute value on every asset, always within 1.7 s.e. So bid-ask bounce does not bias the comparison.
- **The simulator code is correct.** Fill rule: strict inequality, (t, t+T]. Time units are consistent. The taker completes at the opposite quote at t+T. `quote_asof` is causal. Tests 37/37 ok, selftest HARNESS OK. The hook changes nothing when no time-varying model is used, and a constant table reproduces `CostModel` (tested).
- **Maker costs on the majors:** BTC 3.38 ± 0.30, ETH 2.86 ± 0.36 bps. Both exceed 2.5 under either definition. The market reason is that about 10% of orders don't fill because the price ran away, and completing them costs 12–14 bps each. The 0.02 bps of spread a maker earns on BTC is worthless.
- **Edge vs cost.** Per asset, max z = 1.18, the mean of the 15 z-values is about −0.1, and 7–8 of 15 pass on point estimates. That is what pure noise would produce. At the portfolio level, p04's pooled pre-OOS breakeven is 2.51 bps, against an average maker cost of about 3.9 bps (≥ about 3 even on the cheapest assets). **The portfolio does not cover maker costs.** The breakeven s.e. approximation, BE/(SR_gross·√1.68 yr), is standard and reasonable for bar P&L that is roughly uncorrelated. Its caveat is that PurgedKFold BEs are optimistic.
- The bookTicker measurements hold: the 2023-05→2024-03 quoted spreads and top-of-book depth, and the tick-bound versus tight-book split in how good the proxy is. The tick-size trend is real in direction but its size is understated (Blocking 2).
- Hygiene: trials.json is unchanged (3 entries), selection_trials.json has 1 measurement row, and no OOS was touched.

## Proposed next experiment
The idea has now failed 4 times, always at the cost wall. Stop reducing costs on a 5m/4h signal. Instead pick a horizon where the measured costs (6–7 bps taker plus impact) are small compared with the move per trade.
- **Hypothesis:** A cross-sectional daily ranking of the 15 p04 perps on archive positioning data (funding, the change in premium/basis, the change in OI, top-trader L/S), rebalanced once a day with long-short dollar-neutral weights, has a pre-OOS PurgedKFold breakeven ≥ 15 bps per unit traded. That is ≥2× the measured taker cost, as a margin for impact and the PurgedKFold→walk-forward drop.
- **Exact change vs p04:** only the label horizon and rebalance change (H = 1 day, 00:00 UTC decision, delay=1 bar = 5 min), with features limited to p03's positioning set, already causal via `asof_join`. Costs: `TableCostModel(kind="taker")` after Blocking 2 is fixed, plus funding (it matters at daily holds).
- **Pre-OOS selection plan:** no grid. Fix the feature set, the model (p04's), and a top/bottom-3 equal-weight book in PLAN.md. Measure turnover and breakeven on 2022-08 → 2024-03 only.
- **Kill criterion (fixed in advance):** abandon without any OOS run if the pre-OOS portfolio breakeven is < 15 bps, or if the gross Sharpe t-stat is < 2 (at 1.68 yr, s.e. ≈ 0.77, so this needs a gross SR above about 1.5). Only if it passes: one walk-forward OOS trial, logged, with the same thresholds.
- **Expected cost:** 0 OOS trials unless the pre-OOS kill passes, then 1. Compute is small, since the daily panel has about 15×600 rows before OOS. The only prerequisite is the tick-floor fix in `harness/costs.py` plus a test.

## Round 2
**Decision:** ACCEPT
**One line:** All 3 blocking items are fixed. The result stands: maker cost is BTC 3.38 ± 0.30 and ETH 2.86 ± 0.36 bps, which fires p04's original kill rule, so the 5m bar-close mean-reversion family (p01–p04) is abandoned. The cost table now respects the tick floor. Taker cost at $10–50k per order is 7.2–21.5 bps on the thin or tick-bound alts.

### Round-1 blocking items
1. **Kill rule: fixed.** The verdict applies p04's original rule. RESULTS says in plain words that PLAN's added condition was a loosening. `results.json` carries both flags (`abandon_family_p04_review_rule: true`, `..._p05_plan_rule: false`), and the recommendation is to abandon.
2. **Tick floor: fixed.** `monthly_cost_table` now sets hs = max(hs, tick/2) and tags the row `+tick_floor`. A unit test covers it.
   - Rows below the floor: 0 of 690 (was 160). Rows below 0.9·tick/2: 0.
   - Rows where the floor binds: 217 proxy months (128 of them in 2025–26) plus 69 bookTicker months. I recomputed the bookTicker months unfloored: the floor moves them by a median of 0.8% and at most 5.6%.
   - The "Over time" table matches the CSV exactly. OP 2026 is now 3.98 bps half-spread and 8.98 bps taker, against 1.97 before.
   - `tick_bps_trades` is the minimum gap between distinct trade prices in a day, so it cannot be below the true tick except for BTC (see round 1). The floor cannot overstate costs through a bad tick estimate.
3. **Effective spread: fixed.** The market-wide VW-vs-TW ratio paragraph is gone. It is replaced by `impact_check.py`, which treats a taker order as all aggTrades with the same ms and side, takes their VWAP, and measures against the bookTicker mid 1 ms earlier (causal). The run covers 6 assets × 2 days.
   - Every number in the RESULTS size table matches `impact_check.log/json`.
   - Derived claims check out: $10–50k taker all-in is 7.22 / 8.31 / 8.48 / 9.38 / 10.60 / 21.54 bps, which is 1.30–3.54× top-of-book. The quoted spread at order times is 1.02–1.97× its time-weighted value.
   - It agrees with my round-1 ETC spot check (5.6 bps at $10–50k on 1 day, vs 3.48 over 2 days).

### Round-1 non-blocking items
- Calibration sensitivity: disclosed, including the fact that the p04-set calibration was not chosen blind. The 8→7 drop with AVAX at 5.43 / 5.53 / 5.00 matches build.log. ETC 3.32 / 3.22 / 2.63 matches.
- Size-2 flips: disclosed. Size weighting is in the table.
- `make_p04_trade_times.py`: I re-ran it. The output is `DataFrame.equals` to the committed parquet (42,225 rows, 1,930 of size 2).
- Portfolio KeyError for delisted assets: fixed, and a test covers it.
- Look-ahead note: now in both the `monthly_cost_table` docstring and Limitations. It is not in the `TableCostModel` docstring. Add one line there.
- Roll/CS: the reason is now stated as untested. The T=60 warning is in place.
- Tests: 37 ok, and selftest ends with HARNESS OK (I re-ran both). trials.json is unchanged (3). selection_trials.json has 2 measurement rows (original build + rebuild), which is fine.

### Non-blocking (new)
- **Latent bug in `_cost_matrix`: it charges zero cost on bars with no data.** It queries the table only where `np.isfinite(C)`. `_panel` forces W = 0 on non-live bars, so an asset with an interior data gap trades inside the gap. The constant `CostModel` charges those trades; the table model silently charges 0. On a toy 3-bar gap: 16.5 vs 5.5 bps. The p04 universe has 0 interior gaps on the union grid, so no current number changes. Fix: query cost at bars where trade ≠ 0 (raise there if the month is missing), and add a test with an interior gap. Separately, the forced exit and re-entry across a data gap is itself questionable for any future universe that has gaps.
- The frozen exit padding after a delisting is queried too. If an asset's last bar is the last bar of a month, the padding bar falls in a month with no table row, and the lookup raises. This does not happen for MATIC or UNFI, but it is an edge case.
- The tick floor adjusts only the half-spread and taker columns. Proxy-month `maker_all_in_bps` is unchanged. That is acceptable, because the proxy is within 15% of the truth on tick-bound books, but the 2025–26 maker values should be treated as ±1 bps.
- Claim nits in RESULTS:
  - "filled orders cost −1 to +1.8 bps" should be −0.6 to +1.8 (APE captures 2.55).
  - "more of them go unfilled" is false for SOL (95%), OP (93%) and ETC (92%), which fill at or above BTC/ETH (90/92%).
  - bookTicker floor moves are "< 6%", not "< 5%".
  - The size table is 2 days in 2023–24, i.e. before the 2025–26 tick-bound period. It is not representative of 2026 books.
- The impact check is on others' orders. Aggressive orders cluster in time and some are informed, and an order's first fill can print before the bookTicker update. Small orders on 4 of 6 assets show effective > quoted spread (e.g. ADA <$1k 1.91 vs 1.61 quoted), which suggests the reference mid is slightly stale. That biases the size table up modestly, which is the conservative direction for a cost estimate.
- Commit everything: all of p05 plus the harness and test diffs are still uncommitted.

### What the evidence supports (unchanged, with additions)
- Round-1 conclusions hold. No decision-table number changed with the tick-floor fix: the decision uses maker T=5 and pre-OOS months, where the floor mostly doesn't bind.
- **New, usable:** for 2026 the cost table implies top-of-book taker costs of 9–9.5 bps on OP, DOT, GMT and APE. A realistic size (≥ $10k) adds 2–4 bps on normal books and >15 bps on UNFI-class books. BTC and ETH taker cost is ~5.0 bps flat, and their top depth is > $100k.

### Proposed next experiment (kept, two amendments)
Same hypothesis, change and plan as in round 1: a daily cross-sectional positioning ranking of the p04 perps, top/bottom-3, no grid, pre-OOS only, and 0 OOS trials unless the pre-OOS kill passes. Amendments driven by the fixed table:
- **Asset-specific kill.** Keep "portfolio pre-OOS breakeven < 15 bps → abandon". Add: "or breakeven < 2× the turnover-weighted `TableCostModel(kind="taker")` cost plus the $10–50k impact bucket for the assets actually traded". The reason: in 2025–26 the tick-bound alts cost 9+ bps top-of-book, so a flat 15 bps is not 2× for them. Fix the order size in PLAN.md (e.g. $10k per leg).
- **Decision time.** The cost table is built from 04–16 UTC grid posts. In proxy months, 00:00 posts were dropped. 00:00 UTC is also a funding settlement, when spreads may be wider. Either decide at a measured grid time (e.g. 04:00 UTC, delay = 1), or accept that 00:00 costs are unmeasured and state it in PLAN.
- Prerequisite: fix the `_cost_matrix` gap bug and add its test before any backtest uses `{asset: TableCostModel}`.
- Kill criterion otherwise unchanged: gross SR t < 2 pre-OOS → abandon. Expected cost: 0–1 OOS trials; compute is small.
