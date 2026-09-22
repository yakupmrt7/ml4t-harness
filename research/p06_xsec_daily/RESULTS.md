# p06 daily cross-sectional sorts on the 15 p04 perps

**Verdict: KILLED pre-OOS. None of the four pre-registered factors passes.**
The kill fixed in PLAN.md was: gross **t ≥ 2** AND **breakeven ≥ 2× traded
cost**. No factor clears t = 2; the best is basis change at t = 1.61 over
609 decision days. No OOS run, `trials.json` unchanged (3 trials). The four sorts are
logged as 4 rows in `selection_trials.json`.

| factor | long | t (gross) | SR gross | SR net | SR price-only | breakeven bps | traded cost bps | turnover /yr | verdict |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| carry (3d cum funding) | lowest | +0.12 | +0.09 | −0.47 | −0.65 | 1.4 | 8.9 | 938 | fail (t, breakeven) |
| basis change (1d) | lowest | +1.61 | +1.24 | −1.16 | +1.03 | 4.7 | 9.0 | 3,958 | fail (t, breakeven) |
| 1-day reversal | lowest | −0.79 | −0.61 | −2.41 | −0.65 | −3.1 | 9.0 | 3,388 | fail (both) |
| momentum (28d, skip 1d) | highest | +1.23 | +0.95 | **+0.55** | +0.99 | **21.0 ± 17.1** | 8.8 | 778 | fail (t only) |

Sharpe is on daily P&L, annualised by √365. There are **609 decisions and
610 daily buckets** (the first bucket is an empty stub at the 04:00 bar that
opens the grid); t = SR·√(610/365) = SR × 1.29. One s.e. on these Sharpes is
about 0.78. Breakeven s.e. = std(daily gross)·√n / turnover; for the other
three factors it is 12.3 (carry), 2.9 (basis change) and 3.9 (reversal).

Daily P&L is close to serially uncorrelated (lag-1 autocorrelation −0.02 to
−0.08), so the iid t is not optimistic: Newey-West(10) gives 0.13 / 1.50 /
−0.89 / 1.26 for the four factors, against 0.12 / 1.61 / −0.79 / 1.23.

- **Momentum is the only one that meets the economic half of the test, and
  only on the point estimate.** It breaks even at 21.0 bps per unit traded
  against a measured cost of 8.8, i.e. 2.4×, which clears the "2× cost"
  condition as written. But the breakeven's own s.e. is 17.1 bps: one s.e.
  down is 3.9 bps, below the cost. Its t is 1.23, so it fails the
  statistical half outright. It is the only factor with a positive net
  Sharpe (+0.55). Its 2024-Q1 gross Sharpe is −2.89, against +2.07 in 2023.
  A portfolio shift null (all assets shifted by one offset, 300 draws) puts
  its gross Sharpe at **p = 0.087**: not significant either.
- **Basis change has the highest t (1.61) but trades too much.** At 3,958
  units/yr it breaks even at 4.7 bps against 9.0 of cost, so its net Sharpe
  is −1.16 despite a positive gross.
- **Carry's gross is almost entirely funding.** Funding is 8.2× gross,
  because the price leg loses (price-only SR −0.65) and funding pays for
  it. Net of costs it loses.
- **1-day reversal is negative pre-OOS**, i.e. the p01–p04 short-horizon
  reversal does not survive at a 1-day horizon in cross-section. Its 2022
  gross Sharpe is −2.25.
- **The four factors are close to independent**: mean daily cross-sectional
  rank correlations are between −0.07 and +0.08. Combining them would not
  have rescued the t-stats, and the kill does not allow it.

Reproduce (repo root):
- `PYTHONPATH=.:research/p05_costs python research/p05_costs/impact_check.py --assets BTCUSDT ETHUSDT BNBUSDT AVAXUSDT MATICUSDT DOTUSDT SANDUSDT XRPUSDT GMTUSDT --out research/p06_xsec_daily/impact_other9.json`
- `PYTHONPATH=. python research/p06_xsec_daily/selection.py`

## Setup (all fixed in PLAN.md before any factor data was loaded)
| | |
|---|---|
| Universe | the 15 p04 perps; all live through the pre-OOS window |
| Decision | daily at the 04:00 UTC 5m close (a time on p05's measured cost grid), delay = 1, held 24 h |
| Book | long the 3 best, short the 3 worst, ±1 unit ($10k) each; dollar-neutral, $60k gross |
| Window | decisions 2022-08-01 → 2024-03-31 (609), P&L to 2024-04-01 04:00 |
| Costs | p05 `taker_all_in_bps` per asset-month + a constant per-asset $10–50k impact add-on, floored at 0 |
| gross | price P&L **+ funding P&L** (funding is part of a perp's return, and is the point of carry); net = gross − trading cost |
| Data | 5m klines, settled funding, 5m premium index, all ≤ 2024-04. Nothing after the pre-OOS window was downloaded or read |

Factor coverage is 100% of asset-days except basis change (99.5%, from
premium-index gaps). A causality check re-computed each factor at 5 random
dates from data truncated at that date and got identical values.

**Impact add-ons** (bps, = effective half-spread of $10–50k taker orders
minus the quoted half-spread at order times, from 2 bookTicker days):
BTC 0.14, ETH 0.17, XRP 0.71, BNB 1.30, ADA 1.70, SOL 1.74, DOT 2.07, MATIC
2.40, GMT 2.47, APE 2.59, ETC 2.83, AVAX 3.01, OP 3.63, SAND 4.01, UNFI
14.08. With the table's fee + spread, the traded cost comes to 8.8–9.0 bps
per unit across the four factors, because the sorts trade the alts most.

## Per-year gross / net Sharpe
| factor | 2022 (153 d + 1 empty stub) | 2023 (365 d) | 2024 Q1 (91 d) |
|---|---|---|---|
| carry | +0.19 / −0.29 | −0.13 / −0.72 | +0.86 / +0.27 |
| basis change | +2.26 / −0.17 | +0.43 / −2.04 | +2.61 / +0.42 |
| 1-day reversal | −2.25 / −4.11 | −0.19 / −1.93 | +0.34 / −1.60 |
| momentum | +0.24 / −0.16 | +2.07 / +1.69 | −2.89 / −3.40 |

No factor is consistent across the three sub-periods. A 91-day Sharpe has
an s.e. of about 2.0, and a 154-day one about 1.6, so these swings are
mostly noise — which is the point: nothing here is stable enough to trade.

## Long/short split
| factor | long-leg SR | short-leg SR | beta to the 15-perp equal-weight index | SR gross, beta-hedged |
|---|---:|---:|---:|---:|
| carry | +0.84 | −0.76 | −0.05 | +0.11 (vs +0.09) |
| basis change | +0.98 | −0.15 | +0.14 | +1.19 (vs +1.24) |
| 1-day reversal | +0.36 | −0.78 | −0.02 | −0.61 (vs −0.61) |
| momentum | +1.07 | −0.35 | −0.12 | +0.99 (vs +0.95) |

Every factor earns on the long leg and loses on the short leg, which looks
like residual long exposure — crypto rose over this window. **Measured, it
is not:** each book's beta to the equal-weight universe is between −0.12
and +0.14, and hedging that beta out changes the Sharpes by at most 0.05
(it raises momentum's, from 0.95 to 0.99). The legs' market exposures
cancel; the asymmetry is market drift passing through both legs, not
uncontrolled beta. (An earlier draft of this file asserted the opposite
without measuring it.)

## Reading it
- **Nothing here is tradable, and the failure is statistical, not just
  economic.** Momentum is the one factor whose edge per trade (21 ± 17 bps)
  exceeds cost (8.8) on the point estimate — the first time in p01–p06 that
  a signal has cleared the cost wall at all. Its problem is that 609 decision
  days give t = 1.23, and a shift-null p of 0.087: it could easily be luck.
- **The horizon change did what p05 predicted, on point estimates.** Moving
  from 4 h to 1 day cut turnover from ~1,700 units/yr (p04) to 778
  (momentum) and raised the edge per trade from 0.3–6 bps to 21 ± 17. Cost
  is no longer obviously the binding constraint; sample size now is.
- **A t of 1.23 needs about 4× the sample to reach t = 2.5** if the true
  Sharpe is what we measured ((2.5/1.23)² = 4.1). That is 6–7 years of
  daily decisions, and we have 1.7 years pre-OOS.
- **The design had little power, which the kill could not distinguish from
  "no edge".** Reaching t = 2 on 609 days needs an annualised Sharpe of
  about 1.55 from a 3-long / 3-short book in a 15-asset universe. A
  genuinely good factor (true Sharpe ≈ 0.8) would be expected to produce
  t ≈ 1.0 here. The kill was pre-registered and stands, but p06's real
  output is as much a power measurement as a verdict on these factors.

## Next (not run; for the owner to decide)
The reviewer proposes p07: **the same momentum sort, book frozen, on
2020-10-01 → 2022-07-31** — a window this repo has never read. One variable
changes (the sample). Costs would be a flat 12 bps per unit, above every
2022–24 measured value, because the p05 table starts in 2022-08 and must
not be extrapolated backwards. Kill: abandon the line if that window's
gross SR ≤ 0 or breakeven < 12 bps; go to the OOS gate only if both windows
have SR ≥ +0.5, pooled t ≥ 2.0 and pooled breakeven − 1 s.e. ≥ 12 bps.
Cost: 1 selection trial, 0 OOS trials, ~470 kline files, minutes of compute.
Full text in `REVIEW.md`.

## Harness changes (tests 39/39, selftest HARNESS OK)
- `TableCostModel(..., add_bps=)`: constant add-on for size impact.
- `portfolio.funding_pnl(held, funding)`: funding charge per asset on the
  portfolio grid, same arithmetic as `run_backtest` (tested against it).
- `research/p06_xsec_daily/followups.py` (reporting only): breakeven s.e.,
  market beta and beta-hedged Sharpe, Newey-West t, and the momentum shift
  null.
- `research/p05_costs/impact_check.py` gained `--assets` / `--out` and
  per-(asset, day) caching, so a network failure resumes instead of
  redoing the work. Its defaults and measurements are unchanged.
