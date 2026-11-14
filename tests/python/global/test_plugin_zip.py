"""The plugin ZIP a release attaches is a package OpenAI's plugin portal accepts.

The portal has no API, so a person uploads this file by hand. Anything the portal
would refuse should fail here, on the pull request that caused it, and not at
upload time after the release has shipped.
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

spec = importlib.util.spec_from_file_location("plugin_zip", REPO_ROOT / "scripts/release/plugin_zip.py")
plugin_zip = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin_zip)


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout


class PluginZipTests(unittest.TestCase):
    def test_the_release_zip_is_the_plugin_and_only_the_plugin(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "plugin.zip"
            package = plugin_zip.build(REPO_ROOT, out)
            self.assertEqual(package.errors, [])
            with zipfile.ZipFile(out) as archive:
                members = archive.namelist()
                manifest = json.loads(archive.read(".codex-plugin/plugin.json"))
                # The skills the checkout's but for the channel: every pin of the release stamped `@codex`, the
                # channel OpenAI's directory delivers (`channel_stamp.py`), nothing else changed.
                version = manifest["version"]
                skills = {name: archive.read(name).decode("utf-8") for name in members
                          if name.startswith("skills/") and not name.endswith("/")}
                changed = [name for name, text in skills.items()
                           if text.replace(f"+{version}@codex", f"+{version}")
                           != (REPO_ROOT / name).read_text(encoding="utf-8")
                           or plugin_zip.channel_stamp.unstamped(text, version, "codex")]
                pinned = sum(text.count(f"+{version}@codex") for text in skills.values())
                server = json.loads(archive.read(".mcp.json"))["mcpServers"]["cad"]
        # The launcher on its channel, told Codex's startup timeout from the same config: its first start, which
        # installs its version, holds Codex's initialize that long (Codex acts on no list_changed within a turn).
        timeout = server["startup_timeout_sec"]
        self.assertEqual(server["args"][-5:], ["cad-mcp", "--channel", "codex", "--startup-timeout", f"{timeout:g}"])
        # The plugin is at the archive's root, each folder with an entry of its own: the
        # portal turned away a top-level folder without one as holding no plugin.
        names = {name for name in members if not name.endswith("/")}
        self.assertEqual({name for name in members if name.endswith("/")},
                         {f"{folder}/" for folder in plugin_zip.folders(names)})
        self.assertIn(".codex-plugin/", members)
        self.assertEqual(changed, [])
        self.assertGreater(pinned, 100, "the skills' pins were found")
        # Only claude.ai's directory's copy installs by uvx (plugin_branch.py): this one keeps the install script.
        self.assertIn(f"curl -fsSL https://texttocad.dev/install.sh | sh -s -- --add {version}\n", skills["skills/cad/SKILL.md"])
        # Everything tracked under the plugin's roots ships, `.codex-plugin/` icons included,
        # plus exactly the files the archived manifest points at; nothing else from the repo.
        roots = set(git(REPO_ROOT, "ls-files", "--", *plugin_zip.ROOTS).split())
        interface = manifest["interface"]
        pointed_at = {value for name, value in interface.items() if name in plugin_zip.ICONS}
        pointed_at.update(interface.get("screenshots", []))
        if "mcpServers" in manifest:
            self.assertEqual(manifest["mcpServers"], "./.mcp.json")
            pointed_at.add("./.mcp.json")
        self.assertEqual(names, roots | {path[2:] for path in pointed_at})

    def test_every_skill_description_fits_the_hosts_limit(self):
        # Hosts refuse a skill whose description is over 1024 characters; fea's is a short router.
        checked = {}
        for path in sorted((REPO_ROOT / "skills").glob("*/SKILL.md")):
            fields, _ = plugin_zip.front_matter(path.read_bytes())
            checked[path.parent.name] = len(fields.get("description", ""))
        self.assertIn("fea", checked)
        for name, length in checked.items():
            with self.subTest(skill=name):
                self.assertTrue(0 < length <= 1024, f"{name}'s description is {length} characters")
        self.assertLess(checked["fea"], 600)

    def test_mcp_config_moves_to_the_root_and_refused_values_fail(self):
        manifest = {
            "name": "demo", "version": "1.0.0", "description": "Demo plugin.", "author": {"name": "Demo"},
            "skills": "./skills/", "mcpServers": "./codex.mcp.json",
            "interface": {"displayName": "Demo", "shortDescription": "Demo things", "longDescription": "Demo.",
                          "developerName": "Demo", "category": "Productivity", "capabilities": []},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".codex-plugin").mkdir()
            (root / "skills/demo").mkdir(parents=True)
            (root / "skills/demo/SKILL.md").write_text("---\nname: demo\ndescription: Demo.\n---\nRun `cad +1.0.0 x`.\n",
                                                      encoding="utf-8")
            server = {"command": "uvx", "args": ["--from", "cad-mcp==1.0.0", "cad-mcp"]}
            (root / "codex.mcp.json").write_text(json.dumps({"mcpServers": {"cad": server}}), encoding="utf-8")
            git(root, "init", "-q")

            def build(manifest: dict, out: Path | None = None) -> list[str]:
                (root / ".codex-plugin/plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
                git(root, "add", "-A")
                return plugin_zip.build(root, out).errors

            self.assertEqual(build(manifest, root / "out.zip"), [])
            with zipfile.ZipFile(root / "out.zip") as archive:
                self.assertEqual(json.loads(archive.read(".codex-plugin/plugin.json"))["mcpServers"],
                                 "./.mcp.json")
                # The package is OpenAI's directory's copy, on its channel: its launcher is told the channel as
                # its argument, and every pin carries it.
                self.assertEqual(json.loads(archive.read(".mcp.json"))["mcpServers"]["cad"],
                                 {**server, "args": [*server["args"], "--channel", "codex"]})
                self.assertNotIn("codex.mcp.json", archive.namelist())
                self.assertIn(b"Run `cad +1.0.0@codex x`.", archive.read("skills/demo/SKILL.md"))

            # A config that gives Codex a startup timeout tells the launcher the same number; one that is no
            # positive number of seconds fails the package.
            for timeout, args, errors in ((300.0, ["--startup-timeout", "300"], []), (45.5, ["--startup-timeout", "45.5"], []),
                                          ("300", None, [".mcp.json's startup_timeout_sec"]),
                                          (0, None, [".mcp.json's startup_timeout_sec"])):
                with self.subTest(timeout=timeout):
                    (root / "codex.mcp.json").write_text(json.dumps(
                        {"mcpServers": {"cad": {**server, "startup_timeout_sec": timeout}}}), encoding="utf-8")
                    found = build(manifest, root / "out.zip")
                    self.assertEqual([error.split(" is not")[0] for error in found], errors)
                    if args is not None:
                        with zipfile.ZipFile(root / "out.zip") as archive:
                            self.assertEqual(json.loads(archive.read(".mcp.json"))["mcpServers"]["cad"]["args"],
                                             [*server["args"], "--channel", "codex", *args])
            (root / "codex.mcp.json").write_text(json.dumps({"mcpServers": {"cad": server}}), encoding="utf-8")

            # A pin of another version, or a file whose pins cannot be read, fails the package.
            (root / "skills/demo/notes.md").write_bytes("caf\u00e9 `cad +0.9.0 x`".encode("latin-1"))
            self.assertEqual(sorted(error.split(":")[0] for error in build(manifest)), ["skills/demo/notes.md"])
            (root / "skills/demo/notes.md").write_text("`cad +0.9.0 x`", encoding="utf-8")
            self.assertEqual(build(manifest), ["skills/demo/notes.md: cad +0.9.0 is not stamped @codex for 1.0.0"])
            (root / "skills/demo/notes.md").unlink()

            # The portal refuses a subtitle over 30 characters (main's, until this check).
            change = {"interface": {**manifest["interface"], "shortDescription": "Design physical products with AI."}}
            self.assertTrue(any("plugin_short_description_too_long" in error for error in build({**manifest, **change})))


if __name__ == "__main__":
    unittest.main()
