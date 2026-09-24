"""p11 backfill (PLAN amendment 1), 2022-08-01 -> 2026-08-31, into data/collector/p11/. Resumable.

  python backfill.py opt              Deribit BTC option trades (history.deribit.com), one parquet per UTC day
  python backfill.py bybit            Bybit linear BTCUSDT funding (8 h) + 5 m klines
  python backfill.py okx              OKX BTC-USDT-SWAP 5 m candles
  python backfill.py deribit_www OUT  DVOL 1 h + BTC-PERPETUAL hourly funding -> OUT/*.json (www.deribit.com;
                                      stdlib only, so it can run on a box that reaches www.deribit.com)
"""
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

START, END = date(2022, 8, 1), date(2026, 8, 31)
DST = Path("data/collector/p11")
MS_DAY = 86_400_000


def ms(d):
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


def get(url, data=None, tries=8):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None,
                                         headers={"User-Agent": "ml4t-harness-p11", "Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=60).read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(min(60, 2 ** k))
                continue
            raise
        except Exception:
            time.sleep(min(60, 2 ** k))
    raise RuntimeError(f"failed: {url}")


def days():
    d = START
    while d <= END:
        yield d
        d += timedelta(1)


# ---------------------------------------------------------------- Deribit option trades
OPT_COLS = ("timestamp", "trade_id", "instrument_name", "price", "iv", "index_price", "mark_price", "amount", "direction")


def opt_day(d):
    import pandas as pd
    out = DST / "deribit_opt" / f"opt_{d}.parquet"
    if out.exists():
        return d, "skip", 0, 0
    t0, t1 = ms(d), ms(d) + MS_DAY
    rows, seen, start, calls = [], set(), t0, 0
    while True:
        r = get("https://history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time?currency=BTC&kind=option"
                f"&start_timestamp={start}&end_timestamp={t1 - 1}&count=1000&sorting=asc")["result"]
        calls += 1
        new = [t for t in r["trades"] if t["trade_id"] not in seen]
        for t in new:
            seen.add(t["trade_id"])
            rows.append({c: t.get(c) for c in OPT_COLS})
        if not r.get("has_more") or not r["trades"]:
            break
        last = r["trades"][-1]["timestamp"]
        start = last if new else last + 1            # same-ms trades: re-query from the same ms, dedupe by id
        time.sleep(0.1)
    df = pd.DataFrame(rows, columns=OPT_COLS)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".part")
    df.to_parquet(tmp)
    tmp.rename(out)
    return d, "ok", len(df), calls


def opt():
    ds = list(days())
    with ThreadPoolExecutor(4) as ex:
        for i, r in enumerate(ex.map(opt_day, ds)):
            if i % 25 == 0:
                print(i, *r, flush=True)
    print("OPT DONE", flush=True)


# ---------------------------------------------------------------- Bybit
def bybit():
    import pandas as pd
    (DST / "bybit").mkdir(parents=True, exist_ok=True)
    f = DST / "bybit" / "funding.parquet"
    if not f.exists():
        rows, end = [], ms(END) + MS_DAY
        while True:
            L = get(f"https://api.bybit.com/v5/market/funding/history?category=linear&symbol=BTCUSDT&startTime={ms(START)}"
                    f"&endTime={end}&limit=200")["result"]["list"]
            if not L:
                break
            rows += L
            end = int(L[-1]["fundingRateTimestamp"]) - 1               # newest first
            if end < ms(START):
                break
            time.sleep(0.2)
        df = pd.DataFrame(rows).drop_duplicates("fundingRateTimestamp")
        df.to_parquet(f)
        print("bybit funding", len(df), flush=True)
    k = DST / "bybit" / "klines_5m.parquet"
    if not k.exists():
        rows, s = [], ms(START)
        stop = ms(END) + MS_DAY
        while s < stop:
            e = min(s + 1000 * 300_000 - 1, stop - 1)
            L = get(f"https://api.bybit.com/v5/market/kline?category=linear&symbol=BTCUSDT&interval=5&start={s}&end={e}&limit=1000")["result"]["list"]
            rows += L
            s = e + 1
            time.sleep(0.1)
        df = pd.DataFrame(rows, columns=["start", "open", "high", "low", "close", "volume", "turnover"]).drop_duplicates("start")
        df.to_parquet(k)
        print("bybit klines", len(df), flush=True)


# ---------------------------------------------------------------- OKX
def okx():
    import pandas as pd
    out = DST / "okx" / "candles_5m.parquet"
    if out.exists():
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    rows, after = [], ms(END) + MS_DAY                                  # paginate backwards: ts < after
    while after > ms(START):
        L = get(f"https://www.okx.com/api/v5/market/history-candles?instId=BTC-USDT-SWAP&bar=5m&after={after}&limit=100")["data"]
        if not L:
            break
        rows += L
        after = int(L[-1][0])
        time.sleep(0.12)
        if len(rows) % 20000 < 100:
            print("okx", len(rows), datetime.fromtimestamp(after / 1000, timezone.utc), flush=True)
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "vol", "volCcy", "volCcyQuote", "confirm"])
    df = df.drop_duplicates("ts")
    df = df[df["ts"].astype("int64") >= ms(START)]
    df.to_parquet(out)
    print("okx candles", len(df), flush=True)


# ---------------------------------------------------------------- Deribit www (stdlib only)
def deribit_www(outdir):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    B = "https://www.deribit.com/api/v2/public/"
    dv, end = [], ms(END) + MS_DAY
    while True:
        r = get(f"{B}get_volatility_index_data?currency=BTC&start_timestamp={ms(START) - 40 * MS_DAY}&end_timestamp={end}&resolution=3600")["result"]
        dv += r["data"]
        if not r.get("continuation"):
            break
        end = r["continuation"]
        time.sleep(0.2)
    (out / "dvol_1h.json").write_text(json.dumps(dv))
    fr, s = [], ms(START) - 10 * MS_DAY
    while s < ms(END) + MS_DAY:
        e = s + 20 * MS_DAY
        fr += get(f"{B}get_funding_rate_history?instrument_name=BTC-PERPETUAL&start_timestamp={s}&end_timestamp={e}")["result"]
        s = e
        time.sleep(0.2)
    (out / "deribit_funding_1h.json").write_text(json.dumps(fr))
    print("dvol rows", len(dv), "funding rows", len(fr))


if __name__ == "__main__":
    cmd = sys.argv[1]
    {"opt": opt, "bybit": bybit, "okx": okx}.get(cmd, lambda: deribit_www(sys.argv[2]))()
