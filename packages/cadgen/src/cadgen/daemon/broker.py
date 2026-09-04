"""The broker: the pool's two static mechanisms that span processes.

1. **Job slots** — one running build per core. A counting semaphore of
   ``N = os.cpu_count()`` (``CADGEN_JOBS`` overrides), FIFO. A job takes a slot
   before its body runs and holds it through its emit; it YIELDS the slot while it
   waits for children it forced (a waiting parent does no kernel work) and reacquires
   — queuing again if it must — when they are done. That yield is the deadlock
   avoidance: a 1-slot pool still builds a 3-level tree.
2. **In-flight coalescing** — a submit for ``(model, closure hash)`` that matches a
   job already in flight attaches to that job instead of starting another. In-flight
   only, identical source only; never the requested model of a top-level request.

One broker per executor. The daemon IS the broker for its workers (daemon-wide
slots); a transient build's root process runs a private one for the workers it
spawns (per-build slots). Both speak the same frames over the same transport, and
a lease is a CONNECTION: holding a slot is holding the connection open, so a worker
that dies releases its slot by dying. Nothing here reads memory or adapts; the
only inputs are a core count and what is in flight.

Client side (any process that builds)::

    with held("plate.py"):          # a slot for the body + emit
        ...
        with yielded():             # about to wait for a child
            job.wait()

Both are no-ops when no broker is reachable: a limit must never fail a build.
"""

from __future__ import annotations

import collections
import contextlib
import json
import os
import secrets
import threading
from typing import Any, Callable, Iterator

from cadgen.daemon import transport

DEFAULT_IDLE_UNBIND_SECONDS = 600.0


def job_limit() -> int:
    raw = os.environ.get("CADGEN_JOBS", "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return max(1, os.cpu_count() or 1)


# --- the broker itself -----------------------------------------------------------------


class Broker:
    """FIFO slots plus the in-flight registry. Thread-safe; one per executor."""

    def __init__(self, limit: int | None = None) -> None:
        self._cv = threading.Condition()
        self._limit = limit if limit is not None else job_limit()
        self._running: dict[int, str] = {}  # lease id -> label
        self._queue: collections.deque[int] = collections.deque()
        self._next = 0
        self._peak = 0
        self._granted = 0
        # (model, closure) -> {"done": Event, "exit": int | None}
        self._inflight: dict[tuple[str, str], dict[str, Any]] = {}
        self._coalesced = 0

    # slots -------------------------------------------------------------------------

    @property
    def limit(self) -> int:
        return self._limit

    def acquire(self, label: str, *, cancelled: Callable[[], bool] | None = None) -> int | None:
        """Block until a slot is free (FIFO). Returns the lease id, or None if
        ``cancelled()`` turned true while waiting (the requester went away)."""
        with self._cv:
            self._next += 1
            lease = self._next
            self._queue.append(lease)
            while True:
                if self._queue[0] == lease and len(self._running) < self._limit:
                    self._queue.popleft()
                    self._running[lease] = label
                    self._granted += 1
                    self._peak = max(self._peak, len(self._running))
                    self._cv.notify_all()
                    return lease
                if cancelled is not None and cancelled():
                    self._queue.remove(lease)
                    self._cv.notify_all()
                    return None
                self._cv.wait(timeout=0.5 if cancelled is not None else None)

    def release(self, lease: int) -> None:
        with self._cv:
            self._running.pop(lease, None)
            self._cv.notify_all()

    # in flight ------------------------------------------------------------------------

    def claim(self, model: str, closure: str) -> dict[str, Any] | None:
        """Register ``(model, closure)`` as in flight. Returns None when it is now
        yours to build, else the entry to wait on (a job with identical source is
        already running)."""
        key = (model, closure)
        with self._cv:
            entry = self._inflight.get(key)
            if entry is not None and not entry["done"].is_set():
                self._coalesced += 1
                return entry
            self._inflight[key] = {"done": threading.Event(), "exit": None}
            return None

    def finish(self, model: str, closure: str, code: int) -> None:
        with self._cv:
            entry = self._inflight.pop((model, closure), None)
        if entry is not None:
            entry["exit"] = int(code)
            entry["done"].set()

    def snapshot(self) -> dict[str, Any]:
        with self._cv:
            return {
                "running": len(self._running),
                "limit": self._limit,
                "queued": len(self._queue),
                "peakRunning": self._peak,
                "granted": self._granted,
                "inflight": len(self._inflight),
                "coalesced": self._coalesced,
            }

    # serving --------------------------------------------------------------------------

    def handle(self, conn: transport.Channel, request: dict) -> None:
        """Serve one broker request on ``conn``. Blocks for the lease's lifetime:
        the caller runs this on its own thread."""
        kind = request.get("kind")
        if kind == "slot":
            self._serve_slot(conn, request)
        elif kind == "inflight":
            self._serve_inflight(conn, request)
        else:
            _send(conn, {"error": f"unknown broker request {kind!r}"})

    def _serve_slot(self, conn: transport.Channel, request: dict) -> None:
        label = str(request.get("label") or "")
        peer_gone = threading.Event()

        def cancelled() -> bool:
            # A queued requester that closed its connection must not take a slot later.
            probe = conn.recv(0.0)
            if probe == b"":
                peer_gone.set()
            return peer_gone.is_set()

        lease = self.acquire(label, cancelled=cancelled)
        if lease is None:
            return
        try:
            try:
                _send(conn, {"slot": "granted"})
            except OSError:
                return
            # The lease lives as long as the connection: any message or EOF ends it.
            conn.recv(None)
        finally:
            self.release(lease)

    def _serve_inflight(self, conn: transport.Channel, request: dict) -> None:
        model = str(request.get("model") or "")
        closure = str(request.get("closure") or "")
        op = request.get("op")
        if op == "claim":
            entry = self.claim(model, closure)
            if entry is None:
                _send(conn, {"inflight": "yours"})
                # The claimer reports the outcome on this same connection; if it dies
                # first, the attached parties are released with a failure.
                code = 1
                try:
                    raw = conn.recv(None)
                    if raw:
                        payload = json.loads(raw.decode("utf-8"))
                        code = int(payload.get("exit", 1))
                except (OSError, ValueError):
                    pass
                self.finish(model, closure, code)
                return
            _send(conn, {"inflight": "attached"})
            entry["done"].wait()
            with contextlib.suppress(OSError):
                _send(conn, {"exit": entry["exit"] if entry["exit"] is not None else 1})
        else:
            _send(conn, {"error": f"unknown inflight op {op!r}"})


def _send(conn: transport.Channel, frame: dict) -> None:
    conn.send(json.dumps(frame, separators=(",", ":")).encode("utf-8"))


# --- a private broker for a transient build ------------------------------------------------

BROKER_ADDRESS_VAR = "CADGEN_BROKER"
BROKER_KEY_VAR = "CADGEN_BROKER_KEY"
BROKER_STATS_VAR = "CADGEN_BROKER_STATS"  # a file the private broker writes its snapshot to


class PrivateBroker:
    """A broker owned by one top-level transient build, serving its workers.

    Listens on a fresh address with a fresh key, both handed to the workers through
    the environment (they inherit it). Closed when the build ends; a snapshot goes to
    ``CADGEN_BROKER_STATS`` when set (tests read the peak from it).
    """

    def __init__(self, limit: int | None = None) -> None:
        self.broker = Broker(limit)
        self.key = secrets.token_hex(16).encode("ascii")
        # A short digest in the system temp dir: AF_UNIX paths cap at ~104 bytes.
        self.address = transport.private_address(
            transport.identity_digest(f"build-{os.getpid()}-{secrets.token_hex(8)}")
        )
        self._server = transport.Server(self.address, self.key, backlog=64)
        self._thread = threading.Thread(target=self._accept_loop, name="cadgen-broker", daemon=True)
        self._thread.start()

    def _accept_loop(self) -> None:
        while True:
            conn = self._server.accept()
            if conn is None:
                return
            threading.Thread(target=self._serve_one, args=(conn,), daemon=True).start()

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

    def env(self) -> dict[str, str]:
        return {BROKER_ADDRESS_VAR: self.address, BROKER_KEY_VAR: self.key.decode("ascii")}

    def close(self) -> None:
        stats = os.environ.get(BROKER_STATS_VAR)
        if stats:
            with contextlib.suppress(OSError):
                with open(stats, "w", encoding="utf-8") as handle:
                    json.dump(self.broker.snapshot(), handle)
        self._server.close()
        transport.clear_address(self.address)


# --- client side ---------------------------------------------------------------------------


def _endpoint() -> tuple[str, bytes] | None:
    """Where this process's broker is: the private one its root handed down, else the
    daemon it belongs to. None when there is none (an in-process cold build)."""
    address = os.environ.get(BROKER_ADDRESS_VAR)
    key = os.environ.get(BROKER_KEY_VAR)
    if address and key:
        return address, key.encode("ascii")
    if os.environ.get("CADGEN_DAEMON_CHILD") and os.environ.get("CADGEN_DAEMON") != "0":
        from cadgen.daemon.client import daemon_address, daemon_identity

        daemon_key = transport.read_authkey(daemon_identity())
        if daemon_key:
            return daemon_address(), daemon_key
    return None


def _open(request: dict) -> transport.Channel | None:
    endpoint = _endpoint()
    if endpoint is None:
        return None
    address, key = endpoint
    try:
        conn = transport.connect(address, key)
    except OSError:
        return None
    try:
        payload = dict(request)
        if BROKER_ADDRESS_VAR not in os.environ:
            from cadgen.daemon.client import compute_version_token

            payload["token"] = compute_version_token()
        _send(conn, payload)
    except OSError:
        conn.close()
        return None
    return conn


class Lease:
    """A held slot. ``release()`` closes the connection, which is the release."""

    def __init__(self, conn: transport.Channel, label: str) -> None:
        self._conn = conn
        self.label = label

    def release(self) -> None:
        with contextlib.suppress(OSError):
            self._conn.close()


def acquire_slot(label: str, *, on_queued: Callable[[], None] | None = None) -> Lease | None:
    """Block until the broker grants a slot. None when there is no broker."""
    conn = _open({"kind": "slot", "op": "acquire", "label": label})
    if conn is None:
        return None
    # A grant that does not arrive at once means we are queued: say so once.
    raw = conn.recv(0.05)
    if raw is None:
        if on_queued is not None:
            on_queued()
        raw = conn.recv(None)
    if not raw:
        conn.close()
        return None
    return Lease(conn, label)


_CURRENT = threading.local()


def current_lease() -> Lease | None:
    return getattr(_CURRENT, "lease", None)


@contextlib.contextmanager
def held(label: str, *, on_queued: Callable[[], None] | None = None) -> Iterator[Lease | None]:
    """Run the block holding a job slot (or none, when no broker is reachable)."""
    lease = acquire_slot(label, on_queued=on_queued)
    previous = current_lease()
    _CURRENT.lease = lease
    try:
        yield lease
    finally:
        _CURRENT.lease = previous
        if lease is not None:
            lease.release()


@contextlib.contextmanager
def yielded() -> Iterator[None]:
    """Give the held slot back for the block (a wait on children) and take one again
    after -- queuing if the pool filled meanwhile."""
    lease = current_lease()
    if lease is None:
        yield
        return
    lease.release()
    _CURRENT.lease = None
    try:
        yield
    finally:
        _CURRENT.lease = acquire_slot(lease.label)


def claim_inflight(model: str, closure: str) -> tuple[str, transport.Channel] | None:
    """Ask the broker who builds ``(model, closure)``. ``("yours", conn)`` means build
    it and call :func:`report_done` on ``conn``; ``("attached", conn)`` means another
    job with identical source is running and :func:`wait_attached` yields its exit.
    None when there is no broker."""
    conn = _open({"kind": "inflight", "op": "claim", "model": model, "closure": closure})
    if conn is None:
        return None
    raw = conn.recv(30.0)
    if not raw:
        conn.close()
        return None
    try:
        answer = json.loads(raw.decode("utf-8")).get("inflight")
    except ValueError:
        conn.close()
        return None
    if answer not in ("yours", "attached"):
        conn.close()
        return None
    return str(answer), conn


def report_done(conn: transport.Channel, code: int) -> None:
    with contextlib.suppress(OSError):
        _send(conn, {"exit": int(code)})
    conn.close()


def wait_attached(conn: transport.Channel) -> int:
    try:
        raw = conn.recv(None)
        if raw:
            return int(json.loads(raw.decode("utf-8")).get("exit", 1))
    except (OSError, ValueError):
        pass
    finally:
        conn.close()
    return 1
