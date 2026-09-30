"""The broker: FIFO job slots that a waiting parent gives back, and in-flight coalescing.

Driven through a real private broker over the real transport, in threads, so the lease
semantics (a slot is a connection; closing it releases) are the ones production uses.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import textwrap
import threading
import time
import unittest
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.daemon import broker  # noqa: E402


@unittest.skipUnless(os.name == "posix", "POSIX listeners own a socket filesystem entry")
class PrivateBrokerCleanup(unittest.TestCase):
    def test_delayed_accept_owner_keeps_socket_until_listener_disposal(self):
        entered, native_done, release = threading.Event(), threading.Event(), threading.Event()
        original_accept = broker.transport.mpc.Listener.accept

        def delayed_accept(listener):
            entered.set()
            try:
                return original_accept(listener)
            finally:
                native_done.set()
                if not release.wait(5):
                    raise TimeoutError("test did not release the accept owner")

        with mock.patch.object(broker.transport.mpc.Listener, "accept", new=delayed_accept):
            private = broker.PrivateBroker(limit=1)
            # Capture the stdlib unlink receipt to check both its active lifetime
            # and its idempotence after the accept owner disposes the listener.
            finalizer = private._server._listener._listener._unlink
            try:
                self.assertTrue(entered.wait(2), "accept did not begin")
                private.close()
                private.close()
                self.assertTrue(native_done.wait(2), "close did not wake native accept")
                self.assertTrue(private._thread.is_alive(), "accept owner was not held")
                self.assertTrue(Path(private.address).exists(), "broker unlinked the listener's live socket")
                self.assertTrue(finalizer.still_active())
            finally:
                release.set()
                private.close()
                private._thread.join(2)
            self.assertFalse(private._thread.is_alive())
            self.assertFalse(Path(private.address).exists())
            self.assertFalse(finalizer.still_active())
            self.assertIsNone(finalizer())

    def test_process_exit_finalizes_socket_before_delayed_accept_owner(self):
        script = textwrap.dedent("""
            import threading
            from cadgen.daemon import broker, transport

            entered = threading.Event()
            native_done = threading.Event()
            parked = threading.Event()
            original_accept = transport.mpc.Listener.accept

            def delayed_accept(listener):
                entered.set()
                try:
                    return original_accept(listener)
                finally:
                    native_done.set()
                    parked.wait(30)

            transport.mpc.Listener.accept = delayed_accept
            private = broker.PrivateBroker(limit=1)
            assert entered.wait(2), 'accept did not begin'
            private.close()
            assert native_done.wait(2), 'close did not wake native accept'
            assert private._thread.is_alive(), 'accept owner was not held'
            print(private.address, flush=True)
            # Normal process exit runs multiprocessing's finalizers while the
            # daemon accept thread is still parked above.
        """)
        completed = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        address = completed.stdout.strip()
        self.assertTrue(address, "child did not report its owned socket")
        self.addCleanup(broker.transport.clear_address, address)
        self.assertEqual(completed.stderr, "", "process-exit finalizer wrote a traceback")
        self.assertFalse(Path(address).exists())


class PrivateBrokerFixture(unittest.TestCase):
    def setUp(self):
        self.private = broker.PrivateBroker(limit=self.LIMIT)
        self.addCleanup(self.private.close)
        patcher = mock.patch.dict(os.environ, self.private.env())
        patcher.start()
        self.addCleanup(patcher.stop)

    LIMIT = 1


class Slots(PrivateBrokerFixture):
    LIMIT = 2

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
        with mock.patch.dict(os.environ, {broker.BROKER_ADDRESS_VAR: "", broker.BROKER_KEY_VAR: ""}):
            os.environ.pop(broker.BROKER_ADDRESS_VAR)
            os.environ.pop(broker.BROKER_KEY_VAR)
            os.environ.pop("CADGEN_DAEMON_CHILD", None)
            with broker.held("free") as lease:
                self.assertIsNone(lease)
                with broker.yielded():
                    pass

    def test_the_limit_is_the_core_count_unless_overridden(self):
        with mock.patch.dict(os.environ, {"CADGEN_JOBS": ""}):
            self.assertEqual(broker.job_limit(), max(1, os.cpu_count() or 1))
        with mock.patch.dict(os.environ, {"CADGEN_JOBS": "3"}):
            self.assertEqual(broker.job_limit(), 3)
        with mock.patch.dict(os.environ, {"CADGEN_JOBS": "0"}):
            self.assertEqual(broker.job_limit(), 1)

    def _settle(self, predicate, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate(self.private.broker.snapshot()):
                return
            time.sleep(0.01)
        self.fail(f"broker never reached the expected state: {self.private.broker.snapshot()}")


class Coalescing(PrivateBrokerFixture):
    LIMIT = 4

    def test_late_subscriber_gets_exact_source_result_before_exit(self):
        mine = broker.claim_inflight("/m/leaf.py::leaf", "sha-1")
        event = {"sourceResult": {"model": "/m/leaf.py::leaf", "tree": "immutable-source"}}
        broker.report_result(mine[1], event)
        theirs = broker.claim_inflight("/m/leaf.py::leaf", "sha-1")
        ready = threading.Event()
        results = []
        exits = []

        def receive(event):
            results.append(event)
            ready.set()

        thread = threading.Thread(target=lambda: exits.append(broker.wait_attached(theirs[1], on_event=receive)))
        thread.start()
        try:
            self.assertTrue(ready.wait(3))
            self.assertEqual(results, [event])
            self.assertEqual(exits, [])
        finally:
            broker.report_done(mine[1], 1)
            thread.join(5)
        self.assertEqual(exits, [1])

    def test_different_stores_do_not_share_source_results(self):
        first = broker.claim_inflight("/m/leaf.py", "sha-1", store_root="/store/first")
        second = broker.claim_inflight("/m/leaf.py", "sha-1", store_root="/store/second")
        self.assertEqual((first[0], second[0]), ("yours", "yours"))
        broker.report_done(first[1], 0)
        broker.report_done(second[1], 0)

    def test_identical_source_in_flight_is_joined_not_rebuilt(self):
        mine = broker.claim_inflight("/m/leaf.py", "sha-1")
        self.assertEqual(mine[0], "yours")
        theirs = broker.claim_inflight("/m/leaf.py", "sha-1")
        self.assertEqual(theirs[0], "attached")
        result: dict = {}

        def follow() -> None:
            result["exit"] = broker.wait_attached(theirs[1])

        thread = threading.Thread(target=follow)
        thread.start()
        time.sleep(0.1)
        self.assertTrue(thread.is_alive(), "the attached party returned before the job finished")
        broker.report_done(mine[1], 0)
        thread.join(timeout=10)
        self.assertEqual(result["exit"], 0)
        self.assertEqual(self.private.broker.snapshot()["coalesced"], 1)

    def test_a_different_closure_is_a_different_job(self):
        first = broker.claim_inflight("/m/leaf.py", "sha-1")
        second = broker.claim_inflight("/m/leaf.py", "sha-2")
        self.assertEqual((first[0], second[0]), ("yours", "yours"))
        broker.report_done(first[1], 0)
        broker.report_done(second[1], 0)

    def test_a_finished_job_is_never_joined_later(self):
        first = broker.claim_inflight("/m/leaf.py", "sha-1")
        broker.report_done(first[1], 0)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and self.private.broker.snapshot()["inflight"]:
            time.sleep(0.01)
        again = broker.claim_inflight("/m/leaf.py", "sha-1")
        self.assertEqual(again[0], "yours", "coalescing looked into the past")
        broker.report_done(again[1], 0)

    def test_a_claimer_that_dies_releases_the_attached_with_a_failure(self):
        mine = broker.claim_inflight("/m/leaf.py", "sha-9")
        theirs = broker.claim_inflight("/m/leaf.py", "sha-9")
        mine[1].close()  # the claimer vanished without reporting
        self.assertEqual(broker.wait_attached(theirs[1]), 1)


if __name__ == "__main__":
    unittest.main()
