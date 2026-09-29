"""p15 post-hoc descriptive numbers for RESULTS.md (review fixes). Dev only, from step1_panel.parquet.
Nothing here is a decision input; KILL C was decided by step1.py.

  python research/p15_pm_deribit_threshold/descriptive.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from common import DIR  # noqa: E402

p = pd.read_parquet(DIR / "step1_panel.parquet")
p["reason"] = np.select([p.p_rn.isna(), ~p.basis_ok.astype(bool), ~p.k_inside.astype(bool)],
                        ["no bracket/smile", "no basis", "k outside fit"], "main")
m = p[p.reason == "main"]
res = {}

res["coverage"] = p.groupby("reason").agg(rows=("D", "size"), tau_median_d=("tau_d", "median")).round(3).to_dict()
ex = p[(p.reason == "k outside fit") & (p.p_rn < 0.15)]
res["extrapolated_low_bucket"] = {"rows": int(len(ex)), "D_median_pp": round(100 * ex.D.median(), 3)}

# where the dev sample actually sits
q = m.T_utc.dt.to_period("Q").astype(str)
res["rows_by_quarter"] = q.value_counts().sort_index().to_dict()
res["markets_by_year"] = m.groupby(m.T_utc.dt.year).market_id.nunique().to_dict()
low = m[m.p_rn < 0.15]
res["low_bucket_by_year"] = {int(y): {"rows": int(len(g)), "markets": int(g.market_id.nunique()),
                                      "D_median_pp": round(100 * g.D.median(), 3)}
                             for y, g in low.groupby(low.T_utc.dt.year)}

# true first observation per market (first main-set hour of the market), then those with P_RN < 15% there
first = m.sort_values("t").groupby("market_id").first()
fl = first[first.p_rn < 0.15]
res["first_observation_low"] = {"markets": int(len(fl)), "pm_mean": round(fl.pm.mean(), 4),
                                "p_rn_mean": round(fl.p_rn.mean(), 4), "realised": round(fl.yes_gamma.mean(), 4),
                                "D_median_pp": round(100 * fl.D.median(), 3)}

# cells with >= 100 rows and median D >= 1.5 pp (to state the RESULTS claim correctly)
m = m.assign(prn_b=pd.cut(m.p_rn, [0, 0.05, 0.15, 0.35, 0.65, 0.85, 0.95, 1.0000001], right=False),
             tau_b=pd.cut(m.tau_d, [0, 1, 3, 7, np.inf], right=False))
cells = m.groupby(["prn_b", "tau_b"], observed=True).agg(rows=("D", "size"), markets=("market_id", "nunique"),
                                                         dates=("fix_date", "nunique"),
                                                         D_median_pp=("D", lambda s: 100 * s.median()))
big = cells[(cells.rows >= 100) & (cells.D_median_pp >= 1.5)].round(2)
res["cells_ge100_rows_median_ge_1p5pp"] = {f"{a} x {b}": r for (a, b), r in big.to_dict(orient="index").items()}
long = m[m.tau_d >= 7]
res["tau_ge_7d_all_buckets"] = {"rows": int(len(long)), "markets": int(long.market_id.nunique()),
                                "dates": int(long.fix_date.nunique()), "D_median_pp": round(100 * long.D.median(), 3)}

(HERE / "descriptive.json").write_text(json.dumps(res, indent=1, default=str))
print(json.dumps(res, indent=1, default=str))
