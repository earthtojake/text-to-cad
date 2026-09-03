"""`main` is `develop` with versions stamped, requirements pinned, and ONLY models/
removed -- held by test, not prose.

The trim used to drop apps/, tests/, packages/ and requirements-dev.txt too. It no longer
does, and two things have to stay true now that those roots ship:

* no symlink may reach the published tree: Codex `plugin add` drops symlinks silently.
  The repository has no development symlinks left, so this is a fence, not a step;
* packages/ being present is not permission for a skill to import from it (the Skills
  CLI installs skills/<name> alone). scripts/github-workflows/check-publish-tree.sh
  keeps the reach check that used to live inline in release.yml, and adds the rest of
  the contract: models/ absent, the source roots present, and no LFS-tracked path
  outside the README media.

Both scripts run against a throwaway git repo shaped like a checkout.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PREPARE = REPO_ROOT / "scripts" / "release" / "prepare-publish-tree.sh"
CHECK = REPO_ROOT / "scripts" / "github-workflows" / "check-publish-tree.sh"
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"

LFS_POINTER = "version https://git-lfs.github.com/spec/v1\noid sha256:%s\nsize 12\n" % ("0" * 64)


def _run(script: Path, *args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(script), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env={**os.environ, "PUBLISH_TREE_ROOT": str(cwd)},
    )


class PublishTreeScriptsExist(unittest.TestCase):
    def test_scripts_exist_and_are_executable(self) -> None:
        for script in (PREPARE, CHECK):
            self.assertTrue(script.is_file(), f"missing {script}")
            self.assertTrue(os.access(script, os.X_OK), f"{script} is not executable")

    def test_only_models_is_removed(self) -> None:
        result = subprocess.run(
            ["bash", str(PREPARE), "--print-removed-roots"], capture_output=True, text=True, check=True
        )
        self.assertEqual(result.stdout.split(), ["models"])

    def test_release_workflow_prepares_pins_checks_then_commits_in_that_order(self) -> None:
        workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        positions = [
            workflow.index("scripts/release/prepare-publish-tree.sh"),
            workflow.index("scripts/release/pin-cadgen-requirements.sh"),
            workflow.index("scripts/github-workflows/check-publish-tree.sh"),
            workflow.index("Commit publish result"),
        ]
        self.assertEqual(positions, sorted(positions), "prepare -> pin -> check -> commit")

    def test_release_workflow_no_longer_hardcodes_a_trim_list(self) -> None:
        workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        self.assertNotRegex(
            workflow,
            r'removed_roots="[^"]*\b(apps|tests|packages|requirements-dev\.txt)\b',
            "the trim list lives in prepare-publish-tree.sh, and apps/, tests/, packages/ ship",
        )

    def test_no_tracked_symlink_exists_anywhere(self) -> None:
        """The repository carries no development symlinks, so none can reach main.

        The bundle used to materialize one (the cad-viewer skill's runtime) and
        prepare-publish-tree.sh dereferenced another (apps/viewer/packages/cadgen-js).
        Both are gone; a tracked symlink appearing again is a new publish hazard, and
        this names it before the release workflow does.
        """
        tracked = subprocess.run(
            ["git", "ls-files", "-s"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        ).stdout.splitlines()
        symlinks = sorted(line.split("\t", 1)[1] for line in tracked if line.startswith("120000 "))
        self.assertEqual(symlinks, [], "tracked symlinks would reach the publish tree")


class PublishTreeFixture(unittest.TestCase):
    """A throwaway git repo shaped like a bundled checkout of this repo."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        for script in (PREPARE, CHECK):
            target = self.root / script.relative_to(REPO_ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(script, target)
        self._write("VERSION", "9.9.9\n")
        self._write(".gitattributes", "*.step filter=lfs diff=lfs merge=lfs -text\nassets/** filter=lfs diff=lfs merge=lfs -text\n")
        self._write(".gitignore", "node_modules\ndist\n")
        self._write("models/part.step", "ISO-10303-21;\n")
        self._write("models/README.md", "fixtures\n")
        self._write("apps/viewer/package.json", "{}\n")
        self._write("apps/docs/package.json", "{}\n")
        self._write("packages/cadgen/pyproject.toml", "[project]\nname='cadgen'\n")
        self._write("packages/cadgen/src/cadgen/viewer/main.py", "print('viewer')\n")
        self._write("packages/cadgen-js/package.json", "{}\n")
        self._write("packages/cadgen-js/src/index.js", "export {}\n")
        self._write("packages/cadgen-js/node_modules/three/package.json", "{}\n")
        self._write("tests/python/test_x.py", "\n")
        self._write("requirements-dev.txt", "--editable ./packages/cadgen\n")
        self._write("docs/guide.md", "\n")
        self._write("assets/demo.gif", LFS_POINTER)
        self._write("skills/cad/SKILL.md", "# cad\n")
        self._write("skills/cad/requirements.txt", "cadgen==9.9.9\n")
        self._write("skills/cad-viewer/SKILL.md", "# cad-viewer\n")
        self._write("skills/cad-viewer/requirements.txt", "cadgen==9.9.9\n")

        self._git("init", "--quiet")
        self._git("config", "user.email", "t@example.com")
        self._git("config", "user.name", "t")
        self._git("add", "-A")
        self._git("commit", "--quiet", "-m", "bundled checkout")

    def _write(self, rel: str, body: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def _git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def _prepare(self) -> subprocess.CompletedProcess:
        return _run(self.root / "scripts" / "release" / "prepare-publish-tree.sh", cwd=self.root)

    def _check(self) -> subprocess.CompletedProcess:
        return _run(self.root / "scripts" / "github-workflows" / "check-publish-tree.sh", cwd=self.root)


class PrepareBehaviour(PublishTreeFixture):
    def test_removes_models_and_nothing_else(self) -> None:
        result = self._prepare()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse((self.root / "models").exists())
        for kept in ("apps", "packages", "tests", "requirements-dev.txt", "docs", "assets", "skills"):
            self.assertTrue((self.root / kept).exists(), f"{kept} must survive")

    def test_is_idempotent(self) -> None:
        self.assertEqual(0, self._prepare().returncode)
        second = self._prepare()
        self.assertEqual(0, second.returncode, second.stderr)


class CheckBehaviour(PublishTreeFixture):
    def test_fails_before_prepare_and_passes_after(self) -> None:
        before = self._check()
        self.assertEqual(1, before.returncode)
        self.assertIn("models/ must not be present", before.stderr)

        self._prepare()
        after = self._check()
        self.assertEqual(0, after.returncode, after.stderr + after.stdout)
        self.assertIn("allowed: assets/demo.gif", after.stdout)

    def test_a_missing_source_root_fails(self) -> None:
        self._prepare()
        shutil.rmtree(self.root / "tests")
        result = self._check()
        self.assertEqual(1, result.returncode)
        self.assertIn("missing from the publish tree: tests/python", result.stderr)

    def test_a_surviving_symlink_fails(self) -> None:
        self._prepare()
        (self.root / "skills" / "cad" / "lib").symlink_to("../../packages/cadgen-js")
        result = self._check()
        self.assertEqual(1, result.returncode)
        self.assertIn("symlink in the publish tree: skills/cad/lib", result.stderr)

    def test_an_lfs_tracked_path_outside_assets_fails(self) -> None:
        self._prepare()
        self._write("skills/cad/references/example.step", "ISO-10303-21;\n")
        result = self._check()
        self.assertEqual(1, result.returncode)
        self.assertIn("LFS-tracked path in the publish tree", result.stderr)
        self.assertIn("skills/cad/references/example.step", result.stderr)

    def test_an_lfs_pointer_file_is_caught_even_without_the_attribute(self) -> None:
        self._prepare()
        self._write("skills/cad/references/fixture.bin", LFS_POINTER)
        result = self._check()
        self.assertEqual(1, result.returncode)
        self.assertIn("skills/cad/references/fixture.bin", result.stderr)

    def test_a_skill_reaching_into_a_repo_root_fails(self) -> None:
        self._prepare()
        self._write("skills/cad/scripts/helper.py", "import sys\nsys.path.insert(0, '../../packages/cadgen/src')\n")
        result = self._check()
        self.assertEqual(1, result.returncode)
        self.assertIn("a skill reaches into a repo root", result.stderr)
        self.assertIn("skills/cad/scripts/helper.py", result.stderr)

    def test_skill_build_leftovers_fail(self) -> None:
        self._prepare()
        self._write("skills/cad/scripts/__pycache__/helper.cpython-313.pyc", "\x00")
        result = self._check()
        self.assertEqual(1, result.returncode)
        self.assertIn("skills/ ships build or test leftovers", result.stderr)


if __name__ == "__main__":
    unittest.main()
