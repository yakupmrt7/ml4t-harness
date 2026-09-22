# p04 multi-asset: is the p03 edge generic mean reversion across liquid perps?

Written 2026-09-22, before any modelling. Nothing below may change after
pre-OOS numbers are seen, except where a rule says "decided on pre-OOS".

## Hypothesis
The p03 gross edge is short-to-medium-horizon mean reversion from basic
price/volume features, not something BTC-specific. If so:
- the same fixed pipeline has a pooled AUC above 0.5 and a positive gross
  Sharpe on most liquid USD-M perps, not just BTC;
- pooling raises portfolio gross Sharpe by roughly √(effective N), where
  effective N = N / (1 + (N−1)·ρ̄) and ρ̄ = average pairwise correlation of
  per-asset gross P&L;
- cost per unit of turnover does not change, so the per-trade breakeven
  stays about where it was per asset. Pooling improves Sharpe, not bps per trade.

Falsified if pooled pre-OOS AUC < 0.52 or portfolio breakeven < 3.5 bps
(the kill criterion below), or on OOS if the portfolio gross edge fails the
shift null.

## Single change vs p03
One asset → a fixed 15-perp universe with one pooled model and a
risk-budgeted portfolio. p03's positioning features are dropped, since p03
showed they add nothing. Everything else is p03's config, fixed, with no
re-selection:

| | |
|---|---|
| Features | `basic_features` (15), made scale-free per asset (below) |
| Labels | triple barrier, H = 48, pt = sl = 1 × `ewm_vol(288)`·√H, per asset |
| Model | `default_model` (LightGBM), one pooled model across all assets |
| Weights | `average_uniqueness`, computed per asset on its own bar grid |
| Positions | `hysteresis_position` θin 0.05, θout 0.025, min_hold 48, per asset |
| CV | pre-OOS: PurgedKFold(5, 0.01) pooled. OOS: WalkForward(8), first test row at p01's OOS start 2024-04-07 09:15 |
| Costs | taker 5 + 0.5 bps, maker 2 + 0.5 bps, delay = 1 (d = 2 as robustness) |

## Universe (point-in-time, no survivorship)
Produced by `universe.py` (reproducible, no returns used). Out of 1,018
archived USD-M symbols, 967 are perps and **170 have a 5m file for 2022-06**.
Those 170 are ranked by total quote volume over 2022-07. Stable-vs-stable
pairs are excluded (none in the top ranks). **One contract per underlying**
(owner's decision): the highest-volume contract is kept, which removes
BTCBUSD and ETHBUSD. The universe is the top 15. BTCUSDT is rank 1. The full
ranking is in `universe_ranking.csv`.

| rank | symbol | quote vol 2022-07 ($bn) | status |
|---:|---|---:|---|
| 1 | BTCUSDT | 441.9 | IN |
| 2 | ETHUSDT | 282.6 | IN |
| 3 | BTCBUSD | 78.5 | excluded: duplicate underlying |
| 4 | ETHBUSD | 49.6 | excluded: duplicate underlying |
| 5 | ETCUSDT | 35.0 | IN |
| 6 | SOLUSDT | 33.4 | IN |
| 7 | MATICUSDT | 27.8 | IN (delisted, see below) |
| 8 | GMTUSDT | 21.1 | IN |
| 9 | AVAXUSDT | 14.7 | IN |
| 10 | ADAUSDT | 13.8 | IN |
| 11 | BNBUSDT | 13.4 | IN |
| 12 | APEUSDT | 12.3 | IN |
| 13 | SANDUSDT | 11.5 | IN |
| 14 | OPUSDT | 10.2 | IN (first bar 2022-06-01 14:05) |
| 15 | UNFIUSDT | 9.7 | IN (delisted, see below) |
| 16 | XRPUSDT | 9.4 | IN |
| 17 | DOTUSDT | 8.3 | IN |
| 18 | NEARUSDT | 7.8 | first one out |
| 19 | DYDXUSDT | 7.7 | |
| 20 | 1000SHIBUSDT | 7.6 | |

**Delistings and migrations.** A migration counts as a delisting: the
position goes flat after the original symbol's last bar, with no splicing of
the successor ticker. The date is the **last 5m bar with trade count > 0**.
The archive pads both dead symbols with zero-trade bars at a frozen price, and
for UNFI these run to 2026-08, so the file list alone would get this wrong.

| symbol | last live bar (close time, UTC) | what happened | archive runs to |
|---|---|---|---|
| MATICUSDT | 2024-09-04 09:00 | migration MATIC → POL (POLUSDT is **not** spliced in) | 2024-09-11 09:45 (zero-trade padding) |
| UNFIUSDT | 2024-10-30 09:05 | delisted | 2026-09-01 (zero-trade padding) |

Both happen inside the OOS period, and none happen pre-OOS. The OOS portfolio
has 15 assets until 2024-09-04, 14 until 2024-10-30, then 13. Each asset's
series is cut at its last live bar. Its target is forced to 0 at that bar,
so the exit fills at its last traded close and pays normal costs. This is
mildly optimistic: Binance announces delistings days ahead, and spreads
widen before the end.

## Data window
- 5m perp klines 2022-06-01 → 2026-09-01 for all 15, sha256-checked. There
  are no missing bars. About 24 zero-trade bars per symbol come from exchange
  maintenance windows shared across symbols; their returns are 0.
- June–July 2022 is warm-up only, for the 30-day z-scores. **Labels start
  2022-08-01**, after the ranking month, so the month that picked the
  universe is not trained on.
- Pre-OOS = label t0 **and** t1 < 2024-04-07 00:00 (same as p03).
  OOS = 2024-04-07 09:15 → 2026-09-01 (same period as p01–p03).

## Per-asset normalisation (fixed now, no selection)
`basic_features` gives 15 columns, and some are in asset-specific units.
They are transformed per asset with trailing windows only:
- `ret_{1,6,12,48,288}` → `ret_w / (ewm_vol(288)·√w)`. The vol is the same
  one that sets the label barrier width, so returns are in barrier units.
- `vol_48`, `vol_288` → z-score of log vol over the trailing 30 days (8,640
  bars, min_periods 90%).
- Already scale-free, unchanged: `zret_48`, `zret_288`, `vol_ratio`,
  `vlm_z`, `taker_imb_1`, `taker_imb_12`, `hour_sin`, `hour_cos`.

## Pooling and purging
Rows are (t0, asset), sorted by t0. The splitters work on the t0 **time**
of every row, whatever the asset: a PurgedKFold test block excludes any
training row, **from any asset**, whose [t0, t1] overlaps the block's
[first t0, last t1]. WalkForward trains only on rows (any asset) with
t1 < the test block's first t0. The embargo drops the first
ceil(1% · rows) rows after a block, about 1% of the time span. Unit tests
check this with several assets.

## Asset-id feature (decided on pre-OOS, rule fixed now)
One-hot asset id (15 columns), added only if, on pre-OOS PurgedKFold, it
raises the pooled AUC by **≥ 0.002** AND raises the portfolio gross Sharpe.
Otherwise it is left out. Both runs go into selection_trials.json. This is
the only choice made in p04.

## Portfolio
- Per asset: discrete hysteresis position p ∈ {−1, 0, +1}.
- Equal risk budget: w = p · min(3, σ* / σ_t) / 15, with σ_t = annualised
  `ewm_vol(288)` of that asset and σ* = 50%/yr. The scale is **latched when
  the position changes** and held until the next change. Re-scaling every
  bar would add turnover from vol drift alone. The /15 is fixed, so a
  delisting does not resize the other assets.
- Portfolio P&L = sum of per-asset net P&L. Breakeven = Σ gross / Σ |Δw|
  (bps per unit of traded notional).
- Per-asset table rows use the **unscaled ±1** hysteresis positions, so that
  per-asset breakevens and the BTCUSDT row are comparable to p03.
- **Caveat on the BTCUSDT row as p03's "basic-only H=48" ablation.** It uses
  the same labels, hysteresis and costs, but the model is pooled and the
  features are normalised. It answers "does a BTC position from a model
  pooled on 15 perps do as well as p03?", which is close to, but not
  exactly, the ablation p03 proposed.
- **Market caveat.** One cost model for all assets is generous to the small
  alts. BTC/ETH perp half-spreads are well under 1 bp, but for names like
  GMT, APE or UNFI in 2022–24 they were often 1–5 bps. The per-asset
  breakeven column shows which assets would survive realistic alt
  slippage. The costs are not changed (rule 6).

## Harness extensions (minimal, with unit tests)
- `cv`: splitters accept a (t0, asset) MultiIndex and purge on the t0 level.
  Single-asset behaviour is unchanged.
- `features.scale_free_basic_features`: the normalisation above.
- `portfolio`: `risk_scale` (latched), `run_portfolio_backtest` (matches
  `run_backtest` exactly for one asset; delisted assets are flat from their
  last bar), `portfolio_shift_null` (all assets shifted by the **same**
  offset, which keeps the cross-asset correlation of positions), and
  `portfolio_validation_report` (the same verdicts as `validation_report`,
  with the verdict logic shared, not copied).

## Pre-OOS report (selection.py)
Pooled PurgedKFold AUC; per-asset AUC, gross Sharpe, breakeven and
turnover; portfolio gross, net-maker and net-taker Sharpe, breakeven and
turnover; average pairwise correlation of per-asset gross P&L (daily) and
effective N; lookahead audit on every asset.

## Kill criterion (fixed now)
**STOP without running OOS if pooled pre-OOS AUC < 0.52 or portfolio pre-OOS
breakeven < 3.5 bps.** It is evaluated on the final pre-OOS config, after
the asset-id decision.

## OOS (only after the owner's explicit "go")
One run, one trial `p04_multiasset_H48` (maker-cost portfolio backtest, as
in p03), DSR with n_trials = 4. Report:
- portfolio verdict blocks at taker and maker cost;
- the per-asset table (AUC, gross Sharpe, breakeven, turnover), with the
  BTCUSDT row compared directly to p03;
- ρ̄ and effective N;
- per-fold portfolio Sharpe and the long/short split.
