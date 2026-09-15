"""Memory admission counts retained parents, pending spawns and subprocesses."""

from __future__ import annotations

import concurrent.futures
import json
import os
import threading
import unittest
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.daemon import broker as broker_mod  # noqa: E402
from cadgen.daemon import client, memory, pool  # noqa: E402
from tests.python.packages.cadgen.test_daemon_pool import _StubWorker  # noqa: E402

MIB = memory.MIB


class Accounting(unittest.TestCase):
    def test_descendant_rss_is_attributed_once_to_its_worker(self):
        rows = {10: (1, 100), 11: (10, 200), 12: (11, 300),
                20: (1, 400), 21: (20, 500), 30: (1, 900)}
        self.assertEqual(memory.process_tree_bytes([10, 20], rows=rows), {10: 600, 20: 900})

    def test_cycles_and_missing_processes_do_not_hang_or_invent_rss(self):
        rows = {10: (1, 100), 11: (12, 200), 12: (11, 300)}
        self.assertEqual(memory.process_tree_bytes([10, 99], rows=rows), {10: 100})

    def test_policy_reserves_dependency_capacity_and_honors_explicit_zero(self):
        env = {key: "" for key in ("CADGEN_MEMORY_MB", "CADGEN_WORKER_MEMORY_MB",
                                  "CADGEN_DEPENDENCY_MEMORY_MB", "CADGEN_COMPONENT_MEMORY_MB")}
        with mock.patch.dict(os.environ, env), mock.patch.object(memory, "physical_memory_bytes", return_value=12 * 1024 * MIB):
            policy = memory.MemoryPolicy.from_environment()
            self.assertEqual(policy.limit_bytes, 12 * 1024 * MIB * 7 // 10)
            self.assertEqual(policy.dependency_bytes, policy.worker_bytes)
            with mock.patch.dict(os.environ, {"CADGEN_MEMORY_MB": "0"}):
                self.assertEqual(memory.MemoryPolicy.from_environment().limit_bytes, 0)

    def test_component_processes_fit_the_parent_reservation(self):
        policy = memory.MemoryPolicy(8192 * MIB, 2048 * MIB, 2048 * MIB, 384 * MIB)
        with mock.patch.object(memory.MemoryPolicy, "from_environment", return_value=policy):
            with mock.patch.object(memory, "process_tree_bytes", return_value={os.getpid(): 300 * MIB}):
                self.assertEqual(memory.component_worker_limit(8), 4)
                self.assertEqual(memory.component_worker_limit(2), 2)
            with mock.patch.object(memory, "process_tree_bytes", return_value={os.getpid(): 1900 * MIB}):
                self.assertEqual(memory.component_worker_limit(8), 1, "no extra process fits: run inline")


class Admission(unittest.TestCase):
    def setUp(self):
        self.patchers = [mock.patch.object(pool, "Worker", _StubWorker),
                         mock.patch.dict(os.environ, {"CADGEN_DAEMON_SPARES": "0"})]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.resident = {}
        self.policy = memory.MemoryPolicy(12 * MIB, 4 * MIB, 4 * MIB)
        self.pool = pool.Pool(policy=self.policy, memory_reader=lambda pids: {
            pid: self.resident.get(pid, 2 * MIB) for pid in pids
        })
        self.addCleanup(self.pool.shutdown)

    def test_root_admission_leaves_headroom_for_a_dependency(self):
        first = self.pool.acquire("a")
        second = self.pool.acquire("b")
        with self.assertRaises(pool.MemoryAdmissionError):
            self.pool.acquire("root-without-headroom")
        child = self.pool.acquire("child", dependency=True)
        self.assertEqual(self.pool.snapshot()["memory"]["chargedBytes"], 12 * MIB)
        self.assertTrue(all(w.busy and w.alive() for w in (first, second, child)))

    def test_three_level_dependency_can_progress_and_exhaustion_fails_without_evicting_parents(self):
        parent = self.pool.acquire("parent")
        child = self.pool.acquire("child", dependency=True)
        grandchild = self.pool.acquire("grandchild", dependency=True)
        with self.assertRaisesRegex(pool.MemoryAdmissionError, "active builds retain their geometry"):
            self.pool.acquire("too-deep", dependency=True)
        self.assertTrue(all(w.busy and not w.killed for w in (parent, child, grandchild)))

    def test_idle_worker_is_reclaimed_before_new_allocation(self):
        old = self.pool.acquire("old")
        self.pool.release(old)
        self.resident[old.pid] = 6 * MIB
        fresh = self.pool.acquire("new")
        self.assertTrue(old.killed)
        self.assertTrue(fresh.alive())
        self.assertEqual(self.pool.snapshot()["memoryReclaims"], 1)

    def test_dependency_pressure_reclaims_only_idle_state_and_keeps_the_parent(self):
        parent = self.pool.acquire("parent")
        idle = self.pool.acquire("idle")
        self.pool.release(idle)
        self.resident[idle.pid] = 6 * MIB

        child = self.pool.acquire("child", dependency=True)
        self.assertTrue(idle.killed)
        self.assertTrue(parent.busy and parent.alive() and not parent.killed)
        self.assertTrue(child.busy and child.alive())

    def test_oversized_idle_cache_can_be_replaced_with_a_fresh_worker(self):
        old = self.pool.acquire("model")
        self.pool.release(old)
        self.resident[old.pid] = 14 * MIB
        fresh = self.pool.acquire("model")
        self.assertIsNot(old, fresh)
        self.assertTrue(old.killed)
        self.assertFalse(fresh.extra)

    def test_known_oversized_worker_runs_alone_within_the_total_allowance(self):
        old = self.pool.acquire("model")
        self.pool.release(old)
        self.resident[old.pid] = 10 * MIB

        reused = self.pool.acquire("model")
        self.assertIs(old, reused)
        self.assertTrue(reused.busy and not reused.killed)

    def test_isolated_admission_uses_one_consistent_rss_snapshot(self):
        old = self.pool.acquire("model")
        self.pool.release(old)
        samples = iter((10 * MIB, 2 * MIB))
        calls = []

        def fluctuating_reader(pids):
            calls.append(tuple(pids))
            return {pid: next(samples) for pid in pids}

        self.pool._memory_reader = fluctuating_reader

        # Spare replenishment takes its own later policy snapshot; suppress it
        # here so this assertion is specifically about one admission decision.
        with mock.patch.object(self.pool, "ensure_spares"):
            reused = self.pool.acquire("model")

        self.assertIs(old, reused, "a second, drifting RSS sample evicted the admissible sole worker")
        self.assertTrue(reused.busy and not reused.killed)
        self.assertEqual(calls, [(old.pid,)])

    def test_configured_oversized_reservation_runs_alone_but_cannot_starve_a_child(self):
        isolated = pool.Pool(
            policy=memory.MemoryPolicy(6 * MIB, 4 * MIB, 4 * MIB),
            memory_reader=lambda pids: {pid: 2 * MIB for pid in pids},
        )
        self.addCleanup(isolated.shutdown)
        parent = isolated.acquire("parent")
        with self.assertRaisesRegex(pool.MemoryAdmissionError, "sole charge"):
            isolated.acquire("child", dependency=True)
        self.assertTrue(parent.busy and parent.alive() and not parent.killed)

    def test_reservation_larger_than_the_total_limit_fails_before_spawn(self):
        impossible = pool.Pool(
            policy=memory.MemoryPolicy(3 * MIB, 4 * MIB, 0),
            memory_reader=lambda _pids: {},
        )
        self.addCleanup(impossible.shutdown)
        before = _StubWorker._next_pid
        with self.assertRaisesRegex(pool.MemoryAdmissionError, "3 MiB total"):
            impossible.acquire("cannot-fit")
        self.assertEqual(before, _StubWorker._next_pid)

    def test_finished_oversized_worker_is_reclaimed_without_another_request(self):
        worker = self.pool.acquire("large")
        self.resident[worker.pid] = 10 * MIB
        self.pool.release(worker)
        self.assertNotIn(worker.pid, [entry["pid"] for entry in self.pool.snapshot()["workers"]])
        self.assertEqual(self.pool.snapshot()["memoryReclaims"], 1)

    def test_a_pending_spawn_keeps_its_reservation(self):
        entered, finish = threading.Event(), threading.Event()

        class StartingWorker(_StubWorker):
            def __init__(self):
                entered.set()
                if not finish.wait(5):
                    raise AssertionError("test never released the pending spawn")
                super().__init__()

        self.pool = pool.Pool(policy=memory.MemoryPolicy(8 * MIB, 4 * MIB, 4 * MIB),
                              memory_reader=lambda pids: {pid: 2 * MIB for pid in pids})
        self.addCleanup(self.pool.shutdown)
        with mock.patch.object(pool, "Worker", StartingWorker), concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(self.pool.acquire, "pending")
            try:
                self.assertTrue(entered.wait(2))
                # The pending spawn holds its reservation, so a second request
                # waits on it rather than overbooking.
                overbook = executor.submit(self.pool.acquire, "cannot-overbook")
                self.assertFalse(overbook.done())
            finally:
                finish.set()
            worker = future.result(timeout=5)
            # Once the spawn has landed nothing is in flight to release memory.
            with self.assertRaises(pool.MemoryAdmissionError):
                overbook.result(timeout=10)
        self.assertTrue(worker.busy)
        self.assertEqual(self.pool.snapshot()["memory"]["pendingWorkers"], 0)

    def test_admission_waits_for_builds_in_flight_instead_of_refusing(self):
        running = [1]
        waiting = pool.Pool(policy=memory.MemoryPolicy(12 * MIB, 4 * MIB, 4 * MIB),
                            memory_reader=lambda pids: {pid: 2 * MIB for pid in pids},
                            in_flight=lambda: running[0])
        self.addCleanup(waiting.shutdown)
        parent = waiting.acquire("parent")
        first = waiting.acquire("first", dependency=True)
        second = waiting.acquire("second", dependency=True)
        with concurrent.futures.ThreadPoolExecutor() as executor:
            third = executor.submit(waiting.acquire, "third", dependency=True)
            self.assertFalse(third.done())
            self.assertFalse(third.running() and third.done())
            waiting.release(first)  # a finished build hands its worker back
            child = third.result(timeout=5)
        self.assertTrue(child.busy and child.alive())
        self.assertTrue(parent.busy and second.busy)
        self.assertEqual(waiting.snapshot()["memoryRefusals"], 0)

    def test_retiring_rss_is_not_freed_before_process_exit(self):
        old = self.pool.acquire("old")
        self.pool.release(old)
        self.resident[old.pid] = 6 * MIB
        entered, finish = threading.Event(), threading.Event()

        def delayed_kill():
            entered.set()
            finish.wait(5)
            old._alive = False
            old.killed = True

        old.kill = delayed_kill
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(self.pool.acquire, "replacement")
            try:
                self.assertTrue(entered.wait(2))
                self.assertFalse(future.done(), "replacement was admitted while old RSS was still resident")
            finally:
                finish.set()
            fresh = future.result(timeout=5)
        self.assertTrue(fresh.busy and old.killed)

    def test_spare_replenishment_cannot_consume_dependency_reserve(self):
        with mock.patch.dict(os.environ, {"CADGEN_DAEMON_SPARES": "8"}):
            self.pool.ensure_spares()
            with self.pool._cv:
                self.assertLessEqual(self.pool._spares_pending * self.policy.worker_bytes,
                                     self.policy.limit_bytes - self.policy.dependency_bytes)
        # Joining is unnecessary: shutdown also covers workers arriving later.


class DependencyRequest(unittest.TestCase):
    def test_dependency_identity_is_independent_of_coalescing(self):
        with mock.patch.object(client, "compute_version_token", return_value="test"), \
             mock.patch.object(client, "forwarded_env", return_value={}):
            root = client._request_payload("run", ["a.py"], "/work", None, store_root="/cache")
            child = client._request_payload("run", ["b.py"], "/work", None,
                                            store_root="/cache", dependency=True)
        self.assertFalse(root["dependency"])
        self.assertTrue(child["dependency"])
        self.assertFalse(child["coalesce"])

    def test_run_nested_sets_dependency_without_a_closure(self):
        with mock.patch.dict(os.environ, {"CADGEN_DAEMON": "1"}), \
             mock.patch.object(client, "daemon_supported", return_value=True), \
             mock.patch.object(client, "_request_payload", return_value={}) as payload, \
             mock.patch.object(client, "_run_with_retry", return_value=0):
            self.assertEqual(client.run_nested("run", ["b.py"], "/work"), 0)
        self.assertTrue(payload.call_args.kwargs["dependency"])

    def test_server_returns_admission_failure_without_cold_fallback_or_worker_release(self):
        from cadgen.daemon import server

        frames = []
        conn = mock.Mock()
        conn.send.side_effect = lambda data: frames.append(json.loads(data))
        worker_pool = mock.Mock()
        reason = "active builds retain their geometry"
        worker_pool.acquire.side_effect = pool.MemoryAdmissionError(reason)
        ledger, broker = mock.Mock(), mock.Mock()
        job = {"id": "memory-refused"}
        ledger.start.return_value = job
        entry = {"token": "memory-refused"}
        broker.claim_entry.return_value = (True, entry)
        request = {"tool": "run", "argv": ["child.py"], "cwd": "/work",
                   "dependency": True, "closure": "abc", "coalesce": True}
        with mock.patch.object(server, "_POOL", worker_pool), \
             mock.patch.object(server, "_JOBS", ledger), \
             mock.patch.object(server, "_BROKER", broker), \
             mock.patch.object(server, "_log"):
            server._handle_request(conn, request)
        worker_pool.acquire.assert_called_once_with(os.path.realpath("/work/child.py"), dependency=True)
        worker_pool.release.assert_not_called()
        ledger.finish.assert_called_once_with(job, 1, error=reason)
        broker.finish_entry.assert_called_once_with(entry, 1)
        self.assertEqual(frames[-1], {"exit": 1})
        self.assertIn(reason, frames[0]["data"])
        self.assertFalse(any("workerDied" in frame or "restart" in frame for frame in frames))


class InflightOwnership(unittest.TestCase):
    def test_last_detach_atomically_retires_an_abandoned_entry(self):
        broker = broker_mod.Broker()
        owned, original = broker.claim_entry("part.py", "same")
        self.assertTrue(owned)
        attached, consumer = broker.claim_entry("part.py", "same")
        self.assertFalse(attached)
        self.assertIs(original, consumer)

        self.assertTrue(broker.abandon(original))
        self.assertTrue(broker.detach(consumer))
        self.assertTrue(broker.orphaned(original))
        replacement_owned, replacement = broker.claim_entry("part.py", "same")
        self.assertTrue(replacement_owned)
        self.assertIsNot(original, replacement)

        broker.finish_entry(original, 1)
        self.assertEqual(broker.snapshot()["inflight"], 1, "late old completion removed its replacement")
        broker.finish_entry(replacement, 0)
        self.assertEqual(broker.snapshot()["inflight"], 0)

    def test_one_consumer_detaching_does_not_retire_an_active_owner(self):
        broker = broker_mod.Broker()
        _owned, owner = broker.claim_entry("part.py", "same")
        _attached, consumer = broker.claim_entry("part.py", "same")
        self.assertFalse(broker.detach(consumer))
        self.assertFalse(broker.orphaned(owner))
        self.assertEqual(broker.snapshot()["inflight"], 1)
        broker.finish_entry(owner, 0)

    def test_one_of_two_consumers_detaching_keeps_abandoned_work_shared(self):
        broker = broker_mod.Broker()
        _owned, owner = broker.claim_entry("part.py", "same")
        _attached, first = broker.claim_entry("part.py", "same")
        _attached, second = broker.claim_entry("part.py", "same")

        self.assertTrue(broker.abandon(owner))
        self.assertFalse(broker.detach(first))
        self.assertFalse(broker.orphaned(owner))
        self.assertEqual(broker.snapshot()["inflight"], 1)
        self.assertTrue(broker.detach(second))
        self.assertTrue(broker.orphaned(owner))


if __name__ == "__main__":
    unittest.main()
