#!/usr/bin/env python3

"""3D printing's measurements (``cad.trimesh._printing``) and its check (``cad.<type>.dfm(...,
process="printing")``).

Each part is built with build123d so the correct answer is known from the
construction rather than from a recorded run: a 2 mm wall is 2 mm because it
was built that way, and a 30 deg underside is below a 45 deg limit by
geometry. A regression then shows up as a disagreement with the model, not as
a diff against whatever the tool happened to print last time.
"""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

import trimesh
from build123d import Box, Polyline, Pos, Rotation, export_stl, extrude, make_face

import cad
from cad.trimesh import _printing as dfam_tool


def _stl(part, tmp: Path, name: str) -> str:
    path = tmp / f"{name}.stl"
    export_stl(part, str(path))
    return str(path)


def _wedge(angle_deg: float, length: float = 30.0, width: float = 12.0):
    """Cantilever whose underside rises at angle_deg from horizontal.

    Vertex order matters: built the other way up this is a ramp, which is
    self-supporting and tests nothing.
    """
    h = max(length * math.tan(math.radians(angle_deg)), 0.6)
    pts = [(0, 0, 0), (length, h, 0), (0, h, 0), (0, 0, 0)]
    return Rotation(90, 0, 0) * extrude(make_face(Polyline(*pts)), width)


def _hollow_box(wall: float, outer: float = 24.0, height: float = 16.0):
    inner = max(outer - 2 * wall, 0.5)
    return Box(outer, outer, height) - Pos(0, 0, wall) * Box(inner, inner, height)


class MeshFactsTest(unittest.TestCase):
    def test_solid_box_is_watertight_single_body(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            mesh = dfam_tool._load(_stl(Box(20, 20, 15), tmp, "box"))
            facts = dfam_tool._mesh_facts(mesh)

        self.assertTrue(facts["watertight"])
        self.assertEqual(facts["body_count"], 1)
        self.assertEqual(facts["euler_number"], 2)
        self.assertAlmostEqual(facts["volume_mm3"], 6000.0, delta=1.0)


class OverhangTest(unittest.TestCase):
    def test_underside_below_limit_is_flagged_above_limit_is_not(self) -> None:
        """A 30 deg underside is a violation at 45 deg and clear at 20 deg."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = _stl(_wedge(30.0), tmp, "wedge30")
            mesh = dfam_tool._load(path)
            strict = dfam_tool._overhang_facts(mesh, 45.0)
            lenient = dfam_tool._overhang_facts(mesh, 20.0)

        self.assertGreater(strict["down_facing_area_below_limit_mm2"], 0.0)
        self.assertEqual(lenient["down_facing_area_below_limit_mm2"], 0.0)
        self.assertEqual(strict["angle_limit_used_deg"], 45.0)

    def test_face_resting_on_plate_is_not_counted(self) -> None:
        """The base is carried by the bed, so a plain box needs no support."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            mesh = dfam_tool._load(_stl(Box(20, 20, 15), tmp, "box"))
            facts = dfam_tool._overhang_facts(mesh, 45.0)

        self.assertEqual(facts["down_facing_area_below_limit_mm2"], 0.0)
        self.assertEqual(facts["face_count_below_limit"], 0)


class WallThicknessTest(unittest.TestCase):
    def test_measured_wall_matches_constructed_wall(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            mesh = dfam_tool._load(_stl(_hollow_box(2.0), tmp, "wall2"))
            facts = dfam_tool._wall_facts(mesh, samples=600)

        self.assertAlmostEqual(facts["median_mm"], 2.0, delta=0.4)

    def test_thinner_wall_measures_thinner(self) -> None:
        """Ordering must hold even where absolute sampling error does not."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            thin = dfam_tool._wall_facts(
                dfam_tool._load(_stl(_hollow_box(0.8), tmp, "wall08")), samples=600
            )
            thick = dfam_tool._wall_facts(
                dfam_tool._load(_stl(_hollow_box(3.0), tmp, "wall30")), samples=600
            )

        self.assertLess(thin["median_mm"], thick["median_mm"])


class OrientationTest(unittest.TestCase):
    def test_flipping_a_wedge_removes_its_support_requirement(self) -> None:
        """The same wedge is self-supporting once turned over.

        This is the whole point of ranking orientations, so if it stops
        holding, the ranking is not doing anything useful.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            mesh = dfam_tool._load(_stl(_wedge(30.0), tmp, "wedge30"))
            facts = dfam_tool._orientation_facts(mesh, 45.0)

        candidates = facts["candidates"]
        self.assertEqual(len(candidates), 6)

        current = next(c for c in candidates if c["orientation"] == "current_plus_z")
        best = min(candidates, key=lambda c: c["support_area_mm2"])

        self.assertGreater(current["support_area_mm2"], 0.0)
        self.assertEqual(best["support_area_mm2"], 0.0)
        for candidate in candidates:
            self.assertGreater(candidate["build_height_mm"], 0.0)


class FormatCoverageTest(unittest.TestCase):
    """Every 3D mesh type's check reads its file as the viewer does (millimetres, Z up), and the
    Python API measures any mesh trimesh reads (an .obj, a .ply).

    A format that is claimed but unreadable is worse than one that is not
    claimed, because the failure surfaces at the user rather than here.
    """

    def test_each_mesh_type_loads_and_measures(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            stl = _stl(Box(20, 20, 15), tmp, "box")
            cad.stl.export(stl, tmp / "box.3mf", tmp / "box.glb")
            for kind, path in (("stl", stl), ("threemf", tmp / "box.3mf"), ("glb", tmp / "box.glb")):
                with self.subTest(kind=kind):
                    result = getattr(cad, kind).dfm(path, process="printing")
                    facts = result.measurements["mesh"]
                    self.assertTrue(result.ok)
                    self.assertAlmostEqual(facts["volume_mm3"], 6000.0, delta=1.0)
                    self.assertEqual(facts["bbox_mm"], [20.0, 20.0, 15.0], "Z up, in millimetres")
            source = trimesh.load(stl, force="mesh")
            for suffix in (".obj", ".ply"):
                with self.subTest(fmt=suffix):
                    path = tmp / f"box{suffix}"
                    source.export(str(path))
                    facts = cad.trimesh.printing(trimesh.load(str(path), force="mesh"))["mesh"]
                    self.assertAlmostEqual(facts["volume_mm3"], 6000.0, delta=1.0)
                    self.assertEqual(facts["body_count"], 1)


class DegenerateMeshTest(unittest.TestCase):
    def test_zero_area_mesh_reports_instead_of_dividing_by_zero(self) -> None:
        """Area weighting needs a positive total; say so rather than crash."""
        mesh = trimesh.Trimesh(
            vertices=[[0, 0, 0], [1, 0, 0], [2, 0, 0]],
            faces=[[0, 1, 2]],
            process=False,
        )
        facts = dfam_tool._wall_facts(mesh, samples=100)

        self.assertEqual(facts["samples"], 0)
        self.assertIn("degenerate", facts["note"])


def _checked(path, **options) -> tuple[bool, dict]:
    """Check the way a skill run does: whether it passed, and what it measured."""
    result = cad.stl.dfm(path, process="printing", **options)
    return result.ok, result.measurements


def _measured(path, **options) -> dict:
    return _checked(path, **options)[1]


class CheckTest(unittest.TestCase):
    def test_the_check_emits_every_fact_family(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = _stl(Box(20, 20, 15), tmp, "box")
            payload = _measured(path, angle_limit=45.0)

        self.assertGreaterEqual(set(payload), {"mesh", "overhangs", "wall_thickness", "support_volume"})

    def test_angle_limit_is_echoed_back(self) -> None:
        """The limit used has to travel with the numbers it produced."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = _stl(Box(20, 20, 15), tmp, "box")
            payload = _measured(path, angle_limit=30.0)

        self.assertEqual(payload["overhangs"]["angle_limit_used_deg"], 30.0)

    def test_candidates_rank_the_orientations_beside_the_parts_own_figures(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = _stl(_wedge(30.0), tmp, "wedge30")
            result = cad.stl.dfm(path, process="printing", candidates=True)

        self.assertEqual(len(result.measurements["orientations"]["candidates"]), 6)
        self.assertIn("orientations by support area", result.summary)
        # The part as it stands is measured too: its walls, overhangs and support, and what they show.
        self.assertGreaterEqual(set(result.measurements), {"mesh", "overhangs", "wall_thickness", "support_volume"})
        self.assertIn("overhangs", {finding.code for finding in result.findings})

    def test_an_overhang_is_said_where_it_is(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = cad.stl.dfm(_stl(_wedge(30.0), Path(td), "wedge30"), process="printing")

        self.assertTrue(result.ok, "a fact, not a verdict")
        overhang = next(f for f in result.findings if f.code == "overhangs")
        self.assertEqual(overhang.severity, "warning")
        self.assertEqual(len(overhang.location.split(", ")), 3)


class MultiBodyWallTest(unittest.TestCase):
    """A mating clearance is not a wall.

    Cast against a whole assembly, a ray can leave one body, cross the fit gap
    and land on its neighbour, recording the gap as wall thickness. Measuring
    per body makes that impossible.
    """

    def _assembly(self, tmp: Path) -> str:
        socket = Box(10, 10, 10) - Box(6.6, 6.6, 20)     # 1.7 mm wall
        peg = Box(6.0, 6.0, 8)                           # 0.3 mm clearance a side
        export_stl(socket, str(tmp / "socket.stl"))
        export_stl(peg, str(tmp / "peg.stl"))
        merged = trimesh.util.concatenate([
            trimesh.load(str(tmp / "socket.stl"), force="mesh"),
            trimesh.load(str(tmp / "peg.stl"), force="mesh"),
        ])
        path = tmp / "mating.stl"
        merged.export(str(path))
        return str(path)

    def test_each_body_is_measured_against_itself(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            facts = dfam_tool._wall_facts(dfam_tool._load(self._assembly(tmp)), samples=2000)

        self.assertEqual(facts["body_count"], 2)
        self.assertTrue(facts["measured_per_body"])

        thinnest = min(b["min_mm"] for b in facts["per_body"] if b["min_mm"] is not None)
        # 0.3 mm is the fit gap; the thinnest real wall is the 1.7 mm socket.
        self.assertGreater(thinnest, 1.0)

    def test_a_sealed_cavity_is_its_bodys_and_its_skin_a_wall(self) -> None:
        """A groove that stops short of the top (the macropad's knob) is a sealed void inside one solid: one
        body, with the void said, and the 0.5 mm skin over it measured as one of its walls."""
        with tempfile.TemporaryDirectory() as td:
            part = Box(20, 20, 10) - Pos(0, 0, 4.0) * Box(16, 16, 1)   # its top at 4.5, the box's at 5
            result = cad.stl.dfm(_stl(part, Path(td), "sealed"), process="printing", samples=4000)

        self.assertEqual((result.measurements["mesh"]["body_count"], result.measurements["mesh"]["internal_void_count"]),
                         (1, 1))
        codes = {finding.code for finding in result.findings}
        self.assertIn("sealed_voids", codes)
        self.assertNotIn("several_bodies", codes)
        self.assertAlmostEqual(result.measurements["wall_thickness"]["min_mm"], 0.5, delta=0.01)

    def test_a_body_resting_on_another_is_closed_and_measured(self) -> None:
        """A two-material print: a 10 mm baffle standing on a 2 mm diffuser shares the diffuser's top, so
        neither body is closed. Each is closed again as the bodies are split (trimesh's repair, which needs
        networkx: the trimesh extra carries it) and measured against itself: the diffuser's 2 mm wall too."""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "two.stl"
            diffuser = trimesh.creation.box((20, 20, 2))
            baffle = trimesh.creation.box((20, 20, 10))
            baffle.apply_translation((0, 0, 6))
            trimesh.util.concatenate([diffuser, baffle]).export(str(path))
            result = cad.stl.dfm(path, process="printing", samples=400)

        self.assertTrue(result.ok, [(finding.code, finding.message) for finding in result.findings])
        self.assertFalse(result.measurements["mesh"]["watertight"])
        walls = sorted(body["min_mm"] for body in result.measurements["wall_thickness"]["per_body"] if body["min_mm"])
        self.assertEqual([round(wall, 3) for wall in walls], [2.0, 10.0])

    def test_per_body_carries_p05_for_the_same_judgement_rule_as_pooled(self) -> None:
        """SKILL.md says judge on p05_mm (min_mm alone can be a sampling
        outlier) and also says attribute a violation to its own body rather
        than the pooled figure. Both rules only hold together if p05_mm is
        present per body, not only in the pooled result.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            facts = dfam_tool._wall_facts(dfam_tool._load(self._assembly(tmp)), samples=2000)

        for body in facts["per_body"]:
            self.assertIn("p05_mm", body)
            self.assertIsNotNone(body["p05_mm"])

    def test_internal_arrays_never_reach_the_payload(self) -> None:
        """The pooled arrays are numpy and would not survive json.dumps."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            for path in (self._assembly(tmp), _stl(Box(20, 20, 15), tmp, "solid")):
                facts = dfam_tool._wall_facts(dfam_tool._load(path), samples=400)
                leaked = [k for k in facts if k.startswith("_")]
                self.assertEqual(leaked, [], f"{path} leaked {leaked}")
                json.dumps(facts)

    def test_single_body_keeps_the_flat_result_shape(self) -> None:
        """One body must not acquire per-body keys, and must stay accurate.

        Uses a hollow box because a solid box has a bimodal thickness field
        (15 mm through the flats, 20 mm through the sides), so asserting a
        single median would only be testing the triangulation.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = _stl(_hollow_box(2.0), tmp, "hollow_single")
            facts = dfam_tool._wall_facts(dfam_tool._load(path), samples=800)

        self.assertNotIn("body_count", facts)
        self.assertNotIn("per_body", facts)
        self.assertAlmostEqual(facts["median_mm"], 2.0, delta=0.4)


class ResilienceTest(unittest.TestCase):
    def test_one_failing_family_does_not_lose_the_others(self) -> None:
        """A planar mesh kills convex_hull; the rest of the report survives."""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "planar.stl"
            trimesh.Trimesh(
                vertices=[[0, 0, 0], [10, 0, 0], [0, 10, 0]],
                faces=[[0, 1, 2]],
                process=False,
            ).export(str(path))
            result = cad.stl.dfm(path, process="printing")
        payload = result.measurements

        self.assertIn("error", payload["support_volume"])
        self.assertNotIn("error", payload["overhangs"])
        self.assertNotIn("error", payload["mesh"])

        # A degraded report is not a clean one. Without these, a report missing
        # wall thickness because a dependency is absent reads exactly like a
        # report from a part that has no thin walls.
        self.assertTrue(payload["partial"])
        self.assertIn("support_volume", payload["partial_sections"])
        self.assertFalse(result.ok)
        self.assertIn(("error", "measurement_failed", "support_volume"),
                      [(f.severity, f.code, f.location) for f in result.findings])

    def test_a_complete_report_is_not_partial(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = _stl(Box(20, 20, 15), Path(td), "box")
            ok, payload = _checked(path)

        self.assertFalse(payload["partial"])
        self.assertNotIn("partial_sections", payload)
        self.assertTrue(ok)
        json.dumps(payload, allow_nan=False)


class ScaleHintTest(unittest.TestCase):
    """Sub-millimetre bbox means wrong units, not a flawless part."""

    def test_meters_scale_mesh_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            small = dfam_tool._load(_stl(Box(0.05, 0.02, 0.04), tmp, "meters"))
            big = dfam_tool._load(_stl(Box(20, 20, 15), tmp, "mm"))

        self.assertTrue(dfam_tool._scale_hint(small)["units_suspect"])
        self.assertFalse(dfam_tool._scale_hint(big)["units_suspect"])

    def test_scale_appears_in_both_reports(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = _stl(Box(20, 20, 15), tmp, "box")
            self.assertIn("scale", _measured(path))
            self.assertIn("scale", _measured(path, candidates=True))

    def test_units_scale_an_stl_to_millimetres(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            facts = _measured(_stl(Box(2, 2, 1.5), Path(td), "cm"), units="cm")["mesh"]

        self.assertAlmostEqual(facts["volume_mm3"], 6000.0, delta=1.0)


if __name__ == "__main__":
    unittest.main()
