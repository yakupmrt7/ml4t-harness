"""p17: taker fee actually charged on-chain (FeeCharged event 0x55bb3cad.. of the v2 exchange) vs rate * p(1-p) * size,
for trades whose transaction holds exactly one FeeCharged event. Post-measurement diagnostic (reported, not a kill input).
  python research/p17_pm_maker_bound/onchain_fee_check.py
"""
import gzip, json, random, urllib.request
RPCS = ["https://polygon.drpc.org", "https://1rpc.io/matic", "https://polygon-bor-rpc.publicnode.com"]
V2 = "0xe111180000d2663c0091e4f400237545b87b996b"
FEE_TOPIC = "0x55bb3cad"


def rpc(m, p):
    for u in RPCS:
        try:
            b = json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode()
            r = json.loads(urllib.request.urlopen(urllib.request.Request(u, b, {"Content-Type": "application/json", "User-Agent": "p17"}), timeout=30).read())
            if r.get("result") is not None:
                return r["result"]
        except Exception:
            pass


random.seed(7)
picks = []
with gzip.open("data/collector/p17/trades.jsonl.gz", "rt") as f:
    for i, l in enumerate(f):
        if i % 97 == 0:
            r = json.loads(l)
            if r["trades"]:
                picks.append(random.choice(r["trades"]))
out = []
for t in picks[:24]:
    rc = rpc("eth_getTransactionReceipt", [t["transactionHash"]])
    if not rc:
        continue
    fees = [int(lg["data"][2:66], 16) / 1e6 for lg in rc["logs"]
            if lg["address"].lower() == V2 and lg["topics"][0].startswith(FEE_TOPIC)]
    if len(fees) != 1:
        continue
    p, sz = float(t["price"]), float(t["size"])
    implied = fees[0] / (p * (1 - p) * sz) if 0 < p < 1 else float("nan")
    out.append(implied)
    print(f"p {p:.3f} size {sz:9.2f} fee {fees[0]:.5f} implied rate {implied:.4f}")
out = sorted(x for x in out if x == x)
print("n", len(out), "median implied fee rate", out[len(out) // 2] if out else None)
