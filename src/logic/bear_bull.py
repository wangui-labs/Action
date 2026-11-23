# src/logic/bear_bull.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

# Import the Candle — never redefine it.
from src.data_structures.structures import Candle


# -------------------------------------------------
# Direction
# -------------------------------------------------
class Direction(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


# -------------------------------------------------
# BearBull — the classified record for one candle
# -------------------------------------------------
@dataclass(frozen=True, slots=True)
class BearBull:
    """One classified candle. Links back to the original Candle."""
    candle: Candle
    direction: Direction
    streak: int              # consecutive same-direction count, incl. this candle
    is_one_sided: bool       # streak >= threshold

    # --- convenience passthroughs -----------------------------------
    @property
    def index(self) -> int:           return self.candle.index
    @property
    def symbol(self) -> str:          return self.candle.symbol
    @property
    def timeframe(self) -> str:       return self.candle.timeframe
    @property
    def ny_time(self):                return self.candle.ny_time

    @property
    def is_bull(self) -> bool:        return self.direction is Direction.BULLISH
    @property
    def is_bear(self) -> bool:        return self.direction is Direction.BEARISH
    @property
    def is_neutral(self) -> bool:     return self.direction is Direction.NEUTRAL

    def describe(self) -> str:
        return (
            f"{self.direction.value:8} candle {self.index:>4} "
            f"({self.symbol} {self.timeframe}, {self.ny_time:%Y-%m-%d %H:%M} NY)  "
            f"streak={self.streak}  one_sided={self.is_one_sided}"
        )

    def to_record(self) -> dict:
        return {
            "index": self.index,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "ny_time": self.ny_time.isoformat(),
            "direction": self.direction.value,
            "streak": self.streak,
            "is_one_sided": self.is_one_sided,
        }


# -------------------------------------------------
# Classifier + streak tracker
# -------------------------------------------------
def classify(candle: Candle) -> Direction:
    """Pure: bull if close > open, bear if close < open, else neutral."""
    if candle.close > candle.open:
        return Direction.BULLISH
    if candle.close < candle.open:
        return Direction.BEARISH
    return Direction.NEUTRAL


class BearBullClassifier:
    """Stateful: remembers the last direction to count streaks.
    Call `classify_one(candle)` per candle, in chronological order."""

    def __init__(self, one_sided_threshold: int = 4) -> None:
        self.threshold = one_sided_threshold
        self._last_direction: Optional[Direction] = None
        self._streak: int = 0

    def classify_one(self, candle: Candle) -> BearBull:
        direction = classify(candle)

        # Streak: same as last → increment, else reset to 1.
        if direction == self._last_direction:
            self._streak += 1
        else:
            self._streak = 1
            self._last_direction = direction

        return BearBull(
            candle=candle,
            direction=direction,
            streak=self._streak,
            is_one_sided=self._streak >= self.threshold,
        )

    def classify_many(self, candles: list[Candle]) -> list[BearBull]:
        """Convenience for a batch. Resets internal state first."""
        self._last_direction = None
        self._streak = 0
        return [self.classify_one(c) for c in candles]