# src/pipeline/settings.py
"""
All configurable data for the pipeline. One file, one source of truth.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────
# Timeframes we actually fetch (native bars from MT5)
# ─────────────────────────────────────────────────────────────────────
TF_MINUTES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "D": 1440,
}

MT5_TIMEFRAME: dict[str, str] = {
    "1m": "TIMEFRAME_M1",
    "5m": "TIMEFRAME_M5",
    "15m": "TIMEFRAME_M15",
    "1h": "TIMEFRAME_H1",
    "4h": "TIMEFRAME_H4",
    "D": "TIMEFRAME_D1",
}

# Ordered list used by batch fetches — cheapest first, so logs read nicely.
FETCH_TFS: tuple[str, ...] = ("1m", "5m", "15m", "1h", "4h", "D")


# ─────────────────────────────────────────────────────────────────────
# Fetch defaults
# ─────────────────────────────────────────────────────────────────────
DEFAULT_MONTHS: int = 3
FALLBACK_SYMBOL: str = "XAUUSDm"


# ─────────────────────────────────────────────────────────────────────
# Pipeline config (per-run)
# ─────────────────────────────────────────────────────────────────────
@dataclass
class PipelineConfig:
    symbol: str | None = None
    months: int = DEFAULT_MONTHS
    timeframes: tuple[str, ...] = FETCH_TFS

    def validate(self) -> None:
        if self.months <= 0:
            raise ValueError(f"months must be > 0, got {self.months}")
        unknown = [tf for tf in self.timeframes if tf not in TF_MINUTES]
        if unknown:
            raise ValueError(f"unknown timeframes {unknown}, known: {sorted(TF_MINUTES)}")


# ─────────────────────────────────────────────────────────────────────
# Logging — used by src/pipeline/__init__.py
# ─────────────────────────────────────────────────────────────────────
LOG_DIR: Path = Path(__file__).resolve().parents[2] / "src" / "logs"
LOG_FILE: Path = LOG_DIR / "pipeline.log"
LOG_LEVEL: str = "INFO"
LOG_FORMAT: str = "%(asctime)s  %(levelname)-7s  %(name)-24s  %(message)s"
LOG_DATEFMT: str = "%Y-%m-%d %H:%M:%S"