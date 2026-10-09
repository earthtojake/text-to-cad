"""Validated component meshes: immutable GLB objects, input-keyed indexes.

The kernel-free half of the store's mesh format: glTF 2.0 binary (GLB), its
validation and its encoder. cadgen is the only producer -- OCCT's mesher, run on
a component's exact BREP (``cadgen/_internal/occt_mesh.py``) -- and every
consumer only reads: the CAD Viewer, snapshots and mesh exports draw the same
stored triangles. A probe reads only the small index and the object's observed
size. Body reads remain bound to that exact object and an admitted byte limit;
they verify both the content address and the payload's complete input identity
before returning. SURF hashes are provenance here, not additional required
objects or GC roots.

One body is one component at one tolerance pair, in CAD units (millimetres, Z
up), laid out so a reader views every array in place:

- the BIN chunk holds, each section 4-byte aligned and present only when it is
  not empty: POSITION and NORMAL (float32 xyz per vertex), the indices of the
  ONE triangle primitive (uint16 for a component of at most 65,535 vertices,
  else uint32), the face table (uint32 rows ``ord, indexStart, indexCount,
  colour``: a face's triangles are one contiguous index range, its colour 0 for
  none, else a row of the palette plus one), the edge table (uint32 rows ``ord,
  pointStart, pointCount, class``) and every edge's polyline (float32 xyz) back
  to back;
- the JSON chunk is what any glTF reader needs to draw that primitive -- one
  node carrying the CAD -> glTF frame (Z-up millimetres shown Y-up in metres),
  one mesh, three accessors -- and, in ``extras.cadgen``, the body's identity,
  its bounds, scale and part colour, the face colour palette (exact doubles),
  the names the class codes index, and where each table is. It is the
  canonical JSON for those values: a reader rebuilds it and requires it, so
  nothing but the tables grows with the component.

A face the mesh can resolve that no mesher could cover -- OCCT refused it and
its own tessellation (``cadgen/_internal/face_fallback.py``) did not cover its
area -- leaves the component meshed without it: its face range is empty, and
``extras.cadgen.unmeshedFaces`` names it among the ordinals of every such face
(present only when there is one), so each reader says what it does not draw or
write; the index record counts them (``unmeshedFaceCount``, likewise).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import struct
from typing import TYPE_CHECKING, Any

from cadgen.tessellation_policy import DEFAULT_TESSELLATION, tolerance_refusal
from cadgen.store.index import entry_path, write_entry
from cadgen.store.objects import object_path, put_object

if TYPE_CHECKING:
    # The code that builds or views a body's arrays imports numpy where it runs: keys,
    # probes and reads stay stdlib-only for a process that only serves stored meshes
    # (the CAD Viewer's server).
    import numpy as np

# 6: glTF 2.0 binary replaced TESS v5 (one triangle primitive, face and edge
# tables in buffer views, no per-vertex face ordinals).
PAYLOAD_VERSION = 6
# 10: OCCT BRepMesh on the exact BREP replaced the JavaScript surface tessellator.
TESSELLATOR_VERSION = 10
MESH_INDEX_SCHEMA = 2
MAX_INDEX_BYTES = 16 * 1024
# The JSON chunk grows only with the face colour palette, which holds each distinct
# colour once. tessellationCache.js MESH_MAX_JSON_BYTES is the same number.
MAX_JSON_BYTES = 64 * 1024 * 1024
MAX_SAFE_INTEGER = 2**53 - 1
# The standard rung of the display ladder (cadgen.tessellation_policy): what a key
# that names no tolerances means.
DEFAULT_CHORD = DEFAULT_TESSELLATION["chordTolerance"]
DEFAULT_ANGLE = DEFAULT_TESSELLATION["angleTolerance"]
# The class codes of the edge table, in this order (tessellationCache.js MESH_EDGE_CLASSES).
EDGE_CLASSES = ("none", "feature", "tangent", "seam", "degenerate", "boundary", "nonManifold", "unknown")
_EDGE_CODES = {name: code for code, name in enumerate(EDGE_CLASSES)}
# A component of at most this many vertices indexes in UNSIGNED_SHORT; glTF reserves 65,535.
UNSIGNED_SHORT_VERTEX_LIMIT = 65535
# Z-up millimetres as glTF's Y-up metres: -90 degrees about X, then 0.001.
NODE_ROTATION = [-math.sqrt(0.5), 0.0, 0.0, math.sqrt(0.5)]
NODE_SCALE = [0.001, 0.001, 0.001]
_GLB_MAGIC, _GLB_VERSION, _JSON_CHUNK, _BIN_CHUNK = 0x46546C67, 2, 0x4E4F534A, 0x004E4942
_FLOAT, _UNSIGNED_SHORT, _UNSIGNED_INT = 5126, 5123, 5125
_ARRAY_BUFFER, _ELEMENT_ARRAY_BUFFER = 34962, 34963
_TABLE_COLUMNS = 4
_KEY = re.compile(
    rf"([0-9a-f]{{64}})-t{TESSELLATOR_VERSION}-p{PAYLOAD_VERSION}"
    rf"-l([0-9a-f]{{16}})-a([0-9a-f]{{16}})"
)
# Any mesher's and payload format's key, this cadgen's or another's (``obsolete_key``).
_ANY_KEY = re.compile(r"([0-9a-f]{64})-t(\d+)-p(\d+)-l[0-9a-f]{16}-a[0-9a-f]{16}")
_QUALITY_FIELDS = {"chordTolerance", "chordToleranceF64", "angleTolerance", "angleToleranceF64"}
# ``extras.cadgen``'s values, in the order the writer spells them -- ``unmeshedFaces``
# last, and only in a body that has one; the class names and the table references follow
# them.
_CAD_VALUES = ("payloadVersion", "tessellatorVersion", "tessellationInput", "surfaceInput", "surfaceObject",
               "quality", "bounds", "scale", "partColor", "faceColors")
_UNMESHED = "unmeshedFaces"
_COUNT_FIELDS = ("vertexCount", "indexCount", "faceCount", "edgeCount", "edgePointCount")
_RECORD_FIELDS = {
    "schemaVersion", "object", "byteLength", "decodedBytes", "surfaceInput", "surfaceObject",
    "tessellationInput", "renderIdentity", "quality", "tessellatorVersion", "payloadVersion",
    *_COUNT_FIELDS,
}
# The record of a body with unmeshed faces counts them.
_UNMESHED_COUNT = "unmeshedFaceCount"


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
    return type(value) is list and len(value) == 4 and all(map(_finite_number, value))


def _reject_json_constant(value: str):
    raise ValueError(f"nonfinite tessellation JSON constant: {value}")


def _read_json(payload: bytes) -> Any:
    try:
        return json.loads(payload.decode("utf-8"), parse_constant=_reject_json_constant)
    except (ValueError, RecursionError) as exc:
        raise ValueError("invalid tessellation JSON") from exc


# The canonical JSON holds no boolean, and no string of it spells one: a chunk with
# either token is not canonical, which lets ``==`` (where True == 1) decide the rest.
_BOOLEAN_TOKENS = (b"true", b"false")


def float64_hex(value: Any) -> str:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError("tessellation tolerances must be positive finite binary64 values")
    return struct.pack(">d", float(value)).hex()


def tessellation_quality(chord: float = DEFAULT_CHORD, angle: float = DEFAULT_ANGLE) -> dict:
    return {
        "chordTolerance": chord, "chordToleranceF64": float64_hex(chord),
        "angleTolerance": angle, "angleToleranceF64": float64_hex(angle),
    }


def normalize_tessellations(value: Any) -> list[tuple[float, float]]:
    """``[{chordTolerance, angleTolerance}, ...]`` as sorted, distinct (chord, angle) pairs.

    What a request may ask to have meshed: both tolerances, positive finite
    binary64 values within the tessellation policy's bounds
    (``cadgen.tessellation_policy.tolerance_refusal``); anything else is a
    ValueError before any work starts.
    """
    if value is None:
        return []
    if type(value) not in (list, tuple):
        raise ValueError("tessellations must be a list of {chordTolerance, angleTolerance}")
    pairs = set()
    for item in value:
        if type(item) is not dict or set(item) != {"chordTolerance", "angleTolerance"}:
            raise ValueError("a tessellation is exactly {chordTolerance, angleTolerance}")
        chord, angle = item["chordTolerance"], item["angleTolerance"]
        tessellation_quality(chord, angle)  # positive finite binary64 values, or ValueError
        refusal = (tolerance_refusal("chordTolerance", float(chord), name="chordTolerance")
                   or tolerance_refusal("angleTolerance", float(angle), name="angleTolerance"))
        if refusal is not None:
            raise ValueError(refusal)
        pairs.add((float(chord), float(angle)))
    return sorted(pairs)


def tessellation_key(surface_input: str, chord: float = DEFAULT_CHORD, angle: float = DEFAULT_ANGLE) -> str:
    if not _digest(surface_input):
        raise ValueError("surface input must be a full lowercase content digest")
    return f"{surface_input}-t{TESSELLATOR_VERSION}-p{PAYLOAD_VERSION}-l{float64_hex(chord)}-a{float64_hex(angle)}"


def obsolete_key(key: Any) -> bool:
    """Whether a mesh entry's key is an older mesher's or payload format's than this
    cadgen's: no reader asks for it again (STORE.md §8). A newer cadgen's is not."""
    match = _ANY_KEY.fullmatch(key) if isinstance(key, str) else None
    if match is None:
        return False
    mesher, payload = int(match[2]), int(match[3])
    return (mesher <= TESSELLATOR_VERSION and payload <= PAYLOAD_VERSION
            and (mesher, payload) != (TESSELLATOR_VERSION, PAYLOAD_VERSION))


def parse_key(key: Any) -> tuple[str, float, float] | None:
    """A valid key's (surface input, chord, angle); None for anything else."""
    if not valid_key(key):
        return None
    match = _KEY.fullmatch(key)
    return (match[1], struct.unpack(">d", bytes.fromhex(match[2]))[0],
            struct.unpack(">d", bytes.fromhex(match[3]))[0])


def meshable_key(key: Any) -> tuple[str, float, float] | None:
    """``parse_key`` for a key anything may ask to have meshed: its tolerances within
    the tessellation policy's bounds, as ``normalize_tessellations`` holds a
    request's. None for anything else, a valid key outside them included."""
    parsed = parse_key(key)
    if parsed is None or tolerance_refusal("chordTolerance", parsed[1], name="chordTolerance") is not None:
        return None
    return parsed if tolerance_refusal("angleTolerance", parsed[2], name="angleTolerance") is None else None


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


def decoded_bytes(counts: dict) -> int:
    """What decoding a body costs beyond its bytes: the client's mesh data (positions,
    normals, uint32 indices, the edges' points and segment pairs), never less than
    what it builds, and an allowance per face and edge for the selector tables."""
    edge_segments = counts["edgePointCount"] - counts["edgeCount"]
    return (24 * counts["vertexCount"] + 4 * counts["indexCount"] + 12 * counts["edgePointCount"]
            + 8 * edge_segments + 256 * (counts["faceCount"] + counts["edgeCount"]))


def _sections(counts: dict) -> list[tuple[str, int, int | None]]:
    """(name, byte length, target) of each BIN section the counts give, in order."""
    vertices, indices = counts["vertexCount"], counts["indexCount"]
    sections: list[tuple[str, int, int | None]] = []
    if vertices:
        width = 2 if vertices <= UNSIGNED_SHORT_VERTEX_LIMIT else 4
        sections += [("POSITION", 12 * vertices, _ARRAY_BUFFER), ("NORMAL", 12 * vertices, _ARRAY_BUFFER),
                     ("indices", width * indices, _ELEMENT_ARRAY_BUFFER)]
    if counts["faceCount"]:
        sections.append(("cadgen.faces", 4 * _TABLE_COLUMNS * counts["faceCount"], None))
    if counts["edgeCount"]:
        sections += [("cadgen.edges", 4 * _TABLE_COLUMNS * counts["edgeCount"], None),
                     ("cadgen.edgePoints", 12 * counts["edgePointCount"], None)]
    return sections


def canonical_gltf(cad: dict, counts: dict) -> dict:
    """The JSON chunk of a body with these ``extras.cadgen`` values (identity, bounds,
    scale, colours) and these counts: what ``encode_payload`` writes, and what every
    reader requires (tessellationCache.js ``canonicalMeshGltf``)."""
    vertices, indices = counts["vertexCount"], counts["indexCount"]
    views, offset, table = [], 0, {}
    for name, length, target in _sections(counts):
        view: dict[str, Any] = {"buffer": 0, "byteOffset": offset, "byteLength": length}
        if target is not None:
            view["target"] = target
        else:
            view["name"] = name
            table[name[len("cadgen."):]] = len(views)
        views.append(view)
        offset += length + (-length % 4)
    extras = {**cad, "edgeClasses": list(EDGE_CLASSES)}
    for name, count in (("faces", counts["faceCount"]), ("edges", counts["edgeCount"]),
                        ("edgePoints", counts["edgePointCount"])):
        if name in table:
            extras[name] = {"bufferView": table[name], "count": count}
    gltf: dict[str, Any] = {"asset": {"version": "2.0", "generator": "cadgen"}, "extras": {"cadgen": extras}}
    if vertices:
        gltf.update({
            "scene": 0,
            "scenes": [{"nodes": [0]}],
            "nodes": [{"mesh": 0, "rotation": list(NODE_ROTATION), "scale": list(NODE_SCALE)}],
            "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1}, "indices": 2, "mode": 4}]}],
            "accessors": [
                {"bufferView": 0, "componentType": _FLOAT, "count": vertices, "type": "VEC3",
                 "min": list(cad["bounds"]["min"]), "max": list(cad["bounds"]["max"])},
                {"bufferView": 1, "componentType": _FLOAT, "count": vertices, "type": "VEC3"},
                {"bufferView": 2, "componentType": _UNSIGNED_SHORT if vertices <= UNSIGNED_SHORT_VERTEX_LIMIT
                 else _UNSIGNED_INT, "count": indices, "type": "SCALAR"},
            ],
        })
    if views:
        gltf["bufferViews"] = views
        gltf["buffers"] = [{"byteLength": offset}]
    return gltf


class MeshPayload:
    """One validated body's values and views: arrays are numpy views over its bytes."""

    __slots__ = ("cad", "counts", "positions", "normals", "indices", "faces", "edges", "edge_points")

    def __init__(self, cad, counts, positions, normals, indices, faces, edges, edge_points):
        self.cad, self.counts = cad, counts
        self.positions, self.normals, self.indices = positions, normals, indices
        self.faces, self.edges, self.edge_points = faces, edges, edge_points

    def face_ranges(self) -> list[dict]:
        """``[{ord, color, indexStart, indexCount}]``, a face's colour its palette row or None."""
        palette = self.cad["faceColors"]
        return [{"ord": int(ordinal), "color": palette[ref - 1] if ref else None,
                 "indexStart": int(start), "indexCount": int(count)}
                for ordinal, start, count, ref in self.faces.tolist()]

    @property
    def unmeshed_faces(self) -> list[int]:
        """The faces no mesher could cover, which the body does not draw."""
        return list(self.cad.get(_UNMESHED, []))


def _validate_cad(cad: Any) -> None:
    """``extras.cadgen``'s values, before its canonical JSON can be rebuilt from them."""
    if type(cad) is not dict:
        raise ValueError("tessellation lacks its cadgen extras")
    bounds = cad.get("bounds")
    if type(bounds) is not dict or set(bounds) != {"min", "max"} or any(
        type(bounds[name]) is not list or len(bounds[name]) != 3
        or not all(map(_finite_number, bounds[name])) for name in ("min", "max")
    ) or any(lo > hi for lo, hi in zip(bounds["min"], bounds["max"])):
        raise ValueError("invalid tessellation bounds")
    if not _finite_number(cad.get("scale")) or cad["scale"] <= 0:
        raise ValueError("invalid tessellation scale")
    if cad.get("partColor") is not None and not _color(cad["partColor"]):
        raise ValueError("invalid tessellation part color")
    palette = cad.get("faceColors")
    if type(palette) is not list or not all(map(_color, palette)):
        raise ValueError("invalid tessellation face colours")
    if _UNMESHED in cad:
        unmeshed = cad[_UNMESHED]
        if (type(unmeshed) is not list or not unmeshed or not all(_integer(ordinal) and ordinal > 0 for ordinal in unmeshed)
                or any(later <= earlier for earlier, later in zip(unmeshed, unmeshed[1:]))):
            raise ValueError("invalid tessellation unmeshed faces")


def _cad_values(cad: dict) -> dict:
    """``extras.cadgen``'s values, ``unmeshedFaces`` among them where the body has it."""
    values = {name: cad[name] for name in _CAD_VALUES}
    if _UNMESHED in cad:
        values[_UNMESHED] = cad[_UNMESHED]
    return values


def _table_count(cad: dict, name: str) -> int:
    reference = cad.get(name)
    if reference is None:
        return 0
    if type(reference) is not dict or not _integer(reference.get("count")) or reference["count"] <= 0:
        raise ValueError(f"invalid tessellation {name} table")
    return reference["count"]


def _payload_json(payload: bytes) -> tuple[dict, dict, dict, int, int]:
    """A body's GLB framing and JSON chunk, which must be the canonical JSON for its
    values: ``(that JSON, its extras.cadgen, its counts, BIN start, BIN length)``.
    ValueError for anything else."""
    data = memoryview(payload)
    if len(data) < 20:
        raise ValueError("truncated tessellation payload")
    magic, version, length, json_length, json_type = struct.unpack_from("<IIIII", data)
    if magic != _GLB_MAGIC or version != _GLB_VERSION or length != len(data) or json_type != _JSON_CHUNK:
        raise ValueError("unsupported tessellation payload")
    if not 0 < json_length <= MAX_JSON_BYTES or json_length % 4 or 20 + json_length > len(data):
        raise ValueError("invalid tessellation JSON length")
    bin_start, bin_length = 20 + json_length, 0
    if bin_start < len(data):
        if bin_start + 8 > len(data):
            raise ValueError("truncated tessellation BIN chunk")
        bin_length, bin_type = struct.unpack_from("<II", data, bin_start)
        bin_start += 8
        if bin_type != _BIN_CHUNK or bin_length == 0 or bin_length % 4 or bin_start + bin_length != len(data):
            raise ValueError("invalid tessellation BIN chunk")
    text = bytes(data[20:20 + json_length])
    if any(token in text for token in _BOOLEAN_TOKENS):
        raise ValueError("tessellation JSON is not the canonical JSON for its values")
    gltf = _read_json(text)
    if type(gltf) is not dict or type(gltf.get("extras")) is not dict:
        raise ValueError("invalid tessellation JSON")
    cad = gltf["extras"].get("cadgen")
    _validate_cad(cad)
    accessors = gltf.get("accessors")
    vertices = indices = 0
    if accessors is not None:
        if (type(accessors) is not list or len(accessors) != 3 or not all(type(item) is dict for item in accessors)
                or not _integer(accessors[0].get("count")) or not _integer(accessors[2].get("count"))):
            raise ValueError("invalid tessellation accessors")
        vertices, indices = accessors[0]["count"], accessors[2]["count"]
        if not vertices or not indices or indices % 3:
            raise ValueError("invalid tessellation triangle counts")
    counts = {"vertexCount": vertices, "indexCount": indices, "faceCount": _table_count(cad, "faces"),
              "edgeCount": _table_count(cad, "edges"), "edgePointCount": _table_count(cad, "edgePoints")}
    if (counts["edgeCount"] == 0) != (counts["edgePointCount"] == 0):
        raise ValueError("invalid tessellation edge counts")
    try:
        expected = canonical_gltf(_cad_values(cad), counts)
    except KeyError as exc:
        raise ValueError(f"tessellation extras lack {exc}") from exc
    if gltf != expected:
        raise ValueError("tessellation JSON is not the canonical JSON for its values")
    if bin_length != (expected.get("buffers") or [{"byteLength": 0}])[0]["byteLength"]:
        raise ValueError("tessellation BIN chunk does not match its buffer views")
    return expected, cad, counts, bin_start, bin_length


def decode_payload(payload: bytes) -> MeshPayload:
    """One body's values and views, validated: GLB framing, the canonical JSON for its
    values, and tables whose ordinals rise, whose ranges cover their arrays exactly
    and whose colour and class references resolve. ValueError for anything else."""
    import numpy as np

    expected, cad, counts, bin_start, _ = _payload_json(payload)
    vertices, indices = counts["vertexCount"], counts["indexCount"]

    def view(index: int, dtype: str, columns: int):
        entry = expected["bufferViews"][index]
        return np.frombuffer(payload, dtype, entry["byteLength"] // int(dtype[2]),
                             bin_start + entry["byteOffset"]).reshape(-1, columns)

    names = [entry.get("name", "") for entry in expected.get("bufferViews", [])]
    if vertices:
        positions, normals = view(0, "<f4", 3), view(1, "<f4", 3)
        flat = view(2, "<u2" if vertices <= UNSIGNED_SHORT_VERTEX_LIMIT else "<u4", 1).reshape(-1)
        if int(flat.max()) >= vertices:
            raise ValueError("tessellation indices reach past its vertices")
    else:
        positions = normals = np.zeros((0, 3), "<f4")
        flat = np.zeros(0, "<u4")
    empty_table = np.zeros((0, _TABLE_COLUMNS), "<u4")
    faces = view(names.index("cadgen.faces"), "<u4", _TABLE_COLUMNS) if counts["faceCount"] else empty_table
    edges = view(names.index("cadgen.edges"), "<u4", _TABLE_COLUMNS) if counts["edgeCount"] else empty_table
    points = (view(names.index("cadgen.edgePoints"), "<f4", 3) if counts["edgeCount"]
              else np.zeros((0, 3), "<f4"))

    # Both tables are (ord, start, count, reference) rows: the faces cover the triangles
    # once each, in order, and the edges their points.
    for table, name, total, multiple in ((faces, "face", indices, 3), (edges, "edge", counts["edgePointCount"], 1)):
        if not len(table):
            if total:
                raise ValueError(f"incomplete tessellation {name} table")
            continue
        rows = table.astype(np.int64)
        ordinals, starts, sizes = rows[:, 0], rows[:, 1], rows[:, 2]
        ends = sizes.cumsum()
        if (ordinals[0] < 1 or (ordinals[1:] <= ordinals[:-1]).any() or starts[0] != 0
                or (starts[1:] != ends[:-1]).any() or (sizes % multiple).any()):
            raise ValueError(f"invalid tessellation {name} table")
        if int(ends[-1]) != total:
            raise ValueError(f"incomplete tessellation {name} table")
    if len(faces) and int(faces[:, 3].max()) > len(cad["faceColors"]):
        raise ValueError("a tessellation face colour is not in its palette")
    if _UNMESHED in cad:
        empty = {int(ordinal) for ordinal, _start, count, _ref in faces.tolist() if not count}
        if not set(cad[_UNMESHED]) <= empty:
            raise ValueError("a tessellation's unmeshed face is not an empty face of its table")
    if len(edges) and (int(edges[:, 2].min()) < 2 or int(edges[:, 3].max()) >= len(EDGE_CLASSES)):
        raise ValueError("invalid tessellation edge polyline or class")
    return MeshPayload(cad, counts, positions, normals, flat, faces, edges, points)


def payload_record(key: str, payload: bytes) -> dict:
    """Validate a complete body, its tables too, and return its canonical index facts."""
    if not valid_key(key):
        raise ValueError("invalid tessellation input or payload")
    decoded = decode_payload(payload)
    return _record(key, payload, decoded.cad, decoded.counts)


def _record(key: str, payload: bytes, cad: dict, counts: dict) -> dict:
    """The index facts of a body whose JSON gave these values and counts."""
    quality = _quality(cad.get("quality"))
    surface_input, surface_object = cad.get("surfaceInput"), cad.get("surfaceObject")
    if not _digest(surface_object):
        raise ValueError("invalid tessellation surface object")
    expected_key = tessellation_key(surface_input, quality["chordTolerance"], quality["angleTolerance"])
    if (cad.get("tessellatorVersion") != TESSELLATOR_VERSION or cad.get("payloadVersion") != PAYLOAD_VERSION
            or expected_key != key or cad.get("tessellationInput") != key):
        raise ValueError("tessellation payload belongs to a different input")
    record = {
        "schemaVersion": MESH_INDEX_SCHEMA, "object": hashlib.sha256(payload).hexdigest(),
        "byteLength": len(payload), "decodedBytes": decoded_bytes(counts),
        "surfaceInput": surface_input, "surfaceObject": surface_object,
        "tessellationInput": key, "renderIdentity": f"{key}-s{surface_object}",
        "quality": quality, "tessellatorVersion": TESSELLATOR_VERSION, "payloadVersion": PAYLOAD_VERSION,
        **counts,
    }
    if _UNMESHED in cad:
        record[_UNMESHED_COUNT] = len(cad[_UNMESHED])
    if not _valid_record(key, record):
        raise ValueError("invalid tessellation index facts")
    return record


def _array(value: Any, dtype: str, columns: int) -> np.ndarray:
    import numpy as np

    array = np.frombuffer(value, dtype) if isinstance(value, (bytes, bytearray, memoryview)) else np.asarray(value)
    return np.ascontiguousarray(array, dtype).reshape(-1, columns)


def encode_payload(*, surface_input: str, surface_object: str, chord: float, angle: float,
                   positions, normals, indices, face_ranges: list[dict],
                   edges: list[tuple[int, str, Any]], bounds: dict, scale: float,
                   part_color: list | None = None, unmeshed_faces: Any = ()) -> bytes:
    """One component's GLB body.

    ``positions`` and ``normals`` are float32 xyz per vertex and ``indices`` the
    triangles over them (arrays, or little-endian bytes of float32 and uint32);
    ``bounds`` are the positions' (else the polylines') min and max;
    ``face_ranges`` are ``{ord, indexStart, indexCount, color}`` in ordinal order,
    covering the indices; ``edges`` are ``(ord, class, polyline)`` in ordinal
    order, each polyline float32 xyz of at least two points; ``unmeshed_faces``
    are the ordinals of the empty faces no mesher could cover. The result is
    validated before it is returned.
    """
    import numpy as np

    quality = tessellation_quality(chord, angle)
    key = tessellation_key(surface_input, chord, angle)
    positions = _array(positions, "<f4", 3)
    normals = _array(normals, "<f4", 3)
    flat = _array(indices, "<u4", 1).reshape(-1)
    if len(normals) != len(positions) or bool(len(positions)) != bool(len(flat)):
        raise ValueError("a tessellation's normals, positions and triangles must agree")
    # The POSITION accessor's min and max are the bounds, as glTF requires them to be.
    if len(positions) and ([float(v) for v in positions.min(axis=0)] != [float(v) for v in bounds["min"]]
                           or [float(v) for v in positions.max(axis=0)] != [float(v) for v in bounds["max"]]):
        raise ValueError("a tessellation's bounds must be its positions' bounds")
    palette: dict[tuple, int] = {}
    rows = []
    for face in face_ranges:
        color = face.get("color")
        reference = 0 if color is None else palette.setdefault(tuple(float(c) for c in color), len(palette) + 1)
        rows.append((face["ord"], face["indexStart"], face["indexCount"], reference))
    faces = np.array(rows, "<u4").reshape(-1, _TABLE_COLUMNS)
    polylines, rows, start = [], [], 0
    for ordinal, visibility, polyline in edges:
        points = _array(polyline, "<f4", 3)
        if visibility not in _EDGE_CODES:
            raise ValueError(f"unknown tessellation edge class {visibility!r}")
        rows.append((ordinal, start, len(points), _EDGE_CODES[visibility]))
        polylines.append(points)
        start += len(points)
    table = np.array(rows, "<u4").reshape(-1, _TABLE_COLUMNS)
    points = np.concatenate(polylines) if polylines else np.zeros((0, 3), "<f4")
    cad = {
        "payloadVersion": PAYLOAD_VERSION, "tessellatorVersion": TESSELLATOR_VERSION,
        "tessellationInput": key, "surfaceInput": surface_input, "surfaceObject": surface_object,
        "quality": quality,
        "bounds": {"min": [float(v) for v in bounds["min"]], "max": [float(v) for v in bounds["max"]]},
        "scale": float(scale),
        "partColor": None if part_color is None else [float(c) for c in part_color],
        "faceColors": [list(color) for color in palette],
    }
    if unmeshed_faces:
        cad[_UNMESHED] = sorted(int(ordinal) for ordinal in unmeshed_faces)
    counts = {"vertexCount": len(positions), "indexCount": len(flat), "faceCount": len(faces),
              "edgeCount": len(table), "edgePointCount": len(points)}
    gltf = canonical_gltf(cad, counts)
    index_dtype = "<u2" if len(positions) <= UNSIGNED_SHORT_VERTEX_LIMIT else "<u4"
    arrays = {"POSITION": positions, "NORMAL": normals, "indices": flat.astype(index_dtype),
              "cadgen.faces": faces, "cadgen.edges": table, "cadgen.edgePoints": points}
    chunk = b"".join(arrays[name].tobytes() + b"\0" * (-length % 4) for name, length, _ in _sections(counts))
    text = json.dumps(gltf, separators=(",", ":"), allow_nan=False).encode("utf-8")
    text += b" " * (-len(text) % 4)
    total = 12 + 8 + len(text) + (8 + len(chunk) if chunk else 0)
    payload = b"".join([
        struct.pack("<III", _GLB_MAGIC, _GLB_VERSION, total),
        struct.pack("<II", len(text), _JSON_CHUNK), text,
        struct.pack("<II", len(chunk), _BIN_CHUNK) + chunk if chunk else b"",
    ])
    payload_record(key, payload)
    return payload


def _valid_record(key: str, record: Any) -> bool:
    try:
        if (type(record) is not dict or set(record) not in (_RECORD_FIELDS, _RECORD_FIELDS | {_UNMESHED_COUNT})
                or not valid_key(key)):
            return False
        if _UNMESHED_COUNT in record and not (
                _integer(record[_UNMESHED_COUNT]) and 0 < record[_UNMESHED_COUNT] <= record["faceCount"]):
            return False
        quality = _quality(record["quality"])
        if (record["schemaVersion"] != MESH_INDEX_SCHEMA or record["payloadVersion"] != PAYLOAD_VERSION
                or record["tessellatorVersion"] != TESSELLATOR_VERSION
                or not all(_digest(record[name]) for name in ("object", "surfaceInput", "surfaceObject"))):
            return False
        if record["tessellationInput"] != key or tessellation_key(
            record["surfaceInput"], quality["chordTolerance"], quality["angleTolerance"],
        ) != key or record["renderIdentity"] != f"{key}-s{record['surfaceObject']}":
            return False
        if not all(_integer(record[name]) for name in (*_COUNT_FIELDS, "byteLength", "decodedBytes")):
            return False
        if record["edgePointCount"] < 2 * record["edgeCount"] or (record["edgeCount"] == 0) != (record["edgePointCount"] == 0):
            return False
        return (record["byteLength"] >= 20 and record["byteLength"] % 4 == 0
                and record["decodedBytes"] == decoded_bytes(record))
    except (ValueError, TypeError, KeyError, OverflowError, struct.error):
        return False


def probe(key: str) -> dict | None:
    """Bounded metadata only; no body, SURF, native import, or source lookup."""
    if not valid_key(key):
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
        if len(payload) != record["byteLength"]:
            return None
        # The record's content address names the body ``write`` validated whole. A read
        # checks the framing, the canonical JSON and the identity again; the tables are
        # for the decoders that read them (``decode_payload``, tessellationCache.js).
        _, cad, counts, _, _ = _payload_json(payload)
        if _record(key, payload, cad, counts) != record:
            return None
        return payload
    except (OSError, ValueError, TypeError, KeyError, OverflowError, struct.error):
        return None


def unmeshed_faces(payload: bytes) -> list[int]:
    """The faces a valid body leaves undrawn (``unmeshedFaces``), read off its JSON chunk."""
    return list(_payload_json(payload)[1].get(_UNMESHED, []))


def stored_unmeshed_faces(key: str) -> list[int]:
    """The faces the stored mesh at ``key`` leaves undrawn: none when the store lacks it
    or its record counts none, so a reader asks every key it drew for the price of a probe."""
    record = probe(key)
    if record is None or not record.get(_UNMESHED_COUNT):
        return []
    payload = read(key, expected_object=record["object"])
    return unmeshed_faces(payload) if payload is not None else []


def unmeshed_warning(placed: list[tuple[str, str]], faces: list[int], consequence: str) -> str:
    """What a reader says of a component whose mesh leaves ``faces`` undrawn: the
    occurrences that place it (``[(ref, name)]``), the faces, and ``consequence``, whose
    ``{them}`` names the faces as one or several."""
    where = ", ".join(f"#{ref} {name}" if name and name != ref else f"#{ref}" for ref, name in placed[:3])
    if len(placed) > 3:
        where += f" and {len(placed) - 3} more"
    named = ", ".join(f"f{ordinal}" for ordinal in faces[:8]) + (", ..." if len(faces) > 8 else "")
    noun, them = ("face", "it") if len(faces) == 1 else ("faces", "them")
    return f"{where}: {len(faces)} {noun} ({named}) could not be meshed, so {consequence.format(them=them)}"


def write(key: str, payload: bytes) -> dict:
    """Publish a verified object before its input index; observed conflicts fail."""
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
