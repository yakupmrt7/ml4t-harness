"""Loaders: Binance public archive klines, and trades -> bars for your own
collector output.

Binance publishes years of free history at https://data.binance.vision
(spot and USD-M futures klines, aggTrades, funding rates, daily zip files).
Use that for training depth; use your own collector for things the archive
doesn't have (order book, Polymarket, Chainlink).
"""
from __future__ import annotations

import glob

import numpy as np
import pandas as pd

KLINE_COLS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
]


def load_binance_klines(pattern: str) -> pd.DataFrame:
    """Read data.binance.vision kline CSVs/zips (e.g. 'BTCUSDT-5m-2025-*.zip').
    Index = bar CLOSE time, so a feature stamped at t only uses the finished bar."""
    frames = []
    for f in sorted(glob.glob(pattern)):
        df = pd.read_csv(f, header=None, names=KLINE_COLS)
        if not str(df.iloc[0, 0]).isdigit():   # newer files have a header row
            df = df.iloc[1:]
        frames.append(df)
    df = pd.concat(frames).astype({c: float for c in KLINE_COLS[1:6] + KLINE_COLS[7:11]})
    ct = pd.to_numeric(df["close_time"])
    unit = "us" if ct.iloc[0] > 1e14 else "ms"   # futures/spot switched to us in 2025
    df.index = pd.to_datetime(ct + (1 if unit == "ms" else 1000), unit=unit, utc=True)
    df = df[~df.index.duplicated()].sort_index()
    return df[["open", "high", "low", "close", "volume", "quote_volume", "count", "taker_buy_volume"]]


def load_funding(pattern: str) -> pd.Series:
    """data.binance.vision fundingRate monthly CSVs -> Series(rate) by funding time."""
    df = pd.concat(pd.read_csv(f) for f in sorted(glob.glob(pattern)))
    t = pd.to_numeric(df["calc_time"])
    idx = pd.to_datetime(t, unit="us" if t.iloc[0] > 1e14 else "ms", utc=True)
    return pd.Series(df["last_funding_rate"].to_numpy(float), idx).sort_index()


def trades_to_bars(
    trades: pd.DataFrame,
    freq: str = "5min",
    ts="ts", price="price", qty="qty", is_buyer_maker="is_buyer_maker",
) -> pd.DataFrame:
    """Aggregate raw trades (e.g. your collector's aggTrade stream) into time
    bars labelled by their CLOSE time (right edge). Map your column names via
    the keyword args. is_buyer_maker=True means the aggressor SOLD."""
    t = trades[[ts, price, qty, is_buyer_maker]].copy()
    if not pd.api.types.is_datetime64_any_dtype(t[ts]):
        unit = "us" if t[ts].iloc[0] > 1e14 else "ms"
        t[ts] = pd.to_datetime(t[ts], unit=unit, utc=True)
    t = t.set_index(ts).sort_index()
    t["notional"] = t[price] * t[qty]
    t["buy_qty"] = t[qty].where(~t[is_buyer_maker].astype(bool), 0.0)
    g = t.resample(freq, label="right", closed="left")
    bars = pd.DataFrame({
        "open": g[price].first(), "high": g[price].max(), "low": g[price].min(),
        "close": g[price].last(), "volume": g[qty].sum(), "quote_volume": g["notional"].sum(),
        "count": g[price].count(), "taker_buy_volume": g["buy_qty"].sum(),
    })
    bars["close"] = bars["close"].ffill()
    for c in ("open", "high", "low"):
        bars[c] = bars[c].fillna(bars["close"])
    return bars.dropna(subset=["close"])
