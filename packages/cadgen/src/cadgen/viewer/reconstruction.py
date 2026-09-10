"""Opt-in reconstruction experiment; stdlib-only host for a disposable kernel job.

No generator execution or STEP exports. One job per viewer at a
time, with bounded input/output and a hard timeout. This experimental worker
does not participate in document compilation or publish any build records.
"""

from __future__ import annotations

import json
from collections import OrderedDict
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from .backend import require_contained
from .store_paths import (
    result_tree,
    result_descriptor,
    virtual_store_asset,
    cadgen_cache_root_dir,
)
from .reconstruction_cache import cache_key, read_preview, write_preview

MAX_INPUT = 256 * 1024
MAX_OUTPUT = 24 * 1024 * 1024
_slot = threading.BoundedSemaphore(1)
_cache_lock = threading.Lock()
_cache = OrderedDict()
_cache_bytes = 0
MAX_CACHE_BYTES = 64 * 1024 * 1024


def _cached(key):
    with _cache_lock:
        value = _cache.get(key)
        if value is not None:
            _cache.move_to_end(key)
        return value


def _remember(key, value):
    global _cache_bytes
    with _cache_lock:
        previous = _cache.pop(key, None)
        if previous is not None:
            _cache_bytes -= len(previous[0])
        _cache[key] = value
        _cache_bytes += len(value[0])
        while _cache_bytes > MAX_CACHE_BYTES or len(_cache) > 128:
            _, evicted = _cache.popitem(last=False)
            _cache_bytes -= len(evicted[0])


def _response(value, preview, tree, component):
    payload, summary = value
    return {
        **(json.loads(payload) if preview else summary),
        "tree": tree,
        "component": component,
    }


def enabled():
    return os.environ.get("CADGEN_RECONSTRUCTION_EXPERIMENT") == "1"


def reconstruct(root, file_ref, payload):
    if not enabled():
        raise ValueError("Reconstruction experiment is not enabled in this viewer.")
    if len(payload) > MAX_INPUT:
        raise ValueError("Reconstruction recipe exceeds the size limit.")
    request = json.loads(payload)
    candidate = require_contained(
        root, os.path.abspath(os.path.join(root, str(file_ref)))
    )
    if Path(candidate).suffix.lower() not in (".step", ".stp"):
        raise ValueError("Reconstruction requires a STEP file.")
    tree = result_tree(candidate)
    if not tree or request.get("tree") != tree:
        raise ValueError("The STEP changed. Reload its geometry before reconstructing.")
    descriptor = result_descriptor(tree)
    component = str(request.get("component", ""))
    if not descriptor or component not in descriptor["components"]:
        raise ValueError("This part does not belong to the displayed STEP.")
    brep, _ = virtual_store_asset(f"{tree}/components/{component}.brep")
    if not isinstance(brep, Path) or brep.stat().st_size > 32 * 1024 * 1024:
        raise ValueError(
            "Exact geometry is unavailable or too large for this experiment."
        )
    recipe = request.get("recipe")
    # Geometry bytes + recipe + interpreter/kernel; reusable across viewer restarts.
    disk_key = cache_key(brep, recipe)
    key = (cadgen_cache_root_dir(), disk_key)
    preview = request.get("preview") is not False
    cached = _cached(key)
    if cached is not None:
        if result_tree(candidate) != tree:
            raise ValueError(
                "The STEP changed. Reload its geometry before reconstructing."
            )
        return _response(cached, preview, tree, component)
    if not _slot.acquire(timeout=65):
        raise ValueError("Verification is busy. Try again shortly.")
    try:
        cached = _cached(key)
        if cached is None:
            payload = read_preview(disk_key, MAX_OUTPUT)
            from_disk = payload is not None
            if payload is None:
                payload = _run(recipe, brep)
            result = json.loads(payload)
            summary = {
                k: result[k] for k in ("status", "proof", "error") if k in result
            }
            summary["frameCount"] = len(result.get("steps", []))
            cached = (payload, summary)
            _remember(key, cached)
            if (
                not from_disk
                and result.get("status") == "verified"
                and result.get("proof", {}).get("passed") is True
            ):
                write_preview(disk_key, payload)
        if result_tree(candidate) != tree:
            raise ValueError(
                "The STEP changed during verification. Reload and try again."
            )
        return _response(cached, preview, tree, component)
    finally:
        _slot.release()


def _run(recipe, brep):
    with tempfile.TemporaryDirectory(prefix="cad-reconstruction-") as directory:
        source, output = (
            Path(directory) / "request.json",
            Path(directory) / "result.json",
        )
        source.write_text(json.dumps({"recipe": recipe, "brep": str(brep)}))
        # Fixed module/arguments: client input is numerical JSON, never executable code.
        with open(Path(directory) / "worker.log", "wb") as log:
            try:
                process = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "cadgen._internal.step_reconstruction",
                        str(source),
                        str(output),
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    timeout=60,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                raise ValueError("Verification timed out for this part.") from None
        if process.returncode or not output.exists():
            raise ValueError(
                "A complete, valid reconstruction could not be verified for this part."
            )
        if output.stat().st_size > MAX_OUTPUT:
            raise ValueError("Reconstruction preview exceeds the size limit.")
        return output.read_bytes()
