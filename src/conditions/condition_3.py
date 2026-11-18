# src/conditions/condition_3.py
from __future__ import annotations
from typing import Optional
from src.config.auto_trade import auto_trade_config


class Condition3:
    def __init__(
        self,
        max_open_trades: int = 50,
        max_total_lots: float = 10.0,
        max_lots_per_symbol: Optional[float] = None,
        name: str = "condition_3",
        enforce: bool = False,
    ):
        if max_open_trades <= 0:
            raise ValueError(f"max_open_trades must be > 0, got {max_open_trades}")
        if max_total_lots <= 0:
            raise ValueError(f"max_total_lots must be > 0, got {max_total_lots}")
        if max_lots_per_symbol is not None and max_lots_per_symbol <= 0:
            raise ValueError(f"max_lots_per_symbol must be > 0, got {max_lots_per_symbol}")
        self.name = name
        self.enforce = enforce
        self.max_open_trades = max_open_trades
        self.max_total_lots = max_total_lots
        self.max_lots_per_symbol = max_lots_per_symbol

    def _positions(self, data: dict) -> list[dict]:
        if "open_positions" not in data:
            if self.enforce:
                raise KeyError(f"{self.name}: missing 'open_positions'")
            return []
        return list(data["open_positions"])

    def _proposed_lot(self, data: dict) -> float:
        lot = data.get("proposed_lot")
        if lot is None:
            if self.enforce:
                raise KeyError(f"{self.name}: missing 'proposed_lot'")
            return 0.0
        return float(lot)

    def _symbol(self, data: dict) -> Optional[str]:
        return data.get("symbol", None)

    def _volumes(self, positions: list[dict]) -> tuple[float, dict[str, float]]:
        total = 0.0
        by_symbol: dict[str, float] = {}
        for p in positions:
            v = float(p.get("volume", 0.0))
            total += v
            s = str(p.get("symbol", "")).upper()
            by_symbol[s] = by_symbol.get(s, 0.0) + v
        return total, by_symbol

    def check(self, data: dict) -> bool:
        positions = self._positions(data)
        proposed = self._proposed_lot(data)
        symbol = self._symbol(data)
        total_vol, by_symbol = self._volumes(positions)

        if len(positions) >= self.max_open_trades:
            if self.enforce:
                raise ValueError(f"{self.name}: trade count cap hit ({len(positions)}/{self.max_open_trades})")
            return False

        if total_vol + proposed > self.max_total_lots:
            if self.enforce:
                raise ValueError(f"{self.name}: lots cap hit ({total_vol + proposed:.2f}/{self.max_total_lots})")
            return False

        if self.max_lots_per_symbol is not None and symbol:
            s = symbol.upper()
            if by_symbol.get(s, 0.0) + proposed > self.max_lots_per_symbol:
                if self.enforce:
                    raise ValueError(f"{self.name}: per-symbol lots cap hit ({s}: {by_symbol.get(s, 0.0) + proposed:.2f}/{self.max_lots_per_symbol})")
                return False

        return True

    def reason(self, data: dict) -> Optional[str]:
        positions = self._positions(data)
        proposed = self._proposed_lot(data)
        symbol = self._symbol(data)
        total_vol, by_symbol = self._volumes(positions)

        if len(positions) >= self.max_open_trades:
            return f"{self.name}: trade count cap hit ({len(positions)}/{self.max_open_trades})"
        if total_vol + proposed > self.max_total_lots:
            return f"{self.name}: lots cap hit ({total_vol + proposed:.2f}/{self.max_total_lots})"
        if self.max_lots_per_symbol is not None and symbol:
            s = symbol.upper()
            if by_symbol.get(s, 0.0) + proposed > self.max_lots_per_symbol:
                return f"{self.name}: per-symbol lots cap hit ({s}: {by_symbol.get(s, 0.0) + proposed:.2f}/{self.max_lots_per_symbol})"
        return None