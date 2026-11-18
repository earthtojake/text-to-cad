"""The rehearsals' private computers on every system, held where this machine can fake the other one.

``scripts/test/real_computer.py`` and ``scripts/test/rehearse-update.py`` run on Windows too, where a first pass
showed: a run's uv folder in the temporary folder, which is inside the person's profile, refused by the isolation
check; 0.10's ``cad.cmd`` not taken for a shipped release's command; the process listing refused in a service's
session; telemetry kept on by a server that goes by the kept choice. Each is held here, the standard library alone.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import REPO_ROOT
from tests.python.support.tmp_root import temporary_directory

sys.path.insert(0, str(REPO_ROOT / "scripts" / "test"))
import real_computer as rc  # noqa: E402

sys.path.pop(0)


def _rehearsal():
    spec = importlib.util.spec_from_file_location("rehearse_update", REPO_ROOT / "scripts/test/rehearse-update.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class UvFolder(unittest.TestCase):
    def test_a_run_folder_in_the_temporary_folder_is_allowed_and_the_persons_own_are_not(self):
        with temporary_directory(prefix="rehearsal-") as root:
            home = Path(root) / "home"
            local = home / "AppData" / "Local"
            environ = {"LOCALAPPDATA": str(local), "APPDATA": str(home / "AppData" / "Roaming")}
            for windows, temp in ((True, local / "Temp" / "crr.1" / "uv"), (False, Path(root) / "tmp" / "crr.1" / "uv")):
                with self.subTest(windows=windows):
                    refused = lambda path: rc.uv_refused(path, home, environ, windows, darwin=False)  # noqa: E731
                    self.assertFalse(refused(temp))
                    self.assertTrue(refused(home))
                    self.assertTrue(refused(Path(root)))  # holds the home
                    self.assertTrue(refused(home / ".local" / "bin" / "x"))
                    self.assertTrue(refused(home / ".codex"))
            self.assertTrue(rc.uv_refused(local / "uv" / "cache", home, environ, True, darwin=False))
            self.assertTrue(rc.uv_refused(home / ".cache" / "uv", home, environ, False, darwin=False))
            # The person's own uv settings name folders of theirs too.
            named = Path(root) / "elsewhere" / "uv-cache"
            self.assertTrue(rc.uv_refused(named / "x", home, {**environ, "UV_CACHE_DIR": str(named)}, False, False))


class CadCommands(unittest.TestCase):
    def test_a_shipped_cad_cmd_is_found_beside_or_without_cad_exe(self):
        rehearsal = _rehearsal()
        with temporary_directory(prefix="rehearsal-") as root:
            folder = Path(root)
            self.assertEqual([path.name for path in rc.cad_commands(folder, windows=True)], ["cad.exe", "cad.cmd"])
            (folder / "cad.cmd").write_text("@echo off\r\nrem cad proxy: 10\r\n", encoding="utf-8")
            there = [path for path in rc.cad_commands(folder, windows=True) if path.exists()]
            self.assertEqual([path.name for path in there], ["cad.cmd"])
            self.assertTrue(rehearsal.launcher(there[0]))
            (folder / "cad.exe").write_bytes(b"MZ uv's trampoline")
            there = [path for path in rc.cad_commands(folder, windows=True) if path.exists()]
            self.assertEqual([path.name for path in there], ["cad.exe", "cad.cmd"])
            self.assertEqual([path.name for path in there if rehearsal.launcher(path)], ["cad.cmd"])


class Processes(unittest.TestCase):
    def test_on_windows_the_programs_in_the_computer_or_its_uv_folder_and_a_refusal_said(self):
        with temporary_directory(prefix="rehearsal-") as root:
            work, uv = Path(root) / "work", Path(root) / "uv"
            computer = rc.Computer(work, {}, shared=uv, helpers=())
            images = [(11, str(work / "state" / "releases" / "0.10.4" / "Scripts" / "python.exe")),
                      (12, str(uv / "python" / "cpython-3.14" / "python.exe")),
                      (13, str(Path(root) / "elsewhere" / "python.exe"))]
            with mock.patch.object(rc, "WINDOWS", True), mock.patch.object(rc, "windows_images", return_value=images):
                self.assertEqual([pid for pid, _image in computer.processes()], [11, 12])
                self.assertTrue(computer.looked)
            with mock.patch.object(rc, "WINDOWS", True), mock.patch.object(rc, "windows_images", return_value=None):
                self.assertEqual(computer.processes(), [])
                self.assertFalse(computer.looked)


class RealInstallNeeds(unittest.TestCase):
    def test_no_git_or_no_checkout_is_one_line_and_the_tag_is_looked_for(self):
        spec = importlib.util.spec_from_file_location("real_install", REPO_ROOT / "scripts/test/real-install.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with mock.patch.object(module.shutil, "which", return_value=None):
            missing, tagged = module.needs()
        self.assertIn("git is not on PATH", missing)
        self.assertFalse(tagged)
        # A folder outside any checkout (the tests' own temporary folders may lie inside this one).
        with tempfile.TemporaryDirectory() as root, mock.patch.object(module, "REPO_ROOT", Path(root)):
            missing, _tagged = module.needs()
        self.assertIn("is not a git checkout", missing)


class Sentinels(unittest.TestCase):
    """Claude Desktop rewrites its config by itself (its preferences) while it runs: the watch on the machine's own
    files compares what an install could change there, its MCP servers, and every other file by its time."""

    def test_claude_desktop_config_is_watched_by_its_mcp_servers_alone(self):
        config = {"mcpServers": {"x": {"command": "x"}}, "preferences": {"sidebarMode": "chat"}}
        same = {"preferences": {"sidebarMode": "task", "quickEntry": True}, "mcpServers": {"x": {"command": "x"}}}
        self.assertEqual(rc.servers_of(json.dumps(config).encode()), rc.servers_of(json.dumps(same, indent=2).encode()))
        for changed in ({**config, "mcpServers": {"x": {"command": "x"}, "cad": {"command": "cad"}}},
                        {**config, "mcpServers": {"x": {"command": "y"}}}, {"preferences": config["preferences"]}):
            with self.subTest(changed=changed):
                self.assertNotEqual(rc.servers_of(json.dumps(config).encode()), rc.servers_of(json.dumps(changed).encode()))
        # A file that is not a JSON object is compared by its bytes.
        self.assertEqual(rc.servers_of(b"{broken"), rc.servers_of(b"{broken"))
        self.assertNotEqual(rc.servers_of(b"{broken"), rc.servers_of(b"{broken!"))

    def test_a_rewrite_of_the_preferences_moves_nothing_and_a_server_or_another_file_does(self):
        with temporary_directory(prefix="rehearsal-") as root:
            home = Path(root)
            desktop = home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
            desktop.parent.mkdir(parents=True)
            desktop.write_text(json.dumps({"preferences": {"a": 1}}), encoding="utf-8")
            codex = home / ".codex" / "config.toml"
            codex.parent.mkdir()
            codex.write_text("", encoding="utf-8")

            def here():
                with mock.patch.object(rc.Path, "home", return_value=home), mock.patch.object(rc, "WINDOWS", False), \
                        mock.patch.object(rc.sys, "platform", "darwin"):
                    return rc.Sentinels.here()

            before = here()
            desktop.write_text(json.dumps({"preferences": {"a": 2}}), encoding="utf-8")
            self.assertEqual(before.moved(here()), [])
            desktop.write_text(json.dumps({"preferences": {"a": 2}, "mcpServers": {"cad": {}}}), encoding="utf-8")
            self.assertEqual([line.split(":", 1)[0] for line in before.moved(here())], [str(desktop)])
            desktop.write_text(json.dumps({"preferences": {"a": 2}}), encoding="utf-8")
            stamp = codex.stat().st_mtime_ns + 5_000_000_000
            os.utime(codex, ns=(stamp, stamp))
            self.assertEqual([line.split(":", 1)[0] for line in before.moved(here())], [str(codex)])


class Stamp(unittest.TestCase):
    def test_a_rehearsal_stamps_this_trees_major_and_minor_with_a_patch_far_above_a_real_one(self):
        self.assertEqual(rc.stamp(9123, "0.12.3"), "0.12.9123")
        self.assertEqual(rc.stamp(version="1.0.0"), "1.0.9999")
        major, minor = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip().split(".")[:2]
        self.assertEqual(rc.stamp(), f"{major}.{minor}.9999")
        with self.assertRaises(ValueError):
            rc.stamp(12, "0.12.3")


class Telemetry(unittest.TestCase):
    def test_each_computer_keeps_telemetry_off_as_the_persons_choice(self):
        with temporary_directory(prefix="rehearsal-") as root:
            computer = rc.Computer(Path(root) / "work", {}, helpers=())
            kept = json.loads((computer.state / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(kept["telemetry"]["choice"], "off")
            (computer.state / "settings.json").write_text('{"telemetry": {"choice": "on"}}', encoding="utf-8")
            rc.quiet(computer.state)  # never over a choice kept already
            self.assertEqual(json.loads((computer.state / "settings.json").read_text(encoding="utf-8"))["telemetry"]["choice"], "on")


if __name__ == "__main__":
    unittest.main()
