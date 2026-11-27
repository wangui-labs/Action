# src/logic/m_average.py
"""
Two-moving-average trend locator. Stateless.

    from src.logic.m_average import MATrendConfig, MAConfig, trend, allows

    cfg = MATrendConfig(
        fast=MAConfig(period=20,  ma_type="ema", price="close"),
        slow=MAConfig(period=200, ma_type="ema", price="close"),
    )
    t = trend(candles, cfg)
    if allows(t, "BUY"):
        ...
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Sequence

import numpy as np

# ------------------------------------------------------------------ types
PriceSrc = Literal["open", "close", "hl2", "hlc3", "ohlc4", "wclose"]
MAType   = Literal["sma", "ema", "wma", "hma", "kama", "adaptive"]


# ------------------------------------------------------------------ configs
@dataclass(frozen=True, slots=True)
class MAConfig:
    period:  int     = 50
    ma_type: MAType  = "ema"
    price:   PriceSrc = "close"
    shift:   int     = 0            # bars back; 0 = latest


@dataclass(frozen=True, slots=True)
class MATrendConfig:
    fast: MAConfig = MAConfig(period=20,  ma_type="ema")
    slow: MAConfig = MAConfig(period=200, ma_type="ema")
    slope_lookback: int = 3


# ------------------------------------------------------------------ results
@dataclass(frozen=True, slots=True)
class MATrend:
    bias:     int           # +1 close>slow, -1 close<slow, 0 equal
    cross:    int           # +1 fast>slow,  -1 fast<slow,  0 equal
    slope:    float         # fast MA slope (% / lookback bars)
    distance: float         # (close - fast) / fast
    aligned:  bool          # cross agrees with slope
    fast_ma:  float
    slow_ma:  float
    reason:   str


@dataclass(frozen=True, slots=True)
class CrossEvent:
    index:     int          # bar index in the input sequence
    unix:      int          # candle.unix_time if present, else -1
    ny_time:   str          # ISO string if available, else ""
    direction: int          # +1 bull cross, -1 bear cross
    fast:      float
    slow:      float
    gap:       float        # (fast - slow) / slow
    close:     float


# ------------------------------------------------------------------ price sources
def _price_series(candles: Sequence, src: PriceSrc) -> np.ndarray:
    o = np.fromiter((c.open  for c in candles), dtype=float, count=len(candles))
    h = np.fromiter((c.high  for c in candles), dtype=float, count=len(candles))
    l = np.fromiter((c.low   for c in candles), dtype=float, count=len(candles))
    c_ = np.fromiter((c.close for c in candles), dtype=float, count=len(candles))

    if src == "open":   return o
    if src == "close":  return c_
    if src == "hl2":    return (h + l) / 2.0
    if src == "hlc3":   return (h + l + c_) / 3.0
    if src == "ohlc4":  return (o + h + l + c_) / 4.0
    if src == "wclose": return (h + l + 2.0 * c_) / 4.0
    raise ValueError(f"unknown price source: {src!r}")


# ------------------------------------------------------------------ MA kernels
def _sma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(x, np.nan, dtype=float)
    if n <= 0 or len(x) < n:
        return out
    cs = np.cumsum(np.insert(x, 0, 0.0))
    out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def _ema(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(x, np.nan, dtype=float)
    if n <= 0 or len(x) < n:
        return out
    a = 2.0 / (n + 1.0)
    out[n - 1] = x[:n].mean()
    for i in range(n, len(x)):
        out[i] = a * x[i] + (1.0 - a) * out[i - 1]
    return out


def _wma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(x, np.nan, dtype=float)
    if n <= 0 or len(x) < n:
        return out
    w = np.arange(1, n + 1, dtype=float)
    wsum = w.sum()
    for i in range(n - 1, len(x)):
        out[i] = float(np.dot(x[i - n + 1:i + 1], w) / wsum)
    return out


def _hma(x: np.ndarray, n: int) -> np.ndarray:
    half = max(1, int(n / 2))
    sq   = max(1, int(np.sqrt(n)))
    return _wma(2.0 * _wma(x, half) - _wma(x, n), sq)


def _kama(x: np.ndarray, n: int, fast: int = 2, slow: int = 30) -> np.ndarray:
    out = np.full_like(x, np.nan, dtype=float)
    if n <= 1 or len(x) <= n:
        return out
    out[n] = x[: n + 1].mean()
    a_fast, a_slow = 2.0 / (fast + 1.0), 2.0 / (slow + 1.0)
    for i in range(n + 1, len(x)):
        change     = abs(x[i] - x[i - n])
        volatility = float(np.abs(np.diff(x[i - n:i + 1])).sum())
        er = 0.0 if volatility == 0 else change / volatility
        sc = (er * (a_fast - a_slow) + a_slow) ** 2
        out[i] = out[i - 1] + sc * (x[i] - out[i - 1])
    return out


_KERNELS = {
    "sma":      _sma,
    "ema":      _ema,
    "wma":      _wma,
    "hma":      _hma,
    "kama":     _kama,
    "adaptive": _kama,
}


def _ma(x: np.ndarray, cfg: MAConfig) -> np.ndarray:
    k = _KERNELS.get(cfg.ma_type)
    if k is None:
        raise ValueError(f"unknown ma_type: {cfg.ma_type!r}")
    return k(x, cfg.period)


# ------------------------------------------------------------------ public API
def ma(candles: Sequence, cfg: MAConfig) -> np.ndarray:
    """Single MA series. NaN where undefined."""
    if not candles:
        return np.array([], dtype=float)
    px = _price_series(candles, cfg.price)
    series = _ma(px, cfg)
    if cfg.shift > 0:
        series = np.concatenate([np.full(cfg.shift, np.nan), series[:-cfg.shift]])
    return series


def trend(candles: Sequence, cfg: MATrendConfig = MATrendConfig()) -> Optional[MATrend]:
    """Stateless trend snapshot. None if not enough bars."""
    need = (max(cfg.fast.period, cfg.slow.period)
            + cfg.fast.shift + cfg.slow.shift + cfg.slope_lookback + 1)
    if len(candles) < need:
        return None

    fast = ma(candles, cfg.fast)
    slow = ma(candles, cfg.slow)
    last_close = float(candles[-1].close)

    f_last, s_last = fast[-1], slow[-1]
    if not np.isfinite(f_last) or not np.isfinite(s_last):
        return None

    cross = 1 if f_last > s_last else -1 if f_last < s_last else 0
    bias  = 1 if last_close > s_last else -1 if last_close < s_last else 0

    lb = cfg.slope_lookback
    f_prev = fast[-1 - lb]
    slope = 0.0 if not np.isfinite(f_prev) or f_prev == 0 else float((f_last - f_prev) / f_prev)
    distance = float((last_close - f_last) / f_last) if f_last else 0.0
    aligned = (cross > 0 and slope > 0) or (cross < 0 and slope < 0)

    if bias > 0 and cross > 0 and slope > 0:
        why = "bull: close>slow, fast>slow, fast rising"
    elif bias < 0 and cross < 0 and slope < 0:
        why = "bear: close<slow, fast<slow, fast falling"
    elif cross == 0:
        why = "flat: fast==slow"
    else:
        why = f"mixed: bias={bias:+d} cross={cross:+d} slope={slope:+.5f}"

    return MATrend(
        bias=bias, cross=cross, slope=slope, distance=distance,
        aligned=aligned, fast_ma=float(f_last), slow_ma=float(s_last),
        reason=why,
    )


# ------------------------------------------------------------------ one-line gates
def side_ok(t: Optional[MATrend], side: str, *, require_aligned: bool = True) -> bool:
    """True if `t` permits trading `side` ('BUY'/'SELL'). None → False."""
    if t is None:
        return False
    if require_aligned and not t.aligned:
        return False
    if side == "BUY":
        return t.bias >= 0 and t.cross >= 0
    if side == "SELL":
        return t.bias <= 0 and t.cross <= 0
    return False


def allows(t: Optional[MATrend], side: str, *, require_aligned: bool = True) -> bool:
    """Alias of `side_ok` — reads nicer at call sites: `if allows(t, side):`"""
    return side_ok(t, side, require_aligned=require_aligned)


# ------------------------------------------------------------------ cross history
def ma_cross_events(
    candles: Sequence,
    cfg: MATrendConfig = MATrendConfig(),
    *,
    min_gap: float = 0.0,
) -> list[CrossEvent]:
    """
    Every bar where fast crossed slow. Stateless.
    `min_gap` filters noise: emit only if |(fast-slow)/slow| >= min_gap.
    """
    if not candles:
        return []

    fast = ma(candles, cfg.fast)
    slow = ma(candles, cfg.slow)
    n = min(len(fast), len(slow))
    if n < 2:
        return []

    events: list[CrossEvent] = []
    prev_sign: Optional[int] = None
    for i in range(n):
        f, s = fast[i], slow[i]
        if not (np.isfinite(f) and np.isfinite(s)):
            continue
        sign = 1 if f > s else -1 if f < s else 0
        if sign == 0:
            continue
        if prev_sign is not None and sign != prev_sign:
            gap = (f - s) / s if s else 0.0
            if abs(gap) >= min_gap:
                c = candles[i]
                ny = getattr(c, "ny_time", None)
                events.append(CrossEvent(
                    index=i,
                    unix=int(getattr(c, "unix_time", -1)),
                    ny_time=ny.isoformat() if hasattr(ny, "isoformat") else "",
                    direction=sign,
                    fast=float(f),
                    slow=float(s),
                    gap=float(gap),
                    close=float(c.close),
                ))
        prev_sign = sign
    return events


__all__ = [
    "MAConfig", "MATrendConfig", "MATrend", "CrossEvent",
    "ma", "trend", "allows", "side_ok", "ma_cross_events",
    "PriceSrc", "MAType",
]