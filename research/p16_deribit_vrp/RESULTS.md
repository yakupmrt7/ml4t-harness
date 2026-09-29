# p16 — Deribit BTC variance risk premium (weekly short ATM straddle, delta-hedged): KILLED at kill 3 (dev)

**Verdict: a thin, fragile carry that does not pay for its tail.** On 156 dev weeks (2022-08 → 2025-08),
selling the 7-day ATM BTC straddle every Friday and delta-hedging it daily earns **+9.1% of premium net**
(13.7% gross) with **t = 2.17**, so kills 1 and 2 pass as registered — narrowly, and with biases in their
favour (see Review). But the worst week loses **13.1 × the mean week**
(2025-02-28: −$3,444 per 1 BTC vs a mean of +$263), above the pre-registered 12× bar: **kill 3 fires**.
The verdict does not depend on the unit (in return on notional the worst week is 18.7× the mean; in % of
premium 25.5×), and every reported variant also fails kill 3 (12.3–15.2×). No holdout was read and no trial
is logged in `trials_vrp.json`.

Plan: `PLAN.md` (45105ca) and amendment 1 (0d4334d, after step 0, before any P&L). Split fixed from dates
only (f44ff31). Harness: `cvar`, `tail_report` (9075fcf, tests + selftest).

## Setup
| | |
|---|---|
| Trade | every Friday 08:05 UTC, sell the ATM straddle (listed strike nearest the forward) of the next Friday's 08:00 expiry, valued on Deribit's mark surface (smile fitted on that expiry's trade marks in the prior hour); settle on the **official Deribit delivery price** |
| Hedge | Binance BTCUSDT perp, Black-76 straddle delta at entry IV, at entry and daily at 08:05; closed at the expiry 08:00 bar; funding paid/received |
| Costs | measured effective half-spread (trailing 3-month median, % of mark; 0.55% median over the span), Deribit option fee 0.03% of index capped at 12.5% of price per leg, delivery fee 0.015% on the ITM leg, 5.5 bps premium conversion, 5.5 bps taker on hedge turnover |
| Sample | 159 dev Fridays, **156 traded** (no entry smile on 2022-12-30, 2023-06-09, 2024-04-05); non-overlapping weeks; Sharpe s.e. ≈ 1/√3 yr = 0.58 |

## Kills (dev, net, main configuration)
| kill | value | bar | |
|---|---:|---:|---|
| 1. mean net P&L, % of premium (Σ net / Σ premium) | **+9.13%** | ≥ 2% | pass |
| 2. t of weekly return on notional | **2.17** | ≥ 2 | pass |
| 3. worst week / mean week (USD per 1 BTC) | **13.08×** | ≤ 12× | **FIRES** |

## Verdict block (substitute for `validation_report`, per PLAN)
```
weeks 156 (3.0 yr)            Sharpe annual 1.26 ± 0.58     PSR 0.980   DSR 0.962 (5 selection rows)
mean net +$263 / week / BTC   hit rate 62%                  skew +0.38  kurtosis 4.36
CVaR(5%) −$2,399              worst week −$3,444 (2025-02-28)   worst/mean 13.1×  -> kill 3
max drawdown −$7,241 (ends 2024-08-30)
gross 13.7% of premium; costs 4.54 pts: hedge 2.10, option fees 1.14, spread 0.53, delivery 0.28,
  conversion 0.06, funding 0.43 (PAID: the `funding` column is funding received and sums to −0.43%)
halves: first 78 wk +7.2% of premium (t 1.35); second 78 wk +9.8% (t 1.74)
```

| variant (reported, not used for the kills) | net % premium | t | worst/mean | Sharpe/yr |
|---|---:|---:|---:|---:|
| main | 9.13% | 2.17 | 13.1× | 1.26 |
| maker (sold at mark, no spread) | 9.66% | 2.34 | 12.3× | 1.35 |
| stressed cost (h ≥ 1.5% of mark) | 8.16% | 1.89 | 14.9× | 1.10 |
| hedge at the daily ATM IV | 9.66% | 2.11 | 12.3× | 1.22 |
| entry one hour later (09:05) | 7.77% | 1.71 | 15.2× | 0.98 |

Stress weeks (dev): FTX (entry 2022-11-04) −$863 = −3.3 mean weeks; SVB/USDC (2023-03-03 and 03-10) −$717
= −2.7; the 2024-08-02 carry unwind −$2,106 = −8.0. The worst weeks are not the famous crashes. In return
terms 8 of the 10 worst weeks were up-weeks (base rate 58%), led by 2023-01-13 (the January 2023 short
squeeze, −7.3% of notional); in USD terms only 5 of 10, and the USD-worst week 2025-02-28 was a whipsaw
(79.3k → 92.4k → 83.3k → 88.3k: premium $5,597 − payoff $9,286 + hedge $480 − costs $235 = −$3,444).

## What this means
- **There is no clearly established premium in this sample.** Entry IV exceeds 5-minute realised vol in 68%
  of weeks, but that is a median effect of right-skewed realised vol: the mean gap is 1.25 vol points
  (t 1.03), and in variance terms IV² − RV² ≈ −0.002 (t −0.14) (review). Part of the gross P&L is a sampling
  effect a once-a-day hedge collects (daily-sampled realised variance is 0.91× the 5-minute one). The net
  carry is ~$260 per BTC-week on a premium with IQR $1,370–4,286, and its t is fragile: 1.35 / 1.74 in the
  two halves, 0.28 in 2023, 0.87 in 2024, 1.71 with a one-hour-later entry.
- **The tail rule is what kills it**, and narrowly: one week costs 13 weeks of income, a drawdown of ~27 mean
  weeks (−$7,241) sat inside dev, and the t-stat is only 2.2 over three years. An unconditional short-vol
  book in BTC is a bet that the next squeeze is no worse than the last ones — and the holdout contains
  2025-10-10, the largest liquidation day on record.
- **Hedge costs are the biggest drag** (2.1 of 4.54 cost points): daily re-hedging a short-gamma book at taker
  prices. The spread charged (0.55% of mark) is probably low: Deribit's 0.0005 BTC tick is ~1.2–1.5% of an
  ATM weekly leg, implying a half-spread of ~0.6–0.75%; the stressed-cost variant already fails kill 2 (t 1.89).

## Review
`REVIEW.md` (research-reviewer, pre-OOS): **ACCEPT WITH FIXES; the kill stands.** Four weeks (2025-02-28,
2023-01-13, 2024-08-02, 2023-10-20) re-run with independent code match `step1_weeks_main.csv` to $0.1; hedge
and funding signs, delivery keying and every window were checked; no look-ahead; commit order plan →
harness → step 0/split → amendment → P&L. Points that weaken kills 1–2 (all favour a pass, so the kill is
conservative):
- **Premium from the smile, not the marks:** the quadratic smile values the ATM straddle 0.9% (median) above
  the raw ATM marks; valued at the marks, **t = 1.91 and kill 2 would also fire**.
- **Kill 3 in USD depends on hedge cost** (11.4× at 2.5 bp, 10.2× at 0 bp would pass), but in return on notional
  it fires at every hedge cost (16.0×, 14.3×); it rests on one week (the second worst is 10.7×).
- **Holdout power:** 53 weeks would have reached t ≥ 2 with ~23% probability even if the dev edge were real.
- **Harness disclosure:** the `tail_report` date-only-end fix (e17354f) was made after the P&L existed. It
  changes reporting only (stress windows), not the kills; tests and selftest pass.

## Not tested
Defined-risk structures (iron fly / bought wings) that cap the tail, other tenors, ETH. The HAR-RV/LightGBM
timing layer was conditional on this book passing (PLAN), so it is not run; a timing model on a book whose
unconditional variance premium is ≈ 0 in this sample has little to condition.

## Files
`PLAN.md` · `common.py` · `step0.py` (costs, coverage, settle, split) · `step1.py` · `split.json` ·
`step0_costs_by_month.csv`, `step0_settle.json`, `step0_coverage.csv` · `step1.json`, `step1.log`,
`step1_weeks_main.csv` · `selection_trials.json`.
