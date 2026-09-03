"""The publish tree must resolve cadgen from PyPI, not editable from a sibling.

A source checkout installs cadgen with `--editable ./<path>/packages/cadgen`,
which only resolves because the package sits beside the skill. An installed
skill has no such sibling, so the Release workflow rewrites every requirement to
`cadgen==<VERSION>` before committing the publish tree.

That rewrite used to live in `scripts/bundle/bundle-plugin.sh`, over the
generated `plugins/cad/skills` copy. When the plugin package moved to the repo
root that script was deleted and the pinning went with it — silently, because
nothing tested it. These tests exist so it cannot happen again.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "release" / "pin-cadgen-requirements.sh"
# What a skill's requirements.txt says on develop: the distribution, unpinned.
UNPINNED = "cadgen"
# With extras, which the pin must preserve -- dropping them silently uninstalls
# playwright from every published skill that renders.
UNPINNED_EXTRAS = "cadgen[snapshot]"


class PinScriptPresenceTest(unittest.TestCase):
    def test_script_exists_and_is_executable(self):
        self.assertTrue(SCRIPT.is_file(), f"missing {SCRIPT}")
        self.assertTrue(os.access(SCRIPT, os.X_OK), f"{SCRIPT} is not executable")

    def test_release_workflow_runs_it_before_the_publish_commit(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("scripts/release/pin-cadgen-requirements.sh", workflow)
        pin_at = workflow.index("scripts/release/pin-cadgen-requirements.sh")
        commit_at = workflow.index("Commit publish result")
        self.assertLess(pin_at, commit_at, "pinning must run before the publish commit")

    def test_checked_in_requirements_stay_unpinned(self):
        """A source checkout must NOT be pinned — the pin is publish-only.

        Two unpinned spellings are legal on develop, and both must resolve to the repo's
        own cadgen locally: `--editable <path>/packages/cadgen` for a skill that still
        vendors it, and the bare distribution name (optionally with extras) for one that
        installs it. Either way `cadgen==` must not appear in the tree, or a developer
        would silently install a released cadgen over their working copy.
        """
        checked = 0
        for req in sorted(REPO_ROOT.glob("skills/*/requirements.txt")):
            text = req.read_text(encoding="utf-8")
            if "cadgen" not in text:
                continue
            checked += 1
            rel = req.relative_to(REPO_ROOT)
            self.assertNotIn("cadgen==", text, f"{rel} must not be pinned in the source tree")
            self.assertTrue(
                any(line.strip().startswith("cadgen") for line in text.splitlines()),
                f"{rel} should name the cadgen distribution",
            )
        self.assertTrue(checked, "no skill requirements name cadgen")

    def test_the_viewer_client_has_no_python_requirements(self):
        # apps/viewer is the CAD Viewer's CLIENT; its backend is cadgen.viewer,
        # installed by `pip install cadgen`. A requirements.txt here would be a
        # second place to state that dependency, and the pin script would then
        # have to decide whether it is a skill (pin) or an app (floor) -- a
        # distinction that no longer exists.
        self.assertFalse((REPO_ROOT / "apps" / "viewer" / "requirements.txt").exists())

class PinScriptBehaviourTest(unittest.TestCase):
    """Run the real script against a throwaway tree shaped like the publish tree."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "VERSION").write_text("9.9.9\n", encoding="utf-8")
        (self.root / "scripts" / "release").mkdir(parents=True)
        shutil.copy2(SCRIPT, self.root / "scripts" / "release" / SCRIPT.name)

    def _write(self, rel: str, body: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def _run(self, *args):
        return subprocess.run(
            ["bash", str(self.root / "scripts" / "release" / SCRIPT.name), *args],
            capture_output=True,
            text=True,
            cwd=self.root,
        )

    def test_pins_the_distribution_to_the_canonical_version(self):
        target = self._write("skills/cad/requirements.txt", f"{UNPINNED}\nplaywright\n")
        result = self._run()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("cadgen==9.9.9\nplaywright\n", target.read_text(encoding="utf-8"))

    def test_extras_survive_pinning(self):
        """`cadgen[snapshot]==X`, not `cadgen==X`.

        Pinning to the bare name drops the extra, so a published rendering skill
        installs without playwright and fails on its first snapshot -- at the user,
        not here.
        """
        target = self._write("skills/urdf/requirements.txt", f"{UNPINNED_EXTRAS}\n")
        self._run()
        self.assertEqual("cadgen[snapshot]==9.9.9\n", target.read_text(encoding="utf-8"))

    def test_preserves_sibling_requirements(self):
        target = self._write("skills/dxf/requirements.txt", f"{UNPINNED}\nezdxf\nshapely\n")
        self._run()
        self.assertEqual("cadgen==9.9.9\nezdxf\nshapely\n", target.read_text(encoding="utf-8"))

    def test_pins_every_manifest_it_finds(self):
        a = self._write("skills/cad/requirements.txt", f"{UNPINNED}\n")
        b = self._write("skills/cad-viewer/requirements.txt", f"{UNPINNED}\n")
        c = self._write("skills/dxf/requirements.txt", f"{UNPINNED}\n")
        self._run()
        for path in (a, b, c):
            self.assertEqual("cadgen==9.9.9\n", path.read_text(encoding="utf-8"), path)

    def test_is_idempotent(self):
        target = self._write("skills/cad/requirements.txt", f"{UNPINNED}\n")
        self._run()
        second = self._run()
        self.assertEqual(0, second.returncode)
        self.assertEqual("cadgen==9.9.9\n", target.read_text(encoding="utf-8"))

    def test_check_mode_reports_without_writing(self):
        target = self._write("skills/cad/requirements.txt", f"{UNPINNED}\n")
        result = self._run("--check")
        self.assertEqual(1, result.returncode, "unpinned requirements must fail --check")
        self.assertIn("would pin", result.stdout)
        self.assertEqual(f"{UNPINNED}\n", target.read_text(encoding="utf-8"), "--check must not write")

    def test_check_mode_passes_once_pinned(self):
        self._write("skills/cad/requirements.txt", f"{UNPINNED}\n")
        self._run()
        self.assertEqual(0, self._run("--check").returncode)

    def test_skips_excluded_trees(self):
        vendored = self._write("node_modules/pkg/requirements.txt", f"{UNPINNED}\n")
        models = self._write("models/requirements.txt", f"{UNPINNED}\n")
        self._run()
        self.assertEqual(f"{UNPINNED}\n", vendored.read_text(encoding="utf-8"), "node_modules must be skipped")
        self.assertEqual(f"{UNPINNED}\n", models.read_text(encoding="utf-8"), "models must be skipped")

    def test_missing_version_is_an_error(self):
        (self.root / "VERSION").write_text("\n", encoding="utf-8")
        self._write("skills/cad/requirements.txt", f"{UNPINNED}\n")
        result = self._run()
        self.assertEqual(1, result.returncode)
        self.assertIn("Missing canonical release version", result.stderr)


if __name__ == "__main__":
    unittest.main()
