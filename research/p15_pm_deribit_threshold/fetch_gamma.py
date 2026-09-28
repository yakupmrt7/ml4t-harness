"""p15 step 0a/0b: resolution rules and outcomes of the in-scope events from the public Gamma API.

Runs on poly-collector-eu (Polymarket is not reachable from the owner's machine), like p09.
Standard library only. Resumable: one JSON line per event slug; slugs already present are skipped.
~2 requests/s, backoff on 429/5xx. Only rule/resolution fields are kept: price-like fields
(lastTradePrice, bestBid, bestAsk, spread, oneDayPriceChange, ...) are dropped on the VM.

  local:  python research/p15_pm_deribit_threshold/fetch_gamma.py --make-slugs   (writes event_slugs.txt)
  VM:     nice -n 19 python3 fetch_gamma.py --slugs event_slugs.txt --out gamma_events.jsonl
  local:  python research/p15_pm_deribit_threshold/fetch_gamma.py --to-parquet gamma_events.jsonl
"""
import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

GAMMA = "https://gamma-api.polymarket.com/events?slug="
EVENT_KEEP = ["id", "slug", "title", "description", "resolutionSource", "startDate", "endDate", "closed",
              "negRisk", "createdAt"]
MARKET_KEEP = ["id", "slug", "question", "description", "resolutionSource", "conditionId", "clobTokenIds",
               "outcomes", "outcomePrices", "closed", "umaResolutionStatus", "umaResolutionStatuses",
               "automaticallyResolved", "closedTime", "endDate", "startDate", "createdAt", "negRisk"]
DIR = Path("data/collector/p15")


def make_slugs():
    import pandas as pd
    inv = pd.read_parquet(DIR / "inventory.parquet")
    inv = inv[inv.family.isin(["strike", "range"])]
    slugs = sorted(inv.event_slug.dropna().unique())
    Path("research/p15_pm_deribit_threshold/event_slugs.txt").write_text("\n".join(slugs) + "\n")
    print(f"{len(slugs)} event slugs ({len(inv)} markets); {inv.event_slug.isna().sum()} markets without event slug")


def fetch(slugs_path, out_path, rate=2.0):
    import shutil
    assert shutil.disk_usage(".").free > 1e9, "less than 1 GB free: refusing to run"
    slugs = [s.strip() for s in open(slugs_path) if s.strip()]
    done = set()
    if Path(out_path).exists():
        done = {json.loads(l)["slug"] for l in open(out_path) if l.strip()}
    todo = [s for s in slugs if s not in done]
    print(f"{len(slugs)} slugs, {len(done)} done, {len(todo)} to fetch", flush=True)
    with open(out_path, "a") as f:
        for i, s in enumerate(todo):
            rec = {"slug": s, "http": -1, "event": None}
            for attempt in range(6):
                try:
                    req = urllib.request.Request(GAMMA + s, headers={"User-Agent": "p15-research/1.0"})
                    body = json.loads(urllib.request.urlopen(req, timeout=30).read())
                    ev = body[0] if body else None
                    if ev is not None:
                        ev = {**{k: ev.get(k) for k in EVENT_KEEP},
                              "markets": [{k: m.get(k) for k in MARKET_KEEP} for m in ev.get("markets", [])]}
                    rec = {"slug": s, "http": 200, "n": len(body), "event": ev}
                    break
                except urllib.error.HTTPError as e:
                    if e.code in (429, 500, 502, 503, 504):
                        time.sleep(2 ** attempt)
                        continue
                    rec = {"slug": s, "http": e.code, "event": None}
                    break
                except Exception as e:                     # network hiccup: back off and retry
                    rec = {"slug": s, "http": -1, "event": None, "error": type(e).__name__}
                    time.sleep(2 ** attempt)
            f.write(json.dumps(rec) + "\n")
            f.flush()
            if i % 100 == 0:
                print(f"{i}/{len(todo)}", flush=True)
            time.sleep(1 / rate)


def to_parquet(jsonl):
    import pandas as pd
    rows, ev_rows = [], []
    for line in open(jsonl):
        r = json.loads(line)
        ev = r["event"]
        if not ev:
            ev_rows.append({"event_slug": r["slug"], "http": r["http"], "found": False})
            continue
        ev_rows.append({"event_slug": r["slug"], "http": r["http"], "found": True,
                        **{f"ev_{k}": ev.get(k) for k in EVENT_KEEP}})
        for m in ev["markets"]:
            rows.append({"event_slug": r["slug"], "ev_description": ev.get("description"),
                         **{k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in m.items()}})
    pd.DataFrame(rows).to_parquet(DIR / "gamma_markets.parquet")
    pd.DataFrame(ev_rows).to_parquet(DIR / "gamma_events.parquet")
    print(f"{len(ev_rows)} events ({sum(e['found'] for e in ev_rows)} found), {len(rows)} markets")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--make-slugs", action="store_true")
    ap.add_argument("--slugs")
    ap.add_argument("--out")
    ap.add_argument("--to-parquet")
    a = ap.parse_args()
    if a.make_slugs:
        make_slugs()
    elif a.to_parquet:
        to_parquet(a.to_parquet)
    else:
        fetch(a.slugs, a.out)
