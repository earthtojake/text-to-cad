"""The broker: job slots -- work under way first, then FIFO -- that a waiting parent gives
back and a nested build shares, and in-flight coalescing.

The slots are driven through a real broker served on a private address over the real
transport, in threads, so the lease semantics (a slot is a connection; closing it
releases) are the ones production uses. The in-flight registry is the daemon's own
object, driven as ``server._handle_request`` drives it.
"""

from __future__ import annotations

import os
import threading
import time
import unittest
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.daemon import broker  # noqa: E402
from tests.python.support.broker import PrivateBroker  # noqa: E402


class PrivateBrokerFixture(unittest.TestCase):
    LIMIT = 2

    def setUp(self):
        self.private = PrivateBroker(limit=self.LIMIT)
        self.addCleanup(self.private.close)
        self.enterContext(self.private.served())

    def _settle(self, predicate, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate(self.private.broker.snapshot()):
                return
            time.sleep(0.01)
        self.fail(f"broker never reached the expected state: {self.private.broker.snapshot()}")


@unittest.skipUnless(os.name == "posix", "POSIX listeners own a socket filesystem entry")
class Slots(PrivateBrokerFixture):
    def test_a_slot_is_granted_and_released_by_closing(self):
        lease = broker.acquire_slot("a")
        self.assertIsNotNone(lease)
        self.assertEqual(self.private.broker.snapshot()["running"], 1)
        lease.release()
        self._settle(lambda s: s["running"] == 0)

    def test_the_limit_holds_and_the_queue_is_fifo(self):
        held = [broker.acquire_slot(f"h{i}") for i in range(2)]
        order: list[str] = []
        queued_seen = threading.Event()

        def waiter(name: str) -> None:
            lease = broker.acquire_slot(name, on_queued=queued_seen.set)
            order.append(name)
            lease.release()

        threads = []
        for name in ("first", "second", "third"):
            thread = threading.Thread(target=waiter, args=(name,))
            thread.start()
            threads.append(thread)
            self._settle(lambda s, n=len(threads): s["queued"] == n)
        self.assertTrue(queued_seen.wait(2.0), "a queued requester was never told it was queued")
        self.assertEqual(self.private.broker.snapshot()["running"], 2, "the limit was exceeded")
        # Free ONE slot. The broker grants strictly in queue order, but the
        # waiters record their turn client-side, after the grant crosses the
        # socket; with two slots freed at once, two grants land together and
        # the appends race. With one slot the grants cascade -- each waiter
        # releases only after it has recorded its turn -- so the order seen
        # here is the broker's order and nothing else.
        held[0].release()
        for thread in threads:
            thread.join(timeout=10)
        held[1].release()
        self.assertEqual(order, ["first", "second", "third"])
        self.assertLessEqual(self.private.broker.snapshot()["peakRunning"], 2)

    def test_work_under_way_goes_ahead_of_jobs_not_yet_started(self):
        """A slot asked for to continue work under way -- an artifact job something waits on
        -- is granted before every job not yet started, in order among themselves."""
        held = [broker.acquire_slot(f"h{i}") for i in range(2)]
        order: list[str] = []

        def waiter(name: str, first: bool) -> None:
            lease = broker.acquire_slot(name, first=first)
            order.append(name)
            lease.release()

        threads = []
        for name, first in (("new1", False), ("display1", True), ("new2", False), ("display2", True)):
            thread = threading.Thread(target=waiter, args=(name, first))
            thread.start()
            threads.append(thread)
            self._settle(lambda s, n=len(threads): s["queued"] == n)
        # One slot freed: the grants cascade one at a time, in the broker's order.
        held[0].release()
        for thread in threads:
            thread.join(timeout=10)
        held[1].release()
        self.assertEqual(order, ["display1", "display2", "new1", "new2"])

    def test_a_block_entered_while_this_thread_holds_a_slot_runs_in_that_slot(self):
        # A child model's build inside its parent's body: no second slot, no queue, and
        # leaving the nested block keeps the parent's.
        with broker.held("parent") as parent:
            self.assertIsNotNone(parent)
            with broker.held("child") as child:
                self.assertIs(child, parent)
                self.assertEqual(self.private.broker.snapshot()["running"], 1)
            self.assertIs(broker.current_lease(), parent, "leaving the nested block released the parent's slot")
            self.assertEqual(self.private.broker.snapshot()["running"], 1)
        self._settle(lambda s: s["running"] == 0)

    def test_a_yielded_slot_is_taken_back_ahead_of_jobs_not_yet_started(self):
        other = broker.acquire_slot("other")
        order: list[str] = []
        with broker.held("parent"):
            with broker.yielded():
                child = broker.acquire_slot("child")
                waiting = threading.Thread(target=lambda: (broker.acquire_slot("new").release(), order.append("new")))
                waiting.start()
                self._settle(lambda s: s["queued"] == 1)

                def release_child_once_the_parent_asks() -> None:
                    self._settle(lambda s: s["queued"] == 2)
                    child.release()

                # The child's slot comes free once the parent asks for its own back: the
                # parent is granted it, and the job queued before it waits.
                releaser = threading.Thread(target=release_child_once_the_parent_asks)
                releaser.start()
            releaser.join(timeout=10)
            order.append("parent")
            self.assertEqual(self.private.broker.snapshot()["queued"], 1, "the new job still waits")
        waiting.join(timeout=10)
        other.release()
        self.assertEqual(order, ["parent", "new"])

    def test_yielded_gives_the_slot_back_for_the_wait(self):
        other = broker.acquire_slot("other")
        with broker.held("parent") as lease:
            self.assertIsNotNone(lease)
            self.assertEqual(self.private.broker.snapshot()["running"], 2)
            with broker.yielded():
                self._settle(lambda s: s["running"] == 1)
                # A third party can take the slot the parent gave up.
                third = broker.acquire_slot("child")
                self.assertEqual(self.private.broker.snapshot()["running"], 2)
                third.release()
                self._settle(lambda s: s["running"] == 1)
            self.assertEqual(self.private.broker.snapshot()["running"], 2, "the parent did not reacquire")
        other.release()

    def test_a_queued_requester_that_leaves_never_takes_a_slot(self):
        held = [broker.acquire_slot(f"h{i}") for i in range(2)]
        conn = broker._open({"kind": "slot", "op": "acquire", "label": "leaver"})
        self._settle(lambda s: s["queued"] == 1)
        conn.close()
        for lease in held:
            lease.release()
        self._settle(lambda s: s["running"] == 0 and s["queued"] == 0)

    def test_no_broker_means_no_limit_and_no_error(self):
        # A build with no daemon: its body and its pool jobs run on its own threads.
        with mock.patch.object(broker, "_endpoint", return_value=None):
            with broker.held("free") as lease:
                self.assertIsNone(lease)
                with broker.yielded():
                    pass
        self.assertEqual(self.private.broker.snapshot()["granted"], 0)

    def test_the_limit_is_the_core_count_unless_overridden(self):
        with mock.patch.dict(os.environ, {"CADGEN_JOBS": ""}):
            self.assertEqual(broker.job_limit(), max(1, os.cpu_count() or 1))
        with mock.patch.dict(os.environ, {"CADGEN_JOBS": "3"}):
            self.assertEqual(broker.job_limit(), 3)
        with mock.patch.dict(os.environ, {"CADGEN_JOBS": "0"}):
            self.assertEqual(broker.job_limit(), 1)


class Coalescing(unittest.TestCase):
    """The in-flight registry, for the jobs the daemon coalesces: a compile of a
    document's bytes (an artifact request's typed entries: test_daemon_artifacts)."""

    def setUp(self):
        self.registry = broker.Broker(limit=4)

    def test_identical_source_in_flight_is_joined_not_rebuilt(self):
        owns, mine = self.registry.claim_entry("/m/leaf.step", "sha-1")
        self.assertTrue(owns)
        owns, theirs = self.registry.claim_entry("/m/leaf.step", "sha-1")
        self.assertFalse(owns)
        self.assertIs(theirs, mine)
        self.assertEqual(self.registry.snapshot()["coalesced"], 1)
        _result, done, _code = self.registry.wait_update(theirs, result_seen=False, timeout=0.01)
        self.assertFalse(done, "the attached party was released before the job finished")
        self.registry.finish_entry(mine, 1, error="the body is wrong on purpose")
        _result, done, code = self.registry.wait_update(theirs, result_seen=False)
        self.assertEqual((done, code), (True, 1))
        self.assertEqual(theirs["error"], "the body is wrong on purpose", "the attached party gets the owner's reason")
        self.registry.detach(theirs)
        self.assertEqual(self.registry.snapshot()["inflight"], 0)

    def test_a_different_closure_or_store_is_a_different_job(self):
        owns, first = self.registry.claim_entry("/m/leaf.step", "sha-1", store_root="/store/first")
        self.assertTrue(owns)
        for closure, store in (("sha-2", "/store/first"), ("sha-1", "/store/second")):
            owns, entry = self.registry.claim_entry("/m/leaf.step", closure, store_root=store)
            self.assertTrue(owns, (closure, store))
            self.assertIsNot(entry, first)
            self.registry.finish_entry(entry, 0)
        self.registry.finish_entry(first, 0)
        self.assertEqual(self.registry.snapshot()["coalesced"], 0)

    def test_a_finished_job_is_never_joined_later(self):
        owns, first = self.registry.claim_entry("/m/leaf.step", "sha-1")
        self.registry.finish_entry(first, 0)
        self.assertEqual(self.registry.snapshot()["inflight"], 0)
        owns, again = self.registry.claim_entry("/m/leaf.step", "sha-1")
        self.assertTrue(owns, "coalescing looked into the past")
        self.assertIsNot(again, first)
        self.registry.finish_entry(again, 0)


if __name__ == "__main__":
    unittest.main()
