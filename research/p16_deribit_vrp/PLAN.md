# p16 — Variance risk premium on Deribit BTC options: weekly short ATM straddle, delta-hedged

Written 2026-09-29, before any option P&L, realised-vs-implied comparison or cost measurement was run for
this experiment. Source: NEWPLAN.md idea #2, as proposed by the p15 review (research/p15_pm_deribit_threshold/
REVIEW.md, "Proposed next experiment"). The owner started it on 2026-09-29. What has been looked at so far:
Deribit's published fee rules, the list of Deribit delivery prices (fetched, not analysed), the file listing
of the option-trade tape on disk. Nothing below changes after numbers are seen; anything decided on data goes
into a dated amendment committed before the step that uses it.

## Line and scope
- **New line: option risk premia (Deribit).** Not the closed 1h/4h bar-direction line (no direction is
  predicted; the book is delta-hedged), not p15 (a cross-venue probability gap).
- **Single change vs p15:** the target. p15 measured a price gap between two venues; p16 measures the realised
  P&L of an unconditional short-volatility position. No model, no features, no parameter search.
- **Trial log:** `trials_vrp.json` (created only by the one holdout run). Not `trials.json`, `trials_hl.json`
  or `trials_pm.json`.

## Market reasoning (for the owner)
Selling an option is selling insurance against large moves. Delta-hedged, a short straddle's P&L over a week is
approximately ½ Γ S² (σ_implied² − σ_realised²) summed over the week: it earns when the move that happens is
smaller than the move the premium priced in, and loses (sometimes a lot) when it is bigger. Across equity index
options this "variance risk premium" is positive on average because buyers pay for crash protection. In BTC the
literature finds a larger premium that comes mostly from *upside* states (short calls hurt in rallies). The
question is not whether implied vol usually exceeds realised vol, but whether what is left after Deribit's
option fees, bid-ask spreads and hedging costs pays for the tail.

## Hypothesis (falsifiable)
A short 7-day at-the-money BTC straddle on Deribit, opened every Friday after the 08:00 UTC expiry, held to the
next Friday's expiry and delta-hedged once a day in the Binance BTCUSDT perpetual, earns a positive mean weekly
P&L after all costs on dev, large enough to clear the kills below.

## Data (all on disk or fetched once, free)
- **Deribit BTC option trades** `data/collector/p11/deribit_opt/` (2022-08-01 → 2026-08-31): instrument, price
  (BTC), trade IV, index price, mark price, amount, taker direction.
- **Deribit official delivery prices** `data/collector/p16/delivery_btc_usd.json` (daily, `public/get_delivery_prices`,
  fetched 2026-09-29 on a throwaway VM because www.deribit.com is blocked from the owner's machine). This is the
  exact settlement price of each expiry (30-minute TWAP of the index before 08:00 UTC), so no proxy is needed.
- **Binance BTCUSDT perpetual** 5m klines (hedge price) and funding rates (hedge carry), data/raw.
- Tardis.dev free first-of-month quotes were planned for spreads but return HTTP 403 from here (geo/Cloudflare);
  costs are measured from the trade tape instead (below).

## The weekly trade (one configuration, fixed now)
- **Entry:** every Friday at 08:05 UTC. Expiry = the next Friday 08:00 UTC (τ ≈ 7 days). Strike = the listed
  strike (one that traded in that expiry on the entry day before 08:05) nearest to the expiry's forward F.
- **Entry price:** each leg valued on Deribit's mark surface at 08:05: a smile fitted on the mark prices of that
  expiry's trades in [07:05, 08:05] (research/p15_pm_deribit_threshold/surface.py: forward from put–call parity,
  mark-IV inversion, quadratic total-variance smile; ≥ 5 distinct strikes). No smile → the week is recorded as
  "no entry" and excluded (counted and reported).
- **Taker sale:** each leg is sold at mark − h, h = the measured effective half-spread (Step 0), plus the
  Deribit option fee min(0.03% × index, 12.5% × option price) per leg. The BTC premium is converted to USD at
  entry (5.5 bps taker on the premium notional).
- **Settlement:** at expiry, payoff |S_T − K| in USD with S_T = the official delivery price. Delivery fee on the
  in-the-money leg: min(0.015% × S_T, 12.5% × payoff) (charged conservatively; Deribit exempts only daily options).
- **Delta hedge:** in the Binance BTCUSDT perp, at entry (08:05 Friday) and every day at 08:05 UTC until the
  Thursday before expiry; closed at the expiry Friday 08:00 bar. Hedge ratio = Black-76 delta of the short
  straddle at the **entry implied vols** (hedging at implied), remaining τ, perp price as S. Hedge cost: 5.5 bps
  taker on every change of hedge notional (p05 BTC taker). Funding paid/received on the hedge at each Binance
  funding time (settled rates, strictly as-of).
- **Accounting (USD, per 1 BTC of straddle notional per leg):**
  P&L = premium received − option fees − half-spread cost − conversion cost − payoff − delivery fee
        + hedge P&L − hedge costs − funding.
  Reported as (a) % of premium received and (b) return on notional, P&L / S_entry.
- Inverse-option BTC premium exposure is removed by converting at entry; Deribit margin and liquidation are not
  modelled (disclosed; a real book posts BTC/USDC margin with a buffer).

## Step 0 — costs and coverage (before any P&L; reported)
- **Effective half-spread** of ATM weekly options: for trades with |ln(K/F)| < 5% and 3–8 days to expiry, h =
  median of (trade price − mark price) × (+1 taker buy, −1 taker sell), in BTC → USD at the trade's index price,
  also as % of the option's mark. By month over the whole span (costs are not an outcome variable; this reads no
  P&L). The per-week h used at entry is the trailing 3-month median known before that Friday.
- **Coverage:** per Friday, whether the entry smile exists and the settlement price exists. Report counts.
- **Settlement check:** delivery price vs Deribit index_price of option trades in [07:30, 08:00] on 20 random
  Fridays (sanity that the file is the right series); gate: median |difference| < 10 bp.

## Split (fixed in Step 0 from dates only, before any P&L)
Calendar span = entry Fridays from the first Friday with data (2022-08-05) to the last whose expiry is inside the
data (≤ 2026-08-28). **Dev = first 75% of that calendar span; holdout = the rest, never read before the one
holdout run.** Written to `split.json` and committed before Step 1.

## Step 1 — the unconditional book (dev)
Weekly P&L series as above. Reported: gross (before all costs) and net; the cost breakdown per component;
implied vs realised vol per week; mean/median/t; hit rate; skew and kurtosis; **CVaR(5%)**, **max drawdown**,
worst week, and **stress windows** in dev: FTX (week of 2022-11-07), SVB/USDC (week of 2023-03-10), the
2024-08-05 unwind; PSR and DSR on the weekly series (DSR trial count from `selection_trials.json` + `trials_vrp.json`);
annualised Sharpe with its standard error ≈ 1/√years.
Robustness (reported, not used for the kill): maker-style variant (sold at mark, no half-spread); hedging at the
daily realised-vol-updated IV (the day's ATM mark IV) instead of entry IV; entry one hour later (09:05); halves of dev.

## Kill criteria (dev, net, fixed now)
1. **Economics:** mean weekly net P&L < +2% of premium received → KILL.
2. **Statistics:** t-stat of the weekly net return on notional (one observation per week, non-overlapping) < 2 → KILL.
3. **Tail:** the worst dev week loses more than 12 × the mean weekly net P&L (USD per notional) → KILL.
A pass on all three goes to review, then to the OOS gate (the owner's "go"), then one holdout run logged in
`trials_vrp.json`. Pass on holdout = the same three conditions.

## Selection hygiene
- One configuration; no parameter is fitted. The robustness variants are `measurement` rows in
  `selection_trials.json`.
- CLAUDE.md rule 10 (fold-id test) and rule 9 (normalised features) apply to learned feature sets; there is no
  model here. The HAR-RV + LightGBM timing layer (NEWPLAN #2) is a later experiment, only if this passes.
- CLAUDE.md rule 8: the weekly P&L series has no bar-signal structure for `validation_report`'s shift null and
  label permutation; the substitute gauntlet is t / PSR / DSR, CVaR, drawdown, stress windows, halves, the
  1-hour-later entry and the maker/taker cost bracket. Its block goes into RESULTS.md.

## Harness change (before any P&L)
Add to `harness/metrics.py`: `cvar(r, alpha)`, `tail_report(pnl, stress_windows)` returning CVaR(5%), max
drawdown, worst period, worst/mean ratio, skew, kurtosis and per-window P&L. Unit tests in tests/test_core.py;
run tests and selftest.

## Known risks, stated before looking
- **The tail is the whole question.** A short straddle is short gamma: FTX-type weeks produce losses of many
  weeks' premium. Kill 3 exists for that; 2025-10-10 (the largest liquidation day on record) falls in the holdout,
  not dev.
- **Mark ≠ tradeable price** in fast markets; the effective half-spread from the tape is an average, and ATM
  weekly spreads widen exactly in stress weeks (reported by month; the stress weeks' cost is not modelled
  separately).
- **Hedging at 08:05 once a day** leaves intraday gamma unhedged; that is part of the P&L being measured, not a
  flaw, but it makes the result specific to daily hedging.
- **Survivorship / selection:** none (every Friday is traded unless the smile is missing).

---

## Amendment 1 — 2026-09-29, after Step 0, before any P&L is computed

**Step 0 results (no P&L read):**
- Settlement: official delivery price vs the mean Deribit index in [07:30, 08:00] on 20 random Fridays: median
  |diff| 1.6 bp (gate < 10 bp) → the delivery file is the right series. (The sample included some holdout
  Fridays; this reads settlement levels, not strategy outcomes.)
- Coverage: 212 entry Fridays; 205 have an entry smile (missing: 2022-12-30, 2023-06-09, 2024-04-05 in dev;
  2026-03-06, 04-17, 04-24, 08-07 in holdout); all 212 expiries have a delivery price. Missing weeks are
  "no entry" and reported.
- Split (split.json, committed f44ff31): **dev = 159 entry Fridays 2022-08-05 → 2025-08-15; holdout = 53,
  2025-08-22 → 2026-08-21.**
- Effective half-spread of ATM (|ln K/index| < 5%) options with 3–8 days to expiry (`step0_costs_by_month.csv`):
  median **0.55% of mark** over all months (monthly medians 0.10%–1.40%), $4.4 per 1-BTC option. 30–47% of
  trades print on the "wrong" side of mark, so mark is not always the mid, and the median may understate a
  lone taker's cost.

**Definitions fixed now:**
- The half-spread charged at entry is in **% of mark** (scale-free): the trailing 3-month median of
  h_pct_mark over trades strictly before that Friday 08:00, times each leg's mark.
- **Stressed-cost variant (reported, not used for the kills):** h = max(measured, 1.5% of mark) per leg, i.e.
  half of the ~3% full ATM spread reported for 2019–20 Deribit (NEWPLAN sources).
- Hedge prices: Binance BTCUSDT perp 5m bar closing at the hedge time (08:05; the expiry close uses the bar
  closing 08:00). Straddle delta (Black-76 on the perp price, entry IV) = 2·N(d1) − 1 for the long; the short
  book holds +(2·N(d1) − 1) BTC of perp. Funding: Binance settled rates at funding times in (t_i, t_{i+1}],
  paid on the position held then (long pays a positive rate).
- Stress windows (entry Fridays, dev): FTX 2022-11-04; SVB/USDC 2023-03-03 and 2023-03-10; carry unwind
  2024-08-02.
