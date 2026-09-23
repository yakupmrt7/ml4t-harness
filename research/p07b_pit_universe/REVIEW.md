# Review: p07b_pit_universe

**Decision:** ACCEPT WITH FIXES. The verdict, FAIL ON THE GATE, is correct and robust. Three RESULTS.md passages overclaim and must be reworded before commit. No OOS trial, now or later, for the p06 momentum book.
**One line:** On a universe knowable in 2020-09, p06's 3v3 28d/skip-1 momentum book earns SR +0.66 ± 0.74 (t 0.89) on 2020-10 → 2022-07, versus 2.67 on p07's hindsight universe. Pooled with the p06 window it is +0.76 ± 0.53, t 1.43, breakeven 20.7 ± 14.5 bps. That is below the underpowered band. The daily cross-sectional line has now failed twice (p06, p07b). p07 was void.

Verification done by this review (not taken from the report):
- **Universe.** I recomputed the 2020-09 quote volume from the 43 ranking zips on disk. Every sha256 matches `universe.json`. My top 15 is identical to the script's, in the same order (#16–18: BAND, LEND, XTZ). I checked listing against the archive with HEAD requests. CRV, BAL, TRB, SUSHI, SOL, UNI, RUNE, EGLD, ICX, STORJ, BLZ and SRM have no 2020-08 monthly file (first bars are 2020-09-01 → 09-18), so the "listed by 2020-08" rule excludes them correctly. LEND, DEFI and ETC do have 2020-08 files and are in the 43. `universe.py` reads only listing plus quote volume. **No returns are used.** The date-shifted rule matches PLAN.md and p04 exactly.
  - Market note: the one-month listing lag drops SUSHI (4.1e9) and UNI (5.1e9), which would have ranked #4–5 on September volume. So the point-in-time (PIT) universe is weighted towards 2017-era large caps (EOS, NEO, OMG, LTC, BCH). This is mechanical and correct. It is also part of *why* the result is weak (see below).
- **Hole fill.** I rebuilt each series from the raw monthly zips with my own reader, then added only the bars that the daily zips supply at missing timestamps. For TRX, YFI, XRP, LTC and OMG: 1,440 missing bars each, 1,440 daily bars, **0 overlap with monthly bars** (nothing overwritten), 0 still missing. All 15 `data/bars/p07b` caches equal my reconstruction exactly (index and closes). The daily files are sha256-checked in `fetch_daily` before writing.
- **Monkeypatch.** `p07.run_window` reads the module global `UNIVERSE` at call time for the factor panel, the targets and `n_live`. The market/beta series is built from the `closes` dict passed in, which holds only the p07b names in the new window. `p07.load` also reads the global, and it is reset to p04's list before the p06 window is loaded. Evidence that it works:
  - The p06 window reproduces p06/p07 bit for bit (0.9511, t 1.2286, 21.0 ± 17.1, p 0.087).
  - The new window shows `n_live` = 15/15/15.
  - My independent book on the 15 p07b names reproduces the price-only SR exactly with the same 5m-sum arithmetic (below).
- **Causality.** The factor is close(t−24h)/close(t−28d), entry is the 04:05 close (delay 1), and funding is settled rates charged at the first bar at or after settlement. The 5-point truncation assert passes. I found no issue.
- **Independent book** (own code, no harness, 669 days):
  | accounting | price-only SR | gross SR | breakeven | 2020-Q4 / 2021 / 2022 |
  |---|---:|---:|---:|---|
  | 5m bar returns summed at constant notional (harness arithmetic) | 0.656 | — | 20.5 bps (price) | 3.82 / 0.35 / −0.75 |
  | hold fixed units 04:05 → 04:05 (what the book actually does) | 0.488 | **0.455** | **14.4 bps** | 3.80 / 0.00 / −0.85 |

  The script's 0.66 / 20.4 are reproduced. The 0.17-SR gap is accounting, not a bug. The harness credits a position rebalanced to constant notional every 5 minutes at no cost, and on crash-and-rebound days that differs a lot from holding units. **One day, 2021-05-19 (the −30% intraday crash), accounts for 0.39 of the 0.72-unit gap.** In p06 the gap went the other way (1.11 vs 0.99), so it is path noise, not a consistent bias. It does mean the breakeven in the new window is **14–20 bps depending on accounting**, not "≈ 20".
- **Further (daily-hold):**
  - Net SR at 12 bps: 0.08.
  - Without the 10 best days, SR is **−0.77**.
  - Long leg +5.5 units, short leg −3.4 units (a bull market, so this is the expected split and not evidence of anything). Beta −0.10.
  - Per-asset P&L: DOT +1.6, BTC +1.3, TRX +1.3, ETH +1.2 | YFI −1.8, EOS −1.5.
- **PIT vs hindsight, paired** (same 657 days, daily-hold, price-only): 0.56 vs 2.54, ρ = 0.35. **Difference 1.98 ± 0.85** (≈ 2.3 s.e.).
- `git diff HEAD -- harness research/p04* research/p06* research/p07*` is empty, so no tests or selftest were owed. `trials.json` is untouched (3 rows). `selection_trials.json` has exactly 1 row.

## Blocking issues (RESULTS.md wording; the logged numbers and the verdict stay as they are)
1. **"On universes chosen point-in-time, the two windows now agree … a consistent, modest number."** Two estimates with s.e. ≈ 0.75 each "agree" with almost anything. The difference is 0.30 ± 1.07, and both are also within 1.3 s.e. of zero. The per-period SRs span −2.9 to +4.0. Replace with: "The two point estimates (0.66, 0.95) are not distinguishable from each other or from zero."
2. **Breadth diagnostic reading: "It is the only evidence here on whether breadth helps, and it helps a little."** This has two problems. (a) This is not breadth. It is the same 15 names, rank-weighted instead of top/bottom 3. (b) The two books are highly correlated. Pooled t moves 1.43 → 1.61, but in opposite directions per window (new 0.66 → 0.99, p06 0.95 → 0.69). That is noise. Replace with: "Rank-weighting the same 15 names changes pooled t from 1.43 to 1.61, in opposite directions in the two windows. It says nothing about breadth." Also state that 1.61 on an untested diagnostic does **not** move the verdict into the underpowered band. The current text half-says this. Make it explicit.
3. **Disclose the accounting sensitivity** next to the table: with daily-hold arithmetic the new window is SR 0.46 and breakeven 14.4 bps, and one day (2021-05-19) drives most of the gap. This affects the "breakeven ≈ 20 bps in both windows" sentence. Add one line; do not re-log anything. The verdict is unaffected: the kill still does not fire (14.4 ≥ 12, SR > 0), and the gate misses by more.

## Non-blocking issues
- **"The hindsight universe was worth about 2 units of Sharpe."** The paired estimate supports this: 1.98 ± 0.85. Quote the s.e. The universes differ in 9 names, so it is "universe choice worth ~2 SR", and the causal story (survivorship) is the likely reading, not a proven one. Soften the follow-on "the survivor subsets were themselves still biased upward". That is plausible, but the 6-name 2v2 subset is a different book, so the gap (1.47 vs 0.66) mixes bias with book design.
- **"SR is somewhere in 0.2–1.3 (±1 s.e.)"** is correct as a ±1 s.e. band. Say that it is a 68% band. The 95% band is −0.3 to 1.8.
- **Run history.** `RESULTS.md` was last written at 14:35:31. The logged run finished at 14:37:49 (163 s, so it started around 14:35:06, which is also the mtime of `selection.py`). So RESULTS.md was drafted from run 1's printed output, and "Run 2 … gives the same numbers" was written before run 2 had finished. I checked `selection.log` against every number in RESULTS.md and they match, so the statement is true. For the record: the mtimes imply run 1 took ≤ 58 s (between cache build at 14:34:08 and the edit at 14:35:06), while run 2 took 163 s. That is plausible with the p08 session competing for CPU, but it is not verifiable. Add wall-clock start and end times to the Runs section.
  - **Acceptability:** yes. Same config, zero free parameters, and the only code change was `bool()` casts in the output dict, after all numbers were computed. Under CLAUDE.md an identical config is not a new trial, and one logged row is correct. Logging a second row would have been wrong.
- **Rule 8 (`validation_report`)** was not run. Nothing is claimed, the run is selection-only, and this follows p06/p07 practice. Fine as long as no result is ever claimed from it.
- **Costs.** The flat 12 bps is optimistic for 2020 SXP, OMG and NEO perps (thin books). Any realistic cost pushes net SR ≤ 0. This is moot given the fail.
- **Commit set:** `universe.py`, `universe.json`, `universe_ranking.csv`, `selection.py`, `selection.json`, `selection.log`, `selection_trials.json`, `RESULTS.md`, `REVIEW.md`.

## Selection hygiene
- PLAN.md was committed at 3bc1710 (14:29:17). The first ranking zip is 14:29:42, the first new-symbol kline 14:32, the daily hole files 14:33. The rule, book, costs, kill, gate and underpowered band were fixed before any new data was touched. No choice was made after the output was seen.
- The code imports `KILL_BE, GATE_SR, GATE_T, UNDERPOWERED_T` = 12, 0.5, 2.0, 1.5 from p07 unchanged. The kill, gate and underpowered expressions are identical to p07's, which I reviewed line by line. **Nothing was loosened.** The verdict follows mechanically: not killed (0.66 > 0, 20.4 ≥ 12), no gate (t 1.43 < 2.0; BE − 1 s.e. = 6.2 < 12), not underpowered (1.43 < 1.5) → FAIL ON GATE, exactly as PLAN.md says.
- This is the second look at the 2020-10 → 2022-07 window. It is declared in PLAN.md and in the trial row's `note`. A fail does not need a second-look discount.

## What the evidence supports
- On point-in-time universes of 15 liquid perps, 28d/skip-1 cross-sectional momentum has **no detectable edge** across 3.5 years: pooled SR 0.76 ± 0.53, t 1.43 (NW 1.36). The breakeven is 15–21 bps against a ≥ 12 bps cost that is already optimistic, and the P&L rests on a handful of days (ex-top-10 SR < 0). Beta and funding are small, so this is not a disguised long.
- Most of p07's 2.67 came from the universe: 1.98 ± 0.85 SR. The economic reading: in 2021, crypto "momentum" was mostly the long leg riding **newly listed** coins (SOL, AVAX, MATIC, SAND) through their pumps. A universe fixed in 2020 cannot hold them. A monthly-reconstituted universe could, but it would also buy the ones that pumped and died. That question is untested here, and it was deliberately not allowed after this window was seen.
- It does not show that momentum is zero. It shows that at this breadth and horizon the signal-to-noise is too low to ever clear the gate with ~3.5 years of daily data.

## Proposed next experiment
**Line status.** Daily cross-sectional factors on Binance perps: p06 fail, p07 void, p07b fail. The p06 REVIEW pre-committed to one more try at most (breadth), and then a pivot. I recommend **pivoting now and not running breadth**:
- The only breadth evidence (the rank-demeaned diagnostic) is null (point 2 above).
- Wider universes mean smaller caps, where 12 bps is clearly too cheap and 2020–21 spreads were wider. With a breakeven of 15–21 bps, breadth would need to roughly double SR *after* higher costs.
- Any breadth design would be the third look at 2020–22 and the second at 2022–24, and it would be shaped by this diagnostic.

Park the line. Do not spend the OOS trial on it.

**p09: Polymarket BTC short-horizon markets vs the Binance price, a feasibility and kill study.** This uses the collector data (p08 tables: 1s features and events; ~2 months since 2026-07-25). It is the only data here that is not a public archive everyone has backtested.
- **Market reasoning.** Polymarket's BTC "up/down" markets pay 1 if BTC at expiry (Chainlink-reported) is above the reference price. Their fair value is roughly Φ(ln(S/K)/(σ√τ)), and S is set on Binance/CEXs. If Polymarket's order book updates seconds after Binance moves, a taker can buy stale quotes. The costs are the Polymarket half-spread, the taker fee (read it from the collector's market metadata or the current fee schedule, and do not assume 0), and Chainlink-vs-Binance basis at resolution.
- **Hypothesis (falsifiable).** For BTC up/down markets, the move in Binance-implied fair probability over the last k seconds (k ∈ {1, 2, 5, 10}) predicts the next-k-second change in Polymarket mid with a slope > 0. At the best k, the predictable part of the move exceeds half-spread + taker fee on at least 20% of signal events. Falsified otherwise.
- **Exact change.** New data source and new market, so this is not a one-variable change from p07b. That is deliberate: it is the pivot.
- **Pre-OOS selection plan.**
  - Split by calendar: the first 60% of collector days is selection, the last 40% is untouched OOS.
  - On selection days only: first verify timestamp semantics (event vs receive time per stream, clock offset between the Polymarket and Binance receive paths, using `time_source` and the p08 receive-lag percentiles). Then measure the lead-lag cross-correlation and choose k and the σ estimator (trailing only).
  - Log each configuration looked at in `research/p09_*/selection_trials.json`.
  - The OOS test is a single rule (threshold on predicted edge minus costs, taker, delay ≥ 1 event), logged once in `trials.json` with DSR.
- **Kill criteria (fixed in advance).**
  - Abandon if, on selection days, at the best k the median |predicted mid move| on the top-decile signal events is < half-spread + fee.
  - Abandon if the lead-lag peak is at ≤ the measured receive-latency difference between the two feeds (then it is a clock artefact, not an edge).
  - Abandon if fewer than 500 independent signal events exist in the selection period (too little data; wait for more collector days instead of testing).
- **Expected cost:** 0 OOS trials for the feasibility part, and 1 OOS trial only if both kills pass. Compute: reading ~40 days of 1s Polymarket + Binance futures tables from GCS, minutes per day. The main risk is timestamp semantics, which must be settled before any number is looked at.
