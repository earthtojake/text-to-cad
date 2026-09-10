"""Disposable playback meshes in the existing opaque mesh cache, never a sidecar."""

from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path

from cadgen.store.paths import StoreUnwritableError
from cadgen.store.tess_cache import (
    read_tessellation_cache,
    write_tessellation_cache,
)


def cache_key(brep, recipe):
    # Fingerprint the actual interpreter: changing verification or meshing rules
    # must not accept an old proof. This is package code, never model source.
    worker = Path(__file__).parents[1] / "_internal" / "step_reconstruction.py"
    inputs = {
        "geometry": sha256(brep.read_bytes()).hexdigest(),
        "recipe": recipe,
        "interpreter": sha256(worker.read_bytes()).hexdigest(),
        "kernel": version("cadquery-ocp"),
    }
    return (
        "reconstruction-"
        + sha256(
            json.dumps(inputs, sort_keys=True, allow_nan=False).encode()
        ).hexdigest()
    )


def read_preview(key, limit):
    try:
        data = read_tessellation_cache(key)
        if not data or len(data) > limit + 65:
            return None
        digest, payload = data.split(b"\n", 1)
        if digest != sha256(payload).hexdigest().encode():
            return None
        result = json.loads(payload)
        if (
            not isinstance(result, dict)
            or result.get("status") != "verified"
            or not isinstance(result.get("proof"), dict)
            or result["proof"].get("passed") is not True
            or not isinstance(result.get("steps"), list)
            or not result["steps"]
            or not isinstance(result.get("reference"), dict)
        ):
            return None
        return payload
    except (OSError, ValueError):
        return None


def write_preview(key, payload):
    # Atomic publication and GC belong to the shared store. An unavailable cache
    # must not fail a reconstruction that already succeeded.
    try:
        write_tessellation_cache(
            key, sha256(payload).hexdigest().encode() + b"\n" + payload
        )
    except (OSError, StoreUnwritableError):
        pass
