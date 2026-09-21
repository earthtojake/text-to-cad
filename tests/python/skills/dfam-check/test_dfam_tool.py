#!/usr/bin/env python3

"""Measurement tests for the dfam-check tool.

Each part is built with build123d so the correct answer is known from the
construction rather than from a recorded run: a 2 mm wall is 2 mm because it
was built that way, and a 30 deg underside is below a 45 deg limit by
geometry. A regression then shows up as a disagreement with the model, not as
a diff against whatever the tool happened to print last time.
"""

from __future__ import annotations

import contextlib
import io
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import trimesh
from build123d import Box, Polyline, Pos, Rotation, export_stl, extrude, make_face

from tests.python.support.paths import add_repo_path

add_repo_path("skills/dfam-check/scripts")

import dfam_tool  # noqa: E402


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
    """SKILL.md advertises .stl, .obj, .ply and .3mf, so each has to load.

    A format that is claimed but unreadable is worse than one that is not
    claimed, because the failure surfaces at the user rather than here.
    """

    def test_each_advertised_format_loads_and_measures(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            source = trimesh.load(_stl(Box(20, 20, 15), tmp, "box"), force="mesh")

            for suffix in (".stl", ".obj", ".ply", ".3mf"):
                with self.subTest(fmt=suffix):
                    path = tmp / f"box{suffix}"
                    source.export(str(path))
                    facts = dfam_tool._mesh_facts(dfam_tool._load(str(path)))

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


def _run_cli_status(argv: list[str]) -> tuple[int, dict]:
    """Invoke the CLI the way a skill run does: its exit code and its JSON."""
    buf = io.StringIO()
    with mock.patch.object(sys, "argv", ["dfam_tool.py", *argv]):
        with contextlib.redirect_stdout(buf):
            code = dfam_tool.main()
    return code, json.loads(buf.getvalue())


def _run_cli(argv: list[str]) -> dict:
    """Invoke the CLI the way a skill run does and parse what it prints."""
    return _run_cli_status(argv)[1]


class CliTest(unittest.TestCase):
    def test_measure_emits_every_fact_family(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = _stl(Box(20, 20, 15), tmp, "box")
            payload = _run_cli(["measure", path, "--angle-limit", "45"])

        self.assertGreaterEqual(
            set(payload), {"file", "mesh", "overhangs", "wall_thickness"}
        )

    def test_angle_limit_is_echoed_back(self) -> None:
        """The limit used has to travel with the numbers it produced."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = _stl(Box(20, 20, 15), tmp, "box")
            payload = _run_cli(["measure", path, "--angle-limit", "30"])

        self.assertEqual(payload["overhangs"]["angle_limit_used_deg"], 30.0)

    def test_orientations_subcommand_emits_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = _stl(_wedge(30.0), tmp, "wedge30")
            payload = _run_cli(["orientations", path, "--angle-limit", "45"])

        self.assertEqual(len(payload["orientations"]["candidates"]), 6)



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
            code, payload = _run_cli_status(["measure", str(path)])

        self.assertIn("error", payload["support_volume"])
        self.assertNotIn("error", payload["overhangs"])
        self.assertNotIn("error", payload["mesh"])

        # A degraded report is not a clean one. Without these, a report missing
        # wall thickness because a dependency is absent reads exactly like a
        # report from a part that has no thin walls.
        self.assertTrue(payload["partial"])
        self.assertIn("support_volume", payload["partial_sections"])
        self.assertEqual(code, 2)

    def test_a_complete_report_is_not_partial(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = _stl(Box(20, 20, 15), Path(td), "box")
            code, payload = _run_cli_status(["measure", path])

        self.assertFalse(payload["partial"])
        self.assertNotIn("partial_sections", payload)
        self.assertEqual(code, 0)


class ScaleHintTest(unittest.TestCase):
    """Sub-millimetre bbox means wrong units, not a flawless part."""

    def test_meters_scale_mesh_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            small = dfam_tool._load(_stl(Box(0.05, 0.02, 0.04), tmp, "meters"))
            big = dfam_tool._load(_stl(Box(20, 20, 15), tmp, "mm"))

        self.assertTrue(dfam_tool._scale_hint(small)["units_suspect"])
        self.assertFalse(dfam_tool._scale_hint(big)["units_suspect"])

    def test_scale_appears_in_both_subcommands(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = _stl(Box(20, 20, 15), tmp, "box")
            self.assertIn("scale", _run_cli(["measure", path]))
            self.assertIn("scale", _run_cli(["orientations", path]))


if __name__ == "__main__":
    unittest.main()
