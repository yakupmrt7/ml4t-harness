"""p20 step 1 (PLAN + amendments 1-2): unconditional books on DEV cycles (settlement 2010-02 .. 2021-12).

  python research/p20_spy_option_vrp/step1.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
from common import DEV_END, DIR, load_chain_dev  # noqa: E402
from harness.metrics import dsr, psr, tail_report  # noqa: E402

FEE = 0.0065                         # $ per share per leg (IBKR $0.65 / contract)
HEDGE_COST = 1e-4
STRESS = {"2011-08": ("2011-08-01", "2011-09-30"), "2015-08": ("2015-08-01", "2015-09-30"),
          "2018-02": ("2018-02-01", "2018-03-31"), "2020-03": ("2020-02-15", "2020-04-30")}


def yahoo():
    d = json.load(open(DIR / "spy_yahoo.json"))["chart"]["result"][0]
    idx = pd.to_datetime(d["timestamp"], unit="s").normalize()
    close = pd.Series(d["indicators"]["quote"][0]["close"], idx).dropna()
    adj = pd.Series(d["indicators"]["adjclose"][0]["adjclose"], idx).dropna()
    return close[close.index <= DEV_END], adj[adj.index <= DEV_END]


def tbill_daily(idx):
    f = pd.read_csv(DIR / "dtb3.csv", na_values=".")
    s = pd.Series(pd.to_numeric(f.DTB3, errors="coerce").to_numpy() / 100,
                  pd.to_datetime(f.observation_date)).ffill()
    return s.reindex(idx, method="ffill")


def monthly_expiries(ch, trading_days):
    """-> DataFrame(expiry label date in the chain, last trading day) per month."""
    ex = pd.Series(sorted(ch.expiry.unique()))
    rows = []
    for (y, m), g in ex.groupby([ex.dt.year, ex.dt.month]):
        fridays = pd.date_range(f"{y}-{m:02d}-01", periods=31, freq="D")
        fridays = fridays[(fridays.month == m) & (fridays.dayofweek == 4)]
        f3 = fridays[2]
        cand = [d for d in g if d in (f3, f3 + pd.Timedelta(days=1), f3 - pd.Timedelta(days=1))]
        if not cand:
            continue
        e = cand[0]
        last = trading_days[trading_days <= min(e, f3)].max()
        rows.append((e, last))
    return pd.DataFrame(rows, columns=["expiry", "last_day"])


def valid_puts(day_rows):
    return day_rows[(day_rows.p_bid > 0) & (day_rows.p_bid <= day_rows.p_ask)]


def nearest(df, target):
    return df.iloc[(df.strike - target).abs().argsort().iloc[0]]


def build_cycles(ch, close, adj, rf):
    days = close.index
    ch = ch[ch.date.isin(days)]                          # amendment 1: drop non-trading-day rows
    ex = monthly_expiries(ch, days)
    by_day = {d: g for d, g in ch.groupby("date")}
    out = []
    for i in range(1, len(ex)):
        prev_last, e, last = ex.last_day.iloc[i - 1], ex.expiry.iloc[i], ex.last_day.iloc[i]
        if last > DEV_END or last < pd.Timestamp("2010-02-01"):
            continue
        entries = days[days > prev_last][:4]
        rec = None
        for k, t in enumerate(entries[:3]):                # up to 3 tries (amendment 1)
            g = by_day.get(t)
            if g is None:
                continue
            g = g[g.expiry == e]
            vp = valid_puts(g)
            if len(vp) < 2:
                continue
            spot = float(g.underlying.median())
            s1 = nearest(vp, spot)
            s2 = nearest(vp[vp.strike < s1.strike], 0.90 * spot) if (vp.strike < s1.strike).any() else None
            s5 = nearest(vp[vp.strike < s1.strike], 0.95 * spot) if (vp.strike < s1.strike).any() else None
            if s2 is None:
                continue
            rec = {"entry": t, "entry_try": k, "expiry": e, "last_day": last, "spot": spot, "K1": s1.strike,
                   "K2": s2.strike, "K5": s5.strike, "p1_bid": s1.p_bid, "p1_ask": s1.p_ask, "p2_bid": s2.p_bid,
                   "p2_ask": s2.p_ask, "p5_bid": s5.p_bid, "p5_ask": s5.p_ask, "iv_atm": np.nanmean([s1.p_iv, s1.c_iv]),
                   "c1_bid": s1.c_bid, "c1_ask": s1.c_ask}
            # entry one trading day later (reported variant)
            t2 = entries[k + 1] if k + 1 < len(entries) else None
            g2 = by_day.get(t2)
            if g2 is not None:
                g2 = valid_puts(g2[g2.expiry == e])
                if len(g2) >= 2:
                    sp2 = float(by_day[t2].underlying.median())
                    a = nearest(g2, sp2)
                    lo = g2[g2.strike < a.strike]
                    if len(lo):
                        b = nearest(lo, 0.90 * sp2)
                        rec.update({"d2_K1": a.strike, "d2_K2": b.strike, "d2_credit": a.p_bid - b.p_ask})
            break
        if rec is None:
            out.append({"expiry": e, "last_day": last, "skipped": True})
            continue
        S_T = float(close.loc[last])
        rec["S_T"] = S_T
        window = days[(days >= rec["entry"]) & (days <= last)]
        spy_tr = float(adj.loc[last] / adj.loc[rec["entry"]] - 1)
        rf_c = float(np.prod(1 + rf.loc[window[1:]].to_numpy() / 360 * np.diff(window).astype("timedelta64[D]").astype(float)) - 1)
        rec["spy_excess"] = spy_tr - rf_c
        rec["rf_cycle"] = rf_c
        # delta-hedged ATM straddle (reported)
        px = close.loc[window]
        K, sig = rec["K1"], rec["iv_atm"]
        hedge_pnl, hedge_cost, prev = 0.0, 0.0, 0.0
        for j in range(len(px) - 1):
            tau = max((last - px.index[j]).days, 1) / 365
            d1 = (np.log(px.iloc[j] / K) + 0.5 * sig * sig * tau) / (sig * np.sqrt(tau))
            h = 2 * norm.cdf(d1) - 1
            hedge_cost += HEDGE_COST * abs(h - prev) * px.iloc[j]
            hedge_pnl += h * (px.iloc[j + 1] - px.iloc[j])
            prev = h
        hedge_cost += HEDGE_COST * abs(prev) * px.iloc[-1]
        rec["straddle_premium"] = rec["p1_bid"] + rec["c1_bid"]
        rec["straddle_pnl"] = rec["straddle_premium"] - abs(S_T - K) + hedge_pnl - hedge_cost - 2 * FEE
        out.append(rec)
    return pd.DataFrame(out)


def books(c):
    ok = c[~c.get("skipped", pd.Series(False, index=c.index)).fillna(False).astype(bool)].copy()
    pay = lambda K: np.maximum(K - ok.S_T, 0)
    w = ok.K1 - ok.K2
    ok["r_P"] = (ok.p1_bid - ok.p2_ask - 2 * FEE - (pay(ok.K1) - pay(ok.K2))) / w
    ok["r_P_mid"] = ((ok.p1_bid + ok.p1_ask) / 2 - (ok.p2_bid + ok.p2_ask) / 2 - 2 * FEE - (pay(ok.K1) - pay(ok.K2))) / w
    w5 = ok.K1 - ok.K5
    ok["r_P5"] = (ok.p1_bid - ok.p5_ask - 2 * FEE - (pay(ok.K1) - pay(ok.K5))) / w5
    ok["r_CSP"] = (ok.p1_bid - FEE - pay(ok.K1)) / ok.K1
    if "d2_credit" in ok:
        wd = ok.d2_K1 - ok.d2_K2
        ok["r_P_delay1"] = (ok.d2_credit - 2 * FEE - (pay(ok.d2_K1) - pay(ok.d2_K2))) / wd
    ok["straddle_pct_premium"] = ok.straddle_pnl / ok.straddle_premium
    ok["straddle_per_spot"] = ok.straddle_pnl / ok.spot
    return ok.set_index("last_day")


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
    return float(b[0]), float(b[1]), float(b[0] / np.sqrt(V[0, 0])), float(b[1] / np.sqrt(V[1, 1]))


def summarize(r, x, label):
    r = r.dropna()
    xx = x.reindex(r.index)
    a, beta, ta, tb = alpha_nw(r.to_numpy(), xx.to_numpy())
    from scipy import stats
    sr = float(r.mean() / r.std(ddof=1))
    return {"label": label, "cycles": int(len(r)), "ann_mean_%": 1200 * float(r.mean()), "ann_vol_%": 100 * float(r.std(ddof=1) * np.sqrt(12)),
            "sharpe_ann": sr * np.sqrt(12), "t_mean": float(r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))),
            "alpha_ann_%": 1200 * a, "alpha_t_nw": ta, "beta": beta, "beta_t": tb, "skew": float(stats.skew(r)),
            "kurt": float(stats.kurtosis(r, fisher=False)), "worst_cycle_%": 100 * float(r.min()),
            "worst_cycle": str(r.idxmin().date()), "hit": float((r > 0).mean())}


def main():
    close, adj = yahoo()
    rf = tbill_daily(close.index)
    ch = load_chain_dev()
    c = build_cycles(ch, close, adj, rf)
    b = books(c)
    b.to_csv(HERE / "step1_cycles.csv")
    x = b.spy_excess
    res = {"cycles_total": int(len(c)), "cycles_skipped": int(c.get("skipped", pd.Series(dtype=bool)).fillna(False).sum()),
           "entries_delayed": int((b.entry_try > 0).sum())}
    for col, lab in (("r_P", "P (put spread 100/90, taker)"), ("r_P_mid", "P at mid"), ("r_P5", "put spread 100/95"),
                     ("r_CSP", "cash-secured ATM put"), ("r_P_delay1", "P entry +1 day"),
                     ("straddle_per_spot", "delta-hedged ATM straddle, per spot")):
        if col in b:
            res[col] = summarize(b[col], x, lab)
    res["straddle_mean_pct_premium"] = 100 * float(b.straddle_pct_premium.mean())
    res["spy_excess"] = summarize(x, x, "SPY excess (reference)")
    # CBOE PUT index over the same cycles, minus T-bill
    p = pd.read_csv(DIR / "cboe_PUT.csv")
    p.index = pd.to_datetime(p.DATE)
    put = p.PUT.astype(float)
    pr = [float(put.asof(r.Index) / put.asof(r.entry) - 1 - r.rf_cycle) for r in b.itertuples()]
    res["cboe_PUT_excess"] = summarize(pd.Series(pr, b.index), x, "CBOE PUT index minus T-bill")
    tr = tail_report(b.r_P, STRESS)
    res["tail_P"] = tr
    P = res["r_P"]
    res["kills"] = {"k1_ann_mean_below_3": P["ann_mean_%"] < 3.0, "k2_alpha_not_positive_or_t_below_2":
                    not (P["alpha_ann_%"] > 0 and P["alpha_t_nw"] >= 2)}
    res["kills"]["P_passes"] = not any(res["kills"].values())
    rows = [{"name": f"p20_{k}", "kind": "rule" if k == "r_P" else "measurement", "sr_per_period": res[k]["sharpe_ann"] / np.sqrt(12),
             "n": res[k]["cycles"]} for k in ("r_P", "r_P_mid", "r_P5", "r_CSP", "r_P_delay1", "straddle_per_spot") if k in res]
    srs = [r["sr_per_period"] for r in rows]
    rP = b.r_P.dropna()
    from scipy import stats
    res["psr_P"] = psr(P["sharpe_ann"] / np.sqrt(12), len(rP), float(stats.skew(rP)), float(stats.kurtosis(rP, fisher=False)))
    res["dsr_P"] = dsr(P["sharpe_ann"] / np.sqrt(12), len(rP), float(stats.skew(rP)), float(stats.kurtosis(rP, fisher=False)),
                       len(srs), float(np.var(srs, ddof=1)))
    (HERE / "selection_trials.json").write_text(json.dumps(rows, indent=1))
    (HERE / "step1.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
