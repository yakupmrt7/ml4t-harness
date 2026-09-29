# p14 — Cross-venue funding carry, Hyperliquid vs Binance (screen)

Written 2026-09-28, before any funding series was read (fetch.py was running while this was written).

## Why this, after p13
p13 killed "fade the liquidation": the price move is over before the first liquidation prints
(9–16 bps in the prior 60 s), and gross reversion after it is ≈ 0. Leveraged HL traders owe a
second price-insensitive payment, **funding**: every hour longs pay shorts (or the reverse) the
perp premium plus interest. A position that is short the HL perp and long the Binance perp (or the
reverse) has ~zero price exposure and collects the funding **difference**. That is a cash flow, not
a prediction, so it is the forced-flow thesis in its most direct form. It needs no collection: both
venues publish full funding history.

This is not the closed 1h/4h bar-direction line: no direction is predicted, the book is delta-neutral.
It is not the p11 "cross-venue funding" signal either (p11 used funding as a feature for direction).

## Data
- HL `fundingHistory` (hourly since the switch from 8 h), Binance `fapi/v1/fundingRate` (8 h, some 4 h).
- Daily closes from HL `candleSnapshot` 1d and Binance futures 1d klines (basis P&L).
- Universe fixed now, not chosen on funding: BTC ETH SOL XRP DOGE LINK AVAX SUI (listed on both venues
  for the whole span, large on both). Survivorship: all eight are alive today; delisted HL coins are
  not included. That biases toward *no* basis blow-ups, so a pass here is an upper bound for alts.
- Span 2024-01-01 → 2026-09-27. **Dev = first 75% of the calendar span (→ 2026-01-12 00:00 UTC);
  holdout = the rest, not read by the screen.**

## Daily construction
- f_hl(d), f_bn(d) = sum of funding rates stamped in UTC day d (fraction of notional paid by longs).
- spread s(d) = f_hl(d) − f_bn(d). Short-HL/long-BN earns +s(d); the reverse earns −s(d).
- Basis P&L of short-HL/long-BN from d−1 to d: −(r_hl(d) − r_bn(d)), daily close-to-close returns.

## Rule (one, fixed now; no parameter search)
- Signal at end of day d−1: m = trailing 7-day mean of s (days d−7..d−1, all known at d−1 close).
- Position for day d: pos = +1 (short HL / long BN) if m > +c_enter, −1 if m < −c_enter,
  hold the previous position while |m| > c_exit, flat otherwise. c_enter = 3 bps/day, c_exit = 1 bp/day.
- Trade at d's open ≈ d−1 close (delay 1 day: the signal uses funding through d−1, P&L starts d).
- Cost per change of position: 4 legs per full round trip. Taker: HL 4.5 bps + Binance 5 bps + 0.5 bps
  slippage per leg side → entering a pair = 4.5 + 5 + 1 = 10.5 bps, exiting = 10.5 bps (21 bps
  round trip). A flip (+1 → −1) pays 2 × 10.5. Maker variant reported (HL 1.5 + BN 2 per side = 3.5
  per pair side), not used for the kill.
- Equal notional per coin, each coin its own book; portfolio = mean across coins.

## Kill criteria (dev, taker costs)
1. **Economics:** portfolio net annualised return (funding + basis − costs) ≤ 5% per year of gross
   notional per leg (i.e. not better than parking in T-bills with capital on two venues) → KILL.
2. **Robustness:** net Sharpe (daily, annualised) < 1.0, or fewer than half the coins net positive → KILL.
3. **Persistence (sanity, reported):** AR(1) of daily s per coin; if the median is < 0.3 the trailing
   mean is not a forecast and a pass would be luck.
Report alongside: per-coin funding vs basis vs cost decomposition, turnover, days in market,
the worst 5-day basis loss, and delay-2 (signal through d−2).

## Not in this screen
- Margin/liquidation risk of each leg (a hedged pair can still get one leg liquidated in a spike;
  requires leverage choice). Capital efficiency: return is per unit notional per leg, so on 2×
  margin both venues combined need ≈ 1× notional of capital.
- Holdout. One look at the end, logged in trials_hl.json, only if dev passes.

---

## Amendment 1 — 2026-09-29: pre-registration of the STATIC book for the one holdout look
Written after the interim screen (3 coins, RESULTS.md) and before the 8-coin dev numbers of either book are
computed. **The static book is post hoc**: the idea came from reading 3 coins of dev (RESULTS.md, "Why it
failed"). Its dev numbers below are therefore a consistency check, not evidence; the evidence is the holdout.

### What is finished first (unchanged rule)
The PLAN's pre-registered rule is rerun on dev with all 8 coins, no change. Its kills are reported as they fall.

### The static book (fixed now)
- **Position:** every coin in the PLAN universe (BTC ETH SOL XRP DOGE LINK AVAX SUI), equal notional,
  **short the Hyperliquid perp / long the Binance USDT perp**, always on. Portfolio = mean across coins.
- **Leverage and rebalancing:** 2× per leg (collateral per leg = 50% of its notional; capital = 1× notional).
  Every Monday 00:00 UTC both legs are reset to the target notional and collateral is re-split between venues.
  Cost of the reset: 5.5 bps taker on each leg's |notional drift| since the previous reset (drift = the leg's
  weekly return). Collateral transfers are assumed free and immediate (disclosed: in reality minutes to hours
  plus USDC/USDT conversion of a few bps).
- **Entry/exit:** one taker pair entry at the start and one exit at the end (10.5 bps per pair side, PLAN costs).
- **Daily P&L per unit notional:** funding received on the HL short − funding paid on the BN long (settled
  rates summed by UTC day) + basis −(r_HL − r_BN) on daily closes − weekly reset costs − entry/exit.
- **Margin survival (per leg, 2×):** a leg is liquidated if its adverse move from the last reset exceeds 45%
  (1/L − ~5% maintenance). Checked on Binance daily highs (short HL leg, Binance as the price proxy) and daily
  lows (long BN leg), and on **2025-10-10** with Binance 1-minute lows/highs.
- **ADL stress, 2025-10-10 (dev):** Hyperliquid auto-deleveraged shorts in all 8 coins that day (21:16–21:42
  UTC; p13 fill archive: BTC $621M, ETH $458M, SOL $276M, AVAX $37M, XRP $31M, LINK $22M, DOGE $16M, SUI in
  the list if present). Scenario, reported: the HL short is fully ADL'd at the median ADL fill price and
  re-established at the Binance close of the day (00:00 UTC 10-11) with one taker pair side; the P&L of the
  naked Binance long over that interval is added to the day.

### Kills for the static book (dev as a consistency gate; holdout decides)
1. **Economics:** net annualised return per unit notional ≤ **5%/yr** → KILL.
2. **Statistics:** t of weekly net P&L (non-overlapping weeks) < **2** → KILL.
3. **Tail:** worst 5-day net P&L < **−12 × the mean 5-day net P&L** → KILL.
4. **Survival:** any leg liquidated at 2× in the period (margin rule above) → KILL (the book as specified does
   not survive; a lower leverage would be a new book, and a new trial).
Dev must pass 1–4 for the holdout to be spent. **Holdout (2026-01-12 → 2026-09-27): one run of exactly this
book, logged as one trial in `trials_hl.json`; pass = 1–4 on the holdout.** The 2025-10-10 ADL scenario is
reported with the dev result and must not turn kill 3 or 4 on.
