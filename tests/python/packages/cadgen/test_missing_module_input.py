"""A module a model looks for and does not find is an input: when it appears, the model is stale.

An assembly that skips a part module that does not exist yet (``try: from gear
import gear``) builds without it. It used to stay current after gear.py was
written, since its closure held only the modules it imported: plausible-wrong
output at exit 0. Its closure now records every file that would have satisfied
the import, in each search root, as one that must stay absent, so writing
gear.py makes it stale, ``cadgen store why`` names the file, the next run builds
with the gear, and the run after that is current.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

CADGEN_SRC = add_repo_path("packages/cadgen/src")

ASSEMBLY = '''from cadgen import build123d as bd
from cadgen import step

try:
    from gear import gear
except ImportError:
    gear = None


@step
def assembly():
    base = bd.Box(30, 30, 2)
    if gear is None:
        return base
    return bd.Compound([base, bd.Pos(0, 0, 5) * gear()])


if __name__ == "__main__":
    assembly()
'''

GEAR = '''from cadgen import build123d as bd
from cadgen import step


@step
def gear():
    return bd.Cylinder(8, 4)
'''


class MissingModuleInput(unittest.TestCase):
    def setUp(self) -> None:
        scratch = generated_cad_directory(prefix="missing-module-")
        self.addCleanup(scratch.cleanup)
        self.project = Path(scratch.name).resolve()
        (self.project / "assembly.py").write_text(ASSEMBLY, encoding="utf-8")
        self.environment = {**os.environ, "CADGEN_DAEMON": "0", "CADGEN_CACHE_DIR": str(self.project / "store"),
                            "PYTHONPATH": str(CADGEN_SRC)}

    def _run(self, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, *argv], cwd=str(self.project), env=self.environment,
                              capture_output=True, text=True, timeout=600)

    def _build(self) -> str:
        completed = self._run("assembly.py", "--json")
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return json.loads(completed.stdout.strip().splitlines()[-1])["outcome"]

    def test_a_skipped_module_that_appears_makes_the_model_stale(self) -> None:
        self.assertEqual(self._build(), "built")
        alone = (self.project / "assembly.step").read_bytes()
        (self.project / "gear.py").write_text(GEAR, encoding="utf-8")
        why = self._run("-m", "cadgen.cli", "store", "why", "assembly.py")
        self.assertEqual(why.returncode, 1, why.stdout + why.stderr)
        self.assertIn("closure changed: gear.py appeared", why.stdout)
        self.assertEqual(self._build(), "built")
        self.assertNotEqual(alone, (self.project / "assembly.step").read_bytes(), "built with the gear")
        self.assertEqual(self._build(), "current")


if __name__ == "__main__":
    unittest.main()
