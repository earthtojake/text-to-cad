"""The development install: scripts/install/dev_install.py.

What it writes is checked here, in temporary folders; the agent apps it hands that to cannot run
in a test.
"""

from __future__ import annotations

import importlib.util
import json
import os
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
                                                     "CADGEN_INSTALLATION_VERSION": "1.2.3-dev.1",
                                                     **({"CADGEN_PORT": os.environ["CADGEN_PORT"]} if os.environ.get("CADGEN_PORT") else {})})
                    self.assertEqual(sorted(path.parent.name for path in plugin.glob("skills/*/SKILL.md")), skills)
                    self.assertFalse(list(plugin.rglob("__pycache__")))
                    for icon in (manifest.get("logo"), manifest.get("interface", {}).get("logo")):
                        if icon:
                            self.assertTrue((plugin / icon).is_file(), icon)

    def test_the_skills_run_the_version_the_server_registers(self) -> None:
        # CLI verbs, `cadgen run` among them, use the registered dev install; an environment of
        # one's own installs the checkout editable, rather than the release from PyPI.
        released = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        checkout = dev_install.REPO_ROOT / "packages" / "cadgen"
        with tempfile.TemporaryDirectory() as scratch, mock.patch.dict("os.environ", {"CADGEN_LAUNCHER_DIR": ""}):
            rewrites = dev_install.skill_rewrites(released, "1.2.3-dev.1", python="/w/.venv/bin/python")
            # Every rewrite matches text in the documents it rewrites: one that matches nothing is dead.
            documents = "".join(path.read_text(encoding="utf-8") for skill in (REPO_ROOT / "skills").glob("*/SKILL.md")
                                for path in (skill, skill.parent / "references" / "setup.md",
                                             skill.parent / "references" / "model-contract.md") if path.is_file())
            for released_text in rewrites:
                self.assertIn(released_text, documents, "a rewrite that matches nothing in the skills")
            plugin = Path(scratch) / "claude"
            dev_install.assemble("claude", plugin, "1.2.3-dev.1", {"command": "x"}, rewrites=rewrites)
            for skill in plugin.glob("skills/*/SKILL.md"):
                main = skill.read_text(encoding="utf-8")
                setup = skill.parent / "references" / "setup.md"
                text = main + (setup.read_text(encoding="utf-8") if setup.is_file() else "")
                with self.subTest(skill=skill.parent.name):
                    self.assertNotIn("--from cadgen==", text)
                    self.assertNotIn(f"+{released}`", text)
                    # Never the release's installer over this checkout's engine.
                    for command in dev_install.INSTALL_COMMANDS:
                        self.assertNotIn(command, text)
                    if "below means" in text:
                        proxy = Path(dev_install.launcher_dir()).expanduser() / ("cadgen.cmd" if os.name == "nt" else "cadgen")
                        self.assertIn(f"`cadgen` below means `{proxy} +1.2.3-dev.1`", text)
                        if skill.parent.name in {"cad", "dxf", "engineering-drawing"}:
                            self.assertIn("Run models with `cadgen run model.py`.", main)
                        self.assertIn(f"uv pip install --python <python> -e {checkout}", text)
                        self.assertIn(f"uv run --with-editable {checkout} pytest", text)
                        self.assertNotIn(f"cadgen=={released}", text)
                        self.assertIn("/w/.venv/bin/python -m cadgen.cli doctor", text)

    def test_an_independent_copy_rewrites_setup_and_windows_pins_but_preserves_history(self) -> None:
        released, named = "1.2.3", "1.2.3-dev.1"
        with tempfile.TemporaryDirectory() as scratch, mock.patch.dict("os.environ", {"CADGEN_LAUNCHER_DIR": ""}):
            root = Path(scratch) / "source"
            skill = root / "skills/fixture"
            (skill / "references").mkdir(parents=True)
            (root / ".claude-plugin").mkdir()
            (root / ".claude-plugin/plugin.json").write_text(json.dumps({"name": "text-to-cad", "version": released}), encoding="utf-8")
            main = ("---\nname: fixture\ndescription: fixture\n---\n"
                    f"`cadgen` below means `~/.local/bin/cadgen +{released}`.\n"
                    "Use MCP's advertised port. [Setup](references/setup.md) [History](references/migrations.md).\n")
            guide = ("```bash\n" + dev_install.INSTALL_COMMANDS[0] + "\n```\n"
                     + f"On Windows, in PowerShell: `{dev_install.INSTALL_COMMANDS[1]}`. Restart the\n"
                     + dev_install.launch("cadgen", released) + " doctor\n"
                     + dev_install.launch("cadgen", released) + " server\n"
                     + f"uv pip install --python <python> cadgen=={released}\n"
                     + f"uv run --with cadgen=={released} pytest\n"
                     + rf"%USERPROFILE%\.local\bin\cadgen.cmd +{released}" + "\n")
            history = guide  # Even a historical example of this release is outside runtime rewriting.
            (skill / "SKILL.md").write_text(main, encoding="utf-8")
            (skill / "references/setup.md").write_text(guide, encoding="utf-8")
            (skill / "references/migrations.md").write_text(history, encoding="utf-8")
            for wheel in (None, Path("/w/cadgen.whl")):
                with self.subTest(wheel=wheel):
                    rewrites = dev_install.skill_rewrites(released, named, python="/w/python", wheel=wheel)
                    plugin = Path(scratch) / ("wheel" if wheel else "editable")
                    dev_install.assemble("claude", plugin, named,
                                         {"command": "x", "env": {"CADGEN_PORT": "4567"}}, root=root, rewrites=rewrites)
                    copied_main = (plugin / "skills/fixture/SKILL.md").read_text(encoding="utf-8")
                    copied_guide = (plugin / "skills/fixture/references/setup.md").read_text(encoding="utf-8")
                    self.assertTrue(copied_main.startswith("---\nname: fixture\n"))
                    self.assertIn(f"+{named}`", copied_main)
                    self.assertIn(f"cadgen.cmd +{named}", copied_guide)
                    for copied in (copied_main, copied_guide):
                        self.assertIn("CADGEN_PORT=4567", copied)
                        self.assertNotIn(f"cadgen=={released}", copied)
                    note = f"This is a development install of {dev_install.REPO_ROOT}; do not run the install command here"
                    self.assertIn(f"```bash\n# {note}\n```\n", copied_guide)
                    self.assertIn(f"On Windows, in PowerShell: `{note}`. Restart the\n", copied_guide)
                    checkout = dev_install.REPO_ROOT / "packages/cadgen"
                    if wheel:
                        self.assertIn(f"--from {wheel} cadgen doctor", copied_guide)
                        self.assertIn(f"uv pip install --python <python> {wheel}\n", copied_guide)
                        self.assertIn(f"uv run --with {wheel} pytest\n", copied_guide)
                    else:
                        self.assertIn("/w/python -m cadgen.cli doctor", copied_guide)
                        self.assertIn(f"uv pip install --python <python> -e {checkout}\n", copied_guide)
                        self.assertIn(f"uv run --with-editable {checkout} pytest\n", copied_guide)
                    self.assertEqual((plugin / "skills/fixture/references/migrations.md").read_text(encoding="utf-8"), history)
            self.assertEqual((skill / "SKILL.md").read_text(encoding="utf-8"), main)
            self.assertEqual((skill / "references/setup.md").read_text(encoding="utf-8"), guide)

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
                          {"CADGEN_INSTALL_CHANNEL": "dev", "CADGEN_INSTALLATION_VERSION": "v",
                           **({"CADGEN_PORT": os.environ["CADGEN_PORT"]} if os.environ.get("CADGEN_PORT") else {})}))
        # The wheel's installation registers as this install's version, by its own python.
        run.assert_called_once_with(*dev_install.LAUNCHER, str(wheel), "python", "-c", dev_install.REGISTER, "v",
                                    capture=True)
        released = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertTrue(rewrites[dev_install.launch("cadgen", released)].endswith(f"--from {wheel} cadgen"))
        proxy = Path(dev_install.launcher_dir()).expanduser() / ("cadgen.cmd" if os.name == "nt" else "cadgen")
        self.assertEqual(rewrites[f"~/.local/bin/cadgen +{released}"], f"{proxy} +v")
        self.assertEqual(rewrites[f"uv pip install --python <python> cadgen=={released}"],
                         f"uv pip install --python <python> {wheel}")
        self.assertEqual(rewrites[f"uv run --with cadgen=={released}"], f"uv run --with {wheel}")
        self.assertIsNone(page, "a wheel serves the page it was built with")
        self.assertIs(server["required"], True, "Codex blocks on CAD as the release's codex.mcp.json does")

    def test_the_codex_server_is_required_as_the_release_s_is(self) -> None:
        release = json.loads((REPO_ROOT / "codex.mcp.json").read_text(encoding="utf-8"))["mcpServers"]["cad"]
        server = dev_install.server_entry("codex", "/venv/bin/python", Path("/pages"))
        self.assertEqual(server["required"], release["required"])
        self.assertNotIn("required", dev_install.server_entry("claude", "/venv/bin/python", Path("/pages")))

    def test_explicit_port_reaches_the_server_and_project_instructions(self) -> None:
        import argparse

        released = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        wheel = Path("/w/cadgen.whl")
        with mock.patch.dict("os.environ", {"CADGEN_PORT": "4567"}):
            server = dev_install.server_entry("claude", "/venv/bin/python", Path("/pages"))
            self.assertEqual(server["env"]["CADGEN_PORT"], "4567")
            rewrites = dev_install.skill_rewrites(released, "dev", python="/venv/bin/python")
            with tempfile.TemporaryDirectory() as scratch:
                plugin = Path(scratch) / "plugin"
                dev_install.assemble("claude", plugin, "dev", server, rewrites=rewrites)
                for document in (plugin / "skills/cad/SKILL.md", plugin / "skills/cad/references/setup.md"):
                    self.assertIn("CADGEN_PORT=4567", document.read_text(encoding="utf-8"))
            with mock.patch.object(dev_install, "build_wheel", return_value=wheel), \
                    mock.patch.object(dev_install, "register"):
                wheel_server, _, _ = dev_install.runtime("codex", argparse.Namespace(wheel=True, build=False), "dev")
            self.assertEqual(wheel_server["env"]["CADGEN_PORT"], "4567")
        for invalid in ("0", "65536", "bad"):
            with self.subTest(port=invalid), mock.patch.dict("os.environ", {"CADGEN_PORT": invalid}):
                with self.assertRaises(dev_install.Refused):
                    dev_install.server_entry("claude", "/venv/bin/python", Path("/pages"))

    def test_this_scripts_launcher_and_install_command_are_cadgens(self) -> None:
        import sys

        sys.path.insert(0, str(REPO_ROOT / "packages" / "cadgen" / "src"))
        from cadgen._internal.launch import LAUNCHER
        from cadgen.updates import INSTALL, INSTALL_WINDOWS

        self.assertEqual(dev_install.LAUNCHER, LAUNCHER)
        self.assertEqual(dev_install.INSTALL_COMMANDS, (INSTALL, INSTALL_WINDOWS))

    def test_it_reads_the_apps_through_cadgens_providers(self) -> None:
        # One reading of the agent apps for both installers: the development one loads cadgen's by path.
        self.assertEqual(Path(dev_install.providers.__file__).resolve(),
                         REPO_ROOT / "packages" / "cadgen" / "src" / "cadgen" / "_internal" / "providers.py")
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
