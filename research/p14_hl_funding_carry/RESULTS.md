# p14 — HL vs Binance funding carry (dev): the registered rule passes its screen by 0.25 pt; the static book is KILLED (survival)

Dev only (2024-01-01 → 2026-01-12), all 8 coins. Holdout (2026-01-12 → 2026-09-27) not read. No trial logged.
Plan: `PLAN.md` (pre-registered rule) and amendment 1 (16d913f: the static book, pre-registered before its
8-coin dev run; post hoc in origin). The interim 3-coin write-up (kill 1 fired on BTC/ETH/SOL) is superseded.

## Market reasoning (for the owner)
Hyperliquid's retail longs pay more for leverage than Binance's: HL funding exceeds Binance funding on average.
Short HL / long Binance collects the difference with no net price exposure — but each leg sits on a different
venue with its own margin. When price rips, the short leg bleeds margin; when it wicks down, the long leg does.
A hedged book can still be liquidated one leg at a time, and that is where this trade's risk lives.

## 1. The pre-registered rule (PLAN; 7-day mean spread, enter > 3 bps/day, exit < 1 bp/day, taker)
| coin | in market | spread bps/day | AR(1) | funding %/yr | basis %/yr | cost %/yr | **net %/yr** | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BTC | 42% | 2.41 | 0.62 | 5.52 | 0.31 | −1.24 | 4.59 | 4.5 |
| ETH | 32% | 1.73 | 0.54 | 4.00 | 0.13 | −1.14 | 2.99 | 3.0 |
| SOL | 52% | 2.64 | 0.56 | 7.06 | 0.25 | −1.65 | 5.66 | 4.1 |
| XRP | 39% | 1.35 | 0.59 | 4.32 | 0.40 | −1.45 | 3.27 | 3.2 |
| DOGE | 43% | 3.75 | 0.80 | 11.42 | 0.15 | −1.14 | 10.44 | 5.7 |
| LINK | 39% | 2.81 | 0.66 | 6.86 | 0.27 | −1.14 | 5.99 | 4.1 |
| AVAX | 49% | 1.85 | 0.67 | 6.46 | 0.40 | −2.38 | 4.49 | 3.2 |
| SUI | 36% | 2.04 | 0.66 | 5.48 | 0.83 | −1.76 | 4.55 | 3.1 |
| **portfolio** | | | 0.64 (median) | | | | **5.25** (maker 6.24) | 6.7 |

- **Kill 1 (net ≤ 5%/yr): does not fire, by 0.25 pt.** Kill 2 (Sharpe ≥ 1, ≥ half the coins positive): passes
  (8/8). Persistence flag: off (median AR(1) 0.64).
- **Delay 2 (signal through d−2): 4.64%/yr — below the kill line.** The pass does not survive one day of delay.
- **Decay:** net by quarter 18.0 / 3.4 / 1.9 / 12.1 %/yr in 2024 → 0.8 / 2.0 / 3.9 / 0.7 in 2025, −0.1 in
  early 2026. The dev mean is carried by 2024Q1 and 2024Q4.
- **Sharpe is overstated:** basis is marked at daily closes, so intraday excursions (which drive margin calls)
  are invisible to it.
- **Survival (diagnostic, not a registered kill of this rule; `rule_survival.py`):** at 2× per leg, the rule's own
  positions would have had a leg liquidated in **5 of 8 coins** (SOL 2025-01-19; XRP Nov 2024; DOGE Feb–Mar and
  Nov 2024 and **2025-10-10**; AVAX 2024-03-16 and **2025-10-10**; SUI Jan and Nov 2024). A survivable book needs
  ~1× per leg, i.e. capital ≈ 2× notional, which turns 5.25%/yr on notional into **~2.6%/yr on capital** — below
  the T-bill rate the kill was meant to beat.

## 2. The static book (amendment 1: short HL / long BN always, 2× per leg, weekly reset) — KILLED at kill 4
| kill | dev value | bar | |
|---|---:|---:|---|
| 1. net per unit notional | **7.70%/yr** | > 5% | pass |
| 2. weekly t | **7.15** (106 weeks) | ≥ 2 | pass |
| 3. worst 5 days / mean 5 days | **2.1×** (2025-04-09) | ≤ 12× | pass |
| 4. no leg liquidated at 2× | **legs liquidated in 6/8 coins** | none | **FIRES** |

Worst adverse move of each leg from its Monday reset (Binance daily high/low): the short HL leg saw **+116%**
(XRP, Nov 2024), +97% (DOGE), +80% (SUI), +57% (SOL); the long BN leg saw **−84%** (SUI), −72% (AVAX), −67% (DOGE),
−63% (LINK), −60% (XRP) — the last four on **2025-10-10**. BTC (+24% / −19%) and ETH (+44% / −28%) survive.
Net by quarter 22.9 / 4.7 / 3.2 / 14.0 %/yr (2024) → 4.0 / 2.6 / 7.8 / 3.3 (2025), 0.1 (2026Q1 to 01-12).
Funding carries it (BTC 8.8%/yr, DOGE 13.7%); basis ≈ 0; weekly reset costs 0.3–0.8%/yr per coin.

**ADL stress, 2025-10-10:** HL auto-deleveraged shorts in all 8 coins (21:16–21:42 UTC). If the whole short leg
had been ADL'd at the median ADL price and re-shorted at the close, the day would have **gained** +13% of
portfolio notional (per coin +4.4% BTC … +23.2% DOGE): ADL closed shorts near the bottom, before the rebound. With
it, worst 5 days / mean 5 days is 1.1× (kill 3 unchanged). ADL is not this book's danger that day; the Binance
long leg's −60 to −84% intraday wick is.

A lower leverage would be a different book and a new trial; it would also halve (1×) the return on capital,
to ~3.9%/yr at dev's 7.7%/yr on notional — and dev's 2025 quarters average ~4.4%/yr on notional.

## What this means
- The HL-over-Binance funding premium is real and persistent (8/8 coins, AR(1) 0.64), but it has decayed from
  ~10%/yr in 2024 to ~2–4%/yr on notional in 2025, i.e. roughly the T-bill rate on the capital a survivable
  (≈1×) book needs.
- The trade's risk is not price exposure but per-venue margin: alt legs move 60–120% within a week or a day, so
  either capital is idle (low leverage) or a leg gets liquidated. That is why the spread persists: arbitrage
  capital demands exactly this premium for that risk.
- NEWPLAN #3 in this form is closed on dev for the static book. The registered rule's narrow screen pass is the
  only thing that could still spend the holdout (see the OOS decision in the session summary; not run).

## Files
`PLAN.md` (+ amendment 1) · `fetch.py`, `fetch.log` · `run.py`, `run_delay{1,2}.log`, `results_delay{1,2}.json` ·
`static.py`, `static_dev.json`, `static_dev.log` · `rule_survival.py`, `rule_survival.json`.
