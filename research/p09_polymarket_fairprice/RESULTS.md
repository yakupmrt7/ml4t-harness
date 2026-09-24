# p09 Polymarket 5-minute BTC up/down: Step 1 (settlement reconstruction)

**Status: STOPPED at the Step-1 gate.** The rebuilt Chainlink outcome agrees
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

## Options (owner's decision)
1. **Stop p09 here** (the pre-registered default). The collector does not
   capture the settlement price source.
2. **Record the real source going forward.** Add Chainlink Data Streams,
   or the Chainlink price stream Polymarket rebroadcasts on its live-data
   websocket (topic name not yet confirmed), to the collector. Rerun p09 on
   new days only. Existing dev/holdout data cannot fix this.
3. **Continue to Step 2 as a disclosed approximation.** Use Gamma outcomes,
   and on-chain Chainlink or Binance for the current price. Not
   recommended, for the reasons above.

## Files
- `PLAN.md` (with amendment 1)
- `fetch.py`: dev-only downloader
- `fetch_resolutions.py`: Gamma fetch, dev slugs only
- `step1_settlement.py`
- `step1.json`, `step1.log`, `step1_disagreements.csv`
- Local, gitignored:
  - `data/collector/p09/resolutions.parquet` and `gamma.jsonl` (raw API rows)
  - `step1_settlement.parquet`

Reproduce (repo root):
`python research/p09_polymarket_fairprice/fetch.py`, then
`python research/p09_polymarket_fairprice/step1_settlement.py`. The Gamma
fetch needs a host that can reach Polymarket: see `fetch_resolutions.py`.
