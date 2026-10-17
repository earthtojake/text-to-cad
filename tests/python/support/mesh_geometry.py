"""Comparing meshes by geometry within a tolerance (README law 5).

The body a build holds and the same body as read from the STEP it wrote are one part
(law 20) but other bytes, listing their faces and edges in another order, and the kernel
meshes them to different bytes. A test that crosses that boundary -- a build's own export
against a door's from an empty store, a document rendered beside its source against the
same document alone -- compares what each mesh describes, never its bytes: every vertex of
either mesh lies within the tolerance of the other's triangles.
"""
from __future__ import annotations

import json
import struct

import numpy as np

GLB_MAGIC, GLB_JSON, GLB_BIN = 0x46546C67, 0x4E4F534A, 0x004E4942
_COMPONENT_TYPES = {5120: "<i1", 5121: "<u1", 5122: "<i2", 5123: "<u2", 5125: "<u4", 5126: "<f4"}
_WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def binary_stl_triangles(data: bytes) -> np.ndarray:
    """The triangles of a binary STL, ``(n, 3, 3)`` float64."""
    count = struct.unpack_from("<I", data, 80)[0]
    records = np.frombuffer(data, np.dtype([("normal", "<f4", 3), ("vertices", "<f4", (3, 3)), ("attr", "<u2")]),
                            count, 84)
    return records["vertices"].astype(np.float64)


def glb_document(data: bytes) -> tuple[dict, bytes]:
    """A GLB's JSON document and its binary chunk."""
    magic, version, total = struct.unpack_from("<III", data)
    if (magic, version, total) != (GLB_MAGIC, 2, len(data)):
        raise ValueError("not a GLB")
    length, kind = struct.unpack_from("<II", data, 12)
    if kind != GLB_JSON:
        raise ValueError("a GLB starts with its JSON chunk")
    document = json.loads(data[20:20 + length])
    binary_length, binary_kind = struct.unpack_from("<II", data, 20 + length)
    if binary_kind != GLB_BIN:
        raise ValueError("a GLB's second chunk is its binary")
    return document, data[28 + length:28 + length + binary_length]


def glb_accessor(document: dict, binary: bytes, index: int) -> np.ndarray:
    """One accessor's values, ``(count, width)``."""
    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    width = _WIDTHS[accessor["type"]]
    dtype = _COMPONENT_TYPES[accessor["componentType"]]
    start = view["byteOffset"] + accessor.get("byteOffset", 0)
    return np.frombuffer(binary, dtype, accessor["count"] * width, start).reshape(accessor["count"], width)


def glb_mesh_triangles(document: dict, binary: bytes) -> dict[str, np.ndarray]:
    """Each mesh's triangles in its own frame, by mesh name, ``(n, 3, 3)`` float64, every
    primitive of the mesh together."""
    triangles: dict[str, np.ndarray] = {}
    for index, mesh in enumerate(document.get("meshes", [])):
        parts = []
        for primitive in mesh["primitives"]:
            if primitive.get("mode", 4) != 4:
                continue
            positions = glb_accessor(document, binary, primitive["attributes"]["POSITION"]).astype(np.float64)
            if "indices" in primitive:
                indices = glb_accessor(document, binary, primitive["indices"]).reshape(-1).astype(np.int64)
            else:
                indices = np.arange(len(positions))
            parts.append(positions[indices].reshape(-1, 3, 3))
        triangles[mesh.get("name", f"mesh {index}")] = (np.concatenate(parts) if parts
                                                       else np.zeros((0, 3, 3), np.float64))
    return triangles


def glb_without_mesh_data(document: dict) -> dict:
    """The document with everything a mesh's bytes decide removed -- the meshes, the
    accessors, the buffer views and the buffer -- so two GLBs of one scene compare on the
    rest: nodes, placements, animations by their accessor indices and names, materials."""
    kept = {key: value for key, value in document.items()
            if key not in ("meshes", "accessors", "bufferViews", "buffers")}
    kept["nodes"] = [{key: value for key, value in node.items() if key != "mesh"} for node in document.get("nodes", [])]
    return kept


def distance_to_triangles(points: np.ndarray, triangles: np.ndarray, *, block: int = 256) -> np.ndarray:
    """Each point's distance to the nearest triangle, ``(n,)`` (Ericson, closest point on a
    triangle), computed in blocks of ``block`` points against every triangle."""
    if len(triangles) == 0:
        return np.full(len(points), np.inf)
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    ab, ac = b - a, c - a
    out = np.empty(len(points))
    for start in range(0, len(points), block):
        p = points[start:start + block][:, None, :]
        ap = p - a
        d1 = np.einsum("ijk,jk->ij", ap, ab)
        d2 = np.einsum("ijk,jk->ij", ap, ac)
        bp = p - b
        d3 = np.einsum("ijk,jk->ij", bp, ab)
        d4 = np.einsum("ijk,jk->ij", bp, ac)
        cp = p - c
        d5 = np.einsum("ijk,jk->ij", cp, ab)
        d6 = np.einsum("ijk,jk->ij", cp, ac)
        vc = d1 * d4 - d3 * d2
        vb = d5 * d2 - d1 * d6
        va = d3 * d6 - d5 * d4
        denominator = va + vb + vc
        with np.errstate(divide="ignore", invalid="ignore"):
            v = np.where(denominator != 0, vb / denominator, 0.0)
            w = np.where(denominator != 0, vc / denominator, 0.0)
            s_ab = np.clip(np.where(d1 - d3 != 0, d1 / (d1 - d3), 0.0), 0.0, 1.0)
            s_ac = np.clip(np.where(d2 - d6 != 0, d2 / (d2 - d6), 0.0), 0.0, 1.0)
            s_bc = np.clip(np.where((d4 - d3) + (d5 - d6) != 0, (d4 - d3) / ((d4 - d3) + (d5 - d6)), 0.0), 0.0, 1.0)
        closest = a + v[..., None] * ab + w[..., None] * ac
        closest = np.where(((vc <= 0) & (d1 >= 0) & (d3 <= 0))[..., None], a + s_ab[..., None] * ab, closest)
        closest = np.where(((vb <= 0) & (d2 >= 0) & (d6 <= 0))[..., None], a + s_ac[..., None] * ac, closest)
        closest = np.where(((va <= 0) & (d4 - d3 >= 0) & (d5 - d6 >= 0))[..., None],
                           b + s_bc[..., None] * (c - b), closest)
        closest = np.where(((d1 <= 0) & (d2 <= 0))[..., None], a, closest)
        closest = np.where(((d3 >= 0) & (d4 <= d3))[..., None], b, closest)
        closest = np.where(((d6 >= 0) & (d5 <= d6))[..., None], c, closest)
        out[start:start + block] = np.linalg.norm(p - closest, axis=2).min(axis=1)
    return out


def mesh_deviation(first: np.ndarray, second: np.ndarray) -> float:
    """How far the two triangle meshes (``(n, 3, 3)``) lie apart: the largest distance from
    a vertex of either to the other's triangles."""
    one = distance_to_triangles(first.reshape(-1, 3), second)
    other = distance_to_triangles(second.reshape(-1, 3), first)
    return float(max(one.max() if len(one) else 0.0, other.max() if len(other) else 0.0))


def tolerance_of(chord: float, *meshes: np.ndarray) -> float:
    """The distance two meshes at the chord tolerance ``chord`` (relative to the diagonal, as the
    tessellation policy spells it) may lie apart: each within one deflection of the surface
    they both describe, so within two of each other, over the diagonal of their union."""
    stacked = np.concatenate([mesh.reshape(-1, 3) for mesh in meshes if len(mesh)])
    diagonal = float(np.linalg.norm(stacked.max(axis=0) - stacked.min(axis=0)))
    return 2.0 * chord * diagonal
