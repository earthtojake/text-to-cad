"""What a peer without the engine's token can make the listener spend: a connection waits at most
REQUEST_TIMEOUT_SECONDS for any one read, at most MAX_CONNECTIONS are served at once (one more is
closed as it is accepted), and a request refused at the Host or token gate neither keeps the engine
from retiring nor counts as an active client."""

from __future__ import annotations

import socket
import time
import types
import unittest
from unittest import mock

from cadgen.viewer import handler as handler_module

from .test_http_layer import ServerFixture


def closed(sock: socket.socket, within: float) -> bool:
    """Whether the server closes ``sock`` within ``within`` seconds."""
    sock.settimeout(within)
    try:
        return sock.recv(65536) == b""
    except socket.timeout:
        return False
    except ConnectionResetError:
        return True


def until(condition, within: float = 10.0) -> bool:
    """Whether ``condition()`` comes true within ``within`` seconds (polled; a condition, not a sleep)."""
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return condition()


class ListenerBoundsTest(unittest.TestCase):
    def fixture(self) -> ServerFixture:
        fixture = ServerFixture()
        self.addCleanup(fixture.close)
        return fixture

    def test_a_connection_that_stops_sending_is_closed_after_the_read_timeout(self) -> None:
        with mock.patch.object(handler_module, "REQUEST_TIMEOUT_SECONDS", 0.5):
            fixture = self.fixture()
        sock = socket.create_connection(("127.0.0.1", fixture.port), timeout=10)
        self.addCleanup(sock.close)
        sock.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n")  # headers never finished
        started = time.monotonic()
        self.assertTrue(closed(sock, 10), "the half-sent request was let go")
        self.assertLess(time.monotonic() - started, 10)

    def test_connections_past_the_cap_are_closed_as_they_are_accepted(self) -> None:
        with mock.patch.object(handler_module, "MAX_CONNECTIONS", 2):
            fixture = self.fixture()
        held = [socket.create_connection(("127.0.0.1", fixture.port), timeout=10) for _ in range(2)]
        for sock in held:
            self.addCleanup(sock.close)
            sock.sendall(b"GET / HTTP/1.1\r\n")  # each holds a slot
        self.assertTrue(until(lambda: fixture.server._slots._value == 0), "both connections hold a slot")
        third = socket.create_connection(("127.0.0.1", fixture.port), timeout=10)
        self.addCleanup(third.close)
        self.assertTrue(closed(third, 5), "a connection past the cap is closed at once")
        for sock in held:
            sock.close()
        self.assertTrue(until(lambda: fixture.server._slots._value == 2), "slots come back as connections end")
        status, _headers, _body = fixture.request("GET", "/__cad/server", headers={"Host": "localhost"})
        self.assertEqual(status, 200)


class GateOrderTest(unittest.TestCase):
    """EngineApp counts a request as use only once it has passed the gates."""

    def engine(self):
        from cadgen.viewer import engine_app

        server = types.SimpleNamespace(port=4242, touch=mock.Mock(), url="http://127.0.0.1:4242")
        with mock.patch("cadgen.analytics.Recorder"):
            app = engine_app.EngineApp(server, "127.0.0.1")
        return app, server

    def request(self, *, host="127.0.0.1:4242", token=""):
        headers = {"host": host, "authorization": f"Bearer {token}" if token else ""}
        return types.SimpleNamespace(header=lambda name, default="": headers.get(name, default), query={},
                                     path="/__cad/server", method="GET")

    def test_a_refused_request_neither_touches_the_engine_nor_counts_as_active(self) -> None:
        app, server = self.engine()
        seen = []
        response = types.SimpleNamespace(send_json=lambda status, body: seen.append((status, app.active_requests)),
                                         send_bytes=lambda status, *rest: seen.append((status, app.active_requests)))
        app.handle(self.request(host="evil.example"), response)
        app.handle(self.request(token="guessed"), response)
        self.assertEqual([status for status, _active in seen], [403, 403])
        self.assertEqual([active for _status, active in seen], [0, 0])
        server.touch.assert_not_called()
        with mock.patch.object(app, "default_app") as default:
            default.return_value.handle.side_effect = lambda request, response: seen.append(("served", app.active_requests))
            app.handle(self.request(token=app.token), response)
        self.assertEqual(seen[-1], ("served", 1))
        self.assertEqual(app.active_requests, 0)
        self.assertGreaterEqual(server.touch.call_count, 1)


if __name__ == "__main__":
    unittest.main()
