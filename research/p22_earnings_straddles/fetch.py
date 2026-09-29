"""p22 data (PLAN.md): S&P 100 (as of 2019-11-21) earnings events 2020-01-22..2024-12-31 from DoltHub, and the option
quotes on the entry/exit days of each event and its placebo. DEV ONLY: no query touches a date after 2024-12-31.

  python research/p22_earnings_straddles/fetch.py
Outputs (gitignored): data/collector/p22/{events.parquet, quotes/<SYMBOL>.parquet, spy_days.json}
"""
import json
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

D = Path("data/collector/p22")
Q = D / "quotes"
DEV_END = pd.Timestamp("2024-12-31")
START = pd.Timestamp("2020-01-22")
ALIASES = {"FB": ["FB", "META"], "UTX": ["UTX", "RTX"], "BRK.B": ["BRK.B", "BRK/B", "BRK-B"]}
DROP = {"GOOG"}                                                         # duplicate share class of GOOGL
OPT = "https://www.dolthub.com/api/v1alpha1/post-no-preference/options/master?q="
ERN = "https://www.dolthub.com/api/v1alpha1/post-no-preference/earnings/master?q="


class RowLimit(Exception):
    """DoltHub's SQL API returns at most 1,000 rows and flags the result 'RowLimit' (found 2026-09-29)."""


def q(base, sql, tries=6):
    for k in range(tries):
        try:
            r = json.loads(urllib.request.urlopen(base + urllib.parse.quote(sql), timeout=180).read())
            st = r.get("query_execution_status")
            if st == "Success":
                return r.get("rows") or []
            if st == "RowLimit":
                raise RowLimit(sql[:120])
            err = r.get("query_execution_message")
        except RowLimit:
            raise
        except Exception as e:
            err = repr(e)
        time.sleep(3 * (k + 1))
    raise RuntimeError(f"{err}: {sql[:120]}")


def trading_days():
    f = D / "spy_days.json"
    if not f.exists():
        url = "https://query1.finance.yahoo.com/v8/finance/chart/SPY?period1=1575158400&period2=1735776000&interval=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        d = json.loads(urllib.request.urlopen(req, timeout=60).read())["chart"]["result"][0]
        days = sorted({str(pd.to_datetime(t, unit="s").date()) for t in d["timestamp"]})
        f.write_text(json.dumps(days))
    days = pd.DatetimeIndex(json.loads(f.read_text()))
    return days[days <= DEV_END]


def events(days):
    syms = [s for s in json.load(open(D / "sp100_2020-01-01.json"))["symbols"] if s not in DROP]
    rows = []
    for s in syms:
        al = ALIASES.get(s, [s])
        inl = ",".join(f"'{a}'" for a in al)
        for r in q(ERN, f"SELECT act_symbol, date, `when` FROM earnings_calendar WHERE act_symbol IN ({inl}) "
                         f"AND date BETWEEN '{START.date()}' AND '{DEV_END.date()}'"):
            rows.append({"company": s, "symbol": r["act_symbol"], "date": pd.Timestamp(r["date"]), "when": r["when"]})
    e = pd.DataFrame(rows).drop_duplicates(["company", "date"]).sort_values(["company", "date"]).reset_index(drop=True)
    pos = {d: i for i, d in enumerate(days)}

    def exit_day(r):
        if r.date not in pos:
            return pd.NaT
        w = r.when.lower() if isinstance(r.when, str) else ""
        if "after" in w:
            return r.date
        if "before" in w:
            i = pos[r.date] - 1
            return days[i] if i >= 0 else pd.NaT
        return pd.NaT
    e["X"] = e.apply(exit_day, axis=1)
    out = []
    for r in e.itertuples():
        if pd.isna(r.X):
            out.append({**r._asdict(), "E_cands": [], "Xp": pd.NaT, "Ep_cands": []})
            continue
        i = pos[r.X]
        ec = [days[i - k] for k in (2, 3, 4) if i - k >= 0]
        j = i + 21
        xp = days[j] if j < len(days) else pd.NaT
        epc = [days[j - k] for k in (2, 3, 4)] if not pd.isna(xp) else []
        out.append({**r._asdict(), "E_cands": ec, "Xp": xp, "Ep_cands": epc})
    ev = pd.DataFrame(out).drop(columns=["Index"])
    # placebo validity: no announcement of the same company within +-10 trading days of X'
    ann = {c: set(g.date) for c, g in e.groupby("company")}
    def clean(r):
        if pd.isna(r.Xp) or r.Xp > DEV_END:
            return False
        j = pos[r.Xp]
        win = set(days[max(0, j - 10): j + 11])
        return not (win & ann[r.company])
    ev["placebo_ok"] = ev.apply(clean, axis=1)
    return ev


def pull(symbols, dates, exp_lo, exp_hi):
    """Quotes for the given dates and an expiration window, under the 1,000-row cap: split by date, then by
    expiration window, whenever the API reports RowLimit."""
    dates = sorted({d for d in dates if not pd.isna(d) and d <= DEV_END})
    if not dates:
        return []
    inl = ",".join(f"'{a}'" for a in symbols)
    dl = ",".join(f"'{d.date()}'" for d in dates)
    try:
        return q(OPT, f"SELECT date, act_symbol, expiration, strike, call_put, bid, ask, vol FROM option_chain "
                      f"WHERE date IN ({dl}) AND act_symbol IN ({inl}) "
                      f"AND expiration BETWEEN '{exp_lo.date()}' AND '{exp_hi.date()}'")
    except RowLimit:
        if len(dates) > 1:
            return [r for d in dates for r in pull(symbols, [d], exp_lo, exp_hi)]
        mid = exp_lo + (exp_hi - exp_lo) / 2
        if (exp_hi - exp_lo).days < 2:
            raise
        return pull(symbols, dates, exp_lo, mid.normalize()) + pull(symbols, dates, mid.normalize() + pd.Timedelta(days=1), exp_hi)


def main():
    Q.mkdir(parents=True, exist_ok=True)
    days = trading_days()
    ev = events(days)
    ev.to_parquet(D / "events.parquet")
    print(f"events {len(ev)}, with exit day {ev.X.notna().sum()}, placebo ok {ev.placebo_ok.sum()}", flush=True)
    jobs = []
    for comp, g in ev.groupby("company"):
        f = Q / f"{comp.replace('.', '_')}.parquet"
        if not f.exists():
            jobs.append((comp, ALIASES.get(comp, [comp]), g, f))

    def run(job):
        comp, al, g, f = job
        rows = []
        for r in g.itertuples():                              # one query per event (and one per placebo)
            if pd.isna(r.X):
                continue
            ann = r.date
            rows += pull(al, list(r.E_cands) + [r.X], ann + pd.Timedelta(days=7), ann + pd.Timedelta(days=45))
            if r.placebo_ok:
                rows += pull(al, list(r.Ep_cands) + [r.Xp], r.Xp + pd.Timedelta(days=7), r.Xp + pd.Timedelta(days=45))
        df = pd.DataFrame(rows).drop_duplicates() if rows else pd.DataFrame()
        df.to_parquet(f)
        return comp, len(df)

    with ThreadPoolExecutor(6) as ex:
        for fu in as_completed([ex.submit(run, j) for j in jobs]):
            comp, n = fu.result()
            print(comp, n, time.strftime("%H:%M:%S"), flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
