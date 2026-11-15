"""``cad setup``, its hidden ``--engine-update``, and ``cad uninstall`` (``cad_server.cli.setup``, ``uninstall``).

``cad setup`` sets up the version that runs it -- its folder, its server, the check that it runs, its kernel, its
marker, and the ``cad`` command --, then starts that version's server (a real one in ``Serving``; elsewhere the start
is recorded), and knows no app: a home of the test's own holds agent apps' folders and stand-ins
of their commands on PATH, which record any call. ``--engine-update`` is what the updaters of 0.10.0 to 0.11.10 run
of a newer release, from the flat folder they made (its prepare run first, for an automatic update): it sets the
version up, writes the record their switch starts its server by, leaves ``installations/current`` and the ``cad``
command to them, and owes the install script's run, which the version's server carries out (``test_handover``).
``cad uninstall`` removes every version (a real server running, stopped first), the state and cache folders and the
``cad`` command, and nothing else.

The device is ``test_versions``'s (uv stood in for: each version a real virtual environment of this Python naming
this checkout's sources); the real servers are ``test_version_servers``'s. A real 0.11.10 updating into this build
is scripts/test/rehearse-update.py's.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests.python.packages.cad_server.test_version_servers import WAIT, Servers
from tests.python.packages.cad_server.test_versions import OLD, Device

from cad.engine import client, places
from cad_server._internal import arrival, imports, install_script, installations, legacy, versions
from cad_server.cli import setup, uninstall

X, Y = "0.12.0", "0.12.1"
DEV = f"{X}-dev.20261114000000"
# The agents' commands a setup must never run, stood in for on PATH.
APPS = ("claude", "codex", "cursor-agent", "gemini", "grok", "hermes", "npx", "qwen")


def snapshot(folder: Path) -> dict[str, bytes]:
    return {path.relative_to(folder).as_posix(): path.read_bytes() for path in sorted(folder.rglob("*"))
            if path.is_file()}


class Computer(Device):
    """A device with a home of agent apps (their folders, and stand-ins of their commands on PATH, each writing a line
    to ``called`` when run). The server a setup starts is recorded (``served``), never started, unless ``SERVES``."""

    SERVES = False

    def setUp(self) -> None:
        super().setUp()
        self.served = mock.Mock()
        if not self.SERVES:
            patch = mock.patch.object(setup, "_serve", self.served)
            patch.start()
            self.addCleanup(patch.stop)
        self.home = self.root / "home"
        for folder, name, text in ((".claude", "settings.json", "{}"), (".codex", "config.toml", "[plugins]\n"),
                                   (".cursor/plugins/local", "keep", "x"), (".agents/skills/cad", "SKILL.md", "ours")):
            (self.home / folder).mkdir(parents=True)
            (self.home / folder / name).write_text(text, encoding="utf-8")
        tools = self.root / "tools"
        tools.mkdir()
        self.called = self.root / "called"
        for app in APPS:
            stand_in = tools / app
            stand_in.write_text(f"#!/bin/sh\necho {app} \"$@\" >> '{self.called}'\n", encoding="utf-8")
            stand_in.chmod(0o755)
        self.before = snapshot(self.home)
        environment = {"HOME": str(self.home), "USERPROFILE": str(self.home),
                       "PATH": os.pathsep.join([str(tools), os.environ.get("PATH", "")])}
        for patch in (mock.patch.dict(os.environ, environment),
                      mock.patch.object(installations, "_make_interpreter", side_effect=self.interpreter)):
            patch.start()
            self.addCleanup(patch.stop)

    def interpreter(self, folder: str) -> None:
        """On Windows the cad command's Python, as uv makes it, without uv."""
        home = self.root / "python-home"
        home.mkdir(exist_ok=True)
        (home / "python.exe").write_bytes(b"MZ")
        Path(folder, "Scripts").mkdir(parents=True, exist_ok=True)
        Path(folder, "Scripts", "python.exe").write_bytes(b"MZ")
        Path(folder, "pyvenv.cfg").write_text(f"home = {home}\nversion_info = 3.14.0\n", encoding="utf-8")

    def no_app_touched(self) -> None:
        self.assertFalse(self.called.exists(), "no app's command was run")
        self.assertEqual(snapshot(self.home), self.before, "no file of the home changed")

    def main(self, module, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = module.main(argv)
            except SystemExit as exit_:
                code = exit_.code
        return code, out.getvalue(), err.getvalue()


class Setup(Computer):
    def test_six_steps_for_this_version_and_no_app(self) -> None:
        command = Path(installations.proxy_path())
        command.parent.mkdir()
        if os.name != "nt":  # an older release's command: replaced
            command.write_text(f"#!/bin/sh\n# {installations.MARK}11\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {places.INSTALLATION_ENV: DEV}):
            code, out, err = self.main(setup, [])
            self.assertEqual(code, 0, out + err)
            self.assertEqual(out, f"cad {DEV} is installed now: {places.version_dir(DEV)}\n")
            record = places.version_record(DEV)
            self.assertIsNotNone(record, "the version's complete marker")
            self.assertTrue(any("-e" in step for step in self.uv.steps), "a development version from its checkout")
            self.assertEqual(sorted(os.listdir(self.state)), ["install.lock", "installations", "versions"],
                             "nothing but the version's folder and, on a new computer, the record a process with "
                             "no version (the library in a person's own Python) starts a server by")
            self.assertEqual(installations.current()["prefix"], places.version_record(DEV)["prefix"])
            self.assertEqual(installations.proxy_status(), installations.OK, "the cad command, of this revision")
            steps = len(self.uv.steps)
            code, out, err = self.main(setup, [])
            self.assertEqual((code, len(self.uv.steps)), (0, steps), "again: quick, and nothing made twice")
            self.assertEqual(out, f"cad {DEV} is installed: {places.version_dir(DEV)}\n")
        self.assertEqual(self.served.call_args_list, [mock.call(DEV)] * 2, "its server started, where none runs")
        self.no_app_touched()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            setup.main(["--only", "claude"])
        self.assertNotIn("--engine-update", setup.build_parser().format_help(), "hidden")

    def test_earlier_servers_stop_before_the_copy_and_current_names_this_version_where_it_named_none_installed(
            self) -> None:
        # A computer whose `current` names a release no longer installed: the library in a person's own Python starts
        # the server it names, so it names this version now. 0.8's server stops before the copy, not after it.
        installations.point("0.9.9")
        order: list[str] = []
        real = imports.ensure
        with mock.patch.dict(os.environ, {places.INSTALLATION_ENV: DEV}), \
                mock.patch.object(legacy, "stop_earlier", side_effect=lambda told: order.append("stop") or []), \
                mock.patch.object(imports, "ensure", side_effect=lambda name, told: order.append("copy")
                                  or real(name, told=told)):
            code, out, err = self.main(setup, [])
        self.assertEqual((code, order), (0, ["stop", "copy"]), out + err)
        self.assertEqual(installations.current_version(), DEV)
        # A current naming an installed newer version stays as it is.
        installations.point(DEV)
        with mock.patch.object(setup, "_name", return_value=X), mock.patch.object(legacy, "stop_earlier"):
            self.assertEqual(self.main(setup, [])[0], 0)
        self.assertEqual(installations.current_version(), DEV)

    @unittest.skipIf(os.name == "nt", "a foreign cad.exe is the Windows command's own test")
    def test_a_command_of_another_s_fails_setup_and_the_updater_s_run_never_touches_the_command(self) -> None:
        command = Path(installations.proxy_path())
        command.parent.mkdir()
        command.write_text("#!/bin/sh\necho someone else's cad\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {places.INSTALLATION_ENV: DEV}):
            code, out, err = self.main(setup, [])
            self.assertEqual(code, 1, out + err)
            self.assertIn("is not cad's, and is left alone", err)
            with mock.patch.object(places, "versioned", return_value=DEV):
                code, out, err = self.main(setup, ["--engine-update"])
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("cad command", err, "the updater's run writes no command, and says nothing of one")
        self.assertEqual(install_script.read(DEV)["state"], "owed", "the hand-over owed all the same")
        self.assertEqual(command.read_text(encoding="utf-8"), "#!/bin/sh\necho someone else's cad\n")

    def test_the_first_setup_copies_settings_and_store_once_from_the_newest_older_version(self) -> None:
        import json

        self.data(X, {"language": {"locale": "fr"}})
        with mock.patch.dict(os.environ, {places.INSTALLATION_ENV: DEV}):
            code, out, err = self.main(setup, [])
            self.assertEqual(code, 0, out + err)
            self.assertIn(f"took its settings and store from cad {X}'s data", err)
            settings = places.data_dir(DEV) / "settings.json"
            self.assertEqual(json.loads(settings.read_text(encoding="utf-8")), {"language": {"locale": "fr"}})
            (places.data_dir(X) / "settings.json").write_text('{"language": {"locale": "de"}}', encoding="utf-8")
            code, out, err = self.main(setup, [])
            self.assertEqual((code, err), (0, ""), "again: nothing copied")
            self.assertEqual(json.loads(settings.read_text(encoding="utf-8")), {"language": {"locale": "fr"}})
        self.no_app_touched()


@unittest.skipIf(os.name == "nt", "0.8's stand-in stop is a POSIX script")
class Arriving(Computer):
    """The install command's ``cad setup`` on a computer an earlier release ran on: what it left running handed over
    (``legacy.stop_earlier``, ``legacy.hand_over``), cad's own processes and records alone."""

    def test_from_0_11_10_and_0_8_their_servers_stop_and_their_clients_find_this_version(self) -> None:
        import json

        self.legacy()  # 0.11.10 installed by the install command: its data, its flat release, its records
        # 0.8 installed beside it: its installation record, its own `cadgen stop` a stand-in that says what it did.
        stopped = self.root / "cadgen-stopped"
        cadgen = self.root / "cadgen"
        cadgen.write_text(f"#!/bin/sh\necho \"$* telemetry=$CADGEN_TELEMETRY\" >> '{stopped}'\n"
                          "echo '{\"stopped\": [\"0.8.4\"]}'\n", encoding="utf-8")
        cadgen.chmod(0o755)
        (self.state / "installations" / "0.8.4.json").write_text(json.dumps(
            {"version": "0.8.4", "python": sys.executable, "cadgen": str(cadgen), "prefix": str(self.root)}),
            encoding="utf-8")
        flat = str(self.state / "releases" / OLD)
        asked: list[dict] = []

        def ask_flat(message, *, seconds=10.0):  # 0.11.10's server, holding the flat door
            asked.append({key: value for key, value in message.items() if key != "internal"})
            return {"ok": True, "prefix": flat, "installation": OLD} if message["op"] == "status" else {"ok": True}

        with mock.patch.object(setup, "_name", return_value=Y), mock.patch.object(versions, "ask_flat", ask_flat):
            code, out, err = self.main(setup, [])
        self.assertEqual(code, 0, out + err)
        self.assertEqual(stopped.read_text(encoding="utf-8"), "stop --json telemetry=0\n", "0.8's own stop, quiet")
        self.assertIn("stopped cadgen 0.8.4's server", err)
        self.assertEqual(asked, [{"op": "status"}, {"op": "stop", "drain": True}], "asked to stop once idle")
        self.served.assert_not_called()  # its pages' port is taken until it is idle: the next command starts Y's
        record = installations.current()
        self.assertEqual((record["version"], record["prefix"]), (Y, str(places.code_dir(Y) / "server")),
                         "its clients start or find this version's server")
        settings = json.loads((places.data_dir(Y) / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual((settings["telemetry"]["choice"], settings["whats_new"]), ("off", {"seen": []}),
                         "the no kept; What's new decided while 0.11.10's records were there: an updated computer")
        self.no_app_touched()

        # Again, with this version's own server at the flat door: nothing asked to stop, nothing written.
        asked.clear()
        with mock.patch.object(setup, "_name", return_value=Y), \
                mock.patch.object(versions, "ask_flat", side_effect=lambda message, **_: asked.append(message) or {
                    "ok": True, "prefix": str(places.code_dir(Y) / "server")}):
            self.assertEqual(self.main(setup, [])[0], 0)
        self.assertEqual([message["op"] for message in asked], ["status"])
        self.served.assert_called_once_with(Y)


@unittest.skipIf(os.name == "nt", "a command of 0.11.10's is a POSIX script here")
class EngineUpdate(Computer):
    """What an updater of 0.11.10 runs of a newer release Y, and what its switch then needs."""

    def test_prepare_then_the_whole_run_hands_over_owes_the_install_script_and_changes_nothing_else(self) -> None:
        self.legacy()  # 0.11.10 installed: its data, its flat release, its records (current names it)
        command = Path(installations.proxy_path())
        command.parent.mkdir()
        command.write_text(f"#!/bin/sh\n# {installations.MARK}11\n", encoding="utf-8")  # 0.11.10's, which runs current
        before = command.read_bytes()
        again: list[str] = []
        ended: list[tuple] = []
        with mock.patch.object(setup, "_name", return_value=Y), \
                mock.patch.object(setup, "_again", side_effect=lambda cad, alone=False: again.append(cad) or 0), \
                mock.patch.object(arrival, "setup_ended", side_effect=lambda *args, **kwargs: ended.append((*args, kwargs))):
            # The first run, from the flat folder (CAD_UPDATE_PREPARE=1): Y present, and nothing else.
            with mock.patch.dict(os.environ, {setup.PREPARE_ENV: "1"}):
                code, out, err = self.main(setup, ["--engine-update"])
            self.assertEqual(code, 0, out + err)
            self.assertIsNotNone(places.version_record(Y))
            self.assertEqual((again, installations.current_version()), ([], OLD),
                             "the first run changes nothing but Y's own folder")
            self.assertEqual(imports.marker(Y)["imported"]["kind"], "legacy", "its data copied in from their layout")
            # The second, from the flat folder: Y's own cad runs it again.
            code, out, err = self.main(setup, ["--engine-update"])
            self.assertEqual((code, again), (0, [places.version_record(Y)["cad"]]), out + err)
            self.assertEqual(ended, [], "a prepare run that held, and a run that hands on, tell no end")
            # Y's own run: set up, handed over, the install script's run owed, nothing started.
            with mock.patch.object(places, "versioned", return_value=Y), \
                    mock.patch.object(legacy, "hand_over") as hand_over, mock.patch.object(legacy, "_stop") as stops:
                code, out, err = self.main(setup, ["--engine-update"])
            self.assertEqual(code, 0, out + err)
            hand_over.assert_not_called()  # the updater's own switch stops its server: never asked here
            stops.assert_not_called()  # nor any earlier release's: on Windows that may be the updater's own
            self.served.assert_not_called()  # and starts Y's: none started here
        self.assertEqual(ended, [(Y, "updater", OLD, "ok", None, {"first": True})],
                         "its end told once, from the version it came from, by the run that kept its arrival")
        # What the updater's switch then reads: the release to go back to, still its own (current, read after this
        # run), and the record of Y's server environment, which it starts once it has pointed current at Y.
        self.assertEqual(installations.current_version(), OLD)
        record = installations.installation_record(installations.state().read(f"installations/{Y}.json"))
        self.assertEqual((record["version"], record["prefix"]), (Y, str(places.code_dir(Y) / "server")))
        self.assertEqual(command.read_bytes(), before, "0.11.10's cad command, which runs what current names, kept")
        owed = install_script.read(Y)
        self.assertEqual((owed["state"], owed["attempts"]), ("owed", 0), "the install script's run owed, not started")
        self.assertEqual({key: arrival.read(Y)[key] for key in ("route", "from", "served")},
                         {"route": "updater", "from": OLD, "served": None})
        self.no_app_touched()

    def test_a_run_that_fails_tells_its_end_and_why(self) -> None:
        ended: list[tuple] = []
        failing = versions.Present(Y, None, cannot="network", error="no network for what uv's cache lacks")
        with mock.patch.object(setup, "_name", return_value=Y), \
                mock.patch.object(versions, "make_present", return_value=failing), \
                mock.patch.object(arrival, "setup_ended", side_effect=lambda *args, **kwargs: ended.append((*args, kwargs))):
            for argv, environment in ((["--engine-update"], {setup.PREPARE_ENV: "1"}), ([], {})):
                with mock.patch.dict(os.environ, environment):
                    self.assertEqual(self.main(setup, argv)[0], 3)
        self.assertEqual(ended, [(Y, "updater", None, "failed", "network", {"first": False}),
                                 (Y, "setup", None, "failed", "network", {"first": False})])
        self.assertIsNone(install_script.read(Y), "nothing owed by a run that failed")


@unittest.skipIf(os.name == "nt", "0.10.0's stand-in stop is a POSIX script")
class TakeOver(Computer):
    """``--engine-update`` run by 0.10.0's updater on Windows, which keeps its state -- the records its switch reads --
    in the local application data (``places.appdata_state_dir``, here a folder of the test's), apart from this
    version's: its switch could only go back, so the run takes the computer over itself, 0.10.0's server stopped by
    its own stop command before anything of it is taken in."""

    def setUp(self) -> None:
        import json

        super().setUp()
        self.appdata = self.root / "AppData" / "Local" / "cad-state"
        (self.appdata / "installations").mkdir(parents=True)
        self.stopped = self.root / "stopped"
        console = self.root / "ten" / "bin" / "cad"
        console.parent.mkdir(parents=True)
        console.write_text(f"#!/bin/sh\necho \"$*\" >> '{self.stopped}'\n"
                           "echo '{\"ok\": true, \"stopped\": [\"engine\"]}'\nexit ${TEN_EXIT:-0}\n", encoding="utf-8")
        console.chmod(0o755)
        (self.appdata / "installations" / "0.10.0.json").write_text(json.dumps(
            {"version": "0.10.0", "python": sys.executable, "cad": str(console), "prefix": str(console.parent.parent)}),
            encoding="utf-8")
        (self.appdata / "installations" / "current").write_text("0.10.0", encoding="utf-8")
        patch = mock.patch.object(places, "appdata_state_dir", return_value=self.appdata)
        patch.start()
        self.addCleanup(patch.stop)

    def test_0_10_0_s_stop_runs_only_against_0_10_0_s_own_server(self) -> None:
        # Its `cad stop` stops whatever answers at its port file, where later servers write a copy of their own.
        for answering, runs in ((str(places.code_dir(Y) / "server"), False), (str(self.root / "ten"), True),
                                (None, True)):
            with self.subTest(answering=answering):
                self.stopped.unlink(missing_ok=True)
                with mock.patch.object(legacy, "_appdata_serving", return_value=answering):
                    self.assertEqual(legacy.stop_earlier(), ["0.10.0"] if runs else [])
                    self.assertTrue(legacy.stop_appdata(), "held: nothing of 0.10.0's serves, or it stopped")
                self.assertEqual(self.stopped.exists(), runs, "0.10.0's own stop run")

    def test_it_is_told_by_where_0_10_0_made_its_flat_folder(self) -> None:
        with mock.patch.object(sys, "prefix", str(self.appdata / "releases" / Y)):
            self.assertTrue(setup._alone())
        self.assertFalse(setup._alone(), "a flat folder of 0.11.10's layout: its switch starts this version")
        with mock.patch.object(places, "appdata_state_dir", return_value=None):
            self.assertFalse(setup._alone(), "not Windows, or a state folder named")

    def test_0_10_0_stops_before_anything_of_it_is_taken_in_or_nothing_is(self) -> None:
        order: list[int] = []  # at each taking in, how many of 0.10.0's stops had run
        real = places.adopt_earlier
        again: list[tuple] = []
        stops = lambda: self.stopped.read_text(encoding="utf-8").count("stop") if self.stopped.exists() else 0  # noqa: E731
        with mock.patch.object(setup, "_name", return_value=Y), mock.patch.object(setup, "_alone", return_value=True), \
                mock.patch.object(places, "adopt_earlier", side_effect=lambda: order.append(stops()) or real()), \
                mock.patch.object(setup, "_again", side_effect=lambda cad, alone=False: again.append((cad, alone)) or 0):
            with mock.patch.dict(os.environ, {"TEN_EXIT": "1"}):
                code, out, err = self.main(setup, ["--engine-update"])
            self.assertEqual(code, 1, out + err)
            self.assertIn("the server of cad-server 0.10.0 did not stop, and keeps what it has", err)
            self.assertEqual((order, again, places.version_record(Y)), ([], [], None), "nothing made, nothing taken in")
            code, out, err = self.main(setup, ["--engine-update"])
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.stopped.read_text(encoding="utf-8"), "stop --json\nstop --json\n", "its own stop, each run")
        self.assertEqual(order, [2], "taken in once, after this run's stop")
        self.assertEqual(again, [(places.version_record(Y)["cad"], True)], "the version's own run told to take over")

    def test_the_version_s_own_run_takes_the_computer_over_and_points_0_10_0_s_records_at_it(self) -> None:
        self.present(Y)  # the run from the flat folder: the version present, 0.10.0's server stopped
        with mock.patch.object(setup, "_name", return_value=Y), mock.patch.object(places, "versioned", return_value=Y), \
                mock.patch.dict(os.environ, {setup.ALONE_ENV: "1"}):
            code, out, err = self.main(setup, ["--engine-update"])
        self.assertEqual(code, 0, out + err)
        self.assertNotIn(setup.ALONE_ENV, os.environ, "taken off: nothing started from here inherits it")
        server = str(places.code_dir(Y) / "server")
        self.assertEqual((installations.current()["version"], installations.current()["prefix"]), (Y, server))
        from cad_server.engine.registry import Folder

        theirs = installations.current(Folder(self.appdata))
        self.assertEqual((theirs["version"], theirs["prefix"]), (Y, server), "0.10.0's clients start this version")
        self.assertEqual(installations.proxy_status(), installations.OK, "the cad command, this revision's")
        self.served.assert_called_once_with(Y, pages=True)
        self.assertEqual(install_script.read(Y)["state"], "owed", "the install script's run owed, for its server")
        self.assertEqual({key: arrival.read(Y)[key] for key in ("route", "from")}, {"route": "updater", "from": "0.10.0"})
        self.no_app_touched()


class Serving(Servers, Computer):
    """The server plain ``cad setup`` leaves running for every later session, a real one."""

    SERVES = True

    def test_setup_leaves_its_version_s_server_running_and_again_starts_no_other(self) -> None:
        before = dict(os.environ)
        with mock.patch.object(setup, "_name", return_value=X):
            code, out, err = self.main(setup, [])
            self.assertEqual(code, 0, out + err)
            self.assertTrue(out.endswith(f"cad {X}'s server is running\n"), out + err)
            started = versions.ask(X, {"op": "pid"}, seconds=WAIT)
            self.assertIsNotNone(started, "it answers at its own door")
            self.assertTrue(dict(os.environ) == before, "this process's environment as it was")
            code, out, err = self.main(setup, [])
        self.assertEqual(code, 0, out + err)
        self.assertEqual(versions.ask(X, {"op": "pid"}, seconds=WAIT)["pid"], started["pid"], "no other started")
        self.no_app_touched()

    def test_a_server_that_cannot_start_is_said_and_the_setup_still_succeeds(self) -> None:
        with mock.patch.object(setup, "_name", return_value=X), \
                mock.patch.object(client, "connect", side_effect=ConnectionError("the engine server did not start")):
            code, out, err = self.main(setup, [])
        self.assertEqual(code, 0, out + err)
        self.assertEqual(out, f"cad {X} is installed now: {places.version_dir(X)}\n")
        self.assertIn(f"cad {X}'s server is not running: the engine server did not start", err)


class Uninstall(Servers, Computer):
    def test_everything_of_cad_goes_its_server_stopped_first_and_nothing_else(self) -> None:
        self.legacy()  # what 0.11.10 left: its records, its flat release, its cache
        self.version(X)
        self.start(X)
        self.assertIn(installations.write_proxy()[1], (installations.MISSING, installations.STALE))
        beside = self.state.parent / "kept.txt"
        beside.write_text("not cad's", encoding="utf-8")
        others = self.engines / "someone-else.txt"  # the engines' folder a variable named: only cad's entries go
        others.write_text("not cad's", encoding="utf-8")
        self.assertTrue((self.engines / X).is_dir())
        code, out, err = self.main(uninstall, ["--yes"])
        self.assertEqual(code, 0, out + err)
        self.assertIsNone(versions.ask(X, {"op": "pid"}, seconds=2.0), "its server stopped")
        for gone in (self.state, self.cache, Path(installations.proxy_path()), self.engines / X):
            self.assertFalse(gone.exists(), gone)
        self.assertEqual(os.listdir(self.engines), [others.name])
        self.assertTrue(beside.exists())
        self.no_app_touched()
        code, out, _err = self.main(uninstall, ["--yes"])
        self.assertEqual((code, out), (0, "cad is not installed on this computer: nothing to remove.\n"))

    def test_folders_of_cad_s_names_with_no_mark_of_cad_s_are_another_program_s(self) -> None:
        # A state and a cache folder of the same names, another program's: generic names alone, nothing only cad writes.
        (self.state / "documents").mkdir(parents=True)
        (self.state / "settings.json").write_text('{"theme": "dark"}', encoding="utf-8")
        (self.cache / "documents").mkdir(parents=True)
        (self.cache / "downloads").mkdir()
        before = snapshot(self.root)
        code, out, _err = self.main(uninstall, ["--yes"])
        self.assertEqual((code, out), (0, "cad is not installed on this computer: nothing to remove.\n"))
        self.assertEqual(snapshot(self.root), before)
        self.assertTrue((self.state / "documents").is_dir() and (self.cache / "downloads").is_dir())
        # cad's settings are a mark of cad's: that folder is cad's.
        (self.state / "settings.json").write_text('{"telemetry": {"choice": "off"}}', encoding="utf-8")
        code, out, err = self.main(uninstall, ["--yes"])
        self.assertEqual(code, 0, out + err)
        self.assertFalse(self.state.exists())
        self.assertTrue((self.cache / "downloads").is_dir(), "the cache folder holds what cad's never does")

    def test_nobody_to_ask_and_no_yes_changes_nothing(self) -> None:
        self.version(X)
        with mock.patch.object(sys, "stdin", io.StringIO()):
            code, _out, err = self.main(uninstall, [])
        self.assertEqual(code, 2, err)
        self.assertTrue(places.version_dir(X).is_dir())


if __name__ == "__main__":
    unittest.main()
