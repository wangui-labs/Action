# src/analysis/flow_0.py
"""
Flow 0 — label bars + detect swing structure.

Combines BearBullClassifier (logic/bear_bull.py) and Fractal (logic/fractals.py)
into a single chronological pass that emits a structured event stream.

    from src.analysis.flow_0 import label_bars
    flow = label_bars(window.bars())

    flow.bars        # list[LabeledBar]
    flow.nodes       # list[FractalNode]
    flow.pairs       # list[SwingPair]
    flow.events      # list[dict]
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal, Optional, Sequence

from src.data_structures.structures import Candle
from src.logic.bear_bull import BearBull, BearBullClassifier, Direction
from src.logic.fractals import Fractal, FractalNode, SwingPair, SwingPairer

log = logging.getLogger(__name__)

SwingCompare = Literal["HH", "HL", "LH", "LL", "first"]


@dataclass(frozen=True, slots=True)
class LabeledBar:
    candle: Candle
    direction: Direction
    streak: int
    is_one_sided: bool
    swing: Optional[Literal["swing_high", "swing_low"]] = None
    swing_compare: Optional[SwingCompare] = None


@dataclass
class FlowResult:
    bars: list[LabeledBar] = field(default_factory=list)
    nodes: list[FractalNode] = field(default_factory=list)
    pairs: list[SwingPair] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)

    def summary(self) -> str:
        bulls = sum(1 for b in self.bars if b.direction is Direction.BULLISH)
        bears = sum(1 for b in self.bars if b.direction is Direction.BEARISH)
        neuts = len(self.bars) - bulls - bears
        highs = sum(1 for n in self.nodes if n.swing_type == "swing_high")
        lows  = sum(1 for n in self.nodes if n.swing_type == "swing_low")
        return (f"bars={len(self.bars)} (bull={bulls} bear={bears} neutral={neuts})  "
                f"swings={len(self.nodes)} (high={highs} low={lows})  "
                f"pairs={len(self.pairs)}  events={len(self.events)}")


class Flow0:
    """Label bars + detect swings + pair them. Stateless across runs."""

    def __init__(self, one_sided_threshold: int = 4):
        self.classifier = BearBullClassifier(one_sided_threshold=one_sided_threshold)
        self.fractal = Fractal(period=1)

    def run(self, candles: Sequence[Candle], *,
            log_events: bool = True) -> FlowResult:
        candles = list(candles)
        result = FlowResult()
        if not candles:
            return result

        # 1. label every bar
        bb_list: list[BearBull] = self.classifier.classify_many(candles)
        bars_by_index: dict[int, LabeledBar] = {
            c.index: LabeledBar(candle=c, direction=bb.direction,
                                streak=bb.streak, is_one_sided=bb.is_one_sided)
            for c, bb in zip(candles, bb_list)
        }
        result.bars = list(bars_by_index.values())

        # 2. detect swing nodes
        nodes = self.fractal.detect_nodes(candles)
        result.nodes = nodes

        # 3. attach swing label to the bar that IS the swing
        for n in nodes:
            lb = bars_by_index.get(n.candle.index)
            if lb is not None:
                bars_by_index[n.candle.index] = LabeledBar(
                    candle=lb.candle, direction=lb.direction,
                    streak=lb.streak, is_one_sided=lb.is_one_sided,
                    swing=n.swing_type,
                )

        # 4. compare each swing to previous same-type swing
        prev_high: Optional[FractalNode] = None
        prev_low:  Optional[FractalNode] = None
        for n in nodes:
            if n.swing_type == "swing_high":
                cmp_label = self._compare(n, prev_high, higher_is="HH", lower_is="LH")
                prev_high = n
            else:
                cmp_label = self._compare(n, prev_low, higher_is="HL", lower_is="LL")
                prev_low = n
            lb = bars_by_index[n.candle.index]
            bars_by_index[n.candle.index] = LabeledBar(
                candle=lb.candle, direction=lb.direction,
                streak=lb.streak, is_one_sided=lb.is_one_sided,
                swing=lb.swing, swing_compare=cmp_label,
            )

        # 5. rebuild in chronological order
        result.bars = [bars_by_index[c.index] for c in candles]

        # 6. pair swings
        pairer = SwingPairer(nodes)
        result.pairs = pairer.build()

        # 7. events
        result.events = self._build_events(result)
        if log_events:
            self._emit(result)
        return result

    @staticmethod
    def _compare(curr: FractalNode, prev: Optional[FractalNode],
                 higher_is: Literal["HH", "HL"],
                 lower_is: Literal["LH", "LL"]) -> SwingCompare:
        if prev is None:
            return "first"
        return higher_is if curr.price > prev.price else lower_is

    @staticmethod
    def _build_events(r: FlowResult) -> list[dict]:
        events: list[dict] = []
        for b in r.bars:
            if b.swing is not None or b.is_one_sided:
                events.append({
                    "type": "bar",
                    "symbol": b.candle.symbol,
                    "tf": b.candle.timeframe,
                    "ny_time": b.candle.ny_time.isoformat(),
                    "close": b.candle.close,
                    "direction": b.direction.value,
                    "streak": b.streak,
                    "one_sided": b.is_one_sided,
                    "swing": b.swing,
                    "swing_compare": b.swing_compare,
                })
        for p in r.pairs:
            events.append({
                "type": "pair",
                "symbol": p.symbol,
                "tf": p.timeframe,
                "direction": p.direction,
                "start_time": p.start_time.isoformat(),
                "end_time": p.end_time.isoformat(),
                "price_amplitude": round(p.price_amplitude, 5),
                "duration_min": round(p.time_duration_minutes, 1),
                "velocity": round(p.velocity, 6),
            })
        return events

    @staticmethod
    def _emit(r: FlowResult) -> None:
        log.info("FLOW0  %s", r.summary())
        for e in r.events:
            if e["type"] == "bar" and e["swing"] is not None:
                log.info("FLOW0 swing  %s %s  %s  price=%.3f  cmp=%s  streak=%d",
                         e["symbol"], e["tf"], e["swing"], e["close"],
                         e["swing_compare"], e["streak"])
            elif e["type"] == "pair":
                log.info("FLOW0 pair   %s %s  dir=%s  amp=%.3f  dur=%.1fm  vel=%.6f",
                         e["symbol"], e["tf"], e["direction"],
                         e["price_amplitude"], e["duration_min"], e["velocity"])


_DEFAULT_FLOW = Flow0()

def label_bars(candles: Sequence[Candle], *,
               log_events: bool = False) -> FlowResult:
    """One-line API."""
    return _DEFAULT_FLOW.run(candles, log_events=log_events)


__all__ = ["Flow0", "FlowResult", "LabeledBar", "label_bars"]