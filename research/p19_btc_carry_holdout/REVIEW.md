# Review: p19_btc_carry_holdout (pre-OOS; holdout not read by the reviewer)
**Decision:** ACCEPT WITH FIXES. The spec is frozen and identical to p18 book B for BTC. The fixes are small and must
be committed before the single run: save the daily series, log the trial before writing the guard file, and add
four sentences to PLAN. After them, run once (command at the bottom).
**One line:** p19 is a fair one-look test of the question "does BTC HL funding on survivable capital beat 6%/yr in
2026?". In practice the pass is decided by kill 1 alone, and at a true 6%/yr the test is a coin flip, so a pass does
not show an edge above the bar.

## What I checked, and found clean
- **Spec = p18 book B, BTC.** I reproduced p18 independently from dev-only data (funding read with a pyarrow
  `time < 2026-01-12` filter). Dev comes out at 12.862, 2024 at 18.230 and 2025 at 7.762 %/yr on capital, matching
  `dev_reference.json` to every printed digit.
  - Funding sign, day sums, basis term −(r_HL − r_spot), reset cost (5 / 10.5 bps × |r|), entry and exit
    (15.5 bps each), capital 1/L + 1, and ×365 on the mean are all the same as p18 `coin()` for B.
  - L = 3.894 is p18's 3.89450 rounded. Capital is 1.256805 against 1.256773, which moves 2025 by 0.0002 pt.
    Immaterial.
- **Frozen items.** These are all fixed in code and PLAN, and I found no free choice left in them:
  - book, L, capital, costs;
  - span [2026-01-12, 2026-09-27), which is 258 days and 9 calendar months: Jan has 20 days and Sep 26, and both
    partial months are counted;
  - the kill thresholds, NW lags (30), the day convention (UTC; candles open at 00:00) and the entry/exit days.
- **Kills in code = PLAN.**
  - k1: `ann < 6`.
  - k2: `not (t >= 2)` on calendar-month sums, so a NaN counts as a fail.
  - k3: fails if mean 5d ≤ 0 or −min/mean > 12. The rolling 5-day windows stay inside the span.
  - k4: HL high / previous HL close − 1 > 1/3.894 − 0.05 = 20.68%. Day 1 uses the 01-11 close.
- **Holdout code path.**
  - Candles are fetched only for [2026-01-11, 2026-09-27 − 1 ms], then cut again to `< span end`.
  - Funding is cut to [span start, span end) before the resample.
  - `holdout.json` existing aborts the run. The guard runs before any computation.
  - Exactly one `TrialLog("trials_hl.json").log` row is written. Its series is the daily return on capital
    (`pnl / CAPITAL`, n = 258). `trials_hl.json` does not exist yet, so this is trial #1 of the HL line.
- **Dev path and holdout rows.**
  - `hl_ohlc_BTC.parquet` and `bn_spot_ohlc_BTC.parquet` end at 2026-01-11 (parquet statistics).
  - `hl_funding_BTC.parquet` runs to 2026-09-28 15:00. The dev path loads the whole file into memory and cuts it
    *before* the resample, so nothing is computed on holdout rows. This is the same pattern the p18 review accepted.
  - The p19 commits contain no holdout artefact.
- **Holdout funding completeness, inferred from counts only.** The file has 24,039 rows (p14 `fetch.log`). Dev has
  17,807 rows, which is 742 × 24 − 1: one 23-hour day, 2024-08-15. That leaves 6,232 rows at or after the dev end,
  and 258 × 24 + 40 = 6,232 exactly. So the holdout has no missing hours, assuming no duplicates. The
  `fillna(0)` for missing funding is therefore moot, and it would be conservative anyway.
- **Harness.** `harness/` is untouched and no threshold was changed. The 6% bar and the tail and t rules are
  p18's static rule unchanged.

## Blocking issues (fix, commit, then run; none of them changes the spec)
1. **The single run saves no daily series, and it writes the guard before the log.**
   - `holdout.json` holds only summaries. RESULTS will need the monthly P&L table, the decomposition by month and
     the worst days. Getting them would mean calling `book(HOLD, True)` again after the look, which is messy and
     cannot be distinguished from a re-run.
   - If `TrialLog.log` raises after `holdout.json` is written, the holdout is spent and unlogged, and the guard
     then forbids a re-run.
   - Fix: compute `book(HOLD, True)` once. Write `holdout_daily.parquet` with columns pnl, fund, basis, reset, up
     and r = pnl/CAPITAL. Log the trial. Only then write `holdout.json`.
   - Also assert that each candle frame has exactly 259 rows (the pre-day plus 258 days) before any P&L is
     computed. At present a missing 01-11 candle silently sets day 1's return to 0.
2. **PLAN must state these before the run (wording only):**
   - **Two post-hoc choices, both disclosed.**
     - (i) The coin, BTC. It was chosen after seeing p18's per-coin table.
     - (ii) The book, B over A. This one is weaker as a post-hoc choice: p18 PLAN rule 4 had already ranked B ahead
       of A ("same for A if A passes and B does not"), and B was the *lower* dev number (2025: 7.76 vs 8.87; 2024:
       18.2 vs 20.4). So it was not return-chasing.
     - The holdout is fresh data, so these choices do not bias it. They do mean a pass is evidence for "BTC B", not
       for carry in general.
   - **What a pass triggers.** p18's review made "the owner would actually deploy capital on a pass" a condition.
     PLAN records only the reversal. Write down the action on a pass, e.g. "a forward paper run with measured HL
     spread and transfer times before any capital", and the action on a fail: BTC carry is closed with no further
     variants.
   - **Abort rule.** If a fetch fails or a candle assert fires, nothing has been computed or printed. Delete the
     `*_holdout.parquet` caches and repeat the identical command. That is not a second look. Any code change after
     `holdout.json` exists is forbidden.
   - **validation_report does not apply** (CLAUDE.md rule 8). There is no model, no labels and no positions from a
     signal, so its permutation and shift nulls are undefined for an always-on book. Its substitute:
     - the NW s.e. of the annual return;
     - PSR against the bar, i.e. with sr* = (6/36500)/σ_daily, rather than against 0. A yield book's Sharpe against
       zero is about 10 and meaningless;
     - DSR with n_trials = 1, which equals PSR(0).
     State this so RESULTS does not claim a verdict block that was never produced.

## Non-blocking issues
- **Knowledge contamination.** The holdout is code-unread but not market-unknown:
  - the owner lived through 2026;
  - p13's dev (HL BTC books and liquidations, 2026-01 → 06-11) and p12's 2026-09-24 snapshot fall inside it;
  - p14's `run.py` and `static.py` ran position logic over holdout rows in memory, with nothing printed.
  None of these computed this book's P&L. RESULTS should say "code-unread" rather than "unseen".
- **The bar is fixed at 6% = 2025 T-bill + 2.** If 2026 T-bills averaged lower, the economic bar is lower. Do not
  re-base it now, but report the average T-bill yield over the span next to the result.
- The funding coverage check is inferred from counts. A per-day `count ≥ 23` assert would make it explicit. Optional.
- Liquidation uses HL last-trade highs and a 5% maintenance margin. HL's actual BTC maintenance margin is about
  1.25% and liquidation runs on the mark price, so k4 is conservative. That is fine.
- Not modelled: USDT (Binance) vs USDC (HL) drift, which sits inside the "basis" term; daily cross-venue transfers;
  exchange default. These were disclosed in p18 and should be repeated in RESULTS.
- The `*_holdout.parquet` candle caches in the research folder are not gitignored. Commit them (small, public data)
  or ignore them, but decide before the run.

## Statistical power: what a pass or fail means
- 258 days = 0.71 yr.
- The s.e. of the annual return on capital (NW, 30 lags), scaled from dev to 258 days, is **1.16 %/yr** if 2026 has
  2025's dynamics and **4.1 %/yr** with 2024's. PLAN's "1.2–1.8" is the calm end.
- Block bootstrap: 30-day blocks, 258 days, 3–4k draws, the series rescaled to a true mean μ.

  | true μ (%/yr on capital) | 2025 dynamics | 2024 dynamics, scaled | 2024 dynamics, shifted (pessimistic) |
  |---:|---:|---:|---:|
  | 4 | 0.00–0.04 | 0.02 | 0.12 |
  | 6 | **0.45** | 0.44 | 0.26 |
  | 7.8 (BTC B 2025) | **0.93** | 0.81 | 0.45 |
  | 10 | 1.00 | 0.98 | 0.72 |

- **k1 decides almost everything.**
  - k2 (monthly t ≥ 2) binds only in the additive-2024 case, where shifting a high-variance year down to a low mean
    manufactures negative months.
  - k3 and k4 practically never bind: the worst dev HL up-day was 13.8% against a 20.7% threshold, and the dev
    tail ratio was 0.4–1.1 against 12.
- **Reading.**
  - The test is "is the 2026 point estimate at least 6", not "is it significantly above 6". To be about 2 s.e.
    above 6, the estimate needs to be ≥ **8.3** under 2025-like noise.
  - A pass at 6–8.3 means "consistent with a carry at or slightly above the bar".
  - A fail below about 4.8 (6 − 1 s.e.) is informative. A fail at 5–6 means "at the bar, not above it", and it
    still closes the line as registered.
- Dev context: every rolling 258-day window in dev earned 7.5–18.6. The mean fell from 18.2 (2024) to 7.8 (2025).
  So a 2026 level below 6 would just continue the trend. It would not be an anomaly.

## What the evidence supports (pre-run)
- The frozen code reproduces p18 BTC B: dev 12.86 ± 2.06, 2024 18.23 ± 3.46, 2025 7.76 ± 0.98 (%/yr on capital, NW).
  On notional in 2025, HL funding contributes +10.63, basis +0.01 and reset −0.89.
- The holdout is the only fresh evidence. Spending it here is legitimate: the owner reversed the closure in
  writing, and the carry line has no competing claimant for it.

## Proposed next experiment
None inside carry. Whatever the result, p19 ends the carry line:
- on a fail, BTC carry is closed and no variants are allowed (other coins, book A, maker fees, other hedge venues);
- on a pass, the next step is an operational forward test, not research: a paper book with measured HL spread,
  measured transfer delays and measured USDC/USDT drift, 3 months, 0 trials, kill if realised < 6%/yr or any
  transfer takes longer than 1 day.

After that, stop opening crypto lines. Do the ROADMAP §9 write-up for p01–p19 (0 trials). The p18 review's
Polymarket favourite–longshot study stays the only parked idea with an external prior.

## Exact command (once, after fixes 1–2 are committed and the owner says "go")
```
python research/p19_btc_carry_holdout/run.py --holdout 2>&1 | tee research/p19_btc_carry_holdout/holdout.log
```
Then commit `holdout.json`, `holdout.log`, `holdout_daily.parquet`, `trials_hl.json` and RESULTS.md, and do not edit
run.py afterwards.

---

## Final review (post-OOS)
**Decision on the write-up:** ACCEPT WITH FIXES. The fixes are wording only. Every number is verified, the run
followed PLAN, and the FAIL is robust. No code changes, no re-run.
**One line:** on the code-unread 2026 span, frozen BTC carry earned 2.73 ± 0.90 %/yr on capital, which is below
the 6% bar (NW z −3.6) and also below 3-month T-bills (3.67% average). Even the gross funding alone, with zero costs
and zero basis, is 4.81 / 1.2568 = 3.83 %/yr on capital. So the failure comes from the income, not the costs.

### (a) Procedure: clean
- `git diff ff73d53 HEAD -- run.py` is empty, so run.py did not change between the reviewed version and the run.
  The run commit fc58eeb adds only the outputs and `trials_hl.json`.
- The trial was logged at 17:38:03, 64 s after ff73d53. `holdout.log` is just the JSON print: no traceback and no
  sign of an aborted earlier attempt.
- `trials_hl.json` is a new file with exactly 1 entry.
  - n = 258 and sr_per_period = 0.29419. I recomputed mean/std(ddof=1) of `ret_capital` = pnl/1.2568 and got
    exactly that, so the logged series is the daily return on capital.
  - DSR with n_trials = 1 is correct.
- The guard was written after the log, as the review fix required.

### (b) Numbers: exact match
I recomputed from the two candle caches plus `hl_funding_BTC.parquet` cut to [01-12, 09-27). This is independent
code, not `run.py`:
- the daily series matches `holdout_daily.parquet` with max |diff| = 0.0;
- ann 2.72697, NW(30) 0.90426, monthly t 2.72718, tail 2.3482, max up-move 13.976% (2026-02-06), worst day
  −0.1198% (09-26);
- decomposition +4.807 / +0.006 / −0.947;
- the monthly table: all 9 rows to 2 dp.

The FAIL does not depend on the choices that were fixed in advance:
- NW s.e. is 0.63 / 0.67 / 0.90 / 1.16 at 5 / 10 / 30 / 60 lags. Even at 60 lags, 2.73 sits 2.8 s.e. below 6.
- Without the entry and exit costs the return is 3.08.

### (c) Data integrity: clean
- Both candle frames have 259 rows (2026-01-11 → 2026-09-26), with 0 duplicates and 0 gaps. The assert held.
- Funding in the span: 6,192 rows = 258 × 24, with exactly 24 per day, 0 duplicates, first 01-12 00:00:00.053 and
  last 09-26 23:00:00.010. This agrees with the pre-OOS count (6,232 = 6,192 + 40 rows on 09-27/28, which were
  excluded). `fillna(0)` was a no-op.

### (d) Wording fixes to RESULTS.md (non-blocking; apply, no numbers change)
1. **T-bill: the number is missing, and "roughly T-bill level" overclaims.** The pre-OOS review asked for the span's
   T-bill average to be reported next to the result.
   - FRED DTB3 over 2026-01-12 → 09-25: mean **3.67%** (179 obs, range 3.56–4.08).
   - The book earned 0.94 pt/yr *less* than T-bills (z −1.0), so its excess return over cash is zero to negative.
   - Re-basing the bar to 2026 T-bill + 2 = 5.67 would not change the verdict (z −3.3).
   - Market reasoning: the capital sits in USDT/USDC earning nothing. The alternative is a T-bill with no exchange,
     stablecoin or transfer risk. A carry book has to beat that, not zero.
2. **"significantly positive (DSR vs 0 ≈ 1.0) and significantly below the bar (PSR ≈ 0)".**
   - PSR and DSR treat the daily returns as i.i.d. The NW s.e. is 1.57× the i.i.d. s.e. (0.90 vs 0.58), so
     1.5e-7 and 0.99999 overstate the certainty. Quote the NW z-scores next to them: +3.0 vs 0, −3.6 vs 6.
   - Qualify "positive": it is gross of the unmodelled items and of the cost of capital, and against T-bills it is
     not positive.
3. **Line 3: "read by code for the first time in this run"** contradicts the last bullet. p14's run/static scripts,
   and p19's own dev path, loaded the holdout funding rows into memory. Write "this book's P&L computed on it for
   the first time".
4. **"It recovered in Jul–Sep 2026 (5–7%/yr on capital)".** The table shows 4.85–7.09. Jul–Sep combined is
   **5.89** (6.4 without the exit cost), which is at the bar, not above it. Say that.
   - The bar needs HL BTC funding of about **8.5%/yr on notional** (6 × 1.2568 + 0.95 reset).
   - 2026 averaged 4.8. It cleared 8.5 only in Jul (9.5) and Sep (9.0).
5. **Table footnote.**
   - Jan includes the 15.5 bps entry cost, about 2.2 %/yr over 20 days, so Jan without it is about 3.8.
   - Sep includes the exit cost, about 1.7 %/yr over 26 days, so Sep without it is about 6.6.
6. **"tiny tails (worst day −0.12% of capital)".** That day, 09-26, is the exit day, and it is mostly the 0.123%
   exit cost. The worst ordinary day was −0.068% (08-21). The tail claim gets stronger, but the attribution should
   be correct.
7. **"24.1 → 10.6 → 4.8".** Label 2026 as a partial year (01-12 → 09-26).
   - "The holdout continued it rather than reverting" holds for the average.
   - The path inside the span was a V: −0.85 in Apr, 9.5 in Jul. The following sentence already covers this, so
     it is fine.

What is correct and should stay:
- the verdict line;
- "carry is closed, with no variants";
- the kill 2–4 passes;
- "a description, not a signal";
- the code-unread vs market-unknown caveat;
- the unmodelled-costs list.

### What the evidence supports
- The mechanics worked. The book stayed delta-neutral: basis was +0.006 %/yr on notional, and monthly basis ranged
  from −0.56 to +0.74. There was no liquidation (max 14.0% against 20.7%), and tails were negligible.
- The income did not. HL BTC funding averaged 4.8 %/yr on notional, which is 3.8 %/yr on survivable capital. That is
  below the risk-free rate before any cost.
- The funding level is regime-driven. Perp funding is what leveraged longs pay to shorts, and it is high when
  speculative long demand is high (2024). The book has no skill component that could offset a low-demand year.
- Across p14 → p18 → p19 the carry line fell 24 → 11 → 5 %/yr on notional. It is closed by three pre-registered
  decisions, and the holdout is spent.

### Recommendation: what the owner should do next
1. **Stop opening lines. Do the ROADMAP §9 write-up now (0 trials).**
   - Extend it to p01–p19: one table, with the kill that fired and the trial counts from both logs.
   - The durable findings are:
     - the harness killed every idea at its pre-registered bar, including the one idea that reached a holdout;
     - retail-cost bar-direction prediction needs AUC ≈ 0.56–0.59, against a best of 0.54 (p10b);
     - "structural" edges (carry, VRP, maker rebates, longshot gaps) were either regime-decayed or sub-cost at small
       size (p14–p19).
   - p19 is a good closing exhibit: a clean one-look holdout whose failure has a stated economic cause.
2. **Do not revisit HL carry because funding recovered in Jul–Sep.** Any future look needs a new PLAN, data after
   2026-09-27 that nobody has read, a bar re-based to T-bill + 2, and the owner's written reversal. With the 2026
   data it would be a coin flip again.
3. **If the owner wants one more research line after the write-up,** the only parked idea with an external prior
   and free historical data is the **non-crypto Polymarket favourite–longshot bias** (ROADMAP §10; the arXiv
   2609.12878 study). It is distinct from p15 (crypto longshot vs Deribit) and p17 (5m BTC maker).
   - Hypothesis: on resolved sports/politics markets, contracts priced ≤ 10¢ resolve YES less often than their
     price, by more than the fee plus half-spread.
   - Design: a single calibration study on resolved markets, split by resolution date (dev before a fixed date,
     holdout after it).
   - Kill fixed in advance: abandon if the dev calibration gap at ≤ 10¢, net of the measured spread and the
     on-chain fee, is below 1¢ per share or has t < 2 with market-clustered s.e.
   - Cost: 1 trial, and data from the Gamma/CLOB history.
   - Otherwise, **stopping is a legitimate result.** The harness's job was to be able to say "there is nothing
     here", and it has said so 19 times with the bookkeeping intact.
