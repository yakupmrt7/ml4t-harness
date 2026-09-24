# p09 Polymarket 5-minute BTC up/down: settlement, fair value, and what is takeable

Written 2026-09-23, before any p09 data was read. The only things looked at
were p08's documentation (RESULTS/SCHEMAS/VALIDATION.md, reduce.py) and
GCS directory listings and sizes. This follows the owner's brief and the
p07b REVIEW's proposed pivot to the collector data. Nothing below changes
after numbers are seen. Where something must be chosen on dev, the choice
and the candidates are named here.

## Line and scope
- **New line, new data.** This is the pivot away from daily Binance-perp
  cross-sectional factors (p06 fail, p07 void, p07b fail). It is not a
  one-variable change from p07b, and is not meant to be.
- **Measurement only.** No trading rule is selected. Step 3 simulates a
  fixed, pre-registered set of taker rules to measure what is takeable.
  Nothing is optimised.
- **No `trials.json` entries.** This line does not share p01–p07's OOS
  period. `selection_trials.json` gets one row per pre-registered Step-3
  configuration (all reported), marked `measurement`.

## Data (gs://poly-backup-54cb99b7/features/v1/, from p08, code version p08-v4)
Local copies go to `data/collector/p09/` (gitignored). Only these are used:
`1s/chainlink__btc`, `1s/polymarket__price_change`, `1s/polymarket__book`,
`1s/polymarket__last_trade_price` (trade aggregates, junk prints already
excluded, not raw events), `1s/binance_fut__btcusdt@bookTicker`,
`meta/polymarket__markets`, `meta/collector_log`, and `_manifest/*`.

**Split, fixed now (UTC dates):**
- **dev: 2026-07-25 → 2026-09-05.**
- **holdout: 2026-09-06 → 2026-09-20. Not read in this experiment at all.**
  The downloader refuses any path with `date=` ≥ 2026-09-06, and the loader
  asserts the same. As a consequence, the dev market set is every market
  whose whole life *and* end-TWAP window lie before 2026-09-06 00:00:00. A
  market whose end window needs a bar stamped 2026-09-06 is dropped.

**Hygiene (p08):**
- Hours are included only if the manifest shows the unit present for
  every stream a step uses. This is checked per hour, never assumed as
  24 h/day.
- Always excluded: 2026-07-25 h00–17, 2026-07-26 h01/h03/h04, and 2026-08-04
  h16–23.
- A market is used only if every hour touching [start − 60 s, end] is present.
- Polymarket 1s tables are keyed by (second, market, asset_id): one row per
  asset per second *with activity*, not one row per second. Series are
  forward-filled per asset within a market's life only.
- Chainlink: dedupe rounds by `updated_at` across hour files, since p08
  deduped within a row group only.

## Clocks (why this matters)
- Chainlink rounds: `updated_at` is the on-chain round time. The collector
  first sees a round a median ~473 ms later (SCHEMAS.md). For **settlement**
  (Step 1) the round time is used. For anything **tradeable** (Steps 2–3),
  a round counts as known only from `updated_at + observed lag`. The lag is
  the per-second `lag_ms` in the 1s table, falling back to the p95 of that
  lag if missing.
- Polymarket `price_change` is bucketed on its payload `timestamp` (ms).
  The collector receives it later. The per-bucket receive-lag columns are
  used the same way: book state is "known" at payload time + lag.
- `polymarket__book` has no payload clock, only receive time.
- The collector (europe-west3) sits ~127 ms behind Binance event time.
  Binance data is used only for volatility, and as a sensitivity check on
  "current price" (below).

## Important caveat, stated before looking
The markets resolve on **Chainlink Data Streams** "BTC/USD 60s TWAP"
(sub-second reports). The collector records **Chainlink's on-chain BTC/USD
aggregator on Polygon** (rounds ~33 s apart). These are different products.
Step 1 therefore measures how well a TWAP rebuilt from the on-chain rounds
reproduces Polymarket's actual resolutions. A match rate below 100% is
expected near ties. If the match is poor, nothing downstream is valid.

## Step 1: reconstruct settlement (dev)
- **Chainlink feed stats:** round update cadence (distribution of
  inter-round gaps), staleness (age of the latest round at each second), and
  per market, the number of rounds whose `updated_at` falls inside the final
  60 s window. Also the fraction of markets with 0 rounds in that window.
- **TWAP**, as the resolution text defines it: the time-weighted average
  of the price step function (each round's price held from its `updated_at`
  until the next round) over the 60 s window. Candidates:
  - **A (primary): trailing windows** [T_start − 60 s, T_start] and
    [T_end − 60 s, T_end].
  - **B:** point value, i.e. the last round at or before T.
  - **C:** windows forward of the start, [T_start, T_start + 60 s], with the
    end as in A.

  All three are reported. The settlement model used downstream is the one
  with the highest match rate. This is **one disclosed choice**, a
  measurement of the mechanism, not a trading choice. Outcome = Up if
  TWAP_end ≥ TWAP_start.
- **Polymarket's own resolution:** from `meta/polymarket__markets`, the
  latest snapshot of each market with `closed` = true and `outcomePrices`
  at {1,0}/{0,1}, mapped to the Up/Down token via `outcomes`.
  - If a market's metadata never shows a resolved state, it is counted as
    **unverifiable**. It is not guessed from late Polymarket prices.
  - If > 20% of dev markets are unverifiable from the collector metadata, I
    stop and ask the owner before using any external source (e.g.
    Polymarket's public API).
- **Report:** match rate over verifiable markets (overall, per candidate),
  mismatches by |TWAP_end/TWAP_start − 1| margin, and mismatch rate
  vs the number of rounds in the final window.
- **Gate for Step 2 (fixed now):** continue only if the best candidate
  matches ≥ 97% of verifiable markets. Otherwise STOP and report.
  **Regardless of the result, I stop after Step 1 and show the owner the
  match rate before continuing** (owner's instruction).

## Step 2: fair value vs market price (dev only)
For every second t of a market's life (after T_start, before T_end):
- **Current price S_t:** the latest Chainlink round *known* at t (receive
  clock). Sensitivity: the Binance futures mid, shifted by the median
  Chainlink−Binance log basis over the trailing 10 min. Primary is
  Chainlink, because that is what settles.
- **Volatility σ:** realised volatility of Binance futures 1s mid log
  returns over the trailing 15 min, per √second. Fixed, not tuned.
- **Model (a simple diffusion, as intended):** log price is driftless
  Brownian with vol σ. Model A is used for TWAP_start (known once t ≥
  T_start). For TWAP_end, the remaining variance is the variance of
  the 60 s average of a Brownian path, given the path up to t:
  - τ = T_end − t > 60 s: V = σ²(τ − 60) + σ²·60/3 = σ²(τ − 40).
  - τ ≤ 60 s: the already-elapsed part of the window is known (from
    rounds), and the rest has variance σ²·τ³/(3·60²).

  P(up) = Φ((m_t − ln TWAP_start)/√V), where m_t is the conditional mean of
  ln TWAP_end (current log price, blended with the known elapsed part in
  the last minute). The same settlement candidate as chosen in Step 1 is
  used.
- **Market mid:** the Up token's mid (best_bid+best_ask)/2 from
  `price_change` known at t. The Down token is used only to check that
  Up mid + Down mid ≈ 1.
- **Calibration check** (necessary before any gap means anything):
  reliability of model P vs realised outcome in 10 bins, and Brier score of
  model vs market mid, both on dev.
- **Report:**
  - the distribution of gap = model − mid by time-to-expiry bucket
    (0–30 s, 30–60, 60–120, 120–180, 180–240, 240–300 s);
  - the fraction of seconds with |gap| > the half-spread;
  - quoted size at the touch on the side to take when it does (from
    `polymarket__book` if a snapshot at the same touch price is ≤ 5 s old,
    otherwise **unknown and counted as 0**);
  - all of the above conditioned on Chainlink staleness (seconds since the
    last round was received: 0–2, 2–5, 5–15, 15–30, > 30 s). The
    hypothesis is that the gap is largest right after a feed update,
    before the book catches up.

## Step 3: what is actually takeable (dev only)
- **Signal:** at a second where the gap at decision time exceeds a
  threshold h, buy the underpriced token (Up if model > Up ask, Down if
  (1 − model) > Down ask) at its best ask.
- **Timing:**
  - decision time = the receive time of the triggering information;
  - order arrival = decision + L;
  - fill at the touch of the first 1 s price_change state known at or
    after arrival, **only if** that ask is still ≤ the price the signal
    required. Otherwise, no fill.
- **Size:** capped at the quoted touch size (as in Step 2; unknown = 0) and
  at the Polymarket minimum order size. At most **one fill per (market,
  token, Chainlink round)**, so the same liquidity is not counted twice.
- **Holding and cost:**
  - held to resolution; payoff 1 or 0 per contract, using Polymarket's
    actual resolution where verifiable, else the chosen settlement model;
  - **fees 0** (owner). `fee_rate_bps` is checked on a sample of raw
    `last_trade_price` events, and any non-zero value is reported;
  - **gas $0.02 per market position** (Polygon; the CLOB settles on-chain
    via the operator, and redemption is one transaction). Sensitivity:
    $0.10.
- **Pre-registered grid, all reported, nothing chosen:** h ∈ {1, 2, 3, 5}
  cents; L ∈ {150 ms, 500 ms, 1 s} (primary 500 ms: the collector-to-CLOB
  path plus signing is unmeasured). One `selection_trials.json` row per
  (h, L), 12 rows.
- **Report per config:**
  - trades per day and P&L per trade;
  - model edge at fill (fair − fill price), median and mean;
  - realised P&L (mean, t-stat with markets as the unit);
  - total $ of opportunity per day (notional takeable and model-edge $);
  - the size distribution.

## Kill criterion (fixed now; evaluated at h = 1 c, L = 500 ms, on dev)
**Abandon if the median takeable edge is < 1 cent per contract OR total
takeable size is < $50/day.**
- "Takeable edge" = model fair − actual fill price after latency, per
  filled contract.
- "Takeable size" = filled notional ($) per dev day, averaged over dev days
  with full coverage.

Realised P&L is reported next to it as the check on the model. If
realised P&L is negative while model edge is positive, the model is wrong,
and that is reported as such. Either way, **the holdout is not touched in
this experiment.**

## Deliverables
`research/p09_polymarket_fairprice/`: PLAN.md, `fetch.py` (dev-only
downloader + manifest check), `step1_settlement.py`, later `step2_*.py` and
`step3_*.py`, `*.json` outputs, RESULTS.md, REVIEW.md. No harness changes are
expected. If loaders become reusable, they go to `harness/` with tests,
after this experiment.

## Amendment 1 (2026-09-23, owner decisions; before any settlement or price analysis)
Found while fetching (structure only, no outcomes or prices analysed):
- `meta/polymarket__markets` holds one snapshot per market, taken when it is
  added (≈5 min before start; `closed` = False, prices ≈ 0.5). **The
  collector never records a resolution**, so 100% of markets are
  unverifiable from collector data. This trips the "> 20% unverifiable, ask
  the owner" rule above. The owner was asked.
- `resolutionSource` changes over dev. For 5m markets:
  - Chainlink `btc-usd` stream (a point price) for 2026-07-25 → 08-06
    (3,325 markets);
  - `btc-usd-twap-30s` for 08-07 → 08-13 (2,016);
  - `btc-usd-twap-60s` for 08-14 → 09-05 (~6,620).
- The chainlink stream is missing 2026-07-25 h22 on top of p08's list. The
  per-hour manifest check handles this.

Decisions:
- **Scope: all dev 5m markets** (~12k). Each is rebuilt with its **own**
  `resolutionSource` rule: point value at T for `btc-usd`, a 30 s window
  for twap-30s, a 60 s window for twap-60s. Window placement follows
  candidates A/B/C above, with the window length set by the rule. Results
  are reported per regime. 15m markets are out of scope. A market with
  window start ≥ 2026-09-06 00:00 is holdout, even if its metadata row was
  written on 09-05.
- **Resolution source: Polymarket's public Gamma API** (`/markets?slug=`),
  **dev slugs only** (window start ≤ 2026-09-05 23:55 UTC). No holdout slug
  is requested. Requests are rate-limited (~2/s) and resumable, and results
  are cached to `data/collector/p09/resolutions.parquet`. The response
  fields relied on are recorded. Markets Gamma reports as unresolved or
  void are **skipped, not guessed**. Polymarket is not reachable from the
  owner's machine, so the fetch runs on a throwaway GCE VM (europe-west3,
  e2-small), which is deleted afterwards.
- **Three agreement rates replace the single match rate:**
  - (a) rebuilt Chainlink outcome vs Gamma resolution. **This is the one
    that matters.**
  - (b) final Polymarket Up mid (> 0.95 → Up, < 0.05 → Down, else no call)
    vs Gamma resolution.
  - (c) rebuilt outcome vs final mid.

  Here, "final mid" = the last Up-token mid known in [T_end − 5 s, T_end +
  60 s] (the book near and after expiry). This is a secondary check, not a
  replacement.
- **Step-1 gate raised to ~99% for (a), replacing 97%.** If (a) < 99%,
  STOP and show every disagreeing market: start/end TWAP, the margin
  |TWAP_end/TWAP_start − 1|, and the number of rounds in each window.
  Failures at near-ties are expected. Systematic failures mean the
  reconstruction is wrong.

## Amendment 2 (2026-09-24, owner's Step 1b; written before spot data is fetched or any Binance TWAP is computed)
Step 1 gave 92.0% agreement (rebuilt on-chain vs Gamma, gate 99%). Step 1b
rebuilds the same markets' settlement from the **Binance mid** instead.
Dev data only, no new collection, holdout untouched.

- **Markets:** the 11,958 of Step 1 (Gamma-resolved, complete Chainlink
  hours). A market also needs the bookTicker hours for its windows. Markets
  without them are counted and left out per series.
- **Series** (1s bookTicker tables): futures, spot, and a 50/50 blend of
  the two (average of log mids).
  - **Futures** is bucketed on Binance event time `E`, so it needs no lag
    correction.
  - **Spot** has no payload clock and is bucketed on collector receive time.
    It is shifted back by **133 ms**, the median spot receive lag (p08
    SCHEMAS.md, spot `@trade`). A window [a, b] in exchange time therefore
    uses receive buckets a…b weighted 0.867, 1, …, 1, 0.133.
  - Missing seconds carry the last mid forward.
- **Rule windows, matching each market's own rule:**
  - `btc-usd` = point: the last mid before T, i.e. `mid_last` of bucket
    T − 1.
  - twap-30s / twap-60s = the mean of per-second `mid_twap` over [T − W, T]
    at both start and end (candidate A).

  A (trailing) is primary. B (point at both ends) and C (forward start
  window) are reported alongside, as in Step 1. Up if end ≥ start.
- **Report:** agreement vs Gamma per rule period and overall, and by the
  Step-1 gap buckets, measured both on the Binance series' own gap and on
  the on-chain gap. The on-chain numbers (87.3 / 93.2 / 94.0, overall 92.0)
  are shown next to them.
- **On-chain Chainlink vs Binance mapping.** At each Chainlink round time
  u, the Binance mid at u − k is used, for k = −10 … +60 s:
  - the residual log(CL) − log(Binance), after removing a rolling 1 h
    median basis, with its std in bp per k. The k with the smallest std is
    the lead/lag.
  - At that k, the round-to-round returns of CL are regressed on Binance
    returns over the same intervals: slope, R², residual std in bp.
- **Decision rule (owner):**
  - Binance agreement **≥ 99%**: p09 continues with Binance as the
    fair-value input, and on-chain Chainlink is used only for
    cross-checks.
  - **~95–98%**: report and stop for a decision.
  - (Below 95%: report and stop.)
  - The series named here (futures, spot, blend) are the only ones
    compared, and the best of them is reported as the best. That is a
    disclosed choice among 3 × 3 = 9 variants.
