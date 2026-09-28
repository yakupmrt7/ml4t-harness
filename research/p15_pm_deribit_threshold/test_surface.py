"""Tests for p15 surface.py and step0.parse_fixing on synthetic inputs with known answers.

  python research/p15_pm_deribit_threshold/test_surface.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).parent))
import surface as S  # noqa: E402


def synthetic_trades(t, expiries, F_ratio, vol_fn, index=100_000.0, n_per=40, seed=0):
    """Mark prices from a known forward and smile; index jitters a little between trades."""
    rng = np.random.default_rng(seed)
    rows = []
    for e in expiries:
        tau = (e - t).total_seconds() / S.YEAR
        for K in np.linspace(80_000, 120_000, 17):
            for cp in "CP":
                for j in range(n_per // 17 + 1):
                    ts = t - pd.Timedelta(seconds=int(rng.integers(0, 3500)))
                    ix = index * (1 + 1e-4 * rng.standard_normal())
                    F = F_ratio[e] * ix
                    k = np.log(K / F)
                    mark = S.fwd_price(cp, k, vol_fn(k) * np.sqrt(tau))
                    rows.append((ts, f"BTC-{e.strftime('%d%b%y').upper().lstrip('0')}-{int(K)}-{cp}", mark, ix))
    d = pd.DataFrame(rows, columns=["t", "instrument_name", "mark_price", "index_price"])
    return d.join(S.parse_instruments(d.instrument_name))


def test_flat_vol_digital():
    t = pd.Timestamp("2025-06-02 12:00", tz="UTC")
    e1, e2 = pd.Timestamp("2025-06-04 08:00", tz="UTC"), pd.Timestamp("2025-06-06 08:00", tz="UTC")
    fr = {e1: 1.0005, e2: 1.0010}
    tr = synthetic_trades(t, [e1, e2], fr, lambda k: 0.50)
    sm = S.smiles_at(tr, t)
    assert len(sm) == 2, sm
    for s in sm:
        assert abs(s.f_ratio - fr[s.expiry]) < 2e-4, (s.f_ratio, fr[s.expiry])
    T = pd.Timestamp("2025-06-05 16:00", tz="UTC")
    tau = (T - t).total_seconds() / S.YEAR
    wt = (tau - sm[0].tau) / (sm[1].tau - sm[0].tau)
    F = 100_000 * np.exp((1 - wt) * np.log(fr[e1]) + wt * np.log(fr[e2]))
    for K in (95_000, 100_000, 104_000):
        p, diag = S.prob_above(sm, t, T, K, 100_000.0)
        d2 = (np.log(F / K) - 0.5 * 0.25 * tau) / (0.5 * np.sqrt(tau))
        assert abs(p - norm.cdf(d2)) < 0.003, (K, p, norm.cdf(d2))
        assert diag["k_inside_fit"]


def test_skew_enters_digital():
    """With put skew (vol falling in k), the digital call is ABOVE N(d2) at the ATM vol."""
    t = pd.Timestamp("2025-06-02 12:00", tz="UTC")
    e1, e2 = pd.Timestamp("2025-06-04 08:00", tz="UTC"), pd.Timestamp("2025-06-06 08:00", tz="UTC")
    tr = synthetic_trades(t, [e1, e2], {e1: 1.0, e2: 1.0}, lambda k: 0.50 - 0.8 * k)
    sm = S.smiles_at(tr, t)
    T = pd.Timestamp("2025-06-05 16:00", tz="UTC")
    tau = (T - t).total_seconds() / S.YEAR
    p, _ = S.prob_above(sm, t, T, 100_000.0, 100_000.0)
    d2 = -0.5 * 0.5 * np.sqrt(tau)
    assert p > norm.cdf(d2) + 0.01, (p, norm.cdf(d2))


def test_no_bracket_no_value():
    t = pd.Timestamp("2025-06-02 12:00", tz="UTC")
    e1 = pd.Timestamp("2025-06-04 08:00", tz="UTC")
    tr = synthetic_trades(t, [e1], {e1: 1.0}, lambda k: 0.5)
    sm = S.smiles_at(tr, t)
    p, _ = S.prob_above(sm, t, pd.Timestamp("2025-06-05 16:00", tz="UTC"), 100_000.0, 100_000.0)
    assert np.isnan(p)
    p, _ = S.prob_above(sm, t, pd.Timestamp("2025-06-03 16:00", tz="UTC"), 100_000.0, 100_000.0)
    assert np.isnan(p)                                       # before the first expiry: not bracketed


def test_window_is_trailing():
    t = pd.Timestamp("2025-06-02 12:00", tz="UTC")
    e1, e2 = pd.Timestamp("2025-06-04 08:00", tz="UTC"), pd.Timestamp("2025-06-06 08:00", tz="UTC")
    tr = synthetic_trades(t, [e1, e2], {e1: 1.0, e2: 1.0}, lambda k: 0.5)
    future = tr.copy()
    future["t"] = future.t + pd.Timedelta(hours=2)
    future["mark_price"] = future.mark_price * 3                # garbage after t must not matter
    a = S.smiles_at(tr, t)
    b = S.smiles_at(pd.concat([tr, future]), t)
    assert [s.coef.round(12).tolist() for s in a] == [s.coef.round(12).tolist() for s in b]


def test_parse_fixing():
    import step0
    d1 = ("This market will resolve to \"Yes\" if the Binance 1 minute candle for BTCUSDT 13 Dec '24 12:00 "
          "in the ET timezone (noon) has a final “Close” price of 100,000.01 or higher.")
    T, sym = step0.parse_fixing(d1, pd.Timestamp("2024-12-13 12:00", tz="UTC"))
    assert T == pd.Timestamp("2024-12-13 17:00", tz="UTC") and sym == "BTCUSDT"   # EST
    d2 = "if the Binance 1 minute candle for BTC/USDT 12:00 in the ET timezone (noon) on the date specified"
    T, _ = step0.parse_fixing(d2, pd.Timestamp("2025-07-18 16:00", tz="UTC"))
    assert T == pd.Timestamp("2025-07-18 16:00", tz="UTC")                           # EDT
    assert step0.parse_fixing("no candle here", pd.Timestamp("2025-07-18", tz="UTC"))[0] is pd.NaT


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
