# src/analysis/flow_2.py
"""
Flow 2 — consolidation detection on 15m and 4h swings from flow_0.

Min-swing filter (pips, per TF):
    15m → 60
     4h → 120

    from src.analysis.flow_0 import label_bars
    from src.analysis.flow_2 import find_consolidations, find_consolidations_multi

    flow = label_bars(window.bars())
    cons = find_consolidations(window.bars(), flow, tf="15m")
    cons.qualified   # list[ConsolidationRecord]

    # both TFs from a DataLayer
    res = find_consolidations_multi(layer, "XAUUSDm")
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Sequence

from src.data_structures.structures import Candle
from src.logic.consolidation import ConsolidationDetector, ConsolidationRecord
from src.logic.fractals import FractalNode
from src.analysis.flow_0 import FlowResult

log = logging.getLogger(__name__)

FLOW_TFS: tuple[str, ...] = ("15m", "4h")

MIN_SWING_PIPS: dict[str, float] = {
    "15m": 60.0,
    "4h":  120.0,
}
DEFAULT_MIN_SWING_PIPS = 60.0


@dataclass
class ConsolidationResult:
    records: list[ConsolidationRecord] = field(default_factory=list)
    skipped_small: int = 0
    skipped_other: int = 0
    events: list[dict] = field(default_factory=list)

    @property
    def qualified(self) -> list[ConsolidationRecord]:
        return [r for r in self.records if r.qualifies]

    def summary(self) -> str:
        q = len(self.qualified)
        return (f"consolidations={len(self.records)} (qualified={q})  "
                f"skipped_small={self.skipped_small}  "
                f"skipped_other={self.skipped_other}  events={len(self.events)}")


class Flow2:
    """Detect consolidations on opposite-type swings from FlowResult."""

    def __init__(self, pip_size: float = 0.1,
                 max_range_pips: float | dict[str, float] = 60.0,
                 min_candles_inside: int = 8,
                 min_swing_pips_by_tf: Optional[dict[str, float]] = None):
        if pip_size <= 0:
            raise ValueError(f"pip_size must be > 0, got {pip_size}")
        self.pip_size = pip_size
        self.min_swing_pips = min_swing_pips_by_tf or MIN_SWING_PIPS
        self.detector = ConsolidationDetector(
            pip_size=pip_size, max_range_pips=max_range_pips,
            min_candles_inside=min_candles_inside)

    def run(self, candles: Sequence[Candle], flow: FlowResult,
            tf: Optional[str] = None, *,
            log_events: bool = True) -> ConsolidationResult:
        candles = list(candles)
        result = ConsolidationResult()
        if not candles:
            return result
        tf = tf or candles[0].timeframe
        if tf not in FLOW_TFS:
            log.debug("FLOW2 skip   tf=%s not in %s", tf, FLOW_TFS)
            return result
        if not flow.nodes:
            return result

        min_pips = self.min_swing_pips.get(tf, DEFAULT_MIN_SWING_PIPS)
        log.info("FLOW2 start  tf=%s  nodes=%d  pairs=%d  min_swing_pips=%.1f",
                 tf, len(flow.nodes), len(flow.pairs), min_pips)

        for pair in flow.pairs:
            n1, n2 = pair.start, pair.end
            if n1.swing_type == n2.swing_type:
                result.skipped_other += 1
                continue
            low_node  = n1 if n1.swing_type == "swing_low" else n2
            high_node = n2 if n1.swing_type == "swing_low" else n1
            span_pips = (high_node.price - low_node.price) / self.pip_size

            if span_pips < min_pips:
                result.skipped_small += 1
                log.debug("FLOW2 skip   %s %s  span=%.1fp < min=%.1fp",
                          n1.symbol, tf, span_pips, min_pips)
                continue

            try:
                rec = self.detector.detect(candles, n1, n2)
            except Exception as e:
                result.skipped_other += 1
                log.warning("FLOW2 detect failed  low@%d high@%d  %s",
                            low_node.index, high_node.index, e)
                continue

            result.records.append(rec)
            log.info("FLOW2 rec    %s %s  [%.3f–%.3f]  %.1fp  qualifies=%s  "
                     "inside=%d  touches_eq=%d  false_moves=%d  zone=%s",
                     rec.symbol, rec.timeframe, rec.range_low, rec.range_high,
                     rec.range_pips, rec.qualifies, rec.candles_inside,
                     rec.touches_eq, rec.false_moves, rec.zone)
            if rec.has_exit:
                log.info("FLOW2 exit   %s %s  dir=%s  close=%.3f  held=%d",
                         rec.symbol, rec.timeframe, rec.exit_direction,
                         rec.exit_close_price, rec.exit_held_bars)

        result.events = self._build_events(result)
        if log_events:
            log.info("FLOW2 done   %s", result.summary())
        return result

    @staticmethod
    def _build_events(r: ConsolidationResult) -> list[dict]:
        out: list[dict] = []
        for rec in r.records:
            out.append({
                "type": "consolidation",
                "symbol": rec.symbol, "tf": rec.timeframe,
                "range_low": rec.range_low, "range_high": rec.range_high,
                "range_pips": rec.range_pips, "qualifies": rec.qualifies,
                "candles_inside": rec.candles_inside,
                "touches_eq": rec.touches_eq, "false_moves": rec.false_moves,
                "zone": rec.zone,
                "exit": None if not rec.has_exit else {
                    "direction": rec.exit_direction, "index": rec.exit_index,
                    "close": rec.exit_close_price, "held": rec.exit_held_bars,
                },
            })
        return out


_DEFAULT_FLOW2: Optional[Flow2] = None

def find_consolidations(candles: Sequence[Candle], flow: FlowResult,
                        tf: Optional[str] = None, *,
                        pip_size: float = 0.1,
                        log_events: bool = True) -> ConsolidationResult:
    tf = tf or (candles[0].timeframe if candles else None)
    if tf not in FLOW_TFS:
        raise ValueError(f"flow_2 only runs on {FLOW_TFS}, got {tf!r}")
    global _DEFAULT_FLOW2
    if _DEFAULT_FLOW2 is None or _DEFAULT_FLOW2.pip_size != pip_size:
        _DEFAULT_FLOW2 = Flow2(pip_size=pip_size)
    return _DEFAULT_FLOW2.run(candles, flow, tf=tf, log_events=log_events)


def find_consolidations_multi(layer, symbol: str, *,
                              pip_size: float = 0.1,
                              log_events: bool = True) -> dict[str, ConsolidationResult]:
    from src.analysis.flow_0 import label_bars
    out: dict[str, ConsolidationResult] = {}
    for tf in FLOW_TFS:
        w = layer.window(symbol, tf)
        if w is None or len(w) < 20:
            log.warning("FLOW2 multi   %s %s — window missing or too short",
                        symbol, tf)
            out[tf] = ConsolidationResult()
            continue
        bars = w.bars()
        flow = label_bars(bars, log_events=False)
        out[tf] = find_consolidations(bars, flow, tf=tf,
                                      pip_size=pip_size, log_events=log_events)
    return out


__all__ = [
    "FLOW_TFS", "MIN_SWING_PIPS", "ConsolidationResult", "Flow2",
    "find_consolidations", "find_consolidations_multi",
]