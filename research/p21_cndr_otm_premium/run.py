"""p21 (PLAN.md): CBOE Iron Condor index (CNDR), OTM index option premium. Dev 1986-07 .. 2021-12.

  python research/p21_cndr_otm_premium/run.py              # dev
  python research/p21_cndr_otm_premium/run.py --holdout    # ONLY after review and the owner's "go"
"""
import argparse
import io
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import norm

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research/p20_spy_option_vrp"))
from harness.metrics import TrialLog, dsr, psr, tail_report  # noqa: E402

D = ROOT / "data/collector/p20"
DEV = (pd.Period("1986-07", "M"), pd.Period("2021-12", "M"))
HOLD = (pd.Period("2022-01", "M"), pd.Period("2026-08", "M"))
FEE = 0.0065
N_SIM = 2000
SEED = 0


def alpha_nw(r, x, lags=3):
    X = np.column_stack([np.ones(len(x)), x])
    b = np.linalg.lstsq(X, r, rcond=None)[0]
    e = r - X @ b
    n = len(r)
    S = np.zeros((2, 2))
    for L in range(lags + 1):
        w = 1.0 if L == 0 else 1 - L / (lags + 1)
        G = (X[L:] * e[L:, None]).T @ (X[:n - L] * e[:n - L, None]) / n
        S += w * (G if L == 0 else G + G.T)
    Q = np.linalg.inv(X.T @ X / n)
    V = Q @ S @ Q / n
    return float(b[0]), float(b[1]), float(np.sqrt(V[0, 0])), float(b[1] / np.sqrt(V[1, 1]))


def french():
    z = zipfile.ZipFile(D / "ff_factors.zip")
    txt = z.read(z.namelist()[0]).decode("latin1").splitlines()
    rows = []
    for line in txt:
        p = [x.strip() for x in line.split(",")]
        if len(p) >= 5 and len(p[0]) == 6 and p[0].isdigit():
            rows.append((pd.Period(f"{p[0][:4]}-{p[0][4:]}", "M"), float(p[1]) / 100, float(p[4]) / 100))
    f = pd.DataFrame(rows, columns=["m", "mkt_rf", "rf"]).set_index("m")
    return f[~f.index.duplicated()]


def cndr_monthly(span):
    c = pd.read_csv(D / "cboe_CNDR.csv")
    s = pd.Series(c.CNDR.astype(float).to_numpy(), pd.to_datetime(c.DATE)).sort_index()
    s = s[s.index <= span[1].to_timestamp(how="end")]                       # never reads past the span end
    me = s.groupby(s.index.to_period("M")).last()
    r = me.pct_change()
    return r[(r.index >= span[0]) & (r.index <= span[1])], s


def spy_condor_costs():
    """Per p20 dev cycle (2010-2021): the same condor on SPY at entry (|delta| ~0.20 short, ~0.05 long), cost in
    index units c = sum(half-spread + fee) / (10 * max loss)."""
    import step1 as P  # p20
    from common import load_chain_dev
    close, adj = P.yahoo()
    ch = load_chain_dev()
    ch = ch[ch.date.isin(close.index)]
    ex = P.monthly_expiries(ch, close.index)
    by_day = {d: g for d, g in ch.groupby("date")}
    out = []
    for i in range(1, len(ex)):
        prev_last, f3 = ex.last_day.iloc[i - 1], ex.f3.iloc[i]
        t = close.index[close.index > prev_last][:1]
        if not len(t) or t[0] not in by_day:
            continue
        g = by_day[t[0]]
        e = P.label_on(g, f3)
        if e is None:
            continue
        g = g[g.expiry == e]
        spot = float(g.underlying.median())
        puts = g[(g.p_bid > 0) & (g.p_bid <= g.p_ask) & (g.strike < spot)]
        calls = g[(g.c_bid > 0) & (g.c_bid <= g.c_ask) & (g.strike > spot)]
        if len(puts) < 2 or len(calls) < 2:
            continue
        sp = puts.iloc[(puts.p_delta.abs() - 0.20).abs().argsort().iloc[0]]
        lp = puts.iloc[(puts.p_delta.abs() - 0.05).abs().argsort().iloc[0]]
        sc = calls.iloc[(calls.c_delta.abs() - 0.20).abs().argsort().iloc[0]]
        lc = calls.iloc[(calls.c_delta.abs() - 0.05).abs().argsort().iloc[0]]
        if not (lp.strike < sp.strike and lc.strike > sc.strike):
            continue
        mid = lambda b, a: (b + a) / 2
        credit = mid(sp.p_bid, sp.p_ask) + mid(sc.c_bid, sc.c_ask) - mid(lp.p_bid, lp.p_ask) - mid(lc.c_bid, lc.c_ask)
        width = max(sp.strike - lp.strike, lc.strike - sc.strike)
        maxloss = width - credit
        hs = ((sp.p_ask - sp.p_bid) + (lp.p_ask - lp.p_bid) + (sc.c_ask - sc.c_bid) + (lc.c_ask - lc.c_bid)) / 2 + 4 * FEE
        if maxloss > 0:
            out.append({"entry": t[0], "credit": credit, "width": width, "maxloss": maxloss, "cost_index_units": hs / (10 * maxloss),
                        "cost_share_of_credit": hs / credit if credit > 0 else np.nan})
    return pd.DataFrame(out)


def bs(cp, S, K, T, r, sig):
    d1 = (np.log(S / K) + (r + 0.5 * sig * sig) * T) / (sig * np.sqrt(T))
    d2 = d1 - sig * np.sqrt(T)
    if cp == "c":
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def strike_for_delta(delta, S, T, r, sig, cp):
    d1 = norm.ppf(delta) if cp == "c" else norm.ppf(1 + delta)       # put delta = N(d1) - 1
    return S * np.exp(-(d1 * sig * np.sqrt(T) - (r + 0.5 * sig * sig) * T))


def condor_excess(ret_total, rf_m, sig):
    """Zero-premium condor month: options priced by BS at the simulation's own vol. Returns excess return per month."""
    T, r = 1 / 12, np.log(1 + rf_m) * 12
    S = 1.0
    Ksp, Klp = strike_for_delta(-0.20, S, T, r, sig, "p"), strike_for_delta(-0.05, S, T, r, sig, "p")
    Ksc, Klc = strike_for_delta(0.20, S, T, r, sig, "c"), strike_for_delta(0.05, S, T, r, sig, "c")
    credit = bs("p", S, Ksp, T, r, sig) + bs("c", S, Ksc, T, r, sig) - bs("p", S, Klp, T, r, sig) - bs("c", S, Klc, T, r, sig)
    maxloss = max(Ksp - Klp, Klc - Ksc) - credit
    ST = S * (1 + ret_total)
    payoff = (np.maximum(Ksp - ST, 0) - np.maximum(Klp - ST, 0) + np.maximum(ST - Ksc, 0) - np.maximum(ST - Klc, 0))
    return (credit * (1 + rf_m) - payoff) / (10 * maxloss) - rf_m * credit / (10 * maxloss)


def simulate(n_months, mu_m, sig_ann, rf_m, rng, bootstrap=None):
    alphas = []
    for _ in range(N_SIM):
        if bootstrap is None:
            lr = rng.normal(mu_m - 0.5 * sig_ann ** 2 / 12, sig_ann / np.sqrt(12), n_months)
            tot = np.exp(lr) - 1
        else:
            tot = rng.choice(bootstrap, n_months, replace=True)
        rc = condor_excess(tot, rf_m, sig_ann)
        a, _, _, _ = alpha_nw(rc, tot - rf_m)
        alphas.append(a)
    return float(np.mean(alphas)), float(np.std(alphas))


def evaluate(span, cost):
    f = french()
    r, daily = cndr_monthly(span)
    f = f.reindex(r.index)
    ok = r.notna() & f.mkt_rf.notna()
    r, f = r[ok], f[ok]
    gross = r - f.rf
    net = gross - cost
    res = {"months": int(len(net)), "cost_per_month_index_units": cost}
    for lab, s in (("gross", gross), ("net", net)):
        a, b, se, tb = alpha_nw(s.to_numpy(), f.mkt_rf.to_numpy())
        res[lab] = {"ann_mean_%": 1200 * float(s.mean()), "ann_vol_%": 100 * float(s.std(ddof=1) * np.sqrt(12)),
                    "sharpe_ann": float(s.mean() / s.std(ddof=1) * np.sqrt(12)), "alpha_ann_%": 1200 * a,
                    "alpha_t": a / se, "alpha_se_monthly": se, "beta": b, "skew": float(stats.skew(s)),
                    "worst_month_%": 100 * float(s.min()), "worst_month": str(s.idxmin())}
    res["mkt_sharpe_same_months"] = float(f.mkt_rf.mean() / f.mkt_rf.std(ddof=1) * np.sqrt(12))
    # zero-premium simulation calibrated to the span's market
    tot = (f.mkt_rf + f.rf).to_numpy()
    mu_m, sig = float(np.mean(tot)), float(np.std(tot, ddof=1) * np.sqrt(12))
    rf_m = float(f.rf.mean())
    rng = np.random.default_rng(SEED)
    m_ln, sd_ln = simulate(len(net), mu_m, sig, rf_m, rng)
    m_bs, sd_bs = simulate(len(net), mu_m, sig, rf_m, rng, bootstrap=tot)
    N = res["net"]
    se_ann = 1200 * N["alpha_se_monthly"]
    res["sim"] = {"sigma_ann": sig, "mu_month": mu_m, "rf_month": rf_m,
                  "lognormal_alpha_ann_%_mean": 1200 * m_ln, "lognormal_alpha_ann_%_sd": 1200 * sd_ln,
                  "bootstrap_alpha_ann_%_mean": 1200 * m_bs, "bootstrap_alpha_ann_%_sd": 1200 * sd_bs,
                  "excess_over_lognormal_t": (N["alpha_ann_%"] - 1200 * m_ln) / se_ann,
                  "excess_over_bootstrap_t": (N["alpha_ann_%"] - 1200 * m_bs) / se_ann}
    res["kills"] = {"k1_alpha_t_below_2": not (N["alpha_ann_%"] > 0 and N["alpha_t"] >= 2),
                    "k2_not_above_zero_premium_sim": not (res["sim"]["excess_over_lognormal_t"] >= 2),
                    "k3_sharpe_not_above_market": not (N["sharpe_ann"] > res["mkt_sharpe_same_months"])}
    res["kills"]["passes"] = not any(res["kills"].values())
    by_dec = {}
    for dec, idx in net.groupby((net.index.year // 10) * 10).groups.items():
        s, x = net.loc[idx], f.mkt_rf.loc[idx]
        a, b, se, _ = alpha_nw(s.to_numpy(), x.to_numpy())
        by_dec[f"{dec}s"] = {"months": int(len(s)), "ann_mean_%": 1200 * float(s.mean()), "alpha_ann_%": 1200 * a, "alpha_t": a / se}
    res["by_decade_net"] = by_dec
    net_ts = pd.Series(net.to_numpy(), net.index.to_timestamp(how="end"))
    res["tail_net"] = tail_report(net_ts, {"1987-10": ("1987-10-01", "1987-10-31"), "2008-10": ("2008-10-01", "2008-10-31"),
                                           "2020-03": ("2020-03-01", "2020-03-31")})
    sk, ku = float(stats.skew(net)), float(stats.kurtosis(net, fisher=False))
    sr = float(net.mean() / net.std(ddof=1))
    res["psr"] = psr(sr, len(net), sk, ku)
    return res, net


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdout", action="store_true")
    a = ap.parse_args()
    costs = spy_condor_costs()
    costs.to_csv(HERE / "spy_condor_costs.csv", index=False)
    c_med = float(costs.cost_index_units.median())
    c_q3 = float(costs.cost_index_units.quantile(0.75))
    if a.holdout:
        out = HERE / "holdout.json"
        assert not out.exists(), "holdout already run"
        res, net = evaluate(HOLD, c_med)
        TrialLog(str(ROOT / "trials_eqvol.json")).log("p21_cndr_net", pd.DataFrame({"net": net.to_numpy()}),
                                                      {"cost": c_med, "span": [str(HOLD[0]), str(HOLD[1])]})
        out.write_text(json.dumps(res, indent=1, default=str))
    else:
        res, net = evaluate(DEV, c_med)
        res["cost_stats"] = {"cycles": int(len(costs)), "median_index_units": c_med, "q3_index_units": c_q3,
                             "median_share_of_credit": float(costs.cost_share_of_credit.median())}
        res["stressed_cost_net"] = evaluate(DEV, c_q3)[0]["net"]
        (HERE / "dev.json").write_text(json.dumps(res, indent=1, default=str))
        (HERE / "selection_trials.json").write_text(json.dumps([
            {"name": "p21_cndr_net_median_cost", "kind": "rule", "sr_per_period": res["net"]["sharpe_ann"] / np.sqrt(12), "n": res["months"]},
            {"name": "p21_cndr_gross", "kind": "measurement", "sr_per_period": res["gross"]["sharpe_ann"] / np.sqrt(12), "n": res["months"]},
            {"name": "p21_cndr_net_q3_cost", "kind": "measurement", "sr_per_period": res["stressed_cost_net"]["sharpe_ann"] / np.sqrt(12), "n": res["months"]}], indent=1))
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
