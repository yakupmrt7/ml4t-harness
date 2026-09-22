"""Download free history from data.binance.vision (USD-M futures).

python scripts/download_binance.py --symbol BTCUSDT --interval 5m --start 2022-01 --end 2026-08
Monthly files; the current month isn't published until it ends (use daily files for that).
"""
import argparse
import pathlib
import urllib.request

BASE = "https://data.binance.vision/data/futures/um/monthly"


def months(start, end):
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    while (y, m) <= (ey, em):
        yield f"{y:04d}-{m:02d}"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def get(url, dest):
    if dest.exists():
        return "skip"
    try:
        urllib.request.urlretrieve(url, dest)
        return "ok"
    except Exception as e:  # 404 for months that don't exist yet
        return f"miss ({e.__class__.__name__})"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--interval", default="5m")
    ap.add_argument("--start", default="2022-01")
    ap.add_argument("--end", default="2026-08")
    ap.add_argument("--out", default="data/raw")
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for ym in months(a.start, a.end):
        k = f"{a.symbol}-{a.interval}-{ym}.zip"
        f = f"{a.symbol}-fundingRate-{ym}.zip"
        print(k, get(f"{BASE}/klines/{a.symbol}/{a.interval}/{k}", out / k),
              "|", f, get(f"{BASE}/fundingRate/{a.symbol}/{f}", out / f))
