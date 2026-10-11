"""Fast gas flow (`"analysis": "cfd_compressible"`, lite): the study it reads, a nozzle against the isentropic tables,
a normal shock, mass conservation, the low-speed limit against cfd and the ladder.

The nozzle is a converging-diverging bore through a round bar along x, 40 mm long: radius 3 mm at the inlet,
2 mm at the throat (x = 15) and 2.6 mm at the exit, cosine-shaped between, so the flow is close to the
quasi-one-dimensional one. Air enters at x_min from a reservoir (total pressure p0, 20 °C) and leaves at
x_max to 101325 Pa. Subsonic (p_out / p0 = 0.95), every section's Mach number follows the isentropic
area-Mach relation from the exit's Mach number. Choked (p_out / p0 = 0.75), a normal shock stands in the
diverging part where the shock relations put it, and the mass flow is the throat's choked one. Slowly
(0.5 m/s of air through the cfd tests' tube), it is the incompressible laminar flow. Every STEP is a
build123d solid in a temporary directory.
"""

from __future__ import annotations

import io
import json
import math
import struct
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

GAMMA, R_AIR, T0 = 1.4, 287.0, 293.15
P_OUT = 101325.0
R_IN, R_THROAT, R_EXIT, LENGTH, X_THROAT, R_BAR = 3.0, 2.0, 2.6, 40.0, 15.0, 4.0
LIMIT_TEXT = ("Steady, ideal gas, adiabatic (one total temperature); an inviscid core with frictionless walls past the "
              "laminar range, laminar walls in it; no turbulence model; shocks are captured over a few elements.")


def nozzle_study(ratio: float, **changes) -> dict:
    return {"analysis": "cfd_compressible", "mesh": {"size_mm": 1.6},
            "flow": {"kind": "internal", "gas": "air",
                     "inlets": [{"opening": "x_min", "total_pressure_Pa": P_OUT / ratio, "total_temperature_C": 20}],
                     "outlets": [{"opening": "x_max", "pressure_Pa": P_OUT}]}, **changes}


def radius(x: float) -> float:
    if x <= X_THROAT:
        return R_THROAT + (R_IN - R_THROAT) * (1 + math.cos(math.pi * x / X_THROAT)) / 2
    return R_THROAT + (R_EXIT - R_THROAT) * (1 - math.cos(math.pi * (x - X_THROAT) / (LENGTH - X_THROAT))) / 2


def nozzle_step(directory: Path) -> Path:
    from build123d import Axis, BuildLine, BuildPart, BuildSketch, Line, Plane, Spline, export_step, make_face, revolve

    points = [(LENGTH * i / 20, radius(LENGTH * i / 20)) for i in range(21)]
    with BuildPart() as part:
        with BuildSketch(Plane.XY):
            with BuildLine():
                Spline(*points)
                Line(points[-1], (LENGTH, R_BAR))
                Line((LENGTH, R_BAR), (0, R_BAR))
                Line((0, R_BAR), points[0])
            make_face()
        revolve(axis=Axis.X)
    step = directory / "nozzle.step"
    export_step(part.part, str(step))
    return step


# -- the isentropic tables and the normal shock -------------------------------------------------------


def area_ratio(mach: float) -> float:
    g = GAMMA
    return (1 / mach) * ((2 / (g + 1)) * (1 + 0.5 * (g - 1) * mach * mach)) ** ((g + 1) / (2 * (g - 1)))


def pressure_ratio(mach: float) -> float:
    return (1 + 0.5 * (GAMMA - 1) * mach * mach) ** (-GAMMA / (GAMMA - 1))


def bisect(f, low: float, high: float) -> float:
    """The root of increasing-or-decreasing ``f`` between ``low`` and ``high``."""
    f_low = f(low)
    for _ in range(200):
        middle = 0.5 * (low + high)
        if (f(middle) > 0) == (f_low > 0):
            low = middle
        else:
            high = middle
    return 0.5 * (low + high)


def subsonic_mach(ratio: float) -> float:
    return bisect(lambda m: area_ratio(m) - ratio, 1e-6, 1.0)


def exit_mach(ratio: float) -> float:
    """Isentropic exit Mach number at p_out / p0 = ``ratio``."""
    return math.sqrt(2 / (GAMMA - 1) * (ratio ** (-(GAMMA - 1) / GAMMA) - 1))


def shock_place(ratio: float) -> tuple[float, float]:
    """Where a normal shock stands in the diverging part at p_out / p0 = ``ratio``, and the Mach number ahead of it.

    The exit is subsonic past the shock: p_e A_e / (p01 A*) = p_e/p02 * A_e/A*2 fixes its Mach number, the total
    pressure lost (p02 / p01) fixes the shock's Mach number, and the area there is A* times its area ratio."""
    throat, exit_area = math.pi * R_THROAT ** 2, math.pi * R_EXIT ** 2
    m_exit = bisect(lambda m: pressure_ratio(m) * area_ratio(m) - ratio * exit_area / throat, 1e-6, 1.0)
    lost = ratio / pressure_ratio(m_exit)
    g = GAMMA

    def total_ratio(m1):
        return (((g + 1) * m1 ** 2 / ((g - 1) * m1 ** 2 + 2)) ** (g / (g - 1))
                * ((g + 1) / (2 * g * m1 ** 2 - (g - 1))) ** (1 / (g - 1))) - lost

    m1 = bisect(total_ratio, 1.0 + 1e-9, 5.0)
    area = throat * area_ratio(m1)
    return bisect(lambda x: math.pi * radius(x) ** 2 - area, X_THROAT, LENGTH), m1


def choked_mass(p0: float) -> float:
    g = GAMMA
    return p0 * math.pi * (R_THROAT / 1000) ** 2 * math.sqrt(g / (R_AIR * T0)) * (2 / (g + 1)) ** ((g + 1) / (2 * (g - 1)))


# -- running a study ----------------------------------------------------------------------------------


def glb_extras(path: Path) -> tuple[dict, list[str]]:
    raw = path.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    gltf = json.loads(raw[20:20 + length])
    return gltf["meshes"][0]["extras"], list(gltf["meshes"][0]["primitives"][0]["attributes"])


def solve(step: Path, out: Path, study: dict):
    """Run the study; also hand back the gas flow's own space and solution (the volume's Mach numbers)."""
    from cadgen import fea
    from cadgen._internal.fea.analyses.cfd_compressible import CfdCompressibleAnalysis

    captured: dict = {}
    original = CfdCompressibleAnalysis._post

    def keep(self, space, fluid, face_of, row_kind, flow, inputs, setup):
        captured["space"], captured["flow"] = space, flow
        return original(self, space, fluid, face_of, row_kind, flow, inputs, setup)

    with redirect_stderr(io.StringIO()), mock.patch.object(CfdCompressibleAnalysis, "_post", keep):
        result = fea.solve(step, out, study=study)
    return result, captured


def section_mach(captured: dict, x: float, half: float = 0.5) -> float:
    """The mean Mach number of the fluid's nodes within ``half`` mm of the section at ``x``."""
    import numpy as np

    where = captured["space"].dof_locations
    return float(captured["flow"].mach[np.abs(where[:, 0] - x) < half].mean())


class StudyFile(unittest.TestCase):
    def parse(self, **changes):
        from cadgen._internal.fea.study import parse_study

        return parse_study({**nozzle_study(0.95), **changes})

    def test_it_reads_a_gas_flow_without_a_material(self):
        parsed = self.parse()
        inputs = parsed.inputs
        self.assertIsNone(parsed.material)
        self.assertEqual((inputs.kind, inputs.gas.name, inputs.gas.gamma, inputs.gas.R, inputs.walls), ("internal", "air", 1.4, 287.0, "auto"))
        self.assertEqual([(i.opening, i.kind, round(i.total_pressure_Pa, 3), i.total_temperature_C) for i in inputs.inlets],
                         [("x_min", "total", round(P_OUT / 0.95, 3), 20.0)])
        self.assertEqual([(o.opening, o.pressure_Pa) for o in inputs.outlets], [("x_max", P_OUT)])
        self.assertFalse(inputs.mapped)

    def test_an_inlet_by_mass_flow_an_external_stream_and_a_gas_of_its_own(self):
        mass = self.parse(flow={"kind": "internal", "gas": "helium", "walls": "no_slip",
                                "inlets": [{"opening": "x_min", "mass_flow_kg_s": 0.002, "profile": "uniform"}],
                                "outlets": [{"opening": "x_max"}]}).inputs
        self.assertEqual((mass.inlets[0].kind, mass.inlets[0].mass_flow_kg_s, mass.walls, mass.outlets[0].pressure_Pa), ("mass", 0.002, "no_slip", P_OUT))
        self.assertAlmostEqual(mass.gas.gamma, 5 / 3)
        external = self.parse(flow={"kind": "external", "gas": {"name": "argon", "gamma": 1.67, "gas_constant_J_kgK": 208,
                                                                 "viscosity_Pa_s": 2.2e-5}, "velocity_m_s": [150, 0, 0]}).inputs
        self.assertEqual((external.kind, external.velocity_m_s, external.gas.name, external.pressure_Pa, external.temperature_C),
                         ("external", (150.0, 0.0, 0.0), "argon", P_OUT, 20.0))

    def test_the_errors_name_the_field_in_plain_words(self):
        flow = nozzle_study(0.95)["flow"]
        inlet = flow["inlets"][0]
        for changes, fragment in (
            ({"flow": {**flow, "gas": "steam"}}, "is not a gas cadgen knows"),
            ({"flow": {**flow, "inlets": [{"opening": "x_min"}]}}, "total_pressure_Pa (absolute, Pa) or its mass_flow_kg_s, exactly one"),
            ({"flow": {**flow, "inlets": [{**inlet, "total_pressure_Pa": 90000}]}}, "is not above the outlet's 101325 Pa"),
            ({"flow": {**flow, "inlets": [{**inlet, "profile": "uniform"}]}}, "a profile goes with mass_flow_kg_s"),
            ({"flow": {**flow, "walls": "rough"}}, "flow.walls"),
            ({"flow": {**flow, "outlets": [{"opening": "x_min"}]}}, "x_min is named twice"),
            ({"flow": {**flow, "inlets": [{**inlet, "velocity_m_s": 5}]}}, "an inlet takes opening, total_pressure_Pa or mass_flow_kg_s"),
            ({"flow": {**flow, "inlets": [{**inlet, "total_temperature_C": -300}]}}, "above absolute zero"),
            ({"view": {"checks": [{"kind": "stress"}]}}, "add map_to_structure"),
            ({"view": {"checks": [{"kind": "mach"}]}}, "a mach check needs the fastest Mach number allowed"),
            ({"flow": None}, "study.flow"),
        ):
            with self.subTest(fragment=fragment), self.assertRaises(ValueError) as caught:
                self.parse(**changes)
            self.assertIn(fragment, str(caught.exception))

    def test_the_mach_check_is_a_kind_of_its_own(self):
        from cadgen._internal.fea.analyses.kinds import CHECK_SPECS

        spec = CHECK_SPECS["mach"]
        self.assertEqual((spec.default_label, spec.scaling), ("Mach number", "none"))
        self.assertEqual(spec.parse({"kind": "mach", "limit": 0.8, "label": "Nozzle"}, "c"), {"kind": "mach", "limit": 0.8, "label": "Nozzle"})
        parsed = self.parse(view={"checks": [{"kind": "mach", "limit": 0.8}, {"kind": "pressure_drop", "limit_Pa": 3000}]})
        self.assertEqual([check["kind"] for check in parsed.checks], ["mach", "pressure_drop"])

    def test_it_is_registered_built_and_stdlib_only_at_import(self):
        import subprocess
        import sys

        from cadgen._internal.fea.analyses import REGISTRY, get_analysis

        analysis = get_analysis("cfd_compressible")
        self.assertFalse(REGISTRY["cfd_compressible"].planned)
        self.assertEqual((analysis.tier, analysis.word, analysis.limits), (3, "Fast gas flow", (LIMIT_TEXT,)))
        self.assertEqual(analysis.ladder, ("fluid_coarsen", "continuation", "iterative"))
        self.assertEqual([spec.name for spec in analysis.fields][:3], ["pressure", "mach", "temperature"])
        code = (
            "import sys; sys.path.insert(0, 'packages/cadgen/src');"
            "import cadgen._internal.fea.analyses.cfd_compressible, cadgen._internal.fea.compressible;"
            "print(','.join(m for m in ('numpy', 'scipy', 'skfem', 'netgen', 'OCP') if m in sys.modules))"
        )
        root = Path(__file__).resolve().parents[4]
        self.assertEqual(subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True, check=True).stdout.strip(), "")

    def test_the_tables_this_file_checks_against(self):
        # Textbook values (gamma 1.4): A/A* 1.6875 at Mach 0.37 and 2.0 at 0.306; the shock relations at Mach 2.
        self.assertAlmostEqual(area_ratio(2.0), 1.6875, places=4)
        self.assertAlmostEqual(subsonic_mach(2.0), 0.3059, places=3)
        self.assertAlmostEqual(pressure_ratio(1.0), 0.5283, places=4)


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class SubsonicNozzle(unittest.TestCase):
    """p_out / p0 = 0.95: subsonic everywhere (Mach 0.51 at the throat); each section on the isentropic area-Mach curve."""

    RATIO = 0.95

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        study = nozzle_study(cls.RATIO, view={"checks": [{"kind": "mach", "limit": 0.55}, {"kind": "pressure_drop", "limit_Pa": 5000}]})
        cls.result, cls.captured = solve(nozzle_step(directory), directory / "nozzle.glb", study)
        cls.extras, cls.attributes = glb_extras(cls.result.glb)
        cls.sidecar = json.loads(cls.result.sidecar.read_text(encoding="utf-8"))
        cls.summary = cls.result.summary

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_every_section_is_on_the_isentropic_area_mach_curve(self):
        m_exit = exit_mach(self.RATIO)
        sonic = math.pi * R_EXIT ** 2 / area_ratio(m_exit)
        for x in (2.0, 8.0, 15.0, 22.0, 30.0, 38.0):
            expected = subsonic_mach(math.pi * radius(x) ** 2 / sonic)
            with self.subTest(x=x):
                self.assertLess(abs(section_mach(self.captured, x) / expected - 1), 0.05, (x, section_mach(self.captured, x), expected))

    def test_the_mass_flow_is_the_isentropic_one_and_is_conserved(self):
        m_exit = exit_mach(self.RATIO)
        t_exit = T0 / (1 + 0.2 * m_exit ** 2)
        expected = P_OUT / (R_AIR * t_exit) * m_exit * math.sqrt(GAMMA * R_AIR * t_exit) * math.pi * (R_EXIT / 1000) ** 2
        self.assertLess(abs(self.summary["mass_flow_kg_s"] / expected - 1), 0.02, (self.summary["mass_flow_kg_s"], expected))
        self.assertLess(self.summary["flow_balance"], 1e-6)
        self.assertTrue(self.summary["solve"]["converged"])
        self.assertAlmostEqual(self.summary["pressure_ratio"], 1 / self.RATIO, places=5)
        self.assertEqual((self.summary["mach"]["regime"], self.summary["choked"], self.summary["shock"]), ("subsonic", False, None))

    def test_the_glb_carries_pressure_mach_and_temperature_on_the_wetted_walls(self):
        fields = {entry["field"]: entry for entry in self.extras["fields"]}
        self.assertEqual(set(fields), {"pressure", "mach", "temperature"})
        self.assertEqual((fields["pressure"]["units"], fields["mach"]["units"], fields["temperature"]["units"]), ("Pa", "", "°C"))
        for attribute in ("_PRESSURE", "_MACH", "_TEMPERATURE"):
            self.assertIn(attribute, self.attributes)
        # The throat's wall is the fastest and the coldest: T = T0 / (1 + 0.2 M^2).
        self.assertGreater(fields["mach"]["max"], 0.45)
        coldest = (T0 / (1 + 0.2 * fields["mach"]["max"] ** 2)) - 273.15
        self.assertAlmostEqual(fields["temperature"]["min"], coldest, delta=1.0)
        self.assertEqual(self.extras["analysis"]["limits"], [LIMIT_TEXT])
        self.assertEqual(self.sidecar["limits"], [LIMIT_TEXT])
        self.assertEqual(self.extras["analysis"]["mach"]["regime"], "subsonic")
        self.assertEqual(self.extras["analysis"]["walls"], "slip")
        self.assertEqual(self.extras["study"]["flow"]["inlets"][0]["opening"], "x_min")

    def test_its_walls_slip_past_the_laminar_range_and_it_says_so(self):
        self.assertEqual(self.summary["walls"], "slip")
        self.assertGreater(self.summary["reynolds"]["value"], 2000)
        self.assertTrue(any("frictionless (an inviscid core)" in line for line in self.extras["analysis"]["warnings"]))

    def test_the_checks_and_the_cli(self):
        checks = {check["kind"]: check for check in self.summary["checks"]}
        self.assertEqual((checks["mach"]["unit"], checks["mach"]["status"]), ("", "close"))
        self.assertEqual(checks["pressure_drop"]["status"], "passes")
        lines = "\n".join(self.result.human_lines())
        self.assertIn("internal flow of air: fastest Mach", lines)
        self.assertIn("(cfd_compressible)", lines)
        self.assertIn("mach_close_to_limit", [finding["type"] for finding in self.result.findings])


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class ChokedNozzle(unittest.TestCase):
    """p_out / p0 = 0.75 with a one-second time target: the ladder steps the pressure ratio up (continuation),
    the nozzle chokes, and a normal shock stands where the shock relations put it (x = 27.6 mm, Mach 1.69 ahead)."""

    RATIO = 0.75

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        study = nozzle_study(cls.RATIO, fit={"seconds": 1, "allow": ["continuation"]})
        cls.result, cls.captured = solve(nozzle_step(directory), directory / "choked.glb", study)
        cls.extras, _ = glb_extras(cls.result.glb)
        cls.summary = cls.result.summary

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_ladder_steps_the_pressure_ratio_up_and_says_so(self):
        rungs = [step["rung"] for step in self.result.fit]
        self.assertIn("continuation", rungs)
        step = next(step for step in self.result.fit if step["rung"] == "continuation")
        self.assertIn("Reached the full pressure ratio in steps (50%, 100% of the drive)", step["words"])
        self.assertEqual(self.extras["fit"][rungs.index("continuation")]["words"], step["words"])
        self.assertIn("fit_continuation", [finding["type"] for finding in self.result.findings])
        self.assertIn(f"adapted: {step['words']}", self.result.human_lines())
        self.assertEqual(self.summary["solve"]["stages"], [0.5, 1.0])
        self.assertTrue(self.summary["solve"]["converged"])

    def test_it_chokes_at_the_throats_mass_flow(self):
        expected = choked_mass(P_OUT / self.RATIO)
        self.assertLess(abs(self.summary["mass_flow_kg_s"] / expected - 1), 0.02, (self.summary["mass_flow_kg_s"], expected))
        self.assertLess(self.summary["flow_balance"], 1e-6)
        self.assertTrue(self.summary["choked"])
        self.assertEqual(self.summary["mach"]["regime"], "supersonic")
        self.assertAlmostEqual(section_mach(self.captured, X_THROAT + 0.5), 1.0, delta=0.05)

    def test_the_normal_shock_stands_where_the_shock_relations_put_it(self):
        place, ahead = shock_place(self.RATIO)
        diverging = LENGTH - X_THROAT
        # The section-mean Mach number falls back through 1 at the shock.
        sections = [x + 0.5 for x in range(int(X_THROAT), int(LENGTH))]
        machs = [section_mach(self.captured, x) for x in sections]
        peak = machs.index(max(machs))
        after = next(i for i in range(peak, len(machs)) if machs[i] < 1.0)
        crossing = sections[after - 1] + (machs[after - 1] - 1) / (machs[after - 1] - machs[after]) * (sections[after] - sections[after - 1])
        self.assertLess(abs(crossing - place) / diverging, 0.10, (crossing, place))
        # The summary's own place for it, and the Mach number ahead of it (smeared over a few elements, so lower).
        self.assertLess(abs(self.summary["shock"]["at_mm"][0] - place) / diverging, 0.10, (self.summary["shock"], place))
        self.assertGreater(max(machs), 0.8 * ahead)
        self.assertIn("shock", [finding["type"] for finding in self.result.findings])


def cone_nozzle_step(directory: Path) -> Path:
    """A conical converging-diverging bore through a 45 x 16 x 16 mm block along x: radius 6 mm for 5 mm, in straight
    to a sharp 2.5 mm throat at x = 20, out to 3.25 mm at x = 45 (the gallery's nozzle)."""
    from build123d import Align, Axis, Box, BuildLine, BuildPart, BuildSketch, Mode, Plane, Polyline, export_step, make_face, revolve

    with BuildPart() as part:
        Box(45, 16, 16, align=(Align.MIN, Align.CENTER, Align.CENTER))
        with BuildSketch(Plane.XY):
            with BuildLine():
                Polyline((0, 0), (0, 6), (5, 6), (20, 2.5), (45, 3.25), (45, 0), close=True)
            make_face()
        revolve(axis=Axis.X, mode=Mode.SUBTRACT)
    step = directory / "cone_nozzle.step"
    export_step(part.part, str(step))
    return step


def solve_gas_with(**options):
    """compressible.solve_gas with ``options`` laid over what the analysis passes, and every flow it returns."""
    from cadgen._internal.fea import compressible

    original, flows = compressible.solve_gas, []

    def run(problem, **given):
        flows.append(original(problem, **{**given, **options}))
        return flows[-1]

    return mock.patch.object(compressible, "solve_gas", run), flows


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class ChokingStage(unittest.TestCase):
    """The gallery's conical nozzle at half its drive (p0 = 118 kPa to 101 kPa): the gas speeds up through a low
    residual on its way to choking. The stabilisation's coefficients used to be held there, still subsonic ones,
    so the gas ran away where it went supersonic (Mach 10, a limit cycle) and the stage spent all 150 steps; they
    are held now only once the peak Mach number has settled, and the stage settles in well under that."""

    def test_the_half_drive_stage_settles_without_running_away(self):
        from cadgen._internal.fea.compressible import MAX_STEPS

        lines: list[str] = []
        patch, flows = solve_gas_with(schedule=(0.5,), log=lines.append)
        with tempfile.TemporaryDirectory() as tmp, patch:
            directory = Path(tmp)
            study = {**nozzle_study(101325.0 / 135100.0), "mesh": {"size_mm": 2.0}}
            solve(cone_nozzle_step(directory), directory / "cone.glb", study)
        flow = flows[0]
        self.assertTrue(flow.converged)                 # at the stage's own tolerance
        self.assertLess(flow.steps, MAX_STEPS // 2)
        self.assertLess(float(flow.mach.max()), 2.0)
        peaks = [float(line.rsplit("peak Mach ", 1)[1]) for line in lines if "peak Mach" in line]
        self.assertLess(max(peaks), 2.0)


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class UnsettledMarch(unittest.TestCase):
    """A march stopped short of its tolerance (three steps a stage here) is not a settled pass: every check says
    the flow did not settle and none passes outright, and the finding says why."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        study = nozzle_study(0.95, view={"checks": [{"kind": "mach", "limit": 2.0}, {"kind": "pressure_drop", "limit_Pa": 50000}]})
        patch, cls.flows = solve_gas_with(max_steps=3)
        with patch:
            cls.result, _ = solve(nozzle_step(directory), directory / "unsettled.glb", study)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_its_checks_are_labelled_not_settled_and_none_passes(self):
        self.assertFalse(self.result.summary["solve"]["converged"])
        for check in self.result.summary["checks"]:
            with self.subTest(kind=check["kind"]):
                self.assertLess(check["ratio"], 0.9)    # a pass, had the flow settled
                self.assertEqual((check["status"], check["settled"]), ("close", False))
                self.assertTrue(check["label"].endswith("(flow not settled)"))
        lines = "\n".join(self.result.human_lines())
        self.assertIn("check 'Mach number (flow not settled)'", lines)
        self.assertIn("(not settled)", lines)
        types = [finding["type"] for finding in self.result.findings]
        self.assertIn("gas_flow_unsettled", types)
        self.assertFalse(any(kind.endswith("_close_to_limit") for kind in types))


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class LowSpeedLimit(unittest.TestCase):
    """0.5 m/s of air (Mach 0.0015, Re 140) through the cfd tests' tube: laminar walls, the incompressible pressure drop."""

    @classmethod
    def setUpClass(cls):
        from build123d import Align, Cylinder, Rotation, export_step

        from cadgen._internal.fea.compressible import AIR, sutherland

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        step = directory / "tube.step"
        along = (Align.CENTER, Align.CENTER, Align.MIN)
        export_step(Rotation(0, 90, 0) * (Cylinder(3.0, 16.0, align=along) - Cylinder(2.0, 16.0, align=along)), str(step))
        density, viscosity, speed = P_OUT / (R_AIR * T0), sutherland(AIR, T0), 0.5
        cls.mass = density * speed * math.pi * 0.002 ** 2
        incompressible = {"analysis": "cfd", "mesh": {"size_mm": 1.0},
                          "flow": {"kind": "internal", "fluid": {"density_kg_m3": density, "viscosity_Pa_s": viscosity},
                                   "inlets": [{"opening": "x_min", "velocity_m_s": speed}], "outlets": [{"opening": "x_max", "pressure_Pa": 0}]}}
        gas = {"analysis": "cfd_compressible", "mesh": {"size_mm": 1.0},
               "flow": {"kind": "internal", "gas": "air", "inlets": [{"opening": "x_min", "mass_flow_kg_s": cls.mass}],
                        "outlets": [{"opening": "x_max", "pressure_Pa": P_OUT}]}}
        from cadgen import fea

        with redirect_stderr(io.StringIO()):
            cls.cfd = fea.solve(step, directory / "cfd.glb", study=incompressible)
        cls.gas, _ = solve(step, directory / "gas.glb", gas)
        cls.extras, _ = glb_extras(cls.gas.glb)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_it_is_the_incompressible_flow_within_2_percent(self):
        summary = self.gas.summary
        self.assertEqual(summary["walls"], "no_slip")
        self.assertLess(summary["reynolds"]["value"], 2000)
        self.assertAlmostEqual(summary["mass_flow_kg_s"], self.mass, delta=1e-3 * self.mass)
        drop, expected = summary["pressure_drop_Pa"], self.cfd.summary["pressure_drop_Pa"]
        self.assertLess(abs(drop / expected - 1), 0.02, (drop, expected))
        self.assertTrue(any("nearly incompressible here, so the cfd analysis gives the same answer" in line
                            for line in self.extras["analysis"]["warnings"]))


def box_duct_step(directory: Path, side: float, length: float, wall: float = 1.0) -> Path:
    """A square passage through a block along x: sharp corners where the inlet meets the walls."""
    from build123d import Align, Box, export_step

    step = directory / "duct.step"
    along = (Align.MIN, Align.CENTER, Align.CENTER)
    export_step(Box(length, side + 2 * wall, side + 2 * wall, align=along) - Box(length, side, side, align=along), str(step))
    return step


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class BoxDuct(unittest.TestCase):
    """A square duct (sharp corners at its inlet) carries a gas flow."""

    def test_a_square_duct_solves(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            result, _ = solve(box_duct_step(directory, 4.0, 16.0), directory / "duct.glb",
                              {**nozzle_study(0.95), "mesh": {"size_mm": 1.5}})
        self.assertTrue(result.ok)
        self.assertGreater(result.summary["mass_flow_kg_s"], 0)
        self.assertGreater(result.summary["pressure_drop_Pa"], 0)


if __name__ == "__main__":
    unittest.main()
