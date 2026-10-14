"""The Toolpath IR: THE contract between the planners, the stock simulators, the checks, the posts and the GLB.

Planners emit it (through :class:`ToolpathBuilder`); everything downstream reads only it, never a planner's internals.

**Moves** are one numpy structured array (:data:`MOVE_DTYPE`), one row per move, each going from the previous
position (the toolpath's ``start`` for row 0) to its own ``x, y, z``:

=========  ===================================================================================================
``kind``   :data:`RAPID` (0), :data:`FEED` (1), :data:`PLUNGE` (2, a feed move into material along the tool axis,
           posted like a feed), :data:`ARC_CW` (3), :data:`ARC_CCW` (4), :data:`DWELL` (5: no motion, ``p`` seconds)
``x y z``  the end point, WCS mm. A lathe toolpath stores true geometry: ``x`` the radius, ``z`` the axial
           position, ``y`` 0 (posts convert to diameter words).
``a b c``  rotary positions in degrees (multi-axis; 0 where unused). :attr:`Toolpath.rotary` names the axes in use.
``feed``   mm/min for feed, plunge and arc moves; 0 for rapids (the machine's rapid rate) and dwells.
``i j k``  an arc's centre, absolute WCS mm (``i, j`` in XY for :data:`PLANE_XY`; ``i, k`` for ZX).
``plane``  :data:`PLANE_XY` (G17, the default), :data:`PLANE_ZX` (G18, lathe arcs), :data:`PLANE_YZ` (G19).
           Clockwise is as seen looking down the plane's normal axis (G17: from +Z). An arc may be helical (its
           end ``z`` differs from its start); an arc whose end is its start is a full circle.
``p``      a dwell's seconds.
``op``     the global operation index the move belongs to (-1 for linking between operations).
=========  ===================================================================================================

**Events** (:class:`Event`, ordered by ``at``, the move index they happen before) carry everything that is not
motion: ``setup`` (``id``, ``wcs``, ``plain``, ``rotary`` for a 3+2 setup), ``tool`` (``tool``, ``number``,
``plain``), ``spindle`` (``rpm``, ``dir`` cw/ccw/off), ``coolant`` (``mode`` off/flood/mist/air), ``cycle`` (a
canned drilling cycle, below), ``stop`` (``optional``, ``message``), ``beam`` (laser/plasma ``on``, ``power``
0..1, ``pierce_s``) and ``comment`` (``text``).

A ``cycle`` event carries the hole list and the cycle's parameters so a post can emit G81/G83/G73/G84/G85/G82
(``cycle``: drill, peck, chipbreak, tap, bore, ream, spot; ``holes``: ``[[x, y, z_top], ...]``; ``z_bottom``;
``r_plane``; ``retract``: ``r`` or ``initial`` (G99/G98); ``initial_z``; ``peck_mm``; ``dwell_s``; ``feed``;
``pitch_mm`` for taps), and its ``end``: the moves ``[at, end)`` are the cycle expanded into plain moves. The
simulator, the checks and the GLB read the expansion; a post either emits the cycle and skips the expansion or
posts the expansion. The expansion ends where the controller's cycle leaves the tool (over the last hole at the R
plane or the initial level), so both ways leave the machine in the same place.

What the posts read beyond that (every key optional unless said; a post that cannot emit a cycle natively, or finds
a key it needs missing, posts the expansion, so the expansion must always be the whole truth):

- more drilling ``cycle`` names: ``bore_stop`` (G86), ``bore_dwell`` (G89), ``fine_bore`` (G76 on a mill, with
  ``shift_mm``); ``left_hand`` true on a ``tap`` (G74); ``rigid`` on a ``tap`` when the job says (true: the feed
  synchronised to the spindle, refused where the controller cannot; false: a floating holder; absent: the
  controller's own tapping cycle); ``back_bore`` (G87, Haas G77: ``shift_mm`` and ``shift_xy`` as a fine bore's,
  ``retract`` always ``initial``) whose ``r_plane`` is under the part and whose ``z_bottom`` is the cycle's Z word
  above it, the tip's highest point (the head's top on the back counterbore's shoulder). Its expansion, per hole
  from the initial level: a ``spindle`` off event with ``orient`` true, the shift, rapid down through the hole to R,
  back on the axis, the spindle on, a feed up to Z, the dwell, a feed back down to R, oriented and shifted again,
  rapid up to the initial level, back on the axis, the spindle on (G87 and G77 orient at Z rather than back at R: the
  shift moves the insert off the wall either way). An ``orient`` spindle stop is posted with the controller's
  oriented stop (M19). The stock simulators read the expansion's moves with the spindle stopped as the bar's neck
  through the hole (they cut nothing) and its feeds as the head cutting up from under the part
  (:func:`cadgen._internal.cam.stock.move_modes`).
- lathe ``cycle`` ``thread`` (G76): ``z_start``, ``z_end``, ``x_clear`` (the radius it starts and ends at),
  ``x_crest`` (the crest's radius: the major for an external thread, the minor for an internal one), ``depth_mm``
  (radial thread height; the root is ``x_crest`` -/+ it), ``pitch_mm`` (the lead), ``external`` (default true),
  ``first_depth_mm``, ``min_depth_mm``, ``finish_mm``, ``spring_passes``, ``infeed_deg`` (29.5), ``angle_deg``
  (60), ``taper_mm`` (radius change from ``z_start`` to ``z_end``). The expansion starts and ends at
  ``(x_clear, z_start)``.
- lathe ``cycle`` ``turn_rough`` (G71): ``profile`` (``[[x_radius, z], ...]``, the finished profile in cutting
  order), ``depth_mm`` (radial depth a pass), ``allowance_x_mm`` (radial), ``allowance_z_mm``, ``retract_mm``,
  ``feed``, ``x_start``/``z_start`` (where it starts and ends), ``external`` (default true).
- ``spindle`` on a lathe: ``css_m_min`` (constant surface speed; ``rpm`` stays the speed the times assumed),
  ``max_rpm`` (the clamp), ``feed_per_rev`` true (posted per revolution: F = the move's mm/min over ``rpm``).
- multi-axis: a ``setup`` event's ``rotary`` (3+2) means the moves are in the tilted WCS (machine-aligned after the
  table turns); moves whose ``a b c`` change along cutting moves are simultaneous and carry the tool tip in the
  setup's WCS at rotary zero (what TCP, G43.4/G234, expects).
- ``beam`` on a wire EDM: ``taper_deg`` (signed: plus leans the wire's top to the left of travel), ``thickness_mm``
  (program plane to the top guide's plane), ``offset_side`` (``left``/``right``: where the wire runs, for
  controller compensation).

**Operations** are :class:`OpRange` rows: the move range ``[start, end)`` of each operation, its global index, setup,
op name, plain word, tool, and ``meta`` (planner facts a check reads, e.g. ``unreachable`` areas, ``stock_to_leave``).

:meth:`Toolpath.time_s` is the cycle time (moves at their feeds, rapids at the machine's rapid rate, dwells,
``machine.tool_change_s`` per tool event and ``machine.spindle_spinup_s`` per spindle start from standstill: no
acceleration, so it is an estimate);
:meth:`Toolpath.sample` returns :class:`Samples` (points, program time, op, kind, move) along the path with arcs
sampled within a chord tolerance, the one sampler the simulator, the checks and the GLB share.

numpy at import (this module is only imported by the engine, after the job parsed).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

__all__ = [
    "ARC_CCW", "ARC_CW", "DWELL", "Event", "FEED", "MOVE_DTYPE", "MOVE_KINDS", "OpRange", "PLANE_XY", "PLANE_YZ",
    "PLANE_ZX", "PLUNGE", "RAPID", "Samples", "Toolpath", "ToolpathBuilder", "concat",
]

RAPID, FEED, PLUNGE, ARC_CW, ARC_CCW, DWELL = 0, 1, 2, 3, 4, 5
MOVE_KINDS = ("rapid", "feed", "plunge", "arc_cw", "arc_ccw", "dwell")
PLANE_XY, PLANE_ZX, PLANE_YZ = 0, 1, 2
#: The event kinds (see the module docstring for each one's data).
EVENT_KINDS = ("setup", "tool", "spindle", "coolant", "cycle", "stop", "beam", "comment")

MOVE_DTYPE = np.dtype([
    ("kind", "u1"), ("x", "f8"), ("y", "f8"), ("z", "f8"), ("a", "f8"), ("b", "f8"), ("c", "f8"),
    ("feed", "f8"), ("i", "f8"), ("j", "f8"), ("k", "f8"), ("plane", "u1"), ("p", "f8"), ("op", "i4"),
])
#: Rapid rate when no machine is given (mm/min).
DEFAULT_RAPID = 5000.0
#: The most moves one operation plans: past it a job asks for more than any program runs (a hundredth-of-a-millimetre
#: stepover across a metre), and :class:`ToolpathBuilder` refuses it (``PlanTooBig``) before the rows fill the memory.
MAX_MOVES = 2_000_000
#: :meth:`Toolpath.sample` interpolates straight moves this many samples at a time.
_SAMPLE_CHUNK = 250_000


@dataclass(frozen=True)
class Event:
    at: int
    kind: str
    data: dict = field(default_factory=dict)

    def shifted(self, offset: int) -> "Event":
        data = dict(self.data)
        if self.kind == "cycle" and "end" in data:
            data["end"] = data["end"] + offset
        return Event(self.at + offset, self.kind, data)


@dataclass(frozen=True)
class OpRange:
    index: int
    setup: str
    op: str
    plain: str
    tool: str | None
    start: int
    end: int
    meta: dict = field(default_factory=dict)

    def shifted(self, offset: int, index: int | None = None) -> "OpRange":
        return OpRange(self.index if index is None else index, self.setup, self.op, self.plain, self.tool,
                       self.start + offset, self.end + offset, self.meta)


@dataclass(frozen=True)
class Samples:
    """Points along a toolpath: row 0 is the start; row ``n`` ends a piece of move ``move[n]``."""

    points: np.ndarray      # (M, 3)
    t: np.ndarray           # (M,) program time, s
    op: np.ndarray          # (M,) op index of the move the sample ends (-1 for the start)
    kind: np.ndarray        # (M,) move kind of that move (RAPID for the start)
    move: np.ndarray        # (M,) move index (-1 for the start)

    def __iter__(self):
        # (points, t, op, kind): what spec section 8 names the sampler's answer.
        return iter((self.points, self.t, self.op, self.kind))


class Toolpath:
    """Moves, events and operation ranges; see the module docstring."""

    def __init__(self, moves: np.ndarray | None = None, events=(), ops=(), *, start=(0.0, 0.0, 0.0),
                 rotary: tuple[str, ...] = (), lathe: bool = False):
        self.moves = np.zeros(0, dtype=MOVE_DTYPE) if moves is None else np.asarray(moves, dtype=MOVE_DTYPE)
        self.events: tuple[Event, ...] = tuple(sorted(events, key=lambda e: e.at))
        self.ops: tuple[OpRange, ...] = tuple(ops)
        self.start = tuple(float(v) for v in start)
        self.rotary = tuple(rotary)
        self.lathe = lathe

    def __len__(self) -> int:
        return len(self.moves)

    def __repr__(self) -> str:
        return f"Toolpath({len(self.moves)} moves, {len(self.events)} events, {len(self.ops)} ops)"

    # --- geometry ----------------------------------------------------------------------------------------

    def ends(self) -> np.ndarray:
        """(N, 3) end point of every move."""
        m = self.moves
        return np.column_stack([m["x"], m["y"], m["z"]]) if len(m) else np.zeros((0, 3))

    def positions(self) -> np.ndarray:
        """(N + 1, 3): the start, then every move's end."""
        return np.vstack([np.asarray(self.start)[None, :], self.ends()])

    def _arc_geometry(self, index: int, begin: np.ndarray):
        """(centre (3,), radius, sweep (signed, radians), plane axes (u, v, w)) of arc move ``index``."""
        move = self.moves[index]
        u, v, w = {PLANE_XY: (0, 1, 2), PLANE_ZX: (2, 0, 1), PLANE_YZ: (1, 2, 0)}[int(move["plane"])]
        centre = np.array([move["i"], move["j"], move["k"]], dtype=float)
        end = np.array([move["x"], move["y"], move["z"]], dtype=float)
        a0 = math.atan2(begin[v] - centre[v], begin[u] - centre[u])
        a1 = math.atan2(end[v] - centre[v], end[u] - centre[u])
        radius = math.hypot(begin[u] - centre[u], begin[v] - centre[v])
        clockwise = int(move["kind"]) == ARC_CW
        sweep = a1 - a0
        if clockwise:
            while sweep >= -1e-12:
                sweep -= 2 * math.pi
        else:
            while sweep <= 1e-12:
                sweep += 2 * math.pi
        # A start and end within a hair of each other is a full circle, never a zero sweep.
        if abs(abs(sweep) - 2 * math.pi) < 1e-12 and math.hypot(begin[u] - end[u], begin[v] - end[v]) > 1e-9:
            sweep = 0.0
        return centre, radius, sweep, (u, v, w), a0

    def lengths(self) -> np.ndarray:
        """(N,) path length of every move, mm (0 for dwells)."""
        pos = self.positions()
        delta = np.linalg.norm(np.diff(pos, axis=0), axis=1)
        kinds = self.moves["kind"] if len(self.moves) else np.zeros(0, dtype=np.uint8)
        for index in np.nonzero((kinds == ARC_CW) | (kinds == ARC_CCW))[0]:
            _, radius, sweep, (u, v, w), _ = self._arc_geometry(int(index), pos[index])
            rise = pos[index + 1][w] - pos[index][w]
            delta[index] = math.hypot(radius * abs(sweep), rise)
        delta[kinds == DWELL] = 0.0
        return delta

    def durations(self, machine=None) -> np.ndarray:
        """(N,) seconds per move: rapids at the machine's rapid rate, cuts at their feed, dwells their ``p``."""
        rapid = float(getattr(machine, "rapid_mm_min", None) or DEFAULT_RAPID)
        lengths = self.lengths()
        kinds = self.moves["kind"]
        feeds = np.where(kinds == RAPID, rapid, self.moves["feed"])
        feeds = np.where(feeds > 0, feeds, rapid)
        seconds = lengths / feeds * 60.0
        seconds[kinds == DWELL] = self.moves["p"][kinds == DWELL]
        return seconds

    def event_seconds(self, machine=None) -> np.ndarray:
        """(N + 1,) seconds spent in events before each move (a tool change costs ``machine.tool_change_s``, a
        spindle start from standstill ``machine.spindle_spinup_s``, the wait every post dwells after it, and so
        does the restart after a stop; the last slot holds events after the last move)."""
        out = np.zeros(len(self.moves) + 1)
        change = float(getattr(machine, "tool_change_s", 0.0) or 0.0)
        spinup = float(getattr(machine, "spindle_spinup_s", None) or 0.0)
        turning = False
        for event in self.events:
            at = min(event.at, len(self.moves))
            if event.kind == "tool":
                out[at] += change
                turning = False                    # a tool change stops the spindle
            elif event.kind == "spindle":
                on = event.data.get("dir", "cw") != "off"
                if on and not turning:
                    out[at] += spinup
                turning = on
            elif event.kind == "stop" and turning:
                out[at] += spinup                  # the spindle is started again after the stop
            elif event.kind == "beam" and event.data.get("on"):
                out[at] += float(event.data.get("pierce_s", 0.0) or 0.0)
        return out

    def times(self, machine=None) -> np.ndarray:
        """(N + 1,) program time at the start and at each move's end, s (events counted before their move)."""
        waits = self.event_seconds(machine)
        per = self.durations(machine)
        out = np.zeros(len(self.moves) + 1)
        out[1:] = np.cumsum(per + waits[:-1])
        return out

    def time_s(self, machine=None) -> float:
        """The whole program's estimated time, s."""
        if not len(self.moves):
            return float(self.event_seconds(machine).sum())
        return float(self.times(machine)[-1] + self.event_seconds(machine)[-1])

    def op_times(self, machine=None) -> dict[int, tuple[float, float]]:
        """``{op index: (t0, t1)}``: when each operation starts and ends in program time, the tool change before
        its first move included."""
        times = self.times(machine)
        last = len(times) - 1
        return {op.index: (float(times[min(op.start, last)]), float(times[min(op.end, last)])) for op in self.ops}

    # --- sampling ----------------------------------------------------------------------------------------

    def sample(self, chord_mm: float = 0.01, *, machine=None, max_step_mm: float | None = None,
               t0: float = 0.0) -> Samples:
        """Points along the path. Arcs are split so no chord strays more than ``chord_mm`` from the arc; straight
        moves are split into pieces no longer than ``max_step_mm`` when one is given (the simulator's spacing),
        else kept whole. Times are program time from ``t0``."""
        pos = self.positions()
        n = len(self.moves)
        if n == 0:
            return Samples(pos.copy(), np.array([t0]), np.array([-1]), np.array([RAPID], dtype=np.uint8),
                           np.array([-1]))
        times = self.times(machine) + t0
        waits = self.event_seconds(machine)
        kinds = self.moves["kind"]
        pieces = np.ones(n, dtype=np.int64)
        lengths = self.lengths()
        if max_step_mm:
            straight = (kinds == RAPID) | (kinds == FEED) | (kinds == PLUNGE)
            pieces[straight] = np.maximum(1, np.ceil(lengths[straight] / max_step_mm)).astype(np.int64)
        arcs = np.nonzero((kinds == ARC_CW) | (kinds == ARC_CCW))[0]
        geometry = {}
        for index in arcs:
            centre, radius, sweep, axes, a0 = self._arc_geometry(int(index), pos[index])
            geometry[int(index)] = (centre, radius, sweep, axes, a0)
            if radius > chord_mm:
                step = 2.0 * math.acos(max(-1.0, 1.0 - chord_mm / radius))
            else:
                step = math.pi / 2
            count = max(2, int(math.ceil(abs(sweep) / max(step, 1e-6))))
            if max_step_mm:
                count = max(count, int(math.ceil(lengths[index] / max_step_mm)))
            pieces[index] = count
        pieces[kinds == DWELL] = 1
        total = int(pieces.sum())
        points = np.empty((total + 1, 3))
        t = np.empty(total + 1)
        op = np.empty(total + 1, dtype=np.int64)
        kind = np.empty(total + 1, dtype=np.uint8)
        move = np.empty(total + 1, dtype=np.int64)
        points[0], t[0], op[0], kind[0], move[0] = pos[0], times[0], -1, RAPID, -1
        offsets = np.concatenate([[1], 1 + np.cumsum(pieces)])
        # Straight moves (and dwells) vectorised: linear interpolation between their ends.
        simple = np.nonzero(~np.isin(np.arange(n), arcs))[0]
        # In groups of about _SAMPLE_CHUNK samples, so the temporaries stay small on a long path (a simulator's
        # millions of samples), whatever the output's size.
        cumulative = np.cumsum(pieces[simple]) if len(simple) else np.zeros(0, dtype=np.int64)
        edges = [0, *np.searchsorted(cumulative, np.arange(_SAMPLE_CHUNK, int(cumulative[-1]) if len(simple) else 0,
                                                           _SAMPLE_CHUNK)).tolist(), len(simple)]
        for a, b in zip(edges[:-1], edges[1:]):
            if b <= a:
                continue
            group = simple[a:b]
            counts = pieces[group]
            repeat = np.repeat(group, counts)
            within = np.arange(int(counts.sum())) - np.repeat(np.cumsum(counts) - counts, counts)
            fraction = (within + 1) / np.repeat(counts, counts)
            rows = np.repeat(offsets[group], counts) + within
            begin, end = pos[repeat], pos[repeat + 1]
            points[rows] = begin + (end - begin) * fraction[:, None]
            start_t = times[repeat] + waits[repeat]
            t[rows] = start_t + (times[repeat + 1] - start_t) * fraction
            op[rows] = self.moves["op"][repeat]
            kind[rows] = kinds[repeat]
            move[rows] = repeat
        for index, (centre, radius, sweep, (u, v, w), a0) in geometry.items():
            count = int(pieces[index])
            fraction = np.arange(1, count + 1) / count
            angle = a0 + sweep * fraction
            rows = offsets[index] + np.arange(count)
            chunk = np.empty((count, 3))
            chunk[:, u] = centre[u] + radius * np.cos(angle)
            chunk[:, v] = centre[v] + radius * np.sin(angle)
            chunk[:, w] = pos[index][w] + (pos[index + 1][w] - pos[index][w]) * fraction
            chunk[-1] = pos[index + 1]
            points[rows] = chunk
            start_t = times[index] + waits[index]
            t[rows] = start_t + (times[index + 1] - start_t) * fraction
            op[rows] = int(self.moves["op"][index])
            kind[rows] = kinds[index]
            move[rows] = index
        return Samples(points, t, op, kind, move)

    def slice(self, start: int, end: int) -> "Toolpath":
        """Moves ``[start, end)`` as a toolpath of their own, starting where move ``start`` begins (events inside the
        range kept, op ranges dropped)."""
        position = self.positions()[start] if start < len(self.moves) + 1 else self.positions()[-1]
        events = [Event(e.at - start, e.kind, {**e.data, **({"end": e.data["end"] - start} if "end" in e.data else {})})
                  for e in self.events if start <= e.at < end]
        return Toolpath(self.moves[start:end].copy(), events, (), start=tuple(position), rotary=self.rotary,
                        lathe=self.lathe)

    # --- transforms --------------------------------------------------------------------------------------

    def with_op(self, index: int) -> "Toolpath":
        """A copy whose moves all belong to operation ``index`` (a planner's output, before it is placed)."""
        moves = self.moves.copy()
        moves["op"] = index
        return Toolpath(moves, self.events, self.ops, start=self.start, rotary=self.rotary, lathe=self.lathe)


def concat(paths, *, start=None) -> Toolpath:
    """One toolpath of several, in order: events and op ranges shifted to their new move indices."""
    paths = list(paths)
    moves, events, ops = [], [], []
    offset = 0
    rotary: list[str] = []
    for path in paths:
        moves.append(path.moves)
        events.extend(event.shifted(offset) for event in path.events)
        ops.extend(op.shifted(offset) for op in path.ops)
        rotary.extend(axis for axis in path.rotary if axis not in rotary)
        offset += len(path.moves)
    first = start if start is not None else (paths[0].start if paths else (0.0, 0.0, 0.0))
    joined = np.concatenate(moves) if moves else np.zeros(0, dtype=MOVE_DTYPE)
    return Toolpath(joined, events, ops, start=first, rotary=tuple(rotary), lathe=any(p.lathe for p in paths))


class ToolpathBuilder:
    """Moves appended one at a time (or a polyline at once) from a known position; :meth:`build` freezes them.

    Coordinates left ``None`` keep the current value. Zero-length motion is dropped. ``op`` is stamped on every move
    (set it with :meth:`set_op`); events are placed before the next move.
    """

    def __init__(self, start=(0.0, 0.0, 0.0), *, op: int = 0, lathe: bool = False):
        self.start = tuple(float(v) for v in start)
        self._pos = list(self.start)
        self._abc = [0.0, 0.0, 0.0]
        self._rows: list[tuple] = []
        self._events: list[Event] = []
        self._ops: list[OpRange] = []
        self._op = op
        self._open: dict | None = None
        self.rotary: list[str] = []
        self.lathe = lathe

    @property
    def pos(self) -> tuple[float, float, float]:
        return tuple(self._pos)

    @property
    def count(self) -> int:
        return len(self._rows)

    def set_op(self, index: int) -> None:
        self._op = index

    def _target(self, x, y, z):
        return (self._pos[0] if x is None else float(x), self._pos[1] if y is None else float(y),
                self._pos[2] if z is None else float(z))

    def _add(self, kind: int, end, *, feed: float = 0.0, centre=(0.0, 0.0, 0.0), plane: int = PLANE_XY,
             p: float = 0.0, abc=None) -> None:
        if abc is not None:
            self._abc = [float(v) for v in abc]
        if len(self._rows) >= MAX_MOVES:
            from cadgen._internal.cam.job_errors import PlanTooBig

            raise PlanTooBig(f"it needs more than {MAX_MOVES:,} moves: use a bigger tool, a larger stepover or "
                             "stepdown, or a smaller region")
        self._rows.append((kind, end[0], end[1], end[2], *self._abc, float(feed), *centre, plane, float(p), self._op))
        self._pos = list(end)

    def rapid(self, x=None, y=None, z=None) -> None:
        end = self._target(x, y, z)
        if end != tuple(self._pos):
            self._add(RAPID, end)

    def feed(self, x=None, y=None, z=None, *, f: float) -> None:
        end = self._target(x, y, z)
        if end != tuple(self._pos):
            self._add(FEED, end, feed=f)

    def plunge(self, x=None, y=None, z=None, *, f: float) -> None:
        end = self._target(x, y, z)
        if end != tuple(self._pos):
            self._add(PLUNGE, end, feed=f)

    def arc(self, x, y, z, *, centre, clockwise: bool, f: float, plane: int = PLANE_XY) -> None:
        """An arc (or helix) to ``(x, y, z)`` about ``centre`` (absolute, 3 numbers; the plane's two used)."""
        end = self._target(x, y, z)
        self._add(ARC_CW if clockwise else ARC_CCW, end, feed=f, centre=tuple(float(c) for c in centre), plane=plane)

    def dwell(self, seconds: float) -> None:
        if seconds > 0:
            self._add(DWELL, tuple(self._pos), p=seconds)

    def rotate(self, *, f: float = 0.0, **axes: float) -> None:
        """Move rotary axes (``a=30``, ``c=90``); a rapid unless ``f`` is given."""
        abc = list(self._abc)
        for axis, value in axes.items():
            abc["abc".index(axis)] = float(value)
            if axis not in self.rotary:
                self.rotary.append(axis)
        if abc != self._abc:
            self._add(FEED if f else RAPID, tuple(self._pos), feed=f, abc=abc)

    def polyline(self, points, *, f: float, kind: int = FEED) -> None:
        """Feed (or rapid, or plunge) through ``points`` (N, 3) in order."""
        for point in np.asarray(points, dtype=float):
            end = (float(point[0]), float(point[1]), float(point[2]))
            if end != tuple(self._pos):
                self._add(kind, end, feed=0.0 if kind == RAPID else f)

    def event(self, kind: str, **data) -> Event:
        if kind not in EVENT_KINDS:
            raise ValueError(f"unknown event kind {kind!r}; one of {', '.join(EVENT_KINDS)}")
        event = Event(len(self._rows), kind, data)
        self._events.append(event)
        return event

    def begin_cycle(self, **data) -> int:
        """Open a canned cycle; the moves until :meth:`end_cycle` are its expansion. Returns the event's index."""
        self._events.append(Event(len(self._rows), "cycle", data))
        return len(self._events) - 1

    def end_cycle(self, handle: int) -> None:
        event = self._events[handle]
        self._events[handle] = Event(event.at, "cycle", {**event.data, "end": len(self._rows)})

    def begin_op(self, *, index: int, setup: str, op: str, plain: str, tool: str | None) -> None:
        self._op = index
        self._open = {"index": index, "setup": setup, "op": op, "plain": plain, "tool": tool, "start": len(self._rows)}

    def end_op(self, meta: dict | None = None) -> None:
        if self._open is None:
            raise RuntimeError("end_op without begin_op")
        opened = self._open
        self._ops.append(OpRange(opened["index"], opened["setup"], opened["op"], opened["plain"], opened["tool"],
                                 opened["start"], len(self._rows), dict(meta or {})))
        self._open = None

    def build(self) -> Toolpath:
        moves = np.array(self._rows, dtype=MOVE_DTYPE) if self._rows else np.zeros(0, dtype=MOVE_DTYPE)
        return Toolpath(moves, self._events, self._ops, start=self.start, rotary=tuple(self.rotary), lathe=self.lathe)
