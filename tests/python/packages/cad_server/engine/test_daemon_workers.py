"""The daemon's workers: one per script, started on demand, that keeps its memo between builds and
serves one run's calls from one load; its request loop, its kernel's first load and the environment
each run adopts; a worker whose client is gone or that failed, and one retired over its memory cap or
for another environment. Each engine started here has a folder of its own (``CAD_ENGINE_DIR``), and the
state and cache folders the run gives this file (``CAD_STATE_DIR``, ``CAD_CACHE_DIR``)."""

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
from pathlib import Path
from unittest import mock

from tests.python.support import daemon_fixtures, engine_daemon
from tests.python.support.daemon_fixtures import MODEL, SRC

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

    def test_the_engine_s_display_told_with_a_picture_outlives_every_run_after(self) -> None:
        # A model's still is drawn on the engine's X display where its run names no DISPLAY: told with the first
        # export that draws, and kept through each run's environment after, which never names it.
        from cad.engine.worker import adopt, told_display

        own = {"CAD_ENGINE_WORKER": "1"}
        with mock.patch.dict(os.environ, {"CAD_ENGINE_WORKER": "1"}, clear=True):
            adopt({"PATH": "/turn/1"}, own)
            self.assertNotIn("CAD_ENGINE_DISPLAY", os.environ, "a build is told nothing")
            told_display({"CAD_ENGINE_DISPLAY": ":7", "CAD_ENGINE_XAUTHORITY": "/x/cookie", "PATH": "/no"}, own)
            for turn in ({"PATH": "/turn/2"}, {"PATH": "/turn/3", "CAD_ENGINE_DISPLAY": ":99"}, None):
                adopt(turn, own)
                self.assertEqual((os.environ["CAD_ENGINE_DISPLAY"], os.environ["CAD_ENGINE_XAUTHORITY"]),
                                 (":7", "/x/cookie"))
            self.assertEqual(os.environ["PATH"], "/turn/3", "nothing else it was told")


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


class DaemonWorkerTest(daemon_fixtures.DaemonCase):
    """A script's worker through the daemon: warm between builds, in the folder of no project, retired
    and replaced."""

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


if __name__ == "__main__":
    unittest.main()
