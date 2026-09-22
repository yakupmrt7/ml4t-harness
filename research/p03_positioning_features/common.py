"""Shared data building for p03 (selection.py = pre-OOS, run.py = OOS)."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from harness.backtest import CostModel, hysteresis_position
from harness.data import check_close_alignment, load_binance_klines, load_funding, load_metrics
from harness.features import basic_features, positioning_features
from harness.labeling import ewm_vol, triple_barrier

OUT = Path(__file__).parent
BARS_CACHE = Path("data/bars/BTCUSDT-5m-2022-08_2026-08.parquet")   # p01's perp bars
START, END = "2022-09-01", "2026-09-01"
SEL_END = pd.Timestamp("2024-04-07", tz="UTC")   # pre-OOS: label t0 AND t1 < SEL_END
OOS_START = pd.Timestamp(json.loads(Path("research/p01_baseline/results.json").read_text())["oos_start"])
TAKER = CostModel(fee_bps=5, slippage_bps=0.5)
MAKER = CostModel(fee_bps=2, slippage_bps=0.5)
GROUPS = {   # positioning feature -> subgroup (by name prefix)
    "funding": ("funding",), "open_interest": ("oi_",), "basis_premium": ("basis", "premium"),
    "long_short": ("top_acct", "top_pos", "global_ls"), "taker_ls": ("taker_ls",),
}


def load_inputs():
    bars = pd.read_parquet(BARS_CACHE)
    t0, t1 = bars.index[0], bars.index[-1]
    spot = load_binance_klines("data/raw/spot/BTCUSDT-5m-*.zip")["close"].loc[t0:t1]
    prem = load_binance_klines("data/raw/premiumIndexKlines/BTCUSDT-5m-*.zip")["close"].loc[t0:t1]
    metrics = load_metrics("data/raw/metrics/BTCUSDT-metrics-*.zip")
    funding = load_funding("data/raw/BTCUSDT-fundingRate-*.zip")
    info = {
        "spot_missing_bars": int(spot.reindex(bars.index).isna().sum()),
        "premium_missing_bars": int(prem.reindex(bars.index).isna().sum()),
        "perp_spot_return_corr_by_lag": check_close_alignment(bars["close"], spot),
        "metrics_rows": len(metrics),
        "funding_rows": len(funding),
    }
    return bars, metrics, funding, spot, prem, info


def build_features(bars, metrics, funding, spot, prem):
    Xb = basic_features(bars)
    Xp = positioning_features(bars, metrics, funding, spot, prem)
    return Xb.join(Xp), list(Xb.columns), list(Xp.columns)


def subgroup(col):
    for g, prefixes in GROUPS.items():
        if col.startswith(prefixes):
            return g
    return "basic"


def make_labels(close, H):
    lab = triple_barrier(close, H, ewm_vol(close, 288) * np.sqrt(H), pt_mult=1.0, sl_mult=1.0)
    lab = lab.loc[START:END]
    return lab[lab.index < pd.Timestamp(END, tz="UTC")]


def pre_oos(labels):
    return labels[(labels.index < SEL_END) & (labels["t1"] < SEL_END)]


def hyst_fn(close, cfg):
    """preds -> hysteresis target on the full bar grid (bars with no
    prediction hold the current position instead of forcing flat)."""
    return lambda p: hysteresis_position(p.reindex(close.loc[p.index[0]:p.index[-1]].index), **cfg)


def bt_stats(bt, ppy):
    held = bt["held"]
    turnover = held.diff().abs().fillna(held.abs()).sum()
    years = len(bt) / ppy
    from harness.metrics import sharpe
    return {
        "sharpe_gross": sharpe(bt["gross"], ppy),
        "sharpe_net": sharpe(bt["net"], ppy),
        "turnover_per_year": float(turnover / years),
        "breakeven_bps": float(bt["gross"].sum() / turnover * 1e4) if turnover else np.nan,
        "exposure": float((held != 0).mean()),
        "avg_hold_hours": float(2 * held.abs().sum() / turnover / 12) if turnover else np.nan,
    }
