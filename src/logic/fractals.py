# src/logic/fractals.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional, Sequence

from src.data_structures.structures import Candle


# ---------------------------------------------------------------------------
# FractalNode — thin pointer to a Candle + detector output only
# ---------------------------------------------------------------------------
SwingType = Literal["swing_high", "swing_low"]


@dataclass(frozen=True)
class FractalNode:
    node_id: str
    candle: Candle
    swing_type: SwingType
    period: int

    @property
    def price(self) -> float:
        return self.candle.high if self.swing_type == "swing_high" else self.candle.low

    @property
    def index(self) -> int:                      return self.candle.index
    @property
    def symbol(self) -> str:                     return self.candle.symbol
    @property
    def timeframe(self) -> str:                  return self.candle.timeframe
    @property
    def open_time(self) -> datetime:             return self.candle.open_time
    @property
    def ny_time(self) -> datetime:               return self.candle.ny_time
    @property
    def utc_time(self) -> datetime:              return self.candle.utc_time
    @property
    def unix_time(self) -> int:                  return self.candle.unix_time
    @property
    def tick_volume(self) -> int:                return self.candle.tick_volume
    @property
    def source_indices(self) -> tuple[int, ...]: return self.candle.source_indices


# ---------------------------------------------------------------------------
# Fractal — detector + node producer
# ---------------------------------------------------------------------------
class Fractal:
    """Period-1 (3-candle) fractal detector. Input candles are already closed."""

    def __init__(self, period: int = 1) -> None:
        self.period = period

    @staticmethod
    def is_high(candles: Sequence[Candle], idx: int) -> bool:
        if idx <= 0 or idx >= len(candles) - 1:
            return False
        return (candles[idx].high > candles[idx - 1].high
                and candles[idx].high > candles[idx + 1].high)

    @staticmethod
    def is_low(candles: Sequence[Candle], idx: int) -> bool:
        if idx <= 0 or idx >= len(candles) - 1:
            return False
        return (candles[idx].low < candles[idx - 1].low
                and candles[idx].low < candles[idx + 1].low)

    @classmethod
    def detect_highs(cls, candles: Sequence[Candle]) -> list[int]:
        return [i for i in range(1, len(candles) - 1) if cls.is_high(candles, i)]

    @classmethod
    def detect_lows(cls, candles: Sequence[Candle]) -> list[int]:
        return [i for i in range(1, len(candles) - 1) if cls.is_low(candles, i)]

    def detect_nodes(self, candles: Sequence[Candle]) -> list[FractalNode]:
        """Return confirmed swing points in chronological order."""
        highs = set(self.detect_highs(candles))
        lows = set(self.detect_lows(candles))

        nodes: list[FractalNode] = []
        for r, c in enumerate(candles):
            if r in highs:
                nodes.append(FractalNode(
                    node_id=f"{c.symbol}_{c.timeframe}_{c.index}_H",
                    candle=c, swing_type="swing_high", period=self.period,
                ))
            elif r in lows:
                nodes.append(FractalNode(
                    node_id=f"{c.symbol}_{c.timeframe}_{c.index}_L",
                    candle=c, swing_type="swing_low", period=self.period,
                ))
        return nodes


# ---------------------------------------------------------------------------
# SwingPair — one completed move: extreme → opposite extreme
# ---------------------------------------------------------------------------
Direction = Literal["up", "down"]


@dataclass(frozen=True)
class SwingPair:
    """One completed swing between two alternating FractalNodes."""
    start: FractalNode              # low or high
    end: FractalNode                # opposite type
    direction: Direction            # "up" = low→high, "down" = high→low

    @property
    def pair_id(self) -> str:
        return (f"{self.start.symbol}_{self.start.timeframe}_"
                f"{self.start.index}_{self.end.index}")

    @property
    def symbol(self) -> str:    return self.start.symbol
    @property
    def timeframe(self) -> str: return self.start.timeframe

    @property
    def start_time(self) -> datetime: return self.start.ny_time
    @property
    def end_time(self) -> datetime:   return self.end.ny_time
    @property
    def time_duration_minutes(self) -> float:
        return (self.end.ny_time - self.start.ny_time).total_seconds() / 60.0

    @property
    def price_amplitude(self) -> float:
        return abs(self.end.price - self.start.price)

    @property
    def velocity(self) -> float:
        t = self.time_duration_minutes
        return self.price_amplitude / t if t > 0 else 0.0

    @property
    def total_volume(self) -> int:
        return self.start.tick_volume + self.end.tick_volume


# ---------------------------------------------------------------------------
# SwingPairer — collapse same-type runs, then pair adjacent opposites
# ---------------------------------------------------------------------------
class SwingPairer:
    """Builds SwingPairs from an ordered (chronological) list of FractalNodes."""

    def __init__(self, nodes: Sequence[FractalNode],
                 avg_volume: Optional[float] = None) -> None:
        self.nodes = list(nodes)
        self.avg_volume = avg_volume
        self.filtered: list[FractalNode] = []
        self.pairs: list[SwingPair] = []

    def filter_extremes(self) -> list[FractalNode]:
        """Collapse consecutive same-type nodes into one extreme."""
        if not self.nodes:
            self.filtered = []
            return self.filtered

        out: list[FractalNode] = []
        i, n = 0, len(self.nodes)
        while i < n:
            cur = self.nodes[i]
            j = i + 1
            while j < n and self.nodes[j].swing_type == cur.swing_type:
                j += 1
            block = self.nodes[i:j]
            best = (min(block, key=lambda x: x.price)
                    if cur.swing_type == "swing_low"
                    else max(block, key=lambda x: x.price))
            out.append(best)
            i = j

        self.filtered = out
        return out

    def pair(self) -> list[SwingPair]:
        """Join adjacent opposite-type extremes into SwingPairs."""
        if not self.filtered:
            self.filter_extremes()

        pairs: list[SwingPair] = []
        for a, b in zip(self.filtered, self.filtered[1:]):
            if a.swing_type == b.swing_type:
                continue
            direction: Direction = "up" if a.swing_type == "swing_low" else "down"
            pairs.append(SwingPair(start=a, end=b, direction=direction))

        self.pairs = pairs
        return pairs

    def build(self) -> list[SwingPair]:
        """filter_extremes → pair, in one call."""
        self.filter_extremes()
        return self.pair()



    """
    The logic, as comments you can paste into the files later
Here's the design rationale written as comments — so future-you (or a teammate) can read why the code is shaped this way without re-deriving it.

src/logic/labels.py — stateless side
python
# src/logic/labels.py
"""
Stateless labeling rules for fractal swing nodes.

WHY THIS FILE EXISTS
--------------------
The labeling of swing nodes has two concerns that must not be mixed:

  1. CLASSIFICATION (this file) — pure question:
       "Given a price and the current reference price, what kind of
        event is this, and what label does this node get *right now*?"

  2. STATE MACHINE (labeler.py) — mutable question:
       "Walk the chronological nodes, hold the current reference, and
        when an event says 'demote', rewrite the previous reference's
        label retroactively."

This file owns ONLY concern #1. It is pure: no state, no mutation,
no knowledge of node_id, no knowledge of history beyond the single
(reference_price) argument. Every function here is a total function
of its arguments and can be unit-tested with a table of
(price, reference) -> expected event. No fixtures, no sequences.

THE RULE (low side; high side is the mirror image)
--------------------------------------------------
We label each low in chronological order relative to a single
"reference" price (the most recent lower_low, or the baseline).

  - No reference yet          -> swing_low      (baseline)
  - price <  reference        -> lower_low      + DEMOTE the previous reference
  - price >  reference        -> higher_low      (bounce; reference unchanged)
  - price == reference        -> swing_low       (tie; reference unchanged)

The DEMOTE flag is the contract between this file and the state machine:
it says "whoever is holding the reference must retroactively relabel
the previous reference node to swing_low, because this new node has
taken over as the floor."

WHY THE DEMOTION IS A FLAG, NOT A DIRECTIVE
-------------------------------------------
This file does not know node_ids and does not mutate anything.
It cannot perform the retroactive rewrite itself. Instead it says
"demotion is needed" and the state machine (which owns node_ids and
the output dict) performs the rewrite. This keeps this file pure and
keeps the mutable rewrite in exactly one place.

WHY higher_low DOES NOT MOVE THE REFERENCE
------------------------------------------
The reference is defined as "the most recent *break*" (baseline or
lower_low). A bounce (higher_low) is not a break — it is a retreat.
If higher_low moved the reference, then a later low at 85 would be
compared against 95 (the bounce) instead of 90 (the prior LL), and
the "one surviving lower_low" invariant would break: you'd get
swing_low -> lower_low -> higher_low -> lower_low, where the second
lower_low is a fresh LL against the bounce rather than a continuation
of the original floor. Keeping the reference at the last break makes
the label semantics stable: lower_low always means "broke the current
floor," regardless of how many bounces happened in between.

WHY THE TIE IS swing_low (not higher_low)
-----------------------------------------
A tie (price == reference) means price stalled exactly at the floor.
It is not a break (so not lower_low) and not a retreat (so not
higher_low). Treating it as swing_low + not demoting keeps the
existing reference intact and the label honest: "we touched the floor
but did not break it." If you later decide a tie should demote, it is
a one-line change here and the state machine needs no change.

SYMMETRY WITH THE HIGH SIDE
---------------------------
The high track is the exact mirror:

  - No reference yet          -> swing_high     (baseline)
  - price >  reference        -> higher_high    + DEMOTE previous reference
  - price <  reference        -> lower_high      (bounce; reference unchanged)
  - price == reference        -> swing_high      (tie; reference unchanged)

Lows and highs run as two INDEPENDENT state machines. A high's label
never depends on the low track's reference, and vice versa. This is
why the state machine in labeler.py keeps two separate reference
slots (_low_ref, _high_ref) and never shares them.

DO NOT ADD HERE
---------------
- No node_id handling        -> that is the state machine's job
- No output dict / mutation  -> that is the state machine's job
- No sequence walking        -> that is the state machine's job
- No "previous label" lookups-> that is the state machine's job

If you find yourself wanting any of the above, you are in the wrong file.
"""
src/logic/labeler.py — mutable side
python
# src/logic/labeler.py
"""
Stateful labeling pass: walks chronological nodes, holds the current
reference per track, and applies the stateless classifications from
labels.py — including the RETROACTIVE DEMOTION of the previous
reference when a break is detected.

WHY THIS FILE EXISTS (and why it is separate from labels.py)
------------------------------------------------------------
labels.py answers "what kind of event is this?" — pure, testable in
isolation, no state. This file answers "what does the event do to
history?" — it holds exactly the state the rules need (one reference
per track) and owns the one mutation the rules imply (demoting the
previous reference's label).

Splitting them means:
  - The RULES can be tested without a sequence (labels.py).
  - The HISTORY MACHINERY can be tested without re-testing the rules
    (this file), by feeding it synthetic events.
  - A rule change touches one pure function; a state change touches
    one class. They do not entangle.

THE STATE (keep it minimal)
---------------------------
  _low_ref  : Optional[FractalNode]  -> node currently labeled lower_low
                                        (or the baseline swing_low before any break)
  _high_ref : Optional[FractalNode]  -> node currently labeled higher_high
                                        (or the baseline swing_high before any break)
  _labels   : dict[node_id, str]     -> the output; written here, read by callers

There is deliberately NO "last_dir" flag and NO "consecutive break
counter". The retroactive demotion IS the reset: when a break fires,
the previous reference is demoted in place, so the invariant "exactly
one surviving lower_low (and one higher_high) at all times" holds by
construction. If you find yourself wanting a counter, re-read the
rule: the demotion already encodes the reset.

THE INVARIANT (the reason the demotion exists)
-----------------------------------------------
After processing any prefix of the node stream, for the low track:
  - exactly one node is labeled lower_low (the current reference), OR
    none if no break has happened yet (only a baseline swing_low), AND
  - every node that was ever a lower_low but has since been broken
    is labeled swing_low.

This is what makes the labels readable: lower_low is "the current
floor"; swing_low is "a former floor that got taken out" (plus the
initial baseline). Without the demotion, lower_low would pile up and
carry no information (the "endless LL" trap).

WHY THE DEMOTION HAPPENS ON break_down, NOT ON THE NEXT NODE
-----------------------------------------------------------
The demotion is triggered by the event that CAUSES it (the new break),
not by the node that follows. This is what makes the reset retroactive
and order-correct: the moment 85 breaks below 90, 90 is no longer the
floor, so 90 must become swing_low immediately. Deferring the demotion
to the next node would leave a window where two nodes are labeled
lower_low, violating the invariant.

WHY higher_low / lower_high DO NOT TOUCH THE REFERENCE
------------------------------------------------------
See labels.py's comment. Short version: the reference is the last
*break*, not the last *node*. A bounce does not move the floor, so it
must not move the reference. The state machine obeys the stateless
classifier's silence on this: it only updates _low_ref on
"baseline" and "break_down" events.

WHY THE OUTPUT IS dict[node_id, str], NOT A MUTATED FractalNode
---------------------------------------------------------------
FractalNode is frozen=True — labels cannot be attached in place, and
we do not want to break that contract. A dict keyed by node_id:
  - is the minimal mutable surface (one dict, one class),
  - makes retroactive demotion a one-liner
    (labels[prev_ref.node_id] = "swing_low"),
  - lets callers join labels onto nodes by node_id without wrapping,
  - keeps FractalNode and LabeledNode concerns separate.
If callers later want LabeledNode wrappers, that is a presentation
concern — build them from this dict, do not push them into this file.

WHY TWO REFERENCE SLOTS (not one shared ref)
--------------------------------------------
Lows and highs are independent tracks. A low break says nothing about
where the high reference is. Sharing one reference would couple the
tracks and produce nonsense labels (e.g. a high labeled relative to a
low's floor). Two slots, two classifiers, two apply methods — the
symmetry is in the structure, not in shared state.

WHY run() RESETS STATE AT THE TOP
---------------------------------
run() is intended to be called once per full labeling pass (e.g. per
window refresh). Resetting _low_ref, _high_ref, and _labels at the top
makes the pass idempotent: calling run() twice on the same nodes
yields the same output. If you ever need INCREMENTAL labeling (label
only the new tail of the stream), do NOT reuse this method — add a
separate feed(one_node) path with its own tests, because incremental
labeling has different correctness conditions (retroactive demotion
can reach back into already-emitted labels, which a caller consuming
a dict-by-node_id must be prepared for).

WHAT NOT TO PUT HERE
--------------------
- No price comparisons           -> that is labels.py's job
- No label strings               -> import them from labels.py
- No SwingPair logic             -> pair-building is a different concern
                                    (SwingPairer); labels are per-node,
                                    pairs are per-move. Do not merge them.
- No filtering / dedup           -> label the ALREADY-FILTERED nodes.
                                    filter_extremes() collapses same-type
                                    runs; labeling must run after it, or
                                    "consecutive break" semantics get
                                    tangled with dedup semantics.

TESTING NOTES (what the tests should prove)
-------------------------------------------
1. labels.py tests: pure table tests, (price, reference) -> event.
   No Labeler, no nodes, no sequences.
2. labeler.py tests:
   a. Your canonical example: 100 -> 90 -> 85 -> 80 lows gives
      [swing_low, swing_low, swing_low, lower_low].
   b. Bounce case: 100 -> 90 -> 95 -> 85 keeps reference at 90, so
      85 is lower_low and 90 is demoted to swing_low (not 95).
   c. Tie case: 100 -> 90 -> 90 keeps reference at 90, both 90s
      labeled (first lower_low, second swing_low), no demotion.
   d. High mirror: 100 -> 110 -> 105 -> 115 gives
      [swing_high, swing_high, swing_high, higher_high] with the
      same demotion rhythm.
   e. Invariant: at every prefix, at most one lower_low and at most
      one higher_high in the output dict.
   f. Independence: interleaving highs and lows does not change
      either track's labels relative to labeling each track alone.
"""
Quick reference card (put this at the top of either file if you prefer terse)
python
# ─────────────────────────────────────────────────────────────────────
# LABELING — QUICK REFERENCE
#
#   STATELESS (labels.py)        MUTABLE (labeler.py)
#   ─────────────────────        ─────────────────────
#   classify_low(price, ref)  →  Labeler._apply_low(node, event)
#   classify_high(price, ref) →  Labeler._apply_high(node, event)
#
#   Pure. No state.              Holds _low_ref, _high_ref, _labels.
#   No node_ids.                 Owns the retroactive demotion.
#   Table-testable.              Sequence-testable.
#
#   CONTRACT: LowEvent.demote_reference / HighEvent.demote_reference
#   says "the previous reference must be relabeled to the baseline."
#   The state machine obeys; the classifier never mutates.
#
#   LOW TRACK                      HIGH TRACK
#   ─────────                      ──────────
#   no ref        → swing_low      no ref        → swing_high
#   price <  ref  → lower_low +D   price >  ref  → higher_high +D
#   price >  ref  → higher_low     price <  ref  → lower_high
#   price == ref  → swing_low      price == ref  → swing_high
#
#   D = demote previous reference to baseline (retroactive reset).
#   Reference moves ONLY on baseline and break. Bounces/tie: no move.
#   Invariant: exactly one surviving lower_low (and one higher_high).
# ─────────────────────────────────────────────────────────────────────
The one-paragraph version, if you only keep one comment
Stateless side (labels.py) answers "what kind of event is this?" — pure functions of (price, reference) returning an event dataclass with a label and a demote_reference flag. No state, no mutation, no node_ids. Mutable side (labeler.py) answers "what does the event do to history?" — holds one reference per track, walks the chronological nodes, and when an event says demote_reference, rewrites the previous reference's label to the baseline before recording the new node's label. The demotion is the reset — no last_dir counter needed — and it guarantees the invariant that exactly one lower_low (and one higher_high) survives at any prefix, which is what makes the labels meaningful instead of piling up. The two files are split so rules can be table-tested without sequences, and history can be sequence-tested without re-testing rules.
    """