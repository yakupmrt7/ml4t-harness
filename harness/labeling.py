"""Labels for financial ML.

Everything here works on a bar series (time, dollar or volume bars) indexed by
a monotonically increasing DatetimeIndex. Horizons are expressed in bars.

Key idea: a label is not a point in time, it is an *interval* [t0, t1]. The
t1 column produced here is what purged CV and uniqueness weights consume.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view


def ewm_vol(close: pd.Series, span: int = 100) -> pd.Series:
    """EWM std of log returns per bar. Uses only past data (no lookahead)."""
    r = np.log(close).diff()
    return r.ewm(span=span, min_periods=span // 2).std()


def fixed_horizon_labels(close: pd.Series, horizon: int) -> pd.DataFrame:
    """Plain forward return over `horizon` bars. Baseline labelling."""
    c = close.to_numpy(dtype=float)
    n = len(c)
    fwd = np.full(n, np.nan)
    fwd[: n - horizon] = np.log(c[horizon:] / c[: n - horizon])
    t1 = pd.Series(pd.NaT, index=close.index, dtype=close.index.dtype)
    t1.iloc[: n - horizon] = close.index[horizon:]
    out = pd.DataFrame({"t1": t1, "ret": fwd}, index=close.index)
    out["label"] = np.sign(out["ret"])
    return out.dropna()


def triple_barrier(
    close: pd.Series,
    horizon: int,
    width: pd.Series,
    pt_mult: float = 1.0,
    sl_mult: float = 1.0,
    events: pd.Index | None = None,
    zero_on_vertical: bool = False,
) -> pd.DataFrame:
    """Triple-barrier labels (Lopez de Prado, AFML ch.3), fully vectorised.

    For each event time t0:
      upper barrier  = +pt_mult * width[t0]   (log-return space)
      lower barrier  = -sl_mult * width[t0]
      vertical       = t0 + horizon bars
    The label is the sign of whichever is touched first. If the vertical one
    is hit, label = sign(return) unless zero_on_vertical=True.

    `width` must be known at t0 (e.g. ewm_vol(close) * sqrt(horizon)).

    Returns DataFrame indexed by t0 with: t1, ret, label, barrier.
    """
    c = np.log(close.to_numpy(dtype=float))
    w = width.reindex(close.index).to_numpy(dtype=float)
    n = len(c)
    if n <= horizon:
        raise ValueError("series shorter than horizon")

    win = sliding_window_view(c, horizon + 1)          # (n-h, h+1)
    path = win[:, 1:] - win[:, [0]]                    # log ret from t0, bars 1..h
    m = path.shape[0]
    up = pt_mult * w[:m, None]
    dn = -sl_mult * w[:m, None]

    hit_up = path >= up
    hit_dn = path <= dn
    big = horizon + 10
    first_up = np.where(hit_up.any(1), hit_up.argmax(1), big)
    first_dn = np.where(hit_dn.any(1), hit_dn.argmax(1), big)
    first = np.minimum(np.minimum(first_up, first_dn), horizon - 1)

    rows = np.arange(m)
    ret = path[rows, first]
    barrier = np.where(first_up <= first, "pt", np.where(first_dn <= first, "sl", "vert"))
    label = np.sign(ret)
    if zero_on_vertical:
        label = np.where(barrier == "vert", 0.0, label)

    out = pd.DataFrame(
        {
            "t1": close.index[rows + first + 1],
            "ret": ret,
            "label": label,
            "barrier": barrier,
        },
        index=close.index[:m],
    )
    out = out[np.isfinite(w[:m])]
    if events is not None:
        out = out.loc[out.index.intersection(events)]
    return out


def cusum_events(close: pd.Series, threshold: pd.Series | float) -> pd.DatetimeIndex:
    """Symmetric CUSUM filter: sample an event only after a cumulative move
    of `threshold` (log-return units). Cuts label overlap and focuses on
    moments where something happened. threshold can be a series (e.g. vol)."""
    r = np.log(close).diff().fillna(0.0).to_numpy()
    thr = (
        threshold.reindex(close.index).to_numpy(dtype=float)
        if isinstance(threshold, pd.Series)
        else np.full(len(r), float(threshold))
    )
    s_pos = s_neg = 0.0
    idx = []
    for i in range(1, len(r)):
        h = thr[i]
        if not np.isfinite(h):
            continue
        s_pos = max(0.0, s_pos + r[i])
        s_neg = min(0.0, s_neg + r[i])
        if s_pos > h:
            s_pos = 0.0
            idx.append(i)
        elif s_neg < -h:
            s_neg = 0.0
            idx.append(i)
    return close.index[idx]
