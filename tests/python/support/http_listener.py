"""A plain HTTP listener over a ``cad.engine.serve.Server``, for tests that read one over HTTP.

The library's server binds nothing of its own (the daemon's listener is the engine's one);
a test passes this as its ``http_factory`` to read the server's routes at ``server.url``."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def listener(server: Any, host: str, port: int) -> ThreadingHTTPServer:
    """A listener on ``host``:``port`` whose every GET and POST is ``server.route``'s, after
    ``server.touch()``."""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: Any) -> None:
            pass

        def do_GET(self) -> None:  # noqa: N802
            server.touch()
            server.route(self, "GET")

        def do_POST(self) -> None:  # noqa: N802
            server.touch()
            server.route(self, "POST")

    return ThreadingHTTPServer((host, port), Handler)
