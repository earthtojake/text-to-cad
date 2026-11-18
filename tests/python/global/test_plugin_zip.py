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
                # The skills are the checkout's, byte for byte: each setup block installs cad by uv's line, the
                # same in every copy.
                version = manifest["version"]
                skills = {name: archive.read(name).decode("utf-8") for name in members
                          if name.startswith("skills/") and not name.endswith("/")}
                changed = [name for name, text in skills.items()
                           if text != (REPO_ROOT / name).read_text(encoding="utf-8")]
                server = json.loads(archive.read(".mcp.json"))["mcpServers"]["cad"]
        # Every copy's server line is the repository's: uvx runs cad at the release, as `cad mcp`.
        self.assertEqual(server["args"], json.loads((REPO_ROOT / "codex.mcp.json").read_text(encoding="utf-8"))["mcpServers"]["cad"]["args"])
        self.assertEqual(server["args"][-2:], [f"cad@{version}", "mcp"])
        # The plugin is at the archive's root, each folder with an entry of its own: the
        # portal turned away a top-level folder without one as holding no plugin.
        names = {name for name in members if not name.endswith("/")}
        self.assertEqual({name for name in members if name.endswith("/")},
                         {f"{folder}/" for folder in plugin_zip.folders(names)})
        self.assertIn(".codex-plugin/", members)
        self.assertEqual(changed, [])
        for name in (name for name in skills if name.endswith("/SKILL.md")):
            self.assertIn("run `uv tool install cad`", skills[name], name)
            self.assertNotIn(plugin_zip.INSTALL_SCRIPT, skills[name], name)
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
            block = ("---\nname: demo\ndescription: Demo.\n---\nWritten for `cad==1.0.0`. If `cad` is missing, run "
                     "`uv tool install cad`.\n\nWhen it says so.\n")
            (root / "skills/demo/SKILL.md").write_text(block, encoding="utf-8")
            server = {"command": "uvx", "args": ["cad@1.0.0", "mcp"]}
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
                # The server config moves to the root as it is; the skill is the checkout's as it is.
                self.assertEqual(json.loads(archive.read(".mcp.json"))["mcpServers"]["cad"], server)
                self.assertNotIn("codex.mcp.json", archive.namelist())
                self.assertEqual(archive.read("skills/demo/SKILL.md").decode("utf-8"), block)

            # Our install script named anywhere, in a skill or beside it, or a file that is not UTF-8 fails the package.
            for name, text in (("SKILL.md", block + "Or, on Windows: irm https://www.texttocad.dev/install.ps1 | iex\n"),
                               ("notes.md", "Or run curl -fsSL https://texttocad.dev/install.sh | sh"),
                               ("notes.md", "caf\u00e9")):
                with self.subTest(name=name, text=text[-30:]):
                    path = root / "skills/demo" / name
                    before = path.read_bytes() if path.exists() else None
                    path.write_bytes(text.encode("latin-1" if text == "caf\u00e9" else "utf-8"))
                    self.assertEqual({error.split(":")[0] for error in build(manifest)}, {f"skills/demo/{name}"})
                    if before is None:
                        path.unlink()
                    else:
                        path.write_bytes(before)
            self.assertEqual(build(manifest), [])

            # The portal refuses a subtitle over 30 characters (main's, until this check).
            change = {"interface": {**manifest["interface"], "shortDescription": "Design physical products with AI."}}
            self.assertTrue(any("plugin_short_description_too_long" in error for error in build({**manifest, **change})))


if __name__ == "__main__":
    unittest.main()
