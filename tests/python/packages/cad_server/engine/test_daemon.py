"""The warm loop through the daemon: started on demand, one worker per script that keeps
its memo between builds, its door and lock its only files, gone when idle."""

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
import urllib.request
from pathlib import Path
from unittest import mock
from tests.python.support import engine_daemon
from tests.python.support.http_listener import listener
from tests.python.support.paths import add_sources

SRC = add_sources()  # the three packages' sources, as PYTHONPATH names them

MODEL = """
import build123d as bd
from cad.engine import xbf

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
from cad.engine import model


@model
def bracket():
    return bd.Box({size}, 2, 3)

if __name__ == "__main__":
    bracket()
"""


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


CUT = """
import build123d as bd
from cad.engine import xbf

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


LOADS = """
import build123d as bd
from cad.engine import xbf

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
        env = {**os.environ, "PYTHONPATH": str(SRC), "CAD_ENGINE_WORKER": "1"}
        self.worker = subprocess.Popen([sys.executable, "-P", "-m", "cad.engine.worker"], stdin=subprocess.PIPE,
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

    def until_answered(self, ident: int, seen: list | None = None) -> list:
        """The frames up to request ``ident``'s answer, its last frame; its reports."""
        while True:
            frame = self.next()
            if seen is not None:
                seen.append(frame)
            if frame.get("id") == ident and "failed" in frame:
                self.fail(frame["failed"])
            if frame.get("id") == ident and "done" in frame:
                return frame["done"]

    def loads(self) -> int:
        return (self.folder / "loads.txt").read_text(encoding="utf-8").count("load")

    def test_a_queued_request_is_answered_before_the_worker_collects(self) -> None:
        # Two calls back to back: the second is queued while the first builds.
        self.ask(1, ["block"])
        self.ask(2, ["peg"])
        seen: list = []
        self.until_answered(1, seen)
        self.until_answered(2, seen)
        self.assertFalse(any("collected" in frame for frame in seen), "no collection between the two answers")
        self.assertIsInstance(self.next().get("collected"), float, "it collected once idle")

    def test_one_run_s_calls_share_a_load_until_a_file_changes(self) -> None:
        self.until_answered(self._asked(1, None, "one"))  # a cold build: bodies ran, nothing kept
        self.until_answered(self._asked(2, ["block"], "one"))  # nothing ran: this load is kept
        self.assertEqual(self.loads(), 2)
        taken = self.until_answered(self._asked(3, ["peg"], "one"))
        self.assertEqual(self.loads(), 2, "the run's next call is served from its load")
        self.assertEqual(taken[0]["cache"], {"used": True, "from": "memory"})
        self.script.write_text(self.script.read_text(encoding="utf-8") + "# edited\n", encoding="utf-8")
        self.until_answered(self._asked(4, ["block"], "one"))
        self.assertEqual(self.loads(), 3, "an edit between two calls of one run loads the script again")
        self.until_answered(self._asked(5, ["peg"], "two"))
        self.assertEqual(self.loads(), 4, "another run loads the script again")
        self.until_answered(self._asked(6, ["peg"], None))
        self.assertEqual(self.loads(), 5, "a request of no run loads it again")

    def _asked(self, ident: int, functions: list | None, run: str | None) -> int:
        self.ask(ident, functions, run)
        return ident

    def test_a_worker_retires_by_the_cap_its_request_carries_not_its_own_environment_s(self) -> None:
        answers: dict = {}
        for ident, cap in ((1, 1), (2, None)):  # 1 MB, then none: the daemon's (``rssCapMb``)
            request = {"id": ident, "op": "build", "script": str(self.script), "functions": ["block"],
                       "cwd": str(self.folder), "env": {**os.environ, "CAD_ENGINE_WORKER_RSS_MB": "100000"},
                       "rssCapMb": cap}
            self.worker.stdin.write((json.dumps(request) + "\n").encode())
            self.worker.stdin.flush()
            while ident not in answers:
                frame = self.next()
                if frame.get("id") == ident and ("done" in frame or "failed" in frame):
                    answers[ident] = frame
        self.assertTrue(answers[1].get("retire"), answers[1])
        self.assertIn("over its 1 MB cap", answers[1]["done"][0]["retired"], "the run's 100000 MB is not the cap")
        self.assertNotIn("retire", answers[2], "no cap at all")


class KernelNoticeTest(unittest.TestCase):
    """A build on a worker whose kernel is not loaded loads it first, and a load that outlasts
    ``KERNEL_PATIENCE`` is said to the caller once while it goes on; a warm worker says nothing."""

    def test_a_slow_first_load_is_said_while_it_goes_on_and_a_loaded_kernel_says_nothing(self) -> None:
        import threading

        from cad.engine import worker

        said: list[str] = []
        told = threading.Event()

        def say(text: str) -> None:
            said.append(text)
            told.set()

        def slow() -> None:  # the first import macOS checks: still going when the notice comes
            self.assertTrue(told.wait(30), "the notice comes while the load goes on")
            worker._KERNEL_LOADED = True

        with mock.patch.object(worker, "_KERNEL_LOADED", False), mock.patch.object(worker, "KERNEL_PATIENCE", 0.01), \
                mock.patch.object(worker, "load_kernel", side_effect=slow) as load:
            worker.kernel(say)
            self.assertEqual(said, ["loading the CAD kernel for the first time in this environment, up to a minute"])
            worker.kernel(say)  # a warm worker: nothing loads, nothing is said
            self.assertEqual((load.call_count, len(said)), (1, 1))

        def quick() -> None:
            worker._KERNEL_LOADED = True

        made: list[threading.Timer] = []
        timer = threading.Timer

        def recorded(*args, **kwargs) -> threading.Timer:
            made.append(timer(*args, **kwargs))
            return made[-1]

        with mock.patch.object(worker, "_KERNEL_LOADED", False), mock.patch.object(worker, "KERNEL_PATIENCE", 30.0), \
                mock.patch.object(worker, "load_kernel", side_effect=quick), \
                mock.patch.object(worker.threading, "Timer", recorded):
            worker.kernel(say)
        self.assertEqual(len(said), 1, "a load done within the patience is not said")
        # And its timer's thread is gone when the build starts: a profiled build records every thread's
        # calls (cad.engine.profiling), and a cancelled timer waking inside it corrupted its rows.
        self.assertEqual([alive.is_alive() for alive in made], [False])


class AdoptTest(unittest.TestCase):
    def test_a_run_adopts_its_caller_s_environment_but_what_started_the_worker(self) -> None:
        from cad.engine.worker import adopt

        started = {"PYTHONPATH": "/engine", "CAD_ENGINE_WORKER": "1", "PYTHONDONTWRITEBYTECODE": "1",
                   "PATH": "/turn/1", "GONE": "x"}
        with mock.patch.dict(os.environ, started, clear=True):
            adopt({"PATH": "/turn/2", "TURN": "2", "PYTHONPATH": "/caller"}, {"PYTHONPATH": "/engine",
                  "CAD_ENGINE_WORKER": "1", "PYTHONDONTWRITEBYTECODE": "1"})
            self.assertEqual(dict(os.environ), {"PATH": "/turn/2", "TURN": "2", "PYTHONPATH": "/engine",
                                                "CAD_ENGINE_WORKER": "1", "PYTHONDONTWRITEBYTECODE": "1"})
            adopt(None, {})
            self.assertEqual(os.environ["TURN"], "2", "a request with no environment leaves it as it is")


class ClientGoneTest(unittest.TestCase):
    """A build's client gone mid-build (killed, or hung up): the daemon reads the worker on to its
    answer, so the worker never blocks on a full pipe and the script's next run is not stuck
    waiting on it."""

    def worker(self, stdout: bytes, stderr: bytes):
        import io
        import queue
        import threading
        from types import SimpleNamespace

        from cad_server.engine.services import WORKER
        from cad_server.engine.supervisor import Process

        worker = object.__new__(Process)  # its pipes stood in for: no process
        worker.service, worker.popen = WORKER, SimpleNamespace(stdout=io.BytesIO(stdout), stderr=io.BytesIO(stderr))
        worker.answers, worker.asked, worker.progress = queue.Queue(), {}, None
        worker.followers, worker.on_event = [], {}
        worker.tail, worker.said, worker.tail_lock = "", [], threading.Lock()
        worker.on_progress = lambda *_args: None

        def gone(_message: dict) -> None:
            raise BrokenPipeError("the client hung up")

        worker.sink = gone
        return worker

    def test_the_worker_is_read_to_its_answer_when_its_client_is_gone(self) -> None:
        lines = [{"log": "a"}, {"progress": {"kind": "build", "stage": "names"}}, {"log": "b"}, {"done": {"reports": []}}]
        worker = self.worker(b"".join((json.dumps(line) + "\n").encode() for line in lines), b"")
        worker._reader()
        self.assertEqual(worker.answers.get_nowait(), {"done": {"reports": []}})
        self.assertIsNone(worker.answers.get_nowait(), "the worker's end, after its answer")
        self.assertIsNone(worker.sink, "the gone client's sink dropped")
        self.assertEqual(worker.progress, {"kind": "build", "stage": "names"})
        self.assertTrue(worker.popen.stdout.closed, "the reader closes its pipe at EOF")

    def test_its_stderr_is_read_to_the_end_when_its_client_is_gone(self) -> None:
        worker = self.worker(b"", b"a line the model printed\nanother\n")
        worker._stderr()
        self.assertIsNone(worker.sink)
        self.assertTrue(worker.popen.stderr.closed, "the reader closes its pipe at EOF")


class WorkerFailureTest(unittest.TestCase):
    """Real subprocess pipes: startup diagnostics, fault output and the next worker's recovery."""

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="worker-failure-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def test_startup_failure_keeps_the_interpreters_diagnostic(self) -> None:
        from cad_server.engine.services import WORKER
        from cad_server.engine.supervisor import Gone, Process

        # A real interpreter startup failure, before worker.main can send ready or any client
        # has installed a log sink. The missing standard library used to be silently discarded.
        script = str(self.folder / "model.py")
        with self.assertRaises(Gone) as caught:
            Process.start(WORKER, script, script, {**os.environ, "PYTHONHOME": str(self.folder)})
        self.assertIn("did not start", str(caught.exception))
        self.assertIn("encodings", str(caught.exception))

    def test_local_tracebacks_are_not_observer_facts_without_an_exit_status(self) -> None:
        from cad.engine.api import EngineError, _error
        from cad_server.engine.daemon import WORKER_STDERR

        diagnostic = ('Traceback (most recent call last):\n'
                      '  File "/private/model.py", line 7, in secret_model\n'
                      'NameError: private model detail\n')
        for message in ("the worker did not start", "[Errno 32] Broken pipe"):
            with self.subTest(failure=message):
                original = _error(EngineError(message), [], {})
                self.assertEqual(_error(EngineError(message + WORKER_STDERR + diagnostic), [], {}), original)

    def test_where_a_build_was_is_said_before_the_stderr_tail(self) -> None:
        from types import SimpleNamespace

        from cad_server.engine.daemon import WORKER_STDERR, Daemon
        from cad_server.engine.supervisor import Gone

        error = Gone(f"the worker for m.py exited (-11) during the build{WORKER_STDERR}Fatal Python error")
        said = Daemon._where(error, SimpleNamespace(progress={"job": "m.py::m", "stage": "body"}))
        head, _, tail = said.partition(WORKER_STDERR)
        self.assertTrue(head.startswith("the worker for m.py exited (-11) during the build, at m.py::m: "), said)
        self.assertEqual(tail, "Fatal Python error")

    def test_a_build_whose_log_showed_the_stderr_says_it_once(self) -> None:
        from cad.engine import api
        from cad_server.engine.daemon import WORKER_STDERR

        failed = f"the worker for m.py exited (-11) during the build{WORKER_STDERR}Fatal Python error"

        def ask(_order, relay, _frames):
            relay({"log": "Fatal Python error", "stream": "model"})
            raise api.EngineError(failed)

        script = self.folder / "m.py"
        for log, kept in ((print, False), (None, True)):  # shown on the caller's log, or nowhere
            with self.subTest(log=log), mock.patch.object(api, "_ask", side_effect=ask), \
                    self.assertRaises(api.EngineError) as caught:
                api._built(script, None, log=log and (lambda _text: None), progress=False)
            self.assertEqual(WORKER_STDERR in str(caught.exception), kept)
            self.assertIn("exited (-11) during the build", str(caught.exception))

    def test_failed_worker_keeps_a_bounded_fault_stack_and_releases_its_slot(self) -> None:
        from cad_server.engine import daemon
        from cad_server.engine.services import WORKER
        from cad_server.engine.supervisor import Gone, Supervisor

        # Stand in for the kernel, leaving Process/Supervisor and their pipes real. dump_traceback
        # exercises the same stderr output as a native fault without crashing the CI machine.
        child = '''import faulthandler, json, os, sys
print(json.dumps({"ready": os.getpid()}), flush=True)
for line in sys.stdin:
    if json.loads(line)["op"] == "crash":
        sys.stderr.write("discard-this-prefix" + "x" * 20000 + "\\n")
        print("fault handler enabled:", faulthandler.is_enabled(), file=sys.stderr, flush=True)
        faulthandler.dump_traceback()
        os._exit(1)
    print(json.dumps({"done": []}), flush=True)
'''
        popen = subprocess.Popen

        def start(command, **kwargs):
            at = command.index("-m")
            return popen([*command[:at], "-c", child], **kwargs)

        with mock.patch.object(daemon.subprocess, "Popen", side_effect=start):
            pool = Supervisor(1, (WORKER,))
            script, environment = str(self.folder / "model.py"), dict(os.environ)
            worker = pool.lease("worker", script, environment)
            self.addCleanup(worker.stop)
            with self.assertRaises(Gone) as caught:
                worker.request({"op": "crash"}, lambda _frame: None)
            detail = str(caught.exception)
            self.assertIn("exited (1) during the build", detail)
            self.assertIn("fault handler enabled: True", detail)
            self.assertIn('File "<string>"', detail)
            self.assertNotIn("discard-this-prefix", detail)
            self.assertLess(len(detail), 17000)
            # The observer extracts only the exit status, never the local stderr diagnostics.
            from cad.engine.api import EngineError, _error

            facts = {}
            self.assertEqual(_error(EngineError(detail), [], facts)["frames"], [])
            self.assertEqual(facts, {"died": 1})
            pool.release(worker)
            replacement = pool.lease("worker", script, environment)
            self.addCleanup(replacement.stop)
            self.assertNotEqual(replacement.pid, worker.pid)
            self.assertEqual(replacement.request({"op": "ok"}, lambda _frame: None), {"done": []})
            pool.release(replacement)


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
                self.assertRegex(said.getvalue(), rf"^cad {verb}: the system denies text-to-cad's local engine "
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

    def test_an_engine_with_no_base_makes_it_at_its_start_and_stands_its_standby_once_made(self) -> None:
        # The plugin's server alone, as a host's CAD app installs it: the engine it starts, outside any sandbox,
        # makes the base at its start in the background (an agent's sandboxed command cannot), and its standby
        # stands once the base is made.
        import contextlib
        import dataclasses
        import io
        import threading

        from cad_server._internal import base
        from cad_server.engine import daemon

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

        engine = daemon.Daemon()
        self.addCleanup(engine.supervisor.stop)
        stood: list[bool] = []  # whether the base was there each time a standby was asked to stand
        with mock.patch.dict(os.environ, {"CAD_CACHE_DIR": str(scratch), "CAD_ENGINE_STANDBY": "1"}), \
                mock.patch.object(base, "MAKING", base.Making()), mock.patch.object(base, "make", side_effect=make) as made, \
                mock.patch.object(base.Installation, "here", return_value=core), contextlib.redirect_stderr(io.StringIO()), \
                mock.patch.object(engine.supervisor, "stand",
                                  side_effect=lambda _service, _env: stood.append(base.complete(base.where(core)) is not None)):
            engine.stand()
            self.assertEqual((engine.status()["base"]["state"], stood), ("making", [False]))
            go.set()
            deadline = time.monotonic() + 30
            while len(stood) < 2 and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual(engine.status()["base"]["state"], "made")
        made.assert_called_once()
        self.assertEqual(stood, [False, True], "none to stand in at the start; the standby once the base is made")

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

        from cad.engine import client, places

        state = tempfile.mkdtemp(prefix="no-installation-")
        self.addCleanup(shutil.rmtree, state, True)
        with mock.patch.dict(os.environ, {"CAD_STATE_DIR": state}), mock.patch.object(places, "HOME", None), \
                mock.patch.object(client.subprocess, "Popen", side_effect=AssertionError("a daemon was started")):
            with self.assertRaises(ConnectionError) as caught:
                client._start()
        self.assertEqual(str(caught.exception),
                         "cad-server is not installed on this computer: install cad-server and run `cad doctor` once, "
                         "then run this again")
        # A base an installation made (``cad run``'s) starts its installation's engine, current or not.
        base = {"executable": sys.executable, "prefix": sys.prefix, "root": str(Path(state, "server"))}
        with mock.patch.dict(os.environ, {"CAD_STATE_DIR": state}), mock.patch.object(places, "HOME", base), \
                mock.patch.object(client.subprocess, "Popen") as started:
            client._start()
        self.assertEqual(started.call_args.args[0][0], sys.executable)

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


class DaemonTest(unittest.TestCase):
    """Through the daemon. The class shares one engine, so a test's first build takes the standby the
    one before left, with the kernel loaded; each test builds scripts of a folder of its own, and
    reads the workers of its own scripts (``mine``). A test whose subject is the engine's start, its
    environment or all it holds starts an engine of its own (``own``)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.shared = cls.engine(cls.addClassCleanup)

    @classmethod
    def engine(cls, cleanup, **extra: str) -> tuple[Path, dict]:
        """An engine folder and its environment, the engine stopped and the folder removed at ``cleanup``."""
        state = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        cleanup(shutil.rmtree, state, True)
        env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CAD_ENGINE_DIR": str(state),
                                     "CAD_ENGINE_MESH": "inline", **extra}, cleanup)
        cleanup(cls.stopped, state, env)
        return state, env

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-daemon-")).resolve()
        # These are independent fixtures, not moved scripts: keep each original present while
        # the class's shared registry can match another fixture to it.
        self.addClassCleanup(shutil.rmtree, self.folder, True)
        self.state, self.env = self.shared
        self.script = self.folder / "block.py"

    def own(self, **extra: str) -> None:
        """An engine of the test's own from now on, started with ``extra`` in its environment."""
        self.state, self.env = self.engine(self.addCleanup, **extra)

    def mine(self, rows: list[dict]) -> list[dict]:
        """The rows of ``status``'s ``workers`` or ``retired`` that are this test's scripts' (a render
        process's retirement names a document)."""
        return [row for row in rows if "script" in row and Path(row["script"]).parent == self.folder]

    @staticmethod
    def stopped(state: Path, env: dict) -> None:
        engine_daemon.run([sys.executable, "-m", "cad_server.engine", "stop"], env=env)
        deadline = time.monotonic() + 20
        while any(state.glob("*.door")) and time.monotonic() < deadline:
            time.sleep(0.05)

    def _stop_daemon(self) -> None:
        self.stopped(self.state, self.env)

    def cli(self, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        return engine_daemon.run([sys.executable, "-m", "cad_server.engine", *args], cwd=self.folder, env=env or self.env)

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

    def test_inspection_never_builds_a_missing_or_edited_script_model(self):
        from cad.engine.ids import model_id

        # The registry alone, a cache folder nothing can write: a restart is refused with the command
        # (what the cache reopens is ``test_cache``'s).
        self.own(CAD_CACHE_DIR=engine_daemon.unwritable(self.folder))

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
        self.assertIn(f"block ({ident}) is not saved: the engine's cache holds no file of its last build; run "
                      "`cad run ", missing.stderr)
        self.assertFalse(marker.exists())
        inspected = self.cli("inspect", str(self.folder / "XBF/block.xbf"), "--query", "build")
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertIsNone(json.loads(inspected.stdout)["live"])

    def _bare(self) -> str:
        """``bracket.py``: one bare ``@model``, a document of memory alone, and its id."""
        from cad.engine.ids import model_id

        script = self.folder / "bracket.py"
        script.write_text(textwrap.dedent(BARE.format(size=1)), encoding="utf-8")
        return model_id(script, "bracket")

    def test_a_named_model_updates_one_address_and_after_a_restart_names_its_command(self) -> None:
        from urllib.parse import urlparse, parse_qs

        aside = Path(tempfile.mkdtemp(prefix="engine-daemon-cache-")).resolve()
        self.addCleanup(shutil.rmtree, aside, True)
        self.own(CAD_CACHE_DIR=engine_daemon.unwritable(aside))  # nothing kept: ``test_cache``'s

        address = self._bare()
        first = self.built("bracket")
        self.assertEqual(first["files"], {})
        self.assertEqual(first["id"], address)
        self.assertNotIn("address", first, "a report names its document by its id alone")
        url = urlparse(first["url"])
        doc = url.path.strip("/")
        endpoint = f"{url.scheme}://{url.netloc}/api/v1/documents/model/{doc}/structure"
        token = parse_qs(url.query)["token"][0]
        before = get_json(endpoint, token)
        (self.folder / "bracket.py").write_text(textwrap.dedent(BARE.format(size=2)), encoding="utf-8")
        second = self.built("bracket")
        self.assertEqual(urlparse(second["url"])[:3], url[:3], "one address, each URL with a fresh link")
        from cad.engine.ids import model_id

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
        self.assertIn(f"bracket ({address}) is not saved: the engine's cache holds no file of its last build; "
                      "run `cad run ", missing.stderr)
        self.assertEqual(json.loads(self.cli("status", "--json").stdout)["models"], [],
                         "a restart holds nothing: status lists what this server built")

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

    def test_a_script_is_never_a_source_and_an_id_is_read_as_held(self) -> None:
        """No verb imports, runs or builds a script: ``x.py`` and ``x.py::f`` are refused as any file
        that is no document is. An id is the document the engine holds: exported after the script
        changed, it writes the same bytes, and nothing runs."""
        from cad.engine.ids import model_id

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

        from cad.engine.ids import model_id

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
from cad import model, step, xbf
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
        (worker,) = [row["pid"] for row in self.mine(json.loads(self.cli("status", "--json").stdout)["workers"])]
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
        self.assertEqual([row["builds"] for row in self.mine(status["workers"])], [3])
        # The daemon's only files are its door, its lock and its clients' pipes; the build's, its outputs.
        # The daemon's socket (on Windows the port file standing in for it) and its lock, nothing else.
        self.assertEqual({path.suffix or path.name for path in self.state.iterdir()},
                         {".port", ".lock"} if os.name == "nt" else {".door", ".lock", "clients"})
        self.assertEqual(sorted(path.relative_to(self.folder).as_posix() for path in self.folder.rglob("*") if path.is_file()),
                         ["XBF/block.xbf", "block.py"])

    def test_a_caller_s_other_path_keeps_the_warm_worker_and_another_pythonpath_replaces_it(self) -> None:
        # Each load of the script in the worker says which caller's environment it runs in.
        seen = "import os\nif os.environ.get('CAD_ENGINE_WORKER'):\n" \
               "    open('seen.txt', 'a').write(os.environ.get('TURN', '') + ' ' + os.environ['PATH'] + '\\n')\n"
        self.script.write_text(seen + textwrap.dedent(MODEL.format(size=10)), encoding="utf-8")

        def pid() -> int:
            (found,) = self.mine(json.loads(self.cli("status", "--json").stdout)["workers"])
            return found["pid"]

        self.assertGreater(self.built("block", env={**self.env, "TURN": "1"})["memo"]["misses"], 0)
        first = pid()
        # An agent's next turn: its shell's PATH and its own variables are new; the run adopts them.
        turn = {**self.env, "TURN": "2", "PATH": os.pathsep.join([str(self.folder), self.env.get("PATH", "")])}
        warm = self.built("block", env=turn)
        self.assertEqual((warm["memo"]["misses"], warm["cache"]), (0, {"used": True, "from": "memory"}),
                         "taken from the warm worker's memory, as a restart never is")
        self.assertEqual(pid(), first)
        self.assertEqual(self.mine(json.loads(self.cli("status", "--json").stdout)["retired"]), [])
        self.assertEqual((self.folder / "seen.txt").read_text(encoding="utf-8").splitlines()[-1],
                         f"2 {turn['PATH']}", "the run adopted its caller's environment")
        # Another PYTHONPATH is another interpreter: its worker is replaced, and says why.
        other = {**self.env, "PYTHONPATH": os.pathsep.join([self.env["PYTHONPATH"], str(self.folder)])}
        self.built("block", env=other)
        self.assertNotEqual(pid(), first)
        retired = self.mine(json.loads(self.cli("status", "--json").stdout)["retired"])
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

    def where(self, ref: str, doc: str = "XBF/block.xbf") -> dict:
        found = engine_daemon.run([sys.executable, "-m", "cad_server.cli", "inspect", doc, ref], cwd=self.folder,
                                  env=self.env)
        self.assertEqual(found.returncode, 0, found.stderr)
        return json.loads(found.stdout)

    def test_an_element_answers_what_made_it_from_the_worker_that_built_it(self) -> None:
        ident = self.build(10)["id"]
        face = self.where("block/face 1", ident)
        made = face["made_by"]
        line = next(n for n, text in enumerate(self.script.read_text(encoding="utf-8").splitlines(), 1)
                    if "bd.fillet" in text)
        self.assertEqual((made["function"], made["file"], made["line"]), ("block", str(self.script), line))
        self.assertEqual(made["name"], face["name"])
        self.assertTrue(made["feature"].startswith("block.") and made["operation"])
        self.assertGreater(face["area"], 0)
        # By its element name, the same element.
        self.assertEqual(self.where(face["name"], ident)["ordinal"], 1)
        drop = ("made_by", "meshed")
        # The xbf the run wrote is a file: it names no model, so its element answers no ``made_by``,
        # the worker that wrote it live or not -- and every fact the kernel measures is the model's.
        declared = self.where("block/face 1")
        self.assertNotIn("made_by", declared)
        self.assertEqual({k: v for k, v in declared.items() if k not in drop},
                         {k: v for k, v in face.items() if k not in drop})
        # A daemon started again with no build serves the model from its cache cold: no worker
        # holds a trace of it, so ``made_by`` is null -- and every fact the kernel measures is
        # what it was. Nothing of the provenance was written anywhere.
        self._stop_daemon()
        cold = self.where("block/face 1", ident)
        self.assertIsNone(cold.pop("made_by"))
        self.assertEqual({k: v for k, v in cold.items() if k not in drop}, {k: v for k, v in face.items() if k not in drop})
        self.assertEqual(sorted(path.relative_to(self.folder).as_posix() for path in self.folder.rglob("*") if path.is_file()),
                         ["XBF/block.xbf", "block.py"])

    def test_a_worker_over_its_memory_cap_is_retired_and_the_next_build_restarts(self) -> None:
        self.own(CAD_ENGINE_WORKER_RSS_MB="1")  # the engine's cap, which each request carries to its worker
        self.script.write_text(textwrap.dedent(MODEL.format(size=10)), encoding="utf-8")
        report = self.built("block")
        self.assertIn("over its 1 MB cap", report["retired"])
        # The next build is a fresh worker's: a restart, which takes the file it wrote.
        again = self.run_script("block.py")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertTrue(again.stdout.startswith("took block.py::block cold"), again.stdout)
        self.assertIn("retired: the worker held", again.stdout)
        status = json.loads(self.cli("status", "--json").stdout)
        self.assertEqual(self.mine(status["workers"]), [], "each worker left the pool when it was retired")
        self.assertEqual([row["reason"] for row in self.mine(status["retired"])], ["RSS", "RSS"])

    def test_a_failing_body_answers_with_its_error(self) -> None:
        self.script.write_text("from cad.engine import xbf\n\n@xbf('XBF/block.xbf')\ndef block():\n    raise RuntimeError('no')\nif __name__ == '__main__':\n    block()\n", encoding="utf-8")
        done = self.run_script("block.py")
        self.assertEqual(done.returncode, 1)
        self.assertIn("RuntimeError: no", done.stderr)

    def test_a_rerun_behind_its_script_s_running_build_says_it_waits_and_takes_what_it_built(self) -> None:
        # A client its shell's time limit killed leaves its build running; the same command again
        # waits for that build, says so at once, and takes the document it made from its key.
        # Nothing is cancelled.
        from cad.engine import client

        gate = self.folder / "gate"
        (self.folder / "turbine.py").write_text(textwrap.dedent(f"""
            import os, time
            import build123d as bd
            from cad.engine import model


            @model
            def turbine():
                while not os.path.exists({str(gate)!r}):  # held until the test lets it go
                    time.sleep(0.01)
                return bd.Box(2, 2, 2) - bd.Cylinder(0.5, 3)

            if __name__ == "__main__":
                turbine()
            """), encoding="utf-8")

        def status() -> dict:
            with mock.patch.dict(os.environ, {"CAD_ENGINE_DIR": str(self.state)}):
                return client.request({"op": "status"}, start=False) or {}

        def until(condition) -> None:
            deadline = time.monotonic() + 60
            while not condition():
                self.assertLess(time.monotonic(), deadline, "the engine never got there")
                time.sleep(0.05)

        first = subprocess.Popen([sys.executable, "turbine.py"], cwd=self.folder, env=self.env,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        until(lambda: any(worker["busy"] for worker in status().get("workers", [])))
        first.kill()
        first.wait()
        second = subprocess.Popen([sys.executable, "turbine.py"], cwd=self.folder, env=self.env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        until(lambda: status().get("waiting") == 1)
        gate.touch()
        out, err = engine_daemon.communicate(second, self.env)
        self.assertEqual(second.returncode, 0, err)
        self.assertRegex(err, r"(?m)^waiting for the build of turbine\.py started \d+ s ago$")
        self.assertRegex(out, r"(?m)^took turbine\.py::turbine warm in .*nothing ran; "
                         r"took the build of turbine\.py it waited \d+s for$")

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

        from cad.engine.ids import model_id

        # Each model reports its id, the one the script's own process derives (ids.model_id), and
        # its page is that id's.
        expected = [model_id(self.script, "block"), model_id(self.script, "peg")]
        self.assertEqual([line.removeprefix("  id: ") for line in done.stdout.splitlines() if line.startswith("  id: ")],
                         expected)
        views = [line for line in done.stdout.splitlines() if line.startswith("  view: ")]
        self.assertEqual([urlparse(line.removeprefix("  view: ")).path.strip("/") for line in views], expected)
        workers = self.mine(json.loads(self.cli("status", "--json").stdout)["workers"])
        self.assertEqual([(Path(w["script"]).name, w["builds"]) for w in workers], [("block.py", 2)],
                         "the daemon's worker built it, not the script's own process")
        done = engine_daemon.run([sys.executable, "block.py", "--step", "b.step", "--json"], cwd=self.folder,
                                 env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(sorted(path.relative_to(self.folder).as_posix() for path in self.folder.rglob("*") if path.is_file()),
                         ["XBF/block.xbf", "block.py", "peg.stl"])

    def test_decoration_only_declares_and_main_calls_only_its_selected_model(self) -> None:
        self.own()  # no engine yet, so none an import started goes unseen
        self.script.write_text(textwrap.dedent("""
            from cad import model, xbf

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
