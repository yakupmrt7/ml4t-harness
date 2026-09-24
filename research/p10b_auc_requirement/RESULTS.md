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

**Requirement, as a range across the three noise seeds:**

| breakeven target | AUC needed (plain) | AUC needed (de-meaned, no net-long drift) |
|---|---:|---:|
| **3.4 bps**, bare maker cost, zero margin | **0.567 – 0.575** | 0.569 – 0.578 |
| **4.0 bps**, the p10 gate | **0.574 – 0.591** | 0.578 – 0.594 |
| **5.5 bps**, taker | **0.613 – 0.638** | 0.615 – 0.641 |

- **Distance from today:** the best real model is at 0.5445, so even
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
- 33 `measurement` rows in `selection_trials.json`.
- `trials.json` untouched (3).
- Files: `PLAN.md` (committed before any computation), `run.py`,
  `run.log`, `results.json`.
- Runtime 25 s.
