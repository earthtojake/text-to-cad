"""Change notifications cannot lose a revision or occupy a build worker."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

from cadgen.daemon.jobs import JobLedger


class JobWatch(unittest.TestCase):
    def test_start_and_preview_wake_a_waiter_without_a_poll_delay(self):
        ledger = JobLedger()
        for change in (
            lambda: ledger.start(tool="run", subject=""),
            lambda: ledger.observe({"event": {
                "model": "/part.py", "job": job["id"], "state": "building", "sequence": 1,
                "preview": {"output": "/part.step", "tree": "tree"},
            }}),
        ):
            before = ledger.watch(timeout=0)
            result = []
            thread = threading.Thread(target=lambda: result.append(ledger.watch(before["jobsCursor"])))
            thread.start()
            try:
                change()
                thread.join(timeout=0.5)
                self.assertFalse(thread.is_alive(), "ledger change did not notify its waiter")
            finally:
                thread.join(timeout=2)
            self.assertNotEqual(before["jobsCursor"], result[0]["jobsCursor"])
            job = ledger.start(tool="run", subject="/part.py")
        self.assertEqual(result[0]["jobs"][-1]["previews"][os.path.realpath("/part.step")]["tree"], "tree")

    def test_snapshot_and_cursor_are_atomic_and_detached(self):
        ledger = JobLedger()
        before = ledger.watch(timeout=0)
        job = ledger.start(tool="run", subject="")
        after = ledger.watch(before["jobsCursor"], timeout=0)
        after["jobs"][0]["outputs"].append("mutated")
        self.assertEqual(job["outputs"], [])
        current = ledger.watch(after["jobsCursor"], timeout=0)
        self.assertEqual(after["jobsCursor"], current["jobsCursor"])
        self.assertEqual(current["jobs"][0]["id"], job["id"])

    def test_restart_expiry_and_completion_invalidate_cursors(self):
        now = [1.0]
        ledger = JobLedger(retain_seconds=2, clock=lambda: now[0])
        job = ledger.start(tool="run", subject="")
        before = ledger.watch(timeout=0)
        ledger.finish(job, 0)
        finished = ledger.watch(before["jobsCursor"], timeout=0)
        self.assertEqual(finished["jobs"][0]["state"], "done")
        now[0] = 4.0
        expired = ledger.watch(finished["jobsCursor"], timeout=0)
        self.assertNotEqual(expired["jobsCursor"], finished["jobsCursor"])
        self.assertEqual(expired["jobs"], [])
        restarted = JobLedger().watch(expired["jobsCursor"], timeout=0)
        self.assertNotEqual(restarted["jobsCursor"], expired["jobsCursor"])

    def test_filtered_watch_ignores_unrelated_jobs_but_wakes_for_its_producer(self):
        with tempfile.TemporaryDirectory() as scratch:
            output = str((Path(scratch) / "part.step").resolve())
            other = str((Path(scratch) / "other.step").resolve())
            store = str((Path(scratch) / "store").resolve())
            ledger = JobLedger()
            producer = ledger.start(tool="run", subject=output, store_root=store)
            before = ledger.watch(timeout=0, output=output, store_root=store)

            result = []
            thread = threading.Thread(target=lambda: result.append(ledger.watch(
                before["jobsCursor"], timeout=0.5, output=output, store_root=store,
            )))
            thread.start()
            try:
                time.sleep(0.03)
                ledger.start(tool="run", subject=other, store_root=store)
                thread.join(timeout=0.05)
                self.assertTrue(thread.is_alive(), "an unrelated output woke the filtered watch")
                unchanged = ledger.watch(
                    before["jobsCursor"], timeout=0, output=output, store_root=store,
                )
                self.assertEqual(before["jobsCursor"], unchanged["jobsCursor"])

                ledger.observe({"event": {
                    "model": output, "job": producer["id"], "state": "building", "sequence": 1,
                }})
                thread.join(timeout=0.5)
                self.assertFalse(thread.is_alive(), "the matching producer did not wake its watch")
            finally:
                thread.join(timeout=1)
            self.assertNotEqual(before["jobsCursor"], result[0]["jobsCursor"])
            self.assertEqual([producer["id"]], [job["id"] for job in result[0]["jobs"]])

    def test_filtered_cursor_is_scoped_opaque_and_restart_safe(self):
        with tempfile.TemporaryDirectory() as scratch:
            output = str((Path(scratch) / "part.step").resolve())
            other = str((Path(scratch) / "other.step").resolve())
            store = str((Path(scratch) / "store").resolve())
            other_store = str((Path(scratch) / "other-store").resolve())
            ledger = JobLedger()
            selected = ledger.start(tool="run", subject=output, store_root=store)
            ledger.start(tool="run", subject=output, store_root=other_store)
            ledger.start(tool="run", subject=other, store_root=store)
            ledger.start(tool="run", subject=output, store_root=store, editing_producer=False)

            scoped = ledger.watch(timeout=0, output=output, store_root=store)
            self.assertEqual([selected["id"]], [job["id"] for job in scoped["jobs"]])
            self.assertLessEqual(len(scoped["jobsCursor"]), 128)
            self.assertNotIn(output, scoped["jobsCursor"])
            self.assertNotIn(store, scoped["jobsCursor"])
            self.assertEqual(
                scoped["jobsCursor"],
                ledger.watch(scoped["jobsCursor"], timeout=0, output=output, store_root=store)["jobsCursor"],
            )
            restarted = JobLedger().watch(
                scoped["jobsCursor"], timeout=0, output=output, store_root=store,
            )
            self.assertNotEqual(scoped["jobsCursor"], restarted["jobsCursor"])

    def test_filtered_cursor_changes_when_a_selected_finished_job_expires(self):
        now = [1.0]
        with tempfile.TemporaryDirectory() as scratch:
            output = str((Path(scratch) / "part.step").resolve())
            store = str((Path(scratch) / "store").resolve())
            ledger = JobLedger(retain_seconds=2, clock=lambda: now[0])
            producer = ledger.start(tool="run", subject=output, store_root=store)
            ledger.finish(producer, 0)
            finished = ledger.watch(timeout=0, output=output, store_root=store)
            now[0] = 4.0
            expired = ledger.watch(
                finished["jobsCursor"], timeout=0, output=output, store_root=store,
            )
            self.assertNotEqual(finished["jobsCursor"], expired["jobsCursor"])
            self.assertEqual([], expired["jobs"])


class Channel:
    def __init__(self, reply=None):
        self.frames, self.closed, self.reply = [], False, reply

    def send(self, raw):
        self.frames.append(json.loads(raw))

    def recv(self, timeout):
        return json.dumps(self.reply).encode() if self.reply is not None else b""

    def close(self):
        self.closed = True


class WatchTransport(unittest.TestCase):
    def test_client_reads_without_spawning_or_computing_source_token(self):
        from cadgen.daemon import client

        channel = Channel({"status": {"jobsCursor": "epoch:2", "jobs": []}})
        with (
            mock.patch.object(client, "daemon_supported", return_value=True),
            mock.patch.object(client, "_connect", return_value=channel),
            mock.patch.object(client, "_connect_or_spawn", side_effect=AssertionError("spawn")),
            mock.patch.object(client, "compute_version_token", side_effect=AssertionError("source scan")),
        ):
            self.assertEqual(client.watch_jobs("epoch:1", output="/a/part.step", store_root="/a/store"),
                             channel.reply["status"])
        self.assertEqual(channel.frames, [{"kind": "status", "jobsOnly": True, "after": "epoch:1",
                                          "output": "/a/part.step", "storeRoot": "/a/store"}])
        self.assertTrue(channel.closed)

    def test_unavailable_feed_does_not_start_a_daemon(self):
        from cadgen.daemon import client

        with mock.patch.object(client, "_connect", side_effect=OSError), \
                mock.patch.object(client, "_connect_or_spawn", side_effect=AssertionError("spawn")):
            self.assertIsNone(client.watch_jobs())

    def test_waiter_owns_channel_and_does_not_touch_pool_or_broker(self):
        from cadgen.daemon import server

        entered, release = threading.Event(), threading.Event()
        channel = Channel()
        slots = threading.BoundedSemaphore(1)
        ledger = mock.Mock()

        def wait(after):
            entered.set()
            if not release.wait(2):
                raise AssertionError("test did not release waiter")
            return {"jobsCursor": "epoch:2", "jobs": []}

        ledger.watch.side_effect = wait
        with mock.patch.object(server, "_JOBS", ledger), \
                mock.patch.object(server, "_JOB_WATCH_SLOTS", slots), \
                mock.patch.object(server, "_POOL") as pool, mock.patch.object(server, "_BROKER") as broker:
            try:
                self.assertTrue(server._start_job_watch(channel, {"after": "epoch:1"}))
                self.assertTrue(entered.wait(1))
                self.assertFalse(channel.closed)
                pool.assert_not_called()
                broker.assert_not_called()
                self.assertEqual(pool.mock_calls, [])
                self.assertEqual(broker.mock_calls, [])
            finally:
                release.set()
                self.assertTrue(slots.acquire(timeout=2))
                slots.release()
        self.assertTrue(channel.closed)
        self.assertEqual(channel.frames[0]["status"]["jobsCursor"], "epoch:2")

    def test_saturation_returns_immediately_without_an_extra_thread(self):
        from cadgen.daemon import server

        slots = threading.BoundedSemaphore(1)
        slots.acquire()
        channel = Channel()
        with mock.patch.object(server, "_JOBS", JobLedger()), \
                mock.patch.object(server, "_JOB_WATCH_SLOTS", slots), \
                mock.patch.object(server.threading, "Thread", side_effect=AssertionError("extra thread")):
            self.assertFalse(server._start_job_watch(channel, {"after": "epoch:1"}))
        self.assertIn("jobsCursor", channel.frames[0]["status"])

    def test_real_supervisor_serves_status_while_a_watch_is_held(self):
        from cadgen.daemon import client, transport

        if not transport.supported():
            self.skipTest("daemon transport unavailable")
        with tempfile.TemporaryDirectory(prefix="cadgen-watch-") as scratch:
            address = transport.private_address(f"watch-{uuid.uuid4().hex[:12]}")
            env = {"CADGEN_DAEMON_STATE_DIR": str(Path(scratch) / "state"),
                   "CADGEN_DAEMON_SOCKET": address, "CADGEN_DAEMON_SPARES": "0"}
            with mock.patch.dict(os.environ, env), open(Path(scratch) / "daemon.log", "wb") as log:
                process = subprocess.Popen([sys.executable, "-m", "cadgen.daemon"],
                                           stdout=log, stderr=log, env=dict(os.environ))
                thread = None
                try:
                    initial = None
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline and process.poll() is None:
                        initial = client.watch_jobs()
                        if initial is not None:
                            break
                        time.sleep(0.02)
                    self.assertIsNotNone(initial, "private supervisor did not become ready:\n" +
                                         (Path(scratch) / "daemon.log").read_text(encoding="utf-8", errors="replace"))
                    sent, done = threading.Event(), threading.Event()
                    real_send = client._send_json
                    replies = []

                    def send(channel, payload):
                        result = real_send(channel, payload)
                        if payload.get("after"):
                            sent.set()
                        return result

                    def watch():
                        try:
                            replies.append(client.watch_jobs(initial["jobsCursor"]))
                        finally:
                            done.set()

                    with mock.patch.object(client, "_send_json", send):
                        thread = threading.Thread(target=watch)
                        thread.start()
                        self.assertTrue(sent.wait(2))
                        snapshot = client.status()
                        self.assertIsNotNone(snapshot)
                        self.assertFalse(done.is_set(), "a held watch blocked the supervisor accept loop")
                        self.assertEqual(snapshot["workers"], [], "read-only requests spawned kernel workers")
                        thread.join(timeout=3)
                    self.assertFalse(thread.is_alive())
                    self.assertEqual(replies[0]["jobsCursor"], initial["jobsCursor"])
                finally:
                    if process.poll() is None:
                        process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                    if thread is not None:
                        thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
