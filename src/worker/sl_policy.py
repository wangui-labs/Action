# src/worker/sl_policy.py
"""
SLPolicy — stateless stop-loss policy. No MT5, no logic, just data.

Edit the defaults below to tune behavior. The StopLossWorker imports
this module and calls SLPolicy() — you don't need to touch the worker.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

BreachPolicy = Literal["widen", "close", "skip"]


@dataclass(frozen=True)
class SLPolicy:
    # ── ownership ───────────────────────────────────────────────
    magics: frozenset[int] = frozenset({20250101})
    manage_manual: bool = True

    # ── risk per trade (USD) ────────────────────────────────────
    risk_usd: float = 10.0

    # ── reward target (RR ratio: 1.0, 2.0, 4.0) ─────────────────
    rr_ratio: float = 2.0

    # ── breakeven ───────────────────────────────────────────────
    be_at_r: float = 1.0
    be_lock_pct: float = 0.0

    # ── breach handling ─────────────────────────────────────────
    on_breach: BreachPolicy = "close"
    breach_multiple: float = 1.5

    # ── safety ──────────────────────────────────────────────────
    initial_sl_if_missing: bool = True
    enforce_min_stop: bool = True


__all__ = ["SLPolicy", "BreachPolicy"]