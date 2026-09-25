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

import importlib.util
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
from cadgen._internal.fea.study import parse_study  # noqa: E402

HAVE_FEA = all(importlib.util.find_spec(name) is not None for name in ("netgen", "skfem", "pyamg", "numpy", "scipy"))

# The cantilever: length along +X, fixed at x = 0, loaded at x = L in -Z.
LENGTH, WIDTH, HEIGHT, FORCE = 60.0, 6.0, 6.0, 100.0
STEEL = lookup_material("steel")


def _timoshenko_tip_deflection() -> float:
    inertia = WIDTH * HEIGHT ** 3 / 12.0
    shear_modulus = STEEL.E / (2.0 * (1.0 + STEEL.nu))
    bending = FORCE * LENGTH ** 3 / (3.0 * STEEL.E * inertia)
    shear = FORCE * LENGTH / (5.0 / 6.0 * WIDTH * HEIGHT * shear_modulus)
    return bending + shear


def _bending_stress(x: float) -> float:
    return 6.0 * FORCE * (LENGTH - x) / (WIDTH * HEIGHT ** 2)


def _write_cantilever(directory: Path) -> Path:
    from build123d import Align, Box, export_step

    path = directory / "cantilever.step"
    export_step(Box(LENGTH, WIDTH, HEIGHT, align=(Align.MIN, Align.CENTER, Align.CENTER)), str(path))
    return path


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
        from cadgen import fea

        listing = fea.faces(cls.step)
        by_x = {}
        for face in listing.faces:
            if face.surface == "plane" and face.normal is not None and abs(abs(face.normal[0]) - 1) < 1e-6:
                by_x[round(face.center_mm[0])] = face.ref
        cls.fixed_ref, cls.load_ref = by_x[0], by_x[round(LENGTH)]
        cls.listing = listing
        cls.study = {
            "material": "steel",
            "fixtures": [{"faces": [cls.fixed_ref], "type": "fixed"}],
            "loads": [{"faces": [cls.load_ref], "type": "force", "vector_N": [0, 0, -FORCE]}],
            "mesh": {"size_mm": 2.0},
        }
        cls.out = directory / "results" / "cantilever.glb"
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

        def block(name: str) -> np.ndarray:
            start = vtu.index(f'Name="{name}"')
            start = vtu.index(">", start) + 1
            end = vtu.index("</DataArray>", start)
            return np.array(vtu[start:end].split(), dtype=float)

        points = block("connectivity")  # touch the grid to be sure it is well formed
        self.assertEqual(len(points) % 4, 0)
        start = vtu.index("<Points>")
        start = vtu.index(">", vtu.index("<DataArray", start)) + 1
        end = vtu.index("</DataArray>", start)
        xyz = np.array(vtu[start:end].split(), dtype=float).reshape(-1, 3)
        values = block("von_mises")
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
        self.assertEqual(sidecar["legend"]["max"], self.result.summary["max_von_mises_MPa"])
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
        fields = gltf["meshes"][0]["extras"]["fields"]
        self.assertEqual([f["attribute"] for f in fields], ["_VON_MISES", "_DISPLACEMENT"])
        self.assertEqual(fields[1]["max"], self.result.summary["max_displacement_mm"])
        self.assertEqual(gltf["meshes"][0]["extras"]["units"], "MPa")
        self.assertEqual(gltf["meshes"][0]["extras"]["max"], self.result.summary["max_von_mises_MPa"])
        self.assertEqual(gltf["meshes"][0]["extras"]["deformation_scale"], self.result.summary["deformation_scale"])
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


class MissingExtra(unittest.TestCase):
    def test_the_install_hint_names_the_extra(self):
        from cadgen._internal.fea import mesh

        real = mesh.__builtins__["__import__"] if isinstance(mesh.__builtins__, dict) else __import__

        def refuse(name, *args, **kwargs):
            if name == "pyamg":
                raise ImportError(name)
            return real(name, *args, **kwargs)

        import builtins

        original = builtins.__import__
        builtins.__import__ = refuse
        try:
            with self.assertRaises(RuntimeError) as caught:
                mesh.require_fea_stack()
        finally:
            builtins.__import__ = original
        self.assertIn("cadgen[fea]", str(caught.exception))
        self.assertIn("pyamg", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
