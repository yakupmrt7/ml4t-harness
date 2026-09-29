"""p22 step 0 checks + step 1 (PLAN.md), DEV only (announcements 2020-01-22 .. 2024-12-31).

  python research/p22_earnings_straddles/step1.py
"""
import io
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
D = Path("data/collector/p22")
FEE = 0.0065
DEV_END = pd.Timestamp("2024-12-31")


def load_quotes(company):
    f = D / "quotes" / f"{company.replace('.', '_')}.parquet"
    if not f.exists():
        return pd.DataFrame()
    q = pd.read_parquet(f)
    if q.empty:
        return q
    q["date"], q["expiration"] = pd.to_datetime(q.date), pd.to_datetime(q.expiration)
    for c in ("strike", "bid", "ask", "vol"):
        q[c] = pd.to_numeric(q[c], errors="coerce")
    q["cp"] = q.call_put.str.lower().str[0]
    assert (q.date <= DEV_END).all(), "holdout rows loaded"
    return q


def straddle(q, E_cands, X, ann_day, days):
    """-> dict or None. Entry at the latest E candidate with quotes; expiry >= 5 trading days after the announcement;
    ATM by put-call parity at E; buy at ask on E, sell at bid on X."""
    if pd.isna(X) or q.empty:
        return None
    qx = q[q.date == X]
    if qx.empty:
        return None
    pos = days.searchsorted(ann_day)
    min_exp = days[min(pos + 5, len(days) - 1)] if pos + 5 < len(days) else ann_day + pd.Timedelta(days=7)
    for E in sorted(E_cands, reverse=True):                      # latest candidate first (closest to ~3 days)
        qe = q[q.date == E]
        if qe.empty:
            continue
        exps = sorted(e for e in qe.expiration.unique() if e >= min_exp)
        for exp in exps[:1]:
            a = qe[qe.expiration == exp]
            c = a[a.cp == "c"].set_index("strike")
            p = a[a.cp == "p"].set_index("strike")
            k = c.index.intersection(p.index)
            if not len(k):
                continue
            ok = [s for s in k if c.loc[s, "bid"] > 0 and p.loc[s, "bid"] > 0 and c.loc[s, "ask"] >= c.loc[s, "bid"]
                  and p.loc[s, "ask"] >= p.loc[s, "bid"]]
            if not ok:
                continue
            mid = lambda df, s: (df.loc[s, "bid"] + df.loc[s, "ask"]) / 2
            K = min(ok, key=lambda s: abs(mid(c, s) - mid(p, s)))
            b = qx[(qx.expiration == exp) & (qx.strike == K)]
            cx, px_ = b[b.cp == "c"], b[b.cp == "p"]
            if cx.empty or px_.empty:
                return None
            cx, px_ = cx.iloc[0], px_.iloc[0]
            if not (cx.bid >= 0 and px_.bid >= 0 and cx.ask > 0 and px_.ask > 0):
                return None
            cost_in = c.loc[K, "ask"] + p.loc[K, "ask"] + 2 * FEE
            proceeds = cx.bid + px_.bid - 2 * FEE
            mid_in = mid(c, K) + mid(p, K)
            mid_out = (cx.bid + cx.ask) / 2 + (px_.bid + px_.ask) / 2
            spread_rt = ((c.loc[K, "ask"] - c.loc[K, "bid"]) + (p.loc[K, "ask"] - p.loc[K, "bid"]) +
                         (cx.ask - cx.bid) + (px_.ask - px_.bid)) / 2 / mid_in
            return {"E": E, "X": X, "expiry": exp, "K": K, "net": proceeds / cost_in - 1, "gross_mid": mid_out / mid_in - 1,
                    "spread_rt_over_mid": spread_rt, "iv_E": float(np.nanmean([c.loc[K, "vol"], p.loc[K, "vol"]])),
                    "days_held": int(days.searchsorted(X) - days.searchsorted(E))}
    return None


def cluster_t(x, clusters):
    g = pd.Series(np.asarray(x, float)).groupby(np.asarray(clusters)).mean()
    return float(g.mean() / (g.std(ddof=1) / np.sqrt(len(g)))) if len(g) > 2 else np.nan, int(len(g))


def main():
    ev = pd.read_parquet(D / "events.parquet")
    days = pd.DatetimeIndex(json.loads((D / "spy_days.json").read_text()))
    days = days[days <= DEV_END]
    rows, drops = [], {"no_timing": 0, "no_trade": 0, "no_placebo": 0}
    cache = {}
    for r in ev.itertuples():
        q = cache.setdefault(r.company, load_quotes(r.company))
        if pd.isna(r.X):
            drops["no_timing"] += 1
            continue
        t = straddle(q, list(r.E_cands), r.X, r.date, days)
        if t is None:
            drops["no_trade"] += 1
            continue
        pl = None
        if r.placebo_ok:
            pl = straddle(q, list(r.Ep_cands), r.Xp, r.Xp + pd.Timedelta(days=1), days)
        if pl is None:
            drops["no_placebo"] += 1
        rows.append({"company": r.company, "ann": r.date, "when": r.when, **t,
                     "placebo_net": pl["net"] if pl else np.nan, "placebo_gross_mid": pl["gross_mid"] if pl else np.nan})
    d = pd.DataFrame(rows)
    d["week"] = d.ann.dt.to_period("W").astype(str)
    d.to_csv(HERE / "events_dev.csv", index=False)
    net_t, n_w = cluster_t(d.net, d.week)
    both = d.dropna(subset=["placebo_net"])
    diff_t, n_w2 = cluster_t(both.net - both.placebo_net, both.week)
    res = {"events_total": int(len(ev)), "drops": drops, "trades": int(len(d)), "weeks": n_w,
           "net_mean_%": 100 * float(d.net.mean()), "net_median_%": 100 * float(d.net.median()), "net_t_by_week": net_t,
           "gross_mid_mean_%": 100 * float(d.gross_mid.mean()), "gross_mid_t_by_week": cluster_t(d.gross_mid, d.week)[0],
           "median_spread_rt_%_of_mid": 100 * float(d.spread_rt_over_mid.median()),
           "placebo_pairs": int(len(both)), "placebo_net_mean_%": 100 * float(both.placebo_net.mean()),
           "earn_minus_placebo_net_%": 100 * float((both.net - both.placebo_net).mean()), "earn_minus_placebo_t": diff_t,
           "earn_minus_placebo_gross_mid_%": 100 * float((both.gross_mid - both.placebo_gross_mid).mean()),
           "median_days_held": float(d.days_held.median())}
    res["kills"] = {"k1_net_mean_le0_or_t_below_2": not (res["net_mean_%"] > 0 and net_t >= 2),
                    "k2_vs_placebo_t_below_2": not (diff_t >= 2),
                    "k3_spread_ge_gross": res["median_spread_rt_%_of_mid"] >= res["gross_mid_mean_%"]}
    res["kills"]["passes"] = not any(res["kills"].values())
    by = {}
    for name, key in (("year", d.ann.dt.year), ("when", d["when"].fillna("?"))):
        by[name] = {str(k): {"n": int(len(g)), "net_mean_%": 100 * float(g.net.mean()), "gross_mid_%": 100 * float(g.gross_mid.mean())}
                    for k, g in d.groupby(key)}
    d["iv_q"] = pd.qcut(d.iv_E, 5, labels=False, duplicates="drop")
    by["iv_quintile"] = {str(k): {"n": int(len(g)), "net_mean_%": 100 * float(g.net.mean()), "gross_mid_%": 100 * float(g.gross_mid.mean())}
                         for k, g in d.groupby("iv_q")}
    res["by"] = by
    (HERE / "step1.json").write_text(json.dumps(res, indent=1, default=str))
    (HERE / "selection_trials.json").write_text(json.dumps([{"name": "p22_earnings_straddle_net", "kind": "rule",
                                                             "result": {k: res[k] for k in ("net_mean_%", "net_t_by_week")}}], indent=1))
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
