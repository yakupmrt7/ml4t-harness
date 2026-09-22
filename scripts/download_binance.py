"""Download free history from data.binance.vision.

python scripts/download_binance.py --symbol BTCUSDT --interval 5m --start 2022-01 --end 2026-08
python scripts/download_binance.py --kinds metrics premium spot --start 2022-08 --end 2026-08

kinds (default: klines funding):
  klines   USD-M perp klines          -> data/raw/
  funding  USD-M funding rate         -> data/raw/
  premium  USD-M premiumIndexKlines   -> data/raw/premiumIndexKlines/
  spot     spot klines                -> data/raw/spot/
  metrics  USD-M metrics (OI, long/short ratios; DAILY files only) -> data/raw/metrics/

Monthly files; the current month isn't published until it ends (use daily
files for that). Every downloaded file is checked against its .CHECKSUM
(sha256). Missing files are listed at the end.
"""
import argparse
import calendar
import hashlib
import pathlib
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = "https://data.binance.vision/data"


def months(start, end):
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    while (y, m) <= (ey, em):
        yield f"{y:04d}-{m:02d}"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def days(start, end):
    for ym in months(start, end):
        y, m = map(int, ym.split("-"))
        for d in range(1, calendar.monthrange(y, m)[1] + 1):
            yield f"{ym}-{d:02d}"


def jobs(kind, sym, iv, start, end, out):
    if kind == "klines":
        for ym in months(start, end):
            k = f"{sym}-{iv}-{ym}.zip"
            yield f"{ROOT}/futures/um/monthly/klines/{sym}/{iv}/{k}", out / k
    elif kind == "funding":
        for ym in months(start, end):
            k = f"{sym}-fundingRate-{ym}.zip"
            yield f"{ROOT}/futures/um/monthly/fundingRate/{sym}/{k}", out / k
    elif kind == "premium":
        for ym in months(start, end):
            k = f"{sym}-{iv}-{ym}.zip"
            yield f"{ROOT}/futures/um/monthly/premiumIndexKlines/{sym}/{iv}/{k}", out / "premiumIndexKlines" / k
    elif kind == "spot":
        for ym in months(start, end):
            k = f"{sym}-{iv}-{ym}.zip"
            yield f"{ROOT}/spot/monthly/klines/{sym}/{iv}/{k}", out / "spot" / k
    elif kind == "metrics":
        for d in days(start, end):
            k = f"{sym}-metrics-{d}.zip"
            yield f"{ROOT}/futures/um/daily/metrics/{sym}/{k}", out / "metrics" / k
    else:
        raise ValueError(kind)


def get(url, dest):
    """-> 'ok' | 'skip' | 'missing' | 'BAD CHECKSUM' | 'error: ...'"""
    if dest.exists():
        return "skip"
    try:
        data = urllib.request.urlopen(url, timeout=60).read()
    except urllib.error.HTTPError as e:
        return "missing" if e.code == 404 else f"error: HTTP {e.code}"
    except Exception as e:
        return f"error: {e.__class__.__name__}"
    try:
        want = urllib.request.urlopen(url + ".CHECKSUM", timeout=60).read().split()[0].decode()
        if hashlib.sha256(data).hexdigest() != want:
            return "BAD CHECKSUM"
    except urllib.error.HTTPError:
        pass   # a few old files have no checksum; keep the file
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.rename(dest)
    return "ok"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--interval", default="5m")
    ap.add_argument("--start", default="2022-01")
    ap.add_argument("--end", default="2026-08")
    ap.add_argument("--out", default="data/raw")
    ap.add_argument("--kinds", nargs="+", default=["klines", "funding"],
                    choices=["klines", "funding", "premium", "spot", "metrics"])
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for kind in a.kinds:
        js = list(jobs(kind, a.symbol, a.interval, a.start, a.end, out))
        with ThreadPoolExecutor(a.workers) as ex:
            res = list(ex.map(lambda j: get(*j), js))
        counts = {s: res.count(s) for s in sorted(set(res))}
        print(f"{kind:8s} {len(js)} files: {counts}")
        for (url, _), s in zip(js, res):
            if s not in ("ok", "skip"):
                print(f"  {s:12s} {url}")
