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
