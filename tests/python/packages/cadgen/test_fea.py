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
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from tests.python.support.fea_fixtures import (
    box_step, class_directory, ends, glb_array, glb_extras, needs_fea, quiet, read_glb, reported, solve, value_error,
)
from tests.python.support.fea_fixtures import AL6061_NUMBERS, AL7075_NUMBERS, PLA_NUMBERS, STEEL_NUMBERS  # noqa: E402

from cadgen._internal.fea.materials import material_from_spec  # noqa: E402
from cadgen._internal.fea.study import parse_study  # noqa: E402

# The cantilever: length along +X, fixed at x = 0, loaded at x = L in -Z.
# Light enough that steel keeps a safety factor above 3, so it solves once.
LENGTH, WIDTH, HEIGHT, FORCE = 60.0, 6.0, 6.0, 20.0
STEEL = material_from_spec(STEEL_NUMBERS)


def _timoshenko_tip_deflection() -> float:
    inertia = WIDTH * HEIGHT ** 3 / 12.0
    shear_modulus = STEEL.E / (2.0 * (1.0 + STEEL.nu))
    bending = FORCE * LENGTH ** 3 / (3.0 * STEEL.E * inertia)
    shear = FORCE * LENGTH / (5.0 / 6.0 * WIDTH * HEIGHT * shear_modulus)
    return bending + shear


def _bending_stress(x: float) -> float:
    return 6.0 * FORCE * (LENGTH - x) / (WIDTH * HEIGHT ** 2)


TIP = _timoshenko_tip_deflection()


def _glb_indices(path: Path) -> "np.ndarray":
    import numpy as np

    gltf, binary = read_glb(path)
    accessor = gltf["accessors"][gltf["meshes"][0]["primitives"][0]["indices"]]
    view = gltf["bufferViews"][accessor["bufferView"]]
    return np.frombuffer(binary, np.uint32, accessor["count"], view["byteOffset"])


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
    vertex = int(glb_array(path, "_VON_MISES").argmax())
    scale = glb_extras(path)["deformation_scale"]
    x, y, z = glb_array(path, "POSITION", 3)[vertex] - scale * glb_array(path, "_DISPLACEMENT", 3)[vertex]
    return [x * 1000.0, -z * 1000.0, y * 1000.0]  # glTF (x, z, -y) metres back to CAD mm


def _vtu_von_mises(path: Path) -> "tuple[np.ndarray, np.ndarray]":
    """The VTU's corner-node positions (N, 3) and von Mises (N,)."""
    import numpy as np

    vtu = path.read_text(encoding="utf-8")

    def block(marker: str) -> np.ndarray:
        start = vtu.index(">", vtu.index(marker) + len(marker)) + 1
        return np.array(vtu[start:vtu.index("</DataArray>", start)].split(), dtype=float)

    return block("<Points><DataArray").reshape(-1, 3), block('Name="von_mises"')


BASE = {"material": STEEL_NUMBERS, "fixtures": [{"faces": ["face 1"]}], "loads": [{"faces": ["face 2"], "type": "force", "vector_N": [1, 0, 0]}]}


class StudyFile(unittest.TestCase):
    """Stdlib only: a malformed study fails before any heavy import."""

    def test_a_named_material_and_one_fixture_and_load_parse(self):
        study = parse_study({
            "material": AL6061_NUMBERS,
            "fixtures": [{"faces": ["face 1"]}],
            "loads": [{"faces": ["face 2"], "type": "force", "vector_N": [0, 0, -10]}],
        })
        self.assertEqual(study.material.name, "Aluminum 6061-T6")
        self.assertEqual(study.fixtures[0].type, "fixed")
        self.assertEqual(study.loads[0].vector, (0.0, 0.0, -10.0))
        self.assertEqual(study.face_refs, ("face 1", "face 2"))
        self.assertIsNone(study.mesh_size)

    def test_a_studys_material_is_optional_and_only_numbers(self):
        # Left out, each part is solved with its model's own material; given, it is the person's numbers, whole.
        study = parse_study({"fixtures": [{"faces": "face 1"}],
                             "loads": [{"faces": ["face 2"], "type": "pressure", "pressure_MPa": 2.5}]})
        self.assertIsNone(study.material)
        self.assertEqual(study.loads[0].pressure, 2.5)
        with self.assertRaisesRegex(ValueError, "an object needs E_MPa, nu and yield_MPa .*it has no E_MPa, nu"):
            parse_study({**BASE, "material": {"name": "steel", "yield_MPa": 900}})
        from cadgen._internal.fea.materials import material_from_spec

        own = material_from_spec({"name": "Copper  C110", "E_MPa": 117000, "nu": 0.34, "yield_MPa": 69})
        self.assertEqual((own.name, own.source), ("Copper C110", "study"))

    def test_the_errors_name_the_field(self):
        cases = [
            ({**BASE, "material": "unobtainium"}, "give an object with E_MPa, nu and yield_MPa"),
            ({**BASE, "fixtures": []}, "fixtures"),
            ({**BASE, "loads": [{"faces": ["face 2"], "type": "force", "vector_N": [0, 0, 0]}]}, "loads[0].vector_N: the force is zero"),
            ({**BASE, "loads": [{"faces": ["face 2"], "type": "pressure", "pressure_MPa": 0}]}, "loads[0].pressure_MPa: the pressure is zero"),
            ({**BASE, "loads": [{"faces": ["face 2"], "type": "torque"}]}, "loads[0].type"),
            ({**BASE, "mesh": {"size_mm": -1}}, "mesh.size_mm"),
            ({**BASE, "mesh": {"order": 1}}, "study.mesh: unknown keys ['order']; it takes size_mm, refine"),
            ({**BASE, "output": {"vtu": True}}, "study.output: unknown keys ['vtu']; it takes deformation_scale"),
            ({**BASE, "bogus": 1}, "study: unknown keys ['bogus']; a study takes material, fixtures, loads"),
            ({**BASE, "fixtures": [{"faces": ["face 1"], "type": "roller", "direction": [0, 0, 1]}]},
             "fixtures[0]: unknown keys ['direction']; it takes faces, type"),
            ({**BASE, "loads": [{"faces": ["face 2"], "type": "force", "vector_N": [1, 0, 0], "pressure_MPa": 5}]},
             "loads[0]: unknown keys ['pressure_MPa']; it takes faces, type, vector_N"),
            ({**BASE, "loads": [{"faces": ["face 2"], "type": "pressure", "pressure_MPa": 1, "vector_N": [1, 0, 0]}]},
             "loads[0]: unknown keys ['vector_N']; it takes faces, type, pressure_MPa"),
            ({**BASE, "parts": {"arm": {"material": PLA_NUMBERS, "thickness_mm": 2}}}, "parts['arm']: unknown keys ['thickness_mm']"),
            ({**BASE, "connections": [{"between": ["a", "b"], "type": "free", "tolerance_mm": 1}]},
             "connections[0]: unknown keys ['tolerance_mm']; it takes between, type"),
            ({**BASE, "connections": [{"between": ["a", "b"], "type": "welded"}]}, "connections[0].type: 'welded' is not one of ('bonded', 'free')"),
            ({**BASE, "output": {"deformation_scale": 0}}, "output.deformation_scale: must be > 0"),
            ({**BASE, "output": {"deformation_scale": -5}}, "output.deformation_scale: must be > 0"),
        ]
        for document, fragment in cases:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, value_error(self, parse_study, document))

    def test_the_margin_defaults_to_two_and_must_be_positive(self):
        self.assertEqual(parse_study(BASE).margin, 2.0)
        self.assertEqual(parse_study({**BASE, "margin": 1.5}).margin, 1.5)
        for bad in (0, -1, 0.5, "2", True):
            with self.subTest(margin=bad):
                self.assertIn("margin", value_error(self, parse_study, {**BASE, "margin": bad}))

    def test_inline_json_and_a_file_are_accepted(self):
        text = json.dumps({"material": PLA_NUMBERS, "fixtures": [{"faces": ["face 1"]}], "loads": [{"faces": ["face 2"], "type": "force", "vector_N": [0, 1, 0]}]})
        self.assertEqual(parse_study(text).material.name, "PLA")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "study.json"
            path.write_text(text, encoding="utf-8")
            self.assertEqual(parse_study(str(path)).material.name, "PLA")

    def test_no_study_is_a_teaching_error(self):
        self.assertIn("--study", value_error(self, parse_study, None))


class Mesher(unittest.TestCase):
    """netgen installs only where it publishes wheels; elsewhere the solve says so, naming the platform."""

    def test_without_netgen_the_solve_refuses_naming_the_platform_before_reading_anything(self):
        import importlib.util
        import platform
        from unittest import mock

        from cadgen import fea

        real = importlib.util.find_spec
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch("importlib.util.find_spec", lambda name, *a: None if name == "netgen" else real(name, *a)), \
                mock.patch.object(platform, "system", return_value="Linux"), \
                mock.patch.object(platform, "machine", return_value="aarch64"):
            with self.assertRaisesRegex(RuntimeError, r"needs netgen.*not installed.*\(macOS, Linux x86_64 and Windows "
                                                      r"x86_64\), and this is Linux aarch64"):
                fea.solve(Path(tmp) / "absent.step", Path(tmp) / "r.glb", study=BASE)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_the_dependency_is_marked_for_the_platforms_netgen_has_wheels_for(self):
        import tomllib

        from cadgen._internal.fea.mesh import NETGEN_PLATFORMS

        pyproject = Path(__file__).resolve().parents[4] / "packages" / "cadgen" / "pyproject.toml"
        (netgen,) = [d for d in tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["dependencies"]
                     if d.startswith("netgen-mesher")]
        self.assertEqual(netgen.split(";", 1)[1].strip(), "sys_platform == 'darwin' or (sys_platform == 'linux' and "
                         "platform_machine == 'x86_64') or (sys_platform == 'win32' and platform_machine == 'AMD64')")
        self.assertEqual(NETGEN_PLATFORMS, "macOS, Linux x86_64 and Windows x86_64")


class StudyChecks(unittest.TestCase):
    """The study's optional ``checks``: checked like the rest of the study, before any heavy import."""

    def test_checks_parse_as_written(self):
        checks = [{"kind": "stress", "label": "Strength"},
                  {"kind": "displacement", "limit_mm": 0.5, "faces": ["face 2"], "label": "Tip sag"}]
        study = parse_study({**BASE, "margin": 3, "checks": checks})
        self.assertEqual(study.checks, (
            {"kind": "stress", "label": "Strength"}, {"kind": "displacement", "limit_mm": 0.5, "faces": ["face 2"], "label": "Tip sag"}))
        self.assertEqual(study.check_faces, ("face 2",))
        self.assertEqual(study.margin, 3.0)

    def test_with_no_checks_the_stress_check_alone_judges_the_result(self):
        self.assertEqual(parse_study(BASE).checks, ({"kind": "stress"},))
        self.assertEqual(parse_study(BASE).check_faces, ())

    def test_a_malformed_check_is_a_plain_sentence(self):
        cases = [
            ([], "study.checks is empty: leave it out for the stress check alone"),
            ({"kind": "stress"}, "study.checks: expected a list"),
            ([{"kind": "temperature"}], 'checks[0].kind: "temperature" is not a check this cadgen makes; use one of [\'stress\', \'displacement\']'),
            (["stress"], "checks[0]: expected an object"),
            ([{"kind": "stress"}, {"kind": "stress"}], "only one stress check"),
            ([{"kind": "stress", "limit_mm": 1}], "checks[0]: unknown keys ['limit_mm']; a stress check takes"),
            # The margin is the study's, said once: the stress check takes none of its own.
            ([{"kind": "stress", "margin": 3}], "checks[0]: unknown keys ['margin']; a stress check takes ['kind', 'label']"),
            ([{"kind": "displacement"}], "checks[0].limit_mm: a displacement check needs the most it may move"),
            ([{"kind": "displacement", "limit_mm": 0}], "checks[0].limit_mm: must be > 0"),
            ([{"kind": "displacement", "limit_mm": 1, "faces": []}], "checks[0]: 'faces' must be a non-empty list"),
            ([{"kind": "displacement", "limit_mm": 1, "label": ""}], "checks[0].label: expected a short piece of text"),
        ]
        for checks, fragment in cases:
            with self.subTest(fragment=fragment):
                message = value_error(self, parse_study, {**BASE, "checks": checks})
                self.assertIn(fragment, message)
                self.assertNotIn("\u2014", message)

    def test_a_view_is_no_key(self):
        self.assertIn("study: unknown keys ['view']", value_error(self, parse_study, {**BASE, "view": {"checks": []}}))
        self.assertIn("study: unknown keys ['analysis']", value_error(self, parse_study, {**BASE, "analysis": "static"}))


class GlbJson(unittest.TestCase):
    def test_a_non_finite_number_is_refused_rather_than_written_as_json_no_reader_parses(self):
        import numpy as np

        from cadgen._internal.fea.outputs import write_glb

        nodes = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0.5, 0, 0], [0.5, 0.5, 0], [0, 0.5, 0]], float)
        mesh = dict(positions=nodes, displacement=np.zeros_like(nodes), values=np.zeros(6), triangles6=np.array([[0, 1, 2, 3, 4, 5]]),
                    face_of_triangle=np.array([0]), scale=1.0, value_range=(0.0, 1.0))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.glb"
            with self.assertRaises(ValueError):
                write_glb(path, extras={"faces": ["face 1"], "summary": {"max": math.inf}}, **mesh)
            self.assertFalse(path.exists())


@needs_fea
class Cantilever(unittest.TestCase):
    """One solve, many assertions: the run is the expensive part."""

    @classmethod
    def setUpClass(cls):
        from unittest import mock

        from cadgen import fea

        directory = class_directory(cls)
        cls.step = box_step(directory, "cantilever", (LENGTH, WIDTH, WIDTH), "x")
        cls.listing = fea.faces(cls.step)
        cls.fixed_ref, cls.load_ref = ends(cls.listing)
        cls.study = {
            "material": STEEL_NUMBERS,
            "fixtures": [{"faces": [cls.fixed_ref], "type": "fixed"}],
            "loads": [{"faces": [cls.load_ref], "type": "force", "vector_N": [0, 0, -FORCE]}],
            "mesh": {"size_mm": 2.0},
            # Generous limits: the checks pass, so the part still has nothing to say.
            "checks": [
                {"kind": "stress"},
                {"kind": "displacement", "limit_mm": 2 * TIP},
                {"kind": "displacement", "limit_mm": 1.05 * TIP, "faces": [cls.load_ref], "label": "Tip sag"},
                {"kind": "displacement", "limit_mm": TIP, "faces": [cls.fixed_ref], "label": "Clamp"},
            ],
        }
        cls.out = directory / "results" / "cantilever.glb"
        cls.solver = _CountingSolve()
        with mock.patch("cadgen._internal.fea.solve.solve_linear_static", cls.solver):
            cls.result = solve(cls.step, cls.out, cls.study, vtu=True)

    def test_the_face_listing_names_the_six_faces_with_hints(self):
        self.assertEqual(len(self.listing.faces), 6)
        self.assertTrue(all(face.ref.endswith(f"/face {i + 1}") for i, face in enumerate(self.listing.faces)))
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
        # The nodal field is each element's stress extrapolated from its integration points, so it peaks higher.
        self.assertGreaterEqual(peak, self.result.summary["max_von_mises_gauss_MPa"] * 0.99)
        self.assertAlmostEqual(self.result.summary["safety_factor"], STEEL.yield_strength / peak, places=2)

    def test_the_top_fibre_stress_a_quarter_along_matches_my_over_i(self):
        # Probe the VTU: von Mises at the corner nodes on the top face near x = L/4.
        import numpy as np

        xyz, values = _vtu_von_mises(self.result.vtu)
        probe = (np.abs(xyz[:, 0] - LENGTH / 4) < 1.01) & (np.abs(xyz[:, 2] - HEIGHT / 2) < 1e-6) & (np.abs(xyz[:, 1]) < WIDTH / 2 - 1e-6)
        self.assertGreater(probe.sum(), 0)
        expected = _bending_stress(LENGTH / 4)
        self.assertAlmostEqual(values[probe].mean() / expected, 1.0, delta=0.08)

    def test_the_result_files_are_where_the_result_says(self):
        self.assertEqual(self.result.glb, self.out)
        self.assertTrue(self.result.glb.is_file() and self.result.vtu.is_file())
        # The GLB and the VTU asked for, and nothing beside them: the numbers are the result's.
        self.assertEqual(sorted(p.name for p in self.out.parent.iterdir() if p.stem == self.out.stem),
                         sorted([self.out.name, self.out.with_suffix(".vtu").name]))
        said = reported(self.result)
        self.assertEqual(said["study"], self.study)
        self.assertEqual(said["summary"], self.result.summary)
        self.assertEqual(glb_extras(self.result.glb)["fields"][0]["max"], self.result.summary["max_von_mises_MPa"])
        self.assertEqual(said["mesh"]["order"], 2)

    def test_the_glb_writes_von_mises_and_the_displacement(self):
        written = [field["attribute"] for field in glb_extras(self.result.glb)["fields"]]
        self.assertEqual(written, ["_VON_MISES", "_DISPLACEMENT"])
        self.assertNotIn("view", glb_extras(self.result.glb))

    def test_a_displacement_check_measures_the_tip_against_beam_theory(self):
        stress, whole, tip, clamp = self.result.summary["checks"]
        # The whole model and the loaded face both find the tip, where beam theory puts the largest deflection.
        for check in (whole, tip):
            self.assertAlmostEqual(check["value"] / TIP, 1.0, delta=0.04)
            self.assertAlmostEqual(check["where"]["at"][0], LENGTH, delta=1e-6)
        self.assertEqual(whole["value"], self.result.summary["max_displacement_mm"])
        self.assertEqual((tip["label"], tip["faces"], tip["where"]["ref"], tip["unit"]), ("Tip sag", [self.load_ref], self.load_ref, "mm"))
        self.assertEqual((whole["label"], whole["status"], whole["close_at"]), ("Displacement", "passes", 0.9))
        self.assertAlmostEqual(whole["ratio"], whole["value"] / whole["limit"], places=5)
        # Within a tenth of its limit, the model's own accuracy, a check is close; the clamped face does not move.
        self.assertEqual(tip["status"], "close")
        self.assertEqual((clamp["value"], clamp["status"]), (0.0, "passes"))
        self.assertNotIn("faces", whole)

    def test_the_stress_check_is_the_safety_factors_verdict(self):
        stress = self.result.summary["checks"][0]
        factor = self.result.summary["safety_factor"]
        self.assertEqual((stress["kind"], stress["label"], stress["unit"]), ("stress", "Strength", "MPa"))
        self.assertEqual((stress["value"], stress["limit"]), (self.result.summary["max_von_mises_MPa"], STEEL.yield_strength))
        self.assertEqual(stress["ratio"], round(1 / factor, 6))
        self.assertEqual((stress["margin"], stress["close_at"], stress["status"]), (2.0, 0.5, "passes" if factor >= 2 else "close"))

    def test_the_checks_are_written_into_the_glb_the_result_and_the_lines(self):
        checks = self.result.summary["checks"]
        self.assertEqual(glb_extras(self.result.glb)["checks"], checks)
        self.assertEqual(reported(self.result)["summary"]["checks"], checks)
        lines = self.result.human_lines()
        tip = checks[2]
        self.assertIn(f"check 'Tip sag': {tip['value']:g} mm against a {tip['limit']:g} mm limit, {tip['ratio']:.2f}× it, close", lines)
        self.assertEqual(sum(line.startswith("check '") for line in lines), 4)

    def test_the_glb_names_its_step_relative_to_its_own_folder(self):
        self.assertEqual(glb_extras(self.result.glb)["document"], f"../{self.step.name}")
        self.assertEqual(reported(self.result)["document"], str(self.step))

    def test_the_glb_names_its_step_absolutely_when_no_relative_path_exists(self):
        from unittest import mock

        from cadgen._internal.fea.run import _document_ref

        with mock.patch("os.path.relpath", side_effect=ValueError("path is on mount 'C:', start on mount 'D:'")):
            self.assertEqual(_document_ref(self.step, self.out), self.step.resolve().as_posix())

    def test_the_glb_is_a_valid_binary_gltf_with_colours_and_the_value_attribute(self):
        import struct

        raw = self.result.glb.read_bytes()
        magic, version, length = struct.unpack_from("<4sII", raw)
        self.assertEqual((magic, version, length), (b"glTF", 2, len(raw)))
        json_length, json_type = struct.unpack_from("<II", raw, 12)
        self.assertEqual(json_type, 0x4E4F534A)
        gltf = json.loads(raw[20:20 + json_length])
        # The attribute names and the fields' order.
        attributes = gltf["meshes"][0]["primitives"][0]["attributes"]
        extras = gltf["meshes"][0]["extras"]
        self.assertEqual(extras["deformation_scale"], self.result.summary["deformation_scale"])
        self.assertEqual((extras["fields"][0]["units"], extras["fields"][0]["max"]), ("MPa", self.result.summary["max_von_mises_MPa"]))
        self.assertEqual(extras["fields"][1]["max"], self.result.summary["max_displacement_mm"])
        self.assertEqual(len(extras["ramp"]), 5)
        self.assertEqual(extras["safety_factor"], self.result.summary["safety_factor"])
        colour = gltf["accessors"][attributes["COLOR_0"]]
        self.assertEqual((colour["type"], colour["componentType"], colour.get("normalized")), ("VEC4", 5121, True))
        position = gltf["accessors"][attributes["POSITION"]]
        self.assertEqual(position["count"], colour["count"])
        # glTF space is metres, Y up: the deformed tip dips below the undeformed bottom face (CAD -Z -> glTF -Y).
        self.assertLess(position["min"][1], -HEIGHT / 2 / 1000.0)
        self.assertAlmostEqual(position["max"][0], LENGTH / 1000.0, places=2)  # the scaled deformation stretches the tip a little

    def test_the_glb_records_its_study_with_bare_face_refs(self):
        study = glb_extras(self.result.glb)["study"]
        self.assertEqual(study["material"]["name"], "Steel (structural, generic)")
        self.assertEqual(set(study["material"]), {"name", "yield_MPa", "youngs_GPa", "poisson"})
        self.assertAlmostEqual(study["material"]["youngs_GPa"], 200.0, delta=15)
        self.assertEqual(study["fixtures"], [{"type": "fixed", "faces": [self.fixed_ref]}])
        self.assertIn("/face ", self.fixed_ref)
        self.assertEqual(study["loads"], [{"type": "force", "faces": [self.load_ref], "vector_N": [0, 0, -FORCE]}])
        self.assertEqual(study["mesh"]["size_mm"], self.result.mesh["size_mm"])
        self.assertEqual((study["mesh"]["order"], study["mesh"]["elements"], study["mesh"]["refined_from_mm"]),
                         (2, self.result.mesh["elements"], None))
        self.assertEqual(study["margin"], 2.0)

    def test_every_surface_triangle_traces_to_a_source_face(self):
        import numpy as np

        extras = glb_extras(self.result.glb)
        self.assertEqual(extras["faces"], [face.ref for face in self.listing.faces])
        face = glb_array(self.result.glb, "_FACE", 1)[:, 0].astype(int)
        indices = _glb_indices(self.result.glb).reshape(-1, 3)
        self.assertTrue(((face >= 0) & (face < len(extras["faces"]))).all())
        # a triangle's three vertices lie on one face
        self.assertTrue((face[indices[:, 0]] == face[indices[:, 1]]).all() and (face[indices[:, 0]] == face[indices[:, 2]]).all())
        undeformed = glb_array(self.result.glb, "POSITION", 3) - extras["deformation_scale"] * glb_array(self.result.glb, "_DISPLACEMENT", 3)
        x_mm = undeformed[:, 0] * 1000.0
        fixed = face == extras["faces"].index(self.fixed_ref)
        load = face == extras["faces"].index(self.load_ref)
        self.assertTrue(fixed.any() and load.any())
        np.testing.assert_allclose(x_mm[fixed], 0.0, atol=1e-3)
        np.testing.assert_allclose(x_mm[load], LENGTH, atol=1e-3)

    def test_the_cli_reports_the_same_numbers_as_json(self):
        from cadgen import cli

        out = io.StringIO()
        with redirect_stdout(out), quiet():
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
        written = reported(self.result)
        self.assertEqual(written["findings"], [])
        self.assertIsNone(written["refined"])
        self.assertEqual(glb_extras(self.result.glb)["findings"], [])
        self.assertEqual(self.result.mesh["size_mm"], 2.0)

    def test_a_face_on_a_different_part_or_a_non_face_is_refused(self):
        self.assertIn("faces", value_error(self, solve, self.step, self.out, {
            **self.study, "fixtures": [{"faces": [self.fixed_ref.rsplit("/", 1)[0]]}]}))
        value_error(self, solve, self.step, self.out, {**self.study, "loads": [{"faces": ["face 99"], "type": "force", "vector_N": [1, 0, 0]}]})

    def test_a_load_on_a_held_face_is_refused_however_the_face_is_named(self):
        on_fixed = {**self.study, "loads": [{"faces": [f"{self.step.name}#{self.fixed_ref}"], "type": "force", "vector_N": [0, 0, -1]}]}
        self.assertIn(f"loads[0]: {self.step.name}#{self.fixed_ref} is held by fixtures[0] (fixed), which holds it still, so the "
                      "load goes into the support", value_error(self, solve, self.step, self.out, on_fixed))
        # A roller holds a face along its normal, which is where a pressure pushes.
        pressed = {**self.study, "fixtures": [*self.study["fixtures"], {"faces": [self.load_ref], "type": "roller"}],
                   "loads": [{"faces": [self.load_ref], "type": "pressure", "pressure_MPa": 1}]}
        self.assertIn("is held by fixtures[1] (roller), which holds it along its normal",
                      value_error(self, solve, self.step, self.out, pressed))

    def test_reactions_that_do_not_balance_the_load_refuse_the_solve_and_write_nothing(self):
        import dataclasses
        from unittest import mock

        from cadgen._internal.fea import solve as solver

        real = solver.solve_linear_static

        def halved(*args, **kwargs):
            outcome = real(*args, **kwargs)
            return dataclasses.replace(outcome, reactions=[tuple(0.5 * c for c in r) for r in outcome.reactions])

        out = self.out.with_name("unbalanced.glb")
        with mock.patch.object(solver, "solve_linear_static", halved), \
                self.assertRaisesRegex(RuntimeError, r"the reactions do not balance the applied load \(mismatch 10 N\)"):
            solve(self.step, out, {**self.study, "mesh": {"size_mm": 6.0}})
        self.assertFalse(out.exists())

    def test_a_study_no_load_reaches_is_refused_rather_than_passed(self):
        import dataclasses
        from unittest import mock

        import numpy as np

        from cadgen._internal.fea import solve as solver

        real = solver.solve_linear_static

        def unstressed(*args, **kwargs):
            outcome = real(*args, **kwargs)
            return dataclasses.replace(outcome, von_mises=np.zeros_like(outcome.von_mises))

        out = self.out.with_name("unloaded.glb")
        with mock.patch.object(solver, "solve_linear_static", unstressed):
            self.assertIn("no load reaches the part", value_error(self, solve, self.step, out, {**self.study, "mesh": {"size_mm": 6.0}}))
        self.assertFalse(out.exists())

    def test_out_must_be_a_glb(self):
        self.assertIn(".glb", value_error(self, solve, self.step, self.out.with_suffix(".vtu"), self.study))

    def test_a_run_that_fails_at_its_last_file_leaves_the_earlier_result_byte_for_byte(self):
        from unittest import mock

        from cadgen._internal.fea import run

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "r.glb"
            solve(self.step, out, self.study, vtu=True)
            earlier = {path: path.read_bytes() for path in (out, out.with_suffix(".vtu"))}
            heavier = {**self.study, "loads": [{"faces": [self.load_ref], "type": "force", "vector_N": [0, 0, -2 * FORCE]}]}
            real, calls = run.replace_atomic, []

            def fail_on_the_last(source, target):
                calls.append(target)
                if len(calls) == 2:
                    raise OSError("the VTU is held open")
                return real(source, target)

            with mock.patch.object(run, "replace_atomic", fail_on_the_last), self.assertRaises(OSError):
                solve(self.step, out, heavier, vtu=True)
            self.assertEqual({path: path.read_bytes() for path in earlier}, earlier)
            self.assertEqual(sorted(path.name for path in Path(tmp).iterdir()), ["r.glb", "r.vtu"])


@needs_fea
class Yielding(unittest.TestCase):
    """A 3 mm square steel bar, 40 mm long, under 100 N: about 900 MPa at the root."""

    SIZE = 1.0

    @classmethod
    def setUpClass(cls):
        from unittest import mock

        cls.directory = class_directory(cls)
        cls.step = box_step(cls.directory, "cantilever", (40.0, 3.0, 3.0), "x")
        cls.fixed_ref, cls.load_ref = ends(cls.step)
        # The fixture names its face with the document prefix, as the viewer copies it.
        cls.study = {
            "material": STEEL_NUMBERS,
            "fixtures": [{"faces": [f"{cls.step.name}#{cls.fixed_ref}"], "type": "fixed"}],
            "loads": [{"faces": [cls.load_ref], "type": "force", "vector_N": [0, 0, -100.0]}],
            "mesh": {"size_mm": cls.SIZE},
        }
        cls.solver = _CountingSolve()
        from cadgen._internal.fea import mesh

        real_mesh, cls.meshed = mesh.mesh_occurrence, []

        def mesh_spy(occurrence, **kwargs):
            cls.meshed.append(kwargs)
            return real_mesh(occurrence, **kwargs)

        with mock.patch("cadgen._internal.fea.solve.solve_linear_static", cls.solver), \
                mock.patch("cadgen._internal.fea.mesh.mesh_occurrence", mesh_spy):
            cls.result = solve(cls.step, cls.directory / "bar.glb", cls.study)
        cls.said = reported(cls.result)

    def test_it_yields_as_an_error_in_the_result_the_glb_and_the_cli(self):
        first = self.said["findings"][0]
        self.assertEqual((first["check"], first["severity"], first["type"]), ("fea", "error", "yields"))
        self.assertIn("The cantilever yields", first["summary"])
        self.assertEqual(glb_extras(self.result.glb)["findings"], self.said["findings"])
        self.assertEqual(list(self.result.findings), self.said["findings"])
        self.assertIn(f"error: {first['summary']}", self.result.human_lines())

    def test_a_part_that_yields_is_not_ok_and_its_glb_is_written_all_the_same(self):
        # ok is the validators' rule, an error blocks (the command exits 1); the GLB shows where it fails.
        self.assertFalse(self.result.ok)
        self.assertTrue(self.result.glb.is_file())
        self.assertEqual(self.result.human_lines()[-1], f"FAILED {self.step}: 1 blocking finding(s)")

    def test_with_no_checks_the_stress_check_alone_says_what_the_safety_factor_says(self):
        (check,) = self.result.summary["checks"]
        self.assertEqual((check["kind"], check["status"]), ("stress", "fails"))
        self.assertEqual(check["ratio"], round(1 / self.result.summary["safety_factor"], 6))
        self.assertEqual(glb_extras(self.result.glb)["checks"], [check])
        # The stress check's findings are the yields finding already made; it adds none of its own.
        self.assertEqual([f["type"] for f in self.result.findings].count("yields"), 1)
        self.assertNotIn("displacement_over_limit", [f["type"] for f in self.result.findings])

    def test_a_close_call_is_solved_again_finer_and_the_finer_result_is_written(self):
        self.assertEqual(self.solver.calls, 2)
        self.assertEqual(self.result.mesh["size_mm"], self.SIZE / 2)
        refined = self.said["refined"]
        self.assertEqual((refined["from_size_mm"], refined["size_mm"]), (self.SIZE, self.SIZE / 2))
        self.assertEqual(refined["max_von_mises_MPa"], self.result.summary["max_von_mises_MPa"])
        self.assertEqual(glb_extras(self.result.glb)["fields"][0]["max"], self.result.summary["max_von_mises_MPa"])
        mesh = glb_extras(self.result.glb)["study"]["mesh"]
        self.assertEqual((mesh["size_mm"], mesh["refined_from_mm"]), (self.SIZE / 2, self.SIZE))

    def test_the_finer_solve_refines_curved_features_by_the_same_ratio(self):
        first, finer = self.meshed
        self.assertEqual(first.get("refine", 1.0), 1.0)
        self.assertAlmostEqual(finer["refine"], first["max_h"] / finer["max_h"], places=9)
        self.assertGreater(finer["refine"], 1.0)

    def test_the_findings_point_at_the_written_glbs_peak(self):
        yields = self.said["findings"][0]
        self.assertEqual(yields["items"][0]["at"], self.result.summary["max_von_mises_at_mm"])
        for got, want in zip(_glb_peak_at(self.result.glb), yields["items"][0]["at"]):
            self.assertAlmostEqual(got, want, delta=1e-3)

    def test_the_safety_factor_is_floored_never_rounded_up(self):
        sf = self.result.summary["safety_factor"]
        self.assertEqual(sf, math.floor(sf * 1000) / 1000)

    def test_the_summary_safety_factor_is_yield_over_the_written_peak_when_the_finer_peak_is_lower(self):
        import dataclasses
        from unittest import mock

        def halve(outcome):
            return dataclasses.replace(
                outcome, von_mises=outcome.von_mises / 2, von_mises_gauss_max=outcome.von_mises_gauss_max / 2
            )

        solver = _CountingSolve(later=halve)
        with mock.patch("cadgen._internal.fea.solve.solve_linear_static", solver):
            result = solve(self.step, self.directory / "lower.glb", self.study)
        refined = reported(result)["refined"]
        self.assertLess(refined["max_von_mises_MPa"], refined["from_max_von_mises_MPa"])
        self.assertAlmostEqual(result.summary["safety_factor"], 250.0 / result.summary["max_von_mises_MPa"], places=2)
        self.assertNotAlmostEqual(result.summary["safety_factor"], 250.0 / refined["from_max_von_mises_MPa"], places=2)
        (moved,) = [f for f in result.findings if f["type"] == "mesh_not_converged"]
        self.assertTrue(moved["summary"].startswith("The peak changed "), moved["summary"])

    def test_a_peak_on_a_prefixed_fixture_is_at_the_fixture(self):
        at_fixture = [f for f in self.said["findings"] if f["type"] == "peak_at_fixture"]
        self.assertEqual(len(at_fixture), 1)
        self.assertEqual(at_fixture[0]["items"][0]["ref"], self.fixed_ref)
        self.assertNotIn(".step", at_fixture[0]["items"][0]["ref"])

    def test_a_failed_finer_solve_keeps_the_first_result(self):
        from unittest import mock

        solver = _CountingSolve(fail_after=1)
        with mock.patch("cadgen._internal.fea.solve.solve_linear_static", solver):
            result = solve(self.step, self.directory / "failed-resolve.glb", self.study)
        self.assertEqual(solver.calls, 2)
        self.assertEqual(result.mesh["size_mm"], self.SIZE)
        types = [finding["type"] for finding in result.findings]
        self.assertEqual(types[0], "yields")
        self.assertNotIn("mesh_not_converged", types)
        (why,) = [warning for warning in result.warnings if "finer" in warning]
        self.assertIn("the mesher gave up at this size", why)
        self.assertIsNone(reported(result)["refined"]["max_von_mises_MPa"])

    def test_a_fault_in_the_finer_solve_fails_the_study(self):
        # Only the mesher or CalculiX failing is a second opinion lost; a fault of cadgen's is no warning at exit 0.
        from unittest import mock

        solver = _CountingSolve()

        def faulty(*args, **kwargs):
            if solver.calls == 1:
                raise KeyError("a fault of cadgen's")
            return solver(*args, **kwargs)

        out = self.directory / "faulty-resolve.glb"
        with mock.patch("cadgen._internal.fea.solve.solve_linear_static", faulty), self.assertRaises(KeyError):
            solve(self.step, out, self.study)
        self.assertFalse(out.exists())


@needs_fea
class FinerMeshSize(unittest.TestCase):
    """The automatic re-solve halves the element size unless that would pass the DOF budget."""

    @staticmethod
    def estimate(size, finer, dofs):
        return dofs * (size / finer) ** 3

    def test_a_small_part_halves(self):
        from cadgen._internal.fea.run import finer_mesh_size

        self.assertEqual(finer_mesh_size(2.0, 10_000), 1.0)

    def test_a_larger_part_is_capped_under_the_warn_threshold(self):
        from cadgen._internal.fea.run import finer_mesh_size
        from cadgen._internal.fea.solve import DOF_WARN

        finer = finer_mesh_size(2.0, 50_000)
        self.assertTrue(1.0 < finer < 2.0)
        self.assertAlmostEqual(self.estimate(2.0, finer, 50_000), DOF_WARN, delta=DOF_WARN * 1e-6)

    def test_a_part_already_past_the_warn_threshold_stays_under_the_limit(self):
        from cadgen._internal.fea.run import finer_mesh_size
        from cadgen._internal.fea.solve import DOF_LIMIT

        finer = finer_mesh_size(2.0, 160_000)
        self.assertLess(finer, 2.0)
        self.assertLess(self.estimate(2.0, finer, 160_000), DOF_LIMIT)

    def test_a_first_solve_just_under_the_warn_threshold_falls_back_to_the_limit_budget(self):
        from cadgen._internal.fea.run import finer_mesh_size
        from cadgen._internal.fea.solve import DOF_LIMIT

        finer = finer_mesh_size(2.0, 140_000)  # the WARN budget would give a ratio under 1.1
        self.assertLess(finer, 1.9)
        self.assertLess(self.estimate(2.0, finer, 140_000), DOF_LIMIT)

    def test_no_finer_solve_when_there_is_no_room_for_one(self):
        from cadgen._internal.fea.run import finer_mesh_size

        self.assertIsNone(finer_mesh_size(2.0, 1_400_000))


@needs_fea
class MeshOrderGuard(unittest.TestCase):
    def _elements(self, second_order: bool):
        # In a process of its own, as cadgen meshes (fea/mesher.py): netgen's OpenCascade and OCP's cannot share one.
        import pickle
        import subprocess
        import sys

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "elements.pickle"
            script = ("import pickle, sys\nimport netgen.occ as ngocc\n"
                      "mesh = ngocc.OCCGeometry(ngocc.Box((0, 0, 0), (1, 1, 1))).GenerateMesh(maxh=0.5)\n"
                      + ("mesh.SecondOrder()\n" if second_order else "")
                      + "open(sys.argv[1], 'wb').write(pickle.dumps(mesh.Elements3D().NumPy().copy()))\n")
            subprocess.run([sys.executable, "-c", script, str(out)], check=True, capture_output=True)
            return pickle.loads(out.read_bytes())

    def test_first_order_mesh_is_refused(self):
        from cadgen._internal.fea.mesh import require_elements

        with self.assertRaises(RuntimeError):
            require_elements(self._elements(second_order=False))

    def test_second_order_mesh_is_accepted(self):
        from cadgen._internal.fea.mesh import require_elements

        require_elements(self._elements(second_order=True))


class InvertedElements(unittest.TestCase):
    """An element whose curved mid-edge node crossed its opposite face is made straight before CalculiX sees it."""

    def _pair(self):
        """Two unit tets sharing a face, mid-edge nodes shared: A's node on its edge (0, 1) is pushed through the
        opposite face, B's node on its edge (1, 4) is curved a little and stays sound. Returns (nodes, tets, slot)
        with ``slot`` the node id of each corner pair's mid-edge node."""
        import numpy as np

        from cadgen._internal.fea.calculix import NETGEN_EDGES

        corners = np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 1]])
        points, slot = list(corners), {}
        for tet in ((0, 1, 2, 3), (1, 2, 3, 4)):
            for i, j in NETGEN_EDGES:
                pair = tuple(sorted((tet[i], tet[j])))
                if pair not in slot:
                    slot[pair] = len(points)
                    points.append((corners[pair[0]] + corners[pair[1]]) / 2)
        tets = np.array([[*tet, *(slot[tuple(sorted((tet[i], tet[j])))] for i, j in NETGEN_EDGES)]
                         for tet in ((0, 1, 2, 3), (1, 2, 3, 4))])
        nodes = np.array(points)
        nodes[slot[(0, 1)]] = [1.0, 0.5, 0.5]  # past the face x + y + z = 1
        nodes[slot[(1, 4)]] += [0.05, -0.05, 0.0]
        return nodes, tets, slot

    def test_the_inverted_element_alone_is_made_straight_and_counted(self):
        import numpy as np

        from cadgen._internal.fea.calculix import C3D10_EDGES, C3D10_POINTS, SMALLEST_JACOBIAN, c3d10_elements
        from cadgen._internal.fea.mesh import jacobians, straighten_inverted

        nodes, tets, slot = self._pair()
        curved = nodes[slot[(1, 4)]].copy()
        before = jacobians(nodes[c3d10_elements(nodes, tets)], C3D10_EDGES, C3D10_POINTS)
        self.assertEqual((before < SMALLEST_JACOBIAN).any(axis=1).tolist(), [True, False])

        self.assertEqual(straighten_inverted(nodes, tets), 1)
        after = jacobians(nodes[c3d10_elements(nodes, tets)], C3D10_EDGES, C3D10_POINTS)
        self.assertTrue((after >= SMALLEST_JACOBIAN).all())
        np.testing.assert_allclose(after[0], 1.0)  # the straight unit tet: its corners' Jacobian everywhere
        np.testing.assert_allclose(nodes[slot[(0, 1)]], [0.5, 0.0, 0.0])
        np.testing.assert_array_equal(nodes[slot[(1, 4)]], curved)  # the sound neighbour keeps its curve

    def test_an_element_folded_at_a_node_alone_is_made_straight_too(self):
        """CalculiX checks its four integration points only, and solves an element folded at a node, wrongly."""
        import numpy as np

        from cadgen._internal.fea.calculix import C3D10_EDGES, C3D10_POINTS, SMALLEST_JACOBIAN, c3d10_elements
        from cadgen._internal.fea.mesh import jacobians, straighten_inverted

        nodes, tets, slot = self._pair()
        nodes[slot[(0, 1)]] = [0.5875, 0.0875, 0.0875]  # short of the opposite face, past where the node's own map folds
        sound = jacobians(nodes[c3d10_elements(nodes, tets)], C3D10_EDGES, C3D10_POINTS)
        self.assertTrue((sound >= SMALLEST_JACOBIAN).all())  # CalculiX would take it
        self.assertEqual(straighten_inverted(nodes, tets), 1)
        np.testing.assert_allclose(nodes[slot[(0, 1)]], [0.5, 0.0, 0.0])

    def test_a_sound_mesh_is_left_alone(self):
        import numpy as np

        from cadgen._internal.fea.mesh import straighten_inverted

        nodes, tets, slot = self._pair()
        nodes[slot[(0, 1)]] = [0.5, 0.0, 0.0]
        kept = nodes.copy()
        self.assertEqual(straighten_inverted(nodes, tets), 0)
        np.testing.assert_array_equal(nodes, kept)

    def test_an_element_of_flat_corners_is_refused_with_where_it_is(self):
        from cadgen._internal.fea.mesh import straighten_inverted

        nodes, tets, _ = self._pair()
        nodes[3] = [0.5, 0.5, 0.0]  # A's fourth corner in the plane of the other three
        with self.assertRaisesRegex(RuntimeError, r"corners enclose no volume, the first at \(0, 0, 0\); \(1, 0, 0\)"):
            straighten_inverted(nodes, tets)


@needs_fea
class ThinTube(unittest.TestCase):
    """A tube of a 0.5 mm wall at 3 mm elements: netgen's ``SecondOrder`` turns some elements inside out where it
    curves them onto the bore, which CalculiX refused (``nonpositive jacobian``). They are straightened, and it solves."""

    @classmethod
    def setUpClass(cls):
        from build123d import Cylinder, export_step

        directory = class_directory(cls)
        cls.step = directory / "tube.step"
        export_step(Cylinder(5.0, 20.0) - Cylinder(4.5, 20.0), str(cls.step))
        bottom, top = ends(cls.step, axis=2)
        cls.study = {"material": STEEL_NUMBERS, "fixtures": [{"faces": [bottom], "type": "fixed"}],
                     "loads": [{"faces": [top], "type": "force", "vector_N": [50.0, 0, 0]}], "mesh": {"size_mm": 3.0}}
        cls.result = solve(cls.step, directory / "tube.glb", cls.study)

    def test_it_solves_and_says_how_many_elements_were_straightened(self):
        straightened = self.result.mesh["straightened"]
        self.assertGreater(straightened, 0)
        self.assertEqual(reported(self.result)["mesh"]["straightened"], straightened)
        self.assertEqual(glb_extras(self.result.glb)["study"]["mesh"]["straightened"], straightened)


class PeakFace(unittest.TestCase):
    """Which face the peak node sits on, from the boundary triangles alone."""

    def _peak_face(self, peak_node: int, fixed: set[int]):
        import numpy as np

        from cadgen._internal.fea.static import peak_face as _peak_face

        # Two triangles on f1, one on f2, sharing node 2 (an edge between them); node 9 is inside.
        volume = SimpleNamespace(
            boundary_ordinal=np.array([1, 1, 2]),
            faces={ordinal: SimpleNamespace(ref=f"face {ordinal}") for ordinal in (1, 2)},
            max_h=1.0,
        )
        outcome = SimpleNamespace(
            boundary_quadratic=np.array([
                [0, 1, 2, 10, 11, 12], [1, 3, 2, 13, 14, 11], [2, 4, 5, 15, 16, 17],
            ]),
            dof_locations=np.arange(60, dtype=float).reshape(20, 3) * 10.0,
        )
        return _peak_face(volume, outcome, peak_node, fixed)

    def test_an_interior_peak_has_no_face(self):
        self.assertIsNone(self._peak_face(9, {1}))

    def test_a_peak_on_an_unfixed_face_names_it(self):
        self.assertEqual(self._peak_face(4, {1}), "face 2")

    def test_a_peak_on_an_edge_names_the_fixed_face(self):
        self.assertEqual(self._peak_face(2, {2}), "face 2")
        self.assertEqual(self._peak_face(2, set()), "face 1")

    def _near_miss(self, distance: float):
        """A peak node on free face f2, ``distance`` mm (elements of 1 mm) from fixed face f1's nodes."""
        import numpy as np

        from cadgen._internal.fea.static import peak_face as _peak_face

        volume = SimpleNamespace(
            boundary_ordinal=np.array([1, 2]),
            faces={ordinal: SimpleNamespace(ref=f"face {ordinal}") for ordinal in (1, 2)},
            max_h=1.0,
        )
        outcome = SimpleNamespace(
            boundary_quadratic=np.array([[0, 1, 2, 3, 4, 5], [6, 7, 8, 9, 10, 11]]),
            dof_locations=np.zeros((12, 3)),
        )
        outcome.dof_locations[6] = (distance, 0.0, 0.0)  # the peak node; fixed face's nodes sit at the origin
        return _peak_face(volume, outcome, 6, {1})

    def test_a_peak_within_half_an_element_of_a_fixed_face_is_at_it(self):
        self.assertEqual(self._near_miss(0.4), "face 1")

    def test_a_peak_two_elements_from_a_fixed_face_is_on_its_own_face(self):
        self.assertEqual(self._near_miss(2.0), "face 2")


class DofWarning(unittest.TestCase):
    def test_the_automatic_resolve_does_not_blame_the_mesh_size(self):
        from cadgen._internal.fea.solve import dof_warning

        text = dof_warning(620922, automatic=True)
        self.assertEqual(text, "the automatic finer check used 620922 degrees of freedom, so this study took longer")
        self.assertNotIn("mesh.size_mm", text)

    def test_a_large_first_solve_keeps_the_advice(self):
        from cadgen._internal.fea.solve import dof_warning

        self.assertEqual(
            dof_warning(500000, automatic=False),
            "500000 degrees of freedom: expect a slow solve; a larger mesh.size_mm is usually enough",
        )

    def test_small_features_are_named_as_the_cause(self):
        from cadgen._internal.fea.solve import dof_warning

        text = dof_warning(755373, automatic=False, small_feature_mm=0.4)
        self.assertIn("small features (thin walls, fillets, chamfers) set the mesh here", text)
        self.assertIn("elements down to 0.4 mm", text)
        self.assertIn("a larger mesh.size_mm won't help much", text)


@needs_fea
class SmallFeatures(unittest.TestCase):
    """A part of small fillets meshes by its own size, not by a ten-times larger element size asked for."""

    @classmethod
    def setUpClass(cls):
        from build123d import Box, export_step, fillet

        from cadgen._internal.fea.mesh import mesh_occurrence
        from cadgen._internal.fea.document import read_document

        tmp = class_directory(cls)
        plain, rounded = Box(60, 40, 10), fillet(Box(60, 40, 10).edges(), 0.3)
        meshes = []
        for name, shape in (("plain", plain), ("rounded", rounded)):
            export_step(shape, str(tmp / f"{name}.step"))
            occurrence = next(iter(read_document(tmp / f"{name}.step").leaves()))
            meshes.append(mesh_occurrence(occurrence, max_h=15.0))
        cls.plain, cls.rounded = meshes

    def test_a_fillet_does_not_multiply_the_mesh(self):
        # netgen's own defaults made 187k tets of this 60 x 40 x 10 plate at 15 mm; _MESHING makes about 64k.
        self.assertLess(len(self.rounded.tets), 90_000)

    def test_the_feature_size_is_reported_only_when_it_sets_the_mesh(self):
        from cadgen._internal.fea.mesh import small_feature_mm

        self.assertIsNone(small_feature_mm(self.plain))
        size = small_feature_mm(self.rounded)
        self.assertIsNotNone(size)
        self.assertLess(size, 1.0)


@needs_fea
class DefaultSizeAccuracy(unittest.TestCase):
    """Round and holed parts at the default element size, against closed forms, within 10%.

    The mesher is told how finely to follow curvature (``_MESHING``); too
    coarse a setting facets a slender rod or a small hole with elements the
    size of its radius. These two cases are where that shows: a rod whose
    default element size is close to its radius, and a hole a tenth of the
    plate's width.
    """

    # The rod: 6 mm round steel, 100 mm long, fixed at x = 0, 10 N down at x = L.
    ROD_LENGTH, ROD_RADIUS, ROD_FORCE = 100.0, 3.0, 10.0
    # The plate: 120 x 40 x 5 mm steel with a 4 mm hole at its centre, 2 kN along +X.
    PLATE_LENGTH, PLATE_WIDTH, PLATE_THICKNESS, HOLE, PULL = 120.0, 40.0, 5.0, 4.0, 2000.0

    @classmethod
    def setUpClass(cls):
        from build123d import Align, Box, Cylinder, Pos, Rot, export_step

        tmp = class_directory(cls)
        rod = tmp / "rod.step"
        export_step(Rot(0, 90, 0) * Cylinder(cls.ROD_RADIUS, cls.ROD_LENGTH, align=(Align.CENTER, Align.CENTER, Align.MIN)), str(rod))
        fixed, loaded = ends(rod)
        cls.rod = solve(rod, tmp / "rod.glb", {
            "material": STEEL_NUMBERS,
            "fixtures": [{"faces": [fixed]}],
            "loads": [{"faces": [loaded], "type": "force", "vector_N": [0, 0, -cls.ROD_FORCE]}],
        }, vtu=True)

        plate = tmp / "plate.step"
        body = Box(cls.PLATE_LENGTH, cls.PLATE_WIDTH, cls.PLATE_THICKNESS, align=(Align.MIN, Align.CENTER, Align.CENTER))
        export_step(body - Pos(cls.PLATE_LENGTH / 2, 0, 0) * Cylinder(cls.HOLE / 2, 2 * cls.PLATE_THICKNESS), str(plate))
        fixed, loaded = ends(plate)
        cls.plate = solve(plate, tmp / "plate.glb", {
            "material": STEEL_NUMBERS,
            "fixtures": [{"faces": [fixed]}],
            "loads": [{"faces": [loaded], "type": "force", "vector_N": [cls.PULL, 0, 0]}],
        })

    def test_the_rod_is_meshed_at_the_default_size(self):
        self.assertIsNone(reported(self.rod)["refined"])
        self.assertGreater(self.rod.mesh["size_mm"], 0.8 * self.ROD_RADIUS)

    def test_the_round_rods_tip_deflection_matches_beam_theory(self):
        inertia = math.pi * self.ROD_RADIUS ** 4 / 4
        expected = self.ROD_FORCE * self.ROD_LENGTH ** 3 / (3 * STEEL.E * inertia)
        self.assertAlmostEqual(self.rod.summary["max_displacement_mm"] / expected, 1.0, delta=0.10)

    def test_the_round_rods_top_fibre_stress_matches_my_over_i(self):
        # Not the peak: that sits on the clamped edge, a singularity that grows
        # with every refinement. A quarter along (four diameters from the
        # clamp, past its reach) the top fibre carries the beam's own M y / I,
        # compared node by node with the moment and height at each node.
        # Measured +8.6% (nodes +3.6% to +11.6%) with netgen 6.2.2608; the mean
        # is over mesh-dependent nodes, so the CI fea job pins that netgen.
        import numpy as np

        xyz, von_mises = _vtu_von_mises(self.rod.vtu)
        size = self.rod.mesh["size_mm"]
        x, y, z = xyz.T
        top = (np.abs(x - self.ROD_LENGTH / 4) < size) & (z > 0.7 * self.ROD_RADIUS) & (np.hypot(y, z) > self.ROD_RADIUS - 1e-3)
        self.assertGreaterEqual(top.sum(), 3)
        inertia = math.pi * self.ROD_RADIUS ** 4 / 4
        beam = self.ROD_FORCE * (self.ROD_LENGTH - x[top]) * z[top] / inertia
        self.assertAlmostEqual(float(np.mean(von_mises[top] / beam)), 1.0, delta=0.10)

    def test_the_holes_peak_matches_petersons_kt(self):
        # Peterson's finite-width Kt (Howland's values, net section) for a
        # central hole in tension; the peak is the nodal one the run reports,
        # and it must sit on the hole's wall, not at the clamp.
        ratio = self.HOLE / self.PLATE_WIDTH
        kt = 3.0 - 3.14 * ratio + 3.667 * ratio ** 2 - 1.527 * ratio ** 3
        net = self.PULL / ((self.PLATE_WIDTH - self.HOLE) * self.PLATE_THICKNESS)
        x, y, _ = self.plate.summary["max_von_mises_at_mm"]
        self.assertAlmostEqual(math.hypot(x - self.PLATE_LENGTH / 2, y), self.HOLE / 2, delta=0.05)
        self.assertAlmostEqual(self.plate.summary["max_von_mises_MPa"] / (kt * net), 1.0, delta=0.10)


@needs_fea
class FinerAtCurves(unittest.TestCase):
    """A part whose 0.5 mm fillets set its mesh: a smaller element size alone leaves it as it was."""

    @classmethod
    def setUpClass(cls):
        from build123d import Box, export_step, fillet

        from cadgen._internal.fea.mesh import mesh_occurrence
        from cadgen._internal.fea.document import read_document

        step = class_directory(cls) / "rounded.step"
        export_step(fillet(Box(30, 20, 6).edges(), 0.5), str(step))
        occurrence = next(iter(read_document(step).leaves()))
        cls.first = len(mesh_occurrence(occurrence, max_h=8.0).tets)
        cls.halved = len(mesh_occurrence(occurrence, max_h=4.0).tets)
        cls.refined = len(mesh_occurrence(occurrence, max_h=4.0, refine=2.0).tets)

    def test_halving_the_element_size_alone_barely_changes_a_fillet_governed_mesh(self):
        self.assertLess(self.halved, 1.3 * self.first)

    def test_refining_curved_features_by_the_same_ratio_makes_it_materially_finer(self):
        self.assertGreater(self.refined, 2.0 * self.first)


class HumanLine(unittest.TestCase):
    def test_the_cli_line_floors_the_safety_factor_like_the_findings(self):
        from cadgen.results import FeaResult

        result = FeaResult(
            ok=True, document=Path("p.step"), occurrence="part", glb=Path("p.glb"),
            summary={"safety_factor": 1.684}, mesh={},
        )
        self.assertIn("safety factor 1.6", result.human_lines()[1])
        self.assertNotIn("1.684", result.human_lines()[1])


# A link bar whose pin holes' quadratic tetrahedra (netgen, 3.6 mm elements) bow up to 0.8 mm off the chord: a force on
# a curved hole must still be spread over its curved facets and balance.
def _write_link_bar(directory: Path) -> Path:
    """A 140 x 30 x 8 mm bar with a 10 mm pin hole 12 mm in from each end (f7 at x = -58, f8 at x = +58)."""
    from build123d import Align, Box, Cylinder, Pos, export_step

    low = (Align.CENTER, Align.CENTER, Align.MIN)
    path = directory / "link_bar.step"
    export_step(Box(140, 30, 8, align=low) - Pos(-58, 0, 0) * Cylinder(5, 8, align=low)
                - Pos(58, 0, 0) * Cylinder(5, 8, align=low), str(path))
    return path


@needs_fea
class CurvedFacetLoads(unittest.TestCase):
    """A load on a curved face: integrated over the curved six-node triangles, it balances."""

    def test_a_force_on_a_pin_hole_solves_and_balances(self):
        """Before the fix this solve raised "Newton iteration didn't converge" building the pin hole's facet basis."""
        with tempfile.TemporaryDirectory() as tmp:
            # Light enough to keep a safety factor over 3: one solve, at the size that met the stalling element.
            study = {"material": AL7075_NUMBERS, "fixtures": [{"faces": ["face 7"]}],
                     "loads": [{"faces": ["face 8"], "type": "force", "vector_N": [3600, 0, 0]}], "mesh": {"size_mm": 3.585}}
            result = solve(_write_link_bar(Path(tmp)), Path(tmp) / "bar.fea.glb", study)
        self.assertTrue(result.ok)
        self.assertEqual(result.summary["applied_force_N"], [3600.0, 0.0, 0.0])
        self.assertAlmostEqual(result.summary["reaction_force_N"][0], -3600.0, places=3)
        # The net section past the hole carries 3600 N over (30 - 10) x 8 mm: 22.5 MPa; a pin-loaded lug peaks at
        # two to three times its net-section stress.
        self.assertGreater(result.summary["max_von_mises_MPa"], 1.5 * 22.5)
        self.assertLess(result.summary["max_von_mises_MPa"], 4.0 * 22.5)



class CheckLines(unittest.TestCase):
    def test_a_check_far_under_its_limit_says_under_1_percent_not_0_00_times(self):
        from cadgen.results import FeaResult

        def stress(value, ratio):
            return {"label": "Strength", "value": value, "limit": 250.0, "unit": "MPa", "ratio": ratio, "status": "passes"}

        result = FeaResult(ok=True, document=Path("p.step"), occurrence="part", glb=Path("p.glb"),
                           summary={"safety_factor": 2.5, "checks": [stress(0.0053, 2.12e-05), stress(2.5, 0.01)]},
                           mesh={"elements": 10})
        lines = result.human_lines()
        self.assertIn("check 'Strength': 0.0053 MPa against a 250 MPa limit, under 1% of it, passes", lines)
        self.assertIn("check 'Strength': 2.5 MPa against a 250 MPa limit, 0.01× it, passes", lines)
        self.assertFalse(any("0.00×" in line for line in lines))


@needs_fea
class MeshRefine(unittest.TestCase):
    """``mesh.refine``'s balls, as the size field's points: local sizes that refine where they say."""

    def test_a_size_field_refines_where_it_says(self):
        from cadgen._internal.fea.document import read_document
        from cadgen._internal.fea.mesh import mesh_occurrence

        with tempfile.TemporaryDirectory() as tmp:
            step = box_step(Path(tmp), "cantilever", (40.0, 4.0, 4.0), "x")
            occurrence = next(iter(read_document(step).leaves()))
            plain = mesh_occurrence(occurrence, max_h=2.0)
            by_point = mesh_occurrence(occurrence, max_h=2.0, size_field={"points": [[20.0, 0.0, 0.0, 0.5]], "radius_mm": 1.0})
        self.assertGreater(len(by_point.tets), 1.5 * len(plain.tets))


if __name__ == "__main__":
    unittest.main()


@needs_fea
class ModelMaterial(unittest.TestCase):
    """A part solved with its model's own material: the bd_materials its xbf holds, read when the study gives none."""

    @classmethod
    def setUpClass(cls):
        import textwrap

        from cadgen.engine import build as engine_build

        cls.directory = class_directory(cls)
        script = cls.directory / "bar.py"
        script.write_text(textwrap.dedent('''
            import build123d as bd
            from bd_materials import metals
            from cadgen.engine import xbf


            @xbf(out="XBF/bar.xbf")
            def bar():
                part = bd.Box(40, 10, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.CENTER))
                part.material = metals.aluminum()
                return part
        '''), encoding="utf-8")
        (report,) = engine_build.build(script, ["bar"], cwd=cls.directory, log=[].append)
        assert report["ok"], report
        cls.xbf = cls.directory / "XBF" / "bar.xbf"
        fixed, load = ends(cls.xbf)
        cls.study = {"fixtures": [{"faces": [fixed]}], "loads": [{"faces": [load], "type": "force", "vector_N": [0, 0, -100.0]}],
                     "mesh": {"size_mm": 2.0}}

    def test_a_study_with_no_material_takes_the_models(self):
        from bd_materials import metals

        physics = metals.aluminum().material
        said = reported(solve(self.xbf, self.directory / "own.glb", self.study))["material"]
        self.assertEqual((said["name"], said["source"]), (metals.aluminum().name, "document"))
        self.assertEqual(said["yield_MPa"], physics.yield_strength.min)    # the low end: the weakest it may be
        self.assertEqual(said["ranges"]["yield_MPa"], [physics.yield_strength.min, physics.yield_strength.max])

    def test_a_studys_own_numbers_win_over_the_models(self):
        said = reported(solve(self.xbf, self.directory / "given.glb", {**self.study, "material": AL6061_NUMBERS}))["material"]
        self.assertEqual((said["name"], said["yield_MPa"], said["source"]), ("Aluminum 6061-T6", 276.0, "study"))
