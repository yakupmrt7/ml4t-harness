"""p13 loader validation against the live API (ROADMAP §8.6). Read-only, a few dozen calls.
  (a) liquidations: for liquidated users in the archive's last days, userFillsByTime from the API
      must contain the same liquidation fills (tid, px, sz, side, method).
  (b) trade tape: 1-minute close/volume from our ticks vs candleSnapshot 1m for BTC, last ~3 days.
"""
import json, pathlib, sys, time
import numpy as np, pandas as pd, requests

HERE = pathlib.Path(__file__).parent
SRC = HERE.parents[1] / "data/hl/p13_fills"
INFO = "https://api.hyperliquid.xyz/info"
post = lambda b: requests.post(INFO, json=b, timeout=30).json()


def liq_check(days=("20260923", "20260924"), n_users=25, seed=0):
    liq = pd.concat([pd.read_parquet(SRC / "liq" / f"{d}.parquet") for d in days])
    ev = liq[(liq.user == liq.liq_user) & (liq.liq_method == "market")]
    users = ev.liq_user.drop_duplicates().sample(n_users, random_state=seed)
    ok = miss = mism = 0; notes = []
    for u in users:
        mine = ev[ev.liq_user == u]
        t0, t1 = int(mine.time.min()) - 1, int(mine.time.max()) + 1
        api = post({"type": "userFillsByTime", "user": u, "startTime": t0, "endTime": t1})
        api = {f["tid"]: f for f in api if "liquidation" in f}
        for _, r in mine.iterrows():
            f = api.get(r.tid)
            if f is None:
                miss += 1; notes.append(f"missing {u[:10]} tid {r.tid}"); continue
            same = (float(f["px"]) == r.px and float(f["sz"]) == r.sz and f["side"] == r.side
                    and f["liquidation"]["method"] == r.liq_method and f["coin"] == r.coin and f["time"] == r.time)
            ok += same; mism += (not same)
            if not same: notes.append(f"mismatch {u[:10]} tid {r.tid}")
        time.sleep(1.5)                       # userFillsByTime is weight 20+
    return dict(users=n_users, rows_matched=ok, rows_missing=miss, rows_mismatched=mism, notes=notes[:10])


def tape_check(coin="BTC", days=("20260922", "20260923", "20260924")):
    t = pd.concat([pd.read_parquet(SRC / "ticks" / f"{d}.parquet") for d in days])
    t = t[t.coin == coin].sort_values(["time", "tid"])
    t["m"] = t.time // 60000 * 60000
    mine = t.groupby("m").agg(c=("px", "last"), v=("sz", "sum"), n=("tid", "size"))
    start, end = int(mine.index.min()), int(mine.index.max()) + 60000
    rows = []
    while start < end:                              # 5000 candles max per call
        c = post({"type": "candleSnapshot", "req": {"coin": coin, "interval": "1m", "startTime": start,
                                                    "endTime": min(end, start + 4000 * 60000)}})
        rows += c; start += 4000 * 60000; time.sleep(1)
    api = pd.DataFrame(rows).drop_duplicates("t").set_index("t")[["c", "v", "n"]].astype(float)
    j = mine.join(api, rsuffix="_api", how="inner")
    return dict(coin=coin, minutes=len(j), close_equal=float((j.c == j.c_api).mean()),
                vol_rel_err_median=float(((j.v - j.v_api).abs() / j.v_api).median()),
                n_equal=float((j.n == j.n_api).mean()), api_minutes=len(api), our_minutes=len(mine))


if __name__ == "__main__":
    what = sys.argv[1:] or ["liq", "tape"]
    out = {}
    if "liq" in what: out["liq"] = liq_check()
    if "tape" in what: out["tape"] = tape_check()
    print(json.dumps(out, indent=1))
    json.dump(out, open(HERE / f"validate_{'_'.join(what)}.json", "w"), indent=1)
