"""Internal artifact operations, independent of source models and document paths.

Only workers import the native surface producer. Requests contain immutable pins,
never a script, a declared output, or an instruction to run arbitrary Python.
"""

from __future__ import annotations

import contextlib
import copy
from concurrent.futures import Future
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading

from cadgen.daemon import broker

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_CID = re.compile(r"[0-9a-f]{16}\Z")
_PRODUCER_FIELDS = {"scheme", "surfFormat", "build123d", "ocp", "cadqueryOcp"}
# The most mesh keys one request may name: a mesh probe's bound (store/tess_cache.py).
MESH_KEYS_MAX = 256
# The most component cuts one sections request may name.
SECTION_ITEMS_MAX = 256
# How ``deal`` sizes build-pool jobs. A job takes a warm worker when the daemon has
# one (``pool.spare_count``); a job past them starts a worker, whose kernel import
# took 4-5 s on a busy 4-core machine. So the warm workers share any work of at
# least DEAL_PER_JOB items, and a job that starts a worker is dealt only when there
# is enough work to repay that start: about 32 components' surface extraction, or
# 96 components' meshing (motorbike: 0.36 s and 0.11 s a component).
DEAL_PER_JOB = 4
SURFACES_PER_STARTED_WORKER = 32
MESHES_PER_STARTED_WORKER = 96
# A cut is the common of a component's solids with the plane: about 60 ms a component
# (hypercar: 222 crossing cuts, 13 s in one job), so some 40 cuts repay a worker's start.
# Measured on hypercar at fresh planes, one per 256 cuts: 8.6-14.1 s; one per 32: 7.5-9.8 s.
SECTIONS_PER_STARTED_WORKER = 32


class ArtifactJobError(RuntimeError):
    """Artifact work failed; no unaccounted fallback has been attempted."""


class ArtifactDetached(ArtifactJobError):
    """This subscriber left; another subscriber may still need the operation."""


def _digest(value, name, pattern=_HASH):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"artifact {name} must be a lowercase {64 if pattern is _HASH else 16}-digit hex pin")
    return value


def _producer(value):
    if not isinstance(value, dict) or set(value) != _PRODUCER_FIELDS:
        raise ValueError("artifact producer requires exactly scheme, surfFormat, build123d, ocp, cadqueryOcp")
    result = {}
    for name in ("scheme", "surfFormat"):
        if type(value[name]) is not int or value[name] <= 0:
            raise ValueError(f"artifact producer {name} must be a positive integer")
        result[name] = value[name]
    for name in ("build123d", "ocp", "cadqueryOcp"):
        item = value[name]
        if not isinstance(item, str) or not item.strip() or item.lower() in {"unknown", "none"}:
            raise ValueError(f"artifact producer {name} must identify the actual loaded version")
        result[name] = item
    return result


def normalize_request(request):
    """Own a closed, canonical JSON request without consulting any source/store."""
    if not isinstance(request, dict):
        raise ValueError("artifact request must be an object")
    kind = request.get("kind")
    if kind == "producer" and set(request) == {"kind"}:
        return {"kind": "producer"}
    if kind == "meshes" and set(request) == {"kind", "keys"}:
        return {"kind": "meshes", "keys": _mesh_keys(request["keys"])}
    if kind == "sections" and set(request) == {"kind", "items"}:
        return {"kind": "sections", "items": _section_items(request["items"])}
    fields = {"kind", "tree", "cids", "producer", "expected_objects", "force", "tessellations"}
    required = {"kind", "tree", "cids", "producer"}
    if kind != "surfaces" or not required <= set(request) or set(request) - fields:
        raise ValueError("artifact request must be producer, surfaces, meshes or sections with closed immutable inputs")
    cids = request["cids"]
    if not isinstance(cids, (list, tuple)) or not cids:
        raise ValueError("artifact cids must be a nonempty list")
    cids = [_digest(cid, "cid", _CID) for cid in cids]
    if len(cids) != len(set(cids)):
        raise ValueError("artifact cids must not contain duplicates")
    expected = request.get("expected_objects", {})
    if not isinstance(expected, dict):
        raise ValueError("artifact expected_objects must map surface-input pins to object pins")
    expected = {_digest(key, "surface input"): _digest(value, "surface object") for key, value in expected.items()}
    force = request.get("force", False)
    if type(force) is not bool:
        raise ValueError("artifact force must be a boolean")
    from cadgen.store.meshes import normalize_tessellations

    # The meshes to make with the surfaces, in one canonical spelling; a request
    # naming none keeps the shape (and key) it always had.
    tessellations = [{"chordTolerance": chord, "angleTolerance": angle}
                     for chord, angle in normalize_tessellations(request.get("tessellations"))]
    return {"kind": kind, "tree": _digest(request["tree"], "tree"), "cids": sorted(cids),
            "producer": _producer(request["producer"]), "expected_objects": dict(sorted(expected.items())), "force": force,
            **({"tessellations": tessellations} if tessellations else {})}


def _mesh_keys(keys):
    """The tessellation keys a meshes request names, in one canonical order: each a
    key this cadgen writes at tolerances any request may ask to have meshed
    (``store.meshes.meshable_key``), none twice."""
    from cadgen.store.meshes import meshable_key
    from cadgen.tessellation_policy import TESSELLATION_CEILINGS, TESSELLATION_FLOORS

    if not isinstance(keys, (list, tuple)) or not keys or len(keys) > MESH_KEYS_MAX:
        raise ValueError(f"artifact meshes keys must be a nonempty list of at most {MESH_KEYS_MAX}")
    if any(meshable_key(key) is None for key in keys):
        bounds = " and ".join(f"{name} {TESSELLATION_FLOORS[name]:g} to {TESSELLATION_CEILINGS[name]:g}"
                              for name in TESSELLATION_FLOORS)
        raise ValueError(f"artifact meshes keys must be this cadgen's tessellation keys, at {bounds}")
    if len(set(keys)) != len(keys):
        raise ValueError("artifact meshes keys must not contain duplicates")
    return sorted(keys)


def _section_items(items):
    """The component cuts a sections request names, canonical (``store.sections.normalize_item``),
    in one order, none twice."""
    from cadgen.store.sections import normalize_item

    if not isinstance(items, (list, tuple)) or not items or len(items) > SECTION_ITEMS_MAX:
        raise ValueError(f"artifact sections items must be a nonempty list of at most {SECTION_ITEMS_MAX}")
    normalized = [normalize_item(item) for item in items]
    keys = [json.dumps(item, sort_keys=True, separators=(",", ":")) for item in normalized]
    if len(set(keys)) != len(keys):
        raise ValueError("artifact sections items must not contain duplicates")
    return [item for _key, item in sorted(zip(keys, normalized))]


def request_key(request):
    encoded = json.dumps(normalize_request(request), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def store_path(value=None):
    if value is None:
        from cadgen.store.paths import store_root

        value = store_root()
    if not isinstance(value, (str, os.PathLike)) or not str(value):
        raise ValueError("artifact store_root must be an explicit nonempty path")
    return str(Path(value).resolve())


def result_frame(request, result):
    # Round-tripping rejects native wrappers and nonfinite values, and prevents a
    # producer from mutating a result after publication to attached clients.
    value = json.loads(json.dumps(result, allow_nan=False))
    return {"request": request_key(request), "result": value}


def validate_result(request, payload):
    if not isinstance(payload, dict) or set(payload) != {"request", "result"} or payload["request"] != request_key(request):
        raise ArtifactJobError("artifact result does not match the complete requested inputs")
    return result_frame(request, payload["result"])["result"]


_WORKER = threading.local()


@contextlib.contextmanager
def worker_context(root):
    """The store this thread's kernel work is for: a daemon worker's request, or a
    model build in whatever process runs it (``generation``), never a door or a
    server. Under a CPU lease for that store, the artifact work the thread asks for
    runs here, where the kernel is already loaded (:func:`resolve_artifacts`)."""
    previous = getattr(_WORKER, "root", None)
    _WORKER.root = store_path(root)
    try:
        yield
    finally:
        _WORKER.root = previous


def _can_inline(root):
    return (getattr(_WORKER, "root", None) == root and broker.current_lease() is not None
            and store_path() == root)


def execute(request, *, keep_going=None):
    """Worker-only native entry. Source and model lookup are absent by design.

    ``keep_going`` is asked before each derivation and each mesh (``surfaces.derive``,
    ``surfaces.produce_meshes``): a daemon worker's asks its supervisor whether anyone
    still wants the job."""
    request = normalize_request(request)
    from cadgen.store import surfaces

    if request["kind"] == "producer":
        return surfaces.producer_identity()
    if request["kind"] == "meshes":
        return surfaces.produce_meshes(request["keys"], keep_going=keep_going)
    if request["kind"] == "sections":
        from cadgen.store import sections

        return sections.produce(request["items"], keep_going=keep_going)
    meshes = {"tessellations": request["tessellations"]} if request.get("tessellations") else {}
    return surfaces.derive(request["tree"], request["cids"], producer=request["producer"],
                           expected_objects=request["expected_objects"], force=request["force"],
                           keep_going=keep_going, **meshes)


class ArtifactFuture(Future):
    """Completion/result for one artifact operation, with no source-model state."""

    def __init__(self):
        super().__init__()
        self._subscriber_lock = threading.Lock()
        self._detached = False
        self._settled = False
        self._detach_action = None

    @property
    def detached(self):
        with self._subscriber_lock:
            return self._detached

    def detach(self):
        """Retire only this subscription, including when its work is running."""
        with self._subscriber_lock:
            if self._settled or self.done():
                return False
            self._detached = True
            self._settled = True
            action, self._detach_action = self._detach_action, None
        try:
            if action is not None:
                action()
        finally:
            self.set_exception(ArtifactDetached("artifact subscriber detached"))
        return True

    def _bind_detach(self, action):
        with self._subscriber_lock:
            detached = self._detached
            self._detach_action = None if detached else action
        if detached and action is not None:
            action()

    def _begin(self):
        with self._subscriber_lock:
            return not self._detached and self.set_running_or_notify_cancel()

    def _complete(self, value=None, error=None):
        with self._subscriber_lock:
            self._detach_action = None
            if self._settled or self.done():
                return
            self._settled = True
        if error is None:
            self.set_result(value)
        else:
            self.set_exception(error)

    def result(self, timeout=None):
        # The calling thread owns its lease. A background dispatcher must never
        # release it, and an already finished inline result need not yield it.
        if self.done():
            return copy.deepcopy(super().result(timeout))
        with broker.yielded():
            return copy.deepcopy(super().result(timeout))


_PRIVATE_LOCK = threading.Lock()
_PRIVATE = None
_PRIVATE_USERS = 0


def _transient_endpoint():
    """Share a transient broker, passing its identity only in child env."""
    global _PRIVATE, _PRIVATE_USERS
    endpoint = broker._endpoint()
    if endpoint is not None:
        return endpoint, lambda: None
    with _PRIVATE_LOCK:
        if _PRIVATE is None:
            _PRIVATE = broker.PrivateBroker()
        private = _PRIVATE
        _PRIVATE_USERS += 1

    def release():
        global _PRIVATE, _PRIVATE_USERS
        with _PRIVATE_LOCK:
            _PRIVATE_USERS -= 1
            if _PRIVATE_USERS == 0:
                _PRIVATE = None
                private.close()

    return (private.address, private.key), release


def _run_transient(request, root, env, endpoint, *, subscriber=None):
    ticket = broker.claim_artifact(request, store_root=root, endpoint=endpoint)
    role, connection = ticket
    received = []

    def receive(payload):
        if received:
            raise ArtifactJobError("artifact worker returned more than one result")
        received.append(validate_result(request, payload))

    if role == "attached":
        if subscriber is not None:
            subscriber._bind_detach(connection.close)
        code = broker.wait_attached(connection, on_artifact_result=receive,
                                    cancelled=(lambda: subscriber.detached) if subscriber is not None else None)
        if code or not received:
            raise ArtifactJobError("attached artifact operation failed or returned no result")
        return received[0]
    process = None
    code = 1
    chunks = []
    producer_done, orphaned = threading.Event(), threading.Event()
    send_lock = threading.Lock()

    def detach_owner():
        # This channel belongs to the producer pump. Detaching its original
        # subscriber must not close it while attached consumers need results.
        with contextlib.suppress(OSError, ValueError, TypeError), send_lock:
            broker.detach_artifact_owner(connection)

    if subscriber is not None:
        subscriber._bind_detach(detach_owner)

    def watch_owner():
        while not producer_done.is_set():
            try:
                raw = connection.recv(.1)
            except (OSError, ValueError, TypeError):
                raw = b""
            if raw is None:
                continue
            # The broker sends only an orphan notification on this producer
            # channel. EOF or any unexpected frame is also a terminal control
            # failure, never permission to keep unobserved native work running.
            orphaned.set()
            if process is not None and process.poll() is None:
                with contextlib.suppress(OSError):
                    process.terminate()
            return

    watcher = threading.Thread(target=watch_owner, name="cadgen-artifact-owner", daemon=True)
    try:
        watcher.start()
        from cadgen.daemon.executors import worker_env

        child_env = worker_env(env)
        child_env.update({broker.BROKER_ADDRESS_VAR: endpoint[0], broker.BROKER_KEY_VAR: endpoint[1].decode("ascii"),
                          "CADGEN_DAEMON": "0", "CADGEN_CACHE_DIR": root})
        if orphaned.is_set():
            raise ArtifactDetached("artifact producer lost its last subscriber")
        process = subprocess.Popen([sys.executable, "-P", "-m", "cadgen.daemon.artifacts"],
                                   env=child_env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="backslashreplace")
        if orphaned.is_set():
            raise ArtifactDetached("artifact producer lost its last subscriber")
        payload = {"tool": "artifact", "argv": [], "artifact": request, "store_root": root,
                   "env": {}, "root_id": env.get("CADGEN_ROOT_ID")}
        process.stdin.write(json.dumps(payload) + "\n")
        process.stdin.close()
        exit_seen = None
        for line in process.stdout:
            if exit_seen is not None:
                raise ArtifactJobError("artifact worker emitted data after its terminal frame")
            try:
                frame = json.loads(line)
            except ValueError:
                chunks.append(line)
                continue
            if not isinstance(frame, dict):
                raise ArtifactJobError("malformed artifact worker frame")
            if "artifactResult" in frame:
                receive(frame["artifactResult"])
                with send_lock:
                    broker.report_artifact_result(connection, frame["artifactResult"])
            elif "exit" in frame:
                exit_seen = int(frame["exit"])
            elif frame.get("stream") in {"stdout", "stderr"}:
                chunks.append(str(frame.get("data") or ""))
            else:
                raise ArtifactJobError("unexpected artifact worker frame")
        return_code = process.wait()
        if return_code or exit_seen != 0 or not received or orphaned.is_set():
            raise ArtifactJobError("artifact worker failed or returned no result: " + "".join(chunks).strip())
        code = 0
        return received[0]
    finally:
        producer_done.set()
        if watcher.ident is not None:
            watcher.join(timeout=1)
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            for stream in (process.stdin, process.stdout):
                if stream is not None:
                    stream.close()
        with send_lock:
            broker.report_done(connection, code, required=not orphaned.is_set())


def submit_artifact(request, *, store_root=None):
    """Start a typed artifact operation: in this process when it runs kernel work for
    this store under a CPU lease (:func:`worker_context`), else as a build-pool job,
    without importing the CAD kernel here."""
    request = normalize_request(request)
    root = store_path(store_root)
    return _run_inline(request) if _can_inline(root) else _dispatch(request, root)


def _run_inline(request):
    future = ArtifactFuture()
    future._begin()
    try:
        future._complete(validate_result(request, result_frame(request, execute(request))))
    except Exception as exc:
        future._complete(error=exc)
    return future


def _dispatch(request, root):
    """``request`` as a build-pool job, on a thread of its own."""
    future = ArtifactFuture()
    from cadgen.daemon import client
    from cadgen.daemon.executors import use_daemon

    daemon = use_daemon()
    env = dict(os.environ)
    dependency = getattr(_WORKER, "root", None) is not None or broker.current_lease() is not None
    # Capture before the dispatch thread: every request's root/dependency/env is
    # its caller's, not whichever HTTP thread happens to run next.
    payload = client.artifact_payload(request, store_root=root, dependency=dependency) if daemon else None
    endpoint, release = (None, lambda: None) if daemon else _transient_endpoint()

    def run():
        try:
            if not future._begin():
                return
            value = (client.run_artifact(payload, subscriber=future) if daemon
                     else _run_transient(request, root, env, endpoint, subscriber=future))
            future._complete(value)
        except Exception as exc:
            future._complete(error=exc)
        finally:
            future._bind_detach(None)
            release()

    try:
        threading.Thread(target=run, name="cadgen-artifact", daemon=True).start()
    except Exception:
        release()
        raise
    return future


def resolve_artifact(request, *, store_root=None):
    """Resolve one operation; waits yield the caller's CPU lease."""
    return submit_artifact(request, store_root=store_root).result()


def resolve_artifacts(requests, *, store_root=None):
    """Resolve several operations at once, each on a build-pool worker of its own
    (only identical requests share one), and return their results in order once
    every one has finished. The first failure is raised then, never sooner: what
    the others stored is kept, and a retry finds it. A caller that runs kernel work
    for this store under a CPU lease (:func:`worker_context`: a build exporting its
    own meshes) runs the first in its own process while the rest go to the pool --
    :func:`deal` gives such a caller a second share only for work that repays
    starting a worker."""
    requests = list(requests)
    root = store_path(store_root)
    if requests and _can_inline(root):
        # The pool's shares first, so they run while this process does its own.
        rest = [_dispatch(normalize_request(request), root) for request in requests[1:]]
        futures = [submit_artifact(requests[0], store_root=root), *rest]
    else:
        futures = [submit_artifact(request, store_root=store_root) for request in requests]
    results, failure = [], None
    for future in futures:
        try:
            results.append(future.result())
        except Exception as error:  # noqa: BLE001 - raised once the rest are done
            failure = failure or error
            results.append(None)
    if failure is not None:
        raise failure
    return results


def deal(items, *, per_started_worker, parts=None):
    """``items`` dealt round-robin into nonempty lists, one per build-pool job: the
    daemon's warm workers share them (at least ``DEAL_PER_JOB`` items a job), and
    one more job is dealt for every ``per_started_worker`` items -- each such job
    starts a worker -- up to ``parts``, by default one per CPU slot
    (``broker.job_limit``): the most jobs that run at once. For a build's own work
    the first list is the build's, done in its process (:func:`resolve_artifacts`),
    and only the started-worker rule deals more."""
    from cadgen.daemon.executors import use_daemon
    from cadgen.daemon.pool import spare_count

    items = list(items)
    if not items:
        return []
    warm = spare_count() if use_daemon() else 0
    limit = max(1, int(parts) if parts else broker.job_limit())
    started = len(items) // max(1, int(per_started_worker))
    # A build's own work (``worker_context``) does the first share in its own
    # process, so it shares nothing until the work repays starting a worker. Handing
    # it to the warm spares as well was measured slower: the build has bound one of
    # them, and the next share waited on a kernel import.
    count = started if _can_inline(store_path()) else max(min(warm, len(items) // DEAL_PER_JOB), started)
    count = min(limit, max(1, count))
    return [items[index::count] for index in range(count)]


def _main():
    # Private one-shot worker, not an author CLI. No import of store.surfaces
    # occurs until worker._run has acquired the required broker lease.
    from cadgen.daemon import worker

    request = json.loads(sys.stdin.readline())
    worker._apply_request_env(request)
    code = worker._run(request)
    worker._emit({"exit": code})
    return code


if __name__ == "__main__":
    raise SystemExit(_main())
