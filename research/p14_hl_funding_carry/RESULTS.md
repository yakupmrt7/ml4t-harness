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

- **Kill 1 (net ≤ 5%/yr): does not fire, by 0.25 pt — 0.15 standard errors.** With autocorrelation-robust
  (Newey–West, lag 30) errors the result is **5.25 ± 1.6%/yr** (daily P&L lag-1 autocorrelation 0.31; review).
  Kill 2 (Sharpe ≥ 1, ≥ half the coins positive): passes (8/8); the naive Sharpe of 6.7 is ≈ 2.3 after the
  autocorrelation adjustment. Persistence flag: off (median AR(1) 0.64).
- **Delay 2 (signal through d−2): 4.64%/yr — below the kill line.** The pass does not survive one day of delay.
- **Decay:** net by quarter 18.0 / 3.4 / 1.9 / 12.1 %/yr in 2024 → 0.8 / 2.0 / 3.9 / 0.7 in 2025, and −0.1 in
  "2026Q1" (**11 days**, to 01-12). 2024 averages 8.8%/yr, **2025 1.84 ± 0.74%/yr**; four months (Feb–Mar and
  Nov–Dec 2024) produce most of the return, and without them the rule makes about 2.2%/yr (review).
- **Survival (diagnostic, not a registered kill of this rule; `rule_survival.py`):** at 2× per leg with the weekly
  reset, the rule's own positions would have had a leg liquidated in **5 of 8 coins** (SOL 2025-01-19; XRP Nov 2024;
  DOGE Feb–Mar and Nov 2024 and **2025-10-10**; AVAX 2024-03-16 and **2025-10-10**; SUI Jan and Nov 2024). With a
  daily reset (what an operator would do), the worst one-day adverse moves on dev are +42% against the short HL leg
  (XRP 2024-11-16, LINK 2024-12-02) and **−83% against the long BN leg (SUI 2025-10-10, on Binance's mark price)**.
  Survivable leverage is therefore about 2× on the short leg and ≤ 1.15× on the long leg, capital ≈ **1.37×
  notional**, and the return on capital is **3.8%/yr on dev, 1.3%/yr in 2025** (review). The kill-1 benchmark
  assumed 2× (capital ≈ 1× notional), which dev shows does not survive, so the screen pass does not establish an
  investable return.

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

Kill 4 is robust (review): with a **daily** reset, 2× legs are still liquidated, on 2025-10-10 in XRP, DOGE,
LINK, AVAX and SUI; Binance's **mark-price** lows that day were within 0–2 pts of the last-trade lows (−57% to −83%
from the previous close), so it is not a wick artefact; cross margin does not help (the 8 Binance longs fell ~52%
together). The margin rule understates the damage: it ignores liquidation fees and the naked leg left behind
(for DOGE on 10-10 roughly 20–25% of the coin's notional, about a decade of its 2025 carry). The weekly t of 7.15
is overstated by autocorrelation in the same way as the rule's Sharpe.

**ADL scenario, 2025-10-10 (reported only):** HL auto-deleveraged shorts in all 8 coins (21:16–21:42 UTC). At the
median ADL fill price, fully ADL'ing the short leg and re-shorting at the close would have been a gain that day,
because prices rebounded after 21:20. This is one event and one arbitrary summary price (SUI ADL fills ranged
0.61–2.59 around a close of ~2.6); HL ranks ADL by profit × leverage, so a 2× account is unlikely to be fully
deleveraged; and the scenario assumes a Binance long that kill 4 says was liquidated. In a crash that keeps falling
after ADL, the naked long loses. (`with_adl_net_ann%` = 14.1 in static_dev.json is one day adding 6.4 pts/yr; not a
meaningful return.)

A lower leverage would be a different book and a new trial. At the daily-reset survivable leverage (capital ≈ 1.37×
notional) the static book returns **5.6%/yr on capital on dev and 3.2%/yr in 2025** (review).

## What this means
- The HL-over-Binance funding premium is persistent (8/8 coins, AR(1) 0.64), but it roughly quartered from 2024 to
  2025: the registered rule made 8.8%/yr in 2024 and 1.8 ± 0.7%/yr in 2025 on notional, and on survivable capital
  1.3%/yr (rule) and 3.2%/yr (static) in 2025 — below the T-bill rate plus two-venue and stablecoin risk.
- The trade's risk is per-venue margin, not price exposure: alt legs move 40–120% within a day or a week, so either
  capital sits idle at low leverage or a leg is liquidated. (Whether that risk is *why* the spread persists is a
  plausible story, not tested here.)
- The static book is killed on dev (kill 4). The registered rule passed its screen by 0.15 s.e., fails at delay 2,
  and its benchmark's 2× capital assumption fails on dev.

## OOS gate (holdout 2026-01-12 → 2026-09-27)
Reviewer's recommendation (REVIEW.md): **spend nothing; keep the holdout sealed.** The PLAN allows but does not
require the look. A pass would need 2026 above 5%/yr when 2025 ran at 1.8 ± 0.7%/yr, and could not be claimed
because 2× does not survive on dev. The 2026 funding data is the only fresh test data for any carry variant.
If the owner still wants the rule closed with an OOS number: commit a `--holdout` mode for `run.py` first
(position state and 7-day window carried from dev; one `TrialLog("trials_hl.json")` entry), run
`python research/p14_hl_funding_carry/run.py --holdout` once, with kills exactly PLAN 1–2 and the persistence flag;
delay-2 and survival reported; a pass worded "passes screen; not investable at 2× (dev survival)".
**Owner's decision: pending.**

## Review and hygiene
`REVIEW.md` (pre-OOS): **ACCEPT WITH FIXES**, both dev verdicts stand; no look-ahead; signs, day sums, candles
and costs checked (HL spread assumed at 0.5 bps/leg, ≤ 0.15%/yr). Disclosures: `run.py`/`static.py` load data
through 2026-09 and run the position logic through the holdout before cutting at the dev end (causal, nothing
printed, but "holdout not read" is not literally true); amendment 1 was committed at 13:50 UTC after the DOGE–SUI
fetch finished (~13:00), so "before the 8-coin numbers" cannot be verified from timestamps (moot: the static
book died on kill 4). Numbers marked "(review)" were computed by the reviewer and are recorded in REVIEW.md.

## Files
`PLAN.md` (+ amendment 1) · `fetch.py`, `fetch.log` · `run.py`, `run_delay{1,2}.log`, `results_delay{1,2}.json` ·
`static.py`, `static_dev.json`, `static_dev.log` · `rule_survival.py`, `rule_survival.json`.
