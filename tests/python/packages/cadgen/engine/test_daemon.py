"""The warm loop through the daemon: started on demand, one worker per script that keeps
its memo between builds, its socket and lock its only files, gone when idle."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
import urllib.request
from pathlib import Path
from unittest import mock
from tests.python.support import engine_daemon

SRC = Path(__file__).resolve().parents[5] / "packages" / "cadgen" / "src"

MODEL = """
import build123d as bd
from cadgen.engine import xbf

SIZE = {size}


@xbf("XBF/block.xbf")
def block():
    return bd.fillet(bd.Box(SIZE, 4, 2).edges().filter_by(bd.Axis.Z), 0.5)

if __name__ == "__main__":
    block()
"""


# A bare model: no file, its document the worker's memory alone.
BARE = """
import build123d as bd
from cadgen.engine import model


@model
def bracket():
    return bd.Box({size}, 2, 3)

if __name__ == "__main__":
    bracket()
"""


PLUG = """
import build123d as bd
from cadgen.engine import stl


@stl("plug.stl")
def plug():
    return bd.Box(2, 2, 2) - bd.Cylinder(0.5, 3)

if __name__ == "__main__":
    plug()
"""


PAIR = """
import build123d as bd
from cadgen.engine import xbf

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


CUT = """
import build123d as bd
from cadgen.engine import xbf

SIZE = {size}


@xbf("XBF/cut.xbf")
def cut():
    peg = bd.Cylinder(2, 10)
    plate = bd.Box(10, 10, 4) - bd.Pos(SIZE / 10, 0, 0) * peg
    plate.label = "plate"
    peg.label = "peg"
    other = bd.Pos(20, 0, 0) * (bd.Box(6, 6, 6) + bd.Sphere(3.5))
    other.label = "other"
    return bd.Compound(children=[plate, bd.Pos(0, 20, 0) * peg, other], label="cut")

if __name__ == "__main__":
    cut()
"""


def get(url: str, token: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Authorization": "Bearer "+token}), timeout=120) as response:
        return response.read()


def get_json(url: str, token: str) -> dict:
    return json.loads(get(url, token))


class PatcherTest(unittest.TestCase):
    """What a worker meshes for a build: only parts a served document lacks, never a whole
    document whose meshes the daemon has not made yet."""

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-patcher-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.script = self.folder / "pair.py"

    def build(self, size: int):
        from cadgen.engine import build as engine_build
        from cadgen.engine import document

        self.script.write_text(textwrap.dedent(PAIR.format(size=size)), encoding="utf-8")
        os.utime(self.script, ns=(time.time_ns(), time.time_ns()))
        self.assertTrue(engine_build.build(self.script, ["pair"], cwd=self.folder)[-1]["ok"])
        return document.saved(self.folder / "XBF/pair.xbf")

    def patch(self, request: dict, tree) -> list:
        from cadgen.engine.worker import Patcher

        sent: list = []
        patcher = Patcher(request, lambda message, payload: sent.append(message))
        patcher.saved(self.folder / "XBF/pair.xbf", tree)
        return sent

    def test_a_document_nobody_serves_is_meshed_by_no_build(self) -> None:
        tree = self.build(10)
        self.assertEqual(self.patch({}, tree), [])

    def test_a_served_document_s_unchanged_parts_are_not_meshed_by_the_build(self) -> None:
        first = self.build(10)
        served = sorted({part.key for part in first.parts})
        edited = self.build(12)
        from cadgen.engine.ids import file_id

        ident = file_id(self.folder / "XBF/pair.xbf")
        # The daemon serves the first build's document and holds no mesh yet (a cold daemon).
        sent = self.patch({"served": {ident: "0-0"}, "served_keys": {ident: served}, "held": [], "shapes": []}, edited)
        self.assertEqual(len(sent), 1)
        self.assertEqual(len(sent[0]["patch"]["meshes"]), 1, "the changed part alone")


LOADS = """
import build123d as bd
from cadgen.engine import xbf

with open("loads.txt", "a", encoding="utf-8") as handle:  # one line per load of the script
    handle.write("load\\n")


@xbf("XBF/block.xbf")
def block():
    return bd.Box(3, 2, 1)


@xbf("XBF/peg.xbf")
def peg():
    return bd.Cylinder(1, 3)
"""


class WorkerLoopTest(unittest.TestCase):
    """A worker's request loop, driven as the daemon drives it: its collection waits until it is
    idle, and one run's calls of a script are served from one load while its files stand."""

    def setUp(self) -> None:
        import queue
        import threading

        self.folder = Path(tempfile.mkdtemp(prefix="engine-worker-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.script = self.folder / "pair.py"
        self.script.write_text(textwrap.dedent(LOADS), encoding="utf-8")
        env = {**os.environ, "PYTHONPATH": str(SRC), "CADGEN_ENGINE_WORKER": "1"}
        self.worker = subprocess.Popen([sys.executable, "-P", "-m", "cadgen.engine.worker"], stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, cwd=self.folder)
        self.addCleanup(self._stop)
        self.frames: "queue.Queue[dict | None]" = queue.Queue()

        def read() -> None:
            stream = self.worker.stdout
            for line in iter(stream.readline, b""):
                frame = json.loads(line)
                if frame.get("bytes"):
                    stream.read(frame["bytes"])
                self.frames.put(frame)
            self.frames.put(None)

        threading.Thread(target=read, daemon=True).start()
        self.assertIn("ready", self.next())

    def _stop(self) -> None:
        self.worker.stdin.close()
        self.worker.wait(timeout=60)
        self.worker.stdout.close()

    def next(self) -> dict:
        frame = self.frames.get(timeout=300)
        self.assertIsNotNone(frame, "the worker exited")
        return frame

    def ask(self, ident: int, functions: list | None = None, run: str | None = None) -> None:
        request = {"id": ident, "op": "build", "script": str(self.script), "functions": functions,
                   "cwd": str(self.folder), "run": run}
        self.worker.stdin.write((json.dumps(request) + "\n").encode())
        self.worker.stdin.flush()

    def until_settled(self, ident: int, seen: list | None = None) -> list:
        """The frames up to request ``ident``'s ``settled``; its reports."""
        reports = []
        while True:
            frame = self.next()
            if seen is not None:
                seen.append(frame)
            if frame.get("id") == ident and "done" in frame:
                reports = frame["done"]
            if frame.get("id") == ident and "failed" in frame:
                self.fail(frame["failed"])
            if frame.get("id") == ident and frame.get("settled"):
                return reports

    def loads(self) -> int:
        return (self.folder / "loads.txt").read_text(encoding="utf-8").count("load")

    def test_a_queued_request_is_answered_before_the_worker_collects(self) -> None:
        # Two calls back to back: the second is queued while the first builds.
        self.ask(1, ["block"])
        self.ask(2, ["peg"])
        seen: list = []
        self.until_settled(1, seen)
        self.until_settled(2, seen)
        self.assertFalse(any("collected" in frame for frame in seen), "no collection between the two answers")
        self.assertIsInstance(self.next().get("collected"), float, "it collected once idle")

    def test_one_run_s_calls_share_a_load_until_a_file_changes(self) -> None:
        self.until_settled(self._asked(1, None, "one"))  # a cold build: bodies ran, nothing kept
        self.until_settled(self._asked(2, ["block"], "one"))  # nothing ran: this load is kept
        self.assertEqual(self.loads(), 2)
        taken = self.until_settled(self._asked(3, ["peg"], "one"))
        self.assertEqual(self.loads(), 2, "the run's next call is served from its load")
        self.assertEqual(taken[0]["cache"], {"used": True, "from": "memory"})
        self.script.write_text(self.script.read_text(encoding="utf-8") + "# edited\n", encoding="utf-8")
        self.until_settled(self._asked(4, ["block"], "one"))
        self.assertEqual(self.loads(), 3, "an edit between two calls of one run loads the script again")
        self.until_settled(self._asked(5, ["peg"], "two"))
        self.assertEqual(self.loads(), 4, "another run loads the script again")
        self.until_settled(self._asked(6, ["peg"], None))
        self.assertEqual(self.loads(), 5, "a request of no run loads it again")

    def _asked(self, ident: int, functions: list | None, run: str | None) -> int:
        self.ask(ident, functions, run)
        return ident


class AdoptTest(unittest.TestCase):
    def test_a_run_adopts_its_caller_s_environment_but_what_started_the_worker(self) -> None:
        from cadgen.engine.worker import adopt

        started = {"PYTHONPATH": "/engine", "CADGEN_ENGINE_WORKER": "1", "PYTHONDONTWRITEBYTECODE": "1",
                   "PATH": "/turn/1", "GONE": "x"}
        with mock.patch.dict(os.environ, started, clear=True):
            adopt({"PATH": "/turn/2", "TURN": "2", "PYTHONPATH": "/caller"}, {"PYTHONPATH": "/engine",
                  "CADGEN_ENGINE_WORKER": "1", "PYTHONDONTWRITEBYTECODE": "1"})
            self.assertEqual(dict(os.environ), {"PATH": "/turn/2", "TURN": "2", "PYTHONPATH": "/engine",
                                                "CADGEN_ENGINE_WORKER": "1", "PYTHONDONTWRITEBYTECODE": "1"})
            adopt(None, {})
            self.assertEqual(os.environ["TURN"], "2", "a request with no environment leaves it as it is")


class ClientGoneTest(unittest.TestCase):
    """A build's client gone mid-build (killed, or hung up): the daemon reads the worker on to its
    answer, so the worker never blocks on a full pipe and the script's next run is not stuck
    waiting on it."""

    def worker(self, stdout: bytes, stderr: bytes):
        import io
        import queue
        from types import SimpleNamespace

        from cadgen.engine.daemon import Worker

        worker = object.__new__(Worker)  # its pipes stood in for: no process
        worker.process = SimpleNamespace(stdout=io.BytesIO(stdout), stderr=io.BytesIO(stderr))
        worker.answers, worker.asked, worker.progress, worker.touched = queue.Queue(), {}, None, set()
        worker.on_progress = worker.on_patch = lambda *_args: None
        worker.on_settled = lambda *_args: None

        def gone(_message: dict) -> None:
            raise BrokenPipeError("the client hung up")

        worker.sink = gone
        return worker

    def test_the_worker_is_read_to_its_answer_when_its_client_is_gone(self) -> None:
        lines = [{"log": "a"}, {"progress": {"phase": "names"}}, {"log": "b"}, {"done": {"reports": []}}]
        worker = self.worker(b"".join((json.dumps(line) + "\n").encode() for line in lines), b"")
        worker._reader()
        self.assertEqual(worker.answers.get_nowait(), {"done": {"reports": []}})
        self.assertIsNone(worker.answers.get_nowait(), "the worker's end, after its answer")
        self.assertIsNone(worker.sink, "the gone client's sink dropped")
        self.assertEqual(worker.progress, {"phase": "names"})

    def test_its_stderr_is_read_to_the_end_when_its_client_is_gone(self) -> None:
        worker = self.worker(b"", b"a line the model printed\nanother\n")
        worker._stderr()
        self.assertIsNone(worker.sink)
        self.assertEqual(worker.process.stderr.read(), b"", "read to its end")


class ConnectTest(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "a stale socket file is a Unix daemon's")
    def test_a_connect_to_a_stale_socket_fails_and_leaves_no_socket_open(self) -> None:
        import gc
        import socket
        import warnings
        from unittest import mock

        from cadgen.engine import client

        engine = tempfile.mkdtemp(prefix="eng-", dir="/tmp")  # a short socket path
        self.addCleanup(shutil.rmtree, engine, True)
        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": engine}):
            path = client._daemon.socket_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            stale.bind(str(path))
            stale.close()  # the file stays, and nothing listens on it
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", ResourceWarning)
                self.assertIsNone(client._connect())
                gc.collect()
        self.assertEqual([w for w in caught if issubclass(w.category, ResourceWarning)], [])


class EngineFolderTest(unittest.TestCase):
    """The engine's folder holds its socket, lock and port file. One another user owns, or that
    others can write to, would let them take the socket's place: client and daemon refuse it."""

    def setUp(self) -> None:
        self.engine = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None))
        self.addCleanup(shutil.rmtree, self.engine, True)

    @unittest.skipIf(os.name == "nt", "a folder's owner and mode are POSIX's")
    def test_a_folder_others_can_write_or_another_user_owns_is_refused_by_client_and_daemon(self) -> None:
        from unittest import mock

        from cadgen.engine import client, daemon

        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": str(self.engine)}):
            self.assertIsNone(daemon.folder_refusal(daemon.state_dir()))
            self.assertTrue(daemon.socket_folder_ok(daemon.socket_path()))
            os.chmod(self.engine, 0o777)
            refusal = daemon.folder_refusal(daemon.state_dir())
            self.assertIn("can be written by others", refusal)
            self.assertFalse(daemon.socket_folder_ok(daemon.socket_path()))
            with mock.patch.object(client, "_start", side_effect=AssertionError("a daemon was started")):
                with self.assertRaisesRegex(ConnectionError, "can be written by others"):
                    client.connect()
            with self.assertRaisesRegex(PermissionError, "can be written by others"):
                daemon.lock()
            self.assertEqual(sorted(self.engine.iterdir()), [], "nothing was made in the refused folder")
            os.chmod(self.engine, 0o700)
            real, folder = os.lstat, os.fspath(daemon.state_dir())

            def foreign(path, *args, **kwargs):
                found = real(path, *args, **kwargs)
                if os.fspath(path) == folder:
                    return os.stat_result((found.st_mode, found.st_ino, found.st_dev, found.st_nlink,
                                           os.getuid() + 1, found.st_gid, found.st_size, 0, 0, 0))
                return found

            with mock.patch.object(os, "lstat", side_effect=foreign):
                self.assertIn("belongs to another user", daemon.folder_refusal(daemon.state_dir()))
                self.assertFalse(daemon.socket_folder_ok(daemon.socket_path()))
                with self.assertRaisesRegex(PermissionError, "belongs to another user"):
                    daemon.lock()


@unittest.skipIf(os.name == "nt", "the per-user folders are POSIX's")
class DefaultEngineFolderTest(unittest.TestCase):
    """With no ``CADGEN_ENGINE_DIR``, the engine's folder is one no other user can make first."""

    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp")).resolve()
        self.addCleanup(shutil.rmtree, self.base, True)
        self.system: str | None = None  # what macOS names when TMPDIR is unset: nothing, here

    def folder(self, **env: str) -> Path:
        from unittest import mock

        from cadgen.engine import daemon

        cleared = {key: value for key, value in os.environ.items()
                   if key not in ("CADGEN_ENGINE_DIR", "XDG_RUNTIME_DIR", "TMPDIR")}
        with mock.patch.dict(os.environ, {**cleared, **env}, clear=True), \
                mock.patch.object(daemon, "_darwin_temp", return_value=self.system):
            return daemon.state_dir()

    def private(self, name: str, mode: int = 0o700) -> Path:
        folder = self.base / name
        folder.mkdir()
        os.chmod(folder, mode)
        return folder

    def test_the_runtime_folder_then_a_private_temporary_folder_then_tmp_by_uid(self) -> None:
        runtime, own = self.private("run"), self.private("T")
        self.assertEqual(self.folder(XDG_RUNTIME_DIR=str(runtime), TMPDIR=str(own)), runtime / "cadgen-engine")
        self.assertEqual(self.folder(TMPDIR=f"{own}/"), own / "cadgen-engine")
        fallback = Path(os.path.realpath(f"/tmp/cadgen-{os.getuid()}"))
        self.assertEqual(self.folder(), fallback)
        shared = self.private("shared", 0o1777)
        self.assertEqual(self.folder(TMPDIR=str(shared), XDG_RUNTIME_DIR=str(self.base / "missing")), fallback)
        self.assertEqual(self.folder(TMPDIR="relative"), fallback)

    @unittest.skipUnless(sys.platform == "darwin", "macOS names its per-user temporary folder")
    def test_macos_without_tmpdir_finds_the_folder_a_login_session_names(self) -> None:
        from cadgen.engine import daemon

        system = daemon._darwin_temp()
        self.assertTrue(system and system.startswith("/var/folders/"), system)
        self.system = system
        self.assertEqual(self.folder(), Path(os.path.realpath(os.path.join(system, "cadgen-engine"))))

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
            self.assertEqual(self.folder(TMPDIR=str(own)), Path(os.path.realpath(f"/tmp/cadgen-{os.getuid()}")))

    def test_a_long_temporary_folder_names_its_socket_by_digest_in_the_users_own_tmp_folder(self) -> None:
        from unittest import mock

        from cadgen.engine import daemon

        own = self.private("T" + "-long" * 20)
        cleared = {key: value for key, value in os.environ.items() if key != "CADGEN_ENGINE_DIR"}
        with mock.patch.dict(os.environ, {**cleared, "TMPDIR": str(own)}, clear=True):
            os.environ.pop("XDG_RUNTIME_DIR", None)
            self.assertEqual(daemon.state_dir(), own / "cadgen-engine")
            sock = daemon.socket_path()
            self.assertLess(len(os.fsencode(sock)), daemon.SOCKET_PATH_LIMIT)
            self.assertEqual(sock.parent, Path("/tmp") / f"cadgen-{os.getuid()}")
            self.assertTrue(daemon.socket_folder_ok(sock))


class WindowsTokenFirstTest(unittest.TestCase):
    """On Windows the daemon listens on loopback TCP, which any local user can reach: a connection
    shows its token in its first bytes (the client puts it first), and one that does not is refused
    before the rest of its line is read or parsed."""

    def serve(self, payload: bytes):
        import socket
        import threading
        import types
        from unittest import mock

        from cadgen.engine import daemon

        handled = []
        engine = types.SimpleNamespace(token="ab" * 16, handle=lambda request, send: handled.append(request) or send({"ok": True}))
        server_side, client_side = socket.socketpair()
        self.addCleanup(client_side.close)
        with mock.patch.object(daemon, "WINDOWS", True):
            done = threading.Thread(target=daemon._serve_connection, args=(engine, server_side))
            done.start()
            try:
                client_side.sendall(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass  # refused after the first bytes: the rest was never read
            done.join(timeout=30)
        self.assertFalse(done.is_alive(), "the connection was answered or refused, not held")
        return handled, engine.token

    def test_a_connection_without_the_token_first_is_refused_before_its_line_is_read(self) -> None:
        handled, _token = self.serve(b'{"token": "' + b"0" * 32 + b'", "op": "status", "pad": "' + b"x" * 200_000)
        self.assertEqual(handled, [])

    def test_the_client_puts_its_token_first_and_is_served(self) -> None:
        import socket
        import threading
        from unittest import mock

        from cadgen.engine import client

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
        with mock.patch.object(client._daemon, "WINDOWS", True):
            self.assertEqual(client._exchange(ours, {"op": "status"}, address=port_file), {"ok": True})
        answering.join(timeout=30)
        self.assertTrue(sent[0].startswith(b'{"token": "' + token.encode() + b'", "op": "status"'))
        handled, _token = self.serve(sent[0])
        self.assertEqual(handled, [{"token": token, "op": "status"}])


class DaemonEnvironmentTest(unittest.TestCase):
    """The daemon serves every later client, so the client that starts it does not hand it a
    per-process telemetry switch: those are the person's saved choice's to decide."""

    def test_the_started_daemon_does_not_inherit_the_telemetry_switches(self) -> None:
        from unittest import mock

        from cadgen import analytics
        from cadgen.engine import client

        self.assertEqual(set(client._PER_PROCESS_TELEMETRY), set(analytics.ENVIRONMENT),
                         "the engine's copy of the per-process switches must match cadgen.analytics")
        captured = {}

        class FakePopen:
            def __init__(self, _argv, **kwargs):
                captured.update(kwargs.get("env") or {})

        with mock.patch.dict(os.environ, {"DO_NOT_TRACK": "1", "CADGEN_TELEMETRY": "1", "PATH": os.environ.get("PATH", "")}), \
                mock.patch.object(client.subprocess, "Popen", FakePopen):
            client._start()
        self.assertNotIn("DO_NOT_TRACK", captured)
        self.assertNotIn("CADGEN_TELEMETRY", captured)


class SweepTest(unittest.TestCase):
    """``cadgen stop`` reaches every server of the installation, whatever protocol it speaks, and
    ``stop`` and ``status`` take away the files of a dead one."""

    def setUp(self) -> None:
        self.state = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        self.addCleanup(shutil.rmtree, self.state, True)
        self.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CADGEN_ENGINE_DIR": str(self.state),
                                          "CADGEN_ENGINE_IDLE": "60"}, self.addCleanup)

    def cli(self, *args: str) -> subprocess.CompletedProcess:
        return engine_daemon.run([sys.executable, "-m", "cadgen.engine", *args], env=self.env)

    @unittest.skipIf(os.name == "nt", "a stale socket file is a Unix daemon's")
    def test_a_dead_server_s_socket_and_lock_are_removed_and_said(self) -> None:
        import socket
        from unittest import mock

        from cadgen.engine import daemon

        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": str(self.state)}):
            path, lock = daemon.socket_path(), daemon.lock_path()
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stale.bind(str(path))
        stale.close()  # the file stays, and nothing listens on it
        lock.write_text("", encoding="utf-8")
        done = self.cli("status")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "no engine server is running")
        self.assertIn(f"removed stale engine file {path}", done.stderr)
        self.assertIn(f"removed stale engine file {lock}", done.stderr)
        self.assertEqual(list(self.state.iterdir()), [])
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stale.bind(str(path))
        stale.close()
        done = self.cli("stop")
        self.assertEqual((done.returncode, done.stdout), (0, "no engine server is running\n"), done.stderr)
        self.assertEqual(done.stderr, f"removed stale engine file {path}\n", "a swept file a line on stderr")

    def test_a_server_of_an_older_protocol_is_still_stopped(self) -> None:
        from unittest import mock

        from cadgen.engine import client, daemon

        older = daemon.PROTOCOL - 1 or 1
        # The server a cadgen of an older protocol started: the same installation, its own socket.
        server = subprocess.Popen([sys.executable, "-c", "import sys; from cadgen.engine import daemon; "
                                   f"daemon.PROTOCOL = {older}; sys.exit(daemon.main())"], env=self.env,
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: server.poll() is None and server.kill())
        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": str(self.state)}), \
                mock.patch.object(daemon, "PROTOCOL", older + 1):
            address = (daemon.port_path if daemon.WINDOWS else daemon.socket_path)(older)
            deadline = time.monotonic() + 60
            while (found := client._connect(address)) is None:
                self.assertIsNone(server.poll(), "the older server exited before it listened")
                self.assertLess(time.monotonic(), deadline, "the older server listened")
                time.sleep(0.05)
            found.close()
            self.assertIsNone(client.request({"op": "status"}, start=False), "this protocol's server is another")
        # ``cadgen stop`` of this protocol reaches it, and says so in one line, no JSON.
        done = self.cli("stop")
        self.assertEqual((done.returncode, done.stdout, done.stderr),
                         (0, f"stopped the engine server at {address}\n", ""))
        self.assertEqual(server.wait(timeout=60), 0)
        self.assertFalse(address.exists())
        done = self.cli("stop")
        self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "no engine server is running\n", ""))
        done = self.cli("stop", "--json")
        self.assertEqual((done.returncode, json.loads(done.stdout)), (0, {"ok": True, "stopped": []}))


class StateDirSpellingTest(unittest.TestCase):
    def test_a_server_started_under_a_dotted_spelling_is_found_and_stopped_under_the_plain_one(self) -> None:
        from unittest import mock

        from cadgen.engine import client

        state = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        self.addCleanup(shutil.rmtree, state, True)
        (state / "sub").mkdir()
        # Long enough that the socket is named by its folder's digest (``SOCKET_PATH_LIMIT``): two
        # spellings of one folder must hash alike.
        engine = "engine-" * 14
        dotted = f"{state / 'sub'}{os.sep}..{os.sep}{engine}{os.sep}"  # a `..` and a trailing separator
        plain = str(state / engine)
        env = {**os.environ, "PYTHONPATH": str(SRC), "CADGEN_ENGINE_IDLE": "60"}
        dotted_env = engine_daemon.watched({**env, "CADGEN_ENGINE_DIR": dotted}, self.addCleanup)
        plain_env = engine_daemon.watched({**env, "CADGEN_ENGINE_DIR": plain}, self.addCleanup)
        self.addCleanup(engine_daemon.run, [sys.executable, "-m", "cadgen.engine", "stop"], env=plain_env)
        probe = "from cadgen.engine.client import request; print(request({'op': 'status'})['pid'])"
        started = engine_daemon.run([sys.executable, "-c", probe], env=dotted_env)
        self.assertEqual(started.returncode, 0, started.stderr)
        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": plain}):
            found = client.request({"op": "status"}, start=False)
            address = client._daemon.port_path() if client._daemon.WINDOWS else client._daemon.socket_path()
        self.assertIsNotNone(found, "the plain spelling reaches the server the dotted one started")
        self.assertEqual(str(found["pid"]), started.stdout.split()[-1])
        done = engine_daemon.run([sys.executable, "-m", "cadgen.engine", "stop"], env=plain_env)
        self.assertEqual((done.returncode, done.stdout), (0, f"stopped the engine server at {address}\n"), done.stderr)
        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": dotted}):
            self.assertIsNone(client.request({"op": "status"}, start=False), "stopped under either spelling")


class LongStatePathTest(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "a socket's path limit is a Unix socket's")
    def test_a_state_folder_past_the_socket_path_limit_works_and_nobody_changes_folder(self) -> None:
        from unittest import mock

        from cadgen.engine import client

        engine = Path(tempfile.mkdtemp(prefix="eng-")) / ("long-" * 24)
        self.addCleanup(shutil.rmtree, engine.parent, True)
        env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CADGEN_ENGINE_DIR": str(engine)},
                                    self.addCleanup)
        self.addCleanup(engine_daemon.run, [sys.executable, "-m", "cadgen.engine", "stop"], env=env)
        probe = "from cadgen.engine.client import request; print(request({'op': 'status'})['ok'])"
        started = engine_daemon.run([sys.executable, "-c", probe], env=env)
        self.assertEqual((started.returncode, started.stdout.split()[-1:]), (0, ["True"]), started.stderr)
        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": str(engine)}), \
                mock.patch.object(os, "chdir", side_effect=AssertionError("the client changed folder")):
            path = client._daemon.socket_path()
            self.assertLess(len(os.fsencode(path)), 100, "the socket's own path fits the limit")
            self.assertTrue(client.request({"op": "status"}, start=False)["ok"])
        self.assertEqual(os.stat(path.parent).st_mode & 0o077, 0, "the socket's folder is the user's alone")


class InstallationTest(unittest.TestCase):
    def test_every_name_of_the_installation_s_interpreter_reaches_one_engine(self) -> None:
        from unittest import mock

        from cadgen.engine import daemon

        folder = os.path.dirname(sys.executable)
        names = [os.path.join(folder, name) for name in ("python", "python3", f"python3.{sys.version_info[1]}")]
        tags = set()
        for name in names:
            with mock.patch.object(sys, "executable", name):
                tags.add(daemon.socket_path())
        self.assertEqual(len(tags), 1, "`python3 model.py` and `cadgen viewer` share one engine")

    def test_a_relative_and_an_absolute_launch_reach_one_engine(self) -> None:
        # `../../.venv/bin/python model.py` from a model folder, and the absolute path.
        probe = "from cadgen.engine import daemon; print(daemon.socket_path())"
        env = {**os.environ, "PYTHONPATH": str(SRC)}
        with tempfile.TemporaryDirectory() as folder:
            folder = os.path.realpath(folder)
            relative = os.path.relpath(sys.executable, folder) if os.path.splitdrive(sys.executable)[0].lower() \
                == os.path.splitdrive(folder)[0].lower() else sys.executable
            found = {subprocess.run([command, "-c", probe], cwd=folder, env=env, capture_output=True, text=True,
                                    timeout=60).stdout.strip() for command in (relative, sys.executable)}
        self.assertEqual(len(found), 1, found)


class PoolExitTest(unittest.TestCase):
    def test_a_pool_process_exits_when_its_engine_dies_without_cleaning_up(self) -> None:
        probe = ("import os; from cadgen.engine.serve import Mesher; mesher = Mesher('processes', workers=1); "
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

        from cadgen._internal import engine_host
        from cadgen.engine import daemon

        taken = socket.socket()
        self.addCleanup(taken.close)
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]
        engine = daemon.Daemon(60)
        with mock.patch("cadgen.engine.serve.Mesher") as mesher, mock.patch.object(daemon, "HTTP_FACTORY", None):
            with self.assertRaisesRegex(ValueError, f"127.0.0.1:{port}: .*; pass another --port"):
                engine.serve({"port": port})
        mesher.return_value.stop.assert_called_once_with()
        self.assertIsNone(engine.server, "the next request may still choose its port")
        with mock.patch("cadgen.viewer.engine_app.EngineApp") as app, self.assertRaises(OSError):
            engine_host.http_factory(mock.Mock(), "127.0.0.1", port)
        app.return_value.close.assert_called_once_with()


class DaemonTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-daemon-")).resolve()
        self.state = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        self.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CADGEN_ENGINE_DIR": str(self.state),
                                          "CADGEN_ENGINE_IDLE": "60", "CADGEN_ENGINE_MESH": "inline"}, self.addCleanup)
        self.addCleanup(self._stop)
        self.script = self.folder / "block.py"

    def _stop(self) -> None:
        self._stop_daemon()
        shutil.rmtree(self.folder, ignore_errors=True)
        shutil.rmtree(self.state, ignore_errors=True)

    def _stop_daemon(self) -> None:
        self.cli("stop")
        deadline = time.monotonic() + 20
        while any(self.state.glob("*.sock")) and time.monotonic() < deadline:
            time.sleep(0.05)

    def cli(self, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        return engine_daemon.run([sys.executable, "-m", "cadgen.engine", *args], cwd=self.folder, env=env or self.env)

    def run_script(self, name: str, env: dict | None = None) -> subprocess.CompletedProcess:
        """``python NAME``: the script asks the daemon to build its models."""
        return engine_daemon.run([sys.executable, name], cwd=self.folder, env=env or self.env)

    def built(self, name: str, env: dict | None = None) -> dict:
        """Model ``name`` of ``name.py`` built through the daemon by ``Model.build()``: its report."""
        probe = f"import json, {name}; print(json.dumps({name}.{name}.build().models[0]))"
        done = engine_daemon.run([sys.executable, "-B", "-c", probe], cwd=self.folder, env=env or self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout.strip().splitlines()[-1])

    def build(self, size: int) -> dict:
        self.script.write_text(textwrap.dedent(MODEL.format(size=size)), encoding="utf-8")
        return self.built("block")

    def test_inspection_never_builds_missing_or_stale_script_models(self):
        from cadgen.engine.ids import model_id

        # The registry alone, no document cache: a restart is refused with the command
        # (what the cache reopens is ``test_cache``'s).
        self.env = {**self.env, "CADGEN_ENGINE_CACHE_GB": "0"}

        marker = self.folder / "executed.txt"
        main = self.folder / "main.txt"
        self.script.write_text(textwrap.dedent(MODEL.format(size=3)).replace(
            'if __name__ == "__main__":',
            f'from pathlib import Path\nPath({str(marker)!r}).write_text("imported", encoding="utf-8")\n'
            f'if __name__ == "__main__":\n    Path({str(main)!r}).write_text("main", encoding="utf-8")'), encoding="utf-8")
        ident = model_id(self.script, "block")
        # An id nothing holds is refused, naming no build: the engine runs nothing.
        for options in ((), ("face 1",), ("--query", "build")):
            missing = self.cli("inspect", ident, *options)
            self.assertNotEqual(missing.returncode, 0, missing.stdout)
            self.assertIn(f"no document {ident} is held", missing.stderr)
        self.assertFalse(marker.exists())
        self.assertFalse((self.folder / "XBF/block.xbf").exists())
        self.built("block")
        self.assertTrue(marker.exists())
        self.assertFalse(main.exists(), "explicit decorated-model build does not execute __main__")
        saved = (self.folder / "XBF/block.xbf").read_bytes()
        marker.unlink()
        self.script.write_text('raise RuntimeError("inspection ran source")\n', encoding="utf-8")
        for options in ((), ("face 1",), ("--query", "build")):
            inspected = self.cli("inspect", ident, *options)
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertEqual((self.folder / "XBF/block.xbf").read_bytes(), saved)
        self.assertFalse(marker.exists())
        self._stop_daemon()
        # After a restart the registry knows it: refused with the command that builds it again, run by no one.
        missing = self.cli("inspect", ident, "face 1")
        self.assertEqual(missing.returncode, 2)
        self.assertIn(f"block ({ident}) is no longer held: run `python ", missing.stderr)
        self.assertFalse(marker.exists())
        inspected = self.cli("inspect", str(self.folder / "XBF/block.xbf"), "--query", "build")
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertIsNone(json.loads(inspected.stdout)["live"])

    def _bare(self) -> str:
        """``bracket.py``: one bare ``@model``, a document of memory alone, and its id."""
        from cadgen.engine.ids import model_id

        script = self.folder / "bracket.py"
        script.write_text(textwrap.dedent(BARE.format(size=1)), encoding="utf-8")
        return model_id(script, "bracket")

    def test_a_named_model_updates_one_address_and_after_a_restart_names_its_command(self) -> None:
        from urllib.parse import urlparse, parse_qs

        self.env = {**self.env, "CADGEN_ENGINE_CACHE_GB": "0"}  # no document cache: ``test_cache``'s

        address = self._bare()
        first = self.built("bracket")
        self.assertEqual(first["files"], {})
        self.assertEqual(first["id"], address)
        self.assertNotIn("address", first, "a report names its document by its id alone")
        self.assertEqual(first["meshed"], 0)
        url = urlparse(first["url"])
        doc = url.path.strip("/")
        endpoint = f"{url.scheme}://{url.netloc}/api/doc/{doc}"
        token = parse_qs(url.query)["token"][0]
        before = get_json(endpoint, token)
        (self.folder / "bracket.py").write_text(textwrap.dedent(BARE.format(size=2)), encoding="utf-8")
        second = self.built("bracket")
        self.assertEqual(second["url"], first["url"])
        from cadgen.engine.ids import model_id

        self.assertEqual((first["id"], second["id"], doc), (model_id(self.folder / "bracket.py", "bracket"),) * 3,
                         "two builds of one function are one document, served by its id")
        after = get_json(endpoint, token)
        self.assertNotEqual(before["version"], after["version"])
        measured = self.cli("inspect", f"{address}#face 1")
        self.assertEqual(measured.returncode, 0, measured.stderr)
        self.assertEqual(json.loads(measured.stdout)["kind"], "face")
        models = json.loads(self.cli("status", "--json").stdout)["models"]
        self.assertEqual([row["id"] for row in models], [address])
        self.assertEqual([path.name for path in self.folder.iterdir()], ["bracket.py"],
                         "no cache, document, or thumbnail on disk")
        self._stop_daemon()
        missing = self.cli("inspect", f"{address}#face 1")
        self.assertEqual(missing.returncode, 2)
        self.assertIn(f"bracket ({address}) is no longer held: run `python ", missing.stderr)
        self.assertEqual(json.loads(self.cli("status", "--json").stdout)["models"], [],
                         "a restart holds nothing: status lists what this server built")

    def test_a_snapshot_of_a_job_draws_a_memory_model_without_an_intermediate_document(self) -> None:
        from tests.python.packages.cadgen.engine.test_snapshot import gl

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

    def test_a_script_is_never_a_source_and_an_id_is_read_as_held(self) -> None:
        """No verb imports, runs or builds a script: ``x.py`` and ``x.py::f`` are refused as any file
        that is no document is. An id is the document the engine holds: exported after the script
        changed, it writes the same bytes, and nothing runs."""
        from cadgen.engine.ids import model_id

        marker = self.folder / "ran.txt"
        self.script.write_text(textwrap.dedent(MODEL.format(size=3)).replace(
            "def block():\n", f"def block():\n    open({str(marker)!r}, 'w', encoding='utf-8').write('ran')\n"),
            encoding="utf-8")
        for named in (str(self.script), f"{self.script}::block"):
            for verb, *rest in (("export", "refused.step"), ("serve",), ("inspect",), ("snapshot", "refused.png")):
                with self.subTest(verb=verb, source=named):
                    refused = self.cli(verb, named, *rest)
                    self.assertEqual(refused.returncode, 2, refused.stderr)
                    self.assertRegex(refused.stderr, "is no document|is neither a document")
        self.assertEqual(sorted(path.name for path in self.folder.iterdir()), ["block.py"], "nothing ran, nothing was written")
        ident = self.built("block")["id"]
        self.assertEqual(ident, model_id(self.script, "block"))
        marker.unlink()
        first = self.cli("export", ident, "first.step")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.script.write_text(textwrap.dedent(MODEL.format(size=9)), encoding="utf-8")
        again = self.cli("export", ident, "again.step")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual((self.folder / "again.step").read_bytes(), (self.folder / "first.step").read_bytes(),
                         "the held document, as it was built")
        self.assertFalse(marker.exists(), "an id is never built")

    def test_a_program_reports_every_model_its_calls_build_wherever_each_is_defined(self) -> None:
        from urllib.parse import urlsplit

        from cadgen.engine.ids import model_id

        (self.folder / "parts.py").write_text(textwrap.dedent(BARE.format(size=1)).replace("bracket", "cube"),
                                              encoding="utf-8")
        (self.folder / "caller.py").write_text("import parts\nparts.cube()\n", encoding="utf-8")
        done = self.run_script("caller.py")
        self.assertEqual(done.returncode, 0, done.stderr)
        ident = model_id(self.folder / "parts.py", "cube")
        self.assertIn(f"  id: {ident}", done.stdout)
        view = next(line for line in done.stdout.splitlines() if line.startswith("  view: "))
        self.assertEqual(urlsplit(view.removeprefix("  view: ")).path, f"/{ident}")

    def test_main_calls_bare_and_file_models_in_order_and_keeps_its_arguments(self) -> None:
        self.script.write_text("""import sys
from cadgen import model, step, xbf
import build123d as bd
@model
def bare(): return bd.Box(1, 2, 3)
@step('saved.step')
def saved(): return bd.Box(2, 2, 3)
@xbf("XBF/document.xbf")
def document(): return bd.Box(3, 2, 3)
if __name__ == '__main__':
    print('before', sys.argv[1:])
    value = bare()
    print('volume', round(value.shape.volume))
    saved()
    document()
    print('after')
""", encoding="utf-8")
        done = engine_daemon.run([sys.executable, str(self.script), '--mine'], cwd=self.folder, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("before ['--mine']", done.stdout)
        self.assertIn('volume 6', done.stdout)
        self.assertTrue(done.stdout.rstrip().endswith('after'))
        self.assertTrue((self.folder / 'saved.step').is_file())
        self.assertTrue((self.folder / 'XBF/document.xbf').is_file())
        self.assertFalse((self.folder / 'XBF/bare.xbf').exists())

    def test_an_idle_worker_holds_no_project_folder_and_a_build_reads_relative_to_its_script(self) -> None:
        (self.folder / "size.txt").write_text("7", encoding="utf-8")
        self.script.write_text(textwrap.dedent(MODEL.format(size='float(open("size.txt").read())')), encoding="utf-8")
        done = self.run_script("block.py")
        self.assertEqual(done.returncode, 0, done.stderr)
        worker = json.loads(self.cli("status", "--json").stdout)["workers"][0]["pid"]
        if os.name == "nt":  # a folder a process stands in cannot be renamed
            moved = self.folder.with_name(self.folder.name + "-moved")
            os.rename(self.folder, moved)
            os.rename(moved, self.folder)
            return
        if sys.platform.startswith("linux"):
            where = os.readlink(f"/proc/{worker}/cwd")
        else:
            listed = subprocess.run(["lsof", "-a", "-p", str(worker), "-d", "cwd", "-Fn"], capture_output=True,
                                    text=True, timeout=60).stdout
            where = next(line[1:] for line in listed.splitlines() if line.startswith("n"))
        self.assertNotEqual(os.path.realpath(where), os.path.realpath(self.folder), "the idle worker left the folder")

    def test_a_warm_worker_keeps_its_memo_between_builds(self) -> None:
        cold = self.build(10)
        self.assertGreater(cold["memo"]["misses"], 0)
        self.assertEqual(cold["memo"]["hits"], 0)
        warm = self.build(10)
        self.assertEqual(warm["memo"]["misses"], 0)
        # Unchanged: its document holds the model's key, in the worker's memory, and nothing runs.
        self.assertEqual((warm["memo"]["bodies_run"], warm["memo"]["bodies_skipped"], warm["cache"]),
                         (0, 0, {"used": True, "from": "memory"}))
        edited = self.build(12)
        self.assertGreater(edited["memo"]["misses"], 0)
        self.assertTrue(edited["files"][str(self.folder / "XBF/block.xbf")]["written"])
        status = json.loads(self.cli("status", "--json").stdout)
        self.assertEqual(len(status["workers"]), 1)
        self.assertEqual(status["workers"][0]["builds"], 3)
        # The daemon's only files are its socket and lock; the build's, its outputs.
        # The daemon's socket (on Windows the port file standing in for it) and its lock, nothing else.
        self.assertEqual({path.suffix for path in self.state.iterdir()}, {".port" if os.name == "nt" else ".sock", ".lock"})
        self.assertEqual(sorted(path.relative_to(self.folder).as_posix() for path in self.folder.rglob("*") if path.is_file()),
                         ["XBF/block.xbf", "block.py"])

    def test_a_caller_s_other_path_keeps_the_warm_worker_and_another_pythonpath_replaces_it(self) -> None:
        # Each load of the script in the worker says which caller's environment it runs in.
        seen = "import os\nif os.environ.get('CADGEN_ENGINE_WORKER'):\n" \
               "    open('seen.txt', 'a').write(os.environ.get('TURN', '') + ' ' + os.environ['PATH'] + '\\n')\n"
        self.script.write_text(seen + textwrap.dedent(MODEL.format(size=10)), encoding="utf-8")

        def pid() -> int:
            status = json.loads(self.cli("status", "--json").stdout)
            self.assertEqual(len(status["workers"]), 1)
            return status["workers"][0]["pid"]

        self.assertGreater(self.built("block", env={**self.env, "TURN": "1"})["memo"]["misses"], 0)
        first = pid()
        # An agent's next turn: its shell's PATH and its own variables are new; the run adopts them.
        turn = {**self.env, "TURN": "2", "PATH": os.pathsep.join([str(self.folder), self.env.get("PATH", "")])}
        warm = self.built("block", env=turn)
        self.assertEqual((warm["memo"]["misses"], warm["cache"]), (0, {"used": True, "from": "memory"}),
                         "taken from the warm worker's memory, as a restart never is")
        self.assertEqual(pid(), first)
        self.assertEqual(json.loads(self.cli("status", "--json").stdout)["retired"], [])
        self.assertEqual((self.folder / "seen.txt").read_text(encoding="utf-8").splitlines()[-1],
                         f"2 {turn['PATH']}", "the run adopted its caller's environment")
        # Another PYTHONPATH is another interpreter: its worker is replaced, and says why.
        other = {**self.env, "PYTHONPATH": os.pathsep.join([self.env["PYTHONPATH"], str(self.folder)])}
        self.built("block", env=other)
        self.assertNotEqual(pid(), first)
        retired = json.loads(self.cli("status", "--json").stdout)["retired"]
        self.assertEqual([(row["pid"], row["reason"]) for row in retired], [(first, "environment")])

    def test_a_warm_build_writes_the_bytes_a_cold_one_does(self) -> None:
        """A warm worker's faces carry whichever ``Checked`` flag the memo's replay left
        them; the document writes them all cleared. So a fresh worker, building the file
        afresh, writes the bytes the warm one did."""
        self.script = self.folder / "cut.py"
        xbf = self.folder / "XBF/cut.xbf"

        def build(size: int) -> dict:
            self.script.write_text(textwrap.dedent(CUT.format(size=size)), encoding="utf-8")
            return self.built("cut")

        build(10)
        cold = xbf.read_bytes()
        build(12)
        self.assertTrue(build(10)["files"][str(xbf)]["written"], "the edit's file is replaced")
        self.assertEqual(xbf.read_bytes(), cold, "the warm worker wrote the cold one's bytes")
        self._stop_daemon()
        self.assertTrue(build(10)["cache"]["used"], "a fresh worker takes the file its key is in")
        xbf.unlink()
        self._stop_daemon()
        self.assertTrue(build(10)["files"][str(xbf)]["written"])
        self.assertEqual(xbf.read_bytes(), cold, "a fresh worker writes the same bytes")

    def test_a_served_document_follows_the_build_without_its_file_being_read(self) -> None:
        self.script = self.folder / "pair.py"
        self.script.write_text(textwrap.dedent(PAIR.format(size=10)), encoding="utf-8")
        self.assertEqual(self.run_script("pair.py").returncode, 0)
        served = self.cli("serve", "XBF/pair.xbf")
        self.assertEqual(served.returncode, 0, served.stderr)
        from urllib.parse import urlsplit, parse_qs
        url = urlsplit(served.stdout.strip())
        base, query = f"{url.scheme}://{url.netloc}", parse_qs(url.query)
        ident, token = url.path.strip("/"), query["token"][0]
        api = f"{base}/api/doc/{ident}"
        before = get_json(api, token)
        for prototype in before["prototypes"]:  # the page has every part
            self.assertEqual(get(f"{api}/part/{prototype['key']}", token)[:4], b"XBM2")
        self.script.write_text(textwrap.dedent(PAIR.format(size=12)), encoding="utf-8")
        self.assertEqual(self.run_script("pair.py").returncode, 0)
        answer = get_json(f"{api}/version?after={before['version']}&wait=60", token)
        stat = (self.folder / "XBF/pair.xbf").stat()
        self.assertEqual(answer["version"], f"{stat.st_mtime_ns}-{stat.st_size}")
        self.assertIsNotNone(answer["patch"], "the document came from the worker, not from its file")
        self.assertEqual(answer["patch"]["meshes"], 1, "the worker meshed the changed part alone")
        after = get_json(api, token)
        keys = lambda s: {p["name"]: p["key"] for p in s["prototypes"]}  # noqa: E731
        self.assertNotEqual(keys(after)["block"], keys(before)["block"])
        self.assertEqual(keys(after)["peg"], keys(before)["peg"])
        self.assertEqual(get(f"{api}/part/{keys(after)['block']}", token)[:4], b"XBM2")

    def test_a_build_meshes_only_what_it_changed_of_a_served_document(self) -> None:
        self.script = self.folder / "pair.py"
        self.script.write_text(textwrap.dedent(PAIR.format(size=10)), encoding="utf-8")
        self.assertEqual(self.built("pair")["meshed"], 0, "nobody serves it: nothing meshed")
        # A fresh daemon serves the file: its worker has built nothing yet.
        self.cli("stop")
        served = self.cli("serve", "XBF/pair.xbf")
        self.assertEqual(served.returncode, 0, served.stderr)
        from urllib.parse import urlsplit, parse_qs
        url = urlsplit(served.stdout.strip())
        base, query = f"{url.scheme}://{url.netloc}", parse_qs(url.query)
        ident, token = url.path.strip("/"), query["token"][0]
        before = get_json(f"{base}/api/doc/{ident}", token)
        self.script.write_text(textwrap.dedent(PAIR.format(size=12)), encoding="utf-8")
        self.assertEqual(self.built("pair")["meshed"], 1, "the changed part alone, not the whole document")
        answer = get_json(f"{base}/api/doc/{ident}/version?after={before['version']}&wait=60", token)
        self.assertEqual(answer["patch"]["meshes"], 1)
        self.assertEqual(self.built("pair")["meshed"], 0)

    def where(self, ref: str) -> dict:
        found = engine_daemon.run([sys.executable, "-m", "cadgen.cli", "inspect", "XBF/block.xbf", ref], cwd=self.folder,
                                  env=self.env)
        self.assertEqual(found.returncode, 0, found.stderr)
        return json.loads(found.stdout)

    def test_an_element_answers_what_made_it_from_the_worker_that_built_it(self) -> None:
        self.build(10)
        face = self.where("block/face 1")
        made = face["made_by"]
        line = next(n for n, text in enumerate(self.script.read_text(encoding="utf-8").splitlines(), 1)
                    if "bd.fillet" in text)
        self.assertEqual((made["function"], made["file"], made["line"]), ("block", str(self.script), line))
        self.assertEqual(made["name"], face["name"])
        self.assertTrue(made["feature"].startswith("block.") and made["operation"])
        self.assertGreater(face["area"], 0)
        # By its element name, the same element.
        self.assertEqual(self.where(face["name"])["ordinal"], 1)
        # A daemon started again with no build serves the file cold: no worker holds a
        # trace of it, so ``made_by`` is null -- and every fact the kernel measures is
        # what it was. Nothing of the provenance was written anywhere.
        self._stop_daemon()
        cold = self.where("block/face 1")
        self.assertIsNone(cold.pop("made_by"))
        drop = ("made_by", "meshed")
        self.assertEqual({k: v for k, v in cold.items() if k not in drop}, {k: v for k, v in face.items() if k not in drop})
        self.assertEqual(sorted(path.relative_to(self.folder).as_posix() for path in self.folder.rglob("*") if path.is_file()),
                         ["XBF/block.xbf", "block.py"])

    def test_a_worker_over_its_memory_cap_is_retired_and_the_next_build_restarts(self) -> None:
        capped = {**self.env, "CADGEN_ENGINE_WORKER_RSS_MB": "1"}
        self.script.write_text(textwrap.dedent(MODEL.format(size=10)), encoding="utf-8")
        report = self.built("block", env=capped)
        self.assertIn("over its 1 MB cap", report["retired"])
        # The next build is a fresh worker's: a restart, which takes the file it wrote.
        again = self.run_script("block.py", env=capped)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertTrue(again.stdout.startswith("took block.py::block cold"), again.stdout)
        self.assertIn("retired: the worker held", again.stdout)
        status = json.loads(self.cli("status", "--json").stdout)
        self.assertEqual(status["workers"], [], "each worker left the pool when it was retired")
        self.assertEqual([row["reason"] for row in status["retired"]], ["RSS", "RSS"])

    def test_a_failing_body_answers_with_its_error(self) -> None:
        self.script.write_text("from cadgen.engine import xbf\n\n@xbf('XBF/block.xbf')\ndef block():\n    raise RuntimeError('no')\nif __name__ == '__main__':\n    block()\n", encoding="utf-8")
        done = self.run_script("block.py")
        self.assertEqual(done.returncode, 1)
        self.assertIn("RuntimeError: no", done.stderr)

    def test_running_a_model_script_asks_the_daemon_to_build_it(self) -> None:
        # A script runs like Python and takes no options (law 11): every model it defines writes
        # what it declares, whatever its argv holds.
        self.script.write_text(textwrap.dedent(MODEL.format(size=3)) + "\n\n@stl('peg.stl')\ndef peg():\n"
                               "    return bd.Cylinder(1, 3)\nif __name__ == '__main__':\n    peg()\n", encoding="utf-8")
        self.script.write_text(self.script.read_text(encoding="utf-8").replace("import xbf", "import stl, xbf"),
                               encoding="utf-8")
        done = self.run_script("block.py")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual([line.split(" in ")[0] for line in done.stdout.splitlines() if line.startswith("built")],
                         ["built block.py::block cold", "built block.py::peg warm"])
        self.assertEqual(sum(line.startswith("  view: http://127.0.0.1:") for line in done.stdout.splitlines()), 2,
                         "each model reports its viewer link, including file-output builds")
        from urllib.parse import parse_qs, urlparse

        from cadgen.engine.ids import model_id

        # Each model reports its id, the one the script's own process derives (ids.model_id), and
        # its page is that id's.
        expected = [model_id(self.script, "block"), model_id(self.script, "peg")]
        self.assertEqual([line.removeprefix("  id: ") for line in done.stdout.splitlines() if line.startswith("  id: ")],
                         expected)
        views = [line for line in done.stdout.splitlines() if line.startswith("  view: ")]
        self.assertEqual([urlparse(line.removeprefix("  view: ")).path.strip("/") for line in views], expected)
        workers = json.loads(self.cli("status", "--json").stdout)["workers"]
        self.assertEqual([(Path(w["script"]).name, w["builds"]) for w in workers], [("block.py", 2)],
                         "the daemon's worker built it, not the script's own process")
        done = engine_daemon.run([sys.executable, "block.py", "--step", "b.step", "--json"], cwd=self.folder,
                                 env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(sorted(path.relative_to(self.folder).as_posix() for path in self.folder.rglob("*") if path.is_file()),
                         ["XBF/block.xbf", "block.py", "peg.stl"])

    def test_decoration_only_declares_and_main_calls_only_its_selected_model(self) -> None:
        self.script.write_text(textwrap.dedent("""
            from cadgen import model, xbf

            @model
            def unused():
                raise AssertionError("uncalled model ran")

            @xbf("XBF/block.xbf")
            def block():
                import build123d as bd
                return bd.Box(1, 2, 3)

            if __name__ == "__main__":
                import sys
                print("after definitions", "build123d" in sys.modules)
                if "call" in sys.argv:
                    block()
                    print("after call")
            """), encoding="utf-8")
        declared = self.run_script("block.py")
        self.assertEqual((declared.returncode, declared.stdout.strip()), (0, "after definitions False"), declared.stderr)
        self.assertFalse((self.folder / "XBF").exists())
        self.assertFalse(self.state.exists() and any(self.state.iterdir()), "importing starts no daemon")
        called = engine_daemon.run([sys.executable, "block.py", "call"], cwd=self.folder, env=self.env)
        self.assertEqual(called.returncode, 0, called.stderr)
        self.assertIn("after call", called.stdout)
        self.assertTrue((self.folder / "XBF/block.xbf").is_file())


    def test_the_viewer_moves_before_a_derived_file_is_written(self) -> None:
        # A deliberately slow STL writer, put in place in the worker by the model's own module.
        slow = textwrap.dedent("""
            import time
            from cadgen.engine import export

            if not getattr(export, "slow", False):
                class Slow(type(export.KINDS["stl"])):
                    def write(self, view, path):
                        time.sleep(3)
                        super().write(view, path)

                given = export.KINDS["stl"]
                export.KINDS["stl"] = Slow(given.name, given.suffixes, given.writer, given.atomic)
                export.slow = True
        """) + textwrap.dedent(PAIR).replace('@xbf("XBF/pair.xbf")', '@xbf("XBF/pair.xbf")\n@stl("pair.stl")').replace(
            "import xbf", "import stl, xbf")
        self.script = self.folder / "pair.py"
        self.script.write_text(slow.format(size=10), encoding="utf-8")
        self.assertEqual(self.run_script("pair.py").returncode, 0)
        served = self.cli("serve", "XBF/pair.xbf")
        from urllib.parse import urlsplit, parse_qs
        url = urlsplit(served.stdout.strip())
        base, query = f"{url.scheme}://{url.netloc}", parse_qs(url.query)
        ident, token = url.path.strip("/"), query["token"][0]
        before = get_json(f"{base}/api/doc/{ident}", token)
        stl = self.folder / "pair.stl"
        written = stl.stat().st_mtime_ns
        self.script.write_text(slow.format(size=12), encoding="utf-8")
        building = subprocess.Popen([sys.executable, "pair.py"], cwd=self.folder, env=self.env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(building.wait)
        answer = get_json(f"{base}/api/doc/{ident}/version?after={before['version']}&wait=60", token)
        self.assertNotEqual(answer["version"], before["version"])
        self.assertEqual(stl.stat().st_mtime_ns, written, "the viewer moved before the STL was written")
        self.assertEqual(building.wait(timeout=300), 0)
        self.assertNotEqual(stl.stat().st_mtime_ns, written)

    def test_exports_and_a_model_s_document_through_the_daemon(self) -> None:
        self.script = self.folder / "pair.py"
        self.script.write_text(textwrap.dedent(PAIR.format(size=10)), encoding="utf-8")
        self.assertEqual(self.run_script("pair.py").returncode, 0)
        done = self.cli("export", "XBF/pair.xbf", "pair.glb", "pair.step")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(len(json.loads(self.cli("status", "--json").stdout)["workers"]), 1,
                         "the worker that built the document wrote its exports")
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
        self.assertEqual(found["bodies"], {"plug.py::plug": "replayed"}, "the script's warm worker")
        self.assertEqual(found["name"], "plug")
        self.assertAlmostEqual(found["volume"], 8 - 3.14159265 * 0.25 * 2, places=2)

    def test_a_build_with_no_page_starts_no_meshing_process(self) -> None:
        """``python model.py`` serves its document, so the daemon starts its server; the meshing
        pool waits for a page, a view or a mesh: the daemon's only child is the worker."""
        env = {name: value for name, value in self.env.items() if name != "CADGEN_ENGINE_MESH"}
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

    def test_warming_starts_the_server_before_any_document(self) -> None:
        """What the viewer asks at its launch (``{"op": "warm"}``): the daemon, its server and the
        processes a first document waits on, started with no document served; asked again, nothing more."""
        probe = ("import json; from cadgen.engine.client import request; "
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

        probe = ("import json; from cadgen.engine.client import request; request({'op': 'warm'}); "
                 "print(request({'op': 'status'})['pid'])")
        done = engine_daemon.run([sys.executable, "-c", probe], cwd=self.folder, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        pid = int(done.stdout.split()[-1])
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 30
        while engine_daemon._alive(pid) or any(self.state.glob("*.sock")):
            self.assertLess(time.monotonic(), deadline, "the daemon shut down and removed its socket")
            time.sleep(0.05)

    def test_an_idle_daemon_exits(self) -> None:
        env = {**self.env, "CADGEN_ENGINE_IDLE": "0.5"}
        self.script.write_text(textwrap.dedent(MODEL.format(size=3)), encoding="utf-8")
        self.assertEqual(self.run_script("block.py", env=env).returncode, 0)
        deadline = time.monotonic() + 30
        while any(self.state.glob("*.sock")) and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertFalse(any(self.state.glob("*.sock")), "the idle daemon left")


if __name__ == "__main__":
    unittest.main()
