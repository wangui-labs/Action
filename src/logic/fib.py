# src/logic/fib.py
"""
Fibonacci plot over a price range.

    fib = FibPlot.from_prices(3590.00, 3620.00)
    fib.equilibrium_price     # 3605.00  (the 0.5 level)
    fib.levels                # {0.0: 3590.00, 0.236: ..., 0.5: 3605.00, ...}
    fib.price_at(0.618)       # 3608.54  (interpolated)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, Sequence


class FibRatios:
    """Common ratio sets. STANDARD is what consolidation.py uses."""
    STANDARD: ClassVar[tuple[float, ...]] = (
        0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0,
    )
    EXTENDED: ClassVar[tuple[float, ...]] = (
        0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0,
        1.272, 1.618, 2.0,
    )
    SHORT: ClassVar[tuple[float, ...]] = (0.0, 0.5, 1.0)


@dataclass(frozen=True)
class FibPlot:
    low: float
    high: float
    ratios: tuple[float, ...] = FibRatios.STANDARD
    levels: dict[float, float] = field(default_factory=dict)

    @classmethod
    def from_prices(
        cls,
        low: float,
        high: float,
        ratios: Sequence[float] = FibRatios.STANDARD,
    ) -> "FibPlot":
        if high < low:
            low, high = high, low
        span = high - low
        r = tuple(ratios)
        levels = {ratio: low + ratio * span for ratio in r}
        return cls(low=low, high=high, ratios=r, levels=levels)

    # ── convenience ─────────────────────────────────────────────
    @property
    def span(self) -> float:
        return self.high - self.low

    @property
    def equilibrium_price(self) -> float:
        """The 0.5 level — the equilibrium of the range."""
        return self.levels.get(0.5, (self.low + self.high) / 2.0)

    def price_at(self, ratio: float) -> float:
        """Interpolate at an arbitrary ratio (not just those in `levels`)."""
        return self.low + ratio * self.span

    def __repr__(self) -> str:
        return (f"FibPlot(low={self.low:.5f}, high={self.high:.5f}, "
                f"eq={self.equilibrium_price:.5f}, ratios={len(self.ratios)})")


__all__ = ["FibPlot", "FibRatios"]