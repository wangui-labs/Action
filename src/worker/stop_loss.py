# src/worker/stop_loss.py
"""
StopLossWorker — stateless SL/TP manager.

main.py calls exactly ONE line:

    from src.worker.stop_loss import start as start_stop_loss
    sl = start_stop_loss(mw, stop)

Policy comes from src/worker/sl_policy.py. Interval defaults to 10s.
To change behavior, edit SLPolicy defaults — don't touch this file
or main.py.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

import MetaTrader5 as mt5  # type: ignore[import]

from src.interface.marketwatch import MarketWatch
from src.worker.sl_policy import SLPolicy


# ═══════════════════════════════════════════════════════════════════
# PositionView — frozen snapshot, built fresh each pass
# ═══════════════════════════════════════════════════════════════════
@dataclass(frozen=True, slots=True)
class PositionView:
    ticket: int
    symbol: str
    is_long: bool
    volume: float
    entry: float
    current: float
    sl: float
    tp: float
    magic: int

    @property
    def side_sign(self) -> int:
        return 1 if self.is_long else -1

    @property
    def initial_risk(self) -> float:
        return abs(self.entry - self.sl) if self.sl > 0 else 0.0

    @property
    def r_multiple(self) -> float:
        risk = self.initial_risk
        if risk <= 0:
            return 0.0
        return (self.current - self.entry) * self.side_sign / risk


# ═══════════════════════════════════════════════════════════════════
# StopLossWorker — the implementation
# ═══════════════════════════════════════════════════════════════════
class StopLossWorker:
    """Stateless SL/TP manager. Never instantiated directly by main.py."""

    def __init__(self, marketwatch: MarketWatch, *,
                 policy: Optional[SLPolicy] = None,
                 interval_s: float = 10.0):
        self.mw = marketwatch
        self.policy = policy or SLPolicy()
        self.interval_s = interval_s

    # ── public — one pass over all positions ─────────────────────
    def process(self) -> None:
        raw = mt5.positions_get()
        if raw is None:
            return
        for mt5_pos in raw:
            try:
                view = self._view_from(mt5_pos)
                if view is None:
                    continue
                if not self._should_manage(view):
                    continue
                self._manage_one(view)
            except Exception as e:
                symbol = getattr(mt5_pos, "symbol", "?")
                ticket = getattr(mt5_pos, "ticket", "?")
                self._log(f"{symbol} ticket={ticket}: manage error — "
                          f"{type(e).__name__}: {e}")

    # ── internal loop ────────────────────────────────────────────
    def _run_loop(self, stop_event: threading.Event) -> None:
        print(f"[StopLoss] armed — every {self.interval_s}s, "
              f"magics={sorted(self.policy.magics)}, "
              f"manage_manual={self.policy.manage_manual}, "
              f"risk=${self.policy.risk_usd}, "
              f"rr={self.policy.rr_ratio}, "
              f"be_at_r={self.policy.be_at_r}",
              flush=True)
        while not stop_event.is_set():
            try:
                self.process()
            except Exception as e:
                print(f"[StopLoss] process error — {type(e).__name__}: {e}",
                      flush=True)
            time.sleep(self.interval_s)

    # ── view construction ────────────────────────────────────────
    def _view_from(self, mt5_pos) -> Optional[PositionView]:
        tick = self.mw.tick(mt5_pos.symbol)
        is_long = mt5_pos.type == 0
        current = tick["bid"] if is_long else tick["ask"]
        return PositionView(
            ticket=int(mt5_pos.ticket),
            symbol=mt5_pos.symbol,
            is_long=is_long,
            volume=float(mt5_pos.volume),
            entry=float(mt5_pos.price_open),
            current=float(current),
            sl=float(mt5_pos.sl or 0.0),
            tp=float(mt5_pos.tp or 0.0),
            magic=int(mt5_pos.magic or 0),
        )

    def _should_manage(self, v: PositionView) -> bool:
        if v.magic in self.policy.magics:
            return True
        return self.policy.manage_manual and v.magic == 0

    # ── decision tree ────────────────────────────────────────────
    def _manage_one(self, v: PositionView) -> None:
        # 1. Unprotected → add SL + TP
        if v.sl <= 0 or v.tp <= 0:
            if self.policy.initial_sl_if_missing:
                self._place_initial_sltp(v)
            return

        # 2. Breach → policy handling
        if self._is_sl_breached(v):
            self._handle_breach(v)
            return

        # 3. Breakeven
        if v.r_multiple >= self.policy.be_at_r and not self._is_be(v):
            self._apply_breakeven(v)
            return

        # 4. Nothing to do (no trailing)

    # ── actions ──────────────────────────────────────────────────
    def _place_initial_sltp(self, v: PositionView) -> None:
        snap = self.mw.snapshot(v.symbol)
        sl_dist = self._risk_distance(v, snap)
        if sl_dist is None:
            self._log(f"{v.symbol} ticket={v.ticket}: cannot size SL "
                      f"(tick_value={snap.tick_value}, vol={v.volume})")
            return

        sl_price = round(v.entry - sl_dist * v.side_sign, snap.digits)
        tp_dist  = sl_dist * self.policy.rr_ratio
        tp_price = round(v.entry + tp_dist * v.side_sign, snap.digits)

        if not self._passes_min_stop(v, sl_price, snap):
            self._log(f"{v.symbol} ticket={v.ticket}: initial SL too close "
                      f"to market ({sl_price} vs {v.current}) — skipping")
            return
        if not self._passes_min_stop(v, tp_price, snap):
            self._log(f"{v.symbol} ticket={v.ticket}: initial TP too close "
                      f"to market ({tp_price} vs {v.current}) — skipping")
            return

        self._send_sltp(v, sl_price, tp_price, stage="initial")
        self._log(f"{v.symbol} ticket={v.ticket}: initial SL/TP placed  "
                  f"sl={sl_price}  tp={tp_price}  "
                  f"risk=${self.policy.risk_usd}  rr={self.policy.rr_ratio}")

    def _apply_breakeven(self, v: PositionView) -> None:
        snap = self.mw.snapshot(v.symbol)
        lock = v.initial_risk * self.policy.be_lock_pct
        be_price = round(v.entry + lock * v.side_sign, snap.digits)

        if not self._passes_min_stop(v, be_price, snap):
            self._log(f"{v.symbol} ticket={v.ticket}: BE target too close "
                      f"to market ({be_price} vs {v.current}) — holding")
            return
        if not self._is_better_sl(v, be_price, snap):
            return

        self._send_sltp(v, be_price, v.tp, stage="breakeven")
        self._log(f"{v.symbol} ticket={v.ticket}: SL → breakeven {be_price}  "
                  f"(R={v.r_multiple:+.2f})")

    def _handle_breach(self, v: PositionView) -> None:
        policy = self.policy.on_breach
        if policy == "skip":
            return
        if policy == "close":
            self._close(v)
            return
        if policy == "widen":
            snap = self.mw.snapshot(v.symbol)
            widened_usd = self.policy.risk_usd * self.policy.breach_multiple
            dist = self._risk_distance(v, snap, risk_usd=widened_usd)
            if dist is None:
                return
            new_sl = round(v.current - dist * v.side_sign, snap.digits)
            if self._passes_min_stop(v, new_sl, snap):
                self._send_sltp(v, new_sl, v.tp, stage="widened")
                self._log(f"{v.symbol} ticket={v.ticket}: SL widened to "
                          f"{new_sl} (policy=widen)")

    # ── math (was Condition1) ────────────────────────────────────
    def _risk_distance(self, v: PositionView, snap, *,
                       risk_usd: Optional[float] = None) -> Optional[float]:
        usd = risk_usd if risk_usd is not None else self.policy.risk_usd
        denom = snap.tick_value * max(v.volume, 1e-9)
        if denom <= 0:
            return None
        points = usd / denom
        return points * snap.tick_size

    def _passes_min_stop(self, v: PositionView, price: float, snap) -> bool:
        if not self.policy.enforce_min_stop:
            return True
        min_dist = (snap.stops_level_points or 10) * snap.point
        return abs(price - v.current) >= min_dist

    def _is_sl_breached(self, v: PositionView) -> bool:
        if v.sl <= 0:
            return False
        return (v.is_long and v.current <= v.sl) or \
               (not v.is_long and v.current >= v.sl)

    def _is_be(self, v: PositionView) -> bool:
        lock = v.entry + v.initial_risk * self.policy.be_lock_pct * v.side_sign
        return (v.is_long and v.sl >= lock) or (not v.is_long and v.sl <= lock)

    def _is_better_sl(self, v: PositionView, candidate: float, snap) -> bool:
        if v.sl <= 0:
            return True
        if abs(candidate - v.sl) < snap.tick_size * 0.5:
            return False
        return (v.is_long and candidate > v.sl) or \
               (not v.is_long and candidate < v.sl)

    # ── broker I/O ───────────────────────────────────────────────
    def _send_sltp(self, v: PositionView, sl: float, tp: float,
                   *, stage: str) -> None:
        req = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": v.symbol,
            "position": v.ticket,
            "sl": float(sl),
            "tp": float(tp),
            "magic": v.magic,
            "comment": f"sl:{stage}",
        }
        result = mt5.order_send(req)  # type: ignore[arg-type]
        if result is None:
            code, msg = mt5.last_error()
            self._log(f"{v.symbol} ticket={v.ticket}: SLTP send None "
                      f"[{code}]: {msg}")
            return
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            self._log(f"{v.symbol} ticket={v.ticket}: SLTP rejected "
                      f"[{result.retcode}]: {result.comment}")

    def _close(self, v: PositionView) -> None:
        tick = self.mw.tick(v.symbol)
        if tick is None:
            self._log(f"{v.symbol} ticket={v.ticket}: no tick, cannot close")
            return
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": v.symbol,
            "position": v.ticket,
            "volume": v.volume,
            "type": mt5.ORDER_TYPE_SELL if v.is_long else mt5.ORDER_TYPE_BUY,
            "price": tick["bid"] if v.is_long else tick["ask"],
            "deviation": 20,
            "magic": v.magic,
            "comment": "sl:breach_close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(req)  # type: ignore[arg-type]
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            code = result.retcode if result else -1
            msg = result.comment if result else str(mt5.last_error())
            self._log(f"{v.symbol} ticket={v.ticket}: close rejected "
                      f"[{code}]: {msg}")
            return
        self._log(f"{v.symbol} ticket={v.ticket}: closed on SL breach")

    @staticmethod
    def _log(msg: str) -> None:
        print(f"[StopLoss] {msg}", flush=True)


# ═══════════════════════════════════════════════════════════════════
# Module-level API — main.py calls exactly this
# ═══════════════════════════════════════════════════════════════════
def start(
    marketwatch: MarketWatch,
    stop_event: threading.Event,
    *,
    interval_s: float = 10.0,
) -> StopLossWorker:
    """
    Build a StopLossWorker with default policy, start it on a daemon
    thread, and return the worker.

        sl = start_stop_loss(mw, stop)

    To change behavior, edit src/worker/sl_policy.py — not this call.
    """
    worker = StopLossWorker(
        marketwatch,
        policy=SLPolicy(),
        interval_s=interval_s,
    )
    threading.Thread(
        target=worker._run_loop,
        args=(stop_event,),
        daemon=True,
    ).start()
    return worker


__all__ = ["start", "StopLossWorker", "PositionView"]