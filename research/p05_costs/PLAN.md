# p05 costs: measured spreads, maker fills and depth for the p04 universe

Written 2026-09-22, before any cost data was processed. This is not an alpha
experiment: no model is fitted, nothing goes into `trials.json`, and no
strategy is re-selected with the new costs.

## Why
p01–p04 all stop at the same wall: an edge of 0.7–2.5 bps per unit traded
against *assumed* costs, taker 5 + 0.5 bps and maker 2 + 0.5 bps. p04's alts
showed 4–6 bps edges on ±1 positions, but slippage was the same 0.5 bps for
every asset. A first look at the data already argues against that. APEUSDT
had a 0.001 tick at a price of about 2.81, so its minimum possible spread is
3.6 bps, and its half-spread can never be below 1.8 bps.

This starts from p04's REVIEW.md proposal ("measure the cost wall instead of
the edge"). The owner's spec replaces the collector-based version with the
Binance public archive, which covers all 15 assets over 2022-08 → 2026-08.
The collector (since 2026-07-25) is not used here.

## Hypothesis (falsifiable)
Realistic all-in costs per unit traded are well above the backtest's 0.5 bps
slippage for the alts. Measured maker execution, counting the orders that
don't fill, costs ≥ 2.5 bps on BTC/ETH. If so, no asset in the p04 universe
has a pre-OOS breakeven above its realistic cost.

## Data (archive survey: `archive_survey.json`)
| source | coverage in 2022-08 → 2026-08 | use |
|---|---|---|
| USD-M `bookTicker` (best bid/ask, qty, every update) | **2023-05-16 → 2024-03-30 only** (daily files; monthly to 2024-04). All 15 symbols. Nothing before or after | quoted spread, top-of-book depth, true mid, calibration of the trade-based proxies |
| USD-M `aggTrades` | full span (MATIC to 2024-09, UNFI to 2024-10) | effective spread proxy, maker fill simulation |
| USD-M 1m klines | full span | Roll and Corwin–Schultz sanity checks |

The full download is ~335 GB compressed, and the disk has 106 GB free. So
**sampled days**, fixed now: the **3rd, 10th, 17th and 24th of every month**
(UTC days; the weekday rotates across months). Every file is streamed,
reduced to statistics and deleted; only the derived tables are kept. The 1m
klines (1 GB) are downloaded in full.

## Measurements (per asset, per sampled day, aggregated per month)
Notation: mid m = (bid + ask)/2; half-spread = (ask − bid)/2/m; bps
throughout. A quote "at t" is the last update with transaction_time ≤ t
(strictly causal).

**1. Spreads**
- bookTicker, where available: time-weighted quoted half-spread over the
  day, and the half-spread at two sets of "trade times":
  - the **4h grid**, 00/04/08/12/16/20 UTC;
  - **p04 trade times**: bar closes where p04's pre-OOS ±1 hysteresis
    position changes, from `preds_selection.parquet`, 2022-08 → 2024-04,
    restricted to the sampled days. No refit.
- aggTrades, all months:
  - bid proxy = price of the last seller-initiated trade, ask proxy = the
    last buyer-initiated one, mid proxy = their average;
  - effective half-spread of each trade = |p − mid proxy before it| /
    mid proxy, reported both trade-weighted and volume-weighted;
  - proxy quoted half-spread at the trade times.
- Cross-check: on the bookTicker months, compare the aggTrades proxies with
  the true values. The per-asset ratio (true / proxy) is reported. The cost
  table uses bookTicker where it exists and the proxy elsewhere, with a
  `method` column. If a proxy is off by more than 25% on the overlap, the
  table also stores the calibrated value (proxy × the asset's overlap ratio)
  and says which one is used.
- 1m klines: Roll (2·√(−cov(Δp_t, Δp_{t−1})), undefined if the covariance
  is positive) and Corwin–Schultz, per month, as a sanity check only.

**2. Maker fill simulation (conservative, no queue model).** Orders are
posted at the trade times. On the 4h grid there is one buy and one sell per
time. At p04 trade times the side is the actual trade direction.
- A buy limit at the best bid b_t (bookTicker, or the bid proxy) **fills
  only if a later trade prints strictly below b_t** within
  T ∈ {1, 5, 15, 60} min; sells mirror this. There is no partial fill and no
  queue position. A print through the level means the whole resting queue
  at that price has traded.
- **Primary cost: implementation shortfall against the mid at posting**,
  which is exactly what the backtest assumes it pays (fill at close[t]):
  - filled: (b_t − m_t)/m_t + 2 bps maker fee, i.e. minus the half-spread
    captured;
  - unfilled after T: (ask_{t+T} − m_t)/m_t + 5 bps taker fee, i.e. a taker
    buy at T, which includes the drift you missed.
  - The mean over all orders is the **realistic maker all-in cost**, per
    unit traded, comparable to p04's breakeven. After a fill, the position
    earns the same subsequent returns as the backtest. So the only
    difference is the entry price, and adverse selection shows up as a
    low fill rate when the price runs away from you.
- **Also reported, as the spec asks:** markouts. The mid move against the
  order over 5 / 30 / 240 min after a fill, versus after posting
  (unconditional); adverse selection is the difference. The spec's
  formula cost = 2 + adverse selection(h) − half-spread captured, with
  unfilled orders completed as taker, is shown for each h. Note: adding
  after-fill markouts to a backtest that already earns those returns
  double-counts them. That is why the shortfall is the number the
  CostModel uses.
- Horizon window: post times t ≤ 19:00 UTC, so that t + 60 + 240 min stays
  inside the sampled day. On the 4h grid that means 00, 04, 08, 12, 16 UTC.
  This is a small time-of-day restriction; it is noted, not corrected.
- **Default T for the CostModel: 5 min**, fixed now. That is one bar, which
  matches the backtest's delay = 1 assumption that the trade completes
  within the next bar. The other T values are reported.

**3. Taker all-in and impact.** Taker all-in = 5 bps fee + half-spread at the
trade times. Where bookTicker gives quantities: the top-of-book depth in $
on the side a taker would hit, and the fraction of trade times where
$10k and $100k exceed it. Beyond the top level, impact cannot be measured
from this data, so it is flagged, not modelled.

## Deliverables
- `harness/costs.py`:
  - builds and loads the per-asset, per-month table `data/bars/costs.parquet`
    (asset, month, method, half_spread_bps, taker_all_in_bps,
    maker_all_in_bps_T{1,5,15,60}, fill_rate_T{…}, depth, Roll, CS, n);
  - `TableCostModel(table, asset, kind="taker"|"maker", T=5)`, which gives
    a per-bar cost that `run_backtest` / `run_portfolio_backtest` can use
    (a small hook: a cost model may provide `per_unit_at(index)`);
  - months missing from the table raise, except where an explicit fallback
    is passed.
  - Unit tests: hand-built quotes and trades for the spread, the fill rule
    (strict inequality, timeout, taker completion) and the shortfall
    arithmetic; causality of as-of quotes; and `run_backtest` with a
    constant `TableCostModel` equal to `CostModel`.
- `RESULTS.md`: a per-asset table with measured half-spread, taker all-in,
  realistic maker all-in (T = 5 min; other T values alongside), fill rate
  and **p04's pre-OOS breakeven**, measured over the same pre-OOS months
  (2022-08 → 2024-03).

## Decision rule (fixed now)
- An asset **"has edge > realistic cost"** only if its p04 pre-OOS breakeven
  (unscaled ±1, from PurgedKFold, so optimistic) exceeds its realistic maker
  all-in cost (T = 5 min), both over the pre-OOS months. p04's breakeven is
  **not** recomputed or re-optimised.
- **Kill for the p01–p04 family** (from p04 REVIEW.md): if BTC's and ETH's
  realistic maker all-in cost is ≥ 2.5 bps AND no asset has edge >
  realistic cost, recommend abandoning 5m bar-close mean reversion on
  Binance perps.
- The rows in `selection_trials.json` are measurement runs only. No
  strategy numbers are claimed.
