# src/config/auto_trade.py
"""
Per-symbol / contract-level auto-trade config.

Owns: symbol universe, categories, per-symbol minimum lot.
Global risk / BE / trail / influence policy lives in src/config/settings.py.

Lot sizing rule (today):
    Lot size is ALWAYS the symbol's minimum lot.
    - US30m / USTECm         → 0.05
    - everything else         → 0.01
    No stepping, no clamping, no "requested lot".

get_settings() is a flat-dict compatibility view over both files.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from src.config.settings import settings


class TradeMode(Enum):
    MANUAL = "MANUAL"
    AUTO = "AUTO"


INDICES_SYMBOLS: set[str] = {"US30m", "USTECm"}

COMMODITIES_SYMBOLS: set[str] = {
    # energy
    "USOILm", "UKOILm", "XNGUSDm",
    # metals
    "XAUUSDm", "XAGUSDm",
    # FX majors / crosses
    "EURUSDm", "GBPUSDm", "AUDUSDm", "NZDUSDm", "USDJPYm",
    "AUDCHFm", "AUDNZDm",
    # FX exotics
    "AUDMXNm", "AUDNOKm", "USDMXNm", "USDNOKm",
}


@dataclass
class AutoTradeConfig:
    # --- symbol universe ---
    mode: TradeMode = TradeMode.AUTO
    auto_trade_symbols: set[str] = field(default_factory=set)
    indices_symbols: set[str] = field(default_factory=lambda: set(INDICES_SYMBOLS))
    commodities_symbols: set[str] = field(default_factory=lambda: set(COMMODITIES_SYMBOLS))

    # --- lot contract (minimum lot only) ---
    default_min_lot: float = 0.01
    indices_default_min_lot: float = 0.05
    symbol_min_lot: dict[str, float] = field(default_factory=dict)

    # --- SL sizing mode (only "dollar_risk" is used in practice) ---
    sl_mode: str = "dollar_risk"

    # --- overrides ---
    symbol_overrides: dict[str, dict] = field(default_factory=dict)

    # --- manual SL/TP toggle ---
    sl_tp_apply_to_manual: bool = True

    def __post_init__(self) -> None:
        self.auto_trade_symbols = {s.upper() for s in self.auto_trade_symbols}
        self.indices_symbols = {s.upper() for s in self.indices_symbols}
        self.commodities_symbols = {s.upper() for s in self.commodities_symbols}
        self.symbol_min_lot = {k.upper(): float(v) for k, v in self.symbol_min_lot.items()}
        self.symbol_overrides = {k.upper(): v for k, v in self.symbol_overrides.items()}
        for s in self.indices_symbols:
            self.symbol_min_lot.setdefault(s, self.indices_default_min_lot)
        if not self.auto_trade_symbols:
            self.auto_trade_symbols = self.indices_symbols | self.commodities_symbols

    def configure(self, **kwargs) -> None:
        for k, v in kwargs.items():
            if not hasattr(self, k):
                raise AttributeError(f"AutoTradeConfig has no field {k!r}")
            setattr(self, k, v)
        self.__post_init__()

    # --- symbol universe / category ---
    def is_auto_trade_symbol(self, symbol: str) -> bool:
        return True if not self.auto_trade_symbols else symbol.upper() in self.auto_trade_symbols

    def symbol_category(self, symbol: str) -> str | None:
        s = symbol.upper()
        if s in self.indices_symbols:
            return "indices"
        if s in self.commodities_symbols:
            return "commodities"
        return None

    def add_indices(self, *symbols: str) -> None:
        self.indices_symbols.update(s.upper() for s in symbols)
        self.auto_trade_symbols.update(s.upper() for s in symbols)
        for s in symbols:
            self.symbol_min_lot.setdefault(s.upper(), self.indices_default_min_lot)

    def add_commodities(self, *symbols: str) -> None:
        self.commodities_symbols.update(s.upper() for s in symbols)
        self.auto_trade_symbols.update(s.upper() for s in symbols)

    # --- per-symbol minimum lot ---
    def get_min_lot(self, symbol: str) -> float:
        """The lot size we will always use — the symbol's minimum."""
        return self.symbol_min_lot.get(symbol.upper(), self.default_min_lot)

    # --- flat dict view — compatibility over both files ---
    def get_settings(self, symbol: str | None = None) -> dict:
        s = (symbol or "").upper()
        out = {
            # owned here
            "mode": self.mode.value,
            "min_lot": self.get_min_lot(s),
            "category": self.symbol_category(s),
            "sl_mode": self.sl_mode,
            "sl_tp_apply_to_manual": self.sl_tp_apply_to_manual,
            # owned by settings.py — projected here for dict consumers
            "magic_number": settings.influence.magic,
            "max_open_trades": settings.influence.max_open_trades,
            "max_total_lots": settings.influence.max_total_lots,
            "max_lots_per_symbol": settings.influence.max_lots_per_symbol,
            "target_risk_usd": settings.risk.target_risk_usd,
            "rr_default": settings.risk.rr_default,
            "rr_trend_aligned": settings.risk.rr_trend_aligned,
            "be_trigger_r": settings.position_management.be_at_r,
            "trail_start_r": settings.position_management.trail_at_r,
        }
        if s and s in self.symbol_overrides:
            out.update(self.symbol_overrides[s])
        return out

    def should_apply_sl_tp(self) -> bool:
        return True if self.mode == TradeMode.AUTO else self.sl_tp_apply_to_manual


auto_trade_config = AutoTradeConfig()


__all__ = [
    "auto_trade_config",
    "AutoTradeConfig",
    "TradeMode",
    "INDICES_SYMBOLS",
    "COMMODITIES_SYMBOLS",
]