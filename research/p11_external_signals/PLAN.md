# p11 external signals: the last test of 1 h / 4 h BTC direction

Written 2026-09-24, before any availability survey, download or computation.
The owner named this experiment p11. The RTDS settlement check that
p09/p10's reviews queued as "p11" becomes **p12**. Nothing below changes
after numbers are seen. The exact feature list and per-source lags are
added as an amendment **after Step 0 (availability) and before any
backfill**.

## The tension with p10b, stated plainly
p10b applied its pre-registered kill and wrote that the 1 h / 4 h BTC
bar-direction line was "closed for good": no flow v2, no TCN retune, no
stacking. p10b measured what **price- and flow-derived** features can
deliver: every feature added in p01–p10 lowered AUC or left it unchanged.
It could not speak to data classes those experiments never touched. This
experiment is the owner's explicit exception, and it is bounded:
- It tests **external** inputs only: options-implied vol, liquidations,
  and cross-venue funding and basis. No new price/flow/sequence features.
- It is **ONE** pre-registered experiment.
- **If it is killed, the 1 h / 4 h BTC bar-direction line is closed
  permanently,** with no further reopening under any framing. That will be
  recorded in CLAUDE.md.
- Honest prior: p03 already tested Binance-only funding, open interest,
  basis and long/short ratios. None had pre-OOS |t| ≥ 2, and adding them
  lowered AUC. Cross-venue funding and basis are close relatives of that
  failed family. Options-implied vol and liquidations are new here.

## Hypothesis (falsifiable)
External data (implied vol, liquidations, cross-venue funding and basis)
adds directional information at H = 48 (4 h) beyond p01's basic features.
The both-features model must beat basic-only by ≥ 0.01 pre-OOS AUC, and
pre-OOS breakeven − 1 s.e. must be ≥ 4 bps. Falsified otherwise.

## Step 0: availability survey (before anything is built)
No new collectors; historical backfill only, 2022-08 → 2026-08. The
survey calls each API for a handful of timestamps to learn coverage,
granularity and rate limits. It downloads **no** study-period data.
- **(a) Deribit options:**
  - the DVOL index (`public/get_volatility_index_data`): resolutions and
    history depth;
  - whether historical option trades or chain snapshots are reachable
    through the public API.
- **(b) Binance liquidations:** does
  `data.binance.vision/.../futures/um/daily/liquidationSnapshot/BTCUSDT/`
  exist, and for which dates?
- **(c) Cross-venue funding and perp prices:** Bybit, OKX and Hyperliquid
  public REST. Funding-history depth and granularity, candle depth (for
  basis), rate limits.
- **(d) Anything paid:** report and drop.

Output `AVAILABILITY.md`, then **stop for the owner's go** before any
backfill.

## Labels, splits, costs (identical to p03 where named)
- **Labels:** p01's BTCUSDT perp 5 m bars; `triple_barrier` with **H = 48
  (4 h) primary**, pt = sl = 1 × `ewm_vol(288)·√H`; uniqueness weights.
- **H = 288 (1 d)** is secondary. It is reported, and any choice
  involving it is made pre-OOS only.
- **OOS:** `WalkForward(8)` with test blocks starting exactly at
  2024-04-07 09:15, the same period as p01–p04. Run once, only after the
  owner's "go" at the gate.
- **Pre-OOS:** labels with t0 and t1 < 2024-04-07 09:15;
  `PurgedKFold(5, 0.01)`.
- **Costs:** the p05 `TableCostModel`, maker and taker, delay 1 and 2.
- **Positions:** **P2**, as the owner named it, is p10's P2 =
  `hysteresis_position(0.05, 0, 24)`, p02-exact (applied on the full
  bar grid). No position tuning. p03's own pre-OOS-selected hysteresis
  (0.05/0.025/48) is **not** used, because it was chosen on another
  feature set's predictions.
- **Sample:** a common sample, the labels where every model's features
  exist. The start date is set by the latest-starting surviving source
  and reported. Positions are held across dropped bars (p10's lesson).

## Screening (pre-OOS, before any model)
- Univariate IC (Spearman) of each pre-registered external feature
  against the label's realised return, at H = 48 and H = 288.
- t-stats use **effective n** (sum of uniqueness), not the raw count.
- All reported, one `selection_trials.json` row each. **The screen does
  not drop features:** the model uses the full pre-registered list, so
  that there is no data-driven feature selection before the gate.

## Models (LightGBM `default_model`; identical splits, labels, weights)
- **basic** (p01's 15 features), **external** only, and **both**.
- At H = 48 (primary) and H = 288 (secondary), that is 6 rows in
  `selection_trials.json`.
- Per row: AUC, gross/net Sharpe (maker, taker, d = 1 and 2), turnover,
  breakeven ± s.e. (std(daily gross)·√days/turnover), de-meaned
  breakeven, NW(10) t, shift-null p.

## Kill / gate (fixed now, set by p10b; evaluated at H = 48)
- **KILL** (no OOS run) if the best pre-OOS configuration's breakeven
  < 4 bps, **or** external-only AUC < 0.52.
- **GATE** to ONE OOS trial only if **both**:
  - pre-OOS breakeven − 1 s.e. ≥ 4 bps;
  - the both-features model beats basic-only by ≥ 0.01 AUC.
- H = 288 is reported but cannot open the gate on its own. A GATE at
  H = 48 is the only route to OOS.
- **If it gates:** stop and ask the owner. ONE OOS trial for the single
  configuration that passed, logged as `p11_external_signals` with DSR at
  the trials.json count (3 now, 4 after).
- **If killed:** write RESULTS.md, and add to CLAUDE.md: "The 1 h / 4 h
  BTC bar-direction line is closed permanently (p01–p05, p10, p10b,
  p11). Do not reopen it under any framing."
- **p03's warning about the first gate condition:** its selected
  basic+positioning config had a pre-OOS breakeven of 4.70 bps, but
  2.50 bps on OOS. A 4 bps pre-OOS breakeven alone is weak evidence.
  The ≥ 0.01 AUC gain over basic-only is the condition that makes the
  gate meaningful.

## Power
- **OOS:** 2024-04-07 → 2026-08-31 = 2.40 years, annualised Sharpe s.e.
  ≈ **0.645**.
  - A net Sharpe of **≥ 1.29** is needed for t = 2.
  - For DSR > 0.95 at n_trials = 4 (expected max null Sharpe ≈ 0.66), a
    net Sharpe of **≈ 1.7** is needed.
- **Pre-OOS at H = 48:** ~1.6 years, but each label overlaps ~48 bars, so
  effective n is only a few thousand (p03: 2,860 from 2022-12 onward).
  - With n_eff ≈ 3,000 and balanced classes, the s.e. of one AUC is
    ≈ √((1/12)(1/n₁ + 1/n₀)) ≈ **0.011**.
  - The "≥ 0.01 AUC gain" condition is therefore **about one s.e.** of a
    single AUC. The paired difference between nested models on the same
    labels is tighter, perhaps ~0.005, but still noisy.
  - The gate can let a lucky ~2σ gain through. It cannot reliably detect a
    true gain of 0.01. This is accepted as the owner's gate; RESULTS will
    report the paired-difference s.e. (bootstrap by day blocks) next to
    the AUC gain.
- **p10b's curve,** for scale:
  - at H = 12, a 4 bps breakeven needs AUC 0.559–0.591;
  - H = 48 trades less, so the requirement there is lower. p03's basic
    config was already at 4.7 bps pre-OOS.
- **The binding question** is whether external data adds ≥ 0.01 AUC, and
  whether that survives OOS.

## Bookkeeping
- `trials.json` untouched unless the owner says "go" at the gate.
- `selection_trials.json`: IC rows + 6 model rows.
- Deliverables: PLAN.md, AVAILABILITY.md (Step 0), then loaders
  (`backfill.py`), `features.py`, `screen.py`, `selection.py`,
  RESULTS.md, REVIEW.md.
- If a loader becomes reusable it moves to `harness/` with tests, and
  tests + selftest are run.
