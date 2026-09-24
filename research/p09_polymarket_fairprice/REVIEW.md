# Review: p09_polymarket_fairprice

**Decision:** ACCEPT WITH FIXES. The verdict, "no takeable edge from this fair-value model", stands under every execution and weighting convention I tried. Three explanations in RESULTS.md are not supported and must be reworded: why the model loses, "anti-selected", and the t −3.9. The holdout is untouched.
**One line:** A driftless diffusion on a Binance proxy of the settlement price loses to the Polymarket mid on Brier score (+0.0061, t 10.4 by market, 2.8 by day). **All of that loss is in seconds where BTC is within 1 bp of the start price**, which is where our ~0.75 bp proxy error decides the outcome. Where the ex-ante gap is ≥ 3 bp, the model *beats* the mid (−0.0025, t −4.7 by market, −1.5 by day), but not by enough to pay the 0.5 c half-spread.

## Verification done by this review (own code on the parquet outputs, not the report)
- **Holdout.** The latest local `date=` folder is 2026-09-05. The latest resolution slug is 1788652500 (window start 09-05 23:55). The latest market in `step23_markets` ends at 23:55, so the 23:55 market, which needs hour 09-06 h00, is correctly dropped. `fetch.py`, `dev_files` and `load_day_pm` all assert dates before 09-06. `gamma.jsonl` has 11,964 rows, which is exactly the dev slug list. I did not read any holdout data.
- **Brier (recomputed):** model 0.1485, mid 0.1424 in (i). In (ii): 0.1273 vs 0.1278. Both match.
  - (i) difference +0.00611: s.e. 0.00059 clustered by market (t 10.4); s.e. 0.00218 clustered by day (t 2.8). Model worse on 34/43 days.
  - (ii) difference −0.0005, t −1.1 (market) / −0.4 (day).
- **Kill config P&L (recomputed):** 585,810 fills = 14,109/day. Median edge 5.21 c. P&L −1.150 c/contract. t by market −3.92 (11,913 clusters); t by day −3.69. 30/43 days negative. All match.
- **Step 1 / 1b:** `step1.json` and `step1b.json` match the RESULTS tables: 92.01%; blend/A 96.71%; 393 misses split 193/200, max 1.50 bp; best k = 4 for both series at 0.80 / 0.73 bp; slopes 0.92 / 0.95. I read the code. The windows, the spot 0.867…0.133 weighting and the point rule (last mid of bucket T−1) do what Amendment 2 says. `b_finalmid_vs_gamma` = 100% on 11,652.
- **Git order.** PLAN c7a8d6a (09-23 16:24) → A1 8cd3c37 → step 1 830f436 → A2 5c3ebce (09-24 09:50) → 1b 092b70d (09:54) → A3 bc5f967 (10:08) → step23 script 97621d8 (10:16) → results a9acb09 (10:37). Between the script commit and the results, the only change to `step23_fairvalue.py` was a `.rename("p_bin")` crash fix and a `--summarize-only` path. No parameter, universe or metric changed. `trials.json` and `harness/` are untouched. `selection_trials.json` has 12 `measurement` rows.

## Q1: look-ahead in Steps 2–3
- **The inputs are clean.**
  - Binance: futures buckets ≤ t−1 by event time, spot ≤ t−1 by receive time.
  - σ: `c2[j]-c2[j-900]`, i.e. log returns of buckets t−900…t−1.
  - Start reference: TWAP buckets end at t0. Spot receive bucket t0 has weight 0.133 and is complete at t0+1, while the first decision is at t0+1.2. The point rule uses bucket t0−1.
  - In-window known part: buckets te−W…t−1.
  - Polymarket state: bucket t−1 by payload time. The receive lag is ~11 ms p50 and 14 ms p95 (manifest `rt_lag_ms`), so it is known long before t+0.2. Nothing here leaks, and every input approximation handicaps the model, never helps it. The book sees the true Chainlink price-to-beat; we see a Binance proxy of it.
- **Fill state = the ask at the end of the arrival second. This is a sub-second look-ahead in both directions.**
  - 51% of fills are at an ask *below* the signal ask. The book moved against the token during second t, and the sim buys at the later, lower price.
  - Signals where the ask *rose* inside the second are dropped. In reality they would often have filled at the old ask, and they are the favourable ones.
  - The book-size lookup `searchsorted(bt, arr, 'right')` takes snapshots received up to t+1, i.e. up to 0.3–0.85 s after arrival, and `ask_sz_last` is the end-of-second size. Size is only a weight, but weighting turns out to matter (next bullet).
- **Bound.** I rebuilt the signals from `step2_seconds` and filled every signal at the signal ask. That is zero latency and ignores whether the book moved: new touch per episode, unit size. Result: **−0.31 c, t −1.2** (1.06 M signals, clustered by market). So no execution convention turns the aggregate positive. The *sign and significance* of −1.15 c / t −3.9, however, belong to one convention.
- **The headline is weighting-dependent, and this is the real problem with "t −3.9":**

| h (L = 0.5 s) | contract-weighted (reported) | fill-weighted | market-equal-weighted |
|---|---:|---:|---:|
| 1 c | −1.15 c, t −3.9 | −0.62 c, t −2.4 | +0.53 c, t +2.5 |
| 5 c | −1.57 c, t −3.2 | −0.81 c, t −2.0 | +1.80 c, t +6.2 |

  - The cause is **pyramiding**. "One fill per touch price" lets one market take 1–114 fills (median 49, ~13.6k contracts). Markets that trend against the model keep printing new touch prices, so the sim keeps buying: it averages down into losers. By fill-count quintile, per-market mean P&L goes from +4.0 c (fewest fills) to −3.9 c (most).
  - The market-equal column is not tradeable, because its weights depend on the future.
  - The tradeable version is **one entry per market** (first fill). That gives **+0.93 c, t 2.1** (h = 1 c) and +1.33 c, t 3.0 (h = 5 c). It is not robust: 22/43 days positive; first half −0.06 c, second half +1.8 c; 60 s rule only (+1.6 c; point and 30 s rules ≈ 0). Every entry sits within 20 s of the open, and I found it after ~20 looks at dev. **Do not claim it.** It is also not evidence *for* "anti-selected".

## Q2: is "overconfident in the tails, fat tails/jumps" supported? No.
- Brier by ex-ante |gap| (Binance now vs start reference, known at t):

| \|gap\| | < 1 bp | 1–3 bp | 3–10 bp | > 10 bp |
|---|---:|---:|---:|---:|
| model | 0.2343 | 0.1808 | **0.1051** | **0.0367** |
| mid | 0.2128 | 0.1733 | 0.1064 | 0.0426 |
| model − mid, t by market | +14.5 | — | (≥ 3 bp pooled) **−4.7** | (> 10 bp) **−7.5** |

- In the tail bin (model P > 0.9), realised Up depends on the gap:
  - gap > 10 bp: realised **0.983**; model 0.988 (close); mid 0.961 (*under*-confident).
  - gap < 1 bp: realised **0.83**; model 0.98; mid 0.82.
- By time to expiry, the model's worst bucket is 0–30 s (Brier 0.0395 vs 0.0235). There σ√τ is under a bp, so a 0.75 bp error in the reference or in S_t is decisive.
- Reading:
  - The model's tail failure is **input error at the ~1 bp scale**: the Binance proxy vs Chainlink Data Streams, both at the start reference and in the current price. It is not fat-tailed returns. Where the proxy is reliable, the Gaussian diffusion is *better* calibrated than the book.
  - "Book prices jump/vol-burst risk the model misses" (What we learned #1) has no support here. The fix it implies (a fat-tailed fair value) is the wrong next step.
  - "Mid better calibrated" is true unconditionally, and false in the region where the approximation holds.
- Model-free check: the mid's own reliability is within ~1.3 c of realised in every mid bin. That is less than half-spread plus the move, so there is no model-free favourite–longshot edge at the ask.

## Q3: cut (ii)
- **Your direction is right.** Conditioning on |finish gap| ≥ 1 bp removes the late reversals. That favours whichever forecaster is more extreme, here the model. Evidence: the model−mid Brier moves from +0.0061 to −0.0005, and the realised P&L of a favourite-buyer rises (−1.15 → −0.31 c).
- **But the owner's concern was also real, just misnamed.** It is not that "outcomes are wrong". The model's **inputs** are wrong precisely in near-tie markets. (ii) removes both effects at once, and ex post they cannot be separated. So neither (i) nor (ii) isolates what the owner wanted.
- **Better honest cuts:**
  - an ex-ante cut on |gap_now| (done). Ideally it should be normalised: |gap_now| / (σ√τ_eff) against the 0.75 bp proxy error. Pre-register it; don't pick it now.
  - report model *relative to mid* on the same cut. The conditioning bias hits both forecasters, so the relative number is less biased.
  - best: remove the proxy entirely (RTDS, below). Then no cut is needed.
- RESULTS should say (i) plus the ex-ante cut are primary. It already does, correctly flagged as a departure from the owner's rule. Keep that flag.

## Q4: Step 1/1b
- The agreement rates are computed correctly (above).
- The mapping has two caveats. Neither is a bug.
  - (a) The comparison is with the **on-chain aggregator**, not Data Streams. So "~0.7 bp of Data Streams is simply not Binance" is an extrapolation.
  - (b) Binance is sampled as the last mid of an integer-second bucket at an integer `updated_at`. With BTC at ~0.9 bp/s, that quantisation alone contributes a few tenths of a bp of residual. So 0.73–0.80 bp is an **upper bound** on non-Binance content vs the on-chain feed.
  - The centred rolling median is fine for a measurement (it is not a feature).
- The 4 s lag is plausible. On-chain `updated_at` is the transaction time, after the DON (Chainlink's oracle network) observes the price.

## Q5: notional and the kill
- **$2.05 M/day is not capacity.**
  - On 08-20 and 08-27, *all* BTC-5m trades in `last_trade_price` came to $8.0 M and $7.5 M. The sim "took" $1.23 M and $1.58 M on those days, 15–20% of the whole market's volume, with zero impact and zero competition, re-counting refilled and oscillating touches.
  - The $50/day clause passes under any sane sizing: 5 contracts × 288 markets × ~$0.5 ≈ $720/day. So that clause was never binding.
- **Kill.** Report it as "**did not fire; uninformative**". It was written on *model* edge, which only measures the model's disagreement with the book. The pre-registered realised check ("if realised < 0 while model edge > 0, the model is wrong") is what decides. That is what RESULTS does. Keep it, but drop "passed" from the verdict line.
- Lesson for every future kill here: **define it on realised P&L, one entry per market, with the weighting fixed in advance.**

## Blocking issues (RESULTS.md wording only; no rerun, no new rows)
1. **What we learned #1 and the reliability paragraph** ("fat tails, jumps and vol bursts … the market prices those") are not supported. Replace with the gap-bucket Brier table above: the model's deficit is entirely at |gap| < 1 bp and at τ < 30 s, consistent with the proxy error; at ≥ 3 bp the model beats the mid on Brier (t −4.7 by market, −1.5 by day) but not by enough to trade (reliable cut −0.39 c, t −1.0).
2. **"The bigger the claimed edge, the more it loses … anti-selected … the book is right"** holds only under contract weighting with pyramiding. Add the three-weighting table and the unit-size bound at the signal ask (−0.31 c, t −1.2). State that the t −3.9 is for "re-buy at every new touch price, size-weighted" and is not a property of the signal.
3. **Headline/kill line:** say "kill did not fire (model-edge criterion, uninformative); pre-registered realised-P&L check fails". Also report the missing **fee check**: PLAN required inspecting `fee_rate_bps` on raw `last_trade_price` events, and RESULTS is silent on it. Polymarket has charged taker fees on some short crypto markets. If fees are non-zero, every taker number here is optimistic. Do the check on dev raw events or disclose that it was not done.

## Non-blocking issues
- Latency: L = 150 ms and L = 500 ms are identical by construction, and L = 1 s is "the next second". Say that the grid effectively has 2 latencies, not 3.
- Universe count: "11,958 … all with complete Binance" conflicts with Step 1b's 11,934 with data. 24 markets have NaN references, which the loop silently drops (42 markets produce no seconds), and their `near_tie` flag is NaN → False. The count is harmless but wrong. State it.
- The staleness analysis is against on-chain CL, which the model no longer uses. "Direct evidence the book does not wait for on-chain Chainlink" is fine. It says nothing about lag to Binance or Data Streams.
- RESULTS reads bottom-up (Step 1 status below Step 2–3 status), and the Files list says "PLAN.md (with amendment 1)". Tidy up.
- Gas $0.02 and fees 0 are the owner's assumptions. Fine as disclosed.

## Selection hygiene
- Every amendment was committed before its computation (timestamps above). The 1b "best of 9" choice is disclosed. Amendment 3 was written after Step 1b's numbers but before any Step 2 computation, and it fixes the model with no fitted parameter. The 12 grid rows are all reported and nothing was chosen. No OOS was touched, so no `trials.json` row was owed.
- **My own looks count against dev.** This review ran ~20 extra cuts on dev: weightings, first-entry, tau/rule/half splits, and gap-bucket Brier. Dev is now exhausted for any Binance-input rule. Anything suggested by these cuts can only be *confirmed* on data not yet looked at.

## What the evidence supports
- The Polymarket 5m BTC book is well calibrated: mid vs realised within ~1.3 c in every bin, on 11.9k markets.
- A Binance-proxy diffusion loses to it only where the proxy's ~1 bp error matters. Elsewhere it is slightly better calibrated, by less than the spread.
- There is **no taker edge** from this model on dev under any convention I checked. The best-case bound is −0.31 c, t −1.2. "Significantly anti-selected" is a pyramiding artefact, not a finding.
- Market reasoning: near the strike and near expiry, the whole game is knowing the *settlement* price to a fraction of a bp. Polymarket makers watch the Chainlink stream the market settles on, and we modelled a Binance proxy. We lost exactly there. That points to data (the real feed and sub-second timing), not to a better σ model.

## Proposed next experiment (p10: RTDS settlement feed, fresh days only)
- **Hypothesis (falsifiable).** The rebroadcast `crypto_prices_chainlink` btc/usd stream reproduces Gamma resolutions on ≥ 99.5% of 5m markets. With it as both reference and S_t, the same unfitted diffusion's Brier deficit vs the mid in the |gap| < 1 bp bucket falls from +0.0215 to ≤ +0.005.
- **Exact change vs p09:** the price input (Binance proxy → RTDS Chainlink). Model, σ, grid and outcomes stay as in p09. It runs on new days only (from 2026-09-24 07:12). 09-06..09-20 has no RTDS, so the holdout cannot test this. Leave it untouched.
- **Plan:**
  - Step 0: after ≥ 7 full RTDS days (~2,000 markets), fetch Gamma for those slugs, rebuild settlement per rule, and report agreement. No prices vs book are looked at before this.
  - Step 1: Brier by gap bucket and τ, model vs mid. Measurement only.
  - Any taker test goes in a *later* PLAN. It must use one entry per market, a kill on realised P&L with fixed weighting, fees checked, and event-level (not 1 s) fills, because 1 s tables cannot resolve L < 1 s.
- **Kill (fixed now):**
  - Abandon the settlement-exact line if RTDS agreement is < 99.5%: the rebroadcast is then not the settlement feed.
  - Abandon diffusion fair value entirely if, with RTDS inputs, model−mid Brier at |gap| < 1 bp stays > +0.01: the deficit was not input error.
  - If both pass, the model is at best as good as the book. The only remaining edge is speed, and p11 must be an event-level lead-lag study (Binance/RTDS → book) with the p07b-review kills: lead-lag peak ≤ receive-latency difference ⇒ artefact.
- **Expected cost:** 0 holdout trials; ~1–2 weeks of waiting for data; one Gamma fetch on the VM; minutes of compute.
- **On the 09-06..09-20 holdout:** do **not** spend it on the first-entry-per-market pattern found in this review. It rests on ~20 looks, 22/43 days and one half of dev. If the owner wants closure on the Binance-input line before its data goes stale, run exactly one pre-registered test: h = 5 c, L = 0.5 s, first fill per market, unit size, Gamma outcomes, abandon if mean < +0.5 c or t < 2. Log it as one trial. Expect a null.
