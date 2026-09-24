# p10 order flow + a sequence model for 1 h BTC direction

**Verdict: KILLED pre-OOS.** The best pre-OOS configuration breaks even at
**1.53 ± 0.87 bps per unit turnover**, against the pre-registered 4 bps
(maker cost is 3.38 bps). That configuration is **p01's basic features
with p02's hysteresis**, not an order-flow one.
- Adding the 44 trade-level flow features **lowers** AUC (0.5445 → 0.5369)
  and breakeven.
- The TCN on the raw 1-minute flow is at AUC 0.510, below the 0.52 floor.
  It **failed to fit its own inputs**; this says nothing either way about
  sequence models.

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
  4–9 epochs.

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
1. **Order flow did not add information at a 1 h horizon, in this form.**
   Checked by the reviewer, on pre-OOS data only:
   - **The flow features mostly encode the regime.** A LightGBM asked
     which CV fold a row comes from gets **0.936** accuracy from the flow
     features vs 0.416 from the basic ones (chance 0.20).
     - The fold explains 0.61–0.76 of the rank variance of the size and
       run-length features. The median across flow features is 0.08, vs
       0.0004 for the basic ones.
     - In fold 1, the flow models predict P(up) 0.556 on average against a
       realised 0.505: they shift the base rate by regime.
   - **A-flow and A-both are worse than a constant forecast** in log-loss
     (0.6969 and 0.6954 vs 0.6930). They are miscalibrated, not just
     diluted.
   - **The flow's directional part was already in p01.** `imb_5` and p01's
     `taker_imb_1` have the same IC, because the klines already record
     taker-buy volume.
   - Scale-free or rank-transformed flow features would be the only
     variant worth considering. It would need its own PLAN (see "Next").
2. **The TCN failed to fit its own inputs.**
   - Its 240-minute window contains p01's `ret_48` exactly. That one
     feature, sign-flipped and unfitted, has AUC 0.527. The TCN reaches
     0.510, with log-loss 0.6943, worse than a constant.
   - The best inner-validation loss beats a constant by only ~0.0005,
     inside the noise.
   - The inputs were not clipped: a range channel reaches z = 411, others
     62–78. That gives saturated predictions from 0.03 to 0.996.
   - So this is a failed fit of one fixed architecture. **It is not
     evidence about sequence models or about the 1-minute flow.**
3. **The only real signal is still p01's, and it is weak.** A-basic/P2
   shows AUC 0.5445, gross SR 1.20 and survives delay 2 (1.53). That
   matches p02's pre-OOS numbers (0.545, breakeven 1.01–1.35). But:
   - its shift-null p of 0.050 is the best of 16 rows, so it is not
     significant after selection;
   - it is on average +0.09 long, and **18% of its gross is that net-long
     exposure** in a market that rose 123%;
   - the long leg makes +79% and the short leg −6.8%;
   - fold 1 (Sep–Dec 2022) loses (breakeven −1.95 bps);
   - the reversal signal decays across folds: A-basic AUC 0.541 → 0.524;
   - other ways of computing breakeven: 1.86 bps holding positions
     exactly as p02 does (min_hold counted in bars), 1.26 bps with the
     net-long part removed.
   Its breakeven is **≈ 2× short of maker cost** with the flow data
   included or not. Costs, not features, remain the binding constraint
   at a 1 h horizon on BTC.
4. **Power:** the pre-OOS Sharpe s.e. is ~0.79 and the breakeven s.e. is
   0.5–1.6 bps. The gate needed breakeven − 1 s.e. ≥ 4 bps, which is
   ≥ 2.6× what any configuration reached even at +1 s.e.

## Limitations
- **Funding is not in the pre-OOS backtests.** The best configuration is
  net long, and longs mostly paid funding in 2023–24, so including it
  would lower breakeven further.
- **Off-kline prints:** the aggTrades archive contains a few trades
  outside the kline's high–low range (e.g. 2022-09-06 17:13, a print at
  28,368 vs a kline range of 19,068–19,372). 22 pre-OOS bars are more than
  0.1% outside. The volume-only validation cannot catch these. They touch
  a handful of price-based flow features.
- **VPIN bucket completion** is stamped up to one trade early (negligible,
  and it can only help the model).
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
    lost ~5.5 h. **That run produced no numbers.** It died before the
    first model fit, so nothing from it was seen or used.
  - The minute ending 00:00 was first assigned to the wrong day, found
    and fixed before any evaluation.

## Review
REVIEW.md: **ACCEPT WITH FIXES.** The kill is valid, and still holds at
+2 s.e. (3.27 < 3.38 bps maker). The reviewer recomputed 10 features by
hand at 6 random bar closes (all ≤ 2e-13) and found no causality,
labelling or alignment bug. Its four wording fixes are applied above:
1. the TCN is a failed fit;
2. validation loss near ln 2 is no longer read as "learned nothing";
3. the best configuration's P&L makeup is disclosed;
4. the drift evidence is included.

A separate bug is also fixed: `selection.py` now appends to
`selection_trials.json` instead of overwriting it.

## Next (reviewer)
The 1 h / 4 h bar-direction line has failed its kill or cost bar in p02,
p03, p04, p05 and p10. Before closing it for good, one zero-OOS-trial
calculation:
- Build synthetic predictions with pre-OOS AUC 0.55 → 0.65, keeping P2 and
  the costs fixed, and read off breakeven against AUC.
- Kill, fixed in advance: if AUC ≥ 0.58 is needed for 4 bps, abandon the
  line for good (no flow v2, no TCN retune, no stack).
- A rough extrapolation says about 0.61 is needed, and no feature
  addition in p01–p10 has raised AUC at all.
- Then move on to p11 (the RTDS settlement check).

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
