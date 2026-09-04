"""The cad skill's project template is the exemplar: a reader who copies it verbatim gets
a project that BUILDS — part, drawing, mesh-only part, mirrored pair,
sub-assembly and root — with every output landing where the template's `out=`
targets say, and with the store behaving as the skill describes (running the
root builds everything beneath it; a rerun is a no-op; `store why` sees the
frame's two children).

Built cold (`CADGEN_DAEMON=0`, transient workers) in a throwaway project with a
private store, exactly as an agent following the skill would in a fresh
workspace.
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

_FILE_BLOCK = re.compile(r"## `([^`]+)`\n\n```(?:python|markdown|gitignore)\n(.*?)```", re.S)


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
            "STEP/frame.step",
            "STEP/plate.step",
            "STEP/bracket_left.step",
            "STEP/bracket_right.step",
            "STL/standoff.stl",
        ):
            with self.subTest(output=relative):
                output = self.project / relative
                self.assertTrue(output.is_file(), f"{relative} was not written by the root build")
                self.assertGreater(output.stat().st_size, 0)
        # No model here declares kinematics, animation or a mesh beside its STEP.
        self.assertEqual(sorted(p.name for p in (self.project / "STEP").glob("*.json")), [])

        second = self.run_in_project("src/assembly.py")
        self.assertTrue(second.stdout.startswith("current "), f"the rerun was not a no-op:\n{second.stdout}")

        # Every child model is current on its own too, and the frame's record
        # pins exactly the two children its body called.
        for relative in ("src/frame.py", "src/plate.py", "src/standoff.py", "src/bracket_right.py"):
            with self.subTest(model=relative):
                run = self.run_in_project(relative)
                self.assertTrue(run.stdout.startswith("current "), run.stdout)
        why = self.run_in_project("-m", "cadgen.cli", "store", "why", "src/frame.py")
        self.assertIn("verdict current", why.stdout)
        self.assertIn("3 children (2)", why.stdout)
        self.assertIn("plate.py", why.stdout)
        self.assertIn("standoff.py", why.stdout)

    def test_the_drawing_builds(self) -> None:
        run = self.run_in_project("src/plate_drawing.py")
        self.assertTrue(run.stdout.startswith("built "), run.stdout)
        drawing = self.project / "DXF" / "plate_drawing.dxf"
        self.assertTrue(drawing.is_file())
        self.assertGreater(drawing.stat().st_size, 0)

    def test_the_finished_tree_names_every_output(self) -> None:
        """The template's closing tree is what the verify loop produces: every
        generated file it lists is one the scripts write."""
        template = TEMPLATE.read_text(encoding="utf-8")
        tree = template[template.index("## The finished tree") :]
        for name in ("assembly.step", "frame.step", "bracket_left.step", "bracket_right.step", "standoff.stl", "plate_drawing.dxf"):
            self.assertIn(name, tree, f"the finished tree lost {name}")
        self.assertNotIn(".step.json", tree.split("```")[1], "no template model writes a sidecar")


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
        self.assertIn("A mirrored part is its own model", text)
