# NEWPLAN — ideas after the Hyperliquid forced-flow line

Written 2026-09-28, from a review of p01–p14 plus a literature and market-structure search.
It keeps the ideas on record. It is not a pre-registration: each idea still gets its own
`research/pNN_*/PLAN.md` with kill criteria before any data is read.

**Status:** #1 (p15) **KILLED on dev** 2026-09-29: Polymarket − Deribit longshot gap +0.75 pp vs a 2 pp bar. #2 (p16) **KILLED on dev** 2026-09-29: unconditional weekly short straddle, worst week 13.1× the mean (kill 3); the premium itself is not established in 2022–25. #4 (p17) **KILLED** 2026-09-29: maker P&L ≈ 0 before the fee rebate; with the verified rebate +0.13 ¢/share, t 1.82 < 2. #3 (funding carry) is the only idea left, as the unfinished p14.

---

## 1. What the repo actually shows

- **The model can't fix line 1.** p10b is the strongest result in the repo: a 4 bps breakeven
  needs AUC 0.56–0.59, and the best model reached 0.545. More features (p03, p10, p11) made it
  worse, and the TCN failed. Nothing in the literature suggests a transformer or better features
  closes a 0.02–0.05 AUC gap on 1h BTC direction at retail cost. The line stays closed (CLAUDE.md).
- **Every kill had the same cause.** The edge per trade was small, and each trade paid the spread
  and taker fee. That pattern ran through p01–p05, p10, p13 and the p09 taker test.
- **The only positive number in the repo is p14**, and it is a cash flow, not a prediction.
  That is the direction to go: predict things that are actually predictable (funding,
  volatility, mispriced probabilities) and hold for days, not minutes, so costs stop dominating.
- **The HL forced-flow line is dead under the roadmap's own rules** (p13 killed it at stage 2).
  ROADMAP §10 says the parked items are revisited if the line dies at stage 0 or 2, so they are
  now eligible.

## 2. Four ideas, ranked by prior that they make money

### #1 — Polymarket BTC threshold markets vs Deribit option-implied probability (CHOSEN → p15)
- **Why it's an edge:** Polymarket's "BTC above $X on date" contracts are digital options traded
  by retail. The same probability is priced on Deribit by professional volatility desks. Two
  segmented markets pricing the same payoff differently is a structural edge, not a prediction.
- **Evidence:**
  - Arxiv 2606.19517 finds Polymarket about **6–11 percentage points above** the option-implied
    probability.
  - The gap is largest for longshots and long maturities, with an AR(1) half-life of ~4 h.
  - Its delta-hedged arbitrage was profitable after costs, but on only 16 trades (t = 2.1, p = 0.053).
    That is weak, and it is exactly what this harness exists to test on a large sample.
  - A 588M-trade Polymarket study (arxiv 2609.12878) finds the favourite–longshot bias is robust
    in the Crypto and Politics categories and absent in Sports.
- **Costs:** the crypto taker fee is feeRate·p·(1−p) with feeRate 0.07, i.e. ~0.6¢ at p = 0.10
  and 1.75¢ at p = 0.5. That is small against a 5–10 point gap, and the holding period is days.
  Makers pay no fee.
- **Data, no collection:**
  - Deribit BTC option trades with IV and mark price: **1,492 days on disk** in
    `data/collector/p11/deribit_opt` (2022-08-01 → 2026-08-31).
  - Polymarket history from on-chain fills (Goldsky v2 datasets, `poly_data`). The CLOB
    `prices-history` endpoint returns only ≥ 12 h granularity for resolved markets, so it is not
    enough on its own.
- **Step 0, a p09-style kill: the settlement mapping.** Polymarket's resolution source and time
  (per market's `resolutionSource`) differ from Deribit's 08:00 UTC expiry on the Deribit index.
  Measure that mapping error before anything else. Start with terminal markets; "hit $X" markets
  are path-dependent and need barrier pricing.
- **Where ML fits:** little is needed. The benchmark is the option-implied probability. Add ML
  only for the risk-neutral vs real-world adjustment, and only if it beats the plain benchmark.

### #2 — Variance risk premium on Deribit, timed with an ML volatility forecast
This is where ML skill actually pays, because volatility is predictable: out-of-sample R² is
around 0.3–0.6, against roughly 0 for direction.
- **Model:** a HAR-RV baseline (realised variance over the last day, week and month) with
  LightGBM fitted on its residual. Inputs: DVOL, term-structure slope, skew from the option
  trades, funding, weekend effects. Loss: QLIKE.
- **Trade:** sell a delta-hedged 7-day ATM straddle only when implied vol minus forecast realised
  vol is above a threshold.
- **Market reasoning:** Bitcoin's VRP comes mostly from *upside* states, the opposite of the S&P,
  so short calls are hurt in rallies.
- **Costs:** ATM option spreads are about 3% of premium. Measure them for free from Tardis.dev's
  first-of-month datasets, which need no API key.
- **Harness gap first:** Sharpe and PSR flatter short-volatility strategies. Add CVaR, max
  drawdown, and stress windows on 2024-08-05 and 2025-10-10 before trusting any number.

### #3 — p14 carry, made cross-sectional and forecast-driven
- **What the literature says:**
  - He, Manela, Ross & von Wachter: perp-spot arbitrage deviations shrink about 11% a year.
  - Borri, Liu, Tsyvinski & Wu (2025): the carry Sharpe fell from 6.45 over 2020–25 to
    *negative in 2025*.
  - p14's own 2025 quarters match this. It is a yield of roughly the T-bill rate, not alpha.
- **The ML version worth one trial:**
  - Forecast next-k-day funding spreads over every coin listed on HL and at least one CEX,
    delisted coins included.
  - Enter only when forecast carry exceeds round-trip cost plus a basis-risk buffer.
  - Beat EWMA of past funding first, then Pendle Boros's implied funding APR, a market forecast
    with published history from ~2025-08. If the forecast beats Boros, trade the Boros swap
    directly: no hedge and no basis risk.
- **Rule 9 question (owner's call):** for this target, the lagged funding level *is* the signal
  (an autoregressive term). Rule 9 bans raw levels, so this needs a documented exception, still
  with the fold-id test.

### #4 — Polymarket 5-minute markets as a maker, not a taker
- **Why makers:** takers now pay up to 1.75¢ per contract at p = 0.5; makers pay zero and get 20%
  of crypto taker fees back as rebates. On Kalshi, takers lose ~32% on average and makers ~10%
  (Bürgi, Deng & Whelan).
- **Why it's only #4:** these markets are a bot latency war. The 50 ms taker delay is short, and
  the collector (europe-west3) sits ~127 ms behind Binance. Quotes will be picked off.
- **First step is free:** measure maker P&L from `last_trade_price` side and fee fields on data
  already recorded. Treat it as an upper bound: fast makers cancel stale quotes, and a slow maker
  ends up with the fills they avoided.
- **Data window:** only days after 2026-09-20. Dev (07-25 → 09-05) is spent (p09 review), and the
  09-06 → 09-20 holdout stays untouched. RTDS Chainlink is recorded from 2026-09-24 07:12 UTC.

## 3. Data collection: nothing new
Every idea above runs on free history, and most of it is already on disk. The only forward-only
feed worth waiting for is **already running**: RTDS Chainlink (from 2026-09-24), the only record of
the price the Polymarket crypto markets actually settle on, and decisive for #4 per the p09 review.
It reaches 7 days around 2026-10-01 (enough for the settlement-agreement check) and ~30 days in
late October.

Not worth collecting:

| data | why not |
|---|---|
| HL position snapshots | the thesis they served died in p13 |
| HL books | S3 archive exists |
| Deribit quotes | Tardis free first-of-month days are enough to calibrate costs |
| funding | full history is public on every venue |
| Boros | historical data is published |

## 4. Open items on p14 (in progress when this was written)
- **2025-10-10 is inside p14's dev span.** Hyperliquid ran its first cross-margin auto-deleveraging
  (ADL) that day: ~35k ADL events across 161 tokens, and delta-neutral traders had one leg
  force-closed. In a crash the short-HL leg is the profitable one, so it is the leg that gets
  deleveraged, leaving the Binance long unhedged. Daily closes hide this; check the p13 fill
  extraction for ADL fills on that day.
- **One holdout look.** The static book is post hoc. Pre-register it (rule, 5 %/yr kill, margin
  buffer) on all 8 coins and spend the single holdout look on it, logged in `trials_hl.json`.

## 5. ML and harness changes that apply to every line
1. **"Required skill" is step 0 of every PLAN.md.** p10b computed it after four experiments;
   compute the R² or AUC needed to clear cost before building any features.
2. **Targets move from direction to cash flows, volatility and calibrated probabilities**, each
   with a naive baseline the model must beat (EWMA, HAR-RV, the option-implied probability).
3. **Skew-aware reporting in the harness** (CVaR, max drawdown, stress windows) before any carry
   or short-vol result counts.

---

## Sources
- He, Manela, Ross, von Wachter, *Fundamentals of Perpetual Futures*: https://arxiv.org/abs/2212.06888
- Christin, Routledge, Soska, Zetlin-Jones, *The Crypto Carry Trade*: https://gerbil.life/papers/CarryTrade.v1.2.pdf
- Schmeling, Schrimpf, Todorov, *Crypto Carry* (BIS WP 1087): https://www.bis.org/publ/work1087.pdf
- Borri, Liu, Tsyvinski, Wu, *Cryptocurrency as an Investable Asset Class: Coming of Age*: https://arxiv.org/abs/2510.14435
- *Do Prediction Markets Match Option Prices? Bitcoin Threshold Evidence from Binance and Polymarket*: https://arxiv.org/html/2606.19517
- *The Favorite-Longshot Bias in Prediction Markets: Evidence from Polymarket*: https://arxiv.org/pdf/2609.12878
- MSc thesis, BTC prediction-market efficiency (Polymarket, Kalshi, Deribit DVOL): https://github.com/giannandreadestefano/btc-prediction-market-efficiency
- Bürgi, Deng, Whelan, *Makers and Takers: The Economics of the Kalshi Prediction Market*: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5502658
- Polymarket fees and maker rebates: https://startpolymarket.com/learn/polymarket-fees/ ,
  https://www.financemagnates.com/cryptocurrency/polymarket-introduces-dynamic-fees-to-curb-latency-arbitrage-in-short-term-crypto-markets/
- 5-minute market bots and latency: https://dyutam.com/news/polymarket-5-minute-bitcoin-bets-60m-bots-retail/
- `prices-history` granularity limit: https://github.com/Polymarket/py-clob-client/issues/216
- Polymarket on-chain data: https://github.com/warproxxx/poly_data , https://goldsky.com/blog/polymarket-dataset
- Boros historical data: https://github.com/lspss93119/boros
- Tardis.dev free first-of-month datasets: https://docs.tardis.dev/downloadable-csv-files
- Bitcoin VIX and VRP: https://www.researchgate.net/publication/346500941_The_Bitcoin_VIX_and_Its_Variance_Risk_Premium
- Deribit VRP regimes: https://insights.deribit.com/industry/bitcoin-options-finding-edge-in-four-years-of-volatility-regimes/
- BTC option spreads and hedging costs: https://arxiv.org/pdf/2010.07402
- LightGBM for BTC volatility: https://www.sciencedirect.com/science/article/abs/pii/S0957417425040199
- Hyperliquid ADL on 2025-10-10: https://wublock.substack.com/p/hyperliquid-activates-cross-margin ,
  https://pro.edgex.exchange/en-US/news/article/crypto-auto-deleveraging-risks
