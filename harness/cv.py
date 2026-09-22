"""Cross-validation that respects label intervals.

All splitters take `t1`: a Series indexed by event start time t0 whose values
are the label end times. They yield integer positions into that Series.

PurgedKFold  -> model selection / hyperparameters (uses past AND future data
                for training, purged + embargoed around each test block).
WalkForward  -> the backtest. Training data always strictly precedes the
                test block, labels included. This is what you report.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import numpy as np
import pandas as pd


def _check(t1: pd.Series):
    if not t1.index.is_monotonic_increasing:
        raise ValueError("t1 index (t0) must be sorted")
    if (t1.to_numpy() < t1.index.to_numpy()).any():
        raise ValueError("found t1 < t0")


def purge_train(t1: pd.Series, train_pos: np.ndarray, test_start, test_end) -> np.ndarray:
    """Drop training events whose label interval overlaps [test_start, test_end]."""
    t0v = t1.index.to_numpy()[train_pos]
    t1v = t1.to_numpy()[train_pos]
    overlap = (t0v <= test_end) & (t1v >= test_start)
    return train_pos[~overlap]


@dataclass
class PurgedKFold:
    n_splits: int = 5
    embargo_frac: float = 0.01  # fraction of events dropped after each test block

    def split(self, t1: pd.Series) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        _check(t1)
        n = len(t1)
        emb = int(np.ceil(n * self.embargo_frac))
        pos = np.arange(n)
        t0v = t1.index.to_numpy()
        for test_pos in np.array_split(pos, self.n_splits):
            a, b = test_pos[0], test_pos[-1]
            test_start = t0v[a]
            test_end = t1.iloc[a : b + 1].max()
            train = np.concatenate([pos[:a], pos[b + 1 :]])
            train = purge_train(t1, train, test_start, test_end)
            # embargo: events starting right after the test block leak through
            # serial correlation of features, so skip `emb` of them.
            after = pos[(t0v > test_end)]
            if emb and len(after):
                blocked = after[:emb]
                train = np.setdiff1d(train, blocked, assume_unique=True)
            yield train, test_pos


@dataclass
class WalkForward:
    """Anchored (expanding) or rolling walk-forward.

    n_splits test blocks cover the final (1 - min_train_frac) of the data.
    Training for each block = everything whose LABEL ENDS before the block
    starts (i.e. t1 < test_start), optionally limited to the last `max_train`
    events (rolling window).
    """
    n_splits: int = 6
    min_train_frac: float = 0.4
    max_train: int | None = None

    def split(self, t1: pd.Series) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        _check(t1)
        n = len(t1)
        pos = np.arange(n)
        start = int(n * self.min_train_frac)
        t0v = t1.index.to_numpy()
        t1v = t1.to_numpy()
        for test_pos in np.array_split(pos[start:], self.n_splits):
            test_start = t0v[test_pos[0]]
            train = pos[t1v < test_start]
            if self.max_train is not None:
                train = train[-self.max_train :]
            yield train, test_pos
