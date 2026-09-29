# p17 — Upper bound on maker P&L in Polymarket 5-minute BTC up/down markets

Written 2026-09-29, before any trade, price or outcome of the markets below was read. Source: NEWPLAN.md
idea #4 ("first step is free"), proposed as the next experiment by the p16 review. Started by the owner on
2026-09-29. Nothing below changes after numbers are seen; anything decided on data goes into a dated
amendment committed before the step that uses it.

## Line and scope
- **Line:** Polymarket crypto up/down markets as a *maker* (NEWPLAN #4). p09 tested the *taker* side of the same
  markets (killed: realised −1.15 ¢/contract, and the Polymarket mid is well calibrated). The single change vs
  p09: the side of the trade. p17 asks what the passive side of every trade earned.
- **Measurement only, zero trials.** No strategy is selected. `selection_trials.json` gets one `measurement` row.
  No trial log entry (a maker strategy, if one follows, gets its own line log and fresh data).
- **Data window (fixed now):** markets whose 5-minute window starts in **2026-09-21 00:00 → 2026-09-28 23:55 UTC**
  (8 days, 2,304 markets). p09's dev (07-25 → 09-05) is spent and its holdout (09-06 → 09-20) stays untouched.
  Data after 2026-09-28 is reserved for any follow-up.

## Market reasoning (for the owner)
Every trade has a taker (who crossed the spread) and a maker (whose resting order was hit). Holding to
resolution, the maker's P&L on a trade is exactly minus the taker's P&L before fees: if a taker buys "Up" at
p, the maker sold "Up" at p and earns p − 1{Up}. Summing over all trades gives what makers *as a group* made.
Since 2026 Polymarket charges takers a fee on crypto markets (0.07·p·(1−p) per share at the top rate) and
returns 20% of it to makers as rebates. So the maker side gets the spread, plus a rebate, minus adverse
selection: fast takers hit quotes that are stale after Binance moves. We are a slow maker (the collector sits
~127 ms behind Binance), so we would earn **less** than the group average: fast makers cancel stale quotes, and
the fills they avoid are the ones a slow maker keeps. The group average is therefore an **upper bound** for us.
If the upper bound is not positive, the maker idea is dead without building anything.

## Data
- **Markets and outcomes:** Gamma API by slug `btc-updown-5m-<window start epoch>`, on a throwaway VM
  (Polymarket is blocked from the owner's machine; memory rule: never run jobs on the collector VMs). Fields:
  conditionId, clobTokenIds, outcomes, outcomePrices, closed, UMA status, fee fields if present
  (makerBaseFee / takerBaseFee / feesEnabled).
- **Trades:** Polymarket data API, `takerOnly=true`, per conditionId: timestamp (= Polygon block time,
  verified in p15), taker side, outcome index, size, price, tx hash. Same bounded-memory fetcher as p15.
- **Fees:** the taker fee rate per trade is not in the API rows. It is read from the collector's own
  `polymarket__last_trade_price` stream (`fee_rate_bps`), using the GCS backup files for the window that exist
  (read-only `gcloud storage cp` to the laptop; nothing runs on the collector VM).
- **Validation:** per market, API share volume vs Gamma's volume counter (as in p15 amendment 1; gate ≥ 95% of
  markets within 1%); API vs collector `last_trade_price` trade counts on overlapping hours.

## Measurement
For every taker trade (YES-equivalent: outcome 0 = Up at p; outcome 1 at q ↦ p = 1 − q, side flipped):
- maker P&L per share = (p − 1{Up}) if the taker bought Up, (1{Up} − p) if the taker sold Up;
- maker rebate per share = 0.20 × fee, with fee = fee_rate × p·(1−p) where fee_rate is the market's taker rate
  (from `fee_rate_bps` in the collector stream; if fees are 0 in these markets, the rebate is 0). This assigns
  the whole pool pro rata to trades, an upper bound on any one maker's share.
- **Primary statistic:** per market, maker P&L per share traded (Σ P&L / Σ shares, rebate included); then the
  **equal-weighted mean across markets** with a t-stat **clustered by market** (each market is one observation).
  Also reported: share-weighted total, $ per day, by time-to-expiry bucket (0–60 s, 60–180 s, 180–300 s before
  the window end, and pre-window), by price bucket, by trade size, by day; and the same without rebate.

## Kill (fixed now)
**KILL if the upper bound is ≤ 0 or its t (clustered by market) < 2.** A kill closes the maker line for
these markets. A pass does **not** make a strategy: it opens a separate experiment that must measure what a
*slow* maker gets (queue position, cancel latency, fill-conditional markouts) on data after 2026-09-28.

## Known risks, stated before looking
- **Upper bound, not an estimate:** it includes the fastest makers' P&L. The bound is only useful to kill.
- **Hold-to-resolution** is one convention; makers who unwind early have a different P&L. It is the natural
  unit for the question "does the passive side of this market make money".
- **Settlement:** outcomes are Gamma resolutions (no rebuild needed; p09 validated Gamma as ground truth).
- **Rebate uncertainty:** program rules (20% share, eligibility) are from Polymarket documentation as of 2026
  and may differ per market; the no-rebate number is reported next to it.
- **Collector outage** 2026-09-28 20:25 → 09-29 06:05 affects only the fee cross-check, not the API data.
