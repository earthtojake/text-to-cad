"""The release version stamp has to reach every version field it owns.

`scripts/release/sync-version.mjs` can name several paths that are the SAME FILE: a mirrored
`apps/viewer/packages/...` entry is a symlink to the canonical package. Each target reads its file
before any write happens, so two targets stamping one file means the last write wins -- and a
mirror declaring fewer fields than the canonical target silently reverts the field only the
canonical one knows about.

That is not hypothetical: adding a package's version to `packages/cadgen-js/package-lock.json`
without adding it to that file's two symlinked mirrors made the 0.4.10 release fail its own
version gate, after the bump and before anything was published.

Both halves of that failure are asserted below -- targets naming one file are merged, and no
first-party version field in a lockfile is left undeclared. The specific field that broke
0.4.10 is gone, and so are the vendored skill mirrors, so the guard is stated as the
property rather than as that one package's name.
"""

from __future__ import annotations

import json

import subprocess
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
        if not repo_path("apps", "viewer", "packages", "cadgen-js").is_symlink():
            self.skipTest("not in the development symlink layout")
        # The script resolves target paths against the repo root, so the pair below has to be
        # real repo paths: the canonical lockfile and the mirror that symlinks to it.
        script = (
            "const { mergeTargetsByRealPath } = await import(%s);\n"
            "const merged = mergeTargetsByRealPath([\n"
            '  { path: "packages/cadgen-js/package-lock.json",'
            ' fields: [["version"], ["packages", "", "version"]] },\n'
            '  { path: "apps/viewer/packages/cadgen-js/package-lock.json", fields: [["version"]], required: false },\n'
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
