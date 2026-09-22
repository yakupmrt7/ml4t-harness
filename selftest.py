"""Prove the harness works in BOTH directions before trusting it on real data.

  A. Random walk            -> must find nothing.
  B. Planted weak signal    -> must find it (gross), then tell you honestly
                               whether it survives costs.
  C. Leaky feature          -> must scream.
  D. Overlap-leakage demo   -> naive shuffled KFold "finds" edge in A's pure
                               noise; purged CV does not.

Run:  python selftest.py            (~2-4 min on 2 cores)
"""
import time

import numpy as np
import pandas as pd

from harness.backtest import CostModel
from harness.cv import WalkForward
from harness.features import basic_features
from harness.labeling import ewm_vol, triple_barrier
from harness.nulls import validation_report
from harness.weights import average_uniqueness, effective_n

BAR = "5min"
DAYS = 120
H = 12  # label horizon: 12 x 5min = 1h


def synth(days=DAYS, signal_beta=0.0, phi=0.97, seed=1):
    """GARCH(1,1)-ish 5-min returns ~BTC scale. Optional hidden AR(1) state z
    that drives the NEXT bar's drift: r[t+1] = sigma * (beta*z[t] + eps)."""
    rng = np.random.default_rng(seed)
    n = days * 288
    idx = pd.date_range("2026-01-01", periods=n, freq=BAR, tz="UTC")
    eps = rng.standard_t(5, n) / np.sqrt(5 / 3)
    z = np.zeros(n)
    s2 = np.full(n, 1e-6)
    r = np.zeros(n)
    w, a, b = 1e-6 * 0.03, 0.07, 0.90
    for t in range(1, n):
        z[t] = phi * z[t - 1] + np.sqrt(1 - phi**2) * rng.normal()
        s2[t] = w + a * r[t - 1] ** 2 + b * s2[t - 1]
        r[t] = np.sqrt(s2[t]) * (signal_beta * z[t - 1] + eps[t])
    close = pd.Series(30000 * np.exp(np.cumsum(r)), idx)
    vol = pd.Series(np.abs(rng.normal(50, 15, n)), idx)
    bars = pd.DataFrame({"close": close, "volume": vol,
                         "taker_buy_volume": vol * rng.uniform(0.3, 0.7, n)})
    # the model only sees a NOISY version of z
    z_obs = pd.Series(z + rng.normal(0, 0.5, n), idx)
    return bars, z_obs


def build(bars, extra=None):
    X = basic_features(bars)
    if extra is not None:
        for k, v in extra.items():
            X[k] = v
    close = bars["close"]
    width = ewm_vol(close, 288) * np.sqrt(H)
    labels = triple_barrier(close, H, width, pt_mult=1.0, sl_mult=1.0)
    u = average_uniqueness(close.index, labels)
    return X, labels, u


def run(name, bars, extra=None, costs=CostModel(fee_bps=2, slippage_bps=0.5)):
    print(f"\n=== {name} ===")
    t = time.time()
    X, labels, u = build(bars, extra)
    print(f"  labels {len(labels):,}  effective independent n ~{effective_n(u):,.0f}")
    res = validation_report(
        X, labels, bars["close"], WalkForward(n_splits=6, min_train_frac=0.4),
        costs=costs, weights=u, pos_kwargs={"mode": "sign", "threshold": 0.02, "smooth": H},
        n_perm=6, n_shift=200,
    )
    print(f"  ({time.time() - t:.0f}s)")
    return res


if __name__ == "__main__":
    bars_a, z_a = synth(signal_beta=0.0, seed=1)
    bars_b, z_b = synth(signal_beta=0.06, seed=2)

    A = run("A. random walk (expect: nothing)", bars_a, {"z_obs": z_a})
    B = run("B. planted signal, beta=0.06 (expect: gross edge detected)", bars_b, {"z_obs": z_b})
    leak = np.log(bars_a["close"].shift(-H) / bars_a["close"])
    leak = leak + np.random.default_rng(3).normal(0, leak.std(), len(leak))
    C = run("C. leaky feature on random walk (expect: alarms)", bars_a, {"leak": leak})

    v = lambda r, k: next(ok for kk, ok in r["verdicts"].items() if kk.startswith(k))
    checks = {
        "A: no timing edge found": not v(A, "timing edge"),
        "A: pipeline clean": v(A, "pipeline clean"),
        "A: purge probe exposes overlap leakage (naive AUC >> purged)":
            A["purge_probe_naive_auc"] - A["purge_probe_purged_auc"] > 0.02,
        "B: planted edge detected (gross shift-null p<0.05)": v(B, "timing edge"),
        "B: OOS AUC > 0.5": B["oos_auc"] > 0.51,
        "C: lookahead audit flags 'leak'": "leak" in C["lookahead_suspects"],
        "C: implausibility alarm fires": not v(C, "not implausibly good"),
    }
    print("\n=== SELF-TEST ===")
    for k, ok in checks.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {k}")
    print("\nHARNESS OK" if all(checks.values()) else "\nHARNESS BROKEN - do not trust results")
