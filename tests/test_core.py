"""Unit tests for the parts where an off-by-one silently creates fake alpha.
Run: python -m pytest tests -q   (or python tests/test_core.py)"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd

from harness.labeling import triple_barrier, fixed_horizon_labels, ewm_vol
from harness.weights import average_uniqueness, concurrency
from harness.cv import PurgedKFold, WalkForward
from harness.backtest import run_backtest, CostModel, hysteresis_position


def _bars(n=2000, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC")
    return pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 1e-3, n))), idx)


def test_triple_barrier_hand_path():
    idx = pd.date_range("2026-01-01", periods=10, freq="1h")
    close = pd.Series(np.exp([0, .01, .03, -.05, -.05, -.05, -.04, -.05, -.05, -.05]), idx)
    lab = triple_barrier(close, horizon=4, width=pd.Series(0.02, idx))
    # from t0=0: path .01, .03 -> upper (0.02) touched at bar 2
    assert lab.iloc[0]["barrier"] == "pt" and lab.iloc[0]["label"] == 1
    assert lab.iloc[0]["t1"] == idx[2]
    # from t0=2 (log .03): path -.08 at bar 3 -> lower
    assert lab.loc[idx[2], "barrier"] == "sl" and lab.loc[idx[2], "label"] == -1
    # from t0=4: small wiggles -> vertical at t0+4, label = sign of final ret (0)
    assert lab.loc[idx[4], "barrier"] == "vert" and lab.loc[idx[4], "t1"] == idx[8]


def test_labels_never_end_before_start_and_within_horizon():
    c = _bars()
    h = 12
    lab = triple_barrier(c, h, ewm_vol(c) * np.sqrt(h))
    pos0 = c.index.get_indexer(lab.index)
    pos1 = c.index.get_indexer(lab["t1"])
    assert (pos1 > pos0).all() and (pos1 - pos0 <= h).all()


def test_uniqueness():
    c = _bars(500)
    lab1 = fixed_horizon_labels(c, 1)
    assert np.allclose(average_uniqueness(c.index, lab1), 1.0)  # 1-bar labels never overlap
    lab = fixed_horizon_labels(c, 10)
    u = average_uniqueness(c.index, lab)
    assert np.isclose(u.iloc[100], 0.1)  # 10 overlapping labels per bar in steady state
    assert concurrency(c.index, lab).max() == 10


def test_purged_kfold_no_overlap():
    c = _bars()
    lab = fixed_horizon_labels(c, 24)
    t1 = lab["t1"]
    for train, test in PurgedKFold(5, 0.02).split(t1):
        a, b = t1.index[test[0]], t1.iloc[test].max()
        tr0, tr1 = t1.index[train], t1.iloc[train].to_numpy()
        assert not ((tr0 <= b) & (tr1 >= a)).any()
        assert len(np.intersect1d(train, test)) == 0


def test_walk_forward_strictly_past():
    c = _bars()
    lab = fixed_horizon_labels(c, 24)
    t1 = lab["t1"]
    n = 0
    for train, test in WalkForward(5, 0.4).split(t1):
        assert t1.iloc[train].max() < t1.index[test[0]]
        n += 1
    assert n == 5


def test_backtest_timing():
    c = _bars(5000)
    r = c.pct_change()
    # signal known at t (sign of the bar that just closed) on iid returns -> no edge
    bt = run_backtest(c, np.sign(r).fillna(0), CostModel(0, 0))
    assert abs(bt["gross"].mean()) < 3 * bt["gross"].std() / np.sqrt(len(bt))
    # a signal that peeks one bar ahead must look (too) good -> harness does not hide it
    bt2 = run_backtest(c, np.sign(r.shift(-1)).fillna(0), CostModel(0, 0))
    assert bt2["gross"].mean() > 0 and (bt2["gross"] >= 0).all()
    # costs: flipping every bar costs ~2 units of turnover per bar
    bt3 = run_backtest(c, pd.Series(np.where(np.arange(len(c)) % 2, 1.0, -1.0), c.index), CostModel(5, 0))
    assert np.isclose(bt3["cost"].iloc[10], 2 * 5e-4)


def test_delay_zero_rejected():
    c = _bars(100)
    try:
        run_backtest(c, pd.Series(0.0, c.index), delay=0)
    except ValueError:
        return
    raise AssertionError


def _hyst(ps, **kw):
    idx = pd.date_range("2026-01-01", periods=len(ps), freq="5min", tz="UTC")
    return hysteresis_position(pd.Series(ps, idx), **kw).tolist()


def test_hysteresis_entry():
    # strictly beyond 0.5 +- theta_in to enter; the band edge itself does not
    assert _hyst([.5, .52, .531, .52], theta_in=.03, theta_out=.01) == [0, 0, 1, 1]
    assert _hyst([.5, .48, .469, .48], theta_in=.03, theta_out=.01) == [0, 0, -1, -1]


def test_hysteresis_exit():
    # long survives inside (0.5+theta_out, 0.5+theta_in], exits at <= 0.5+theta_out
    assert _hyst([.54, .52, .511, .51, .52], theta_in=.03, theta_out=.01) == [1, 1, 1, 0, 0]
    assert _hyst([.46, .48, .489, .49, .48], theta_in=.03, theta_out=.01) == [-1, -1, -1, 0, 0]
    # theta_out=0: hold until the signal crosses 0.5
    assert _hyst([.54, .501, .5], theta_in=.03) == [1, 1, 0]
    # NaN holds the current position
    assert _hyst([.54, np.nan, np.nan, .5], theta_in=.03) == [1, 1, 1, 0]


def test_hysteresis_min_hold():
    # entry at bar 0 is frozen for 3 bars even though p says exit
    assert _hyst([.54, .5, .5, .5, .5], theta_in=.03, min_hold=3) == [1, 1, 1, 0, 0]
    # the exit to flat (bar 3) is a change too: no re-entry before bar 6
    assert _hyst([.54, .5, .5, .5, .54, .54, .54, .54], theta_in=.03, min_hold=3) == [1, 1, 1, 0, 0, 0, 1, 1]
    # min_hold=1 imposes nothing
    assert _hyst([.54, .5, .54], theta_in=.03, min_hold=1) == [1, 0, 1]


def test_hysteresis_no_direct_flip():
    # a strong reversal inside min_hold does not flip, and it goes straight to
    # short once min_hold is up (the long exit condition is met on that bar)
    assert _hyst([.54, .40, .40, .40], theta_in=.03, min_hold=3) == [1, 1, 1, -1]
    # on random p: every long<->short flip happens on a bar that meets the exit
    # AND entry conditions, and never inside min_hold
    rng = np.random.default_rng(0)
    p = np.clip(0.5 + np.cumsum(rng.normal(0, 0.01, 5000)) * 0.1 + rng.normal(0, .03, 5000), 0, 1)
    ti, to, mh = .03, .01, 6
    pos = np.array(_hyst(p, theta_in=ti, theta_out=to, min_hold=mh))
    chg = np.flatnonzero(np.diff(pos) != 0) + 1
    assert len(chg) > 20 and np.diff(chg).min() >= mh
    for i in chg:
        if pos[i - 1] == 1 and pos[i] == -1:
            assert p[i] <= .5 + to and p[i] < .5 - ti
        if pos[i - 1] == -1 and pos[i] == 1:
            assert p[i] >= .5 - to and p[i] > .5 + ti
        if pos[i - 1] == 1 and pos[i] == 0:
            assert p[i] <= .5 + to
        if pos[i - 1] == -1 and pos[i] == 0:
            assert p[i] >= .5 - to


if __name__ == "__main__":
    for k, fn in list(globals().items()):
        if k.startswith("test_"):
            fn(); print("ok", k)
