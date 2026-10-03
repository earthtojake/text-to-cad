"""The development install: scripts/install/dev_install.py.

What it writes is checked here, in temporary folders; the agent apps it hands that to cannot run
in a test.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from tests.python.support.paths import REPO_ROOT

spec = importlib.util.spec_from_file_location("dev_install", REPO_ROOT / "scripts/install/dev_install.py")
dev_install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dev_install)


class DevPluginTests(unittest.TestCase):
    def test_every_plugin_host_gets_the_skills_and_this_checkouts_server(self) -> None:
        manifests = {"claude": ".claude-plugin/plugin.json", "codex": ".codex-plugin/plugin.json",
                     "cursor": ".cursor-plugin/plugin.json", "grok": ".claude-plugin/plugin.json",
                     "gemini": "gemini-extension.json"}
        skills = sorted(path.parent.name for path in (REPO_ROOT / "skills").glob("*/SKILL.md"))
        with tempfile.TemporaryDirectory() as scratch:
            for host in dev_install.PLUGIN_HOSTS:
                with self.subTest(host=host):
                    plugin = Path(scratch) / host
                    server = dev_install.server_entry(host, "/venv/bin/python", Path("/pages/1"))
                    dev_install.assemble(host, plugin, "1.2.3-dev.1", server)
                    manifest = json.loads((plugin / manifests[host]).read_text(encoding="utf-8"))
                    self.assertEqual((manifest["name"], manifest["version"]), (dev_install.plugin_name(), "1.2.3-dev.1"))
                    servers = manifest["mcpServers"]  # Gemini keeps them inline; the rest name a file
                    if isinstance(servers, str):
                        servers = json.loads((plugin / servers).read_text(encoding="utf-8"))["mcpServers"]
                    self.assertEqual(servers, {"cad": server})
                    self.assertEqual(server["env"], {"CADGEN_MCP_APP_DIR": "/pages/1"})
                    self.assertEqual(sorted(path.parent.name for path in plugin.glob("skills/*/SKILL.md")), skills)
                    self.assertFalse(list(plugin.rglob("__pycache__")))
                    for icon in (manifest.get("logo"), manifest.get("interface", {}).get("logo")):
                        if icon:
                            self.assertTrue((plugin / icon).is_file(), icon)

    def test_the_skills_launch_command_follows_the_servers_runtime(self) -> None:
        # The dev server runs the checkout's .venv; the copied skills must run it too, or the
        # agent's scripts would use the release's installation and a daemon of their own.
        commands = {"cadgen": "/w/.venv/bin/python -m cadgen.cli", "python": "/w/.venv/bin/python"}
        with tempfile.TemporaryDirectory() as scratch:
            plugin = Path(scratch) / "claude"
            dev_install.assemble("claude", plugin, "1.2.3-dev.1", {"command": "x"}, commands=commands)
            for skill in plugin.glob("skills/*/SKILL.md"):
                text = skill.read_text(encoding="utf-8")
                with self.subTest(skill=skill.parent.name):
                    self.assertNotIn("--from cadgen==", text)
                    if "below means" in text:
                        self.assertIn("`cadgen` below means `/w/.venv/bin/python -m cadgen.cli`", text)
                        self.assertIn("`python` below means `/w/.venv/bin/python`", text)

    def test_wheel_mode_runs_one_wheel_for_the_server_and_the_skills(self) -> None:
        import argparse
        from unittest import mock

        wheel = Path("/w/tmp/codex-dev/wheels/1/cadgen-1.2.3-py3-none-any.whl")
        with mock.patch.object(dev_install, "build_wheel", return_value=wheel):
            server, commands, page = dev_install.runtime("codex", argparse.Namespace(wheel=True, build=False), "v")
        self.assertEqual(server["args"], [*dev_install.LAUNCHER[1:], str(wheel), "cadgen", "mcp"])
        self.assertEqual(commands["cadgen"], " ".join((*dev_install.LAUNCHER, str(wheel), "cadgen")))
        self.assertIsNone(page, "a wheel serves the page it was built with")

    def test_this_scripts_launcher_is_cadgens(self) -> None:
        import sys

        sys.path.insert(0, str(REPO_ROOT / "packages" / "cadgen" / "src"))
        from cadgen._internal.launch import LAUNCHER

        self.assertEqual(dev_install.LAUNCHER, LAUNCHER)

    def test_this_repositorys_skills_installed_loose_are_found_and_others_are_not(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            folder = Path(scratch) / "skills"
            for name, body in (("cad", (REPO_ROOT / "skills/cad/SKILL.md").read_text(encoding="utf-8")),
                               ("theirs", "---\nname: theirs\ndescription: x\n---\nNot ours.\n")):
                (folder / name).mkdir(parents=True)
                (folder / name / "SKILL.md").write_text(body, encoding="utf-8")
            self.assertEqual(dev_install.loose_skills([folder, Path(scratch) / "absent"]), [folder / "cad"])
        # The check reads each skill's provenance line, so every skill must keep one.
        for skill in (REPO_ROOT / "skills").glob("*/SKILL.md"):
            self.assertIn(dev_install.PROVENANCE, skill.read_text(encoding="utf-8"), skill)


if __name__ == "__main__":
    unittest.main()
