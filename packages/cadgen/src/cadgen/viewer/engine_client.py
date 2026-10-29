"""HTTP access for a client of the explicitly selected engine (never a document relay)."""
from __future__ import annotations

import http.client
import os
import threading
from urllib.parse import urlsplit

from cadgen.engine import daemon
from cadgen.engine.client import _answering, missing, request


def _door(address=None):
    """Which engine the selected private door names now: the identity
    of the door a daemon reads (on Windows, of its port file, made anew at each start), or None when
    no engine answers there. A stat and an open of the door that writes nothing: some 15 us."""
    address = address or daemon.address()
    try:
        found = os.stat(address)
    except OSError:
        return None
    if daemon.WINDOWS:
        return found.st_ino, found.st_mtime_ns, found.st_size
    return (found.st_dev, found.st_ino) if _answering(address) else None


class EngineClient:
    """The engine's loopback endpoint as its door last named it. Only the engine can own that
    door (``daemon.folder_refusal``), while a loopback port is anyone's once the engine has let it
    go, and every call carries the user's page token, which outlives the engine. So the endpoint
    held is used only while the door that named it still answers (``_door``), and it is read from
    the door again whenever it may be stale: an engine gone or replaced, after any answer that is
    not a success, after a connection error, and for every call that asks for a ``fresh``
    endpoint (an MCP ``initialize``)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.endpoint = None
        self.door = None  # the identity of the door that named ``endpoint`` (``_door``)
        self.address = None  # where that door is

    def connect(self, *, fresh=False):
        """Attach to the endpoint the private door names; no HTTP client starts an engine."""
        with self.lock:
            selected = daemon.address()
            if self.endpoint is not None and not fresh and (self.address != selected or self.door is None
                                                            or _door(self.address) != self.door):
                self.endpoint = None  # its engine is gone: its port, and the token sent there, anyone's
            if self.endpoint is None or fresh:
                self.endpoint = None
                answer = request({'op': 'http'}, start=False)
                if not answer:
                    raise missing()
                if 'failed' in answer:
                    raise ConnectionError(answer['failed'])
                self.address = selected
                self.endpoint, self.door = answer, _door(self.address)
            return self.endpoint

    def forget(self):
        """Ask the engine where it listens again on the next call."""
        with self.lock:
            self.endpoint = None

    def _forget(self, endpoint):
        with self.lock:
            if self.endpoint is endpoint:
                self.endpoint = None

    def call(self, method, path, body=b'', headers=None, *, fresh=False):
        # A refused connection or credential is rediscovered through the private door before
        # retrying. HTTP attachment never starts an engine.
        endpoint = self.connect(fresh=fresh)
        for attempt in (1, 2):
            parsed = urlsplit(endpoint['url'])
            conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=600)
            try:
                conn.request(method, path, body=body, headers={**(headers or {}),
                             'Authorization': 'Bearer ' + endpoint['token']})
                response = conn.getresponse()
                answer = response.status, dict(response.getheaders()), response.read()
            except ConnectionRefusedError:
                self._forget(endpoint)
                if attempt == 2:
                    raise
                endpoint = self.connect(fresh=True)
                continue
            except (OSError, http.client.HTTPException):
                self._forget(endpoint)
                raise
            finally:
                conn.close()
            if not 200 <= answer[0] < 300:
                self._forget(endpoint)  # the next call asks the door where the engine listens
                if attempt == 1 and answer[0] == 403 and b'engine token required' in answer[2]:
                    endpoint = self.connect(fresh=True)
                    continue
            return answer
