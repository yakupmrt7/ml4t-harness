# p15 — Polymarket BTC threshold markets vs Deribit option-implied probability

Written 2026-09-28, before any Polymarket market list, resolution or price was read for this
experiment and before any Deribit option trade was read for it. Source: NEWPLAN.md idea #1,
chosen by the owner on 2026-09-28. Nothing below changes after numbers are seen; where a choice
must be made on data, the candidates are named here and the choice goes into a dated amendment
committed before the step that uses it.

## Line and scope
- **New line: segmented-market pricing.** It is not the closed 1h/4h bar-direction line (no
  direction is predicted from price history) and not p09 (5-minute up/down markets, a driftless
  diffusion on realised vol, taker latency). Here the fair value is **another market's price**:
  the Deribit risk-neutral probability of the same event.
- **The single change vs p09** (the last Polymarket fair-value experiment): the fair value comes
  from the Deribit implied-volatility surface instead of a diffusion on realised vol, and the
  markets are multi-hour to multi-week threshold markets held to resolution instead of 5-minute ones.
- **Trial log:** this line gets its own, `trials_pm.json` (created on the first holdout run). It
  does not write to `trials.json` (closed Binance line) or `trials_hl.json` (HL line).

## Hypothesis (falsifiable)
For Polymarket BTC **terminal** threshold contracts ("BTC above $K at time T"; range buckets are
differences of two such digitals), the Polymarket YES price exceeds the Deribit risk-neutral
probability of the same event where that probability is low. Selling YES (buying NO) when the gap
is at least θ = 5 pp, held to resolution, earns positive realised P&L after Polymarket fees against
the actual resolutions.

Prior evidence (NEWPLAN.md): arxiv 2606.19517 finds a 6–11 pp mean gap, largest at low implied
probability and long maturity, but on 3 contracts / 16 trades (t 2.1). Arxiv 2609.12878 finds the
favourite–longshot bias robust in Polymarket's Crypto category.

Market reasoning: a digital on Polymarket and a Deribit call spread around K pay almost the same
thing. Deribit prices are set by professional volatility desks that hedge; Polymarket's are set by
retail, who overpay for lottery-like longshots. The two venues are segmented (different collateral,
KYC, users), so the gap can persist. What can break it: the settlement mapping (different fixing
time, different underlying), Polymarket fees and spreads, and a gap that is real but too small or
too rare to trade.

## Required skill (NEWPLAN §5.1), before any data
To sell YES at price p the trade pays the taker fee 0.07·p·(1−p) per share (≈ 0.6 ¢ at p = 0.10,
1.75 ¢ at p = 0.5; conservatively applied to the whole span even where fees were 0) plus the
distance from the observed price to the bid. The bid is not observed in on-chain fills; the entry
rule below fills only at prices at which a taker actually sold YES, so the spread is paid inside the
fill price. **Break-even: a mean realised edge per contract above the fee, i.e. ≳ 1 ¢.** The kill
below asks for +1 ¢ mean and t ≥ 2.

## Market families
- **In scope:** Polymarket markets whose payoff is a function of **one BTC price at one fixing
  time** and which resolve on a reproducible source (expected: a Binance BTC/USDT 1-minute candle
  close at a stated time; confirmed per market from its resolution text in Step 0): "above $K on
  date" and "price range on date" families, any tenor.
- **Out of scope:** "hit / reach $K by date" (path-dependent; needs barrier pricing; possible later
  experiment), up/down 5m/15m/1h/daily markets (p09's territory, and for up/down the strike is set
  at the window start), anything resolving on a source we cannot reproduce, non-BTC underlyings.

## Data
- **Polymarket market metadata and resolutions:** Gamma API, fetched on `poly-collector-eu` exactly
  like p09 (Polymarket is not reachable from the owner's machine): standard-library script, ~2 req/s,
  lowest CPU priority, working folder deleted afterwards. Fields: question, description (resolution
  rule), slug, condition id, CLOB token ids, start/end dates, outcomes, outcomePrices, UMA status.
- **Polymarket fills (prices):** on-chain order fills. The source is chosen in Step 0 among
  (a) a public processed dataset (HuggingFace `SII-WANGZJ/Polymarket_data` or `warproxxx/poly_data`
  output), (b) Goldsky's Polymarket datasets, (c) direct Polygon logs of the CTF Exchange contracts
  (v1 and the v2 contracts from 2026-04-28). Whichever is used must first pass the validation in 0d.
  Fills give price, size, time, maker/taker and which token the taker bought or sold.
- **Deribit:** BTC option trades on disk, `data/collector/p11/deribit_opt/` (2022-08-01 →
  2026-08-31; per trade: instrument, price in BTC, trade IV, index price, **mark price**, amount,
  direction). May be extended past 2026-08-31 with the same p11 downloader (`history.deribit.com` is
  reachable) **before** the split is fixed in 0f, never after.
- **Binance:** BTCUSDT spot 1-minute klines from data.binance.vision (settlement rebuild and basis).

## Step 0 — availability, settlement mapping, split (no Polymarket price and no gap is read)
- **0a Inventory.** Enumerate every BTC market in the in-scope families: resolution text, strike(s),
  fixing time T (UTC), source, created/closed times, outcome. Report counts per family and month.
- **0b Settlement reproduction.** Rebuild each market's outcome from Binance BTCUSDT 1m klines
  under its own rule and compare with Gamma. Report agreement overall and by |S_T/K − 1| bucket.
  **KILL A:** agreement < 99.5 % on markets with |S_T/K − 1| > 1 bp → the mapping is not understood;
  stop and report (p09-style).
- **0c Underlying mapping.** At each fixing time, the Deribit index (index_price on option trades
  within ±60 s of T) vs Binance BTCUSDT close: distribution in bps. Fair value uses the strike
  mapped into Deribit-index terms, K_D = K · (1 + b), b = median basis over the trailing 7 days
  **known at decision time** (causal). Report the distribution; no gate.
- **0d Fill-data validation.** On ≥ 30 in-scope markets across the span, fill count and USDC volume
  from the chosen fill source vs the Polymarket data API (trades endpoint, fetched on the VM) or
  vs raw Polygon logs. Gate: count and volume agree within 1 % on ≥ 29/30. Failing sources are
  replaced, not patched.
- **0e Power.** Count distinct fixing dates in the would-be dev span that have ≥ 1 in-scope market
  with ≥ 1 taker-sell fill in the decision window of Step 2 (count only; prices not read).
  Outcomes on one fixing date share one BTC path, so **the fixing date is the cluster**.
  **KILL B:** < 100 dev clusters → underpowered; stop.
- **0f Split, fixed then and committed before Step 1.** Common span = fixing dates with both
  Polymarket fills and Deribit trades. **Dev = first 75 % of that calendar span, holdout = last
  25 %.** Holdout markets' fills are never loaded by Steps 1–2 (the loader asserts it).

## Step 1 — fair value and gap (dev, measurement)
- **Decision grid:** every UTC hour close t from a market's first fill to T − 1 h.
- **Deribit surface at t,** from option trades in [t − 60 min, t] (trailing only):
  - per trade, invert the **mark price** (BTC-denominated; × index → USD) to a mark IV (Black-76,
    forward below); marks are Deribit's own smoothed surface and are less noisy than trade IVs;
  - forward per expiry from put–call parity on the near-ATM call/put marks in the window;
  - per expiry, a weighted least-squares quadratic smile in log-moneyness k = ln(K/F), weights =
    vega; expiries with < 5 distinct strikes in the window are dropped;
  - maturity T is bracketed by the two nearest surviving expiries; total implied variance
    w(k, τ) = σ²τ is interpolated linearly in τ at fixed k (no extrapolation: if T is outside the
    surviving expiries, no fair value at t).
- **Risk-neutral probability:** P_RN = −∂C/∂K at K_D from the smile (numerical, ±0.25 %), which
  includes the skew term; no discounting (days-horizon, < 0.1 pp; disclosed). Range buckets =
  P_RN(K_low) − P_RN(K_high).
- **Polymarket price at t:** VWAP of YES fills in [t − 60 min, t]; if none, no observation.
- **Gap:** D = PM − P_RN. Report D by P_RN bucket (< 5, 5–15, 15–35, 35–65, 65–85, 85–95, > 95 %)
  × τ bucket (< 1 d, 1–3 d, 3–7 d, > 7 d), with CIs from a cluster bootstrap by fixing date.
- **Calibration:** Brier and reliability of PM and of P_RN against Gamma outcomes, same buckets,
  clustered by fixing date. Both forecasters are scored on the same (market, t) rows.
- **KILL C:** in the P_RN < 15 % bucket, the median D < 2 pp → no gap worth trading; stop.

## Step 2 — the rule (dev; one rule, no parameter search)
- **Rule R (sell side, the hypothesis):** at the first decision hour t where D ≥ θ = 5 pp, sell YES
  (buy NO) one unit; **at most one entry per market**; hold to resolution. (p09's review: one entry
  per market, fixed weighting, kill on realised P&L.)
- **Entry fill:** the first on-chain fill in (t + 60 s, t + 60 min] in which a taker **sold** YES or
  bought NO, at that fill's YES-equivalent price (so the spread is paid). No such fill → no trade.
  Fee 0.07·p·(1−p) per share on every entry. No exit before resolution, so no exit fee.
- **P&L per contract** = (entry price − fee) − 1{YES wins}. Unit size, equal weight per market.
- **Reported, not used for the kill:** the mirror buy side (D ≤ −5 pp); θ = 3 and 10 pp; entry at
  t + 2 h (delay check); first vs second half of dev; per family and per τ bucket; a
  **hedged** version (sell YES, buy the Deribit call spread [K_D − δ, K_D + δ] sized to the digital,
  Deribit fees 0.03 % of underlying capped at 12.5 % of premium, per leg, at mark ± half the
  trailing median trade-vs-mark distance); the daily P&L series by resolution date with PSR, DSR
  (trial count from `trials_pm.json` + selection rows), max drawdown and worst 5 fixing dates.
- **KILL D (economics, dev):** mean realised P&L of Rule R < +1.0 ¢ per contract, or t < 2
  (clustered by fixing date) → kill; no holdout run.
- **Robustness (reported; a failure is stated, not overridden):** sign of mean P&L the same in both
  halves of dev and at the t + 2 h delay.

## Selection hygiene
- No parameter is fitted. Each computed configuration (Rule R and every reported variant) is one row
  in `selection_trials.json`, marked `measurement` or `rule`.
- CLAUDE.md rule 10 (fold-id test) applies to learned feature sets; this experiment has no model and
  no features. If a later step adds a model (e.g. a risk-neutral → physical adjustment), it gets the
  fold-id test and its own PLAN amendment.
- CLAUDE.md rule 8: there is no bar-return series for `validation_report`; the substitute gauntlet is
  the cluster-bootstrap CI, PSR/DSR on the daily resolved-P&L series, the delay check and the half
  split above. Its block goes into RESULTS.md.

## Holdout
Only if Step 2 passes KILL D and the review accepts: Rule R exactly as frozen, once, on the holdout
markets, logged as one trial in `trials_pm.json`. Pass = mean P&L > +1.0 ¢ per contract and t ≥ 2.

## Known risks, stated before looking
- **Fixing-time and underlying mismatch** (Binance BTCUSDT at a candle close vs Deribit index at
  08:00 UTC): handled by the smile's time interpolation and the causal basis in 0c; 0b/0c measure it.
- **Thin Polymarket strikes:** long-dated far strikes may trade rarely; the entry rule skips them,
  which may leave few trades (KILL B counts this in advance).
- **Short-longshot P&L is negatively skewed:** many small gains, rare full losses. Mean-based kills
  and date clustering are used for that reason; PSR uses skew and kurtosis.
- **Survivorship:** none expected (every resolved market is included), but markets voided or disputed
  on UMA are reported, not dropped silently.

---

## Amendment 1 — 2026-09-28, after step 0a–0d, before the split (0f) and before any Polymarket price or gap is read

**What has been read so far:** market metadata (question, strikes, dates, volume), Gamma rule texts and
resolved outcomes, Binance 1m closes at fixing times, Deribit `index_price` near fixing times, and fill
**counts, share volumes and timestamps** for validation. No Polymarket price level has been looked at,
and no Deribit option price or IV.

### 0a Inventory (inventory.py, fetch_gamma.py)
- Families from metadata: **strike** ("above $K on date", 5,836 markets, 437 fixing dates, share volume
  1.23 B), **range** (price buckets incl. "less than / greater than", 5,481 markets), and
  **hourly_above** (40,547 one-hour markets created ~1.3 h before an hourly fixing, median volume $100).
- **hourly_above is out of scope, structurally:** a fixing 1.3 h ahead is never bracketed by two
  Deribit expiries (the step-1 no-extrapolation rule), and these are p09-type short-horizon markets.
- Out of scope by source: 6 Coinbase-settled (2023), 3 CoinMarketCap (2021), 36 with no Binance rule
  text (2021–22 legacy); 11 markets of one event with an **ambiguous "12AM ET" fixing** (title vs
  end_date disagree; decided from metadata, not outcomes). **In scope: 11,261 markets.**
- **The fixing time comes from each market's rule text, never from `end_date`** (end_date is 12:00 UTC
  for 12:00-ET fixings in older markets, and was overwritten months later for some). 49 phrasings
  handled (`step0.parse_fixing`, tested).

### 0b Settlement (step0.py rules) — KILL A does not fire
- First run 99.90% agreement (11 misses, all > 30 bp from strike). All 11 were parser errors (year
  anchored on an overwritten end_date; the ambiguous 12AM event) and were fixed by metadata rules.
- **Final: 11,261 / 11,261 = 100.00% agreement** with Gamma, including all 68 markets within 3 bp of the
  strike. Rule: Binance BTCUSDT 1m candle OPENING at T; strike family S > K; range family boundary goes
  to the higher bracket (S ≥ K for "greater than", S < K for "less than", K_lo ≤ S < K_hi).

### 0c Underlying (step0.py basis)
Deribit index / Binance BTCUSDT − 1 at T (678 fixing times): median +1.0 bp, IQR −4.0 / +4.5 bp,
1–99% −25 / +17 bp; by year median +12.0 (2023), −0.2 (2024), +2.3 (2025), −4.0 (2026). The causal
strike mapping of step 1 is kept.

### 0d Fill source — the HuggingFace table FAILS and is REPLACED (not patched)
- Checked against Polygon block timestamps by transaction hash: Polymarket's **data API** timestamps equal
  the block time in 18/18 trades; the HF table's are off by +94…+102 s in some block ranges and by
  −5…−6 h in others (e.g. markets 605522, 556542), and part of the v2-exchange fills is missing
  (v2 share volume 50–90% of the API's). The API's per-market share volume equals Polymarket's own
  volume counter (metadata `volume`) exactly on 30/40 sampled markets (the others were still trading
  when the metadata snapshot was taken).
- **New source: Polymarket data API taker trades** (`fetch_trades.py`, on the VM): per trade timestamp
  (= block time), taker side, outcome index, size, price, taker wallet, tx hash. The original 0d count
  criterion is replaced because the two tables have different units (maker fills vs taker trades).
- **Gate for the new source (fixed now):** (i) share volume within 1% of the metadata volume on ≥ 95%
  of markets that closed before 2026-07-15 (snapshot date margin); (ii) 50 random trades across the span
  have timestamp = block time exactly. Failing either → stop and report.
- **API cap:** ≤ 10,500 rows per query, newest first. Capped markets are re-fetched per side; if a side
  still hits the cap the market is flagged `truncated` (oldest trades missing). Expected ≈ 1 market
  (≈ 15 need the per-side split, all 2024-11 → 2025-03 weekly strikes). Truncated markets stay in, with
  their available trades, and are reported separately.

### Definitions fixed for Steps 1–2 (in API terms)
- YES-equivalent trade: outcomeIndex 0 at price p, or outcomeIndex 1 at price q ↦ p = 1 − q.
  **"Taker sold YES"** = (SELL, outcome 0) or (BUY, outcome 1).
- PM price at t: share-weighted VWAP of YES-equivalent prices of all taker trades in [t − 60 min, t].
- Entry fill (Rule R): the first "taker sold YES" trade with timestamp in (t + 60 s, t + 60 min], at its
  YES-equivalent price. Fee 0.07·p·(1 − p) per share (identical for the NO-side representation).
- **Strike extrapolation:** the main P_RN requires k(K_D) inside the traded k-range of **both**
  bracketing smiles (no extrapolation in k either); extrapolated values are reported separately, never
  used for the kill.
- **Causal basis b(t):** median over trades in [t − 7 d, t] of (Deribit index_price / Binance 1m close of
  the minute containing the trade) − 1, from 1 000 evenly spaced trades per day; K_D = K·(1 + b).
- Range markets: between = P(K_lo) − P(K_hi); less than = 1 − P(K_hi); greater than = P(K_lo) (the
  boundary convention is immaterial for a continuous distribution).
- Clusters for all CIs and t-stats: the fixing date (ET calendar date of T).

### 0e / 0f
Computed after the trade fetch, in that order: the split (0f) first from fixing dates only (rule
unchanged: common span of fixing dates with Binance-rule markets and Deribit trades on disk,
2022-08-01 → 2026-08-31, and the inventory, markets created by 2026-07-20; dev = first 75% of the
calendar span), then KILL B (0e) on dev fixing dates only. Deribit is not extended.

---

## Amendment 2 — 2026-09-29, owner's decision after the 0d source gate failed as written; before any Polymarket price is read

- **Gate (ii) passes:** 50/50 random trades have timestamp = Polygon block time.
- **Gate (i) FAILS as written** (amendment 1 scope: all markets closed before 2026-07-15): 88.6% within 1% of
  Polymarket's volume counter vs the 95% bar. By span: **dev 99.35%** (volume-weighted |API − counter| 1.1%;
  failures are the 11 truncated 2024-12 → 2025-02 weekly strikes and markets whose counter is 0), **holdout
  80.0%**, concentrated in 2026-03 (70% fail) and 2026-04 (96% fail) fixings, where the API is a median ~4%
  below the counter (around the v1 → v2 exchange migration of 2026-04-28).
- **Owner's decision (post hoc, disclosed):** the gate is evaluated per span. Steps 1–2 run on dev, which
  passes. **Before any holdout run**, the 2026-03/04 shortfall must be explained by an independent on-chain
  check of ≥ 5 affected markets; if it is not explained, those fixing months are excluded from the holdout by
  a rule written down before the holdout is read. The 95% threshold itself is unchanged.
- The 11 truncated markets (oldest trades missing) stay in dev with their available trades and are
  reported separately in Step 2.
