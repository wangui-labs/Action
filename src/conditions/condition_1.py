# src/conditions/condition_1.py
"""
Condition1 — the calculation authority for SL/TP, breakeven, and trailing.

Owns every formula StopLossWorker needs. The worker calls these methods and
applies the result to the broker; it does no math of its own.

Policy sources (read inside each method, no constructor args):
  • settings.risk                  → target_risk_usd, rr_default, rr_trend_aligned
  • settings.position_management   → be_at_r, be_lock_pct, trail_at_r,
                                     trail_distance_r, stops_level_buffer,
                                     breach_multiple, tp_breach_multiple
  • auto_trade_config              → per-symbol overrides, mode

Snapshot caching: call begin_tick() at the top of a worker tick and
end_tick() in finally. All snapshot() calls inside the tick are memoized,
so one MarketWatch hit per symbol per tick.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.config.auto_trade import auto_trade_config
from src.config.settings import settings
from src.conditions.condition_0 import Condition0
from src.interface.marketwatch import MarketWatch, SymbolSnapshot


# ═══════════════════════════════════════════════════════════════════════
# Data shapes (consumed by callers of build_trade_plan)
# ═══════════════════════════════════════════════════════════════════════
class Side(str, Enum):
    LONG = "long"
    SHORT = "short"

    @classmethod
    def from_mt5(cls, type_int: int) -> "Side":
        return cls.LONG if type_int == 0 else cls.SHORT

    @property
    def sign(self) -> int:
        return 1 if self is Side.LONG else -1


@dataclass(frozen=True)
class StopLoss:
    price: float
    entry: float
    side: Side
    points: float
    basis: str = "dollar_risk"


@dataclass(frozen=True)
class TakeProfit:
    price: float
    points: float
    basis: str = "rr"


@dataclass(frozen=True)
class TradePlan:
    symbol: str
    condition: str
    side: Side
    entry: float
    sl_price: float
    sl_points: float
    tp_price: float
    tp_points: float
    rr: float
    lot_size: float
    risk_usd: float
    reward_usd: float
    magic: int
    mode: str
    trend_aligned: bool = False


# ═══════════════════════════════════════════════════════════════════════
# Condition1
# ═══════════════════════════════════════════════════════════════════════
class Condition1:
    _SIDE_ALIAS = {
        "buy": Side.LONG, "long": Side.LONG,
        "sell": Side.SHORT, "short": Side.SHORT,
    }

    def __init__(
        self,
        marketwatch: MarketWatch,
        sizing: Condition0,
        max_sl_points: Optional[float] = None,
        name: str = "condition_1",
    ):
        self.name = name
        self.marketwatch = marketwatch
        self.sizing = sizing
        self.max_sl_points = max_sl_points
        self._snap_cache: dict[str, SymbolSnapshot] = {}

    # ── per-tick snapshot cache ─────────────────────────────────────
    def begin_tick(self) -> None:
        self._snap_cache.clear()

    def end_tick(self) -> None:
        self._snap_cache.clear()

    def _info(self, symbol: str) -> SymbolSnapshot:
        snap = self._snap_cache.get(symbol)
        if snap is None:
            snap = self.marketwatch.snapshot(symbol)
            self._snap_cache[symbol] = snap
        return snap

    # ── small helpers ───────────────────────────────────────────────
    def _parse_side(self, raw) -> Side:
        if isinstance(raw, str):
            key = raw.strip().lower()
            if key not in self._SIDE_ALIAS:
                raise ValueError(f"side must be one of {sorted(self._SIDE_ALIAS)}, got {raw!r}")
            return self._SIDE_ALIAS[key]
        return Side.from_mt5(int(raw))

    @staticmethod
    def _pip_value_per_lot(info: SymbolSnapshot) -> float:
        return info.tick_value * (info.pip_size / info.tick_size)

    @staticmethod
    def _points_to_price(points: float, info: SymbolSnapshot, side: Side) -> float:
        return points * info.tick_size * side.sign

    def _risk_usd(self, symbol: str) -> float:
        per = auto_trade_config.get_settings(symbol).get("target_risk_usd")
        return float(per if per is not None else settings.risk.target_risk_usd)

    # ── dollar-risk formula (was condition_00) ──────────────────────
    def dollar_risk_points(self, risk_usd: float, lot: float, symbol: str) -> Optional[float]:
        info = self._info(symbol)
        denom = info.tick_value * max(lot, 1e-9)
        if denom <= 0:
            return None
        pts = risk_usd / denom
        return min(pts, self.max_sl_points) if self.max_sl_points else pts

    # ── SL sizing dispatch (dollar-risk only) ───────────────────────
    def _sl_points_for(self, lot: float, symbol: str) -> float:
        pts = self.dollar_risk_points(self._risk_usd(symbol), lot, symbol)
        if pts is None:
            raise ValueError(f"{self.name}: invalid tick_value/lot for {symbol}")
        return pts

    # ── SL / TP construction ────────────────────────────────────────
    def _stop(self, entry: float, side: Side, sl_points: float, symbol: str) -> StopLoss:
        info = self._info(symbol)
        price = entry - self._points_to_price(sl_points, info, side)
        return StopLoss(price=round(price, info.digits), entry=entry, side=side,
                        points=round(sl_points, 1))

    def _target(self, entry: float, side: Side, tp_points: float, symbol: str) -> TakeProfit:
        info = self._info(symbol)
        price = entry + self._points_to_price(tp_points, info, side)
        return TakeProfit(price=round(price, info.digits), points=round(tp_points, 1))

    def _rr(self, trend_aligned: bool, symbol: Optional[str] = None) -> float:
        key = "rr_trend_aligned" if trend_aligned else "rr_default"
        if symbol:
            per = auto_trade_config.get_settings(symbol)
            if key in per:
                return float(per[key])
        return settings.risk.rr_trend_aligned if trend_aligned else settings.risk.rr_default

    # ═══════════════════════════════════════════════════════════════
    # Public API — sizing / plan
    # ═══════════════════════════════════════════════════════════════
    def check(self, data: dict) -> bool:
        try:
            symbol = data["symbol"]
            lot = self.sizing.size(symbol)
            self._parse_side(data["side"])
            info = self._info(symbol)
            sl_pts = self._sl_points_for(lot, symbol)
            if self.max_sl_points and sl_pts > self.max_sl_points:
                return False
            sl_usd = sl_pts * (info.tick_size / info.pip_size) * self._pip_value_per_lot(info) * lot
            return sl_usd <= self._risk_usd(symbol) * 2.0
        except (KeyError, ValueError, PermissionError):
            return False

    def build_trade_plan(self, data: dict, symbol: Optional[str] = None,
                         trend_aligned: bool = False) -> Optional[TradePlan]:
        symbol = symbol or data.get("symbol") or ""
        if not symbol:
            return None
        try:
            lot = self.sizing.size(symbol)
        except (KeyError, PermissionError):
            return None

        side = self._parse_side(data["side"])
        entry = float(data["price"])
        info = self._info(symbol)

        sl_points = self._sl_points_for(lot, symbol)
        rr = self._rr(trend_aligned, symbol)
        tp_points = sl_points * rr
        sl = self._stop(entry, side, sl_points, symbol)
        tp = self._target(entry, side, tp_points, symbol)

        pip_val = self._pip_value_per_lot(info)
        risk_usd = sl_points * (info.tick_size / info.pip_size) * pip_val * lot
        reward_usd = tp_points * (info.tick_size / info.pip_size) * pip_val * lot

        return TradePlan(
            symbol=symbol, condition=self.name, side=side, entry=entry,
            sl_price=sl.price, sl_points=sl.points,
            tp_price=tp.price, tp_points=tp.points,
            rr=round(rr, 2), lot_size=lot,
            risk_usd=round(risk_usd, 2), reward_usd=round(reward_usd, 2),
            magic=settings.influence.magic,
            mode=auto_trade_config.get_settings(symbol)["mode"],
            trend_aligned=trend_aligned,
        )

    # ═══════════════════════════════════════════════════════════════
    # Public API — worker-facing calculations (plain values, no objects)
    # ═══════════════════════════════════════════════════════════════
    def plan_for_position(self, pos: dict) -> Optional[dict]:
        """Return {'sl_price','tp_price','sl_points','tp_points'} or None."""
        plan = self.build_trade_plan({
            "symbol": pos["symbol"],
            "side": "buy" if pos["type"] == 0 else "sell",
            "price": pos["price_open"],
        })
        if plan is None:
            return None
        return {
            "sl_price": plan.sl_price, "tp_price": plan.tp_price,
            "sl_points": plan.sl_points, "tp_points": plan.tp_points,
        }

    def is_sl_breached(self, pos: dict, sl_price: float) -> bool:
        info = self._info(pos["symbol"])
        tick = self.marketwatch.tick(pos["symbol"])
        is_long = pos["type"] == 0
        current = tick["bid"] if is_long else tick["ask"]
        return (is_long and sl_price >= current) or (not is_long and sl_price <= current)

    def is_tp_breached(self, pos: dict, tp_price: float) -> bool:
        info = self._info(pos["symbol"])
        tick = self.marketwatch.tick(pos["symbol"])
        is_long = pos["type"] == 0
        current = tick["bid"] if is_long else tick["ask"]
        return (is_long and tp_price <= current) or (not is_long and tp_price >= current)

    def widened_sl_price(self, pos: dict, multiple: Optional[float] = None) -> Optional[float]:
        m = multiple if multiple is not None else settings.position_management.breach_multiple
        widened_risk = self._risk_usd(pos["symbol"]) * m
        lot = float(pos.get("volume", 0.0))
        pts = self.dollar_risk_points(widened_risk, lot, pos["symbol"])
        if pts is None:
            return None
        info = self._info(pos["symbol"])
        tick = self.marketwatch.tick(pos["symbol"])
        is_long = pos["type"] == 0
        current = tick["bid"] if is_long else tick["ask"]
        distance = pts * info.tick_size
        return current - distance if is_long else current + distance

    def escalated_tp_price(self, pos: dict, multiple: Optional[float] = None) -> Optional[float]:
        m = multiple if multiple is not None else settings.position_management.tp_breach_multiple
        base_rr = self._rr(False, pos["symbol"])
        escalated_rr = base_rr * m
        lot = float(pos.get("volume", 0.0))
        sl_pts = self.dollar_risk_points(self._risk_usd(pos["symbol"]), lot, pos["symbol"])
        if sl_pts is None:
            return None
        info = self._info(pos["symbol"])
        side = Side.from_mt5(pos["type"])
        return round(pos["price_open"] + sl_pts * escalated_rr * info.tick_size * side.sign, info.digits)

    def r_multiple(self, pos: dict, price: float) -> float:
        entry = pos["price_open"]
        initial = abs(entry - pos["sl"]) if pos["sl"] > 0 else 0.0
        if initial <= 0:
            return 0.0
        is_long = pos["type"] == 0
        return ((price - entry) if is_long else (entry - price)) / initial

    def breakeven_sl(self, pos: dict, price: float) -> Optional[float]:
        pm = settings.position_management
        if self.r_multiple(pos, price) < pm.be_at_r:
            return None
        info = self._info(pos["symbol"])
        initial = abs(pos["price_open"] - pos["sl"]) if pos["sl"] > 0 else 0.0
        lock = initial * pm.be_lock_pct
        is_long = pos["type"] == 0
        return round(pos["price_open"] + (lock if is_long else -lock), info.digits)

    def trailing_sl(self, pos: dict, price: float) -> Optional[float]:
        pm = settings.position_management
        if self.r_multiple(pos, price) < pm.trail_at_r:
            return None
        info = self._info(pos["symbol"])
        initial = abs(pos["price_open"] - pos["sl"]) if pos["sl"] > 0 else 0.0
        trail = pm.trail_distance_r * initial
        is_long = pos["type"] == 0
        return round(price - (trail if is_long else -trail), info.digits)

    def better_sl(self, pos: dict, candidate: float) -> bool:
        info = self._info(pos["symbol"])
        is_long = pos["type"] == 0
        current = pos["sl"]
        if current <= 0:
            return True
        if abs(candidate - current) < info.tick_size * 0.5:
            return False
        return candidate > current if is_long else candidate < current

    def min_stop_distance(self, symbol: str) -> float:
        info = self._info(symbol)
        return (info.stops_level_points or 10) * info.point * settings.position_management.stops_level_buffer