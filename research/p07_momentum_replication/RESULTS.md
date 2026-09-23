# p07 does p06's momentum sort replicate on 2020-10 → 2022-07?

**Verdict: gate passes mechanically; NOT credited because the universe is
look-ahead for the new window; OOS not spent; p07b (point-in-time
universe) pre-registered.** The 15-perp universe was ranked on 2022-07
volume, which is the last month of a window ending 2022-07. p07b is in
`research/p07b_pit_universe/`. No OOS run, `trials.json` untouched. One row in
`selection_trials.json`: its `decision` field says "GATE", and this file
overrides that reading. The logged numbers are not edited.

Runs: one unlogged run (`--no-log`), then one logged run of the same
config. Between them the only code change was how p06's module is
imported (via importlib, to avoid a name clash), and the two
`selection.json` outputs are identical. The PLAN edit at 9bd5432 (the
"live" wording, to match p06's frozen momentum code) was made after the
raw zips were downloaded, but before any cache was built or any number
computed. `diagnostics.py` is reporting only and was written after the
first run.

## Numbers (book frozen from p06; gross = price + funding; flat 12 bps for net)

| sample | days | gross SR ± s.e. | t | NW(10) t | net SR @12 | breakeven bps ± s.e. | turnover /yr | beta to EW | β-hedged SR | shift null p |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **new 2020-10 → 2022-07** | 657 | **+2.67 ± 0.75** | 3.58 | 3.34 | +2.41 | **125 ± 35** | 648 | +0.12 | +2.57 | 0.000 |
| p06 2022-08 → 2024-03 | 609 | +0.95 ± 0.77 | 1.23 | 1.26 | +0.41 | 21.0 ± 17.1 | 779 | −0.12 | +0.99 | 0.087 |
| **pooled** | 1,266 | +2.00 ± 0.54 | **3.72** | 3.47 | | **70 ± 19** (−1 s.e. = 51) | 711 | | | |

- The p06 window reproduces p06 exactly: SR 0.951, t 1.229, breakeven
  21.0 ± 17.1, shift-null p 0.087. The 610 → 609 change is the dropped stub.
- New window: 669 decisions. The 12 days before 2020-10-13 had fewer than 8
  live and are dropped. Live count is 8–15 (mean 11.8).
- The shift null is on bar-level price-only gross, like p06's.

Per-period gross SR:

| new window | | | p06 window | | |
|---|---|---|---|---|---|
| 2020-Q4 (80 d) | 2021 (365 d) | 2022-01→07 (212 d) | 2022-08→12 (153 d) | 2023 (365 d) | 2024-Q1 (91 d) |
| +5.69 | +3.38 | +0.26 | +0.24 | +2.07 | −2.89 |

The s.e. of a per-period SR is about 1/√(days/365): 2.1 for 2020-Q4, 1.0 for 2021, 1.3 for 2022-01→07.

## Kill / gate as pre-registered (PLAN.md)
- Kill (new SR ≤ 0 or new breakeven < 12): **not hit** (2.67, 125 bps).
- Gate: both SR ≥ 0.5 (2.67, 0.95) ✓; pooled t ≥ 2 (3.72) ✓; pooled
  breakeven − 1 s.e. ≥ 12 (51) ✓ → **GATE**.

## Why the new-window number cannot be taken at face value
**The 15-perp universe is point-in-time for p06's window but look-ahead for this one.**
p04 ranked perps by **2022-07 quote volume**, which is the *last* month of
the new window. For 2020-10 → 2022-07, the universe is therefore "the
coins that ended up among the most traded in mid-2022". That set is tilted
towards coins that went up a lot in 2021 (SOL, AVAX, MATIC, SAND). Coins that
ran up and then collapsed or faded are missing: LUNA was delisted in 2022-05,
and others such as DOGE, LINK, LTC and FTT had fallen below rank 15 by July.
Momentum goes long the recent winners. Inside a universe picked for being
future winners, "winners keep winning" is partly built in. This is
survivorship bias, and it inflates exactly this factor. p06's REVIEW
specified "same universe" and so did the owner's brief. I ran it as
specified. The bias was not caught at planning time, including by me.

Evidence and sizing (diagnostics.py + REVIEW.md; reviewer diagnostics on an
already-read window, not trials):
- p04's rule applied as of the month *before* the window (listed by
  2020-08, ranked on 2020-09 volume) gives BTC ETH LINK TRX BNB YFI DOT BCH
  XRP EOS SXP LTC ADA NEO OMG. **Only 6 of the 15 overlap** with p07's
  universe.
- 6 of p07's names (MATIC, SAND, UNFI, GMT, APE, OP) had not listed when the
  window began and are in the universe only because they survived to 2022-07.
  They carry 38% of the window's P&L. SAND, AVAX and MATIC alone carry 61%.
  SAND's two Facebook → Meta rename days are 11%.
- On hindsight-free subsets of the same universe (reviewer's
  daily-close implementation, which gives 2.56 for the full book vs the
  script's 2.67):

  | book | SR | t |
  |---|---:|---:|
  | p07 as run, 15 names, 3v3 | 2.56 | 3.44 |
  | the 9 listed before the window, 3v3 | 1.92 | 2.55 |
  | the 6 also in the 2020-09 top 15, 2v2 | 1.47 | 1.97 |

  So **the new-window SR is biased upward by roughly 1 unit**. Even the
  subsets are survivors, since they exclude LINK, YFI, SXP, EOS and the
  like, so the clean value is unknown. It is probably above 0 and well
  below 2.67.
- The bias acts through price paths, not average drift. Only 5 of
  223 bps/day of P&L comes from the ex-post mean return per asset. The
  universe is guaranteed to contain the 2021 pumps momentum rode, and it
  cannot contain coins where momentum bought the top and rode the collapse.

What it is *not* (checked):
- Not a fill or print artifact. delay=2 gives SR 2.65 (vs 2.67). The first bar
  after each 04:00 fill carries −0.8% of P&L. 5m |return| > 20% occurs 0–3
  times per asset (UNFI 10), too rare to matter.
- Not a few days. Without the 10 best days, SR is 1.77. Without the 10 best
  and 10 worst, it is 2.86.
- Not market beta: beta is +0.12 and the hedged SR is 2.57.
- Not causality in the signal: the momentum values at 5 random dates are
  identical when recomputed from data truncated at t.

Data gaps: the monthly archive has holes on 2022-02-26 → 03-01 (SOL, SAND,
UNFI, XRP) and 2022-04-01 → 04-03 (those four plus GMT). The harness sets
the return across a hole to zero and force-closes the position. This only
touches 2022 and cannot change the conclusion. p07b should fill the holes
from the daily files.

## DIAGNOSTIC only (not part of the kill, not the book tested): rank-demeaned, all live assets
| sample | days | gross SR | t | breakeven bps ± s.e. | turnover /yr |
|---|---:|---:|---:|---:|---:|
| new | 657 | +2.82 | 3.78 | 131 ± 35 | 576 |
| p06 | 609 | +0.69 | 0.90 | 15.3 ± 17.1 | 593 |
| pooled | 1,266 | +2.04 | 3.79 | 75 ± 20 | 584 |

Breadth does not add power in the p06 window (0.69 vs 0.95). Over 15
assets, the middle ranks add noise rather than signal there. The
new-window figure has the same universe bias.

## Review
REVIEW.md: ACCEPT WITH FIXES. The gate is mechanically valid and must not be
credited, and the OOS trial must not be spent on it. The fixes above are
applied.

## Reproduce (repo root)
- `for s in <15 symbols>; do python scripts/download_binance.py --symbol $s --interval 5m --start 2020-01 --end 2022-07; done`
- `PYTHONPATH=. python research/p07_momentum_replication/selection.py` (~6 min)
- `PYTHONPATH=.:research/p07_momentum_replication python research/p07_momentum_replication/diagnostics.py`
