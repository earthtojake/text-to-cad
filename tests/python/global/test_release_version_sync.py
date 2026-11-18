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
        """A pyproject is a TOML target and a pin target: stamping one must keep the other."""
        targets = json.loads(_node(
            "const { jsonTargets, pinTargets, tomlTargets, lockTargets } = await import(%s);\n"
            "console.log(JSON.stringify([...jsonTargets.map((t) => t.path), ...pinTargets, ...tomlTargets,"
            " ...lockTargets.map((t) => t.path)]));"
            % json.dumps(SYNC_SCRIPT.as_uri())))
        self.assertIn("codex.mcp.json", targets)
        self.assertIn("uv.lock", targets)
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch).resolve()  # the script runs main() only when argv[1] is its real path
            for relative in {*targets, "scripts/release/sync-version.mjs"}:
                if repo_path(relative).is_file():
                    (root / relative).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(repo_path(relative), root / relative)
            # A skill names the cad it was written for as `cad==X`; nothing else in a skill is stamped: not a
            # pattern (`cad==*`), not another word's `cad`, not a version in prose, and not the setup
            # block's fixed first release of a global install (0.11.12), whatever release is stamped.
            skill = root / "skills/fixture/SKILL.md"
            skill.parent.mkdir(parents=True)
            fixed = "0.11.12, run `uv tool install cad`, adding `--force` if uv says `cad` already exists.\n"
            unstamped = ("---\nname: fixture\n---\n"
                         "Written for `cad==1.0.0`. Before first use in a chat, run `cad --version`. If `cad` is missing "
                         "or older than\n" + fixed + "A pattern: `uv tool install cad==*`.\n"
                         "```bash\nuv tool install --managed-python --python 3.14 cad==0.11.10-dev.1\n```\n"
                         "Not the release: cad 1.0.0 in prose, `my-cad==1.2.3`, bpy 5.2.3, cadgen==0.1.0, "
                         "text-to-cad@earthtojake.\n")
            stamped = (unstamped.replace("cad==1.0.0", "cad==9.9.9").replace("0.11.10-dev.1", "9.9.9"))
            skill.write_text(unstamped, encoding="utf-8")
            (root / "VERSION").write_text("9.9.9\n", encoding="utf-8")
            result = subprocess.run(["node", str(root / "scripts/release/sync-version.mjs")],
                                    capture_output=True, text=True, timeout=120)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual(json.loads((root / "gemini-extension.json").read_text(encoding="utf-8"))["version"], "9.9.9")
            codex = json.loads((root / "codex.mcp.json").read_text(encoding="utf-8"))
            self.assertIn("cad@9.9.9", codex["mcpServers"]["cad"]["args"])
            # The four projects are the release, and the aliases pin cad at it.
            for project in ("cad", "aliases/cad-server", "aliases/cad-mcp", "aliases/cadgen"):
                text = (root / "packages" / project / "pyproject.toml").read_text(encoding="utf-8")
                self.assertIn('\nversion = "9.9.9"\n', text, project)
                if project != "cad":
                    self.assertIn('"cad==9.9.9"', text, project)
                    self.assertNotRegex(text, r"cad==(?!9\.9\.9)", project)
            self.assertEqual(skill.read_text(encoding="utf-8"), stamped)
            # The development lock records cad's version, and `uv sync --locked` refuses one that is not the
            # pyproject's: its entry is stamped with the rest.
            self.assertIn('\nname = "cad"\nversion = "9.9.9"\nsource = { editable = "packages/cad" }\n',
                          (root / "uv.lock").read_text(encoding="utf-8"))
            # Stamped once, it is stamped: a second run changes nothing.
            again = subprocess.run(["node", str(root / "scripts/release/sync-version.mjs")],
                                   capture_output=True, text=True, timeout=120)
            self.assertEqual(0, again.returncode, again.stdout + again.stderr)
            self.assertIn("already synced", again.stdout)
            # A release at that fixed number or past it stamps the release and leaves the fixed number alone.
            for release in ("0.11.12", "0.12.0"):
                (root / "VERSION").write_text(f"{release}\n", encoding="utf-8")
                bumped = subprocess.run(["node", str(root / "scripts/release/sync-version.mjs")],
                                        capture_output=True, text=True, timeout=120)
                self.assertEqual(0, bumped.returncode, bumped.stdout + bumped.stderr)
                self.assertEqual(skill.read_text(encoding="utf-8"), stamped.replace("9.9.9", release), release)
            # The README, the docs site's homepage and its policy pages are prose and no pin target: a
            # pin there would never be stamped. The privacy policy's telemetry commands run `cad`.
            self.assertIn("<code>cad telemetry off</code>",
                          repo_path("apps/docs/src/app/privacy-policy/page.tsx").read_text(encoding="utf-8"))
            for page in ("README.md", "apps/docs/src/lib/content.ts", "apps/docs/src/app/privacy-policy/page.tsx",
                         "apps/docs/src/app/terms-of-service/page.tsx"):
                self.assertNotRegex(repo_path(page).read_text(encoding="utf-8"), r"(?<![\w.-])(cadgen|cad(-server|-mcp)?(\[[a-z0-9_,.-]+\])?)==", page)

    def test_the_version_check_holds_the_manifests_and_the_skills_to_the_release(self) -> None:
        """check-version.sh refuses a manifest or a server line of another release, and a skill written for
        another."""
        # The four distributions' pyprojects, which it checks too, as they are.
        projects = json.loads(_node("const { tomlTargets } = await import(%s);\nconsole.log(JSON.stringify(tomlTargets));"
                                    % json.dumps(SYNC_SCRIPT.as_uri())))
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch).resolve()
            # And the plugin's manifests and server configs, which name the release.
            manifests = json.loads(_node("const { jsonTargets, pinTargets } = await import(%s);\n"
                                         "console.log(JSON.stringify([...jsonTargets.map((t) => t.path), ...pinTargets]));"
                                         % json.dumps(SYNC_SCRIPT.as_uri())))
            manifests = [path for path in manifests if path.endswith(".json") and "package" not in path]
            for relative in ("scripts/release/check-version.sh", "scripts/release/release-tags.sh",
                             "scripts/release/unavailable-versions.txt",
                             *projects, *manifests):
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(repo_path(relative), root / relative)
            shutil.copy2(repo_path("VERSION"), root / "VERSION")
            # And the skills, which name the release they were written for.
            shutil.copytree(repo_path("skills"), root / "skills")
            check = [str(root / "scripts/release/check-version.sh")]
            passed = subprocess.run(check, capture_output=True, text=True, timeout=60)
            self.assertEqual(0, passed.returncode, passed.stdout + passed.stderr)
            (root / "VERSION").write_text("9.9.9\n", encoding="utf-8")
            stale = subprocess.run(check, capture_output=True, text=True, timeout=60)
            self.assertEqual(1, stale.returncode, stale.stdout + stale.stderr)
            released = repo_path("VERSION").read_text(encoding="utf-8").strip()
            self.assertIn(f"skills/ names cad=={released}; expected 9.9.9", stale.stderr)
            for manifest in (".claude-plugin/plugin.json", ".muse-plugin/marketplace.json", ".kimi-plugin/plugin.json"):
                self.assertIn(f"{manifest} names version {released}; expected 9.9.9", stale.stderr)
            self.assertIn(f"codex.mcp.json names cad@{released}; expected 9.9.9", stale.stderr)
            # A command pinned to a version fails whatever the version.
            (root / "VERSION").write_text(f"{released}\n", encoding="utf-8")
            (root / "skills/cad/references/pinned.md").write_text(f"Run `cad +{released} run x.py`.\n", encoding="utf-8")
            pinned = subprocess.run(check, capture_output=True, text=True, timeout=60)
            self.assertEqual(1, pinned.returncode, pinned.stdout + pinned.stderr)
            self.assertIn("skills/cad/references/pinned.md", pinned.stderr)

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
