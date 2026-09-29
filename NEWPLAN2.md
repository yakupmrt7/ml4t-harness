# NEWPLAN2 — non-crypto markets, after the crypto lines closed

Written 2026-09-29 from a literature and market-access search, after p01–p19 found no edge in crypto
(README.md). It keeps the ideas on record. It is not a pre-registration: each idea gets its own
`research/pNN_*/PLAN.md` with kill criteria before any data is read.

Constraints carried over from the owner: no weeks-long data collection unless the data is a gem (every idea
below runs on free or cheap *history*); results must be tradeable by a retail account based in Turkey.

---

## 1. What the crypto work says about where to look next
- **Costs decided every crypto line.** Taker costs were 4–10 bps per side; p10b showed a 4 bps breakeven needs
  AUC 0.56–0.59. On US index products the cost scale is roughly 10× smaller: S&P 500 e-mini futures (ES) cost
  well under 1 bp per side, SPY options quote about 1 ¢ wide on a $5–10 option, IBKR charges $0.65 per option
  contract. Ideas that died on crypto costs can be alive here; that is the main reason to move.
- **Premia were real but too small or too decayed (p14–p19).** Look for premia with *decades* of evidence, not
  two years, and measure return on the capital the trade needs (lesson 7).
- **Where ML earns its keep:** volatility is forecastable (R² 0.3–0.6), direction is not. Put ML on the
  volatility and sizing side, not the sign.

## 2. Access from Turkey (checked 2026-09-29)
| venue | status for a Turkey resident |
|---|---|
| **Interactive Brokers** (US stocks, ETFs, options, futures incl. ES/VIX) | accounts open to Turkey residents |
| **Borsa Istanbul** (BIST equities, VİOP futures/options) | local brokers; legal |
| Polymarket | **blocked** since 2026-07-16 by Milli Piyango (decision 2026/10, "unauthorised betting") |
| Kalshi | US persons only |
| Betting exchanges (Betfair etc.) | offshore betting is restricted in Turkey |
**Prediction markets and betting exchanges can be studied but not legally traded from Turkey**, so they rank last.

---

## 3. Ideas, ranked (edge prior × free-data testability × deployability × ML fit)

### #1 — S&P 500 / Nasdaq index option variance risk premium, with ML volatility timing
- **Market reasoning:** index option buyers pay for crash insurance; implied vol exceeds realised vol on average.
  Unlike BTC (p16), this premium has decades of evidence: the CBOE S&P 500 PutWrite index (PUT) has returned
  ~10%/yr since 1986 with ~36% less volatility than the S&P 500 and a higher Sharpe ratio (CBOE/Bondarenko). It
  loses in sharp rallies and crashes (2008, 2020, Feb 2018 "Volmageddon").
- **What is different from p16:** (i) the premium is established over decades, not 3 years; (ii) costs are tiny
  (SPY/QQQ options ~1 ¢ wide); (iii) **defined-risk structures** (put spreads / iron condors) cap the tail that
  killed p16 at kill 3; (iv) ML is used where it works: HAR-RV + LightGBM forecasts of realised vol decide when
  and how much to sell.
- **Data (free, historical, no collection):** the GitHub SPY/QQQ/IWM chain datasets cited at first are **gone**
  (404 on 2026-09-29, likely taken down). Replacements found (owner's pointers + search): Kaggle
  `dudesurfin` SPY EOD chains 2010–2023 (optionsDX schema, bid/ask, IV, Greeks), Kaggle `shankerabhigyan` SPY
  2014–2025 (bid/ask, sizes, OI, IV, Greeks), Kaggle `kylegraupe` SPY 2020–2022, DoltHub `post-no-preference/options`
  (thin SPY slice to 2026-09); all download without credentials. CBOE PUT/BXM/VIX/VIX3M histories (free).
  **Cross-validate sources before trusting** (p15's lesson).
- **Kill (to fix in its PLAN):** on dev, net return on margin capital ≥ T-bill + 3 pts, t ≥ 2, worst month
  ≥ −X × mean month, and the ML-timed book must beat the unconditional book *and* the PUT index after costs.
- **Deployable:** yes (IBKR options; defined-risk spreads keep margin known).

### #2 — Long straddles into earnings (the "uncertainty run-up")
- **Market reasoning:** investors under-price the size of the earnings move in the days before it. Gao, Xing &
  Zhang (JFQA 2018): ATM straddles held from 3 days before an announcement to the announcement earned
  **+3.34%** on average, stronger in smaller, more volatile, costlier-to-trade stocks. It is *long* volatility,
  so there is no crash tail; the enemy is the bid-ask spread, which the harness measures well.
- **Data:** free single-stock option history is thin: optionsDX gives 10 tickers (incl. AAPL, TSLA, NVDA) 2010–2023
  free, which is enough for a step-0 screen; breadth needs a paid EOD set (e.g. historicaldata.net, FirstRate;
  a few hundred $) — decide only if the screen survives. Earnings dates from free calendars.
- **Kill:** net of the measured spread (entry and exit at bid/ask) mean straddle return ≤ 0 or t < 2 by
  announcement cluster; post-publication decay expected (McLean–Pontiff: US anomalies −58% after publication).

### #3 — Borsa Istanbul cross-section (home market)
- **Why BIST:** Jensen, Kelly & Pedersen (JF 2023) find the **United States is the only country with a reliable
  post-publication decline** in anomaly returns; anomalies elsewhere persist. BIST is retail-heavy and little
  studied by quants; the owner can trade it legally at local costs. Most published BIST "predictability" papers
  (day-of-week, 57% random-forest accuracy) are exactly the kind of claim this harness kills, which is an
  opportunity, not a result.
- **The data risk is the whole question (p07's survivorship lesson):** free prices (Yahoo `.IS`) miss delisted
  stocks; point-in-time fundamentals need KAP filings or a paid vendor (Finnet, Matriks). Returns must be in real
  or USD terms (TRY inflation).
- **Step 0 kill:** if a delisting-complete BIST universe cannot be assembled for ≥ 10 years, stop. Then price-only
  factors first (momentum, short-term reversal, low volatility, liquidity), ML ranker second, with measured BIST
  costs (commission + BSMV + spread).

### #4 — End-of-day hedging flows in S&P 500 futures
- **Market reasoning:** option dealers short gamma and leveraged ETFs must trade *with* the day's move near the
  close; the last 30 minutes' return is predicted by the rest of the day (Baltussen, Da, Lammers & Martens, JFE 2021).
  ES costs are tiny, so a small predictive edge can pay, unlike crypto.
- **Counter-evidence to test first:** 0DTE options (≈ 59% of SPX volume by 2025) appear to **dampen** intraday
  momentum (Adams et al., 2025). The prior is weak.
- **Data:** SPY/ES minute bars 2016–2026 (free via broker/data APIs with an account, or cheap vendor files).
- **Kill:** last-30-minute signal breakeven < measured ES cost (tick + fee) on dev, or no effect after 2022.

### Parked (tested elsewhere and dead, or not deployable)
- **Post-earnings announcement drift:** gone in large caps since 2006, recently in microcaps too (Martineau 2022).
- **Pre-FOMC drift:** disappeared after 2015 (Kurov, Wolfe & Gilbert 2021).
- **"Lazy Prices" (10-K text changes):** 22%/yr in the paper; a public post-2009 replication on the S&P 100 gets
  −0.9%/yr (t −0.5).
- **ML on the equity cross-section (Gu, Kelly & Xiu):** most of the gain is in microcaps and distressed stocks and
  more than half disappears without them or after costs (Avramov, Cheng & Metzker, MS 2023). A proper test needs
  survivorship-free CRSP data (WRDS, paid or via a university); the free Open Source Asset Pricing signals
  (212 predictors, `pip install openassetpricing`) help only once returns are clean.
- **Trend following / time-series momentum:** a real long-run premium (SG Trend Index CAGR ~5.3% since inception,
  max drawdown ~21%) but weak in 2024–25 (trailing 12 months +2.4% at end-2025) and little room for ML; an
  allocation decision, not research.
- **VIX futures roll (short VIX in contango, hedged with ES):** 53%/yr in 2006–11 (Simon & Campasano) and blown up in
  Feb 2018; folds into #1 as one structure, with CFE's free settlement history.
- **Prediction markets / sports exchanges (favourite–longshot bias):** the evidence is real (Polymarket politics,
  Kalshi makers vs takers), but trading them from Turkey is not legal. Research-only.

## 4. Recommended order
1. **#1 index option VRP** — strongest prior, free data, costs 10× below crypto, ML where it works, defined risk.
2. **#2 earnings straddles** — cheap step-0 screen on 10 free tickers before any purchase.
3. **#3 BIST** — only if step 0 can build a survivorship-free universe.
4. **#4 ES end-of-day** — one quick dev test; expect the 0DTE era to have killed it.

---

## Sources
- CBOE PutWrite (PUT) index and white paper: https://www.cboe.com/insights/posts/white-paper-shows-volatility-risk-premium-facilitated-higher-risk-adjusted-returns-for-put-index/ ;
  Bondarenko, Historical performance of put-writing strategies: https://cdn.cboe.com/resources/education/research_publications/PutWriteCBOE19_v14_by_Prof_Oleg_Bondarenko_as_of_June_14.pdf
- Free SPY/QQQ/IWM option chains 2008–2025: https://github.com/SaidBahaDev/options-dataset-hist ; free option data survey: https://davidariasfinance.com/scripts/free-options-data/ ; optionsDX: https://www.optionsdx.com/
- Gao, Xing & Zhang, straddles around earnings (JFQA 2018): https://doi.org/10.2139/ssrn.2204549
- McLean & Pontiff, post-publication decay: https://www.fmg.ac.uk/sites/default/files/2020-08/Jeffrey-Pontiff.pdf
- Jensen, Kelly & Pedersen, Is there a replication crisis in finance? (JF 2023): https://onlinelibrary.wiley.com/doi/10.1111/jofi.13249
- Avramov, Cheng & Metzker, ML vs economic restrictions (MS 2023): https://dx.doi.org/10.1287/mnsc.2022.4449
- Lazy Prices (JF 2020): https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12885 ; post-2009 S&P 100 replication: https://github.com/iqueipopg/lazy-prices
- Martineau, Rest in peace PEAD: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3111607
- Kurov, Wolfe & Gilbert, disappearing pre-FOMC drift: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3134546
- Baltussen, Da, Lammers & Martens, hedging demand and intraday momentum (JFE 2021): https://www.sciencedirect.com/science/article/abs/pii/S0304405X21001598
- Adams et al., 0DTEs and market volatility (2025): https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5641974
- Simon & Campasano, VIX futures basis: https://www.efmaefm.org/0efmameetings/efma%20annual%20meetings/2013-Reading/papers/VIX%20paper_EFMA.pdf
- Open Source Asset Pricing data: https://www.openassetpricing.com/data/
- SG Trend Index 2025: https://www.toptradersunplugged.com/trend-following-performance-report-december-2025/
- Lou, Polk & Skouras, overnight vs intraday returns: https://www.sciencedirect.com/science/article/abs/pii/S0304405X19300650
- Borsa Istanbul predictability studies (examples): https://www.researchgate.net/publication/333639166_Testing_Market_Efficiency_with_Nonlinear_Methods_Evidence_from_Borsa_Istanbul
- Polymarket blocked in Turkey (2026-07-16): https://www.turkiyetoday.com/business/turkiye-blocks-access-to-prediction-market-platform-polymarket-3224289
- Interactive Brokers for Turkey residents: https://brokerchooser.com/best-brokers/best-international-online-brokers-for-citizens-in-turkey
