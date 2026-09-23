"""p09: Polymarket resolutions from the public Gamma API, dev 5m slugs only (PLAN.md,
amendment 1). Runs on a throwaway GCE VM because Polymarket is not reachable from the
owner's machine. Standard library only. Resumable: one JSON line per slug in the output;
slugs already present are skipped. ~2 requests/s, backoff on 429/5xx.

  local:  python research/p09_polymarket_fairprice/fetch_resolutions.py --make-slugs   (writes slugs.txt, dev only)
  VM:     python3 fetch_resolutions.py --slugs slugs.txt --out gamma.jsonl
  local:  python research/p09_polymarket_fairprice/fetch_resolutions.py --to-parquet gamma.jsonl
"""
import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

GAMMA = "https://gamma-api.polymarket.com/markets?slug="
LAST_DEV_START = 1788652500          # 2026-09-05 23:55:00 UTC; any later window start is holdout
KEEP = ["id", "slug", "closed", "active", "archived", "outcomes", "outcomePrices", "umaResolutionStatus",
        "umaResolutionStatuses", "resolvedBy", "closedTime", "endDate", "startDate", "eventStartTime",
        "resolutionSource", "clobTokenIds", "automaticallyResolved"]


def slug_start(s):
    return int(s.rsplit("-", 1)[1])


def fetch(slugs_path, out_path, rate=2.0):
    import shutil
    assert shutil.disk_usage(".").free > 1e9, "less than 1 GB free: refusing to run"
    slugs = [s.strip() for s in open(slugs_path) if s.strip()]
    assert all(s.startswith("btc-updown-5m-") and slug_start(s) <= LAST_DEV_START for s in slugs), "non-dev slug"
    done = set()
    if Path(out_path).exists():
        done = {json.loads(l)["slug"] for l in open(out_path) if l.strip()}
    todo = [s for s in slugs if s not in done]
    print(f"{len(slugs)} slugs, {len(done)} done, {len(todo)} to fetch", flush=True)
    with open(out_path, "a") as f:
        for i, s in enumerate(todo):
            for attempt in range(6):
                try:
                    # /markets hides closed markets unless closed=true; fall back to the plain query
                    for query in (GAMMA + s + "&closed=true", GAMMA + s):
                        req = urllib.request.Request(query, headers={"User-Agent": "p09-research/1.0"})
                        body = json.loads(urllib.request.urlopen(req, timeout=30).read())
                        if body:
                            break
                    rec = {"slug": s, "http": 200, "n": len(body), "query": "closed=true" if "closed=true" in query else "plain",
                           "market": {k: body[0].get(k) for k in KEEP} if body else None}
                    break
                except urllib.error.HTTPError as e:
                    if e.code in (429, 500, 502, 503, 504):
                        time.sleep(2 ** attempt)
                        continue
                    rec = {"slug": s, "http": e.code, "n": 0, "market": None}
                    break
                except Exception as e:                     # network hiccup: back off and retry
                    time.sleep(2 ** attempt)
                    rec = {"slug": s, "http": -1, "n": 0, "market": None, "error": type(e).__name__}
            f.write(json.dumps(rec) + "\n")
            f.flush()
            if i % 500 == 0:
                print(i, s, rec["http"], flush=True)
            time.sleep(1 / rate)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--make-slugs", action="store_true")
    ap.add_argument("--slugs")
    ap.add_argument("--out")
    ap.add_argument("--to-parquet")
    a = ap.parse_args()
    if a.make_slugs:
        import glob
        import pandas as pd
        d = pd.concat(pd.read_parquet(f, columns=["slug"]) for f in
                      sorted(glob.glob("data/collector/p09/meta/polymarket__markets/date=*/*.parquet")))
        s = sorted({x for x in d["slug"] if x.startswith("btc-updown-5m-") and slug_start(x) <= LAST_DEV_START})
        Path("data/collector/p09/slugs_dev_5m.txt").write_text("\n".join(s) + "\n")
        print(len(s), "dev 5m slugs; first", s[0], "last", s[-1])
    elif a.to_parquet:
        import pandas as pd
        rows = [json.loads(l) for l in open(a.to_parquet) if l.strip()]
        out = pd.DataFrame([{"slug": r["slug"], "http": r["http"], "n": r["n"],
                             **{k: (json.dumps(v) if isinstance(v, (list, dict)) else v)
                                for k, v in (r["market"] or {}).items()}} for r in rows])
        assert out["slug"].map(slug_start).max() <= LAST_DEV_START
        out.to_parquet("data/collector/p09/resolutions.parquet")
        print(out.shape, out["http"].value_counts().to_dict())
    else:
        fetch(a.slugs, a.out)
