"""A job-slot broker served on a private address, for tests of the broker's client side.

In production the daemon is the one broker (``cadgen.daemon.broker``): it serves slot
requests over its own socket. A test of ``held``, ``yielded`` and ``acquire_slot``, or
of a job that takes a slot, needs a broker to answer without a daemon, so this serves a
``Broker`` on a fresh address with a fresh key, and :func:`served` points the client's
endpoint lookup at it for the test's length.
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import threading
import time
from unittest import mock

from cadgen.daemon import broker, transport

CLOSE_JOIN_SECONDS = 2.0  # how long close waits for the broker's own threads


class PrivateBroker:
    """A ``Broker`` served on a private address. ``close()`` stops it."""

    def __init__(self, limit: int | None = None) -> None:
        self.broker = broker.Broker(limit)
        self.key = secrets.token_hex(16).encode("ascii")
        # A short digest in the system temp dir: AF_UNIX paths cap at ~104 bytes.
        self.address = transport.private_address(
            transport.identity_digest(f"test-broker-{os.getpid()}-{secrets.token_hex(8)}")
        )
        self._server = transport.Server(self.address, self.key, backlog=64)
        self._serving: set[threading.Thread] = set()
        self._serving_lock = threading.Lock()
        self._thread = threading.Thread(target=self._accept_loop, name="cadgen-test-broker", daemon=True)
        self._thread.start()

    @property
    def endpoint(self) -> tuple[str, bytes]:
        return self.address, self.key

    def served(self) -> contextlib.AbstractContextManager[None]:
        """Make this broker the one the client side of ``cadgen.daemon.broker`` reaches."""
        return mock.patch.object(broker, "_endpoint", return_value=self.endpoint)

    def _accept_loop(self) -> None:
        while True:
            conn = self._server.accept()
            if conn is None:
                return
            thread = threading.Thread(target=self._serve_one, args=(conn,), daemon=True)
            with self._serving_lock:
                self._serving.add(thread)
            thread.start()

    def _serve_one(self, conn: transport.Channel) -> None:
        try:
            raw = conn.recv(30.0)
            if not raw:
                return
            request = json.loads(raw.decode("utf-8"))
            if isinstance(request, dict):
                self.broker.handle(conn, request)
        except (OSError, ValueError):
            pass
        finally:
            with contextlib.suppress(OSError):
                conn.close()
            with self._serving_lock:
                self._serving.discard(threading.current_thread())

    def close(self) -> None:
        # The listener owns the socket unlink, including process-exit finalization. Then
        # wait for this broker's threads, so none wakes into the interpreter's
        # finalization: the accept thread first, since it starts the others, then the
        # handshakes it started and a request still being served.
        self._server.close()
        deadline = time.monotonic() + CLOSE_JOIN_SECONDS

        def remaining() -> float:
            return max(0.0, deadline - time.monotonic())

        if self._thread is not threading.current_thread():
            self._thread.join(remaining())
        self._server.join(remaining())
        with self._serving_lock:
            serving = list(self._serving)
        for thread in serving:
            if thread is not threading.current_thread():
                thread.join(remaining())
