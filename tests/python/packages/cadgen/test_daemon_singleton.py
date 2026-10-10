"""One daemon per address, one spawning client, one authkey.

Twenty clients starting at once used to start twenty daemons; the losers' probes
against a backlog-8 listener were refused, read as a stale socket, and unlinked
the winner's live address. These pin the three pieces that replaced the probe:
the SingletonLock, the spawn election, and the linked authkey -- and that a stale
daemon hands its lock over before it tells a client to restart.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
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
                address = str(Path(tmp) / "daemon.sock")
                with ThreadPoolExecutor(max_workers=20) as pool:
                    keys = list(pool.map(lambda _: transport.ensure_authkey(address), range(20)))
                self.assertEqual(len(set(keys)), 1, "clients hold different secrets")
                self.assertEqual(keys[0], transport.read_authkey(address))
                leftovers = [p for p in Path(tmp).iterdir() if p.name.endswith(".tmp")]
                self.assertEqual(leftovers, [], "temp key files were left behind")

    def test_private_addresses_have_private_keys(self):
        with tempfile.TemporaryDirectory(prefix="cadgen-key-") as tmp:
            with mock.patch.object(transport, "state_dir", lambda: Path(tmp)):
                left = str(Path(tmp) / "same.sock")
                right = str(Path(tmp) / "same.other")
                left_key = transport.ensure_authkey(left)
                right_key = transport.ensure_authkey(right)
                self.assertNotEqual(left_key, right_key)
                self.assertEqual(transport.read_authkey(left), left_key)
                self.assertEqual(transport.read_authkey(right), right_key)
                self.assertNotEqual(transport._authkey_path(left), transport._authkey_path(right))
                self.assertTrue(transport._authkey_path(left).is_file())
                self.assertTrue(transport._authkey_path(right).is_file())

    def test_an_existing_empty_key_never_returns_an_unpublished_secret(self):
        with tempfile.TemporaryDirectory(prefix="cadgen-key-") as tmp:
            with mock.patch.object(transport, "state_dir", lambda: Path(tmp)):
                address = str(Path(tmp) / "daemon.sock")
                transport._authkey_path(address).touch()
                with mock.patch.object(transport.time, "sleep"):
                    with self.assertRaisesRegex(OSError, "empty or unreadable"):
                        transport.ensure_authkey(address)


class BindTest(unittest.TestCase):
    def test_a_daemon_that_cannot_take_the_lock_stands_down_without_touching_the_address(self):
        held = transport.SingletonLock(Path(tempfile.mkdtemp(prefix="cadgen-bind-")) / "x.lock")
        self.assertTrue(held.acquire())
        self.addCleanup(held.release)
        with mock.patch.object(transport, "daemon_lock", lambda key: transport.SingletonLock(held.path)), \
                mock.patch.object(transport, "clear_address") as clear, \
                mock.patch.object(transport, "ensure_authkey") as ensure, \
                mock.patch.object(server, "_log"):
            self.assertIsNone(server._bind("/tmp/does-not-matter.sock"))
        clear.assert_not_called()
        ensure.assert_not_called()

    def test_the_lock_holder_sweeps_a_leftover_address_and_binds(self):
        tmp = Path(tempfile.mkdtemp(prefix="cadgen-bind-"))
        lock = transport.SingletonLock(tmp / "x.lock")
        created = {}

        class _Server:
            def __init__(self, address, authkey, backlog, on_authentication_error):
                created["args"] = (address, backlog)
                created["repair"] = on_authentication_error

        with mock.patch.object(transport, "daemon_lock", lambda key: lock), \
                mock.patch.object(transport, "address_is_stale", lambda a: True), \
                mock.patch.object(transport, "clear_address") as clear, \
                mock.patch.object(transport, "ensure_authkey", return_value=b"key") as ensure, \
                mock.patch.object(transport, "publish_authkey") as publish, \
                mock.patch.object(transport, "Server", _Server), \
                mock.patch.object(server, "_log"):
            self.assertIsNotNone(server._bind("/tmp/leftover.sock"))
            created["repair"]()
        clear.assert_called_once_with("/tmp/leftover.sock")
        ensure.assert_called_once_with("/tmp/leftover.sock")
        self.assertEqual(created["args"][1], 128)
        self.assertTrue(lock.held, "the daemon keeps the lock for its life")
        publish.assert_called_once_with("/tmp/leftover.sock", b"key")
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
                mock.patch.object(client, "_reap_detached") as reap, \
                mock.patch.object(client, "_connect", fake_connect), \
                mock.patch.object(client, "daemon_identity", lambda: "id"):
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _: client._connect_or_spawn("/tmp/x.sock"), range(8)))
        self.assertEqual(results, ["channel"] * 8)
        self.assertEqual(len(spawns), 1, f"expected one spawn, got {len(spawns)}")
        reap.assert_called_once_with(mock.ANY)


class RestartHandoverTest(unittest.TestCase):
    """A stale daemon gives up its lock BEFORE it tells the client to restart.

    The client respawns at once. The stale daemon used to clear its address, reply,
    and hold the lock through its pool shutdown (about half a second per warm worker),
    so the respawned daemon stood down and the address was left with no daemon: the
    CAD Viewer's geometry request, which has no cold path, failed.
    """

    def test_the_lock_is_free_when_a_client_is_told_to_restart(self):
        tmp = Path(tempfile.mkdtemp(prefix="cgr-", dir=None if os.name == "nt" else "/tmp"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        address = rf"\\.\pipe\cadgen-handover-{os.getpid()}" if os.name == "nt" else str(tmp / "d.sock")
        listening, teardown = threading.Event(), threading.Event()

        class _Pool:
            """No workers, and a teardown that lasts until the test has looked."""

            def ensure_spares(self):
                listening.set()

            def unbind_idle(self):
                pass

            def shutdown(self):
                teardown.wait(30)

        stale = threading.Thread(target=server.serve, daemon=True)
        with mock.patch.dict(os.environ, {"CADGEN_DAEMON_SOCKET": address, "CADGEN_DAEMON_STATE_DIR": str(tmp)}), \
                mock.patch.object(server, "_POOL", _Pool()), \
                mock.patch.object(server, "_DAEMON_LOCK", None), \
                mock.patch.object(server, "compute_version_token", return_value="stale"), \
                mock.patch.object(server.signal, "signal"), \
                mock.patch.object(server, "_log"):
            stale.start()
            try:
                self.assertTrue(listening.wait(30), "the stale daemon never bound")
                channel = transport.connect(address, transport.read_authkey(address))
                try:
                    channel.send(json.dumps({"tool": "run", "argv": [], "token": "current"}).encode("utf-8"))
                    self.assertEqual(json.loads(channel.recv(30.0)), {"restart": True})
                finally:
                    channel.close()
                successor = transport.daemon_lock(address)
                self.assertTrue(successor.acquire(), "the respawned daemon would stand down")
                successor.release()
            finally:
                teardown.set()
                stale.join(30)
                if server._DAEMON_LOCK is not None:
                    server._DAEMON_LOCK.release()


class OneTokenForOneCodeTest(unittest.TestCase):
    """A checkout carried a stale editable install's metadata (0.7.15) in site-packages and
    a wheel build's egg-info (0.7.19) under ``src``. The daemon, with ``src`` first on its
    path, read one; a client without it read the other; every daemon retired on its first
    request and the next computed the same token: a strict request respawned daemons until
    it timed out. The token is the version declared beside the code, so the two read the
    same files and agree."""

    def _tree(self, *, checkout: bool) -> Path:
        root = Path(tempfile.mkdtemp(prefix="cgv-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        if checkout:
            (root / "pyproject.toml").write_text('[project]\nname = "cadgen"\nversion = "1.2.3"\n', encoding="utf-8")
            site = root / "src"
            (site / "cadgen.egg-info").mkdir(parents=True)
            (site / "cadgen.egg-info" / "PKG-INFO").write_text("Name: cadgen\nVersion: 9.9.9\n", encoding="utf-8")
        else:
            site = root / "lib" / "site-packages"
            (site / "cadgen-4.5.6.dist-info").mkdir(parents=True)
        (site / "cadgen").mkdir(parents=True)
        (site / "cadgen" / "__init__.py").write_text("", encoding="utf-8")
        return site / "cadgen"

    def test_the_version_is_the_one_declared_beside_the_code(self):
        self.assertTrue(client.compute_version_token(self._tree(checkout=True)).startswith("1.2.3:"))
        installed = self._tree(checkout=False)
        self.assertTrue(client.compute_version_token(installed).startswith("4.5.6:"))
        # An install that failed midway left an older version's metadata: the newest written
        # names what is there, whatever the names sort as.
        stale = installed.parent / "cadgen-4.5.10.dist-info"
        stale.mkdir()
        os.utime(stale, (1, 1))
        self.assertTrue(client.compute_version_token(installed).startswith("4.5.6:"))


@unittest.skipIf(os.name == "nt", "a pipe name has no path to outgrow")
class DeepStateDirTest(unittest.TestCase):
    """A state directory too deep for a Unix socket (``CADGEN_DAEMON_STATE_DIR``, a deep
    ``TMPDIR``) left the daemon unable to bind, and every request with no cold path -- a
    mesh export -- failed with "could not accept the request". Its socket now goes in a
    short folder of this user's own; the key, the locks and the log stay where they were."""

    def setUp(self):
        tmp = Path(tempfile.mkdtemp(prefix="cgd-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.tmp = tmp
        self.deep = tmp / ("a-state-directory-too-deep-for-a-socket-" * 3)
        self.enterContext(mock.patch.dict(os.environ, {"CADGEN_DAEMON_STATE_DIR": str(self.deep)}))
        os.environ.pop("CADGEN_DAEMON_SOCKET", None)  # restored with the rest of the environment

    def test_only_the_socket_moves_and_every_client_finds_the_same_one(self):
        natural = self.deep / f"cadgen-daemon-v{transport.PROTOCOL}-id.sock"
        self.assertFalse(transport._fits(natural), "the premise: this path cannot be bound")
        address = transport.address_for("id")
        self.assertEqual(Path(address).parent, transport.short_folder())
        self.assertTrue(transport._fits(address))
        self.assertEqual(transport.address_for("id"), address)
        self.assertNotEqual(transport.address_for("other"), address)
        with mock.patch.dict(os.environ, {"CADGEN_DAEMON_STATE_DIR": str(self.deep / "elsewhere")}):
            self.assertNotEqual(transport.address_for("id"), address)
        self.assertEqual(transport._authkey_path(address).parent, self.deep)
        self.assertEqual(client.log_path(address).parent, self.deep)
        self.assertEqual(transport.daemon_lock(address).path.parent, self.deep)
        with mock.patch.dict(os.environ, {"CADGEN_DAEMON_STATE_DIR": str(self.tmp)}):
            self.assertEqual(transport.address_for("id"), str(self.tmp / f"cadgen-daemon-v{transport.PROTOCOL}-id.sock"))
            self.assertEqual(transport._authkey_path(transport.address_for("id")).parent, self.tmp)

    def test_the_short_folder_is_used_only_when_it_is_this_users_alone(self):
        import stat

        short = self.tmp / "short"
        self.enterContext(mock.patch.object(transport, "short_folder", lambda: short))
        address = str(short / "d.sock")
        transport.claim_folder(address, create=False)  # nothing there yet: no daemon, no error
        self.assertFalse(short.exists())
        transport.claim_folder(address, create=True)
        self.assertEqual(stat.S_IMODE(short.stat().st_mode), 0o700)
        short.chmod(0o755)
        transport.claim_folder(address, create=False)
        self.assertEqual(stat.S_IMODE(short.stat().st_mode), 0o700, "a folder of ours others can enter is closed")
        short.rmdir()
        # Another user's folder, as this user sees it: not a folder of its own. A file, or a
        # link to a folder, is the same refusal without needing a second account.
        (self.tmp / "real").mkdir()
        for planted in ("file", "link"):
            with self.subTest(planted=planted):
                if planted == "file":
                    short.write_text("", encoding="utf-8")
                else:
                    short.symlink_to(self.tmp / "real", target_is_directory=True)
                for create in (False, True):
                    with self.assertRaisesRegex(transport.AddressUnusable, "CADGEN_DAEMON_STATE_DIR"):
                        transport.claim_folder(address, create=create)
                short.unlink()

    def test_every_door_says_why_when_no_daemon_can_listen(self):
        short = self.tmp / "short"
        short.write_text("", encoding="utf-8")  # planted where the socket's folder belongs
        self.enterContext(mock.patch.object(transport, "short_folder", lambda: short))
        self.enterContext(mock.patch.dict(os.environ, {"CADGEN_DAEMON_SOCKET": str(short / "d.sock")}))
        self.enterContext(mock.patch.object(client, "_spawn_daemon", side_effect=AssertionError("spawned")))
        payload = {"tool": "step-compile", "prog": "cadgen step compile", "argv": ["x.step"], "token": "t"}
        chunks: list[str] = []
        self.assertIsNone(client._run_with_retry(payload, on_stream=chunks.append, strict=True))
        self.assertIn("is not a folder of this user's", "".join(chunks))
        self.assertIn("CADGEN_DAEMON_STATE_DIR", "".join(chunks))
        import io
        from contextlib import redirect_stderr

        err = io.StringIO()
        with redirect_stderr(err):
            self.assertIsNone(client._run_with_retry(payload))
        self.assertIn("CADGEN_DAEMON_STATE_DIR", err.getvalue())
        self.assertIn("Running this in this process", err.getvalue())
        self.assertIsNone(client.status())

    def test_a_daemon_in_a_deep_state_dir_binds_its_short_address_and_serves(self):
        address = client.daemon_address()
        self.assertEqual(Path(address).parent, transport.short_folder())
        listening, stopped = threading.Event(), threading.Event()

        class _Pool:
            def ensure_spares(self):
                listening.set()

            def unbind_idle(self):
                pass

            def snapshot(self):
                return {"workers": []}

            def shutdown(self):
                stopped.set()

        daemon = threading.Thread(target=server.serve, daemon=True)
        with mock.patch.object(server, "_POOL", _Pool()), \
                mock.patch.object(server, "_DAEMON_LOCK", None), \
                mock.patch.object(server.signal, "signal"), \
                mock.patch.object(server, "_log"):
            daemon.start()
            try:
                self.assertTrue(listening.wait(30), "the daemon never bound")
                status = client.status()
                self.assertIsNotNone(status, "a client could not reach the daemon")
                self.assertEqual(status["socket"], address)
                self.assertTrue(transport.read_authkey(address))
                self.assertTrue((self.deep / (Path(address).name + ".key")).is_file())
            finally:
                # A request from other code: the daemon retires, releasing its address.
                with contextlib.suppress(OSError):
                    channel = transport.connect(address, transport.read_authkey(address) or b"")
                    try:
                        channel.send(json.dumps({"token": "retire"}).encode("utf-8"))
                        channel.recv(30.0)
                    finally:
                        channel.close()
                daemon.join(30)
                if server._DAEMON_LOCK is not None:
                    server._DAEMON_LOCK.release()
        self.assertFalse(daemon.is_alive())
        self.assertFalse(Path(address).exists(), "the daemon left its socket behind")


if __name__ == "__main__":
    unittest.main()
