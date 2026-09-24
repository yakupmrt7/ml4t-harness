"""p09 Step 1b (PLAN.md amendment 2): rebuild each dev 5m market's settlement from a TWAP of
the BINANCE mid (futures, spot, 50/50 blend) instead of on-chain Chainlink rounds, and map
on-chain Chainlink against Binance (lead/lag, slope, residual). Dev only.

Run from the repo root:  python research/p09_polymarket_fairprice/step1b_binance.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

import step1_settlement as s1

HERE = Path(__file__).parent
D = s1.D
SPOT_LAG = 0.133                     # s: median spot receive lag (p08 SCHEMAS.md); spot is bucketed on receive time
FFILL_LIMIT = 60                     # s: carry a mid forward at most this long
STREAMS = {"fut": "binance_fut__btcusdt@bookTicker", "spot": "binance_spot__btcusdt@bookTicker"}
KS = list(range(-10, 61))


def load_series(stream):
    """Dense per-second arrays on [T0, T1): last mid and in-second TWAP (NaN where no data within FFILL_LIMIT)."""
    fs = s1.dev_files(f"1s/{stream}/date=*/*.parquet")
    b = pd.concat(pd.read_parquet(f, columns=["bucket_start", "mid_last", "mid_twap"]) for f in fs)
    t = b["bucket_start"].dt.as_unit("s").astype("int64").to_numpy()
    T0, T1 = t.min(), t.max() + 1
    last = np.full(T1 - T0, np.nan)
    tw = np.full(T1 - T0, np.nan)
    last[t - T0] = b["mid_last"].to_numpy()
    tw[t - T0] = np.where(np.isfinite(b["mid_twap"]), b["mid_twap"], b["mid_last"])
    # seconds with no quote: carry the last mid (a quiet book), up to FFILL_LIMIT seconds
    last = pd.Series(last).ffill(limit=FFILL_LIMIT).to_numpy()
    tw = np.where(np.isnan(tw), last, tw)
    return T0, last, tw


class Series:
    def __init__(self, stream, shift):
        self.T0, self.last, self.tw = load_series(stream)
        self.shift = shift                       # exchange time = receive time - shift

    def point(self, T):
        """Last mid before exchange time T (bucket T-1; the sub-second shift is ignored for a point)."""
        i = T - 1 - self.T0
        return self.last[i] if 0 <= i < len(self.last) else np.nan

    def twap(self, a, b):
        """TWAP over exchange time [a, b] from 1 s buckets; with shift s the receive window is [a+s, b+s]."""
        i0, i1 = a - self.T0, b - self.T0
        if i0 < 0 or i1 >= len(self.tw):
            return np.nan
        if self.shift == 0:
            return float(np.mean(self.tw[i0:i1]))
        w = np.ones(i1 - i0 + 1)
        w[0], w[-1] = 1 - self.shift, self.shift
        return float(np.sum(self.tw[i0:i1 + 1] * w) / (b - a))


def settle(ser, t0, t1, W, cand):
    if W == 0 or cand == "B":
        return ser.point(t0), ser.point(t1)
    if cand == "A":
        return ser.twap(t0 - W, t0), ser.twap(t1 - W, t1)
    return ser.twap(t0, t0 + W), ser.twap(t1 - W, t1)       # C


def margin_table(df, col):
    x = df.assign(bin=pd.cut(df[col], s1.MARGIN_BINS, include_lowest=True).astype(str))
    return x.groupby("bin")["agree"].agg(["size", "mean"]).to_dict("index")


def mapping(ts, px, ser, name):
    """On-chain CL round price vs Binance mid at u - k: basis-demeaned residual std per k, and a returns regression."""
    def pts(u, k):
        i = u - k - 1 - ser.T0
        out = np.full(len(u), np.nan)
        ok = (i >= 0) & (i < len(ser.last))
        out[ok] = ser.last[i[ok]]
        return out
    u = ts.astype(np.int64)
    keep = np.isfinite(pts(u, KS[0])) & np.isfinite(pts(u, KS[-1]))
    u, p = u[keep], px[keep]
    res = {}
    for k in KS:
        bm = pts(u, k)
        r = pd.Series(np.log(p) - np.log(bm))
        r = r - r.rolling(109, center=True, min_periods=30).median()   # ~1 h of rounds: slow basis drift out
        res[k] = float(r.std() * 1e4)
    kbest = min(res, key=res.get)
    bm = pts(u, kbest)
    dt = np.diff(u)
    ok = (dt > 0) & (dt <= 60) & np.isfinite(np.diff(np.log(bm)))
    y, x = np.diff(np.log(p))[ok], np.diff(np.log(bm))[ok]
    slope, icpt = np.polyfit(x, y, 1)
    e = y - (slope * x + icpt)
    return {"series": name, "n_rounds": int(len(u)), "resid_std_bp_by_k": {k: round(v, 3) for k, v in res.items()},
            "best_k_s": kbest, "resid_std_bp_at_best_k": res[kbest], "resid_std_bp_at_k0": res[0],
            "returns_regression_at_best_k": {"n": int(ok.sum()), "slope": float(slope), "r2": float(1 - e.var() / y.var()),
                                             "resid_std_bp": float(e.std() * 1e4)}}


if __name__ == "__main__":
    m = s1.load_markets()
    step1 = pd.read_parquet(D / "step1_settlement.parquet").set_index("slug")
    gamma_up = step1["gamma_up"]
    use = m.loc[step1.index[step1["gamma_up"].notna()]]            # the 11,958 of Step 1
    assert len(use) == 11958, len(use)
    hours = {k: s1.present_hours(v) for k, v in STREAMS.items()}
    ser = {"fut": Series(STREAMS["fut"], 0.0), "spot": Series(STREAMS["spot"], SPOT_LAG)}
    out = {"n_markets": len(use), "spot_shift_s": SPOT_LAG, "onchain_step1": {
        "btc-usd": 0.873, "btc-usd-twap-30s-streams": 0.932, "btc-usd-twap-60s-streams": 0.940, "all": 0.920}}
    rows = []
    for slug, r in use.iterrows():
        need = s1.hours_between(r["t0"] - max(r["W"], 1), r["t_end"])
        cov = {k: need <= hours[k] for k in STREAMS}
        for cand in ("A", "B", "C"):
            v = {k: settle(ser[k], r["t0"], r["t_end"], r["W"], cand) if cov[k] else (np.nan, np.nan) for k in ser}
            bl = tuple(np.exp(0.5 * (np.log(v["fut"][i]) + np.log(v["spot"][i]))) for i in (0, 1))
            for name, (s, e) in {**v, "blend": bl}.items():
                rows.append({"slug": slug, "rule": r["rule"], "cand": cand, "series": name, "start": s, "end": e})
    rb = pd.DataFrame(rows)
    rb["ok"] = rb["start"].notna() & rb["end"].notna()
    rb["up"] = (rb["end"] >= rb["start"]).astype(float)
    rb["margin"] = (rb["end"] / rb["start"] - 1).abs()
    rb["gamma_up"] = rb["slug"].map(gamma_up)
    rb["onchain_margin"] = rb["slug"].map(step1["margin"])
    rb["agree"] = rb["up"] == rb["gamma_up"]
    rb = rb[rb["ok"]]

    out["coverage"] = rb[rb["cand"] == "A"].groupby("series").size().to_dict()
    out["agreement"] = {}
    for (name, cand), g in rb.groupby(["series", "cand"]):
        key = f"{name}/{cand}"
        out["agreement"][key] = {"all": {"n": len(g), "rate": float(g["agree"].mean())},
                                 **{rule: {"n": len(x), "rate": float(x["agree"].mean())} for rule, x in g.groupby("rule")}}
    # primary = candidate A (trailing windows; point for btc-usd); best series among fut/spot/blend on A
    prim = {k: v for k, v in out["agreement"].items() if k.endswith("/A")}
    best = max(prim, key=lambda k: prim[k]["all"]["rate"])
    out["best_primary"] = best
    g = rb[(rb["series"] + "/" + rb["cand"]) == best]
    out["best_by_own_margin"] = margin_table(g, "margin")
    out["best_by_onchain_margin"] = margin_table(g, "onchain_margin")
    d = g[~g["agree"]]
    out["best_disagreements"] = {"n": len(d), "rebuilt_up_gamma_down": int((d["up"] == 1).sum()),
                                 "rebuilt_down_gamma_up": int((d["up"] == 0).sum()),
                                 "own_margin_bp_quantiles": (d["margin"].quantile([.5, .9, .99, 1]) * 1e4).round(3).to_dict()}
    # same markets, both methods: where do they disagree with each other and with Gamma
    both = g.set_index("slug").join(step1[["rebuilt_up"]])
    out["best_vs_onchain"] = {
        "both_right": int(((both["up"] == both["gamma_up"]) & (both["rebuilt_up"] == both["gamma_up"])).sum()),
        "binance_right_onchain_wrong": int(((both["up"] == both["gamma_up"]) & (both["rebuilt_up"] != both["gamma_up"])).sum()),
        "binance_wrong_onchain_right": int(((both["up"] != both["gamma_up"]) & (both["rebuilt_up"] == both["gamma_up"])).sum()),
        "both_wrong": int(((both["up"] != both["gamma_up"]) & (both["rebuilt_up"] != both["gamma_up"])).sum())}
    d.to_csv(HERE / "step1b_disagreements.csv", index=False)

    ts, px, _ = s1.load_rounds()
    out["mapping"] = [mapping(ts, px, ser[k], k) for k in ser]
    out["decision"] = ("CONTINUE: Binance >= 99%" if prim[best]["all"]["rate"] >= 0.99 else
                       "STOP for decision: 95-99%" if prim[best]["all"]["rate"] >= 0.95 else "STOP: below 95%")
    (HERE / "step1b.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: v for k, v in out.items() if k != "mapping"}, indent=1, default=str))
    for mp in out["mapping"]:
        print(mp["series"], {k: v for k, v in mp.items() if k != "resid_std_bp_by_k"})
