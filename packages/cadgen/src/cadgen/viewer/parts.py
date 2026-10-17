"""A runtime view's display data, read from the store: each component's part record
(``cadgen.store.parts``: its display mesh and selector table), which the build that
made the tree derived. A part the store lacks is derived by ONE build-pool job for the
request (``kind: display``); this server never derives.

And one face's exact area and centroid (``POST /__cad/measure``, :class:`FaceMeasures`),
which no part carries: the store's answer when it holds one, else one build-pool job
(``kind: measure``, ``store.parts.measure_face``) that every request for the face joins
while it runs, waited for only as long as the app's hold, then a 202 that has the page
ask again; this server never measures.

Tokens are disposable subscribers to that job, never persistent store
entries or editing sessions. Every poll repeats and validates its immutable
inputs. Disconnect/cancellation detaches that subscriber, not another reader,
and never kills a derivation: the daemon finishes the one in hand into the store
and starts no other for a job nobody is subscribed to.
"""

from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import wait as wait_for
import json
import logging
import os
import threading
import time
import uuid

from cadgen.store import parts
from cadgen.store.objects import object_path
from cadgen.store.paths import store_root
from cadgen.store.trees import COMPONENT_OBJECTS, capture_tree

LOG = logging.getLogger("cadgen.viewer.parts")

MAX_COMPONENTS = 64
MAX_SUBSCRIBERS = 256
SUBSCRIBER_IDLE_SECONDS = 120
# How long a measure request waits on its job before it answers 202: a face measures inside it
# but where its component is large to decode, which costs one request per hold.
MEASURE_HOLD_SECONDS = 2.0
# How long a finished measure's answer is kept for the requests that follow it, and how many.
MEASURED_SECONDS = 30.0
MEASURED_MAX = 64

# A tree hash names its bytes, and those bytes name every component the tree pins
# with its entry, so a tree's component map cannot change. The viewer verifies it
# once per process (capture_tree, the complete closure) and keeps it, rather than
# checking the whole closure again on every request: the browser asks about each
# component separately, so that made a model's first open quadratic in its size.
# What can change is whether the objects are still there, since eviction and GC
# delete files. So every request stats the tree's object and the objects of each
# component it names, and a missing one sends the tree back through the complete
# verification, which fails as it always did. A component a request does not name
# is not looked at: a derivation verifies its whole closure before it writes.
PINNED_TREES = 8
PINNED_COMPONENTS = 100_000
_PINS: OrderedDict[tuple[str, str], "_Pin"] = OrderedDict()
_PINS_LOCK = threading.Lock()


def _is_digest(value) -> bool:
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


class _Pin:
    """One verified tree's component map (read-only) and where each object lies."""

    __slots__ = ("components", "paths", "tree_path")

    def __init__(self, tree: str, components: dict):
        self.components = components
        self.paths: dict[str, tuple[str, ...]] = {}
        for cid, entry in components.items():
            self.paths[cid] = tuple(str(object_path(entry[field])) for field in COMPONENT_OBJECTS
                                    if entry.get(field))
        self.tree_path = str(object_path(tree))

    def present(self, cids) -> bool:
        """Whether the tree's object and every object of ``cids`` are still on disk."""
        try:
            os.stat(self.tree_path)
            for cid in cids:
                for path in self.paths[cid]:
                    os.stat(path)
        except OSError:
            return False
        return True


def _pinned(tree: str, cids=()) -> _Pin:
    """``tree``'s verified component map, with the objects of ``cids`` present.

    A miss, or an object gone since the map was verified, verifies the complete
    closure again (``capture_tree``), raising for a missing or damaged one."""
    key = (str(store_root().resolve()), tree)
    with _PINS_LOCK:
        pin = _PINS.get(key)
        if pin is not None:
            _PINS.move_to_end(key)
    if pin is not None:
        if pin.present(cids):
            return pin
        with _PINS_LOCK:
            if _PINS.get(key) is pin:
                del _PINS[key]
    descriptor, _ = capture_tree(tree, retain_payloads=False)
    pin = _Pin(tree, descriptor["components"])
    with _PINS_LOCK:
        _PINS[key] = pin
        _PINS.move_to_end(key)
        total = sum(len(item.components) for item in _PINS.values())
        while len(_PINS) > 1 and (len(_PINS) > PINNED_TREES or total > PINNED_COMPONENTS):
            _old_key, old = _PINS.popitem(last=False)
            total -= len(old.components)
    return pin


def _request(body: bytes) -> tuple[dict, dict, dict, str | None]:
    if len(body) > 128 * 1024:
        raise ValueError("part request is too large")
    value = json.loads(body)
    fields = {"tree", "viewId", "producer", "components"}
    if type(value) is not dict or not fields <= set(value) or set(value) - fields - {"job"}:
        raise ValueError("part request requires tree, viewId, producer and components")
    producer = parts.producer_fields(value["producer"])
    tree = value["tree"]
    if not _is_digest(tree):
        raise ValueError("part request names no tree")
    pin = _pinned(tree)
    view_id = parts._view_id(tree, producer)
    if value["viewId"] != view_id:
        raise ValueError("part request mixes runtime views")
    components = value["components"]
    if type(components) is not list or not 0 < len(components) <= MAX_COMPONENTS:
        raise ValueError("part request must name between 1 and 64 components")
    selected = {}
    for item in components:
        if type(item) is not dict or set(item) != {"cid", "part"}:
            raise ValueError("invalid part component request")
        cid = item["cid"]
        entry = pin.components.get(cid) if type(cid) is str else None
        key = parts.part_key(entry, producer) if entry is not None else None
        if entry is None or cid in selected or item["part"] != key:
            raise ValueError("part request names an unpinned component or part")
        selected[cid] = key
    job = value.get("job")
    if job is not None and (type(job) is not str or len(job) != 32 or any(c not in "0123456789abcdef" for c in job)):
        raise ValueError("invalid part subscriber token")
    operation = {"kind": "display", "tree": value["tree"], "cids": sorted(selected), "producer": producer}
    # The named components' objects, still on disk; the map itself is read-only.
    _pinned(tree, selected)
    return {"viewId": view_id}, selected, operation, job


def _measure_request(body: bytes) -> tuple[dict, dict]:
    """``(component entry, artifact operation)`` of a measure request: the view the page
    holds (``tree``, ``viewId``, ``producer``), a component of its tree and the part key the
    view gave it (``cid``, ``part``), and a face of it by ordinal (``face``)."""
    if len(body) > 4 * 1024:
        raise ValueError("measure request is too large")
    value = json.loads(body)
    fields = {"tree", "viewId", "producer", "cid", "part", "face"}
    if type(value) is not dict or set(value) != fields:
        raise ValueError("measure request requires tree, viewId, producer, cid, part and face")
    producer = parts.producer_fields(value["producer"])
    tree = value["tree"]
    if not _is_digest(tree):
        raise ValueError("measure request names no tree")
    pin = _pinned(tree)
    if value["viewId"] != parts._view_id(tree, producer):
        raise ValueError("measure request mixes runtime views")
    cid = value["cid"]
    entry = pin.components.get(cid) if type(cid) is str else None
    if entry is None or value["part"] != parts.part_key(entry, producer):
        raise ValueError("measure request names an unpinned component or part")
    face = value["face"]
    if type(face) is not int or face < 1:
        raise ValueError("measure request names no face")
    _pinned(tree, (cid,))
    return entry, {"kind": "measure", "tree": tree, "cid": cid, "face": face}


class FaceMeasures:
    """``POST /__cad/measure``'s jobs: one per face, off the request, joined by every request
    for it. ``hold_seconds`` is how long a request waits on a job before answering 202, and
    ``retry_ms`` the wait the 202 asks of the page before it asks again: the CAD Viewer holds
    and has the page ask again at once; the CAD app's tunnel, whose calls share a host's few
    slots, holds briefly and has its page come back a moment later (``cadgen.mcp.tunnel``)."""

    def __init__(self, *, hold_seconds: float = MEASURE_HOLD_SECONDS, retry_ms: int = 0, clock=time.monotonic):
        self.hold_seconds = hold_seconds
        self.retry_ms = retry_ms
        self._clock = clock
        self._lock = threading.Lock()
        # request key -> (future, when it finished or None)
        self._jobs: dict[str, list] = {}

    def response(self, body: bytes) -> tuple[int, dict]:
        """``(status, body)``: the face's ``{"face", "area", "center"}`` at 200, 202 while it is
        measured, or ``{"error": ...}`` at 400 for a face its job could not measure."""
        from cadgen.daemon.artifacts import request_key

        entry, operation = _measure_request(body)
        face = operation["face"]
        remembered = parts.remembered_face_measure(entry, face)
        if remembered is not None:
            return 200, {"face": face, **remembered}
        future = self._job(request_key(operation), operation)
        if not wait_for([future], timeout=self.hold_seconds).done:
            return 202, {"state": "measuring", "retryMs": self.retry_ms}
        try:
            value = future.result()
        except Exception as error:  # noqa: BLE001 - the face's own failure, answered to the page
            LOG.warning("face measure failed for %s face %d: %r", operation["cid"], face, error)
            return 400, {"error": str(error) or type(error).__name__}
        return 200, {"face": face, **value}

    def _job(self, key: str, operation: dict):
        """The job measuring this face: the one running, or finished recently enough to answer
        from, else a new one."""
        from cadgen.daemon.artifacts import submit_artifact

        now = self._clock()
        with self._lock:
            finished = sorted((job[1], name) for name, job in self._jobs.items() if job[1] is not None)
            surplus = len(finished) - MEASURED_MAX
            for index, (finished_at, name) in enumerate(finished):
                if index < surplus or now - finished_at > MEASURED_SECONDS:
                    del self._jobs[name]
            job = self._jobs.get(key)
            if job is not None:
                return job[0]
            future = submit_artifact(operation, store_root=store_root())
            job = self._jobs[key] = [future, None]
        future.add_done_callback(lambda _future: job.__setitem__(1, self._clock()))
        return future


class PartSubscribers:
    def __init__(self):
        self._guard = threading.Lock()
        self._changed = threading.Condition(self._guard)
        self._jobs = {}
        self._reaper = None

    @staticmethod
    def _detach(future):
        future.detach()

    def cancel(self, token: str) -> None:
        with self._guard:
            job = self._jobs.pop(token, None)
            self._changed.notify_all()
        if job is not None:
            self._detach(job["future"])

    def _prune(self):
        now = time.monotonic()
        with self._guard:
            expired = [key for key, value in self._jobs.items() if now - value["touched"] > SUBSCRIBER_IDLE_SECONDS]
            jobs = [self._jobs.pop(key) for key in expired]
        for job in jobs:
            self._detach(job["future"])

    def _start_reaper_locked(self):
        if self._reaper is not None:
            return

        def reap():
            # A crashed tab cannot send cancellation. Deadline expiry must
            # release its subscription even when no subsequent HTTP call arrives.
            while True:
                with self._changed:
                    if not self._jobs:
                        self._reaper = None
                        return
                    deadline = min(job["touched"] for job in self._jobs.values()) + SUBSCRIBER_IDLE_SECONDS
                    self._changed.wait(max(.001, deadline - time.monotonic()))
                self._prune()

        self._reaper = threading.Thread(target=reap, name="cadgen-part-subscribers", daemon=True)
        self._reaper.start()

    def resolve(self, body: bytes) -> dict:
        from cadgen.daemon.artifacts import request_key, submit_artifact

        view, selected, operation, token = _request(body)
        self._prune()
        request_identity = (str(store_root().resolve()), request_key(operation))
        future = None
        if token is not None:
            with self._guard:
                job = self._jobs.get(token)
                if job is None or job["request"] != request_identity:
                    raise ValueError("part subscriber is expired, cancelled, or belongs to different inputs")
                job["touched"] = time.monotonic()
                self._changed.notify_all()
                future = job["future"]
        response = {"viewId": view["viewId"], "components": {}}

        def settle(cids) -> list[str]:
            """Answer each of ``cids`` the store holds the part of; the rest are missing."""
            missing = []
            for cid in cids:
                record = parts.probe(selected[cid])
                if record is not None:
                    # The part's record: what a probe of the mesh store answers, so the client
                    # reads the part's mesh, and later its selector table, without asking again.
                    response["components"][cid] = {"part": selected[cid], "state": "ready", "record": record}
                else:
                    missing.append(cid)
            return missing

        missing = settle(selected)
        if not missing:
            if token is not None:
                self.cancel(token)
            return response
        if future is None:
            with self._guard:
                if len(self._jobs) >= MAX_SUBSCRIBERS:
                    raise ValueError("part request capacity reached; retry after an active request finishes")
                # The one job for this request's missing components (its first answer's: a poll
                # names the same inputs). Each HTTP consumer owns one future; the daemon
                # coalesces the native work, so cancelling this token cannot detach another.
                future = submit_artifact({**operation, "cids": sorted(missing)}, store_root=store_root())
                token = uuid.uuid4().hex
                self._jobs[token] = {"future": future, "request": request_identity, "touched": time.monotonic()}
                self._start_reaper_locked()
                self._changed.notify_all()
        if future.done():
            try:
                future.result()
                error = "display derivation completed without its requested output"
            except Exception as exc:
                LOG.warning("display derivation failed for %s: %r", operation["tree"][:16], exc)
                error = str(exc) or type(exc).__name__
            # Recheck once after completion, including a completion that raced the
            # first lookup. A deleted result is then a failure. So is a failed job's,
            # for only the components it left missing: one component's failure is
            # raised once the others are stored (parts.derive), and they are ready.
            missing = settle(missing)
            for cid in missing:
                response["components"][cid] = {"part": selected[cid], "state": "failed", "error": error}
            self.cancel(token)
            if parts.producer_unavailable(error):
                from cadgen.daemon.artifacts import resolve_artifact
                from cadgen.store.view import descriptor_for_view

                replacement = resolve_artifact({"kind": "producer"})
                if parts.producer_key(replacement) != parts.producer_key(operation["producer"]):
                    from cadgen.store.view import note_replaced_producer

                    # The next view of any document hinting the refused producer starts under
                    # this one (and re-attests it), instead of a refused job per part per open.
                    note_replaced_producer(operation["producer"], replacement)
                    response["replacementView"] = descriptor_for_view(operation["tree"], producer=replacement)
                    for cid in missing:
                        response["components"][cid]["code"] = "producer-unavailable"
            return response
        response["job"] = token
        for cid in missing:
            response["components"][cid] = {"part": selected[cid], "state": "pending", "job": token}
        return response
