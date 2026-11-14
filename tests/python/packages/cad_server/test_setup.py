"""``cad setup``, its hidden ``--engine-update``, and ``cad uninstall`` (``cad_server.cli.setup``, ``uninstall``).

``cad setup`` sets up the version that runs it -- its folder, its server, the check that it runs, its kernel, its
marker, and the ``cad`` command -- and knows no app: a home of the test's own holds agent apps' folders and stand-ins
of their commands on PATH, which record any call. ``--engine-update`` is what the updaters of 0.10.0 to 0.11.10 run
of a newer release, from the flat folder they made (its prepare run first, for an automatic update): it sets the
version up, hands over from their layout, and starts the install script once, never waiting on it (its stand-in,
``CAD_ENGINE_UPDATE_INSTALLER``). ``cad uninstall`` removes every version (a real server running, stopped first),
the state and cache folders and the ``cad`` command, and nothing else.

The device is ``test_versions``'s (uv stood in for: each version a real virtual environment of this Python naming
this checkout's sources); the real servers are ``test_version_servers``'s. A real 0.11.10 updating into this build
is scripts/test/rehearse-update.py's.
"""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.python.packages.cad_server.test_version_servers import Servers
from tests.python.packages.cad_server.test_versions import OLD, Device

from cad.engine import places
from cad_server._internal import imports, installations, legacy, versions
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
    to ``called`` when run)."""

    def setUp(self) -> None:
        super().setUp()
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
                       "PATH": os.pathsep.join([str(tools), os.environ.get("PATH", "")]), setup.INSTALLER_ENV: ""}
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
            self.assertEqual(sorted(os.listdir(self.state)), ["install.lock", "versions"],
                             "nothing but the version's folder: no pointer, no record, no setting")
            self.assertEqual(installations.proxy_status(), installations.OK, "the cad command, of this revision")
            steps = len(self.uv.steps)
            code, out, err = self.main(setup, [])
            self.assertEqual((code, len(self.uv.steps)), (0, steps), "again: quick, and nothing made twice")
            self.assertEqual(out, f"cad {DEV} is installed: {places.version_dir(DEV)}\n")
        self.no_app_touched()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            setup.main(["--only", "claude"])
        self.assertNotIn("--engine-update", setup.build_parser().format_help(), "hidden")

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


@unittest.skipIf(os.name == "nt", "the install script's stand-in is a POSIX script")
class EngineUpdate(Computer):
    """What an updater of 0.11.10 runs of a newer release Y, and what its switch then needs."""

    def test_prepare_then_the_whole_run_hands_over_and_starts_the_installer_once_without_waiting(self) -> None:
        self.legacy()  # 0.11.10 installed: its data, its flat release, its records
        released, ran = self.root / "released", self.root / "ran"
        installer = self.root / "installer.py"
        installer.write_text("import sys, time, pathlib\n"
                             "released, ran = map(pathlib.Path, sys.argv[1:])\n"
                             "while not released.exists():\n    time.sleep(0.02)\n"
                             "with ran.open('a') as out:\n    out.write('ran\\n')\n", encoding="utf-8")
        hook = f"{sys.executable} {installer} {released} {ran}"
        again: list[str] = []
        with mock.patch.object(setup, "_name", return_value=Y), \
                mock.patch.object(setup, "_again", side_effect=lambda cad: again.append(cad) or 0), \
                mock.patch.dict(os.environ, {setup.INSTALLER_ENV: hook}):
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
            self.assertFalse(ran.exists(), "nothing started by a run that hands on")
            # Y's own run: set up, handed over, the installer started and not waited for.
            began = time.monotonic()
            with mock.patch.object(places, "versioned", return_value=Y), \
                    mock.patch.object(legacy, "hand_over") as hand_over:
                code, out, err = self.main(setup, ["--engine-update"])
            self.assertEqual(code, 0, out + err)
            hand_over.assert_not_called()  # the updater's own switch stops its server: never asked here
            self.assertFalse(ran.exists(), "it returned while the installer still waits")
        # What the updater's switch then reads: the records of its layout naming Y's server environment.
        record = installations.current()
        self.assertEqual((record["version"], record["prefix"]), (Y, str(places.code_dir(Y) / "server")))
        self.assertEqual(installations.proxy_status(), installations.OK)
        released.write_text("", encoding="utf-8")
        deadline = began + 60
        while not ran.exists():
            self.assertLess(time.monotonic(), deadline, "the installer ran")
            time.sleep(0.02)
        self.assertEqual(ran.read_text(encoding="utf-8"), "ran\n", "started once")
        self.no_app_touched()

    def test_an_empty_installer_starts_nothing(self) -> None:
        with mock.patch.object(subprocess, "Popen") as started:
            self.assertIsNone(setup.start_installer())
        started.assert_not_called()
        with mock.patch.dict(os.environ, {setup.INSTALLER_ENV: "printf ok"}), \
                mock.patch.object(subprocess, "Popen") as started:
            setup.start_installer()
        self.assertEqual(started.call_args.args[0], ["printf", "ok"])
        self.assertIs(started.call_args.kwargs["stdout"], subprocess.DEVNULL, "its output read by no one")
        os.environ.pop(setup.INSTALLER_ENV)
        self.assertEqual(setup.installer(), ["sh", "-c", "curl -fsSL https://texttocad.dev/install.sh | sh"])


class Uninstall(Servers, Computer):
    def test_everything_of_cad_goes_its_server_stopped_first_and_nothing_else(self) -> None:
        self.legacy()  # what 0.11.10 left: its records, its flat release, its cache
        self.version(X)
        self.start(X)
        self.assertIn(installations.write_proxy()[1], (installations.MISSING, installations.STALE))
        beside = self.state.parent / "kept.txt"
        beside.write_text("not cad's", encoding="utf-8")
        code, out, err = self.main(uninstall, ["--yes"])
        self.assertEqual(code, 0, out + err)
        self.assertIsNone(versions.ask(X, {"op": "pid"}, seconds=2.0), "its server stopped")
        for gone in (self.state, self.cache, Path(installations.proxy_path())):
            self.assertFalse(gone.exists(), gone)
        self.assertTrue(beside.exists())
        self.no_app_touched()
        code, out, _err = self.main(uninstall, ["--yes"])
        self.assertEqual((code, out), (0, "cad is not installed on this computer: nothing to remove.\n"))

    def test_nobody_to_ask_and_no_yes_changes_nothing(self) -> None:
        self.version(X)
        with mock.patch.object(sys, "stdin", io.StringIO()):
            code, _out, err = self.main(uninstall, [])
        self.assertEqual(code, 2, err)
        self.assertTrue(places.version_dir(X).is_dir())


if __name__ == "__main__":
    unittest.main()
