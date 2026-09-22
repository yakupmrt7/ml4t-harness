# Review: p04_multiasset
**Decision:** ACCEPT WITH FIXES (the kill is accepted; RESULTS.md needs edits before commit)
**One line:** The pooled 15-perp book breaks even at 2.51 bps pre-OOS, which is below the pre-registered 3.5 line. The arithmetic is correct. Most of the shortfall comes from one PurgedKFold block (Aug–Nov 2022), and the rest is 1.9–3.3 bps in 3 of the other 4 blocks. No OOS run and no trial were used.

## Is 2.51 bps real? (bug check)
I recomputed it independently from `preds_selection.parquet` with my own latch and backtest, without using `harness/portfolio.py`:
- Portfolio breakeven is **2.511 bps** and gross SR is **1.79**, which matches selection.log. The 15 per-asset unscaled breakevens match the table.
- Turnover definition: Σ|Δheld| on the risk-scaled /15 weights, in the same units as the gross P&L. That is consistent. The equal-notional 3.84 bps equals the plain mean of the 15 per-asset breakevens (3.83), as it should when turnover is equal.
- risk_scale latching: the scale is set at every change of position, including flips, and uses ewm_vol at t, which is causal. The exit trades the latched size. Correct.
- Per-asset hysteresis reindexing: preds cover every pre-OOS bar per asset (n_preds ≈ 177k = 1.68 y of 5m bars). NaN holds the position. Per-asset AUCs are ~0.52–0.54, so preds are aligned to the right asset.
- Pooled PurgedKFold: the purge uses the t0 time level across assets, so rows with the same t0 on either side of a block boundary are purged through the t1 ≥ test_start test. The embargo is ceil(1% of rows). Rows are nearly uniform across assets pre-OOS, so that is ≈1% of time. Correct.
- Labels and features: built per asset, trailing windows only. The ret/σ normalisation uses ewm_vol up to and including bar t. The vol z-score is rolling and trailing. The lookahead audit is clean on all 15 assets. No leak found.

The kill was not caused by a bug.

## Blocking issues
None for the kill itself. The following must be fixed in RESULTS.md before commit:
1. **The "why the breakeven is low" section attributes the shortfall to the equal-risk sizing. Time matters as much.** I split the same preds by PurgedKFold block, post hoc and as a diagnostic only:

   | block | span | portfolio BE bps | gross SR |
   |---|---|---:|---:|
   | 1 | 2022-08-01 → 2022-12-01 | −2.20 | −1.25 |
   | 2 | 2022-12 → 2023-04 | 3.34 | 2.24 |
   | 3 | 2023-04 → 2023-08 | 3.28 | 2.39 |
   | 4 | 2023-08 → 2023-12 | 1.88 | 1.89 |
   | 5 | 2023-12 → 2024-04 | 6.43 | 4.14 |

   Block 1 covers the Aug–Nov 2022 bear market and the FTX collapse. In that block, mean reversion lost money on 10 of 15 assets. It is also the one block whose model was trained only on later data. On p03's window (from 2022-12-15) the portfolio breakeven is 3.66 bps. That is barely over the line, and it is pre-walk-forward and cherry-picked. 3 of 5 blocks are below 3.5, so the kill holds either way. Say that the edge is regime-dependent, and do not present sizing as the main cause.
2. **The BTC vs p03 sentence "pooling did not carry p03's BTC result over" is confounded.** On p03's window, the pooled model's BTC row is BE 1.80 bps / gross SR 0.87. On the added Aug–Dec 2022 months it is −4.46 bps. Most of the 0.34 vs 3.66 gap comes from the window, not from pooling or normalisation. Also, p03's 3.66 uses sign positions and its 4.70 is the full model, so neither is basic-only with hysteresis. Replace the sentence with this decomposition (labelled post hoc), or delete it.
3. **"Generality: supported (15/15 AUC > 0.5, 15/15 SR > 0)."** The 15 rows come from one pooled model and the same test blocks, with ρ̄ = 0.22. They are not 15 independent tests. Each row's SR s.e. is ≈ 0.77, and PurgedKFold is optimistic (for p03 BTC, AUC was 0.545 PKF vs 0.528 walk-forward). Reword to "consistent with, pre-OOS".
4. **"Diversification: supported, scales as √(effective N)."** This is close to a tautology. ρ̄ is measured on the same P&L being aggregated. The comparison uses a risk-scaled portfolio SR (1.79 ± 0.77) against a mean of unscaled single-asset SRs. A 1.76× vs 1.91× match with s.e. 0.77 on the numerator tests nothing. Reword to "consistent with".
5. **Market note, "alt half-spreads typically 1–5 bps".** No data is cited. The direction is plausible: thin alt books have wider spreads than BTC and ETH. The number is unmeasured, so either mark it as an assumption or measure it. Also add that the gross edge **survives delay = 2** (portfolio BE 2.61 bps, gross SR 1.88; per-asset d=2 SRs are about the same as d=1). That rules out one-bar bid-ask bounce as the source of the alt edge. It does not rule out spread cost.
6. Commit the harness changes, tests, selection.py/common.py/selection.* and RESULTS.md together. They are all uncommitted now, and PLAN.md is the only thing that proves pre-registration.

## Non-blocking issues
- **Selection hygiene is clean.** PLAN.md (75830ee) predates the modelling and has not been changed since. selection_trials.json has exactly 2 rows (one run, 17:13 and 17:14). trials.json still has 3 entries. The asset-id rule was applied as written: gain +0.00192 < 0.002, so the id was excluded, even though the id variant was better on every metric. It also fails the kill (2.77 bps). No loosening: the equal-notional 3.84 is correctly labelled as not a p04 result.
- The kill was evaluated on a block (block 1) where PurgedKFold predicts 2022 using only 2023–24 training data. This was part of the pre-registered design, so it is not a reason to override the kill. Keep it in mind when reading any PKF number.
- p03's hysteresis (0.05/0.025/48) was tuned on BTC-only probabilities. The pooled model is less dispersed: exposure is 44% here vs p03's 62%. This was pre-registered, not an error.
- `run_portfolio_backtest` has no funding and silently ignores `CostModel.include_funding`. run.py adds funding separately. Either raise on include_funding=True or document it in the signature. A mean-reversion book systematically shorts after rallies, when funding is most positive, so alt funding is not negligible the way it was for BTC in p03.
- `portfolio_shift_null`: shifted weights that land on non-live bars are dropped. For delisted assets the null therefore has less exposure than the actual book. That is minor, but in OOS it biases the null slightly. Add a test with a delisted asset.
- `portfolio_validation_report`: thresholds are unchanged (the verdicts() refactor is a pure move, confirmed in the diff). The permutation test permutes labels across assets and time, which is fine. `purge_probe` on MultiIndex runs through the same pooled PurgedKFold, which is fine. Tests pass (29/29).
- One CostModel for all assets. Any future multi-asset work needs a per-asset cost vector (measured, not assumed) before a portfolio breakeven means anything.

## What the evidence supports
- The 2.51 bps pre-OOS breakeven is arithmetically correct, and the kill was applied as pre-registered.
- Scale-free price/volume mean reversion gives a small pooled AUC (0.526 PKF) on liquid perps. Gross P&L is positive in 4 of 5 time blocks and strongly negative in the Aug–Nov 2022 crash block.
- Per unit of notional, the edge is larger on higher-vol alts (4–6 bps unscaled) than on BTC/ETH (0.3–0.6 bps over the full window, ~2 bps from 2022-12). The alts are also where the uniform 5.5/2.5 bps cost model is least credible.
- The book is roughly market-neutral (net exposure −0.02, long/short legs 52/48), so it is not beta.
- The edge survives delay = 2, so it is not a one-bar microstructure artefact.
- It is not supported that pooling adds bps per trade. It adds Sharpe, and the costs are driven by bps.

## Line status
p01 (1h), p02 (hysteresis), p03 (4h + positioning) and p04 (pooled alts) all hit the same wall. Per-trade edge is 0.7 → 1.1 → 2.5 bps on OOS and 2.5 bps pre-OOS here, against 2.5 bps maker (optimistic) and 5.5 bps taker. That is 4 consecutive experiments on "5m bar-close mean reversion from price/volume features" that failed tradability. **Stop adding features, assets or sizing schemes to this line.** Also skip p03's proposed basic-only BTC ablation. It would spend a trial on attribution, and it cannot pass net because p03 already breaks even at 2.5 bps.

## Proposed next experiment (p05: measure the cost wall instead of the edge)
The remaining unknown that decides whether any of this is tradable is the true maker cost: fee plus adverse selection, plus the orders that never fill and have to be crossed at taker. That cost is currently an assumed 2.5 bps. In market terms, a resting limit order fills mostly when price moves through it, i.e. against you. The 2 bps maker fee is a floor, not the cost.
- **Hypothesis:** On Binance BTCUSDT and ETHUSDT perps, passive execution of p03-style entries and exits (post at the best quote at the close of bar t, cross at taker if unfilled after k seconds) has an all-in cost ≤ 1.5 bps per unit traded, which would leave room under p03's 2.5 bps breakeven. Falsified if the cost is ≥ 2.5 bps.
- **Exact change:** no model change. Use the frozen p03 model's positions (no refit) on the collector period, 2026-07-25 → now, and replace the CostModel with a fill simulator built on the collector's order-book and trade streams. First inspect the collector schema, as CLAUDE.md asks, and write a loader with timestamp tests: exchange event time vs receive time, since snapshot vs publish-time lag is the leak risk.
- **Selection plan:** fix k (the maker timeout) and the markout horizon in PLAN.md before loading any collector data. No grid. If one is required, choose it on the first 2 weeks only and report on the rest.
- **Kill criterion (fixed in advance):** if the measured all-in maker cost is ≥ 2.5 bps per unit turnover (fee + mean 1-bar adverse markout on fills + taker cost × miss rate), abandon 5m bar-close mean reversion on Binance entirely. Pivot to data with a different information source (the collector's Polymarket/Chainlink streams) rather than more of the same features.
- **Expected cost:** 0 entries in trials.json, since no strategy Sharpe is claimed. Cost-measurement runs go in selection_trials.json. Compute is small: ~2 months of L2/trade data for 2 symbols. Harness work is `data` (collector loader) plus `backtest` (fill simulator) with unit tests and selftest.
