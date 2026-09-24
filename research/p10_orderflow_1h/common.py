"""p10 shared: bars/labels exactly as p01, 1-minute flow table, pre-registered flow features
(PLAN.md), TCN input channels. Causal: a feature at 5m bar close t uses minutes ending <= t.
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd

from harness.features import basic_features
from harness.labeling import ewm_vol, triple_barrier
from harness.weights import average_uniqueness

OUT = Path(__file__).parent
FLOW = Path("data/collector/flow_v1")
START, END = "2022-09-01", "2026-09-01"
H = 12
OOS_START = pd.Timestamp(json.loads(Path("research/p01_baseline/results.json").read_text())["oos_start"])
WINDOWS = (5, 15, 60, 240)
VPIN_USD = 10_000_000.0
BASELINE_MIN = 30 * 1440


def load_bars():
    return pd.read_parquet("data/bars/BTCUSDT-5m-2022-08_2026-08.parquet")


def p01_labels(bars):
    close = bars["close"]
    labels = triple_barrier(close, H, ewm_vol(close, 288) * np.sqrt(H), pt_mult=1.0, sl_mult=1.0)
    labels = labels.loc[START:END]
    labels = labels[labels.index < pd.Timestamp(END, tz="UTC")]
    return labels, average_uniqueness(close.index, labels)


def load_flow(pre_oos_only: bool = False) -> pd.DataFrame:
    """1-minute flow on a full minute grid. Minutes of a missing day stay NaN; minutes with no
    trade inside a present day get zero counts. pre_oos_only: refuse any day >= OOS start date."""
    fs = sorted(glob.glob(str(FLOW / "1m/date=*/flow_*.parquet")))
    if pre_oos_only:
        fs = [f for f in fs if f.split("date=")[1][:10] < str(OOS_START.date())]
    f = pd.concat(pd.read_parquet(x) for x in fs).sort_index()
    f = f[~f.index.duplicated()]
    days = pd.DatetimeIndex(sorted({x.split("date=")[1][:10] for x in fs}), tz="UTC")
    grid = pd.date_range(f.index[0].floor("D") + pd.Timedelta("1min"), f.index[-1], freq="1min")
    present = (grid - pd.Timedelta("1min")).floor("D").isin(days)       # the minute ending 00:00 belongs to the previous day's file
    f = f.reindex(grid)
    zero_cols = ["n_agg", "n_trades", "buy_qty", "sell_qty", "buy_notional", "sell_notional", "big_notional",
                 "n_runs", "max_run", "vpin_done", "vpin_absimb", "n_zero"]
    f.loc[present, zero_cols] = f.loc[present, zero_cols].fillna(0)
    f["px_last"] = f["px_last"].where(~present | f["px_last"].notna()).ffill().where(present)
    for c in ("px_first", "px_high", "px_low"):
        f[c] = f[c].fillna(f["px_last"])
    f["present"] = present
    return f


def _minute_derived(f):
    d = pd.DataFrame(index=f.index)
    d["qty"] = f["buy_qty"] + f["sell_qty"]
    d["notional"] = f["buy_notional"] + f["sell_notional"]
    d["sn"] = (f["buy_notional"] - f["sell_notional"]) / 1e6               # signed notional, $M
    d["ret1"] = np.log(f["px_last"]).diff()
    d["base"] = f["n_agg"].rolling(BASELINE_MIN, min_periods=BASELINE_MIN // 2).mean()   # per-minute n_agg, trailing 30 d
    return d


def flow_features(f: pd.DataFrame, at: pd.DatetimeIndex) -> pd.DataFrame:
    """Pre-registered flow features (PLAN.md), evaluated at 5m bar closes `at`."""
    d = _minute_derived(f)
    out = {}
    for w in WINDOWS:
        R = lambda s: s.rolling(w, min_periods=w)   # noqa: E731  trailing, ends at the minute END t
        qty, n = R(d["qty"]).sum(), R(f["n_agg"]).sum()
        out[f"imb_{w}"] = (R(f["buy_qty"]).sum() - R(f["sell_qty"]).sum()) / qty.replace(0, np.nan)
        out[f"lcnt_{w}"] = np.log1p(n)
        out[f"msize_{w}"] = qty / n.replace(0, np.nan)
        out[f"medsize_{w}"] = R(f["size_median"]).median()
        out[f"big_{w}"] = R(f["big_notional"]).sum() / R(d["notional"]).sum().replace(0, np.nan)
        done = R(f["vpin_done"]).sum()
        out[f"vpin_{w}"] = R(f["vpin_absimb"]).sum() / (done.replace(0, np.nan) * VPIN_USD)
        out[f"runmean_{w}"] = n / R(f["n_runs"]).sum().replace(0, np.nan)
        out[f"runmax_{w}"] = R(f["max_run"]).max()
        out[f"intens_{w}"] = n / (d["base"].shift(w) * w)                   # baseline ends at the window start
        if w >= 15:
            x, y = d["sn"], d["ret1"]
            cov = R(x * y).mean() - R(x).mean() * R(y).mean()
            var = R(x * x).mean() - R(x).mean() ** 2
            out[f"lambda_{w}"] = cov / var.replace(0, np.nan)
            out[f"rv_{w}"] = np.sqrt(R(d["ret1"] ** 2).sum())
    X = pd.DataFrame(out)
    X["rv_ratio_15_240"] = X["rv_15"] / X["rv_240"].replace(0, np.nan)
    X["rv_ratio_60_240"] = X["rv_60"] / X["rv_240"].replace(0, np.nan)
    # a window touching a missing day is NaN (not zeros)
    miss = (~f["present"]).astype(float).rolling(max(WINDOWS) + 1, min_periods=1).max() > 0
    X[miss] = np.nan
    return X.reindex(at)


TCN_CHANNELS = ["l_nagg", "l_buyn", "l_selln", "imb", "big", "l_medsize", "runmean", "l_maxrun", "vpin",
                "ret1", "l_hilo", "intens"]


def tcn_channels(f: pd.DataFrame) -> pd.DataFrame:
    """12 per-minute channels for the TCN (PLAN.md), before per-fold standardisation."""
    d = _minute_derived(f)
    c = pd.DataFrame(index=f.index)
    c["l_nagg"] = np.log1p(f["n_agg"])
    c["l_buyn"] = np.log1p(f["buy_notional"])
    c["l_selln"] = np.log1p(f["sell_notional"])
    c["imb"] = ((f["buy_qty"] - f["sell_qty"]) / d["qty"].replace(0, np.nan)).fillna(0)
    c["big"] = (f["big_notional"] / d["notional"].replace(0, np.nan)).fillna(0)
    c["l_medsize"] = np.log1p(f["size_median"].fillna(0))
    c["runmean"] = (f["n_agg"] / f["n_runs"].replace(0, np.nan)).fillna(0)
    c["l_maxrun"] = np.log1p(f["max_run"].fillna(0))
    c["vpin"] = (f["vpin_absimb"] / (f["vpin_done"].replace(0, np.nan) * VPIN_USD)).fillna(0)
    c["ret1"] = d["ret1"].fillna(0)
    c["l_hilo"] = np.log(f["px_high"] / f["px_low"]).fillna(0)
    c["intens"] = (f["n_agg"] / d["base"].shift(1)).fillna(1.0)
    c[~f["present"]] = np.nan
    return c[TCN_CHANNELS]
