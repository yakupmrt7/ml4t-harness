"""Performance statistics, including the ones that correct for luck.

Sharpe ratios in PSR/DSR are PER-PERIOD (not annualised); the helpers take
care of that. Reference: Bailey & Lopez de Prado (2012, 2014).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

EULER_GAMMA = 0.5772156649015329


def periods_per_year(index: pd.DatetimeIndex) -> float:
    """Crypto trades 24/7, so use calendar time."""
    # NB: don't use index.asi8 -- its unit (ns/us) depends on the index dtype
    dt = pd.Series(index).diff().dt.total_seconds().median()
    return 365.25 * 86400 / dt


def sharpe(r: pd.Series, ppy: float | None = None) -> float:
    r = r.dropna()
    sd = r.std(ddof=1)
    if sd == 0 or len(r) < 2:
        return 0.0
    s = r.mean() / sd
    return s * np.sqrt(ppy) if ppy else s


def max_drawdown(equity: pd.Series) -> float:
    return float((equity / equity.cummax() - 1).min())


def psr(sr: float, n: int, skew: float, kurt: float, sr_star: float = 0.0) -> float:
    """Probabilistic Sharpe Ratio: P(true SR > sr_star). Per-period SRs.
    kurt is NON-excess kurtosis (normal = 3)."""
    denom = np.sqrt(max(1e-12, 1 - skew * sr + (kurt - 1) / 4 * sr**2))
    return float(stats.norm.cdf((sr - sr_star) * np.sqrt(n - 1) / denom))


def expected_max_sr(n_trials: int, var_sr: float) -> float:
    """E[max SR] among n_trials skill-less strategies (per-period)."""
    if n_trials < 2:
        return 0.0
    z1 = stats.norm.ppf(1 - 1 / n_trials)
    z2 = stats.norm.ppf(1 - 1 / (n_trials * np.e))
    return float(np.sqrt(var_sr) * ((1 - EULER_GAMMA) * z1 + EULER_GAMMA * z2))


def dsr(sr: float, n: int, skew: float, kurt: float, n_trials: int, var_sr: float) -> float:
    """Deflated Sharpe Ratio: PSR against the best SR you'd expect from luck
    after n_trials attempts. > 0.95 is the usual bar."""
    return psr(sr, n, skew, kurt, sr_star=expected_max_sr(n_trials, var_sr))


def summarize(bt: pd.DataFrame, trials: "TrialLog | None" = None) -> dict:
    ppy = periods_per_year(bt.index)
    net, gross = bt["net"], bt["gross"]
    active = bt["held"] != 0
    years = len(bt) / ppy
    turnover = bt["held"].diff().abs().sum()
    sr_pp = sharpe(net)
    sk = float(stats.skew(net))
    ku = float(stats.kurtosis(net, fisher=False))
    out = {
        "bars": len(bt),
        "years": round(years, 3),
        "ann_return_net": float(net.mean() * ppy),
        "ann_vol": float(net.std() * np.sqrt(ppy)),
        "sharpe_gross": sharpe(gross, ppy),
        "sharpe_net": sharpe(net, ppy),
        "max_drawdown": max_drawdown(bt["equity"]),
        "exposure": float(active.mean()),
        "hit_rate": float((bt.loc[active, "gross"] > 0).mean()) if active.any() else np.nan,
        "turnover_per_year": float(turnover / years) if years else np.nan,
        "cost_drag_ann": float(bt["cost"].mean() * ppy),
        "funding_drag_ann": float(bt["funding"].mean() * ppy),
        "breakeven_cost_bps": float(gross.sum() / turnover * 1e4) if turnover else np.nan,
        "psr_vs_0": psr(sr_pp, len(net), sk, ku),
        "skew": sk,
        "kurtosis": ku,
    }
    if trials is not None and len(trials) >= 2:
        out["n_trials"] = len(trials)
        out["dsr"] = dsr(sr_pp, len(net), sk, ku, len(trials), trials.var_sr())
    return out


@dataclass
class TrialLog:
    """Append-only record of EVERY configuration you evaluated on the
    backtest period. The DSR is only honest if this includes the failures.
    Persisted to JSON so the count survives notebook restarts."""
    path: str = "trials.json"
    rows: list = field(default_factory=list)

    def __post_init__(self):
        p = Path(self.path)
        if p.exists():
            self.rows = json.loads(p.read_text())

    def __len__(self):
        return len(self.rows)

    def log(self, name: str, bt: pd.DataFrame, params: dict | None = None) -> None:
        self.rows.append(
            {
                "name": name,
                "params": params or {},
                "sr_per_period": sharpe(bt["net"]),
                "n": int(len(bt)),
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        )
        Path(self.path).write_text(json.dumps(self.rows, indent=1, default=str))

    def var_sr(self) -> float:
        return float(np.var([r["sr_per_period"] for r in self.rows], ddof=1))
