"""The JS side must build and test the same way on every machine and every Node.

Two independent ways that stopped being true, both reported in #201:

* the Viewer bundler picked its package manager from what was INSTALLED, so a release
  built on a laptop with pnpm on PATH was bundled against a different node_modules layout
  than the committed lockfile describes;
* the JS test runners passed ``--experimental-default-type=module``, a flag that current
  Node rejects outright -- so the suites refused to start rather than failing a test.

Both are the kind of thing nobody notices until a specific machine or a specific Node,
which is why they are pinned here rather than left to whoever runs the build next.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

VIEWER_DIR = REPO_ROOT / "viewer"
VIEWER_BUNDLER = REPO_ROOT / "scripts" / "bundle" / "skills" / "bundle-cad-viewer.sh"
IMPLICITJS_RUNNER = REPO_ROOT / "packages" / "implicitjs" / "scripts" / "run-tests.mjs"
NODE_MODULE_SUPPORT = (
    REPO_ROOT / "packages" / "implicitjs" / "src" / "lib" / "implicitCad" / "nodeModuleSupport.js"
)
TEST_RUNNERS = (
    REPO_ROOT / "packages" / "cadjs" / "scripts" / "run-tests.mjs",
    IMPLICITJS_RUNNER,
    REPO_ROOT / "viewer" / "scripts" / "run-tests.mjs",
)


def resolved_viewer_package_manager(*lockfiles: str, override: str = "") -> str:
    """Run the bundler's own resolver against a synthetic viewer dir.

    The function is extracted from the script and executed rather than pattern-matched, so
    the test asserts on BEHAVIOUR -- including the fallback order -- instead of on the text
    of a shell if-chain. Both package managers are stubbed onto PATH so "installed" is never
    what decides the answer.
    """
    bundler = VIEWER_BUNDLER.read_text(encoding="utf-8")
    match = re.search(
        r"^resolve_viewer_package_manager\(\) \{.*?^\}\n",
        bundler,
        re.DOTALL | re.MULTILINE,
    )
    if match is None:
        raise AssertionError("resolve_viewer_package_manager is gone from the Viewer bundler")

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        bin_dir = root / "bin"
        viewer_dir = root / "viewer"
        bin_dir.mkdir()
        viewer_dir.mkdir()
        for command in ("npm", "pnpm"):
            executable = bin_dir / command
            executable.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
        for lockfile in lockfiles:
            (viewer_dir / lockfile).touch()

        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{bin_dir}:{env.get('PATH', '')}",
                "VIEWER_DIR": str(viewer_dir),
                "VIEWER_PACKAGE_MANAGER": override,
            }
        )
        result = subprocess.run(
            ["bash", "-c", f"set -euo pipefail\n{match.group(0)}\nresolve_viewer_package_manager"],
            check=True,
            capture_output=True,
            env=env,
            text=True,
        )
        return result.stdout.strip()


class ViewerPackageManagerIsDecidedByTheLockfileTest(unittest.TestCase):
    def test_the_repository_commits_exactly_one_viewer_lockfile(self) -> None:
        # The premise of every case below: there is one committed answer to appeal to.
        self.assertTrue((VIEWER_DIR / "package-lock.json").is_file())
        self.assertFalse(
            (VIEWER_DIR / "pnpm-lock.yaml").exists(),
            "two committed lockfiles would make the build's package manager ambiguous again",
        )

    def test_a_committed_npm_lockfile_wins_over_an_installed_pnpm(self) -> None:
        self.assertEqual("npm", resolved_viewer_package_manager("package-lock.json"))

    def test_a_pnpm_lockfile_selects_pnpm(self) -> None:
        self.assertEqual("pnpm", resolved_viewer_package_manager("pnpm-lock.yaml"))

    def test_a_stray_local_pnpm_lockfile_cannot_flip_a_committed_npm_build(self) -> None:
        # `pnpm install` in viewer/ leaves an untracked pnpm-lock.yaml behind; a release
        # build must not change shape because someone ran it once.
        self.assertEqual(
            "npm",
            resolved_viewer_package_manager("package-lock.json", "pnpm-lock.yaml"),
        )

    def test_an_explicit_override_still_wins(self) -> None:
        self.assertEqual(
            "pnpm",
            resolved_viewer_package_manager("package-lock.json", override="pnpm"),
        )

    def test_with_no_lockfile_at_all_it_still_answers(self) -> None:
        self.assertIn(resolved_viewer_package_manager(), {"npm", "pnpm"})


class TestRunnersStartOnCurrentNodeTest(unittest.TestCase):
    def test_no_runner_passes_a_flag_current_node_rejects(self) -> None:
        # Node 24 removed --experimental-default-type, and an unknown flag is not a failed
        # test: the interpreter exits before the runner reports anything at all. Comments are
        # stripped first -- a runner is free to explain WHY it no longer passes the flag.
        for runner in TEST_RUNNERS:
            with self.subTest(runner=runner.name):
                code = re.sub(r"//[^\n]*", "", runner.read_text(encoding="utf-8"))
                self.assertNotIn(
                    "--experimental-default-type",
                    code,
                    f"{runner.relative_to(REPO_ROOT)} passes a flag current Node rejects",
                )

    def test_the_implicitjs_node_floor_is_one_number(self) -> None:
        # The runner refuses below the floor and the loader explains the same limit to a
        # user; a hand-copied second number is how the two drift.
        declared = re.search(
            r"IMPLICIT_JS_MIN_NODE_MAJOR = (\d+)",
            NODE_MODULE_SUPPORT.read_text(encoding="utf-8"),
        )
        self.assertIsNotNone(declared, "implicitjs must declare IMPLICIT_JS_MIN_NODE_MAJOR")
        runner = IMPLICITJS_RUNNER.read_text(encoding="utf-8")
        floors = set(re.findall(r"nodeMajor < (\d+)", runner))
        self.assertEqual(
            {declared.group(1)},
            floors,
            "the implicitjs runner's Node floor disagrees with IMPLICIT_JS_MIN_NODE_MAJOR",
        )
        self.assertIn(f"Node {declared.group(1)} or newer", runner)

    def test_the_ci_node_version_satisfies_that_floor(self) -> None:
        declared = int(
            re.search(
                r"IMPLICIT_JS_MIN_NODE_MAJOR = (\d+)",
                NODE_MODULE_SUPPORT.read_text(encoding="utf-8"),
            ).group(1)
        )
        workflow = (REPO_ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
        versions = [int(value) for value in re.findall(r'node-version:\s*"(\d+)"', workflow)]
        self.assertTrue(versions, "test.yml must pin a Node version")
        for version in versions:
            self.assertGreaterEqual(
                version,
                declared,
                "CI runs a Node the implicitjs suite refuses to start on",
            )

    def test_viewer_declares_the_module_type_its_tests_rely_on(self) -> None:
        # The flag existed to force module semantics; the durable answer is that every
        # package that owns .js tests declares itself a module package.
        for package_json in (
            REPO_ROOT / "packages" / "cadjs" / "package.json",
            REPO_ROOT / "packages" / "implicitjs" / "package.json",
            VIEWER_DIR / "package.json",
        ):
            with self.subTest(package=package_json.parent.name):
                self.assertEqual(
                    "module",
                    json.loads(package_json.read_text(encoding="utf-8")).get("type"),
                )


if __name__ == "__main__":
    unittest.main()
