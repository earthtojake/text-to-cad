"""A small G-code reader for the CAM tests: parse posted text back into moves, with modal state.

Reads G0/G1/G2/G3 (I/J/K centres, incremental; G17/G18/G19), G4, G80 and the canned cycles G81/G82/G83/G73/G84/G85
(and G74/G86/G89/G76 on a mill: their motion is G84's or G85's), G33.1 rigid tapping (feed in, feed back), expanded
the way a controller runs them: rapid over the hole at the current level, rapid to R, feed to Z in pecks for
G83/G73, back to R (G99) or the initial level (G98). G90 only (``G91`` is refused unless the block homes with G28),
G20/G21 (inches scaled to mm), work offsets, F/S/T/M words, and comments in parentheses or after ``;``.

The dialect bits the posts write are read too, backwards compatibly: A/B/C words (a rotary-only line is a move of its
own), ``G28``/``G30`` homes and ``G53`` machine-coordinate moves (recorded in ``homes``, no motion: the IR has
none), ``G92`` (sets the position), tool length and
TCP words (``G43``, ``G43.4``, ``G234``: ``tcp``), tilted planes (``G68.2``: ``tilt``; ``G254``: ``dwo``), wire taper
and compensation (``G51``/``G52``: ``taper``; ``G41``/``G42``: ``comp``; ``U V`` on a move: ``uv``), feed per
revolution (``G95``, or the lathe's ``G99``: ``Move.per_rev``) and an inline laser power ``S`` (``Move.s``).

``read(text, lathe=True)`` reads a lathe program: X is a diameter (``diameter=True``, the default; LinuxCNC's
``G7``/``G8`` switch it) and comes back as the radius the IR stores, I stays a radius, G98/G99 are feed per minute and
per revolution, and the threading and roughing cycles are read: ``G76`` (Fanuc's two blocks, Haas's one block,
LinuxCNC's one block) into ``threads`` (and the final pass at the root as moves), ``G71`` (Fanuc's two blocks or
Haas's one) into ``roughs`` with its profile blocks, which are skipped as motion (the tool ends where it started).
:func:`sample` turns the moves into points for comparing with the IR's own samples, and :func:`compare_moves` holds
the read-back to the IR move by move: each move's kind and feed, the spindle running through every cut (each move
keeps the spindle state it ran with: ``Move.spindle``, ``oriented`` after M19, ``stop_z``), and the dwells in order.

For a machine simulation (``gcode_crash``) the program also keeps ``timeline``: every move and every non-motion
:class:`Event` in program order, each with its line number: ``tool`` (a T word), ``m6``, ``spindle`` (M3/M4/M5 with
S), ``speed`` (an S word alone), ``stop`` (M0/M1), ``mcode`` (any other M word), ``home`` (G28/G30/G53 with the axis
words), ``length`` (G43/G43.4/G234/G49 with H), ``tilt`` (G68.2/G53.1/G69/G254/G255), ``mode`` (G20/G21/G90/G91),
``wcs`` (G54..G59), ``g92`` and ``rough`` (a lathe G71 with its profile). A move says which axes its line named
(``Move.given``; a cycle's or a thread's synthesised moves name X Y Z) and which canned cycle it came from
(``Move.cycle``); a dwell keeps its P word (``Move.p``).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

_WORD = re.compile(r"([A-Z])\s*([-+]?(?:\d+\.?\d*|\.\d+))")
_DRILL = ("G81", "G82", "G83", "G73", "G84", "G85", "G74", "G86", "G89")
_IGNORED = ("G90", "G94", "G91.1", "G40", "G49", "G64", "G61", "G43", "G53.1", "G69", "G255", "G187", "G7", "G8",
            "G96", "G97", "G50", "G80")


@dataclass
class Move:
    kind: str                        # rapid | feed | arc_cw | arc_ccw | dwell
    start: tuple
    end: tuple
    feed: float = 0.0
    centre: tuple | None = None
    plane: str = "G17"
    line: int = 0
    abc: dict = field(default_factory=dict)
    per_rev: bool = False
    uv: tuple | None = None
    s: float | None = None
    #: The axis letters the line named (``"XZ"``, ``"AC"``); X Y Z for a move a cycle or a thread synthesised.
    given: str = "XYZ"
    #: The canned cycle (``G83``, ``G84``, ``G33.1``, ``G76``...) the move is part of, else None.
    cycle: str | None = None
    #: A dwell's P word as written (seconds or milliseconds, by dialect).
    p: float = 0.0
    #: The spindle while the move runs: ``M3``/``M4``, or None when stopped (M5, M0/M1, or never started).
    spindle: str | None = None
    #: The spindle was stopped oriented (M19) and has not started since.
    oriented: bool = False
    #: Where Z stood when the spindle last stopped (None while it runs).
    stop_z: float | None = None


@dataclass
class Event:
    """A non-motion word in program order (see the module docstring for the kinds)."""

    line: int
    kind: str
    data: dict = field(default_factory=dict)


@dataclass
class Program:
    moves: list
    tools: list
    spindle: list                    # (rpm, M3/M4/M5)
    coolant: list
    offsets: list
    comments: list
    stops: int = 0
    cycles: list = field(default_factory=list)
    homes: int = 0
    tcp: list = field(default_factory=list)
    tilt: list = field(default_factory=list)
    dwo: int = 0
    taper: list = field(default_factory=list)
    comp: list = field(default_factory=list)
    threads: list = field(default_factory=list)
    roughs: list = field(default_factory=list)
    g92: list = field(default_factory=list)
    #: Every :class:`Move` and :class:`Event` in program order.
    timeline: list = field(default_factory=list)


def _strip(line: str) -> tuple[str, list[str]]:
    comments = re.findall(r"\(([^)]*)\)", line)
    line = re.sub(r"\([^)]*\)", "", line)
    if ";" in line:
        line, tail = line.split(";", 1)
        comments.append(tail.strip())
    return line.strip().upper(), comments


def read(text: str, start=(0.0, 0.0, 0.0), *, lathe: bool = False, diameter: bool = True) -> Program:
    pos = list(start)
    abc = {"A": 0.0, "B": 0.0, "C": 0.0}
    motion, plane, scale, feed, retract = "G0", "G18" if lathe else "G17", 1.0, 0.0, "G98"
    per_rev = False
    cycle: dict | None = None
    thread_first: dict | None = None
    rough_first: dict | None = None
    profile: dict | None = None
    program = Program([], [], [], [], [], [])

    def x_value(value: float) -> float:
        return value / 2.0 if lathe and diameter else value

    spin = {"m": None, "oriented": False, "stop_z": None}

    def add(kind, end, *, centre=None, number=0, uv=None, s=None, given="XYZ", cycle_code=None):
        move = Move(kind, tuple(pos), tuple(end), feed if kind not in ("rapid", "dwell") else 0.0, centre, plane,
                    number, dict(abc), per_rev and kind != "rapid", uv, s, given, cycle_code,
                    spindle=spin["m"], oriented=spin["oriented"], stop_z=spin["stop_z"])
        program.moves.append(move)
        program.timeline.append(move)
        pos[:] = end

    def event(kind, number, **data):
        program.timeline.append(Event(number, kind, data))

    for number, raw in enumerate(text.splitlines(), 1):
        line, comments = _strip(raw)
        program.comments.extend(comments)
        if not line or line == "%":
            continue
        words = [(letter, float(value)) for letter, value in _WORD.findall(line)]
        gs = [f"G{v:g}" for letter, v in words if letter == "G"]
        values = {letter: v for letter, v in words if letter != "G"}
        if profile is not None:
            # Inside a G71's profile blocks: read the points, do not move.
            last = profile["points"][-1] if profile["points"] else (pos[0], pos[2])
            point = (x_value(values["X"]) * scale if "X" in values else last[0],
                     values["Z"] * scale if "Z" in values else last[1])
            profile["points"].append(point)
            if values.get("N") == profile["nf"]:
                program.roughs[-1]["profile"] = profile["points"]
                profile = None
            continue
        explicit_motion = None
        homing = "G28" in gs or "G30" in gs or "G53" in gs
        for code in gs:
            if code in ("G17", "G18", "G19"):
                plane = code
            elif code == "G20":
                scale = 25.4
            elif code == "G21":
                scale = 1.0
            elif code in ("G98", "G99"):
                if lathe:
                    per_rev = code == "G99"
                else:
                    retract = code
            elif code == "G95":
                per_rev = True
            elif code == "G94":
                per_rev = False
            elif code in ("G7", "G8"):
                diameter = code == "G7"
            elif code in ("G54", "G55", "G56", "G57", "G58", "G59"):
                program.offsets.append(code)
            elif code in ("G0", "G1", "G2", "G3", "G33.1") or (code in _DRILL and not lathe) or (
                    code == "G76" and not lathe):
                explicit_motion = code
            elif code == "G80":
                cycle = None
                motion = "G80"
            elif code == "G4":
                dwell = Move("dwell", tuple(pos), tuple(pos), 0.0, None, plane, number, given="")
                dwell.p = values.get("P", 0.0)               # the P word as written (seconds or ms by dialect)
                program.moves.append(dwell)
                program.timeline.append(dwell)
            elif code in ("G43.4", "G234"):
                program.tcp.append(code)
            elif code == "G68.2":
                program.tilt.append({k: values.get(k, 0.0) for k in "XYZIJK"})
            elif code == "G254":
                program.dwo += 1
            elif code in ("G51", "G52", "G50") and not lathe and "S" not in values:
                program.taper.append((code, values.get("A", 0.0)))
            elif code in ("G41", "G42"):
                program.comp.append((code, values.get("D")))
            elif code in ("G28", "G30", "G53"):
                program.homes += 1
            elif code == "G92":
                pos[0] = values.get("X", pos[0] / scale) * scale
                pos[1] = values.get("Y", pos[1] / scale) * scale
                program.g92.append((pos[0], pos[1]))
            elif code == "G91":
                if not homing:
                    raise ValueError(f"line {number}: incremental G91 is not read")
            elif code in _IGNORED or code in ("G51", "G52", "G50", "G76", "G71", "G70"):
                pass
        if "F" in values:
            feed = values["F"] * (1.0 if per_rev else scale)
        if "T" in values:
            program.tools.append(int(values["T"]))
        if "S" in values or any(letter == "M" and v in (3, 4, 5) for letter, v in words):
            for letter, v in words:
                if letter == "M" and v in (3, 4, 5):
                    program.spindle.append((values.get("S"), f"M{v:g}"))
        for letter, v in words:
            if letter == "M" and v in (7, 8, 9):
                program.coolant.append(f"M{v:g}")
            if letter == "M" and v in (0, 1):
                program.stops += 1
            if letter == "M" and v in (3, 4):
                spin.update(m=f"M{v:g}", oriented=False, stop_z=None)
            elif letter == "M" and v in (0, 1, 5):
                spin.update(m=None, stop_z=pos[2] if spin["stop_z"] is None else spin["stop_z"])
            elif letter == "M" and v == 19:
                spin.update(m=None, oriented=True, stop_z=pos[2] if spin["stop_z"] is None else spin["stop_z"])
        _events(event, number, gs, values, words, homing)
        if homing or "G92" in gs or "G4" in gs or "G68.2" in gs:
            continue
        if lathe and "G76" in gs:
            _thread(program, values, pos, add, number, thread_first, x_value, scale)
            thread_first = None if ("X" in values or "Z" in values) else dict(values)
            continue
        if lathe and "G71" in gs:
            if "P" not in values:
                rough_first = dict(values)
                continue
            depth = values.get("D", (rough_first or {}).get("U", 0.0))
            program.roughs.append({"ns": values["P"], "nf": values["Q"], "depth": depth * scale,
                                   "u": values.get("U", 0.0), "w": values.get("W", 0.0), "start": (pos[0], pos[2]),
                                   "profile": []})
            event("rough", number, rough=program.roughs[-1])
            program.cycles.append("G71")
            profile = {"nf": values["Q"], "points": []}
            rough_first = None
            continue
        if lathe and "G70" in gs:
            continue
        if explicit_motion:
            motion = explicit_motion
            if motion in _DRILL or motion == "G76":
                cycle = {"code": motion, "initial": pos[2], "R": values.get("R", 0.0) * scale,
                         "Z": values.get("Z", 0.0) * scale, "Q": values.get("Q", 0.0) * scale}
                program.cycles.append(motion)
        if not lathe and ("G51" in gs or "G52" in gs):
            values.pop("A", None)                 # a wire taper's angle, not a rotary axis
        for axis in "ABC":
            if axis in values:
                abc[axis] = values[axis]
        has_axis = any(axis in values for axis in "XYZ")
        has_rotary = any(axis in values for axis in "ABC")
        uv = (values.get("U", 0.0) * scale, values.get("V", 0.0) * scale) if ("U" in values or "V" in values) \
            and not lathe else None
        if motion == "G33.1" and "Z" in values:
            top = pos[2]
            add("feed", (pos[0], pos[1], values["Z"] * scale), number=number, cycle_code="G33.1")
            add("feed", (pos[0], pos[1], top), number=number, cycle_code="G33.1")
            program.cycles.append("G33.1")
            continue
        if (motion in _DRILL or motion == "G76") and cycle is not None and has_axis:
            if explicit_motion is None:
                cycle["R"] = values.get("R", cycle["R"] / scale) * scale
            x = values.get("X", pos[0] / scale) * scale
            y = values.get("Y", pos[1] / scale) * scale
            if "Z" in values:
                cycle["Z"] = values["Z"] * scale
            level = pos[2]
            add("rapid", (x, y, level), number=number, cycle_code=cycle["code"])
            add("rapid", (x, y, cycle["R"]), number=number, cycle_code=cycle["code"])
            if cycle["code"] in ("G83", "G73") and cycle["Q"] > 0:
                depth = cycle["R"]
                while depth > cycle["Z"] + 1e-9:
                    depth = max(cycle["Z"], depth - cycle["Q"])
                    add("feed", (x, y, depth), number=number, cycle_code=cycle["code"])
                    if depth > cycle["Z"] + 1e-9:
                        if cycle["code"] == "G83":
                            # Full retract to R, then rapid back to just over the last depth.
                            add("rapid", (x, y, cycle["R"]), number=number, cycle_code=cycle["code"])
                            add("rapid", (x, y, depth + 0.5), number=number, cycle_code=cycle["code"])
                        else:
                            add("rapid", (x, y, depth + 0.2), number=number, cycle_code=cycle["code"])
            else:
                add("feed", (x, y, cycle["Z"]), number=number, cycle_code=cycle["code"])
            back = cycle["initial"] if retract == "G98" else cycle["R"]
            add("feed" if cycle["code"] in ("G84", "G74", "G85", "G89") else "rapid", (x, y, back), number=number,
                cycle_code=cycle["code"])
            continue
        if not has_axis and not has_rotary and uv is None and (motion not in ("G2", "G3") or not any(
                k in values for k in "IJK")):
            continue                              # no motion (a full circle names its centre: I J K)
        end = list(pos)
        for i, axis in enumerate("XYZ"):
            if axis in values:
                end[i] = (x_value(values[axis]) if i == 0 else values[axis]) * scale
        s = values.get("S") if motion in ("G0", "G1", "G2", "G3") else None
        given = "".join(axis for axis in "XYZABC" if axis in values)
        if motion == "G0":
            add("rapid", end, number=number, uv=uv, s=s, given=given)
        elif motion == "G1":
            add("feed", end, number=number, uv=uv, s=s, given=given)
        elif motion in ("G2", "G3"):
            u, v = {"G17": (0, 1), "G18": (2, 0), "G19": (1, 2)}[plane]
            offsets = {"G17": ("I", "J"), "G18": ("K", "I"), "G19": ("J", "K")}[plane]
            centre = list(pos)
            centre[u] = pos[u] + values.get(offsets[0], 0.0) * scale
            centre[v] = pos[v] + values.get(offsets[1], 0.0) * scale
            add("arc_cw" if motion == "G2" else "arc_ccw", end, centre=tuple(centre), number=number, uv=uv, s=s,
                given=given)
    return program


def _events(event, number, gs, values, words, homing) -> None:
    """The line's non-motion words as timeline events (before its motion, as a controller runs them)."""
    for code in gs:
        if code in ("G28", "G30", "G53"):
            event("home", number, code=code, axes={k: v for k, v in values.items() if k in "XYZABCUVW"},
                  incremental="G91" in gs)
        elif code in ("G43", "G43.4", "G234", "G49"):
            event("length", number, code=code, h=values.get("H"))
        elif code in ("G68.2", "G53.1", "G69", "G254", "G255"):
            event("tilt", number, code=code)
        elif code == "G92":
            event("g92", number, axes={k: v for k, v in values.items() if k in "XYZ"})
        elif code in ("G20", "G21", "G90", "G91"):
            event("mode", number, code=code)
        elif code in ("G54", "G55", "G56", "G57", "G58", "G59"):
            event("wcs", number, code=code)
    if "T" in values:
        event("tool", number, t=int(values["T"]))
    for letter, v in words:
        if letter != "M":
            continue
        if v == 6:
            event("m6", number)
        elif v in (3, 4, 5):
            event("spindle", number, m=int(v), s=values.get("S"))
        elif v in (0, 1):
            event("stop", number, m=int(v))
        else:
            event("mcode", number, m=v, s=values.get("S"))
    if "S" in values and not any(letter == "M" and v in (3, 4, 5) for letter, v in words):
        event("speed", number, s=values["S"], gs=tuple(gs))


def _thread(program, values, pos, add, number, first, x_value, scale) -> None:
    """A lathe G76: record it and add its final pass at the root (rapid in, feed along, rapid out and back)."""
    if "X" not in values and "Z" not in values:
        return                                    # Fanuc's first block: passes, angle, minimum depth
    if "I" in values and "K" in values and "X" not in values:     # LinuxCNC: drive line here, I crest offset, K depth
        crest = pos[0] + x_value(values["I"]) * scale
        depth = x_value(values["K"]) * scale
        root = crest - depth if values["I"] < 0 else crest + depth
        pitch = values["P"] * scale
        dialect = "linuxcnc"
    else:                                         # Fanuc's second block or Haas's one block: X is the root
        root = x_value(values["X"]) * scale
        depth = (values["K"] if "K" in values else values.get("P", 0.0) / 1000.0) * scale
        pitch = values["F"] * scale
        dialect = "haas" if "D" in values else "fanuc"
    z_end = values["Z"] * scale
    clear, z_start = pos[0], pos[2]
    program.threads.append({"dialect": dialect, "root": root, "depth": depth, "pitch": pitch, "z_end": z_end,
                            "x_clear": clear, "z_start": z_start, "first": dict(first or {})})
    program.cycles.append("G76")
    add("rapid", (root, pos[1], z_start), number=number, cycle_code="G76")
    add("feed", (root, pos[1], z_end), number=number, cycle_code="G76")
    add("rapid", (clear, pos[1], z_end), number=number, cycle_code="G76")
    add("rapid", (clear, pos[1], z_start), number=number, cycle_code="G76")


def sample(program: Program, chord: float = 0.005, max_step: float | None = None):
    """(points (N, 3), kinds) along every move; arcs split within ``chord``, lines into pieces no longer than
    ``max_step`` when one is given."""
    import numpy as np

    points, kinds = [], []
    for move in program.moves:
        if move.kind == "dwell":
            continue
        piece = move_points(move, chord, max_step)
        points.extend(piece)
        kinds.extend([move.kind] * len(piece))
    return np.asarray(points, dtype=float), kinds


def move_points(move: Move, chord: float = 0.005, max_step: float | None = None) -> list:
    """Points along one move after its start: an arc split within ``chord``, a line into pieces no longer than
    ``max_step`` when one is given."""
    points = []
    if move.kind in ("arc_cw", "arc_ccw"):
        u, v, w = {"G17": (0, 1, 2), "G18": (2, 0, 1), "G19": (1, 2, 0)}[move.plane]
        c = move.centre
        a0 = math.atan2(move.start[v] - c[v], move.start[u] - c[u])
        a1 = math.atan2(move.end[v] - c[v], move.end[u] - c[u])
        radius = math.hypot(move.start[u] - c[u], move.start[v] - c[v])
        sweep = a1 - a0
        if move.kind == "arc_cw":
            while sweep >= -1e-9:
                sweep -= 2 * math.pi
        else:
            while sweep <= 1e-9:
                sweep += 2 * math.pi
        step = 2 * math.acos(max(-1.0, 1 - chord / radius)) if radius > chord else math.pi / 2
        count = max(2, int(math.ceil(abs(sweep) / step)))
        if max_step:
            length = math.hypot(radius * abs(sweep), move.end[w] - move.start[w])
            count = max(count, int(math.ceil(length / max_step)))
        for k in range(1, count + 1):
            angle = a0 + sweep * k / count
            p = [0.0, 0.0, 0.0]
            p[u] = c[u] + radius * math.cos(angle)
            p[v] = c[v] + radius * math.sin(angle)
            p[w] = move.start[w] + (move.end[w] - move.start[w]) * k / count
            points.append(p)
    else:
        length = math.dist(move.start, move.end)
        count = max(1, int(math.ceil(length / max_step))) if max_step else 1
        for k in range(1, count + 1):
            points.append([a + (b - a) * k / count for a, b in zip(move.start, move.end)])
    return points


#: Posted moves whose F is not the IR's feed by design: a thread's F is its pitch, a rigid tap's feed is the spindle's,
#: and a tap's F is the posted S times the pitch (checked on its own).
_FEED_EXEMPT = ("G76", "G33.1", "G84", "G74")


def compare_moves(program: Program, path, *, planar: bool = False, spindle: bool = True, dwell_ms: bool = False,
                  native=(), tolerance: float = 0.012) -> list[str]:
    """What in the read-back ``program`` is not the IR ``path`` (as posted: :func:`cam_fixtures_posts.with_entries`),
    move by move: [] when nothing. Each posted move is matched, in order, to the IR move it runs along (its middle on
    that move's path, the same way along it), and must be of its kind (a rapid a rapid, a cut a feed, plunge or arc,
    an arc turning the same way) at its feed (F to 0.1 mm/min; a per-revolution feed, a thread's, a rigid tap's and a
    tap cycle's are exempt). With ``spindle`` (a mill or a lathe) every cut runs with the spindle on, and no move
    crosses XY with the spindle stopped un-oriented (no M19) below where it stopped: a boring bar dragged across the
    wall; and the posted dwells are the IR's, in order and length (``dwell_ms``: P is milliseconds), leaving out a G4
    right after a spindle start (a spin-up wait) and dwells inside the ``native`` cycles (``(at, end)`` move ranges the
    post wrote as canned cycles). (A beam's pierce dwell is the beam event's, not a move: not compared.) ``planar``
    compares X Y only."""
    import numpy as np

    from cadgen._internal.cam.ir import ARC_CCW, ARC_CW, DWELL, RAPID

    dims = 2 if planar else 3
    problems: list[str] = []
    samples = path.sample(0.002)
    positions = path.positions()
    kinds = path.moves["kind"]
    polylines = []
    for k in range(len(path.moves)):
        rows = samples.points[samples.move == k]
        polylines.append(np.vstack([positions[k], rows])[:, :dims] if len(rows) else positions[k:k + 1, :dims])

    def along(poly, probe):
        """(distance from ``probe`` to the polyline, the direction of its nearest segment)."""
        if len(poly) < 2:
            return math.inf, np.zeros(dims)
        a, b = poly[:-1], poly[1:]
        d = b - a
        length2 = np.maximum((d * d).sum(axis=1), 1e-18)
        t = np.clip(((probe - a) * d).sum(axis=1) / length2, 0.0, 1.0)
        gaps = np.linalg.norm(probe - (a + t[:, None] * d), axis=1)
        best = int(np.argmin(gaps))
        return float(gaps[best]), d[best] / math.sqrt(length2[best])

    cursor = 0
    for move in program.moves:
        if move.kind == "dwell":
            continue
        points = np.asarray([move.start] + move_points(move, 0.002), dtype=float)[:, :dims]
        steps = np.linalg.norm(np.diff(points, axis=0), axis=1)
        total = float(steps.sum())
        if total < 1e-6:
            continue
        cumulative = np.concatenate([[0.0], np.cumsum(steps)])
        k = min(int(np.searchsorted(cumulative, total / 2.0)), len(steps)) - 1
        k = max(k, 0)
        f = (total / 2.0 - cumulative[k]) / max(steps[k], 1e-18)
        probe = points[k] + (points[k + 1] - points[k]) * f
        heading = (points[k + 1] - points[k]) / max(steps[k], 1e-18)
        found = None
        for index in range(cursor, len(path.moves)):
            if int(kinds[index]) == DWELL:
                continue
            gap, direction = along(polylines[index], probe)
            if gap <= tolerance and float(direction @ heading) > 0.0:
                found = index
                break
        where = f"line {move.line} ({move.kind} to {tuple(round(v, 4) for v in move.end)})"
        if found is None:
            problems.append(f"{where}: no IR move from move {cursor} on runs there")
            continue
        cursor = found
        ir_kind = int(kinds[found])
        cutting = move.kind != "rapid"
        if cutting != (ir_kind != RAPID):
            problems.append(f"{where}: the IR's move {found} is a {('rapid', 'feed', 'plunge', 'arc_cw', 'arc_ccw')[ir_kind]}")
        elif move.kind in ("arc_cw", "arc_ccw") and ir_kind in (ARC_CW, ARC_CCW) and (
                (move.kind == "arc_cw") != (ir_kind == ARC_CW)):
            problems.append(f"{where}: the IR's arc {found} turns the other way")
        elif cutting and not move.per_rev and move.cycle not in _FEED_EXEMPT and abs(
                move.feed - float(path.moves["feed"][found])) > 0.05 + 1e-6:
            problems.append(f"{where}: F{move.feed:g}, the IR's move {found} feeds at {path.moves['feed'][found]:g}")
        if spindle and cutting and move.spindle is None:
            problems.append(f"{where}: cuts with the spindle stopped")
        if spindle and move.spindle is None and not move.oriented and move.stop_z is not None and math.hypot(
                move.end[0] - move.start[0], move.end[1] - move.start[1]) > 1e-6 and min(
                move.start[2], move.end[2]) <= move.stop_z + 1e-6:
            problems.append(f"{where}: crosses X Y with the spindle stopped un-oriented, at or below where it "
                            "stopped")
    if not spindle:
        return problems
    # Dwells, in order.
    posted = []
    last = None
    for item in program.timeline:
        if isinstance(item, Move) and item.kind == "dwell":
            spun = isinstance(last, Event) and last.kind == "spindle" and last.data.get("m") in (3, 4) and (
                last.line == item.line - 1)
            if not spun:
                posted.append((item.line, item.p / 1000.0 if dwell_ms else item.p))
        last = item
    inside = lambda k: any(at <= k < end for at, end in native)  # noqa: E731
    wanted = [float(path.moves["p"][k]) for k in range(len(path.moves)) if int(kinds[k]) == DWELL and not inside(k)]
    if len(posted) != len(wanted) or any(abs(a - b) > 1e-3 for (_, a), b in zip(posted, wanted)):
        problems.append(f"dwells {[round(p, 4) for _, p in posted]} s posted, the IR's are {wanted}")
    return problems


def posted_text(result, setup: str | None = None) -> str:
    """Every file a ``cam.plan`` result posted for ``setup`` (default: the first setup), joined in program order: a
    post that writes one file per tool (GRBL) splits a setup, and the files read back as one program."""
    from pathlib import Path

    setup = setup if setup is not None else result.posts[0]["setup"]
    return "".join(Path(p["file"]).read_text(encoding="utf-8") for p in result.posts if p["setup"] == setup)
