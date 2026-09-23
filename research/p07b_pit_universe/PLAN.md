# p07b p06's momentum book on a point-in-time universe, 2020-10 → 2022-07

Written 2026-09-23, before any kline of a new symbol was downloaded,
including the 2020-09 ranking files. It follows
research/p07_momentum_replication/REVIEW.md, "Proposed next experiment".
Nothing below changes after numbers are seen.

## Two caveats, stated first
1. **The window is no longer untouched.** p07 ran this exact book on
   2020-10 → 2022-07 (SR 2.67, on a universe ranked with hindsight). p07's
   reviewer then ran subset diagnostics on it: 9 pre-listed names gave 1.92,
   and the 6 names shared with the 2020-09 ranking gave 1.47. It also
   computed the expected 2020-09 membership from volume. This is the
   **second look** at the window.
2. **p07b is a de-biased re-estimate, not a pristine replication.** What
   keeps it honest is that the rule is fixed mechanically here, before its
   output is seen. p07's row stays in `selection_trials.json`, and p07b adds
   a second row. A gate pass here is read knowing it is the second look.

## Hypothesis (falsifiable)
p06's 3v3 28d/skip-1 momentum book, on a universe chosen by p04's rule
**as of the month before the window**, has gross SR > 0 and breakeven
≥ 12 bps on 2020-10-01 → 2022-07-31. Falsified if SR ≤ 0 or breakeven < 12.

## Single change vs p07: the universe DATE
p04's rule (`research/p04_multiasset/universe.py`) is applied unchanged,
with its dates moved from (listed by 2022-06, ranked on 2022-07) to
**(listed by 2020-08, ranked on 2020-09)**:
1. Every USD-M symbol archived on data.binance.vision (S3 listing, which
   keeps delisted symbols). Perpetuals only: no `_YYMMDD` suffix.
2. **Eligible: a monthly 5m kline file exists for 2020-08.**
3. **Rank by total quote volume over 2020-09** (monthly 5m file,
   sha256-checked against the archive's .CHECKSUM).
4. Exclude stablecoin-vs-stablecoin pairs. Keep one contract per underlying
   (the highest-volume one). Take the top 15. BTCUSDT must be in it.
5. Delisting: the last bar with trade count > 0 in the downloaded 5m
   klines. An asset whose last live bar is before 2022-08-01 04:00 is
   delisted inside the window and handled by the harness (forced flat at
   its last traded close, normal costs, no successor spliced in).

The universe is **static** for the whole window. No monthly
reconstitution. The script re-derives the universe (`universe.py`) and
writes `universe.json` and `universe_ranking.csv`, with the sha256 of every
2020-09 ranking file. Ranking files go to `data/raw/universe_2020-09/`.
Returns are not used anywhere in the selection.

Expected membership, from p07's review (volume only): BTC ETH LINK TRX BNB
YFI DOT BCH XRP EOS SXP LTC ADA NEO OMG. The script's own output is what
counts. If it differs from this list, the difference is reported and the
script's list is used.

Unchanged from p07: the book (p06's `weights`, `daily`, `sr`: 04:00 UTC
decision, delay = 1, top-3 long / bottom-3 short, ±1 unit ($10k),
dollar-neutral), p07's `momentum` and live definition (bars at t − 24h and
t − 28d), ≥ 8 live (days below are flat and dropped), the flat **12 bps**
cost, gross = price + funding, daily bucketing, and the **p06 window**
(2022-08 → 2024-03, p04 universe, p04 caches), recomputed by p07's
unchanged code. Pooled = the p07b new-window daily gross series
concatenated with the p06-window series, as in p07.

## Data
- 5m USD-M klines + settled funding, **2020-01 → 2022-07**, for every
  p07b universe symbol not already on disk (`scripts/download_binance.py`).
- **Pre-registered data fix: archive holes.** p07's review found monthly
  5m files missing 2022-02-26 → 03-01 and 2022-04-01 → 04-03 for some
  symbols. For each p07b symbol, over [its first monthly bar, 2022-08-01
  04:00], every 5m timestamp missing from the monthly files is found. For
  each UTC day that contains one, the **daily** 5m file
  (`futures/um/daily/klines/{SYM}/5m/`, sha256-checked) is downloaded into
  `data/raw/daily_klines/`, and **only the missing bars** are taken from it.
  Monthly bars are never overwritten. Bars filled and bars still missing are
  reported per symbol. This fix is applied to the new window only. The p06
  window stays exactly as in p06/p07, so its numbers reproduce.
- Caches: `data/bars/p07b/{SYM}-5m-2020-01_2022-07.parquet` (filled).

## Pre-OOS report (exactly p07's table, for the p07b universe)
The universe list and ranking, live count over time, days dropped, delistings,
and hole-fill counts. For the new window, the p06 window and pooled: gross SR
± s.e., t, NW(10) t, net SR at 12 bps, price-only SR, breakeven ± s.e.,
turnover, beta to the equal-weight live universe and the beta-hedged SR,
per-period SR with its s.e., and the shift-null p per window. Also p07's
rank-demeaned book, as a **DIAGNOSTIC only**, as in p07.

## What each sample can show
Both windows have ~657 / 609 days, so p07's table applies: SR for t = 2 is
1.48 (new) and 1.55 (p06). Pooled is ≈ 1,266 days, so SR ≈ 1.07 is needed
for t = 2, and ≈ 0.80 for t = 1.5. p07's reviewer diagnostics (1.5–1.9 on
survivor subsets) are the rough prior. With p06's window at 0.95, a
new-window SR of about 1.2 gives a pooled t of about 2.

## Kill criterion (fixed now; same thresholds as p07, not loosened)
- **KILL** the daily cross-sectional momentum line if the p07b new-window
  gross SR ≤ 0 **or** its breakeven < 12 bps.
- **GATE** only if both windows' SR ≥ 0.5 **and** pooled t ≥ 2.0 **and**
  pooled breakeven − 1 s.e. ≥ 12 bps.
- **Underpowered, not dead:** not killed, both SR > 0, 1.5 ≤ pooled t < 2.0.
  STOP and report. Nothing new is planned in this experiment.
- Anything else: STOP, report as a fail on the gate.
- **Stop at the gate either way.** If it GATEs, before any OOS trial:
  rebuild costs for the new window's names (2020 spreads on SXP, OMG, NEO
  may exceed 12 bps), then spend the single OOS trial on the p06 book
  (p04 universe, 2024-04 →), logged in `trials.json` with DSR. That needs
  the owner's "go".
- If p07b fails, it is the daily cross-sectional line's second failure
  (p06, p07b).

Bookkeeping: **one row in `research/p07b_pit_universe/selection_trials.json`**,
whatever the outcome. `trials.json` is not touched.
