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

**Status (after Step 1b): STOPPED for the owner's decision.** A TWAP of the
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
- Local, gitignored:
  - `data/collector/p09/resolutions.parquet` and `gamma.jsonl` (raw API rows)
  - `step1_settlement.parquet`

Reproduce (repo root):
`python research/p09_polymarket_fairprice/fetch.py`, then
`python research/p09_polymarket_fairprice/step1_settlement.py`. The Gamma
fetch needs a host that can reach Polymarket: see `fetch_resolutions.py`.
