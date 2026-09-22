"""Measured trading costs: spreads, a conservative maker-fill simulator, and a
per-asset, per-month cost table that the backtesters can read.

Market background (why this exists):
  * A TAKER pays the fee plus half the bid-ask spread (buying at the ask,
    when the backtest marks at the mid/close), plus impact if the order is
    bigger than the size at the best price.
  * A MAKER posts a limit order and earns the half-spread IF it fills, but
    it fills mostly when price trades through it, i.e. when the move is going
    against you (adverse selection). Orders that never fill must eventually
    be completed as taker, after the price may have run away.
  * Tick size sets a floor on the spread: an asset priced at 2.81 with a
    0.001 tick can never quote tighter than 3.6 bps.

All timestamps are UTC. Binance archive times are epoch ms (bookTicker
transaction_time, aggTrades transact_time); `_epoch_to_utc` also accepts us.
A quote "at t" is the last update with time <= t.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .data import _epoch_to_utc

BOOK_COLS = ["update_id", "best_bid_price", "best_bid_qty", "best_ask_price", "best_ask_qty",
             "transaction_time", "event_time"]
AGG_COLS = ["agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id", "transact_time",
            "is_buyer_maker"]


def _read(path, cols, usecols):
    """Archive CSV (or zip) with or without a header row; numeric columns
    parsed as float64 / int64 (is_buyer_maker stays text)."""
    first = pd.read_csv(path, header=None, nrows=1).iloc[0, 0]
    has_header = not str(first).lstrip("-").replace(".", "").isdigit()
    dtypes = {c: (str if c == "is_buyer_maker" else "int64" if c.endswith(("time", "_id")) else "float64")
              for c in usecols}
    return pd.read_csv(path, header=None, names=cols, usecols=usecols, skiprows=1 if has_header else 0,
                       dtype=dtypes, engine="c")


def load_book_ticker(path) -> pd.DataFrame:
    """USD-M bookTicker CSV/zip -> DataFrame(bid, bid_qty, ask, ask_qty) indexed
    by transaction_time (UTC), sorted, duplicates kept in file order."""
    df = _read(path, BOOK_COLS, ["best_bid_price", "best_bid_qty", "best_ask_price", "best_ask_qty",
                                 "transaction_time"])
    out = pd.DataFrame({
        "bid": df["best_bid_price"].astype(float).to_numpy(), "bid_qty": df["best_bid_qty"].astype(float).to_numpy(),
        "ask": df["best_ask_price"].astype(float).to_numpy(), "ask_qty": df["best_ask_qty"].astype(float).to_numpy(),
    }, index=_epoch_to_utc(df["transaction_time"]))
    return out.sort_index(kind="stable")


def load_agg_trades(path) -> pd.DataFrame:
    """USD-M aggTrades CSV/zip -> DataFrame(price, qty, buyer_maker) indexed by
    transact_time (UTC). buyer_maker=True: the aggressor SOLD (hit the bid)."""
    df = _read(path, AGG_COLS, ["price", "quantity", "transact_time", "is_buyer_maker"])
    bm = df["is_buyer_maker"].astype(str).str.lower().map({"true": True, "false": False})
    out = pd.DataFrame({"price": df["price"].astype(float).to_numpy(), "qty": df["quantity"].astype(float).to_numpy(),
                        "buyer_maker": bm.to_numpy(bool)}, index=_epoch_to_utc(df["transact_time"]))
    return out.sort_index(kind="stable")


# ---- quotes -----------------------------------------------------------------

def quote_asof(quotes: pd.DataFrame, times) -> pd.DataFrame:
    """Last quote with time <= t for each t (NaN before the first quote)."""
    times = pd.DatetimeIndex(times)
    i = quotes.index.searchsorted(times, side="right") - 1
    out = quotes.iloc[np.maximum(i, 0)].copy()
    out[i < 0] = np.nan
    out.index = times
    out["mid"] = (out["bid"] + out["ask"]) / 2
    return out


def trade_proxy_quotes(trades: pd.DataFrame) -> pd.DataFrame:
    """Quote proxy from trades alone: bid = price of the last seller-initiated
    trade, ask = price of the last buyer-initiated trade, INCLUDING the trade
    at that timestamp (use quote_asof on the result, or .shift(1), to get the
    proxy prevailing before a trade). Can be stale or crossed in fast markets."""
    p = trades["price"]
    bid = p.where(trades["buyer_maker"]).ffill()
    ask = p.where(~trades["buyer_maker"]).ffill()
    q = pd.DataFrame({"bid": bid.to_numpy(), "ask": ask.to_numpy(), "bid_qty": np.nan, "ask_qty": np.nan},
                     index=trades.index)
    return q[~q.index.duplicated(keep="last")]


def half_spread_bps(q: pd.DataFrame) -> pd.Series:
    mid = (q["bid"] + q["ask"]) / 2
    return (q["ask"] - q["bid"]) / 2 / mid * 1e4


def time_weighted_half_spread(quotes: pd.DataFrame, start, end) -> float:
    """Time-weighted mean quoted half-spread (bps) over [start, end)."""
    q = quotes.loc[(quotes.index >= start) & (quotes.index < end)]
    q = q[~q.index.duplicated(keep="last")]
    if len(q) < 2:
        return np.nan
    t = np.append(q.index.as_unit("ns").asi8, pd.Timestamp(end).value)   # .value is always ns
    dt = np.diff(t).astype(float)
    hs = half_spread_bps(q).to_numpy()
    ok = np.isfinite(hs)
    return float((hs[ok] * dt[ok]).sum() / dt[ok].sum())


def effective_half_spread(trades: pd.DataFrame, quotes: pd.DataFrame | None = None) -> pd.Series:
    """Per-trade effective half-spread (bps) = |price - mid| / mid, with mid the
    quote prevailing strictly BEFORE the trade (bookTicker if given, else the
    trade proxy from earlier trades)."""
    q = trade_proxy_quotes(trades) if quotes is None else quotes
    before = quote_asof(q, trades.index - pd.Timedelta(1, "ms"))
    mid = (before["bid"].to_numpy() + before["ask"].to_numpy()) / 2
    return pd.Series(np.abs(trades["price"].to_numpy() - mid) / mid * 1e4, index=trades.index)


def roll_half_spread(close: pd.Series) -> float:
    """Roll (1984): half-spread = sqrt(-cov(dp_t, dp_t-1)) in bps of price.
    NaN when the autocovariance is positive (the estimator is undefined)."""
    dp = np.log(close).diff().dropna()
    c = np.cov(dp.iloc[1:], dp.iloc[:-1])[0, 1]
    return float(np.sqrt(-c) * 1e4) if c < 0 else np.nan


def corwin_schultz_half_spread(high: pd.Series, low: pd.Series) -> float:
    """Corwin & Schultz (2012) high-low spread estimator, mean over
    consecutive bar pairs with negative estimates set to 0. Returns the
    half-spread in bps."""
    hl = np.log(high / low) ** 2
    beta = hl + hl.shift(-1)
    h2, l2 = pd.concat([high, high.shift(-1)], axis=1).max(1), pd.concat([low, low.shift(-1)], axis=1).min(1)
    gamma = np.log(h2 / l2) ** 2
    k = 3 - 2 * np.sqrt(2)
    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)
    s = 2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha))
    s = s.clip(lower=0).dropna()
    return float(s.mean() / 2 * 1e4)


# ---- maker fill simulation --------------------------------------------------

def simulate_maker(
    posts: pd.DataFrame, quotes: pd.DataFrame, trades: pd.DataFrame, T_minutes=(1, 5, 15, 60),
    markout_minutes=(5, 30, 240), maker_fee_bps=2.0, taker_fee_bps=5.0,
) -> pd.DataFrame:
    """Conservative passive execution, no queue model.

    posts : DataFrame indexed by post time t with column 'side' (+1 buy, -1 sell).
    quotes: quotes used for the limit price, the mid and the taker completion
            (bookTicker, or trade_proxy_quotes(trades)).
    A buy rests at the bid at t and FILLS only if a trade prints STRICTLY below
    it in (t, t+T]; a sell rests at the ask and needs a print strictly above.
    Unfilled after T -> completed as taker at the opposite quote at t+T.

    Per order and T:
      shortfall_T  = side * (exec_price - mid_t) / mid_t  (bps; >0 = worse than
                     the mid the backtest assumes)
      all_in_T     = shortfall_T + maker fee (filled) or taker fee (unfilled)
      filled_T, fill_s_T (seconds to fill)
    Markouts (bps, >0 = the mid moved AGAINST the order):
      mo_post_h    = -side * (mid_{t+h} - mid_t) / mid_t
      mo_fill_T_h  = -side * (mid_{tf+h} - mid_tf) / mid_tf   (filled only)
    """
    t = posts.index
    side = posts["side"].to_numpy(float)
    q0 = quote_asof(quotes, t)
    mid0 = q0["mid"].to_numpy()
    limit = np.where(side > 0, q0["bid"].to_numpy(), q0["ask"].to_numpy())
    tt = trades.index.asi8
    unit = trades.index.unit
    tp = trades["price"].to_numpy()
    t_ns = t.as_unit(unit).asi8
    out = pd.DataFrame({"side": side, "bid": q0["bid"].to_numpy(), "ask": q0["ask"].to_numpy(), "mid": mid0},
                       index=t)
    for h in markout_minutes:
        m = quote_asof(quotes, t + pd.Timedelta(minutes=h))["mid"].to_numpy()
        out[f"mo_post_{h}"] = -side * (m - mid0) / mid0 * 1e4
    for T in T_minutes:
        per_s = {"ns": 10**9, "us": 10**6, "ms": 10**3, "s": 1}[unit]
        dT = T * 60 * per_s
        filled = np.zeros(len(t), bool)
        tf = np.full(len(t), np.iinfo(np.int64).min)
        for k in range(len(t)):
            if not np.isfinite(limit[k]):
                continue
            a = np.searchsorted(tt, t_ns[k], side="right")
            b = np.searchsorted(tt, t_ns[k] + dT, side="right")
            seg = tp[a:b]
            hit = seg < limit[k] if side[k] > 0 else seg > limit[k]
            if hit.any():
                filled[k] = True
                tf[k] = tt[a + int(hit.argmax())]
        qT = quote_asof(quotes, t + pd.Timedelta(minutes=T))
        taker_px = np.where(side > 0, qT["ask"].to_numpy(), qT["bid"].to_numpy())
        px = np.where(filled, limit, taker_px)
        sf = side * (px - mid0) / mid0 * 1e4
        out[f"filled_{T}"] = filled
        out[f"fill_s_{T}"] = np.where(filled, (tf - t_ns) / per_s, np.nan)
        out[f"shortfall_{T}"] = sf
        out[f"all_in_{T}"] = sf + np.where(filled, maker_fee_bps, taker_fee_bps)
        tfi = pd.DatetimeIndex(np.where(filled, tf, t_ns).astype(f"datetime64[{unit}]"), tz="UTC")
        mf = quote_asof(quotes, tfi)["mid"].to_numpy()
        for h in markout_minutes:
            m = quote_asof(quotes, tfi + pd.Timedelta(minutes=h))["mid"].to_numpy()
            out[f"mo_fill_{T}_{h}"] = np.where(filled, -side * (m - mf) / mf * 1e4, np.nan)
    return out


# ---- cost table -> cost model -----------------------------------------------

@dataclass
class TableCostModel:
    """Per-bar cost from a per-(asset, month) table.

    table : DataFrame with columns asset, month ('YYYY-MM') and `column`,
            in bps per unit traded, ALL-IN (fees included).
    per_unit_at(index) -> ndarray of cost per unit turnover for each bar.
    Months not in the table raise, unless `fallback_bps` is given.
    For COSTING only: a monthly value averages days later in that month, so
    never use it as a feature or a trade filter (look-ahead)."""
    table: pd.DataFrame
    asset: str
    column: str = "taker_all_in_bps"
    fallback_bps: float | None = None
    include_funding: bool = True

    def per_unit_at(self, index: pd.DatetimeIndex) -> np.ndarray:
        t = self.table[self.table["asset"] == self.asset].set_index("month")[self.column]
        months = pd.DatetimeIndex(index).tz_convert("UTC").strftime("%Y-%m")
        v = t.reindex(months).to_numpy(dtype=float)
        if np.isnan(v).any():
            if self.fallback_bps is None:
                missing = sorted(set(months[np.isnan(v)]))
                raise KeyError(f"no {self.column} for {self.asset} in months {missing[:5]}...")
            v = np.where(np.isnan(v), self.fallback_bps, v)
        return v / 1e4

    @property
    def per_unit_turnover(self):
        raise TypeError("TableCostModel is time-varying: use per_unit_at(index)")


# ---- building the table -------------------------------------------------------

T_LIST = (1, 5, 15, 60)
COST_TABLE_PATH = "data/bars/costs.parquet"


def overlap_calibration(orders: pd.DataFrame, kind: str = "grid") -> pd.DataFrame:
    """Per asset, on orders simulated with BOTH quote sources (bookTicker days):
    ratio of true to proxy half-spread, and bookTicker minus proxy maker all-in
    cost for each T, on matched orders (same asset, time, side)."""
    o = orders[orders["kind"] == kind]
    key = ["asset", "t", "side"]
    cols = ["hs_bps"] + [f"all_in_{T}" for T in T_LIST]
    bt = o[o["quotes"] == "bookTicker"].set_index(key)[cols]
    px = o[o["quotes"] == "proxy"].set_index(key)[cols]
    m = bt.join(px, lsuffix="_bt", rsuffix="_px", how="inner").dropna()
    g = m.groupby(level="asset")
    out = pd.DataFrame({"n_matched": g.size(), "hs_bt": g["hs_bps_bt"].mean(), "hs_proxy": g["hs_bps_px"].mean()})
    out["hs_ratio_bt_over_proxy"] = out["hs_bt"] / out["hs_proxy"]
    for T in T_LIST:
        out[f"maker_all_in_{T}_bt_minus_proxy"] = g[f"all_in_{T}_bt"].mean() - g[f"all_in_{T}_px"].mean()
    return out


def monthly_cost_table(orders: pd.DataFrame, days: pd.DataFrame, calib: pd.DataFrame | None = None,
                       taker_fee_bps: float = 5.0, kind: str = "grid", calib_tol: float = 0.25) -> pd.DataFrame:
    """Per (asset, month) cost table from simulated orders at `kind` post times.

    bookTicker months use true quotes; other months use the trade proxy. If
    `calib` is given and an asset's proxy half-spread is off by more than
    calib_tol on the overlap, proxy months use proxy x ratio (half-spread) and
    proxy + (bt - proxy) (maker all-in); `method` records what was used.
    taker_all_in_bps = taker fee + half-spread at the post times (top of book,
    no impact beyond it). maker_all_in_bps = the T=5 min simulation.
    The half-spread is floored at tick/2 (a quote cannot be tighter than one
    tick); `days` must carry tick_bps_trades, and method gets "+tick_floor"
    when the floor binds (the proxy calibration was fitted in other months).
    Each monthly value averages days that come AFTER a given bar in that
    month: use it for costing, never as a feature or a trade filter."""
    o = orders[orders["kind"] == kind].copy()
    o["month"] = pd.DatetimeIndex(o["t"]).strftime("%Y-%m")
    tick = days.groupby(["asset", "month"])["tick_bps_trades"].median()
    has_bt = o[o["quotes"] == "bookTicker"].groupby(["asset", "month"]).size().rename("n_bt")
    rows = []
    for (a, mth), g in o.groupby(["asset", "month"]):
        use_bt = (a, mth) in has_bt.index
        src = g[g["quotes"] == ("bookTicker" if use_bt else "proxy")]
        r = {"asset": a, "month": mth, "n_orders": int(len(src)), "hs_proxy_bps": float(g.loc[g["quotes"] == "proxy", "hs_bps"].mean())}
        hs = float(src["hs_bps"].mean())
        adj = {T: 0.0 for T in T_LIST}
        method = "bookTicker" if use_bt else "proxy"
        if not use_bt and calib is not None and a in calib.index:
            ratio = calib.loc[a, "hs_ratio_bt_over_proxy"]
            if np.isfinite(ratio) and abs(ratio - 1) > calib_tol:
                hs *= ratio
                adj = {T: float(calib.loc[a, f"maker_all_in_{T}_bt_minus_proxy"]) for T in T_LIST}
                method = "proxy_calibrated"
        floor = float(tick.get((a, mth), np.nan)) / 2
        if np.isfinite(floor) and hs < floor:
            hs, method = floor, method + "+tick_floor"
        r.update({"method": method, "half_spread_bps": hs, "tick_floor_bps": floor, "taker_all_in_bps": taker_fee_bps + hs})
        for T in T_LIST:
            r[f"maker_all_in_bps_T{T}"] = float(src[f"all_in_{T}"].mean()) + adj[T]
            r[f"fill_rate_T{T}"] = float(src[f"filled_{T}"].mean())
        r["maker_all_in_bps"] = r["maker_all_in_bps_T5"]
        if use_bt and "take_side_depth_usd" in src:
            r["top_depth_usd_median"] = float(src["take_side_depth_usd"].median())
            r["frac_10k_exceeds_top"] = float(src["exceeds_top_10k"].mean())
            r["frac_100k_exceeds_top"] = float(src["exceeds_top_100k"].mean())
        rows.append(r)
    tab = pd.DataFrame(rows)
    d = days.groupby(["asset", "month"]).agg(n_days=("date", "size"), volume_usd_day=("volume_usd", "mean"),
                                             eff_hs_proxy_vw=("eff_hs_proxy_vw", "mean"),
                                             tick_bps=("tick_bps_trades", "median")).reset_index()
    return tab.merge(d, on=["asset", "month"], how="left")


def load_cost_table(path: str = COST_TABLE_PATH) -> pd.DataFrame:
    return pd.read_parquet(path)
