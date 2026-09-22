# p01 baseline: basic_features, 1h triple barrier, BTCUSDT perp 5m

**Verdict: nothing tradable.** The model shows a small classification skill
(AUC 0.528), but its gross timing edge does not beat the shifted-position
null (p = 0.053), and it breaks even only at 0.68 bps per unit of turnover.
Real taker cost is about 5.5 bps, so the net Sharpe is -7.4.

Trial #1 in `trials.json` (`baseline_5m_1h`). Run with
`python research/p01_baseline/run.py`. Full numbers are in `results.json`
and the raw output is in `run.log`.

## Setup
| | |
|---|---|
| Data | Binance USD-M perp BTCUSDT 5m klines (`data/raw`), label t0 in [2022-09-01, 2026-09-01). 2022-08 was loaded only as feature warm-up. 429,696 bars, 0 gaps |
| Features | `basic_features` (16 cols: returns 1..288, vol 48/288, z-ret, vol ratio, volume z, taker imbalance, hour sin/cos) |
| Labels | `triple_barrier`, H=12 (1h), pt=sl=1 x `ewm_vol(288)*sqrt(12)`. Barrier hit: vertical 68%, sl 16%, pt 16% |
| Sample size | 420,757 labels, **effective n = 43,596** (sum of uniqueness, ~9.7x overlap) |
| Model / weights | `default_model` (LightGBM), average-uniqueness sample weights |
| Evaluation | `WalkForward(8, 0.4)`. OOS is 2024-04-07 → 2026-08-31 (877 days, **Sharpe s.e. ≈ 0.64**) |
| Positions | sign(p-0.5) if \|p-0.5\|>0.02, averaged over the last 12 bars |
| Costs | `CostModel(fee_bps=5, slippage_bps=0.5)`, delay=1 |

## validation_report verdict
Refreshed after `3a30993` (the delay verdict now tests gross edge). This came
from an identical re-run with `--no-log`, and every other number matched the
original run exactly.
```
  OOS span                877 days (annualised Sharpe s.e. ~0.6)
  OOS AUC                 +0.528
  Sharpe gross / net      +1.038 / -7.389
  permuted labels         AUC +0.501, Sharpe -0.017 ± 0.68
  shift-null p (gross)    0.053
  PSR(net SR > 0)         0.000   breakeven cost 0.68 bps/turnover
  purge probe AUC         naive +0.575 vs purged +0.538
  Sharpe by delay (net)   d=1: -7.39, d=2: -7.53, d=3: -7.65
  Sharpe by delay (gross) d=1: +1.04, d=2: +0.89, d=3: +0.77
  Sharpe by cost (bps)    0:+1.04, 1:-0.50, 2:-2.03, 4:-5.09, 6:-8.15, 8:-11.21, 12:-17.32
  [PASS] no lookahead-looking features
  [PASS] not implausibly good (gross Sharpe < 4.0)
  [PASS] pipeline clean (permuted labels -> AUC~0.5, Sharpe~0)
  [FAIL] timing edge beats shifted nulls (gross, p<0.05)
  [FAIL] net Sharpe > 0 with PSR > 0.95
  [PASS] gross edge survives 1 extra bar (d=2 keeps >50% of d=1)
```

## Other numbers
| | |
|---|---|
| Sharpe net / DSR | -7.39 / 0.000 (n_trials=1, so DSR equals PSR. No deflation yet) |
| Breakeven cost | 0.68 bps per unit turnover |
| Turnover | 4,884x notional per year (≈13x per day) |
| Cost drag | 269% of notional per year |
| Exposure / mean \|pos\| / mean pos | 93% / 0.55 / +0.08 |
| Hit rate (active bars, gross) | 50.96% |
| Max drawdown (net) | -99.7% |
| Net Sharpe incl. funding | -7.38 (funding contributes +0.26%/yr, which is negligible because the book is close to flat on average) |

## Reading it
- **The pipeline is clean.** With permuted labels, AUC is 0.501 and the gross
  Sharpe is centred on 0. The lookahead audit is clean. The purge probe shows
  the expected overlap inflation: naive shuffled-KFold AUC is 0.575, while
  purged AUC is 0.538.
- **The model has a little classification skill, but no proven timing edge.**
  AUC 0.528 is well above the permuted 0.501. A gross Sharpe of +1.04 with
  s.e. 0.64 is only about 1.6σ, and the shifted-position null gives p = 0.053.
  Most of what the model "knows" is probably volatility/regime structure,
  which a shifted copy of the same positions also earns.
- **Costs decide the result.** The strategy trades about 13x its notional per
  day, which means holding each position for roughly 2 hours. It breaks even
  at 0.68 bps per unit of turnover. That is below the Binance VIP0 maker fee
  (about 2 bps) and far below taker cost (5 bps plus spread). One bp of cost
  is already enough to make it negative.
- **The gross edge that exists holds up under delay.** Gross Sharpe goes
  1.04 → 0.89 → 0.77 at d=1/2/3, so d=2 keeps 86%. Whatever the model picks
  up is unlikely to be bid-ask bounce. However, this is persistence of an edge that is
  not itself significant (shift-null p = 0.053), so on its own it is weak
  evidence.

## Next (each is a new logged trial)
The binding constraint is turnover relative to edge per trade. The obvious
levers are fewer, better-chosen bets (CUSUM events, a higher prob threshold,
longer H) and features that carry more information than price/volume bars.
Any selection among these must be done with PurgedKFold on the pre-OOS
segment, not by comparing WalkForward results.
