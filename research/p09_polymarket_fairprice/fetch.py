"""p09 dev-only downloader: features/v1 tables for 2026-07-25 -> 2026-09-05 into
data/collector/p09/. Refuses any date >= 2026-09-06 (holdout, PLAN.md).
gcloud storage cp verifies CRC32C on every object.

Run from the repo root:  python research/p09_polymarket_fairprice/fetch.py [--streams ...]
"""
import argparse
import subprocess
from datetime import date, timedelta
from pathlib import Path

SRC = "gs://poly-backup-54cb99b7/features/v1"
DST = Path("data/collector/p09")
DEV_START, DEV_END, HOLDOUT_START = date(2026, 7, 25), date(2026, 9, 5), date(2026, 9, 6)
STREAMS = {
    "1s/chainlink__btc": "chainlink__btc", "meta/polymarket__markets": "polymarket__markets",
    "meta/collector_log": "collector_log", "1s/polymarket__price_change": "polymarket__price_change",
    "1s/polymarket__book": "polymarket__book", "1s/polymarket__last_trade_price": "polymarket__last_trade_price",
    "1s/binance_fut__btcusdt@bookTicker": "binance_fut__btcusdt@bookTicker",
    "1s/binance_spot__btcusdt@bookTicker": "binance_spot__btcusdt@bookTicker",
}


def dev_dates():
    d = DEV_START
    while d <= DEV_END:
        assert d < HOLDOUT_START
        yield d
        d += timedelta(days=1)


def fetch(prefix, stream):
    """One gcloud call per kind with every dev date as a source (parallel inside gcloud).
    The source list is built from dev_dates() only, so no holdout object is ever named."""
    for kind in (prefix, f"_manifest/{stream}"):
        todo = [d for d in dev_dates() if not ((DST / kind / f"date={d}").exists() and any((DST / kind / f"date={d}").iterdir()))]
        if not todo:
            continue
        (DST / kind).mkdir(parents=True, exist_ok=True)
        srcs = [f"{SRC}/{kind}/date={d}" for d in todo]
        assert all(date.fromisoformat(s.rsplit("date=", 1)[1]) < HOLDOUT_START for s in srcs)
        r = subprocess.run(["gcloud", "storage", "cp", "-r", *srcs, str(DST / kind)], capture_output=True, text=True)
        if r.returncode:
            print(f"  {kind}: {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else 'error'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--streams", nargs="+", default=list(STREAMS))
    a = ap.parse_args()
    for p in a.streams:
        print("fetch", p)
        fetch(p, STREAMS[p])
