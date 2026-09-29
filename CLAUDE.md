# quant-research-harness

ML trading research on crypto (BTC first) with a validation harness that has
to be able to say "there is nothing here". Owner is strong at ML and new to
finance: explain market-specific reasoning (costs, microstructure, funding)
when it comes up, and skip ML basics.

**Current line (owner, 2026-09-29): none open. NEWPLAN.md #1 (p15), #2 (p16), #3 (p14 + p18) and
#4 (p17) are closed on dev; the HL forced-flow line (docs/ROADMAP.md) was killed at p13. The owner
reopened one test (2026-09-29): p19, BTC-only carry, which spent p14's holdout as trial #1 in
`trials_hl.json` and FAILED (2.73%/yr on capital vs 6%). Carry is closed with no variants.
Current line (owner, 2026-09-29): NEWPLAN2.md #1, SPY option variance risk premium (p20+), trial log
`trials_eqvol.json`.**

## Commands
- `pip install -e ".[dev]"`: install
- `python tests/test_core.py` (or `pytest -q`): unit tests. Run after ANY change in `harness/`.
- `python selftest.py`: must end with `HARNESS OK`. Run after changes to labeling, cv, backtest, metrics or nulls.
- `python scripts/download_binance.py --interval 5m --start 2022-01 --end 2026-08`: free history into data/raw

## Layout
- `harness/`: library code (labels, weights, cv, backtest, metrics, nulls, features, data)
- `research/pNN_<name>/`: one folder per experiment (script or notebook + short RESULTS.md)
- `data/raw` = Binance archive zips, `data/collector` = slices synced from the GCS collector, `data/bars` = parquet caches. All gitignored.
- `trials.json`: the trial log of the closed Binance line (p01–p11). `trials_hl.json`: the trial
  log of the Hyperliquid line. `trials_pm.json`: the trial log of the Polymarket-vs-Deribit line
  (p15). `trials_vrp.json`: the trial log of the Deribit VRP line (p16+). Each is created by its line's
  first holdout trial and committed; only `trials.json` exists so far. Never delete or edit their
  entries. "The trial log" below means the current line's log (no line is open now; p14 writes to
  `trials_hl.json`).

## Research script conventions (research/pNN_<name>/run.py)
- Take a `--no-log` flag that skips `TrialLog.log`. Re-running an identical
  config (e.g. after a report-only harness change) is not a new trial. Any
  change to data, features, labels, model, CV, positions or costs IS a new
  trial and must be logged.
- Save the OOS predictions to `research/pNN_<name>/preds.parquet` (index `t0`,
  column `prob_up`; gitignored), so later re-evaluations need no refit.
- On a `--no-log` re-run, check that every number unrelated to the change
  matches the committed `results.json` exactly. If anything differs, stop and
  find out why before updating RESULTS.md.
- Commit `run.py`, `RESULTS.md`, `results.json` and `run.log`.

## Non-negotiable rules
1. **Causality.** A feature at bar t may use data up to the close of bar t only. Trailing windows only, never `center=True` or `shift(-k)` in features. Bars are indexed by CLOSE time.
2. **No delay=0.** Backtests use delay>=1. Report delay=2 as a robustness check.
3. **Evaluate out of sample with WalkForward.** PurgedKFold is for model selection only. Never use sklearn's shuffled KFold/train_test_split on labels.
4. **Log every trial** that touched the backtest period with `TrialLog.log(...)`, failures included. Report DSR alongside Sharpe.
5. **Never loosen a null test or verdict threshold to make a result pass.** If a result fails, report that it failed.
6. **Costs are always on.** Default CostModel(fee_bps=5, slippage_bps=0.5) for taker. Report the breakeven cost too.
7. Report effective n (sum of uniqueness), not the raw label count, and the annualised Sharpe standard error (~1/sqrt(years)).
8. A result is claimed only after `validation_report` has been run on it. Paste its verdict block into RESULTS.md.
9. **Features enter normalised.** Every feature is a rank or a z-score against a trailing window,
   never a raw level. Raw levels let trees identify the regime (fold-id accuracy 0.998 in p11,
   0.936 in p10) and predict base rates instead of direction.
10. **Adversarial fold-id test.** For any new feature set, train a model to predict the CV fold id
   from the features and report its accuracy in RESULTS.md (chance = 1/n_folds). High accuracy
   means the features encode time, not signal.

## Hyperliquid line bookkeeping
- Own dev/holdout split: first 75% / last 25% of the collected calendar span, fixed the day
  collection starts. The holdout is untouched until the ROADMAP's final stage.
- Own trial log: `trials_hl.json`. Do not write HL trials to `trials.json`.
- Costs measured for Hyperliquid separately (fee schedule, measured spread, fill assumption).
  Never reuse the Binance cost table or `CostModel` defaults for HL results.

## Data notes
- Binance archive timestamps: futures klines, premiumIndexKlines and funding are ms throughout;
  SPOT klines switched to us on 2025-01-01. `load_binance_klines` decides the unit per row, so one
  glob can span both.
- `data/raw` layout: perp klines + fundingRate at top level; `premiumIndexKlines/`, `spot/`, `metrics/`
  (daily files only) in subfolders, because premium/spot/perp kline files share the same file name.
  `python scripts/download_binance.py --kinds metrics premium spot --start 2022-08 --end 2026-08`.
- Snapshot data (metrics, funding) is joined with `asof_join` (strict: a row stamped T is first used
  by the bar closing AFTER T). Metrics rows summarise the 5 min ENDING at T; funding rows are settled
  rates with a few ms of stamp jitter. Top-trader long/short ratios are empty until 2022-12-14.
- Collector (GCS, europe-west3): Polymarket CLOB, Binance spot/futures websockets and Chainlink, since 2026-07-25. The schema is not documented here yet, so ask or inspect a file before writing loaders.

## Closed research lines (do not reopen)
- **1 h / 4 h BTC bar-direction prediction is closed permanently** (p01–p05, p10, p10b, p11).
  Price/flow features (p01–p05, p10), a TCN on 1-minute flow (p10), and external data
  (Deribit DVOL and option-trade flow, cross-venue funding and basis; p11) all failed their kill
  or cost bar. p10b showed that a 4 bps breakeven needs AUC ≈ 0.56–0.59, against a best of
  0.54; that requirement was measured at H=12, not H=48 (p11 reviewer correction).
  Liquidations were never tested (no free history for 2022-08 → 2026-08), so the closure says
  nothing about them.
  Do not reopen it under any framing (new features, new models, stacking, other horizons of the
  same bar-direction label), unless the owner explicitly and newly decides otherwise.
  The closure does NOT cover the Polymarket settlement / fair-value / latency work (p09, p12).
