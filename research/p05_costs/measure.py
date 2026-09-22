"""p05 step 1-3: stream sampled days of aggTrades (+ bookTicker where it
exists), reduce each (asset, day) to statistics, delete the raw files.

Sampled days (PLAN.md): the 3rd, 10th, 17th and 24th of each month,
2022-08 -> 2026-08, up to each asset's last live day. bookTicker exists only
2023-05-16 -> 2024-03-30.

Per (asset, day) -> data/bars/p05/<asset>/<date>.parquet (orders) and
<date>.json (day stats). Resumable: finished days are skipped.

Downloads run in a thread pool (I/O bound; the archive serves ~0.3-1 MB/s per
connection), processing in a small process pool (a BTC bookTicker day is
~12M rows, ~2 GB RAM).

Run from the repo root:  PYTHONPATH=. python research/p05_costs/measure.py
"""
import hashlib
import json
import sys
import time
import traceback
import urllib.error
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, ThreadPoolExecutor, wait
from pathlib import Path

import numpy as np
import pandas as pd

from harness.costs import (effective_half_spread, half_spread_bps, load_agg_trades, load_book_ticker, quote_asof,
                           simulate_maker, time_weighted_half_spread, trade_proxy_quotes)

HERE = Path(__file__).parent
UNI = json.loads(Path("research/p04_multiasset/universe.json").read_text())
STAGE = Path("data/raw/p05_stage")
OUTD = Path("data/bars/p05")
BASE = "https://data.binance.vision/data/futures/um/daily"
DAYS = (3, 10, 17, 24)
BT_FIRST, BT_LAST = pd.Timestamp("2023-05-16"), pd.Timestamp("2024-03-30")
GRID_HOURS = (0, 4, 8, 12, 16)          # 4h grid, t <= 19:00 so t + 60 + 240 min stays in the day
LAST_POST = pd.Timedelta(hours=19)
NOTIONALS = (10_000, 100_000)
N_DL, N_PROC, MAX_STAGED = 12, 4, 16


def sampled_days(asset):
    last = pd.Timestamp(UNI["lifetimes"][asset]["last_live_bar"]).tz_localize(None).normalize()
    out = []
    for m in pd.period_range("2022-08", "2026-08", freq="M"):
        for d in DAYS:
            day = pd.Timestamp(year=m.year, month=m.month, day=d)
            if day < last:                     # a full live day
                out.append(day)
    return out


def jobs():
    js = []
    for a in UNI["universe"]:
        for day in sampled_days(a):
            if (OUTD / a / f"{day.date()}.json").exists():
                continue
            js.append((a, day, BT_FIRST <= day <= BT_LAST))
    # interleave assets so heavy BTC/ETH bookTicker days are not all in flight together
    js.sort(key=lambda j: (j[1], UNI["universe"].index(j[0])))
    return js


def fetch(url, dest):
    if dest.exists():
        return dest
    for attempt in range(5):
        try:
            data = urllib.request.urlopen(url, timeout=900).read()
            want = urllib.request.urlopen(url + ".CHECKSUM", timeout=60).read().split()[0].decode()
            if hashlib.sha256(data).hexdigest() != want:
                raise IOError("bad checksum")
            tmp = dest.with_suffix(".part")
            tmp.write_bytes(data)
            tmp.rename(dest)
            return dest
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            err = e
        except Exception as e:  # noqa: BLE001 - retry any transport error
            err = e
        time.sleep(5 * (attempt + 1))
    raise IOError(f"{url}: {err}")


def download(job):
    a, day, has_bt = job
    d = day.date()
    STAGE.mkdir(parents=True, exist_ok=True)
    ag = fetch(f"{BASE}/aggTrades/{a}/{a}-aggTrades-{d}.zip", STAGE / f"{a}-aggTrades-{d}.zip")
    bt = fetch(f"{BASE}/bookTicker/{a}/{a}-bookTicker-{d}.zip", STAGE / f"{a}-bookTicker-{d}.zip") if has_bt else None
    return job, ag, bt


def post_times(a, day, p04):
    start = pd.Timestamp(day, tz="UTC")
    grid = [start + pd.Timedelta(hours=h) for h in GRID_HOURS]
    g = pd.DataFrame({"side": [1.0] * len(grid) + [-1.0] * len(grid), "kind": "grid"},
                     index=pd.DatetimeIndex(grid + grid))
    x = p04[(p04["asset"] == a) & (p04["t"] >= start) & (p04["t"] <= start + LAST_POST)]
    q = pd.DataFrame({"side": x["side"].to_numpy(float), "kind": "p04"}, index=pd.DatetimeIndex(x["t"]))
    return pd.concat([g, q])


def process(job, ag_path, bt_path):
    a, day, _ = job
    start, end = pd.Timestamp(day, tz="UTC"), pd.Timestamp(day, tz="UTC") + pd.Timedelta(days=1)
    p04 = pd.read_parquet(HERE / "p04_trade_times.parquet")
    tr = load_agg_trades(ag_path)
    tr = tr[(tr.index >= start) & (tr.index < end)]
    px = trade_proxy_quotes(tr)
    notional = tr["price"] * tr["qty"]
    eff_px = effective_half_spread(tr)
    ok = np.isfinite(eff_px)
    st = {"asset": a, "date": str(day.date()), "month": day.strftime("%Y-%m"), "n_trades": int(len(tr)),
          "volume_usd": float(notional.sum()), "has_bookticker": bt_path is not None,
          "eff_hs_proxy_tw": float(eff_px[ok].mean()),
          "eff_hs_proxy_vw": float((eff_px[ok] * notional[ok]).sum() / notional[ok].sum()),
          "tick_bps_trades": float(np.diff(np.unique(tr["price"].to_numpy())).min() / tr["price"].median() * 1e4)}
    posts = post_times(a, day, p04)
    sims = [simulate_maker(posts[["side"]], px, tr).assign(kind=posts["kind"].to_numpy(), quotes="proxy")]
    if bt_path is not None:
        bt = load_book_ticker(bt_path)
        bt = bt[(bt.index >= start - pd.Timedelta(minutes=1)) & (bt.index < end)]
        eff_bt = effective_half_spread(tr, bt)
        okb = np.isfinite(eff_bt)
        spread_px = (bt["ask"] - bt["bid"])
        pos = spread_px[spread_px > 0]
        st.update({
            "n_quotes": int(len(bt)), "tw_hs_bt": time_weighted_half_spread(bt, start, end),
            "eff_hs_bt_tw": float(eff_bt[okb].mean()),
            "eff_hs_bt_vw": float((eff_bt[okb] * notional[okb]).sum() / notional[okb].sum()),
            "tick_bps_quotes": float(pos.min() / ((bt["ask"] + bt["bid"]) / 2).median() * 1e4),
            "frac_time_one_tick": float(np.isclose(spread_px, pos.min()).mean())})
        sb = simulate_maker(posts[["side"]], bt, tr).assign(kind=posts["kind"].to_numpy(), quotes="bookTicker")
        q = quote_asof(bt, posts.index)
        take_depth = np.where(posts["side"].to_numpy() > 0, q["ask"] * q["ask_qty"], q["bid"] * q["bid_qty"])
        sb["take_side_depth_usd"] = take_depth
        for n in NOTIONALS:
            sb[f"exceeds_top_{n // 1000}k"] = take_depth < n
        sims.append(sb)
    orders = pd.concat(sims)
    orders["hs_bps"] = half_spread_bps(orders)
    orders.insert(0, "asset", a)
    out = OUTD / a
    out.mkdir(parents=True, exist_ok=True)
    orders.rename_axis("t").to_parquet(out / f"{day.date()}.parquet")
    (out / f"{day.date()}.json").write_text(json.dumps(st))
    for f in (ag_path, bt_path):
        if f is not None:
            f.unlink()
    return a, str(day.date())


def process_safe(job, ag, bt):
    try:
        return process(job, ag, bt), None
    except Exception:  # noqa: BLE001 - report and continue with other days
        return (job[0], str(job[1].date())), traceback.format_exc()


if __name__ == "__main__":
    js = jobs()
    print(f"{len(js)} (asset, day) jobs to do, {sum(j[2] for j in js)} with bookTicker", flush=True)
    t0, done, errors = time.time(), 0, []
    with ThreadPoolExecutor(N_DL) as dl, ProcessPoolExecutor(N_PROC) as pp:
        pending_dl, pending_pp = set(), set()
        it = iter(js)
        while True:
            while len(pending_dl) + len(pending_pp) < MAX_STAGED:
                j = next(it, None)
                if j is None:
                    break
                pending_dl.add(dl.submit(download, j))
            if not pending_dl and not pending_pp:
                break
            finished, _ = wait(pending_dl | pending_pp, return_when=FIRST_COMPLETED)
            for f in finished:
                if f in pending_dl:
                    pending_dl.discard(f)
                    try:
                        job, ag, bt = f.result()
                    except Exception as e:  # noqa: BLE001
                        errors.append(repr(e)); print("DOWNLOAD ERROR", e, flush=True); continue
                    if ag is None:
                        errors.append(f"missing aggTrades {job[0]} {job[1].date()}"); print(errors[-1], flush=True); continue
                    pending_pp.add(pp.submit(process_safe, job, ag, bt))
                else:
                    pending_pp.discard(f)
                    (a, d), err = f.result()
                    done += 1
                    if err:
                        errors.append(f"{a} {d}: {err}"); print("PROCESS ERROR", a, d, err, flush=True)
                    if done % 25 == 0 or err:
                        el = time.time() - t0
                        print(f"{done}/{len(js)} done, {el / 60:.0f} min, ETA {el / done * (len(js) - done) / 60:.0f} min", flush=True)
    print(f"FINISHED {done} jobs, {len(errors)} errors in {(time.time() - t0) / 60:.0f} min", flush=True)
    for e in errors[:20]:
        print(" ", e.splitlines()[0] if e else e)
    sys.exit(1 if errors else 0)
