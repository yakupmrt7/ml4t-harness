"""p13: reduce Hyperliquid `node_fills_by_block` hourly files to what the event study needs.

Runs where the archive is cheap to read (an EC2 box in ap-northeast-1, same region as the bucket),
so only the small outputs leave AWS. Resumable, one unit = one UTC day of hourly files, with a
manifest per day (p08 conventions). Stdlib + pyarrow (+ orjson if installed); needs the `aws` and
`lz4` CLIs.

Per day it writes, under --out:
  liq/<YYYYMMDD>.parquet    every fill row carrying `liquidation`, ALL coins, both sides
  ticks/<YYYYMMDD>.parquet  one row per trade for --coins (taker side), with the liquidation flag
  addrs/<YYYYMMDD>.parquet  every address that filled that day: n_fills, notional, first/last ms
  manifest/<YYYYMMDD>.json  per hour: source key, bytes, lines, fills, liq rows, status

  python extract.py --days 20250727:20260925 --out out/          # on the box
  python extract.py --local data/raw/hl_sample/fills_20260920_10.lz4 --out /tmp/x   # test

Timestamps: fill `time` is ms epoch UTC (the trade's block time); `block_time` is kept on liq rows.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys
import time

import pyarrow as pa
import pyarrow.parquet as pq

try:
    import orjson
    loads = orjson.loads
except ImportError:  # 2-3x slower, same result
    loads = json.loads

BUCKET = "s3://hl-mainnet-node-data/node_fills_by_block/hourly"
COINS = ("BTC", "ETH", "SOL", "HYPE", "ZEC", "XRP")

LIQ_COLS = ["time", "block_time", "block_number", "user", "coin", "px", "sz", "side", "dir",
            "startPosition", "closedPnl", "crossed", "fee", "hash", "oid", "tid",
            "liq_user", "liq_markPx", "liq_method"]
TICK_COLS = ["time", "coin", "px", "sz", "side", "tid", "liq", "liq_method"]


class Day:
    def __init__(self):
        self.liq = {c: [] for c in LIQ_COLS}
        self.ticks = {c: [] for c in TICK_COLS}
        self.addrs: dict[str, list] = {}   # user -> [n_fills, notional, first_ms, last_ms]

    def feed(self, lines) -> dict:
        n_lines = n_fills = n_liq = 0
        coins = set(COINS)
        seen_tid = set()            # a trade appears once per side; keep one tick per (coin, tid)
        for line in lines:
            n_lines += 1
            blk = loads(line)
            for user, f in blk["events"]:
                n_fills += 1
                t = f["time"]; px = float(f["px"]); sz = float(f["sz"])
                a = self.addrs.get(user)
                if a is None:
                    self.addrs[user] = [1, px * sz, t, t]
                else:
                    a[0] += 1; a[1] += px * sz; a[3] = t
                liq = f.get("liquidation")
                if liq is not None:
                    n_liq += 1
                    L = self.liq
                    for k, v in (("time", t), ("block_time", blk["block_time"]),
                                 ("block_number", blk["block_number"]), ("user", user),
                                 ("coin", f["coin"]), ("px", px), ("sz", sz), ("side", f["side"]),
                                 ("dir", f["dir"]), ("startPosition", float(f["startPosition"])),
                                 ("closedPnl", float(f["closedPnl"])), ("crossed", f["crossed"]),
                                 ("fee", float(f["fee"])), ("hash", f["hash"]), ("oid", f["oid"]),
                                 ("tid", f["tid"]), ("liq_user", liq.get("liquidatedUser")),
                                 ("liq_markPx", float(liq["markPx"])), ("liq_method", liq.get("method"))):
                        L[k].append(v)
                if f["coin"] in coins and f["crossed"]:
                    key = (f["coin"], f["tid"])
                    if key in seen_tid:
                        continue
                    seen_tid.add(key)
                    T = self.ticks
                    T["time"].append(t); T["coin"].append(f["coin"]); T["px"].append(px)
                    T["sz"].append(sz); T["side"].append(f["side"]); T["tid"].append(f["tid"])
                    T["liq"].append(liq is not None)
                    T["liq_method"].append(None if liq is None else liq.get("method"))
        return dict(lines=n_lines, fills=n_fills, liq_rows=n_liq)

    def write(self, out: pathlib.Path, day: str):
        for name, cols in (("liq", self.liq), ("ticks", self.ticks)):
            (out / name).mkdir(parents=True, exist_ok=True)
            pq.write_table(pa.table(cols), out / name / f"{day}.parquet", compression="zstd")
        (out / "addrs").mkdir(parents=True, exist_ok=True)
        u = list(self.addrs)
        v = list(self.addrs.values())
        pq.write_table(pa.table({"user": u, "n_fills": [x[0] for x in v], "notional": [x[1] for x in v],
                                 "first_ms": [x[2] for x in v], "last_ms": [x[3] for x in v]}),
                       out / "addrs" / f"{day}.parquet", compression="zstd")


def stream_hour(key: str):
    """Yield decompressed lines of one hourly object without touching disk."""
    s3 = subprocess.Popen(["aws", "s3", "cp", key, "-", "--request-payer", "requester", "--only-show-errors"],
                          stdout=subprocess.PIPE)
    lz = subprocess.Popen(["lz4", "-dc"], stdin=s3.stdout, stdout=subprocess.PIPE)
    s3.stdout.close()
    counter = {"bytes": 0}
    for line in lz.stdout:
        counter["bytes"] += len(line)
        yield line
    if lz.wait() != 0 or s3.wait() != 0:
        raise RuntimeError(f"stream failed: {key} (aws {s3.returncode}, lz4 {lz.returncode})")


def run_day(day: str, out: pathlib.Path, hours=range(24)):
    man = out / "manifest" / f"{day}.json"
    if man.exists() and json.loads(man.read_text()).get("status") == "ok":
        return "skip"
    d = Day(); rows = []; status = "ok"
    for h in hours:
        key = f"{BUCKET}/{day}/{h}.lz4"
        t0 = time.time()
        try:
            r = d.feed(stream_hour(key))
            r.update(hour=h, key=key, status="ok", seconds=round(time.time() - t0, 1))
        except Exception as e:  # a missing hour is recorded, not fatal (first/last day are partial)
            r = dict(hour=h, key=key, status=f"error: {e}")
        rows.append(r)
    if not any(r["status"] == "ok" for r in rows):
        status = "empty"
    d.write(out, day)
    man.parent.mkdir(parents=True, exist_ok=True)
    man.write_text(json.dumps(dict(day=day, status=status, hours=rows,
                                   n_liq=len(d.liq["time"]), n_ticks=len(d.ticks["time"]),
                                   n_addrs=len(d.addrs)), indent=1))
    return status


def days_between(a: str, b: str):
    d0 = dt.datetime.strptime(a, "%Y%m%d"); d1 = dt.datetime.strptime(b, "%Y%m%d")
    while d0 <= d1:
        yield d0.strftime("%Y%m%d"); d0 += dt.timedelta(days=1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", help="YYYYMMDD:YYYYMMDD inclusive")
    ap.add_argument("--local", help="test on one local .lz4 hourly file instead of S3")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    if a.local:
        t0 = time.time()
        p = subprocess.Popen(["lz4", "-dc", a.local], stdout=subprocess.PIPE)
        d = Day(); r = d.feed(p.stdout); p.wait()
        d.write(out, "local")
        print(r, f"ticks {len(d.ticks['time'])} addrs {len(d.addrs)} in {time.time()-t0:.1f}s", flush=True)
        sys.exit(0)
    first, last = a.days.split(":")
    for day in days_between(first, last):
        t0 = time.time()
        s = run_day(day, out)
        print(day, s, f"{time.time()-t0:.0f}s", flush=True)
