"""p08 post-run checks on the written features:
  1. no zero/negative prices survive in the 1s trade tables (the v4 fix),
  2. how many source stream-hours the collector never wrote.

Run on the VM:  ~/venv/bin/python check_outputs.py
"""
import collections
import re
import subprocess

import pyarrow.compute as pc
import pyarrow.dataset as ds

B = "YOUR-GCS-BUCKET"

for s in ("binance_fut__btcusdt@trade", "binance_spot__btcusdt@trade"):
    d = ds.dataset(f"gs://{B}/features/v1/1s/{s}", format="parquet")
    t = d.to_table(columns=["px_last", "px_min", "n_trades", "n_zero_prints"])
    zl = pc.sum(pc.cast(pc.less_equal(t["px_last"], 0), "int64")).as_py()
    zm = pc.sum(pc.cast(pc.less_equal(t["px_min"], 0), "int64")).as_py()
    zp = pc.sum(t["n_zero_prints"]).as_py()
    print(f"{s}: 1s rows {t.num_rows:,} | px_last<=0 {zl} | px_min<=0 {zm} "
          f"| zero prints excluded {zp:,} | trades {pc.sum(t['n_trades']).as_py():,}")

out = subprocess.run(["gcloud", "storage", "ls", f"gs://{B}/eu-raw_pq/**"],
                     capture_output=True, text=True).stdout
have = set()
for line in out.splitlines():
    m = re.search(r"/eu-raw_pq/(\d{4}-\d{2}-\d{2})/(.+)__(\d{2})\.parquet$", line)
    if m:
        have.add((m.group(1), m.group(2), m.group(3)))

days = sorted({d for d, _, _ in have})
streams = sorted({s for _, s, _ in have})
miss = collections.Counter()
miss_days = collections.defaultdict(set)
for d in days:
    for s in streams:
        for h in range(24):
            if (d, s, f"{h:02d}") not in have:
                miss[s] += 1
                miss_days[s].add(d)

print(f"\nsource objects present: {len(have):,} of {len(days) * len(streams) * 24:,} "
      f"({len(days)} days x {len(streams)} streams x 24 h)")
for s, c in miss.most_common():
    print(f"  missing {c:4d} h  {s:44s} on {len(miss_days[s]):2d} days, e.g. {sorted(miss_days[s])[:3]}")
