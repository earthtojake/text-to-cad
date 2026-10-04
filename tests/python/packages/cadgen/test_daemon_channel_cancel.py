"""Cancellation must not let a blocked channel read another connection's bytes."""

from __future__ import annotations

import multiprocessing.connection as mpc
import os
import socket
import struct
import threading
import unittest
from unittest import mock

from cadgen.daemon.transport import Channel


@unittest.skipIf(os.name == "nt", "POSIX socket descriptor reuse")
class ChannelCancellationTest(unittest.TestCase):
    def test_cancelled_partial_frame_does_not_consume_a_replacement_connection(self):
        receiver, sender = socket.socketpair()
        connection = mpc.Connection(receiver.detach())
        channel = Channel(connection)
        entered, release = threading.Event(), threading.Event()
        received, failures = [], []
        descriptor = connection.fileno()
        native_read = mpc.Connection._read
        reads = 0

        def read(fd, size):
            nonlocal reads
            if fd == descriptor:
                reads += 1
                if reads == 2:
                    entered.set()
                    if not release.wait(2):
                        raise RuntimeError("test did not release the frame reader")
            return native_read(fd, size)

        def receive():
            try:
                received.append(channel.recv())
            except BaseException as error:
                failures.append(error)

        replacement_receiver = replacement_sender = None
        with mock.patch.object(mpc.Connection._recv, "__defaults__", (read,)):
            thread = threading.Thread(target=receive, daemon=True)
            thread.start()
            try:
                sender.sendall(struct.pack("!i", 4))
                self.assertTrue(entered.wait(2), "reader did not consume the partial frame header")
                channel.close()
                replacement_receiver, replacement_sender = socket.socketpair()
                replacement_sender.sendall(b"next")
                release.set()
                thread.join(2)
                self.assertFalse(thread.is_alive(), "cancelled receive did not finish")
                self.assertEqual(failures, [])
                self.assertEqual(received, [b""], "cancelled channel stole the replacement connection's bytes")
                self.assertEqual(replacement_receiver.recv(4), b"next")
            finally:
                release.set()
                channel.close()
                sender.close()
                if replacement_sender is not None:
                    replacement_sender.close()
                thread.join(2)
                if replacement_receiver is not None:
                    replacement_receiver.close()

    def test_cancel_wakes_a_reader_waiting_for_its_first_frame(self):
        receiver, sender = socket.socketpair()
        connection = mpc.Connection(receiver.detach())
        channel = Channel(connection)
        entered = threading.Event()
        received, failures = [], []
        native_poll = connection.poll

        def poll(timeout):
            entered.set()
            return native_poll(timeout)

        def receive():
            try:
                received.append(channel.recv(60))
            except BaseException as error:
                failures.append(error)

        with mock.patch.object(connection, "poll", side_effect=poll):
            thread = threading.Thread(target=receive, daemon=True)
            thread.start()
            try:
                self.assertTrue(entered.wait(2), "receive did not start polling")
                channel.close()
                channel.close()
                thread.join(2)
                self.assertFalse(thread.is_alive(), "cancel did not wake the native reader")
                self.assertEqual(failures, [])
                self.assertEqual(received, [b""])
                self.assertTrue(connection.closed)
                self.assertEqual(channel.recv(0), b"")
                with self.assertRaises(OSError):
                    channel.send(b"after-close")
            finally:
                channel.close()
                sender.close()
                thread.join(2)

    def test_uncancelled_frames_and_timeout_keep_the_existing_contract(self):
        receiver, sender = socket.socketpair()
        channel = Channel(mpc.Connection(receiver.detach()))
        peer = Channel(mpc.Connection(sender.detach()))
        with channel, peer:
            self.assertIsNone(channel.recv(0))
            peer.send(b"ordinary")
            self.assertEqual(channel.recv(), b"ordinary")
            channel.send(b"reply")
            self.assertEqual(peer.recv(), b"reply")


if __name__ == "__main__":
    unittest.main()
