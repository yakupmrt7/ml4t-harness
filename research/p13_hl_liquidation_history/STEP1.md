# p13 step 1 — the liquidation event set (no price outcomes read)

Source: `node_fills_by_block`, full fixed span 2025-07-27 08:00 → 2026-09-25 08:00 UTC (14.0 months),
reduced on arbscan-tokyo by `extract.py` (426/426 days `ok`, `extract_run.log`), analysed by
`events.py` (`step1.log`, `step1.json`). Outputs in `data/hl/p13_fills/` (gitignored).

## Validation (ROADMAP §8.6, `validate.py`)
- **Liquidations vs API:** 25 random liquidated users (2026-09-23/24), `userFillsByTime`: **187/187**
  liquidation rows match on tid, px, sz, side, coin, time and method; 0 missing.
- **Trade tape vs API:** BTC 1-minute bars from our ticks vs `candleSnapshot`, 3,372 minutes: trade
  count equal in 100%, volume median relative error 0, close equal in 92.7%. **All** close mismatches
  are same-millisecond ties (the API close is one of the prices in the last ms): `tid` is not
  execution order. Step 2 must keep the archive's block order within a millisecond.

## Definitions (PLAN.md), and one correction made before any outcome was read
- Event = one liquidation order: the liquidated user's rows, merged on (coin, liq_user, oid).
- **Correction:** the liquidator vaults (HLP children, e.g. `0xb0a55f…`, `0x2e3d94…`) appear as the
  "liquidated user" on `backstop` rows, including their own auto-deleveraging on 2025-10-10.
  Backstop liquidations transfer the position to the vault **without trading in the book**, so they
  are not forced flow. **Primary set = `market` liquidations**; backstop reported apart:
  23,628 events, $3.69B. (A filter on `dir == "Auto-Deleveraging"` found 0 rows on the liquidated side.)

## Events (market method)
1,395,165 liquidation orders, $35.3B notional. Per coin:

| coin | events | /week | liquidated notional p50 / p90 / p99 / max ($) | longs liquidated | in cascades (60 s) |
|---|---:|---:|---|---:|---:|
| BTC | 709,368 | 11,684 | 830 / 27,096 / 319,902 / 97.1M | 63% | 99% |
| ETH | 240,166 | 3,956 | 805 / 35,116 / 591,514 / 96.2M | 70% | 98% |
| SOL | 208,582 | 3,435 | 514 / 15,340 / 176,856 / 29.0M | 72% | 98% |
| HYPE | 99,232 | 1,634 | 540 / 27,358 / 204,211 / 11.0M | 75% | 95% |
| ZEC | 69,224 | 1,140 (listed 2025-10-02) | 378 / 14,371 / 163,282 / 17.2M | 55% | 96% |
| XRP | 68,593 | 1,130 | 480 / 11,575 / 132,459 / 22.5M | 78% | 96% |

Market-wide cross-check: BTC liquidations median $21.5M/day, max $2.2B on 2025-10-10.

## Independent events (clusters merged across the six coins)

| gap | clusters | per month | median full month | min full month | dev | holdout |
|---|---:|---:|---:|---:|---:|---:|
| 10 s | 67,894 | 4,862 | 4,259 | 3,052 | 53,662 | 14,232 |
| **60 s (kill)** | **31,541** | **2,259** | 2,048 | 1,595 | 24,927 | 6,614 |
| 300 s | 14,738 | 1,056 | 1,023 | 824 | 11,615 | 3,123 |

Cluster shape (60 s): median 6 events, p90 94, max 19,513 (2025-10-10); 40% span more than one
coin; duration median 15 s, p90 122 s. Not concentrated in a few days: clusters on all 426 days, the
top 10 days hold 6% of them, effective number of equally weighted days 339.

**Most clusters are tiny.** The median liquidation is ~$800, which cannot move a book. Counting only
clusters large enough to matter (descriptive, not part of the pre-registered kill):

| cluster notional ≥ | clusters | per month | dev | holdout | days |
|---|---:|---:|---:|---:|---:|
| $100k | 11,248 | 806 | 9,071 | 2,177 | 422 |
| $1M | 3,854 | 276 | 3,190 | 664 | 397 |
| $10M | 652 | 47 | 569 | 83 | 232 |

## Kill 1 (power): **passes**
2,259 independent events/month at the 60 s gap vs the pre-registered ~200. It would still pass on
clusters ≥ $1M (276/month); it would not on clusters ≥ $10M (47/month). Kill 2 (economics) is step 2.
