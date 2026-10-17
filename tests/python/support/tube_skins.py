"""What a player does with cadgen's tube skins, in numpy: the references the tube skin
tests pose with -- a glTF player skinning a tube (``cadgen._internal.tube_skin``), and a
CAD view reading the payload (``cadgen._internal.tube_skin_payload``) and drawing it."""

from __future__ import annotations

import json
import struct

import numpy as np


def joint_matrices(translations: np.ndarray, rotations: np.ndarray) -> np.ndarray:
    """Each joint's 4x4 from its origin and unit quaternion (x, y, z, w)."""
    x, y, z, w = rotations.T
    m = np.zeros((len(rotations), 4, 4))
    m[:, 0, :3] = np.column_stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)])
    m[:, 1, :3] = np.column_stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)])
    m[:, 2, :3] = np.column_stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)])
    m[:, :3, 3] = translations
    m[:, 3, 3] = 1.0
    return m


def skin(joints, rest, tube) -> np.ndarray:
    """``tube``'s vertices (``tube_skin.SkinnedTube``) posed by ``joints``, as a glTF player
    skins them: the weighted sum of each joint's pose times its inverse bind."""
    from cadgen._internal.tube_skin import inverse_binds

    binds = np.transpose(inverse_binds(rest), (0, 2, 1))  # row-major again
    matrices = joint_matrices(joints.translations, joints.rotations) @ binds
    p = np.column_stack([tube.positions.astype(np.float64), np.ones(len(tube.positions))])
    out = np.zeros((len(p), 4))
    for slot in range(2):
        index = tube.joints[:, slot].astype(np.int64)
        out += tube.weights[:, slot, None] * np.einsum("vij,vj->vi", matrices[index], p)
    return out[:, :3]


def decode_tube_skins(data: bytes) -> dict:
    """The payload's content with every array field replaced by its numpy array
    (flat, in its stored dtype): what a view reads."""
    from cadgen.store.meshes import GLB_BIN_CHUNK, GLB_JSON_CHUNK, GLB_MAGIC, GLB_VERSION

    magic, version, total = struct.unpack_from("<III", data)
    if (magic, version) != (GLB_MAGIC, GLB_VERSION) or total != len(data):
        raise ValueError("not a tube skins payload")
    length, kind = struct.unpack_from("<II", data, 12)
    gltf = json.loads(data[20:20 + length])
    binary_length, binary_kind = struct.unpack_from("<II", data, 20 + length)
    if kind != GLB_JSON_CHUNK or binary_kind != GLB_BIN_CHUNK:
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


def view_skin(local: np.ndarray, along: np.ndarray, rest: np.ndarray, key: np.ndarray,
              placement: np.ndarray) -> np.ndarray:
    """What a CAD view draws, in the document: each component-local point blended
    between the two joints either side of it, joint j moving it by
    placement^-1 . key_j . rest_j^-1 . placement, then placed."""
    count = len(rest)
    matrices = np.linalg.inv(placement) @ joint_matrices(key[:, :3], key[:, 3:]) @ np.linalg.inv(
        joint_matrices(rest[:, :3], rest[:, 3:])) @ placement
    lower = np.minimum(np.floor(along).astype(int), count - 2)
    weight = (along - lower)[:, None]
    points = np.column_stack([local, np.ones(len(local))])
    blended = ((1 - weight) * np.einsum("vij,vj->vi", matrices[lower], points)
               + weight * np.einsum("vij,vj->vi", matrices[lower + 1], points))
    return (blended @ placement.T)[:, :3]
