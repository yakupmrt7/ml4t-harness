"""p09 Steps 2-3 (PLAN.md + amendment 3), dev only.

Step 2: every second of every market's life, model P(up) from a driftless diffusion on the
Binance 50/50 blend (no fitted parameter, no lag shift) vs the Polymarket Up mid.
Step 3: take the touch when model - ask >= h, after latency L, capped at quoted size, held to
resolution; outcomes are GAMMA resolutions. Grid h x L, all reported, nothing chosen.

Every result twice: (i) all markets, (ii) excluding markets whose FINISH is within 1 bp of a tie
(Step-1b blend rebuild; ex post, a reporting cut only). Ex-ante reliability flag: |current gap|
bucket at decision time; "reliable" = >= 3 bp.

Run from the repo root:  python research/p09_polymarket_fairprice/step23_fairvalue.py
"""
import json
from collections import defaultdict
from math import erf, sqrt
from pathlib import Path

import numpy as np
import pandas as pd

import step1_settlement as s1
import step1b_binance as s1b

HERE = Path(__file__).parent
D = s1.D
DECISION_OFFSET = 0.2          # s after the second boundary: buckets <= t-1 are complete by ~t+0.13
SIGMA_WIN = 900                # s, trailing realised vol window (Binance futures 1s mid)
BOOK_MAX_AGE = 5               # s, a book snapshot counts for size only if this fresh and at the same price
MIN_ORDER = 5                  # contracts (orderMinSize, all markets)
GAS = 0.02                     # $ per market position; sensitivity 0.10
HS = [0.01, 0.02, 0.03, 0.05]
LS = [0.15, 0.5, 1.0]
KILL = {"h": 0.01, "L": 0.5, "median_edge": 0.01, "usd_per_day": 50.0}
GAP_BINS = [0, 1e-5, 3e-5, 1e-4, 3e-4, 1e-3, np.inf]
GAP_LABELS = ["<0.1bp", "0.1-0.3", "0.3-1", "1-3", "3-10", ">10bp"]
TTE_BINS = [0, 30, 60, 120, 180, 240, 300]
STALE_BINS = [0, 2, 5, 15, 30, np.inf]
EMPTY = pd.DataFrame({"t": np.array([], np.int64), "best_bid_last": [], "best_ask_last": [], "ask_sz_last": []})


def ncdf(z):
    return 0.5 * (1 + erf(z / sqrt(2)))


def dense_pm(groups, assets, lo, hi, cols):
    """Per asset: arrays over seconds [lo, hi) of the last state known at the END of each second, forward-filled."""
    out = {}
    for a in assets:
        g = groups.get(a, EMPTY)
        arrs = {}
        for c in cols:
            x = np.full(hi - lo, np.nan)
            i = g["t"].to_numpy() - lo
            ok = (i >= 0) & (i < hi - lo)
            x[i[ok]] = g[c].to_numpy()[ok]
            arrs[c] = pd.Series(x).ffill().to_numpy()
        out[a] = arrs
    return out


def load_day_pm(day, stream, cols, tokens):
    fs = sorted(D.glob(f"1s/{stream}/date={day}/*.parquet"))
    assert all(s1.date.fromisoformat(day) < s1.HOLDOUT_START for _ in fs)
    if not fs:
        return pd.DataFrame(columns=["t", "asset_id"] + cols)
    f = pd.concat(pd.read_parquet(x, columns=["bucket_start", "asset_id"] + cols) for x in fs)
    f["asset_id"] = f["asset_id"].astype(str)
    f = f[f["asset_id"].isin(tokens)]
    f["t"] = f["bucket_start"].dt.as_unit("s").astype("int64")
    return f.sort_values("t")


def main():
    m = s1.load_markets()
    step1 = pd.read_parquet(D / "step1_settlement.parquet").set_index("slug")
    gamma_up = step1["gamma_up"]
    ser = {"fut": s1b.Series(s1b.STREAMS["fut"], 0.0), "spot": s1b.Series(s1b.STREAMS["spot"], s1b.SPOT_LAG)}
    hours = {k: s1.present_hours(v) for k, v in s1b.STREAMS.items()}
    pc_hours, bk_hours = s1.present_hours("polymarket__price_change"), s1.present_hours("polymarket__book")
    fut = ser["fut"]
    # trailing realised variance per second of the futures mid, over buckets [t-900, t-1]
    lr = np.diff(np.log(fut.last), prepend=np.nan)
    lr2 = np.where(np.isfinite(lr), lr * lr, 0.0)
    cnt = np.isfinite(lr).astype(float)
    c2, cn = np.concatenate([[0], np.cumsum(lr2)]), np.concatenate([[0], np.cumsum(cnt)])
    cl_ts, _, _ = s1.load_rounds()

    # universe: Gamma-resolved, Binance-covered (Step 1b), price_change hours complete over the life
    m = m[m.index.isin(step1.index[step1["gamma_up"].notna()])].copy()
    m["down_token"] = [json.loads(t)[json.loads(o).index("Down")] for t, o in zip(m["clobTokenIds"], m["outcomes"])]
    life_hours = [s1.hours_between(r.t0 - max(r.W, 1), r.t_end) for r in m.itertuples()]
    m["cov"] = [h <= hours["fut"] and h <= hours["spot"] and h <= pc_hours for h in life_hours]
    m["book_cov"] = [h <= bk_hours for h in life_hours]
    counts = {"gamma_resolved": int(len(m)), "binance_and_pm_covered": int(m["cov"].sum()),
              "book_covered": int((m["cov"] & m["book_cov"]).sum())}
    m = m[m["cov"]]
    # ex-post near-tie finish (Step 1b blend/A rebuild): a reporting cut only
    fin = {}
    for slug, r in m.iterrows():
        s, e = [np.exp(0.5 * (np.log(ser["fut"].twap(a, b) if r.W else ser["fut"].point(b))
                              + np.log(ser["spot"].twap(a, b) if r.W else ser["spot"].point(b))))
                for a, b in ((r.t0 - r.W, r.t0), (r.t_end - r.W, r.t_end))]
        fin[slug] = abs(e / s - 1)
    m["finish_gap"] = pd.Series(fin)
    m["near_tie"] = m["finish_gap"] < 1e-4
    m["day"] = pd.to_datetime(m["t0"], unit="s", utc=True).dt.strftime("%Y-%m-%d")

    sec_rows, trades = [], []
    for day, md in m.groupby("day"):
        tokens = set(md["up_token"]) | set(md["down_token"])
        pc = load_day_pm(day, "polymarket__price_change", ["best_bid_last", "best_ask_last"], tokens)
        bk = load_day_pm(day, "polymarket__book", ["best_ask_last", "ask_sz_last"], tokens)
        pcg, bkg = dict(tuple(pc.groupby("asset_id"))), dict(tuple(bk.groupby("asset_id")))
        for slug, r in md.iterrows():
            t0, te, W = int(r.t0), int(r.t_end), int(r.W)
            lo, hi = t0 - 10, te + 2
            P = dense_pm(pcg, [r.up_token, r.down_token], lo, hi, ["best_bid_last", "best_ask_last"])
            B = dense_pm(bkg, [r.up_token, r.down_token], lo, hi, ["best_ask_last", "ask_sz_last"]) if r.book_cov else None
            Bt = {a: bkg.get(a, EMPTY)["t"].to_numpy() for a in (r.up_token, r.down_token)} if r.book_cov else None
            # start reference (settlement approximation, exactly Step 1b blend/A)
            if W:
                k0 = np.exp(0.5 * (np.log(ser["fut"].twap(t0 - W, t0)) + np.log(ser["spot"].twap(t0 - W, t0))))
            else:
                k0 = np.exp(0.5 * (np.log(ser["fut"].point(t0)) + np.log(ser["spot"].point(t0))))
            lk0 = np.log(k0)
            outcome = gamma_up[slug]
            last_fill, last_zero = {}, {}                    # (token, h, L) -> touch price already taken / already seen at size 0
            positions = set()
            for t in range(t0 + 1, te):
                tau = te - t
                i_f, i_s = t - 1 - fut.T0, t - 1 - ser["spot"].T0
                sf, ss = fut.last[i_f], ser["spot"].last[i_s]
                if not (np.isfinite(sf) and np.isfinite(ss) and np.isfinite(lk0)):
                    continue
                ls_t = 0.5 * (np.log(sf) + np.log(ss))
                j = t - fut.T0                               # buckets [t-900, t-1]
                n = cn[j] - cn[j - SIGMA_WIN]
                if n < SIGMA_WIN / 2:
                    continue
                var1 = (c2[j] - c2[j - SIGMA_WIN]) / n       # per-second variance
                if W == 0:
                    mu, V = ls_t, var1 * tau
                elif tau > W:
                    mu, V = ls_t, var1 * (tau - 2 * W / 3)
                else:                                        # inside the final window: known part + unknown part
                    a0, a1 = te - W - fut.T0, t - fut.T0     # buckets [te-W, t-1], receive-time spot, no shift
                    kf = np.mean(fut.tw[a0:a1]) if a1 > a0 else sf
                    ks = np.mean(ser["spot"].tw[te - W - ser["spot"].T0:t - ser["spot"].T0]) if a1 > a0 else ss
                    known = np.exp(0.5 * (np.log(kf) + np.log(ks)))
                    mu = np.log(((W - tau) * known + tau * np.exp(ls_t)) / W)
                    V = var1 * tau ** 3 / (3 * W * W)
                p = ncdf((mu - lk0) / sqrt(V)) if V > 0 else float(mu >= lk0)
                k = t - 1 - lo                                   # Polymarket state known at t
                ub, ua = P[r.up_token]["best_bid_last"][k], P[r.up_token]["best_ask_last"][k]
                da = P[r.down_token]["best_ask_last"][k]
                if not (np.isfinite(ub) and np.isfinite(ua)):
                    continue
                mid = (ub + ua) / 2
                gap_now = abs(ls_t - lk0)
                cl_i = np.searchsorted(cl_ts, t + DECISION_OFFSET - 0.5, side="right") - 1   # round known ~0.5 s after stamp
                stale = t + DECISION_OFFSET - (cl_ts[cl_i] + 0.5) if cl_i >= 0 else np.nan
                sz_up = np.nan
                if B is not None:
                    bt = Bt[r.up_token]
                    q = np.searchsorted(bt, t, side="left") - 1
                    if q >= 0 and t - bt[q] <= BOOK_MAX_AGE and B[r.up_token]["best_ask_last"][k] == ua:
                        sz_up = B[r.up_token]["ask_sz_last"][k]
                sec_rows.append((slug, t, tau, p, mid, (ua - ub) / 2, ua, da, gap_now, stale, sz_up, r.near_tie, outcome))

                # ---- Step 3: taker signals on this second, every (h, L)
                for tok, fair, ask in ((r.up_token, p, ua), (r.down_token, 1 - p, da)):
                    if not np.isfinite(ask) or fair - ask < min(HS):
                        continue
                    for L in LS:
                        arr = t + DECISION_OFFSET + L
                        ka = int(np.floor(arr)) - lo                 # state at the end of the arrival second
                        if ka >= hi - lo:
                            continue
                        fill = P[tok]["best_ask_last"][ka]
                        if not np.isfinite(fill) or fill > ask:
                            continue                                 # book moved away: no fill
                        size = 0.0
                        if B is not None:
                            bt = Bt[tok]
                            q = np.searchsorted(bt, arr, side="right") - 1
                            if q >= 0 and arr - bt[q] <= BOOK_MAX_AGE and B[tok]["best_ask_last"][ka] == fill:
                                size = float(B[tok]["ask_sz_last"][ka])
                        if size < MIN_ORDER:
                            size = 0.0
                        for h in HS:
                            if fair - ask < h:
                                continue
                            key = (tok, h, L)
                            seen = last_fill if size > 0 else last_zero
                            if seen.get(key) == fill:
                                continue                             # this touch already taken (or already seen with no size)
                            seen[key] = fill
                            win = outcome if tok == r.up_token else 1 - outcome
                            trades.append({"slug": slug, "day": day, "t": t, "tau": tau, "token": "up" if tok == r.up_token else "down",
                                           "h": h, "L": L, "fair": fair, "signal_ask": ask, "fill": fill, "size": size,
                                           "edge_at_fill": fair - fill, "pnl_per_contract": win - fill,
                                           "gap_now": gap_now, "near_tie": bool(r.near_tie)})
    sec = pd.DataFrame(sec_rows, columns=["slug", "t", "tau", "p", "mid", "half_spread", "up_ask", "down_ask", "gap_now",
                                          "cl_stale", "up_ask_size", "near_tie", "outcome"])
    tr = pd.DataFrame(trades)
    sec.to_parquet(D / "step2_seconds.parquet")
    tr.to_parquet(D / "step3_trades.parquet")
    m[["t0", "t_end", "rule", "W", "finish_gap", "near_tie", "day", "book_cov"]].to_parquet(D / "step23_markets.parquet")
    return m, sec, tr, counts


def summarize(m, sec, tr, counts):
    out = {"counts": {**counts, "near_tie_finish_markets": int(m["near_tie"].sum())},
           "note_ii": "(ii) excludes markets whose FINISH is within 1 bp of a tie: an ex-post reporting cut; "
                      "realised P&L on (ii) is biased by construction (coin-flip finishes removed)"}
    days = len(m) / 288.0                                            # market-days of full coverage
    out["dev_days_equiv"] = days
    sec["gap"] = sec["p"] - sec["mid"]
    sec["tte_bin"] = pd.cut(sec["tau"], TTE_BINS, right=False).astype(str)
    sec["stale_bin"] = pd.cut(sec["cl_stale"], STALE_BINS, right=False).astype(str)
    sec["gap_bin"] = pd.cut(sec["gap_now"], GAP_BINS, labels=GAP_LABELS, include_lowest=True).astype(str)
    sec["beyond_hs"] = sec["gap"].abs() > sec["half_spread"]
    for tag, s in (("i_all", sec), ("ii_excl_near_tie_finish", sec[~sec["near_tie"]])):
        o = {"n_seconds": len(s), "n_markets": int(s["slug"].nunique()),
             "calibration": {}, "brier_model": float(((s["p"] - s["outcome"]) ** 2).mean()),
             "brier_mid": float(((s["mid"] - s["outcome"]) ** 2).mean())}
        cb = pd.cut(s["p"], np.linspace(0, 1, 11), include_lowest=True)
        o["calibration"] = s.groupby(cb, observed=True).agg(n=("outcome", "size"), p=("p", "mean"), realised=("outcome", "mean"),
                                                            mid=("mid", "mean")).round(4).reset_index().astype(str).to_dict("records")
        agg = dict(n=("gap", "size"), gap_mean=("gap", "mean"), gap_abs_median=("gap", lambda x: x.abs().median()),
                   gap_abs_p90=("gap", lambda x: x.abs().quantile(0.9)), frac_beyond_half_spread=("beyond_hs", "mean"),
                   half_spread_median=("half_spread", "median"))
        o["by_tte"] = s.groupby("tte_bin").agg(**agg).round(4).to_dict("index")
        o["by_cl_staleness"] = s.groupby("stale_bin").agg(**agg).round(4).to_dict("index")
        o["by_gap_now"] = s.groupby("gap_bin").agg(**agg).round(4).to_dict("index")
        b = s[s["beyond_hs"]]
        o["size_at_touch_when_beyond_hs"] = {"n": len(b), "frac_size_known": float(b["up_ask_size"].notna().mean()),
                                             "median": float(b["up_ask_size"].median()),
                                             "p90": float(b["up_ask_size"].quantile(0.9))}
        out[f"step2_{tag}"] = o

    def tsum(t, days_):
        f = t[t["size"] > 0]
        if not len(f):
            return {"n_signals": len(t), "n_fills": 0}
        notional = (f["size"] * f["fill"]).sum()
        pos = f.groupby(["slug", "token"]).ngroups
        pnl = (f["size"] * f["pnl_per_contract"]).sum() - GAS * pos
        per_mkt = f.assign(p=f["size"] * f["pnl_per_contract"]).groupby("slug")["p"].sum()
        return {"n_signals": len(t), "n_fills": len(f), "fills_per_day": len(f) / days_,
                "median_edge_at_fill": float(f["edge_at_fill"].median()), "mean_edge_at_fill": float(f["edge_at_fill"].mean()),
                "median_edge_all_signals_incl_zero_size": float(t["edge_at_fill"].median()),
                "realised_pnl_per_contract_mean": float((f["size"] * f["pnl_per_contract"]).sum() / f["size"].sum()),
                "notional_usd_per_day": float(notional / days_), "model_edge_usd_per_day": float((f["size"] * f["edge_at_fill"]).sum() / days_),
                "realised_pnl_usd_per_day_after_gas": float(pnl / days_),
                "realised_pnl_t_by_market": float(per_mkt.mean() / per_mkt.std() * np.sqrt(len(per_mkt))) if len(per_mkt) > 1 else np.nan,
                "gas_sens_0.10_usd_per_day": float(((f["size"] * f["pnl_per_contract"]).sum() - 0.10 * pos) / days_),
                "size_quantiles": f["size"].quantile([.1, .5, .9, .99]).round(1).to_dict()}

    tr["gap_bin"] = pd.cut(tr["gap_now"], GAP_BINS, labels=GAP_LABELS, include_lowest=True).astype(str)
    days_ii = (~m["near_tie"]).sum() / 288.0
    out["step3"] = {}
    for tag, t, dd in (("i_all", tr, days), ("ii_excl_near_tie_finish", tr[~tr["near_tie"]], days_ii)):
        o = {}
        for (h, L), g in t.groupby(["h", "L"]):
            o[f"h={h:.2f},L={L}"] = tsum(g, dd)
        k = t[(t["h"] == KILL["h"]) & (t["L"] == KILL["L"])]
        o["kill_config_by_gap_now"] = {b: tsum(g, dd) for b, g in k.groupby("gap_bin")}
        o["kill_config_reliable_gap_ge_3bp"] = tsum(k[k["gap_now"] >= 3e-4], dd)
        out["step3"][tag] = o
    for tag in ("i_all", "ii_excl_near_tie_finish"):
        s = out["step3"][tag][f"h={KILL['h']:.2f},L={KILL['L']}"]
        med, usd = s.get("median_edge_at_fill", np.nan), s.get("notional_usd_per_day", 0.0)
        out[f"kill_{tag}"] = {"median_edge_at_fill": med, "notional_usd_per_day": usd,
                              "killed": bool(not (med >= KILL["median_edge"]) or usd < KILL["usd_per_day"])}
    return out


if __name__ == "__main__":
    m, sec, tr, counts = main()
    out = summarize(m, sec, tr, counts)
    (HERE / "step23.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: out[k] for k in ("counts", "dev_days_equiv", "kill_i_all", "kill_ii_excl_near_tie_finish")},
                     indent=1, default=str))
