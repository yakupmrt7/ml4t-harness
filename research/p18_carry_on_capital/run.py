"""p18 (PLAN.md): HL funding carry on survivable capital, dev only (2024-01-01 -> 2026-01-12), 2025 decides.
Books: A short HL perp / long BN perp; B short HL perp / long BN spot; C oracle timing of A and B (DP).

  python research/p18_carry_on_capital/run.py
"""
import json
import pathlib
import sys
import time

import numpy as np
import pandas as pd
import requests

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE.parents[1] / "data/hl/funding"
COINS = ["BTC", "ETH", "SOL", "XRP", "DOGE", "LINK", "AVAX", "SUI"]
START, END = pd.Timestamp("2024-01-01", tz="UTC"), pd.Timestamp("2026-01-12", tz="UTC")
Y25 = (pd.Timestamp("2025-01-01", tz="UTC"), pd.Timestamp("2026-01-01", tz="UTC"))
C_HL, C_BNP, C_SPOT = 5e-4, 5.5e-4, 10.5e-4          # taker + slippage per side
BUFFER, MM, LMAX = 1.5, 0.05, 5.0
BAR = 6.0                                             # %/yr on capital
SEL = HERE / "selection_trials.json"


def cut(s):
    s = s[(s.index >= START) & (s.index < END)]
    return s


def hl_ohlc(coin):
    f = DATA / f"hl_ohlc_{coin}.parquet"
    if not f.exists():
        body = {"type": "candleSnapshot", "req": {"coin": coin, "interval": "1d", "startTime": int(START.timestamp() * 1000),
                                                  "endTime": int(END.timestamp() * 1000) - 1}}
        for k in range(6):
            r = requests.post("https://api.hyperliquid.xyz/info", json=body, timeout=30)
            if r.status_code == 200:
                break
            time.sleep(5 * (k + 1))
        c = r.json()
        pd.DataFrame({"date": pd.to_datetime([x["t"] for x in c], unit="ms", utc=True),
                      "high": [float(x["h"]) for x in c], "low": [float(x["l"]) for x in c],
                      "close": [float(x["c"]) for x in c]}).to_parquet(f)
    return cut(pd.read_parquet(f).set_index("date"))


def bn_spot_ohlc(coin):
    f = DATA / f"bn_spot_ohlc_{coin}.parquet"
    if not f.exists():
        k = requests.get("https://api.binance.com/api/v3/klines",
                         params={"symbol": coin + "USDT", "interval": "1d", "startTime": int(START.timestamp() * 1000),
                                 "endTime": int(END.timestamp() * 1000) - 1, "limit": 1000}, timeout=30).json()
        pd.DataFrame({"date": pd.to_datetime([x[0] for x in k], unit="ms", utc=True), "high": [float(x[2]) for x in k],
                      "low": [float(x[3]) for x in k], "close": [float(x[4]) for x in k]}).to_parquet(f)
    return cut(pd.read_parquet(f).set_index("date"))


def bn_perp_ohlc(coin):
    return cut(pd.read_parquet(DATA / f"bn_ohlc_{coin}.parquet").set_index("date"))


def daily_funding(venue, coin):
    f = pd.read_parquet(DATA / f"{venue}_funding_{coin}.parquet").set_index("time")["rate"]
    f = f[(f.index >= START) & (f.index < END)]
    return f.resample("1D").sum(min_count=1)


def worst_move(o, side):
    prev = o.close.shift(1)
    return float((o.high / prev - 1).max()) if side == "short" else float((1 - o.low / prev).max())


def lev(M):
    return min(LMAX, 1.0 / (BUFFER * M + MM))


def oracle(pnl_by_state, switch_cost):
    """DP over states (dict state -> daily pnl array incl. holding costs; state 0 = flat, pnl 0).
    switch_cost(a, b) per transition. Starts and ends flat. Returns the optimal daily pnl path."""
    states = list(pnl_by_state)
    n = len(next(iter(pnl_by_state.values())))
    V = {s: (0.0 if s == 0 else -switch_cost(0, s)) + pnl_by_state[s][0] for s in states}
    back = []
    for t in range(1, n):
        nv, bp = {}, {}
        for s in states:
            best = max(states, key=lambda p: V[p] - switch_cost(p, s))
            nv[s] = V[best] - switch_cost(best, s) + pnl_by_state[s][t]
            bp[s] = best
        back.append(bp)
        V = nv
    last = max(states, key=lambda s: V[s] - switch_cost(s, 0))
    path = [last]
    for bp in reversed(back):
        path.append(bp[path[-1]])
    path = path[::-1]
    daily = np.array([pnl_by_state[s][t] for t, s in enumerate(path)])
    for t in range(n):                                     # charge switches on the day they happen
        prev = 0 if t == 0 else path[t - 1]
        daily[t] -= switch_cost(prev, path[t])
    daily[-1] -= switch_cost(path[-1], 0)
    return daily, np.array(path)


def coin(c):
    idx = pd.date_range(START, END - pd.Timedelta(days=1), freq="D", tz="UTC")
    fh, fb = daily_funding("hl", c).reindex(idx).fillna(0), daily_funding("bn", c).reindex(idx).fillna(0)
    hl, bp, sp = hl_ohlc(c), bn_perp_ohlc(c), bn_spot_ohlc(c)
    r_hl, r_bp, r_sp = (x.close.pct_change().reindex(idx).fillna(0) for x in (hl, bp, sp))
    L_s, L_l = lev(worst_move(hl, "short")), lev(worst_move(bp, "long"))
    capA, capB = 1 / L_s + 1 / L_l, 1 / L_s + 1.0
    hold_A = (r_hl.abs() * C_HL + r_bp.abs() * C_BNP).to_numpy()   # daily reset of both legs
    hold_B = (r_hl.abs() * C_HL + r_sp.abs() * C_SPOT).to_numpy()
    carry_A = (fh - fb - (r_hl - r_bp)).to_numpy()
    carry_B = (fh - (r_hl - r_sp)).to_numpy()
    A = carry_A - hold_A
    A[0] -= C_HL + C_BNP
    A[-1] -= C_HL + C_BNP
    B = carry_B - hold_B
    B[0] -= C_HL + C_SPOT
    B[-1] -= C_HL + C_SPOT
    oA, pathA = oracle({0: np.zeros(len(idx)), 1: carry_A - hold_A, -1: -carry_A - hold_A},
                       lambda a, b: abs(b - a) * (C_HL + C_BNP))
    oB, pathB = oracle({0: np.zeros(len(idx)), 1: carry_B - hold_B}, lambda a, b: abs(b - a) * (C_HL + C_SPOT))
    ser = pd.DataFrame({"A": A, "B": B, "oA": oA, "oB": oB}, index=idx)
    return ser, {"L_short_hl": L_s, "L_long_bnperp": L_l, "M_short": worst_move(hl, "short"),
                 "M_long_perp": worst_move(bp, "long"), "capital_A": capA, "capital_B": capB,
                 "oracle_A_days_in": int((pathA != 0).sum()), "oracle_B_days_in": int((pathB != 0).sum())}


def nw_se_annual(x, lags=30):
    e = x - x.mean()
    n = len(e)
    v = float(e @ e / n)
    for L in range(1, lags + 1):
        v += 2 * (1 - L / (lags + 1)) * float(e[L:] @ e[:-L]) / n
    return 365 * np.sqrt(v / n)


def evaluate(daily_pnl, capital, label):
    """daily_pnl: portfolio P&L per unit notional; capital: portfolio capital per unit notional."""
    r = daily_pnl / capital
    out = {}
    for name, (a, b) in {"dev": (START, END), "2025": Y25}.items():
        x = r[(r.index >= a) & (r.index < b)]
        m = x.groupby(x.index.tz_localize(None).to_period("M")).sum()
        f5 = x.rolling(5).sum().dropna()
        out[name] = {"ann_on_capital_%": 36500 * float(x.mean()), "nw_se_%": 100 * nw_se_annual(x.to_numpy()),
                     "monthly_t": float(m.mean() / (m.std(ddof=1) / np.sqrt(len(m)))), "months": int(len(m)),
                     "worst5d_over_mean5d": float(-f5.min() / f5.mean()) if f5.mean() > 0 else None}
    y = out["2025"]
    out["passes_static_rule"] = bool(y["ann_on_capital_%"] >= BAR and y["monthly_t"] >= 2 and
                                     y["worst5d_over_mean5d"] is not None and y["worst5d_over_mean5d"] <= 12)
    out["label"] = label
    return out


def main():
    per, sers = {}, {}
    for c in COINS:
        sers[c], per[c] = coin(c)
    cap = {k: float(np.mean([per[c][f"capital_{k}"] for c in COINS])) for k in ("A", "B")}
    port = {k: pd.concat({c: sers[c][k] for c in COINS}, axis=1).mean(axis=1) for k in ("A", "B", "oA", "oB")}
    res = {"capital_per_unit_notional": cap,
           "A": evaluate(port["A"], cap["A"], "static perp/perp"),
           "B": evaluate(port["B"], cap["B"], "static perp/spot"),
           "oracle_A": evaluate(port["oA"], cap["A"], "oracle perp/perp"),
           "oracle_B": evaluate(port["oB"], cap["B"], "oracle perp/spot")}
    best = max(("oracle_A", "oracle_B"), key=lambda k: res[k]["2025"]["ann_on_capital_%"])
    res["C"] = {"which": best, **res[best]["2025"]}
    c_ann = res["C"]["ann_on_capital_%"]
    res["decision"] = {
        "rule1_close_carry": c_ann < BAR,
        "A_passes": res["A"]["passes_static_rule"], "B_passes": res["B"]["passes_static_rule"],
        "outcome": ("close carry entirely (oracle < 6%/yr on capital in 2025)" if c_ann < BAR else
                    "B passes: pre-register B for the p14 holdout" if res["B"]["passes_static_rule"] else
                    "A passes: pre-register A for the p14 holdout" if res["A"]["passes_static_rule"] else
                    "forecast problem only (oracle passes, static books fail)")}
    res["per_coin"] = per
    res["per_coin_2025_ann_on_capital_%"] = {
        c: {k: 36500 * float(sers[c][k][(sers[c].index >= Y25[0]) & (sers[c].index < Y25[1])].mean()) /
            per[c][f"capital_{'A' if k in ('A', 'oA') else 'B'}"] for k in ("A", "B", "oA", "oB")} for c in COINS}
    d1010 = pd.Timestamp("2025-10-10", tz="UTC")
    res["2025-10-10_portfolio_pnl_per_notional_%"] = {k: 100 * float(port[k].get(d1010, np.nan)) for k in port}
    print(json.dumps(res, indent=1, default=str))
    (HERE / "results.json").write_text(json.dumps(res, indent=1, default=str))
    SEL.write_text(json.dumps([{"name": f"p18_{k}", "kind": "measurement",
                                "result": {"ann_on_capital_2025_%": res[k]["2025"]["ann_on_capital_%"],
                                           "monthly_t_2025": res[k]["2025"]["monthly_t"]}}
                               for k in ("A", "B", "oracle_A", "oracle_B")], indent=1))


if __name__ == "__main__":
    main()
