"""Fetch public funding history (HL hourly, Binance 8h) and daily closes for the p14 universe.

Writes data/hl/funding/{hl,bn}_funding_<COIN>.parquet and {hl,bn}_daily_<COIN>.parquet.
HL info endpoint weight ~45 per 500-row page -> paced at ~20 pages/min.
"""
import sys, time, json, pathlib
import requests
import pandas as pd

OUT = pathlib.Path(__file__).resolve().parents[2] / "data/hl/funding"
OUT.mkdir(parents=True, exist_ok=True)
START = int(pd.Timestamp("2024-01-01", tz="UTC").timestamp() * 1000)
COINS = sys.argv[1:] or ["BTC", "ETH", "SOL", "XRP", "DOGE", "LINK", "AVAX", "SUI"]
HL = "https://api.hyperliquid.xyz/info"
BN = "https://fapi.binance.com/fapi/v1"


def hl_post(body):
    for k in range(8):
        r = requests.post(HL, json=body, timeout=30)
        if r.status_code == 200:
            return r.json()
        time.sleep(5 * (k + 1))
    r.raise_for_status()


def hl_funding(coin):
    rows, t = [], START
    while True:
        page = hl_post({"type": "fundingHistory", "coin": coin, "startTime": t})
        if not page:
            break
        rows += page
        t = page[-1]["time"] + 1
        time.sleep(2.5)
        if len(page) < 500:
            break
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    df["rate"] = df["fundingRate"].astype(float)
    return df[["time", "rate"]]


def bn_funding(coin):
    rows, t = [], START
    while True:
        page = requests.get(f"{BN}/fundingRate", params={"symbol": coin + "USDT", "startTime": t, "limit": 1000}, timeout=30).json()
        if not page:
            break
        rows += page
        t = page[-1]["fundingTime"] + 1
        if len(page) < 1000:
            break
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["fundingTime"], unit="ms", utc=True)
    df["rate"] = df["fundingRate"].astype(float)
    return df[["time", "rate"]]


def hl_daily(coin):
    c = hl_post({"type": "candleSnapshot", "req": {"coin": coin, "interval": "1d", "startTime": START,
                                                    "endTime": int(time.time() * 1000)}})
    df = pd.DataFrame(c)
    return pd.DataFrame({"date": pd.to_datetime(df["t"], unit="ms", utc=True), "close": df["c"].astype(float),
                         "vol_usd": df["v"].astype(float) * df["c"].astype(float)})


def bn_daily(coin):
    k = requests.get(f"{BN}/klines", params={"symbol": coin + "USDT", "interval": "1d", "startTime": START,
                                             "limit": 1500}, timeout=30).json()
    return pd.DataFrame({"date": pd.to_datetime([r[0] for r in k], unit="ms", utc=True),
                         "close": [float(r[4]) for r in k]})


if __name__ == "__main__":
    for coin in COINS:
        if (OUT / f"hl_funding_{coin}.parquet").exists():
            continue
        bn_funding(coin).to_parquet(OUT / f"bn_funding_{coin}.parquet")
        bn_daily(coin).to_parquet(OUT / f"bn_daily_{coin}.parquet")
        hl_daily(coin).to_parquet(OUT / f"hl_daily_{coin}.parquet")
        f = hl_funding(coin)
        f.to_parquet(OUT / f"hl_funding_{coin}.parquet")
        print(coin, len(f), f.time.min(), f.time.max(), flush=True)
