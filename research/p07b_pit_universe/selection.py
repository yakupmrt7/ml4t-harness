"""p07b pre-OOS: p06's 3v3 momentum book on a point-in-time universe (p04's rule as
of 2020-09, universe.json) over 2020-10 -> 2022-07 (PLAN.md). Everything except the
universe date is p07's code, called unchanged; the p06 window is p07's run verbatim.
Pre-registered data fix: 5m bars missing from the monthly archive are filled from
the daily files (missing bars only). One selection trial.

Run from the repo root:  PYTHONPATH=. python research/p07b_pit_universe/selection.py [--no-log]
"""
import argparse
import hashlib
import importlib.util
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from harness.data import load_binance_klines, load_funding

_spec = importlib.util.spec_from_file_location("p07_selection", "research/p07_momentum_replication/selection.py")
p07 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p07)

HERE = Path(__file__).parent
UNIVERSE = json.loads((HERE / "universe.json").read_text())["universe"]
NEW, OLD = "new_2020-10_2022-07", "p06_2022-08_2024-03"
FIRST, LAST = p07.WINDOWS[NEW]
PNL_END = LAST + p07.DAY
DAILY_RAW = Path("data/raw/daily_klines")
DAILY_URL = "https://data.binance.vision/data/futures/um/daily/klines"
CACHE = Path("data/bars/p07b")


def fetch_daily(sym, day):
    """-> path or None (404). sha256-checked against .CHECKSUM."""
    dest = DAILY_RAW / f"{sym}-5m-{day}.zip"
    if dest.exists():
        return dest
    u = f"{DAILY_URL}/{sym}/5m/{sym}-5m-{day}.zip"
    try:
        data = urllib.request.urlopen(u, timeout=60).read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    want = urllib.request.urlopen(u + ".CHECKSUM", timeout=60).read().split()[0].decode()
    assert hashlib.sha256(data).hexdigest() == want, (sym, day)
    DAILY_RAW.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return dest


def load_bars(sym):
    """Monthly 5m bars 2020-01..2022-07, holes filled from daily files (missing bars only),
    cut at the last bar with trades (p04's delisting rule). -> bars, fill report."""
    cache = CACHE / f"{sym}-5m-2020-01_2022-07.parquet"
    rep_path = CACHE / f"{sym}-fill.json"
    if cache.exists() and rep_path.exists():
        return pd.read_parquet(cache), json.loads(rep_path.read_text())
    pats = [p for p in (f"data/raw/{sym}-5m-2020-*.zip", f"data/raw/{sym}-5m-2021-*.zip", f"data/raw/{sym}-5m-2022-0[1-7].zip")
            if list(Path().glob(p))]
    b = pd.concat([load_binance_klines(p) for p in pats])
    b = b[~b.index.duplicated()].sort_index().loc[:PNL_END]
    grid = pd.date_range(b.index[0], min(b.index[-1], PNL_END), freq="5min")
    missing = grid.difference(b.index)
    days = sorted({str(d.date()) for d in (missing - pd.Timedelta("5min")).floor("1D")})   # bar closing 00:00 is in the previous day's file
    fill = []
    no_file = []
    for d in days:
        f = fetch_daily(sym, d)
        if f is None:
            no_file.append(d)
            continue
        db = load_binance_klines(str(f))
        fill.append(db.loc[db.index.intersection(missing)])
    if fill:
        b = pd.concat([b] + fill)
        assert not b.index.duplicated().any()
        b = b.sort_index()
    still = grid.difference(b.index)
    live = b.index[b["count"] > 0]
    rep = {"first_bar": str(b.index[0]), "missing_in_monthly": len(missing), "days_fetched": days,
           "days_without_daily_file": no_file, "bars_filled": len(missing) - len(still), "still_missing": len(still),
           "last_live_bar": str(live[-1]), "delisted_in_window": bool(live[-1] < PNL_END - p07.DAY)}
    # the monthly archive ends at 2022-08-01 00:00, so every series stops 4 h before PNL_END (as in p07):
    # the last daily bucket is 20 h for all assets, and the harness sees no delisting since all end together
    b = b.loc[: live[-1]]
    CACHE.mkdir(parents=True, exist_ok=True)
    b.to_parquet(cache)
    rep_path.write_text(json.dumps(rep, indent=1))
    return b, rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-log", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    closes, funding, fills = {}, {}, {}
    for a in UNIVERSE:
        b, fills[a] = load_bars(a)
        closes[a] = b["close"]
        funding[a] = load_funding(f"data/raw/{a}-fundingRate-*.zip").loc[FIRST - 30 * p07.DAY: PNL_END]
    print("hole fill:", json.dumps({a: {k: r[k] for k in ("missing_in_monthly", "bars_filled", "still_missing",
                                                         "delisted_in_window")} for a, r in fills.items()}))
    times = pd.date_range(FIRST, LAST, freq="1D")
    for t in np.random.default_rng(0).choice(times, 5, replace=False):           # causality, as in p07
        t = pd.Timestamp(t)
        for a in UNIVERSE:
            x, y = p07.momentum(closes[a].loc[:t], pd.DatetimeIndex([t])), p07.momentum(closes[a], pd.DatetimeIndex([t]))
            assert np.allclose(x, y, equal_nan=True), (a, t)

    # p07's run_window reads its module-level UNIVERSE: point it at the p07b list for the
    # new window only, then back to p04's for the p06 window. No other code differs.
    out = {"plan": "research/p07b_pit_universe/PLAN.md", "universe": UNIVERSE, "hole_fill": fills,
           "cost_bps_flat": 12, "min_live": p07.MIN_LIVE, "windows": {},
           "diagnostic_rank_demeaned": {"_note": "DIAGNOSTIC ONLY: not part of the kill, not the book tested"}}
    daily_g, turn = {"3v3": [], "rank": []}, {"3v3": 0.0, "rank": 0.0}
    p04_universe = p07.UNIVERSE
    keys = ("days", "sr_gross", "sr_se", "t_gross", "t_nw10", "breakeven_bps", "breakeven_se_bps",
            "turnover_units_per_year", "sr_net_12bps", "beta_to_ew_live", "per_segment_sr_gross")
    for win in (NEW, OLD):
        if win == NEW:
            p07.UNIVERSE, c, f = UNIVERSE, closes, funding
        else:
            p07.UNIVERSE = p04_universe
            c, f = p07.load(win)
        res, dg, to, _ = p07.run_window(win, c, f, "3v3", shift_null=True)
        res["per_segment_sr_se"] = {k: float(1 / np.sqrt(v["days"] / 365)) for k, v in res["per_segment_sr_gross"].items()}
        out["windows"][win] = res
        daily_g["3v3"].append(dg)
        turn["3v3"] += to
        print(f"\n[{win}] 3v3 momentum, universe {'p07b 2020-09' if win == NEW else 'p04 2022-07'}\n"
              + json.dumps(res, indent=1, default=lambda v: round(v, 4)))
        rd, dgr, tor, _ = p07.run_window(win, c, f, "rank")
        out["diagnostic_rank_demeaned"][win] = {k: rd[k] for k in keys}
        daily_g["rank"].append(dgr)
        turn["rank"] += tor
        print(f"[{win}] DIAGNOSTIC rank-demeaned: " + json.dumps(out["diagnostic_rank_demeaned"][win], default=lambda v: round(v, 4)))
    p07.UNIVERSE = p04_universe

    pooled = p07.stats(pd.concat(daily_g["3v3"]), None, None, turn["3v3"])
    out["pooled"] = pooled
    out["diagnostic_rank_demeaned"]["pooled"] = p07.stats(pd.concat(daily_g["rank"]), None, None, turn["rank"])
    print("\n[pooled] 3v3:", json.dumps(pooled, default=lambda v: round(v, 4)))
    print("[pooled] DIAGNOSTIC rank-demeaned:", json.dumps(out["diagnostic_rank_demeaned"]["pooled"], default=lambda v: round(v, 4)))

    new, old = out["windows"][NEW], out["windows"][OLD]
    killed = new["sr_gross"] <= 0 or new["breakeven_bps"] < p07.KILL_BE
    gate = (not killed and new["sr_gross"] >= p07.GATE_SR and old["sr_gross"] >= p07.GATE_SR
            and pooled["t_gross"] >= p07.GATE_T and pooled["breakeven_minus_1se"] >= p07.KILL_BE)
    underpowered = (not killed and not gate and new["sr_gross"] > 0 and old["sr_gross"] > 0
                    and p07.UNDERPOWERED_T <= pooled["t_gross"] < p07.GATE_T)
    decision = ("KILL: abandon daily cross-sectional momentum" if killed else
                "GATE: stop at the OOS gate, rebuild costs for new names first, ask owner" if gate else
                "UNDERPOWERED, NOT DEAD: stop" if underpowered else
                "FAIL ON GATE: not killed, not underpowered-band; stop")
    out["kill_check"] = {"killed": bool(killed), "gate": bool(gate), "underpowered": bool(underpowered), "decision": decision}
    print("\nKILL CHECK:", json.dumps(out["kill_check"]))
    (HERE / "selection.json").write_text(json.dumps(out, indent=1, default=str))
    if not args.no_log:
        path = HERE / "selection_trials.json"
        prev = json.loads(path.read_text()) if path.exists() else []
        row = {"kind": "factor", "name": "p07b momentum_28d_skip1, point-in-time universe (2020-09)",
               "params": {"sign": 1, "legs": p07.N_LEG, "decision": "04:00 UTC daily", "min_live": p07.MIN_LIVE,
                          "universe": UNIVERSE, "costs": "flat 12 bps per unit, funding in gross",
                          "windows": [NEW, OLD], "note": "second look at the 2020-10..2022-07 window (p07 was the first)"},
               "sr_gross_new": new["sr_gross"], "sr_gross_p06": old["sr_gross"], "t_gross_pooled": pooled["t_gross"],
               "breakeven_bps_new": new["breakeven_bps"], "breakeven_bps_pooled": pooled["breakeven_bps"],
               "breakeven_se_bps_pooled": pooled["breakeven_se_bps"], "n": pooled["days"], "period": "daily gross",
               "decision": decision, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
        path.write_text(json.dumps(prev + [row], indent=1, default=str))
    print(f"({time.time() - t0:.0f}s)")
