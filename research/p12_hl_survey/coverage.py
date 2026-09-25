"""p12 survey: how much open interest do the leaderboard's largest accounts hold, and do
their positions carry a liquidation price? Read-only, throttled under the public limit
(clearinghouseState weight 2, 1200 weight/min/IP -> we use ~480 req/min). Writes one
summary json; no market data is recorded."""
import argparse, json, time, requests
from collections import defaultdict

INFO = "https://api.hyperliquid.xyz/info"
LB = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"

ap = argparse.ArgumentParser()
ap.add_argument("--top", type=int, default=3000)
ap.add_argument("--rps", type=float, default=8.0)
ap.add_argument("--out", default="coverage_positions.json")
ap.add_argument("--addrs", help="json list of addresses to poll instead of the leaderboard top")
a = ap.parse_args()

s = requests.Session()
rows = s.get(LB, timeout=60).json()["leaderboardRows"]
rows.sort(key=lambda r: -float(r["accountValue"]))
addrs = json.load(open(a.addrs))[: a.top] if a.addrs else [r["ethAddress"] for r in rows[: a.top]]

meta, ctxs = s.post(INFO, json={"type": "metaAndAssetCtxs"}, timeout=30).json()
oi = {u["name"]: float(c["openInterest"]) for u, c in zip(meta["universe"], ctxs)}
mark = {u["name"]: float(c["markPx"]) for u, c in zip(meta["universe"], ctxs)}

positions = []  # (rank, addr, coin, szi, entryPx, liqPx, lev_type, lev, marginUsed)
t0 = time.time(); errs = 0
for i, ad in enumerate(addrs):
    while time.time() - t0 < i / a.rps:
        time.sleep(0.01)
    try:
        st = s.post(INFO, json={"type": "clearinghouseState", "user": ad}, timeout=30).json()
    except Exception:
        errs += 1; continue
    for ap_ in st.get("assetPositions", []):
        p = ap_["position"]
        positions.append(dict(rank=i, addr=ad, coin=p["coin"], szi=float(p["szi"]),
                              entryPx=float(p["entryPx"]), liqPx=None if p["liquidationPx"] is None else float(p["liquidationPx"]),
                              levType=p["leverage"]["type"], lev=p["leverage"]["value"],
                              marginUsed=float(p["marginUsed"])))
    if i % 500 == 0:
        print(i, len(positions), f"{time.time()-t0:.0f}s", flush=True)

json.dump(dict(polled=len(addrs), errors=errs, seconds=time.time() - t0, time=int(t0 * 1000),
               oi=oi, mark=mark, positions=positions), open(a.out, "w"))
print("done", len(positions), "errors", errs)
