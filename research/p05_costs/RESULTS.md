# p05 costs: measured spreads, maker fills and depth for the p04 universe

**Verdict: realistic costs kill the p01–p04 family.** p04's REVIEW committed
to abandoning 5m bar-close mean reversion on Binance if the realistic maker
all-in cost is ≥ 2.5 bps. It is **3.38 ± 0.30 bps for BTC and 2.86 ± 0.36
bps for ETH**. Across the 15 perps, no asset's pre-OOS edge is
distinguishable from its cost.

- **Maker is dearer than assumed: 2.6–6.7 bps all-in, against the assumed
  2.5.** On BTC/ETH, 90% of orders fill within 5 min at about the 2 bps fee.
  The rest must be crossed after the price has run away, at 12–14 bps each.
  On the alts, filled orders cost −0.6 to +1.8 bps, because the half-spread
  earned offsets part of the fee. But unfilled ones cost 16–53 bps, and
  on the tick-bound alts (APE, DOT, GMT, SAND, ADA) 15–21% go unfilled.
- **Taker is 5.0–7.0 bps at top-of-book size, and much more at trading
  size.** BTC/ETH half-spreads are 0.02–0.03 bps, far below the assumed
  0.5. The tick-bound alts pay 1–2 bps. At $10–50k per order, the measured
  effective half-spread is 2.2–4.4 bps on ETC, OP, SOL and ADA, 5.6 on APE
  and 16.5 on UNFI.
- **Edge vs cost.** On point estimates, 8 of 15 assets have a p04 pre-OOS
  breakeven above their maker cost (ADA, APE, AVAX, ETC, MATIC, OP, SAND,
  SOL). That drops to 7 (AVAX falls out) under the other calibration
  choices and under size weighting. **None is significant**:
  - the best z is 1.18 (ETC), and the mean z over the 15 assets is −0.14,
    which is what noise gives;
  - p04's breakevens carry s.e. of 1.6–4.1 bps and are optimistic
    PurgedKFold numbers.
  - ETC and OP clear top-of-book taker, but not the $10–50k taker cost
    (≈ 8.5 and 9.4 bps against breakevens of 5.8 and 6.3).
- **Which kill rule.** p05's PLAN.md restated p04's kill with an extra
  condition ("AND no asset has edge > realistic cost"). Under that looser
  version the family would survive on the 7–8 noisy point estimates. It was
  written before any data, but it weakened a commitment already made, so
  the original rule is the one applied here. **Recommendation: abandon
  5m bar-close mean reversion on Binance perps.**

This was not an alpha experiment: no model was fitted, no strategy was
re-selected, and `trials.json` is unchanged (3 trials). The two
measurement builds are logged in `selection_trials.json`.

Reproduce (repo root; ~1 h, ~43 GB streamed, only statistics kept):
- `PYTHONPATH=.:research/p04_multiasset python research/p05_costs/make_p04_trade_times.py`
- `PYTHONPATH=. python research/p05_costs/measure.py` (resumable)
- `python scripts/download_binance.py --symbol <S> --interval 1m --start 2022-08 --end 2026-08 --kinds klines --out data/raw/klines1m` (each symbol)
- `PYTHONPATH=. python research/p05_costs/build.py`
- `PYTHONPATH=.:research/p05_costs python research/p05_costs/impact_check.py` (order-size check)

## Data actually available (`archive_survey.json`)
| source | coverage | used |
|---|---|---|
| USD-M bookTicker | **2023-05-16 → 2024-03-30 only**, for all 15 symbols (daily files; nothing before or after) | 630 asset-days: true quotes and depth |
| USD-M aggTrades | full span (MATIC → 2024-09, UNFI → 2024-10) | 2,757 asset-days |
| 1m klines | full span | Roll and Corwin–Schultz |

Sampled days were the 3rd, 10th, 17th and 24th of each month, fixed in
PLAN.md: 196 per asset (101 for MATIC, 108 for UNFI). That gave 40,559
simulated orders.

## Decision table (pre-OOS months 2022-08 → 2024-03, orders at p04's trade times and directions)
All numbers are bps per unit of notional traded; ± is one s.e.
- **Maker** is the implementation shortfall against the mid at the
  decision time, which is exactly what the backtest assumes it pays
  (fill at close[t], delay = 1):
  - filled orders get the bid (or ask) plus the 2 bps fee;
  - orders unfilled after 5 min are completed as taker at t + 5 min plus
    the 5 bps fee.
- **Taker** = the 5 bps fee + the quoted half-spread (top-of-book size).
- **p04 BE** = p04's pre-OOS breakeven (unscaled ±1, PurgedKFold), not
  recomputed. Its s.e. is BE / t, with t = gross SR·√1.68 yr.
- z = (BE − maker) / √(se_BE² + se_maker²).

| asset | half-spread | taker all-in | maker all-in (T=5) | fill 5 min | maker, 4h grid | top depth $ (median) | $10k > top | p04 BE | z |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BTCUSDT | 0.02 | 5.02 | 3.38 ± 0.30 | 90% | 3.07 | 179,656 | 6% | 0.34 ± 1.64 | −1.82 |
| ETHUSDT | 0.03 | 5.03 | 2.86 ± 0.36 | 92% | 3.12 | 107,054 | 13% | 0.62 ± 1.96 | −1.12 |
| BNBUSDT | 0.19 | 5.19 | 4.18 ± 0.56 | 89% | 3.55 | 8,530 | 58% | 1.96 ± 1.84 | −1.15 |
| ETCUSDT | 0.29 | 5.29 | 2.62 ± 0.45 | 92% | 3.75 | 1,723 | 91% | **5.81 ± 2.68** | +1.18 |
| SOLUSDT | 0.42 | 5.42 | 2.72 ± 0.43 | 95% | 4.09 | 4,393 | 77% | **5.16 ± 3.86** | +0.63 |
| OPUSDT | 0.37 | 5.37 | 3.18 ± 0.54 | 93% | 3.54 | 1,580 | 95% | **6.32 ± 3.84** | +0.81 |
| AVAXUSDT | 0.70 | 5.70 | 4.88 ± 1.24 | 86% | 4.37 | 2,276 | 90% | **4.94 ± 2.88** | +0.02 |
| MATICUSDT | 0.71 | 5.71 | 3.88 ± 0.62 | 91% | 3.46 | 8,835 | 56% | **4.08 ± 2.70** | +0.07 |
| DOTUSDT | 0.95 | 5.95 | 4.19 ± 0.62 | 87% | 4.01 | 11,528 | 53% | 3.01 ± 2.38 | −0.48 |
| UNFIUSDT | 1.09 | 6.09 | 3.99 ± 1.48 | 90% | 5.05 | 530 | 97% | 3.41 ± 4.13 | −0.13 |
| SANDUSDT | 1.05 | 6.05 | 4.17 ± 0.61 | 85% | 4.66 | 5,288 | 79% | **5.97 ± 2.89** | +0.61 |
| XRPUSDT | 1.10 | 6.10 | 2.97 ± 0.40 | 88% | 4.24 | 37,714 | 6% | 2.82 ± 2.43 | −0.06 |
| ADAUSDT | 1.41 | 6.41 | 4.47 ± 0.74 | 84% | 4.35 | 21,446 | 26% | **5.12 ± 2.41** | +0.26 |
| GMTUSDT | 1.81 | 6.81 | 6.68 ± 1.41 | 83% | 4.61 | 10,813 | 56% | 1.80 ± 3.41 | −1.32 |
| APEUSDT | 2.03 | 7.03 | 4.79 ± 0.77 | 84% | 4.17 | 18,188 | 34% | **6.16 ± 3.19** | +0.42 |

Bold = breakeven > maker cost on the point estimate. Depth and "$10k > top"
come from bookTicker days only (2023-05 → 2024-03).

**Sensitivity** (maker all-in, T = 5):

| variant | assets with BE > maker |
|---|---:|
| as tabled: proxy months calibrated on the p04-time orders (the PLAN did not say which set; I chose it when writing build.py, after a dry run on partial data, so not blind) | 8 |
| calibrated on the 4h-grid orders instead | 7 (AVAX 5.43 > 4.94) |
| no calibration | 7 (AVAX 5.53) |
| orders weighted by trade size (a flip = 2 units) | 7 (AVAX 5.00) |

ETC's maker cost is 2.62 as tabled, 3.2–3.3 without the p04-fitted
calibration, and 2.63 size-weighted.

**Other T values** (maker all-in, same orders): BTC 3.49 / 3.38 / 3.15 /
2.96 and ETH 3.40 / 2.86 / 2.49 / 2.55 at T = 1 / 5 / 15 / 60 min. The median
fill rate over the 15 assets is 79 / 89 / 93 / 97%. T = 5 was fixed in
advance. **Don't quote the T = 60 column for individual alts.** Unfilled
orders there carry 60 min of drift, and the proxy calibration shifts reach
−13 bps (AVAX), so those numbers are noise.

## Taker cost by order size (review fix; `impact_check.py`)
A taker order = the aggTrades sharing one timestamp and aggressor side (a
sweep prints one aggTrade per price level). Its effective half-spread is its
VWAP against the bookTicker mid just before it. Measured on 2 bookTicker
days (2023-06-10, 2024-01-10), 0.17–1.8 M orders per asset:

| asset | < $1k | $1–10k | $10–50k | $50–100k | > $100k | levels swept at $10–50k | quoted, time-weighted | quoted at order times |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SOLUSDT | 0.57 | 0.86 | 2.22 | 4.30 | 6.01 | 7.6 | 0.24 | 0.48 |
| ETCUSDT | 0.72 | 1.22 | 3.48 | 8.03 | 10.73 | 7.1 | 0.35 | 0.65 |
| OPUSDT | 0.76 | 1.47 | 4.38 | 9.37 | 16.34 | 10.3 | 0.43 | 0.75 |
| ADAUSDT | 1.91 | 2.24 | 3.31 | 8.11 | 12.88 | 1.4 | 1.47 | 1.61 |
| APEUSDT | 2.59 | 3.32 | 5.60 | 14.89 | 22.99 | 1.6 | 2.94 | 3.01 |
| UNFIUSDT | 2.97 | 4.84 | 16.54 | 57.80 | n/a | 9.1 | 1.55 | 2.46 |

- The time-weighted quoted spread understates what a taker pays even at
  small size, because **spreads widen when trading happens**. At the
  moments orders arrive, the quoted half-spread is 1.0–2.0× its
  time-weighted value (about 2× on the thin books).
- **Thin books** (ETC, OP, SOL, UNFI) are cheap at < $1k but sweep 7–10
  levels at $10–50k.
- **Tick-bound books** (ADA, APE) have a wide spread but deep levels: the
  cost rises slowly until $50k.
- These are 2 days in 2023–24. They do not describe 2026, when the
  alts are tick-bound at 4–8 bps (see "Over time"). Small orders pay a
  little more than the quoted spread on 4 of 6 assets, which suggests the
  reference mid is slightly stale; that errs toward overstating cost.
- For a strategy trading $10–50k per order, taker all-in is about 7.2 (SOL),
  8.3–8.5 (ADA, ETC), 9.4 (OP), 10.6 (APE) and 21.5 bps (UNFI). That is
  roughly 1.3–3.5× the top-of-book numbers in the decision table.

## Why maker costs about 3–4 bps, not 2.5 (market mechanics)
Take BTC. The half-spread is 0.02 bps (one $0.10 tick on a $25–70k price),
so resting at the bid earns nothing over the mid.
- 89–90% of orders fill within 5 min, at a cost of ≈ the 2 bps fee.
- The other ~10% don't fill, **because the price moved away**. Completing
  them as taker costs the 5 bps fee plus ~7 bps of drift, ≈ 12 bps.
- 0.9 × 2 + 0.1 × 12 ≈ 3 bps.

That is adverse selection showing up as *which orders get filled*. On the
alts, one tick is 1–5 bps, so filled orders earn part of it back: their
average cost is −0.6 to +1.8 bps. But unfilled orders cost 16–53 bps, and
the tick-bound alts fill least often (79–85%, against 89–96% for BTC, ETH,
SOL, OP, ETC and UNFI; bookTicker days).

**Markouts** (spec view; p04 trade times on bookTicker days, T = 5):
- Adverse selection at 5 min (markout after the fill minus markout after
  posting) is −1.4 to +4.3 bps.
- The spec's formula (2 + AS_h − half-spread captured, with unfilled
  orders completed as taker) gives 2.3–9.3 bps at h = 5 min, close to the
  shortfall.
- At 30 and 240 min it swings from −6 to +11 bps. Posting markouts reach
  ±45 bps with n ≈ 150 per asset, so that is noise.
- The markout formula also double-counts against this backtest, because
  the backtest already earns the post-fill returns. So the table uses the
  shortfall. Full numbers: `results.json` → `markouts_p04_bookticker`.

## Spread cross-checks (bookTicker days, bps)
| asset | quoted, 4h grid | quoted, time-weighted | trade proxy (quoted) | proxy / true | tick | time at 1 tick | Roll | Corwin–Schultz |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BTCUSDT | 0.015 | 0.015 | 0.032 | 2.2× | 0.02 | 59% | 1.03 | 0.73 |
| ETHUSDT | 0.027 | 0.026 | 0.112 | 4.2× | 0.05 | 98% | 1.46 | 0.82 |
| SOLUSDT | 0.172 | 0.171 | 0.404 | 2.3× | 0.31 | 83% | 2.33 | 2.10 |
| AVAXUSDT | 0.329 | 0.331 | 0.572 | 1.7× | 0.62 | 79% | 1.66 | 1.74 |
| OPUSDT | 0.335 | 0.311 | 0.589 | 1.8× | 0.56 | 76% | 1.81 | 2.03 |
| ETCUSDT | 0.267 | 0.272 | 0.440 | 1.6× | 0.52 | 83% | 1.78 | 1.30 |
| BNBUSDT | 0.192 | 0.192 | 0.295 | 1.5× | 0.37 | 88% | 1.09 | 0.90 |
| UNFIUSDT | 0.998 | 0.965 | 1.514 | 1.5× | 1.80 | 76% | 3.39 | 2.11 |
| MATICUSDT | 0.693 | 0.692 | 0.808 | 1.2× | 1.38 | 97% | 1.18 | 1.52 |
| DOTUSDT | 0.912 | 0.916 | 0.965 | 1.1× | 1.83 | 97% | 1.60 | 1.43 |
| XRPUSDT | 0.899 | 0.903 | 0.924 | 1.0× | 1.81 | 99% | 1.62 | 1.41 |
| ADAUSDT | 1.397 | 1.398 | 1.491 | 1.1× | 2.80 | 99% | 1.91 | 1.83 |
| SANDUSDT | 1.208 | 1.195 | 1.230 | 1.0× | 2.39 | 97% | 1.66 | 1.56 |
| GMTUSDT | 2.272 | 2.258 | 2.159 | 0.95× | 4.52 | 98% | 2.89 | 2.19 |
| APEUSDT | 2.702 | 2.692 | 2.635 | 0.97× | 5.37 | 93% | 3.10 | 2.61 |

- **Tick-bound assets** (ADA, APE, DOT, GMT, SAND, XRP, MATIC) sit at a
  one-tick spread 93–99% of the time. The trade proxy is within 15% of the
  truth for them.
- **Tight-spread assets:** the proxy overstates by 1.5–4×, because the last
  buy and last sell prints are stale. Their proxy months use proxy × the
  overlap ratio (PLAN rule: more than 25% off).
- **The half-spread is floored at tick/2** (review fix). The ratio was
  fitted in 2023–24, and applied to other months it pushed values below
  one tick after prices fell. The floor binds on 217 proxy asset-months,
  mostly 2025–26. It also binds on 69 bookTicker months, but moves them by
  < 6% (median 0.8%), a median-price artefact.
- The quoted spread can be lower than half the "tick" column in a given
  month, because tick bps use the month's median price.
- For BTC, the trade-derived tick (used for the floor) comes out below the
  true 0.1 USD tick. The floor never binds there.
- **Roll and Corwin–Schultz disagree with the measured spreads by up to
  ~70× (BTC)**, so they are not usable as spread estimates for these
  assets at 1m. (Why they fail is not tested here.)

## Over time (cost table, 4h-grid orders, full span, tick-floored)
| asset | half-spread 2022 | 2023 | 2024 | 2025 | 2026 (Jan–Aug) | taker all-in 2026 | maker all-in 2026 |
|---|---:|---:|---:|---:|---:|---:|---:|
| BTCUSDT | 0.03 | 0.02 | 0.02 | 0.01 | 0.01 | 5.01 | 3.28 |
| ETHUSDT | 0.04 | 0.03 | 0.02 | 0.02 | 0.02 | 5.02 | 2.93 |
| SOLUSDT | 1.13 | 0.23 | 0.10 | 0.14 | 0.59 | 5.59 | 3.80 |
| OPUSDT | 0.59 | 0.38 | 0.33 | 0.81 | 3.98 | 8.98 | 6.21 |
| DOTUSDT | 1.00 | 1.03 | 0.93 | 1.49 | 3.70 | 8.70 | 7.16 |
| GMTUSDT | 1.26 | 2.15 | 1.50 | 1.65 | 4.51 | 9.51 | 6.70 |
| APEUSDT | 1.35 | 2.40 | 1.11 | 1.43 | 3.95 | 8.95 | 6.10 |

As alt prices fell, their fixed tick sizes grew to 4–8 bps of price by 2026.
That puts a floor under their spreads: **OP went from 0.3 to 4.0 bps of
half-spread**, and its top-of-book taker cost is now 9 bps. The full table
is `costs_table.csv` (= `data/bars/costs.parquet`); `method` records
bookTicker / proxy / proxy_calibrated and "+tick_floor".

## Limitations
- **The fill model has no order size and no queue.** It needs a print
  strictly through our price, then assumes the whole order fills at that
  price. This is optimistic where the top of book is thin (ETC $1.7k, OP
  $1.6k, UNFI $0.5k median).
- Fees are VIP0 throughout (2 / 5 bps); tiers and rebates are not modelled.
- **Taker costs in the decision table and cost table are for
  top-of-book-sized orders.** At $10–50k, use the size table above (2
  days, 6 assets).
- **Sampling:** 4 days per month. Posts are at t ≤ 19:00 UTC. Proxy posts
  at 00:00 have no earlier trade and are dropped. There are ~270–300
  p04-time orders per asset pre-OOS.
- **Proxy months** (all except 2023-05 → 2024-03) rest on a calibration
  fitted on those 11 months, plus the tick floor.
- **Maker costs in proxy months are not tick-floored.** Treat 2025–26 maker
  values as ±1 bps.
- **The cost table is for costing only.** Each monthly value averages days
  later in that month, so using it as a feature or a trade filter would
  leak.
- p04's breakevens are optimistic PurgedKFold numbers with large s.e. The
  PurgedKFold → walk-forward drop seen for BTC in p03 would lower them.

## Harness changes (tests 37/37, selftest HARNESS OK)
- `harness/costs.py`:
  - loaders for bookTicker and aggTrades (with or without a header row);
  - `quote_asof` (causal, last quote ≤ t) and `trade_proxy_quotes`;
  - time-weighted and effective half-spread;
  - Roll and Corwin–Schultz;
  - `simulate_maker` (strict trade-through fill, taker completion after T,
    shortfall and markouts);
  - `overlap_calibration`, `monthly_cost_table` (tick floor) and
    `load_cost_table`;
  - `TableCostModel`, which gives a per-asset, per-month **all-in** cost
    (fees included), e.g. `taker_all_in_bps` or `maker_all_in_bps`.
- `run_backtest` and `run_portfolio_backtest` accept a time-varying cost
  model (`per_unit_at`). The portfolio version also takes
  `{asset: cost model}`. It looks up a table cost only on bars where that
  asset trades: inside a data gap too, and for the exit fill after a
  delisting, priced at the last listed month. A missing month on a traded
  bar raises. A constant
  table reproduces `CostModel` exactly (tested).
- The tests cover the strict fill rule, timeout and taker completion,
  shortfall and markout arithmetic, `quote_asof` causality,
  time-weighting, Roll on a known bounce, the table builder's
  source/calibration/tick-floor choices, delisted-asset and data-gap
  portfolio costs, and the loaders.

No strategy has been re-run with the new costs (spec).
