# p11 external signals: the last test of 1 h / 4 h BTC direction

**Verdict: KILLED pre-OOS, on both pre-registered conditions.**
1. **External-only AUC is 0.4979 at H = 48** (< 0.52), i.e. chance. Its
   gross Sharpe is −1.38 and its breakeven −2.88 bps.
2. **The best H = 48 configuration is basic-only**, at 2.85 ± 0.96 bps
   (< 4).

- **Adding the external features makes the model worse.** At H = 48,
  AUC(both) − AUC(basic) = **−0.0206 ± 0.0068** (day-block bootstrap),
  ≈ 3 s.e. *below* zero, where the gate needed +0.01. The combined
  model's breakeven is −1.84 bps.
- No OOS run; `trials.json` untouched (3).
- **Per the plan, the 1 h / 4 h BTC bar-direction line is now closed
  permanently.** CLAUDE.md records it.

## Data (Step 0, `AVAILABILITY.md`; all free, backfilled 2026-09-24)
- **Deribit** (through the collector box, since www.deribit.com is blocked
  from the laptop):
  - DVOL, 1 h: 36,769 candles, zero gaps;
  - perp funding, 1 h: 36,480 rows, zero gaps.
- **Deribit BTC option trades** (history.deribit.com): **17.9 M trades**
  over all 1,492 days (1,860–62,417 per day), each with `iv`, direction,
  strike and expiry.
- **Bybit:** funding (4,477 settlements) and 5 m candles (429,696 bars,
  zero gaps).
- **OKX:** 5 m candles (429,696 bars, zero gaps).
- **Binance:** funding and 5 m bars (on disk).
- **Dropped at Step 0:**
  - **liquidations** (Binance USD-M archive empty; COIN-M only
    2023-06 → 2024-10);
  - OKX funding (API keeps ~3 months);
  - Hyperliquid (from 2023-05 only);
  - option chains (paid).
- **26 features, pre-registered in PLAN amendment 1 before any backfill:**
  DVOL (6), options flow (8), ATM IV from trades (2), funding dispersion
  across Binance/Bybit/Deribit (4), cross-venue basis vs Bybit/OKX (6).
  Publication lags are fixed per source. Look-ahead audit: no suspects.

## Pre-OOS results
Labels have t0 and t1 before 2024-04-07 09:15. `PurgedKFold(5, 0.01)`,
uniqueness weights, P2 = hysteresis(0.05, 0, 24) run p02-exact, p05 cost
table. Every source covers the full pre-OOS window, so the common sample
starts 2022-09-01.

| H | model | AUC | gross SR (d1 / d2) | net SR maker | turnover / yr | breakeven bps ± s.e. | de-meaned | shift-null p |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **48** | basic | **0.5410** | 2.15 / 1.75 | −0.20 | 3,065 | **2.85 ± 0.96** | 2.45 | 0.015 |
| 48 | external | **0.4979** | −1.38 / −1.34 | −2.86 | 1,991 | −2.88 ± 1.67 | −3.87 | 0.990 |
| 48 | both | 0.5205 | −1.00 / −0.85 | −2.67 | 2,316 | −1.84 ± 1.49 | −2.59 | 0.980 |
| 288 | basic | 0.4969 | 0.64 / 0.79 | −1.02 | 2,251 | 1.20 ± 1.42 | 0.16 | 0.500 |
| 288 | external | 0.4819 | −1.48 / −1.67 | −2.25 | 1,093 | −5.90 ± 3.09 | −9.08 | 1.000 |
| 288 | both | 0.4850 | −0.98 / −1.11 | −1.75 | 1,124 | −3.88 ± 3.32 | −7.02 | 0.995 |

- **Sample sizes:** H = 48: 168,211 labels, effective n 4,696. H = 288:
  168,124 labels, effective n 852.
- **AUC(both) − AUC(basic):** H = 48: −0.0206 ± 0.0068. H = 288:
  −0.0119 ± 0.0143.

## IC screen (Spearman vs realised label return, t on effective n; all 26 reported, none dropped)
- **H = 48:** 2 of 26 have |t| ≥ 2: `opt_netcall_4h` (IC −0.044, t −3.00)
  and `dvol_z30d` (IC +0.032, t +2.22). Next: `opt_netcall_1d` −1.82,
  `basis_okx_chg_4h` +1.64, `opt_skew_4h` −1.45.
  - About 1.2 of 26 are expected at |t| ≥ 2 by chance.
  - `opt_netcall_4h` at t = −3.0 is the one feature worth noting (a
    contrarian options-flow signal). One marginal univariate signal did
    not survive into the model: the external model is at chance, and it
    drags the combined one down.
- **H = 288:** none with |t| ≥ 2. The largest is `ivrv_1d` at −1.44.

## Reading
1. **As a model input set, the external data failed. One options-flow
   feature carries a real-looking signal, but mostly one we already
   had.** From the reviewer, pre-OOS diagnostics run after the fact:
   - **`opt_netcall_4h` alone reaches AUC 0.539**, with the same sign in
     all 5 folds, almost the basic model's 0.541. The pre-registered
     26-feature external model, by contrast, is at chance (0.498).
   - **It largely repeats p01's 4 h reversal:** its correlation with
     `ret_48` is 0.39. Option traders buy calls after rallies and puts
     after sell-offs. Added to the basic set after the fact, it gains
     only **+0.005 AUC**, half the gate. The kill stands, and this is not
     a claim.
   - **Why the full external set fails:** a classifier asked which CV fold
     a row comes from gets **99.8%** right from the external features, vs
     47% from the basic ones. The raw levels (DVOL, basis, funding, ATM
     IV) identify the regime, and the model's base rate goes wrong on
     held-out regimes. That is the p10 failure again; its review had
     already recommended regime-normalised features, and this
     pre-registered set did not use them.
2. **The basic features are still the only signal:** AUC 0.541, gross SR
   2.15, shift-null p 0.015 at H = 48. Consistent with p03 (the 4 h
   horizon helped) and with p10b (cost is the wall). The breakeven of
   2.85 bps, or 2.45 without the long drift, is still **below the 3.38 bps
   maker cost** and far below the 4 bps gate.
3. **Liquidations**, the one requested family with a plausible mechanical
   link to short-horizon moves, were **not tested**. No free history
   exists for the window.
4. **Weaker parts of the specification** (non-blocking, from the
   reviewer):
   - Binance and Bybit funding enter as the last *settled* rate, up to
     8 h old, while Deribit's is ≤ 1 h old. The funding-difference
     features partly measure that staleness gap, not venue disagreement.
   - Option flow is counted in contracts, not premium or delta.

## Review
REVIEW.md: **ACCEPT WITH FIXES.** The kill is valid on both conditions.
The reviewer recomputed 14 features by hand at 7 bar closes (≤ 1e-14)
and checked the publication lags against the data itself (e.g. DVOL's
candle-open stamp). It found no bug that could hide a signal. Its
wording fixes are applied above: the options-flow nuance, the regime
diagnosis, and the weaker spec points. The CLAUDE.md note is corrected
to match.

## Closure
Per PLAN.md and the owner's instruction, this kill closes **the 1 h / 4 h
BTC bar-direction line permanently** (p01–p05, p10, p10b, p11). The note is
added to CLAUDE.md. Next in the queue: **p12**, the RTDS settlement check
on the new collector feed, from ≥ 7 days after 2026-09-24.

## Files
- `PLAN.md` (+ amendment 1)
- `AVAILABILITY.md`
- `backfill.py`, `features.py`, `selection.py`, `selection.log`
- `selection.json`, `selection_trials.json` (52 IC rows + 6 model rows)
- Local, gitignored: `data/collector/p11/` (option trades 538 MB, DVOL,
  funding, Bybit/OKX candles), `preds_selection_H*.parquet`

Reproduce (repo root):
1. `python research/p11_external_signals/backfill.py opt|bybit|okx`
2. `python research/p11_external_signals/backfill.py deribit_www OUT`, on
   a host that reaches www.deribit.com
3. `PYTHONPATH=.:research/p11_external_signals python research/p11_external_signals/selection.py` (~2 min)
