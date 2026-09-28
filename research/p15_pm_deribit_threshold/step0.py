"""p15 step 0b/0c/0e/0f (PLAN.md). No Polymarket price and no gap is read here.

0b  settlement: parse each market's own rule text (Gamma description) into
    (fixing time T in UTC, source, comparison), rebuild the outcome from Binance BTCUSDT 1m klines,
    compare with Gamma's resolved outcome. KILL A: agreement < 99.5% where |S_T/K - 1| > 1 bp.
0c  underlying: Deribit index (option-trade index_price within +-60 s of T) vs Binance close at T.
0e  power: distinct dev fixing dates with >= 1 taker-sell-YES fill in a Step-2 entry window.
    Counts only. KILL B: < 100.
0f  split: common span of fixing dates -> dev first 75% / holdout last 25%; writes split.json.

  python research/p15_pm_deribit_threshold/step0.py rules      # 0b parse + rebuild + agreement
  python research/p15_pm_deribit_threshold/step0.py basis      # 0c
  python research/p15_pm_deribit_threshold/step0.py split      # 0f (writes split.json once)
  python research/p15_pm_deribit_threshold/step0.py power      # 0e (after the split)
"""
import glob
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.data import load_binance_klines  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from common import DIR, HERE, SPLIT, in_scope_markets, load_fills, split  # noqa: E402

ET = "America/New_York"
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                      "nov", "dec"], 1)}
DERIBIT = Path("data/collector/p11/deribit_opt")


# ---------------------------------------------------------------- 0b: rule text -> (T, comparison)
CANDLE = re.compile(r"Binance 1 minute candle for (BTC/?USDT)\s+(.*?)\s+in the ET timezone", re.I)
IN_TITLE = re.compile(r"Binance 1 minute candle for (BTC/?USDT) on the time and date specified in the title", re.I)
TIME_ONLY = re.compile(r"^(\d{1,2}):(\d{2})$")
DATE_TIME = re.compile(r"^(\d{1,2})\s+([A-Za-z]{3})[a-z]*\s+'?(\d{2,4})\s+(\d{1,2}):(\d{2})$")
TITLED = re.compile(r"^titled\s+(\d{4})/(\d{2})/(\d{2})\s+(\d{1,2}):(\d{2})$")
Q_DATE = re.compile(r"\bon\s+([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2})\b")
Q_TIME = re.compile(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(AM|PM)\s*ET\b", re.I)


def _date_from_question(question, anchor):
    """(year, month, day) from 'on <Month> <day>' in the title. Titles carry no year: take the first
    such date on or after the market's creation (anchor = created_at; end_date is sometimes
    overwritten months later, which put 2025 markets into 2026 in the first run)."""
    q = Q_DATE.search(question or "")
    if not q or q[1][:3].lower() not in MONTHS:
        return None
    mon, day = MONTHS[q[1][:3].lower()], int(q[2])
    a = pd.Timestamp(anchor).tz_convert(ET).normalize() - pd.Timedelta(days=1)
    cands = [pd.Timestamp(year=y, month=mon, day=day, tz=ET) for y in (a.year, a.year + 1)]
    best = min(c for c in cands if c >= a)
    return best.year, best.month, best.day


def parse_fixing(desc, end_date, question=None, created_at=None):
    """Fixing time T (UTC) of a Binance BTC/USDT 1-minute candle from the market's own rule text.
    Phrasings handled (step 0b inventory of 49 templates):
      '... candle for BTCUSDT 13 Dec '24 12:00 in the ET timezone'            date+time in the rule
      '... candle for BTC/USDT titled 2023/04/12 12:00 in the ET timezone'    date+time in the rule
      '... candle for BTC/USDT 12:00 in the ET timezone ... date specified in the title'
                                                                              time in rule, date in title
      '... candle for BTC/USDT on the time and date specified in the title'  both in title ('at 4PM ET')
    Anything else (Coinbase, CoinMarketCap, unparsed) -> (NaT, None): out of scope, reported.
    The candle is the one OPENING at T (Binance labels candles by open time)."""
    desc = desc if isinstance(desc, str) else ""
    local = None
    if m := CANDLE.search(desc):
        sym, when = m[1].replace("/", "").upper(), m[2].strip().rstrip(",")
        if d := DATE_TIME.match(when):
            day, mon, yr, hh, mm = int(d[1]), MONTHS.get(d[2][:3].lower()), int(d[3]), int(d[4]), int(d[5])
            local = pd.Timestamp(year=yr + 2000 if yr < 100 else yr, month=mon, day=day, hour=hh, minute=mm)
        elif d := TITLED.match(when):
            local = pd.Timestamp(year=int(d[1]), month=int(d[2]), day=int(d[3]), hour=int(d[4]), minute=int(d[5]))
        elif t := TIME_ONLY.match(when):
            ymd = _date_from_question(question, created_at if created_at is not None else end_date) if question else None
            if ymd is None:
                e = pd.Timestamp(end_date).tz_convert(ET)
                ymd = (e.year, e.month, e.day)
            local = pd.Timestamp(year=ymd[0], month=ymd[1], day=ymd[2], hour=int(t[1]), minute=int(t[2]))
    elif m := IN_TITLE.search(desc):
        sym = m[1].replace("/", "").upper()
        ymd, tm = (_date_from_question(question, created_at if created_at is not None else end_date),
                   Q_TIME.search(question or ""))
        if ymd and tm:
            hh = int(tm[1]) % 12 + (12 if tm[3].upper() == "PM" else 0)
            local = pd.Timestamp(year=ymd[0], month=ymd[1], day=ymd[2], hour=hh, minute=int(tm[2] or 0))
    if local is None:
        return pd.NaT, None
    return local.tz_localize(ET).tz_convert("UTC"), sym


def binance_1m():
    k = load_binance_klines("data/raw/spot/BTCUSDT-1m-*.zip")      # index = bar close edge
    return k["close"]


def rebuild(inv, close):
    """Outcome from the candle that OPENS at T (its close is stamped T + 1 min in our index).
    Tie conventions from the rule texts: strike family 'above' = 'higher than' / '.01 or higher' -> S > K;
    range family brackets resolve an exact boundary to the HIGHER bracket -> 'greater than' S >= K,
    'less than' S < K, 'between' K_lo <= S < K_hi. (Closes are in cents, so exact ties are rare.)"""
    s = close.reindex(inv.T_utc + pd.Timedelta(minutes=1)).to_numpy()
    above = np.where(inv.family == "range", s >= inv.k_low, s > inv.k_low)
    yes = np.where(inv.kind == "above", above,
                   np.where(inv.kind == "below", s < inv.k_high, (s >= inv.k_low) & (s < inv.k_high)))
    gap = np.where(inv.kind == "above", s / inv.k_low - 1,
                   np.where(inv.kind == "below", s / inv.k_high - 1,
                            np.minimum(np.abs(s / inv.k_low - 1), np.abs(s / inv.k_high - 1))))
    return pd.DataFrame({"S_T": s, "yes_rebuilt": np.where(np.isnan(s), np.nan, yes.astype(float)),
                         "gap_bp": np.abs(gap) * 1e4}, index=inv.index)


def gamma_outcome(g):
    """1 = first outcome ('Yes') won, 0 = second won, NaN = unresolved / not 1-0."""
    def one(r):
        try:
            outs, prices = json.loads(r.outcomes), [float(x) for x in json.loads(r.outcomePrices)]
        except (TypeError, ValueError):
            return np.nan
        if sorted(prices) != [0.0, 1.0] or outs[0].lower() != "yes":
            return np.nan
        return float(prices[0] == 1.0)
    return g.apply(one, axis=1)


def cmd_rules():
    g = pd.read_parquet(DIR / "gamma_markets.parquet")
    g["id"] = g["id"].astype(str)
    inv = pd.read_parquet(DIR / "inventory.parquet")          # not in_scope_markets(): no rules join yet
    inv = inv[inv.family.isin(["strike", "range"])].copy()
    inv["id"] = inv.id.astype(str)
    g["description"] = g.description.where(g.description.notna() & (g.description.astype(str).str.len() > 0),
                                           g.ev_description)            # empty market text -> event text
    inv = inv.merge(g[["id", "description", "outcomes", "outcomePrices", "umaResolutionStatus", "closed",
                       "question"]].rename(columns={"question": "g_question", "closed": "g_closed"}),
                    on="id", how="left")
    print(f"inventory {len(inv)}, with Gamma row {inv.description.notna().sum()}")
    fx = inv.apply(lambda r: parse_fixing(r.description, r.end_date, r.question, r.created_at), axis=1, result_type="expand")
    inv["T_utc"], inv["symbol"] = fx[0], fx[1]
    # Ex-ante ambiguity (metadata only): a '12AM ET' title whose end_date is not T can mean midnight at
    # the start or at the end of the named day; one event (2025-08-29) was resolved at end_date.
    amb = inv.question.str.contains(r"12\s*AM ET", regex=True) & inv.T_utc.notna() & (inv.T_utc != inv.end_date)
    print(f"ambiguous 12AM fixing (excluded): {int(amb.sum())} markets")
    inv.loc[amb, "T_utc"] = pd.NaT
    src = inv.description.fillna("").str.extract(r"resolve.*?(Binance|Coinbase|oinmarketcap|oingecko)",
                                                 flags=re.I)[0].fillna("none")
    print("source:", src.value_counts().to_dict(), "| unparsed Binance rules:",
          int(((src == "Binance") & inv.T_utc.isna()).sum()))
    dd = (inv.T_utc.dt.tz_convert(ET).dt.date != inv.end_date.dt.tz_convert(ET).dt.date) & inv.T_utc.notna()
    print(f"T's ET date != end_date's ET date: {int(dd.sum())} markets "
          f"(T - end_date h: {((inv.T_utc - inv.end_date)[dd].dt.total_seconds() / 3600).round(1).value_counts().head(6).to_dict()})")
    # rule templates: numbers, dates and times masked, so one line per distinct phrasing
    tmpl = inv.description.fillna("<none>").str.replace(r"\d[\d,\.]*", "#", regex=True).str.slice(0, 260)
    inv["template"] = tmpl.factorize()[0]
    print(f"{inv.template.nunique()} rule templates; T parsed for {inv.T_utc.notna().sum()}")
    for t, grp in inv.groupby("template"):
        print(f"--- template {t}: {len(grp)} markets, e.g. {grp.question.iloc[0]}")
        print("   ", str(grp.description.iloc[0])[:300].replace("\n", " "))
    inv["yes_gamma"] = gamma_outcome(inv)
    close = binance_1m()
    inv = inv.join(rebuild(inv, close))
    ok = inv.yes_gamma.notna() & inv.yes_rebuilt.notna()
    agree = inv.yes_gamma == inv.yes_rebuilt
    far = ok & (inv.gap_bp > 1)
    print(f"\nresolved 1-0 in Gamma: {inv.yes_gamma.notna().sum()}; rebuildable: {ok.sum()}")
    print(f"agreement all: {agree[ok].mean():.4%} ({(~agree[ok]).sum()} misses)")
    print(f"agreement |gap| > 1 bp (KILL A needs >= 99.5%): {agree[far].mean():.4%} "
          f"({(~agree[far]).sum()} misses of {far.sum()})")
    bins = pd.cut(inv.gap_bp, [0, 0.1, 1, 3, 10, 30, np.inf])
    print(pd.DataFrame({"n": ok.groupby(bins).sum(), "agree": agree[ok].groupby(bins[ok]).mean()}).to_string())
    print("\nby family:", agree[ok].groupby(inv.family[ok]).agg(["size", "mean"]).to_dict())
    print("T vs end_date (h):", ((inv.T_utc - inv.end_date).dt.total_seconds() / 3600).round(2).value_counts()
          .head(8).to_dict())
    misses = inv[ok & ~agree]
    misses[["id", "question", "kind", "k_low", "k_high", "T_utc", "end_date", "S_T", "gap_bp", "yes_gamma",
            "yes_rebuilt", "umaResolutionStatus", "template"]].to_csv(HERE / "step0_misses.csv", index=False)
    inv[["id", "T_utc", "symbol", "template", "yes_gamma", "yes_rebuilt", "gap_bp", "umaResolutionStatus"]] \
        .to_parquet(DIR / "rules.parquet")
    res = {"n_inventory": int(len(inv)), "n_gamma": int(inv.description.notna().sum()),
           "n_T_parsed": int(inv.T_utc.notna().sum()), "n_templates": int(inv.template.nunique()),
           "n_resolved_1_0": int(inv.yes_gamma.notna().sum()), "n_rebuildable": int(ok.sum()),
           "agree_all": float(agree[ok].mean()), "agree_gt1bp": float(agree[far].mean()),
           "n_gt1bp": int(far.sum()), "misses_gt1bp": int((~agree[far]).sum()),
           "kill_A": bool(agree[far].mean() < 0.995)}
    (HERE / "step0_rules.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


# ---------------------------------------------------------------- 0c: Deribit index vs Binance at T
def deribit_index_at(times, half_window=pd.Timedelta(seconds=60)):
    out = {}
    for day, ts in pd.Series(times).groupby(pd.Series(times).dt.date):
        f = DERIBIT / f"opt_{day}.parquet"
        if not f.exists():
            continue
        d = pd.read_parquet(f, columns=["timestamp", "index_price"])
        t = pd.to_datetime(d.timestamp, unit="ms", utc=True)
        for T in ts:
            sel = (t >= T - half_window) & (t <= T + half_window)
            if sel.any():
                out[T] = float(d.index_price[sel].median())
    return pd.Series(out)


def cmd_basis():
    r = pd.read_parquet(DIR / "rules.parquet")
    T = pd.Series(r.T_utc.dropna().unique()).sort_values()
    idx = deribit_index_at(T)
    close = binance_1m()
    b = (idx / close.reindex(idx.index + pd.Timedelta(minutes=1)).to_numpy() - 1) * 1e4
    b = b.dropna()
    print(f"fixing times {len(T)}, with Deribit index +-60 s {len(idx)}, basis rows {len(b)}")
    q = b.quantile([0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]).round(2)
    print("Deribit index / Binance BTCUSDT - 1 at T, bps:", q.to_dict())
    print("by year median:", b.groupby(b.index.year).median().round(2).to_dict())
    b.rename("basis_bp").to_frame().to_parquet(DIR / "basis_at_T.parquet")
    (HERE / "step0_basis.json").write_text(json.dumps({"n": int(len(b)), "quantiles_bp": q.to_dict(),
                                                       "by_year_median_bp": b.groupby(b.index.year).median()
                                                       .round(3).to_dict()}, indent=1, default=str))


# ---------------------------------------------------------------- 0f: split
def cmd_split():
    """PLAN 0f + amendment 1: common span of fixing times with a parsed Binance rule and a Gamma 1-0
    outcome, inside Deribit coverage on disk; dev = first 75% of that calendar span. Fixing dates only."""
    assert not SPLIT.exists(), "split.json already fixed; never rewritten"
    r = in_scope_markets(dev_only=False)
    r = r[r.T_utc.notna() & r.yes_gamma.notna()]
    der_days = sorted(p.stem[4:] for p in DERIBIT.glob("opt_*.parquet"))
    der_first = pd.Timestamp(der_days[0], tz="UTC")
    der_last = pd.Timestamp(der_days[-1], tz="UTC") + pd.Timedelta(days=1)
    T = r.T_utc[(r.T_utc >= der_first) & (r.T_utc < der_last)]
    start, end = T.min().floor("D"), T.max().floor("D") + pd.Timedelta(days=1)
    cut = (start + 0.75 * (end - start)).floor("D")
    s = {"dev_start": str(start), "dev_end": str(cut), "holdout_start": str(cut), "holdout_end": str(end),
         "rule": "fixing times with parsed Binance rule + Gamma 1-0 outcome, inside Deribit trades on disk "
                 "(2022-08-01..2026-08-31); dev = first 75% of the calendar span (PLAN 0f, amendment 1)",
         "n_markets_dev": int(((T >= start) & (T < cut)).sum()), "n_markets_holdout": int((T >= cut).sum()),
         "n_fixing_dates_dev": int(T[T < cut].dt.tz_convert(ET).dt.date.nunique()),
         "n_fixing_dates_holdout": int(T[T >= cut].dt.tz_convert(ET).dt.date.nunique()),
         "n_markets_outside_deribit": int(len(r) - len(T)),
         "fixed_on": str(pd.Timestamp.now(tz="UTC").floor("s"))}
    SPLIT.write_text(json.dumps(s, indent=1))
    print(json.dumps(s, indent=1))


if __name__ == "__main__":
    {"rules": cmd_rules, "basis": cmd_basis, "split": cmd_split}[sys.argv[1]]()
