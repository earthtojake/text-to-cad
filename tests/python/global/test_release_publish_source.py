from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

from tests.python.support.paths import REPO_ROOT
from tests.python.support.tmp_root import temporary_directory


CHECK_SCRIPT = REPO_ROOT / "scripts" / "release" / "check-publish-source.sh"


class ReleasePublishSourceTests(unittest.TestCase):
    def run_git(self, repo: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return result.stdout.strip()

    def write_file(self, repo: Path, name: str, text: str) -> None:
        (repo / name).write_text(text, encoding="utf-8")

    def commit(self, repo: Path, title: str, body: str | None = None) -> str:
        self.run_git(repo, "add", "-A")
        command = ["commit", "-m", title]
        if body is not None:
            command.extend(["-m", body])
        self.run_git(repo, *command)
        return self.run_git(repo, "rev-parse", "HEAD")

    def init_repo(self, repo: Path) -> str:
        self.run_git(repo, "init")
        self.run_git(repo, "config", "user.name", "Release Test")
        self.run_git(repo, "config", "user.email", "release-test@example.com")
        self.write_file(repo, "source.txt", "previous source\n")
        previous_source = self.commit(repo, "Previous source")
        self.run_git(repo, "branch", "-M", "develop")
        return previous_source

    def run_check(self, repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["RELEASE_REPO_ROOT"] = os.fspath(repo)
        return subprocess.run(
            [os.fspath(CHECK_SCRIPT), *args],
            cwd=repo,
            env=env,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def create_publish_commit(self, repo: Path, previous_source: str, *, include_source_line: bool = True) -> str:
        self.run_git(repo, "checkout", "-b", "main")
        self.write_file(repo, "source.txt", "generated output\n")
        body = f"Source commit: {previous_source}" if include_source_line else None
        publish_commit = self.commit(repo, "Publish 0.1.0 from develop to main", body)
        self.run_git(repo, "checkout", "develop")
        return publish_commit

    def create_generated_merge_publish_commit(self, repo: Path, target_parent: str, source_parent: str) -> str:
        self.write_file(repo, "source.txt", "generated output\n")
        self.run_git(repo, "add", "-A")
        tree = self.run_git(repo, "write-tree")
        message = repo / "message.txt"
        message.write_text(
            "\n".join(
                [
                    "Publish 0.2.0 from develop to main",
                    "",
                    f"Source commit: {source_parent}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        publish_commit = self.run_git(
            repo,
            "commit-tree",
            tree,
            "-p",
            target_parent,
            "-p",
            source_parent,
            "-F",
            "message.txt",
        )
        self.run_git(repo, "branch", "-f", "main", publish_commit)
        self.run_git(repo, "reset", "--hard", "develop")
        return publish_commit

    def test_accepts_source_that_contains_previous_publish_source(self) -> None:
        with temporary_directory(prefix="release-source-ok-") as repo_text:
            repo = Path(repo_text)
            previous_source = self.init_repo(repo)
            self.create_publish_commit(repo, previous_source)
            self.write_file(repo, "source.txt", "next source\n")
            source_commit = self.commit(repo, "Next source")

            result = self.run_check(repo, "--source-ref", source_commit, "--target-ref", "main")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Publish source is valid", result.stdout)

    def test_prints_previous_source_from_publish_message(self) -> None:
        with temporary_directory(prefix="release-source-print-") as repo_text:
            repo = Path(repo_text)
            previous_source = self.init_repo(repo)
            self.create_publish_commit(repo, previous_source)

            result = self.run_check(repo, "--target-ref", "main", "--print-previous-source")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), previous_source)

    def test_prints_source_parent_from_generated_merge_publish_commit(self) -> None:
        with temporary_directory(prefix="release-source-merge-") as repo_text:
            repo = Path(repo_text)
            previous_source = self.init_repo(repo)
            target_parent = self.create_publish_commit(repo, previous_source)
            self.write_file(repo, "source.txt", "next source\n")
            source_parent = self.commit(repo, "Next source")
            self.create_generated_merge_publish_commit(repo, target_parent, source_parent)

            result = self.run_check(repo, "--target-ref", "main", "--print-previous-source")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), source_parent)

    def test_rejects_source_that_drops_previous_publish_source(self) -> None:
        with temporary_directory(prefix="release-source-bad-") as repo_text:
            repo = Path(repo_text)
            previous_source = self.init_repo(repo)
            self.create_publish_commit(repo, previous_source)
            self.run_git(repo, "checkout", "--orphan", "unrelated")
            self.write_file(repo, "source.txt", "unrelated source\n")
            unrelated_source = self.commit(repo, "Unrelated source")

            result = self.run_check(repo, "--source-ref", unrelated_source, "--target-ref", "main")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("previous publish source is not an ancestor", result.stderr)

    def test_uses_target_parent_as_legacy_previous_source_fallback(self) -> None:
        with temporary_directory(prefix="release-source-legacy-") as repo_text:
            repo = Path(repo_text)
            previous_source = self.init_repo(repo)
            self.create_publish_commit(repo, previous_source, include_source_line=False)
            self.write_file(repo, "source.txt", "next source\n")
            source_commit = self.commit(repo, "Next source")

            result = self.run_check(repo, "--source-ref", source_commit, "--target-ref", "main")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(previous_source, result.stdout)


if __name__ == "__main__":
    unittest.main()
