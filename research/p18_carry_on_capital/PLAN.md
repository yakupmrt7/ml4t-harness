# p18 — Does any HL funding-carry structure earn ≥ 6%/yr on survivable capital? (dev only)

Written 2026-09-29, before any computation for this experiment. Source: the p14 review's proposed next experiment
(research/p14_hl_funding_carry/REVIEW.md), started by the owner on 2026-09-29 together with the decision to keep
p14's holdout sealed. Everything is dev: **2024-01-01 → 2026-01-12**; **2025 (01-01 → 12-31) is the decision
year** because the premium decayed from 2024 to 2025. No holdout data is loaded: every loader cuts at 2026-01-12
at load time (p14 review hygiene point). No trial is logged; every evaluation is a row in `selection_trials.json`.

## Line and the single change vs p14
Line: Hyperliquid funding carry (NEWPLAN #3; trial log `trials_hl.json`, still absent). The single change vs p14
is the **denominator**: returns are measured on the capital a book needs to survive every dev day, not per unit
notional at an assumed 2×. A second structure (B, spot long leg) and an oracle ceiling (C) are added; nothing is
fitted.

## Market reasoning (for the owner)
p14 showed the funding spread is real but the per-venue margin kills leveraged legs. A long **spot** leg cannot be
liquidated and pays no funding, so a short-HL-perp / long-Binance-spot book collects all of HL's funding (not just
the spread over Binance) at the price of fully funding the spot leg. The oracle book (C) knows every future day's
carry and times entries and exits perfectly: it is the most any forecast (NEWPLAN #3's ML version) could ever earn.
If even the oracle cannot clear the bar, no model can.

## Universe and data (cut at 2026-01-12 on load)
- Coins: BTC ETH SOL XRP DOGE LINK AVAX SUI (p14's universe).
- HL hourly funding and Binance perp 8-hourly funding (p14 files), summed by UTC day.
- Daily OHLC: Hyperliquid perp (`candleSnapshot` 1d), Binance USDT perp (p14 `bn_ohlc_*`), Binance **spot** USDT
  (`api/v3/klines` 1d). Closes for P&L; highs/lows for survivable leverage.

## The books (per coin, equal notional, portfolio = mean across coins)
- **A, static perp/perp:** short HL perp, long Binance perp, always on. Daily P&L per unit notional =
  f_HL − f_BN − (r_HLperp − r_BNperp).
- **B, static perp/spot:** short HL perp, long Binance spot, always on. Daily P&L = f_HL − (r_HLperp − r_BNspot).
- **C, oracle:** for each coin and for each of A and B separately, the position path in {0, +1} (and −1 for A:
  long HL / short BN) that maximises dev P&L net of switching costs, found by dynamic programming with full
  knowledge of every day's realised P&L. C = the better (on 2025 capital return) of oracle-A and oracle-B, per
  portfolio. C is computed, never traded.
- **Costs (taker, per side):** HL perp 4.5 + 0.5 bps; Binance perp 5 + 0.5 bps; Binance spot 10 + 0.5 bps. Static
  books pay one entry at the start of dev and one exit at the end, plus a **daily reset** to equal notional
  (cost: each leg's taker rate on its |daily return|). The oracle pays the pair's two sides on every switch and the
  daily reset while in position.

## Survivable leverage and capital (fixed now)
- Daily reset (the operator restores target notional and collateral every day). For each coin and perp leg,
  M = the worst one-day adverse move on dev against that leg vs the previous close: short HL leg max(high/prev − 1)
  on HL candles; long Binance perp leg max(1 − low/prev) on Binance perp candles.
- **Leverage with a 1.5× buffer:** L = min(5, 1 / (1.5·M + 0.05)) (0.05 = maintenance margin). The spot leg is fully
  funded (collateral = notional, cannot be liquidated).
- Capital per unit notional: A = 1/L_short + 1/L_long; B = 1/L_short + 1.
- The worst moves use the whole dev span, including 2025: that is look-ahead in the sizing, and it can only lower
  leverage and so lower the return on capital (conservative for a pass). Disclosed.
- Return on capital = mean daily P&L per unit notional / capital per unit notional, annualised (×365).

## Decision rules (fixed now; 2025 = decision year)
1. **C (oracle) < 6%/yr on capital in 2025 → close carry entirely**, including the NEWPLAN #3 forecasting version
   (no forecast can beat the oracle). 6% = T-bill + 2 pts for two-venue and stablecoin risk.
2. A static book **passes** if, in 2025: return on capital ≥ 6%/yr, **monthly t ≥ 2** (12 monthly P&Ls), worst
   5-day P&L ≥ −12 × the mean 5-day P&L, and no leg liquidated at its leverage (by construction on dev; reported).
3. If C passes but A and B both fail → #3 survives only as a forecasting problem, which must first beat an EWMA of
   past funding on dev in a separate, pre-registered experiment.
4. If B passes → pre-register B exactly (this spec, frozen) and spend p14's sealed holdout on it, as one trial in
   `trials_hl.json`, only after review and the owner's "go". (Same for A if A passes and B does not.)
Also reported: dev-wide (2024–2025) numbers, per-coin leverage and returns, the 2025-10-10 day, and Newey–West
standard errors of the annual return.

## Known risks
- USDC (HL) vs USDT (Binance) basis, cross-venue transfer delays, and exchange default are not modelled.
- Daily reset needs daily collateral moves between venues (operational; assumed free).
- HL liquidates on its own mark price; HL daily highs are last-trade based (p14 review: Binance mark ≈ last within
  0–2 pts on 2025-10-10).
