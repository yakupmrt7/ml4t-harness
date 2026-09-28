"""p15 shared loaders. The holdout guard lives here: once split.json exists (step 0f), load_fills()
and in_scope_markets(dev_only=True) never return a market whose fixing date is in the holdout."""
import json
from pathlib import Path

import pandas as pd

DIR = Path("data/collector/p15")
HERE = Path(__file__).parent
SPLIT = HERE / "split.json"


def split():
    """{'dev_start','dev_end','holdout_start','holdout_end'} as UTC Timestamps, or None before 0f."""
    if not SPLIT.exists():
        return None
    s = json.loads(SPLIT.read_text())
    return {k: pd.Timestamp(v) for k, v in s.items() if k.endswith(("_start", "_end"))}


def in_scope_markets(dev_only=True):
    """In-scope markets (strike + range families, with the step 0b rule table joined if present).
    Fixing time T = end_date. With dev_only and a fixed split, holdout fixing dates are dropped."""
    inv = pd.read_parquet(DIR / "inventory.parquet")
    inv = inv[inv.family.isin(["strike", "range"])].copy()
    inv["id"] = inv.id.astype(str)
    rules = DIR / "rules.parquet"
    if rules.exists():
        inv = inv.merge(pd.read_parquet(rules), on="id", how="left")
    s = split()
    if dev_only and s is not None:
        inv = inv[(inv.end_date >= s["dev_start"]) & (inv.end_date < s["dev_end"])]
    return inv


def load_fills(market_ids=None, dev_only=True, columns=None):
    """On-chain fills (one row per maker fill; see step0 notes on the taker-order rows).
    dev_only with a fixed split: raises if asked for a holdout market."""
    dev = set(in_scope_markets(dev_only=True).id) if (dev_only and split() is not None) else None
    if market_ids is not None:
        market_ids = set(map(str, market_ids))
        if dev is not None and not market_ids <= dev:
            raise ValueError(f"{len(market_ids - dev)} requested markets are not dev markets")
    frames = []
    for f in sorted((DIR / "fills").glob("rg=*.parquet")):
        d = pd.read_parquet(f, columns=columns)
        if len(d) == 0:
            continue
        keep = d.market_id.isin(market_ids) if market_ids is not None else (
            d.market_id.isin(dev) if dev is not None else slice(None))
        frames.append(d[keep])
    fills = pd.concat(frames, ignore_index=True)
    if "timestamp" in fills:
        fills["time"] = pd.to_datetime(fills.timestamp, unit="s", utc=True)
    return fills
