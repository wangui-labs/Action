# src/interface/connection.py
"""
Connection — the single MT5 session owner + tick event dispatcher.

    conn = Connection()
    conn._startup()                       # initialize + verify terminal + account
    conn.watch("XAUUSDm")                 # symbols the loop should track
    conn.on_tick(fn)                      # fn(symbol: str, tick: dict) -> None
    conn.run_loop()                       # blocking; emits on NEW ticks only
    conn.disconnect()

Nothing else in the project should call mt5.initialize/shutdown.

Event semantics
---------------
MT5's Python API has no push feed — the terminal is queried synchronously.
So this loop polls `symbol_info_tick()` cheaply, and only *emits* a tick
event when `tick.time_msc` advances for that symbol. Subscribers therefore
see one event per real tick, not one per loop iteration.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional

import MetaTrader5 as mt5

log = logging.getLogger(__name__)


class MT5ConnectionError(RuntimeError):
    """Raised when MT5 refuses a connection operation."""
    def __init__(self, action: str, code: int, message: str):
        self.action = action
        self.code = code
        self.message = message
        super().__init__(f"{action} failed [{code}]: {message}")


TickCallback = Callable[[str, dict], None]


class Connection:
    """Owns the MT5 python bridge. Emits one event per *new* tick per symbol."""

    def __init__(self):
        self._connected: bool = False
        self._tick_callbacks: list[TickCallback] = []
        self._symbols: set[str] = set()
        self._last_tick_msc: dict[str, int] = {}
        self._loop_sleep_s: float = 0.02       # 50 Hz poll of the cache
        self._stopping: bool = False

    # ── state ──────────────────────────────────────────────────
    @property
    def connected(self) -> bool:
        return self._connected

    # ── lifecycle ──────────────────────────────────────────────
    def _startup(self) -> None:
        """Initialize the MT5 bridge, verify terminal + account, log state."""
        if self._connected:
            return
        if not mt5.initialize():
            code, msg = mt5.last_error()
            raise MT5ConnectionError("initialize", code, msg)

        term = mt5.terminal_info()
        acc  = mt5.account_info()
        if term is None or acc is None:
            code, msg = mt5.last_error()
            mt5.shutdown()
            raise MT5ConnectionError("terminal_info/account_info", code,
                                     msg or "terminal or account unavailable")

        self._connected = True
        print(f"connected  : {term.connected}")
        print(f"account    : {acc.login}")
        print(f"balance    : {acc.balance:.2f} {acc.currency}")
        print(f"trading    : {acc.trade_allowed}")

    def connect(self) -> None:
        """Alias for _startup() — older code paths call connect()."""
        self._startup()

    def disconnect(self) -> None:
        if self._connected:
            mt5.shutdown()
            self._connected = False

    # ── subscription ───────────────────────────────────────────
    def watch(self, *symbols: str) -> None:
        """
        Register symbols the loop should poll for ticks.
        Calling multiple times is additive; safe with no symbols.
        """
        for sym in symbols:
            if sym:
                self._symbols.add(sym)

    def unwatch(self, *symbols: str) -> None:
        for sym in symbols:
            self._symbols.discard(sym)
            self._last_tick_msc.pop(sym, None)

    def on_tick(self, fn: TickCallback) -> None:
        """
        Register a callback invoked once per *new* tick.

        Signature: fn(symbol: str, tick: dict) -> None
        tick = {"bid": float, "ask": float, "time": int, "time_msc": int}
        Callbacks fire in registration order; one raising does not
        block the others.
        """
        if fn not in self._tick_callbacks:
            self._tick_callbacks.append(fn)

    # ── loop ───────────────────────────────────────────────────
    def run_loop(self, sleep_s: Optional[float] = None) -> None:
        """
        Blocking loop. On every iteration, polls watched symbols and
        emits tick events only when time_msc advanced. Stops on
        KeyboardInterrupt or conn.stop().
        """
        if not self._connected:
            raise MT5ConnectionError("run_loop", -1, "not connected")
        interval = sleep_s if sleep_s is not None else self._loop_sleep_s
        self._stopping = False
        try:
            while not self._stopping:
                self._emit_new_ticks()
                time.sleep(interval)
        finally:
            self._stopping = False

    def stop(self) -> None:
        """Ask run_loop to exit after the current tick."""
        self._stopping = True

    # ── internals ──────────────────────────────────────────────
    def _emit_new_ticks(self) -> None:
        for sym in tuple(self._symbols):
            tick = mt5.symbol_info_tick(sym)
            if tick is None:
                continue
            # Dedupe: emit only when time_msc advances.
            if self._last_tick_msc.get(sym) == tick.time_msc:
                continue
            self._last_tick_msc[sym] = tick.time_msc
            payload = {
                "bid": tick.bid,
                "ask": tick.ask,
                "time": int(tick.time),
                "time_msc": int(tick.time_msc),
            }
            for fn in self._tick_callbacks:
                try:
                    fn(sym, payload)
                except Exception:
                    name = getattr(fn, "__name__", repr(fn))
                    log.exception("[loop] tick callback %s failed", name)