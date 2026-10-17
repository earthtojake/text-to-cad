"""The broker: the daemon's two static mechanisms that span its workers.

1. **Job slots** — one running build per core. A counting semaphore of
   ``N = os.cpu_count()`` (``CADGEN_JOBS`` overrides). A job takes a slot
   before its body runs and holds it through its emit; a child model built
   inside the body runs in the slot its parent holds (``held`` nests); the job
   YIELDS the slot while it waits for a pool job -- its display, export or
   verify job -- and reacquires, queuing again if it must, when that is done.
   That yield is the deadlock avoidance: a 1-slot pool still finishes a build
   that waits on its own pool jobs. Work already under way goes first: a slot
   asked for to continue it -- an artifact job a build or a view waits on, a job
   taking back the slot it yielded -- is granted ahead of every job not yet
   started, in order among themselves; the rest are granted in order (FIFO). So
   a build's own display job runs in the slot the build yields to wait for it,
   and the build takes the slot back the moment the job is done, rather than
   both queuing behind builds that have not begun.
2. **In-flight coalescing** — a compile or an artifact request that matches a
   job already in flight (the same document's bytes, the same artifact request)
   attaches to that job instead of starting another. In flight only.

The daemon IS the broker for its workers: it serves slot requests over its own
socket (``server._handle_request``) and claims in-flight entries for the requests
it relays. A lease is a CONNECTION: holding a slot is holding the connection open,
so a worker that dies releases its slot by dying. With no daemon there is no
broker: a build runs its own body and its pool jobs on threads of its own process.
Memory admission belongs to the worker pool, separately from these CPU leases;
yielding a CPU lease never releases the parent's memory allowance.

Client side (a daemon worker's job)::

    with held("plate.py"):          # a slot for the body + emit
        ...
        with yielded():             # about to wait for a pool job
            job.result()

Both are no-ops when no broker is reachable: a limit must never fail a build.
"""

from __future__ import annotations

import collections
import contextlib
import copy
import json
import os
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
    """Slots -- work under way first, then FIFO -- plus the in-flight registry.
    Thread-safe; the daemon's."""

    def __init__(self, limit: int | None = None) -> None:
        self._cv = threading.Condition()
        self._limit = limit if limit is not None else job_limit()
        self._running: dict[int, str] = {}  # lease id -> label
        self._queue: collections.deque[int] = collections.deque()
        # The queued leases that continue work under way, always the queue's head.
        self._first: set[int] = set()
        self._next = 0
        self._peak = 0
        self._granted = 0
        # (store, subject, closure) -> one uniquely owned entry. Consumers are explicit:
        # losing a waiting subscriber never cancels canonical work another
        # subscriber still needs, while losing the owner plus its last consumer
        # leaves the worker eligible for cancellation by the supervisor.
        self._inflight: dict[tuple[str, ...], dict[str, Any]] = {}
        self._coalesced = 0

    # slots -------------------------------------------------------------------------

    @property
    def limit(self) -> int:
        return self._limit

    def acquire(self, label: str, *, cancelled: Callable[[], bool] | None = None,
                first: bool = False) -> int | None:
        """Block until a slot is free: in order, or, for work under way (``first``),
        in order ahead of every job not yet started. Returns the lease id, or None if
        ``cancelled()`` turned true while waiting (the requester went away)."""
        with self._cv:
            self._next += 1
            lease = self._next
            if first:
                self._queue.insert(len(self._first), lease)
                self._first.add(lease)
            else:
                self._queue.append(lease)
            while True:
                if self._queue[0] == lease and len(self._running) < self._limit:
                    self._queue.popleft()
                    self._first.discard(lease)
                    self._running[lease] = label
                    self._granted += 1
                    self._peak = max(self._peak, len(self._running))
                    self._cv.notify_all()
                    return lease
                if cancelled is not None and cancelled():
                    self._queue.remove(lease)
                    self._first.discard(lease)
                    self._cv.notify_all()
                    return None
                self._cv.wait(timeout=0.5 if cancelled is not None else None)

    def release(self, lease: int) -> None:
        with self._cv:
            self._running.pop(lease, None)
            self._cv.notify_all()

    # in flight ------------------------------------------------------------------------

    def claim_entry(self, model: str, closure: str, *, store_root: str = "") -> tuple[bool, dict[str, Any]]:
        """Claim a unique in-flight entry.

        Returns ``(True, entry)`` for its producer and ``(False, entry)`` for
        an attached consumer. The entry token, rather than its reusable key,
        makes late completion unable to finish a replacement producer.
        """
        key = (os.path.realpath(store_root) if store_root else "", model, closure)
        return self._claim_key(key)

    def claim_artifact_entry(self, request: dict, *, store_root: str) -> tuple[bool, dict[str, Any]]:
        from cadgen.daemon.artifacts import normalize_request, request_key, store_path

        request = normalize_request(request)
        return self._claim_key(("artifact", store_path(store_root), request_key(request), ""), artifact=True)

    def _claim_key(self, key: tuple[str, ...], *, artifact: bool = False) -> tuple[bool, dict[str, Any]]:
        with self._cv:
            entry = self._inflight.get(key)
            if entry is not None and not entry["done"].is_set():
                if entry["ownerActive"] or entry["consumers"]:
                    entry["consumers"] += 1
                    self._coalesced += 1
                    return False, entry
            entry = {
                "key": key,
                "done": threading.Event(),
                "exit": None,
                "error": None,
                "result": None,
                "artifact": artifact,
                "ownerActive": True,
                "consumers": 0,
                "orphaned": threading.Event(),
            }
            self._inflight[key] = entry
            return True, entry

    def publish_artifact_result(self, entry: dict[str, Any], result: dict) -> None:
        """Retain an artifact job's result for present and late consumers."""
        if not entry.get("artifact"):
            return
        with self._cv:
            if entry["result"] is None and not entry["done"].is_set():
                entry["result"] = {"artifactResult": copy.deepcopy(result)}
                self._cv.notify_all()

    def wait_update(self, entry: dict[str, Any], *, result_seen: bool, timeout: float = .1) -> tuple[dict | None, bool, int]:
        """Wait for the entry's result (an artifact job's, once, unless ``result_seen``)
        or its end: ``(result frame or None, done, exit)``."""
        with self._cv:
            self._cv.wait_for(lambda: entry["done"].is_set() or (entry["result"] is not None and not result_seen), timeout)
            result = copy.deepcopy(entry["result"]) if not result_seen else None
            return result, entry["done"].is_set(), int(entry["exit"] if entry["exit"] is not None else 1)

    def _retire_orphan_locked(self, entry: dict[str, Any]) -> None:
        key = entry["key"]
        if self._inflight.get(key) is entry:
            self._inflight.pop(key, None)
        entry["orphaned"].set()
        self._cv.notify_all()

    def detach(self, entry: dict[str, Any]) -> bool:
        """Detach one consumer; return True when its old work became orphaned.

        Retirement and removal from the attachable registry are one locked
        operation, so a new request receives a new token before the supervisor
        terminates the old worker.
        """
        with self._cv:
            if entry["consumers"]:
                entry["consumers"] -= 1
            if not entry["ownerActive"] and not entry["consumers"] and not entry["done"].is_set():
                self._retire_orphan_locked(entry)
            self._cv.notify_all()
            return entry["orphaned"].is_set()

    def abandon(self, entry: dict[str, Any]) -> bool:
        """Mark the producer connection gone; return whether consumers remain."""
        with self._cv:
            entry["ownerActive"] = False
            if not entry["consumers"] and not entry["done"].is_set():
                self._retire_orphan_locked(entry)
            return bool(entry["consumers"] and not entry["done"].is_set())

    @staticmethod
    def orphaned(entry: dict[str, Any]) -> bool:
        return entry["orphaned"].is_set() and not entry["done"].is_set()

    def finish_entry(self, entry: dict[str, Any], code: int, *, error: str | None = None) -> None:
        """Close the entry with the owner's exit code and, for a failure, its one-line
        reason, which attached consumers record as their own."""
        with self._cv:
            key = entry["key"]
            if self._inflight.get(key) is entry:
                self._inflight.pop(key, None)
            entry["exit"] = int(code)
            entry["error"] = str(error) if code != 0 and error else None
            entry["ownerActive"] = False
            entry["done"].set()
            self._cv.notify_all()

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
        """Serve one slot request on ``conn``. Blocks for the lease's lifetime:
        the caller runs this on its own thread."""
        if request.get("kind") == "slot":
            self._serve_slot(conn, request)
        else:
            _send(conn, {"error": f"unknown broker request {request.get('kind')!r}"})

    def _serve_slot(self, conn: transport.Channel, request: dict) -> None:
        label = str(request.get("label") or "")
        peer_gone = threading.Event()

        def cancelled() -> bool:
            # A queued requester that closed its connection must not take a slot later.
            probe = conn.recv(0.0)
            if probe == b"":
                peer_gone.set()
            return peer_gone.is_set()

        lease = self.acquire(label, cancelled=cancelled, first=bool(request.get("first")))
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


def _send(conn: transport.Channel, frame: dict) -> None:
    conn.send(json.dumps(frame, separators=(",", ":")).encode("utf-8"))


# --- client side ---------------------------------------------------------------------------


def _endpoint() -> tuple[str, bytes] | None:
    """Where this process's broker is: the daemon it belongs to, when it is a daemon
    worker. None when there is none (a build with no daemon)."""
    if os.environ.get("CADGEN_DAEMON_CHILD"):
        from cadgen.daemon.client import daemon_address

        address = daemon_address()
        daemon_key = transport.read_authkey(address)
        if daemon_key:
            return address, daemon_key
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
        from cadgen.daemon.client import compute_version_token

        _send(conn, {**request, "token": compute_version_token()})
    except OSError:
        conn.close()
        return None
    return conn


class Lease:
    """A held slot. ``release()`` closes the connection, which is the release."""

    def __init__(self, conn: transport.Channel, label: str, *, required=False) -> None:
        self._conn = conn
        self.label = label
        self.required = required

    def release(self) -> None:
        with contextlib.suppress(OSError):
            self._conn.close()


def acquire_slot(label: str, *, on_queued: Callable[[], None] | None = None,
                 required: bool = False, first: bool = False) -> Lease | None:
    """Block until the broker grants a slot. None when there is no broker. ``first``:
    the slot continues work under way, and goes ahead of jobs not yet started."""
    conn = _open({"kind": "slot", "op": "acquire", "label": label, **({"first": True} if first else {})})
    if conn is None:
        if required:
            raise RuntimeError("artifact CPU broker is unavailable; work was not run")
        return None
    # A grant that does not arrive at once means we are queued: say so once.
    try:
        raw = conn.recv(0.05)
        if raw is None:
            if on_queued is not None:
                on_queued()
            raw = conn.recv(None)
        granted = bool(raw) and (not required or json.loads(raw.decode("utf-8")) == {"slot": "granted"})
    except (OSError, ValueError):
        granted = False
    if not granted:
        conn.close()
        if required:
            raise RuntimeError("artifact CPU broker did not grant a lease; work was not run")
        return None
    return Lease(conn, label, required=required)


_CURRENT = threading.local()


def current_lease() -> Lease | None:
    return getattr(_CURRENT, "lease", None)


@contextlib.contextmanager
def held(label: str, *, on_queued: Callable[[], None] | None = None,
         required: bool = False, first: bool = False) -> Iterator[Lease | None]:
    """Run the block holding a job slot (or none, when no broker is reachable); ``first``
    as :func:`acquire_slot`'s. Nests: a block entered while this thread holds a slot --
    a child model's build inside its parent's body -- runs in that slot."""
    previous = current_lease()
    if previous is not None:
        yield previous
        return
    lease = acquire_slot(label, on_queued=on_queued, required=required, first=first)
    _CURRENT.lease = lease
    try:
        yield lease
    finally:
        active = current_lease()
        _CURRENT.lease = None
        if active is not None:
            active.release()


@contextlib.contextmanager
def yielded() -> Iterator[None]:
    """Give the held slot back for the block (a wait on a pool job) and take one again
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
        _CURRENT.lease = acquire_slot(lease.label, required=lease.required, first=True)
