"""p12 survey: do the top leaderboard accounts hold positions through sub-accounts that the
leaderboard does not list? subAccounts is weight 20 -> throttled to ~50 req/min."""
import json, time, requests
s = requests.Session(); INFO = "https://api.hyperliquid.xyz/info"
rows = s.get("https://stats-data.hyperliquid.xyz/Mainnet/leaderboard", timeout=60).json()["leaderboardRows"]
lb = set(r["ethAddress"].lower() for r in rows)
rows.sort(key=lambda r: -float(r["accountValue"]))
meta, ctxs = s.post(INFO, json={"type": "metaAndAssetCtxs"}).json()
oi = {u["name"]: float(c["openInterest"]) for u, c in zip(meta["universe"], ctxs)}
out = dict(masters=0, with_subs=0, subs=0, subs_in_lb=0, gross={}, oi=oi)
for r in rows[:150]:
    t = time.time()
    subs = s.post(INFO, json={"type": "subAccounts", "user": r["ethAddress"]}, timeout=30).json() or []
    out["masters"] += 1; out["with_subs"] += bool(subs); out["subs"] += len(subs)
    for sa in subs:
        out["subs_in_lb"] += sa["subAccountUser"].lower() in lb
        for ap in sa["clearinghouseState"]["assetPositions"]:
            c = ap["position"]["coin"]; out["gross"][c] = out["gross"].get(c, 0) + abs(float(ap["position"]["szi"]))
    time.sleep(max(0, 1.3 - (time.time() - t)))
json.dump(out, open("subaccounts.json", "w"), indent=1)
print({k: v for k, v in out.items() if k not in ("gross", "oi")})
for c in ["BTC", "ETH", "HYPE", "SOL"]:
    print(c, f"sub-account gross / (2*OI) = {out['gross'].get(c,0)/(2*oi[c]):.1%}")
