# src/conditions/condition_0.py
"""
Condition0 — sizing / symbol universe gate.

Two responsibilities:
  1. size(symbol) → the lot to trade. Today, always the symbol's minimum.
  2. is_known(symbol) → is it in the auto-trade universe?

    from src.config.auto_trade import auto_trade_config

    c0 = Condition0(market_watch=auto_trade_config.auto_trade_symbols)
    c0.size("XAUUSDm")          # 0.01
    c0.is_known("XAUUSDm")      # True
"""
from __future__ import annotations

from typing import Callable, Iterable, Optional

from src.config.auto_trade import auto_trade_config
from src.config.settings import settings


class Condition0:
    """Sizing + symbol universe. No MT5 calls. No MarketWatch needed."""

    def __init__(
        self,
        market_watch: Iterable[str] | None = None,
        symbols_provider: Optional[Callable[[], Iterable[str]]] = None,
        name: str = "condition_0",
    ):
        """
        market_watch     — static allow-list (e.g. auto_trade_config.auto_trade_symbols)
        symbols_provider — callable that returns the *live* tradable universe
                           (e.g. marketwatch.tradable_symbols). Used by is_known.
        """
        self.name = name
        self._static: set[str] = {s.upper() for s in (market_watch or set())}
        self._provider = symbols_provider

    # ── universe ────────────────────────────────────────────────
    def is_known(self, symbol: str) -> bool:
        """True if symbol is in the static list OR the live provider's output."""
        s = symbol.upper()
        if self._static and s in self._static:
            return True
        if self._provider is not None:
            try:
                live = {x.upper() for x in (self._provider() or [])}
            except Exception:
                live = set()
            if live and s in live:
                return True
        return not self._static and self._provider is None  # both empty → allow

    # ── sizing ──────────────────────────────────────────────────
    def size(self, symbol: str) -> float:
        """The lot size to trade. Always the symbol's minimum today."""
        s = symbol.upper()
        if not self.is_known(s):
            raise PermissionError(f"symbol {symbol!r} not in auto-trade universe")
        return auto_trade_config.get_min_lot(s)

    # ── condition interface (for old gate callers, harmless now) ─
    def check(self, data: dict) -> bool:
        symbol = data.get("symbol", "")
        return bool(symbol) and self.is_known(symbol)

    def reason(self, data: dict) -> str:
        symbol = data.get("symbol", "")
        return f"symbol {symbol!r} not in auto-trade universe"


__all__ = ["Condition0"]