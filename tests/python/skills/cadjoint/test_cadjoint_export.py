#!/usr/bin/env python3

"""Export tests for the cadjoint skill's mesher.

The documented examples are exported as a user would export them and read
back with trimesh. Each assertion is a fact of the construction: the knob's
body is a 20 mm radius cylinder 16 mm tall, the planter's revolved profile
spans 0 to 70 mm in Z, so a mesh that disagrees is wrong, not merely
different from a recorded run.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import trimesh

from tests.python.support.paths import add_repo_path

add_repo_path("skills/cadjoint/scripts")

import cadjoint_export  # noqa: E402

EXAMPLES = Path(cadjoint_export.__file__).resolve().parents[1] / "references" / "examples"


def _run(*argv: str) -> tuple[int, dict]:
    captured = io.StringIO()
    with redirect_stdout(captured):
        code = cadjoint_export.main(list(argv))
    return code, json.loads(captured.getvalue())


class DocumentedExamplesTest(unittest.TestCase):
    def _export(self, example: str, resolution: int = 96) -> tuple[dict, trimesh.Trimesh]:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / f"{example}.stl"
            code, report = _run(str(EXAMPLES / f"{example}.py"), str(out),
                                "--resolution", str(resolution))
            self.assertEqual(code, 0, report)
            mesh = trimesh.load(out)
        return report, mesh

    def test_knob_is_one_closed_body_of_the_constructed_size(self) -> None:
        report, mesh = self._export("knob")
        self.assertFalse(report["clipped"])
        self.assertTrue(mesh.is_watertight)
        self.assertEqual(len(mesh.split(only_watertight=False)), 1)
        # 40 mm across less the knurl and the 1 mm rim blend; 16 mm tall
        # less the dome blend.
        x, y, z = mesh.extents
        self.assertAlmostEqual(x, y, delta=0.5)
        self.assertGreater(x, 38.0)
        self.assertLess(x, 40.5)
        self.assertGreater(z, 15.0)
        self.assertLess(z, 16.5)

    def test_planter_has_no_body_on_its_axis(self) -> None:
        """A revolve profile closed along the axis puts a false wall there."""
        report, mesh = self._export("planter")
        self.assertFalse(report["clipped"])
        self.assertTrue(mesh.is_watertight)
        self.assertEqual(len(mesh.split(only_watertight=False)), 1)
        low, high = mesh.bounds
        self.assertGreater(high[2], 68.0)  # rim
        self.assertLess(low[2], -3.0)      # feet below the floor


class BoundsTest(unittest.TestCase):
    def _scene(self, td: str, source: str) -> str:
        path = Path(td) / "scene.py"
        path.write_text(source, encoding="utf-8")
        return str(path)

    def test_a_part_hundreds_of_units_across_is_not_clipped(self) -> None:
        # The kernel's own export scans a fixed box of half-width 3 units.
        with tempfile.TemporaryDirectory() as td:
            scene = self._scene(td, (
                "from cadjoint.construction import Solid\n"
                "scene = Solid.box(size=(150.0, 40.0, 5.0), position=(0, 0, 5.0), name='bar')\n"
            ))
            out = Path(td) / "bar.stl"
            code, report = _run(scene, str(out), "--resolution", "64")
            self.assertEqual(code, 0, report)
            self.assertFalse(report["clipped"])
            mesh = trimesh.load(out)
        self.assertTrue(mesh.is_watertight)
        for measured, expected in zip(mesh.extents, (300.0, 80.0, 10.0)):
            self.assertAlmostEqual(measured, expected, delta=0.1)

    def test_a_box_cutting_through_the_part_is_reported_as_clipped(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            scene = self._scene(td, (
                "from cadjoint.construction import Solid\n"
                "scene = Solid.sphere(radius=10.0, name='ball')\n"
            ))
            code, report = _run(scene, str(Path(td) / "ball.stl"),
                                "--bounds", "-5", "-5", "-5", "15", "15", "15")
        self.assertEqual(code, 0, report)
        self.assertTrue(report["clipped"])

    def test_a_box_wholly_inside_the_part_is_an_error_not_an_empty_file(self) -> None:
        # No surface crosses such a box, so the kernel's boundary warning
        # never fires; the field itself has to be asked.
        with tempfile.TemporaryDirectory() as td:
            scene = self._scene(td, (
                "from cadjoint.construction import Solid\n"
                "scene = Solid.sphere(radius=10.0, name='ball')\n"
            ))
            code, report = _run(scene, str(Path(td) / "ball.stl"),
                                "--bounds", "-5", "-5", "-5", "5", "5", "5")
        self.assertEqual(code, 1)
        self.assertIn("inside the part", report["error"])

    def test_a_plate_thinner_than_the_scan_spacing_is_found(self) -> None:
        # 300 x 80 x 1: the scan cube that holds it has 10.7-unit spacing.
        with tempfile.TemporaryDirectory() as td:
            scene = self._scene(td, (
                "from cadjoint.construction import Solid\n"
                "scene = Solid.box(size=(150.0, 40.0, 0.5), position=(0, 0, 3.0), name='sheet')\n"
            ))
            out = Path(td) / "sheet.stl"
            code, report = _run(scene, str(out), "--resolution", "512")
            self.assertEqual(code, 0, report)
            self.assertFalse(report["clipped"])
            mesh = trimesh.load(out)
        self.assertTrue(mesh.is_watertight)
        self.assertAlmostEqual(mesh.extents[2], 1.0, delta=0.05)

    def test_an_unbounded_object_fails_and_names_the_way_out(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            scene = self._scene(td, "from cadjoint.sdf import Plane\nscene = Plane(0.0)\n")
            code, report = _run(scene, str(Path(td) / "plane.stl"))
        self.assertEqual(code, 1)
        self.assertIn("--bounds", report["error"])


class WarningsTest(unittest.TestCase):
    """The two mistakes a valid mesh hides: wrong units and a shattered wall."""

    def _report(self, source: str, *argv: str) -> dict:
        with tempfile.TemporaryDirectory() as td:
            scene = Path(td) / "scene.py"
            scene.write_text(source, encoding="utf-8")
            code, report = _run(str(scene), str(Path(td) / "out.stl"), *argv)
        self.assertEqual(code, 0, report)
        return report

    def test_a_scene_written_in_metres_is_flagged(self) -> None:
        report = self._report(
            "from cadjoint.construction import Solid\n"
            "scene = Solid.box(size=(0.02, 0.01, 0.003), name='block')\n",
            "--resolution", "64",
        )
        self.assertEqual(report["bodies"], 1)
        self.assertAlmostEqual(max(report["size"]), 0.04, delta=1e-3)
        self.assertEqual(len(report["warnings"]), 1)
        self.assertIn("metres", report["warnings"][0])

    def test_a_wall_thinner_than_the_cells_is_flagged_not_passed(self) -> None:
        # A 0.2 mm shell meshed at ~0.9 mm cells falls apart into fragments.
        report = self._report(
            "from cadjoint.construction import Solid\n"
            "from cadjoint.sdf import Shell\n"
            "scene = Shell(Solid.sphere(radius=30.0, name='ball'), 0.2)\n",
            "--resolution", "64",
        )
        self.assertGreater(report["bodies"], 1)
        self.assertTrue(any("raise --resolution" in note for note in report["warnings"]))

    def test_a_clean_part_has_no_warnings(self) -> None:
        report = self._report(
            "from cadjoint.construction import Solid\n"
            "scene = Solid.box(size=(20.0, 10.0, 3.0), name='block')\n",
            "--resolution", "64",
        )
        self.assertEqual(report["bodies"], 1)
        self.assertEqual(report["warnings"], [])
        for measured, expected in zip(report["size"], (40.0, 20.0, 6.0)):
            self.assertAlmostEqual(measured, expected, delta=0.05)


class ErrorsTest(unittest.TestCase):
    def test_a_missing_object_lists_the_ones_that_exist(self) -> None:
        code, report = _run(str(EXAMPLES / "knob.py"), "/nonexistent/x.stl", "--object", "lid")
        self.assertEqual(code, 1)
        self.assertIn("'lid'", report["error"])
        self.assertIn("scene", report["error"])
        self.assertIn("knurl", report["error"])

    def test_an_unknown_suffix_is_refused(self) -> None:
        code, report = _run(str(EXAMPLES / "knob.py"), "/tmp/knob.ply")
        self.assertEqual(code, 1)
        self.assertIn(".ply", report["error"])


if __name__ == "__main__":
    unittest.main()
