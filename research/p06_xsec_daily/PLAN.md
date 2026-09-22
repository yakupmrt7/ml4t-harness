# p06 cross-sectional daily sorts on the 15 p04 perps

Written 2026-09-22, before any factor data was downloaded or loaded for this
experiment. The funding files are already on disk from p04, but this
experiment has not read them. Nothing below changes after pre-OOS numbers
are seen.

## Why
p01–p05 showed that 5m bar-close mean reversion earns 0.3–6 bps per trade
against a measured cost of 2.6–6.7 bps maker and 5–7 bps taker (7–21 bps at
$10–50k). p05's REVIEW (round 2) proposes moving to a horizon where the move
per trade is large compared with the cost: one decision a day, ranking the
15 perps against each other.

## Hypothesis (falsifiable)
At least one of four standard crypto cross-sectional factors, sorted daily
and traded dollar-neutral, has a pre-OOS gross Sharpe t ≥ 2 and a
breakeven ≥ 2× its own measured trading cost. Falsified if none of the
four does.

## Single change vs p05/p04
There is no model. Four pre-registered single-factor sorts replace the
LightGBM pipeline. Horizon: 1 day instead of 4 h. Costs: p05's measured
table plus size impact, replacing the assumed 5 + 0.5 bps.

## Universe and data
- The 15 perps of p04 (`research/p04_multiasset/universe.json`), point-in-time.
  MATIC and UNFI delist inside the OOS period only, so pre-OOS all 15 are
  live.
- 5m perp klines (p04 cache), settled funding rates (archive, already
  downloaded), and 5m **premiumIndexKlines** for all 15, to be downloaded
  for **2022-06 → 2024-04 only**. Nothing from after the pre-OOS window is
  downloaded or loaded for the signals.
- **Pre-OOS window:** decisions on 2022-08-01 → 2024-03-31 (608 days);
  P&L up to 2024-04-01 04:00 UTC. The OOS period would start 2024-04-07,
  as in p01–p04.

## Decision rule (fixed)
- One decision per day at the close of the 5m bar ending **04:00 UTC**,
  which is a time on p05's measured cost grid. Positions are held for 24 h
  until the next decision.
- **delay = 1:** the target set at the 04:00 close is held from the next
  bar, as in `run_backtest`.
- **Rank** the live assets with a non-missing factor value. **Long the 3
  best and short the 3 worst**, equal notional: weight ±1 per asset, where
  1 unit = $10k per leg. Dollar-neutral, 6 positions, $60k gross. Ties are
  broken by symbol order.
- Assets not in the top 3 or bottom 3 are flat. A position that stays in
  its leg is not traded; only changes in weight trade.

## Factors (exactly these four, signs fixed)
Every value uses data up to the 04:00 close at most. Funding and premium
are strict as-of joins, as in p03.

| # | name | definition at decision time t (04:00 UTC) | long |
|---|---|---|---|
| 1 | carry | sum of the last 9 **settled** funding rates stamped strictly before t (≈ 3 days) | **lowest** (longs are paid, or pay least) |
| 2 | basis change | mean premium index over the 12 bars ending at t, minus the same mean ending at t − 24h | **lowest** (premium fell; contrarian to crowding into longs) |
| 3 | 1-day reversal | close(t) / close(t − 24h) − 1 | **lowest** (yesterday's losers) |
| 4 | momentum | close(t − 24h) / close(t − 28d) − 1 (skips the last day) | **highest** (winners) |

## Costs and P&L (fixed)
- **Trading cost per unit traded** = p05's `taker_all_in_bps` for that asset
  and month (`data/bars/costs.parquet`: fee + quoted half-spread,
  tick-floored), **plus a constant per-asset impact add-on**. The add-on =
  effective half-spread of $10–50k taker orders minus the quoted
  half-spread at order times, from `research/p05_costs/impact_check.py`
  on its 2 bookTicker days (2023-06-10, 2024-01-10).
  - p05 measured 6 assets; **the same script, days and definitions are run
    for the other 9 before any factor data is loaded.**
  - The add-on is floored at 0.
- Funding P&L: longs pay positive funding, using the weight held into
  each settlement, as in `run_backtest`.
- **gross = price P&L + funding P&L.** Funding is part of a perp position's
  return, and for carry it is the point. Price-only P&L is reported too.
  **net = gross − trading costs.**
- **Breakeven** = Σ gross / Σ |Δw| (bps per unit traded). **Traded cost** =
  the |Δw|-weighted mean of the per-bar cost actually charged.

## Pre-OOS report (per factor)
- Gross and net Sharpe, computed on daily P&L summed over 24 h windows,
  annualised by √365.
- **t = daily gross SR × √(n days).**
- Turnover (units per year), breakeven vs traded cost.
- Long-leg and short-leg gross.
- Per-year gross/net Sharpe: 2022-08→12, 2023, 2024-Q1.
- Price-only vs funding share of gross.
- Mean cross-sectional rank correlation between factors, for information.

Each factor counts as one selection trial: **4 rows in
`selection_trials.json`**, whatever the outcome. `trials.json` is not
touched.

## Kill criterion (fixed now)
A factor **passes** only if **t ≥ 2 AND breakeven ≥ 2 × its traded cost**.
- If none passes: STOP, write RESULTS.md, no OOS.
- If one or more pass: propose **one** combination (the equal-weight
  average of the passing factors' cross-sectional ranks, same top-3 /
  bottom-3 rule), write it down, and stop at the OOS gate for the owner's
  "go". There is no further selection.

Note on multiple testing: with 4 factors tried, the chance that at least
one reaches t ≥ 2 by luck is about 4 × 2.3% ≈ 9%. The breakeven condition
and the OOS gate are what guard against that. The threshold is not
corrected.

## Harness (minimal)
- `TableCostModel(..., add_bps=0.0)`: a constant add-on, for the impact
  term.
- `portfolio.funding_pnl(held, funding)`: funding charge per asset on the
  portfolio grid, with the same arithmetic as `run_backtest`.
- Both get unit tests. Run tests + selftest.
