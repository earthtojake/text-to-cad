"""The release version stamp has to reach every version field it owns.

`scripts/release/sync-version.mjs` can name several paths that are the SAME FILE: a mirrored
`apps/web/packages/...` entry is a symlink to the canonical package. Each target reads its file
before any write happens, so two targets stamping one file means the last write wins -- and a
mirror declaring fewer fields than the canonical target silently reverts the field only the
canonical one knows about.

That is not hypothetical: adding a package's version to `packages/core/package-lock.json`
without adding it to that file's two symlinked mirrors made the 0.4.10 release fail its own
version gate, after the bump and before anything was published.

Both halves of that failure are asserted below -- targets naming one file are merged, and no
first-party version field in a lockfile is left undeclared. The specific field that broke
0.4.10 is gone, and so are the vendored skill mirrors, so the guard is stated as the
property rather than as that one package's name.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import repo_path

SYNC_SCRIPT = repo_path("scripts", "release", "sync-version.mjs")


def _node(script: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        timeout=60,
    )
    if result.returncode != 0:
        raise AssertionError(f"node failed: {result.stderr.strip()}")
    return result.stdout


class VersionSyncMirrorTests(unittest.TestCase):
    def test_targets_naming_one_file_are_merged_into_one_write(self) -> None:
        """Two targets on the same real file become one target holding both field sets."""
        if not repo_path("apps", "web", "packages", "core").is_symlink():
            self.skipTest("not in the development symlink layout")
        # The script resolves target paths against the repo root, so the pair below has to be
        # real repo paths: the canonical lockfile and the mirror that symlinks to it.
        script = (
            "const { mergeTargetsByRealPath } = await import(%s);\n"
            "const merged = mergeTargetsByRealPath([\n"
            '  { path: "packages/core/package-lock.json",'
            ' fields: [["version"], ["packages", "", "version"]] },\n'
            '  { path: "apps/web/packages/core/package-lock.json", fields: [["version"]], required: false },\n'
            "]);\n"
            "console.log(JSON.stringify({ count: merged.length, fields: merged[0].fields,"
            " treatedAsRequired: merged[0].required !== false }));"
            % json.dumps(SYNC_SCRIPT.as_uri())
        )
        payload = json.loads(_node(script))
        self.assertEqual(1, payload["count"], "a symlinked mirror must not get its own write")
        self.assertIn(
            ["packages", "", "version"],
            payload["fields"],
            "the merged target must keep the field only the canonical target declared",
        )
        self.assertTrue(payload["treatedAsRequired"], "a required target keeps the file required")

    def test_every_lockfile_target_stamps_every_first_party_version(self) -> None:
        """The 0.4.10 failure, stated as the property rather than as one package name.

        A lockfile carries a version for the package itself and for each workspace package
        linked into it, all of which move with the release; every other version in the file
        belongs to a dependency and must not be touched. First-party entries are the ones
        outside `node_modules`. A release breaks when the file gains such an entry and the
        target does not gain the matching field, which is exactly what 0.4.10 hit.
        """
        targets = json.loads(
            _node(
                "const { jsonTargets } = await import(%s);\n"
                "console.log(JSON.stringify(jsonTargets));" % json.dumps(SYNC_SCRIPT.as_uri())
            )
        )
        lockfiles = [t for t in targets if t["path"].endswith("package-lock.json")]
        self.assertTrue(lockfiles, "expected at least one lockfile target")
        for target in lockfiles:
            path = repo_path(target["path"])
            if not path.is_file():
                self.assertFalse(target.get("required", True), f"{target['path']} is required but missing")
                continue
            declared = {tuple(field) for field in target["fields"]}
            entries = json.loads(path.read_text(encoding="utf-8")).get("packages", {})
            for name in entries:
                if "node_modules" in name:
                    continue
                with self.subTest(path=target["path"], entry=name or "<root>"):
                    self.assertIn(
                        ("packages", name, "version"),
                        declared,
                        f"{target['path']} would ship a stale version for {name or 'the root package'}",
                    )

    def test_a_file_with_a_version_and_a_pin_takes_both(self) -> None:
        """The Gemini extension is a JSON target and a pin target: stamping one must keep the other."""
        targets = json.loads(_node(
            "const { jsonTargets, pinTargets, bootstrapTargets, tomlTargets } = await import(%s);\n"
            "console.log(JSON.stringify([...jsonTargets.map((t) => t.path), ...pinTargets,"
            " ...bootstrapTargets.map((t) => t.path), ...tomlTargets]));"
            % json.dumps(SYNC_SCRIPT.as_uri())))
        self.assertIn("gemini-extension.json", targets)
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch).resolve()  # the script runs main() only when argv[1] is its real path
            for relative in {*targets, "scripts/release/sync-version.mjs"}:
                if repo_path(relative).is_file():
                    (root / relative).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(repo_path(relative), root / relative)
            # A skill names no release: it runs the `cad` command, and the release stamps nothing in it.
            skill = root / "skills/fixture/SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("Run `cad run model.py`. An older release used cadgen==0.1.0.\n", encoding="utf-8")
            (root / "VERSION").write_text("9.9.9\n", encoding="utf-8")
            result = subprocess.run(["node", str(root / "scripts/release/sync-version.mjs")],
                                    capture_output=True, text=True, timeout=120)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            manifest = json.loads((root / "gemini-extension.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["version"], "9.9.9")
            self.assertIn("cad-mcp==9.9.9", manifest["mcpServers"]["cad"]["args"])
            # The four distributions are the release, and the server and the alias pin the library at it.
            for project in ("cad", "cad-server", "cad-mcp", "aliases/cadgen"):
                text = (root / "packages" / project / "pyproject.toml").read_text(encoding="utf-8")
                self.assertIn('\nversion = "9.9.9"\n', text, project)
                if project not in ("cad", "cad-mcp"):
                    self.assertIn('"cad==9.9.9"', text, project)
                    self.assertNotRegex(text, r"cad==(?!9\.9\.9)", project)
            # The one-line installer falls back to the release it ships with, and pins nothing else:
            # its `cad-server==$version` is the release it found.
            installer = (root / "scripts/install/install.sh").read_text(encoding="utf-8")
            self.assertIn('\nCAD_VERSION="9.9.9"\n', installer)
            self.assertIn('--from "$requirement" cad "$verb"', installer)
            self.assertIn('requirement="cad-server==$version"', installer)
            self.assertIn('\n    $CadVersion = "9.9.9"\n', (root / "scripts/install/install.ps1").read_text(encoding="utf-8"))
            self.assertEqual(skill.read_text(encoding="utf-8"), "Run `cad run model.py`. An older release used cadgen==0.1.0.\n")
            # So does the turn-off command the privacy policy prints.
            self.assertIn("--from cad-server==9.9.9 cad telemetry off",
                          (root / "apps/docs/src/app/privacy-policy/page.tsx").read_text(encoding="utf-8"))
            # The README and the docs site's homepage are prose and no pin target: a pin there would
            # never be stamped.
            for page in ("README.md", "apps/docs/src/lib/content.ts"):
                self.assertNotRegex(repo_path(page).read_text(encoding="utf-8"), r"(?<![\w.-])(cadgen|cad(-server|-mcp)?(\[[a-z0-9_,.-]+\])?)==", page)
            # And the install page's Claude Desktop config and the installer it says the command runs.
            page = (root / "docs/install.md").read_text(encoding="utf-8")
            self.assertIn('"--from", "cad-mcp==9.9.9", "cad-mcp"', page)
            self.assertIn("--from cad-server==9.9.9 cad setup", page)

    def test_the_version_check_holds_the_installer_s_fallback_to_the_release(self) -> None:
        """check-version.sh refuses an installer script that would fall back to another release."""
        # The four distributions' pyprojects, which it checks too, as they are.
        projects = json.loads(_node("const { tomlTargets } = await import(%s);\nconsole.log(JSON.stringify(tomlTargets));"
                                    % json.dumps(SYNC_SCRIPT.as_uri())))
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch).resolve()
            for relative in ("scripts/release/check-version.sh", "scripts/release/release-tags.sh",
                             "scripts/release/unavailable-versions.txt", "scripts/install/install.sh", "scripts/install/install.ps1",
                             *projects):
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(repo_path(relative), root / relative)
            shutil.copy2(repo_path("VERSION"), root / "VERSION")
            check = [str(root / "scripts/release/check-version.sh")]
            passed = subprocess.run(check, capture_output=True, text=True, timeout=60)
            self.assertEqual(0, passed.returncode, passed.stdout + passed.stderr)
            (root / "VERSION").write_text("9.9.9\n", encoding="utf-8")
            stale = subprocess.run(check, capture_output=True, text=True, timeout=60)
            self.assertEqual(1, stale.returncode, stale.stdout + stale.stderr)
            released = repo_path("VERSION").read_text(encoding="utf-8").strip()
            for script in ("install.sh", "install.ps1"):
                self.assertIn(f"scripts/install/{script} falls back to {released}; expected 9.9.9", stale.stderr)

    def test_derived_metadata_is_synced_at_the_current_version(self) -> None:
        """The gate the release workflows run, at the version in VERSION."""
        result = subprocess.run(
            ["node", str(SYNC_SCRIPT), "--check"],
            capture_output=True,
            text=True,
            cwd=str(repo_path()),
            timeout=120,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
