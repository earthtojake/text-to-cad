"""Artifact-only asynchronous SURF resolution for owned runtime views.

Tokens are disposable subscribers to pooled work, never persistent store
entries or editing sessions. Every poll repeats and validates its immutable
inputs. Disconnect/cancellation detaches that subscriber, not another reader.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from urllib.parse import urlencode

from cadgen.store import surfaces
from cadgen.store.objects import object_path, read_verified_object
from cadgen.store.paths import store_root
from cadgen.store.trees import capture_tree

MAX_COMPONENTS = 64
MAX_SUBSCRIBERS = 256
SUBSCRIBER_IDLE_SECONDS = 120


def _request(body: bytes) -> tuple[dict, dict, dict, str | None, dict]:
    if len(body) > 128 * 1024:
        raise ValueError("surface request is too large")
    value = json.loads(body)
    fields = {"tree", "viewId", "producer", "components"}
    if type(value) is not dict or not fields <= set(value) or set(value) - fields - {"job"}:
        raise ValueError("surface request requires tree, viewId, producer and components")
    producer = surfaces.producer_fields(value["producer"])
    tree = value["tree"]
    canonical, _ = capture_tree(tree, retain_payloads=False)
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
        entry = canonical["components"].get(cid)
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
    operation = {"kind": "surfaces", "tree": value["tree"], "cids": sorted(selected),
                 "producer": producer, "expected_objects": expected}
    return {"viewId": view_id}, selected, operation, job, canonical


def surface_object_url(tree: str, surface_input: str, digest: str) -> str:
    return "/__cad/store?" + urlencode({"tree": tree, "surfaceInput": surface_input, "object": digest})


def pinned_surface_object(tree: str, surface_input: str, digest: str):
    """Serve exact CAS bytes only when a verified derivation binds D to O."""
    from cadgen.store.index import read_entry

    if any(type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
           for value in (tree, surface_input, digest)):
        return None
    # The geometry pins which component may participate; the derivation index
    # pins its full producer and exact output. No producer initialization here.
    descriptor, _ = capture_tree(tree, retain_payloads=False)
    record = read_entry("surface", surface_input)
    if record is None or record.get("object") != digest:
        return None
    producer = record.get("producer")
    for entry in descriptor["components"].values():
        if entry["contentHash"] != record.get("component"):
            continue
        if producer is None:
            if entry.get("kind") != "eager-only" or entry.get("eagerSurface") != digest:
                continue
            if surfaces.surface_input(entry, {}) != surface_input:
                continue
            surfaces.validate_surface_bytes(read_verified_object(digest))
            return object_path(digest)
        if surfaces.surface_input(entry, producer) != surface_input:
            continue
        found = surfaces.lookup(entry, producer)
        if found is not None and found["object"] == digest:
            return object_path(digest)
    return None


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
            if record is not None and expected is not None and record["object"] != expected:
                response["components"][cid] = {"surfaceInput": entry["surfaceInput"], "state": "failed",
                                               "error": "surface output differs from the displayed mesh", "code": "surface-conflict"}
            elif record is not None:
                response["components"][cid] = {
                    "surfaceInput": entry["surfaceInput"], "state": "ready", "surfaceObject": record["object"],
                    "url": surface_object_url(operation["tree"], entry["surfaceInput"], record["object"]),
                    "byteLength": object_path(record["object"]).stat().st_size,
                }
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
            error = None
            try:
                future.result()
                remaining = []
                for cid in missing:
                    record = surfaces.lookup(canonical["components"][cid], operation["producer"])
                    expected = operation["expected_objects"].get(selected[cid]["surfaceInput"])
                    if record is None or (expected is not None and record["object"] != expected):
                        remaining.append(cid)
                    else:
                        response["components"][cid] = {
                            "surfaceInput": selected[cid]["surfaceInput"], "state": "ready",
                            "surfaceObject": record["object"],
                            "url": surface_object_url(operation["tree"], selected[cid]["surfaceInput"], record["object"]),
                            "byteLength": object_path(record["object"]).stat().st_size,
                        }
                missing = remaining
                # Recheck once after completion, including a completion that
                # raced the first lookup. A deleted result is then a failure.
                error = "surface derivation completed without its requested output"
            except Exception as exc:
                error = str(exc)
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
