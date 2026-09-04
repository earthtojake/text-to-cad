"""One daemon per address, one spawning client, one authkey.

Twenty clients starting at once used to start twenty daemons; the losers' probes
against a backlog-8 listener were refused, read as a stale socket, and unlinked
the winner's live address. These pin the three pieces that replaced the probe:
the process-lifetime SingletonLock, the spawn election, and the linked authkey.
"""

from __future__ import annotations

import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.daemon import client, server, transport  # noqa: E402


class SingletonLockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="cadgen-lock-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "d.lock"

    def test_the_second_holder_is_refused_until_the_first_releases(self):
        first = transport.SingletonLock(self.path)
        second = transport.SingletonLock(self.path)
        self.assertTrue(first.acquire())
        self.assertTrue(first.held)
        self.assertFalse(second.acquire(), "two holders of one singleton lock")
        first.release()
        self.assertFalse(first.held)
        self.assertTrue(second.acquire())
        second.release()

    def test_acquire_is_idempotent_for_the_holder(self):
        lock = transport.SingletonLock(self.path)
        self.assertTrue(lock.acquire())
        self.assertTrue(lock.acquire())
        lock.release()
        lock.release()  # a second release is a no-op, not an error


class AuthkeyTest(unittest.TestCase):
    def test_twenty_concurrent_creators_agree_on_one_key(self):
        with tempfile.TemporaryDirectory(prefix="cadgen-key-") as tmp:
            with mock.patch.object(transport, "state_dir", lambda: Path(tmp)):
                identity = "test-identity"
                with ThreadPoolExecutor(max_workers=20) as pool:
                    keys = list(pool.map(lambda _: transport.ensure_authkey(identity), range(20)))
                self.assertEqual(len(set(keys)), 1, "clients hold different secrets")
                self.assertEqual(keys[0], transport.read_authkey(identity))
                leftovers = [p for p in Path(tmp).iterdir() if p.name.endswith(".tmp")]
                self.assertEqual(leftovers, [], "temp key files were left behind")


class BindTest(unittest.TestCase):
    def test_a_daemon_that_cannot_take_the_lock_stands_down_without_touching_the_address(self):
        held = transport.SingletonLock(Path(tempfile.mkdtemp(prefix="cadgen-bind-")) / "x.lock")
        self.assertTrue(held.acquire())
        self.addCleanup(held.release)
        with mock.patch.object(transport, "daemon_lock", lambda key: transport.SingletonLock(held.path)), \
                mock.patch.object(transport, "clear_address") as clear, \
                mock.patch.object(server, "_log"):
            self.assertIsNone(server._bind("/tmp/does-not-matter.sock", b"key"))
        clear.assert_not_called()

    def test_the_lock_holder_sweeps_a_leftover_address_and_binds(self):
        tmp = Path(tempfile.mkdtemp(prefix="cadgen-bind-"))
        lock = transport.SingletonLock(tmp / "x.lock")
        created = {}

        class _Server:
            def __init__(self, address, authkey, backlog):
                created["args"] = (address, backlog)

        with mock.patch.object(transport, "daemon_lock", lambda key: lock), \
                mock.patch.object(transport, "address_is_stale", lambda a: True), \
                mock.patch.object(transport, "clear_address") as clear, \
                mock.patch.object(transport, "Server", _Server), \
                mock.patch.object(server, "_log"):
            self.assertIsNotNone(server._bind("/tmp/leftover.sock", b"key"))
        clear.assert_called_once_with("/tmp/leftover.sock")
        self.assertEqual(created["args"][1], 128)
        self.assertTrue(lock.held, "the daemon keeps the lock for its life")
        lock.release()


class SpawnElectionTest(unittest.TestCase):
    def test_concurrent_clients_spawn_exactly_one_daemon(self):
        tmp = Path(tempfile.mkdtemp(prefix="cadgen-elect-"))
        spawns = []
        up = threading.Event()
        lock_path = tmp / "spawn.lock"

        class _Proc:
            def poll(self):
                return None

        def fake_spawn(address):
            spawns.append(address)
            up.set()
            return _Proc()

        def fake_connect(address):
            if not up.is_set():
                raise OSError("no daemon")
            return "channel"

        with mock.patch.object(transport, "spawn_lock", lambda key: transport.SingletonLock(lock_path)), \
                mock.patch.object(client, "_spawn_daemon", fake_spawn), \
                mock.patch.object(client, "_connect", fake_connect), \
                mock.patch.object(client, "daemon_identity", lambda: "id"):
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _: client._connect_or_spawn("/tmp/x.sock"), range(8)))
        self.assertEqual(results, ["channel"] * 8)
        self.assertEqual(len(spawns), 1, f"expected one spawn, got {len(spawns)}")


if __name__ == "__main__":
    unittest.main()
