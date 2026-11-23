# src/pipeline/window.py
"""
Rolling analysis window.

    w = Window(depth=200)
    w.seed(md.get("XAUUSDm", "4h"))
    w.push(new_candle)
"""
from __future__ import annotations

from collections import deque

from src.data_structures.structures import Candle


class Window:
    """Bounded rolling view over a bar stream. Deque handles eviction."""

    def __init__(self, depth: int):
        if depth < 1:
            raise ValueError(f"depth must be >= 1, got {depth}")
        self._depth = depth
        self._buf: deque[Candle] = deque(maxlen=depth)

    @property
    def depth(self) -> int:
        return self._depth

    def __len__(self) -> int:
        return len(self._buf)

    def __iter__(self):
        return iter(self._buf)

    def __getitem__(self, i):
        return self._buf[i]

    def seed(self, bars: list[Candle]) -> None:
        """Replace the buffer with `bars`, keeping the last `depth`."""
        self._buf = deque(bars, maxlen=self._depth)

    def push(self, candle: Candle) -> None:
        """Append a newly-closed bar. Oldest evicts automatically."""
        if not self._buf or self._buf[-1].unix_time < candle.unix_time:
            self._buf.append(candle)

    def bars(self) -> tuple[Candle, ...]:
        """Immutable view — safe to hand to a pure analyzer."""
        return tuple(self._buf)

    @property
    def last(self) -> Candle | None:
        return self._buf[-1] if self._buf else None

    @property
    def first(self) -> Candle | None:
        return self._buf[0] if self._buf else None

    def is_full(self) -> bool:
        return len(self._buf) == self._depth

    def set_depth(self, depth: int) -> None:
        if depth < 1:
            raise ValueError(f"depth must be >= 1, got {depth}")
        if depth == self._depth:
            return
        self._depth = depth
        self._buf = deque(self._buf, maxlen=depth)