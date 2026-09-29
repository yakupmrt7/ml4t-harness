"""p14 diagnostic (reported, not a kill of the registered rule, whose PLAN left margin out of the screen):
would the registered rule's positions have been liquidated at 2x per leg? Same margin rule as static.py
(adverse move > 45% from the last Monday reset, Binance daily high/low), applied only on days the rule holds a
position, on the side it holds (pos +1 = short HL / long BN; pos -1 = long HL / short BN).
  python research/p14_hl_funding_carry/rule_survival.py
"""
import json, pathlib, sys
import numpy as np
import pandas as pd
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run as R
import static as S

out = {}
for c in R.COINS:
    b = R.coin_book(c, 1)
    o, bc = S.bn_ohlc(c), S.closes("bn", c)
    ref, hits = None, []
    for d, pos in b.pos.items():
        if pos == 0:
            ref = None
            continue
        if ref is None or d.dayofweek == 0:
            ref = float(bc.loc[:d - pd.Timedelta(days=1)].iloc[-1])
        up, dn = o.high.get(d, np.nan) / ref - 1, 1 - o.low.get(d, np.nan) / ref
        # pos +1: short leg on HL loses on up-moves, long leg on BN loses on down-moves; pos -1 mirrored
        if up > S.LIQ_MOVE or dn > S.LIQ_MOVE:
            hits.append(str(d.date()))
    out[c] = {"days_in_market": int(b.pos.ne(0).sum()), "liquidation_days_2x": hits}
print(json.dumps(out, indent=1))
(HERE / "rule_survival.json").write_text(json.dumps(out, indent=1))
