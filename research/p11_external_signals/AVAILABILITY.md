# p11 Step 0: what external history is actually obtainable (2022-08 → 2026-08)

Surveyed 2026-09-24 with a handful of API calls per source. No study-period
data was downloaded. From the laptop, `www.deribit.com` times out (blocked,
like Polymarket), so Deribit's main API was probed from `collector-vm`.
`history.deribit.com`, Bybit, OKX, Hyperliquid and data.binance.vision are
reachable from the laptop.

## Summary
| source | data | obtainable free? | coverage in 2022-08 → 2026-08 | granularity | verdict |
|---|---|---|---|---|---|
| **Deribit DVOL** (`public/get_volatility_index_data`, www) | BTC 30-day implied-vol index, OHLC | yes | **full** (daily back to 2021-03-24; hourly checked at 2022-08, 2024-01, 2026-08) | **1 h** candles (1 min is recent only: empty at 2022/2024) | **KEEP** (backfill from the collector VM, since www is blocked here) |
| **Deribit option trades** (`history.deribit.com`, `get_last_trades_by_currency_and_time`, kind=option) | every BTC option trade: instrument (expiry/strike/type), price, **iv**, index price, mark price, amount, **direction** | yes | **full** (checked 2022-09-01, 2024-01-10, 2026-08-20) | per trade (ms). The busiest sample: 172 trades in 10 min | **KEEP**. Est. 5–25 k trades/day → ~10–35 M trades, count = 1000 per call → ~10–35 k calls |
| Deribit option chain / order-book snapshots | full chain marks, greeks, OI at past times | **no** (the public API gives current books only) | — | — | DROP (paid: Tardis.dev, Laevitas, Amberdata) |
| **Deribit perp funding** (`get_funding_rate_history`, www) | hourly `interest_1h` / `interest_8h`, index price | yes | **full** | 1 h | **KEEP** |
| **Deribit perp trades** (`history.deribit.com`, kind=future) | BTC-PERPETUAL trades, index and mark price | yes | full | per trade | optional; mark/index are already in the funding rows (hourly) |
| **Binance USD-M liquidations** (`futures/um/daily/liquidationSnapshot/BTCUSDT/`) | liquidation orders | **no**: the prefix exists but is **empty** (monthly also empty) | — | — | **DROP** |
| Binance COIN-M liquidations (`futures/cm/daily/liquidationSnapshot/BTCUSD_PERP/`) | liquidation snapshots | yes | **2023-06-25 → 2024-10-14 only** (472 files) | per event (Binance's snapshot stream is capped at ~1/s/symbol) | **DROP**: starts 10 months into pre-OOS and stops 6 months into OOS. The COIN-M book is also much smaller than USD-M |
| Bybit / OKX liquidation history | — | no (public endpoints are recent-only) | — | — | DROP (paid: Coinglass, Tardis) |
| **Bybit** funding (`/v5/market/funding/history`, linear BTCUSDT) | settled funding | yes | **full** (checked 2022-08, 2024-01, 2026-08) | 8 h | **KEEP** |
| **Bybit** perp candles (`/v5/market/kline`, 5 m) | OHLCV | yes | **full** | 5 m | **KEEP** (basis) |
| OKX funding (`/api/v5/public/funding-rate-history`) | settled funding | **only the last ~3 months** (empty for 2022 and 2024; data at 2026-06) | — | 8 h | DROP (OKX's bulk "historical data" files did not resolve at guessed URLs; unverified) |
| **OKX** perp candles (`/api/v5/market/history-candles`, BTC-USDT-SWAP, 5 m) | OHLCV | yes | **full** | 5 m | **KEEP** (basis) |
| Hyperliquid funding (`info` fundingHistory) | hourly funding + premium | yes | **from ~2023-05 only** (empty 2022-08, present 2023-06) | 1 h | **DROP**: it would push the common sample start to 2023-05 and cut pre-OOS to ~11 months |
| Hyperliquid candles (`candleSnapshot`) | OHLCV | recent only (empty at 2023-06 and 2026-08 for a 1 h window) | — | — | DROP |
| Paid vendors (Tardis, Kaiko, Coinglass, Laevitas, Amberdata) | chains, full liquidations | paid | — | — | DROP (per brief) |

## What this leaves for the feature set
The owner's requested families, mapped to what survived:
1. **Implied vol level and its change:** DVOL (1 h), plus an ATM-IV proxy
   from Deribit option trades. ✔
2. **Implied − realised spread:** DVOL vs realised vol from our own
   Binance 5 m bars. ✔
3. **Liquidation volume and imbalance by side: NOT OBTAINABLE free for the
   window.** USD-M is empty, and COIN-M covers only 2023-06 → 2024-10. ✘
   - The closest free substitute is **options flow** (Deribit trade
     direction, calls vs puts). It is a different signal, not a stand-in
     for liquidations, and is proposed as its own family.
4. **Funding dispersion across venues:** Binance (already on disk), Bybit
   (8 h) and Deribit (1 h). Three venues; OKX and Hyperliquid drop out. ✔
   (narrower than asked)
5. **Basis differences between venues:** Binance vs Bybit vs OKX perp 5 m
   closes (and Deribit perp mark/index, hourly). ✔

**Honest assessment.**
- The two families most distinct from p03's failed set are liquidations
  (unavailable) and options (available).
- Funding dispersion and cross-venue basis are close relatives of p03's
  Binance funding/basis features. None of those reached pre-OOS |t| ≥ 2,
  and adding them lowered AUC.
- The genuinely new information here is **Deribit options: DVOL and the
  option trade flow.**

## Proposed publication lags (to be fixed in PLAN amendment 1, before backfill)
| source | stamp | assumed availability | alignment to a 5 m bar closing at t |
|---|---|---|---|
| DVOL 1 h candle | candle open time; covers [T, T+1 h) | computed continuously by Deribit; the close is final at T + 1 h. Allow 1 min | a candle is usable from the first bar closing ≥ T + 1 h + 1 min, i.e. the bar at T + 1 h + 5 min. Worst case ~5 min stale. |
| Deribit option trades | trade timestamp (ms) | public in real time | trades with timestamp < t |
| Deribit funding (hourly) | the row's timestamp | published at the stamp | a row stamped ≤ t − 1 min |
| Bybit / Binance funding (8 h settled) | settlement time | the settled rate is known at settlement | strict `asof_join` (the row is first used by the bar closing after the stamp), as p03 |
| Bybit / OKX 5 m candles | candle open time | final at open + 5 min | the candle closing at t is used at bar close t. It is public at t within ms, same as our own Binance bar. Execution is delay ≥ 1 anyway |

## Backfill cost estimate (after "go")
- **Deribit option trades:** ~10–35 k calls to history.deribit.com from the
  laptop, which reaches it. At a polite ~5 req/s, **~0.5–2 h**. Raw
  trades are stored as daily parquet in `data/collector/p11/deribit_opt/`,
  probably a few hundred MB.
- **DVOL hourly + Deribit hourly funding:** ~40 calls in total, run
  from `collector-vm` (www is blocked here), minutes.
- **Bybit funding and 5 m candles:** ~4,500 kline calls (1,000 bars each)
  + ~30 funding calls. Minutes.
- **OKX 5 m candles:** history-candles returns 100 per call, so ~4,200
  calls at ~10 req/s, ~10 min.
- **No new collector, no paid source, no VM needed**, except the ~40
  Deribit-www calls routed through the existing collector box.

## Decision needed (owner)
- **"go":** backfill DVOL, Deribit option trades, Deribit/Bybit funding,
  and Bybit/OKX 5 m candles. Then write PLAN amendment 1 (the exact
  pre-registered feature list and the lags above) **before** computing any
  feature or label statistic.
- **Liquidations are dropped** (no free history). Options flow is proposed
  as a separate family, not a substitute.
