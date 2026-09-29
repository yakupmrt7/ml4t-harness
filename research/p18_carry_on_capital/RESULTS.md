# p18 — HL funding carry on survivable capital (dev): the ORACLE earns 5.0%/yr in 2025 → carry closed

**Verdict: decision rule 1 fires.** Even a book that knows every future day's carry and times it perfectly
(C = oracle perp/spot) earns **5.0 ± 1.0%/yr on survivable capital in 2025**, below the pre-registered 6%/yr
(T-bill + 2 pts for two venues and stablecoin risk). The static books earn less: A (short HL perp / long Binance
perp) **2.7%/yr**, B (short HL perp / long Binance spot) **4.2%/yr**. Per PLAN, **funding carry is closed
entirely, including the NEWPLAN #3 forecasting version**: no forecast of these books can beat the oracle.
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
- **Survivable leverage (daily reset, 1.5× buffer on the worst dev day):** BTC 3.9× short HL / 3.4× long BN perp;
  ETH 2.5 / 2.2; SOL 2.3 / 1.7; XRP 1.5 / 1.1; DOGE 1.7 / **0.96**; LINK 1.5 / 1.0; AVAX 2.7 / **0.91**; SUI 1.5 /
  **0.77**. The alt long legs' worst one-day moves (58–83%, mostly 2025-10-10) force them below 1×, so their capital
  exceeds notional. The sizing uses dev's worst days including 2025 (look-ahead that can only lower the return;
  disclosed in PLAN).
- 2025-10-10 at daily closes: A −0.04%, B +0.13% of notional that day (the liquidation risk is in the leverage,
  not in the daily P&L).

### Per coin, 2025, %/yr on capital (descriptive; not a decision input)
| | BTC | ETH | SOL | XRP | DOGE | LINK | AVAX | SUI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | **8.87** | 2.81 | 3.66 | 2.41 | 1.79 | 3.10 | 2.76 | 1.22 |
| B | **7.76** | 4.86 | 2.32 | 4.04 | 4.07 | 5.69 | 2.37 | 2.89 |
| oracle B | 7.76 | 5.03 | 3.63 | 5.31 | 4.55 | 5.72 | 4.37 | 4.01 |

**BTC alone clears 6% on capital in 2025**, because its small worst-day moves (14–17%) allow ~3.5× per leg. This
is a single coin chosen after seeing the per-coin results: it is selection, not evidence, and the pre-registered
decision above closes the line. Testing a BTC-only book would need its own PLAN and the owner's decision to reopen
carry; it would then be a legitimate one-trial use of p14's sealed holdout.

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
