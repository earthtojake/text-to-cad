"""``cad setup``, its hidden ``--engine-update``, and ``cad uninstall`` (``cad_server.cli.setup``, ``uninstall``).

``cad setup`` sets up the version that runs it -- its folder, its server, the check that it runs, its kernel, its
marker, and the ``cad`` command --, then starts that version's server (a real one in ``Serving``; elsewhere the start
is recorded), and knows no app: a home of the test's own holds agent apps' folders and stand-ins
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
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.python.packages.cad_server.test_version_servers import WAIT, Servers
from tests.python.packages.cad_server.test_versions import OLD, Device

from cad.engine import client, places
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
    def test_a_command_of_another_s_fails_setup_but_never_the_updater_s_run(self) -> None:
        command = Path(installations.proxy_path())
        command.parent.mkdir()
        command.write_text("#!/bin/sh\necho someone else's cad\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {places.INSTALLATION_ENV: DEV}):
            code, out, err = self.main(setup, [])
            self.assertEqual(code, 1, out + err)
            self.assertIn("is not cad's, and is left alone", err)
            with mock.patch.object(places, "versioned", return_value=DEV), \
                    mock.patch.object(setup, "start_installer") as started:
                code, out, err = self.main(setup, ["--engine-update"])
        self.assertEqual(code, 0, out + err)
        self.assertIn("is not cad's, and is left alone", err)
        started.assert_called_once_with(DEV)
        self.assertEqual(installations.current_version(), DEV, "the hand-over done all the same")
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
            self.served.assert_not_called()  # and starts Y's: none started here
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


class Installer(unittest.TestCase):
    def test_a_command_of_quoted_paths_with_spaces_starts_on_every_platform(self) -> None:
        # Windows's rehearsal named its stand-in this way and it never started: the quotes were kept in each word.
        folder = Path(tempfile.mkdtemp(prefix="cad installer "))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        stand_in, ran = folder / "stand in.py", folder / "it ran"
        stand_in.write_text("import pathlib, sys\npathlib.Path(sys.argv[1]).write_text('ran', encoding='utf-8')\n",
                            encoding="utf-8")
        with mock.patch.dict(os.environ, {setup.INSTALLER_ENV: f'"{sys.executable}" "{stand_in}" "{ran}"'}):
            self.assertIsNotNone(setup.start_installer())
        deadline = time.monotonic() + 60
        while not ran.exists():
            self.assertLess(time.monotonic(), deadline, "the installer ran")
            time.sleep(0.02)


class Site:
    """A stand-in for the docs site: ``install.py`` served from a local port, its text what ``pages`` holds next (each
    ask takes the next; the last stays), or not found while that is None."""

    def __init__(self, test: unittest.TestCase, *pages: str | None) -> None:
        import http.server

        self.pages, self.asked = list(pages), 0
        site = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - the standard library's name
                site.asked += 1
                page = site.pages.pop(0) if len(site.pages) > 1 else site.pages[0]
                if page is None:
                    self.send_error(404)
                    return
                body = page.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args) -> None:
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        test.addCleanup(self.server.server_close)
        test.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/install.py"


def install_py(fallback: str) -> str:
    return f'#!/usr/bin/env python3\n"""The installer."""\nFALLBACK = "{fallback}"\n'


class InstallerWaits(unittest.TestCase):
    """The install script ``--engine-update`` starts waits until the site's install.py names this release: the site
    is deployed after the version feed names it (``cad_server._internal.install_script``)."""

    def test_it_waits_for_the_site_to_name_this_release_and_gives_up_once_its_delays_are_spent(self) -> None:
        from cad_server._internal import install_script

        slept: list[float] = []
        site = Site(self, None, install_py("0.11.10"), install_py(Y))
        self.assertTrue(install_script.wait(site.url, Y, delays=(1.0, 2.0, 4.0, 8.0), sleep=slept.append))
        self.assertEqual((site.asked, slept), (3, [1.0, 2.0]), "not found, then the release before, then this one")
        for named, version, ready in ((Y, f"{Y}-dev.20261115000000", True), ("0.13.0", Y, True),
                                      ("0.12.0", Y, False), ("0.12", "0.12.0", True)):
            with self.subTest(named=named, version=version):
                self.assertEqual(install_script.serves(Site(self, install_py(named)).url, version), ready)
        slept.clear()
        site = Site(self, install_py("0.11.10"))
        self.assertFalse(install_script.wait(site.url, Y, delays=(1.0, 2.0), sleep=slept.append))
        self.assertEqual((site.asked, slept), (3, [1.0, 2.0]), "asked at once and after each delay, then no more")
        self.assertFalse(install_script.serves("http://127.0.0.1:9/install.py", Y), "an address that does not answer")
        self.assertEqual(install_script.main([Y, "http://127.0.0.1:9/install.py"]), 0, "no command: nothing run")

    def test_the_updater_s_installer_starts_detached_once_the_site_names_this_release(self) -> None:
        folder = Path(tempfile.mkdtemp(prefix="cad installer "))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        stand_in, ran = folder / "stand in.py", folder / "it ran"
        stand_in.write_text("import pathlib, sys\npathlib.Path(sys.argv[1]).write_text('ran', encoding='utf-8')\n",
                            encoding="utf-8")
        site = Site(self, install_py(Y))
        with mock.patch.dict(os.environ, {setup.INSTALLER_ENV: f'"{sys.executable}" "{stand_in}" "{ran}"',
                                          setup.INSTALL_PY_ENV: site.url}):
            self.assertIsNotNone(setup.start_installer(Y))
        deadline = time.monotonic() + 60
        while not ran.exists():
            self.assertLess(time.monotonic(), deadline, "the installer ran")
            time.sleep(0.02)
        self.assertGreaterEqual(site.asked, 1, "the site was asked first")
        # The hosted script waits for the site's install.py; a test's stand-in waits for none unless told one.
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(setup.INSTALLER_ENV, None)
            os.environ.pop(setup.INSTALL_PY_ENV, None)
            self.assertEqual(setup.install_py(), "https://www.texttocad.dev/install.py")
            os.environ[setup.INSTALLER_ENV] = "printf ok"
            self.assertIsNone(setup.install_py())


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
