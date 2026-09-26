"""p13 step 2: the event study on dev, as fixed in PLAN.md (step 2 addendum). No trial.

Inputs: windows.parquet (windows.py), data/hl/p13_books/snaps (book_windows.py on the box),
data/hl/p13_fills/ticks (vol), data/raw/spot/*-1s-*.zip (Binance spot 1 s, cross-venue).
  python research/p13_hl_liquidation_history/step2.py   -> window_metrics.parquet, step2.json, step2.log

Split run (the books stay on the Tokyo box; 2026-09-26 the link to it was too slow to pull them):
  box:   python step2.py --stage box --books books/ --windows windows.parquet
         -> wm_box.parquet (0.5 s metrics), window_metrics_5s.parquet, mids1s.npz (HL mid on a 1 s
            grid t0-60..t0+300 s per window, for the cross-venue step)
  local: python research/p13_hl_liquidation_history/step2.py --stage local   (reads those three)
The calculations are identical to a single-machine run.
"""
import argparse
import glob, json, pathlib
import numpy as np, pandas as pd


HERE = pathlib.Path(__file__).parent
ROOT = HERE.parents[1]
BOOKS = ROOT / "data/hl/p13_books"
TICKS = ROOT / "data/hl/p13_fills/ticks"
H = (5, 60, 120, 300)
KILL_H = (60, 120, 300)
FEE_BPS = 4.5
DELAY = 2_000
RNG = np.random.default_rng(13)
BINANCE = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT", "XRP": "XRPUSDT", "ZEC": "ZECUSDT"}


# ---------------------------------------------------------------- loading
def load_books(coin=None):
    """{coin: snapshots}. With `coin`, read only that coin's rows (the box has 7.6 GB; all six at once
    ran out of memory on 2026-09-26)."""
    fs = sorted((BOOKS / "snaps").glob("*.parquet"))
    flt = [("coin", "==", coin)] if coin else None
    b = pd.concat([pd.read_parquet(f, filters=flt) for f in fs], ignore_index=True)
    b = b.drop_duplicates(["coin", "t"]).sort_values(["coin", "t"], kind="stable")
    b["mid"] = (b.bid + b.ask) / 2
    return {c: g.reset_index(drop=True) for c, g in b.groupby("coin")}


def at(book, tq):
    """index of the last snapshot at or before each time in tq (-1 if none)."""
    return np.searchsorted(book.t.to_numpy(), tq, side="right") - 1


def vol_1s(windows):
    """σ of 1 s last-trade log returns over [t0 - 30 min, t0 - 60 s], per window, from our tick tape.
    Ticks are kept in archive (block) order within a millisecond; the last row per second wins."""
    out = pd.Series(np.nan, index=windows.index)
    day = pd.to_datetime(windows.t0, unit="ms", utc=True).dt.strftime("%Y%m%d")
    for d, idx in windows.groupby(day).groups.items():
        prev = (pd.Timestamp(d) - pd.Timedelta(days=1)).strftime("%Y%m%d")
        parts = [pd.read_parquet(TICKS / f"{x}.parquet", columns=["time", "coin", "px"])
                 for x in (prev, d) if (TICKS / f"{x}.parquet").exists()]
        tk = pd.concat(parts, ignore_index=True)
        for c, wi in windows.loc[idx].groupby("coin").groups.items():
            x = tk[tk.coin == c]
            sec = (x.time.to_numpy() // 1000)
            last = pd.Series(x.px.to_numpy(), index=sec).groupby(level=0).last()
            s_idx, s_px = last.index.to_numpy(), last.to_numpy()
            for i in wi:
                t0s = windows.at[i, "t0"] // 1000
                lo, hi = t0s - 1800, t0s - 60
                j0, j1 = np.searchsorted(s_idx, lo, "left"), np.searchsorted(s_idx, hi, "right")
                if j1 - j0 < 30:
                    continue
                grid = np.arange(lo, hi + 1)
                k = np.searchsorted(s_idx[j0:j1], grid, "right") - 1
                ok = k >= 0
                p = np.log(s_px[j0:j1][k[ok]])
                r = np.diff(p)
                out.at[i] = r.std() if len(r) > 100 else np.nan
    return out


def binance_1s(coin):
    sym = BINANCE.get(coin)
    if sym is None:
        return None
    cache = ROOT / f"data/bars/{sym}_1s_close_p13.parquet"
    if cache.exists():
        s = pd.read_parquet(cache)["close"]
    else:
        from harness.data import load_binance_klines
        df = load_binance_klines(str(ROOT / f"data/raw/spot/{sym}-1s-*.zip"))
        # index = bar close; the close is known at that instant -> use last bar with close <= τ
        s = pd.Series(df.close.to_numpy(), index=df.index.asi8 // 1_000_000, name="close")
        s.to_frame().to_parquet(cache)
    return s


# ---------------------------------------------------------------- per-window metrics
def window_metrics(w, books, coarse=False):
    rows = []
    for c, ww in w.groupby("coin"):
        bk = books[c]; bt = bk.t.to_numpy(); mid = bk.mid.to_numpy()
        cols = {k: bk[k].to_numpy() for k in ("spread_bps", "bid_d50", "ask_d50", "sell10k", "buy10k", "sell50k", "buy50k")}
        for i, r in ww.iterrows():
            t0 = r.t0; s = r.s; d = -s
            if coarse:           # a 5 s feed with a random phase: value at τ = snapshot as of the last grid point <= τ
                ph = RNG.integers(0, 5000)
                g = lambda tau: t0 - 65_000 + ph + ((np.asarray(tau) - (t0 - 65_000 + ph)) // 5000) * 5000
            else:
                g = lambda tau: np.asarray(tau)
            n_in = np.searchsorted(bt, t0 + DELAY + 300_000, "right") - np.searchsorted(bt, t0 - 60_000, "left")
            if n_in < 10:                              # archive gap (e.g. 2025-10-16..22): no book, skip
                continue
            q = np.array([t0 - 60_000, t0, t0 + DELAY] + [t0 + DELAY + h * 1000 for h in H])
            k = np.searchsorted(bt, g(q), side="right") - 1
            if (k < 0).any():
                continue
            m = mid[k]
            e = k[2]                                   # entry snapshot
            lo, hi = np.searchsorted(bt, [t0 - 60_000, t0 + DELAY + 300_000])
            seg = bt[max(lo - 1, 0):hi]
            max_gap = np.diff(seg).max() if len(seg) > 1 else np.inf
            rec = dict(window_id=r.window_id, cluster=r.cluster, coin=c, t0=t0, s=s, liq_ntl=r.liq_ntl,
                       max_gap_ms=float(max_gap),
                       pre_move_bps=s * (m[1] / m[0] - 1) * 1e4,
                       push_to_entry_bps=s * (m[2] / m[1] - 1) * 1e4,
                       spread_entry=cols["spread_bps"][e],
                       cost10k_rt=cols["buy10k"][e] + cols["sell10k"][e] + 2 * FEE_BPS,
                       cost50k_rt=cols["buy50k"][e] + cols["sell50k"][e] + 2 * FEE_BPS)
            for j, h in enumerate(H):
                rec[f"rev{h}"] = d * (m[3 + j] / m[2] - 1) * 1e4
                x = k[3 + j]
                rec[f"cost10k_exit{h}"] = cols["buy10k"][e] + cols["sell10k"][x] + 2 * FEE_BPS if s == -1 else \
                                           cols["sell10k"][e] + cols["buy10k"][x] + 2 * FEE_BPS
            if not coarse:
                # book depletion / refill on the absorbing side (bids absorb forced selling)
                dep = cols["bid_d50"] if s == -1 else cols["ask_d50"]
                b0, b1 = np.searchsorted(bt, [t0 - 60_000, t0 - 5_000])
                base = np.median(dep[b0:b1]) if b1 > b0 else np.nan
                a0, a1 = np.searchsorted(bt, [t0, t0 + 300_000])
                post = dep[a0:a1]; pt = bt[a0:a1]
                rec["depth_base"] = base
                if len(post) and base > 0:
                    ratio = post / base
                    rec["depth_min_ratio_60s"] = ratio[pt <= t0 + 60_000].min() if (pt <= t0 + 60_000).any() else np.nan
                    imin = int(np.argmin(ratio[pt <= t0 + 60_000])) if (pt <= t0 + 60_000).any() else 0
                    back = np.nonzero(ratio[imin:] >= 0.9)[0]
                    rec["refill_s"] = (pt[imin + back[0]] - t0) / 1000 if len(back) else 300.0
                    rec["refill_censored"] = not len(back)
                sp = cols["spread_bps"]
                rec["spread_base"] = np.median(sp[b0:b1]) if b1 > b0 else np.nan
                s0, s1 = np.searchsorted(bt, [t0, t0 + 30_000])
                rec["spread_max30"] = sp[s0:s1].max() if s1 > s0 else np.nan
            rows.append(rec)
    return pd.DataFrame(rows)


def mids_1s(wm, books):
    """HL book mid at t0 + (-60..300) s per window (last snapshot at or before each second)."""
    ids, arr = [], []
    for c, ww in wm.groupby("coin"):
        bk = books[c]; bt = bk.t.to_numpy(); mid = bk.mid.to_numpy()
        for _, r in ww.iterrows():
            kh = np.searchsorted(bt, r.t0 + np.arange(-60, 301) * 1000, "right") - 1
            if (kh < 0).any():
                continue
            ids.append(r.window_id); arr.append(mid[kh].astype(np.float64))
    return np.array(ids), np.array(arr)


def dislocation(wm, ids, mids):
    """HL mid vs Binance spot 1 s close, de-meaned on [t0-60, t0-5] s, in bps, signed by s."""
    out = []
    pos = {w: i for i, w in enumerate(ids)}
    for c, ww in wm.groupby("coin"):
        bn = binance_1s(c)
        if bn is None:
            continue
        bx, bp = bn.index.to_numpy(), bn.to_numpy()
        for _, r in ww.iterrows():
            if r.window_id not in pos:
                continue
            grid = r.t0 + np.arange(-60, 301) * 1000
            kb = np.searchsorted(bx, grid, "right") - 1
            if (kb < 0).any():
                continue
            dev = np.log(mids[pos[r.window_id]] / bp[kb]) * 1e4
            dev = r.s * (dev - np.median(dev[:56]))           # >0 = HL pushed further than Binance
            post = dev[60:]
            pk = int(np.argmax(post[:61]))
            back = np.nonzero(np.abs(post[pk:]) <= 2)[0]
            out.append(dict(window_id=r.window_id, disloc_peak_bps=post[pk], disloc_peak_s=pk,
                            disloc_back_s=(pk + back[0]) if len(back) else np.nan))
    return pd.DataFrame(out)


# ---------------------------------------------------------------- aggregation
def boot_median(df, col, reps=500):
    """95% CI of the median of `col`, resampling clusters (a multi-coin cluster is one draw)."""
    g = df.groupby("cluster")[col].apply(np.array)
    arr = list(g.values)
    if len(arr) < 20:
        return (np.nan, np.nan)
    meds = []
    for _ in range(reps):
        pick = RNG.integers(0, len(arr), len(arr))
        meds.append(np.nanmedian(np.concatenate([arr[i] for i in pick])))
    return tuple(np.percentile(meds, [2.5, 97.5]))


def summarise(wm, label):
    n_days = pd.to_datetime(wm.t0, unit="ms", utc=True).dt.floor("D").value_counts()
    res = dict(label=label, windows=len(wm), clusters=int(wm.cluster.nunique()),
               n_eff_days=float(n_days.sum() ** 2 / (n_days ** 2).sum()),
               cost10k_rt_p50=float(wm.cost10k_rt.median()), cost50k_rt_p50=float(wm.cost50k_rt.median()),
               spread_entry_p50=float(wm.spread_entry.median()))
    for h in H:
        ci = boot_median(wm, f"rev{h}")
        res[f"rev{h}_p50"] = float(wm[f"rev{h}"].median()); res[f"rev{h}_ci"] = [float(ci[0]), float(ci[1])]
        res[f"rev{h}_mean"] = float(wm[f"rev{h}"].mean())
        res[f"net{h}_p50"] = float((wm[f"rev{h}"] - wm.cost10k_rt).median())
        res[f"share_rev{h}_gt_cost"] = float((wm[f"rev{h}"] > wm.cost10k_rt).mean())
    return res


def kill2(s_all, s_top):
    clears = {f"{nm}_h{h}": s[f"rev{h}_p50"] >= s["cost10k_rt_p50"]
              for nm, s in (("all", s_all), ("top", s_top)) for h in KILL_H}
    return dict(clears=clears, killed=not any(clears.values()))


def box_stage(books_dir, windows_path, out_dir):
    global BOOKS
    BOOKS = pathlib.Path(books_dir); out = pathlib.Path(out_dir)
    w_all = pd.read_parquet(windows_path)
    parts_m, parts_c, parts_i, parts_z = [], [], [], []
    for c in sorted(w_all.coin.unique()):            # one coin in memory at a time
        books = load_books(c)
        if c not in books:
            continue
        w = w_all[w_all.coin == c]
        m = window_metrics(w, books); parts_m.append(m)
        parts_c.append(window_metrics(w, books, coarse=True))
        i, z = mids_1s(m, books); parts_i.append(i); parts_z.append(z)
        print(c, len(w), "windows,", len(m), "with books", flush=True)
        del books
    w = w_all
    wm = pd.concat(parts_m, ignore_index=True); wc = pd.concat(parts_c, ignore_index=True)
    ids = np.concatenate(parts_i); mids = np.concatenate(parts_z)
    wm.to_parquet(out / "wm_box.parquet"); wc.to_parquet(out / "window_metrics_5s.parquet")
    np.savez_compressed(out / "mids1s.npz", ids=ids, mids=mids)
    print(f"box stage: {len(w)} windows in, {len(wm)} with books, {len(wc)} coarse, {len(ids)} mid grids")


def main():
    wm = pd.read_parquet(HERE / "wm_box.parquet")
    wc = pd.read_parquet(HERE / "window_metrics_5s.parquet")
    z = np.load(HERE / "mids1s.npz")
    w_all = pd.read_parquet(HERE / "windows.parquet")
    vc = HERE / "sigma1s_cache.parquet"         # vol only depends on windows + ticks; cache it
    if vc.exists():
        wm = wm.merge(pd.read_parquet(vc), on="window_id", how="left")
    else:
        wm["sigma1s"] = vol_1s(wm)
        wm[["window_id", "sigma1s"]].to_parquet(vc)
    for h in H:
        wm[f"rev{h}_vol"] = wm[f"rev{h}"] / 1e4 / (wm.sigma1s * np.sqrt(h))
    wm = wm.merge(dislocation(wm, z["ids"], z["mids"]), on="window_id", how="left")
    wm.to_parquet(HERE / "window_metrics.parquet")

    ok = wm.max_gap_ms <= 2000
    main_ = wm[ok]
    top_thr = main_.liq_ntl.quantile(0.9)
    out = dict(n_windows_defined=len(w_all), n_windows_with_books=len(wm),
               n_windows_no_book=int(len(w_all) - len(wm)), n_cadence_ok=int(ok.sum()),
               top_decile_liq_ntl_threshold=float(top_thr))
    out["all"] = summarise(main_, "0.5 s books, all windows")
    out["top"] = summarise(main_[main_.liq_ntl >= top_thr], "0.5 s books, top liq-notional decile")
    out["kill2"] = kill2(out["all"], out["top"])
    okc = wc.window_id.isin(main_.window_id)
    wc_ = wc[okc]
    out["coarse_all"] = summarise(wc_, "5 s coarsened, all windows")
    out["coarse_top"] = summarise(wc_[wc_.liq_ntl >= top_thr], "5 s coarsened, top decile")
    out["coarse_kill2"] = kill2(out["coarse_all"], out["coarse_top"])
    out["slow_books"] = summarise(wm[~ok], "windows with >2 s book gaps (reported apart)") if (~ok).sum() > 50 else None
    main_ = main_.copy()
    main_["decile"] = pd.qcut(main_.liq_ntl, 10, labels=False, duplicates="drop")
    out["deciles"] = [dict(decile=int(dd), liq_ntl_lo=float(g.liq_ntl.min()), liq_ntl_hi=float(g.liq_ntl.max()),
                           windows=len(g), clusters=int(g.cluster.nunique()),
                           **{f"rev{h}_p50": float(g[f"rev{h}"].median()) for h in H},
                           cost10k_rt_p50=float(g.cost10k_rt.median()),
                           pre_move_p50=float(g.pre_move_bps.median()), push_p50=float(g.push_to_entry_bps.median()),
                           depth_min_ratio_p50=float(g.depth_min_ratio_60s.median()),
                           refill_s_p50=float(g.refill_s.median()), spread_max30_p50=float(g.spread_max30.median()),
                           spread_base_p50=float(g.spread_base.median()),
                           rev60_vol_p50=float(g.rev60_vol.median()),
                           disloc_peak_p50=float(g.disloc_peak_bps.median()) if g.disloc_peak_bps.notna().any() else None)
                      for dd, g in main_.groupby("decile")]
    out["by_coin"] = {c: summarise(g, c) for c, g in main_.groupby("coin")}
    out["dislocation"] = dict(windows=int(main_.disloc_peak_bps.notna().sum()),
                              peak_p50=float(main_.disloc_peak_bps.median()),
                              peak_p90=float(main_.disloc_peak_bps.quantile(.9)),
                              peak_s_p50=float(main_.disloc_peak_s.median()),
                              back_s_p50=float(main_.disloc_back_s.median()),
                              never_back_share=float(main_.disloc_back_s.isna().mean()))
    json.dump(out, open(HERE / "step2.json", "w"), indent=1, default=float)
    print(json.dumps(out, indent=1, default=float)[:6000])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["box", "local"], default="local")
    ap.add_argument("--books", default="books"); ap.add_argument("--windows", default="windows.parquet")
    ap.add_argument("--out", default=".")
    a = ap.parse_args()
    box_stage(a.books, a.windows, a.out) if a.stage == "box" else main()
