# Review: p14_hl_funding_carry (pre-OOS, before the holdout gate)
**Decision:** ACCEPT WITH FIXES. Both dev verdicts stand. The fixes are bookkeeping and wording. **Do not spend the holdout.**
**One line:** HL funding exceeds Binance funding in 8/8 coins, but the premium fell from 8.8%/yr (2024) to 1.8 ± 0.7%/yr
(2025) for the registered rule. The rule's 5.25%/yr dev pass is 0.15 autocorrelation-robust s.e. above the bar. At 2x
per leg the book cannot survive even when rebalanced daily, and even on Binance's mark price: 2025-10-10 wipes out
alt long legs.

## What I checked, and found clean
- **Funding sign.** Positive rate means longs pay, on both venues. Short HL / long BN earns f_hl − f_bn, as coded.
- **Look-ahead.** m(d−1) uses HL stamps up to 23:00 and BN stamps up to 16:00 of d−1. Position is `shift(delay)`.
  There is no look-ahead.
- **Stamp jitter.** HL stamps land 0.15 s to 888 s after the hour; BN stamps land 0 to 16 ms after. No stamp crosses a
  UTC day boundary backwards.
- **Day convention.** Crediting the 00:00 settlement of day d to day d is achievable: the signal is known by 23:00, so
  one can enter before 00:00. I also assigned each payment to the day it accrues (stamp − 20 min): 5.25 → 5.27%/yr
  at delay 1, 4.64 → 4.64 at delay 2. Immaterial.
- **Candles.** HL and Binance 1d candles are both indexed by UTC open time: 742 rows each on dev, no gaps. So
  `pct_change` is a clean close-to-close return and there are no multi-day jumps.
- **Binance funding cadence.** 8 h throughout dev (2,225 intervals, all 8 h). Summing by day is right.
- **ADL data.** ADL rows are side B, `startPosition` < 0: shorts forced to buy back. The static book's short leg is on
  that side.
- **Harness and ML rules.** harness/ is untouched since 9075fcf, and nothing was loosened. No model, CV or feature
  matrix is involved, so rule 9 and the fold-id test do not apply to this threshold rule. They will apply to NEWPLAN
  #3's forecast, where the funding level is non-stationary (2024 vs 2025).

## Blocking issues (fix before the result counts; neither verdict changes)
1. **No `selection_trials.json`.** p15–p17 each have one. p14 needs one entry per dev evaluation:
   - interim 3-coin run
   - 8-coin run at delay 1
   - 8-coin run at delay 2
   - the post-hoc static diagnostic inside run.py (seen on 3 coins before amendment 1)
   - static.py on dev
   - rule_survival.py

   `trials_hl.json` must stay absent, because no holdout was touched.
2. **The statistics lack standard errors, and the Sharpe is overstated.** Daily P&L is autocorrelated (lag-1 0.31;
   positions and funding persist). Newey–West s.e. of the rule's annual return:
   - lag 30: 1.6%/yr; lag 7–90: 1.0–1.9%/yr
   - monthly: 1.5%/yr (t 3.4 on 25 months)

   So the result is **5.25 ± 1.6%/yr**, and the kill-1 margin of 0.25 pt is **0.15 s.e.** The naive Sharpe of 6.7
   becomes ≈ 2.3 after the autocorrelation adjustment (kill 2 still passes). 2025 alone: **1.84 ± 0.74%/yr**.
   - Four months (Feb–Mar 2024, Nov–Dec 2024) produce most of the return. Without them, about 2.2%/yr.
   - Static book: the weekly t of 7.15 is overstated the same way.
   - RESULTS must quote these numbers and label 2026Q1 as 11 days.
3. **"A survivable book needs ~1x per leg (capital ≈ 2x notional) → ~2.6%/yr on capital" is wrong under the report's
   own margin rule, and it does not say what survives.**
   - Under the registered weekly reset, the XRP short leg moved +116% and DOGE +97% from the Monday reference. That
     liquidates even 1x.
   - With a daily reset (reference = previous close, which is what a real operator would do), the maximum one-day
     adverse move over dev is:
     - short leg: +42% (XRP 2024-11-16, LINK 2024-12-02)
     - long leg: −83% (SUI 2025-10-10)
   - Survivable leverage is therefore asymmetric: about 2x on the short HL leg and ≤ ~1.15x on the long BN leg, with
     no buffer. Capital ≈ 0.5 + 0.87 ≈ **1.37x notional**.
   - Return on capital: rule **3.8%/yr on dev and 1.3%/yr in 2025**; static book **5.6% dev, 3.2% in 2025**.
   - The conclusion (below T-bills plus venue risk in 2025) stands; the numbers in RESULTS must be replaced with these.
4. **The OOS decision must be written in RESULTS.md, not in "the session summary".** See the recommendation below.

## Non-blocking issues
- **Is the margin rule sound?** Kill 4 firing is robust. The only thing it overstates is timing.
  - **Weekly vs daily reset.** The weekly reset overstates liquidations. With a daily reset, 2x hits only on
    2025-10-10 (XRP, DOGE, LINK, AVAX, SUI; 1 day each), and kill 4 still fires.
  - **Binance last-trade wick vs mark.** I fetched Binance 1-minute **mark-price** klines for 2025-10-10 (a dev date).
    Mark lows sit within 0–2 pts of last-trade lows: XRP −57%, DOGE −64%, LINK −63%, AVAX −70%, SUI −83% from the
    previous close. Binance liquidates on mark, so this was not a wick artifact.
  - **Cross margin.** It does not rescue the book. The 8 Binance longs fell together, by about 52% on average at the
    lows. Cross margin inside HL pools the *winning* legs, and collateral cannot move between venues within minutes.
  - **Threshold.** 45% is slightly conservative: the true 2x threshold is about 47–49% after maintenance margin.
    Immaterial against moves of 58–84%.
  - **What the rule understates.** It ignores liquidation fees and the naked leg left after a liquidation. Rough
    arithmetic for DOGE on 10-10:
    - BN long liquidated near −45%;
    - HL short held from the low to the close (−22% close-to-close);
    - loss ≈ 20–25% of that coin's notional.

    One such event outweighs about a decade of the rule's 2025 carry on that coin. The HL short leg was checked on
    Binance prices, not HL mark. Acceptable, because its hits came from multi-day rallies that HL mark tracks.
- **ADL scenario.** The code's logic and sign are right: the short is closed at p_adl instead of held to the close and
  re-shorted there, so delta = (close − p_adl)/prev − HL fee. But:
  - The median fill is an arbitrary summary. SUI ADL fills ranged from 0.61 to 2.59 around a close of ~2.6, and the
    first fills would give about 0.
  - HL ranks ADL by profit x leverage, so a 2x account is unlikely to be *fully* ADL'd.
  - The scenario assumes the BN long survived, which contradicts kill 4 for 5 alts that same day.
  - The gain exists only because prices rebounded after 21:20. In a crash that keeps falling after ADL, the naked
    Binance long loses.

  "ADL is not this book's danger" is one event read as a law. Reword to: "on 10-10, at the median ADL price, the
  scenario was a gain because prices rebounded." `with_adl_net_ann%` (14.1) in static_dev.json is not a meaningful
  number: one day adds 6.4 pt/yr. Drop it or label it.
- **Holdout hygiene.** run.py and static.py load funding and candles through 2026-09 and run the position state machine
  through the holdout before truncating. Dev numbers cannot be affected (the logic is causal) and nothing is printed,
  but "holdout not read" is not literally true. Cut at load.
- **Amendment timing.** fetch.log shows DOGE–SUI funding finished around 13:00 UTC on 09-29. Amendment 1 was committed
  at 13:50 UTC, and its interim RESULTS still said "downloading". The claim "before the 8-coin numbers" cannot be
  verified. It does not matter, because the static book died anyway.
- **Costs.** HL costs are the fee schedule plus an assumed 0.5 bps/leg; the spread was not measured (CLAUDE.md). The
  impact is ≤ 0.15%/yr at 11–23 round trips over 2 years. The open positions at dev end are not charged an exit
  (≤ 0.05%/yr). USDC/USDT basis and transfer delays are ignored (disclosed for the static book).
- **Report glitches.** In static_dev.json `k1_econ` is serialised as the string "False" (numpy bool with `default=str`).
  run.py has no `--holdout`, `--no-log` or TrialLog path, so a holdout run would need a code change committed first.

## What the evidence supports
- On dev, HL funding > Binance funding in 8/8 coins (mean spread 1.3–3.7 bps/day, AR(1) 0.54–0.80).
  - HL alone: 18.6–37.1%/yr in 2024, 5.3–11.9%/yr in 2025.
  - Binance: 10–14%/yr in 2024, 0.1–5.1%/yr in 2025.
- The cross-venue premium roughly quartered from 2024 to 2025. The registered rule made 8.8%/yr in 2024 and 1.8%/yr in
  2025 on notional. Delay 2 fails kill 1 (4.64%/yr).
- The static short-HL/long-BN book is **KILLED** at registered kill 4. That verdict is robust to daily reset and to
  mark price, because of 2025-10-10.
- The rule's kill-1 benchmark assumes 2x per leg (PLAN: "on 2x margin … ≈ 1x notional of capital"). Dev shows 2x does
  not survive, so a kill-1 pass does not establish an investable return.
- Not supported:
  - "arbitrage capital demands exactly this premium for that risk" (a plausible story, untested);
  - "ADL is not the danger" (n = 1);
  - "survivable at ~1x" (see blocking 3).

## OOS gate recommendation: spend nothing. The holdout stays sealed.
- The PLAN allows the look ("only if dev passes"). It does not oblige it, and declining makes no claim, so no rule is
  bent.
- **Information value is low.** For the holdout to pass, 2026 must run at more than 5%/yr when 2025 ran at
  1.8 ± 0.7%/yr and delay-2 already fails. A pass would mean a 2024-style leverage mania, not a validated rule.
- **A pass would not be claimable.** The benchmark's 2x capital assumption fails on dev. Adding survival as a holdout
  kill now would be tightening, which is allowed, but dev already fails it, so the look would be decided before it is
  taken.
- **The data has a use.** 2026-01-12 → 2026-09-27 is the only fresh funding data for any carry variant (next section).
  Spending it on a near-dead rule contaminates it for the one variant that might survive.
- **If the owner still wants the rule closed with an OOS number**, it is legitimate under the PLAN:
  - first commit a holdout mode for run.py: a `--holdout` flag; the position state and 7-day window carried from dev;
    one `TrialLog("trials_hl.json").log(...)`;
  - then run `python research/p14_hl_funding_carry/run.py --holdout` once;
  - kills are **exactly the PLAN's 1–2 (and the 3 flag) as written**. Delay-2 and daily-reset survival are reported,
    not kills;
  - a pass must be worded "passes screen; not investable at 2x (dev survival)".

  I do not recommend it.

## Proposed next experiment (NEWPLAN #1, #2, #4 are dead; this decides #3 without touching the holdout)
- **Hypothesis:** at a leverage that survives every dev day (daily reset, Binance mark, 1.5x buffer on the worst
  dev day), at least one carry structure earns ≥ 6%/yr **on capital** in 2025, net of taker costs. The 6% is T-bill
  plus 2 pt for two-venue and stablecoin risk.
  - A: the static cross-venue perp/perp book from this experiment.
  - B: short HL perp / long Binance **spot** (the spot leg cannot be liquidated, and it collects all of HL funding,
    which averaged 8.4%/yr in 2025, instead of the 4.4% spread).
  - C: the perfect-foresight timing of the better of A and B. This is the ceiling for NEWPLAN #3's forecast.
- **Exact change vs p14:** the only new variable is the capital denominator: survivable per-leg leverage from daily
  mark-price moves, with the buffer fixed in the PLAN. Add B's spot leg (Binance spot klines are already in data/raw).
  C is computed, not traded. No model is fitted.
- **Pre-OOS plan:** dev only (2024-01-01 → 2026-01-12), with 2025 as the decision year because of the decay.
  - PLAN.md with the leverage rule, buffer and kills, committed before any computation.
  - Every run goes into selection_trials.json. No trial is logged.
- **Kill criteria (fixed in advance):**
  - If C < 6%/yr on capital in 2025, close carry entirely, including the NEWPLAN #3 ML version (no forecast can beat
    the oracle).
  - If C passes but A and B static both fail, #3 lives only as a forecast problem. It must first beat EWMA on dev.
  - If B static passes (arithmetic prior: BTC ≈ 10.6/1.33 ≈ 8%/yr gross; 8-coin mean ≈ 8.4/1.5 ≈ 5.6%/yr gross),
    pre-register B exactly, with 6%/yr on capital, monthly t ≥ 2, the tail rule and zero liquidations. Spend the p14
    holdout on B, as one trial in trials_hl.json.
- **Expected cost:** 0 OOS trials; about 1 day of compute and code (only the 10-10 mark klines and spot klines are
  missing).
- **If C fails:** every NEWPLAN idea is dead. Stop opening lines. Per ROADMAP §7, write up p12–p17 as "the harness
  said there is nothing here". The only parked item with an external prior is the Polymarket politics
  favourite–longshot bias (arxiv 2609.12878); give it its own PLAN before reading any data.
