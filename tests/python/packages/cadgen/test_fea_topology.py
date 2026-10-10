"""Topology optimisation ("Lighten it"): the study, the numerics, and two classic benchmarks end to end.

The benchmarks are thin steel slabs (2 mm thick, so they behave like the 2D textbook problems) written to
STEP in a temporary directory: the MBB beam (simply held at its two bottom corners, pushed down at the top
middle, 50 % of the material) and a cantilever (held on its left face, pushed down at the middle of its
right face, 40 %). Each asserts what the method promises: the final volume is the target within 1 %, the
compliance only falls once the continuation has finished, the design is symmetric when the problem is, the
optimum is stiffer than a uniform grey part of the same mass, and no stiffer than the solid part. There is
no published compliance for a 3D linear-tet slab to compare with (Sigmund's 99-line code reports its
designs on 2D bilinear quads), so the optimum is measured against the fine solid baseline instead, and the
numerical core is checked for discretisation independence on a structured mesh (a coarse and a twice-finer
design within 5 %), its gradient against finite differences, and its filter and surface against exact
answers. A ladder test forces symmetry and a coarser design mesh with a tiny time target.
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

from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402
from cadgen._internal.fea.study import parse_study  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

STUDY = {
    "analysis": "topology", "material": "steel", "fixtures": [{"faces": ["#o1.f1"]}],
    "loads": [{"faces": ["#o1.f2"], "type": "force", "vector_N": [0, -100, 0]}],
}


def _study(**changes) -> dict:
    return {**STUDY, **changes}


class Parse(unittest.TestCase):
    """Stdlib: the study's keys, their defaults and the errors that name the field."""

    def test_defaults(self):
        parsed = parse_study(_study())
        inputs = parsed.inputs
        self.assertEqual((inputs.objective, inputs.volume_fraction, inputs.penalty, inputs.iterations), ("stiffest", 0.3, 3.0, 150))
        self.assertEqual(parsed.mesh_order, 1)
        self.assertEqual([c["kind"] for c in parsed.checks], ["mass_saved", "stress"])
        self.assertEqual(inputs.face_refs, ("#o1.f1", "#o1.f2"))
        self.assertEqual(parse_study(_study(objective="lightest")).inputs.volume_fraction, 0.5)

    def test_keys(self):
        inputs = parse_study(_study(volume_fraction=0.25, keep=["#o1.f7"], min_member_mm=4, penalty=3.5,
                                    symmetry=["x", {"axis": "z", "at_mm": 1}], extrusion="z", iterations=60)).inputs
        self.assertEqual(inputs.keep, ("#o1.f7",))
        self.assertIn("#o1.f7", inputs.face_refs)
        self.assertEqual(inputs.symmetry, (("x", None), ("z", 1.0)))
        self.assertEqual(inputs.extrusion, (0.0, 0.0, 1.0))
        self.assertEqual(parse_study(_study(extrusion={"direction": [0, 3, 4]})).inputs.extrusion, (0.0, 0.6, 0.8))
        cases = parse_study({k: v for k, v in _study(load_cases=[
            {"name": "lift", "loads": [{"faces": ["#o1.f2"], "type": "force", "vector_N": [0, 10, 0]}]},
            {"loads": [{"faces": ["#o1.f3"], "type": "pressure", "pressure_MPa": 1}]},
        ]).items() if k != "loads"}).inputs.cases
        self.assertEqual([name for name, _ in cases], ["lift", "case 2"])
        self.assertEqual(parse_study(_study(fit={"allow": ["coarse_design", "symmetry"]})).fit["allow"], ["coarse_design", "symmetry"])

    def test_errors_name_the_field(self):
        gravity = [{"type": "gravity", "vector_g": [0, 0, -1]}]
        cases = [
            (_study(volume_fraction=1.2), "volume_fraction: the share of the part's material to keep"),
            (_study(objective="cheapest"), "objective: \"cheapest\" is not one of"),
            (_study(penalty=9), "penalty: SIMP's exponent"),
            (_study(symmetry=["w"]), "symmetry[0]: a plane"),
            (_study(symmetry=["x", "x"]), "symmetry: name each axis once"),
            (_study(extrusion=[0, 0, 1]), "extrusion: the direction"),
            (_study(iterations=5), "iterations: the most optimisation iterations"),
            (_study(load_cases=[]), "give 'loads' (one load case) or 'load_cases'"),
            (_study(loads=gravity), "loads[0].type: 'gravity' is not one of"),
            (_study(mesh={"order": 2}), "study.mesh.order: topology studies take order 1"),
            (_study(objective="lightest", view={"checks": [{"kind": "mass_saved"}]}), "a lightest study needs a limit"),
            (_study(view={"checks": [{"kind": "mass_saved", "min_percent": 120}]}), "min_percent: the share of the mass to save"),
        ]
        for document, fragment in cases:
            with self.subTest(fragment=fragment), self.assertRaises(ValueError) as caught:
                parse_study(document)
            self.assertIn(fragment, str(caught.exception))

    def test_the_mass_saved_check(self):
        from cadgen._internal.fea.analyses.kinds import MASS_SAVED

        self.assertEqual(MASS_SAVED.parse({"kind": "mass_saved"}, "c"), {"kind": "mass_saved", "min_percent": 25.0})
        self.assertEqual(MASS_SAVED.parse({"kind": "mass_saved", "min_percent": 40, "label": "Weight"}, "c"),
                         {"kind": "mass_saved", "min_percent": 40.0, "label": "Weight"})
        self.assertEqual((MASS_SAVED.default_label, MASS_SAVED.scaling, MASS_SAVED.unique), ("Mass saved", "none", True))


def _slab(points):
    """A structured slab of linear tets, ``points`` per axis, as (points (N, 3), tets (E, 4))."""
    import numpy as np
    from skfem import MeshTet

    mesh = MeshTet.init_tensor(*(np.linspace(0.0, length, count + 1) for length, count in points))
    return mesh.p.T.copy(), mesh.t.T.copy()


def _half_mbb(nx: int):
    """The classic half MBB beam (3 x 1, plane: z held), a structured slab of linear tets: (problem, element size)."""
    import numpy as np

    from cadgen._internal.fea import topology_ops as topo
    from cadgen._internal.fea.operators import isotropic_matrix

    L, H = 60.0, 20.0
    ny = nx // 3
    points, tets = _slab([(L, nx), (H, ny), (2.0, 1)])
    Ke, volume, gradients = topo.tet_stiffness(points, tets, isotropic_matrix(1.0, 0.3))
    n = len(points)
    dofs = (3 * tets[:, :, None] + np.arange(3)).reshape(len(tets), 12)
    fixed = [3 * np.flatnonzero(np.isclose(points[:, 0], 0.0))]                                    # symmetry: ux = 0
    fixed.append(3 * np.flatnonzero(np.isclose(points[:, 0], L) & np.isclose(points[:, 1], 0.0)) + 1)  # the roller
    fixed.append(3 * np.arange(n) + 2)                                                           # plane
    free = np.setdiff1d(np.arange(3 * n), np.concatenate(fixed))
    F = np.zeros((3 * n, 1))
    top = np.flatnonzero(np.isclose(points[:, 0], 0.0) & np.isclose(points[:, 1], H))
    F[3 * top + 1, 0] = -1.0 / len(top)
    problem = topo.TopologyProblem(points, tets, Ke, volume, gradients, dofs, 3 * n, F, free, np.zeros(len(tets), bool))
    return problem, L / nx


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Core(unittest.TestCase):
    """topology_ops on structured meshes: exact answers, gradients and discretisation independence."""

    def test_the_filter_keeps_a_constant_and_its_adjoint_is_its_transpose(self):
        import numpy as np

        from cadgen._internal.fea import topology_ops as topo

        points, tets = _slab([(10.0, 5), (4.0, 2), (2.0, 1)])
        volume, gradients = topo.tet_geometry(points, tets)
        self.assertAlmostEqual(float(volume.sum()), 80.0, places=9)
        filt = topo.HelmholtzFilter(tets, volume, gradients, len(points), topo.filter_radius(3.0))
        _, element = filt.apply(np.full(len(tets), 0.4))
        np.testing.assert_allclose(element, 0.4, atol=1e-12)
        rng = np.random.default_rng(2)
        x, y = rng.random(len(tets)), rng.random(len(tets))
        self.assertAlmostEqual(float(filt.apply(x)[1] @ y), float(x @ filt.adjoint(y)), places=10)

    def test_the_compliance_gradient_matches_finite_differences(self):
        import numpy as np

        from cadgen._internal.fea import topology_ops as topo

        problem, h = _half_mbb(6)
        filt = topo.HelmholtzFilter(problem.tets, problem.volume, problem.gradients, len(problem.points), topo.filter_radius(3 * h))
        solver = topo.LinearSolver(problem, "direct")
        x = np.random.default_rng(4).uniform(0.3, 0.7, len(problem.tets))
        c, dc, dv, _, _ = topo.evaluate(problem, filt, solver, x, 3.0, 2.0)
        for e in (0, 17, len(x) - 1):
            step = np.zeros_like(x)
            step[e] = 1e-6
            up = topo.evaluate(problem, filt, solver, x + step, 3.0, 2.0)
            down = topo.evaluate(problem, filt, solver, x - step, 3.0, 2.0)
            self.assertAlmostEqual((up[0] - down[0]) / 2e-6 / dc[e], 1.0, delta=1e-4)
        volume = lambda design: float(problem.volume @ topo.heaviside(filt.apply(design)[1], 2.0)) / float(problem.volume.sum())
        step = np.zeros_like(x)
        step[5] = 1e-6
        self.assertAlmostEqual((volume(x + step) - volume(x - step)) / 2e-6 / dv[5], 1.0, delta=1e-5)

    def test_the_iterative_solver_agrees_with_the_direct_one(self):
        import numpy as np

        from cadgen._internal.fea import topology_ops as topo
        from cadgen._internal.fea.operators import rigid_body_modes

        problem, _ = _half_mbb(12)
        component = np.tile(np.arange(3), len(problem.points))
        problem.near_nullspace = rigid_body_modes(np.repeat(problem.points, 3, axis=0), component)
        scale = np.random.default_rng(1).uniform(0.01, 1.0, len(problem.tets))
        K = problem.assemble(scale)
        direct = topo.LinearSolver(problem, "direct").solve(K)
        iterative = topo.LinearSolver(problem, "iterative")
        first = iterative.solve(K)
        np.testing.assert_allclose(first, direct, atol=1e-6 * np.abs(direct).max())
        # Warm-started on a slightly changed stiffness, with the same hierarchy: still the direct answer.
        K2 = problem.assemble(scale * 1.01)
        np.testing.assert_allclose(iterative.solve(K2), topo.LinearSolver(problem, "direct").solve(K2), atol=1e-6 * np.abs(direct).max())
        self.assertEqual(iterative.rebuilds, 1)

    def test_a_coarse_and_a_twice_finer_design_agree(self):
        """Discretisation independence: the filter fixes the member size in mm, so the optimum's compliance
        hardly moves when the mesh is halved (half MBB, 50 %, the classic problem)."""
        from cadgen._internal.fea import topology_ops as topo

        results = []
        for nx in (24, 48):
            problem, _ = _half_mbb(nx)
            schedule = topo.Schedule(max_iterations=120)
            _, projected, history, _ = topo.optimise(problem, 0.5, schedule, radius=topo.filter_radius(7.5),
                                                     design_map=topo.DesignMap(len(problem.tets)))
            self.assertAlmostEqual(history.volume[-1], 0.5, delta=0.005)
            results.append(history.compliance[-1])
            solid = float(problem.energies(topo.LinearSolver(problem, "direct").solve(problem.assemble(1.0 + 0 * projected))).sum())
            # Stiffer than the same mass spread evenly (SIMP's grey: compliance / 0.5^3), never stiffer than solid.
            self.assertTrue(solid < history.compliance[-1] < solid / 0.5 ** 3, (solid, history.compliance[-1]))
        self.assertLess(abs(results[1] - results[0]) / results[1], 0.05, results)

    def test_the_surface_of_a_solid_block_is_the_block(self):
        import numpy as np

        from cadgen._internal.fea import topology_ops as topo

        points, tets = _slab([(4.0, 4), (2.0, 2), (2.0, 2)])
        faces = np.concatenate([tets[:, list(f)] for f in ((1, 2, 3), (0, 3, 2), (0, 1, 3), (0, 2, 1))])
        key = np.sort(faces, axis=1)
        _, first, counts = np.unique(key, axis=0, return_index=True, return_counts=True)
        boundary = faces[first[counts == 1]]
        vertices, triangles, _ = topo.iso_surface(points, tets, np.ones(len(points)), boundary)
        self.assertAlmostEqual(topo.enclosed_volume(vertices, triangles), 16.0, places=9)
        # Density falling along x: the design is x < 1.7, closed by the block's own faces; smoothing a flat cut keeps it.
        for values, length in ((1.0 - (points[:, 0] + 0.3) / 4.0, 1.7), (1.0 - points[:, 0] / 4.0, 2.0)):
            vertices, triangles, fixed = topo.iso_surface(points, tets, values, boundary)
            self.assertAlmostEqual(topo.enclosed_volume(vertices, triangles), 4.0 * length, places=6)
            if length == 1.7:  # (a level exactly at nodes leaves sliver triangles; real densities never sit on it)
                smoothed = topo.smooth(vertices, triangles, fixed)
                self.assertAlmostEqual(topo.enclosed_volume(smoothed, triangles), 4.0 * length, delta=1e-6)

    def test_the_design_map_makes_a_design_symmetric(self):
        import numpy as np

        from cadgen._internal.fea import topology_ops as topo

        # Element centroids on a grid symmetric about x = 3, in a shuffled order; columns along z.
        grid = np.stack(np.meshgrid(np.arange(6) + 0.5, np.arange(2) + 0.5, np.arange(3) + 0.5, indexing="ij"), -1).reshape(-1, 3)
        centroids = grid[np.random.default_rng(5).permutation(len(grid))]
        design = topo.DesignMap(len(centroids))
        self.assertLess(design.add_mirror(centroids, 0, 3.0, 1.0), 1e-12)
        self.assertEqual(design.add_extrusion(centroids, np.array([0.0, 0.0, 1.0]), 1.0), 12)
        values = design.apply(np.random.default_rng(0).random(len(centroids)))
        mirrored = centroids.copy()
        mirrored[:, 0] = 6.0 - mirrored[:, 0]
        partner = [int(np.argmin(np.linalg.norm(centroids - m, axis=1))) for m in mirrored]
        np.testing.assert_allclose(values, values[partner], atol=1e-12)
        column = [np.flatnonzero(np.all(np.isclose(centroids[:, :2], c[:2]), axis=1)) for c in centroids]
        for members in column:
            np.testing.assert_allclose(values[members], values[members[0]], atol=1e-12)


def _glb(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    return json.loads(raw[20:20 + length]), raw[20 + length + 8:]


def _attribute(path: Path, name: str):
    import numpy as np

    gltf, blob = _glb(path)
    primitive = gltf["meshes"][0]["primitives"][0]
    accessor = gltf["accessors"][primitive["attributes"][name]]
    view = gltf["bufferViews"][accessor["bufferView"]]
    width = {"SCALAR": 1, "VEC3": 3}[accessor["type"]]
    data = np.frombuffer(blob, dtype=np.float32, count=accessor["count"] * width,
                         offset=view.get("byteOffset", 0) + accessor.get("byteOffset", 0))
    return data.reshape(accessor["count"], width)


def _slab_step(directory: Path, name: str, outline) -> Path:
    from build123d import Face, Solid, Vector, Wire, export_step

    solid = Solid.extrude(Face(Wire.make_polygon([Vector(x, y, 0) for x, y in outline], close=True)), Vector(0, 0, 2.0))
    path = directory / f"{name}.step"
    export_step(solid, str(path))
    return path


def _faces_at(path: Path) -> dict:
    from cadgen import fea

    return {tuple(round(c, 3) for c in face.center_mm): face.ref for face in fea.faces(path).faces}


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Benchmarks(unittest.TestCase):
    """The MBB beam and the cantilever, end to end through ``cadgen fea``."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls._tmp.name)
        # MBB: 60 x 20, 3 mm pads at the bottom corners, a 3 mm load pad at the top middle.
        cls.mbb = _slab_step(cls.directory, "mbb", [(0, 0), (3, 0), (57, 0), (60, 0), (60, 20), (31.5, 20), (28.5, 20), (0, 20)])
        at = _faces_at(cls.mbb)
        cls.mbb_faces = (at[(1.5, 0.0, 1.0)], at[(58.5, 0.0, 1.0)], at[(30.0, 20.0, 1.0)])
        # Cantilever: 40 x 20, held on its left face, a 2 mm load pad at the middle of its right face.
        cls.cantilever = _slab_step(cls.directory, "cantilever", [(0, 0), (40, 0), (40, 9), (40, 11), (40, 20), (0, 20)])
        at = _faces_at(cls.cantilever)
        cls.cantilever_faces = (at[(0.0, 10.0, 1.0)], at[(40.0, 10.0, 1.0)])

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _mbb_study(self, **changes) -> dict:
        left, right, top = self.mbb_faces
        return {"analysis": "topology", "material": "steel", "fixtures": [{"faces": [left, right]}],
                "loads": [{"faces": [top], "type": "force", "vector_N": [0, -100, 0]}], "volume_fraction": 0.5,
                "mesh": {"size_mm": 2.0}, "iterations": 100, **changes}

    def _solve(self, step: Path, name: str, study: dict):
        from cadgen import fea

        glb = self.directory / f"{name}.fea.glb"
        with redirect_stderr(io.StringIO()):
            result = fea.solve(step, glb, study=study)
        self.assertTrue(result.ok)
        sidecar = json.loads(glb.with_suffix(".json").read_text(encoding="utf-8"))
        return result, glb, sidecar

    def _promises(self, result, sidecar, target: float):
        """Volume on target within 1 %; compliance non-increasing (0.5 % slack) once the continuation is done;
        stiffer than the uniform grey part of the same mass, never stiffer than the solid part."""
        summary = result.summary
        self.assertAlmostEqual(summary["volume_fraction"], target, delta=0.01 * target)
        history = result_history(sidecar)
        final = history[sidecar_final_stage(sidecar):]
        self.assertGreaterEqual(len(final), 3)
        rises = [(b - a) / a for a, b in zip(final, final[1:])]
        self.assertLess(max(rises), 5e-3, rises)
        solid = summary["solid_compliance_Nmm"]
        self.assertGreater(summary["verified_compliance_Nmm"], solid)
        self.assertLess(summary["compliance_Nmm"], solid / target ** 3)
        return summary

    def test_mbb_beam(self):
        result, glb, sidecar = self._solve(self.mbb, "mbb", self._mbb_study(symmetry=["x"]))
        summary = self._promises(result, sidecar, 0.5)
        self.assertLess(summary["compliance_ratio"], 2.0)
        self.assertLess(summary["grey_percent"], 10.0)
        # The design is symmetric about the middle: the surface's density averaged over cells, against its mirror cell.
        import numpy as np

        positions = _attribute(glb, "POSITION").astype(float) * 1000.0      # glTF metres -> mm; x is the part's x
        final = sidecar["series"]["frames"][-1]["attributes"]["material_kept"]
        density = _attribute(glb, final)[:, 0]
        across = int(np.argmax(np.ptp(positions[:, 1:], axis=0))) + 1       # the slab's height in glTF axes
        cells = np.stack([np.clip((positions[:, 0] / 4.0).astype(int), 0, 14),
                          np.clip(((positions[:, across] - positions[:, across].min()) / 4.0).astype(int), 0, 4)], axis=1)
        sums, counts = np.zeros((15, 5)), np.zeros((15, 5))
        np.add.at(sums, (cells[:, 0], cells[:, 1]), density)
        np.add.at(counts, (cells[:, 0], cells[:, 1]), 1)
        mean = sums / np.maximum(counts, 1)
        self.assertLess(float(np.abs(mean - mean[::-1]).mean()), 0.05, np.round(mean, 2))
        # What it writes: the series, the curves, the checks, the kept faces and the design surface.
        self.assertEqual(sidecar["analysis"], "topology")
        self.assertLessEqual(len(sidecar["series"]["frames"]), 24)
        self.assertEqual(sidecar["series"]["frames"][-1]["label"], "Final design")
        self.assertEqual(set(sidecar["curves"]), {"compliance_Nmm", "volume_fraction", "grey_fraction"})
        self.assertEqual([c["kind"] for c in summary["checks"]], ["mass_saved", "stress"])
        self.assertEqual(summary["checks"][0]["status"], "passes")
        self.assertTrue(set(self.mbb_faces) <= {entry["face"] for entry in summary["kept_solid"]})
        stl = glb.with_name(sidecar["files"]["design_stl"])
        self.assertTrue(stl.is_file())
        self.assertAlmostEqual(summary["surface_volume_mm3"] / summary["design_volume_mm3"], 1.0, delta=0.15)
        self.assertEqual(stl.stat().st_size, 84 + 50 * summary["design_triangles"])
        self.assertTrue(any(line.startswith("design surface:") for line in result.human_lines()))
        print(f"\nMBB: {summary['iterations']} iterations, volume {summary['volume_fraction']:.4f}, compliance "
              f"{summary['compliance_Nmm']:.5g} N mm (verified {summary['verified_compliance_Nmm']:.5g}), solid "
              f"{summary['solid_compliance_Nmm']:.5g}, ratio {summary['compliance_ratio']:.3f}, grey {summary['grey_percent']:.2f} %, "
              f"{result.timings}")

    def test_cantilever(self):
        held, pushed = self.cantilever_faces
        study = {"analysis": "topology", "material": "steel", "fixtures": [{"faces": [held]}],
                 "loads": [{"faces": [pushed], "type": "force", "vector_N": [0, -100, 0]}], "volume_fraction": 0.4,
                 "mesh": {"size_mm": 1.5}, "iterations": 120,
                 "view": {"checks": [{"kind": "mass_saved", "min_percent": 50}, {"kind": "displacement", "limit_mm": 0.05}]}}
        result, glb, sidecar = self._solve(self.cantilever, "cantilever", study)
        summary = self._promises(result, sidecar, 0.4)
        self.assertEqual([(c["kind"], c["status"]) for c in summary["checks"]], [("mass_saved", "passes"), ("displacement", "passes")])
        print(f"\ncantilever: {summary['iterations']} iterations, volume {summary['volume_fraction']:.4f}, compliance "
              f"{summary['compliance_Nmm']:.5g} N mm (verified {summary['verified_compliance_Nmm']:.5g}), solid "
              f"{summary['solid_compliance_Nmm']:.5g}, ratio {summary['compliance_ratio']:.3f}, grey {summary['grey_percent']:.2f} %, "
              f"{result.timings}")

    def test_the_ladder_halves_and_coarsens_it_and_says_what_member_size_is_left(self):
        result, glb, sidecar = self._solve(self.mbb, "mbb-ladder", self._mbb_study(iterations=60, fit={"seconds": 0.3}))
        rungs = [step["rung"] for step in sidecar["fit"]]
        self.assertIn("symmetry", rungs)
        self.assertIn("coarse_design", rungs)
        coarse = next(step for step in sidecar["fit"] if step["rung"] == "coarse_design")
        self.assertRegex(coarse["words"], r"resolves members down to about [0-9.]+ mm")
        self.assertTrue(any(line.startswith("adapted: Used a coarser design mesh") for line in result.human_lines()))
        self.assertTrue(any(f["type"] == "fit_coarse_design" for f in sidecar["findings"]))
        self.assertAlmostEqual(result.summary["volume_fraction"], 0.5, delta=0.005)
        self.assertFalse(any("do not balance" in warning for warning in result.warnings))
        print(f"\nladder: {rungs}, {coarse['words']}; {result.summary['iterations']} iterations, {result.mesh}")

    def test_lightest_finds_the_least_material_that_stays_within_its_limit(self):
        study = self._mbb_study(objective="lightest", volume_fraction=0.5, iterations=40,
                                view={"checks": [{"kind": "displacement", "limit_mm": 0.0028}]})
        result, glb, sidecar = self._solve(self.mbb, "mbb-lightest", study)
        rounds = result.summary["lightest_rounds"]
        self.assertGreaterEqual(len(rounds), 2)
        passing = [r["volume_fraction"] for r in rounds if r["passes"]]
        self.assertTrue(passing)
        self.assertAlmostEqual(result.summary["volume_fraction_target"], min(passing), places=4)
        self.assertTrue(any(not r["passes"] and r["volume_fraction"] < min(passing) for r in rounds), rounds)
        self.assertEqual(result.summary["checks"][0]["status"] != "fails", True)
        print(f"\nlightest: {rounds}")


def result_history(sidecar: dict) -> list[float]:
    return sidecar["curves"]["compliance_Nmm"]["y"]


def sidecar_final_stage(sidecar: dict) -> int:
    return sidecar["summary"]["final_stage_start"]


if __name__ == "__main__":
    unittest.main()
