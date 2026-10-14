"""Machine crashes: the independent checker (``tests/python/support/gcode_crash.py``) fires on every rule for a small
hand-written bad program and stays quiet on its good twin; every post golden is crash-free; and small planned parts
of every machine kind, posted with every post that serves the kind, are crash-free."""

from __future__ import annotations

import dataclasses
import unittest
from pathlib import Path

import numpy as np

from tests.python.support import cam_fixtures_posts as F
from tests.python.support import gcode_crash as C

MILL_TOOLS = {1: C.ToolShape.from_job({"type": "flat", "diameter_mm": 6}, 0),
              2: C.ToolShape.from_job({"type": "drill", "diameter_mm": 5}, 1),
              3: C.ToolShape.from_job({"type": "tap", "diameter_mm": 6, "pitch_mm": 1.0}, 2)}
#: A 40 x 30 x 10 block, its top at WCS Z0.
BLOCK = C.StockShape.box((-20, -15, -10), (20, 15, 0))
MILL = {"kind": "mill", "post": "linuxcnc", "stock": BLOCK, "tools": MILL_TOOLS, "clearance": 5.0, "retract": 2.0}
#: The ISO mill start: Z home, T1, spindle, X Y over the origin, the tool length at the clearance height.
HEAD = "G21 G90 G94 G17\nG54\nG53 G0 Z0\nT1 M6\nS10000 M3\nG0 X0 Y0\nG0 G43 Z5 H1\n"
GRBL_HEAD = "G90 G94 G17 G21\nG54\n(Load T1: 6 mm flat)\nG0 Z5\nS10000 M3\nG4 P3\nX0 Y0\n"
#: A hole drilled 10 deep at the origin with T2, then T3 (an M6x1 tap) over it.
TAP_HEAD = ("G21 G90 G94 G17\nG54\nG53 G0 Z0\nT2 M6\nS8000 M3\nG0 X0 Y0\nG0 G43 Z5 H2\nG0 Z2\nG1 Z-10 F300\n"
            "G0 Z5\nG53 G0 Z0\nT3 M6\nS500 M3\nG0 X0 Y0\nG0 G43 Z5 H3\n")
LATHE = {"kind": "lathe", "post": "fanuc", "tools": {1: C.ToolShape.from_job({"type": "turn"}, 0),
                                                       2: C.ToolShape.from_job({"type": "turn"}, 1)},
         "stock": C.StockShape("cylinder", np.eye(4), np.array([-10, -10, -30.0]), np.array([10, 10, 0.5]), 2,
                               np.zeros(3), 10.0), "clearance": 5.0}
LATHE_HEAD = "G21\nG0 G18 G40 G80 G98\nG54\nG28 U0. W0.\nT0101\nG97 S1000 M3\n"
PLASMA = {"kind": "plasma", "post": "plasma"}
PLASMA_HEAD = "G21\nG90 G94 G17 G40\nG54\nG0 Z10\nG0 X0 Y0\n"
WIRE = {"kind": "wire_edm", "post": "wire_edm", "stock": C.StockShape.box((0, 0, -12), (90, 70, 0))}
WIRE_HEAD = "G21\nG90 G40 G50\nG92 X15. Y15.\nG1 X12. Y15. F10.\nG2 X12. Y15. I3. J0.\n"


def rules(text, **context) -> set[str]:
    return {f.rule for f in C.check(text, **{**MILL, **context})}


class Rules(unittest.TestCase):
    """Each rule fires on a bad program and stays quiet on its good twin."""

    def assertFires(self, rule, text, **context):
        found = rules(text, **context)
        self.assertIn(rule, found, f"{rule} did not fire on:\n{text}")

    def assertQuiet(self, text, **context):
        found = C.check(text, **{**MILL, **context})
        self.assertEqual(found, [], "\n".join(map(str, found)))

    def test_a_rapid_into_uncut_stock(self):
        self.assertFires("rapid_into_stock", HEAD + "G0 Z-3\n")
        self.assertFires("rapid_into_stock", HEAD + "G0 Z1\nG1 Z-3 F300\nG0 X10\n")
        # Into the slot it cut, and back down into its own hole: clear.
        self.assertQuiet(HEAD + "G0 Z1\nG1 Z-3 F300\nG1 X10\nG0 Z5\nG0 X0\nG0 Z-2.9\nG1 Z-4\nG0 Z5\nG0 X5\n"
                                "G0 Z-2.95\nG0 Z5\nM5\nG53 G0 Z0\nM2\n")
        # A ball's own scallop: down to where it cut, beside it is not.
        ball = {**MILL_TOOLS, 1: C.ToolShape.from_job({"type": "ball", "diameter_mm": 6}, 0)}
        self.assertQuiet(HEAD + "G0 Z1\nG1 Z-3 F300\nG0 Z-2.9\nG0 Z5\n", tools=ball)
        self.assertFires("rapid_into_stock", HEAD + "G0 Z1\nG1 Z-3 F300\nG0 Z5\nG0 X2\nG0 Z-2.9\n", tools=ball)

    def test_a_rapid_through_a_tilted_setups_stock(self):
        from cadgen._internal.cam.wcs import rotation_for

        r = np.asarray(rotation_for({"a_deg": 30.0}))
        matrix = np.eye(4)
        matrix[:3, :3] = r
        matrix[:3, 3] = [0, 0, -(np.array([[x, y, z] for x in (-20, 20) for y in (-15, 15) for z in (-10, 0)])
                                 @ r.T)[:, 2].max()]
        stock = C.StockShape("box", matrix, np.array([-20, -15, -10.0]), np.array([20, 15, 0.0]))
        top = float(stock.column(np.array([0.0]), np.array([0.0]))[1][0])     # the tilted top over X0 Y0
        self.assertLess(top, -5.0)
        self.assertFires("rapid_into_stock", HEAD + f"G0 Z{top - 1:.3f}\n", stock=stock, kind="mill5")
        # The disc of a 6 mm tool reaches 3 tan 30 = 1.73 mm higher up the slope than its centre.
        self.assertFires("rapid_into_stock", HEAD + f"G0 Z{top + 1.5:.3f}\n", stock=stock, kind="mill5")
        self.assertQuiet(HEAD + f"G0 Z{top + 1.9:.3f}\nG0 Z5\nM5\n", stock=stock, kind="mill5")

    def test_the_table_and_a_fixture(self):
        self.assertFires("table", HEAD + "G0 X25\nG0 Z1\nG1 Z-12 F300\nG0 Z5\n")
        self.assertQuiet(HEAD + "G0 X25\nG0 Z1\nG1 Z-10.5 F300\nG0 Z5\n")
        clamp = [((15, -15, 0), (20, 15, 10))]
        self.assertFires("fixture", HEAD + "G0 X17\n", fixtures=clamp)
        self.assertQuiet(HEAD + "G0 X10\n", fixtures=clamp)

    def test_cutting_with_the_spindle_stopped(self):
        self.assertFires("spindle_off", "G53 G0 Z0\nT1 M6\nG0 X0 Y0\nG0 G43 Z5 H1\nG0 Z1\nG1 Z-1 F300\n")
        self.assertFires("spindle_off", HEAD + "M0\nG0 Z1\nG1 Z-1 F300\n")
        self.assertQuiet(HEAD + "M0\nS10000 M3\nG0 Z1\nG1 Z-1 F300\nG0 Z5\n")
        self.assertFires("spinup", "G90 G94 G17 G21\nG54\n(Load T1: 6 mm flat)\nG0 Z5\nS10000 M3\nX0 Y0\nZ1\n"
                                   "G1 Z-1 F300\n", post="grbl")
        self.assertQuiet(GRBL_HEAD + "Z1\nG1 Z-1 F300\nG0 Z5\nM5\nM2\n", post="grbl")

    def test_a_tool_change_away_from_the_top(self):
        self.assertFires("tool_change", HEAD + "T2 M6\n")
        self.assertQuiet(HEAD + "G53 G0 Z0\nT2 M6\nS8000 M3\nG0 X10 Y0\nG0 G43 Z5 H2\n")
        self.assertQuiet(HEAD + "T2 M06\nS8000 M3\nG0 X10 Y0\nG0 G43 Z5 H2\n", post="haas")   # Haas homes Z itself
        self.assertFires("tool_change", GRBL_HEAD + "(Load T2: 5 mm drill)\n", post="grbl")
        self.assertFires("tool_change", LATHE_HEAD + "G0 X30. Z5.\nT0202\n", **LATHE)
        self.assertQuiet(LATHE_HEAD + "G0 X30. Z5.\nG28 U0. W0.\nT0202\nG0 X30.\nZ5.\n", **LATHE)

    def test_the_entry_order(self):
        start = "G21 G90\nG54\nG53 G0 Z0\nT1 M6\nS10000 M3\n"
        self.assertFires("entry", start + "G0 X0 Y0 Z5\n")                     # a diagonal plunge from the top
        self.assertFires("entry", start + "G0 G43 Z5 H1\n")                    # down before X Y
        self.assertFires("entry", "G90 G94 G17 G21\nG54\n(Load T1: 6 mm flat)\nS10000 M3\nG4 P3\nG0 X10 Y0\n",
                         post="grbl")                                           # X Y at an unknown height
        self.assertFires("entry", "G21 G90\nG54\n(Load T1: 6 mm flat)\nG0 Z-1\n", post="grbl")   # Z first, but not up
        self.assertFires("entry", start + "G0 X0 Y0\nG0 A30 C0\n", kind="mill5")  # rotary after X Y
        self.assertQuiet(start + "G0 A30 C0\nG0 X0 Y0\nG0 G43 Z5 H1\n", kind="mill5")
        self.assertFires("entry", "G21\nG90 G94 G17 G40\nG54\nG0 X10 Y10\nG0 Z3.8\n", **PLASMA)
        self.assertQuiet(PLASMA_HEAD, **PLASMA)

    def test_a_rotary_turn_with_the_tool_low(self):
        self.assertFires("rotary", HEAD + "G0 Z1\nG0 A90\n", kind="mill4")
        self.assertQuiet(HEAD + "G0 A90\n", kind="mill4")
        self.assertFires("rotary", HEAD + "G0 Z1\nG1 X1 A10 F100\n", kind="mill4")      # simultaneous, no TCP
        tcp = "G21 G90\nG54\nG53 G0 Z0\nT1 M6\nS10000 M3\nG0 A0\nG43.4 H1\nG0 X25 Y0\nG0 Z1\nG1 Z-1 F300\n"
        self.assertFires("rotary", tcp + "G0 A10\n", kind="mill4")                       # out of the cut
        self.assertQuiet(tcp + "G0 Z2\nG0 A10\n", kind="mill4")
        self.assertFires("rotary", HEAD + "G0 Z1\nG53.1\n", kind="mill5")

    def test_tapping(self):
        cycle = "G0 Z5\nG99 G84 X0 Y0 Z-8 R2 F500\nG80\n"
        self.assertFires("tap", TAP_HEAD.replace("M3", "M4") + cycle)
        self.assertFires("tap", TAP_HEAD + cycle.replace("F500", "F400"))
        self.assertFires("tap", TAP_HEAD + cycle, post="fanuc")                           # no M29
        self.assertQuiet(TAP_HEAD + "M29 S500\n" + cycle, post="fanuc")
        self.assertQuiet(TAP_HEAD + cycle)
        expanded = "G0 Z2\nG1 Z-8 F500\n"
        self.assertFires("tap", TAP_HEAD + expanded + "G1 Z2\n")                        # out without reversing
        self.assertFires("tap", TAP_HEAD + expanded + "G0 Z5\n")                        # out at rapid
        self.assertQuiet(TAP_HEAD + expanded + "S500 M4\nG1 Z2\nS500 M3\nG0 Z5\n")
        # Deeper than the drill went, or where it never drilled: the tap breaks.
        self.assertFires("tap", TAP_HEAD + "G0 Z2\nG1 Z-12 F500\nS500 M4\nG1 Z2\n")
        self.assertFires("tap", TAP_HEAD + "G0 X10\nG0 Z2\nG1 Z-4 F500\nS500 M4\nG1 Z2\n")

    def test_the_shank_and_the_holder(self):
        necked = {**MILL_TOOLS, 1: C.ToolShape.from_job({"type": "ball", "diameter_mm": 2, "flute_length_mm": 4,
                                                          "stickout_mm": 30, "shank_diameter_mm": 6}, 0)}
        slot = HEAD + "G0 Z1\nG1 Z-6 F300\nG1 X10\nG0 Z5\n"
        self.assertFires("holder", slot, tools=necked)          # 6 deep with 4 of flutes: the 6 mm shank rubs
        self.assertQuiet(slot.replace("Z-6", "Z-3.9"), tools=necked)
        held = {**MILL_TOOLS, 1: C.ToolShape.from_job({"type": "flat", "diameter_mm": 6, "flute_length_mm": 20,
                                                        "stickout_mm": 8, "holder_diameter_mm": 30}, 0)}
        self.assertFires("holder", HEAD + "G0 X25\nG0 Z-9\n", tools=held)   # beside the block, the holder over it
        self.assertQuiet(HEAD + "G0 X40\nG0 Z-9\nG0 Z5\n", tools=held)

    def test_the_tool_length_and_the_modes(self):
        self.assertFires("length", "G21 G90\nG54\nG53 G0 Z0\nT1 M6\nS10000 M3\nG0 X0 Y0\nG0 Z5\n")
        self.assertFires("length", "G21 G90\nG54\nG53 G0 Z0\nT1 M6\nS10000 M3\nG0 X0 Y0\nG0 G43 Z5 H2\n")
        self.assertFires("modal", "G90\nG54\nG53 G0 Z0\nT1 M6\nS10000 M3\nG0 X0 Y0\nG0 G43 Z5 H1\n")
        self.assertFires("modal", "G21 G90\nG53 G0 Z0\nT1 M6\nS10000 M3\nG0 X0 Y0\nG0 G43 Z5 H1\n")
        self.assertFires("modal", HEAD + "G91 G28 Z0\nG0 Z5\n")                    # G91 left on after the home
        self.assertQuiet(HEAD + "G91 G28 Z0\nG90\nG0 X5\n")

    def test_arcs(self):
        self.assertFires("arc", HEAD + "G0 Z1\nG1 Z-1 F300\nG2 X10 Y0 I3 J0\n")
        self.assertFires("arc", HEAD + "G0 Z1\nG1 Z-1 F300\nG2 X0 Y0 I0 J0\n")
        self.assertQuiet(HEAD + "G0 Z1\nG1 Z-1 F300\nG2 X6 Y0 I3 J0\nG3 X6 Y0 Z-2 I-3 J0\nG0 Z5\n")
        self.assertQuiet(HEAD + "G0 Z1\nG1 Z-1 F300\nG3 X6 Y0 I3 J0 F500\nM5\nG0 Z5\n")   # M5 alone is no arc

    def test_travel(self):
        self.assertFires("travel", HEAD + "G0 X-20\nG0 X20\n", travel=(30, 30, 30))
        self.assertQuiet(HEAD + "G0 X-10\nG0 X10\n", travel=(30, 30, 30))
        self.assertFires("travel", HEAD + "G0 A120\n", kind="mill4", rotary_limits={"a": (-90, 90)})

    def test_the_beam(self):
        fire = "G0 Z3.8\nM3\nG4 P0.5\nG1 Z1.5 F1000\nG1 X10\n"
        self.assertQuiet(PLASMA_HEAD + fire + "M5\nG0 Z10\nG0 X30\n", **PLASMA)
        self.assertFires("beam", PLASMA_HEAD + fire + "G0 X30\n", **PLASMA)              # rapid with the torch on
        self.assertFires("beam", PLASMA_HEAD + fire + "M5\nG0 X30\n", **PLASMA)          # rapid at cut height
        self.assertFires("beam", PLASMA_HEAD + "G0 Z1.5\nM3\nG4 P0.5\nG1 X10 F1000\n", **PLASMA)   # fired low
        self.assertFires("beam", PLASMA_HEAD + "G0 Z3.8\nM3\nG1 Z1.5 F1000\nG1 X10\n", **PLASMA)  # no dwell
        jet = {"kind": "waterjet", "post": "waterjet"}
        self.assertFires("beam", "G21 G90\nG54\nG0 X0 Y0\nM3\nG1 X10 F500\n", **jet)
        self.assertQuiet("G21 G90\nG54\nG0 X0 Y0\nM3\nG4 P1\nG1 X10 F500\nM5\nG0 X20\n", **jet)
        laser = {"kind": "laser", "post": "grbl"}
        laser_head = "G21 G90\nG54\nG0 Z5\nG0 X0 Y0\nG0 Z2\n"
        self.assertFires("beam", laser_head + "M4 S1000\nG4 P0.5\nG1 X10 F500\n", **laser)
        self.assertQuiet(laser_head + "M3 S1000\nG4 P0.5\nM4 S1000\nG1 X10 F500\nM5\nG0 X20\n", **laser)

    def test_a_wire_dragged_through_solid(self):
        self.assertFires("wire", WIRE_HEAD + "G0 X40. Y40.\n", **WIRE)
        self.assertQuiet(WIRE_HEAD + "M50\nG0 X40. Y40.\nM60\nG1 X40. Y30.\n", **WIRE)
        self.assertQuiet(WIRE_HEAD + "G0 X15. Y15.\n", **WIRE)          # back along its own cut to the start hole

    def test_the_lathe(self):
        self.assertFires("rapid_into_stock", LATHE_HEAD + "G0 X30. Z5.\nG0 X10. Z-5.\n", **LATHE)
        self.assertFires("spindle_off", LATHE_HEAD.replace("G97 S1000 M3\n", "") + "G0 X30.\nZ2.\nG1 X-0.8 F0.2\n",
                         **LATHE)
        self.assertQuiet(LATHE_HEAD + "G0 X30.\nZ0.\nG1 X-0.8 F0.2\nG0 Z2.\nX30.\nX18.\nG1 Z-20. F0.2\nX20.\n"
                                      "G0 Z2.\nG28 U0. W0.\nM30\n", **LATHE)
        # A home move straight out of a bore: through the wall.
        self.assertFires("rapid_into_stock", LATHE_HEAD + "G0 X30.\nZ2.\nG0 X0.\nG1 Z-10. F0.1\nG28 U0. W0.\n",
                         **{**LATHE, "tools": {1: C.ToolShape.from_job({"type": "drill", "diameter_mm": 8}, 0)}})


def _post_context(program, *, lathe_stock=None):
    tools = {t.number: C.ToolShape.from_job(t.as_dict(), 0) for t in program.tools.values()}
    machine = program.machine
    if machine.kind == "lathe":
        stock = lathe_stock
    else:
        stock = C.StockShape("box", np.asarray(program.wcs.matrix()), np.array([-20, -15, -10.0]),
                             np.array([20, 15, 0.0]))
    return {"kind": machine.kind, "post": machine.post, "stock": stock, "tools": tools,
            "clearance": program.clearance_z, "retract": program.retract_z,
            "setup_rotary": dict(program.wcs.rotary_deg),
            "diameter": machine.diameter_mode, "options": dict(machine.post_options or {})}


class Goldens(unittest.TestCase):
    """Every post golden (``goldens/<post>/*.nc``, ``golden/grbl.*.nc``) runs without a crash on its fixture's
    stock: a 40 x 30 x 10 block, a Ø20 bar, a sheet."""

    def test_every_golden_is_crash_free(self):
        from tests.python.packages.cadgen.cam.test_cam_posts_dialects import CASES

        folder = Path(__file__).with_name("goldens")
        bar = C.StockShape("cylinder", np.eye(4), np.array([-10, -10, -30.0]), np.array([10, 10, 0.5]), 2,
                           np.zeros(3), 10.0)
        for post_name, kind, keys, golden in CASES:
            with self.subTest(post=post_name, golden=golden):
                program = F.program(kind, post_name, keys)
                text = (folder / post_name / f"{golden}.nc").read_text(encoding="utf-8")
                found = C.check(text, **_post_context(program, lathe_stock=bar))
                self.assertEqual(found, [], "\n".join(map(str, found)))

    def test_the_grbl_goldens_are_crash_free_as_one_job(self):
        from tests.python.packages.cadgen.cam.test_cam_posts import small_program

        program = small_program()
        texts = [p.read_text(encoding="utf-8") for p in sorted(Path(__file__).with_name("golden").glob("grbl.*.nc"))]
        context = _post_context(program)
        found = C.check(texts, **context)
        self.assertEqual(found, [], "\n".join(map(str, found)))


def _plan(document: Path, job: dict):
    """Plan ``job`` in process (no simulation, checks or files): (parsed job, stock, setup plans, op plans)."""
    from cadgen._internal.cam.job import parse_job
    from cadgen._internal.cam.part import read_part
    from cadgen._internal.cam.run import parse_operations, plan_setups
    from cadgen._internal.cam.stock import build_stock
    from tests.python.support.cam_fixtures import quiet

    with quiet():
        parsed = parse_job(job)
        part = read_part(Path(document), sheet_thickness_mm=parsed.stock.thickness_mm)
        stock = build_stock(parsed.stock, part, base_dir=parsed.base_dir)
        setups, ops, _ = plan_setups(parsed, parse_operations(parsed), part, stock)
    return parsed, stock, setups, ops


def _posted(planned, post_name: str, kind: str | None = None, keys: dict | None = None):
    """Every setup of a plan posted with ``post_name`` (machine keys ``keys``), as a controller gets it: ``[(setup id,
    [texts], check context)]``. A post that cannot run the toolpath raises its CamJobError."""
    from cadgen import __version__
    from cadgen._internal.cam import posts as registry
    from cadgen._internal.cam.posts.base import Program

    parsed, stock, setups, ops = planned
    kind = kind or parsed.machine.kind
    raw = {"kind": kind, "post": post_name, **(keys or {})}
    machine = dataclasses.replace(parsed.machine, kind=kind, post=post_name,
                                  post_options=registry.parse_options(post_name, raw),
                                  diameter_mode=raw.get("diameter_mode", parsed.machine.diameter_mode))
    post = registry.get_post(post_name, kind)
    tools = {t.id: t for t in parsed.tools}
    cam = {"machine": machine.as_dict(), "stock": stock.as_dict(), "tools": [t.as_dict() for t in parsed.tools],
           "setups": [{"id": sp.setup.id, "matrix": sp.wcs.matrix(), "heights": sp.heights.as_dict(),
                       "orientation": sp.setup.orientation} for sp in setups]}
    out = []
    for k, sp in enumerate(setups):
        program = Program(setup=sp.setup, wcs=sp.wcs, toolpath=sp.toolpath, tools=tools, machine=machine,
                          version=__version__, part="part.step", tolerance_mm=parsed.tolerance_mm,
                          clearance_z=sp.heights.clearance, retract_z=sp.heights.retract, setup_index=k,
                          setup_count=len(setups))
        used = {op.tool.id for op in ops if op.setup == sp.setup.id and op.tool is not None}
        texts = ([text for _, text in post.render_tool_files(program)] if post.split_by_tool and len(used) > 1
                 else [post.render(program)])
        out.append((sp.setup.id, texts, C.context_from_cam(cam, sp.setup.id, post=post_name)))
    return out


class EveryPost(unittest.TestCase):
    """Small parts of every machine kind, planned once and posted with every post that serves the kind (and the
    machine keys that change what a post writes): the checker finds no crash in any of them."""

    @classmethod
    def setUpClass(cls):
        from cadgen import cam
        from tests.python.support import cam_fixtures_cutting as cutting
        from tests.python.support import cam_fixtures_milling2d as m2d
        from tests.python.support import cam_fixtures_multiaxis as multi
        from tests.python.support import cam_fixtures_turning as turning
        from tests.python.support.cam_fixtures import class_directory, quiet

        folder = class_directory(cls)
        cls.plans = {}
        # A 2.5D bracket: face, slot, helix bore, peck drill, chamfer, profile with tabs; and its holes drilled and
        # tapped on their own, for the posts that can tap (one that cannot refuses the tap: no_post_support).
        step = m2d.bracket_step(folder)
        with quiet():
            features = cam.features(step)
        top = next(f["ref"] for f in features.faces if f["surface"] == "plane" and abs(f.get("z_mm", -1) - 12) < 1e-6)
        slot = next(f["ref"] for f in features.faces if f["surface"] == "plane" and abs(f.get("z_mm", -1) - 8) < 1e-6)
        bore = next(f["ref"] for f in features.faces if f["surface"] == "cylinder"
                    and abs(f.get("diameter_mm", 0) - 16) < 1e-6)
        tools = [{"id": "T1", "type": "flat", "diameter_mm": 6, "flutes": 3, "flute_length_mm": 20, "stickout_mm": 30},
                 {"id": "T2", "type": "flat", "diameter_mm": 4, "flutes": 3, "flute_length_mm": 12, "stickout_mm": 25},
                 {"id": "T3", "type": "drill", "diameter_mm": 5},
                 {"id": "T4", "type": "tap", "diameter_mm": 6, "pitch_mm": 1.0},
                 {"id": "T5", "type": "vee", "diameter_mm": 10, "angle_deg": 90, "flute_length_mm": 6,
                  "stickout_mm": 25}]
        cls.plans["mill"] = _plan(step, m2d.mill_job([
            {"op": "face", "tool": "T1"},
            {"op": "slot", "tool": "T2", "faces": [slot], "stepdown_mm": 2},
            {"op": "helix_bore", "tool": "T1", "faces": [bore]},
            {"op": "drill", "tool": "T3", "holes": {"diameter_mm": 5}, "cycle": "peck"},
            {"op": "chamfer", "tool": "T5", "faces": [top], "width_mm": 0.5, "loops": "inner"},
            {"op": "contour", "tool": "T1", "faces": [top], "loops": "outer", "stepdown_mm": 4,
             "tabs": {"count": 4}, "lead_in_mm": 2, "lead_out_mm": 2}], tools=tools))
        cls.plans["mill_tap"] = _plan(step, m2d.mill_job([
            {"op": "face", "tool": "T1"},
            {"op": "drill", "tool": "T3", "holes": {"diameter_mm": 5}, "cycle": "peck"},
            {"op": "drill", "tool": "T4", "holes": {"diameter_mm": 5}, "cycle": "tap"}], tools=tools))
        # A filleted block: z-level rough, then a waterline whose passes start a tool radius outside the stock's side
        # (its links once came down there through the stock the rough left on the wall).
        from tests.python.support import cam_fixtures_milling3d as m3d

        cls.plans["mill3d"] = _plan(m3d.fillet_block_step(folder), m3d.mill3d_job([
            {"op": "rough", "tool": "T1", "stock_to_leave_mm": 0.3, "stepdown_mm": 6},
            {"op": "waterline", "tool": "T2", "stepdown_mm": 3.0}]))
        # A turned shaft: face, centre drill, rough and finish outside and in, groove, thread, part off.
        shaft = turning.shaft_step(folder)
        with quiet():
            thread = turning.face_ref(cam.features(shaft), 20.0)
        cls.plans["lathe"] = _plan(shaft, turning.lathe_job([
            {"op": "turn_face", "tool": "T1"}, {"op": "turn_drill", "tool": "T6", "peck_mm": 5},
            {"op": "turn_rough", "tool": "T1"}, {"op": "turn_rough", "tool": "T7", "side": "id"},
            {"op": "turn_finish", "tool": "T2", "face": True}, {"op": "turn_finish", "tool": "T7", "side": "id"},
            {"op": "turn_groove", "tool": "T3"}, {"op": "turn_thread", "tool": "T4", "faces": [thread]},
            {"op": "turn_partoff", "tool": "T5"}]))
        # A 4th axis: a wrap (simultaneous A under TCP) and, on the same bar, an indexed setup.
        bar = multi.wrapped_cylinder_step(folder)
        stock = {"kind": "cylinder", "axis": "x", "diameter_mm": 32}
        cls.plans["mill4"] = _plan(bar, multi.multiaxis_job([
            {"op": "rotary", "tool": "T1", "mode": "rough", "stock_to_leave_mm": 0.3, "stepdown_mm": 2,
             "x_range_mm": [-4, 4], "sample_mm": 2.0},
            {"op": "rotary", "tool": "T2", "x_range_mm": [-4, 4], "stepover_mm": 2.0, "sample_mm": 2.0}],
            stock=stock))
        cls.plans["mill4_indexed"] = _plan(bar, multi.multiaxis_job([], stock=stock, setups=[
            {"id": "side", "orientation": "+Y", "origin": "stock-top-center",
             "operations": [{"op": "face", "tool": "T1"}]}]))
        # A 5-axis: 3+2 faces and a pocket on an angled block, swarf on a tapered boss, a dome finished 5-axis.
        angled = multi.angled_block_step(folder)
        with quiet():
            features = cam.features(angled)
        floor = np.asarray(multi.angled_pocket_centre()) - multi.ANGLED["pocket"][2] * np.asarray(
            multi.angled_normal())
        ref = multi.face_ref(features, surface="plane", near=floor, normal=multi.angled_normal())
        cls.plans["mill5_indexed"] = _plan(angled, multi.multiaxis_job([], kind="mill5", setups=[
            {"id": "top", "orientation": "+Z", "operations": [{"op": "face", "tool": "T1"}]},
            {"id": "tilt", "orientation": {"a_deg": multi.ANGLED["tilt_deg"]},
             "operations": [{"op": "face", "tool": "T1"}, {"op": "pocket", "tool": "T1", "faces": [ref]}]}]))
        taper = multi.tapered_boss_step(folder)
        with quiet():
            walls = [f["ref"] for f in cam.features(taper).faces if f["surface"] in ("bspline", "plane")
                     and abs(f["center_mm"][2] - (multi.TAPER["plate"][2] + multi.TAPER["height"] / 2)) < 1.0]
        clear = {"op": "pocket", "tool": "T1", "stepdown_mm": 4, "stock_to_leave_mm": 0.3,
                 "region": {"polygon": [[-33, -23], [33, -23], [33, 23], [-33, 23]], "bottom_z": -13}}
        cls.plans["mill5_swarf"] = _plan(taper, multi.multiaxis_job(
            [clear, {"op": "swarf", "tool": "T1", "faces": walls}], kind="mill5",
            machine={"rotary_limits_deg": {"a": [-30, 110]}}))
        dome = multi.dome_step(folder)
        with quiet():
            sphere = multi.face_ref(cam.features(dome), surface="sphere", near=[0, 0, 14], tolerance=2.0)
        job = multi.multiaxis_job([
            {"op": "rough", "tool": "T1", "stock_to_leave_mm": 0.5, "stepdown_mm": 4},
            {"op": "surface_normal", "tool": "T2", "faces": [sphere], "stepover_mm": 4.0, "sample_mm": 2.0,
             "lead_deg": 10, "max_tilt_deg": 35}], kind="mill5")
        job["setups"][0]["retract_mm"] = 5
        cls.plans["mill5_dome"] = _plan(dome, job)
        # Sheets: a laser, a plasma and a waterjet cut-out, and a wire EDM die.
        dxf = cutting.bracket_dxf(folder)
        for kind, thickness in (("laser", 3.0), ("plasma", 6.0), ("waterjet", 6.0)):
            cls.plans[kind] = _plan(dxf, cutting.cut_job(kind, thickness=thickness))
        cls.plans["wire_edm"] = _plan(dxf, cutting.cut_job("wire_edm", {"profiles": "holes", "skims": 1,
                                                                        "taper_deg": 0.5}, thickness=10.0,
                                                           material="tool-steel"))

    def assertCrashFree(self, plan_name: str, post_name: str, kind: str | None = None, keys: dict | None = None):
        with self.subTest(plan=plan_name, post=post_name, kind=kind, keys=keys):
            for setup, texts, context in _posted(self.plans[plan_name], post_name, kind, keys):
                found = C.check(texts, **context)
                self.assertEqual(found, [], f"setup {setup}:\n" + "\n".join(map(str, found)))

    def test_every_post_of_every_kind(self):
        from cadgen._internal.cam.job_errors import CamJobError
        from cadgen._internal.cam.posts import REGISTRY

        from cadgen._internal.cam.job_errors import PostRefusal

        plans = {"mill": ("mill", "mill3d", "mill_tap"), "router": ("mill", "mill_tap"), "lathe": ("lathe",),
                 "mill4": ("mill4", "mill4_indexed"), "mill5": ("mill5_indexed", "mill5_swarf", "mill5_dome"),
                 "laser": ("laser",),
                 "plasma": ("plasma",), "waterjet": ("waterjet",), "wire_edm": ("wire_edm",)}
        for kind, names in plans.items():
            for post_name, entry in REGISTRY.items():
                if kind not in entry.kinds:
                    continue
                for name in names:
                    if name == "mill_tap" and post_name == "grbl":
                        # GRBL cannot hold the feed to the spindle: the tap is refused on its operation, never posted.
                        with self.assertRaises(PostRefusal) as caught:
                            _posted(self.plans[name], post_name, kind)
                        self.assertIn("tap", str(caught.exception))
                        continue
                    if post_name == "mach3" and name == "mill4":
                        # Mach has no tool centre point control: the wrap is refused, never posted.
                        with self.assertRaises(CamJobError):
                            _posted(self.plans[name], post_name, kind)
                        continue
                    self.assertCrashFree(name, post_name, kind)

    def test_the_machine_keys_that_change_what_a_post_writes(self):
        for name, post_name, keys in (
                ("mill", "linuxcnc", {"cycles": False}), ("mill", "fanuc", {"cycles": False}),
                ("mill", "mach3", {"cycles": False}), ("mill", "haas", {"smoothing": "finish"}),
                ("mill", "grbl", {"spindle_spinup_s": 5}),
                ("lathe", "fanuc", {"cycles": True}), ("lathe", "haas", {"cycles": True}),
                ("lathe", "linuxcnc", {"diameter_mode": False}),
                ("laser", "marlin", {"inline_power": True}), ("laser", "marlin", {"laser_mode": "dynamic"}),
                ("plasma", "plasma", {"thc": False}), ("plasma", "mach3", {"thc": True}),
                ("waterjet", "waterjet", {"z_words": True}),
                ("wire_edm", "wire_edm", {"uv_words": True})):
            self.assertCrashFree(name, post_name, None, keys)

if __name__ == "__main__":
    unittest.main()
