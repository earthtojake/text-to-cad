"""Posts: the GRBL golden on one small IR, its G-code read back to the IR's own path, arc fitting, the registry."""

from __future__ import annotations

import math
import os
import unittest
from pathlib import Path

import numpy as np

from cadgen._internal.cam.ir import ToolpathBuilder
from cadgen._internal.cam.job import parse_job
from cadgen._internal.cam.posts import get_post
from cadgen._internal.cam.posts.base import Program, fit_arcs
from cadgen._internal.cam.wcs import build_wcs
from tests.python.support import gcode_reader

GOLDENS = Path(__file__).with_name("golden")        # grbl.T1.nc, grbl.T2.nc

JOB = {
    "machine": {"kind": "mill", "post": "grbl"}, "material": "aluminum-6061",
    "stock": {"kind": "box", "margin_mm": 1},
    "tools": [{"id": "T1", "type": "flat", "diameter_mm": 6, "flutes": 3}, {"id": "T2", "type": "drill", "diameter_mm": 5}],
    "setups": [{"id": "top", "operations": [{"op": "face", "tool": "T1"}]}],
}


def small_program() -> Program:
    """Every kind of move and event on a 40 x 30 plate: a rounded square, a helix, a dwell, a tool change and a
    drill cycle (expanded, since GRBL has none)."""
    job = parse_job(JOB)
    setup = job.setups[0]
    corners = np.array([[-20, -15, -1], [20, 15, 0]], dtype=float)
    wcs = build_wcs(setup, stock_points=corners, part_points=corners)
    b = ToolpathBuilder((0, 0, 5))
    b.event("setup", id="top", wcs="G54", plain="Top")
    b.begin_op(index=0, setup="top", op="pocket", plain="Pocket", tool="T1")
    b.event("tool", tool="T1", number=1)
    b.event("spindle", rpm=13260, dir="cw")
    b.event("coolant", mode="flood")
    b.rapid(x=10, y=0)
    b.rapid(z=1)
    b.feed(z=0, f=600)
    b.arc(10, 0, -1, centre=(5, 0, 0), clockwise=False, f=1200)        # a helical full turn
    # A rounded square as short lines: the post fits arcs to its corners.
    for k in range(0, 91, 5):
        a = math.radians(k)
        b.feed(x=5 + 5 * math.cos(a), y=5 * math.sin(a), z=-1, f=1990)
    b.feed(x=-5, y=5, f=1990)
    b.dwell(0.5)
    b.rapid(z=5)
    b.end_op()
    b.begin_op(index=1, setup="top", op="drill", plain="Drill", tool="T2")
    b.event("tool", tool="T2", number=2)
    b.event("spindle", rpm=7640, dir="cw")
    handle = b.begin_cycle(cycle="peck", holes=[[-10, 5, 0], [10, 5, 0]], z_bottom=-6.0, r_plane=1.0,
                           retract="initial", initial_z=5.0, peck_mm=3.0, feed=300.0)
    for x in (-10, 10):
        b.rapid(x=x, y=5)
        b.rapid(z=1)
        b.feed(z=-3, f=300)
        b.rapid(z=1)
        b.rapid(z=-2.5)
        b.feed(z=-6, f=300)
        b.rapid(z=5)
    b.end_cycle(handle)
    b.end_op()
    b.event("coolant", mode="off")
    path = b.build()
    return Program(setup=setup, wcs=wcs, toolpath=path, tools={t.id: t for t in job.tools}, machine=job.machine,
                   version="TEST", part="plate.step", material="aluminium 6061", tolerance_mm=0.01)


class Grbl(unittest.TestCase):
    """GRBL has no tool table and cannot jog after M0: a two-tool setup posts one complete file per tool."""

    def setUp(self):
        self.program = small_program()
        self.post = get_post("grbl", "mill")
        self.files = self.post.render_tool_files(self.program)
        self.text = "".join(text for _, text in self.files)

    def test_the_goldens(self):
        self.assertEqual(["T1", "T2"], [label for label, _ in self.files])
        for label, text in self.files:
            with self.subTest(file=label):
                golden = GOLDENS / f"grbl.{label}.nc"
                if not golden.exists() or os.environ.get("CAM_UPDATE_GOLDENS"):  # pragma: no cover - (re)writes it
                    golden.write_text(text, encoding="utf-8")
                self.assertEqual(golden.read_text(encoding="utf-8"), text)

    def test_one_program_with_two_tools_is_refused(self):
        from cadgen._internal.cam.job_errors import CamJobError

        with self.assertRaises(CamJobError) as caught:
            self.post.render(self.program)
        self.assertIn("one file per tool", str(caught.exception))

    def test_each_file_opens_with_the_safety_block_names_its_tool_and_starts_safe(self):
        for k, (label, text) in enumerate(self.files):
            with self.subTest(file=label):
                lines = text.splitlines()
                self.assertIn("NOT proven on a machine. Air-cut it", lines[2])
                self.assertIn("work offset G54", lines[3])
                self.assertIn(f"File {k + 1} of 2: load {label}:", text.replace("\n(", " ").replace(")", ""))
                self.assertNotIn("M6", text)
                self.assertNotIn("M0", text)                   # no M0 tool change: GRBL cannot jog in Hold
                self.assertNotIn("G83", text)                  # GRBL posts the cycle expanded
                # Z up to the clearance height before the spindle starts, a spin-up dwell, X Y, then down.
                body = lines[lines.index("G54") + 1:]
                self.assertTrue(body[0].startswith(f"(Load {label}:"), body[0])
                self.assertEqual("G0 Z5", body[1])
                self.assertRegex(body[2], r"^S\d+ M3$")
                self.assertEqual("G4 P3", body[3])
                first_move = next(line for line in body[4:] if line.startswith(("G0", "G1", "X", "Y", "Z")))
                self.assertRegex(first_move, r"^(G0 )?X-?[\d.]+ Y-?[\d.]+$")     # G0 still modal after Z
                self.assertTrue(text.rstrip().endswith("M2"))
        # The second file carries the coolant the first switched on (a new file starts with it off).
        self.assertIn("M8", self.files[1][1])
        self.assertEqual(self.text, "".join(t for _, t in get_post("grbl", "mill").render_tool_files(small_program())))

    def test_a_one_tool_setup_is_one_file(self):
        from dataclasses import replace

        from cadgen._internal.cam.ir import Toolpath

        path = self.program.toolpath
        end = path.ops[0].end
        events = [e for e in path.events if e.at < end]
        one = replace(self.program, toolpath=Toolpath(path.moves[:end], events, path.ops[:1], start=path.start))
        files = self.post.render_tool_files(one)
        self.assertEqual([("T1", self.post.render(one))], files)
        self.assertNotIn("File 1 of", files[0][1])

    def test_the_gcode_reads_back_to_the_ir_path(self):
        read = gcode_reader.read(self.text, start=self.program.toolpath.start)
        points, _ = gcode_reader.sample(read, 0.002, max_step=0.05)
        ir = self.program.toolpath.sample(0.002, max_step_mm=0.05).points        # the start too: G0 Z5 sits on it
        # Every posted point lies on the IR's path, and every IR point on the posted path, within the tolerance.
        for a, b in ((points, ir), (ir, points)):
            gaps = np.min(np.linalg.norm(a[:, None, :] - b[None, :, :], axis=2), axis=1)
            self.assertLess(float(gaps.max()), 0.035)
        self.assertTrue(any(m.kind in ("arc_cw", "arc_ccw") for m in read.moves))
        self.assertIn("M8", read.coolant)
        self.assertTrue(np.allclose(points[-1], self.program.toolpath.ends()[-1]))


class ArcFitting(unittest.TestCase):
    def test_a_sampled_circle_fits_to_an_arc_and_a_zigzag_stays_lines(self):
        angles = np.linspace(0, math.pi, 40)
        arc = np.column_stack([10 * np.cos(angles), 10 * np.sin(angles), np.zeros(40)])
        pieces = fit_arcs(arc, 0.01)
        self.assertEqual(["arc"], [p[0] for p in pieces])
        self.assertAlmostEqual(0.0, pieces[0][2][0], places=6)
        self.assertFalse(pieces[0][3])                  # counter-clockwise
        zigzag = np.array([[0, 0, 0], [1, 1, 0], [2, 0, 0], [3, 1, 0], [4, 0, 0]], dtype=float)
        self.assertEqual(["line"] * 4, [p[0] for p in fit_arcs(zigzag, 0.01)])


class Registry(unittest.TestCase):
    def test_a_planned_post_teaches(self):
        from cadgen._internal.cam.job_errors import CamJobError
        from cadgen._internal.cam.posts import POST_NAMES, available

        missing = [name for name in POST_NAMES if not available(name)]
        if missing:
            from cadgen._internal.cam.posts import REGISTRY

            name = missing[0]
            with self.assertRaises(CamJobError) as caught:
                get_post(name, REGISTRY[name].kinds[0])
            self.assertIn("is planned but not in this cadgen yet", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
