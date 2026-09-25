"""p12 survey: message and byte rates of the public websocket streams, to size a collector.
Counts in memory over a short window and writes a summary json; nothing else is stored.
Also counts distinct addresses seen in the `trades` stream (users=[buyer, seller])."""
import argparse, json, threading, time
from collections import defaultdict
import websocket

ap = argparse.ArgumentParser()
ap.add_argument("--minutes", type=float, default=10)
ap.add_argument("--coins", default="BTC,ETH,SOL,HYPE,ZEC,XRP")
ap.add_argument("--out", default="ws_rates.json")
a = ap.parse_args()
coins = a.coins.split(",")
subs = [{"type": "allMids"}]
for c in coins:
    subs += [{"type": t, "coin": c} for t in ("trades", "l2Book", "bbo", "activeAssetCtx")]

msgs = defaultdict(int); byts = defaultdict(int); trades = defaultdict(int)
users = defaultdict(set); all_users = set(); first = {}
lock = threading.Lock()

def key(d):
    ch = d.get("channel")
    data = d.get("data")
    coin = None
    if isinstance(data, list) and data and isinstance(data[0], dict):
        coin = data[0].get("coin")
    elif isinstance(data, dict):
        coin = data.get("coin")
    return ch, coin

def on_message(ws, m):
    d = json.loads(m)
    ch, coin = key(d)
    if ch in (None, "subscriptionResponse", "pong"):
        return
    k = f"{ch}:{coin}" if coin else ch
    with lock:
        msgs[k] += 1; byts[k] += len(m)
        first.setdefault(k, m[:1500])
        if ch == "trades":
            for t in d["data"]:
                trades[coin] += 1
                for u in t["users"]:
                    users[coin].add(u); all_users.add(u)

def on_open(ws):
    for s in subs:
        ws.send(json.dumps({"method": "subscribe", "subscription": s}))

ws = websocket.WebSocketApp("wss://api.hyperliquid.xyz/ws", on_message=on_message, on_open=on_open)
th = threading.Thread(target=ws.run_forever, kwargs={"ping_interval": 30}, daemon=True); th.start()
time.sleep(10)  # skip the initial snapshots
with lock:
    msgs.clear(); byts.clear(); trades.clear(); users.clear(); all_users.clear()
t0 = time.time()
time.sleep(a.minutes * 60)
el = time.time() - t0
ws.close()
with lock:
    out = dict(seconds=el, coins=coins,
               per_stream={k: dict(msgs_per_s=msgs[k] / el, bytes_per_s=byts[k] / el) for k in sorted(msgs)},
               trades_per_s={c: trades[c] / el for c in trades},
               distinct_users={c: len(users[c]) for c in users}, distinct_users_all=len(all_users),
               examples=first)
json.dump(out, open(a.out, "w"), indent=1)
tot_b = sum(byts.values()) / el
print(f"{el:.0f}s total {sum(msgs.values())/el:.1f} msg/s {tot_b/1e3:.1f} kB/s = {tot_b*86400/1e9:.2f} GB/day raw JSON; users {len(all_users)}")
json.dump(sorted(all_users), open("addrs_ws_users.json", "w"))
