"""p13 review fix: size deciles by liquidated notional KNOWN AT ENTRY (t0 + 2 s), the registered
cost variants, and where the no-book windows are. Reads step 2 outputs; no new outcomes defined.
  -> causal_size.json"""
import json, pathlib
import numpy as np, pandas as pd
from events import clusters

HERE = pathlib.Path(__file__).parent
FEE = 4.5
ev = pd.read_parquet(HERE / "events.parquet")
ev = ev[ev.method == "market"].sort_values("t0").reset_index(drop=True)
ev["cluster"] = clusters(ev.t0.to_numpy(), 60)
wm = pd.read_parquet(HERE / "window_metrics.parquet")
w = wm[wm.max_gap_ms <= 2000].copy()

# notional of the window's coin in its cluster with liquidation time <= t0 + 2 s
e = ev[["cluster", "coin", "t0", "ntl"]].rename(columns={"t0": "te"})
m = w[["window_id", "cluster", "coin", "t0"]].merge(e, on=["cluster", "coin"])
known = m[m.te <= m.t0 + 2000].groupby("window_id").ntl.sum()
w["ntl_known"] = w.window_id.map(known).fillna(0.0)
w["known_share"] = w.ntl_known / w.liq_ntl

out = dict(known_share_top_registered_decile_p50=float(w[w.liq_ntl >= w.liq_ntl.quantile(.9)].known_share.median()))
w["cdec"] = pd.qcut(w.ntl_known.rank(method="first"), 10, labels=False)
out["deciles_known_at_entry"] = [dict(decile=int(d), ntl_known_lo=float(g.ntl_known.min()), ntl_known_hi=float(g.ntl_known.max()),
                                      windows=len(g), clusters=int(g.cluster.nunique()),
                                      rev60=float(g.rev60.median()), rev120=float(g.rev120.median()),
                                      rev300=float(g.rev300.median()), cost=float(g.cost10k_rt.median()))
                                 for d, g in w.groupby("cdec")]
top = w[w.cdec == 9]
out["top_known_decile"] = dict(threshold=float(top.ntl_known.min()), windows=len(top), clusters=int(top.cluster.nunique()),
                               **{f"rev{h}": float(top[f"rev{h}"].median()) for h in (60, 120, 300)},
                               cost=float(top.cost10k_rt.median()),
                               killed=bool(all(top[f"rev{h}"].median() < top.cost10k_rt.median() for h in (60, 120, 300))))
# registered cost variants (all windows): exit-time book, and maker exit (taker in + maker out, half-spread+impact in only)
w["cost_maker_exit"] = np.where(w.s == -1, w.cost10k_rt - 2 * FEE, w.cost10k_rt - 2 * FEE) / 2 + FEE + 1.5
out["cost_variants_all"] = {f"exit_book_h{h}": float(w[f"cost10k_exit{h}"].median()) for h in (60, 120, 300)}
out["cost_variants_all"]["maker_exit_optimistic"] = float(w.cost_maker_exit.median())
out["cost_variants_all"]["cost50k_rt"] = float(w.cost50k_rt.median())
# where are the windows without books?
allw = pd.read_parquet(HERE / "windows.parquet")
nob = allw[~allw.window_id.isin(wm.window_id)]
t = pd.to_datetime(nob.t0, unit="ms", utc=True)
gap = ((t >= "2025-10-16 12:00") & (t < "2025-10-23")) | ((t >= "2025-11-17 13:00") & (t < "2025-11-26"))
out["no_book"] = dict(total=len(nob), in_two_archive_gaps=int(gap.sum()), elsewhere=int((~gap).sum()),
                      elsewhere_by_day={str(k): int(v) for k, v in t[~gap].dt.strftime("%Y-%m-%d").value_counts().head(10).items()})
json.dump(out, open(HERE / "causal_size.json", "w"), indent=1)
print(json.dumps({k: v for k, v in out.items() if k != "deciles_known_at_entry"}, indent=1))
for d in out["deciles_known_at_entry"]:
    print(f"d{d['decile']} known ${d['ntl_known_lo']:>11,.0f}-{d['ntl_known_hi']:>13,.0f} n {d['windows']} rev60 {d['rev60']:+.2f} rev120 {d['rev120']:+.2f} rev300 {d['rev300']:+.2f} cost {d['cost']:.2f}")
