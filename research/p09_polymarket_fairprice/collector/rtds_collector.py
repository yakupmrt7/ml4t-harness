"""Polymarket live-data (RTDS) collector: the Chainlink prices Polymarket's crypto
up/down markets settle on (topic crypto_prices_chainlink, all symbols, ~1 update/s each).

Runs as its OWN process (poly-rtds.service), separate from poly.collector, so adding it
never restarts or touches the existing feeds. Same raw layout and writer:
    data/raw/{date}/polymarket_rtds/crypto_prices_chainlink/{HH}.ndjson
which compact_raw.py (rglob *.ndjson) and retention_push.py pick up unchanged
-> eu-raw_pq/{date}/polymarket_rtds__crypto_prices_chainlink__{HH}.parquet.
Its operational log goes to feed `polymarket_rtds/_log`, never to collector_log
(which the main collector process appends to).

Run:  .venv/bin/python scripts/rtds_collector.py [--root data/raw]
"""
import argparse
import asyncio
from pathlib import Path

import orjson

from poly.collector.run import REPO_ROOT, load_config
from poly.collector.storage import RawWriter
from poly.collector.ws import run_ws

URL = "wss://ws-live-data.polymarket.com"
# unfiltered 'update' subscription: the filtered {"symbol": ...} form only returns a snapshot
SUBSCRIBE = {"action": "subscribe",
             "subscriptions": [{"topic": "crypto_prices_chainlink", "type": "update", "filters": ""}]}


class RtdsWriter(RawWriter):
    def log(self, source: str, event: str, **kw) -> None:
        print(f"{source}: {event}" + (f" {kw}" if kw else ""), flush=True)
        self.write("polymarket_rtds/_log", {"source": source, "event": event, **kw})


async def on_connect(ws):
    await ws.send(orjson.dumps(SUBSCRIBE).decode())


async def keepalive(ws):
    while True:                                  # RTDS expects an application-level PING every ~5 s
        await asyncio.sleep(5)
        await ws.send("PING")


def feed_for(ev) -> str:
    topic = ev.get("topic") if isinstance(ev, dict) else None
    return f"polymarket_rtds/{topic or 'other'}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None, help="raw root (default: the collector config's storage.root)")
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(load_config(None)["storage"]["root"])
    if not root.is_absolute():
        root = REPO_ROOT / root
    writer = RtdsWriter(root)
    writer.log("polymarket_rtds", "starting", root=str(root), url=URL)
    try:
        asyncio.run(run_ws("polymarket_rtds", URL, writer, feed_for, on_connect=on_connect, keepalive=keepalive))
    finally:
        writer.close()


if __name__ == "__main__":
    main()
