# p07b p06's momentum book on a point-in-time universe, 2020-10 → 2022-07

**Verdict: FAIL ON THE GATE. Not killed, and not in the "underpowered" band.**
On a universe knowable in 2020-09, the new window's gross Sharpe is
**+0.66 ± 0.74** (t 0.89), against p07's 2.67 on the hindsight universe.
Pooled with the p06 window, t = **1.43**, below the 1.5 floor of the
underpowered band. Pooled breakeven is **20.7 ± 14.5 bps** (−1 s.e. = 6.2,
under the 12 bps bar). Stopped. No OOS run, `trials.json` untouched. One
row in `selection_trials.json` (the second look at this window, after p07).

Caveats (from PLAN.md): the 2020-10 → 2022-07 window had already been read
by p07 and by p07's reviewer, so this is a de-biased re-estimate, not a
pristine replication. The universe rule was fixed mechanically in PLAN.md
(3bc1710) before any new-symbol data was downloaded.

## Universe (p04's rule, as of 2020-09; `universe.py`, sha256 per ranking file in `universe.json`)
Eligible = a 2020-08 monthly 5m file exists (43 perps). Ranked on 2020-09
quote volume, top 15, one contract per underlying:
**BTC ETH LINK TRX BNB YFI DOT BCH XRP EOS SXP LTC ADA NEO OMG** (all USDT).
This is identical to the list p07's reviewer computed. 6 of the 15 overlap
with p07's universe. All 15 are live on every decision day: no days
dropped, no delistings in the window.

Pre-registered hole fill: TRX, YFI, XRP, LTC and OMG were each missing
1,440 monthly-archive bars (2022-02-26 → 03-01 and 2022-04-01 → 04-03). All
were filled from sha256-checked daily files, with 0 bars still missing. The
other 10 had no holes. All series end at 2022-08-01 00:00 (the last
monthly bar), so the last daily bucket is 20 h. This is the same as in p07.

## Numbers (book frozen from p06; gross = price + funding; flat 12 bps for net)

| sample | universe | days | gross SR ± s.e. | t | NW(10) t | net SR @12 | breakeven bps ± s.e. | turnover /yr | beta | β-hedged SR | shift null p |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **new 2020-10 → 2022-07** | 2020-09 PIT | 669 | **+0.66 ± 0.74** | 0.89 | 0.83 | +0.27 | **20.4 ± 22.9** | 771 | −0.21 | +0.76 | 0.117 |
| p06 2022-08 → 2024-03 | p04 (PIT) | 609 | +0.95 ± 0.77 | 1.23 | 1.26 | +0.41 | 21.0 ± 17.1 | 779 | −0.12 | +0.99 | 0.087 |
| **pooled** | | 1,278 | +0.76 ± 0.53 | **1.43** | 1.36 | | **20.7 ± 14.5** (−1 s.e. = 6.2) | 775 | | | |
| *p07, for reference* | *2022-07 (hindsight)* | *657* | *+2.67* | *3.58* | | | *125 ± 35* | | | | |

The p06 window reproduces p06/p07 exactly (0.951, t 1.229, 21.0 ± 17.1, p 0.087).

Per-period gross SR (s.e. ≈ 1/√years):

| 2020-Q4 (92 d) | 2021 (365 d) | 2022-01→07 (212 d) | 2022-08→12 (153 d) | 2023 (365 d) | 2024-Q1 (91 d) |
|---|---|---|---|---|---|
| +3.96 ± 1.99 | +0.32 ± 1.00 | −0.80 ± 1.31 | +0.24 ± 1.54 | +2.07 ± 1.00 | −2.89 ± 2.00 |

## Kill / gate as pre-registered (PLAN.md, same thresholds as p07)
- Kill (new SR ≤ 0 or new breakeven < 12): **not hit** (SR +0.66,
  breakeven 20.4). Both hold only on the point estimate: breakeven −1 s.e.
  is −2.6 bps.
- Gate: both SR ≥ 0.5 ✓ (0.66, 0.95); pooled t ≥ 2.0 ✗ (1.43); pooled
  breakeven − 1 s.e. ≥ 12 ✗ (6.2) → **no gate**.
- Underpowered band (1.5 ≤ pooled t < 2.0, both SR > 0): ✗ (1.43) → **fail on the gate.**

## What this says
- **The hindsight universe was worth about 2 units of Sharpe in this
  window.** On the same days, the difference is 2.67 − 0.66 = 1.98 ± 0.85:
  the two books' daily P&L has correlation 0.35 (from the reviewer). p07's
  reviewer estimated ~1 from survivor subsets of p07's universe. That
  estimate mixed the universe bias with a different book (fewer names, 2v2),
  so the two are not directly comparable.
- **The two point-in-time windows are not distinguishable from each other,
  and neither is distinguishable from zero.** Their SR difference is
  0.30 ± 1.07, and each is within 1.3 s.e. of 0. Pooled over 3.5 years:
  SR 0.76 ± 0.53, t = 1.43. 68% band 0.2–1.3, **95% band −0.3–1.8**.
  Pooled breakeven is 20.7 ± 14.5 bps against a 12 bps cost. It cannot be
  told apart from zero or from "too thin to trade".
- **Accounting sensitivity (from the reviewer; not the pre-registered
  number):** the harness sums 5m returns, which amounts to rebalancing to
  constant size every 5 minutes at no cost. Holding fixed units from one
  04:05 fill to the next, which is what the book actually does, gives a
  new-window gross SR of **0.46** and a breakeven of **14.4 bps**. The
  2021-05-19 crash day is 0.39 of the 0.72 units of the gap. Under that
  accounting, net SR at 12 bps is 0.08. In p06's window the gap went the
  other way, so it looks like path noise, not a steady bias. The kill still
  does not fire (14.4 ≥ 12). The new-window breakeven is 14–20 bps,
  depending on accounting.
- The 2021 bull market, where the hindsight universe made SR 3.4, gives
  +0.32 on the point-in-time list. 2020-Q4 is strong (+3.96) on both lists,
  over 92 days (s.e. ~2).
- Funding is small again (−5% of gross), and beta is slightly negative.

## DIAGNOSTIC only (not part of the kill, not the book tested): rank-demeaned, all live assets
| sample | days | gross SR | t | breakeven bps ± s.e. | turnover /yr |
|---|---:|---:|---:|---:|---:|
| new (2020-09 PIT) | 669 | +0.99 | 1.34 | 28.9 ± 21.5 | 607 |
| p06 | 609 | +0.69 | 0.90 | 15.3 ± 17.1 | 593 |
| pooled | 1,278 | +0.86 | 1.61 | 22.5 ± 13.9 | 600 |

This book uses the same 15 names with rank weights. It is not a wider
universe, so it does not test breadth in the sense of more assets. It
moves in opposite directions in the two windows: 0.66 → 0.99 in the new
window and 0.95 → 0.69 in p06's. That pattern is noise, not evidence that
rank weights help. Its pooled t of 1.61 is a diagnostic. It does **not**
move the verdict into the underpowered band, because the tested book's t is
1.43.

## Runs
- `universe.py` once. A load-only pass built the caches and hole-fill
  report, computing no returns. It revealed a wrong `delisted_in_window` flag
  (every series ends 4 h before the P&L end), which was fixed in the report
  only. The harness saw no delisting either way.
- `selection.py` run 1 computed every number above, then crashed on
  `json.dumps` of a numpy bool in the kill-check dict, before writing
  `selection.json` or the trial row. Its duration was not recorded, because
  the crash came before the timing print. The fix was `bool(...)` casts
  only.
- Run 2 (logged, `selection.log`, 163 s; caches were warm) is the same
  config. It wrote the one row. The first draft of this file was written
  from run 1's output before run 2 finished. Afterwards, run 2's log was
  diffed against run 1's: every number is identical, and the only
  difference is one blank line.

## Review
REVIEW.md: ACCEPT WITH FIXES. The verdict (fail on the gate) is confirmed. The universe, hole fill, p06-window reproduction and new-window SR were checked independently. The claim fixes above are applied. The reviewer recommends never spending an OOS trial on the p06 momentum book, and pivoting to the collector data (p09 in REVIEW.md).

## Reproduce (repo root)
- `PYTHONPATH=. python research/p07b_pit_universe/universe.py`
- `for s in <15 symbols>; do python scripts/download_binance.py --symbol $s --interval 5m --start 2020-01 --end 2022-07; done`
- `PYTHONPATH=. python research/p07b_pit_universe/selection.py` (~15 min; fetches daily files for holes)
