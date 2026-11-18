# src/conditions/condition_0.py
"""
Condition0 — lot-sizing authority.

One job: given a symbol, return its minimum lot size.
That is the only lot we ever send.

Universe: `is_known` accepts a symbol if it's in the static market_watch
set OR in the live provider (e.g. MarketWatch.universe). This lets the
engine scan the whole live universe without the static list going stale.

Public API:
    is_known(symbol)        → bool   (in Market Watch — static or live)
    is_auto_trade(symbol)   → bool   (in auto-trade universe)
    can_trade(symbol)       → bool   (mode AUTO + known + auto-trade)
    size(symbol)            → float  (always the symbol's min lot)
    lot_contract(symbol)    → dict   (just {'min_lot': …})
    check(data)             → bool   (gate shim; delegates to can_trade)
    reason(data)            → str    (human-readable failure reason)
"""
from __future__ import annotations

from typing import Callable, Iterable, Optional

from src.config.auto_trade import auto_trade_config, TradeMode


class Condition0:
    def __init__(
        self,
        market_watch: Optional[Iterable[str]] = None,
        *,
        symbols_provider: Optional[Callable[[], object]] = None,
        name: str = "condition_0",
        enforce_auto_trade: bool = True,
    ):
        self.name = name
        self._static = frozenset(s.upper() for s in (market_watch or []))
        self._provider = symbols_provider
        self.enforce_auto_trade = enforce_auto_trade

    # ── live market watch view ─────────────────────────────────────
    @property
    def market_watch(self) -> frozenset[str]:
        """
        Union of the static set and the live provider (if any).
        Returned as an upper-cased frozenset for membership tests.
        """
        out = set(self._static)
        if self._provider is not None:
            try:
                raw = self._provider()
                if isinstance(raw, dict):
                    out |= {k.upper() for k in raw}
                else:
                    out |= {x.upper() for x in raw}
            except Exception:
                pass
        return frozenset(out)

    # ── universe questions ─────────────────────────────────────────
    def is_known(self, symbol: str) -> bool:
        return (symbol or "").upper() in self.market_watch

    def is_auto_trade(self, symbol: str) -> bool:
        s = (symbol or "").upper()
        if not s:
            return False
        if not self.enforce_auto_trade:
            return True
        return auto_trade_config.is_auto_trade_symbol(s)

    def can_trade(self, symbol: str) -> bool:
        if auto_trade_config.mode != TradeMode.AUTO:
            return False
        return self.is_known(symbol) and self.is_auto_trade(symbol)

    # ── lot contract ───────────────────────────────────────────────
    def lot_contract(self, symbol: str) -> dict:
        """Return {'min_lot'} — the lot size we send for this symbol."""
        s = (symbol or "").upper()
        return {"min_lot": auto_trade_config.get_min_lot(s)}

    # ── sizing ─────────────────────────────────────────────────────
    def size(self, symbol: str) -> float:
        """
        The lot size to send for `symbol`. Always the symbol's minimum.

        Raises KeyError if the symbol isn't in Market Watch (static or live).
        Raises PermissionError if it isn't in the auto-trade universe.
        """
        s = (symbol or "").upper()
        if s not in self.market_watch:
            raise KeyError(
                f"{self.name}: symbol {symbol!r} not in Market Watch "
                f"(static={sorted(self._static)}, live={'yes' if self._provider else 'no'})"
            )
        if self.enforce_auto_trade and not auto_trade_config.is_auto_trade_symbol(s):
            raise PermissionError(
                f"{self.name}: symbol {s!r} is not in the auto-trade universe"
            )
        return auto_trade_config.get_min_lot(s)

    # ── gate interface (called by checks.py) ───────────────────────
    def check(self, data: dict) -> bool:
        """Gate shim. `checks.py` calls this. Delegates to can_trade()."""
        return self.can_trade((data.get("symbol") or ""))

    def reason(self, data: dict) -> str | None:
        """Human-readable reason for a failed check(). Return None if it passes."""
        raw = data.get("symbol") or ""
        s = raw.upper()
        if not s:
            return "no symbol"
        if s not in self.market_watch:
            # show original casing — the input was `UKOILm`, not `UKOILM`
            return f"{raw} not in Market Watch"
        if auto_trade_config.mode != TradeMode.AUTO:
            return "mode is not AUTO"
        if self.enforce_auto_trade and not auto_trade_config.is_auto_trade_symbol(s):
            return f"{raw} not in auto-trade universe"
        return None