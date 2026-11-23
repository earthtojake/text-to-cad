"""cad's own update (``cad_server/_internal/auto_update.py``, its helper ``auto_update_helper.py``, ``cad update auto``,
``cad plugin``, and the starts that meet a newer server): on by default, for a global install alone; ``on`` only for
one; no update without the feed or to an older release; the idle rule; the helper's command lines on POSIX and Windows,
and what it runs, in order, never a ``cad plugin`` command; the server's rule for that command (``plugin_catch_up``): once
where cad is newer than the release the plugin is up to date for, however cad got there, bounded; each ended attempt
counted once (``auto_update.report``); a start that joins a newer server; a start that failed still updating. No test
reaches the real feed or PyPI, or runs uv, and every one runs on a computer of its own (``Case``: a temporary home, a
PATH of its own stand-ins), so none is a mock away from the agent apps of the computer it runs on."""

from __future__ import annotations

import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import cad_server
from cad.engine import client
from cad.engine.previous import version
from cad_server import updates
from cad_server._internal import auto_update, auto_update_helper as helper
from cad_server.cli import auto_update as command, plugin as plugin_command
from tests.python.support.agent_apps import a_home_of_its_own

RECEIPT = '[tool]\nrequirements = [{ name = "cad", specifier = "==0.1.0" }]\nentrypoints = [{ name = "cad" }]\n'
BOUNDED = "cad>=0.1.0,<1"  # the requirement of 0.1.0's upgrade: inside its major, never below it (``auto_update.bound``)


class Case(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(__import__("shutil").rmtree, self.tmp, ignore_errors=True)
        self.state = self.tmp / "state"
        self.home = self.tmp / "home"
        self.tool = self.tmp / "tools" / "cad"  # a uv tool's environment
        self.tool.mkdir(parents=True)
        (self.tool / "uv-receipt.toml").write_text(RECEIPT, encoding="utf-8")
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.uv = self.bin / ("uv.exe" if os.name == "nt" else "uv")
        self.uv.write_text("", encoding="utf-8")
        self.uv.chmod(0o755)
        # An engine folder of its own, where no server runs: the switches written here (``SwitchesTest``), never by
        # the server the runner started for this file (``ServerSwitchesTest`` starts one of its own).
        self.engine = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None))
        self.addCleanup(__import__("shutil").rmtree, self.engine, ignore_errors=True)
        # A home of its own, and PATH the stand-ins alone: ``cad plugin`` is run here, and what it would find and
        # change, were a test's mock ever to miss, is this folder's and no agent app's.
        a_home_of_its_own(self, self.home, self.bin)
        for patch in (mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.state),
                                                   "CAD_ENGINE_DIR": str(self.engine)}),
                      mock.patch.object(sys, "prefix", str(self.tool)),
                      mock.patch.object(cad_server, "__version__", "0.1.0"),
                      mock.patch.object(updates, "checking", return_value=True)):
            patch.start()
            self.addCleanup(patch.stop)

    def feed(self, latest: str | None, lines: dict | None = None):
        """The feed as last read, ``{"latest", "lines"}`` (no ``lines``: a feed with ``latest`` alone)."""
        return mock.patch.object(updates, "feed", return_value=None if latest is None else
                                 {"latest": latest, **({"lines": lines} if lines is not None else {})})

    def cli(self, *argv: str, main=None) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = (main or command.main)(list(argv))
            except SystemExit as leaving:
                code = leaving.code
        return code, out.getvalue(), err.getvalue()

    def kept(self) -> dict:
        return json.loads((self.state / "settings.json").read_text(encoding="utf-8"))


class GlobalInstallTest(Case):
    def test_a_global_install_is_one_an_installer_made_and_says_how_it_updates(self) -> None:
        found = auto_update.global_install()
        self.assertEqual((found.installer.name, found.prefix), ("uv", self.tool))
        self.assertEqual([os.path.normcase(part) for part in found.program], [os.path.normcase(str(self.uv))])
        self.assertEqual(found.launcher, auto_update.tool_command(self.tool))
        uv = found.installer
        self.assertEqual(uv.upgrade(["uv"], "0.1.0"), ["uv", "tool", "install", "--upgrade", "cad>=0.1.0,<1"],
                         "inside the major of the release that runs, never below it, and no Python flags")
        self.assertEqual(uv.cross(["uv"], "0.1.0"), ["uv", "tool", "install", "--upgrade", "cad>=0.1.0"],
                         "`cad update --major`: the floor alone, never below the release that runs")
        self.assertEqual(uv.put_back(["uv"], "0.1.0"),
                         ["uv", "tool", "install", "--managed-python", "--python", "3.14", "cad==0.1.0"])
        self.assertEqual(uv.launchers(["uv"]), ["uv", "tool", "dir", "--bin"])
        self.assertEqual(uv.environ(self.tool), {}, "uv's commands need nothing of the server's environment changed")
        carried = self.tmp / "carried" / "uv"
        carried.parent.mkdir()
        carried.write_text("", encoding="utf-8")
        with mock.patch.object(auto_update, "find_uv", return_value=None):
            with mock.patch.object(auto_update, "carried_uv", return_value=str(carried)):
                self.assertEqual(auto_update.global_install().program, [str(carried)], "the uv cad carries")
            with mock.patch.object(auto_update, "carried_uv", return_value=None):
                self.assertIsNone(auto_update.global_install().program, "a global install whose installer is not found")
        for receipt in (None, '[tool]\nrequirements = [{ name = "other" }, { name = "cad" }]\n', "not toml ["):
            with self.subTest(receipt=receipt):
                if receipt is None:
                    (self.tool / "uv-receipt.toml").unlink(missing_ok=True)
                else:
                    (self.tool / "uv-receipt.toml").write_text(receipt, encoding="utf-8")
                self.assertIsNone(auto_update.global_install())
        (self.tool / "uv-receipt.toml").write_text('[tool]\nrequirements = ["cad==0.1.0"]\n', encoding="utf-8")
        self.assertEqual(auto_update.uv_tool(), self.tool, "a receipt's requirement as a string")

    def test_the_bound_is_the_major_of_the_release_that_runs_and_its_floor_that_release(self) -> None:
        for version, bound in (("0.11.12", "cad>=0.11.12,<1"), ("0.12.0", "cad>=0.12.0,<1"), ("1.4.2", "cad>=1.4.2,<2"),
                               ("9.0.0", "cad>=9.0.0,<10"), ("10.2.3", "cad>=10.2.3,<11")):
            with self.subTest(version=version):
                self.assertEqual(auto_update.bound(version), bound)
        for version in ("0.11.12-dev.1", "1.0", "", None):
            with self.subTest(version=version), self.assertRaises(ValueError):
                auto_update.bound(version)

    def test_another_installer_is_one_more_entry(self) -> None:
        other = auto_update.Installer(name="other", owns=lambda prefix: (prefix / "other.json").is_file(),
                                      find=lambda: ["/o/other"], upgrade=lambda other, version: [*other, "up", version],
                                      cross=lambda other, version: [*other, "up", "--all"],
                                      put_back=lambda other, release: [*other, "add", f"cad=={release}"],
                                      launchers=lambda other: [*other, "bin"])
        (self.tool / "uv-receipt.toml").unlink()
        (self.tool / "other.json").write_text("{}", encoding="utf-8")
        with mock.patch.object(auto_update, "INSTALLERS", (auto_update.UV, auto_update.PIPX, other)):
            found = auto_update.global_install()
            self.assertEqual((found.installer.name, found.program), ("other", ["/o/other"]))
            line = auto_update.helper_command(None, now=1.0, version="0.1.0", base="/py", install=found)
        self.assertEqual(json.loads(line[5])["cad"], str(auto_update.tool_command(self.tool)))
        told = json.loads(line[5])
        self.assertEqual((told["upgrade"], told["put_back"], told["launchers"]),
                         (["/o/other", "up", "0.1.0"], ["/o/other", "add", "cad==0.1.0"], ["/o/other", "bin"]))
        line = auto_update.helper_command(None, now=1.0, version="0.1.0", base="/py", install=found, major=True)
        self.assertEqual(json.loads(line[5])["upgrade"], ["/o/other", "up", "--all"])


class SwitchesTest(Case):
    def test_on_by_default_for_a_global_install_and_off_and_on_kept(self) -> None:
        self.assertEqual(auto_update.switches(), {"on": True}, "nothing kept: on")
        self.assertEqual(self.cli(), (0, "update auto: on\n", ""))
        self.assertEqual(self.cli("off"), (0, "update auto: off\n", ""))
        self.assertEqual(self.kept()["auto_update"], {"on": False})
        self.assertEqual(self.cli("status"), (0, "update auto: off\n", ""))
        self.assertEqual(self.cli("on"), (0, "update auto: on\n", ""))
        self.assertEqual(self.kept()["auto_update"], {"on": True})
        self.assertEqual(self.cli("on", "--installer")[0], 2, "no --installer any more")

    def test_a_cad_that_is_no_global_install_says_so_and_on_is_refused(self) -> None:
        (self.tool / "uv-receipt.toml").unlink()
        self.assertEqual(self.cli(), (0, f"{command.NOT_GLOBAL}\n", ""))
        code, out, err = self.cli("on")
        self.assertEqual((code, out, err), (1, "", f"cad update auto: {command.REFUSED}\n"))
        self.assertFalse((self.state / "settings.json").exists(), "nothing written")


    def test_an_off_kept_by_0_11_stands_until_cad_update_auto_on(self) -> None:
        """0.10.0 to 0.11.11 kept a person's off as ``updates.automatic: false`` in the same settings file: where
        ``auto_update.on`` was never chosen, cad updates nothing and says it is off, and why; ``on`` writes ``true``,
        which wins, and the earlier key stays as it was."""
        from cad_server.cli import doctor
        from cad_server.settings import update_section

        update_section(auto_update.EARLIER_SECTION, lambda kept: {**kept, auto_update.EARLIER_KEY: False})
        self.assertEqual(auto_update.switches(), {"on": False, "earlier": True})
        self.assertEqual(self.cli(), (0, f"update auto: off{command.EARLIER}\n", ""))
        self.assertIn(f"update auto off{command.EARLIER},", doctor._update()[1])
        with self.feed("0.2.0", {"0": "0.2.0"}):
            self.assertIsNone(auto_update.due(), "nothing updates itself")
        self.assertEqual(self.cli("on"), (0, "update auto: on\n", ""))
        self.assertEqual((self.kept()["auto_update"], self.kept()["updates"]), ({"on": True}, {"automatic": False}))
        with self.feed("0.2.0", {"0": "0.2.0"}):
            self.assertEqual(auto_update.due(), auto_update.Due("0.2.0", "0.2.0"))

    def test_the_earlier_choice_counts_only_where_none_was_made_here_and_unreadable_is_on(self) -> None:
        self.state.mkdir(parents=True)
        settings = self.state / "settings.json"
        for new, old, on in ((None, False, False), (None, True, True), (None, None, True), (True, False, True),
                             (False, None, False), (False, True, False)):
            with self.subTest(new=new, old=old):
                settings.write_text(json.dumps({**({"auto_update": {"on": new}} if new is not None else {}),
                                                **({"updates": {"automatic": old}} if old is not None else {})}),
                                    encoding="utf-8")
                self.assertEqual(auto_update.switches()["on"], on)
        for broken in ("not json", '{"updates": "off"}', "[]"):
            with self.subTest(broken=broken):
                settings.write_text(broken, encoding="utf-8")
                self.assertEqual(auto_update.switches(), {"on": True})
        settings.unlink()
        settings.mkdir()  # there, and cannot be read
        self.assertEqual(auto_update.switches(), {"on": True})


class PluginSwitchTest(Case):
    def test_off_by_default_and_kept(self) -> None:
        self.assertFalse(auto_update.plugin_switch())
        run = lambda *argv: self.cli("update", "auto", *argv, main=plugin_command.main)  # noqa: E731
        self.assertEqual(run(), (0, "plugin update auto: off\n", ""))
        self.assertEqual(run("on"), (0, "plugin update auto: on\n", ""))
        self.assertEqual(self.kept()["plugin"], {"auto_update": True})
        self.assertEqual(run("status"), (0, "plugin update auto: on\n", ""))
        self.assertEqual(run("off"), (0, "plugin update auto: off\n", ""))
        self.assertEqual(self.kept()["plugin"], {"auto_update": False})
        self.assertEqual(self.kept().get("auto_update"), None, "cad's own switch untouched")

    def test_bare_cad_plugin_prints_its_help_and_refresh_does_nothing(self) -> None:
        code, out, err = self.cli(main=plugin_command.main)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("usage: cad plugin", out)
        self.assertEqual(self.cli("--refresh", main=plugin_command.main), (0, "", ""), "what 0.11.10's updater runs")
        from cad_server.cli import main as cad

        self.assertEqual(self.cli("plugin", "--refresh", main=cad), (0, "", ""))

    def test_a_run_of_the_command_here_would_see_a_computer_of_its_own(self) -> None:
        """What ``cad plugin install`` and ``cad plugin update`` take this computer to be (``computer.Here``), in a
        test of this file: a home in the test's folder, no command but the test's stand-ins, no app's folder named
        elsewhere. A run no mock stood in for finds no agent app, and changes nothing outside that folder."""
        from cad_server.plugin import apps, computer
        from tests.python.support.agent_apps import ELSEWHERE

        here = computer.Here()
        self.assertEqual((here.home, here.path_only), (self.home, True))
        places = [Path(folder) for folder in here.search_path().split(os.pathsep)]
        places += [here.config_home(), apps.claude_dir(here), apps.hermes_home(here), *here.state_dirs()]
        self.assertEqual([place for place in places if self.tmp not in place.parents], [])
        self.assertEqual([name for name in ELSEWHERE if name in os.environ], [])

    def test_a_run_a_server_began_has_a_deadline_and_a_hard_stop_and_a_person_s_neither(self) -> None:
        """``cad plugin install`` where this release's server began it (``CAD_PLUGIN_SERVER_RUN``) has
        ``INSTALL_SECONDS``, a hard stop armed for them before the run begins and let go as the command ends
        (``plugin_catch_up.HardStop``), and keeps how it ended in the server's record; typed by a person, or under the
        name an earlier release gives its server's run (``CAD_INSTALL_ATTEMPT``), it runs as long as it runs. What it runs, the
        deadline's effect and the stop's are ``tests/python/packages/cad_server/plugin/test_command.py``'s."""
        from cad_server._internal import auto_update_helper, plugin_catch_up
        from cad_server.plugin import run

        self.assertIsNone(plugin_catch_up.deadline(), "a person's own run")
        with mock.patch.dict(os.environ, {plugin_catch_up.ATTEMPT_ENV: "7.0"}):
            self.assertIsNone(plugin_catch_up.deadline(), "an earlier release's server's run")
        plugin_catch_up.noted("0.0.1")
        plugin_catch_up._change(lambda found: {**found, "release": "0.1.0", "at": 7.0, "tries": 1,
                                               "outcome": "underway"})
        stopped = run.Facts(by=run.SERVER, outcome=run.FAILED, code=124, stopped=True)
        steps = mock.Mock()
        steps.install.return_value = stopped
        with mock.patch.dict(os.environ, {plugin_catch_up.SERVER_ENV: "7.0"}), \
                mock.patch.object(run, "install", steps.install), \
                mock.patch.object(plugin_catch_up, "HardStop", steps.HardStop):
            self.assertEqual(plugin_catch_up.deadline(), auto_update_helper.INSTALL_SECONDS)
            self.assertEqual(self.cli("install", main=plugin_command.main)[0], 124)
        self.assertEqual([call[0] for call in steps.mock_calls],
                         ["HardStop", "install", "HardStop().over", "HardStop().cancel"])
        self.assertEqual(steps.HardStop.call_args.args, (float(auto_update_helper.INSTALL_SECONDS),))
        self.assertEqual({name: value for name, value in steps.install.call_args.kwargs.items() if name != "going"},
                         {"prog": "cad plugin install", "seconds": float(auto_update_helper.INSTALL_SECONDS)})
        found = plugin_catch_up.read()
        self.assertEqual((found["for"], found["outcome"], found["code"]), ("0.0.1", "failed", 124))
        # A crash lets the stop go too: no stop outlives its command.
        steps.reset_mock()
        steps.install.side_effect = RuntimeError("a mistake of ours")
        with mock.patch.dict(os.environ, {plugin_catch_up.SERVER_ENV: "7.0"}), \
                mock.patch.object(run, "install", steps.install), \
                mock.patch.object(plugin_catch_up, "HardStop", steps.HardStop), self.assertRaises(RuntimeError):
            plugin_command.main(["install"])
        self.assertEqual([call[0] for call in steps.mock_calls], ["HardStop", "install", "HardStop().cancel"])
        with mock.patch.object(run, "install", return_value=run.Facts(by=run.PERSON)) as ran, \
                mock.patch.object(plugin_catch_up, "HardStop") as stop:
            self.assertEqual(self.cli("update", main=plugin_command.main)[0], 0)
            self.assertEqual(self.cli("install", main=plugin_command.main)[0], 0)
            with mock.patch.dict(os.environ, {plugin_catch_up.ATTEMPT_ENV: "7.0"}):
                self.assertEqual(self.cli("install", main=plugin_command.main)[0], 0)
        self.assertEqual([call.kwargs["seconds"] for call in ran.call_args_list], [None] * 3)
        stop.assert_not_called()
        self.assertEqual(plugin_catch_up.read()["for"], "0.1.0", "ended with exit status 0: this cad's")

    def test_an_attempt_past_its_time_is_stopped_with_everything_it_started(self) -> None:
        """BRIDGE-ONLY. How the server stops an attempt of the hosted install command it began
        (``install_script._stop``): the command and what it started gone."""
        from cad.engine.places import detached
        from cad_server._internal import install_script

        pids = self.tmp / "pids"
        stand_in = self.tmp / "hangs.py"
        stand_in.write_text("import os, subprocess, sys, time\n"
                            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'])\n"
                            "with open(sys.argv[1] + '.part', 'w') as out:\n"
                            "    out.write(f'{os.getpid()} {child.pid}')\n"
                            "os.replace(sys.argv[1] + '.part', sys.argv[1])\n"
                            "time.sleep(600)\n", encoding="utf-8")
        process = subprocess.Popen([sys.executable, str(stand_in), str(pids)], stdin=subprocess.DEVNULL, **detached())
        self.addCleanup(_end, process.pid)
        deadline = time.monotonic() + 60
        while not pids.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        own, child = map(int, pids.read_text(encoding="utf-8").split())
        whole = install_script._stop(process)
        self.assertTrue(_gone(own), "the command itself, always")
        if whole:
            self.assertTrue(_gone(child), "and what it started")
        else:  # a Windows session where taskkill is refused (no interactive logon): said, never claimed
            self.addCleanup(_end, child)

    def test_a_refused_or_hung_taskkill_still_ends_the_process_itself_and_says_so(self) -> None:
        """On Windows, in a session with no interactive logon (SSH, a service), ``taskkill /T`` answers "Access denied"
        and ends nothing: ``_stop`` then ends the process itself, within its bound, and says the tree was not
        stopped. taskkill is a stand-in here; the process is real."""
        from cad_server._internal import install_script

        refused = subprocess.CompletedProcess(["taskkill"], 1)
        for answer in ({"return_value": refused}, {"side_effect": subprocess.TimeoutExpired("taskkill", 1)},
                       {"side_effect": OSError("no taskkill")}):
            with self.subTest(answer=answer):
                sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
                self.addCleanup(_end, sleeper.pid)
                with mock.patch.object(install_script.subprocess, "run", **answer) as taskkill:
                    self.assertFalse(install_script._stop(sleeper, windows=True, seconds=10.0))
                self.assertEqual(taskkill.call_args.args[0][:4], ["taskkill", "/T", "/F", "/PID"])
                self.assertIsNotNone(sleeper.poll(), "the process itself ended, and waited for")

class ServerSwitchesTest(Case):
    """Where a server runs, ``cad update auto on|off`` and ``cad plugin update auto on|off`` have it keep the switches
    (``{"op": "auto_update"}``, ``{"op": "plugin_auto_update"}``), so a shell whose sandbox may not write the state
    folder (Codex's: ``settings.lock: Operation not permitted``) needs no permission; whether this cad may turn its
    updates on is judged here, for the cad the command runs from."""

    def test_the_server_keeps_the_switches_and_the_global_install_rule_is_this_command_s(self) -> None:
        from tests.python.support import engine_daemon

        env = {**os.environ, "PATH": os.environ.get("PATH", ""), "CAD_UPDATE_CHECK": "0",
               "CAD_CACHE_DIR": str(self.tmp / "cache")}
        engine_daemon.start(env, self.addCleanup)
        refused = PermissionError(1, "Operation not permitted", "settings.lock")
        with mock.patch.object(auto_update, "change", side_effect=refused), \
                mock.patch.object(auto_update, "change_plugin", side_effect=refused):
            self.assertEqual(self.cli("off"), (0, "update auto: off\n", ""))
            self.assertEqual(auto_update.switches(), {"on": False}, "kept by the server, in the state folder")
            self.assertEqual(self.cli("on"), (0, "update auto: on\n", ""))
            self.assertEqual(self.cli("update", "auto", "on", main=plugin_command.main),
                             (0, "plugin update auto: on\n", ""))
            self.assertTrue(auto_update.plugin_switch())
            (self.tool / "uv-receipt.toml").unlink()  # this command's cad is no global install: refused before the server
            code, out, err = self.cli("on")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("not a global install", err)
        self.assertTrue(auto_update.switches()["on"])

    def test_with_no_server_or_one_that_does_not_know_how_the_command_writes_them_itself(self) -> None:
        with mock.patch.object(client, "request", return_value={"failed": "unknown request 'auto_update'"}) as asked:
            self.assertEqual(self.cli("off"), (0, "update auto: off\n", ""))
        self.assertEqual(asked.call_args.args[0], {"op": "auto_update", "on": False})
        self.assertEqual(asked.call_args.kwargs["start"], False, "a switch never starts a server")
        self.assertIs(self.kept()["auto_update"]["on"], False)
        with mock.patch.object(client, "request", return_value={"failed": "unknown request 'plugin_auto_update'"}):
            self.assertEqual(self.cli("update", "auto", "on", main=plugin_command.main),
                             (0, "plugin update auto: on\n", ""))
        with mock.patch.object(client, "request", return_value={"ok": True, "switches": {"on": True,
                                                                                          "installer": False}}):
            self.assertEqual(self.cli("on"), (0, "update auto: on\n", ""), "a server of 0.11.x keeps it too")
        with mock.patch.object(client, "request", return_value={"failed": "could not save it: disk full"}):
            code, _out, err = self.cli("on")
        self.assertEqual(code, 1)
        self.assertIn("could not save the choice: could not save it: disk full", err)
        self.assertFalse(auto_update.switches()["on"], "the server's failure is said, never written over here")

    def test_the_server_refuses_what_is_no_switch(self) -> None:
        from cad_server.engine.daemon import switch_auto_update, switch_plugin

        self.assertIn("failed", switch_auto_update({"op": "auto_update", "on": "yes"}))
        self.assertIn("failed", switch_plugin({"op": "plugin_auto_update"}))
        self.assertEqual(switch_auto_update({"op": "auto_update", "on": False, "installer": True, "ran_for": "0.1.0"}),
                         {"ok": True, "switches": {"on": False}}, "what an earlier command sends besides is not read")
        self.assertEqual(self.kept()["auto_update"], {"on": False})


class CarriedUvTest(Case):
    """Where the person's uv is not found, cad's update of a uv install runs the uv cad carries, copied out of cad's
    environment first: the update replaces that environment."""

    def test_the_carried_uv_is_copied_out_of_the_environment_and_the_helper_runs_the_copy(self) -> None:
        inside = self.tool / "bin" / "uv"  # where cad's `uv` dependency puts it: in the environment
        inside.parent.mkdir()
        inside.write_bytes(b"uv's binary")
        base = self.tmp / "python" / "bin" / "python3"
        with mock.patch.object(auto_update, "find_uv", return_value=None), \
                mock.patch.object(auto_update, "carried_uv", return_value=str(inside)), \
                mock.patch.object(sys, "_base_executable", str(base), create=True), \
                mock.patch.object(auto_update.subprocess, "Popen") as popen:
            self.assertEqual(auto_update.global_install().program, [str(inside)])
            self.assertTrue(auto_update.trigger("0.2.0"))
            told = json.loads(popen.call_args.args[0][5])
            copy = self.state / auto_update.UPDATE_UV / "uv"
            self.assertEqual((told["upgrade"][0], told["put_back"][0], told["launchers"][0]), (str(copy),) * 3)
            self.assertEqual(copy.read_bytes(), b"uv's binary")
            inside.write_bytes(b"uv's newer binary")  # another size: copied again
            auto_update._keep(self.state / auto_update.RECORD, {**auto_update.last(), "outcome": "failed"})
            self.assertTrue(auto_update.trigger("0.2.1"))
            self.assertEqual(copy.read_bytes(), b"uv's newer binary")
            self.assertEqual(sorted(path.name for path in copy.parent.iterdir()), ["uv"], "nothing left beside it")
        self.assertEqual(auto_update.outside_copy([str(self.uv)]), [str(self.uv)], "a uv outside: run as it is")
        self.assertEqual(auto_update.carried_uv() is not None, __import__("importlib.util").util.find_spec("uv")
                         is not None, "cad's own dependency, where it is installed")


class FindUvTest(Case):
    def test_path_first_then_the_installers_folders_and_never_this_environment_s(self) -> None:
        # On Windows ``shutil.which`` names the file with PATHEXT's case (``uv.EXE``): the same file.
        self.assertEqual(os.path.normcase(auto_update.find_uv() or ""), os.path.normcase(self.uv))
        home = self.tmp / "home"
        for folder, environ in ((home / ".local" / "bin", {}), (home / ".cargo" / "bin", {}),
                                (self.tmp / "xdg", {"XDG_BIN_HOME": str(self.tmp / "xdg")}),
                                (self.tmp / "own" / "bin", {"UV_INSTALL_DIR": str(self.tmp / "own")})):
            with self.subTest(folder=folder):
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "uv").write_text("", encoding="utf-8")
                found = auto_update.find_uv({"PATH": "", "HOME": str(home), **environ}, windows=False)
                self.assertEqual(found, str(folder / "uv"))
                (folder / "uv").unlink()
        (self.tool / "bin").mkdir()
        (self.tool / "bin" / "uv").write_text("", encoding="utf-8")  # cad's own dependency: replaced by the update
        (self.tool / "bin" / "uv").chmod(0o755)
        self.assertIsNone(auto_update.find_uv({"PATH": str(self.tool / "bin"), "HOME": str(home)}, windows=False))

    def test_on_windows_it_is_uv_exe_in_the_profile_s_folders(self) -> None:
        profile = self.tmp / "profile"
        (profile / ".local" / "bin").mkdir(parents=True)
        (profile / ".local" / "bin" / "uv.exe").write_text("", encoding="utf-8")
        self.assertEqual(auto_update.find_uv({"PATH": "", "USERPROFILE": str(profile), "HOME": "/nowhere"},
                                             windows=True), str(profile / ".local" / "bin" / "uv.exe"))


    def test_on_windows_a_batch_file_is_never_run_and_a_real_exe_on_path_is(self) -> None:
        """Windows runs a ``.cmd`` or ``.bat`` through cmd.exe, which reads the ``<`` and ``>`` of ``cad>=X,<N`` as
        redirections: where uv or pipx is on PATH only as one, it is not found; a real ``.exe`` of the same name is."""
        folder = self.tmp / "shims"
        folder.mkdir()
        exes: dict[str, str] = {}

        def which(name, path=None):  # Windows' own: PATHEXT's order, so a batch file where no .exe is there
            if name.endswith(".exe"):
                return exes.get(name)
            return {"uv": str(folder / "uv.cmd"), "pipx": str(folder / "pipx.bat")}.get(name)

        environ = {"PATH": str(folder), "USERPROFILE": str(self.tmp / "profile"), "HOME": "/nowhere"}
        pipx = lambda: auto_update.find_pipx(environ, prefix=str(self.tool), python=str(self.tmp / "none"),  # noqa: E731
                                             windows=True)
        for name in ("uv.cmd", "pipx.bat", "uv.exe", "pipx.exe"):
            (folder / name).write_text("", encoding="utf-8")
        with mock.patch.object(auto_update.shutil, "which", side_effect=which):
            self.assertIsNone(auto_update.find_uv(environ, windows=True))
            self.assertIsNone(pipx())
            exes.update({"uv.exe": str(folder / "uv.exe"), "pipx.exe": str(folder / "pipx.exe")})
            self.assertEqual(auto_update.find_uv(environ, windows=True), str(folder / "uv.exe"))
            self.assertEqual(pipx(), [str(folder / "pipx.exe")])
            exes["uv.exe"] = str(folder / "uv.cmd")  # whatever names it, a batch file is never one
            self.assertIsNone(auto_update.find_uv(environ, windows=True))


PIPX_METADATA = {"main_package": {"package": "cad", "package_or_url": "cad", "package_version": "0.1.0"},
                 "pipx_metadata_version": "0.12"}


class PipxTest(Case):
    """cad installed by ``pipx install cad``: a global install as uv's is, updated by pipx's own commands, pipx found as
    the person's install found it, and found from outside it (``installed_tool``) where uv has none."""

    def setUp(self) -> None:
        super().setUp()
        self.pipx_home = self.tmp / "pipx"
        self.env = self.pipx_home / "venvs" / "cad"  # pipx's environment of cad
        self.env.mkdir(parents=True)
        (self.env / "pipx_metadata.json").write_text(json.dumps(PIPX_METADATA), encoding="utf-8")
        self.pipx = self.bin / ("pipx.exe" if os.name == "nt" else "pipx")
        self.pipx.write_text("", encoding="utf-8")
        self.pipx.chmod(0o755)
        for patch in (mock.patch.object(sys, "prefix", str(self.env)),
                      mock.patch.object(auto_update, "PIPX_SYSTEM", ())):  # never this machine's own pipx
            patch.start()
            self.addCleanup(patch.stop)
        auto_update._has_pipx.cache_clear()
        self.addCleanup(auto_update._has_pipx.cache_clear)

    def test_a_cad_pipx_installed_is_a_global_install_updated_by_pipx_s_own_commands(self) -> None:
        found = auto_update.global_install()
        self.assertEqual((found.installer.name, found.prefix), ("pipx", self.env))
        self.assertEqual([os.path.normcase(part) for part in found.program], [os.path.normcase(str(self.pipx))])
        pipx = found.installer
        # Inside the major, for this upgrade alone (measured: pipx keeps no range, so a person's own `pipx upgrade
        # cad` takes the newest of all); one argument with no space or quote, which pipx's split leaves whole.
        self.assertEqual(pipx.upgrade(["pipx"], "0.1.0"), ["pipx", "upgrade", "cad", "--pip-args=cad>=0.1.0,<1"])
        self.assertEqual(pipx.upgrade(["pipx"], "1.4.2"), ["pipx", "upgrade", "cad", "--pip-args=cad>=1.4.2,<2"])
        # `cad update --major`: the floor alone, which replaces the range pipx 1.18 keeps (measured: a plain `pipx
        # upgrade cad` there stays inside it).
        self.assertEqual(pipx.cross(["pipx"], "0.1.0"), ["pipx", "upgrade", "cad", "--pip-args=cad>=0.1.0"])
        self.assertEqual(pipx.put_back(["pipx"], "0.1.0"), ["pipx", "install", "--force", "cad==0.1.0"])
        self.assertEqual(pipx.launchers(["pipx"]), ["pipx", "environment", "--value", "PIPX_BIN_DIR"])
        self.assertEqual(pipx.upgrade(["/py", "-P", "-m", "pipx"], "0.1.0"),
                         ["/py", "-P", "-m", "pipx", "upgrade", "cad", "--pip-args=cad>=0.1.0,<1"])
        self.assertEqual(pipx.environ(self.env), {"PIPX_HOME": str(self.pipx_home)}, "the home that holds venvs/cad")
        told = json.loads(auto_update.helper_command("0.2.0", now=1.0, version="0.1.0", base="/py", install=found)[5])
        self.assertEqual((told["cad"], told["prefix"], told["upgrade"], told["put_back"], told["launchers"]),
                         (str(auto_update.tool_command(self.env)), str(self.env),
                          [*found.program, "upgrade", "cad", "--pip-args=cad>=0.1.0,<1"],
                          [*found.program, "install", "--force", "cad==0.1.0"],
                          [*found.program, "environment", "--value", "PIPX_BIN_DIR"]))
        told = json.loads(auto_update.helper_command("1.0.0", now=1.0, version="0.1.0", base="/py", install=found,
                                                     major=True)[5])
        self.assertEqual((told["upgrade"], told["major"]),
                         ([*found.program, "upgrade", "cad", "--pip-args=cad>=0.1.0"], True))
        with self.feed("0.2.0"):
            self.assertEqual(auto_update.due(), auto_update.Due("0.2.0", "0.2.0"),
                             "automatic updates on by default, as for uv's")
            with mock.patch.object(auto_update, "find_pipx", return_value=None):
                self.assertIsNone(auto_update.global_install().program, "pipx not found")
                self.assertIsNone(auto_update.due(), "pipx not found: no automatic update")
                self.assertEqual(auto_update.asked(pypi=lambda: {"latest": "0.2.0", "lines": {}}),
                                 {"failed": auto_update.no_installer("pipx")})
        self.assertEqual(auto_update.no_installer("pipx"), "cad was installed with pipx, and the cad server cannot find "
                                                           "pipx, so it cannot update cad")
        self.assertEqual(self.cli(), (0, "update auto: on\n", ""))
        self.assertEqual(self.cli("off"), (0, "update auto: off\n", ""))
        self.assertEqual(self.cli("on"), (0, "update auto: on\n", ""), "on is a global install's to turn on")
        (self.env / "uv-receipt.toml").write_text(RECEIPT, encoding="utf-8")
        self.assertEqual(auto_update.global_install().installer.name, "uv", "uv's asked first")

    def test_what_is_not_pipx_s_cad(self) -> None:
        other = {"main_package": {**PIPX_METADATA["main_package"], "package": "other"}}
        for case, text in (("another package", json.dumps(other)), ("unreadable", "not json {"),
                           ("no main package", "{}"), ("none", None)):
            with self.subTest(case=case):
                if text is None:
                    (self.env / "pipx_metadata.json").unlink()
                else:
                    (self.env / "pipx_metadata.json").write_text(text, encoding="utf-8")
                self.assertIsNone(auto_update.global_install())
        for folder in (self.pipx_home / "venvs" / "cad_2", self.tmp / "elsewhere" / "cad"):  # a --suffix; not pipx's
            with self.subTest(folder=folder):
                folder.mkdir(parents=True)
                (folder / "pipx_metadata.json").write_text(json.dumps(PIPX_METADATA), encoding="utf-8")
                self.assertIsNone(auto_update.pipx_tool(str(folder)))
        self.assertEqual(auto_update.pipx_home(self.tmp / "elsewhere" / "cad"), {})

    def test_the_trigger_hands_the_helper_pipx_s_home_and_pipx_s_command_lines(self) -> None:
        base = self.tmp / "python" / "bin" / "python3"
        with mock.patch.object(sys, "_base_executable", str(base), create=True), \
                mock.patch.dict(os.environ, {"PIPX_HOME": str(self.tmp / "another")}), \
                mock.patch.object(auto_update.subprocess, "Popen") as popen:
            self.assertTrue(auto_update.trigger("0.2.0"))
        (line,), options = popen.call_args
        self.assertEqual(options["env"]["PIPX_HOME"], str(self.pipx_home), "the home of the cad that runs")
        told = json.loads(line[5])
        self.assertEqual(([os.path.normcase(part) for part in told["upgrade"][:1]], told["upgrade"][1:]),
                         ([os.path.normcase(str(self.pipx))], ["upgrade", "cad", "--pip-args=cad>=0.1.0,<1"]))

    def test_pipx_is_found_on_path_then_where_it_is_usually_installed_then_by_its_python(self) -> None:
        home = self.tmp / "home"
        found = lambda environ, **options: auto_update.find_pipx(  # noqa: E731
            {"PATH": "", "HOME": str(home), **environ}, prefix=str(self.env), python=str(self.tmp / "nopython"),
            windows=False, **options)
        self.assertEqual([os.path.normcase(part) for part in auto_update.find_pipx(windows=os.name == "nt")],
                         [os.path.normcase(str(self.pipx))], "on PATH")
        for folder, environ in ((self.tmp / "own", {"PIPX_BIN_DIR": str(self.tmp / "own")}),
                                (home / ".local" / "bin", {}), (home / "Library" / "Python" / "3.12" / "bin", {})):
            with self.subTest(folder=folder):
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "pipx").write_text("", encoding="utf-8")
                self.assertEqual(found(environ), [str(folder / "pipx")])
                (folder / "pipx").unlink()
        for version in ("3.9", "3.13"):  # pip install --user pipx, on macOS: the newest Python's first
            (home / "Library" / "Python" / version / "bin").mkdir(parents=True, exist_ok=True)
            (home / "Library" / "Python" / version / "bin" / "pipx").write_text("", encoding="utf-8")
        self.assertEqual(found({}), [str(home / "Library" / "Python" / "3.13" / "bin" / "pipx")])
        __import__("shutil").rmtree(home / "Library")
        (self.env / "bin").mkdir()
        (self.env / "bin" / "pipx").write_text("", encoding="utf-8")  # inside cad's environment: never that one
        self.assertIsNone(found({"PATH": str(self.env / "bin")}))
        python = self.tmp / "python3"
        python.write_text("", encoding="utf-8")
        with mock.patch.object(auto_update, "_has_pipx", return_value=True) as has:
            self.assertEqual(auto_update.find_pipx({"PATH": "", "HOME": str(home)}, prefix=str(self.env),
                                                   python=str(python), windows=False),
                             [str(python), "-P", "-m", "pipx"], "python -m pipx, by the Python that owns it")
            has.assert_called_once_with(str(python))
            self.assertIsNone(auto_update.find_pipx({"PATH": "", "HOME": str(home)}, prefix=str(self.tmp),
                                                    python=str(python), windows=False), "never a Python inside cad's")
        with mock.patch.object(auto_update, "_has_pipx", return_value=False):
            self.assertIsNone(auto_update.find_pipx({"PATH": "", "HOME": str(home)}, prefix=str(self.env),
                                                    python=str(python), windows=False))
        import importlib.util

        self.assertEqual(auto_update._has_pipx(sys.executable), importlib.util.find_spec("pipx") is not None)
        self.assertFalse(auto_update._has_pipx(str(self.tmp / "no such python")))

    def test_on_windows_pipx_exe_is_found_in_the_per_user_pythons_and_scoop(self) -> None:
        profile, appdata, local = self.tmp / "profile", self.tmp / "roaming", self.tmp / "local"
        environ = {"PATH": "", "USERPROFILE": str(profile), "APPDATA": str(appdata), "LOCALAPPDATA": str(local)}
        for folder in (appdata / "Python" / "Python313" / "Scripts", local / "Programs" / "Python" / "Python314" / "Scripts",
                       profile / "scoop" / "shims", profile / ".local" / "bin"):
            with self.subTest(folder=folder):
                folder.mkdir(parents=True)
                (folder / "pipx.exe").write_text("", encoding="utf-8")
                self.assertEqual(auto_update.find_pipx(environ, prefix=str(self.env), python=str(self.tmp / "none"),
                                                       windows=True), [str(folder / "pipx.exe")])
                (folder / "pipx.exe").unlink()

    def test_installed_tool_finds_uv_s_cad_first_then_pipx_s(self) -> None:
        uv_tools = self.tmp / "uv-tools"
        uv_tools.mkdir()
        own = auto_update.tool_command(self.env)
        own.parent.mkdir(parents=True)
        own.write_text("", encoding="utf-8")
        answers = {("tool", "dir"): str(uv_tools), ("environment", "--value"): str(self.pipx_home / "venvs")}
        asked: list[list[str]] = []

        def said(command, _timeout):
            asked.append(command)
            return answers.get(tuple(command[1:3]))

        with mock.patch.object(auto_update, "_said", side_effect=said):
            self.assertEqual(auto_update.installed_tool("uv", pipx=["pipx"]), self.env, "uv has no cad: pipx's")
            self.assertEqual(asked, [["uv", "tool", "dir"], ["pipx", "environment", "--value", "PIPX_LOCAL_VENVS"]])
            with mock.patch.object(auto_update, "find_pipx", return_value=["/p/pipx"]):
                self.assertEqual(auto_update.installed_tool("uv"), self.env, "pipx found as the update finds it")
            self.assertEqual(asked[-1], ["/p/pipx", "environment", "--value", "PIPX_LOCAL_VENVS"])
            with mock.patch.object(auto_update, "find_pipx", return_value=None):
                self.assertIsNone(auto_update.installed_tool("uv"), "no pipx: none")
            (uv_tools / "cad").mkdir()
            (uv_tools / "cad" / "uv-receipt.toml").write_text(RECEIPT, encoding="utf-8")
            auto_update.tool_command(uv_tools / "cad").parent.mkdir(parents=True)
            auto_update.tool_command(uv_tools / "cad").write_text("", encoding="utf-8")
            self.assertEqual(auto_update.installed_tool("uv", pipx=["pipx"]), uv_tools / "cad", "uv's wins")
            (uv_tools / "cad" / "uv-receipt.toml").unlink()
            own.unlink()
            self.assertIsNone(auto_update.installed_tool("uv", pipx=["pipx"]), "pipx's with no cad command of its own")
        with mock.patch.object(auto_update, "_said", side_effect=[OSError("no uv"), str(self.pipx_home / "venvs")]):
            own.write_text("", encoding="utf-8")
            self.assertEqual(auto_update.installed_tool("uv", pipx=["pipx"]), self.env, "uv cannot answer: pipx's")
        # pipx 1.0 (Ubuntu 22.04's) has no `pipx environment`: its list names cad's command inside the environment.
        listed = json.dumps({"venvs": {"cad": {"metadata": {"main_package": {"app_paths": [
            {"__Path__": str(own), "__type__": "Path"}]}}}}})
        with mock.patch.object(auto_update, "_said", side_effect=[None, None, listed]) as said_:
            self.assertEqual(auto_update.installed_tool("uv", pipx=["pipx"]), self.env)
        self.assertEqual(said_.call_args.args[0], ["pipx", "list", "--json"])
        with mock.patch.object(auto_update, "_said", side_effect=[None, None, json.dumps({"venvs": {}})]):
            self.assertIsNone(auto_update.installed_tool("uv", pipx=["pipx"]), "pipx 1.0 with no cad")

    def test_doctor_names_pipx(self) -> None:
        from cad_server.cli import doctor

        line = doctor._installer()
        self.assertEqual((line["name"], os.path.normcase(line["detail"])), ("pipx", os.path.normcase(str(self.pipx))))
        self.assertEqual(doctor._update()[1], f"update auto on, plugin update auto off; a global install by pipx "
                                              f"({self.env})")
        with mock.patch.object(auto_update, "find_pipx", return_value=None):
            self.assertEqual(doctor._installer()["detail"], "not found")
        (self.env / "pipx_metadata.json").unlink()
        self.assertEqual(doctor._installer()["name"], "uv", "no global install: the uv the update would use")


class DueTest(Case):
    Due = auto_update.Due

    def test_every_condition_and_forward_only(self) -> None:
        with self.feed("0.2.0"):
            self.assertEqual(auto_update.due(), self.Due("0.2.0", "0.2.0"), "on with nothing kept")
        for latest in (None, "0.1.0", "0.0.9", "0.2.0-dev.1", "garbage"):  # no answer, the same, older, no release
            with self.subTest(latest=latest), self.feed(latest):
                self.assertIsNone(auto_update.due())
        with self.feed("0.2.0"):
            with mock.patch.object(updates, "checking", return_value=False):  # CAD_UPDATE_CHECK=0, CI
                self.assertIsNone(auto_update.due())
            with mock.patch.object(auto_update, "find_uv", return_value=None), \
                    mock.patch.object(auto_update, "carried_uv", return_value=None):
                self.assertIsNone(auto_update.due())
            with mock.patch.object(sys, "prefix", str(self.tmp)):  # not a global install
                self.assertIsNone(auto_update.due())
            auto_update.change(False)
            self.assertIsNone(auto_update.due())

    def test_the_newest_release_of_this_major_and_never_a_higher_major(self) -> None:
        """The feed's ``lines`` name each major's newest: the update moves to this major's, never to a higher one, never
        back. A feed whose ``lines`` name none of this major still updates inside it, by the bounded upgrade."""
        for case, latest, lines, due in (
                ("this major newer", "0.2.0", {"0": "0.2.0"}, self.Due("0.2.0", "0.2.0")),
                ("both: this major's, never the higher", "1.3.0", {"0": "0.4.0", "1": "1.3.0"},
                 self.Due("0.4.0", "0.4.0")),
                ("a higher major alone, this major's not newer", "1.3.0", {"0": "0.1.0", "1": "1.3.0"}, None),
                ("this major's older than this cad", "1.3.0", {"0": "0.0.9", "1": "1.3.0"}, None),
                # No entry for this major: `latest` of this major, as before `lines`; of a higher one, the bounded
                # upgrade all the same (no release named), counted by `latest`; of a lower one, nothing.
                ("lines of other majors alone, latest higher", "1.3.0", {"1": "1.3.0"}, self.Due(None, "1.3.0")),
                ("no lines, latest of this major", "0.3.0", {}, self.Due("0.3.0", "0.3.0")),
                ("no lines, latest higher", "2.0.0", {}, self.Due(None, "2.0.0")),
                ("latest alone (no lines key), this major", "0.3.0", None, self.Due("0.3.0", "0.3.0")),
                ("latest alone (no lines key), higher", "1.0.0", None, self.Due(None, "1.0.0")),
                ("latest alone, the same", "0.1.0", None, None)):
            with self.subTest(case=case), self.feed(latest, lines):
                self.assertEqual(auto_update.due(), due)
        with mock.patch.object(cad_server, "__version__", "1.4.2"):  # from 1.0 the same rule
            for lines, due in (({"0": "0.12.0", "1": "1.5.0", "2": "2.0.0"}, self.Due("1.5.0", "1.5.0")),
                               ({"0": "0.12.0", "1": "1.4.2", "2": "2.0.0"}, None), ({"0": "0.12.0"}, None)):
                with self.subTest(lines=lines), self.feed(max(lines.values(), key=auto_update.release), lines):
                    self.assertEqual(auto_update.due(), due)

    def test_the_upgrade_is_bounded_by_the_release_that_runs_each_time(self) -> None:
        """The floor and the bound come from the release that runs, never a fixed number: what the helper is told."""
        for version, upgrade in (("0.1.0", "cad>=0.1.0,<1"), ("0.12.3", "cad>=0.12.3,<1"), ("1.4.2", "cad>=1.4.2,<2")):
            with self.subTest(version=version), mock.patch.object(cad_server, "__version__", version), \
                    mock.patch.object(auto_update.subprocess, "Popen") as popen, \
                    mock.patch.object(sys, "_base_executable", str(self.tmp / "python3"), create=True):
                (self.state / auto_update.RECORD).unlink(missing_ok=True)
                self.assertTrue(auto_update.trigger(None, wanted="9.0.0"))
                told = json.loads(popen.call_args.args[0][5])
                self.assertEqual((told["upgrade"][-1], told["major"], told["target"]), (upgrade, False, None))
        with mock.patch.object(cad_server, "__version__", "0.1.0-dev.1"), \
                mock.patch.object(auto_update.subprocess, "Popen") as popen:
            (self.state / auto_update.RECORD).unlink(missing_ok=True)
            self.assertFalse(auto_update.trigger("0.2.0"), "no release to bound it by: none begins")
        popen.assert_not_called()

    def test_the_feed_is_read_only_where_asked_and_a_failed_release_is_tried_once_more_never_in_a_loop(self) -> None:
        with self.feed("0.2.0") as feed:
            auto_update.due()
            auto_update.due(fetch=True)
        self.assertEqual([call.kwargs for call in feed.call_args_list], [{"fetch": False}, {"fetch": True}])
        record = self.state / auto_update.RECORD
        with self.feed("0.2.0"), mock.patch.object(auto_update.subprocess, "Popen"), \
                mock.patch.object(sys, "_base_executable", str(self.tmp / "python3"), create=True):
            self.assertTrue(auto_update.trigger("0.2.0"))
            now = auto_update.last()["at"]
            self.assertEqual((auto_update.last()["tries"], auto_update.due(now=now)), (1, None), "underway")
            self.assertEqual(auto_update.due(now=now + auto_update.RETRY_SECONDS), self.Due("0.2.0", "0.2.0"),
                             "a helper that died")
            auto_update._keep(record, {**auto_update.last(), "outcome": "failed"})
            self.assertIsNone(auto_update.due(now=now), "not by the server the failed update started")
            self.assertEqual(auto_update.due(now=now + auto_update.RETRY_SECONDS), self.Due("0.2.0", "0.2.0"),
                             "once more, later")
            self.assertFalse(auto_update.trigger("0.2.0"), "a trigger asks again in the step that begins it")
            auto_update._keep(record, {**auto_update.last(), "at": now - auto_update.RETRY_SECONDS})  # an hour on
            self.assertTrue(auto_update.trigger("0.2.0"))
            auto_update._keep(record, {**auto_update.last(), "outcome": "failed"})
            self.assertEqual(auto_update.last()["tries"], 2)
            self.assertIsNone(auto_update.due(now=now + 10 * auto_update.RETRY_SECONDS), "and never again")
        with self.feed("0.2.1"):
            self.assertEqual(auto_update.due(now=now), self.Due("0.2.1", "0.2.1"), "a newer release is no retry")

    def test_with_no_release_of_this_major_named_the_tries_are_counted_by_latest_never_in_a_loop(self) -> None:
        """A feed without ``lines`` and ``latest`` of a higher major: the bounded upgrade, whose record names the release
        it got (``current``: nothing newer), counted by ``latest`` all the same, at most ``TRIES`` times."""
        record = self.state / auto_update.RECORD
        with self.feed("1.0.0"), mock.patch.object(auto_update.subprocess, "Popen"), \
                mock.patch.object(sys, "_base_executable", str(self.tmp / "python3"), create=True):
            for tries in (1, 2):
                found = auto_update.due(now=time.time() + (tries - 1) * auto_update.RETRY_SECONDS)
                self.assertEqual(found, self.Due(None, "1.0.0"))
                self.assertTrue(auto_update.trigger(found.target, wanted=found.wanted))
                begun = auto_update.last()
                self.assertEqual((begun["release"], begun["wanted"], begun["tries"]), ("latest", "1.0.0", tries))
                auto_update._keep(record, {**begun, "release": "0.1.0", "outcome": "current",
                                           "at": begun["at"] - (2 - tries) * auto_update.RETRY_SECONDS})
            self.assertIsNone(auto_update.due(now=time.time() + 10 * auto_update.RETRY_SECONDS), "never a third")
        with self.feed("1.0.1"):
            self.assertEqual(auto_update.due(), self.Due(None, "1.0.1"), "a newer latest: tried afresh")

    def test_an_update_underway_under_any_name_holds_every_automatic_trigger_while_it_is_believed(self) -> None:
        record = self.state / auto_update.RECORD
        now = time.time()
        auto_update._keep(record, {"release": "latest", "wanted": "latest", "from": "0.1.0", "at": now, "tries": 1,
                                   "outcome": "underway", "asked": True})  # a typed `cad update`, of no release named
        with self.feed("0.2.0"), mock.patch.object(auto_update.subprocess, "Popen") as popen, \
                mock.patch.object(sys, "_base_executable", str(self.tmp / "python3"), create=True):
            self.assertIsNone(auto_update.due(now=now + 60), "underway, of another name")
            self.assertFalse(auto_update.trigger("0.2.0"), "nor begun by a trigger asked anyway")
            popen.assert_not_called()
            self.assertEqual(auto_update.due(now=now + auto_update.RETRY_SECONDS), self.Due("0.2.0", "0.2.0"),
                             "past the hour: a helper that died, no longer believed")


class RecordTest(Case):
    def test_a_tries_that_is_no_integer_counts_as_none_and_never_stops_an_update(self) -> None:
        """A record whose ``tries`` is null, a string, a float or a bool: never a check that raises (which would stop
        every update for good, only a claim replacing the record); counted as 0, and the next claim writes 1."""
        for tries in (None, "2", 1.0, True):
            with self.subTest(tries=tries):
                auto_update._keep(self.state / auto_update.RECORD, {
                    "release": "0.2.0", "wanted": "0.2.0", "from": "0.1.0", "at": 5.0, "tries": tries,
                    "outcome": "failed", "ended": 6.0, "reported": True})
                self.assertEqual(auto_update._tries("0.2.0"), 0)
                with self.feed("0.2.0", {"0": "0.2.0"}):
                    self.assertEqual(auto_update.due(now=10_000.0), auto_update.Due("0.2.0", "0.2.0"))
                said, kept = auto_update._claim(release="0.2.0", wanted="0.2.0", version="0.1.0", installer="uv",
                                                automatic=True, major=False)
                self.assertEqual((said, kept["tries"], auto_update.last()["tries"]), (auto_update.BEGUN, 1, 1))


class SecondProcessTest(Case):
    """Starting an update is one step across processes: two processes that each start one at the same moment (two
    servers starting at once, each asking ``at_start``) begin one between them, the other none (automatic) or joining
    it (typed). Real processes, each with this test's computer, released together."""

    SCRIPT = """
import json, os, sys, time
from pathlib import Path
from unittest import mock
import cad_server
from cad_server import updates
from cad_server._internal import auto_update
tool, go, out, automatic = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4] == "auto"
with mock.patch.object(sys, "prefix", str(tool)), mock.patch.object(cad_server, "__version__", "0.1.0"), \\
        mock.patch.object(updates, "checking", return_value=True), \\
        mock.patch.object(sys, "_base_executable", str(tool.parent / "python3"), create=True), \\
        mock.patch.object(auto_update.subprocess, "Popen") as popen:
    while not go.exists():
        time.sleep(0.001)
    if automatic:
        began = auto_update.trigger("0.2.0", wanted="0.2.0")
        found = auto_update.last()
    else:
        found = auto_update.begin("0.2.0")
        began = popen.called
out.write_text(json.dumps({"began": began, "helpers": popen.call_count, "at": (found or {}).get("at")}))
"""

    def race(self, kinds: tuple[str, str]) -> list[dict]:
        from tests.python.support.paths import repo_path

        go = self.tmp / "go"
        outs = [self.tmp / f"out{index}.json" for index in range(len(kinds))]
        env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(repo_path("packages/cad/src")), str(repo_path("."))]),
               "CAD_STATE_DIR": str(self.state)}
        processes = [subprocess.Popen([sys.executable, "-c", self.SCRIPT, str(self.tool), str(go), str(out), kind],
                                      env=env) for out, kind in zip(outs, kinds)]
        self.state.mkdir(parents=True, exist_ok=True)
        go.write_text("go", encoding="utf-8")
        for process in processes:
            self.assertEqual(process.wait(60), 0)
        return [json.loads(out.read_text(encoding="utf-8")) for out in outs]

    def test_two_servers_starting_at_once_begin_one_update(self) -> None:
        said = self.race(("auto", "auto"))
        self.assertEqual(sorted(found["began"] for found in said), [False, True], said)
        self.assertEqual(sum(found["helpers"] for found in said), 1, "one helper started between them")
        self.assertEqual((auto_update.last()["tries"], auto_update.last()["outcome"]), (1, "underway"))

    def test_a_typed_update_and_a_server_at_once_one_begins_and_the_typed_one_joins_it(self) -> None:
        said = self.race(("auto", "typed"))
        self.assertEqual(sum(found["helpers"] for found in said), 1, said)
        self.assertEqual(said[1]["at"], auto_update.last()["at"], "the typed one waits on the one attempt")


class WhenTest(Case):
    def test_the_idle_rule(self) -> None:
        with mock.patch.object(auto_update, "due", return_value=auto_update.Due("0.2.0", "0.2.0")), \
                mock.patch.object(auto_update, "trigger", return_value=True) as trigger:
            self.assertFalse(auto_update.tend(working=True, ran=False, quiet_for=1e9), "never while work is in flight")
            self.assertFalse(auto_update.tend(working=False, ran=True, quiet_for=auto_update.IDLE_SECONDS - 1))
            self.assertEqual(trigger.call_count, 0)
            self.assertTrue(auto_update.tend(working=False, ran=False, quiet_for=0.0), "nothing has run: at once")
            self.assertTrue(auto_update.tend(working=False, ran=True, quiet_for=auto_update.IDLE_SECONDS))
            self.assertTrue(auto_update.at_start())
        self.assertEqual(trigger.call_args_list, [mock.call("0.2.0", wanted="0.2.0")] * 3, "each an automatic update")
        with mock.patch.object(auto_update, "due", return_value=None):
            self.assertFalse(auto_update.at_start())
        self.assertEqual(client.UPDATING, auto_update.UPDATING)


class HelperCommandTest(Case):
    def test_its_command_line_on_posix_and_on_windows(self) -> None:
        for windows, cad in ((False, self.tool / "bin" / "cad"), (True, self.tool / "Scripts/cad.exe")):
            with self.subTest(windows=windows):
                line = auto_update.helper_command("0.2.0", now=5.0, version="0.1.0", uv="/u/uv", base="/py/python",
                                                  record="/s/auto-update.json", windows=windows)
                self.assertEqual(line[:4], ["/py/python", "-I", "-S", "-c"])
                self.assertEqual(line[4], auto_update.HELPER.read_text(encoding="utf-8"))
                self.assertEqual(json.loads(line[5]), {
                    "cad": str(cad), "target": "0.2.0", "prefix": str(self.tool), "record": "/s/auto-update.json",
                    "from": "0.1.0", "at": 5.0, "tries": 1,
                    "upgrade": ["/u/uv", "tool", "install", "--upgrade", "cad>=0.1.0,<1"],
                    "put_back": ["/u/uv", "tool", "install", "--managed-python", "--python", "3.14", "cad==0.1.0"],
                    "launchers": ["/u/uv", "tool", "dir", "--bin"], "installer": "uv", "wanted": "0.2.0",
                    "asked": False, "major": False, "start": True})
        told = json.loads(auto_update.helper_command("1.0.0", now=5.0, version="0.1.0", uv="/u/uv", base="/py",
                                                     asked=True, major=True)[5])
        self.assertEqual((told["upgrade"], told["major"], told["put_back"][-1]),
                         (["/u/uv", "tool", "install", "--upgrade", "cad>=0.1.0"], True, "cad==0.1.0"),
                         "`cad update --major`: the newest release of all; a failure puts back the release that ran")

    def triggered(self, **options) -> tuple[list[str], dict]:
        """A trigger with nothing underway (the record of one before it, underway, is taken away first)."""
        (self.state / auto_update.RECORD).unlink(missing_ok=True)
        base = self.tmp / "python" / "bin" / "python3"
        with mock.patch.object(sys, "_base_executable", str(base), create=True), \
                mock.patch.dict(os.environ, {"PYTHONPATH": "/src", "VIRTUAL_ENV": str(self.tool), "KEEP": "1"}), \
                mock.patch.object(auto_update.subprocess, "Popen") as popen:
            self.assertTrue(auto_update.trigger("0.2.0", **options))
        (line,), env = popen.call_args
        self.assertEqual(line[0], str(base))
        return line, env

    def test_the_trigger_starts_it_detached_with_nothing_of_this_environment_and_keeps_the_attempt(self) -> None:
        line, options = self.triggered()
        self.assertEqual(os.path.normcase(json.loads(line[5])["upgrade"][0]), os.path.normcase(self.uv))
        self.assertNotIn("PYTHONPATH", options["env"])
        self.assertNotIn("VIRTUAL_ENV", options["env"])
        self.assertEqual(options["env"]["KEEP"], "1")
        self.assertEqual(options["start_new_session" if os.name != "nt" else "creationflags"],
                         True if os.name != "nt" else 0x08000000 | 0x00000200)
        self.assertEqual(auto_update.last()["outcome"], "underway")
        (self.state / auto_update.RECORD).unlink()
        with mock.patch.object(sys, "_base_executable", str(self.tool / "bin" / "python"), create=True), \
                mock.patch.object(auto_update.subprocess, "Popen") as popen:
            self.assertFalse(auto_update.trigger("0.2.1"), "never a Python of the environment it replaces")
        popen.assert_not_called()
        self.assertIsNone(auto_update.last(), "and nothing kept as underway")
        with mock.patch.object(sys, "_base_executable", str(self.tmp / "python3"), create=True), \
                mock.patch.object(auto_update.subprocess, "Popen", side_effect=OSError("no such file")):
            self.assertFalse(auto_update.trigger("0.2.1"))
        self.assertEqual((auto_update.last()["outcome"], auto_update.last()["detail"]),
                         ("failed", "the update's helper could not start: OSError: no such file"),
                         "a helper that never started holds nothing underway")
        self.assertIsNone(auto_update.underway())

    def test_the_helper_and_the_record_are_told_the_installer_and_whether_it_was_typed_and_never_an_install(self):
        auto_update.change_plugin(True)  # the switch on: the helper runs no install command whatever it says
        for automatic, major in ((True, False), (False, False), (False, True)):
            with self.subTest(automatic=automatic, major=major):
                told = json.loads(self.triggered(automatic=automatic, major=major)[0][5])
                self.assertEqual((told["installer"], told["asked"], told["major"]), ("uv", not automatic, major))
                self.assertNotIn("then_install", told)
                kept = auto_update.last()
                self.assertEqual((kept["installer"], kept["asked"], kept["major"], kept["wanted"]),
                                 ("uv", not automatic, major, "0.2.0"))
        (self.state / auto_update.RECORD).unlink()  # none underway, which `cad update` would join
        with mock.patch.object(auto_update.subprocess, "Popen") as popen, \
                mock.patch.object(sys, "_base_executable", str(self.tmp / "python3"), create=True):
            found = auto_update.begin("1.0.0", major=True)
        told = json.loads(popen.call_args.args[0][5])
        self.assertEqual((found["release"], found["asked"], found["major"], told["upgrade"][-1], told["start"]),
                         ("1.0.0", True, True, "cad>=0.1.0", True))

    def test_the_helper_is_told_whether_to_start_the_server_after_it(self) -> None:
        self.assertTrue(json.loads(self.triggered()[0][5])["start"], "a server ran: it starts again")
        self.assertFalse(json.loads(self.triggered(automatic=False, start=False)[0][5])["start"])


class HelperTest(unittest.TestCase):
    """What the helper runs, in order, and what it keeps."""

    UPGRADE = ["uv", "tool", "install", "--upgrade", BOUNDED]

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.tmp, ignore_errors=True)
        self.site = self.tmp / "lib" / "python3.14" / "site-packages"
        self.site.mkdir(parents=True)
        (self.site / "cad-0.1.0.dist-info").mkdir()
        self.told = {"cad": "cad", "target": "0.2.0", "prefix": str(self.tmp), "record": "r", "from": "0.1.0",
                     "at": 1.0, "upgrade": self.UPGRADE, "put_back": ["uv", "tool", "install", "cad==0.1.0"],
                     "launchers": ["uv", "tool", "dir", "--bin"], "installer": "uv", "asked": True}

    def fake(self, installs: list[int], removes: bool = False, bin_folder: tuple[int, str] = (1, "no tools"),
             newest: str = "0.2.0"):
        """A stand-in for uv and cad: each install exits as ``installs`` says, putting its release in place when it
        succeeds (the upgrade's: ``newest``; a release put back: its own) and, with ``removes``, removing the whole tool
        when it fails (as uv does once it has begun); ``uv tool dir --bin`` answers ``bin_folder``."""
        ran: list[list[str]] = []

        def run(line, timeout):
            if line[1:3] == ["tool", "dir"]:
                ran.append(["dir"])
                return bin_folder
            ran.append(line[1:3] if line[0] == self.told["cad"] else ["install", line[-1]])
            present = list(self.site.glob("cad-*.dist-info"))
            if line[0] == "uv":
                code = installs.pop(0)
                for found in present:
                    found.rmdir()
                if code == 0:
                    (self.site / f"cad-{line[-1].split('==')[1] if '==' in line[-1] else newest}.dist-info"
                     ).mkdir()
                elif not removes:
                    for found in present:
                        found.mkdir()
                return code, "uv said"
            return (0, "done") if present else (127, "cad: not found")
        return ran, run

    def test_stop_upgrade_start_and_tried_again_on_failure(self) -> None:
        ran, run = self.fake([1, 1, 0])
        waited: list[float] = []
        found = helper.update(self.told, run=run, sleep=waited.append, windows=False)
        self.assertEqual(ran, [["server", "stop"], *[["install", BOUNDED]] * 3, ["server", "start"]])
        self.assertEqual(waited, list(helper.WAITS[:3]))
        self.assertEqual((found["outcome"], found["release"], found["from"], found["started"]),
                         ("installed", "0.2.0", "0.1.0", "done"))

    def test_the_record_names_the_release_the_upgrade_got(self) -> None:
        ran, run = self.fake([0], newest="0.2.3")
        self.assertEqual(helper.update(self.told, run=run, sleep=lambda _s: None, windows=False)["release"], "0.2.3",
                         "newer than the feed said")
        for got, outcome in (("0.1.0", "current"), ("0.1.1", "installed")):  # PyPI not asked: whatever it gets
            with self.subTest(got=got):
                for found in self.site.glob("cad-*.dist-info"):
                    found.rename(self.site / "cad-0.1.0.dist-info")
                ran, run = self.fake([0], newest=got)
                done = helper.update({**self.told, "target": None}, run=run, sleep=lambda _s: None, windows=False)
                self.assertEqual((done["outcome"], done["release"]), (outcome, got))

    def test_an_upgrade_that_gets_less_than_asked_is_tried_again_then_what_it_got_of_this_major_stands(self) -> None:
        """The feed named 0.2.0 and the index offers 0.1.5 (or nothing newer): tried at each wait, then taken -- newer
        is ``installed``, the release that ran ``current`` -- never a failure: nothing newer of this major is to be
        had. Its tries stay counted by the release it was for, so it is not asked again within the hour."""
        for newest, outcome in (("0.1.5", "installed"), ("0.1.0", "current")):
            with self.subTest(newest=newest):
                for found in self.site.glob("cad-*.dist-info"):
                    found.rename(self.site / "cad-0.1.0.dist-info")
                ran, run = self.fake([0] * len(helper.WAITS), newest=newest)
                found = helper.update({**self.told, "wanted": "0.2.0"}, run=run, sleep=lambda _s: None, windows=False)
                self.assertEqual((found["outcome"], found["release"], found["wanted"], found["detail"]),
                                 (outcome, newest, "0.2.0", f"it installed {newest}, not 0.2.0"))
                self.assertEqual(ran.count(["install", BOUNDED]), len(helper.WAITS))

    def test_the_upgrade_ends_only_on_a_release_of_this_major_never_older(self) -> None:
        """What the helper accepts: a release of the major of the one that ran, not older than it -- newer is
        ``installed``, the same ``current``; anything else (an older release, another major's) a failure, as every
        failure is: cad runs, so nothing is put back, and the event's step is ``older``."""
        for newest, target, outcome in (("0.3.0", None, "installed"), ("0.1.0", None, "current"),
                                        ("1.0.0", None, "failed"), ("0.0.9", None, "failed"),
                                        ("1.0.0", "0.2.0", "failed")):
            with self.subTest(newest=newest, target=target):
                for found in self.site.glob("cad-*.dist-info"):
                    found.rename(self.site / "cad-0.1.0.dist-info")
                ran, run = self.fake([0] * len(helper.WAITS), newest=newest)
                found = helper.update({**self.told, "target": target}, run=run, sleep=lambda _s: None, windows=False)
                self.assertEqual(found["outcome"], outcome)
                if outcome == "failed":
                    self.assertEqual((found["release"], found["detail"], "restored" in found, ran[-2:]),
                                     (target or "latest", f"it installed {newest}, which it may not end on", False,
                                      [["--version"], ["server", "start"]]))
                    self.assertEqual(auto_update.event({**found, "release": "x", "at": 1.0})["reason"], "older")
                else:
                    self.assertEqual((found["release"], ran.count(["install", BOUNDED])), (newest, 1))

    def test_cad_update_major_accepts_a_higher_major_and_never_an_older_release(self) -> None:
        cross = ["uv", "tool", "install", "--upgrade", "cad>=0.1.0"]
        told = {**self.told, "target": "1.0.0", "major": True, "upgrade": cross}
        ran, run = self.fake([0], newest="1.0.0")
        found = helper.update(told, run=run, sleep=lambda _s: None, windows=False)
        self.assertEqual((found["outcome"], found["release"], found["major"], ran[1]),
                         ("installed", "1.0.0", True, ["install", "cad>=0.1.0"]))
        (self.site / "cad-1.0.0.dist-info").rename(self.site / "cad-0.1.0.dist-info")
        ran, run = self.fake([0] * len(helper.WAITS), newest="0.0.9")
        self.assertEqual(helper.update({**told, "target": None}, run=run, sleep=lambda _s: None,
                                       windows=False)["outcome"], "failed", "older: never, --major or not")
        # Asked for PyPI's newest of all, a higher major, it ends on a release of this major (an installer that kept a
        # range, as pipx 1.18 does): a failure said as one, never `current`, and counted as the upgrade's, never older.
        for got in ("0.1.0", "0.1.5"):
            with self.subTest(got=got):
                for found in self.site.glob("cad-*.dist-info"):
                    found.rename(self.site / "cad-0.1.0.dist-info")
                ran, run = self.fake([0] * len(helper.WAITS), newest=got)
                found = helper.update(told, run=run, sleep=lambda _s: None, windows=False)
                self.assertEqual((found["outcome"], found["release"], found["detail"],
                                  ran.count(["install", "cad>=0.1.0"])),
                                 ("failed", "1.0.0", f"it installed {got}, not 1.0.0", len(helper.WAITS)))
                self.assertEqual(auto_update.event({**found, "at": 1.0})["reason"], "upgrade")

    def test_cad_update_major_that_crossed_is_installed_whatever_release_of_the_higher_major_it_got(self) -> None:
        """PyPI named 2.0.0 and the index (a mirror that lags) gave 1.4.0: the major was crossed, which is what was
        asked: ``installed``, the record naming 1.4.0, at the first try. Where no higher major was the target, it ends
        as ``cad update`` does: what it got of this major stands."""
        cross = ["uv", "tool", "install", "--upgrade", "cad>=0.1.0"]
        ran, run = self.fake([0], newest="1.4.0")
        found = helper.update({**self.told, "target": "2.0.0", "major": True, "upgrade": cross}, run=run,
                              sleep=lambda _s: None, windows=False)
        self.assertEqual((found["outcome"], found["release"], ran.count(["install", "cad>=0.1.0"])),
                         ("installed", "1.4.0", 1))
        (self.site / "cad-1.4.0.dist-info").rename(self.site / "cad-0.1.0.dist-info")
        ran, run = self.fake([0] * len(helper.WAITS), newest="0.1.5")
        found = helper.update({**self.told, "target": "0.2.0", "major": True, "upgrade": cross}, run=run,
                              sleep=lambda _s: None, windows=False)
        self.assertEqual((found["outcome"], found["release"]), ("installed", "0.1.5"), "no higher major: as `cad update`")

    def test_an_environment_already_on_a_higher_major_is_never_taken_down_by_the_bounded_upgrade(self) -> None:
        """A person's ``uv tool install cad@latest`` landed a higher major between the trigger and the helper: the
        bounded upgrade, whose floor is the release that ran, would move it down. It is left as it is."""
        (self.site / "cad-0.1.0.dist-info").rename(self.site / "cad-1.0.0.dist-info")
        for target in (None, "0.2.0"):
            with self.subTest(target=target):
                ran, run = self.fake([])
                found = helper.update({**self.told, "target": target}, run=run, windows=False)
                self.assertEqual((found["outcome"], found["release"], ran),
                                 ("current", "1.0.0", [["server", "stop"], ["server", "start"]]))

    def test_a_failed_install_still_starts_the_server_with_whatever_cad_is_there(self) -> None:
        ran, run = self.fake([1] * len(helper.WAITS))
        found = helper.update(self.told, run=run, sleep=lambda _s: None, windows=False)
        self.assertEqual((ran[0], ran[-1], found["outcome"], found["detail"], found["release"]),
                         (["server", "stop"], ["server", "start"], "failed", "uv said", "0.2.0"))

    def test_an_install_that_failed_and_took_the_tool_with_it_puts_back_the_release_that_ran_then_starts(self) -> None:
        ran, run = self.fake([1] * len(helper.WAITS) + [0], removes=True)
        found = helper.update(self.told, run=run, sleep=lambda _s: None, windows=False)
        self.assertEqual(ran, [["server", "stop"], *[["install", BOUNDED]] * len(helper.WAITS), ["--version"],
                               ["install", "cad==0.1.0"], ["server", "start"]])
        self.assertEqual((found["outcome"], found["restored"], found["started"]), ("failed", True, "done"))
        self.assertEqual(helper.installed(self.tmp), (0, 1, 0), "the release that ran before, and no other")
        ran, run = self.fake([1] * len(helper.WAITS))  # a failure that left the tool as it was: nothing put back
        self.assertNotIn("restored", helper.update(self.told, run=run, sleep=lambda _s: None, windows=False))
        self.assertEqual(ran[-2:], [["--version"], ["server", "start"]])

    def test_told_no_server_ran_it_starts_none(self) -> None:
        ran, run = self.fake([0])
        found = helper.update({**self.told, "start": False}, run=run, sleep=lambda _s: None, windows=False)
        self.assertEqual(ran, [["server", "stop"], ["install", BOUNDED]])
        self.assertEqual((found["outcome"], found["start"]), ("installed", False))
        self.assertNotIn("started", found)

    def test_forward_only_an_environment_at_the_target_or_newer_is_left_alone(self) -> None:
        (self.site / "cad-0.1.0.dist-info").rename(self.site / "cad-0.3.0.dist-info")
        ran, run = self.fake([])
        found = helper.update(self.told, run=run, windows=False)
        self.assertEqual((found["outcome"], found["release"]), ("current", "0.3.0"))
        self.assertEqual(ran, [["server", "stop"], ["server", "start"]])
        windows = self.tmp / "win"
        (windows / "Lib" / "site-packages" / "cad-0.2.0.dist-info").mkdir(parents=True)
        self.assertEqual(helper.installed(windows), (0, 2, 0), "a Windows environment's layout")

    def test_the_record_keeps_the_installer_and_whether_it_was_typed_and_no_install_command_runs(self) -> None:
        for installs in ([0], [1] * len(helper.WAITS)):
            with self.subTest(installs=installs):
                for found in self.site.glob("cad-*.dist-info"):
                    found.rename(self.site / "cad-0.1.0.dist-info")
                ran, run = self.fake(installs)
                record = helper.update(self.told, run=run, sleep=lambda _s: None, windows=False)
                self.assertEqual((record["installer"], record["asked"]), ("uv", True))
                self.assertEqual([argv for argv in ran if "plugin" in argv], [],
                                 "the server of the new cad runs it, never the helper")
                self.assertFalse({"then_install", "install_command"} & set(record))
        told = {key: value for key, value in self.told.items() if key not in ("installer", "asked")}
        _ran, run = self.fake([0])
        self.assertFalse({"installer", "asked"} & set(helper.update(told, run=run, sleep=lambda _s: None,
                                                                    windows=False)), "a helper told neither keeps none")

    def windows_tool(self) -> Path:
        """A Windows tool as uv lays it out: the bin folder's ``cad.exe`` (outside the environment) and the
        environment's own ``Scripts/cad.exe``. The bin folder."""
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, folder, ignore_errors=True)
        (folder / "cad.exe").write_bytes(b"uv's launcher")
        (self.tmp / "Scripts").mkdir()
        (self.tmp / "Scripts" / "cad.exe").write_bytes(b"the environment's launcher")
        self.told["cad"] = str(self.tmp / "Scripts" / "cad.exe")
        return folder

    def test_on_windows_each_cad_exe_is_set_aside_in_the_bin_folder_before_each_try_and_tidied(self) -> None:
        """A running cad.exe cannot be removed, only renamed: before each try both are renamed into the bin folder,
        never left inside the environment uv deletes on a failure, and a copy put back; what was set aside is deleted
        at the start and the end."""
        folder = self.windows_tool()
        (folder / ".cad.exe.1-1.0.old").write_bytes(b"an earlier run's")
        ran, run = self.fake([1, 0], bin_folder=(0, str(folder)))
        seen = []

        def looking(line, timeout):
            if line[0] == "uv" and line[1:3] == ["tool", "install"]:
                seen.append((sorted(path.name for path in folder.iterdir()),
                             sorted(path.name for path in (self.tmp / "Scripts").iterdir()),
                             (folder / "cad.exe").read_bytes(), (self.tmp / "Scripts" / "cad.exe").read_bytes()))
            return run(line, timeout)

        found = helper.update(self.told, run=looking, sleep=lambda _s: None, windows=True)
        self.assertEqual(found["outcome"], "installed")
        self.assertEqual(ran, [["dir"], ["server", "stop"], *[["install", BOUNDED]] * 2, ["server", "start"]])
        for tries, (bin_names, scripts, launcher, own) in enumerate(seen, start=1):
            aside = [name for name in bin_names if name != "cad.exe"]
            self.assertEqual(len(aside), 2 * tries, "both set aside at each try; the earlier run's tidied first")
            self.assertTrue(all(name.startswith(".cad.exe.") and name.endswith((".0.old", ".1.old")) for name in aside))
            self.assertNotIn(".cad.exe.1-1.0.old", aside)
            self.assertEqual((scripts, launcher, own), (["cad.exe"], b"uv's launcher", b"the environment's launcher"),
                             "a copy put back where each was, and nothing set aside inside the environment")
        self.assertEqual([path.name for path in folder.iterdir()], ["cad.exe"], "tidied at the end")

    def test_on_windows_a_set_aside_that_fails_is_skipped_and_the_install_still_tried(self) -> None:
        folder = self.windows_tool()
        with mock.patch.object(helper.os, "replace", side_effect=OSError(18, "not the same device")):
            self.assertEqual(helper.set_aside(self.told, folder), [])
        (self.tmp / "Scripts" / "cad.exe").unlink()
        moved = helper.set_aside(self.told, folder)
        self.assertEqual(([path.parent for path in moved], (folder / "cad.exe").read_bytes()),
                         ([folder], b"uv's launcher"))
        # A file still running refuses to be deleted (here a folder by that name): left for the next run, no error.
        (folder / ".cad.exe.2-2.1.old").mkdir()
        helper.tidy(folder)
        self.assertEqual(sorted(path.name for path in folder.iterdir()), [".cad.exe.2-2.1.old", "cad.exe"])
        # uv cannot say where its bin folder is: nothing set aside, the install tried all the same.
        ran, run = self.fake([0])
        self.assertEqual(helper.update(self.told, run=run, sleep=lambda _s: None, windows=True)["outcome"], "installed")
        self.assertEqual(ran, [["dir"], ["server", "stop"], ["install", BOUNDED], ["server", "start"]])

    def test_pipx_s_command_lines_run_as_handed_its_launchers_set_aside_and_its_release_put_back(self) -> None:
        """The helper knows no installer: pipx's upgrade, put-back and launchers' folder are the lines it is handed,
        and on Windows the cad.exe in pipx's bin folder and the environment's own are set aside as uv's are."""
        folder = self.windows_tool()
        told = {**self.told, "upgrade": ["pipx", "upgrade", "cad"], "put_back": ["pipx", "install", "--force", "cad==0.1.0"],
                "launchers": ["pipx", "environment", "--value", "PIPX_BIN_DIR"]}
        ran, aside = [], []

        def run(line, timeout):
            ran.append(line)
            present = list(self.site.glob("cad-*.dist-info"))
            if line == told["launchers"]:
                return 0, str(folder)
            if line[0] == "pipx":
                aside.append(len([path for path in folder.iterdir() if path.name != "cad.exe"]))
                for found in present:  # a failed upgrade that leaves no cad; the put-back installs its release
                    found.rmdir()
                if line == told["put_back"]:
                    (self.site / "cad-0.1.0.dist-info").mkdir()
                    return 0, "installed package cad 0.1.0"
                return 1, "pipx said no"
            return (0, "done") if present else (127, "cad: not found")

        found = helper.update(told, run=run, sleep=lambda _s: None, windows=True)
        self.assertEqual(ran, [told["launchers"], [told["cad"], "server", "stop"], *[told["upgrade"]] * len(helper.WAITS),
                               [told["cad"], "--version"], told["put_back"], [told["cad"], "server", "start"]])
        self.assertEqual(aside, [2 * tries for tries in range(1, len(helper.WAITS) + 2)], "both set aside at each try")
        self.assertEqual((found["outcome"], found["restored"], found["detail"]), ("failed", True, "pipx said no"))
        self.assertEqual(helper.installed(self.tmp), (0, 1, 0))

    def test_the_record_is_written_beside_and_moved_into_place_and_a_refused_move_falls_back(self) -> None:
        """Written to a file of its own, then moved into place, so a reader never finds it half written; where Windows
        refuses the move (another process has the record open), tried again briefly, then written in place. Never
        raises."""
        path = self.tmp / "auto-update.json"
        files = lambda: sorted(found.name for found in self.tmp.iterdir() if found.is_file())  # noqa: E731
        helper.keep(str(path), {"outcome": "installed"})
        self.assertEqual((json.loads(path.read_text(encoding="utf-8")), files()),
                         ({"outcome": "installed"}, ["auto-update.json"]))
        refused: list[str] = []

        def busy(times: int):
            def replace(source, target):
                if len(refused) < times:
                    refused.append(target)
                    raise PermissionError(13, "the file is in use", target)
                os.replace(source, target)
            return replace

        waited: list[float] = []
        helper.keep(str(path), {"outcome": "failed"}, replace=busy(2), sleep=waited.append)
        self.assertEqual((json.loads(path.read_text(encoding="utf-8")), waited, files()),
                         ({"outcome": "failed"}, [0, *helper.REPLACE_WAITS[:2]], ["auto-update.json"]))
        refused.clear()
        waited.clear()
        helper.keep(str(path), {"outcome": "current"}, replace=busy(100), sleep=waited.append)
        self.assertEqual((json.loads(path.read_text(encoding="utf-8")), waited, files()),
                         ({"outcome": "current"}, [0, *helper.REPLACE_WAITS], ["auto-update.json"]))
        helper.keep(str(self.tmp / "no such folder" / "auto-update.json"), {"outcome": "failed"})  # never raises

    def test_no_console_window_on_windows(self) -> None:
        with mock.patch.object(helper.subprocess, "run", return_value=types.SimpleNamespace(returncode=0, stdout="")) \
                as running:
            helper.run(["cad"], 5)
        self.assertEqual(running.call_args.kwargs["creationflags"], helper.NO_WINDOW)
        self.assertEqual(helper.NO_WINDOW, 0x08000000 if os.name == "nt" else 0)

    def stand_ins(self, log: Path, uv: str) -> None:
        for name, body in (("cad", f'echo "cad $*" >> {log}'), ("uv", f'echo "uv $*" >> {log}; {uv}')):
            (self.tmp / name).write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
            (self.tmp / name).chmod(0o755)
        (self.tmp / "bin").mkdir()
        (self.tmp / "bin" / "cad").symlink_to(self.tmp / "cad")

    @unittest.skipIf(os.name == "nt", "the stand-in uv and cad are shell scripts")
    def test_the_helper_runs_isolated_from_its_own_source_and_keeps_its_outcome(self) -> None:
        log = self.tmp / "log"
        self.stand_ins(log, f"mv {self.site}/cad-0.1.0.dist-info {self.site}/cad-0.2.0.dist-info")
        record = self.tmp / "auto-update.json"
        line = auto_update.helper_command("0.2.0", now=1.0, version="0.1.0", prefix=str(self.tmp),
                                          uv=str(self.tmp / "uv"), record=str(record), windows=False)
        env = {**os.environ, "PYTHONPATH": "/nowhere-at-all"}
        subprocess.run(line, check=True, env=env, cwd=self.tmp, timeout=60)
        self.assertEqual(log.read_text(encoding="utf-8").splitlines(),
                         ["cad server stop", "uv tool install --upgrade cad>=0.1.0,<1", "cad server start"])
        kept = json.loads(record.read_text(encoding="utf-8"))
        self.assertEqual((kept["outcome"], kept["release"], kept["installer"], kept["asked"]),
                         ("installed", "0.2.0", "uv", False))

    @unittest.skipIf(os.name == "nt", "the stand-in uv and cad are shell scripts")
    def test_a_helper_run_outside_codex_s_sandbox_with_its_variables_still_set_ends_with_a_running_server(self):
        """An update begun by a server Codex started outside its sandbox (an approved ``cad server start``) hands the
        helper the sandbox's variables: its ``cad server start`` starts the server all the same, the system allowing
        it the loopback port."""
        from cad.engine import api

        engine = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp"))
        self.addCleanup(__import__("shutil").rmtree, engine, ignore_errors=True)
        state = self.tmp / "state"
        env = {**os.environ, "CAD_ENGINE_DIR": str(engine), "CAD_STATE_DIR": str(state),
               "CAD_CACHE_DIR": str(self.tmp / "cache"), "CAD_UPDATE_CHECK": "0",
               "CODEX_SANDBOX": "seatbelt", "CODEX_SANDBOX_NETWORK_DISABLED": "1"}
        from tests.python.support.engine_daemon import register

        register(state)
        self.addCleanup(lambda: mock.patch.dict(os.environ, {"CAD_ENGINE_DIR": str(engine)})(api.stop)())
        (self.tmp / "cad").write_text(f'#!/bin/sh\nexec "{sys.executable}" -m cad_server.cli "$@"\n', encoding="utf-8")
        (self.tmp / "uv").write_text(f"#!/bin/sh\nmv {self.site}/cad-0.1.0.dist-info {self.site}/cad-0.2.0.dist-info\n",
                                     encoding="utf-8")
        for name in ("cad", "uv"):
            (self.tmp / name).chmod(0o755)
        (self.tmp / "bin").mkdir()
        (self.tmp / "bin" / "cad").symlink_to(self.tmp / "cad")
        record = self.tmp / "auto-update.json"
        line = auto_update.helper_command("0.2.0", now=1.0, version="0.1.0", prefix=str(self.tmp),
                                          uv=str(self.tmp / "uv"), record=str(record), windows=False)
        subprocess.run(line, check=True, env=env, cwd=self.tmp, timeout=180)
        kept = json.loads(record.read_text(encoding="utf-8"))
        self.assertEqual((kept["outcome"], kept["started"]), ("installed", f"started the cad server (cad {version()})"))
        with mock.patch.dict(os.environ, {"CAD_ENGINE_DIR": str(engine)}):
            self.assertEqual(client.request({"op": "pid"}, start=False)["ok"], True, "a server answers")


class LauncherTest(unittest.TestCase):
    """uv's ``cad.exe`` runs ``python cad.exe``: the launcher, a zip, is ``sys.path[0]``, and a process that reads
    package metadata through it holds it open, which Windows will not rename. Importing ``cad_server`` takes it off."""

    def path_after_import(self, *argv: str) -> list[str]:
        from tests.python.support.paths import SOURCE_PATH

        done = subprocess.run([sys.executable, *argv], capture_output=True, text=True, timeout=120,
                              env={**os.environ, "PYTHONPATH": SOURCE_PATH})
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_the_launcher_is_taken_off_the_path_and_any_other_first_entry_left(self) -> None:
        import zipfile

        folder = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, folder, ignore_errors=True)
        for name, gone in (("CAD.EXE", True), ("OTHER.EXE", False)):  # cad's launcher, in any case; another program's
            program = folder / name
            with zipfile.ZipFile(program, "w") as archive:
                archive.writestr("__main__.py", "import json, sys\nimport cad_server\nprint(json.dumps(sys.path))\n")
            path = self.path_after_import(str(program))
            self.assertEqual(str(program) not in path, gone, name)
            if not gone:
                self.assertEqual(path[0], str(program), "another program's zip keeps its first path entry")
        first = str(folder / "bin")
        script = f"import json, sys\nsys.path.insert(0, {first!r})\nimport cad_server\nprint(json.dumps(sys.path))"
        self.assertEqual(self.path_after_import("-c", script)[0], first)


class JoinTest(unittest.TestCase):
    """Older meets newer: a start joins a newer server, never replaces it; a newer start replaces an older one."""

    def test_a_start_finds_a_newer_server_running_and_joins_it(self) -> None:
        newer = types.SimpleNamespace(release="999.0.0", close=lambda: None)
        with mock.patch.object(client, "_connect", return_value=newer), \
                mock.patch.object(client, "sweep", side_effect=AssertionError("never stopped")), \
                mock.patch.object(client, "_spawn", side_effect=AssertionError("never started")):
            said = client.start()
        self.assertEqual(said, f"the cad server (cad 999.0.0, newer than this cad {version()}) is already running")
        older = types.SimpleNamespace(release="0.0.1", close=lambda: None)
        with mock.patch.object(client, "_connect", return_value=older), \
                mock.patch.object(client, "_sandboxed", return_value=False), \
                mock.patch.object(client, "sweep") as sweep:
            self.assertIsNone(client.make_way())
        sweep.assert_called_once_with(stop=True, seconds=client.STOP_SECONDS, leave=version())

    def test_starts_at_once_stop_the_older_server_alone_and_join_the_one_another_of_them_started(self) -> None:
        """Starts at the same moment all find an older server; one stops it and starts this release's. Another reaches
        the server after that -- before it would tell it to stop, or while it waits for the older one to go -- and
        joins the server it finds, of this release or a newer one: never told to stop, never waited on."""
        for moment in ("before the stop", "while the older one goes"):
            for theirs in (version(), "999.0.0"):
                serving = ["0.0.1"]  # the release of the server that answers now
                stopped: list[str] = []

                def connect(*_args, **_kwargs):
                    return types.SimpleNamespace(release=serving[0], close=lambda: None)

                def sandboxed() -> bool:  # asked between the start's look at the server and its stop
                    if moment == "before the stop":
                        serving[0] = theirs
                    return False

                def exchange(connection, message, **_kwargs):
                    stopped.append(connection.release)
                    if moment == "while the older one goes":
                        serving[0] = theirs  # the other start's server answers before this one sees none
                    return {"ok": True}

                with self.subTest(moment=moment, theirs=theirs), \
                        mock.patch.object(client, "_connect", side_effect=connect), \
                        mock.patch.object(client, "_answering", return_value=True), \
                        mock.patch.object(client, "_sandboxed", side_effect=sandboxed), \
                        mock.patch.object(client, "_note_pages"), \
                        mock.patch.object(client, "_exchange", side_effect=exchange), \
                        mock.patch.object(client, "_remove_dead", return_value=[]):
                    said = client.make_way()
                    self.assertEqual(stopped, [] if moment == "before the stop" else ["0.0.1"], "the older one alone")
                    self.assertEqual(said, f"the cad server (cad {version()}) is already running" if theirs == version()
                                     else f"the cad server (cad 999.0.0, newer than this cad {version()}) is already "
                                          "running")

    def test_a_server_that_hands_its_start_to_an_update_is_waited_for_and_the_update_s_newer_server_joined(self):
        answers = iter([None, None, None, types.SimpleNamespace(release="999.0.0", close=lambda: None)])
        spawned = types.SimpleNamespace(pid=10, poll=lambda: client.UPDATING)
        with mock.patch.object(client, "make_way", return_value=None), \
                mock.patch.object(client.places, "make_engine_dir"), \
                mock.patch.object(client.places, "folder_refusal", return_value=None), \
                mock.patch.object(client, "_spawn", return_value=spawned) as spawn, \
                mock.patch.object(client, "_connect", side_effect=lambda: next(answers)):
            said = client.start()
        spawn.assert_called_once()
        self.assertIn("newer than this cad", said)

    def test_cad_mcp_reaches_its_release_or_a_newer_one_and_a_cad_command_its_own_alone(self) -> None:
        def answering(release):
            return mock.patch.object(client, "_connect", return_value=mock.Mock(release=release))

        with mock.patch.object(client, "RELEASE", None), mock.patch.object(client, "AT_LEAST", "0.2.0"):
            for release in ("0.2.0", "0.3.0"):
                with answering(release):
                    self.assertEqual(client.connect().release, release)
            with answering("0.1.0"), self.assertRaises(client.OtherRelease):
                client.connect()
        with mock.patch.object(client, "RELEASE", "0.2.0"), answering("0.3.0"), \
                self.assertRaises(client.OtherRelease) as said:
            client.connect()
        self.assertEqual(str(said.exception), "cad here is 0.2.0; the running server is 0.3.0: install cad 0.3.0")


class FailedStartTest(Case):
    def test_a_start_that_fails_still_updates_and_says_so_before_it_gives_up(self) -> None:
        from cad_server.cli import server

        err = io.StringIO()
        with self.feed("0.2.0") as feed, \
                mock.patch.object(client, "start", side_effect=ConnectionError("the engine server did not start")), \
                mock.patch.object(auto_update, "trigger", return_value=True) as trigger, \
                redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = server.main(["start"])
        self.assertEqual(code, 1)
        trigger.assert_called_once_with("0.2.0", wanted="0.2.0")
        self.assertEqual(feed.call_args.kwargs, {"fetch": True}, "the feed read where it is due: no server reads it")
        self.assertEqual(err.getvalue().splitlines(), ["cad: updating cad to 0.2.0, which then starts the server",
                                                       "cad server start: the engine server did not start"])
        err = io.StringIO()
        with self.feed("1.0.0"), \
                mock.patch.object(client, "start", side_effect=ConnectionError("the engine server did not start")), \
                mock.patch.object(auto_update, "trigger", return_value=True) as trigger, \
                redirect_stderr(err), redirect_stdout(io.StringIO()):
            server.main(["start"])
        trigger.assert_called_once_with(None, wanted="1.0.0")
        self.assertEqual(err.getvalue().splitlines()[0],
                         "cad: updating cad to the newest 0.x release, which then starts the server",
                         "a feed naming no release of this major: the bounded upgrade, never 1.0.0")

    def test_a_start_whose_files_an_update_removed_under_it_still_says_one_line(self) -> None:
        """As a failed install on Windows did: cad's own files gone while the start waited. What the failure needs was
        imported before, so it says its one line, never a traceback."""
        from cad_server import _internal
        from cad_server.cli import server

        def removed(_port):
            delattr(_internal, "auto_update")
            sys.modules["cad_server._internal.auto_update"] = None  # importing it now raises ImportError
            raise ConnectionError("the engine server did not start: cad is updating")

        self.addCleanup(sys.modules.__setitem__, "cad_server._internal.auto_update", auto_update)
        self.addCleanup(setattr, _internal, "auto_update", auto_update)
        err = io.StringIO()
        with mock.patch.object(client, "start", side_effect=removed), \
                mock.patch.object(auto_update, "after_failed_start", return_value=None), \
                redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = server.main(["start"])
        self.assertEqual((code, err.getvalue()),
                         (1, "cad server start: the engine server did not start: cad is updating\n"))


class AskedTest(Case):
    """``cad update`` as the server judges it (``auto_update.asked``) and begins it (``begin``): PyPI asked now, and
    none of the automatic limits -- the switch, ``TRIES``, ``RETRY_SECONDS`` -- applies."""

    def asked(self, newest: str | None, major: bool = False, **lines: str) -> dict:
        """``asked`` with PyPI's answer in the feed's shape: ``newest`` its newest of all (None: out of reach), and
        ``lines`` (``m0="0.2.0"``) each major's newest; by default ``newest``'s own."""
        known = None if newest is None else {"latest": newest, "lines": {key[1:]: value for key, value in lines.items()}
                                             or {newest.split(".")[0]: newest}}
        return auto_update.asked(major=major, pypi=lambda: known)

    def test_what_it_refuses_and_what_it_answers(self) -> None:
        auto_update.change(False)
        self.assertEqual(self.asked("0.2.0"), {"ok": True, "updating": "0.2.0", "from": "0.1.0"}, "the switch off")
        self.assertEqual(self.asked("0.1.0"), {"ok": True, "newest": "0.1.0"})
        self.assertEqual(self.asked("0.0.9"), {"ok": True, "newest": "0.1.0"}, "never back")
        self.assertEqual(self.asked(None), {"ok": True, "updating": None, "from": "0.1.0"},
                         "PyPI out of reach: the upgrade runs all the same")
        with mock.patch.object(updates, "checking", return_value=False):
            self.assertEqual(self.asked("0.2.0"), {"failed": auto_update.CHECK_OFF})
        with mock.patch.object(auto_update, "find_uv", return_value=None), \
                mock.patch.object(auto_update, "carried_uv", return_value=None):
            self.assertEqual(self.asked("0.2.0"), {"failed": auto_update.no_installer("uv")})
        with mock.patch.object(sys, "prefix", str(self.tmp)):
            self.assertEqual(self.asked("0.2.0"), {"failed": auto_update.NOT_THE_TOOL})
        with mock.patch.object(updates, "pypi", return_value={"latest": "0.3.0", "lines": {"0": "0.3.0"}}) as pypi:
            self.assertEqual(auto_update.asked()["updating"], "0.3.0")
        pypi.assert_called_once_with()

    def test_it_stays_inside_the_major_and_names_a_higher_one(self) -> None:
        """PyPI's newest release of this major (not yanked: ``updates.pypi``'s), never a higher major's, which the
        answer names (``higher``); ``--major`` takes the newest of all."""
        self.assertEqual(self.asked("1.0.0", m0="0.2.0", m1="1.0.0"),
                         {"ok": True, "updating": "0.2.0", "from": "0.1.0", "higher": "1.0.0"}, "both out")
        self.assertEqual(self.asked("1.0.0", m0="0.1.0", m1="1.0.0"),
                         {"ok": True, "newest": "0.1.0", "higher": "1.0.0"}, "nothing newer in this major")
        self.assertEqual(self.asked("1.0.0", m1="1.0.0"),
                         {"ok": True, "updating": None, "from": "0.1.0", "higher": "1.0.0"},
                         "none of this major named: the bounded upgrade all the same")
        self.assertEqual(self.asked("1.0.0", major=True, m0="0.2.0", m1="1.0.0"),
                         {"ok": True, "updating": "1.0.0", "from": "0.1.0", "major": True})
        self.assertEqual(self.asked("0.2.0", major=True), {"ok": True, "updating": "0.2.0", "from": "0.1.0",
                                                           "major": True}, "--major with no higher major: the newest")
        self.assertEqual(self.asked("0.1.0", major=True), {"ok": True, "newest": "0.1.0"})
        self.assertEqual(self.asked(None, major=True), {"ok": True, "updating": None, "from": "0.1.0", "major": True})
        with mock.patch.object(cad_server, "__version__", "0.1.0-dev.1"):
            self.assertIn("no release", self.asked("0.2.0")["failed"])

    def test_begin_starts_one_attempt_counted_as_any_and_joins_the_one_underway(self) -> None:
        with mock.patch.object(auto_update.subprocess, "Popen") as popen, \
                mock.patch.object(sys, "_base_executable", str(self.tmp / "python3"), create=True):
            first = auto_update.begin("0.2.0")
            self.assertEqual((first["release"], first["outcome"], first["tries"]), ("0.2.0", "underway", 1))
            self.assertEqual(auto_update.begin("0.2.0"), first, "joined, never a second at once")
            self.assertEqual(auto_update.begin("0.2.1"), first, "an attempt of another release underway: joined too")
            self.assertEqual(popen.call_count, 1)
            auto_update._keep(self.state / auto_update.RECORD, {**first, "outcome": "failed"})
            again = auto_update.begin("0.2.0")
            self.assertEqual((again["tries"], popen.call_count), (2, 2), "counted, so the automatic tries stay bounded")
            auto_update._keep(self.state / auto_update.RECORD, {**again, "at": again["at"] - auto_update.RETRY_SECONDS})
            self.assertEqual(auto_update.begin("0.2.0")["tries"], 3, "an underway record past the hour: a dead helper")
            auto_update._keep(self.state / auto_update.RECORD, {**again, "outcome": "failed"})
            unknown = auto_update.begin(None)
            self.assertEqual((unknown["release"], json.loads(popen.call_args.args[0][5])["target"]), ("latest", None),
                             "PyPI out of reach: whatever the upgrade gets")
        with mock.patch.object(auto_update, "_start", side_effect=OSError("the state folder is read-only")):
            auto_update._keep(self.state / auto_update.RECORD, {**again, "outcome": "failed"})
            self.assertIsNone(auto_update.begin("0.2.0"))


class ServerUpdateTest(Case):
    """The server's part of ``cad update`` (``Daemon.update``): the update begun at once where nothing is in flight,
    else the moment it ends, never twice; an attempt underway joined; what the command asks while it waits."""

    def daemon(self, working: list[bool]):
        import threading

        from cad_server.engine.daemon import Daemon

        fake = types.SimpleNamespace(busy_lock=threading.Lock(), asked_update=None, stopping=threading.Event(),
                                     draining=False, working=lambda: working[0])
        fake._update_when_idle = types.MethodType(Daemon._update_when_idle, fake)
        return fake, lambda request: Daemon.update(fake, request)

    def test_begun_once_nothing_is_in_flight_and_never_twice(self) -> None:
        import threading

        for newest in ("0.2.0", None):
            working, begun = [True], threading.Event()
            fake, ask = self.daemon(working)
            judged = {"ok": True, "updating": newest, "from": "0.1.0"}
            with self.subTest(newest=newest), mock.patch.object(auto_update, "asked", return_value=judged), \
                    mock.patch.object(auto_update, "underway", return_value=None), \
                    mock.patch.object(auto_update, "begin", side_effect=lambda _t, major: begun.set() or {"at": 1.0}
                                      ) as begin, redirect_stderr(io.StringIO()):
                first = ask({"op": "update"})
                self.assertEqual({key: first[key] for key in judged}, judged)
                self.assertEqual(ask({"op": "update"})["since"], first["since"], "the same update, asked twice")
                self.assertEqual(ask({"op": "update", "begin": False})["waiting"], newest or "latest")
                self.assertFalse(begun.is_set(), "not while work is in flight")
                working[0] = False
                self.assertTrue(begun.wait(30))
                for thread in threading.enumerate():
                    if thread.name == "cad-update":
                        thread.join(30)
                begin.assert_called_once_with(newest, major=False)
                self.assertIsNone(fake.asked_update)
        # `cad update --major`: judged as such, begun as such.
        working, begun = [False], threading.Event()
        fake, ask = self.daemon(working)
        judged = {"ok": True, "updating": "1.0.0", "from": "0.1.0", "major": True}
        with mock.patch.object(auto_update, "asked", return_value=judged) as asked, \
                mock.patch.object(auto_update, "underway", return_value=None), \
                mock.patch.object(auto_update, "begin", side_effect=lambda _t, major: begun.set() or {"at": 1.0}
                                  ) as begin, redirect_stderr(io.StringIO()):
            ask({"op": "update", "major": True})
            self.assertTrue(begun.wait(30))
            for thread in threading.enumerate():
                if thread.name == "cad-update":
                    thread.join(30)
        asked.assert_called_once_with(major=True)
        begin.assert_called_once_with("1.0.0", major=True)
        underway = {"release": "0.2.0", "at": 5.0, "outcome": "underway"}
        with mock.patch.object(auto_update, "asked", return_value=judged), \
                mock.patch.object(auto_update, "underway", return_value=underway), \
                mock.patch.object(auto_update, "begin") as begin:
            self.assertEqual(ask({"op": "update"})["since"], 5.0, "joined")
        begin.assert_not_called()
        with mock.patch.object(auto_update, "asked", return_value={"ok": True, "newest": "0.1.0"}):
            self.assertEqual(ask({"op": "update"}), {"ok": True, "newest": "0.1.0"})

    def test_a_real_server_answers_it_and_one_that_is_no_global_install_refuses(self) -> None:
        from tests.python.support import engine_daemon
        from cad_server.cli import update as typed

        env = {**os.environ, "PATH": os.environ.get("PATH", ""), "CAD_UPDATE_CHECK": "0",
               "CAD_CACHE_DIR": str(self.tmp / "cache")}
        engine_daemon.start(env, self.addCleanup)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = typed.main([])
        self.assertEqual((code, out.getvalue(), err.getvalue()), (1, "", f"cad update: {auto_update.NOT_THE_TOOL}\n"))
        looked = client.request({"op": "update", "begin": False}, start=False)
        self.assertEqual((looked["ok"], looked["last"], looked["waiting"]), (True, None, None))


class UpdateCommandTest(Case):
    """``cad update`` (``cad_server/cli/update.py``): refused for a cad that is no global install, the one line with no
    server, an older server's answer; it waits and says how the update ended, on Windows as everywhere."""

    def typed(self, answer=None, *, raises: Exception | None = None, looks=(), argv=()):
        from cad_server.cli import update as typed

        out, err = io.StringIO(), io.StringIO()
        looks = iter(looks)
        with mock.patch.object(client, "request", return_value=answer, side_effect=raises) as request, \
                mock.patch.object(typed, "look", side_effect=lambda *_a: next(looks)), \
                mock.patch.object(typed.time, "sleep"), redirect_stdout(out), redirect_stderr(err):
            try:
                code = typed.main(list(argv))
            except SystemExit as leaving:
                code = leaving.code
        return code, out.getvalue(), err.getvalue(), request

    def test_a_higher_major_is_named_in_one_line_and_major_installs_it(self) -> None:
        line = auto_update.MAJOR_LINE.format(release="1.0.0")
        self.assertEqual(line, "cad 1.0.0, a new major version, is out and does not install itself: `cad update "
                               "--major` installs it (what changes: https://github.com/earthtojake/text-to-cad/tree/"
                               "main/docs/migrations)")
        self.assertEqual(self.typed({"ok": True, "newest": "0.1.0", "higher": "1.0.0"})[:3],
                         (0, f"cad 0.1.0 is the newest 0.x release\n{line}\n", ""))
        answer = {"ok": True, "updating": "0.2.0", "from": "0.1.0", "since": 5.0, "higher": "1.0.0"}
        record = {"release": "0.2.0", "at": 5.0, "outcome": "installed", "started": "started"}
        self.assertEqual(self.typed(answer, looks=[("0.2.0", record, None, True)])[:3],
                         (0, f"cad 0.1.0 updated to 0.2.0\n{line}\n", ""))
        current = {**record, "release": "0.1.0", "outcome": "current"}
        self.assertEqual(self.typed({**answer, "updating": None}, looks=[("0.1.0", current, None, True)])[:3],
                         (0, f"cad 0.1.0 is the newest 0.x release\n{line}\n", ""), "PyPI named none of this major")
        failed = {**record, "outcome": "failed", "detail": "uv said no"}
        self.assertNotIn(line, self.typed(answer, looks=[("0.1.0", failed, None, True)])[1], "said where it ended well")
        # --major: asked of the server as such, and said as any update is.
        major = {"ok": True, "updating": "1.0.0", "from": "0.1.0", "since": 5.0, "major": True}
        code, out, err, request = self.typed(major, looks=[("1.0.0", {**record, "release": "1.0.0"}, None, True)],
                                             argv=["--major"])
        self.assertEqual((code, out, err), (0, "cad 0.1.0 updated to 1.0.0\n", ""))
        self.assertEqual(request.call_args.args[0], {"op": "update", "major": True})
        self.assertEqual(self.typed({"ok": True, "newest": "1.0.0"}, argv=["--major"])[:3],
                         (0, "cad 1.0.0 is the newest release\n", ""))

    def test_major_with_no_server_updates_here_by_the_crossing_command(self) -> None:
        none = client.NotRunning(client.NOT_RUNNING)

        def looks():
            begun = auto_update.last()
            yield None, {**begun, "release": "1.0.0", "outcome": "installed", "start": False}, None, False

        with mock.patch.object(client, "_sandboxed", return_value=False), \
                mock.patch.object(updates, "pypi", return_value={"latest": "1.0.0", "lines": {"0": "0.1.0", "1": "1.0.0"}}), \
                mock.patch.object(sys, "_base_executable", str(self.tmp / "python3"), create=True), \
                mock.patch.object(auto_update.subprocess, "Popen") as popen:
            self.assertEqual(self.typed(raises=none, looks=looks(), argv=["--major"])[:3],
                             (0, "cad 0.1.0 updated to 1.0.0\n", ""))
        told = json.loads(popen.call_args.args[0][5])
        self.assertEqual((told["target"], told["major"], told["upgrade"][-1], told["start"]),
                         ("1.0.0", True, "cad>=0.1.0", False))

    def test_major_is_no_option_of_update_auto_and_the_help_says_the_rule(self) -> None:
        for argv in (["--major", "auto"], ["auto", "--major"], ["--major", "auto", "status"]):
            with self.subTest(argv=argv):
                code, out, err, request = self.typed(argv=argv)
                self.assertEqual((code, out), (2, ""))
                request.assert_not_called()
        self.assertFalse((self.state / "settings.json").exists(), "nothing written")
        code, out, _err, _request = self.typed(argv=["--help"])
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[:2], ["usage: cad update [-h] [--major]",
                                                "       cad update auto [{status,on,off}]"])
        self.assertIn("cad installs every newer release of its major version by itself, and a new major version only "
                      "when you run `cad update --major`.", " ".join(out.split()))

    def test_refused_never_started_and_an_older_server_s_answer(self) -> None:
        from cad_server.cli import update as typed

        (self.tool / "uv-receipt.toml").unlink()
        code, out, err, request = self.typed()
        self.assertEqual((code, out, err), (1, "", f"cad update: {typed.NOT_A_TOOL}\n"))
        request.assert_not_called()
        (self.tool / "uv-receipt.toml").write_text(RECEIPT, encoding="utf-8")
        with mock.patch.object(client, "_sandboxed", return_value=True), \
                mock.patch.object(auto_update, "asked") as asked:
            self.assertEqual(self.typed(raises=client.NotRunning(client.NOT_RUNNING))[:3],
                             (1, "", f"cad update: {client.SANDBOXED}\n"), "a sandbox: no server, and no update here")
        asked.assert_not_called()
        self.assertEqual(self.typed({"failed": "unknown request 'update'"})[:3],
                         (1, "", f"cad update: {typed.OLD_SERVER}\n"))
        self.assertEqual(self.typed({"failed": auto_update.CHECK_OFF})[:3],
                         (1, "", f"cad update: {auto_update.CHECK_OFF}\n"))
        self.assertEqual(self.typed({"ok": True, "newest": "0.1.0"})[:3], (0, "cad 0.1.0 is the newest release\n", ""))
        self.assertEqual(self.typed()[3].call_args.args[0], {"op": "update"})

    def test_it_waits_for_the_attempt_and_says_how_it_ended(self) -> None:
        answer = {"ok": True, "updating": "0.2.0", "from": "0.1.0", "since": 5.0}
        underway = {"release": "0.2.0", "at": 5.0, "outcome": "underway"}
        earlier = {"release": "0.1.9", "at": 1.0, "outcome": "installed"}
        for record, ended in (({**underway, "outcome": "installed", "started": "started"},
                               (0, "cad 0.1.0 updated to 0.2.0\n", "")),
                              ({**underway, "outcome": "failed", "detail": "uv said no", "restored": True},
                               (1, "", "cad update: could not update cad 0.1.0 to 0.2.0: uv said no; cad 0.1.0 is "
                                       "running\n")),
                              ({**underway, "outcome": "installed", "started": "not started: it exited 1"},
                               (1, "", "cad update: cad 0.1.0 updated to 0.2.0, but the cad server did not start "
                                       "again: run `cad server start`\n"))):
            with self.subTest(outcome=record["outcome"]):
                running = "0.2.0" if record["outcome"] == "installed" else "0.1.0"
                looks = [("0.1.0", earlier, "0.2.0", True), (None, underway, None, False),
                         (running, record, None, True)]
                self.assertEqual(self.typed(answer, looks=looks)[:3], ended)
        failed = {**underway, "outcome": "failed", "detail": "uv said no"}
        self.assertIn("; no cad server is running: run `cad server start`",
                      self.typed(answer, looks=[(None, failed, None, False)])[2])
        self.assertEqual(self.typed(answer, looks=[("0.1.0", earlier, None, True)])[:3],
                         (1, "", "cad update: the update could not begin, so cad 0.1.0 stays as it is\n"))

    def test_with_no_server_it_updates_here_and_leaves_none_running(self) -> None:
        auto_update.change_plugin(True)  # the switch on: a typed update still never runs the install command
        none = client.NotRunning(client.NOT_RUNNING)
        with mock.patch.object(client, "_sandboxed", return_value=False), \
                mock.patch.object(updates, "pypi", return_value={"latest": "0.1.0", "lines": {"0": "0.1.0"}}):
            self.assertEqual(self.typed(raises=none)[:3], (0, "cad 0.1.0 is the newest release\n", ""))
        self.assertIsNone(auto_update.last(), "nothing begun")

        def looks():
            begun = auto_update.last()
            yield None, begun, None, False
            yield None, {**begun, "outcome": "installed", "start": False}, None, False

        with mock.patch.object(client, "_sandboxed", return_value=False), \
                mock.patch.object(updates, "pypi", return_value={"latest": "0.2.0", "lines": {"0": "0.2.0"}}), \
                mock.patch.object(sys, "_base_executable", str(self.tmp / "python3"), create=True), \
                mock.patch.object(auto_update.subprocess, "Popen") as popen:
            seen = looks()
            self.assertEqual(self.typed(raises=none, looks=seen)[:3],
                             (0, "cad 0.1.0 updated to 0.2.0\n", ""))
        told = json.loads(popen.call_args.args[0][5])
        self.assertEqual((told["target"], told["start"], told["asked"]), ("0.2.0", False, True),
                         "no server started after it, a typed update")
        self.assertNotIn("then_install", told, "the helper never runs the install command")
        record = {"release": "0.2.0", "at": 5.0, "outcome": "failed", "detail": "uv said no", "start": False}
        self.assertEqual(self.typed({"ok": True, "updating": "0.2.0", "from": "0.1.0", "since": 5.0},
                                    looks=[(None, record, None, False)])[:3],
                         (1, "", "cad update: could not update cad 0.1.0 to 0.2.0: uv said no\n"),
                         "nothing said of a server none asked for")
        judged = {"ok": True, "updating": "0.2.0", "from": "0.1.0"}
        with mock.patch.object(client, "_sandboxed", return_value=False), \
                mock.patch.object(auto_update, "asked", return_value=judged), \
                mock.patch.object(auto_update, "begin", return_value=None):
            self.assertEqual(self.typed(raises=none)[:3],
                             (1, "", "cad update: the update could not begin, so cad 0.1.0 stays as it is\n"))

    def test_without_pypi_s_answer_it_says_what_the_upgrade_got(self) -> None:
        answer = {"ok": True, "updating": None, "from": "0.1.0", "since": 5.0}
        waiting = ("0.1.0", None, "latest", True)
        for record, said in (({"release": "0.2.0", "at": 5.0, "outcome": "installed", "started": "started"},
                              (0, "cad 0.1.0 updated to 0.2.0\n", "")),
                             ({"release": "0.1.0", "at": 5.0, "outcome": "current", "started": "started"},
                              (0, "cad 0.1.0 is the newest release\n", "")),
                             ({"release": "latest", "at": 5.0, "outcome": "failed", "detail": "no network"},
                              (1, "", "cad update: could not update cad 0.1.0 to the newest release: no network; cad "
                                      "0.1.0 is running\n"))):
            with self.subTest(outcome=record["outcome"]):
                self.assertEqual(self.typed(answer, looks=[waiting, ("0.1.0", record, None, True)])[:3], said)

    def test_it_gives_up_waiting_after_ten_minutes(self) -> None:
        from cad_server.cli import update as typed

        said: list[str] = []
        clock = iter(range(0, 10_000, 100))
        code = typed.wait(lambda: (None, {"release": "0.2.0", "at": 5.0, "outcome": "underway"}, None, False), "0.1.0",
                          5.0, said=lambda words: said.append(words) or 1, clock=lambda: float(next(clock)),
                          sleep=lambda _s: None)
        self.assertEqual((code, said), (1, ["the update of cad 0.1.0 is still underway after 10 minutes: run "
                                            "`cad --version` later to see where it ended"]))


class DoctorTest(Case):
    def test_doctor_shows_the_switches_the_install_uv_and_the_last_attempt(self) -> None:
        from cad_server.cli import doctor

        auto_update._keep(self.state / auto_update.RECORD, {"release": "0.2.0", "from": "0.1.0", "at": 0.0,
                                                            "outcome": "failed", "detail": "uv said no",
                                                            "restored": True})
        lines = {check["name"]: check["detail"] for check in (doctor._check(name, *how()) for name, how in
                 (("update", doctor._update), ("attempt", doctor._attempt)))}
        self.assertEqual(lines["update"], f"update auto on, plugin update auto off; a global install by uv ({self.tool})")
        auto_update.change(False)
        auto_update.change_plugin(True)
        (self.tool / "uv-receipt.toml").unlink()
        self.assertEqual(doctor._update()[1], "this cad is not a global install, so it never updates itself; plugin "
                                              "update auto on")
        self.assertRegex(lines["attempt"], r"^0\.1\.0 to 0\.2\.0 on \S+ \S+: failed \(uv said no\); 0\.1\.0 put back$")

    def test_doctor_and_the_switch_s_status_say_the_newest_of_this_major_and_a_higher_major_in_one_line(self) -> None:
        from cad_server.cli import doctor

        line = auto_update.MAJOR_LINE.format(release="1.2.0")
        self.assertEqual(doctor._newest(), doctor._check("newest", doctor.INFO, "the version feed has not been read on "
                                                                               "this computer yet"))
        self.assertEqual(self.cli(), (0, "update auto: on\n", ""), "nothing to say without a feed")
        known = {"checked": time.time(), "feed": {"latest": "1.2.0", "lines": {"0": "0.3.0", "1": "1.2.0"}}}
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / updates.FILE).write_text(json.dumps(known), encoding="utf-8")
        with mock.patch.object(updates, "feed", wraps=updates.feed) as read:
            self.assertEqual(doctor._newest(), doctor._check(
                "newest", doctor.INFO, "cad 0.3.0 is the newest 0.x release the version feed names", [line]))
            self.assertEqual(self.cli(), (0, f"update auto: on\n{line}\n", ""))
            self.assertEqual(self.cli("off"), (0, "update auto: off\n", ""), "said by the status alone")
        self.assertTrue(read.call_args_list and all(call.kwargs == {"fetch": False} for call in read.call_args_list),
                        "read as last kept, never fetched")
        known["feed"] = {"latest": "0.3.0", "lines": {"0": "0.3.0"}}
        (self.state / updates.FILE).write_text(json.dumps(known), encoding="utf-8")
        self.assertEqual(doctor._newest(), doctor._check("newest", doctor.INFO,
                                                         "cad 0.3.0 is the newest 0.x release the version feed names"))
        known["feed"] = {"latest": "1.2.0"}  # none of this major named
        (self.state / updates.FILE).write_text(json.dumps(known), encoding="utf-8")
        self.assertEqual(doctor._newest()["detail"], "the version feed names no 0.x release; its newest is cad 1.2.0")

    def test_doctor_shows_the_plugin_s_record(self) -> None:
        from cad_server._internal import plugin_catch_up
        from cad_server.cli import doctor

        self.assertEqual(doctor._catch_up(), (doctor.INFO, "no record of the plugin being up to date on this "
                                                           "computer"))
        plugin_catch_up.noted("0.0.9")
        self.assertEqual(doctor._catch_up()[1], "the plugin is up to date for cad 0.0.9")
        plugin_catch_up._change(lambda found: {**found, "release": "0.1.0", "at": 0.0, "tries": 2,
                                               "outcome": "failed", "code": 1})
        self.assertRegex(doctor._catch_up()[1], r"^the plugin is up to date for cad 0\.0\.9; the last run, "
                                                r"for cad 0\.1\.0 on \S+ \S+: failed \(exit 1\), try 2 of 3$")
        plugin_catch_up._change(lambda found: {**found, "owed": "0.1.0"})
        self.assertRegex(doctor._catch_up()[1], r"^the plugin is up to date for cad 0\.0\.9; a run is owed for cad "
                                                r"0\.1\.0 \(the last did not go well\); the last run, ")


class PluginCatchUpTest(Case):
    """The server's rule (``plugin_catch_up``): where the person's switch is on and this cad is newer than the release
    the plugin is up to date for, ``cad plugin install`` once, by this cad's own command, detached; bounded; however cad
    got newer; never where the check is off, a test said the server runs nothing, the cad is no global install or a
    development build, or the bridge owes its own run of the hosted install command."""

    def setUp(self) -> None:
        super().setUp()
        from cad_server._internal import install_script, plugin_catch_up

        self.catch_up = plugin_catch_up
        # Not set and empty, the runner's way to say the server runs nothing by itself: here the rule is asked.
        patch = mock.patch.dict(os.environ, {install_script.INSTALLER_ENV: "the-install-command"})
        patch.start()
        self.addCleanup(patch.stop)
        self.told: list[str] = []

    def switch_on(self) -> None:
        """The switch on as an earlier setup left it, with no record (``change_plugin`` would write one)."""
        from cad_server.settings import update_section

        update_section(auto_update.PLUGIN_SECTION, lambda kept: {**kept, "auto_update": True})

    def begun(self, now: float | None = None):
        with mock.patch.object(self.catch_up.subprocess, "Popen") as popen:
            process = self.catch_up.begin(self.told.append, now=now)
        return process, popen

    def test_a_computer_never_up_to_date_is_owed_the_run_an_app_s_failure_left_and_tries_it_at_most_three_times(
            self) -> None:
        """No ``for`` ever (a fresh install), and a person's run where one app failed: that run marks this release as
        owed a run (``owed``), which the hosted install command's switch, told the run did not go well, leaves as it
        is and keeps no release by. The server, past its first minute, runs it as it would for a newer cad: once, then
        again an hour after each try began and not before, at most three runs for this release in all. A later run
        that goes well clears the mark and keeps the release; the switch turned on by hand does too."""
        self.switch_on()
        self.catch_up.ended(0, failed=True)  # a person's run: exit status 0, one app failed
        self.assertEqual(self.catch_up.read(), {"owed": "0.1.0"})
        auto_update.change_plugin(True, "0.1.0", note=False)  # the install command's switch, with CAD_INSTALL_FAILED=1
        self.assertEqual(self.catch_up.read(), {"owed": "0.1.0"})
        started, now = [0.0], [1_000_000.0]
        catcher = self.catch_up.Catcher(started=0.0, clock=lambda: started[0])
        with mock.patch.object(self.catch_up.subprocess, "Popen") as popen, mock.patch("time.time", lambda: now[0]):
            popen.return_value.poll.return_value = None
            started[0] = self.catch_up.START_SECONDS - 1
            self.assertFalse(catcher.tend(self.told.append), "never in the server's first minute")
            self.assertEqual(self.catch_up.read(), {"owed": "0.1.0"}, "nor taken as up to date")
            started[0] = self.catch_up.START_SECONDS
            for tries in range(1, self.catch_up.TRIES + 1):
                self.assertTrue(catcher.tend(self.told.append), tries)
                record = self.catch_up.read()
                self.assertEqual((record["release"], record["tries"], record["outcome"], "for" in record),
                                 ("0.1.0", tries, "underway", False))
                with mock.patch.dict(os.environ, {self.catch_up.SERVER_ENV: str(record["at"])}):
                    self.catch_up.ended(0, failed=True)  # the same app failed again
                popen.return_value.poll.return_value = 0
                now[0] += self.catch_up.RETRY_SECONDS - 1
                self.assertFalse(catcher.tend(self.told.append), "not within the hour")
                popen.return_value.poll.return_value = None
                now[0] += 1
            record = self.catch_up.read()
            self.assertEqual((record["owed"], record["outcome"], record["code"], record["tries"]),
                             ("0.1.0", "failed", 0, 3))
            self.assertFalse(catcher.tend(self.told.append))
            now[0] += 100 * self.catch_up.RETRY_SECONDS
            self.assertFalse(catcher.tend(self.told.append), "three runs for one release, then nothing more")
            self.assertEqual(popen.call_count, self.catch_up.TRIES)
        # A later run that goes well clears the mark and keeps this release.
        self.catch_up.ended(0)
        record = self.catch_up.read()
        self.assertEqual((record["for"], "owed" in record), ("0.1.0", False))
        self.assertFalse(self.catch_up.due())
        # The switch turned on by hand means "from this release on": the mark goes, the release is kept.
        self.catch_up.ended(1)
        self.assertEqual(self.catch_up.read()["owed"], "0.1.0")
        auto_update.change_plugin(True)
        record = self.catch_up.read()
        self.assertEqual((record["for"], "owed" in record), ("0.1.0", False))
        # A mark of an earlier release is owed by a newer cad too, until a run goes well.
        self.catch_up._change(lambda found: {"owed": "0.0.9"})
        self.assertTrue(self.catch_up.due())
        self.assertEqual(self.catch_up.read(), {"owed": "0.0.9"}, "a computer owed a run is not taken as up to date")

    def test_the_switch_off_runs_nothing_and_writes_nothing(self) -> None:
        self.assertFalse(self.catch_up.due())
        self.assertFalse((self.state / self.catch_up.RECORD).exists())

    def test_with_no_record_it_is_this_release_s_and_nothing_runs(self) -> None:
        self.switch_on()
        self.assertFalse(self.catch_up.due(), "never right after a fresh install, nor on a computer that had it on")
        self.assertEqual(self.catch_up.read(), {"for": "0.1.0"})
        self.assertFalse(self.catch_up.due())

    def test_a_newer_cad_runs_it_once_by_its_own_command_detached_its_output_logged(self) -> None:
        self.switch_on()
        self.catch_up.noted("0.0.9")
        self.assertTrue(self.catch_up.due())
        catcher = self.catch_up.Catcher(wait=0.0)  # a server started a while ago
        # A server started under an earlier release's run, or a hosted install command's way of saying a run ends
        # badly, passes neither on: its run is named by this release's own mark alone.
        with mock.patch.object(self.catch_up.subprocess, "Popen") as popen, \
                mock.patch.dict(os.environ, {"PYTHONPATH": "/src", self.catch_up.ATTEMPT_ENV: "6.0",
                                             self.catch_up.FAILED_ENV: "1"}):
            popen.return_value.poll.return_value = None  # still running
            self.assertTrue(catcher.tend(self.told.append))
            self.assertFalse(catcher.tend(self.told.append), "never a second while this server's run runs")
        (line,), options = popen.call_args
        self.assertEqual(line, [str(auto_update.tool_command(self.tool)), "plugin", "install"])
        self.assertEqual(self.told, ["cad 0.1.0 is newer than the one the plugin is up to date for: `cad plugin "
                                     "install` runs once now, in the background"])
        record = self.catch_up.read()
        self.assertEqual((record["for"], record["release"], record["tries"], record["outcome"]),
                         ("0.0.9", "0.1.0", 1, "underway"))
        self.assertEqual(options["env"][self.catch_up.SERVER_ENV], str(record["at"]))
        for name in ("PYTHONPATH", self.catch_up.ATTEMPT_ENV, self.catch_up.FAILED_ENV):
            self.assertNotIn(name, options["env"])
        self.assertEqual(Path(options["stdout"].name), self.state / auto_update.INSTALL_LOG)
        self.assertEqual(options["start_new_session" if os.name != "nt" else "creationflags"],
                         True if os.name != "nt" else 0x08000000 | 0x00000200)
        self.assertEqual(popen.call_count, 1)
        self.assertFalse(self.catch_up.due(), "underway: waited for, whichever server began it")
        with mock.patch.dict(os.environ, {self.catch_up.SERVER_ENV: str(record["at"])}):
            self.catch_up.ended(0)
        record = self.catch_up.read()
        self.assertEqual((record["for"], record["outcome"], record["code"]), ("0.1.0", "ok", 0))
        self.assertFalse(self.catch_up.due(), "up to date")
        self.assertEqual(self.catch_up.last("0.1.0"), "ok")

    def test_a_run_that_exited_without_saying_how_it_ended_is_kept_as_failed_with_its_exit_status(self) -> None:
        self.switch_on()
        self.catch_up.noted("0.0.9")
        catcher = self.catch_up.Catcher(wait=0.0)  # a server started a while ago
        with mock.patch.object(self.catch_up.subprocess, "Popen") as popen:
            popen.return_value.poll.return_value = None
            self.assertTrue(catcher.tend(self.told.append))
            popen.return_value.poll.return_value = 7  # it crashed before it could say
            self.assertFalse(catcher.tend(self.told.append), "and nothing again within the hour")
        record = self.catch_up.read()
        self.assertEqual((record["outcome"], record["code"], record["tries"]), ("failed", 7, 1))
        self.assertEqual(self.catch_up.last("0.1.0"), "failed")

    def test_a_server_begins_none_in_its_first_minute_and_one_once_it_has_passed(self) -> None:
        """A person's install command that updated cad restarted the server, and goes on to the plugin a moment later:
        the server's first minute (``START_SECONDS``, by its own monotonic clock from its start) is that command's."""
        self.switch_on()
        self.catch_up.noted("0.0.9")
        before = self.catch_up.read()
        clock = [5000.0]
        catcher = self.catch_up.Catcher(clock[0], clock=lambda: clock[0])
        self.assertEqual((catcher.wait, self.catch_up.START_SECONDS), (60.0, 60.0))
        with mock.patch.object(self.catch_up.subprocess, "Popen") as popen:
            popen.return_value.poll.return_value = None
            for seconds in (0.0, 1.0, self.catch_up.START_SECONDS - 0.5):
                clock[0] = 5000.0 + seconds
                self.assertFalse(catcher.tend(self.told.append), seconds)
            popen.assert_not_called()
            self.assertEqual(self.catch_up.read(), before, "nothing kept, no try spent")
            clock[0] = 5000.0 + self.catch_up.START_SECONDS
            self.assertTrue(catcher.tend(self.told.append))
        self.assertEqual(popen.call_count, 1)
        self.assertEqual((self.catch_up.read()["tries"], self.catch_up.read()["outcome"]), (1, "underway"))
        # Made with no start, it starts now, by the monotonic clock.
        fresh = self.catch_up.Catcher()
        self.assertLess(abs(fresh.started - time.monotonic()), 5.0)
        self.assertIs(fresh.clock, time.monotonic)

    def test_while_a_run_holds_the_lock_the_server_begins_none_and_keeps_nothing(self) -> None:
        """A person's run (or the hosted install command's) holds the lock: the server's tending begins nothing and
        leaves the record exactly as it was, so no try is spent; with the lock free and the plugin up to date for this
        release (that run kept it), still nothing; free and not up to date, one run."""
        from cad_server._internal import file_lock

        self.switch_on()
        self.catch_up.noted("0.0.9")
        record = self.state / self.catch_up.RECORD
        before = record.read_bytes()
        catcher = self.catch_up.Catcher(wait=0.0)
        with mock.patch.object(self.catch_up.subprocess, "Popen") as popen:
            popen.return_value.poll.return_value = None
            with file_lock.exclusive(self.state / self.catch_up.LOCK):
                self.assertTrue(self.catch_up.due(), "the rule alone would run it")
                self.assertFalse(catcher.tend(self.told.append))
                self.assertFalse(catcher.tend(self.told.append), "at every tending while it is held")
                self.assertEqual(record.read_bytes(), before)
                self.assertEqual(self.told, [])
            popen.assert_not_called()
            self.catch_up.noted("0.1.0")  # that run ended well: up to date for this release
            after = record.read_bytes()
            self.assertFalse(catcher.tend(self.told.append))
            popen.assert_not_called()
            self.assertEqual(record.read_bytes(), after)
            self.catch_up.noted("0.0.9")  # free, and not up to date
            self.assertTrue(catcher.tend(self.told.append))
        self.assertEqual(popen.call_count, 1)
        self.assertEqual(self.catch_up.read()["tries"], 1)

    def test_a_failed_run_is_tried_again_at_most_three_runs_each_an_hour_after_the_last_never_in_a_loop(self) -> None:
        self.switch_on()
        self.catch_up.noted("0.0.9")
        now = 1_000_000.0
        for tries in range(1, self.catch_up.TRIES + 1):
            with self.subTest(tries=tries):
                self.assertTrue(self.catch_up.due(now=now))
                self.begun(now=now)
                with mock.patch.dict(os.environ, {self.catch_up.SERVER_ENV: str(now)}):
                    self.catch_up.ended(1)
                self.assertEqual((self.catch_up.read()["tries"], self.catch_up.read()["outcome"]), (tries, "failed"))
                self.assertEqual(self.catch_up.read()["for"], "0.0.9", "a failure writes none")
                self.assertFalse(self.catch_up.due(now=now), "not by the same tending")
                self.assertFalse(self.catch_up.due(now=now + self.catch_up.RETRY_SECONDS - 1), "nor within the hour")
                now += self.catch_up.RETRY_SECONDS
        self.assertFalse(self.catch_up.due(now=now + 100 * self.catch_up.RETRY_SECONDS), "and never again")
        with mock.patch.object(cad_server, "__version__", "0.1.1"):
            self.assertTrue(self.catch_up.due(now=now), "a newer cad gets runs of its own")

    def test_two_servers_never_both_begin_and_a_run_underway_of_any_release_is_waited_for(self) -> None:
        """``due`` and ``begin`` are one step: ``begin`` asks the record again under the lock, so a server that asked
        ``due`` before another kept its run begins none; a newer cad waits for an older release's run underway, and
        begins none where a run ended well since it asked."""
        self.switch_on()
        self.catch_up.noted("0.0.9")
        now = 1_000_000.0
        self.assertTrue(self.catch_up.due(now=now), "both servers ask, and are told to run it")
        first, _popen = self.begun(now=now)
        self.assertIsNotNone(first)
        second, popen = self.begun(now=now + 1)
        self.assertIsNone(second, "the second begins none")
        popen.assert_not_called()
        self.assertEqual((self.catch_up.read()["at"], self.catch_up.read()["tries"]), (now, 1))
        with mock.patch.object(cad_server, "__version__", "0.2.0"):  # a newer cad, the older release's run underway
            self.assertFalse(self.catch_up.due(now=now + 60), "waited for")
            self.assertIsNone(self.begun(now=now + 60)[0])
            self.assertEqual(self.catch_up.read()["release"], "0.1.0")
            stale = now + self.catch_up.RETRY_SECONDS
            self.assertTrue(self.catch_up.due(now=stale), "a run begun an hour ago, never ended: no longer waited for")
            self.catch_up.noted("0.2.0")  # a run that ended well since `due` was asked (another server's)
            self.assertIsNone(self.begun(now=stale)[0], "up to date: none begun")
        self.assertEqual(self.catch_up.read()["release"], "0.1.0")

    def test_a_run_that_never_said_how_it_ended_counts_as_tried_and_failed(self) -> None:
        self.switch_on()
        self.catch_up.noted("0.0.9")
        process, popen = self.begun(now=1_000_000.0)
        self.assertIs(process, popen.return_value)
        self.assertFalse(self.catch_up.due(now=1_000_000.0 + 60))
        self.assertEqual(self.catch_up.last("0.1.0", now=1_000_000.0 + 60), "underway")
        later = 1_000_000.0 + self.catch_up.RETRY_SECONDS
        self.assertEqual(self.catch_up.last("0.1.0", now=later), "failed")
        self.assertTrue(self.catch_up.due(now=later))
        with mock.patch.object(self.catch_up.subprocess, "Popen", side_effect=OSError("no such file")):
            self.assertIsNone(self.catch_up.begin(self.told.append, now=later))
        record = self.catch_up.read()
        self.assertEqual((record["tries"], record["outcome"], record["code"]), (2, "failed", None))
        self.assertIn("`cad plugin install` could not start: no such file", self.told)

    def test_the_time_is_read_once_the_lock_is_held_so_a_run_begun_while_this_server_waited_is_waited_for(self) -> None:
        """Another server keeps its run while this one waits for the state folder's lock: this one's time, read once
        the lock is held, is after that run's, which is underway and waited for. Read before the lock, it would be
        before it, which counts as a clock set back, and a second run would begin."""
        import itertools

        self.switch_on()
        self.catch_up.noted("0.0.9")
        clock = itertools.count(1_000_000)
        real = self.catch_up._change

        def another_first(change):
            real(lambda kept: {**kept, "release": "0.1.0", "at": float(next(clock)), "tries": 1, "outcome": "underway"})
            return real(change)

        with mock.patch.object(self.catch_up.time, "time", side_effect=lambda: float(next(clock))), \
                mock.patch.object(self.catch_up, "_change", side_effect=another_first), \
                mock.patch.object(self.catch_up.subprocess, "Popen") as popen:
            self.assertFalse(self.catch_up.Catcher(wait=0.0).tend(self.told.append))
        popen.assert_not_called()
        self.assertEqual((self.catch_up.read()["tries"], self.catch_up.read()["outcome"]), (1, "underway"))

    def test_the_hard_stop_closes_the_run_s_record_and_ends_the_process_waiting_on_nothing(self) -> None:
        """``HardStop``, its time come (``_stop``, here by hand: the clock is the standard library's) and the
        process's end stood in for: a run still going is kept as stopped, says its last words once, and the process
        ends with 124 -- whatever those words wait on; a run that ended by itself says nothing twice; a command that
        is done is left alone. A whole command ended by it: ``plugin/test_command.py``."""
        import threading

        from cad_server.plugin import computer

        catch_up = self.catch_up
        self.assertEqual(catch_up.STOPPED, computer.STOPPED)
        underway = {"for": "0.0.9", "release": "0.1.0", "at": 7.0, "tries": 1, "outcome": "underway"}

        def stopped(stop) -> tuple:
            self.addCleanup(stop.cancel)
            with mock.patch.object(catch_up.os, "_exit") as gone:
                stop._stop()
            found = catch_up.read()
            return [call.args for call in gone.call_args_list], found["outcome"], found.get("code")

        with mock.patch.dict(os.environ, {catch_up.SERVER_ENV: "7.0"}):
            said: list[str] = []
            catch_up._change(lambda _found: dict(underway))
            stop = catch_up.HardStop(900.0, lambda: said.append(catch_up.read()["outcome"]))
            self.assertEqual(stop._timer.interval, 900.0 + catch_up.GRACE_SECONDS, "the deadline, and a short grace")
            self.assertTrue(stop._timer.daemon, "never what keeps the process from exiting")
            self.assertEqual(stopped(stop), ([(124,)], "failed", 124))
            self.assertEqual(said, ["failed"], "its last words, once the record is closed")
            # The run ended by itself: its record and its count are its own, and the stop only ends the process.
            catch_up._change(lambda _found: dict(underway))
            stop = catch_up.HardStop(900.0, lambda: said.append("twice"))
            stop.over()
            self.assertEqual(stopped(stop), ([(124,)], "underway", None))
            # The command is done: nothing is ended.
            stop = catch_up.HardStop(900.0, lambda: said.append("twice"))
            stop.cancel()
            self.assertEqual(stopped(stop), ([], "underway", None))
            self.assertTrue(stop._timer.finished.is_set())
            # What hangs may hold the state folder's lock, which closing the record waits on: that is not waited for.
            # The process ends, and the server that began the run keeps it as failed (``Catcher``).
            held = threading.Event()
            self.addCleanup(held.set)
            with mock.patch.object(catch_up, "ended", lambda _code: held.wait()), \
                    mock.patch.object(catch_up, "CLOSE_SECONDS", 0.0):
                self.assertEqual(stopped(catch_up.HardStop(900.0, lambda: said.append("late"))),
                                 ([(124,)], "underway", None))
        self.assertEqual(said, ["failed"])

    def test_however_cad_got_newer_a_typed_update_or_one_by_hand_the_server_catches_up(self) -> None:
        self.switch_on()
        self.catch_up.noted("0.1.0")
        self.assertFalse(self.catch_up.due())
        # `cad update` typed (or `uv tool upgrade cad`, `pipx upgrade cad`): the cad the server now runs is newer.
        with mock.patch.object(cad_server, "__version__", "0.2.0"):
            self.assertTrue(self.catch_up.due())
            self.begun()
            self.assertEqual(self.catch_up.read()["release"], "0.2.0")

    def test_never_where_the_check_is_off_a_test_says_so_no_global_install_a_development_build_or_the_bridge_owes_it(
            self) -> None:
        from cad_server._internal import install_script

        self.switch_on()
        self.catch_up.noted("0.0.9")
        self.assertTrue(self.catch_up.due())
        with mock.patch.object(updates, "checking", return_value=False):  # CAD_UPDATE_CHECK=0, CI
            self.assertFalse(self.catch_up.due())
        with mock.patch.dict(os.environ, {install_script.INSTALLER_ENV: ""}):  # a test's: the server runs nothing
            self.assertTrue(self.catch_up.silenced())
            self.assertFalse(self.catch_up.due())
        with mock.patch.dict(os.environ):  # the variable names the bridge's command: `cad plugin install` needs none
            del os.environ[install_script.INSTALLER_ENV]
            self.assertTrue(self.catch_up.due())
        with mock.patch.object(sys, "prefix", str(self.tmp)):  # not a global install
            self.assertFalse(self.catch_up.due())
        with mock.patch.object(cad_server, "__version__", "0.1.0-dev.20261118"):
            self.assertFalse(self.catch_up.due())
        # BRIDGE-ONLY: install mode owed is the bridge's one run; ended well, its command's last step wrote the record.
        install_script.owe("0.1.0")
        self.assertFalse(self.catch_up.due())
        record = install_script.read()
        install_script._write({**record, "state": install_script.DONE})
        auto_update.change_plugin(True, "0.1.0")  # `cad plugin update auto on`, the install command's last step
        self.assertFalse(self.catch_up.due(), "no second run after the bridge's")
        self.assertEqual(self.catch_up.read()["for"], "0.1.0")

    def test_the_bridge_s_run_done_with_an_app_failed_holds_nothing_back_and_leaves_a_run_owed(self) -> None:
        """BRIDGE-ONLY. While install mode is owed, its run is the computer's one; it is done once cad is installed,
        whatever the apps did, and where an app's step failed the plugin is then this rule's: held back no longer, and
        owed a run for the release install mode was owed for, though no run of the global install marked it (here the
        plugin's step ran a cad from uv's cache, or none could run it)."""
        from cad_server._internal import install_script

        self.switch_on()
        self.catch_up.noted("0.0.9")
        install_script.owe("0.1.0", now=1000.0)
        self.assertFalse(self.catch_up.due(), "held while install mode is owed")
        # An attempt begun at 1000.0 whose report says cad is there and an app's step failed.
        install_script._write({**install_script.read(), "attempts": 1, "first": 1000.0, "last": 1000.0,
                               "outcome": install_script.RUNNING})
        (self.state / install_script.REPORT).write_text(json.dumps({"setup": 0, "apps": {
            "claude": "installed", "gemini": "failed"}}), encoding="utf-8")
        self.assertFalse(self.catch_up.due(), "held while it runs")
        install_script.Carrier(began=0.0).tend("0.1.0", self.told.append, mono=10.0, wall=1100.0)
        self.assertEqual(install_script.read()["state"], install_script.DONE)
        self.assertEqual(self.catch_up.read(), {"for": "0.0.9", "owed": "0.1.0"})
        self.assertTrue(self.catch_up.due(), "the plugin is this rule's now")
        self.begun()
        self.assertEqual((self.catch_up.read()["release"], self.catch_up.read()["tries"]), ("0.1.0", 1))

    def test_turned_on_by_an_install_run_ending_badly_it_is_on_and_nothing_is_taken_as_up_to_date(self) -> None:
        """The hosted install command turns the switch on as its last step wherever cad is there, and says how its run
        is ending (``FAILED_ENV``), as it did for 0.11.12 and 0.11.13, which read it the same way: ending badly, the
        switch is on and ``for`` stays as it was, so the server runs the command again for this release; ending well,
        or typed by a person, ``for`` is this release. By the command itself and by the server alike."""
        from cad_server.engine.daemon import switch_plugin

        self.catch_up.noted("0.0.9")  # an earlier run ended well, for 0.0.9
        for by_the_server in (False, True):
            with self.subTest(by_the_server=by_the_server):
                auto_update.change_plugin(False)
                self.catch_up._change(lambda found: {**found, "for": "0.0.9"})
                answer = (lambda request: switch_plugin(request)) if by_the_server else (lambda _r: {"failed":
                                                                                                    "unknown request"})
                with mock.patch.object(client, "request", side_effect=lambda request, **_o: answer(request)) as asked, \
                        mock.patch.dict(os.environ, {self.catch_up.FAILED_ENV: "1"}):
                    self.assertEqual(self.cli("update", "auto", "on", main=plugin_command.main),
                                     (0, "plugin update auto: on\n", ""))
                self.assertEqual(asked.call_args.args[0], {"op": "plugin_auto_update", "on": True, "release": "0.1.0",
                                                           "note": False})
                self.assertTrue(auto_update.plugin_switch())
                self.assertEqual(self.catch_up.read()["for"], "0.0.9", "nothing taken as up to date")
                self.assertTrue(self.catch_up.due(), "so the server runs the command again for this release")
                for ending in ("", None):  # ending well (the install command says so), or a person typing it
                    self.catch_up._change(lambda found: {**found, "for": "0.0.9"})
                    with mock.patch.object(client, "request", side_effect=lambda request, **_o: answer(request)) \
                            as asked, mock.patch.dict(os.environ, {} if ending is None else
                                                      {self.catch_up.FAILED_ENV: ending}):
                        if ending is None:
                            os.environ.pop(self.catch_up.FAILED_ENV, None)
                        self.cli("update", "auto", "on", main=plugin_command.main)
                    self.assertNotIn("note", asked.call_args.args[0])
                    self.assertEqual(self.catch_up.read()["for"], "0.1.0", "from this release on")
                # A cad that is no global install (the newest release, run from uv's cache) asks as a run ending
                # badly does: the switch, and nothing of its own release, which the installed cad may never reach.
                self.catch_up._change(lambda found: {**found, "for": "0.0.9"})
                with mock.patch.object(client, "request", side_effect=lambda request, **_o: answer(request)) as asked, \
                        mock.patch.object(sys, "prefix", str(self.tmp)), \
                        mock.patch.object(cad_server, "__version__", "9.0.0"):
                    self.assertTrue(plugin_command._keep(True, note=True))
                    self.catch_up.ended(0)
                self.assertEqual(asked.call_args.args[0], {"op": "plugin_auto_update", "on": True, "release": "9.0.0",
                                                           "note": False})
                self.assertEqual(self.catch_up.read()["for"], "0.0.9")
        # No record at all (a computer where no run ever ended well), the run ending badly: nothing written; the rule
        # for no record then takes this release as up to date, and the command runs once cad is newer.
        (self.state / self.catch_up.RECORD).unlink()
        with mock.patch.object(client, "request", return_value={"failed": "unknown request"}), \
                mock.patch.dict(os.environ, {self.catch_up.FAILED_ENV: "1"}):
            self.cli("update", "auto", "on", main=plugin_command.main)
        self.assertFalse((self.state / self.catch_up.RECORD).exists())

    def test_turning_it_on_takes_the_command_as_up_to_date_for_the_cad_that_asked(self) -> None:
        from cad_server.engine.daemon import switch_plugin

        auto_update.change_plugin(True, "0.3.0")
        self.assertEqual(self.catch_up.read()["for"], "0.3.0")
        auto_update.change_plugin(False)
        self.assertEqual(self.catch_up.read()["for"], "0.3.0", "turned off: the record stays")
        self.assertEqual(switch_plugin({"op": "plugin_auto_update", "on": True, "release": "0.4.0"}),
                         {"ok": True, "on": True})
        self.assertEqual(self.catch_up.read()["for"], "0.4.0", "the asking cad's, not the server's")
        self.assertEqual(switch_plugin({"op": "plugin_auto_update", "on": True}), {"ok": True, "on": True})
        self.assertEqual(self.catch_up.read()["for"], "0.1.0", "an earlier command's: this server's")
        with mock.patch.object(client, "request", return_value={"failed": "unknown request"}) as asked:
            self.cli("update", "auto", "on", main=plugin_command.main)
        self.assertEqual(asked.call_args.args[0], {"op": "plugin_auto_update", "on": True, "release": "0.1.0"})

    def test_the_server_catches_up_then_counts_at_its_start_and_never_while_it_stops(self) -> None:
        import threading

        from cad_server.engine.daemon import Daemon

        calls: list[str] = []
        stand_in = types.SimpleNamespace(draining=False, stopping=threading.Event(),
                                         catching=types.SimpleNamespace(tend=lambda told: calls.append("catch up")))
        with mock.patch.object(auto_update, "report", side_effect=lambda: calls.append("count")):
            Daemon.caught_up(stand_in)
            stand_in.stopping.set()
            Daemon.caught_up(stand_in)
        self.assertEqual(calls, ["catch up", "count"])


class UnderAPluginRunTest(Case):
    """cad's own update while a run of ``cad plugin install`` or ``cad plugin update`` is going (its lock held:
    ``plugin_catch_up.running``): the automatic one is not due, a typed one is refused in one line, and none begins,
    which would replace the environment's files under the run."""

    def another_run(self):
        from cad_server._internal import file_lock, plugin_catch_up

        self.state.mkdir(parents=True, exist_ok=True)
        return file_lock.exclusive(self.state / plugin_catch_up.LOCK)

    def test_no_update_begins_while_a_run_holds_its_lock_and_one_does_once_it_has_ended(self) -> None:
        from cad_server._internal import plugin_catch_up
        from cad_server.cli import update as typed

        newer = {"latest": "0.2.0", "lines": {"0": "0.2.0"}}
        self.assertFalse(plugin_catch_up.running())
        self.assertFalse((self.state / plugin_catch_up.LOCK).exists(), "asked without making the lock's file")
        with self.feed("0.2.0"), mock.patch.object(updates, "pypi", return_value=newer), \
                mock.patch.object(sys, "_base_executable", str(self.tmp / "python3"), create=True), \
                mock.patch.object(auto_update.subprocess, "Popen") as popen:
            self.assertEqual(auto_update.due(), auto_update.Due("0.2.0", "0.2.0"))
            with self.another_run():
                self.assertTrue(plugin_catch_up.running())
                # The automatic update: not due, at a start and at a tending alike.
                self.assertIsNone(auto_update.due())
                self.assertFalse(auto_update.at_start())
                self.assertFalse(auto_update.tend(working=False, ran=False, quiet_for=0.0))
                self.assertIsNone(auto_update.after_failed_start())
                # A typed one: refused in one line, by the server that judges it and by the command with none.
                self.assertEqual(auto_update.asked(), {"failed": auto_update.INSTALLING})
                err = io.StringIO()
                with mock.patch.object(client, "request", side_effect=client.NotRunning(client.NOT_RUNNING)), \
                        mock.patch.object(client, "_sandboxed", return_value=False), redirect_stderr(err):
                    self.assertEqual(typed.main([]), 1)
                self.assertEqual(err.getvalue(), "cad update: an install into the agent apps is running now, and cad "
                                                 "is not updated under it: run `cad update` again once it has ended\n")
                # And where a run began after the check, asked again as the update begins.
                self.assertFalse(auto_update.trigger("0.2.0"))
                self.assertIsNone(auto_update.begin("0.2.0"))
                self.assertEqual((popen.call_count, auto_update.last()), (0, None))
            self.assertFalse(plugin_catch_up.running())
            self.assertEqual(auto_update.asked(), {"ok": True, "updating": "0.2.0", "from": "0.1.0"})
            self.assertTrue(auto_update.at_start())
            self.assertEqual((popen.call_count, auto_update.last()["outcome"]), (1, "underway"))


class UpdateCountTest(Case):
    """Each ended attempt of cad's own update counted once (``auto_update.report``, ``event``): the event each kind of
    record makes, marked as counted, the one before a new attempt counted first, and the wait for the install
    command's run for the cad an update installed."""

    def setUp(self) -> None:
        super().setUp()
        from cad_server._internal import plugin_catch_up

        self.catch_up = plugin_catch_up

    def ended(self, **fields) -> dict:
        record = {"release": "0.2.0", "from": "0.1.0", "at": 5.0, "tries": 1, "ended": 6.0, "outcome": "installed",
                  "detail": "uv said", "installer": "uv", "asked": False, **fields}
        auto_update._keep(self.state / auto_update.RECORD, record)
        return record

    def test_each_kind_of_record_is_the_event_it_makes(self) -> None:
        base = {"earlier": "0.1.0", "reason": None, "tries": 1, "installer": "uv", "asked": False, "plugin": "none"}
        for fields, made in (
                ({}, {"outcome": "installed"}),
                ({"outcome": "current"}, {"outcome": "current"}),
                ({"outcome": "failed", "detail": "uv said no", "tries": 2}, {"outcome": "failed", "reason": "upgrade",
                                                                             "tries": 2}),
                ({"outcome": "failed", "detail": "it installed 0.0.9, which it may not end on"},
                 {"outcome": "failed", "reason": "older"}),
                # `--major` that did not cross: a newer release than the one that ran, never `older`
                ({"outcome": "failed", "detail": "it installed 0.1.5, not 1.0.0", "major": True},
                 {"outcome": "failed", "reason": "upgrade"}),
                ({"outcome": "failed", "restored": True}, {"outcome": "restored", "reason": "upgrade"}),
                ({"outcome": "failed", "restored": False}, {"outcome": "failed", "reason": "put_back"}),
                ({"asked": True, "installer": "pipx"}, {"outcome": "installed", "asked": True, "installer": "pipx"}),
                ({"installer": None, "asked": None}, {"outcome": "installed"}),  # kept before it named them: this cad's
        ):
            with self.subTest(fields=fields):
                self.assertEqual(auto_update.event(self.ended(**fields)), {**base, **made})
        self.assertIsNone(auto_update.event({"release": "0.2.0", "at": 5.0, "outcome": "underway"}), "not ended")

    def test_a_newer_cad_s_count_says_how_the_install_command_s_run_for_it_went_and_waits_while_it_runs(self) -> None:
        record = self.ended()
        self.catch_up._change(lambda found: {**found, "release": "0.2.0", "at": time.time(), "tries": 1,
                                             "outcome": "underway"})
        self.assertIs(auto_update.event(record), auto_update.WAIT)
        with mock.patch("cad_server.analytics.update") as counted:
            self.assertFalse(auto_update.report(), "waits for it")
        counted.assert_not_called()
        for outcome in ("ok", "failed"):
            with self.subTest(outcome=outcome):
                self.catch_up._change(lambda found: {**found, "outcome": outcome})
                self.assertEqual(auto_update.event(record)["plugin"], outcome)
        self.catch_up._change(lambda found: {**found, "release": "0.1.9"})
        self.assertEqual(auto_update.event(record)["plugin"], "none", "none ran for it")
        self.assertEqual(auto_update.event(self.ended(outcome="current"))["plugin"], "none")

    def test_the_plugin_field_counts_only_a_run_begun_since_the_attempt_began(self) -> None:
        record = self.ended()  # the attempt began at 5.0
        self.catch_up._change(lambda found: {**found, "release": "0.2.0", "at": 4.0, "tries": 1, "outcome": "ok"})
        self.assertEqual(auto_update.event(record)["plugin"], "none", "a run begun before this attempt is another's")
        self.catch_up._change(lambda found: {**found, "at": 5.0})
        self.assertEqual(auto_update.event(record)["plugin"], "ok")

    def test_a_new_attempt_counts_the_one_before_even_while_its_install_command_runs(self) -> None:
        """No event is dropped: where the attempt before still waits for the install command's run for the cad it
        installed, a new attempt counts it as it stands, that run ``underway``."""
        self.ended()
        self.catch_up._change(lambda found: {**found, "release": "0.2.0", "at": time.time(), "tries": 1,
                                             "outcome": "underway"})
        with mock.patch("cad_server.analytics.update") as counted, \
                mock.patch.object(auto_update.subprocess, "Popen"), \
                mock.patch.object(sys, "_base_executable", str(self.tmp / "python3"), create=True):
            self.assertFalse(auto_update.report(), "the server's own count waits for it")
            counted.assert_not_called()
            self.assertTrue(auto_update.trigger("0.2.1", automatic=False))
        counted.assert_called_once_with(earlier="0.1.0", outcome="installed", reason=None, tries=1, installer="uv",
                                        asked=False, plugin="underway")
        from cad_server import analytics

        self.assertEqual(analytics._update_event("0.1.0", "installed", None, 1, "uv", False, "underway")["plugin"],
                         "underway", "a word the sender keeps and sends")
        self.assertIsNone(analytics._update_event("0.1.0", "current", None, 1, "uv", False, "underway"))

    def test_counted_once_and_marked_so(self) -> None:
        self.ended(outcome="failed", detail="uv said no", restored=True)
        with mock.patch("cad_server.analytics.update") as counted:
            self.assertTrue(auto_update.report())
            self.assertFalse(auto_update.report(), "once")
        counted.assert_called_once_with(earlier="0.1.0", outcome="restored", reason="upgrade", tries=1,
                                        installer="uv", asked=False, plugin="none")
        self.assertTrue(auto_update.last()["reported"])
        auto_update._keep(self.state / auto_update.RECORD, {"release": "0.2.0", "at": 7.0, "outcome": "underway"})
        with mock.patch("cad_server.analytics.update") as counted:
            self.assertFalse(auto_update.report(), "underway: nothing ended yet")
        counted.assert_not_called()
        (self.state / auto_update.RECORD).unlink()
        self.assertFalse(auto_update.report(), "no attempt")

    def test_a_new_attempt_counts_the_one_before_it_replaces(self) -> None:
        self.ended(outcome="failed", detail="uv said no", release="0.2.0")
        with mock.patch("cad_server.analytics.update") as counted, \
                mock.patch.object(auto_update.subprocess, "Popen"), \
                mock.patch.object(sys, "_base_executable", str(self.tmp / "python3"), create=True):
            self.assertTrue(auto_update.trigger("0.2.1", automatic=False))
        counted.assert_called_once_with(earlier="0.1.0", outcome="failed", reason="upgrade", tries=1,
                                        installer="uv", asked=False, plugin="none")
        self.assertEqual((auto_update.last()["release"], auto_update.last()["outcome"]), ("0.2.1", "underway"))


def _end(pid: int) -> None:
    """Process ``pid`` ended where it still runs (a test's leftover); quiet where it is gone."""
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass


def _gone(pid: int, within: float = 30.0) -> bool:
    """Whether process ``pid`` has exited, awaited for up to ``within`` s: on Windows by its own termination signal; on
    POSIX, gone or a zombie (its parent, stopped with it, no longer reaps it: in a container nothing may reap an
    orphan). No program is needed where it is not there (``_state``)."""
    if os.name == "nt":
        from tests.python.support.engine_daemon import _windows_exited

        return _windows_exited(pid, int(within * 1000))
    deadline = time.monotonic() + within
    while True:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        state = _state(pid)
        if state is not None and (not state or state.startswith("Z")):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


def _state(pid: int) -> str | None:
    """The state of process ``pid`` as the system says it ('Z' a zombie), '' where it is no longer listed, None where
    nothing here can say: on Linux ``/proc/<pid>/stat``, its field after the closing parenthesis of the command name
    (which may itself hold spaces or parentheses); elsewhere ``ps`` where it is found (macOS). Some test jobs' Linux
    has no ``ps``."""
    if Path("/proc").is_dir():
        try:
            stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        fields = stat[stat.rfind(")") + 1:].split()
        return fields[0] if fields else ""
    ps = shutil.which("ps")
    if ps is None:
        return None
    return subprocess.run([ps, "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()


if __name__ == "__main__":
    unittest.main()
