# p21 — Out-of-the-money index option premium: CBOE Iron Condor index (CNDR), 1986 → 2026

Written 2026-09-29 before any CNDR return, alpha or cost was computed. Proposed by the p20 review (the ATM version was
closed; the premium is thought to sit in OTM options, which p20 never sold). Read so far: the CNDR methodology PDF
(v4.1), its daily level file (the first and last two rows were printed while checking the download), and a web search
snippet stating CNDR's 2010–2024 compound return was about −0.7%/yr. **The holdout period is therefore partly known**
(disclosed; it weakens the holdout, it does not change the rules).

## Line and change vs p20
- Line: equity index option premia (`trials_eqvol.json`, still absent). Change vs p20: the options sold are
  **~20-delta OTM** put and call (CNDR), not ATM, with ~5-delta wings; the book is CBOE's own rules-based index, not our
  construction; the history starts in 1986.

## Market reasoning (for the owner)
Index option buyers pay most for protection far from the money; a short 20-delta strangle with 5-delta wings (an iron
condor) collects that, earns when the index stays in range, and loses a capped amount when it moves far. CNDR holds a
T-bill account of 10× the maximum loss, so ~10% of the index is at risk each month and its return is small and steady
when it works. The question is whether that return is a premium beyond market beta and beyond what a fairly priced
condor would earn, after trading costs.

## Data (free)
- CNDR daily levels, CBOE (`CNDR_History.csv`), base 1986-06-20 (back-filled; launched 2015). Options priced at the
  **mid** of the last quote before 11:00 ET on the third Friday; AM-settled SPX; T-bill account = 10 × max loss.
- Kenneth French data library, monthly Mkt-RF and RF (US market, from 1926).
- CBOE SPX daily closes (volatility and drift for the simulation).
- Costs: the dev SPY option chains of p20 (2010–2021) to measure the spread of the 20- and 5-delta legs.

## Split (fixed now)
**Dev = 1986-07 → 2021-12 (calendar months); holdout = 2022-01 → 2026-08.** Monthly returns from month-end CNDR levels.

## The book and its costs
- Monthly excess return r = CNDR month return − RF.
- **Costs (CNDR trades at mid):** a taker pays half the bid–ask spread on each of the four legs at entry (held to
  cash settlement, no exit). For each p20 dev cycle (2010–2021) the same condor is built on SPY at entry (strikes nearest
  |delta| 0.20 and 0.05, target monthly expiry), and the cost per cycle in index units is
  c = Σ legs (half-spread + $0.0065 fee) / (10 × max loss), max loss = wing width − net mid credit (per share).
  The median c over 2010–2021 is deducted from every month (1986–2009 included, disclosed), and the maximum
  2010–2021 quartile reported as a stressed cost.

## Kills (dev, net of costs)
1. **Premium, not beta:** regress monthly r on Mkt-RF: alpha ≤ 0 or Newey–West (lag 3) **t < 2** → KILL.
2. **Premium, not option convexity:** a zero-premium simulation — 2,000 paths of lognormal monthly SPX returns at the
   dev drift and volatility, each month's condor priced by Black–Scholes at that same volatility (20/5-delta strikes,
   T-bill account 10× max loss), the same regression per path. KILL unless (alpha − mean simulated alpha) / NW s.e. of
   alpha **≥ 2**.
3. **Worth holding:** Sharpe ratio of r ≤ Sharpe of Mkt-RF over the same months → KILL.
Reported: gross vs net, alpha by decade, 1987-10 / 2008-10 / 2020-03 months, CVaR, drawdown, a bootstrap version of
the simulation (resampling actual SPX monthly returns), and the stressed cost.

## Holdout (2022-01 → 2026-08)
Only if dev passes 1–3 and the review accepts: one run, kills 1 and 3 on the holdout (kill 2's simulation re-run with the
holdout's drift and volatility), logged as one trial in `trials_eqvol.json` after the owner's "go".

## Rules
No model and no features (rules 9–10 do not apply). One configuration; reported variants are `measurement` rows in
`selection_trials.json`. `validation_report` substitute: the NW alpha regression, the simulation benchmark, PSR/DSR on
the monthly series, and the gross/net and stressed-cost bracket.
