"""p16 shared loaders: Friday calendar, Deribit delivery prices, Deribit trade days, the entry smile.
Reuses research/p15_pm_deribit_threshold/surface.py (tested there)."""
import json
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "p15_pm_deribit_threshold"))
import surface as S  # noqa: E402

DERIBIT = Path("data/collector/p11/deribit_opt")
DIR = Path("data/collector/p16")
FIRST_FRIDAY = pd.Timestamp("2022-08-05 08:00", tz="UTC")
LAST_EXPIRY = pd.Timestamp("2026-08-28 08:00", tz="UTC")       # last Friday expiry inside the data (to 2026-08-31)
ENTRY_LAG = pd.Timedelta(minutes=5)                            # entry at 08:05, after the 08:00 expiry
SMILE_WINDOW = pd.Timedelta(minutes=60)


def fridays():
    """Entry Fridays (08:00 UTC stamps) whose 7-day expiry is inside the data."""
    out = pd.date_range(FIRST_FRIDAY, LAST_EXPIRY - pd.Timedelta(days=7), freq="7D")
    assert all(d.dayofweek == 4 for d in out)
    return list(out)


def delivery_prices():
    """Official Deribit BTC delivery prices (30-min index TWAP before 08:00 UTC), by date."""
    rows = json.loads((DIR / "delivery_btc_usd.json").read_text())
    return pd.Series({pd.Timestamp(r["date"]).date(): float(r["delivery_price"]) for r in rows}).sort_index()


@lru_cache(maxsize=4)
def deribit_day(d: str):
    f = DERIBIT / f"opt_{d}.parquet"
    if not f.exists():
        return None
    x = pd.read_parquet(f, columns=["timestamp", "instrument_name", "price", "mark_price", "index_price", "amount",
                                    "direction", "iv"])
    x = x[x.instrument_name.str.match(r"^BTC-\d{1,2}[A-Z]{3}\d{2}-\d+-[CP]$")]
    x = x.join(S.parse_instruments(x.instrument_name))
    x["t"] = pd.to_datetime(x.timestamp, unit="ms", utc=True)
    return x.sort_values("t").reset_index(drop=True)


def entry_smile(friday: pd.Timestamp):
    """Smile of the expiry friday + 7 d from mark prices of that expiry's trades in (t - 60 min, t], t = 08:05.
    Returns (Smile or None, info) with the forward, index at t, and strikes that traded that day before t."""
    t = friday + ENTRY_LAG
    expiry = friday + pd.Timedelta(days=7)
    x = deribit_day(str(friday.date()))
    if x is None:
        return None, {}
    ex = x[(x.expiry == expiry) & (x.t <= t)]
    w = ex[ex.t > t - SMILE_WINDOW]
    info = {"t": t, "expiry": expiry, "n_trades_window": int(len(w)),
            "strikes_traded_today": sorted(ex.K.unique().tolist())}
    if w.empty:
        return None, info
    sm = S.fit_smile(w, t)
    if sm is None:
        return None, info
    idx = float(x[x.t <= t].index_price.iloc[-1])
    info.update({"index": idx, "F": idx * sm.f_ratio, "n_strikes": sm.n_strikes})
    return sm, info
