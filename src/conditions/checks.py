# src/conditions/condition_0.py
from __future__ import annotations
import math
from typing import Iterable, Optional
from src.config.auto_trade import auto_trade_config, TradeMode


def _half_up(x: float) -> int:
    return math.floor(x + 0.5)


def clamp_lot(lot: float, *, min_lot: float, max_lot: float, step: float) -> float:
    if not math.isfinite(lot): raise ValueError(f"lot must be finite, got {lot!r}")
    if not (min_lot > 0):      raise ValueError(f"min_lot must be > 0, got {min_lot!r}")
    if not (step > 0):         raise ValueError(f"step must be > 0, got {step!r}")
    if max_lot < min_lot:      raise ValueError(f"max_lot ({max_lot}) < min_lot ({min_lot})")
    lot = max(min_lot, min(max_lot, lot))
    snapped = min_lot + _half_up((lot - min_lot) / step) * step
    if snapped > max_lot: snapped -= step
    if snapped < min_lot: snapped = min_lot
    return round(snapped, 2)


class Condition0:
    def __init__(self, market_watch: Iterable[str], name: str = "condition_0", enforce_auto_trade: bool = True):
        self.name = name
        self.market_watch = frozenset(s.upper() for s in market_watch)
        self.enforce_auto_trade = enforce_auto_trade

    def check(self, data: dict) -> bool:
        s = (data.get("symbol") or "").upper()
        if not s or s not in self.market_watch: return False
        if auto_trade_config.mode != TradeMode.AUTO: return False
        if self.enforce_auto_trade and not auto_trade_config.is_auto_trade_symbol(s): return False
        return True

    def _require(self, symbol: str) -> str:
        s = symbol.upper()
        if s not in self.market_watch:
            raise KeyError(f"{self.name}: symbol {symbol!r} not in Market Watch ({sorted(self.market_watch)})")
        if self.enforce_auto_trade and not auto_trade_config.is_auto_trade_symbol(s):
            raise PermissionError(f"{self.name}: symbol {s!r} is not in the auto-trade universe")
        return s

    def _norm(self, overrides: Optional[dict[str, float]]) -> dict[str, float]:
        return {k.upper(): v for k, v in overrides.items()} if overrides else {}

    def size(self, symbol: str, overrides: Optional[dict[str, float]] = None) -> float:
        s = self._require(symbol)
        requested = self._norm(overrides).get(s) or auto_trade_config.get_settings(s).get("lot_size") or auto_trade_config.get_min_lot(s)
        return clamp_lot(float(requested),
                         min_lot=auto_trade_config.get_min_lot(s),
                         max_lot=auto_trade_config.get_max_lot(s),
                         step=auto_trade_config.get_lot_step(s))

    def apply(self, plan: dict, symbol: str, overrides: Optional[dict[str, float]] = None) -> dict:
        lot = self.size(symbol, overrides=overrides)
        s = auto_trade_config.get_settings(symbol)
        return {**plan, "lot_size": lot, "min_lot": s["min_lot"], "max_lot": s["max_lot"],
                "lot_step": s["lot_step"], "sizing_condition": self.name}