# p13 step 0 — archive span, size and cost (no bulk download)

Listed 2026-09-25 with `aws s3 ls --recursive --summarize --request-payer requester`. Samples
downloaded (≈35 MB, ≈$0.003) into `data/raw/hl_sample/` (gitignored): one hour of fills
(2026-09-20 10:00), BTC l2Book for 2026-04-01 10:00 and 2026-09-20 10:00, asset_ctxs for 2026-09-23.

## Fills: `s3://hl-mainnet-node-data/node_fills_by_block/hourly/<YYYYMMDD>/<H>.lz4` (ap-northeast-1)
- Span **2025-07-27 08:00 → 2026-09-25 08:00 UTC, 425 days**, 10,200 hourly files, no missing days
  (first and last day partial). Older formats (`node_fills`, `node_trades`) not examined.
- **290.5 GB** compressed; 0.66 GB/day median (max 1.60). lz4 ratio ≈ 4.8× → ~1.4 TB of JSON.
- Format (verified): one JSON line per block `{local_time, block_time, block_number, events:[[user,
  fill], …]}`; each fill has the API fill fields plus, on liquidations,
  **`liquidation: {liquidatedUser, markPx, method}`**, present on **both** counterparties' rows.
  The sample hour had 320,460 fill rows, 100 carrying `liquidation` (50 trades × 2 sides; all
  `method: market`; AAVE, MORPHO, SUI, DOGE, VVV and a builder-dex market, none of the six coins).
  `time` is ms epoch UTC. Builder-deployed (HIP-3) markets appear with a `dex:` prefix (`xyz:`, `para:`).

## Book and contexts: `s3://hyperliquid-archive/` (us-east-1)
- `market_data/<YYYYMMDD>/<H>/l2Book/<COIN>.lz4`: 2023-04-15 → 2026-09-24. One JSON line per
  snapshot, the websocket `l2Book` message (20 levels/side) with a recorder timestamp.
  **Cadence changes over the span (measured on BTC hour 10):** ~0.54 s median gap from
  **2025-09 to 2026-06** (6,579 snapshots/hour on 2026-04-01), but ~5.4 s on 2025-07-27 and **from
  2026-07 on** (671/hour on 2026-09-20), matching p12's live measurement. The hour
  2026-07-15 10:00 is missing. So the dev span (below) mostly has 0.5 s books; the holdout has 5 s books.
- Six coins' l2Book ≈ 165–190 MB/day (BTC alone ~30 MB/day at 0.5 s cadence, ~5 MB at 5 s).
- `asset_ctxs/<YYYYMMDD>.csv.lz4`: ~4.5 MB/day, columns `time, coin, funding, open_interest,
  prev_day_px, day_ntl_vlm, premium, oracle_px, mark_px, mid_px, impact_bid_px, impact_ask_px`.
  **Only ~547 rows/day per coin (one per ~2.6 min)**: too coarse for the seconds-scale mark/oracle
  dislocation in step 2. Use Binance (free public archive, or our collector from 2026-07-25) as the
  external reference instead, and state that it approximates the 5-venue mark median.

## Cost (S3 → internet egress; requester pays. ap-northeast-1 $0.114/GB, us-east-1 $0.09/GB,
list prices; request charges negligible; AWS's 100 GB/month free egress may apply to the payer
account, not relied on)

| pull | GB | est. $ |
|---|---:|---:|
| (a) 3 months of fills (range over three windows: 2025-10→12, 2025-07→10, 2026-06→09) | 52–79 | **$5.9–9.0** |
| (b) BTC l2Book, 3 months at 0.5 s cadence | ~2.7 | $0.25 |
| (b) BTC asset_ctxs, 3 months (all coins in one file) | ~0.4 | $0.04 |
| six coins' l2Book, 3 months | ~15 | $1.4 |
| **full fills span, 425 days** | 290.5 | **$33.1** |
| six coins' l2Book, full dev span (~318 days) | ~55 | $5.0 |

Alternative for the full span without egress: stream-filter inside AWS ap-northeast-1 (same-region
S3 reads are free) on a small EC2 instance, and download only the liquidation rows and the address
set (MBs). A few $ of compute, but it means running infrastructure in the owner's AWS account.

Local processing: fills can be streamed (`aws s3 cp - | lz4 -dc | filter`) without storing the
1.4 TB of JSON; the bottleneck is download bandwidth (290 GB ≈ 6.5 h at 100 Mbit/s).

## Dev / holdout split (fixed now, before loading any fills)
Dev = 2025-07-27 08:00 → 2026-06-11 02:00 UTC; holdout = 2026-06-11 02:00 → 2026-09-25 08:00 UTC.
