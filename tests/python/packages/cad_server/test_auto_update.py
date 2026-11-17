"""cad's own update (``cad_server/_internal/auto_update.py``, its helper ``auto_update_helper.py``, ``cad auto-update``,
and the starts that meet a newer server): off by default; ``on`` only for a uv tool; no update without the feed or to an
older release; the idle rule; the helper's command lines on POSIX and Windows, and what it runs, in order; a start that
joins a newer server; a start that failed still updating. No test reaches the real feed or runs uv."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
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
from cad_server.cli import auto_update as command

RECEIPT = '[tool]\nrequirements = [{ name = "cad", specifier = "==0.1.0" }]\nentrypoints = [{ name = "cad" }]\n'


class Case(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(__import__("shutil").rmtree, self.tmp, ignore_errors=True)
        self.state = self.tmp / "state"
        self.tool = self.tmp / "tools" / "cad"  # a uv tool's environment
        self.tool.mkdir(parents=True)
        (self.tool / "uv-receipt.toml").write_text(RECEIPT, encoding="utf-8")
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.uv = self.bin / ("uv.exe" if os.name == "nt" else "uv")
        self.uv.write_text("", encoding="utf-8")
        self.uv.chmod(0o755)
        for patch in (mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.state), "PATH": str(self.bin)}),
                      mock.patch.object(sys, "prefix", str(self.tool)),
                      mock.patch.object(cad_server, "__version__", "0.1.0"),
                      mock.patch.object(updates, "checking", return_value=True)):
            patch.start()
            self.addCleanup(patch.stop)

    def feed(self, latest: str | None):
        return mock.patch.object(updates, "feed", return_value=None if latest is None else {"latest": latest})

    def cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = command.main(list(argv))
            except SystemExit as leaving:
                code = leaving.code
        return code, out.getvalue(), err.getvalue()


class SwitchesTest(Case):
    def test_both_are_off_by_default_and_on_installer_records_this_release_and_off_turns_both_off(self) -> None:
        self.assertEqual(auto_update.switches(), {"on": False, "installer": False, "installer_ran_for": None})
        self.assertEqual(self.cli(), (0, "auto-update: off\ninstaller: off\n", ""))
        self.assertEqual(self.cli("on"), (0, "auto-update: on\ninstaller: off\n", ""))
        self.assertEqual(self.cli("on", "--installer"), (0, "auto-update: on\ninstaller: on\n", ""))
        self.assertEqual(auto_update.switches()["installer_ran_for"], "0.1.0")
        self.assertEqual(self.cli("off"), (0, "auto-update: off\ninstaller: off\n", ""))
        kept = json.loads((self.state / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(kept["auto_update"], {"on": False, "installer": False, "installer_ran_for": "0.1.0"})
        self.assertEqual(self.cli("off", "--installer")[0], 2, "--installer goes with on alone")

    def test_on_is_refused_in_one_line_unless_this_cad_is_the_uv_tool_cad(self) -> None:
        for receipt in (None, '[tool]\nrequirements = [{ name = "other" }, { name = "cad" }]\n', "not toml ["):
            with self.subTest(receipt=receipt):
                if receipt is None:
                    (self.tool / "uv-receipt.toml").unlink(missing_ok=True)
                else:
                    (self.tool / "uv-receipt.toml").write_text(receipt, encoding="utf-8")
                code, out, err = self.cli("on")
                self.assertEqual((code, out), (1, ""))
                self.assertEqual(err.count("\n"), 1)
                self.assertIn("not a uv tool", err)
                self.assertFalse(auto_update.switches()["on"])
        (self.tool / "uv-receipt.toml").write_text('[tool]\nrequirements = ["cad==0.1.0"]\n', encoding="utf-8")
        self.assertEqual(auto_update.uv_tool(), self.tool, "a receipt's requirement as a string")


class FindUvTest(Case):
    def test_path_first_then_the_installers_folders_and_never_this_environment_s(self) -> None:
        self.assertEqual(auto_update.find_uv(), str(self.uv))
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


class DueTest(Case):
    def setUp(self) -> None:
        super().setUp()
        auto_update.change(True)

    def test_every_condition_and_forward_only(self) -> None:
        with self.feed("0.2.0"):
            self.assertEqual(auto_update.due(), "0.2.0")
        for latest in (None, "0.1.0", "0.0.9", "0.2.0-dev.1", "garbage"):  # no answer, the same, older, no release
            with self.subTest(latest=latest), self.feed(latest):
                self.assertIsNone(auto_update.due())
        with self.feed("0.2.0"):
            with mock.patch.object(updates, "checking", return_value=False):  # CAD_UPDATE_CHECK=0, CI
                self.assertIsNone(auto_update.due())
            with mock.patch.object(auto_update, "find_uv", return_value=None):
                self.assertIsNone(auto_update.due())
            with mock.patch.object(sys, "prefix", str(self.tmp)):  # not a uv tool
                self.assertIsNone(auto_update.due())
            auto_update.change(False)
            self.assertIsNone(auto_update.due())

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
            self.assertEqual(auto_update.due(now=now + auto_update.RETRY_SECONDS), "0.2.0", "a helper that died")
            auto_update._keep(record, {**auto_update.last(), "outcome": "failed"})
            self.assertIsNone(auto_update.due(now=now), "not by the server the failed update started")
            self.assertEqual(auto_update.due(now=now + auto_update.RETRY_SECONDS), "0.2.0", "once more, later")
            self.assertTrue(auto_update.trigger("0.2.0"))
            auto_update._keep(record, {**auto_update.last(), "outcome": "failed"})
            self.assertEqual(auto_update.last()["tries"], 2)
            self.assertIsNone(auto_update.due(now=now + 10 * auto_update.RETRY_SECONDS), "and never again")
        with self.feed("0.2.1"):
            self.assertEqual(auto_update.due(now=now), "0.2.1", "a newer release is no retry")


class WhenTest(Case):
    def test_the_idle_rule(self) -> None:
        with mock.patch.object(auto_update, "due", return_value="0.2.0"), \
                mock.patch.object(auto_update, "trigger", return_value=True) as trigger:
            self.assertFalse(auto_update.tend(working=True, ran=False, quiet_for=1e9), "never while work is in flight")
            self.assertFalse(auto_update.tend(working=False, ran=True, quiet_for=auto_update.IDLE_SECONDS - 1))
            self.assertEqual(trigger.call_count, 0)
            self.assertTrue(auto_update.tend(working=False, ran=False, quiet_for=0.0), "nothing has run: at once")
            self.assertTrue(auto_update.tend(working=False, ran=True, quiet_for=auto_update.IDLE_SECONDS))
            self.assertTrue(auto_update.at_start())
        self.assertEqual(trigger.call_args_list, [mock.call("0.2.0")] * 3)
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
                self.assertEqual(json.loads(line[5]), {"uv": "/u/uv", "cad": str(cad), "target": "0.2.0",
                                                       "prefix": str(self.tool), "record": "/s/auto-update.json",
                                                       "from": "0.1.0", "at": 5.0, "tries": 1})

    def test_the_trigger_starts_it_detached_with_nothing_of_this_environment_and_keeps_the_attempt(self) -> None:
        base = self.tmp / "python" / "bin" / "python3"
        with mock.patch.object(sys, "_base_executable", str(base), create=True), \
                mock.patch.dict(os.environ, {"PYTHONPATH": "/src", "VIRTUAL_ENV": str(self.tool), "KEEP": "1"}), \
                mock.patch.object(auto_update.subprocess, "Popen") as popen:
            self.assertTrue(auto_update.trigger("0.2.0"))
        (line,), options = popen.call_args
        self.assertEqual(line[0], str(base))
        self.assertEqual(json.loads(line[5])["uv"], str(self.uv))
        self.assertNotIn("PYTHONPATH", options["env"])
        self.assertNotIn("VIRTUAL_ENV", options["env"])
        self.assertEqual(options["env"]["KEEP"], "1")
        self.assertEqual(options["start_new_session" if os.name != "nt" else "creationflags"],
                         True if os.name != "nt" else 0x08000000 | 0x00000200)
        self.assertEqual(auto_update.last()["outcome"], "underway")
        with mock.patch.object(sys, "_base_executable", str(self.tool / "bin" / "python"), create=True), \
                mock.patch.object(auto_update.subprocess, "Popen") as popen:
            self.assertFalse(auto_update.trigger("0.2.1"), "never a Python of the environment it replaces")
        popen.assert_not_called()


class HelperTest(unittest.TestCase):
    """What the helper runs, in order, and what it keeps."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.tmp, ignore_errors=True)
        self.site = self.tmp / "lib" / "python3.14" / "site-packages"
        self.site.mkdir(parents=True)
        (self.site / "cad-0.1.0.dist-info").mkdir()
        self.told = {"uv": "uv", "cad": "cad", "target": "0.2.0", "prefix": str(self.tmp), "record": "r",
                     "from": "0.1.0", "at": 1.0}

    def fake(self, installs: list[int], removes: bool = False):
        """A stand-in for uv and cad: each install exits as ``installs`` says, putting its release in place when it
        succeeds and, with ``removes``, removing the whole tool when it fails (as uv does once it has begun)."""
        ran: list[list[str]] = []

        def run(line, timeout):
            ran.append(line[1:3] if line[0] == "cad" else ["install", line[-1]])
            present = list(self.site.glob("cad-*.dist-info"))
            if line[0] == "uv":
                code = installs.pop(0)
                for found in present:
                    found.rmdir()
                if code == 0:
                    (self.site / f"cad-{line[-1].split('==')[1]}.dist-info").mkdir()
                elif not removes:
                    for found in present:
                        found.mkdir()
                return code, "uv said"
            return (0, "done") if present else (127, "cad: not found")
        return ran, run

    def test_stop_install_start_and_tried_again_on_failure(self) -> None:
        ran, run = self.fake([1, 1, 0])
        waited: list[float] = []
        found = helper.update(self.told, run=run, sleep=waited.append)
        self.assertEqual(ran, [["server", "stop"], *[["install", "cad==0.2.0"]] * 3, ["server", "start"]])
        self.assertEqual(waited, list(helper.WAITS[:3]))
        self.assertEqual((found["outcome"], found["release"], found["from"], found["started"]),
                         ("installed", "0.2.0", "0.1.0", "done"))

    def test_a_failed_install_still_starts_the_server_with_whatever_cad_is_there(self) -> None:
        ran, run = self.fake([1] * len(helper.WAITS))
        found = helper.update(self.told, run=run, sleep=lambda _s: None)
        self.assertEqual((ran[0], ran[-1], found["outcome"], found["detail"]),
                         (["server", "stop"], ["server", "start"], "failed", "uv said"))

    def test_an_install_that_failed_and_took_the_tool_with_it_puts_back_the_release_that_ran_then_starts(self) -> None:
        ran, run = self.fake([1] * len(helper.WAITS) + [0], removes=True)
        found = helper.update(self.told, run=run, sleep=lambda _s: None)
        self.assertEqual(ran, [["server", "stop"], *[["install", "cad==0.2.0"]] * len(helper.WAITS), ["--version"],
                               ["install", "cad==0.1.0"], ["server", "start"]])
        self.assertEqual((found["outcome"], found["restored"], found["started"]), ("failed", True, "done"))
        self.assertEqual(helper.installed(self.tmp), (0, 1, 0), "the release that ran before, and no other")
        ran, run = self.fake([1] * len(helper.WAITS))  # a failure that left the tool as it was: nothing put back
        self.assertNotIn("restored", helper.update(self.told, run=run, sleep=lambda _s: None))
        self.assertEqual(ran[-2:], [["--version"], ["server", "start"]])

    def test_forward_only_an_environment_at_the_target_or_newer_is_left_alone(self) -> None:
        (self.site / "cad-0.1.0.dist-info").rename(self.site / "cad-0.3.0.dist-info")
        ran, run = self.fake([])
        self.assertEqual(helper.update(self.told, run=run)["outcome"], "current")
        self.assertEqual(ran, [["server", "stop"], ["server", "start"]])
        windows = self.tmp / "win"
        (windows / "Lib" / "site-packages" / "cad-0.2.0.dist-info").mkdir(parents=True)
        self.assertEqual(helper.installed(windows), (0, 2, 0), "a Windows environment's layout")

    def test_no_console_window_on_windows(self) -> None:
        with mock.patch.object(helper.subprocess, "run", return_value=types.SimpleNamespace(returncode=0, stdout="")) \
                as running:
            helper.run(["cad"], 5)
        self.assertEqual(running.call_args.kwargs["creationflags"], helper.NO_WINDOW)
        self.assertEqual(helper.NO_WINDOW, 0x08000000 if os.name == "nt" else 0)

    @unittest.skipIf(os.name == "nt", "the stand-in uv and cad are shell scripts")
    def test_the_helper_runs_isolated_from_its_own_source_and_keeps_its_outcome(self) -> None:
        log = self.tmp / "log"
        for name, body in (("cad", f'echo "cad $*" >> {log}'),
                           ("uv", f'echo "uv $*" >> {log}; mv {self.site}/cad-0.1.0.dist-info '
                                  f'{self.site}/cad-0.2.0.dist-info')):
            (self.tmp / name).write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
            (self.tmp / name).chmod(0o755)
        record = self.tmp / "auto-update.json"
        line = auto_update.helper_command("0.2.0", now=1.0, version="0.1.0", prefix=str(self.tmp),
                                          uv=str(self.tmp / "uv"), record=str(record), windows=False)
        (self.tmp / "bin").mkdir()
        (self.tmp / "bin" / "cad").symlink_to(self.tmp / "cad")
        env = {**os.environ, "PYTHONPATH": "/nowhere-at-all"}
        subprocess.run(line, check=True, env=env, cwd=self.tmp, timeout=60)
        self.assertEqual(log.read_text(encoding="utf-8").splitlines(),
                         ["cad server stop", "uv tool install --managed-python --python 3.14 cad==0.2.0",
                          "cad server start"])
        self.assertEqual(json.loads(record.read_text(encoding="utf-8"))["outcome"], "installed")


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
        sweep.assert_called_once_with(stop=True, seconds=client.STOP_SECONDS)

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

        auto_update.change(True)
        err = io.StringIO()
        with self.feed("0.2.0") as feed, \
                mock.patch.object(client, "start", side_effect=ConnectionError("the engine server did not start")), \
                mock.patch.object(auto_update, "trigger", return_value=True) as trigger, \
                redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = server.main(["start"])
        self.assertEqual(code, 1)
        trigger.assert_called_once_with("0.2.0")
        self.assertEqual(feed.call_args.kwargs, {"fetch": True}, "the feed read where it is due: no server reads it")
        self.assertEqual(err.getvalue().splitlines(), ["cad: updating cad to 0.2.0, which then starts the server",
                                                       "cad server start: the engine server did not start"])


class DoctorTest(Case):
    def test_doctor_shows_the_switches_the_tool_uv_and_the_last_attempt(self) -> None:
        from cad_server.cli import doctor

        auto_update.change(True)
        auto_update._keep(self.state / auto_update.RECORD, {"release": "0.2.0", "from": "0.1.0", "at": 0.0,
                                                            "outcome": "failed", "detail": "uv said no",
                                                            "restored": True})
        lines = {check["name"]: check["detail"] for check in (doctor._check(name, *how()) for name, how in
                 (("update", doctor._update), ("attempt", doctor._attempt)))}
        self.assertEqual(lines["update"], f"auto-update on, installer off; a uv tool ({self.tool})")
        self.assertRegex(lines["attempt"], r"^0\.1\.0 to 0\.2\.0 on \S+ \S+: failed \(uv said no\); 0\.1\.0 put back$")


if __name__ == "__main__":
    unittest.main()
