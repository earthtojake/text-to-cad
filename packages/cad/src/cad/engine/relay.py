"""The engine's door for a program that cannot dial it.

A program on the WebAssembly kernel's Python (``cad run``, where a person chose that kernel) has no pipes of the
system's to make its pair with (``door.dial``): its sockets are its host's, and they connect. So the process that
starts it stands between: a ``Relay`` listens on the loopback, admits a connection by the token it made (as a
Windows engine's port does), dials the engine itself for it (``client._connect``) and passes the bytes both ways
until either side is done. The program is told where by ``VARIABLE`` -- its relay's port and token, which it must
know before it starts -- and its client asks there (``client._connect``).

The relay admits what its starter's own client could ask, no more: it runs as the person who ran the program, and
its token is the program's alone.
"""

from __future__ import annotations

import secrets
import socket
import threading
from typing import Any

from cad.engine import door

__all__ = ["VARIABLE", "Relay", "named"]

# The relay a program asks the engine through: ``<port> <token>``, as a Windows engine's port file reads.
VARIABLE = "CAD_ENGINE_RELAY"
_CHUNK = 1 << 16


def named(text: str | None) -> tuple[int, str] | None:
    """The port and token ``VARIABLE`` names, or None where it names none that reads."""
    parts = (text or "").split()
    if len(parts) != 2 or not parts[0].isdigit():
        return None
    return int(parts[0]), parts[1]


class Relay:
    """A listener on the loopback for one program: ``value`` is what its ``VARIABLE`` holds. ``close`` ends it
    and every connection through it."""

    def __init__(self) -> None:
        self.token = secrets.token_hex(16)
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.value = f"{self.listener.getsockname()[1]} {self.token}"
        self.held: list[Any] = []
        self.lock = threading.Lock()
        self.closed = False
        threading.Thread(target=self._listen, name="cad-relay", daemon=True).start()

    def _listen(self) -> None:
        while True:
            try:
                taken, _address = self.listener.accept()
            except OSError:
                return  # closed
            threading.Thread(target=self._serve, args=(taken,), name="cad-relay-connection", daemon=True).start()

    def _serve(self, taken: socket.socket) -> None:
        from cad.engine import client

        engine = None
        try:
            taken.settimeout(door.GREETING_SECONDS)
            line = b""
            while not line.endswith(b"\n") and len(line) < door.HELLO_LIMIT:
                byte = taken.recv(1)  # the hello alone: what follows it is the engine's to read
                if not byte:
                    return
                line += byte
            if door.hello_id(line.rstrip(b"\r\n")) != self.token:
                return
            engine = client._connect()
            if engine is None:
                return  # no engine: the program hears no greeting, as at a door nobody reads
            with self.lock:
                if self.closed:
                    return
                self.held += [taken, engine]
            taken.settimeout(None)
            taken.sendall(door.greeting(engine.protocol, engine.release))
            threading.Thread(target=self._down, args=(engine, taken), name="cad-relay-answers", daemon=True).start()
            while True:
                data = taken.recv(_CHUNK)
                if not data:
                    return
                engine.writer.write(data)
                engine.writer.flush()
        except (OSError, ValueError):
            return
        finally:
            for one in (engine, taken):
                try:
                    if one is not None:
                        one.close()
                except OSError:
                    pass

    @staticmethod
    def _down(engine: Any, taken: socket.socket) -> None:
        try:
            while True:
                data = engine.reader.read1(_CHUNK)
                if not data:
                    break
                taken.sendall(data)
        except (OSError, ValueError):
            pass
        try:
            taken.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def close(self) -> None:
        with self.lock:
            self.closed = True
            held, self.held = self.held, []
        try:
            self.listener.shutdown(socket.SHUT_RDWR)  # wakes the thread that waits in accept: nothing more is taken
        except OSError:
            pass
        for one in (self.listener, *held):
            try:
                one.close()
            except OSError:
                pass
