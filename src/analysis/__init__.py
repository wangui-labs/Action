# src/analysis/__init__.py
"""
Analysis package.

Public API:

    from src.analysis import Analysis
    from src.analysis import label_bars, find_consolidations
    from src.analysis import Flow0, Flow2, FlowResult, ConsolidationResult
    from src.analysis import FLOW_TFS, Decision

`main.py` should import only `Analysis` from here.
"""
from __future__ import annotations

from src.analysis.analysis import Analysis, Decision
from src.analysis.flow_0 import (
    Flow0,
    FlowResult,
    LabeledBar,
    label_bars,
)
from src.analysis.flow_2 import (
    FLOW_TFS,
    MIN_SWING_PIPS,
    ConsolidationResult,
    Flow2,
    find_consolidations,
    find_consolidations_multi,
)

__all__ = [
    # main consumer
    "Analysis",
    "Decision",
    # flow_0
    "Flow0",
    "FlowResult",
    "LabeledBar",
    "label_bars",
    # flow_2
    "FLOW_TFS",
    "MIN_SWING_PIPS",
    "Flow2",
    "ConsolidationResult",
    "find_consolidations",
    "find_consolidations_multi",
]