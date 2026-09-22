"""Vectorised bar-level backtester with fees, slippage and perp funding.

Timing convention (the single most common source of fake results):
  * `target[t]` is decided with information available at the CLOSE of bar t.
  * delay=1 -> the position is held over bar t+1, filled at close[t].
    Optimistic: assumes you trade at the exact price you just observed.
    Slippage bps is meant to cover that.
  * delay=2 -> filled at close[t+1], held over bar t+2. Use this as a
    robustness check; if the edge vanishes at delay=2 it was probably
    microstructure noise (bid-ask bounce) rather than prediction.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class CostModel:
    fee_bps: float = 5.0        # Binance USD-M perps VIP0 taker ~5bps; maker ~2bps
    slippage_bps: float = 1.0   # half-spread + impact; BTC perp top-of-book is ~0.1bp, be generous
    include_funding: bool = True

    @property
    def per_unit_turnover(self) -> float:
        return (self.fee_bps + self.slippage_bps) / 1e4


def signal_to_position(
    prob_up: pd.Series,
    threshold: float = 0.0,
    mode: str = "sign",
    smooth: int = 1,
    max_pos: float = 1.0,
) -> pd.Series:
    """Map P(up) to a target position in [-max_pos, max_pos].

    mode='sign'   : +1 / -1 when |p-0.5| > threshold, else 0.
    mode='linear' : 2*(p-0.5) scaled, clipped. Bet size grows with confidence.
    smooth=k      : average the last k targets. With a k-bar label horizon
                    this approximates holding k overlapping sub-bets, and
                    cuts turnover roughly k-fold.
    """
    edge = prob_up - 0.5
    if mode == "sign":
        pos = np.sign(edge).where(edge.abs() > threshold, 0.0)
    elif mode == "linear":
        pos = (2 * edge).where(edge.abs() > threshold, 0.0)
    else:
        raise ValueError(mode)
    if smooth > 1:
        pos = pos.rolling(smooth, min_periods=1).mean()
    return pos.clip(-max_pos, max_pos)


def run_backtest(
    close: pd.Series,
    target: pd.Series,
    costs: CostModel = CostModel(),
    delay: int = 1,
    funding: pd.Series | None = None,
) -> pd.DataFrame:
    """Returns per-bar DataFrame: held, ret, gross, cost, funding, net, equity.

    close   : bar close prices (full series, not just the test period).
    target  : target positions indexed by bar time (NaN / missing = flat).
    funding : perp funding rate per funding timestamp (e.g. 0.0001 = 1bp).
              Longs PAY positive funding.
    """
    if delay < 1:
        raise ValueError("delay must be >= 1; delay=0 is lookahead")
    tgt = target.reindex(close.index).fillna(0.0)
    held = tgt.shift(delay).fillna(0.0)
    ret = close.pct_change().fillna(0.0)
    gross = held * ret
    trade = held.diff().abs().fillna(held.abs())
    cost = trade * costs.per_unit_turnover

    fund = pd.Series(0.0, index=close.index)
    if funding is not None and costs.include_funding and len(funding):
        f = funding.sort_index()
        f = f[(f.index >= close.index[0]) & (f.index <= close.index[-1])]
        pos_idx = close.index.searchsorted(f.index, side="left")
        pos_idx = np.minimum(pos_idx, len(close) - 1)
        charge = np.zeros(len(close))
        np.add.at(charge, pos_idx, f.to_numpy())
        # position held going INTO the funding timestamp pays/receives
        fund = pd.Series(held.to_numpy() * charge, index=close.index)

    net = gross - cost - fund
    return pd.DataFrame(
        {
            "held": held,
            "ret": ret,
            "gross": gross,
            "cost": cost,
            "funding": fund,
            "net": net,
            "equity": (1 + net).cumprod(),
        }
    )
