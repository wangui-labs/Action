# src/config/settings.py
"""
Global runtime settings.

Single source of truth for all policy that is NOT per-symbol. Per-symbol
overrides live in auto_trade.py. Every file that needs policy imports
`settings` from here.

    from src.config.settings import settings
    settings.influence.magic                # 20250101
    settings.position_management.be_at_r    # 1.0
    settings.execution.sl_tick_interval_s   # 10.0
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════════
# Risk sizing
# ═══════════════════════════════════════════════════════════════════
@dataclass
class RiskSettings:
    target_risk_usd: float = 5.0        # per-trade dollar risk
    rr_default: float = 2.0             # reward:risk when not trend-aligned
    rr_trend_aligned: float = 2.5       # reward:risk when trend-aligned


# ─────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────
from pathlib import Path

LOG_DIR: Path = Path(__file__).resolve().parents[2] / "src" / "logs"
LOG_FILE: Path = LOG_DIR / "pipeline.log"
LOG_LEVEL: str = "INFO"
LOG_FORMAT: str = "%(asctime)s  %(levelname)-7s  %(name)-24s  %(message)s"
LOG_DATEFMT: str = "%Y-%m-%d %H:%M:%S"

# ═══════════════════════════════════════════════════════════════════
# Position management (BE / trail / breach)
# ═══════════════════════════════════════════════════════════════════
@dataclass
class PositionManagementSettings:
    # breakeven
    be_at_r: float = 1.0                # move SL to BE at this R multiple
    be_lock_pct: float = 0.10           # lock this % of initial risk in profit

    # trailing
    trail_at_r: float = 1.5             # start trailing at this R multiple
    trail_distance_r: float = 0.5       # trail this many Rs behind price

    # stops distance buffer above broker minimum
    stops_level_buffer: float = 1.5     # multiply broker min stop by this

    # when SL is breached (price crossed it before broker closed)
    on_breach: str = "close"            # "widen" | "close" | "skip"
    breach_multiple: float = 2.0        # widen to this many × risk
    tp_breach_multiple: float = 1.5     # escalate TP at this many × base RR


# ═══════════════════════════════════════════════════════════════════
# Influence — trade frequency / caps / magic
# ═══════════════════════════════════════════════════════════════════
@dataclass
class InfluenceSettings:
    magic: int = 20250101               # the identifier for auto-trades
    max_open_trades: int = 5            # total across account
    max_total_lots: float = 0.10        # total lots across account
    max_lots_per_symbol: float = 0.05   # per-symbol cap
    max_trades_per_symbol: int = 3      # per-symbol count cap
    max_trades_per_day: int = 20


# ═══════════════════════════════════════════════════════════════════
# Execution timings
# ═══════════════════════════════════════════════════════════════════
@dataclass
class ExecutionSettings:
    account_refresh_s: float = 2.0
    position_refresh_s: float = 2.0
    position_history_refresh_s: float = 30.0
    sl_tick_interval_s: float = 10.0    # StopLossWorker poll
    order_cooldown_s: float = 60.0      # backoff on rejection
    loop_sleep_s: float = 0.05          # connection loop tick (20 Hz)


# ═══════════════════════════════════════════════════════════════════
# Root settings object
# ═══════════════════════════════════════════════════════════════════
@dataclass
class Settings:
    risk: RiskSettings = field(default_factory=RiskSettings)
    position_management: PositionManagementSettings = field(
        default_factory=PositionManagementSettings)
    influence: InfluenceSettings = field(default_factory=InfluenceSettings)
    execution: ExecutionSettings = field(default_factory=ExecutionSettings)

    # global toggle: manage manually-opened positions (magic == 0)
    manage_manual: bool = True


# singleton — imported everywhere as `from src.config.settings import settings`
settings = Settings()


__all__ = [
    "settings",
    "Settings",
    "RiskSettings",
    "PositionManagementSettings",
    "InfluenceSettings",
    "ExecutionSettings",
]