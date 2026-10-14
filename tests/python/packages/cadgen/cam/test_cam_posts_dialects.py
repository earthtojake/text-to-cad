"""Posts past GRBL (track B3): a golden per post and machine kind on a small hand-built IR, every program read back to
the IR's own path, the dialect words each controller needs, and the teaching refusals."""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

import numpy as np

from cadgen._internal.cam.ir import ARC_CCW, ARC_CW, DWELL
from cadgen._internal.cam.job import parse_job
from cadgen._internal.cam.job_errors import CamJobError, PostRefusal
from cadgen._internal.cam.posts import POST_NAMES, REGISTRY, available, get_post
from tests.python.support import cam_fixtures_posts as F
from tests.python.support import gcode_reader

GOLDENS = Path(__file__).with_name("goldens")

#: (post, fixture kind, machine keys, golden name)
CASES = [
    ("linuxcnc", "mill", {}, "mill"),
    ("linuxcnc", "mill4", {}, "mill4"),
    ("linuxcnc", "mill4_wrap", {}, "mill4_wrap"),
    ("linuxcnc", "mill5", {}, "mill5"),
    ("linuxcnc", "mill5_tcp", {}, "mill5_tcp"),
    ("linuxcnc", "lathe", {}, "lathe"),
    ("fanuc", "mill", {}, "mill"),
    ("fanuc", "mill4", {}, "mill4"),
    ("fanuc", "mill5", {}, "mill5"),
    ("fanuc", "mill5_tcp", {}, "mill5_tcp"),
    ("fanuc", "lathe", {}, "lathe"),
    ("fanuc", "lathe", {"cycles": True, "program_number": 42}, "lathe_cycles"),
    ("haas", "mill", {"smoothing": "medium"}, "mill"),
    ("haas", "mill5", {}, "mill5"),
    ("haas", "mill5_tcp", {}, "mill5_tcp"),
    ("haas", "lathe", {}, "lathe"),
    ("haas", "lathe", {"cycles": True}, "lathe_cycles"),
    ("mach3", "mill", {}, "mill"),
    ("mach3", "mill4", {}, "mill4"),
    ("mach3", "router", {"cycles": False}, "router_expanded"),
    ("mach3", "plasma", {"thc": True, "dwell_ms": True}, "plasma"),
    ("marlin", "laser", {}, "laser"),
    ("marlin", "laser", {"laser_scale": 1000, "inline_power": True}, "laser_inline"),
    ("plasma", "plasma", {}, "plasma"),
    ("waterjet", "waterjet", {}, "waterjet"),
    ("wire_edm", "wire_edm", {}, "wire_edm"),
]
_KIND = {"mill5_tcp": "mill5", "mill4_wrap": "mill4"}


def render(post_name: str, kind: str, keys: dict):
    program = F.program(kind, post_name, keys)
    post = get_post(post_name, _KIND.get(kind, kind))
    return post, program, post.render(program)


def _nearest(a: np.ndarray, b: np.ndarray) -> float:
    """The largest distance from a point of ``a`` to the polyline through ``b`` (consecutive points joined)."""
    if not len(a):
        return 0.0
    if len(b) == 1:
        return float(np.linalg.norm(a - b[0], axis=1).max())
    p0, p1 = b[:-1], b[1:]
    d = p1 - p0
    length2 = np.maximum((d * d).sum(axis=1), 1e-18)
    best = np.full(len(a), np.inf)
    for chunk in range(0, len(a), 512):
        q = a[chunk:chunk + 512][:, None, :]
        t = np.clip(((q - p0[None]) * d[None]).sum(axis=2) / length2[None], 0.0, 1.0)
        gap = np.linalg.norm(q - (p0[None] + t[..., None] * d[None]), axis=2).min(axis=1)
        best[chunk:chunk + 512] = gap
    return float(best.max())


def read_back(post, program, text):
    machine = program.machine
    lathe = machine.kind == "lathe"
    start = program.toolpath.start
    if machine.kind == "wire_edm":
        start = (0.0, 0.0, 0.0)
    return gcode_reader.read(text, start=start, lathe=lathe, diameter=getattr(machine, "diameter_mode", True))


def compare(post, program, text, **overrides) -> list[str]:
    """:func:`gcode_reader.compare_moves` of ``text`` (posted by ``post`` from ``program``) against the IR as posted."""
    from cadgen._internal.cam.posts.base import SPINDLE_KINDS

    machine = program.machine
    path = F.with_entries(program.toolpath, lathe=machine.kind == "lathe")
    native = [(e.at, e.data["end"]) for e in path.events if e.kind == "cycle" and post.emits_cycle(e.data)]
    dwell_ms = bool(getattr(post, "dwell_ms", False)) or bool((machine.post_options or {}).get("dwell_ms"))
    options = {"planar": machine.kind in ("laser", "plasma", "waterjet", "wire_edm"),
               "spindle": machine.kind in SPINDLE_KINDS, "dwell_ms": dwell_ms, "native": native, **overrides}
    return gcode_reader.compare_moves(read_back(post, program, text), path, **options)


class Goldens(unittest.TestCase):
    def test_every_post_and_kind_matches_its_golden(self):
        for post_name, kind, keys, golden in CASES:
            with self.subTest(post=post_name, case=golden):
                _, _, text = render(post_name, kind, keys)
                path = GOLDENS / post_name / f"{golden}.nc"
                if not path.exists() or os.environ.get("CAM_UPDATE_GOLDENS"):  # pragma: no cover - (re)writes it
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(text, encoding="utf-8")
                self.assertEqual(path.read_text(encoding="utf-8"), text)
                self.assertEqual(text, render(post_name, kind, keys)[2], "posting is deterministic")

    def test_every_registered_post_is_built_and_opens_with_the_safety_block(self):
        self.assertEqual([name for name in POST_NAMES if not available(name)], [])
        for post_name, kind, keys, golden in CASES:
            with self.subTest(post=post_name, case=golden):
                text = render(post_name, kind, keys)[2].upper()
                head = "\n".join(text.splitlines()[:8])
                self.assertIn("NOT PROVEN ON A MACHINE. AIR-CUT IT OR RUN IT SINGLE-BLOCK FIRST", head)
                self.assertTrue(text.isascii())
                self.assertLessEqual(max(len(line) for line in text.splitlines()), 70)
                # What to verify is the machine kind's: tool lengths on a mill, never on a beam or a wire.
                machine = _KIND.get(kind, kind)
                if machine in ("mill", "mill4", "mill5", "router"):
                    self.assertIn("VERIFY THE WORK OFFSET", head)
                    self.assertIn("EVERY TOOL LENGTH", head)
                elif machine == "lathe":
                    self.assertIn("EVERY TOOL'S OFFSETS", head)
                else:
                    self.assertNotIn("TOOL LENGTH", text)
                    if post_name == "marlin":
                        self.assertNotIn("G54", text)
                        self.assertIn("THE ORIGIN IS WHERE THE HEAD STARTS", head)
                    elif post_name == "wire_edm":
                        self.assertIn("VERIFY THE START HOLE", head)
                    else:
                        self.assertIn("VERIFY THE WORK OFFSET", head)


class ReadBack(unittest.TestCase):
    """Every posted program, read by a controller-like reader, retraces the IR (native cycles the reader cannot
    expand are checked by their parameters instead)."""

    def _ir_points(self, program, post, masked_kinds, step=None):
        # The IR as posted: the first rapid after each tool change runs X Y first, then Z.
        path = F.with_entries(program.toolpath, lathe=program.machine.kind == "lathe")
        samples = path.sample(0.002, max_step_mm=step)
        keep = np.ones(len(samples.points), dtype=bool)       # the start too: a G43 Z line can sit on it
        for event in path.events:
            if event.kind == "cycle" and event.data.get("cycle") in masked_kinds and post.emits_cycle(event.data):
                keep &= ~((samples.move >= event.at) & (samples.move < event.data["end"]))
        if program.machine.kind == "wire_edm":
            first_cut = next(i for i in range(len(path.moves)) if path.moves[i]["kind"] != 0)
            before = samples.move < first_cut
            keep &= ~before
            keep[int(np.nonzero(before)[0].max())] = True          # where the wire is threaded
        return samples.points[keep]

    def test_the_posted_path_is_the_ir_path(self):
        for post_name, kind, keys, golden in CASES:
            with self.subTest(post=post_name, case=golden):
                post, program, text = render(post_name, kind, keys)
                read = read_back(post, program, text)
                # Dense points of one path against the polyline of the other, both ways.
                dense, _ = gcode_reader.sample(read, 0.002, max_step=0.25)
                line, _ = gcode_reader.sample(read, 0.002)
                begin = program.toolpath.start if program.machine.kind != "wire_edm" else (*read.g92[0], 0.0)
                dense, line = np.vstack([begin, dense]), np.vstack([begin, line])
                masked = ("thread", "turn_rough")
                ir_dense = self._ir_points(program, post, masked, 0.25)
                ir_line = self._ir_points(program, post, masked)
                planar = program.machine.kind in ("laser", "plasma", "waterjet", "wire_edm")
                if planar:
                    dense, line, ir_dense, ir_line = (a[:, :2] for a in (dense, line, ir_dense, ir_line))
                self.assertLess(_nearest(ir_dense, line), 0.012, "every IR point is on the posted path")
                if not read.threads and not read.roughs:
                    self.assertLess(_nearest(dense, ir_line), 0.012, "every posted point is on the IR path")
                points = line
                if not planar:
                    self.assertTrue(np.allclose(points[-1], program.toolpath.ends()[-1], atol=1e-3))

    def test_every_move_is_the_ir_moves_kind_at_its_feed(self):
        # The read-back above is geometry; this holds each posted move to the IR move it runs along: a rapid a rapid,
        # a cut at the IR's feed (so a modal F a post forgot to change shows), the spindle on through every cut, and
        # the dwells in order and length in the post's own unit.
        for post_name, kind, keys, golden in CASES:
            with self.subTest(post=post_name, case=golden):
                post, program, text = render(post_name, kind, keys)
                self.assertEqual([], compare(post, program, text))

    def test_lathe_cycles_read_back_to_their_parameters(self):
        for post_name in ("linuxcnc", "fanuc", "haas"):
            with self.subTest(post=post_name):
                post, program, text = render(post_name, "lathe", {})
                read = read_back(post, program, text)
                self.assertEqual(len(read.threads), 1)
                thread = read.threads[0]
                self.assertAlmostEqual(thread["root"], F.THREAD["x_crest"] - F.THREAD["depth_mm"], places=3)
                self.assertAlmostEqual(thread["depth"], F.THREAD["depth_mm"], places=3)
                self.assertAlmostEqual(thread["pitch"], F.THREAD["pitch_mm"], places=4)
                self.assertAlmostEqual(thread["z_end"], F.THREAD["z_end"], places=4)
                self.assertAlmostEqual(thread["x_clear"], F.THREAD["x_clear"], places=4)
                self.assertEqual(read.roughs, [], "roughing posts expanded unless machine.cycles is true")
                points, _ = gcode_reader.sample(read, 0.002, max_step=0.05)
                ir = F.with_entries(program.toolpath, lathe=True).sample(0.002, max_step_mm=0.05).points
                self.assertLess(_nearest(points, ir), 0.035, "the thread's final pass is the IR's last pass")
        for post_name in ("fanuc", "haas"):
            with self.subTest(post=post_name, cycles=True):
                post, program, text = render(post_name, "lathe", {"cycles": True})
                read = read_back(post, program, text)
                self.assertEqual(len(read.roughs), 1)
                rough = read.roughs[0]
                # The first profile block moves X only (Fanuc type I), from the cycle's start Z.
                self.assertEqual([tuple(float(v) for v in np.round(p, 6)) for p in rough["profile"]],
                                 [(F.ROUGH["profile"][0][0], F.ROUGH["z_start"])]
                                 + [tuple(p) for p in F.ROUGH["profile"]])
                self.assertAlmostEqual(rough["depth"], F.ROUGH["depth_mm"])
                self.assertAlmostEqual(abs(rough["u"]), 2 * F.ROUGH["allowance_x_mm"])

    def test_rotary_words_follow_the_ir(self):
        for post_name, kind in (("linuxcnc", "mill5_tcp"), ("fanuc", "mill5_tcp"), ("haas", "mill5_tcp"),
                                ("linuxcnc", "mill4_wrap")):
            with self.subTest(post=post_name, kind=kind):
                post, program, text = render(post_name, kind, {})
                read = read_back(post, program, text)
                moves = program.toolpath.moves
                ir = [tuple(np.round([m["x"], m["y"], m["z"], m["a"], m["b"], m["c"]], 4)) for m in moves
                      if int(m["kind"]) != DWELL]
                # The entry turns the rotary axes first, where the tool starts, before any linear move.
                ir.insert(0, tuple(np.round([*program.toolpath.start, *(moves[0][a] for a in "abc")], 4)))
                posted = [tuple(np.round([*mv.end, mv.abc["A"], mv.abc["B"], mv.abc["C"]], 4)) for mv in read.moves
                          if mv.kind != "dwell"]
                dedupe = lambda rows: [r for k, r in enumerate(rows) if k == 0 or r != rows[k - 1]]  # noqa: E731
                self.assertEqual(dedupe(ir), dedupe(posted))
                self.assertFalse(any(m.kind in ("arc_cw", "arc_ccw") for m in read.moves))
                self.assertEqual(read.tcp, [post.tcp_code] if kind == "mill5_tcp" else ["G43.4"])

    def test_tilted_setups_turn_the_table_after_each_tool_change(self):
        for post_name, words in (("linuxcnc", "G0 A30 C90"), ("haas", "G0 A30. C90.")):
            with self.subTest(post=post_name):
                text = render(post_name, "mill5", {})[2]
                lines = text.splitlines()
                changes = [k for k, line in enumerate(lines) if re.match(r"(N\d+ )?T\d+ M0?6$", line)]
                self.assertEqual(3, len(changes))
                for k in changes:
                    self.assertEqual(lines[k + 1], words)
                if post_name == "haas":
                    self.assertEqual(lines.count("G254"), 3)
                    self.assertEqual(lines.count("G255"), 3)
        text = render("fanuc", "mill5", {})[2]
        read = gcode_reader.read(text, start=(0, 0, 5))
        self.assertEqual(len(read.tilt), 3)
        self.assertEqual(read.tilt[0], {"X": 0.0, "Y": 0.0, "Z": 0.0, "I": -90.0, "J": -30.0, "K": 0.0})
        self.assertEqual(text.count("G69"), 3)
        moves = "\n".join(line for line in text.split("G21", 1)[1].splitlines() if "G28" not in line)
        self.assertNotIn(" A", moves)                           # G68.2 turns the table: no A/C words posted
        self.assertTrue(text.rstrip().endswith("G91 G28 Z0.\nG90\nG91 G28 A0. C0.\nG90\nG49\nM30\n%"))


class Dialects(unittest.TestCase):
    def test_fanuc_and_haas_write_decimal_points_percent_and_an_o_number(self):
        for post_name, o_line in (("fanuc", "O1000 "), ("haas", "O01000 ")):
            for kind in ("mill", "lathe"):
                with self.subTest(post=post_name, kind=kind):
                    text = render(post_name, kind, {})[2]
                    lines = text.splitlines()
                    self.assertEqual(lines[0], "%")
                    self.assertEqual(lines[-1], "%")
                    self.assertTrue(lines[1].startswith(o_line))
                    code = [re.sub(r"\([^)]*\)", "", line) for line in lines]
                    for line in code:
                        for word in re.findall(r"\b([XYZIJKRQUWABC])(-?[\d.]+)", line):
                            if line.startswith("G76"):           # its P and Q are microns, A an angle
                                continue
                            self.assertIn(".", word[1], f"{word} in {line!r}")
        self.assertTrue(render("fanuc", "lathe", {"cycles": True, "program_number": 42})[2].splitlines()[1]
                        .startswith("O0042 "))

    def test_fanuc_comments_are_upper_case_and_the_lathe_has_no_g90(self):
        text = render("fanuc", "lathe", {})[2]
        for comment in re.findall(r"\(([^)]*)\)", text):
            self.assertEqual(comment, comment.upper())
        self.assertNotIn("G90", text)                   # a turning cycle in G-code system A
        self.assertIn("T0101", text)
        self.assertIn("G50 S3000", text)
        self.assertIn("G96 S200 M3", text)
        self.assertIn("G99", text)
        self.assertIn("G76 P010060 Q50 R0.", text)
        self.assertIn("G76 X8.78 Z-15. P610 Q250 F1.", text)
        self.assertIn("G2 X12. Z-10. I2. K0.", text)    # X a diameter, I a radius

    def test_linuxcnc_lathe_and_tapping(self):
        text = render("linuxcnc", "lathe", {})[2]
        self.assertIn("G7", text.splitlines())
        self.assertIn("G96 D3000 S200 M3", text)
        self.assertIn("G95", text)
        self.assertIn("G76 P1 Z-15 I-2 J0.5 K1.22 R2 Q29.5 H1", text)
        radius = render("linuxcnc", "lathe", {"diameter_mode": False})[2]
        self.assertIn("G8", radius.splitlines())
        self.assertIn("G2 X6 Z-10 I2 K0", radius)
        mill = render("linuxcnc", "mill", {})[2]
        self.assertIn("G33.1 Z-3.5 K1", mill)
        self.assertNotIn("G84", mill)
        self.assertIn("G98 G83 X-10 Y5 Z-6 R1 Q3 F300", mill)
        self.assertTrue(mill.rstrip().endswith("M2"))

    def test_fanuc_rigid_taps_with_m29_and_haas_without(self):
        self.assertIn("M29 S500\nG99 G84", render("fanuc", "mill", {})[2])
        haas = render("haas", "mill", {"smoothing": "medium"})[2]
        self.assertNotIn("M29", haas)
        self.assertIn("G99 G84 X-10. Y5. Z-3.5 R2. F500.", haas)
        self.assertIn("G187 P2 E0.01", haas)
        self.assertIn("T1 M06", haas)

    def test_cycles_false_posts_every_cycle_as_moves(self):
        for post_name in ("linuxcnc", "fanuc", "haas", "mach3"):
            with self.subTest(post=post_name):
                text = render(post_name, "mill", {"cycles": False})[2]
                self.assertNotRegex(text, r"\bG8[1-9]\b|G73|G33\.1")
                if post_name != "mach3":
                    lathe = render(post_name, "lathe", {"cycles": False})[2]
                    self.assertNotIn("G76", lathe)
                    self.assertNotIn("G71", lathe)

    def test_mach3_sets_incremental_arc_centres_and_dwells_in_seconds(self):
        text = render("mach3", "mill", {})[2]
        self.assertIn("G91.1", text)
        self.assertIn("G4 P0.5", text)
        self.assertIn("G98 G83", text)
        self.assertIn("G4 P500", render("mach3", "mill", {"dwell_ms": True})[2])

    def test_torch_sequence(self):
        text = render("plasma", "plasma", {})[2]
        self.assertIn("G0 Z3.8\nM3\nG4 P0.4\nG1 Z1.5 F1000\nM101\n", text)
        self.assertIn("M102\nM5\nG0 Z10\n", text)
        quiet = render("plasma", "plasma", {"thc": False, "torch_z": False, "pierce_delay_s": 1.5})[2]
        self.assertNotIn("M101", quiet)
        self.assertNotIn("Z", "\n".join(l for l in quiet.splitlines() if not l.startswith("(")))
        mach = render("mach3", "plasma", {})[2]
        self.assertNotIn("M101", mach)                 # THC is off by default on Mach3
        self.assertIn("M3\nG4 P0.4", mach)

    def test_marlin_scales_power_and_never_ends_with_m30(self):
        text = render("marlin", "laser", {})[2]
        self.assertIn("M3 S204", text)                  # 0.8 of 255
        self.assertNotIn("M30", text)
        self.assertNotIn("G54", text.replace("; Verify the work offset G54", ""))
        self.assertIn("M8", text)                       # air assist
        inline = render("marlin", "laser", {"laser_scale": 1000, "inline_power": True})[2]
        self.assertIn("M3 I S0", inline)
        self.assertIn("G1 X5 S800 F1500", inline)
        self.assertIn("G0 S0\nX-15 Y-15", inline)
        self.assertNotIn("Z", "\n".join(l for l in text.splitlines() if not l.startswith(";")))
        dynamic = render("marlin", "laser", {"laser_mode": "dynamic"})[2]
        self.assertIn("M4 S204", dynamic)

    def test_waterjet_jet_words(self):
        text = render("waterjet", "waterjet", {})[2]
        self.assertIn("M3\nG4 P0.4\nG1 X5 F1500", text)
        self.assertEqual(text.count("M5"), 2)

    def test_wire_edm_start_point_threading_and_taper(self):
        text = render("wire_edm", "wire_edm", {})[2]
        self.assertIn("G92 X0. Y0.", text)
        # Fanuc-format automatic wire threading: M50 cuts the wire, M60 threads it.
        self.assertIn("(CUT THE WIRE FOR THE NEXT START HOLE)\nM50\nG0 X-15. Y-15.\n(THREAD THE WIRE)\nM60", text)
        self.assertIn("WIRE CENTRE", text)
        self.assertNotRegex(text, r"\bZ-?\d")
        tapered = F.wire({"uv_words": False}, beam={"taper_deg": 2.0, "thickness_mm": 20.0})
        g51 = get_post("wire_edm", "wire_edm").render(tapered)
        self.assertEqual(g51.count("G51 A2."), 2)
        self.assertEqual(g51.count("G50"), 3)          # the preamble's cancel and one per cut
        uv = get_post("wire_edm", "wire_edm").render(F.wire({"uv_words": True},
                                                            beam={"taper_deg": 2.0, "thickness_mm": 20.0}))
        read = gcode_reader.read(uv)
        lean = 20.0 * np.tan(np.radians(2.0))
        leans = [np.hypot(*m.uv) for m in read.moves if m.uv is not None and m.kind == "feed" and any(m.uv)]
        self.assertTrue(leans)
        self.assertTrue(np.allclose(leans, lean, atol=2e-3))
        # The square's first side runs +X: the wire's top leans to its left, +Y.
        side = next(m for m in read.moves if m.uv and m.start[1] == -12.0 and m.end == (12.0, -12.0, 0.0))
        self.assertAlmostEqual(side.uv[1], lean, places=3)
        self.assertNotIn("G2 ", uv)
        self.assertNotIn("G3 ", uv)
        comp = get_post("wire_edm", "wire_edm").render(F.wire({"wire_comp": "controller"},
                                                              beam={"offset_side": "left"}))
        self.assertEqual(comp.count("G41 D1"), 2)


    def test_a_skim_pass_keeps_the_wire_threaded(self):
        from dataclasses import replace

        from cadgen._internal.cam.ir import ToolpathBuilder

        base = F.wire()
        b = ToolpathBuilder((0, 0, 0))
        b.event("tool", tool="W1", number=1)
        for label in ("rough", "skim"):              # the same start hole, a pass and a skim
            b.event("beam", on=True, offset_side="left", **{"pass": label})
            b.feed(x=5, y=0, f=300)
            b.arc(5, 0, 0, centre=(0, 0, 0), clockwise=False, f=300)
            b.feed(x=0, y=0, f=300)
            b.event("beam", on=False)
        text = get_post("wire_edm", "wire_edm").render(replace(base, toolpath=b.build()))
        self.assertNotIn("M60", text)
        self.assertNotIn("M50", text)

    def test_a_radial_thread_infeed_posts_a_zero_tip_angle(self):
        from dataclasses import replace

        from cadgen._internal.cam.ir import Event, Toolpath

        program = F.lathe("fanuc")
        events = [Event(e.at, e.kind, {**e.data, "infeed_deg": 0.0} if e.data.get("cycle") == "thread" else e.data)
                  for e in program.toolpath.events]
        path = Toolpath(program.toolpath.moves, events, program.toolpath.ops, start=program.toolpath.start, lathe=True)
        self.assertIn("G76 P010000 Q50", get_post("fanuc", "lathe").render(replace(program, toolpath=path)))
        haas = F.lathe("haas")
        path = Toolpath(haas.toolpath.moves, events, haas.toolpath.ops, start=haas.toolpath.start, lathe=True)
        self.assertRegex(get_post("haas", "lathe").render(replace(haas, toolpath=path)), r"G76 .* A0\n")


class Refusals(unittest.TestCase):
    def assertRefuses(self, call, *fragments):
        with self.assertRaises(CamJobError) as caught:
            call()
        for fragment in fragments:
            self.assertIn(fragment, str(caught.exception))

    def test_events_a_machine_cannot_run(self):
        from cadgen._internal.cam.ir import Event, Toolpath

        program = F.mill("fanuc")
        path = program.toolpath
        beam = Toolpath(path.moves, list(path.events) + [Event(3, "beam", {"on": True})], path.ops, start=path.start)
        self.assertRefuses(lambda: get_post("fanuc", "mill").render(_with(program, beam)), "no beam")
        cut = F.cutting("plasma", "plasma")
        spun = Toolpath(cut.toolpath.moves, list(cut.toolpath.events) + [Event(1, "spindle", {"rpm": 100})],
                        (), start=cut.toolpath.start)
        self.assertRefuses(lambda: get_post("plasma", "plasma").render(_with(cut, spun)), "starts a spindle")
        wet = Toolpath(cut.toolpath.moves, list(cut.toolpath.events) + [Event(1, "coolant", {"mode": "flood"})],
                       (), start=cut.toolpath.start)
        self.assertRefuses(lambda: get_post("plasma", "plasma").render(_with(cut, wet)), "no coolant")
        wire = F.wire()
        drill = Toolpath(wire.toolpath.moves, list(wire.toolpath.events) + [Event(1, "cycle", {"cycle": "drill"})],
                         (), start=wire.toolpath.start)
        self.assertRefuses(lambda: get_post("wire_edm", "wire_edm").render(_with(wire, drill)), "drilling cycle")

    def test_axes_a_machine_does_not_have(self):
        wrap = F.simultaneous("fanuc", "mill5", "ac")
        three = F.mill("fanuc")
        from dataclasses import replace

        self.assertRefuses(lambda: get_post("fanuc", "mill").render(replace(wrap, machine=three.machine)),
                           "turns the A axis", "XYZ")
        bc = F.simultaneous("haas", "mill5", "bc")
        ac = F.simultaneous("haas", "mill5", "ac")
        self.assertRefuses(lambda: get_post("haas", "mill5").render(replace(bc, machine=ac.machine)),
                           "turns the B axis")
        lathe = F.lathe("fanuc")
        moves = lathe.toolpath.moves.copy()
        moves["y"][5] = 1.0
        from cadgen._internal.cam.ir import Toolpath

        off = Toolpath(moves, lathe.toolpath.events, lathe.toolpath.ops, start=lathe.toolpath.start, lathe=True)
        self.assertRefuses(lambda: get_post("fanuc", "lathe").render(_with(lathe, off)), "off the XZ plane")

    def test_a_simultaneous_wrap_needs_tool_centre_point_control(self):
        wrap = F.simultaneous("mach3", "mill4", "a")
        self.assertRefuses(lambda: get_post("mach3", "mill4").render(wrap), "no tool centre point control",
                           "linuxcnc, fanuc, haas")

    def test_wire_options_that_need_more_from_the_cut(self):
        self.assertRefuses(lambda: get_post("wire_edm", "wire_edm").render(F.wire({"wire_comp": "controller"})),
                           "which side")
        self.assertRefuses(lambda: get_post("wire_edm", "wire_edm").render(
            F.wire({"uv_words": True}, beam={"taper_deg": 2.0})), "thickness_mm")

    def test_machine_keys_belong_to_their_post(self):
        job = {"machine": {"kind": "mill", "post": "fanuc", "cycles": True, "program_number": 7},
               "material": "aluminum-6061", "stock": {"kind": "box", "margin_mm": 1},
               "tools": [{"id": "T1", "type": "flat", "diameter_mm": 6}],
               "setups": [{"id": "top", "operations": [{"op": "face", "tool": "T1"}]}]}
        parsed = parse_job(job)
        self.assertEqual(parsed.machine.post_options, {"cycles": True, "program_number": 7.0})
        self.assertEqual(parsed.machine.as_dict()["cycles"], True)
        bad = {**job, "machine": {"kind": "mill", "post": "fanuc", "laser_scale": 255}}
        self.assertRefuses(lambda: parse_job(bad), "unknown key 'laser_scale'", "cycles", "program_number")
        wrong = {**job, "machine": {"kind": "mill", "post": "fanuc", "cycles": "yes"}}
        self.assertRefuses(lambda: parse_job(wrong), "machine.cycles must be true or false")
        scale = {**job, "machine": {"kind": "laser", "post": "marlin", "laser_scale": 100}}
        self.assertRefuses(lambda: parse_job(scale), "machine.laser_scale", "255, 1000")
        big = F.mill("fanuc", {"program_number": 12345})
        self.assertRefuses(lambda: get_post("fanuc", "mill").render(big), "at most 9999")

    def test_every_post_serves_exactly_its_registered_kinds(self):
        for name, entry in REGISTRY.items():
            with self.subTest(post=name):
                post = get_post(name, entry.kinds[0])
                self.assertEqual(tuple(post.kinds), entry.kinds)
                self.assertEqual(post.extension, entry.extension)


def _job(post: str, build, *, kind: str = "mill", keys=None, tools=None, rotary=()):
    """A program on ``post`` from ``build(b)`` (a ToolpathBuilder starting at (0, 0, 5)) with the mill tools."""
    from cadgen._internal.cam.ir import Toolpath, ToolpathBuilder

    setup, wcs = F._setup()
    b = ToolpathBuilder((0, 0, 5))
    build(b)
    path = b.build()
    if rotary:
        path = Toolpath(path.moves, path.events, path.ops, start=path.start, rotary=rotary)
    return F._program(setup, wcs, path, F._tools(tools or F.MILL_TOOLS), F._machine(kind, post, keys))


def _start(b, tool="T1", rpm=10000):
    b.event("setup", id="top", wcs="G54", plain="Top", rotary={})
    b.begin_op(index=0, setup="top", op="pocket", plain="P", tool=tool)
    b.event("tool", tool=tool, number=int(tool[1:]))
    if rpm:
        b.event("spindle", rpm=rpm, dir="cw")


def _code(text: str) -> list[str]:
    return [line for line in text.splitlines() if line and not line.startswith(("(", ";", "%", "O"))]


class Safety(unittest.TestCase):
    """The CNC programmer's review: every finding as a test."""

    def assertRefuses(self, call, *fragments):
        with self.assertRaises(CamJobError) as caught:
            call()
        for fragment in fragments:
            self.assertIn(fragment, str(caught.exception))
        return str(caught.exception)

    # the drilling cycle names a planner may emit --------------------------------------------------------

    def test_every_drill_cycle_name_posts_natively_or_expanded(self):
        native = {
            "fanuc": {"drill": "G81", "spot": "G82", "peck": "G83", "chipbreak": "G73", "tap": "G84", "tap_left": "G74",
                      "ream": "G85", "bore": "G85", "bore_dwell": "G89", "bore_stop": "G86", "fine_bore": "G76"},
            "haas": {"drill": "G81", "spot": "G82", "peck": "G83", "chipbreak": "G73", "tap": "G84", "tap_left": "G74",
                     "ream": "G85", "bore": "G85", "bore_dwell": "G89", "bore_stop": "G86", "fine_bore": "G76"},
            "linuxcnc": {"drill": "G81", "spot": "G82", "peck": "G83", "chipbreak": "G73", "tap": "G33.1",
                         "tap_left": "G33.1", "ream": "G85", "bore": "G85", "bore_dwell": "G89", "bore_stop": "G86",
                         "fine_bore": None},
            "mach3": {"drill": "G81", "spot": "G82", "peck": "G83", "chipbreak": "G73", "tap": "G84", "tap_left": None,
                      "ream": "G85", "bore": "G85", "bore_dwell": "G89", "bore_stop": "G86", "fine_bore": None},
        }
        for post_name, codes in native.items():
            for name, code in codes.items():
                cycle = "tap" if name == "tap_left" else name

                def build(b):
                    _start(b, tool="T3" if cycle == "tap" else "T2", rpm=500)
                    b.rapid(x=-10, y=5)
                    data = {"cycle": cycle, "holes": [[-10, 5, 0]], "z_bottom": -6.0, "r_plane": 1.0,
                            "retract": "initial", "initial_z": 5.0, "feed": 300.0, "peck_mm": 3.0, "dwell_s": 0.5,
                            "pitch_mm": 1.0, "shift_mm": 0.1, **({"left_hand": True} if name == "tap_left" else {})}
                    h = b.begin_cycle(**data)
                    b.rapid(z=1)
                    b.feed(z=-6, f=300)
                    b.feed(z=1, f=300)
                    b.rapid(z=5)
                    b.end_cycle(h)
                    b.end_op()

                with self.subTest(post=post_name, cycle=name):
                    program = _job(post_name, build)
                    if code is None and cycle == "tap":
                        # No left-hand tapping cycle: a tap posted as moves breaks, so it is refused.
                        with self.assertRaises(PostRefusal) as caught:
                            get_post(post_name, "mill").render(program)
                        self.assertIn("thread mill", str(caught.exception))
                        self.assertEqual(0, caught.exception.operation)
                        continue
                    text = get_post(post_name, "mill").render(program)
                    if code:
                        self.assertRegex(text, rf"(?m)^(G9[89] )?{re.escape(code)}\b")
                    else:
                        self.assertNotRegex(text, r"\bG(7[3-6]|8[1-9])\b")
                        self.assertIn("G1 Z-6", text.replace("G1 Z-6.", "G1 Z-6"))
                    read = read_back(None, program, text)
                    self.assertAlmostEqual(-6.0, min(m.end[2] for m in read.moves), places=3)

    # 2: a native cycle in a simultaneous program ------------------------------------------------------------

    def _tcp_then_drill(self, post):
        import numpy as np

        from cadgen._internal.cam.ir import Toolpath

        def build(b):
            _start(b)
            b.rapid(x=-10, y=0)
            b.rapid(z=1)
            b.feed(z=0, f=500)
            for k in range(1, 4):
                b.feed(x=-10 + 2 * k, y=0, z=0, f=800)
            b.rapid(z=5)
            b.end_op()
            b.begin_op(index=1, setup="top", op="drill", plain="Drill", tool="T2")
            b.event("tool", tool="T2", number=2)
            b.event("spindle", rpm=7600, dir="cw")
            h = b.begin_cycle(cycle="drill", holes=[[-10, 5, 0]], z_bottom=-6.0, r_plane=1.0, retract="initial",
                              initial_z=5.0, feed=300.0)
            b.rapid(x=-10, y=5)
            b.rapid(z=1)
            b.feed(z=-6, f=300)
            b.rapid(z=5)
            b.end_cycle(h)
            b.end_op()

        program = _job(post, build, kind="mill5")
        moves = program.toolpath.moves.copy()
        a = np.zeros(len(moves))
        a[3:6] = [5, 10, 15]
        a[6] = 15
        moves["a"] = a
        path = Toolpath(moves, program.toolpath.events, program.toolpath.ops, start=(0, 0, 5), rotary=("a",))
        return _with(program, path)

    def test_a_simultaneous_program_posts_its_drilling_expanded_with_the_rotary_words(self):
        for post_name, tcp in (("fanuc", "G43.4"), ("haas", "G234"), ("linuxcnc", "G43.4")):
            with self.subTest(post=post_name):
                text = get_post(post_name, "mill5").render(self._tcp_then_drill(post_name))
                self.assertNotRegex(text, r"\bG8[1-9]\b")
                code = _code(text)
                second = code.index(next(line for line in code if re.match(r"(N\d+ )?T2 M0?6$", line)))
                # Rotaries first (the table to A0 with Z at the top), then TCP on, then X Y, then Z.
                after = code[second + 1:]
                self.assertRegex(after[0], r"^S7600 M3$")
                self.assertRegex(after[1], r"^G0 A0\.?$")
                self.assertEqual(f"{tcp} H2", after[2])
                self.assertRegex(after[3], r"^G0 X-10\.? Y5\.?$")
                read = read_back(None, self._tcp_then_drill(post_name), text)
                self.assertAlmostEqual(-6.0, min(m.end[2] for m in read.moves), places=3)
                self.assertEqual(0.0, read.moves[-1].abc["A"])

    # 4: tiny arcs -----------------------------------------------------------------------------------------

    def test_an_arc_shorter_than_the_posted_resolution_is_a_line_not_a_full_circle(self):
        def build(b):
            _start(b)
            b.rapid(x=10, y=0)
            b.rapid(z=-1)
            b.arc(10, 0.0004, -1, centre=(0, 0, 0), clockwise=False, f=500)
            b.feed(x=10, y=5, f=500)
            b.end_op()

        for post_name in ("linuxcnc", "fanuc", "grbl"):
            with self.subTest(post=post_name):
                text = get_post(post_name, "mill").render(_job(post_name, build))
                self.assertNotRegex(text, r"\bG[23]\b")

    def test_an_arc_whose_end_is_off_its_circle_is_refused(self):
        def build(b):
            _start(b)
            b.rapid(x=10, y=0)
            b.rapid(z=-1)
            b.arc(0, 10.5, -1, centre=(0, 0, 0), clockwise=False, f=500)
            b.end_op()

        self.assertRefuses(lambda: get_post("fanuc", "mill").render(_job("fanuc", build)), "from its centre",
                           "operation 1 (pocket), move 2")

    # 5, 6, 7: the entry, Z home before M6 and a rotary index, G91.1 -------------------------------------------

    def test_after_a_tool_change_x_y_come_first_then_the_tool_length_then_down(self):
        def build(b):
            _start(b)
            b.rapid(x=10, y=0, z=1)                        # a diagonal descent as the first move
            b.feed(z=-1, f=300)
            b.rapid(z=5)
            b.end_op()

        expected = {"linuxcnc": ["G53 G0 Z0", "T1 M6", "S10000 M3", "G0 X10 Y0", "G0 G43 Z5 H1", "Z1"],
                    # Mach3 is often never homed: Z up in the work offset, the new length at once, Z up again.
                    "mach3": ["G0 Z5", "T1 M6", "G43 H1", "G0 Z5", "S10000 M3", "G0 X10 Y0", "Z1"],
                    "fanuc": ["G91 G28 Z0.", "G90", "T1 M6", "S10000 M3", "G0 X10. Y0.", "G0 G43 Z5. H1", "Z1."],
                    "haas": ["N1 T1 M06", "S10000 M3", "G0 X10. Y0.", "G0 G43 Z5. H1", "Z1."],
                    "grbl": ["G0 Z5", "S10000 M3", "G4 P3", "X10 Y0", "Z1"]}
        for post_name, lines in expected.items():
            with self.subTest(post=post_name):
                code = _code(get_post(post_name, "mill").render(_job(post_name, build)))
                start = code.index(lines[0])
                self.assertEqual(lines, code[start:start + len(lines)])

    def test_linuxcnc_sets_incremental_arc_centres_and_homes_z_before_every_tool_change(self):
        for kind in ("mill", "lathe"):
            with self.subTest(kind=kind):
                self.assertIn("G91.1", render("linuxcnc", kind, {})[2].splitlines())
        text = render("linuxcnc", "mill", {})[2]
        lines = text.splitlines()
        for k, line in enumerate(lines):
            if re.match(r"T\d+ M6$", line):
                self.assertEqual("G53 G0 Z0", lines[k - 1])
        lathe = render("linuxcnc", "lathe", {})[2].splitlines()
        for k, line in enumerate(lathe):
            if re.match(r"T\d+ M6$", line):
                self.assertEqual("G30", lathe[k - 1])
        self.assertEqual(["G30", "M2"], lathe[-2:])

    def test_a_3_plus_2_index_without_a_tool_change_homes_z_first(self):
        from cadgen._internal.cam.ir import Event, Toolpath

        program = F.program("mill5", "linuxcnc")
        path = program.toolpath
        bare = Toolpath(path.moves, [e for e in path.events if e.kind not in ("tool", "spindle")], path.ops,
                        start=path.start, rotary=path.rotary)
        text = get_post("linuxcnc", "mill5").render(_with(program, bare))
        self.assertIn("G55\nG53 G0 Z0\nG0 A30 C90\n", text)

    # 8: arc fitting does not fold a ramp into a flat helix -------------------------------------------------

    def test_a_ramp_onto_a_circle_stays_a_ramp(self):
        import math

        def build(b):
            _start(b)
            b.rapid(x=10, y=0)
            b.rapid(z=1)
            b.feed(x=10 * math.cos(math.radians(5)), y=10 * math.sin(math.radians(5)), z=-2, f=500)
            for k in range(10, 181, 5):
                a = math.radians(k)
                b.feed(x=10 * math.cos(a), y=10 * math.sin(a), z=-2, f=500)
            b.rapid(z=5)
            b.end_op()

        program = _job("fanuc", build)
        text = get_post("fanuc", "mill").render(program)
        read = read_back(None, program, text)
        for move in read.moves:
            if move.kind in ("arc_cw", "arc_ccw"):
                self.assertEqual(move.start[2], move.end[2], "no helix: the ramp is a line of its own")
        ramp = next(m for m in read.moves if m.kind == "feed" and m.end[2] == -2.0)
        self.assertEqual(1.0, ramp.start[2])

    # 9, 10: a stop or a tool change restores the spindle and coolant ----------------------------------------

    def test_after_a_stop_the_spindle_and_coolant_come_back_on_before_the_next_move(self):
        def build(b):
            _start(b)
            b.event("coolant", mode="flood")
            b.rapid(x=10, y=0)
            b.rapid(z=1)
            b.event("stop", optional=False, message="Check chip")
            b.feed(z=-2, f=300)
            b.feed(x=0, f=600)
            b.rapid(z=5)
            b.end_op()

        for post_name, restore in (("fanuc", ["S10000 M3", "M8"]), ("grbl", ["S10000 M3", "G4 P3", "M8"]),
                                   ("linuxcnc", ["S10000 M3", "M8"])):
            with self.subTest(post=post_name):
                code = _code(get_post(post_name, "mill").render(_job(post_name, build)))
                k = code.index("M0")
                self.assertEqual(restore, code[k + 1:k + 1 + len(restore)])

    def test_iso_tool_changes_stop_the_spindle_and_coolant_and_bring_the_coolant_back(self):
        for post_name in ("linuxcnc", "fanuc", "haas", "mach3"):
            with self.subTest(post=post_name):
                code = _code(render(post_name, "mill", {})[2])
                for k, line in enumerate(code):
                    if re.match(r"T[23] M0?6$", line):
                        before = code[max(0, k - 6):k]
                        self.assertIn("M5", before)
                        self.assertIn("M9", before)
                        self.assertIn("M8", code[k:k + 6])
                self.assertNotIn("M9\nM5\nM9", "\n".join(code))
                self.assertNotRegex("\n".join(code), r"(?m)^(M[59])\n\1$")

    def test_a_cut_after_a_tool_change_without_a_spindle_start_is_refused(self):
        def build(b):
            b.event("setup", id="top", wcs="G54", plain="Top", rotary={})
            b.begin_op(index=0, setup="top", op="pocket", plain="P", tool="T1")
            b.event("tool", tool="T1", number=1)
            b.rapid(x=10, y=0)
            b.feed(z=-1, f=300)
            b.end_op()

        self.assertRefuses(lambda: get_post("linuxcnc", "mill").render(_job("linuxcnc", build)), "spindle stopped")

    # 11: GRBL laser -----------------------------------------------------------------------------------------

    def test_a_grbl_laser_pierces_at_constant_power_and_cuts_in_dynamic_mode(self):
        text = get_post("grbl", "laser").render(F.cutting("laser", "grbl"))
        self.assertIn("M3 S800\nG4 P0.4\nM4 S800\nG1", text)
        self.assertNotIn("M7", text)
        self.assertIn("M8", text)                          # air assist on GRBL's one coolant output

    def test_a_head_with_z_words_goes_up_before_its_first_x_y_rapid(self):
        # Where the head starts is unknown (a torch at its cut height, a laser at its focus): an X Y rapid first
        # drags it across the sheet and the parts tipped up in it.
        for post_name, kind, keys, first in (("plasma", "plasma", {}, "G0 Z10"), ("mach3", "plasma", {}, "G0 Z10"),
                                             ("grbl", "laser", {}, "G0 Z5"),
                                             ("waterjet", "waterjet", {"z_words": True}, "G0 Z5"),
                                             ("marlin", "laser", {"z_words": True}, "G0 Z5")):
            with self.subTest(post=post_name):
                motion = [line for line in _code(render(post_name, kind, keys)[2]) if line.startswith(("G0", "G1"))
                          and any(w[0] in "XYZ" for w in line.split()[1:])]
                self.assertEqual(motion[0], first)
        motion = [line for line in _code(render("plasma", "plasma", {"torch_z": False})[2]) if line.startswith("G0")]
        self.assertTrue(motion[0].startswith("G0 X"))       # no torch heights: no Z at all

    # 12: Marlin origin --------------------------------------------------------------------------------------

    def test_marlin_sets_the_origin_where_the_head_starts(self):
        text = render("marlin", "laser", {})[2]
        self.assertIn("G92 X0 Y0", text.splitlines())
        self.assertIn("G92 X0 Y0 Z0", render("marlin", "laser", {"z_words": True})[2].splitlines())

    # 13, 14: comments ---------------------------------------------------------------------------------------

    def test_comments_are_ascii_without_percent_or_semicolon_and_at_most_70_wide(self):
        from dataclasses import replace

        names = {"material": "aluminium – 6061 “T6”; 20% recycled", "part": "bracket’s (v2).step"}
        for post_name, kind in (("grbl", "mill"), ("fanuc", "mill"), ("haas", "mill"), ("wire_edm", "wire_edm"),
                                ("linuxcnc", "mill")):
            with self.subTest(post=post_name):
                program = replace(F.program(kind, post_name), **names)
                post = get_post(post_name, kind)
                text = "".join(t for _, t in post.render_tool_files(program))
                self.assertTrue(all(b < 0x80 for b in text.encode("utf-8")))
                lines = text.splitlines()
                self.assertLessEqual(max(len(line) for line in lines), 70)
                inner = [line[1:-1] for line in lines if line.startswith("(")] + \
                        [line.split("(", 1)[1] for line in lines if line.startswith("O")]
                self.assertFalse([c for c in inner if "%" in c or ";" in c], inner)
                self.assertEqual(lines.count("%"), 2 if post_name in ("fanuc", "haas", "wire_edm") else 0)

    # 15: numbers no controller should get ---------------------------------------------------------------

    def test_a_nan_or_negative_feed_is_refused_naming_the_move(self):
        for post_name in ("fanuc", "grbl", "marlin"):
            kind = "laser" if post_name == "marlin" else "mill"
            rpm = 0 if kind == "laser" else 10000

            def negative(b):
                _start(b, rpm=rpm)
                b.rapid(x=10, y=0)
                b.feed(z=-1, f=-300)
                b.end_op()

            def nan(b):
                _start(b, rpm=rpm)
                b.rapid(x=10, y=0)
                b.feed(z=-1, f=300)
                b.feed(x=float("nan"), f=600)
                b.end_op()

            with self.subTest(post=post_name):
                self.assertRefuses(lambda: get_post(post_name, kind).render(_job(post_name, negative, kind=kind)),
                                   "move 1", "feed is -300")
                self.assertRefuses(lambda: get_post(post_name, kind).render(_job(post_name, nan, kind=kind)),
                                   "operation 1 (pocket), move 2", "X is nan")

    # 16: GRBL spin-up ---------------------------------------------------------------------------------------

    def test_grbl_waits_for_the_spindle_only_when_it_starts_from_standstill(self):
        program = F.mill("grbl")
        files = get_post("grbl", "mill").render_tool_files(program)
        self.assertEqual(["T1", "T2"], [label for label, _ in files])
        for _, text in files:
            self.assertRegex(text, r"S\d+ M3\nG4 P3\n")

        def reversing(b):
            _start(b, rpm=500)
            b.rapid(x=10, y=0)
            b.rapid(z=1)
            b.feed(z=-1, f=300)
            b.event("spindle", rpm=500, dir="ccw")
            b.feed(z=1, f=300)
            b.end_op()

        text = get_post("grbl", "mill").render(_job("grbl", reversing))
        self.assertIn("S500 M3\nG4 P3\n", text)
        self.assertIn("S500 M4\nZ1\n", text)               # a reversal: no dwell there
        quick = get_post("grbl", "mill").render_tool_files(F.mill("grbl", {"spindle_spinup_s": 0}))
        self.assertNotIn("G4 P3", "".join(t for _, t in quick))

    # 17: headers ----------------------------------------------------------------------------------------

    def test_linuxcnc_tcp_says_it_needs_a_tcp_kinematics(self):
        self.assertIn("SWITCHKINS", render("linuxcnc", "mill5_tcp", {})[2].upper())

    # 18: the end of a 3+2 program ------------------------------------------------------------------------

    def test_3_plus_2_and_tcp_programs_end_with_z_home_then_the_table_at_rotary_zero(self):
        for post_name, kind, tail in (
                ("fanuc", "mill5", ["G69", "G91 G28 Z0.", "G90", "G91 G28 A0. C0.", "G90", "G49", "M30"]),
                ("haas", "mill5", ["G255", "G91 G28 Z0.", "G90", "G91 G28 A0. C0.", "G90", "G49", "M30"]),
                ("linuxcnc", "mill5", ["M5", "G49", "G53 G0 Z0", "G53 G0 A0 C0", "M2"]),
                ("mach3", "mill4", ["M5", "G0 Z5", "G0 A0", "G49", "M30"]),
                ("linuxcnc", "mill5_tcp", ["G49", "G53 G0 Z0", "G53 G0 A0 C0", "M2"])):
            with self.subTest(post=post_name, kind=kind):
                code = _code(render(post_name, kind, {})[2])
                self.assertEqual(tail, code[-len(tail):])

    # 19: rotary swings ------------------------------------------------------------------------------------

    def test_a_rapid_that_turns_the_table_out_of_a_cut_is_refused(self):
        import numpy as np

        from cadgen._internal.cam.ir import Toolpath

        program = F.simultaneous("linuxcnc", "mill5", "ac")
        moves = program.toolpath.moves.copy()
        moves["a"][13:] = 0.0                              # the retract swings A back while the tool is in the cut
        moves["c"][13:] = 0.0
        swing = Toolpath(moves, program.toolpath.events, program.toolpath.ops, start=(0, 0, 5), rotary=("a", "c"))
        self.assertRefuses(lambda: get_post("linuxcnc", "mill5").render(_with(program, swing)),
                           "straight out of a cut", "move 13")
        # From a rapid lift (in the air) the same turn is the planner's to make: posted as one TCP move.
        lifted = np.insert(moves, 13, moves[12])
        lifted["kind"][13] = 0
        lifted["z"][13] = moves["z"][12] + 1.0
        ok = Toolpath(lifted, program.toolpath.events, program.toolpath.ops, start=(0, 0, 5), rotary=("a", "c"))
        get_post("linuxcnc", "mill5").render(_with(program, ok))

    def test_a_rotary_indexed_between_passes_is_posted_under_tcp(self):
        # A rotary op's passes "along" X turn A only on rapids between passes, and its moves are the tip in the
        # part's frame at rotary zero: without TCP they would be posted where the turned part is not.
        def build(b):
            _start(b)
            b.rapid(x=-10, y=0)
            b.rapid(z=1)
            b.feed(x=10, f=500)
            b.rapid(z=5)
            b.rotate(a=30)
            b.rapid(x=-10, z=1)
            b.feed(x=10, f=500)
            b.rapid(z=5)
            b.end_op()

        text = get_post("linuxcnc", "mill4").render(_job("linuxcnc", build, kind="mill4"))
        self.assertIn("G43.4 H1", text)
        self.assertRefuses(lambda: get_post("mach3", "mill4").render(_job("mach3", build, kind="mill4")),
                           "no tool centre point control")

def _with(program, path):
    from dataclasses import replace

    return replace(program, toolpath=path)


if __name__ == "__main__":
    unittest.main()
