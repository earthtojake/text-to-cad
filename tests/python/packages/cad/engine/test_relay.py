"""The engine's door for a program that cannot dial it (``cad.engine.relay``): a listener on the loopback that
admits its program by a token, dials the engine for it and passes the bytes both ways; and the client of a Python
with no pipes of the system's, which asks there."""

from __future__ import annotations

import os
import socket
import threading
import unittest
from unittest import mock

from tests.python.support.paths import add_sources

add_sources()

from cad.engine import client, door, places, relay  # noqa: E402


class _Engine:
    """An engine's end of a connection: what the relay's dial returns, and a thread that answers each line."""

    def __init__(self) -> None:
        self.near, self.far = socket.socketpair()
        self.stream = self.far.makefile("rwb")
        self.connection = door.Connection(self.near.makefile("rb"), self.near.makefile("wb"), self.near,
                                          protocol=door.DOOR_PROTOCOL, release="9.9.9")
        threading.Thread(target=self._answer, daemon=True).start()

    def _answer(self) -> None:
        for line in self.stream:
            self.stream.write(b"answered " + line)
            self.stream.flush()

    def close(self) -> None:
        for one in (self.near, self.far):
            one.close()


class RelayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = _Engine()
        self.addCleanup(self.engine.close)
        self.dialled = mock.patch.object(client, "_connect", return_value=self.engine.connection)
        self.dial = self.dialled.start()
        self.addCleanup(self.dialled.stop)
        self.relay = relay.Relay()
        self.addCleanup(self.relay.close)

    def said(self, token: str) -> tuple[socket.socket, bytes]:
        port, _token = relay.named(self.relay.value)
        taken = socket.create_connection(("127.0.0.1", port), timeout=30)
        self.addCleanup(taken.close)
        taken.sendall(door.hello(token))
        return taken, taken.makefile("rb").readline()

    def test_its_program_s_token_is_admitted_greeted_as_the_engine_greets_and_its_bytes_pass_both_ways(self) -> None:
        port, token = relay.named(self.relay.value)
        taken, line = self.said(token)
        self.assertEqual((door.greeted(line.rstrip(b"\n")), door.released(line.rstrip(b"\n"))),
                         (door.DOOR_PROTOCOL, "9.9.9"))
        stream = taken.makefile("rwb")
        for asked in (b'{"op":"pid"}\n', b"x" * 200_000 + b"\n"):
            stream.write(asked)
            stream.flush()
            self.assertEqual(stream.readline(), b"answered " + asked)
        self.dial.assert_called_once_with()

    def test_another_token_and_a_line_that_is_no_hello_hear_nothing_and_no_engine_is_dialled(self) -> None:
        for token in ("0" * door.ID_CHARACTERS, "not a hello"):
            if token == "not a hello":
                port, _token = relay.named(self.relay.value)
                taken = socket.create_connection(("127.0.0.1", port), timeout=30)
                self.addCleanup(taken.close)
                taken.sendall(b"not a hello\n")
                line = taken.makefile("rb").readline()
            else:
                _taken, line = self.said(token)
            self.assertEqual(line, b"")
        self.dial.assert_not_called()

    def test_with_no_engine_its_program_hears_no_greeting(self) -> None:
        self.dial.return_value = None
        _taken, line = self.said(relay.named(self.relay.value)[1])
        self.assertEqual(line, b"")

    def test_what_names_a_relay(self) -> None:
        self.assertEqual(relay.named("4711 abc"), (4711, "abc"))
        for text in (None, "", "4711", "port token", "1 2 3"):
            self.assertIsNone(relay.named(text), text)


class RelayedClientTest(unittest.TestCase):
    """A client on a Python with no pipes (``places.THREADS`` false) asks its starter's relay, and no door."""

    def test_it_connects_through_the_relay_it_is_told_of_and_to_nothing_where_it_is_told_of_none(self) -> None:
        engine = _Engine()
        self.addCleanup(engine.close)
        between = relay.Relay()
        self.addCleanup(between.close)
        real = client._connect
        with mock.patch.object(client, "_connect", return_value=engine.connection), \
                mock.patch.object(places, "THREADS", False), \
                mock.patch.object(client, "dial", side_effect=AssertionError("the door was dialled")):
            with mock.patch.dict(os.environ, {relay.VARIABLE: between.value}):
                found = real()
            self.assertIsNotNone(found)
            self.addCleanup(found.close)
            self.assertEqual((found.protocol, found.release, found.token), (door.DOOR_PROTOCOL, "9.9.9", None))
            found.writer.write(b'{"op":"pid"}\n')
            found.writer.flush()
            self.assertEqual(found.reader.readline(), b'answered {"op":"pid"}\n')
            with mock.patch.dict(os.environ):
                os.environ.pop(relay.VARIABLE, None)
                self.assertIsNone(real())


if __name__ == "__main__":
    unittest.main()
