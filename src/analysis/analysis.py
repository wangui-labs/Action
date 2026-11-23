# src/analysis/analysis.py
"""
Analysis — combines flow_0 + flow_2. Wired into main.py via one line:

    analysis = Analysis(layer.md, layer.windows)
    analysis.order = order
    for (sym, tf) in layer.windows:
        layer.feed.subscribe(sym, tf,
            lambda c, s=sym, t=tf: analysis.on_bar(s, t, c))

Only 15m / 4h bars do work. Everything else returns immediately.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from src.data_structures.structures import Candle
from src.pipeline.access import MarketData
from src.pipeline.window import Window

from src.analysis.flow_0 import Flow0, FlowResult
from src.analysis.flow_2 import FLOW_TFS, Flow2, ConsolidationResult

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Decision:
    symbol: str
    tf: str
    kind: str
    side: str
    price: float
    reason: str
    unix: int

    def to_record(self) -> dict:
        return {"symbol": self.symbol, "tf": self.tf, "kind": self.kind,
                "side": self.side, "price": self.price,
                "reason": self.reason, "unix": self.unix}


class Analysis:
    """Per-bar analysis over the 15m and 4h windows. Emits Decisions."""

    def __init__(self, md: MarketData,
                 windows: dict[tuple[str, str], Window], *,
                 pip_size: float = 0.1,
                 one_sided_threshold: int = 4,
                 order=None):
        self.md = md
        self.windows = windows
        self.order = order
        self._flow0: dict[str, Flow0] = {
            tf: Flow0(one_sided_threshold=one_sided_threshold) for tf in FLOW_TFS
        }
        self._flow2 = Flow2(pip_size=pip_size)
        self.decisions: list[Decision] = []
        self._last_decision_unix: dict[tuple[str, str], int] = {}

    def on_bar(self, symbol: str, tf: str, candle: Candle) -> None:
        if tf not in FLOW_TFS:
            return
        w = self.windows.get((symbol, tf))
        if w is None or len(w) < 20:
            return
        self._evaluate(symbol, tf, candle, w)

    def _evaluate(self, symbol: str, tf: str, candle: Candle,
                  w: Window) -> None:
        bars = w.bars()

        flow: FlowResult = self._flow0[tf].run(bars, log_events=False)
        cons: ConsolidationResult = self._flow2.run(
            bars, flow, tf=tf, log_events=False)

        for rec in cons.qualified:
            if not rec.has_exit:
                continue
            if rec.exit_index != candle.index:
                continue
            side = "BUY" if rec.exit_direction == "up" else "SELL"
            self._decide(symbol=symbol, tf=tf, kind="consolidation_exit",
                         side=side, price=rec.exit_close_price or candle.close,
                         candle=candle,
                         reason=(f"consolidation exit {rec.exit_direction} "
                                 f"[{rec.range_low:.3f}–{rec.range_high:.3f}] "
                                 f"{rec.range_pips:.1f}p "
                                 f"held={rec.exit_held_bars} zone={rec.zone}"))

        if len(flow.bars) >= 2:
            prev_lb = flow.bars[-2]
            curr_lb = flow.bars[-1]
            if (prev_lb.is_one_sided
                    and prev_lb.direction.value != curr_lb.direction.value
                    and curr_lb.direction.value != "neutral"):
                side = "BUY" if curr_lb.direction.value == "bullish" else "SELL"
                self._decide(symbol=symbol, tf=tf, kind="streak_break",
                             side=side, price=candle.close, candle=candle,
                             reason=(f"streak broke after {prev_lb.streak} "
                                     f"{prev_lb.direction.value} bars"))

    def _decide(self, symbol: str, tf: str, kind: str, side: str,
                price: float, candle: Candle, reason: str) -> None:
        key = (symbol, tf)
        if self._last_decision_unix.get(key) == candle.unix_time:
            return
        self._last_decision_unix[key] = candle.unix_time

        d = Decision(symbol=symbol, tf=tf, kind=kind, side=side,
                     price=price, reason=reason, unix=candle.unix_time)
        self.decisions.append(d)

        log.info("DECISION  %-8s %-3s  kind=%-18s  side=%-4s  price=%.3f  %s",
                 symbol, tf, kind, side, price, reason)

        if self.order is not None:
            try:
                self._send_order(d)
            except Exception:
                log.exception("order send failed for %s", d)

    def _send_order(self, d: Decision) -> None:
        log.info("order hook — decision logged only: %s", d.to_record())

    def window(self, symbol: str, tf: str) -> Optional[Window]:
        return self.windows.get((symbol, tf))

    def last_decision(self) -> Optional[Decision]:
        return self.decisions[-1] if self.decisions else None

    def summary(self) -> str:
        by_kind: dict[str, int] = {}
        for d in self.decisions:
            by_kind[d.kind] = by_kind.get(d.kind, 0) + 1
        parts = ", ".join(f"{k}={v}" for k, v in by_kind.items()) or "none"
        return f"decisions={len(self.decisions)} ({parts})"


__all__ = ["Analysis", "Decision"]