"""Decorator arguments are ordinary Python, evaluated when the module is imported.

``out=`` may be an f-string, a concatenation or a constant from ``lib/``; a
tolerance may come from a shared constant. Nothing is read off the source text,
and the values feeding the arguments are tracked like any other input.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

from tests.python.support.paths import REPO_ROOT, add_repo_path
from tests.python.support.tmp_root import temporary_directory

add_repo_path("packages/cadgen/src")

PYTHON = sys.executable

DIMS = """\
NAME = "plate_rev_b"
TOL = 0.02
"""

PLATE = """\
from cadgen import build123d as bd
from cadgen import step, stl
from lib.dims import NAME, TOL

FOLDER = "out"


@stl(out=f"{FOLDER}/{NAME}.stl", mesh_tolerance=TOL)
@step(out=FOLDER + "/" + NAME + ".step", mesh_tolerance=TOL * 2)
def plate():
    return bd.Box(20, 10, 2)


if __name__ == "__main__":
    plate()
"""


class DecoratorArgumentsAreEvaluated(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = temporary_directory(prefix="cadgen-decorator-args-")
        self.root = Path(self._tmp.name)
        self.src = self.root / "src"
        (self.src / "lib").mkdir(parents=True)
        (self.src / "lib" / "__init__.py").write_text("", encoding="utf-8")
        (self.src / "lib" / "dims.py").write_text(DIMS, encoding="utf-8")
        (self.src / "plate.py").write_text(PLATE, encoding="utf-8")
        self.env = dict(os.environ)
        self.env.update(
            {
                "CADGEN_DAEMON": "0",
                "CADGEN_CACHE_DIR": str(self.root / "store"),
                "PYTHONPATH": str(REPO_ROOT / "packages/cadgen/src"),
            }
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_py(self, *argv: str) -> subprocess.CompletedProcess:
        completed = subprocess.run(
            [PYTHON, *argv], cwd=str(self.src), env=self.env, capture_output=True, text=True, timeout=600
        )
        return completed

    def test_computed_arguments_decide_where_the_files_land(self) -> None:
        completed = self.run_py("plate.py")
        self.assertEqual(completed.returncode, 0, completed.stderr[-3000:])
        self.assertTrue((self.src / "out" / "plate_rev_b.step").is_file(), completed.stderr[-2000:])
        self.assertTrue((self.src / "out" / "plate_rev_b.stl").is_file(), completed.stderr[-2000:])
        rerun = self.run_py("plate.py")
        self.assertEqual(rerun.returncode, 0, rerun.stderr[-3000:])
        self.assertIn("current", rerun.stdout)

    def test_the_metadata_reader_reports_the_evaluated_values(self) -> None:
        from cadgen.metadata import parse_generator_metadata

        metadata = parse_generator_metadata(self.src / "plate.py")
        self.assertEqual(metadata.out_target, "out/plate_rev_b.step")
        self.assertAlmostEqual(metadata.mesh_tolerance, 0.04)
        (stl_decl,) = metadata.mesh_exports
        self.assertEqual(stl_decl.out, "out/plate_rev_b.stl")
        self.assertAlmostEqual(stl_decl.mesh_tolerance, 0.02)

    def test_a_constant_feeding_out_is_a_tracked_input(self) -> None:
        self.assertEqual(self.run_py("plate.py").returncode, 0)
        dims = self.src / "lib" / "dims.py"
        dims.write_text(DIMS.replace("plate_rev_b", "plate_rev_c"), encoding="utf-8")
        why = subprocess.run(
            [PYTHON, "-m", "cadgen.cli", "store", "why", "plate.py"],
            cwd=str(self.src), env=self.env, capture_output=True, text=True, timeout=300,
        )
        self.assertIn("STALE", why.stdout + why.stderr)
        self.assertIn("dims.py", why.stdout + why.stderr)
        rebuilt = self.run_py("plate.py")
        self.assertEqual(rebuilt.returncode, 0, rebuilt.stderr[-3000:])
        self.assertTrue((self.src / "out" / "plate_rev_c.step").is_file())

    def test_a_bad_argument_is_refused_at_import(self) -> None:
        bad = self.src / "bad.py"
        bad.write_text(
            "from cadgen import build123d as bd\nfrom cadgen import step\n\n\n@step(out=\"\")\ndef bad():\n"
            "    return bd.Box(1, 1, 1)\n\n\nif __name__ == '__main__':\n    bad()\n",
            encoding="utf-8",
        )
        completed = self.run_py("bad.py")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("out= must be a non-empty path string", completed.stderr)


if __name__ == "__main__":
    unittest.main()
