# ml4t-harness

ML trading research on crypto (BTC first) with a validation harness that has
to be able to say "there is nothing here". Owner is strong at ML and new to
finance: explain market-specific reasoning (costs, microstructure, funding)
when it comes up, and skip ML basics.

## Commands
- `pip install -e ".[dev]"`: install
- `python tests/test_core.py` (or `pytest -q`): unit tests. Run after ANY change in `harness/`.
- `python selftest.py`: must end with `HARNESS OK`. Run after changes to labeling, cv, backtest, metrics or nulls.
- `python scripts/download_binance.py --interval 5m --start 2022-01 --end 2026-08`: free history into data/raw

## Layout
- `harness/`: library code (labels, weights, cv, backtest, metrics, nulls, features, data)
- `research/pNN_<name>/`: one folder per experiment (script or notebook + short RESULTS.md)
- `data/raw` = Binance archive zips, `data/collector` = slices synced from the GCS collector, `data/bars` = parquet caches. All gitignored.
- `trials.json`: the trial log. Committed. Never delete or edit its entries.

## Non-negotiable rules
1. **Causality.** A feature at bar t may use data up to the close of bar t only. Trailing windows only, never `center=True` or `shift(-k)` in features. Bars are indexed by CLOSE time.
2. **No delay=0.** Backtests use delay>=1. Report delay=2 as a robustness check.
3. **Evaluate out of sample with WalkForward.** PurgedKFold is for model selection only. Never use sklearn's shuffled KFold/train_test_split on labels.
4. **Log every trial** that touched the backtest period with `TrialLog.log(...)`, failures included. Report DSR alongside Sharpe.
5. **Never loosen a null test or verdict threshold to make a result pass.** If a result fails, report that it failed.
6. **Costs are always on.** Default CostModel(fee_bps=5, slippage_bps=0.5) for taker. Report the breakeven cost too.
7. Report effective n (sum of uniqueness), not the raw label count, and the annualised Sharpe standard error (~1/sqrt(years)).
8. A result is claimed only after `validation_report` has been run on it. Paste its verdict block into RESULTS.md.

## Data notes
- Binance archive klines: close_time is ms before 2025 and us after; `load_binance_klines` handles both.
- Collector (GCS, europe-west3): Polymarket CLOB, Binance spot/futures websockets and Chainlink, since 2026-07-25. The schema is not documented here yet, so ask or inspect a file before writing loaders.
