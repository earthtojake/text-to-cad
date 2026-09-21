"""Coalesced requests keep the owning request's preview and completion identity."""
from __future__ import annotations

import concurrent.futures
import contextlib
import json
import os
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from cadgen.daemon import server
from cadgen.daemon.broker import Broker
from cadgen.daemon.jobs import JobLedger
from cadgen.viewer.preview import preview_status
from tests.python.support.store_fixtures import seed_result
from tests.python.support.tmp_root import generated_cad_directory


class Connection:
    def __init__(self):
        self.frames = []

    def send(self, raw):
        self.frames.append(json.loads(raw))


class DisconnectableConnection(Connection):
    def __init__(self):
        super().__init__()
        self.disconnected = threading.Event()
        self.failed_send = threading.Event()

    def send(self, raw):
        if self.disconnected.is_set():
            self.failed_send.set()
            raise OSError("peer closed")
        super().send(raw)

    def recv(self, _timeout=None):
        return b"" if self.disconnected.is_set() else None


class PreviewWorker:
    pid = 123
    extra = False

    def __init__(self, model, output, tree, *, exit_code=0):
        self.model, self.output, self.tree = model, output, tree
        self.exit_code = exit_code
        self.preview_relayed = threading.Event()
        self.allow_save = threading.Event()
        self.saved_relayed = threading.Event()
        self.allow_exit = threading.Event()
        self.killed = False

    def send(self, request):
        self.request = request

    def alive(self):
        return not self.killed

    def kill(self):
        self.killed = True
        self.allow_save.set()
        self.allow_exit.set()

    def event(self, sequence, **extra):
        return {"event": {"model": str(self.model), "job": self.request["job_id"],
                          "sequence": sequence, "state": "building", **extra}}

    def frames(self, **_kwargs):
        yield self.event(1, preview={"output": str(self.output), "tree": self.tree},
                         sourceResult={"model": f"{self.model}::part", "tree": self.tree})
        self.preview_relayed.set()  # The supervisor has folded and relayed it.
        if not self.allow_save.wait(5):
            raise AssertionError("Test did not release the save barrier")
        if self.exit_code == 0:
            from cadgen.catalog import artifact_file_hash
            from cadgen.store.records import note_document_tree

            self.output.write_bytes(b"completed document bytes")
            digest = artifact_file_hash(self.output)
            note_document_tree(digest, self.tree)
            yield self.event(2, saved={"output": str(self.output), "tree": self.tree,
                                       "documentHash": digest})
        else:
            yield {"stream": "stderr", "data": "[cadgen] FAILED: RuntimeError: save refused\n"}
        self.saved_relayed.set()
        if not self.allow_exit.wait(5):
            raise AssertionError("Test did not release the completion barrier")
        yield {"exit": self.exit_code}


class CoalescedPreviewRequests(unittest.TestCase):
    def setUp(self):
        temporary = generated_cad_directory(prefix="coalesced-preview-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.model = self.root / "part.py"
        self.model.write_text("from cadgen import step\n@step\ndef part(): pass\n", encoding="utf-8")
        self.output, self.store = self.root / "part.step", self.root / "store"
        env = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.store)})
        env.start()
        self.addCleanup(env.stop)
        self.tree = seed_result(self.output)
        self.ledger, self.broker = JobLedger(), Broker()

    def request(self, *, closure="same source", coalesce=True):
        return {"tool": "run", "argv": [str(self.model)], "cwd": str(self.root),
                "store_root": str(self.store), "closure": closure, "coalesce": coalesce,
                "dependency": coalesce}

    def feed(self):
        # Editing status remains an event/object read, even after completion.
        with mock.patch("cadgen.store.records.read_record", side_effect=AssertionError("model record read")), \
             mock.patch("cadgen.store.records.model_for_output", side_effect=AssertionError("output record read")):
            return preview_status(str(self.root), str(self.output), jobs=self.ledger.snapshot())

    def wait_until(self, predicate, message):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        self.fail(message)

    def exercise_follower(self, *, exit_code):
        worker = PreviewWorker(self.model, self.output, self.tree, exit_code=exit_code)
        worker_pool = mock.Mock()
        worker_pool.acquire.return_value = worker
        producer_conn, follower_conn = Connection(), Connection()
        claim_pending, allow_claim, follower_attached = (threading.Event() for _ in range(3))
        original_claim = self.broker.claim_entry

        def claim(*args, **kwargs):
            # The producer has reached its preview before the follower starts.
            if worker.preview_relayed.is_set():
                claim_pending.set()
                if not allow_claim.wait(5):
                    raise AssertionError("Test did not release the claim barrier")
            result = original_claim(*args, **kwargs)
            if not result[0]:
                follower_attached.set()
            return result

        with contextlib.ExitStack() as stack:
            for name, value in (("_POOL", worker_pool), ("_JOBS", self.ledger), ("_BROKER", self.broker)):
                stack.enter_context(mock.patch.object(server, name, value))
            stack.enter_context(mock.patch.object(server, "_log"))
            stack.enter_context(mock.patch.object(server, "_watch_client"))
            stack.enter_context(mock.patch.object(self.broker, "claim_entry", side_effect=claim))
            executor = stack.enter_context(concurrent.futures.ThreadPoolExecutor(max_workers=2))
            producer_future = executor.submit(server._handle_request, producer_conn, self.request())
            try:
                self.assertTrue(worker.preview_relayed.wait(3))
                producer_id = worker.request["job_id"]
                follower_future = executor.submit(server._handle_request, follower_conn, self.request())
                self.assertTrue(claim_pending.wait(3))
                # It is not yet known whether this request will own work. It
                # must not briefly replace the visible producer before claim.
                before_claim = self.feed()
                self.assertEqual(before_claim["request"], producer_id)
                self.assertEqual(before_claim["preview"]["tree"], self.tree)
                allow_claim.set()
                self.assertTrue(follower_attached.wait(3))
                self.assertFalse(follower_future.done())
                self.assertEqual(self.feed()["request"], producer_id)
                self.assertFalse(self.output.exists())
                self.wait_until(lambda: bool(follower_conn.frames), "late subscriber did not receive the source result")
                self.assertEqual(follower_conn.frames[0]["event"]["sourceResult"]["tree"], self.tree)

                worker.allow_save.set()
                self.assertTrue(worker.saved_relayed.wait(3))
                self.assertFalse(producer_future.done())
                self.assertFalse(follower_future.done(), "STEP publication alone cannot finish a follower")
                self.assertEqual(len(follower_conn.frames), 1)
                if exit_code == 0:
                    self.assertEqual(self.feed()["saved"]["tree"], self.tree)
                else:
                    self.assertNotIn("saved", self.feed())
                worker.allow_exit.set()
                producer_future.result(timeout=3)
                follower_future.result(timeout=3)
            finally:
                allow_claim.set()
                worker.allow_save.set()
                worker.allow_exit.set()

        worker_pool.acquire.assert_called_once_with(str(self.model), dependency=True)
        self.assertEqual(follower_conn.frames[-1], {"exit": exit_code})
        self.assertEqual(len(follower_conn.frames), 2)
        producer, follower = self.ledger.snapshot()
        self.assertEqual(producer["id"], producer_id)
        self.assertNotEqual(producer["id"], follower["id"])
        self.assertFalse(follower["editingProducer"])
        self.assertNotIn("previews", follower, "A follower never becomes the event producer")
        self.assertNotIn("savedResults", follower)
        self.assertEqual(follower["exit"], exit_code)
        self.assertIsNotNone(follower["finishedAt"])
        status = self.feed()
        self.assertEqual(status["request"], producer_id)
        self.assertEqual(status["revision"], before_claim["revision"])
        self.assertEqual(status["epoch"], before_claim["epoch"])
        self.assertEqual(status["state"], "failed" if exit_code else "done")
        if exit_code:
            self.assertEqual(status["error"], "save refused")
        self.ledger.observe(worker.event(99, preview={"output": str(self.output), "tree": "late"}))
        self.assertEqual(self.feed(), status, "Late producer events must remain fenced after completion")
        # A later real request must still advance ordering despite the retained
        # follower and all of the older producer's preview/saved events.
        latest = self.ledger.start(tool="run", subject=str(self.model), store_root=str(self.store))
        self.assertEqual(self.feed()["request"], latest["id"])
        self.assertNotIn("preview", self.feed())

    def test_successful_follower_keeps_preview_and_waits_for_full_owner_completion(self):
        self.exercise_follower(exit_code=0)

    def test_failed_owner_remains_the_visible_request_after_follower_completion(self):
        self.exercise_follower(exit_code=1)

    def test_coalescing_owner_advances_order_before_worker_admission(self):
        worker_pool = mock.Mock()

        def refused(*args, **kwargs):
            status = self.feed()
            self.assertEqual(status["state"], "submitted")
            self.assertIsNotNone(status["revision"], "The claim owner is an accepted editing request")
            raise server.pool_mod.MemoryAdmissionError("memory admission refused")

        worker_pool.acquire.side_effect = refused
        conn = Connection()
        with mock.patch.object(server, "_POOL", worker_pool), \
             mock.patch.object(server, "_JOBS", self.ledger), \
             mock.patch.object(server, "_BROKER", self.broker), \
             mock.patch.object(server, "_log"):
            server._handle_request(conn, self.request())
        self.assertEqual(self.feed()["error"], "memory admission refused")
        self.assertEqual(self.feed()["state"], "failed")
        self.assertEqual(self.broker.snapshot()["inflight"], 0)
        self.assertEqual(conn.frames[-1], {"exit": 1})
        worker_pool.release.assert_not_called()

    def test_disconnected_producer_continues_for_an_attached_consumer(self):
        worker = PreviewWorker(self.model, self.output, self.tree)
        worker_pool = mock.Mock()
        worker_pool.acquire.return_value = worker
        producer_conn, consumer_conn = DisconnectableConnection(), DisconnectableConnection()

        with mock.patch.object(server, "_POOL", worker_pool), \
             mock.patch.object(server, "_JOBS", self.ledger), \
             mock.patch.object(server, "_BROKER", self.broker), \
             mock.patch.object(server, "CLIENT_LIVENESS_INTERVAL_SECONDS", 0.02), \
             mock.patch.object(server, "_log"), \
             concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            producer = executor.submit(server._handle_request, producer_conn, self.request())
            self.assertTrue(worker.preview_relayed.wait(3))
            consumer = executor.submit(server._handle_request, consumer_conn, self.request())
            self.wait_until(lambda: self.broker.snapshot()["coalesced"] == 1, "consumer never attached")

            producer_conn.disconnected.set()
            self.assertTrue(producer_conn.failed_send.wait(3), "producer disconnect was not observed")
            self.assertFalse(worker.killed, "canonical work was killed despite its attached consumer")
            worker.allow_save.set()
            worker.allow_exit.set()
            producer.result(timeout=3)
            consumer.result(timeout=3)

        self.assertFalse(worker.killed)
        self.assertEqual(consumer_conn.frames[-1], {"exit": 0})
        worker_pool.release.assert_called_once_with(worker, healthy=True)
        self.assertEqual(self.broker.snapshot()["inflight"], 0)

    def test_disconnected_consumer_does_not_cancel_the_active_producer(self):
        worker = PreviewWorker(self.model, self.output, self.tree)
        worker_pool = mock.Mock()
        worker_pool.acquire.return_value = worker
        producer_conn, consumer_conn = DisconnectableConnection(), DisconnectableConnection()

        with mock.patch.object(server, "_POOL", worker_pool), \
             mock.patch.object(server, "_JOBS", self.ledger), \
             mock.patch.object(server, "_BROKER", self.broker), \
             mock.patch.object(server, "CLIENT_LIVENESS_INTERVAL_SECONDS", 0.02), \
             mock.patch.object(server, "_log"), \
             concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            producer = executor.submit(server._handle_request, producer_conn, self.request())
            self.assertTrue(worker.preview_relayed.wait(3))
            consumer = executor.submit(server._handle_request, consumer_conn, self.request())
            self.wait_until(lambda: self.broker.snapshot()["coalesced"] == 1, "consumer never attached")

            consumer_conn.disconnected.set()
            consumer.result(timeout=3)
            self.assertFalse(worker.killed, "one subscriber canceled its producer's canonical work")
            self.assertEqual(self.broker.snapshot()["inflight"], 1)
            worker.allow_save.set()
            worker.allow_exit.set()
            producer.result(timeout=3)

        self.assertFalse(worker.killed)
        worker_pool.release.assert_called_once_with(worker, healthy=True)


if __name__ == "__main__":
    unittest.main()
