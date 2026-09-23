"""p09 Step 1 (PLAN.md + amendment 1): rebuild each dev 5m market's settlement from the
collector's Chainlink rounds and compare with Polymarket's resolution (Gamma API).

Three agreement rates: (a) rebuilt outcome vs Gamma, (b) final Polymarket Up mid vs Gamma,
(c) rebuilt vs final mid. Settlement candidates A/B/C (PLAN.md), window length from each
market's own resolutionSource (btc-usd: point, twap-30s: 30 s, twap-60s: 60 s).
Dev only: every path read is asserted to be dated < 2026-09-06.

Run from the repo root:  python research/p09_polymarket_fairprice/step1_settlement.py
"""
import glob
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
D = Path("data/collector/p09")
HOLDOUT_START = date(2026, 9, 6)
LAST_DEV_START = 1788652500                      # 2026-09-05 23:55 UTC
EXCLUDED_HOURS = ({("2026-07-25", h) for h in range(18)} | {("2026-07-26", h) for h in (1, 3, 4)}
                  | {("2026-08-04", h) for h in range(16, 24)})
RULE_W = {"btc-usd": 0, "btc-usd-twap-30s-streams": 30, "btc-usd-twap-60s-streams": 60}
FINAL_MID_WINDOW = (-5, 60)                       # seconds around T_end
MARGIN_BINS = [0, 1e-5, 3e-5, 1e-4, 3e-4, 1e-3, np.inf]


def dev_files(pattern):
    fs = sorted(glob.glob(str(D / pattern)))
    for f in fs:
        d = date.fromisoformat(f.split("date=")[1][:10])
        assert d < HOLDOUT_START, f
    return fs


def present_hours(stream):
    """{(date, hour)} whose manifest exists, minus the fixed exclusions."""
    out = set()
    for f in dev_files(f"_manifest/{stream}/date=*/*.json"):
        out.add((f.split("date=")[1][:10], int(Path(f).stem)))
    return out - EXCLUDED_HOURS


def hours_between(t0, t1):
    h = pd.date_range(pd.Timestamp(t0, unit="s", tz="UTC").floor("h"), pd.Timestamp(t1, unit="s", tz="UTC"), freq="h")
    return {(str(x.date()), x.hour) for x in h}


def load_markets():
    m = pd.concat(pd.read_parquet(f) for f in dev_files("meta/polymarket__markets/date=*/*.parquet"))
    m = m[m["slug"].str.startswith("btc-updown-5m-")].drop_duplicates("slug", keep="last").copy()
    m["t0"] = m["slug"].str.rsplit("-", n=1).str[1].astype(int)
    m = m[m["t0"] <= LAST_DEV_START]
    m["t_end"] = m["t0"] + 300
    m["rule"] = m["resolutionSource"].str.replace("https://data.chain.link/streams/", "", regex=False)
    m["W"] = m["rule"].map(RULE_W)
    assert m["W"].notna().all(), m.loc[m["W"].isna(), "rule"].unique()
    toks = m["clobTokenIds"].map(json.loads)
    outs = m["outcomes"].map(json.loads)
    m["up_token"] = [t[o.index("Up")] for t, o in zip(toks, outs)]
    return m.set_index("slug")


def load_rounds():
    c = pd.concat(pd.read_parquet(f, columns=["n_rounds", "price_last", "updated_at_last"])
                  for f in dev_files("1s/chainlink__btc/date=*/*.parquet"))
    multi = int((c["n_rounds"] > 1).sum())
    r = c.drop_duplicates("updated_at_last").sort_values("updated_at_last")
    return r["updated_at_last"].to_numpy(np.int64), r["price_last"].to_numpy(float), multi


def step_value(ts, px, t):
    """Price of the last round with updated_at <= t (NaN if none)."""
    i = np.searchsorted(ts, t, side="right") - 1
    return px[i] if i >= 0 else np.nan


def twap(ts, px, a, b):
    """Time-weighted average of the round step function over [a, b]. -> (twap, rounds inside (a, b])."""
    if b <= a:
        return step_value(ts, px, b), 0
    i0 = np.searchsorted(ts, a, side="right")
    i1 = np.searchsorted(ts, b, side="right")
    knots = np.concatenate([[a], ts[i0:i1], [b]]).astype(float)
    vals = np.concatenate([[step_value(ts, px, a)], px[i0:i1]])
    return float(np.sum(vals * np.diff(knots)) / (b - a)), int(i1 - i0)


def settle(ts, px, t0, t1, W, cand):
    if W == 0 or cand == "B":
        s, e = step_value(ts, px, t0), step_value(ts, px, t1)
        ns = ne = 0
    elif cand == "A":
        (s, ns), (e, ne) = twap(ts, px, t0 - W, t0), twap(ts, px, t1 - W, t1)
    elif cand == "C":
        (s, ns), (e, ne) = twap(ts, px, t0, t0 + W), twap(ts, px, t1 - W, t1)
    return s, e, ns, ne


def final_mids(m, pc_hours):
    """Last Up-token mid known in [T_end - 5 s, T_end + 60 s], per market (NaN if none)."""
    need = {}
    for slug, r in m.iterrows():
        for dh in hours_between(r["t_end"] + FINAL_MID_WINDOW[0], r["t_end"] + FINAL_MID_WINDOW[1]):
            need.setdefault(dh, []).append(slug)
    tok = m["up_token"]
    out = {}
    for (d, h), slugs in sorted(need.items()):
        if (d, h) not in pc_hours:
            continue
        f = D / f"1s/polymarket__price_change/date={d}/polymarket__price_change__{h:02d}.parquet"
        assert date.fromisoformat(d) < HOLDOUT_START
        if not f.exists():
            continue
        p = pd.read_parquet(f, columns=["bucket_start", "asset_id", "mid_last"])
        p["asset_id"] = p["asset_id"].astype(str)
        p = p[p["asset_id"].isin(set(tok[slugs]))]
        p["t"] = p["bucket_start"].dt.as_unit("s").astype("int64")
        for slug in slugs:
            te = m.at[slug, "t_end"]
            q = p[(p["asset_id"] == tok[slug]) & (p["t"] >= te + FINAL_MID_WINDOW[0]) & (p["t"] <= te + FINAL_MID_WINDOW[1])]
            if len(q):
                prev = out.get(slug)
                last = q.sort_values("t").iloc[-1]
                if prev is None or last["t"] >= prev[0]:
                    out[slug] = (int(last["t"]), float(last["mid_last"]))
    return pd.Series({k: v[1] for k, v in out.items()}, dtype=float)


def gamma_outcomes(m):
    g = pd.read_parquet(D / "resolutions.parquet").set_index("slug")
    assert g.index.str.rsplit("-", n=1).str[1].astype(int).max() <= LAST_DEV_START
    g = g.reindex(m.index)
    status = pd.Series("ok", index=m.index)
    status[g["n"].fillna(0) == 0] = "not_found"
    ok = status == "ok"
    closed = g["closed"].astype(str).str.lower() == "true"
    resolved = g["umaResolutionStatus"].astype(str) == "resolved"
    status[ok & ~closed] = "unresolved"
    status[ok & closed & ~resolved] = "not_uma_resolved"
    up = pd.Series(np.nan, index=m.index)
    for slug in m.index[status == "ok"]:
        outs, prices = json.loads(g.at[slug, "outcomes"]), json.loads(g.at[slug, "outcomePrices"])
        pu = float(prices[outs.index("Up")])
        if pu in (0.0, 1.0) and float(prices[outs.index("Down")]) == 1 - pu:
            up[slug] = pu
        else:
            status[slug] = "void_or_split"
    return up, status


def agree(x, y):
    k = x.notna() & y.notna()
    return {"n": int(k.sum()), "agree": int((x[k] == y[k]).sum()),
            "rate": float((x[k] == y[k]).mean()) if k.any() else float("nan")}


if __name__ == "__main__":
    m = load_markets()
    ts, px, multi = load_rounds()
    cl_hours, pc_hours = present_hours("chainlink__btc"), present_hours("polymarket__price_change")
    m["cl_complete"] = [hours_between(r.t0 - max(r.W, 1), r.t_end) <= cl_hours for r in m.itertuples()]
    out = {"n_markets_dev_5m": len(m), "by_rule": m["rule"].value_counts().to_dict(),
           "n_chainlink_complete": int(m["cl_complete"].sum()), "chainlink": {}}

    # ---- Chainlink feed stats (dev, complete hours only)
    gaps = np.diff(ts)
    out["chainlink"] = {"n_rounds": int(len(ts)), "seconds_with_2plus_rounds": multi,
                        "gap_s_quantiles": {q: float(np.quantile(gaps, q)) for q in (0.05, 0.25, 0.5, 0.75, 0.95, 0.99)},
                        "gap_s_max": int(gaps.max())}

    gamma_up, gstatus = gamma_outcomes(m)
    out["gamma_status"] = gstatus.value_counts().to_dict()
    mid = final_mids(m, pc_hours).reindex(m.index)
    mid_up = pd.Series(np.where(mid > 0.95, 1.0, np.where(mid < 0.05, 0.0, np.nan)), index=m.index)
    mid_up[mid.isna()] = np.nan
    out["final_mid"] = {"n_with_mid": int(mid.notna().sum()), "n_called": int(mid_up.notna().sum())}

    rows = []
    use = m[m["cl_complete"]]
    for cand in ("A", "B", "C"):
        for slug, r in use.iterrows():
            s, e, ns, ne = settle(ts, px, r["t0"], r["t_end"], r["W"], cand)
            rows.append({"slug": slug, "cand": cand, "rule": r["rule"], "start": s, "end": e, "n_rounds_start": ns,
                         "n_rounds_end": ne, "margin": abs(e / s - 1), "rebuilt_up": float(e >= s)})
    rb = pd.DataFrame(rows)
    out["agreement"] = {}
    for rule, g in rb.groupby("rule"):
        out["agreement"][rule] = {}
        for cand, gc in g.groupby("cand"):
            gc = gc.set_index("slug")
            out["agreement"][rule][cand] = {"a_rebuilt_vs_gamma": agree(gc["rebuilt_up"], gamma_up),
                                            "c_rebuilt_vs_finalmid": agree(gc["rebuilt_up"], mid_up)}
    out["b_finalmid_vs_gamma"] = {rule: agree(mid_up[m["rule"] == rule], gamma_up[m["rule"] == rule]) for rule in RULE_W}
    best = {rule: max(("A", "B", "C") if RULE_W[rule] else ("B",),
                      key=lambda c: out["agreement"][rule][c]["a_rebuilt_vs_gamma"]["rate"]) for rule in out["agreement"]}
    out["best_candidate"] = best
    sel = pd.concat([rb[(rb["rule"] == rule) & (rb["cand"] == c)] for rule, c in best.items()]).set_index("slug")
    sel["gamma_up"] = gamma_up
    sel["mid_up"] = mid_up
    sel["final_mid"] = mid
    k = sel["gamma_up"].notna()
    out["a_overall_best"] = agree(sel["rebuilt_up"], sel["gamma_up"])
    sel["agree"] = sel["rebuilt_up"] == sel["gamma_up"]
    sel["margin_bin"] = pd.cut(sel["margin"], MARGIN_BINS, include_lowest=True).astype(str)
    out["a_by_margin"] = sel[k].groupby("margin_bin")["agree"].agg(["size", "mean"]).to_dict("index")
    out["a_by_rounds_in_end_window"] = sel[k].assign(r=sel["n_rounds_end"].clip(upper=3)).groupby("r")["agree"].agg(
        ["size", "mean"]).to_dict("index")
    out["zero_rounds_in_end_window_frac"] = {rule: float((g["n_rounds_end"] == 0).mean())
                                             for rule, g in sel.groupby("rule")}
    dis = sel[k & ~sel["agree"]].reset_index()[["slug", "rule", "cand", "start", "end", "margin", "n_rounds_start",
                                                 "n_rounds_end", "rebuilt_up", "gamma_up", "final_mid"]]
    dis.to_csv(HERE / "step1_disagreements.csv", index=False)
    sel.reset_index().to_parquet(D / "step1_settlement.parquet")
    out["n_disagreements"] = len(dis)
    out["gate_99"] = bool(out["a_overall_best"]["rate"] >= 0.99)
    (HERE / "step1.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out, indent=1, default=str))
