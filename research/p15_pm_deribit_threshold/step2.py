"""p15 step 2 (PLAN.md + amendment 1): Rule R on DEV, realised P&L against Gamma outcomes.

Rule R (the hypothesis, used for KILL D): per market, the FIRST decision hour t of the step-1 main set
with D >= 5 pp -> sell YES (buy NO) one unit at the first 'taker sold YES' trade in (t + 60 s, t + 60 min],
at its YES-equivalent price p; fee 0.07 p (1 - p); hold to resolution. No fill -> no trade in that market.
P&L per contract = p - fee - 1{YES}.
KILL D: mean P&L < +1.0 c per contract or t < 2 (clustered by fixing date).
Reported only: mirror buy side, theta 3 / 10 pp, entry delayed 2 h, 'first signal hour WITH a fill',
dev halves, family, tau and P_RN buckets, daily series PSR/DSR/drawdown, and the Deribit cost of hedging
the entry with a call spread (fees + half-spreads), which says whether a hedged version could exist.

  python research/p15_pm_deribit_threshold/step2.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import surface as S  # noqa: E402
from common import DIR, load_trades, split  # noqa: E402
from harness.metrics import dsr, max_drawdown, psr  # noqa: E402
from step1 import Deribit, causal_basis, basis_samples  # noqa: E402

FEE_RATE = 0.07
SEL = HERE / "selection_trials.json"


def fee(p):
    return FEE_RATE * p * (1 - p)


def cluster_stats(pnl, clusters):
    d = pd.Series(np.asarray(pnl, float)).groupby(np.asarray(clusters)).mean()
    n = len(d)
    t = d.mean() / (d.std(ddof=1) / np.sqrt(n)) if n > 2 and d.std(ddof=1) > 0 else np.nan
    return float(t), n


def run_rule(panel, trades, theta=0.05, side="sell", delay=pd.Timedelta(0), first_with_fill=False):
    """One entry per market. side 'sell': signal D >= theta, fill on a taker-sells-YES trade;
    side 'buy': signal D <= -theta, fill on a taker-buys-YES trade."""
    sig = panel[(panel.D >= theta) if side == "sell" else (panel.D <= -theta)].sort_values(["market_id", "t"])
    want = trades.taker_sells_yes if side == "sell" else ~trades.taker_sells_yes
    tr = trades[want]
    by_m = {m: g for m, g in tr.groupby("market_id")}
    rows = []
    for m, g in sig.groupby("market_id", sort=False):
        cand = g if first_with_fill else g.iloc[:1]
        mt = by_m.get(m)
        for r in cand.itertuples():
            if mt is None:
                break
            lo, hi = r.t + delay + pd.Timedelta(seconds=60), r.t + delay + pd.Timedelta(minutes=60)
            if hi > r.T_utc:                                   # never enter after the fixing
                break
            x = mt[(mt.time > lo) & (mt.time <= hi)]
            if len(x):
                f = x.iloc[0]
                p = float(f.p_yes)
                pnl = (p - fee(p) - r.yes_gamma) if side == "sell" else (r.yes_gamma - p - fee(p))
                rows.append({"market_id": m, "t_signal": r.t, "t_fill": f.time, "p": p, "fee": fee(p), "pnl": pnl,
                             "D": r.D, "p_rn": r.p_rn, "pm": r.pm, "yes": r.yes_gamma, "T_utc": r.T_utc,
                             "fix_date": r.fix_date, "family": r.family, "kind": r.kind, "tau_d": r.tau_d})
                break
    return pd.DataFrame(rows)


def summarise(tr, label):
    if tr.empty:
        return {"label": label, "trades": 0}
    t, n_dates = cluster_stats(tr.pnl, tr.fix_date)
    return {"label": label, "trades": int(len(tr)), "markets": int(tr.market_id.nunique()), "dates": n_dates,
            "mean_pnl_c": 100 * float(tr.pnl.mean()), "median_pnl_c": 100 * float(tr.pnl.median()),
            "t_by_date": t, "win_share": float((tr.pnl > 0).mean()), "mean_entry_p": float(tr.p.mean()),
            "mean_fee_c": 100 * float(tr.fee.mean()), "mean_D_pp": 100 * float(tr.D.mean()),
            "realised_yes": float(tr.yes.mean()), "mean_p_rn": float(tr.p_rn.mean())}


def daily_series(tr, s):
    """P&L per ET fixing date (unit size), zero on dev days without a resolution."""
    days = pd.date_range(s["dev_start"].tz_convert("America/New_York").date(),
                         (s["dev_end"] - pd.Timedelta(days=1)).tz_convert("America/New_York").date(), freq="D")
    d = tr.groupby(pd.to_datetime(tr.fix_date)).pnl.sum().reindex(days, fill_value=0.0)
    first = pd.to_datetime(tr.fix_date).min()
    return d[d.index >= first]


def hedge_cost(tr, delta=0.02):
    """Deribit cost (USD per $1 digital) of buying the call spread [K_D(1-delta), K_D(1+delta)] on the first
    expiry >= T at the signal hour: per leg min(0.03% F, 12.5% premium) fee + half-spread (median
    |trade - mark| of that expiry's trades in the window), times 1/(K2 - K1) options. Range markets
    ('between') need two spreads. Reported only."""
    der, (bt, bv) = Deribit(), basis_samples()
    out = []
    for r in tr.itertuples():
        w = der.window(r.t_signal)
        sm = S.smiles_at(w, r.t_signal) if w is not None and len(w) else []
        tau_T = (r.T_utc - r.t_signal).total_seconds() / S.YEAR
        after = [x for x in sm if x.tau >= tau_T]
        if not after:
            out.append(np.nan)
            continue
        s2 = after[0]
        ix = float(w.index_price.iloc[-1])
        F = ix * s2.f_ratio
        b = causal_basis(bt, bv, r.t_signal)
        b = 0.0 if not np.isfinite(b) else b
        we = w[w.expiry == s2.expiry]
        hs_usd = float(np.median(np.abs(we.price - we.mark_price))) * F if len(we) else np.nan
        strikes = {"above": [r.K_low], "below": [r.K_high], "between": [r.K_low, r.K_high]}[r.kind]
        cost = 0.0
        for K in strikes:
            KD = K * (1 + b)
            K1, K2 = KD * (1 - delta), KD * (1 + delta)
            for Kx in (K1, K2):
                k = np.log(Kx / F)
                wk = s2.w(k)
                prem = F * S.fwd_price("C", k, np.sqrt(max(wk, 1e-12)))
                cost += (min(0.0003 * F, 0.125 * prem) + hs_usd) / (K2 - K1)
        out.append(cost)
    return np.array(out)


def log_selection(rows):
    old = json.loads(SEL.read_text()) if SEL.exists() else []
    SEL.write_text(json.dumps(old + rows, indent=1, default=str))


def main():
    s = split()
    panel = pd.read_parquet(DIR / "step1_panel.parquet")
    assert (panel.T_utc < s["dev_end"]).all()
    main_set = panel[panel.p_rn.notna() & panel.k_inside & panel.basis_ok].copy()
    inv = pd.read_parquet(DIR / "inventory.parquet")[["id", "k_low", "k_high"]].astype({"id": str})
    main_set = main_set.merge(inv.rename(columns={"id": "market_id", "k_low": "K_low", "k_high": "K_high"}),
                              on="market_id", how="left")
    trades = load_trades(dev_only=True)
    res, sel_rows = {}, []

    configs = [("R_sell_theta5", dict(theta=0.05, side="sell")),
               ("buy_theta5", dict(theta=0.05, side="buy")),
               ("sell_theta3", dict(theta=0.03, side="sell")),
               ("sell_theta10", dict(theta=0.10, side="sell")),
               ("sell_theta5_delay2h", dict(theta=0.05, side="sell", delay=pd.Timedelta(hours=2))),
               ("sell_theta5_first_with_fill", dict(theta=0.05, side="sell", first_with_fill=True))]
    books = {}
    for name, kw in configs:
        tr = run_rule(main_set, trades, **kw)
        books[name] = tr
        res[name] = summarise(tr, name)
        if len(tr):
            dly = daily_series(tr, s)
            sel_rows.append({"name": f"p15_{name}", "kind": "rule" if name == "R_sell_theta5" else "measurement",
                             "params": {k: str(v) for k, v in kw.items()},
                             "sr_per_period": float(dly.mean() / dly.std(ddof=1)) if dly.std(ddof=1) > 0 else 0.0,
                             "n": int(len(dly))})
        print(json.dumps(res[name]), flush=True)

    R = books["R_sell_theta5"]
    kill = res["R_sell_theta5"]
    kill_D = bool(kill.get("trades", 0) == 0 or kill["mean_pnl_c"] < 1.0 or not (kill["t_by_date"] >= 2))
    res["kill_D"] = {"mean_pnl_c": kill.get("mean_pnl_c"), "t_by_date": kill.get("t_by_date"),
                     "threshold": "mean >= +1.0 c and t >= 2", "fires": kill_D}
    if len(R):
        mid = pd.Timestamp(s["dev_start"]) + (pd.Timestamp(s["dev_end"]) - pd.Timestamp(s["dev_start"])) / 2
        res["halves"] = {"first": summarise(R[R.T_utc < mid], "first half"), "second": summarise(R[R.T_utc >= mid], "second half")}
        res["by_family"] = {f: summarise(g, f) for f, g in R.groupby("family")}
        res["by_tau"] = {str(b): summarise(g, str(b)) for b, g in R.groupby(pd.cut(R.tau_d, [0, 1, 3, 7, np.inf]), observed=True)}
        res["by_p_rn"] = {str(b): summarise(g, str(b)) for b, g in
                          R.groupby(pd.cut(R.p_rn, [0, 0.05, 0.15, 0.35, 0.65, 1.0]), observed=True)}
        dly = daily_series(R, s)
        sr = float(dly.mean() / dly.std(ddof=1))
        sk, ku = float(stats.skew(dly)), float(stats.kurtosis(dly, fisher=False))
        all_sel = (json.loads(SEL.read_text()) if SEL.exists() else []) + sel_rows
        trials_pm = json.loads(Path("trials_pm.json").read_text()) if Path("trials_pm.json").exists() else []
        srs = [r["sr_per_period"] for r in all_sel + trials_pm]
        n_trials = len(srs)
        var_sr = float(np.var(srs, ddof=1)) if n_trials > 1 else 0.0
        eq = dly.cumsum()
        res["daily"] = {"days": int(len(dly)), "sr_daily": sr, "sr_annual": sr * np.sqrt(365), "skew": sk, "kurt": ku,
                        "psr": psr(sr, len(dly), sk, ku), "dsr": dsr(sr, len(dly), sk, ku, n_trials, var_sr),
                        "n_trials_for_dsr": n_trials, "total_pnl_usd_unit": float(eq.iloc[-1]),
                        "max_drawdown_usd_unit": float((eq - eq.cummax()).min()),
                        "worst_5_dates": dly.nsmallest(5).round(3).to_dict()}
        # robustness (reported; failures stated)
        d2 = res["sell_theta5_delay2h"]
        res["robustness"] = {"halves_same_sign": bool(np.sign(res["halves"]["first"].get("mean_pnl_c", 0)) ==
                                                      np.sign(res["halves"]["second"].get("mean_pnl_c", 0))),
                             "delay2h_same_sign": bool(np.sign(d2.get("mean_pnl_c", 0)) == np.sign(kill["mean_pnl_c"]))}
        hc = hedge_cost(R)
        R = R.assign(hedge_cost=hc, gap_at_entry=R.p - R.p_rn)
        ok = np.isfinite(hc)
        res["hedge"] = {"rows": int(ok.sum()), "median_hedge_cost_c": 100 * float(np.median(hc[ok])) if ok.any() else None,
                        "median_gap_at_entry_pp": 100 * float(R.gap_at_entry.median()),
                        "median_gap_minus_pm_fee_minus_hedge_c": 100 * float((R.gap_at_entry - R.fee - R.hedge_cost)[ok].median()) if ok.any() else None,
                        "share_positive_after_costs": float(((R.gap_at_entry - R.fee - R.hedge_cost)[ok] > 0).mean()) if ok.any() else None}
        R.to_parquet(DIR / "step2_rule_R_trades.parquet")
    log_selection(sel_rows)
    (HERE / "step2.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({k: res[k] for k in res if k in ("kill_D", "halves", "daily", "robustness", "hedge")}, indent=1, default=str))


if __name__ == "__main__":
    main()
