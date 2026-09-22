"""Sample weights for overlapping labels (AFML ch.4).

With a 60-bar horizon on 1-bar steps, each label shares ~59/60 of its future
with its neighbour. Treating them as independent overstates your sample size
~60x and lets trees memorise. Average uniqueness fixes the weighting.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _positions(index: pd.DatetimeIndex, t0: pd.Index, t1: pd.Series):
    """Bar positions of the returns a label depends on: (t0, t1] -> i0+1..i1.
    The bar ending AT t0 is already known when the label starts."""
    i0 = index.get_indexer(t0)
    i1 = index.searchsorted(t1.to_numpy(), side="left")
    i1 = np.minimum(i1, len(index) - 1)
    if (i0 < 0).any():
        raise ValueError("event t0 not found in bar index")
    return i0 + 1, i1


def concurrency(index: pd.DatetimeIndex, labels: pd.DataFrame) -> pd.Series:
    """Number of labels whose return window (t0, t1] covers each bar."""
    i0, i1 = _positions(index, labels.index, labels["t1"])
    d = np.zeros(len(index) + 1)
    np.add.at(d, i0, 1)
    np.add.at(d, i1 + 1, -1)
    return pd.Series(np.cumsum(d[:-1]), index=index)


def average_uniqueness(index: pd.DatetimeIndex, labels: pd.DataFrame) -> pd.Series:
    """Mean over the label's life of 1/concurrency. 1.0 = no overlap."""
    c = concurrency(index, labels).to_numpy()
    inv = np.where(c > 0, 1.0 / np.maximum(c, 1), 0.0)
    cs = np.concatenate([[0.0], np.cumsum(inv)])
    i0, i1 = _positions(index, labels.index, labels["t1"])
    u = (cs[i1 + 1] - cs[i0]) / (i1 - i0 + 1)
    return pd.Series(u, index=labels.index, name="uniqueness")


def effective_n(uniqueness: pd.Series) -> float:
    """Rough count of independent labels. Report this, not len(y)."""
    return float(uniqueness.sum())


def return_attribution_weights(
    close: pd.Series, labels: pd.DataFrame, uniqueness: pd.Series
) -> pd.Series:
    """Uniqueness * |label return|, normalised to mean 1. Big, unique moves
    matter more than tiny overlapping ones."""
    w = uniqueness * labels["ret"].abs()
    return w / w.mean()
