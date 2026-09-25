"""p12 survey: summarise coverage_positions.json (and optional extra samples) into
coverage of OI and the liquidation-price distribution around mark."""
import json, sys
from collections import defaultdict
import numpy as np

files = sys.argv[1:] or ["coverage_positions.json"]
for f in files:
    d = json.load(open(f))
    pos, oi, mark = d["positions"], d["oi"], d["mark"]
    print(f"\n== {f}: polled {d['polled']} accounts in {d['seconds']/60:.1f} min, {len(pos)} positions")
    by = defaultdict(list)
    for p in pos: by[p["coin"]].append(p)
    print(f"{'coin':6s} {'OI$M':>8s} {'long%OI':>8s} {'short%OI':>8s} {'liqPx%':>7s} {'n':>5s} "
          f"{'liq<=2%':>8s} {'liq<=5%':>8s} {'liq<=10%':>8s} {'top10%':>7s} {'cross%':>7s}")
    for c in ["BTC", "ETH", "HYPE", "SOL", "ZEC", "XRP"]:
        ps = by.get(c, []); m = mark[c]; o = oi[c]
        lg = sum(p["szi"] for p in ps if p["szi"] > 0); sh = -sum(p["szi"] for p in ps if p["szi"] < 0)
        ntl = np.array([abs(p["szi"]) * m for p in ps])
        has = [p for p in ps if p["liqPx"] is not None]
        liq_ntl = lambda k: sum(abs(p["szi"]) * m for p in has if abs(p["liqPx"] / m - 1) <= k) / (o * m)
        top10 = np.sort(ntl)[::-1][:10].sum() / ntl.sum() if len(ntl) else np.nan
        cross = sum(abs(p["szi"]) for p in ps if p["levType"] == "cross") / max(lg + sh, 1e-12)
        print(f"{c:6s} {o*m/1e6:8.0f} {lg/o:8.1%} {sh/o:8.1%} "
              f"{sum(abs(p['szi']) for p in has)/max(lg+sh,1e-12):7.1%} {len(ps):5d} "
              f"{liq_ntl(.02):8.2%} {liq_ntl(.05):8.2%} {liq_ntl(.10):8.2%} {top10:7.1%} {cross:7.1%}")
    # coverage curve by leaderboard rank, BTC
    if "rank" in pos[0]:
        for c in ["BTC", "ETH"]:
            o = oi[c]; ps = by[c]
            cum = [(k, sum(abs(p["szi"]) for p in ps if p["rank"] < k) / (2 * o)) for k in (100, 300, 1000, 3000)]
            print(c, "gross coverage (|long|+|short|)/(2*OI) by top-k accounts:",
                  ", ".join(f"top{k}: {v:.1%}" for k, v in cum))
