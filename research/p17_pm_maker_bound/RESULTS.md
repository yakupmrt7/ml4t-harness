# p17 — Upper bound on maker P&L, Polymarket 5-minute BTC up/down: passes as registered, NOT CREDITED

**Verdict: the maker side of these markets earns only the rebate, and at the fee actually charged the bound is
not significant.** Over 2,304 markets (2026-09-21 → 09-28, 3.48 M taker trades, 110 M shares), makers as a group
lose **−0.06 ¢ per share** to takers before rebates (t −0.91). Everything positive comes from the maker rebate.
- **As registered** (amendment 1: fee rate 0.10, the most generous reading of Gamma's `takerBaseFee = 1000`):
  bound **+0.21 ¢/share, t 2.98 → the kill does not fire.**
- **But the on-chain fee is 0.07**, not 0.10: the v2 exchange's `FeeCharged` event equals 0.0700 · p(1−p) ·
  size on **24 / 24** sampled trades (`onchain_fee_check.py`). At the fee actually charged the bound is
  **+0.13 ¢/share with t 1.82 < 2**, which is the registered kill condition.

The registered evaluation passes only because of a fee assumption the data now contradicts, so, as with p07's
look-ahead universe, **the pass is recorded but not credited**. No strategy follows from it: a slow maker earns
less than the group bound (the fast makers' cancellations are the fills a slow maker keeps). Zero trials; no
trial log exists for this line.

Plan: `PLAN.md` (f1874aa) and amendment 1 (052c94d, after validation, before any P&L). Scripts committed
before any trade was read (15e06f4).

## Data and validation
| | |
|---|---|
| Markets | all 2,304 `btc-updown-5m` windows starting 2026-09-21 00:00 → 09-28 23:55 UTC; all found and resolved in Gamma (outcome 0 = Up) |
| Trades | Polymarket data API, taker trades (timestamps = block time, p15); none truncated |
| Volume gate | **96.1%** of markets within 1% of Gamma's volume counter (≥ 95%) |
| Collector cross-check | the collector's own trade stream has a median 97% of the API's share volume (it misses a few %) |
| Fees | Gamma: `feesEnabled`, `crypto_fees_v2`, base fee 1000 on all markets; collector `fee_rate_bps` = 0 on every trade (an order field, uninformative); **on-chain: 0.0700 · p(1−p) per share, 24/24** |

## The bound (maker P&L per share, equal weight per market, t clustered by market)
| fee rate for the rebate | bound ¢/share | t | share-weighted ¢/share | $ per day (all makers) | kill |
|---|---:|---:|---:|---:|---|
| **0.10 (registered, most generous)** | **+0.207** | **2.98** | +0.385 | 52.7 k | does not fire |
| **0.07 (charged on-chain)** | **+0.126** | **1.82** | +0.302 | 41.3 k | fires |
| 0 (no rebate) | −0.063 | −0.91 | +0.108 | 14.8 k | fires |

Rebate = 20% of the taker fee, assigned pro rata to every maker share (an upper bound on any one maker's
share of the pool). Equal weighting per market is the registered primary; share weighting is higher because
large trades are better for makers (below).

### Descriptive (fee 0.10 row; not decision inputs)
| time before window end | share of volume | ¢/share |
|---|---:|---:|
| before the window opens | 5.5% | +0.89 |
| 180–300 s | 31.2% | +0.42 |
| 60–180 s | 40.2% | +0.39 |
| last 60 s | 20.0% | +0.21 |
| after the window end | 3.1% | +0.22 |

| taker trade size (shares) | share of volume | ¢/share |
|---|---:|---:|
| ≤ 10 | 8.8% | −0.39 |
| 10–100 | 38.9% | −0.31 |
| 100–1,000 | 36.8% | +0.80 |
| > 1,000 | 15.5% | +1.59 |

- **Small takers win against makers, large takers lose** (even after a generous rebate). That is the adverse-
  selection pattern expected when small, fast bots pick off stale quotes; it is also exactly the flow a slow
  maker cannot avoid.
- By day: 7 of 8 days positive at fee 0.10; 2026-09-27 negative (−0.27 ¢).
- By price: makers earn least at the extremes (≤ 5 ¢ and ≥ 95 ¢: +0.10 to +0.17 ¢) and most at 5–40 ¢.

## What this means
- The passive side of Polymarket's 5-minute BTC markets does not earn the spread; it earns the fee rebate, and
  only when the book is aggregated over all makers, the fastest included. Before rebates makers lose to takers.
- At the fee actually charged, even that aggregate is not distinguishable from zero over 8 days.
- For a maker 127 ms behind Binance the bound is not reachable. NEWPLAN #4 is closed unless a later experiment
  measures slow-maker fills directly, which this result gives no reason to fund.

## Files
`PLAN.md` · `fetch.py` (throwaway VM, deleted) · `step1.py` (validate, measure) · `validate.log/json` ·
`measure.json` (0.10), `measure_fee007.json`, `measure_fee0.json`, `measure.log` · `onchain_fee_check.py/.log` ·
`selection_trials.json`.
