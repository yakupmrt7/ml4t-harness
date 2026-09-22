"""A deliberately small, strictly-causal starter feature set.

Rule: every feature at bar t uses data up to and including the CLOSE of bar
t, never later. Rolling windows are trailing (pandas default), never
center=True. Project 1 grows this into the full feature zoo.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


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
