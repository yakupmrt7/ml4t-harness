# Project 0 — a validation harness for ML trading research

Before any LSTM, TCN or tree touches real data, this harness has to be able
to say **"there is nothing here"** on noise and **"there is something here"**
on a planted signal. `selftest.py` proves both.

```
pip install -r requirements.txt
python tests/test_core.py     # 7 unit tests on the off-by-one hotspots
python selftest.py            # ~90 s, ends with HARNESS OK
```

## Layout

| module | what it does | why it matters |
|---|---|---|
| `labeling.py` | fixed-horizon + triple-barrier labels (vectorised), CUSUM event sampler | a label is an interval `[t0, t1]`, not a point |
| `weights.py` | concurrency, average uniqueness, effective n | 1h labels on 5-min bars overlap 12x: 34k labels ≈ 3.6k independent ones |
| `cv.py` | `PurgedKFold` (model selection), `WalkForward` (the backtest you report) | stops overlapping labels leaking across folds |
| `backtest.py` | bar backtester: fees, slippage, perp funding, execution delay | `delay=0` is refused; `delay=2` is your robustness check |
| `metrics.py` | Sharpe, drawdown, turnover, breakeven cost, PSR, DSR, `TrialLog` | DSR is only honest if every trial is logged, failures included |
| `nulls.py` | lookahead audit, permuted labels, circular-shift null, purge probe, cost sweep, delay check, `validation_report` | the gauntlet a result must survive |
| `features.py` | small, strictly causal starter set | Project 1 replaces this |
| `data.py` | data.binance.vision klines + funding loaders, trades → bars for your collector | bars indexed by **close** time |

## The gauntlet (`validation_report`)

1. **Lookahead audit.** Next-bar |IC| > 0.10 for any feature means it almost certainly peeks.
2. **Implausibility alarm.** Gross Sharpe beyond max(4, 4 × standard error) means find the bug before celebrating.
3. **Permuted labels.** Train on shuffled labels: AUC must be ~0.5 and Sharpe ~0. If not, the leak is in the plumbing (joins, timing, backtester), not the model.
4. **Circular-shift null (gross).** Slide your positions against returns. Turnover and autocorrelation are kept, timing is destroyed. This tests timing skill.
5. **PSR of net Sharpe > 0.95.** Tests whether it makes money after costs, given how little data you have.
6. **Extra-bar delay.** If the edge dies at `delay=2`, it was bid-ask bounce, not prediction.
7. **Purge probe.** AUC under naive shuffled KFold versus purged. Shows how much fake skill overlap creates.

## Self-test results (synthetic 5-min GARCH bars, 120 days, 1h triple-barrier labels)

| case | OOS AUC | Sharpe gross / net | verdict |
|---|---|---|---|
| A. random walk | 0.479 | −4.2 / −10.1 | no edge (shift-null p = 0.93) ✔ |
| B. planted weak signal | 0.533 | +8.2 / +2.1 | edge detected (p < 0.005), **but PSR(net) = 0.82, which is not proven after costs** ✔ |
| C. leaky feature | 0.785 | +80 / +68 | lookahead audit + implausibility alarm fire ✔ |
| purge probe on A (pure noise) | naive **0.679** vs purged 0.488 | | naive CV invents a 0.68 AUC from nothing ✔ |

Also: the best of 50 random strategies had annual Sharpe 4.0 and PSR 0.96. Its DSR after
50 logged trials was **0.35**.

## Three things this taught before touching real data

- **Two months cannot prove a strategy.** Annualised Sharpe standard error ≈ 1/√years. With about 70 days out of sample that is ±2.3. B is a real signal and still can't clear the bar. Train bar-level models on **years** of free history from [data.binance.vision](https://data.binance.vision) (klines, aggTrades, funding). Use your own collector for what the archive lacks: order book, Polymarket, Chainlink.
- **Costs are the model.** B's breakeven is 3.3 bps per unit of turnover. At a 5 bps taker fee it loses money, and at a 2 bps maker fee it survives. Execution style decides as much as the classifier does.
- **Naive CV lies by ~0.18 AUC** on overlapping labels with persistent features. That gap is bigger than any real edge you will ever find.

## Using it on real data

```python
from harness.data import load_binance_klines, load_funding
from harness.features import basic_features
from harness.labeling import ewm_vol, triple_barrier
from harness.weights import average_uniqueness
from harness.cv import WalkForward
from harness.backtest import CostModel
from harness.nulls import validation_report
from harness.metrics import TrialLog

bars = load_binance_klines("data/BTCUSDT-5m-*.zip")
funding = load_funding("data/BTCUSDT-fundingRate-*.zip")   # pass to run_backtest for P&L
H = 12
labels = triple_barrier(bars.close, H, ewm_vol(bars.close, 288) * H**0.5)
X = basic_features(bars)
res = validation_report(X, labels, bars.close, WalkForward(8, 0.4),
                        costs=CostModel(fee_bps=5, slippage_bps=0.5),
                        weights=average_uniqueness(bars.index, labels),
                        pos_kwargs={"mode": "sign", "threshold": 0.02, "smooth": H})
TrialLog("trials.json").log("baseline_5m_1h", res["backtest"], {"H": H})
```

For your collector's trades, use `trades_to_bars(df, "5min", ts=..., price=..., qty=..., is_buyer_maker=...)`.

## Workspace setup

```
unzip ml4t-harness.zip && cd ml4t-harness
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python tests/test_core.py && python selftest.py     # expect HARNESS OK
git init && git add -A && git commit -m "Project 0: validation harness"
python scripts/download_binance.py --interval 5m --start 2022-01 --end 2026-08
claude
```
