# Review: p12_hl_survey
**Decision (round 2):** ACCEPT. Round 1 was ACCEPT WITH FIXES, and all 5 blocking items are now resolved. Two small corrections remain, listed below as non-blocking.
**One line:** Per-address liquidation prices are public. The accounts we can find hold about 12–19% of BTC OI at a ≤ 1 min refresh, about 32% at 5–18 min, and about 40% (38–44%) using every source we found. The rest (~60%) is off the leaderboard and of unknown concentration. "PARTLY" is the correct verdict under PLAN.md, and the pre-registered bar for "yes" is missed by a wide margin.

## Round 2 (2026-09-25; files only, no network)
Re-checked against the files. `probe.py tailci` was re-run offline and reproduces `probe.log` exactly.

| round-1 blocking item | status | evidence |
|---|---|---|
| 1. coverage and cadence reported for different address sets | fixed | §2b now has a refresh-vs-coverage table, and the verdict gives the pairs. Top 600 = 18.87% BTC / 31.45% ETH, recomputed from `coverage_positions.json` |
| 2. false "nothing within ±5%"; mixed denominators | fixed | §2d gives ETH 0.11%, and 4.25% one-sided = 2.1% gross |
| 3. "spread across many accounts" | fixed | replaced with "off-leaderboard, concentration unknown" |
| 4. no error bar on the tail scale-up; the 1008 accounts | fixed | BTC 5.2% [2.7–8.5], ETH 2.0% [0.7–3.7], HYPE 4.7% [2.4–7.4]. The first 8 addresses are HLP (index 0 = HLP vault), not scaled; all HLP positions come from index 1, and its BTC position is 0.53 BTC. My round-1 guess that ranks 1002/1004 were HLP was wrong: they are sampled accounts |
| 5. "measured" claims with no script | fixed | `probe.py` covers the universe, leaderboard count and tail draw (seed 12), the overlap (1439 → 1183, 17.8%, matches the addrs files), the l2Book cadence (re-run: median 5.39 s) and `tailci` |

Non-blocking items from round 1 are addressed: the +1.7% OI drift, one-sided OI stated as an inference, the kill-criterion caveats, conditioning only possible going forward, rows vs messages, the unknown archive span, the gitignore entries, and `trials.json` = p01–p11.
CLAUDE.md line 82 ("p09, p12" Polymarket) is deliberately left for the owner. That is the right call, since this reviewer cannot authorise CLAUDE.md edits.

### Remaining non-blocking corrections (text only; they change no verdict)
- **The "≳ 30 min, all sources" row in the §2b table is wrong.** The ~5% from the tail requires polling all 43,797 tail accounts, not the
  1000 sampled. Everything together is about 48.3k accounts: about 80 min at the 10/s weight limit, and about 5 h at the measured 2.7/s. Change it to
  "≈ 80 min (limit) / ≈ 5 h (measured)".
- **The ≤ 1 min row is rate-limit arithmetic at 10/s, which has not been achieved.** At the measured sequential 2.7/s, 1 min covers the top ~160 accounts =
  **11.7% BTC** / 16.7% ETH. The verdict should say "~12–19% at ≤ 1 min" instead of "~19%".
- **The §3 universe table quotes the 2026-09-24 first run, which no committed file holds.** `probe.log` is a later re-run with different values (ranks 1–7 unchanged).
  Acceptable as dated, but mark it "first run, not in probe.log".
- **The tail draw cannot be reproduced from the repo.** It depends on that day's leaderboard, and `addrs_*.json` are gitignored. That is fine for a survey; state it as a limit.

---
## Round 1 (superseded decision: ACCEPT WITH FIXES)

## Numbers checked (SURVEY.md vs outputs)
All of these match: top-3000 BTC gross coverage 32.3% (top100/300/1000 = 7.3/14.3/22.8), ETH 39.7%; liqPx non-null
94.9% BTC, 87.1–94.6% for the others; cross 87.4–97.8%; ±2% band = 4.25% (two positions: $97.9M long at −1.73% 35x cross,
$42.3M short at +1.18% 40x isolated); tail ×43.8 → BTC 5.3%, ETH 2.0%, HYPE 4.7%; trades-stream addresses 1.0%;
sub-accounts 31/150, 305 subs, 0 on the leaderboard, BTC 2.2%; WS 47.2 msg/s, 1.32 GB/day, bbo 35.3, trades 4.7 msg/s /
10.2 prints/s, BTC 2.89 prints/s; l2Book 0.187 msg/s per coin (5.4 s gap); 3000 polls in 1102 s = 18.4 min.
Sum 32.3+5.2+1.0+2.2+0 = 40.7%, reported as "≈ 40%". OK.

## Blocking issues (fix SURVEY.md before stage 1 is started on the strength of it)
1. **The coverage figure and the cadence figure are for different address sets.** The ≥70% bar is coverage *at ≤ 1 min*.
   The 40% is at 5–18 min, and the 5 min figure is not even measured (it is weight arithmetic: 10 req/s needs about 4
   concurrent streams at 0.4 s latency. Latency from europe-west3 was not measured). At 1 min, about 600 accounts fit, which is about
   15–18% of BTC OI (between the top300 figure of 14.3% and the top1000 figure of 22.8%). The verdict should give the pair: "~16% at 1 min, ~32% at
   ~5 min (unmeasured), ~40% at 18 min plus a 10-min discovery window." It is still PARTLY, but a weaker PARTLY than the text suggests.
2. **False sentence in §2d:** "Nothing within ±5% for the other five coins." ETH has 0.11% of OI within ±5%
   (two positions, ranks 1350 and 2052, at −4.5% and −4.7%). Also, the ±2% and ±5% bands are |szi|/OI (one side), while coverage
   is gross/(2·OI). So the 4.25% is 2.1% on the coverage scale. State the denominator.
3. **Unsupported interpretation in §2b:** "OI is spread across many accounts, not concentrated in a findable few." The
   tail sample says the opposite about the leaderboard: ranks 3001–46,797 (43,797 accounts) add only ~5%. So the
   missing ~60% is **off the leaderboard**, and nothing measured tells us whether it sits in a few large accounts
   (market makers, vaults, sub-accounts of non-top masters) or in many small ones. Replace the sentence with that.
4. **Tail scaling uncertainty is not reported.** BTC positions in the tail are heavy-tailed (top-10 accounts = 74% of tail
   BTC notional). Bootstrapping the 1008 polled accounts gives a 95% range of **2.7%–8.4%** for the scaled 5.2% (and that range
   probably understates it for a power law). Also: the file has 1008 addresses, not 1000. If the 8 extra are HLP + 7 children,
   they were scaled ×43.8 too (ranks 1002/1004 hold HYPE/UNI/NEAR, so HYPE is inflated by ≤ ~0.5 pp. BTC is unaffected). Say which it is.
5. **"Measured" claims with no committed script or output:** PLAN.md names `probe.py`, which is not in the folder. Nothing
   reproduces the l2Book cadence (p10/p50/p90), the universe table, the 1103 `allMids` keys, the 46,797 leaderboard rows,
   "17.8% of trade addresses on the leaderboard", HLP 0.0%, or the random draw of the tail sample (no seed, no script). Either
   commit `probe.py` and a small `probe.json`, or relabel these as "measured, not reproducible from this folder".

## Non-blocking issues
- **Overlap between sources:** 2 addresses appear in both the top-3000 (day 1) and the tail sample (day 2), which comes from leaderboard
  rank drift between the two pulls. Sub-accounts (not on the leaderboard) versus trades-stream addresses (not on the leaderboard) cannot be checked, because
  `subaccounts.json` stores no addresses. The worst-case double count is 1.0 pp. Adding snapshots from two days is acceptable at this
  precision (BTC OI 39.0k vs 39.7k coins, +1.7%, not the "<1%" stated; mark 84,583 vs 83,969), but say so.
- **OI semantics assumed:** `openInterest` is treated as one-sided. That fits long%OI ≈ short%OI in the top 3000 (32.8/31.7),
  but it is not documented in the survey. State it as an inference.
- **Weak pre-registered gate:** PLAN's "partly" has no lower bound. Once `clearinghouseState` existed, only "no" could kill the line,
  and "no" was already ruled out. This was not relaxed after the fact, but it means stage 0 could not really fail. The next step needs a numeric bar.
- **The "partly continues only if the event study can be conditioned on it" clause is asserted, not shown.** Conditioning needs the
  covered share *per event*, and history has no position state at all. So the conditioned study can only run on forward data.
- **Documented, unverified facts are mostly labelled correctly.** Where they are not:
  - "every address that ever traded appears in `node_fills_by_block`" assumes the archive starts at genesis. The start date is unknown.
  - "`--serve-info` … without the public rate limit" and "`periodic_abci_states` hold every position" are documentation claims, and "only path to complete coverage" rests on them.
  - "several hundred USD/month" is unpriced.
- **e2-small:** "~2,150 msg/s" is p08's 186 M *rows*/day, not messages. An e2-small is a shared-core machine with a 50% sustained CPU baseline. Headroom
  is unmeasured, which the survey admits. Fine as written, provided "should fit" is not repeated elsewhere as a finding.
- `ws_rates.py` writes to a hard-coded session scratchpad path. `coverage_*.json` are not in `.gitignore`, although SURVEY says they will not be committed.
  Add `research/p12_hl_survey/coverage_*.json` to `.gitignore` before `git add` of the folder.
- CLAUDE.md line 21 says `trials.json` covers "p01–p12", and line 82 names p12 as Polymarket latency work. p12 is now this survey. Fix the numbering there.

## What the evidence supports
- Liquidation prices for any known address: public, exact, cross/isolated flagged, ~2.5–2.7 polls/s sequentially.
- Enumeration from public sources: leaderboard top 3000 ≈ 32% of BTC OI. Everything else found adds about 8 pp (±3). The residual ~60% is off-leaderboard
  and of unknown concentration.
- No public liquidation feed. Liquidations are inferable only for tracked addresses. Historical events are *documented* to exist in S3 fills
  (not verified).
- The collector's market-data load is small (47 msg/s, 1.3 GB/day raw on a quiet evening).
- One snapshot showed $140M within ±2% of BTC mark in two accounts. That is n=1 and says nothing about frequency.

## Proposed next experiment
Do not build the stage-1 collector yet. The cheapest decisive test of the whole thesis does not need the map. It needs
historical liquidation events, and those are documented to exist in S3. One pull answers both open questions: whether liquidations
move price enough to matter (the stage-2 kill criterion), and which addresses exist (the coverage gap).

**p13_hl_liq_history**, in two steps:
- **Step A: price the pull (no download).** List `s3://hl-mainnet-node-data/node_fills_by_block` (requester pays). Record the archive start date,
  the bytes per day, and the egress cost. Decide before any download: if the archive covers < 3 months or the cost is > $50, stop and fall back to the
  forward trades-stream address logger (below).
- **Step B: run the stage-2 event study on history, as a no-trial study.**
  - **Hypothesis:** BTC liquidation fills on HL are followed within 60–300 s by a reversion (price moving back against the liquidation's
    direction) whose median, in bps, is at least HL's documented base-tier taker fee plus the measured half-spread.
  - **Change vs p12:** add the historical fill data source. Nothing else.
  - **Pre-OOS plan:** fix the dev/holdout split by calendar before loading any fills (first 75% dev), and analyse dev only. Take the price path
    from the fills themselves (the HL trade tape) and cross-check it against free Binance aggTrades. Before building on the fills, validate the loader against
    ground truth: HL `candleSnapshot` for the last 3.5 days, and `userFills` liquidation records for a few known addresses (rule 6).
    Also extract the full address set, poll it once, and report BTC OI coverage, with the time the poll takes, next to the p12 numbers.
  - **Kill criteria, decided now:**
    - Thesis dead if the dev median reversion at every horizon in {60, 120, 300 s} is below
      taker fee + half-spread, both for all events and for the top size decile.
    - Map path dead, and the thesis narrowed to "tracked large accounts" only, if the full historical address set still attributes < 70% of BTC OI.
  - **Expected cost:** 0 trials (it is an event study, as in ROADMAP §4, and the holdout stays untouched), S3 egress (priced in step A), a few hours of polling.
- **Fallback if step A fails:** run a 72-hour trades-stream address logger (addresses only, in memory, then dumped), poll the union, and plot coverage against
  window length. Kill criterion: if coverage is < 50% after 72 h and still flattening, scope the thesis down to the tracked-accounts version.
