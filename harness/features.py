"""A deliberately small, strictly-causal starter feature set.

Rule: every feature at bar t uses data up to and including the CLOSE of bar
t, never later. Rolling windows are trailing (pandas default), never
center=True. Project 1 grows this into the full feature zoo.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data import asof_join
from .labeling import ewm_vol


def basic_features(bars: pd.DataFrame, windows=(1, 6, 12, 48, 288)) -> pd.DataFrame:
    """bars needs 'close'; uses 'volume' and 'taker_buy_volume' if present."""
    c = bars["close"]
    lr = np.log(c).diff()
    f = pd.DataFrame(index=bars.index)
    for w in windows:
        f[f"ret_{w}"] = np.log(c / c.shift(w))
    for w in (48, 288):
        vol = lr.rolling(w).std()
        f[f"vol_{w}"] = vol
        f[f"zret_{w}"] = f["ret_12"] / (vol * np.sqrt(12))
    f["vol_ratio"] = f["vol_48"] / f["vol_288"]
    if "volume" in bars:
        v = bars["volume"]
        f["vlm_z"] = (v - v.rolling(288).mean()) / v.rolling(288).std()
    if "taker_buy_volume" in bars and "volume" in bars:
        imb = 2 * bars["taker_buy_volume"] / bars["volume"].replace(0, np.nan) - 1
        f["taker_imb_1"] = imb
        f["taker_imb_12"] = imb.rolling(12).mean()
    hour = bars.index.hour + bars.index.minute / 60
    f["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    f["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    return f


def scale_free_basic_features(bars: pd.DataFrame, windows=(1, 6, 12, 48, 288), z_window: int = 30 * 288) -> pd.DataFrame:
    """basic_features with the asset-specific units removed, for pooling assets.

    ret_w  -> ret_w / (ewm_vol(288) * sqrt(w)): returns in units of the
              triple-barrier width (which is ewm_vol(288) * sqrt(H)).
    vol_w  -> z-score of log(vol_w) over the trailing z_window bars
              (min_periods 90%).
    The other columns are already scale-free and are kept as they are.
    Trailing windows only, per asset: call it once per asset.
    """
    f = basic_features(bars, windows)
    sig = ewm_vol(bars["close"], 288)
    for w in windows:
        f[f"ret_{w}"] = f[f"ret_{w}"] / (sig * np.sqrt(w))
    mp = int(0.9 * z_window)
    for w in (48, 288):
        lv = np.log(f[f"vol_{w}"].where(f[f"vol_{w}"] > 0))
        f[f"vol_{w}"] = (lv - lv.rolling(z_window, min_periods=mp).mean()) / lv.rolling(z_window, min_periods=mp).std()
    return f.rename(columns={**{f"ret_{w}": f"ret_{w}_vs" for w in windows}, "vol_48": "vol_48_z", "vol_288": "vol_288_z"})


def positioning_features(
    bars: pd.DataFrame,
    metrics: pd.DataFrame,
    funding: pd.Series,
    spot_close: pd.Series,
    premium_close: pd.Series,
    metrics_tolerance: str = "30min",
) -> pd.DataFrame:
    """Slow, crypto-native positioning features on the bar grid of `bars`.

    Timing rules (see harness.data):
      * metrics and funding are snapshots: joined with asof_join (strict), so a
        row stamped T is first used by the bar closing after T. Metrics older
        than `metrics_tolerance` -> NaN (data gaps are not forward-filled).
      * funding: settled rates only. Stats (z-score, sums) are computed on the
        settlement series first, then joined, so they never see a later rate.
      * spot and premium-index klines are indexed by close time like `bars`
        and joined on the exact timestamp.
    Everything is a trailing window. Long windows use min_periods ~90% so a
    short data gap does not blank out a month of rows.
    """
    idx = bars.index
    c = bars["close"]
    f = pd.DataFrame(index=idx)

    def z(x, w):
        return (x - x.rolling(w, min_periods=int(0.9 * w)).mean()) / x.rolling(w, min_periods=int(0.9 * w)).std()

    # funding: 8h settlements -> 3 per day, 90 per 30 days
    fr = funding.sort_index()
    fund = pd.DataFrame({
        "funding": fr,
        "funding_z30d": (fr - fr.rolling(90).mean()) / fr.rolling(90).std(),
        "funding_cum1d": fr.rolling(3).sum(),
        "funding_cum3d": fr.rolling(9).sum(),
    })
    f = f.join(asof_join(idx, fund, tolerance="9h"))

    m = asof_join(idx, metrics, tolerance=metrics_tolerance)
    oi = np.log(m["sum_open_interest"])
    for w, name in ((12, "1h"), (48, "4h"), (288, "1d")):
        f[f"oi_chg_{name}"] = oi - oi.shift(w)
    for w, name in ((48, "4h"), (288, "1d")):
        # + : OI grows in the direction price moved (new positions chasing);
        # - : OI falls while price moves (closing / liquidations / squeezes)
        f[f"oi_px_div_{name}"] = f[f"oi_chg_{name}"] * np.sign(np.log(c / c.shift(w)))
    f["oi_z30d"] = z(oi, 30 * 288)

    basis = (c / spot_close.reindex(idx) - 1).rolling(12, min_periods=10).mean()
    f["basis_1h"] = basis
    f["basis_z7d"] = z(basis, 7 * 288)
    prem = premium_close.reindex(idx).rolling(12, min_periods=10).mean()
    f["premium_1h"] = prem
    f["premium_chg_4h"] = prem - prem.shift(48)

    for col, name in (("count_toptrader_long_short_ratio", "top_acct_ls"),
                      ("sum_toptrader_long_short_ratio", "top_pos_ls"),
                      ("count_long_short_ratio", "global_ls")):
        x = np.log(m[col])
        f[name] = x
        f[f"{name}_chg_4h"] = x - x.shift(48)
        f[f"{name}_chg_1d"] = x - x.shift(288)
    tk = np.log(m["sum_taker_long_short_vol_ratio"])
    f["taker_ls_1h"] = tk.rolling(12, min_periods=10).mean()
    f["taker_ls_4h"] = tk.rolling(48, min_periods=43).mean()
    return f
