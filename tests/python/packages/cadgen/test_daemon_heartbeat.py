"""Silence means hung, not busy: a running job heartbeats, and a silent worker's CPU is read.

Real worker processes (``cadgen.daemon.worker.serve``) run a tiny test-owned tool in
place of a model, with the kernel prewarm stubbed out and the intervals shrunk, so
each case costs about a second: a body that sleeps past the silence window survives
on its heartbeat; a body that holds the GIL while computing survives on its CPU
clock; a body that holds the GIL without computing, or a stopped process, is killed;
and ordinary frames arrive exactly as before, with no heartbeat relayed or left over.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from cadgen.daemon import pool as pool_mod
from tests.python.support.tmp_root import generated_cad_directory

HEARTBEAT = 0.2  # the worker's beat in these tests
SILENCE = 1.0  # the supervisor's silence window in these tests

_TOOL = textwrap.dedent('''
    import ctypes, os, signal, sys, time

    def _hold_gil_idle(seconds):
        # A foreign call through PyDLL keeps the GIL: nothing else in the process
        # runs, and nothing computes -- a native deadlock, as the heartbeat sees it.
        if os.name == "nt":
            ctypes.PyDLL("kernel32").Sleep(int(seconds * 1000))
        else:
            ctypes.PyDLL(None).sleep(int(seconds))

    def _hold_gil_busy(seconds):
        # sum() over a range is one C loop that never yields the GIL: a long OCCT
        # boolean, as the heartbeat sees it.
        start = time.perf_counter()
        sum(range(2_000_000))
        rate = 2_000_000 / max(time.perf_counter() - start, 1e-6)
        sum(range(int(rate * seconds)))

    def main(argv):
        verb, *rest = argv
        if verb == "print":
            for text in rest:
                print(text, flush=True)
                time.sleep(0.6)
            return 0
        if verb == "phase":
            from cadgen.daemon.executors import emit_event
            emit_event({"model": "m.py", "state": "building", "phase": rest[0]})
            time.sleep(float(rest[1]))  # a few beats carry the phase
            _hold_gil_idle(float(rest[2]))
            return 0
        if verb == "sleep":
            time.sleep(float(rest[0]))
        elif verb == "gil-idle":
            _hold_gil_idle(float(rest[0]))
        elif verb == "gil-busy":
            _hold_gil_busy(float(rest[0]))
        elif verb == "stop":
            os.kill(os.getpid(), signal.SIGSTOP)
        print("body done", flush=True)
        return 0
''')


class _WorkerCase(unittest.TestCase):
    def setUp(self) -> None:
        temporary = generated_cad_directory(prefix="daemon-heartbeat-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / "heartbeat_fixture_tool.py").write_text(_TOOL, encoding="utf-8")
        prelude = textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {str(self.root)!r})
            from cadgen.daemon import server, worker
            server._TOOL_IMPORTS["fixture"] = "heartbeat_fixture_tool"
            worker._warm_imports = lambda: None
            worker.HEARTBEAT_INTERVAL_SECONDS = {HEARTBEAT!r}
            raise SystemExit(worker.serve())
        """)
        original_popen = subprocess.Popen

        def start(argv, **kwargs):
            if argv == [sys.executable, "-m", "cadgen.daemon.worker"]:
                return original_popen([sys.executable, "-c", prelude], **kwargs)
            return original_popen(argv, **kwargs)

        with mock.patch.object(pool_mod.subprocess, "Popen", start):
            self.worker = pool_mod.Worker()
        self.addCleanup(self.worker.kill)

    def run_job(self, *argv: str) -> list[dict]:
        self.worker.send({
            "kind": "run", "tool": "fixture", "argv": list(argv), "cwd": str(self.root),
            "store_root": str(self.root / "store"), "job_id": "test:job-1", "env": {},
        })
        return list(self.worker.frames(silence_timeout=SILENCE))


class SilenceIsNotBusy(_WorkerCase):
    def test_a_body_sleeping_past_the_silence_window_survives_on_its_heartbeat(self):
        frames = self.run_job("sleep", str(SILENCE * 3))
        self.assertEqual(frames[-1]["exit"], 0)
        self.assertIn({"stream": "stdout", "data": "body done"}, frames)

    def test_a_native_call_holding_the_gil_while_computing_survives_on_its_cpu_clock(self):
        reads: list[float | None] = []
        real = pool_mod.process_cpu_seconds

        def spy(pid):
            reads.append(real(pid))
            return reads[-1]

        with mock.patch.object(pool_mod, "process_cpu_seconds", spy):
            frames = self.run_job("gil-busy", str(SILENCE * 3))
        self.assertEqual(frames[-1]["exit"], 0)
        # The heartbeat was starved, so the silence window really elapsed and the
        # worker's CPU clock is what kept it.
        self.assertTrue(reads, "the silence window never elapsed; the busy body did not starve the heartbeat")
        self.assertTrue(all(value is not None for value in reads))


class WedgedIsStillKilled(_WorkerCase):
    def test_a_blocked_heartbeat_with_no_cpu_progress_is_killed(self):
        # Left alone, the body would finish and exit 0: WorkerGone with this
        # message is the supervisor killing the wedge rather than waiting it out.
        with self.assertRaises(pool_mod.WorkerGone) as caught:
            self.run_job("phase", "fillets", str(HEARTBEAT * 3), str(SILENCE * 8))
        self.assertIn("no CPU progress", str(caught.exception))
        self.assertIn("last phase: fillets", str(caught.exception))
        self.assertFalse(self.worker.alive())

    @unittest.skipIf(os.name == "nt", "SIGSTOP is POSIX")
    def test_a_stopped_process_is_killed(self):
        with self.assertRaises(pool_mod.WorkerGone) as caught:
            self.run_job("stop")
        self.assertIn("went silent", str(caught.exception))
        self.assertFalse(self.worker.alive())

    @unittest.skipIf(os.name == "nt", "SIGSTOP is POSIX")
    def test_a_process_stopped_from_outside_mid_sleep_is_killed(self):
        self.worker.send({
            "kind": "run", "tool": "fixture", "argv": ["sleep", "30"], "cwd": str(self.root),
            "store_root": str(self.root / "store"), "job_id": "test:job-1", "env": {},
        })
        # The job's first beat is written as its body starts: from then on it is
        # mid-sleep. Left queued, the beat is the supervisor's CPU baseline.
        deadline = time.monotonic() + 60
        while self.worker._frames.empty():
            if time.monotonic() >= deadline:
                self.fail("the job never started")
            time.sleep(0.01)
        os.kill(self.worker.proc.pid, signal.SIGSTOP)
        with self.assertRaises(pool_mod.WorkerGone):
            list(self.worker.frames(silence_timeout=SILENCE))
        self.assertFalse(self.worker.alive())


class NormalFramesAreUnchanged(_WorkerCase):
    def test_output_arrives_in_order_and_no_heartbeat_is_relayed_or_left_over(self):
        # Each line is separated by three heartbeat intervals.
        frames = self.run_job("print", "one", "two")
        self.assertEqual({tuple(frame) for frame in frames[:-1]}, {("stream", "data")})
        self.assertEqual("".join(frame["data"] for frame in frames[:-1]), "one\ntwo\n")
        self.assertEqual(frames[-1], {"exit": 0, "pid": self.worker.pid})
        # The heartbeat stops with the job (HeartbeatLifetime pins the thread):
        # the next request's first frame on this channel is its own answer.
        self.worker.send({"kind": "ping"})
        self.assertEqual(self.worker._frames.get(timeout=60), {"pong": self.worker.pid})


class HeartbeatLifetime(unittest.TestCase):
    """The beat starts with a job and its thread is gone when the job is, in process."""

    def test_the_first_beat_is_synchronous_and_the_thread_is_joined_on_exit(self):
        from cadgen.daemon import worker

        beats: list[tuple[threading.Thread, dict]] = []
        second_beat = threading.Event()

        def emit(frame: dict) -> None:
            beats.append((threading.current_thread(), frame))
            if len(beats) >= 2:
                second_beat.set()

        with mock.patch.object(worker, "_emit", emit), \
                mock.patch.object(worker, "HEARTBEAT_INTERVAL_SECONDS", 0.01):
            with worker._heartbeat():
                # The supervisor's CPU baseline exists from the job's first instant:
                # the job's own thread emitted it, before the heartbeat thread could.
                self.assertIs(beats[0][0], threading.current_thread())
                self.assertIn("cpu", beats[0][1]["heartbeat"])
                self.assertTrue(second_beat.wait(60), "the heartbeat thread never beat")
            # Joined before the job's exit frame could be written: nothing can
            # beat after it, into the next request's channel.
            self.assertEqual(
                [thread for thread in threading.enumerate() if thread.name == "cadgen-worker-heartbeat"], []
            )


class CpuClock(unittest.TestCase):
    def test_this_process_clock_reads_like_process_time(self):
        sum(range(3_000_000))
        inside = time.process_time()
        outside = pool_mod.process_cpu_seconds(os.getpid())
        self.assertIsNotNone(outside, "no CPU clock on this platform: a starved heartbeat would read as a hang")
        self.assertAlmostEqual(outside, inside, delta=0.5)

    def test_ps_time_formats(self):
        self.assertEqual(pool_mod._parse_cpu_time("  0:01.50\n"), 1.5)
        self.assertEqual(pool_mod._parse_cpu_time("123:04.25"), 123 * 60 + 4.25)
        self.assertEqual(pool_mod._parse_cpu_time("01:02:03"), 3723.0)
        self.assertEqual(pool_mod._parse_cpu_time("2-01:02:03"), 2 * 86400 + 3723.0)

    @unittest.skipIf(os.name == "nt", "Windows reads the clock through GetProcessTimes")
    def test_the_clock_needs_no_ps_on_path(self):
        # A daemon inherits whatever PATH launched it; with no ps on it, a
        # starved-but-busy worker read as hung and was killed.
        with mock.patch.dict(os.environ, {"PATH": ""}):
            ps = pool_mod._ps_executable()
            self.assertTrue(os.path.isabs(ps), ps)
            self.assertIsNotNone(pool_mod.process_cpu_seconds(os.getpid()))

    def test_a_gone_process_has_no_clock(self):
        process = subprocess.Popen([sys.executable, "-c", "pass"])
        process.wait()
        self.assertIsNone(pool_mod.process_cpu_seconds(process.pid))


if __name__ == "__main__":
    unittest.main()
