"""p15 step 0d: validate the HuggingFace on-chain fills against Polymarket's own data API.

Sample: 40 in-scope markets with >= 1 fill, seed 0, 10 per exchange contract (v1 CTF, v1 NegRisk,
v2 CTF, v2 NegRisk). The data API (takerOnly=true) returns one row per taker trade; our table has one
row per MAKER fill (a taker order that sweeps n makers is n rows), so counts are not 1:1 by
construction. Reconciliation instead: each API taker trade (timestamp, taker wallet, size) is matched
to our fills with the same second and taker address, summing token_amount. Per market we report the
share of API trades matched and the share-volume ratio over the API's time range.
Gate (PLAN amendment 1): >= 99% of API taker trades matched AND share volume within 1%, on >= 90% of
sampled markets. Counts and volumes only; prices are not compared or printed.

  local:  python research/p15_pm_deribit_threshold/validate_fills.py --sample        (writes val_markets.txt)
  VM:     nice -n 19 python3 validate_fills.py --fetch val_markets.txt val_api.jsonl
  local:  python research/p15_pm_deribit_threshold/validate_fills.py --compare data/collector/p15/val_api.jsonl
"""
import argparse
import json
import time
import urllib.request
from pathlib import Path

API = "https://data-api.polymarket.com/trades?market={cid}&limit=500&offset={off}&takerOnly=true"
HERE = Path(__file__).parent


def sample():
    import sys
    import pandas as pd
    sys.path.insert(0, str(HERE))
    from common import DIR, load_fills
    f = load_fills(dev_only=False, columns=["market_id", "contract"])
    per = f.groupby("market_id").contract.agg(lambda s: s.mode().iloc[0]).rename("contract").reset_index()
    g = pd.read_parquet(DIR / "gamma_markets.parquet")[["id", "conditionId"]].astype(str)
    per = per.merge(g, left_on="market_id", right_on="id")
    pick = per.groupby("contract").sample(n=10, random_state=0)
    (HERE / "val_markets.txt").write_text("\n".join(f"{r.market_id} {r.conditionId}" for r in pick.itertuples()) + "\n")
    print(pick.contract.value_counts().to_dict())


def fetch(path, out):
    rows = [l.split() for l in open(path) if l.strip()]
    with open(out, "w") as f:
        for mid, cid in rows:
            trades, off, truncated = [], 0, False
            while True:
                for attempt in range(6):
                    try:
                        req = urllib.request.Request(API.format(cid=cid, off=off), headers={"User-Agent": "p15-research/1.0"})
                        page = json.loads(urllib.request.urlopen(req, timeout=30).read())
                        break
                    except Exception as e:
                        page = None
                        err = repr(e)
                        time.sleep(2 ** attempt)
                if page is None:                          # API refuses deep offsets: keep what we have
                    truncated = True
                    break
                trades += [{k: t.get(k) for k in ("timestamp", "proxyWallet", "size", "side", "outcomeIndex",
                                                   "transactionHash")} for t in page]
                if len(page) < 500:
                    break
                off += 500
                time.sleep(0.5)
            f.write(json.dumps({"market_id": mid, "conditionId": cid, "n": len(trades), "truncated": truncated,
                                "trades": trades}) + "\n")
            f.flush()
            print(mid, len(trades), "truncated" if truncated else "", flush=True)
            time.sleep(0.5)


def compare(path):
    import sys
    import numpy as np
    import pandas as pd
    sys.path.insert(0, str(HERE))
    from common import load_fills
    recs = [json.loads(l) for l in open(path)]
    fills = load_fills([r["market_id"] for r in recs], dev_only=False,
                       columns=["timestamp", "block_number", "log_index", "contract", "market_id", "taker", "token_amount"])
    fills = fills.drop_duplicates(["block_number", "log_index", "contract"])
    fills["taker"] = fills.taker.str.lower()
    out = []
    for r in recs:
        api = pd.DataFrame(r["trades"])
        f = fills[fills.market_id == r["market_id"]]
        if api.empty:
            out.append({"market_id": r["market_id"], "api_n": 0, "ours_n": len(f)})
            continue
        api["proxyWallet"] = api.proxyWallet.str.lower()
        lo, hi = api.timestamp.min(), api.timestamp.max()
        fw = f[(f.timestamp >= lo) & (f.timestamp <= hi)]
        ours = fw.groupby(["timestamp", "taker"]).token_amount.sum()
        a = api.groupby(["timestamp", "proxyWallet"])["size"].sum()
        j = a.to_frame("api").join(ours.rename("ours"), how="left")
        matched = np.isclose(j.api, j.ours.fillna(0), rtol=1e-3, atol=0.02)
        out.append({"market_id": r["market_id"], "contract": f.contract.mode().iloc[0] if len(f) else None,
                    "api_n": int(r["n"]), "truncated": r["truncated"], "ours_rows_in_range": int(len(fw)),
                    "api_groups": int(len(j)), "matched_share": float(matched.mean()),
                    "vol_ratio": float(fw.token_amount.sum() / api["size"].sum())})
    res = pd.DataFrame(out)
    res["pass"] = (res.matched_share >= 0.99) & (res.vol_ratio.sub(1).abs() <= 0.01)
    print(res.to_string())
    s = {"n_markets": int(len(res)), "n_pass": int(res["pass"].sum()),
         "gate_pass": bool(res["pass"].mean() >= 0.9),
         "matched_share_median": float(res.matched_share.median()), "vol_ratio_median": float(res.vol_ratio.median())}
    print(json.dumps(s, indent=1))
    res.to_csv(HERE / "step0_validate_fills.csv", index=False)
    (HERE / "step0_validate_fills.json").write_text(json.dumps(s, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--fetch", nargs=2)
    ap.add_argument("--compare")
    a = ap.parse_args()
    if a.sample:
        sample()
    elif a.fetch:
        fetch(*a.fetch)
    else:
        compare(a.compare)
