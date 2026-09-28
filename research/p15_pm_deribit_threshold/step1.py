"""p15 step 1 (PLAN.md + amendment 1): Deribit risk-neutral probability vs Polymarket price, DEV ONLY.

Per in-scope dev market and each UTC hour close t from its first trade to T - 1 h:
  PM(t)   = share-weighted VWAP of YES-equivalent taker-trade prices in (t - 60 min, t]
  P_RN(t) = Deribit digital from smiles fitted on option trades in (t - 60 min, t], T bracketed by two
            expiries, strike mapped K_D = K (1 + b(t)) with b the causal 7-day median basis,
            k(K_D) inside the traded k-range of both bracketing smiles (main set)
  D       = PM - P_RN
Outputs: data/collector/p15/step1_panel.parquet (gitignored), step1.json, step1.log.
KILL C: in the P_RN < 15% bucket, median D < 2 pp.

  python research/p15_pm_deribit_threshold/step1.py
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import surface as S  # noqa: E402
from common import DIR, in_scope_markets, load_trades, split  # noqa: E402
from harness.data import load_binance_klines  # noqa: E402

DERIBIT = Path("data/collector/p11/deribit_opt")
ET = "America/New_York"
PRN_BUCKETS = [0, 0.05, 0.15, 0.35, 0.65, 0.85, 0.95, 1.0000001]
TAU_BUCKETS_D = [0, 1, 3, 7, np.inf]
N_BOOT = 1000


class Deribit:
    """Day-file cache of option trades with parsed instruments; window queries by time."""

    def __init__(self):
        self.cache = {}

    def day(self, d):
        if d not in self.cache:
            f = DERIBIT / f"opt_{d}.parquet"
            if not f.exists():
                self.cache[d] = None
            else:
                x = pd.read_parquet(f, columns=["timestamp", "instrument_name", "price", "mark_price", "index_price"])
                x = x[x.instrument_name.str.match(r"^BTC-\d{1,2}[A-Z]{3}\d{2}-\d+-[CP]$")]
                x = x.join(S.parse_instruments(x.instrument_name))
                x["t"] = pd.to_datetime(x.timestamp, unit="ms", utc=True)
                self.cache[d] = x.sort_values("t").reset_index(drop=True)
            if len(self.cache) > 6:
                self.cache.pop(next(iter(self.cache)))
        return self.cache[d]

    def window(self, t, width=pd.Timedelta(minutes=60)):
        days = sorted({(t - width).date(), t.date()})
        parts = [p for p in (self.day(str(d)) for d in days) if p is not None]
        if not parts:
            return None
        x = pd.concat(parts)
        return x[(x.t > t - width) & (x.t <= t)]


def basis_samples():
    """Causal basis samples: for 1,000 evenly spaced Deribit trades per day, index_price / Binance close of
    the last COMPLETED minute at or before the trade - 1 (amendment 1)."""
    close = load_binance_klines("data/raw/spot/BTCUSDT-1m-*.zip")["close"]          # index = close edge
    rows = []
    for f in sorted(DERIBIT.glob("opt_*.parquet")):
        x = pd.read_parquet(f, columns=["timestamp", "index_price"])
        if len(x) == 0:
            continue
        x = x.iloc[np.linspace(0, len(x) - 1, min(1000, len(x))).astype(int)]
        tt = pd.to_datetime(x.timestamp, unit="ms", utc=True)
        c = close.reindex(tt.dt.floor("min"), method="ffill").to_numpy()   # bar closing at floor(t) <= t
        rows.append(pd.DataFrame({"t": tt.to_numpy(), "b": x.index_price.to_numpy() / c - 1}))
    b = pd.concat(rows).dropna().sort_values("t")
    return b.t.to_numpy(), b.b.to_numpy()


def causal_basis(bt, bv, t):
    lo, hi = np.searchsorted(bt, np.datetime64(t - pd.Timedelta(days=7)), "right"), np.searchsorted(bt, np.datetime64(t), "right")
    return float(np.median(bv[lo:hi])) if hi > lo else np.nan


def prob_event(sm, t, T, kind, k_low, k_high, b, index_now):
    """P_RN of the market's YES event and whether every strike used is inside both smiles' k-range."""
    def pa(K):
        return S.prob_above(sm, t, T, K * (1 + b), index_now)
    if kind == "above":
        p, d = pa(k_low)
        return p, d.get("k_inside_fit", False), d
    if kind == "below":
        p, d = pa(k_high)
        return (1 - p if np.isfinite(p) else np.nan), d.get("k_inside_fit", False), d
    p1, d1 = pa(k_low)
    p2, d2 = pa(k_high)
    p = p1 - p2 if np.isfinite(p1) and np.isfinite(p2) else np.nan
    return p, d1.get("k_inside_fit", False) and d2.get("k_inside_fit", False), d1


def build_panel():
    s = split()
    mk = in_scope_markets(dev_only=True)
    mk = mk[mk.yes_gamma.notna()].set_index("id")
    tr = load_trades(dev_only=True)
    tr = tr[tr.market_id.isin(mk.index)]
    tr["t"] = tr.time.dt.ceil("h")                                     # (t - 60 min, t] -> hour close t
    tr["pv"] = tr.p_yes * tr["size"]
    g = tr.groupby(["market_id", "t"]).agg(pv=("pv", "sum"), sz=("size", "sum"), n=("size", "size"))
    g["pm"] = g.pv / g.sz
    g = g.reset_index()
    g = g.join(mk[["T_utc", "kind", "k_low", "k_high", "family", "yes_gamma"]], on="market_id")
    g = g[g.t <= g.T_utc - pd.Timedelta(hours=1)]
    assert (g.T_utc < s["dev_end"]).all()
    print(f"dev markets {len(mk)}, with trades {tr.market_id.nunique()}, (market, hour) rows {len(g)}, "
          f"decision hours {g.t.nunique()}", flush=True)
    bt, bv = basis_samples()
    der = Deribit()
    out, t0 = [], time.time()
    for i, (t, grp) in enumerate(g.groupby("t")):
        w = der.window(t)
        if w is None or w.empty:
            continue
        sm = S.smiles_at(w, t)
        index_now = float(w.index_price.iloc[-1])
        b = causal_basis(bt, bv, t)
        for r in grp.itertuples():
            p, inside, d = prob_event(sm, t, r.T_utc, r.kind, r.k_low, r.k_high, b if np.isfinite(b) else 0.0,
                                      index_now)
            out.append((r.market_id, t, p, inside, np.isfinite(b), d.get("atm_vol", np.nan), d.get("tau1_d", np.nan),
                        d.get("tau2_d", np.nan), len(sm)))
        if i % 500 == 0:
            print(f"  hour {i}/{g.t.nunique()} {time.time() - t0:.0f} s", flush=True)
    p = pd.DataFrame(out, columns=["market_id", "t", "p_rn", "k_inside", "basis_ok", "atm_vol", "tau1_d", "tau2_d",
                                   "n_smiles"])
    panel = g.merge(p, on=["market_id", "t"], how="left")
    panel["tau_d"] = (panel.T_utc - panel.t).dt.total_seconds() / 86400
    panel["D"] = panel.pm - panel.p_rn
    panel["fix_date"] = panel.T_utc.dt.tz_convert(ET).dt.date.astype(str)
    panel.to_parquet(DIR / "step1_panel.parquet")
    return panel


def boot_median(x, clusters, rng):
    """Median of x with a cluster (fixing date) bootstrap 95% CI."""
    x, clusters = np.asarray(x), np.asarray(clusters)
    uc, inv = np.unique(clusters, return_inverse=True)
    groups = [x[inv == j] for j in range(len(uc))]
    meds = []
    for _ in range(N_BOOT):
        pick = rng.integers(0, len(uc), len(uc))
        meds.append(np.median(np.concatenate([groups[j] for j in pick])))
    return float(np.median(x)), float(np.percentile(meds, 2.5)), float(np.percentile(meds, 97.5))


def cluster_t(diff, clusters):
    d = pd.Series(np.asarray(diff)).groupby(np.asarray(clusters)).mean()
    return float(d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))) if len(d) > 2 else np.nan


def report(panel):
    rng = np.random.default_rng(0)
    res = {}
    n_all = len(panel)
    valid = panel.p_rn.notna()
    main = valid & panel.k_inside & panel.basis_ok
    res["rows"] = {"all": int(n_all), "p_rn_defined": int(valid.sum()), "main (k inside, basis ok)": int(main.sum()),
                   "markets_main": int(panel[main].market_id.nunique()),
                   "fix_dates_main": int(panel[main].fix_date.nunique())}
    print(json.dumps(res["rows"], indent=1))
    m = panel[main].copy()
    m["prn_b"] = pd.cut(m.p_rn, PRN_BUCKETS, right=False)
    m["tau_b"] = pd.cut(m.tau_d, TAU_BUCKETS_D, right=False)
    rows = []
    for (pb, tb), x in m.groupby(["prn_b", "tau_b"], observed=True):
        if len(x) < 30:
            continue
        med, lo, hi = boot_median(x.D, x.fix_date, rng)
        rows.append({"p_rn": str(pb), "tau_d": str(tb), "rows": len(x), "markets": x.market_id.nunique(),
                     "dates": x.fix_date.nunique(), "D_median_pp": 100 * med, "ci_lo": 100 * lo, "ci_hi": 100 * hi,
                     "D_mean_pp": 100 * x.D.mean()})
    tab = pd.DataFrame(rows)
    print("\nGap D = PM - P_RN (pp), main rows, by P_RN x tau bucket (CI: fixing-date bootstrap):")
    print(tab.round(2).to_string(index=False))
    res["gap_table"] = tab.round(4).to_dict(orient="records")
    rows = []
    for pb, x in m.groupby("prn_b", observed=True):
        med, lo, hi = boot_median(x.D, x.fix_date, rng)
        rows.append({"p_rn": str(pb), "rows": len(x), "markets": x.market_id.nunique(), "dates": x.fix_date.nunique(),
                     "D_median_pp": 100 * med, "ci_lo": 100 * lo, "ci_hi": 100 * hi, "D_mean_pp": 100 * x.D.mean(),
                     "pm_mean": x.pm.mean(), "p_rn_mean": x.p_rn.mean(), "realised": x.yes_gamma.mean()})
    tabp = pd.DataFrame(rows)
    print("\nBy P_RN bucket (all tau):")
    print(tabp.round(3).to_string(index=False))
    res["gap_by_prn"] = tabp.round(5).to_dict(orient="records")
    # calibration on the same rows
    y = m.yes_gamma.to_numpy()
    b_pm, b_rn = (m.pm - y) ** 2, (m.p_rn - y) ** 2
    res["brier"] = {"pm": float(b_pm.mean()), "p_rn": float(b_rn.mean()),
                    "pm_minus_rn": float((b_pm - b_rn).mean()),
                    "t_by_fix_date": cluster_t(b_pm - b_rn, m.fix_date)}
    print("\nBrier (same rows):", json.dumps(res["brier"]))
    rel = []
    for name, col in (("pm", "pm"), ("p_rn", "p_rn")):
        rb = pd.cut(m[col], np.linspace(0, 1, 11), include_lowest=True)
        z = m.groupby(rb, observed=True).agg(n=("yes_gamma", "size"), forecast=(col, "mean"), realised=("yes_gamma", "mean"),
                                             dates=("fix_date", "nunique"))
        z["forecaster"] = name
        rel.append(z.reset_index().rename(columns={col: "bin"}))
    rel = pd.concat(rel)
    rel["bin"] = rel["bin"].astype(str)
    print("\nReliability (10 bins):")
    print(rel.round(3).to_string(index=False))
    res["reliability"] = rel.round(4).to_dict(orient="records")
    low = m[m.p_rn < 0.15]
    med, lo, hi = boot_median(low.D, low.fix_date, rng)
    res["kill_C"] = {"bucket": "P_RN < 15%", "rows": int(len(low)), "markets": int(low.market_id.nunique()),
                     "dates": int(low.fix_date.nunique()), "D_median_pp": 100 * med, "ci": [100 * lo, 100 * hi],
                     "threshold_pp": 2.0, "fires": bool(med < 0.02)}
    print("\nKILL C:", json.dumps(res["kill_C"]))
    # reported alongside: extrapolated-k rows (never used for the kill)
    ex = panel[valid & ~panel.k_inside]
    res["extrapolated_rows"] = {"rows": int(len(ex)), "D_median_pp": float(100 * ex.D.median()) if len(ex) else None}
    (HERE / "step1.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    f = DIR / "step1_panel.parquet"
    panel = pd.read_parquet(f) if (len(sys.argv) > 1 and sys.argv[1] == "--report-only") else build_panel()
    report(panel)
