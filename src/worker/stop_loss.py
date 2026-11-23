# src/worker/stop_loss.py
"""
StopLossWorker — stateless SL manager.

Called from main.py as ONE LINE:

    sl = StopLossWorker.start(mw, stop)

Everything else — Condition0 (sizing), Condition1 (SL math), the poll loop,
the daemon thread — is built and owned inside this file. main.py never sees
Condition0, Condition1, auto_trade_config, or settings.execution.

For manual control instead of a thread:

    c0 = Condition0(market_watch=auto_trade_config.auto_trade_symbols)
    c1 = Condition1(marketwatch=mw, sizing=c0)
    sl = StopLossWorker(condition1=c1)
    sl.process()                       # one pass, no thread

No Connection. No Position. No MarketWatch attribute. The worker reads
mt5.positions_get() directly (same as before) and delegates all math to
Condition1 (which holds its own MarketWatch reference internally).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Literal, Optional

import MetaTrader5 as mt5

from src.config.settings import settings
from src.conditions.condition_1 import Condition1


BreachPolicy = Literal["widen", "close", "skip"]


@dataclass
class ManagedPosition:
    ticket: int
    symbol: str
    side: str
    entry: float
    initial_risk: float
    stage: str = "initial"
    last_sl: float = 0.0
    last_attach_attempt: float = 0.0


class StopLossWorker:
    """Stateless SL manager. main.py calls .start(mw, stop) or .process()."""

    def __init__(
        self,
        condition1: Condition1,
        *,
        auto_magics: Optional[set[int]] = None,
        manage_manual: Optional[bool] = None,
    ):
        self.condition1 = condition1
        self.auto_magics = set(auto_magics if auto_magics is not None
                               else {settings.influence.magic})
        self.manage_manual = (manage_manual if manage_manual is not None
                              else settings.manage_manual)

        # per-ticket bookkeeping (state, not connection state)
        self._managed: dict[int, ManagedPosition] = {}
        self._last_process_time: float = 0.0

    # ═══════════════════════════════════════════════════════════════
    # One-line API — main.py calls exactly this
    # ═══════════════════════════════════════════════════════════════
    @classmethod
    def start(
        cls,
        marketwatch,
        stop_event: threading.Event,
        *,
        auto_magics: Optional[set[int]] = None,
        manage_manual: Optional[bool] = None,
        interval_s: Optional[float] = None,
    ) -> "StopLossWorker":
        """
        Build everything the worker needs, then start it on a daemon thread.

            sl = StopLossWorker.start(mw, stop)

        All defaults come from settings. Override via kwargs if needed.
        Returns the worker so callers can call sl.process() manually.
        """
        # local imports — keep module import cost low, avoid cycles
        from src.conditions.condition_0 import Condition0
        from src.config.auto_trade import auto_trade_config

        c0 = Condition0(market_watch=auto_trade_config.auto_trade_symbols)
        c1 = Condition1(marketwatch=marketwatch, sizing=c0)

        worker = cls(
            condition1=c1,
            auto_magics=auto_magics,
            manage_manual=manage_manual,
        )

        poll_s = (interval_s if interval_s is not None
                  else settings.execution.sl_tick_interval_s)

        threading.Thread(
            target=worker._run_loop,
            args=(stop_event, poll_s),
            daemon=True,
        ).start()

        return worker

    def _run_loop(self, stop_event: threading.Event, interval_s: float) -> None:
        """Internal poll loop. Not called by main.py directly."""
        print(f"[StopLoss] armed — every {interval_s}s, "
              f"magics={sorted(self.auto_magics)}, "
              f"manage_manual={self.manage_manual}", flush=True)
        while not stop_event.is_set():
            try:
                self.process()
            except Exception as e:
                print(f"[StopLoss] process error — {type(e).__name__}: {e}",
                      flush=True)
            time.sleep(interval_s)

    # ═══════════════════════════════════════════════════════════════
    # Public API — one full pass over all positions
    # ═══════════════════════════════════════════════════════════════
    def process(self) -> None:
        """One full pass over all open positions. Idempotent, safe to call often."""
        self.condition1.begin_tick()
        try:
            positions = self._open_positions()
            for pos in positions:
                if not self._should_manage(pos):
                    continue
                try:
                    self._manage_one(pos)
                except Exception as e:
                    self._log(f"{pos.get('symbol')} ticket={pos.get('ticket')}: "
                              f"manage error — {type(e).__name__}: {e}")
        finally:
            self.condition1.end_tick()

        # forget positions that no longer exist
        live_tickets = {int(p["ticket"]) for p in positions}
        for ticket in list(self._managed.keys()):
            if ticket not in live_tickets:
                self._managed.pop(ticket, None)

        self._last_process_time = time.time()

    # ═══════════════════════════════════════════════════════════════
    # Internals
    # ═══════════════════════════════════════════════════════════════
    def _open_positions(self) -> list[dict]:
        raw = mt5.positions_get()
        if raw is None:
            return []
        return [p._asdict() for p in raw]

    def _should_manage(self, pos: dict) -> bool:
        magic = int(pos.get("magic", 0))
        if magic in self.auto_magics:
            return True
        return self.manage_manual and magic == 0

    def _manage_one(self, pos: dict) -> None:
        ticket = int(pos["ticket"])
        symbol = pos["symbol"]
        state = self._managed.get(ticket)

        if state is None:
            entry = float(pos["price_open"])
            initial_sl = float(pos.get("sl", 0.0))
            initial_risk = abs(entry - initial_sl) if initial_sl > 0 else 0.0
            state = ManagedPosition(
                ticket=ticket,
                symbol=symbol,
                side="long" if int(pos["type"]) == 0 else "short",
                entry=entry,
                initial_risk=initial_risk,
                stage="initial",
                last_sl=initial_sl,
            )
            self._managed[ticket] = state

        # Condition1 holds its own MarketWatch reference — no mw needed here.
        tick = self.condition1.marketwatch.tick(symbol)
        is_long = int(pos["type"]) == 0
        price = tick["bid"] if is_long else tick["ask"]

        current_sl = float(pos.get("sl", 0.0))

        # 1. breach handling first — SL already crossed
        if current_sl > 0 and self.condition1.is_sl_breached(pos, current_sl):
            self._handle_sl_breach(pos, state)
            return

        # 2. trailing takes priority, then breakeven
        candidate = self.condition1.trailing_sl(pos, price)
        if candidate is None:
            candidate = self.condition1.breakeven_sl(pos, price)
        if candidate is None:
            return

        # 3. only apply if it's a better SL
        if not self.condition1.better_sl(pos, candidate):
            return

        self._apply_sl(pos, candidate, stage="trail_or_be")

    def _handle_sl_breach(self, pos: dict, state: ManagedPosition) -> None:
        policy: str = settings.position_management.on_breach

        if policy == "skip":
            return

        if policy == "widen":
            widened = self.condition1.widened_sl_price(pos)
            if widened is None:
                return
            self._apply_sl(pos, widened, stage="widened")
            return

        if policy == "close":
            self._close_position(pos)
            return

    def _apply_sl(self, pos: dict, new_sl: float, *, stage: str) -> None:
        ticket = int(pos["ticket"])
        symbol = pos["symbol"]
        tp = float(pos.get("tp", 0.0))

        req = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": symbol,
            "position": ticket,
            "sl": float(new_sl),
            "tp": tp,
            "magic": int(pos.get("magic", 0)),
            "comment": f"sl:{stage}",
        }

        result = mt5.order_send(req)  # type: ignore[arg-type]
        if result is None:
            code, msg = mt5.last_error()
            self._log(f"{symbol} ticket={ticket}: SLTP send None [{code}]: {msg}")
            return

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            self._log(f"{symbol} ticket={ticket}: SLTP rejected "
                      f"[{result.retcode}]: {result.comment}")
            return

        state = self._managed.get(ticket)
        if state is not None:
            state.last_sl = new_sl
            state.stage = stage
            state.last_attach_attempt = time.time()

        self._log(f"{symbol} ticket={ticket}: SL → {new_sl:.5f} ({stage})")

    def _close_position(self, pos: dict) -> None:
        ticket = int(pos["ticket"])
        symbol = pos["symbol"]
        volume = float(pos["volume"])
        is_long = int(pos["type"]) == 0

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            self._log(f"{symbol} ticket={ticket}: no tick, cannot close")
            return

        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "position": ticket,
            "volume": volume,
            "type": mt5.ORDER_TYPE_SELL if is_long else mt5.ORDER_TYPE_BUY,
            "price": tick.bid if is_long else tick.ask,
            "deviation": 20,
            "magic": int(pos.get("magic", 0)),
            "comment": "sl:breach_close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(req)  # type: ignore[arg-type]
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            code = result.retcode if result else -1
            msg = result.comment if result else str(mt5.last_error())
            self._log(f"{symbol} ticket={ticket}: close rejected [{code}]: {msg}")
            return

        self._managed.pop(ticket, None)
        self._log(f"{symbol} ticket={ticket}: closed on SL breach")

    @staticmethod
    def _log(msg: str) -> None:
        print(f"[StopLoss] {msg}", flush=True)


__all__ = ["StopLossWorker", "ManagedPosition", "BreachPolicy"]