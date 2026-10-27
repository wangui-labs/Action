from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence


@dataclass
class Candle:
    index: int  # continuous sequence number — proves the stream has no gaps
    open_time: datetime
    symbol: str
    timeframe: str
    unix_time: int
    utc_time: datetime
    ny_time: datetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: int
    source_indices: tuple[int, ...] = ()


class Fractal:
    """Period-1 (3-candle) fractal detector. Input candles are already closed."""

    @staticmethod
    def is_high(candles: Sequence[Candle], idx: int) -> bool:
        """Swing high: curr.high > left.high and curr.high > right.high."""
        if idx <= 0 or idx >= len(candles) - 1: return False
        return candles[idx].high > candles[idx - 1].high and candles[idx].high > candles[idx + 1].high

    @staticmethod
    def is_low(candles: Sequence[Candle], idx: int) -> bool:
        """Swing low: curr.low < left.low and curr.low < right.low."""
        if idx <= 0 or idx >= len(candles) - 1: return False
        return candles[idx].low < candles[idx - 1].low and candles[idx].low < candles[idx + 1].low

    @classmethod
    def detect_highs(cls, candles: Sequence[Candle]) -> list[int]:
        """All confirmed swing high indices."""
        return [i for i in range(1, len(candles) - 1) if cls.is_high(candles, i)]

    @classmethod
    def detect_lows(cls, candles: Sequence[Candle]) -> list[int]:
        """All confirmed swing low indices."""
        return [i for i in range(1, len(candles) - 1) if cls.is_low(candles, i)]







\





'''




class BarState(Enum):
    CLOSED = "closed"
    AGGREGATED = "aggregated"
    PARTIAL = "partial"
    LIVE = "live"
    
@dataclass
class FractalNode:
    node_id: str
    symbol: str
    timeframe: str
    period: int
    unix_time: int
    utc_time: datetime
    ny_time: datetime
    index: int
    price: float
    swing_type: Literal["swing_high", "swing_low"]
    tick_volume: int
    label: Optional[float] = None


@dataclass
class CandleNode:
    candle_id: str
    candle: Candle
    start_time: datetime
    end_time: datetime
    children: List[str] = field(default_factory=list)
    children_by_tf: Dict[str, List[str]] = field(default_factory=dict)







# ============================================================================
# FRACTAL DETECTOR - BATCH MODE ONLY
# ============================================================================

class BatchFractalDetector:
    """Detect fractals from complete candle list. Period fixed at 2."""
    
    PERIOD = 2
    
    @staticmethod
    def _node_id(candle: Candle, swing_type: str) -> str:
        return f"{candle.symbol}_{candle.timeframe}_p{BatchFractalDetector.PERIOD}_{candle.unix_time}_{swing_type}"
    
    @staticmethod
    def detect(candles: List[Candle]) -> List[FractalNode]:
        """Detect all fractals in candle list"""
        n = BatchFractalDetector.PERIOD
        if len(candles) < (2 * n + 1):
            return []
        
        results = []
        for i in range(n, len(candles) - n):
            curr = candles[i]
            
            if FractalLogic.is_high(candles, i, n):
                results.append(FractalNode(
                    node_id=BatchFractalDetector._node_id(curr, "high"),
                    symbol=curr.symbol, timeframe=curr.timeframe, period=n,
                    unix_time=curr.unix_time, utc_time=curr.utc_time, ny_time=curr.ny_time,
                    index=i, price=curr.high, swing_type="swing_high", tick_volume=curr.tick_volume
                ))
            elif FractalLogic.is_low(candles, i, n):
                results.append(FractalNode(
                    node_id=BatchFractalDetector._node_id(curr, "low"),
                    symbol=curr.symbol, timeframe=curr.timeframe, period=n,
                    unix_time=curr.unix_time, utc_time=curr.utc_time, ny_time=curr.ny_time,
                    index=i, price=curr.low, swing_type="swing_low", tick_volume=curr.tick_volume
                ))
        
        return results


# ============================================================================
# FRACTAL DETECTOR - STREAMING MODE ONLY
# ============================================================================

@dataclass
class _PendingFractal:
    """Internal: fractal waiting for right-side confirmation"""
    node: FractalNode
    confirmed_at: int  # index needed for confirmation


class StreamingFractalDetector:
    """Detect fractals from streaming candles (one at a time). Period fixed at 2."""
    
    PERIOD = 2
    
    def __init__(self):
        self.candles: List[Candle] = []
        self._pending: Dict[int, _PendingFractal] = {}
    
    def _node_id(self, candle: Candle, swing_type: str) -> str:
        return f"{candle.symbol}_{candle.timeframe}_p{StreamingFractalDetector.PERIOD}_{candle.unix_time}_{swing_type}"
    
    def _create_node(self, candle: Candle, idx: int, swing_type: str) -> FractalNode:
        price = candle.high if swing_type == "high" else candle.low
        return FractalNode(
            node_id=self._node_id(candle, swing_type),
            symbol=candle.symbol, timeframe=candle.timeframe, period=StreamingFractalDetector.PERIOD,
            unix_time=candle.unix_time, utc_time=candle.utc_time, ny_time=candle.ny_time,
            index=idx, price=price, 
            swing_type="swing_high" if swing_type == "high" else "swing_low",
            tick_volume=candle.tick_volume
        )
    
    def ingest(self, candle: Candle) -> List[FractalNode]:
        """Process one candle. Returns newly confirmed fractals."""
        self.candles.append(candle)
        idx = len(self.candles) - 1
        n = StreamingFractalDetector.PERIOD
        confirmed = []
        
        # Check for new potential fractal (need left side only)
        check_idx = idx - n
        if check_idx >= n:
            curr = self.candles[check_idx]
            
            if FractalLogic.possible_high(self.candles, check_idx, n):
                node = self._create_node(curr, check_idx, "high")
                self._pending[check_idx] = _PendingFractal(node, check_idx + n)
            elif FractalLogic.possible_low(self.candles, check_idx, n):
                node = self._create_node(curr, check_idx, "low")
                self._pending[check_idx] = _PendingFractal(node, check_idx + n)
        
        # Check pending fractals for confirmation - FIXED
        to_remove = []
        for p_idx, pending in self._pending.items():
            if idx >= pending.confirmed_at:
                # Check the specific type, not OR condition
                is_confirmed = False
                if pending.node.swing_type == "swing_high":
                    is_confirmed = FractalLogic.is_high(self.candles, p_idx, n)
                else:  # swing_low
                    is_confirmed = FractalLogic.is_low(self.candles, p_idx, n)
                
                if is_confirmed:
                    confirmed.append(pending.node)
                to_remove.append(p_idx)
        
        for p_idx in to_remove:
            del self._pending[p_idx]
        
        return confirmed
    
    def reset(self) -> None:
        self.candles = []
        self._pending = {}


# ============================================================================
# HIERARCHY (Same as before, simplified)
# ============================================================================

class MultiTimeframeHierarchy:
    """Bottom-up hierarchy using period 2 fractals only."""
    
    TIMEFRAME_DURATIONS = {
        "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
        "1h": 3600, "2h": 7200, "4h": 14400, "D": 86400, "W": 604800,
    }
    
    TIMEFRAME_ORDER = ["W", "D", "4h", "2h", "1h", "30m", "15m", "5m", "1m"]
    
    def __init__(self):
        self.candles_by_tf: Dict[str, List[Candle]] = {}
        self.fractals_by_tf: Dict[str, List[FractalNode]] = {}
        self.candle_nodes: Dict[str, CandleNode] = {}
        self.fractal_nodes: Dict[str, FractalNode] = {}
    
    def add_candles(self, timeframe: str, candles: List[Candle]) -> None:
        self.candles_by_tf[timeframe] = candles
    
    def detect_fractals(self, timeframe: str) -> None:
        """Detect period-2 fractals for this timeframe"""
        if timeframe not in self.candles_by_tf:
            raise ValueError(f"No candles for {timeframe}")
        fractals = BatchFractalDetector.detect(self.candles_by_tf[timeframe])
        self.fractals_by_tf[timeframe] = fractals
        for f in fractals:
            self.fractal_nodes[f.node_id] = f
    
    def _candle_id(self, candle: Candle) -> str:
        return f"{candle.symbol}_{candle.timeframe}_{candle.unix_time}"
    
    def _get_duration(self, tf: str) -> int:
        return self.TIMEFRAME_DURATIONS.get(tf, 3600)
    
    def _tf_weight(self, tf: str) -> int:
        try:
            return self.TIMEFRAME_ORDER.index(tf)
        except ValueError:
            return 99
    
    def build(self) -> None:
        """Build hierarchy: higher candles collect lower fractals"""
        # Build candle nodes
        self.candle_nodes = {}
        for tf, candles in self.candles_by_tf.items():
            duration = self._get_duration(tf)
            for candle in candles:
                cid = self._candle_id(candle)
                self.candle_nodes[cid] = CandleNode(
                    candle_id=cid, candle=candle,
                    start_time=candle.ny_time,
                    end_time=candle.ny_time + timedelta(seconds=duration)
                )
        
        # Connect parents to children
        sorted_tfs = sorted(self.candles_by_tf.keys(), key=self._tf_weight)
        for i, parent_tf in enumerate(sorted_tfs):
            if parent_tf == sorted_tfs[-1]:
                continue
            lower_tfs = sorted_tfs[i+1:]
            
            for parent_candle in self.candles_by_tf.get(parent_tf, []):
                parent_id = self._candle_id(parent_candle)
                parent_node = self.candle_nodes.get(parent_id)
                if not parent_node:
                    continue
                
                parent_end = parent_node.start_time + timedelta(seconds=self._get_duration(parent_tf))
                
                for child_tf in lower_tfs:
                    for fractal in self.fractals_by_tf.get(child_tf, []):
                        if parent_node.start_time <= fractal.ny_time < parent_end:
                            parent_node.children.append(fractal.node_id)
                            if child_tf not in parent_node.children_by_tf:
                                parent_node.children_by_tf[child_tf] = []
                            parent_node.children_by_tf[child_tf].append(fractal.node_id)
    
    def get_candle_children(self, candle: Candle) -> List[FractalNode]:
        cid = self._candle_id(candle)
        node = self.candle_nodes.get(cid)
        if not node:
            return []
        return [self.fractal_nodes[child_id] for child_id in node.children if child_id in self.fractal_nodes]
    
    def get_alignment(self, fractal: FractalNode, window_minutes: int = 30) -> Dict[str, str]:
        result = {}
        time_window = timedelta(minutes=window_minutes)
        
        for tf, candles in self.candles_by_tf.items():
            if tf == fractal.timeframe:
                continue
            
            for candle in candles:
                start = candle.ny_time
                end = start + timedelta(seconds=self._get_duration(tf))
                
                if start <= fractal.ny_time < end:
                    children = self.get_candle_children(candle)
                    if not children:
                        result[tf] = "NO_FRACTAL"
                        break
                    
                    closest = None
                    closest_diff = time_window
                    for child in children:
                        diff = abs(child.ny_time - fractal.ny_time)
                        if diff < closest_diff:
                            closest_diff = diff
                            closest = child
                    
                    if closest:
                        result[tf] = "ALIGNED" if closest.swing_type == fractal.swing_type else "OPPOSITE"
                    else:
                        result[tf] = "NO_FRACTAL"
                    break
        
        return result


# ============================================================================
# DATA STRUCTURE FOR SWING PAIRS
# ============================================================================

@dataclass
class SwingPair:
    """A complete swing from extreme to extreme"""
    # Identification
    pair_id: str
    symbol: str
    timeframe: str
    
    # The two fractals
    start_fractal: FractalNode   # Can be HIGH or LOW
    end_fractal: FractalNode     # Opposite type
    
    # Direction
    direction: Literal["up", "down"]  # up = low→high, down = high→low
    
    # Amplitude measurements
    price_amplitude: float        # abs(high - low)
    time_duration_minutes: float  # time difference in minutes
    velocity: float               # price_amplitude / time_duration_minutes
    
    # Volume
    total_volume: int             # sum of volumes across both fractals
    volume_weighted_amplitude: float  # price_amplitude * (total_volume / avg_volume)
    
    # Metadata
    start_time: datetime
    end_time: datetime


class SwingPairer:
    """Creates swing pairs with extreme selection (lowest lows, highest highs)"""
    
    def __init__(self, fractals: List[FractalNode], avg_volume: Optional[float] = None):
        self.fractals = fractals
        self.avg_volume = avg_volume or 100.0  # Default fallback
        self.filtered: List[FractalNode] = []
        self.pairs: List[SwingPair] = []
    
    def filter_extremes(self) -> List[FractalNode]:
        """Keep only the lowest low and highest high in consecutive same-type sequences"""
        if not self.fractals:
            return []
        
        filtered = []
        i = 0
        while i < len(self.fractals):
            current = self.fractals[i]
            
            # Look ahead for same-type fractals
            j = i + 1
            while j < len(self.fractals) and self.fractals[j].swing_type == current.swing_type:
                j += 1
            
            # For this block of same-type fractals, find the extreme
            block = self.fractals[i:j]
            if current.swing_type == "swing_low":
                # Keep the lowest low
                best = min(block, key=lambda f: f.price)
            else:
                # Keep the highest high
                best = max(block, key=lambda f: f.price)
            
            filtered.append(best)
            i = j  # Move to next different type
        
        self.filtered = filtered
        return filtered
    
    def pair(self) -> List[SwingPair]:
        """Pair alternating filtered fractals"""
        if not self.filtered:
            self.filter_extremes()
        
        # Handle edge case: not enough fractals for a pair
        if len(self.filtered) < 2:
            self.pairs = []
            return []
        
        pairs = []
        for i in range(len(self.filtered) - 1):
            start = self.filtered[i]
            end = self.filtered[i + 1]
            
            # Must be opposite types
            if start.swing_type == end.swing_type:
                continue
            
            # Determine direction
            if start.swing_type == "swing_low" and end.swing_type == "swing_high":
                direction = "up"
                price_amp = end.price - start.price
            else:
                direction = "down"
                price_amp = start.price - end.price
            
            # Calculate metrics
            time_diff = (end.ny_time - start.ny_time).total_seconds() / 60.0
            velocity = price_amp / time_diff if time_diff > 0 else 0
            total_vol = start.tick_volume + end.tick_volume
            
            # FIXED: Use configurable avg_volume instead of hardcoded 100
            volume_weighted_amp = price_amp * (total_vol / self.avg_volume) if self.avg_volume > 0 else price_amp
            
            pair_id = f"{start.symbol}_{start.timeframe}_{start.unix_time}_{end.unix_time}"
            
            pairs.append(SwingPair(
                pair_id=pair_id,
                symbol=start.symbol,
                timeframe=start.timeframe,
                start_fractal=start,
                end_fractal=end,
                direction=direction,
                price_amplitude=price_amp,
                time_duration_minutes=time_diff,
                velocity=velocity,
                total_volume=total_vol,
                volume_weighted_amplitude=volume_weighted_amp,
                start_time=start.ny_time,
                end_time=end.ny_time
            ))
        
        self.pairs = pairs
        return pairs










# logic/detectors/fractal.py
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional

@dataclass
class Fractal:
    side: Literal["LOW", "HIGH"]
    price: float
    bar_open_time: datetime
    confirmed_at: datetime


def detect_fractal(
    bars: list,          # list of bar dicts, oldest → newest
    i: int,              # index of the middle bar (the candidate)
    current_time: datetime,
) -> Optional[Fractal]:
    """
    A 3-candle fractal: middle bar (i) must be higher/lower than
    its left neighbor (i-1) and right neighbor (i+1).

    In Pine, `high[1]` is the PREVIOUS bar and `high[0]` is the CURRENT bar,
    so the fractal is only known AFTER the next bar prints.
    In Python, that means: only call this when bar i+1 exists.
    """
    if i < 1 or i + 1 >= len(bars):
        return None  # not enough bars on either side yet

    left   = bars[i - 1]
    middle = bars[i]
    right  = bars[i + 1]

    # Up fractal (swing high) — same as Pine: high[1] > high[0] and high[1] > high[2]
    if middle["high"] > left["high"] and middle["high"] > right["high"]:
        return Fractal(
            side="HIGH",
            price=middle["high"],
            bar_open_time=middle["open_time"],
            confirmed_at=current_time,
        )

    # Down fractal (swing low) — same as Pine: low[1] < low[0] and low[1] < low[2]
    if middle["low"] < left["low"] and middle["low"] < right["low"]:
        return Fractal(
            side="LOW",
            price=middle["low"],
            bar_open_time=middle["open_time"],
            confirmed_at=current_time,
        )

    return None

















"""
This is a string, not a comment.

# comment this
#5. The Lineage Table (This Is What You Attach)
#Add a fourth structure alongside S and C:

#text
#LINEAGE  ─  one row per (anchor × tf) edge

# anchor_id   tf     role            state        extreme_price
# A-00042     5m     born            SEALED       4231.50
 #A-00042     15m    is_bar_low      SEALED       4231.50
#A-00042     1h     is_bar_low      PROVISIONAL  4231.50
 #A-00042     4h     is_bar_low      PROVISIONAL  4231.50
 #A-00042     1D     not_yet         —            —            ← 1D bar is far from this price
 #A-00043     5m     born            SEALED       4240.10
# Fractal-Only Anchor System — Working Slice

Let's build the smallest thing that proves the concept: **fractals only, anchor registry + retargeting, with the edge cases handled.** If this works, everything else (bars, consolidation) plugs in the same way.

---

## 1. Data Model

Three tables. That's it. Everything else is derived.

### 1.1 `Anchor` — the physical event

```python
@dataclass(frozen=True)
class Anchor:
    id:           str          # "A-00042", monotonic, never reused
    side:         Literal["LOW", "HIGH"]
    born_tf:      str          # "5m" — lowest TF that first saw it
    price:        float        # the swing price
    bar_open_time: datetime    # open time of the born_tf bar that pivoted
    confirmed_at: datetime     # when the born_tf confirmed it (see §2)
```

**Invariants:**
- `id` is created once. Never mutated.
- `price`, `side`, `born_tf`, `bar_open_time`, `confirmed_at` are immutable after creation.
- No field references a higher TF. Anchors are TF-agnostic.

### 1.2 `LineageEdge` — anchor ↔ TF window mapping

```python
@dataclass
class LineageEdge:
    anchor_id:     str
    tf:            str           # the HIGHER TF this edge is about
    bar_open_time: datetime      # which bar on that TF
    role:          Literal["EXTREME_LOW", "EXTREME_HIGH", "INTERIOR"]
    state:         Literal["PROVISIONAL", "SEALED", "SUPERSEDED"]
    extreme_price: float         # anchor's price, cached for query speed
    updated_at:    datetime
```

**Primary key:** `(anchor_id, tf, bar_open_time)`.
An anchor can have **at most one edge per (tf, bar)**. Two edges for the same triple is a bug.

**Role meaning:**
- `EXTREME_LOW` / `EXTREME_HIGH` → this anchor is *currently* the low/high of that HTF bar
- `INTERIOR` → anchor is inside the bar but not its extreme (kept for lineage queries)
- We only *retarget* `EXTREME_*` edges. `INTERIOR` edges are written once and left alone.

**State meaning:**
- `PROVISIONAL` → HTF bar still open; a deeper anchor could supersede this one
- `SEALED` → HTF bar closed; this anchor **was** the extreme at close (final truth)
- `SUPERSEDED` → a deeper anchor replaced it while bar was open (historical, kept for audit)

### 1.3 `BarWindow` — what the linker needs to know about open HTF bars

```python
@dataclass
class BarWindow:
    tf:            str
    bar_open_time: datetime
    bar_close_time: datetime
    current_low_id:  Optional[str]   # anchor id currently holding the low
    current_high_id: Optional[str]   # anchor id currently holding the high
    is_closed:     bool
```

This is the "pointer" table. It's the only mutable state the linker writes to when retargeting. The `LineageEdge` history is append-only; `BarWindow` holds the *current* answer.

---

## 2. Anchor Creation — "Confirmed Fractal"

A fractal isn't an anchor the moment its pivot bar prints. It's an anchor when **the pattern that defines a fractal completes** on the born TF — i.e., N bars to the right have printed without breaking it.

```python
def maybe_create_anchor(pivot_bar, tf, pattern_params) -> Optional[Anchor]:
    # fractal logic lives in logic/detectors/fractal.py
    # this function only Wraps it in an Anchor if confirmed
    if not fractal_is_confirmed(pivot_bar, pattern_params):
        return None
    return Anchor(
        id=next_id(),
        side=pivot_bar.side,
        born_tf=tf,
        price=pivot_bar.extreme_price,
        bar_open_time=pivot_bar.open_time,
        confirmed_at=now(),          # ← matters for §4
    )
```

**Key timing rule:** `confirmed_at` is *later* than `bar_open_time` by the fractal's confirmation lag (typically N bars). Every downstream edge must respect this — a 1h bar that closed *before* `confirmed_at` cannot have this anchor as its extreme, even if price matches.

---

## 3. Retargeting Logic — The Core Loop

When an anchor is created, it must be considered against **every higher TF bar it falls inside**. Two cases per (anchor, tf):

### 3.1 Case A — HTF bar is still open → possibly retarget

```python
def apply_anchor_to_open_bar(anchor: Anchor, tf: str, bw: BarWindow):
    if bw.is_closed:
        return  # handled in Case B path

    if anchor.confirmed_at >= bw.bar_close_time:
        return  # anchor wasn't confirmed in time to affect this bar's story

    current_id = bw.current_low_id if anchor.side == "LOW" else bw.current_high_id
    if current_id is None:
        _set_extreme(bw, anchor, "PROVISIONAL")
        return

    current = registry.get(current_id)
    if _is_more_extreme(anchor, current):
        _supersede(current, bw, tf)              # old edge → SUPERSEDED
        _set_extreme(bw, anchor, "PROVISIONAL")  # new edge → PROVISIONAL
    else:
        _record_interior(anchor, bw, tf)         # new edge → INTERIOR
```

### 3.2 Case B — HTF bar is already closed → late anchor, historical backfill

```python
def apply_anchor_to_closed_bar(anchor: Anchor, tf: str, bw: BarWindow):
    if anchor.confirmed_at >= bw.bar_close_time:
        return  # legitimately too late — do not backfill
    # anchor was confirmed before close → it *did* influence this bar
    current = registry.get(bw.current_low_id or bw.current_high_id)
    if current is None or _is_more_extreme(anchor, current):
        _seal_supersede(current)                 # old edge → SUPERSEDED
        _set_extreme(bw, anchor, "SEALED")       # new edge → SEALED directly
    else:
        _record_interior(anchor, bw, tf)
```

**Why Case B exists:** late-arriving data (a 5m fractal that confirms 3 bars later) can resolve *after* a 1h bar already closed. Without Case B, that 5m anchor would silently never link to the 1h. Case B closes that gap while still respecting `confirmed_at < bar_close_time`.

### 3.3 The comparison function

```python
def _is_more_extreme(new: Anchor, cur: Anchor) -> bool:
    if new.side != cur.side:
        raise ValueError("side mismatch — caller bug")
    # price tie → earlier confirmation wins; then earlier bar wins
    if new.price == cur.price:
        if new.confirmed_at != cur.confirmed_at:
            return new.confirmed_at < cur.confirmed_at
        return new.bar_open_time < cur.bar_open_time
    return new.price < cur.price if new.side == "LOW" else new.price > cur.price
```

That's the tiebreaker chain. Never silently drop a tie.

---

## 4. Sealing — On HTF Bar Close

When `bar_close_time` hits, freeze the current pointer:

```python
def seal_bar(bw: BarWindow):
    for side in ("LOW", "HIGH"):
        anchor_id = bw.current_low_id if side == "LOW" else bw.current_high_id
        if anchor_id is None:
            continue
        edge = lineage.get(anchor_id, bw.tf, bw.bar_open_time)
        edge.state = "SEALED"
        edge.updated_at = now()
    bw.is_closed = True
```

**Sealed is final.** Nothing retargets a sealed edge. If you ever need to "unseal" (data correction), that's a new anchor + a new edge with `SUPERSEDED` on the old one — never a mutation.

---

## 5. The Edge Cases (This Is Why We're Doing Fractals First)

### Edge case 1 — Bar close race

Anchor `A-100` is confirmed at `14:59:58` on 5m. The 1h bar closes at `15:00:00`. Does `A-100` belong to the 1h bar?

**Rule:** `confirmed_at < bar_close_time` → yes, it belongs. Equality is a *reject* (no backfill at the boundary). Encode it once:

```python
def belongs_to_bar(anchor, bw):
    return anchor.confirmed_at < bw.bar_close_time
```

Not `<=`. Every off-by-one race in this system is this line.

### Edge case 2 — Missing TF data

The 4h feed drops for one bar. The linker sees no 4h bar close event.

**Rule:** sealing is **event-driven, not time-driven**. If no `seal_bar` event arrives, the 4h `BarWindow` stays `is_closed=False` forever (until the next bar close, which seals the current one *and* the missing one in one step). The linker must:

```python
def on_bar_close(tf, bar_open_time):
    # seal any unsealed BarWindow on this tf with bar_close_time <= now
    for bw in windows.get_stale(tf, before=now()):
        seal_bar(bw)
```

So a dropped bar doesn't leak provisional edges — the next close sweeps them up. Nothing silently stays `PROVISIONAL`.

### Edge case 3 — Price ties

Two 5m swing lows at exactly `4231.50`, both confirmed in the same 1h bar.

**Rule:** the tiebreaker in `_is_more_extreme` decides — earliest `confirmed_at` wins. The loser becomes `INTERIOR` (not dropped — its lineage is still queryable). If both have identical `confirmed_at`, earlier `bar_open_time` wins. If both identical, earlier `id` wins (deterministic, never crashes).

### Edge case 4 — Anchor confirmed after *all* higher TF bars it should have touched

A 5m fractal confirms 20 bars late. The 1h bar it belonged to closed 15 bars ago. Case B runs: since `confirmed_at >= bar_close_time`, the anchor is correctly rejected for that 1h bar. It still links to the **current open** 1h bar if its price is more extreme there (Case A), and it links to future bars normally. No retroactive rewriting.

### Edge case 5 — Deeper anchor arrives for a sealed bar

Impossible by construction if `confirmed_at < bar_close_time` gating is enforced — because a *new* anchor with `confirmed_at >= bar_close_time` is Case B-rejected, and a *deeper existing* anchor would already have been seen as an anchor (it was confirmed before close, so it was already processed). If you ever observe this, it's a **data integrity bug**, not a logic bug — log and alert, never auto-fix.

### Edge case 6 — Same anchor, same price, two different bars on the same TF

Rare but possible if TFs misalign (e.g., custom 8h bars). **Rule:** each edge is keyed on `(anchor_id, tf, bar_open_time)`, so two edges coexist cleanly. `BarWindow` pointers keep them separate. No collision.

---

## 6. What This Gives You for Free

With **fractals alone**, the system now answers:

- **"Where did this 1h low come from?"** → query `LineageEdge` by `(tf=1h, bar_open_time=X, role=EXTREME_LOW)`, get `anchor_id`, look up `Anchor`.
- **"What is this 5m swing low influencing right now?"** → query all edges with `anchor_id=A-xxx`, filter `state=PROVISIONAL` → list of (tf, bar) pairs.
- **"Are these multi-TF fractal signals independent?"** → `count(distinct anchor_id) / count(edges)` per bucket = the **Lineage Diversity** metric from the last message, now computed for real.

That last one is the payoff: **before a single weight is tuned, you can already see whether your "confluence" is real or one anchor echoed 5 times.**

---

## 7. Module Sketch

```
logic/lineage/
  anchor_registry.py
    class AnchorRegistry:
      def next_id() -> str
      def create(anchor) -> Anchor
      def get(id) -> Anchor

  lineage_store.py
    class LineageStore:
      def upsert_edge(edge)                    # append-only history
      def get_edges_for_anchor(anchor_id)
      def get_extreme(tf, bar_open_time, side) -> Optional[LineageEdge]

  bar_window.py
    class BarWindowStore:
      def get_or_create(tf, bar_open_time)
      def get_stale(tf, before) -> list[BarWindow]
      def set_pointer(bw, side, anchor_id)

  linker.py
    def on_anchor_created(anchor: Anchor):     # §3 dispatcher
    def on_bar_close(tf, bar_open_time):       # §4 + stale sweep
    def belongs_to_bar(anchor, bw) -> bool     # §5 edge case 1, single source
```

`linker.py` is the only file that mutates state. Everything else is a pure store. That makes the whole thing unit-testable by feeding in `Anchor` + `BarWindow` fixtures and asserting on `LineageEdge` state.

---

## 8. Minimal Test Set (before you wire it into `S`)

Five fixtures that prove the tricky parts:

1. **Basic retarget** — 5m low creates anchor, 1h bar open, anchor becomes `PROVISIONAL`. Deeper 5m low arrives → old edge `SUPERSEDED`, new one `PROVISIONAL`. 1h closes → `SEALED`.
2. **Race at close** — `confirmed_at = bar_close_time - 1s` → accepted. `= bar_close_time` → rejected.
3. **Missing TF** — 4h bar skipped, next 4h close seals the current `BarWindow` and the skipped one.
4. **Tie** — two equal-price lows → earliest `confirmed_at` wins, loser is `INTERIOR`.
5. **Late anchor, closed bar** — 5m fractal confirms after 1h close → not linked to that 1h bar (Case B reject), but links to current 1h bar if more extreme.

If those five pass, the lineage layer is trustworthy and you can bolt on bar-classification and consolidation as additional detectors writing into `S` without touching this code.

---

**Next decision point:** once this is running for fractals, do you want the `INTERIOR` edges to be kept permanently (audit + query, storage grows) or pruned on `SEALED` (storage bounded, historical queries need recomputation)? That's the one storage tradeoff we haven't fixed yet.

"""   


'''
