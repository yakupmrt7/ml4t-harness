# p20 — SPY option variance risk premium, defined-risk book, with an ML volatility-timing layer

Written 2026-09-29 before any option price, return or P&L was read for this experiment. Source: NEWPLAN2.md #1,
started by the owner on 2026-09-29. Read so far: dataset descriptions, file schemas and per-year row/day counts.
Nothing below changes after numbers are seen; anything decided on data goes into a dated amendment committed
before the step that uses it.

## Line, trial log, and the single change vs p16
- **New line: equity index option premia** (US listed options; tradeable from Turkey via Interactive Brokers).
  Trial log: `trials_eqvol.json` (created only by a holdout run).
- **Change vs p16 (Deribit BTC, killed at its tail rule):** the market (SPY options: decades of documented
  premium, ~1 ¢ spreads), and the structure: a **defined-risk put spread**, so the tail is capped by construction
  instead of being tested by a worst/mean rule that any unhedged short-vol book fails.

## Market reasoning (for the owner)
Selling a put is selling crash insurance; buyers overpay on average (implied vol > realised vol), and the CBOE
put-write index has earned roughly equity-like returns with lower volatility since 1986. But a short put is also
**long the market**: much of its return is plain equity beta. The premium that is *not* beta is what we test,
as the alpha of the book's monthly returns against SPY's. The put spread buys a further-out put so the worst month
is bounded; that costs part of the premium.

## Data (free; no collection)
| role | source | span | fields |
|---|---|---|---|
| dev | Kaggle `dudesurfin/spy-options-eod-volatility-surface-2010-2023` (optionsDX schema, MIT) | 2010-01 → 2021-12 used | 16:00 ET chain: bid/ask, IV, Greeks per strike×expiry, underlying last |
| holdout, part 1 | same file | 2022-01 → 2023-12 | same |
| holdout, part 2 | Kaggle `shankerabhigyan/s-and-p500-options-spy-implied-volatility-2019-24` (CC0) | 2024-01 → 2025-12 | bid/ask, sizes, volume, OI, IV, Greeks |
| cross-check | Kaggle `kylegraupe/spy-daily-eod-options-quotes-2020-2022` (CC0) | 2020–2021 only | EOD quotes |
| supplement (reported only) | DoltHub `post-no-preference/options` | 2024 → 2026-09 | thin SPY slice (~100–260 contracts/day) |
| underlying check | SPY daily closes from an independent free source (Stooq or similar) | 2010 → 2021 | |
| benchmarks | CBOE daily index histories (PUT, BXM, VIX, VIX3M) | free | |

**Split (fixed now): dev = 2010-01-01 → 2021-12-31; holdout = 2022-01-01 → 2025-12-31.** Holdout rows are never
loaded before the one holdout run (the loader asserts it). The holdout changes source in 2024; the two sources are
cross-validated on their **dev** overlap (2014–2021) only.

## Step 0 — data validation (dev dates only; before any P&L)
- Trading days per year vs the NYSE calendar; duplicate (date, expiry, strike) keys; bid ≤ ask; share of rows with
  zero bids. Gate: ≥ 98% of NYSE days present in dev; missing days listed.
- Underlying: `UNDERLYING_LAST` vs an independent SPY daily close. Gate: median |diff| < 0.05%, 99% of days within
  0.5%.
- Cross-source quotes on identical (date, expiry, strike, type): dudesurfin vs kylegraupe (2020–2021) and dudesurfin
  vs shankerabhigyan (2014–2021). Gate: median |mid difference| ≤ 1 ¢ and ≥ 95% of matched mids within 5 ¢, per
  source pair. **If the shankerabhigyan pair fails, the holdout is 2022–2023 only** (fixed now).

## Step 1 — the unconditional books (dev)
**Cycle:** monthly. Entry on the first trading day after each standard monthly expiration (third Friday); expiry =
the next standard monthly expiration (≈ 25–35 days). Hold to expiry. Settlement price S_T = SPY close on the
expiration day (`UNDERLYING_LAST` on that date). Early assignment and dividend effects are ignored (disclosed; they
matter only for deep in-the-money short puts near ex-dividend dates).

- **P (primary, the one that can pass):** short the put with strike nearest the entry spot, long the put with strike
  nearest 0.90 × spot, same expiry. Sell at the **bid**, buy at the **ask** (taker both legs), plus $0.65 per contract
  per leg (IBKR), i.e. 0.0065 $/share/leg. Capital at risk = strike width. Monthly return on capital
  r = (credit − fees − (max(K₁−S_T,0) − max(K₂−S_T,0))) / width. Collateral would earn T-bills in practice, so r is
  an **excess** return.
- Reported, not used for kills: P at mid prices (maker bound); a 5% wing (long put at 0.95 × spot); a cash-secured ATM
  put (capital = strike; the CBOE PUT construction); entry one trading day later; a short ATM straddle delta-hedged
  daily in SPY at the close (pure variance premium; hedge cost 1 bp per unit traded); the CBOE PUT index over the same
  months.

**Kills for P (dev, 144 cycles):**
1. **Economics:** annualised mean r (12 × mean monthly) < **3%/yr** on capital → KILL.
2. **Premium, not beta:** regress monthly r on SPY's monthly excess return over the same cycle: alpha ≤ 0 or its
   Newey–West (lag 3) **t < 2** → KILL.
3. **Tail (defined risk, reported):** worst cycle, CVaR(5%), max drawdown of the monthly series on capital-at-risk, and
   the stress cycles 2011-08, 2015-08, 2018-02, 2020-03. No numeric kill: the loss per cycle is capped at 100% of
   capital by construction, and sizing is a separate decision.

## Step 2 — ML volatility timing (dev walk-forward; pre-registered now, run whatever Step 1 shows)
- **Target:** log realised variance of SPY over the cycle (close-to-close daily returns from entry to expiry),
  annualised.
- **Features at entry (all causal, all normalised — CLAUDE.md rule 9):** log realised variance over the last 5, 21 and
  63 trading days, each as a z-score against its trailing 252-day history; log(IV_ATM,30d²) from the chain and its
  z-score; log(IV²/RV²₂₁); VIX and VIX3M from CBOE as log(VIX3M/VIX) (term-structure slope) and the VIX z-score.
- **Models:** HAR regression (OLS on the three RV terms; the baseline) and LightGBM regression (default harness
  settings, no tuning), both trained on an **expanding window by calendar year** (first test year 2013), predicting each
  test year's cycles out of sample.
- **Decision rule (no fitted threshold):** open P in a cycle only if forecast variance premium IV_ATM² − RV̂² > 0; else
  stay flat (r = 0).
- **Rule 10:** adversarial fold-id test on the feature set (predict the test year from the features; chance = 1/9),
  reported in RESULTS.
- **Kills for the timed book (on the 2013–2021 out-of-sample cycles):**
  a. LightGBM must beat HAR on out-of-sample QLIKE; if not, the timed book uses HAR and ML "adds nothing" is reported.
  b. The timed book must pass kills 1 and 2 on those cycles, **and** beat unconditional P on the same cycles with a
     paired t ≥ 2 on the monthly return differences → otherwise timing adds nothing.

## Holdout (2022-01 → 2025-12; one run, after review and the owner's "go")
Book chosen by a rule fixed now: the timed book if it passed Step 2; else P if it passed Step 1; else **no holdout
run**. The chosen book is frozen and run once on the holdout cycles (models retrained through 2021 only, no refit
inside the holdout), logged as one trial in `trials_eqvol.json`. Pass = kills 1 and 2 on the holdout.

## Selection hygiene and reporting
- One primary configuration; variants are `measurement` rows in `selection_trials.json`.
- CLAUDE.md rule 8: no bar-label `validation_report` applies; the substitute is the alpha regression with NW errors,
  PSR/DSR on the monthly series, the delay (+1 day) check, the mid/taker cost bracket, and the stress cycles.
- Effective n = number of non-overlapping monthly cycles (144 on dev); annual Sharpe s.e. ≈ 1/√12 ≈ 0.29.

## Known risks, stated before looking
- **Public, well-known premium:** post-publication decay (McLean–Pontiff) and the 0DTE era (2023+) may have compressed
  it; that is what the holdout tests.
- **EOD quotes at 16:00** can be stale for far strikes; the 10%-OTM wing is liquid on SPY, but the taker assumption
  (bid/ask) is used for the kills for that reason.
- **Source switch inside the holdout (2024)**, handled by the Step 0 cross-validation.
