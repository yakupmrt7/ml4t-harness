# p12 — Hyperliquid public API survey (stage 0)

Survey only: no collector, no trading logic, no trial (nothing in `trials_hl.json`).
Every number marked **measured** comes from the live public API with the scripts in this folder.
Every number marked **documented** comes from the official docs and was not independently verified.

Measurement windows: top-3000 poll and websocket rates 2026-09-24 19:34–19:52 UTC (Thursday evening,
a quiet market: BTC ~2.9 trades/s); tail sample, sub-accounts and l2Book cadence 2026-09-25 ~07:45–07:58
UTC. Coverage shares from the two days are added below; BTC OI moved +1.7% between them, so the
sum is of two snapshots, not one. OI is taken as one-sided (longs = shorts = `openInterest`); that
is an inference, supported by longs ≈ shorts in the top-3000 sample (32.8% vs 31.7% of OI).

Reproducibility: `probe.py` re-runs the measurements that were first taken ad hoc (universe table,
leaderboard row count and tail-sample draw, trades-stream/leaderboard overlap, l2Book cadence,
tail bootstrap); `probe.log` is its re-run on 2026-09-25. Limit: the tail sample depends on that
day's leaderboard and the address files are gitignored, so it cannot be redrawn from the repo alone (ranks 1–7 of the universe unchanged,
8–10 moved; l2Book gap median 5.39 s again). The HLP check reused the tail-sample run
(`addrs_tail_sample.json`, first 8 addresses).

Scripts: `coverage.py` (polls `clearinghouseState` for a list of addresses),
`analyse_coverage.py`, `ws_rates.py` (in-memory message counts), `subaccounts.py`, `probe.py`.
Raw per-address files (`coverage_*.json`, `addrs_*.json`) are kept locally and gitignored (lists of
addresses and positions; public, but not something the repo needs).

---

## 1. Market data

All REST calls are `POST https://api.hyperliquid.xyz/info` with a JSON body `{"type": ...}`.
Websocket: `wss://api.hyperliquid.xyz/ws`, `{"method":"subscribe","subscription":{...}}`.

| data | REST (`type`) | websocket | shape (measured) | notes |
|---|---|---|---|---|
| book | `l2Book` `{coin, nSigFigs?, mantissa?}` | `l2Book` | `{coin, time, levels:[[{px,sz,n}×20],[…×20]]}` | **Max 20 levels/side.** `nSigFigs` aggregates coarser (BTC `nSigFigs=2` → $1000 buckets, ±20 buckets). WS is a **snapshot**, not deltas. Docs say "each block ≥0.5 s since last push"; **measured median gap 5.4 s** (p10 5.0, p90 5.5, BTC alone, 60 s) |
| top of book | — | `bbo` | `{coin, time, bbo:[{px,sz,n},{px,sz,n}]}` | measured 5–7 msg/s per coin; the only fast book stream |
| trades | `recentTrades` `{coin}` (last 10) | `trades` | `{coin, side, px, sz, time, hash, tid, users:[buyer, seller]}` | **both counterparty addresses are public on every print**. No liquidation flag |
| candles | `candleSnapshot` `{req:{coin, interval, startTime, endTime}}` | `candle` | `{t,T,s,i,o,c,h,l,v,n}` | most recent **5000 candles only** (1m ≈ 3.5 days) |
| mids | `allMids` | `allMids` | `{coin: mid}`, 1103 keys (perps + spot + builder dexes) | WS measured 0.2 msg/s, 19 kB each |
| asset ctx | `metaAndAssetCtxs` | `activeAssetCtx` `{coin}` | `{funding, openInterest, prevDayPx, dayNtlVlm, premium, oraclePx, markPx, midPx, impactPxs, dayBaseVlm}` | WS measured ~1 msg/s per coin. Oracle and mark update ~every 3 s (documented) |
| predicted funding | `predictedFundings` | — | per coin: HL, Binance, Bybit rate + next time | HL funds **hourly** |

**Rate limits (documented).** REST: 1200 weight/min per IP. Weight 2: `l2Book`, `allMids`,
`clearinghouseState`, `orderStatus`, `spotClearinghouseState`, `exchangeStatus`; weight 20: every
other info type; fills/history types add weight per 20 items returned; explorer 40. Websocket per IP:
10 connections, 30 new connections/min, 1000 subscriptions, **10 unique users across user-specific
subscriptions**, 2000 outbound messages/min.

**History (documented, not downloaded).** Requester-pays S3: `s3://hyperliquid-archive/market_data/<date>/<hour>/l2Book/<coin>.lz4` and `asset_ctxs` (updated ~monthly, "may be missing");
`s3://hl-mainnet-node-data/` with `node_fills_by_block` (fills in API format, incl. the liquidation
field), `explorer_blocks`, `replica_cmds` (all L1 transactions), `misc_events_by_block`. No candles.
Transfer cost not measured.

Market microstructure note for the event study: liquidations trigger on the **mark price**, not the
last trade. Mark = median of (oracle + 150 s EMA of HL mid − oracle), (median of HL bid/ask/last),
(weighted median of Binance/OKX/Bybit/Gate/MEXC perp mids). So a cascade on HL needs the *external*
venues to move too; HL's own book alone can move mark only through one of three median inputs.

---

## 2. Position and liquidation data (the decisive part)

### 2a. Per-address position state — **public, with liquidation price**
`clearinghouseState {user}` (weight 2) returns `assetPositions[].position = {coin, szi, entryPx,
leverage:{type: cross|isolated, value}, liquidationPx, marginUsed, positionValue, unrealizedPnl,
returnOnEquity, maxLeverage, cumFunding}` plus `marginSummary`, `crossMaintenanceMarginUsed`.
Measured: `liquidationPx` is non-null for **95% of BTC position size** and 87–95% for the other coins
in the top-3000 sample (null = far-away or not computable). Cross margin dominates (87–98% of size),
which matters: a cross position's liquidation price moves when *any* other position in that account
moves, so the map must be refreshed, not computed once from entry and leverage.
Websocket equivalent (`clearinghouseState`/`webData3` per user) is capped at 10 users/IP, so polling
is the only way to scale. **Going forward only:** there is no historical endpoint for past position
state; reconstruction needs `replica_cmds` or node state snapshots (below).

### 2b. Enumerating who holds the open interest — **the binding constraint**
There is no endpoint listing all accounts or all positions. Sources of addresses, measured:

| source | what it is | share of BTC OI held (gross, (|long|+|short|)/(2·OI)) |
|---|---|---|
| leaderboard top 3000 by account value (`GET https://stats-data.hyperliquid.xyz/Mainnet/leaderboard`, 39 MB, 46,797 rows: address, accountValue, pnl/roi/vlm by window) | 3000 polled | **32.3%** (top100 7.3%, top300 14.3%, top1000 22.8%); ETH 39.7% |
| leaderboard ranks 3001–46797 | random 1000 sampled (seed 12), scaled ×43.8; the 8 HLP addresses polled in the same run are not scaled | ~5.2%, bootstrap 95% 2.7–8.5% (ETH 2.0% [0.7–3.7], HYPE 4.7% [2.4–7.4]) |
| addresses in the `trades` stream (10 min, 6 coins: 1439 addresses, only 17.8% on the leaderboard) | 1183 non-leaderboard polled | 1.0% |
| sub-accounts of the top-150 leaderboard masters (`subAccounts`, weight 20) | 31 of 150 have subs, 305 subs, **0 of them on the leaderboard** | 2.2% |
| HLP vault and its 7 children | polled | 0.0% |
| **total attributable** | | **≈ 40% of BTC OI** (≈ 38–44% given the tail interval; overlap between sources: 2 addresses in both days' samples; sub-accounts vs trades-stream not checkable, worst case ~1 point double-counted) |

So **~60% of BTC open interest could not be attributed** from the public API with these sources.
The whole leaderboard below rank 3000 adds only ~5%, so the missing OI sits in accounts that are
**not on the leaderboard** and did not trade in the 10-minute window (the leaderboard's inclusion
rule is undocumented; it lists no sub-accounts). Whether that is a few large accounts or many small
ones is unknown. **Not tested:** sub-accounts beyond the top 150 masters.

Paths that could close the gap (not tested, costs are estimates):
1. **Address discovery from history:** every address that traded within the archive's span appears in
   `node_fills_by_block` on S3 (requester pays; span, size and cost not yet checked). Build the full address set once, then keep it
   current from the `trades` stream (both counterparties are on every print). Polling cost then
   scales with the number of accounts that hold positions, which this survey did not measure.
2. **Run a non-validating node** (documented: 16 vCPU, 128 GB RAM, 500 GB SSD, Ubuntu 24.04, ~100
   GB/day of logs, Tokyo recommended). `--serve-info` gives a local `clearinghouseState` for any
   user without the public rate limit, and `periodic_abci_states` (every 10,000 blocks) hold the full
   L1 state, i.e. every position (documented, not verified). This is the only path to **complete** coverage. Rough GCP cost of a
   16 vCPU / 128 GB machine: several hundred USD/month (not priced precisely).
3. Third parties already publish HL liquidation maps built from on-chain positions (CoinGlass
   "Hyperliquid liquidation map", hyperperps.app). Useful as a ground-truth cross-check for
   our own map; not a data source to build on (no history, unknown method, terms of use).

**Refresh cadence, paired with coverage.** Measured 2.5 `clearinghouseState` calls/s sequentially
(≈0.4 s latency from Istanbul): 3000 accounts take **18.4 min** (measured). The weight limit allows
at most 600 calls/min (10/s) per IP, which needs ~4 concurrent requests (not tried):

| refresh cycle | accounts | BTC OI covered | ETH OI covered | basis |
|---|---:|---:|---:|---|
| ≤ 1 min | top 160 | 11.7% | 16.7% | at the measured 2.72 calls/s (163 in 60 s; top 163 gives 12.0% / 16.9%) |
| ≤ 1 min | top 600 | 18.9% | 31.4% | at the 10 calls/s rate-limit ceiling (not achieved) |
| ~5 min | top 3000 | 32.3% | 39.7% | rate-limit arithmetic |
| 18.4 min | top 3000 | 32.3% | 39.7% | measured |
| ~80 min (10/s) to ~5 h (2.72/s) | all sources above, ~48.3k accounts (all 43.8k lower-rank leaderboard accounts, not the 1000 sampled) | ≈ 40% | — | arithmetic |

Cross-margin liquidation prices drift between polls, so a map built this way is minutes stale for
the long tail.

### 2c. Liquidation events
- **No public all-users liquidation feed** exists (no websocket topic, no info type).
- `userFills`/`userEvents` carry `liquidation: {liquidatedUser, markPx, method: market|backstop}`,
  but only for a user you subscribe to (10 users/IP) or poll (weight 20+, last 2000 fills; 10,000
  most recent via `userFillsByTime`).
- The public `trades` stream has no liquidation flag. A liquidation can be **inferred** going
  forward when a print's `users` contains an address we track whose position then disappears or
  shrinks by ~20% (large positions are liquidated 20% at a time with a 30 s cooldown, documented).
- **Historically:** `node_fills_by_block` includes the liquidation field per fill (documented,
  not downloaded; archive start date and size unknown), so past liquidation events can be reconstructed from S3. Past liquidation
  *levels* cannot, without replaying `replica_cmds`.
- Backstop liquidations (equity < 2/3 of maintenance) transfer the position to the HLP liquidator
  vault without trading in the book.

### 2d. Snapshot example (measured, 2026-09-24 19:34 UTC, BTC mark 84,552)
Two leaderboard accounts held $98M long at 35x cross with liquidationPx −1.73% from mark, and $42M
short at 40x isolated with liquidationPx +1.18%. These two are the only top-3000 BTC positions with
liquidation within ±2% of mark: 4.25% of one-sided BTC OI (2.1% on the gross scale used for coverage
above). Within ±5%: BTC 5.35% of one-sided OI, ETH 0.11%, the other four coins 0.00%. This is the thesis in one snapshot: individually visible, large, close to mark. It also shows
that the interesting mass is lumpy, so an event study will have few independent events.

---

## 3. Universe (measured, `metaAndAssetCtxs`, 2026-09-24 19:34 UTC, first ad-hoc run with no saved
output; `probe.log` holds the 2026-09-25 re-run: same top 7. 178 live perps; total 24h volume $8.49B,
OI $13.0B)

| rank | by 24h volume | $M | share | by OI | $M | share |
|---|---|---:|---:|---|---:|---:|
| 1 | BTC | 4010 | 47.2% | BTC | 3298 | 25.4% |
| 2 | ETH | 1087 | 12.8% | ETH | 2881 | 22.2% |
| 3 | HYPE | 832 | 9.8% | HYPE | 1990 | 15.3% |
| 4 | ZEC | 639 | 7.5% | ZEC | 847 | 6.5% |
| 5 | SOL | 314 | 3.7% | SOL | 708 | 5.4% |
| 6 | NEAR | 302 | 3.6% | NEAR | 380 | 2.9% |
| 7 | XRP | 194 | 2.3% | XRP | 293 | 2.3% |
| 8 | ONDO | 127 | 1.5% | LIT | 239 | 1.8% |
| 9 | LIT | 79 | 0.9% | PUMP | 153 | 1.2% |
| 10 | LTC | 77 | 0.9% | DOGE | 121 | 0.9% |

One day's snapshot; ranks 4–10 move with narratives. Max leverage: BTC 40x, ETH 25x, SOL/XRP 20x,
HYPE/ZEC 10x. Suggested collector set: BTC, ETH, SOL (Binance-matched) + HYPE, ZEC, XRP.

---

## 4. Collector cost

Measured over 10 min on 6 coins (BTC, ETH, SOL, HYPE, ZEC, XRP), quiet market:

| stream | msg/s (6 coins) | raw JSON GB/day |
|---|---:|---:|
| `bbo` | 35.3 | 0.43 |
| `trades` | 4.7 (10.2 prints/s total) | 0.25 |
| `activeAssetCtx` | 5.9 | 0.16 |
| `l2Book` (20 levels, ~5 s snapshots) | 1.1 | 0.15 |
| `allMids` | 0.2 | 0.33 (drop it; `activeAssetCtx` covers the coins) |
| **total** | **47** | **1.3** |

Plus position polling: ~3000 accounts × ~1–2 kB per poll cycle, a few hundred MB/day at a 5-min
cycle (estimate). Size for 10× on a violent day: ~500 msg/s, ~15 GB/day raw JSON; p08's hourly
parquet conventions compress JSON several-fold.

**e2-small:** the existing Polymarket + Binance collector already writes ~186 M rows/day (p08), i.e.
~2,150 rows/s (rows, not websocket messages; one message can hold several rows). HL adds ~2% of that in messages; the load that matters is the REST poller
(2.5–10 req/s), which is network-bound, not CPU-bound. It should fit, **but VM headroom was not
measured**; check CPU/RAM/disk on the VM before stage 1. A non-validating node (path 2 above) does
not fit on it under any reading.

---

## 5. Verdict

**Can we, going forward, know where forced liquidations sit BEFORE they happen? — PARTLY.**

- **Yes, for any account we know:** its exact liquidation price per position is public
  (`clearinghouseState.liquidationPx`), including for the largest leveraged positions, and it can
  be refreshed at up to 10 accounts/s per IP.
- **No, not for the market as a whole, from the public API alone.** Coverage and refresh together:
  **~12–19% of BTC OI at ≤ 1 min** (top ~160–600 accounts, one IP, measured vs ceiling rate), 32% at
  5–18 min, ≈ 40% (38–44%) at 80 min–5 h using every source found. Pre-registered bar for "yes" (PLAN.md): ≥ 70% of BTC OI at
  ≤ 1 min refresh. **Not met, by a wide margin.**
- **Liquidation events:** no public all-users feed. Going forward they are inferable for tracked
  accounts; historically they are in the S3 fill archive (requester pays, not downloaded).

**Per the kill criterion this does not kill the line**: liquidation levels *are* obtainable from
position state, and a "partly" continues to stage 1 as long as the covered share is stated and the
event study is conditioned on it. Two honest caveats: (i) the pre-registered criterion had no floor
for "partly", so once per-account positions proved public the line could only be killed by "no";
(ii) conditioning on visibility needs position snapshots at each event, which exist only from the
day we start polling, so it can only be done on data collected going forward. Before stage 1 builds the collector, one cheap step decides how
far "partly" goes: build the address set from `node_fills_by_block` (one S3 pull, cost to be priced
first) and measure what share of OI it attributes. If that still leaves most OI unseen, the
remaining options are a non-validating node (complete, expensive) or scoping the thesis down to
"large visible positions near liquidation", which is where the one snapshot above says the action is.
