"""p13 figure input: the signed HL mid path around a liquidation, aggregated (dev, cadence-ok windows).
Reads the gitignored mids1s.npz / window_metrics.parquet / causal_size inputs and writes a small
committed CSV: event_path.csv (second, group, median_bps, p25_bps, p75_bps, mean_bps, n).
Path = s x (mid(t0 + τ) / mid(t0) - 1) in bps, τ = -60..300 s; > 0 = further in the liquidation's push
direction. Groups: all; top decile by liquidated notional known at entry (t0 + 2 s)."""
import pathlib
import numpy as np, pandas as pd
from events import clusters

HERE = pathlib.Path(__file__).parent
z = np.load(HERE / "mids1s.npz"); ids, mids = z["ids"], z["mids"]
wm = pd.read_parquet(HERE / "window_metrics.parquet").set_index("window_id")
ok = wm.index[wm.max_gap_ms <= 2000]
ev = pd.read_parquet(HERE / "events.parquet"); ev = ev[ev.method == "market"].sort_values("t0").reset_index(drop=True)
ev["cluster"] = clusters(ev.t0.to_numpy(), 60)
m = wm.loc[ok, ["cluster", "coin", "t0"]].reset_index().merge(
    ev[["cluster", "coin", "t0", "ntl"]].rename(columns={"t0": "te"}), on=["cluster", "coin"])
known = m[m.te <= m.t0 + 2000].groupby("window_id").ntl.sum().reindex(ok).fillna(0)
top = set(known[known >= known.quantile(0.9)].index)
pos = {w: i for i, w in enumerate(ids)}
sel = [w for w in ok if w in pos]
s = wm.loc[sel, "s"].to_numpy()
P = mids[[pos[w] for w in sel]]
path = s[:, None] * (P / P[:, [60]] - 1) * 1e4
rows = []
for name, mask in (("all", np.ones(len(sel), bool)), ("top_known_decile", np.array([w in top for w in sel]))):
    x = path[mask]
    for j, tau in enumerate(range(-60, 301)):
        c = x[:, j]
        rows.append(dict(second=tau, group=name, median_bps=np.median(c), p25_bps=np.percentile(c, 25),
                         p75_bps=np.percentile(c, 75), mean_bps=c.mean(), n=len(c)))
pd.DataFrame(rows).to_csv(HERE / "event_path.csv", index=False, float_format="%.4f")
print(pd.DataFrame(rows).query("second in (-60,-30,0,2,60,120,300)"))
