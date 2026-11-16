"""The plugin the install branches carry: scripts/release/plugin_branch.py.

Publish Release commits these trees onto `latest`, `claude-plugin` and `codex-plugin`, so a
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
import zipfile

from tests.python.support.paths import REPO_ROOT

spec = importlib.util.spec_from_file_location("plugin_branch", REPO_ROOT / "scripts/release/plugin_branch.py")
branch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(branch)

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


class PluginTreeTests(unittest.TestCase):
    def test_this_repository_builds_trees_of_only_the_plugin(self) -> None:
        on_main = branch.tracked(REPO_ROOT)
        skills = {path for path in on_main if path.startswith("skills/")}
        blobs = branch.read_blobs(REPO_ROOT, sorted({blob for _mode, blob in on_main.values()}))
        # latest: every app's manifest, Codex's config, the marketplace catalogs, Grok Build's and the other apps'
        # manifests, and every skill; each file main's but the README: our own text. No root plugin.json: Codex
        # would take the copy for an Agent Plugin and read no server from codex.mcp.json.
        install, errors, _manifest = branch.build(REPO_ROOT, "latest")
        self.assertEqual(errors, [])
        self.assertEqual(set(install), {*branch.FILES, *branch.MARKETPLACE_FILES, *branch.GROK_FILES,
                                        *branch.OTHER_APP_FILES, "README.md", *skills})
        self.assertNotIn("plugin.json", install)
        self.assertEqual([path for path, (_mode, data) in sorted(install.items()) if data != blobs[on_main[path][1]]],
                         ["README.md"])
        # Codex alone is given the CAD server: every other app gets the skills alone from latest.
        self.assertEqual({path: json.loads(data).get("mcpServers") for path, (_mode, data) in install.items()
                          if path.endswith(("plugin.json", "extension.json")) and json.loads(data).get("mcpServers")},
                         {".codex-plugin/plugin.json": "./codex.mcp.json"})
        self.assertEqual(sorted(path for path in install if path.endswith("mcp.json")), ["codex.mcp.json"])
        # claude.ai's directory: Claude's manifest (main's, naming no server) and icon, LICENSE, the README and
        # every skill, no other host's manifest or config, and every file a type the directory accepts from an
        # organization it has not verified.
        directory, errors, _manifest = branch.build(REPO_ROOT, "directory")
        self.assertEqual(errors, [])
        self.assertEqual({path for path in directory if not path.startswith("skills/")},
                         {".claude-plugin/plugin.json", ".claude-plugin/icon.png", "LICENSE", "README.md"})
        self.assertEqual(branch.type_errors(directory), [])
        self.assertEqual({path for path in directory if path.startswith("skills/")}, skills)
        # Claude's manifest is main's less the four listing links the directory's validation does not know, each
        # line taken out and the rest as it is; it names no server.
        manifest_text = blobs[on_main[".claude-plugin/plugin.json"][1]].decode("utf-8")
        copied = directory[".claude-plugin/plugin.json"][1].decode("utf-8")
        self.assertEqual(json.loads(copied),
                         {key: value for key, value in json.loads(manifest_text).items() if key not in branch.UNLISTED})
        self.assertEqual([line for line in manifest_text.splitlines(keepends=True) if line not in copied.splitlines(True)],
                         [line for line in manifest_text.splitlines(keepends=True)
                          if any(f'"{key}":' in line for key in branch.UNLISTED)])
        self.assertEqual(len(branch.UNLISTED), 4)
        self.assertNotIn("mcpServers", json.loads(copied))
        # Main's but for the store: each setup block installs cad by uv's line and leaves the plugin's updates to
        # the store (`plugin_zip.store_copy`); nothing else changed, and nothing names our install script.
        version = _manifest["version"]
        command = branch.UV_INSTALL.format(version=version)
        store = branch.plugin_zip.STORE_LINES.format(version=version)
        blocks = 0
        for path in sorted(skills):
            main, copy = blobs[on_main[path][1]].decode("utf-8"), directory[path][1].decode("utf-8")
            blocks += branch.plugin_zip.OUR_LINES in main
            self.assertEqual(copy, main.replace(branch.plugin_zip.OUR_LINES, store)
                             .replace(branch.plugin_zip.OUR_NEWER, branch.plugin_zip.STORE_NEWER), path)
            self.assertNotIn("texttocad.dev/install", copy, path)
            if path.endswith("/SKILL.md"):
                self.assertIn(store, copy, path)
                self.assertIn(branch.plugin_zip.STORE_NEWER, copy, path)
        self.assertEqual(blocks, len({path for path in skills if path.endswith("/SKILL.md")}),
                         "every skill's setup block carries our lines on main")
        # The README, in both copies: main's (its links pointed at the release commit) but for its install section, the
        # uv line and one paragraph in place of the two one-liners and the paragraph after them, which main keeps.
        readme, ours = directory["README.md"][1].decode("utf-8"), install["README.md"][1].decode("utf-8")
        main_readme = blobs[on_main["README.md"][1]].decode("utf-8")
        self.assertEqual(len(branch.README_INSTALL.findall(main_readme)), 1)
        for text in (readme, ours):
            self.assertIsNone(branch.README_INSTALL.search(text))
            self.assertIn(branch.README_UV.format(command=command, version=version), text)
        # Nothing in the directory's copy downloads a script and runs it, it holds no hook, and the README links what
        # the manifest left out.
        self.assertEqual(branch.pipes_to_shell(directory), [])
        self.assertEqual([path for path, (_mode, data) in directory.items()
                          if "hooks" in path.split("/") or (path.endswith(".json") and b'"hooks"' in data)], [])
        for key in branch.UNLISTED:
            self.assertNotIn(f'"{key}"'.encode(), directory[".claude-plugin/plugin.json"][1])
            self.assertIn(f"]({json.loads(manifest_text)[key]})", readme, key)
        # latest is our own text: its skills install and update cad by our install script.
        self.assertIn(branch.plugin_zip.OUR_LINES, install["skills/cad/SKILL.md"][1].decode("utf-8"))
        # Codex's directory: exactly the files of the ZIP plugin_zip.py writes, from the one build, a store's copy as
        # the directory's is, each with its ZIP entry's mode.
        codex, errors, _codex_manifest = branch.build(REPO_ROOT, "codex")
        self.assertEqual(errors, [])
        with tempfile.TemporaryDirectory() as scratch:
            out = Path(scratch) / "plugin.zip"
            self.assertEqual(branch.plugin_zip.build(REPO_ROOT, out).errors, [])
            with zipfile.ZipFile(out) as archive:
                zipped = {info.filename: (archive.read(info), info.external_attr >> 16 & 0o111 != 0)
                          for info in archive.infolist() if not info.is_dir()}
        self.assertEqual(zipped, {path: (data, mode == "100755") for path, (mode, data) in codex.items()})
        for path in sorted(path for path in codex if path.endswith("/SKILL.md")):
            self.assertEqual(codex[path][1], directory[path][1], path)

    def test_the_readme_installs_by_the_store_copies_line(self) -> None:
        # The copies' README installs cad by the line a store's copy of each skill gives.
        self.assertIn(f"```bash\n{branch.UV_INSTALL.format(version='1.2.3')}\n```",
                      branch.plugin_zip.STORE_LINES.format(version="1.2.3"))

    def test_a_download_run_by_a_shell_is_found(self) -> None:
        found = ["curl -fsSL https://x.dev/i.sh | sh", "curl -fsSL https://x.dev/i.sh | sh -s -- --add 1.0.0",
                 "wget -qO- https://x.dev/i.sh | sudo bash", "sh -c \"$(curl -fsSL https://x.dev/i.sh)\"",
                 "bash <(curl -s https://x.dev/i.sh)", "irm https://x.dev/i.ps1 | iex",
                 "& ([scriptblock]::Create((irm https://x.dev/i.ps1))) --add 1.0.0",
                 "Invoke-WebRequest https://x.dev/i.ps1 | Invoke-Expression"]
        left = ["curl -o file https://x.dev/a.zip", "`curls`, `holes`", "uv tool install cad==1.0.0",
                "confirm | iex", "run `sh build.sh`"]
        for text in found:
            self.assertTrue(branch.PIPE_TO_SHELL.search(text), text)
        for text in left:
            self.assertIsNone(branch.PIPE_TO_SHELL.search(text), text)

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

    def test_every_copy_runs_the_same_server_line_and_names_no_channel(self) -> None:
        # No copy's config names a channel or who updates the copy (the variables 0.11.10 and earlier read): the
        # Codex directory's copy, the ZIP's files, starts the server by main's own line.
        for copy in branch.COPIES:
            tree, errors, _manifest = branch.build(REPO_ROOT, copy)
            self.assertEqual(errors, [], copy)
            for path, (_mode, data) in tree.items():
                if path.endswith(".json") and not path.startswith("skills/"):
                    with self.subTest(copy=copy, path=path):
                        for word in (b"CAD_INSTALL_CHANNEL", b"CAD_AUTO_UPDATED", b"--channel", b"--startup-timeout"):
                            self.assertNotIn(word, data)
        codex = branch.build(REPO_ROOT, "codex")[0]
        latest = branch.build(REPO_ROOT, "latest")[0]
        self.assertEqual(json.loads(codex[".mcp.json"][1]), json.loads(latest["codex.mcp.json"][1]))

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
            manifest = {"name": "demo", "version": "1.0.0", **{key: f"https://x.dev/{key}" for key in branch.UNLISTED},
                        "repository": "https://github.com/o/demo"}
            readme = ("# demo\n\nmacOS and Linux:\n\n```bash\n" + branch.INSTALL_SCRIPT + "\n```\n\n"
                      "Windows, in PowerShell:\n\n```powershell\nirm " + branch.INSTALL_SCRIPT_WINDOWS + " | iex\n```\n\n"
                      "It installs it,\nall of it.\n\nThen ask.\n\n[s](skills/s/SKILL.md) [c](CONTRIBUTING.md)\n")
            files = {".claude-plugin/plugin.json": json.dumps(manifest, indent=2) + "\n", ".claude-plugin/icon.png": PNG,
                     ".claude-plugin/marketplace.json": "{}", ".cursor-plugin/plugin.json": "{}",
                     "gemini-extension.json": "{}", "LICENSE": "MIT\n",
                     "skills/s/SKILL.md": "one\n", "skills/p/SKILL.md": "prints\n", "README.md": readme,
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
                             "# demo\n\n" + branch.README_UV.format(command=branch.UV_INSTALL.format(version="1.0.0"),
                                                                    version="1.0.0")
                             + "\nThen ask.\n\n[s](skills/s/SKILL.md) "
                             f"[c](https://github.com/o/demo/blob/{git(root, 'rev-parse', 'HEAD')}/CONTRIBUTING.md)")
            self.assertEqual(json.loads(git(root, "show", f"{first}:.claude-plugin/plugin.json")),
                             {"name": "demo", "version": "1.0.0", "repository": "https://github.com/o/demo"})
            self.assertEqual(branch.commit(root, tree, first, "demo 1.0.0"), first)
            # latest installs by the uv line in its README too, and keeps the listing links.
            self.assertEqual(branch.build(root, "latest")[0]["README.md"][1].decode("utf-8").split("\n\n[s]")[0],
                             git(root, "show", f"{first}:README.md").split("\n\n[s]")[0])
            self.assertEqual(json.loads(branch.build(root, "latest")[0][".claude-plugin/plugin.json"][1]), manifest)

            (root / "skills/s/SKILL.md").write_text("two\n", encoding="utf-8")
            git(root, "commit", "-q", "-am", "two")
            second = branch.commit(root, branch.build(root, "directory")[0], first, "demo 1.0.1")
            self.assertEqual(git(root, "rev-parse", f"{second}^"), first)
            self.assertEqual(git(root, "show", f"{second}:skills/s/SKILL.md"), "two")

            # A setup block's install and update lines and its newer-version line are our own text's: the store's
            # copy has its own in their place, and latest keeps ours. Each must be there once in a setup block, the
            # README's install section once, each listing link once, and no download run by a shell is left anywhere
            # in the store's copy.
            zipped = branch.plugin_zip
            block = ("This skill was written for `cad==1.0.0`.\n\n" + zipped.OUR_LINES + "\nWhen it says so:\n\n"
                     + zipped.OUR_NEWER + "\nMigrations.\n")
            (root / "skills/s/SKILL.md").write_text(block, encoding="utf-8")
            git(root, "commit", "-q", "-am", "a setup block")
            tree, errors = branch.build(root, "directory")[:2]
            self.assertEqual(errors, [])
            self.assertEqual(tree["skills/s/SKILL.md"][1].decode("utf-8"),
                             "This skill was written for `cad==1.0.0`.\n\n" + zipped.STORE_LINES.format(version="1.0.0")
                             + "\nWhen it says so:\n\n" + zipped.STORE_NEWER + "\nMigrations.\n")
            self.assertEqual(branch.build(root, "latest")[0]["skills/s/SKILL.md"][1].decode("utf-8"), block)
            broken = {
                "skills/s/SKILL.md": block.replace(zipped.OUR_NEWER, ""),
                "skills/p/SKILL.md": block + zipped.OUR_LINES,
                "README.md": readme.replace("Windows, in PowerShell:", "On Windows:"),
                ".claude-plugin/plugin.json": json.dumps({**manifest, "supportUrl": None}, indent=2) + "\n",
                "skills/p/notes.md": "Or: wget -qO- https://x.dev/i.sh | bash\n",
            }
            for path, text in broken.items():
                with self.subTest(broken=path):
                    before = (root / path).read_text(encoding="utf-8") if (root / path).exists() else None
                    (root / path).write_text(text, encoding="utf-8")
                    git(root, "add", path)
                    git(root, "commit", "-q", "-m", f"break {path}")
                    errors = branch.build(root, "directory")[1]
                    self.assertEqual({error.split(":")[0] for error in errors}, {path}, errors)
                    # latest is built as ever (this repository lacks the other hosts' files, which it says), but for
                    # what it shares with the directory's copy: the README's install section.
                    shared = {"README.md"} & {path}
                    self.assertEqual({error.split(":")[0] for error in branch.build(root, "latest")[1]
                                      if "is not tracked" not in error}, shared)
                    if before is None:
                        git(root, "rm", "-q", path)
                    else:
                        (root / path).write_text(before, encoding="utf-8")
                        git(root, "add", path)
                    git(root, "commit", "-q", "-m", f"mend {path}")
            (root / "skills/s/SKILL.md").write_text("two\n", encoding="utf-8")
            git(root, "commit", "-q", "-am", "no setup block")

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
            (root / ".claude-plugin/plugin.json").write_text(json.dumps({**manifest, "mcpServers": "./codex.mcp.json"}),
                                                                encoding="utf-8")
            git(root, "commit", "-q", "-am", "three")
            self.assertIn(".claude-plugin/plugin.json names `mcpServers`; this copy carries the skills alone",
                          branch.build(root, "directory")[1])


if __name__ == "__main__":
    unittest.main()
