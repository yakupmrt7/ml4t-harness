# p07 does the p06 momentum sort replicate on untouched history?

Written 2026-09-23, before any 2020-01 → 2022-05 data was downloaded or
loaded. It follows research/p06_xsec_daily/REVIEW.md, "Proposed next
experiment", as written there. Nothing below changes after numbers are seen.

## Hypothesis (falsifiable)
The 28d/skip-1 cross-sectional momentum sort, with p06's book frozen, has a
positive gross Sharpe on **2020-10-01 → 2022-07-31**. No experiment in this
repo has read this window. (p06 read 2022-06/07 closes, but only as warm-up
for its first momentum values. No P&L from before 2022-08-01 04:00 was ever
computed.) Falsified if this window's gross Sharpe is ≤ 0.

## Single change vs p06
One variable changes: the sample. The factor, its sign, the 04:00 UTC
decision, delay = 1, 3 long / 3 short, ±1 unit ($10k) per leg,
equal-notional and dollar-neutral, the daily bucketing and the 15-perp
universe are all p06's. The other three p06 factors are dropped.
**No free parameters. Nothing is chosen on the new window.**

## Data
- 5m USD-M perp klines + settled funding for the 15 p04 perps,
  **2020-01 → 2022-07**, from `scripts/download_binance.py`. Assets listed
  later than 2020-01 just have fewer files. Caches:
  `data/bars/{SYM}-5m-2020-01_2022-07.parquet`.
- The p06 window is recomputed from the existing
  `data/bars/{SYM}-5m-2022-06_2026-08.parquet` caches, cut at
  2024-04-01 04:00 as in p06. Nothing after that is read.

## Book (frozen from p06)
- Decision at the 04:00 UTC 5m close, daily. Held 24 h. delay = 1.
- momentum(t) = close(t − 24h) / close(t − 28d) − 1, using exact 5m bars.
  An asset is **live** at t if the factor is not missing, i.e. its bars at
  t − 24h and t − 28d both exist (p06's code; the bar at t itself is not
  checked). Listing dates are not otherwise used.
- Long the 3 highest, short the 3 lowest, weight ±1, ties by symbol.
  Only changes in weight trade.
- **Require ≥ 8 live.** On a day with fewer than 8 live, the book is flat
  and that day is **dropped** from the sample (not counted as a zero). There
  are no delistings among the 15 before 2022-08, so this mostly trims the start
  of the window (a missing 5m bar can also drop a day). Dropped days are counted and reported.
- The decision grid for the new window is 2020-10-01 04:00 → 2022-07-31
  04:00, with P&L to 2022-08-01 04:00. p06's first decision is 2022-08-01
  04:00, so the two windows neither overlap nor leave a gap.
- **Daily sample:** bucket d = bars in (d 04:00, d+1 04:00], one per
  decision day. p06's empty stub bucket (the grid's first bar, held = 0) is
  dropped, so the p06 window has 609 days here, not 610. Its review showed
  this moves SR 0.950 → 0.951.
- gross = price P&L + funding P&L (longs pay positive funding), as in p06.

## Costs (fixed)
**A flat 12 bps per unit traded**, in both windows and pooled, for the net
leg only. p05's cost table does NOT cover pre-2022-08 and is not
extrapolated backwards. 12 bps sits above every 2022-24 measured value
(8.8–9.0) to allow for wider 2020-21 spreads. No new cost table is built
unless the gate passes.

## Windows and pooling
Each window runs as its own backtest and starts flat, so the p06 window
reproduces p06. **Pooled** = the two daily gross series concatenated
(≈ 1,278 days), with turnover summed.
- Pooled breakeven = Σ gross / Σ turnover. Its s.e. = std(daily gross) ·
  √n / Σ turnover, as in p06's follow-ups.
- t = daily SR · √n. Newey-West(10) t is reported alongside.

## What each sample can show (stated before running)
t = SR_ann · √(n/365). The gross Sharpe needed for **t = 2**:

| sample | days (approx.) | 1 s.e. of SR | SR for t = 2 | SR for t = 1.5 |
|---|---:|---:|---:|---:|
| 2020-10 → 2022-07 | 669 (fewer if < 8 live early) | 0.74 | **1.48** | 1.11 |
| 2022-08 → 2024-03 (p06) | 609 | 0.77 | **1.55** | 1.16 |
| pooled | ≈ 1,278 | 0.53 | **1.07** | 0.80 |

What this means for reading the result:
- **Neither window alone can reach t = 2** unless its Sharpe is ~1.5. That is
  why the gate uses the pooled t, and asks only SR ≥ 0.5 per window.
- p06's window gave 0.95. If the pooled Sharpe is about the day-weighted
  average of the two windows (roughly true only if the two windows have
  similar daily vol, and 2021 was more volatile), the new window needs about
  **1.2** for the pooled t to reach 2.
- A true Sharpe of 0.8, which is a good factor, gives an expected pooled t
  of 1.5. So there is a real chance of landing in "underpowered, not dead"
  even if the factor is real. That outcome gets reported as such. It is
  not a reason to relax anything.
- The p06 window is not a clean sample for momentum. Momentum was the best
  of four p06 factors on the net/breakeven leg, so its p06 number carries
  selection bias. **The new window is the clean test.** The kill is
  therefore on the new window alone, and the gate requires both.
- Pooled breakeven: p06's was 21.0 ± 17.1 bps. The pooled s.e. will be about
  12 bps, so "breakeven − 1 s.e. ≥ 12" needs a pooled breakeven of about
  24+ bps.

## Pre-OOS report
For the new window, the p06 window and pooled:
- gross SR ± 1/√years, t, NW(10) t, net SR at 12 bps, price-only SR
- breakeven ± s.e., turnover (units/yr)
- beta of the daily gross to the equal-weight live-universe return, and
  the beta-hedged SR
- per-year gross SR: 2020-Q4, 2021, 2022-01→07 | 2022-08→12, 2023, 2024-Q1
- `portfolio_shift_null` p-value (gross, 300 draws) per window
- live-asset count over time, days dropped for < 8 live

**DIAGNOSTIC only. Not part of the kill, and not the book being tested:**
the same momentum signal with **rank-demeaned weights over all live
assets**: w_i ∝ rank_i − mean(rank), scaled so Σ|w| = 6 (same $60k gross
as 3v3), same ≥ 8-live rule, both windows and pooled: gross SR, t,
breakeven ± s.e. It exists to show how much power breadth would add. It
cannot open the gate or substitute for the 3v3 result.

## Kill criterion (fixed now)
- **KILL** (abandon daily cross-sectional momentum) if the 2020-10 → 2022-07
  gross SR ≤ 0 **or** its breakeven < 12 bps.
- **Go to the OOS gate** only if **both** windows have gross SR ≥ +0.5
  **and** pooled t ≥ 2.0 **and** pooled breakeven − 1 s.e. ≥ 12 bps.
- **Underpowered, not dead:** not killed, both windows' SR > 0, and pooled
  t in [1.5, 2.0). Report it as such and STOP. The only allowed follow-up is
  more breadth, never a new threshold.
- Anything else (not killed, gate not met, not in the underpowered band):
  STOP, report as a fail on the gate.

Bookkeeping: **one row in `selection_trials.json`**, whatever the outcome.
`trials.json` is not touched. Stop at the gate.
