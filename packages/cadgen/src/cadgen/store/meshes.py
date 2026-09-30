"""Validated tessellation entries: immutable TESS objects, input-keyed indexes.

This is the kernel-free Python half of the shared TESS v4 contract. A probe
reads only the small index and the object's observed size. Body reads remain
bound to that exact object and an admitted byte limit; they verify both the
content address and the payload's complete input identity before returning.
SURF hashes are provenance here, not additional required objects or GC roots.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import struct
from typing import Any

from cadgen.store.index import entry_path, write_entry
from cadgen.store.objects import object_path, put_object

TESS_VERSION = 4
TESSELLATOR_VERSION = 5
MESH_INDEX_SCHEMA = 1
MAX_INDEX_BYTES = 16 * 1024
MAX_HEADER_BYTES = 4 * 1024 * 1024
MAX_SAFE_INTEGER = 2**53 - 1
DEFAULT_CHORD = 0.0015
DEFAULT_ANGLE = 0.35
_KEY = re.compile(
    rf"([0-9a-f]{{64}})-t{TESSELLATOR_VERSION}-p{TESS_VERSION}"
    rf"-l([0-9a-f]{{16}})-a([0-9a-f]{{16}})"
)
_QUALITY_FIELDS = {"chordTolerance", "chordToleranceF64", "angleTolerance", "angleToleranceF64"}
_COUNT_FIELDS = ("positionCount", "normalCount", "faceOrdCount", "indexCount", "sideOrdCount")
_SIZE_FIELDS = {"headerBytes", "arrayBytes", "faceRangeCount", "edgeCount", "edgeClassCount", "edgeSegmentCount"}
_EDGE_CLASSES = {"none", "feature", "tangent", "seam", "degenerate", "boundary", "nonManifold", "unknown"}
_RECORD_FIELDS = {
    "schemaVersion", "object", "byteLength", "decodedBytes", "surfaceInput", "surfaceObject",
    "tessellationInput", "renderIdentity", "quality", "tessellatorVersion", "payloadVersion",
    *_SIZE_FIELDS,
}


class MeshConflictError(ValueError):
    """One deterministic tessellation input produced different output bytes."""


def _integer(value: Any) -> bool:
    return type(value) is int and 0 <= value <= MAX_SAFE_INTEGER


def _digest(value: Any) -> bool:
    return type(value) is str and len(value) == 64 and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _finite_number(value: Any) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _color(value: Any) -> bool:
    return value is None or (type(value) is list and len(value) == 4 and all(map(_finite_number, value)))


def _ordinal(value: Any) -> bool:
    return _integer(value) and value > 0


def _reject_json_constant(value: str):
    raise ValueError(f"nonfinite tessellation JSON constant: {value}")


def _read_json(payload: bytes) -> Any:
    try:
        return json.loads(payload, parse_constant=_reject_json_constant)
    except (ValueError, RecursionError) as exc:
        raise ValueError("invalid tessellation JSON") from exc


def _validate_render_metadata(header: dict) -> None:
    """Mirror the shared codec's metadata contract, without decoding arrays."""
    bounds = header.get("bounds")
    if type(bounds) is not dict or any(
        type(bounds.get(name)) is not list or len(bounds[name]) != 3
        or not all(map(_finite_number, bounds[name])) for name in ("min", "max")
    ) or any(lo > hi for lo, hi in zip(bounds["min"], bounds["max"])):
        raise ValueError("invalid tessellation bounds")
    if not _finite_number(header.get("scale")) or header["scale"] <= 0 or not _color(header.get("partColor")):
        raise ValueError("invalid tessellation scale or part color")

    classes = {}
    for pair in header["edgeClasses"]:
        if (type(pair) is not list or len(pair) != 2 or not _ordinal(pair[0])
                or pair[0] in classes or type(pair[1]) is not str or pair[1] not in _EDGE_CLASSES):
            raise ValueError("invalid tessellation edge classes")
        classes[pair[0]] = pair[1]
    edge_ordinals = set()
    for edge in header["edges"]:
        ordinal, visibility = edge.get("ord"), edge.get("visibilityClass")
        if (not _ordinal(ordinal) or ordinal in edge_ordinals or ordinal not in classes
                or (visibility is not None and (type(visibility) is not str or visibility != classes[ordinal]))):
            raise ValueError("invalid tessellation edge metadata")
        edge_ordinals.add(ordinal)

    face_ordinals, next_index = set(), 0
    for face in header["faceRanges"]:
        if type(face) is not dict:
            raise ValueError("invalid tessellation face range")
        ordinal, start, count = face.get("ord"), face.get("indexStart"), face.get("indexCount")
        if (not _ordinal(ordinal) or ordinal in face_ordinals or not _integer(start) or not _integer(count)
                or start % 3 or count % 3 or start != next_index or start + count > header["indexCount"]
                or not _color(face.get("color"))):
            raise ValueError("invalid tessellation face range")
        face_ordinals.add(ordinal)
        next_index += count
    if next_index != header["indexCount"]:
        raise ValueError("incomplete tessellation face ranges")


def float64_hex(value: Any) -> str:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError("tessellation tolerances must be positive finite binary64 values")
    return struct.pack(">d", float(value)).hex()


def tessellation_quality(chord: float = DEFAULT_CHORD, angle: float = DEFAULT_ANGLE) -> dict:
    return {
        "chordTolerance": chord, "chordToleranceF64": float64_hex(chord),
        "angleTolerance": angle, "angleToleranceF64": float64_hex(angle),
    }


def tessellation_key(surface_input: str, chord: float = DEFAULT_CHORD, angle: float = DEFAULT_ANGLE) -> str:
    if not _digest(surface_input):
        raise ValueError("surface input must be a full lowercase content digest")
    return f"{surface_input}-t{TESSELLATOR_VERSION}-p{TESS_VERSION}-l{float64_hex(chord)}-a{float64_hex(angle)}"


def valid_key(key: Any) -> bool:
    if not isinstance(key, str) or _KEY.fullmatch(key) is None:
        return False
    match = _KEY.fullmatch(key)
    try:
        return tessellation_key(
            match[1], struct.unpack(">d", bytes.fromhex(match[2]))[0],
            struct.unpack(">d", bytes.fromhex(match[3]))[0],
        ) == key
    except (ValueError, OverflowError, struct.error):
        return False


def _quality(value: Any) -> dict:
    if type(value) is not dict or set(value) != _QUALITY_FIELDS:
        raise ValueError("invalid tessellation quality")
    expected = tessellation_quality(value["chordTolerance"], value["angleTolerance"])
    if value != expected:
        raise ValueError("tessellation quality bits do not match its values")
    return expected


def _decoded_bytes(sizes: dict) -> int:
    # Typed arrays plus conservative JSON metadata overhead. Encoded bytes are
    # reserved separately by a downloading consumer; this is not an RSS claim.
    return sizes["arrayBytes"] + 8 * sizes["edgeSegmentCount"] + 8 * sizes["headerBytes"] + 256 * (
        sizes["faceRangeCount"] + sizes["edgeCount"] + sizes["edgeClassCount"]
    )


def payload_record(key: str, payload: bytes) -> dict:
    """Validate a complete v4 body and return its canonical index facts."""
    if not valid_key(key) or len(payload) < 12:
        raise ValueError("invalid tessellation input or payload")
    magic, version, header_size = struct.unpack_from("<III", payload)
    if magic != 0x53534554 or version != TESS_VERSION:
        raise ValueError("unsupported tessellation payload")
    if not 0 < header_size <= MAX_HEADER_BYTES or header_size % 4 or 12 + header_size > len(payload):
        raise ValueError("invalid tessellation header length")
    header = _read_json(payload[12:12 + header_size])
    if type(header) is not dict:
        raise ValueError("invalid tessellation header")
    quality = _quality(header.get("quality"))
    surface_input, surface_object = header.get("surfaceInput"), header.get("surfaceDigest")
    if not _digest(surface_object):
        raise ValueError("invalid tessellation surface object")
    expected_key = tessellation_key(surface_input, quality["chordTolerance"], quality["angleTolerance"])
    if (header.get("tessellatorVersion") != TESSELLATOR_VERSION or header.get("payloadVersion") != TESS_VERSION
            or expected_key != key or header.get("tessellationInput") != key):
        raise ValueError("tessellation payload belongs to a different input")
    counts = [header.get(name) for name in _COUNT_FIELDS]
    edges, ranges, classes = header.get("edges"), header.get("faceRanges"), header.get("edgeClasses")
    if not all(type(value) is list for value in (edges, ranges, classes)):
        raise ValueError("tessellation lacks complete rendering metadata")
    if any(type(edge) is not dict for edge in edges):
        raise ValueError("invalid tessellation edges")
    counts.extend(edge.get("count") for edge in edges)
    if not all(_integer(value) for value in counts):
        raise ValueError("invalid tessellation array counts")
    if (header["positionCount"] % 3 or header["normalCount"] != header["positionCount"]
            or header["faceOrdCount"] * 3 != header["positionCount"] or header["indexCount"] % 3
            or header["sideOrdCount"] != header["indexCount"] or any(edge["count"] % 3 for edge in edges)):
        raise ValueError("invalid tessellation vertex, triangle or edge grouping")
    _validate_render_metadata(header)
    array_bytes = sum(counts) * 4
    if array_bytes > MAX_SAFE_INTEGER or 12 + header_size + array_bytes != len(payload):
        raise ValueError("tessellation array lengths do not match the payload")
    sizes = {
        "headerBytes": header_size, "arrayBytes": array_bytes,
        "faceRangeCount": len(ranges), "edgeCount": len(edges), "edgeClassCount": len(classes),
        "edgeSegmentCount": sum(max(0, edge["count"] // 3 - 1) for edge in edges),
    }
    record = {
        "schemaVersion": MESH_INDEX_SCHEMA, "object": hashlib.sha256(payload).hexdigest(),
        "byteLength": len(payload), "decodedBytes": _decoded_bytes(sizes),
        "surfaceInput": surface_input, "surfaceObject": surface_object,
        "tessellationInput": key, "renderIdentity": f"{key}-s{surface_object}",
        "quality": quality, "tessellatorVersion": TESSELLATOR_VERSION, "payloadVersion": TESS_VERSION,
        **sizes,
    }
    if not _valid_record(key, record):
        raise ValueError("invalid tessellation index facts")
    return record


def _valid_record(key: str, record: Any) -> bool:
    try:
        if type(record) is not dict or set(record) != _RECORD_FIELDS or not valid_key(key):
            return False
        quality = _quality(record["quality"])
        if (record["schemaVersion"] != MESH_INDEX_SCHEMA or record["payloadVersion"] != TESS_VERSION
                or record["tessellatorVersion"] != TESSELLATOR_VERSION
                or not all(_digest(record[name]) for name in ("object", "surfaceInput", "surfaceObject"))):
            return False
        if record["tessellationInput"] != key or tessellation_key(
            record["surfaceInput"], quality["chordTolerance"], quality["angleTolerance"],
        ) != key or record["renderIdentity"] != f"{key}-s{record['surfaceObject']}":
            return False
        if not all(_integer(record[name]) for name in (*_SIZE_FIELDS, "byteLength", "decodedBytes")):
            return False
        if not 0 < record["headerBytes"] <= MAX_HEADER_BYTES or record["headerBytes"] % 4:
            return False
        return (record["byteLength"] == 12 + record["headerBytes"] + record["arrayBytes"]
                and record["arrayBytes"] % 4 == 0 and record["decodedBytes"] == _decoded_bytes(record))
    except (ValueError, TypeError, KeyError, OverflowError, struct.error):
        return False


def probe(key: str) -> dict | None:
    """Bounded metadata only; no body, SURF, native import, or source lookup."""
    if os.environ.get("CADGEN_MESH_CACHE") == "0" or not valid_key(key):
        return None
    try:
        with entry_path("mesh", key).open("rb") as stream:
            raw = stream.read(MAX_INDEX_BYTES + 1)
        if len(raw) > MAX_INDEX_BYTES:
            return None
        record = _read_json(raw)
        if not _valid_record(key, record):
            return None
        if object_path(record["object"]).stat().st_size != record["byteLength"]:
            return None
        return record
    except (OSError, ValueError, TypeError, KeyError):
        return None


def read(key: str, *, expected_object: str | None = None, max_bytes: int | None = None) -> bytes | None:
    """Read at most an admitted body's size and verify its exact identity."""
    record = probe(key)
    if record is None or (expected_object is not None and expected_object != record["object"]):
        return None
    limit = record["byteLength"] if max_bytes is None else max_bytes
    if not _integer(limit) or record["byteLength"] > limit:
        return None
    try:
        with object_path(record["object"]).open("rb") as stream:
            if os.fstat(stream.fileno()).st_size != record["byteLength"]:
                return None
            payload = stream.read(record["byteLength"] + 1)
        if len(payload) != record["byteLength"] or payload_record(key, payload) != record:
            return None
        return payload
    except (OSError, ValueError, TypeError, KeyError, OverflowError, struct.error):
        return None


def write(key: str, payload: bytes) -> dict | None:
    """Publish a verified object before its input index; observed conflicts fail."""
    if os.environ.get("CADGEN_MESH_CACHE") == "0":
        return None
    record = payload_record(key, payload)
    prior = probe(key)
    if prior is not None and (prior["object"] != record["object"] or prior["surfaceObject"] != record["surfaceObject"]):
        # A corrupt prior body is a miss and can be repaired. A valid different
        # body for these same deterministic inputs is not a new cache revision.
        if read(key, expected_object=prior["object"]) is not None:
            raise MeshConflictError("tessellation producer returned different bytes for the same immutable input")
    digest = put_object(payload, repair=True)
    if digest != record["object"]:
        raise ValueError("tessellation object address mismatch")
    write_entry("mesh", key, record)
    return record
