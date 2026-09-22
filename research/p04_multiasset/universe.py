"""p04 universe, point-in-time (no survivorship). Uses NO returns, only listing
dates and July 2022 quote volume.

1. Every USD-M symbol ever archived on data.binance.vision (the S3 listing
   keeps delisted symbols). Perpetuals only: dated delivery contracts have a
   `_YYMMDD` suffix.
2. Eligible: a 5m kline file exists for 2022-06 (i.e. listed by 2022-06).
3. Rank by total quote volume over 2022-07 (monthly 5m file, sha256-checked).
4. Exclude stablecoin-vs-stablecoin pairs. Keep ONE contract per underlying
   (the highest-volume one; this drops BTCBUSD/ETHBUSD, owner's decision
   2026-09-22). Take the top 15. BTCUSDT must be in it.
5. Delisting / migration (e.g. MATIC -> POL, no splicing of the successor):
   the last bar with trade count > 0 in the downloaded 5m klines. The archive
   pads some dead symbols with zero-trade bars at a frozen price, so the file
   list alone is not enough.

July files go to data/raw/universe_2022-07/ (gitignored).
Writes universe.json and universe_ranking.csv.

Run from the repo root:  python research/p04_multiasset/universe.py
"""
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from harness.data import load_binance_klines

OUT = Path(__file__).parent
RAW = Path("data/raw/universe_2022-07")
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
KL = "https://data.binance.vision/data/futures/um/monthly/klines"
N = 15
STABLES = {"USDT", "BUSD", "USDC", "TUSD", "USDP", "DAI", "FDUSD", "UST", "USTC"}
QUOTES = ("USDT", "BUSD", "USDC")


def list_symbols():
    syms, marker = [], ""
    pre = "data/futures/um/monthly/klines/"
    while True:
        u = f"{S3}?delimiter=/&prefix={pre}" + (f"&marker={pre}{urllib.parse.quote(marker)}/" if marker else "")
        x = urllib.request.urlopen(u, timeout=60).read().decode()
        ps = re.findall(rf"<Prefix>{pre}([^<]+)/</Prefix>", x)
        syms += ps
        if "<IsTruncated>true" not in x:
            return syms
        marker = ps[-1]


def exists(url):
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60)
        return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise


def july_volume(sym):
    q = urllib.parse.quote(sym)
    if not exists(f"{KL}/{q}/5m/{q}-5m-2022-06.zip"):
        return {"symbol": sym, "listed_by_2022_06": False}
    dest = RAW / f"{sym}-5m-2022-07.zip"
    if not dest.exists():
        u = f"{KL}/{q}/5m/{q}-5m-2022-07.zip"
        data = urllib.request.urlopen(u, timeout=120).read()
        want = urllib.request.urlopen(u + ".CHECKSUM", timeout=60).read().split()[0].decode()
        assert hashlib.sha256(data).hexdigest() == want, sym
        dest.write_bytes(data)
    b = load_binance_klines(str(dest))
    return {"symbol": sym, "listed_by_2022_06": True, "quote_volume_2022_07": float(b["quote_volume"].sum()),
            "bars_2022_07": len(b)}


def split_symbol(sym):
    for q in QUOTES:
        if sym.endswith(q):
            return sym[: -len(q)], q
    return sym, ""


def last_live_bar(sym):
    b = load_binance_klines(f"data/raw/{sym}-5m-20*.zip")
    live = b.index[b["count"] > 0]
    return live[-1], b.index[-1]


if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    all_syms = list_symbols()
    perps = [s for s in all_syms if "_" not in s]
    with ThreadPoolExecutor(16) as ex:
        rows = list(ex.map(july_volume, perps))
    df = pd.DataFrame(rows)
    df = df[df["listed_by_2022_06"]].sort_values("quote_volume_2022_07", ascending=False).reset_index(drop=True)
    df["vol_rank"] = df.index + 1
    df[["base", "quote"]] = [split_symbol(s) for s in df["symbol"]]
    df["status"] = ""
    seen = set()
    chosen = []
    for i, r in df.iterrows():
        if r["base"] in STABLES and r["quote"] in STABLES:
            df.loc[i, "status"] = "excluded: stable-vs-stable"
        elif r["base"] in seen:
            df.loc[i, "status"] = "excluded: duplicate underlying"
        elif len(chosen) < N:
            chosen.append(r["symbol"])
            df.loc[i, "status"] = "IN"
        seen.add(r["base"])
    assert "BTCUSDT" in chosen

    df.to_csv(OUT / "universe_ranking.csv", index=False)
    life = {}
    end = pd.Timestamp("2026-09-01", tz="UTC")
    for s in chosen:
        last, file_end = last_live_bar(s)
        life[s] = {"last_live_bar": str(last), "archive_last_bar": str(file_end),
                   "delisted": bool(last < end - pd.Timedelta("1D"))}
    out = {"n_archived_um_symbols": len(all_syms), "n_perps": len(perps),
           "n_listed_by_2022_06": len(df), "universe": chosen, "lifetimes": life}
    (OUT / "universe.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    print(df.head(25).to_string())
