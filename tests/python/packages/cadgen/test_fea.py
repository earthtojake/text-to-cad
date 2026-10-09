"""``cadgen fea``: the study file, the face listing, and the solver against hand calculations.

The physics check is an end-loaded cantilever, the one case every FEA course
validates first: tip deflection against Timoshenko beam theory and the
bending stress on the top fibre a quarter of the way along against My/I.
Both have closed forms, so a wrong Lame parameter, a wrong traction, a
mis-paired mid-edge node or a wrong stress recovery all show up as a number
off by far more than the tolerance. The fixture is a build123d box written
to a temporary STEP; nothing under ``models/`` is read.
"""

from __future__ import annotations

import io
import json
import math
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.fea.materials import lookup_material  # noqa: E402
from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402
from cadgen._internal.fea.study import parse_study  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

# The cantilever: length along +X, fixed at x = 0, loaded at x = L in -Z.
# Light enough that steel keeps a safety factor above 3, so it solves once.
LENGTH, WIDTH, HEIGHT, FORCE = 60.0, 6.0, 6.0, 20.0
STEEL = lookup_material("steel")


def _timoshenko_tip_deflection() -> float:
    inertia = WIDTH * HEIGHT ** 3 / 12.0
    shear_modulus = STEEL.E / (2.0 * (1.0 + STEEL.nu))
    bending = FORCE * LENGTH ** 3 / (3.0 * STEEL.E * inertia)
    shear = FORCE * LENGTH / (5.0 / 6.0 * WIDTH * HEIGHT * shear_modulus)
    return bending + shear


def _bending_stress(x: float) -> float:
    return 6.0 * FORCE * (LENGTH - x) / (WIDTH * HEIGHT ** 2)


def _write_cantilever(directory: Path, length: float = LENGTH, side: float = WIDTH) -> Path:
    from build123d import Align, Box, export_step

    path = directory / "cantilever.step"
    export_step(Box(length, side, side, align=(Align.MIN, Align.CENTER, Align.CENTER)), str(path))
    return path


def _end_faces(listing) -> tuple[str, str]:
    """The refs of the faces at x = 0 and at the far end."""
    by_x = {}
    for face in listing.faces:
        if face.surface == "plane" and face.normal is not None and abs(abs(face.normal[0]) - 1) < 1e-6:
            by_x[face.center_mm[0]] = face.ref
    return by_x[min(by_x)], by_x[max(by_x)]


def _glb_extras(path: Path) -> dict:
    import struct

    raw = path.read_bytes()
    json_length, _ = struct.unpack_from("<II", raw, 12)
    return json.loads(raw[20:20 + json_length])["meshes"][0]["extras"]


class _CountingSolve:
    """Wraps the solver to count its calls; ``fail_after`` makes later calls
    raise, ``later`` rewrites the outcome of every call after the first."""

    def __init__(self, fail_after: int | None = None, later=None):
        from cadgen._internal.fea import solve

        self.real = solve.solve_linear_static
        self.calls = 0
        self.fail_after = fail_after
        self.later = later

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise RuntimeError("the mesher gave up at this size")
        outcome = self.real(*args, **kwargs)
        return self.later(outcome) if self.later and self.calls > 1 else outcome


def _glb_peak_at(path: Path) -> list[float]:
    """The undeformed CAD-mm position of the GLB vertex with the highest ``_VON_MISES``."""
    import struct

    import numpy as np

    raw = path.read_bytes()
    json_length, _ = struct.unpack_from("<II", raw, 12)
    gltf = json.loads(raw[20:20 + json_length])
    binary = raw[20 + json_length + 8:]
    primitive = gltf["meshes"][0]["primitives"][0]

    def read(name: str, width: int) -> np.ndarray:
        accessor = gltf["accessors"][primitive["attributes"][name]]
        view = gltf["bufferViews"][accessor["bufferView"]]
        data = np.frombuffer(binary, np.float32, accessor["count"] * width, view["byteOffset"])
        return data.reshape(-1, width).astype(float)

    vertex = int(read("_VON_MISES", 1).argmax())
    scale = gltf["meshes"][0]["extras"]["deformation_scale"]
    x, y, z = read("POSITION", 3)[vertex] - scale * read("_DISPLACEMENT", 3)[vertex]
    return [x * 1000.0, -z * 1000.0, y * 1000.0]  # glTF (x, z, -y) metres back to CAD mm


class StudyFile(unittest.TestCase):
    """Stdlib only: a malformed study fails before any heavy import."""

    def test_a_named_material_and_one_fixture_and_load_parse(self):
        study = parse_study({
            "material": "6061-T6",
            "fixtures": [{"faces": ["#o1.f1"]}],
            "loads": [{"faces": ["#o1.f2"], "type": "force", "vector_N": [0, 0, -10]}],
        })
        self.assertEqual(study.material.name, "Aluminum 6061-T6")
        self.assertEqual(study.fixtures[0].type, "fixed")
        self.assertEqual(study.loads[0].vector, (0.0, 0.0, -10.0))
        self.assertEqual(study.face_refs, ("#o1.f1", "#o1.f2"))
        self.assertIsNone(study.mesh_size)

    def test_a_custom_material_overrides_the_table(self):
        study = parse_study({
            "material": {"name": "steel", "yield_MPa": 900},
            "fixtures": [{"faces": "#o1.f1"}],
            "loads": [{"faces": ["#o1.f2"], "type": "pressure", "pressure_MPa": 2.5}],
        })
        self.assertEqual(study.material.E, STEEL.E)
        self.assertEqual(study.material.yield_strength, 900.0)
        self.assertEqual(study.loads[0].pressure, 2.5)

    def test_the_errors_name_the_field(self):
        base = {"material": "steel", "fixtures": [{"faces": ["#o1.f1"]}], "loads": [{"faces": ["#o1.f2"], "type": "force", "vector_N": [1, 0, 0]}]}
        cases = [
            ({**base, "material": "unobtainium"}, "unknown material"),
            ({**base, "fixtures": []}, "fixtures"),
            ({**base, "loads": [{"faces": ["#o1.f2"], "type": "force", "vector_N": [0, 0, 0]}]}, "vector_N"),
            ({**base, "loads": [{"faces": ["#o1.f2"], "type": "torque"}]}, "loads[0].type"),
            ({**base, "mesh": {"size_mm": -1}}, "mesh.size_mm"),
            ({**base, "bogus": 1}, "unknown keys"),
        ]
        for document, fragment in cases:
            with self.subTest(fragment=fragment), self.assertRaises(ValueError) as caught:
                parse_study(document)
            self.assertIn(fragment, str(caught.exception))

    def test_the_margin_defaults_to_two_and_must_be_positive(self):
        base = {"material": "steel", "fixtures": [{"faces": ["#o1.f1"]}], "loads": [{"faces": ["#o1.f2"], "type": "force", "vector_N": [1, 0, 0]}]}
        self.assertEqual(parse_study(base).margin, 2.0)
        self.assertEqual(parse_study({**base, "margin": 1.5}).margin, 1.5)
        for bad in (0, -1, 0.5, "2", True):
            with self.subTest(margin=bad), self.assertRaises(ValueError) as caught:
                parse_study({**base, "margin": bad})
            self.assertIn("margin", str(caught.exception))

    def test_inline_json_and_a_file_are_accepted(self):
        text = json.dumps({"material": "pla", "fixtures": [{"faces": ["#o1.f1"]}], "loads": [{"faces": ["#o1.f2"], "type": "force", "vector_N": [0, 1, 0]}]})
        self.assertEqual(parse_study(text).material.name, "PLA")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "study.json"
            path.write_text(text, encoding="utf-8")
            self.assertEqual(parse_study(str(path)).material.name, "PLA")

    def test_no_study_is_a_teaching_error(self):
        with self.assertRaises(ValueError) as caught:
            parse_study(None)
        self.assertIn("--study", str(caught.exception))


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Cantilever(unittest.TestCase):
    """One solve, many assertions: the run is the expensive part."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        cls.step = _write_cantilever(directory)
        from unittest import mock

        from cadgen import fea

        listing = fea.faces(cls.step)
        cls.fixed_ref, cls.load_ref = _end_faces(listing)
        cls.listing = listing
        cls.study = {
            "material": "steel",
            "fixtures": [{"faces": [cls.fixed_ref], "type": "fixed"}],
            "loads": [{"faces": [cls.load_ref], "type": "force", "vector_N": [0, 0, -FORCE]}],
            "mesh": {"size_mm": 2.0},
        }
        cls.out = directory / "results" / "cantilever.glb"
        cls.solver = _CountingSolve()
        with mock.patch("cadgen._internal.fea.solve.solve_linear_static", cls.solver):
            cls.result = fea.solve(cls.step, cls.out, study=cls.study, vtu=True)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_face_listing_names_the_six_faces_with_hints(self):
        self.assertEqual(len(self.listing.faces), 6)
        self.assertTrue(all(face.ref.endswith(f".f{i + 1}") for i, face in enumerate(self.listing.faces)))
        end = next(face for face in self.listing.faces if face.ref == self.load_ref)
        self.assertAlmostEqual(end.area_mm2, WIDTH * HEIGHT, places=3)
        self.assertIn("normal +X", end.hint)

    def test_tip_deflection_matches_beam_theory(self):
        expected = _timoshenko_tip_deflection()
        self.assertAlmostEqual(self.result.summary["max_displacement_mm"] / expected, 1.0, delta=0.04)
        self.assertAlmostEqual(self.result.summary["max_displacement_at_mm"][0], LENGTH, delta=1e-6)

    def test_reactions_balance_the_load(self):
        applied = self.result.summary["applied_force_N"]
        reaction = self.result.summary["reaction_force_N"]
        self.assertEqual(applied, [0.0, 0.0, -FORCE])
        for a, r in zip(applied, reaction):
            self.assertAlmostEqual(a + r, 0.0, delta=1e-3 * FORCE)
        self.assertEqual(self.result.warnings, ())

    def test_the_stress_scale_is_right(self):
        # The nodal peak sits at the clamped edge (a concentration), so the
        # check is bounded rather than exact: between the root bending stress
        # and twice it.
        root = _bending_stress(0.0)
        peak = self.result.summary["max_von_mises_MPa"]
        self.assertGreater(peak, 0.9 * root)
        self.assertLess(peak, 2.0 * root)
        self.assertGreaterEqual(self.result.summary["max_von_mises_gauss_MPa"], peak * 0.99)
        self.assertAlmostEqual(self.result.summary["safety_factor"], STEEL.yield_strength / peak, places=2)

    def test_the_top_fibre_stress_a_quarter_along_matches_my_over_i(self):
        # Probe the VTU: von Mises at the corner nodes on the top face near x = L/4.
        import numpy as np

        vtu = self.result.vtu.read_text(encoding="utf-8")

        def block(marker: str) -> np.ndarray:
            """The numbers of the DataArray whose opening tag holds ``marker``."""
            start = vtu.index(">", vtu.index(marker) + len(marker)) + 1
            return np.array(vtu[start:vtu.index("</DataArray>", start)].split(), dtype=float)

        xyz = block("<Points><DataArray").reshape(-1, 3)
        values = block('Name="von_mises"')
        probe = (np.abs(xyz[:, 0] - LENGTH / 4) < 1.01) & (np.abs(xyz[:, 2] - HEIGHT / 2) < 1e-6) & (np.abs(xyz[:, 1]) < WIDTH / 2 - 1e-6)
        self.assertGreater(probe.sum(), 0)
        expected = _bending_stress(LENGTH / 4)
        self.assertAlmostEqual(values[probe].mean() / expected, 1.0, delta=0.08)

    def test_the_result_files_are_where_the_result_says(self):
        self.assertEqual(self.result.glb, self.out)
        self.assertEqual(self.result.sidecar, self.out.with_suffix(".json"))
        self.assertTrue(self.result.glb.is_file() and self.result.sidecar.is_file() and self.result.vtu.is_file())
        sidecar = json.loads(self.result.sidecar.read_text(encoding="utf-8"))
        self.assertEqual(sidecar["study"], self.study)
        self.assertEqual(sidecar["summary"], self.result.summary)
        self.assertEqual(sidecar["fields"][0]["max"], self.result.summary["max_von_mises_MPa"])
        self.assertEqual(sidecar["mesh"]["order"], 2)

    def test_the_glb_is_a_valid_binary_gltf_with_colours_and_the_value_attribute(self):
        import struct

        raw = self.result.glb.read_bytes()
        magic, version, length = struct.unpack_from("<4sII", raw)
        self.assertEqual((magic, version, length), (b"glTF", 2, len(raw)))
        json_length, json_type = struct.unpack_from("<II", raw, 12)
        self.assertEqual(json_type, 0x4E4F534A)
        gltf = json.loads(raw[20:20 + json_length])
        attributes = gltf["meshes"][0]["primitives"][0]["attributes"]
        self.assertEqual(set(attributes), {"POSITION", "NORMAL", "COLOR_0", "_VON_MISES", "_DISPLACEMENT"})
        extras = gltf["meshes"][0]["extras"]
        self.assertEqual(extras["deformation_scale"], self.result.summary["deformation_scale"])
        self.assertEqual([f["attribute"] for f in extras["fields"]], ["_VON_MISES", "_DISPLACEMENT"])
        self.assertEqual((extras["fields"][0]["units"], extras["fields"][0]["max"]), ("MPa", self.result.summary["max_von_mises_MPa"]))
        self.assertEqual(extras["fields"][1]["max"], self.result.summary["max_displacement_mm"])
        self.assertEqual(len(extras["ramp"]), 5)
        colour = gltf["accessors"][attributes["COLOR_0"]]
        self.assertEqual((colour["type"], colour["componentType"], colour.get("normalized")), ("VEC4", 5121, True))
        position = gltf["accessors"][attributes["POSITION"]]
        self.assertEqual(position["count"], colour["count"])
        # glTF space is metres, Y up: the deformed tip dips below the undeformed bottom face (CAD -Z -> glTF -Y).
        self.assertLess(position["min"][1], -HEIGHT / 2 / 1000.0)
        self.assertAlmostEqual(position["max"][0], LENGTH / 1000.0, places=2)  # the scaled deformation stretches the tip a little

    def test_the_cli_reports_the_same_numbers_as_json(self):
        from cadgen import cli

        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(["fea", "solve", str(self.step), str(self.out.with_name("again.glb")), "--study", json.dumps(self.study), "--json"])
        self.assertEqual(code, 0, out.getvalue())
        payload = json.loads(out.getvalue().strip().splitlines()[-1])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["summary"]["max_displacement_mm"], self.result.summary["max_displacement_mm"])
        self.assertEqual(payload["mesh"]["dofs"], self.result.mesh["dofs"])
        self.assertEqual(payload["findings"], [])

    def test_a_comfortable_part_solves_once_and_has_nothing_to_say(self):
        self.assertEqual(self.solver.calls, 1)
        self.assertEqual(self.result.findings, ())
        sidecar = json.loads(self.result.sidecar.read_text(encoding="utf-8"))
        self.assertEqual(sidecar["findings"], [])
        self.assertIsNone(sidecar["refined"])
        self.assertEqual(_glb_extras(self.result.glb)["findings"], [])
        self.assertEqual(self.result.mesh["size_mm"], 2.0)

    def test_a_face_on_a_different_part_or_a_non_face_is_refused(self):
        from cadgen import fea

        with self.assertRaises(ValueError) as caught:
            fea.solve(self.step, study={**self.study, "fixtures": [{"faces": [self.fixed_ref.rsplit(".", 1)[0]]}]})
        self.assertIn("faces", str(caught.exception))
        with self.assertRaises(ValueError):
            fea.solve(self.step, study={**self.study, "loads": [{"faces": ["#o1.f99"], "type": "force", "vector_N": [1, 0, 0]}]})

    def test_out_must_be_a_glb(self):
        from cadgen import fea

        with self.assertRaises(ValueError) as caught:
            fea.solve(self.step, self.out.with_suffix(".vtu"), study=self.study)
        self.assertIn(".glb", str(caught.exception))


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Yielding(unittest.TestCase):
    """A 3 mm square steel bar, 40 mm long, under 100 N: about 900 MPa at the root."""

    SIZE = 1.0

    @classmethod
    def setUpClass(cls):
        from unittest import mock

        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        cls.step = _write_cantilever(directory, length=40.0, side=3.0)
        cls.fixed_ref, cls.load_ref = _end_faces(fea.faces(cls.step))
        # The fixture names its face with the document prefix, as the viewer copies it.
        cls.study = {
            "material": "steel",
            "fixtures": [{"faces": [f"{cls.step.name}{cls.fixed_ref}"], "type": "fixed"}],
            "loads": [{"faces": [cls.load_ref], "type": "force", "vector_N": [0, 0, -100.0]}],
            "mesh": {"size_mm": cls.SIZE},
        }
        cls.solver = _CountingSolve()
        with mock.patch("cadgen._internal.fea.solve.solve_linear_static", cls.solver):
            cls.result = fea.solve(cls.step, directory / "bar.glb", study=cls.study)
        cls.sidecar = json.loads(cls.result.sidecar.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_it_yields_as_an_error_in_the_sidecar_the_glb_and_the_cli(self):
        first = self.sidecar["findings"][0]
        self.assertEqual((first["check"], first["severity"], first["type"]), ("fea", "error", "yields"))
        self.assertIn("The cantilever yields", first["summary"])
        self.assertEqual(_glb_extras(self.result.glb)["findings"], self.sidecar["findings"])
        self.assertEqual(list(self.result.findings), self.sidecar["findings"])
        self.assertIn(f"error: {first['summary']}", self.result.human_lines())

    def test_a_close_call_is_solved_again_finer_and_the_finer_result_is_written(self):
        self.assertEqual(self.solver.calls, 2)
        self.assertEqual(self.result.mesh["size_mm"], self.SIZE / 2)
        refined = self.sidecar["refined"]
        self.assertEqual((refined["from_size_mm"], refined["size_mm"]), (self.SIZE, self.SIZE / 2))
        self.assertEqual(refined["max_von_mises_MPa"], self.result.summary["max_von_mises_MPa"])
        self.assertEqual(_glb_extras(self.result.glb)["fields"][0]["max"], self.result.summary["max_von_mises_MPa"])

    def test_the_findings_point_at_the_written_glbs_peak(self):
        yields = self.sidecar["findings"][0]
        self.assertEqual(yields["items"][0]["at"], self.result.summary["max_von_mises_at_mm"])
        for got, want in zip(_glb_peak_at(self.result.glb), yields["items"][0]["at"]):
            self.assertAlmostEqual(got, want, delta=1e-3)

    def test_the_summary_safety_factor_is_the_checks_when_the_finer_peak_is_lower(self):
        import dataclasses
        from unittest import mock

        from cadgen import fea

        def halve(outcome):
            return dataclasses.replace(
                outcome, von_mises=outcome.von_mises / 2, von_mises_gauss_max=outcome.von_mises_gauss_max / 2
            )

        solver = _CountingSolve(later=halve)
        with mock.patch("cadgen._internal.fea.solve.solve_linear_static", solver):
            result = fea.solve(self.step, Path(self._tmp.name) / "lower.glb", study=self.study)
        refined = json.loads(result.sidecar.read_text(encoding="utf-8"))["refined"]
        self.assertLess(refined["max_von_mises_MPa"], refined["from_max_von_mises_MPa"])
        self.assertAlmostEqual(result.summary["safety_factor"], 250.0 / refined["from_max_von_mises_MPa"], places=3)
        self.assertNotAlmostEqual(result.summary["safety_factor"], 250.0 / result.summary["max_von_mises_MPa"], places=2)
        (moved,) = [f for f in result.findings if f["type"] == "mesh_not_converged"]
        self.assertTrue(moved["summary"].startswith("The peak changed "), moved["summary"])

    def test_a_peak_on_a_prefixed_fixture_is_at_the_fixture(self):
        at_fixture = [f for f in self.sidecar["findings"] if f["type"] == "peak_at_fixture"]
        self.assertEqual(len(at_fixture), 1)
        self.assertEqual(at_fixture[0]["items"][0]["ref"], self.fixed_ref)
        self.assertNotIn(".step", at_fixture[0]["items"][0]["ref"])

    def test_a_failed_finer_solve_keeps_the_first_result(self):
        from unittest import mock

        from cadgen import fea

        solver = _CountingSolve(fail_after=1)
        out = Path(self._tmp.name) / "failed-resolve.glb"
        with mock.patch("cadgen._internal.fea.solve.solve_linear_static", solver):
            result = fea.solve(self.step, out, study=self.study)
        self.assertEqual(solver.calls, 2)
        self.assertEqual(result.mesh["size_mm"], self.SIZE)
        types = [finding["type"] for finding in result.findings]
        self.assertEqual(types[0], "yields")
        self.assertNotIn("mesh_not_converged", types)
        (why,) = [warning for warning in result.warnings if "finer" in warning]
        self.assertIn("the mesher gave up at this size", why)
        sidecar = json.loads(result.sidecar.read_text(encoding="utf-8"))
        self.assertIsNone(sidecar["refined"]["max_von_mises_MPa"])


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class MeshOrderGuard(unittest.TestCase):
    def _elements(self, second_order: bool):
        import netgen.occ as ngocc

        mesh = ngocc.OCCGeometry(ngocc.Box((0, 0, 0), (1, 1, 1))).GenerateMesh(maxh=0.5)
        if second_order:
            mesh.SecondOrder()
        return mesh.Elements3D().NumPy().copy()

    def test_first_order_mesh_is_refused(self):
        from cadgen._internal.fea.mesh import _require_ten_node_tets

        with self.assertRaises(RuntimeError):
            _require_ten_node_tets(self._elements(second_order=False))

    def test_second_order_mesh_is_accepted(self):
        from cadgen._internal.fea.mesh import _require_ten_node_tets

        _require_ten_node_tets(self._elements(second_order=True))


class PeakFace(unittest.TestCase):
    """Which face the peak node sits on, from the boundary triangles alone."""

    def _peak_face(self, peak_node: int, fixed: set[int]):
        from types import SimpleNamespace

        import numpy as np

        from cadgen._internal.fea.run import _peak_face

        # Two triangles on f1, one on f2, sharing node 2 (an edge between them); node 9 is inside.
        volume = SimpleNamespace(
            boundary_ordinal=np.array([1, 1, 2]),
            faces={ordinal: SimpleNamespace(ref=f"#o1.f{ordinal}") for ordinal in (1, 2)},
        )
        outcome = SimpleNamespace(boundary_quadratic=np.array([
            [0, 1, 2, 10, 11, 12], [1, 3, 2, 13, 14, 11], [2, 4, 5, 15, 16, 17],
        ]))
        return _peak_face(volume, outcome, peak_node, fixed)

    def test_an_interior_peak_has_no_face(self):
        self.assertIsNone(self._peak_face(9, {1}))

    def test_a_peak_on_an_unfixed_face_names_it(self):
        self.assertEqual(self._peak_face(4, {1}), "#o1.f2")

    def test_a_peak_on_an_edge_names_the_fixed_face(self):
        self.assertEqual(self._peak_face(2, {2}), "#o1.f2")
        self.assertEqual(self._peak_face(2, set()), "#o1.f1")


class MissingExtra(unittest.TestCase):
    def test_the_install_hint_names_the_extra(self):
        import builtins
        from unittest import mock

        real = builtins.__import__

        def refuse(name, *args, **kwargs):
            if name == "pyamg":
                raise ImportError(name)
            return real(name, *args, **kwargs)

        with mock.patch("builtins.__import__", refuse), self.assertRaises(RuntimeError) as caught:
            require_fea_stack()
        self.assertIn("cadgen[fea]", str(caught.exception))
        self.assertIn("pyamg", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
