"""p20 step 2 (PLAN + amendment 2): ML volatility timing of book P, DEV walk-forward (test years 2013..2021).

  python research/p20_spy_option_vrp/step2.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier, LGBMRegressor
from sklearn.model_selection import KFold, cross_val_score

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
from common import DEV_END, DIR  # noqa: E402
from step1 import alpha_nw, summarize, yahoo  # noqa: E402

H = 21
LGB = dict(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=200, subsample=0.7, subsample_freq=1,
           colsample_bytree=0.7, reg_lambda=5.0, random_state=0, verbose=-1)
FEATS = ["f_rv5_21", "f_rv63_21", "z_rv21", "z_vix", "f_term", "f_iv_rv"]
HAR = ["f_rv5_21", "f_rv63_21"]


def cboe(sym):
    d = pd.read_csv(DIR / f"cboe_{sym}.csv")
    return pd.Series(d.CLOSE.astype(float).to_numpy(), pd.to_datetime(d.DATE))


def features():
    close, adj = yahoo()
    lr = np.log(adj).diff()
    sq = lr ** 2
    rv = {k: sq.rolling(k).mean() * 252 for k in (5, 21, 63)}                 # annualised variance, trailing
    fwd = sq[::-1].rolling(H).mean()[::-1].shift(-1) * 252                     # next H days (t+1..t+H)
    vix, vix3m = cboe("VIX").reindex(adj.index).ffill(), cboe("VIX3M").reindex(adj.index).ffill()

    def z(x, w=252):
        return (x - x.rolling(w, min_periods=200).mean()) / x.rolling(w, min_periods=200).std()

    f = pd.DataFrame(index=adj.index)
    f["f_rv5_21"] = np.log(rv[5] / rv[21])
    f["f_rv63_21"] = np.log(rv[63] / rv[21])
    f["z_rv21"] = z(np.log(rv[21]))
    f["z_vix"] = z(np.log(vix))
    f["f_term"] = np.log(vix3m / vix)
    f["f_iv_rv"] = np.log((vix / 100) ** 2 / rv[21])
    f["rv21"] = rv[21]
    f["y"] = np.log(fwd / rv[21])
    f["target_end"] = pd.Series(adj.index, adj.index).shift(-H)               # last day of the target window
    return f[f.index <= DEV_END]


def qlike(real, fc):
    x = real / fc
    return x - np.log(x) - 1


def main():
    f = features()
    cyc = pd.read_csv(HERE / "step1_cycles.csv", parse_dates=["last_day", "entry"]).set_index("last_day")
    close, adj = yahoo()
    lr = np.log(adj).diff()
    rows = []
    for yr in range(2013, 2022):
        start = pd.Timestamp(f"{yr}-01-01")
        tr = f[(f.index < start) & (f.target_end < start)].dropna(subset=FEATS + ["y"])     # purged
        har = np.linalg.lstsq(np.column_stack([np.ones(len(tr)), tr[HAR]]), tr.y, rcond=None)[0]
        gbm = LGBMRegressor(**LGB).fit(tr[FEATS], tr.y)
        for last, c in cyc[(cyc.index >= start) & (cyc.index < pd.Timestamp(f"{yr + 1}-01-01"))].iterrows():
            x = f.loc[c.entry]
            if x[FEATS].isna().any():
                continue
            p_har = float(har[0] + har[1:] @ x[HAR].to_numpy())
            p_gbm = float(gbm.predict(x[FEATS].to_frame().T)[0])
            win = lr[(lr.index > c.entry) & (lr.index <= last)]
            real = float((win ** 2).mean() * 252)
            rows.append({"last_day": last, "year": yr, "entry": c.entry, "iv2": float(c.iv_atm) ** 2, "rv21": float(x.rv21),
                         "fc_har": float(x.rv21 * np.exp(p_har)), "fc_gbm": float(x.rv21 * np.exp(p_gbm)), "real": real,
                         "r_P": float(c.r_P), "spy_excess": float(c.spy_excess)})
    d = pd.DataFrame(rows).set_index("last_day")
    d["q_har"], d["q_gbm"] = qlike(d.real, d.fc_har), qlike(d.real, d.fc_gbm)
    diff = d.q_gbm - d.q_har
    res = {"oos_cycles": int(len(d)), "qlike_har": float(d.q_har.mean()), "qlike_gbm": float(d.q_gbm.mean()),
           "qlike_gbm_minus_har_t": float(diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff))))}
    res["a_gbm_beats_har"] = bool(res["qlike_gbm"] < res["qlike_har"])
    use = "fc_gbm" if res["a_gbm_beats_har"] else "fc_har"
    res["model_used"] = use
    d["trade"] = d.iv2 - d[use] > 0
    d["r_timed"] = np.where(d.trade, d.r_P, 0.0)
    res["share_cycles_traded"] = float(d.trade.mean())
    res["unconditional_P_oos"] = summarize(d.r_P, d.spy_excess, "P, 2013-2021 cycles")
    res["timed_P_oos"] = summarize(pd.Series(d.r_timed, d.index), d.spy_excess, f"timed P ({use})")
    dd = d.r_timed - d.r_P
    res["paired_diff_ann_%"] = 1200 * float(dd.mean())
    res["paired_t"] = float(dd.mean() / (dd.std(ddof=1) / np.sqrt(len(dd))))
    T = res["timed_P_oos"]
    res["kills"] = {"a_ml_adds_nothing_to_forecast": not res["a_gbm_beats_har"],
                    "b_timed_fails_k1": T["ann_mean_%"] < 3.0,
                    "b_timed_fails_k2": not (T["alpha_ann_%"] > 0 and T["alpha_t_nw"] >= 2),
                    "b_timing_not_better_paired_t_below_2": not (res["paired_t"] >= 2)}
    res["kills"]["timed_passes"] = not (res["kills"]["b_timed_fails_k1"] or res["kills"]["b_timed_fails_k2"] or
                                        res["kills"]["b_timing_not_better_paired_t_below_2"])
    # rule 10: can the features identify the year?
    fy = f[(f.index >= "2013-01-01")].dropna(subset=FEATS)
    acc = cross_val_score(LGBMClassifier(**LGB), fy[FEATS], fy.index.year, cv=KFold(5, shuffle=True, random_state=0))
    res["fold_id_accuracy"] = float(acc.mean())
    res["fold_id_chance"] = 1 / 9
    # also: timing with the other model and a plain VIX-based rule (reported)
    other = "fc_har" if use == "fc_gbm" else "fc_gbm"
    res["timed_other_model"] = summarize(pd.Series(np.where(d.iv2 - d[other] > 0, d.r_P, 0.0), d.index), d.spy_excess,
                                         f"timed P ({other}), reported")
    d.to_csv(HERE / "step2_cycles.csv")
    sel = json.loads((HERE / "selection_trials.json").read_text())
    sel += [{"name": "p20_timed_P", "kind": "rule", "sr_per_period": T["sharpe_ann"] / np.sqrt(12), "n": T["cycles"]},
            {"name": "p20_timed_P_other_model", "kind": "measurement",
             "sr_per_period": res["timed_other_model"]["sharpe_ann"] / np.sqrt(12), "n": res["timed_other_model"]["cycles"]}]
    (HERE / "selection_trials.json").write_text(json.dumps(sel, indent=1))
    (HERE / "step2.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
