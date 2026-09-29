# p22 — Long ATM straddles into earnings (the implied-volatility run-up), S&P 100, 2020–2026

Written 2026-09-29 before any option price was read for this experiment. Source: NEWPLAN2.md #2, proposed as the next
experiment by the p20 and p21 reviews after three short-volatility failures (p16, p20, p21). Read so far: schemas and
row counts of DoltHub `post-no-preference/options` (option_chain) and `post-no-preference/earnings`
(earnings_calendar), their snapshot calendar for AAPL, and metadata of Kaggle AAPL/TSLA chains.

## Line, trial log, single change
- New line: **event volatility** (US single-stock options; tradeable via IBKR). Trial log `trials_earn.json`
  (created only by a holdout run).
- Change vs the short-vol experiments: **long** volatility, over a known event; the enemy is the bid–ask spread paid
  twice, not a crash tail.

## Market reasoning (for the owner)
Before an earnings announcement, the market knows a jump is coming, and implied volatility of options expiring after the
announcement rises into it. Gao, Xing & Zhang (JFQA 2018) find ATM straddles held from about 3 days before the
announcement to the announcement earned +3.34% on average (1996–2013), strongest in smaller and more volatile stocks:
investors under-price the coming uncertainty. We **exit at the last close before the announcement**, so the trade
collects the run-up and never holds through the jump or the post-event volatility crush.

## Data (free)
- Option quotes: DoltHub `post-no-preference/options`, table `option_chain` (bid, ask, IV, Greeks per strike/expiry).
  Snapshots are **Mon/Wed/Fri in 2020–2024** and every weekday in 2025–2026 (checked on AAPL).
- Earnings dates and timing: DoltHub `earnings_calendar` (`when` = before market open / after market close), from
  2020-01-22.
- Universe (fixed now, point-in-time): **S&P 100 constituents as of 2020-01-01** (from the index's list on that date),
  kept for the whole span; later additions are not added, deletions stay while their options trade.
- Cross-checks: Kaggle `kylegraupe` AAPL (2016–2023) and TSLA (2019–2022) optionsDX 16:00 chains; SEC EDGAR 8-K item 2.02
  filing times for a sample of announcements.

## Split (fixed now)
**Dev = announcements 2020-01-22 → 2024-12-31; holdout = 2025-01-01 → 2026-09-28.** Holdout quotes are never queried
before the one holdout run.

## The trade (fixed now)
- **Exit day X** = the last trading day whose close precedes the announcement: the announcement day for "after market
  close", the day before for "before market open". Unknown timing → event dropped (counted).
- **Entry day E** = the latest snapshot day that is 2–4 trading days before X (the published design is ~3 days).
  Both E and X must be snapshot days with quotes; otherwise the event is dropped (counted; MWF snapshots drop some).
- **Expiry** = the nearest expiry at least 5 trading days after the announcement day, the same contracts at E and X.
- **Strike** = at E, the strike minimising |call mid − put mid| (put–call parity ATM; no separate price feed needed).
- **Prices:** buy the call and the put at the **ask** on E, sell both at the **bid** on X; $0.65 per contract per leg
  each way (0.0065 $/share). Return = (bids at X − asks at E − fees) / (asks at E + fees at E).
- Mid-to-mid gross return reported alongside (the maker bound).
- **Placebo (no event):** the same construction on the same stock with X′ = X + 21 trading days (and E′ accordingly),
  requiring no announcement within ±10 trading days of X′.

## Kills (dev; clustered by announcement week)
1. Net mean return ≤ 0, or its t < 2 → KILL.
2. Earnings minus placebo (paired by event), t < 2 → KILL (the run-up must be an event effect, not a volatility drift).
3. Median round-trip spread cost (asks − bids, over asks) ≥ the gross mid-to-mid mean → KILL (the spread eats the effect).
Reported: by year, by BMO/AMC, by pre-event IV level, by stock volatility decile; dropped-event counts; the AAPL/TSLA
cross-source check; the EDGAR timing check.

## Holdout (2025-01 → 2026-09)
Only if dev passes and the review accepts: the frozen trade, once, logged as one trial in `trials_earn.json` after the
owner's "go". Pass = kills 1–3 on the holdout.

## Rules and known risks
- No model or features (rules 9–10 do not apply). One configuration; variants are `measurement` rows.
- **Mega-caps are where the published effect is weakest** (it is strongest in small, volatile, illiquid names): this
  screen leans against the idea. A gross mid-to-mid mean ≤ 0 closes the line; a failure only on costs is reported to the
  owner, who decides whether a broader (paid) dataset is worth it.
- DoltHub snapshot time is not documented; the AAPL/TSLA cross-check against 16:00 optionsDX quotes tests it (step 0).
- 2020–2024 dev includes the 2020 volatility regime; results are reported by year.
