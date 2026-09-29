"""p16 step 0 (PLAN.md): costs, coverage, settlement check and the split. No P&L is computed here.

  python research/p16_deribit_vrp/step0.py costs      # effective half-spread of ATM weekly options by month
  python research/p16_deribit_vrp/step0.py coverage   # per Friday: entry smile exists, delivery price exists
  python research/p16_deribit_vrp/step0.py settle     # delivery price vs Deribit index in [07:30, 08:00]
  python research/p16_deribit_vrp/step0.py split      # writes split.json once
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from common import (DERIBIT, DIR, fridays, delivery_prices, deribit_day, entry_smile)  # noqa: E402

SPLIT = HERE / "split.json"


def cmd_costs():
    """Effective half-spread h = median((price - mark) * side) for ATM (|ln K/F| < 5%, F ~ index) options with
    3-8 days to expiry, in BTC -> USD at the trade's index, and as % of mark. By month."""
    rows = []
    for f in sorted(DERIBIT.glob("opt_*.parquet")):
        x = deribit_day(f.stem[4:])
        if x is None or x.empty:
            continue
        tau_d = (x.expiry - x.t).dt.total_seconds() / 86400
        atm = (np.abs(np.log(x.K / x.index_price)) < 0.05) & tau_d.between(3, 8) & (x.mark_price > 0)
        y = x[atm]
        if y.empty:
            continue
        side = np.where(y.direction == "buy", 1.0, -1.0)
        h_btc = (y.price - y.mark_price) * side
        rows.append(pd.DataFrame({"t": y.t, "h_usd": h_btc * y.index_price, "h_pct_mark": h_btc / y.mark_price,
                                  "amount": y.amount}))
    d = pd.concat(rows)
    d["month"] = d.t.dt.strftime("%Y-%m")
    m = d.groupby("month").agg(trades=("h_usd", "size"), h_usd_median=("h_usd", "median"),
                               h_pct_mark_median=("h_pct_mark", "median"),
                               share_negative=("h_usd", lambda s: float((s < 0).mean())))
    m.to_csv(HERE / "step0_costs_by_month.csv")
    print(m.round(4).to_string())
    print("\nall months: h_usd median", round(float(d.h_usd.median()), 2), "| h % of mark median",
          round(float(d.h_pct_mark.median()), 4))
    d[["t", "h_usd", "h_pct_mark"]].to_parquet(DIR / "atm_effective_half_spread.parquet")


def cmd_coverage():
    dp = delivery_prices()
    rows = []
    for fri in fridays():
        expiry = fri + pd.Timedelta(days=7)
        sm, info = entry_smile(fri)
        rows.append({"friday": fri, "entry_smile": sm is not None, "n_strikes": info.get("n_strikes"),
                     "entry_delivery": fri.date() in dp.index, "expiry_delivery": expiry.date() in dp.index})
    c = pd.DataFrame(rows)
    c.to_csv(HERE / "step0_coverage.csv", index=False)
    print(f"Fridays {len(c)}; entry smile {int(c.entry_smile.sum())}; expiry delivery price {int(c.expiry_delivery.sum())}")
    print(c[~c.entry_smile | ~c.expiry_delivery].to_string())


def cmd_settle():
    dp = delivery_prices()
    rng = np.random.default_rng(0)
    fr = fridays()
    pick = [fr[i] for i in rng.choice(len(fr), 20, replace=False)]
    out = []
    for fri in pick:
        x = deribit_day(str(fri.date()))
        w = x[(x.t >= fri - pd.Timedelta(minutes=30)) & (x.t < fri)]
        if w.empty or fri.date() not in dp.index:
            continue
        out.append({"friday": fri.date(), "delivery": dp[fri.date()], "index_mean_0730_0800": float(w.index_price.mean()),
                    "diff_bp": 1e4 * (dp[fri.date()] / w.index_price.mean() - 1)})
    o = pd.DataFrame(out)
    print(o.round(2).to_string())
    med = float(o.diff_bp.abs().median())
    res = {"n": int(len(o)), "median_abs_diff_bp": med, "gate_lt_10bp": med < 10}
    print(json.dumps(res))
    (HERE / "step0_settle.json").write_text(json.dumps(res, indent=1))


def cmd_split():
    assert not SPLIT.exists(), "split.json already fixed; never rewritten"
    fr = fridays()
    start, end = fr[0], fr[-1]
    cut = start + 0.75 * (end - start)
    dev = [f for f in fr if f < cut]
    s = {"dev_start": str(start), "dev_end": str(cut), "holdout_start": str(cut), "holdout_end": str(end),
         "rule": "entry Fridays 08:00 UTC from the first with data to the last whose expiry is inside the data; "
                 "dev = first 75% of the calendar span (PLAN)",
         "n_weeks_dev": len(dev), "n_weeks_holdout": len(fr) - len(dev),
         "fixed_on": str(pd.Timestamp.now(tz="UTC").floor("s"))}
    SPLIT.write_text(json.dumps(s, indent=1))
    print(json.dumps(s, indent=1))


if __name__ == "__main__":
    {"costs": cmd_costs, "coverage": cmd_coverage, "settle": cmd_settle, "split": cmd_split}[sys.argv[1]]()
