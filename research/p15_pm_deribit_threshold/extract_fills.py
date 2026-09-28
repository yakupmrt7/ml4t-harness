"""p15 step 0d: extract on-chain fills of the in-scope markets from the public HuggingFace dataset
SII-WANGZJ/Polymarket_data (trades.parquet, ~37.5 GB, every OrderFilled event of the Polymarket
CLOB exchange contracts v1 and v2, through 2026-07-20).

Reads the remote parquet with HTTP range requests, row group by row group: first the (tiny,
dictionary-encoded) market_id column, then the needed columns only for row groups that hold an
in-scope market. transaction_hash is not read (60% of the bytes); (block_number, log_index) is the
unique key. Output: data/collector/p15/fills/rg=NNNN.parquet (resumable), gitignored.

This writes fills to disk but prints no price statistics. Steps 1-2 load them through
load_fills(), which refuses holdout fixing dates once the split is fixed (step 0f).

  python research/p15_pm_deribit_threshold/extract_fills.py [--workers 8]
"""
import argparse
import io
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

URL = "https://huggingface.co/datasets/SII-WANGZJ/Polymarket_data/resolve/main/trades.parquet"
DIR = Path("data/collector/p15")
OUT = DIR / "fills"
COLS = ["timestamp", "block_number", "log_index", "contract", "market_id", "maker", "taker", "price",
        "usd_amount", "token_amount", "maker_direction", "taker_direction", "nonusdc_side"]


class HTTPRangeFile(io.RawIOBase):
    """Minimal seekable file over HTTP range requests (enough for pyarrow's parquet reader)."""

    def __init__(self, url):
        self.url, self.pos = url, 0
        r = urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60)
        self.size = int(r.headers["Content-Length"])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off)
        return self.pos

    def read(self, n=-1):
        if n < 0:
            n = self.size - self.pos
        if n == 0 or self.pos >= self.size:
            return b""
        end = min(self.pos + n, self.size) - 1
        for attempt in range(6):
            try:
                req = urllib.request.Request(self.url, headers={"Range": f"bytes={self.pos}-{end}"})
                b = urllib.request.urlopen(req, timeout=180).read()
                break
            except Exception:
                if attempt == 5:
                    raise
                time.sleep(2 ** attempt)
        self.pos += len(b)
        return b

    def readinto(self, buf):
        b = self.read(len(buf))
        buf[: len(b)] = b
        return len(b)


def resolved_url():
    return urllib.request.urlopen(urllib.request.Request(URL, method="HEAD"), timeout=60).url


def one(url, i, ids):
    out = OUT / f"rg={i:04d}.parquet"
    if out.exists():
        return i, -1
    pf = pq.ParquetFile(HTTPRangeFile(url))
    mid = pf.read_row_group(i, columns=["market_id"]).column(0)
    mask = pc.is_in(mid, value_set=ids)
    n = pc.sum(mask).as_py() or 0
    if n:
        tb = pf.read_row_group(i, columns=COLS).filter(mask)
    else:
        tb = pa.table({c: pa.array([], type=pf.schema_arrow.field(c).type) for c in COLS})
    tmp = out.with_suffix(".tmp")
    pq.write_table(tb, tmp)
    tmp.rename(out)
    return i, n


def main(workers):
    OUT.mkdir(parents=True, exist_ok=True)
    inv = pd.read_parquet(DIR / "inventory.parquet")
    inv = inv[inv.family.isin(["strike", "range"])]
    ids = pa.array(sorted(inv.id.astype(str).unique()))
    url = resolved_url()
    n_rg = pq.ParquetFile(HTTPRangeFile(url)).metadata.num_row_groups
    print(f"{len(ids)} in-scope markets, {n_rg} row groups", flush=True)
    t0, done, rows = time.time(), 0, 0
    with ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(one, url, i, ids) for i in range(n_rg)]
        for f in as_completed(futs):
            i, n = f.result()
            done += 1
            rows += max(n, 0)
            if done % 25 == 0:
                print(f"{done}/{n_rg} row groups, {rows} rows kept, {time.time() - t0:.0f} s", flush=True)
    print(f"done: {rows} rows kept this run, {time.time() - t0:.0f} s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    main(ap.parse_args().workers)
