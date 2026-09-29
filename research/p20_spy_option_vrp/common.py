"""p20 shared loader. The holdout guard lives here: load_chain_dev() reads only dudesurfin files for 2010-2021 and
asserts every row is inside the dev span; holdout files (2022+) are never opened by it."""
from pathlib import Path

import pandas as pd

DIR = Path("data/collector/p20")
SRC = DIR / "dudesurfin"
DEV_START, DEV_END = pd.Timestamp("2010-01-01"), pd.Timestamp("2021-12-31")
HOLD_START, HOLD_END = pd.Timestamp("2022-01-01"), pd.Timestamp("2025-12-31")
COLS = {"[QUOTE_DATE]": "date", "[UNDERLYING_LAST]": "underlying", "[EXPIRE_DATE]": "expiry", "[DTE]": "dte",
        "[STRIKE]": "strike", "[C_BID]": "c_bid", "[C_ASK]": "c_ask", "[C_IV]": "c_iv", "[C_DELTA]": "c_delta",
        "[P_BID]": "p_bid", "[P_ASK]": "p_ask", "[P_IV]": "p_iv", "[P_DELTA]": "p_delta"}


def _load(years):
    frames = []
    for y in years:
        d = pd.read_parquet(SRC / f"spy_eod_{y}.parquet", columns=list(COLS))
        d = d.rename(columns=COLS)
        for c in ("date", "expiry"):
            d[c] = pd.to_datetime(d[c].astype(str).str.strip())
        for c in d.columns:
            if c not in ("date", "expiry"):
                d[c] = pd.to_numeric(d[c], errors="coerce")
        frames.append(d)
    return pd.concat(frames, ignore_index=True)


def load_chain_dev():
    ch = _load(range(DEV_START.year, DEV_END.year + 1))
    assert ch.date.between(DEV_START, DEV_END).all(), "non-dev rows in a dev load"
    return ch
