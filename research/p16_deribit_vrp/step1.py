"""p16 step 1 (PLAN.md + amendment 1): weekly short 7-day ATM straddle, delta-hedged daily, DEV ONLY.

Per entry Friday f (dev): at t0 = f 08:05 UTC sell the ATM straddle of the expiry f + 7 d at Deribit mark minus
the measured half-spread, pay option fees, convert the premium to USD; hedge in the Binance BTCUSDT perp at t0 and
daily at 08:05 with the Black-76 straddle delta at entry IV; settle on the official delivery price; delivery fee on
the ITM leg; hedge closed at the expiry-Friday 08:00 bar; funding on the hedge.
P&L in USD per 1 BTC of notional per leg; normalised by premium and by S_entry.
Kills (dev, net, main config): mean P&L < 2% of premium; t (return on notional, weekly) < 2; worst week loss
> 12 x mean weekly P&L.

  python research/p16_deribit_vrp/step1.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import norm

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
from common import DIR, S, SMILE_WINDOW, deribit_day, delivery_prices, fridays  # noqa: E402
from harness.data import load_binance_klines, load_funding  # noqa: E402
from harness.metrics import dsr, psr, tail_report  # noqa: E402

YEAR = S.YEAR
TAKER_HEDGE = 5.5e-4
CONVERT = 5.5e-4
OPT_FEE, OPT_CAP = 3e-4, 0.125
DELIV_FEE = 1.5e-4
STRESSED_H = 0.015
STRESS = {"FTX_2022-11-04": ("2022-11-04", "2022-11-04"), "SVB_2023-03": ("2023-03-03", "2023-03-10"),
          "unwind_2024-08-02": ("2024-08-02", "2024-08-02")}
SEL = HERE / "selection_trials.json"


def dev_fridays():
    s = json.loads((HERE / "split.json").read_text())
    cut = pd.Timestamp(s["dev_end"])
    out = [f for f in fridays() if f < cut]      # last dev expiry = first holdout entry: no overlap of positions
    return out, cut


def smile_for(t, expiry):
    """Smile of `expiry` from mark prices of its trades in (t - 60 min, t]; also the index at t."""
    days = sorted({(t - SMILE_WINDOW).date(), t.date()})
    parts = [p for p in (deribit_day(str(d)) for d in days) if p is not None]
    if not parts:
        return None, np.nan, []
    x = pd.concat(parts)
    ex = x[(x.expiry == expiry) & (x.t <= t)]
    w = ex[ex.t > t - SMILE_WINDOW]
    sm = S.fit_smile(w, t) if len(w) else None
    idx = float(x[x.t <= t].index_price.iloc[-1]) if (x.t <= t).any() else np.nan
    traded = ex[ex.t.dt.date == t.date()].K.unique()
    return sm, idx, traded


def bs_delta_straddle(S_, K, tau, sig):
    if tau <= 0:
        return float(np.sign(S_ - K))
    d1 = (np.log(S_ / K) + 0.5 * sig * sig * tau) / (sig * np.sqrt(tau))
    return 2 * norm.cdf(d1) - 1


class Inputs:
    def __init__(self):
        self.perp = load_binance_klines("data/raw/BTCUSDT-5m-*.zip")["close"]           # index = close edge
        self.funding = load_funding("data/raw/BTCUSDT-fundingRate-*.zip")
        self.dp = delivery_prices()
        hs = pd.read_parquet(DIR / "atm_effective_half_spread.parquet")
        m = hs.set_index("t").h_pct_mark.sort_index()
        self.h_monthly = m

    def perp_at(self, t):
        return float(self.perp.loc[:t].iloc[-1]) if t in self.perp.index else float(self.perp.asof(t))

    def h_pct(self, friday):
        """Trailing 3-month median effective half-spread (% of mark), trades strictly before friday 08:00."""
        w = self.h_monthly[(self.h_monthly.index < friday) & (self.h_monthly.index >= friday - pd.DateOffset(months=3))]
        return float(w.median()) if len(w) else np.nan


def one_week(inp, friday, entry_offset=pd.Timedelta(minutes=5), h_mode="measured", hedge_iv="entry"):
    t0 = friday + entry_offset
    expiry = friday + pd.Timedelta(days=7)
    sm, idx, traded = smile_for(t0, expiry)
    if sm is None or len(traded) == 0 or not np.isfinite(idx):
        return None
    F = idx * sm.f_ratio
    K = float(min(traded, key=lambda k: abs(k - F)))
    k = np.log(K / F)
    s = np.sqrt(max(sm.w(k), 1e-12))
    tau0 = (expiry - t0).total_seconds() / YEAR
    iv = s / np.sqrt(tau0)
    call, put = F * S.fwd_price("C", k, s), F * S.fwd_price("P", k, s)
    prem = call + put
    h = inp.h_pct(friday)
    if h_mode == "maker":
        h = 0.0
    elif h_mode == "stressed":
        h = max(h, STRESSED_H)
    spread_cost = h * prem
    opt_fees = min(OPT_FEE * idx, OPT_CAP * call) + min(OPT_FEE * idx, OPT_CAP * put)
    conv = CONVERT * prem
    S_T = inp.dp.get(expiry.date(), np.nan)
    payoff = abs(S_T - K)
    deliv_fee = min(DELIV_FEE * S_T, OPT_CAP * payoff) if payoff > 0 else 0.0
    # hedge: t0, then daily at the same clock time until the day before expiry; close at the expiry 08:00 bar
    times = [t0 + pd.Timedelta(days=i) for i in range(7) if t0 + pd.Timedelta(days=i) < expiry]
    px = [inp.perp_at(t) for t in times]
    close_px = inp.perp_at(expiry)
    pos, hedge_pnl, hedge_cost, fund, prev = [], 0.0, 0.0, 0.0, 0.0
    sig = iv
    for i, (t, p) in enumerate(zip(times, px)):
        if hedge_iv == "daily" and i > 0:
            sm_d, _, _ = smile_for(t, expiry)
            if sm_d is not None:
                Fd = p
                sig = np.sqrt(max(sm_d.w(np.log(K / Fd)), 1e-12) / sm_d.tau)
        tau = (expiry - t).total_seconds() / YEAR
        hpos = bs_delta_straddle(p, K, tau, sig)                 # BTC long perp held by the short straddle
        hedge_cost += TAKER_HEDGE * abs(hpos - prev) * p
        nxt_t = times[i + 1] if i + 1 < len(times) else expiry
        nxt_p = px[i + 1] if i + 1 < len(times) else close_px
        hedge_pnl += hpos * (nxt_p - p)
        fr = inp.funding[(inp.funding.index > t) & (inp.funding.index <= nxt_t)]
        for ft, rate in fr.items():
            fund -= hpos * inp.perp_at(ft) * rate
        pos.append(hpos)
        prev = hpos
    hedge_cost += TAKER_HEDGE * abs(prev) * close_px                # close the hedge
    rv = np.log(inp.perp.loc[t0:expiry]).diff().dropna()
    rv_ann = float(rv.std() * np.sqrt(365 * 288)) if len(rv) > 10 else np.nan
    gross = prem - payoff + hedge_pnl
    costs = spread_cost + opt_fees + conv + deliv_fee + hedge_cost - fund
    net = gross - costs
    return {"friday": friday, "K": K, "F": F, "S_entry": idx, "S_T": S_T, "iv": iv, "rv": rv_ann, "premium": prem,
            "payoff": payoff, "hedge_pnl": hedge_pnl, "gross": gross, "spread_cost": spread_cost, "opt_fees": opt_fees,
            "convert": conv, "deliv_fee": deliv_fee, "hedge_cost": hedge_cost, "funding": fund, "net": net,
            "h_pct": h, "n_strikes": sm.n_strikes, "net_pct_prem": net / prem, "ret_notional": net / idx,
            "gross_ret_notional": gross / idx}


def run(inp, frs, **kw):
    rows = [r for r in (one_week(inp, f, **kw) for f in frs) if r is not None]
    return pd.DataFrame(rows).set_index("friday")


def summary(b, label):
    ret = b.ret_notional
    tr = tail_report(b.net, STRESS)
    sr = float(ret.mean() / ret.std(ddof=1))
    years = len(b) / 52.18
    return {"label": label, "weeks": int(len(b)), "mean_net_pct_premium": float(b.net.sum() / b.premium.sum()),
            "mean_of_weekly_pct_premium": float(b.net_pct_prem.mean()), "median_net_pct_premium": float(b.net_pct_prem.median()),
            "mean_net_usd": float(b.net.mean()), "t_ret_notional": float(ret.mean() / (ret.std(ddof=1) / np.sqrt(len(ret)))),
            "sharpe_weekly": sr, "sharpe_annual": sr * np.sqrt(52.18), "sharpe_annual_se": 1 / np.sqrt(years),
            "gross_mean_pct_premium": float(b.gross.sum() / b.premium.sum()),
            "mean_iv": float(b.iv.mean()), "mean_rv": float(b.rv.mean()), "share_iv_gt_rv": float((b.iv > b.rv).mean()),
            "cost_breakdown_pct_premium": {c: float(b[c].sum() / b.premium.sum()) for c in
                                           ("spread_cost", "opt_fees", "convert", "deliv_fee", "hedge_cost", "funding")},
            "tail": tr}


def main():
    frs, cut = dev_fridays()
    inp = Inputs()
    configs = {"main": {}, "maker": {"h_mode": "maker"}, "stressed_cost": {"h_mode": "stressed"},
               "hedge_daily_iv": {"hedge_iv": "daily"}, "entry_0905": {"entry_offset": pd.Timedelta(minutes=65)}}
    res, books, sel = {}, {}, []
    for name, kw in configs.items():
        b = run(inp, frs, **kw)
        assert (b.index < cut).all()
        books[name] = b
        res[name] = summary(b, name)
        sel.append({"name": f"p16_{name}", "kind": "rule" if name == "main" else "measurement",
                    "params": {k: str(v) for k, v in kw.items()}, "sr_per_period": res[name]["sharpe_weekly"],
                    "n": res[name]["weeks"]})
        print(name, json.dumps({k: v for k, v in res[name].items() if k not in ("tail", "cost_breakdown_pct_premium")},
                               default=str), flush=True)
    m, M = books["main"], res["main"]
    res["kills"] = {"k1_mean_net_pct_premium": M["mean_net_pct_premium"], "k1_threshold": 0.02,
                    "k1_fires": M["mean_net_pct_premium"] < 0.02,
                    "k2_t": M["t_ret_notional"], "k2_fires": not (M["t_ret_notional"] >= 2),
                    "k3_worst_over_mean": M["tail"]["worst_over_mean"], "k3_fires": not (M["tail"]["worst_over_mean"] <= 12)}
    res["kills"]["killed"] = res["kills"]["k1_fires"] or res["kills"]["k2_fires"] or res["kills"]["k3_fires"]
    half = m.index[len(m) // 2]
    res["halves"] = {"first": summary(m[m.index < half], "first half"), "second": summary(m[m.index >= half], "second half")}
    ret = m.ret_notional
    sk, ku = float(stats.skew(ret)), float(stats.kurtosis(ret, fisher=False))
    srs = [r["sr_per_period"] for r in sel]
    res["psr_dsr"] = {"psr": psr(M["sharpe_weekly"], len(ret), sk, ku),
                      "dsr": dsr(M["sharpe_weekly"], len(ret), sk, ku, len(srs), float(np.var(srs, ddof=1))),
                      "n_trials": len(srs)}
    res["no_entry_weeks"] = [str(f.date()) for f in frs if f not in m.index]
    m.to_csv(HERE / "step1_weeks_main.csv")
    SEL.write_text(json.dumps(sel, indent=1, default=str))
    (HERE / "step1.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({"kills": res["kills"], "psr_dsr": res["psr_dsr"], "tail_main": M["tail"],
                      "costs_main": M["cost_breakdown_pct_premium"],
                      "halves": {k: {kk: v[kk] for kk in ("weeks", "mean_net_pct_premium", "t_ret_notional")}
                                 for k, v in res["halves"].items()},
                      "no_entry_weeks": res["no_entry_weeks"]}, indent=1, default=str))


if __name__ == "__main__":
    main()
