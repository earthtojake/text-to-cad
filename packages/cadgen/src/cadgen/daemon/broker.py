"""The broker: the pool's two static mechanisms that span processes.

1. **Job slots** — one running build per core. A counting semaphore of
   ``N = os.cpu_count()`` (``CADGEN_JOBS`` overrides), FIFO. A job takes a slot
   before its body runs and holds it through its emit; it YIELDS the slot while it
   waits for children it forced (a waiting parent does no kernel work, but
   retains its geometry and memory reservation in the worker pool) and reacquires
   — queuing again if it must — when they are done. That yield is the deadlock
   avoidance: a 1-slot pool still builds a 3-level tree.
2. **In-flight coalescing** — a submit for ``(model, closure hash)`` that matches a
   job already in flight attaches to that job instead of starting another. In-flight
   only, identical source only; never the requested model of a top-level request.

One broker per executor. The daemon IS the broker for its workers (daemon-wide
slots); a transient build's root process runs a private one for the workers it
spawns (per-build slots). Both speak the same frames over the same transport, and
a lease is a CONNECTION: holding a slot is holding the connection open, so a worker
that dies releases its slot by dying. Memory admission belongs to the worker
pool, separately from these CPU leases; yielding a CPU lease never releases
the parent's memory allowance.

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
import copy
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
        # (model, closure) -> one uniquely owned entry. Consumers are explicit:
        # losing a waiting subscriber never cancels canonical work another
        # subscriber still needs, while losing the owner plus its last consumer
        # leaves the worker eligible for cancellation by the supervisor.
        self._inflight: dict[tuple[str, ...], dict[str, Any]] = {}
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
                "result": None,
                "artifact": artifact,
                "ownerActive": True,
                "consumers": 0,
                "orphaned": threading.Event(),
            }
            self._inflight[key] = entry
            return True, entry

    def publish_result(self, entry: dict[str, Any], event: dict) -> None:
        """Retain this producer's source result for present and late consumers."""
        if entry.get("artifact") or not isinstance(event.get("sourceResult"), dict):
            return
        with self._cv:
            if entry["result"] is None and not entry["done"].is_set():
                entry["result"] = copy.deepcopy(event)
                self._cv.notify_all()

    def publish_artifact_result(self, entry: dict[str, Any], result: dict) -> None:
        """Retain typed artifact output without manufacturing a source event."""
        if not entry.get("artifact"):
            return
        with self._cv:
            if entry["result"] is None and not entry["done"].is_set():
                entry["result"] = {"artifactResult": copy.deepcopy(result)}
                self._cv.notify_all()

    def wait_update(self, entry: dict[str, Any], *, result_seen: bool, timeout: float = .1) -> tuple[dict | None, bool, int]:
        with self._cv:
            self._cv.wait_for(lambda: entry["done"].is_set() or (entry["result"] is not None and not result_seen), timeout)
            event = copy.deepcopy(entry["result"]) if not result_seen else None
            return event, entry["done"].is_set(), int(entry["exit"] if entry["exit"] is not None else 1)

    def claim(self, model: str, closure: str) -> dict[str, Any] | None:
        """Register ``(model, closure)`` as in flight. Returns None when it is now
        yours to build, else the entry to wait on (a job with identical source is
        already running)."""
        owned, entry = self.claim_entry(model, closure)
        return None if owned else entry

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

    def finish_entry(self, entry: dict[str, Any], code: int) -> None:
        with self._cv:
            key = entry["key"]
            if self._inflight.get(key) is entry:
                self._inflight.pop(key, None)
            entry["exit"] = int(code)
            entry["ownerActive"] = False
            entry["done"].set()
            self._cv.notify_all()

    def finish(self, model: str, closure: str, code: int) -> None:
        with self._cv:
            entry = self._inflight.get(("", model, closure))
        if entry is not None:
            self.finish_entry(entry, code)

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
            if "artifact" in request:
                owned, entry = self.claim_artifact_entry(request["artifact"], store_root=request.get("store_root"))
            else:
                owned, entry = self.claim_entry(model, closure, store_root=str(request.get("store_root") or ""))
            if owned:
                # The claimer reports the outcome on this same connection; if it dies
                # first, the attached parties are released with a failure.
                code = 1
                try:
                    _send(conn, {"inflight": "yours"})
                    while True:
                        if entry.get("artifact") and self.orphaned(entry):
                            _send(conn, {"orphaned": True})
                            break
                        raw = conn.recv(.1 if entry.get("artifact") else None)
                        if raw is None:
                            continue
                        if not raw:
                            break
                        payload = json.loads(raw.decode("utf-8"))
                        if payload.get("ownerDetached") is True and entry.get("artifact"):
                            self.abandon(entry)
                        if isinstance(payload.get("event"), dict):
                            self.publish_result(entry, payload["event"])
                        if isinstance(payload.get("artifactResult"), dict):
                            self.publish_artifact_result(entry, payload["artifactResult"])
                        if "exit" in payload:
                            code = int(payload["exit"])
                            break
                except (OSError, ValueError):
                    pass
                finally:
                    self.finish_entry(entry, code)
                return
            try:
                _send(conn, {"inflight": "attached"})
                result_seen = False
                while True:
                    event, done, code = self.wait_update(entry, result_seen=result_seen)
                    if event is not None:
                        _send(conn, event if entry.get("artifact") else {"event": event})
                        result_seen = True
                    if done:
                        _send(conn, {"exit": code})
                        break
                    if conn.recv(0.0) == b"":
                        break
            finally:
                self.detach(entry)
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
        # Listener owns the socket unlink, including process-exit finalization.
        # The accept thread may still be completing its shutdown wakeup; clearing
        # its unique address here races that owner and makes finalization fail.
        self._server.close()


# --- client side ---------------------------------------------------------------------------


def _endpoint() -> tuple[str, bytes] | None:
    """Where this process's broker is: the private one its root handed down, else the
    daemon it belongs to. None when there is none (an in-process cold build)."""
    address = os.environ.get(BROKER_ADDRESS_VAR)
    key = os.environ.get(BROKER_KEY_VAR)
    if address and key:
        return address, key.encode("ascii")
    if os.environ.get("CADGEN_DAEMON_CHILD") and os.environ.get("CADGEN_DAEMON") != "0":
        from cadgen.daemon.client import daemon_address

        address = daemon_address()
        daemon_key = transport.read_authkey(address)
        if daemon_key:
            return address, daemon_key
    return None


def _open(request: dict, *, endpoint: tuple[str, bytes] | None = None) -> transport.Channel | None:
    explicit_endpoint = endpoint is not None
    endpoint = endpoint if endpoint is not None else _endpoint()
    if endpoint is None:
        return None
    address, key = endpoint
    try:
        conn = transport.connect(address, key)
    except OSError:
        return None
    try:
        payload = dict(request)
        if not explicit_endpoint and BROKER_ADDRESS_VAR not in os.environ:
            from cadgen.daemon.client import compute_version_token

            payload["token"] = compute_version_token()
        _send(conn, payload)
    except OSError:
        conn.close()
        return None
    return conn


class Lease:
    """A held slot. ``release()`` closes the connection, which is the release."""

    def __init__(self, conn: transport.Channel, label: str, *, required=False, endpoint=None) -> None:
        self._conn = conn
        self.label = label
        self.required = required
        self.endpoint = endpoint

    def release(self) -> None:
        with contextlib.suppress(OSError):
            self._conn.close()


def acquire_slot(label: str, *, on_queued: Callable[[], None] | None = None,
                 required: bool = False, endpoint=None) -> Lease | None:
    """Block until the broker grants a slot. None when there is no broker."""
    conn = _open({"kind": "slot", "op": "acquire", "label": label}, endpoint=endpoint)
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
    return Lease(conn, label, required=required, endpoint=endpoint)


_CURRENT = threading.local()


def current_lease() -> Lease | None:
    return getattr(_CURRENT, "lease", None)


@contextlib.contextmanager
def held(label: str, *, on_queued: Callable[[], None] | None = None,
         required: bool = False, endpoint=None) -> Iterator[Lease | None]:
    """Run the block holding a job slot (or none, when no broker is reachable)."""
    lease = acquire_slot(label, on_queued=on_queued, required=required, endpoint=endpoint)
    previous = current_lease()
    _CURRENT.lease = lease
    try:
        yield lease
    finally:
        active = current_lease()
        _CURRENT.lease = previous
        if active is not None:
            active.release()


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
        _CURRENT.lease = acquire_slot(lease.label, required=lease.required, endpoint=lease.endpoint)


def claim_artifact(request: dict, *, store_root: str, endpoint=None) -> tuple[str, transport.Channel]:
    from cadgen.daemon.artifacts import ArtifactJobError, normalize_request, store_path

    conn = _open({"kind": "inflight", "op": "claim", "artifact": normalize_request(request),
                  "store_root": store_path(store_root)}, endpoint=endpoint)
    if conn is None:
        raise ArtifactJobError("artifact broker unavailable; no unaccounted retry")
    try:
        raw = conn.recv(30.0)
        answer = json.loads(raw.decode("utf-8")) if raw else None
        if not isinstance(answer, dict) or answer.get("inflight") not in {"yours", "attached"}:
            raise ArtifactJobError("artifact broker returned no valid claim")
        return answer["inflight"], conn
    except BaseException:
        conn.close()
        raise


def claim_inflight(model: str, closure: str, *, store_root: str = "") -> tuple[str, transport.Channel] | None:
    """Ask the broker who builds ``(model, closure)``. ``("yours", conn)`` means build
    it and call :func:`report_done` on ``conn``; ``("attached", conn)`` means another
    job with identical source is running and :func:`wait_attached` yields its exit.
    None when there is no broker."""
    conn = _open({"kind": "inflight", "op": "claim", "model": model, "closure": closure, "store_root": store_root})
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


def report_done(conn: transport.Channel, code: int, *, required: bool = False) -> None:
    try:
        _send(conn, {"exit": int(code)})
    except OSError:
        if required:
            raise
    finally:
        conn.close()


def report_result(conn: transport.Channel, event: dict) -> None:
    with contextlib.suppress(OSError):
        _send(conn, {"event": event})


def report_artifact_result(conn: transport.Channel, result: dict) -> None:
    # A failed result publication is a failed operation, never a lost success
    # silently reported to consumers that attached to this producer.
    _send(conn, {"artifactResult": result})


def detach_artifact_owner(conn: transport.Channel) -> None:
    _send(conn, {"ownerDetached": True})


def wait_attached(conn: transport.Channel, *, on_event: Callable[[dict], None] | None = None,
                  on_artifact_result: Callable[[dict], None] | None = None, cancelled=None) -> int:
    try:
        while True:
            if cancelled is not None and cancelled():
                return 1
            raw = conn.recv(.1 if cancelled is not None else None)
            if raw is None:
                continue
            if not raw:
                break
            frame = json.loads(raw.decode("utf-8"))
            if isinstance(frame.get("event"), dict) and on_event is not None:
                on_event(frame["event"])
            if isinstance(frame.get("artifactResult"), dict) and on_artifact_result is not None:
                on_artifact_result(frame["artifactResult"])
            if "exit" in frame:
                return int(frame["exit"])
    except (OSError, ValueError, TypeError):
        pass
    finally:
        conn.close()
    return 1
