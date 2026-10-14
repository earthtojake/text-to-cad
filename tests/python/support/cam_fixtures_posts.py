"""Hand-built toolpath IRs for the post suites (track B3): one small program per machine kind, independent of every
planner, each touching every event kind its machine can run.

:func:`program` returns a ``posts.base.Program`` for ``kind`` (``mill``, ``mill4``, ``mill5``, ``mill5_tcp``,
``router``, ``lathe``, ``laser``, ``plasma``, ``waterjet``, ``wire_edm``) and a post name, with optional machine keys
checked through the post's own options (as a job would). The numbers below are the ones the suites assert.
"""

from __future__ import annotations

import math

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

#: The lathe program's thread and roughing cycles (radius, z), for assertions.
THREAD = {"z_start": 2.0, "z_end": -15.0, "x_clear": 6.0, "x_crest": 5.0, "depth_mm": 0.61, "pitch_mm": 1.0,
          "first_depth_mm": 0.25, "min_depth_mm": 0.05, "spring_passes": 1, "angle_deg": 60, "infeed_deg": 29.5,
          "external": True, "finish_mm": 0.0}
ROUGH = {"profile": [[4.0, 1.0], [4.0, -10.0], [6.0, -10.0], [6.0, -20.0], [10.5, -20.0]], "depth_mm": 1.5,
         "allowance_x_mm": 0.2, "allowance_z_mm": 0.1, "retract_mm": 0.5, "x_start": 10.5, "z_start": 2.0,
         "external": True}
LATHE_RPM = 1500.0
CUT_HOLES = [[-10.0, 5.0, 0.0], [10.0, 5.0, 0.0]]


def _machine(kind: str, post: str, keys: dict | None):
    from cadgen._internal.cam import posts as registry
    from cadgen._internal.cam.job import Machine

    raw = {"kind": kind, "post": post, **(keys or {})}
    registry.entry_for(post, kind)
    options = registry.parse_options(post, raw)
    kinematics = raw.get("kinematics") or ("ac_trunnion" if kind == "mill5" else None)
    import dataclasses

    shared = {"spindle_spinup_s": raw["spindle_spinup_s"]} if "spindle_spinup_s" in raw and "spindle_spinup_s" in {
        f.name for f in dataclasses.fields(Machine)} else {}
    return Machine(kind=kind, post=post, max_rpm=raw.get("max_rpm"), kinematics=kinematics,
                   diameter_mode=raw.get("diameter_mode", True), post_options=options, tool_change_s=5.0, **shared)


def _tools(entries):
    from cadgen._internal.cam.tools import parse_tool

    return {tool.id: tool for tool in (parse_tool(entry, i) for i, entry in enumerate(entries))}


def _setup(orientation="+Z", wcs="G54", setup_id="top"):
    import numpy as np

    from cadgen._internal.cam.job import Setup
    from cadgen._internal.cam.wcs import build_wcs

    setup = Setup(id=setup_id, plain="Top" if orientation == "+Z" else "Tilted", orientation=orientation,
                  origin="stock-top-center", operations=(), wcs=wcs)
    corners = np.array([[-20, -15, -10], [20, 15, 0]], dtype=float)
    return setup, build_wcs(setup, stock_points=corners, part_points=corners)


def _program(setup, wcs, path, tools, machine, **extra):
    from cadgen._internal.cam.posts.base import Program

    return Program(setup=setup, wcs=wcs, toolpath=path, tools=tools, machine=machine, version="TEST",
                   part="part.step", material="aluminium 6061", tolerance_mm=0.01, clearance_z=5.0, **extra)


MILL_TOOLS = [{"id": "T1", "type": "flat", "diameter_mm": 6, "flutes": 3},
              {"id": "T2", "type": "drill", "diameter_mm": 5},
              {"id": "T3", "type": "tap", "diameter_mm": 6, "pitch_mm": 1.0}]


def taps(post: str, keys=None) -> bool:
    """Whether ``post`` (with machine keys ``keys``) taps with a cycle: GRBL has none, and ``cycles: false`` posts
    every cycle as moves; both refuse a tap (a tap posted as moves breaks), so the fixture leaves it out there."""
    return post != "grbl" and (keys or {}).get("cycles") is not False


def _mill_path(b, *, rotary_setup=None, wcs="G54", tap=True):
    """A rounded-square pocket pass with a helix, a dwell, a stop, a peck cycle, a tap cycle (``tap``) and coolant."""

    b.event("setup", id="top", wcs=wcs, plain="Top", rotary=dict(rotary_setup or {}))
    b.begin_op(index=0, setup="top", op="pocket", plain="Pocket", tool="T1")
    b.event("tool", tool="T1", number=1)
    b.event("spindle", rpm=12000, dir="cw")
    b.event("coolant", mode="flood")
    b.event("comment", text="Pocket #o1.f12")
    b.rapid(x=10, y=0)
    b.rapid(z=1)
    b.feed(z=0, f=600)
    b.arc(10, 0, -1, centre=(5, 0, 0), clockwise=False, f=1200)
    for k in range(0, 91, 5):
        a = math.radians(k)
        b.feed(x=5 + 5 * math.cos(a), y=5 * math.sin(a), z=-1, f=1990)
    b.feed(x=-5, y=5, f=1990)
    b.dwell(0.5)
    b.rapid(z=5)
    b.end_op()
    b.event("stop", optional=True, message="Check the pocket")
    b.begin_op(index=1, setup="top", op="drill", plain="Drill", tool="T2")
    b.event("tool", tool="T2", number=2)
    b.event("spindle", rpm=7600, dir="cw")
    handle = b.begin_cycle(cycle="peck", holes=CUT_HOLES, z_bottom=-6.0, r_plane=1.0, retract="initial",
                           initial_z=5.0, peck_mm=3.0, feed=300.0)
    for x, y, _ in CUT_HOLES:              # pecks of 3 from R1: -2, -5, -6, out to R and back 0.5 over each
        b.rapid(x=x, y=y)
        b.rapid(z=1)
        b.feed(z=-2, f=300)
        b.rapid(z=1)
        b.rapid(z=-1.5)
        b.feed(z=-5, f=300)
        b.rapid(z=1)
        b.rapid(z=-4.5)
        b.feed(z=-6, f=300)
        b.rapid(z=5)
    b.end_cycle(handle)
    b.end_op()
    if not tap:
        b.event("coolant", mode="off")
        return
    b.begin_op(index=2, setup="top", op="drill", plain="Tap", tool="T3")
    b.event("tool", tool="T3", number=3)
    b.event("spindle", rpm=500, dir="cw")
    # The tap stops a pitch above the drilled hole's full diameter (Z-4.5 under the 5 mm drill's point at Z-6).
    handle = b.begin_cycle(cycle="tap", holes=CUT_HOLES, z_bottom=-3.5, r_plane=2.0, retract="r", initial_z=5.0,
                           feed=500.0, pitch_mm=1.0)
    for x, y, _ in CUT_HOLES:             # in at rpm x pitch, the spindle reversed, out (as drill.py expands G84)
        b.rapid(x=x, y=y)
        b.rapid(z=2)
        b.feed(z=-3.5, f=500)
        b.event("spindle", rpm=500, dir="ccw")
        b.feed(z=2, f=500)
        b.event("spindle", rpm=500, dir="cw")
    b.end_cycle(handle)
    b.rapid(z=5)
    b.end_op()
    b.event("coolant", mode="off")


def mill(post: str, keys=None, kind: str = "mill"):
    from cadgen._internal.cam.ir import ToolpathBuilder

    setup, wcs = _setup()
    b = ToolpathBuilder((0, 0, 5))
    _mill_path(b, tap=taps(post, keys))
    return _program(setup, wcs, b.build(), _tools(MILL_TOOLS), _machine(kind, post, keys))


def tilted(post: str, kind: str, orientation: dict, keys=None):
    """A 3+2 setup: the pocket and drilling of :func:`mill` in a tilted frame (the setup event names the turn)."""
    from cadgen._internal.cam.ir import ToolpathBuilder

    from cadgen._internal.cam.ir import Toolpath

    setup, wcs = _setup(orientation, wcs="G55", setup_id="tilt")
    b = ToolpathBuilder((0, 0, 5))
    _mill_path(b, rotary_setup=dict(wcs.rotary_deg), wcs="G55", tap=taps(post, keys))
    path = b.build()
    # Like the planners, every move carries the setup's (constant) rotary position.
    moves = path.moves.copy()
    for axis, value in wcs.rotary_deg:
        moves[axis] = value
    path = Toolpath(moves, path.events, path.ops, start=path.start, rotary=tuple(a for a, _ in wcs.rotary_deg))
    return _program(setup, wcs, path, _tools(MILL_TOOLS), _machine(kind, post, keys))


def simultaneous(post: str, kind: str = "mill5", axes: str = "ac", keys=None):
    """A wrap: feed moves whose A (and C) change with X, under one tool: tool centre point control territory."""
    import numpy as np

    from cadgen._internal.cam.ir import Toolpath, ToolpathBuilder

    setup, wcs = _setup()
    b = ToolpathBuilder((0, 0, 5))
    b.event("setup", id="top", wcs="G54", plain="Top", rotary={})
    b.begin_op(index=0, setup="top", op="surface_normal", plain="5-axis finish", tool="T1")
    b.event("tool", tool="T1", number=1)
    b.event("spindle", rpm=10000, dir="cw")
    b.rapid(x=-10, y=0)
    b.rapid(z=1)
    b.feed(z=0, f=500)
    for k in range(1, 11):
        b.feed(x=-10 + 2 * k, y=0, z=-0.1 * k, f=800)
    b.rapid(z=5)
    b.end_op()
    path = b.build()
    moves = path.moves.copy()
    angles = np.zeros(len(moves))
    angles[3:13] = np.linspace(3, 30, 10)
    angles[13:] = angles[12]               # the retract holds the tool's tilt: it never swings A in the cut
    moves["a"] = angles
    used = ("a",)
    if "c" in axes:
        moves["c"] = angles * 2
        used = ("a", "c")
    if axes == "bc":
        moves["b"], moves["a"] = angles, 0.0
        used = ("b", "c")
    path = Toolpath(moves, path.events, path.ops, start=path.start, rotary=used)
    raw = {**(keys or {})}
    if kind == "mill5" and axes == "bc":
        raw["kinematics"] = "bc_head"
    return _program(setup, wcs, path, _tools(MILL_TOOLS), _machine(kind, post, raw))


LATHE_TOOLS = [{"id": "T1", "type": "turn", "insert": "C", "nose_radius_mm": 0.4},
               {"id": "T2", "type": "thread", "pitch_mm": 1.0},
               {"id": "T3", "type": "drill", "diameter_mm": 5}]


def lathe(post: str, keys=None):
    """Face, rough (a G71-style cycle with its expansion), a finish profile with a G18 arc, a centre-drill peck
    (expanded on every lathe post) and an M10x1 thread (a G76-style cycle with its expansion). x is the radius."""
    from cadgen._internal.cam.ir import PLANE_ZX, ToolpathBuilder

    setup, wcs = _setup(setup_id="lathe")
    b = ToolpathBuilder((15, 0, 5), lathe=True)
    b.event("setup", id="lathe", wcs="G54", plain="Lathe", rotary={})
    b.begin_op(index=0, setup="lathe", op="turn_face", plain="Face", tool="T1")
    b.event("tool", tool="T1", number=1)
    b.event("spindle", rpm=LATHE_RPM, dir="cw", css_m_min=200.0, max_rpm=3000.0, feed_per_rev=True)
    b.event("coolant", mode="flood")
    b.rapid(x=11, z=0)
    b.feed(x=-0.4, f=0.2 * LATHE_RPM)
    b.rapid(z=2)
    b.end_op()
    b.begin_op(index=1, setup="lathe", op="turn_rough", plain="Rough turn", tool="T1")
    b.rapid(x=ROUGH["x_start"], z=ROUGH["z_start"])
    handle = b.begin_cycle(cycle="turn_rough", feed=0.25 * LATHE_RPM, **ROUGH)
    for level, z_end in ((9.0, -20.0 + 0.1), (7.5, -20.0 + 0.1), (6.2, -10.0 + 0.1)):
        b.rapid(x=level)
        b.feed(z=z_end, f=0.25 * LATHE_RPM)
        b.feed(x=level + 0.5, f=0.25 * LATHE_RPM)
        b.rapid(z=ROUGH["z_start"])
    b.rapid(x=ROUGH["x_start"])
    b.end_cycle(handle)
    b.end_op()
    b.begin_op(index=2, setup="lathe", op="turn_finish", plain="Finish turn", tool="T1")
    b.rapid(x=3, z=1)
    b.feed(x=4, z=0, f=0.1 * LATHE_RPM)
    b.feed(z=-8, f=0.1 * LATHE_RPM)
    # A concave fillet R2 from (4, -8) to (6, -10): centre (6, -8), clockwise seen from +Y.
    b.arc(6, 0, -10, centre=(6, 0, -8), clockwise=True, f=0.1 * LATHE_RPM, plane=PLANE_ZX)
    b.feed(z=-20, f=0.1 * LATHE_RPM)
    b.feed(x=10.5, f=0.1 * LATHE_RPM)
    b.rapid(z=5)
    b.end_op()
    b.begin_op(index=3, setup="lathe", op="turn_drill", plain="Centre drill", tool="T3")
    b.event("tool", tool="T3", number=3)
    b.event("spindle", rpm=1200.0, dir="cw")
    b.rapid(x=0, z=5)
    handle = b.begin_cycle(cycle="peck", holes=[[0.0, 0.0, 0.0]], z_bottom=-6.0, r_plane=1.0, retract="r",
                           peck_mm=3.0, feed=120.0)
    b.rapid(z=1)
    b.feed(z=-2, f=120)
    b.rapid(z=1)
    b.rapid(z=-1.5)
    b.feed(z=-5, f=120)
    b.rapid(z=1)
    b.rapid(z=-4.5)
    b.feed(z=-6, f=120)
    b.rapid(z=1)
    b.end_cycle(handle)
    b.rapid(z=5)
    b.end_op()
    b.begin_op(index=4, setup="lathe", op="turn_thread", plain="Thread", tool="T2")
    b.event("tool", tool="T2", number=2)
    b.event("spindle", rpm=800.0, dir="cw")
    b.event("stop", optional=False, message="Check the thread gauge")
    b.rapid(x=THREAD["x_clear"], z=THREAD["z_start"])
    handle = b.begin_cycle(cycle="thread", feed=THREAD["pitch_mm"] * 800.0, **THREAD)
    for depth in (0.25, 0.45, 0.61):
        b.rapid(x=THREAD["x_crest"] - depth)
        b.feed(z=THREAD["z_end"], f=THREAD["pitch_mm"] * 800.0)
        b.rapid(x=THREAD["x_clear"])
        b.rapid(z=THREAD["z_start"])
    b.end_cycle(handle)
    b.dwell(1.0)
    b.rapid(z=5)
    b.end_op()
    b.event("coolant", mode="off")
    return _program(setup, wcs, b.build(), _tools(LATHE_TOOLS), _machine("lathe", post, keys))


def _contours(b, *, beam: dict, tool="T1"):
    """Two cuts on a sheet: a 20 mm square with a lead-in and a Ø10 hole as two arcs, inside first."""
    b.event("setup", id="sheet", wcs="G54", plain="Sheet", rotary={})
    b.begin_op(index=0, setup="sheet", op="cut", plain="Cut out", tool=tool)
    b.event("tool", tool=tool, number=1)
    # The hole: pierce at its centre, lead in to the edge, two half circles.
    b.rapid(x=0, y=0)
    b.rapid(z=0)
    b.event("beam", on=True, **beam)
    b.feed(x=5, y=0, f=1500)
    b.arc(-5, 0, 0, centre=(0, 0, 0), clockwise=False, f=1500)
    b.arc(5, 0, 0, centre=(0, 0, 0), clockwise=False, f=1500)
    b.event("beam", on=False)
    b.rapid(z=5)
    b.rapid(x=-15, y=-15)
    b.rapid(z=0)
    b.event("beam", on=True, **beam)
    b.feed(x=-12, y=-12, f=1500)
    for x, y in ((12, -12), (12, 12), (-12, 12), (-12, -12)):
        b.feed(x=x, y=y, f=1500)
    b.event("beam", on=False)
    b.rapid(z=5)
    b.end_op()


def cutting(kind: str, post: str, keys=None, beam: dict | None = None):
    from cadgen._internal.cam.ir import ToolpathBuilder

    setup, wcs = _setup(setup_id="sheet")
    tools = _tools([{"id": "T1", "type": "beam", "kerf_mm": 0.2}])
    b = ToolpathBuilder((0, 0, 5))
    beam = dict(beam if beam is not None else {"power": 0.8, "pierce_s": 0.4})
    if kind == "laser":
        b.event("coolant", mode="air")
    _contours(b, beam=beam)
    b.event("stop", optional=True, message="Take the part out")
    if kind == "laser":
        b.event("coolant", mode="off")
    return _program(setup, wcs, b.build(), tools, _machine(kind, post, keys))


def wire(keys=None, beam: dict | None = None):
    from cadgen._internal.cam.ir import ToolpathBuilder

    setup, wcs = _setup(setup_id="wire")
    tools = _tools([{"id": "W1", "type": "wire", "diameter_mm": 0.25, "number": 1}])
    b = ToolpathBuilder((0, 0, 5))
    beam = dict(beam if beam is not None else {})
    _contours(b, beam=beam, tool="W1")
    return _program(setup, wcs, b.build(), tools, _machine("wire_edm", "wire_edm", keys))


def program(kind: str, post: str, keys=None):
    """The suite's one program for ``kind`` on ``post``."""
    if kind in ("mill", "router"):
        return mill(post, keys, kind)
    if kind == "mill4":
        return tilted(post, "mill4", {"a_deg": 30.0}, keys)
    if kind == "mill5":
        return tilted(post, "mill5", {"a_deg": 30.0, "c_deg": 90.0}, keys)
    if kind == "mill5_tcp":
        return simultaneous(post, "mill5", "ac", keys)
    if kind == "mill4_wrap":
        return simultaneous(post, "mill4", "a", keys)
    if kind == "lathe":
        return lathe(post, keys)
    if kind == "wire_edm":
        return wire(keys)
    return cutting(kind, post, keys)


def with_entries(path, lathe: bool = False):
    """``path`` as the posts move it at an entry (the program's first motion and the first after each tool change):
    a rapid that changes both the plane's axes (X Y; a lathe's X) and Z is split into the plane's move at the height
    it starts from, then Z. Events and cycle ends shift with the inserted moves (for read-back comparisons)."""
    import numpy as np

    from cadgen._internal.cam.ir import DWELL, RAPID, Event, Toolpath

    moves = path.moves
    entries = sorted({0} | {e.at for e in path.events if e.kind == "tool"})
    positions = path.positions()
    inserts = []
    for at in entries:
        m = next((k for k in range(at, len(moves)) if int(moves[k]["kind"]) != DWELL), None)
        if m is None or int(moves[m]["kind"]) != RAPID:
            continue
        start, end = positions[m], positions[m + 1]
        plane = [0] if lathe else [0, 1]
        if any(abs(end[k] - start[k]) > 1e-9 for k in plane) and abs(end[2] - start[2]) > 1e-9:
            inserts.append(m)
    if not inserts:
        return path
    rows = []
    for k in range(len(moves)):
        if k in inserts:
            row = moves[k].copy()
            row["z"] = positions[k][2]
            rows.append(row)
        rows.append(moves[k].copy())
    new = np.array(rows, dtype=moves.dtype)

    def shift(index: int) -> int:
        return index + sum(1 for m in inserts if m < index)

    events = [Event(shift(e.at), e.kind,
                    {**e.data, **({"end": shift(e.data["end"])} if "end" in e.data else {})}) for e in path.events]
    return Toolpath(new, events, (), start=path.start, rotary=path.rotary, lathe=path.lathe)
