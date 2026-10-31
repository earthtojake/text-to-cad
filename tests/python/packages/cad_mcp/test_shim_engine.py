"""The stdio transport reaches the device's server on its own (``cad_mcp.engine``): it starts the current
installation's, whatever release it is itself; on a device with none current it registers one first -- the
server its own environment carries, else its own release's, installed by uvx -- and with none at all it says
how to install one. Nothing is started for real: ``Popen`` and ``run`` are stood in for."""

from __future__ import annotations

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
        python, console = bin_ / "python", bin_ / "cadgen"
        for path in (python, console):
            path.write_text("", encoding="utf-8")
        record = {"version": version, "python": str(python), "cadgen": str(console), "prefix": str(self.elsewhere)}
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
    a bare ``ok`` as protocol 0, and a protocol it does not speak refused."""

    def test_its_hello_and_greeting_are_the_library_s(self) -> None:
        from cad.engine import door

        ident = "0123456789abcdef" * 2
        self.assertEqual((engine.DOOR_PROTOCOL, engine.hello(ident)), (door.DOOR_PROTOCOL, door.hello(ident)))
        for line in (b"ok\n", b"ok 1\n", b"ok 1", b"ok 2 later\n", b"ok \n", b"ok one\n", b"no\n", b""):
            self.assertEqual(engine.greeted(line), door.greeted(line), line)

    @unittest.skipIf(os.name == "nt", "the door's pipes are POSIX's")
    def test_it_dials_the_door_in_its_protocol_and_takes_a_bare_greeting_as_protocol_0(self) -> None:
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

        for on_hello, protocol in ((library, 1), (greets(b"ok\n"), 0), (greets(b"ok 2\n"), None)):
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

if __name__ == "__main__":
    unittest.main()
