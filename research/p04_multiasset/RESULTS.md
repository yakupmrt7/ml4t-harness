# p04 multi-asset: 15 liquid perps, one pooled model, H = 4h

**Verdict: KILLED before OOS.** Pre-OOS portfolio breakeven is **2.51 bps**,
below the 3.5 bps kill line fixed in PLAN.md. Pooled pre-OOS AUC is 0.526
(line: 0.52), so only the breakeven condition fails. No OOS run, no trial in
`trials.json` (still 3 trials). The asset-id variant (not selected, see
below) also fails, at 2.77 bps.

What we learned:
- **Consistent with a generic, not BTC-specific, signal.** Every asset's
  AUC is above 0.5 (0.517–0.540) and every asset's gross Sharpe is above 0.
  These are not 15 independent confirmations: it is one pooled model scored
  on the same test blocks, and the assets' P&L correlates at ρ̄ ≈ 0.22. The
  edge per trade is largest on the higher-vol alts (4–6 bps on ±1
  positions). BTC and ETH, where the backtest's costs are most realistic,
  are at 0.3 and 0.6 bps.
- **Consistent with diversification.** ρ̄ of daily gross P&L is 0.22,
  which gives effective N ≈ 3.6 of 15. Portfolio gross Sharpe is 1.79 against
  a mean single-asset 1.02. That is roughly the √3.6 ≈ 1.9× predicted, but
  it is a weak test: ρ̄ is measured on the same P&L that is being combined,
  the portfolio is risk-scaled while the single-asset figures are not, and
  the portfolio Sharpe s.e. is about 0.77.
- **Two things pull the breakeven down, and neither is the whole story:**
  - *Time.* Aug–Nov 2022, which includes the FTX crash, is −2.20 bps, with
    10 of 15 assets losing. The four later PurgedKFold blocks are 3.34,
    3.28, 1.88 and 6.40 bps. On p03's window (from 2022-12-15) the
    portfolio breakeven is 3.66 bps, and that is still before the
    PurgedKFold → walk-forward drop.
  - *Sizing.* Equal risk sizes the low-vol, low-edge names (BTC, ETH, BNB)
    up; they take 30% of turnover and give 6% of gross P&L.

  Three of the five blocks are below 3.5 bps, so the kill does not hinge on
  either factor.
- **Not bid-ask bounce.** At delay = 2 the portfolio keeps its gross edge:
  breakeven 2.61 bps, gross SR 1.87 (vs 2.51 and 1.79 at d = 1).

All numbers are pre-OOS PurgedKFold, which trains on both sides of each test
block and is optimistic. For BTC in p03 the gap was AUC 0.545 pre-OOS vs
0.528 walk-forward.

Reproduce (from the repo root):
- `python research/p04_multiasset/universe.py` (universe, no returns used)
- `PYTHONPATH=. python research/p04_multiasset/selection.py` (pre-OOS only)

`run.py` is the OOS script prepared for the gate. It was **never run**.

## Setup
| | |
|---|---|
| Universe | Top 15 USD-M perps by 2022-07 quote volume, from the 170 with a 2022-06 file; one contract per underlying (see PLAN.md) |
| Delistings | MATICUSDT last bar 2024-09-04 09:00 (→ POL, not spliced); UNFIUSDT 2024-10-30 09:05. Both fall after the pre-OOS window |
| Features | `scale_free_basic_features` (15): returns in ewm_vol(288)·√w units, 30-day z-scored log vol, the rest unchanged |
| Labels | triple barrier H = 48, pt = sl = 1 × ewm_vol(288)·√H, per asset |
| Model / weights | `default_model`, pooled; `average_uniqueness` per asset |
| CV | PurgedKFold(5, 0.01) on the pooled (t0, asset) rows; purge and embargo on time across all assets |
| Positions | hysteresis 0.05 / 0.025 / 48 per asset; weight = pos · min(3, 0.5/σ_t) / 15, latched at entry |
| Pre-OOS | label t0, t1 ∈ [2022-08-01, 2024-04-07): **2,656,211 labels, effective n 73,541** (sum over assets; the assets are correlated, so the truly independent count is lower). 1.68 years, portfolio Sharpe s.e. ≈ 0.77 |
| Costs | taker 5 + 0.5, maker 2 + 0.5 bps, delay = 1 |

The lookahead audit (every feature, every asset, pre-OOS) found no suspects.
The max |IC with the next bar| is 0.065, on BTCUSDT.

## Asset-id decision (the only choice in p04)
Rule fixed in PLAN.md: include the one-hot asset id iff it raises pooled AUC
by ≥ 0.002 **and** raises portfolio gross Sharpe.

| | AUC | gross SR | net SR maker | net SR taker | breakeven bps | turnover/yr |
|---|---:|---:|---:|---:|---:|---:|
| **no asset id (chosen)** | 0.5256 | +1.79 | +0.01 | −2.14 | **2.51** | 1,473 |
| asset id | 0.5275 | +2.04 | +0.20 | −2.00 | 2.77 | 1,456 |

AUC gain is +0.0019, just under 0.002, so the id is left out. The rule
stands. Both variants are below 3.5 bps, so the kill does not depend on this
call. Both rows are in `selection_trials.json`.

## Kill check
```
KILL CHECK: pooled AUC 0.5256 (min 0.52), breakeven 2.51 bps (min 3.5)  =>  KILLED: do not run OOS
```

## Per asset (pre-OOS, unscaled ±1 hysteresis, as in p03)
| asset | AUC | gross SR | net SR maker | net SR taker | breakeven bps | turnover/yr | exposure |
|---|---:|---:|---:|---:|---:|---:|---:|
| BTCUSDT | 0.526 | +0.16 | −1.01 | −2.42 | 0.34 | 1,724 | 44% |
| ETHUSDT | 0.530 | +0.24 | −0.74 | −1.92 | 0.62 | 1,722 | 44% |
| ETCUSDT | 0.536 | +1.67 | +0.95 | +0.09 | 5.81 | 1,729 | 44% |
| SOLUSDT | 0.520 | +1.03 | +0.53 | −0.07 | 5.16 | 1,771 | 45% |
| MATICUSDT | 0.522 | +1.16 | +0.45 | −0.41 | 4.08 | 1,769 | 45% |
| GMTUSDT | 0.517 | +0.41 | −0.16 | −0.84 | 1.80 | 1,757 | 45% |
| AVAXUSDT | 0.523 | +1.32 | +0.65 | −0.15 | 4.94 | 1,759 | 45% |
| ADAUSDT | 0.528 | +1.64 | +0.84 | −0.12 | 5.12 | 1,755 | 44% |
| BNBUSDT | 0.530 | +0.82 | −0.23 | −1.48 | 1.96 | 1,752 | 45% |
| APEUSDT | 0.520 | +1.49 | +0.89 | +0.16 | 6.16 | 1,765 | 44% |
| SANDUSDT | 0.528 | +1.59 | +0.93 | +0.13 | 5.97 | 1,747 | 44% |
| OPUSDT | 0.517 | +1.27 | +0.77 | +0.17 | 6.32 | 1,747 | 44% |
| UNFIUSDT | 0.520 | +0.64 | +0.17 | −0.39 | 3.41 | 1,752 | 44% |
| XRPUSDT | 0.540 | +0.89 | +0.10 | −0.85 | 2.82 | 1,734 | 44% |
| DOTUSDT | 0.530 | +0.98 | +0.17 | −0.81 | 3.01 | 1,742 | 44% |

Per-asset Sharpe s.e. ≈ 0.77. No single row is significant; the pattern
across rows is the information.

**BTCUSDT vs p03 (pre-OOS, both PurgedKFold), a confounded comparison.**
Neither p03 pre-OOS figure matches this setup:
- the basic-only H=48 model (AUC 0.543, gross SR +2.31, 3.66 bps) used
  sign/threshold positions, not hysteresis;
- 4.70 bps with the same hysteresis was the full basic+positioning model.

The pooled model's BTC row is 0.526, +0.16 and 0.34 bps overall. But that
covers a longer window. On the four months p03 did not have (2022-08-01 →
2022-12-15), BTC is −4.46 bps (gross SR −1.90). On p03's window it is
**1.80 bps (gross SR +0.87)**. So the window explains much of the gap. What
remains (1.80 vs 3.7–4.7) mixes the effects of pooling, normalised features
and a different position rule. None of this is the OOS ablation p03
proposed, which remains unrun.

## Portfolio (pre-OOS)
| | value |
|---|---:|
| gross Sharpe | +1.79 (s.e. ≈ 0.77) |
| net Sharpe maker / taker | +0.01 / −2.14 |
| breakeven | **2.51 bps** per unit traded notional |
| turnover / yr (Σ\|Δw\|) | 1,473 |
| mean gross / net exposure | 0.37 / −0.02 |
| gross P&L from long / short legs | 52% / 48% |
| delay = 2: gross SR / breakeven | +1.87 / 2.61 bps |
| ρ̄ of per-asset gross P&L, daily (5m bars) | 0.223 (0.218) |
| effective N = N / (1 + (N−1)ρ̄) | 3.64 of 15 |
| mean single-asset gross SR (unscaled) | +1.02 → portfolio +1.79 (×1.76; √3.64 = 1.91; weak test, see top) |

**By PurgedKFold test block** (post-hoc split of the same predictions,
diagnostic only). Each block is predicted by a model trained on the other
four:

| block | span | gross SR | breakeven bps | assets with gross < 0 |
|---:|---|---:|---:|---:|
| 1 | 2022-08-01 → 2022-12-01 (FTX) | −1.25 | −2.20 | 10 / 15 |
| 2 | 2022-12-01 → 2023-04-03 | +2.24 | 3.34 | 4 / 15 |
| 3 | 2023-04-03 → 2023-08-04 | +2.39 | 3.28 | 1 / 15 |
| 4 | 2023-08-04 → 2023-12-05 | +1.89 | 1.88 | 4 / 15 |
| 5 | 2023-12-05 → 2024-04-06 | +4.13 | 6.40 | 2 / 15 |

The s.e. of a 4-month Sharpe is about 1.7.

The book is market-neutral in aggregate (net exposure −0.02) and makes money
about equally on both legs, so this is not beta.

## Sizing contribution to the low breakeven (diagnostic, not a selection)
Time is the other half; see the block table above. Decomposing the
risk-scaled portfolio by asset:

| asset | share of turnover | share of gross P&L | breakeven bps | mean ann. vol |
|---|---:|---:|---:|---:|
| BTCUSDT | 10.9% | 0.9% | 0.21 | 44% |
| BNBUSDT | 9.9% | 7.1% | 1.81 | 51% |
| ETHUSDT | 9.2% | −2.2% | −0.61 | 53% |
| … 12 alts | 70.0% | 94.2% | 1.1 – 6.2 | 68 – 114% |

Equal risk means weight ∝ 1/vol, so BTC, ETH and BNB get the biggest
notional and the most turnover, but they have the least edge per trade. For
reference only, an **equal-notional** book on the same predictions breaks
even at 3.84 bps (gross SR 1.93). That is not the pre-registered portfolio.
Switching to it after seeing the kill would loosen the result (rule 5), so it
is not a p04 result.

**Market note (why 3.84 would not be real either).** Breakeven is measured
per unit of notional traded. A signal that predicts moves in units of each
asset's own volatility (which is what the scale-free features and
vol-scaled barriers are built for) gives a bps edge roughly proportional
to that asset's vol. So the high-vol alts *look* better in bps. Their
trading costs also scale up, though. The backtest charges all 15 assets the
same 0.5 bps slippage. My working assumption, **not measured in this repo**,
is that half-spreads on APE, OP, GMT or UNFI perps in 2022–24 were
several bps, against well under 1 bp for BTC. If that is right, the alts'
4–6 bps breakevens are the most flattered numbers here. Measuring per-asset
spreads (e.g. from bookTicker archives or the collector) is needed before
any multi-asset result can be trusted.

## Reading it
- **Hypothesis, generality part: consistent pre-OOS, not proven.** One
  pooled model has AUC > 0.5 and gross SR > 0 on every asset. The rows are
  correlated and come from the same folds, and the gross edge disappears
  in Aug–Nov 2022.
- **Hypothesis, diversification part: consistent, weakly tested.** ρ̄ = 0.22;
  portfolio gross SR is 1.76× the mean single-asset SR, against the 1.91×
  that √(effective N) predicts.
- **Tradability: fails.** Per-trade edge is 2.5 bps at the pre-registered
  weights, before the PurgedKFold → walk-forward drop (for BTC in p03 about
  a third of the AUC edge). It is lower still once realistic alt spreads
  are counted. The binding constraint remains edge per trade versus cost,
  not Sharpe.
- **BTC specifically:** most of the gap to p03 is the added 2022-08 →
  2022-12 window (−4.46 bps there, 1.80 bps on p03's window). The rest
  cannot be separated from the pooling, feature and position-rule changes.

## Harness changes (tests + selftest pass)
- `cv`: splitters take a (t0, asset) MultiIndex and purge, embargo and
  walk forward on t0 time across all assets. Tests:
  `test_pooled_purged_kfold_purges_across_assets`,
  `test_pooled_walk_forward_strictly_past_across_assets`,
  `test_multiindex_single_asset_matches_plain`,
  `test_pooled_split_rejects_unsorted_time`.
- `features.scale_free_basic_features`: invariant to price and volume
  level, and prefix-invariant (causal).
- `portfolio`: `risk_scale` (latched), `run_portfolio_backtest` (matches
  `run_backtest` to 1e-15 for one asset; funding is not included, by design; a delisted asset exits at its last
  close, paying once), `portfolio_shift_null` (one offset for all assets;
  reproduces `circular_shift_null` exactly for identical assets; finds
  planted timing; consistent with the backtest when an asset delists. Shifted
  positions that land on unlisted bars are dropped, so the null carries a bit
  less exposure when assets delist), and `portfolio_validation_report` (verdict logic shared
  with `validation_report` through `nulls.verdicts`, with no threshold
  changed).
- `python tests/test_core.py`: 29/29 ok. `python selftest.py`: HARNESS OK.
