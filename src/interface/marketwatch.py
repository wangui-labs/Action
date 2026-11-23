# src/interface/marketwatch.py
"""
MarketWatch — symbol metadata: info, tick, snapshot, open-status, universe.

    mw = MarketWatch(conn)

    mw.tick("XAUUSDm")         → {"bid": ..., "ask": ..., "time": ...}
    mw.snapshot("XAUUSDm")     → SymbolSnapshot (frozen)
    mw.info("XAUUSDm")         → raw mt5 symbol_info (dict-like)
    mw.tradable_symbols()      → list[str]
    mw.is_open("XAUUSDm")      → bool
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import MetaTrader5 as mt5

from src.interface.connection import Connection


@dataclass(frozen=True)
class SymbolSnapshot:
    symbol: str
    bid: float
    ask: float
    time: int
    digits: int
    point: float
    pip_size: float
    tick_size: float
    tick_value: float
    contract_size: float
    stops_level_points: int
    trade_allowed: bool
    session_open: bool


class MarketWatch:
    """Read-only symbol metadata. Never owns the Connection (main.py does)."""

    def __init__(self, connection: Connection):
        self._conn = connection

    # ── raw passthroughs ───────────────────────────────────────
    def info(self, symbol: str):
        info = mt5.symbol_info(symbol)
        if info is None:
            raise KeyError(f"symbol {symbol!r} not found")
        return info

    def tick(self, symbol: str) -> dict:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise KeyError(f"no tick for {symbol!r}")
        return {"bid": tick.bid, "ask": tick.ask, "time": int(tick.time)}

    def is_open(self, symbol: str) -> bool:
        info = mt5.symbol_info(symbol)
        if info is None:
            return False
        return bool(info.trade_mode != mt5.SYMBOL_TRADE_MODE_DISABLED) and bool(
            getattr(info, "session_deals", 0) >= 0)

    # ── frozen snapshot for downstream consumers ────────────────
    def snapshot(self, symbol: str) -> SymbolSnapshot:
        info = self.info(symbol)
        tick = self.tick(symbol)
        pip_size = 0.1 if info.digits == 2 else 0.0001
        return SymbolSnapshot(
            symbol=symbol,
            bid=tick["bid"],
            ask=tick["ask"],
            time=tick["time"],
            digits=info.digits,
            point=info.point,
            pip_size=pip_size,
            tick_size=info.trade_tick_size,
            tick_value=info.trade_tick_value,
            contract_size=info.trade_contract_size,
            stops_level_points=info.trade_stops_level,
            trade_allowed=bool(info.trade_mode != mt5.SYMBOL_TRADE_MODE_DISABLED),
            session_open=self.is_open(symbol),
        )

    # ── universe ────────────────────────────────────────────────
    def tradable_symbols(self) -> list[str]:
        raw = mt5.symbols_get()
        if not raw:
            return []
        return [
            s.name for s in raw
            if s.visible and s.trade_mode != mt5.SYMBOL_TRADE_MODE_DISABLED
        ]