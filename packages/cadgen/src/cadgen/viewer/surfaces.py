"""Artifact-only asynchronous SURF resolution for owned runtime views.

Tokens are disposable subscribers to pooled work, never persistent store
entries or editing sessions. Every poll repeats and validates its immutable
inputs. Disconnect/cancellation detaches that subscriber, not another reader,
and never kills a derivation: the daemon finishes the one in hand into the store
and starts no other for a job nobody is subscribed to.
"""

from __future__ import annotations

from collections import OrderedDict
import json
import logging
import os
import threading
import time
import uuid
from urllib.parse import urlencode

from cadgen.store import surfaces
from cadgen.store.objects import object_path, read_verified_object
from cadgen.store.paths import store_root
from cadgen.store.trees import capture_tree

LOG = logging.getLogger("cadgen.viewer.surfaces")

MAX_COMPONENTS = 64
MAX_SUBSCRIBERS = 256
SUBSCRIBER_IDLE_SECONDS = 120

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

    __slots__ = ("components", "by_content", "paths", "tree_path")

    def __init__(self, tree: str, components: dict):
        self.components = components
        self.by_content: dict[str, list[str]] = {}
        self.paths: dict[str, tuple[str, ...]] = {}
        for cid, entry in components.items():
            self.by_content.setdefault(entry["contentHash"], []).append(cid)
            self.paths[cid] = tuple(str(object_path(entry[field])) for field in ("brep", "eagerSurface")
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


def _request(body: bytes) -> tuple[dict, dict, dict, str | None, dict]:
    if len(body) > 128 * 1024:
        raise ValueError("surface request is too large")
    value = json.loads(body)
    fields = {"tree", "viewId", "producer", "components"}
    if type(value) is not dict or not fields <= set(value) or set(value) - fields - {"job", "tessellation"}:
        raise ValueError("surface request requires tree, viewId, producer and components")
    producer = surfaces.producer_fields(value["producer"])
    tree = value["tree"]
    if not _is_digest(tree):
        raise ValueError("surface request names no tree")
    pin = _pinned(tree)
    view_id = surfaces._view_id(tree, producer)
    if value["viewId"] != view_id:
        raise ValueError("surface request mixes runtime views")
    components = value["components"]
    if type(components) is not list or not 0 < len(components) <= MAX_COMPONENTS:
        raise ValueError("surface request must name between 1 and 64 components")
    selected = {}
    expected = {}
    for item in components:
        if type(item) is not dict or not {"cid", "surfaceInput"} <= set(item) or set(item) - {"cid", "surfaceInput", "expectedSurfaceObject"}:
            raise ValueError("invalid surface component request")
        cid = item["cid"]
        entry = pin.components.get(cid) if type(cid) is str else None
        surface_input = surfaces.surface_input(entry, producer) if entry is not None else None
        if entry is None or cid in selected or item["surfaceInput"] != surface_input:
            raise ValueError("surface request names an unpinned component or input")
        selected[cid] = {"surfaceInput": surface_input}
        if "expectedSurfaceObject" in item:
            digest = item["expectedSurfaceObject"]
            if type(digest) is not str or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("expected surface object must be a full lowercase digest")
            expected[surface_input] = digest
    job = value.get("job")
    if job is not None and (type(job) is not str or len(job) != 32 or any(c not in "0123456789abcdef" for c in job)):
        raise ValueError("invalid surface subscriber token")
    # A tessellation asks for the components' meshes at that tolerance as well:
    # the display mesh is produced here, by OCCT, never by the browser.
    tessellations = [] if value.get("tessellation") is None else surfaces.normalize_tessellations([value["tessellation"]])
    operation = {"kind": "surfaces", "tree": value["tree"], "cids": sorted(selected),
                 "producer": producer, "expected_objects": expected,
                 **({"tessellations": [{"chordTolerance": chord, "angleTolerance": angle}
                                       for chord, angle in tessellations]} if tessellations else {})}
    # The named components' objects, still on disk; the map itself is read-only.
    canonical = {"components": _pinned(tree, selected).components}
    return {"viewId": view_id}, selected, operation, job, canonical


def surface_object_url(tree: str, surface_input: str, digest: str) -> str:
    return "/__cad/store?" + urlencode({"tree": tree, "surfaceInput": surface_input, "object": digest})


def pinned_surface_object(tree: str, surface_input: str, digest: str):
    """Serve exact CAS bytes only when a verified derivation binds D to O: the
    surface the input names, or the selector table derived from that surface
    (``store.selectors``), bound to it by its record."""
    from cadgen.store import selectors
    from cadgen.store.index import read_entry

    if not all(_is_digest(value) for value in (tree, surface_input, digest)):
        return None
    # The geometry pins which component may participate; the derivation index
    # pins its full producer and exact output. No producer initialization here.
    pin = _pinned(tree)
    record = read_entry("surface", surface_input)
    if record is None:
        return None
    if record.get("object") != digest:
        table = selectors.probe(selectors.selector_key(surface_input))
        if table is None or table["object"] != digest or table["surfaceObject"] != record.get("object"):
            return None
        if pinned_surface_object(tree, surface_input, record["object"]) is None:
            return None
        return object_path(digest)
    producer, component = record.get("producer"), record.get("component")
    for cid in pin.by_content.get(component, ()) if type(component) is str else ():
        entry = pin.components[cid]
        if producer is None:
            if entry.get("kind") != "eager-only" or entry.get("eagerSurface") != digest:
                continue
            if surfaces.surface_input(entry, {}) != surface_input:
                continue
            _pinned(tree, (cid,))
            surfaces.validate_surface_bytes(read_verified_object(digest))
            return object_path(digest)
        if surfaces.surface_input(entry, producer) != surface_input:
            continue
        _pinned(tree, (cid,))
        found = surfaces.lookup(entry, producer)
        if found is not None and found["object"] == digest:
            return object_path(digest)
    return None


def _meshes(entry: dict, operation: dict) -> list[dict] | None:
    """The stored mesh records of every tessellation ``operation`` asks for, or None
    while any is missing."""
    records = list(surfaces.mesh_records(entry, operation["producer"], operation.get("tessellations")).values())
    return None if any(record is None for record in records) else records


def _selectors(entry: dict, operation: dict, record: dict) -> dict | None:
    """The stored selector table of the component's surface, or None while missing."""
    table = surfaces.selector_record(entry, operation["producer"])
    return table if table is not None and table["surfaceObject"] == record["object"] else None


def _ready(operation: dict, entry: dict, record: dict, meshes: list[dict], table: dict) -> dict:
    ready = {
        "surfaceInput": entry["surfaceInput"], "state": "ready", "surfaceObject": record["object"],
        "url": surface_object_url(operation["tree"], entry["surfaceInput"], record["object"]),
        "byteLength": object_path(record["object"]).stat().st_size,
        # The component's selector table (``store.selectors``): the refs and facts the page
        # joins to the mesh, served by the same store route as the surface.
        "selectors": {
            "object": table["object"],
            "url": surface_object_url(operation["tree"], entry["surfaceInput"], table["object"]),
            "byteLength": table["byteLength"],
        },
    }
    if meshes:
        # The mesh's index record: what a tessellation-cache probe answers, so the
        # client reads its body next without asking again.
        ready["mesh"] = meshes[0]
    return ready


class SurfaceSubscribers:
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

        self._reaper = threading.Thread(target=reap, name="cadgen-surface-subscribers", daemon=True)
        self._reaper.start()

    def resolve(self, body: bytes) -> dict:
        from cadgen.daemon.artifacts import request_key, submit_artifact

        view, selected, operation, token, canonical = _request(body)
        self._prune()
        request_identity = (str(store_root().resolve()), request_key(operation))
        future = None
        if token is not None:
            with self._guard:
                job = self._jobs.get(token)
                if job is None or job["request"] != request_identity:
                    raise ValueError("surface subscriber is expired, cancelled, or belongs to different inputs")
                job["touched"] = time.monotonic()
                self._changed.notify_all()
                future = job["future"]
        response = {"viewId": view["viewId"], "components": {}}
        missing = []
        for cid, entry in selected.items():
            record = surfaces.lookup(canonical["components"][cid], operation["producer"])
            expected = operation["expected_objects"].get(entry["surfaceInput"])
            meshes = _meshes(canonical["components"][cid], operation)
            table = _selectors(canonical["components"][cid], operation, record) if record is not None else None
            if record is not None and expected is not None and record["object"] != expected:
                response["components"][cid] = {"surfaceInput": entry["surfaceInput"], "state": "failed",
                                               "error": "surface output differs from the displayed mesh", "code": "surface-conflict"}
            elif record is not None and meshes is not None and table is not None:
                response["components"][cid] = _ready(operation, entry, record, meshes, table)
            else:
                missing.append(cid)
        if not missing:
            if token is not None:
                self.cancel(token)
            return response
        if future is None:
            with self._guard:
                if len(self._jobs) >= MAX_SUBSCRIBERS:
                    raise ValueError("surface request capacity reached; retry after an active request finishes")
                # Each HTTP consumer owns one future. The daemon coalesces the
                # native work; cancelling this token cannot detach another one.
                future = submit_artifact(operation, store_root=store_root())
                token = uuid.uuid4().hex
                self._jobs[token] = {"future": future, "request": request_identity, "touched": time.monotonic()}
                self._start_reaper_locked()
                self._changed.notify_all()
        if future.done():
            try:
                future.result()
                error = "surface derivation completed without its requested output"
            except Exception as exc:
                LOG.warning("surface derivation failed for %s: %r", operation["tree"][:16], exc)
                error = str(exc) or type(exc).__name__
            # Recheck once after completion, including a completion that raced the
            # first lookup. A deleted result is then a failure. So is a failed job's,
            # for only the components it left missing: one component's failure is
            # raised once the others are stored (surfaces.derive), and they are ready.
            remaining = []
            for cid in missing:
                record = surfaces.lookup(canonical["components"][cid], operation["producer"])
                expected = operation["expected_objects"].get(selected[cid]["surfaceInput"])
                meshes = _meshes(canonical["components"][cid], operation)
                table = _selectors(canonical["components"][cid], operation, record) if record is not None else None
                if record is None or meshes is None or table is None or (expected is not None and record["object"] != expected):
                    remaining.append(cid)
                else:
                    response["components"][cid] = _ready(operation, selected[cid], record, meshes, table)
            missing = remaining
            for cid in missing:
                response["components"][cid] = {"surfaceInput": selected[cid]["surfaceInput"], "state": "failed", "error": error}
            self.cancel(token)
            if surfaces.producer_unavailable(error):
                from cadgen.daemon.artifacts import resolve_artifact
                from cadgen.store.view import descriptor_for_view

                replacement = resolve_artifact({"kind": "producer"})
                if surfaces.producer_key(replacement) != surfaces.producer_key(operation["producer"]):
                    response["replacementView"] = descriptor_for_view(operation["tree"], producer=replacement)
                    for cid in missing:
                        response["components"][cid]["code"] = "producer-unavailable"
            return response
        response["job"] = token
        for cid in missing:
            response["components"][cid] = {"surfaceInput": selected[cid]["surfaceInput"], "state": "pending", "job": token}
        return response
