#!/usr/bin/env bash
# Pull a SLICE of the collector data for local work. Don't mirror all ~300GB:
# heavy jobs (full order-book feature builds) should run on the GCP box.
# Usage: scripts/sync_collector_sample.sh gs://YOUR_BUCKET/binance/futures/aggTrade/2026-09-0
set -euo pipefail
SRC="${1:?give a gs:// prefix}"
gcloud storage rsync --recursive "$SRC" data/collector/
