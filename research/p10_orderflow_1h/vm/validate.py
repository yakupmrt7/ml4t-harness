"""p10 validation (PLAN.md amendment 1), run on the VM for one month: raw daily aggTrades
(re-downloaded, sha256-checked) and the reducer's 1-minute output vs the 5m klines.

 1. daily totals: volume and taker-buy volume within 1e-9 relative, trade count within 1e-5
 2. every per-bar residual (kline - aggTrade sum) covered by the qty of aggTrades stamped
    within 1 s before that bar's start or end boundary
 3. share of exactly matching bars, max |residual|/volume
Also checks the reducer's 1-minute output (from GCS) sums to the same 5m values as the raw.

  python validate.py --month 2023-06 --klines BTCUSDT-5m-2023-06.zip
"""
import argparse
import calendar
import hashlib
import io
import json
import subprocess
import zipfile

import numpy as np
import pandas as pd

from reduce_flow import OUT, SRC, fetch, read_zip

KL = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "count",
      "taker_buy_volume", "taker_buy_quote_volume", "ignore"]


def klines(path):
    with zipfile.ZipFile(path) as z, z.open(z.namelist()[0]) as f:
        k = pd.read_csv(f, header=None, names=KL)
    if not str(k.iloc[0, 0]).isdigit():
        k = k.iloc[1:]
    k = k.astype({"close_time": "int64", "volume": float, "taker_buy_volume": float, "count": "int64"})
    k.index = pd.to_datetime(k["close_time"] + 1, unit="ms", utc=True)
    return k


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True)
    ap.add_argument("--klines", required=True)
    a = ap.parse_args()
    y, m = map(int, a.month.split("-"))
    K = klines(a.klines)
    rows, bad = [], []
    for day in range(1, calendar.monthrange(y, m)[1] + 1):
        d = f"{a.month}-{day:02d}"
        url = SRC.format(d=d)
        raw = fetch(url)
        assert hashlib.sha256(raw).hexdigest() == fetch(url + ".CHECKSUM").split()[0].decode(), d
        df = read_zip(raw)
        t = df["transact_time"].to_numpy()
        sell = df["is_buyer_maker"].str.lower().to_numpy() == "true"
        qty = df["quantity"].to_numpy()
        ntr = (df["last_trade_id"] - df["first_trade_id"] + 1).to_numpy()
        be = pd.to_datetime((t // 300_000 + 1) * 300_000, unit="ms", utc=True)
        near = (t % 300_000) >= 299_000                                   # within 1 s before the bar end
        g = pd.DataFrame({"vol": qty, "buy": np.where(sell, 0.0, qty), "n": ntr,
                          "near": np.where(near, qty, 0.0)}, index=be).groupby(level=0).sum()
        k = K.loc[g.index.min():g.index.max()]
        j = k[["volume", "taker_buy_volume", "count"]].join(g, how="inner")
        tot = {"vol": abs(j["volume"].sum() - j["vol"].sum()) / j["volume"].sum(),
               "buy": abs(j["taker_buy_volume"].sum() - j["buy"].sum()) / j["taker_buy_volume"].sum(),
               "count": abs(j["count"].sum() - j["n"].sum()) / j["count"].sum()}
        res = j["volume"] - j["vol"]
        bound = j["near"] + j["near"].shift(1).fillna(0)
        covered = (res.abs() <= bound + 1e-9)
        # reducer output (GCS) must reproduce the raw 5m sums
        pq = f"{OUT}/1m/date={d}/flow_{d}.parquet"
        buf = subprocess.run(["gcloud", "storage", "cat", pq], capture_output=True).stdout
        f = pd.read_parquet(io.BytesIO(buf))
        f5 = f.resample("5min", label="right", closed="right")[["buy_qty", "sell_qty", "n_trades"]].sum()
        jj = g.join(f5, how="inner")
        red_ok = bool(np.allclose(jj["vol"], jj["buy_qty"] + jj["sell_qty"], rtol=1e-9, atol=1e-9)
                      and np.allclose(jj["buy"], jj["buy_qty"], rtol=1e-9, atol=1e-9) and (jj["n"] == jj["n_trades"]).all())
        r = {"date": d, "bars": len(j), "tot_rel_vol": tot["vol"], "tot_rel_buy": tot["buy"], "tot_rel_count": tot["count"],
             "covered_share": float(covered.mean()), "exact_share": float((res.abs() <= 1e-9).mean()),
             "max_res_rel": float((res.abs() / j["volume"]).max()), "reducer_matches_raw": red_ok}
        r["pass"] = bool(tot["vol"] <= 1e-9 and tot["buy"] <= 1e-9 and tot["count"] <= 1e-5 and covered.all() and red_ok)
        rows.append(r)
        print(json.dumps(r), flush=True)
    s = pd.DataFrame(rows)
    summary = {"month": a.month, "days": len(s), "days_pass": int(s["pass"].sum()), "all_pass": bool(s["pass"].all()),
               "exact_share_mean": float(s["exact_share"].mean()), "max_res_rel": float(s["max_res_rel"].max()),
               "max_tot_rel_count": float(s["tot_rel_count"].max())}
    print("SUMMARY", json.dumps(summary))
    json.dump({"summary": summary, "days": rows}, open(f"validate_{a.month}.json", "w"), indent=1)
