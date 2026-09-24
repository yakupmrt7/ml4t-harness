# p10b What AUC would a 1 h BTC direction model need to beat costs?

**Verdict: KILL, as pre-registered. The 1 h / 4 h BTC bar-direction line is
closed.**
- **The kill:** with seed 0, the one the plan says decides, a 4 bps
  breakeven needs pooled AUC **0.590** (≥ 0.58).
- **The robustness seeds:** 0.591 (seed 1) and 0.574 (seed 2). Seed 2 falls
  in the 0.56–0.58 band, where the plan says "abandon unless the owner
  funds v2". **Every seed says abandon.** The "closed for good" wording
  rests on the pre-registered seed.
- **Where the best real model stands:** AUC 0.5445. No feature added in
  p01–p10 has raised AUC, and p03's and p10's both lowered it.

**Row zero (sanity check, PLAN amendment 1): PASS, exact.** At k = 0 the
synthetic pipeline reproduces:
- **p10's A-basic/P2 row, under p10's hold rule:** AUC 0.5445495…,
  breakeven 1.5309846975…, turnover 2,965.1369…/yr. Identical to
  `research/p10_orderflow_1h/selection.json` → `results_held` at full
  precision.
- **This curve's base, under the p02-exact hold rule:** breakeven
  1.864324984464265, turnover 3,050/yr.
- The two differ only in how P2 treats the ~7% of bars without a
  prediction.

The direction-only curves, recomputed after the amendment, are
bit-identical to the first run.

**Requirement, as a range across the three noise seeds** (direction-only
arm, which decides the kill):

| breakeven target | AUC needed (plain) | AUC needed (de-meaned, no net-long drift) |
|---|---:|---:|
| **3.4 bps**, bare maker cost, zero margin | **0.567 – 0.575** | 0.569 – 0.578 |
| **4.0 bps**, the p10 gate | **0.574 – 0.591** | 0.578 – 0.594 |
| **5.5 bps**, taker | **0.613 – 0.638** | 0.615 – 0.641 |

**Magnitude arm, reported only** (PLAN amendment 1): a signal stronger on
bigger moves, s = sign(label) · |ret| / std(|ret|) + ε.

| breakeven target | AUC needed (plain) | AUC needed (de-meaned) |
|---|---:|---:|
| 3.4 bps | **0.557 – 0.559** | 0.558 – 0.561 |
| 4.0 bps | **0.559 – 0.564** | 0.561 – 0.567 |
| 5.5 bps | **0.576 – 0.577** | 0.577 – 0.579 |

**Required AUC as a range, bracketed by the two arms.** A real feature
most likely sits between direction-only and magnitude-weighted:

| breakeven target | AUC needed | vs the best real model (0.5445) |
|---|---:|---:|
| 3.4 bps (bare maker) | **0.557 – 0.575** | +0.012 to +0.030 |
| **4.0 bps (gate)** | **0.559 – 0.591** | **+0.015 to +0.047** |
| 5.5 bps (taker) | **0.576 – 0.638** | +0.031 to +0.093 |

- **An honest reading of the band:** if a real feature behaved like the
  magnitude arm, the 4 bps requirement (0.559–0.564) would fall in the
  plan's **0.56–0.58 "abandon unless the owner funds v2"** band, not the
  "closed for good" one. The pre-registered decision uses the
  direction-only curve, which gives 0.590 → closed. Either way the
  outcome is **abandon**; only the wording (closed vs owner's call)
  depends on the arm.
- **Even the optimistic arm needs +0.015 AUC** over the best real model.
  No feature added in p01–p10 has raised AUC at all.

- **Distance from today (direction-only):** the best real model is at 0.5445, so even
  breaking even at bare maker cost needs **+0.023 to +0.030 AUC**. That is
  roughly 1.5× the edge p01 has over a coin flip (0.0445), on top of it.
- **p10's gate asked for more than breakeven:** breakeven − 1 s.e. ≥ 4 bps.
  With s.e. ≈ 0.8 bps, that is a breakeven of ≈ 4.8 bps, and the table
  points to AUC ≈ 0.60–0.61.

## Method (PLAN.md; no new features or model, no selection, 0 OOS trials)
- **Sample and base:** p10's pre-OOS common sample (156,943 labels, t0 and
  t1 < 2024-04-07 09:15). Base predictions are p10's saved A-basic
  PurgedKFold predictions (AUC 0.5445).
- **Synthetic predictions:** p = sigmoid(logit(p_A-basic) + k · s), with
  s = sign(label) + N(0, 1) (label-0 rows: noise only). k was bisected so
  each target AUC is hit to ±0.0005. That is 11 targets (0.55–0.65) × 3
  noise seeds.
- **Positions:** P2 exactly as p02 runs it (hysteresis 0.05/0/24 on the
  full 5 m grid; a bar without a prediction holds, min_hold counts bars).
  Delay 1.
- **Costs:** p05 maker table for net Sharpe.
- **De-meaned breakeven** = held × (ret − mean bar return): it removes the
  net-long drift (the base model is +0.09 long on average).
- **Required AUC:** linear interpolation of the breakeven-vs-AUC curve.
- **Check against p10's review:** the base itself, A-basic with p02-exact
  P2, gives breakeven **1.86 ± 0.85 bps** (de-meaned 1.59) and turnover
  3,050/yr. That matches the reviewer's 1.86.

## The curve (breakeven bps, with de-meaned in parentheses; s.e. ≈ 0.8 bps at every point)
| AUC | seed 0 | seed 1 | seed 2 |
|---:|---:|---:|---:|
| 0.55 | 1.83 (1.56) | 1.77 (1.50) | 1.98 (1.71) |
| 0.56 | 2.29 (2.03) | 2.59 (2.32) | 2.68 (2.42) |
| 0.57 | 2.95 (2.70) | 3.78 (3.53) | 3.78 (3.53) |
| 0.58 | 3.79 (3.56) | 3.64 (3.40) | 4.39 (4.14) |
| 0.59 | 4.01 (3.79) | 3.97 (3.75) | 4.51 (4.29) |
| 0.60 | 4.65 (4.43) | 4.66 (4.44) | 5.12 (4.90) |
| 0.61 | 4.78 (4.58) | 5.31 (5.10) | 5.39 (5.18) |
| 0.62 | 5.11 (4.93) | 6.05 (5.88) | 5.39 (5.19) |
| 0.63 | 5.23 (5.05) | 6.68 (6.52) | 5.86 (5.68) |
| 0.64 | 5.56 (5.39) | 7.03 (6.87) | 6.48 (6.32) |
| 0.65 | 6.40 (6.23) | 6.66 (6.52) | 6.51 (6.36) |

- **Shape:** roughly **+0.5 to +0.6 bps of breakeven per +0.01 AUC**.
  Turnover barely moves (3,050 → 3,500/yr), so extra AUC buys edge per
  trade, not fewer trades.
- **Noise:** each point has s.e. ≈ 0.8 bps, and seeds differ by up to 1.5
  bps at the same AUC. That is why the requirement is given as a range.
  More seeds would narrow it but could not move it from ~0.57–0.59 to
  below 0.56.

## The magnitude-arm curve (breakeven bps, with de-meaned in parentheses)
| AUC | seed 0 | seed 1 | seed 2 |
|---:|---:|---:|---:|
| 0.55 | 2.30 (2.03) | 2.14 (1.87) | 1.99 (1.72) |
| 0.56 | 3.61 (3.36) | 3.79 (3.52) | 4.20 (3.94) |
| 0.57 | 4.62 (4.39) | 4.47 (4.23) | 4.78 (4.53) |
| 0.58 | 6.09 (5.87) | 6.25 (6.03) | 5.84 (5.61) |
| 0.59 | 7.13 (6.93) | 7.40 (7.19) | 6.79 (6.56) |
| 0.60 | 7.55 (7.36) | 8.53 (8.35) | 7.69 (7.48) |
| 0.61 | 8.62 (8.43) | 9.08 (8.91) | 8.83 (8.63) |
| 0.62 | 9.21 (9.04) | 9.55 (9.38) | 10.05 (9.87) |
| 0.63 | 10.31 (10.15) | 10.53 (10.36) | 10.61 (10.44) |
| 0.64 | 11.48 (11.33) | 11.32 (11.15) | 10.76 (10.60) |
| 0.65 | 12.65 (12.51) | 11.97 (11.82) | 12.53 (12.38) |

Breakeven rises about **+1 bp per +0.01 AUC** here, twice the
direction-only slope. Skill concentrated on big moves is worth about
twice as much per unit of AUC.

## Caveat
A label-derived signal predicts barrier **direction**, not the size of
the move. A real feature with the same AUC could be worth more (if it
picks the large moves) or less (if its skill sits in small, cost-dominated
moves). This curve is an approximation of what AUC buys, not a bound.

## Decision
The pre-registered kill applies: **no flow v2, no TCN retune, no stacking
on the 1 h BTC triple-barrier label.** The 1 h / 4 h bar-direction line
(p01–p05, p10) is closed. The p10 reviewer's pivot is next: **p11**, the
RTDS settlement check, once ≥ 7 days of the new collector feed exist
(from 2026-09-24).

## Bookkeeping
- 66 `measurement` rows in `selection_trials.json`: 33 direction, 33
  magnitude arm.
- PLAN amendment 1 (row zero + magnitude arm) was written **after** the
  first run's numbers were seen, and is disclosed as such. It is
  reporting only; the kill rule and deciding curve are unchanged.
- `trials.json` untouched (3).
- Files: `PLAN.md` (committed before any computation), `run.py`,
  `run.log`, `results.json`.
- Runtime 25 s.
