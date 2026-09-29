"""Write an implicit :class:`~cadgen._internal.implicit.mesh.Mesh` as STL or GLB.

Two plain writers with no dependency beyond numpy, because the implicit path
never has a B-rep for the store's Node exporter to tessellate: its geometry
is already triangles.

The GLB is spec-conformant Y-up (the CAD Z-up positions are rotated on the
way out, and every node declares ``cadUpAxis: "y"`` so the viewer applies
the correction exactly once), with ONE NODE PER LEAF of the field. A leaf is
a primitive in the author's code; its node carries the leaf's label, its
source site and a colour, so picking a face in the viewer names the line
that made it. The STL is binary and flat-shaded, as STLs are.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

from cadgen._internal.implicit.mesh import Mesh

__all__ = ["write_stl", "write_glb", "leaf_color", "leaf_name"]

# A palette that reads on both light and dark viewer backgrounds, one colour per
# leaf in author order (wrapping after twelve).
_PALETTE = [
    (0.42, 0.60, 0.86),
    (0.93, 0.60, 0.29),
    (0.45, 0.76, 0.48),
    (0.86, 0.42, 0.45),
    (0.63, 0.53, 0.82),
    (0.55, 0.42, 0.33),
    (0.88, 0.55, 0.78),
    (0.55, 0.55, 0.55),
    (0.75, 0.75, 0.30),
    (0.30, 0.75, 0.80),
    (0.95, 0.75, 0.45),
    (0.50, 0.68, 0.70),
]


def leaf_color(index: int) -> tuple[float, float, float]:
    return _PALETTE[index % len(_PALETTE)]


def leaf_name(mesh: Mesh, index: int) -> str:
    """What a leaf's node is called: its label, else ``<kind>@<site>``, else ``<kind> <n>``."""
    leaf = mesh.leaves[index]
    if leaf.label:
        return leaf.label
    if leaf.site:
        return f"{leaf.kind}@{leaf.site}"
    return f"{leaf.kind} {index + 1}"


def write_stl(mesh: Mesh, out: Path, *, name: str = "implicit") -> Path:
    """Binary STL: one facet per triangle with its face normal."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    positions, normals = mesh.flat_shaded()
    count = len(mesh.triangles)
    record = np.zeros(count, dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
    record["n"] = normals.astype("<f4")
    record["v"] = positions.reshape(count, 3, 3).astype("<f4")
    header = f"cadgen implicit {name}".encode("ascii", "replace")[:80].ljust(80, b"\0")
    tmp = out.with_name(out.name + ".tmp")
    with open(tmp, "wb") as handle:
        handle.write(header)
        handle.write(struct.pack("<I", count))
        handle.write(record.tobytes())
    tmp.replace(out)
    return out


def _pad(data: bytes, boundary: int = 4, fill: bytes = b"\0") -> bytes:
    remainder = len(data) % boundary
    return data if remainder == 0 else data + fill * (boundary - remainder)


def write_glb(mesh: Mesh, out: Path, *, name: str = "implicit", units: str = "mm") -> Path:
    """glTF binary, Y-up, one node and primitive per leaf, positions welded per leaf."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    # CAD Z-up -> glTF Y-up: (x, y, z) -> (x, z, -y).
    to_gltf = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], dtype=np.float64)
    positions_all = (mesh.vertices @ to_gltf).astype("<f4")
    normals_all = (mesh.normals @ to_gltf).astype("<f4")

    binary = bytearray()
    buffer_views: list[dict] = []
    accessors: list[dict] = []
    materials: list[dict] = []
    meshes: list[dict] = []
    nodes: list[dict] = []

    def add_view(data: bytes, target: int) -> int:
        offset = len(binary)
        binary.extend(_pad(data))
        buffer_views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(data), "target": target})
        return len(buffer_views) - 1

    def add_accessor(view: int, component: int, count: int, kind: str, extrema: tuple | None = None) -> int:
        accessor = {"bufferView": view, "componentType": component, "count": count, "type": kind}
        if extrema is not None:
            accessor["min"], accessor["max"] = [list(map(float, e)) for e in extrema]
        accessors.append(accessor)
        return len(accessors) - 1

    leaf_ids = sorted(set(int(i) for i in mesh.triangle_leaf.tolist()))
    for index, leaf_id in enumerate(leaf_ids):
        tris = mesh.triangles[mesh.triangle_leaf == leaf_id]
        used, local = np.unique(tris.reshape(-1), return_inverse=True)
        local = local.reshape(-1, 3).astype("<u4")
        pos = positions_all[used]
        nrm = normals_all[used]
        pos_view = add_view(pos.tobytes(), 34962)
        nrm_view = add_view(nrm.tobytes(), 34962)
        idx_view = add_view(local.tobytes(), 34963)
        pos_acc = add_accessor(pos_view, 5126, len(pos), "VEC3", (pos.min(axis=0), pos.max(axis=0)))
        nrm_acc = add_accessor(nrm_view, 5126, len(nrm), "VEC3")
        idx_acc = add_accessor(idx_view, 5125, local.size, "SCALAR")
        color = leaf_color(leaf_id)
        materials.append(
            {
                "name": leaf_name(mesh, leaf_id),
                "pbrMetallicRoughness": {"baseColorFactor": [*color, 1.0], "metallicFactor": 0.0, "roughnessFactor": 0.6},
                "doubleSided": False,
            }
        )
        meshes.append(
            {
                "name": leaf_name(mesh, leaf_id),
                "primitives": [{"attributes": {"POSITION": pos_acc, "NORMAL": nrm_acc}, "indices": idx_acc, "material": index, "mode": 4}],
            }
        )
        leaf = mesh.leaves[leaf_id]
        nodes.append(
            {
                "name": leaf_name(mesh, leaf_id),
                "mesh": index,
                "extras": {
                    "cadOccurrenceId": f"implicit:{leaf_id}",
                    "cadSourceKind": "implicit",
                    "cadUnits": units,
                    "cadUpAxis": "y",
                    "implicitLeaf": leaf_id,
                    "implicitKind": leaf.kind,
                    "implicitLabel": leaf.label or "",
                    "implicitSite": leaf.site or "",
                    "implicitTriangles": int(len(tris)),
                },
            }
        )

    root = {
        "name": name,
        "children": list(range(len(nodes))),
        "extras": {"cadSourceKind": "implicit", "cadUnits": units, "cadUpAxis": "y", "implicitResolution": mesh.resolution},
    }
    nodes.append(root)
    document = {
        "asset": {"version": "2.0", "generator": "cadgen implicit"},
        "scene": 0,
        "scenes": [{"name": name, "nodes": [len(nodes) - 1]}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": materials,
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": len(binary)}],
    }
    json_chunk = _pad(json.dumps(document, separators=(",", ":")).encode("utf-8"), fill=b" ")
    bin_chunk = bytes(binary)
    total = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
    tmp = out.with_name(out.name + ".tmp")
    with open(tmp, "wb") as handle:
        handle.write(struct.pack("<4sII", b"glTF", 2, total))
        handle.write(struct.pack("<II", len(json_chunk), 0x4E4F534A))
        handle.write(json_chunk)
        handle.write(struct.pack("<II", len(bin_chunk), 0x004E4942))
        handle.write(bin_chunk)
    tmp.replace(out)
    return out
