# src/logic/bear_bull.py
"""
Per-candle classification + geometry.

    classify(candle)                       → Direction          (pure)
    classify_batch(candles, threshold=4)   → list[BearBull]      (pure per call)
    body_of(candle)                        → (body, range)      (pure, if needed)

BearBull is a complete pure summary of ONE bar:
  - direction / streak / is_one_sided   (directional tier)
  - body, range, ratios, close position  (geometric tier)

Everything in the geometric tier is precomputed — consumers never
recompute abs(close - open). Tier-3 (relation to previous bar) is a
separate pure function, relative_features(prev, curr), because it
needs two bars and does not belong on a single-bar record.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.data_structures.structures import Candle


# ── Direction ────────────────────────────────────────────────
class Direction(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


# ── BearBull ─────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class BearBull:
    """One classified candle. Complete pure summary of one bar."""
    candle: Candle
    direction: Direction
    streak: int
    is_one_sided: bool

    # geometric tier — precomputed at construction
    body: float             # abs(close - open)
    range: float            # high - low
    body_ratio: float       # body / range (0 if range==0)
    close_pos: float        # (close - low) / range (0=low, 1=high)
    upper_wick_ratio: float # (high - max(o,c)) / range
    lower_wick_ratio: float # (min(o,c) - low) / range
    signed_body: float      # +body_ratio (bull), -body_ratio (bear), 0 (neutral)

    # ── passthroughs ─────────────────────────────────────────
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

    @property
    def has_body(self) -> bool:       return self.body_ratio > 0.0

    def describe(self) -> str:
        return (
            f"{self.direction.value:8} candle {self.index:>4} "
            f"({self.symbol} {self.timeframe}, "
            f"{self.ny_time:%Y-%m-%d %H:%M} NY)  "
            f"body={self.body_ratio:.2f}  "
            f"close_pos={self.close_pos:.2f}  "
            f"signed={self.signed_body:+.2f}  "
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
            "body": self.body,
            "range": self.range,
            "body_ratio": self.body_ratio,
            "close_pos": self.close_pos,
            "upper_wick_ratio": self.upper_wick_ratio,
            "lower_wick_ratio": self.lower_wick_ratio,
            "signed_body": self.signed_body,
        }


# ── core pure function ───────────────────────────────────────
def classify(candle: Candle) -> Direction:
    """Pure: bull if close > open, bear if close < open, else neutral."""
    if candle.close > candle.open:
        return Direction.BULLISH
    if candle.close < candle.open:
        return Direction.BEARISH
    return Direction.NEUTRAL


def _geometry(candle: Candle, direction: Direction) -> tuple[
    float, float, float, float, float, float, float
]:
    """Pure: (body, range, body_ratio, close_pos, upper_wick_ratio,
              lower_wick_ratio, signed_body)."""
    body = abs(candle.close - candle.open)
    rng = candle.high - candle.low

    # Degenerate bar (zero range) — avoid division by zero.
    if rng <= 0.0:
        return body, rng, 0.0, 0.5, 0.0, 0.0, 0.0

    body_ratio = body / rng
    close_pos = (candle.close - candle.low) / rng
    upper_wick = candle.high - max(candle.open, candle.close)
    lower_wick = min(candle.open, candle.close) - candle.low
    upper_wick_ratio = upper_wick / rng
    lower_wick_ratio = lower_wick / rng

    sign = (
        +1.0 if direction is Direction.BULLISH
        else -1.0 if direction is Direction.BEARISH
        else 0.0
    )
    signed_body = sign * body_ratio

    return (
        body, rng, body_ratio, close_pos,
        upper_wick_ratio, lower_wick_ratio, signed_body,
    )


# ── batch (the stateless public API) ─────────────────────────
def classify_batch(
    candles: list[Candle],
    one_sided_threshold: int = 4,
) -> list[BearBull]:
    """
    Classify candles in chronological order. Streak is computed within
    the batch only — no state survives the call.
    """
    out: list[BearBull] = []
    last_dir: Optional[Direction] = None
    streak = 0

    for c in candles:
        d = classify(c)
        streak = streak + 1 if d == last_dir else 1
        last_dir = d
        body, rng, br, cp, uwr, lwr, sb = _geometry(c, d)
        out.append(BearBull(
            candle=c,
            direction=d,
            streak=streak,
            is_one_sided=streak >= one_sided_threshold,
            body=body,
            range=rng,
            body_ratio=br,
            close_pos=cp,
            upper_wick_ratio=uwr,
            lower_wick_ratio=lwr,
            signed_body=sb,
        ))
    return out


# ── tier-3: pure relation between two adjacent bars ──────────
@dataclass(frozen=True, slots=True)
class BarRelation:
    """Pure features from (prev, curr). No state, no BearBull fields."""
    direction_flip: bool
    higher_high: bool
    lower_low: bool
    inside_bar: bool
    outside_bar: bool
    body_engulf: bool


def relative_features(prev: BearBull, curr: BearBull) -> BarRelation:
    """Pure: relation between adjacent BearBulls. No state."""
    pc, cc = prev.candle, curr.candle
    return BarRelation(
        direction_flip=prev.direction is not curr.direction,
        higher_high=cc.high > pc.high,
        lower_low=cc.low < pc.low,
        inside_bar=cc.high <= pc.high and cc.low >= pc.low,
        outside_bar=cc.high > pc.high and cc.low < pc.low,
        body_engulf=(
            prev.direction is not curr.direction
            and curr.body > prev.body
        ),
    )


# ── optional thin wrapper (delegates, no retained state) ─────
class BearBullClassifier:
    """
    Optional convenience wrapper. Delegates to classify_batch —
    no state survives classify_many(). classify_one() is provided
    for a single candle with streak=1 (no cross-call memory).
    """

    def __init__(self, one_sided_threshold: int = 4) -> None:
        self.threshold = one_sided_threshold

    def classify_one(self, candle: Candle) -> BearBull:
        # Single candle: streak is 1 by definition (no prior context).
        return classify_batch([candle], self.threshold)[0]

    def classify_many(self, candles: list[Candle]) -> list[BearBull]:
        return classify_batch(candles, self.threshold)