"""An explicit editing session's ephemeral preview feed, never a saved-file resolver.

The daemon owns request ordering and publishes complete immutable trees. This
read-only adapter matches the output and store, validates object availability,
and exposes only display data. No source, closure, model record or output index
is consulted. A daemon restart expires this channel; ordinary artifact readers
continue to resolve the bytes on disk.
"""

from __future__ import annotations

import copy
import json
import os
import time
from pathlib import Path
from urllib.parse import urlencode

from cadgen.store.paths import store_root
from cadgen.store.trees import capture_tree

from .backend import normalized_file_ref, require_contained
from .build_progress import _daemon_jobs
from .store_paths import result_snapshot


def _preview_target(root_path: str, file_ref: str) -> str:
    ref = normalized_file_ref(file_ref)
    if not ref or Path(ref).suffix.lower() not in {".step", ".stp"}:
        raise ValueError("An editing preview requires a STEP output path")
    target = os.path.abspath(ref if os.path.isabs(ref) else os.path.join(root_path, ref))
    require_contained(root_path, target)
    if any(part.startswith(".") for part in Path(os.path.relpath(target, root_path)).parts):
        raise ValueError("Hidden output paths are not served")
    return target


def preview_update(root_path: str, file_ref: str, *, after: str | None = None) -> dict:
    """Wake for ledger changes; each response still verifies artifact identity."""
    target = _preview_target(root_path, file_ref)  # refuse invalid paths before waiting
    from cadgen.daemon.client import watch_jobs

    update = watch_jobs(after, output=os.path.realpath(target), store_root=os.path.realpath(store_root()))
    if update is None:
        return preview_status(root_path, file_ref)
    result = preview_status(root_path, file_ref, jobs=update["jobs"])
    result["feedCursor"] = update["jobsCursor"]
    if update.get("jobsWatchLimited"):
        result["feedLimited"] = True
    return result


def preview_status(root_path: str, file_ref: str, *, jobs: list[dict] | None = None) -> dict:
    file_path = _preview_target(root_path, file_ref)
    # Match the catalog's root-relative file identity. An absolute path in a
    # provisional entry would be written into ?file= by the selection effect,
    # whose URL normalizer removes its leading slash.
    display_file = os.path.relpath(file_path, root_path).replace(os.sep, "/")
    target = os.path.realpath(file_path)
    active_store = os.path.realpath(store_root())
    listed = jobs if jobs is not None else _daemon_jobs(time.time(), max_age=0.08)
    matching = [
        job for job in listed
        if job.get("tool") == "run"
        and job.get("editingProducer", True)
        and job.get("storeRoot") and os.path.realpath(job["storeRoot"]) == active_store
        and target in {os.path.realpath(p) for p in job.get("outputs", [])}
    ]
    if not matching:
        return {"output": target, "file": display_file, "state": "disconnected", "revision": None}
    latest = max(matching, key=lambda job: int(job.get("sequence") or 0))
    result = {
        "output": target,
        "file": display_file,
        "epoch": latest.get("epoch"),
        "revision": int(latest.get("sequence") or 0),
        "request": latest.get("id"),
        "state": latest.get("state"),
        "phase": latest.get("phase"),
        "detail": latest.get("detail"),
        "updatedAt": round(float(latest.get("updatedAt") or 0.0) * 1000.0),
        "error": latest.get("error"),
    }
    # Only the newest accepted request can publish. The client may retain a
    # previously displayed tree while this request has no preview yet.
    verified = {}
    for key, output_key in (("previews", "preview"), ("savedResults", "saved")):
        payload = (latest.get(key) or {}).get(target)
        if output_key == "saved" and not payload and latest.get("state") == "done":
            # A no-op model run has no new publication event. Resolve its
            # saved output from actual bytes so an earlier failed preview is
            # not kept forever after a successful current-file request.
            current = result_snapshot(target)
            if current:
                payload = {"tree": current[1], "documentHash": current[0]}
        if not isinstance(payload, dict):
            continue
        tree_hash = str(payload.get("tree") or "")
        if tree_hash not in verified:
            try:
                verified[tree_hash] = capture_tree(tree_hash, retain_payloads=False)[0]
            except (OSError, ValueError, TypeError, KeyError, RuntimeError, OverflowError):
                verified[tree_hash] = None
        descriptor = verified[tree_hash]
        if descriptor is None:
            result["error"] = "Preview geometry is no longer available in the cache"
            if output_key == "preview":
                result["previewUnavailable"] = True
            continue
        result[output_key] = {
            "tree": tree_hash,
            "kind": descriptor.get("entryKind", "part"),
            "sequence": int(payload.get("sequence") or 0),
            "url": f"/__cad/store?file={tree_hash}",
        }
        if output_key == "preview":
            result[output_key]["kinematics"] = copy.deepcopy(payload.get("kinematics"))
            if payload.get("surfaceProducer") is not None:
                from cadgen.store.surfaces import producer_fields

                selected_producer = producer_fields(payload["surfaceProducer"])
                result[output_key]["surfaceProducer"] = selected_producer
                result[output_key]["url"] += "&" + urlencode({
                    "surfaceProducer": json.dumps(selected_producer, sort_keys=True, separators=(",", ":")),
                })
            result[output_key]["appearance"] = copy.deepcopy(payload.get("appearance"))
            result[output_key]["animation"] = copy.deepcopy(payload.get("animation"))
        else:
            # A completed write is only labelled saved if these are still the
            # actual bytes. It never aliases a live preview into index/document.
            digest = payload.get("documentHash")
            if not digest or result_snapshot(target) != (digest, tree_hash):
                result.pop(output_key)
                result["error"] = "The saved file has changed since this build completed"
            else:
                result[output_key]["documentHash"] = digest
                result[output_key]["url"] += "&documentHash=" + digest
    return result
