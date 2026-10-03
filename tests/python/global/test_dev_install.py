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
        manifests = {"codex": ".codex-plugin/plugin.json", "claude": ".claude-plugin/plugin.json",
                     "cursor": ".cursor-plugin/plugin.json", "grok": ".claude-plugin/plugin.json"}
        skills = dev_install.skill_names()
        with tempfile.TemporaryDirectory() as scratch:
            for host in dev_install.PLUGIN_HOSTS:
                with self.subTest(host=host):
                    plugin = Path(scratch) / host
                    server = dev_install.server_entry(host, "/venv/bin/python", Path("/pages/1"))
                    dev_install.assemble(host, plugin, "1.2.3-dev.1", server)
                    manifest = json.loads((plugin / manifests[host]).read_text(encoding="utf-8"))
                    self.assertEqual((manifest["name"], manifest["version"]), (dev_install.plugin_name(), "1.2.3-dev.1"))
                    self.assertEqual(json.loads((plugin / manifest["mcpServers"]).read_text(encoding="utf-8")),
                                     {"mcpServers": {"cad": server}})
                    self.assertEqual(server["env"], {"CADGEN_MCP_APP_DIR": "/pages/1"})
                    self.assertEqual(sorted(path.parent.name for path in plugin.glob("skills/*/SKILL.md")), skills)
                    self.assertFalse(list(plugin.rglob("__pycache__")))
                    for icon in (manifest.get("logo"), manifest.get("interface", {}).get("logo")):
                        if icon:
                            self.assertTrue((plugin / icon).is_file(), icon)


class SkillLinkTests(unittest.TestCase):
    def test_links_are_this_checkouts_own_and_nothing_else_is_touched(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root, destination = Path(scratch) / "checkout", Path(scratch) / "agent" / "skills"
            for name in ("alpha", "beta"):
                (root / "skills" / name).mkdir(parents=True)
                (root / "skills" / name / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
            destination.mkdir(parents=True)
            (destination / "theirs").mkdir()
            (destination / "retired").symlink_to(root / "skills" / "retired", target_is_directory=True)

            done = dev_install.link_skills(destination, root)
            self.assertEqual(done, ["removed retired (retired)", "linked alpha", "linked beta"])
            self.assertEqual((destination / "alpha").resolve(), (root / "skills" / "alpha").resolve())
            self.assertEqual(dev_install.link_skills(destination, root), [])

            self.assertEqual(dev_install.unlink_skills(destination, root), ["removed alpha", "removed beta"])
            self.assertEqual([path.name for path in destination.iterdir()], ["theirs"])


if __name__ == "__main__":
    unittest.main()
