# p08 step 2: proposed reduction job (NOT run — for approval)

Goal: turn 261 GB of raw JSON-in-parquet into ~2.5 GB of 1-second and
1-minute feature tables under `gs://YOUR-GCS-BUCKET/features/`, so
research runs on a laptop. Read-only on `eu-raw_pq/`; the job writes only
under `features/`.

## Where the work is
From step 1 (`SCHEMAS.md`): 186 M rows/day, of which `polymarket__price_change`
(62.7 M) and `binance_fut@bookTicker` (75.7 M) are 90% of the bytes.
**JSON parsing is ~95% of the CPU.** Measured single-core, orjson, on this
laptop:

| stream | rows/day | measured rate | core-s/day |
|---|---:|---:|---:|
| binance_fut@bookTicker | 75.7 M | 183 k rows/s (end-to-end) | 414 |
| polymarket__price_change | 62.7 M | 129 k rows/s parse | ~630 |
| binance_spot@bookTicker | 23.4 M | ~183 k rows/s | 128 |
| binance_fut@trade | 11.6 M | 207 k rows/s | 58 |
| binance_spot@trade | 9.4 M | 207 k rows/s | 47 |
| polymarket__book | 1.4 M | 17 k rows/s (99-level ladders) | 84 |
| binance_fut@depth20@100ms | 0.8 M | 11.8 k rows/s (40 levels) | 71 |
| everything else | <0.7 M | — | <10 |
| **total** | **186 M** | | **~1,440 core-s/day** |

58 days ≈ **23 core-hours on a laptop core**, ≈ **30–40 core-hours on a
c3 vCPU** (Sapphire Rapids single-core is roughly 0.6–0.8× this machine for
this workload; the estimate should be confirmed by the 1-day pilot below).

## Machine and cost (us-central1, same continent as the US multi-region bucket)
Reads from a US multi-region bucket to a us-central1 VM incur **no egress
charge**; ~17 k GET operations cost about $0.01. The job is CPU-bound, not
network-bound: 261 GB at a few hundred MB/s is ~15 minutes of transfer
spread across the run.

| option | vCPU | $/hr on-demand | $/hr spot | est. wall time | est. cost |
|---|---:|---:|---:|---:|---:|
| `c3-highcpu-8` | 8 | ~$0.28 | ~$0.09 | 5–7 h | $1.5–2 |
| **`c3-highcpu-22` (recommended)** | 22 | ~$0.77 | ~$0.25 | **2–3 h** | **~$2** |
| `c3-highcpu-44` | 44 | ~$1.54 | ~$0.50 | 1–1.5 h | ~$2 |

Plus a 50 GB pd-balanced scratch disk (~$0.005/hr). Spot is ~70% cheaper and
safe here because the job is resumable, but preemption mid-run adds wall
time; on-demand for ~3 h at ~$2 is simplest. **Total cost of the full run is
a few dollars**, so the machine choice matters less than getting the
features right.

Memory: process one **row group** at a time, not one file. A 197 MB
price_change file expands to several GB as Python objects if materialised
whole; per row group (~20 k rows) it stays ~200 MB per worker. 22 workers
fit comfortably in 44 GB.

## Work unit, chunking and resumability
- **Unit = (date, stream, hour)**: 12 streams × 24 h × 58 days = **16,704
  units**, each reading exactly one input object. Embarrassingly parallel.
- Outputs per unit:
  `features/v1/1s/<stream>/date=YYYY-MM-DD/<stream>__<HH>.parquet`
  `features/v1/1m/<stream>/date=YYYY-MM-DD/<stream>__<HH>.parquet`
  `features/v1/_manifest/<stream>/date=YYYY-MM-DD/<HH>.json`
- **Resume rule:** if the manifest object exists and records the same input
  `generation`, size and `code_version`, skip the unit. So a killed or
  preempted VM restarts with no lost work, and a changed input or a bumped
  code version reprocesses.
- **Atomicity:** GCS object creation is atomic, so a partial write never
  becomes visible. Outputs are written first, the manifest last: a crash
  leaves outputs without a manifest, and the unit is simply redone.
- Manifest records: input path/generation/size/crc32c, output row counts,
  first/last bucket, code version, parse errors, wall time. That doubles as
  the validation table (e.g. hours with zero rows, or gaps).
- The driver writes a work list, shuffles it (so the two heavy streams don't
  all land at once), and a pool of workers claims units.

**Integrity (from the step-1 incident):** a stalled `gcloud storage cp`
produced a byte-complete but ZSTD-corrupt file. Every unit must verify
**CRC32C against object metadata** before parsing (the
`google-cloud-storage` client does this on download, or `google-crc32c`
explicitly), and treat a mismatch as a retry, not a failure. Also note
`gcloud storage cp` stalled repeatedly on 60–200 MB objects from this
laptop, while a plain authenticated HTTPS GET fetched the same object in
31 s; the job should use the Python client or plain GETs, not the CLI.

## Outputs, per stream
Every table is keyed by `bucket_start` (UTC, 1 s or 1 min) and carries
`n_msgs`, `time_source` ("event" or "receive") and `rt_lag_ms_p50` so the
127 ms collector lag stays visible downstream. Polymarket tables add
`market` and `asset_id`.

| stream | features |
|---|---|
| `binance_{fut,spot}@bookTicker` | last/mean/time-weighted mid, microprice `(a·B + b·A)/(A+B)`, spread_bps, best bid/ask and sizes, imbalance `(B−A)/(B+A)`, updates count |
| `binance_fut@depth20@100ms` | mid, microprice, depth in $ at 1/5/10/20 levels per side, imbalance at L1/L5/L20, book slope, spread_bps |
| `binance_{fut,spot}@trade` | signed volume (aggressor from `m`), buy/sell volume and counts, VWAP, last price, max trade size |
| `chainlink__btc` | dedup by `round_id`: answer/1e8, `updated_at`, staleness at bucket end, rpc round-trip |
| `polymarket__price_change` | per asset: last best_bid/best_ask, mid, spread, change count, BUY/SELL size sums |
| `polymarket__book` | per asset: top of book, size at the top level, depth within 1c/5c of touch, total size, level count |
| `polymarket__last_trade_price` | per asset: last price, traded size, count, signed size |
| `polymarket__markets` | normalised metadata table (id, conditionId, slug, clobTokenIds, outcomes, start/end, tick size, min size) |
| `polymarket__tick_size_change`, `collector_log` | pass-through normalised (tiny) |

**Time keys, per SCHEMAS.md:** Binance streams and Polymarket
`price_change` / `last_trade_price` bucket on the payload's own event time;
`binance_spot@bookTicker` and `polymarket__book` have no payload timestamp
and must bucket on `rt_ns` (flagged in `time_source`).

### Expected output size
Measured: the futures bookTicker hour reduced to 3,601 one-second rows =
**0.19 MB/hour**; a price_change sample reduced to ~0.27 MB/hour across 14
assets.

| stream | 1s MB/day | 58-day total |
|---|---:|---:|
| binance_fut@bookTicker | 4.6 | 265 MB |
| binance_spot@bookTicker | ~3.6 | ~210 MB |
| binance_fut@depth20 | ~4.8 | ~280 MB |
| trades (fut + spot) | ~7 | ~410 MB |
| polymarket__price_change | ~6.5 | ~375 MB |
| polymarket__book | ~7 | ~400 MB |
| polymarket__last_trade_price | ~1.2 | ~70 MB |
| chainlink + metadata | <0.5 | ~30 MB |
| 1m tables (all streams) | ~0.5 | ~30 MB |
| **total** | **~36 MB/day** | **~2.1 GB** |

That is a **~125× reduction**, small enough to pull the whole feature set to
a laptop.

## Plan of record
1. **1-day pilot** on 2026-09-10 (all 12 streams, 288 units) on the
   recommended VM: confirms the core-hour estimate, the output sizes, and
   the schemas. Cost ~$1, ~10 minutes.
2. Check the pilot outputs against the raw hour files already in /tmp
   (row counts, a hand-checked bucket or two), then run the remaining
   57 days.
3. Delete the VM. Outputs stay in `features/v1/`.

Nothing here is run until you approve. The only open choices I would flag:
**(a)** whether 1 s is fine as the finest grid (the depth20 stream is
100 ms, so a 100 ms option exists at ~10× the output size, ~2.8 GB for that
stream alone), and **(b)** whether to also emit an event-level normalised
parquet for the two Binance trade streams (~2 GB total, no aggregation),
which would let later work re-bucket without re-reading the raw JSON.
