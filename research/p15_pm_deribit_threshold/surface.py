"""p15 step 1: Deribit risk-neutral probability of {S_T > K} from option trades in a trailing window.

Conventions (PLAN.md step 1):
- Deribit BTC options are inverse: price in BTC = (Black-76 USD price) / F, with F the expiry's forward.
  In forward units a call is c = N(d1) - (K/F) N(d2), a put p = (K/F) N(-d2) - N(-d1).
- Forward per expiry from put-call parity on near-ATM strikes: c - p = 1 - K/F, using call/put mark
  pairs at the same strike within 120 s of each other, as a ratio to the index (median over pairs).
  No pair -> the expiry is dropped (no silent F = index fallback).
- Mark IV per trade from its MARK price (Deribit's smoothed surface), OTM side only.
- Smile per expiry: vega-weighted least squares, total variance w(k) = a + b k + c k^2, k = ln(K/F);
  >= 5 distinct strikes, w > 0 on the fitted range.
- Maturity T between two surviving expiries: w interpolated linearly in tau at fixed k, ln(F/index)
  linearly in tau. No extrapolation.
- P_RN(S_T > K) = -dC/dK, numerical +-0.25% of K through the smile (includes the skew term).
Expiry time: 08:00 UTC on the date in the instrument name.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm

YEAR = 365.0 * 86400.0
MIN_STRIKES = 5
PAIR_SECONDS = 120
ATM_BAND = 0.05          # |ln(K/index)| for parity pairs


def parse_instruments(names: pd.Series) -> pd.DataFrame:
    p = names.str.extract(r"^BTC-(\d{1,2}[A-Z]{3}\d{2})-(\d+)-([CP])$")
    expiry = pd.to_datetime(p[0], format="%d%b%y", utc=True) + pd.Timedelta(hours=8)
    return pd.DataFrame({"expiry": expiry, "K": p[1].astype(float), "cp": p[2]}, index=names.index)


def fwd_price(cp, k, sig_sqrt_t):
    """Option value in forward units (divide USD by F), k = ln(K/F)."""
    d1 = -k / sig_sqrt_t + 0.5 * sig_sqrt_t
    d2 = d1 - sig_sqrt_t
    if cp == "C":
        return norm.cdf(d1) - np.exp(k) * norm.cdf(d2)
    return np.exp(k) * norm.cdf(-d2) - norm.cdf(-d1)


def implied_total_sd(cp, k, value):
    """sigma*sqrt(tau) from a forward-unit price; NaN outside no-arbitrage bounds."""
    intrinsic = max(1 - np.exp(k), 0.0) if cp == "C" else max(np.exp(k) - 1, 0.0)
    upper = 1.0 if cp == "C" else np.exp(k)
    if not (intrinsic + 1e-10 < value < upper - 1e-10):
        return np.nan
    try:
        return brentq(lambda s: fwd_price(cp, k, s) - value, 1e-5, 5.0, xtol=1e-9)
    except ValueError:
        return np.nan


def forward_ratio(tr: pd.DataFrame) -> float:
    """Median of F/index over call/put mark pairs at the same strike within PAIR_SECONDS.
    tr: one expiry's trades with columns t, K, cp, mark_price, index_price."""
    near = tr[np.abs(np.log(tr.K / tr.index_price)) < ATM_BAND]
    c, p = near[near.cp == "C"].sort_values("t"), near[near.cp == "P"].sort_values("t")
    if c.empty or p.empty:
        return np.nan
    m = pd.merge_asof(c, p, on="t", by="K", direction="nearest", tolerance=pd.Timedelta(seconds=PAIR_SECONDS),
                      suffixes=("_c", "_p")).dropna(subset=["mark_price_p"])
    diff = m.mark_price_c - m.mark_price_p                     # = 1 - K/F
    ok = diff < 1
    if not ok.any():
        return np.nan
    F = m.K[ok] / (1 - diff[ok])
    idx = 0.5 * (m.index_price_c[ok] + m.index_price_p[ok])
    return float(np.median(F / idx))


@dataclass
class Smile:
    expiry: pd.Timestamp
    tau: float           # years from the decision time
    f_ratio: float       # F / index
    coef: np.ndarray     # w(k) = coef[0] + coef[1] k + coef[2] k^2
    k_range: tuple
    n_strikes: int

    def w(self, k):
        return self.coef[0] + self.coef[1] * k + self.coef[2] * k * k


def fit_smile(tr: pd.DataFrame, t: pd.Timestamp):
    expiry = tr.expiry.iloc[0]
    tau = (expiry - t).total_seconds() / YEAR
    if tau <= 0:
        return None
    fr = forward_ratio(tr)
    if not np.isfinite(fr):
        return None
    F = fr * tr.index_price.to_numpy()
    k = np.log(tr.K.to_numpy() / F)
    otm = np.where(tr.cp.to_numpy() == "C", k >= 0, k < 0)
    rows = []
    for cp, kk, v, keep in zip(tr.cp.to_numpy(), k, tr.mark_price.to_numpy(), otm):
        if keep:
            s = implied_total_sd(cp, kk, v)
            if np.isfinite(s):
                rows.append((kk, s * s, s))
    if not rows:
        return None
    a = np.array(rows)
    kk, w, s = a[:, 0], a[:, 1], a[:, 2]
    if len(np.unique(np.round(kk, 6))) < MIN_STRIKES:
        return None
    vega = norm.pdf(-kk / s + 0.5 * s)                         # forward-unit vega shape, as a weight
    X = np.column_stack([np.ones_like(kk), kk, kk * kk])
    coef, *_ = np.linalg.lstsq(X * vega[:, None], w * vega, rcond=None)
    grid = np.linspace(kk.min(), kk.max(), 50)
    if np.any(coef[0] + coef[1] * grid + coef[2] * grid ** 2 <= 0):
        return None
    return Smile(expiry, tau, fr, coef, (float(kk.min()), float(kk.max())), int(len(np.unique(np.round(kk, 6)))))


def smiles_at(trades: pd.DataFrame, t: pd.Timestamp, window=pd.Timedelta(minutes=60)):
    """All surviving smiles from trades in [t - window, t]. trades: columns t, instrument_name,
    mark_price, index_price, plus parsed expiry/K/cp."""
    w = trades[(trades.t > t - window) & (trades.t <= t) & (trades.expiry > t)]
    out = []
    for _, tr in w.groupby("expiry"):
        sm = fit_smile(tr, t)
        if sm is not None:
            out.append(sm)
    return sorted(out, key=lambda s: s.tau)


def prob_above(smiles, t: pd.Timestamp, T: pd.Timestamp, K_index_terms: float, index_now: float,
               bump=0.0025):
    """P_RN(S_T > K) with T bracketed by two smiles; NaN otherwise. Also returns diagnostics."""
    tau = (T - t).total_seconds() / YEAR
    lo = [s for s in smiles if s.tau <= tau]
    hi = [s for s in smiles if s.tau >= tau]
    if not lo or not hi:
        return np.nan, {}
    s1, s2 = lo[-1], hi[0]
    wt = 0.0 if s2.tau == s1.tau else (tau - s1.tau) / (s2.tau - s1.tau)
    lnfr = (1 - wt) * np.log(s1.f_ratio) + wt * np.log(s2.f_ratio)
    F = index_now * np.exp(lnfr)

    def call_usd(K):
        k = np.log(K / F)
        wk = s1.w(k) + (s2.w(k) - s1.w(k)) * wt              # total variance, linear in tau at fixed k
        if wk <= 0:
            return np.nan
        return F * fwd_price("C", k, np.sqrt(wk))

    K = K_index_terms
    up, dn = call_usd(K * (1 + bump)), call_usd(K * (1 - bump))
    p = -(up - dn) / (2 * K * bump)
    k0 = np.log(K / F)
    inside = min(s1.k_range[0], s2.k_range[0]) <= k0 <= max(s1.k_range[1], s2.k_range[1])
    return float(np.clip(p, 0, 1)) if np.isfinite(p) else np.nan, {
        "F": F, "tau1_d": s1.tau * 365, "tau2_d": s2.tau * 365, "k": k0, "k_inside_fit": inside,
        "atm_vol": float(np.sqrt((s1.w(0) + (s2.w(0) - s1.w(0)) * wt) / max(tau, 1e-9)))}
