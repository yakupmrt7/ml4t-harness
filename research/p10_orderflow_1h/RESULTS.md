# p10 order flow + a sequence model for 1 h BTC direction

**Verdict: KILLED pre-OOS.** The best pre-OOS configuration breaks even at
**1.53 ± 0.87 bps per unit turnover**, against the pre-registered 4 bps
(maker cost is 3.38 bps). That configuration is **p01's basic features
with p02's hysteresis**, not an order-flow one.
- Adding the 44 trade-level flow features **lowers** AUC (0.5445 → 0.5369)
  and breakeven.
- The TCN on the raw 1-minute flow is at AUC 0.510, below the 0.52 floor.

No OOS run and `trials.json` untouched (3 trials). The 8 configurations,
plus 8 corrected rows, are logged in `selection_trials.json`.

## What was built
- **Data:** 1-minute order-flow aggregates from all Binance USD-M BTCUSDT
  aggTrades, 2022-08-01 → 2026-08-31.
  - 1,492 daily zips, 25.9 GB zipped, each sha256-checked. The reduction
    ran on a throwaway `e2-standard-8` (≈ 1 h, ≈ $0.30; VM deleted).
  - Output: `gs://poly-backup-54cb99b7/features/flow_v1/`, 1-minute
    parquet plus a manifest per day, 201 MB. Code: `vm/reduce_flow.py`;
    run log: `vm/run.log`.
- **Validation** (2023-06, `validate_2023-06.json`; PLAN amendments 1–2):
  - The reducer reproduces the raw aggTrades exactly on all 30 days.
  - An exact per-bar match against the 5 m klines is impossible by
    construction: an aggTrade has one timestamp, its trades can straddle a
    bar boundary.
  - The pre-registered criterion failed on 18/30 days:
    - trade-count definitions, up to 5.7e-4; the count is not used by any
      feature;
    - volume totals, ≤ 1.05e-6;
    - one > 1 s boundary spill.
  - The owner accepted the data after this diagnosis.
- **Features:** 44 pre-registered, causal, trailing flow features over
  5/15/60/240 min (imbalance, count, mean/median size, big-trade share,
  VPIN on $10M buckets, aggressor runs, intensity vs a 30-day baseline,
  Kyle λ, realised vol and its ratios), plus p01's 15 `basic_features`.
  The look-ahead audit flagged nothing.
- **TCN:** as fixed in PLAN.md. 4 residual blocks, 48 channels,
  dilations 1/4/16/64, 240 × 12 input, 51 k parameters. Trained on the
  laptop GPU (MPS), 25 s per epoch. Early stopping ended the folds after
  4–9 epochs: validation loss never moved away from ln 2 ≈ 0.693.

## Pre-OOS results
Labels have t0 and t1 before 2024-04-07 09:15. `PurgedKFold(5, 0.01)`,
uniqueness weights, p01's triple-barrier H = 12. The common sample is
156,943 labels (effective n 16,181).

| config | AUC | gross SR (d=1 / d=2) | net SR, maker | turnover / yr | **breakeven bps ± s.e.** | NW(10) t | shift-null p |
|---|---:|---:|---:|---:|---:|---:|---:|
| A-basic / P1 | **0.5445** | 0.96 / 0.72 | −3.57 | 5,050 | 0.66 ± 0.51 | 1.64 | 0.110 |
| **A-basic / P2** | **0.5445** | 1.20 / 1.53 | −1.23 | 2,965 | **1.53 ± 0.87** | 1.76 | 0.050 |
| A-flow / P1 | 0.5223 | −0.27 / −0.51 | −4.26 | 4,768 | −0.21 ± 0.60 | −0.45 | 0.920 |
| A-flow / P2 | 0.5223 | −0.22 / −0.24 | −2.24 | 2,577 | −0.34 ± 1.24 | −0.33 | 0.895 |
| A-both / P1 | 0.5369 | 0.07 / −0.11 | −3.69 | 4,734 | 0.06 ± 0.60 | 0.14 | 0.735 |
| A-both / P2 | 0.5369 | 0.59 / 0.27 | −1.54 | 2,804 | 0.86 ± 1.07 | 1.00 | 0.415 |
| B-TCN / P1 | 0.5101 | 0.79 / 0.71 | −2.78 | 3,633 | 0.68 ± 0.67 | 1.42 | 0.710 |
| B-TCN / P2 | 0.5101 | −0.33 / −0.33 | −1.87 | 1,863 | −0.66 ± 1.59 | −0.52 | 0.955 |

- **Positions:** P1 = p01's sign rule (0.02, smooth 12); P2 = p02's
  hysteresis (0.05, 0, hold 24). Both are fixed from earlier experiments.
- **Maker cost:** the p05 table (≈ 3.3 bps for BTC).
- **Breakeven s.e.:** std(daily gross) · √days / turnover.

**Kill check:** best configuration (highest breakeven with AUC ≥ 0.52) =
A-basic/P2, 1.53 bps < 4 bps → **KILL**. Even +1 s.e. is 2.4 bps.

### A correction made before this write-up (the kill is unaffected)
`selection.py` let `run_backtest` treat bars missing from the common
sample (~7%) as **flat**. That added a flat-and-back round trip at each
one and roughly doubled turnover (A-basic/P1: 11,181 vs p02's 5,312 for the
same rule). The first run's decision was also KILL, at a best breakeven of
0.47 bps.

`reevaluate.py` re-evaluates the **same saved predictions**, without
refitting, with positions **held** across dropped bars. That is p02's
rule, and the table above uses it. Both sets of rows are in
`selection_trials.json`, and the first set is in `selection.json`
(`results`). The corrected turnover now matches p02's.

## Reading
1. **Order flow did not add information at a 1 h horizon, at least in
   this form.**
   - On its own the flow set is barely above chance (AUC 0.522), and its
     gross Sharpe is negative under both position rules.
   - Mixed with the basic features it *dilutes* them (0.5445 → 0.5369).
   - A plausible cause, not tested: several flow features are levels
     with strong drift over 2022–2024 (trade count, sizes, run lengths,
     λ). A tree model splits on regime rather than direction, and
     PurgedKFold trains partly on other regimes. A scale-free or
     rank-transformed flow set would be the natural next step. It would
     need its own PLAN.
2. **The TCN learned nothing.** Validation loss stayed at ln 2 in every
   fold. The fixed architecture had no search, so this is one shot, not a
   verdict on sequence models. But the raw 1-minute flow does not carry
   enough 1 h directional signal for a small TCN to find in 125 k labels.
3. **The only real signal is still p01's.** A-basic/P2 shows AUC 0.5445,
   gross SR 1.20, shift-null p 0.050, and it survives delay 2 (1.53).
   That matches p02's pre-OOS numbers (0.545, breakeven 1.01–1.35).
   Its breakeven is **≈ 2× short of maker cost** with the flow data
   included or not. Costs, not features, remain the binding constraint
   at a 1 h horizon on BTC.
4. **Power:** the pre-OOS Sharpe s.e. is ~0.79 and the breakeven s.e. is
   0.5–1.6 bps. The gate needed breakeven − 1 s.e. ≥ 4 bps, which is
   ≥ 2.6× what any configuration reached even at +1 s.e.

## Limitations
- **Common sample excludes ~7% of labels.** `vpin_5` is NaN whenever no
  $10M bucket completes within 5 minutes. That is the pre-registered
  definition, and in quiet months it reaches 20% of labels (2022-12). All
  8 configurations use the same sample, and positions are held across the
  dropped bars.
- **"Median" trade size over a window** is the median of per-minute
  medians, as disclosed in PLAN.md.
- **Aggressor runs** are cut at minute boundaries.
- **Engineering incidents, recorded for reproducibility:**
  - Importing PyTorch before LightGBM segfaults LightGBM on macOS
    (OpenMP clash), so `selection.py` imports lightgbm first.
  - A first `nohup` launch inside a tool call was silently killed, which
    lost ~5.5 h.
  - The minute ending 00:00 was first assigned to the wrong day, found
    and fixed before any evaluation.

## Files
- `PLAN.md` (+ amendments 1–2)
- `vm/reduce_flow.py`, `vm/validate.py`, `vm/run.log`
- `validate_2023-06.json`
- `common.py` (features, channels), `tcn.py`
- `selection.py`, `selection.log`
- `reevaluate.py`, `reevaluate.log`
- `selection.json`, `selection_trials.json`
- Local, gitignored: `preds_selection.parquet`, `data/collector/flow_v1/`

Reproduce (repo root):
1. `python research/p10_orderflow_1h/vm/reduce_flow.py --start 2022-08-01 --end 2026-08-31` (on a VM)
2. `gcloud storage rsync -r gs://poly-backup-54cb99b7/features/flow_v1/1m data/collector/flow_v1/1m`
3. `PYTHONPATH=.:research/p10_orderflow_1h python research/p10_orderflow_1h/selection.py` (~35 min)
4. `PYTHONPATH=.:research/p10_orderflow_1h python research/p10_orderflow_1h/reevaluate.py`
