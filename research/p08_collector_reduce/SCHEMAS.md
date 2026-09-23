# p08 step 1: collector raw schemas (gs://poly-backup-54cb99b7/eu-raw_pq)

Inspected 2026-09-23 from **one hour file per stream**, `2026-09-10` hour 12
UTC (~250 MB downloaded to /tmp, well under the 1 GB cap). The bucket was
touched **read-only**: `ls`, `du`, `objects describe` and `cp` to /tmp.

Bucket: `poly-backup-54cb99b7`, location **US multi-region**, standard class.
Other top-level prefixes exist and are out of scope here: `us-raw_pq/`,
`fairprice/`, `research/`.

Layout: `eu-raw_pq/<YYYY-MM-DD>/<source>__<stream>__<HH>.parquet`, one file
per stream-hour, **58 days** 2026-07-25 → 2026-09-20, 12 streams, 288 files
per day.

## Every stream has the same three columns
| column | type | meaning |
|---|---|---|
| `rt_ns` | int64 | collector **receive** time, wall clock, ns since epoch |
| `mono_ns` | int64 | collector monotonic clock, ns (for gap/ordering checks within a process run; not wall time) |
| `data` | string | the **raw JSON payload**, unparsed |

So all the structure lives in a JSON string: any reduction is a JSON parse
job first. Files are ZSTD-compressed parquet, 1–158 row groups each.

**Timing.** `rt_ns` is not exchange time. Against the Binance payload event
time `E`/`T`, the collector (europe-west3) sits at a **median 127 ms
behind**, p95 136–157 ms, p99 up to 1.5 s on depth20:

| stream | lag p50 | p95 | p99 | min |
|---|---:|---:|---:|---:|
| binance_fut @trade | 128.5 ms | 156.8 | 199.0 | 125.2 |
| binance_spot @trade | 132.8 ms | 150.9 | 167.3 | 125.9 |
| binance_fut @depth20@100ms | 126.7 ms | 135.8 | 1487.3 | 125.8 |

Features must therefore key off the payload's own event time where one
exists, and `rt_ns` only where none does (see the per-stream table).

## Volume: one day (2026-09-10), 4.87 GB total
Rows/hour are measured on hour 12; rows/day scale that by 24.

| stream | GB/day | MB/hour | rows/hour | rows/day (est) | payload event time? |
|---|---:|---:|---:|---:|---|
| `polymarket__price_change` | 3.746 | 156.1 | 2,613,174 | 62.7 M | yes, `timestamp` ms |
| `binance_fut__btcusdt@bookTicker` | 0.625 | 26.0 | 3,154,619 | 75.7 M | yes, `E` and `T` ms |
| `binance_spot__btcusdt@bookTicker` | 0.160 | 6.6 | 975,518 | 23.4 M | **no** — `rt_ns` only |
| `polymarket__book` | 0.154 | 6.4 | 59,732 | 1.4 M | **no** — `rt_ns` only |
| `binance_fut__btcusdt@depth20@100ms` | 0.061 | 2.5 | 34,933 | 0.8 M | yes, `E`/`T` ms |
| `binance_fut__btcusdt@trade` | 0.052 | 2.2 | 484,793 | 11.6 M | yes, `E`/`T` ms |
| `binance_spot__btcusdt@trade` | 0.046 | 1.9 | 392,143 | 9.4 M | yes, `E`/`T` ms |
| `polymarket__last_trade_price` | 0.032 | 1.3 | 28,015 | 0.7 M | yes, `timestamp` ms |
| `polymarket__tick_size_change` | ~0 | 0.005 | 64 | 1.5 k | yes, `timestamp` ms |
| `polymarket__markets` | ~0 | 0.009 | 16 | 384 | dates as ISO strings |
| `collector_log` | ~0 | 0.003 | 66 | 1.6 k | `rt_ns` only |
| `chainlink__btc` | ~0 | 0.010 | 315 | 7.6 k | yes, `updated_at` s |

**Two streams are 90% of the bytes**: `polymarket__price_change` (77%) and
`binance_fut@bookTicker` (13%). About **186 M rows/day**, ~10.8 G rows over
58 days.

## Payloads, per stream

### binance_fut / binance_spot `@bookTicker`
Futures (`{"stream":..., "data":{...}}`):
```json
{"e":"bookTicker","u":11522383822432,"s":"BTCUSDT","ps":"BTCUSDT",
 "b":"77817.40","B":"34.502","a":"77817.50","A":"24.782",
 "T":1789041599917,"E":1789041599917,"st":1}
```
Spot has **fewer fields and no timestamps**: `{"u","s","b","B","a","A"}`
only. Prices and sizes are strings. b/B = best bid and its size, a/A = best
ask and its size.

### binance_fut `@depth20@100ms`
```json
{"e":"depthUpdate","E":1789041599975,"T":1789041599974,"s":"BTCUSDT",
 "U":…, "u":…, "pu":…,
 "b":[["77817.40","33.264"], …20 levels…],
 "a":[["77817.50","25.749"], …20 levels…]}
```
Top-20 snapshot both sides every 100 ms, prices/sizes as strings. This is
the only order-book depth in the dataset (spot has no depth stream).

### binance_fut / binance_spot `@trade`
```json
{"e":"trade","E":1789041599937,"T":1789041599937,"s":"BTCUSDT",
 "t":8066025793,"p":"77817.40","q":"0.001","X":"MARKET","m":true,"st":1}
```
`m: true` means the buyer was the maker, i.e. **the aggressor sold**. Spot
carries `M` instead of `X`/`st`.

### chainlink__btc (the Polymarket resolution source)
```json
{"round_id":"55340232221132493785","answer":7782774700000,
 "updated_at":1789041594,"started_at":1789041590,
 "rpc":"https://polygon-bor-rpc.publicnode.com","rtt_ms":26.6}
```
`answer / 1e8` = USD (77,827.75). 315 rows/hour, but only **112 distinct
rounds**: the collector polls (median 33 s between round updates) and
repeats unchanged rounds. Median gap from `updated_at` to `rt_ns` is
**16.3 s**, so the on-chain feed is far behind the exchange streams.
Dedupe on `round_id` and use `updated_at`.

### polymarket__book (full snapshot)
```json
{"market":"0x30dc…","asset_id":"195052…",
 "bids":[{"price":"0.01","size":"102542.9"}, …],
 "asks":[{"price":"0.99","size":"…"}, …]}
```
A whole ladder per message: median **99 price levels**, max 123. 20 markets
and 40 asset_ids in the sample hour (2 outcome tokens per market).
**No timestamp in the payload** — `rt_ns` is the only clock.

### polymarket__price_change (the heavy one)
```json
{"market":"0xf3c2…","event_type":"price_change","timestamp":"1789041600000",
 "price_changes":[
   {"asset_id":"677021…","price":"0.52","size":"65","side":"BUY",
    "hash":"2100bd7e…","best_bid":"0.99","best_ask":"1"},
   {"asset_id":"387865…","price":"0.48","size":"65","side":"SELL",
    "hash":"23c2c868…","best_bid":"0","best_ask":"0.01"}]}
```
Median 2 changes per message, 596 bytes/row. **Each change carries
`best_bid`/`best_ask`**, so a top-of-book series can be built from this
stream alone, without replaying `book` snapshots. Has its own `timestamp`
(ms).

### polymarket__last_trade_price
```json
{"market":"0x30dc…","asset_id":"195052…","price":"0.41","size":"7.380953",
 "fee_rate_bps":"0","side":"BUY","timestamp":"1789041600041",
 "event_type":"last_trade_price","transaction_hash":"0xda92…"}
```

### polymarket__markets (metadata, 16 rows/hour)
~70 fields. The useful ones: `id`, `conditionId`, `slug`, `question`,
`clobTokenIds`, `outcomes`, `outcomePrices`, `startDate`, `endDate`,
`orderPriceMinTickSize`, `orderMinSize`, `bestBid`, `bestAsk`, `spread`,
`liquidity`, `active`, `closed`, `resolutionSource`.

**What these markets are:** 5-minute BTC up/down contracts, e.g. slug
`btc-updown-5m-1789041900`, "Bitcoin Up or Down - September 10,
8:05AM-8:10AM ET". They resolve on the **Chainlink BTC/USD 60s TWAP**
(`data.chain.link/streams/btc-usd-twap-60s-streams`), up if the TWAP at the
end ≥ the TWAP at the start. The collector records that same Chainlink feed,
which is what makes this dataset self-contained for pricing them.

### polymarket__tick_size_change
```json
{"market":"0xf3c2…","asset_id":"387865…","old_tick_size":"0.01",
 "new_tick_size":"0.001","timestamp":"1789041622268","event_type":"tick_size_change"}
```
Tick changes matter for cost work: the tick is the spread floor, as p05
showed on Binance.

### collector_log
```json
{"source":"tracker","event":"market_added","slug":"btc-updown-5m-1789041900","n_tokens":2}
```
Operational events (`market_added`, `token_set_changed`, …). Useful for
knowing when a market entered the collector's subscription set, i.e. when
absence of data means "not subscribed" rather than "no activity".

## Measured processing rates (this laptop, 1 core, orjson)
End-to-end on `binance_fut@bookTicker`, one hour: read 0.3 s, JSON parse
16.3 s, aggregate 0.7 s → **17.2 s for 3.15 M rows (183 k rows/s)**, giving
3,601 one-second rows at **0.19 MB/hour** output.

Parse-only, by payload shape: trade 207 k rows/s, price_change (pending),
polymarket book 17 k rows/s (59 MB/s, big ladders), depth20 11.8 k rows/s
(12 MB/s). **JSON parsing is ~95% of the work**; parquet read and the
aggregation itself are noise.

## Data-integrity warning (hit during this step)
A `gcloud storage cp` of `polymarket__price_change__12.parquet` stalled, was
auto-resumed, and produced a file of **exactly the right byte count that
failed ZSTD decompression on a later row group**. Reading the footer and the
first row group did not catch it. Any job must validate a whole object
(read every row group, or check CRC32C against the object metadata) before
trusting it, and must not treat "right size" as "intact".
