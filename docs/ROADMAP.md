# Roadmap — forced-flow line (Hyperliquid) + write-up

Written 2026-09-24. Supersedes the scattered "next steps" in p09–p11 reviews.
Everything here serves one thesis; anything that doesn't is in "Parked" at the bottom.

---

## 0. The thesis

**On Hyperliquid, forced liquidations are visible before they happen. Be the liquidity they
trade against, and only act when the expected move exceeds the measured cost.**

Why this and not another predictor:
- p01–p11 established that predicting BTC direction from public data does not clear costs at
  1h/4h. The required AUC (~0.57–0.59 for 4 bps) is far beyond the 0.545 that four years of
  feature work produced.
- The remaining edge for a small trader is **structural, not predictive**: find someone who is
  obliged to trade regardless of price, and be on the other side.
- Hyperliquid is the only venue where positions and liquidation levels may be **publicly
  visible in advance**. That is information no centralised exchange gives you, and it is free.

Each stage below has a kill criterion fixed before it runs. Stage 0 is decisive and cheap: if
liquidation-level data is not public at usable granularity, the line dies there having cost
two days.

---

## 1. Repo decision: same repo, renamed

Keep working in `ml4t-harness`. Rename it to something line-agnostic (e.g. `quant-research`
or `market-research-harness`) and keep one repo, because:
- the harness (labels, purged CV, backtester, metrics, nulls), the measured cost model
  (`harness/costs.py`) and the p08 reduction pattern are all reused as-is;
- `CLAUDE.md`, the `research-reviewer` agent and the `/experiment` command carry the discipline
  across lines;
- one repo tells a better story than two: "a research harness, and the lines tested with it".

Structure going forward:

```
research/
  p01..p11_*/        # closed line: BTC bar direction (do not reopen; see CLAUDE.md)
  p12_hl_survey/
  p13_hl_collector/
  p14_hl_event_study/
  p15_hl_entry_rule/
  p16_hl_selection/
  p17_hl_holdout/
docs/
  README.md          # the front door
  report.pdf         # 6-8 page write-up of the closed line
  figures/
```

Add to `CLAUDE.md` when the line starts:
- the 1h/4h BTC bar-direction line is **closed permanently** (p10b kill);
- the HL line has its **own** dev/holdout split and does **not** share `trials.json`;
- keep `trials.json` for the closed line; start `trials_hl.json` for this one.

---

## 2. Stage 0 — API survey (2 days, decisive)

**Question:** what does Hyperliquid actually expose publicly, and at what granularity?

Paste to Claude Code:

```
/experiment p12_hl_survey

Survey only. No collector yet, no trading logic, no trials.

Goal: determine exactly what Hyperliquid's public API exposes, so we can decide whether the
forced-flow thesis is testable. Report facts with endpoint names, response shapes, limits.

Cover:
1. Market data: l2Book (depth, update rate), trades, candleSnapshot, allMids,
   metaAndAssetCtxs (mark price, oracle price, funding, open interest). Websocket vs REST,
   rate limits, whether snapshots or deltas.
2. THE DECISIVE ONE — position and liquidation data. Determine whether any of these are
   public, and at what granularity:
   - per-address position state (size, entry, leverage, liquidation price)
   - any aggregate of open positions or liquidation levels by price bucket
   - a liquidations feed or liquidation events (websocket topic, explorer, or fills stream)
   - the explorer's transaction/fill stream, and whether liquidations are identifiable in it
   - leaderboard-style endpoints listing large accounts
   For each: exact endpoint, what it returns, how often it can be polled, and whether it can
   be reconstructed historically or only recorded going forward.
3. Universe: which perps have meaningful volume/open interest on HL (report top 10 by both).
4. What a collector would cost: message rates per stream, estimated GB/day for BTC+ETH+SOL
   plus 2-3 mid-caps, and whether the existing e2-small can carry it.

Write research/p12_hl_survey/SURVEY.md with a verdict section answering:
can we, going forward, know where forced liquidations sit BEFORE they happen? yes/no/partly.
No new dependencies beyond an HTTP client. Do not start recording anything yet.
```

**Kill:** if liquidation levels are not obtainable (directly or by reconstruction from
position state), stop. Fall back options are in "Parked".

---

## 3. Stage 1 — collector (build in 2-3 days, then runs 6-8 weeks)

Only if stage 0 says yes/partly.

- Streams: HL l2Book, trades, funding/OI context, and whatever position/liquidation data
  stage 0 found. Plus **matched Binance** BTC/ETH/SOL bookTicker+trades for cross-venue work.
- Reuse the p08 conventions exactly: hourly parquet per stream, manifest per unit, CRC checks,
  resumable, written to GCS. The p08 reducer extends to new streams cheaply.
- Run on the existing VM (check headroom first; HL books are chatty). Keep the collector
  process separate from the Polymarket one so a crash in either is isolated.
- **Target 6–8 weeks, not 4.** The unit of observation is a liquidation event; you want
  thousands of them, including at least one violent day.
- Daily health check: hours present per stream, message counts, gaps. p08 showed an 8-hour
  silent outage; catch those within a day, not at analysis time.

**Split, fixed the day collection starts:** first 75% of the calendar span is dev, last 25% is
holdout, untouched until stage 5.

---

## 4. Stage 2 — event study (no trial, ~1 week once data exists)

**Question:** do forced liquidations produce a mechanical, exploitable price move?

Measure, per liquidation event (and per cascade, defined as events clustered within N seconds):
- size, side, price relative to mark and to the book at that instant;
- price path from −60s to +300s, in vol units and in bps;
- how much of the move happens *before* the event (already priced in);
- book depletion and spread widening during the event, and refill time;
- the same conditioned on event size deciles and on whether the level was visible in advance;
- cross-venue: does Binance move first, simultaneously, or after?

**Kill:** if the median post-event reversion is smaller than HL's spread plus fees at the
sizes involved, the thesis is dead. Report the distribution, not just the median — the tail
may be where the business is, in which case say so explicitly and re-scope to large events.

---

## 5. Stage 3 — entry rule (dev only)

Simplest thing that captures the measured effect, pre-registered before it runs:
- passive: resting bids stacked below visible liquidation clusters;
- or aggressive: take after the cascade prints, hold for the measured reversion horizon.
- Costs: HL's actual fee schedule (maker/taker), measured spread, and a queue-aware fill
  assumption. Do **not** reuse p05's Binance cost table; measure HL separately.
- Report breakeven bps per unit traded, turnover, and edge per event, exactly as p02–p10 did.

**Kill:** pre-OOS breakeven below 2x measured cost.

---

## 6. Stage 4 — selection layer (the "selectivity" idea, in its right place)

Only meaningful if stage 3 shows an edge. Filtering a signal with no edge yields fewer trades
with no edge — that is why running meta-labelling on p10's dead signal was dropped.

- Primary model = the stage 3 entry rule, frozen.
- Secondary model answers "act on this event or not?", using features the primary did not see:
  volatility state, book depth and refill speed, time since last cascade, funding extremity,
  cross-venue spread, size of the visible cluster below.
- Evaluate as precision: trades taken vs average edge per trade vs breakeven bps, swept over
  the secondary model's threshold.
- **Baseline it must beat:** the naive "take every event above size X" rule. If it cannot beat
  that, selectivity added nothing.
- Power note in PLAN.md: filtering to the top 20% of events means 20% of the sample.

Resources (video first):
- Joubert, *Meta-Labeling: Solving for Non-Stationarity and Position Sizing* (YouTube)
- Hudson & Thames, *Meta Labeling (A Toy Example)*
- Singh & Joubert, *Does Meta-Labeling Add to Signal Efficacy?*
- Joubert et al., *Meta-Labeling: Theory and Framework* (SSRN 4032018)
- hudson-and-thames/meta-labeling (GitHub)
- QuantConnect, *Why Meta-Labeling Is Not a Silver Bullet* (read early)

---

## 7. Stage 5 — holdout and decision

- One run on the held-out final 25%. One trial logged in `trials_hl.json`.
- Pass: net positive after HL fees and a conservative fill model, with margin.
- Then either paper-trade live for 2-4 weeks (infrastructure test, not a second chance for the
  strategy) or write it up and stop.

---

## 8. Discipline carried over (non-negotiable)

1. Kill criteria fixed in PLAN.md before any data is read.
2. Holdout untouched until stage 5; every look costs a trial and raises the DSR bar.
3. The `research-reviewer` subagent reviews every stage before it is accepted.
4. Never loosen a threshold to make a result pass. A failed stage is reported as failed.
5. Costs always on, and measured for the venue in question.
6. Validate any new data source against ground truth before building on it (p08's zero-price
   prints; p09's settlement mismatch).
7. Report effective sample size and the standard error next to every Sharpe-like number.

---

## 9. Parallel track — the write-up (2-3 days, while data accumulates)

Not research; packaging. Do it in the gaps, aim to have it sendable in October.

- `docs/README.md`: what the harness is, the 11 experiments in one table, the three general
  findings, how to reproduce.
- `docs/report.pdf`, 6-8 pages: question, method, results, what each kill taught.
- Four figures:
  1. IC decay by horizon (p03);
  2. breakeven bps vs measured cost across p01-p10;
  3. required AUC vs breakeven (p10b), with the best real AUC marked;
  4. p07 vs p07b — the survivorship gap (2.67 -> 0.66).
- Decide the TCN: either fix the input scaling and rerun once as a documented footnote, or cut
  it from the narrative. Do not leave "we tried deep learning and it failed" implied.
- Strip bucket names, project ids and anything credential-shaped before publishing.
- Be able to defend every design choice out loud: purging and embargo, the deflated Sharpe,
  why trials are budgeted, why the near-tie exclusion was wrong in p09.

---

## 10. Parked (not dead, just not now)

- **p11 external signals** (Deribit DVOL, Binance liquidationSnapshot, cross-venue funding).
  A separate thesis. Revisit only if the HL line dies at stage 0 or 2.
- **p11 RTDS settlement check** (Polymarket's rebroadcast feed, recording since 2026-09-24).
  Cheap to run later; the feed accumulates in the meantime.
- **Variance risk premium on Deribit.** Most likely to actually make money, needs options data
  and real risk management. A serious project in its own right.
- **Prediction markets beyond crypto** (Polymarket/Kalshi sports, weather, politics).
  Retail-dominated, zero fees, documented favourite-longshot bias, small size is an advantage.
  The closest cousin to this line's logic.

---

## 11. Known risks to this line

- Liquidation levels may not be public at useful granularity -> stage 0 kills it.
- The effect may be real but already arbitraged by faster participants; the event study should
  show how much of the move happens before the event.
- HL fees and spreads may be wide enough to eat the reversion; measure them before modelling.
- 6-8 weeks may contain no violent day, leaving the interesting tail unsampled. If so, say the
  sample is regime-limited rather than concluding.
- Latency: you are in Istanbul on a cloud box. If the edge needs sub-100ms reaction, it is not
  yours. The event study should report how long the opportunity persists.