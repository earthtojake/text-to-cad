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

    def test_a_server_that_stops_answering_never_holds_a_request(self) -> None:
        # B11: each line the door is asked for is waited for DOOR_SECONDS at most, through the pipes and the port.
        import socket

        folder = Path(tempfile.mkdtemp(prefix="shim-silent-"))
        self.addCleanup(shutil.rmtree, folder, True)
        port_file = folder / "engine.port"
        port_file.write_text(f"1 {'ab' * 16}\n", encoding="utf-8")
        mine, theirs = socket.socketpair()
        self.addCleanup(theirs.close)
        stream = mine.makefile("rwb")
        connections = [(True, engine.Connection(stream, stream, stream, mine))]
        if os.name != "nt":
            down, up = os.pipe(), os.pipe()  # a server that took the request and says nothing
            self.addCleanup(os.close, down[1])
            self.addCleanup(os.close, up[0])
            connections.append((False, engine.Connection(open(down[0], "rb"), open(up[1], "wb"))))
        for windows, connection in connections:
            with self.subTest(windows=windows), mock.patch.object(engine, "WINDOWS", windows), \
                    mock.patch.object(engine, "DOOR_SECONDS", 0.05):
                said: list = []
                asking = threading.Thread(target=lambda: said.append(
                    self.assertRaises(ConnectionError, engine._exchange, connection, {"op": "http"}, port_file)),
                    daemon=True)
                asking.start()
                asking.join(30)
                self.assertFalse(asking.is_alive(), "the request was answered")
                self.assertEqual(len(said), 1)

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

    def pinned(self, channel: str | None = None, version: str | None = None) -> engine.Pin:
        with mock.patch.object(engine, "own_version", return_value=version or self.X):
            return engine.configure(channel)

    def proxy(self):
        """A ``Proxy`` whose client fails any call: nothing may reach a server."""
        from cad_mcp import shim

        class Client:
            def call(self, *args, **kwargs):
                raise AssertionError(f"nothing is sent: {args}")

        return shim.Proxy(client=Client())

    def test_the_channel_is_an_argument_of_the_server_config(self) -> None:
        from cad_mcp import shim

        for args, expected in (([], (None, None)), (["--channel", "codex"], ("codex", None)),
                               (["--channel=codex"], ("codex", None)), (["--channel", "default"], (None, None)),
                               (["--channel", "codex", "--startup-timeout", "300"], ("codex", 300.0)),
                               (["--startup-timeout=12.5"], (None, 12.5))):
            with self.subTest(args=args):
                self.assertEqual(shim.arguments(args), expected)
        for args in (["--channel", "Not a channel"], ["--channel"], ["--other"], ["--channel=@"], ["--startup-timeout"],
                     ["--startup-timeout", "0"], ["--startup-timeout=-5"], ["--startup-timeout", "soon"],
                     ["--startup-timeout=nan"], ["--startup-timeout", "inf"]):
            with self.subTest(args=args), self.assertRaises(ValueError):
                shim.arguments(args)
        for args, said in ((["--channel", "Bad"], "not a channel"), (["--startup-timeout", "0"], "not a startup timeout")):
            with self.subTest(args=args), mock.patch.object(sys, "stderr", io.StringIO()) as err:
                self.assertEqual(shim.main(args), 2)
            self.assertIn(said, err.getvalue())

    def test_the_initialize_waits_for_its_version_as_long_as_its_app_waits_for_it_to_start(self) -> None:
        # Codex acts on no list_changed within a turn: a thread whose initialize is answered by the placeholder greeting
        # before the version is installed never gets its tools in that turn. Where its config says how long the app
        # waits (`--startup-timeout`), the initialize waits 80% of it, never less than 20 seconds.
        from cad_mcp import shim
        from cad_mcp.protocol import RequestContext

        for startup, seconds in ((None, 20.0), (300.0, 240.0), (30.0, 24.0), (10.0, 20.0)):
            with self.subTest(startup=startup):
                self.assertEqual(shim.initialize_seconds(startup), seconds)
                asked: list = []
                proxy = shim.Proxy(client=object(), startup=startup)
                with mock.patch.object(engine, "unavailable",
                                       side_effect=lambda wait: asked.append(wait) or (engine.INSTALLING, "")):
                    proxy.handle("initialize", {"protocolVersion": "2025-06-18"}, RequestContext(1, {}))
                self.assertEqual(asked, [seconds])

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

    def test_stale_once_its_channel_moves_on_and_where_its_own_cad_says_so(self) -> None:
        self.installed(self.X)
        moving = self.pinned("codex")
        self.point(self.X, "codex")
        with self.run_as(lambda command: self.fail("on its channel's version: nothing runs")):
            engine.prepare(moving)
        self.assertIsNone(engine.stale())
        self.point(self.Y, "codex")  # its channel updated while the thread stayed open
        self.assertEqual(engine.stale(), engine.stale_line(self.X, "codex", self.Y))
        # Its own version's cad finds the channel past it as it moves it (another moved it meanwhile): stale.
        pin = self.pinned()
        with self.run_as(lambda command: (self.point(self.Y), (engine.STALE_EXIT, "cad: this command is ..."))[1]):
            engine.prepare(pin)
        self.assertEqual((pin.stale, engine.stale()), (engine.stale_line(self.X, None, self.Y),) * 2)

    def test_stale_means_its_channel_is_on_a_newer_version_never_an_older_one(self) -> None:
        # B5: a launcher newer than its channel's pointer (a store just updated the plugin) is the channel's next
        # version, never stale; one older than it is.
        self.pinned(version=self.Y).ready.set()
        for pointed, stale in ((self.X, False), (f"{self.Y}-dev.20261113000000", True), ("0.13.0rc1", True),
                               ("0.12.1rc1", False), (self.Y, False)):
            with self.subTest(pointed=pointed):
                self.point(pointed)
                self.assertEqual(engine.stale(), engine.stale_line(self.Y, None, pointed) if stale else None)

    def test_a_launcher_newer_than_its_channel_says_it_is_being_installed_never_stale(self) -> None:
        # B5: while it installs its version and moves its channel to it, a tool call is told its version is being
        # installed and to try again shortly; nothing reaches a server, and the thread is never called stale.
        from cad_mcp.protocol import RequestContext

        self.point(self.X, "codex")
        pin = self.pinned("codex", version=self.Y)
        installing, go = threading.Event(), threading.Event()

        def answers(command):
            if command[0] == "uvx":
                installing.set()
                self.assertTrue(go.wait(30))
                self.installed(self.Y)
            else:
                self.point(self.Y, "codex")
            return 0, ""

        with self.run_as(answers), mock.patch.object(engine, "READY_SECONDS", 0.01):
            preparing = threading.Thread(target=engine.prepare, args=(pin,))
            preparing.start()
            self.addCleanup(preparing.join, 30)
            self.addCleanup(go.set)
            self.assertTrue(installing.wait(30))
            self.assertIsNone(engine.stale())
            answer = self.proxy().handle("tools/call", {"name": "cad_show", "arguments": {}}, RequestContext(1, {}))
            self.assertEqual(answer, {"content": [{"type": "text", "text": engine.installing_line(self.Y)}],
                                      "isError": True})
            self.assertEqual(engine.installing_line(self.Y),
                             f"text-to-cad {self.Y} is being installed on this computer: try again shortly")
            go.set()
            preparing.join(30)
        self.assertEqual((pin.ready.is_set(), pin.stale, pin.failed, engine.stale()), (True, None, None, None))

    def test_a_launcher_older_than_its_channel_installs_nothing_and_never_connects(self) -> None:
        # B6: an app still holding an older copy is stale at once, its pointer read first: nothing is installed or
        # run, no server is started or reached, and every request is answered here with the line.
        from cad_mcp.protocol import RequestContext, RpcError

        self.point(self.Y)
        pin = self.pinned()
        with self.run_as(lambda command: self.fail(f"a stale launcher runs nothing: {command}")):
            engine.prepare(pin)
        line = engine.stale_line(self.X, None, self.Y)
        self.assertEqual((pin.ready.is_set(), pin.stale, pin.failed), (True, line, None))
        with mock.patch.object(engine, "_connect", side_effect=AssertionError("never connects")), \
                mock.patch.object(subprocess, "Popen", side_effect=AssertionError("never starts a server")):
            for call in (engine.connect, lambda: engine.connect(start=False), engine.hold):
                with self.assertRaises(ConnectionError) as said:
                    call()
                self.assertEqual(str(said.exception), line)
            proxy = self.proxy()
            for method in ("initialize", "tools/list", "resources/list", "resources/read"):
                with self.subTest(method=method), self.assertRaises(RpcError) as refused:
                    proxy.handle(method, {"uri": "ui://cad/app"}, RequestContext(1, {}))
                self.assertEqual(refused.exception.message, line)
            self.assertEqual(proxy.handle("tools/call", {"name": "cad_show"}, RequestContext(2, {}))["content"][0]["text"],
                             line)
            self.assertEqual(proxy.handle("ping", {}, RequestContext(3, {})), {})
            proxy.notify("notifications/cancelled", {"requestId": 2})  # dropped

    def test_a_server_running_for_a_version_its_channel_left_is_never_reached_again(self) -> None:
        # B6: a launcher made ready before its channel moved on reaches its old server no more, nor restarts it.
        self.installed(self.X)
        self.pinned().ready.set()
        self.point(self.Y)
        with mock.patch.object(engine, "_connect", side_effect=AssertionError("never connects")), \
                self.assertRaises(ConnectionError) as said:
            engine.connect()
        self.assertEqual(str(said.exception), engine.stale_line(self.X, None, self.Y))

    def test_a_channel_taken_off_this_computer_starts_nothing_until_an_install_writes_it_again(self) -> None:
        # `cad uninstall` removed the pointer of the channel this transport's version was on, then stopped its server:
        # every request is answered here with one line, and nothing starts, connects or installs (it used to start the
        # server again within a second). A pointer that is there but cannot be read, or names no version, is not gone;
        # written again, the same transport serves again.
        from cad_mcp.protocol import RequestContext

        self.installed(self.X)
        self.point(self.X)
        pin = self.pinned()
        with self.run_as(lambda command: self.fail(f"on its channel's version: nothing runs: {command}")):
            engine.prepare(pin)
        self.assertEqual((engine.unavailable(), pin.named), (None, True))
        path = self.state / "default"
        path.unlink()
        line = engine.removed_line(self.X, None)
        self.assertEqual(engine.unavailable(), (engine.STALE, line))
        with self.run_as(lambda command: self.fail(f"installs nothing: {command}")), \
                mock.patch.object(engine, "_connect", side_effect=AssertionError("never connects")), \
                mock.patch.object(subprocess, "Popen", side_effect=AssertionError("never starts a server")):
            for call in (engine.connect, engine.hold):
                with self.assertRaises(ConnectionError) as said:
                    call()
                self.assertEqual(str(said.exception), line)
            self.assertEqual(self.proxy().handle("tools/call", {"name": "cad_show", "arguments": {}},
                                                 RequestContext(1, {})),
                             {"content": [{"type": "text", "text": line}], "isError": True})
        for there in (b"", b"not a version\n", None):  # None: a folder, which cannot be read as a file
            with self.subTest(there=there):
                if there is None:
                    path.unlink()
                    path.mkdir()
                else:
                    path.write_bytes(there)
                self.assertIsNone(engine.unavailable(), "there and unreadable: not gone")
        path.rmdir()
        self.assertEqual(engine.unavailable(), (engine.STALE, line))
        self.point(self.X)  # installed again
        self.assertIsNone(engine.unavailable(), "served again")
        self.assertEqual(engine.engine_dir(), self.engines.resolve() / self.X)

    def test_a_channel_never_seen_naming_its_version_is_not_gone(self) -> None:
        # Its first start, still installing: no pointer yet is the channel's first use, never a channel taken off.
        self.pinned()
        self.assertEqual(engine.unavailable()[0], engine.INSTALLING)
        self.assertIsNone(engine.stale())
        # Its own cad moved a named channel to it: from then on, the pointer gone is the channel taken off.
        self.installed(self.X)
        pin = self.pinned("codex")
        with self.run_as(lambda command: (self.point(self.X, "codex"), (0, ""))[1]):
            engine.prepare(pin)
        self.assertIsNone(engine.unavailable())
        (self.state / "channels" / "codex").unlink()
        self.assertEqual(engine.unavailable(), (engine.STALE, engine.removed_line(self.X, "codex")))

    def test_the_line_says_which_version_its_channel_gone_and_the_repair(self) -> None:
        self.assertEqual(engine.removed_line("0.11.11", None, "posix"),
                         "this is text-to-cad 0.11.11, and its channel (default) is not on this computer any more: "
                         "text-to-cad was uninstalled here; run the install command, curl -fsSL "
                         "https://texttocad.dev/install.sh | sh, then start a new thread")
        self.assertIn(f"run the install command, {engine.INSTALL_WINDOWS}, then", engine.removed_line("0.11.11", None, "nt"))
        self.assertEqual(engine.removed_line("0.11.11", "codex"),
                         "this is text-to-cad 0.11.11, and its channel (codex) is not on this computer any more: start "
                         "a new thread, and this app's copy of the text-to-cad plugin installs it again")

    def test_a_thread_open_across_its_channel_s_update_keeps_its_lists(self) -> None:
        # Stale after it listed its tools: the list it had is answered again, each tool then answering the line.
        from cad_mcp.protocol import RequestContext

        self.installed(self.X)
        self.pinned().ready.set()
        proxy = self.proxy()
        tools = {"tools": [{"name": "cad_show"}]}
        with mock.patch.object(proxy, "_post", return_value=tools):
            self.assertEqual(proxy.handle("tools/list", {}, RequestContext(1, {})), tools)
        self.point(self.Y)
        self.assertEqual(proxy.handle("tools/list", {}, RequestContext(2, {})), tools)

    def test_while_its_version_installs_every_request_is_answered_here_within_its_bound(self) -> None:
        # B11: past the initialize, a request never waits on the install: each is answered here in the form its
        # method expects, the lists empty and announced as changed once the version is ready.
        from cad_mcp import shim
        from cad_mcp.protocol import RequestContext, RpcError

        self.pinned()  # not ready: being installed
        told: list[str] = []
        announced = threading.Event()
        proxy = self.proxy()
        proxy.tell = lambda method, params: (told.append(method), len(told) == 2 and announced.set())
        line = engine.installing_line(self.X)
        with mock.patch.object(shim, "INITIALIZE_SECONDS", 0.01), mock.patch.object(engine, "READY_SECONDS", 0.01):
            greeting = proxy.handle("initialize", {"protocolVersion": "2025-06-18"}, RequestContext(0, {}))
            self.assertEqual(greeting["capabilities"], {"tools": {"listChanged": True}, "resources": {"listChanged": True}})
            proxy.notify("notifications/initialized", {})
            proxy.notify("notifications/cancelled", {"requestId": 9})
            for method, answer in (("tools/list", {"tools": []}), ("resources/list", {"resources": []}),
                                   ("resources/templates/list", {"resourceTemplates": []}), ("ping", {}),
                                   ("tools/call", {"content": [{"type": "text", "text": line}], "isError": True})):
                with self.subTest(method=method):
                    self.assertEqual(proxy.handle(method, {}, RequestContext(1, {})), answer)
            for method in ("resources/read", "completion/complete"):
                with self.subTest(method=method), self.assertRaises(RpcError) as refused:
                    proxy.handle(method, {"uri": "ui://cad/app"}, RequestContext(2, {}))
                self.assertEqual((refused.exception.code, refused.exception.message), (shim.UNAVAILABLE, line))
            with self.assertRaises(ConnectionError) as said:
                engine.connect()  # bounded: answered at once, never waiting on the install
            self.assertEqual(str(said.exception), line)
        self.assertEqual(told, [], "nothing is announced before the version is ready")
        engine.PIN.ready.set()
        self.assertTrue(announced.wait(30), told)
        self.assertEqual(told, ["notifications/resources/list_changed", "notifications/tools/list_changed"])

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
        from cad_server import updates
        from cad_server._internal import cli_errors, pins, pointers, versions

        self.assertEqual((engine.CHANNEL, engine.DEFAULT_CHANNEL), (places.CHANNEL.pattern, places.DEFAULT_CHANNEL))
        self.assertEqual((engine.install_command("posix"), engine.install_command("nt")),
                         (updates.INSTALL, updates.INSTALL_WINDOWS))
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
                path = pointers.write(channel, "0.12.0", mirrored=False)
                self.assertEqual(engine.pointer(channel), pointers.read(channel))
                self.assertEqual(engine.pointer_path(channel), path)
            code = root / "versions" / "0.12.0" / "code"
            (code / "bin").mkdir(parents=True)
            for script in ("python", "cad"):
                (code / "bin" / script).write_text("", encoding="utf-8")
            marker = {"schema": places.VERSION_SCHEMA, "version": "0.12.0", "python": str(code / "bin" / "python"),
                      "cad": str(code / "bin" / "cad"), "prefix": str(code)}
            (code / places.VERSION_MARKER).write_text(json.dumps(marker), encoding="utf-8")
            self.assertEqual(engine.version_record("0.12.0"), places.version_record("0.12.0"))
            self.assertIsNone(engine.version_record("0.12.1"))

    def test_it_orders_versions_as_the_server_does(self) -> None:
        from cad_server._internal import versions

        names = ["0.11.10", "0.11.11", "0.11.11-dev.20261113000000", "0.11.11-dev.20261114000000", "0.12.0.dev1",
                 "0.12.0a1", "0.12.0rc1", "0.12.0", "0.12", "0.12.0.post1", "0.12.1", "1.0.0", "1!0.1", "not-a-version"]
        for one in names:
            self.assertEqual(engine.order(one) is None, versions.order(one) is None, one)
            for other in names:
                self.assertEqual(engine.older(one, other), versions.older(one, other), (one, other))

    def test_the_stale_line_says_what_the_cad_command_s_says_then_its_own_repair(self) -> None:
        # What a stale launcher says of its channel is what the cad command says of a stale pin's; the opening is each
        # one's own (the launcher is its version, a command is only for one), and so is the repair: a new thread
        # first here, the skill read again there.
        from cad_server._internal import pins

        for channel, now in ((None, "0.12.1"), ("codex", "0.12.1"), (None, None)):
            with self.subTest(channel=channel, now=now):
                shared = pins.channel_now(channel, now) + ": "
                line = engine.stale_line("0.12.0", channel, now)
                self.assertTrue(line.startswith(f"this is text-to-cad 0.12.0, and {shared}start a new thread; if a new "
                                                "thread says the same, "), line)
                self.assertTrue(pins.stale("0.12.0", channel, now).startswith(
                    f"this command is for text-to-cad 0.12.0, and {shared}read the skill again"))
                self.assertIn("`cad update`" if channel is None else "update the text-to-cad plugin in the app", line)


if __name__ == "__main__":
    unittest.main()
