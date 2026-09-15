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
    fields = {"kind", "tree", "cids", "producer", "expected_objects", "force"}
    required = {"kind", "tree", "cids", "producer"}
    if kind != "surfaces" or not required <= set(request) or set(request) - fields:
        raise ValueError("artifact request must be producer or surfaces with closed immutable inputs")
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
    return {"kind": kind, "tree": _digest(request["tree"], "tree"), "cids": sorted(cids),
            "producer": _producer(request["producer"]), "expected_objects": dict(sorted(expected.items())), "force": force}


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
    """An actual worker request's store; never inferred from a subject/env flag."""
    previous = getattr(_WORKER, "root", None)
    _WORKER.root = store_path(root)
    try:
        yield
    finally:
        _WORKER.root = previous


def _can_inline(root):
    return (getattr(_WORKER, "root", None) == root and broker.current_lease() is not None
            and store_path() == root)


def execute(request):
    """Worker-only native entry. Source and model lookup are absent by design."""
    request = normalize_request(request)
    from cadgen.store import surfaces

    if request["kind"] == "producer":
        return surfaces.producer_identity()
    return surfaces.derive(request["tree"], request["cids"], producer=request["producer"],
                           expected_objects=request["expected_objects"], force=request["force"])


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
        process = subprocess.Popen([sys.executable, "-m", "cadgen.daemon.artifacts"],
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
    """Start a typed artifact operation without importing the CAD kernel here."""
    request = normalize_request(request)
    root = store_path(store_root)
    future = ArtifactFuture()
    if _can_inline(root):
        future._begin()
        try:
            future._complete(validate_result(request, result_frame(request, execute(request))))
        except Exception as exc:
            future._complete(error=exc)
        return future

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
