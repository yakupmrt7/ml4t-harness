"""p22 step 0 checks (dev dates only):
 1. DoltHub AAPL quotes vs Kaggle kylegraupe AAPL (optionsDX, 16:00 ET) on common dates/contracts: is DoltHub an
    end-of-day snapshot? (mid differences; a large systematic gap would mean a different snapshot time)
 2. DoltHub earnings `when` vs SEC EDGAR 8-K Item 2.02 acceptance times for a sample of companies.

  python research/p22_earnings_straddles/step0_checks.py
"""
import io
import json
import time
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
D = Path("data/collector/p22")
DEV_END = pd.Timestamp("2024-12-31")
UA = {"User-Agent": "quant-research-harness p22 research yakupmertkarasulu@gmail.com"}
CIK = {"AAPL": 320193, "MSFT": 789019, "JPM": 19617, "JNJ": 200406, "NFLX": 1065280, "WMT": 104169, "NKE": 320187,
       "ORCL": 1341439}


def snapshot_check():
    q = pd.read_parquet(D / "quotes" / "AAPL.parquet")
    q["date"], q["expiration"] = pd.to_datetime(q.date), pd.to_datetime(q.expiration)
    for c in ("strike", "bid", "ask"):
        q[c] = pd.to_numeric(q[c], errors="coerce")
    q["type"] = q.call_put.str.lower().str[0]
    q["mid"] = (q.bid + q.ask) / 2
    dates = set(q.date[(q.date <= "2023-03-31")])
    z = zipfile.ZipFile(D / "aapl_graupe.zip")
    name = [n for n in z.namelist() if n.endswith(".csv")]
    keep = []
    for n in name:
        with z.open(n) as f:
            for ch in pd.read_csv(io.TextIOWrapper(f, encoding="utf-8-sig"), chunksize=400_000, skipinitialspace=True):
                ch.columns = [c.strip().strip("[]") for c in ch.columns]
                ch["date"] = pd.to_datetime(ch.QUOTE_DATE.astype(str).str.strip())
                ch = ch[ch.date.isin(dates)]
                if len(ch):
                    for t, b, a in (("c", "C_BID", "C_ASK"), ("p", "P_BID", "P_ASK")):
                        keep.append(pd.DataFrame({"date": ch.date, "expiration": pd.to_datetime(ch.EXPIRE_DATE.astype(str).str.strip()),
                                                  "strike": pd.to_numeric(ch.STRIKE, errors="coerce"), "type": t,
                                                  "mid_o": (pd.to_numeric(ch[b], errors="coerce") + pd.to_numeric(ch[a], errors="coerce")) / 2}))
    o = pd.concat(keep)
    j = q.merge(o, on=["date", "expiration", "strike", "type"]).dropna(subset=["mid", "mid_o"])
    j = j[(j.mid > 0) & (j.mid_o > 0)]
    rel = (j.mid / j.mid_o - 1)
    return {"matched_quotes": int(len(j)), "dates": int(j.date.nunique()),
            "median_abs_mid_diff_$": float((j.mid - j.mid_o).abs().median()),
            "median_rel_diff": float(rel.median()), "median_abs_rel_diff": float(rel.abs().median()),
            "share_within_5pct": float((rel.abs() <= 0.05).mean())}


def edgar_check():
    ev = pd.read_parquet(D / "events.parquet")
    out = []
    for sym, cik in CIK.items():
        url = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
        d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read())
        r = d["filings"]["recent"]
        f = pd.DataFrame({"form": r["form"], "items": r["items"], "acc": r["acceptanceDateTime"], "fdate": r["filingDate"]})
        f = f[(f.form == "8-K") & f["items"].str.contains("2.02")]
        f["acc"] = pd.to_datetime(f.acc).dt.tz_convert("America/New_York")
        e = ev[(ev.company == sym) & ev.date.le(DEV_END)]
        for x in e.itertuples():
            m = f[(f.acc.dt.tz_localize(None).dt.normalize() >= x.date - pd.Timedelta(days=1)) &
                  (f.acc.dt.tz_localize(None).dt.normalize() <= x.date + pd.Timedelta(days=1))]
            if m.empty:
                out.append({"sym": sym, "date": x.date, "when": x.when, "edgar": None})
                continue
            t = m.acc.iloc[-1]
            edgar_when = "before" if t.hour < 9 or (t.hour == 9 and t.minute < 30) else ("after" if t.hour >= 16 else "during")
            out.append({"sym": sym, "date": x.date, "when": x.when, "edgar_time": str(t), "edgar": edgar_when,
                        "same_day": t.date() == x.date.date()})
        time.sleep(0.5)
    o = pd.DataFrame(out)
    have = o[o.edgar.notna()]
    agree = have.apply(lambda r: isinstance(r.when, str) and r.edgar in r.when.lower(), axis=1)
    return {"events": int(len(o)), "with_edgar_8k": int(len(have)), "timing_agree_share": float(agree.mean()) if len(have) else None,
            "edgar_during_market": int((have.edgar == "during").sum()),
            "disagreements": have[~agree][["sym", "date", "when", "edgar_time"]].astype(str).to_dict("records")[:15]}


if __name__ == "__main__":
    res = {"snapshot_vs_optionsdx_aapl": snapshot_check(), "earnings_timing_vs_edgar": edgar_check()}
    (HERE / "step0_checks.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str))
