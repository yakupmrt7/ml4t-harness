"""Shared data building for p04 (selection.py = pre-OOS, run.py = OOS).
Everything here is fixed in PLAN.md."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from harness.backtest import CostModel, hysteresis_position, run_backtest
from harness.data import load_binance_klines
from harness.features import scale_free_basic_features
from harness.labeling import ewm_vol, triple_barrier
from harness.metrics import periods_per_year, sharpe
from harness.pipeline import align, oos_auc
from harness.portfolio import risk_scale
from harness.weights import average_uniqueness

OUT = Path(__file__).parent
UNI = json.loads((OUT / "universe.json").read_text())
UNIVERSE = UNI["universe"]
N_ASSETS = len(UNIVERSE)
BARS_START = "2022-06-01"                         # warm-up for the 30d z-scores
LABEL_START, END = "2022-08-01", "2026-09-01"     # labels start after the ranking month
SEL_END = pd.Timestamp("2024-04-07", tz="UTC")    # pre-OOS: label t0 AND t1 < SEL_END
OOS_START = pd.Timestamp(json.loads(Path("research/p01_baseline/results.json").read_text())["oos_start"])
H = 48
HYST = {"theta_in": 0.05, "theta_out": 0.025, "min_hold": 48}   # p03's, fixed
TARGET_VOL, CAP = 0.50, 3.0
TAKER = CostModel(fee_bps=5, slippage_bps=0.5)
MAKER = CostModel(fee_bps=2, slippage_bps=0.5)
GROSS = CostModel(0, 0)


def load_bars(sym):
    """5m perp bars from BARS_START, cut at the last bar with trades (delisting)."""
    cache = Path(f"data/bars/{sym}-5m-2022-06_2026-08.parquet")
    if cache.exists():
        b = pd.read_parquet(cache)
    else:
        b = load_binance_klines(f"data/raw/{sym}-5m-20*.zip").loc[BARS_START:]
        cache.parent.mkdir(parents=True, exist_ok=True)
        b.to_parquet(cache)
    last = pd.Timestamp(UNI["lifetimes"][sym]["last_live_bar"])
    b = b.loc[:last]
    assert b["count"].iloc[-1] > 0
    return b


def build_asset(bars):
    close = bars["close"]
    X = scale_free_basic_features(bars)
    lab = triple_barrier(close, H, ewm_vol(close, 288) * np.sqrt(H), pt_mult=1.0, sl_mult=1.0)
    lab = lab.loc[LABEL_START:END]
    lab = lab[lab.index < pd.Timestamp(END, tz="UTC")]
    X, lab = align(X, lab)
    u = average_uniqueness(close.index, lab)
    return X, lab, u


def stack(d):
    """{asset: frame/series indexed by t0} -> (t0, asset) MultiIndex sorted by t0."""
    parts = []
    for a, f in d.items():
        f = f.copy()
        f.index = pd.MultiIndex.from_arrays([f.index, [a] * len(f)], names=["t0", "asset"])
        parts.append(f)
    return pd.concat(parts).sort_index(level=["t0", "asset"])


def load_all():
    closes, Xs, labs, us, info = {}, {}, {}, {}, {}
    for a in UNIVERSE:
        b = load_bars(a)
        X, lab, u = build_asset(b)
        closes[a], Xs[a], labs[a], us[a] = b["close"], X, lab, u
        info[a] = {"first_bar": str(b.index[0]), "last_bar": str(b.index[-1]), "labels": len(lab),
                   "effective_n": float(u.sum()), "zero_trade_bars": int((b["count"] == 0).sum())}
    return closes, stack(Xs), stack(labs), stack(us).rename("uniqueness"), info


def add_asset_id(X):
    a = X.index.get_level_values(1)
    return X.join(pd.DataFrame({f"id_{s}": (a == s).astype(float) for s in UNIVERSE}, index=X.index))


def pre_oos(labels):
    t0 = labels.index.get_level_values(0)
    return labels[(t0 < SEL_END) & (labels["t1"] < SEL_END)]


def by_asset(s):
    return {a: x.droplevel(1) for a, x in s.groupby(level=1, sort=False)}


def unit_positions(preds, closes):
    """{asset: discrete hysteresis position on the asset's bar grid}. Bars with
    no prediction hold the current position (as p03's hyst_fn)."""
    out = {}
    for a, p in by_asset(preds).items():
        c = closes[a].loc[p.index[0]:p.index[-1]]
        out[a] = hysteresis_position(p.reindex(c.index), **HYST)
    return out


def ann_vol(close):
    return ewm_vol(close, 288) * np.sqrt(periods_per_year(close.index))


def make_position_fn(closes):
    vols = {a: ann_vol(c) for a, c in closes.items()}

    def fn(preds):
        return {a: risk_scale(p, vols[a], TARGET_VOL, CAP) / N_ASSETS
                for a, p in unit_positions(preds, closes).items()}
    return fn


def bt_stats(bt, ppy):
    held = bt["held"]
    turnover = held.diff().abs().fillna(held.abs()).sum()
    years = len(bt) / ppy
    return {
        "sharpe_gross": sharpe(bt["gross"], ppy),
        "sharpe_net_maker": sharpe(bt["net"], ppy),
        "turnover_per_year": float(turnover / years),
        "breakeven_bps": float(bt["gross"].sum() / turnover * 1e4) if turnover else np.nan,
        "exposure": float((held != 0).mean()),
        "mean_position": float(held.mean()),
    }


def per_asset_table(preds, labels, closes):
    """Unscaled +-1 hysteresis per asset (comparable to p03), maker cost."""
    rows = []
    pos = unit_positions(preds, closes)
    for a, p in by_asset(preds).items():
        c = closes[a].loc[p.index[0]:p.index[-1]]
        bt = run_backtest(c, pos[a], MAKER)
        s = bt_stats(bt, periods_per_year(c.index))
        s["sharpe_net_taker"] = sharpe(run_backtest(c, pos[a], TAKER)["net"], periods_per_year(c.index))
        rows.append({"asset": a, "auc": oos_auc(p, labels.xs(a, level=1)), "n_preds": len(p), **s})
    return pd.DataFrame(rows).set_index("asset")


def correlation_stats(parts_gross, closes):
    """Average pairwise correlation of per-asset (scaled) gross P&L, daily and
    per 5m bar, and effective N = N / (1 + (N-1) rho). An asset counts only
    while listed (pairwise-complete correlations)."""
    parts_gross = parts_gross.copy()
    for a in parts_gross.columns:
        c = closes[a]
        parts_gross.loc[(parts_gross.index < c.index[0]) | (parts_gross.index > c.index[-1]), a] = np.nan
    out = {}
    for name, g in (("daily", parts_gross.resample("1D").sum(min_count=1)), ("bar", parts_gross)):
        g = g.loc[:, g.abs().sum() > 0]
        cm = g.corr().to_numpy()
        n = cm.shape[0]
        rho = float(cm[~np.eye(n, dtype=bool)].mean())
        out[name] = {"n_assets": n, "avg_pairwise_corr": rho, "effective_n": n / (1 + (n - 1) * rho)}
    return out
