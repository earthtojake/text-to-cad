from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from cadpy_fea import materials as materials_mod


def _has(mod: str) -> bool:
    try:
        __import__(mod)
    except Exception:  # noqa: BLE001
        return False
    return True


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/fea", *args],
        cwd=SKILL_ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


class FeaCliWrapperTests(unittest.TestCase):
    def test_help_runs_cleanly(self) -> None:
        result = _run("--help")
        self.assertEqual("", result.stderr)
        self.assertEqual(0, result.returncode)
        self.assertIn("usage: fea", result.stdout)

    def test_help_does_not_import_solver_stack(self) -> None:
        code = (
            "import sys; sys.path.insert(0, 'scripts'); "
            "import cadpy_fea.cli; "
            "print('ngsolve' in sys.modules); "
            "print('netgen' in sys.modules); "
            "print('OCP.OCP' in sys.modules)"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=SKILL_ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual("", result.stderr)
        self.assertEqual(0, result.returncode)
        self.assertEqual(["False", "False", "False"], result.stdout.strip().splitlines())

    def test_materials_lists_table(self) -> None:
        result = _run("materials", "--quiet")
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertIn("steel", payload["materials"])
        self.assertIn("pla", payload["materials"])

    def test_modal_without_solver_reports_install_hint(self) -> None:
        # Only meaningful when ngsolve is absent; otherwise skip.
        if _has("ngsolve"):
            self.skipTest("ngsolve installed")
        result = _run("modal", "missing.step", "--material", "steel")
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertIn("ngsolve", payload["errors"][0]["message"])


class MaterialMathTests(unittest.TestCase):
    def test_lame_parameters(self) -> None:
        steel = materials_mod.get_material("steel")
        lam, mu = steel.lame()
        # mu = E / (2(1+nu)) = 200e9 / 2.6
        self.assertAlmostEqual(mu, 200e9 / 2.6, delta=1e6)
        self.assertGreater(lam, 0)

    def test_pcb_composite_density_bounds(self) -> None:
        thin = materials_mod.pcb_composite_density(1.6e-3)
        thick = materials_mod.pcb_composite_density(3.2e-3)
        base = materials_mod.MATERIALS["fr4"].rho
        # More copper fraction in a thinner board => higher density.
        self.assertGreater(thin, thick)
        self.assertGreater(thin, base)
        self.assertLess(thick, thin)

    def test_unknown_material_raises(self) -> None:
        with self.assertRaises(KeyError):
            materials_mod.get_material("unobtanium")

    def test_table_covers_common_categories(self) -> None:
        categories = {m.category for m in materials_mod.MATERIALS.values()}
        for expected in ("metal", "plastic", "composite", "elastomer", "wood", "ceramic"):
            self.assertIn(expected, categories)
        # A representative spread across 3D printing, machining, and sheet metal.
        for key in ("pla", "petg", "tpu", "peek", "steel", "aluminum",
                    "titanium", "copper", "brass", "fr4", "acrylic"):
            self.assertIn(key, materials_mod.MATERIALS)
        self.assertGreaterEqual(len(materials_mod.MATERIALS), 30)

    def test_every_material_is_physically_valid(self) -> None:
        for name, m in materials_mod.MATERIALS.items():
            self.assertGreater(m.E, 0, name)
            self.assertGreater(m.rho, 0, name)
            self.assertGreaterEqual(m.nu, 0.0, name)
            self.assertLess(m.nu, 0.5, name)  # finite Lame parameters
            lam, mu = m.lame()
            self.assertGreater(mu, 0, name)
            self.assertGreater(m.zeta, 0, name)
            self.assertLess(m.zeta, 1.0, name)  # underdamped

    def test_damping_ordering_metals_ring_plastics_damp(self) -> None:
        # Metals should ring far longer than plastics/elastomers.
        self.assertLess(materials_mod.get_material("steel").zeta,
                        materials_mod.get_material("pla").zeta)
        self.assertLess(materials_mod.get_material("aluminum").zeta,
                        materials_mod.get_material("abs").zeta)
        self.assertLess(materials_mod.get_material("pla").zeta,
                        materials_mod.get_material("rubber").zeta)

    def test_aliases_resolve(self) -> None:
        self.assertIs(materials_mod.get_material("AL"), materials_mod.MATERIALS["aluminum"])
        self.assertIs(materials_mod.get_material("SS"), materials_mod.MATERIALS["stainless"])
        self.assertIs(materials_mod.get_material("pom"), materials_mod.MATERIALS["delrin"])
        self.assertIs(materials_mod.get_material("ti"), materials_mod.MATERIALS["titanium"])
        self.assertIs(materials_mod.get_material("Carbon Fiber"), materials_mod.MATERIALS["cfrp"])


@unittest.skipUnless(
    _has("ngsolve") and _has("netgen") and _has("build123d"),
    "modal FEA solver stack not installed",
)
class ModalSolveTests(unittest.TestCase):
    def test_cantilever_box_has_positive_modes(self) -> None:
        from build123d import Box, Pos, export_step

        with tempfile.TemporaryDirectory() as tmp:
            step = Path(tmp) / "beam.step"
            # 10 x 10 x 40 beam standing in +Z, clamped at the bottom face.
            part = Pos(0, 0, 20) * Box(10, 10, 40)
            export_step(part, str(step))
            result = _run(
                "modal", str(step), "--material", "steel",
                "--fixed", "bottom", "--modes", "3", "--quiet",
            )
            self.assertEqual(0, result.returncode, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"], payload)
            freqs = [m["frequencyHz"] for m in payload["modes"]]
            self.assertEqual(3, len(freqs))
            self.assertTrue(all(f > 0 for f in freqs), freqs)
            self.assertTrue(freqs == sorted(freqs), freqs)


if __name__ == "__main__":
    unittest.main()
