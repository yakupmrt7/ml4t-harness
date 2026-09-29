# p21 — OTM index option premium (CBOE Iron Condor index, CNDR), 1986–2021: KILLED on dev (all three kills)

**Verdict: this one strategy — the monthly 20/5-delta SPX iron condor — shows no alpha over 1986–2021 as a whole, and
none since 2010; its pre-2010 alpha depends on generous cost assumptions.** Net of measured costs, CNDR's monthly excess return has alpha
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
- **Zero-premium benchmark (kill 2):** a condor priced fairly by Black–Scholes at the market's own volatility (15.5%/yr)
  earns a simulated regression alpha of +1.10 ± 2.50%/yr (lognormal); CNDR's net alpha is below it (t −0.28). The
  simulated condor carries about **twice CNDR's risk** (no skew puts the 5-delta wing close: credit/collateral 2.71% vs
  1.27% on SPY condors 2010–21, monthly sd 4.3% vs 2.0%, beta −0.22 vs +0.16); scaled to CNDR's size the benchmark alpha
  is ≈ +0.5%/yr and kill 2 still fires (t ≈ 0.2) — it is redundant with kill 1 (review). The **bootstrap variant is not
  a zero-premium benchmark**: it prices at flat 15.5% vol but settles on actual monthly returns, which are more peaked
  than lognormal (66.9% of months inside the short strikes vs 59.6%), so its +4.2%/yr is what a no-skew market would
  have paid; it is not used for any conclusion.
- **By decade (net):** 1980s (42 months) +0.8%/yr alpha (t 0.19); 1990s +4.2% (t 1.95); 2000s +3.9% (t 1.97); 2010s
  −3.3% (t −1.39); 2020–21 −6.2% (t −1.22). **Pooled, the pre-2010 alpha clears the bar: 1986-07 → 2009 +3.19%/yr (NW t
  2.28); 1990 → 2009 +3.63%/yr (t 2.55)** (review). That split was chosen after seeing the decades, and two caveats push it
  down: costs before 2010 are generous (SPY options only from 2005; SPX quoted in 1/16–1/8 ticks, so the 2010–21 SPY median
  of 4.2% of credit is the cheapest possible choice for exactly the years with the alpha), and pre-2015 CNDR is a
  back-fill from an undocumented source (1986–89 has 3–9 zero-return days a year). **After 2010 the alpha is −3.76%/yr
  (t −1.74): it vanished — not significantly negative — and the change is significant (−7.6%/yr, t −3.4).**
- Tail (net, monthly): CVaR(5%) −6.2%, worst month −10.6% (1987-10, 59 mean months), 2008-10 −7.2%, 2020-03 −4.2%,
  max drawdown −31%. PSR 0.95 on a series with skew −2.0 (the mean is positive; it is not a premium beyond beta); the DSR
  promised in PLAN was not computed (3 selection rows; it would be at most the PSR).
- Kill 3 is a point rule: each Sharpe has s.e. ≈ 0.17, and the gap to the market (−0.26) has t ≈ −1.4. CNDR rolls on the
  third Friday while the regression and simulation use calendar months (a small mismatch). The cost is that of a SPY
  copy of the condor, not of CNDR on SPX.

## What this means
- Together with p20 (ATM puts on SPY 2010–2021: levered beta) and p16 (BTC options: tail), three pre-registered
  short-volatility tests have failed. **Scope:** this closes the monthly 20/5 SPX condor; it says nothing about put-writing
  (PUT), naked strangles, weekly/0DTE options, delta-hedged variance or VIX futures. Per the p20 review's rule, short
  volatility is abandoned after three failures, and PUT/BXM/VIX-roll variants are not opened.
- The review of p20 recommended dropping short volatility after a third failure: next is NEWPLAN2 #2 (long straddles
  into earnings — the long side of volatility, where the enemy is the spread, not the tail).

## Files
`PLAN.md` · `run.py` · `dev.json`, `dev.log` · `spy_condor_costs.csv` · `selection_trials.json`.
