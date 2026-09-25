# p12_hl_survey — plan

Stage 0 of the forced-flow line (docs/ROADMAP.md §2). Survey only: no collector, no
trading logic, no trials, nothing written to `trials_hl.json`. There is no model, so there is
no pre-OOS selection, no OOS gate and no fold-id test.

## Question
What does Hyperliquid's public API expose, and at what granularity? Decisive sub-question:
**can we, going forward, know where forced liquidations sit BEFORE they happen?**

## Hypothesis (falsifiable)
Per-address position state including a liquidation price is public, and the set of addresses
holding open interest can be enumerated well enough (directly or by reconstruction) to build a
liquidation-level map by price bucket that covers a large share of open interest.

## Change vs previous experiment
New venue and new line; p11 was the last experiment on the closed Binance line. Nothing is
carried over except the harness and the discipline.

## Method
1. Read the official API docs (info endpoint, websocket subscriptions, rate limits).
2. Verify every claim against the live public API with small, rate-limit-respecting calls
   (`requests`/`websocket-client`, already installed; no new dependencies). Record the
   response shapes actually returned, not the documented ones.
3. For the decisive items, measure rather than assume: how many addresses appear in the
   trades stream per minute, what share of OI a sample of addresses accounts for, and how
   fast per-address state can be polled under the published limits.
4. Measure message rates on the websockets over a short window (minutes, in memory only;
   nothing recorded to disk beyond the summary numbers) to size a collector.

Scripts: `probe.py` (REST), `ws_rates.py` (websocket rates, short window). Output: `SURVEY.md`
with a verdict section.

## Kill criterion (fixed now, from ROADMAP §2)
If liquidation levels are **not obtainable, directly or by reconstruction from position
state**, the verdict is **no** and the line stops at stage 0 (fall back to "Parked").
Operationally:
- **yes**: per-address liquidation prices are public AND the addresses holding the bulk of OI
  (≥ ~70% of BTC OI) can be enumerated and refreshed at ≤ 1 min cadence within public limits;
- **partly**: liquidation prices are public but coverage or refresh cadence falls short of
  that (e.g. only the largest accounts, or only a minority of OI);
- **no**: no per-address liquidation price or position state is public, and no aggregate of
  it exists.
"partly" continues to stage 1 only if the covered share is stated and the event study can be
conditioned on it.
