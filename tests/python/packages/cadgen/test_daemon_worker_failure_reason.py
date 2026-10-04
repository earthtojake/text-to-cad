"""The native worker's exit evidence must reach the daemon job ledger."""

from __future__ import annotations

import json
import multiprocessing.connection as mpc
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from cadgen.daemon import pool, server
from cadgen.daemon.jobs import JobLedger
from cadgen.daemon.transport import Channel
from cadgen.viewer.build_progress import build_progress_snapshot


class WorkerFailureReasonTest(unittest.TestCase):
    def relay_child(self, response: str):
        # This child only speaks the real worker's stdio frame protocol. No CAD
        # imports are needed to exercise EOF, exit status, relay and ledger finish.
        child = subprocess.Popen(
            [sys.executable, "-c", "import json,sys\nsys.stdin.readline()\n" + response],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8",
        )
        worker = pool.Worker.__new__(pool.Worker)
        worker.proc = child
        worker.pid = child.pid
        worker.extra = False
        worker._frames = queue.Queue()
        reader = threading.Thread(target=worker._pump, daemon=True)
        reader.start()
        ledger = JobLedger()
        supervisor, client = (Channel(connection) for connection in mpc.Pipe())
        admission = mock.Mock()
        admission.acquire.return_value = worker
        try:
            with tempfile.TemporaryDirectory(prefix="cadgen-worker-reason-") as temp:
                document = Path(temp) / "owned.step"
                document.write_text("owned test document", encoding="utf-8")
                request = {"tool": "step-compile", "argv": [str(document)], "cwd": temp,
                           "store_root": str(Path(temp) / "store")}
                with mock.patch.object(server, "_POOL", admission), \
                     mock.patch.object(server, "_JOBS", ledger), \
                     mock.patch.object(server, "_log"), \
                     mock.patch.object(server, "_REQUESTS_SERVED", [0]):
                    server._handle_request(supervisor, request)
                frames = []
                while True:
                    frame = json.loads(client.recv(2))
                    frames.append(frame)
                    if "exit" in frame:
                        break
                return ledger.snapshot()[0], frames
        finally:
            supervisor.close()
            client.close()
            if child.poll() is None:
                child.kill()
            child.wait(timeout=2)
            if child.stdin is not None:
                child.stdin.close()
            reader.join(2)
            self.assertFalse(reader.is_alive(), "owned child frame reader did not end")

    def test_unexpected_native_worker_exit_keeps_its_reason_in_the_ledger(self):
        job, frames = self.relay_child("sys.exit(7)\n")
        death = next(frame["workerDied"] for frame in frames if "workerDied" in frame)
        self.assertEqual(death["exitStatus"], 7)
        self.assertEqual((job["state"], job["exit"]), ("failed", 1))
        progress = build_progress_snapshot(job["outputs"][0], jobs=[job])
        self.assertEqual(progress["failed"]["error"], death["detail"])
        self.assertEqual(job["error"], death["detail"])
        self.assertIn("code 7", job["error"])

    def test_reported_tool_failure_keeps_its_existing_error(self):
        job, frames = self.relay_child(
            "print(json.dumps({'stream':'stderr','data':'RuntimeError: owned failure\\n'}),flush=True)\n"
            "print(json.dumps({'exit':2}),flush=True)\n"
        )
        self.assertEqual((job["state"], job["exit"], job["error"]), ("failed", 2, "owned failure"))
        self.assertFalse(any("workerDied" in frame for frame in frames))

    def test_worker_exit_reason_is_separate_from_partial_stderr(self):
        job, frames = self.relay_child(
            "print(json.dumps({'stream':'stderr','data':'starting owned operation '}),flush=True)\n"
            "sys.exit(7)\n"
        )
        death = next(frame["workerDied"] for frame in frames if "workerDied" in frame)
        self.assertEqual(job["error"], death["detail"])

    def test_success_has_no_failure_reason(self):
        job, frames = self.relay_child("print(json.dumps({'exit':0}),flush=True)\n")
        self.assertEqual((job["state"], job["exit"], job["error"]), ("done", 0, None))
        self.assertFalse(any("workerDied" in frame for frame in frames))


if __name__ == "__main__":
    unittest.main()
