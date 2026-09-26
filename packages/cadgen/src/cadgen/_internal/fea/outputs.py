"""The files a study writes: a vertex-coloured GLB, an optional VTU.

The GLB is what the viewer shows. Its ``COLOR_0`` is the von Mises ramp and
its positions are the deformed shape (displacement times a scale), so any
glTF viewer shows the result. The raw fields ride along for a viewer that
knows them: ``_VON_MISES`` (float, MPa) and ``_DISPLACEMENT`` (vec3, in glTF
units and axes -- metres, Y up -- unscaled), so the FEA overlay can recolour
by either field and change the deformation scale from the same file. The
mesh carries ``extras`` with the fields, the deformation scale and the ramp
stops -- a legend's inputs. Written by hand (glTF 2.0 is a JSON header and
one binary buffer) so the result path adds no dependency the solver did not
already need.

The VTU is the archival form for ParaView: linear tetrahedra with the
displacement vector and von Mises as point data.
"""

from __future__ import annotations

import io
import json
import struct
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

__all__ = ["RAMP", "auto_deformation_scale", "ramp", "write_glb", "write_vtu"]

#: Blue -> cyan -> green -> yellow -> red: the ramp every FEA post-processor
#: uses, so a reader's eye already knows which end is hot. Written into the
#: GLB's extras so a viewer recolouring by another field draws the same ramp.
RAMP = ((0.0, (0.05, 0.10, 0.90)), (0.25, (0.05, 0.85, 0.95)), (0.5, (0.10, 0.85, 0.15)),
        (0.75, (0.98, 0.90, 0.10)), (1.0, (0.90, 0.08, 0.05)))

# netgen's 6-node triangle lists the three corners, then the mid-edge nodes of
# edges (1,2) (0,2) (0,1), in that order.
_TRIG6_MID_OF_EDGE = {(1, 2): 3, (0, 2): 4, (0, 1): 5}


def ramp(t: "np.ndarray") -> "np.ndarray":
    """(n, 3) RGB in [0, 1] for values t in [0, 1]."""
    import numpy as np

    t = np.clip(np.asarray(t, dtype=float), 0.0, 1.0)
    stops = np.array([s for s, _ in RAMP])
    colours = np.array([c for _, c in RAMP])
    return np.stack([np.interp(t, stops, colours[:, channel]) for channel in range(3)], axis=1)


def auto_deformation_scale(max_displacement: float, bbox_diagonal: float) -> float:
    """A scale that shows the largest displacement as 5% of the part's diagonal,
    rounded to two significant figures; 1 when nothing moves."""
    if not max_displacement > 0:
        return 1.0
    raw = 0.05 * bbox_diagonal / max_displacement
    if raw <= 1.0:
        return 1.0
    magnitude = 10 ** int(f"{raw:e}".split("e")[1])
    return float(round(raw / magnitude, 1) * magnitude)


def _gltf_space(points_mm: "np.ndarray") -> "np.ndarray":
    """CAD (x, y, z) mm -> glTF (x, z, -y) metres: the convention cadgen's own
    GLB export uses, so the part shows upright at its true size everywhere."""
    import numpy as np

    out = np.empty_like(points_mm, dtype=np.float32)
    out[:, 0] = points_mm[:, 0] / 1000.0
    out[:, 1] = points_mm[:, 2] / 1000.0
    out[:, 2] = -points_mm[:, 1] / 1000.0
    return out


def _vertex_normals(positions: "np.ndarray", triangles: "np.ndarray") -> "np.ndarray":
    import numpy as np

    a = positions[triangles[:, 1]] - positions[triangles[:, 0]]
    b = positions[triangles[:, 2]] - positions[triangles[:, 0]]
    face = np.cross(a, b)
    normals = np.zeros_like(positions)
    for corner in range(3):
        np.add.at(normals, triangles[:, corner], face)
    length = np.linalg.norm(normals, axis=1, keepdims=True)
    length[length == 0] = 1.0
    return normals / length


def _split_quadratic(triangles6: "np.ndarray") -> "np.ndarray":
    """Four linear triangles per six-node triangle, so the mid-edge values show;
    the sub-triangles keep the parent's winding."""
    import numpy as np

    c0, c1, c2 = triangles6[:, 0], triangles6[:, 1], triangles6[:, 2]
    m01 = triangles6[:, _TRIG6_MID_OF_EDGE[(0, 1)]]
    m12 = triangles6[:, _TRIG6_MID_OF_EDGE[(1, 2)]]
    m20 = triangles6[:, _TRIG6_MID_OF_EDGE[(0, 2)]]
    return np.vstack([
        np.column_stack([c0, m01, m20]),
        np.column_stack([m01, c1, m12]),
        np.column_stack([m20, m12, c2]),
        np.column_stack([m01, m12, m20]),
    ])


def _signed_volume(positions: "np.ndarray", triangles: "np.ndarray") -> float:
    import numpy as np

    a, b, c = positions[triangles[:, 0]], positions[triangles[:, 1]], positions[triangles[:, 2]]
    return float((np.cross(a, b) * c).sum() / 6.0)


def write_glb(
    path: Path,
    *,
    positions: "np.ndarray",
    displacement: "np.ndarray",
    values: "np.ndarray",
    triangles6: "np.ndarray",
    scale: float,
    value_range: tuple[float, float],
    extras: dict,
) -> None:
    """A binary glTF of the deformed boundary surface with the value ramp as vertex colour.

    ``positions``, ``displacement`` and ``values`` are per node (corner and
    mid-edge alike); ``triangles6`` are the mesher's boundary triangles in
    those node ids, wound consistently, which is kept -- flipped as a whole
    only when the surface encloses negative volume.
    """
    import numpy as np

    triangles = _split_quadratic(triangles6)
    if _signed_volume(positions, triangles) < 0:
        triangles = triangles[:, [0, 2, 1]]
    used, compact = np.unique(triangles, return_inverse=True)
    tris = compact.reshape(triangles.shape).astype(np.uint32)
    pos = _gltf_space(positions[used] + scale * displacement[used])
    vals = values[used].astype(np.float32)
    disp = _gltf_space(displacement[used])
    lo, hi = value_range
    t = (vals - lo) / (hi - lo) if hi > lo else np.zeros_like(vals)
    rgba = np.hstack([(ramp(t) * 255).round().astype(np.uint8), np.full((len(used), 1), 255, np.uint8)])
    normals = _vertex_normals(pos.astype(float), tris).astype(np.float32)

    blobs: list[bytes] = []
    views: list[dict] = []
    accessors: list[dict] = []

    def add(array: "np.ndarray", *, target: int, kind: str, component: int, normalized: bool = False, bounds: bool = False) -> int:
        data = np.ascontiguousarray(array).tobytes()
        offset = sum(len(b) for b in blobs)
        blobs.append(data + b"\0" * (-len(data) % 4))
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(data), "target": target})
        accessor = {"bufferView": len(views) - 1, "componentType": component, "count": int(array.shape[0]), "type": kind}
        if normalized:
            accessor["normalized"] = True
        if bounds:
            accessor["min"] = [float(x) for x in array.min(axis=0)]
            accessor["max"] = [float(x) for x in array.max(axis=0)]
        accessors.append(accessor)
        return len(accessors) - 1

    ARRAY, ELEMENT = 34962, 34963
    FLOAT, UBYTE, UINT = 5126, 5121, 5125
    name = extras.get("name", "fea result")
    gltf = {
        "asset": {"version": "2.0", "generator": "cadgen fea"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": name}],
        "meshes": [{
            "name": name,
            "extras": extras,
            "primitives": [{
                "attributes": {
                    "POSITION": add(pos, target=ARRAY, kind="VEC3", component=FLOAT, bounds=True),
                    "NORMAL": add(normals, target=ARRAY, kind="VEC3", component=FLOAT),
                    "COLOR_0": add(rgba, target=ARRAY, kind="VEC4", component=UBYTE, normalized=True),
                    "_VON_MISES": add(vals.reshape(-1, 1), target=ARRAY, kind="SCALAR", component=FLOAT),
                    "_DISPLACEMENT": add(disp, target=ARRAY, kind="VEC3", component=FLOAT),
                },
                "indices": add(tris.reshape(-1, 1), target=ELEMENT, kind="SCALAR", component=UINT),
                "material": 0,
                "mode": 4,
            }],
        }],
        "materials": [{
            "name": "fea ramp",
            "doubleSided": True,
            "pbrMetallicRoughness": {"baseColorFactor": [1.0, 1.0, 1.0, 1.0], "metallicFactor": 0.0, "roughnessFactor": 0.85},
        }],
        "buffers": [{"byteLength": sum(len(b) for b in blobs)}],
        "bufferViews": views,
        "accessors": accessors,
    }
    header = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    header += b" " * (-len(header) % 4)
    binary = b"".join(blobs)
    total = 12 + 8 + len(header) + 8 + len(binary)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(struct.pack("<4sII", b"glTF", 2, total))
        handle.write(struct.pack("<II", len(header), 0x4E4F534A))
        handle.write(header)
        handle.write(struct.pack("<II", len(binary), 0x004E4942))
        handle.write(binary)


def write_vtu(
    path: Path,
    *,
    positions: "np.ndarray",
    tets: "np.ndarray",
    displacement: "np.ndarray",
    values: "np.ndarray",
) -> None:
    """An ASCII VTK unstructured grid of linear tetrahedra with point data."""
    import numpy as np

    def rows(array: "np.ndarray", fmt: str) -> str:
        buffer = io.StringIO()
        np.savetxt(buffer, array, fmt=fmt)
        return buffer.getvalue().rstrip("\n")

    n_points, n_cells = len(positions), len(tets)
    text = f"""<?xml version="1.0"?>
<VTKFile type="UnstructuredGrid" version="0.1" byte_order="LittleEndian">
<UnstructuredGrid>
<Piece NumberOfPoints="{n_points}" NumberOfCells="{n_cells}">
<Points><DataArray type="Float64" NumberOfComponents="3" format="ascii">
{rows(positions, "%.7g")}
</DataArray></Points>
<Cells>
<DataArray type="Int64" Name="connectivity" format="ascii">
{rows(tets, "%d")}
</DataArray>
<DataArray type="Int64" Name="offsets" format="ascii">
{rows(np.arange(4, 4 * n_cells + 1, 4), "%d")}
</DataArray>
<DataArray type="UInt8" Name="types" format="ascii">
{" ".join(["10"] * n_cells)}
</DataArray>
</Cells>
<PointData Scalars="von_mises" Vectors="displacement">
<DataArray type="Float64" Name="von_mises" format="ascii">
{rows(values, "%.7g")}
</DataArray>
<DataArray type="Float64" Name="displacement" NumberOfComponents="3" format="ascii">
{rows(displacement, "%.7g")}
</DataArray>
</PointData>
</Piece>
</UnstructuredGrid>
</VTKFile>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
