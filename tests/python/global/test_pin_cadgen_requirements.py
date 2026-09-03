"""Every skill pins cadgen to VERSION, and the release PR is what stamps the pins.

An installed skill resolves cadgen from PyPI (the Skills CLI copies skills/<name>
alone; no sibling packages/ is there to install editable), so the pin has to name
a release that exists. main is both the source tree and what installers clone,
so the pins live in it and move with every version bump.

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
# A bare distribution line -- what the pin script must rewrite (check-version.sh
# rejects it on main, where every skill pins cadgen==VERSION).
UNPINNED = "cadgen"
# With extras, which the pin must preserve -- dropping them silently uninstalls
# playwright from every published skill that renders.
UNPINNED_EXTRAS = "cadgen[snapshot]"


class PinScriptPresenceTest(unittest.TestCase):
    def test_script_exists_and_is_executable(self):
        self.assertTrue(SCRIPT.is_file(), f"missing {SCRIPT}")
        self.assertTrue(os.access(SCRIPT, os.X_OK), f"{SCRIPT} is not executable")

    def test_release_workflow_pins_in_the_release_pr(self):
        # The pin is stamped WITH the version bump, in the release PR against main,
        # so main never carries a VERSION its skill pins disagree with.
        workflow = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        bump_at = workflow.index("scripts/release/bump-version.sh")
        pin_at = workflow.index("scripts/release/pin-cadgen-requirements.sh")
        pr_at = workflow.index("Create or update release pull request")
        self.assertLess(bump_at, pin_at)
        self.assertLess(pin_at, pr_at, "pinning must happen before the release PR is committed")

    def test_checked_in_requirements_are_pinned_to_version(self):
        """main is the source branch AND what installers clone, so the pins live in it.

        Every skill naming cadgen pins exactly VERSION. The editable install a
        developer gets from requirements-dev.txt reports that same version
        (sync-version.mjs stamps pyproject.toml), so the pin is satisfied in a checkout
        too; `pip install -r skills/<s>/requirements.txt` on its own would fetch the
        release from PyPI, which is why requirements-dev.txt is the development door.
        check-version.sh enforces the same rule in CI.
        """
        version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        checked = 0
        for req in sorted(REPO_ROOT.glob("skills/*/requirements.txt")):
            text = req.read_text(encoding="utf-8")
            if "cadgen" not in text:
                continue
            checked += 1
            rel = req.relative_to(REPO_ROOT)
            pins = [line.strip() for line in text.splitlines() if line.strip().startswith("cadgen")]
            self.assertEqual(len(pins), 1, f"{rel} should name cadgen once: {pins}")
            self.assertRegex(pins[0], rf"^cadgen(\[[a-z0-9_,-]+\])?==\s*{version}$", f"{rel}: {pins[0]}")
        self.assertTrue(checked, "no skill requirements name cadgen")

    def test_the_viewer_client_has_no_python_requirements(self):
        # apps/viewer is the CAD Viewer's CLIENT; its backend is cadgen.viewer,
        # installed by `pip install cadgen`. A requirements.txt here would be a
        # second place to state that dependency, and the pin script would then
        # have to decide whether it is a skill (pin) or an app (floor) -- a
        # distinction that no longer exists.
        self.assertFalse((REPO_ROOT / "apps" / "viewer" / "requirements.txt").exists())

class PinScriptBehaviourTest(unittest.TestCase):
    """Run the real script against a throwaway tree shaped like the repo."""

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

    def test_a_stale_pin_is_moved_to_the_current_version(self):
        # A bump moves EVERY pin: a skill left at the previous release would name a
        # cadgen whose CLI the skill text no longer matches.
        target = self._write("skills/cad/requirements.txt", "cadgen[snapshot]==1.0.0\n")
        self.assertEqual(1, self._run("--check").returncode)
        self._run()
        self.assertEqual("cadgen[snapshot]==9.9.9\n", target.read_text(encoding="utf-8"))

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
