"""The engine server: its folder holds its door and lock, and one others could take is refused; it is
started by a client only where one can be, in an installation's environment, standing a worker by, and
never stops on a timer, only when told or its door is gone, removing its own files; and what it serves
through the daemon -- a document's page, its exports and snapshots -- with its meshing processes started
only for a page."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support import daemon_fixtures, engine_daemon
from tests.python.support.daemon_fixtures import MODEL, SRC, get, get_json
from tests.python.support.http_listener import listener

PLUG = """
import build123d as bd
from cad.engine import stl


@stl("plug.stl")
def plug():
    return bd.Box(2, 2, 2) - bd.Cylinder(0.5, 3)

if __name__ == "__main__":
    plug()
"""


PAIR = """
import build123d as bd
from cad.engine import xbf

SIZE = {size}


@xbf("XBF/pair.xbf")
def pair():
    block = bd.Box(SIZE, 4, 2)
    block.label = "block"
    peg = bd.Pos(20, 0, 0) * bd.Cylinder(2, 5)
    peg.label = "peg"
    return bd.Compound(children=[block, peg], label="pair")

if __name__ == "__main__":
    pair()
"""


class ConnectTest(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "a door is a POSIX daemon's")
    def test_a_door_nobody_reads_is_no_engine_and_leaves_no_pipe_or_file_open(self) -> None:
        import gc
        import warnings
        from unittest import mock

        from cad.engine import client, places

        engine = tempfile.mkdtemp(prefix="eng-")
        self.addCleanup(shutil.rmtree, engine, True)
        with mock.patch.dict(os.environ, {"CAD_ENGINE_DIR": engine}):
            door = places.door_path()
            os.mkfifo(door, 0o600)  # a dead daemon's: the file stays, and nothing reads it
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", ResourceWarning)
                self.assertIsNone(client._connect())
                gc.collect()
            self.assertEqual(list((Path(engine) / "clients").iterdir()), [], "its pair went with it")
        self.assertEqual([w for w in caught if issubclass(w.category, ResourceWarning)], [])


class SandboxTest(unittest.TestCase):
    """In a shell whose sandbox refuses the loopback port the engine's HTTP server needs, no engine
    is started: the client says so at once, and so does one whose daemon could not listen."""

    def setUp(self) -> None:
        from unittest import mock

        self.engine = tempfile.mkdtemp(prefix="eng-")
        self.addCleanup(shutil.rmtree, self.engine, True)
        cleared = {key: value for key, value in os.environ.items() if not key.startswith("CODEX_SANDBOX")}
        patched = mock.patch.dict(os.environ, {**cleared, "CAD_ENGINE_DIR": self.engine}, clear=True)
        patched.start()
        self.addCleanup(patched.stop)

    def test_no_engine_in_a_sandbox_without_network_is_said_in_one_line_and_starts_none(self) -> None:
        from unittest import mock

        from cad.engine import client

        self.assertIn(("CODEX_SANDBOX_NETWORK_DISABLED", "1"), client.SANDBOXES, "cadgen's host adapter names it")
        with mock.patch.dict(os.environ, {"CODEX_SANDBOX": "seatbelt", "CODEX_SANDBOX_NETWORK_DISABLED": "1"}), \
                mock.patch.object(client, "_start", side_effect=AssertionError("a daemon was started")):
            with self.assertRaises(ConnectionError) as said:
                client.request({"op": "status"})
        self.assertEqual(str(said.exception), client.SANDBOXED)
        self.assertNotIn("\n", client.SANDBOXED)

    def test_a_daemon_that_cannot_listen_leaves_its_reason_and_the_client_says_it_at_once(self) -> None:
        import errno
        from unittest import mock

        from cad.engine import client, places
        from cad_server.engine import daemon

        bytecode = sys.dont_write_bytecode
        self.addCleanup(setattr, sys, "dont_write_bytecode", bytecode)
        with mock.patch.object(daemon, "_can_listen", side_effect=PermissionError(errno.EPERM, "Operation not permitted")), \
                mock.patch.object(daemon, "_bind", side_effect=PermissionError(errno.EPERM, "Operation not permitted")), \
                mock.patch("sys.stderr"):
            self.assertEqual(daemon.main(), 1)
        note = json.loads(places.failure_path().read_text(encoding="utf-8"))
        self.assertTrue(note["denied"])
        held = places.lock()
        self.assertIsNotNone(held, "its lock was let go")
        held.close()

        class Exited:  # the daemon as the client sees it: gone, failing, its note left
            returncode = 1

            def __init__(self, written: dict) -> None:
                places.failure_path().write_text(json.dumps(written), encoding="utf-8")

            def poll(self) -> int:
                return 1

        with mock.patch.object(client, "_start", lambda: Exited(note)):
            with self.assertRaisesRegex(ConnectionError, "^" + re.escape(client.SANDBOXED)
                                        + r" \(the engine server cannot listen on a local port: Operation not permitted\)$"):
                client.connect(timeout=30)
        with mock.patch.object(client, "_start", lambda: Exited({"reason": "it broke", "denied": False})):
            with self.assertRaisesRegex(ConnectionError, r"^the engine server did not start: it broke$"):
                client.connect(timeout=30)


class EngineFolderTest(unittest.TestCase):
    """The engine's folder holds its door, lock and port file. One another user owns, or that
    others can write to, would let them take the door's place: client and daemon refuse it."""

    def setUp(self) -> None:
        self.engine = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None))
        self.addCleanup(shutil.rmtree, self.engine, True)

    @unittest.skipIf(os.name == "nt", "a folder's owner and mode are POSIX's")
    def test_a_folder_others_can_write_or_another_user_owns_is_refused_by_client_and_daemon(self) -> None:
        from unittest import mock

        from cad.engine import client, places

        with mock.patch.dict(os.environ, {"CAD_ENGINE_DIR": str(self.engine)}):
            self.assertIsNone(places.folder_refusal(places.engine_dir()))
            os.chmod(self.engine, 0o777)
            refusal = places.folder_refusal(places.engine_dir())
            self.assertIn("can be written by others", refusal)
            with mock.patch.object(client, "_start", side_effect=AssertionError("a daemon was started")):
                with self.assertRaisesRegex(ConnectionError, "can be written by others"):
                    client.connect()
            with self.assertRaisesRegex(PermissionError, "can be written by others"):
                places.lock()
            self.assertEqual(sorted(self.engine.iterdir()), [], "nothing was made in the refused folder")
            os.chmod(self.engine, 0o700)
            real, folder = os.lstat, os.fspath(places.engine_dir())

            def foreign(path, *args, **kwargs):
                found = real(path, *args, **kwargs)
                if os.fspath(path) == folder:
                    return os.stat_result((found.st_mode, found.st_ino, found.st_dev, found.st_nlink,
                                           os.getuid() + 1, found.st_gid, found.st_size, 0, 0, 0))
                return found

            with mock.patch.object(os, "lstat", side_effect=foreign):
                self.assertIn("belongs to another user", places.folder_refusal(places.engine_dir()))
                with self.assertRaisesRegex(PermissionError, "belongs to another user"):
                    places.lock()

    @unittest.skipIf(os.name == "nt" or os.geteuid() == 0, "a folder's mode binds a POSIX user who is not root")
    def test_a_folder_the_system_denies_is_one_line_from_status_and_stop(self) -> None:
        import io
        from unittest import mock

        from cad_server.engine import cli
        from cad.engine import places

        with mock.patch.dict(os.environ, {"CAD_ENGINE_DIR": str(self.engine)}):
            os.mkfifo(places.door_path(), 0o600)  # a dead daemon's door: status sweeps it, taking the lock
            os.chmod(self.engine, 0o500)
            self.addCleanup(os.chmod, self.engine, 0o700)
            for verb in ("status", "stop"):
                with mock.patch("sys.stderr", new_callable=io.StringIO) as said, mock.patch("sys.stdout"):
                    self.assertEqual(cli.run(verb, []), 1)
                self.assertRegex(said.getvalue(), rf"^cad {verb}: the system denies cad-server's engine "
                                 r"\(taking the lock in the engine's folder .+: Permission denied\); .+ "
                                 r"run this command outside it, or with the sandbox's permission\n$")


@unittest.skipIf(os.name == "nt", "the per-user folders are POSIX's")
class DefaultEngineFolderTest(unittest.TestCase):
    """With no ``CAD_ENGINE_DIR``, the engine's folder is one no other user can make first."""

    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp")).resolve()
        self.addCleanup(shutil.rmtree, self.base, True)
        self.system: str | None = None  # what macOS names when TMPDIR is unset: nothing, here

    def folder(self, **env: str) -> Path:
        from unittest import mock

        from cad.engine import places

        cleared = {key: value for key, value in os.environ.items()
                   if key not in ("CAD_ENGINE_DIR", "XDG_RUNTIME_DIR", "TMPDIR")}
        with mock.patch.dict(os.environ, {**cleared, **env}, clear=True), \
                mock.patch.object(places, "_darwin_temp", return_value=self.system):
            return places.engine_dir()

    def private(self, name: str, mode: int = 0o700) -> Path:
        folder = self.base / name
        folder.mkdir()
        os.chmod(folder, mode)
        return folder

    def test_the_runtime_folder_then_a_private_temporary_folder_then_tmp_by_uid(self) -> None:
        runtime, own = self.private("run"), self.private("T")
        self.assertEqual(self.folder(XDG_RUNTIME_DIR=str(runtime), TMPDIR=str(own)), runtime / "cad-engine")
        self.assertEqual(self.folder(TMPDIR=f"{own}/"), own / "cad-engine")
        fallback = Path(os.path.realpath(f"/tmp/cad-{os.getuid()}"))
        self.assertEqual(self.folder(), fallback)
        shared = self.private("shared", 0o1777)
        self.assertEqual(self.folder(TMPDIR=str(shared), XDG_RUNTIME_DIR=str(self.base / "missing")), fallback)
        self.assertEqual(self.folder(TMPDIR="relative"), fallback)

    @unittest.skipUnless(sys.platform == "darwin", "macOS names its per-user temporary folder")
    def test_macos_without_tmpdir_finds_the_folder_a_login_session_names(self) -> None:
        from cad.engine import places

        system = places._darwin_temp()
        self.assertTrue(system and system.startswith("/var/folders/"), system)
        self.system = system
        self.assertEqual(self.folder(), Path(os.path.realpath(os.path.join(system, "cad-engine"))))

    @unittest.skipUnless(sys.platform == "darwin", "macOS names its per-user temporary folder")
    def test_macos_keeps_the_system_folder_when_a_sandbox_sets_its_own_tmpdir(self) -> None:
        from cad.engine import places

        self.system = places._darwin_temp()
        self.assertEqual(self.folder(TMPDIR=str(self.private("sandbox"))),
                         Path(os.path.realpath(os.path.join(self.system, "cad-engine"))))

    def test_a_temporary_folder_another_user_owns_is_passed_over(self) -> None:
        from unittest import mock

        own = self.private("T")
        real = os.stat

        def foreign(path, *args, **kwargs):
            found = real(path, *args, **kwargs)
            if os.fspath(path) == str(own):
                return os.stat_result((found.st_mode, found.st_ino, found.st_dev, found.st_nlink,
                                       os.getuid() + 1, found.st_gid, found.st_size, 0, 0, 0))
            return found

        with mock.patch.object(os, "stat", side_effect=foreign):
            self.assertEqual(self.folder(TMPDIR=str(own)), Path(os.path.realpath(f"/tmp/cad-{os.getuid()}")))

class WindowsTokenFirstTest(unittest.TestCase):
    """On Windows the daemon listens on loopback TCP, which any local user can reach: a connection
    shows its token first, in the door's hello, the token where a pair's id goes, and one that does
    not -- 0.8's client, whose request line came first, among them -- is refused before the rest of
    its line is read or parsed."""

    def serve(self, payload: bytes, said: list | None = None):
        import socket
        import threading
        import types
        from unittest import mock

        from cad_server.engine import daemon

        handled = []
        engine = types.SimpleNamespace(token="ab" * 16, refusal=None, unsaid="",
                                       handle=lambda request, send: handled.append(request) or send({"ok": True}))
        server_side, client_side = socket.socketpair()
        self.addCleanup(client_side.close)
        with mock.patch.object(daemon, "WINDOWS", True):
            done = threading.Thread(target=daemon._serve_connection, args=(engine, server_side))
            done.start()
            try:
                client_side.sendall(payload)
            except OSError:
                pass  # refused after the first bytes, the rest never read (macOS may say ENOTCONN)
            done.join(timeout=30)
        self.assertFalse(done.is_alive(), "the connection was answered or refused, not held")
        if said is not None:
            client_side.settimeout(5)
            stream = client_side.makefile("rb")
            said.extend(iter(stream.readline, b""))
        return handled, engine.token

    def test_a_hello_with_the_token_is_greeted_in_its_protocol_and_served_and_one_without_is_refused(self) -> None:
        from cad.engine import door

        token = "ab" * 16
        request = b'{"token": "' + token.encode() + b'", "op": "status"}\n'
        for hello, greeting in ((door.hello(token), b"ok 1\n"), (token.encode() + b" 9 later\n", b"ok 1\n")):
            said: list[bytes] = []
            handled, _token = self.serve(hello + request, said)
            self.assertEqual(handled, [{"token": token, "op": "status"}], hello)
            self.assertEqual(said, [greeting, b'{"ok":true}\n'], hello)
        for hello in (door.hello("0" * 32), token.encode() + b"\n", token.encode() + b" 0\n", b"ab" * 300 + b"\n",
                      b"not a hello\n"):
            said = []
            handled, _token = self.serve(hello + request, said)
            self.assertEqual((handled, said), ([], []), hello)

    def test_a_request_with_no_hello_first_is_refused_before_its_line_is_read(self) -> None:
        for token in ("0" * 32, "ab" * 16):  # 0.8's client's line, the token first: refused, right or wrong
            handled, _token = self.serve(b'{"token": "' + token.encode() + b'", "op": "status", "pad": "' + b"x" * 200_000)
            self.assertEqual(handled, [])

    def test_a_port_file_being_renamed_into_place_is_read_once_it_is_there(self) -> None:
        # Windows refuses a reader while the starting engine renames its port file into place; a
        # client polling for it then is not refused by the system, and one refused throughout is.
        from unittest import mock

        from cad.engine import client, places

        port_file = Path(tempfile.mkdtemp(prefix="eng-port-")) / "x.port"
        self.addCleanup(shutil.rmtree, port_file.parent, True)
        refused = PermissionError(13, "Permission denied")
        with mock.patch.object(client.time, "sleep"), \
                mock.patch.object(Path, "read_text", side_effect=[refused, refused, "1234 ab\n"]):
            self.assertEqual(client._port_text(port_file), "1234 ab\n")
        with mock.patch.object(client.time, "sleep"), mock.patch.object(Path, "read_text", side_effect=refused), \
                mock.patch.object(places, "WINDOWS", True), self.assertRaisesRegex(ConnectionError, "denies"):
            client._connect(port_file)

    def test_a_stopping_engine_s_port_file_refused_as_it_is_removed_is_gone_not_denied(self) -> None:
        # Windows refuses every open of a file pending deletion until its last handle closes: the
        # port file of an engine told to stop, refused past the ladder, is going (CI run 42841031724,
        # ``api.stop``'s wait said the system denied the engine). A living engine's is still denied.
        from unittest import mock

        from cad.engine import client, places

        folder = Path(tempfile.mkdtemp(prefix="eng-port-"))
        self.addCleanup(shutil.rmtree, folder, True)
        port_file = folder / "x.port"
        port_file.write_text("1234 ab\n", encoding="utf-8")
        gone = places.Endpoint(port_file, folder / "x.lock")  # its lock let go and removed
        with mock.patch.object(client.time, "sleep"), mock.patch.object(places, "WINDOWS", True), \
                mock.patch.object(Path, "read_text", side_effect=PermissionError(13, "Permission denied")):
            self.assertTrue(client.wait_gone(endpoint=gone))
            with self.assertRaisesRegex(ConnectionError, "denies"):
                client._answering(port_file)

    def test_the_client_s_request_carries_its_token_and_is_served_after_its_hello(self) -> None:
        import socket
        import threading
        from unittest import mock

        from cad.engine import client, door, places

        token = "ab" * 16
        port_file = Path(tempfile.mkdtemp(prefix="eng-port-")) / "x.port"
        self.addCleanup(shutil.rmtree, port_file.parent, True)
        port_file.write_text(f"1234 {token}\n", encoding="utf-8")
        ours, theirs = socket.socketpair()
        sent = []

        def engine() -> None:
            with theirs:
                stream = theirs.makefile("rwb")
                sent.append(stream.readline())
                stream.write(b'{"ok": true}\n')
                stream.flush()

        answering = threading.Thread(target=engine)
        answering.start()
        with mock.patch.object(places, "WINDOWS", True):
            stream = ours.makefile("rwb")
            connection = client.Connection(stream, stream, stream, ours)
            self.assertEqual(client._exchange(connection, {"op": "status"}, address=port_file), {"ok": True})
        answering.join(timeout=30)
        self.assertTrue(sent[0].startswith(b'{"token": "' + token.encode() + b'", "op": "status"'))
        handled, _token = self.serve(door.hello(token) + sent[0])
        self.assertEqual(handled, [{"token": token, "op": "status"}])

    def test_the_client_says_its_hello_at_any_port_and_the_daemon_carries_its_protocol(self) -> None:
        import socket
        import threading
        import types
        from unittest import mock

        from cad.engine import client, door, places
        from cad_server.engine import daemon

        token = "ab" * 16
        folder = Path(tempfile.mkdtemp(prefix="eng-port-"))
        self.addCleanup(shutil.rmtree, folder, True)
        listener = socket.create_server(("127.0.0.1", 0))  # any free port, never the engine's
        self.addCleanup(listener.close)
        engine = types.SimpleNamespace(token=token, refusal=None, unsaid="",
                                       handle=lambda request, send: send({"ok": True}))
        spoken: list[int] = []
        serving = daemon._serve

        def serve(*args, **kwargs) -> None:
            spoken.append(args[3] if len(args) > 3 else kwargs.get("protocol"))
            serving(*args, **kwargs)

        def accept() -> None:
            connection, _address = listener.accept()
            daemon._serve_connection(engine, connection)

        for name in (places.NAME, "0123456789ab"):  # 0.8's port files were named for their installation
            port_file = folder / f"{name}.port"
            port_file.write_text(f"{listener.getsockname()[1]} {token}\n", encoding="utf-8")
            accepting = threading.Thread(target=accept)
            accepting.start()
            with mock.patch.object(places, "WINDOWS", True), mock.patch.object(daemon, "WINDOWS", True), \
                    mock.patch.object(daemon, "_serve", serve):
                connection = client._connect(port_file)
                self.assertIsNotNone(connection, name)
                self.assertEqual(connection.protocol, door.DOOR_PROTOCOL, name)
                self.assertEqual(client._exchange(connection, {"op": "status"}, address=port_file), {"ok": True})
            accepting.join(timeout=30)
            self.assertEqual(spoken.pop(), door.DOOR_PROTOCOL, f"the daemon carries the hello's protocol: {name}")


class NoTimerTest(unittest.TestCase):
    """The engine never stops on a timer, nor retires a worker on one: memory alone does, and only
    ``stop`` stops it."""

    def test_a_day_idle_unheld_keeps_the_idle_worker_and_only_stop_stops_the_engine(self) -> None:
        import types
        from unittest import mock

        from cad_server.engine import daemon

        engine = daemon.Daemon(cap=1)
        stopped: list[str] = []
        engine.supervisor.launch = lambda service, key, label, environment, cwd, standby: types.SimpleNamespace(
            service=service, key=key, label=label, environment=environment, pid=1, leased=False, retired=False,
            rss=100.0, used=time.monotonic(), alive=lambda: True, stop=lambda: stopped.append("worker"))
        worker = engine.lease("/w/block.py", {})
        engine.release(worker)
        with mock.patch("time.monotonic", return_value=worker.used + 24 * 3600):
            engine.tend()  # no holder, nothing to do, a day on
        self.assertEqual((stopped, engine.supervisor.processes("worker")), ([], [worker]), "its idle worker stays")
        self.assertFalse(engine.stopping.is_set(), "the engine stays")
        sent: list[dict] = []
        engine.handle({"op": "stop"}, sent.append)
        self.assertEqual(sent, [{"ok": True}])
        self.assertTrue(engine.stopping.is_set())

    def test_an_engine_whose_door_is_gone_stops_and_one_whose_door_stands_stays(self) -> None:
        from cad_server.engine import daemon

        folder = Path(tempfile.mkdtemp(prefix="door-"))
        self.addCleanup(shutil.rmtree, folder, True)
        door = folder / "engine.door"
        door.write_bytes(b"")
        engine = daemon.Daemon(cap=1)
        engine.reached_by(door)
        with mock.patch("time.monotonic", return_value=time.monotonic() + 24 * 3600):
            engine.tend()
        self.assertFalse(engine.stopping.is_set(), "its door stands: it stays, however long idle")
        door.unlink()  # its folder cleaned up: no one can reach it
        engine.tend()
        self.assertTrue(engine.stopping.is_set())


class BusyTest(unittest.TestCase):
    """What ``status`` says is in use, and an update's drain waits for: a request that serves, binding
    the HTTP server, is in use until it is answered."""

    def test_a_launch_binding_its_server_is_busy_until_it_is_answered(self) -> None:
        import threading

        from cad_server.engine import daemon

        engine = daemon.Daemon(cap=1)
        self.addCleanup(engine.supervisor.stop)
        binding, release = threading.Event(), threading.Event()

        def bind(*_args, **_kwargs):
            binding.set()
            release.wait(30)
            raise ValueError("cannot listen on 127.0.0.1:0")

        answered: list = []

        def launch() -> None:
            try:
                engine.handle({"op": "viewer"}, answered.append)
            except ValueError as error:  # the connection says it (``_serve``)
                answered.append(str(error))

        with mock.patch.object(daemon, "bind", bind):
            asking = threading.Thread(target=launch)
            asking.start()
            self.assertTrue(binding.wait(30))
            self.assertEqual(engine.status()["busy"], 1, "binding: in use, so never retired under the launch")
            release.set()
            asking.join(30)
        self.assertEqual(answered, ["cannot listen on 127.0.0.1:0"])
        self.assertEqual(engine.status()["busy"], 0)


class StandbyStartTest(unittest.TestCase):
    def test_the_daemon_s_start_stands_one_by_in_its_starter_s_environment(self) -> None:
        from unittest import mock

        from cad_server.engine import daemon
        from cad.engine import places

        engine = daemon.Daemon()
        self.addCleanup(engine.supervisor.stop)
        asked: list[dict] = []
        root = places.engine_root()
        with mock.patch.object(engine.supervisor, "stand", side_effect=lambda *args: asked.append(args)), \
                mock.patch.dict(os.environ, {"PYTHONPATH": os.pathsep.join((root, "/mine")),
                                             "CAD_ENGINE_STANDBY": "1"}):
            engine.stand()
        self.assertTrue(engine.supervisor.standbys["worker"].enabled)
        self.assertEqual([service for service, _environment in asked], ["worker"])
        self.assertEqual(asked[0][1]["PYTHONPATH"], "/mine", "without the engine's folder its starter put first")

    def core(self):
        """An installation whose own environment has no kernel (the plugin's server alone), its cache a
        scratch folder, and a fake making gated by the event returned."""
        import contextlib
        import dataclasses
        import io
        import threading

        from cad_server._internal import base

        scratch = Path(tempfile.mkdtemp(prefix="engine-base-"))
        self.addCleanup(shutil.rmtree, scratch, True)
        core = dataclasses.replace(base._own(), kernel=False)
        go = threading.Event()

        def make(env, recipe, told, *, finish, marker, done):
            told(recipe.making)
            go.wait(30)
            base.interpreter(env).parent.mkdir(parents=True)
            base.interpreter(env).write_text("", encoding="utf-8")
            written = {"schema": base.SCHEMA, "key": env.name, "path": []}
            (env / marker).write_text(json.dumps(written), encoding="utf-8")
            return written

        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(mock.patch.dict(os.environ, {"CAD_CACHE_DIR": str(scratch), "CAD_ENGINE_STANDBY": "1"}))
        stack.enter_context(mock.patch.object(base, "MAKING", base.Making()))
        made = stack.enter_context(mock.patch.object(base, "make", side_effect=make))
        stack.enter_context(mock.patch.object(base.Installation, "here", return_value=core))
        stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
        return core, go, made

    def test_an_engine_with_no_base_makes_none_and_stands_no_standby_until_its_first_need_made_it(self) -> None:
        # The plugin's server alone, as a host's CAD app installs it: its engine's start makes nothing, and no
        # standby stands; the first kernel process's start makes the base, and the standby stands once it is made.
        import threading

        from cad_server._internal import base
        from cad_server.engine import daemon

        core, go, made = self.core()
        engine = daemon.Daemon()
        self.addCleanup(engine.supervisor.stop)
        stood: list[bool] = []  # whether the base was there each time a standby was asked to stand
        with mock.patch.object(engine.supervisor, "stand",
                               side_effect=lambda _service, _env: stood.append(base.complete(base.where(core)) is not None)):
            engine.stand()
            self.assertEqual((engine.status()["base"], stood), (None, []), "nothing made, and no standby, at the start")
            made.assert_not_called()
            found: list = []
            asking = threading.Thread(target=lambda: found.append(daemon._places.kernel(make=True)), daemon=True)
            asking.start()
            deadline = time.monotonic() + 30
            while (engine.status()["base"] or {}).get("state") != "making" and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual((engine.status()["base"]["state"], found, stood), ("making", [], []),
                             "the kernel process's start waits on the making; no standby meanwhile")
            go.set()
            asking.join(30)
            deadline = time.monotonic() + 30
            while not stood and time.monotonic() < deadline:
                time.sleep(0.01)
        self.assertEqual(found[0]["python"], str(base.interpreter(base.where(core))))
        made.assert_called_once()
        self.assertEqual(stood, [True], "the standby, once the base is made")

    def test_an_engine_whose_base_is_made_stands_its_standby_at_its_start(self) -> None:
        from cad_server._internal import base
        from cad_server.engine import daemon

        core, go, _made = self.core()
        go.set()
        base.ensure(core, told=lambda _line: None)  # made already, by an earlier engine
        engine = daemon.Daemon()
        self.addCleanup(engine.supervisor.stop)
        with mock.patch.object(engine.supervisor, "stand") as stand:
            engine.stand()
        self.assertEqual([call.args[0] for call in stand.call_args_list], ["worker"])

    def test_with_the_switch_off_none_stands_by_and_none_replaces_one(self) -> None:
        from unittest import mock

        from cad_server.engine import daemon

        engine = daemon.Daemon()
        self.addCleanup(engine.supervisor.stop)
        with mock.patch.object(engine.supervisor, "stand") as stand, \
                mock.patch.dict(os.environ, {"CAD_ENGINE_STANDBY": "0"}):
            engine.stand()
        stand.assert_not_called()
        self.assertFalse(engine.supervisor.standbys["worker"].enabled,
                         "no standby to start after an adoption or a fresh worker either")


class DaemonEnvironmentTest(unittest.TestCase):
    """The daemon serves every later client, so the client that starts it does not hand it a
    per-process telemetry switch: those are the person's saved choice's to decide. And it is an
    installation's: a client starts no server of its own environment."""

    def test_with_no_installation_a_client_starts_nothing_and_says_so_in_one_line(self) -> None:
        from unittest import mock

        from cad.engine import client, places, said
        from cad_server._internal import installations

        state = tempfile.mkdtemp(prefix="no-installation-")
        self.addCleanup(shutil.rmtree, state, True)

        def refused(words) -> str:
            with mock.patch.dict(os.environ, {"CAD_STATE_DIR": state}), mock.patch.object(places, "HOME", None), \
                    mock.patch.object(said, "UNREGISTERED", words), \
                    mock.patch.object(client.subprocess, "Popen", side_effect=AssertionError("a daemon was started")):
                with self.assertRaises(ConnectionError) as caught:
                    client._start()
            return str(caught.exception)

        # A model's process, the library alone: the server is what is missing.
        self.assertEqual(refused(None), "cad-server is not installed on this computer: install cad-server and run "
                                        "`cad doctor` once, then run this again")
        # A process of cad-server's own: never that cad-server is not installed, but what is true of it.
        self.assertEqual(said.UNREGISTERED.__module__, "cad_server", "importing the server says its own words")
        with mock.patch.object(installations, "here", return_value=None), \
                mock.patch.object(installations, "own_version", return_value="0.10.0"):
            self.assertEqual(refused(said.UNREGISTERED), "this cad-server is not registered on this computer: run "
                                                         "`cad doctor` once, which registers it, then run this again")
        from cad.engine.previous import version

        with mock.patch.object(installations, "here", return_value=None), \
                mock.patch.object(installations, "own_version", return_value=None):
            self.assertEqual(refused(said.UNREGISTERED), "this cad-server is a source tree, which registers only as a "
                                                         "version it is named: run `cad doctor` once with "
                                                         f"CAD_INSTALLATION_VERSION={version()}-dev.0 set, then run this "
                                                         "again")
        with mock.patch.object(installations, "here", return_value={"version": "0.10.0"}):
            self.assertEqual(refused(said.UNREGISTERED), "no cad-server is current on this computer: run `cad doctor` "
                                                         "once, which makes this one current, then run this again")
        # A base an installation made (``cad run``'s) starts its installation's engine, current or not.
        base = {"executable": sys.executable, "prefix": sys.prefix, "root": str(Path(state, "server"))}
        with mock.patch.dict(os.environ, {"CAD_STATE_DIR": state}), mock.patch.object(places, "HOME", base), \
                mock.patch.object(client.subprocess, "Popen") as started:
            client._start()
        self.assertEqual(started.call_args.args[0][0], sys.executable)

    def test_an_interpreter_with_no_console_script_registers_with_one_beside_its_record(self) -> None:
        # A test's interpreter that reads the packages from PYTHONPATH: never left unregistered.
        from cad.engine import places

        state, bare = (Path(tempfile.mkdtemp(prefix=prefix)) for prefix in ("state-", "bare-env-"))
        for folder in (state, bare):
            self.addCleanup(shutil.rmtree, folder, True)
        self.assertTrue(engine_daemon.register(state, sys.executable, str(bare)))
        current = places.current(state)
        self.assertEqual((current["python"], current["prefix"]), (sys.executable, str(bare)))
        self.assertEqual(Path(current["cad"]).parent, state / "installations", "its console script, beside it")
        self.assertIn("-m cad_server.cli", Path(current["cad"]).read_text(encoding="utf-8"))

    def test_the_started_daemon_does_not_inherit_the_telemetry_switches(self) -> None:
        from unittest import mock

        from cad_server import analytics
        from cad.engine import client

        self.assertEqual(set(client._PER_PROCESS_TELEMETRY), set(analytics.ENVIRONMENT),
                         "the engine's copy of the per-process switches must match cad_server.analytics")
        captured = {}

        class FakePopen:
            pid = 0

            def __init__(self, _argv, **kwargs):
                captured.update(kwargs.get("env") or {})

        with mock.patch.dict(os.environ, {"DO_NOT_TRACK": "1", "CAD_TELEMETRY": "1", "PATH": os.environ.get("PATH", "")}), \
                mock.patch.object(client.subprocess, "Popen", FakePopen):
            client._start()
        self.assertNotIn("DO_NOT_TRACK", captured)
        self.assertNotIn("CAD_TELEMETRY", captured)

    def test_the_daemon_and_its_workers_cache_bytecode_in_the_engine_s_folder_alone(self) -> None:
        from cad.engine import client, places
        from cad_server.engine.services import WORKER
        from cad_server.engine.supervisor import Process

        cache = Path(tempfile.mkdtemp(prefix="engine-bytecode-")).resolve()
        self.addCleanup(shutil.rmtree, cache, True)

        def started(given: dict[str, str]) -> dict[str, dict[str, str]]:
            """The environment a daemon is started with from a caller's ``given``, and the one that
            daemon starts a worker with for a run in ``given``."""
            found: dict[str, dict] = {}

            class Captured(Exception):
                pass

            def popen(argv, **kwargs):
                found["worker" if argv[-1].endswith("worker") else "daemon"] = kwargs["env"]
                raise Captured

            with mock.patch.object(subprocess, "Popen", popen):
                with mock.patch.dict(os.environ, given):
                    if "PYTHONPYCACHEPREFIX" not in given:
                        os.environ.pop("PYTHONPYCACHEPREFIX", None)
                    with self.assertRaises(Captured):
                        client._start()
                with mock.patch.dict(os.environ, found["daemon"], clear=True), self.assertRaises(Captured):
                    script = str(cache / "model.py")
                    Process.start(WORKER, script, script, dict(given))  # in the daemon, for a run in ``given``
            return found

        ours = str(cache / places.PYCACHE / places.bytecode_tag())
        found = started({"CAD_CACHE_DIR": str(cache), "PYTHONDONTWRITEBYTECODE": "1"})
        for process in ("daemon", "worker"):
            self.assertEqual(found[process].get("PYTHONPYCACHEPREFIX"), ours, process)
            self.assertNotIn("PYTHONDONTWRITEBYTECODE", found[process], f"a caller's switch is not the {process}'s")
        if os.name != "nt":  # a folder's mode bits are POSIX's; Windows' per-user temporary folder is the user's
            self.assertEqual(stat.S_IMODE(os.stat(ours).st_mode) & 0o077, 0, "this user's alone")
        given = started({"CAD_CACHE_DIR": str(cache), "PYTHONPYCACHEPREFIX": str(cache / "theirs")})
        self.assertEqual(given["daemon"]["PYTHONPYCACHEPREFIX"], str(cache / "theirs"), "a prefix given is honoured")
        if os.name != "nt":
            os.chmod(ours, 0o777)
            self.assertEqual(started({"CAD_CACHE_DIR": str(cache)})["daemon"].get("PYTHONDONTWRITEBYTECODE"), "1",
                             "a folder others can write to is none of the engine's")


class SweepTest(unittest.TestCase):
    """``cad stop`` stops the engine of its engine folder, and ``stop`` and ``status`` take away the files
    of a dead one."""

    def setUp(self) -> None:
        self.state = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        self.addCleanup(shutil.rmtree, self.state, True)
        self.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CAD_ENGINE_DIR": str(self.state)},
                                         self.addCleanup)

    def cli(self, *args: str) -> subprocess.CompletedProcess:
        return engine_daemon.run([sys.executable, "-m", "cad_server.engine", *args], env=self.env)

    @unittest.skipIf(os.name == "nt", "a door is a POSIX daemon's")
    def test_a_dead_server_s_door_and_lock_are_removed_and_said(self) -> None:
        from unittest import mock

        from cad.engine import places

        with mock.patch.dict(os.environ, {"CAD_ENGINE_DIR": str(self.state)}):
            path, lock = places.door_path(), places.lock_path()
        os.mkfifo(path, 0o600)  # the file stays, and nothing reads it
        lock.write_text("", encoding="utf-8")
        done = self.cli("status")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "no engine server is running")
        self.assertIn(f"removed stale engine file {path}", done.stderr)
        self.assertIn(f"removed stale engine file {lock}", done.stderr)
        self.assertEqual(list(self.state.iterdir()), [])
        os.mkfifo(path, 0o600)
        done = self.cli("stop")
        self.assertEqual((done.returncode, done.stdout), (0, "no engine server is running\n"), done.stderr)
        self.assertEqual(done.stderr, f"removed stale engine file {path}\n", "a swept file a line on stderr")

    def test_status_starts_no_engine_a_verb_that_starts_one_says_so_and_stop_leaves_none(self) -> None:
        own = Path(tempfile.mkdtemp(prefix="own-"))
        self.addCleanup(shutil.rmtree, own, True)
        self.env.update(CAD_STATE_DIR=str(own / "state"), CAD_CACHE_DIR=str(own / "cache"))
        engine_daemon.register(self.env["CAD_STATE_DIR"])  # the installation whose engine a verb starts
        for _ in range(2):
            done = self.cli("status")
            self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "no engine server is running\n", ""))
        self.assertEqual(list(self.state.iterdir()), [], "status started nothing")
        unknown = "00000000-0000-5000-8000-000000000000"
        first, again = self.cli("inspect", unknown), self.cli("inspect", unknown)
        self.assertEqual((first.returncode, first.stderr.splitlines()[0]), (2, "engine started"), first.stderr)
        self.assertNotIn("engine started", again.stderr, "said only by the verb that started it")
        self.assertEqual(self.cli("stop").returncode, 0)
        done = self.cli("status")
        self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "no engine server is running\n", ""))


class OwnFilesTest(unittest.TestCase):
    """A stopping engine removes its own files from the engine folder, and nothing in it that is not its
    own."""

    def setUp(self) -> None:
        self.state = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        self.addCleanup(shutil.rmtree, self.state, True)
        own = Path(tempfile.mkdtemp(prefix="own-"))
        self.addCleanup(shutil.rmtree, own, True)
        self.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CAD_ENGINE_DIR": str(self.state),
                                          "CAD_STATE_DIR": str(own / "state"), "CAD_CACHE_DIR": str(own / "cache"),
                                          "CAD_ENGINE_STANDBY": "0"}, self.addCleanup)
        patch = mock.patch.dict(os.environ, {"CAD_ENGINE_DIR": str(self.state)})
        patch.start()
        self.addCleanup(patch.stop)

    def started(self) -> subprocess.Popen:
        from cad.engine import client

        server = subprocess.Popen([sys.executable, "-m", "cad_server.engine.daemon"], env=self.env,
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: server.poll() is None and server.kill())
        deadline = time.monotonic() + 60
        while (found := client._connect()) is None:
            self.assertIsNone(server.poll(), "the engine exited before it listened")
            self.assertLess(time.monotonic(), deadline, "the engine listened")
            time.sleep(0.05)
        found.close()
        return server

    def left(self) -> list[str]:
        return sorted(path.name for path in self.state.iterdir() if path.name != "clients")

    def test_an_engine_removes_its_files_as_it_stops_and_leaves_what_is_not_its_own(self) -> None:
        from cad.engine import client, places

        ours = places.NAME
        places.failure_path().write_text('{"reason": "an earlier start"}', encoding="utf-8")
        (self.state / "notes.txt").write_text("", encoding="utf-8")  # no engine's
        server = self.started()
        self.assertIn(f"{ours}.failed", self.left(), "its starting leaves the note an earlier start left its client")
        self.assertEqual(client.request({"op": "stop"}, start=False), {"ok": True})
        self.assertEqual(server.wait(timeout=60), 0)
        self.assertEqual(self.left(), ["notes.txt"], "its lock, door and failure note went with it")
        if os.name != "nt":  # a terminate stops it as ``stop`` does; Windows' terminate is a kill
            server = self.started()
            server.terminate()
            self.assertEqual(server.wait(timeout=60), 0)
            self.assertEqual(self.left(), ["notes.txt"])

    @unittest.skipIf(os.name == "nt", "an open file is never removed on Windows")
    def test_a_lock_whose_file_is_removed_as_it_is_taken_takes_the_file_its_name_names(self) -> None:
        import builtins

        from cad.engine import places

        path = self.state / "aaaaaaaaaaaa.lock"
        path.write_text("", encoding="utf-8")
        real = builtins.open
        opened: list[str] = []

        def opener(file, *args, **kwargs):
            handle = real(file, *args, **kwargs)
            if not opened:
                opened.append(str(file))
                os.unlink(file)  # its last holder removed it as this one opened it
            return handle

        with mock.patch("builtins.open", opener):
            held = places.lock(path)
        self.addCleanup(held.close)
        self.assertEqual(opened, [str(path)])
        self.assertTrue(places.names(held, path), "the lock is on the file the name names")
        self.assertIsNone(places.lock(path), "and it is held: no second daemon takes it")


class StateDirSpellingTest(unittest.TestCase):
    def test_a_server_started_under_a_dotted_spelling_is_found_and_stopped_under_the_plain_one(self) -> None:
        from unittest import mock

        from cad.engine import client, places

        state = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        self.addCleanup(shutil.rmtree, state, True)
        (state / "sub").mkdir()
        engine = "engine-" * 14  # a long folder: a pipe's path has no socket's length limit
        dotted = f"{state / 'sub'}{os.sep}..{os.sep}{engine}{os.sep}"  # a `..` and a trailing separator
        plain = str(state / engine)
        env = {**os.environ, "PYTHONPATH": str(SRC)}
        dotted_env = engine_daemon.watched({**env, "CAD_ENGINE_DIR": dotted}, self.addCleanup)
        plain_env = engine_daemon.watched({**env, "CAD_ENGINE_DIR": plain}, self.addCleanup)
        self.addCleanup(engine_daemon.run, [sys.executable, "-m", "cad_server.engine", "stop"], env=plain_env)
        probe = "from cad.engine.client import request; print(request({'op': 'status'})['pid'])"
        started = engine_daemon.run([sys.executable, "-c", probe], env=dotted_env)
        self.assertEqual(started.returncode, 0, started.stderr)
        with mock.patch.dict(os.environ, {"CAD_ENGINE_DIR": plain}):
            found = client.request({"op": "status"}, start=False)
            address = places.address()
        self.assertIsNotNone(found, "the plain spelling reaches the server the dotted one started")
        self.assertEqual(str(found["pid"]), started.stdout.split()[-1])
        done = engine_daemon.run([sys.executable, "-m", "cad_server.engine", "stop"], env=plain_env)
        self.assertEqual((done.returncode, done.stdout), (0, f"stopped the engine server at {address}\n"), done.stderr)
        with mock.patch.dict(os.environ, {"CAD_ENGINE_DIR": dotted}):
            self.assertIsNone(client.request({"op": "status"}, start=False), "stopped under either spelling")


class InstallationTest(unittest.TestCase):
    def test_every_name_of_the_installation_s_interpreter_reaches_one_engine(self) -> None:
        from unittest import mock

        from cad.engine import places

        folder = os.path.dirname(sys.executable)
        names = [os.path.join(folder, name) for name in ("python", "python3", f"python3.{sys.version_info[1]}")]
        tags = set()
        for name in names:
            with mock.patch.object(sys, "executable", name):
                tags.add(places.address())
        self.assertEqual(len(tags), 1, "`python3 model.py` and `cad viewer` share one engine")

    def test_a_relative_and_an_absolute_launch_reach_one_engine(self) -> None:
        # `../../.venv/bin/python model.py` from a model folder, and the absolute path.
        probe = "from cad.engine import places; print(places.address())"
        env = {**os.environ, "PYTHONPATH": str(SRC)}
        with tempfile.TemporaryDirectory() as folder:
            folder = os.path.realpath(folder)
            relative = os.path.relpath(sys.executable, folder) if os.path.splitdrive(sys.executable)[0].lower() \
                == os.path.splitdrive(folder)[0].lower() else sys.executable
            # A shell finds a relative command from its own folder; Windows' CreateProcess would look
            # from this process's, so there the test finds it as cmd.exe does (a full path).
            found = {subprocess.run([command, "-c", probe], cwd=folder, env=env, capture_output=True, text=True,
                                    executable=os.path.normpath(os.path.join(folder, command)) if os.name == "nt"
                                    else None,
                                    timeout=60).stdout.strip() for command in (relative, sys.executable)}
        self.assertEqual(len(found), 1, found)
        self.assertNotIn("", found, "the probe said no door")


class PoolExitTest(unittest.TestCase):
    def test_a_pool_process_exits_when_its_engine_dies_without_cleaning_up(self) -> None:
        probe = ("import os; from cad.engine.serve import Mesher; mesher = Mesher('processes', workers=1); "
                 "print(mesher.processes().submit(os.getpid).result(), flush=True); os._exit(0)")
        done = engine_daemon.run([sys.executable, "-c", probe], env={**os.environ, "PYTHONPATH": str(SRC)})
        self.assertEqual(done.returncode, 0, done.stderr)
        orphan = int(done.stdout.split()[-1])
        deadline = time.monotonic() + 30
        while engine_daemon._alive(orphan):
            self.assertLess(time.monotonic(), deadline, "the pool process outlived the process that started it")
            time.sleep(0.05)


class ListenTest(unittest.TestCase):
    def test_a_taken_port_is_refused_by_name_and_leaves_no_pool_or_recorder_behind(self) -> None:
        import socket
        from unittest import mock

        from cad_server._internal import engine_host
        from cad_server.engine import daemon

        taken = socket.socket()
        self.addCleanup(taken.close)
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]
        for engine, request in ((daemon.Daemon(), {"port": port}), (daemon.Daemon(port=port), {})):
            with mock.patch("cad.engine.serve.Mesher") as mesher, mock.patch.object(daemon, "HTTP_FACTORY", listener), \
                    mock.patch.object(daemon, "_answers", return_value=False), mock.patch.object(daemon, "_note"):
                # The listen tried (no probe answered first): the server it made fails its bind.
                with self.assertRaisesRegex(daemon.PortHeld,
                                            f"^port {port} is held by .+: stop it, or pass another --port$"):
                    engine.serve(request)
            mesher.return_value.stop.assert_called_once_with()
            self.assertIsNone(engine.server)
            if request:  # a request's own port: that request refused, the engine running on for the others
                self.assertIsNone(engine.refusal)
            else:
                self.assertIsNotNone(engine.refusal, "an engine whose own port is held can never serve: it stops")
        with mock.patch("cad_server.viewer.engine_app.EngineApp") as app, self.assertRaises(OSError):
            engine_host.http_factory(mock.Mock(), "127.0.0.1", port)
        app.return_value.close.assert_called_once_with()


class DaemonServerTest(daemon_fixtures.DaemonCase):
    """What the server serves of a build through the daemon, and its own start and stop."""

    def test_a_snapshot_of_a_job_draws_a_memory_model_without_an_intermediate_document(self) -> None:
        from tests.python.packages.cad_server.engine.test_snapshot import gl

        gl()
        address = self._bare()
        self.built("bracket")
        packet = {"input": address, "jobs": [{"outputs": [
            {"path": str(self.folder / "bracket.png"), "width": 200, "height": 150}]}]}
        drawn = self.cli("snapshot", "--job", json.dumps(packet))
        self.assertEqual(drawn.returncode, 0, drawn.stderr)
        from PIL import Image

        with Image.open(self.folder / "bracket.png") as picture:
            self.assertEqual(picture.size, (200, 150))
        self.assertEqual(sorted(path.name for path in self.folder.iterdir()), ["bracket.png", "bracket.py"])

    def test_a_served_declared_xbf_follows_its_file_when_its_model_runs_again(self) -> None:
        """A model's declared xbf opened as a file is a file: a run that rewrites it sends the page
        nothing, and the page's version moves because the file's bytes did -- its version is the
        file's, and its parts are read from it."""
        self.script = self.folder / "pair.py"
        self.script.write_text(textwrap.dedent(PAIR.format(size=10)), encoding="utf-8")
        self.assertEqual(self.run_script("pair.py").returncode, 0)
        served = self.cli("serve", "XBF/pair.xbf")
        self.assertEqual(served.returncode, 0, served.stderr)
        from urllib.parse import urlsplit, parse_qs
        url = urlsplit(served.stdout.strip())
        base, query = f"{url.scheme}://{url.netloc}", parse_qs(url.query)
        ident, token = url.path.strip("/"), query["token"][0]
        api = f"{base}/api/v1/documents/xbf/{ident}"
        before = get_json(f"{api}/structure", token)
        for prototype in before["prototypes"]:  # the page has every part
            self.assertEqual(get(f"{api}/parts/{prototype['key']}", token)[:4], b"XBM2")
        self.script.write_text(textwrap.dedent(PAIR.format(size=12)), encoding="utf-8")
        ran = self.run_script("pair.py")
        self.assertEqual(ran.returncode, 0, ran.stderr)
        answer = get_json(f"{base}/api/v1/documents/{ident}/version?after={before['version']}&wait=60", token)
        stat = (self.folder / "XBF/pair.xbf").stat()
        self.assertEqual(answer["version"], f"{stat.st_mtime_ns}-{stat.st_size}", "the file's own version")
        self.assertNotIn("patch", answer, "nothing of the run reached the page")
        after = get_json(f"{api}/structure", token)
        keys = lambda s: {p["name"]: p["key"] for p in s["prototypes"]}  # noqa: E731
        self.assertNotEqual(keys(after)["block"], keys(before)["block"])
        self.assertEqual(keys(after)["peg"], keys(before)["peg"])
        self.assertEqual(get(f"{api}/parts/{keys(after)['block']}", token)[:4], b"XBM2")

    def test_the_viewer_moves_before_a_derived_file_is_written(self) -> None:
        # An STL writer held until the test lets it go, put in place in the worker by the model's own module.
        gate = self.folder / "gate"
        gate.touch()  # the first build writes at once
        slow = textwrap.dedent("""
            import os, time
            from cad.engine import export

            if not getattr(export, "slow", False):
                class Slow(type(export.KINDS["stl"])):
                    def write(self, view, path):
                        while not os.path.exists(GATE_PATH):
                            time.sleep(0.01)
                        super().write(view, path)

                given = export.KINDS["stl"]
                export.KINDS["stl"] = Slow(given.name, given.suffixes, given.writer, given.atomic)
                export.slow = True
        """).replace("GATE_PATH", repr(str(gate))) + textwrap.dedent(PAIR).replace('@xbf("XBF/pair.xbf")', '@xbf("XBF/pair.xbf")\n@stl("pair.stl")').replace(
            "import xbf", "import stl, xbf")
        self.script = self.folder / "pair.py"
        self.script.write_text(slow.format(size=10), encoding="utf-8")
        self.assertEqual(self.run_script("pair.py").returncode, 0)
        served = self.cli("serve", "XBF/pair.xbf")
        from urllib.parse import urlsplit, parse_qs
        url = urlsplit(served.stdout.strip())
        base, query = f"{url.scheme}://{url.netloc}", parse_qs(url.query)
        ident, token = url.path.strip("/"), query["token"][0]
        before = get_json(f"{base}/api/v1/documents/xbf/{ident}/structure", token)
        stl = self.folder / "pair.stl"
        written = stl.stat().st_mtime_ns
        self.script.write_text(slow.format(size=12), encoding="utf-8")
        gate.unlink()
        building = subprocess.Popen([sys.executable, "pair.py"], cwd=self.folder, env=self.env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(building.wait)
        answer = get_json(f"{base}/api/v1/documents/{ident}/version?after={before['version']}&wait=60", token)
        self.assertNotEqual(answer["version"], before["version"])
        self.assertEqual(stl.stat().st_mtime_ns, written, "the viewer moved before the STL was written")
        gate.touch()
        self.assertEqual(building.wait(timeout=300), 0)
        self.assertNotEqual(stl.stat().st_mtime_ns, written)

    def test_exports_and_a_model_s_document_through_the_daemon(self) -> None:
        self.script = self.folder / "pair.py"
        self.script.write_text(textwrap.dedent(PAIR.format(size=10)), encoding="utf-8")
        self.assertEqual(self.run_script("pair.py").returncode, 0)
        done = self.cli("export", "XBF/pair.xbf", "pair.glb", "pair.step")
        self.assertEqual(done.returncode, 0, done.stderr)
        workers = json.loads(self.cli("status", "--json").stdout)["workers"]
        self.assertEqual(([Path(row["script"]).name for row in self.mine(workers)],
                          [row["script"] for row in workers if row["script"] == "documents"]), (["pair.py"], ["documents"]),
                         "a declared xbf is a file: the documents worker read it, never the model's worker")
        done = self.cli("export", "pair.step", "back.xbf")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.folder / "back.xbf").is_file())
        self.assertEqual(self.cli("export", "pair.glb", "x.step").returncode, 2, "a mesh is no source")
        self.assertEqual(self.cli("export", "pair.py::pair", "x.step").returncode, 2, "a script is no source")
        (self.folder / "plug.py").write_text(textwrap.dedent(PLUG), encoding="utf-8")
        built = self.run_script("plug.py")
        self.assertEqual(built.returncode, 0, built.stderr)
        self.assertTrue((self.folder / "plug.stl").is_file())
        # From Python: the model's document and shape, asked of the worker that holds them.
        probe = textwrap.dedent("""
            import json, plug
            report = plug.plug.build().models[0]
            handle = plug.plug()
            print(json.dumps({"bodies": report["bodies"], "name": handle.shape.label,
                              "volume": round(handle.shape.volume, 3)}))
        """)
        done = engine_daemon.run([sys.executable, "-c", probe], cwd=self.folder, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        found = json.loads(done.stdout.strip().splitlines()[-1])
        self.assertEqual(found["bodies"], {"plug.py::plug": "loaded"}, "the script's warm worker, by its key")
        self.assertEqual(found["name"], "plug")
        self.assertAlmostEqual(found["volume"], 8 - 3.14159265 * 0.25 * 2, places=2)

    def test_a_build_with_no_page_starts_no_meshing_process(self) -> None:
        """``python model.py`` serves its document, so the daemon starts its server; the meshing
        pool waits for a page, a view or a mesh: the daemon's only child is the worker (with no
        standby, ``CAD_ENGINE_STANDBY=0``)."""
        self.own()
        env = {name: value for name, value in self.env.items() if name != "CAD_ENGINE_MESH"}
        env["CAD_ENGINE_STANDBY"] = "0"
        self.script.write_text(textwrap.dedent(MODEL.format(size=3)), encoding="utf-8")
        done = self.run_script("block.py", env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("  view: http://127.0.0.1:", done.stdout, "the build registered its page")
        status = json.loads(self.cli("status", "--json", env=env).stdout)
        children = []
        for path in Path(env[engine_daemon.JOURNAL]).glob("*-*.txt"):
            role, _, pid = path.stem.partition("-")
            first = path.read_text(encoding="utf-8").split("\n", 1)[0]
            if pid.isdigit() and f"parent={status['pid']} " in first and engine_daemon._alive(int(pid)):
                children.append((role, int(pid)))
        self.assertEqual(children, [("worker", status["workers"][0]["pid"])])
        self.assertIsNone(status["standby"])

    def test_warming_starts_the_server_before_any_document(self) -> None:
        """What the viewer asks at its launch (``{"op": "warm"}``): the daemon, its server and the
        processes a first document waits on, started with no document served; asked again, nothing more."""
        self.own()
        probe = ("import json; from cad.engine.client import request; "
                 "print(json.dumps([request({'op': 'warm'}), request({'op': 'warm'}), request({'op': 'status'})]))")
        done = engine_daemon.run([sys.executable, "-c", probe], cwd=self.folder, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        first, again, status = json.loads(done.stdout.strip().splitlines()[-1])
        self.assertEqual((first, again), ({"ok": True}, {"ok": True}))
        self.assertTrue(status["serving"]["url"].startswith("http://127.0.0.1:"))
        self.assertEqual(status["serving"]["documents"], [])

    @unittest.skipIf(os.name == "nt", "a terminate signal is POSIX's")
    def test_a_terminated_daemon_stops_as_stop_does(self) -> None:
        import signal

        self.own()

        probe = ("import json; from cad.engine.client import request; request({'op': 'warm'}); "
                 "print(request({'op': 'status'})['pid'])")
        done = engine_daemon.run([sys.executable, "-c", probe], cwd=self.folder, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        pid = int(done.stdout.split()[-1])
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 30
        while engine_daemon._alive(pid) or any(self.state.glob("*.door")):
            self.assertLess(time.monotonic(), deadline, "the daemon shut down and removed its door")
            time.sleep(0.05)


if __name__ == "__main__":
    unittest.main()
