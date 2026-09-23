"""p07 pre-OOS: does p06's 28d/skip-1 momentum sort replicate on 2020-10 -> 2022-07?
(PLAN.md). The book is frozen from p06: 04:00 UTC daily decision, delay=1, top-3 long /
bottom-3 short, +-1 unit ($10k) each, gross = price + funding. New: require >= 8 live
(days with fewer are flat and dropped), flat 12 bps per unit traded for net, and a
rank-demeaned all-asset book reported as a DIAGNOSTIC only. One selection trial.

Run from the repo root:  PYTHONPATH=. python research/p07_momentum_replication/selection.py [--no-log]
"""
import argparse
import importlib.util
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from harness.backtest import CostModel
from harness.data import load_binance_klines, load_funding
from harness.portfolio import funding_pnl, portfolio_shift_null, run_portfolio_backtest

_spec = importlib.util.spec_from_file_location("p06_selection", "research/p06_xsec_daily/selection.py")
p06 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p06)
N_LEG, UNIVERSE, daily, sr, weights = p06.N_LEG, p06.UNIVERSE, p06.daily, p06.sr, p06.weights   # p06's book, frozen

HERE = Path(__file__).parent
DAY = pd.Timedelta(days=1)
WINDOWS = {   # first / last decision (04:00 UTC); P&L to last + 1 day
    "new_2020-10_2022-07": (pd.Timestamp("2020-10-01 04:00", tz="UTC"), pd.Timestamp("2022-07-31 04:00", tz="UTC")),
    "p06_2022-08_2024-03": (pd.Timestamp("2022-08-01 04:00", tz="UTC"), pd.Timestamp("2024-03-31 04:00", tz="UTC")),
}
MIN_LIVE = 8
COST = CostModel(fee_bps=12, slippage_bps=0)          # flat 12 bps per unit traded
SEGMENTS = {"new_2020-10_2022-07": (("2020Q4", "2020-10-01", "2020-12-31"), ("2021", "2021-01-01", "2021-12-31"),
                                    ("2022-01..07", "2022-01-01", "2022-07-31")),
            "p06_2022-08_2024-03": (("2022-08..12", "2022-08-01", "2022-12-31"), ("2023", "2023-01-01", "2023-12-31"),
                                    ("2024Q1", "2024-01-01", "2024-03-31"))}
KILL_BE, GATE_SR, GATE_T, UNDERPOWERED_T = 12.0, 0.5, 2.0, 1.5


def load_closes_new(a):
    cache = Path(f"data/bars/{a}-5m-2020-01_2022-07.parquet")
    if cache.exists():
        return pd.read_parquet(cache)["close"]
    files = [p for p in (f"data/raw/{a}-5m-2020-*.zip", f"data/raw/{a}-5m-2021-*.zip", f"data/raw/{a}-5m-2022-0[1-7].zip")
             if list(Path().glob(p))]
    b = pd.concat([load_binance_klines(p) for p in files])
    b = b[~b.index.duplicated()].sort_index()
    b.to_parquet(cache)
    return b["close"]


def load(window):
    first, last = WINDOWS[window]
    pnl_end = last + DAY
    closes, funding = {}, {}
    for a in UNIVERSE:
        if window.startswith("new"):
            c = load_closes_new(a)
        else:
            c = pd.read_parquet(f"data/bars/{a}-5m-2022-06_2026-08.parquet")["close"]
        closes[a] = c.loc[: pnl_end]
        funding[a] = load_funding(f"data/raw/{a}-fundingRate-*.zip").loc[first - 30 * DAY: pnl_end]
    return closes, funding


def momentum(close, times):
    """p06's factor: close(t - 24h) / close(t - 28d) - 1, exact 5m bars; NaN if either is missing."""
    return close.reindex(times - DAY).to_numpy() / close.reindex(times - 28 * DAY).to_numpy() - 1


def rank_demeaned(values: pd.DataFrame) -> pd.DataFrame:
    """DIAGNOSTIC book: w ~ rank - mean(rank) over live assets, scaled to sum|w| = 2*N_LEG."""
    r = values.rank(axis=1)
    w = r.sub(r.mean(axis=1), axis=0)
    return (w.div(w.abs().sum(axis=1), axis=0) * 2 * N_LEG).fillna(0.0)


def nw_t(d, lags=10):
    r = d - d.mean()
    acov = sum((1 - k / (lags + 1)) * 2 * (r[k:] * r[:-k].to_numpy()).mean() for k in range(1, lags + 1))
    return float(d.mean() / np.sqrt((r.var() + acov) / len(d)))


def stats(dg, dn, dp, turnover, mkt=None):
    n = len(dg)
    out = {"days": n, "sr_gross": sr(dg), "sr_se": float(1 / np.sqrt(n / 365)), "t_gross": sr(dg) * np.sqrt(n / 365),
           "t_nw10": nw_t(dg), "turnover_units": float(turnover), "turnover_units_per_year": float(turnover / (n / 365)),
           "breakeven_bps": float(dg.sum() / turnover * 1e4), "breakeven_se_bps": float(dg.std() * np.sqrt(n) / turnover * 1e4)}
    out["breakeven_minus_1se"] = out["breakeven_bps"] - out["breakeven_se_bps"]
    if dn is not None:
        out["sr_net_12bps"] = sr(dn)
    if dp is not None:
        out["sr_price_only"] = sr(dp)
    if mkt is not None:
        x = mkt.reindex(dg.index).fillna(0.0)
        beta = float(np.polyfit(x, dg, 1)[0])
        out["beta_to_ew_live"] = beta
        out["sr_gross_beta_hedged"] = sr(dg - beta * x)
    return out


def run_window(window, closes, funding, book, shift_null=False):
    first, last = WINDOWS[window]
    pnl_end = last + DAY
    times = pd.date_range(first, last, freq="1D")
    vals = pd.DataFrame({a: momentum(closes[a], times) for a in UNIVERSE}, index=times)
    n_live = vals.notna().sum(axis=1)
    ok = n_live >= MIN_LIVE
    vals_ok = vals.where(ok, np.nan, axis=0)                        # < 8 live -> no book that day
    w = weights(vals_ok, +1) if book == "3v3" else rank_demeaned(vals_ok)
    grid = {a: c.loc[first:pnl_end] for a, c in closes.items()}
    tg = {a: w[a].reindex(grid[a].index, method="ffill").fillna(0.0) for a in UNIVERSE}
    pf_g, parts = run_portfolio_backtest(grid, tg, CostModel(0, 0))
    pf_n, _ = run_portfolio_backtest(grid, tg, COST)
    fch = funding_pnl(parts["held"], funding)
    price = pf_g["gross"]
    gross = price - fch.sum(axis=1)
    net = gross - pf_n["cost"]
    keep = pd.DatetimeIndex(times[ok.to_numpy()].normalize())      # decision days with a book; drops p06's stub
    dg, dn, dp = (daily(x).reindex(keep) for x in (gross, net, price))
    assert dg.notna().all(), "missing daily bucket"
    assert abs(daily(gross).drop(keep, errors="ignore").abs().sum()) < 1e-12, "P&L on a dropped day"
    rets = pd.concat([c.pct_change(fill_method=None) for c in grid.values()], axis=1)
    mkt = daily(rets.mean(axis=1, skipna=True).fillna(0.0))
    turnover = pf_g["turnover"].sum()
    res = stats(dg, dn, dp, turnover, mkt)
    res.update({"first_decision": str(first), "last_decision": str(last), "decisions": len(times),
                "days_dropped_lt8_live": int((~ok).sum()),
                "first_day_with_book": str(times[ok.to_numpy()][0]),
                "n_live_min_max_mean": [int(n_live[ok].min()), int(n_live[ok].max()), float(n_live[ok].mean())],
                "mean_legs_changed_per_day": float((w.diff().abs().sum(axis=1) > 0).mean()),
                "funding_share_of_gross": float(-fch.sum().sum() / gross.sum()) if gross.sum() else np.nan})
    res["per_segment_sr_gross"] = {k: {"sr": sr(dg.loc[a:b]), "days": int(len(dg.loc[a:b]))} for k, a, b in SEGMENTS[window]}
    if shift_null:
        actual, null, p = portfolio_shift_null(grid, tg, CostModel(0, 0), n=300)
        res.update({"shift_null_price_only_bar_sr": float(actual), "shift_null_p": p,
                    "shift_null_mean": float(null.mean()), "shift_null_std": float(null.std())})
    return res, dg, turnover, vals


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-log", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    out = {"plan": "research/p07_momentum_replication/PLAN.md", "cost_bps_flat": 12, "min_live": MIN_LIVE, "windows": {},
           "diagnostic_rank_demeaned": {"_note": "DIAGNOSTIC ONLY: not part of the kill, not the book tested"}}
    daily_g = {"3v3": [], "rank": []}
    turn = {"3v3": 0.0, "rank": 0.0}
    for win in WINDOWS:
        closes, funding = load(win)
        # causality: momentum at t is identical when computed from data truncated at t
        first, last = WINDOWS[win]
        times = pd.date_range(first, last, freq="1D")
        for t in np.random.default_rng(0).choice(times, 5, replace=False):
            t = pd.Timestamp(t)
            for a in UNIVERSE:
                x, y = momentum(closes[a].loc[:t], pd.DatetimeIndex([t])), momentum(closes[a], pd.DatetimeIndex([t]))
                assert np.allclose(x, y, equal_nan=True), (a, t)
        res, dg, to, vals = run_window(win, closes, funding, "3v3", shift_null=True)
        out["windows"][win] = res
        daily_g["3v3"].append(dg)
        turn["3v3"] += to
        print(f"\n[{win}] 3v3 momentum (causality ok)\n" + json.dumps(res, indent=1, default=lambda v: round(v, 4)))
        rd, dgr, tor, _ = run_window(win, closes, funding, "rank")
        rd = {k: rd[k] for k in ("days", "sr_gross", "sr_se", "t_gross", "t_nw10", "breakeven_bps", "breakeven_se_bps",
                                 "turnover_units_per_year", "sr_net_12bps", "beta_to_ew_live", "per_segment_sr_gross")}
        out["diagnostic_rank_demeaned"][win] = rd
        daily_g["rank"].append(dgr)
        turn["rank"] += tor
        print(f"[{win}] DIAGNOSTIC rank-demeaned: " + json.dumps(rd, default=lambda v: round(v, 4)))

    pooled = stats(pd.concat(daily_g["3v3"]), None, None, turn["3v3"])
    out["pooled"] = pooled
    out["diagnostic_rank_demeaned"]["pooled"] = stats(pd.concat(daily_g["rank"]), None, None, turn["rank"])
    print("\n[pooled] 3v3:", json.dumps(pooled, default=lambda v: round(v, 4)))
    print("[pooled] DIAGNOSTIC rank-demeaned:", json.dumps(out["diagnostic_rank_demeaned"]["pooled"], default=lambda v: round(v, 4)))

    new, old = out["windows"]["new_2020-10_2022-07"], out["windows"]["p06_2022-08_2024-03"]
    killed = new["sr_gross"] <= 0 or new["breakeven_bps"] < KILL_BE
    gate = (not killed and new["sr_gross"] >= GATE_SR and old["sr_gross"] >= GATE_SR and pooled["t_gross"] >= GATE_T
            and pooled["breakeven_minus_1se"] >= KILL_BE)
    underpowered = (not killed and not gate and new["sr_gross"] > 0 and old["sr_gross"] > 0
                    and UNDERPOWERED_T <= pooled["t_gross"] < GATE_T)
    decision = ("KILL: abandon daily cross-sectional momentum" if killed else
                "GATE: proceed to OOS gate, ask owner" if gate else
                "UNDERPOWERED, NOT DEAD: stop; only breadth may follow" if underpowered else
                "FAIL ON GATE: not killed, not underpowered-band; stop")
    out["kill_check"] = {"killed": killed, "gate": gate, "underpowered": underpowered, "decision": decision}
    print("\nKILL CHECK:", json.dumps(out["kill_check"]))
    (HERE / "selection.json").write_text(json.dumps(out, indent=1, default=str))
    if not args.no_log:
        path = HERE / "selection_trials.json"
        prev = json.loads(path.read_text()) if path.exists() else []
        row = {"kind": "factor", "name": "p07 momentum_28d_skip1 replication",
               "params": {"sign": 1, "legs": N_LEG, "decision": "04:00 UTC daily", "min_live": MIN_LIVE,
                          "costs": "flat 12 bps per unit, funding in gross", "windows": list(WINDOWS)},
               "sr_gross_new": new["sr_gross"], "sr_gross_p06": old["sr_gross"], "t_gross_pooled": pooled["t_gross"],
               "breakeven_bps_new": new["breakeven_bps"], "breakeven_bps_pooled": pooled["breakeven_bps"],
               "breakeven_se_bps_pooled": pooled["breakeven_se_bps"], "n": pooled["days"], "period": "daily gross",
               "decision": decision, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
        path.write_text(json.dumps(prev + [row], indent=1, default=str))
    print(f"({time.time() - t0:.0f}s)")
