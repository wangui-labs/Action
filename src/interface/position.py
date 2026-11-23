# src/interface/position.py
"""
Position — cached MT5 position/order/deal state. Stateless w.r.t. Connection.

    pos = Position()                  # no conn
    pos.refresh(force=True)
    pos.active() / pos.pending() / pos.closed()

main.py wires the refresh:

    conn.on_tick(pos.refresh)

Mutations (modify_sl_tp, close, cancel_order) call MT5 directly.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import MetaTrader5 as mt5


class PositionError(Exception):
    def __init__(self, action: str, code: int, message: str):
        self.action, self.code, self.message = action, code, message
        super().__init__(f"{action} failed [{code}]: {message}")


class Position:

    def __init__(
        self,
        history_limit: int = 100,
        active_interval_s: float = 2.0,
        history_interval_s: float = 30.0,
    ):
        self._history_limit = history_limit
        self._active: list[dict] = []
        self._pending: list[dict] = []
        self._closed: list[dict] = []
        self._last_active_ts: float = 0.0
        self._last_history_ts: float = 0.0
        self._active_interval_s = active_interval_s
        self._history_interval_s = history_interval_s
        self.refresh(force=True)

    def refresh(self, force: bool = False) -> None:
        now = time.time()
        if force or (now - self._last_active_ts) >= self._active_interval_s:
            self._last_active_ts = now
            self._refresh_active()
            self._refresh_pending()
        if force or (now - self._last_history_ts) >= self._history_interval_s:
            self._last_history_ts = now
            self._refresh_closed()

    def _refresh_active(self) -> None:
        try:
            raw = mt5.positions_get() or []
        except Exception as e:
            print(f"[Position] active refresh failed: {e}")
            return
        self._active = [p._asdict() for p in raw]

    def _refresh_pending(self) -> None:
        try:
            raw = mt5.orders_get() or []
        except Exception as e:
            print(f"[Position] pending refresh failed: {e}")
            return
        self._pending = [o._asdict() for o in raw]

    def _refresh_closed(self) -> None:
        try:
            to = datetime.now(timezone.utc)
            frm = to - timedelta(days=1)
            raw = mt5.history_deals_get(frm, to) or []
        except Exception as e:
            print(f"[Position] history refresh failed: {e}")
            return
        deals = [d._asdict() for d in raw
                 if d.entry in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_INOUT)]
        deals.sort(key=lambda d: d.get("time", 0), reverse=True)
        self._closed = deals[: self._history_limit]

    # ── active ──────────────────────────────────────────────────
    def active(self, symbol: Optional[str] = None,
               magic: Optional[int] = None) -> list[dict]:
        out = self._active
        if symbol:
            out = [p for p in out if p["symbol"] == symbol]
        if magic is not None:
            out = [p for p in out if p["magic"] == magic]
        return out

    def all(self, symbol: Optional[str] = None,
            magic: Optional[int] = None) -> list[dict]:
        return self.active(symbol=symbol, magic=magic)

    def get(self, ticket: int) -> Optional[dict]:
        for p in self._active:
            if p["ticket"] == ticket:
                return p
        return None

    def normalized(self, ticket: int) -> Optional[dict]:
        pos = self.get(ticket)
        if pos is None:
            return None
        is_long = pos["type"] == mt5.POSITION_TYPE_BUY
        return {
            "ticket": pos["ticket"], "symbol": pos["symbol"],
            "side": "long" if is_long else "short",
            "entry": pos["price_open"],
            "sl_price": pos["sl"], "tp_price": pos["tp"],
            "volume": pos["volume"], "profit": pos["profit"],
            "swap": pos["swap"], "commission": pos.get("commission", 0.0),
            "current_price": pos["price_current"],
            "magic": pos["magic"], "comment": pos["comment"],
        }

    def pnl(self, ticket: int) -> Optional[float]:
        pos = self.get(ticket)
        if pos is None:
            return None
        return pos["profit"] + pos["swap"] + pos.get("commission", 0.0)

    def count(self, symbol: Optional[str] = None,
              magic: Optional[int] = None) -> int:
        return len(self.active(symbol=symbol, magic=magic))

    def total_lots(self, symbol: Optional[str] = None,
                   magic: Optional[int] = None) -> float:
        return sum(p["volume"] for p in self.active(symbol=symbol, magic=magic))

    # ── pending ─────────────────────────────────────────────────
    def pending(self, symbol: Optional[str] = None) -> list[dict]:
        if symbol:
            return [o for o in self._pending if o["symbol"] == symbol]
        return self._pending

    def get_order(self, ticket: int) -> Optional[dict]:
        for o in self._pending:
            if o["ticket"] == ticket:
                return o
        return None

    def count_pending(self, symbol: Optional[str] = None) -> int:
        return len(self.pending(symbol=symbol))

    def total_pending_lots(self, symbol: Optional[str] = None) -> float:
        return sum(o["volume_current"] for o in self.pending(symbol=symbol))

    # ── closed ──────────────────────────────────────────────────
    def closed(self, limit: Optional[int] = None) -> list[dict]:
        return self._closed[:limit] if limit else self._closed

    def last_closed(self, symbol: Optional[str] = None) -> Optional[dict]:
        for d in self._closed:
            if symbol is None or d.get("symbol") == symbol:
                return d
        return None

    # ── mutations ───────────────────────────────────────────────
    def modify_sl_tp(self, ticket: int, sl: Optional[float] = None,
                     tp: Optional[float] = None) -> dict:
        pos = self.get(ticket)
        if pos is None:
            raise PositionError("modify", -1, f"position {ticket} not found")

        new_sl = float(sl) if sl is not None else float(pos["sl"])
        new_tp = float(tp) if tp is not None else float(pos["tp"])
        req = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": pos["symbol"], "position": int(ticket),
            "sl": new_sl, "tp": new_tp,
            "magic": int(pos.get("magic", 0)),
        }
        self._send(req, "modify_sl_tp")
        self.refresh(force=True)
        return {"retcode": mt5.TRADE_RETCODE_DONE,
                "ticket": ticket, "sl": new_sl, "tp": new_tp}

    def breakeven(self, ticket: int) -> dict:
        pos = self.get(ticket)
        if pos is None:
            raise PositionError("breakeven", -1, f"position {ticket} not found")
        return self.modify_sl_tp(ticket, sl=pos["price_open"])

    def close(self, ticket: int, lot: Optional[float] = None,
              comment: str = "") -> dict:
        pos = self.get(ticket)
        if pos is None:
            raise PositionError("close", -1, f"position {ticket} not found")

        volume = float(lot) if lot is not None else float(pos["volume"])
        if volume <= 0 or volume > pos["volume"]:
            raise PositionError("close", -1,
                                f"invalid close volume {volume} "
                                f"(position has {pos['volume']})")

        is_long = pos["type"] == mt5.POSITION_TYPE_BUY
        tick = mt5.symbol_info_tick(pos["symbol"])
        if tick is None:
            raise PositionError("close", -1, f"no tick for {pos['symbol']}")
        price = tick.bid if is_long else tick.ask

        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos["symbol"], "position": int(ticket),
            "volume": volume,
            "type": mt5.ORDER_TYPE_SELL if is_long else mt5.ORDER_TYPE_BUY,
            "price": float(price), "deviation": 20,
            "magic": int(pos.get("magic", 0)),
            "comment": comment or "close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        self._send(req, "close")
        self.refresh(force=True)
        return {"retcode": mt5.TRADE_RETCODE_DONE,
                "ticket": ticket, "price": price, "volume": volume}

    def close_all(self, symbol: Optional[str] = None,
                  magic: Optional[int] = None) -> list[dict]:
        out = []
        for pos in list(self.active(symbol=symbol, magic=magic)):
            try:
                out.append({"ticket": pos["ticket"], **self.close(pos["ticket"])})
            except PositionError as e:
                out.append({"ticket": pos["ticket"], "error": str(e)})
        return out

    def cancel_order(self, ticket: int) -> dict:
        if self.get_order(ticket) is None:
            raise PositionError("cancel", -1, f"order {ticket} not found")
        self._send({"action": mt5.TRADE_ACTION_REMOVE, "order": int(ticket)},
                   "cancel_order")
        self.refresh(force=True)
        return {"retcode": mt5.TRADE_RETCODE_DONE, "ticket": ticket}

    # ── internals ───────────────────────────────────────────────
    @staticmethod
    def _send(request: dict, action: str) -> None:
        check = mt5.order_check(request)
        if check is None or check.retcode != 0:
            code, msg = (mt5.last_error() if check is None
                         else (check.retcode, check.comment))
            raise PositionError(f"{action}:check", code,
                                msg or "pre-trade check failed")
        result = mt5.order_send(request)
        if result is None:
            code, msg = mt5.last_error()
            raise PositionError(f"{action}:send", code, msg)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            raise PositionError(f"{action}:send", result.retcode, result.comment)