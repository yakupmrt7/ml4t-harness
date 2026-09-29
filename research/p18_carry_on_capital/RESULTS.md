# p18 — HL funding carry on survivable capital (dev): the ORACLE earns 5.0%/yr in 2025 → carry closed

**Verdict: decision rule 1 fires.** Even a book that knows every future day's carry and times it perfectly
(C = oracle perp/spot) earns **5.0 ± 1.0%/yr on survivable capital in 2025**, below the pre-registered 6%/yr
(T-bill + 2 pts for two venues and stablecoin risk). The static books earn less: A (short HL perp / long Binance
perp) **2.7%/yr**, B (short HL perp / long Binance spot) **4.2%/yr**. Per PLAN, **funding carry is closed,
including the NEWPLAN #3 forecasting version — by the pre-registered decision, not by a proof.** The oracle is not
a strict ceiling: it earns nothing on idle capital (flat on 18.8% of capital-days), and with T-bills on idle capital
it reaches 6.18%/yr, right at the bar (review; changing the ceiling now would be a post-hoc loosening, so rule 1
stands). The practical reading: to reach 6%, a forecast would need about **91% of perfect foresight's timing gain**
over static B, (6 − 4.21)/(6.18 − 4.21). And the oracle bounds only the *timing* of this fixed 8-coin book, not
coin selection across Hyperliquid (BTC alone reaches 8.9%, below).
Dev only (2024-01-01 → 2026-01-12, loaders and fetches cut at the dev end); p14's holdout stays sealed; no trial.

Plan: `PLAN.md` (ec8c73f); code and oracle tests committed before computation (see git log).

## Numbers (portfolio of 8 coins, equal notional; returns on capital, annualised; ± = Newey–West s.e.)
| | capital / notional | 2025 %/yr | 2025 monthly t | 2025 worst 5d / mean 5d | dev %/yr | dev monthly t |
|---|---:|---:|---:|---:|---:|---:|
| A static perp/perp | 1.35 | **2.74 ± 0.84** | 2.82 | 4.8× | 5.20 ± 1.29 | 4.09 |
| B static perp/spot | 1.51 | **4.21 ± 1.21** | 3.12 | 3.8× | 9.44 ± 2.37 | 4.01 |
| oracle A | 1.35 | 3.76 ± 0.56 | 5.64 | 0.6× | 6.59 ± 1.23 | 5.31 |
| **oracle B = C** | 1.51 | **5.01 ± 0.95** | 4.69 | 0.8× | 10.07 ± 2.29 | 4.42 |

- **Decision rule 1 (C < 6% → close carry): fires.** Rule 2: neither static book reaches 6% on capital in 2025
  (both pass the t and tail parts). Rules 3–4 do not apply.
- **Why the oracle adds little:** switching costs 10.5–15.5 bps per side, while the daily basis between venues
  moves only a few bps, so perfect timing mostly means "stay in"; the oracle is in the market 505–742 of 742 days
  per coin. The ceiling is set by the funding level itself, which fell from 2024 to 2025.
- **The biggest cost is the daily reset** (restoring each leg to target notional every day at taker prices):
  about **1.2%/yr on capital**, more than the oracle's whole timing gain. For B in 2025 on notional: HL funding
  +8.37%, basis −0.25%, reset −1.79% → ≈ 6.3%/yr, ÷ 1.51 capital = 4.2%.
- **Robustness of C (review; one change at a time unless stated; none is used to overturn rule 1):**

  | change | C %/yr |
  |---|---:|
  | registered | 5.01 |
  | buffer 1.25 / 1.0 | 5.27 / 5.56 |
  | no reset cost | 5.98 |
  | maker-level fees (best oracle, A) | 5.59 |
  | cross-margined legs per venue | 5.64 |
  | T-bill on idle capital | **6.18** |
  | cross-margin + buffer 1.0 | 6.24 |
  | buffer 1.0 + no reset + maker fees | 8.61 |

  Every single change except T-bills on idle capital keeps C under 6%; two or more stacked loosenings cross it. No
  static book reaches 6% under any single change (B with three stacked loosenings: 5.99).
- **Survivable leverage (daily reset, 1.5× buffer on the worst dev day):** BTC 3.9× short HL / 3.4× long BN perp;
  ETH 2.5 / 2.2; SOL 2.3 / 1.7; XRP 1.5 / 1.1; DOGE 1.7 / **0.96**; LINK 1.5 / 1.0; AVAX 2.7 / **0.91**; SUI 1.5 /
  **0.77**. The alt long legs' worst one-day moves (58–83%, mostly 2025-10-10) force them below 1×, so their capital
  exceeds notional. The sizing uses dev's worst days including 2025. PLAN called this look-ahead conservative; for a
  *closure* it is generous: sized on 2024 alone, five alt long legs and SOL's short leg would have been liquidated
  in 2025, mostly on 10-10 (BTC and ETH survive). The 2025 static returns also carry no entry/exit cost
  (≤ 0.2%/yr generous).
- 2025-10-10 at daily closes: A −0.04%, B +0.13% of notional that day (the liquidation risk is in the leverage,
  not in the daily P&L).

### Per coin, 2025, %/yr on capital (descriptive; not a decision input)
| | BTC | ETH | SOL | XRP | DOGE | LINK | AVAX | SUI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | **8.87** | 2.81 | 3.66 | 2.41 | 1.79 | 3.10 | 2.76 | 1.22 |
| B | **7.76** | 4.86 | 2.32 | 4.04 | 4.07 | 5.69 | 2.37 | 2.89 |
| oracle B | 7.76 | 5.03 | 3.63 | 5.31 | 4.55 | 5.72 | 4.37 | 4.01 |

**BTC alone clears 6% on capital in 2025:** A 8.87 ± 1.51, B 7.76 ± 0.98 (≈ 1.8–1.9 s.e. above 6; 2024: 20.4 and
18.2). For A the edge is leverage (worst-day moves of 14–17% allow ~3.5× per leg); for B it is BTC's high HL funding
(10.6%/yr) and its low reset cost (0.89 vs 1.79%/yr). This is a coin chosen after seeing the table — "lowest wick"
is one of several rules one could name post hoc — so it is selection, not evidence, and the pre-registered decision
closes the line. An 8.5-month holdout has a standard error of ~1.2–1.8%/yr, so one look could not tell 6% from 8%.
Reviewer's view, which I share: BTC carry at roughly T-bill + 3–4 pts, and shrinking, is an investment decision, not
a research finding. Spend p14's sealed holdout on it only if the owner would actually deploy capital on a pass and
reverses the closure in writing (new frozen PLAN, review, one trial in `trials_hl.json`).

## What this means
- The HL funding premium is real, but on the capital needed to survive the venues' wicks it paid ~2.7–4.2%/yr in
  2025 for a diversified book, and at most 5.0% with perfect foresight: below T-bills plus the risks of holding
  collateral on two venues.
- With p15–p17, every NEWPLAN idea is closed: #1 (p15), #2 (p16), #3 (p14 + p18), #4 (p17).

## Not covered
Coins outside the fixed 8 (HL-only alts with high funding have no Binance hedge leg), other hedge venues (Bybit,
OKX), USDC/USDT basis and transfer delays, exchange default, and funding-rate swaps (Pendle Boros). The oracle is a
ceiling for timing these books at daily resolution, not for every possible carry trade.

## Files
`PLAN.md` · `run.py` · `test_oracle.py` · `results.json` · `run.log` · `selection_trials.json`.
