# p13 — Hyperliquid liquidation event study on history: KILLED at kill 2 (economics)

**Verdict: the forced-flow thesis, in its pre-registered form, is dead on dev.** After a forced
liquidation on Hyperliquid, the price does not come back by more than the round-trip cost of trading
it. For the median window the reversion is +0.4 / +0.7 / +2.1 bps at 60 / 120 / 300 s against a median
cost of 9.8 bps, and the mean is about zero (−0.5 / −0.6 / +0.2 bps), so there is no gross edge even
before costs. Ranked by the liquidated size known at entry, every decile is flat at +1 to +2.5 bps
(300 s), the largest included (+2.3 vs a 9.5 bps cost). Per ROADMAP §4 and
PLAN.md the line closes here and the collector is not built. No trial (event study); holdout
(2026-06-11 → 2026-09-25) not read.

Plan and definitions: `PLAN.md` (incl. the step 2 addendum fixed before any book was read, commit
b0eee85). Step 0: `STEP0.md`. Step 1: `STEP1.md`. Step 2 code: `windows.py`, `book_windows.py` (box),
`step2.py` (box + local stages); numbers: `step2.json`, `step2.log`.

## Data (dev: 2025-07-27 08:00 → 2026-06-11 02:00 UTC)
- Events: market-method liquidations from `node_fills_by_block` (step 1; validated 187/187 vs the API).
- Windows: one per (60 s cluster across the six coins, coin): **47,270** defined; **43,592** have book
  data; 3,678 have none: two gaps of the book archive (2025-10-16 12:00 → 10-22 and 2025-11-17 13:00 →
  11-25, `NoSuchKey` on S3) for 3,565 of them, the other 113 in thin-book hours elsewhere (fewer than
  10 snapshots in the window; top days 2025-11-16, 2026-01-05); **39,079** have ≤ 2 s book gaps everywhere in [t0 − 60 s, t0 + 302 s]
  (the pre-registered main set); 4,513 with slower books are reported apart.
- **Independence:** the 39,079 windows fall in **21,109 clusters** (a cluster = liquidations with no
  gap > 60 s across all six coins; a multi-coin cluster is one bootstrap draw), spread over an
  **effective 221 equally-weighted days**. Confidence intervals below resample clusters.
- Books: `hyperliquid-archive` l2Book (20 levels, ~0.5 s in dev) for the 18,119 coin-hours touched by
  any window, reduced on arbscan-tokyo. Vol: 1 s last-trade returns from our tick tape. External
  reference: Binance spot 1 s closes (no HYPE).

## Kill 2 (pre-registered): median reversion vs median round-trip cost, $10k clip, taker both ways

Entry at the book mid 2 s after the first liquidation of the window; reversion = move back against
the liquidation's push, bps. Cost = (VWAP buy $10k − VWAP sell $10k)/mid at entry + 2 × 4.5 bps fee.

| set | windows / clusters | cost p50 | rev 60 s p50 [95% CI] | rev 120 s | rev 300 s | share of windows with rev 300 s > cost |
|---|---|---:|---|---|---|---:|
| all, 0.5 s books | 39,079 / 21,109 | 9.78 | +0.40 [+0.24, +0.52] | +0.72 [+0.51, +0.94] | +2.05 [+1.68, +2.38] | 36% |
| top decile, **registered** (≥ $758k liquidated in the window; look-ahead, see below) | 3,908 / 2,782 | 9.41 | −8.80 [−9.44, −8.32] | −12.93 [−13.93, −12.25] | −13.71 [−15.18, −11.93] | 20% |

**KILLED:** median reversion < median cost at all three horizons in both sets. The median of
per-window net (reversion − cost) is −9.6 / −9.3 / −8.1 bps (all) and −18.7 / −22.8 / −23.3 bps (top).
Means are lower than medians (all windows: −0.5 / −0.6 / +0.2 bps): the tail goes against the trade;
at 300 s p25 / p75 are about −15 / +19 bps (many small gains, a few large losses, per the review).

**Registered cost variants** (all windows, medians): exit-time book 9.81–9.82 bps; $50k clip 10.55 bps;
maker exit (taker in, maker out; optimistic, approximated as the entry half of spread + impact +
4.5 + 1.5 bps) **6.39 bps**. The median reversion (≤ 2.05 bps) is below every variant.

### The registered top decile is look-ahead; the causal version is also killed
A window's registered size is the total liquidated notional of its cluster, which includes
liquidations after entry. In the registered top decile the median window has only **1%** of its
notional known at t0 + 2 s, so its −8.8 / −12.9 / −13.7 bps "continuation" is selection on the outcome
(the price kept moving, so more accounts were liquidated). Ranked instead by notional known at entry
(`causal_size.py`, `causal_size.json`; post hoc, reported as a robustness check, not a new test):

| decile by $ known at entry | known $ | rev 60 s | rev 120 s | rev 300 s | cost |
|---|---|---:|---:|---:|---:|
| 0 | 0–62 | −0.09 | +0.07 | +0.98 | 10.03 |
| 2 | 205–509 | +0.44 | +0.65 | +2.27 | 9.93 |
| 5 | 2.3k–4.8k | +0.40 | +0.40 | +2.26 | 9.77 |
| 7 | 11k–28k | +0.90 | +1.11 | +2.53 | 9.69 |
| 8 | 28k–72k | +0.54 | +1.18 | +2.17 | 9.59 |
| **9** | **≥ 72k** (3,908 windows / 3,228 clusters) | **+1.36** | **+1.63** | **+2.30** | **9.48** |

Flat across size, and far below cost at every horizon. Direction s was also taken from the whole
window; computed from liquidations known at t0 + 2 s it agrees in 99.3% of windows and gives
+0.44 / +0.77 / +2.10 bps (review), so direction look-ahead is negligible.

## Downsample check (owner, 2026-09-26): the same study on 5 s books (today's live cadence)

| set | cost p50 | rev 5 s | rev 60 s | rev 120 s | rev 300 s |
|---|---:|---:|---:|---:|---:|
| all, 5 s | 9.88 | −0.89 | −0.76 [−0.90, −0.64] | −0.54 | +0.50 [+0.17, +0.84] |
| top decile, 5 s | 9.45 | −2.59 | −10.76 | −15.48 | −16.34 |

Also killed (the top-decile row carries the same look-ahead as above). At 5 s the small positive
reversion of the 0.5 s study turns negative up to 120 s, but this measures a *stale observed mid*, not
a stale fill: a real order fills at the live price, and the liquidation trigger comes from the trade
stream, which the book cadence does not slow. So the check shows the reversion is small enough to be
swamped by 5 s staleness in the measurement; it does not by itself show a 5 s trader could not reach
the 0.5 s numbers. It does not change the verdict: those 0.5 s numbers are below cost anyway.

## What the events look like (0.5 s books, by decile of liquidated notional in the window)

Deciles below are by **registered (whole-window) size**, so the size axis carries the look-ahead
described above; the pre-move, depth and spread columns do not depend on outcomes after entry.

| decile | liquidated $ | rev 60 s | rev 300 s | rev 60 s in σ units | move in the 60 s **before** t0 | depth left (min / pre) | refill | spread pre → max 30 s |
|---|---|---:|---:|---:|---:|---:|---:|---|
| 0 | 0–178 | +2.8 | +4.3 | +0.32 | +9.1 | 0.42 | 32 s | 0.34 → 2.49 |
| 3 | 2.7k–7.3k | +2.4 | +4.8 | +0.26 | +14.3 | 0.36 | 29 s | 0.36 → 2.80 |
| 5 | 19k–42k | +0.7 | +3.6 | +0.08 | +14.7 | 0.29 | 30 s | 0.33 → 2.86 |
| 7 | 92k–226k | −1.7 | +0.5 | −0.19 | +15.6 | 0.20 | 29 s | 0.27 → 3.06 |
| 8 | 226k–758k | −4.3 | −3.2 | −0.49 | +15.1 | 0.13 | 30 s | 0.23 → 2.98 |
| 9 | 758k–253M | −8.8 | −13.7 | −0.99 | +14.8 | 0.06 | 33 s | 0.16 → 3.00 |

(all deciles in `step2.json`; costs 9.4–10.1 bps in every decile.)

- **Most of the move is over before the first liquidation prints:** the price moved 9–16 bps in the
  push direction in the preceding 60 s, which is what put these accounts under water in the first
  place (liquidations trigger on the mark, which lags). The book-side reaction after t0 is small next
  to it.
- **Book depletion and refill (descriptive, no placebo):** depth on the absorbing side (within 50 bps,
  in practice capped by the 20 visible levels) falls to 6–42% of its pre-event median and is back to 90%
  in ~30 s (median) in every decile; spreads widen from ~0.3 to ~3 bps for a few seconds. Even decile 0
  ($0–178 liquidated) shows depth falling to 42%, so much of this is ordinary book flicker around a
  moving price rather than the liquidation itself; without a matched non-event baseline these numbers
  do not isolate an event effect.
- **The size pattern in the registered deciles (small revert a little, large "continue") is an artefact
  of the look-ahead size axis**; by size known at entry, all deciles are flat (table above).
- **By coin:** no coin clears cost (rev 300 s p50: BTC +1.4, ETH +2.4, SOL +2.8, XRP +1.9, HYPE +0.8,
  ZEC +8.0 vs ZEC's cost 14.6).

## Cross-venue: does HL dislocate from the external price?
HL book mid vs Binance spot 1 s close, de-meaned on [t0 − 60, t0 − 5] s, signed so > 0 = HL pushed
further than Binance (32,057 windows with a Binance pair): peak **+3.3 bps median** (p90 9.8), reached
~25 s after t0, back within 2 bps ~26 s later; 18% do not come back within the window. The dislocation
grows with size (decile 0: 2.6 bps, decile 9: 4.4 bps) but stays below the ~10 bps round trip. Binance
spot approximates the 5-venue perp median that drives HL's mark; the gap to the true mark is not measured.

## What survives, and what does not
- Dead, as tested: fading HL liquidations with a **taker entry 2 s after the first liquidation print,
  $10k clip, fixed exits at 60 / 120 / 300 s**, on 0.5 s books (and on 5 s books, with the caveat above),
  for all events and for the largest by size known at entry. Median gross reversion ≤ 2.3 bps against
  ≥ 6.4 bps for even the optimistic maker-exit cost; mean gross reversion ≈ 0.
- Not tested: sub-2 s entry, passive entries (resting bids below visible clusters, i.e. the ROADMAP
  stage 3 "passive" rule, with queue position in a depleting book), exhaustion-timed entries. The
  review's prior on these is low, and they must not be tried on this dev span, which has now been read.
- Stage 0's map question is moot for this thesis: seeing the levels in advance does not help if
  trading against the forced flow loses ~8–23 bps per round trip after costs.

## Infrastructure and teardown
- AWS spend for p13: fill-archive reads same-region (~10k GET, < $0.01); book archive cross-region
  18,119 files ≈ 22 GB ≈ $0.45; box → laptop egress ≈ 8.3 GB fills + small step 2 outputs ≈ $1.
- Created for p13: IAM role + instance profile `p13-hl-archive-read` (read-only on
  `hl-mainnet-node-data` and `hyperliquid-archive`), attached to `arbscan-tokyo`; `~/p13` on the box
  (venv, `books/` 1.6 GB, step 2 outputs); `lz4` and `python3-venv` via apt; SSH rule on `arbscan-sg`
  now allows only 46.196.164.48/32. **Teardown (2026-09-26, after the review):** IAM instance profile
disassociated from `arbscan-tokyo`; role policy, role and instance profile `p13-hl-archive-read`
deleted (`get-role` → NoSuchEntity); `~/p13` deleted on the box (disk back to 14 GB used). Left in
place: the apt packages `lz4`, `python3-venv` (harmless, no cost) and the instance itself, which hosts
the owner's arbscan work and bills while running (~$2.5/day). Its state is the owner's call, not p13's.

## Validation-report note
CLAUDE.md rule 8 (`validation_report`) applies to strategy results with a return series; this is an
event study with a pre-registered kill and no strategy, so there is no verdict block to paste. No
trial is logged and no threshold was changed.
