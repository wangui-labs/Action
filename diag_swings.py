# diag_swings.py
from __future__ import annotations

import statistics

from src.interface.connection import Connection
from src.interface.marketwatch import MarketWatch
from src.pipeline.access import bootstrap
from src.analysis.flow_0 import label_bars
from src.analysis.flow_2 import MIN_SWING_PIPS


SYMBOL = "XAUUSDm"


def main() -> None:
    conn = Connection(); conn._startup()
    mw = MarketWatch(conn)
    layer = bootstrap(conn, mw, symbols=[SYMBOL], months=3, depth=500)

    # what MT5 says about this symbol
    info = mw.info(SYMBOL)
    tick = mw.tick(SYMBOL)
    print(f"\n=== {SYMBOL} symbol metadata ===")
    print(f"  digits          : {info.digits}")
    print(f"  point           : {info.point}")
    print(f"  trade_tick_size : {info.trade_tick_size}")
    print(f"  trade_tick_value: {info.trade_tick_value}")
    print(f"  bid             : {tick['bid']:.5f}")
    print(f"  ask             : {tick['ask']:.5f}")
    print(f"  spread (price)  : {tick['ask'] - tick['bid']:.5f}")
    print(f"  spread (points) : {(tick['ask'] - tick['bid']) / info.point:.1f}")

    for tf in ("15m", "4h"):
        bars = layer.window(SYMBOL, tf).bars()
        flow = label_bars(bars, log_events=False)

        # swing ranges in PRICE
        prices = [abs(p.end.price - p.start.price) for p in flow.pairs]
        if not prices:
            print(f"\n=== {tf} ===  no pairs"); continue

        prices.sort()
        n = len(prices)
        def pct(p: float) -> float: return prices[min(n - 1, int(p * n))]

        print(f"\n=== {tf} swing ranges (price units) ===  pairs={n}")
        print(f"  min     : {prices[0]:.5f}")
        print(f"  p10     : {pct(0.10):.5f}")
        print(f"  p25     : {pct(0.25):.5f}")
        print(f"  median  : {pct(0.50):.5f}")
        print(f"  p75     : {pct(0.75):.5f}")
        print(f"  p90     : {pct(0.90):.5f}")
        print(f"  max     : {prices[-1]:.5f}")
        print(f"  mean    : {statistics.mean(prices):.5f}")
        print(f"  stdev   : {statistics.stdev(prices):.5f}")

        # what pip_size would make min_swing_pips = min_swing_pips exactly?
        target = MIN_SWING_PIPS[tf]
        implied_pip = statistics.median(prices) / target
        print(f"\n  current config: min_swing_pips={target}  pip_size=0.1")
        print(f"  → a {target}-pip swing = {target * 0.1:.3f} price units")
        print(f"  → median swing of {statistics.median(prices):.3f} price = "
              f"{statistics.median(prices) / 0.1:.1f} pips  (at pip_size=0.1)")

        # show a few concrete pairs
        print(f"\n  first 10 pairs (price | as pips @ 0.1 | @ 0.01 | @ 1.0):")
        for p in flow.pairs[:10]:
            amp = abs(p.end.price - p.start.price)
            print(f"    {p.direction:4}  {p.start_time:%m-%d %H:%M}→{p.end_time:%H:%M}"
                  f"  {p.start.price:.3f}→{p.end.price:.3f}"
                  f"  |  {amp:>7.3f}  |  {amp/0.1:>7.1f}p  |  {amp/0.01:>8.1f}p  |  {amp/1.0:>6.2f}p")

    conn.disconnect()


if __name__ == "__main__":
    main()