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

SRC = Path(__file__).resolve().parents[5] / "packages" / "cadgen" / "src"


def setUpModule():
    engine_daemon.isolate(unittest.addModuleCleanup, start=False)

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
        ready = self.next()
        self.assertIn("ready", ready)
        self.execution = ready["execution"]

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
                   "cwd": str(self.folder), "run": run, "execution": self.execution}
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


class KernelNoticeTest(unittest.TestCase):
    """A build on a worker whose kernel is not loaded loads it first, and a load that outlasts
    ``KERNEL_PATIENCE`` is said to the caller once while it goes on; a warm worker says nothing."""

    def test_a_slow_first_load_is_said_while_it_goes_on_and_a_loaded_kernel_says_nothing(self) -> None:
        import threading

        from cadgen.engine import worker

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
        # calls (cadgen.engine.profiling), and a cancelled timer waking inside it corrupted its rows.
        self.assertEqual([alive.is_alive() for alive in made], [False])


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
        import threading
        from types import SimpleNamespace

        from cadgen.engine.daemon import Worker

        worker = object.__new__(Worker)  # its pipes stood in for: no process
        worker.process = SimpleNamespace(stdout=io.BytesIO(stdout), stderr=io.BytesIO(stderr))
        worker.answers, worker.asked, worker.progress = queue.Queue(), {}, None
        worker.followers = []
        worker.stderr_tail, worker.stderr_lock = "", threading.Lock()
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
        self.assertTrue(worker.process.stdout.closed, "the reader closes its pipe at EOF")

    def test_its_stderr_is_read_to_the_end_when_its_client_is_gone(self) -> None:
        worker = self.worker(b"", b"a line the model printed\nanother\n")
        worker._stderr()
        self.assertIsNone(worker.sink)
        self.assertTrue(worker.process.stderr.closed, "the reader closes its pipe at EOF")


def _launched(command: list[str]) -> int:
    """Where a worker's command names the worker, in either launch form (``daemon.Worker``): an
    installed cadgen's ``-m cadgen.engine.worker``, or a source checkout's ``-c`` line that runs
    ``cadgen.engine.worker`` from the import root after it. A fake worker's ``-c`` goes there."""
    if "-m" in command:
        return command.index("-m")
    at = command.index("-c")
    assert "cadgen.engine.worker" in command[at + 1], command
    return at


class WorkerFailureTest(unittest.TestCase):
    """Real subprocess pipes: startup diagnostics, fault output and the next worker's recovery."""

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="worker-failure-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def test_startup_failure_keeps_the_interpreters_diagnostic(self) -> None:
        from cadgen.engine.daemon import Worker, WorkerGone

        # A real interpreter startup failure, before worker.main can send ready or any client
        # has installed a log sink. The missing standard library used to be silently discarded.
        with self.assertRaises(WorkerGone) as caught:
            Worker(str(self.folder / "model.py"), {**os.environ, "PYTHONHOME": str(self.folder)})
        self.assertIn("did not start", str(caught.exception))
        self.assertIn("encodings", str(caught.exception))

    def test_local_tracebacks_are_not_observer_facts_without_an_exit_status(self) -> None:
        from cadgen.engine.api import EngineError, _error
        from cadgen.engine.daemon import WORKER_STDERR

        diagnostic = ('Traceback (most recent call last):\n'
                      '  File "/private/model.py", line 7, in secret_model\n'
                      'NameError: private model detail\n')
        for message in ("the worker did not start", "[Errno 32] Broken pipe"):
            with self.subTest(failure=message):
                original = _error(EngineError(message), [], {})
                self.assertEqual(_error(EngineError(message + WORKER_STDERR + diagnostic), [], {}), original)

    def test_where_a_build_was_is_said_before_the_stderr_tail(self) -> None:
        from types import SimpleNamespace

        from cadgen.engine.daemon import WORKER_STDERR, Daemon, WorkerGone

        error = WorkerGone(f"the worker for m.py exited (-11) during the build{WORKER_STDERR}Fatal Python error")
        said = Daemon._where(error, SimpleNamespace(progress={"job": "m.py::m", "stage": "body"}))
        head, _, tail = said.partition(WORKER_STDERR)
        self.assertTrue(head.startswith("the worker for m.py exited (-11) during the build, at m.py::m: "), said)
        self.assertEqual(tail, "Fatal Python error")

    def test_a_build_whose_log_showed_the_stderr_says_it_once(self) -> None:
        from cadgen.engine import api
        from cadgen.engine.daemon import WORKER_STDERR

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
        from cadgen.engine import daemon

        # Stand in for the kernel, leaving Worker/Pool and their pipes real. dump_traceback
        # exercises the same stderr output as a native fault without crashing the CI machine.
        # The child says the execution it runs in, as a worker does (``runtime.describe``): the engine
        # takes no worker whose Python is not the one asked for.
        child = '''import faulthandler, json, os, sys
from cadgen.engine import runtime
print(json.dumps({"ready": os.getpid(), "execution": runtime.describe()}), flush=True)
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
            return popen([*command[:_launched(command)], "-c", child], **kwargs)

        with mock.patch.object(daemon.subprocess, "Popen", side_effect=start):
            pool = daemon.Pool(cap=1, start=daemon.Worker)
            script, environment = str(self.folder / "model.py"), dict(os.environ)
            worker = pool.lease(script, environment)
            self.addCleanup(worker.stop)
            with self.assertRaises(daemon.WorkerGone) as caught:
                worker.build({"op": "crash"}, lambda _frame: None)
            detail = str(caught.exception)
            self.assertIn("exited (1) during the build", detail)
            self.assertIn("fault handler enabled: True", detail)
            self.assertIn('File "<string>"', detail)
            self.assertNotIn("discard-this-prefix", detail)
            self.assertLess(len(detail), 17000)
            # The observer extracts only the exit status, never the local stderr diagnostics.
            from cadgen.engine.api import EngineError, _error

            facts = {}
            self.assertEqual(_error(EngineError(detail), [], facts)["frames"], [])
            self.assertEqual(facts, {"died": 1})
            pool.release(worker)
            replacement = pool.lease(script, environment)
            self.addCleanup(replacement.stop)
            self.assertNotEqual(replacement.pid, worker.pid)
            self.assertEqual(replacement.build({"op": "ok"}, lambda _frame: None), {"done": []})
            pool.release(replacement)


class NudgeTest(unittest.TestCase):
    """A project of another cadgen release that meets the engine (protocol, format, native line) is
    served, and told once, at its worker's first build (``runtime.nudge``): never a refusal, and never
    again for the worker's life."""

    def worker(self, release: str):
        from cadgen.engine import daemon, runtime

        child = '''import json, os, sys
print(json.dumps({"ready": os.getpid(), "execution": json.loads(os.environ["CADGEN_TEST_EXECUTION"])}), flush=True)
for line in sys.stdin:
    print(json.dumps({"done": []}), flush=True)
'''
        execution = {**runtime.describe(), "release": release}  # the project's cadgen, as its worker says it
        execution["fingerprint"] = runtime.digest({key: value for key, value in execution.items() if key != "fingerprint"})
        popen = subprocess.Popen

        def start(command, **kwargs):
            return popen([*command[:_launched(command)], "-c", child], **kwargs)

        environment = {**os.environ, "CADGEN_TEST_EXECUTION": json.dumps(execution)}
        with mock.patch.object(daemon.subprocess, "Popen", side_effect=start):
            worker = daemon.Worker(str(Path(tempfile.gettempdir()) / "model.py"), environment, execution=execution)
        self.addCleanup(worker.stop)
        return worker

    @staticmethod
    def told(worker) -> list[str]:
        said: list[dict] = []
        worker.build({"id": 1, "op": "build"}, said.append)
        return [message["log"] for message in said if message.get("stream") == "notice"]

    def test_an_older_project_is_told_once_to_update_cadgen_in_its_environment(self) -> None:
        from cadgen.engine.previous import version

        worker = self.worker("0.0.1")
        self.assertEqual(self.told(worker), [f"project cadgen 0.0.1 is older than the engine's {version()}: uv pip "
                                             "install -U cadgen in the project environment"])
        self.assertEqual(self.told(worker), [], "once a worker's life, never at its next build")

    def test_a_newer_project_is_told_to_update_the_engine_and_one_of_its_release_nothing(self) -> None:
        from cadgen.engine import runtime
        from cadgen.engine.previous import version

        self.assertEqual(self.told(self.worker("99.0.0")), [f"the engine runs cadgen {version()}, this project 99.0.0: "
                                                            f"run `{runtime.INSTALL}` to update the engine"])
        self.assertEqual(self.told(self.worker(version())), [])


class ConnectTest(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "a door is a POSIX daemon's")
    def test_a_door_nobody_reads_is_no_engine_and_leaves_no_pipe_or_file_open(self) -> None:
        import gc
        import warnings
        from unittest import mock

        from cadgen.engine import client

        engine = tempfile.mkdtemp(prefix="eng-")
        self.addCleanup(shutil.rmtree, engine, True)
        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": engine}):
            door = client._daemon.door_path()
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
        patched = mock.patch.dict(os.environ, {**cleared, "CADGEN_ENGINE_DIR": self.engine}, clear=True)
        patched.start()
        self.addCleanup(patched.stop)

    def test_no_engine_in_a_sandbox_without_network_is_said_in_one_line_and_starts_none(self) -> None:
        from unittest import mock

        from cadgen.engine import client

        self.assertIn(("CODEX_SANDBOX_NETWORK_DISABLED", "1"), client.SANDBOXES, "cadgen's host adapter names it")
        with mock.patch.dict(os.environ, {"CODEX_SANDBOX": "seatbelt", "CODEX_SANDBOX_NETWORK_DISABLED": "1"}), \
                mock.patch.object(client, "_start", side_effect=AssertionError("a daemon was started")):
            with self.assertRaises(ConnectionError) as said:
                client.connect(start=True)
        self.assertEqual(str(said.exception), client.SANDBOXED)
        self.assertNotIn("\n", client.SANDBOXED)

    def test_a_daemon_that_cannot_listen_leaves_its_reason_and_the_client_says_it_at_once(self) -> None:
        import errno
        from unittest import mock

        from cadgen.engine import client, daemon

        bytecode = sys.dont_write_bytecode
        self.addCleanup(setattr, sys, "dont_write_bytecode", bytecode)
        with mock.patch.object(daemon, "_can_listen", side_effect=PermissionError(errno.EPERM, "Operation not permitted")), \
                mock.patch.object(daemon, "_bind", side_effect=PermissionError(errno.EPERM, "Operation not permitted")), \
                mock.patch("sys.stderr"):
            self.assertEqual(daemon.main(), 1)
        note = json.loads(daemon.failure_path().read_text(encoding="utf-8"))
        self.assertTrue(note["denied"])
        held = daemon.lock()
        self.assertIsNotNone(held, "its lock was let go")
        held.close()

        class Exited:  # the daemon as the client sees it: gone, failing, its note left
            returncode = 1

            def __init__(self, written: dict) -> None:
                daemon.failure_path().write_text(json.dumps(written), encoding="utf-8")

            def poll(self) -> int:
                return 1

        with mock.patch.object(client, "_start", lambda: Exited(note)):
            with self.assertRaisesRegex(ConnectionError, "^" + re.escape(client.SANDBOXED)
                                        + r" \(the engine server cannot listen on a local port: Operation not permitted\)$"):
                client.connect(start=True, timeout=30)
        with mock.patch.object(client, "_start", lambda: Exited({"reason": "it broke", "denied": False})):
            with self.assertRaisesRegex(ConnectionError, r"^the engine server did not start: it broke$"):
                client.connect(start=True, timeout=30)


class EngineFolderTest(unittest.TestCase):
    """The engine's folder holds its door, lock and port file. One another user owns, or that
    others can write to, would let them take the door's place: client and daemon refuse it."""

    def setUp(self) -> None:
        self.engine = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None))
        self.addCleanup(shutil.rmtree, self.engine, True)

    @unittest.skipIf(os.name == "nt", "a folder's owner and mode are POSIX's")
    def test_a_folder_others_can_write_or_another_user_owns_is_refused_by_client_and_daemon(self) -> None:
        from unittest import mock

        from cadgen.engine import client, daemon

        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": str(self.engine)}):
            self.assertIsNone(daemon.folder_refusal(daemon.state_dir()))
            os.chmod(self.engine, 0o777)
            refusal = daemon.folder_refusal(daemon.state_dir())
            self.assertIn("can be written by others", refusal)
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
                with self.assertRaisesRegex(PermissionError, "belongs to another user"):
                    daemon.lock()

    @unittest.skipIf(os.name == "nt" or os.geteuid() == 0, "a folder's mode binds a POSIX user who is not root")
    def test_a_folder_the_system_denies_is_one_line_from_status_and_stop(self) -> None:
        import io
        from unittest import mock

        from cadgen.engine import cli, daemon

        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": str(self.engine)}):
            os.mkfifo(daemon.door_path(), 0o600)  # a dead daemon's door: status sweeps it, taking the lock
            os.chmod(self.engine, 0o500)
            self.addCleanup(os.chmod, self.engine, 0o700)
            for verb in ("status", "stop"):
                with mock.patch("sys.stderr", new_callable=io.StringIO) as said, mock.patch("sys.stdout"):
                    self.assertEqual(cli.run(verb, []), 1)
                self.assertRegex(said.getvalue(), rf"^cadgen {verb}: the system denies cadgen's local engine "
                                 r"\(taking the lock in the engine's folder .+: Permission denied\); .+ "
                                 r"run this command outside it, or with the sandbox's permission\n$")


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

    @unittest.skipUnless(sys.platform == "darwin", "macOS names its per-user temporary folder")
    def test_macos_keeps_the_system_folder_when_a_sandbox_sets_its_own_tmpdir(self) -> None:
        from cadgen.engine import daemon

        self.system = daemon._darwin_temp()
        self.assertEqual(self.folder(TMPDIR=str(self.private("sandbox"))),
                         Path(os.path.realpath(os.path.join(self.system, "cadgen-engine"))))

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
        from cadgen.engine.previous import version
        engine = types.SimpleNamespace(token="ab" * 16, refusal=None, unsaid="", release_version=version(),
                                       port=daemon.selected_port(), instance="test-instance",
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
        return handled, engine.token

    def test_a_connection_without_the_token_first_is_refused_before_its_line_is_read(self) -> None:
        handled, _token = self.serve(b'{"token": "' + b"0" * 32 + b'", "op": "status", "pad": "' + b"x" * 200_000)
        self.assertEqual(handled, [])

    def test_a_port_file_being_renamed_into_place_is_read_once_it_is_there(self) -> None:
        # Windows refuses a reader while the starting engine renames its port file into place; a
        # client polling for it then is not refused by the system, and one refused throughout is.
        from unittest import mock

        from cadgen.engine import client

        port_file = Path(tempfile.mkdtemp(prefix="eng-port-")) / "x.port"
        self.addCleanup(shutil.rmtree, port_file.parent, True)
        refused = PermissionError(13, "Permission denied")
        with mock.patch.object(client.time, "sleep"), \
                mock.patch.object(Path, "read_text", side_effect=[refused, refused, "1234 ab\n"]):
            self.assertEqual(client._port_text(port_file), "1234 ab\n")
        with mock.patch.object(client.time, "sleep"), mock.patch.object(Path, "read_text", side_effect=refused), \
                mock.patch.object(client._daemon, "WINDOWS", True), self.assertRaisesRegex(ConnectionError, "denies"):
            client._connect(port_file)

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
                hello = json.loads(sent[-1])
                identity = {key: hello[key] for key in ("protocol", "release", "port", "writes", "reads", "native")}
                identity["instance"] = "test-instance"
                stream.write((json.dumps({"ok": True, **identity}) + "\n").encode())
                stream.flush()
                sent.append(stream.readline())
                stream.write(b'{"ok": true}\n')
                stream.flush()

        answering = threading.Thread(target=engine)
        answering.start()
        with mock.patch.object(client._daemon, "WINDOWS", True):
            stream = ours.makefile("rwb")
            connection = client.Connection(stream, stream, stream, ours)
            self.assertEqual(client._exchange(connection, {"op": "status"}, address=port_file), {"ok": True})
        answering.join(timeout=30)
        self.assertTrue(sent[0].startswith(b'{"token": "' + token.encode() + b'", "op": "hello"'))
        self.assertTrue(sent[1].startswith(b'{"token": "' + token.encode() + b'", "op": "status"'))
        handled, _token = self.serve(b''.join(sent))
        self.assertEqual(handled, [json.loads(sent[1])])


class NoTimerTest(unittest.TestCase):
    """The engine never stops on a timer, nor retires a worker on one: memory alone does, and only
    ``stop`` stops it."""

    def test_a_day_idle_unheld_keeps_the_idle_worker_and_only_stop_stops_the_engine(self) -> None:
        import types
        from unittest import mock

        from cadgen.engine import daemon

        engine = daemon.Daemon(cap=1)
        stopped: list[str] = []
        worker = types.SimpleNamespace(key="/w/block.py", script="/w/block.py", pid=1, leased=False, rss=100.0,
                                       used=time.monotonic(), alive=lambda: True, stop=lambda: stopped.append("worker"))
        engine.pool.live[worker.key] = worker
        with mock.patch("time.monotonic", return_value=worker.used + 24 * 3600):
            engine.tend()  # no holder, nothing to do, a day on
        self.assertEqual((stopped, list(engine.pool.live)), ([], [worker.key]), "its idle worker stays")
        self.assertFalse(engine.stopping.is_set(), "the engine stays")
        sent: list[dict] = []
        engine.handle({"op": "stop"}, sent.append)
        self.assertEqual(sent, [{"ok": True}])
        self.assertTrue(engine.stopping.is_set())

    def test_an_engine_whose_door_is_gone_stops_and_one_whose_door_stands_stays(self) -> None:
        from cadgen.engine import daemon

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
    """What another installation's engine asks before it retires this one (``status``): a request that
    serves, binding the HTTP server, is in use until it is answered."""

    def test_a_launch_binding_its_server_is_busy_until_it_is_answered(self) -> None:
        import threading

        from cadgen.engine import daemon

        engine = daemon.Daemon(cap=1)
        self.addCleanup(engine.pool.stop)
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

        from cadgen.engine import daemon

        engine = daemon.Daemon()
        self.addCleanup(engine.pool.stop)
        asked: list[dict] = []
        root = daemon.engine_root()
        with mock.patch.object(engine.pool, "stand", side_effect=asked.append), \
                mock.patch.dict(os.environ, {"PYTHONPATH": os.pathsep.join((root, "/mine")),
                                             "CADGEN_ENGINE_STANDBY": "1"}):
            engine.stand()
        self.assertEqual(engine.pool.spare, engine._spare)
        self.assertEqual(len(asked), 1)
        self.assertEqual(asked[0]["PYTHONPATH"], "/mine", "without the engine's folder its starter put first")

    def test_with_the_switch_off_none_stands_by_and_none_replaces_one(self) -> None:
        from unittest import mock

        from cadgen.engine import daemon

        engine = daemon.Daemon()
        self.addCleanup(engine.pool.stop)
        with mock.patch.object(engine.pool, "stand") as stand, \
                mock.patch.dict(os.environ, {"CADGEN_ENGINE_STANDBY": "0"}):
            engine.stand()
        stand.assert_not_called()
        self.assertIsNone(engine.pool.spare, "no standby to start after an adoption or a fresh worker either")


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
            pid = 0

            def __init__(self, _argv, **kwargs):
                captured.update(kwargs.get("env") or {})

        with mock.patch.dict(os.environ, {"DO_NOT_TRACK": "1", "CADGEN_TELEMETRY": "1", "PATH": os.environ.get("PATH", "")}), \
                mock.patch.object(client.subprocess, "Popen", FakePopen):
            client._start()
        self.assertNotIn("DO_NOT_TRACK", captured)
        self.assertNotIn("CADGEN_TELEMETRY", captured)

    def test_the_daemon_and_its_workers_cache_bytecode_in_the_engine_s_folder_alone(self) -> None:
        from cadgen.engine import client, daemon, registry

        cache = Path(tempfile.mkdtemp(prefix="engine-bytecode-")).resolve()
        self.addCleanup(shutil.rmtree, cache, True)

        def started(given: dict[str, str]) -> dict[str, dict[str, str]]:
            """The environment a daemon is started with from a caller's ``given``, and the one that
            daemon starts a worker with for a run in ``given``."""
            found: dict[str, dict] = {}

            class Captured(Exception):
                pass

            def popen(argv, **kwargs):
                found["worker" if any("cadgen.engine.worker" in item for item in argv) else "daemon"] = kwargs["env"]
                raise Captured

            with mock.patch.object(subprocess, "Popen", popen):
                with mock.patch.dict(os.environ, given):
                    if "PYTHONPYCACHEPREFIX" not in given:
                        os.environ.pop("PYTHONPYCACHEPREFIX", None)
                    with self.assertRaises(Captured):
                        client._start()
                with mock.patch.dict(os.environ, found["daemon"], clear=True), self.assertRaises(Captured):
                    daemon.Worker(str(cache / "model.py"), dict(given))  # in the daemon, for a run in ``given``
            return found

        ours = str(cache / daemon.PYCACHE / daemon._tag())
        found = started({"CADGEN_CACHE_DIR": str(cache), "PYTHONDONTWRITEBYTECODE": "1"})
        for process in ("daemon", "worker"):
            self.assertEqual(found[process].get("PYTHONPYCACHEPREFIX"), ours, process)
            self.assertNotIn("PYTHONDONTWRITEBYTECODE", found[process], f"a caller's switch is not the {process}'s")
        if os.name != "nt":  # a folder's mode bits are POSIX's; Windows' per-user temporary folder is the user's
            self.assertEqual(stat.S_IMODE(os.stat(ours).st_mode) & 0o077, 0, "this user's alone")
        given = started({"CADGEN_CACHE_DIR": str(cache), "PYTHONPYCACHEPREFIX": str(cache / "theirs")})
        self.assertEqual(given["daemon"]["PYTHONPYCACHEPREFIX"], str(cache / "theirs"), "a prefix given is honoured")
        with mock.patch.object(registry, "FACTORY", None):  # no distribution names a cache folder: nothing written
            bare = started({"PYTHONDONTWRITEBYTECODE": ""})
        self.assertEqual((bare["daemon"].get("PYTHONDONTWRITEBYTECODE"), bare["daemon"].get("PYTHONPYCACHEPREFIX")), ("1", None))
        if os.name != "nt":
            os.chmod(ours, 0o777)
            self.assertEqual(started({"CADGEN_CACHE_DIR": str(cache)})["daemon"].get("PYTHONDONTWRITEBYTECODE"), "1",
                             "a folder others can write to is none of the engine's")


class SweepTest(unittest.TestCase):
    """``cadgen stop`` reaches every server of the installation, whatever protocol it speaks, and
    ``stop`` and ``status`` take away the files of a dead one."""

    def setUp(self) -> None:
        self.state = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        self.addCleanup(shutil.rmtree, self.state, True)
        self.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CADGEN_ENGINE_DIR": str(self.state)},
                                         self.addCleanup)

    def cli(self, *args: str) -> subprocess.CompletedProcess:
        return engine_daemon.run([sys.executable, "-m", "cadgen.engine", *args], env=self.env)

    @unittest.skipIf(os.name == "nt", "a door is a POSIX daemon's")
    def test_a_dead_server_s_door_and_lock_are_removed_and_said(self) -> None:
        from unittest import mock

        from cadgen.engine import daemon

        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": str(self.state)}):
            path, lock = daemon.door_path(), daemon.lock_path()
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

    def test_status_and_inspection_start_nothing_and_explicit_bootstrap_can_be_stopped(self) -> None:
        self.env.update(CADGEN_STATE_DIR=str(self.state / "state"), CADGEN_CACHE_DIR=str(self.state / "cache"))
        done = self.cli("status")
        self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "no engine server is running\n", ""))
        unknown = "00000000-0000-5000-8000-000000000000"
        missing = self.cli("inspect", unknown)
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("no cadgen server", missing.stderr)
        self.assertEqual(list(self.state.iterdir()), [], "ordinary commands started nothing")
        engine_daemon.bootstrap(self.env)
        self.assertEqual(self.cli("stop").returncode, 0)
        done = self.cli("status")
        self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "no engine server is running\n", ""))

    def test_an_incompatible_server_is_refused_by_name_and_stopped_only_by_stop(self) -> None:
        from cadgen.engine import client, daemon, runtime

        older = daemon.PROTOCOL - 1
        self.env.update(CADGEN_STATE_DIR=str(self.state / "state"), CADGEN_CACHE_DIR=str(self.state / "cache"))
        server = subprocess.Popen([sys.executable, "-c", "import sys; from cadgen.engine import daemon; "
                                   f"daemon.PROTOCOL = {older}; sys.exit(daemon.main())"], env=self.env,
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(engine_daemon.reap, server)
        with mock.patch.dict(os.environ, self.env, clear=True):
            deadline = time.monotonic() + 60
            while (found := client._connect()) is None:
                self.assertIsNone(server.poll(), "the server exited before it listened")
                self.assertLess(time.monotonic(), deadline, "the server listened")
                time.sleep(0.05)
            found.close()
            said = (f"cadgen client speaks protocol {daemon.PROTOCOL}, the engine on port {daemon.selected_port()} "
                    f"protocol {older}: update the older one (run `{runtime.INSTALL}` for the engine; "
                    "`uv pip install -U cadgen` in the project)")
            with self.assertRaises(client.Incompatible) as refused:
                client.request({"op": "status"}, start=False)
            self.assertEqual(str(refused.exception), said)
            with mock.patch.object(client, "_start") as start, self.assertRaises(client.Incompatible):
                client.connect(start=True)  # its release is this one's: a start never retires it
            start.assert_not_called()
            self.assertIsNone(server.poll(), "an incompatible server is never stopped implicitly")
        done = self.cli("stop")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("stopped the engine server at", done.stdout, "an explicit stop stops any release's")
        self.assertEqual(server.wait(60), 0)


class OlderEngine:
    """An older release's engine as this cadgen meets it (0.8.1's protocol 3): a door named by its
    installation (``tag``), one request a connection with no handshake, its lock held, and its HTTP
    server listening on ``port``. It answers ``status`` -- with what uses it (``uses``: its holders,
    watched pages, builds and HTTP work, none by default) -- and, when it ``stops``, ``stop``: it
    answers, then takes its door, its listener and its lock away, as 0.8.1's engine does."""

    def __init__(self, folder: Path, tag: str, port: int, *, stops: bool = True, uses: dict | None = None) -> None:
        import fcntl
        import socket
        import threading

        from cadgen.engine import door

        self.port, self.stops, self.requests = port, stops, []
        # What its status says uses it, as 0.8.1's says it: holds, watched pages, builds, HTTP work.
        self.uses = {"holders": 0, "watched": 0, "busy": 0, "active": False, **(uses or {})}
        self.address, self.lock = folder / f"{tag}.door", folder / f"{tag}.lock"
        self.gone = threading.Event()
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", port))
        self.listener.listen()
        self.held = open(self.lock, "a+")
        fcntl.flock(self.held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.door = door.Door(self.address, lambda ident: door.answer(folder / door.CLIENTS, ident, self.serve))

    def serve(self, reader, writer) -> None:
        import threading

        request = json.loads(reader.readline())
        self.requests.append(request)
        if request.get("op") == "status":
            answer = {"ok": True, "version": "0.8.1", "installation": "0.8.1", "pid": 4242, "token": "SECRET",
                      "serving": {"port": self.port, "url": f"http://127.0.0.1:{self.port}"}, "models": ["SECRET"],
                      **self.uses}
        elif request.get("op") == "stop" and self.stops:
            answer = {"ok": True}
        else:
            answer = {"failed": f"unknown request {request.get('op')!r}"}
        writer.write((json.dumps(answer) + "\n").encode())
        writer.flush()
        if answer == {"ok": True}:
            threading.Thread(target=self.close).start()

    def close(self) -> None:
        if self.gone.is_set():
            return
        self.door.close()
        self.listener.close()
        self.lock.unlink(missing_ok=True)  # removed while still held, as ``daemon.let_go`` does
        self.held.close()
        self.gone.set()


class HeldPort:
    """A selected port and an engine folder of the test's own, with no engine of this release on
    it, and ``cadgen`` verbs run in this process (``cli``)."""

    def setUp(self) -> None:
        self.engine = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        self.addCleanup(shutil.rmtree, self.engine, True)
        self.port = engine_daemon.free_port()
        patch = mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": str(self.engine), "CADGEN_PORT": str(self.port)})
        patch.start()
        self.addCleanup(patch.stop)

    def cli(self, *argv: str) -> tuple[int, str, str]:
        import io
        from contextlib import redirect_stderr, redirect_stdout

        from cadgen.engine import cli

        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.run(argv[0], list(argv[1:]))
        return code, out.getvalue(), err.getvalue()

    def listen(self) -> None:
        """Something listening on the selected port."""
        import socket

        listener = socket.socket()
        self.addCleanup(listener.close)
        listener.bind(("127.0.0.1", self.port))
        listener.listen()


@unittest.skipIf(os.name == "nt", "an older engine's door is a POSIX engine's")
class OlderEngineTest(HeldPort, unittest.TestCase):
    """A 0.8.1 engine still running on the selected port: its door is named by its installation, so
    no door of this protocol answers there. ``status`` names it, ``stop`` stops it through its own
    door and touches no engine on another port, and the held port is said by name to ``cadgen
    server``, the MCP bootstrap and every client."""

    def older(self, tag: str, port: int, **options) -> OlderEngine:
        engine = OlderEngine(self.engine, tag, port, **options)
        self.addCleanup(engine.close)
        return engine

    def test_status_names_it_and_stop_stops_it_alone_through_its_own_door(self) -> None:
        from cadgen.engine import door

        here = self.older("111111111111", self.port)
        elsewhere = self.older("0000000000aa", engine_daemon.free_port())  # asked first: its port is another
        code, out, err = self.cli("status")
        self.assertEqual((code, out, err), (1, "", f"cadgen status: cadgen 0.8.1's engine (pid 4242) serves port "
                                                   f"{self.port} with an older protocol: stop it with "
                                                   f"`cadgen stop --port {self.port}`\n"))
        code, out, err = self.cli("status", "--json")
        self.assertEqual((code, err), (1, ""))
        self.assertEqual(json.loads(out)["holder"], {"kind": "engine", "port": self.port, "release": "0.8.1",
                                                     "installation": "0.8.1", "pid": 4242, "address": str(here.address)})
        self.assertNotIn("SECRET", out, "only what the engine says of itself")
        code, out, err = self.cli("stop")
        self.assertEqual((code, out, err), (0, f"stopped cadgen 0.8.1's engine (pid 4242) on port {self.port}\n", ""))
        self.assertFalse(door.answering(here.address), "waited for until it was gone")
        self.assertFalse(here.lock.exists(), "and what its stop left of its files removed")
        self.assertTrue(here.gone.wait(10))
        self.assertTrue(door.answering(elsewhere.address), "an engine on another port is never touched")
        self.assertEqual({request["op"] for request in elsewhere.requests}, {"status"})
        self.assertEqual(self.cli("status"), (0, "no engine server is running\n", ""))
        self.assertEqual(self.cli("stop"), (0, "no engine server is running\n", ""))

    def test_one_that_refuses_the_stop_is_named_with_the_command_of_its_own_release(self) -> None:
        here = self.older("111111111111", self.port, stops=False)
        code, out, err = self.cli("stop")
        self.assertEqual((code, out), (1, ""))
        self.assertEqual(err, f"cadgen stop: cadgen 0.8.1's engine (pid 4242) serves port {self.port} with an older "
                              "protocol and did not take the stop request: stop it with `cadgen +0.8.1 stop`\n")
        self.assertFalse(here.gone.is_set())
        self.assertEqual([request["op"] for request in here.requests], ["status", "stop"])

    def test_the_port_it_holds_is_said_by_name_to_every_client_and_to_a_server_while_in_use(self) -> None:
        from cadgen.engine import client, daemon

        here = self.older("111111111111", self.port, uses={"holders": 1})
        said = (f"port {self.port} is held by cadgen 0.8.1's engine (pid 4242): run `cadgen stop --port {self.port}` "
                "to stop it, then start again")
        self.assertEqual(str(client.missing()), said)
        with self.assertRaisesRegex(ConnectionError, f"^{re.escape(said)}$"):
            client.request({"op": "status"})
        engine = daemon.Daemon(port=self.port)
        self.addCleanup(engine.pool.stop)
        with mock.patch.object(daemon, "HTTP_FACTORY", None), mock.patch.object(client, "RETIRE_SECONDS", 0), \
                self.assertRaises(daemon.PortHeld) as held:
            engine.serve({})
        self.assertEqual((str(held.exception), held.exception.who), (
            f"port {self.port} is held by cadgen 0.8.1's engine (pid 4242), still in use by 1 app server: quit that app "
            f"or run `cadgen stop --port {self.port}`", "cadgen 0.8.1's engine (pid 4242)"))
        self.assertNotIn("stop", [request["op"] for request in here.requests], "an engine in use is never displaced")

    def test_a_start_retires_it_once_idle_and_never_while_in_use(self) -> None:
        import io
        from contextlib import redirect_stderr

        from cadgen.engine import client, daemon

        here = self.older("111111111111", self.port, uses={"holders": 1, "watched": 2, "busy": 1})
        with self.assertRaises(client.InUse) as busy:
            client.retire_older(wait=0)
        self.assertEqual(str(busy.exception), (
            f"port {self.port} is held by cadgen 0.8.1's engine (pid 4242), still in use by 1 app server and 2 open pages "
            f"and 1 request: quit that app or run `cadgen stop --port {self.port}`"))
        self.assertEqual({request["op"] for request in here.requests}, {"status"})
        here.uses.update(holders=0, watched=0, busy=0)
        engine = daemon.Daemon(port=self.port)
        self.addCleanup(engine.pool.stop)
        err = io.StringIO()
        with mock.patch.object(daemon, "HTTP_FACTORY", None), redirect_stderr(err):
            server = engine.serve({})  # the server's bind retires it, and takes the port
        self.addCleanup(server.stop)
        self.assertEqual(server.port, self.port)
        self.assertTrue(here.gone.wait(10), "stopped through its own door")
        self.assertEqual(err.getvalue(), f"cadgen: retired cadgen 0.8.1's engine (pid 4242) for {daemon.installation()}\n")
        self.assertIsNone(client.retire_older(), "nothing older serves the port")

    def test_retire_older_returns_its_identity_once_and_names_one_that_refuses(self) -> None:
        from cadgen.engine import client

        here = self.older("111111111111", self.port)
        self.assertEqual(client.retire_older(), {"release": "0.8.1", "pid": 4242, "port": self.port})
        self.assertTrue(here.gone.wait(10))
        self.assertFalse(here.lock.exists(), "what its stop left of its files removed")
        self.assertIsNone(client.retire_older())
        stubborn = self.older("222222222222", self.port, stops=False)  # the port it let go
        with self.assertRaises(ConnectionError) as refused:
            client.retire_older()
        self.assertEqual(str(refused.exception), f"port {self.port} is held by cadgen 0.8.1's engine (pid 4242), which did "
                                                 "not take the stop request: stop it with `cadgen +0.8.1 stop`")
        self.assertFalse(stubborn.gone.is_set())


class OtherListenerTest(HeldPort, unittest.TestCase):
    """Anything else on the selected port is named to ``status`` and to every client, with what frees
    the port, never with a command that would start a server where none can listen."""

    def test_any_other_listener_on_the_port_is_named_to_status_and_to_every_client(self) -> None:
        from cadgen.engine import client, daemon
        from cadgen.engine.previous import version

        self.listen()
        self.assertEqual({key: client.holder()[key] for key in ("kind", "port")}, {"kind": "process", "port": self.port})
        free = "stop it or select another port with CADGEN_PORT"
        for held, who in (((4321, "squatter", "/usr/bin/squatter --listen"),
                           f"squatter (pid 4321), not a cadgen {version()} server"),
                          ((4322, "python3.13", "/venv/bin/python -m cadgen.engine server"),
                           "another cadgen (python3.13, pid 4322) that this cadgen cannot reach (another engine folder, "
                           "or an older release)"),
                          ((None, None, None), f"another process, not a cadgen {version()} server")):
            said = f"port {self.port} is held by {who}: {free}"
            with self.subTest(held=held), mock.patch.object(daemon, "port_holder", return_value=held):
                self.assertEqual(str(client.missing()), said)
                self.assertEqual(self.cli("status"), (1, "", f"cadgen status: {said}\n"))
                code, out, _err = self.cli("status", "--json")
                self.assertEqual((code, json.loads(out)), (1, {"ok": False, "error": said, "holder": {
                    "kind": "process", "port": self.port, "pid": held[0], "name": held[1], "cadgen": held[0] == 4322}}))
        self.assertEqual(self.cli("stop"), (0, "no engine server is running\n", ""), "nothing of cadgen's to stop")

    def test_this_release_s_engine_starting_or_stopping_is_said_to_be(self) -> None:
        # Its HTTP server binds before its door is made, and its door goes before it closes: a cadgen
        # holding the port and the port's lock is this release's engine on its way in or out.
        from cadgen.engine import client, daemon

        self.listen()
        held = daemon.lock()
        self.addCleanup(held.close)
        said = (f"port {self.port}'s server (python3.13, pid 4323) holds its private lock but has not answered; it "
                "may be starting or stopping: try again once it is ready")
        with mock.patch.object(daemon, "port_holder",
                               return_value=(4323, "python3.13", "/venv/bin/python -P -m cadgen._internal.engine_daemon")):
            self.assertEqual(str(client.missing()), said)
            self.assertEqual(self.cli("status"), (1, "", f"cadgen status: {said}\n"))
            held.close()  # a lock nobody holds is a dead engine's: another cadgen, which this one cannot reach
            self.assertIn("that this cadgen cannot reach", str(client.missing()))


class ExportRequestTest(unittest.TestCase):
    def test_an_export_runs_in_the_engine_s_record_of_its_document_never_its_request_s_execution(self) -> None:
        # A client names a document by its id and the engine substitutes what it holds of it; an
        # execution the request names itself is never used, so a malformed one is refused like any
        # export of a document the engine does not hold, never a handler that crashed.
        import io

        from cadgen.engine import daemon

        engine = daemon.Daemon(cap=1)
        self.addCleanup(engine.pool.stop)
        identity = {"protocol": daemon.PROTOCOL, "release": engine.release_version, "port": engine.port,
                    "instance": engine.instance}
        from cadgen.engine import client

        hello = client.hello(port=engine.port)
        held = "00000000-0000-5000-8000-000000000000"
        for crafted in ({"source": {"script": "/project/model.py", "function": "part", "held": held,
                                    "execution": {"python": "/project/.venv/bin/python"}}},
                        {"source": {"script": "/project/model.py", "function": "part", "held": held},
                         "execution": "not an execution"}):
            request = {"op": "export", "engineIdentity": identity, "destinations": ["out.step"], **crafted}
            lines = "".join(json.dumps({"token": engine.token, **message}) + "\n" for message in (hello, request))
            out = io.BytesIO()
            with self.subTest(crafted=crafted):
                daemon._serve(engine, io.BytesIO(lines.encode()), out)
                answers = [json.loads(line) for line in out.getvalue().splitlines()]
                self.assertTrue(answers[0]["ok"])
                self.assertIn(held, answers[-1]["failed"], "refused as a document the engine does not hold")


class OwnFilesTest(unittest.TestCase):
    """A stopping engine removes its own files from the engine folder; a starting one removes every
    dead engine's, never a live engine's nor anything in the folder that is not an engine's."""

    def setUp(self) -> None:
        self.state = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        self.addCleanup(shutil.rmtree, self.state, True)
        own = Path(tempfile.mkdtemp(prefix="own-"))
        self.addCleanup(shutil.rmtree, own, True)
        self.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CADGEN_ENGINE_DIR": str(self.state),
                                          "CADGEN_PORT": str(engine_daemon.free_port()),
                                          "CADGEN_STATE_DIR": str(own / "state"), "CADGEN_CACHE_DIR": str(own / "cache"),
                                          "CADGEN_ENGINE_STANDBY": "0"}, self.addCleanup)
        patch = mock.patch.dict(os.environ, self.env, clear=True)
        patch.start()
        self.addCleanup(patch.stop)

    def started(self) -> subprocess.Popen:
        from cadgen.engine import client

        server = subprocess.Popen([sys.executable, "-m", "cadgen.engine.daemon"], env=self.env,
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

    def until(self, condition, what: str) -> None:
        deadline = time.monotonic() + 60
        while not condition():
            self.assertLess(time.monotonic(), deadline, what)
            time.sleep(0.05)

    def test_an_engine_removes_its_files_as_it_stops_and_dead_engines_files_as_it_starts(self) -> None:
        from cadgen.engine import client, daemon

        ours = daemon._tag()
        daemon.failure_path().write_text('{"reason": "an earlier start"}', encoding="utf-8")
        dead = self.state / "aaaaaaaaaaaa.lock"
        dead.write_text("", encoding="utf-8")  # a killed engine's: nobody holds it
        live = self.state / "cccccccccccc.lock"
        held = daemon.lock(live)  # another engine's, running
        self.addCleanup(held.close)
        (self.state / "cccccccccccc.port").write_text("1 token\n", encoding="utf-8")
        server = self.started()
        self.until(lambda: not dead.exists(), "the starting engine removed the dead engine's lock")
        self.assertTrue(live.exists() and (self.state / "cccccccccccc.port").exists(), "a live engine's files stay")
        self.assertIn(f"{ours}.failed", self.left(), "its own note is not a dead engine's")
        self.assertEqual(client.request({"op": "stop"}, start=False), {"ok": True})
        self.assertEqual(server.wait(timeout=60), 0)
        self.assertEqual(self.left(), ["cccccccccccc.lock", "cccccccccccc.port"],
                         "its lock, door and failure note went with it")
        if os.name != "nt":  # a terminate stops it as ``stop`` does; Windows' terminate is a kill
            server = self.started()
            server.terminate()
            self.assertEqual(server.wait(timeout=60), 0)
            self.assertEqual(self.left(), ["cccccccccccc.lock", "cccccccccccc.port"])

    @unittest.skipIf(os.name == "nt", "doors and sockets are a POSIX engine's")
    def test_the_sweep_takes_a_dead_engine_s_files_and_leaves_a_live_one_s_and_what_is_no_engine_s(self) -> None:
        import socket

        from cadgen.engine import daemon

        def fifo(name: str, *, read: bool = False) -> None:
            os.mkfifo(self.state / name, 0o600)
            if read:  # an engine reads it: it answers
                reader = os.open(self.state / name, os.O_RDONLY | os.O_NONBLOCK)
                self.addCleanup(os.close, reader)

        old = time.time() - 600
        for name in ("aaaaaaaaaaaa.lock", "aaaaaaaaaaaa.port", "aaaaaaaaaaaa.failed", "eeeeeeeeeeee.lock",
                     "eeeeeeeeeeee.failed", "cccccccccccc.lock", "cccccccccccc.failed", f"{daemon._tag()}.failed",
                     "cadgen-open-0123456789abcdef.html", "notes.txt", "ABCDEFABCDEF.lock", "aaaaaaaaaaaa.lock.bak"):
            (self.state / name).write_text("", encoding="utf-8")
        for name in ("aaaaaaaaaaaa.failed", "cccccccccccc.failed"):
            os.utime(self.state / name, (old, old))
        (self.state / "clients").mkdir()
        fifo("aaaaaaaaaaaa.door")  # killed: nobody reads it
        fifo("cccccccccccc.door", read=True)
        fifo("dddddddddddd.door", read=True)  # an engine with no lock file here answers: it is live
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stale.bind(str(self.state / "bbbbbbbbbbbbbbbb.sock"))  # an early engine's, bound and gone
        stale.close()
        listening = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listening.bind(str(self.state / "ffffffffffff.sock"))
        listening.listen(16)
        self.addCleanup(listening.close)
        held = daemon.lock(self.state / "cccccccccccc.lock")
        self.addCleanup(held.close)

        removed = daemon.sweep_dead(self.state)
        self.assertEqual(sorted(Path(path).name for path in removed),
                         ["aaaaaaaaaaaa.door", "aaaaaaaaaaaa.failed", "aaaaaaaaaaaa.lock", "aaaaaaaaaaaa.port",
                          "bbbbbbbbbbbbbbbb.sock", "eeeeeeeeeeee.lock"])
        self.assertEqual(self.left(), sorted(["ABCDEFABCDEF.lock", "aaaaaaaaaaaa.lock.bak", "cadgen-open-0123456789abcdef.html",
                                              "cccccccccccc.door", "cccccccccccc.failed", "cccccccccccc.lock",
                                              "dddddddddddd.door", "eeeeeeeeeeee.failed", f"{daemon._tag()}.failed",
                                              "ffffffffffff.sock", "notes.txt"]),
                         "a live engine's files, a note its client may still read, this engine's and no engine's stay")
        self.assertEqual(daemon.sweep_dead(self.state), [], "nothing is removed twice")

    @unittest.skipIf(os.name == "nt", "an open file is never removed on Windows")
    def test_a_lock_whose_file_is_removed_as_it_is_taken_takes_the_file_its_name_names(self) -> None:
        import builtins

        from cadgen.engine import daemon

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
            held = daemon.lock(path)
        self.addCleanup(held.close)
        self.assertEqual(opened, [str(path)])
        self.assertTrue(daemon._names(held, path), "the lock is on the file the name names")
        self.assertIsNone(daemon.lock(path), "and it is held: no second daemon takes it")


class StateDirSpellingTest(unittest.TestCase):
    def test_a_server_started_under_a_dotted_spelling_is_found_and_stopped_under_the_plain_one(self) -> None:
        from unittest import mock

        from cadgen.engine import client

        state = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        self.addCleanup(shutil.rmtree, state, True)
        (state / "sub").mkdir()
        engine = "engine-" * 14  # a long folder: a pipe's path has no socket's length limit
        dotted = f"{state / 'sub'}{os.sep}..{os.sep}{engine}{os.sep}"  # a `..` and a trailing separator
        plain = str(state / engine)
        env = {**os.environ, "PYTHONPATH": str(SRC)}
        dotted_env = engine_daemon.watched({**env, "CADGEN_ENGINE_DIR": dotted}, self.addCleanup)
        plain_env = engine_daemon.watched({**env, "CADGEN_ENGINE_DIR": plain}, self.addCleanup)
        self.addCleanup(engine_daemon.run, [sys.executable, "-m", "cadgen.engine", "stop"], env=plain_env)
        probe = "from cadgen.engine.client import request; print(request({'op': 'status'}, start=True)['pid'])"
        started = engine_daemon.run([sys.executable, "-c", probe], env=dotted_env)
        self.assertEqual(started.returncode, 0, started.stderr)
        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": plain}):
            found = client.request({"op": "status"}, start=False)
            address = client._daemon.address()
        self.assertIsNotNone(found, "the plain spelling reaches the server the dotted one started")
        self.assertEqual(str(found["pid"]), started.stdout.split()[-1])
        done = engine_daemon.run([sys.executable, "-m", "cadgen.engine", "stop"], env=plain_env)
        self.assertEqual((done.returncode, done.stdout), (0, f"stopped the engine server at {address}\n"), done.stderr)
        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": dotted}):
            self.assertIsNone(client.request({"op": "status"}, start=False), "stopped under either spelling")


class InstallationTest(unittest.TestCase):
    def test_every_name_of_the_installation_s_interpreter_reaches_one_engine(self) -> None:
        from unittest import mock

        from cadgen.engine import daemon

        folder = os.path.dirname(sys.executable)
        names = [os.path.join(folder, name) for name in ("python", "python3", f"python3.{sys.version_info[1]}")]
        tags = set()
        for name in names:
            with mock.patch.object(sys, "executable", name):
                tags.add(daemon.address())
        self.assertEqual(len(tags), 1, "`python3 model.py` and `cadgen viewer` share one engine")

    def test_a_relative_and_an_absolute_launch_reach_one_engine(self) -> None:
        # `../../.venv/bin/python model.py` from a model folder, and the absolute path.
        probe = "from cadgen.engine import daemon; print(daemon.address())"
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
        engine = daemon.Daemon(port=port)
        with mock.patch("cadgen.engine.serve.Mesher") as mesher, mock.patch.object(daemon, "HTTP_FACTORY", None), \
                mock.patch.object(daemon, "_answers", return_value=False):
            with self.assertRaisesRegex(daemon.PortHeld, f"^port {port} is held by"):
                engine.serve({})
        mesher.return_value.stop.assert_called_once_with()
        self.assertIsNone(engine.server)
        with mock.patch("cadgen.viewer.engine_app.EngineApp") as app, self.assertRaises(OSError):
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
        storage = Path(tempfile.mkdtemp(prefix="engine-storage-")).resolve()
        cleanup(shutil.rmtree, storage, True)
        env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CADGEN_ENGINE_DIR": str(state),
                                     "CADGEN_PORT": str(engine_daemon.free_port()),
                                     "CADGEN_STATE_DIR": str(storage / "state"),
                                     "CADGEN_CACHE_DIR": str(storage / "cache"),
                                     "CADGEN_ENGINE_MESH": "inline", **extra}, cleanup)
        cleanup(cls.stopped, state, env)
        engine_daemon.bootstrap(env)
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
        """The rows of ``status``'s ``workers`` or ``retired`` that are this test's scripts'."""
        return [row for row in rows if Path(row["script"]).parent == self.folder]

    @staticmethod
    def stopped(state: Path, env: dict) -> None:
        engine_daemon.run([sys.executable, "-m", "cadgen.engine", "stop"], env=env)
        deadline = time.monotonic() + 20
        while any(state.glob("*.door")) and time.monotonic() < deadline:
            time.sleep(0.05)

    def _restart_daemon(self) -> None:
        self.stopped(self.state, self.env)
        engine_daemon.bootstrap(self.env)

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

    def test_inspection_never_builds_a_missing_or_edited_script_model(self):
        from cadgen.engine.ids import model_id

        # The registry alone, a cache folder nothing can write: a restart is refused with the command
        # (what the cache reopens is ``test_cache``'s).
        self.own(CADGEN_CACHE_DIR=engine_daemon.unwritable(self.folder))

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
        self._restart_daemon()
        # After a restart the registry knows it: refused with the command that builds it again, run by no one.
        missing = self.cli("inspect", ident, "face 1")
        self.assertEqual(missing.returncode, 2)
        self.assertIn(f"block ({ident}) is not saved: the engine's cache holds no file of its last build; run "
                      "`cadgen run ", missing.stderr)
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

        aside = Path(tempfile.mkdtemp(prefix="engine-daemon-cache-")).resolve()
        self.addCleanup(shutil.rmtree, aside, True)
        self.own(CADGEN_CACHE_DIR=engine_daemon.unwritable(aside))  # nothing kept: ``test_cache``'s

        address = self._bare()
        first = self.built("bracket")
        self.assertEqual(first["files"], {})
        self.assertEqual(first["id"], address)
        self.assertNotIn("address", first, "a report names its document by its id alone")
        url = urlparse(first["url"])
        doc = url.path.strip("/")
        endpoint = f"{url.scheme}://{url.netloc}/api/doc/{doc}"
        token = parse_qs(url.query)["token"][0]
        before = get_json(endpoint, token)
        (self.folder / "bracket.py").write_text(textwrap.dedent(BARE.format(size=2)), encoding="utf-8")
        second = self.built("bracket")
        self.assertEqual(urlparse(second["url"])[:3], url[:3], "one address, each URL with a fresh link")
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
        self._restart_daemon()
        missing = self.cli("inspect", f"{address}#face 1")
        self.assertEqual(missing.returncode, 2)
        self.assertIn(f"bracket ({address}) is not saved: the engine's cache holds no file of its last build; "
                      "run `cadgen run ", missing.stderr)
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
        seen = "import os\nif os.environ.get('CADGEN_ENGINE_WORKER'):\n" \
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
        self._restart_daemon()
        self.assertTrue(build(10)["cache"]["used"], "a fresh worker takes the file its key is in")
        xbf.unlink()
        self._restart_daemon()
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
        api = f"{base}/api/doc/{ident}"
        before = get_json(api, token)
        for prototype in before["prototypes"]:  # the page has every part
            self.assertEqual(get(f"{api}/part/{prototype['key']}", token)[:4], b"XBM2")
        self.script.write_text(textwrap.dedent(PAIR.format(size=12)), encoding="utf-8")
        ran = self.run_script("pair.py")
        self.assertEqual(ran.returncode, 0, ran.stderr)
        answer = get_json(f"{api}/version?after={before['version']}&wait=60", token)
        stat = (self.folder / "XBF/pair.xbf").stat()
        self.assertEqual(answer["version"], f"{stat.st_mtime_ns}-{stat.st_size}", "the file's own version")
        self.assertNotIn("patch", answer, "nothing of the run reached the page")
        after = get_json(api, token)
        keys = lambda s: {p["name"]: p["key"] for p in s["prototypes"]}  # noqa: E731
        self.assertNotEqual(keys(after)["block"], keys(before)["block"])
        self.assertEqual(keys(after)["peg"], keys(before)["peg"])
        self.assertEqual(get(f"{api}/part/{keys(after)['block']}", token)[:4], b"XBM2")

    def where(self, ref: str, doc: str = "XBF/block.xbf") -> dict:
        found = engine_daemon.run([sys.executable, "-m", "cadgen.cli", "inspect", doc, ref], cwd=self.folder,
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
        self._restart_daemon()
        cold = self.where("block/face 1", ident)
        self.assertIsNone(cold.pop("made_by"))
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
        self.assertEqual(self.mine(status["workers"]), [], "each worker left the pool when it was retired")
        self.assertEqual([row["reason"] for row in self.mine(status["retired"])], ["RSS", "RSS"])

    def test_a_failing_body_answers_with_its_error(self) -> None:
        self.script.write_text("from cadgen.engine import xbf\n\n@xbf('XBF/block.xbf')\ndef block():\n    raise RuntimeError('no')\nif __name__ == '__main__':\n    block()\n", encoding="utf-8")
        done = self.run_script("block.py")
        self.assertEqual(done.returncode, 1)
        self.assertIn("RuntimeError: no", done.stderr)

    def test_a_rerun_behind_its_script_s_running_build_says_it_waits_and_takes_what_it_built(self) -> None:
        # A client its shell's time limit killed leaves its build running; the same command again
        # waits for that build, says so at once, and takes the document it made from its key.
        # Nothing is cancelled.
        from cadgen.engine import client

        gate = self.folder / "gate"
        (self.folder / "turbine.py").write_text(textwrap.dedent(f"""
            import os, time
            import build123d as bd
            from cadgen.engine import model


            @model
            def turbine():
                while not os.path.exists({str(gate)!r}):  # held until the test lets it go
                    time.sleep(0.01)
                return bd.Box(2, 2, 2) - bd.Cylinder(0.5, 3)

            if __name__ == "__main__":
                turbine()
            """), encoding="utf-8")

        def status() -> dict:
            with mock.patch.dict(os.environ, self.env, clear=True):
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

        from cadgen.engine.ids import model_id

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
        self.own()
        self.stopped(self.state, self.env)  # declarations must work with no running server
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
        self.assertFalse(any(self.state.glob("*.door")) or any(self.state.glob("*.port")), "importing starts no daemon")
        engine_daemon.bootstrap(self.env)
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
            from cadgen.engine import export

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
        before = get_json(f"{base}/api/doc/{ident}", token)
        stl = self.folder / "pair.stl"
        written = stl.stat().st_mtime_ns
        self.script.write_text(slow.format(size=12), encoding="utf-8")
        gate.unlink()
        building = subprocess.Popen([sys.executable, "pair.py"], cwd=self.folder, env=self.env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(building.wait)
        answer = get_json(f"{base}/api/doc/{ident}/version?after={before['version']}&wait=60", token)
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
        standby, ``CADGEN_ENGINE_STANDBY=0``)."""
        self.own(CADGEN_ENGINE_STANDBY="0", CADGEN_ENGINE_MESH="processes")
        env = {name: value for name, value in self.env.items() if name != "CADGEN_ENGINE_MESH"}
        env["CADGEN_ENGINE_STANDBY"] = "0"
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

        self.own()

        probe = ("import json; from cadgen.engine.client import request; request({'op': 'warm'}); "
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
