# p15 — Polymarket BTC threshold markets vs Deribit option-implied probability: KILLED at KILL C (dev)

**Verdict: no tradeable gap.** On 4,907 dev markets (2023-04 → 2025-09; 43,828 market-hours in the
main set), Polymarket's price and the Deribit risk-neutral probability of the same event agree to within
about 1 pp. For longshots (P_RN < 15%) the median gap is **+0.75 pp [0.64, 0.88]** against the
pre-registered 2 pp bar, so **KILL C fires** and Step 2 (the trading rule) was not run. As forecasters
the two are indistinguishable (Brier 0.1426 vs 0.1418, t 0.23 by fixing date). No holdout was read and no
trial is logged.

Plan: `PLAN.md` (commit baf4903) with amendment 1 (f66d9c9, step 0 findings and Step 1 definitions,
before any price) and amendment 2 (150bb9a, the owner's decision after the data-source gate failed as
written). Split fixed from fixing dates only (f8a8832); Step 1/2 code committed before any Polymarket
price was loaded (7cbd757).

## What was tested
Polymarket's "Bitcoin above $K on <date>" and "Bitcoin price on <date>" bucket markets are digital
options on the Binance BTCUSDT 1-minute close at a stated time (usually 12:00 ET). The same probability
is priced by Deribit's option surface. The hypothesis (NEWPLAN #1; arxiv 2606.19517 reported a 6–11 pp gap
on three 2023 contracts) was that retail Polymarket prices longshots well above Deribit, by more than
fees.

## Step 0 — data and settlement (all gates on dev pass)
| check | result |
|---|---|
| Inventory | 11,261 in-scope markets (strike 5,800, range 5,461) after excluding 1-hour markets (never bracketed by two Deribit expiries), 6 Coinbase and 39 legacy/CoinMarketCap markets, and 11 markets of one event with an ambiguous "12AM ET" fixing |
| **KILL A: settlement rebuild** | **11,261 / 11,261 = 100%** agreement with Gamma, incl. all 68 markets within 3 bp of the strike (first run 99.90%; the 11 misses were parser bugs, fixed from metadata). The fixing time must come from each market's rule text: `end_date` is wrong for older markets |
| Underlying | Deribit index / Binance BTCUSDT − 1 at the fixing: median +1.0 bp, IQR −4.0 / +4.5 bp (USDT/USD basis drifts by year: +12 bp 2023, −4 bp 2026); mapped causally into the strike |
| Fill source | The public HuggingFace on-chain table **failed** (timestamps off by +94…+102 s or by 5–6 h vs Polygon block time in some ranges; part of the v2-exchange fills missing) and was **replaced** by Polymarket's data API (7.82 M taker trades; timestamps = block time on 50/50 checked) |
| Source gate (i) | **Failed as written** (88.6% of markets within 1% of Polymarket's volume counter vs 95%): **dev 99.35%**, holdout 80.0% (2026-03/04 fixings, API ~4% short around the v2 migration). Owner's decision (amendment 2): gate per span; dev proceeds; the holdout gap must be explained before any holdout run |
| KILL B: power | 198 dev fixing dates with usable trades (≥ 100) |
| Split | dev 2023-04-12 → 2025-09-29 (4,907 markets, 201 dates); holdout 2025-09-29 → 2026-07-27 (6,354 markets, 298 dates) — the calendar rule gives the holdout more markets because listings grew |

## Step 1 — the gap (dev, measurement)
PM(t) = VWAP of taker trades in the hour to t; P_RN(t) = Deribit digital from smiles fitted on the hour's
option marks, maturity bracketed by two expiries, strike inside both smiles' traded range (main set).
D = PM − P_RN, CIs by fixing-date bootstrap.

| P_RN bucket | rows | markets | dates | D median, pp [95% CI] | D mean, pp | PM mean | P_RN mean | realised |
|---|---:|---:|---:|---|---:|---:|---:|---:|
| 0–5% | 5,232 | 549 | 112 | +0.65 [0.54, 0.79] | +0.94 | 0.033 | 0.023 | 0.018 |
| 5–15% | 9,198 | 827 | 150 | +0.83 [0.69, 1.02] | +1.17 | 0.113 | 0.101 | 0.113 |
| 15–35% | 13,639 | 927 | 178 | +0.29 [0.15, 0.44] | +0.71 | 0.235 | 0.228 | 0.228 |
| 35–65% | 8,080 | 562 | 177 | +0.11 [−0.20, 0.43] | +0.11 | 0.489 | 0.487 | 0.525 |
| 65–85% | 3,801 | 324 | 136 | −1.16 [−1.51, −0.84] | −1.34 | 0.737 | 0.751 | 0.767 |
| 85–95% | 2,299 | 238 | 102 | −1.37 [−1.73, −1.05] | −1.68 | 0.885 | 0.902 | 0.897 |
| 95–100% | 1,579 | 187 | 77 | −0.90 [−1.18, −0.64] | −1.17 | 0.966 | 0.978 | 0.999 |

**KILL C (pre-registered): median D in P_RN < 15% = +0.75 pp [0.64, 0.88] < 2 pp → fires.** The full
P_RN × maturity table is in `step1.log` / `step1.json`; no cell with ≥ 100 rows reaches 2 pp.

- **The sign pattern is a favourite–longshot tilt** (Polymarket slightly rich on longshots, slightly
  cheap on favourites), consistent with arxiv 2609.12878, but about a tenth of the size needed. The
  crypto taker fee alone (0.07·p·(1−p)) is 0.6–1.2 ¢ in the 10–20% range, before the spread.
- **Calibration:** Brier 0.1426 (Polymarket) vs 0.1418 (Deribit) on the same rows, difference t 0.23 by
  fixing date. Both reliability curves are within ~2–3 pp of realised in every decile except 50–60%
  (both under-forecast: realised 0.63).

### Descriptive, post hoc (not used for any decision)
- **The gap compressed:** low-bucket median D was +2.75 pp in 2024 (408 rows, few markets) and +0.72 pp in
  2025 (14,022 rows). The prior paper's 2023 sample predates the compression.
- **First observation per market** (916 low-bucket markets): PM 12.9% vs P_RN 10.6% vs realised 10.8%.
  Early, thin prices are richer; this is a mean over each market's first hour, not the registered
  statistic, and on dev it could only be a hypothesis for fresh data.
- **Coverage:** main set 43,828 of 94,374 market-hours. 39,884 had no bracketing expiry pair (median
  0.9 d to fixing: the last hours after the final expiry before the 12:00 ET fixing), 10,662 needed strike
  extrapolation (their low-bucket median D is +0.40 pp, so extrapolated strikes do not hide a gap).

## What survives, what does not
- **Dead, as tested:** a pricing gap between Polymarket BTC threshold/range markets and the Deribit
  surface large enough to sell Polymarket longshots against. On 2025 data the two venues are priced
  within ~1 pp, which is inside the fee plus spread of either side.
- **Not tested:** Step 2's realised P&L (not run: KILL C fired first, per PLAN), a hedged book, maker-side
  entry, other underlyings (ETH/SOL markets), "hit $K" touch markets.
- **Infrastructure kept:** the settlement parser (49 rule phrasings, 100% agreement), the Deribit
  surface / digital pricer (`surface.py`, tested), and the finding that the HuggingFace Polymarket table
  must not be used for timing-sensitive work.

## Validation-report note
CLAUDE.md rule 8 applies to strategy results with a return series. This experiment was killed at a
measurement step before any rule was run, so there is no verdict block. No trial is logged in
`trials_pm.json`; no threshold was changed (amendment 2 changed the scope of a data-source gate at the
owner's decision, disclosed above, not a kill threshold).

## Incident (infrastructure)
The first Polymarket trade fetch ran on `poly-collector-eu` and, holding every result in memory, drove
the 2 GB VM out of memory: it hung from ~2026-09-28 20:25 to 2026-09-29 06:05 UTC, when it was reset with
the owner's approval. The live collectors lost ~9.7 h (Polymarket CLOB, Binance, on-chain Chainlink and the
RTDS Chainlink stream; the RTDS window has no archive). The fetch was rewritten with bounded memory and
finished on a throwaway VM (`p15-fetch`, deleted afterwards); p15 files were removed from the collector VM.

## Files
`PLAN.md` · `inventory.py` · `fetch_gamma.py` · `step0.py` (rules, basis, split, apigate, power) ·
`extract_fills.py` / `validate_fills.py` (the rejected HF source) · `fetch_trades.py` · `common.py`
(holdout guard) · `surface.py` + `test_surface.py` · `step1.py` · `step2.py` (written and committed, not run) ·
logs and JSON for every step · `split.json`.
