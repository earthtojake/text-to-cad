"""The source sidecar: everything SOURCE-derived a generated model carries.

The tree (in the user-level store, keyed by the document's content
hash) is a pure function of the STEP file's bytes plus schema versions — the
cache engine's world, freely evictable. The model's DECLARATIONS live in ONE
sidecar FILE BESIDE THE MODEL, ``<name>.step.json``: the KINEMATICS section
(typed mates with axes resolved to world numbers, couplings, pose presets) and
the MESH EXPORTS section (what the model's ``@stl``/``@glb``/``@threemf``
declarations resolved to, so a bare mesh door reads DECLARATIONS from the
document instead of importing the model module). Choreography is NOT here: the
render module beside the document (``<name>.step.js``) is authored, loaded by
the viewer by name, and read by no build. NOTHING source-derived-as-identity — no paths, hashes, closures, or
timestamps: a sidecar ships beside the artifact, and a generated file carries
no tie back to its source. Provenance lives in the RECORDS tier below. The
sidecar sits beside the model because declarations cannot be re-derived from
the STEP bytes: evicting the store must never lose kinematics. New capability
= new SECTION + schema bump, never a second sidecar file.

A sidecar exists ONLY when the model NEEDS one: a kinematics section, an
animation section, or declared mesh exports. A plain model — geometry and
nothing else — writes no sidecar at all; its provenance and freshness ride
the PROVENANCE RECORD in the evictable records tier (bottom of this module),
which every generated build writes and every gate reads — the ONE home of
source-derived identity. Eviction costs one rebuild, never correctness (an
evicted record simply reads as an import until the next build re-records it).
Imports write neither. The JS authority
(``apps/viewer/server/artifact_status.py``) mirrors this: a sidecar at THIS schema
is a fast yes, and the record decides everything else.

Write ordering matters: the sidecar is written BEFORE the tree lands at
its content key, so a resolvable package never races a missing sidecar.
Readers are lock-blind and tolerate a MISSING sidecar; a sidecar that is
present must declare ``SOURCE_SIDECAR_SCHEMA_VERSION``, because reading
sections out of a file written to a different shape is how a model silently
loses its kinematics.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from cadgen._internal.atomic_replace import replace_atomic, temp_suffix

# APPENDED to the artifact's whole name, so the pair sorts and reads together:
# `part.step` -> `part.step.json`. Never match a sidecar on this suffix alone —
# it is `.json`, which every unrelated JSON file also ends with. Construct the
# path from the artifact (:func:`source_sidecar_path`), or match the artifact
# suffix too (`.step.json` / `.stp.json`).
SOURCE_SIDECAR_SUFFIX = ".json"
# 6: the animation and meshExports sections are gone. Choreography is the render
#    module beside the document (`<name>.step.js`), loaded by the viewer and never
#    by a build; a mesh door tessellates the document's tree and writes the file
#    it was asked for, and what a model declares lives in its record. A sidecar
#    is written for kinematics alone. 5 moved provenance OUT of the sidecar.
SOURCE_SIDECAR_SCHEMA_VERSION = 6

# What a sidecar may CONTAIN: declarations only. Anything source-derived-as-
# provenance (paths, hashes, closures, timestamps) belongs to the provenance
# record; a sidecar sits beside the artifact and ships with it.
_SIDECAR_SECTIONS = ("schemaVersion", "kinematics")


def source_sidecar_path(step_path: Path | str) -> Path:
    """``<name>.step`` -> ``<name>.step.json``, beside the model."""
    artifact = Path(step_path)
    return artifact.with_name(artifact.name + SOURCE_SIDECAR_SUFFIX)


class SidecarSchemaError(ValueError):
    """A sidecar file that is not at the schema this cadgen reads."""


def _raw_source_sidecar(step_path: Path | str) -> dict[str, Any] | None:
    """The sidecar's JSON with NO schema gate. Only the writer's no-op compare
    and the schema gate itself may use this; every consumer of the SECTIONS
    goes through :func:`read_source_sidecar`."""
    try:
        payload = json.loads(source_sidecar_path(step_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def sidecar_schema_is_current(payload: Mapping[str, Any] | None) -> bool:
    return bool(payload) and payload.get("schemaVersion") == SOURCE_SIDECAR_SCHEMA_VERSION


def read_source_sidecar(step_path: Path | str) -> dict[str, Any] | None:
    """The document's declarations, or ``None`` when it has no sidecar.

    A sidecar that IS there must declare this schema: reading sections out of
    a file written to a different shape is how a model silently loses its
    kinematics. Missing/unreadable stays ``None`` (an import, or a plain model
    that declares nothing); wrong schema is an error with the fix.
    """
    payload = _raw_source_sidecar(step_path)
    if payload is None:
        return None
    if not sidecar_schema_is_current(payload):
        found = payload.get("schemaVersion", "none")
        artifact = Path(step_path)
        raise SidecarSchemaError(
            f"{source_sidecar_path(artifact).name}: unsupported sidecar schema {found} "
            f"(expected {SOURCE_SIDECAR_SCHEMA_VERSION}) — rebuild the model "
            f"(python {artifact.stem}.py) or re-annotate the document "
            f"(cadgen step build)"
        )
    return payload


def model_is_generated(step_path: Path | str) -> bool:
    """Whether this artifact carries a sidecar this cadgen reads — the same
    fast yes ``artifactStatus.mjs`` takes. Never raises: classification is not
    a render, and the loud refusal belongs to the readers of the SECTIONS."""
    return sidecar_schema_is_current(_raw_source_sidecar(step_path))


# The sections that WARRANT a sidecar. Provenance alone does not: it also
# lives in the assembly.json, and a file per plain model is pure clutter.
_WARRANTING_SECTIONS = ("kinematics",)


def sidecar_is_warranted(payload: Mapping[str, Any] | None) -> bool:
    """Whether this payload carries anything the model actually needs a
    sidecar FOR. A sidecar is written only when strictly necessary — today,
    kinematics: metadata with no reader beside the artifact belongs in the
    record, not in a file."""
    if not payload:
        return False
    return any(payload.get(section) for section in _WARRANTING_SECTIONS)


def write_source_sidecar(step_path: Path | str, payload: Mapping[str, Any]) -> None:
    """Write the sidecar — or, for a payload that warrants none, remove any
    stale one (a model that DROPPED its kinematics must lose the file).
    Only the FILE: the build's provenance record stays."""
    if not sidecar_is_warranted(payload):
        source_sidecar_path(step_path).unlink(missing_ok=True)
        return
    target = source_sidecar_path(step_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    body = {k: v for k, v in payload.items() if k in _SIDECAR_SECTIONS}
    body["schemaVersion"] = SOURCE_SIDECAR_SCHEMA_VERSION
    # A rewrite that changes nothing but the timestamp is pure churn — for
    # committed sidecars (imported/ projects) it dirties git on every no-op.
    if _raw_source_sidecar(step_path) == body:
        return
    temp = target.with_name(f".{target.name}{temp_suffix()}")
    temp.write_text(json.dumps(body, sort_keys=True), encoding="utf-8")
    replace_atomic(temp, target)


def remove_source_sidecar(step_path: Path | str) -> None:
    """Imports must never leave a stale generated-marker behind (e.g. a
    re-import over a model that used to be generated)."""
    source_sidecar_path(step_path).unlink(missing_ok=True)


def read_source_provenance(step_path: Path | str) -> dict[str, Any] | None:
    """The document's source provenance, read from the STORE RECORD of the model
    behind it (``cadgen.store.records``): sourceKind, the script path relative
    to the document, and the closure. ``None`` for a document with no record.

    The provenance record file this used to read is gone; the model record is
    the one freshness memory (STORE.md)."""
    from cadgen.store.records import record_for_document, source_for_document

    document = Path(step_path)
    record = record_for_document(document)
    if record is None:
        return None
    source = source_for_document(document)
    payload: dict[str, Any] = {
        "sourceKind": str(record.get("sourceKind") or "python"),
        "sourceClosureHash": str((record.get("closure") or {}).get("hash") or ""),
        "sourceClosureFiles": list((record.get("closure") or {}).get("files") or []),
        "tree": str(record.get("tree") or ""),
    }
    for key in ("sourceHash", "annotationHash", "kinematics", "stepHash"):
        if record.get(key) is not None:
            payload[key] = record[key]
    try:
        document_resolved = document.expanduser().resolve()
    except (OSError, RuntimeError):
        document_resolved = document
    if str(source) != str(document_resolved):
        import os

        try:
            payload["sourcePath"] = os.path.relpath(str(source), str(document_resolved.parent))
        except ValueError:
            payload["sourcePath"] = str(source)
    return payload
