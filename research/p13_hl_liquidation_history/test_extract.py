"""python research/p13_hl_liquidation_history/test_extract.py"""
import json, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import pyarrow.parquet as pq
from extract import Day


def fill(coin, side, crossed, tid, px="100.0", sz="2.0", t=1_000, liq=None):
    f = dict(coin=coin, px=px, sz=sz, side=side, time=t, startPosition="5.0", dir="Close Long",
             closedPnl="-1.0", hash="0xh", oid=7, crossed=crossed, fee="0.01", tid=tid)
    if liq: f["liquidation"] = liq
    return f


def test_day():
    L = {"liquidatedUser": "0xL", "markPx": "99.0", "method": "market"}
    blocks = [
        {"block_time": "t", "block_number": 1, "events": [
            ["0xL", fill("BTC", "A", True, 11, liq=L)],       # liquidated taker
            ["0xM", fill("BTC", "B", False, 11, liq=L)],      # its maker, same trade
            ["0xA", fill("ETH", "B", True, 12, t=2_000)],
            ["0xB", fill("ETH", "A", False, 12, t=2_000)],
            ["0xA", fill("DOGE", "B", True, 13, t=3_000)],    # not in COINS: no tick
            ["0xC", fill("DOGE", "A", False, 13, t=3_000)]]},
    ]
    d = Day()
    r = d.feed(json.dumps(b).encode() for b in blocks)
    assert r == dict(lines=1, fills=6, liq_rows=2), r
    assert d.ticks["coin"] == ["BTC", "ETH"]            # one tick per trade, taker side
    assert d.ticks["side"] == ["A", "B"] and d.ticks["liq"] == [True, False]
    assert d.liq["liq_user"] == ["0xL", "0xL"] and d.liq["user"] == ["0xL", "0xM"]
    assert d.addrs["0xA"][:2] == [2, 400.0] and d.addrs["0xA"][2:] == [2_000, 3_000]
    with tempfile.TemporaryDirectory() as tmp:
        d.write(pathlib.Path(tmp), "x")
        assert pq.read_table(pathlib.Path(tmp) / "addrs" / "x.parquet").num_rows == 5


if __name__ == "__main__":
    test_day(); print("ok")
