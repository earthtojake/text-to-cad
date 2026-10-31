"""The engine's door (``cad.engine.door``): a hello's and a greeting's framing and protocol number, a
connection over a pair of named pipes, the owner and type check on a pair, and the sweep of a killed
client's pair."""

from __future__ import annotations

import os
import secrets
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
        opened = door.Door(path, lambda ident, protocol: door.answer(self.clients, ident, serve, protocol))
        self.addCleanup(opened.close)
        return path

    def test_a_hello_is_one_short_line_naming_an_id_and_its_protocol_and_a_bare_id_is_protocol_0(self) -> None:
        from cad.engine import door

        ident = "0123456789abcdef" * 2
        line = door.hello(ident)
        self.assertEqual(line, ident.encode() + b" 1\n")
        self.assertEqual(door.DOOR_PROTOCOL, 1)
        self.assertLess(len(line), 512, "below PIPE_BUF: hellos written at once never interleave")
        self.assertEqual(door.hello(ident, 0), ident.encode() + b"\n", "protocol 0: the bare id, 0.8's hello")
        for said, protocol in ((line, 1), (door.hello(ident, 0), 0), (ident.encode() + b" 7 later fields\n", 7)):
            self.assertEqual(door.hello_id(said.rstrip(b"\n")), ident)
            self.assertEqual(door.hello_protocol(said.rstrip(b"\n")), protocol)
        for other in (b"", ident[:-1].encode(), ident.upper().encode(), ident.encode() + b"0",
                      b"../" + ident[3:].encode(), ident.encode()[:-1] + b"\x00", ident.encode() + b" ",
                      ident.encode() + b" one", ident.encode() + b" -1", ident.encode() + b"  1"):
            self.assertIsNone(door.hello_id(other), other)
            self.assertIsNone(door.hello_protocol(other), other)

    def test_a_greeting_names_the_protocol_the_connection_speaks_and_a_bare_ok_is_protocol_0(self) -> None:
        from cad.engine import door

        self.assertEqual(door.greeting(1), b"ok 1\n")
        self.assertEqual(door.greeting(), b"ok 1\n")
        self.assertEqual(door.greeting(0), b"ok\n", "protocol 0: the bare greeting, 0.8's")
        for line, protocol in ((b"ok 1\n", 1), (b"ok 1", 1), (b"ok\n", 0), (b"ok", 0), (b"ok 2 later fields\n", 2)):
            self.assertEqual(door.greeted(line), protocol, line)
        for other in (b"", b"\n", b"ok \n", b"ok one\n", b"no 1\n", b"okay\n", b"ok\n\n"):
            self.assertIsNone(door.greeted(other), other)

    def test_the_daemon_greets_each_hello_in_the_protocol_it_spoke(self) -> None:
        from cad.engine import door

        path = self.open_door(lambda reader, writer: reader.readline())
        for protocol, greeting in ((1, b"ok 1\n"), (0, b"ok\n"), (9, b"ok 1\n")):
            ident = secrets.token_hex(16)
            up, down = door.pair(self.clients, ident)
            os.mkfifo(up, 0o600)
            os.mkfifo(down, 0o600)
            hold = os.open(down, os.O_RDWR)
            self.addCleanup(os.close, hold)
            self.addCleanup(os.close, os.open(up, os.O_RDWR))
            knock = os.open(path, os.O_WRONLY)
            self.addCleanup(os.close, knock)
            os.write(knock, door.hello(ident, protocol))
            with selectors.DefaultSelector() as selector:
                selector.register(hold, selectors.EVENT_READ)
                self.assertTrue(selector.select(10), "the pair was greeted")
                self.assertEqual(os.read(hold, 64), greeting, f"a protocol {protocol} hello")

    def test_a_client_takes_a_bare_greeting_as_protocol_0_and_refuses_one_it_does_not_speak(self) -> None:
        from cad.engine import door

        for greeting, protocol in ((b"ok\n", 0), (b"ok 1\n", 1), (b"ok 2\n", None), (b"no\n", None)):
            def answer(ident: str, _protocol: int, greeting: bytes = greeting) -> None:
                up, down = door.pair(self.clients, ident)
                writer = os.open(down, os.O_WRONLY | os.O_NONBLOCK)
                reader = os.open(up, os.O_RDONLY | os.O_NONBLOCK)
                os.write(writer, greeting)  # an engine that greets so, and goes: the client holds its pair
                os.close(writer)
                os.close(reader)

            path = self.folder / "other.door"
            opened = door.Door(path, answer)
            self.addCleanup(opened.close)
            connection = door.dial(path, timeout=5)
            if protocol is None:
                self.assertIsNone(connection, greeting)
            else:
                self.assertIsNotNone(connection, greeting)
                self.assertEqual(connection.protocol, protocol)
                connection.close()
            opened.close()

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

    def test_a_client_says_the_bare_hello_at_an_earlier_release_s_door_and_its_own_at_the_engine_s(self) -> None:
        from cad.engine import client, door, places

        heard: list[int] = []

        def engine(ident: str, protocol: int) -> None:
            heard.append(protocol)
            door.answer(self.clients, ident, lambda reader, writer: reader.readline(), protocol)

        for name, protocol in (("0123456789ab", 0), (places.NAME, door.DOOR_PROTOCOL)):  # 0.8's door: a tag
            opened = door.Door(self.folder / f"{name}.door", engine)
            self.addCleanup(opened.close)
            connection = client._connect(opened.path)
            self.assertIsNotNone(connection, name)
            self.assertEqual(connection.protocol, protocol, name)
            connection.close()
            opened.close()
        self.assertEqual(heard, [0, door.DOOR_PROTOCOL])

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
        self.assertEqual(greeting, door.greeting(), "one greeting: the second hello was not answered")
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
