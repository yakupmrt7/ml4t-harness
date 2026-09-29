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


def cvar(r, alpha: float = 0.05) -> float:
    """Expected shortfall: mean of the worst ceil(alpha * n) observations (a loss is negative).
    Uses the empirical tail, no distribution assumption."""
    x = np.sort(np.asarray(pd.Series(r).dropna(), float))
    if len(x) == 0:
        return float("nan")
    k = max(1, int(np.ceil(alpha * len(x))))
    return float(x[:k].mean())


def tail_report(pnl: pd.Series, stress_windows: dict | None = None, alpha: float = 0.05) -> dict:
    """Skew-aware summary of a per-period P&L series (e.g. weekly P&L of a short-vol book).
    pnl is additive (P&L per period, not compounded). stress_windows: {name: (start, end)} inclusive,
    reported as the summed P&L of periods inside each window and its size in mean periods.
    'worst_over_mean' = worst period loss / mean P&L (how many mean periods one bad period erases);
    NaN if the mean is <= 0."""
    x = pd.Series(pnl).dropna()
    eq = x.cumsum()
    dd = eq - np.maximum.accumulate(np.r_[0.0, eq.to_numpy()])[1:]
    mean = float(x.mean())
    worst = float(x.min())
    out = {
        "n": int(len(x)),
        "mean": mean,
        "std": float(x.std(ddof=1)),
        "t": float(mean / (x.std(ddof=1) / np.sqrt(len(x)))) if len(x) > 1 and x.std(ddof=1) > 0 else float("nan"),
        "hit_rate": float((x > 0).mean()),
        "skew": float(stats.skew(x)),
        "kurtosis": float(stats.kurtosis(x, fisher=False)),
        f"cvar_{int(alpha * 100)}": cvar(x, alpha),
        "worst": worst,
        "worst_when": str(x.idxmin()),
        "worst_over_mean": float(-worst / mean) if mean > 0 else float("nan"),
        "max_drawdown": float(dd.min()),
        "max_drawdown_end": str(dd.idxmin()),
    }
    for name, (a, b) in (stress_windows or {}).items():
        if isinstance(x.index, pd.DatetimeIndex):
            lo, hi = pd.Timestamp(a), pd.Timestamp(b)
            lo = lo.tz_localize(x.index.tz) if lo.tzinfo is None and x.index.tz is not None else lo
            hi = hi.tz_localize(x.index.tz) if hi.tzinfo is None and x.index.tz is not None else hi
            if isinstance(b, str) and len(b) == 10:            # date-only end: inclusive of the whole day
                hi = hi + pd.Timedelta(days=1) - pd.Timedelta(1, "ns")
            w = x[(x.index >= lo) & (x.index <= hi)]
        else:
            w = x[(x.index >= a) & (x.index <= b)]
        out[f"stress_{name}"] = {"periods": int(len(w)), "pnl": float(w.sum()),
                                 "in_mean_periods": float(w.sum() / mean) if mean > 0 else float("nan")}
    return out


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
