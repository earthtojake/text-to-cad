"""JSON-RPC 2.0 over newline-delimited stdio: the transport an MCP host speaks.

One reader thread parses messages. Requests the host sends run on a small pool,
so a slow request (a model's bytes, a picture) never blocks the others; ``initialize`` and ``ping``
run on the reader so a handshake is never queued behind work. Every outgoing
message is one line written under one lock. Requests this side sends (a form
elicitation, for instance) wait on a future keyed by their id.

The standard output of the process belongs to the protocol alone:
:func:`claim_stdout` moves the original descriptor aside and points descriptor 1
at standard error, so a stray ``print`` -- or a child process inheriting the
descriptor -- can never corrupt a frame.
"""

from __future__ import annotations

import itertools
import json
import logging
import os
import sys
import threading
from collections.abc import Callable, Iterable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, BinaryIO

LOG = logging.getLogger("cadgen.mcp")

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Methods answered on the reader thread, in arrival order.
_INLINE_METHODS = frozenset({"initialize", "ping"})


class RpcError(Exception):
    """A JSON-RPC error the handler wants returned to the caller as-is."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def payload(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            error["data"] = self.data
        return error


class RequestContext:
    """What a handler knows about the request it is serving."""

    __slots__ = ("request_id", "meta", "connection")

    def __init__(self, request_id: Any, meta: dict[str, Any], connection: "Connection") -> None:
        self.request_id = request_id
        self.meta = meta
        self.connection = connection

    @property
    def cancelled(self) -> bool:
        return self.connection.is_cancelled(self.request_id)


Handler = Callable[[str, dict[str, Any], RequestContext], Any]
NotificationHandler = Callable[[str, dict[str, Any]], None]


def claim_stdout() -> BinaryIO:
    """Return a private binary stream on the original stdout; send fd 1 to stderr."""
    protocol_fd = os.dup(1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    return os.fdopen(protocol_fd, "wb", buffering=0)


class Connection:
    """One peer: reads frames from ``reader``, writes frames to ``writer``."""

    def __init__(
        self,
        reader: Iterable[bytes],
        writer: BinaryIO,
        handler: Handler,
        *,
        on_notification: NotificationHandler | None = None,
        workers: int = 16,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._handler = handler
        self._on_notification = on_notification
        self._write_lock = threading.Lock()
        self._pending: dict[Any, Future] = {}
        self._pending_lock = threading.Lock()
        self._cancelled: set[Any] = set()
        self._ids = itertools.count(1)
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="cadgen-mcp")
        self._closed = threading.Event()

    # -- serving -------------------------------------------------------------

    def serve(self) -> None:
        """Serve until the reader ends; then fail every pending outgoing request."""
        try:
            for raw in self._reader:
                line = raw.strip()
                if line:
                    self._receive(line)
        finally:
            self._close()
            self._pool.shutdown(wait=False, cancel_futures=True)

    def _close(self) -> None:
        self._closed.set()
        with self._pending_lock:
            pending, self._pending = self._pending, {}
            for future in pending.values():
                if not future.done():
                    future.set_exception(ConnectionError("the host closed the connection"))

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    def is_cancelled(self, request_id: Any) -> bool:
        return request_id in self._cancelled

    def _receive(self, line: bytes) -> None:
        try:
            message = json.loads(line)
        except ValueError:
            self._send({"jsonrpc": "2.0", "id": None, "error": {"code": PARSE_ERROR, "message": "invalid JSON"}})
            return
        if not isinstance(message, dict):
            self._send({"jsonrpc": "2.0", "id": None, "error": {"code": INVALID_REQUEST, "message": "expected one JSON-RPC object"}})
            return
        method = message.get("method")
        if method is None:
            self._resolve(message)
            return
        params = message.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        if "id" not in message:
            self._notification(method, params)
            return
        request_id = message["id"]
        if method in _INLINE_METHODS:
            self._run(request_id, method, params)
        else:
            self._pool.submit(self._run, request_id, method, params)

    def _notification(self, method: str, params: dict[str, Any]) -> None:
        if method == "notifications/cancelled":
            self._cancelled.add(params.get("requestId"))
            return
        if self._on_notification is not None:
            try:
                self._on_notification(method, params)
            except Exception:  # a notification has no one to report to
                LOG.exception("notification %s failed", method)

    def _run(self, request_id: Any, method: str, params: dict[str, Any]) -> None:
        meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
        context = RequestContext(request_id, meta, self)
        try:
            result = self._handler(method, params, context)
        except RpcError as error:
            response = {"jsonrpc": "2.0", "id": request_id, "error": error.payload()}
        except Exception as error:  # every request gets an answer
            LOG.exception("request %s failed", method)
            response = {"jsonrpc": "2.0", "id": request_id, "error": {"code": INTERNAL_ERROR, "message": f"{type(error).__name__}: {error}"}}
        else:
            response = {"jsonrpc": "2.0", "id": request_id, "result": result if result is not None else {}}
        # A cancelled request gets no response (MCP cancellation); forget it either way.
        cancelled = request_id in self._cancelled
        self._cancelled.discard(request_id)
        if not cancelled:
            self._send(response)

    # -- requests and notifications from this side ---------------------------

    def request(self, method: str, params: dict[str, Any], *, timeout: float | None = None) -> Any:
        """Send a request to the host and wait for its result."""
        request_id = f"cadgen-{next(self._ids)}"
        future: Future = Future()
        with self._pending_lock:
            if self.closed:
                raise ConnectionError("the host closed the connection")
            self._pending[request_id] = future
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        try:
            return future.result(timeout=timeout)
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params:
            message["params"] = params
        self._send(message)

    def _resolve(self, message: dict[str, Any]) -> None:
        with self._pending_lock:
            future = self._pending.get(message.get("id"))
            if future is None or future.done():
                return
            if "error" in message:
                error = message["error"] if isinstance(message["error"], dict) else {}
                future.set_exception(RpcError(int(error.get("code", INTERNAL_ERROR)), str(error.get("message", "request failed")), error.get("data")))
            else:
                future.set_result(message.get("result"))

    def _send(self, message: dict[str, Any]) -> None:
        frame = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        with self._write_lock:
            try:
                self._writer.write(frame)
                self._writer.flush()
            except (BrokenPipeError, ValueError, OSError):
                self._close()
