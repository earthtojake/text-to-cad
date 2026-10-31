"""The engine's door (``cad.engine.door``): a hello's framing, a connection over a pair of named
pipes, the owner and type check on a pair, and the sweep of a killed client's pair."""

from __future__ import annotations

import os
import selectors
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock


@unittest.skipIf(os.name == "nt", "the door is POSIX's: Windows keeps its loopback port")
class DoorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="door-"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.clients = self.folder / "clients"
        self.clients.mkdir(mode=0o700)

    def open_door(self, serve) -> Path:
        from cad.engine import door

        path = self.folder / "x.door"
        opened = door.Door(path, lambda ident: door.answer(self.clients, ident, serve))
        self.addCleanup(opened.close)
        return path

    def test_a_hello_is_one_short_line_and_only_an_id_is_a_hello(self) -> None:
        from cad.engine import door

        ident = "0123456789abcdef" * 2
        line = door.hello(ident)
        self.assertEqual(line, ident.encode() + b"\n")
        self.assertLess(len(line), 512, "below PIPE_BUF: hellos written at once never interleave")
        self.assertEqual(door.hello_id(line.rstrip(b"\n")), ident)
        for other in (b"", ident[:-1].encode(), ident.upper().encode(), ident.encode() + b"0",
                      b"../" + ident[3:].encode(), ident.encode()[:-1] + b"\x00"):
            self.assertIsNone(door.hello_id(other), other)

    def test_a_request_and_its_answers_cross_the_pair_and_either_side_leaving_is_the_other_s_end(self) -> None:
        from cad.engine import door

        served = threading.Event()
        seen: list[bytes] = []

        def serve(reader, writer) -> None:
            seen.append(reader.readline())
            writer.write(b"one\ntwo\n")
            writer.flush()
            seen.append(reader.read())  # the client gone: end of file
            served.set()

        path = self.open_door(serve)
        connection = door.dial(path)
        self.assertIsNotNone(connection)
        with connection:
            connection.writer.write(b'{"op": "status"}\n')
            connection.writer.flush()
            self.assertEqual([connection.reader.readline(), connection.reader.readline()], [b"one\n", b"two\n"])
        self.assertTrue(served.wait(10))
        self.assertEqual(seen, [b'{"op": "status"}\n', b""])
        self.assertEqual(list(self.clients.iterdir()), [], "the pair's names went once it was connected")

        def leaves(reader, writer) -> None:
            reader.readline()  # and goes, without a word

        path = self.open_door(leaves)  # the same path: the first door is replaced, as a restart's is
        with door.dial(path) as connection:
            connection.writer.write(b"{}\n")
            connection.writer.flush()
            self.assertEqual(connection.reader.read(), b"", "the daemon's side gone: end of file")

    def test_a_door_nobody_reads_answers_nothing_at_once(self) -> None:
        from cad.engine import door

        path = self.folder / "dead.door"
        os.mkfifo(path, 0o600)
        started = time.monotonic()
        self.assertFalse(door.answering(path))
        self.assertIsNone(door.dial(path))
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(list(self.clients.iterdir()), [])
        self.assertFalse(door.answering(self.folder / "missing.door"))

    def test_a_daemon_that_dies_after_reading_the_hello_ends_the_client_s_wait(self) -> None:
        from cad.engine import door

        path = self.folder / "dying.door"
        os.mkfifo(path, 0o600)
        reading = os.open(path, os.O_RDONLY | os.O_NONBLOCK)  # the daemon: it reads one hello, and dies

        def die() -> None:
            while True:
                try:
                    if os.read(reading, 64):
                        break
                except BlockingIOError:
                    time.sleep(0.01)
            os.close(reading)

        dying = threading.Thread(target=die, daemon=True)
        dying.start()
        started = time.monotonic()
        self.assertIsNone(door.dial(path, timeout=60))
        self.assertLess(time.monotonic() - started, 30, "not the whole greeting wait: nobody reads the door")
        dying.join(5)
        self.assertEqual(list(self.clients.iterdir()), [])

    def test_a_clients_folder_opened_to_others_is_closed_again_and_connects(self) -> None:
        from cad.engine import door

        def serve(reader, writer) -> None:
            reader.readline()
            writer.write(b"ok\n")
            writer.flush()

        path = self.open_door(serve)
        os.chmod(self.clients, 0o755)
        connection = door.dial(path)
        self.assertIsNotNone(connection, "a folder of this user's, in the engine's own: closed, not a dead end")
        with connection:
            connection.writer.write(b"{}\n")
            connection.writer.flush()
            self.assertEqual(connection.reader.readline(), b"ok\n")
        self.assertEqual(self.clients.stat().st_mode & 0o777, 0o700)

    def test_a_pair_that_is_not_this_user_s_fifo_is_refused_and_never_served(self) -> None:
        from cad.engine import door

        served: list[int] = []
        ident = "ab" * 16
        up, down = door.pair(self.clients, ident)
        target = self.folder / "elsewhere"
        os.mkfifo(target, 0o600)
        held = os.open(target, os.O_RDWR)  # a reader there: a followed link would open
        self.addCleanup(os.close, held)

        def pair(make_down) -> None:
            for path in (up, down):
                path.unlink(missing_ok=True)
            os.mkfifo(up, 0o600)
            make_down()

        real = os.fstat

        def foreign(fd):
            found = real(fd)
            return os.stat_result((found.st_mode, found.st_ino, found.st_dev, found.st_nlink, os.getuid() + 1,
                                   found.st_gid, found.st_size, 0, 0, 0))

        def other_users() -> None:
            os.mkfifo(down, 0o600)
            self.addCleanup(os.close, os.open(down, os.O_RDWR))  # a client's reader: the open succeeds

        for make_down, as_another in ((lambda: down.write_bytes(b""), False),  # a plain file
                                      (lambda: down.symlink_to(target), False),  # a link, never followed
                                      (other_users, True)):  # a pipe of another user's
            pair(make_down)
            with mock.patch.object(door.os, "fstat", side_effect=foreign) if as_another else mock.MagicMock():
                door.answer(self.clients, ident, lambda reader, writer: served.append(1))
            self.assertEqual(served, [])
            self.assertFalse(up.exists() or down.is_symlink() or down.exists(), "the refused pair's names went")
        os.set_blocking(held, False)
        with self.assertRaises(BlockingIOError, msg="nothing was written through the link"):
            os.read(held, 16)


    def test_a_pair_named_twice_is_answered_once(self) -> None:
        from cad.engine import door

        release = threading.Event()
        answered: list[int] = []

        def serve(reader, writer) -> None:
            answered.append(1)
            release.wait(10)

        path = self.open_door(serve)
        self.addCleanup(release.set)
        ident = "d" * 32
        up, down = door.pair(self.clients, ident)
        os.mkfifo(up, 0o600)
        os.mkfifo(down, 0o600)
        hold = os.open(down, os.O_RDWR)
        self.addCleanup(os.close, hold)
        self.addCleanup(os.close, os.open(up, os.O_RDWR))
        knock = os.open(path, os.O_WRONLY)
        self.addCleanup(os.close, knock)
        os.write(knock, door.hello(ident) * 2)  # one write: the reader takes both lines in one read
        greeting = b""
        with selectors.DefaultSelector() as selector:
            selector.register(hold, selectors.EVENT_READ)
            self.assertTrue(selector.select(10), "the pair was greeted")
            greeting += os.read(hold, 64)
            if selector.select(0.5):  # a second answer, were there one, greets well within this
                greeting += os.read(hold, 64)
        self.assertEqual(greeting, door.GREETING, "one greeting: the second hello was not answered")
        self.assertEqual(answered, [1])

    def test_the_sweep_takes_a_killed_client_s_old_pair_without_opening_it(self) -> None:
        from cad.engine import door

        old, young, held = "a" * 32, "b" * 32, "c" * 32
        for ident in (old, young, held):
            for path in door.pair(self.clients, ident):
                os.mkfifo(path, 0o600)
        (self.clients / "notes.txt").write_text("not a pair", encoding="utf-8")
        past = time.time() - door.STALE_SECONDS - 1
        for ident in (old, held):
            for path in door.pair(self.clients, ident):
                os.utime(path, (past, past))
        with mock.patch.object(door.os, "open", side_effect=AssertionError("a pair was opened")):
            removed = door.sweep(self.clients, {held})
        self.assertEqual(sorted(removed), [f"{old}.down", f"{old}.up"])
        self.assertEqual(sorted(p.name for p in self.clients.iterdir()),
                         sorted([f"{young}.down", f"{young}.up", f"{held}.down", f"{held}.up", "notes.txt"]))


if __name__ == "__main__":
    unittest.main()
