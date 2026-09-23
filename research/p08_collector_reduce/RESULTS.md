# p08 collector reduction: 261 GB of raw JSON → queryable feature tables

Infrastructure, not research. No model, no trial in `trials.json`, no OOS
gate. The point is to make the collector data usable from a laptop, and to
find out whether it can be trusted.

- **Step 1** (schemas, sizes, timing): `SCHEMAS.md`
- **Step 2** (the proposal that was approved): `REDUCTION_PROPOSAL.md`
- **Validation** against Binance's public record: `VALIDATION.md`
- Code: `reduce.py` (the job), `validate_archive.py` (the cross-check)

## The run (actuals)
| | |
|---|---|
| units | 16,704 attempted; **16,150 processed, 0 errors**, 387 source hours absent, 167 already current |
| wall time | **102.7 min** on one `c3-highcpu-22`, 10 workers |
| input | 261 GB of JSON-in-parquet |
| output | **6.75 GB** — 1s 3.12 GB, events 3.36 GB, 1m 240 MB, meta 35 MB |
| rows | 75.7 M one-second, 2.4 M one-minute, **328.0 M trade prints**, 189 k metadata |

That is a **39× reduction**, more than the ~125× I projected: event-level
trades (your choice (b)) are half the output, and the 1s tables came out
larger than estimated because the Polymarket tables carry a row per
(second, asset) rather than one per second.

## What now exists
`gs://poly-backup-54cb99b7/features/v1/`

| kind | path | content |
|---|---|---|
| 1-second | `1s/<stream>/date=YYYY-MM-DD/<stream>__<HH>.parquet` | per-second features, all 12 streams |
| 1-minute | `1m/…` | the same features per minute |
| event-level | `events/<stream>/…` | every Binance trade print (futures and spot), unaggregated |
| metadata | `meta/<stream>/…` | Polymarket markets, tick-size changes, collector log |
| manifests | `_manifest/<stream>/date=…/<HH>.json` | per unit: input generation/size/crc32c, output row counts, parse errors, receive-lag percentiles, runtime |

Read it with any parquet reader, e.g.

```bash
python -c "import pyarrow.dataset as ds; print(ds.dataset('gs://poly-backup-54cb99b7/features/v1/1s/binance_fut__btcusdt@bookTicker', format='parquet').to_table().num_rows)"
```

Every table carries `bucket_start` (UTC), `n_msgs`, and `time_source`
("event" where the payload has its own timestamp, "receive" where it does
not). Polymarket tables are additionally keyed by `market` and `asset_id`.

## Validation: the collector lost nothing, but the feed has junk prints
Full detail in `VALIDATION.md`. On the pilot day, against Binance's own
aggTrades archive:

- **0 of 3,107,022 archive trades missing**, match rate 1.000, no gap
  episodes, volume agreeing to 7e-5%.
- The collector holds **13,515 records the archive lacks**: 13,514
  zero-price, zero-quantity `NA` prints that the futures websocket emits and
  the archive omits, plus one real 0.1 BTC trade (a day-boundary artefact).
- **Those zero prints were corrupting the features.** Included in the
  aggregates they set `px_min = 0` in up to ~19% of one-second buckets, and
  could set `px_last = 0`. Fixed in code version `p08-v4`: prints with
  price ≤ 0 or qty ≤ 0 are excluded from 1s/1m aggregates, kept in the
  event tables tagged by `trade_type`, and counted per bucket in
  `n_zero_prints`.

This is the reason the validation step was worth doing before building
anything on the data.

## Coverage gaps in the raw data (`check_outputs.py`)
387 stream-hours are absent from the **source**; the reduction wrote
everything that exists. They are not scattered — they are three episodes:

| when | missing | what it looks like |
|---|---|---|
| 2026-07-25 h00–17 | 18 h, every stream | the collector simply started at 18:00 UTC that day |
| 2026-07-26 h01, h03, h04 | 3 h, every stream | short restarts |
| **2026-08-04 h16–23** | 8 h, every stream | a contiguous half-day outage |

Plus sparse streams that only get a file when something happens
(`tick_size_change` 48 h, `last_trade_price` 40 h absent, on scattered days).

So the usable span is **57 days and 19 hours**, with one 8-hour hole on
2026-08-04. Research on this data should check manifest presence per hour
rather than assuming 24 hours a day.

There is also a 13th stream in the bucket that nothing documented:
`binance_spot__!serverShutdown`, which exists exactly once
(2026-09-08 05:00) — Binance's shutdown notice on the spot socket. It is
not reduced; it is an operational marker worth knowing about.

## Verification of the zero-price fix, all 58 days
| stream | 1s rows | `px_last` ≤ 0 | `px_min` ≤ 0 | junk prints excluded |
|---|---:|---:|---:|---:|
| binance_fut@trade | 4,548,737 | **0** | **0** | 577,935 |
| binance_spot@trade | 4,203,133 | **0** | **0** | 0 |

168.9 M futures and 162.4 M spot trades are aggregated across the period.

## Cost and runtime (actual)
| | |
|---|---|
| VM | `c3-highcpu-22`, us-central1-a, on-demand (spot quota is 0 on this project) |
| Pilot day | 288 units in 2.3 min |
| Full 58 days | 102.7 min, 16,150 units, 0 errors |
| Reads | US multi-region bucket → same-continent VM: no egress charge |
| VM cost | ~$0.77/hr |

Workers are capped at 10, not 22: a `polymarket__price_change` hour peaks at
~2.3 GB and workers are never recycled.

## What broke, and what it cost
Worth recording, because most of the elapsed time went here rather than
into compute:

1. **OOM.** The first version accumulated parsed JSON dicts for a whole
   file; a 2.6M-row Polymarket hour reached 4.7 GB RSS and the kernel killed
   the worker. Fixed by converting each row group to column arrays and
   dropping the dicts (peak ~2.3 GB, and ~2× faster).
2. **Pool deadlock.** `ProcessPoolExecutor(max_tasks_per_child=20)` hung the
   parent in `futex_wait` with zero workers once recycling began. Removed;
   memory is bounded by the worker cap instead.
3. **Chainlink `round_id` overflow.** A 20-digit id does not fit int64;
   dedupe by string.
4. **Fake receive lag.** Streams without a payload timestamp were getting a
   "lag" measured against their own receive time. They now record
   `lag_measurable: false` and null lags.
5. **404 on absent hours** raised instead of being reported as missing.
6. **Self-inflicted:** `pkill -f reduce.py` also matched the SSH session
   carrying that command, so it killed its own workers and left a deadlocked
   parent — twice. Kill by PID, or with a pattern that cannot match the
   launching command.
7. **Transfer corruption (local).** A stalled `gcloud storage cp` produced a
   byte-complete file that failed ZSTD decompression on a later row group;
   the footer and first row group read fine. A plain authenticated HTTPS GET
   fetched the same object in 31 s. The job verifies CRC32C on every
   download for this reason.

## What this does not do
- No 100 ms tables (the owner chose 1 s as the finest grid); the depth20
  stream is natively 100 ms, so that option remains open at ~10× the size.
- No event-level bookTicker (75 M rows/day was judged too big).
- The archive cross-check has been run for one day only. Extending it to all
  58 days is one archive file per day and is the obvious next check.
- Nothing here says the data contains an edge. It says the data is complete,
  the timing is documented, and the junk prints are quarantined.
