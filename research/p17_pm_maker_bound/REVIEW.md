# Review: p17_pm_maker_bound
**Decision:** ACCEPT WITH FIXES. The measurement is sound. On verified inputs the kill fires. Several descriptive claims overreach.
**One line:** Across all makers in Polymarket 5-min BTC markets, P&L before rebates is ~0 (−0.06 ¢/share, t −0.9; share-weighted +0.11 ¢, t 1.2). The 20% rebate adds 0.19 ¢/share and takes the registered statistic to +0.13 ¢, t 1.82 < 2. The maker line for these markets closes. That is the third consecutive Polymarket kill (p09, p15, p17).

## Answers to the four questions

**(a) Maker P&L = −(taker P&L before fees): correct. Each API row is exactly one taker order.**
- The data has 3,479,125 rows and 3,479,125 distinct `transactionHash`. Every match tx holds exactly one taker
  order. The `drop_duplicates` in `trades()` removed 0 rows.
- I checked 65 rows on-chain: 25 random SELLs, 25 random BUYs and 15 with >500 shares. Each one matches the
  taker's own `OrderFilled` (the event whose taker field is the exchange) on side, size and price, to 1e-10.
  The API price is the taker's **average execution price** across all maker fills, up to 50 per tx. So the sum
  over makers equals −taker exactly.
- Mint and merge matches need no special case. Example: a taker BUY of Up at 0.01 filled by makers BUYING Down
  at 0.99 (tx 0x27756f…). A maker who buys Down at 1−p gets (1−1{Up}) − (1−p) = p − 1{Up}. That is the same as
  selling Up at p, so the YES-equivalent mapping (outcome 1 at q → p = 1−q, side flipped) is right.
  Maker-maker matches do not exist outside a taker order, so nothing is missed or counted twice.
- Outcome mapping sanity check: trades after the window end have mean p_up 0.99 when Up won and 0.03 when it lost.

**(b) Rebate model: 20% is verified on-chain, and the allocation in the code matches Polymarket's. RESULTS describes it wrongly.**
- I checked the actual daily payouts. Maker rebates arrive around 00:45 UTC from `0xfdb1b8dc…`, through the
  disperser `0xd152f549…`. I divided each payout by the maker's previous-day fee-equivalent, Σ 0.07·shares·p(1−p)
  over its maker fills (all `OrderFilled` with that maker, from `eth_getLogs`). Result: **0.1997, 0.1998, 0.1997,
  0.1997** (3 wallets, 4 wallet-days; two of the wallets are 100% BTC-5m makers).
- So the program pays **20% of the fee, weighted by fee-equivalent (∝ p(1−p) per share), not per share**. It is
  paid per maker per day. Makers pay no fee: 0 on 63/65 txs, $0.10 in total on the other 2.
- `step1.py` assigns 0.2·fee·p(1−p)·size to each fill. That is exactly the program's allocation, so at fee 0.07
  the group number is **exact, not a bound**. But RESULTS calls it "pro rata to every maker share (an upper bound
  on any one maker's share)". That is wrong on both counts. A maker who quotes only near 50 ¢ gets
  0.35 ¢/share, against the 0.19 ¢ average.
- Fee 0.07 is confirmed: 24/24 in `onchain_fee_check`, 65/65 in my sample, from p = 0.001 to 0.98, with implied
  rate 0.0700. A few small fills show 0.078–0.087 (rounding on per-fill fees). The 0.10 reading of
  `takerBaseFee=1000` is **factually false**, not "generous".
- There is an unmodelled second payer, `0x520bf77d…`: $897 and $207 on consecutive days to one wallet (0.21× and
  0.29× its fee-equivalent, so not fill-based). This looks like liquidity rewards. It did **not** pay the two
  pure-BTC-5m makers in the same window, so it most likely belongs to other markets. That is not proven:
  `fetch.py` did not keep Gamma's rewards fields (`clobRewards`, `rewardsMaxSpread`, `rewardsMinSize`). If BTC-5m
  has a quoting-rewards pool, maker income is understated.

**(c) Handling: "not credited" is directionally right. State it as a kill on verified inputs.**
- This is not loosening; it is the opposite. The amendment picked 0.10 as a stand-in for an unknown fact. The fact
  is now measured, and it does not depend on the P&L.
- There is no asymmetric-scrutiny problem. The statistic is monotone in the fee rate, so a kill at 0.10 would
  also have been a kill at 0.07. The check could only ever move the result toward a kill.
- The kill is also robust to how the t-stat is computed:

| t-stat at fee 0.07 | value |
|---|---:|
| i.i.d. across markets (as registered) | 1.82 |
| Newey-West, lags 6–48 | 1.57–1.68 |
| day-clustered (8 days) | 1.56 |
| lag-1 autocorrelation of per-market P&L | 0.03 |

- Recommended record: the registered evaluation did not fire, but it rests on a false input (0.10). With verified
  fee and rebate the registered rule fires, and the line closes per PLAN. This matches p07 in spirit. The title
  "passes as registered" invites misreading.

**(d) The descriptive tables use the false 0.10 row, and two claims do not hold** (see Blocking).

## Blocking issues
1. **The "makers lose before rebates" claim is wrong** (headline, and the first bullet of "What this means").
   Equal-weight is −0.063 ¢ with t −0.91. Share-weighted is **+0.108 ¢ (t 1.23)**, and the no-rebate $ column is
   **+$14.8k/day**. Write "≈ 0 before rebates".
2. **The descriptive tables use fee 0.10**, a rate now known to be false. Redo them at 0.07 (and at no rebate)
   and add the by-market t per bucket (it is already in the json).
3. **The size table is misread.** Size is in shares.
   - 65% of the ">1,000 shares" volume trades at ≤5 ¢ or ≥95 ¢ (lottery tickets and near-certain buys), against
     12–16% for ≤100 shares. "Large takers" in shares are mostly cheap tails.
   - By $ notional the pattern is not monotone (no-rebate by-market t: ≤$5 +3.8, $5–50 −6.9, $50–500 −0.3,
     >$500 +2.2).
   - Delete "small, fast bots pick off stale quotes … exactly the flow a slow maker cannot avoid", or mark it as
     conjecture.
4. **The price claim is a rebate artefact.** "Makers earn least at the extremes" holds only with the rebate, which
   is ∝ p(1−p). Without it, mid-prices are worst (0.4–0.8: −0.06 / −0.02 ¢) and the tails are +0.14 / +0.07 ¢.
5. **Fix the rebate description** as in (b), and add the payout verification (the ratios above, the payer
   address, the method).
6. **Add the robust t-stats** (Newey-West, day-cluster). Disclose that the **share-weighted** figure at 0.07 is
   +0.30 ¢, **t 3.46**. It is not the registered statistic, but it is the one number that points the other way,
   so the owner should see it next to the kill.

## Non-blocking issues
- The code implementing amendment 1 (the 0.10 / 0.07 / 0 runs in `step1.py`) was committed with the results
  (f3cb0c9), not with the amendment (052c94d). The amendment text specifies the change fully, so this is
  process only. The line "scripts committed before any trade was read" is true only of the original version.
- The on-chain fee check (one receipt per trade) was cheap and possible before amendment 1. Lesson for PLANs:
  verify fee and rebate parameters on-chain before registering them, not after the P&L.
- **The "upper bound" argument is asserted, not shown.** The group mean includes slow retail limit orders as well
  as fast makers, so a *selective* maker could do better than it. It bounds only a maker with the group's flow mix
  and worse latency. The closure is safe anyway on economics: the whole margin is the 0.19 ¢ rebate, and one
  stratum alone moves makers by ±0.7 ¢ per share before rebate (≤100 shares −0.65 to −0.74 ¢; >100 shares
  +0.54 to +1.45 ¢).
- Volume gate: of the 89 failures, 73 are markets where Gamma's volume counter is 0. That is a Gamma artefact,
  not missing API data. The other 16 are real mismatches.
- `selection_trials.json` has only the 0.10 row. Add the verified-input evaluation as a second measurement row.
- Bookkeeping:
  - CLAUDE.md "current line" still names NEWPLAN #2.
  - The NEWPLAN status line omits #4.
  - CLAUDE.md lists `trials_hl/pm/vrp.json` as committed, but only `trials.json` exists.
- No harness change, and no threshold or verdict was loosened. There is no trial-log entry, which is correct:
  zero trials.

## What the evidence supports
- The data covers 2,304 markets, 3.48 M taker orders, 110 M shares and 8 days. The API is complete: its volume
  ratio to Gamma is 1.000 from the 1st to the 99th percentile, and it matches the chain.
- Makers as a group earn ≈ 0 against takers before rebates.
- The rebate is 20% of a 0.07·p(1−p) fee, weighted by fee-equivalent: 0.19 ¢/share, about $26.6k/day across all
  makers.
- The registered statistic on verified inputs is **+0.126 ¢/share, t 1.82 (Newey-West / day-cluster 1.6): KILL.**
- Nothing here supports a slow maker. The bucket patterns (pre-window, large-share trades) are post hoc strata
  from the single measurement window and must not be mined.

## Proposed next experiment
The Polymarket venue has now failed three pre-registered kills in a row: p09 (taker), p15 (vs Deribit) and p17
(maker). **Abandon Polymarket.** NEWPLAN #1, #2 and #4 are closed. The only positive number in the repo is p14's
static carry, which is post hoc and has never touched its holdout. NEWPLAN #3 (forecast-driven carry) only makes
sense if that base carry survives out of sample. So the single cheapest decisive test is p14's one holdout look.

- **Hypothesis:** the zero-parameter static book (short the HL perp, long the Binance perp, equal notional on the
  8 coins fixed in p14's PLAN, one taker entry and one exit) earns ≥ 5 %/yr per unit notional net on the
  untouched holdout, 2026-01-12 → 2026-09-27.
- **Exact change vs p14:**
  - No new data or parameters. Only the rule changes, from the threshold rule (killed on dev) to the static book
    written in p14's RESULTS.
  - p14's RESULTS says this rule was chosen post hoc on dev. The holdout is therefore its only test.
- **Pre-OOS plan, all on dev and committed before the holdout is read:**
  - Finish all 8 coins.
  - Register the rule, costs (HL measured, Binance taker), margin buffer (3× per leg) and funding.
  - Run `tail_report` (CVaR, worst 5-day, stress windows).
  - Check the 2025-10-10 ADL fills from the p13 extraction, and state how a force-closed leg is booked.
- **Kill, decided in advance:** kill if any of these holds:
  - holdout net < 5 %/yr per unit notional (≈ T-bill + 1);
  - weekly t < 2;
  - worst 5-day loss > 12× the mean 5-day P&L (the same tail bar as p16).
  If it fails, NEWPLAN #3 is dropped with it, and every NEWPLAN idea is exhausted. The next step is then the
  owner's call on a new thesis, not another variant.
- **Expected cost:** 1 trial in `trials_hl.json` (the line's only holdout look). Compute is minutes, since the
  funding and candle history is already fetched apart from 5 coins, about 15 min at the HL rate limit.
