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
        # Plugins standard's, and every skill; each file main's but the README: our own text, the default channel.
        install, errors, _manifest = branch.build(REPO_ROOT, "latest")
        self.assertEqual(errors, [])
        self.assertEqual(set(install), {*branch.FILES, *branch.MARKETPLACE_FILES, *branch.STANDARD_FILES,
                                        *branch.GROK_FILES, "README.md", *skills})
        self.assertEqual([path for path, (_mode, data) in sorted(install.items()) if data != blobs[on_main[path][1]]],
                         ["README.md"])
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
        # Main's but for the channel and the install block: every pin of the release stamped `@claude`, the channel
        # claude.ai's directory delivers (`channel_stamp.py`), and in each setup block the uvx command in place of the
        # install script's line, the Windows sentence gone; nothing else changed.
        version = _manifest["version"]
        command = branch.UVX_INSTALL.format(version=version)
        line, windows = branch.SETUP_LINE.format(version=version), branch.SETUP_WINDOWS.format(version=version)
        pinned, blocks = 0, 0
        for path in sorted(skills):
            main, copy = blobs[on_main[path][1]].decode("utf-8"), directory[path][1].decode("utf-8")
            blocks += line in main
            self.assertEqual(copy.replace(f"+{version}@claude", f"+{version}"),
                             main.replace(line, command + "\n").replace(windows, ""), path)
            self.assertEqual(branch.channel_stamp.unstamped(copy, version, "claude"), [], path)
            pinned += copy.count(f"+{version}@claude")
        self.assertGreater(pinned, 100, "the skills' pins were found")
        self.assertEqual(blocks, len({path for path in skills if path.endswith("/SKILL.md")}),
                         "every skill's setup block was replaced")
        cad = directory["skills/cad/SKILL.md"][1].decode("utf-8")
        self.assertIn(f"```bash\n{command}\n```\n\nIt installs {version} and the `cad` command and changes nothing else.",
                      cad)
        # The README: latest's (its links pointed at the release commit) but for its install section, the uvx command
        # and one paragraph in place of the two one-liners and the paragraph after them.
        readme, ours = directory["README.md"][1].decode("utf-8"), install["README.md"][1].decode("utf-8")
        section = branch.README_INSTALL.search(ours)[0]
        self.assertEqual(readme, ours.replace(section, branch.README_UVX.format(command=command, version=version)))
        self.assertIn(f"```bash\n{command}\n```", readme)
        # Nothing in the copy downloads a script and runs it, and the README links what the manifest left out.
        self.assertEqual(branch.pipes_to_shell(directory), [])
        for key in branch.UNLISTED:
            self.assertNotIn(f'"{key}"'.encode(), directory[".claude-plugin/plugin.json"][1])
            self.assertIn(f"]({json.loads(manifest_text)[key]})", readme, key)
        # Every other copy keeps the install script: latest's skills are main's, its README the one-liners.
        self.assertIn(line, install["skills/cad/SKILL.md"][1].decode("utf-8"))
        self.assertIn(windows, install["skills/cad/SKILL.md"][1].decode("utf-8"))
        self.assertEqual(len(branch.pipes_to_shell(install)), 2 * blocks + 2)

    def test_the_uvx_command_and_the_install_script_are_the_server_s(self) -> None:
        # The copy installs by the server's own line for a version (`cad setup --add`, what the `cad` command runs
        # for a version it lacks), and replaces the install script as the server and main's skills name it.
        from tests.python.support.paths import add_sources

        add_sources()
        from cad_server._internal import launch
        from cad_server.updates import INSTALL, INSTALL_WINDOWS

        self.assertEqual(branch.UVX_INSTALL.format(version="1.2.3"), launch.launch_command("cad", "1.2.3") + " setup --add")
        self.assertEqual(branch.INSTALL_SCRIPT, INSTALL)
        self.assertEqual(f"irm {branch.INSTALL_SCRIPT_WINDOWS} | iex", INSTALL_WINDOWS)

    def test_a_pin_left_unstamped_or_of_another_version_is_found_however_the_command_is_written(self) -> None:
        unstamped = branch.channel_stamp.unstamped
        for text in ("`cad +1.0.0 model x`", "`cad.exe +0.9.0 x`", "`cad +0.9.0@claude x`", '["cad", "+0.9.0", "x"]',
                     "['cad', '+0.9.0@claude']", '"cad","+1.0.0@codex"', "+1.0.0 alone"):
            self.assertTrue(unstamped(text, "1.0.0", "claude"), text)
        for text in ("`cad +1.0.0@claude model x`", '["cad", "+1.0.0@claude", "x"]', "`--add 1.0.0`", "cad, +5 more",
                     '["cad", "setup"]', "arcad +0.9.0"):
            self.assertEqual(unstamped(text, "1.0.0", "claude"), [], text)

    def test_a_download_run_by_a_shell_is_found(self) -> None:
        found = ["curl -fsSL https://x.dev/i.sh | sh", "curl -fsSL https://x.dev/i.sh | sh -s -- --add 1.0.0",
                 "wget -qO- https://x.dev/i.sh | sudo bash", "sh -c \"$(curl -fsSL https://x.dev/i.sh)\"",
                 "bash <(curl -s https://x.dev/i.sh)", "irm https://x.dev/i.ps1 | iex",
                 "& ([scriptblock]::Create((irm https://x.dev/i.ps1))) --add 1.0.0",
                 "Invoke-WebRequest https://x.dev/i.ps1 | Invoke-Expression"]
        left = ["curl -o file https://x.dev/a.zip", "`curls`, `holes`", "uvx --from cad-server==1.0.0 cad setup --add",
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

    def test_no_config_names_a_channel_or_who_updates_the_copy(self) -> None:
        # A channel is a pin's (`cad +<VERSION>@<channel>`) or a store's launcher's argument (`cad-mcp --channel`),
        # never a server's environment: no copy's config sets the variables 0.11.10 and earlier read.
        for copy in branch.COPIES:
            tree, errors, _manifest = branch.build(REPO_ROOT, copy)
            self.assertEqual(errors, [], copy)
            for path, (_mode, data) in tree.items():
                if path.endswith(".json") and not path.startswith("skills/"):
                    with self.subTest(copy=copy, path=path):
                        self.assertNotIn(b"CAD_INSTALL_CHANNEL", data)
                        self.assertNotIn(b"CAD_AUTO_UPDATED", data)
                        self.assertNotIn(b"--channel", data)
                        self.assertNotIn(b"--startup-timeout", data)  # the Codex directory's ZIP's alone

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
                     "gemini-extension.json": "{}", "claude.mcp.json": SERVERS, "cursor.mcp.json": SERVERS, "LICENSE": "MIT\n",
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
                             "# demo\n\n" + branch.README_UVX.format(command=branch.UVX_INSTALL.format(version="1.0.0"),
                                                                     version="1.0.0")
                             + "\nThen ask.\n\n[s](skills/s/SKILL.md) "
                             f"[c](https://github.com/o/demo/blob/{git(root, 'rev-parse', 'HEAD')}/CONTRIBUTING.md)")
            self.assertEqual(json.loads(git(root, "show", f"{first}:.claude-plugin/plugin.json")),
                             {"name": "demo", "version": "1.0.0", "repository": "https://github.com/o/demo"})
            self.assertEqual(branch.commit(root, tree, first, "demo 1.0.0"), first)
            # latest keeps the install script and the listing links.
            self.assertEqual(branch.build(root, "latest")[0]["README.md"][1].decode("utf-8").split("\n\n[s]")[0],
                             readme.split("\n\n[s]")[0])
            self.assertEqual(json.loads(branch.build(root, "latest")[0][".claude-plugin/plugin.json"][1]), manifest)

            (root / "skills/s/SKILL.md").write_text("two\n", encoding="utf-8")
            git(root, "commit", "-q", "-am", "two")
            second = branch.commit(root, branch.build(root, "directory")[0], first, "demo 1.0.1")
            self.assertEqual(git(root, "rev-parse", f"{second}^"), first)
            self.assertEqual(git(root, "show", f"{second}:skills/s/SKILL.md"), "two")

            # The copy's pins carry its channel: a pin of the release is stamped, the line installing it is not, and
            # a pin of any other version left in the text fails the build.
            (root / "skills/s/SKILL.md").write_text("Run `cad +1.0.0 model x` (`+1.0.0`); `--add 1.0.0`.\n",
                                                   encoding="utf-8")
            git(root, "commit", "-q", "-am", "pinned")
            tree, errors, _manifest = branch.build(root, "directory")
            self.assertEqual(errors, [])
            self.assertEqual(tree["skills/s/SKILL.md"][1],
                             b"Run `cad +1.0.0@claude model x` (`+1.0.0@claude`); `--add 1.0.0`.\n")
            self.assertEqual(branch.build(root, "latest")[0]["skills/s/SKILL.md"][1],
                             b"Run `cad +1.0.0 model x` (`+1.0.0`); `--add 1.0.0`.\n")
            (root / "skills/s/SKILL.md").write_text("Run `cad +0.9.0 model x`.\n", encoding="utf-8")
            git(root, "commit", "-q", "-am", "another version")
            self.assertEqual(branch.build(root, "directory")[1],
                             ["skills/s/SKILL.md: cad +0.9.0 is not stamped @claude for 1.0.0"])
            (root / "skills/s/SKILL.md").write_text("two\n", encoding="utf-8")
            git(root, "commit", "-q", "-am", "unpinned")

            # The setup block installs by the uvx command; what it replaces must be there once each, the README's
            # install section once, each listing link once, and no download run by a shell is left anywhere.
            block = ("Install:\n\n```bash\n" + branch.SETUP_LINE.format(version="1.0.0") + "```\n\n"
                     + branch.SETUP_WINDOWS.format(version="1.0.0") + "It installs 1.0.0.\n")
            (root / "skills/s/SKILL.md").write_text(block, encoding="utf-8")
            git(root, "commit", "-q", "-am", "a setup block")
            tree, errors = branch.build(root, "directory")[:2]
            self.assertEqual(errors, [])
            self.assertEqual(tree["skills/s/SKILL.md"][1].decode("utf-8"),
                             "Install:\n\n```bash\nuvx --no-config --managed-python --python 3.14 "
                             "--from cad-server==1.0.0 cad setup --add\n```\n\nIt installs 1.0.0.\n")
            self.assertEqual(branch.build(root, "latest")[0]["skills/s/SKILL.md"][1].decode("utf-8"), block)
            broken = {
                "skills/s/SKILL.md": block.replace(branch.SETUP_WINDOWS.format(version="1.0.0"), ""),
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
                    # latest is built as ever (this repository lacks the other hosts' files, which it says).
                    self.assertEqual([error for error in branch.build(root, "latest")[1] if "is not tracked" not in error], [])
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
            (root / ".claude-plugin/plugin.json").write_text(json.dumps({**manifest, "mcpServers": "./claude.mcp.json"}),
                                                                encoding="utf-8")
            git(root, "commit", "-q", "-am", "three")
            self.assertIn(".claude-plugin/plugin.json names `mcpServers`; this copy carries the skills alone",
                          branch.build(root, "directory")[1])


if __name__ == "__main__":
    unittest.main()
