from __future__ import annotations

import json
import os
import struct
from array import array
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cadgen.selector_types import SelectorBundle


STEP_TOPOLOGY_EXTENSION = "STEP_topology"
STEP_TOPOLOGY_SCHEMA_VERSION = 2
STEP_TOPOLOGY_EDGE_CLASSIFICATION_ALGORITHM = "oc-brep-continuity-v1"
STEP_TOPOLOGY_SURFACE_EDGE_ALGORITHM = "oc-polygon-on-triangulation-v1"
STEP_TOPOLOGY_EDGE_ANGULAR_TOLERANCE_DEG = 2
STEP_TOPOLOGY_EDGE_SAMPLE_COUNT = 3
STEP_EDGE_BARYCENTRIC_ATTRIBUTE = "_CAD_EDGE_BARYCENTRIC"
STEP_EDGE_CLASS_ATTRIBUTE = "_CAD_EDGE_CLASS"
STEP_EDGE_FLAGS = {
    "DEGENERATE": 1 << 1,
    "SEAM": 1 << 2,
    "NOT_REFERENCEABLE": 1 << 3,
    "BOUNDARY": 1 << 4,
    "NON_MANIFOLD": 1 << 5,
    "HARD": 1 << 6,
    "TANGENT": 1 << 7,
    "UNKNOWN_CONTINUITY": 1 << 8,
}
STEP_EDGE_VISIBILITY_CLASSES = {
    "FEATURE": "feature",
    "TANGENT": "tangent",
    "SEAM": "seam",
    "DEGENERATE": "degenerate",
    "BOUNDARY": "boundary",
    "NON_MANIFOLD": "nonManifold",
    "UNKNOWN": "unknown",
}
STEP_EDGE_RENDER_VISIBILITY_CLASSES = (
    STEP_EDGE_VISIBILITY_CLASSES["FEATURE"],
    STEP_EDGE_VISIBILITY_CLASSES["TANGENT"],
    STEP_EDGE_VISIBILITY_CLASSES["SEAM"],
    STEP_EDGE_VISIBILITY_CLASSES["DEGENERATE"],
)
STEP_EDGE_DEFAULT_RENDER_VISIBILITY_CLASSES = STEP_EDGE_RENDER_VISIBILITY_CLASSES
STEP_EDGE_SURFACE_CLASS_CODES = {
    "none": 0,
    "feature": 1,
    "tangent": 2,
    "seam": 3,
    "degenerate": 4,
    "boundary": 5,
    "nonManifold": 6,
    "unknown": 7,
}
STEP_SURFACE_HALF_EDGE_COLUMNS = (
    "edgeRow",
    "faceRow",
    "occurrenceRow",
    "primitiveIndex",
    "triangleIndex",
    "side",
    "classCode",
)
GLB_MAGIC = 0x46546C67
GLB_VERSION = 2
UNSIGNED_BYTE = 5121


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _parse_glb_header(path: Path, payload: bytes) -> tuple[int, int]:
    if len(payload) < 20:
        raise ValueError(f"Not a GLB file: {_display_path(path)}")
    magic, version, length = struct.unpack_from("<III", payload, 0)
    if magic != GLB_MAGIC or version != GLB_VERSION or length > len(payload):
        raise ValueError(f"Not a GLB v2 file: {_display_path(path)}")
    return version, length


def _read_glb_chunks(path: Path) -> tuple[dict[str, Any], bytes]:
    payload = path.expanduser().resolve().read_bytes()
    _, length = _parse_glb_header(path, payload)
    offset = 12
    json_payload: bytes | None = None
    binary_payload = b""
    while offset + 8 <= length:
        chunk_length, chunk_type = struct.unpack_from("<I4s", payload, offset)
        offset += 8
        chunk = payload[offset : offset + chunk_length]
        offset += chunk_length
        if chunk_type == b"JSON":
            json_payload = chunk
        elif chunk_type == b"BIN\0":
            binary_payload = chunk
    if json_payload is None:
        raise ValueError(f"GLB is missing JSON chunk: {_display_path(path)}")
    gltf = json.loads(json_payload.decode("utf-8").rstrip(" \t\r\n\0"))
    if not isinstance(gltf, dict):
        raise ValueError(f"GLB JSON chunk is not an object: {_display_path(path)}")
    return gltf, binary_payload

def normalize_step_edge_render_visibility_classes(value: object) -> tuple[str, ...]:
    if value is None:
        return STEP_EDGE_DEFAULT_RENDER_VISIBILITY_CLASSES
    raw_values = value if isinstance(value, (list, tuple, set, frozenset)) else [value]
    valid_values = set(STEP_EDGE_VISIBILITY_CLASSES.values())
    normalized: list[str] = []
    for raw in raw_values:
        normalized_value = str(raw or "").strip()
        if normalized_value in valid_values and normalized_value not in normalized:
            normalized.append(normalized_value)
    if STEP_EDGE_VISIBILITY_CLASSES["FEATURE"] not in normalized:
        normalized.insert(0, STEP_EDGE_VISIBILITY_CLASSES["FEATURE"])
    ordered = [
        class_id
        for class_id in STEP_EDGE_RENDER_VISIBILITY_CLASSES
        if class_id in normalized
    ]
    extras = [
        class_id
        for class_id in normalized
        if class_id not in STEP_EDGE_RENDER_VISIBILITY_CLASSES
    ]
    return tuple(ordered + extras)


def step_topology_capabilities(
    edge_visibility_classes: object = None,
) -> dict[str, Any]:
    visibility_classes = normalize_step_edge_render_visibility_classes(edge_visibility_classes)
    return {
        "edgeClassification": {
            "algorithm": STEP_TOPOLOGY_EDGE_CLASSIFICATION_ALGORITHM,
            "angularToleranceDeg": STEP_TOPOLOGY_EDGE_ANGULAR_TOLERANCE_DEG,
            "samples": STEP_TOPOLOGY_EDGE_SAMPLE_COUNT,
        },
        "surfaceEdgeRendering": {
            "algorithm": STEP_TOPOLOGY_SURFACE_EDGE_ALGORITHM,
            "primitiveAttributes": {
                "barycentric": STEP_EDGE_BARYCENTRIC_ATTRIBUTE,
                "class": STEP_EDGE_CLASS_ATTRIBUTE,
            },
            "classCodes": STEP_EDGE_SURFACE_CLASS_CODES,
            "visibilityClasses": list(visibility_classes),
        },
    }


def step_edge_surface_class_code(
    edge: Mapping[str, Any],
    *,
    enabled_visibility_classes: object = None,
) -> int:
    flags = int(edge.get("flags") or 0)
    visibility_class = str(edge.get("visibilityClass") or "").strip()
    if enabled_visibility_classes is not None:
        enabled = set(normalize_step_edge_render_visibility_classes(enabled_visibility_classes))
        if visibility_class not in enabled:
            return STEP_EDGE_SURFACE_CLASS_CODES["none"]
    if flags & STEP_EDGE_FLAGS["DEGENERATE"] or visibility_class == STEP_EDGE_VISIBILITY_CLASSES["DEGENERATE"]:
        return STEP_EDGE_SURFACE_CLASS_CODES["degenerate"]
    if flags & STEP_EDGE_FLAGS["SEAM"] or visibility_class == STEP_EDGE_VISIBILITY_CLASSES["SEAM"]:
        return STEP_EDGE_SURFACE_CLASS_CODES["seam"]
    if flags & STEP_EDGE_FLAGS["BOUNDARY"] or visibility_class == STEP_EDGE_VISIBILITY_CLASSES["BOUNDARY"]:
        return STEP_EDGE_SURFACE_CLASS_CODES["boundary"]
    if flags & STEP_EDGE_FLAGS["NON_MANIFOLD"] or visibility_class == STEP_EDGE_VISIBILITY_CLASSES["NON_MANIFOLD"]:
        return STEP_EDGE_SURFACE_CLASS_CODES["nonManifold"]
    if flags & STEP_EDGE_FLAGS["UNKNOWN_CONTINUITY"] or visibility_class == STEP_EDGE_VISIBILITY_CLASSES["UNKNOWN"]:
        return STEP_EDGE_SURFACE_CLASS_CODES["unknown"]
    if flags & STEP_EDGE_FLAGS["TANGENT"] or visibility_class == STEP_EDGE_VISIBILITY_CLASSES["TANGENT"]:
        return STEP_EDGE_SURFACE_CLASS_CODES["tangent"]
    if flags & STEP_EDGE_FLAGS["HARD"] or visibility_class == STEP_EDGE_VISIBILITY_CLASSES["FEATURE"]:
        return STEP_EDGE_SURFACE_CLASS_CODES["feature"]
    # Deliberate fallthrough, not a gap: an edge carrying none of the flags above
    # (no continuity classification at all) renders as a feature edge, same as the
    # explicit HARD/FEATURE branch above. This keeps EVERY classified edge in
    # exactly one class.
    return STEP_EDGE_SURFACE_CLASS_CODES["feature"]


def is_displayable_step_edge_surface_class_code(value: object) -> bool:
    try:
        code = int(value)
    except (TypeError, ValueError):
        return False
    return code not in {STEP_EDGE_SURFACE_CLASS_CODES["none"], STEP_EDGE_SURFACE_CLASS_CODES["degenerate"]}


def read_step_topology_index_from_glb(glb_path: Path, *, entry_path: Path | None = None) -> dict[str, Any] | None:
    # A view DIRECTORY carries its topology index as its
    # assembly.json. The monolith-GLB branch that used to read an
    # embedded index from a file is gone with the beside-model layout: every
    # artifact is a store directory.
    if not glb_path.is_dir():
        return None
    descriptor_path = glb_path / "assembly.json"
    if not descriptor_path.is_file():
        return None
    try:
        manifest = json.loads(descriptor_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(manifest, dict):
        return None
    # The ONE merge point for the source sidecar: the assembly.json is
    # STEP-pure (source_sidecar.py), so source-derived state — provenance
    # the freshness gates read, pose, mates — is attached here under an
    # internal key every manifest consumer shares. Never written to disk.
    # The sidecar lives BESIDE THE MODEL, so callers that know the entry
    # file pass it; store packages themselves carry no source state.
    if entry_path is not None:
        from cadgen._internal.source_sidecar import read_source_provenance

        # The records-tier provenance record every generated build writes.
        sidecar = read_source_provenance(entry_path)
        if sidecar is not None:
            manifest["_sourceSidecar"] = sidecar
    return manifest


def read_step_topology_manifest_from_glb(glb_path: Path, *, entry_path: Path | None = None) -> dict[str, Any] | None:
    return read_step_topology_index_from_glb(glb_path, entry_path=entry_path)


def build_step_topology_index_manifest(
    manifest: Mapping[str, Any],
    *,
    entry_kind: str | None = None,
) -> dict[str, Any]:
    resolved_entry_kind = str(entry_kind or "").strip().lower()
    assembly = manifest.get("assembly")
    if not resolved_entry_kind:
        resolved_entry_kind = "assembly" if isinstance(assembly, Mapping) else "part"
    if resolved_entry_kind not in {"part", "assembly"}:
        resolved_entry_kind = "part"

    tables = manifest.get("tables") if isinstance(manifest.get("tables"), Mapping) else {}
    occurrence_columns = tables.get("occurrenceColumns") if isinstance(tables, Mapping) else None
    # No version field: the store KEY (CACHE_SCHEMA_VERSION salt) is the one
    # regeneration signal, and nothing inside an artifact records a scheme.
    index: dict[str, Any] = {
        "profile": "index",
        "entryKind": resolved_entry_kind,
    }
    # STEP-pure keys only: source-derived state rides the source sidecar
    # (source_sidecar.py), attached by the tree reader as _sourceSidecar.
    for key in (
        "capabilities",
        "stepPath",
        "stepHash",
        "bbox",
        "stats",
        "edgeRendering",
    ):
        value = manifest.get(key)
        if value is not None:
            index[key] = value
    if isinstance(occurrence_columns, list):
        index["tables"] = {"occurrenceColumns": occurrence_columns}
    occurrences = manifest.get("occurrences")
    if isinstance(occurrences, list):
        index["occurrences"] = occurrences
    if isinstance(assembly, Mapping):
        index["assembly"] = assembly
        index["entryKind"] = "assembly"
    return index
