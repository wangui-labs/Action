# src/analysis/flow_1.py
"""
Flow 1: Multi-timeframe fractal analysis.

Runs Fractal + SwingPairer on every requested timeframe in one pass.
Produces a MultiTFAnalysis snapshot with cross-TF helpers.

    from src.analysis.flow_1 import analyze_multi_fractal
    flow = analyze_multi_fractal("XAUUSDm")

    flow.timeframes              # ('1m','5m','15m','1h','4h')
    flow.of("5m").nodes          # nodes on 5m
    flow.latest_swing("5m")      # most recent swing on 5m
    flow.nodes_at(4000.0, pct=0.5)  # cross-TF nodes near a price
    flow.describe()              # log-friendly summary

Public API:
    analyze_multi_fractal(symbol, timeframes=..., months=..., mode=...)
        -> MultiTFAnalysis
"""
from __future__ import annotations

from dataclasses import dataclass

from src.logic.fractals import Candle, Fractal, FractalNode, SwingPair, SwingPairer
from src.pipeline.access import get
from src.pipeline.settings import TF_MINUTES


# Timeframe ordering — lowest to highest. Used for "higher TF bias" helpers.
TF_ORDER: tuple[str, ...] = ("1m", "5m", "15m", "30m", "1h", "2h", "4h", "D", "W")

DEFAULT_TIMEFRAMES: tuple[str, ...] = ("1m", "5m", "15m", "1h", "4h")


# ─────────────────────────────────────────────────────────────────────
# Per-timeframe holder
# ─────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class TimeframeFractal:
    """One timeframe's fractal output. No candles stored — nodes carry their own."""
    timeframe: str
    nodes: tuple[FractalNode, ...]
    pairs: tuple[SwingPair, ...]

    @property
    def node_count(self) -> int: return len(self.nodes)
    @property
    def pair_count(self) -> int: return len(self.pairs)

    @property
    def last_node(self) -> FractalNode | None:
        return self.nodes[-1] if self.nodes else None

    @property
    def last_pair(self) -> SwingPair | None:
        return self.pairs[-1] if self.pairs else None

    def swing_highs(self) -> list[FractalNode]:
        return [n for n in self.nodes if n.swing_type == "swing_high"]

    def swing_lows(self) -> list[FractalNode]:
        return [n for n in self.nodes if n.swing_type == "swing_low"]


# ─────────────────────────────────────────────────────────────────────
# Multi-TF container + helpers
# ─────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class MultiTFAnalysis:
    """
    Snapshot of fractal analysis across several timeframes for one symbol.

    Immutable. Safe to hold, pass around, cache.
    """
    symbol: str
    by_tf: dict[str, TimeframeFractal]

    # ── basic access ────────────────────────────────────────────────
    @property
    def timeframes(self) -> tuple[str, ...]:
        return tuple(self.by_tf.keys())

    def of(self, tf: str) -> TimeframeFractal:
        if tf not in self.by_tf:
            raise KeyError(f"timeframe {tf!r} not in snapshot; have {list(self.by_tf)}")
        return self.by_tf[tf]

    def has(self, tf: str) -> bool:
        return tf in self.by_tf

    # ── per-TF shortcuts ────────────────────────────────────────────
    def nodes(self, tf: str) -> tuple[FractalNode, ...]:
        return self.of(tf).nodes

    def pairs(self, tf: str) -> tuple[SwingPair, ...]:
        return self.of(tf).pairs

    def latest_swing(self, tf: str) -> FractalNode | None:
        return self.of(tf).last_node

    def latest_pair(self, tf: str) -> SwingPair | None:
        return self.of(tf).last_pair

    # ── cross-TF queries ────────────────────────────────────────────
    def nodes_at(self, price: float, pct: float = 0.5) -> dict[str, list[FractalNode]]:
        """
        All nodes whose price is within `pct` percent of `price`, per TF.

        Example: nodes_at(4100.0, pct=0.25) → nodes within ±0.25% of 4100.0.
        Useful for "which TFs agree this level matters?"
        """
        tol = abs(price) * pct / 100.0
        lo, hi = price - tol, price + tol
        return {
            tf: [n for n in tff.nodes if lo <= n.price <= hi]
            for tf, tff in self.by_tf.items()
        }

    def tf_confluence_at(self, price: float, pct: float = 0.5) -> int:
        """
        How many timeframes have at least one node near `price`.

        0 = no TF cares about this level
        1 = one TF has a swing here (weak)
        3+ = strong cross-TF confluence
        """
        return sum(1 for nodes in self.nodes_at(price, pct).values() if nodes)

    def strongest_nodes(self, pct: float = 0.5, min_tfs: int = 2) -> list[dict]:
        """
        Nodes that appear on multiple TFs (within price tolerance).

        Returns list of clusters, each:
            {
                "price": <avg price>,
                "type": "swing_high" | "swing_low",
                "tfs": [<tf names that agree>],
                "nodes": {tf: node},
                "confluence": len(tfs),
            }
        Sorted by confluence (highest first).
        """
        # Start from the highest TF's nodes as anchors, then find TFs that agree
        anchor_tf = max(self.timeframes, key=lambda t: TF_ORDER.index(t) if t in TF_ORDER else -1)
        anchors = self.by_tf[anchor_tf].nodes
        if not anchors:
            return []

        clusters = []
        for anchor in anchors:
            tol = abs(anchor.price) * pct / 100.0
            lo, hi = anchor.price - tol, anchor.price + tol

            agree: dict[str, FractalNode] = {anchor_tf: anchor}
            for tf, tff in self.by_tf.items():
                if tf == anchor_tf:
                    continue
                for n in tff.nodes:
                    if n.swing_type != anchor.swing_type:
                        continue
                    if lo <= n.price <= hi:
                        agree[tf] = n
                        break

            if len(agree) >= min_tfs:
                clusters.append({
                    "price": anchor.price,
                    "type": anchor.swing_type,
                    "tfs": list(agree.keys()),
                    "nodes": agree,
                    "confluence": len(agree),
                })

        clusters.sort(key=lambda c: -c["confluence"])
        return clusters

    def higher_tf_bias(self, ref_tfs: tuple[str, ...] = ("1h", "4h")) -> str:
        """
        Coarse directional bias from the most recent pair on each reference TF.

        Returns 'up', 'down', or 'neutral'.
        'up'  = every ref TF's last pair is an up-pair
        'down' = every ref TF's last pair is a down-pair
        otherwise 'neutral' (mixed or missing).
        """
        directions = set()
        for tf in ref_tfs:
            if not self.has(tf):
                continue
            last = self.latest_pair(tf)
            if last is not None:
                directions.add(last.direction)

        if directions == {"up"}:   return "up"
        if directions == {"down"}: return "down"
        return "neutral"

    # ── summary ────────────────────────────────────────────────────
    def to_record(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframes": {
                tf: {
                    "nodes": tff.node_count,
                    "pairs": tff.pair_count,
                    "last_pair_dir": tff.last_pair.direction if tff.last_pair else None,
                }
                for tf, tff in self.by_tf.items()
            },
            "higher_tf_bias": self.higher_tf_bias(),
        }

    def describe(self) -> str:
        if not self.by_tf:
            return f"MultiTFAnalysis({self.symbol}) — EMPTY"

        lines = [f"MultiTFAnalysis: {self.symbol}"]
        lines.append(f"  {'TF':>4}  {'nodes':>7}  {'pairs':>7}  "
                     f"{'last_dir':>9}  {'last_price':>12}  {'last_time':>16}")
        lines.append("  " + "-" * 68)
        for tf in self.timeframes:
            tff = self.by_tf[tf]
            last = tff.last_pair
            last_dir = last.direction if last else "—"
            last_price = f"{last.end.price:.3f}" if last else "—"
            last_time = last.end.utc_time.strftime("%Y-%m-%d %H:%M") if last else "—"
            lines.append(f"  {tf:>4}  {tff.node_count:>7,}  {tff.pair_count:>7,}  "
                         f"{last_dir:>9}  {last_price:>12}  {last_time:>16}")

        bias = self.higher_tf_bias()
        lines.append(f"  higher-TF bias: {bias}")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────
# Flow entry point
# ─────────────────────────────────────────────────────────────────────
def analyze_multi_fractal(
    symbol: str,
    timeframes: tuple[str, ...] = DEFAULT_TIMEFRAMES,
    months: int = 3,
    mode: str = "native",
    refresh: bool = False,
) -> MultiTFAnalysis:
    """
    Run fractal analysis on every timeframe for `symbol`.

    Parameters
    ----------
    symbol     : MT5 symbol (case-sensitive), e.g. "XAUUSDm"
    timeframes : which timeframes to analyze. Default is (1m, 5m, 15m, 1h, 4h).
    months     : fetch window per TF
    mode       : "native" (MT5 bars per TF) or "bucket" (aggregate from 1m)
    refresh    : bypass cache on this call

    Returns
    -------
    MultiTFAnalysis with one TimeframeFractal per requested TF.
    """
    by_tf: dict[str, TimeframeFractal] = {}

    for tf in timeframes:
        if tf not in TF_MINUTES:
            raise ValueError(f"unknown timeframe {tf!r}, known: {sorted(TF_MINUTES)}")

        candles = get(symbol, tf, months, mode=mode, refresh=refresh)
        if not candles:
            by_tf[tf] = TimeframeFractal(tf, (), ())
            continue

        nodes = Fractal().detect_nodes(candles)
        pairs = SwingPairer(nodes).build()
        by_tf[tf] = TimeframeFractal(tf, tuple(nodes), tuple(pairs))

    return MultiTFAnalysis(symbol=symbol, by_tf=by_tf)


__all__ = [
    "TF_ORDER",
    "DEFAULT_TIMEFRAMES",
    "TimeframeFractal",
    "MultiTFAnalysis",
    "analyze_multi_fractal",
]