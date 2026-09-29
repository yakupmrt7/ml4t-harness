# p19 — BTC-only funding carry (short HL perp / long Binance spot): one holdout look

Written 2026-09-29, before any holdout-period price or funding is loaded for this experiment.

## Why this exists, and what it is not
- p18 closed funding carry by its pre-registered rule (the oracle earned 5.0%/yr on survivable capital in 2025,
  below 6%). Its per-coin table showed **BTC alone above the bar** (A 8.87 ± 1.51, B 7.76 ± 0.98 %/yr on capital
  in 2025). That is a coin chosen **after** seeing the table: selection, not evidence.
- **The owner reversed the closure for this one test, in writing, on 2026-09-29** ("yes I want this tested"),
  as the p18 review required. p19 spends p14's sealed holdout on it as **one trial** in `trials_hl.json`.
- The holdout has ~8.5 months: its standard error is ~1.2–1.8%/yr, so one look cannot tell 6% from 8%. A pass
  would mean "consistent with a small carry above the bar", not a proven edge; a fail closes BTC carry too.

## The book (frozen; the p18 "B" structure, BTC only)
- **Short BTC perp on Hyperliquid, long BTC spot on Binance (USDT), equal notional, always on.**
- Chosen over A (perp/perp, the higher dev number) *before* the holdout, for survivability rather than dev return:
  the spot leg cannot be liquidated, B's return is HL funding (10.6%/yr on BTC in 2025) rather than leverage, and
  its dev standard error is smaller. A is not run.
- **Leverage, frozen from dev (p18 run.py, BTC):** HL short leg L = **3.894** (worst dev one-day up-move 13.8%,
  buffer 1.5, maintenance 0.05). Spot leg fully funded. **Capital = 1/3.894 + 1 = 1.2568 × notional.**
- **Daily P&L per unit notional** = f_HL (BTC funding summed by UTC day; the short receives positive funding)
  − (r_HLperp − r_BNspot) (daily close-to-close, candles opening 00:00 UTC) − daily reset cost
  (5 bps × |r_HLperp| + 10.5 bps × |r_BNspot|) ; entry on the first day and exit on the last day each cost
  5 + 10.5 bps. Identical to p18 `run.py` book B for BTC.
- **Return on capital** = mean daily P&L / 1.2568, × 365.

## Holdout span (p14, fixed 2026-09-28): 2026-01-12 → 2026-09-27 (exclusive end)
Data: HL BTC funding and Binance spot BTC 1d candles for the span, and HL BTC 1d candles (fetched at run time,
requests ending 2026-09-27). Binance perp data is not used.

## Kills (holdout; the p18 static-book rule, unchanged)
1. Return on capital **< 6%/yr** → FAIL.
2. **Monthly t < 2** (calendar months of the span; the partial first and last months included) → FAIL.
3. Worst 5-day P&L **< −12 ×** the mean 5-day P&L (or mean ≤ 0) → FAIL.
4. **Liquidation:** any day whose HL high exceeds the previous close by more than 1/3.894 − 0.05 = **20.7%** → FAIL.
Pass = none of 1–4. Reported alongside: Newey–West s.e. of the annual return, the funding / basis / reset
decomposition, the worst day, and the same numbers on dev (2024, 2025) for reference.

## Procedure
1. Dev reference numbers from the frozen code (no holdout data) → `dev_reference.json`.
2. Pre-OOS review by the research-reviewer.
3. **Stop for the owner's "go".** Then run once: `python research/p19_btc_carry_holdout/run.py --holdout`,
   which logs exactly one trial to `trials_hl.json`. Never re-run with changes.
4. RESULTS.md, final review, commit.
