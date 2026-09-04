"""The pool's dispatch rule: a worker per model, an extra when it is busy, spares in reserve.

Nothing waits on another build and nothing is refused: the rule is bookkeeping, so it is
asserted against stub workers on identity and state, never on timing.
"""

from __future__ import annotations

import concurrent.futures
import os
import pathlib
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from cadgen.daemon import pool as pool_mod  # noqa: E402


class _StubWorker:
    """Stands in for a subprocess: the dispatch rule is about bookkeeping, not OCP."""

    _next_pid = 1000
    spawned = 0

    def __init__(self) -> None:
        _StubWorker._next_pid += 1
        _StubWorker.spawned += 1
        self.pid = _StubWorker._next_pid
        self.busy = False
        self.extra = False
        self.model = ""
        self.jobs_served = 0
        self.last_used = 0.0
        self.use_seq = next(pool_mod._USE_SEQUENCE)
        self.killed = False
        self._alive = True

    def alive(self) -> bool:
        return self._alive

    def kill(self) -> None:
        self.killed = True
        self._alive = False


def _settle(pool: pool_mod.Pool, timeout: float = 5.0) -> None:
    """Wait for the background spare refill to land."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pool.snapshot()["sparesPending"] == 0:
            return
        time.sleep(0.01)
    raise AssertionError("spare refill never settled")


class _PoolFixture(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(pool_mod, "Worker", _StubWorker)
        patcher.start()
        self.addCleanup(patcher.stop)
        _StubWorker.spawned = 0
        self.pool = pool_mod.Pool()
        self.addCleanup(self.pool.shutdown)

    def _spares(self, count: int):
        return mock.patch.dict(os.environ, {"CADGEN_DAEMON_SPARES": str(count)})


class Binding(_PoolFixture):
    def test_a_model_binds_a_worker_and_keeps_it(self):
        with self._spares(0):
            first = self.pool.acquire("/m/a.py")
            self.pool.release(first)
            again = self.pool.acquire("/m/a.py")
        self.assertIs(first, again, "sequential builds of one model must reuse its worker")
        self.assertEqual(first.model, "/m/a.py")
        self.assertFalse(first.extra)
        self.pool.release(again)
        self.assertEqual(again.jobs_served, 2)

    def test_two_models_never_share_a_worker(self):
        with self._spares(0):
            a = self.pool.acquire("/m/a.py")
            self.pool.release(a)
            b = self.pool.acquire("/m/b.py")
        self.assertIsNot(a, b)
        self.assertEqual({a.model, b.model}, {"/m/a.py", "/m/b.py"})
        self.pool.release(b)

    def test_a_busy_model_gets_an_extra_and_nobody_waits(self):
        with self._spares(0):
            primary = self.pool.acquire("/m/a.py")
            extra = self.pool.acquire("/m/a.py")
        self.assertIsNot(primary, extra)
        self.assertTrue(extra.extra)
        self.assertEqual(extra.model, "/m/a.py")
        self.assertEqual(self.pool.snapshot()["concurrent"], 1)
        self.pool.release(extra)
        self.pool.release(primary)

    def test_an_extra_returns_to_the_spare_set_when_its_job_ends(self):
        with self._spares(1):
            primary = self.pool.acquire("/m/a.py")
            _settle(self.pool)
            extra = self.pool.acquire("/m/a.py")
            _settle(self.pool)
            self.pool.release(extra)
            _settle(self.pool)
            snapshot = self.pool.snapshot()
        spares = [w for w in snapshot["workers"] if not w["model"]]
        self.assertEqual(len(spares), 1, snapshot)
        self.assertTrue(extra.killed or extra.model == "", "the extra neither returned nor left")
        self.pool.release(primary)

    def test_a_request_with_no_model_borrows_a_spare_without_binding_it(self):
        with self._spares(0):
            worker = self.pool.acquire("")
            self.assertEqual(worker.model, "")
            self.pool.release(worker)
            _settle(self.pool)
        bound = [w for w in self.pool.snapshot()["workers"] if w["model"]]
        self.assertEqual(bound, [], "a subject-less job bound a worker")

    def test_nothing_is_capped(self):
        with self._spares(0):
            held = [self.pool.acquire(f"/m/{i}.py") for i in range(40)]
        self.assertEqual(len({w.pid for w in held}), 40)
        for worker in held:
            self.pool.release(worker)

    def test_concurrent_acquire_never_hands_one_worker_to_two_callers(self):
        with self._spares(0):
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                got = list(executor.map(lambda i: self.pool.acquire(f"/m/{i % 3}.py"), range(24)))
        self.assertEqual(len({w.pid for w in got}), len(got), "a worker was handed out twice")
        for worker in got:
            self.pool.release(worker)


class Spares(_PoolFixture):
    def test_ensure_spares_fills_to_k_in_the_background(self):
        with self._spares(2):
            self.pool.ensure_spares()
            _settle(self.pool)
            self.assertEqual(self.pool.snapshot()["spares"], 2)
            self.assertEqual(self.pool.snapshot()["imports"], 2)

    def test_binding_a_spare_starts_a_replacement(self):
        with self._spares(2):
            self.pool.ensure_spares()
            _settle(self.pool)
            before = _StubWorker.spawned
            worker = self.pool.acquire("/m/a.py")
            _settle(self.pool)
            snapshot = self.pool.snapshot()
        self.assertEqual(worker.model, "/m/a.py")
        self.assertEqual(snapshot["spares"], 2, "the spare set was not refilled")
        self.assertEqual(_StubWorker.spawned, before + 1, "exactly one replacement")
        self.pool.release(worker)

    def test_a_model_with_no_worker_takes_a_spare_not_a_spawn(self):
        with self._spares(1):
            self.pool.ensure_spares()
            _settle(self.pool)
            spare_pid = next(w["pid"] for w in self.pool.snapshot()["workers"] if not w["model"])
            worker = self.pool.acquire("/m/a.py")
        self.assertEqual(worker.pid, spare_pid, "a warm spare was available and not used")
        self.pool.release(worker)

    def test_the_spare_set_never_exceeds_k(self):
        with self._spares(1):
            self.pool.ensure_spares()
            _settle(self.pool)
            primary = self.pool.acquire("/m/a.py")
            _settle(self.pool)
            extras = [self.pool.acquire("/m/a.py") for _ in range(3)]
            _settle(self.pool)
            for extra in extras:
                self.pool.release(extra)
            _settle(self.pool)
            self.assertLessEqual(self.pool.snapshot()["spares"], 1)
        self.pool.release(primary)


class Lifecycle(_PoolFixture):
    def test_a_crashed_worker_is_dropped_and_its_model_rebinds_fresh(self):
        with self._spares(0):
            worker = self.pool.acquire("/m/a.py")
            worker._alive = False
            self.pool.release(worker, healthy=False)
            replacement = self.pool.acquire("/m/a.py")
        self.assertIsNot(worker, replacement)
        self.assertEqual(self.pool.snapshot()["crashes"], 1)
        self.pool.release(replacement)

    def test_a_worker_is_recycled_after_n_jobs(self):
        with self._spares(0), mock.patch.dict(os.environ, {"CADGEN_DAEMON_RECYCLE": "2"}):
            first = self.pool.acquire("/m/a.py")
            self.pool.release(first)
            same = self.pool.acquire("/m/a.py")
            self.assertIs(first, same)
            self.pool.release(same)  # second job: recycled
            fresh = self.pool.acquire("/m/a.py")
        self.assertIsNot(first, fresh)
        self.assertTrue(first.killed)
        self.assertEqual(self.pool.snapshot()["recycles"], 1)
        self.pool.release(fresh)

    def test_bound_workers_are_never_idle_reaped(self):
        with self._spares(0):
            worker = self.pool.acquire("/m/a.py")
            self.pool.release(worker)
            worker.last_used = 0.0  # ages ago
            self.pool.reap_dead()
        self.assertFalse(worker.killed)
        self.assertEqual(len(self.pool.snapshot()["workers"]), 1)

    def test_shutdown_kills_everything(self):
        with self._spares(0):
            held = [self.pool.acquire(f"/m/{i}.py") for i in range(3)]
            for worker in held:
                self.pool.release(worker)
        self.pool.shutdown()
        self.assertTrue(all(w.killed for w in held))
        self.assertEqual(self.pool.snapshot()["workers"], [])


class IdleUnbind(unittest.TestCase):
    """A bound worker idle for ten minutes returns to spare; nothing else is ever unbound."""

    def setUp(self) -> None:
        patcher = mock.patch.object(pool_mod, "Worker", _StubWorker)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.now = [1000.0]
        self.pool = pool_mod.Pool(clock=lambda: self.now[0])
        self.addCleanup(self.pool.shutdown)

    def test_a_bound_worker_idle_past_the_timer_becomes_a_spare(self):
        with mock.patch.dict(os.environ, {"CADGEN_DAEMON_SPARES": "1", "CADGEN_DAEMON_IDLE_UNBIND": "600"}):
            worker = self.pool.acquire("/m/a.py")
            self.pool.release(worker)
            _settle(self.pool)
            self.now[0] += 599.0
            self.pool.unbind_idle()
            self.assertEqual(worker.model, "/m/a.py", "unbound before the timer")
            self.now[0] += 2.0
            self.pool.unbind_idle()
        # The spare set already held K=1, so this one exits rather than growing it.
        self.assertTrue(worker.killed or worker.model == "")
        self.assertEqual(self.pool.snapshot()["unbinds"], 1)

    def test_an_unbound_worker_is_rebound_without_a_spawn(self):
        with mock.patch.dict(os.environ, {"CADGEN_DAEMON_SPARES": "1", "CADGEN_DAEMON_IDLE_UNBIND": "600"}):
            worker = self.pool.acquire("/m/a.py")
            self.pool.release(worker)
            _settle(self.pool)
            self.now[0] += 601.0
            self.pool.unbind_idle()
            snapshot = self.pool.snapshot()
            # Unbound: either it is the spare now, or the spare set was already full and
            # it left. Either way there is exactly K warm and nothing bound.
            self.assertNotIn("/m/a.py", [w["model"] for w in snapshot["workers"]])
            self.assertEqual(snapshot["spares"], 1, snapshot)
            spare_pid = next(w["pid"] for w in snapshot["workers"] if not w["model"])
            again = self.pool.acquire("/m/b.py")
            self.assertEqual(again.pid, spare_pid, "a warm spare was available and a fresh worker was spawned instead")
            self.assertEqual(again.model, "/m/b.py")
            self.pool.release(again)

    def test_busy_and_recently_used_workers_are_left_alone(self):
        with mock.patch.dict(os.environ, {"CADGEN_DAEMON_SPARES": "0", "CADGEN_DAEMON_IDLE_UNBIND": "600"}):
            busy = self.pool.acquire("/m/a.py")
            idle = self.pool.acquire("/m/b.py")
            self.pool.release(idle)
            self.now[0] += 100.0
            self.pool.unbind_idle()
            self.assertEqual((busy.model, idle.model), ("/m/a.py", "/m/b.py"))
            self.now[0] += 600.0
            self.pool.unbind_idle()
            self.assertEqual(busy.model, "/m/a.py", "a busy worker was unbound")
            self.assertTrue(idle.model == "" or idle.killed, "the idle worker stayed bound")
        self.pool.release(busy)


class Status(_PoolFixture):
    def test_snapshot_reports_per_worker_model_busy_jobs_extra(self):
        with self._spares(0):
            primary = self.pool.acquire("/m/a.py")
            extra = self.pool.acquire("/m/a.py")
            self.pool.release(extra)
            snapshot = self.pool.snapshot()
        rows = {w["pid"]: w for w in snapshot["workers"]}
        self.assertEqual(rows[primary.pid], {"pid": primary.pid, "model": "/m/a.py", "busy": True, "extra": False, "jobs": 0})
        for key in ("spares", "imports", "concurrent", "jobs", "recycles", "crashes"):
            self.assertIn(key, snapshot)
        self.assertEqual(snapshot["concurrent"], 1)
        self.assertEqual(snapshot["jobs"], 1)
        self.pool.release(primary)


if __name__ == "__main__":
    unittest.main()
