"""p12 survey: the measurements that were first taken ad hoc, as one reproducible script.
  universe   top 10 perps by 24h volume and by OI (metaAndAssetCtxs)
  sample     leaderboard row count; draws the tail sample (ranks > 3000, 1000 accounts, seed 12)
             and prepends HLP + its children -> addrs_tail_sample.json (input to coverage.py)
  overlap    share of addresses seen in the trades stream (addrs_ws_users.json, from ws_rates.py)
             that are on the leaderboard -> addrs_ws_not_lb.json (input to coverage.py)
  l2cadence  gap between websocket l2Book snapshots for BTC over 60 s
  tailci     bootstrap 95% interval of the scaled tail-sample coverage (offline)
Live numbers change run to run; SURVEY.md quotes the first run and dates it."""
import json, random, sys, threading, time
import numpy as np, requests

INFO = "https://api.hyperliquid.xyz/info"
LB = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
HLP = "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303"


def leaderboard():
    rows = requests.get(LB, timeout=60).json()["leaderboardRows"]
    rows.sort(key=lambda r: -float(r["accountValue"]))
    return rows


def universe():
    m, c = requests.post(INFO, json={"type": "metaAndAssetCtxs"}, timeout=30).json()
    rows = [(u["name"], float(x["dayNtlVlm"]), float(x["openInterest"]) * float(x["markPx"]), u["maxLeverage"])
            for u, x in zip(m["universe"], c) if not u.get("isDelisted")]
    tv, to = sum(r[1] for r in rows), sum(r[2] for r in rows)
    print(f"live perps {len(rows)}  24h vol ${tv/1e9:.2f}B  OI ${to/1e9:.2f}B")
    for k, name, tot in ((1, "vol", tv), (2, "OI", to)):
        print("top10 by", name)
        for r in sorted(rows, key=lambda r: -r[k])[:10]:
            print(f"  {r[0]:8s} vol ${r[1]/1e6:8.0f}M  OI ${r[2]/1e6:8.0f}M  maxLev {r[3]:2d}  share {r[k]/tot:.1%}")


def sample():
    rows = leaderboard()
    print("leaderboard rows", len(rows))
    tail = [r["ethAddress"] for r in rows[3000:]]
    random.seed(12)
    samp = random.sample(tail, 1000)
    kids = requests.post(INFO, json={"type": "vaultDetails", "vaultAddress": HLP}, timeout=30).json()
    hlp = [HLP] + kids["relationship"]["data"]["childAddresses"]
    json.dump(hlp + samp, open("addrs_tail_sample.json", "w"))
    print(f"tail {len(tail)} accounts, sampled 1000; {len(hlp)} HLP addresses first (not scaled)")


def overlap():
    lb = {r["ethAddress"].lower() for r in leaderboard()}
    ws = json.load(open("addrs_ws_users.json"))
    out = [u for u in ws if u.lower() not in lb]
    json.dump(out, open("addrs_ws_not_lb.json", "w"))
    print(f"trades-stream addresses {len(ws)}, on leaderboard {len(ws)-len(out)} ({1-len(out)/len(ws):.1%})")


def l2cadence(seconds=62):
    import websocket
    ts = []
    def on_message(ws, m):
        d = json.loads(m)
        if d.get("channel") == "l2Book": ts.append(d["data"]["time"])
    def on_open(ws):
        ws.send(json.dumps({"method": "subscribe", "subscription": {"type": "l2Book", "coin": "BTC"}}))
    ws = websocket.WebSocketApp("wss://api.hyperliquid.xyz/ws", on_message=on_message, on_open=on_open)
    threading.Thread(target=ws.run_forever, daemon=True).start(); time.sleep(seconds); ws.close()
    g = np.diff(ts) / 1000
    print(f"l2Book BTC: {len(ts)} snapshots; gap s median {np.median(g):.2f} p10 {np.percentile(g,10):.2f} p90 {np.percentile(g,90):.2f}")


def tailci(n_tail=43797, n_hlp=8):
    t = json.load(open("coverage_tail_sample.json")); oi = t["oi"]
    samp = json.load(open("addrs_tail_sample.json"))[n_hlp:]
    rng = np.random.default_rng(0)
    for c in ("BTC", "ETH", "HYPE", "SOL"):
        per = dict.fromkeys(samp, 0.0)
        for p in t["positions"]:
            if p["coin"] == c and p["addr"] in per: per[p["addr"]] += abs(p["szi"])
        v = np.array(list(per.values())) / (2 * oi[c]) * n_tail / len(samp)
        bs = [rng.choice(v, len(v)).sum() for _ in range(5000)]
        print(f"{c} tail coverage {v.sum():.1%}  bootstrap 95% {np.percentile(bs,2.5):.1%}-{np.percentile(bs,97.5):.1%}  (HLP excluded from scaling)")


if __name__ == "__main__":
    for step in sys.argv[1:] or ["universe", "l2cadence", "tailci"]:
        print(f"--- {step}"); globals()[step]()
