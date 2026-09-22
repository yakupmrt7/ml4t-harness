# p02 positioning: hysteresis instead of sign + smooth

**Verdict: nothing tradable, and positioning alone cannot fix it.** On the
same OOS predictions as p01, hysteresis halves turnover (4,884 → 2,419 per
year) and raises breakeven from 0.68 to **1.07 bps**. That is a 58% gain, but
it costs 27% of gross Sharpe (1.04 → 0.76). Net Sharpe is still **-1.01 at
maker cost** and -3.11 at taker cost, with DSR 0.000. The gross timing edge
is weaker than p01's against the shifted null (p = 0.120 vs 0.053). Even
before OOS, no config in the grid broke even at maker cost: the best
in-sample breakeven was 1.35 bps against a 2.5 bps cost.

Trial #2 in `trials.json` (`p02_hysteresis`, maker-cost backtest). The 32
grid runs are in `selection_trials.json`; they never touched OOS. Run with
`python research/p02_positioning/run.py`. Full numbers are in
`results.json` and the raw output is in `run.log`. A `--no-log` re-run
reproduced `results.json` byte for byte.

## Setup
| | |
|---|---|
| Unchanged from p01 | data, `basic_features`, triple-barrier H=12 labels, `default_model`, uniqueness weights, costs, delay=1 |
| OOS predictions | `research/p01_baseline/preds.parquet` with no refit. validation_report refits for its null tests; the script asserts that its predictions equal p01's bit for bit, and they did |
| The one change | `hysteresis_position(p, theta_in, theta_out, min_hold)`: enter beyond 0.5±θin, exit to flat at 0.5±θout, hold ≥ min_hold bars after any change. Positions are {-1, 0, +1}. Bars with no prediction (65 in OOS) hold the current position |
| Selection data | label t0 < 2024-04-07 only (2022-09-01 → 2024-04-06, 1.60 years, 168,192 labels, **effective n 17,141**). Predictions come from `PurgedKFold(5, embargo_frac=0.01)`, AUC 0.545 |
| Selection rule | max net Sharpe at maker cost (2+0.5 bps) over θin ∈ {.01,.02,.03,.05} × θout ∈ {0, θin/2} × min_hold ∈ {1,6,12,24} |
| Selected | **θin = 0.05, θout = 0, min_hold = 24** (2 hours) |
| OOS | 2024-04-07 → 2026-08-31 (877 days, **Sharpe s.e. ≈ 0.64**), run once |

**Maker vs taker cost.** A *taker* order crosses the spread and executes
immediately at about 5 bps fee plus slippage. A *maker* order rests a limit
order in the book and waits to be hit, which is cheaper (about 2 bps at
Binance VIP0). The maker numbers here are an **optimistic bound**. They
assume every limit order fills at the bar close price, one bar after the
decision. In reality some orders never fill because price moves away. The
ones that do fill are disproportionately the ones where price comes toward
you and keeps going (adverse selection). Neither effect is modelled.

## validation_report verdict: taker (5 + 0.5 bps)
```
  OOS span                877 days (annualised Sharpe s.e. ~0.6)
  OOS AUC                 +0.528
  Sharpe gross / net      +0.757 / -3.113
  permuted labels         AUC +0.501, Sharpe +0.226 ± 0.46
  shift-null p (gross)    0.120
  PSR(net SR > 0)         0.000   breakeven cost 1.07 bps/turnover
  purge probe AUC         naive +0.575 vs purged +0.538
  Sharpe by delay (net)   d=1: -3.11, d=2: -3.13, d=3: -3.17
  Sharpe by delay (gross) d=1: +0.76, d=2: +0.74, d=3: +0.74
  Sharpe by cost (bps)    0:+0.76, 1:+0.05, 2:-0.65, 4:-2.06, 6:-3.46, 8:-4.85, 12:-7.59
  [PASS] no lookahead-looking features
  [PASS] not implausibly good (gross Sharpe < 4.0)
  [PASS] pipeline clean (permuted labels -> AUC~0.5, Sharpe~0)
  [FAIL] timing edge beats shifted nulls (gross, p<0.05)
  [FAIL] net Sharpe > 0 with PSR > 0.95
  [PASS] gross edge survives 1 extra bar (d=2 keeps >50% of d=1)
```

## validation_report verdict: maker (2 + 0.5 bps)
```
  OOS span                877 days (annualised Sharpe s.e. ~0.6)
  OOS AUC                 +0.528
  Sharpe gross / net      +0.757 / -1.006
  permuted labels         AUC +0.501, Sharpe +0.226 ± 0.46
  shift-null p (gross)    0.120
  PSR(net SR > 0)         0.059   breakeven cost 1.07 bps/turnover
  purge probe AUC         naive +0.575 vs purged +0.538
  Sharpe by delay (net)   d=1: -1.01, d=2: -1.02, d=3: -1.04
  Sharpe by delay (gross) d=1: +0.76, d=2: +0.74, d=3: +0.74
  Sharpe by cost (bps)    0:+0.76, 1:+0.05, 2:-0.65, 4:-2.06, 6:-3.46, 8:-4.85, 12:-7.59
  [PASS] no lookahead-looking features
  [PASS] not implausibly good (gross Sharpe < 4.0)
  [PASS] pipeline clean (permuted labels -> AUC~0.5, Sharpe~0)
  [FAIL] timing edge beats shifted nulls (gross, p<0.05)
  [FAIL] net Sharpe > 0 with PSR > 0.95
  [PASS] gross edge survives 1 extra bar (d=2 keeps >50% of d=1)
```

## vs p01 (same OOS predictions)
| | p01 (sign, 0.02, smooth 12) | p02 (hysteresis .05 / 0 / 24) |
|---|---:|---:|
| Gross Sharpe | +1.04 | +0.76 |
| Net Sharpe, taker | -7.39 | -3.11 |
| Net Sharpe, maker | -2.79 | -1.01 |
| PSR / DSR (maker) | n/a | 0.059 / 0.000 (n_trials = 2) |
| Turnover / yr | 4,884 | 2,419 |
| Breakeven (bps per unit turnover) | 0.68 | 1.07 |
| Exposure | 93% | 45% |
| Avg holding time | 2.0 h | 3.3 h |
| Shift-null p (gross) | 0.053 | 0.120 |
| Max drawdown (maker) | n/a | -68% |

Avg holding time = 2 × Σ\|position\| / turnover, which is the mean life of
one unit of position. It is defined the same way for the continuous p01
positions and the discrete p02 ones. p01's maker Sharpe comes from its
predictions at 2+0.5 bps and is reporting only, not a new trial. Funding is
not included in either column; p01 measured it as negligible (+0.26%/yr).

## Selection grid (pre-OOS, PurgedKFold predictions)
Sorted by the selection metric. The p01 rule is shown for reference only and
was not a candidate.

| config | gross SR | net SR maker | net SR taker | turnover/yr | breakeven bps | exposure | avg hold h |
|---|---:|---:|---:|---:|---:|---:|---:|
| **in=0.05 out=0.0 hold=24** (selected) | +0.82 | -1.21 | -3.63 | 3,120 | 1.01 | 54% | 3.0 |
| in=0.02 out=0.0 hold=24 | +1.22 | -1.30 | -4.30 | 4,211 | 1.21 | 70% | 2.9 |
| in=0.02 out=0.01 hold=24 | +1.16 | -1.44 | -4.55 | 4,310 | 1.11 | 65% | 2.6 |
| in=0.05 out=0.025 hold=12 | +2.03 | -1.72 | -6.20 | 5,361 | 1.35 | 45% | 1.5 |
| in=0.03 out=0.0 hold=24 | +0.50 | -1.82 | -4.59 | 3,816 | 0.54 | 64% | 2.9 |
| in=0.05 out=0.025 hold=24 | +0.43 | -1.88 | -4.65 | 3,445 | 0.46 | 48% | 2.4 |
| in=0.05 out=0.0 hold=12 | +0.86 | -2.06 | -5.55 | 4,486 | 0.74 | 55% | 2.1 |
| in=0.05 out=0.0 hold=1 | +1.76 | -2.26 | -7.06 | 6,538 | 1.09 | 57% | 1.5 |
| in=0.05 out=0.0 hold=6 | +1.09 | -2.32 | -6.39 | 5,462 | 0.80 | 56% | 1.8 |
| in=0.01 out=0.005 hold=24 | +0.05 | -2.64 | -5.85 | 4,710 | 0.05 | 74% | 2.7 |
| in=0.01 out=0.0 hold=24 | -0.07 | -2.73 | -5.89 | 4,764 | -0.07 | 79% | 2.9 |
| in=0.03 out=0.0 hold=12 | +0.72 | -2.75 | -6.88 | 5,925 | 0.52 | 68% | 2.0 |
| in=0.02 out=0.0 hold=12 | +1.06 | -2.80 | -7.40 | 6,723 | 0.69 | 74% | 1.9 |
| *p01 rule (sign, 0.02, smooth 12)* (reference) | +0.89 | -2.91 | -7.46 | 5,313 | 0.59 | 96% | 2.0 |
| in=0.03 out=0.015 hold=24 | -0.40 | -2.96 | -6.02 | 4,052 | -0.38 | 59% | 2.6 |
| in=0.02 out=0.01 hold=12 | +1.27 | -3.01 | -8.11 | 7,178 | 0.74 | 68% | 1.7 |
| in=0.03 out=0.015 hold=12 | +0.95 | -3.15 | -8.02 | 6,649 | 0.58 | 61% | 1.6 |
| in=0.05 out=0.025 hold=6 | +1.59 | -3.32 | -9.16 | 6,974 | 0.81 | 44% | 1.1 |
| in=0.03 out=0.0 hold=6 | +1.27 | -3.33 | -8.81 | 7,967 | 0.69 | 71% | 1.6 |
| in=0.01 out=0.0 hold=12 | +0.81 | -3.47 | -8.54 | 7,803 | 0.47 | 82% | 1.9 |
| in=0.01 out=0.005 hold=12 | +0.68 | -3.70 | -8.90 | 7,768 | 0.39 | 77% | 1.7 |
| in=0.03 out=0.015 hold=6 | +1.70 | -4.03 | -10.84 | 9,488 | 0.74 | 62% | 1.2 |
| in=0.02 out=0.0 hold=6 | +1.09 | -4.10 | -10.25 | 9,278 | 0.52 | 78% | 1.5 |
| in=0.03 out=0.0 hold=1 | +1.99 | -4.24 | -11.64 | 11,082 | 0.80 | 75% | 1.2 |
| in=0.05 out=0.025 hold=1 | +2.21 | -4.40 | -12.23 | 9,661 | 0.83 | 43% | 0.8 |
| in=0.02 out=0.01 hold=6 | +1.32 | -4.75 | -11.93 | 10,440 | 0.54 | 71% | 1.2 |
| in=0.01 out=0.0 hold=6 | +1.09 | -4.83 | -11.83 | 11,007 | 0.46 | 86% | 1.4 |
| in=0.01 out=0.005 hold=6 | +1.18 | -5.15 | -12.62 | 11,442 | 0.46 | 81% | 1.2 |
| in=0.02 out=0.0 hold=1 | +2.13 | -5.78 | -15.13 | 14,607 | 0.67 | 84% | 1.0 |
| in=0.03 out=0.015 hold=1 | +2.22 | -6.90 | -17.66 | 15,367 | 0.61 | 64% | 0.7 |
| in=0.01 out=0.0 hold=1 | +1.89 | -8.31 | -20.28 | 19,577 | 0.46 | 92% | 0.8 |
| in=0.02 out=0.01 hold=1 | +2.14 | -8.46 | -20.96 | 18,926 | 0.50 | 76% | 0.7 |
| in=0.01 out=0.005 hold=1 | +1.81 | -10.27 | -24.42 | 22,781 | 0.37 | 88% | 0.7 |

## Reading it
- **The positioning change did what it was meant to do, but not by enough.**
  Hysteresis removes trades where p just wiggles around the threshold, and
  breakeven per unit of turnover rises 58%. The trade-off is that part of the
  model's signal is thrown away: gross Sharpe falls from 1.04 to 0.76, and the
  timing edge against shifted nulls weakens from p = 0.053 to 0.120.
  Exposure also halves, so the book is flat more than half the time.
- **The grid shows the ceiling before OOS was touched.** Across all 32
  configs, breakeven ranges from -0.38 to 1.35 bps. Cost at maker is 2.5 bps.
  To break even, the model needs about 1.9× more edge per unit traded than the
  best in-sample config, and 2.3× more than the OOS result. No mapping from
  these predictions to positions provides that.
- **The selection is noisy.** The selection segment is 1.6 years, so the
  in-sample Sharpe s.e. is about 0.8. The top three configs are within 0.25
  Sharpe of each other, so their ranking is mostly noise. The winner is also
  at a corner of the grid (largest θin, longest hold), so the in-sample
  optimum may lie outside it. However, gross Sharpe at hold=24 ranges from
  -0.40 to +1.22 depending on the thresholds, with no clean trend, and the
  best in-sample breakeven (1.35 bps) is far from 2.5. Extending the grid is
  unlikely to close that gap.
- **The PurgedKFold selection predictions are more optimistic than
  walk-forward** (AUC 0.545 vs 0.528 OOS), because each fold trains on data
  both before and after the block. That is acceptable for ranking positioning
  rules against each other, but it is why the selected config's in-sample
  gross Sharpe (0.82) does not transfer one-to-one to OOS (0.76).
- The delay verdict passes again (gross 0.76 → 0.74 → 0.74 at d=1/2/3), but
  as in p01 this is persistence of an edge that is not significant.

## Next (each is a new logged trial)
The gap is edge per trade, not trade count. Positioning has done its part,
so the next levers are on the prediction side:
- **Longer horizon.** Cost per trade is fixed while the typical move grows
  roughly with √H. Labels at H = 48 (4h) or 288 (1d) give each trade a larger
  move to overcome the same 2.5–5.5 bps. This needs its own WalkForward run,
  so it is a new trial.
- **Features that carry information price bars don't.** Candidates are
  funding rate, open interest, the perp–spot basis, and order-book imbalance
  from the collector (since 2026-07-25, so too short for OOS on its own).
- Any choice between these should be made on the pre-OOS segment, as here.

## Add-on: per-fold and long/short split
Added later. This is reporting only: no trial and no refit.
`addon_folds.py` rebuilds the selected p02 backtest from p01's
`preds.parquet`, checks that it reproduces the gross Sharpe above exactly,
and writes `addon_folds.json`. Folds are p01's 8 WalkForward test blocks.

| fold | span | gross SR | net SR maker | exposure | BTC over fold |
|---:|---|---:|---:|---:|---:|
| 1 | 2024-04-07 → 2024-07-25 | +2.23 | +0.08 | 51% | -5% |
| 2 | 2024-07-25 → 2024-11-12 | +1.44 | -0.42 | 52% | +31% |
| 3 | 2024-11-12 → 2025-03-02 | -0.41 | -1.99 | 50% | -0% |
| 4 | 2025-03-02 → 2025-06-19 | +3.37 | +1.48 | 43% | +22% |
| 5 | 2025-06-19 → 2025-10-07 | +0.79 | -1.77 | 40% | +18% |
| 6 | 2025-10-07 → 2026-01-24 | +0.79 | -0.67 | 43% | -28% |
| 7 | 2026-01-24 → 2026-05-14 | -1.54 | -3.00 | 42% | -11% |
| 8 | 2026-05-14 → 2026-08-31 | -0.72 | -2.45 | 40% | -1% |

Each fold is about 110 days, so the per-fold Sharpe s.e. is about 1.8.
Individual folds tell you little. The pattern does: gross Sharpe is positive
in 5 of 8 folds, and the most recent two (2026) are both negative. Whatever
edge the model had does not look stable.

| leg | share of bars | gross P&L (sum of bar returns) | per year | hit rate |
|---|---:|---:|---:|---:|
| long | 28% | +48.5% | +20.2% | 50.9% |
| short | 17% | +13.8% | +5.7% | 51.3% |
| total | 45% | +62.3% | +25.9% | |

BTC buy-and-hold over the OOS period was +13%. The long leg earns 78% of
gross P&L. Market drift explains only a few points of that (about 28%
exposure × 13%), so it is mostly timing rather than beta. The short leg is
positive but small.
