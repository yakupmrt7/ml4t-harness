"""p17 descriptive tables and robust t-stats at the VERIFIED fee (0.07) and with no rebate (review fixes).
Not a decision input: the kill is in step1.py / RESULTS.md.

  python research/p17_pm_maker_bound/descriptive.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from step1 import REBATE_SHARE, markets, trades  # noqa: E402

m = markets()
m = m[m.found & m.up.notna()].set_index("slug")
t, _ = trades()
t = t[t.slug.isin(m.index)].join(m[["up", "start"]], on="slug")
t["maker"] = np.where(t.taker_buys_up, t.p_up - t.up, t.up - t.p_up) * t["size"]
t["rebate07"] = REBATE_SHARE * 0.07 * t.p_up * (1 - t.p_up) * t["size"]
t["to_end_s"] = (t.start + pd.Timedelta(seconds=300) - t.time).dt.total_seconds()
t["usd"] = t["size"] * np.where(t.taker_buys_up, t.p_up, 1 - t.p_up)       # dollars the taker paid


def per_market(x, col):
    g = x.groupby("slug")
    return g[col].sum() / g["size"].sum()


def tstat(s):
    s = s.dropna()
    return float(s.mean() / (s.std(ddof=1) / np.sqrt(len(s)))) if len(s) > 2 else np.nan


def newey_west_t(s, lags=5):
    s = s.dropna().to_numpy()
    e = s - s.mean()
    n = len(e)
    v = e @ e / n
    for L in range(1, lags + 1):
        v += 2 * (1 - L / (lags + 1)) * (e[L:] @ e[:-L]) / n
    return float(s.mean() / np.sqrt(v / n))


out = {}
for name, col in (("fee_0.07", "net07"), ("no_rebate", "maker")):
    t["net07"] = t.maker + t.rebate07
    pm = per_market(t, col).reindex(m.index).sort_index()
    byday = pm.groupby(m.start.dt.date).mean()
    out[name] = {"bound_c_equal_weight": 100 * float(pm.mean()), "t_iid_by_market": tstat(pm),
                 "t_newey_west_5": newey_west_t(pm, 5), "t_newey_west_12": newey_west_t(pm, 12),
                 "t_clustered_by_day": tstat(byday), "lag1_autocorr": float(pm.autocorr(1)),
                 "share_weighted_c": 100 * float(t[col].sum() / t["size"].sum()),
                 "share_weighted_t_by_market": tstat(t.groupby("slug")[col].sum() / t.groupby("slug")["size"].sum().mean()),
                 "usd_per_day": float(t[col].sum() / 8)}
    tables = {}
    for tab, cut in (("time_to_end_s", pd.cut(t.to_end_s, [-np.inf, 0, 60, 180, 300, np.inf],
                                             labels=["after end", "last 60 s", "60-180 s", "180-300 s", "before window"])),
                     ("price_up", pd.cut(t.p_up, [0, 0.05, 0.2, 0.4, 0.6, 0.8, 0.95, 1.0])),
                     ("size_shares", pd.cut(t["size"], [0, 10, 100, 1000, np.inf])),
                     ("size_usd", pd.cut(t.usd, [0, 10, 100, 1000, np.inf]))):
        rows = {}
        for k, x in t.groupby(cut, observed=True):
            rows[str(k)] = {"share_of_volume": round(float(x["size"].sum() / t["size"].sum()), 4),
                            "c_per_share": round(100 * float(x[col].sum() / x["size"].sum()), 3),
                            "t_by_market": round(tstat(per_market(x, col)), 2)}
        tables[tab] = rows
    out[name]["tables"] = tables
big = t[t["size"] > 1000]
out["gt1000_shares_at_extremes_share"] = float(big.loc[(big.p_up <= 0.05) | (big.p_up >= 0.95), "size"].sum() / big["size"].sum())
(HERE / "descriptive.json").write_text(json.dumps(out, indent=1, default=str))
print(json.dumps(out, indent=1, default=str))
