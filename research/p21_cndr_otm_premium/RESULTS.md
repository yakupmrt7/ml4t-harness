# p21 — OTM index option premium (CBOE Iron Condor index, CNDR), 1986–2021: KILLED on dev (all three kills)

**Verdict: the out-of-the-money premium in S&P 500 options is not there after beta, costs and a fair-pricing benchmark
over 1986–2021, and it turned negative after 2010.** Net of measured costs, CNDR's monthly excess return has alpha
**+0.75%/yr (NW t 0.61)** against the market, **does not beat a zero-premium condor** (excess over the lognormal
simulation t −0.28), and its Sharpe (0.31) is **below the market's** (0.57) over the same 426 months. Per PLAN, no
holdout run; `trials_eqvol.json` is not created.

Plan: `PLAN.md` (dd99851); code committed before running (see git log). Data: CNDR daily levels (CBOE, back-filled
to 1986; options priced at mid before 11:00 ET; T-bill account = 10 × max loss), Kenneth French monthly Mkt-RF and RF.

## Numbers (dev 1986-07 → 2021-12, 426 months; excess over T-bills; NW lag 3)
| | %/yr | vol %/yr | Sharpe | beta | alpha %/yr | alpha t | worst month |
|---|---:|---:|---:|---:|---:|---:|---:|
| gross (CNDR as published, mid prices) | 2.77 | 7.03 | 0.40 | 0.16 | +1.39 | 1.12 | −10.5% (1987-10) |
| **net of median measured cost (kill book)** | **2.14** | 7.03 | **0.31** | 0.16 | **+0.75** | **0.61** | −10.6% |
| net of stressed (Q3) cost | 1.98 | 7.03 | 0.28 | 0.16 | +0.60 | 0.48 | −10.6% |
| market (Mkt-RF), same months | — | — | 0.57 | 1 | — | — | — |

- **Costs** (`spy_condor_costs.csv`, 140 SPY cycles 2010–2021, the same 20/5-delta condor): half-spreads plus fees =
  **0.053%** of the index per month (median; 4.2% of the credit), 0.066% at the upper quartile. Costs are not what kills
  it; the gross alpha is t 1.1.
- **Zero-premium benchmark:** a condor priced fairly at the market's own volatility (15.5%/yr) earns a simulated alpha of
  **+1.10 ± 2.50%/yr** (lognormal) and **+4.17 ± 2.50%/yr** (bootstrap of actual monthly returns): the regression
  "alpha" of a short-option book is positive even with no premium. CNDR's net alpha is below both (t −0.28 and −2.75).
- **By decade (net):** 1980s (42 months) +0.8%/yr alpha (t 0.19); **1990s +4.2% (t 1.95); 2000s +3.9% (t 1.97); 2010s
  −3.3% (t −1.39); 2020–21 −6.2% (t −1.22)**. Whatever premium existed before 2010 was below the t ≥ 2 bar in each decade
  and reversed afterwards, consistent with the publication/crowding story and with CNDR's roughly flat level since 2010.
- Tail (net, monthly): CVaR(5%) −6.2%, worst month −10.6% (1987-10, 59 mean months), 2008-10 −7.2%, 2020-03 −4.2%,
  max drawdown −31%. PSR 0.95 (the mean is positive; it is not a premium beyond beta).

## What this means
- Together with p20 (ATM puts on SPY 2010–2021: levered beta) and p16 (BTC options: tail), three pre-registered
  short-volatility tests have failed. The equity index option premium that the 1990s–2000s literature documented is
  not tradeable as a stand-alone strategy for a retail account today: after beta it was modest even then and negative
  since 2010.
- The review of p20 recommended dropping short volatility after a third failure: next is NEWPLAN2 #2 (long straddles
  into earnings — the long side of volatility, where the enemy is the spread, not the tail).

## Files
`PLAN.md` · `run.py` · `dev.json`, `dev.log` · `spy_condor_costs.csv` · `selection_trials.json`.
