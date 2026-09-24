"""p10 flow reduction: Binance USD-M BTCUSDT aggTrades (one UTC day per unit) -> 1-minute
order-flow aggregates, written to gs://poly-backup-54cb99b7/features/flow_v1/.

Unit = one UTC day: daily zip from data.binance.vision, sha256-checked against its .CHECKSUM
(the same rows as the monthly zips, at a resumable granularity). Output parquet + manifest
per day; a unit is skipped when its manifest has the same CODE_VERSION and input sha256.
Uploads use `gcloud storage cp`, which verifies CRC32C.

Minute label = minute END (close time), as the 5m bars. Columns (PLAN.md):
  n_agg, n_trades, buy_qty, sell_qty, buy_notional, sell_notional, big_notional (aggTrade >= $100k),
  size_median, n_runs, max_run (same-side aggTrade runs, cut at minute boundaries),
  px_first, px_last, px_high, px_low, vpin_done, vpin_absimb ($10M buckets, reset daily), n_zero.

  python reduce_flow.py --start 2022-08-01 --end 2026-08-31 --workers 20          # VM
  python reduce_flow.py --local-zip X.zip --local-out out/                          # test, no GCS
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import tempfile
import time
import traceback
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, timedelta

import numpy as np
import pandas as pd

CODE_VERSION = "flow_v1.0"
SRC = "https://data.binance.vision/data/futures/um/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-{d}.zip"
OUT = "gs://poly-backup-54cb99b7/features/flow_v1"
BIG_USD = 100_000.0
VPIN_USD = 10_000_000.0
COLS = ["agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id", "transact_time", "is_buyer_maker"]


def read_zip(raw: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        name = z.namelist()[0]
        with z.open(name) as f:
            head = f.readline()
        has_header = not head[:1].isdigit()
        with z.open(name) as f:
            df = pd.read_csv(f, header=None, names=COLS, skiprows=1 if has_header else 0,
                             dtype={"agg_trade_id": "int64", "price": "float64", "quantity": "float64",
                                    "first_trade_id": "int64", "last_trade_id": "int64", "transact_time": "int64",
                                    "is_buyer_maker": "str"}, engine="c")
    return df


def reduce_day(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    t = df["transact_time"].to_numpy()
    t_ns = np.where(t > 10**14, t * 1_000, t * 1_000_000)             # ms (futures) or us, per row
    px, qty = df["price"].to_numpy(), df["quantity"].to_numpy()
    sell = df["is_buyer_maker"].str.lower().to_numpy() == "true"       # buyer is maker -> taker SOLD
    ntr = (df["last_trade_id"] - df["first_trade_id"] + 1).to_numpy()
    real = (px > 0) & (qty > 0)
    n_zero_total = int((~real).sum())
    order = np.argsort(t_ns, kind="stable")
    t_ns, px, qty, sell, ntr, real = t_ns[order], px[order], qty[order], sell[order], ntr[order], real[order]
    minute_end = (t_ns // 60_000_000_000 + 1) * 60                     # epoch seconds of the minute END
    zero_by_min = pd.Series(~real).groupby(minute_end).sum()
    t_ns, px, qty, sell, ntr, minute_end = (a[real] for a in (t_ns, px, qty, sell, ntr, minute_end))
    notional = px * qty
    buy = ~sell

    # runs of same-side aggTrades, cut at minute boundaries
    new_run = np.ones(len(sell), bool)
    new_run[1:] = (sell[1:] != sell[:-1]) | (minute_end[1:] != minute_end[:-1])
    run_id = np.cumsum(new_run)
    run_len = np.bincount(run_id)[1:]
    run_min = minute_end[new_run]

    # VPIN: fixed $ buckets filled sequentially within the day; a trade belongs to the bucket its cum ends in
    cum = np.cumsum(notional)
    b = (cum // VPIN_USD).astype(np.int64)
    signed = np.where(buy, notional, -notional)
    nb = b.max() + 1 if len(b) else 0
    bucket_imb = np.bincount(b, weights=signed, minlength=nb)
    bucket_end_min = np.zeros(nb, np.int64)
    np.maximum.at(bucket_end_min, b, minute_end)
    complete = np.arange(nb) < (cum[-1] // VPIN_USD if len(cum) else 0)   # the last partial bucket is dropped

    g = pd.DataFrame({"m": minute_end, "px": px, "qty": qty, "buy_qty": np.where(buy, qty, 0.0),
                      "sell_qty": np.where(sell, qty, 0.0), "buy_notional": np.where(buy, notional, 0.0),
                      "sell_notional": np.where(sell, notional, 0.0),
                      "big_notional": np.where(notional >= BIG_USD, notional, 0.0), "ntr": ntr})
    agg = g.groupby("m").agg(n_agg=("px", "size"), n_trades=("ntr", "sum"), buy_qty=("buy_qty", "sum"),
                             sell_qty=("sell_qty", "sum"), buy_notional=("buy_notional", "sum"),
                             sell_notional=("sell_notional", "sum"), big_notional=("big_notional", "sum"),
                             size_median=("qty", "median"), px_first=("px", "first"), px_last=("px", "last"),
                             px_high=("px", "max"), px_low=("px", "min"))
    runs = pd.DataFrame({"m": run_min, "len": run_len}).groupby("m")["len"].agg(n_runs="size", max_run="max")
    vp = pd.DataFrame({"m": bucket_end_min[complete], "imb": np.abs(bucket_imb[complete])}).groupby("m")["imb"].agg(
        vpin_done="size", vpin_absimb="sum")
    out = agg.join(runs).join(vp)
    out["vpin_done"] = out["vpin_done"].fillna(0).astype("int64")
    out["vpin_absimb"] = out["vpin_absimb"].fillna(0.0)
    out["n_zero"] = zero_by_min.reindex(out.index).fillna(0).astype("int64")
    out.index = pd.to_datetime(out.index, unit="s", utc=True).rename("minute_end")
    info = {"rows_in": int(len(df)), "rows_real": int(real.sum()) if len(real) else 0, "n_zero": n_zero_total,
            "minutes": int(len(out)), "vpin_buckets": int(complete.sum()),
            "first": str(out.index[0]) if len(out) else None, "last": str(out.index[-1]) if len(out) else None}
    return out, info


def fetch(url: str) -> bytes:
    for attempt in range(6):
        try:
            return urllib.request.urlopen(url, timeout=120).read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            time.sleep(2 ** attempt)
        except Exception:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"download failed: {url}")


def gcs_read_json(path: str):
    r = subprocess.run(["gcloud", "storage", "cat", path], capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None


def unit(d: str) -> dict:
    t0 = time.time()
    man_path = f"{OUT}/_manifest/date={d}.json"
    url = SRC.format(d=d)
    try:
        want = fetch(url + ".CHECKSUM").split()[0].decode()
        old = gcs_read_json(man_path)
        if old and old.get("code_version") == CODE_VERSION and old.get("input_sha256") == want:
            return {"date": d, "status": "current"}
        raw = fetch(url)
        got = hashlib.sha256(raw).hexdigest()
        if got != want:
            return {"date": d, "status": "BAD_CHECKSUM"}
        out, info = reduce_day(read_zip(raw))
        with tempfile.TemporaryDirectory() as td:
            pq = os.path.join(td, f"flow_{d}.parquet")
            out.to_parquet(pq)
            dst = f"{OUT}/1m/date={d}/flow_{d}.parquet"
            r = subprocess.run(["gcloud", "storage", "cp", pq, dst], capture_output=True, text=True)
            if r.returncode:
                return {"date": d, "status": "UPLOAD_FAILED", "err": r.stderr[-300:]}
            man = {"date": d, "code_version": CODE_VERSION, "input_url": url, "input_sha256": want,
                   "input_bytes": len(raw), **info, "output": dst, "output_bytes": os.path.getsize(pq),
                   "seconds": round(time.time() - t0, 2)}
            mp = os.path.join(td, "m.json")
            open(mp, "w").write(json.dumps(man))
            r = subprocess.run(["gcloud", "storage", "cp", mp, man_path], capture_output=True, text=True)
            if r.returncode:
                return {"date": d, "status": "MANIFEST_FAILED", "err": r.stderr[-300:]}
        return {"date": d, "status": "ok", "seconds": man["seconds"], "rows": info["rows_in"]}
    except urllib.error.HTTPError as e:
        return {"date": d, "status": f"HTTP_{e.code}"}
    except Exception:
        return {"date": d, "status": "ERROR", "err": traceback.format_exc()[-500:]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--local-zip")
    ap.add_argument("--local-out")
    a = ap.parse_args()
    if a.local_zip:
        t0 = time.time()
        out, info = reduce_day(read_zip(open(a.local_zip, "rb").read()))
        os.makedirs(a.local_out, exist_ok=True)
        out.to_parquet(os.path.join(a.local_out, os.path.basename(a.local_zip).replace(".zip", ".parquet")))
        print(json.dumps(info), f"{time.time() - t0:.1f}s")
        raise SystemExit
    d0, d1 = date.fromisoformat(a.start), date.fromisoformat(a.end)
    days = [str(d0 + timedelta(i)) for i in range((d1 - d0).days + 1)]
    res = []
    with ProcessPoolExecutor(a.workers) as ex:
        futs = {ex.submit(unit, d): d for d in days}
        for i, f in enumerate(as_completed(futs)):
            r = f.result()
            res.append(r)
            if r["status"] not in ("ok", "current") or i % 50 == 0:
                print(i, json.dumps(r), flush=True)
    summary = pd.Series([r["status"] for r in res]).value_counts().to_dict()
    print("SUMMARY", json.dumps(summary), flush=True)
