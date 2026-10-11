"""A document's bending tubes as a CAD view plays them: bound meshes and every key's joints.

The animated GLB export carries ONE clip's skins in glTF's own terms. A CAD view
(the viewer, the CAD app, a snapshot) plays every clip of the document over the
component meshes it already draws, so it needs the same skins in its terms: each
tube occurrence refined and bound in its component's frame, with the component's
edges bound alongside (``tube_skin.bind_occurrence``), and every key of every tube
track posed as joints. Nothing in a view works out where a tube is; it blends the
joints of two keys and skins (``packages/core``'s tube skin player).

The payload is GLB-framed: a glTF JSON chunk whose ``buffers`` and ``bufferViews``
frame the arrays, and whose ``extras.cadgenTubeSkins`` says what they are::

    {"schemaVersion": 1,
     "bindings": [{"occurrence", "joints", "rest", "positions", "normals", "indices",
                   "sourceTriangles", "along", "material",
                   "edgePositions", "edgeAlong", "edgeOrdinals", "edgeClasses"}, ...],
     "tracks": [{"clip", "track", "keys", "bindings": [binding index, ...]}, ...]}

Every array field is a bufferView index; arrays are little-endian float32, but
``indices``, ``sourceTriangles`` and ``edgeOrdinals`` (uint32) and ``edgeClasses``
(uint8, ``store.meshes.EDGE_CLASSES`` codes). A binding is one occurrence on one
rest centerline and band length, shared by every track that bends it that way:
``positions``/``normals``/``edgePositions`` are component-local millimetres,
``along`` each vertex's joint coordinate (the joint below plus its weight toward
the next), ``material`` its rest arc length and transverse offsets (a braid's
coordinates), ``sourceTriangles`` the component triangle each refined triangle came
from (a view's face ids follow it). ``rest`` is ``(joints, 7)`` and a track's
``keys`` ``(keys, joints, 7)``: each joint's origin and unit quaternion
``(x, y, z, w)``, x along the tangent, in the space the paths are authored in --
one key per time of the sidecar track, in its order, each quaternion on the side
of the key before's so a short-way slerp turns it the way the bake measured.

Derived data, cached in the store's ``skin`` index (``cadgen.store.skins``):
:func:`tube_skins_bytes` is the door, and a second call for the same document,
animation and meshes reads the store.
"""

from __future__ import annotations

import json
import struct
from typing import Any, Mapping

import numpy as np

__all__ = [
    "TUBE_SKINS_SCHEMA_VERSION",
    "build_tube_skins",
    "decode_tube_skins",
    "tube_skins_bytes",
    "tube_tracks",
]

# Bumped with the payload's shape or the binding rule; it is in the store key.
TUBE_SKINS_SCHEMA_VERSION = 1
_SCHEME = f"cadgen-tube-skins-v{TUBE_SKINS_SCHEMA_VERSION}"
_GLB_MAGIC, _JSON_CHUNK, _BIN_CHUNK = 0x46546C67, 0x4E4F534A, 0x004E4942
_DTYPES = {"<f4": np.float32, "<u4": np.uint32, "|u1": np.uint8}


def tube_tracks(animation: Any) -> list[tuple[str, int, Mapping[str, Any]]]:
    """``(clip id, track index, track)`` for every tube track, in the section's order."""
    return [(str(clip.get("id")), index, track)
            for clip in ((animation or {}).get("clips") or [])
            for index, track in enumerate(clip.get("tracks") or []) if track.get("tube") is not None]


def build_tube_skins(descriptor: Mapping[str, Any], components: Mapping[str, Any], animation: Any) -> bytes:
    """The payload for ``descriptor``'s occurrences, ``components`` holding each
    tube component's decoded stored mesh (``store.meshes.decode_payload``) by id."""
    from cadgen._internal import tube_skin

    occurrences = {str(occurrence.get("id")): occurrence for occurrence in descriptor.get("occurrences") or []}
    arrays: list[np.ndarray] = []

    def view(values: np.ndarray, dtype: str) -> int:
        arrays.append(np.ascontiguousarray(values, dtype=dtype).reshape(-1))
        return len(arrays) - 1

    bindings: list[dict] = []
    shared: dict[tuple, int] = {}
    rests: dict[tuple, tuple] = {}
    tracks: list[dict] = []
    for clip_id, index, track in tube_tracks(animation):
        rest_spec, spacing = track["rest"], float(track["maxSegmentLength"])
        shape = (json.dumps(rest_spec, sort_keys=True, separators=(",", ":")), spacing)
        if shape not in rests:
            rest = tube_skin.compile_rest(rest_spec)
            fractions = tube_skin.joint_fractions(rest, spacing)
            rests[shape] = (rest, fractions, tube_skin.joints_on(rest, fractions))
        rest, fractions, rest_joints = rests[shape]
        keys = tube_skin.continuous([tube_skin.key_joints(key, rest_spec, rest, fractions) for key in track["tube"]])
        members = []
        for member in track["targets"]:
            known = shared.get((member, *shape))
            if known is None:
                occurrence = occurrences.get(str(member))
                component = components.get(str((occurrence or {}).get("component") or ""))
                if occurrence is None or component is None:
                    raise ValueError(f"animation clip {clip_id!r} bends {member!r}, which the document does not place")
                bound = tube_skin.bind_occurrence(component, occurrence.get("transform"), rest, spacing, fractions)
                known = shared[(member, *shape)] = len(bindings)
                bindings.append({
                    "occurrence": str(member), "joints": len(fractions),
                    "rest": view(np.hstack([rest_joints.translations, rest_joints.rotations]), "<f4"),
                    "positions": view(bound.positions, "<f4"), "normals": view(bound.normals, "<f4"),
                    "indices": view(bound.indices, "<u4"), "sourceTriangles": view(bound.source_triangles, "<u4"),
                    "along": view(bound.along, "<f4"), "material": view(bound.material, "<f4"),
                    "edgePositions": view(bound.edge_positions, "<f4"), "edgeAlong": view(bound.edge_along, "<f4"),
                    "edgeOrdinals": view(bound.edge_ordinals, "<u4"), "edgeClasses": view(bound.edge_classes, "|u1"),
                })
            members.append(known)
        poses = np.stack([np.hstack([joints.translations, joints.rotations]) for joints in keys])
        tracks.append({"clip": clip_id, "track": index, "keys": view(poses, "<f4"), "bindings": members})
    return _glb({"schemaVersion": TUBE_SKINS_SCHEMA_VERSION, "bindings": bindings, "tracks": tracks}, arrays)


def _glb(content: dict, arrays: list[np.ndarray]) -> bytes:
    views, chunks, offset = [], [], 0
    for values in arrays:
        data = values.tobytes()
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(data)})
        padding = -len(data) % 4
        chunks.append(data + b"\0" * padding)
        offset += len(data) + padding
    binary = b"".join(chunks)
    gltf = {"asset": {"version": "2.0", "generator": "cadgen tube skins"},
            "buffers": [{"byteLength": len(binary)}], "bufferViews": views, "extras": {"cadgenTubeSkins": content}}
    text = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    text += b" " * (-len(text) % 4)
    total = 12 + 8 + len(text) + 8 + len(binary)
    return (struct.pack("<III", _GLB_MAGIC, 2, total) + struct.pack("<II", len(text), _JSON_CHUNK) + text
            + struct.pack("<II", len(binary), _BIN_CHUNK) + binary)


def decode_tube_skins(data: bytes) -> dict:
    """The payload's content with every array field replaced by its numpy array
    (flat, in its stored dtype): what a view reads, for tests and checks."""
    magic, version, total = struct.unpack_from("<III", data)
    if (magic, version) != (_GLB_MAGIC, 2) or total != len(data):
        raise ValueError("not a tube skins payload")
    length, kind = struct.unpack_from("<II", data, 12)
    gltf = json.loads(data[20:20 + length])
    binary_length, binary_kind = struct.unpack_from("<II", data, 20 + length)
    if kind != _JSON_CHUNK or binary_kind != _BIN_CHUNK:
        raise ValueError("not a tube skins payload")
    start = 28 + length
    content = gltf["extras"]["cadgenTubeSkins"]
    views = gltf["bufferViews"]
    dtypes = {"indices": "<u4", "sourceTriangles": "<u4", "edgeOrdinals": "<u4", "edgeClasses": "|u1"}

    def read(field: str, index: int) -> np.ndarray:
        entry = views[index]
        dtype = np.dtype(dtypes.get(field, "<f4"))
        return np.frombuffer(data, dtype, entry["byteLength"] // dtype.itemsize, start + entry["byteOffset"])

    bindings = [{field: (read(field, value) if field not in ("occurrence", "joints") else value)
                 for field, value in binding.items()} for binding in content["bindings"]]
    tracks = [{**track, "keys": read("keys", track["keys"])} for track in content["tracks"]]
    return {"schemaVersion": content["schemaVersion"], "bindings": bindings, "tracks": tracks}


def tube_skins_bytes(*, tree: str, document_hash: str, animation: Any,
                     chord: float | None = None, angle: float | None = None) -> bytes | None:
    """The payload for one document's bytes and sidecar animation, bound to its
    stored meshes at (``chord``, ``angle``) -- the CAD view's default tessellation
    unless named -- or None when the animation bends no tube. What the store lacks
    is derived as an export derives it (build-pool jobs), and the payload is cached
    in the store's ``skin`` index."""
    from cadgen._internal.mesh_export import MeshSource, stored_meshes
    from cadgen._internal.source_sidecar import animation_digest
    from cadgen.store import meshes, skins
    from cadgen.store.view import descriptor_for_view

    tracks = tube_tracks(animation)
    if not tracks:
        return None
    pair = (meshes.DEFAULT_CHORD if chord is None else float(chord),
            meshes.DEFAULT_ANGLE if angle is None else float(angle))
    meshes.normalize_tessellations([{"chordTolerance": pair[0], "angleTolerance": pair[1]}])
    descriptor = descriptor_for_view(tree, document_hash=document_hash)
    if descriptor is None:
        raise FileNotFoundError(f"tube skins: geometry tree missing or unreadable: {tree}")
    placed = {str(occurrence.get("id")): str(occurrence.get("component") or "")
              for occurrence in descriptor.get("occurrences") or []}
    cids = sorted({placed[str(member)] for _clip, _index, track in tracks for member in track["targets"]
                   if str(member) in placed})
    key = skins.skin_input_key(
        scheme=_SCHEME, document_hash=document_hash, animation_digest=animation_digest(animation),
        mesh_keys=[meshes.tessellation_key(descriptor["components"][cid]["surfaceInput"], *pair) for cid in cids],
    )
    cached = skins.read(key)
    if cached is not None:
        return cached
    descriptor, bodies = stored_meshes(MeshSource(tree, document_hash), [pair], None, components=cids)
    data = build_tube_skins(descriptor, {cid: meshes.decode_payload(bodies[(cid, pair)]) for cid in cids}, animation)
    skins.write(key, data)
    return data
