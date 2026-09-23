# p08 validation: is the collector's data complete and clean?

Cross-check of the collector's `binance_fut btcusdt@trade` stream for
**2026-09-10** against Binance's own public record (daily aggTrades from
data.binance.vision). The archive aggregates consecutive trades at one
price/side/ms and carries `first_trade_id`..`last_trade_id`, so its
individual trade ids are the union of those ranges. That makes the check
exact, not statistical.

Run: `~/venv/bin/python validate_archive.py --date 2026-09-10`
(`validate_archive.json` holds the full output, per hour.)

## Headline: the collector dropped nothing
| | archive | collector |
|---|---:|---:|
| individual trades | 3,107,022 | 3,120,537 |
| aggTrades rows | 1,175,077 | — |
| volume (BTC) | 142,694.888 | 142,694.988 |
| **archive trades missing from the collector** | | **0** |
| **match rate** | | **1.000** |
| gap episodes | | **0** |
| duplicate rows in the collector | | 0 |

Every hour matches: per-hour volume agrees to 0.0013% or better, and the
whole day agrees to 7e-5%. There is no hour, and no run of trade ids, that
the collector missed. For 58 days of websocket capture from a small VM,
that is a clean result: whatever we build on this data is not fighting
silent message loss.

## The collector holds 13,515 records the archive does not
Not a discrepancy in the collector's favour so much as a quirk of the
futures feed:

| | count |
|---|---:|
| extra ids of type `NA` | 13,514 |
| extra ids of type `MARKET` | 1 |

- **`NA` prints are zero-price, zero-quantity records** (738 of them in
  hour 12; price 0.00 and qty 0.000 in every one). Binance's futures
  `@trade` stream emits them; the public aggTrades archive leaves almost
  all of them out. They carry no volume, which is why the day's volume
  still matches to 7e-5%.
- The **one extra `MARKET` trade** is 0.1 BTC and accounts for the entire
  +0.100 BTC volume difference. Most likely a day-boundary artefact
  between the collector's event-time cut and the archive's.
- 840 `NA` ids do appear "matched". That is an artefact of my method: an
  `NA` print whose id falls inside an aggTrade's
  `first_trade_id`..`last_trade_id` range is counted as present, since the
  range is expanded as a contiguous block.

## The bug this check caught
Those zero-price prints were **corrupting the 1-second trade features**.
They were included in the aggregates, so:
- `px_min` was 0.00 in any bucket containing one — up to ~700 of 3,592
  buckets in a single hour (19%);
- `px_last` would have been 0.00 whenever such a print landed last in a
  bucket.

Downstream, a zero mid or a zero low would have wrecked any feature built
on trade prices, and nothing in the pipeline would have complained.

**Fix (code version `p08-v4`):** prints with price ≤ 0 or qty ≤ 0 never
enter the 1s/1m aggregates. They are retained in the **event-level** table,
tagged by the new `trade_type` column, so nothing is lost and the filter
stays auditable. Each aggregate row carries `n_zero_prints`, the count
excluded from that bucket.

After the fix, on hour 12: 0 buckets with `px_min = 0`, 0 with
`px_last = 0`, `px_min` ranging 76,634.30–77,870.70, and 737 zero prints
accounted for in `n_zero_prints`. The 738th sits in a second that contained
*only* a zero print, so that second has no trade row at all — correct, since
no trade happened.

Spot is unaffected: `binance_spot@trade` has no zero-price or zero-qty rows.

## What this does and does not cover
- It covers one stream on one day. The futures trade stream is the only one
  with an independent public record to check against; bookTicker, depth20
  and the Polymarket streams have no equivalent archive.
- The 58-day run reprocesses every day with the same code, but the
  archive comparison itself has only been run for 2026-09-10. Running it
  across all 58 days is cheap (one archive file per day) and is the obvious
  next validation if this data is going to carry real weight.
- Message-level completeness says nothing about *timing* accuracy. The
  collector sits a median 127 ms behind Binance event time (SCHEMAS.md),
  and two streams have no payload timestamp at all.
