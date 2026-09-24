# Review: p11_external_signals
**Decision:** ACCEPT WITH FIXES. The KILL is valid, it holds on both pre-registered conditions, and no OOS data was touched. RESULTS.md and the CLAUDE.md closure note overclaim in three places (see Blocking). Only the wording needs to change.
**One line:** 26 external features (DVOL, Deribit option flow and ATM IV, funding dispersion across 3 venues, basis vs 2 venues) add no 4 h direction AUC to p01's basic set when fed raw to LightGBM. The model uses them to identify the regime (it predicts the CV fold with 99.8% accuracy) and loses 0.021 ± 0.007 AUC. One feature, `opt_netcall_4h`, has a real-looking univariate signal (AUC 0.539, the same sign in 5/5 folds). But it overlaps p01's 4 h reversal (ρ = 0.39 with ret_48), and even a post-hoc stack adds only +0.005 AUC. Liquidations remain untested.

## Verification done by this review (own code, pre-OOS only; option files < 2024-04-08, bars < 2024-04-07 09:15)
- **Git and file order.**
  - PLAN 104a0f1 (19:59) → AVAILABILITY 1f289b3 (20:09) → A1 b807f1d (20:20:00).
  - The first backfill file is dated 20:20:56 (bybit funding 20:21, Deribit www 20:23). backfill.py mtime 20:20:42, features.py 20:24:52. Code commit 71eca5c 20:25. The last option file is 21:38:06.
  - The crashed run is at 21:38:23 (pycache), and the tz fix 59bcbe9 at 21:38:40. The crash is at the `close.loc[START:...]` slice, before any feature, label or model, so no numbers existed.
  - All 58 rows of `selection_trials.json` (52 IC + 6 model) carry timestamps 21:39:41–21:40:45, i.e. one run.
  - `trials.json` has 3 entries, with no diff since the PLAN, and `harness/` has no diff. So tests and selftest were not required.
  - The feature code implements A1 exactly. It adds three unregistered but non-data-driven details: flow excludes iv ≤ 0 trades, ATM IV also needs ≥ 5 trades, and the DVOL z-score needs min_periods 600.
- **Feature spot-check.** 7 closes: 4 random, plus 2023-03-10 09:05 (just after an hour boundary) and 2023-06-01 08:00/08:05 (either side of a funding settlement). 14 features each were recomputed by hand from the raw files: dvol, dvol_chg_4h, ivrv_1d, the 3 flow ratios, atm_iv_4h, the 3 funding rates, fund_bybit_minus_bin, basis_bybit and basis_okx. **All match to ≤ 1e-14.**
  - At 08:00 the Binance funding used is the 00:00 settlement, and at 08:05 it is the 08:00 one (strict asof ✔).
  - At 08:00 the DVOL used is the candle opening 06:00. The 07:00 candle becomes usable only at 08:05 (T + 1 h + 1 min ✔).
- **Timestamp semantics, checked from data rather than docs:**
  - **DVOL stamp = candle open.** (c − o) of the candle stamped T correlates −0.087 with the BTC return over [T, T+1h), against −0.015 over [T−1h, T). The +1 h + 1 min lag is therefore right, not 1 h too early. There are 0 gaps, and open equals the previous close in 99.96% of candles.
  - **Bybit/OKX candle alignment:** `check_close_alignment` puts the peak at lag 0 (ρ 0.994 / 0.996), with lag ±1 at −0.05. Median |basis| is 1.3 / 4.5 bps aligned vs 6.0 / 7.0 bps if shifted one bar. All OKX candles are `confirm=1`.
  - **Options:**
    - In a 1/20 sample (334 k trades), 0 instruments are unparsed, all expiries fall at 08:00 UTC, the minimum dte is > 0, and moneyness has a median of 1.005.
    - `iv` is in % (median 56). It has 999 junk prints, but the median-based features are robust to them.
    - The 5-min bucket `floor + 5 min` holds [t−5m, t), and the median windows use `searchsorted(side="left")`. Both are strictly < t ✔.
  - **Funding units:**
    - Binance and Bybit are settled per-8 h rates (median 1e-4, stamped 00/08/16).
    - Deribit `interest_8h` = the trailing sum of 8 hourly `interest_1h` values (ρ 0.9998, ratio 0.9995). It is per-8 h and comparable ✔.
  - **ivrv:** √(365·288) on 5 m log returns is right for a 24/7 market. dvol/100 is in decimal. Example: 2024-03-05 22:10 has ivrv_1d −0.60 on the crash day, which is plausible.
- **`oos_predict_nan`** is equivalent to `harness.pipeline.oos_predict`, except that it skips `align` and the < 100-row guard. In practice only 36 rows of `opt_skew_4h` are NaN (0.02%), so the NaN path is immaterial. The basic H = 48 AUC of 0.541 matches p03's 0.543 on a slightly different start date.
- **Numbers reproduced** from `preds_selection_H48.parquet`: AUCs 0.5410 / 0.4979 / 0.5205, and the basic row's breakeven 2.847 ± 0.964 bps.

## Blocking issues (wording; the KILL itself stands)
1. **Reading 1, "the external data carries no usable 4 h direction signal in this form", needs the univariate evidence next to it.** My pre-OOS diagnostics:
   - **`opt_netcall_4h`** (a signed net-call-buying ratio): univariate AUC **0.539** (sign fixed on the full pre-OOS sample). Per-fold Spearman IC vs label return: −0.044, −0.024, −0.050, −0.073, −0.031, the **same sign in 5/5 folds**. With the sign learned in-fold by logistic CV, AUC is **0.533**.
   - That is nearly the basic model's 0.541, yet the external LightGBM sits at 0.498. **The tree model failed to use its best input.** "No usable signal" is a claim about the model, not about the data.
   - **Why it does not rescue the hypothesis:** ρ = +0.39 with `ret_48`. In market terms, option traders buy calls after 4 h rallies and puts after drops, so this is largely p01's 4 h reversal seen through Deribit. A post-hoc CV logistic stack of logit(p_basic) and `opt_netcall_4h` reaches **0.5458**, i.e. **+0.005** over basic, which is half the +0.01 gate. It is also selected after seeing 52 screens (1 of 52 at |t| = 3.0 has family-wise p ≈ 0.13).
   - Its breakeven under P2 is not comparable: logistic probabilities are compressed, so θ = 0.05 trades 1,124×/yr instead of 3,065. It is a diagnostic, not a trial.
   - **Replace with:** "The external set adds no AUC to basic in LightGBM (−0.021 ± 0.007). The one consistent univariate signal, net option call buying (AUC 0.539, 5/5 folds), mostly restates 4 h reversal (ρ 0.39 with ret_48). Stacked onto basic it adds +0.005 AUC post hoc, below the +0.01 gate."
2. **"Regime, not direction" is stated as an explanation but untested. It is now supported; add the numbers:**
   - An adversarial LightGBM predicts the PurgedKFold fold id (chance 0.20) with **0.998** accuracy from the external features, vs **0.474** from basic.
   - Mean predicted P(up) by fold: "both" gives 0.570 / 0.513 / 0.544 / 0.500 / 0.483, while the actual up shares are 0.497 / 0.512 / 0.497 / 0.525 / 0.537. The level features (DVOL 31–120, persistent OKX basis around +4 bps, funding levels, ATM IV) let the model infer each fold's base rate from its neighbours in time. In the held-out block that base rate is wrong, the same failure as p10.
   - Per-fold AUC for external-only: 0.501 / 0.501 / 0.519 / 0.517 / 0.483.
3. **Fix the CLAUDE.md closure note:**
   - (a) "p10b showed a 4 bps breakeven needs AUC ≈ 0.56–0.59" was measured at **H = 12**. At H = 48 the requirement is unmeasured, and lower (fewer trades). Say so.
   - (b) Add "liquidations untested (no free history for 2022–26)", so that "all failed" is not read as covering them.
   - (c) "other horizons of the same bar-direction label" must not be read as covering Polymarket up/down contract **pricing/settlement** work. That work conditions on the observed path and a known strike; it does not forecast drift. Add: "Does not cover settlement/fair-value/latency work on Polymarket contracts (p09, p12)."
   - (d) "all failed their pre-registered kills": p01/p02 were not pre-registered kill experiments. Say "failed their kill or cost bar".
   - The closure itself is warranted and correctly pre-committed (PLAN, before data).

## Non-blocking issues
- **The feature spec repeats p10's known failure mode.** p10's review recommended rank/regime-normalised features for any v2, but A1 registered 12 of 26 features as raw levels. The fold-id result above shows the cost. For the record, this is a design weakness, not a bug, and the pre-registration was honoured.
- **Funding staleness is asymmetric.**
  - Binance and Bybit enter as the last **settled** rate, up to 8 h old. Deribit enters as a trailing 8 h rate, ≤ 1 h old.
  - So `fund_deribit_minus_bin` and `fund_disp` partly measure staleness, not disagreement.
  - Deribit also has no +0.01% interest floor: its median is 7.8e-6, against Binance's 1e-4. The Deribit − Binance difference is therefore about −1e-4 by construction.
  - A cleaner cross-venue measure would have used Binance `premiumIndexKlines` (on disk, real-time) against Bybit/OKX premium. It cannot change the verdict.
- **Option flow is contract-count-weighted (BTC `amount`), not premium- or delta-weighted.** A 0.1-BTC deep-OTM lottery ticket counts the same as a 0.1-BTC ATM hedge. The standard "net call buying" measures weight by delta or premium. This is a spec choice, noted for anyone reading the family as "tested thoroughly".
- **Kill condition 1 fired on the basic-only row** (2.85 bps < 4), which contains no external data. It is a valid pre-registered condition, but it says nothing about the external features. Condition 2 (AUC 0.498) and the gate's gain (−0.021, about 4.5 s.e. below +0.01) carry the decision.
- **`dropped_by_col`** reports NaN counts, not drops: `opt_skew_4h` is NaN-tolerant and was kept. The 44 rows actually dropped come from the basic features. Rename it in any reuse.
- **Owner "go" before A1** is not recorded in git (A1's text asserts it). Timing is consistent: 11 min after AVAILABILITY and 56 s before the first download.
- **The start date is hard-coded** (2022-09-01), not "set by the latest-starting source" as the PLAN says. Every source covers it, so this is immaterial.
- **Basic H = 48 is 2.85 ± 0.96 bps** gross on pre-OOS: 1.60 y, n_eff 4,696, Sharpe s.e. ≈ 0.79, gross SR 2.15. It is 13.5% net long (mean position +0.135) in a rising market, and de-meaned it is 2.45 bps. Against the p05 BTC maker cost (median 3.2, range 2.0–5.3 bps) and taker ~5.0, it is not tradeable. p03's OOS 2.50 bps says the same.

## What the evidence supports
- **The KILL is valid and robust.**
  - External-only AUC is 0.498 (s.e. ≈ 0.01).
  - The both − basic gain is −0.021 ± 0.007, where +0.01 was needed.
  - H = 288 agrees: −0.012 ± 0.014, no IC |t| ≥ 2, n_eff 852.
  - I found no alignment, unit, parsing or NaN bug that could hide a signal. Every source's timestamp semantics were checked from data, and 14 features match hand computation at 7 closes, including hour and settlement boundaries.
  - The strongest post-hoc repair I could build (a logistic stack with the one consistent feature) reaches +0.005 AUC.
- **What was tested:** Deribit IV level, change and IV − RV; option flow and trade-implied skew/ATM IV; funding dispersion (Binance/Bybit/Deribit); and Bybit/OKX basis. For 4 h BTC direction, these add nothing that LightGBM can use on top of 4 h reversal, and raw levels actively hurt via regime identification.
- **What was not tested:** liquidations, options OI/greeks/chain-based skew (paid data), and premium-weighted flow.
- **The 1 h / 4 h BTC bar-direction line has failed in p02, p03, p04, p05, p10, p10b and p11.** Closing it is correct. The expected value of further feature work is below its multiple-testing cost: the best AUC seen is 0.541–0.546, against the AUC needed for 4 bps (0.56–0.59 at H = 12).

## Proposed next experiment (p12: RTDS settlement check, as queued by the p09 review)
- **Hypothesis (falsifiable):** The collector's rebroadcast Chainlink btc/usd stream (`crypto_prices_chainlink`) reproduces Polymarket's Gamma resolutions on ≥ 99.5% of BTC up/down markets from the first ≥ 7 full RTDS days (from 2026-09-24 07:12 UTC, so no earlier than 2026-10-02).
- **Exact change vs p09:** the settlement/reference price input only (Binance proxy → RTDS Chainlink). Before step 0, no model, σ, fair value or book comparison is done.
- **Market reasoning:** these contracts settle on a specific oracle print at a specific second. Near the strike and near expiry, the value is decided by fractions of a bp in that exact feed. p09 lost precisely where its Binance proxy differs from the oracle. If the collector's stream is not the settlement feed, every downstream fair-value or latency study is built on the wrong price.
- **Pre-OOS plan:**
  - Step 0: document the collector schema in CLAUDE.md, as it notes the schema is missing.
  - Rebuild settlement per market rule (start print vs end print, tie rule) for every market in the window, fetch Gamma outcomes for the same slugs, and report the agreement rate plus every disagreement with its |end − start| in bp.
  - Disagreements are expected only at |gap| < ~0.1 bp. Any at larger gaps means a timing/stamp error (receive time vs oracle round time); report it, do not tune it away.
  - Nothing is selected, and `trials.json` is not touched. This is a data-validation measurement.
- **Kill (fixed now, from the p09 review):**
  - Abandon the settlement-exact line if agreement is < 99.5%.
  - If it passes, the p09 step 1 (Brier vs mid by gap bucket, RTDS inputs) runs with its pre-set kill: abandon diffusion fair value if the model − mid Brier at |gap| < 1 bp stays > +0.01.
  - p09-dev and the 09-06..09-20 holdout stay untouched.
- **Expected cost:** 0 OOS trials, one Gamma fetch, minutes of compute, and ~1 week of waiting.
- **Until then:** use the wait for Step 0's schema documentation only. Do not use it for any BTC-direction work, which is now closed.
