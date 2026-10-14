"""Multi-axis jobs end to end on test-owned parts: a 3+2 pocket on an angled face, a 4th-axis wrap of a grooved bar,
swarf on a tapered boss and a 5-axis finish of a dome; their geometry checked against the exact part."""

from __future__ import annotations

import math
import re
import unittest
from pathlib import Path

import numpy as np

from tests.python.support.cam_fixtures import accessor_array, class_directory, quiet, read_glb
from tests.python.support.cam_fixtures_multiaxis import (
    ANGLED, CYLINDER, DOME, TAPER, angled_block_step, angled_normal, angled_pocket_centre, dome_step, face_ref,
    multiaxis_job, tapered_boss_step, wrapped_cylinder_step,
)


def plan_only(step: Path, job: dict):
    """The planned setups and operations (no simulation, no posting): the planners' own output."""
    from cadgen._internal.cam.job import parse_job
    from cadgen._internal.cam.part import read_part
    from cadgen._internal.cam.run import parse_operations, plan_setups
    from cadgen._internal.cam.stock import build_stock

    parsed = parse_job(job)
    operations = parse_operations(parsed)
    part = read_part(step)
    stock = build_stock(parsed.stock, part)
    setups, ops, _ = plan_setups(parsed, operations, part, stock)
    return parsed, setups, ops


def cutting(setup, op):
    """(tips in part mm, tool axes in part coordinates) of an operation's feed moves."""
    from cadgen._internal.cam.ir import FEED, PLUNGE
    from cadgen._internal.cam.multiaxis import path_axes

    path = setup.toolpath
    span = next(r for r in path.ops if r.index == op.index)
    index = np.arange(span.start, span.end)
    index = index[np.isin(path.moves["kind"][index], (FEED, PLUNGE))]
    tips = setup.wcs.from_wcs(np.column_stack([path.moves[k][index] for k in "xyz"]))
    return tips, path_axes(path, setup.wcs, index)


class IndexedSetup(unittest.TestCase):
    """A pocket square to a face tilted 30° about X, cut from a 3+2 setup on a 4th axis."""

    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        cls.directory = class_directory(cls)
        cls.step = angled_block_step(cls.directory)
        features = cam.features(cls.step)
        floor = np.asarray(angled_pocket_centre()) - ANGLED["pocket"][2] * np.asarray(angled_normal())
        cls.floor_ref = face_ref(features, surface="plane", near=floor, normal=angled_normal())
        cls.job = multiaxis_job([], setups=[
            {"id": "top", "orientation": "+Z", "operations": [{"op": "face", "tool": "T1"}]},
            {"id": "tilt", "orientation": {"a_deg": ANGLED["tilt_deg"]},
             "operations": [{"op": "pocket", "tool": "T1", "faces": [cls.floor_ref]}]}])
        with quiet():
            cls.result = cam.plan(cls.step, job=cls.job)
        cls.parsed, cls.setups, cls.ops = plan_only(cls.step, cls.job)

    def test_it_plans_ready_and_posts_the_rotation_before_the_cut(self):
        result = self.result
        self.assertTrue(result.ok, result.findings)
        self.assertEqual("ready", result.verdict["status"], result.findings)
        text = Path(next(p["file"] for p in result.posts if p["setup"] == "tilt")).read_text(encoding="utf-8")
        lines = text.splitlines()
        turn = next(i for i, line in enumerate(lines) if re.search(r"\bA30\b", line))
        cut = next(i for i, line in enumerate(lines) if line.startswith("G1"))
        self.assertLess(turn, cut)
        self.assertNotIn("G43.4", text)               # 3+2: rotate, then cut in three axes
        document, _ = read_glb(result.glb)
        setups = document["scenes"][0]["extras"]["cam"]["setups"]
        self.assertEqual({"a_deg": 30.0}, setups[1]["orientation"])
        # The tilted setup's tool axis is its matrix's third row (WCS +Z in part coordinates); its lines carry none.
        np.testing.assert_allclose(angled_normal(), setups[1]["matrix"][2][:3], atol=1e-9)
        self.assertFalse(any("_CAM_AXIS" in m["primitives"][0]["attributes"] for m in document["meshes"]))
        self.assertGreater(result.summary["removed_mm3"], 0.9 * 16 * 8 * 3)

    def test_every_move_of_the_tilted_setup_carries_its_rotary_position(self):
        top, tilt = self.setups
        self.assertEqual(("a",), tilt.toolpath.rotary)
        self.assertTrue((tilt.toolpath.moves["a"] == 30.0).all())
        self.assertTrue((top.toolpath.moves["a"] == 0.0).all())

    def test_the_pocket_reaches_its_floor_inside_its_outline(self):
        tilt = self.setups[1]
        tips, axes = cutting(tilt, self.ops[1])
        normal = np.asarray(angled_normal())
        np.testing.assert_allclose(np.tile(normal, (len(axes), 1)), axes, atol=1e-9)
        centre = np.asarray(angled_pocket_centre())
        floor = centre - ANGLED["pocket"][2] * normal
        depth = (tips - floor) @ normal
        self.assertAlmostEqual(0.0, float(depth.min()), delta=0.01)
        inside = depth < ANGLED["pocket"][2] - 1e-3        # below the angled face: in the pocket
        across = np.cross(normal, (1.0, 0.0, 0.0))
        half_x = ANGLED["pocket"][0] / 2 - 3.0
        half_y = ANGLED["pocket"][1] / 2 - 3.0
        self.assertLessEqual(float(np.abs((tips[inside] - centre)[:, 0]).max()), half_x + 0.01)
        self.assertLessEqual(float(np.abs((tips[inside] - centre) @ across).max()), half_y + 0.01)

    def test_a_tilt_the_machine_cannot_reach_is_refused(self):
        from cadgen import cam

        job = multiaxis_job([], setups=[{"id": "tilt", "orientation": {"a_deg": 30, "c_deg": 15},
                                         "operations": [{"op": "pocket", "tool": "T1", "faces": [self.floor_ref]}]}])
        result = cam.plan(self.step, job=job, out_dir=self.directory / "refused")
        self.assertFalse(result.ok)
        self.assertIn("this mill4 turns only A (about X), so c_deg cannot be reached", result.findings[0]["summary"])


def in_bar(points):
    """Whether part points lie inside the grooved, flatted bar (analytic)."""
    x, y, z = points[:, 0], points[:, 1], points[:, 2]
    radius = np.hypot(y, z)
    half = CYLINDER["length"] / 2
    inside = (radius < CYLINDER["radius"]) & (np.abs(x) < half)
    g0, g1 = CYLINDER["groove"]["x"]
    inside &= ~((x > g0) & (x < g1) & (radius > CYLINDER["groove"]["radius"]))
    f0, f1 = CYLINDER["flat"]["x"]
    inside &= ~((x > f0) & (x < f1) & (z > CYLINDER["flat"]["z"]))
    return inside


def ball_surface(centres, radius, count=48):
    """Points on spheres of ``radius`` round each centre (M * count, 3)."""
    k = np.arange(count) + 0.5
    phi = np.arccos(1 - 2 * k / count)
    theta = math.pi * (1 + 5 ** 0.5) * k
    unit = np.column_stack([np.cos(theta) * np.sin(phi), np.sin(theta) * np.sin(phi), np.cos(phi)])
    return (centres[:, None, :] + radius * unit[None, :, :]).reshape(-1, 3)


class Wrap(unittest.TestCase):
    """A grooved, flatted bar wrapped on a 4th axis with a 4 mm ball."""

    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        cls.directory = class_directory(cls)
        cls.step = wrapped_cylinder_step(cls.directory)
        stock = {"kind": "cylinder", "axis": "x", "diameter_mm": 32}
        op = {"op": "rotary", "tool": "T2", "x_range_mm": [-6, 14], "stepover_mm": 1.0, "sample_mm": 1.0}
        cls.job = multiaxis_job([op], stock=stock)
        with quiet():
            cls.result = cam.plan(cls.step, job=cls.job)
        cls.parsed, cls.setups, cls.ops = plan_only(cls.step, cls.job)
        rough = {**op, "mode": "rough", "passes": "along", "stock_to_leave_mm": 0.5, "stepdown_mm": 2.0,
                 "x_range_mm": [-5, 5]}
        cls.rough = plan_only(cls.step, multiaxis_job([rough], stock=stock))

    def test_it_plans_ready_and_posts_a_simultaneous_a(self):
        result = self.result
        self.assertTrue(result.ok, result.findings)
        self.assertEqual("ready", result.verdict["status"], result.findings)
        self.assertEqual("rotary", result.verdict["lite"][0]["op"])
        text = Path(result.posts[0]["file"]).read_text(encoding="utf-8")
        self.assertGreater(len(re.findall(r"^G1 .*\bA-?\d|^[XYZ].*\bA-?\d", text, re.M)), 100)
        path = self.setups[0].toolpath
        self.assertEqual(("a",), path.rotary)
        self.assertAlmostEqual(0.0, float(path.moves["a"][-1]), places=6)     # unwound back to the setup's A
        # The GLB's feed vertices carry the tool's axis (glTF axes), pointing at the bar's X axis where it cuts.
        document, blob = read_glb(result.glb)
        feed = next(m for m in document["meshes"] if m["name"] == "s1 feed")["primitives"][0]
        points = accessor_array(document, blob, feed["attributes"]["POSITION"]).astype(float) * 1000.0
        axis = accessor_array(document, blob, feed["attributes"]["_CAM_AXIS"]).astype(float)
        cutting = np.hypot(points[:, 1], points[:, 2]) < CYLINDER["radius"] + 0.5
        radial = points[cutting][:, 1:] / np.linalg.norm(points[cutting][:, 1:], axis=1, keepdims=True)
        np.testing.assert_allclose(radial, axis[cutting][:, 1:], atol=1e-3)
        np.testing.assert_allclose(0.0, axis[cutting][:, 0], atol=1e-6)

    def test_the_ball_never_enters_the_bar_and_reaches_the_groove_and_the_flat(self):
        tips, axes = cutting(self.setups[0], self.ops[0])
        r = 2.0
        centres = tips + r * axes
        self.assertFalse(in_bar(ball_surface(centres, r - 0.02)).any())
        radius = np.hypot(tips[:, 1], tips[:, 2])
        groove = np.abs(tips[:, 0]) < 0.9
        self.assertAlmostEqual(CYLINDER["groove"]["radius"], float(radius[groove].min()), delta=0.02)
        flat = (tips[:, 0] > 10.5) & (tips[:, 0] < 13.5) & (np.abs(tips[:, 1]) < 0.5) & (tips[:, 2] > 0)
        self.assertAlmostEqual(CYLINDER["flat"]["z"], float(tips[flat, 2].min()), delta=0.02)
        # The tool always points at the X axis.
        radial = np.column_stack([np.zeros(len(tips)), tips[:, 1], tips[:, 2]])
        radial /= np.linalg.norm(radial, axis=1, keepdims=True)
        np.testing.assert_allclose(radial, axes, atol=1e-6)

    def test_roughing_keeps_its_stock_to_leave(self):
        _, setups, ops = self.rough
        tips, axes = cutting(setups[0], ops[0])
        self.assertGreater(ops[0].meta["levels"], 1)
        centres = tips + 2.0 * axes
        self.assertFalse(in_bar(ball_surface(centres, 2.0 + 0.5 - 0.02)).any())

    def test_a_bar_along_another_axis_is_refused(self):
        from cadgen import cam

        job = multiaxis_job([{"op": "rotary", "tool": "T2"}], stock={"kind": "cylinder", "axis": "z"})
        result = cam.plan(self.step, job=job, out_dir=self.directory / "refused")
        self.assertFalse(result.ok)
        self.assertIn("turns the part about its X axis", result.findings[0]["summary"])


class Swarf(unittest.TestCase):
    """The tapered boss's four walls cut with the side of a flat, after a 3-axis clear."""

    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        cls.directory = class_directory(cls)
        cls.step = tapered_boss_step(cls.directory)
        cls.features = cam.features(cls.step)
        cls.walls = [f["ref"] for f in cls.features.faces if f["surface"] in ("bspline", "plane")
                     and abs(f["center_mm"][2] - (TAPER["plate"][2] + TAPER["height"] / 2)) < 1.0]
        clear = {"op": "pocket", "tool": "T1", "stepdown_mm": 4, "stock_to_leave_mm": 0.3,
                 "region": {"polygon": [[-33, -23], [33, -23], [33, 23], [-33, 23]], "bottom_z": -13}}
        cls.job = multiaxis_job([clear, {"op": "swarf", "tool": "T1", "faces": cls.walls}], kind="mill5",
                                machine={"rotary_limits_deg": {"a": [-30, 110]}})
        with quiet():
            cls.result = cam.plan(cls.step, job=cls.job)
        cls.parsed, cls.setups, cls.ops = plan_only(cls.step, cls.job)

    def test_it_plans_ready(self):
        self.assertEqual(4, len(self.walls))
        result = self.result
        self.assertTrue(result.ok, result.findings)
        self.assertEqual("ready", result.verdict["status"], result.findings)
        self.assertEqual(4, self.ops[1].meta["passes"])
        self.assertAlmostEqual(TAPER["lean_deg"], self.ops[1].meta["max_tilt_deg"], delta=0.01)

    def test_the_tool_lies_along_each_wall_one_radius_off_it_with_its_end_at_the_foot(self):
        tips, axes = cutting(self.setups[0], self.ops[1])
        lean = math.radians(TAPER["lean_deg"])
        bx, by = TAPER["bottom"]
        planes = []
        for sign in (1, -1):
            planes.append((np.array([sign * math.cos(lean), 0, math.sin(lean)]), np.array([sign * bx / 2, 0, 5.0])))
            planes.append((np.array([0, sign * math.cos(lean), math.sin(lean)]), np.array([0, sign * by / 2, 5.0])))
        distance = np.column_stack([(tips - point) @ normal for normal, point in planes])
        wall = np.argmin(np.abs(distance - 3.0), axis=1)
        on_wall = np.abs(distance[np.arange(len(tips)), wall] - 3.0) < 0.01
        # The tip's centre sits a radius off the wall, so its end's lowest point is at the wall's foot.
        foot = np.abs(tips[:, 2] - (TAPER["plate"][2] + 3.0 * math.sin(lean))) < 0.01
        self.assertGreater((on_wall & foot).sum(), 40)
        for k in np.nonzero(on_wall & foot)[0]:
            self.assertLess(abs(float(axes[k] @ planes[wall[k]][0])), 1e-6)     # the axis lies in the wall

    def test_walls_it_cannot_follow_are_refused(self):
        from cadgen import cam

        top = face_ref(self.features, surface="plane", near=[0, 0, 17])
        cases = {"faces the tool (a floor, not a wall)": {"faces": [top]},
                 "more than max_tilt_deg 10": {"faces": self.walls[:1], "max_tilt_deg": 10}}
        for message, keys in cases.items():
            job = multiaxis_job([{"op": "swarf", "tool": "T1", **keys}], kind="mill5")
            with self.subTest(message=message):
                result = cam.plan(self.step, job=job, out_dir=self.directory / "refused")
                self.assertFalse(result.ok)
                self.assertIn(message, result.findings[0]["summary"])


class SurfaceNormal(unittest.TestCase):
    """A 4 mm ball over the dome, its axis along the surface normal leaned 10° along the cut."""

    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        cls.directory = class_directory(cls)
        cls.step = dome_step(cls.directory)
        cls.dome = face_ref(cam.features(cls.step), surface="sphere", near=[0, 0, 14], tolerance=2.0)
        cls.job = multiaxis_job([{"op": "surface_normal", "tool": "T2", "faces": [cls.dome], "stepover_mm": 2.0,
                                  "sample_mm": 1.0, "lead_deg": 10, "max_tilt_deg": 35}], kind="mill5")
        cls.parsed, cls.setups, cls.ops = plan_only(cls.step, cls.job)

    def test_the_ball_rides_the_dome_with_its_axis_on_the_normal_led_and_capped(self):
        tips, axes = cutting(self.setups[0], self.ops[0])
        bz = DOME["block"][2]
        centre = np.array([0.0, 0.0, bz + DOME["rise"] - DOME["radius"]])
        balls = tips + 2.0 * axes
        reach = np.linalg.norm(balls - centre, axis=1)
        riding = np.abs(reach - (DOME["radius"] + 2.0)) < 0.03
        self.assertGreater(riding.mean(), 0.8)
        self.assertGreaterEqual(float(reach.min()), DOME["radius"] + 2.0 - 0.03)     # never into the dome
        tilt = np.degrees(np.arccos(np.clip(axes[:, 2], -1, 1)))
        self.assertLessEqual(float(tilt.max()), 35.0 + 1e-6)
        normal = (balls - centre) / reach[:, None]
        lead = np.degrees(np.arccos(np.clip(np.einsum("ij,ij->i", normal, axes), -1, 1)))
        near_top = riding & (normal[:, 2] > math.cos(math.radians(20)))
        self.assertTrue(np.all(np.abs(lead[near_top] - 10.0) < 1.5), lead[near_top])
        self.assertEqual(("a", "c"), self.setups[0].toolpath.rotary)

    def test_every_turn_between_lines_starts_in_the_air_and_the_plan_posts(self):
        from cadgen import cam
        from cadgen._internal.cam.ir import RAPID

        path = self.setups[0].toolpath
        span = next(r for r in path.ops if r.index == self.ops[0].index)
        moves = path.moves[span.start:span.end]
        abc = np.column_stack([moves[k] for k in "ac"])
        turning = np.nonzero(np.any(np.abs(np.diff(abc, axis=0)) > 1e-9, axis=1))[0] + 1
        rapid_turns = [i for i in turning if moves["kind"][i] == RAPID]
        self.assertTrue(rapid_turns)
        # The move before a rapid that turns the table is never a cut: the tool left it up its axis first.
        self.assertTrue(all(moves["kind"][i - 1] == RAPID for i in rapid_turns))
        with quiet():
            result = cam.plan(self.step, job=self.job, out_dir=self.directory / "posted")
        self.assertTrue(result.ok, result.findings)

    def test_only_a_ball_may_follow_the_normal(self):
        from cadgen import cam

        job = multiaxis_job([{"op": "surface_normal", "tool": "T1", "faces": [self.dome]}], kind="mill5")
        result = cam.plan(self.step, job=job, out_dir=self.directory / "refused")
        self.assertFalse(result.ok)
        self.assertIn("cuts with a ball tool", result.findings[0]["summary"])


if __name__ == "__main__":
    unittest.main()
