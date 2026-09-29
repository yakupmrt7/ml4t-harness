"""p14 screen: cross-venue funding carry HL vs Binance, the single rule of PLAN.md, dev only.

python research/p14_hl_funding_carry/run.py [--delay 1|2]
"""
import argparse, json, pathlib
import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE.parents[1] / "data/hl/funding"
COINS = ["BTC", "ETH", "SOL", "XRP", "DOGE", "LINK", "AVAX", "SUI"]
START, DEV_END = pd.Timestamp("2024-01-01", tz="UTC"), pd.Timestamp("2026-01-12", tz="UTC")
C_ENTER, C_EXIT, WIN = 3e-4, 1e-4, 7
PAIR_SIDE = {"taker": (4.5 + 5 + 2 * 0.5) * 1e-4, "maker": (1.5 + 2) * 1e-4}


def daily_funding(venue, coin):
    f = pd.read_parquet(DATA / f"{venue}_funding_{coin}.parquet")
    return f.set_index("time")["rate"].resample("1D").sum(min_count=1)


def daily_ret(venue, coin):
    d = pd.read_parquet(DATA / f"{venue}_daily_{coin}.parquet").set_index("date")["close"]
    return d.pct_change()


def positions(m):
    pos, out = 0, []
    for x in m.to_numpy():
        if np.isnan(x):
            pos = 0
        elif x > C_ENTER:
            pos = 1
        elif x < -C_ENTER:
            pos = -1
        elif pos == 1 and x <= C_EXIT or pos == -1 and x >= -C_EXIT:
            pos = 0
        out.append(pos)
    return pd.Series(out, index=m.index)


def coin_book(coin, delay):
    s = (daily_funding("hl", coin) - daily_funding("bn", coin)).rename("s")
    basis = -(daily_ret("hl", coin) - daily_ret("bn", coin))
    df = pd.concat([s, basis.rename("basis")], axis=1).loc[START:]
    m = df["s"].rolling(WIN, min_periods=WIN).mean()
    pos = positions(m).shift(delay).fillna(0)          # m through d-1 -> position on d (delay=1)
    trades = pos.diff().abs().fillna(pos.abs())          # pair-sides traded
    out = pd.DataFrame({"pos": pos, "fund": pos * df["s"], "basis": pos * df["basis"].fillna(0),
                        "s": df["s"], "trades": trades})
    for k, c in PAIR_SIDE.items():
        out[f"net_{k}"] = out["fund"] + out["basis"] - trades * c
    return out.loc[:DEV_END - pd.Timedelta("1D")]


def ann(x):
    return {"ann_ret_pct": 365 * x.mean() * 100, "sharpe": np.sqrt(365) * x.mean() / x.std(),
            "years": len(x) / 365}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=int, default=1)
    a = ap.parse_args()
    books, rows = {}, []
    for c in COINS:
        if not (DATA / f"hl_funding_{c}.parquet").exists():
            print("missing", c)
            continue
        b = coin_book(c, a.delay)
        books[c] = b
        s = b["s"].dropna()
        worst5 = (b["basis"].rolling(5).sum()).min()
        rows.append({"coin": c, "days": len(b), "in_mkt": b.pos.ne(0).mean(), "short_hl_share": (b.pos > 0).mean(),
                     "s_mean_bps_day": 1e4 * s.mean(), "s_ar1": s.autocorr(1),
                     "fund_ann%": 365e2 * b.fund.mean(), "basis_ann%": 365e2 * b.basis.mean(),
                     "cost_ann%_taker": -365e2 * (b.trades * PAIR_SIDE["taker"]).mean(),
                     "net_ann%_taker": 365e2 * b.net_taker.mean(), "net_ann%_maker": 365e2 * b.net_maker.mean(),
                     "sharpe_taker": np.sqrt(365) * b.net_taker.mean() / b.net_taker.std(),
                     "round_trips": b.trades.sum() / 2, "worst5d_basis_bps": 1e4 * worst5})
    tab = pd.DataFrame(rows).set_index("coin")
    pd.set_option("display.width", 250)
    print(tab.round(3).to_string())
    port = {k: pd.concat([b[f"net_{k}"] for b in books.values()], axis=1).mean(axis=1) for k in PAIR_SIDE}
    res = {k: ann(v) for k, v in port.items()}
    res["gross_funding_ann%"] = 365e2 * pd.concat([b.fund for b in books.values()], axis=1).mean(axis=1).mean()
    res["basis_ann%"] = 365e2 * pd.concat([b.basis for b in books.values()], axis=1).mean(axis=1).mean()
    res["coins_net_positive_taker"] = int((tab["net_ann%_taker"] > 0).sum())
    res["n_coins"] = len(tab)
    res["median_s_ar1"] = float(tab["s_ar1"].median())
    t = res["taker"]
    res["kill1_econ"] = bool(t["ann_ret_pct"] <= 5)
    res["kill2_robust"] = bool(t["sharpe"] < 1 or res["coins_net_positive_taker"] < len(tab) / 2)
    res["kill3_persist_flag"] = bool(res["median_s_ar1"] < 0.3)
    res["delay"] = a.delay
    # by calendar half-year, to see whether it is one regime
    ph = port["taker"].groupby(port["taker"].index.tz_localize(None).to_period("Q").astype(str)).mean() * 365e2
    res["net_ann%_taker_by_quarter"] = ph.round(2).to_dict()
    # POST HOC diagnostic (not pre-registered, not a decision input): static short-HL/long-BN,
    # one pair entry at the start and one exit at the end of dev.
    st = {}
    for c, b in books.items():
        x = (b["s"].fillna(0) + (-(daily_ret("hl", c) - daily_ret("bn", c))).reindex(b.index).fillna(0))
        x.iloc[0] -= PAIR_SIDE["taker"]; x.iloc[-1] -= PAIR_SIDE["taker"]
        st[c] = x
    stp = pd.concat(st, axis=1)
    res["posthoc_static_short_hl"] = {**ann(stp.mean(axis=1)), "per_coin_ann%": (365e2 * stp.mean()).round(2).to_dict(),
                                      "by_quarter_ann%": (stp.mean(axis=1).groupby(stp.index.tz_localize(None).to_period("Q").astype(str)).mean() * 365e2).round(2).to_dict(),
                                      "worst_5d_bps": float(1e4 * stp.mean(axis=1).rolling(5).sum().min())}
    print(json.dumps(res, indent=1, default=float))
    (HERE / f"results_delay{a.delay}.json").write_text(json.dumps({"portfolio": res, "per_coin": tab.round(4).to_dict("index")},
                                                                   indent=1, default=float))


if __name__ == "__main__":
    main()
