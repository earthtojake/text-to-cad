"""Build the documented minimal part and assembly starters in an isolated store.

The assembly must build its children, preserve their placements and be current
on rerun. The part starter must also work independently.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path, repo_path

CADGEN_SRC = add_repo_path("packages/cadgen/src")

SKILL = repo_path("skills/cad/references/project-layout.md")
TEMPLATE = repo_path("skills/cad/references/project-template.md")

_FILE_BLOCK = re.compile(r"```python\n# (src/[\w/]+\.py)\n(.*?)```", re.S)


def _template_files() -> dict[str, str]:
    files = dict(_FILE_BLOCK.findall(TEMPLATE.read_text(encoding="utf-8")))
    assert "src/assembly.py" in files, "the template lost its root assembly"
    return files


class TheTemplateBuilds(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="cad-project-template-")
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name).resolve()
        for relative, source in _template_files().items():
            target = self.project / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding="utf-8")
        self.environment = {
            **os.environ,
            "CADGEN_DAEMON": "0",
            "CADGEN_COMPONENT_WORKERS": "1",
            "CADGEN_CACHE_DIR": str(self.project / "store"),
            "PYTHONPATH": str(CADGEN_SRC),
        }

    def run_in_project(self, *argv: str) -> subprocess.CompletedProcess:
        completed = subprocess.run(
            [sys.executable, *argv],
            cwd=str(self.project),
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=900,
        )
        self.assertEqual(completed.returncode, 0, f"{' '.join(argv)} failed:\n{completed.stdout}\n{completed.stderr}")
        return completed

    def test_the_root_builds_everything_beneath_it(self) -> None:
        first = self.run_in_project("src/assembly.py")
        self.assertTrue(first.stdout.startswith("built "), first.stdout)
        for relative in (
            "STEP/assembly.step",
            "STEP/plate.step",
            "STEP/standoff.step",
        ):
            with self.subTest(output=relative):
                output = self.project / relative
                self.assertTrue(output.is_file(), f"{relative} was not written by the root build")
                self.assertGreater(output.stat().st_size, 0)
        # No model here declares kinematics, materials or animation.
        self.assertEqual(sorted(p.name for p in (self.project / "STEP").glob("*.json")), [])

        self.run_in_project("-c", """
from cadgen import read_scene
scene = read_scene("STEP/assembly.step")
plate = scene.resolve("#plate").shape().bounding_box()
for label in ("#standoff_left", "#standoff_right"):
    post = scene.resolve(label).shape().bounding_box()
    assert abs(post.min.Z - plate.max.Z) < 1e-6, (label, post.min.Z, plate.max.Z)
""")

        second = self.run_in_project("src/assembly.py")
        self.assertTrue(second.stdout.startswith("current "), f"the rerun was not a no-op:\n{second.stdout}")

        # The assembly record is current and pins exactly the two children its
        # body called (per-child records being current is test_models_per_file's).
        why = self.run_in_project("-m", "cadgen.cli", "store", "why", "src/assembly.py")
        self.assertIn("verdict current", why.stdout)
        self.assertIn("3 children (2)", why.stdout)
        self.assertIn("plate.py", why.stdout)
        self.assertIn("standoff.py", why.stdout)

    def test_the_part_builds_without_the_assembly_files(self) -> None:
        (self.project / "src/standoff.py").unlink()
        (self.project / "src/assembly.py").unlink()
        run = self.run_in_project("src/plate.py")
        self.assertTrue(run.stdout.startswith("built "), run.stdout)
        self.assertTrue((self.project / "STEP/plate.step").is_file())
        self.assertEqual(len(list((self.project / "STEP").glob("*.step"))), 1)


class TheSkillTeachesTheContract(unittest.TestCase):
    def test_no_retired_mechanism_is_taught(self) -> None:
        for path in (SKILL, TEMPLATE):
            text = path.read_text(encoding="utf-8")
            for word in ("Memo", "memo(", "lock", "Makefile", "cadgen build", "render package", "-o "):
                self.assertNotIn(word, text, f"{path.name} still teaches {word!r}")

    def test_the_skill_states_pull_semantics(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("running the root is the\nwhole build", text)
        self.assertIn("does NOT rebuild the assemblies", text)
        self.assertIn("models by result, constants by value, functions by file", text)
