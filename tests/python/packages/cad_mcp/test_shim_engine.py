"""The stdio transport reaches the device's server on its own (``cad_mcp.engine``): it starts the current
installation's, whatever release it is itself; on a device with none current it registers one first -- the
server its own environment carries, else its own release's, installed by uvx -- and with none at all it says
how to install one. Nothing is started for real: ``Popen`` and ``run`` are stood in for."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import cad_mcp
from cad_mcp import engine


class Started(Exception):
    """What the stood-in ``Popen`` raises: nothing starts."""


class StartTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="shim-engine-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.state = self.root / "state"
        self.elsewhere = self.root / "elsewhere"
        patched = mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.state), "CAD_ENGINE_DIR": str(self.root / "engine"),
                                               "CAD_CACHE_DIR": str(self.root / "cache"),
                                               "PYTHONPATH": "/a/checkout/src", "DO_NOT_TRACK": "1"})
        patched.start()
        self.addCleanup(patched.stop)

    def installed(self, version: str = "9.9.9") -> dict:
        """An installation registered and current, its Python and console script there."""
        bin_ = self.elsewhere / "bin"
        bin_.mkdir(parents=True, exist_ok=True)
        python, console = bin_ / "python", bin_ / "cad"
        for path in (python, console):
            path.write_text("", encoding="utf-8")
        record = {"version": version, "python": str(python), "cad": str(console), "prefix": str(self.elsewhere)}
        folder = self.state / "installations"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{version}.json").write_text(json.dumps(record), encoding="utf-8")
        (folder / "current").write_text(version, encoding="utf-8")
        return record

    def started(self) -> tuple[list[str], dict]:
        with mock.patch.object(subprocess, "Popen", side_effect=Started) as popen, self.assertRaises(Started):
            engine._start()
        [call] = popen.call_args_list
        return call.args[0], call.kwargs

    def test_the_current_installation_s_server_starts_with_its_own_python(self) -> None:
        record = self.installed()
        with mock.patch.object(engine, "register") as registered:
            argv, options = self.started()
        registered.assert_not_called()
        self.assertEqual(argv, [record["python"], "-P", "-m", engine.DAEMON_MODULE])
        env = options["env"]
        self.assertNotIn("PYTHONPATH", env, "another installation imports its own server")
        self.assertNotIn("DO_NOT_TRACK", env, "a switch of this process's alone")
        self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1", "nothing written beside a library")

    def test_a_device_with_none_current_registers_one_first(self) -> None:
        with mock.patch.object(engine, "register", side_effect=lambda: self.installed("1.2.3")) as registered:
            argv, _options = self.started()
        registered.assert_called_once()
        self.assertEqual(argv[0], str(self.elsewhere / "bin" / "python"))

    def test_registering_runs_the_server_here_else_installs_this_release_with_uvx(self) -> None:
        with mock.patch.object(engine.importlib.util, "find_spec", return_value=object()), \
                mock.patch.object(subprocess, "run") as ran:
            engine.register()
        self.assertEqual(ran.call_args.args[0], [sys.executable, "-P", "-m", engine.REGISTER])
        with mock.patch.object(engine.importlib.util, "find_spec", return_value=None), \
                mock.patch.object(subprocess, "run") as ran:
            engine.register()
        self.assertEqual(ran.call_args.args[0], [*engine.LAUNCHER, f"{engine.SERVER}=={cad_mcp.__version__}", "python",
                                                 "-P", "-m", engine.REGISTER])
        for name in ("stdin", "stdout", "stderr"):
            self.assertEqual(ran.call_args.kwargs[name], subprocess.DEVNULL, "its words are nobody's here")

    def test_two_threads_that_find_no_server_start_and_register_one(self) -> None:
        # The hold and the host's first request both find no server on a device's first start: the
        # second waits for the first one's start and takes its server, so one registration runs.
        up = threading.Event()
        looked = threading.Barrier(2, timeout=30)
        answers = iter(range(2))  # the first look of each thread meets the other before either starts

        def connected(where=None):
            if next(answers, None) is not None:
                looked.wait()
            return "connection" if up.is_set() else None

        class Process:
            def poll(self):
                return None

        def started(*_args, **_kwargs):
            up.set()
            return Process()

        found: list = []
        with mock.patch.object(engine, "_connect", side_effect=connected), \
                mock.patch.object(engine, "register", side_effect=lambda: self.installed("1.2.3")) as registered, \
                mock.patch.object(subprocess, "Popen", side_effect=started) as popen:
            threads = [threading.Thread(target=lambda: found.append(engine.connect(timeout=30))) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(60)
        self.assertEqual(found, ["connection", "connection"])
        self.assertEqual((registered.call_count, popen.call_count), (1, 1))

    def test_with_no_server_anywhere_it_says_how_to_install_one(self) -> None:
        with mock.patch.object(engine, "register"), \
                mock.patch.object(engine.importlib.util, "find_spec", return_value=None), \
                self.assertRaisesRegex(ConnectionError, "run the install command"):
            engine._start()



class DoorTest(unittest.TestCase):
    """The transport's own copy of the door's client half (it does not import the library) says the
    library's hello and reads its greeting: in protocol 1 through the door's pipes and on Windows' port,
    and a greeting it does not speak -- 0.8's bare ``ok`` among them -- refused."""

    def test_its_hello_and_greeting_are_the_library_s(self) -> None:
        from cad.engine import door

        ident = "0123456789abcdef" * 2
        self.assertEqual((engine.DOOR_PROTOCOL, engine.hello(ident)), (door.DOOR_PROTOCOL, door.hello(ident)))
        for line in (b"ok\n", b"ok 0\n", b"ok 1\n", b"ok 1", b"ok 2 later\n", b"ok \n", b"ok one\n", b"no\n", b""):
            self.assertEqual(engine.greeted(line), door.greeted(line), line)

    @unittest.skipIf(os.name == "nt", "the door's pipes are POSIX's")
    def test_it_dials_the_door_in_its_protocol_and_refuses_0_8_s_bare_greeting(self) -> None:
        from cad.engine import door

        folder = Path(tempfile.mkdtemp(prefix="shim-door-"))
        self.addCleanup(shutil.rmtree, folder, True)
        heard: list[int] = []

        def library(ident: str, protocol: int) -> None:
            heard.append(protocol)
            door.answer(folder / door.CLIENTS, ident, lambda reader, writer: reader.readline(), protocol)

        def greets(greeting: bytes):
            def answer(ident: str, _protocol: int) -> None:
                up, down = door.pair(folder / door.CLIENTS, ident)
                writer = os.open(down, os.O_WRONLY | os.O_NONBLOCK)
                os.close(os.open(up, os.O_RDONLY | os.O_NONBLOCK))
                os.write(writer, greeting)  # an engine that greets so, and goes
                os.close(writer)
            return answer

        for on_hello, protocol in ((library, 1), (greets(b"ok\n"), None), (greets(b"ok 2\n"), None)):
            opened = door.Door(folder / "engine.door", on_hello)
            self.addCleanup(opened.close)
            connection = engine.dial(opened.path, timeout=5)
            if protocol is None:
                self.assertIsNone(connection, "a protocol it does not speak")
            else:
                self.assertIsNotNone(connection)
                self.assertEqual(connection.protocol, protocol)
                connection.close()
            opened.close()
        self.assertEqual(heard, [1], "the engine heard protocol 1")

    def test_on_windows_it_says_hello_at_the_port_and_is_greeted_and_served(self) -> None:
        import socket
        import types

        from cad_server.engine import daemon

        token = "ab" * 16
        folder = Path(tempfile.mkdtemp(prefix="shim-port-"))
        self.addCleanup(shutil.rmtree, folder, True)
        port_file = folder / "engine.port"
        listener = socket.create_server(("127.0.0.1", 0))  # any free port, never the engine's
        self.addCleanup(listener.close)
        port_file.write_text(f"{listener.getsockname()[1]} {token}\n", encoding="utf-8")
        handled: list[dict] = []
        server = types.SimpleNamespace(token=token, refusal=None, unsaid="",
                                       handle=lambda request, send: handled.append(request) or send({"ok": True}))

        def accept() -> None:
            connection, _address = listener.accept()
            daemon._serve_connection(server, connection)

        accepting = threading.Thread(target=accept)
        accepting.start()
        with mock.patch.object(engine, "WINDOWS", True), mock.patch.object(daemon, "WINDOWS", True):
            connection = engine._connect(port_file)
            self.assertIsNotNone(connection)
            self.assertEqual(connection.protocol, 1)
            self.assertEqual(engine._exchange(connection, {"op": "status"}, port_file), {"ok": True})
        accepting.join(timeout=30)
        self.assertEqual(handled, [{"token": token, "op": "status"}])


class PinTest(unittest.TestCase):
    """A transport of a version reaches that version's server and no other: its ``--channel``, its version made
    ready at start (installed where it is not, then its channel moved by that version's own ``cad``), and the line
    every tool call answers once its channel moved past it. Nothing runs for real: ``run`` is stood in for."""

    X, Y = "0.12.0", "0.12.1"

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="shim-pin-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.state, self.engines = self.root / "state", self.root / "engines"
        patched = mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.state), "CAD_ENGINE_DIR": str(self.engines),
                                               "CAD_INSTALLATION_VERSION": ""})
        patched.start()
        self.addCleanup(patched.stop)
        pinned = mock.patch.object(engine, "PIN", engine.Pin())
        pinned.start()
        self.addCleanup(pinned.stop)
        self.ran: list[list[str]] = []

    def installed(self, version: str) -> dict:
        """Version ``version`` present: its installed marker, its Python and ``cad`` there."""
        code = self.state / "versions" / version / "code"
        (code / "server" / "bin").mkdir(parents=True, exist_ok=True)
        record = {"schema": "cad version/1", "version": version, "python": str(code / "server" / "bin" / "python"),
                  "cad": str(code / "server" / "bin" / "cad"), "prefix": str(code / "server")}
        for script in ("python", "cad"):
            (code / "server" / "bin" / script).write_text("", encoding="utf-8")
        (code / "cad-version.json").write_text(json.dumps(record), encoding="utf-8")
        return record

    def point(self, version: str, channel: str | None = None) -> None:
        path = self.state / ("default" if channel is None else f"channels/{channel}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{version}\n", encoding="utf-8")

    def run_as(self, answers):
        """``subprocess.run`` stood in for: each command recorded, answered by ``answers(command)``: ``(code,
        stderr)``."""
        def run(command, **_kwargs):
            self.ran.append(list(command))
            code, said = answers(command)
            return subprocess.CompletedProcess(command, code, "", said)

        return mock.patch.object(subprocess, "run", run)

    def pinned(self, channel: str | None = None) -> engine.Pin:
        with mock.patch.object(engine, "own_version", return_value=self.X):
            return engine.configure(channel)

    def test_the_channel_is_an_argument_of_the_server_config(self) -> None:
        from cad_mcp import shim

        for args, expected in (([], None), (["--channel", "codex"], "codex"), (["--channel=codex"], "codex"),
                               (["--channel", "default"], None)):
            with self.subTest(args=args):
                self.assertEqual(shim.arguments(args), expected)
        for args in (["--channel", "Not a channel"], ["--channel"], ["--other"], ["--channel=@"]):
            with self.subTest(args=args), self.assertRaises(ValueError):
                shim.arguments(args)
        with mock.patch.object(sys, "stderr", io.StringIO()) as err:
            self.assertEqual(shim.main(["--channel", "Bad"]), 2)
        self.assertIn("not a channel", err.getvalue())

    def test_its_version_is_its_own_release_and_a_source_tree_has_none(self) -> None:
        self.assertIsNone(engine.own_version(), "this checkout's transport: no version, the flat door")
        with mock.patch.object(cad_mcp, "source_tree", return_value=False), \
                mock.patch.object(cad_mcp, "_version", return_value=self.X):
            self.assertEqual(engine.own_version(), self.X)
        with mock.patch.dict(os.environ, {"CAD_INSTALLATION_VERSION": f"{self.X}-dev.20261113000000"}):
            self.assertEqual(engine.own_version(), f"{self.X}-dev.20261113000000", "a development install's build")

    def test_present_and_its_channel_on_it_nothing_runs(self) -> None:
        self.installed(self.X)
        self.point(self.X, "codex")
        pin = self.pinned("codex")
        with self.run_as(lambda command: self.fail(f"nothing runs: {command}")):
            engine.prepare(pin)
        self.assertTrue(pin.ready.is_set())
        self.assertEqual((pin.failed, pin.stale, engine.stale()), (None, None, None))

    def test_absent_it_is_installed_with_uvx_then_its_own_cad_moves_its_channel(self) -> None:
        pin = self.pinned("codex")

        def answers(command):
            if command[0] == "uvx":
                self.installed(self.X)
                return 0, ""
            self.point(self.X, "codex")
            return 0, ""

        with self.run_as(answers):
            engine.prepare(pin)
        record = engine.version_record(self.X)
        self.assertEqual(self.ran, [[*engine.LAUNCHER, f"cad-server=={self.X}", "cad", "setup", "--add", "--quiet"],
                                    [record["cad"], f"+{self.X}@codex", "setup", "--add", "--quiet"]])
        self.assertEqual((pin.failed, pin.stale), (None, None))

    def test_absent_and_not_installable_says_how_to_install_it(self) -> None:
        pin = self.pinned()
        with self.run_as(lambda command: (2, "error: Failed to fetch: dns error")):
            engine.prepare(pin)
        self.assertEqual(len(self.ran), 1)
        self.assertIn("could not be installed here (error: Failed to fetch: dns error)", pin.failed)
        self.assertTrue(pin.failed.endswith(engine.add_command(self.X)))
        with self.assertRaises(ConnectionError) as said:
            engine.connect()
        self.assertEqual(str(said.exception), pin.failed)

    def test_stale_at_start_and_once_its_channel_moves_on(self) -> None:
        self.installed(self.X)
        self.point(self.Y)
        pin = self.pinned()
        with self.run_as(lambda command: (engine.STALE_EXIT, "cad: this command is for text-to-cad 0.12.0, ...")):
            engine.prepare(pin)
        line = f"this CAD app is text-to-cad {self.X}, and its channel (default) is on text-to-cad {self.Y} now: " \
               "start a new thread to use it"
        self.assertEqual((pin.stale, engine.stale()), (line, line))
        moving = self.pinned("codex")
        self.point(self.X, "codex")
        with self.run_as(lambda command: self.fail("on its channel's version: nothing runs")):
            engine.prepare(moving)
        self.assertIsNone(engine.stale())
        self.point(self.Y, "codex")  # its channel updated while the thread stayed open
        self.assertEqual(engine.stale(), line.replace("(default)", "(codex)"))

    def test_a_stale_thread_s_tool_call_is_answered_with_the_line_and_nothing_is_sent(self) -> None:
        from cad_mcp.protocol import RequestContext
        from cad_mcp.shim import Proxy

        self.installed(self.X)
        self.point(self.Y)
        self.pinned().ready.set()

        class Client:
            def call(self, *args, **kwargs):
                raise AssertionError("nothing is sent")

        answer = Proxy(client=Client()).handle("tools/call", {"name": "cad_show", "arguments": {}},
                                               RequestContext(1, {}))
        self.assertTrue(answer["isError"])
        self.assertIn("start a new thread", answer["content"][0]["text"])

    def test_an_initialize_while_its_version_installs_is_answered_and_the_session_opened_next(self) -> None:
        from cad_mcp import shim
        from cad_mcp.protocol import RequestContext

        self.pinned()  # not ready: being installed
        sent: list[str] = []

        class Client:
            def call(self, method, path, body=b"", headers=None, **_kwargs):
                message = json.loads(body)
                sent.append(message.get("method"))
                if message.get("method") == "initialize":
                    return 200, {"Mcp-Session-Id": "s1"}, json.dumps(
                        {"jsonrpc": "2.0", "id": message["id"], "result": {"protocolVersion": "2025-06-18"}}).encode()
                if "id" not in message:
                    return 202, {}, b""
                return 200, {}, json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": {"tools": []}}).encode()

        proxy = shim.Proxy(client=Client())
        with mock.patch.object(shim, "INITIALIZE_SECONDS", 0.01):
            greeting = proxy.handle("initialize", {"protocolVersion": "2025-06-18"}, RequestContext(1, {}))
        self.assertEqual((greeting["serverInfo"]["name"], greeting["serverInfo"]["version"]), ("cad", self.X))
        proxy.notify("notifications/initialized", {})
        self.assertEqual(sent, [], "nothing reaches the server before the version is ready")
        engine.PIN.ready.set()
        self.assertEqual(proxy.handle("tools/list", {}, RequestContext(2, {})), {"tools": []})
        self.assertEqual(sent, ["initialize", "notifications/initialized", "tools/list"])

    def test_it_reaches_its_own_version_s_door_and_starts_that_version_alone(self) -> None:
        self.installed(self.Y)
        other = self.root / "elsewhere"
        (other / "bin").mkdir(parents=True)
        (other / "bin" / "python").write_text("", encoding="utf-8")
        (other / "bin" / "cad").write_text("", encoding="utf-8")
        folder = self.state / "installations"
        folder.mkdir(parents=True)
        (folder / f"{self.Y}.json").write_text(json.dumps({"version": self.Y, "python": str(other / "bin" / "python"),
                                                          "cad": str(other / "bin" / "cad"), "prefix": str(other)}),
                                               encoding="utf-8")
        (folder / "current").write_text(self.Y, encoding="utf-8")
        self.pinned().ready.set()
        self.assertEqual(engine.engine_dir(), self.engines.resolve() / self.X)
        with self.assertRaises(ConnectionError) as said:
            engine._start()  # not installed: never the current installation's, nor another version's
        self.assertIn(f"text-to-cad {self.X} is not installed", str(said.exception))
        record = self.installed(self.X)
        with mock.patch.object(subprocess, "Popen", side_effect=Started) as popen, self.assertRaises(Started):
            engine._start()
        [call] = popen.call_args_list
        self.assertEqual(call.args[0][0], record["python"])
        self.assertEqual(call.kwargs["env"]["CAD_INSTALLATION_VERSION"], self.X)


class SameFoldersTest(unittest.TestCase):
    """The transport's copy of the library's folder rules (``cad.engine.places``, which it does not import)
    names the same folders: the state folder, a version's folder, the engines' folder and a version's engine
    folder, overridden or not."""

    def test_the_copies_name_the_same_folders(self) -> None:
        from cad.engine import places

        root = Path(tempfile.mkdtemp(prefix="shim-places-"))
        self.addCleanup(shutil.rmtree, root, True)
        settings = [{"CAD_STATE_DIR": "", "CAD_ENGINE_DIR": "", "XDG_STATE_HOME": "", "XDG_RUNTIME_DIR": ""},
                    {"CAD_STATE_DIR": str(root / "state"), "CAD_ENGINE_DIR": str(root / "engines")},
                    {"CAD_STATE_DIR": "", "CAD_ENGINE_DIR": "", "XDG_STATE_HOME": str(root / "xdg")}]
        for environment in settings:
            with self.subTest(environment), mock.patch.dict(os.environ, environment):
                self.assertEqual(engine.state_dir(), places.state_dir())
                self.assertEqual(engine.default_engine_dir(), places.default_engine_dir())
                self.assertEqual(engine.engines_dir(), places.engines_dir())
                self.assertEqual(engine.engine_dir(), places.engines_dir(), "the flat door, which this transport reaches")
                for version in ("0.12.0", "0.12.0-dev.20261113120000"):
                    self.assertEqual(engine.version_dir(version), places.version_dir(version))
                    self.assertEqual(engine.engine_dir(version), places.engine_dir(version))
        for name in ("..", "../x", ""):
            with self.subTest(name), self.assertRaises(ValueError):
                engine.version_dir(name)

    def test_the_copies_of_the_server_s_rules_say_what_the_server_does(self) -> None:
        from cad.engine import places
        from cad_server._internal import cli_errors, pins, pointers, versions

        self.assertEqual((engine.CHANNEL, engine.DEFAULT_CHANNEL), (places.CHANNEL.pattern, places.DEFAULT_CHANNEL))
        self.assertEqual((engine.VERSION, engine.RELEASED), (places.VERSION.pattern, pins.RELEASED.pattern))
        self.assertEqual((engine.VERSION_MARKER, engine.VERSION_SCHEMA), (places.VERSION_MARKER, places.VERSION_SCHEMA))
        self.assertEqual((engine.INSTALLATION_ENV, engine.STALE_EXIT),
                         (places.INSTALLATION_ENV, cli_errors.REASONS["stale_pin"]))
        for system in ("posix", "nt"):
            self.assertEqual(engine.add_command("0.12.0", system), versions.add_command("0.12.0", system))
        root = Path(tempfile.mkdtemp(prefix="shim-rules-"))
        self.addCleanup(shutil.rmtree, root, True)
        with mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(root)}):
            for channel in (None, "codex"):
                self.assertIsNone(engine.pointer(channel))
                pointers.write(channel, "0.12.0", mirrored=False)
                self.assertEqual(engine.pointer(channel), pointers.read(channel))
            code = root / "versions" / "0.12.0" / "code"
            (code / "bin").mkdir(parents=True)
            for script in ("python", "cad"):
                (code / "bin" / script).write_text("", encoding="utf-8")
            marker = {"schema": places.VERSION_SCHEMA, "version": "0.12.0", "python": str(code / "bin" / "python"),
                      "cad": str(code / "bin" / "cad"), "prefix": str(code)}
            (code / places.VERSION_MARKER).write_text(json.dumps(marker), encoding="utf-8")
            self.assertEqual(engine.version_record("0.12.0"), places.version_record("0.12.0"))
            self.assertIsNone(engine.version_record("0.12.1"))


if __name__ == "__main__":
    unittest.main()
