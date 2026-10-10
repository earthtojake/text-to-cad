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
from contextlib import contextmanager, redirect_stderr, redirect_stdout
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

@contextmanager
def quiet():
    """The CLI's progress lines go to stderr; a test that is not about them keeps them out of the run's output."""
    with redirect_stderr(io.StringIO()):
        yield


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


TIP = _timoshenko_tip_deflection()


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


def _glb_attribute(path: Path, name: str, width: int) -> "np.ndarray":
    """One vertex attribute of the result GLB, (count, width) floats."""
    import struct

    import numpy as np

    raw = path.read_bytes()
    json_length, _ = struct.unpack_from("<II", raw, 12)
    gltf = json.loads(raw[20:20 + json_length])
    binary = raw[20 + json_length + 8:]
    accessor = gltf["accessors"][gltf["meshes"][0]["primitives"][0]["attributes"][name]]
    view = gltf["bufferViews"][accessor["bufferView"]]
    data = np.frombuffer(binary, np.float32, accessor["count"] * width, view["byteOffset"])
    return data.reshape(-1, width).astype(float)


def _glb_indices(path: Path) -> "np.ndarray":
    import struct

    import numpy as np

    raw = path.read_bytes()
    json_length, _ = struct.unpack_from("<II", raw, 12)
    gltf = json.loads(raw[20:20 + json_length])
    accessor = gltf["accessors"][gltf["meshes"][0]["primitives"][0]["indices"]]
    view = gltf["bufferViews"][accessor["bufferView"]]
    return np.frombuffer(raw[20 + json_length + 8:], np.uint32, accessor["count"], view["byteOffset"])


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


# The agent's view of a result: which controls Study's Result shows, named states, and the markers.
VIEW = {
    "controls": [
        {"drives": "field", "type": "enum", "label": "Show", "options": ["von_mises", "displacement"], "default": "von_mises"},
        {"drives": "deformation", "type": "number", "label": "Exaggerate", "min": 0, "max": 50, "default": 12},
        {"drives": "load_scale", "type": "number", "label": "Rider weight", "min": 0.5, "max": 3, "default": 1, "unit": "×"},
        {"drives": "threshold", "type": "number", "label": "Show above", "field": "von_mises", "min": 0, "max": 300, "default": 138, "unit": "MPa"},
    ],
    "presets": [{"label": "Landing (3×)", "load_scale": 3}],
    "show": {"loads": True, "fixtures": False},
}


class StudyView(unittest.TestCase):
    """The study's optional ``view``: checked like the rest of the study, before any heavy import."""

    BASE = {"material": "steel", "fixtures": [{"faces": ["#o1.f1"]}], "loads": [{"faces": ["#o1.f2"], "type": "force", "vector_N": [1, 0, 0]}]}

    def _view(self, **changes):
        return {**VIEW, **changes}

    def _control(self, drives, **changes):
        controls = [dict(control, **changes) if control["drives"] == drives else control for control in VIEW["controls"]]
        return self._view(controls=controls)

    def test_a_view_parses_as_written_and_no_view_is_none(self):
        self.assertIsNone(parse_study(self.BASE).view)
        self.assertEqual(parse_study({**self.BASE, "view": VIEW}).view, VIEW)

    def test_a_bare_control_takes_its_type_and_range_defaults(self):
        view = parse_study({**self.BASE, "view": {"controls": [{"drives": "deformation", "max": 40}, {"drives": "load_scale", "max": 2}]}}).view
        # A deformation with no default leaves it to the result's own exaggeration; a load_scale starts at a tenth of the load.
        self.assertEqual(view["controls"][0], {"drives": "deformation", "type": "number", "min": 0.0, "max": 40.0})
        self.assertEqual(view["controls"][1], {"drives": "load_scale", "type": "number", "min": 0.1, "max": 2.0, "default": 1.0})
        # One with no range at all runs to four times the result's own exaggeration, which the viewer reads; half a range is refused.
        bare = parse_study({**self.BASE, "view": {"controls": [{"drives": "deformation", "label": "Exaggerate"}]}}).view
        self.assertEqual(bare["controls"], [{"drives": "deformation", "type": "number", "label": "Exaggerate"}])
        with self.assertRaises(ValueError) as caught:
            parse_study({**self.BASE, "view": {"controls": [{"drives": "deformation", "default": 12}]}})
        self.assertIn("leave min, max and default all out", str(caught.exception))

    def test_show_parts_overrides_when_the_parts_panel_shows_either_way(self):
        for shown in (True, False):
            self.assertEqual(parse_study({**self.BASE, "view": {"show": {"parts": shown}}}).view, {"show": {"parts": shown}})

    def test_presets_with_no_controls_set_the_default_field_and_deformation(self):
        presets = [{"label": "Exaggerated", "deformation": 40, "field": "displacement"}]
        self.assertEqual(parse_study({**self.BASE, "view": {"presets": presets}}).view, {"presets": [{"label": "Exaggerated", "deformation": 40.0, "field": "displacement"}]})
        with self.assertRaises(ValueError) as caught:
            parse_study({**self.BASE, "view": {"presets": [{"label": "Heavy", "load_scale": 2}]}})
        self.assertIn("a preset here can set only label, deformation, field", str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            parse_study({**self.BASE, "view": {"presets": [{"label": "Inside out", "deformation": -1}]}})
        self.assertIn("view.presets[0].deformation: -1 must be 0 or more", str(caught.exception))

    def test_a_malformed_view_is_a_study_error_in_a_plain_sentence(self):
        threshold_on_safety = self._control("threshold", field="safety_factor")
        cases = [
            (self._view(colours=1), "view: unknown keys ['colours']"),
            (self._control("field", colour="red"), "view.controls[0]: unknown keys ['colour']"),
            (self._view(controls=[{"drives": "speed", "max": 1}]), "view.controls[0].drives: 'speed' is not one of"),
            (self._view(controls=[{"drives": "deformation", "max": 9}, {"drives": "deformation", "max": 4}]), "only one control drives deformation"),
            (self._control("field", options=["von_mises", "safety_factor"]), "'safety_factor' is not a field the result writes"),
            (self._control("field", default="displacement", options=["von_mises"]), "default 'displacement' is not one of its options"),
            (self._control("deformation", type="enum"), "a deformation control is a number"),
            (self._control("load_scale", min=3, max=1), "min (3) must be below max (1)"),
            (self._control("load_scale", default=5), "default (5) must be between min (0.5) and max (3)"),
            (self._control("deformation", min=-1), "min (-1) must be zero or more"),
            (self._control("load_scale", min=0), "view.controls[2].min: a load_scale control starts above no load; min (0) must be more than 0"),
            (self._control("threshold", max=float("inf")), "view.controls[3].max: expected a finite number, got inf"),
            (self._control("deformation", default=float("nan")), "view.controls[1].default: expected a finite number, got nan"),
            (self._control("deformation", max=True), "view.controls[1].max: expected a number, got true"),
            (self._view(presets=[{"label": "Huge", "load_scale": float("inf")}]), "view.presets[0].load_scale: expected a finite number"),
            (self._view(controls=[]), "view.controls is empty: leave it out for the default controls"),
            (threshold_on_safety, "'safety_factor' is not a field the result writes"),
            (self._control("threshold", field=None), "view.controls[3].field: name the field it compares"),
            (self._control("deformation", field="von_mises"), "view.controls[1]: unknown keys ['field']"),
            (self._view(presets=[{"label": "Bump", "threshold": 50, "load_scale": 9}]), "view.presets[0].load_scale: 9 must be between"),
            (self._view(presets=[{"label": "Bump", "mesh": 1}]), "view.presets[0]: 'mesh' is not a control"),
            (self._view(presets=[{"load_scale": 2}]), "view.presets[0].label"),
            (self._view(presets=[{"label": "Flip", "field": "strain"}]), "view.presets[0].field: 'strain' is not one of"),
            (self._view(show={"loads": "yes"}), "view.show.loads: true or false"),
            (self._view(show={"arrows": True}), "view.show: unknown keys ['arrows']; expected loads, fixtures, parts"),
            (self._view(colours=1), "expected checks, sections, controls, presets, show"),
            (self._view(show={"parts": 1}), "view.show.parts: true or false, got 1"),
        ]
        for view, fragment in cases:
            with self.subTest(fragment=fragment), self.assertRaises(ValueError) as caught:
                parse_study({**self.BASE, "view": view})
            self.assertIn(fragment, str(caught.exception))
        # A preset may only set what a declared control drives.
        with self.assertRaises(ValueError) as caught:
            parse_study({**self.BASE, "view": {"controls": [VIEW["controls"][0]], "presets": [{"label": "Heavy", "load_scale": 2}]}})
        self.assertIn("'load_scale' is not a control", str(caught.exception))

    def test_checks_sections_and_when_parse_as_written(self):
        view = {
            "checks": [{"kind": "stress", "margin": 2, "label": "Strength"}, {"kind": "displacement", "limit_mm": 0.5, "faces": ["#o1.f2"], "label": "Tip sag"}],
            "sections": ["verdict", "controls"],
            "controls": [{"drives": "load_scale", "max": 2, "when": "failing"}],
        }
        study = parse_study({**self.BASE, "view": view})
        self.assertEqual(study.view["checks"], [
            {"kind": "stress", "margin": 2.0, "label": "Strength"}, {"kind": "displacement", "limit_mm": 0.5, "faces": ["#o1.f2"], "label": "Tip sag"}])
        self.assertEqual(study.view["sections"], ["verdict", "controls"])
        self.assertEqual(study.view["controls"][0]["when"], "failing")
        self.assertEqual(study.check_faces, ("#o1.f2",))
        # The stress check's margin is the study's.
        self.assertEqual(study.margin, 2.0)
        self.assertEqual(parse_study({**self.BASE, "view": {"checks": [{"kind": "stress", "margin": 3}]}}).margin, 3.0)

    def test_with_no_checks_the_stress_check_alone_judges_the_result(self):
        self.assertEqual(parse_study(self.BASE).checks, ({"kind": "stress"},))
        self.assertEqual(parse_study({**self.BASE, "view": {"show": {"loads": True}}}).checks, ({"kind": "stress"},))
        self.assertEqual(parse_study(self.BASE).check_faces, ())

    def test_a_malformed_check_section_or_when_is_a_plain_sentence(self):
        cases = [
            ({"checks": []}, "view.checks is empty: leave it out for the stress check alone"),
            ({"checks": {"kind": "stress"}}, "view.checks: expected a list"),
            ({"checks": [{"kind": "frequency"}]}, 'view.checks[0].kind: "frequency" is not a check this cadgen makes'),
            ({"checks": ["stress"]}, "view.checks[0]: expected an object"),
            ({"checks": [{"kind": "stress"}, {"kind": "stress"}]}, "only one stress check"),
            ({"checks": [{"kind": "stress", "limit_mm": 1}]}, "view.checks[0]: unknown keys ['limit_mm']; a stress check takes"),
            ({"checks": [{"kind": "stress", "margin": 0.5}]}, "view.checks[0].margin: a safety factor below 1 means the part yields"),
            ({"checks": [{"kind": "displacement"}]}, "view.checks[0].limit_mm: a displacement check needs the most it may move"),
            ({"checks": [{"kind": "displacement", "limit_mm": 0}]}, "view.checks[0].limit_mm: must be > 0"),
            ({"checks": [{"kind": "displacement", "limit_mm": 1, "faces": []}]}, "view.checks[0]: 'faces' must be a non-empty list"),
            ({"checks": [{"kind": "displacement", "limit_mm": 1, "label": ""}]}, "view.checks[0].label: expected a short piece of text"),
            ({"sections": []}, "view.sections: list the parts of Study to show"),
            ({"sections": ["verdict", "chart"]}, 'view.sections[1]: "chart" is not one of'),
            ({"sections": ["setup", "setup"]}, "view.sections[1]: 'setup' is listed twice"),
            ({"controls": [{"drives": "load_scale", "max": 2, "when": "sometimes"}]}, 'view.controls[0].when: "sometimes" is not one of'),
        ]
        for view, fragment in cases:
            with self.subTest(fragment=fragment), self.assertRaises(ValueError) as caught:
                parse_study({**self.BASE, "view": view})
            self.assertIn(fragment, str(caught.exception))
            self.assertNotIn("\u2014", str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            parse_study({**self.BASE, "margin": 2, "view": {"checks": [{"kind": "stress", "margin": 3}]}})
        self.assertIn("the stress check's margin (3) is not the study's margin (2); give it once", str(caught.exception))


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
                write_glb(path, extras={"faces": ["#o1.f1"], "view": {"max": math.inf}}, **mesh)
            self.assertFalse(path.exists())


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
            # Generous limits: the checks pass, so the part still has nothing to say.
            "view": {**VIEW, "checks": [
                {"kind": "stress"},
                {"kind": "displacement", "limit_mm": 2 * TIP},
                {"kind": "displacement", "limit_mm": 1.05 * TIP, "faces": [cls.load_ref], "label": "Tip sag"},
                {"kind": "displacement", "limit_mm": TIP, "faces": [cls.fixed_ref], "label": "Clamp"},
            ]},
        }
        cls.out = directory / "results" / "cantilever.glb"
        cls.solver = _CountingSolve()
        with mock.patch("cadgen._internal.fea.solve.solve_linear_static", cls.solver), quiet():
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

    def test_the_view_names_only_fields_the_glb_writes(self):
        from cadgen._internal.fea.study import VIEW_FIELDS

        written = {field["attribute"] for field in _glb_extras(self.result.glb)["fields"]}
        self.assertLessEqual({f"_{name.upper()}" for name in VIEW_FIELDS}, written)

    def test_the_studys_view_is_copied_into_the_glb_and_the_sidecar(self):
        self.assertEqual(_glb_extras(self.result.glb)["view"], self.study["view"])
        self.assertEqual(json.loads(self.result.sidecar.read_text(encoding="utf-8"))["view"], self.study["view"])

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

    def test_the_checks_are_written_into_the_glb_the_sidecar_and_the_lines(self):
        checks = self.result.summary["checks"]
        self.assertEqual(_glb_extras(self.result.glb)["checks"], checks)
        self.assertEqual(json.loads(self.result.sidecar.read_text(encoding="utf-8"))["summary"]["checks"], checks)
        lines = self.result.human_lines()
        tip = checks[2]
        self.assertIn(f"check 'Tip sag': {tip['value']:g} mm against a {tip['limit']:g} mm limit, {tip['ratio']:.2f}× it, close", lines)
        self.assertEqual(sum(line.startswith("check '") for line in lines), 4)

    def test_the_glb_names_its_step_relative_to_its_own_folder(self):
        self.assertEqual(_glb_extras(self.result.glb)["document"], f"../{self.step.name}")
        sidecar = json.loads(self.result.sidecar.read_text(encoding="utf-8"))
        self.assertEqual(sidecar["document"], str(self.step))

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
        attributes = gltf["meshes"][0]["primitives"][0]["attributes"]
        self.assertEqual(set(attributes), {"POSITION", "NORMAL", "COLOR_0", "_VON_MISES", "_DISPLACEMENT", "_FACE"})
        extras = gltf["meshes"][0]["extras"]
        self.assertEqual(extras["deformation_scale"], self.result.summary["deformation_scale"])
        self.assertEqual([f["attribute"] for f in extras["fields"]], ["_VON_MISES", "_DISPLACEMENT"])
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
        study = _glb_extras(self.result.glb)["study"]
        self.assertEqual(study["material"]["name"], "Steel (structural, generic)")
        self.assertEqual(set(study["material"]), {"name", "yield_MPa", "youngs_GPa", "poisson"})
        self.assertAlmostEqual(study["material"]["youngs_GPa"], 200.0, delta=15)
        self.assertEqual(study["fixtures"], [{"type": "fixed", "faces": [self.fixed_ref]}])
        self.assertTrue(self.fixed_ref.startswith("#o"))
        self.assertEqual(study["loads"], [{"type": "force", "faces": [self.load_ref], "vector_N": [0, 0, -FORCE]}])
        self.assertEqual(study["mesh"]["size_mm"], self.result.mesh["size_mm"])
        self.assertEqual((study["mesh"]["order"], study["mesh"]["elements"], study["mesh"]["refined_from_mm"]),
                         (2, self.result.mesh["elements"], None))
        self.assertEqual(study["margin"], 2.0)

    def test_every_surface_triangle_traces_to_a_source_face(self):
        import numpy as np

        extras = _glb_extras(self.result.glb)
        self.assertEqual(extras["faces"], [face.ref for face in self.listing.faces])
        face = _glb_attribute(self.result.glb, "_FACE", 1)[:, 0].astype(int)
        indices = _glb_indices(self.result.glb).reshape(-1, 3)
        self.assertTrue(((face >= 0) & (face < len(extras["faces"]))).all())
        # a triangle's three vertices lie on one face
        self.assertTrue((face[indices[:, 0]] == face[indices[:, 1]]).all() and (face[indices[:, 0]] == face[indices[:, 2]]).all())
        undeformed = _glb_attribute(self.result.glb, "POSITION", 3) - extras["deformation_scale"] * _glb_attribute(self.result.glb, "_DISPLACEMENT", 3)
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
        sidecar = json.loads(self.result.sidecar.read_text(encoding="utf-8"))
        self.assertEqual(sidecar["findings"], [])
        self.assertIsNone(sidecar["refined"])
        self.assertEqual(_glb_extras(self.result.glb)["findings"], [])
        self.assertEqual(self.result.mesh["size_mm"], 2.0)

    def test_a_face_on_a_different_part_or_a_non_face_is_refused(self):
        from cadgen import fea

        with self.assertRaises(ValueError) as caught, quiet():
            fea.solve(self.step, study={**self.study, "fixtures": [{"faces": [self.fixed_ref.rsplit(".", 1)[0]]}]})
        self.assertIn("faces", str(caught.exception))
        with self.assertRaises(ValueError), quiet():
            fea.solve(self.step, study={**self.study, "loads": [{"faces": ["#o1.f99"], "type": "force", "vector_N": [1, 0, 0]}]})

    def test_out_must_be_a_glb(self):
        from cadgen import fea

        with self.assertRaises(ValueError) as caught, quiet():
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
        from cadgen._internal.fea import mesh

        real_mesh, cls.meshed = mesh.mesh_occurrence, []

        def mesh_spy(occurrence, **kwargs):
            cls.meshed.append(kwargs)
            return real_mesh(occurrence, **kwargs)

        with mock.patch("cadgen._internal.fea.solve.solve_linear_static", cls.solver), \
                mock.patch("cadgen._internal.fea.mesh.mesh_occurrence", mesh_spy), quiet():
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

    def test_a_study_without_a_view_writes_none(self):
        self.assertNotIn("view", _glb_extras(self.result.glb))
        self.assertNotIn("view", self.sidecar)

    def test_with_no_view_the_stress_check_alone_says_what_the_safety_factor_says(self):
        (check,) = self.result.summary["checks"]
        self.assertEqual((check["kind"], check["status"]), ("stress", "fails"))
        self.assertEqual(check["ratio"], round(1 / self.result.summary["safety_factor"], 6))
        self.assertEqual(_glb_extras(self.result.glb)["checks"], [check])
        # The stress check's findings are the yields finding already made; it adds none of its own.
        self.assertEqual([f["type"] for f in self.result.findings].count("yields"), 1)
        self.assertNotIn("displacement_over_limit", [f["type"] for f in self.result.findings])

    def test_a_close_call_is_solved_again_finer_and_the_finer_result_is_written(self):
        self.assertEqual(self.solver.calls, 2)
        self.assertEqual(self.result.mesh["size_mm"], self.SIZE / 2)
        refined = self.sidecar["refined"]
        self.assertEqual((refined["from_size_mm"], refined["size_mm"]), (self.SIZE, self.SIZE / 2))
        self.assertEqual(refined["max_von_mises_MPa"], self.result.summary["max_von_mises_MPa"])
        self.assertEqual(_glb_extras(self.result.glb)["fields"][0]["max"], self.result.summary["max_von_mises_MPa"])
        mesh = _glb_extras(self.result.glb)["study"]["mesh"]
        self.assertEqual((mesh["size_mm"], mesh["refined_from_mm"]), (self.SIZE / 2, self.SIZE))

    def test_the_finer_solve_refines_curved_features_by_the_same_ratio(self):
        first, finer = self.meshed
        self.assertEqual(first.get("refine", 1.0), 1.0)
        self.assertAlmostEqual(finer["refine"], first["max_h"] / finer["max_h"], places=9)
        self.assertGreater(finer["refine"], 1.0)

    def test_the_findings_point_at_the_written_glbs_peak(self):
        yields = self.sidecar["findings"][0]
        self.assertEqual(yields["items"][0]["at"], self.result.summary["max_von_mises_at_mm"])
        for got, want in zip(_glb_peak_at(self.result.glb), yields["items"][0]["at"]):
            self.assertAlmostEqual(got, want, delta=1e-3)

    def test_the_safety_factor_is_floored_never_rounded_up(self):
        import math

        sf = self.result.summary["safety_factor"]
        self.assertEqual(sf, math.floor(sf * 1000) / 1000)

    def test_the_summary_safety_factor_is_yield_over_the_written_peak_when_the_finer_peak_is_lower(self):
        import dataclasses
        from unittest import mock

        from cadgen import fea

        def halve(outcome):
            return dataclasses.replace(
                outcome, von_mises=outcome.von_mises / 2, von_mises_gauss_max=outcome.von_mises_gauss_max / 2
            )

        solver = _CountingSolve(later=halve)
        with mock.patch("cadgen._internal.fea.solve.solve_linear_static", solver), quiet():
            result = fea.solve(self.step, Path(self._tmp.name) / "lower.glb", study=self.study)
        refined = json.loads(result.sidecar.read_text(encoding="utf-8"))["refined"]
        self.assertLess(refined["max_von_mises_MPa"], refined["from_max_von_mises_MPa"])
        self.assertAlmostEqual(result.summary["safety_factor"], 250.0 / result.summary["max_von_mises_MPa"], places=2)
        self.assertNotAlmostEqual(result.summary["safety_factor"], 250.0 / refined["from_max_von_mises_MPa"], places=2)
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
        with mock.patch("cadgen._internal.fea.solve.solve_linear_static", solver), quiet():
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
class FinerMeshSize(unittest.TestCase):
    """The automatic re-solve halves the element size unless that would pass the DOF budget."""

    @staticmethod
    def estimate(size, finer, dofs):
        return dofs * (size / finer) ** 3

    def test_a_small_part_halves(self):
        from cadgen._internal.fea.run import finer_mesh_size

        self.assertEqual(finer_mesh_size(2.0, 20_000), 1.0)

    def test_a_larger_part_is_capped_under_the_warn_threshold(self):
        from cadgen._internal.fea.run import finer_mesh_size
        from cadgen._internal.fea.solve import DOF_WARN

        finer = finer_mesh_size(2.0, 100_000)
        self.assertTrue(1.0 < finer < 2.0)
        self.assertAlmostEqual(self.estimate(2.0, finer, 100_000), DOF_WARN, delta=DOF_WARN * 1e-6)

    def test_a_part_already_past_the_warn_threshold_stays_under_the_limit(self):
        from cadgen._internal.fea.run import finer_mesh_size
        from cadgen._internal.fea.solve import DOF_LIMIT

        finer = finer_mesh_size(2.0, 679_000)  # a real L-bracket at its default size
        self.assertLess(finer, 2.0)
        self.assertLess(self.estimate(2.0, finer, 679_000), DOF_LIMIT)

    def test_a_first_solve_just_under_the_warn_threshold_falls_back_to_the_limit_budget(self):
        from cadgen._internal.fea.run import finer_mesh_size
        from cadgen._internal.fea.solve import DOF_LIMIT

        finer = finer_mesh_size(2.0, 350_000)  # the WARN budget would give a ratio under 1.1
        self.assertLess(finer, 1.9)
        self.assertLess(self.estimate(2.0, finer, 350_000), DOF_LIMIT)

    def test_no_finer_solve_when_there_is_no_room_for_one(self):
        from cadgen._internal.fea.run import finer_mesh_size

        self.assertIsNone(finer_mesh_size(2.0, 1_400_000))


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
        self.assertEqual(self._peak_face(4, {1}), "#o1.f2")

    def test_a_peak_on_an_edge_names_the_fixed_face(self):
        self.assertEqual(self._peak_face(2, {2}), "#o1.f2")
        self.assertEqual(self._peak_face(2, set()), "#o1.f1")

    def _near_miss(self, distance: float):
        """A peak node on free face f2, ``distance`` mm (elements of 1 mm) from fixed face f1's nodes."""
        from types import SimpleNamespace

        import numpy as np

        from cadgen._internal.fea.run import _peak_face

        volume = SimpleNamespace(
            boundary_ordinal=np.array([1, 2]),
            faces={ordinal: SimpleNamespace(ref=f"#o1.f{ordinal}") for ordinal in (1, 2)},
            max_h=1.0,
        )
        outcome = SimpleNamespace(
            boundary_quadratic=np.array([[0, 1, 2, 3, 4, 5], [6, 7, 8, 9, 10, 11]]),
            dof_locations=np.zeros((12, 3)),
        )
        outcome.dof_locations[6] = (distance, 0.0, 0.0)  # the peak node; fixed face's nodes sit at the origin
        return _peak_face(volume, outcome, 6, {1})

    def test_a_peak_within_half_an_element_of_a_fixed_face_is_at_it(self):
        self.assertEqual(self._near_miss(0.4), "#o1.f1")

    def test_a_peak_two_elements_from_a_fixed_face_is_on_its_own_face(self):
        self.assertEqual(self._near_miss(2.0), "#o1.f2")


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


@unittest.skipUnless(HAVE_FEA, "cadgen[fea] is not installed")
class SmallFeatures(unittest.TestCase):
    """A part of small fillets meshes by its own size, not by a ten-times larger element size asked for."""

    @classmethod
    def setUpClass(cls):
        from build123d import Box, export_step, fillet

        from cadgen._internal.fea.mesh import mesh_occurrence
        from cadgen.step_scene import read_scene

        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        plain, rounded = Box(60, 40, 10), fillet(Box(60, 40, 10).edges(), 0.3)
        meshes = []
        for name, shape in (("plain", plain), ("rounded", rounded)):
            export_step(shape, str(tmp / f"{name}.step"))
            occurrence = next(iter(read_scene(tmp / f"{name}.step").leaves()))
            meshes.append(mesh_occurrence(occurrence, max_h=15.0))
        cls.plain, cls.rounded = meshes

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_a_fillet_does_not_multiply_the_mesh(self):
        # netgen's own defaults made 187k tets of this 60 x 40 x 10 plate at 15 mm; _MESHING makes about 64k.
        self.assertLess(len(self.rounded.tets), 90_000)

    def test_the_feature_size_is_reported_only_when_it_sets_the_mesh(self):
        from cadgen._internal.fea.mesh import small_feature_mm

        self.assertIsNone(small_feature_mm(self.plain))
        size = small_feature_mm(self.rounded)
        self.assertIsNotNone(size)
        self.assertLess(size, 1.0)


def _vtu_von_mises(path: Path) -> "tuple[np.ndarray, np.ndarray]":
    """The VTU's corner-node positions (N, 3) and von Mises (N,)."""
    import numpy as np

    vtu = path.read_text(encoding="utf-8")

    def block(marker: str) -> np.ndarray:
        start = vtu.index(">", vtu.index(marker) + len(marker)) + 1
        return np.array(vtu[start:vtu.index("</DataArray>", start)].split(), dtype=float)

    return block("<Points><DataArray").reshape(-1, 3), block('Name="von_mises"')


@unittest.skipUnless(HAVE_FEA, "cadgen[fea] is not installed")
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

        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)

        def ends(step: Path) -> tuple[str, str]:
            planes = [f for f in fea.faces(step).faces if f.surface == "plane" and f.normal and abs(abs(f.normal[0]) - 1) < 1e-6]
            return min(planes, key=lambda f: f.center_mm[0]).ref, max(planes, key=lambda f: f.center_mm[0]).ref

        rod = tmp / "rod.step"
        export_step(Rot(0, 90, 0) * Cylinder(cls.ROD_RADIUS, cls.ROD_LENGTH, align=(Align.CENTER, Align.CENTER, Align.MIN)), str(rod))
        fixed, loaded = ends(rod)
        with quiet():
            cls.rod = fea.solve(rod, tmp / "rod.glb", vtu=True, study={
                "material": "steel",
                "fixtures": [{"faces": [fixed]}],
                "loads": [{"faces": [loaded], "type": "force", "vector_N": [0, 0, -cls.ROD_FORCE]}],
            })

        plate = tmp / "plate.step"
        body = Box(cls.PLATE_LENGTH, cls.PLATE_WIDTH, cls.PLATE_THICKNESS, align=(Align.MIN, Align.CENTER, Align.CENTER))
        export_step(body - Pos(cls.PLATE_LENGTH / 2, 0, 0) * Cylinder(cls.HOLE / 2, 2 * cls.PLATE_THICKNESS), str(plate))
        fixed, loaded = ends(plate)
        with quiet():
            cls.plate = fea.solve(plate, tmp / "plate.glb", study={
                "material": "steel",
                "fixtures": [{"faces": [fixed]}],
                "loads": [{"faces": [loaded], "type": "force", "vector_N": [cls.PULL, 0, 0]}],
            })

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_rod_is_meshed_at_the_default_size(self):
        self.assertIsNone(json.loads(self.rod.sidecar.read_text(encoding="utf-8"))["refined"])
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


@unittest.skipUnless(HAVE_FEA, "cadgen[fea] is not installed")
class FinerAtCurves(unittest.TestCase):
    """A part whose 0.5 mm fillets set its mesh: a smaller element size alone leaves it as it was."""

    @classmethod
    def setUpClass(cls):
        from build123d import Box, export_step, fillet

        from cadgen._internal.fea.mesh import mesh_occurrence
        from cadgen.step_scene import read_scene

        cls._tmp = tempfile.TemporaryDirectory()
        step = Path(cls._tmp.name) / "rounded.step"
        export_step(fillet(Box(30, 20, 6).edges(), 0.5), str(step))
        occurrence = next(iter(read_scene(step).leaves()))
        cls.first = len(mesh_occurrence(occurrence, max_h=8.0).tets)
        cls.halved = len(mesh_occurrence(occurrence, max_h=4.0).tets)
        cls.refined = len(mesh_occurrence(occurrence, max_h=4.0, refine=2.0).tets)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_halving_the_element_size_alone_barely_changes_a_fillet_governed_mesh(self):
        self.assertLess(self.halved, 1.3 * self.first)

    def test_refining_curved_features_by_the_same_ratio_makes_it_materially_finer(self):
        self.assertGreater(self.refined, 2.0 * self.first)


@unittest.skipUnless(HAVE_FEA, "cadgen[fea] is not installed")
class MultigridRetry(unittest.TestCase):
    """A multigrid attempt that diverges is stopped and tried again, not left to run to the iteration cap."""

    N = 21000  # past DIRECT_SOLVE_BELOW

    def _system(self):
        import numpy as np
        import scipy.sparse as sparse

        K = sparse.diags(np.linspace(1.0, 2.0, self.N)).tocsr()
        return K, np.ones(self.N), np.arange(self.N), np.zeros((self.N, 3)), np.arange(self.N) % 3

    def _fake(self, diverges: bool, K, f, starts: list):
        import numpy as np

        class Fake:
            def solve(self, rhs, tol, accel, maxiter, residuals, callback, x0=None):
                starts.append(x0)
                if diverges:
                    for _ in range(50):
                        callback(1e6 * np.ones(len(rhs)))
                    raise AssertionError("a diverging attempt must be stopped by the callback")
                residuals.extend([1.0, 1e-9])
                return rhs / K.diagonal()

        return Fake()

    def _run(self, diverging: list[bool]):
        from unittest import mock

        from cadgen._internal.fea.solve import _solve_system

        K, f, free, locations, component = self._system()
        self.starts: list = []
        fakes = iter(self._fake(d, K, f, self.starts) for d in diverging)
        warnings: list[str] = []
        with mock.patch("pyamg.smoothed_aggregation_solver", side_effect=lambda *a, **k: next(fakes)):
            _, how = _solve_system(K, f, free, locations, component, warnings)
        return how, warnings

    def test_a_diverging_attempt_is_retried(self):
        how, warnings = self._run([True, False])
        self.assertEqual(how, "amg+cg (2 iterations)")
        self.assertEqual(warnings, [])

    def test_a_retry_starts_from_another_guess_than_the_attempt_before(self):
        import numpy as np

        self._run([True, False])
        first, second = self.starts
        self.assertTrue(first is None or not np.any(first))
        self.assertTrue(np.any(second))

    def test_numpys_global_random_state_is_left_alone(self):
        import numpy as np

        np.random.seed(1234)
        before = np.random.get_state()[1].copy()
        self._run([True, False])
        self.assertTrue(np.array_equal(np.random.get_state()[1], before))

    def test_the_direct_solver_takes_over_when_every_attempt_fails(self):
        how, warnings = self._run([True, True, True])
        self.assertEqual(how, "superlu (after amg)")
        self.assertIn("did not converge in 3 attempts", warnings[0])


@unittest.skipUnless(HAVE_FEA, "cadgen[fea] is not installed")
class PartProjection(unittest.TestCase):
    """One part's von Mises field: the L2 projection over its own elements, zero on the rest."""

    def test_a_field_the_basis_holds_comes_back_on_the_parts_nodes_and_zero_elsewhere(self):
        import numpy as np
        from skfem import Basis, ElementTetP2, MeshTet

        from cadgen._internal.fea.solve import _project_on_elements

        mesh = MeshTet.init_tensor(np.linspace(0, 2, 5), np.linspace(0, 1, 3), np.linspace(0, 1, 3))
        scalar = Basis(mesh, ElementTetP2())
        rows = mesh.p[0, mesh.t].mean(axis=0) < 1.0
        x = np.asarray(scalar.interpolate(scalar.doflocs[0]))  # (elements, quadrature): x itself, quadratic-exact
        result = _project_on_elements(scalar, 1.0 + x, rows)
        own = np.unique(scalar.element_dofs[:, rows])
        np.testing.assert_allclose(result[own], 1.0 + scalar.doflocs[0, own], atol=1e-8)
        self.assertFalse(np.any(np.delete(result, own)))


class HumanLine(unittest.TestCase):
    def test_the_cli_line_floors_the_safety_factor_like_the_findings(self):
        from cadgen.results import FeaResult

        result = FeaResult(
            ok=True, document=Path("p.step"), occurrence="#o1", glb=Path("p.glb"), sidecar=Path("p.json"),
            summary={"safety_factor": 1.684}, mesh={},
        )
        self.assertIn("safety factor 1.6", result.human_lines()[1])
        self.assertNotIn("1.684", result.human_lines()[1])


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
