# Running extract.py on the Tokyo box (arbscan-tokyo, ap-northeast-1)

Why there: the fill archive (`hl-mainnet-node-data`, 290 GB) sits in ap-northeast-1. Same-region S3
reads have no transfer charge, so the full span costs ~10,200 GET requests (< $0.01) instead of ~$33
of internet egress. Only the outputs (~4–5 GB: ticks ~3.6 GB, addresses ~0.6 GB, liquidations tens
of MB) leave AWS, ≈ $0.5 at $0.114/GB.

Measured on the laptop: one hourly file (29 MB lz4, 139 MB JSON, 320k fills) in 0.9 s with orjson.
On the box's 2 vCPUs at `nice 19` beside arbscan, expect ~2–3 s/hour → **~6–8 h for the full
span** with one process (network is not the bottleneck in-region).

## Prerequisites on the box
1. `sudo apt-get install -y lz4 awscli` (or AWS CLI v2) and `pip install pyarrow orjson`.
2. S3 read credentials. The instance has **no IAM role**. Either
   - (preferred) attach a role allowing `s3:GetObject`/`s3:ListBucket` on
     `arn:aws:s3:::hl-mainnet-node-data` and `.../*`, or
   - export the laptop's `yakup-cli` keys in the session only (`export AWS_ACCESS_KEY_ID=… `),
     not written to disk on the box.
3. Disk: outputs ≤ 5 GB; the box has a 40 GB gp3 volume. Nothing is decompressed to disk.

## Run
```
scp research/p13_hl_liquidation_history/extract.py ubuntu@<box>:~/p13/
ssh ubuntu@<box>
cd ~/p13 && nohup nice -n 19 python3 extract.py --days 20250727:20260925 --out out > run.log 2>&1 &
tail -f run.log                       # one line per day: "<day> ok <seconds>s"
```
Resumable: a day whose `manifest/<day>.json` says `ok` is skipped on restart. Hours that fail are
recorded in the manifest with the error (the first and last day are partial by design: 16 and 8
hours). Hours after 2026-09-25 08:00 UTC are outside the fixed span and are ignored in analysis.

## Bring back
```
rsync -av ubuntu@<box>:~/p13/out/ data/hl/p13_fills/      # gitignored (data/ is ignored)
```
Then delete `~/p13/out` on the box.
