"""p15 step 0a: inventory of Polymarket BTC terminal-threshold markets, from metadata only.

Input: data/collector/p15/markets.parquet (HuggingFace SII-WANGZJ/Polymarket_data, markets table).
No prices or fills are read here. Output: data/collector/p15/inventory.parquet, one row per market
with the parsed payoff (kind in {above, below, between}, strike(s) in USD), family and end_date.

  python research/p15_pm_deribit_threshold/inventory.py
"""
import re
import sys
from pathlib import Path

import pandas as pd

SRC = Path("data/collector/p15/markets.parquet")
OUT = Path("data/collector/p15/inventory.parquet")

NUM = r"\$?\s*([\d][\d,]*(?:\.\d+)?)\s*([kK])?"
EXCLUDE = re.compile(r"up or down|reach|dip|\bhit\b|closer to|flip|ethbtc|market cap|dominance|\betf\b|"
                     r"microstrategy|\bsay\b|announce|all[- ]time high|\bath\b|before", re.I)
IS_BTC = re.compile(r"\bbitcoin\b|\bbtc\b|\$btc", re.I)
ABOVE = re.compile(r"(?:above|greater than|over|higher than)\s+" + NUM, re.I)
BELOW = re.compile(r"(?:below|less than|under|lower than)\s+" + NUM, re.I)
BETWEEN = re.compile(r"between\s+" + NUM + r"\s*(?:and|-|to)\s*" + NUM, re.I)


def usd(num, k):
    x = float(num.replace(",", ""))
    return x * 1000 if k else x


def parse(q):
    """-> (kind, k_low, k_high) or None. 'above': payoff 1{S > k_low}; 'below': 1{S < k_high};
    'between': 1{k_low <= S < k_high}. Tie conventions come from the resolution text (step 0b)."""
    if not IS_BTC.search(q) or EXCLUDE.search(q):
        return None
    if m := BETWEEN.search(q):
        lo, hi = usd(m[1], m[2]), usd(m[3], m[4])
        return ("between", lo, hi) if lo < hi else None
    a, b = ABOVE.search(q), BELOW.search(q)
    if a and not b:
        return "above", usd(a[1], a[2]), float("nan")
    if b and not a:
        return "below", float("nan"), usd(b[1], b[2])
    return None


def family(row):
    """Metadata family. 'hourly_above' = the 'Bitcoin above ___ on <date>, <h> ET?' events created
    ~1.3 h before the fixing (never bracketed by two Deribit expiries: excluded by PLAN step 1)."""
    tau_h = (row.end_date - row.created_at).total_seconds() / 3600
    if re.match(r"^Bitcoin above [\d,\.]+k? on .*\d(AM|PM) ET\?$", row.question) and tau_h < 3:
        return "hourly_above"
    if row.kind == "between" or (row.event_title and re.search(r"price", row.event_title, re.I)):
        return "range"
    return "strike"


def main():
    m = pd.read_parquet(SRC, columns=["id", "question", "slug", "condition_id", "token1", "token2", "answer1",
                                      "answer2", "closed", "outcome_prices", "volume", "event_id", "event_slug",
                                      "event_title", "created_at", "end_date", "neg_risk"])
    m = m[m.question.str.contains(IS_BTC)]
    p = m.question.map(parse)
    m = m[p.notna()].copy()
    m[["kind", "k_low", "k_high"]] = pd.DataFrame(p[p.notna()].tolist(), index=m.index)
    m["family"] = m.apply(family, axis=1)
    # sanity: strikes in a plausible BTC range; anything else is a parse error to inspect, not keep
    bad = ~((m.k_low.isna() | m.k_low.between(1e3, 1e6)) & (m.k_high.isna() | m.k_high.between(1e3, 1e6)))
    if bad.any():
        print(f"dropping {bad.sum()} rows with implausible strikes:", file=sys.stderr)
        print(m.loc[bad, "question"].head(20).to_string(), file=sys.stderr)
    m = m[~bad]
    m["tau_h"] = (m.end_date - m.created_at).dt.total_seconds() / 3600
    m.to_parquet(OUT)
    g = m.groupby("family").agg(markets=("id", "size"), events=("event_id", "nunique"),
                                fix_times=("end_date", "nunique"), fix_dates=("end_date", lambda s: s.dt.date.nunique()),
                                vol_musd=("volume", lambda s: s.sum() / 1e6), vol_med=("volume", "median"),
                                tau_h_med=("tau_h", "median"), first=("end_date", "min"), last=("end_date", "max"))
    print(g.to_string())
    print(pd.crosstab(m.end_date.dt.strftime("%Y-%m"), m.family).to_string())
    print(m.groupby(["family", "kind"]).size().to_string())
    print(m.closed.value_counts().to_dict())


if __name__ == "__main__":
    main()
