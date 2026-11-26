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
import re
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
from cad_server._internal import auto_update, auto_update_helper as helper, store
from cad_server.cli import auto_update as command, plugin as plugin_command
from tests.python.support.agent_apps import a_home_of_its_own

RECEIPT = '[tool]\nrequirements = [{ name = "cad", specifier = "==0.1.0" }]\nentrypoints = [{ name = "cad" }]\n'
# The uv cad carries, as it is found: each test's computer stands it in (``Case``).
CARRIED_UV = auto_update.carried_uv


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
                      mock.patch.object(updates, "checking", return_value=True),
                      # The uv the update builds with is the stand-in on PATH, and the environment reads the pointer.
                      mock.patch.object(auto_update, "carried_uv", return_value=None),
                      mock.patch.object(store, "switches", return_value=True)):
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
    def test_a_global_install_is_one_uv_or_pipx_made_and_names_the_uv_it_builds_with(self) -> None:
        found = auto_update.global_install()
        self.assertEqual((found.installer, found.prefix), ("uv", self.tool))
        self.assertEqual(os.path.normcase(found.uv), os.path.normcase(str(self.uv)), "the person's, none carried")
        self.assertEqual(found.launcher, auto_update.tool_command(self.tool))
        carried = self.tmp / "carried" / "uv"
        with mock.patch.object(auto_update, "carried_uv", return_value=str(carried)):
            self.assertEqual(auto_update.global_install().uv, str(carried), "the uv cad carries first")
        with mock.patch.object(auto_update, "find_uv", return_value=None):
            self.assertIsNone(auto_update.global_install().uv, "a global install with no uv to build with")
        for receipt in (None, '[tool]\nrequirements = [{ name = "other" }, { name = "cad" }]\n', "not toml ["):
            with self.subTest(receipt=receipt):
                if receipt is None:
                    (self.tool / "uv-receipt.toml").unlink(missing_ok=True)
                else:
                    (self.tool / "uv-receipt.toml").write_text(receipt, encoding="utf-8")
                self.assertIsNone(auto_update.global_install())
        (self.tool / "uv-receipt.toml").write_text('[tool]\nrequirements = ["cad==0.1.0"]\n', encoding="utf-8")
        self.assertEqual(auto_update.uv_tool(), self.tool, "a receipt's requirement as a string")

    def test_what_is_built_is_the_release_named_else_this_major_s_newest_never_below_the_release_that_runs(self):
        self.assertEqual(auto_update.requirement("0.2.0", "0.1.0"), "cad==0.2.0")
        self.assertEqual(auto_update.requirement(None, "0.1.0"), "cad>=0.1.0,<1")

    def test_the_bound_is_the_major_of_the_release_that_runs_and_its_floor_that_release(self) -> None:
        for version, bound in (("0.11.12", "cad>=0.11.12,<1"), ("0.12.0", "cad>=0.12.0,<1"), ("1.4.2", "cad>=1.4.2,<2"),
                               ("9.0.0", "cad>=9.0.0,<10"), ("10.2.3", "cad>=10.2.3,<11")):
            with self.subTest(version=version):
                self.assertEqual(auto_update.bound(version), bound)
        for version in ("0.11.12-dev.1", "1.0", "", None):
            with self.subTest(version=version), self.assertRaises(ValueError):
                auto_update.bound(version)

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
        ``RUN_SECONDS``, a hard stop armed for them before the run begins and let go as the command ends
        (``plugin_catch_up.HardStop``), and keeps how it ended in the server's record; typed by a person, or under the
        name an earlier release gives its server's run (``CAD_INSTALL_ATTEMPT``), it runs as long as it runs. What it runs, the
        deadline's effect and the stop's are ``tests/python/packages/cad_server/plugin/test_command.py``'s."""
        from cad_server._internal import plugin_catch_up
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
            self.assertEqual(plugin_catch_up.deadline(), plugin_catch_up.RUN_SECONDS)
            self.assertEqual(self.cli("install", main=plugin_command.main)[0], 124)
        self.assertEqual([call[0] for call in steps.mock_calls],
                         ["HardStop", "install", "HardStop().over", "HardStop().cancel"])
        self.assertEqual(steps.HardStop.call_args.args, (float(plugin_catch_up.RUN_SECONDS),))
        self.assertEqual({name: value for name, value in steps.install.call_args.kwargs.items() if name != "going"},
                         {"prog": "cad plugin install", "seconds": float(plugin_catch_up.RUN_SECONDS)})
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
    """The uv the update builds with is the one cad carries, of the release that runs: beside the ``uv`` package it
    imports (a stored release's ``bin``), else where ``uv.find_uv_bin`` looks."""

    def test_the_uv_beside_the_package_imported_first_then_the_one_uv_finds(self) -> None:
        stored = self.tmp / "store" / "0.2.0-cp314"
        (stored / "uv").mkdir(parents=True)
        beside = stored / "bin" / ("uv.exe" if os.name == "nt" else "uv")
        found = self.tmp / "env" / "bin" / "uv"
        found.parent.mkdir(parents=True)
        found.write_text("", encoding="utf-8")
        package = types.SimpleNamespace(__file__=str(stored / "uv" / "__init__.py"), find_uv_bin=lambda: str(found))
        with mock.patch.dict(sys.modules, {"uv": package}):
            self.assertEqual(CARRIED_UV(), str(found), "no uv beside the package: the one uv finds")
            beside.parent.mkdir(parents=True)
            beside.write_text("", encoding="utf-8")
            self.assertEqual(CARRIED_UV(), str(beside), "a stored release's own")
        with mock.patch.dict(sys.modules, {"uv": None}):
            self.assertIsNone(CARRIED_UV(), "no uv package: none")

    def test_the_kernel_s_environments_are_made_with_the_same_uv_where_the_person_has_none(self) -> None:
        """``base.find_uv``: the person's uv on PATH, else the one this release carries, never an environment's own
        older one first."""
        from cad_server._internal import base

        stored = self.tmp / "store" / "0.2.0-cp314"
        beside = stored / "bin" / ("uv.exe" if os.name == "nt" else "uv")
        beside.parent.mkdir(parents=True)
        (stored / "uv").mkdir()
        beside.write_text("", encoding="utf-8")
        older = self.tmp / "env" / "bin" / "uv"
        package = types.SimpleNamespace(__file__=str(stored / "uv" / "__init__.py"), find_uv_bin=lambda: str(older))
        carried = mock.patch.object(auto_update, "carried_uv", CARRIED_UV)  # the real one: ``Case`` stands in for it
        with carried, mock.patch.dict(sys.modules, {"uv": package}), mock.patch.object(shutil, "which", return_value=None):
            self.assertEqual(base.find_uv(), str(beside))
        with carried, mock.patch.dict(sys.modules, {"uv": package}), \
                mock.patch.object(shutil, "which", return_value="/on/path/uv"):
            self.assertEqual(base.find_uv(), "/on/path/uv", "the person's first")
        with carried, mock.patch.dict(sys.modules, {"uv": None}), mock.patch.object(shutil, "which", return_value=None), \
                self.assertRaises(base.Refused):
            base.find_uv()


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

    def test_a_cad_pipx_installed_is_a_global_install_and_updates_as_uv_s_does(self) -> None:
        found = auto_update.global_install()
        self.assertEqual((found.installer, found.prefix), ("pipx", self.env))
        self.assertEqual(os.path.normcase(found.uv), os.path.normcase(str(self.uv)), "built with uv all the same")
        told = json.loads(auto_update.helper_command("0.2.0", now=1.0, version="0.1.0", record="r", install=found)[-1])
        self.assertEqual((told["cad"], told["requirement"], told["installer"]),
                         (str(auto_update.tool_command(self.env)), "cad==0.2.0", "pipx"))
        with self.feed("0.2.0"):
            self.assertEqual(auto_update.due(), auto_update.Due("0.2.0", "0.2.0"),
                             "automatic updates on by default, as for uv's")
        self.assertEqual(self.cli(), (0, "update auto: on\n", ""))
        self.assertEqual(self.cli("off"), (0, "update auto: off\n", ""))
        self.assertEqual(self.cli("on"), (0, "update auto: on\n", ""), "on is a global install's to turn on")
        (self.env / "uv-receipt.toml").write_text(RECEIPT, encoding="utf-8")
        self.assertEqual(auto_update.global_install().installer, "uv", "uv's asked first")

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
        self.assertEqual((line["name"], os.path.normcase(line["detail"])), ("uv", os.path.normcase(str(self.uv))))
        self.assertEqual(doctor._update()[1], f"update auto on, plugin update auto off; a global install by pipx "
                                              f"({self.env})")
        with mock.patch.object(auto_update, "find_uv", return_value=None):
            self.assertEqual(doctor._installer()["detail"], "not found")


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
                    mock.patch.object(auto_update.subprocess, "Popen") as popen:
                for name in (auto_update.RECORD, auto_update.TRIED):
                    (self.state / name).unlink(missing_ok=True)
                self.assertTrue(auto_update.trigger(None, wanted="9.0.0"))
                told = json.loads(popen.call_args.args[0][-1])
                self.assertEqual((told["requirement"], told["target"]), (upgrade, None))
                self.assertNotIn("major", told, "cad's own update never crosses a major")
        with mock.patch.object(cad_server, "__version__", "0.1.0-dev.1"), \
                mock.patch.object(auto_update.subprocess, "Popen") as popen:
            (self.state / auto_update.RECORD).unlink(missing_ok=True)
            self.assertFalse(auto_update.trigger("0.2.0"), "no release to bound it by: none begins")
        popen.assert_not_called()

    def test_the_feed_is_read_only_where_asked_and_a_failed_release_waits_its_hour(self) -> None:
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
            self.assertIsNone(auto_update.due(now=now + auto_update.LOST_SECONDS),
                              "its helper silent: lost, and the release waits the hour after its first try")
            self.assertEqual(auto_update.due(now=now + auto_update.HOUR), self.Due("0.2.0", "0.2.0"))
            auto_update._keep(record, {**auto_update.last(), "outcome": "failed"})
            self.assertIsNone(auto_update.due(now=now), "not by the server the failed update started")
            self.assertEqual(auto_update.due(now=now + auto_update.HOUR), self.Due("0.2.0", "0.2.0"), "an hour on")
            self.assertFalse(auto_update.trigger("0.2.0"), "a trigger asks the schedule again in the step that begins")
        with self.feed("0.2.1"):
            self.assertEqual(auto_update.due(now=now), self.Due("0.2.1", "0.2.1"), "a newer release starts afresh")

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
    def test_a_tries_that_is_no_integer_counts_the_record_as_one_try_and_never_stops_an_update(self) -> None:
        """A record whose ``tries`` is null, a string, a float or a bool: never a check that raises (which would stop
        every update for good, only a claim replacing the record); the attempt it keeps is one try, and the next claim
        writes 2."""
        for tries in (None, "2", 1.0, True):
            with self.subTest(tries=tries):
                (self.state / auto_update.TRIED).unlink(missing_ok=True)
                auto_update._keep(self.state / auto_update.RECORD, {
                    "release": "0.2.0", "wanted": "0.2.0", "from": "0.1.0", "at": 5.0, "tries": tries,
                    "outcome": "failed", "ended": 6.0, "reported": True})
                self.assertEqual(auto_update.tries(10_000.0)["tried"]["0.2.0"]["tries"], 1)
                with self.feed("0.2.0", {"0": "0.2.0"}):
                    self.assertEqual(auto_update.due(now=10_000.0), auto_update.Due("0.2.0", "0.2.0"))
                said, kept = auto_update._claim(release="0.2.0", wanted="0.2.0", version="0.1.0", installer="uv",
                                                automatic=True)
                self.assertEqual((said, kept["tries"], auto_update.last()["tries"]), (auto_update.BEGUN, 2, 2))

    def test_tries_that_no_release_wrote_are_read_as_none_and_never_raise(self) -> None:
        self.state.mkdir(parents=True, exist_ok=True)
        for kept in ("garbage", "[]", json.dumps({"tried": [], "recent": {}, "seen": True}),
                     json.dumps({"tried": {"0.2.0": {"tries": "x", "at": "y", "first": None, "cause": 5}, "1": 7},
                                 "recent": ["z", None, 5.0, True]})):
            with self.subTest(kept=kept):
                (self.state / auto_update.TRIED).write_text(kept, encoding="utf-8")
                found = auto_update.tries(10.0)
                self.assertEqual(set(found), {"tried", "recent", "seen"})
                self.assertEqual(found["recent"], [5.0] if "z" in kept else [])
                self.assertIsNone(auto_update.next_try("0.2.0", found, 10.0), "nothing it can read holds one back")
                with self.feed("0.2.0", {"0": "0.2.0"}):
                    self.assertEqual(auto_update.due(now=10.0), auto_update.Due("0.2.0", "0.2.0"))


class ScheduleTest(Case):
    """The automatic update's schedule, on a clock of the test's own (no waiting): each release tried again after
    1, 2, 4, 8, 16, then 24 hours, never given up on; at most ``DAILY`` attempts in a day, of every release; kept by
    release, so two servers of two releases never set each other's count back; a typed update spending no automatic
    try. Each attempt's helper stands in as one that ended at once, failed."""

    START = 1_000_000.0

    def setUp(self) -> None:
        super().setUp()
        self.clock = [self.START]
        self.counted: list[dict] = []
        for patch in (mock.patch.object(auto_update.time, "time", lambda: self.clock[0]),
                      mock.patch.object(auto_update.subprocess, "Popen"),
                      mock.patch.object(sys, "_base_executable", str(self.tmp / "python3"), create=True),
                      mock.patch("cad_server.analytics.update", side_effect=lambda **kw: self.counted.append(kw))):
            patch.start()
            self.addCleanup(patch.stop)

    def ended(self) -> None:
        """The attempt just begun, ended by its helper at once: failed, the network down."""
        auto_update._keep(self.state / auto_update.RECORD, {**auto_update.last(), "outcome": "failed",
                                                            "cause": "network", "ended": self.clock[0]})

    def tendings(self, hours: float, servers: tuple[str, ...] = ("0.1.0",), every: float = 600.0) -> list[tuple]:
        """``hours`` of each server tending itself in turn every ``every`` seconds, nothing in flight: ``(the server's
        release, the release its attempt was for, the hour it began since START, the try it was)`` for each begun."""
        begun = []
        until = self.clock[0] + hours * auto_update.HOUR
        while self.clock[0] < until:
            for version in servers:
                with mock.patch.object(cad_server, "__version__", version):
                    if auto_update.tend():
                        found = auto_update.last()
                        begun.append((version, found["wanted"], (found["at"] - self.START) / auto_update.HOUR,
                                      found["tries"]))
                        self.ended()
            self.clock[0] += every
        return begun

    def test_a_release_that_keeps_failing_waits_twice_as_long_each_time_up_to_a_day_and_is_never_given_up_on(self):
        with self.feed("0.2.0", {"0": "0.2.0"}):
            begun = self.tendings(100)
        # 1, 2, 4 and 8 hours after the tries before; the fifth waits for the day's first to be a day old (4 a day),
        # then 16 hours, then a day each.
        self.assertEqual([(hour, tries) for _v, _w, hour, tries in begun],
                         [(0, 1), (1, 2), (3, 3), (7, 4), (24, 5), (40, 6), (64, 7), (88, 8)])
        entry = auto_update.tries()["tried"]["0.2.0"]
        self.assertEqual((entry["tries"], entry["first"], entry["cause"]), (8, self.START, "network"))
        self.assertEqual(len(self.counted), 7, "each attempt before counted once, as the next began")
        with self.feed("0.2.1", {"0": "0.2.1"}):
            again = self.tendings(1)
        self.assertEqual([(wanted, tries) for _v, wanted, _h, tries in again], [("0.2.1", 1)],
                         "a newer release starts at none of its own")
        self.assertEqual(auto_update.tries()["tried"]["0.2.0"]["tries"], 8, "and leaves the one before as it was")

    def test_the_wait_before_each_try_and_the_day_s_limit(self) -> None:
        book = {"tried": {"0.2.0": {"tries": 3, "at": 100.0}}, "recent": [], "seen": None}
        self.assertEqual(auto_update.next_try("0.2.0", book, 100.0 + 60), 100.0 + 4 * auto_update.HOUR)
        self.assertIsNone(auto_update.next_try("0.2.0", book, 100.0 + 4 * auto_update.HOUR))
        self.assertIsNone(auto_update.next_try("0.2.0", book, 50.0), "a clock set back counts as long ago")
        self.assertIsNone(auto_update.next_try("0.3.0", book, 100.0), "another release: none of its own yet")
        book["tried"]["0.2.0"]["tries"] = 10 ** 9  # no try count makes the wait more than a day, nor slow to work out
        self.assertEqual(auto_update.next_try("0.2.0", book, 100.0), 100.0 + auto_update.DAY)
        book = {"tried": {}, "recent": [10.0, 20.0, 30.0, 40.0], "seen": None}
        self.assertEqual(auto_update.next_try("0.3.0", book, 50.0), 10.0 + auto_update.DAY,
                         "four begun in the day: the next once the first of them is a day old")

    def test_two_servers_of_two_releases_taking_turns_never_set_each_other_s_count_back(self) -> None:
        """Two servers on one state folder, of two releases of two majors (one left running in an engine folder no
        newer client reaches), each wanting its own major's newest, which fails every time: kept in the last attempt
        alone, each attempt of one release set the other's count back, and each server began one at every tending,
        taking turns, with no end. Kept by release: each waits its own schedule, and the day's limit is theirs
        together."""
        with self.feed("1.2.0", {"0": "0.3.0", "1": "1.2.0"}):
            begun = self.tendings(96, servers=("0.1.0", "1.0.0"))
        for version, wanted in (("0.1.0", "0.3.0"), ("1.0.0", "1.2.0")):
            mine = [(hour, tries) for v, w, hour, tries in begun if v == version]
            self.assertTrue(all(w == wanted for v, w, _h, _t in begun if v == version))
            self.assertEqual([tries for _hour, tries in mine], list(range(1, len(mine) + 1)), "never set back")
            for (before, tries), (after, _next) in zip(mine, mine[1:]):
                self.assertGreaterEqual(after - before, min(2 ** (tries - 1), 24), (version, mine))
            self.assertGreaterEqual(len(mine), 6, "never given up on, nor starved by the other")
            self.assertEqual(auto_update.tries()["tried"][wanted]["tries"], len(mine))
        hours = [hour for _v, _w, hour, _t in begun]
        for hour in hours:
            self.assertLessEqual(len([other for other in hours if hour - 24 < other <= hour]), auto_update.DAILY,
                                 "at most four a day between them")

    def test_a_typed_update_spends_no_automatic_try_and_counts_among_the_day_s_attempts(self) -> None:
        with self.feed("0.2.0", {"0": "0.2.0"}):
            self.assertEqual(self.tendings(0.1), [("0.1.0", "0.2.0", 0.0, 1)])
            for typed in range(4):
                self.clock[0] += auto_update.HOUR
                found = auto_update.begin("0.2.0")
                self.assertEqual((found["asked"], found["tries"]), (True, 2), "the try it would be, none spent")
                self.ended()
            self.assertEqual(auto_update.tries()["tried"]["0.2.0"]["tries"], 1)
            self.assertEqual(len(auto_update.tries()["recent"]), 5)
            self.assertEqual(self.tendings(5), [], "five begun in the day: no automatic one")
            self.assertIsNotNone(auto_update.begin("0.2.0"), "a typed one always begins")
            self.ended()
            begun = self.tendings(24)
        second_typed = 600 + 2 * auto_update.HOUR  # the first tending moved the clock on ten minutes
        self.assertEqual(begun[0][2:], ((second_typed + auto_update.DAY) / auto_update.HOUR, 2),
                         "its second try once fewer than four began in the day")


class BeatTest(Case):
    """An attempt is underway while its helper beats (``beat``, every ``BEAT_SECONDS``), however long it runs, and
    lost once it has not for ``LOST_SECONDS``; a record a release before the beat kept is underway for its hour."""

    def test_underway_while_it_beats_and_lost_once_it_has_not_for_twenty_minutes(self) -> None:
        at = 1_000_000.0
        base = {"release": "0.2.0", "wanted": "0.2.0", "from": "0.1.0", "at": at, "tries": 1, "outcome": "underway"}
        for record, now, believed in (
                ({**base, "beat": at + 2 * 3600}, at + 2 * 3600 + 60, True),  # two hours in, still beating
                ({**base, "beat": at}, at + auto_update.LOST_SECONDS - 1, True),
                ({**base, "beat": at}, at + auto_update.LOST_SECONDS, False),
                ({**base, "beat": at + 10}, at, False),  # a clock set back counts as long ago
                ({**base, "beat": at + auto_update.LONGEST_SECONDS}, at + auto_update.LONGEST_SECONDS + 1, False),
                ({**base, "beat": "soon"}, at + 60, True),  # no beat it can read: a record of a release before it
                (base, at + auto_update.RETRY_SECONDS - 1, True),
                (base, at + auto_update.RETRY_SECONDS, False)):
            with self.subTest(record=record, now=now - at):
                auto_update._keep(self.state / auto_update.RECORD, record)
                self.assertEqual(auto_update.underway(now) is not None, believed)
                self.assertEqual(auto_update.cause(record, now), None if believed else "lost")
        auto_update._keep(self.state / auto_update.RECORD, {**base, "beat": time.time() - auto_update.LOST_SECONDS})
        self.assertEqual(auto_update.event(auto_update.last())["outcome"], "lost", "counted lost once silent")

    def test_the_helper_beats_while_it_runs_and_never_over_another_attempt_s_record(self) -> None:
        record = self.tmp / "auto-update.json"
        kept = {"release": "0.2.0", "at": 5.0, "beat": 5.0, "outcome": "underway"}
        record.write_text(json.dumps(kept), encoding="utf-8")
        told = {"record": str(record), "at": 5.0}
        beat = helper.Beat(told, every=0.01)
        until = time.monotonic() + 30
        while json.loads(record.read_text(encoding="utf-8")).get("beat") == 5.0 and time.monotonic() < until:
            time.sleep(0.01)
        beat.stop()
        self.assertFalse(beat.thread.is_alive(), "no beat after stop: the outcome is the record's last word")
        found = json.loads(record.read_text(encoding="utf-8"))
        self.assertGreater(found["beat"], 5.0)
        self.assertEqual({**found, "beat": 5.0}, kept, "the beat alone changed")
        beat = helper.Beat(told, every=3600)  # beats by hand alone
        self.addCleanup(beat.stop)
        for other in ({**kept, "at": 6.0}, {**kept, "outcome": "failed"}):  # another attempt's, or this one ended
            record.write_text(json.dumps(other), encoding="utf-8")
            beat.mark()
            self.assertEqual(json.loads(record.read_text(encoding="utf-8")), other, "left as it was")
        record.write_text(json.dumps(kept), encoding="utf-8")
        beat.mark()
        self.assertGreater(json.loads(record.read_text(encoding="utf-8"))["beat"], 5.0)
        record.write_text(json.dumps({**kept, "at": 6.0}), encoding="utf-8")
        with mock.patch.object(helper, "update", return_value={"outcome": "failed", "at": 5.0}):
            helper.main({**told, "log": None})
        self.assertEqual(json.loads(record.read_text(encoding="utf-8"))["at"], 6.0,
                         "an attempt begun since, the first taken for lost: its record is the newer one's")
        record.write_text(json.dumps(kept), encoding="utf-8")
        with mock.patch.object(helper, "update", return_value={"outcome": "failed", "at": 5.0}):
            helper.main({**told, "log": None})
        self.assertEqual(json.loads(record.read_text(encoding="utf-8")), {"outcome": "failed", "at": 5.0})

    def test_the_trigger_keeps_the_first_beat_and_a_lost_attempt_is_counted_once_by_the_next(self) -> None:
        counted: list[dict] = []
        with self.feed("0.2.0"), mock.patch.object(auto_update.subprocess, "Popen"), \
                mock.patch.object(sys, "_base_executable", str(self.tmp / "python3"), create=True), \
                mock.patch("cad_server.analytics.update", side_effect=lambda **kw: counted.append(kw)):
            self.assertTrue(auto_update.trigger("0.2.0"))
            first = auto_update.last()
            self.assertEqual(first["beat"], first["at"])
            auto_update._keep(self.state / auto_update.RECORD, {**first, "beat": first["at"] - auto_update.LOST_SECONDS,
                                                                "at": first["at"] - auto_update.HOUR})
            self.assertTrue(auto_update.begin("0.2.0") is not None)
        self.assertEqual([(kw["outcome"], kw["cause"]) for kw in counted], [("lost", "lost")])


class StaleServerTest(Case):
    """A server older than what its own environment runs, which is the release wanted already (another update, or
    one by hand, switched it after the server started): no attempt, no try spent."""

    def test_no_update_and_no_try_where_the_environment_runs_the_release_wanted_or_newer(self) -> None:
        for held, latest, lines, due in (("0.2.0", "0.2.0", {"0": "0.2.0"}, None),
                                         ("0.3.0", "0.2.0", {"0": "0.2.0"}, None),
                                         ("1.0.2", "1.0.2", {"0": "0.2.0", "1": "1.0.2"}, None),  # a higher major, by hand
                                         ("0.1.5", "0.2.0", {"0": "0.2.0"}, ("0.2.0", "0.2.0")),  # newer, not wanted
                                         ("0.1.0", "0.2.0", {"0": "0.2.0"}, ("0.2.0", "0.2.0")),  # its own
                                         (None, "0.2.0", {"0": "0.2.0"}, ("0.2.0", "0.2.0"))):  # none it can read
            with self.subTest(held=held, latest=latest), self.feed(latest, lines), \
                    mock.patch.object(store, "active", return_value=held):
                self.assertEqual(auto_update.due(), None if due is None else auto_update.Due(*due))
                self.assertEqual(auto_update.stale("0.2.0"), due is None)
        self.assertFalse((self.state / auto_update.RECORD).exists(), "nothing begun")
        self.assertFalse((self.state / auto_update.TRIED).exists(), "no try spent")


class OlderRecordTest(Case):
    """Law 14, tier 3, both ways: an older release reads this one's record as it reads its own (``release``, ``at``,
    ``wanted``, ``tries``, ``outcome``: its rule stops trying a release once ``tries`` reaches its limit, and an attempt
    is underway for its hour); this release reads an older one's, which keeps no tries beside it and no beat."""

    def test_an_older_release_s_record_is_counted_once_and_read_by_its_own_rule(self) -> None:
        now = 1_000_000.0
        older = {"release": "0.2.0", "wanted": "0.2.0", "from": "0.1.0", "at": now, "tries": 2,
                 "outcome": "failed", "installer": "uv", "asked": False, "cause": "network"}
        auto_update._keep(self.state / auto_update.RECORD, older)
        book = auto_update.tries(now + 60)
        self.assertEqual((book["tried"]["0.2.0"], book["recent"]),
                         ({"tries": 2, "first": now, "at": now, "cause": "network"}, [now]))
        self.assertEqual(auto_update.next_try("0.2.0", book, now + 60), now + 2 * auto_update.HOUR,
                         "its two tries count: the third waits two hours")
        auto_update._keep(self.state / auto_update.RECORD, {**older, "outcome": "underway", "at": now})
        self.assertIsNotNone(auto_update.underway(now + auto_update.RETRY_SECONDS - 1), "no beat: its hour")
        self.assertIsNone(auto_update.underway(now + auto_update.RETRY_SECONDS))
        auto_update._keep(self.state / auto_update.RECORD, {**older, "asked": True, "tries": 3})
        self.assertEqual(auto_update.tries(now + 60)["tried"], {}, "a typed one of its own: no automatic try")

    def test_an_older_release_s_attempt_between_this_one_s_is_counted_and_never_sets_the_count_back(self) -> None:
        """This release keeps its tries apart, which an older release never writes: its attempt in between (its
        record whole, with its own count: the record's ``tries``, one more than this one kept) is counted from the
        record, once, and every other release's count stays."""
        with self.feed("0.2.0"), mock.patch.object(auto_update.subprocess, "Popen"), \
                mock.patch.object(sys, "_base_executable", str(self.tmp / "python3"), create=True), \
                mock.patch("cad_server.analytics.update"):
            self.assertTrue(auto_update.trigger("0.2.0"))
            mine = auto_update.last()
            self.assertLessEqual({"release", "wanted", "from", "at", "tries", "outcome"}, set(mine))
            self.assertEqual((type(mine["at"]), mine["tries"], mine["outcome"]), (float, 1, "underway"))
            book = json.loads((self.state / auto_update.TRIED).read_text(encoding="utf-8"))
            book["tried"]["1.0.0"] = {"tries": 5, "first": 1.0, "at": 2.0}
            auto_update._keep(self.state / auto_update.TRIED, book)
            # The older release's attempt: its record whole, in place of this one's.
            theirs = {"release": "0.2.0", "wanted": "0.2.0", "from": "0.1.0", "at": mine["at"] + 7200.0,
                      "tries": mine["tries"] + 1, "outcome": "failed"}
            auto_update._keep(self.state / auto_update.RECORD, theirs)
            for _ in range(2):
                found = auto_update.tries(theirs["at"] + 60)
                self.assertEqual((found["tried"]["0.2.0"]["tries"], found["tried"]["0.2.0"]["first"],
                                  found["tried"]["1.0.0"]["tries"], len(found["recent"])),
                                 (2, mine["at"], 5, 2), "counted once, whoever reads it")


class CauseOfARecordTest(Case):
    def test_a_record_s_cause_is_its_own_and_an_older_record_s_is_read_as_it_was_kept(self) -> None:
        """``cause`` is read where the record keeps one of the words; a record a release before it kept (no
        ``cause``) reads as it did -- its outcome and detail, and ``kept`` where the detail says the release that ran
        stayed --; an attempt still underway past its hour is ``lost``. Older releases read ``outcome`` as ever. Its
        event says the cause (``already`` where the environment held the release already, ``none`` where the record
        names none), and counts an attempt underway past its hour ``lost``."""
        base = {"release": "0.2.0", "wanted": "0.2.0", "from": "0.1.0", "at": 1000.0, "tries": 1, "ended": 1010.0}
        for record, cause, sent in (
                ({**base, "outcome": "failed", "detail": "uv said no", "cause": "network"}, "network", ("failed", "network")),
                ({**base, "outcome": "failed", "detail": "uv said no"}, None, ("failed", "none")),
                ({**base, "outcome": "failed", "cause": "a word of a later release"}, None, ("failed", "none")),
                ({**base, "outcome": "current", "detail": "cad 0.1.0 is the newest release it may take"}, None,
                 ("current", "none")),
                ({**base, "outcome": "failed", "cause": "kept"}, None, ("failed", "none")),  # a word no longer kept
                ({**base, "outcome": "current", "detail": "cad 0.2.0 is installed"}, None, ("current", "already")),
                ({**base, "outcome": "current", "detail": "uv said"}, None, ("current", "none")),
                ({**base, "outcome": "installed"}, None, ("installed", None)),
                ({**base, "outcome": "underway"}, None, ("lost", "lost")),  # its hour long gone by the clock
                ({**base, "outcome": "underway", "at": 1000.0 - auto_update.RETRY_SECONDS}, "lost", ("lost", "lost")),
                ({**base, "outcome": "underway", "cause": "helper_crash"}, "helper_crash", ("lost", "helper_crash")),
                ({**base, "outcome": "underway", "at": time.time()}, None, None)):  # underway: nothing to count yet
            with self.subTest(record=record):
                auto_update._keep(self.state / auto_update.RECORD, record)
                found = auto_update.last()
                self.assertEqual(found, record, "read whole, a field it does not know included")
                self.assertEqual(auto_update.cause(found, now=1020.0 if record["at"] < 2000 else record["at"]), cause)
                counted = auto_update.event(found)
                self.assertEqual(None if counted is None else (counted["outcome"], counted["cause"]), sent)


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
        mock.patch.object(auto_update, "carried_uv", return_value=None), \\
        mock.patch("cad_server._internal.store.switches", return_value=True), \\
        mock.patch.object(sys, "_base_executable", str(tool.parent / "python3"), create=True), \\
        mock.patch.object(auto_update.subprocess, "Popen") as popen:
    while not go.exists():
        time.sleep(0.001)
    if automatic:
        began = auto_update.trigger("0.2.0", wanted="0.2.0") is not None
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
    def test_a_tending_begins_what_is_due_to_get_its_release_ready_and_never_the_switch(self) -> None:
        """``tend``: an update due begun at once, to get its release ready alone, at every tending (it is told nothing
        of what is in flight or of the last command: ``Daemon.tend``); never the switch to a release that is ready
        (``restart``), however long it has been ready. What it began, or None."""
        made = {"release": "0.2.0", "switch": False}
        with mock.patch.object(auto_update, "due", return_value=auto_update.Due("0.2.0", "0.2.0")), \
                mock.patch.object(auto_update, "trigger", return_value=made) as trigger, \
                mock.patch.object(auto_update, "restart") as restart:
            self.assertIs(auto_update.tend(), made)
            self.assertIs(auto_update.tend(), made)
            with mock.patch.object(auto_update, "due", return_value=None):
                self.assertIsNone(auto_update.tend(), "nothing due: nothing, and never the switch")
        restart.assert_not_called()
        self.assertEqual(trigger.call_args_list, [mock.call("0.2.0", wanted="0.2.0", switch=False)] * 2,
                         "each an automatic update that gets its release ready alone")

    def test_the_entry_point_runs_the_daemon_and_nothing_of_the_update_before_it(self) -> None:
        """What the start hands to the update, where a release is ready, is the daemon's own (``daemon.main``,
        ``ReadyTest``): the module the starter runs imports nothing of it."""
        from cad_server._internal import engine_daemon

        source = Path(engine_daemon.__file__).read_text(encoding="utf-8")
        self.assertNotIn("auto_update", source.split('"""', 2)[2], "nothing of the update before the daemon runs")
        self.assertFalse(hasattr(client, "UPDATING"))


class HelperCommandTest(Case):
    def test_its_command_line(self) -> None:
        found = auto_update.Global("uv", self.tool, "/u/uv")
        line = auto_update.helper_command("0.2.0", now=5.0, version="0.1.0", record="/s/auto-update.json", install=found,
                                          log="/s/auto-update.log", python="/env/python")
        # The environment's own interpreter, which takes the release that runs by the pointer; the worker as a module of
        # it; its one argument short (Windows starts no process whose command line passes 32,767 characters).
        self.assertEqual(line[:4], ["/env/python", "-P", "-m", "cad_server._internal.auto_update_helper"])
        self.assertLess(len(subprocess.list2cmdline(line)), 4096)
        self.assertEqual(json.loads(line[4]), {
            "record": "/s/auto-update.json", "log": "/s/auto-update.log", "from": "0.1.0", "at": 5.0, "tries": 1,
            "wanted": "0.2.0", "asked": False, "start": True, "target": "0.2.0",
            "requirement": "cad==0.2.0", "cad": str(auto_update.tool_command(self.tool)), "uv": "/u/uv",
            "installer": "uv"})
        self.assertEqual(auto_update.tool_command(self.tool, windows=True), self.tool / "Scripts/cad.exe")
        found = auto_update.Global("pipx", self.tool, "/u/uv")
        told = json.loads(auto_update.helper_command(None, now=5.0, version="0.1.0", record="r", install=found,
                                                     asked=True)[-1])
        self.assertEqual((told["requirement"], told["wanted"], told["installer"]),
                         ("cad>=0.1.0,<1", "latest", "pipx"), "a typed update with no release named: this major's")
        self.assertEqual(auto_update.helper_command(None, now=5.0, version="0.1.0", record="r", install=found)[0],
                         sys.executable, "this environment's interpreter by default")

    def triggered(self, **options) -> tuple[list[str], dict]:
        """A trigger with nothing underway (the record of one before it, underway, is taken away first)."""
        (self.state / auto_update.RECORD).unlink(missing_ok=True)
        with mock.patch.dict(os.environ, {"PYTHONPATH": "/src", "VIRTUAL_ENV": str(self.tool), "KEEP": "1"}), \
                mock.patch.object(auto_update.subprocess, "Popen") as popen:
            self.assertTrue(auto_update.trigger("0.2.0", **options))
        (line,), env = popen.call_args
        self.assertEqual(line[0], sys.executable)
        return line, env

    def test_the_trigger_starts_it_detached_with_nothing_that_points_elsewhere_and_keeps_the_attempt(self) -> None:
        line, options = self.triggered()
        told = json.loads(line[-1])
        self.assertEqual(os.path.normcase(told["uv"]), os.path.normcase(self.uv))
        self.assertEqual(told["log"], str(self.state / auto_update.LOG), "the log beside the record")
        self.assertNotIn("PYTHONPATH", options["env"], "the worker takes the release that runs by the pointer")
        self.assertNotIn("VIRTUAL_ENV", options["env"])
        self.assertEqual((options["env"]["KEEP"], options["env"]["CAD_STATE_DIR"]), ("1", str(self.state)),
                         "the state folder, where the pointer is, the same for everything it runs")
        self.assertEqual(options["start_new_session" if os.name != "nt" else "creationflags"],
                         True if os.name != "nt" else 0x08000000 | 0x00000200)
        self.assertEqual((auto_update.last()["outcome"], auto_update.last()["phase"]), ("underway", "building"))
        (self.state / auto_update.RECORD).unlink()
        with mock.patch.object(auto_update.subprocess, "Popen", side_effect=OSError("no such file")):
            self.assertFalse(auto_update.trigger("0.2.1"))
        self.assertEqual((auto_update.last()["outcome"], auto_update.last()["detail"], auto_update.last()["cause"]),
                         ("failed", "the update's worker could not start: OSError: no such file", "helper_start"),
                         "a worker that never started holds nothing underway")
        self.assertIsNone(auto_update.underway())
        (self.state / auto_update.RECORD).unlink()
        for word, patch in (("no_switch", mock.patch.object(store, "switches", return_value=False)),
                            ("no_installer", mock.patch.object(auto_update, "find_uv", return_value=None))):
            with self.subTest(word=word), patch, mock.patch.object(auto_update.subprocess, "Popen") as popen:
                self.assertEqual(auto_update.blocked(auto_update.global_install()), word)
                self.assertFalse(auto_update.trigger("0.2.1"), "none begins")
                popen.assert_not_called()
                self.assertIsNone(auto_update.last(), "and nothing kept as underway")

    def test_the_worker_and_the_record_are_told_the_installer_and_whether_it_was_typed_and_never_an_install(self):
        auto_update.change_plugin(True)  # the switch on: the worker runs no install command whatever it says
        for automatic in (True, False):
            with self.subTest(automatic=automatic):
                told = json.loads(self.triggered(automatic=automatic)[0][-1])
                self.assertEqual((told["installer"], told["asked"]), ("uv", not automatic))
                kept = auto_update.last()
                self.assertEqual((kept["installer"], kept["asked"], kept["wanted"]), ("uv", not automatic, "0.2.0"))
        (self.state / auto_update.RECORD).unlink()  # none underway, which `cad update` would join
        with mock.patch.object(auto_update.subprocess, "Popen") as popen:
            found = auto_update.begin("0.2.1")
        told = json.loads(popen.call_args.args[0][-1])
        self.assertEqual((found["release"], found["asked"], told["requirement"], told["start"]),
                         ("0.2.1", True, "cad==0.2.1", True))

    def test_the_worker_is_told_whether_a_server_is_wanted_after_it(self) -> None:
        self.assertTrue(json.loads(self.triggered()[0][-1])["start"], "a server ran: it starts again")
        self.assertFalse(json.loads(self.triggered(automatic=False, start=False)[0][-1])["start"])


class WorkerTest(unittest.TestCase):
    """What the worker does, in order, and what it keeps (``auto_update_helper.update``): a stand-in ``run`` for uv
    and the environment's ``cad`` command, and the store's functions standing in for its folders (the store is
    ``test_store.py``'s). The environment runs ``active`` (its pointer's release, else its own, 0.1.0); a server of
    ``serving`` answers, or none."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.told = {"record": str(self.tmp / "auto-update.json"), "log": str(self.tmp / "auto-update.log"),
                     "from": "0.1.0", "at": 1.0, "tries": 1, "wanted": "0.2.0", "asked": False,
                     "start": True, "target": "0.2.0", "requirement": "cad==0.2.0", "cad": "cad", "uv": "uv",
                     "installer": "uv"}
        self.pointer: dict | None = None  # the pointer as kept
        self.serving: str | None = "0.1.0"  # the release of the server that answers
        self.elsewhere = False  # that server runs from another environment
        self.stored: dict[str, Path] = {}
        self.unsound: set[Path] = set()  # stored releases that no longer run
        self.build = (0, "Installed 40 packages in 1.2s\n")  # uv's exit status and words
        self.verifies = "0.2.0"  # the release the build says it is, or None: it does not run
        self.starts = {"0.1.0": True, "0.2.0": True}  # whether a release's server starts
        self.gone = True  # whether a server stopped goes within the bound
        self.ran: list[list[str]] = []
        self.calls: list[tuple] = []
        self.phases: list[str] = []
        for name in ("active", "folder", "marker", "sound", "build", "verify", "publish", "remove", "pointer", "pointed",
                     "point", "restore", "clean"):
            patch = mock.patch.object(store, name, side_effect=getattr(self, f"_{name}"))
            patch.start()
            self.addCleanup(patch.stop)
        for patch in (mock.patch.object(helper, "answering", side_effect=self._answering),
                      mock.patch.object(client, "sweep", side_effect=self._sweep),
                      mock.patch.object(helper, "UV_SYSTEM", ()), mock.patch.dict(os.environ)):
            patch.start()
            self.addCleanup(patch.stop)
        for name in [name for name in os.environ if name.startswith(("UV_", "SSL_CERT_"))]:  # this computer's
            del os.environ[name]
        os.environ.update(XDG_CONFIG_HOME=str(self.tmp / "config"), XDG_CONFIG_DIRS=str(self.tmp / "config"),
                          HOME=str(self.tmp))

    # --- the stand-ins -------------------------------------------------------------------------------------------

    def _active(self, prefix=None):
        return self.pointer["release"] if self.pointer else "0.1.0"

    def _folder(self, release):
        return self.tmp / "store" / f"{release}-cp314"

    def _marker(self, path):
        return next(({"release": release} for release, kept in self.stored.items() if kept == Path(path)), None)

    def _sound(self, path, *, run, timeout=180.0):
        if self._marker(path) is None:
            return False
        code, _said = run([sys.executable, "-I", "-S", "-c", "selftest", str(path)], timeout)
        return code == 0

    def _build(self, requirement, *, uv, run, timeout=900.0):
        code, said = run([uv, "pip", "install", "--target", str(self.tmp / "store" / ".building-1"), requirement],
                         timeout)
        if code != 0:
            raise store.Failed("build", code, said)
        return self.tmp / "store" / ".building-1"

    def _verify(self, staged, *, run, timeout=180.0):
        code, said = run([sys.executable, "-I", "-S", "-c", "selftest", str(staged)], timeout)
        if code != 0:
            raise store.Failed("verify", code, said)
        return self.verifies

    def _publish(self, staged, release, *, run=None):
        self.stored[release] = self._folder(release)
        self.unsound.discard(self.stored[release])
        self.calls.append(("publish", release))
        return self.stored[release]

    def _remove(self, path):
        self.calls.append(("remove", Path(path).name))
        return True

    def _pointer(self, prefix=None):
        return self.pointer

    def _pointed(self, prefix=None):
        return self.pointer

    def _point(self, path, *, prefix=None):
        self.calls.append(("point", Path(path).name))
        self.pointer = {"pointer": 1, "path": str(path), "release": self._marker(path)["release"]}
        return self.pointer

    def _restore(self, kept, *, prefix=None):
        self.calls.append(("restore", kept))
        self.pointer = kept

    def _clean(self, keep=()):
        self.calls.append(("clean", [Path(path).name for path in keep if path]))
        return []

    def _answering(self):
        return None if self.serving is None else (self.serving, "/elsewhere" if self.elsewhere else sys.prefix)

    def _sweep(self, *, stop, seconds=60.0, leave=None):
        """``client.sweep`` as the switch asks it (``auto_update_helper.stop``): the server stopped at once."""
        self.calls.append(("stop", seconds))
        if not self.gone:
            raise ConnectionError("the engine server at door did not exit")
        self.serving = None
        return {"stopped": ["door"], "running": [], "removed": []}

    def the_switch_s_or(self, other):
        """A stand-in for ``client.sweep`` that is ``_sweep`` for the switch's own stop (``STOP_SECONDS``) and
        ``other`` for any other."""
        return lambda **asked: (self._sweep(**asked) if asked.get("seconds") == helper.STOP_SECONDS
                                else other(**asked))

    def cad(self, command, timeout):
        self.ran.append(list(command))
        if command[0] == "uv":
            return self.build
        if command[1:3] == ["-I", "-S"]:
            if Path(command[-1]) in self.unsound:
                return 1, "ImportError: DLL load failed while importing _multiarray_umath"
            return (0, f"cad {self.verifies}\n") if self.verifies else (1, "ModuleNotFoundError: No module named 'ezdxf'")
        release = self._active()
        if command[1:] == ["--version"]:
            return (0, f"cad {release}\n") if self.starts.get(release) else (1, "ModuleNotFoundError: cad_server")
        if command[1:] == ["server", "start"]:
            if not self.starts.get(release):
                return 1, "cad server start: the engine server did not start: it exited with code 1"
            self.serving, self.elsewhere = release, False
            return 0, f"started the cad server (cad {release})\n"
        raise AssertionError(command)

    def update(self, **told):
        return helper.update({**self.told, **told}, run=self.cad, mark=self.phases.append)

    def commands(self) -> list[str]:
        return [" ".join(command[1:3]) if command[0] != "uv" else "uv build" for command in self.ran]

    # --- the tests -------------------------------------------------------------------------------------------------

    def test_built_beside_then_the_server_stopped_at_once_and_the_release_switched_to(self) -> None:
        found = self.update()
        self.assertEqual(self.commands(), ["uv build", "-I -S", "server start"])
        self.assertEqual(self.calls, [("publish", "0.2.0"), ("stop", helper.STOP_SECONDS),
                                      ("point", "0.2.0-cp314"), ("clean", ["0.2.0-cp314"])])
        self.assertEqual(self.phases, ["building", "switching"], "kept as uv builds, then before anything stopped")
        self.assertEqual(found, {"release": "0.2.0", "outcome": "installed", "from": "0.1.0", "at": 1.0, "tries": 1,
                                 "ended": found["ended"], "detail": f"cad 0.2.0 runs from {self._folder('0.2.0')}",
                                 "started": "started the cad server (cad 0.2.0)", "installer": "uv", "wanted": "0.2.0",
                                 "asked": False})
        self.assertEqual(self.ran[0][-1], "cad==0.2.0", "the release asked for, by name")
        log = Path(self.told["log"]).read_text(encoding="utf-8")
        for said in ("cad's update, begun", "cad==0.2.0 built by uv", "$ uv pip install", "exit 0 after",
                     "| Installed 40 packages", "$ cad server start", "stopped: gone",
                     "ended ", ": installed"):
            self.assertIn(said, log)
        # From a stored release: the tidying keeps the one switched to alone (``test_store.SwitchTidyTest``).
        self.ran.clear(), self.calls.clear()
        self.stored["0.2.0"] = self._folder("0.2.0")
        self.pointer = {"path": str(self._folder("0.2.0")), "release": "0.2.0"}
        self.verifies, self.starts["0.2.1"] = "0.2.1", True
        self.assertEqual(self.update(**{"from": "0.2.0", "target": "0.2.1", "requirement": "cad==0.2.1"})["outcome"],
                         "installed")
        self.assertEqual(self.calls[-2:], [("point", "0.2.1-cp314"), ("clean", ["0.2.1-cp314"])])

    def test_a_release_stored_already_is_run_once_and_switched_to_unbuilt(self) -> None:
        self.stored["0.2.0"] = self._folder("0.2.0")
        self.assertEqual(self.update()["outcome"], "installed")
        self.assertEqual(self.commands(), ["-I -S", "server start"], "run once, as a build is, and never built")
        self.assertEqual(self.ran[0][-1], str(self._folder("0.2.0")))

    def test_a_release_stored_already_that_no_longer_runs_is_built_again(self) -> None:
        """Another Python of this version built it, or a file of it is gone: never switched to as it is."""
        self.pointer, self.serving = None, "0.1.0"
        self.stored["0.2.0"] = self._folder("0.2.0")
        self.unsound.add(self._folder("0.2.0"))
        found = self.update()
        self.assertEqual(self.commands(), ["-I -S", "uv build", "-I -S", "server start"])
        self.assertEqual((found["outcome"], self.calls[0]), ("installed", ("publish", "0.2.0")))
        # Where a process still runs the one that does not: the build ends there, in use, and nothing is switched.
        self.pointer, self.serving = None, "0.1.0"
        self.unsound.add(self._folder("0.2.0"))
        self.calls.clear()
        busy = OSError(16, "resource busy: the stored release does not run, and a process still runs it", "store")
        with mock.patch.object(store, "publish", side_effect=busy):
            found = self.update()
        self.assertEqual((found["outcome"], found["cause"], self.pointer, self.serving), ("failed", "in_use", None, "0.1.0"))
        self.assertNotIn("point", [call[0] for call in self.calls])

    def test_nothing_newer_ends_current_and_nothing_stops(self) -> None:
        self.verifies = "0.1.0"
        found = self.update(target=None, requirement="cad>=0.1.0,<1")
        self.assertEqual((found["release"], found["outcome"], found["detail"]),
                         ("0.1.0", "current", "cad 0.1.0 is the newest release it may take"))
        self.assertNotIn("cause", found)
        self.assertEqual(self.calls, [("remove", ".building-1"), ("clean", [])])
        self.assertEqual((self.serving, self.phases), ("0.1.0", ["building"]), "the server left running")
        self.assertEqual(auto_update.event(found)["cause"], "none")

    def test_a_release_it_may_not_end_on_is_never_switched_to(self) -> None:
        for major, built, outcome in ((False, "1.0.0", "failed"), (False, "0.0.9", "failed"), (True, "0.0.9", "failed"),
                                      (True, "1.0.0", "failed")):
            with self.subTest(major=major, built=built):
                self.pointer, self.serving, self.verifies = None, "0.1.0", built
                self.starts[built] = True
                self.calls.clear()
                # ``major``: what a release before this one told its worker for `cad update --major`, read no more.
                found = self.update(target=None, major=major, requirement="cad>=0.1.0" if major else "cad>=0.1.0,<1")
                self.assertEqual(found["outcome"], outcome)
                if outcome == "failed":
                    self.assertEqual((found["detail"], found["cause"]), (f"it built cad {built}, which it may not end on",
                                                                         "unknown"))
                    self.assertEqual(auto_update.event(found)["reason"], "older")
                    self.assertNotIn("point", [call[0] for call in self.calls])

    def test_a_build_that_fails_changes_nothing_and_says_why_from_uv_s_words(self) -> None:
        for code, said, cause in (
                (2, "error: Failed to fetch: `https://pypi.org/simple/cad/`\n  Caused by: tcp connect error\n",
                 "network"),
                (2, "error: failed to write to file `/s/store/.building-1/cad/x.py`: No space left on device (os "
                    "error 28)\n", "disk_full"),
                (1, "  × No solution found when resolving dependencies:\n  ╰─▶ Because there is no version of cad==0.2.0"
                    " and you require cad==0.2.0, we can conclude that your requirements are unsatisfiable.\n",
                 "no_release"),
                (None, "TimeoutExpired: Command '['uv', 'pip']' timed out after 900 seconds", "timeout"),
                (None, "FileNotFoundError: [Errno 2] No such file or directory: 'uv'", "no_program"),
                (2, "error: something nobody has seen before\n", "unknown")):
            with self.subTest(cause=cause):
                self.calls.clear(), self.phases.clear()
                self.build = (code, said)
                found = self.update()
                self.assertEqual((found["outcome"], found["cause"], found["release"]), ("failed", cause, "0.2.0"))
                self.assertEqual(found["detail"], said.strip().splitlines()[-1].strip())
                self.assertEqual(self.calls, [("clean", [])], "nothing that runs was touched")
                self.assertEqual((self.serving, self.pointer, self.phases), ("0.1.0", None, ["building"]))
                counted = auto_update.event(found)
                self.assertEqual((counted["outcome"], counted["reason"], counted["cause"]), ("failed", "upgrade", cause))
        self.build = (1, "  × No solution found when resolving dependencies:\n  ╰─▶ Because there is no version of "
                         "cad==0.2.0, we can conclude that your requirements are unsatisfiable.\n")
        with mock.patch.dict(os.environ, {"UV_EXCLUDE_NEWER": "2026-01-01"}):
            self.assertEqual(self.update()["cause"], "config_exclude", "a setting of the person's explains it")
        self.assertIn("uv's settings found (names only): config_exclude: UV_EXCLUDE_NEWER",
                      Path(self.told["log"]).read_text(encoding="utf-8"))

    def test_a_release_that_does_not_run_is_broken_and_never_switched_to(self) -> None:
        self.verifies = None
        found = self.update()
        self.assertEqual((found["outcome"], found["cause"]), ("failed", "broken"))
        self.assertEqual(found["detail"], "the release built did not run: ModuleNotFoundError: No module named 'ezdxf'")
        self.assertEqual((self.serving, self.pointer, self.phases), ("0.1.0", None, ["building"]))

    def test_the_way_back_is_named_only_once_the_pointer_is_back(self) -> None:
        """While the pointer names the release that did not start, a start of the release before stands by
        (``auto_update.leaving``, ``client.start``); the phase ``restoring`` lets it launch its own again, so it is
        kept only once the pointer is back: a daemon launched before would run the release that does not start."""
        self.starts["0.2.0"] = False
        seen: list[tuple[str, str | None]] = []
        helper.update(self.told, run=self.cad, mark=lambda phase: seen.append((phase, self.pointer)))
        self.assertEqual([phase for phase, _pointer in seen], ["building", "switching", "restoring"])
        self.assertIsNone(seen[-1][1], "the pointer was back, at none as before, when the way back was named")

    def test_a_server_that_does_not_start_puts_the_pointer_back_and_the_release_before_runs_again(self) -> None:
        self.starts["0.2.0"] = False
        found = self.update()
        self.assertEqual(self.commands(), ["uv build", "-I -S", "server start", "server start"])
        self.assertEqual(self.calls, [("publish", "0.2.0"), ("stop", helper.STOP_SECONDS),
                                      ("point", "0.2.0-cp314"), ("restore", None), ("clean", [])],
                         "the pointer written back exactly as it was read: none")
        self.assertEqual((found["outcome"], found["cause"], found["restored"], found["started"]),
                         ("failed", "start_failed", True, "started the cad server (cad 0.1.0)"))
        self.assertEqual(self.phases, ["building", "switching", "restoring"],
                         "the way back named before the release before starts")
        self.assertEqual(found["detail"], "cad 0.2.0 did not start: cad server start: the engine server did not start: "
                                          "it exited with code 1")
        self.assertEqual((self.serving, self.pointer), ("0.1.0", None), "the release before runs, and its server")
        counted = auto_update.event(found)
        self.assertEqual((counted["outcome"], counted["reason"], counted["cause"]), ("restored", "upgrade",
                                                                                    "start_failed"))
        # A pointer of a stored release before: written back as it was read.
        kept = {"pointer": 1, "path": str(self._folder("0.1.5")), "release": "0.1.5", "prefix": "/env"}
        self.pointer, self.serving, self.starts["0.1.5"] = dict(kept), "0.1.5", True
        self.calls.clear()
        found = self.update(**{"from": "0.1.5"})
        self.assertEqual(self.pointer, kept)
        self.assertEqual((found["restored"], self.serving), (True, "0.1.5"))
        # Where the release before does not start either: said so, never put back.
        self.pointer, self.serving, self.starts["0.1.0"] = None, "0.1.0", False
        found = self.update()
        self.assertEqual((found["outcome"], found["restored"], found["started"][:12]), ("failed", False, "not started:"))
        self.assertEqual(auto_update.event(found)["reason"], "put_back")

    def test_a_server_of_the_new_release_come_up_late_is_stopped_on_the_way_back(self) -> None:
        self.starts["0.2.0"] = False
        ran = self.cad

        def late(command, timeout):
            code, said = ran(command, timeout)
            if command[1:] == ["server", "start"] and code != 0:
                self.serving = "0.2.0"  # its start was given up on, and its server answers all the same
            return code, said

        def sweep(*, stop, seconds=60.0, leave=None):
            self.calls.append(("sweep", stop, leave))
            self.serving = None
            return {"stopped": ["door"], "running": [], "removed": []}

        with mock.patch.object(client, "sweep", side_effect=self.the_switch_s_or(sweep)):
            found = helper.update(self.told, run=late, mark=self.phases.append)
        self.assertLess(self.calls.index(("restore", None)), self.calls.index(("sweep", True, None)),
                        "the pointer put back first, then the server of the release that failed stopped at once")
        self.assertEqual((found["outcome"], found["cause"], found["restored"], self.serving, self.pointer),
                         ("failed", "start_failed", True, "0.1.0", None))
        self.assertIn("the cad server 0.2.0 that answered after the switch failed was stopped",
                      Path(self.told["log"]).read_text(encoding="utf-8"))
        # The server of the release before, still there after the stop's bound: never stopped again, and joined.
        self.calls.clear()
        self.pointer, self.serving, self.gone = None, "0.1.0", False
        with mock.patch.object(client, "sweep", side_effect=self.the_switch_s_or(AssertionError("never stopped"))):
            found = self.update()
        self.assertEqual((found["restored"], self.serving), (True, "0.1.0"))
        # A stop that fails never stops the way back.
        self.pointer, self.serving, self.gone = None, "0.1.0", True
        def fails(**_asked):
            raise ConnectionError("did not exit")

        with mock.patch.object(client, "sweep", side_effect=self.the_switch_s_or(fails)):
            found = helper.update(self.told, run=late, mark=self.phases.append)
        self.assertEqual((found["outcome"], found["cause"]), ("failed", "start_failed"))
        self.assertIn("could not be stopped: ConnectionError: did not exit",
                      Path(self.told["log"]).read_text(encoding="utf-8"))

    def test_a_pointer_that_cannot_be_written_switches_nothing_and_is_said_as_the_write_s_own_failure(self) -> None:
        with mock.patch.object(store, "point", side_effect=PermissionError(13, "Permission denied")):
            found = self.update()
        self.assertEqual(self.commands(), ["uv build", "-I -S", "server start"], "the new release was never run")
        self.assertEqual((found["outcome"], found["cause"], found["restored"], found["started"]),
                         ("failed", "denied", True, "started the cad server (cad 0.1.0)"))
        self.assertEqual(found["detail"],
                         "the pointer could not be written: PermissionError: [Errno 13] Permission denied")
        self.assertEqual((self.serving, self.pointer), ("0.1.0", None), "the server it stopped runs again")
        counted = auto_update.event(found)
        self.assertEqual((counted["outcome"], counted["reason"], counted["cause"]), ("restored", "upgrade", "denied"))
        self.serving = None
        with mock.patch.object(store, "point", side_effect=OSError(28, "No space left on device")):
            found = self.update(start=False)
        self.assertEqual((found["cause"], found["restored"], found["start"]), ("disk_full", True, False),
                         "tried again by the schedule, as a release whose server did not start is not")

    def test_with_no_server_wanted_the_command_confirms_the_release(self) -> None:
        self.serving = None
        found = self.update(start=False)
        self.assertEqual(self.commands(), ["uv build", "-I -S", "--version"])
        self.assertEqual((found["outcome"], found["start"]), ("installed", False))
        self.assertNotIn("started", found)
        self.assertNotIn(("stop", helper.STOP_SECONDS), self.calls, "none to stop")
        self.assertIsNone(self.serving, "none started")
        self.pointer = None
        self.starts["0.2.0"] = False
        found = self.update(start=False)
        self.assertEqual((found["outcome"], found["cause"], found["restored"], self.pointer),
                         ("failed", "broken", True, None))
        self.serving = None
        self.starts["0.2.0"] = True
        self.pointer = None
        self.assertEqual(self.update(start=True)["started"], "started the cad server (cad 0.2.0)",
                         "`start`: a server wanted though none ran")

    def test_a_server_still_there_after_the_stop_s_bound_is_replaced_all_the_same(self) -> None:
        self.gone = False
        found = self.update()
        self.assertEqual(found["outcome"], "installed")
        self.assertEqual(self.serving, "0.2.0", "the new release's start replaced it")
        self.assertIn("still there, and the next start replaces it", Path(self.told["log"]).read_text(encoding="utf-8"))

    def test_an_environment_that_runs_the_release_already_is_left_and_an_older_server_replaced(self) -> None:
        self.stored["0.2.0"] = self._folder("0.2.0")
        self.pointer = {"path": str(self._folder("0.2.0")), "release": "0.2.0"}
        found = self.update()
        self.assertEqual((found["outcome"], found["release"], found["detail"], found["started"]),
                         ("current", "0.2.0", "cad 0.2.0 is installed", "started the cad server (cad 0.2.0)"))
        self.assertEqual(self.commands(), ["server start"], "nothing built")
        self.assertEqual(self.calls, [("stop", helper.STOP_SECONDS), ("clean", [])])
        self.assertEqual(self.phases, ["switching"], "kept before the server stops: a command meanwhile waits")
        self.assertEqual(auto_update.event(found)["cause"], "already")
        for serving, elsewhere, replaced in (("0.2.0", False, False), ("0.2.0", True, True), (None, False, True)):
            with self.subTest(serving=serving, elsewhere=elsewhere):
                self.serving, self.elsewhere = serving, elsewhere
                self.ran.clear(), self.phases.clear()
                self.update()
                self.assertEqual(self.commands(), ["server start"] if replaced else [])
                self.assertEqual(self.phases, ["switching"] if replaced else [])
        self.serving = None
        self.ran.clear()
        self.assertEqual(self.update(start=False)["start"], False)
        self.assertEqual(self.ran, [], "none ran, none wanted")
        self.assertEqual(self.update(target=None, requirement="cad>=0.1.0,<1")["outcome"], "current",
                         "with no release named: anything newer than the release that ran")

    def test_the_worker_runs_as_a_module_of_the_environment_and_keeps_its_outcome(self) -> None:
        """A real process, as the trigger starts it: uv not there, so the build fails at once, and the record says so."""
        state = self.tmp / "state"
        record = state / auto_update.RECORD
        state.mkdir()
        record.write_text(json.dumps({"release": "0.2.0", "at": 1.0, "outcome": "underway"}), encoding="utf-8")
        told = {**self.told, "record": str(record), "log": str(state / auto_update.LOG),
                "uv": str(self.tmp / "no-such-uv"), "from": "0.0.1"}
        from tests.python.support.paths import SOURCE_PATH

        done = subprocess.run([sys.executable, "-P", "-m", "cad_server._internal.auto_update_helper", json.dumps(told)],
                              capture_output=True, text=True, timeout=120, cwd=str(self.tmp),
                              env={**os.environ, "CAD_STATE_DIR": str(state), "PYTHONPATH": SOURCE_PATH})
        self.assertEqual(done.returncode, 0, done.stderr)
        found = json.loads(record.read_text(encoding="utf-8"))
        self.assertEqual((found["outcome"], found["cause"], found["at"]), ("failed", "no_program", 1.0))
        self.assertIn("$ " + str(self.tmp / "no-such-uv"), (state / auto_update.LOG).read_text(encoding="utf-8"))

    def test_a_worker_that_raises_keeps_the_attempt_underway_marked_as_its_crash_and_logs_why(self) -> None:
        record = Path(self.told["record"])
        kept = {"release": "0.2.0", "at": 1.0, "beat": 1.0, "outcome": "underway", "phase": "building"}
        record.write_text(json.dumps(kept), encoding="utf-8")
        with mock.patch.object(helper, "update", side_effect=KeyError("requirement")):
            helper.main(self.told)
        found = json.loads(record.read_text(encoding="utf-8"))
        self.assertEqual({**found, "beat": 1.0}, {**kept, "cause": "helper_crash", "detail": "KeyError: 'requirement'"})
        self.assertIn("the worker stopped with an error", Path(self.told["log"]).read_text(encoding="utf-8"))
        self.assertEqual(auto_update.event({**found, "at": 0.0, "beat": 0.0})["cause"], "helper_crash")

    def test_the_phase_is_kept_by_the_beat_and_never_written_back_by_it(self) -> None:
        record = Path(self.told["record"])
        kept = {"release": "0.2.0", "at": 1.0, "beat": 1.0, "outcome": "underway", "phase": "building"}
        record.write_text(json.dumps(kept), encoding="utf-8")
        beat = helper.Beat(self.told, every=3600)
        self.addCleanup(beat.stop)
        beat.mark("switching")
        beat.mark()
        self.assertEqual(json.loads(record.read_text(encoding="utf-8"))["phase"], "switching")
        record.write_text(json.dumps({**kept, "at": 2.0}), encoding="utf-8")
        beat.mark("switching")
        self.assertEqual(json.loads(record.read_text(encoding="utf-8"))["phase"], "building", "another attempt's")

    def record(self, **fields) -> dict:
        """The attempt's record as the claim keeps it, underway (``auto_update._claim``)."""
        kept = {"release": "0.2.0", "wanted": "0.2.0", "from": "0.1.0", "at": 1.0, "beat": 1.0, "tries": 1,
                "outcome": "underway", "phase": "building", "installer": "uv", "asked": False,
                **fields}
        Path(self.told["record"]).write_text(json.dumps(kept), encoding="utf-8")
        return kept

    def kept(self) -> dict:
        return json.loads(Path(self.told["record"]).read_text(encoding="utf-8"))

    def test_an_attempt_that_gets_its_release_ready_alone_ends_ready_and_its_release_is_kept(self) -> None:
        self.record(switch=False)
        found = self.update()
        self.assertEqual(self.commands(), ["uv build", "-I -S"], "nothing stopped, nothing started")
        self.assertEqual(self.calls, [("publish", "0.2.0"), ("clean", ["0.2.0-cp314"])],
                         "never pointed at, and kept from the store's tidying")
        self.assertEqual((self.serving, self.pointer, self.phases), ("0.1.0", None, ["building"]))
        self.assertEqual(found, {"release": "0.2.0", "outcome": "ready", "switch": False, "from": "0.1.0", "at": 1.0,
                                 "tries": 1, "ended": found["ended"], "installer": "uv", "wanted": "0.2.0",
                                 "asked": False,
                                 "detail": f"cad 0.2.0 is ready in {self._folder('0.2.0')}, and nothing points at it yet"})
        self.assertEqual(self.kept(), found, "written whole in the step that decided it")
        self.assertIn(": ready", Path(self.told["log"]).read_text(encoding="utf-8"))
        # The worker's last write never writes it again: over a sitting that resumed it since, or a second one.
        resumed = self.record(at=2.0, phase="switching")
        with mock.patch.object(helper, "update", return_value={**found, "ended": found["ended"] + 1}):
            helper.main({**self.told, "log": None})
            self.assertEqual(self.kept(), resumed)
            Path(self.told["record"]).write_text(json.dumps(found), encoding="utf-8")
            helper.main({**self.told, "log": None})
            self.assertEqual(self.kept(), found)

    def test_a_person_s_ask_during_the_build_takes_the_attempt_on_to_the_switch_as_theirs(self) -> None:
        self.record(switch=False)
        ran = self.cad

        def asked(command, timeout):
            if command[0] == "uv":  # `cad update` while uv builds: the claim makes the attempt whole
                self.record(switch=True, asked=True)
            return ran(command, timeout)

        found = helper.update(self.told, run=asked, mark=self.phases.append)
        self.assertEqual((found["outcome"], found["asked"], self.serving), ("installed", True, "0.2.0"))
        self.assertEqual(self.phases, ["building", "switching"])
        # Where the build fails after such an ask, the worker's last write keeps the ask.
        self.record(switch=True, asked=True)
        with mock.patch.object(helper, "update", return_value={"release": "0.2.0", "at": 1.0, "outcome": "failed",
                                                               "asked": False}):
            helper.main({**self.told, "log": None})
        self.assertEqual(self.kept(), {"release": "0.2.0", "at": 1.0, "outcome": "failed", "asked": True})

    def test_a_resumed_attempt_switches_to_its_stored_release_and_builds_it_again_where_it_no_longer_runs(self):
        self.stored["0.2.0"] = self._folder("0.2.0")
        self.record(phase="switching")
        found = self.update()
        self.assertEqual((found["outcome"], self.commands(), self.phases), ("installed", ["-I -S", "server start"],
                                                                            ["switching"]), "never built")
        self.pointer, self.serving = None, "0.1.0"
        self.ran.clear(), self.phases.clear()
        self.unsound.add(self._folder("0.2.0"))
        found = self.update()
        self.assertEqual(found["outcome"], "installed", "the attempt heals itself")
        self.assertEqual((self.commands(), self.phases),
                         (["-I -S", "uv build", "-I -S", "server start"], ["building", "switching"]))

    def test_the_decision_and_every_write_of_the_record_hold_the_state_folder_s_lock(self) -> None:
        """The record's read-change-write by the beat, the decision to end ``ready`` and the last write, each under
        the state folder's lock (``file_lock.state``, the claim's): what another process changed in between is never
        written back over."""
        from cad_server._internal import file_lock

        lock = Path(self.told["record"]).parent / file_lock.STATE_LOCK
        held: list[bool] = []

        def keep(path, record):
            with file_lock.attempt(lock) as free:
                held.append(not free)
            Path(path).write_text(json.dumps(record), encoding="utf-8")

        with mock.patch.object(helper, "keep", side_effect=keep):
            self.record(switch=False)
            beat = helper.Beat(self.told, every=3600)
            self.addCleanup(beat.stop)
            beat.mark("building")
            self.update()
            self.record()
            with mock.patch.object(helper, "update", return_value={"release": "0.2.0", "at": 1.0, "outcome": "failed"}):
                helper.main({**self.told, "log": None})
        self.assertEqual(held, [True, True, True], "the beat, the decision, the last write")

    def test_a_lock_that_cannot_be_taken_never_ends_the_attempt(self) -> None:
        """Where the state folder's lock cannot be taken (its file refused, the system's lock call failing), each write
        of the record is made without it (``helper.held``): the worker never dies of its record."""
        with mock.patch("cad_server._internal.file_lock.state", side_effect=OSError(13, "Permission denied")):
            self.record(switch=False)
            beat = helper.Beat(self.told, every=3600)
            self.addCleanup(beat.stop)
            beat.mark("building")
            self.assertEqual((self.kept()["phase"], self.kept()["beat"] > 1.0), ("building", True), "a beat written")
            found = self.update()
            self.assertEqual((found["outcome"], self.kept()), ("ready", found), "a ready-only attempt ends ready")
            self.record()
            with mock.patch.object(helper, "update", return_value={"release": "0.2.0", "at": 1.0, "outcome": "failed"}):
                helper.main({**self.told, "log": None})
            self.assertEqual(self.kept(), {"release": "0.2.0", "at": 1.0, "outcome": "failed"},
                             "a whole one writes its outcome")
        with mock.patch.object(helper, "_read", side_effect=RuntimeError("the step's own error")), \
                self.assertRaises(RuntimeError):
            helper.settle(self.told, {"release": "0.2.0"}, self._folder("0.2.0"))

    def test_a_log_that_cannot_be_written_never_stops_the_update(self) -> None:
        found = self.update(log=str(self.tmp / "no" / "such" / "folder" / "auto-update.log"))
        self.assertEqual(found["outcome"], "installed")

class CauseTest(unittest.TestCase):
    """Why a build did not end well, one word (``auto_update_helper.CAUSES``), told from uv's own words, as it
    printed them, and from the system's own message for an error, as uv and Python wrap it on Windows."""

    # (the cause, the installer's exit status, all it printed)
    SAID = (
        ("no_release", 1, "  × No solution found when resolving dependencies:\n"
                          "  ╰─▶ Because only cad==0.1.0 is available and you require cad>=0.5.0,<1, we\n"
                          "      can conclude that your requirements are unsatisfiable.\n"),
        ("no_release", 1, "  × No solution found when resolving dependencies:\n"
                          "  ╰─▶ Because cad was not found in the package registry and you require\n"
                          "      cad>=0.5.0,<1, we can conclude that your requirements are unsatisfiable.\n"),
        ("python", 1, "  × No solution found when resolving dependencies:\n"
                      "  ╰─▶ Because only cad==0.2.0 is available and cad==0.2.0 requires Python\n"
                      "      >=3.99, we can conclude that cad==0.2.0 cannot be used.\n"
                      "      And because you require cad==0.2.0, we can conclude that your\n"
                      "      requirements are unsatisfiable.\n"),
        ("python", 1, "upgrading cad...\nERROR: Package 'cad' requires a different Python: 3.13.18 not in '>=3.99'\n"
                      "'/home/me/.local/pipx/venvs/cad/bin/python -m pip --no-input install --upgrade cad>=0.2.0,<1\n"
                      "cad -q' failed\n"),
        ("platform", 1, "  × No solution found when resolving dependencies:\n"
                        "  ╰─▶ Because only cad==0.3.0 is available and cad==0.3.0 has no wheels with a\n"
                        "      matching Python implementation tag (e.g., `cp313`), we can conclude that\n"
                        "      cad==0.3.0 cannot be used.\n"
                        "      And because you require cad==0.3.0, we can conclude that your\n"
                        "      requirements are unsatisfiable.\n\n"
                        "hint: You require CPython 3.13 (`cp313`), but we only found wheels for `cad` (v0.3.0) with "
                        "the following Python implementation tag: `cp399`"),
        ("offline", 1, "  × No solution found when resolving dependencies:\n"
                       "  ╰─▶ Because cad was not found in the cache and you require cad>=0.5.0,<1, we\n"
                       "      can conclude that your requirements are unsatisfiable.\n\n"
                       "hint: Packages were unavailable because the network was disabled. When the network is "
                       "disabled, registry packages may only be read from the cache."),
        ("network", 2, "error: Failed to fetch: `https://pypi.org/simple/cad/`\n"
                       "  Caused by: error sending request for url (https://pypi.org/simple/cad/)\n"
                       "  Caused by: client error (Connect)\n  Caused by: tcp connect error\n"
                       "  Caused by: Connection refused (os error 111)\n"),
        ("network", 2, "error: Failed to fetch: `https://pypi.org/simple/cad/`\n"
                       "  Caused by: error sending request for url (https://pypi.org/simple/cad/)\n"
                       "  Caused by: client error (Connect)\n  Caused by: tunnel error: unsuccessful\n"),
        ("network", 2, "error: Failed to fetch: `https://pypi.org/simple/cad/`\n"
                       "  Caused by: error sending request for url (https://pypi.org/simple/cad/)\n"
                       "  Caused by: client error (Connect)\n"
                       "  Caused by: invalid peer certificate: Other(OtherError(CaUsedAsEndEntity))\n"),
        ("network", 1, "WARNING: Retrying (Retry(total=0, connect=None, read=None, redirect=None, status=None)) after "
                       "connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPConnection "
                       "object at 0x7fd5495a5160>: Failed to establish a new connection: [Errno 111] Connection "
                       "refused')': /simple/cad/\nERROR: Could not find a version that satisfies the requirement "
                       "cad<1,>=0.5.0 (from versions: none)\n"
                       "ERROR: No matching distribution found for cad<1,>=0.5.0\n"),
        ("disk_full", 2, "Resolved 1 package in 2ms\nerror: failed to write to file "
                         "`/home/me/.local/share/uv/tools/cad/bin/activate_this.py`: No space left on device (os "
                         "error 28)\n"),
        ("disk_full", 2, "error: failed to write to file `C:\\Users\\me\\AppData\\Roaming\\uv\\tools\\cad\\Lib\\"
                         "site-packages\\cad-0.2.0.dist-info\\RECORD`: There is not enough space on the disk. (os "
                         "error 112)\n"),
        ("disk_full", 1, "ERROR: Could not install packages due to an OSError: [Errno 28] No space left on device\n"),
        ("in_use", 2, "Installed 1 package in 3.20s\nerror: Failed to install entrypoint\n"
                      "  Caused by: failed to remove file `C:\\Users\\me\\.local\\bin\\cad.exe`: The process cannot "
                      "access the file because it is being used by another process. (os error 32)\n"),
        ("in_use", 1, "ERROR: Could not install packages due to an OSError: [WinError 32] The process cannot access "
                      "the file because it is being used by another process: 'C:\\\\Users\\\\me\\\\pipx\\\\venvs\\\\cad"
                      "\\\\Scripts\\\\cad.exe'\n"),
        ("denied", 2, "error: failed to remove directory `C:\\Users\\me\\AppData\\Roaming\\uv\\tools\\cad\\Lib\\"
                      "site-packages\\cad_server`: Access is denied. (os error 5)\n"),
        ("denied", 1, "ERROR: Could not install packages due to an OSError: [WinError 5] Access is denied: "
                      "'C:\\\\Users\\\\me\\\\pipx\\\\venvs\\\\cad\\\\Lib\\\\site-packages\\\\cad_server'\n"),
        ("denied", 2, "error: failed to create directory `/opt/uv/tools/cad`: Permission denied (os error 13)\n"),
        ("unknown", 1, "error: something nobody has seen before\n"),
        ("unknown", 1, ""),
    )

    def test_each_cause_the_installer_s_words_tell(self) -> None:
        for cause, code, said in self.SAID:
            with self.subTest(cause=cause, said=said[:60]):
                self.assertEqual(helper.classify(code, said), cause)
        told = {word for word, _code, _said in self.SAID}
        self.assertLessEqual(told, set(helper.CAUSES))
        self.assertIsNone(helper.classify(0, "Resolved 1 package in 1ms\nChecked 1 package in 0.06ms\n"))

    def test_a_command_that_never_ended_or_never_started_is_said_from_the_system_s_error(self) -> None:
        """Through the helper's own ``run``: a program that is not there, one that outlives its time."""
        self.assertEqual(helper.classify(*helper.run([str(Path(tempfile.gettempdir()) / "no-such-uv")], 5)),
                         "no_program")
        self.assertEqual(helper.classify(*helper.run([sys.executable, "-c", "import time; time.sleep(30)"], 0.5)),
                         "timeout")

    def test_every_cause_is_said_in_plain_words(self) -> None:
        self.assertEqual(set(auto_update.SAID), set(helper.CAUSES))
        self.assertEqual(len(helper.CAUSES), len(set(helper.CAUSES)))
        self.assertEqual(auto_update.in_words("network"), "uv could not reach the package index")
        self.assertNotIn("`", auto_update.in_words("no_switch"), "the words say what is wrong; ``advice``, what to do")

    def test_every_cause_has_one_line_that_says_what_to_do_by_who_made_the_install(self) -> None:
        """``advice``: a line for every cause the record keeps, the same for ``cad doctor``, ``cad update`` and the line
        a cad behind says; a reinstall names the installer's own command and no other; no line asks or exclaims."""
        retries = "cad tries again by itself; `cad update` tries now"
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, {"CAD_STATE_DIR": folder}):
            for word in helper.CAUSES:
                for installer in (*auto_update.INSTALLERS, None):
                    with self.subTest(word=word, installer=installer):
                        line = auto_update.advice(word, installer)
                        self.assertTrue(line and "\n" not in line and "please" not in line.lower() and "!" not in line)
                        self.assertEqual(line.count("`") % 2, 0)
                        commands = re.findall(r"`([^`]+)`", line)
                        self.assertLessEqual(set(commands), {"cad update", *auto_update.REINSTALL.values()}, line)
                        self.assertLessEqual(len(commands), 1, "one command to run, at most")
            said = {word: auto_update.advice(word) for word in helper.CAUSES}
            self.assertEqual({word for word, line in said.items() if line == retries},
                             {"network", "timeout", "no_release", "in_use", "unknown", "helper_start", "helper_crash",
                              "lost"})
            self.assertEqual(said["denied"], f"give your user write access to cad's state folder ({Path(folder)}) and "
                                             f"to uv's cache, then {retries}")
            self.assertEqual(said["disk_full"], f"free room on the disk, then {retries}")
            self.assertEqual(said["offline"], "the update follows your uv settings: change uv's offline setting, then "
                                              "`cad update`")
            self.assertEqual(said["config_index"], "the update follows your uv settings: change the package index named "
                                                   "in uv's settings, then `cad update`")
            self.assertEqual(said["broken"], "nothing to do: cad kept the release it has and tries again by itself")
            self.assertEqual(said["start_failed"], "nothing to do: cad went back to the release before and takes the "
                                                   "next release when it is out; `cad update` tries this one again")
            for word in ("no_installer", "no_program"):
                self.assertEqual(said[word], "install uv (https://docs.astral.sh/uv/), then `cad update`",
                                 "cad is whole: only uv is missing")
            for installer, command in (("uv", "uv tool install --force cad"), ("pipx", "pipx install --force cad")):
                self.assertEqual(auto_update.advice("no_switch", installer), f"install cad again: `{command}`")
                self.assertEqual(auto_update.advice("python", installer), "the release asks for a newer Python than "
                                 f"this cad was installed on: install cad again: `{command}`")
                self.assertEqual(auto_update.advice("packaged", installer), "install cad again from PowerShell opened "
                                 f"from the Start menu: `{command}`")
        with self.assertRaises(KeyError):
            auto_update.advice("half_made")

    def test_the_installer_s_settings_are_found_by_name_and_never_read_for_their_value(self) -> None:
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, ignore_errors=True)
        (home / ".config" / "uv").mkdir(parents=True)
        toml = home / ".config" / "uv" / "uv.toml"
        toml.write_text('exclude-newer = "2026-01-01T00:00:00Z"\n[[index]]\nurl = "https://mirror.example/simple"\n'
                        '[pip]\nindex-url = "https://other.example/simple"\n', encoding="utf-8")
        patch = mock.patch.object(helper, "UV_SYSTEM", ())  # none of this computer's own files
        patch.start()
        self.addCleanup(patch.stop)
        environ = {"HOME": str(home), "XDG_CONFIG_DIRS": str(home / "none"), "UV_NATIVE_TLS": "1", "PATH": "/x"}
        found = helper.settings(environ, windows=False)
        self.assertEqual(found, {"config_exclude": [f"exclude-newer ({toml})"], "config_index": [f"index ({toml})"],
                                 "config_tls": ["UV_NATIVE_TLS"]})
        self.assertNotIn("mirror.example", json.dumps(found), "names, never values")
        self.assertEqual(helper.settings({**environ, "UV_NO_CONFIG": "1"}, windows=False),
                         {"config_tls": ["UV_NATIVE_TLS"]})
        toml.write_text("not toml [", encoding="utf-8")
        self.assertEqual(helper.settings({"HOME": str(home), "XDG_CONFIG_DIRS": str(home)}, windows=False), {},
                         "a file that cannot be read holds nothing known")

    def test_a_setting_explains_a_cause_only_where_its_words_fit(self) -> None:
        tls, index = {"config_tls": ["SSL_CERT_FILE"]}, {"config_index": ["UV_INDEX_URL"]}
        certificate = "Caused by: invalid peer certificate: UnknownIssuer"
        mirror = "error: Failed to fetch: `https://mirror.example/simple/cad/`\n  Caused by: tcp connect error"
        for cause, said, found, then in (
                ("network", certificate, tls, "config_tls"), ("network", "tcp connect error", tls, "network"),
                ("network", certificate, {}, "network"), ("network", mirror, index, "config_index"),
                ("network", mirror.replace("mirror.example", "pypi.org"), index, "network"),
                ("no_release", "", index, "config_index"),
                ("no_release", "", {"config_exclude": ["UV_EXCLUDE_NEWER"]}, "config_exclude"),
                ("no_release", "", {"offline": ["UV_OFFLINE"]}, "offline"), ("in_use", "", index, "in_use"),
                ("python", "", index, "python"), ("unknown", "", index, "unknown")):
            with self.subTest(cause=cause, found=found, said=said[:30]):
                self.assertEqual(helper.refine(cause, said, found), then)


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
                mock.patch.object(auto_update, "trigger", return_value={"release": "0.2.0"}) as trigger, \
                redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = server.main(["start"])
        self.assertEqual(code, 1)
        trigger.assert_called_once_with("0.2.0", wanted="0.2.0", switch=True)
        self.assertEqual(feed.call_args.kwargs, {"fetch": True}, "the feed read where it is due: no server reads it")
        self.assertEqual(err.getvalue().splitlines(), ["cad: updating cad to 0.2.0: it is installed beside this cad, then its server is "
                                                       "started",
                                                       "cad server start: the engine server did not start"])
        err = io.StringIO()
        with self.feed("1.0.0"), \
                mock.patch.object(client, "start", side_effect=ConnectionError("the engine server did not start")), \
                mock.patch.object(auto_update, "trigger", return_value={"release": "latest"}) as trigger, \
                redirect_stderr(err), redirect_stdout(io.StringIO()):
            server.main(["start"])
        trigger.assert_called_once_with(None, wanted="1.0.0", switch=True)
        self.assertEqual(err.getvalue().splitlines()[0],
                         "cad: updating cad to the newest 0.x release: it is installed beside this cad, then its "
                         "server is started",
                         "a feed naming no release of this major: the bounded upgrade, never 1.0.0")

class AskedTest(Case):
    """``cad update`` as the server judges it (``auto_update.asked``) and begins it (``begin``): PyPI asked now, and
    none of the automatic limits -- the switch, the schedule (``next_try``) -- applies."""

    def asked(self, newest: str | None, **lines: str) -> dict:
        """``asked`` with PyPI's answer in the feed's shape: ``newest`` its newest of all (None: out of reach), and
        ``lines`` (``m0="0.2.0"``) each major's newest; by default ``newest``'s own."""
        known = None if newest is None else {"latest": newest, "lines": {key[1:]: value for key, value in lines.items()}
                                             or {newest.split(".")[0]: newest}}
        return auto_update.asked(pypi=lambda: known)

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
            self.assertEqual(self.asked("0.2.0"), {"failed": "uv cannot be found, so no update can begin: install uv "
                                                             "(https://docs.astral.sh/uv/), then `cad update`"})
        with mock.patch.object(store, "switches", return_value=False):
            self.assertEqual(self.asked("0.2.0"), {"failed": auto_update.in_words("no_switch") + ": install cad "
                                                             "again: `uv tool install --force cad`"})
        with mock.patch.object(sys, "prefix", str(self.tmp)):
            self.assertEqual(self.asked("0.2.0"), {"failed": auto_update.NOT_THE_TOOL})
        with mock.patch.object(updates, "pypi", return_value={"latest": "0.3.0", "lines": {"0": "0.3.0"}}) as pypi:
            self.assertEqual(auto_update.asked()["updating"], "0.3.0")
        pypi.assert_called_once_with()

    def test_it_stays_inside_the_major_and_names_a_higher_one(self) -> None:
        """PyPI's newest release of this major (not yanked: ``updates.pypi``'s), never a higher major's, which the
        answer names (``higher``) and nothing crosses to."""
        self.assertEqual(self.asked("1.0.0", m0="0.2.0", m1="1.0.0"),
                         {"ok": True, "updating": "0.2.0", "from": "0.1.0", "higher": "1.0.0"}, "both out")
        self.assertEqual(self.asked("1.0.0", m0="0.1.0", m1="1.0.0"),
                         {"ok": True, "newest": "0.1.0", "higher": "1.0.0"}, "nothing newer in this major")
        self.assertEqual(self.asked("1.0.0", m1="1.0.0"),
                         {"ok": True, "updating": None, "from": "0.1.0", "higher": "1.0.0"},
                         "none of this major named: the bounded upgrade all the same")
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
            self.assertEqual((again["tries"], popen.call_count), (1, 2), "begun again at once: a typed one spends no "
                                                                         "automatic try")
            self.assertEqual((auto_update.tries()["tried"], len(auto_update.tries()["recent"])), ({}, 2),
                             "counted among the day's attempts alone")
            auto_update._keep(self.state / auto_update.RECORD, {**again, "beat": again["at"] - auto_update.LOST_SECONDS})
            self.assertEqual(auto_update.begin("0.2.0")["outcome"], "underway", "its helper silent: lost, and begun "
                                                                                "again")
            self.assertEqual(popen.call_count, 3)
            auto_update._keep(self.state / auto_update.RECORD, {**again, "outcome": "failed"})
            unknown = auto_update.begin(None)
            self.assertEqual((unknown["release"], json.loads(popen.call_args.args[0][-1])["target"]), ("latest", None),
                             "PyPI out of reach: whatever the upgrade gets")
        with mock.patch.object(auto_update, "_start", side_effect=OSError("the state folder is read-only")):
            auto_update._keep(self.state / auto_update.RECORD, {**again, "outcome": "failed"})
            self.assertIsNone(auto_update.begin("0.2.0"))


class ButtonTest(Case):
    """What the viewer's update button shows (``auto_update.button``): only where cad can update itself; the release
    of its own major it is behind, never a higher major's; an attempt of this release underway; the last one's
    failure, said by its cause, until it is put away (``dismiss``) or another attempt begins."""

    def keep(self, **record) -> dict:
        found = {"release": "0.2.0", "wanted": "0.2.0", "from": "0.1.0", "at": 1000.0, "tries": 1, "installer": "uv",
                 "asked": False, **record}
        auto_update._keep(self.state / auto_update.RECORD, found)
        return found

    def test_where_it_shows_and_what_it_offers(self) -> None:
        with self.feed("0.2.0", {"0": "0.2.0"}):
            self.assertEqual(auto_update.button(), {"version": "0.1.0", "latest": "0.2.0", "state": "idle"})
            auto_update.change(False)
            self.assertEqual(auto_update.button()["latest"], "0.2.0", "automatic updates off: a person can click")
            with mock.patch.object(updates, "checking", return_value=False):  # CAD_UPDATE_CHECK=0, CI
                self.assertIsNone(auto_update.button())
            with mock.patch.object(sys, "prefix", str(self.tmp)):  # not a global install
                self.assertIsNone(auto_update.button())
            with mock.patch.object(cad_server, "__version__", "0.1.0-dev.1"):
                self.assertIsNone(auto_update.button())
        for latest, lines, offered in (("0.1.0", {"0": "0.1.0"}, None), ("1.0.0", {"0": "0.1.0", "1": "1.0.0"}, None),
                                       ("1.0.0", {"1": "1.0.0"}, None), ("1.0.0", {"0": "0.3.0", "1": "1.0.0"}, "0.3.0")):
            with self.subTest(lines=lines), self.feed(latest, lines):
                self.assertEqual(auto_update.button()["latest"], offered, "never a higher major")
        with self.feed(None):
            self.assertEqual(auto_update.button()["latest"], None)

    def test_an_attempt_underway_and_one_that_failed(self) -> None:
        now = time.time()
        with self.feed("0.2.0", {"0": "0.2.0"}):
            self.keep(outcome="underway", at=now)
            self.assertEqual(auto_update.button(now=now + 5),
                             {"version": "0.1.0", "latest": "0.2.0", "state": "working", "at": now, "asked": False})
            for phase in auto_update.PHASES:  # the step it is at, which the button's ring shows
                self.keep(outcome="underway", at=now, phase=phase)
                self.assertEqual(auto_update.button(now=now + 5)["phase"], phase)
            self.keep(outcome="underway", at=now, phase="polishing")
            self.assertNotIn("phase", auto_update.button(now=now + 5), "a word no page knows is not passed on")
            self.keep(outcome="underway", at=now, **{"from": "0.0.9"})
            self.assertEqual(auto_update.button(now=now + 5)["state"], "idle",
                             "another release's attempt: the one that installed this cad, its end not written yet")
            for word, said in (("in_use", "a file of cad's was in use by another program"),
                               ("network", "uv could not reach the package index"),
                               ("config_exclude", "a setting of uv's hides newer releases (exclude-newer)")):
                with self.subTest(word=word):
                    self.keep(outcome="failed", ended=now, cause=word, at=now)
                    self.assertEqual(auto_update.button(now=now + 5),
                                     {"version": "0.1.0", "latest": "0.2.0", "state": "failed", "at": now,
                                      "asked": False, "cause": word, "said": said, "installer": "uv"})
            (self.state / auto_update.LOG).write_text("$ uv tool install --upgrade cad\n", encoding="utf-8")
            self.assertEqual(auto_update.button(now=now + 5)["log"], str(self.state / auto_update.LOG),
                             "the helper's log, where there is one")
            self.keep(outcome="failed", ended=now, cause="start_failed", restored=True, at=now, asked=True)
            self.assertEqual(auto_update.button(now=now + 5)["said"], "the new release's server did not start, so the "
                                                                      "release before runs again")
            self.keep(outcome="underway", at=now - auto_update.RETRY_SECONDS)
            self.assertEqual(auto_update.button(now=now)["cause"], "lost", "a record a release before the beat kept")
            self.keep(outcome="underway", at=now - 3 * auto_update.HOUR, beat=now - 60)
            self.assertEqual(auto_update.button(now=now)["state"], "working", "past the hour, its helper beating")
            self.keep(outcome="underway", at=now - 3 * auto_update.HOUR, beat=now - auto_update.LOST_SECONDS)
            self.assertEqual(auto_update.button(now=now)["cause"], "lost", "its helper silent")
            self.keep(outcome="underway", at=now, cause="helper_crash")
            self.assertEqual(auto_update.button(now=now + 5)["state"], "failed", "a helper that raised")
            self.keep(outcome="installed", ended=now, release="0.2.0", at=now)
            self.assertEqual(auto_update.button(now=now + 5)["state"], "idle")
        with self.feed("0.1.0", {"0": "0.1.0"}):
            self.assertEqual(auto_update.button(now=now + 5)["state"], "idle", "no longer behind: nothing to say")
        with self.feed("0.2.0", {"0": "0.2.0"}), mock.patch.object(auto_update, "stale", return_value=True) as stale:
            self.keep(outcome="failed", ended=now, cause="network", at=now)
            self.assertEqual(auto_update.button(now=now + 5)["state"], "idle",
                             "the environment holds the release already: a click restarts the server on it")
        self.assertEqual(stale.call_args.args[0], "0.2.0")

    def test_a_failure_put_away_stays_away_until_another_attempt(self) -> None:
        now = time.time() - 100
        with self.feed("0.2.0", {"0": "0.2.0"}):
            self.keep(outcome="failed", ended=now, cause="disk_full", at=now)
            self.assertFalse(auto_update.dismiss(now - 1), "another attempt's: nothing put away")
            self.assertEqual(auto_update.button(now=now + 5)["state"], "failed")
            self.assertNotIn("dismissed", auto_update.button(now=now + 5))
            self.assertTrue(auto_update.dismiss(now))
            self.assertTrue(auto_update.last()["dismissed"])
            put = auto_update.button(now=now + 5)
            self.assertEqual((put["state"], put["cause"], put["dismissed"]), ("failed", "disk_full", True),
                             "still said, put away: behind its icon on every page")
            self.keep(outcome="underway", at=now + 10)
            self.assertFalse(auto_update.dismiss(now + 10), "an attempt underway has nothing to put away")
            self.keep(outcome="failed", ended=now + 20, cause="network", at=now + 10)
            self.assertEqual(auto_update.button(now=now + 30)["cause"], "network", "a new attempt's failure shows")
            self.assertNotIn("dismissed", auto_update.button(now=now + 30))


class ReadyTest(Case):
    """The server's own update gets its release ready and switches nothing (``"switch": false``, outcome ``ready``);
    the switch follows by itself only as the server starts (``restart``), or at a person's ask, whatever the moment
    (``_claim``); never at a tending, however long the release has been ready. On a clock of the
    test's own; the worker stands in (``Popen``) and its record is written as it writes one."""

    T0 = 1_000_000.0

    def setUp(self) -> None:
        super().setUp()
        self.clock = [self.T0]
        self.known = {"latest": "0.2.0", "lines": {"0": "0.2.0"}}  # the version feed as last read
        self.popen = mock.Mock()
        self.counted: list[dict] = []
        for patch in (mock.patch.object(auto_update.time, "time", lambda: self.clock[0]),
                      mock.patch.object(auto_update.subprocess, "Popen", self.popen),
                      mock.patch.object(updates, "feed", side_effect=lambda fetch=False: self.known),
                      mock.patch.object(sys, "_base_executable", str(self.tmp / "python3"), create=True),
                      mock.patch("cad_server.analytics.update", side_effect=lambda **kw: self.counted.append(kw))):
            patch.start()
            self.addCleanup(patch.stop)

    def stored(self, release: str = "0.2.0") -> Path:
        """``release`` whole in the store, as the worker's build leaves it (``store.publish``'s marker)."""
        folder = store.folder(release)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / store.MARKER).write_text(json.dumps({"store": 1, "release": release, "python": store.tag(),
                                                       "for": store.built_for(), "built": 0.0}), encoding="utf-8")
        return folder

    def made(self, release: str = "0.2.0") -> dict:
        """The server's tending with nothing run: the attempt at ``release`` begun to get it ready alone, then ended by
        its worker as it ends one (``auto_update_helper.settle``): ``ready``, the release in the store."""
        for name in (auto_update.RECORD, auto_update.TRIED):
            (self.state / name).unlink(missing_ok=True)
        begun = auto_update.tend()
        self.assertEqual((begun["release"], begun["switch"], begun["phase"]), (release, False, "building"))
        self.assertNotIn("switch", json.loads(self.popen.call_args.args[0][-1]), "the worker reads it from the record")
        folder = self.stored(release)
        found = {**{name: begun[name] for name in ("release", "wanted", "from", "at", "tries", "installer", "asked")},
                 "outcome": "ready", "switch": False, "ended": self.clock[0],
                 "detail": f"cad {release} is ready in {folder}, and nothing points at it yet"}
        auto_update._keep(self.state / auto_update.RECORD, found)
        self.popen.reset_mock()
        return found

    def told(self) -> dict:
        return json.loads(self.popen.call_args.args[0][-1])

    def test_a_release_ready_is_this_release_s_last_record_whose_folder_is_still_a_release(self) -> None:
        self.assertEqual((auto_update.ready(), auto_update.kept()), (None, []), "no record")
        found = self.made()
        self.assertEqual((auto_update.ready(), auto_update.kept()), (found, [store.folder("0.2.0")]))
        self.assertEqual((auto_update.underway(), auto_update.cause(found), auto_update.event(found)), (None, None, None),
                         "neither underway nor ended: nothing is counted for it")
        self.assertFalse(auto_update.report())
        for case, record in (("another release's", {**found, "from": "0.0.9"}),
                             ("installed", {**found, "outcome": "installed"}),
                             ("no release named", {**found, "release": "latest"})):
            with self.subTest(case=case):
                auto_update._keep(self.state / auto_update.RECORD, record)
                self.assertEqual((auto_update.ready(), auto_update.kept()), (None, []))
        auto_update._keep(self.state / auto_update.RECORD, found)
        (store.folder("0.2.0") / store.MARKER).unlink()
        self.assertEqual((auto_update.ready(), auto_update.kept()), (None, []), "its folder no release any more")
        (self.state / auto_update.RECORD).write_text("not json", encoding="utf-8")
        self.assertIsNone(auto_update.ready())

    def test_the_release_ready_is_not_due_again_and_a_newer_one_takes_its_place(self) -> None:
        self.made()
        self.assertIsNone(auto_update.due(), "only its switch is left")
        self.known = {"latest": "0.2.1", "lines": {"0": "0.2.1"}}
        self.assertEqual(auto_update.due(), auto_update.Due("0.2.1", "0.2.1"))
        begun = auto_update.tend()
        self.assertEqual((begun["release"], begun["switch"], self.told()["target"]), ("0.2.1", False, "0.2.1"),
                         "got ready alone too")
        self.assertEqual(auto_update.kept(), [], "the release that was ready is the worker's to tidy now")

    def test_restart_never_by_itself_where_updates_are_off_or_the_feed_no_longer_calls_for_it(self) -> None:
        found = self.made()
        self.clock[0] += auto_update.DAY
        for case, patch in (
                ("automatic updates off", mock.patch.object(auto_update, "switches", return_value={"on": False})),
                ("the check off", mock.patch.object(updates, "checking", return_value=False)),
                ("not a global install", mock.patch.object(sys, "prefix", str(self.tmp))),
                ("the feed unreadable", mock.patch.object(self, "known", None)),
                ("the feed calls for another", mock.patch.object(self, "known", {"latest": "0.2.1",
                                                                                 "lines": {"0": "0.2.1"}})),
                ("the feed calls for none", mock.patch.object(self, "known", {"latest": "0.1.0",
                                                                              "lines": {"0": "0.1.0"}}))):
            with self.subTest(case=case), patch:
                self.assertIsNone(auto_update.restart())
        self.popen.assert_not_called()
        self.assertEqual(auto_update.last(), found, "left ready, for a person")

    def test_a_tending_never_switches_however_long_the_release_has_been_ready(self) -> None:
        from cad_server.engine import daemon

        found = self.made()
        for since in (0.0, auto_update.HOUR, auto_update.DAY, 30 * auto_update.DAY):
            with self.subTest(since=since):
                self.clock[0] = found["ended"] + since
                self.assertIsNone(auto_update.tend())
        # Nor the server's own tending, with nothing in flight and nothing asked of it since it started.
        engine = mock.Mock(address=None, door=None, draining=False, worked=5.0, began=5.0, last=5.0)
        engine.stopping.is_set.return_value = False
        engine.working.return_value = False
        with mock.patch.object(updates, "refresh"), mock.patch.object(daemon, "_send_counts"), \
                redirect_stderr(io.StringIO()) as err:
            daemon.Daemon.tend(engine)
        self.assertEqual((auto_update.last(), self.popen.call_count, err.getvalue()), (found, 0, ""),
                         "left ready: the next start or a person's ask switches")

    def test_restart_by_itself_as_the_server_starts(self) -> None:
        found = self.made()
        self.clock[0] = found["ended"] + 5
        begun = auto_update.restart()
        self.assertEqual(auto_update.last(), begun)
        self.assertEqual((begun["release"], begun["outcome"], begun["phase"], begun["at"], begun["beat"],
                          begun["tries"], begun["asked"]),
                         ("0.2.0", "underway", "switching", self.clock[0], self.clock[0], found["tries"], False))
        self.assertNotIn("switch", begun, "a whole update: its switch")
        told = self.told()
        self.assertEqual((told["target"], told["requirement"], told["start"], told["asked"]),
                         ("0.2.0", "cad==0.2.0", True, False))
        self.assertTrue(auto_update.switching() and auto_update.leaving(), "a start meanwhile stands aside")

    def test_the_resume_spends_no_try_and_is_held_by_no_schedule(self) -> None:
        found = self.made()
        book = json.loads((self.state / auto_update.TRIED).read_text(encoding="utf-8"))
        book["recent"] += [self.T0 + 1, self.T0 + 2, self.T0 + 3]  # the day's four begun
        book["tried"]["0.2.0"]["cause"] = "start_failed"  # and the release held back
        auto_update._keep(self.state / auto_update.TRIED, book)
        self.clock[0] += 60  # its next try an hour away by the schedule
        self.assertIsNotNone(auto_update.next_try("0.2.0", auto_update.tries(), self.clock[0]))
        begun = auto_update.restart()
        self.assertEqual((begun["at"], begun["tries"]), (self.clock[0], found["tries"]))
        after = auto_update.tries()
        self.assertEqual((after["recent"], after["seen"]), (book["recent"], self.clock[0]),
                         "nothing added to the day's attempts")
        self.assertEqual((after["tried"]["0.2.0"]["tries"], after["tried"]["0.2.0"]["at"]), (1, self.clock[0]),
                         "the last try's begin is this sitting's, so a switch that fails is that try's cause")
        self.assertEqual(self.counted, [], "the ready attempt is no event: its switch is counted when it ends")
        # The switch's server did not start: that try's cause, and the release held back by itself.
        auto_update._keep(self.state / auto_update.RECORD, {**begun, "outcome": "failed", "cause": "start_failed",
                                                            "ended": self.clock[0]})
        self.assertTrue(auto_update.given_up("0.2.0", auto_update.tries()))
        self.assertEqual(auto_update.after_failed_start(), None, "not tried again by itself")

    def test_a_person_s_ask_resumes_the_release_ready_or_begins_the_one_asked_for(self) -> None:
        for case, target in (("the release ready", "0.2.0"), ("PyPI out of reach", None)):
            with self.subTest(case=case):
                found = self.made()
                self.clock[0] += 60
                begun = auto_update.begin(target)
                self.assertEqual((begun["release"], begun["phase"], begun["asked"], begun["tries"]),
                                 ("0.2.0", "switching", True, found["tries"]))
                self.assertEqual((self.told()["target"], self.told()["requirement"], self.told()["asked"]),
                                 ("0.2.0", "cad==0.2.0", True), "exactly the release that is ready")
                self.assertEqual(auto_update.tries()["tried"]["0.2.0"]["at"], found["at"], "a typed one spends none")
        self.made()
        begun = auto_update.begin("0.2.1")
        self.assertEqual((begun["release"], begun["phase"], begun["asked"]), ("0.2.1", "building", True))
        self.assertNotIn("switch", begun)
        self.assertEqual(auto_update.kept(), [], "another release asked for: a new attempt takes the record's place")
        found = self.made()
        self.assertIsNone(auto_update.trigger("0.2.0", wanted="0.2.0", switch=False),
                          "an attempt that gets a release ready alone never resumes one")
        self.assertEqual(auto_update.last(), found)
        self.popen.assert_not_called()
        self.assertEqual(auto_update.after_failed_start(), "0.2.0", "a start that failed: as a start's, its switch")
        self.assertEqual(auto_update.last()["phase"], "switching")

    def test_a_person_who_asks_during_the_silent_build_gets_the_whole_update(self) -> None:
        begun = auto_update.tend()
        self.assertIsNone(auto_update.trigger("0.2.0", wanted="0.2.0"), "the server's own joins nothing")
        self.assertEqual(auto_update.last(), begun, "and changes nothing")
        joined = auto_update.begin("0.2.0")
        self.assertEqual((joined["at"], joined["switch"], joined["asked"]), (begun["at"], True, True))
        self.assertEqual(auto_update.last(), joined, "made whole in the record, in the step that joins it")
        self.assertEqual(self.popen.call_count, 1, "never a second attempt at once")
        self.assertEqual(auto_update.begin("0.2.0"), joined, "joined again as it is")

    def test_the_button_shows_a_release_ready_and_nothing_of_a_silent_build(self) -> None:
        begun = auto_update.tend()
        self.assertEqual(auto_update.button(now=self.clock[0] + 5),
                         {"version": "0.1.0", "latest": "0.2.0", "state": "idle"}, "offered as it was")
        auto_update.begin("0.2.0")
        self.assertEqual(auto_update.button(now=self.clock[0] + 5),
                         {"version": "0.1.0", "latest": "0.2.0", "state": "working", "at": begun["at"], "asked": True,
                          "phase": "building"}, "a person's: it restarts the server")
        found = self.made()
        self.assertEqual(auto_update.button(now=self.clock[0] + 5),
                         {"version": "0.1.0", "latest": "0.2.0", "state": "ready", "ready": "0.2.0",
                          "at": found["at"], "asked": False})
        auto_update.change(False)
        self.assertEqual(auto_update.button(now=self.clock[0] + 5)["state"], "ready", "a person can always click")
        self.known = {"latest": "0.2.1", "lines": {"0": "0.2.1"}}
        self.assertEqual(auto_update.button(now=self.clock[0] + 5),
                         {"version": "0.1.0", "latest": "0.2.1", "state": "idle"}, "the feed moved on")

    def test_the_server_s_start_is_the_switch_unless_it_is_the_person_s_own_or_updates_are_off(self) -> None:
        from cad_server.engine import daemon

        found = self.made()
        err = io.StringIO()
        with mock.patch.object(daemon, "lock", return_value=None) as lock, redirect_stderr(err):
            self.assertEqual(daemon.main([], foreground=True), 0, "a person's own server: started as it is")
            self.assertEqual(daemon.main(["--port", "4321"]), 0, "a port named: the person's, started as it is")
            auto_update.change(False)
            self.assertEqual(daemon.main([]), 0)
            auto_update.change(True)
        self.assertEqual((lock.call_count, auto_update.last(), self.popen.call_count), (3, found, 0))
        with mock.patch.object(daemon, "lock", side_effect=AssertionError("no lock is taken")), redirect_stderr(err):
            self.assertEqual(daemon.main([]), 0, "it stands aside: the update's worker starts the next server")
        begun = auto_update.last()
        self.assertEqual((begun["outcome"], begun["phase"], self.popen.call_count), ("underway", "switching", 1))
        self.assertIn("cad 0.2.0 is installed beside this cad, so this start restarts on it", err.getvalue())
        with mock.patch.object(daemon, "lock", side_effect=AssertionError("no lock is taken")):
            self.assertEqual(daemon.main([]), 0, "a start again meanwhile stands aside too, and begins none")
        self.assertEqual((auto_update.last(), self.popen.call_count), (begun, 1))

    def test_the_server_s_start_keeps_the_release_ready_as_it_tidies_the_store(self) -> None:
        import threading

        from cad_server.engine.daemon import Daemon

        self.made()
        stand_in = types.SimpleNamespace(draining=False, stopping=threading.Event(), tidied=float("-inf"),
                                         catching=types.SimpleNamespace(tend=lambda told: None))
        with mock.patch.object(store, "clean") as clean, mock.patch.object(auto_update, "report"):
            Daemon.caught_up(stand_in, starting=True)
        clean.assert_called_once_with(keep=[store.folder("0.2.0")])

    def test_a_server_tidies_the_store_at_most_once_an_hour_and_never_while_an_update_is_underway(self) -> None:
        # The release a switch left goes at a later tidying (the switch's own worker still ran it as it tidied): a
        # server that runs for days tidies within the hour after the switch, not only at its next start.
        import threading

        from cad_server.engine import daemon
        from cad_server.engine.daemon import Daemon

        stand_in = types.SimpleNamespace(draining=False, stopping=threading.Event(), tidied=float("-inf"),
                                         catching=types.SimpleNamespace(tend=lambda told: None))
        clock = [10_000.0]
        underway = [None]
        with mock.patch.object(store, "clean") as clean, mock.patch.object(auto_update, "report"), \
                mock.patch.object(daemon.time, "monotonic", side_effect=lambda: clock[0]), \
                mock.patch.object(auto_update, "underway", side_effect=lambda: underway[0]):
            Daemon.caught_up(stand_in, starting=True)
            Daemon.caught_up(stand_in)
            clock[0] += daemon.TIDY_SECONDS - 1
            Daemon.caught_up(stand_in)
            self.assertEqual(clean.call_count, 1, "at the start, then nothing within the hour")
            clock[0] += 1
            underway[0] = {"outcome": "underway"}
            Daemon.caught_up(stand_in)
            self.assertEqual(clean.call_count, 1, "never while an update is underway")
            underway[0] = None
            Daemon.caught_up(stand_in)
            self.assertEqual(clean.call_count, 2, "an hour on, it tidies again")


class ServerUpdateTest(Case):
    """The server's part of ``cad update`` (``Daemon.update``): the update begun at once, whatever is in flight; an
    attempt underway joined; what the command asks while it waits."""

    def test_begun_at_once_whatever_is_in_flight_and_an_attempt_underway_joined(self) -> None:
        """A typed update begins at once: the release is built beside the one that runs, then the switch
        stops this server at once, whatever is in flight (the worker's ``stop``)."""
        from cad_server.engine.daemon import Daemon

        fake = types.SimpleNamespace(working=lambda: True)
        ask = lambda request: Daemon.update(fake, request)  # noqa: E731
        # ``"major": true``: what an older ``cad update --major`` sends, read no more: the update stays in its major.
        for newest, major in (("0.2.0", False), (None, False), ("0.2.0", True)):
            judged = {"ok": True, "updating": newest, "from": "0.1.0"}
            begun = {"release": newest or "latest", "at": 5.0, "outcome": "underway"}
            with self.subTest(newest=newest, major=major), \
                    mock.patch.object(auto_update, "asked", return_value=judged) as asked, \
                    mock.patch.object(auto_update, "begin", return_value=begun) as begin, \
                    redirect_stderr(io.StringIO()) as err:
                self.assertEqual(ask({"op": "update", **({"major": True} if major else {})}),
                                 {**judged, "updating": newest or "latest", "since": 5.0})
            asked.assert_called_once_with()
            begin.assert_called_once_with(newest)
            self.assertIn("this server restarts on it, stopping what is in flight", err.getvalue())
        self.assertEqual(ask({"op": "update", "begin": False})["waiting"], None, "none waits to begin")
        with mock.patch.object(auto_update, "asked", return_value={"ok": True, "updating": "0.2.0", "from": "0.1.0"}), \
                mock.patch.object(auto_update, "begin", return_value=None):
            self.assertEqual(ask({"op": "update"}),
                             {"failed": "the update could not begin, so cad 0.1.0 stays as it is"})
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

    def test_a_higher_major_is_named_in_one_line_and_never_crossed_to(self) -> None:
        line = auto_update.MAJOR_LINE.format(release="1.0.0")
        self.assertEqual(line, "cad 1.0.0, a new major version, is out: the migration guides say what changes "
                               "(https://github.com/earthtojake/text-to-cad/tree/main/docs/migrations)")
        self.assertNotIn("`cad update", line, "no command crosses a major")
        self.assertEqual(self.typed({"ok": True, "newest": "0.1.0", "higher": "1.0.0"})[:3],
                         (0, f"cad 0.1.0 is the newest 0.x release\n{line}\n", ""))
        answer = {"ok": True, "updating": "0.2.0", "from": "0.1.0", "since": 5.0, "higher": "1.0.0"}
        record = {"release": "0.2.0", "at": 5.0, "outcome": "installed", "started": "started"}
        code, out, err, request = self.typed(answer, looks=[("0.2.0", record, None, True)])
        self.assertEqual((code, out, err), (0, f"cad 0.1.0 updated to 0.2.0\n{line}\n", ""))
        self.assertEqual(request.call_args.args[0], {"op": "update"}, "asked of the server as it always is")
        current = {**record, "release": "0.1.0", "outcome": "current"}
        self.assertEqual(self.typed({**answer, "updating": None}, looks=[("0.1.0", current, None, True)])[:3],
                         (0, f"cad 0.1.0 is the newest 0.x release\n{line}\n", ""), "PyPI named none of this major")
        failed = {**record, "outcome": "failed", "detail": "uv said no"}
        self.assertNotIn(line, self.typed(answer, looks=[("0.1.0", failed, None, True)])[1], "said where it ended well")

    def test_major_is_no_option_and_the_help_says_the_rule(self) -> None:
        """``--major`` is gone: refused as any unknown option is, before anything is asked or written."""
        for argv in (["--major"], ["--major", "auto"], ["auto", "--major"], ["--major", "auto", "status"]):
            with self.subTest(argv=argv):
                code, out, err, request = self.typed(argv=argv)
                self.assertEqual((code, out), (2, ""))
                self.assertIn("unrecognized arguments: --major", err)
                request.assert_not_called()
        self.assertFalse((self.state / "settings.json").exists(), "nothing written")
        code, out, _err, _request = self.typed(argv=["--help"])
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[:2], ["usage: cad update [-h]", "       cad update auto [{status,on,off}]"])
        self.assertIn("cad installs every newer release of its major version by itself, and never a new major "
                      "version.", " ".join(out.split()))

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
                             (0, "cad 0.1.0 updated to 0.2.0\n", "cad: installing cad 0.2.0 beside cad 0.1.0\n"),
                             "each step said once on stderr as the record names it")
        told = json.loads(popen.call_args.args[0][-1])
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

    def test_a_failure_says_its_cause_what_to_do_and_where_the_log_is_in_one_line(self) -> None:
        answer = {"ok": True, "updating": "0.2.0", "from": "0.1.0", "since": 5.0}
        failed = {"release": "0.2.0", "at": 5.0, "outcome": "failed", "detail": "error: uv's last line",
                  "installer": "uv"}
        log = self.state / auto_update.LOG
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("cad's update, begun ...\n", encoding="utf-8")
        for record, line in (
                ({**failed, "cause": "network"},
                 "could not update cad 0.1.0 to 0.2.0, as uv could not reach the package index: cad tries again by "
                 f"itself; `cad update` tries now; its log: {log}"),
                ({**failed, "cause": "no_switch", "installer": "pipx"},
                 f"could not update cad 0.1.0 to 0.2.0, as {auto_update.in_words('no_switch')}: install cad again: "
                 f"`pipx install --force cad`; its log: {log}"),
                ({**failed, "cause": "start_failed", "restored": True, "detail": "cad 0.2.0 did not start: x"},
                 "could not update cad 0.1.0 to 0.2.0, as the new release's server did not start, so the release "
                 "before runs again (cad 0.1.0): nothing to do: cad went back to the release before and takes the "
                 f"next release when it is out; `cad update` tries this one again; its log: {log}"),
                ({**failed, "cause": "start_failed", "restored": False, "detail": "cad 0.2.0 did not start: x"},
                 "could not update cad 0.1.0 to 0.2.0, as the new release's server did not start, so the release "
                 "before runs again (cad 0.1.0), but its server did not start either: `cad server start` starts it; "
                 f"its log: {log}")):
            with self.subTest(cause=record["cause"]):
                code, out, err, _request = self.typed(answer, looks=[("0.1.0", record, None, True)])
                self.assertEqual((code, out, err), (1, "", f"cad update: {line}\n"))
                self.assertNotIn("uv's last line", err, "uv's words only where there is no cause")
        log.unlink()
        self.assertEqual(self.typed(answer, looks=[("0.1.0", {**failed, "cause": "disk_full"}, None, True)])[2],
                         "cad update: could not update cad 0.1.0 to 0.2.0, as the disk is full: free room on the disk, "
                         "then cad tries again by itself; `cad update` tries now\n", "no log: none named")

    def test_a_release_ready_is_said_as_its_restart_alone(self) -> None:
        """The attempt begins at its switch (``auto_update._claim``'s resume): the restart, naming the release, with no
        line before it; where that release no longer runs and is built again, its switch said again after."""
        answer = {"ok": True, "updating": "0.2.0", "from": "0.1.0", "since": 5.0}
        resumed = {"release": "0.2.0", "at": 5.0, "outcome": "underway", "phase": "switching"}
        installed = {**resumed, "outcome": "installed", "started": "started"}
        restarting = "cad: restarting the cad server on cad 0.2.0, installed beside cad 0.1.0\n"
        self.assertEqual(self.typed(answer, looks=[("0.1.0", resumed, None, True), ("0.2.0", installed, None, True)])[:3],
                         (0, "cad 0.1.0 updated to 0.2.0\n", restarting))
        looks = [("0.1.0", resumed, None, True), ("0.1.0", {**resumed, "phase": "building"}, None, True),
                 ("0.1.0", resumed, None, True), ("0.2.0", installed, None, True)]
        self.assertEqual(self.typed(answer, looks=looks)[2],
                         restarting + "cad: installing cad 0.2.0 beside cad 0.1.0\n"
                                      "cad: restarting the cad server on it\n")
        looks = [(None, resumed, None, False), (None, {**installed, "start": False}, None, False)]
        self.assertEqual(self.typed({**answer, "here": True}, looks=looks)[:3],
                         (0, "cad 0.1.0 updated to 0.2.0\n", "cad: switching to cad 0.2.0, installed beside cad 0.1.0\n"),
                         "no server running")

    def test_it_gives_up_waiting_after_half_an_hour(self) -> None:
        from cad_server.cli import update as typed

        said: list[str] = []
        clock = iter(range(0, 10_000, 100))
        code = typed.wait(lambda: (None, {"release": "0.2.0", "at": 5.0, "outcome": "underway"}, None, False), "0.1.0",
                          5.0, said=lambda words: said.append(words) or 1, clock=lambda: float(next(clock)),
                          sleep=lambda _s: None)
        self.assertEqual((code, said), (1, ["the update of cad 0.1.0 is still underway after 30 minutes: run "
                                            "`cad --version` later to see where it ended"]))


class DoctorTest(Case):
    def test_doctor_says_a_release_ready_and_when_cad_restarts_on_it(self) -> None:
        from cad_server.cli import doctor

        folder = store.folder("0.2.0")
        folder.mkdir(parents=True)
        (folder / store.MARKER).write_text(json.dumps({"store": 1, "release": "0.2.0", "python": store.tag(),
                                                       "for": store.built_for(), "built": 0.0}), encoding="utf-8")
        auto_update._keep(self.state / auto_update.RECORD, {
            "release": "0.2.0", "wanted": "0.2.0", "from": "0.1.0", "at": 0.0, "tries": 1, "outcome": "ready",
            "switch": False, "ended": 1.0, "asked": False, "detail": f"cad 0.2.0 is ready in {folder}"})
        ready = "cad 0.2.0 is installed beside the cad that runs"
        with self.feed("0.2.0", {"0": "0.2.0"}):
            self.assertEqual(doctor._attempt(), (doctor.INFO, f"{ready}, and cad restarts on it as the server next "
                                                              "starts; now with `cad update`"))
            auto_update.change(False)
            self.assertEqual(doctor._attempt(), (doctor.INFO, f"{ready}: automatic updates are off, so cad restarts "
                                                              "on it with `cad update` or the viewer's update button"))
        with self.feed("0.2.1", {"0": "0.2.1"}):
            self.assertEqual(doctor._attempt(), (doctor.INFO, f"{ready}, but the version feed no longer calls for it, "
                                                              "so cad does not restart on it by itself: `cad update` "
                                                              "updates cad"))
            self.assertEqual(doctor._fix([doctor._check("attempt", *doctor._attempt())]), [], "nothing to fix")

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
        self.assertRegex(lines["attempt"], r"^0\.1\.0 to 0\.2\.0 on \S+ \S+: failed \(uv said no\); cad 0\.1\.0 runs again$")

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
                "newest", doctor.INFO, "cad 0.3.0 is the newest 0.x release the version feed names (asked less than a "
                                       "minute ago)", [line]))
            self.assertEqual(self.cli(), (0, f"update auto: on\n{line}\n", ""))
            self.assertEqual(self.cli("off"), (0, "update auto: off\n", ""), "said by the status alone")
        self.assertTrue(read.call_args_list and all(call.kwargs == {"fetch": False} for call in read.call_args_list),
                        "read as last kept, never fetched")
        known["feed"] = {"latest": "0.3.0", "lines": {"0": "0.3.0"}}
        (self.state / updates.FILE).write_text(json.dumps(known), encoding="utf-8")
        self.assertEqual(doctor._newest(), doctor._check("newest", doctor.INFO,
                                                         "cad 0.3.0 is the newest 0.x release the version feed names "
                                                         "(asked less than a minute ago)"))
        known["feed"] = {"latest": "1.2.0"}  # none of this major named
        (self.state / updates.FILE).write_text(json.dumps(known), encoding="utf-8")
        self.assertEqual(doctor._newest()["detail"], "the version feed names no 0.x release; its newest is cad 1.2.0 "
                                                     "(asked less than a minute ago)")

    def test_doctor_says_why_each_attempt_ended_as_it_did_and_where_its_log_is(self) -> None:
        """Each outcome's line: the installer's words whatever the outcome, and the cause in plain words, a warning
        where it failed, kept the release that ran, or was lost; then the log, where there is one."""
        from cad_server.cli import doctor

        now = time.time()
        base = {"release": "0.2.0", "wanted": "0.2.0", "from": "0.1.0", "at": now, "tries": 1, "installer": "uv"}
        head = r"^0\.1\.0 to {release} on \S+ \S+: "
        in_use = ("Caused by: failed to remove file `C:\\Users\\me\\.local\\bin\\cad.exe`: The process cannot access "
                  "the file because it is being used by another process. (os error 32)")
        for record, status, said in (
                ({**base, "outcome": "installed", "detail": ""}, doctor.INFO, "installed$"),
                ({**base, "release": "0.1.5", "outcome": "installed", "detail": "it installed 0.1.5, not 0.2.0"},
                 doctor.INFO, r"installed \(it installed 0\.1\.5, not 0\.2\.0\)$"),
                ({**base, "outcome": "failed", "detail": "cad 0.2.0 did not start: x", "cause": "start_failed",
                  "restored": True}, doctor.WARNING,
                 r"failed \(cad 0\.2\.0 did not start: x\): the new release's server did not start, so the release "
                 r"before runs again; cad 0\.1\.0 runs again$"),
                ({**base, "release": "0.3.0", "outcome": "current", "detail": "cad 0.3.0 is installed"}, doctor.INFO,
                 r"current \(cad 0\.3\.0 is installed\)$"),
                ({**base, "outcome": "failed", "detail": in_use, "cause": "in_use", "restored": True}, doctor.WARNING,
                 r"failed \(Caused by: .+ \(os error 32\)\): a file of cad's was in use by another program; cad "
                 r"0\.1\.0 runs again$"),
                ({**base, "outcome": "failed", "detail": "uv said no", "cause": "network", "installer": "pipx"},
                 doctor.WARNING, r"failed \(uv said no\): uv could not reach the package index$"),
                ({**base, "outcome": "failed", "detail": "the update's worker could not start: OSError: x",
                  "cause": "helper_start"}, doctor.WARNING, r"failed \(.+\): the update's worker could not start$"),
                ({**base, "outcome": "underway"}, doctor.INFO, "underway$"),
                ({**base, "outcome": "underway", "at": now - auto_update.RETRY_SECONDS - 60}, doctor.WARNING,
                 r"underway: the update's worker ended without saying how$"),
                ({**base, "outcome": "underway", "cause": "helper_crash", "detail": "KeyError: 'upgrade'"},
                 doctor.WARNING, r"underway \(KeyError: 'upgrade'\): the update's worker stopped with an error$")):
            with self.subTest(record=record):
                auto_update._keep(self.state / auto_update.RECORD, record)
                found = doctor._attempt()
                self.assertEqual(found[0], status, found[1])
                self.assertRegex(found[1], head.format(release=re.escape(record["release"])) + said)
                # Under a warning, the one line that says what to do, by its cause and who made the install.
                self.assertEqual(found[2:], ([auto_update.advice(auto_update.cause(record), "uv")],)
                                 if status == doctor.WARNING else ())
        log = self.state / auto_update.LOG
        log.write_text("cad's update, begun ...\n", encoding="utf-8")
        self.assertTrue(doctor._attempt()[1].endswith(f"; its log: {log}"))
        auto_update._keep(self.state / auto_update.RECORD, {**base, "outcome": "failed", "detail": "x",
                                                            "cause": "disk_full"})
        self.assertEqual(self.json_check("attempt")["status"], "warning")

    def json_check(self, name: str) -> dict:
        from cad_server.cli import doctor

        with mock.patch.object(doctor, "_probe_kernel", return_value=(doctor.KERNEL_OK, "/site/OCP.pyd")):
            code, out, _err = self.cli("--json", main=doctor.main)
        return next(check for check in json.loads(out)["checks"] if check["name"] == name)

    def test_doctor_warns_where_the_release_the_feed_names_has_had_its_tries_or_no_update_can_begin(self) -> None:
        from cad_server.cli import doctor

        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / updates.FILE).write_text(json.dumps({"checked": time.time(), "feed": {
            "latest": "0.2.0", "lines": {"0": "0.2.0"}}}), encoding="utf-8")
        now = time.time()
        when = lambda at: time.strftime("%Y-%m-%d %H:%M", time.localtime(at))  # noqa: E731
        base = {"release": "0.2.0", "wanted": "0.2.0", "from": "0.1.0", "at": now, "outcome": "failed",
                "detail": "uv said no", "installer": "uv"}
        auto_update._keep(self.state / auto_update.RECORD, {**base, "tries": 1, "outcome": "current",
                                                            "detail": "cad 0.2.0 is installed"})
        self.assertEqual(doctor._attempt(), (doctor.INFO, doctor._attempt()[1]), "one try: said, no warning")
        self.assertTrue(doctor._attempt()[1].endswith(
            f"; cad 0.2.0 has been tried 1 time by itself, and is tried again from {when(now + 3600)}: `cad update` "
            "tries it now"))
        auto_update._keep(self.state / auto_update.RECORD, {**base, "tries": 3, "cause": "unknown"})
        self.assertEqual(doctor._attempt(), (doctor.WARNING, doctor._attempt()[1], [auto_update.RETRIES]))
        self.assertTrue(doctor._attempt()[1].endswith(
            f": uv's output names no cause cad knows; cad 0.2.0 has been tried 3 times by itself, and is tried again "
            f"from {when(now + 4 * 3600)}: `cad update` tries it now"), "never given up on, each wait twice the last")
        auto_update._keep(self.state / auto_update.RECORD, {**base, "tries": 3, "at": now - 5 * 3600})
        self.assertIn("tried 3 times by itself, and is tried again at the next check", doctor._attempt()[1])
        (self.state / auto_update.RECORD).unlink()
        said = f"update auto on, plugin update auto off; a global install by uv ({self.tool})"
        self.assertEqual(doctor._update(), (doctor.INFO, said))
        with mock.patch.object(auto_update, "find_uv", return_value=None), \
                mock.patch.object(auto_update, "carried_uv", return_value=None):
            self.assertEqual(doctor._attempt(), (doctor.INFO, "none"), "no update can begin: the update line's")
            self.assertEqual(doctor._update(), (doctor.WARNING, f"{said}; uv cannot be found, so no update can begin",
                                                ["install uv (https://docs.astral.sh/uv/), then `cad update`"]))
        with mock.patch.object(store, "switches", return_value=False):
            self.assertEqual(doctor._update(), (doctor.WARNING, f"{said}; {auto_update.in_words('no_switch')}",
                                                ["install cad again: `uv tool install --force cad`"]))
            auto_update.change(False)
            self.assertEqual(doctor._update()[0], doctor.WARNING, "automatic updates off: cad update cannot either")
        self.assertEqual(doctor._attempt(), (doctor.INFO, "none"))

    def test_a_release_held_back_is_said_plainly_and_never_given_a_next_try(self) -> None:
        """A release whose last automatic try ended with its server not starting (``given_up``) is not tried again by
        itself: the attempt line says it is held back, never when it is tried next, and the line under it what to do."""
        from cad_server.cli import doctor

        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / updates.FILE).write_text(json.dumps({"checked": time.time(), "feed": {
            "latest": "0.2.0", "lines": {"0": "0.2.0"}}}), encoding="utf-8")
        auto_update._keep(self.state / auto_update.RECORD, {
            "release": "0.2.0", "wanted": "0.2.0", "from": "0.1.0", "at": time.time(), "tries": 1, "installer": "uv",
            "outcome": "failed", "cause": "start_failed", "restored": True, "detail": "cad 0.2.0 did not start: x"})
        self.assertTrue(auto_update.given_up("0.2.0", auto_update.tries()))
        status, said, more = doctor._attempt()
        self.assertEqual(status, doctor.WARNING)
        self.assertTrue(said.endswith("; cad 0.1.0 runs again; cad 0.2.0 has been tried 1 time by itself, and is held "
                                      "back: its server did not start, so cad waits for the next release"), said)
        self.assertNotIn("tried again", said)
        self.assertEqual(more, ["nothing to do: cad went back to the release before and takes the next release when it "
                                "is out; `cad update` tries this one again"])
        # Held back by an earlier try though the record is now another's (a typed try that ended otherwise).
        auto_update._keep(self.state / auto_update.TRIED, auto_update._kept(auto_update.tries()))
        auto_update._keep(self.state / auto_update.RECORD, {
            "release": "0.2.0", "wanted": "0.2.0", "from": "0.1.0", "at": time.time() + 1, "tries": 1,
            "installer": "uv", "asked": True, "outcome": "failed", "cause": "network", "detail": "uv said no"})
        status, said, more = doctor._attempt()
        self.assertIn("is held back", said)
        self.assertEqual(more, [auto_update.advice("start_failed")])

    def test_the_fix_check_is_there_only_where_something_is_wrong_and_says_the_one_thing_to_do(self) -> None:
        from cad_server.cli import doctor

        def fix() -> list:
            with mock.patch.object(doctor, "_probe_kernel", return_value=(doctor.KERNEL_OK, "/site/OCP.pyd")):
                _code, out, _err = self.cli("--json", main=doctor.main)
            checks = json.loads(out)["checks"]
            self.assertNotIn("fix", [check["name"] for check in checks[:-1]], "the last check alone")
            return [check for check in checks if check["name"] == "fix"]

        self.assertEqual(fix(), [], "all is well")
        auto_update._keep(self.state / auto_update.RECORD, {"release": "0.2.0", "from": "0.1.0", "at": time.time(),
                                                            "outcome": "failed", "cause": "disk_full", "detail": "x",
                                                            "installer": "uv"})
        self.assertEqual(fix(), [{"name": "fix", "status": "warning",
                                  "detail": "free room on the disk, then cad tries again by itself; `cad update` tries "
                                            "now"}])
        auto_update._keep(self.state / auto_update.RECORD, {"release": "0.2.0", "from": "0.0.9", "at": time.time(),
                                                            "outcome": "failed", "cause": "disk_full", "detail": "x"})
        self.assertEqual(fix(), [], "an attempt of another release is history")
        with mock.patch.object(store, "switches", return_value=False):
            self.assertEqual([found["detail"] for found in fix()], ["install cad again: `uv tool install --force cad`"])
        (self.state / auto_update.RECORD).unlink()
        # Behind for days by the rule of the line a command says: the record ``notice`` keeps, read, never written.
        (self.state / updates.FILE).write_text(json.dumps({"checked": time.time(), "feed": {
            "latest": "0.2.0", "lines": {"0": "0.2.0"}}}), encoding="utf-8")
        self.assertEqual(fix(), [], "never noted behind")
        self.assertFalse((self.state / auto_update.NOTICE).exists(), "the report writes nothing")
        auto_update._keep(self.state / auto_update.NOTICE, {"from": "0.1.0", "behind": "0.2.0",
                                                            "since": time.time() - auto_update.DAY})
        self.assertEqual(fix(), [], "behind for a day")
        auto_update._keep(self.state / auto_update.NOTICE, {"from": "0.1.0", "behind": "0.2.0",
                                                            "since": time.time() - auto_update.BEHIND_SECONDS})
        self.assertEqual([found["detail"] for found in fix()],
                         ["cad 0.2.0 is out and this cad has stayed behind it: `cad update` updates it"])
        auto_update.change(False)
        self.assertEqual(fix(), [], "automatic updates off: the release is the person's choice")

    def test_the_newest_line_says_when_the_feed_was_last_asked_for(self) -> None:
        from cad_server.cli import doctor

        for seconds, said in ((-5, ""), (0, " (asked less than a minute ago)"), (60, " (asked 1 minute ago)"),
                              (119 * 60, " (asked 119 minutes ago)"), (2 * 3600, " (asked 2 hours ago)"),
                              (47 * 3600, " (asked 47 hours ago)"), (3 * 86400 + 5, " (asked 3 days ago)")):
            with self.subTest(seconds=seconds):
                self.assertEqual(doctor._asked(1_000_000.0 - seconds, now=1_000_000.0), said)
        self.assertEqual(doctor._asked(None), "")
        self.assertIsNone(updates.asked(), "never asked on this computer")

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

    def test_two_servers_of_two_releases_taking_turns_never_set_each_other_s_count_back(self) -> None:
        """Two servers on one state folder, one of an earlier release left running beside the newer one (another
        engine folder, which no newer client reaches), and an app's step that fails at every run: each run of one
        release came between the other's, and when only the last run was kept, each server began a run at every
        tending, taking turns, with no end. Counted for each release: one run each in the hour, at most ``TRIES``
        each for good."""
        self.switch_on()
        self.catch_up.noted("0.0.9")
        servers = {"0.1.0": self.catch_up.Catcher(wait=0.0), "0.1.1": self.catch_up.Catcher(wait=0.0)}
        now = [1_000_000.0]
        with mock.patch.object(self.catch_up.subprocess, "Popen") as popen, mock.patch("time.time", lambda: now[0]):
            popen.return_value.poll.return_value = 0  # each run ends as soon as it began (below)
            begun: list[str] = []

            def tendings(count: int) -> None:
                for _ in range(count):
                    for release, catcher in servers.items():
                        with mock.patch.object(cad_server, "__version__", release):
                            if catcher.tend(self.told.append):
                                begun.append(release)
                                record = self.catch_up.read()
                                # The run is the installed cad's command, the newer one: its app failed again.
                                with mock.patch.object(cad_server, "__version__", "0.1.1"), \
                                        mock.patch.dict(os.environ, {self.catch_up.SERVER_ENV: str(record["at"])}):
                                    self.catch_up.ended(0, failed=True)
                        now[0] += 15.0  # each server tends every 30 seconds

            tendings(60)  # half an hour of tendings
            self.assertEqual(sorted(begun), ["0.1.0", "0.1.1"], "one run of each release in the hour, no more")
            for _ in range(10):
                now[0] += self.catch_up.RETRY_SECONDS
                tendings(4)
        self.assertEqual((begun.count("0.1.0"), begun.count("0.1.1")), (self.catch_up.TRIES, self.catch_up.TRIES))
        self.assertEqual(popen.call_count, 2 * self.catch_up.TRIES)
        self.assertEqual(self.catch_up.read()["tried"]["0.1.1"]["tries"], self.catch_up.TRIES)

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
        stand_in = types.SimpleNamespace(draining=False, stopping=threading.Event(), tidied=float("-inf"),
                                         catching=types.SimpleNamespace(tend=lambda told: calls.append("catch up")))
        with mock.patch.object(auto_update, "report", side_effect=lambda: calls.append("count")):
            Daemon.caught_up(stand_in)
            stand_in.stopping.set()
            Daemon.caught_up(stand_in)
        self.assertEqual(calls, ["catch up", "count"])


class NewestFirstTest(Case):
    """A person always gets the newest (``auto_update.begin``, ``_newest_first``): an automatic attempt that was only
    getting an older release ready when they asked for a newer one ends first, and theirs then installs the newer
    one and switches to it, never to the older."""

    def test_an_ask_for_a_newer_release_waits_for_an_older_one_getting_ready_then_asks_for_the_newer(self) -> None:
        getting_ready = {"release": "0.2.0", "outcome": "underway", "switch": False}
        states = [getting_ready, getting_ready, None]
        slept: list[float] = []
        with mock.patch.object(auto_update, "underway", side_effect=lambda: states.pop(0) if states else None), \
                mock.patch.object(auto_update.time, "sleep", side_effect=slept.append), \
                mock.patch.object(auto_update, "_start", return_value=(auto_update.BEGUN, {"release": "0.3.0"})) as start:
            found = auto_update.begin("0.3.0")
        self.assertEqual(found, {"release": "0.3.0"})
        self.assertEqual(len(slept), 2, "waited while the older one was still getting ready")
        self.assertEqual(start.call_args.args[0], "0.3.0", "then the newer one, asked by name")

    def test_no_wait_where_it_is_the_release_asked_for_a_whole_update_none_named_or_none_underway(self) -> None:
        cases = {"the same release": ("0.3.0", {"release": "0.3.0", "switch": False}),
                 "a whole update underway": ("0.3.0", {"release": "0.2.0", "switch": True}),
                 "PyPI named none": (auto_update.LATEST, {"release": "0.2.0", "switch": False}),
                 "nothing underway": ("0.3.0", None)}
        for name, (target, found) in cases.items():
            with self.subTest(case=name), mock.patch.object(auto_update, "underway", return_value=found), \
                    mock.patch.object(auto_update.time, "sleep", side_effect=AssertionError("no wait")), \
                    mock.patch.object(auto_update, "_start", return_value=(auto_update.UNDERWAY, {"release": "x"})):
                self.assertEqual(auto_update.begin(target), {"release": "x"})

    def test_the_wait_is_bounded_by_the_longest_a_release_takes_to_get_ready(self) -> None:
        from cad_server._internal import store

        clock = [0.0]
        def sleep(seconds: float) -> None:
            clock[0] += seconds
        stuck = {"release": "0.2.0", "switch": False}
        with mock.patch.object(auto_update, "underway", return_value=stuck):
            auto_update._newest_first("0.3.0", sleep=sleep, clock=lambda: clock[0])
        self.assertGreaterEqual(clock[0], store.BUILD_SECONDS + store.VERIFY_SECONDS)
        self.assertLess(clock[0], store.BUILD_SECONDS + store.VERIFY_SECONDS + 61.0, "then the ask goes on")


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
        base = {"earlier": "0.1.0", "reason": None, "tries": 1, "installer": "uv", "asked": False, "plugin": "none",
                "cause": None}
        for fields, made in (
                ({}, {"outcome": "installed"}),
                ({"outcome": "current"}, {"outcome": "current", "cause": "none"}),
                ({"outcome": "current", "cause": "unknown"}, {"outcome": "current", "cause": "unknown"}),
                ({"outcome": "current", "detail": "cad 0.2.0 is installed"}, {"outcome": "current", "cause": "already"}),
                ({"outcome": "failed", "detail": "uv said no", "tries": 2, "cause": "disk_full"},
                 {"outcome": "failed", "reason": "upgrade", "tries": 2, "cause": "disk_full"}),
                ({"outcome": "failed", "detail": "it built cad 0.0.9, which it may not end on"},
                 {"outcome": "failed", "reason": "older", "cause": "none"}),
                # a release before's `--major` that did not cross: a newer release than the one that ran, never `older`
                ({"outcome": "failed", "detail": "it installed 0.1.5, not 1.0.0", "major": True},
                 {"outcome": "failed", "reason": "upgrade", "cause": "none"}),
                ({"outcome": "failed", "restored": True, "cause": "network"},
                 {"outcome": "restored", "reason": "upgrade", "cause": "network"}),
                ({"outcome": "failed", "restored": False}, {"outcome": "failed", "reason": "put_back", "cause": "none"}),
                ({"outcome": "failed", "cause": "helper_start"}, {"outcome": "failed", "reason": "upgrade",
                                                                  "cause": "helper_start"}),
                ({"asked": True, "installer": "pipx"}, {"outcome": "installed", "asked": True, "installer": "pipx"}),
                ({"installer": None, "asked": None}, {"outcome": "installed"}),  # kept before it named them: this cad's
                # Still underway past its hour: its helper died, with a word or without one.
                ({"outcome": "underway", "tries": 2, "asked": True}, {"outcome": "lost", "tries": 2, "asked": True,
                                                                      "cause": "lost"}),
                ({"outcome": "underway", "cause": "helper_crash"}, {"outcome": "lost", "cause": "helper_crash"}),
        ):
            with self.subTest(fields=fields):
                self.assertEqual(auto_update.event(self.ended(**fields)), {**base, **made})
        self.assertIsNone(auto_update.event({"release": "0.2.0", "at": time.time(), "outcome": "underway"}), "not ended")
        self.assertIsNone(auto_update.event({"release": "0.2.0", "at": time.time(), "outcome": "underway",
                                             "cause": "helper_crash"}), "held for its hour as any attempt underway")

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
                                        asked=False, plugin="underway", cause=None)
        from cad_server import analytics

        self.assertEqual(analytics._update_event("0.1.0", "installed", None, 1, "uv", False, "underway")["plugin"],
                         "underway", "a word the sender keeps and sends")
        self.assertIsNone(analytics._update_event("0.1.0", "current", None, 1, "uv", False, "underway"))

    def test_the_sender_keeps_every_cause_of_each_outcome_and_no_other_word(self) -> None:
        """``cause`` (schema 13's) on every outcome but ``installed``, a word of that outcome's (``UPDATE_CAUSES``);
        none given, ``none`` (an update a release before it kept). Every word an attempt's record keeps is sent for
        one outcome or another."""
        from cad_server import analytics

        def made(outcome: str, cause: object) -> dict | None:
            return analytics._update_event("0.1.0", outcome, "upgrade" if outcome in ("failed", "restored") else None,
                                           0 if outcome == "blocked" else 1, "uv", False, "none", cause)

        for outcome in sorted(analytics.UPDATE_OUTCOMES - {"installed"}):
            for cause in sorted(set().union(*analytics.UPDATE_CAUSES.values())):
                with self.subTest(outcome=outcome, cause=cause):
                    found = made(outcome, cause)
                    self.assertEqual(found is not None, cause in analytics.UPDATE_CAUSES[outcome])
                    if found is not None:
                        self.assertEqual(found["cause"], cause)
            for word in ("eaccess", "Failed to fetch: https://pypi.org/simple/cad/", "", 7, True, "NETWORK"):
                self.assertIsNone(made(outcome, word), (outcome, word))
        self.assertEqual(made("failed", None)["cause"], "none")
        self.assertIsNone(made("lost", None), "a lost attempt always says which")
        self.assertNotIn("cause", made("installed", None))
        self.assertIsNone(made("installed", "network"), "an update that installed a newer cad names none")
        self.assertEqual(set().union(*analytics.UPDATE_CAUSES.values()) - {"already", "none"}, set(helper.CAUSES))

    def test_counted_once_and_marked_so(self) -> None:
        self.ended(outcome="failed", detail="uv said no", restored=True)
        with mock.patch("cad_server.analytics.update") as counted:
            self.assertTrue(auto_update.report())
            self.assertFalse(auto_update.report(), "once")
        counted.assert_called_once_with(earlier="0.1.0", outcome="restored", reason="upgrade", tries=1,
                                        installer="uv", asked=False, plugin="none", cause="none")
        self.assertTrue(auto_update.last()["reported"])
        auto_update._keep(self.state / auto_update.RECORD, {"release": "0.2.0", "at": time.time(), "outcome": "underway"})
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
                                        installer="uv", asked=False, plugin="none", cause="none")
        self.assertEqual((auto_update.last()["release"], auto_update.last()["outcome"]), ("0.2.1", "underway"))

    def test_an_attempt_that_never_said_how_it_ended_is_counted_lost_once_past_its_hour(self) -> None:
        """Its helper died: the record stays underway. Held for its hour as any attempt underway, then counted once,
        ``lost``, by the server or by the attempt that takes its place."""
        now = time.time()
        auto_update._keep(self.state / auto_update.RECORD, {"release": "0.2.0", "wanted": "0.2.0", "from": "0.1.0",
                                                            "at": now, "tries": 1, "outcome": "underway",
                                                            "installer": "uv", "asked": False})
        with mock.patch("cad_server.analytics.update") as counted:
            self.assertFalse(auto_update.report(), "underway")
            with mock.patch.object(auto_update.time, "time", return_value=now + auto_update.RETRY_SECONDS):
                self.assertTrue(auto_update.report())
                self.assertFalse(auto_update.report(), "once")
        counted.assert_called_once_with(earlier="0.1.0", outcome="lost", reason=None, tries=1, installer="uv",
                                        asked=False, plugin="none", cause="lost")
        self.assertEqual(auto_update.last()["outcome"], "underway", "the record kept as it was, marked counted")
        auto_update._keep(self.state / auto_update.RECORD, {"release": "0.2.0", "wanted": "0.2.0", "from": "0.1.0",
                                                            "at": now - auto_update.RETRY_SECONDS, "tries": 1,
                                                            "outcome": "underway", "cause": "helper_crash",
                                                            "installer": "uv"})
        with mock.patch("cad_server.analytics.update") as counted, \
                mock.patch.object(auto_update.subprocess, "Popen"), \
                mock.patch.object(sys, "_base_executable", str(self.tmp / "python3"), create=True):
            self.assertTrue(auto_update.trigger("0.2.1", automatic=False))
        counted.assert_called_once_with(earlier="0.1.0", outcome="lost", reason=None, tries=1, installer="uv",
                                        asked=False, plugin="none", cause="helper_crash")


class BlockedCountTest(Case):
    """An automatic update that is due and cannot begin (``auto_update.blocked``) counted once for each release the
    feed calls for, from the release that runs (``auto_update._blocked``): ``blocked``, its cause, no try made."""

    def test_counted_once_for_each_release_and_never_where_none_is_due(self) -> None:
        missing = (mock.patch.object(auto_update, "find_uv", return_value=None),
                   mock.patch.object(auto_update, "carried_uv", return_value=None))
        with missing[0], missing[1], mock.patch("cad_server.analytics.update") as counted:
            with self.feed("0.1.0"):
                self.assertIsNone(auto_update.due(), "nothing newer: none due, none counted")
            counted.assert_not_called()
            with mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.state)}):
                auto_update.change(False)
                with self.feed("0.2.0"):
                    self.assertIsNone(auto_update.due(), "off: no update is due, so none is blocked")
                auto_update.change(True)
            counted.assert_not_called()
            with self.feed("0.2.0"):
                for _ in range(3):
                    self.assertIsNone(auto_update.due())
                    self.assertIsNone(auto_update.due(fetch=True))
            counted.assert_called_once_with(earlier="0.1.0", outcome="blocked", tries=0, installer="uv", asked=False,
                                            cause="no_installer")
            kept = json.loads((self.state / auto_update.BLOCKED).read_text(encoding="utf-8"))
            self.assertEqual((kept["from"], kept["wanted"], kept["cause"]), ("0.1.0", "0.2.0", "no_installer"))
            with self.feed("0.2.1"):
                self.assertIsNone(auto_update.due())
                self.assertIsNone(auto_update.due())
            self.assertEqual(counted.call_count, 2, "once more for a newer release")
        self.assertFalse((self.state / auto_update.RECORD).exists(), "no attempt: nothing kept of one")
        with mock.patch("cad_server.analytics.update") as counted, self.feed("0.2.2"), \
                mock.patch.object(store, "switches", return_value=False):
            self.assertIsNone(auto_update.due())
        counted.assert_called_once_with(earlier="0.1.0", outcome="blocked", tries=0, installer="uv", asked=False,
                                        cause="no_switch")
        with mock.patch("cad_server.analytics.update") as counted, self.feed("0.2.3"):
            self.assertEqual(auto_update.due(), auto_update.Due("0.2.3", "0.2.3"), "one that can begin is due")
        counted.assert_not_called()

    def test_the_count_is_one_the_sender_keeps(self) -> None:
        from cad_server import analytics

        self.assertIsNotNone(analytics._update_event("0.1.0", "blocked", None, 0, "uv", False, "none", "no_switch"))
        self.assertIsNone(analytics._update_event("0.1.0", "blocked", None, 1, "uv", False, "none", "no_switch"))


class StartFailedRuleTest(Case):
    """A release whose last automatic try ended with its server not starting (``start_failed``: the release before
    runs again) is not tried again by itself; every other cause follows the schedule, and a typed update tries it."""

    def test_a_server_that_did_not_start_holds_its_release_back_from_the_automatic_update_alone(self) -> None:
        now = 1_000_000.0
        with self.feed("0.2.0", {"0": "0.2.0"}), mock.patch.object(auto_update.subprocess, "Popen"):
            for cause, due in (("start_failed", None), ("broken", auto_update.Due("0.2.0", "0.2.0")),
                               ("network", auto_update.Due("0.2.0", "0.2.0"))):
                with self.subTest(cause=cause):
                    (self.state / auto_update.TRIED).unlink(missing_ok=True)
                    auto_update._keep(self.state / auto_update.RECORD, {
                        "release": "0.2.0", "wanted": "0.2.0", "from": "0.1.0", "at": now, "tries": 1,
                        "outcome": "failed", "cause": cause, "restored": True, "reported": True})
                    self.assertEqual(auto_update.due(now=now + 2 * auto_update.DAY), due)
                    self.assertEqual(auto_update.given_up("0.2.0", auto_update.tries(now)), due is None)
            said, _kept = auto_update._claim(release="0.2.0", wanted="0.2.0", version="0.1.0", installer="uv",
                                             automatic=True)
            self.assertEqual(said, auto_update.BEGUN, "the last cause network: begun")
            auto_update._keep(self.state / auto_update.RECORD, {**auto_update.last(), "outcome": "failed",
                                                                "cause": "start_failed", "reported": True})
            self.assertEqual(auto_update._claim(release="0.2.0", wanted="0.2.0", version="0.1.0", installer="uv",
                                                automatic=True), (auto_update.NOT_YET, {}),
                             "asked again in the step that begins one")
            self.assertEqual(auto_update.begin("0.2.0")["outcome"], "underway", "`cad update` tries it")
        with self.feed("0.2.1", {"0": "0.2.1"}):
            self.assertEqual(auto_update.due(now=time.time() + 2 * auto_update.DAY), auto_update.Due("0.2.1", "0.2.1"),
                             "the next release is tried by itself")

    def test_a_person_s_own_update_that_ended_so_holds_the_release_back_as_an_automatic_try_does(self) -> None:
        """A typed update spends no try, and what it showed stands all the same: the server restored a moment ago is
        not stopped again for the same release."""
        now = 1_000_000.0
        typed = {"release": "0.2.0", "wanted": "0.2.0", "from": "0.1.0", "at": now, "tries": 1, "asked": True,
                 "outcome": "failed", "cause": "start_failed", "restored": True, "reported": True}
        with self.feed("0.2.0", {"0": "0.2.0"}), mock.patch.object(auto_update.subprocess, "Popen"):
            auto_update._keep(self.state / auto_update.RECORD, typed)
            book = auto_update.tries(now + 2)
            self.assertEqual(book["tried"]["0.2.0"], {"tries": 0, "first": now, "at": now, "cause": "start_failed"},
                             "no try spent")
            self.assertTrue(auto_update.given_up("0.2.0", book))
            self.assertIsNone(auto_update.due(now=now + 2), "not two seconds later")
            self.assertIsNone(auto_update.due(now=now + 2 * auto_update.DAY), "nor days later")
            self.assertIsNone(auto_update.waiting(now=now + 2), "never tried by itself: no next try to name")
            # Its automatic tries before stand as they were, and the cause is the release's now.
            auto_update._keep(self.state / auto_update.TRIED, {"tried": {"0.2.0": {
                "tries": 2, "first": now - 9000, "at": now - 5000, "cause": "network"}}, "recent": [], "seen": now - 5000})
            self.assertEqual(auto_update.tries(now + 2)["tried"]["0.2.0"],
                             {"tries": 2, "first": now - 9000, "at": now - 5000, "cause": "start_failed"})
            # Any other cause of a person's update changes nothing of the automatic one's.
            auto_update._keep(self.state / auto_update.RECORD, {**typed, "cause": "network"})
            self.assertFalse(auto_update.given_up("0.2.0", auto_update.tries(now + 2)))
            # Kept past the record: the next attempt, of whatever release, writes the tries with it.
            auto_update._keep(self.state / auto_update.RECORD, typed)
            (self.state / auto_update.TRIED).unlink()
            self.assertEqual(auto_update.begin("0.2.0")["outcome"], "underway", "`cad update` tries it again")
            kept = json.loads((self.state / auto_update.TRIED).read_text(encoding="utf-8"))
            self.assertEqual(kept["tried"]["0.2.0"]["cause"], "start_failed")


class NoticeTest(Case):
    """A global install with automatic updates on that has stayed behind a release of its own major for three days
    says so in one line on stderr after a command's own output, at most once a day (``auto_update.notice``, said by
    ``cad_server.cli``): never where cad is current, automatic updates are off, an update is underway, or a release
    came out less than three days ago; never on stdout; nothing where its record cannot be written. A clock of the
    test's own (``now=``)."""

    T0 = 1_000_000.0

    def notice(self, at: float) -> str | None:
        return auto_update.notice(now=self.T0 + at)

    def kept(self) -> dict:
        return json.loads((self.state / auto_update.NOTICE).read_text(encoding="utf-8"))

    def test_noted_first_said_three_days_later_and_then_once_a_day(self) -> None:
        day = auto_update.DAY
        line = "cad: cad 0.2.0 is out and this is 0.1.0: `cad update` updates it"
        with self.feed("0.2.0", {"0": "0.2.0"}):
            self.assertIsNone(self.notice(0), "the first time only the time is noted")
            self.assertEqual(self.kept(), {"from": "0.1.0", "behind": "0.2.0", "since": self.T0})
            for at in (60.0, day, 3 * day - 1):
                self.assertIsNone(self.notice(at), at)
            self.assertEqual(self.notice(3 * day), line)
            self.assertEqual(self.kept()["said"], self.T0 + 3 * day)
            self.assertIsNone(self.notice(3 * day + 1), "not within a day of the last time")
            self.assertIsNone(self.notice(4 * day - 1))
            self.assertEqual(self.notice(4 * day), line)
            self.assertEqual(self.notice(3.5 * day), line, "said later than now (a clock set back): long ago")
        with self.feed("0.2.1", {"0": "0.2.1"}):
            self.assertEqual(self.notice(5 * day), "cad: cad 0.2.1 is out and this is 0.1.0: `cad update` updates it",
                             "a newer release out meanwhile: behind all the same, since the first time")
        with self.feed("0.1.0", {"0": "0.1.0"}):
            self.assertIsNone(self.notice(6 * day), "current")
            self.assertFalse((self.state / auto_update.NOTICE).exists(), "afresh once current")
        with self.feed("0.2.0", {"0": "0.2.0"}):
            self.assertIsNone(self.notice(7 * day), "a release behind starts afresh")
            self.assertIsNone(self.notice(9 * day), "a healthy computer: a release out two days, nothing said")

    def test_a_cad_updated_since_starts_afresh(self) -> None:
        with self.feed("0.3.0", {"0": "0.3.0"}):
            auto_update._keep(self.state / auto_update.NOTICE, {"from": "0.0.9", "behind": "0.1.0", "since": 0.0})
            self.assertIsNone(self.notice(0))
            self.assertEqual(self.kept()["since"], self.T0)
            auto_update._keep(self.state / auto_update.NOTICE, {"from": "0.1.0", "behind": "0.3.0",
                                                                "since": self.T0 + auto_update.DAY})
            self.assertIsNone(self.notice(0), "noted in the future (a clock set back): noted again, nothing said")
            self.assertEqual(self.kept()["since"], self.T0)

    def test_each_situation_s_line_names_both_releases_why_and_one_command(self) -> None:
        later = 3 * auto_update.DAY
        record = {"release": "0.2.0", "wanted": "0.2.0", "from": "0.1.0", "at": self.T0, "tries": 1,
                  "installer": "uv", "outcome": "failed", "cause": "disk_full", "detail": "x"}
        with self.feed("0.2.0", {"0": "0.2.0"}):
            for situation, setup, line in (
                    ("failed", lambda: auto_update._keep(self.state / auto_update.RECORD, record),
                     "cad: this cad is 0.1.0 and has not been able to update itself to 0.2.0 (the disk is full): "
                     "free room on the disk, then cad tries again by itself; `cad update` tries now"),
                    ("lost", lambda: auto_update._keep(self.state / auto_update.RECORD, {
                        **record, "outcome": "underway", "cause": None, "at": self.T0 - 2 * auto_update.LOST_SECONDS,
                        "beat": self.T0 - 2 * auto_update.LOST_SECONDS}),
                     "cad: this cad is 0.1.0 and has not been able to update itself to 0.2.0 (the update's worker "
                     "ended without saying how): cad tries again by itself; `cad update` tries now"),
                    ("another release's attempt", lambda: auto_update._keep(self.state / auto_update.RECORD, {
                        **record, "from": "0.0.9"}),
                     "cad: cad 0.2.0 is out and this is 0.1.0: `cad update` updates it")):
                with self.subTest(situation):
                    (self.state / auto_update.NOTICE).unlink(missing_ok=True)
                    setup()
                    self.assertIsNone(self.notice(0))
                    self.assertEqual(self.notice(later), line)
            (self.state / auto_update.RECORD).unlink()
            for word, patch, line in (
                    ("no_installer", mock.patch.object(auto_update, "find_uv", return_value=None),
                     "cad: this cad is 0.1.0 and cannot update itself to 0.2.0 (uv cannot be found, so no update can "
                     "begin): install uv (https://docs.astral.sh/uv/), then `cad update`"),
                    ("no_switch", mock.patch.object(store, "switches", return_value=False),
                     f"cad: this cad is 0.1.0 and cannot update itself to 0.2.0 ({auto_update.in_words('no_switch')}): "
                     "install cad again: `uv tool install --force cad`")):
                with self.subTest(word), patch:
                    (self.state / auto_update.NOTICE).unlink(missing_ok=True)
                    self.assertIsNone(self.notice(0))
                    self.assertEqual(self.notice(later), line)

    def test_never_where_off_current_underway_or_no_global_install(self) -> None:
        later = 3 * auto_update.DAY
        auto_update._keep(self.state / auto_update.NOTICE, {"from": "0.1.0", "behind": "0.2.0", "since": self.T0})
        before = self.kept()
        with self.feed("0.2.0", {"0": "0.2.0"}):
            auto_update.change(False)
            self.assertIsNone(self.notice(later), "automatic updates off: the release is the person's choice")
            auto_update.change(True)
            with mock.patch.object(updates, "checking", return_value=False):
                self.assertIsNone(self.notice(later), "the check turned off for this process")
            auto_update._keep(self.state / auto_update.RECORD, {
                "release": "0.2.0", "wanted": "0.2.0", "from": "0.1.0", "at": self.T0 + later, "tries": 1,
                "outcome": "underway", "beat": self.T0 + later, "phase": "building"})
            self.assertIsNone(self.notice(later), "an update underway")
            (self.state / auto_update.RECORD).unlink()
            receipt = self.tool / "uv-receipt.toml"
            receipt.unlink()
            self.assertIsNone(self.notice(later), "no global install")
            receipt.write_text(RECEIPT, encoding="utf-8")
            self.assertEqual(self.kept(), before, "none of them wrote anything")
            with mock.patch.object(auto_update, "_keep", side_effect=OSError("read-only")):
                self.assertIsNone(self.notice(later), "a record it cannot write: nothing said, so never every command")
            self.assertTrue(self.notice(later))
        with self.feed("1.0.0", {"1": "1.0.0"}):
            self.assertIsNone(self.notice(later + 2 * auto_update.DAY), "a higher major never makes cad behind")
        with self.feed(None):
            self.assertIsNone(self.notice(later + 3 * auto_update.DAY), "no feed read yet")
        with mock.patch.object(auto_update, "switches", side_effect=RuntimeError("x")):
            self.assertIsNone(self.notice(later), "never raises")

    def run_cad(self, *argv: str) -> tuple[int, str, str]:
        from cad_server import cli

        return self.cli(*argv, main=cli.main)

    def test_a_command_says_it_on_stderr_after_its_output_and_never_where_it_should_not(self) -> None:
        auto_update._keep(self.state / auto_update.NOTICE, {"from": "0.1.0", "behind": "0.2.0",
                                                            "since": time.time() - auto_update.BEHIND_SECONDS - 60})
        line = "cad: cad 0.2.0 is out and this is 0.1.0: `cad update` updates it"
        cache = Path(os.environ.get("CAD_CACHE_DIR") or self.tmp / "cache")
        with self.feed("0.2.0", {"0": "0.2.0"}), mock.patch.dict(os.environ, {"CAD_CACHE_DIR": str(cache)}):
            from cad.engine.places import installation

            code, out, err = self.run_cad("--version")
            self.assertEqual((code, out), (0, f"cad {installation()}\n"))
            self.assertNotIn(line, err)
            for argv in (("cache", "dir", "--help"), ("cache", "dir", "--json"), ("doctor",), ("update", "auto", "status"),
                         ("telemetry",), ("requirement",)):
                with self.subTest(argv=argv), mock.patch("cad_server.cli.doctor._probe_kernel",
                                                         return_value=("ok", "/site/OCP.pyd")):
                    _code, out, err = self.run_cad(*argv)
                    self.assertNotIn(line, out + err)
            with mock.patch("cad_server.analytics.stdout_closed", return_value=True):
                self.assertNotIn(line, self.run_cad("cache", "dir")[2], "its output's reader gone")
            code, out, err = self.run_cad("cache", "dir")
            self.assertEqual((code, out), (0, f"{cache}\n"), "never on stdout")
            self.assertEqual(err.splitlines()[-1], line, "the last line on stderr, after the command's output")
            self.assertNotIn(line, self.run_cad("cache", "dir")[2], "once a day")
        auto_update._keep(self.state / auto_update.NOTICE, {**json.loads(
            (self.state / auto_update.NOTICE).read_text(encoding="utf-8")), "said": 0.0})
        with self.feed("0.2.0", {"0": "0.2.0"}):
            code, out, err = self.run_cad("cache", "nope")
            self.assertEqual((code, out), (2, ""))
            self.assertEqual(err.splitlines()[-1], line, "whatever the command's exit status")


class SwitchingTest(Case):
    """While the worker switches releases (its record's ``phase``), a ``cad`` command that finds no server, or one
    older than its own release, waits for the next (``client.SWITCHING``); not otherwise, and never past
    ``SWITCH_SECONDS``."""

    def keep(self, **fields) -> None:
        now = time.time()
        auto_update._keep(self.state / auto_update.RECORD, {"release": "0.2.0", "wanted": "0.2.0", "from": "0.1.0",
                                                            "at": now, "beat": now, "tries": 1,
                                                            "outcome": "underway", **fields})

    def test_switching_is_the_attempt_underway_in_its_switching_phase(self) -> None:
        self.assertFalse(auto_update.switching(), "no record")
        self.keep(phase="building")
        self.assertFalse(auto_update.switching())
        self.keep(phase="switching")
        self.assertTrue(auto_update.switching())
        self.keep(phase="restoring")
        self.assertTrue(auto_update.switching(), "on the way back the release before is the one to wait for")
        self.keep(phase="switching", outcome="installed")
        self.assertFalse(auto_update.switching(), "ended")
        self.keep(phase="switching", beat=time.time() - auto_update.LOST_SECONDS)
        self.assertFalse(auto_update.switching(), "lost: no longer believed")
        (self.state / auto_update.RECORD).write_text("not json", encoding="utf-8")
        self.assertFalse(auto_update.switching())

    def test_a_server_of_the_release_being_left_starts_none_while_the_update_switches(self) -> None:
        """``leaving``: between the server the update stopped and the next release's, a start of the release being
        left would take the next one's place, and be taken for the server the update waits to see gone."""
        from cad_server.engine import daemon

        self.assertFalse(auto_update.leaving(), "no record")
        self.keep(phase="building")
        self.assertFalse(auto_update.leaving(), "nothing has stopped yet")
        self.keep(phase="switching")
        self.assertTrue(auto_update.leaving(), "this release (0.1.0) is the one being left")
        with mock.patch.object(cad_server, "__version__", "0.2.0"):
            self.assertFalse(auto_update.leaving(), "the next release's server is the one to start")
        self.keep(phase="restoring")
        self.assertFalse(auto_update.leaving(), "on the way back the release before starts again")
        self.keep(phase="switching", beat=time.time() - auto_update.LEAVING_SECONDS - 1)
        self.assertFalse(auto_update.leaving(), "a worker that died holds no start back for long")
        self.keep(phase="switching", outcome="installed")
        self.assertFalse(auto_update.leaving(), "ended")
        (self.state / auto_update.RECORD).write_text("not json", encoding="utf-8")
        self.assertFalse(auto_update.leaving())
        # The server's start: none while leaving, and nothing taken; as ever otherwise.
        self.keep(phase="switching")
        err = io.StringIO()
        with mock.patch.object(daemon, "lock", side_effect=AssertionError("no lock is taken")), redirect_stderr(err):
            self.assertEqual(daemon.main([]), 0, "left at once, as where another daemon is up")
            self.assertEqual(err.getvalue(), "", "detached: nothing said")
            self.assertEqual(daemon.main([], foreground=True), 0)
        self.assertIn("cad is updating itself", err.getvalue())
        self.keep(phase="restoring")
        with mock.patch.object(daemon, "lock", return_value=None) as lock:  # another daemon holds it: left as ever
            self.assertEqual(daemon.main([]), 0)
        lock.assert_called_once()
        with mock.patch.object(auto_update, "leaving", side_effect=RuntimeError("unreadable")), \
                mock.patch.object(daemon, "lock", return_value=None) as lock:
            self.assertEqual(daemon.main([]), 0, "what cannot be told is no reason not to start")
        lock.assert_called_once()

    def test_the_cad_command_sets_the_hook_where_it_holds_its_release(self) -> None:
        from cad_server import cli

        fake = types.SimpleNamespace(RELEASE=None, SWITCHING=None, LEAVING=None)
        cli._hold_to_release(fake)
        self.assertEqual((fake.RELEASE, fake.SWITCHING, fake.LEAVING), (version(), auto_update.switching, None))
        # Every command's client stands by for the update's switch, the server's own too: they start servers.
        cli._stand_by(fake)
        self.assertIs(fake.LEAVING, auto_update.leaving)

    def start(self, looks: list, *, leaving: list, exits: list) -> tuple[object, int]:
        """``client.start`` with stand-ins: ``looks``, the server that answers at each look (None: none; the last
        stays); ``leaving``, what the hook says at each ask (the last stays); ``exits``, how each daemon launched
        has left by the time it is asked (None: it runs on). What it returned or raised, and how many it launched.
        Each look is half a second of the clock."""
        clock, launched = [0.0], []
        answers, says = iter(looks), iter(leaving)
        last, said = [None], [False]

        def connect_(*_args, **_kwargs):
            last[0] = next(answers, last[0])
            return None if last[0] is None else mock.Mock(release=last[0])

        def leaving_() -> bool:
            said[0] = next(says, said[0])
            return said[0]

        def spawn(_port):
            launched.append(mock.Mock(poll=mock.Mock(return_value=exits[min(len(launched), len(exits) - 1)])))
            return launched[-1]

        note = self.state / "failure.json"  # none is left: a daemon that leaves badly is said by its exit status
        note.parent.mkdir(parents=True, exist_ok=True)
        with mock.patch.object(client, "make_way", return_value=None), \
                mock.patch.object(client.places, "make_engine_dir"), \
                mock.patch.object(client.places, "folder_refusal", return_value=None), \
                mock.patch.object(client.places, "failure_path", return_value=note), \
                mock.patch.object(client, "_spawn", side_effect=spawn), \
                mock.patch.object(client, "_connect", side_effect=connect_), \
                mock.patch.object(client, "_another_s", return_value=False), \
                mock.patch.object(client, "LEAVING", leaving_), \
                mock.patch.object(client.time, "monotonic", side_effect=lambda: clock[0]), \
                mock.patch.object(client.time, "sleep", side_effect=lambda _s: clock.__setitem__(0, clock[0] + 0.5)):
            try:
                return client.start(), len(launched)
            except ConnectionError as error:
                return error, len(launched)

    def test_a_start_launches_nothing_while_the_update_switches_away_and_waits_for_its_server(self) -> None:
        """``client.start`` while ``leaving``: the next server is the update's to start. A daemon launched then runs
        whichever release the pointer names at that instant, and one of a release whose server does not start would
        fail the start a moment before the update goes back."""
        mine = version()
        # The daemon launched stood aside (it left at once, well); the update's server answers ten looks on: nothing
        # more was launched in those five seconds, and the start says cad updated itself.
        said, launched = self.start([None] * 10 + ["99.0.0"], leaving=[True], exits=[0])
        self.assertEqual((said, launched), (f"started the cad server (cad 99.0.0): cad updated itself from {mine} as "
                                            "the server started", 1))
        # A daemon that left badly during the switch (it ran the release that does not start) is no failure of this
        # start: the update went back, and the release before answers.
        said, launched = self.start([None] * 6 + [mine], leaving=[True] * 4 + [False], exits=[1])
        self.assertEqual(launched, 1, "the update's own start of the release before answered first")
        self.assertIn(f"(cad {mine})", str(said))
        self.assertNotIsInstance(said, ConnectionError)
        # The switch ended and left no server: a second later, and not before, this start launches its own again,
        # however the one before left; that one is judged as any is.
        said, launched = self.start([None] * 9 + [mine], leaving=[True] * 3 + [False], exits=[1, None])
        self.assertEqual((said, launched), (f"started the cad server (cad {mine})", 2))
        said, launched = self.start([None], leaving=[True] * 3 + [False], exits=[0, 1])
        self.assertEqual((str(said), launched), ("the engine server did not start: it exited with code 1", 2))
        # With no switch, as ever: a daemon that left badly is said at once, one that left well is launched again a
        # second on, and a newer server that answers was another start's.
        said, launched = self.start([None], leaving=[False], exits=[1])
        self.assertEqual((str(said), launched), ("the engine server did not start: it exited with code 1", 1))
        said, launched = self.start([None] * 5 + [mine], leaving=[False], exits=[0, None])
        self.assertEqual((said, launched), (f"started the cad server (cad {mine})", 2))
        said, launched = self.start([None, "99.0.0"], leaving=[False], exits=[None])
        self.assertEqual((said, launched), (f"the cad server (cad 99.0.0, newer than this cad {mine}) is already running", 1))
        # A hook that fails is no switch, and neither is none.
        def broken() -> bool:
            raise OSError("the state folder is refused")

        with mock.patch.object(client, "LEAVING", broken):
            self.assertFalse(client._leaving())  # noqa: SLF001
        with mock.patch.object(client, "LEAVING", None):
            self.assertFalse(client._leaving())  # noqa: SLF001

    def connect(self, answers: list, *, switching, release: str | None = "0.2.0", seconds: float = 5.0):
        """``client.connect`` with the servers that answer one look after another (the last stays) and the hook."""
        looks = iter(answers)
        last: list = [None]

        def connect_(*_args, **_kwargs):
            last[0] = next(looks, last[0])
            return None if last[0] is None else mock.Mock(release=last[0])

        with mock.patch.object(client, "RELEASE", release), mock.patch.object(client, "AT_LEAST", None), \
                mock.patch.object(client, "SWITCHING", switching), mock.patch.object(client, "SWITCH_SECONDS", seconds), \
                mock.patch.object(client, "_connect", side_effect=connect_) as dialled, \
                mock.patch.object(client.time, "sleep"):
            try:
                return client.connect(), dialled.call_count
            except ConnectionError as error:
                return error, dialled.call_count

    def test_a_command_waits_for_the_update_s_server_while_it_switches_and_not_otherwise(self) -> None:
        found, looks = self.connect([None, None, "0.2.0"], switching=lambda: True)
        self.assertEqual((found.release, looks), ("0.2.0", 3), "none, then the update's")
        found, looks = self.connect(["0.1.0", "0.1.0", "0.2.0"], switching=lambda: True)
        self.assertEqual((found.release, looks), ("0.2.0", 3), "the older one still going, then the update's")
        found, looks = self.connect([None], switching=lambda: False)
        self.assertEqual((type(found), looks), (client.NotRunning, 1), "no switch: said at once")
        found, looks = self.connect(["0.1.0"], switching=None)
        self.assertEqual((type(found), looks), (client.OtherRelease, 1), "no hook: as ever")
        found, looks = self.connect(["0.3.0"], switching=lambda: True)
        self.assertEqual((type(found), looks), (client.OtherRelease, 1), "a newer server is never waited on")
        ended = iter([True, True, False])
        found, looks = self.connect([None], switching=lambda: next(ended))
        self.assertEqual((type(found), looks), (client.NotRunning, 3), "the switch ended: whatever answers then")
        found, _looks = self.connect([None], switching=lambda: True, seconds=0.0)
        self.assertIs(type(found), client.NotRunning, "never past its bound")

        def broken() -> bool:
            raise OSError("the state folder is refused")

        found, looks = self.connect([None], switching=broken)
        self.assertEqual((type(found), looks), (client.NotRunning, 1), "a hook that fails is no switch")

    def test_a_command_of_the_release_before_that_meets_the_one_after_says_so_in_one_line(self) -> None:
        from cad_server._internal.cli_errors import classify

        error = client.OtherRelease.met("0.2.0", "0.1.0")
        self.assertEqual((error.theirs, error.mine), ("0.2.0", "0.1.0"))
        with mock.patch.object(store, "active", return_value="0.2.0"):
            failure = classify(error)
        self.assertEqual((str(failure), failure.reason, failure.next),
                         ("cad updated itself to 0.2.0 while this command ran: run it again", "other_release", ()))
        for theirs, active in (("0.2.0", "0.1.0"), ("0.0.9", "0.0.9"), (None, None)):
            with self.subTest(theirs=theirs), mock.patch.object(store, "active", return_value=active):
                failure = classify(client.OtherRelease.met(theirs, "0.1.0"))
                self.assertEqual((str(failure), failure.next), (client._other(theirs, "0.1.0"), (client.START,)))


class CutShortTest(unittest.TestCase):
    """A request its server closed unanswered while cad's own update switches releases (``client._cut_short``): in a
    ``cad`` command, the next release's server is waited for and met as one of another release, which the command
    says as cad having updated itself while it ran; else the closed connection is said as it is."""

    def setUp(self) -> None:
        for patch in (mock.patch.object(client, "RELEASE", "0.1.0"), mock.patch.object(client, "SWITCH_SECONDS", 5.0),
                      mock.patch.object(client.time, "sleep")):
            patch.start()
            self.addCleanup(patch.stop)

    def closed(self) -> mock.Mock:
        connection = mock.MagicMock()
        connection.token = "t"  # on Windows a request carries its connection's token
        connection.__enter__.return_value = connection
        connection.reader = iter([])  # closed: nothing more to read
        return connection

    def test_a_request_the_switch_cut_short_meets_the_next_release_s_server(self) -> None:
        answers = iter([None, None, mock.Mock(release="0.2.0")])  # gone, then the next release's
        with mock.patch.object(client, "SWITCHING", lambda: True), \
                mock.patch.object(client, "_connect", side_effect=lambda *_a, **_k: next(answers)), \
                self.assertRaises(client.OtherRelease) as met:
            client._exchange(self.closed(), {"op": "status"})
        self.assertEqual((met.exception.theirs, met.exception.mine), ("0.2.0", "0.1.0"))
        from cad_server._internal.cli_errors import classify

        with mock.patch.object(store, "active", return_value="0.2.0"):
            self.assertEqual(str(classify(met.exception)),
                             "cad updated itself to 0.2.0 while this command ran: run it again")

    def test_a_reset_connection_is_cut_short_too(self) -> None:
        connection = self.closed()
        connection.writer.write.side_effect = ConnectionResetError("reset")
        with mock.patch.object(client, "SWITCHING", lambda: True), \
                mock.patch.object(client, "_connect", return_value=mock.Mock(release="0.2.0")), \
                self.assertRaises(client.OtherRelease):
            client._exchange(connection, {"op": "status"})

    def test_said_as_it_is_with_no_switch_no_release_held_or_no_newer_server(self) -> None:
        cases = ((lambda: False, "0.1.0", mock.Mock(release="0.2.0")),  # no switch underway
                 (lambda: True, None, mock.Mock(release="0.2.0")),  # no command: no release held
                 (None, "0.1.0", mock.Mock(release="0.2.0")))  # nothing says
        for switching, release, found in cases:
            with self.subTest(release=release), mock.patch.object(client, "SWITCHING", switching), \
                    mock.patch.object(client, "RELEASE", release), \
                    mock.patch.object(client, "_connect", return_value=found) as connect, \
                    self.assertRaisesRegex(ConnectionError, "^the engine server closed the connection$"):
                client._exchange(self.closed(), {"op": "status"})
            connect.assert_not_called()
        # The switch went back, or ended with the release before still serving: nothing newer answers.
        ends = iter([True, True, False])
        with mock.patch.object(client, "SWITCHING", lambda: next(ends)), \
                mock.patch.object(client, "_connect", return_value=mock.Mock(release="0.1.0")), \
                self.assertRaises(ConnectionError) as said:
            client._exchange(self.closed(), {"op": "status"})
        self.assertNotIsInstance(said.exception, client.OtherRelease)


class TheServerStopsTest(unittest.TestCase):
    """The stop a switch asks (``client.sweep``, as ``cad server stop``), and the drain 0.11.11 and earlier ask
    (``{"op": "stop", "drain": true}``), which a server of this release still honours: a real server goes."""

    def test_a_real_server_stops_at_once_or_drains_as_asked_and_goes(self) -> None:
        from tests.python.support import engine_daemon

        for drain in (False, True):
            with self.subTest(drain=drain):
                tmp = Path(tempfile.mkdtemp())
                self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
                engine = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None))
                self.addCleanup(shutil.rmtree, engine, ignore_errors=True)
                env = {**os.environ, "CAD_UPDATE_CHECK": "0", "CAD_STATE_DIR": str(tmp / "state"),
                       "CAD_CACHE_DIR": str(tmp / "cache"), "CAD_ENGINE_DIR": str(engine)}
                with mock.patch.dict(os.environ, env):
                    engine_daemon.start(env, self.addCleanup)
                    found = client._connect()
                    self.assertIsNotNone(found)
                    if drain:
                        self.assertEqual(client._exchange(found, {"op": "stop", "drain": True}),
                                         {"ok": True, "draining": True})
                        self.assertTrue(client.wait_gone(60.0))
                    else:
                        found.close()
                        self.assertEqual(len(client.sweep(stop=True, seconds=60.0)["stopped"]), 1)
                    self.assertIsNone(client._connect())


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
