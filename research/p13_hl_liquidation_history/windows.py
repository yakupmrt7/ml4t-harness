"""p13 step 2: the event windows (dev only), from step 1's events. Reads no prices.
One window per (60 s cluster across the six coins, coin). See PLAN.md step 2 addendum.
  -> windows.parquet  (window_id, cluster, coin, t0 ms, s, liq_ntl, liq_buy_ntl, liq_sell_ntl, n_events)
"""
import pathlib
import numpy as np, pandas as pd
from events import SPAN, DEV_END, clusters

HERE = pathlib.Path(__file__).parent
ev = pd.read_parquet(HERE / "events.parquet")
ev = ev[ev.method == "market"].sort_values("t0").reset_index(drop=True)
ev["cluster"] = clusters(ev.t0.to_numpy(), 60)
ev["buy"] = np.where(ev.side == "B", ev.ntl, 0.0)
ev["sell"] = np.where(ev.side == "A", ev.ntl, 0.0)
w = (ev.groupby(["cluster", "coin"]).agg(t0=("t0", "min"), liq_ntl=("ntl", "sum"), liq_buy_ntl=("buy", "sum"),
                                         liq_sell_ntl=("sell", "sum"), n_events=("ntl", "size"))
       .reset_index().sort_values(["t0", "coin"]).reset_index(drop=True))
w["s"] = np.sign(w.liq_buy_ntl - w.liq_sell_ntl).astype(int)     # -1: longs liquidated, forced selling
dev_end_ms = int(DEV_END.timestamp() * 1000)
w = w[(w.t0 + 302_000 < dev_end_ms) & (w.s != 0)].reset_index(drop=True)
w["window_id"] = np.arange(len(w))
w.to_parquet(HERE / "windows.parquet")
print(f"dev windows {len(w)} in {w.cluster.nunique()} clusters; by coin:", w.coin.value_counts().to_dict())
print("s=-1 share", (w.s == -1).mean().round(3), "; liq_ntl p50/p90/p99",
      w.liq_ntl.quantile([.5, .9, .99]).round(0).tolist())
