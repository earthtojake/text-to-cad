"""The analysis protocol: the registry, the shared element space and operators, study dispatch, static moved.

Registry and parse tests are stdlib only. The operator tests run on a small
box meshed in the test (skfem's structured tets, laid out the way netgen hands
a mesh over: 10-node tets, 6-node boundary triangles, faces by ordinal), so
they need the fea extra but no STEP and no mesher. The golden test writes a
cantilever STEP into a temporary directory and solves it twice.
"""

from __future__ import annotations

import io
import json
import struct
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.fea.analyses import ANALYSIS_NAMES, REGISTRY, get_analysis  # noqa: E402
from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

# Section 2 and 2.1 of the spec, in order.
TIER_1 = ("static", "modal", "buckling", "thermal", "thermal_transient", "thermal_stress", "harmonic",
          "random_vibration", "shock", "transient", "fatigue")
PLANNED = ("cfd_turbulent", "cfd_compressible", "creep", "composite", "bolt", "electromagnetic")
# Of section 2.1's names, those built since (registered in the same place, no longer planned).
BUILT_SINCE = ("cfd_turbulent", "cfd_compressible", "creep", "composite", "bolt", "electromagnetic")



def planned_entry(name: str):
    """A registry entry registered as planned whose module is not in this cadgen (every name of spec 2.1 is built)."""
    from unittest import mock

    from cadgen._internal.fea.analyses import Entry

    return mock.patch.dict(REGISTRY, {name: Entry(name, 3, f"cadgen._internal.fea.analyses.{name}", "Unbuilt", "Not built", True)})


# netgen's edge order of a 10-node tet, and of a 6-node triangle's mid-edge nodes.
_TET_EDGES = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
_TRIG_EDGES = ((1, 2), (0, 2), (0, 1))


def box_volume(lengths=(4.0, 1.0, 1.0), cells=(4, 1, 1)):
    """A box of 10-node tets as the mesher hands one over: faces 1-6 are x-, x+, y-, y+, z-, z+."""
    import numpy as np
    from skfem import MeshTet

    from cadgen._internal.fea.mesh import FaceFingerprint, VolumeMesh

    mesh = MeshTet.init_tensor(*(np.linspace(0.0, size, count + 1) for size, count in zip(lengths, cells)))
    points = list(mesh.p.T)
    middle: dict[tuple[int, int], int] = {}

    def mid(a: int, b: int) -> int:
        key = (min(a, b), max(a, b))
        if key not in middle:
            middle[key] = len(points)
            points.append(0.5 * (mesh.p[:, a] + mesh.p[:, b]))
        return middle[key]

    tets = [list(t) + [mid(t[a], t[b]) for a, b in _TET_EDGES] for t in mesh.t.T]
    facets = mesh.facets[:, mesh.boundary_facets()].T
    boundary = [list(f) + [mid(f[a], f[b]) for a, b in _TRIG_EDGES] for f in facets]
    nodes = np.array(points)
    centres = nodes[facets].mean(axis=1)
    ordinal = np.zeros(len(facets), dtype=np.int64)
    for axis in range(3):
        ordinal[np.isclose(centres[:, axis], 0.0)] = 2 * axis + 1
        ordinal[np.isclose(centres[:, axis], lengths[axis])] = 2 * axis + 2
    faces = {}
    for o in range(1, 7):
        axis, high = divmod(o - 1, 2)
        centre = [size / 2 for size in lengths]
        centre[axis] = lengths[axis] if high else 0.0
        area = float(np.prod([size for i, size in enumerate(lengths) if i != axis]))
        faces[o] = FaceFingerprint(f"#o1.f{o}", o, area, tuple(centre))
    diagonal = float(np.linalg.norm(lengths))
    return VolumeMesh(nodes=nodes, tets=np.array(tets, dtype=np.int64), boundary=np.array(boundary, dtype=np.int64),
                      boundary_ordinal=ordinal, faces=faces, max_h=max(lengths) / max(cells), bbox_diagonal=diagonal, seconds=0.0)


class Registry(unittest.TestCase):
    def test_every_analysis_is_registered_in_order(self):
        self.assertEqual(ANALYSIS_NAMES[:len(TIER_1)], TIER_1)
        self.assertEqual(ANALYSIS_NAMES[len(TIER_1):len(TIER_1) + 5], ("drop", "cfd", "impact", "nonlinear", "contact"))
        after = len(TIER_1) + 5
        self.assertEqual(ANALYSIS_NAMES[after:after + len(PLANNED)], PLANNED)
        # Built after spec 2.1's names, each registered after them: topology ("Lighten it") among them.
        self.assertIn("topology", ANALYSIS_NAMES[after + len(PLANNED):])
        self.assertEqual((REGISTRY["topology"].tier, REGISTRY["topology"].word, REGISTRY["topology"].planned), (3, "Lighten it", False))
        self.assertIn("acoustic", ANALYSIS_NAMES[after + len(PLANNED):])
        self.assertEqual((REGISTRY["acoustic"].tier, REGISTRY["acoustic"].word, REGISTRY["acoustic"].planned), (3, "Sound", False))
        self.assertIn("fracture", ANALYSIS_NAMES[after + len(PLANNED):])
        self.assertEqual((REGISTRY["fracture"].tier, REGISTRY["fracture"].word, REGISTRY["fracture"].planned), (3, "Cracks", False))
        self.assertIn("conjugate_heat", ANALYSIS_NAMES[after + len(PLANNED):])
        self.assertEqual((REGISTRY["conjugate_heat"].tier, REGISTRY["conjugate_heat"].word, REGISTRY["conjugate_heat"].planned),
                         (3, "Cooled by flow", False))
        self.assertIn("rotordynamics", ANALYSIS_NAMES[after + len(PLANNED):])
        self.assertEqual((REGISTRY["rotordynamics"].tier, REGISTRY["rotordynamics"].word, REGISTRY["rotordynamics"].planned),
                         (3, "Spinning", False))
        self.assertIn("fsi", ANALYSIS_NAMES[after + len(PLANNED):])
        self.assertEqual((REGISTRY["fsi"].tier, REGISTRY["fsi"].word, REGISTRY["fsi"].planned), (3, "Flow and bending", False))
        self.assertIn("piezo", ANALYSIS_NAMES[after + len(PLANNED):])
        self.assertEqual((REGISTRY["piezo"].tier, REGISTRY["piezo"].word, REGISTRY["piezo"].planned), (3, "Piezo", False))
        self.assertIn("multiphase", ANALYSIS_NAMES[after + len(PLANNED):])
        self.assertEqual((REGISTRY["multiphase"].tier, REGISTRY["multiphase"].word, REGISTRY["multiphase"].planned),
                         (3, "Two fluids", False))
        self.assertEqual([REGISTRY[name].tier for name in ("static", "drop", "cfd")], [1, 2, 3])
        self.assertEqual(REGISTRY["modal"].word, "Vibration")
        self.assertTrue(all(REGISTRY[name].planned != (name in BUILT_SINCE) for name in PLANNED))

    def test_an_unknown_name_lists_every_name(self):
        with self.assertRaises(ValueError) as caught:
            get_analysis("stress")
        self.assertIn("'stress' is not an analysis", str(caught.exception))
        self.assertIn("modal", str(caught.exception))

    def test_an_unbuilt_name_says_it_is_planned_never_an_import_error(self):
        # Every name of spec 2.1 is built now: a planned entry whose module is not in this cadgen stands in.
        for name in ("cfd_multiphase",):
            with self.subTest(name=name), self.assertRaises(ValueError) as caught, planned_entry(name):
                get_analysis(name)
            self.assertIn(f"'{name}' is planned but not in this cadgen yet; available: static", str(caught.exception))

    def test_static_is_built_and_stdlib_only_at_import(self):
        import subprocess
        import sys

        static = get_analysis("static")
        self.assertEqual((static.name, static.tier, static.word), ("static", 1, "Strength"))
        self.assertIs(get_analysis("static"), static)
        code = (
            "import sys; sys.path.insert(0, 'packages/cadgen/src');"
            "import cadgen._internal.fea.analyses.static, cadgen._internal.fea.analyses.kinds;"
            "heavy = sorted(m for m in ('numpy', 'scipy', 'skfem', 'OCP', 'netgen') if m in sys.modules);"
            "print(','.join(heavy))"
        )
        root = Path(__file__).resolve().parents[4]
        heavy = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(heavy, "")


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Operators(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cadgen._internal.fea.femspace import FemSpace
        from cadgen._internal.fea.materials import lookup_material

        cls.volume = box_volume()
        cls.space = FemSpace.build(cls.volume)
        cls.steel = lookup_material("steel")

    def test_the_space_maps_the_meshers_faces(self):
        import numpy as np

        self.assertEqual(self.space.boundary_quadratic.shape, (len(self.volume.boundary), 6))
        facets = self.space.facets_of(["#o1.f2"], {"#o1.f2": 2})
        self.assertTrue(np.allclose(self.space.mesh.p[0, self.space.mesh.facets[:, facets]], 4.0))

    def test_mass_sums_to_density_times_volume(self):
        import numpy as np

        from cadgen._internal.fea import operators

        M = operators.mass(self.space, self.steel)
        x = (self.space.component == 0).astype(float)
        self.assertAlmostEqual(float(x @ (M @ x)) / (self.steel.density * 4.0), 1.0, places=10)
        lumped = operators.mass(self.space, self.steel, lumped=True)
        self.assertAlmostEqual(float(lumped.diagonal()[self.space.component == 2].sum()) / (self.steel.density * 4.0), 1.0, places=10)
        f = operators.body_force(self.space, self.steel, (0.0, 0.0, -operators.G0_MM_S2))
        self.assertAlmostEqual(float(f[self.space.component == 2].sum()) / (-self.steel.density * 4.0 * operators.G0_MM_S2), 1.0, places=10)
        self.assertAlmostEqual(float(np.abs(f[self.space.component != 2]).sum()), 0.0, places=12)

    def test_the_geometric_stiffness_is_symmetric(self):
        import numpy as np

        from cadgen._internal.fea import operators

        rng = np.random.default_rng(3)
        u = rng.standard_normal(self.space.dofs)
        sigma = operators.stress(self.space, self.steel, u)
        Kg = operators.geometric_stiffness(self.space, sigma)
        self.assertLess(abs(Kg - Kg.T).max(), 1e-9 * abs(Kg).max())

    def test_the_matrix_free_product_is_the_assembled_one(self):
        import numpy as np

        from cadgen._internal.fea import operators

        K = operators.stiffness(self.space, self.steel)
        x = np.random.default_rng(1).standard_normal(self.space.dofs)
        for chunk in (5, 1000):
            with self.subTest(chunk=chunk):
                y = operators.ElementChunkOperator(self.space, self.steel, chunk=chunk) @ x
                self.assertLess(np.abs(y - K @ x).max(), 1e-12 * np.abs(K @ x).max())
        diagonal = operators.ElementChunkOperator(self.space, self.steel, chunk=7).diagonal()
        self.assertLess(np.abs(diagonal - K.diagonal()).max(), 1e-12 * K.diagonal().max())

    def test_a_free_thermal_strain_moves_without_stress(self):
        import numpy as np

        from cadgen._internal.fea import operators
        from cadgen._internal.fea.solve import solve_linear_static
        from cadgen._internal.fea.study import Fixture

        # A bar held on its x- face only in x (here: clamped) and heated 10 K grows α ΔT L at the far end.
        alpha, rise = 11.7e-6, 10.0
        strain = np.full(self.space.basis.dx.shape, alpha * rise)
        outcome = solve_linear_static(self.volume, self.steel, (Fixture(("#o1.f1",)),), (), {"#o1.f1": 1},
                                      initial_strain=strain, space=self.space)
        far = np.isclose(outcome.dof_locations[:, 0], 4.0)
        self.assertAlmostEqual(float(outcome.displacement[far, 0].mean()) / (alpha * rise * 4.0), 1.0, delta=0.05)
        self.assertLess(abs(sum(outcome.applied)), 1e-9)
        self.assertIsNotNone(operators)

    def test_the_solver_choices_agree(self):
        import numpy as np

        from cadgen._internal.fea.solve import solve_linear_static
        from cadgen._internal.fea.study import Fixture, Load

        study = ((Fixture(("#o1.f1",)),), (Load(("#o1.f2",), "force", vector=(0.0, 0.0, -10.0)),), {"#o1.f1": 1, "#o1.f2": 2})
        direct = solve_linear_static(self.volume, self.steel, *study, solver="direct")
        matrix_free = solve_linear_static(self.volume, self.steel, *study, solver="matrix_free", space=self.space)
        self.assertTrue(matrix_free.solver.startswith("matrix-free cg"))
        np.testing.assert_allclose(matrix_free.displacement, direct.displacement, atol=1e-6 * np.abs(direct.displacement).max())
        for a, r in zip(direct.applied, np.sum(direct.reactions, axis=0)):
            self.assertAlmostEqual(a + r, 0.0, delta=1e-6)

    def test_gravity_counts_in_the_applied_load_so_reactions_balance(self):
        import numpy as np

        from cadgen._internal.fea import operators
        from cadgen._internal.fea.solve import solve_linear_static
        from cadgen._internal.fea.study import Fixture

        outcome = solve_linear_static(self.volume, self.steel, (Fixture(("#o1.f1",)),), (), {"#o1.f1": 1},
                                      body_loads=[(0.0, 0.0, -operators.G0_MM_S2)], space=self.space)
        weight = self.steel.density * 4.0 * operators.G0_MM_S2
        self.assertAlmostEqual(outcome.applied[2] / -weight, 1.0, places=9)
        self.assertAlmostEqual(outcome.reactions[0][2] / weight, 1.0, places=6)
        self.assertGreater(np.abs(outcome.displacement[:, 2]).max(), 0.0)

    def test_a_facet_pressure_is_a_pressure_load(self):
        import numpy as np

        from cadgen._internal.fea.solve import solve_linear_static
        from cadgen._internal.fea.study import Fixture, Load

        ordinal_of = {"#o1.f1": 1, "#o1.f6": 6}
        uniform = solve_linear_static(self.volume, self.steel, (Fixture(("#o1.f1",)),),
                                      (Load(("#o1.f6",), "pressure", pressure=0.2),), ordinal_of, space=self.space)
        per_facet = np.where(self.volume.boundary_ordinal == 6, 0.2, 0.0)
        mapped = solve_linear_static(self.volume, self.steel, (Fixture(("#o1.f1",)),), (), ordinal_of,
                                     facet_pressures=per_facet, space=self.space)
        np.testing.assert_allclose(mapped.displacement, uniform.displacement, atol=1e-12)


BASE = {"material": "steel", "fixtures": [{"faces": ["#o1.f1"]}], "loads": [{"faces": ["#o1.f2"], "type": "force", "vector_N": [1, 0, 0]}]}


class StudyDispatch(unittest.TestCase):
    """The ``analysis`` key and the common keys: stdlib only, before any heavy import."""

    def test_no_analysis_is_static_and_says_the_same(self):
        from cadgen._internal.fea.study import CHECK_KINDS, VIEW_FIELDS, parse_study

        bare, named = parse_study(BASE), parse_study({**BASE, "analysis": "static"})
        self.assertEqual((bare.analysis, named.analysis), ("static", "static"))
        self.assertEqual((bare.fixtures, bare.loads, bare.inputs), (named.fixtures, named.loads, named.inputs))
        self.assertEqual(bare.inputs.anchor_refs, ("#o1.f1",))
        self.assertTrue(bare.inputs.requires_anchor)
        self.assertIsNone(bare.fit)
        self.assertEqual((CHECK_KINDS, VIEW_FIELDS), (("stress", "displacement"), ("von_mises", "displacement")))

    def test_an_unknown_or_planned_analysis_is_a_plain_error(self):
        from cadgen._internal.fea.study import parse_study

        for name, fragment in (("vibration", "is not an analysis cadgen knows"), ("cfd_multiphase", "planned but not in this cadgen yet"),
                               (3, "expected the analysis's name")):
            with self.subTest(name=name), self.assertRaises(ValueError) as caught, planned_entry("cfd_multiphase"):
                parse_study({**BASE, "analysis": name})
            self.assertIn(fragment, str(caught.exception))

    def test_unknown_keys_name_the_analysis_and_what_it_takes(self):
        from cadgen._internal.fea.study import parse_study

        with self.assertRaises(ValueError) as caught:
            parse_study({**BASE, "modes": 6})
        self.assertIn("unknown keys ['modes']; static studies take analysis, material, fixtures, loads", str(caught.exception))

    def test_a_check_static_does_not_make_is_refused(self):
        from cadgen._internal.fea.study import parse_study

        with self.assertRaises(ValueError) as caught:
            parse_study({**BASE, "view": {"checks": [{"kind": "frequency", "min_Hz": 60}]}})
        self.assertIn("is not a check this cadgen makes; use one of ['stress', 'displacement']", str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            parse_study({**BASE, "view": {"controls": [{"drives": "mode"}]}})
        self.assertIn("'mode' is not one of ['field', 'deformation', 'load_scale', 'threshold']", str(caught.exception))

    def test_static_refuses_linear_elements_as_before(self):
        from cadgen._internal.fea.study import parse_study

        with self.assertRaises(ValueError) as caught:
            parse_study({**BASE, "mesh": {"order": 1}})
        self.assertIn("only quadratic (order 2) elements are supported", str(caught.exception))

    def test_fit_parses_and_never_refuses_a_model(self):
        from cadgen._internal.fea.study import parse_study

        study = parse_study({**BASE, "fit": {"memory_GB": 8, "seconds": 600, "allow": ["iterative", "local_refine"]}})
        self.assertEqual(study.fit, {"memory_GB": 8.0, "seconds": 600.0, "allow": ["iterative", "local_refine"]})
        self.assertEqual(parse_study({**BASE, "fit": {"allow": []}}).fit, {"allow": []})
        for fit, fragment in (({"memory_GB": 0}, "fit.memory_GB: must be > 0"), ({"allow": ["shrink"]}, "fit.allow[0]: \"shrink\" is not one of"),
                              ({"budget": 1}, "fit: unknown keys ['budget']"), ({"allow": "iterative"}, "fit.allow: list")):
            with self.subTest(fragment=fragment), self.assertRaises(ValueError) as caught:
                parse_study({**BASE, "fit": fit})
            self.assertIn(fragment, str(caught.exception))

    def test_body_loads_have_no_faces_and_need_a_density(self):
        from cadgen._internal.fea.study import parse_study

        study = parse_study({**BASE, "loads": [{"type": "gravity", "vector_g": [0, 0, -1]}, {"type": "acceleration", "vector_g": [5, 0, 0]}]})
        self.assertEqual([load.type for load in study.body_loads], ["gravity", "acceleration"])
        self.assertEqual(study.surface_loads, ())
        self.assertEqual(study.face_refs, ("#o1.f1",))
        self.assertEqual(study.inputs.body_accelerations, [(0.0, 0.0, -9806.65), (-5 * 9806.65, -0.0, -0.0)])
        cases = [
            ({"loads": [{"type": "gravity"}]}, "loads[0].vector_g: gravity as [x, y, z] in g"),
            ({"loads": [{"type": "gravity", "vector_g": [0, 0, 0]}]}, "loads[0].vector_g: the gravity is zero"),
            ({"loads": [{"type": "gravity", "vector_g": [0, 0, -1], "faces": ["#o1.f2"]}]}, "acts on the whole part"),
            ({"material": {"E_MPa": 1000, "nu": 0.3, "yield_MPa": 10}, "loads": [{"type": "acceleration", "vector_g": [1, 0, 0]}]},
             "static studies need the density"),
        ]
        for change, fragment in cases:
            with self.subTest(fragment=fragment), self.assertRaises(ValueError) as caught:
                parse_study({**BASE, **change})
            self.assertIn(fragment, str(caught.exception))


class CheckKinds(unittest.TestCase):
    def test_every_kind_parses_its_own_keys(self):
        from cadgen._internal.fea.analyses.kinds import CHECK_SPECS

        self.assertEqual(list(CHECK_SPECS), ["stress", "displacement", "frequency", "buckling", "temperature", "acceleration",
                                             "fatigue", "pressure_drop", "velocity", "plastic_strain", "contact_pressure",
                                             "creep_strain", "ply_failure", "electric_field", "bolt_load", "joint_separation",
                                             "joint_slip", "mach", "sound_level", "mass_saved", "fracture",
                                             "crack_life", "voltage", "critical_speed", "stability",
                                             "fill_level", "wall_pressure"])
        parse = {kind: spec.parse for kind, spec in CHECK_SPECS.items()}
        self.assertEqual(parse["frequency"]({"kind": "frequency", "min_Hz": 60, "mode": 2}, "c"), {"kind": "frequency", "min_Hz": 60.0, "mode": 2})
        self.assertEqual(parse["frequency"]({"kind": "frequency", "avoid_Hz": [110, 130]}, "c")["avoid_Hz"], [110.0, 130.0])
        self.assertEqual(parse["buckling"]({"kind": "buckling"}, "c"), {"kind": "buckling", "margin": 3.0})
        self.assertEqual(parse["fatigue"]({"kind": "fatigue", "cycles": 1e6}, "c"), {"kind": "fatigue", "cycles": 1e6, "margin": 1.5})
        self.assertEqual(parse["temperature"]({"kind": "temperature", "max_C": 85, "faces": ["#o1.f7"], "label": "Chip"}, "c"),
                         {"kind": "temperature", "max_C": 85.0, "faces": ["#o1.f7"], "label": "Chip"})
        self.assertEqual(CHECK_SPECS["buckling"].scaling, "inverse")
        self.assertEqual(CHECK_SPECS["frequency"].default_label, "Vibration")

    def test_the_errors_name_the_field(self):
        from cadgen._internal.fea.analyses.kinds import CHECK_SPECS

        cases = [
            ("frequency", {"kind": "frequency", "min_Hz": 60, "avoid_Hz": [1, 2]}, "exactly one"),
            ("frequency", {"kind": "frequency", "avoid_Hz": [130, 110]}, "c.avoid_Hz: low (130) must be below high (110)"),
            ("frequency", {"kind": "frequency", "avoid_Hz": [1, 2], "mode": 1}, "c.mode: a band check looks at every mode"),
            ("buckling", {"kind": "buckling", "margin": 0.5}, "c.margin: a buckling margin below 1"),
            ("temperature", {"kind": "temperature"}, "c.max_C"),
            ("acceleration", {"kind": "acceleration", "limit_g": -1}, "c.limit_g: must be > 0"),
            ("velocity", {"kind": "velocity", "limit_Pa": 1}, "c: unknown keys ['limit_Pa']; a velocity check takes"),
        ]
        for kind, entry, fragment in cases:
            with self.subTest(fragment=fragment), self.assertRaises(ValueError) as caught:
                CHECK_SPECS[kind].parse(entry, "c")
            self.assertIn(fragment, str(caught.exception))

    @unittest.skipUnless(HAVE_FEA, "numpy comes with the fea extra")
    def test_field_max_over_takes_the_faces_nodes_or_every_node(self):
        import numpy as np

        from cadgen._internal.fea.analyses.kinds import field_max_over
        from cadgen._internal.fea.mesh import FaceFingerprint

        boundary = np.array([[0, 1, 2], [2, 3, 4]])
        faces = {1: FaceFingerprint("#o1.f1", 1, 1.0, (0, 0, 0)), 2: FaceFingerprint("#o1.f2", 2, 1.0, (0, 0, 0))}
        values = np.array([0.0, 1.0, 2.0, 5.0, 3.0, 9.0])
        common = dict(boundary=boundary, boundary_ordinal=np.array([1, 2]), locations=np.arange(18.0).reshape(6, 3),
                      face_ref=faces, ordinal_of={"a": 1, "b": 2}, where="view.checks[1]")
        on_one = field_max_over(values, ("a",), **common)
        self.assertEqual((on_one.node, on_one.value, on_one.ref, on_one.faces, on_one.at), (2, 2.0, "#o1.f1", ("#o1.f1",), (6.0, 7.0, 8.0)))
        self.assertEqual(field_max_over(values, (), **common).node, 5)
        self.assertIsNone(field_max_over(values, (), **common).ref)


def _glb_parts(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    json_length, _ = struct.unpack_from("<II", raw, 12)
    return json.loads(raw[20:20 + json_length]), raw[20 + json_length + 8:]


class CliLines(unittest.TestCase):
    def _result(self, **changes):
        from cadgen.results import FeaResult

        fields = {"summary": {"safety_factor": 2.5}, "mesh": {"elements": 10}, **changes}
        return FeaResult(ok=True, document=Path("p.step"), occurrence="#o1", glb=Path("p.glb"), sidecar=Path("p.json"), **fields)

    def test_static_lines_are_todays_plus_one_line_per_fit_step(self):
        plain = self._result().human_lines()
        step = {"rung": "iterative", "words": "Used an iterative solver to fit in memory", "accuracy": None}
        adapted = self._result(fit=(step,)).human_lines()
        self.assertEqual([line for line in adapted if line not in plain], ["adapted: Used an iterative solver to fit in memory"])

    def test_another_analysis_writes_its_own_lines(self):
        from unittest import mock

        from cadgen._internal.fea import analyses

        class Vibration:
            def human_lines(self, summary):
                return [f"first mode {summary['f1']} Hz"]

        with mock.patch.dict(analyses._INSTANCES, {"modal": Vibration()}):
            lines = self._result(analysis="modal", summary={"f1": 85.0, "checks": []}).human_lines()
        self.assertIn("(modal)", lines[0])
        self.assertEqual(lines[1], "first mode 85.0 Hz")
        self.assertFalse(any("safety factor" in line for line in lines))

    def test_a_unitless_check_reads_with_single_spaces(self):
        check = {"label": "Fatigue life", "value": 1.317, "limit": 1.5, "unit": "", "ratio": 0.759, "status": "close"}
        stress = {"label": "Strength", "value": 77.1, "limit": 250.0, "unit": "MPa", "ratio": 0.31, "status": "passes"}
        lines = self._result(summary={"safety_factor": 2.5, "checks": [check, stress]}).human_lines()
        self.assertIn("check 'Fatigue life': 1.317 against a 1.5 limit, 0.76× it, close", lines)
        self.assertIn("check 'Strength': 77.1 MPa against a 250 MPa limit, 0.31× it, passes", lines)


def _cantilever(directory: Path) -> Path:
    from build123d import Align, Box, export_step

    path = directory / "cantilever.step"
    export_step(Box(40.0, 4.0, 4.0, align=(Align.MIN, Align.CENTER, Align.CENTER)), str(path))
    return path


def _end_faces(listing) -> tuple[str, str]:
    by_x = {face.center_mm[0]: face.ref for face in listing.faces
            if face.surface == "plane" and face.normal is not None and abs(abs(face.normal[0]) - 1) < 1e-6}
    return by_x[min(by_x)], by_x[max(by_x)]


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class MeshOptions(unittest.TestCase):
    """mesh.py's ``order`` and ``size_field``: linear tets end to end, and local sizes that refine."""

    @classmethod
    def setUpClass(cls):
        from cadgen import fea
        from cadgen.step_scene import read_scene

        cls._tmp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls._tmp.name)
        cls.step = _cantilever(cls.directory)
        cls.fixed, cls.loaded = _end_faces(fea.faces(cls.step))
        cls.occurrence = next(iter(read_scene(cls.step).leaves()))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_linear_elements_mesh_solve_and_write(self):
        import numpy as np

        from cadgen._internal.fea.femspace import FemSpace
        from cadgen._internal.fea.materials import lookup_material
        from cadgen._internal.fea.mesh import mesh_occurrence
        from cadgen._internal.fea.outputs import write_glb
        from cadgen._internal.fea.solve import solve_linear_static
        from cadgen._internal.fea.study import Fixture, Load

        volume = mesh_occurrence(self.occurrence, max_h=2.0, order=1)
        self.assertEqual((volume.tets.shape[1], volume.boundary.shape[1]), (4, 3))
        space = FemSpace.build(volume, order=1)
        ordinal_of = {self.fixed: int(self.fixed.rsplit("f", 1)[1]), self.loaded: int(self.loaded.rsplit("f", 1)[1])}
        outcome = solve_linear_static(volume, lookup_material("steel"), (Fixture((self.fixed,)),),
                                      (Load((self.loaded,), "force", vector=(0.0, 0.0, -20.0)),), ordinal_of, space=space)
        self.assertEqual(outcome.boundary_quadratic.shape[1], 3)
        self.assertAlmostEqual(outcome.applied[2] + sum(r[2] for r in outcome.reactions), 0.0, delta=1e-6)
        path = self.directory / "linear.glb"
        write_glb(path, positions=outcome.dof_locations, displacement=outcome.displacement, values=outcome.von_mises,
                  triangles6=outcome.boundary_quadratic, face_of_triangle=np.zeros(len(volume.boundary), dtype=np.int64),
                  scale=1.0, value_range=(0.0, float(outcome.von_mises.max())), extras={"faces": ["#o1.f1"]},
                  extra_attributes={"_TEMPERATURE": outcome.von_mises, "_HEAT_FLUX": outcome.displacement})
        gltf, _ = _glb_parts(path)
        primitive = gltf["meshes"][0]["primitives"][0]
        self.assertEqual(gltf["accessors"][primitive["indices"]]["count"], 3 * len(volume.boundary))
        self.assertEqual(list(primitive["attributes"])[-2:], ["_TEMPERATURE", "_HEAT_FLUX"])
        self.assertEqual(gltf["accessors"][primitive["attributes"]["_HEAT_FLUX"]]["type"], "VEC3")

    def test_a_size_field_refines_where_it_says(self):
        import numpy as np

        from cadgen._internal.fea.mesh import mesh_occurrence

        plain = mesh_occurrence(self.occurrence, max_h=2.0)
        ordinal = int(self.loaded.rsplit("f", 1)[1])
        by_face = mesh_occurrence(self.occurrence, max_h=2.0, size_field={"faces": {ordinal: 0.5}})
        by_point = mesh_occurrence(self.occurrence, max_h=2.0, size_field={"points": [[20.0, 0.0, 0.0, 0.5]], "radius_mm": 1.0})
        for refined in (by_face, by_point):
            self.assertGreater(len(refined.tets), 1.5 * len(plain.tets))
        # The fine face's triangles are small; the far end's keep the global size.
        def mean_edge(volume, face):
            corners = volume.nodes[volume.boundary[volume.boundary_ordinal == face][:, :3]]
            return float(np.linalg.norm(corners[:, 1] - corners[:, 0], axis=1).mean())
        self.assertLess(mean_edge(by_face, ordinal), 0.8)
        self.assertGreater(mean_edge(by_face, int(self.fixed.rsplit("f", 1)[1])), 1.2)


class SkillDocs(unittest.TestCase):
    """The skill says what the registry says: every built analysis runs today, in both of its tables."""

    def _rows(self, path: Path, heading: str) -> list[list[str]]:
        import re

        text = path.read_text(encoding="utf-8")
        section = text.split(heading, 1)[1]
        section = re.split(r"\n#{2,3} ", section, maxsplit=1)[0]
        lines = [line for line in section.splitlines() if line.startswith("|") and "---" not in line]
        return [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines[1:]]  # past the header

    def test_every_built_analysis_has_a_runs_today_row_and_a_status_cell(self):
        import re

        skill = Path(__file__).resolve().parents[4] / "skills" / "fea"
        built = [name for name, entry in REGISTRY.items() if not entry.planned]
        planned = [name for name, entry in REGISTRY.items() if entry.planned]

        # SKILL.md's "Choose the analysis": the analysis is the first `name` of its second column.
        status_of: dict[str, list[str]] = {}
        for cells in self._rows(skill / "SKILL.md", "## Choose the analysis"):
            if len(cells) < 5:
                continue
            found = re.match(r"`([a-z_]+)`", cells[1])
            if found:
                status_of.setdefault(found.group(1), []).append(cells[3])
        for name in built:
            with self.subTest(table="SKILL.md", analysis=name):
                self.assertIn(name, status_of, f"{name} has no row in SKILL.md's Choose the analysis table")
                self.assertTrue(all(status.startswith("**Runs today**") for status in status_of[name]), status_of[name])
        self.assertEqual(sorted(set(status_of) - set(REGISTRY)), [])
        for name in planned:
            self.assertFalse(any("Runs today" in status for status in status_of.get(name, [])), name)

        # study-file.md's `analysis` table: one row per registered name, its word and its status.
        table = {}
        for cells in self._rows(skill / "references" / "study-file.md", "## `analysis`"):
            found = re.fullmatch(r"`([a-z_]+)`", cells[0])
            if found and len(cells) >= 4:
                table[found.group(1)] = (cells[1], cells[2])
        self.assertEqual(sorted(table), sorted(REGISTRY))
        for name, (word, status) in table.items():
            with self.subTest(table="study-file.md", analysis=name):
                self.assertEqual(word, REGISTRY[name].word)
                self.assertTrue(status.startswith("planned" if REGISTRY[name].planned else "runs today"), status)
        # Nothing says an analysis is only coming or that static alone runs.
        for path in (skill / "SKILL.md", skill / "references" / "study-file.md", skill / "references" / "planned-next.md"):
            text = path.read_text(encoding="utf-8")
            for stale in ("coming, not in this cadgen", "Only `static` runs", "the only one that runs today", "is planned, and"):
                self.assertNotIn(stale, text, f"{path.name} still says {stale!r}")


class PrivateNames(unittest.TestCase):
    """No fea module reaches into another's private names: each shares what others use under a public name."""

    def test_no_module_imports_or_reads_another_modules_private_name(self):
        import ast

        root = Path(__file__).resolve().parents[4] / "packages" / "cadgen" / "src" / "cadgen" / "_internal" / "fea"
        found = []
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            own = "cadgen._internal." + ".".join(path.relative_to(root.parent).with_suffix("").parts)
            modules = {}  # a name bound to a cadgen module in this file -> that module
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("cadgen"):
                    for alias in node.names:
                        if alias.name.startswith("_") and not alias.name.startswith("__") and node.module != own:
                            found.append(f"{path.name}:{node.lineno} from {node.module} import {alias.name}")
                        modules[alias.asname or alias.name] = f"{node.module}.{alias.name}"
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("cadgen"):
                            modules[alias.asname or alias.name.split(".")[0]] = alias.name
            for node in ast.walk(tree):
                if (isinstance(node, ast.Attribute) and node.attr.startswith("_") and not node.attr.startswith("__")
                        and isinstance(node.value, ast.Name) and node.value.id in modules):
                    found.append(f"{path.name}:{node.lineno} {node.value.id}.{node.attr}")
        self.assertEqual(found, [])


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Golden(unittest.TestCase):
    """Static moved, not rewritten: a study with and without ``"analysis": "static"`` writes the same GLB, byte for byte."""

    def test_naming_static_changes_no_byte(self):
        from cadgen import fea

        with tempfile.TemporaryDirectory() as tmp, redirect_stderr(io.StringIO()):
            directory = Path(tmp)
            step = _cantilever(directory)
            fixed, loaded = _end_faces(fea.faces(step))
            study = {"material": "steel", "fixtures": [{"faces": [fixed]}], "mesh": {"size_mm": 2.0},
                     "loads": [{"faces": [loaded], "type": "force", "vector_N": [0, 0, -20]}],
                     "view": {"checks": [{"kind": "stress"}, {"kind": "displacement", "limit_mm": 1, "faces": [loaded]}]}}
            bare = fea.solve(step, directory / "bare.glb", study=study)
            named = fea.solve(step, directory / "named.glb", study={"analysis": "static", **study})
            self.assertEqual(bare.glb.read_bytes(), named.glb.read_bytes())
            gltf, _ = _glb_parts(named.glb)
            extras = gltf["meshes"][0]["extras"]
            self.assertNotIn("analysis", extras)
            self.assertEqual([f["attribute"] for f in extras["fields"]], ["_VON_MISES", "_DISPLACEMENT"])
            self.assertEqual(set(extras["fields"][0]), {"attribute", "name", "units", "min", "max", "attribute_scale"})
            first, second = (json.loads(r.sidecar.read_text(encoding="utf-8")) for r in (bare, named))
            for sidecar in (first, second):
                sidecar.pop("study")
                sidecar.pop("timings")
                sidecar["files"].pop("glb")
            self.assertEqual(first, second)
            self.assertNotIn("analysis", second)
            self.assertEqual(named.analysis, "static")


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class WrittenAttributes(unittest.TestCase):
    """What run.py writes beyond static: a study that names no face, and each field under its own attribute only."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls._tmp.name)
        cls.step = _cantilever(cls.directory)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_static_writes_von_mises_beside_displacement_as_before(self):
        from cadgen import fea

        fixed, loaded = _end_faces(fea.faces(self.step))
        study = {"material": "steel", "fixtures": [{"faces": [fixed]}], "mesh": {"size_mm": 4.0},
                 "loads": [{"faces": [loaded], "type": "force", "vector_N": [0, 0, -20]}]}
        with redirect_stderr(io.StringIO()):
            result = fea.solve(self.step, self.directory / "static.glb", study=study)
        gltf, _ = _glb_parts(result.glb)
        self.assertEqual(list(gltf["meshes"][0]["primitives"][0]["attributes"]),
                         ["POSITION", "NORMAL", "COLOR_0", "_VON_MISES", "_DISPLACEMENT", "_FACE"])

    def test_a_free_free_modal_study_names_no_face_and_solves_end_to_end(self):
        from cadgen import fea

        with redirect_stderr(io.StringIO()):
            result = fea.solve(self.step, self.directory / "free.glb",
                               study={"analysis": "modal", "material": "steel", "modes": 2, "mesh": {"size_mm": 4.0}})
        self.assertTrue(result.ok)
        self.assertEqual((result.analysis, result.occurrence), ("modal", "#o1"))
        self.assertEqual(result.summary["rigid_body_modes"], 6)
        self.assertEqual(len(result.summary["modes"]), 2)
        gltf, _ = _glb_parts(result.glb)
        attributes = gltf["meshes"][0]["primitives"][0]["attributes"]
        # The mode shape is a vector: the surface is coloured by its magnitude, and no stress copy rides along.
        self.assertNotIn("_VON_MISES", attributes)
        self.assertEqual(gltf["accessors"][attributes["_DISPLACEMENT"]]["type"], "VEC3")
        self.assertIn("COLOR_0", attributes)
        listed = [entry["attribute"] for entry in gltf["meshes"][0]["extras"]["fields"]]
        self.assertEqual(listed, ["_DISPLACEMENT"])
        self.assertTrue(set(listed) <= set(attributes))


if __name__ == "__main__":
    unittest.main()
