"""Build-pool artifact jobs, independent of source models: this runtime's producer
(``kind: producer``); the display data of the parts a view found missing from the
store (``kind: display``: one request, one job, one worker); one face's exact area and
centroid, measured on its component's stored BREP for a view or a mate's axis that asks
(``kind: measure``, ``store.parts.measure_face``); a stored tree written to
a staged STEP (``kind: export``) and a written document checked against the tree it
was written from (``kind: verify``, ``store/exports.py``). A job runs on a daemon
worker, or, with no daemon (``CADGEN_DAEMON=0``), in the process that asks, on a
thread of its own: never a process per job. The caller's own thread never imports
the native producer. Requests contain immutable pins and may name a staged file or a
document, never a script, a declared output, or an instruction to run arbitrary
Python. A verify is keyed by the bytes and the tree, not by the path it reads them at,
so every door asking about one document joins one job.
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
import threading

from cadgen.daemon import broker

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_CID = re.compile(r"[0-9a-f]{16}\Z")
_PRODUCER_FIELDS = {"build123d", "ocp", "cadqueryOcp"}


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
        raise ValueError("artifact producer requires exactly build123d, ocp, cadqueryOcp")
    result = {}
    for name in ("build123d", "ocp", "cadqueryOcp"):
        item = value[name]
        if not isinstance(item, str) or not item.strip() or item.lower() in {"unknown", "none"}:
            raise ValueError(f"artifact producer {name} must identify the actual loaded version")
        result[name] = item
    return result


def _path(value, name):
    if not isinstance(value, str) or not value or not os.path.isabs(value):
        raise ValueError(f"artifact {name} must be an absolute path")
    if Path(value).suffix.lower() not in (".step", ".stp"):
        raise ValueError(f"artifact {name} must name a STEP document")
    return str(Path(value))


def normalize_request(request):
    """Own a closed, canonical JSON request without consulting any source/store."""
    if not isinstance(request, dict):
        raise ValueError("artifact request must be an object")
    kind = request.get("kind")
    if kind == "producer" and set(request) == {"kind"}:
        return {"kind": "producer"}
    if kind == "export" and set(request) == {"kind", "tree", "out", "names"}:
        if not isinstance(request["names"], bool):
            raise ValueError("artifact names must be a boolean")
        return {"kind": kind, "tree": _digest(request["tree"], "tree"), "out": _path(request["out"], "out"),
                "names": request["names"]}
    if kind == "measure" and set(request) == {"kind", "tree", "cid", "face"}:
        face = request["face"]
        if type(face) is not int or face < 1:
            raise ValueError("artifact face must be a face ordinal, an integer from 1")
        return {"kind": kind, "tree": _digest(request["tree"], "tree"), "cid": _digest(request["cid"], "cid", _CID),
                "face": face}
    if kind == "verify" and set(request) == {"kind", "tree", "document", "sha256", "producer"}:
        producer = request["producer"]
        return {"kind": kind, "tree": _digest(request["tree"], "tree"),
                "document": _path(request["document"], "document"), "sha256": _digest(request["sha256"], "sha256"),
                "producer": None if producer is None else _producer(producer)}
    if kind != "display" or set(request) != {"kind", "tree", "cids", "producer"}:
        raise ValueError("artifact request must be producer; display with exactly tree, cids and producer; "
                         "measure with tree, cid and face; export with tree, out and names; "
                         "or verify with tree, document, sha256 and producer")
    cids = request["cids"]
    if not isinstance(cids, (list, tuple)) or not cids:
        raise ValueError("artifact cids must be a nonempty list")
    cids = [_digest(cid, "cid", _CID) for cid in cids]
    if len(cids) != len(set(cids)):
        raise ValueError("artifact cids must not contain duplicates")
    return {"kind": kind, "tree": _digest(request["tree"], "tree"), "cids": sorted(cids),
            "producer": _producer(request["producer"])}


def request_key(request):
    """What one job answers: the request, but for a verify the path it reads its bytes
    at, which are named by their digest."""
    request = normalize_request(request)
    if request["kind"] == "verify":
        request = {key: value for key, value in request.items() if key != "document"}
    encoded = json.dumps(request, sort_keys=True, separators=(",", ":"), allow_nan=False)
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
    """The store this thread's job is for: a daemon worker's request. An artifact job the
    thread submits while it runs is that job's dependency (``client.artifact_payload``)."""
    previous = getattr(_WORKER, "root", None)
    _WORKER.root = store_path(root)
    try:
        yield
    finally:
        _WORKER.root = previous


def execute(request, *, keep_going=None):
    """Worker-only native entry. Source and model lookup are absent by design.

    ``keep_going`` is asked before each part (``parts.derive``): a daemon worker's asks
    its supervisor whether anyone still wants the job. An export and a verify are one step
    each, and a verify is finished whoever still waits for it: its answer is the store's."""
    request = normalize_request(request)
    from cadgen.store import parts

    if request["kind"] == "producer":
        return parts.producer_identity()
    if request["kind"] == "measure":
        return parts.measure_face(request["tree"], request["cid"], request["face"])
    if request["kind"] in ("export", "verify"):
        from cadgen.store import exports

        if request["kind"] == "export":
            return exports.export_step(request["tree"], Path(request["out"]), names=request["names"])
        return exports.verify_document(request["tree"], Path(request["document"]), request["sha256"],
                                       producer=request["producer"])
    return parts.derive(request["tree"], request["cids"], producer=request["producer"], keep_going=keep_going)


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
        # release it, and an already finished result need not yield it.
        if self.done():
            return copy.deepcopy(super().result(timeout))
        with broker.yielded():
            return copy.deepcopy(super().result(timeout))


def submit_artifact(request, *, store_root=None):
    """Start a typed artifact operation as ONE build-pool job, on a thread of its own,
    without importing the CAD kernel on the caller's thread: a daemon worker's, or with no
    daemon this process's (:func:`_run_here`), against the store it names, which must then
    be this process's. A caller that waits for it yields the slot it holds (``result``)."""
    request = normalize_request(request)
    root = store_path(store_root)
    future = ArtifactFuture()
    from cadgen.daemon import client
    from cadgen.daemon.executors import use_daemon

    daemon = use_daemon()
    payload = None
    if daemon:
        dependency = getattr(_WORKER, "root", None) is not None or broker.current_lease() is not None
        # Captured before the dispatch thread: every request's root/dependency/env is
        # its caller's, not whichever HTTP thread happens to run next.
        payload = client.artifact_payload(request, store_root=root, dependency=dependency)
    elif root != store_path():
        raise ValueError(f"with no daemon an artifact job runs in this process, on its store, not {root}")

    def run():
        try:
            if not future._begin():
                return
            value = (client.run_artifact(payload, subscriber=future) if daemon
                     else _run_here(request, keep_going=lambda: not future.detached))
            future._complete(value)
        except Exception as exc:
            future._complete(error=exc)
        finally:
            future._bind_detach(None)

    threading.Thread(target=run, name="cadgen-artifact", daemon=True).start()
    return future


def _run_here(request, *, keep_going):
    """The job in this process, with no daemon to run it and no broker to take a slot
    from; asking ``keep_going`` before each derivation, which stops once its one
    subscriber has left. The result is what a worker's would be: plain JSON. What the
    job reads on its thread -- the file an export wrote, parsed by its verify --
    is cadgen's own, never an input of a build in progress (``filetrace.paused``)."""
    from cadgen._internal.filetrace import paused

    with paused():
        return result_frame(request, execute(request, keep_going=keep_going))["result"]


def resolve_artifact(request, *, store_root=None):
    """Resolve one operation; waits yield the caller's CPU lease."""
    return submit_artifact(request, store_root=store_root).result()
