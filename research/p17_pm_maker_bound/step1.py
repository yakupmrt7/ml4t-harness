"""p17 (PLAN.md): upper bound on maker P&L in Polymarket 5-minute BTC up/down markets, 2026-09-21..28 UTC.

  python research/p17_pm_maker_bound/step1.py validate   # volume gate + collector cross-check (no P&L)
  python research/p17_pm_maker_bound/step1.py measure    # the bound and KILL
"""
import glob
import gzip
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
DIR = Path("data/collector/p17")
REBATE_SHARE = 0.20


def markets():
    rows = []
    for l in open(DIR / "gamma.jsonl"):
        r = json.loads(l)
        m = r["market"]
        if not m:
            rows.append({"slug": r["slug"], "found": False})
            continue
        outs = json.loads(m["outcomes"]) if m.get("outcomes") else None
        prices = json.loads(m["outcomePrices"]) if m.get("outcomePrices") else None
        up = np.nan
        if outs and prices and sorted(float(p) for p in prices) == [0.0, 1.0]:
            up = float(float(prices[outs.index("Up")]) == 1.0) if "Up" in outs else np.nan
        rows.append({"slug": r["slug"], "found": True, "conditionId": m.get("conditionId"), "outcome0": outs[0] if outs else None,
                     "up": up, "closed": m.get("closed"), "uma": m.get("umaResolutionStatus"),
                     "volume": float(m.get("volumeNum") or m.get("volume") or 0), "feesEnabled": m.get("feesEnabled"),
                     "takerBaseFee": m.get("takerBaseFee"), "makerBaseFee": m.get("makerBaseFee"), "feeType": m.get("feeType"),
                     "start": pd.Timestamp(int(r["slug"].rsplit("-", 1)[1]), unit="s", tz="UTC")})
    return pd.DataFrame(rows)


def trades():
    frames, meta = [], []
    with gzip.open(DIR / "trades.jsonl.gz", "rt") as f:
        for l in f:
            r = json.loads(l)
            meta.append({k: r[k] for k in ("slug", "n", "mode", "truncated")})
            if r["trades"]:
                d = pd.DataFrame(r["trades"])
                d["slug"] = r["slug"]
                frames.append(d)
    t = pd.concat(frames, ignore_index=True).drop_duplicates(
        ["transactionHash", "proxyWallet", "outcomeIndex", "side", "size", "price", "timestamp"])
    t = t.astype({"timestamp": "int64", "size": float, "price": float, "outcomeIndex": int})
    t["time"] = pd.to_datetime(t.timestamp, unit="s", utc=True)
    t["p_up"] = np.where(t.outcomeIndex == 0, t.price, 1 - t.price)
    t["taker_buys_up"] = ((t.side == "BUY") & (t.outcomeIndex == 0)) | ((t.side == "SELL") & (t.outcomeIndex == 1))
    return t, pd.DataFrame(meta)


def cmd_validate():
    m = markets()
    t, meta = trades()
    print(f"slugs {len(m)}, found {int(m.found.sum())}, resolved 1-0 {int(m.up.notna().sum())}, "
          f"outcome0 values {m.outcome0.value_counts(dropna=False).to_dict()}")
    print("fee fields:", {c: m[c].astype(str).value_counts().head(5).to_dict() for c in
                          ("feesEnabled", "takerBaseFee", "makerBaseFee", "feeType")})
    print("fetch modes:", meta["mode"].value_counts().to_dict(), "truncated", int(meta.truncated.sum()))
    v = t.groupby("slug")["size"].sum()
    x = m.set_index("slug").join(v.rename("api"))
    x["api"] = x.api.fillna(0)
    ok = ((x.api / x.volume.replace(0, np.nan) - 1).abs() <= 0.01) | ((x.api == 0) & (x.volume == 0))
    share = float(ok[x.found].mean())
    print(f"volume gate: {share:.4%} of markets within 1% of Gamma volume (bar 95%); "
          f"ratio quantiles {(x.api / x.volume.replace(0, np.nan)).quantile([.01, .05, .5, .95, .99]).round(4).to_dict()}")
    # collector cross-check on the hours it has (09-21..09-25): share volume per market
    col = []
    for f in sorted(glob.glob(str(DIR / "ltp/*/*.parquet"))):
        for s in pd.read_parquet(f, columns=["data"]).data:
            try:
                j = json.loads(s)
            except Exception:
                continue
            for r in (j if isinstance(j, list) else [j]):
                if r.get("event_type") == "last_trade_price":
                    col.append((r["market"], float(r["size"]), int(r["timestamp"]) // 1000))
    c = pd.DataFrame(col, columns=["conditionId", "size", "ts"])
    cid = m.set_index("conditionId").slug
    c = c[c.conditionId.isin(cid.index)]
    c["slug"] = c.conditionId.map(cid)
    cv = c.groupby("slug")["size"].sum()
    j = pd.concat([cv.rename("collector"), v.rename("api")], axis=1, join="inner")
    j["ratio"] = j.collector / j.api
    print(f"collector vs API share volume on {len(j)} markets: ratio quantiles "
          f"{j.ratio.quantile([.05, .25, .5, .75, .95]).round(4).to_dict()}")
    res = {"slugs": int(len(m)), "found": int(m.found.sum()), "resolved": int(m.up.notna().sum()),
           "volume_gate_share": share, "volume_gate_pass": share >= 0.95, "truncated": int(meta.truncated.sum()),
           "collector_markets": int(len(j)), "collector_over_api_median": float(j.ratio.median()),
           "fee_fields": {c: m[c].astype(str).value_counts().head(5).to_dict() for c in
                          ("feesEnabled", "takerBaseFee", "makerBaseFee", "feeType")}}
    (HERE / "validate.json").write_text(json.dumps(res, indent=1, default=str))


def cluster_t(x):
    x = pd.Series(x).dropna()
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))) if len(x) > 2 else np.nan


def cmd_measure(fee_rate_per_market=None, out="measure.json", log_selection=True):
    m = markets()
    m = m[m.found & m.up.notna()].set_index("slug")
    t, meta = trades()
    t = t[t.slug.isin(m.index)].join(m[["up", "start"]], on="slug")
    fee_rate = 0.0 if fee_rate_per_market is None else fee_rate_per_market
    t["maker_pnl"] = np.where(t.taker_buys_up, t.p_up - t.up, t.up - t.p_up) * t["size"]
    t["rebate"] = REBATE_SHARE * fee_rate * t.p_up * (1 - t.p_up) * t["size"]
    t["pnl"] = t.maker_pnl + t.rebate
    t["to_end_s"] = (t.start + pd.Timedelta(seconds=300) - t.time).dt.total_seconds()
    t["bucket"] = pd.cut(t.to_end_s, [-np.inf, 0, 60, 180, 300, np.inf],
                         labels=["after end", "last 60 s", "60-180 s", "180-300 s", "before window"])
    per = t.groupby("slug").agg(pnl=("pnl", "sum"), maker=("maker_pnl", "sum"), shares=("size", "sum"),
                                trades=("size", "size"))
    per["per_share"] = per.pnl / per.shares
    per["per_share_norebate"] = per.maker / per.shares
    res = {"markets": int(len(per)), "trades": int(len(t)), "shares": float(t["size"].sum()),
           "fee_rate_used": fee_rate, "rebate_share": REBATE_SHARE,
           "bound_c_per_share_equal_weight": 100 * float(per.per_share.mean()),
           "t_by_market": cluster_t(per.per_share),
           "bound_norebate_c": 100 * float(per.per_share_norebate.mean()),
           "t_norebate": cluster_t(per.per_share_norebate),
           "share_weighted_c_per_share": 100 * float(t.pnl.sum() / t["size"].sum()),
           "usd_total": float(t.pnl.sum()), "usd_per_day": float(t.pnl.sum() / 8),
           "share_markets_positive": float((per.pnl > 0).mean())}
    res["kill"] = {"fires": bool(res["bound_c_per_share_equal_weight"] <= 0 or not (res["t_by_market"] >= 2)),
                   "rule": "bound <= 0 or t (clustered by market) < 2"}
    g = t.groupby("bucket", observed=True)
    res["by_time_to_end"] = {str(k): {"trades": int(len(x)), "share_of_volume": float(x["size"].sum() / t["size"].sum()),
                                      "c_per_share": 100 * float(x.pnl.sum() / x["size"].sum()),
                                      "t_by_market": cluster_t(x.groupby("slug").pnl.sum() / x.groupby("slug")["size"].sum())}
                             for k, x in g}
    pb = pd.cut(t.p_up, [0, 0.05, 0.2, 0.4, 0.6, 0.8, 0.95, 1.0])
    res["by_price"] = {str(k): {"share_of_volume": float(x["size"].sum() / t["size"].sum()),
                                "c_per_share": 100 * float(x.pnl.sum() / x["size"].sum())} for k, x in t.groupby(pb, observed=True)}
    sb = pd.cut(t["size"], [0, 10, 100, 1000, np.inf])
    res["by_size"] = {str(k): {"share_of_volume": float(x["size"].sum() / t["size"].sum()),
                               "c_per_share": 100 * float(x.pnl.sum() / x["size"].sum())} for k, x in t.groupby(sb, observed=True)}
    per = per.join(m[["start"]])
    res["by_day"] = {str(d): {"markets": int(len(x)), "c_per_share_eq": 100 * float(x.per_share.mean()),
                              "usd": float(x.pnl.sum())} for d, x in per.groupby(per.start.dt.date)}
    print(json.dumps(res, indent=1, default=str))
    (HERE / out).write_text(json.dumps(res, indent=1, default=str))
    if log_selection:
        sel = HERE / "selection_trials.json"
        sel.write_text(json.dumps([{"name": "p17_maker_upper_bound", "kind": "measurement",
                                    "params": {"fee_rate": fee_rate, "rebate_share": REBATE_SHARE},
                                    "result": {k: res[k] for k in ("bound_c_per_share_equal_weight", "t_by_market")}}],
                                  indent=1))
    return res


if __name__ == "__main__":
    if sys.argv[1] == "validate":
        cmd_validate()
    else:                                  # amendment 1: kill on fee 0.10 (most generous); 0.07 and 0 reported
        cmd_measure(0.10, "measure.json", True)
        for fr, name in ((0.07, "measure_fee007.json"), (0.0, "measure_fee0.json")):
            r = cmd_measure(fr, name, False)
