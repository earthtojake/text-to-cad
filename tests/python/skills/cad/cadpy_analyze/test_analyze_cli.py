from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[5] / "skills" / "cad"


def _has_build123d() -> bool:
    try:
        import build123d  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/analyze", *args],
        cwd=SKILL_ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _write_box(path: Path, x: float, y: float, z: float, at=(0.0, 0.0, 0.0)) -> None:
    from build123d import Box, Pos, export_step

    part = Pos(*at) * Box(x, y, z)
    export_step(part, str(path))


class AnalyzeCliWrapperTests(unittest.TestCase):
    def test_help_runs_cleanly(self) -> None:
        result = _run("--help")
        self.assertEqual("", result.stderr)
        self.assertEqual(0, result.returncode)
        self.assertIn("usage: analyze", result.stdout)

    def test_help_does_not_import_heavy_cad_modules(self) -> None:
        code = (
            "import sys; sys.path.insert(0, 'scripts'); "
            "import cadpy_analyze.cli; "
            "print('OCP.OCP' in sys.modules); "
            "print('build123d' in sys.modules)"
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
        self.assertEqual(["False", "False"], result.stdout.strip().splitlines())


@unittest.skipUnless(_has_build123d(), "build123d not importable")
class AnalyzeComputationTests(unittest.TestCase):
    def test_props_box_inertia(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            step = Path(tmp) / "box.step"
            _write_box(step, 10.0, 20.0, 30.0)
            result = _run("props", str(step), "--quiet")
            self.assertEqual(0, result.returncode, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertAlmostEqual(payload["volume"], 6000.0, places=2)
            inertia = payload["inertiaAboutCom"]
            # Solid box, unit density, about COM: Ixx = V/12 (y^2+z^2), etc.
            self.assertAlmostEqual(inertia["Ixx"], 650000.0, delta=50.0)
            self.assertAlmostEqual(inertia["Iyy"], 500000.0, delta=50.0)
            self.assertAlmostEqual(inertia["Izz"], 250000.0, delta=50.0)
            for off in ("Ixy", "Ixz", "Iyz"):
                self.assertAlmostEqual(inertia[off], 0.0, delta=1.0)

    def test_interference_overlapping_boxes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a.step"
            b = Path(tmp) / "b.step"
            _write_box(a, 10.0, 10.0, 10.0)
            _write_box(b, 10.0, 10.0, 10.0, at=(5.0, 0.0, 0.0))
            result = _run("interference", str(a), str(b), "--quiet")
            self.assertEqual(0, result.returncode, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["interferes"])
            self.assertAlmostEqual(payload["volume"], 500.0, delta=5.0)

    def test_clearance_separated_boxes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a.step"
            b = Path(tmp) / "b.step"
            _write_box(a, 10.0, 10.0, 10.0)
            _write_box(b, 10.0, 10.0, 10.0, at=(15.0, 0.0, 0.0))
            result = _run("clearance", str(a), str(b), "--quiet")
            self.assertEqual(0, result.returncode, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual("apart", payload["status"])
            self.assertAlmostEqual(payload["clearance"], 5.0, delta=0.05)

    def test_section_box_area(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            step = Path(tmp) / "box.step"
            _write_box(step, 10.0, 20.0, 30.0)
            result = _run("section", str(step), "--axis", "z", "--slices", "5", "--quiet")
            self.assertEqual(0, result.returncode, result.stderr)
            payload = json.loads(result.stdout)
            # Constant 10x20 cross-section along z.
            self.assertAlmostEqual(payload["minArea"], 200.0, delta=2.0)
            self.assertAlmostEqual(payload["maxArea"], 200.0, delta=2.0)


if __name__ == "__main__":
    unittest.main()
