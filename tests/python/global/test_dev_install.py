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
                    self.assertEqual(server["env"], {"CADGEN_INSTALL_CHANNEL": "dev", "CADGEN_MCP_APP_DIR": "/pages/1",
                                                     "CADGEN_INSTALLATION_VERSION": "1.2.3-dev.1"})
                    self.assertEqual(sorted(path.parent.name for path in plugin.glob("skills/*/SKILL.md")), skills)
                    self.assertFalse(list(plugin.rglob("__pycache__")))
                    for icon in (manifest.get("logo"), manifest.get("interface", {}).get("logo")):
                        if icon:
                            self.assertTrue((plugin / icon).is_file(), icon)

    def test_the_skills_run_the_version_the_server_registers(self) -> None:
        # The dev server runs the checkout's .venv, registered as this install's own version; the
        # copied skills must run that version, or the agent's scripts would run the release's
        # installation and a daemon of their own.
        released = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        with tempfile.TemporaryDirectory() as scratch, mock.patch.dict("os.environ", {"CADGEN_LAUNCHER_DIR": ""}):
            rewrites = dev_install.skill_rewrites(released, "1.2.3-dev.1", python="/w/.venv/bin/python")
            # Every rewrite matches text in the documents it rewrites: one that matches nothing is dead.
            documents = "".join(path.read_text(encoding="utf-8") for skill in (REPO_ROOT / "skills").glob("*/SKILL.md")
                                for path in (skill, skill.parent / "references" / "setup.md") if path.is_file())
            for released_text in rewrites:
                self.assertIn(released_text, documents, "a rewrite that matches nothing in the skills")
            plugin = Path(scratch) / "claude"
            dev_install.assemble("claude", plugin, "1.2.3-dev.1", {"command": "x"}, rewrites=rewrites)
            for skill in plugin.glob("skills/*/SKILL.md"):
                setup = skill.parent / "references" / "setup.md"
                text = skill.read_text(encoding="utf-8") + (setup.read_text(encoding="utf-8") if setup.is_file() else "")
                with self.subTest(skill=skill.parent.name):
                    self.assertNotIn("--from cadgen==", text)
                    self.assertNotIn(f"+{released}`", text)
                    # Never the release's installer over this checkout's engine.
                    for command in dev_install.INSTALL_COMMANDS:
                        self.assertNotIn(command, text)
                    if "below means" in text:
                        self.assertIn("`cadgen` below means `cadgen +1.2.3-dev.1`", text)
                        self.assertIn("`python` below means `cadgen +1.2.3-dev.1 run`", text)
                        self.assertIn("it says 1.2.3-dev.1 is not installed", text)
                        self.assertIn("/w/.venv/bin/python -m cad_server.cli doctor`", text)

    def test_wheel_mode_registers_one_wheel_for_the_server_and_the_skills(self) -> None:
        import argparse

        wheel = Path("/w/tmp/codex-dev/wheels/1/cadgen-1.2.3-py3-none-any.whl")
        with tempfile.TemporaryDirectory() as scratch, mock.patch.object(dev_install, "build_wheel", return_value=wheel), \
                mock.patch.object(dev_install, "dev_root", return_value=Path(scratch)), \
                mock.patch.object(dev_install, "run", return_value="/state/installations/v.json\n") as run:
            server, rewrites, page = dev_install.runtime("codex", argparse.Namespace(wheel=True, build=False), "v")
            # Its record is kept, for --uninstall to take out.
            self.assertEqual(json.loads((Path(scratch) / "installations.json").read_text(encoding="utf-8")),
                             {"v": "/state/installations/v.json"})
        self.assertEqual((server["args"], server["env"]),
                         ([*dev_install.LAUNCHER[1:], str(wheel), "cadgen", "mcp"],
                          {"CADGEN_INSTALL_CHANNEL": "dev", "CADGEN_INSTALLATION_VERSION": "v"}))
        # The wheel's installation registers as this install's version, by its own python.
        run.assert_called_once_with(*dev_install.LAUNCHER, str(wheel), "python", "-c", dev_install.REGISTER, "v",
                                    capture=True)
        released = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertTrue(rewrites[dev_install.launch("cadgen", released)].endswith(f"--from {wheel} cadgen"))
        self.assertEqual(rewrites[f"cadgen +{released}"], "cadgen +v")
        self.assertIsNone(page, "a wheel serves the page it was built with")

    def test_the_install_command_becomes_a_note_in_the_setup_guide_and_history_is_left(self) -> None:
        released, named = "1.2.3", "1.2.3-dev.1"
        with tempfile.TemporaryDirectory() as scratch, mock.patch.dict("os.environ", {"CADGEN_LAUNCHER_DIR": ""}):
            root = Path(scratch) / "source"
            skill = root / "skills/fixture"
            (skill / "references").mkdir(parents=True)
            (root / ".claude-plugin").mkdir()
            (root / ".claude-plugin/plugin.json").write_text(json.dumps({"name": "text-to-cad", "version": released}),
                                                            encoding="utf-8")
            main = ("---\nname: fixture\ndescription: fixture\n---\n"
                    f"`cadgen` below means `cadgen +{released}`. [Setup](references/setup.md)\n")
            guide = ("```bash\n" + dev_install.INSTALL_COMMANDS[0] + "\n```\n"
                     + f"On Windows, in PowerShell: `{dev_install.INSTALL_COMMANDS[1]}`. Restart the\n"
                     + dev_install.launch("cadgen", released) + " doctor\n"
                     + rf"%USERPROFILE%\.local\bin\cadgen.cmd +{released}" + "\n")
            (skill / "SKILL.md").write_text(main, encoding="utf-8")
            (skill / "references/setup.md").write_text(guide, encoding="utf-8")
            (skill / "references/migrations.md").write_text(guide, encoding="utf-8")
            rewrites = dev_install.skill_rewrites(released, named, python="/w/python")
            plugin = Path(scratch) / "plugin"
            dev_install.assemble("claude", plugin, named, {"command": "x"}, root=root, rewrites=rewrites)
            copied = (plugin / "skills/fixture/references/setup.md").read_text(encoding="utf-8")
            note = f"This is a development install of {dev_install.REPO_ROOT}; do not run the install command here"
            self.assertIn(f"```bash\n# {note}\n```\n", copied)
            self.assertIn(f"On Windows, in PowerShell: `{note}`. Restart the\n", copied)
            self.assertIn("/w/python -m cad_server.cli doctor", copied)
            self.assertIn(f"cadgen.cmd +{named}", copied)
            self.assertIn(f"`cadgen +{named}`", (plugin / "skills/fixture/SKILL.md").read_text(encoding="utf-8"))
            # A migration reference may name an old release on purpose: copied as it is.
            self.assertEqual((plugin / "skills/fixture/references/migrations.md").read_text(encoding="utf-8"), guide)

    def test_this_scripts_launcher_and_install_command_are_cadgens(self) -> None:
        import sys

        from tests.python.support.paths import add_sources

        add_sources()
        from cad_server._internal.launch import LAUNCHER
        from cad_server.updates import INSTALL, INSTALL_WINDOWS

        self.assertEqual(dev_install.LAUNCHER, LAUNCHER)
        self.assertEqual(dev_install.INSTALL_COMMANDS, (INSTALL, INSTALL_WINDOWS))

    def test_it_reads_the_apps_through_cadgens_providers(self) -> None:
        # One reading of the agent apps for both installers: the development one loads cadgen's by path.
        self.assertEqual(Path(dev_install.providers.__file__).resolve(),
                         REPO_ROOT / "packages" / "texttocad-server" / "src" / "cad_server" / "_internal" / "providers.py")
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
        # The check reads each skill's provenance line, so every skill must keep one.
        for skill in (REPO_ROOT / "skills").glob("*/SKILL.md"):
            self.assertIn(dev_install.PROVENANCE, skill.read_text(encoding="utf-8"), skill)


if __name__ == "__main__":
    unittest.main()
