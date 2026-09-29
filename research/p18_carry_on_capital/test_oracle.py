"""Hand-checked tests of run.oracle (DP with switching costs, flat at start and end).
  python research/p18_carry_on_capital/test_oracle.py"""
import sys, pathlib
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from run import oracle

def cost(a, b):
    return abs(b - a) * 0.5

# carry +1.0 on days 1-2 only: enter day 1, exit after day 2 -> total 2.0 - 0.5 - 0.5 = 1.0
d, p = oracle({0: np.zeros(4), 1: np.array([-0.1, 1.0, 1.0, -0.1])}, cost)
assert list(p) == [0, 1, 1, 0], p
assert np.isclose(d.sum(), 1.0), d.sum()
# a single +0.8 day does not pay two switches of 0.5 -> stay flat
d, p = oracle({0: np.zeros(3), 1: np.array([0.0, 0.8, 0.0])}, cost)
assert list(p) == [0, 0, 0] and np.isclose(d.sum(), 0.0)
# three states: short pays on day 0-1, long on day 2-3; flip costs 2 * 0.5
d, p = oracle({0: np.zeros(4), 1: np.array([-2, -2, 2, 2.0]), -1: np.array([2, 2, -2, -2.0])}, cost)
assert list(p) == [-1, -1, 1, 1], p
assert np.isclose(d.sum(), 8 - 0.5 - 1.0 - 0.5), d.sum()
print("ok oracle tests")
