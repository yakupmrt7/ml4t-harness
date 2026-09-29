"""p20 step 0 (PLAN.md): data validation on DEV dates only (2010-01-01 .. 2021-12-31). No P&L.

  python research/p20_spy_option_vrp/step0.py

1. dudesurfin chains: trading days vs an independent SPY calendar (Yahoo), duplicate keys, bid > ask, zero bids.
2. UNDERLYING_LAST vs Yahoo's unadjusted SPY close.
3. Cross-source mids on identical (date, expiry, strike, type) for 60 random dev dates:
   dudesurfin vs shankerabhigyan (2014-2021; independent vendor) and dudesurfin vs kylegraupe (2020-2021; same
   optionsDX schema, so a conversion-integrity check). Streaming parsers keep memory bounded; holdout years
   (2022+) are never opened.
"""
import io
import json
import sys
import zipfile
from pathlib import Path

import ijson
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from common import DEV_END, DEV_START, DIR, load_chain_dev  # noqa: E402

RNG = np.random.default_rng(0)


def yahoo_closes():
    d = json.load(open(DIR / "spy_yahoo.json"))["chart"]["result"][0]
    idx = pd.to_datetime(d["timestamp"], unit="s").normalize()
    return pd.Series(d["indicators"]["quote"][0]["close"], index=idx).dropna()


def mids_dudesurfin(ch):
    c = ch[["date", "expiry", "strike"]].copy()
    out = []
    for typ, b, a in (("call", "c_bid", "c_ask"), ("put", "p_bid", "p_ask")):
        x = c.assign(type=typ, mid=(ch[b] + ch[a]) / 2, spread=ch[a] - ch[b])
        out.append(x)
    return pd.concat(out)


def shanker_dates(years, dates):
    """Stream the per-year JSON files (dev years only) and keep rows of the sampled dates."""
    rows = []
    z = zipfile.ZipFile(DIR / "spy_2014_2025_shanker.zip")
    for y in years:
        assert y <= 2021, "holdout year"
        want = {d for d in dates if d.year == y}
        if not want:
            continue
        with z.open(f"spy_options_data_{y % 100:02d}.json") as f:
            for day, recs in ijson.kvitems(f, ""):
                d = pd.Timestamp(day)
                if d in want:
                    for r in recs:
                        bid, ask = float(r["bid"]), float(r["ask"])
                        rows.append((d, pd.Timestamp(r["expiration"]), float(r["strike"]), r["type"], (bid + ask) / 2))
    return pd.DataFrame(rows, columns=["date", "expiry", "strike", "type", "mid_other"])


def graupe_dates(dates):
    z = zipfile.ZipFile(DIR / "spy_eod_2020_2022_graupe.zip")
    want = {d for d in dates if d.year in (2020, 2021)}
    keep = []
    with z.open("spy_2020_2022.csv") as f:
        for chunk in pd.read_csv(io.TextIOWrapper(f, encoding="utf-8-sig"), chunksize=500_000, skipinitialspace=True):
            chunk.columns = [c.strip().strip("[]") for c in chunk.columns]
            chunk["date"] = pd.to_datetime(chunk["QUOTE_DATE"].astype(str).str.strip())
            chunk = chunk[chunk.date.isin(want)]
            if len(chunk):
                for typ, b, a in (("call", "C_BID", "C_ASK"), ("put", "P_BID", "P_ASK")):
                    keep.append(pd.DataFrame({"date": chunk.date, "expiry": pd.to_datetime(chunk.EXPIRE_DATE.astype(str).str.strip()),
                                              "strike": pd.to_numeric(chunk.STRIKE, errors="coerce"), "type": typ,
                                              "mid_other": (pd.to_numeric(chunk[b], errors="coerce") + pd.to_numeric(chunk[a], errors="coerce")) / 2}))
    return pd.concat(keep) if keep else pd.DataFrame()


def compare(mine, other, label):
    j = mine.merge(other, on=["date", "expiry", "strike", "type"], how="inner").dropna(subset=["mid", "mid_other"])
    j = j[(j.mid > 0) & (j.mid_other > 0)]
    d = (j.mid - j.mid_other).abs()
    res = {"pair": label, "matched_quotes": int(len(j)), "dates": int(j.date.nunique()),
           "median_abs_mid_diff_$": float(d.median()), "share_within_5c": float((d <= 0.05).mean()),
           "p99_abs_mid_diff_$": float(d.quantile(0.99)),
           "gate_pass": bool(d.median() <= 0.01 and (d <= 0.05).mean() >= 0.95)}
    # the ATM, 25-35 DTE puts the book actually trades, separately
    dte = (j.expiry - j.date).dt.days
    atm = j[(j.type == "put") & dte.between(20, 40)]
    if len(atm):
        da = (atm.mid - atm.mid_other).abs()
        res["book_region_median_abs_mid_diff_$"] = float(da.median())
        res["book_region_share_within_5c"] = float((da <= 0.05).mean())
    return res


def main():
    ch = load_chain_dev()
    y = yahoo_closes()
    y = y[(y.index >= DEV_START) & (y.index <= DEV_END)]
    days = pd.DatetimeIndex(sorted(ch.date.unique()))
    missing = y.index.difference(days)
    extra = days.difference(y.index)
    res = {"chain_rows": int(len(ch)), "chain_days": int(len(days)), "yahoo_days": int(len(y)),
           "share_of_trading_days_present": float(1 - len(missing) / len(y)),
           "missing_days": [str(d.date()) for d in missing], "extra_days_not_trading": [str(d.date()) for d in extra],
           "duplicate_keys": int(ch.duplicated(["date", "expiry", "strike"]).sum()),
           "put_bid_gt_ask": int((ch.p_bid > ch.p_ask).sum()), "call_bid_gt_ask": int((ch.c_bid > ch.c_ask).sum()),
           "share_put_zero_bid": float((ch.p_bid == 0).mean())}
    res["gate_days"] = res["share_of_trading_days_present"] >= 0.98
    u = ch.groupby("date").underlying.median()
    j = pd.concat([u, y.rename("yahoo")], axis=1, join="inner")
    rel = (j.underlying / j.yahoo - 1).abs()
    res.update({"underlying_days_compared": int(len(j)), "underlying_median_abs_rel_diff": float(rel.median()),
                "underlying_share_within_0.5pct": float((rel <= 0.005).mean()),
                "underlying_worst_days": {str(k.date()): round(float(v), 5) for k, v in rel.nlargest(5).items()}})
    res["gate_underlying"] = bool(rel.median() < 0.0005 and (rel <= 0.005).mean() >= 0.99)
    mine = mids_dudesurfin(ch)
    dates_14_21 = sorted(RNG.choice(days[days.year >= 2014], 60, replace=False))
    dates_14_21 = [pd.Timestamp(d) for d in dates_14_21]
    sh = shanker_dates(range(2014, 2022), set(dates_14_21))
    res["cross_shankerabhigyan"] = compare(mine[mine.date.isin(dates_14_21)], sh, "dudesurfin vs shankerabhigyan")
    dates_20_21 = [pd.Timestamp(d) for d in sorted(RNG.choice(days[days.year >= 2020], 30, replace=False))]
    gr = graupe_dates(set(dates_20_21))
    res["cross_kylegraupe"] = compare(mine[mine.date.isin(dates_20_21)], gr, "dudesurfin vs kylegraupe (same schema)")
    (HERE / "step0.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({k: v for k, v in res.items() if k not in ("missing_days", "extra_days_not_trading")}, indent=1,
                     default=str))
    print("missing days:", res["missing_days"][:40], "..." if len(res["missing_days"]) > 40 else "")
    print("extra days:", res["extra_days_not_trading"][:20])


if __name__ == "__main__":
    main()
