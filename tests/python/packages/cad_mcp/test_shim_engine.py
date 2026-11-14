"""The stdio transport reaches its own version's server on its own (``cad_mcp.engine``): it installs its version where
it is missing with that release's own line, starts that version's server from its own Python, and a source tree's
(no version) starts the server its environment carries. Nothing is started for real: ``Popen`` is stood in for, and
the install runs a stand-in ``uvx`` that records how it was called."""

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


def started() -> tuple[list[str], dict]:
    with mock.patch.object(subprocess, "Popen", side_effect=Started) as popen:
        try:
            engine._start()
        except Started:
            pass
    [call] = popen.call_args_list
    return call.args[0], call.kwargs


class SourceTreeStartTest(unittest.TestCase):
    """A transport with no version (a checkout's) starts the server its own environment carries, by the flat door."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="shim-engine-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        patched = mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.root / "state"),
                                               "CAD_ENGINE_DIR": str(self.root / "engine"),
                                               "CAD_CACHE_DIR": str(self.root / "cache"),
                                               "PYTHONPATH": "/a/checkout/src", "DO_NOT_TRACK": "1"})
        patched.start()
        self.addCleanup(patched.stop)
        pinned = mock.patch.object(engine, "PIN", engine.Pin())
        pinned.start()
        self.addCleanup(pinned.stop)

    def test_the_server_this_environment_carries_starts_and_none_says_so(self) -> None:
        with mock.patch.object(engine.importlib.util, "find_spec", return_value=object()):
            argv, options = started()
        self.assertEqual(argv, [sys.executable, "-P", "-m", engine.DAEMON_MODULE])
        env = options["env"]
        self.assertEqual(env["PYTHONPATH"], "/a/checkout/src", "its own environment imports its own server")
        self.assertNotIn("DO_NOT_TRACK", env, "a switch of this process's alone")
        self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1", "nothing written beside a library")
        self.assertEqual(engine.engine_dir(), engine.engines_dir(), "the flat door")
        with mock.patch.object(engine.importlib.util, "find_spec", return_value=None), \
                self.assertRaisesRegex(ConnectionError, "no CAD server is installed with this transport"):
            engine._start()

    def test_two_threads_that_find_no_server_start_one(self) -> None:
        # The hold and the host's first request both find no server at first: the second waits for the first one's
        # start and takes its server, so one server starts.
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

        def popen(*_args, **_kwargs):
            up.set()
            return Process()

        found: list = []
        with mock.patch.object(engine, "_connect", side_effect=connected), \
                mock.patch.object(engine.importlib.util, "find_spec", return_value=object()), \
                mock.patch.object(subprocess, "Popen", side_effect=popen) as starts:
            threads = [threading.Thread(target=lambda: found.append(engine.connect(timeout=30))) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(60)
        self.assertEqual(found, ["connection", "connection"])
        self.assertEqual(starts.call_count, 1)


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
        server = types.SimpleNamespace(token=token, refusal=None, unsaid="", ended=lambda request: None,
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
    """A transport of a version reaches that version's server and no other: its version installed at start where it
    is missing, by that release's own line, and every request answered here, never left waiting, while it installs
    or where it could not be installed."""

    X = "0.12.0"

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="shim-pin-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.state, self.engines = self.root / "state", self.root / "engines"
        patched = mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.state), "CAD_ENGINE_DIR": str(self.engines),
                                               "CAD_CACHE_DIR": str(self.root / "cache"), "CAD_INSTALLATION_VERSION": ""})
        patched.start()
        self.addCleanup(patched.stop)
        pinned = mock.patch.object(engine, "PIN", engine.Pin())
        pinned.start()
        self.addCleanup(pinned.stop)

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

    def uvx(self, *, installs: bool) -> Path:
        """A stand-in ``uvx`` first on PATH: it records its arguments, and installs version X as ``cad setup`` would
        (``installs``) or fails as uv does with no network."""
        folder = self.root / "bin"
        folder.mkdir(exist_ok=True)
        record = self.root / "uvx-called.json"
        install = (f"code = pathlib.Path({str(self.state)!r}) / 'versions' / {self.X!r} / 'code'\n"
                   "(code / 'bin').mkdir(parents=True)\n"
                   "[(code / 'bin' / name).write_text('') for name in ('python', 'cad')]\n"
                   "(code / 'cad-version.json').write_text(json.dumps({'schema': 'cad version/1', 'version': "
                   f"{self.X!r}, 'python': str(code / 'bin' / 'python'), 'cad': str(code / 'bin' / 'cad'), "
                   "'prefix': str(code)}))\n") if installs else \
            "sys.stderr.write('error: Failed to fetch: dns error\\n'); sys.exit(2)\n"
        script = folder / "uvx"
        script.write_text(f"#!{sys.executable}\nimport json, pathlib, sys\n"
                          f"pathlib.Path({str(record)!r}).write_text(json.dumps(sys.argv[1:]))\n" + install,
                          encoding="utf-8")
        script.chmod(0o755)
        patched = mock.patch.dict(os.environ, {"PATH": f"{folder}{os.pathsep}{os.environ.get('PATH', '')}"})
        patched.start()
        self.addCleanup(patched.stop)
        return record

    def pinned(self, channel: str | None = None) -> engine.Pin:
        with mock.patch.object(engine, "own_version", return_value=self.X):
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
                               (["--startup-timeout=12.5"], (None, 12.5)), (["--startup-timeout", "86400"], (None, 86400.0))):
            with self.subTest(args=args):
                self.assertEqual(shim.arguments(args), expected)
        for args in (["--channel", "Not a channel"], ["--channel"], ["--other"], ["--channel=@"], ["--startup-timeout"],
                     ["--startup-timeout", "0"], ["--startup-timeout=-5"], ["--startup-timeout", "soon"],
                     ["--startup-timeout=nan"], ["--startup-timeout", "inf"],
                     # Past a day: a wait that long overflows `threading.Event.wait` on Windows (near 4.29e6 s).
                     ["--startup-timeout", "86401"], ["--startup-timeout", "1e400"], ["--startup-timeout", "5e6"]):
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

    def test_installed_nothing_runs(self) -> None:
        self.installed(self.X)
        pin = self.pinned()
        with mock.patch.object(subprocess, "run", side_effect=AssertionError("nothing runs")):
            engine.prepare(pin)
        self.assertEqual((pin.ready.is_set(), pin.failed, engine.unavailable()), (True, None, None))

    @unittest.skipIf(os.name == "nt", "the stand-in uvx is a script run by its #! line")
    def test_missing_it_is_installed_by_its_own_release_s_line_and_its_server_started(self) -> None:
        called = self.uvx(installs=True)
        pin = self.pinned("codex")
        engine.prepare(pin)
        self.assertEqual(json.loads(called.read_text(encoding="utf-8")),
                         ["--no-config", "--managed-python", "--python", "3.14", "--from", f"cad-server=={self.X}",
                          "cad", "setup"])
        self.assertEqual((pin.failed, engine.unavailable()), (None, None))
        argv, options = started()
        self.assertEqual(argv[0], engine.version_record(self.X)["python"])
        self.assertEqual(options["env"]["CAD_INSTALLATION_VERSION"], self.X)
        self.assertEqual(engine.engine_dir(), self.engines.resolve() / self.X, "its own version's door")

    @unittest.skipIf(os.name == "nt", "the stand-in uvx is a script run by its #! line")
    def test_missing_and_not_installable_every_request_says_so_and_nothing_waits(self) -> None:
        # A sandbox with no network: the install fails, and every request is answered here with one line, the
        # command to run with it; nothing reaches or starts a server.
        from cad_mcp.protocol import RequestContext, RpcError

        self.uvx(installs=False)
        pin = self.pinned()
        engine.prepare(pin)
        line = pin.failed
        self.assertEqual(line, f"cad {self.X} is not installed, and it could not be installed here (error: "
                               f"Failed to fetch: dns error): run uvx --no-config --managed-python --python 3.14 --from "
                               f"cad-server=={self.X} cad setup outside any sandbox")
        with mock.patch.object(engine, "_connect", side_effect=AssertionError("never connects")), \
                mock.patch.object(subprocess, "Popen", side_effect=AssertionError("never starts a server")):
            for call in (engine.connect, engine.hold):
                with self.assertRaises(ConnectionError) as said:
                    call()
                self.assertEqual(str(said.exception), line)
            proxy = self.proxy()
            for method in ("initialize", "tools/list", "resources/read"):
                with self.subTest(method=method), self.assertRaises(RpcError) as refused:
                    proxy.handle(method, {"uri": "ui://cad/app"}, RequestContext(1, {}))
                self.assertEqual(refused.exception.message, line)
            self.assertEqual(proxy.handle("tools/call", {"name": "cad_show"}, RequestContext(2, {})),
                             {"content": [{"type": "text", "text": line}], "isError": True})
            self.assertEqual(proxy.handle("ping", {}, RequestContext(3, {})), {})

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
        self.assertEqual(line, f"cad {self.X} is being installed on this computer: try again shortly")
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


class DeclaredLogTest(unittest.TestCase):
    def test_what_the_app_declared_and_what_it_was_offered_go_to_the_app_s_log(self) -> None:
        # The line to read where an app shows no views: what it said at initialize, and the server's answer.
        from cad_mcp import shim
        from cad_mcp.protocol import RequestContext

        class Client:
            def call(self, method, path, body=b"", headers=None, **_kwargs):
                message = json.loads(body)
                if message.get("method") == "initialize":
                    return 200, {"Mcp-Session-Id": "s1"}, json.dumps(
                        {"jsonrpc": "2.0", "id": message["id"], "result": {"protocolVersion": "2025-06-18"}}).encode()
                return 200, {}, json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": {"tools": []}}).encode()

        proxy = shim.Proxy(client=Client(), launcher=lambda: {"host": "gemini", "renders": None})
        ui = {"io.modelcontextprotocol/ui": {"mimeTypes": ["text/html;profile=mcp-app"]}}
        with mock.patch.object(engine, "PIN", engine.Pin()), self.assertLogs("cad_mcp", "INFO") as logged:
            proxy.handle("initialize", {"clientInfo": {"name": "some-app", "version": "1.2"},
                                        "capabilities": {"extensions": ui}}, RequestContext(1, {}))
            proxy.handle("tools/list", {}, RequestContext(2, {}))
        self.assertEqual(logged.output, [
            'INFO:cad_mcp:some-app 1.2 declares io.modelcontextprotocol/ui {"mimeTypes": ["text/html;profile=mcp-app"]}; '
            "launched by gemini",
            "INFO:cad_mcp:the server offers this app no tools"])


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

    def test_the_copies_of_the_library_s_rules_say_what_the_library_does(self) -> None:
        from cad.engine import places

        self.assertEqual((engine.CHANNEL, engine.DEFAULT_CHANNEL), (places.CHANNEL.pattern, places.DEFAULT_CHANNEL))
        self.assertEqual(engine.VERSION, places.VERSION.pattern)
        self.assertEqual((engine.VERSION_MARKER, engine.VERSION_SCHEMA), (places.VERSION_MARKER, places.VERSION_SCHEMA))
        self.assertEqual(engine.INSTALLATION_ENV, places.INSTALLATION_ENV)
        root = Path(tempfile.mkdtemp(prefix="shim-rules-"))
        self.addCleanup(shutil.rmtree, root, True)
        with mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(root)}):
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
