#!/usr/bin/env python3

"""Export tests for the cadjoint skill's mesher.

The documented examples are exported as a user would export them and read
back with trimesh. Each assertion is a fact of the construction: the clevis
bracket is drawn 120 x 60 x 52, the node is cut by a 40 mm ball and its
wall is 2 mm, so a mesh or a field that disagrees is wrong, not merely
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

    def test_clevis_bracket_holds_the_drawn_envelope(self) -> None:
        """120 x 60 x 52 as drawn: blends round the roots without bulging faces."""
        report, mesh = self._export("clevis_bracket", resolution=128)
        self.assertTrue(report["watertight"])
        self.assertTrue(mesh.is_watertight)
        self.assertEqual(report["bodies"], 1)
        self.assertEqual(report["warnings"], [])
        # Width: the root blend under each rib foot reaches 0.15 mm past the
        # plate edge (measured on the field), plus up to a fifth of a cell of
        # mesh error at this resolution; length and height do not move.
        length, width, height = mesh.extents
        self.assertAlmostEqual(length, 120.0, delta=0.15)
        self.assertAlmostEqual(width, 60.0 + 2 * 0.15, delta=0.2)
        self.assertAlmostEqual(height, 52.0, delta=0.15)

    def test_space_frame_node_is_one_open_shell_inside_its_cutting_ball(self) -> None:
        """Six blended, hollowed tubes cut by a 40 mm ball stay one piece."""
        import numpy as np

        report, mesh = self._export("space_frame_node", resolution=128)
        self.assertTrue(report["watertight"])
        self.assertTrue(mesh.is_watertight)
        self.assertEqual(report["bodies"], 1)
        self.assertEqual(report["warnings"], [])
        # The ball of radius 40 bounds everything; the up tube's 2 mm wall
        # (radii 9 to 11) meets it at z = sqrt(40^2 - 9^2).
        self.assertLess(np.linalg.norm(mesh.vertices, axis=1).max(), 40.0 + 0.3)
        self.assertAlmostEqual(mesh.bounds[1][2], (40.0**2 - 9.0**2) ** 0.5, delta=0.3)

    def test_a_revolve_profile_closed_along_the_axis_shells_like_a_mirrored_one(self) -> None:
        """cadjoint#50: an axis edge is interior, not a surface.

        Shelled, a cup is hollow, so the point on its axis halfway up lies in
        the cavity. Before the fix a profile closed along the axis made the
        axis a surface and the shell put material there.
        """
        import numpy as np

        def field_on_axis(points: str) -> float:
            source = (
                "from cadjoint.construction import PolygonProfile, SketchPlane, revolve\n"
                "from cadjoint.sdf import Shell\n"
                f"profile = PolygonProfile({points}, "
                "plane=SketchPlane(origin=(0, 0, 0), normal=(0, 1, 0)), name='cup')\n"
                "scene = Shell(revolve(profile), 2.0)\n"
            )
            with tempfile.TemporaryDirectory() as td:
                scene = Path(td) / "cup.py"
                scene.write_text(source, encoding="utf-8")
                obj = cadjoint_export.load_object(scene, "scene")
            return float(obj(np.array([[0.0, 0.0, 25.0]], dtype=np.float32))[0])

        on_axis = field_on_axis("[(0, 0), (30, 0), (40, 50), (0, 50)]")
        mirrored = field_on_axis("[(-30, 0), (30, 0), (40, 50), (-40, 50)]")
        self.assertGreater(on_axis, 20.0)
        self.assertAlmostEqual(on_axis, mirrored, delta=1e-3)


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


class EdgeCheckTest(unittest.TestCase):
    """The report's watertight flag counts edges after cadjoint welds slivers."""

    def test_a_closed_surface_passes_and_an_extra_triangle_fails(self) -> None:
        import numpy as np

        tetrahedron = np.array([[0, 2, 1], [0, 1, 3], [1, 2, 3], [0, 3, 2]])
        self.assertEqual(cadjoint_export.bad_edges(tetrahedron), 0)
        self.assertGreater(cadjoint_export.bad_edges(np.vstack([tetrahedron, [[0, 1, 2]]])), 0)

    def test_cadjoints_weld_drops_a_sliver_whose_corners_coincide(self) -> None:
        """cadjoint#52: the sliver goes before the edge check sees it."""
        import numpy as np
        from cadjoint.meshing import remove_slivers
        from cadjoint.meshing.dual_contouring import Mesh

        vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 1e-16]], float)
        faces = np.array([[0, 2, 1], [0, 1, 3], [1, 2, 3], [0, 3, 2], [4, 0, 1]])
        mesh = Mesh(vertices=vertices, faces=faces, quads=None, normals=None, cells=None)
        welded, removed = remove_slivers(mesh)
        self.assertEqual(removed, 1)
        self.assertEqual(cadjoint_export.bad_edges(np.asarray(welded.faces)), 0)


class StepSizeTest(unittest.TestCase):
    def test_an_oversized_faceted_step_is_flagged_and_an_stl_is_not(self) -> None:
        big = 225_000_000  # cadgen 0.8 took about three minutes to draw this size
        step = cadjoint_export.review_warnings([60, 60, 60], 1, 0.3, 0, "step", big)
        stl = cadjoint_export.review_warnings([60, 60, 60], 1, 0.3, 0, "stl", big)
        self.assertEqual(len(step), 1)
        self.assertIn("225 MB", step[0])
        self.assertEqual(stl, [])


class ErrorsTest(unittest.TestCase):
    def test_a_missing_object_lists_the_ones_that_exist(self) -> None:
        code, report = _run(str(EXAMPLES / "clevis_bracket.py"), "/nonexistent/x.stl", "--object", "lid")
        self.assertEqual(code, 1)
        self.assertIn("'lid'", report["error"])
        self.assertIn("scene", report["error"])
        self.assertIn("pin", report["error"])

    def test_an_unknown_suffix_is_refused(self) -> None:
        code, report = _run(str(EXAMPLES / "clevis_bracket.py"), "/tmp/clevis.ply")
        self.assertEqual(code, 1)
        self.assertIn(".ply", report["error"])


if __name__ == "__main__":
    unittest.main()
