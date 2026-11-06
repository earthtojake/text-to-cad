"""A pull request releases when it changes VERSION; the guard decides when it may.

Run on the pull request's merge commit, as Version Check runs it: the first parent is the
target branch as it is now, so a release the branch inherited is not one it makes.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import repo_path

REPOSITORY = "owner/repo"


class PrVersionGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="pr-version-guard-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Version guard test")
        self.git("config", "user.email", "version-guard@example.invalid")
        self.git("config", "core.hooksPath", str(self.root / "no-hooks"))
        # No git process outlives a command here: a detached auto-gc or auto-maintenance (git 2.55,
        # on CI) still writing into .git when the directory is removed fails the cleanup.
        self.git("config", "gc.auto", "0")
        self.git("config", "gc.autoDetach", "false")
        self.git("config", "maintenance.auto", "false")
        self.write_version("0.5.0")
        self.commit("Initial release")
        self.git("tag", "v0.5.0")
        self.git("switch", "-c", "feature")
        (self.root / "README.md").write_text("Feature work\n", encoding="utf-8")
        self.commit("Feature work")
        self.git("switch", "main")

    def git(self, *args: str) -> str:
        return subprocess.check_output(
            ["git", *args], cwd=self.root, text=True, stderr=subprocess.DEVNULL,
        )

    def write_version(self, value: str) -> None:
        (self.root / "VERSION").write_text(value + "\n", encoding="utf-8")

    def commit(self, message: str) -> None:
        self.git("add", ".")
        self.git("commit", "-m", message)

    def release_on_main(self, version: str) -> None:
        self.git("switch", "main")
        self.write_version(version)
        self.commit(f"Release {version}")
        self.git("tag", f"v{version}")

    def check(self, head_repo: str = REPOSITORY) -> subprocess.CompletedProcess[str]:
        """The guard on the merge commit GitHub would test: main with the branch merged in."""
        self.git("switch", "--detach", "main")
        self.git("merge", "--no-ff", "--no-edit", "feature")
        return subprocess.run(
            ["bash", str(repo_path("scripts/release/check-pr-version.sh")), head_repo],
            cwd=self.root, text=True, capture_output=True, check=False,
            env={**os.environ, "GITHUB_REPOSITORY": REPOSITORY},
        )

    def bump_feature(self, version: str) -> None:
        self.git("switch", "feature")
        self.write_version(version)
        self.commit(f"Bump to {version}")

    def test_a_branch_that_leaves_version_alone_releases_nothing(self) -> None:
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("releases nothing", result.stdout)

    def test_a_release_the_branch_inherited_is_not_one_it_makes(self) -> None:
        self.release_on_main("0.5.1")
        self.git("switch", "feature")
        self.git("merge", "--no-edit", "main")
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("releases nothing", result.stdout)

    def test_a_branch_of_this_repository_may_release(self) -> None:
        self.bump_feature("0.5.1")
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("releases 0.5.1", result.stdout)
        self.assertIn("Merging it releases it", result.stdout)

    def test_a_fork_may_not_release(self) -> None:
        self.bump_feature("0.5.1")
        result = self.check(head_repo="someone/fork")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fork", result.stderr)

    def test_a_version_behind_the_target_branch_is_refused(self) -> None:
        self.bump_feature("0.4.9")
        result = self.check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not past 0.5.0", result.stderr)

    def test_a_bump_another_pull_request_released_first_releases_nothing(self) -> None:
        # Both bumped to 0.5.1 and the other merged first: the merge takes the identical
        # line from both sides, so this one no longer changes VERSION.
        self.bump_feature("0.5.1")
        self.release_on_main("0.5.1")
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("releases nothing", result.stdout)

    def test_a_release_must_pass_the_latest_tag(self) -> None:
        self.git("tag", "v0.6.0")
        self.bump_feature("0.5.1")
        result = self.check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("latest release, v0.6.0", result.stderr)

    def test_a_release_too_large_for_the_push_path_filter_is_refused(self) -> None:
        # GitHub matches a push's paths against its first 300 changed files, so Publish Release
        # might not start for a release that changes more.
        self.git("switch", "feature")
        for index in range(300):
            (self.root / f"file-{index:03}.txt").write_text(f"{index}\n", encoding="utf-8")
        self.commit("Many files")
        self.bump_feature("0.5.1")
        result = self.check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("first 300", result.stderr)

    def released(self, version: str) -> None:
        """main released at ``version``, its tag the latest, and the feature branch up to date with it."""
        self.release_on_main(version)
        self.git("switch", "feature")
        self.git("merge", "--no-edit", "main")

    def migration_guide(self) -> None:
        self.git("switch", "feature")
        (self.root / "docs" / "migrations").mkdir(parents=True)
        (self.root / "docs" / "migrations" / "migrating-0.5-to-0.6.md").write_text("Renamed.\n", encoding="utf-8")
        self.commit("A migration guide")

    def test_below_1_0_a_migration_guide_takes_a_minor_release(self) -> None:
        # Below 1.0 a patch release installs itself on every device; a minor or major one waits.
        self.released("0.10.4")
        self.migration_guide()
        self.bump_feature("0.10.5")
        result = self.check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("VERSION 0.10.5 is a patch release, which installs itself on every device", result.stderr)
        self.assertIn("docs/migrations/migrating-0.5-to-0.6.md", result.stderr)
        self.assertIn("a minor release below 1.0: scripts/release/bump-version.sh minor", result.stderr)
        for version in ("0.11.0", "1.1.0"):
            self.bump_feature(version)
            result = self.check()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"releases {version}", result.stdout)

    def test_from_1_0_a_migration_guide_takes_a_major_release(self) -> None:
        # From 1.0 a patch or minor release installs itself on every device; a major one waits.
        self.released("1.2.3")
        self.migration_guide()
        for version, part in (("1.2.4", "patch"), ("1.3.0", "minor")):
            self.bump_feature(version)
            result = self.check()
            self.assertNotEqual(result.returncode, 0, version)
            self.assertIn(f"VERSION {version} is a {part} release, which installs itself on every device",
                          result.stderr)
            self.assertIn("a major release from 1.0: scripts/release/bump-version.sh major", result.stderr)
        self.bump_feature("2.0.0")
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("releases 2.0.0", result.stdout)

    def test_it_refuses_anything_but_a_merge_commit(self) -> None:
        result = subprocess.run(
            ["bash", str(repo_path("scripts/release/check-pr-version.sh")), REPOSITORY],
            cwd=self.root, text=True, capture_output=True, check=False,
            env={**os.environ, "GITHUB_REPOSITORY": REPOSITORY},
        )
        self.assertNotEqual(result.returncode, 0)


# Releases on both sides of 1.0, and across it.
VERSIONS = ("0.0.1", "0.9.9", "0.10.4", "0.10.5", "0.11.0", "0.11.12", "1.0.0", "1.0.1", "1.2.3", "1.2.4",
            "1.3.0", "1.9.3", "2.0.0", "2.1.0", "10.0.0")


class TheGuardKeepsTheUpdatersRuleTests(unittest.TestCase):
    """Version Check's copy of the rule (release-tags.sh: the release scripts import nothing of the
    packages, and its job installs no Python) answers as the automatic updater's
    (cad_server.auto_updates.takes): a release refused a migration guide is exactly one a device takes
    by itself."""

    def test_every_pair_of_releases_bumps_and_installs_itself_as_the_updater_says(self) -> None:
        from cad_server import auto_updates

        pairs = [(have, want) for have in VERSIONS for want in VERSIONS]
        script = ('source "$1"; while read -r have want; do '
                  'bump="$(version_bump "$have" "$want")" || bump=none; '
                  'if version_installs_itself "$have" "$want"; then takes=yes; else takes=no; fi; '
                  'echo "$have $want $bump $takes"; done')
        result = subprocess.run(
            ["bash", "-c", script, "bash", str(repo_path("scripts/release/release-tags.sh"))],
            input="".join(f"{have} {want}\n" for have, want in pairs),
            text=True, capture_output=True, check=True,
        )
        answered = {(have, want): (bump, takes)
                    for have, want, bump, takes in (line.split() for line in result.stdout.splitlines())}
        self.assertEqual(sorted(answered), sorted(pairs))
        for have, want in pairs:
            expected = (auto_updates.bump(have, want) or "none", "yes" if auto_updates.takes(have, want) else "no")
            self.assertEqual(answered[have, want], expected, (have, want))


if __name__ == "__main__":
    unittest.main()
