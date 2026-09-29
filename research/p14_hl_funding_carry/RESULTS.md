# p14 — HL vs Binance funding carry: INTERIM (3 of 8 coins), pre-registered rule KILLED at kill 1

Status 2026-09-28: BTC, ETH, SOL fetched; XRP DOGE LINK AVAX SUI still downloading (HL API rate limit,
~2.5 min/coin). Rerun `python research/p14_hl_funding_carry/run.py` when `fetch.log` lists all eight.
Dev only (2024-01-01 → 2026-01-12); holdout not read. No trial logged yet (screen; see "next").

## Pre-registered rule (PLAN.md): 7-day mean spread, enter at |m| > 3 bps/day, exit at 1 bp/day, taker

| coin | in market | spread mean bps/day | AR(1) | funding %/yr | basis %/yr | cost %/yr | **net %/yr** | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BTC | 42% | 2.41 | 0.62 | 5.52 | 0.31 | −1.24 | **4.59** | 4.5 |
| ETH | 32% | 1.73 | 0.54 | 4.00 | 0.13 | −1.14 | **2.99** | 3.0 |
| SOL | 52% | 2.64 | 0.56 | 7.06 | 0.25 | −1.65 | **5.66** | 4.1 |
| portfolio | | | | 5.53 | 0.23 | | **4.41** (maker 5.31) | 5.3 |

- **Kill 1 fires:** 4.41 %/yr ≤ 5 %/yr. Kill 2 passes (Sharpe 5.3, 3/3 coins positive); persistence
  passes (median AR(1) 0.56). Delay 2 (BTC+ETH): 3.41 vs 3.79 %/yr at delay 1.
- **Decaying:** net by quarter 12.5 / 4.7 / 3.6 / 11.6 %/yr in 2024 → 0.5 / 0.6 / 2.9 / −0.7 in 2025.
- Sharpe is overstated: funding accrues smoothly and basis is marked only at daily closes, so
  intraday basis excursions (which drive margin calls on the losing leg) are not in the series.

## Why it failed: the threshold sat above the structural spread (post hoc, not a decision input)
HL funding exceeds Binance's in **every** dev quarter (BTC spread +4.0 to +19.7 %/yr annualised; ETH
+1.3 to +12.5). In 2025 the spread was ~1.3–1.8 bps/day, below the 3 bps/day entry, so the rule stayed flat.
A zero-parameter "always short HL / long BN" book (one taker entry and exit) earns on dev:

| | BTC | ETH | SOL | portfolio | 2024 quarters | 2025 quarters | worst 5 d |
|---|---:|---:|---:|---:|---|---|---:|
| static short HL / long BN, %/yr per unit notional | 8.67 | 6.13 | 9.47 | **8.09** | 19.5 / 8.3 / 5.6 / 13.7 | 4.1 / 3.3 / 7.8 / 3.4 | −18 bps |

This is post hoc on read dev data, so it is a hypothesis for the holdout and not a result. Economically
it is a **yield**, not alpha: HL's retail longs pay more for leverage than Binance's, arb capital
compresses the gap, and in 2025 it is ~4.6 %/yr per unit notional, roughly the T-bill rate. On capital,
at 3x margin per leg (capital ≈ 0.67 × notional) that is ~7 %/yr before: the risk of a leg being
liquidated in a spike, USDC (HL) vs USDT (Binance) basis, and venue risk on both.

## Next (owner's call)
1. Finish the 8 coins and rerun (no rule change). Alts are where HL retail leverage is largest.
2. If the static book is to be tested, pre-register it (rule, 5 %/yr kill, margin buffer) and spend
   the **one** holdout look on it (2026-01-12 → 2026-09-27), logged in `trials_hl.json`.
