"""p08 reduction job: raw collector JSON-in-parquet -> 1s / 1m feature tables
(+ event-level trades), written under gs://<bucket>/features/v1/.

READ-ONLY on eu-raw_pq/. Writes only under features/v1/. Never deletes.

Unit of work = (date, stream, hour), one input object each. Resumable: a unit
is skipped when its manifest records the same input generation, size and
CODE_VERSION. Outputs are written before the manifest, so a crash redoes the
unit; GCS object creation is atomic, so a partial write is never visible.

Memory: each row group is parsed, converted to COLUMN ARRAYS, and the dicts
dropped. Accumulating parsed dicts instead costs GBs per worker and OOM-killed
the first pilot (a 2.6M-row price_change file reached 4.7 GB RSS).

Layout written:
  features/v1/1s/<stream>/date=YYYY-MM-DD/<stream>__<HH>.parquet
  features/v1/1m/<stream>/date=YYYY-MM-DD/<stream>__<HH>.parquet
  features/v1/events/<stream>/date=YYYY-MM-DD/<stream>__<HH>.parquet   (trades only)
  features/v1/meta/<stream>/date=YYYY-MM-DD/<stream>__<HH>.parquet     (markets/log/tick)
  features/v1/_manifest/<stream>/date=YYYY-MM-DD/<HH>.json

Time keys (SCHEMAS.md): payload event time where it exists, else rt_ns. Streams
with no payload timestamp cannot have their receive lag measured at all; their
manifests record lag_measurable=false and null lags.

Usage:
  python reduce.py --start 2026-09-10 --end 2026-09-10 --workers 20
  python reduce.py --local-dir /tmp/p08 --date 2026-09-10 --hour 12   (test, no GCS)
"""
from __future__ import annotations

import argparse
import io
import json
import os
import random
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date as Date, timedelta

import numpy as np
import orjson
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

CODE_VERSION = "p08-v4"   # v4: drop zero-price/zero-qty prints from trade aggregates
BUCKET = "poly-backup-54cb99b7"
RAW_PREFIX = "eu-raw_pq"
OUT_PREFIX = "features/v1"

STREAMS = [
    "binance_fut__btcusdt@bookTicker", "binance_fut__btcusdt@depth20@100ms", "binance_fut__btcusdt@trade",
    "binance_spot__btcusdt@bookTicker", "binance_spot__btcusdt@trade", "chainlink__btc",
    "polymarket__book", "polymarket__last_trade_price", "polymarket__price_change",
    "polymarket__markets", "polymarket__tick_size_change", "collector_log",
]
EVENT_LEVEL = {"binance_fut__btcusdt@trade", "binance_spot__btcusdt@trade"}
META = {"polymarket__markets", "polymarket__tick_size_change", "collector_log"}
RECEIVE_TIME = {"binance_spot__btcusdt@bookTicker", "polymarket__book"} | META


# ---------------------------------------------------------------- helpers

def _intern(vals, cache):
    """One Python string per distinct value (asset_id / market repeat heavily)."""
    return [cache.setdefault(v, v) for v in vals]


def _agg(df, keys, spec):
    # observed=True: categorical keys must not produce every category combination
    g = df.groupby(keys, sort=True, observed=True)
    return pd.DataFrame({name: fn(g) for name, fn in spec.items()}).reset_index()


def _cat(v):
    """Group keys as categorical codes: 5M Python strings per column otherwise."""
    return pd.Categorical(v)


def _twap(ts, val, bucket, width):
    nxt = np.empty(len(ts), dtype=np.float64)
    nxt[:-1] = ts[1:]
    nxt[-1] = ts[-1]
    w = np.clip(np.minimum(nxt, (bucket + 1) * width) - ts, 0, None)
    d = pd.DataFrame({"bucket": bucket, "wv": w * val, "w": w}).groupby("bucket").sum()
    return (d["wv"] / d["w"].replace(0, np.nan)).rename("mid_twap")


LAG = {"lag_ms_p50": lambda g: g["lag_ms"].median(), "lag_ms_p95": lambda g: g["lag_ms"].quantile(0.95)}


# ---------------------------------------------------------------- extractors
# rows (payload dicts of one row group) + rt_ns -> dict of column arrays

def x_book_ticker(rows, rt_ns, cache):
    n = len(rows)
    ev = "E" in rows[0]
    ts = np.fromiter((r["E"] for r in rows), np.int64, n) if ev else rt_ns // 1_000_000
    return {"ts": ts,
            "b": np.fromiter((float(r["b"]) for r in rows), np.float64, n),
            "a": np.fromiter((float(r["a"]) for r in rows), np.float64, n),
            "B": np.fromiter((float(r["B"]) for r in rows), np.float64, n),
            "A": np.fromiter((float(r["A"]) for r in rows), np.float64, n),
            "lag_ms": (rt_ns / 1e6 - ts) if ev else np.full(n, np.nan)}


def x_depth20(rows, rt_ns, cache):
    n = len(rows)
    ts = np.fromiter((r["E"] for r in rows), np.int64, n)
    out = {k: np.empty(n) for k in ("bid", "ask", "bid_sz", "ask_sz", "dbid5", "dask5", "dbid20", "dask20")}
    for i, r in enumerate(rows):
        bp = np.array([float(p) for p, _ in r["b"]]); bq = np.array([float(q) for _, q in r["b"]])
        ap = np.array([float(p) for p, _ in r["a"]]); aq = np.array([float(q) for _, q in r["a"]])
        out["bid"][i], out["ask"][i] = bp[0], ap[0]
        out["bid_sz"][i], out["ask_sz"][i] = bq[0], aq[0]
        out["dbid5"][i], out["dask5"][i] = (bp[:5] * bq[:5]).sum(), (ap[:5] * aq[:5]).sum()
        out["dbid20"][i], out["dask20"][i] = (bp * bq).sum(), (ap * aq).sum()
    out["ts"] = ts
    out["lag_ms"] = rt_ns / 1e6 - ts
    return out


def x_trade(rows, rt_ns, cache):
    n = len(rows)
    ts = np.fromiter((r.get("T", r["E"]) for r in rows), np.int64, n)
    return {"ts": ts, "px": np.fromiter((float(r["p"]) for r in rows), np.float64, n),
            "qty": np.fromiter((float(r["q"]) for r in rows), np.float64, n),
            "m": np.fromiter((bool(r["m"]) for r in rows), bool, n),
            "trade_id": np.fromiter((int(r["t"]) for r in rows), np.int64, n),
            # X: MARKET, or NA for liquidation/ADL prints, which the public
            # aggTrades archive leaves out (see VALIDATION.md)
            "xtype": _intern([str(r.get("X", "")) for r in rows], cache),
            "rt_ns": rt_ns, "lag_ms": rt_ns / 1e6 - ts}


def x_chainlink(rows, rt_ns, cache):
    n = len(rows)
    rid = np.array([str(r["round_id"]) for r in rows])          # 20 digits: does not fit int64
    keep = np.concatenate([[True], rid[1:] != rid[:-1]])        # dedupe repeated polls of one round
    upd = np.fromiter((int(r["updated_at"]) for r in rows), np.int64, n)[keep]
    return {"ts": upd * 1000,
            "price": np.fromiter((float(r["answer"]) / 1e8 for r in rows), np.float64, n)[keep],
            "updated_at": upd, "lag_ms": rt_ns[keep] / 1e6 - upd * 1000}


def x_pm_price_change(rows, rt_ns, cache):
    ts, aid, mkt, bb, ba, buy, sell, lag = [], [], [], [], [], [], [], []
    for r, rt in zip(rows, rt_ns):
        t = int(r["timestamp"])
        m = r["market"]
        for c in r["price_changes"]:
            ts.append(t); aid.append(c["asset_id"]); mkt.append(m)
            bb.append(float(c["best_bid"] or "nan")); ba.append(float(c["best_ask"] or "nan"))
            sz = float(c["size"] or 0)
            buy.append(sz if c["side"] == "BUY" else 0.0)
            sell.append(sz if c["side"] == "SELL" else 0.0)
            lag.append(rt / 1e6 - t)
    return {"ts": np.asarray(ts, np.int64), "asset_id": _intern(aid, cache), "market": _intern(mkt, cache),
            "bb": np.asarray(bb), "ba": np.asarray(ba), "buy": np.asarray(buy), "sell": np.asarray(sell),
            "lag_ms": np.asarray(lag)}


def x_pm_book(rows, rt_ns, cache):
    n = len(rows)
    out = {k: np.full(n, np.nan) for k in ("bb", "ba")}
    for k in ("bsz", "asz", "d1", "d5", "tot", "lv"):
        out[k] = np.zeros(n)
    aid, mkt = [], []
    for i, r in enumerate(rows):
        bids = [(float(x["price"]), float(x["size"])) for x in r.get("bids") or []]
        asks = [(float(x["price"]), float(x["size"])) for x in r.get("asks") or []]
        aid.append(r["asset_id"]); mkt.append(r["market"])
        out["lv"][i] = len(bids) + len(asks)
        out["tot"][i] = sum(s for _, s in bids) + sum(s for _, s in asks)
        if bids:
            p, s = max(bids, key=lambda x: x[0]); out["bb"][i], out["bsz"][i] = p, s
        if asks:
            p, s = min(asks, key=lambda x: x[0]); out["ba"][i], out["asz"][i] = p, s
        if bids and asks:
            out["d1"][i] = (sum(s for p, s in bids if p >= out["bb"][i] - 0.01)
                            + sum(s for p, s in asks if p <= out["ba"][i] + 0.01))
            out["d5"][i] = (sum(s for p, s in bids if p >= out["bb"][i] - 0.05)
                            + sum(s for p, s in asks if p <= out["ba"][i] + 0.05))
    out["ts"] = rt_ns // 1_000_000                              # no payload timestamp
    out["asset_id"] = _intern(aid, cache)
    out["market"] = _intern(mkt, cache)
    return out


def x_pm_last_trade(rows, rt_ns, cache):
    n = len(rows)
    ts = np.fromiter((int(r["timestamp"]) for r in rows), np.int64, n)
    sz = np.fromiter((float(r["size"]) for r in rows), np.float64, n)
    side = np.array([r["side"] for r in rows])
    return {"ts": ts, "asset_id": _intern([r["asset_id"] for r in rows], cache),
            "market": _intern([r["market"] for r in rows], cache),
            "px": np.fromiter((float(r["price"]) for r in rows), np.float64, n), "sz": sz,
            "buy": np.where(side == "BUY", sz, 0.0), "sell": np.where(side == "SELL", sz, 0.0),
            "lag_ms": rt_ns / 1e6 - ts}


META_FIELDS = {
    "polymarket__markets": ["id", "conditionId", "slug", "question", "clobTokenIds", "outcomes", "outcomePrices",
                            "startDate", "endDate", "orderPriceMinTickSize", "orderMinSize", "bestBid", "bestAsk",
                            "spread", "liquidity", "active", "closed", "resolutionSource"],
    "polymarket__tick_size_change": ["market", "asset_id", "old_tick_size", "new_tick_size", "timestamp"],
    "collector_log": ["source", "event", "slug", "n_tokens"],
}


def x_meta(stream):
    def f(rows, rt_ns, cache):
        out = {k: [None if r.get(k) is None else str(r.get(k)) for r in rows] for k in META_FIELDS[stream]}
        out["rt_ns"] = rt_ns
        return out
    return f


# ---------------------------------------------------------------- aggregators
# concatenated columns -> one row per (bucket[, market, asset_id])

def a_book_ticker(c, width):
    mid = (c["a"] + c["b"]) / 2
    sz = c["A"] + c["B"]
    safe = np.where(sz > 0, sz, 1)
    bucket = c["ts"] // width
    df = pd.DataFrame({"bucket": bucket, "b": c["b"], "a": c["a"], "B": c["B"], "A": c["A"], "mid": mid,
                       "micro": np.where(sz > 0, (c["a"] * c["B"] + c["b"] * c["A"]) / safe, mid),
                       "spread_bps": (c["a"] - c["b"]) / mid * 1e4,
                       "imb": np.where(sz > 0, (c["B"] - c["A"]) / safe, 0.0), "lag_ms": c["lag_ms"]})
    out = _agg(df, ["bucket"], {
        "n_msgs": lambda g: g.size(), "mid_last": lambda g: g["mid"].last(), "mid_mean": lambda g: g["mid"].mean(),
        "micro_last": lambda g: g["micro"].last(), "bid_last": lambda g: g["b"].last(),
        "ask_last": lambda g: g["a"].last(), "bid_sz_last": lambda g: g["B"].last(),
        "ask_sz_last": lambda g: g["A"].last(), "spread_bps_mean": lambda g: g["spread_bps"].mean(),
        "spread_bps_last": lambda g: g["spread_bps"].last(), "imb_mean": lambda g: g["imb"].mean(),
        "imb_last": lambda g: g["imb"].last(), **LAG})
    return out.merge(_twap(c["ts"], mid, bucket, width), left_on="bucket", right_index=True, how="left")


def a_depth20(c, width):
    mid = (c["bid"] + c["ask"]) / 2
    top = c["bid_sz"] + c["ask_sz"]
    d5, d20 = c["dbid5"] + c["dask5"], c["dbid20"] + c["dask20"]
    df = pd.DataFrame({
        "bucket": c["ts"] // width, "mid": mid, "bid": c["bid"], "ask": c["ask"],
        "bid_sz": c["bid_sz"], "ask_sz": c["ask_sz"], "dbid5": c["dbid5"], "dask5": c["dask5"],
        "dbid20": c["dbid20"], "dask20": c["dask20"], "spread_bps": (c["ask"] - c["bid"]) / mid * 1e4,
        "micro": np.where(top > 0, (c["ask"] * c["bid_sz"] + c["bid"] * c["ask_sz"]) / np.where(top > 0, top, 1), mid),
        "imb1": np.where(top > 0, (c["bid_sz"] - c["ask_sz"]) / np.where(top > 0, top, 1), 0.0),
        "imb5": np.where(d5 > 0, (c["dbid5"] - c["dask5"]) / np.where(d5 > 0, d5, 1), 0.0),
        "imb20": np.where(d20 > 0, (c["dbid20"] - c["dask20"]) / np.where(d20 > 0, d20, 1), 0.0),
        "lag_ms": c["lag_ms"]})
    return _agg(df, ["bucket"], {
        "n_msgs": lambda g: g.size(), "mid_last": lambda g: g["mid"].last(), "mid_mean": lambda g: g["mid"].mean(),
        "micro_last": lambda g: g["micro"].last(), "bid_last": lambda g: g["bid"].last(),
        "ask_last": lambda g: g["ask"].last(), "bid_sz_last": lambda g: g["bid_sz"].last(),
        "ask_sz_last": lambda g: g["ask_sz"].last(), "spread_bps_mean": lambda g: g["spread_bps"].mean(),
        "depth_bid_5_usd_mean": lambda g: g["dbid5"].mean(), "depth_ask_5_usd_mean": lambda g: g["dask5"].mean(),
        "depth_bid_20_usd_mean": lambda g: g["dbid20"].mean(), "depth_ask_20_usd_mean": lambda g: g["dask20"].mean(),
        "imb1_mean": lambda g: g["imb1"].mean(), "imb5_mean": lambda g: g["imb5"].mean(),
        "imb20_mean": lambda g: g["imb20"].mean(), "imb20_last": lambda g: g["imb20"].last(), **LAG})


def a_trade(c, width):
    sgn = np.where(c["m"], -1.0, 1.0)                           # m=True -> aggressor SOLD
    df = pd.DataFrame({"bucket": c["ts"] // width, "px": c["px"], "qty": c["qty"],
                       "signed": c["qty"] * sgn, "notional": c["px"] * c["qty"],
                       "buy": np.where(~c["m"], c["qty"], 0.0), "sell": np.where(c["m"], c["qty"], 0.0),
                       "lag_ms": c["lag_ms"]})
    # The futures stream carries zero-price, zero-qty prints (X="NA", ~0.4% of
    # rows, absent from the public aggTrades archive). Left in, they set
    # px_min = 0 and can set px_last = 0. They stay in the event table, tagged
    # by trade_type, but never enter the aggregates.
    real = (df["px"] > 0) & (df["qty"] > 0)
    zero_per_bucket = df.loc[~real].groupby("bucket").size().rename("n_zero_prints")
    df = df[real]
    out = _agg(df, ["bucket"], {
        "n_trades": lambda g: g.size(), "volume": lambda g: g["qty"].sum(),
        "buy_volume": lambda g: g["buy"].sum(), "sell_volume": lambda g: g["sell"].sum(),
        "signed_volume": lambda g: g["signed"].sum(), "notional": lambda g: g["notional"].sum(),
        "vwap": lambda g: g["notional"].sum() / g["qty"].sum(), "px_last": lambda g: g["px"].last(),
        "px_max": lambda g: g["px"].max(), "px_min": lambda g: g["px"].min(),
        "max_trade_qty": lambda g: g["qty"].max(), **LAG})
    out = out.merge(zero_per_bucket, left_on="bucket", right_index=True, how="left")
    out["n_zero_prints"] = out["n_zero_prints"].fillna(0).astype("int64")
    return out


def a_chainlink(c, width):
    df = pd.DataFrame({"bucket": c["ts"] // width, "price": c["price"], "updated_at": c["updated_at"],
                       "lag_ms": c["lag_ms"]})
    return _agg(df, ["bucket"], {
        "n_rounds": lambda g: g.size(), "price_last": lambda g: g["price"].last(),
        "price_mean": lambda g: g["price"].mean(), "updated_at_last": lambda g: g["updated_at"].last(), **LAG})


def a_pm_price_change(c, width):
    mid = (c["bb"] + c["ba"]) / 2
    df = pd.DataFrame({"bucket": c["ts"] // width, "market": _cat(c["market"]), "asset_id": _cat(c["asset_id"]),
                       "bb": c["bb"], "ba": c["ba"], "mid": mid, "spread": c["ba"] - c["bb"],
                       "buy": c["buy"], "sell": c["sell"], "lag_ms": c["lag_ms"]})
    return _agg(df, ["bucket", "market", "asset_id"], {
        "n_changes": lambda g: g.size(), "best_bid_last": lambda g: g["bb"].last(),
        "best_ask_last": lambda g: g["ba"].last(), "mid_last": lambda g: g["mid"].last(),
        "mid_mean": lambda g: g["mid"].mean(), "spread_last": lambda g: g["spread"].last(),
        "buy_size": lambda g: g["buy"].sum(), "sell_size": lambda g: g["sell"].sum(), **LAG})


def a_pm_book(c, width):
    df = pd.DataFrame({"bucket": c["ts"] // width, "market": _cat(c["market"]), "asset_id": _cat(c["asset_id"]),
                       "bb": c["bb"], "ba": c["ba"], "mid": (c["bb"] + c["ba"]) / 2, "spread": c["ba"] - c["bb"],
                       "bsz": c["bsz"], "asz": c["asz"], "d1": c["d1"], "d5": c["d5"], "tot": c["tot"],
                       "lv": c["lv"]})
    return _agg(df, ["bucket", "market", "asset_id"], {
        "n_snapshots": lambda g: g.size(), "best_bid_last": lambda g: g["bb"].last(),
        "best_ask_last": lambda g: g["ba"].last(), "mid_last": lambda g: g["mid"].last(),
        "spread_last": lambda g: g["spread"].last(), "bid_sz_last": lambda g: g["bsz"].last(),
        "ask_sz_last": lambda g: g["asz"].last(), "depth_1c_last": lambda g: g["d1"].last(),
        "depth_5c_last": lambda g: g["d5"].last(), "total_size_last": lambda g: g["tot"].last(),
        "n_levels_last": lambda g: g["lv"].last()})


def a_pm_last_trade(c, width):
    df = pd.DataFrame({"bucket": c["ts"] // width, "market": _cat(c["market"]), "asset_id": _cat(c["asset_id"]),
                       "px": c["px"], "sz": c["sz"], "buy": c["buy"], "sell": c["sell"], "lag_ms": c["lag_ms"]})
    return _agg(df, ["bucket", "market", "asset_id"], {
        "n_trades": lambda g: g.size(), "px_last": lambda g: g["px"].last(), "size": lambda g: g["sz"].sum(),
        "buy_size": lambda g: g["buy"].sum(), "sell_size": lambda g: g["sell"].sum(), **LAG})


EXTRACTORS = {
    "binance_fut__btcusdt@bookTicker": x_book_ticker, "binance_spot__btcusdt@bookTicker": x_book_ticker,
    "binance_fut__btcusdt@depth20@100ms": x_depth20,
    "binance_fut__btcusdt@trade": x_trade, "binance_spot__btcusdt@trade": x_trade,
    "chainlink__btc": x_chainlink, "polymarket__price_change": x_pm_price_change,
    "polymarket__book": x_pm_book, "polymarket__last_trade_price": x_pm_last_trade,
    **{s: x_meta(s) for s in META},
}
AGGREGATORS = {
    "binance_fut__btcusdt@bookTicker": a_book_ticker, "binance_spot__btcusdt@bookTicker": a_book_ticker,
    "binance_fut__btcusdt@depth20@100ms": a_depth20,
    "binance_fut__btcusdt@trade": a_trade, "binance_spot__btcusdt@trade": a_trade,
    "chainlink__btc": a_chainlink, "polymarket__price_change": a_pm_price_change,
    "polymarket__book": a_pm_book, "polymarket__last_trade_price": a_pm_last_trade,
}


# ---------------------------------------------------------------- unit processing

def parse_unit(raw: bytes, stream: str):
    """Stream row groups, convert each to column arrays, drop the dicts."""
    pf = pq.ParquetFile(io.BytesIO(raw))
    wrapped = stream.startswith("binance_")
    extract = EXTRACTORS[stream]
    chunks, errs, n_in, cache = [], 0, 0, {}
    for i in range(pf.num_row_groups):
        t = pf.read_row_group(i, columns=["rt_ns", "data"])
        rt = t.column("rt_ns").to_numpy()
        rows, rts = [], []
        for j, s in enumerate(t.column("data").to_pylist()):
            try:
                d = orjson.loads(s)
                rows.append(d["data"] if wrapped else d)
                rts.append(rt[j])
            except Exception:
                errs += 1
        n_in += len(rows)
        if rows:
            chunks.append(extract(rows, np.asarray(rts, dtype=np.int64), cache))
        del rows, rts, t
    if not chunks:
        return {}, errs, n_in
    cols = {}
    for k in chunks[0]:
        parts = [c[k] for c in chunks]
        cols[k] = (np.concatenate(parts) if isinstance(parts[0], np.ndarray)
                   else [v for p in parts for v in p])
    return cols, errs, n_in


def process_unit(raw: bytes, stream: str, day: str, hour: int):
    t0 = time.time()
    cols, errs, n_in = parse_unit(raw, stream)
    res = {}
    man = {"stream": stream, "date": day, "hour": hour, "code_version": CODE_VERSION,
           "n_rows_in": n_in + errs, "n_parse_errors": errs,
           "time_source": "receive" if stream in RECEIVE_TIME else "event",
           "lag_measurable": stream not in RECEIVE_TIME}
    if not cols:
        man["empty"] = True
        return res, man
    if stream in META:
        res["meta"] = pd.DataFrame(cols)
    else:
        for freq, width in (("1s", 1000), ("1m", 60_000)):
            df = AGGREGATORS[stream](cols, width)
            df.insert(0, "bucket_start", pd.to_datetime(df.pop("bucket") * width, unit="ms", utc=True))
            df["time_source"] = man["time_source"]
            res[freq] = df
        if stream in EVENT_LEVEL:
            res["events"] = pd.DataFrame({"event_ms": cols["ts"], "trade_id": cols["trade_id"], "price": cols["px"],
                                          "qty": cols["qty"], "is_buyer_maker": cols["m"],
                                          "trade_type": cols["xtype"], "rt_ns": cols["rt_ns"]})
        for col in ("lag_ms_p50", "lag_ms_p95"):
            v = res["1s"][col].median() if col in res["1s"] else np.nan
            man[f"rt_{col}"] = None if pd.isna(v) else float(v)
    man.update({k: int(len(v)) for k, v in res.items()})
    man["seconds"] = round(time.time() - t0, 2)
    return res, man


# ---------------------------------------------------------------- GCS io

# GCS calls hang indefinitely without an explicit timeout (3 workers stalled in
# the pilot). Every call below gets a timeout plus retry.
GCS_TIMEOUT = 300


def _client():
    from google.cloud import storage
    return storage.Client()


try:
    from google.api_core.exceptions import NotFound
except ImportError:               # only needed on the GCS path
    NotFound = FileNotFoundError


def _retry():
    from google.cloud.storage.retry import DEFAULT_RETRY
    return DEFAULT_RETRY.with_deadline(900)


def _blob(client, path):
    return client.bucket(BUCKET).blob(path)


def out_path(kind, stream, day, hour):
    if kind == "manifest":
        return f"{OUT_PREFIX}/_manifest/{stream}/date={day}/{hour:02d}.json"
    return f"{OUT_PREFIX}/{kind}/{stream}/date={day}/{stream}__{hour:02d}.parquet"


def run_unit(args):
    stream, day, hour = args
    try:
        client = _client()
        src = _blob(client, f"{RAW_PREFIX}/{day}/{stream}__{hour:02d}.parquet")
        try:
            src.reload(timeout=60, retry=_retry())
        except NotFound:          # the collector did not write this hour at all
            return {"stream": stream, "date": day, "hour": hour, "missing": True}
        if src.size is None:
            return {"stream": stream, "date": day, "hour": hour, "missing": True}
        mblob = _blob(client, out_path("manifest", stream, day, hour))
        if mblob.exists(timeout=60, retry=_retry()):
            old = json.loads(mblob.download_as_bytes(timeout=GCS_TIMEOUT, retry=_retry()))
            if (old.get("code_version") == CODE_VERSION and old.get("input_generation") == src.generation
                    and old.get("input_size") == src.size):
                return {**old, "skipped": True}
        raw = src.download_as_bytes(checksum="crc32c", timeout=GCS_TIMEOUT, retry=_retry())   # integrity checked
        res, man = process_unit(raw, stream, day, hour)
        del raw
        man.update({"input_generation": src.generation, "input_size": src.size, "input_crc32c": src.crc32c})
        for kind, df in res.items():
            buf = io.BytesIO()
            pq.write_table(pa.Table.from_pandas(df, preserve_index=False), buf, compression="zstd")
            _blob(client, out_path(kind, stream, day, hour)).upload_from_string(
                buf.getvalue(), content_type="application/octet-stream",
                timeout=GCS_TIMEOUT, retry=_retry())
            man[f"{kind}_bytes"] = buf.tell()
        _blob(client, out_path("manifest", stream, day, hour)).upload_from_string(
            json.dumps(man), content_type="application/json", timeout=GCS_TIMEOUT, retry=_retry())
        return man
    except Exception:
        return {"stream": stream, "date": day, "hour": hour, "error": traceback.format_exc()[-1500:]}


def days(start, end):
    d0, d1 = Date.fromisoformat(start), Date.fromisoformat(end)
    while d0 <= d1:
        yield d0.isoformat()
        d0 += timedelta(days=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--streams", nargs="+", default=STREAMS)
    ap.add_argument("--hours", nargs="+", type=int, default=list(range(24)))
    # a price_change hour peaks ~2.3 GB and workers are never recycled, so cap
    # concurrency: 10 x 2.3 GB stays well inside 43 GB
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--local-dir"); ap.add_argument("--date"); ap.add_argument("--hour", type=int)
    a = ap.parse_args()

    if a.local_dir:
        for stream in a.streams:
            f = os.path.join(a.local_dir, f"{stream}__{a.hour:02d}.parquet")
            if not os.path.exists(f):
                print(f"skip {stream}: no local file"); continue
            res, man = process_unit(open(f, "rb").read(), stream, a.date, a.hour)
            print(json.dumps(man))
            for k, df in res.items():
                print(f"   {k}: {len(df):,} rows, cols {list(df.columns)[:8]}{'...' if len(df.columns) > 8 else ''}")
        return

    units = [(s, d, h) for d in days(a.start, a.end) for s in a.streams for h in a.hours]
    random.Random(0).shuffle(units)                 # spread the two heavy streams across workers
    print(f"{len(units)} units, {a.workers} workers, code {CODE_VERSION}", flush=True)
    t0 = time.time(); done = skipped = errors = missing = 0
    rows_out, bytes_out = {}, {}
    # NB: no max_tasks_per_child — recycling a worker mid-run deadlocked the pool
    # (parent in futex_wait, zero workers). Memory is bounded by --workers instead.
    with ProcessPoolExecutor(a.workers) as ex:
        futs = [ex.submit(run_unit, u) for u in units]
        for i, fu in enumerate(as_completed(futs), 1):
            m = fu.result()
            if m.get("error"):
                errors += 1
                print("ERROR", m["stream"], m["date"], m["hour"], m["error"][-400:], flush=True)
            elif m.get("missing"):
                missing += 1
            elif m.get("skipped"):
                skipped += 1
            else:
                done += 1
                for k in ("1s", "1m", "events", "meta"):
                    if k in m:
                        rows_out[k] = rows_out.get(k, 0) + m[k]
                        bytes_out[k] = bytes_out.get(k, 0) + m.get(f"{k}_bytes", 0)
            if i % 200 == 0 or i == len(units):
                el = time.time() - t0
                print(f"{i}/{len(units)} done={done} skip={skipped} miss={missing} err={errors} "
                      f"{el/60:.1f} min, ETA {el/i*(len(units)-i)/60:.1f} min, rows {rows_out}", flush=True)
    mb = json.dumps({k: round(v / 1e6, 1) for k, v in bytes_out.items()})
    print(f"FINISHED done={done} skipped={skipped} missing={missing} errors={errors} "
          f"in {(time.time()-t0)/60:.1f} min; rows {rows_out}; MB {mb}", flush=True)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
