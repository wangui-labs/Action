# src/interface/connection.py
"""
Connection — the single MT5 session owner.

    conn = Connection()
    conn._startup()          # initialize + verify terminal + account
    conn.on_tick(fn)         # register per-loop tick callback
    conn.run_loop()          # blocking loop until stop / Ctrl+C
    conn.disconnect()

Nothing else in the project should call mt5.initialize/shutdown.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

import MetaTrader5 as mt5


class MT5ConnectionError(RuntimeError):
    """Raised when MT5 refuses a connection operation."""
    def __init__(self, action: str, code: int, message: str):
        self.action = action
        self.code = code
        self.message = message
        super().__init__(f"{action} failed [{code}]: {message}")


class Connection:
    """Owns the MT5 python bridge. Callbacks fire every loop tick."""

    def __init__(self):
        self._connected: bool = False
        self._ticks: list[Callable[[], None]] = []
        self._loop_sleep_s: float = 0.05    # 20 Hz
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

    # ── tick callbacks + loop ──────────────────────────────────
    def on_tick(self, fn: Callable[[], None]) -> None:
        """Register a callback invoked every loop tick. Order preserved."""
        if fn not in self._ticks:
            self._ticks.append(fn)

    def run_loop(self, sleep_s: Optional[float] = None) -> None:
        """
        Blocking loop. Calls each registered tick callback, then sleeps.
        Stop via KeyboardInterrupt or conn.stop().
        """
        if not self._connected:
            raise MT5ConnectionError("run_loop", -1, "not connected")
        interval = sleep_s if sleep_s is not None else self._loop_sleep_s
        self._stopping = False
        try:
            while not self._stopping:
                for fn in self._ticks:
                    try:
                        fn()
                    except Exception as e:
                        name = getattr(fn, "__name__", repr(fn))
                        print(f"[loop] {name} raised {type(e).__name__}: {e}",
                              flush=True)
                time.sleep(interval)
        finally:
            self._stopping = False

    def stop(self) -> None:
        """Ask run_loop to exit after the current tick."""
        self._stopping = True