"""p13 step 2: reduce `hyperliquid-archive/market_data/<day>/<H>/l2Book/<COIN>.lz4` to per-snapshot
book statistics, keeping only snapshots inside event windows, plus hourly baselines of every
snapshot. Runs on the Tokyo box; only the outputs leave AWS. Resumable per day (manifest).

Per snapshot (exchange `time`, ms): bid, ask, spread_bps, depth notional within 10 / 50 bps of mid
per side (bid_d10, ask_d10, bid_d50, ask_d50), cost in bps vs mid to SELL / BUY $10k and $50k
(sell10k, buy10k, sell50k, buy50k; NaN if the 20 levels don't cover it).

  python book_windows.py --windows windows_times.parquet --hours hours.parquet --out books/
      (hours.parquet: coin, day YYYYMMDD, hour 0-23 = the coin-hours touched by any window; S3 reads
       via boto3 + lz4.frame, 8 in parallel)
  python book_windows.py --windows windows_times.parquet --local BTC.lz4 --coin BTC --out /tmp/x

outputs:  snaps/<day>.parquet   rows for snapshots in [t0 - 65 s, t0 + 310 s] of any window
          hourly/<day>.parquet  per (coin, hour): n, gap p50/max, spread p50/p90, depth p50, cost p50
          manifest/<day>.json
"""
from __future__ import annotations

import argparse, bisect, datetime as dt, json, math, pathlib, subprocess, time
from concurrent.futures import ThreadPoolExecutor

import pyarrow as pa, pyarrow.parquet as pq

try:
    import orjson
    loads = orjson.loads
except ImportError:
    import json as _j
    loads = _j.loads

BUCKET = "s3://hyperliquid-archive/market_data"
COINS = ("BTC", "ETH", "SOL", "HYPE", "ZEC", "XRP")
PRE, POST = 65_000, 310_000
COLS = ["coin", "t", "bid", "ask", "spread_bps", "bid_d10", "ask_d10", "bid_d50", "ask_d50",
        "sell10k", "buy10k", "sell50k", "buy50k"]


def cost(levels, mid, notional):
    """bps vs mid to take `notional` against these levels (walking from the top); NaN if short."""
    need, got_q, got_n = notional, 0.0, 0.0
    for lv in levels:
        px = float(lv["px"]); q = float(lv["sz"])
        take = min(q, (need - got_n) / px)
        got_q += take; got_n += take * px
        if got_n >= need - 1e-9:
            return abs(got_n / got_q / mid - 1) * 1e4
    return math.nan


def depth(levels, mid, bps):
    lim = bps / 1e4
    tot = 0.0
    for lv in levels:
        px = float(lv["px"])
        if abs(px / mid - 1) > lim:
            break
        tot += px * float(lv["sz"])
    return tot


def snap_stats(bids, asks):
    bid = float(bids[0]["px"]); ask = float(asks[0]["px"]); mid = (bid + ask) / 2
    return (bid, ask, (ask - bid) / mid * 1e4, depth(bids, mid, 10), depth(asks, mid, 10),
            depth(bids, mid, 50), depth(asks, mid, 50), cost(bids, mid, 1e4), cost(asks, mid, 1e4),
            cost(bids, mid, 5e4), cost(asks, mid, 5e4))


class Windows:
    def __init__(self, path):
        t = pq.read_table(path).to_pydict()
        self.by = {}
        for c, t0 in zip(t["coin"], t["t0"]):
            self.by.setdefault(c, []).append(t0)
        for c in self.by:
            self.by[c].sort()

    def inside(self, coin, t):
        s = self.by.get(coin)
        if not s:
            return False
        i = bisect.bisect_right(s, t + PRE)          # windows with t0 - PRE <= t
        return i > 0 and s[i - 1] + POST >= t or any(s[j] + POST >= t for j in range(max(0, i - 50), i))


def pct(v, q):
    if not v:
        return math.nan
    v = sorted(x for x in v if x == x)
    return v[min(len(v) - 1, int(q * len(v)))] if v else math.nan


def process(lines, coin, win: Windows, rows: dict, hourly: list, hour_key):
    ts, spreads, d50, c10 = [], [], [], []
    n = 0
    for line in lines:
        d = loads(line)
        data = d["raw"]["data"] if "raw" in d else d
        bids, asks = data["levels"]
        if not bids or not asks:
            continue
        t = data["time"]; n += 1
        st = snap_stats(bids, asks)
        ts.append(t); spreads.append(st[2]); d50.append(min(st[5], st[6])); c10.append(max(st[7], st[8]))
        if win.inside(coin, t):
            for k, v in zip(COLS, (coin, t) + st):
                rows[k].append(v)
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    hourly.append(dict(coin=coin, hour=hour_key, n=n, gap_p50=pct(gaps, .5), gap_max=max(gaps) if gaps else math.nan,
                       spread_p50=pct(spreads, .5), spread_p90=pct(spreads, .9), depth50_min_side_p50=pct(d50, .5),
                       cost10k_worse_side_p50=pct(c10, .5)))


def stream(key):
    s3 = subprocess.Popen(["aws", "s3", "cp", key, "-", "--request-payer", "requester", "--only-show-errors"],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    lz = subprocess.Popen(["lz4", "-dc"], stdin=s3.stdout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    s3.stdout.close()
    yield from lz.stdout
    if lz.wait() != 0 or s3.wait() != 0:
        raise RuntimeError(f"stream failed: {key}: {s3.stderr.read().decode()[:200]}")


_s3 = None


def fetch(key):
    """compressed bytes of one object (boto3, requester pays), or the exception."""
    global _s3
    import boto3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name="us-east-1")
    b, k = key[5:].split("/", 1)
    try:
        return _s3.get_object(Bucket=b, Key=k, RequestPayer="requester")["Body"].read()
    except Exception as e:
        return e


def run_day(day, win, out, wanted):
    man = out / "manifest" / f"{day}.json"
    if man.exists() and json.loads(man.read_text()).get("status") == "ok":
        return "skip"
    import lz4.frame
    rows = {k: [] for k in COLS}; hourly = []; status = []
    keys = [(c, h, f"{BUCKET}/{day}/{h}/l2Book/{c}.lz4") for c, h in sorted(wanted)]
    with ThreadPoolExecutor(8) as ex:
        blobs = list(ex.map(lambda x: fetch(x[2]), keys))
    for (c, h, key), blob in zip(keys, blobs):
        try:
            if isinstance(blob, Exception):
                raise blob
            process(lz4.frame.decompress(blob).splitlines(), c, win, rows, hourly, f"{day}T{h:02d}")
            status.append(dict(key=key, status="ok", bytes=len(blob)))
        except Exception as e:
            status.append(dict(key=key, status=f"error: {e}"[:300]))
    for name, tab in (("snaps", rows), ("hourly", {k: [r[k] for r in hourly] for k in (hourly[0] if hourly else {})})):
        (out / name).mkdir(parents=True, exist_ok=True)
        if tab:
            pq.write_table(pa.table(tab), out / name / f"{day}.parquet", compression="zstd")
    n_ok = sum(s["status"] == "ok" for s in status)
    man.parent.mkdir(parents=True, exist_ok=True)
    man.write_text(json.dumps(dict(day=day, status="ok" if n_ok else "empty", files_ok=n_ok, files=len(status),
                                   bytes=sum(x.get("bytes", 0) for x in status),
                                   snaps_kept=len(rows["t"]), errors=[s for s in status if s["status"] != "ok"]), indent=1))
    return f"ok {n_ok}/{len(status)} files, {len(rows['t'])} snaps kept"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--windows", required=True)
    ap.add_argument("--hours"); ap.add_argument("--local"); ap.add_argument("--coin")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = pathlib.Path(a.out); win = Windows(a.windows)
    if a.local:
        t0 = time.time(); rows = {k: [] for k in COLS}; hourly = []
        p = subprocess.Popen(["lz4", "-dc", a.local], stdout=subprocess.PIPE)
        process(p.stdout, a.coin, win, rows, hourly, "local"); p.wait()
        print(hourly[0], f"kept {len(rows['t'])} in {time.time()-t0:.1f}s")
        raise SystemExit
    hrs = pq.read_table(a.hours).to_pydict()
    by_day = {}
    for c, d, h in zip(hrs["coin"], hrs["day"], hrs["hour"]):
        by_day.setdefault(d, set()).add((c, h))
    for day in sorted(by_day):
        t0 = time.time()
        print(day, run_day(day, win, out, by_day[day]), f"{time.time()-t0:.0f}s", flush=True)
