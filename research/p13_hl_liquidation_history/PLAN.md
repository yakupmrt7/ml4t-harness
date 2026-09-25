# p13_hl_liquidation_history — plan

Stage 2 of the forced-flow line (docs/ROADMAP.md §4), run on history before any collector is
built. Starts from p12's REVIEW.md proposal. No trial, nothing in `trials_hl.json`: this is an event
study, not a strategy. The holdout (below) is not read.

**Correction to the brief:** p12 did not *find* liquidations in the S3 archive. It found them
*documented* there (SURVEY.md §2c: "documented, not downloaded; archive start date and size
unknown"). Step 0 verifies this on one small file before anything else is built on it.

## Hypothesis (falsifiable)
Forced liquidations on Hyperliquid (BTC, ETH, SOL, HYPE, ZEC, XRP) are followed within 60–300 s by a
reversion of price back against the liquidation's direction, and the median reversion is larger than
the round-trip cost of trading it on HL.

## Change vs p12
Add a data source: the historical fill archive (`node_fills_by_block`) and, if affordable, the L2
book archive (`market_data`). Nothing else.

## Steps and stops
- **Step 0: price it (no bulk download).** List both prefixes with `--request-payer requester`.
  Report the date span, bytes per day, and GB and $ for (a) 3 months of fills and (b) BTC
  l2Book + asset_ctxs over the same span. Download **one** hour of fills (< $0.10) to verify the
  liquidation field exists and to learn the schema. **STOP and show the owner.** Nothing above
  ~$20 is downloaded without approval.
- **Step 1: event set.** Every fill carrying the `liquidation` field over the available span, for the
  six coins. Per coin: events/week, liquidated notional distribution, time clustering, method
  (market vs backstop), share in cascades. **STOP and show the event counts.**
- **Step 2: event study** (dev span only): price path −60 s…+300 s, move before the event, book
  depletion and refill, spread during the event, size deciles, HL mid vs external mark dislocation.

## Dev / holdout split
Fixed by calendar on the archive's span as listed in step 0, **before any fill is loaded**: first 75%
dev, last 25% holdout. **Fixed 2026-09-25 from the listing:** span 2025-07-27 08:00 → 2026-09-25 08:00
UTC (425 days); **dev = 2025-07-27 08:00 → 2026-06-11 02:00 UTC, holdout = 2026-06-11 02:00 →
2026-09-25 08:00 UTC.** Archive hours added after the listing are not part of either. Step 1 counts events over the full span (counts use no price outcomes, and
the count kill needs the full rate); step 2 reads price paths **on dev only**. The holdout is kept
for a later strategy test (ROADMAP stage 5). CLAUDE.md's HL split is defined on the collected span;
this archive split applies to archive-based work only, and is written into RESULTS.md when fixed.

## Definitions (fixed now)
- **Event:** one fill row with a non-null `liquidation` field, on the liquidated user's side.
  Fills of one liquidation order (same `hash`/order, same liquidated user) are merged into one event.
- **Independent event:** events are grouped into clusters, merged **across the six coins**, where a
  new cluster starts after a gap of **> 60 s** with no liquidation. One cluster = one independent
  event (it is one market shock). Sensitivity reported at 10 s and 300 s gaps; the kill uses 60 s.
- **Reversion (per cluster, per coin):** let t0 = time of the cluster's first liquidation fill and
  d = +1 if the liquidations were sells (longs liquidated), −1 if buys. Entry at the mid at
  t0 + 2 s (latency delay, per rule 2: delay ≥ 1). Reversion(h) = d × (mid(t0+2s+h) − mid(t0+2s)) /
  mid(t0+2s), in bps, for h ∈ {60, 120, 300} s. Positive = price came back. Also reported at +5 s.
  Mid source: L2 book archive if bought; otherwise the trade tape (last-trade proxy), stated as such.
- **Tradeable size:** a $10k–$50k clip, i.e. well inside the top 20 levels of the book for all six
  coins at normal times; the cost is measured at that size from the book at t0 + 2 s.
- **Cost ("spread plus fees"), round trip, taker in and out:** full spread at t0 + 2 s (half on entry,
  half on exit) + 2 × HL base-tier taker fee (4.5 bps, docs re-checked 2026-09-25; maker 1.5 bps) + impact at the
  clip size. Reported alongside: a maker-exit variant (taker + maker fee), which is optimistic.

## Kill criteria (fixed now, restated from the brief)
The line closes and the collector is not built if **either** holds:
1. **Power:** fewer than **~200 independent events per month** (60 s clusters, all six coins
   together, averaged over the span).
2. **Economics:** on dev, the **median reversion at tradeable size is smaller than the round-trip
   cost** above, at every horizon in {60, 120, 300} s, both for all clusters and for the top
   liquidated-notional decile. (If only the top decile clears cost, the line is re-scoped to large
   events and says so; it is not declared alive in general.)

Stage-0 carry-over: the map coverage question (p12) is secondary here. If the fill archive is bought,
the full address set is extracted and polled once, with BTC OI coverage and poll time reported next
to p12's numbers.

## Validation before building on the data (ROADMAP §8.6)
- Loader vs ground truth: HL `candleSnapshot` 1m closes vs the fill tape over the last 3.5 days
  overlapping the archive; and `userFills` liquidation records for a few archived liquidated
  addresses vs the archive rows.
- Timestamps: unit and timezone checked on the sample file; bars and events indexed by close/fill time.

## Expected cost
0 trials. S3 egress as priced in step 0 (approval needed above ~$20). Laptop compute.
