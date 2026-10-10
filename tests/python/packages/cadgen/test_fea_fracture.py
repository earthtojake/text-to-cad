"""Fracture: the crack the study describes, the materials' toughness, Paris's law, the benchmarks and the ladder.

Benchmarks (linear-elastic fracture mechanics against the handbook closed forms):
- a centre crack (2a = 10 mm) through a 100 mm wide plate in tension, held in
  plane strain: K = σ √(πa) · √(sec(πa/W)) (Feddersen's finite-width correction,
  1.006 here), within 5 %;
- a single edge crack (a/W = 0.05) in tension: Tada's
  K = σ √(πa) (1.12 − 0.231 (a/W) + 10.55 (a/W)² − 21.72 (a/W)³ + 30.39 (a/W)⁴),
  which is 1.12 σ √(πa) within 1.1 % at this a/W, within 5 %;
- Paris's law integrated by the engine against the closed form for a constant
  geometry factor (Norton eq. 6.4b), within 2 %, on its own and on a solved crack;
- the ladder: a tiny budget solves a symmetric quarter (the fronts mirrored and
  joined) and a coarse pass with the front kept fine, each said everywhere, K
  within 7 %.

The plates are build123d boxes written to a temporary STEP. Parse, Paris and
material tests are stdlib only; the solves need the fea extra.
"""

from __future__ import annotations

import io
import json
import math
import re
import struct
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from tests.python.support import markdown
from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.fea.analyses import REGISTRY, get_analysis  # noqa: E402
from cadgen._internal.fea.crack import paris_life, paris_life_closed_form, parse_crack  # noqa: E402
from cadgen._internal.fea.materials import MATERIALS, NONE_REASONS, material_from_spec  # noqa: E402
from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402
from cadgen._internal.fea.study import parse_study  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

REFERENCE = Path(__file__).resolve().parents[4] / "skills" / "fea" / "references"
EDGE = {"kind": "edge", "face": "#o1.f1", "at_mm": [0, 0, 1], "normal": [0, 1, 0], "size_mm": 5}


def _study(**more) -> dict:
    return {"analysis": "fracture", "material": "aluminum-7075-t6", "fixtures": [{"faces": ["#o1.f3"]}],
            "loads": [{"faces": ["#o1.f4"], "type": "pressure", "pressure_MPa": -100}], "crack": EDGE, **more}


class StudyFile(unittest.TestCase):
    def test_it_is_registered_built_tier_3_cracks(self):
        entry = REGISTRY["fracture"]
        self.assertEqual((entry.tier, entry.word, entry.planned), (3, "Cracks", False))
        analysis = get_analysis("fracture")
        self.assertEqual(analysis.ladder, ("iterative", "local_refine", "defeature", "symmetry"))
        self.assertTrue(analysis.isotropic_only)
        self.assertEqual([check.kind for check in analysis.checks], ["fracture", "crack_life", "stress", "displacement"])

    def test_it_takes_static_fixtures_and_loads_and_a_crack(self):
        parsed = parse_study(_study())
        inputs = parsed.inputs
        self.assertEqual(inputs.face_refs, ("#o1.f3", "#o1.f4", "#o1.f1"))
        self.assertEqual((inputs.crack.kind, inputs.crack.size_mm, inputs.crack.normal), ("edge", 5.0, (0.0, 1.0, 0.0)))
        self.assertEqual(parsed.checks, ({"kind": "fracture", "margin": 1.5},))
        self.assertIsNone(inputs.growth)
        grown = parse_study(_study(growth={"load_ratio": 0.1}, material={"name": "steel", "fracture_toughness_MPa_sqrt_m": 50},
                                   view={"checks": [{"kind": "fracture"}, {"kind": "crack_life", "cycles": 1e5}]}))
        self.assertEqual(grown.inputs.growth.load_ratio, 0.1)
        self.assertEqual(grown.checks[1], {"kind": "crack_life", "cycles": 1e5, "margin": 2.0})

    def test_every_kind_parses(self):
        by_plane = {**{key: value for key, value in EDGE.items() if key != "normal"}, "plane": "xz"}
        self.assertEqual(parse_crack(by_plane).normal, (0.0, 1.0, 0.0))
        surface = parse_crack({**EDGE, "kind": "surface", "length_mm": 12})
        self.assertEqual((surface.kind, surface.length_mm), ("surface", 12.0))
        through = parse_crack({**EDGE, "kind": "through", "along": [1, 0, 0]})
        self.assertEqual(through.along, (1.0, 0.0, 0.0))
        embedded = parse_crack({"kind": "embedded", "at_mm": [0, 0, 0], "normal": [0, 0, 2], "size_mm": 1})
        self.assertEqual((embedded.face, embedded.normal), (None, (0.0, 0.0, 1.0)))

    def test_the_errors_say_what_to_give(self):
        cases = [
            ({k: v for k, v in _study().items() if k != "crack"}, "study.crack: a fracture study describes its crack"),
            (_study(crack={**EDGE, "kind": "notch"}), "crack.kind"),
            (_study(crack={k: v for k, v in EDGE.items() if k != "face"}), "crack.face: the face the crack opens from"),
            (_study(crack={**EDGE, "length_mm": 3}), "crack.length_mm: goes with a surface or embedded crack"),
            (_study(crack={**EDGE, "plane": "xy"}), 'give the crack plane as "normal"'),
            (_study(crack={**EDGE, "kind": "embedded"}), "an embedded crack opens from no face"),
            (_study(crack={**EDGE, "kind": "through", "along": [0, 1, 0]}), "crack.along: must lie in the crack plane"),
            (_study(view={"checks": [{"kind": "crack_life", "cycles": 10}]}), "a crack_life check needs a growth block"),
            (_study(growth={"load_ratio": 1}), "growth.load_ratio"),
            (_study(growth={"paris_C": 1e-11}), "give paris_C and paris_m together"),
            (_study(material="steel"), "fracture studies need the fracture toughness K_IC, and Steel (structural, generic) has none"),
            (_study(material={"name": "aluminum-7075-t6"}, growth={}), "add paris_C to the material object"),
        ]
        for study, fragment in cases:
            with self.subTest(fragment=fragment), self.assertRaises(ValueError) as caught:
                parse_study(study)
            self.assertIn(fragment, str(caught.exception))

    def test_a_study_judged_by_displacement_alone_needs_no_toughness(self):
        parsed = parse_study(_study(material="steel", view={"checks": [{"kind": "displacement", "limit_mm": 1}]}))
        self.assertNotIn("fracture_toughness", parsed.inputs.material_needs)

    def test_words(self):
        from cadgen._internal.fea.analyses.fracture import crack_words, point_words

        self.assertEqual(crack_words({"kind": "edge", "size_mm": 2, "face": "#o1.f4"}, "face 4"), "2 mm edge crack on face 4")
        self.assertEqual(crack_words({"kind": "surface", "size_mm": 1.5, "length_mm": 6}, "face 4"),
                         "1.5 mm deep surface crack, 6 mm long, on face 4")
        self.assertEqual(crack_words({"kind": "through", "size_mm": 5}, "face 6"), "10 mm through crack across face 6")
        self.assertEqual(crack_words({"kind": "embedded", "size_mm": 1}), "2 mm embedded crack")
        self.assertEqual(point_words("surface", end=False, deepest=True), "the deepest point")
        self.assertEqual(point_words("surface", end=True, deepest=False), "the surface")


class Materials(unittest.TestCase):
    """Every toughness and Paris constant in the table is in materials.md's Fracture table with a source; the rest say why not."""

    def _rows(self) -> dict[str, list[str]]:
        text = (REFERENCE / "materials.md").read_text(encoding="utf-8")
        section = markdown.section(text, "## Fracture")
        rows = {}
        for line in section.splitlines():
            match = re.match(r"\|\s*`([a-z0-9-]+)`", line)
            if match:
                rows[match.group(1)] = [cell.strip() for cell in line.strip().strip("|").split("|")][1:]
        return rows

    def test_the_reference_gives_the_tables_numbers_and_sources(self):
        rows = self._rows()
        self.assertEqual(set(rows), set(MATERIALS))
        for key, material in MATERIALS.items():
            for column, attribute in enumerate(("fracture_toughness", "paris_C", "paris_m")):
                with self.subTest(material=key, property=attribute):
                    cell = rows[key][column]
                    value = getattr(material, attribute)
                    if value is None:
                        self.assertTrue(cell.startswith("none"))
                        self.assertIn((key, attribute), NONE_REASONS)
                    else:
                        self.assertAlmostEqual(float(cell) / value, 1.0, places=9)
                        self.assertTrue(rows[key][3], "a value with no source")

    def test_the_sourced_values(self):
        self.assertEqual([MATERIALS[key].fracture_toughness for key in ("aluminum-6061-t6", "aluminum-7075-t6", "titanium-6al-4v")],
                         [29.0, 20.0, 75.0])
        self.assertEqual((MATERIALS["steel"].paris_C, MATERIALS["steel"].paris_m), (6.9e-12, 3.0))
        self.assertEqual((MATERIALS["stainless-304"].paris_C, MATERIALS["stainless-304"].paris_m), (5.6e-12, 3.25))
        for key in ("abs", "pla", "petg", "nylon-pa12"):
            self.assertIsNone(MATERIALS[key].fracture_toughness)

    def test_the_material_object_gives_them(self):
        steel = material_from_spec({"name": "steel", "fracture_toughness_MPa_sqrt_m": 50, "paris_C": 1e-11, "paris_m": 3.1})
        self.assertEqual((steel.fracture_toughness, steel.paris_C, steel.paris_m), (50.0, 1e-11, 3.1))
        self.assertEqual(steel.as_dict()["fracture_toughness_MPa_sqrt_m"], 50.0)


class ParisLaw(unittest.TestCase):
    def test_the_integration_meets_the_closed_form_for_a_constant_geometry_factor(self):
        # A centre crack, Y = 1, Δσ = 90 MPa (R = 0.1 of 100 MPa), steel's Paris fit, from 2 mm to K = 40 MPa√m.
        for m, C in ((3.0, 6.9e-12), (3.25, 5.6e-12), (2.0, 1e-10)):
            with self.subTest(m=m):
                a0, K0, toughness = 2.0, 100.0 * math.sqrt(math.pi * 0.002), 40.0
                life = paris_life(K0, a0, toughness, C, m, load_ratio=0.1)
                closed = paris_life_closed_form(90.0, 1.0, a0, life["critical_mm"], C, m)
                self.assertAlmostEqual(life["critical_mm"], a0 * (toughness / K0) ** 2, places=9)
                self.assertLess(abs(life["cycles"] / closed - 1.0), 0.02)

    def test_a_reversing_load_grows_on_its_tension_only_and_a_stop_size_ends_it_early(self):
        tension = paris_life(10.0, 1.0, 30.0, 6.9e-12, 3.0, load_ratio=0.0)
        self.assertAlmostEqual(paris_life(10.0, 1.0, 30.0, 6.9e-12, 3.0, load_ratio=-1.0)["cycles"], tension["cycles"])
        stopped = paris_life(10.0, 1.0, 30.0, 6.9e-12, 3.0, final_mm=2.0)
        self.assertLess(stopped["cycles"], tension["cycles"])
        self.assertEqual(stopped["final_mm"], 2.0)


def _glb(path: Path) -> dict:
    raw = path.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    return json.loads(raw[20:20 + length])


def _plate(directory: Path, name: str, width: float, height: float, thickness: float, *, centred: bool):
    """A plate written to a STEP, and its faces by outward normal ("+x", "-y", ...)."""
    from build123d import Align, Box, export_step

    from cadgen import fea

    step = directory / f"{name}.step"
    align = (Align.CENTER if centred else Align.MIN, Align.CENTER, Align.MIN)
    export_step(Box(width, height, thickness, align=align), str(step))
    faces = {}
    for face in fea.faces(step).faces:
        axis = max(range(3), key=lambda k: abs(face.normal[k]))
        faces[("+" if face.normal[axis] > 0 else "-") + "xyz"[axis]] = face.ref
    return step, faces


def _solve(step: Path, out: Path, study: dict):
    from cadgen import fea

    with redirect_stderr(io.StringIO()):
        return fea.solve(step, out, study=study)


SIGMA, W, HEIGHT, T, A = 100.0, 100.0, 200.0, 2.0, 5.0


def _tension(faces: dict, rollers: tuple[str, ...], crack: dict, **more) -> dict:
    """Tension σ on +y, held on rollers (one fixture: their reactions are not counted twice), plane strain through z."""
    return {"analysis": "fracture", "material": "aluminum-7075-t6", "mesh": {"size_mm": 8.0},
            "fixtures": [{"type": "roller", "faces": [faces[key] for key in rollers]}],
            "loads": [{"type": "pressure", "faces": [faces["+y"]], "pressure_MPa": -SIGMA}], "crack": crack, **more}


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class CentreCrack(unittest.TestCase):
    """2a = 10 mm through a 100 mm wide plate, plane strain (rollers on both faces): K = σ√(πa)·√(sec(πa/W))."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        cls.step, cls.faces = _plate(directory, "centre", W, HEIGHT, T, centred=True)
        crack = {"kind": "through", "face": cls.faces["+z"], "at_mm": [0, 0, T / 2], "normal": [0, 1, 0], "size_mm": A}
        cls.study = _tension(cls.faces, ("-y", "-z", "+z", "-x", "+x"), crack,
                             growth={"load_ratio": 0.1, "paris_C": 6.9e-12, "paris_m": 3.0},
                             view={"checks": [{"kind": "fracture"}, {"kind": "crack_life", "cycles": 1e5}]})
        cls.result = _solve(cls.step, directory / "centre.fea.glb", cls.study)
        cls.extras = _glb(cls.result.glb)["meshes"][0]["extras"]
        cls.sidecar = json.loads(cls.result.sidecar.read_text(encoding="utf-8"))
        cls.directory = directory

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_K_meets_the_finite_width_closed_form(self):
        expected = SIGMA * math.sqrt(math.pi * A / 1000.0) * math.sqrt(1.0 / math.cos(math.pi * A / W))
        summary = self.result.summary
        stations = [station["K_I"] for station in summary["front"]]
        self.assertEqual(len({station["front"] for station in summary["front"]}), 2)  # both tips
        self.assertLess(abs(sum(stations) / len(stations) / expected - 1.0), 0.05)
        self.assertLess(abs(summary["K_max_MPa_sqrt_m"] / expected - 1.0), 0.05)
        for station in summary["front"]:
            self.assertLess(abs(station["K_II"]) + abs(station["K_III"]), 0.02 * expected)
            # Mode I alone: the domain J is K_I² / E' (plane strain), within 2 %.
            E, nu = MATERIALS["aluminum-7075-t6"].E, MATERIALS["aluminum-7075-t6"].nu
            K_from_J = math.sqrt(station["J_N_per_mm"] * E / (1 - nu * nu) / 1000.0)
            self.assertLess(abs(K_from_J / station["K_I"] - 1.0), 0.02)
        self.assertLess(summary["domain_change_percent"], 5.0)

    def test_the_check_the_life_and_the_paris_closed_form(self):
        fracture, life = self.result.summary["checks"]
        K = self.result.summary["K_max_MPa_sqrt_m"]
        self.assertEqual((fracture["kind"], fracture["unit"], fracture["limit"], fracture["status"]), ("fracture", "MPa√m", 20.0, "passes"))
        self.assertAlmostEqual(fracture["ratio"], K / 20.0, places=4)
        self.assertEqual(fracture["point"], "mid-front")
        growth = self.result.summary["growth"]
        Y = K / (SIGMA * math.sqrt(math.pi * A / 1000.0))
        closed = paris_life_closed_form(0.9 * SIGMA, Y, A, growth["critical_mm"], 6.9e-12, 3.0)
        self.assertLess(abs(growth["cycles"] / closed - 1.0), 0.02)
        self.assertEqual((life["kind"], life["need"], life["status"]), ("crack_life", 1e5, "passes"))
        self.assertEqual(life["life"], growth["cycles"])

    def test_the_glb_and_sidecar_carry_the_crack(self):
        self.assertEqual(self.extras["analysis"]["type"], "fracture")
        self.assertEqual(self.extras["analysis"]["word"], "Cracks")
        crack = self.extras["crack"]
        self.assertEqual(crack["words"], "10 mm through crack across " + self.faces["+z"])
        self.assertEqual(len(crack["front_mm"]), len(self.result.summary["front"]))
        self.assertEqual(self.extras["study"]["crack"]["face"], self.faces["+z"])
        self.assertEqual(self.extras["study"]["growth"], {"load_ratio": 0.1, "paris_C": 6.9e-12, "paris_m": 3.0})
        self.assertEqual([field["field"] for field in self.extras["fields"]], ["von_mises", "displacement"])
        curves = self.sidecar["curves"]
        self.assertEqual(set(curves), {"K_I", "K_II", "K_III"})
        self.assertEqual((curves["K_I"]["x_unit"], curves["K_I"]["y_unit"]), ("mm", "MPa√m"))
        self.assertEqual(len(curves["K_I"]["y"]), len(self.result.summary["front"]))
        lines = self.result.human_lines()
        self.assertTrue(any(line.startswith("K ") and "toughness 20 MPa√m" in line for line in lines), lines)
        self.assertTrue(any(line.startswith("crack growth (Paris") for line in lines), lines)

    def test_the_crack_opens(self):
        # The duplicated faces move apart: the largest displacement is at the crack's faces, not the loaded end alone.
        self.assertGreater(self.result.summary["max_displacement_mm"], 0.0)
        self.assertFalse([finding for finding in self.result.findings if finding["severity"] == "error"])


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class EdgeCrack(unittest.TestCase):
    """a/W = 0.05 from the edge of a plate in tension: Tada's F(a/W), which is 1.12 for a small crack."""

    def test_K_meets_the_edge_crack_closed_form(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            step, faces = _plate(directory, "edge", W, HEIGHT, T, centred=False)
            crack = {"kind": "edge", "face": faces["-x"], "at_mm": [0, 0, T / 2], "normal": [0, 1, 0], "size_mm": A}
            result = _solve(step, directory / "edge.fea.glb", _tension(faces, ("-y", "-z", "+z", "+x"), crack))
        x = A / W
        tada = 1.12 - 0.231 * x + 10.55 * x ** 2 - 21.72 * x ** 3 + 30.39 * x ** 4
        nominal = SIGMA * math.sqrt(math.pi * A / 1000.0)
        K = result.summary["K_max_MPa_sqrt_m"]
        self.assertLess(abs(K / (tada * nominal) - 1.0), 0.05)
        self.assertLess(abs(K / (1.12 * nominal) - 1.0), 0.05)
        self.assertEqual(result.summary["crack"]["words"], f"5 mm edge crack on {faces['-x']}")


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Ladder(unittest.TestCase):
    """A tiny budget: the symmetric quarter and the coarse pass, each said everywhere, K still within 7 %."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls._tmp.name)
        cls.step, cls.faces = _plate(cls.directory, "ladder", W, HEIGHT, T, centred=True)
        cls.crack = {"kind": "through", "face": cls.faces["+z"], "at_mm": [0, 0, T / 2], "normal": [0, 1, 0], "size_mm": A}
        cls.expected = SIGMA * math.sqrt(math.pi * A / 1000.0) * math.sqrt(1.0 / math.cos(math.pi * A / W))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _run(self, name: str, allow: list[str], size: float):
        study = _tension(self.faces, ("-y", "-z", "+z", "-x", "+x"), self.crack,
                         mesh={"size_mm": size}, fit={"memory_GB": 0.05, "seconds": 0.5, "allow": allow})
        return _solve(self.step, self.directory / f"{name}.fea.glb", study)

    def _said(self, result, rung: str) -> dict:
        self.assertTrue(result.ok)
        step = next(step for step in result.fit if step["rung"] == rung)
        self.assertEqual(_glb(result.glb)["meshes"][0]["extras"]["fit"], list(result.fit))
        self.assertEqual(json.loads(result.sidecar.read_text(encoding="utf-8"))["fit"], list(result.fit))
        self.assertIn(f"adapted: {step['words']}" + (f" ({step['accuracy']})" if step["accuracy"] else ""), result.human_lines())
        self.assertIn(f"fit_{rung}", [finding["type"] for finding in result.findings if finding["severity"] == "info"])
        return step

    def test_symmetry_solves_a_quarter_and_joins_the_fronts(self):
        result = self._run("quarter", ["symmetry"], 4.0)
        step = self._said(result, "symmetry")
        self.assertIn("one quarter", step["words"])
        self.assertEqual({plane["axis"] for plane in step["detail"]["planes"]}, {"x", "z"})  # never the crack's own plane
        front = result.summary["front"]
        self.assertEqual(len({station["front"] for station in front}), 2)
        for station in front:
            self.assertLess(abs(station["K_I"] / self.expected - 1.0), 0.07)

    def test_local_refine_keeps_the_front_fine(self):
        result = self._run("coarse", ["local_refine"], 2.0)
        step = self._said(result, "local_refine")
        self.assertIn("the crack front is", step["words"])
        self.assertIn("between the coarse and the refined pass", step["accuracy"])
        self.assertLess(abs(result.summary["K_max_MPa_sqrt_m"] / self.expected - 1.0), 0.07)


if __name__ == "__main__":
    unittest.main()
