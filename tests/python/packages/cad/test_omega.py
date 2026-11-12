"""The omega integration: ``cad omega check`` judges the mesh omega-core's ``gsl`` writes against the model's field,
and ``cad run gsl`` is ``gsl`` as it is.

The measurements are numpy alone and tested everywhere. What runs ``gsl`` needs the omega-core wheel, which
requirements-dev.txt installs on macOS and Linux (it has no Windows build): those tests skip, by name, where it is
absent. Every model is written by the test into a temporary folder.
"""

from __future__ import annotations

import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

from cad.omega._check import measure, queryable, read_stl

HAS_OMEGA = importlib.util.find_spec("omega_core") is not None
NEEDS_OMEGA = "needs omega-core (cad[omega]: macOS and Linux)"

# A unit tetrahedron, its faces wound outward.
TETRA = np.array([[[0, 0, 0], [0, 1, 0], [1, 0, 0]],
                  [[0, 0, 0], [1, 0, 0], [0, 0, 1]],
                  [[0, 0, 0], [0, 0, 1], [0, 1, 0]],
                  [[1, 0, 0], [0, 1, 0], [0, 0, 1]]], dtype=np.float64)


def write_stl(path: Path, triangles) -> Path:
    """A binary STL of ``triangles`` (normals zero, as many writers leave them)."""
    with path.open("wb") as out:
        out.write(b"\0" * 80 + struct.pack("<I", len(triangles)))
        for triangle in triangles:
            out.write(struct.pack("<3f", 0, 0, 0) + struct.pack("<9f", *np.asarray(triangle).ravel()) + b"\0\0")
    return path


class Measurements(unittest.TestCase):
    def test_a_closed_tetrahedron_has_no_open_edge_and_its_volume(self) -> None:
        measured = measure(TETRA)
        self.assertEqual((4, 0, 0, 0), (measured["triangles"], measured["open_edges"], measured["non_manifold_edges"],
                                        measured["degenerate_triangles"]))
        self.assertAlmostEqual(1 / 6, measured["volume_mm3"])
        self.assertEqual(([0.0, 0.0, 0.0], [1.0, 1.0, 1.0]), (measured["bbox_min"], measured["bbox_max"]))

    def test_a_missing_face_opens_three_edges_and_a_flipped_mesh_encloses_a_negative_volume(self) -> None:
        self.assertEqual(3, measure(TETRA[:3])["open_edges"])
        self.assertAlmostEqual(-1 / 6, measure(TETRA[:, ::-1])["volume_mm3"])

    def test_an_edge_of_three_triangles_and_a_triangle_of_no_area_are_counted(self) -> None:
        fin = np.array([[[0, 0, 0], [1, 0, 0], [0.5, -1, 0.5]]], dtype=np.float64)  # a third face on edge 0-1
        sliver = np.array([[[0, 0, 0], [1, 1, 1], [2, 2, 2]]], dtype=np.float64)
        measured = measure(np.concatenate([TETRA, fin, sliver]))
        self.assertEqual(1, measured["non_manifold_edges"])
        self.assertEqual(1, measured["degenerate_triangles"])

    def test_no_triangles_measure_as_empty(self) -> None:
        self.assertEqual(0, measure(np.zeros((0, 3, 3)))["triangles"])

    def test_binary_and_ascii_stls_read_the_same_and_anything_else_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            binary = write_stl(Path(folder) / "t.stl", TETRA)
            ascii_ = Path(folder) / "a.stl"
            ascii_.write_text("solid t\n" + "".join(
                "facet normal 0 0 0\nouter loop\n" + "".join(f"vertex {x} {y} {z}\n" for x, y, z in tri)
                + "endloop\nendfacet\n" for tri in TETRA) + "endsolid t\n", encoding="utf-8")
            np.testing.assert_allclose(read_stl(binary), TETRA)
            np.testing.assert_allclose(read_stl(ascii_), TETRA)
            junk = Path(folder) / "j.stl"
            junk.write_bytes(b"not a mesh")
            with self.assertRaisesRegex(ValueError, "not an STL"):
                read_stl(junk)

    def test_the_evaluator_is_handed_the_model_without_its_scene_and_whole_line_comments(self) -> None:
        text = "@scene(40)\n// the part\ns = sphere(10); // kept\nreturn s;\n"
        self.assertEqual("s = sphere(10); // kept\nreturn s;\n", queryable(text))


@unittest.skipUnless(HAS_OMEGA, NEEDS_OMEGA)
class Check(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def model(self, name: str, text: str) -> Path:
        path = self.folder / f"{name}.gsl"
        path.write_text(text, encoding="utf-8")
        return path

    def codes(self, result) -> set[str]:
        return {finding.code for finding in result.findings if finding.severity == "error"}

    def test_a_sound_part_passes_with_its_volume_within_the_field_s(self) -> None:
        from cad.omega import check

        result = check(self.model("ball", "@scene(24)\n// a ball\nball = sphere(8);\nreturn ball;\n"))
        self.assertTrue(result.ok, result.findings)
        self.assertRegex(result.summary, r"^OK .*ball\.gsl: \d+ triangles, .* mm3, .* in @scene\(24\)$")
        low, high = result.measurements["field_volume_mm3"]
        self.assertLessEqual(low * 0.98, result.measurements["volume_mm3"])
        self.assertLessEqual(result.measurements["volume_mm3"], high * 1.02)
        self.assertAlmostEqual(4 / 3 * np.pi * 8 ** 3, result.measurements["volume_mm3"], delta=2.0)

    def test_a_model_without_scene_is_refused_before_gsl_guesses_a_box(self) -> None:
        from cad.omega import check

        result = check(self.model("bare", "return sphere(8);\n"))
        self.assertFalse(result.ok)
        self.assertEqual({"no_scene"}, self.codes(result))

    def test_a_model_gsl_refuses_is_said_in_gsl_s_words(self) -> None:
        from cad.omega import check

        result = check(self.model("broken", "@scene(24)\nreturn sphere(8\n"))
        self.assertEqual({"compile_failed"}, self.codes(result))
        self.assertIn("unexpected token", next(f.message for f in result.findings if f.code == "compile_failed"))

    def test_a_part_larger_than_its_scene_is_cut_off(self) -> None:
        from cad.omega import check

        result = check(self.model("big", "@scene(20)\nreturn sphere(15);\n"))
        self.assertIn("cut_off", self.codes(result))

    def test_a_given_mesh_is_judged_inside_out_empty_or_open(self) -> None:
        from cad.omega import check

        model = self.model("tetra", "@scene(4)\nreturn sphere(1);\n")
        self.assertIn("inside_out", self.codes(check(model, mesh=write_stl(self.folder / "f.stl", TETRA[:, ::-1]))))
        self.assertEqual({"empty_mesh"}, self.codes(check(model, mesh=write_stl(self.folder / "e.stl", TETRA[:0]))))
        self.assertIn("open_edges", self.codes(check(model, mesh=write_stl(self.folder / "o.stl", TETRA[:3]))))

    def test_a_mesh_that_lost_a_wall_thinner_than_its_cells_is_refused(self) -> None:
        """A 0.3 mm shell meshed coarse: gsl exits 0 and its mesh keeps a sliver of the wall, or none of it."""
        import subprocess

        import omega_core

        from cad.omega import check

        model = self.model("shell", "@scene(40)\nreturn max(sphere(15), -sphere(14.7));\n")
        coarse = self.folder / "coarse.stl"
        done = subprocess.run([str(omega_core.executable()), "compile", "-t", "stl", "--subdivision", "5", "--no-meta",
                               "-o", str(coarse), str(model)], capture_output=True, text=True)
        self.assertEqual(0, done.returncode, done.stderr)
        result = check(model, mesh=coarse)
        self.assertFalse(result.ok)
        self.assertTrue(self.codes(result) & {"volume_mismatch", "inside_out", "open_edges", "empty_mesh"},
                        result.findings)

    def test_a_file_that_is_no_gsl_model_is_refused(self) -> None:
        from cad.omega import check

        other = self.folder / "part.txt"
        other.write_text("x", encoding="utf-8")
        self.assertFalse(check(other).ok)

    def test_cad_run_gsl_runs_the_wheel_s_gsl_as_it_is(self) -> None:
        import contextlib
        import io

        from cad.omega._command import main

        self.assertEqual(0, main(["gsl", "--version"]))
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertNotEqual(0, main(["gsl", "compile", str(self.folder / "missing.gsl")]))


if __name__ == "__main__":
    unittest.main()
