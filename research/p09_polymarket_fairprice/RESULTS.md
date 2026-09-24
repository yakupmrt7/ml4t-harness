# p09 Polymarket 5-minute BTC up/down: Step 1 / 1b (settlement reconstruction)

> **Settlement approximation (read this first).** These markets settle on
> **Chainlink Data Streams** (BTC/USD point / 30 s TWAP / 60 s TWAP,
> depending on the period). The collector did not record that feed for the
> dev period. Everything from Step 2 on approximates it with a **TWAP of the
> Binance mid** (50/50 futures/spot blend, each market's own rule window).
> That approximation reproduces Polymarket's actual resolutions on **96.7%**
> of dev markets. The residual against Chainlink is **~0.75 bp** of
> non-Binance content (Step 1b), and every miss is within 1.5 bp of a tie.
> Outcomes in Steps 2–3 are **Gamma resolutions**, never the rebuild. Every
> Step 2/3 number is reported twice: all markets, and excluding markets
> whose finish is within 1 bp of a tie. Where the two differ materially, the
> second is the honest one.

**Status (after Steps 2–3): the model-based edge is not real, so there is
no takeable edge to report.** The pre-registered kill (median takeable edge
≥ 1 c AND ≥ $50/day) is **passed mechanically, but invalidated by realised
P&L.**
- The model claims a median 5.2 c edge per filled contract. Trading it
  **loses** 1.15 c per contract (t = −3.9, clustered by market) against
  Gamma outcomes.
- The Polymarket mid is better calibrated than the model (Brier 0.1424 vs
  0.1485).

PLAN.md says what to do in this case: "If realised P&L is negative while
model edge is positive, the model is wrong, and that is reported as such."
No trading rule is selected. The holdout is untouched.

**Status after Step 1b (superseded): STOPPED for the owner's decision.** A TWAP of the
Binance mid (50/50 futures/spot blend) reproduces Polymarket's resolution on
**96.7%** of dev markets, against 92.0% from on-chain Chainlink. The
owner's rule puts 95–98% in the "report and stop" band (PLAN.md,
amendment 2). The holdout is still untouched.

**Step 1 status: STOPPED at the Step-1 gate.** The rebuilt Chainlink outcome agrees
with Polymarket's resolution on **92.0%** of dev markets (11,003 / 11,958).
The pre-registered gate is ≥ 99% (PLAN.md, amendment 1). Steps 2–3 were not
run. The holdout (2026-09-06 → 09-20) was not read, and no holdout slug was
requested. No `trials.json` or `selection_trials.json` entries.
Next step: the owner's decision (see "Options").

## What was done
- **Data:** dev only (2026-07-25 → 09-05), from `features/v1` (p08). Each
  date folder's file count was checked against its manifest. Fixed
  exclusions: 07-25 h00–17, 07-26 h01/03/04, 08-04 h16–23. The chainlink
  stream is also missing 07-25 h22.
- **Markets:** all 11,964 dev 5m BTC up/down markets (window start ≤
  2026-09-05 23:55 UTC). 11,959 have complete Chainlink hours.
- **Resolution rule per market,** from its own `resolutionSource`:

| period (5m markets) | resolution source | markets |
|---|---|---:|
| 07-25 → 08-06 | Chainlink `btc-usd` (point price) | 3,325 |
| 08-07 → 08-13 | `btc-usd-twap-30s` | 2,016 |
| 08-14 → 09-05 | `btc-usd-twap-60s` | 6,623 |

- **Ground truth: Polymarket's Gamma API** (`/markets?slug=…&closed=true`,
  with a fallback to a plain query). Fields relied on: `closed`,
  `umaResolutionStatus`, `outcomes`, `outcomePrices`; `closedTime` and
  `automaticallyResolved` are recorded too.
  - 11,963 markets are resolved (Up 5,941, Down 6,022).
  - 1 is unresolved (prices 0.995/0.005) and was skipped.
  - None are void.
  - The fetch ran on `poly-collector-eu`, because Polymarket is not
    reachable from the owner's machine. It made ~2 requests/s at the lowest
    CPU priority, then its working folder was deleted.
- **Rebuilt settlement:** a step function of the collector's Chainlink
  rounds, deduped by `updated_at`. Candidates:
  - A: trailing windows [T − W, T] at start and end;
  - B: point value (last round ≤ T);
  - C: forward start window.

  Up if end ≥ start. The best candidate per rule is the one disclosed choice
  (PLAN.md): B for `btc-usd` and twap-30s, A for twap-60s.

## Chainlink feed (the collector's copy)
- 108,207 rounds in dev.
- Gap between rounds: median **33 s**; p5 31 s, p95 35 s, p99 44 s; max
  8 h (outage).
- 5,673 one-second buckets held 2+ rounds. Only the last round per second
  survives the p08 1s table.
- Rounds inside the final window: the 60s regime has 0 rounds in 0.02% of
  markets, usually 1–2. The 30s regime is scored with its best candidate,
  B (point), so it has no window rounds by construction.

## The three agreement rates

| rule | markets | (a) rebuilt vs Gamma | (b) final mid vs Gamma | (c) rebuilt vs final mid |
|---|---:|---:|---:|---:|
| point, 07-25 → 08-06 | 3,320 | 87.3% (B) | 100% (3,290) | 87.5% |
| twap-30s, 08-07 → 08-13 | 2,016 | 93.2% (B; A 90.8, C 91.1) | 100% (2,007) | 93.1% |
| twap-60s, 08-14 → 09-05 | 6,622 | **94.0% (A; B 93.1, C 90.8)** | 100% (6,355) | 94.0% |
| **all** | **11,958** | **92.0%** | **100% (11,652)** | 92.0% |

- "Final mid" = the last Up-token mid in [T_end − 5 s, T_end + 60 s]. It
  calls Up above 0.95 and Down below 0.05, and makes no call in between.
  It makes a call for 11,653 of 11,918 markets that have a mid.
- **(b) = 100%:** Polymarket's own book at expiry always agrees with the
  resolution. Our rebuilt outcome, (a), does not.

## Where the disagreements are (a, best candidate)

By the gap between start and end, |TWAP_end / TWAP_start − 1|:

| gap | < 0.1 bp | 0.1–0.3 | 0.3–1 | 1–3 | 3–10 | > 10 bp |
|---|---:|---:|---:|---:|---:|---:|
| markets | 252 | 468 | 1,295 | 2,753 | 4,751 | 2,438 |
| agree | 59% | 68% | 76% | 89% | 97.9% | 99.8% |

- **Direction:** 955 disagreements. 472 are rebuilt Up / Gamma Down and 483
  are rebuilt Down / Gamma Up. There is no directional bias, which rules
  out a sign or offset error.
- **Size:** in bp, half of the disagreements have a gap under 0.78, 90%
  under 3.1, 99% under 7.7, and the largest is 17.9.
  - The largest ones are all in the point-price period: the last on-chain
    round can be up to ~33 s old, and BTC moves that much in 33 s.
- **By day:** agreement ranges from 58% on 2026-07-25 (a partial first day)
  to 96.5%, with a median of 93.1%.
- **Ties:** 10 markets with start = end.
- The full list is in `step1_disagreements.csv`, with start/end, gap,
  rounds in each window and the final mid.

## Reading
The reconstruction is not systematically wrong. The misses have no
direction and fall away smoothly as the gap grows, which is the
near-tie signature. But the near-tie zone is **wide**. The collector
records Chainlink's **on-chain Polygon aggregator** (one round every ~33 s),
while the markets settle on **Chainlink Data Streams** (sub-second reports).
A 60 s window therefore contains only ~2 of our prices. 40% of markets
have a gap under 3 bp (~$20 at $65k BTC), and in that zone we miss about
1 in 6.

Consequences for the rest of p09:
- **Polymarket's price source is better than ours:** its final mid is 100%
  right, and ours is 92%.
- **A Step-2 "gap" would mostly measure our feed's staleness.** A fair value
  built on this feed is weakest exactly in close markets, which is where any
  mispricing would be.
- **The kill cannot be evaluated honestly with this settlement model.** Any
  takeable edge would sit where our settlement is wrong 11–40% of the time.

## Step 1b: Binance mid instead of on-chain Chainlink (PLAN.md, amendment 2)
Same markets, same Gamma ground truth. 11,934 of the 11,958 have complete
bookTicker hours; the other 24 are left out.
- Futures is bucketed on Binance event time.
- Spot is bucketed on receive time and shifted back 133 ms, its median
  receive lag.
- The blend averages the log mids of futures and spot.
- Windows match each market's rule: point / 30 s / 60 s. A (trailing) is
  primary; B and C are reported too. The best of the 9 (series ×
  candidate) variants is a disclosed choice.

| variant | point 07-25→08-06 | twap-30s 08-07→08-13 | twap-60s 08-14→09-05 | all |
|---|---:|---:|---:|---:|
| on-chain Chainlink (Step 1, best) | 87.3 | 93.2 | 94.0 | 92.0 |
| Binance futures, A | 96.0 | 92.0 | 96.8 | 95.8 |
| Binance spot, A | 96.2 | 93.4 | 97.3 | 96.3 |
| **Binance 50/50 blend, A** | **97.0** | **93.9** | **97.4** | **96.7** |
| blend, B (point at both ends) | 97.0 | 90.0 | 88.5 | 91.1 |
| blend, C (forward start window) | 97.0 | 88.3 | 87.5 | 90.3 |

Trailing windows (A) clearly beat the alternatives for the TWAP rules. The
point rule is identical across A/B/C by construction.

Blend/A agreement by gap bucket:

| gap | < 0.1 bp | 0.1–0.3 | 0.3–1 | 1–3 | 3–10 | > 10 bp |
|---|---:|---:|---:|---:|---:|---:|
| markets (by the blend's own gap) | 292 | 426 | 1,282 | 2,760 | 4,714 | 2,460 |
| agree | 54% | 69% | 90.8% | 99.6% | **100%** | **100%** |
| agree, bucketed by the on-chain gap (Step 1) | 83% | 80% | 90% | 96.6% | 99.2% | 100% |

- **Disagreements:** 393, split 193 rebuilt Up / Gamma Down and 200 the
  other way, so there is again no direction. **All are within 1.5 bp** of a
  tie on the blend's own gap: median 0.18 bp, p90 0.59, p99 1.24.
- **Blend vs on-chain, on the same markets:**
  - both right: 10,702;
  - Binance right, on-chain wrong: 839;
  - Binance wrong, on-chain right: 291;
  - both wrong: 102.
- The full list is in `step1b_disagreements.csv`.

### How well Binance stands in for the (on-chain) Chainlink feed
The on-chain Chainlink round price at time u is compared with the Binance
mid at u − k. A rolling 1 h median basis is removed first. The table shows
the residual std in bp:

| k (s) | −5 | 0 | 2 | 3 | **4** | 5 | 6 | 8 | 10 | 15 | 30 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| futures | 2.15 | 1.51 | 1.16 | 0.97 | **0.80** | 0.81 | 0.96 | 1.29 | 1.62 | 2.36 | 3.59 |
| spot | 1.96 | 1.30 | 0.99 | 0.81 | **0.73** | 0.82 | 1.02 | 1.36 | 1.70 | 2.43 | 3.63 |

- **Lead/lag:** an on-chain round stamped u reflects the Binance price of
  about **4 s earlier**. Binance leads the on-chain feed by ~4 s.
- **Returns regression, round to round, at k = 4:**
  - futures: slope 0.92, R² 0.93, residual 0.96 bp;
  - spot: slope 0.95, R² 0.93, residual 0.91 bp.

  The slope is below 1 because Chainlink is an aggregate across venues and
  Binance moves a little more.
- **Residual size:** ~0.7–0.8 bp in level at the best lag. That is about
  the size of the gap where settlement agreement drops below 90%. That
  residual is the floor on how well any Binance-based rebuild can do.

### Reading
- Binance is a much better stand-in for the settlement feed than our
  on-chain copy: 96.7% vs 92.0%. Beyond a 1 bp gap it is essentially
  exact: 99.6% at 1–3 bp and 100% above 3 bp.
- **What remains is irreducible with Binance alone.** Every miss is within
  1.5 bp of a tie. 17% of markets (2,000) have a gap under 1 bp, and there
  agreement is 54–91%. Chainlink Data Streams is a multi-venue aggregate,
  and ~0.7 bp of it is simply not Binance.
- **For a fair-value model this matters less than for settlement.** A
  market that ends within 1 bp of its strike is a near-coin-flip for
  everyone, the book included. The mispricing Step 2 looks for would have
  to be much larger than 1 bp of BTC to clear a Polymarket spread. That is
  an argument, not a measurement.
- **Not tried (would be a new, undisclosed parameter):** shifting the
  Binance windows by the ~4 s lag seen against the on-chain feed. The
  lag is to the on-chain aggregator, not to Data Streams, so there is no
  basis for pre-registering a shift.

## Options (owner's decision)
*(Written after Step 1; still relevant, with Step 1b's 96.7% in hand.)*

1. **Stop p09 here** (the pre-registered default). The collector does not
   capture the settlement price source.
2. **Record the real source going forward.** Add Chainlink Data Streams,
   or the Chainlink price stream Polymarket rebroadcasts on its live-data
   websocket (topic name not yet confirmed), to the collector. Rerun p09 on
   new days only. Existing dev/holdout data cannot fix this.
3. **Continue to Step 2 as a disclosed approximation.** Use Gamma outcomes,
   and on-chain Chainlink or Binance for the current price. Not
   recommended, for the reasons above.

## Steps 2–3: fair value vs the market, and what is takeable (PLAN.md, amendment 3)
- **Universe:** 11,958 Gamma-resolved dev markets, all with complete
  Binance, price_change and book hours; 11,916 produce at least one scored
  second. That is 3.56 M market-seconds, ≈ 41.5 market-days.
- **Model:** driftless diffusion on the Binance blend; start reference =
  the Step-1b blend over the rule window; σ = trailing 15 min realised vol
  of the 1 s futures mid; no fitted parameter; no lag shift.
- **Timing:** decisions at t + 0.2 s, using 1 s buckets ≤ t − 1.
- **Outcomes:** Gamma.
- **The two cuts:** (i) all markets; (ii) excluding the 2,000 markets whose
  finish is within 1 bp of a tie.

### Which of the two cuts is honest here: (i), not (ii)
The owner's rule says that if (i) and (ii) differ materially, (ii) is the
honest one. That rule assumed near-tie markets carry wrong outcomes. In
Steps 2–3 the outcomes are **Gamma resolutions, so every market's outcome
is the true one.**
- Dropping markets that *finish* near the tie conditions on the future.
  It removes exactly the late reversals that punish an overconfident
  model, so (ii) is biased **upward**.
- The settlement approximation affects only the model's *input* (the start
  reference, ±0.75 bp). The ex-ante flag below handles that without
  looking ahead.
- So (ii) is reported as asked, but **(i), and the ex-ante "reliable" cut,
  are the honest numbers.** This is flagged for the owner, not silently
  applied.

### Step 2: calibration first
| | Brier, model | Brier, Polymarket mid |
|---|---:|---:|
| (i) all | 0.1485 | **0.1424** |
| (ii) excl. near-tie finish | 0.1273 | 0.1278 |

Reliability of the model's P(up) against Gamma outcomes, in (i):

| model P bin | 0–0.1 | 0.1–0.2 | 0.2–0.3 | 0.3–0.4 | 0.4–0.5 | 0.5–0.6 | 0.6–0.7 | 0.7–0.8 | 0.8–0.9 | 0.9–1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| mean model P | 0.020 | 0.150 | 0.251 | 0.352 | 0.463 | 0.546 | 0.649 | 0.749 | 0.850 | 0.981 |
| realised Up | 0.049 | 0.182 | 0.258 | 0.342 | 0.460 | 0.542 | 0.643 | 0.733 | 0.825 | 0.955 |
| mean Polymarket mid | 0.066 | 0.194 | 0.276 | 0.361 | 0.465 | 0.550 | 0.644 | 0.733 | 0.813 | 0.935 |

The model is well calibrated in the middle and **overconfident in the
tails**. When it says 0.98, Up happens 95.5% of the time, and the mid
(0.935) was closer. That is the classic failure of a Gaussian diffusion
with a trailing-vol σ: fat tails, jumps and vol bursts inside 5 minutes.
The market prices those, and the model does not.

**Gap = model − mid, by time to expiry (i):**

| time to expiry | 0–30 s | 30–60 | 60–120 | 120–180 | 180–240 | 240–300 |
|---|---:|---:|---:|---:|---:|---:|
| median \|gap\| (probability points) | 0.005 | 0.009 | 0.027 | 0.035 | 0.038 | 0.031 |
| p90 \|gap\| | 0.135 | 0.174 | 0.152 | 0.130 | 0.117 | 0.101 |
| share of seconds with \|gap\| > half-spread | 27% | 54% | 79% | 91% | 92% | 89% |

- Median half-spread is 0.5 c: the book is one tick wide almost always.
- **Quoted size at the touch when |gap| > half-spread:** known (fresh book
  snapshot at the same price) in 82% of those 2.80 M seconds; median 178
  contracts, p90 698.
- **By on-chain Chainlink staleness** (0–2, 2–5, 5–15, 15–30, > 30 s since
  the last round): the median |gap| is 0.0276–0.0279 in every bucket, and
  the share beyond the half-spread is 78.6–79.0%. **No "just after a feed
  update" effect.** That is expected once the model runs on Binance and not
  the on-chain feed. It is also direct evidence that the book does not
  wait for on-chain Chainlink.

### Step 3: taking the touch when model − ask ≥ h
- **Fills:** at the ask in the second the order arrives, only if that ask
  is still ≤ the signal ask. Size = the fresh book size at that price,
  else 0 (below 5 contracts = 0). One fill per touch price.
- **Holding and cost:** held to Gamma resolution; gas $0.02 per position;
  fees 0.
- **Latency:** L = 150 ms and L = 500 ms give **identical** results. With
  1 s tables, both arrivals land in the same second, so latency below
  ~1 s is **not resolved** by this data.

| h, L | fills/day | median model edge at fill | realised P&L / contract | t (by market) | realised $/day after gas | notional $/day |
|---|---:|---:|---:|---:|---:|---:|
| **1 c, 0.5 s (kill config)** | 14,109 | **5.2 c** | **−1.15 c** | **−3.92** | −45,019 | 2.05 M |
| 1 c, 1.0 s | 12,542 | 6.2 c | −1.30 c | −4.52 | −45,932 | 1.74 M |
| 2 c, 0.5 s | 11,525 | 6.2 c | −1.24 c | −3.65 | −37,626 | 1.54 M |
| 3 c, 0.5 s | 9,341 | 7.3 c | −1.36 c | −3.51 | −32,508 | 1.18 M |
| 5 c, 0.5 s | 6,136 | 9.9 c | −1.57 c | −3.19 | −23,569 | 0.71 M |
| *(ii)* 1 c, 0.5 s | 13,269 | 4.8 c | −0.31 c | −0.99 | −11,912 | 2.08 M |
| *(ii)* 5 c, 0.5 s | 5,140 | 9.0 c | +0.20 c | +0.37 | +2,669 | 0.67 M |

(The full 12-row grid, with (ii) for every row, is in `step23.json` and
`selection_trials.json`, marked `measurement`.)

- **The bigger the claimed edge, the more it loses:** realised P&L falls
  from −1.15 c to −1.57 c as h rises from 1 c to 5 c. The signal is anti-selected.
  When the model disagrees most with the book, the book is right.
- **By ex-ante gap at decision** (kill config, (i)):

| \|current gap\| | < 0.1 bp | 0.1–0.3 | 0.3–1 | 1–3 | 3–10 | > 10 bp |
|---|---:|---:|---:|---:|---:|---:|
| fills/day | 1,037 | 906 | 2,412 | 4,390 | 4,512 | 852 |
| median model edge | 7.8 c | 7.8 c | 6.6 c | 5.4 c | 4.4 c | 3.7 c |
| realised P&L / contract | −3.32 c | −1.73 c | −2.29 c | −1.09 c | −0.55 c | +0.25 c |
| t | −3.86 | −2.26 | −4.24 | −2.53 | −1.25 | +0.38 |

- **"Reliable" (ex-ante |gap| ≥ 3 bp):** 5,363 fills/day, median model
  edge 4.3 c, realised **−0.39 c/contract, t = −0.97**, −$6.6k/day. In
  (ii): +0.56 c, t = 1.44. Where our settlement approximation is
  trustworthy, the edge is ~0, not 4 c.
- **The notional ($0.6–2 M/day) is not takeable capacity.** It re-counts
  replenished touch liquidity every time the price ticks, over 288 markets
  a day. It only says size is not the binding constraint: the model is.

### Kill criterion, as pre-registered (h = 1 c, L = 500 ms)
| | median takeable (model) edge | takeable size $/day | kill fires? | realised P&L / contract |
|---|---:|---:|---|---:|
| (i) all | 5.2 c (≥ 1 c) | 2.05 M (≥ $50) | **no, mechanically** | **−1.15 c, t −3.9** |
| (ii) excl. near-tie finish | 4.8 c | 2.08 M | no, mechanically | −0.31 c, t −1.0 |

The kill was written on *model* edge, with realised P&L as the check on
the model. The check fails: significantly negative in (i), zero in (ii),
zero in the ex-ante reliable cut. **Verdict: there is no takeable edge from
this fair-value model.** What the kill "passes" is the model's own
miscalibration.

### What we learned
1. The Polymarket 5-minute BTC book is **better calibrated than a
   textbook diffusion on Binance**, especially in the tails. It prices the
   jump and vol-burst risk that a Gaussian model with trailing σ misses.
2. The hypothesised lag (book slow to react to the settlement feed) does
   **not show up at 1 s resolution** against the on-chain feed. The gap is
   flat across Chainlink staleness buckets. Any latency edge would sit
   below 1 s, which this data (1 s tables, ~127 ms collector lag) cannot
   resolve.
3. Next steps that would make sense: a sub-second (event-level) test of
   book reaction to Binance moves, and/or a fat-tailed fair value. Each
   needs its own PLAN. The holdout (09-06 → 09-20) is still untouched and
   is the only clean data left for this line.

## Collector: the real settlement feed, recorded from 2026-09-24 07:12:35 UTC
Added on `poly-collector-eu` (e2-small: 2 vCPU, 2 GB RAM). The existing
`collector.service` used ~20% CPU and 109 MB, with 1.47 GB of memory free,
so there was room for this.
- **What:** Polymarket's live-data websocket (`wss://ws-live-data.polymarket.com`),
  topic `crypto_prices_chainlink`, unfiltered `update` subscription. It
  carries the Chainlink prices Polymarket's crypto up/down markets settle
  on, once per second per symbol (btc/usd, eth/usd, sol/usd, xrp/usd,
  doge/usd, …), with the Chainlink observation timestamp and a
  full-precision value.
  - Subscribing with a `{"symbol": …}` filter returned only a snapshot,
    so the subscription is unfiltered.
- **How (existing streams not disturbed):** a separate process and
  systemd unit, `poly-rtds.service` (`Nice=5`, `MemoryMax=256M`,
  `Restart=always`), running `scripts/rtds_collector.py`. A copy is in
  `collector/rtds_collector.py` here.
  - It reuses the collector's own `RawWriter` and `run_ws` (reconnect,
    recv-time stamping), with an app-level PING every 5 s.
  - It writes `data/raw/{date}/polymarket_rtds/crypto_prices_chainlink/{HH}.ndjson`,
    which the existing cron compaction (`rglob *.ndjson`) and GCS push pick up
    unchanged: `eu-raw_pq/{date}/polymarket_rtds__crypto_prices_chainlink__{HH}.parquet`.
  - Its operational log is its own feed, `polymarket_rtds/_log`; it never
    appends to `collector_log`.
  - `collector.service` was not restarted: the same PID before and after.
    The new process uses ~1% CPU and ~31 MB.
- **Not added: Chainlink Data Streams directly.** It needs Chainlink-issued
  API credentials (a commercial product), and none are available here.
  Polymarket's rebroadcast is the practical substitute. That it matches
  resolutions exactly still has to be verified, once enough days of it
  have accumulated.
- **When usable:** from 2026-09-24 07:12 UTC. The retention job pushes days
  older than 2 days, so the first day on GCS is expected around 2026-09-26/27.

## Files
- `PLAN.md` (with amendment 1)
- `fetch.py`: dev-only downloader
- `fetch_resolutions.py`: Gamma fetch, dev slugs only
- `step1_settlement.py`
- `step1.json`, `step1.log`, `step1_disagreements.csv`
- `step1b_binance.py`, `step1b.json`, `step1b.log`, `step1b_disagreements.csv`
- `step23_fairvalue.py`, `step23.json`, `step23.log`, `step23_counts.json`, `selection_trials.json` (12 measurement rows)
- Local, gitignored: `step2_seconds.parquet`, `step3_trades.parquet`, `step23_markets.parquet`
- Local, gitignored:
  - `data/collector/p09/resolutions.parquet` and `gamma.jsonl` (raw API rows)
  - `step1_settlement.parquet`

Reproduce (repo root):
`python research/p09_polymarket_fairprice/fetch.py`, then
`python research/p09_polymarket_fairprice/step1_settlement.py`. The Gamma
fetch needs a host that can reach Polymarket: see `fetch_resolutions.py`.
