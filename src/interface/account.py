# src/interface/account.py
"""
Account — cached MT5 account state. Stateless w.r.t. Connection.

    acc = Account()                # no conn needed
    acc.refresh(force=True)        # pull once, synchronously
    acc.status_line()              # read

main.py wires it as a tick subscriber:

    conn.on_tick(acc.refresh)         # (sym, tick) ignored; 2 s throttle
    conn.on_tick(acc.print_status)    # (sym, tick) ignored; 5 s throttle

`refresh()` and `print_status()` accept `(symbol, tick)` so they are valid
`Connection.on_tick` handlers with no lambda wrapper. Both are throttled
internally — the event fires per tick, the handler decides cadence.
"""
from __future__ import annotations

import time
from typing import Optional

import MetaTrader5 as mt5


class Account:
    """Cache over mt5.account_info(). No Connection reference."""

    def __init__(
        self,
        refresh_interval_s: float = 2.0,
        print_interval_s: float = 5.0,
    ):
        self._snap: dict = {}
        self._last_refresh_ts: float = 0.0
        self._last_print_ts: float = 0.0
        self._refresh_interval_s: float = refresh_interval_s
        self._print_interval_s: float = print_interval_s
        self._status_started: bool = False
        self.refresh(force=True)

    # ── event handler ──────────────────────────────────────────
    def refresh(
        self,
        symbol: Optional[str] = None,
        tick: Optional[dict] = None,
        force: bool = False,
    ) -> None:
        """
        Pull account_info() at most once every `refresh_interval_s`.

        Accepts (symbol, tick) so it can be registered directly with
        Connection.on_tick. Account equity moves on any held symbol,
        so per-symbol filtering is not useful here — the throttle is.
        """
        now = time.time()
        if not force and (now - self._last_refresh_ts) < self._refresh_interval_s:
            return
        self._last_refresh_ts = now
        try:
            raw = mt5.account_info()
        except Exception as e:
            print(f"[Account] refresh failed: {e}")
            return
        if raw is None:
            return
        d = raw._asdict()
        margin = float(d.get("margin", 0.0))
        equity = float(d.get("equity", 0.0))
        self._snap = {
            "login": d.get("login", 0),
            "balance": float(d.get("balance", 0.0)),
            "equity": equity,
            "margin": margin,
            "margin_free": float(d.get("margin_free", 0.0)),
            "margin_level": (equity / margin * 100.0) if margin > 0 else None,
            "profit": float(d.get("profit", 0.0)),
            "currency": d.get("currency", ""),
            "leverage": int(d.get("leverage", 0)),
            "trade_mode": d.get("trade_mode", 0),
        }

    def print_status(
        self,
        symbol: Optional[str] = None,
        tick: Optional[dict] = None,
    ) -> None:
        """
        Print the status line at most once every `print_interval_s`.
        Accepts (symbol, tick) so it can be wired to Connection.on_tick.
        """
        now = time.time()
        if (now - self._last_print_ts) < self._print_interval_s:
            return
        self._last_print_ts = now
        prefix = "" if self._status_started else "\n"
        self._status_started = True
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {self.status_line()}"
        print(f"{prefix}\r{line:<120}", end="", flush=True)

    # ── reads ──────────────────────────────────────────────────
    def snapshot(self) -> dict:
        return dict(self._snap)

    @property
    def login(self) -> int:
        return self._snap.get("login", 0)

    @property
    def balance(self) -> float:
        return self._snap.get("balance", 0.0)

    @property
    def equity(self) -> float:
        return self._snap.get("equity", 0.0)

    @property
    def margin(self) -> float:
        return self._snap.get("margin", 0.0)

    @property
    def margin_free(self) -> float:
        return self._snap.get("margin_free", 0.0)

    @property
    def margin_level(self) -> Optional[float]:
        return self._snap.get("margin_level")

    @property
    def profit(self) -> float:
        return self._snap.get("profit", 0.0)

    @property
    def currency(self) -> str:
        return self._snap.get("currency", "")

    @property
    def leverage(self) -> int:
        return self._snap.get("leverage", 0)

    def status_line(self) -> str:
        lvl = self.margin_level
        lvl_s = f"{lvl:.1f}" if lvl is not None else "—"
        return (
            f"bal={self.balance:.2f}  "
            f"eq={self.equity:.2f}  "
            f"pnl={self.profit:+.2f}  "
            f"margin={self.margin:.2f}  "
            f"free={self.margin_free:.2f}  "
            f"lvl={lvl_s}  "
            f"{self.currency}"
        )