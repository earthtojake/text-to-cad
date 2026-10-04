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
        # The plugin is at the archive's root, each folder with an entry of its own: the
        # portal turned away a top-level folder without one as holding no plugin.
        names = {name for name in members if not name.endswith("/")}
        self.assertEqual({name for name in members if name.endswith("/")},
                         {f"{folder}/" for folder in plugin_zip.folders(names)})
        self.assertIn(".codex-plugin/", members)
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

    def test_mcp_config_moves_to_the_root_and_refused_values_fail(self):
        manifest = {
            "name": "demo", "version": "1.0.0", "description": "Demo plugin.", "author": {"name": "Demo"},
            "skills": "./skills/", "mcpServers": "./codex.mcp.json",
            "interface": {"displayName": "Demo", "shortDescription": "Demo things", "longDescription": "Demo.",
                          "developerName": "Demo", "category": "Productivity", "capabilities": []},
            "extensions": {"com.openai": {"onboardingSkill": "./skills/cad-setup/SKILL.md"}},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".codex-plugin").mkdir()
            (root / "skills/cad-setup").mkdir(parents=True)
            (root / "skills/cad-setup/SKILL.md").write_text("---\nname: cad-setup\ndescription: Set up.\n---\nSteps.\n",
                                                        encoding="utf-8")
            server = {"command": "uvx", "args": ["--from", "cadgen==1.0.0", "cadgen", "mcp"]}
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
                # The package names its channel, OpenAI's directory, as its server's `--channel`, which
                # analytics report; `--auto-updated` leaves the copy to the directory, which updates it.
                self.assertEqual(json.loads(archive.read(".mcp.json"))["mcpServers"]["cad"],
                                 {**server, "args": [*server["args"], "--channel", "openai-directory", "--auto-updated"]})
                self.assertNotIn("codex.mcp.json", archive.namelist())

            # The portal refuses both: a subtitle over 30 characters (main's, until this
            # check) and an onboarding skill named instead of given as its SKILL.md path.
            for change, code in (
                ({"interface": {**manifest["interface"], "shortDescription": "Give your agent CAD superpowers."}},
                 "plugin_short_description_too_long"),
                ({"extensions": {"com.openai": {"onboardingSkill": "setup"}}}, "onboardingSkill"),
            ):
                with self.subTest(code=code):
                    self.assertTrue(any(code in error for error in build({**manifest, **change})))


if __name__ == "__main__":
    unittest.main()
