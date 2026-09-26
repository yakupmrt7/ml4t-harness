"""p13 step 1: the liquidation event set and its power. No price outcomes are read here.

Definitions (PLAN.md, fixed before loading):
  event    = the liquidated user's fill rows (user == liq_user) for one liquidation order,
             merged on (coin, liq_user, oid). Notional = sum(px * sz). Side 'A' = the liquidated
             user sold (a long was liquidated).
             Correction after the first run (no outcomes read): the liquidator vaults (HLP children)
             appear as liq_user on "backstop" rows, including when their own positions are
             auto-deleveraged (ADL). All of that is method "backstop". Rows with dir ==
             "Auto-Deleveraging" are also dropped if any are on the liquidated side (0 found).
             PRIMARY set = method "market" (orders sent into the book = the forced flow);
             "backstop" (position transferred to the liquidator vault, no book trade) reported apart.
  cluster  = events of the six coins merged across coins; a new cluster starts after a gap
             > GAP seconds with no event. One cluster = one independent event. Kill uses GAP=60.

  python research/p13_hl_liquidation_history/events.py      -> events.parquet, step1.json, step1.log
"""
import json, pathlib, sys
import numpy as np, pandas as pd

HERE = pathlib.Path(__file__).parent
SRC = HERE.parents[1] / "data/hl/p13_fills"
COINS = ["BTC", "ETH", "SOL", "HYPE", "ZEC", "XRP"]
SPAN = (pd.Timestamp("2025-07-27 08:00", tz="UTC"), pd.Timestamp("2026-09-25 08:00", tz="UTC"))
DEV_END = pd.Timestamp("2026-06-11 02:00", tz="UTC")
KILL_PER_MONTH = 200


def load_events() -> pd.DataFrame:
    liq = pd.concat([pd.read_parquet(f) for f in sorted((SRC / "liq").glob("*.parquet"))], ignore_index=True)
    liq = liq[(liq.user == liq.liq_user) & liq.coin.isin(COINS)].copy()
    adl = liq.dir == "Auto-Deleveraging"
    load_events.adl_rows = int(adl.sum())
    liq = liq[~adl]
    liq["ntl"] = liq.px * liq.sz
    ev = (liq.groupby(["coin", "liq_user", "oid"], sort=False)
             .agg(t0=("time", "min"), t1=("time", "max"), side=("side", "first"), n_fills=("tid", "size"),
                  sz=("sz", "sum"), ntl=("ntl", "sum"), px_first=("px", "first"), px_last=("px", "last"),
                  markPx=("liq_markPx", "first"), method=("liq_method", "first"),
                  n_sides=("side", "nunique"))
             .reset_index())
    ev["time"] = pd.to_datetime(ev.t0, unit="ms", utc=True)
    ev = ev[(ev.time >= SPAN[0]) & (ev.time < SPAN[1])].sort_values("t0").reset_index(drop=True)
    return ev


def clusters(t_ms: np.ndarray, gap_s: float) -> np.ndarray:
    """cluster id per event (t_ms sorted)."""
    return np.concatenate([[0], np.cumsum(np.diff(t_ms) > gap_s * 1000)])


def main():
    ev_all = load_events()
    ev = ev_all[ev_all.method == "market"].reset_index(drop=True)
    bs = ev_all[ev_all.method == "backstop"]
    months = (SPAN[1] - SPAN[0]).days / 30.4375
    weeks = (SPAN[1] - SPAN[0]).days / 7
    out = dict(span=[str(SPAN[0]), str(SPAN[1])], months=round(months, 2), n_events=len(ev),
               n_liq_orders_with_both_sides=int((ev.n_sides > 1).sum()))
    out.update(adl_rows_dropped=load_events.adl_rows, backstop_events=len(bs),
               backstop_ntl=float(bs.ntl.sum()), market_ntl=float(ev.ntl.sum()))
    lines = [f"span {SPAN[0]} -> {SPAN[1]} ({months:.1f} months); {len(ev)} market-liquidation events (orders); "
             f"excluded: {len(bs)} backstop events (${bs.ntl.sum()/1e9:.2f}B, no book trade), "
             f"{load_events.adl_rows} ADL rows; market events ${ev.ntl.sum()/1e9:.1f}B"]

    # per coin
    per = {}
    lines.append(f"\n{'coin':5s} {'events':>7s} {'/week':>7s} {'first':>11s} {'ntl p50':>9s} {'p90':>9s} {'p99':>10s} "
                 f"{'max':>11s} {'long-liq':>8s} {'clu60':>6s} {'in casc':>7s} {'top5d':>6s}")
    for c in COINS:
        e = ev[ev.coin == c]
        if e.empty:
            lines.append(f"{c:5s} none"); continue
        cid = clusters(e.t0.to_numpy(), 60)
        csize = np.bincount(cid)
        daycount = e.time.dt.floor("D").value_counts()
        q = e.ntl.quantile([.5, .9, .99]).to_numpy()
        per[c] = dict(events=len(e), per_week=len(e) / weeks, first=str(e.time.min().date()),
                      ntl_p50=q[0], ntl_p90=q[1], ntl_p99=q[2], ntl_max=float(e.ntl.max()),
                      long_liq_share=float((e.side == "A").mean()),
                      clusters60=int(len(csize)), share_in_cascade=float(csize[cid][csize[cid] > 1].size / len(e)),
                      top5_days_share=float(daycount.head(5).sum() / len(e)), days_with_events=int(len(daycount)))
        p = per[c]
        lines.append(f"{c:5s} {p['events']:7d} {p['per_week']:7.0f} {p['first']:>11s} {q[0]:9,.0f} {q[1]:9,.0f} {q[2]:10,.0f} "
                     f"{p['ntl_max']:11,.0f} {p['long_liq_share']:8.0%} {p['clusters60']:6d} "
                     f"{p['share_in_cascade']:7.0%} {p['top5_days_share']:6.0%}")
    out["per_coin"] = per

    # independent events: clusters across the six coins
    t = ev.t0.to_numpy()
    lines.append("\nindependent events (clusters across all six coins):")
    lines.append(f"{'gap':>5s} {'clusters':>9s} {'/month':>7s} {'median month':>12s} {'min month':>9s} {'dev':>6s} {'holdout':>7s}")
    ind = {}
    for gap in (10, 60, 300):
        cid = clusters(t, gap)
        first = ev.groupby(cid).time.min()
        by_m = first.dt.tz_localize(None).dt.to_period("M").value_counts().sort_index()
        full_months = by_m.iloc[1:-1]            # first and last months are partial
        ind[gap] = dict(clusters=int(cid.max() + 1), per_month=(cid.max() + 1) / months,
                        median_full_month=float(full_months.median()), min_full_month=int(full_months.min()),
                        dev=int((first < DEV_END).sum()), holdout=int((first >= DEV_END).sum()),
                        by_month={str(k): int(v) for k, v in by_m.items()})
        d = ind[gap]
        lines.append(f"{gap:4d}s {d['clusters']:9d} {d['per_month']:7.0f} {d['median_full_month']:12.0f} "
                     f"{d['min_full_month']:9d} {d['dev']:6d} {d['holdout']:7d}")
    out["independent"] = ind
    lines.append("clusters per calendar month (60 s gap): " +
                 ", ".join(f"{k}: {v}" for k, v in ind[60]["by_month"].items()))

    # cluster size and concentration in time (60 s)
    cid = clusters(t, 60)
    g = ev.groupby(cid).agg(n=("coin", "size"), ntl=("ntl", "sum"), coins=("coin", "nunique"),
                            dur=("t1", "max"), start=("t0", "min"))
    g["dur_s"] = (g.dur - g.start) / 1000
    days = pd.to_datetime(g.start, unit="ms", utc=True).dt.floor("D").value_counts()
    n_eff_days = days.sum() ** 2 / (days ** 2).sum()       # effective number of equally-weighted days
    out["cluster_shape_60"] = dict(size_p50=float(g.n.median()), size_p90=float(g.n.quantile(.9)),
                                   size_max=int(g.n.max()), multi_coin_share=float((g.coins > 1).mean()),
                                   dur_p50_s=float(g.dur_s.median()), dur_p90_s=float(g.dur_s.quantile(.9)),
                                   days_with_clusters=int(len(days)), top10_days_share=float(days.head(10).sum() / days.sum()),
                                   n_eff_days=float(n_eff_days))
    s = out["cluster_shape_60"]
    lines.append(f"\ncluster shape (60 s): events/cluster p50 {s['size_p50']:.0f}, p90 {s['size_p90']:.0f}, max {s['size_max']}; "
                 f"multi-coin {s['multi_coin_share']:.0%}; duration p50 {s['dur_p50_s']:.0f}s p90 {s['dur_p90_s']:.0f}s")
    lines.append(f"time concentration: clusters on {s['days_with_clusters']} days; top-10 days hold "
                 f"{s['top10_days_share']:.0%}; effective number of days {s['n_eff_days']:.0f}")

    # power where it matters: clusters by total liquidated notional (descriptive, no outcomes)
    lines.append("\nclusters (60 s) by total market-liquidated notional:")
    lines.append(f"{'>= $':>8s} {'clusters':>9s} {'/month':>7s} {'dev':>6s} {'holdout':>7s} {'days':>5s}")
    by_size = {}
    for thr in (1e5, 1e6, 1e7):
        m = g.ntl >= thr
        st = pd.to_datetime(g.start[m], unit="ms", utc=True)
        by_size[int(thr)] = dict(clusters=int(m.sum()), per_month=float(m.sum() / months),
                                 dev=int((st < DEV_END).sum()), holdout=int((st >= DEV_END).sum()),
                                 days=int(st.dt.floor("D").nunique()))
        b = by_size[int(thr)]
        lines.append(f"{thr:8,.0f} {b['clusters']:9d} {b['per_month']:7.0f} {b['dev']:6d} {b['holdout']:7d} {b['days']:5d}")
    out["clusters_by_notional_60"] = by_size

    # kill 1
    k = ind[60]["per_month"]
    out["kill_power"] = dict(threshold=KILL_PER_MONTH, value=k, killed=bool(k < KILL_PER_MONTH))
    lines.append(f"\nKILL 1 (power): {k:.0f} independent events/month (60 s) vs threshold {KILL_PER_MONTH} -> "
                 f"{'KILLED' if k < KILL_PER_MONTH else 'passes'}")

    ev_all.to_parquet(HERE / "events.parquet")      # both methods; step 2 filters to market
    json.dump(out, open(HERE / "step1.json", "w"), indent=1, default=float)
    txt = "\n".join(lines); print(txt); (HERE / "step1.log").write_text(txt + "\n")


if __name__ == "__main__":
    main()
