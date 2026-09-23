"""p07b universe: p04's rule (research/p04_multiasset/universe.py) with its dates
moved to one month before the p07 window. Uses NO returns: only listing dates
and 2020-09 quote volume.

1. Every USD-M symbol archived on data.binance.vision; perpetuals only.
2. Eligible: a monthly 5m kline file exists for 2020-08.
3. Rank by total quote volume over 2020-09 (monthly 5m file, sha256-checked;
   the sha256 of every ranking file is written to universe.json).
4. Exclude stable-vs-stable; one contract per underlying; top 15; BTCUSDT in it.
5. Delisting: the last bar with trade count > 0 in the 2020-01 -> 2022-07 5m
   klines (run after the download; see selection.py).

Ranking files go to data/raw/universe_2020-09/ (gitignored).
Writes universe.json and universe_ranking.csv.

Run from the repo root:  PYTHONPATH=. python research/p07b_pit_universe/universe.py
"""
import hashlib
import importlib.util
import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from harness.data import load_binance_klines

_spec = importlib.util.spec_from_file_location("p04_universe", "research/p04_multiasset/universe.py")
p04 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p04)

OUT = Path(__file__).parent
RAW = Path("data/raw/universe_2020-09")
ELIGIBLE_MONTH, RANK_MONTH = "2020-08", "2020-09"


def rank_volume(sym):
    q = urllib.parse.quote(sym)
    if not p04.exists(f"{p04.KL}/{q}/5m/{q}-5m-{ELIGIBLE_MONTH}.zip"):
        return {"symbol": sym, f"listed_by_{ELIGIBLE_MONTH}": False}
    dest = RAW / f"{sym}-5m-{RANK_MONTH}.zip"
    u = f"{p04.KL}/{q}/5m/{q}-5m-{RANK_MONTH}.zip"
    want = urllib.request.urlopen(u + ".CHECKSUM", timeout=60).read().split()[0].decode()
    if not dest.exists():
        data = urllib.request.urlopen(u, timeout=120).read()
        assert hashlib.sha256(data).hexdigest() == want, sym
        dest.write_bytes(data)
    assert hashlib.sha256(dest.read_bytes()).hexdigest() == want, sym
    b = load_binance_klines(str(dest))
    return {"symbol": sym, f"listed_by_{ELIGIBLE_MONTH}": True, f"quote_volume_{RANK_MONTH}": float(b["quote_volume"].sum()),
            f"bars_{RANK_MONTH}": len(b), "sha256": want}


if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    all_syms = p04.list_symbols()
    perps = [s for s in all_syms if "_" not in s]
    with ThreadPoolExecutor(16) as ex:
        rows = list(ex.map(rank_volume, perps))
    df = pd.DataFrame(rows)
    df = df[df[f"listed_by_{ELIGIBLE_MONTH}"]].sort_values(f"quote_volume_{RANK_MONTH}", ascending=False).reset_index(drop=True)
    df["vol_rank"] = df.index + 1
    df[["base", "quote"]] = [p04.split_symbol(s) for s in df["symbol"]]
    df["status"] = ""
    seen, chosen = set(), []
    for i, r in df.iterrows():
        if r["base"] in p04.STABLES and r["quote"] in p04.STABLES:
            df.loc[i, "status"] = "excluded: stable-vs-stable"
        elif r["base"] in seen:
            df.loc[i, "status"] = "excluded: duplicate underlying"
        elif len(chosen) < p04.N:
            chosen.append(r["symbol"])
            df.loc[i, "status"] = "IN"
        seen.add(r["base"])
    assert "BTCUSDT" in chosen
    df.to_csv(OUT / "universe_ranking.csv", index=False)
    out = {"rule": "p04 universe.py, eligible = 5m file for 2020-08, ranked on 2020-09 quote volume",
           "n_archived_um_symbols": len(all_syms), "n_perps": len(perps), f"n_listed_by_{ELIGIBLE_MONTH}": len(df),
           "universe": chosen,
           "ranking_file_sha256": {s: df.set_index("symbol").loc[s, "sha256"] for s in df["symbol"]}}
    (OUT / "universe.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "ranking_file_sha256"}, indent=1))
    print(df.head(25).drop(columns="sha256").to_string())
