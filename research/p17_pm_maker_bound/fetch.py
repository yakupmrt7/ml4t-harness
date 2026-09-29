"""p17 fetch (throwaway VM only; Polymarket is blocked from the owner's machine and the collector VMs are
off-limits for research jobs). Standard library only; bounded memory (results streamed to disk).

  VM:  python3 fetch.py gamma gamma.jsonl          # 2,304 slugs btc-updown-5m-<start>, 2026-09-21..28 UTC
       python3 fetch.py trades gamma.jsonl trades.jsonl.gz
"""
import gzip
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

START = 1789948800            # 2026-09-21 00:00:00 UTC
END = 1790639700              # 2026-09-28 23:55:00 UTC (last window start)
GAMMA = "https://gamma-api.polymarket.com/markets?slug={slug}"
TRADES = "https://data-api.polymarket.com/trades?market={cid}&limit=500&offset={off}&takerOnly=true{side}"
KEEP_M = ["id", "slug", "question", "conditionId", "clobTokenIds", "outcomes", "outcomePrices", "closed",
          "umaResolutionStatus", "startDate", "endDate", "eventStartTime", "volume", "volumeNum", "feesEnabled",
          "makerBaseFee", "takerBaseFee", "feeType", "resolutionSource"]
KEEP_T = ("timestamp", "side", "outcomeIndex", "size", "price", "proxyWallet", "transactionHash")
CAP = 10_500


def get(url):
    for attempt in range(7):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "p17-research/1.0"})
            return json.loads(urllib.request.urlopen(req, timeout=30).read())
        except urllib.error.HTTPError as e:
            if e.code == 400:
                return None
            time.sleep(2 ** attempt)
        except Exception:
            time.sleep(2 ** attempt)
    raise RuntimeError(url)


def gamma(out):
    assert (END - START) % 300 == 0
    slugs = [f"btc-updown-5m-{t}" for t in range(START, END + 1, 300)]
    done = set()
    if Path(out).exists():
        done = {json.loads(l)["slug"] for l in open(out) if l.strip()}
    with open(out, "a") as f:
        for i, s in enumerate(slugs):
            if s in done:
                continue
            body = get(GAMMA.format(slug=s) + "&closed=true") or get(GAMMA.format(slug=s)) or []
            m = body[0] if body else None
            f.write(json.dumps({"slug": s, "market": {k: m.get(k) for k in KEEP_M} if m else None}) + "\n")
            f.flush()
            if i % 200 == 0:
                print("gamma", i, len(slugs), time.strftime("%H:%M:%S"), flush=True)
            time.sleep(0.3)
    print("gamma done", flush=True)


def pull(cid, side=""):
    rows, off = [], 0
    while off <= 10_000:
        page = get(TRADES.format(cid=cid, off=off, side=side))
        if not page:
            break
        rows += [{k: t.get(k) for k in KEEP_T} for t in page]
        if len(page) < 500:
            break
        off += 500
        time.sleep(1 / 3)
    return rows


def one(slug, cid):
    rows, mode, trunc = pull(cid), "all", False
    if len(rows) >= CAP:
        b, s = pull(cid, "&side=BUY"), pull(cid, "&side=SELL")
        rows, mode, trunc = b + s, "by_side", len(b) >= CAP or len(s) >= CAP
    return {"slug": slug, "conditionId": cid, "n": len(rows), "mode": mode, "truncated": trunc, "trades": rows}


def trades(gpath, out, workers=6):
    todo = []
    for l in open(gpath):
        r = json.loads(l)
        if r["market"] and r["market"].get("conditionId"):
            todo.append((r["slug"], r["market"]["conditionId"]))
    done = set()
    if Path(out).exists():
        with gzip.open(out, "rt") as f:
            for l in f:
                try:
                    done.add(json.loads(l)["slug"])
                except Exception:
                    break
    todo = [t for t in todo if t[0] not in done]
    print(f"{len(done)} done, {len(todo)} to fetch", flush=True)
    it, pending, i = iter(todo), set(), 0
    with gzip.open(out, "at") as f, ThreadPoolExecutor(workers) as ex:
        while True:
            while len(pending) < 2 * workers:
                nxt = next(it, None)
                if nxt is None:
                    break
                pending.add(ex.submit(one, *nxt))
            if not pending:
                break
            fin, pending = wait(pending, return_when=FIRST_COMPLETED)
            for fu in fin:
                f.write(json.dumps(fu.result()) + "\n")
                i += 1
                if i % 200 == 0:
                    f.flush()
                    print("trades", i, len(todo), time.strftime("%H:%M:%S"), flush=True)
    print("trades done", flush=True)


if __name__ == "__main__":
    {"gamma": lambda: gamma(sys.argv[2]), "trades": lambda: trades(sys.argv[2], sys.argv[3])}[sys.argv[1]]()
