# src/logic/fractals.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional, Sequence

from src.data_structures.structures import Candle


# ---------------------------------------------------------------------------
# FractalNode — thin pointer to a Candle + detector output only
# ---------------------------------------------------------------------------
SwingType = Literal["swing_high", "swing_low"]


@dataclass(frozen=True)
class FractalNode:
    node_id: str
    candle: Candle
    swing_type: SwingType
    period: int

    @property
    def price(self) -> float:
        return self.candle.high if self.swing_type == "swing_high" else self.candle.low

    @property
    def index(self) -> int:                      return self.candle.index
    @property
    def symbol(self) -> str:                     return self.candle.symbol
    @property
    def timeframe(self) -> str:                  return self.candle.timeframe
    @property
    def open_time(self) -> datetime:             return self.candle.open_time
    @property
    def ny_time(self) -> datetime:               return self.candle.ny_time
    @property
    def utc_time(self) -> datetime:              return self.candle.utc_time
    @property
    def unix_time(self) -> int:                  return self.candle.unix_time
    @property
    def tick_volume(self) -> int:                return self.candle.tick_volume
    @property
    def source_indices(self) -> tuple[int, ...]: return self.candle.source_indices


# ---------------------------------------------------------------------------
# Fractal — detector + node producer
# ---------------------------------------------------------------------------
class Fractal:
    """Period-1 (3-candle) fractal detector. Input candles are already closed."""

    def __init__(self, period: int = 1) -> None:
        self.period = period

    @staticmethod
    def is_high(candles: Sequence[Candle], idx: int) -> bool:
        if idx <= 0 or idx >= len(candles) - 1:
            return False
        return (candles[idx].high > candles[idx - 1].high
                and candles[idx].high > candles[idx + 1].high)

    @staticmethod
    def is_low(candles: Sequence[Candle], idx: int) -> bool:
        if idx <= 0 or idx >= len(candles) - 1:
            return False
        return (candles[idx].low < candles[idx - 1].low
                and candles[idx].low < candles[idx + 1].low)

    @classmethod
    def detect_highs(cls, candles: Sequence[Candle]) -> list[int]:
        return [i for i in range(1, len(candles) - 1) if cls.is_high(candles, i)]

    @classmethod
    def detect_lows(cls, candles: Sequence[Candle]) -> list[int]:
        return [i for i in range(1, len(candles) - 1) if cls.is_low(candles, i)]

    def detect_nodes(self, candles: Sequence[Candle]) -> list[FractalNode]:
        """Return confirmed swing points in chronological order."""
        highs = set(self.detect_highs(candles))
        lows = set(self.detect_lows(candles))

        nodes: list[FractalNode] = []
        for r, c in enumerate(candles):
            if r in highs:
                nodes.append(FractalNode(
                    node_id=f"{c.symbol}_{c.timeframe}_{c.index}_H",
                    candle=c, swing_type="swing_high", period=self.period,
                ))
            elif r in lows:
                nodes.append(FractalNode(
                    node_id=f"{c.symbol}_{c.timeframe}_{c.index}_L",
                    candle=c, swing_type="swing_low", period=self.period,
                ))
        return nodes


# ---------------------------------------------------------------------------
# SwingPair — one completed move: extreme → opposite extreme
# ---------------------------------------------------------------------------
Direction = Literal["up", "down"]


@dataclass(frozen=True)
class SwingPair:
    """One completed swing between two alternating FractalNodes."""
    start: FractalNode              # low or high
    end: FractalNode                # opposite type
    direction: Direction            # "up" = low→high, "down" = high→low

    @property
    def pair_id(self) -> str:
        return (f"{self.start.symbol}_{self.start.timeframe}_"
                f"{self.start.index}_{self.end.index}")

    @property
    def symbol(self) -> str:    return self.start.symbol
    @property
    def timeframe(self) -> str: return self.start.timeframe

    @property
    def start_time(self) -> datetime: return self.start.ny_time
    @property
    def end_time(self) -> datetime:   return self.end.ny_time
    @property
    def time_duration_minutes(self) -> float:
        return (self.end.ny_time - self.start.ny_time).total_seconds() / 60.0

    @property
    def price_amplitude(self) -> float:
        return abs(self.end.price - self.start.price)

    @property
    def velocity(self) -> float:
        t = self.time_duration_minutes
        return self.price_amplitude / t if t > 0 else 0.0

    @property
    def total_volume(self) -> int:
        return self.start.tick_volume + self.end.tick_volume


# ---------------------------------------------------------------------------
# SwingPairer — collapse same-type runs, then pair adjacent opposites
# ---------------------------------------------------------------------------
class SwingPairer:
    """Builds SwingPairs from an ordered (chronological) list of FractalNodes."""

    def __init__(self, nodes: Sequence[FractalNode],
                 avg_volume: Optional[float] = None) -> None:
        self.nodes = list(nodes)
        self.avg_volume = avg_volume
        self.filtered: list[FractalNode] = []
        self.pairs: list[SwingPair] = []

    def filter_extremes(self) -> list[FractalNode]:
        """Collapse consecutive same-type nodes into one extreme."""
        if not self.nodes:
            self.filtered = []
            return self.filtered

        out: list[FractalNode] = []
        i, n = 0, len(self.nodes)
        while i < n:
            cur = self.nodes[i]
            j = i + 1
            while j < n and self.nodes[j].swing_type == cur.swing_type:
                j += 1
            block = self.nodes[i:j]
            best = (min(block, key=lambda x: x.price)
                    if cur.swing_type == "swing_low"
                    else max(block, key=lambda x: x.price))
            out.append(best)
            i = j

        self.filtered = out
        return out

    def pair(self) -> list[SwingPair]:
        """Join adjacent opposite-type extremes into SwingPairs."""
        if not self.filtered:
            self.filter_extremes()

        pairs: list[SwingPair] = []
        for a, b in zip(self.filtered, self.filtered[1:]):
            if a.swing_type == b.swing_type:
                continue
            direction: Direction = "up" if a.swing_type == "swing_low" else "down"
            pairs.append(SwingPair(start=a, end=b, direction=direction))

        self.pairs = pairs
        return pairs

    def build(self) -> list[SwingPair]:
        """filter_extremes → pair, in one call."""
        self.filter_extremes()
        return self.pair()