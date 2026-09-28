"""p15 step 0d (PLAN amendment 1): taker trades of every in-scope market from Polymarket's data API.

Replaces the HuggingFace fill table, which failed 0d (timestamps off by +94..+102 s or by 5-6 h in
some block ranges vs Polygon block times; part of the v2-exchange fills missing). The data API's
timestamps equal the block timestamps (18/18 checked by transaction hash) and its share volume
equals Polymarket's own per-market volume counter.

API limits: newest first, offset <= 10,000 (so <= 10,500 rows per query). A market that hits the
cap is re-fetched per side (side=BUY and side=SELL, each <= 10,500); if a side still hits the cap,
the market is flagged `truncated` (its OLDEST trades are missing) and Steps 1-2 report it.

Runs on poly-collector-eu (Polymarket is not reachable from the owner's machine). Standard library.
Resumable (one gzip-JSON line per market; done markets are skipped). ~3 req/s with backoff.

  local:  python research/p15_pm_deribit_threshold/fetch_trades.py --make-list      (trade_markets.txt)
  VM:     nice -n 19 python3 fetch_trades.py --fetch trade_markets.txt trades.jsonl.gz
  local:  python research/p15_pm_deribit_threshold/fetch_trades.py --to-parquet data/collector/p15/trades.jsonl.gz
"""
import argparse
import gzip
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://data-api.polymarket.com/trades?market={cid}&limit=500&offset={off}&takerOnly=true{side}"
KEEP = ("timestamp", "side", "outcomeIndex", "size", "price", "proxyWallet", "transactionHash")
CAP = 10_500
HERE = Path(__file__).parent


def make_list():
    import sys
    import pandas as pd
    sys.path.insert(0, str(HERE))
    from common import DIR
    r = pd.read_parquet(DIR / "rules.parquet")
    g = pd.read_parquet(DIR / "gamma_markets.parquet")[["id", "conditionId"]].astype(str)
    r = r[r.T_utc.notna()].merge(g, on="id")
    (HERE / "trade_markets.txt").write_text("\n".join(f"{a} {b}" for a, b in zip(r.id, r.conditionId)) + "\n")
    print(f"{len(r)} markets")


def get(url):
    for attempt in range(7):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "p15-research/1.0"})
            return json.loads(urllib.request.urlopen(req, timeout=30).read())
        except urllib.error.HTTPError as e:
            if e.code == 400:                     # offset cap
                return None
            time.sleep(2 ** attempt)
        except Exception:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"failed: {url}")


def pull(cid, side=""):
    rows, off = [], 0
    while off <= 10_000:
        page = get(API.format(cid=cid, off=off, side=side))
        if not page:
            break
        rows += [{k: t.get(k) for k in KEEP} for t in page]
        if len(page) < 500:
            break
        off += 500
        time.sleep(1 / 3)
    return rows


def fetch(path, out):
    todo = [l.split() for l in open(path) if l.strip()]
    done = set()
    if Path(out).exists():
        with gzip.open(out, "rt") as f:
            done = {json.loads(l)["market_id"] for l in f if l.strip()}
    todo = [t for t in todo if t[0] not in done]
    print(f"{len(done)} done, {len(todo)} to fetch", flush=True)
    with gzip.open(out, "at") as f:
        for i, (mid, cid) in enumerate(todo):
            rows, mode, truncated = pull(cid), "all", False
            if len(rows) >= CAP:
                buy, sell = pull(cid, "&side=BUY"), pull(cid, "&side=SELL")
                rows, mode = buy + sell, "by_side"
                truncated = len(buy) >= CAP or len(sell) >= CAP
            f.write(json.dumps({"market_id": mid, "conditionId": cid, "n": len(rows), "mode": mode,
                                "truncated": truncated, "trades": rows}) + "\n")
            f.flush()
            if i % 200 == 0:
                print(f"{i}/{len(todo)} {time.strftime('%H:%M:%S')}", flush=True)
            time.sleep(1 / 3)
    print("done", flush=True)


def to_parquet(path):
    import sys
    import pandas as pd
    sys.path.insert(0, str(HERE))
    from common import DIR
    frames, meta = [], []
    with gzip.open(path, "rt") as f:
        for l in f:
            r = json.loads(l)
            meta.append({k: r[k] for k in ("market_id", "conditionId", "n", "mode", "truncated")})
            if r["trades"]:
                d = pd.DataFrame(r["trades"])
                d["market_id"] = r["market_id"]
                frames.append(d)
    t = pd.concat(frames, ignore_index=True)
    n0 = len(t)
    t = t.drop_duplicates(["transactionHash", "proxyWallet", "outcomeIndex", "side", "size", "price", "timestamp"])
    t = t.astype({"timestamp": "int64", "size": "float64", "price": "float64", "outcomeIndex": "int8"})
    t.to_parquet(DIR / "trades.parquet")
    m = pd.DataFrame(meta)
    m.to_parquet(DIR / "trades_meta.parquet")
    print(f"{len(m)} markets, {len(t)} trades ({n0 - len(t)} exact duplicates dropped), "
          f"modes {m['mode'].value_counts().to_dict()}, truncated {int(m.truncated.sum())}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--make-list", action="store_true")
    ap.add_argument("--fetch", nargs=2)
    ap.add_argument("--to-parquet")
    a = ap.parse_args()
    if a.make_list:
        make_list()
    elif a.fetch:
        fetch(*a.fetch)
    else:
        to_parquet(a.to_parquet)
