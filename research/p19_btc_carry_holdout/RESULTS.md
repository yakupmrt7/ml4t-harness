# p19 — BTC funding carry (short HL perp / long Binance spot), one holdout look: FAIL at kill 1

**Verdict: the carry is positive but below the bar.** On p14's holdout (2026-01-12 → 2026-09-27, 258 days, read
by code for the first time in this run), the frozen book returned **2.73 ± 0.90%/yr on capital** (Newey–West
s.e.), against the pre-registered **6%/yr**. Kill 1 fires; kills 2–4 do not. Per PLAN amendment 1: **carry is
closed, with no variants.** One trial, logged as #1 in `trials_hl.json`; `run.py` will not be run or edited again.

Plan: `PLAN.md` (8870d51; code fixes 04910c2), amendment 1 and review fixes (ff73d53), pre-OOS `REVIEW.md`
(ACCEPT WITH FIXES). The owner reversed p18's closure for this single test and said "go" at the gate;
on a pass the next step would have been a 3-month paper test (owner's choice).

## Verdict block (substitute for `validation_report`, per PLAN amendment 1)
```
span 2026-01-12 -> 2026-09-27 (258 days, 9 calendar months)   capital 1.2568 x notional (L_short 3.894)
return on capital   2.73 %/yr  (NW s.e. 0.90)        bar 6.00 %/yr  -> kill 1 FIRES
monthly t           2.73                              bar 2          -> pass
worst 5d / mean 5d  2.35x                             bar 12x        -> pass
max HL up-move      13.98% (vs 20.68% liquidation)                   -> pass, no liquidation
PSR vs the 6% bar   0.0000002      DSR (1 trial, vs 0)   0.99999
decomposition, %/yr on notional: HL funding +4.81, basis +0.01, daily reset −0.95
```

| month (2026) | days | return on capital, %/yr | HL BTC funding, %/yr on notional |
|---|---:|---:|---:|
| Jan (from 12th) | 20 | 1.54 | 5.75 |
| Feb | 28 | 1.20 | 2.32 |
| Mar | 31 | −0.21 | 0.90 |
| Apr | 30 | −1.35 | −0.85 |
| May | 31 | 1.60 | 3.08 |
| Jun | 30 | 3.95 | 5.88 |
| Jul | 31 | 7.09 | 9.47 |
| Aug | 31 | 5.56 | 8.33 |
| Sep (to 26th) | 26 | 4.85 | 9.01 |

## What this means
- The book did what it was built to do: delta-neutral, no liquidation (the largest HL daily rally, 14.0%, stayed
  below the 20.7% the frozen leverage allowed), tiny tails (worst day −0.12% of capital). What failed is the
  **income**: Hyperliquid's BTC funding fell from 24.1%/yr (2024) to 10.6% (2025) to **4.8%** (2026, on notional),
  and was negative in April. The return on capital followed: 18.2 → 7.8 → 2.7%/yr.
- The decline is the trend dev already showed (p14, p18); the holdout continued it rather than reverting. It
  recovered in Jul–Sep 2026 (5–7%/yr on capital), which is a description, not a signal: a second look would be a
  new trial and a new PLAN.
- The result is significantly positive (DSR vs 0 ≈ 1.0) and significantly below the bar (PSR vs 6% ≈ 0): a real,
  small carry of roughly T-bill level on the capital it needs, before USDT/USDC drift, cross-venue transfers and
  exchange default, which are not modelled.
- The holdout was unread by code, not unknown: the owner lived through 2026, and p12/p13 data overlap it; none of
  those computed this book's P&L.

## Files
`PLAN.md` · `run.py` (frozen) · `dev_reference.json/.log` · `REVIEW.md` (pre-OOS) · `holdout.json`, `holdout.log`,
`holdout_daily.parquet`, `hl_ohlc_BTC_holdout.parquet`, `bn_spot_ohlc_BTC_holdout.parquet` · `../../trials_hl.json`.
