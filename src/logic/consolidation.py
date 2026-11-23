# src/logic/consolidation.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence

from src.logic.fractals import Candle, FractalNode
from src.logic.fib import FibPlot, FibRatios


@dataclass(frozen=True)
class ConsolidationRecord:
    node_low: FractalNode
    node_high: FractalNode

    range_pips: float
    fib: FibPlot

    window_start_index: int
    window_end_index: int
    window_start_time: datetime
    window_end_time: datetime
    candles_inside: int
    qualifies: bool

    last_price: float
    ratio: float
    zone: str
    touches_eq: int
    false_moves: int

    exit_direction: Optional[str]
    exit_index: Optional[int]
    exit_time: Optional[datetime]
    exit_close_price: Optional[float]
    exit_held_bars: int

    @property
    def symbol(self) -> str:        return self.node_low.symbol
    @property
    def timeframe(self) -> str:     return self.node_low.timeframe
    @property
    def range_low(self) -> float:   return self.node_low.price
    @property
    def range_high(self) -> float:  return self.node_high.price
    @property
    def equilibrium(self) -> float: return self.fib.equilibrium_price
    @property
    def has_exit(self) -> bool:     return self.exit_direction is not None

    def describe(self) -> str:
        head = (f"CONSOLIDATION {self.symbol} {self.timeframe} "
                f"[{self.range_low:.5f}–{self.range_high:.5f}] "
                f"{self.range_pips:.1f}p qualifies={self.qualifies}")
        win = (f"  window {self.window_start_index}..{self.window_end_index} "
               f"({self.candles_inside} candles)")
        pos = (f"  position {self.zone} ratio={self.ratio:.3f} eq={self.equilibrium:.5f} "
               f"touches={self.touches_eq} false_moves={self.false_moves}")
        ex = "  exit: none" if not self.has_exit else (
            f"  exit: {self.exit_direction} @ {self.exit_index} "
            f"close={self.exit_close_price:.5f} held={self.exit_held_bars}")
        return "\n".join([head, win, pos, ex])

    def to_record(self) -> dict:
        return {
            "symbol": self.symbol, "timeframe": self.timeframe,
            "range_low": self.range_low, "range_high": self.range_high,
            "range_pips": self.range_pips, "qualifies": self.qualifies,
            "window": {
                "start_index": self.window_start_index,
                "end_index": self.window_end_index,
                "candles_inside": self.candles_inside,
            },
            "position": {
                "ratio": self.ratio, "zone": self.zone,
                "equilibrium": self.equilibrium,
                "touches_eq": self.touches_eq, "false_moves": self.false_moves,
            },
            "exit": None if not self.has_exit else {
                "direction": self.exit_direction, "index": self.exit_index,
                "time": self.exit_time.isoformat(timespec="seconds"),
                "close_price": self.exit_close_price, "held_bars": self.exit_held_bars,
            },
        }


class ConsolidationDetector:
    """Two FractalNodes → one ConsolidationRecord. Inclusive candle scan."""

    def __init__(
        self,
        pip_size: float,
        max_range_pips: float | dict[str, float] = 60.0,
        min_candles_inside: int = 8,
        exit_hold_bars: int = 2,
        eq_touch_tolerance_frac: float = 0.02,
        ratios: Sequence[float] = FibRatios.STANDARD,
    ):
        if pip_size <= 0:
            raise ValueError(f"pip_size must be > 0, got {pip_size}")
        self.pip_size = pip_size
        self.max_range_pips = max_range_pips
        self.min_candles_inside = min_candles_inside
        self.exit_hold_bars = exit_hold_bars
        self.eq_touch_tolerance_frac = eq_touch_tolerance_frac
        self.ratios = ratios

    @staticmethod
    def _body_inside(c: Candle, low: float, high: float) -> bool:
        return low <= min(c.open, c.close) and max(c.open, c.close) <= high

    @staticmethod
    def _ordered(n1: FractalNode, n2: FractalNode) -> tuple[FractalNode, FractalNode]:
        if n1.swing_type == n2.swing_type:
            raise ValueError(f"need one swing_high and one swing_low, got "
                             f"{n1.swing_type} & {n2.swing_type}")
        return (n1, n2) if n1.swing_type == "swing_low" else (n2, n1)

    def _max_pips_for(self, symbol: str) -> float:
        if isinstance(self.max_range_pips, dict):
            return float(self.max_range_pips.get(symbol.upper(),
                                                 self.max_range_pips.get("default", 60.0)))
        return float(self.max_range_pips)

    def detect(
        self, candles: Sequence[Candle], n1: FractalNode, n2: FractalNode,
    ) -> ConsolidationRecord:
        low_node, high_node = self._ordered(n1, n2)

        range_low  = low_node.price
        range_high = high_node.price
        span = range_high - range_low
        if span <= 0:
            raise ValueError("range must be positive — nodes are at the same price")
        range_pips = span / self.pip_size

        fib = FibPlot.from_prices(range_low, range_high, ratios=self.ratios)

        between = [c for c in candles if low_node.index <= c.index <= high_node.index]
        inside = [c for c in between if self._body_inside(c, range_low, range_high)]

        if inside:
            window_start_idx = inside[0].index
            window_end_idx   = inside[-1].index
            window_start_t   = inside[0].ny_time
            window_end_t     = inside[-1].ny_time
        else:
            window_start_idx = low_node.index
            window_end_idx   = high_node.index
            window_start_t   = low_node.ny_time
            window_end_t     = high_node.ny_time

        max_pips = self._max_pips_for(low_node.symbol)
        qualifies = (range_pips <= max_pips and len(inside) >= self.min_candles_inside)

        last_price = between[-1].close if between else high_node.price
        ratio = max(0.0, min(1.0, (last_price - range_low) / span))
        tol = self.eq_touch_tolerance_frac * span
        if abs(ratio - 0.5) <= (tol / span if span else 0):
            zone = "equilibrium"
        elif ratio < 0.5:
            zone = "discount"
        else:
            zone = "premium"

        eq_price = fib.equilibrium_price
        touches_eq = sum(1 for c in between
                         if c.low <= eq_price + tol and c.high >= eq_price - tol)

        false_moves = 0
        for i in range(1, len(between)):
            prev, cur = between[i - 1], between[i]
            prev_in = self._body_inside(prev, range_low, range_high)
            cur_in  = self._body_inside(cur,  range_low, range_high)
            if prev_in and not cur_in and i + 1 < len(between):
                if self._body_inside(between[i + 1], range_low, range_high):
                    false_moves += 1

        post = [c for c in candles if c.index > window_end_idx]
        exit_direction = None
        exit_index = None
        exit_time = None
        exit_close = None
        exit_held = 0

        for i, c in enumerate(post):
            if self._body_inside(c, range_low, range_high):
                continue
            direction = "up" if c.close > range_high else "down"
            tail = post[i:i + self.exit_hold_bars]
            if len(tail) < self.exit_hold_bars:
                break
            held = sum(
                1 for n in tail
                if (direction == "up" and n.close > range_high)
                or (direction == "down" and n.close < range_low)
            )
            if held >= self.exit_hold_bars:
                exit_direction = direction
                exit_index = c.index
                exit_time = c.ny_time
                exit_close = c.close
                exit_held = held
            break

        return ConsolidationRecord(
            node_low=low_node, node_high=high_node,
            range_pips=round(range_pips, 1), fib=fib,
            window_start_index=window_start_idx, window_end_index=window_end_idx,
            window_start_time=window_start_t, window_end_time=window_end_t,
            candles_inside=len(inside), qualifies=qualifies,
            last_price=last_price, ratio=ratio, zone=zone,
            touches_eq=touches_eq, false_moves=false_moves,
            exit_direction=exit_direction, exit_index=exit_index,
            exit_time=exit_time, exit_close_price=exit_close, exit_held_bars=exit_held,
        )