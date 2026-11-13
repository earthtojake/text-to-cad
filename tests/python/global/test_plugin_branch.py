"""The plugin the install branches carry: scripts/release/plugin_branch.py.

Publish Release commits these trees onto `latest` and `claude-plugin`, so a
tree claude.ai's directory would hold or refuse has to fail here, on the pull request that
causes it, rather than at release time.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tests.python.support.paths import REPO_ROOT

spec = importlib.util.spec_from_file_location("plugin_branch", REPO_ROOT / "scripts/release/plugin_branch.py")
branch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(branch)

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64
SERVERS = json.dumps({"mcpServers": {"cad": {"command": "uvx", "args": ["--from", "cad-mcp==1.0.0", "cad-mcp"]}}})


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


class PluginTreeTests(unittest.TestCase):
    def test_this_repository_builds_trees_of_only_the_plugin(self) -> None:
        on_main = branch.tracked(REPO_ROOT)
        skills = {path for path in on_main if path.startswith("skills/")}
        blobs = branch.read_blobs(REPO_ROOT, sorted({blob for _mode, blob in on_main.values()}))
        # latest: every host's manifest and config, the marketplace catalog, Codex's, Grok Build's and the Agent
        # Plugins standard's, and every skill; each file main's, but the README and latest's Cursor config.
        install, errors, _manifest = branch.build(REPO_ROOT, "latest")
        self.assertEqual(errors, [])
        self.assertEqual(set(install), {*branch.FILES, *branch.MARKETPLACE_FILES, *branch.STANDARD_FILES,
                                        *branch.GROK_FILES, "README.md", *skills})
        self.assertEqual([path for path, (_mode, data) in sorted(install.items()) if data != blobs[on_main[path][1]]],
                         ["README.md", "cursor.mcp.json"])
        # Claude Code gets the skills alone from latest; Grok Build reads its own manifest first, naming the server.
        self.assertEqual({path: json.loads(install[path][1]).get("mcpServers")
                          for path in (".claude-plugin/plugin.json", ".grok-plugin/plugin.json")},
                         {".claude-plugin/plugin.json": None, ".grok-plugin/plugin.json": "./claude.mcp.json"})
        # claude.ai's directory: Claude's manifest (main's, naming no server) and icon, LICENSE, the README and
        # every skill, no other host's manifest or config, and every file a type the directory accepts from an
        # organization it has not verified.
        directory, errors, _manifest = branch.build(REPO_ROOT, "directory")
        self.assertEqual(errors, [])
        self.assertEqual({path for path in directory if not path.startswith("skills/")},
                         {".claude-plugin/plugin.json", ".claude-plugin/icon.png", "LICENSE", "README.md"})
        self.assertEqual(directory[".claude-plugin/plugin.json"][1], blobs[on_main[".claude-plugin/plugin.json"][1]])
        self.assertNotIn("mcpServers", json.loads(directory[".claude-plugin/plugin.json"][1]))
        self.assertEqual(branch.type_errors(directory), [])
        self.assertEqual({path for path in directory if path.startswith("skills/")}, skills)
        # Byte for byte main's: the skills' `cad +<VERSION>` pins are the release's in every copy.
        self.assertEqual([path for path in skills if directory[path][1] != blobs[on_main[path][1]]], [])

    def test_the_install_copy_lists_itself_as_the_plugin(self) -> None:
        # The catalog lists the plugin at the root of the branch it is read from, so a marketplace
        # added from `latest` installs what that branch holds -- no link back to the repo.
        install, _errors, manifest = branch.build(REPO_ROOT, "latest")
        catalog = json.loads(install[".claude-plugin/marketplace.json"][1])
        self.assertEqual([entry["source"] for entry in catalog["plugins"] if entry["name"] == manifest["name"]], ["./"])

    def test_every_file_a_manifest_names_ships_in_its_copy(self) -> None:
        # Developers install main and users install a copy, so a manifest or config that names a file the
        # copy leaves out works for every developer and breaks for every user.
        on_main = set(branch.tracked(REPO_ROOT))

        def strings(value):
            if isinstance(value, dict):
                value = list(value.values())
            if isinstance(value, list):
                for item in value:
                    yield from strings(item)
            elif isinstance(value, str):
                yield value

        for copy in branch.COPIES:
            tree, errors, _manifest = branch.build(REPO_ROOT, copy)
            self.assertEqual(errors, [], copy)
            missing = [f"{path} -> {value}" for path, (_mode, data) in sorted(tree.items())
                       if path.endswith(".json") and not path.startswith("skills/")
                       for value in strings(json.loads(data))
                       if branch.holds(on_main, value) and not branch.holds(set(tree), value)]
            with self.subTest(copy=copy):
                self.assertEqual(missing, [])

    def test_each_config_names_the_channel_its_installs_come_from(self) -> None:
        # Every installer but claude.ai's directory, whose copy has no server, follows latest, where the configs
        # keep main's channels but Cursor's: main's names the Cursor Marketplace, which reads main and updates
        # its copies, and a Cursor install by hand clones the branch. The server's environment is the plugin's
        # say (the server's _internal/channel.py).
        tree, errors, _manifest = branch.build(REPO_ROOT, "latest")
        self.assertEqual(errors, [])
        said = {path: json.loads(tree[path][1])["mcpServers"]["cad"]["env"]
                for path in ("claude.mcp.json", "codex.mcp.json", "cursor.mcp.json", "mcp.json", "gemini-extension.json")}
        self.assertEqual(said, {
            "claude.mcp.json": {"CAD_INSTALL_CHANNEL": "claude-github"},
            "codex.mcp.json": {"CAD_INSTALL_CHANNEL": "codex-github"},
            "cursor.mcp.json": {"CAD_INSTALL_CHANNEL": "cursor-github"},
            "mcp.json": {"CAD_INSTALL_CHANNEL": "agent-plugins"},
            "gemini-extension.json": {"CAD_INSTALL_CHANNEL": "gemini-github"},
        })

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

    def test_the_directory_copy_refuses_every_file_type_but_text_and_images(self) -> None:
        # claude.ai's directory accepts from an organization it has not verified Markdown, text, JSON, YAML and
        # PNG, JPEG, GIF, WebP or ICO images, by content: nothing starting with #!, nothing but UTF-8 with no NUL
        # byte, no config Claude Code would read beside the manifest, no package manager's, and nothing in
        # .claude-plugin/ but plugin.json and images.
        allowed = {".claude-plugin/plugin.json": b"{}", ".claude-plugin/icon.png": PNG, "LICENSE": b"MIT\n",
                   "skills/a/SKILL.md": b"# A\n", "skills/a/LICENSE": b"MIT\n", "skills/a/agents/openai.yaml": b"a: 1\n",
                   "skills/a/notes.txt": "café\n".encode()}
        refused = {"skills/a/run.py": b"print(1)\n", "skills/a/run.md": b"#!/bin/sh\necho\n", ".mcp.json": b"{}",
                   ".claude-plugin/marketplace.json": b"{}", "skills/a/package.json": b"{}", "skills/a/x.json": b"{\0}",
                   "skills/a/latin.md": "café".encode("latin-1"), "skills/a/fake.png": b"not a png",
                   "skills/a/hooks/hooks.json": b"{}"}
        errors = branch.type_errors({path: ("100644", data) for path, data in {**allowed, **refused}.items()})
        self.assertEqual([error.split(": ")[0] for error in errors], sorted(refused))

    def test_commits_build_on_the_branch_and_an_unchanged_tree_adds_none(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            git(root, "init", "-q")
            git(root, "config", "user.name", "Test")
            git(root, "config", "user.email", "test@example.com")
            manifest = {"name": "demo", "version": "1.0.0", "repository": "https://github.com/o/demo"}
            files = {".claude-plugin/plugin.json": json.dumps(manifest), ".claude-plugin/icon.png": PNG,
                     ".claude-plugin/marketplace.json": "{}", ".cursor-plugin/plugin.json": "{}",
                     "gemini-extension.json": "{}", "claude.mcp.json": SERVERS, "cursor.mcp.json": SERVERS, "LICENSE": "MIT\n",
                     "skills/s/SKILL.md": "one\n", "skills/p/SKILL.md": "prints\n",
                     "README.md": "[s](skills/s/SKILL.md) [c](CONTRIBUTING.md)\n",
                     "CONTRIBUTING.md": "x\n", "apps/web.js": "x\n"}
            for path, content in files.items():
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_bytes(content if isinstance(content, bytes) else content.encode())
            git(root, "add", "-A")
            git(root, "commit", "-q", "-m", "one")

            # Every skill, and nothing another host reads.
            tree, errors, _manifest = branch.build(root, "directory")
            self.assertEqual(errors, [])
            first = branch.commit(root, tree, None, "demo 1.0.0")
            self.assertEqual(git(root, "ls-tree", "-r", "--name-only", first).split(),
                             [".claude-plugin/icon.png", ".claude-plugin/plugin.json", "LICENSE", "README.md",
                              "skills/p/SKILL.md", "skills/s/SKILL.md"])
            self.assertEqual(git(root, "show", f"{first}:README.md"),
                             f"[s](skills/s/SKILL.md) [c](https://github.com/o/demo/blob/{git(root, 'rev-parse', 'HEAD')}"
                             "/CONTRIBUTING.md)")
            self.assertEqual(branch.commit(root, tree, first, "demo 1.0.0"), first)

            (root / "skills/s/SKILL.md").write_text("two\n", encoding="utf-8")
            git(root, "commit", "-q", "-am", "two")
            second = branch.commit(root, branch.build(root, "directory")[0], first, "demo 1.0.1")
            self.assertEqual(git(root, "rev-parse", f"{second}^"), first)
            self.assertEqual(git(root, "show", f"{second}:skills/s/SKILL.md"), "two")

            # A file the directory refuses, in a skill, fails the build: no skill is left out to make it pass.
            (root / "skills/p/scripts").mkdir()
            (root / "skills/p/scripts/go.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
            git(root, "add", "-A")
            git(root, "commit", "-q", "-m", "a script")
            tree, errors, _manifest = branch.build(root, "directory")
            self.assertIn("skills/p/scripts/go.py", tree)
            self.assertEqual([error.split(": ")[0] for error in errors], ["skills/p/scripts/go.py"])
            git(root, "rm", "-q", "-r", "skills/p/scripts")
            git(root, "commit", "-q", "-m", "no script")

            # A server or hooks in Claude's manifest fails the directory's copy, which carries the skills alone.
            (root / ".claude-plugin/plugin.json").write_text(json.dumps({**manifest, "mcpServers": "./claude.mcp.json"}),
                                                                encoding="utf-8")
            git(root, "commit", "-q", "-am", "three")
            self.assertIn(".claude-plugin/plugin.json names `mcpServers`; this copy carries the skills alone",
                          branch.build(root, "directory")[1])


if __name__ == "__main__":
    unittest.main()
