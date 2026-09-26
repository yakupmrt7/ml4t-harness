"""p08 validation: did the collector drop messages?

Cross-checks the collector's binance_fut btcusdt@trade stream for one day
against Binance's public archive (daily aggTrades), which is the exchange's
own record.

An archive aggTrade aggregates consecutive trades at one price/side/ms and
carries first_trade_id..last_trade_id, so the archive's individual trade ids
are the union of those ranges. The collector records every trade separately
with its own id `t`. So the comparison is exact, not statistical:
  * per hour: trade counts and volume
  * id-level: which archive trade ids never arrived at the collector
  * the gap structure of what is missing (episodes, longest run, when)

Run (on the VM, after the day's events are written):
  ~/venv/bin/python validate_archive.py --date 2026-09-10 [--out result.json]
"""
from __future__ import annotations

import argparse
import io
import json
import urllib.request
import zipfile

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

BUCKET = "YOUR-GCS-BUCKET"
STREAM = "binance_fut__btcusdt@trade"
ARCHIVE = "https://data.binance.vision/data/futures/um/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-{date}.zip"
COLS = ["agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id", "transact_time", "is_buyer_maker"]


def load_archive(date):
    raw = urllib.request.urlopen(ARCHIVE.format(date=date), timeout=900).read()
    z = zipfile.ZipFile(io.BytesIO(raw))
    with z.open(z.namelist()[0]) as fh:
        head = fh.readline()
    skip = 0 if str(head).split(",")[0].strip("b'").isdigit() else 1
    with z.open(z.namelist()[0]) as fh:
        df = pd.read_csv(fh, header=None, names=COLS, skiprows=skip)
    for c in ("agg_trade_id", "first_trade_id", "last_trade_id", "transact_time"):
        df[c] = df[c].astype("int64")
    df["quantity"] = df["quantity"].astype(float)
    return df


def load_collector(date):
    d = ds.dataset(f"gs://{BUCKET}/features/v1/events/{STREAM}/date={date}", format="parquet")
    cols = ["event_ms", "trade_id", "qty"] + (["trade_type"] if "trade_type" in d.schema.names else [])
    t = d.to_table(columns=cols)
    return t.to_pandas()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--out", default="validate_archive.json")
    a = ap.parse_args()

    arc = load_archive(a.date)
    col = load_collector(a.date)

    # the archive's individual trade ids = union of [first_trade_id, last_trade_id]
    counts = (arc["last_trade_id"] - arc["first_trade_id"] + 1).to_numpy()
    arc_ids = np.concatenate([np.arange(f, l + 1) for f, l in
                              zip(arc["first_trade_id"].to_numpy(), arc["last_trade_id"].to_numpy())])
    col_ids = np.unique(col["trade_id"].to_numpy())

    # per-hour comparison (UTC, exchange transact_time vs collector event time)
    arc_h = pd.DataFrame({"hour": pd.to_datetime(arc["transact_time"], unit="ms", utc=True).dt.hour,
                          "n": counts, "vol": arc["quantity"].to_numpy()}).groupby("hour").sum()
    col_h = pd.DataFrame({"hour": pd.to_datetime(col["event_ms"], unit="ms", utc=True).dt.hour,
                          "n": 1, "vol": col["qty"].to_numpy()}).groupby("hour").sum()
    per_hour = arc_h.join(col_h, lsuffix="_archive", rsuffix="_collector", how="outer").fillna(0)
    per_hour["n_diff"] = per_hour["n_collector"] - per_hour["n_archive"]
    per_hour["match_rate"] = per_hour["n_collector"] / per_hour["n_archive"].replace(0, np.nan)
    per_hour["vol_diff_pct"] = (per_hour["vol_collector"] / per_hour["vol_archive"] - 1) * 100

    missing = np.setdiff1d(arc_ids, col_ids, assume_unique=False)      # archive trades the collector never got
    extra = np.setdiff1d(col_ids, arc_ids, assume_unique=False)        # collector ids the archive lacks
    # why extras exist: the archive's aggTrades omit non-MARKET (liquidation/ADL) prints
    extra_by_type, matched_by_type = {}, {}
    if "trade_type" in col:
        is_extra = col["trade_id"].isin(set(extra.tolist()))
        extra_by_type = col.loc[is_extra, "trade_type"].value_counts().to_dict()
        matched_by_type = col.loc[~is_extra, "trade_type"].value_counts().to_dict()

    gaps = []
    if len(missing):
        brk = np.where(np.diff(missing) > 1)[0]
        starts = np.concatenate([[0], brk + 1])
        ends = np.concatenate([brk, [len(missing) - 1]])
        id_to_ms = dict(zip(arc["last_trade_id"].to_numpy(), arc["transact_time"].to_numpy()))
        pos = np.searchsorted(arc["last_trade_id"].to_numpy(), missing[starts])
        pos = np.clip(pos, 0, len(arc) - 1)
        ts = arc["transact_time"].to_numpy()[pos]
        for s, e, t in zip(starts, ends, ts):
            gaps.append({"first_id": int(missing[s]), "last_id": int(missing[e]),
                         "n": int(e - s + 1), "utc": str(pd.Timestamp(t, unit="ms", tz="UTC"))})
        gaps.sort(key=lambda g: -g["n"])

    out = {
        "date": a.date, "stream": STREAM,
        "archive_trades": int(counts.sum()), "archive_aggtrades": int(len(arc)),
        "collector_rows": int(len(col)), "collector_unique_ids": int(len(col_ids)),
        "collector_duplicate_rows": int(len(col) - len(col_ids)),
        "archive_volume": float(arc["quantity"].sum()), "collector_volume": float(col["qty"].sum()),
        "volume_diff_pct": float(col["qty"].sum() / arc["quantity"].sum() * 100 - 100),
        "missing_from_collector": int(len(missing)),
        "match_rate": float(1 - len(missing) / counts.sum()),
        "ids_not_in_archive": int(len(extra)),
        "extra_ids_by_trade_type": {str(k): int(v) for k, v in extra_by_type.items()},
        "matched_ids_by_trade_type": {str(k): int(v) for k, v in matched_by_type.items()},
        "n_gap_episodes": len(gaps), "largest_gaps": gaps[:15],
        "gap_len_p50": float(np.median([g["n"] for g in gaps])) if gaps else 0.0,
        "per_hour": per_hour.reset_index().to_dict(orient="records"),
    }
    print(json.dumps({k: v for k, v in out.items() if k not in ("per_hour", "largest_gaps")}, indent=1))
    print("\nper hour:\n", per_hour.round(4).to_string())
    print("\nlargest gaps:\n", json.dumps(gaps[:10], indent=1))
    with open(a.out, "w") as fh:
        json.dump(out, fh, indent=1)


if __name__ == "__main__":
    main()
