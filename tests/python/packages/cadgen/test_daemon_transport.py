"""Daemon channels have one close owner even when cancellation races cleanup."""

from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock
import uuid

from cadgen.daemon import client, transport
from cadgen.daemon.transport import Channel


class _BlockingCloseConnection:
    def __init__(self) -> None:
        self.close_entered = threading.Event()
        self.release_close = threading.Event()
        self.closed = threading.Event()
        self.close_calls = 0
        self._guard = threading.Lock()

    def close(self) -> None:
        with self._guard:
            self.close_calls += 1
        self.close_entered.set()
        self.release_close.wait(2)
        self.closed.set()


class _BlockingReceiveConnection:
    def __init__(self) -> None:
        self.receive_entered = threading.Event()
        self.closed = threading.Event()
        self.close_calls = 0

    def recv_bytes(self) -> bytes:
        self.receive_entered.set()
        if not self.closed.wait(2):
            raise TimeoutError("close did not unblock receive")
        raise OSError("connection closed")

    def close(self) -> None:
        self.close_calls += 1
        self.closed.set()


class ChannelCloseOwnershipTest(unittest.TestCase):
    def test_concurrent_close_has_one_underlying_owner_without_serializing_callers(self) -> None:
        connection = _BlockingCloseConnection()
        channel = Channel(connection)
        first = threading.Thread(target=channel.close)
        first.start()
        self.assertTrue(connection.close_entered.wait(1), "first close did not reach the connection")

        second_done = threading.Event()

        def close_again() -> None:
            channel.close()
            second_done.set()

        second = threading.Thread(target=close_again)
        second.start()
        try:
            self.assertTrue(second_done.wait(1), "duplicate close waited behind the blocking owner")
            self.assertEqual(connection.close_calls, 1)
        finally:
            connection.release_close.set()
            first.join(2)
            second.join(2)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())

    def test_close_unblocks_receive_and_repeated_close_is_idempotent(self) -> None:
        connection = _BlockingReceiveConnection()
        channel = Channel(connection)
        received: list[bytes | None] = []
        receiver = threading.Thread(target=lambda: received.append(channel.recv()))
        receiver.start()
        self.assertTrue(connection.receive_entered.wait(1), "receive did not begin")

        channel.close()
        channel.close()
        receiver.join(2)

        self.assertFalse(receiver.is_alive())
        self.assertEqual(received, [b""])
        self.assertEqual(connection.close_calls, 1)


class _PendingListener:
    """Windows-like listener: closing queued handles does not wake pending accept."""

    def __init__(self, connection=None):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.connection = connection
        self.close_calls = 0
        self.accept_calls = 0
        self.close_thread = None

    def accept(self):
        self.accept_calls += 1
        self.entered.set()
        if not self.release.wait(2):
            raise TimeoutError("pending accept was not woken")
        if self.connection is not None:
            return self.connection
        raise EOFError("wakeup disconnected before authentication")

    def close(self):
        self.close_calls += 1
        self.close_thread = threading.get_ident()


class ServerShutdownTest(unittest.TestCase):
    def accept_in_thread(self, listener):
        results, errors = [], []

        def accept():
            try:
                results.append(listener.accept())
            except BaseException as exc:
                errors.append(exc)

        thread = threading.Thread(target=accept, daemon=True)
        thread.start()
        return thread, results, errors

    def test_pending_pipe_accept_is_woken_then_closed_by_its_owner(self):
        pending = _PendingListener()
        with mock.patch.object(transport.mpc, "Listener", return_value=pending) as factory, \
                mock.patch.object(transport, "_family", return_value="AF_PIPE"), \
                mock.patch.object(transport, "_wake_listener") as wake:
            listener = transport.Server("private-pipe", b"secret", backlog=4)

            def wake_pending(address, family):
                self.assertEqual((address, family), ("private-pipe", "AF_PIPE"))
                self.assertEqual(pending.close_calls, 0, "close must not race native pipe creation")
                pending.release.set()

            wake.side_effect = wake_pending
            thread, results, errors = self.accept_in_thread(listener)
            try:
                self.assertTrue(pending.entered.wait(1))
                listener.close()
                listener.close()
            finally:
                pending.release.set()
                thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(results, [None])
            self.assertTrue(listener.closed)
            self.assertEqual(pending.close_calls, 1)
            self.assertEqual(pending.close_thread, thread.ident)
            wake.assert_called_once()
            factory.assert_called_once_with("private-pipe", family="AF_PIPE", authkey=b"secret", backlog=4)

    def test_authenticated_channel_returning_across_close_is_discarded(self):
        connection = mock.Mock()
        pending = _PendingListener(connection)
        with mock.patch.object(transport.mpc, "Listener", return_value=pending), \
                mock.patch.object(transport, "_wake_listener", side_effect=lambda *_: pending.release.set()):
            listener = transport.Server("private", b"secret")
            thread, results, errors = self.accept_in_thread(listener)
            try:
                self.assertTrue(pending.entered.wait(1))
                listener.close()
            finally:
                pending.release.set()
                thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(results, [None])
            connection.close.assert_called_once_with()

    def test_rejected_authentication_repairs_the_owned_key_and_keeps_accepting(self):
        connection = mock.Mock()
        native = mock.Mock()
        native.accept.side_effect = [transport.mpc.AuthenticationError("stale"), connection]
        repair = mock.Mock()
        with mock.patch.object(transport.mpc, "Listener", return_value=native):
            listener = transport.Server(
                "private",
                b"secret",
                on_authentication_error=repair,
            )
            channel = listener.accept()
        self.assertIsNotNone(channel)
        repair.assert_called_once_with()
        channel.close()

    def test_close_without_accept_is_immediate_and_repeated_accept_stays_closed(self):
        pending = _PendingListener()
        with mock.patch.object(transport.mpc, "Listener", return_value=pending), \
                mock.patch.object(transport, "_wake_listener") as wake:
            listener = transport.Server("private", b"secret")
            listener.close()
            listener.close()
            self.assertIsNone(listener.accept())
            self.assertIsNone(listener.accept())
            self.assertEqual(pending.accept_calls, 0)
            self.assertEqual(pending.close_calls, 1)
            wake.assert_not_called()

    def test_close_does_not_wait_for_an_existing_stalled_authentication(self):
        pending = _PendingListener(mock.Mock())
        with mock.patch.object(transport.mpc, "Listener", return_value=pending), \
                mock.patch.object(transport, "_wake_listener"):
            listener = transport.Server("private", b"secret")
            thread, results, errors = self.accept_in_thread(listener)
            try:
                self.assertTrue(pending.entered.wait(1))
                listener.close()
                self.assertTrue(thread.is_alive(), "the existing peer has not disconnected yet")
                self.assertEqual(pending.close_calls, 0)
            finally:
                pending.release.set()
                thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(results, [None])
            pending.connection.close.assert_called_once_with()
            self.assertEqual(pending.close_calls, 1)

    def test_interrupted_accept_preserves_exception_and_releases_native_ownership(self):
        pending = mock.Mock()
        interruption = KeyboardInterrupt("accept interrupted")
        pending.accept.side_effect = interruption
        with mock.patch.object(transport.mpc, "Listener", return_value=pending), \
                mock.patch.object(transport, "_wake_listener") as wake:
            listener = transport.Server("private", b"secret")
            with self.assertRaises(KeyboardInterrupt) as caught:
                listener.accept()
            self.assertIs(caught.exception, interruption)
            listener.close()
            pending.close.assert_called_once_with()
            wake.assert_not_called()

    def test_pipe_wakeup_holds_both_instances_and_never_waits_or_authenticates(self):
        import ctypes

        kernel = mock.Mock()
        order = []
        handles = iter((11, 12))

        def create(*args):
            handle = next(handles)
            order.append(("open", handle))
            return handle

        kernel.CreateFileW.side_effect = create
        kernel.CloseHandle.side_effect = lambda handle: order.append(("close", handle))
        with mock.patch.object(ctypes, "WinDLL", return_value=kernel, create=True), \
                mock.patch.object(transport.mpc, "Client", side_effect=AssertionError("unbounded Client wake")):
            transport._wake_pipe_listener("private-pipe")
        self.assertEqual(order, [("open", 11), ("open", 12), ("close", 11), ("close", 12)])
        kernel.WaitNamedPipeW.assert_not_called()

    def test_pipe_wakeup_busy_instance_does_not_retry_or_leak_first_handle(self):
        import ctypes

        kernel = mock.Mock()
        kernel.CreateFileW.side_effect = (11, ctypes.c_void_p(-1).value)
        with mock.patch.object(ctypes, "WinDLL", return_value=kernel, create=True), \
                mock.patch.object(ctypes, "get_last_error", return_value=231, create=True) as last_error, \
                mock.patch.object(ctypes, "WinError", create=True) as win_error:
            transport._wake_pipe_listener("private-pipe")
        last_error.assert_called_once_with()
        win_error.assert_not_called()
        self.assertEqual(kernel.CreateFileW.call_count, 2)
        kernel.CloseHandle.assert_called_once_with(11)
        kernel.WaitNamedPipeW.assert_not_called()

    def test_pipe_wakeup_open_failure_closes_previously_opened_handle(self):
        import ctypes

        # File/path-not-found cannot be a normal close race while the Server
        # guard retains its listener. Access/resource errors must also stay loud.
        for error in (2, 3, 5, 8):
            with self.subTest(winerror=error):
                kernel = mock.Mock()
                kernel.CreateFileW.side_effect = (11, ctypes.c_void_p(-1).value)
                failure = OSError(error, "second open failed")
                with mock.patch.object(ctypes, "WinDLL", return_value=kernel, create=True), \
                        mock.patch.object(ctypes, "get_last_error", return_value=error, create=True) as last_error, \
                        mock.patch.object(ctypes, "WinError", return_value=failure, create=True) as win_error:
                    with self.assertRaises(OSError) as caught:
                        transport._wake_pipe_listener("private-pipe")
                self.assertIs(caught.exception, failure)
                last_error.assert_called_once_with()
                win_error.assert_called_once_with(error)
                kernel.CloseHandle.assert_called_once_with(11)

    def test_failed_wakeup_keeps_admission_closed_and_later_close_can_retry(self):
        import ctypes

        pending = _PendingListener()
        kernel = mock.Mock()
        kernel.CreateFileW.side_effect = (ctypes.c_void_p(-1).value, 11, 12)
        kernel.CloseHandle.side_effect = lambda _: pending.release.set()
        failure = OSError(5, "wakeup unavailable")
        with mock.patch.object(transport.mpc, "Listener", return_value=pending), \
                mock.patch.object(transport, "_family", return_value="AF_PIPE"), \
                mock.patch.object(ctypes, "WinDLL", return_value=kernel, create=True), \
                mock.patch.object(ctypes, "get_last_error", return_value=5, create=True) as last_error, \
                mock.patch.object(ctypes, "WinError", return_value=failure, create=True) as win_error:
            listener = transport.Server("private", b"secret")
            thread, results, errors = self.accept_in_thread(listener)
            try:
                self.assertTrue(pending.entered.wait(1))
                with self.assertRaises(OSError) as caught:
                    listener.close()
                self.assertIs(caught.exception, failure)
                self.assertTrue(listener.closed)
                self.assertEqual(pending.close_calls, 0)
                kernel.CloseHandle.assert_not_called()
                listener.close()
                listener.close()
            finally:
                pending.release.set()
                thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(results, [None])
            self.assertEqual(kernel.CreateFileW.call_count, 3)
            self.assertEqual(kernel.CloseHandle.call_args_list, [mock.call(11), mock.call(12)])
            last_error.assert_called_once_with()
            win_error.assert_called_once_with(5)
            self.assertEqual(pending.close_calls, 1)

    def real_listener(self):
        address = transport.private_address(transport.identity_digest(uuid.uuid4().hex))
        listener = transport.Server(address, b"test-key")
        self.addCleanup(transport.clear_address, address)
        self.addCleanup(listener.close)
        return listener

    def test_real_pending_accept_exits_without_an_application_channel(self):
        listener = self.real_listener()
        entered = threading.Event()
        native_accept = listener._listener.accept

        def accept():
            entered.set()
            return native_accept()

        with mock.patch.object(listener._listener, "accept", side_effect=accept):
            thread, results, errors = self.accept_in_thread(listener)
            try:
                self.assertTrue(entered.wait(1))
                start = time.monotonic()
                listener.close()
                self.assertLess(time.monotonic() - start, 1, "close waited on a peer handshake")
            finally:
                listener.close()
                thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results, [None])
        self.assertIsNone(listener.accept())

    def test_real_bad_authentication_does_not_stop_accepting_valid_clients(self):
        listener = self.real_listener()
        thread, results, errors = self.accept_in_thread(listener)
        try:
            with self.assertRaises(OSError):
                transport.connect(listener.address, b"wrong-key")
            with transport.connect(listener.address, b"test-key") as client:
                client.send(b"authenticated request")
                thread.join(2)
                self.assertFalse(thread.is_alive())
                self.assertEqual(errors, [])
                self.assertEqual(len(results), 1)
                self.assertIsInstance(results[0], Channel)
                with results[0] as accepted:
                    self.assertEqual(accepted.recv(1), b"authenticated request")
        finally:
            listener.close()
            thread.join(2)

    def test_real_rejected_stale_key_is_republished_and_retried(self):
        with tempfile.TemporaryDirectory(prefix="cadgen-auth-repair-") as tmp:
            with mock.patch.object(transport, "state_dir", return_value=Path(tmp)):
                address = transport.private_address(transport.identity_digest(uuid.uuid4().hex))
                try:
                    self._assert_real_key_repair(address, replace=True)
                finally:
                    transport.clear_address(address)
                    transport._authkey_path(address).unlink(missing_ok=True)

    def test_real_missing_key_is_republished_and_retried(self):
        with tempfile.TemporaryDirectory(prefix="cadgen-auth-repair-") as tmp:
            with mock.patch.object(transport, "state_dir", return_value=Path(tmp)):
                address = transport.private_address(transport.identity_digest(uuid.uuid4().hex))
                try:
                    self._assert_real_key_repair(address, replace=False)
                finally:
                    transport.clear_address(address)
                    transport._authkey_path(address).unlink(missing_ok=True)

    def _assert_real_key_repair(self, address: str, *, replace: bool) -> None:
        owned_key = b"owned-key"
        if replace:
            transport.publish_authkey(address, b"stale-key")
        listener = transport.Server(
            address,
            owned_key,
            on_authentication_error=lambda: transport.publish_authkey(address, owned_key),
        )
        thread, results, errors = self.accept_in_thread(listener)
        try:
            with client._connect(address) as connection:
                connection.send(b"recovered")
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(transport.read_authkey(address), owned_key)
            with results[0] as accepted:
                self.assertEqual(accepted.recv(1), b"recovered")
        finally:
            listener.close()
            thread.join(2)


if __name__ == "__main__":
    unittest.main()
