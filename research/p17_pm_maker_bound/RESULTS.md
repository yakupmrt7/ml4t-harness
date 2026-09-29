# p17 — Maker P&L in Polymarket 5-minute BTC up/down markets: KILL FIRES on verified inputs

**Verdict: the passive side of these markets earns about zero before the fee rebate, and with the rebate
actually paid the result is not significant. NEWPLAN #4 is closed.** Over 2,304 markets (2026-09-21 → 09-28,
3.48 M taker trades, 110 M shares), maker P&L per share, equal-weighted by market (the registered statistic):

| inputs | bound ¢/share | t (registered: i.i.d. by market) | robust t | kill |
|---|---:|---:|---|---|
| **fee 0.07 with 20% rebate — verified on-chain** | **+0.126** | **1.82** | 1.70 / 1.66 (Newey-West 5 / 12), 1.56 (by day) | **fires (t < 2)** |
| no rebate | −0.063 | −0.91 | −0.85 / −0.83, −0.78 | fires |
| fee 0.10 (amendment 1's reading; false) | +0.207 | 2.98 | — | does not fire |

- **The kill fires once the fee is the one actually charged.** Amendment 1 (committed before any P&L) chose
  to evaluate the kill at fee 0.10, reading Gamma's `takerBaseFee = 1000` as the most generous case while
  Gamma and the collector disagreed. The on-chain `FeeCharged` event equals 0.0700 · p(1−p) · size on
  24/24 trades (`onchain_fee_check.py`) and 65/65 in the review, so 0.10 was a factual error, not a generous
  choice. Correcting a fact does not loosen any threshold, and it could not have manufactured a kill in
  reverse: the statistic rises with the fee rate, so a kill at 0.10 would also have been a kill at 0.07.
  The on-chain check was cheap and should have been done before amendment 1.
- **The rebate is confirmed and exact, not a bound.** Polymarket pays makers daily from `0xfdb1b8dc…` at
  **0.1997–0.1998** of their previous-day fee-equivalent (Σ 0.07 · shares · p(1−p) over their maker fills) for 3
  wallets over 4 wallet-days (review). The rebate is weighted by fee-equivalent, i.e. by p(1−p), which is what
  `step1.py` does, so the group number at 0.07 is the actual rebate paid to makers as a group. Makers pay no fee.
  A second daily payer (`0x520bf77d…`) paid one wallet $897 and $207 in amounts that do not track fills,
  probably liquidity rewards on other markets; not established (Gamma's rewards fields were not saved).
- **Share-weighted, the number is larger:** +0.30 ¢/share at fee 0.07 (t 3.4 on per-market $ P&L), +0.11 ¢
  without rebate (t 1.2); about $41 k/day to all makers with the rebate, $15 k/day without. This is not the
  registered statistic, and it is dominated by the trade-size effect below.
- **Group, not us:** the group average includes the fastest makers (who cancel stale quotes) and slow retail
  limit orders. A slow maker 127 ms behind Binance keeps the fills the fast ones avoid; a selective maker could
  beat the average. Either way the entire margin is the ~0.19 ¢/share rebate, while trade size alone moves
  maker P&L by about ±0.7 ¢/share, so there is nothing robust to build on.

Zero trials; no trial log exists for this line. Plan: `PLAN.md` (f1874aa), amendment 1 (052c94d, before any
P&L). The `step1.py` change that implements amendment 1's three fee readings was committed with the results
(f3cb0c9), not with the amendment.

## Data and validation
| | |
|---|---|
| Markets | all 2,304 `btc-updown-5m` windows starting 2026-09-21 00:00 → 09-28 23:55 UTC; all found and resolved (outcome 0 = Up; after the end the Up price averages 0.99 when Up won and 0.03 when it lost) |
| Trades | Polymarket data API taker trades: 3,479,125 rows = 3,479,125 distinct transactions (one row per taker order); side, size and price match the taker's on-chain fill to 1e-10 on 65 checked rows (review); none truncated |
| Volume gate | 96.1% of markets within 1% of Gamma's volume counter (≥ 95%); 73 of the 89 failures are markets whose counter reads 0 |
| Collector cross-check | the collector's own trade stream has a median 97% of the API's share volume |
| Fees | on-chain 0.0700 · p(1−p) per share on the taker; Gamma `crypto_fees_v2`, base fee 1000; collector `fee_rate_bps` = 0 (an order field, uninformative) |

## Descriptive (verified fee 0.07; `descriptive.py` → `descriptive.json`; not decision inputs)
¢/share is share-weighted within the bucket; t is of per-market ¢/share (equal weight), so the two can disagree
in sign.

| time before window end | share of volume | ¢/share (0.07) | t | ¢/share (no rebate) | t |
|---|---:|---:|---:|---:|---:|
| before the window opens | 5.5% | +0.74 | 1.37 | +0.39 | 0.35 |
| 180–300 s | 31.2% | +0.30 | 2.24 | +0.01 | 0.48 |
| 60–180 s | 40.2% | +0.32 | 1.25 | +0.15 | −0.49 |
| last 60 s | 20.0% | +0.17 | 4.87 | +0.09 | 3.80 |
| after the window end | 3.1% | +0.21 | 16.1 | +0.21 | 15.9 |

| price of Up | share of volume | ¢/share (0.07) | t | ¢/share (no rebate) | t |
|---|---:|---:|---:|---:|---:|
| ≤ 5 ¢ | 15.3% | +0.16 | 4.64 | +0.14 | 4.56 |
| 5–20 ¢ | 10.4% | +0.57 | 5.45 | +0.43 | 5.11 |
| 20–40 ¢ | 14.1% | +0.46 | 5.98 | +0.17 | 5.19 |
| 40–60 ¢ | 21.6% | +0.29 | −2.37 | −0.06 | −3.91 |
| 60–80 ¢ | 14.5% | +0.27 | 5.80 | −0.02 | 5.00 |
| 80–95 ¢ | 10.4% | +0.37 | 4.02 | +0.22 | 3.64 |
| ≥ 95 ¢ | 13.8% | +0.09 | 3.75 | +0.07 | 3.67 |

| taker trade size | share of volume | ¢/share (0.07) | t |
|---|---:|---:|---:|
| ≤ 10 shares | 8.8% | −0.49 | −11.7 |
| 10–100 shares | 38.9% | −0.41 | −6.6 |
| 100–1,000 shares | 36.8% | +0.72 | 4.7 |
| > 1,000 shares | 15.5% | +1.55 | 4.5 |
| by dollars: ≤ $10 / $10–100 / $100–1k / > $1k | 27.5 / 43.9 / 23.8 / 4.8% | +0.14 / −0.22 / +1.30 / +1.07 | +6.5 / −6.2 / +1.3 / −0.8 |

- **The share-size pattern is mostly a price effect:** 65% of the "> 1,000 shares" volume trades at ≤ 5 ¢ or
  ≥ 95 ¢ (cheap long shots and near-certain buys). By dollar size the pattern is not monotone, so nothing here
  says "small fast takers pick off makers"; that story is conjecture and is not claimed.
- **Mid prices (40–60 ¢) are the worst range for makers without the rebate**, and the rebate is largest there
  (it is proportional to p(1−p)). Trades after the window end are near-certain and small (3% of volume).

## What this means
- Makers as a group capture about nothing from takers in these markets; the 20% rebate on a 0.07 · p(1−p) taker
  fee is the whole margin, and over 8 days even that is not distinguishable from zero on the registered statistic.
- With p09 (taker, killed), p15 (Polymarket vs Deribit, killed) and now p17, Polymarket's crypto markets have
  failed three pre-registered tests from both sides. NEWPLAN #4 is closed.

## Files
`PLAN.md` · `fetch.py` (throwaway VM, deleted) · `step1.py` (validate, measure) · `descriptive.py` ·
`validate.log/json` · `measure.json` (0.10), `measure_fee007.json`, `measure_fee0.json`, `measure.log` ·
`descriptive.json/log` · `onchain_fee_check.py/.log` · `selection_trials.json` · `REVIEW.md`.
