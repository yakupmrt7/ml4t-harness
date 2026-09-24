# p10 order flow + a sequence model for 1 h BTC direction

Written 2026-09-24, before any aggTrades data was downloaded or any p10 code
was run. Nothing below changes after numbers are seen. p09's reviewer
proposed a different p10 (an RTDS settlement check). That becomes **p11**
once ≥ 7 days of the new feed exist. The owner named this experiment p10.

## Question and hypothesis
Can a 1 h BTC direction model beat the measured costs (maker 3.38 ± 0.30
bps all-in, taker 5.02 bps; p05)? p01–p04 said "not with bar-level
features": p01 had AUC 0.528 but broke even at only 0.68 bps.

**Hypothesis (falsifiable):** trade-level order-flow features, and/or a
sequence model on the 1-minute flow, raise the edge per unit turnover to a
pre-OOS **breakeven − 1 s.e. ≥ 4 bps**. Falsified if the best pre-OOS
configuration has breakeven < 4 bps or pooled AUC < 0.52.

## What changes vs p01 (and what does not)
- **Changes:**
  - features: trade-level order flow, alongside p01's `basic_features`;
  - model class: a TCN on the raw 1-minute flow sequence, alongside
    LightGBM.
- **Unchanged:**
  - data: BTCUSDT USD-M perp, 5m bars, label t0 in [2022-09-01, 2026-09-01);
  - labels: `triple_barrier` H = 12, pt = sl = 1 × `ewm_vol(288)·√H`;
  - weights: `average_uniqueness`;
  - OOS evaluation: `WalkForward(8)` with test blocks starting exactly at
    2024-04-07 09:15, as p03/p04;
  - costs: taker `CostModel(5, 0.5)` / maker 3.38, plus `TableCostModel`
    where the table covers the month;
  - delay 1, with delay 2 reported.

## Data (build on a temporary VM; the laptop never processes raw trades)
- **Source:** Binance USD-M BTCUSDT aggTrades, 2022-08 → 2026-08. 49 monthly
  zips, **25.9 GB zipped** (measured by HEAD requests), ~130–150 GB as CSV.
- **One aggTrade = one taker order's fills at one price in one ms.** It is
  the unit of "trade" below. `is_buyer_maker = true` means the taker sold.
  Each row carries `first/last_trade_id`, which gives the underlying trade
  count too.
- **Work unit = one UTC day.** Resumable, with a manifest per unit (input
  checksum, rows, output rows, runtime). Outputs are verified with CRC32C
  on upload to `gs://poly-backup-54cb99b7/features/flow_v1/`. Machine,
  cost and runtime are proposed separately, and nothing launches before
  the owner's "go".
- **Output per UTC minute** (label = minute END, i.e. close time):
  - trade counts: `n_agg` (aggTrades), `n_trades` (underlying trades);
  - volume: `buy_qty`, `sell_qty`, `buy_notional`, `sell_notional`;
  - `big_notional`: notional in aggTrades ≥ $100k;
  - `size_median` (qty per aggTrade);
  - runs: `n_runs` and `max_run` (a run = consecutive same-side
    aggTrades; runs are cut at minute boundaries);
  - prices: `px_first`, `px_last`, `px_high`, `px_low`;
  - VPIN buckets: `vpin_done` and `vpin_absimb`;
  - `n_zero` (junk prints, excluded as in p08).
- **VPIN:** fixed **$10M** notional buckets, filled sequentially within the
  UTC day (reset at 00:00). `vpin_done` counts buckets completed in the
  minute. `vpin_absimb` sums |buy − sell| notional over those buckets.
- **Validation (before any feature is used):** one month (2023-06), 5 m
  sums vs the 5 m klines:
  - `buy_qty` = `taker_buy_volume`;
  - `buy_qty + sell_qty` = `volume`;
  - `n_trades` = `count`.

  All must match to ≤ 1e-6 relative on ≥ 99.9% of bars; otherwise stop
  and report.

## Features (pre-registered, causal, trailing; windows w ∈ {5, 15, 60, 240} min)
A feature at 5 m bar close t uses only minutes whose END ≤ t.
1. **Signed imbalance:** (buy_qty − sell_qty) / (buy_qty + sell_qty).
2. **Size and count:**
   - log trade count (`n_agg`);
   - mean aggTrade size (qty / n_agg);
   - "median" size = median of the per-minute medians (a disclosed
     approximation);
   - big-trade share = big_notional / total notional.
3. **VPIN:** Σ vpin_absimb / (Σ vpin_done × $10M) over buckets completed in
   the window. NaN if no bucket completed.
4. **Aggressor runs:**
   - mean run length = Σ n_agg / Σ n_runs;
   - max run = max of the per-minute max_run.
5. **Arrival intensity:** n_agg in the window / (the mean n_agg per
   minute over the 30 days ending at the window start × w).
6. **Kyle λ:** OLS slope of the 1-minute log price change
   (px_last/px_last(−1)) on 1-minute signed notional, in $M, within the
   window. Only w ∈ {15, 60, 240}, because 5 points is too few.
7. **Realised vol** from 1-minute px_last log returns, for w ∈ {15, 60,
   240}, plus the ratios rv15/rv240 and rv60/rv240.

That gives ~37 flow columns, plus p01's 15 `basic_features`.
`feature_lookahead_audit` is run on all of them.

## Models (identical splits, labels, weights)
- **A. LightGBM** (`default_model`), with a pre-OOS feature-group ablation:
  **A-basic** (p01's set), **A-flow**, **A-both**.
- **B. TCN on the raw 1-minute flow sequence.** Fixed architecture, no
  search.
  - **Input:** the last 240 minutes ending at the bar close × 12 channels:
    - log1p(n_agg), log1p(buy_notional), log1p(sell_notional);
    - signed imbalance and big-trade share;
    - log1p(size_median), mean run length, max run;
    - VPIN absimb/done;
    - 1-minute log return, log(high/low);
    - the minute's intensity vs its 30-day baseline.
    - Each channel is standardised with the mean/std of the fold's
      training minutes.
  - **Architecture:** 4 residual blocks, each two causal dilated Conv1d
    (kernel 3) + ReLU + dropout 0.2, 48 channels, dilations 1, 4, 16, 64
    (receptive field 341 min ≥ 240). Then the last time step concatenated
    with the time-mean, a linear layer to 1 logit.
  - **Training:**
    - loss: BCE on the same binary target LightGBM uses, weighted by
      average uniqueness;
    - optimiser: AdamW, lr 1e-3, weight decay 1e-4, batch 512;
    - ≤ 30 epochs, early stopping, patience 3, on an inner validation set
      = the last 10% of the fold's training labels (time-ordered, purged
      by t1);
    - seed 0.
  - **Hardware:** trained on the laptop (PyTorch, MPS/CPU), or on the VM
    if the laptop is too slow. Same code either way.
- **C. Not run in p10.** The TCN-embedding → LightGBM stack needs
  out-of-fold embeddings inside every fold (nested training). Its extra
  complexity is only worth it if B shows signal. If B's pre-OOS AUC ≥
  A-both's, C becomes the follow-up.

## Positions (both fixed from earlier experiments; no new tuning)
- **P1:** p01's rule, sign(p − 0.5) if |p − 0.5| > 0.02, averaged over 12
  bars.
- **P2:** p02's pre-OOS selection, `hysteresis_position(θin = 0.05,
  θout = 0, min_hold = 24)`.

## Pre-OOS selection (unattended; label t0 AND t1 < 2024-04-07 09:15)
- **Window:** 2022-09-01 → 2024-04-06, 1.60 years, ~168 k labels, effective
  n ~17 k (p02).
- **Evaluation:** `PurgedKFold(5, embargo_frac=0.01)` with uniqueness
  weights.
- **Configurations**, every one a row in `selection_trials.json`:
  {A-basic, A-flow, A-both, B} × {P1, P2} = **8**.
- **Metrics per configuration:**
  - pooled AUC;
  - gross Sharpe and net Sharpe (maker, taker; delay 1 and 2);
  - turnover;
  - **breakeven** = Σ gross / Σ turnover, with **s.e.** = std(daily gross) ·
    √n_days / Σ turnover (as in p06/p07);
  - NW(10) t, and the shift-null p (gross).
- **"Best configuration"** = the highest breakeven among those with pooled
  AUC ≥ 0.52. This is disclosed as a max over 8.

## Kill / gate (fixed now)
- **KILL** (no OOS run): if the best pre-OOS configuration has breakeven
  < 4 bps per unit turnover, **or** pooled AUC < 0.52 for every
  configuration.
- **GATE** to one OOS run only if the best configuration's pre-OOS
  **breakeven − 1 s.e. ≥ 4 bps**. Maker cost is 3.38 bps, so this leaves a
  real margin. Otherwise STOP.
- **If it gates:** ONE OOS trial, for that single configuration only, via
  `WalkForward(8)` + `validation_report`. It is logged as
  **`p10_orderflow_1h`**, with DSR at **n_trials = 4** (3 in trials.json
  plus this one), at maker and taker cost and delay 1/2. Not one run per
  model. Stop at the gate and ask the owner before running it.
- **Honest multiple-testing note:** the 8 pre-OOS configurations and p02's
  32-row grid mean the true search is wider than 4. DSR at n = 4 follows
  the owner's instruction, and a DSR at n = 12 (4 + 8) is reported next to
  it.

## Power (what the OOS window can show)
- **OOS:** 2024-04-07 → 2026-08-31 = **2.40 years**. The annualised Sharpe
  s.e. is ≈ 1/√2.40 = **0.645**.
  - To be distinguishable from zero at t = 2, the net Sharpe needs to be
    **≥ 1.29** (≥ 1.06 at one-sided 5%).
  - With DSR at n_trials = 4, the expected max of 4 null Sharpes is ≈ 1.03
    × 0.645 ≈ 0.66. PSR > 0.95 against that needs a net Sharpe ≈ 0.66 +
    1.65 × 0.645 ≈ **1.7**.
- **Pre-OOS:** 1.60 years, Sharpe s.e. ≈ 0.79. The breakeven gate is used
  instead of a Sharpe gate for this reason: breakeven is the quantity that
  decides costs.
- **For reference:** p01's gross Sharpe was 1.04 at 0.68 bps breakeven.
  Reaching 4 bps at similar turnover means ~6× the edge per trade. Reaching
  it by cutting turnover 6× (P2 already halves it) needs the per-trade
  edge to hold up.

## Deliverables
- `research/p10_orderflow_1h/`: PLAN.md; `vm/` (the reduction job, its
  launcher and README); `validate.py`; `features.py` (1-minute →
  5 m-bar features); `tcn.py`; `selection.py` (pre-OOS, 8 rows); later
  `run.py` (OOS, not run before "go"); RESULTS.md; REVIEW.md.
- Flow features live in `data/collector/flow_v1/` (gitignored).
- If feature code becomes reusable, it moves to `harness/` with tests,
  and tests + selftest are run.

## Amendment 1 (2026-09-24, validation criterion; before the VM run or any feature/label work)
A one-day test of the reducer (2023-06-15, on the laptop: 1.24 M aggTrades,
0.8 s) showed that the pre-registered check — every 5 m bar matching the
kline to ≤ 1e-6 on ≥ 99.9% of bars — **cannot hold by construction**:
- An aggTrade carries one `transact_time`, but the klines are built from
  the individual trades inside it. Near a bar boundary those can fall on
  either side.
- On the test day only 82% of bars match exactly. Every mismatch is offset
  by an equal and opposite one in the adjacent bar, and the day totals of
  volume and taker-buy volume match exactly.

This is a property of the data, not a result threshold, so the check is
replaced, before any full run, with (on 2023-06, all days):
1. Daily totals: volume and taker-buy volume within 1e-9 relative; trade
   count within 1e-5 relative (the test day: −6 of 1.24 M, from
   trade-id ranges the klines skip).
2. **Every** per-bar residual (kline − aggTrade sum) must be covered by
   the qty of aggTrades stamped within 1 s before that bar's start or end
   boundary. That is the only way a trade can spill across (test day:
   288/288).
3. Report the share of exactly matching bars and the max |residual|/volume
   (test day: 82%, 0.35%).

If 1 or 2 fails on any day of 2023-06, stop and report. A second, smaller
deviation: the reducer uses the **daily** aggTrades zips, which have the
same rows as the monthly ones and a sha256 CHECKSUM each. That keeps the
work unit at one day (resumable). CRC32C applies to the GCS uploads.

## Amendment 2 (2026-09-24, owner accepted; after the 2023-06 validation, before any feature/label/model evaluation)
The 2023-06 validation (`validate_2023-06.json`) failed amendment 1's
criterion on 18/30 days. The reducer reproduces the raw aggTrades exactly
on all 30 days. The failures are archive-vs-kline differences:
- **Trade count:** 13 days, up to 5.7e-4 relative. aggTrade trade-id ranges
  include ids the klines do not count. No feature uses `n_trades`.
- **Volume:** 6 days, ≤ 1.05e-6 relative (0.35 BTC of 333,105 on 06-08),
  from a few trades that are in the klines but not in the aggTrades archive.
- **Boundary spill:** one bar on 06-08, 2.56 BTC, from an aggTrade stamped
  > 1 s from its trades.

The owner accepted the data ("accept"). The criterion on record becomes:
- volume and taker-buy totals ≤ 1e-5 relative (met on every day; worst
  1.05e-6);
- trade count is not validated, because it is not used;
- boundary spills are unrestricted.

`n_trades` stays in the table but is excluded from all features and
channels (it already was). Nothing else changes.
