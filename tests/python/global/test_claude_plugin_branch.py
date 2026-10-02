"""The plugin claude.ai's directory follows: scripts/release/claude_plugin_branch.py.

Publish Release commits this tree onto the `claude-plugin` branch, so a tree the
directory would hold or refuse has to fail here, on the pull request that causes
it, rather than at release time.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tests.python.support.paths import REPO_ROOT

spec = importlib.util.spec_from_file_location("claude_plugin_branch", REPO_ROOT / "scripts/release/claude_plugin_branch.py")
branch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(branch)

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


class ClaudePluginTreeTests(unittest.TestCase):
    def test_this_repository_builds_a_tree_of_only_the_plugin(self) -> None:
        tree, errors, _manifest = branch.build(REPO_ROOT)
        self.assertEqual(errors, [])
        self.assertEqual({path.split("/")[0] for path in tree}, {".claude-plugin", "claude.mcp.json", "skills", "LICENSE", "README.md"})
        self.assertEqual({path for path in tree if path.startswith(".claude-plugin/")},
                         {".claude-plugin/plugin.json", ".claude-plugin/icon.png"})

    def test_readme_links_outside_the_tree_point_at_the_commit(self) -> None:
        text = ('[cad](skills/cad/SKILL.md) [dir](skills/cad/) [license](LICENSE) [web](https://x.dev) [top](#install)\n'
                '[guide](CONTRIBUTING.md#releases) <img src="apps/logo.png"> [gone](missing.md)\n')
        errors: list[str] = []
        out = branch.readme_for_tree(text, {"skills/cad/SKILL.md", "LICENSE"},
                                     {"skills/cad/SKILL.md", "LICENSE", "CONTRIBUTING.md", "apps/logo.png"},
                                     "https://github.com/o/r", "abc123", errors)
        self.assertIn("[cad](skills/cad/SKILL.md) [dir](skills/cad/) [license](LICENSE) [web](https://x.dev) [top](#install)", out)
        self.assertIn("[guide](https://github.com/o/r/blob/abc123/CONTRIBUTING.md#releases)", out)
        self.assertIn('<img src="https://github.com/o/r/raw/abc123/apps/logo.png">', out)
        self.assertEqual(errors, ["README.md links to missing.md, which is not in the repository"])

    def test_files_the_directory_would_hold_or_refuse_fail(self) -> None:
        errors = branch.rule_errors({
            "skills/a/icon.png": ("100644", PNG),
            "skills/a/big.md": ("100644", b"x" * branch.MAX_TEXT_BYTES),
            "skills/a/favicon.ico": ("100644", b"\0\0\1\0" + b"\0" * 16),
            "skills/a/model.step": ("100644", branch.LFS_POINTER + b"\noid sha256:0\nsize 1\n"),
            "skills/a/link": ("120000", b"../b"),
        })
        self.assertEqual([error.split(":")[0] for error in errors],
                         ["skills/a/big.md", "skills/a/favicon.ico", "skills/a/link", "skills/a/model.step"])

    def test_commits_build_on_the_branch_and_an_unchanged_tree_adds_none(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            git(root, "init", "-q")
            git(root, "config", "user.name", "Test")
            git(root, "config", "user.email", "test@example.com")
            manifest = {"name": "demo", "version": "1.0.0", "repository": "https://github.com/o/demo"}
            files = {".claude-plugin/plugin.json": json.dumps(manifest), ".claude-plugin/icon.png": PNG,
                     ".claude-plugin/marketplace.json": "{}", "claude.mcp.json": "{}", "LICENSE": "MIT\n",
                     "skills/s/SKILL.md": "one\n",
                     "README.md": "[s](skills/s/SKILL.md) [c](CONTRIBUTING.md)\n", "CONTRIBUTING.md": "x\n",
                     "apps/web.js": "x\n"}
            for path, content in files.items():
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_bytes(content if isinstance(content, bytes) else content.encode())
            git(root, "add", "-A")
            git(root, "commit", "-q", "-m", "one")

            tree, errors, _manifest = branch.build(root)
            self.assertEqual(errors, [])
            first = branch.commit(root, tree, None, "demo 1.0.0")
            self.assertEqual(git(root, "ls-tree", "-r", "--name-only", first).split(),
                             [".claude-plugin/icon.png", ".claude-plugin/plugin.json", "LICENSE", "README.md",
                              "claude.mcp.json", "skills/s/SKILL.md"])
            self.assertIn(f"[c](https://github.com/o/demo/blob/{git(root, 'rev-parse', 'HEAD')}/CONTRIBUTING.md)",
                          git(root, "show", f"{first}:README.md"))
            self.assertEqual(branch.commit(root, tree, first, "demo 1.0.0"), first)

            (root / "skills/s/SKILL.md").write_text("two\n", encoding="utf-8")
            git(root, "commit", "-q", "-am", "two")
            second = branch.commit(root, branch.build(root)[0], first, "demo 1.0.1")
            self.assertEqual(git(root, "rev-parse", f"{second}^"), first)
            self.assertEqual(git(root, "show", f"{second}:skills/s/SKILL.md"), "two")


if __name__ == "__main__":
    unittest.main()
