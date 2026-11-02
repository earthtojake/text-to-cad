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
from unittest import mock

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
                    server = dev_install.server_entry(host, "/venv/bin/python", Path("/pages/1"), "1.2.3-dev.1")
                    dev_install.assemble(host, plugin, "1.2.3-dev.1", server)
                    manifest = json.loads((plugin / manifests[host]).read_text(encoding="utf-8"))
                    self.assertEqual((manifest["name"], manifest["version"]), (dev_install.plugin_name(), "1.2.3-dev.1"))
                    servers = manifest["mcpServers"]  # Gemini keeps them inline; the rest name a file
                    if isinstance(servers, str):
                        servers = json.loads((plugin / servers).read_text(encoding="utf-8"))["mcpServers"]
                    self.assertEqual(servers, {"cad": server})
                    self.assertEqual(server["env"], {"CAD_INSTALL_CHANNEL": "dev", "CAD_MCP_APP_DIR": "/pages/1",
                                                     "CAD_INSTALLATION_VERSION": "1.2.3-dev.1"})
                    self.assertEqual(sorted(path.parent.name for path in plugin.glob("skills/*/SKILL.md")), skills)
                    self.assertFalse(list(plugin.rglob("__pycache__")))
                    for icon in (manifest.get("logo"), manifest.get("interface", {}).get("logo")):
                        if icon:
                            self.assertTrue((plugin / icon).is_file(), icon)

    def test_the_skills_never_send_the_agent_to_the_release_s_installer(self) -> None:
        # The dev server runs the checkout's .venv, made the current installation, which the `cad` command
        # the skills run runs; the release's installer would put the published release over it.
        with tempfile.TemporaryDirectory() as scratch, mock.patch.dict("os.environ", {"CAD_LAUNCHER_DIR": ""}):
            rewrites = dev_install.skill_rewrites()
            # Every rewrite matches text in the skills: one that matches nothing is dead.
            documents = "".join(skill.read_text(encoding="utf-8") for skill in (REPO_ROOT / "skills").glob("*/SKILL.md"))
            for released_text in rewrites:
                self.assertIn(released_text, documents, "a rewrite that matches nothing in the skills")
            plugin = Path(scratch) / "claude"
            dev_install.assemble("claude", plugin, "1.2.3-dev.1", {"command": "x"}, rewrites=rewrites)
            note = f"This is a development install of {dev_install.REPO_ROOT}; do not run the install command here"
            for skill in plugin.glob("skills/*/SKILL.md"):
                text = skill.read_text(encoding="utf-8")
                with self.subTest(skill=skill.parent.name):
                    for command in dev_install.INSTALL_COMMANDS:
                        self.assertNotIn(command, text)
                    if "## Setup" in text:
                        self.assertIn(f"```bash\n# {note}\n```\n", text)
                        self.assertIn(f"On Windows, in PowerShell: `{note}`.", text)

    def test_wheel_mode_registers_one_wheel_for_the_server_and_the_skills(self) -> None:
        import argparse

        with tempfile.TemporaryDirectory() as scratch:
            # One build's three wheels, side by side: the library's, the server's and the shim's.
            built = Path(scratch) / "wheels" / "1"
            built.mkdir(parents=True)
            library, wheel, shim = (built / f"{name}-1.2.3-py3-none-any.whl"
                                    for name in ("cad", "cad_server", "cad_mcp"))
            for path in (library, wheel, shim):
                path.write_bytes(b"")
            with mock.patch.object(dev_install, "build_wheel", return_value=wheel), \
                    mock.patch.object(dev_install, "dev_root", return_value=Path(scratch)), \
                    mock.patch.object(dev_install, "run", return_value="/state/installations/v.json\n") as run:
                server, rewrites, page = dev_install.runtime("codex", argparse.Namespace(wheel=True, build=False), "v")
                # Its record is kept, for --uninstall to take out.
                self.assertEqual(json.loads((Path(scratch) / "installations.json").read_text(encoding="utf-8")),
                                 {"v": "/state/installations/v.json"})
        # The app starts the shim's wheel; the server's, with the library's beside it, is registered.
        self.assertEqual((server["args"], server["env"]),
                         ([*dev_install.LAUNCHER[1:], str(shim), "cad-mcp"],
                          {"CAD_INSTALL_CHANNEL": "dev", "CAD_INSTALLATION_VERSION": "v"}))
        uvx = [*dev_install.LAUNCHER[:-1], "--with", str(library), dev_install.LAUNCHER[-1], str(wheel)]
        # The server's installation registers as this install's version, by its own python.
        run.assert_called_once_with(*uvx, "python", "-c", dev_install.REGISTER, "v", capture=True)
        self.assertEqual(rewrites, dev_install.skill_rewrites())
        self.assertIsNone(page, "a wheel serves the page it was built with")

    def test_this_scripts_launcher_and_install_command_are_the_servers(self) -> None:
        import sys

        from tests.python.support.paths import add_sources

        add_sources()
        from cad_server._internal.launch import LAUNCHER
        from cad_server.updates import INSTALL, INSTALL_WINDOWS

        self.assertEqual(dev_install.LAUNCHER, LAUNCHER)
        self.assertEqual(dev_install.INSTALL_COMMANDS, (INSTALL, INSTALL_WINDOWS))

    def test_it_reads_the_apps_through_the_servers_providers(self) -> None:
        # One reading of the agent apps for both installers: the development one loads the server's by path.
        self.assertEqual(Path(dev_install.providers.__file__).resolve(),
                         REPO_ROOT / "packages" / "cad-server" / "src" / "cad_server" / "_internal" / "providers.py")
        self.assertIs(dev_install.loose_skills, dev_install.providers.loose_skills)
        self.assertEqual(dev_install.skill_folders("codex"), dev_install.providers.skill_folders("codex"))

    def test_this_repositorys_skills_installed_loose_are_found_and_others_are_not(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            folder = Path(scratch) / "skills"
            for name, body in (("cad", (REPO_ROOT / "skills/cad/SKILL.md").read_text(encoding="utf-8")),
                               ("theirs", "---\nname: theirs\ndescription: x\n---\nNot ours.\n")):
                (folder / name).mkdir(parents=True)
                (folder / name / "SKILL.md").write_text(body, encoding="utf-8")
            self.assertEqual(dev_install.loose_skills([folder, Path(scratch) / "absent"]), [folder / "cad"])
        # The check reads the repository each skill's front matter names, so every skill must name it.
        for skill in (REPO_ROOT / "skills").glob("*/SKILL.md"):
            front_matter = skill.read_text(encoding="utf-8").split("\n---\n", 1)[0]
            self.assertIn(f"\nmetadata:\n  repository: {dev_install.PROVENANCE}\n", front_matter + "\n", skill)


if __name__ == "__main__":
    unittest.main()
