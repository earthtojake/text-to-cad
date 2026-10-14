"""Posts: what a second, independent CAM engine's posts and their review taught, one behaviour a test.

Comments a GRBL cannot misread, one O number a setup, no S0, a tap's F that follows its posted S, the header's speeds
per tool, depths never deeper than planned, arc fitting within its tolerance everywhere (straight runs, helices), a
read-back held to every move's kind and feed, taps and un-oriented fine bores refused where they would break, the
spin-up wait on every post, line numbers, GRBL's line length, the fine bore's shift, the back bore (G87, Haas G77, or
its moves with M19), rigid and floating taps, no G43 left at the end, coolant a
controller has no code for, no machine-coordinate move on an unhomed Mach3, and the mutations the read-back catches.
"""

from __future__ import annotations

import math
import re
import unittest
from dataclasses import replace

import numpy as np

from cadgen._internal.cam.job_errors import CamJobError, PostRefusal
from cadgen._internal.cam.posts import get_post
from cadgen._internal.cam.posts.base import fit_arcs
from tests.python.packages.cadgen.cam.test_cam_posts_dialects import _code, _job, _start, compare, render
from tests.python.support import cam_fixtures_posts as F
from tests.python.support import gcode_reader

ISO = ("linuxcnc", "fanuc", "haas", "mach3")


def _cut(b, f=1000):
    b.rapid(x=10, y=0)
    b.rapid(z=1)
    b.plunge(z=-1, f=300)
    b.feed(x=20, f=f)
    b.rapid(z=5)


class Comments(unittest.TestCase):
    def test_no_grbl_realtime_character_reaches_any_post(self):
        # GRBL's serial interrupt takes ! (feed hold), ~ (cycle start) and ? (status) out of every byte, comments too.
        note = "Check depth? then feed hold! ~resume"
        for post_name, kind in (("grbl", "mill"), ("fanuc", "mill"), ("haas", "mill"), ("linuxcnc", "mill"),
                                ("mach3", "mill"), ("marlin", "laser"), ("plasma", "plasma"),
                                ("waterjet", "waterjet"), ("wire_edm", "wire_edm"), ("grbl", "laser")):
            with self.subTest(post=post_name, kind=kind):
                program = replace(F.program(kind, post_name), notes=(note,), material="6061 [T6] {x} <y> $1 ^ @")
                text = "".join(t for _, t in get_post(post_name, kind).render_tool_files(program))
                self.assertFalse(set("!~?") & set(text), [line for line in text.splitlines() if set("!~?") & set(line)])
                self.assertIn("CHECK DEPTH THEN FEED HOLD RESUME", text.upper())


class ProgramNumbers(unittest.TestCase):
    def test_each_setup_has_its_own_o_number(self):
        for post_name, first, second in (("fanuc", "O1000 ", "O1001 "), ("haas", "O01000 ", "O01001 ")):
            with self.subTest(post=post_name):
                program = F.mill(post_name)
                one = get_post(post_name, "mill").render(replace(program, setup_index=0, setup_count=2))
                two = get_post(post_name, "mill").render(replace(program, setup_index=1, setup_count=2))
                self.assertTrue(one.splitlines()[1].startswith(first))
                self.assertTrue(two.splitlines()[1].startswith(second))
        wire = F.wire()
        self.assertIn("\nO1001 ", get_post("wire_edm", "wire_edm").render(replace(wire, setup_index=1, setup_count=2)))
        numbered = F.mill("fanuc", {"program_number": 42})
        self.assertIn("\nO0043 ", get_post("fanuc", "mill").render(replace(numbered, setup_index=1, setup_count=2)))
        last = F.mill("fanuc", {"program_number": 9999})
        with self.assertRaises(CamJobError) as caught:
            get_post("fanuc", "mill").render(replace(last, setup_index=1, setup_count=2))
        self.assertIn("at most 9999", str(caught.exception))


class SpindleSpeed(unittest.TestCase):
    def test_a_speed_that_rounds_to_s0_is_refused_on_its_operation(self):
        def build(b):
            _start(b, rpm=0.4)
            _cut(b)
            b.end_op()

        for post_name in ("grbl", "fanuc", "linuxcnc"):
            with self.subTest(post=post_name):
                with self.assertRaises(PostRefusal) as caught:
                    get_post(post_name, "mill").render(_job(post_name, build))
                self.assertIn("S0", str(caught.exception))
                self.assertEqual(0, caught.exception.operation)


class TapFeed(unittest.TestCase):
    def test_a_taps_feed_is_the_posted_s_times_the_pitch(self):
        tools = [*F.MILL_TOOLS[:2], {"id": "T3", "type": "tap", "diameter_mm": 8, "pitch_mm": 1.25}]

        def build(b):
            _start(b, tool="T3", rpm=636.6)
            b.rapid(x=-10, y=5)
            h = b.begin_cycle(cycle="tap", holes=[[-10, 5, 0]], z_bottom=-8.0, r_plane=2.0, retract="initial",
                              initial_z=5.0, feed=636.6 * 1.25, pitch_mm=1.25)
            b.rapid(z=2)
            b.feed(z=-8, f=636.6 * 1.25)
            b.event("spindle", rpm=636.6, dir="ccw")
            b.feed(z=2, f=636.6 * 1.25)
            b.event("spindle", rpm=636.6, dir="cw")
            b.rapid(z=5)
            b.end_cycle(h)
            b.end_op()

        for post_name, feed in (("fanuc", "F796.25"), ("haas", "F796.25"), ("mach3", "F796.25")):
            with self.subTest(post=post_name):
                text = get_post(post_name, "mill").render(_job(post_name, build, tools=tools))
                self.assertIn("S637 M3", text)
                self.assertRegex(text, rf"G8[4] .* {feed}\n")
        self.assertIn("M29 S637\n", get_post("fanuc", "mill").render(_job("fanuc", build, tools=tools)))


class Header(unittest.TestCase):
    def test_each_tool_line_names_its_speeds_and_fastest_feeds(self):
        def build(b):
            _start(b, rpm=8000)
            _cut(b, f=1000)
            b.event("spindle", rpm=9000, dir="cw")
            b.rapid(x=30, y=0)
            b.plunge(z=-1, f=250)
            b.feed(x=40, f=1200)
            b.rapid(z=5)
            b.end_op()

        text = get_post("linuxcnc", "mill").render(_job("linuxcnc", build))
        self.assertIn("T1: 6 mm flat: 8000 and 9000 rpm, feed 1200 mm/min, plunge 300 mm/min",
                      text.replace(")\n(", " "))
        self.assertIn("(T1: 6 MM FLAT: 12000 RPM, FEED 1990 MM/MIN)", render("fanuc", "mill", {})[2])
        self.assertIn("; T1: 0.2 mm kerf beam: feed 1500 mm/min", render("marlin", "laser", {})[2])


class Depths(unittest.TestCase):
    def test_a_cut_never_posts_deeper_than_planned(self):
        def build(b):
            _start(b, tool="T2", rpm=3000)
            b.rapid(x=10.0006, y=0)
            b.rapid(z=-0.0006)
            b.plunge(z=-1.0006, f=300)
            b.feed(x=20, f=1000)
            b.rapid(z=5)
            b.rapid(x=5, y=5)
            h = b.begin_cycle(cycle="drill", holes=[[5, 5, 0]], z_bottom=-8.0004, r_plane=2.0, retract="initial",
                              initial_z=5.0, feed=200.0)
            b.rapid(z=2)
            b.plunge(z=-8.0004, f=200)
            b.rapid(z=5)
            b.end_cycle(h)
            b.end_op()

        text = get_post("fanuc", "mill").render(_job("fanuc", build))
        self.assertIn("G0 X10.001 Y0.\n", text)                   # a rapid: nearest
        self.assertIn("Z-0.001\n", text)
        self.assertIn("G1 Z-1. F300.\n", text)                     # a cut: toward safe
        self.assertIn("G98 G81 X5. Y5. Z-8. R2.", text)            # a cycle's depth: toward its R plane
        grbl = get_post("grbl", "mill").render(_job("grbl", build))
        self.assertIn("G1 Z-1 F300\n", grbl)
        self.assertNotIn("Z-8.001", grbl)


def _deviation(points, pieces) -> float:
    """The farthest the fitted ``pieces`` stray from the polyline ``points`` and the polyline from them."""
    pts = np.asarray(points, dtype=float)
    worst, start, i = 0.0, pts[0], 0
    for piece in pieces:
        end = np.asarray(piece[1], dtype=float)
        j = i + 1 + int(np.argmin(np.linalg.norm(pts[i + 1:] - end, axis=1)))
        t = np.linspace(0.0, 1.0, 60)[:, None]
        line = np.vstack([a + (b - a) * t for a, b in zip(pts[i:j], pts[i + 1:j + 1])])
        if piece[0] == "arc":
            c = np.asarray(piece[2])
            radius = float(np.linalg.norm(start[:2] - c))
            off = np.abs(np.linalg.norm(line[:, :2] - c, axis=1) - radius)
            a0, a1 = (math.atan2(*(p[:2] - c)[::-1]) for p in (start, end))
            sweep = (a1 - a0) % (2 * math.pi)
            sweep = sweep - 2 * math.pi if piece[3] else sweep
            angles = a0 + sweep * np.linspace(0.0, 1.0, 400)
            arc = np.column_stack([c[0] + radius * np.cos(angles), c[1] + radius * np.sin(angles)])
            d = line[1:, :2] - line[:-1, :2]
            length2 = np.maximum((d * d).sum(axis=1), 1e-18)
            s = np.clip(((arc[:, None] - line[None, :-1, :2]) * d[None]).sum(axis=2) / length2[None], 0, 1)
            back = np.linalg.norm(arc[:, None] - (line[None, :-1, :2] + s[..., None] * d[None]), axis=2).min(axis=1)
            worst = max(worst, float(off.max()), float(back.max()))
        else:
            ab = end - start
            s = np.clip((line - start) @ ab / max(float(ab @ ab), 1e-18), 0.0, 1.0)
            worst = max(worst, float(np.linalg.norm(line - (start + s[:, None] * ab), axis=1).max()))
        start, i = end, j
    return worst


class ArcFitting(unittest.TestCase):
    def test_no_point_of_the_polyline_strays_past_the_tolerance(self):
        # Each point 0.006 off the circle (a slow wave) and each chord sagging 0.009: either alone is within 0.01,
        # together they were not (an arc 0.015 off its chords was fitted).
        n, radius, step = 41, 20.0, 2 * math.acos(1 - 0.009 / 20.0)
        pts = [((radius + 0.006 * math.sin(2 * math.pi * k / (n - 1))) * math.cos(k * step),
                (radius + 0.006 * math.sin(2 * math.pi * k / (n - 1))) * math.sin(k * step), 0.0) for k in range(n)]
        pieces = fit_arcs(pts, 0.01)
        self.assertIn("arc", [p[0] for p in pieces])
        self.assertLessEqual(_deviation(pts, pieces), 0.01 + 1e-6)

    def test_a_polygon_whose_chords_sag_past_the_tolerance_stays_lines(self):
        def polygon(radius, sides):
            return [(radius * math.cos(2 * math.pi * k / sides), radius * math.sin(2 * math.pi * k / sides), 0.0)
                    for k in range(sides + 1)]

        # A 64-gon of radius 20 sags 0.024 from its circle, a 90-gon 0.012: at 0.01 neither is an arc.
        for sides in (64, 90):
            self.assertEqual(["line"] * sides, [p[0] for p in fit_arcs(polygon(20, sides), 0.01)])
        fine = fit_arcs(polygon(20, 64), 0.05)
        self.assertEqual("arc", fine[0][0])
        self.assertLessEqual(len(fine), 2)
        # The same circle sampled at a quarter of the tolerance: arcs only, about its centre.
        dense = fit_arcs(polygon(20, 1000), 0.01)
        self.assertEqual({"arc"}, {p[0] for p in dense})
        self.assertTrue(all(np.allclose(p[2], (0, 0), atol=1e-6) for p in dense))

    def test_a_square_stays_four_lines_and_a_straight_run_is_one(self):
        square = [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0), (0, 0, 0)]
        pieces = fit_arcs(square, 0.05)
        self.assertEqual(["line"] * 4, [p[0] for p in pieces])
        self.assertEqual([[10, 0, 0], [10, 10, 0], [0, 10, 0], [0, 0, 0]], [list(p[1]) for p in pieces])
        run = fit_arcs([(x, 0, 0) for x in range(11)], 0.05)
        self.assertEqual([("line", [10, 0, 0])], [(p[0], list(p[1])) for p in run])
        # Back on itself is not a straight run.
        self.assertEqual(2, len(fit_arcs([(0, 0, 0), (10, 0, 0), (5, 0, 0)], 0.05)))

    def test_clockwise_and_helical_arcs_fit(self):
        turn = [(10 * math.cos(-math.pi * k / 32), 10 * math.sin(-math.pi * k / 32), -k / 32) for k in range(33)]
        pieces = fit_arcs(turn, 0.05, helical=True)
        self.assertEqual(["arc"], [p[0] for p in pieces])
        self.assertTrue(pieces[0][3])                              # clockwise
        self.assertTrue(np.allclose(pieces[0][1], (-10, 0, -1)))
        self.assertNotIn("arc", [p[0] for p in fit_arcs(turn, 0.05)])     # without helical arcs: lines
        flat = [(x, y, 0.0) for x, y, _ in turn]
        self.assertTrue(fit_arcs(flat, 0.05)[0][3])

    def test_fitting_is_deterministic(self):
        points = [(7.3 * math.cos(2 * math.pi * k / 50), 7.3 * math.sin(2 * math.pi * k / 50), -1.25)
                  for k in range(51)]
        one, two = fit_arcs(points, 0.02), fit_arcs(np.asarray(points), 0.02)
        self.assertEqual(repr([(p[0], list(p[1]), *p[2:]) for p in one]),
                         repr([(p[0], list(p[1]), *p[2:]) for p in two]))

    def test_a_straight_run_and_a_densified_helix_post_as_one_move_each(self):
        def build(b):
            _start(b)
            b.rapid(x=0, y=0)
            b.rapid(z=0)
            for k in range(1, 11):
                b.feed(x=2 * k, y=0, z=0, f=800)                   # a 10-segment straight run
            b.rapid(z=5)
            b.rapid(x=30, y=0)
            b.rapid(z=0)
            for k in range(1, 65):                                  # a full helical turn as 64 lines, 1 mm down
                a = 2 * math.pi * k / 64
                b.feed(x=25 + 5 * math.cos(a), y=5 * math.sin(a), z=-k / 64, f=600)
            b.rapid(z=5)
            b.end_op()

        for post_name in ("fanuc", "grbl", "linuxcnc"):
            with self.subTest(post=post_name):
                program = _job(post_name, build)
                post = get_post(post_name, "mill")
                text = post.render(program)
                code = _code(text)
                self.assertEqual(1, sum(1 for line in code if re.match(r"(G1 )?X20\.? (F800\.?)?$", line)), code)
                arcs = [line for line in code if re.match(r"G[23] ", line)]
                self.assertLessEqual(len(arcs), 2)
                self.assertTrue(all("Z" in line for line in arcs))
                self.assertLess(len(code), 40)
                self.assertEqual([], compare(post, program, text))
        flat = get_post("fanuc", "mill")
        flat.helical_arcs = False
        text = flat.render(_job("fanuc", build))
        self.assertFalse([line for line in _code(text) if re.match(r"G[23] ", line)])


class ReadBackCatches(unittest.TestCase):
    """The read-back (gcode_reader.compare_moves) is strict where a program would cut wrong: each broken program
    fails it."""

    def broken(self, post, program, text, old, new=""):
        self.assertEqual([], compare(post, program, text))
        self.assertIn(old, text)
        self.assertNotEqual([], compare(post, program, text.replace(old, new, 1)), f"{old!r} -> {new!r}")

    def test_a_feed_left_modal(self):
        for post_name in ("grbl", *ISO):
            with self.subTest(post=post_name):
                post, program = get_post(post_name, "mill"), F.mill(post_name)
                if post_name == "grbl":
                    program = post.tool_programs(program)[0][1]        # one file per tool: the first
                text = post.render(program)
                line = next(line for line in text.splitlines() if re.search(r" F1990\.?$", line))
                self.broken(post, program, text, line, re.sub(r" F1990\.?$", "", line))

    def test_a_dwell_in_the_wrong_unit(self):
        post, program, text = render("fanuc", "mill", {})
        self.broken(post, program, text, "G4 P500\n", "G4 P0.5\n")

    def test_a_missing_g80(self):
        def build(b):
            _start(b, tool="T2", rpm=3000)
            b.rapid(x=-10, y=5)
            h = b.begin_cycle(cycle="drill", holes=[[-10, 5, 0]], z_bottom=-6.0, r_plane=1.0, retract="initial",
                              initial_z=5.0, feed=300.0)
            b.rapid(z=1)
            b.plunge(z=-6, f=300)
            b.rapid(z=5)
            b.end_cycle(h)
            b.rapid(x=10, y=5)
            b.rapid(z=1)
            b.plunge(z=-2, f=300)
            b.rapid(z=5)
            b.end_op()

        for post_name in ISO:
            with self.subTest(post=post_name):
                program = _job(post_name, build)
                post = get_post(post_name, "mill")
                text = post.render(program)
                # Every cycle ends with G80, and the next move names its motion code: no bare X Y drills again.
                lines = text.splitlines()
                k = lines.index("G80")
                self.assertTrue(lines[k + 1].startswith("G0 "), lines[k + 1])
                self.broken(post, program, text, f"G80\n{lines[k + 1]}", lines[k + 1][3:])

    def test_a_missing_m3_after_a_bore(self):
        def build(b):
            _start(b, tool="T2", rpm=3000)
            b.rapid(x=-10, y=5)
            h = b.begin_cycle(cycle="bore_stop", holes=[[-10, 5, 0], [10, 5, 0]], z_bottom=-6.0, r_plane=2.0,
                              retract="r", initial_z=5.0, feed=200.0)
            for x in (-10, 10):
                b.rapid(x=x, y=5)
                b.rapid(z=2)
                b.plunge(z=-6, f=200)
                b.event("spindle", dir="off")
                b.rapid(z=2)
                b.event("spindle", rpm=3000, dir="cw")
            b.end_cycle(h)
            b.rapid(z=5)
            b.end_op()

        post, program = get_post("grbl", "mill"), _job("grbl", build)
        text = post.render(program)
        self.broken(post, program, text, "M5\nG0 Z2\nS3000 M3\nG4 P3\n", "M5\nG0 Z2\n")


def _fine_bore(shift_xy=(1.0, 0.0), shift=0.2):
    """One fine-bored hole, its expansion as the drilling op writes it: feed in, oriented stop, the bar shifted off the
    wall, out to R, back on the axis, the spindle on, up to the initial level."""
    def build(b):
        _start(b, tool="T2", rpm=3000)
        b.rapid(x=10, y=5)
        data = {"cycle": "fine_bore", "holes": [[10, 5, 0]], "z_bottom": -6.0, "r_plane": 2.0, "retract": "initial",
                "initial_z": 5.0, "feed": 200.0, "shift_mm": shift}
        if shift_xy is not None:
            data["shift_xy"] = list(shift_xy)
        h = b.begin_cycle(**data)
        b.rapid(z=2)
        b.plunge(z=-6, f=200)
        if shift_xy is not None:
            b.event("spindle", dir="off", orient=True)
            b.rapid(x=10 + shift * shift_xy[0], y=5 + shift * shift_xy[1])
            b.rapid(z=2)
            b.rapid(x=10, y=5)
        else:
            b.event("spindle", dir="off")
            b.rapid(z=2)
        b.event("spindle", rpm=3000, dir="cw")
        b.rapid(z=5)
        b.end_cycle(h)
        b.end_op()

    return build


class FineBore(unittest.TestCase):
    def test_g76_shifts_the_way_the_cycle_says_and_the_header_says_where_the_tip_points(self):
        fanuc = get_post("fanuc", "mill").render(_job("fanuc", _fine_bore((1.0, 0.0)))).replace(")\n(", " ")
        self.assertIn("G98 G76 X10. Y5. Z-6. R2. Q0.2 F200.", fanuc)
        self.assertIn("FINE BORE: THE BAR SHIFTS +X OFF THE WALL, SO AT THE SPINDLE ORIENT ITS TIP MUST POINT -X.", fanuc)
        self.assertIn("IT MUST BE +X.", fanuc)
        haas = get_post("haas", "mill").render(_job("haas", _fine_bore((0.0, 1.0))))
        self.assertIn("G98 G76 X10. Y5. Z-6. R2. I0. J0.2 F200.", haas)
        self.assertIn("shifts +Y off the wall, so at the spindle orient its tip must point -Y", haas.replace(")\n(", " "))

    def test_a_shift_the_cycle_cannot_make_is_posted_as_moves_with_an_oriented_stop(self):
        for post_name, shift, orient in (("fanuc", (0.0, -1.0), "M19"), ("linuxcnc", (1.0, 0.0), "M19 R0 Q10")):
            with self.subTest(post=post_name):
                post, program = get_post(post_name, "mill"), _job(post_name, _fine_bore(shift))
                text = post.render(program)
                self.assertNotRegex(text, r"\bG76\b")
                self.assertIn(f"M5\n{orient}\n", text)
                self.assertEqual([], compare(post, program, text))
                # The shift before the orient: the bar crosses the wall un-oriented.
                self.assertNotEqual([], compare(post, program, text.replace(f"{orient}\n", "", 1)))

    def test_a_post_that_cannot_orient_refuses_a_shifting_fine_bore(self):
        for post_name in ("mach3", "grbl"):
            with self.subTest(post=post_name):
                with self.assertRaises(PostRefusal) as caught:
                    get_post(post_name, "mill").render(_job(post_name, _fine_bore()))
                self.assertIn("orient", str(caught.exception))
                self.assertEqual(0, caught.exception.operation)

    def test_without_a_shift_direction_the_fine_bore_posts_as_before(self):
        fanuc = get_post("fanuc", "mill").render(_job("fanuc", _fine_bore(None, 0.1)))
        self.assertIn("G98 G76 X10. Y5. Z-6. R2. Q0.1 F200.", fanuc)
        self.assertNotIn("FINE BORE:", fanuc)
        self.assertNotIn("M19", get_post("mach3", "mill").render(_job("mach3", _fine_bore(None, 0.1))))


def _back_bore(shift_xy=(1.0, 0.0), shift=2.5, dwell=None, holes=((10.0, 5.0),)):
    """Back-bored holes, their expansion as the drilling op writes it: from the initial level an oriented stop, the
    bar shifted, down through the hole to R under the part, back on the axis, the spindle on, a feed up to Z, (a
    dwell,) a feed back down to R, oriented and shifted again, up to the initial level, back on the axis, the spindle
    on."""
    def build(b):
        _start(b, tool="T2", rpm=3000)
        b.rapid(x=holes[0][0], y=holes[0][1])
        data = {"cycle": "back_bore", "holes": [[x, y, 0] for x, y in holes], "z_bottom": -6.0, "r_plane": -20.0,
                "retract": "initial", "initial_z": 5.0, "feed": 200.0, "shift_mm": shift,
                "shift_xy": list(shift_xy)}
        if dwell:
            data["dwell_s"] = dwell
        h = b.begin_cycle(**data)
        sx, sy = shift * shift_xy[0], shift * shift_xy[1]
        for x, y in holes:
            b.rapid(x=x, y=y)
            for z_to in (-20.0, 5.0):
                b.event("spindle", dir="off", orient=True)
                b.rapid(x=x + sx, y=y + sy)
                b.rapid(z=z_to)
                b.rapid(x=x, y=y)
                b.event("spindle", rpm=3000, dir="cw")
                if z_to < 0:
                    b.feed(z=-6, f=200)
                    if dwell:
                        b.dwell(dwell)
                    b.feed(z=-20, f=200)
        b.end_cycle(h)
        b.end_op()

    return build


class BackBore(unittest.TestCase):
    def test_fanuc_posts_g87_with_its_q_shift_and_haas_g77_with_i_j(self):
        fanuc = get_post("fanuc", "mill").render(_job("fanuc", _back_bore(holes=((10.0, 5.0), (20.0, 5.0)))))
        self.assertIn("G98 G87 X10. Y5. Z-6. R-20. Q2.5 F200.\nX20. Y5.\nG80\n", fanuc)
        joined = fanuc.replace(")\n(", " ")
        self.assertIn("BACK BORE: THE BAR SHIFTS +X TO PASS ITS HEAD THROUGH THE HOLE, SO AT THE SPINDLE ORIENT ITS "
                      "TIP MUST POINT -X.", joined)
        self.assertIn("G87 SHIFTS ITS BAR BY Q ALONG THE DIRECTION THE CONTROL'S PARAMETERS SET: IT MUST BE +X.", joined)
        # The controller's cycle stops, orients and restarts the spindle itself: none of the expansion's M5/M19.
        self.assertNotIn("M19", fanuc)
        self.assertEqual(1, fanuc.count("M5\n"))                                       # the program's end
        self.assertIn("G98 G87 X10. Y5. Z-6. R-20. Q2.5 P300 F200.",
                      get_post("fanuc", "mill").render(_job("fanuc", _back_bore(dwell=0.3))))
        haas = get_post("haas", "mill").render(_job("haas", _back_bore((0.0, -1.0))))
        self.assertIn("G98 G77 X10. Y5. Z-6. R-20. I0. J-2.5 F200.", haas)
        self.assertNotRegex(haas, r"\bG87\b")
        self.assertIn("shifts -Y to pass its head through the hole, so at the spindle orient its tip must point +Y",
                      haas.replace(")\n(", " "))

    def test_a_back_bore_the_cycle_cannot_make_posts_as_moves_with_an_oriented_stop_before_each_shift(self):
        for post_name, build, keys, orient in (("linuxcnc", _back_bore(), None, "M19 R0 Q10"),
                                               ("fanuc", _back_bore((0.0, 1.0)), None, "M19"),
                                               ("fanuc", _back_bore(), {"cycles": False}, "M19"),
                                               ("haas", _back_bore(dwell=0.3), None, "M19")):
            with self.subTest(post=post_name, keys=keys):
                post, program = get_post(post_name, "mill"), _job(post_name, build, keys=keys)
                text = post.render(program)
                self.assertNotRegex(text, r"\bG(87|77)\b")
                self.assertEqual(2, text.count(f"M5\n{orient}\n"))
                self.assertEqual([], compare(post, program, text))
                # Without the orient the bar crosses the hole's wall with the spindle stopped anywhere.
                self.assertNotEqual([], compare(post, program, text.replace(f"{orient}\n", "", 1)))

    def test_a_post_that_cannot_orient_refuses_a_back_bore(self):
        for post_name in ("mach3", "grbl"):
            with self.subTest(post=post_name):
                with self.assertRaises(PostRefusal) as caught:
                    get_post(post_name, "mill").render(_job(post_name, _back_bore()))
                self.assertIn("cannot stop the spindle oriented (M19)", str(caught.exception))
                self.assertIn("fanuc G87, haas G77, linuxcnc", str(caught.exception))
                self.assertEqual(0, caught.exception.operation)


class TapHolders(unittest.TestCase):
    """``rigid`` on a tap cycle: true asks for the feed synchronised to the spindle, false a floating holder, left out
    the controller's own tapping cycle (as before)."""

    @staticmethod
    def build(rigid=None, left=False):
        def build(b):
            _start(b, tool="T3", rpm=500)
            b.rapid(x=-10, y=5)
            data = {"cycle": "tap", "holes": [[-10, 5, 0]], "z_bottom": -6.0, "r_plane": 2.0, "retract": "initial",
                    "initial_z": 5.0, "feed": 500.0, "pitch_mm": 1.0}
            if rigid is not None:
                data["rigid"] = rigid
            if left:
                data["left_hand"] = True
            h = b.begin_cycle(**data)
            b.rapid(z=2)
            b.feed(z=-6, f=500)
            b.event("spindle", rpm=500, dir="cw" if left else "ccw")
            b.feed(z=2, f=500)
            b.event("spindle", rpm=500, dir="ccw" if left else "cw")
            b.rapid(z=5)
            b.end_cycle(h)
            b.end_op()

        return build

    def test_each_post_writes_its_rigid_or_floating_tap(self):
        cases = [
            ("fanuc", None, False, "M29 S500\nG98 G84 X-10. Y5. Z-6. R2. F500."),
            ("fanuc", True, False, "M29 S500\nG98 G84 X-10. Y5. Z-6. R2. F500."),
            ("fanuc", False, False, ")\nG98 G84 X-10. Y5. Z-6. R2. F500."),
            ("haas", True, False, "G98 G84 X-10. Y5. Z-6. R2. F500."),
            ("haas", False, False, "G98 G84 X-10. Y5. Z-6. R2. F500."),
            ("linuxcnc", None, False, "G33.1 Z-6 K1"),
            ("linuxcnc", True, False, "G33.1 Z-6 K1"),
            ("linuxcnc", False, False, "G98 G84 X-10 Y5 Z-6 R2 F500"),
            ("linuxcnc", False, True, "G98 G74 X-10 Y5 Z-6 R2 F500"),
            ("mach3", None, False, "G98 G84 X-10 Y5 Z-6 R2 F500"),
            ("mach3", False, False, "G98 G84 X-10 Y5 Z-6 R2 F500"),
        ]
        for post_name, rigid, left, words in cases:
            with self.subTest(post=post_name, rigid=rigid, left=left):
                tools = [*F.MILL_TOOLS[:2], {**F.MILL_TOOLS[2], **({"hand": "left"} if left else {})}]
                post, program = get_post(post_name, "mill"), _job(post_name, self.build(rigid, left), tools=tools)
                text = post.render(program)
                self.assertIn(words, text)
                if rigid is False:
                    self.assertNotIn("M29", text)
                    self.assertNotIn("G33.1", text)
                self.assertEqual([], compare(post, program, text))

    def test_a_rigid_tap_on_mach3_is_refused_and_a_floating_one_is_not(self):
        with self.assertRaises(PostRefusal) as caught:
            get_post("mach3", "mill").render(_job("mach3", self.build(True)))
        message = str(caught.exception)
        self.assertIn("cannot synchronise the feed to the spindle", message)
        self.assertIn("\"rigid\": false", message)
        self.assertIn("thread_mill", message)
        self.assertEqual(0, caught.exception.operation)
        # GRBL taps neither way.
        for rigid in (True, False):
            with self.assertRaises(PostRefusal):
                get_post("grbl", "mill").render(_job("grbl", self.build(rigid)))


class Taps(unittest.TestCase):
    def build(self, b):
        _start(b, tool="T3", rpm=500)
        b.rapid(x=-10, y=5)
        h = b.begin_cycle(cycle="tap", holes=[[-10, 5, 0]], z_bottom=-6.0, r_plane=2.0, retract="initial",
                          initial_z=5.0, feed=500.0, pitch_mm=1.0)
        b.rapid(z=2)
        b.feed(z=-6, f=500)
        b.event("spindle", rpm=500, dir="ccw")
        b.feed(z=2, f=500)
        b.event("spindle", rpm=500, dir="cw")
        b.rapid(z=5)
        b.end_cycle(h)
        b.end_op()

    def test_a_tap_posted_as_moves_is_refused_naming_thread_milling(self):
        for post_name, keys, fragment in (("grbl", None, "has no tapping cycle"),
                                          ("fanuc", {"cycles": False}, "machine.cycles"),
                                          ("linuxcnc", {"cycles": False}, "machine.cycles")):
            with self.subTest(post=post_name):
                with self.assertRaises(PostRefusal) as caught:
                    get_post(post_name, "mill").render(_job(post_name, self.build, keys=keys))
                self.assertIn(fragment, str(caught.exception))
                self.assertIn("thread_mill", str(caught.exception))
                self.assertEqual(0, caught.exception.operation)
        # Where the controller taps, the tap is its cycle.
        self.assertIn("G98 G84 X-10. Y5. Z-6. R2. F500.", get_post("fanuc", "mill").render(_job("fanuc", self.build)))


class SpinUp(unittest.TestCase):
    def test_the_jobs_spin_up_dwells_after_every_spindle_start_on_every_post(self):
        for post_name, dwell in (("linuxcnc", "G4 P1.5"), ("fanuc", "G4 P1500"), ("haas", "G4 P1500"),
                                 ("mach3", "G4 P1.5"), ("grbl", "G4 P1.5")):
            with self.subTest(post=post_name):
                post, program = get_post(post_name, "mill"), F.mill(post_name)
                program = replace(program, machine=replace(program.machine, spindle_spinup_s=1.5))
                text = "".join(t for _, t in post.render_tool_files(program))
                starts = re.findall(r"S\d+ M3\n(.*)\n", text)
                self.assertTrue(starts)
                self.assertEqual({dwell}, set(starts))
                if post_name != "grbl":
                    self.assertEqual([], compare(post, program, text))
        self.assertNotIn("M3\nG4", render("linuxcnc", "mill", {})[2])       # LinuxCNC waits for its spindle
        self.assertIn("M3\nG4 P3\n", "".join(t for _, t in get_post("grbl", "mill").render_tool_files(F.mill("grbl"))))


class LineNumbers(unittest.TestCase):
    def test_haas_numbers_each_tool_change(self):
        lines = render("haas", "mill", {})[2].splitlines()
        self.assertEqual(["N1 T1 M06", "N2 T2 M06", "N3 T3 M06"], [line for line in lines if " M06" in line])

    def test_fanuc_numbers_every_block_when_asked(self):
        self.assertNotRegex(render("fanuc", "mill", {})[2], r"(?m)^N\d")
        post, program, text = render("fanuc", "mill", {"line_numbers": True})
        code = [line for line in text.splitlines() if line and line[0] not in "(%O"]
        numbers = [line.split()[0] for line in code]
        self.assertTrue(all(re.fullmatch(r"N\d+", n) for n in numbers), code[:3])
        self.assertEqual(len(numbers), len(set(numbers)))
        self.assertEqual([], compare(post, program, text))
        # A roughing cycle's profile keeps its own N numbers (G71 P and Q name them), none used twice.
        lathe = render("fanuc", "lathe", {"cycles": True, "line_numbers": True})[2]
        p, q = re.search(r"G71 P(\d+) Q(\d+)", lathe).groups()
        numbers = re.findall(r"(?m)^(N\d+) ", lathe)
        self.assertEqual(1, numbers.count(f"N{p}"))
        self.assertEqual(1, numbers.count(f"N{q}"))
        self.assertEqual(len(numbers), len(set(numbers)))


class GrblLines(unittest.TestCase):
    def test_every_line_fits_grbls_buffer_and_a_longer_one_is_a_bug(self):
        post = get_post("grbl", "mill")
        for _, text in post.render_tool_files(F.mill("grbl")):
            for line in text.splitlines():
                self.assertLessEqual(len("".join(line.split("(")[0].split())), 79)
                self.assertLessEqual(len(line), 127)
        with self.assertRaises(ValueError):
            post.check_lines("G1 " + "X1.234567 " * 10)
        with self.assertRaises(ValueError):
            post.check_lines("(" + "a" * 130 + ")")


class ProgramEnd(unittest.TestCase):
    def test_no_tool_length_is_left_on_at_the_end(self):
        for post_name in ISO:
            with self.subTest(post=post_name):
                text = render(post_name, "mill", {})[2]
                lengths = [e for e in gcode_reader.read(text, start=(0, 0, 5)).timeline
                           if isinstance(e, gcode_reader.Event) and e.kind == "length"]
                self.assertEqual("G49", lengths[-1].data["code"])
                code = _code(text)
                if post_name == "linuxcnc":
                    # LinuxCNC's G53 move still applies the length: G49 first, at each tool change and at the end.
                    homes = [k for k, line in enumerate(code) if line == "G53 G0 Z0"]
                    self.assertTrue(homes)
                    self.assertTrue(all(code[k - 1] == "G49" for k in homes[1:]))
                else:
                    self.assertEqual("G49", code[code.index("M30") - 1 - (post_name == "haas" and "G187" in code)])


class Coolant(unittest.TestCase):
    def build(self, mode):
        def build(b):
            _start(b)
            b.event("coolant", mode=mode)
            _cut(b)
            b.event("coolant", mode="off")
            b.end_op()

        return build

    def test_a_coolant_the_controller_has_no_code_for_is_switched_by_hand(self):
        for post_name, mode in (("grbl", "mist"), ("grbl", "air"), ("fanuc", "air"), ("linuxcnc", "air"),
                                ("mach3", "air")):
            with self.subTest(post=post_name, mode=mode):
                text = get_post(post_name, "mill").render(_job(post_name, self.build(mode)))
                code = _code(text)
                self.assertFalse({"M7", "M8"} & set(code), code)
                self.assertRegex(text, rf"(?i)\(coolant {mode}: the {post_name} post has no code for it, switch it on")
                self.assertRegex(text, rf"(?i)\(coolant {mode}: switch it off by hand")
        haas = _code(get_post("haas", "mill").render(_job("haas", self.build("air"))))
        self.assertIn("M83", haas)
        self.assertIn("M84", haas)
        self.assertIn("M7", _code(get_post("fanuc", "mill").render(_job("fanuc", self.build("mist")))))
        laser = get_post("grbl", "laser").render(F.cutting("laser", "grbl"))
        self.assertIn("M8", _code(laser))                       # a GRBL laser's air assist on its coolant output

    def test_switching_coolant_turns_the_first_off(self):
        def build(b):
            _start(b)
            b.event("coolant", mode="flood")
            _cut(b)
            b.event("coolant", mode="mist")
            _cut(b)
            b.end_op()

        self.assertIn("M8\nG0 X10 Y0", get_post("linuxcnc", "mill").render(_job("linuxcnc", build)))
        self.assertIn("M9\nM7\n", get_post("linuxcnc", "mill").render(_job("linuxcnc", build)))


class MachineCoordinates(unittest.TestCase):
    def test_an_unhomed_mach3_never_moves_in_machine_coordinates(self):
        for kind in ("mill", "mill4"):
            with self.subTest(kind=kind):
                post, program, text = render("mach3", kind, {})
                self.assertNotIn("G53", text)
                code = _code(text)
                for k, line in enumerate(code):
                    if re.match(r"T\d+ M6$", line):
                        self.assertEqual("G0 Z5", code[k - 1])
                self.assertEqual([], compare(post, program, text))
        homed = render("mach3", "mill4", {"homed": True})[2]
        self.assertIn("G53 G0 Z0\nT1 M6", homed)
        self.assertIn("G53 G0 Z0\nG53 G0 A0\nG49\nM30", homed)

    def test_grbl_never_homes(self):
        text = "".join(t for _, t in get_post("grbl", "mill").render_tool_files(F.mill("grbl")))
        self.assertNotRegex(text, r"\bG(28|30|53)\b")


if __name__ == "__main__":
    unittest.main()
