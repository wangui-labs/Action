# src/logic/labels.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Optional

LowLabel  = Literal["swing_low", "lower_low", "higher_low"]
HighLabel = Literal["swing_high", "higher_high", "lower_high"]


@dataclass(frozen=True)
class LowEvent:
    """Pure classification of one low against a reference. No mutation."""
    kind: Literal["baseline", "break_down", "bounce_up", "tie"]
    label: LowLabel          # what THIS node gets right now
    demote_reference: bool   # should the PREVIOUS reference be demoted?


@dataclass(frozen=True)
class HighEvent:
    kind: Literal["baseline", "break_up", "bounce_down", "tie"]
    label: HighLabel
    demote_reference: bool


def classify_low(price: float, reference: Optional[float]) -> LowEvent:
    if reference is None:
        return LowEvent("baseline",   "swing_low",  False)
    if price < reference:
        return LowEvent("break_down", "lower_low",  True)    # break → demote prev
    if price > reference:
        return LowEvent("bounce_up",  "higher_low", False)
    return LowEvent("tie",            "swing_low",  False)


def classify_high(price: float, reference: Optional[float]) -> HighEvent:
    if reference is None:
        return HighEvent("baseline",    "swing_high", False)
    if price > reference:
        return HighEvent("break_up",    "higher_high", True)   # break → demote prev
    if price < reference:
        return HighEvent("bounce_down", "lower_high",  False)
    return HighEvent("tie",             "swing_high", False)