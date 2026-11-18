# src/conditions/condition_2.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import FrozenSet, Optional
from src.logic.session import KillZone, SessionLabel, SessionResolver


class TradeNotAllowed(Exception):
    pass


@dataclass(frozen=True)
class SessionCondition:
    allowed: FrozenSet[KillZone]

    def __post_init__(self):
        object.__setattr__(self, "allowed", frozenset(self.allowed))
        if not self.allowed:
            raise ValueError("SessionCondition.allowed must be non-empty")

    def allows(self, ts: datetime) -> bool:
        if ts.tzinfo is None:
            raise ValueError("naive datetime — pass a tz-aware timestamp")
        return SessionResolver.resolve(ts).killzone in self.allowed

    def assert_allowed(self, ts: datetime) -> SessionLabel:
        if ts.tzinfo is None:
            raise ValueError("naive datetime — pass a tz-aware timestamp")
        label = SessionResolver.resolve(ts)
        if label.killzone not in self.allowed:
            raise TradeNotAllowed(
                f"killzone={label.killzone.value} not in "
                f"{sorted(z.value for z in self.allowed)} at {ts.isoformat()}"
            )
        return label

    def reason(self, ts: datetime) -> Optional[str]:
        label = SessionResolver.resolve(ts)
        return None if label.killzone in self.allowed else (
            f"outside allowed sessions (now={label.killzone.value}, "
            f"allowed={sorted(z.value for z in self.allowed)})"
        )


class Condition2:
    def __init__(self, allowed, name: str = "condition_2", enforce: bool = False):
        self.name = name
        self.enforce = enforce
        self._session = SessionCondition(allowed=allowed)

    def check(self, data: dict) -> bool:
        ts = data.get("ny_time")
        if ts is None:
            if self.enforce:
                raise TradeNotAllowed(f"{self.name}: missing 'ny_time'")
            return False
        if self.enforce:
            self._session.assert_allowed(ts)
            return True
        return self._session.allows(ts)

    def reason(self, data: dict) -> Optional[str]:
        ts = data.get("ny_time")
        return f"{self.name}: missing 'ny_time'" if ts is None else self._session.reason(ts)

    def build_trade_plan(self, data: dict, symbol: Optional[str] = None) -> Optional[dict]:
        s = symbol or data.get("symbol")
        if not s:
            raise KeyError(f"{self.name}: no symbol (arg or data['symbol'])")
        return {"symbol": s.upper(), "condition": self.name} if self.check(data) else None