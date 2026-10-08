"""A document's stored meshes, placed and coloured, as STL, 3MF or GLB bytes.

The writer half of the one mesh path (``mesh_export.run_mesh_exporter`` is the
engine around it). Its input is what the store already holds: one GLB body per
component (``cadgen.store.meshes``), OCCT's mesh of the component's exact BREP --
the triangles the CAD Viewer and snapshots draw -- and the flattened descriptor
whose occurrences place each component in the document. Nothing here meshes,
reads the store or imports the kernel.

- :func:`build_primitives` bakes every occurrence's ABSOLUTE transform into its
  copy of the component (mirroring-safe: a reflection flips the winding, and the
  inverse-transpose carries the normals) and groups the triangles by resolved
  colour and finish. The colour of a face is the first of: its own intrinsic
  colour, the occurrence's (a named material's ``baseColor``, then its STEP
  colour), the component's, the part's, the export default.
- :func:`stl_bytes` is binary STL, colourless by format, without the triangles
  that cover nothing (as the 3MF weld drops them).
- :func:`threemf_bytes` is one ``basematerials`` group with one object per
  primitive, its vertices shared by exact position (what a slicer welds on).
- :func:`glb_bytes` is glTF 2.0, Y-up metres: one node per primitive for a static
  file, one node per OCCURRENCE when a clip animates it (a channel needs a node
  to target), with the occurrence ids, the declared up axis and the authored PBR
  finish carried through. A clip's moving parts hang under PIVOT nodes, and a
  bending tube's primitives carry JOINTS_0/WEIGHTS_0 for its SKIN (``tube_skin``).

Determinism (README law 5): the same meshes and descriptor give the same bytes.
Every value written is IEEE arithmetic in a fixed order -- elementwise numpy
operations, never a BLAS product or a float reduction -- and every collection is
emitted in a sorted or declared order.
"""

from __future__ import annotations

import dataclasses
import json
import math
import re
import struct
import zlib
from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np

# Authored sRGB, the colour of a face nothing else colours.
DEFAULT_COLOR = "#d4d4d8"
# glTF is Y-up metres; a document is Z-up millimetres: (x, y, z) -> (x, z, -y) is
# a proper rotation (winding and outwardness untouched), and mm -> m applies to
# positions and translations only.
CAD_TO_GLB_SCALE = 0.001
# The per-occurrence PBR finish a descriptor may carry (``source_sidecar.apply_appearance``),
# in the order the grouping key serializes it.
MATERIAL_CHANNELS = ("roughness", "metalness", "clearcoat", "clearcoatRoughness", "opacity")
# The finish of a source that authored none.
DEFAULT_ROUGHNESS = 0.42
DEFAULT_METALNESS = 0.03
# A primitive with at most this many vertices indexes in UNSIGNED_SHORT.
UNSIGNED_SHORT_VERTEX_LIMIT = 65535

_HEX = re.compile(r"#[0-9a-fA-F]{6}")
_UNSAFE_NAME = re.compile(r'[\x00-\x1f<>:"/\\|?*]+')
_FLOAT, _UNSIGNED_SHORT, _UNSIGNED_INT = 5126, 5123, 5125
_ARRAY_BUFFER, _ELEMENT_ARRAY_BUFFER = 34962, 34963
_TRIANGLES = 4


@dataclass(frozen=True)
class Tessellation:
    """One component's stored mesh, unlocated, in the document's units."""

    positions: np.ndarray  # (n, 3) float32
    normals: np.ndarray  # (n, 3) float32
    indices: np.ndarray  # (m,) uint32, m % 3 == 0
    face_ranges: list
    part_color: list | None = None


def decode_tessellation(payload: bytes) -> Tessellation:
    """The arrays of one stored mesh, a GLB body (``cadgen.store.meshes.encode_payload``),
    viewed in place but for its indices, widened to uint32."""
    from cadgen.store.meshes import decode_payload

    decoded = decode_payload(payload)
    return Tessellation(
        positions=decoded.positions, normals=decoded.normals, indices=decoded.indices.astype(np.uint32),
        face_ranges=decoded.face_ranges(), part_color=decoded.cad["partColor"],
    )


@dataclass
class Primitive:
    """Indexed, coloured triangles placed in the document's world (CAD millimetres)."""

    color: str  # "#rrggbb", sRGB
    positions: np.ndarray  # (v, 3) float32
    normals: np.ndarray  # (v, 3) float32, unit
    indices: np.ndarray  # (t * 3,) uint32
    node: str | None = None  # the occurrence this primitive belongs to, per-occurrence only
    name: str | None = None
    occurrence_id: str | None = None
    opacity: float | None = None  # a caller's override (a clip's opacity at its start)
    material: dict | None = None  # the authored finish, channels in [0, 1]
    material_id: str = ""
    material_name: str = ""
    # A bending tube's skin binding (glb only): JOINTS_0 and WEIGHTS_0, and which of
    # the file's skins its node uses.
    joints: np.ndarray | None = None  # (v, 4) uint16
    weights: np.ndarray | None = None  # (v, 4) float32
    skin: int | None = None

    @property
    def triangle_count(self) -> int:
        return len(self.indices) // 3


# --- colour ---------------------------------------------------------------------


def _finite(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def _linear_channel_to_srgb_byte(channel: object) -> int:
    value = _finite(channel)
    clamped = _clamp01(0.0 if value is None else value)
    srgb = clamped * 12.92 if clamped <= 0.0031308 else 1.055 * clamped ** (1 / 2.4) - 0.055
    # Half up, like every hex this pipeline has ever written for a linear colour.
    return int(math.floor(_clamp01(srgb) * 255 + 0.5))


def linear_rgb_to_hex(rgb: object) -> str | None:
    """LINEAR RGB(A) floats -> sRGB ``#rrggbb``; alpha rides separately. None
    unless at least three channels."""
    if not isinstance(rgb, (list, tuple)) or len(rgb) < 3:
        return None
    return "#" + "".join(f"{_linear_channel_to_srgb_byte(channel):02x}" for channel in rgb[:3])


def _srgb_to_linear(component: float) -> float:
    return component / 12.92 if component <= 0.04045 else ((component + 0.055) / 1.055) ** 2.4


def _float32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def _hex_rgb01(color: str) -> tuple[float, float, float]:
    value = color if _HEX.fullmatch(str(color or "")) else DEFAULT_COLOR
    return tuple(int(value[index:index + 2], 16) / 255 for index in (1, 3, 5))  # type: ignore[return-value]


def sanitize_name(value: object, fallback: str = "model") -> str:
    return _UNSAFE_NAME.sub("-", str(value or fallback).strip()) or fallback


def occurrence_finish(material: object, color: object) -> dict | None:
    """The occurrence's authored finish, each channel clamped to [0, 1], with its
    STEP alpha folded into ``opacity`` (the two multiply, as the viewport composes
    them). None when nothing is authored, so an unauthored source groups -- and
    writes -- exactly as a plain one."""
    finish: dict[str, float] = {}
    if isinstance(material, Mapping):
        for channel in MATERIAL_CHANNELS:
            value = _finite(material.get(channel))
            if value is not None:
                finish[channel] = _clamp01(value)
    alpha = _finite(color[3]) if isinstance(color, (list, tuple)) and len(color) >= 4 else None
    source_alpha = 1.0 if alpha is None else _clamp01(alpha)
    if source_alpha < 0.999:
        finish["opacity"] = source_alpha * finish.get("opacity", 1.0)
    return finish or None


def _finish_key(finish: dict | None, material_id: str) -> str:
    # Colour alone would merge a brushed and a polished body of one colour into one
    # material, and distinct named materials stay apart even when their channels match.
    key = "" if finish is None else "|" + ",".join(
        repr(finish[channel]) if channel in finish else "" for channel in MATERIAL_CHANNELS)
    return key + (f"|material:{material_id}" if material_id else "")


# --- placement ------------------------------------------------------------------


_IDENTITY_12 = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0)


@dataclass(frozen=True)
class _Placement:
    matrix: tuple | None  # row-major 3x4, None for the identity
    mirrored: bool = False
    normal_matrix: tuple | None = None  # inverse-transpose of the 3x3, row-major


def _placement(transform: object) -> _Placement:
    if not isinstance(transform, (list, tuple)) or len(transform) < 12:
        return _Placement(None)
    m = tuple(float(value) for value in transform[:12])
    if m == _IDENTITY_12:
        return _Placement(None)
    a, b, c, d, e, f, g, h, i = m[0], m[1], m[2], m[4], m[5], m[6], m[8], m[9], m[10]
    big_a, big_b, big_c = e * i - f * h, f * g - d * i, d * h - e * g
    det = a * big_a + b * big_b + c * big_c
    normal = None
    if math.isfinite(det) and abs(det) >= 1e-30:
        inv = 1.0 / det
        # The TRUE inverse-transpose (divided by the determinant), so a reflected
        # surface's outward normal maps outward with no extra negation; only the
        # winding needs the flip.
        normal = (
            big_a * inv, big_b * inv, big_c * inv,
            (c * h - b * i) * inv, (a * i - c * g) * inv, (b * g - a * h) * inv,
            (b * f - c * e) * inv, (c * d - a * f) * inv, (a * e - b * d) * inv,
        )
    return _Placement(m, det < 0, normal)


def _place(positions: np.ndarray, normals: np.ndarray, placement: _Placement) -> tuple[np.ndarray, np.ndarray]:
    """Placed float32 positions and unit normals, computed in float64 in a fixed order."""
    p = positions.astype(np.float64)
    n = normals.astype(np.float64)
    m = placement.matrix
    if m is not None:
        x, y, z = p[:, 0], p[:, 1], p[:, 2]
        p = np.stack([m[0] * x + m[1] * y + m[2] * z + m[3],
                      m[4] * x + m[5] * y + m[6] * z + m[7],
                      m[8] * x + m[9] * y + m[10] * z + m[11]], axis=1)
    k = placement.normal_matrix
    if k is not None:
        x, y, z = n[:, 0], n[:, 1], n[:, 2]
        n = np.stack([k[0] * x + k[1] * y + k[2] * z,
                      k[3] * x + k[4] * y + k[5] * z,
                      k[6] * x + k[7] * y + k[8] * z], axis=1)
    length = np.sqrt(n[:, 0] * n[:, 0] + n[:, 1] * n[:, 1] + n[:, 2] * n[:, 2])
    length = np.where(length > 0, length, 1.0)
    return p.astype(np.float32), (n / length[:, None]).astype(np.float32)


def occurrence_colors(
    descriptor: Mapping[str, Any], occurrence: Mapping[str, Any], tessellation: Tessellation,
    default_color: str | None = None,
) -> list[str]:
    """Every face range of one occurrence resolved to its export colour: its own,
    else the occurrence's (a named material's ``baseColor``, then its STEP colour),
    the component's, the part's, the export default. The one chain, for the soup
    and for a morph bake that replaces an occurrence's primitives alike."""
    cid = str(occurrence.get("component") or "")
    base_color = str(occurrence.get("baseColor") or "")
    occurrence_color = base_color.lower() if _HEX.fullmatch(base_color) else linear_rgb_to_hex(occurrence.get("color"))
    component_color = linear_rgb_to_hex(((descriptor.get("components") or {}).get(cid) or {}).get("color"))
    fallback = (occurrence_color or component_color or linear_rgb_to_hex(tessellation.part_color)
                or (default_color or DEFAULT_COLOR).lower())
    return [linear_rgb_to_hex(face_range.get("color")) or fallback for face_range in tessellation.face_ranges]


def occurrence_world_mesh(
    occurrence: Mapping[str, Any], tessellation: Tessellation,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """One occurrence's whole component, placed: (positions, normals, triangles,
    the face range of each triangle), the triangles in face-range order and
    re-wound under a reflection exactly as the soup places them."""
    placement = _placement(occurrence.get("transform"))
    positions, normals = _place(tessellation.positions, tessellation.normals, placement)
    triangles, ranges = [], []
    for range_index, face_range in enumerate(tessellation.face_ranges):
        start, count = int(face_range.get("indexStart") or 0), int(face_range.get("indexCount") or 0)
        block = tessellation.indices[start:start + count // 3 * 3].reshape(-1, 3)
        triangles.append(block[:, [0, 2, 1]] if placement.mirrored else block)
        ranges.append(np.full(len(block), range_index, dtype=np.int64))
    if not triangles:
        return positions, normals, np.zeros((0, 3), dtype=np.uint32), np.zeros(0, dtype=np.int64)
    return positions, normals, np.concatenate(triangles).astype(np.uint32), np.concatenate(ranges)


@dataclass
class _Group:
    color: str
    material: dict | None
    material_id: str
    material_name: str
    node: str | None
    name: str | None
    occurrence_id: str | None
    opacity: float | None
    members: list = field(default_factory=list)  # (component id, range index, placement)


def build_primitives(
    descriptor: Mapping[str, Any],
    tessellations: Mapping[str, Tessellation],
    *,
    default_color: str | None = None,
    per_occurrence: bool = False,
    hidden: frozenset[str] | set[str] = frozenset(),
    opacity: Mapping[str, float] | None = None,
    overrides: Mapping[str, list[Primitive]] | None = None,
) -> list[Primitive]:
    """The descriptor's occurrences, baked into colour-grouped primitives.

    The flat layout groups every face of one colour and finish across the whole
    document into one primitive. ``per_occurrence`` keys each group by its
    occurrence as well, so a GLB node is an occurrence a clip can move; it costs
    sharing across occurrences, so only an animated export asks for it. ``hidden``
    occurrences are left out and ``opacity`` overrides an occurrence's alpha --
    the effects a clip's ``drop`` bakes at its start. ``overrides`` (per
    occurrence only) are primitives somebody else built for an occurrence -- a
    morph bake's refined, posed tube -- spliced in where its own would sort.
    """
    if default_color is not None and not _HEX.fullmatch(default_color):
        raise ValueError(f"the default export colour must be #rrggbb, got {default_color!r}")
    if overrides and not per_occurrence:
        raise ValueError("primitive overrides are keyed by occurrence, and the flat layout has none")
    groups: dict[str, _Group] = {}
    spliced: dict[str, Primitive] = {}
    for occurrence_index, occurrence in enumerate(descriptor.get("occurrences") or []):
        cid = str(occurrence.get("component") or "")
        tessellation = tessellations.get(cid)
        if tessellation is None:
            continue
        occurrence_id = str(occurrence.get("id") or cid)
        if occurrence_id in hidden:
            continue
        finish = occurrence_finish(occurrence.get("material"), occurrence.get("color"))
        material_id = str(occurrence.get("materialId") or "").strip()
        material_name = str(occurrence.get("materialName") or material_id).strip()
        finish_key = _finish_key(finish, material_id)
        placement = _placement(occurrence.get("transform"))
        name = str(occurrence.get("name") or occurrence_id)
        override = (overrides or {}).get(occurrence_id)
        if override is not None:
            for ordinal, primitive in enumerate(override):
                key = f"{occurrence_index:08d}|{primitive.color}{finish_key}|{ordinal:04d}"
                spliced[key] = dataclasses.replace(
                    primitive, node=occurrence_id, name=name, occurrence_id=occurrence_id,
                    opacity=None if opacity is None else opacity.get(occurrence_id), material=finish,
                    material_id=material_id, material_name=material_name,
                )
            continue
        colors = occurrence_colors(descriptor, occurrence, tessellation, default_color)
        for range_index, face_range in enumerate(tessellation.face_ranges):
            if int(face_range.get("indexCount") or 0) < 3:
                continue
            color = colors[range_index]
            key = (f"{occurrence_index:08d}|{color}" if per_occurrence else color) + finish_key
            group = groups.get(key)
            if group is None:
                group = groups[key] = _Group(
                    color=color, material=finish, material_id=material_id, material_name=material_name,
                    node=occurrence_id if per_occurrence else None, name=name if per_occurrence else None,
                    occurrence_id=occurrence_id if per_occurrence else None,
                    opacity=None if opacity is None else opacity.get(occurrence_id),
                )
            group.members.append((cid, range_index, placement))

    face_vertices: dict[tuple[str, int], tuple[np.ndarray, np.ndarray]] = {}

    def vertices_of(cid: str, range_index: int) -> tuple[np.ndarray, np.ndarray]:
        """A face range's own vertices (sorted ids) and its triangles over them."""
        cached = face_vertices.get((cid, range_index))
        if cached is None:
            tessellation = tessellations[cid]
            face_range = tessellation.face_ranges[range_index]
            start, count = int(face_range["indexStart"]), int(face_range["indexCount"])
            used, local = np.unique(tessellation.indices[start:start + count], return_inverse=True)
            cached = face_vertices[(cid, range_index)] = (used, local.astype(np.uint32).reshape(-1, 3))
        return cached

    primitives: list[Primitive] = []
    for key in sorted([*groups, *spliced]):
        if key in spliced:
            primitives.append(spliced[key])
            continue
        group = groups[key]
        positions, normals, indices = [], [], []
        base = 0
        for cid, range_index, placement in group.members:
            used, triangles = vertices_of(cid, range_index)
            tessellation = tessellations[cid]
            placed, turned = _place(tessellation.positions[used], tessellation.normals[used], placement)
            if placement.mirrored:
                triangles = triangles[:, [0, 2, 1]]  # keeps recomputed facet normals outward
            positions.append(placed)
            normals.append(turned)
            indices.append((triangles + np.uint32(base)).reshape(-1))
            base += len(placed)
        if not base:
            continue
        primitives.append(Primitive(
            color=group.color, positions=np.concatenate(positions), normals=np.concatenate(normals),
            indices=np.concatenate(indices).astype(np.uint32), node=group.node, name=group.name,
            occurrence_id=group.occurrence_id, opacity=group.opacity, material=group.material,
            material_id=group.material_id, material_name=group.material_name,
        ))
    return [primitive for primitive in primitives if primitive.triangle_count]


def total_triangles(primitives: list[Primitive]) -> int:
    return sum(primitive.triangle_count for primitive in primitives)


# --- STL ------------------------------------------------------------------------

_STL_RECORD = np.dtype([("normal", "<f4", (3,)), ("corners", "<f4", (9,)), ("attribute", "<u2")])


def _facet_normals(corners: np.ndarray) -> np.ndarray:
    """Each triangle's unit normal from its float32 corners, (0, 0, 1) for a sliver."""
    c = corners.astype(np.float64)
    ux, uy, uz = c[:, 3] - c[:, 0], c[:, 4] - c[:, 1], c[:, 5] - c[:, 2]
    vx, vy, vz = c[:, 6] - c[:, 0], c[:, 7] - c[:, 1], c[:, 8] - c[:, 2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    length = np.sqrt(nx * nx + ny * ny + nz * nz)
    degenerate = ~(length > 1e-12)
    safe = np.where(degenerate, 1.0, length)
    normals = np.stack([nx / safe, ny / safe, nz / safe], axis=1)
    normals[degenerate] = (0.0, 0.0, 1.0)
    return normals.astype(np.float32)


def stl_bytes(primitives: list[Primitive], *, name: str = "model") -> bytes:
    """Binary STL: an 80-byte header naming the model, then every triangle that covers
    something."""
    corners = np.concatenate(
        [primitive.positions[primitive.indices].reshape(-1, 9) for primitive in primitives]
        or [np.zeros((0, 9), np.float32)]
    )
    # A triangle two of whose corners are one point (OCCT's mesh has them at a
    # sphere's pole, a cone's apex) covers nothing and still carries its edges,
    # which a slicer welding by position then counts four times. Left out, as the
    # 3MF weld leaves it out; == holds -0.0 and 0.0 one point, as that weld does.
    a, b, c = corners[:, 0:3], corners[:, 3:6], corners[:, 6:9]
    corners = corners[~((a == b).all(axis=1) | (b == c).all(axis=1) | (c == a).all(axis=1))]
    records = np.zeros(len(corners), dtype=_STL_RECORD)
    records["normal"] = _facet_normals(corners)
    records["corners"] = corners
    header = bytes(ord(character) & 0x7F for character in f"cad {sanitize_name(name)}"[:80])
    return header.ljust(80, b"\0") + struct.pack("<I", len(corners)) + records.tobytes()


# --- 3MF ------------------------------------------------------------------------


def xml_escape(value: object) -> str:
    return (str(value if value is not None else "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _welded(primitive: Primitive) -> tuple[np.ndarray, np.ndarray]:
    """The primitive's corners shared by EXACT position, numbered in first-seen
    order, with triangles that collapse onto a repeated vertex dropped."""
    # +0.0 makes -0.0 the same vertex as 0.0.
    corners = np.ascontiguousarray(primitive.positions[primitive.indices] + np.float32(0.0))
    if not len(corners):
        return np.zeros((0, 3), np.float32), np.zeros((0, 3), np.int64)
    keys = corners.view(np.dtype((np.void, corners.dtype.itemsize * 3))).reshape(-1)
    _unique, first, inverse = np.unique(keys, return_index=True, return_inverse=True)
    order = np.argsort(first, kind="stable")
    rank = np.empty_like(order)
    rank[order] = np.arange(len(order))
    triangles = rank[inverse.reshape(-1)].reshape(-1, 3)
    keep = ((triangles[:, 0] != triangles[:, 1]) & (triangles[:, 1] != triangles[:, 2])
            & (triangles[:, 2] != triangles[:, 0]))
    return corners[first[order]], triangles[keep]


def _zip_stored(files: list[tuple[str, bytes]]) -> bytes:
    """A STORED zip with the DOS epoch as every timestamp, so the same content is
    the same archive from any producer at any time."""
    dos_time, dos_date = 0, (1 << 5) | 1
    local_parts, central_parts = [], []
    offset = 0
    for name, body in files:
        encoded = name.encode("utf-8")
        crc = zlib.crc32(body) & 0xFFFFFFFF
        local = struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, 0, 0, dos_time, dos_date,
                            crc, len(body), len(body), len(encoded), 0)
        local_parts += [local, encoded, body]
        central_parts += [struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20, 0, 0, dos_time, dos_date,
                                      crc, len(body), len(body), len(encoded), 0, 0, 0, 0, 0, offset), encoded]
        offset += len(local) + len(encoded) + len(body)
    central = b"".join(central_parts)
    end = struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, len(files), len(files), len(central), offset, 0)
    return b"".join(local_parts) + central + end


def threemf_bytes(primitives: list[Primitive], *, name: str = "model") -> bytes:
    """A 3MF package: one ``basematerials`` group, one object per primitive
    referencing its colour, every object a build item."""
    materials = "\n".join(
        f'      <base name="material-{index}" displaycolor="{xml_escape(primitive.color.upper())}FF"/>'
        for index, primitive in enumerate(primitives)
    )
    objects, items = [], []
    for index, primitive in enumerate(primitives):
        vertices, triangles = _welded(primitive)
        # Nine significant digits are every float32 exactly.
        vertex_lines = "\n".join(
            f'        <vertex x="{x:.9g}" y="{y:.9g}" z="{z:.9g}"/>' for x, y, z in vertices.tolist())
        triangle_lines = "\n".join(
            f'        <triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in triangles.tolist())
        object_id = index + 2  # 1 is the materials group
        objects.append(
            f'    <object id="{object_id}" type="model" pid="1" pindex="{index}">\n'
            "      <mesh>\n"
            f"        <vertices>\n{vertex_lines}\n        </vertices>\n"
            f"        <triangles>\n{triangle_lines}\n        </triangles>\n"
            "      </mesh>\n"
            "    </object>"
        )
        items.append(f'    <item objectid="{object_id}"/>')
    model = "".join([
        '<?xml version="1.0" encoding="UTF-8"?>\n',
        '<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" ',
        'xmlns:m="http://schemas.microsoft.com/3dmanufacturing/material/2015/02">\n',
        f'  <metadata name="Title">{xml_escape(name)}</metadata>\n',
        "  <resources>\n",
        f'    <basematerials id="1">\n{materials}\n    </basematerials>\n',
        "\n".join(objects), "\n",
        "  </resources>\n",
        "  <build>\n", "\n".join(items), "\n  </build>\n",
        "</model>\n",
    ])
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
        '  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
        "</Types>\n"
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '  <Relationship Target="/3D/3dmodel.model" Id="rel-1" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
        "</Relationships>\n"
    )
    return _zip_stored([
        ("[Content_Types].xml", content_types.encode("utf-8")),
        ("_rels/.rels", relationships.encode("utf-8")),
        ("3D/3dmodel.model", model.encode("utf-8")),
    ])


# --- GLB ------------------------------------------------------------------------


def _y_up(values: np.ndarray, scale: float) -> np.ndarray:
    """(x, y, z) -> (x, z, -y), times ``scale``, back to float32."""
    v = values.astype(np.float64)
    return np.stack([v[:, 0] * scale, v[:, 2] * scale, -(v[:, 1] * scale)], axis=1).astype(np.float32)


def _gltf_material(primitive: Primitive) -> dict:
    # sRGB in, LINEAR out (baseColorFactor is linear), canonicalized to float32 so
    # the bytes do not hang on the last bit of a pow.
    rgb = [_float32(_srgb_to_linear(_clamp01(channel))) for channel in _hex_rgb01(primitive.color)]
    finish = primitive.material or {}
    # A caller's opacity (a clip's faded occurrence) wins over the authored one.
    alpha = (finish.get("opacity", 1.0) if primitive.opacity is None
             else _clamp01(float(primitive.opacity)))
    material: dict[str, Any] = {
        "name": sanitize_name(primitive.material_name or primitive.name or "material", "material"),
        "doubleSided": True,
        "extras": {"cadSourceColor": True},
        "pbrMetallicRoughness": {
            "baseColorFactor": [*rgb, alpha],
            "roughnessFactor": finish.get("roughness", DEFAULT_ROUGHNESS),
            "metallicFactor": finish.get("metalness", DEFAULT_METALNESS),
        },
    }
    if alpha < 1:
        # Importers ignore baseColorFactor's alpha in the default OPAQUE mode.
        material["alphaMode"] = "BLEND"
    clearcoat = finish.get("clearcoat")
    if clearcoat is not None and clearcoat > 0:
        coat: dict[str, float] = {"clearcoatFactor": clearcoat}
        if "clearcoatRoughness" in finish:
            coat["clearcoatRoughnessFactor"] = finish["clearcoatRoughness"]
        material["extensions"] = {"KHR_materials_clearcoat": coat}
    return material


def glb_bytes(primitives: list[Primitive], *, name: str = "model", animation: Any = None) -> bytes:
    """glTF 2.0 binary, Y-up metres, uncompressed and unquantized (what slicers and
    stock importers read).

    ``animation`` is a clip in glTF's terms (``glb_animation.GltfClip``), whose pivots
    and skins name the primitives' ``node`` keys. A pivot is two nodes -- one at
    ``pivot + d`` turned by ``q``, over one at ``-pivot`` that carries the pivot's
    occurrence nodes -- and a skin is a joint node per joint, under the pivot that
    also moves its tube or at the scene's root. Every node's own transform is its pose
    at the clip's first moment: what the file shows when nothing plays it.
    """
    binary: list[bytes] = []
    size = 0
    buffer_views: list[dict] = []
    accessors: list[dict] = []

    def view(payload: bytes, target: int | None = None) -> int:
        nonlocal size
        padding = -size % 4
        if padding:
            binary.append(b"\0" * padding)
            size += padding
        entry: dict[str, int] = {"buffer": 0, "byteOffset": size, "byteLength": len(payload)}
        if target is not None:
            entry["target"] = target
        binary.append(payload)
        size += len(payload)
        buffer_views.append(entry)
        return len(buffer_views) - 1

    def accessor(entry: dict) -> int:
        accessors.append(entry)
        return len(accessors) - 1

    materials: list[dict] = []
    groups: dict[str, dict] = {}
    for primitive in primitives:
        positions = _y_up(primitive.positions, CAD_TO_GLB_SCALE)
        normals = _y_up(primitive.normals, 1.0)
        count = len(positions)
        index_dtype, index_type = ("<u2", _UNSIGNED_SHORT) if count <= UNSIGNED_SHORT_VERTEX_LIMIT else ("<u4", _UNSIGNED_INT)
        index_bytes = primitive.indices.astype(index_dtype).tobytes()
        position_view = view(positions.astype("<f4").tobytes(), _ARRAY_BUFFER)
        normal_view = view(normals.astype("<f4").tobytes(), _ARRAY_BUFFER)
        index_view = view(index_bytes + b"\0" * (-len(index_bytes) % 4), _ELEMENT_ARRAY_BUFFER)
        attributes = {
            "POSITION": accessor({
                "bufferView": position_view, "byteOffset": 0, "componentType": _FLOAT, "count": count,
                "type": "VEC3", "min": [float(value) for value in positions.min(axis=0)],
                "max": [float(value) for value in positions.max(axis=0)],
            }),
            "NORMAL": accessor({
                "bufferView": normal_view, "byteOffset": 0, "componentType": _FLOAT, "count": count, "type": "VEC3",
            }),
        }
        if primitive.joints is not None:
            attributes["JOINTS_0"] = accessor({
                "bufferView": view(primitive.joints.astype("<u2").tobytes(), _ARRAY_BUFFER), "byteOffset": 0,
                "componentType": _UNSIGNED_SHORT, "count": count, "type": "VEC4",
            })
            attributes["WEIGHTS_0"] = accessor({
                "bufferView": view(primitive.weights.astype("<f4").tobytes(), _ARRAY_BUFFER), "byteOffset": 0,
                "componentType": _FLOAT, "count": count, "type": "VEC4",
            })
        index_accessor = accessor({
            "bufferView": index_view, "byteOffset": 0, "componentType": index_type,
            "count": len(primitive.indices), "type": "SCALAR",
        })
        materials.append(_gltf_material(primitive))
        entry = {"attributes": attributes, "indices": index_accessor, "material": len(materials) - 1,
                 "mode": _TRIANGLES}
        # A primitive with no node key gets a node of its own; no occurrence id
        # begins with a NUL, so the keys cannot collide.
        key = f"\0primitive:{len(groups)}" if primitive.node is None else str(primitive.node)
        group = groups.setdefault(key, {"primitive": primitive, "primitives": [], "skin": primitive.skin})
        if group["skin"] != primitive.skin:
            # `skin` belongs to a NODE, so every primitive of one node must agree on it.
            raise ValueError(f"node {key!r} mixes primitives of skins {group['skin']} and {primitive.skin}")
        group["primitives"].append(entry)

    meshes: list[dict] = []
    nodes: list[dict] = []
    node_index: dict[str, int] = {}
    for key, group in groups.items():
        first: Primitive = group["primitive"]
        meshes.append({"primitives": group["primitives"]})
        node: dict[str, Any] = {
            "mesh": len(meshes) - 1,
            "name": sanitize_name(first.name or name, name),
            "extras": {
                # An identity namespace keyed on the source kind, so it survives a rename.
                "cadOccurrenceId": str(first.occurrence_id or f"step:{len(nodes)}"),
                "cadSourceKind": "step",
                "cadUnits": "m",
                # The DECLARED space of these positions, so a CAD reader converts once.
                "cadUpAxis": "y",
            },
        }
        if group["skin"] is not None:
            node["skin"] = int(group["skin"])
        node_index[key] = len(nodes)
        nodes.append(node)

    roots = set(range(len(nodes)))
    skins: list[dict] = []
    animations: list[dict] = []
    if animation is not None and (animation.pivots or animation.skins):
        samplers: list[dict] = []
        channels: list[dict] = []
        time_accessors: dict[bytes, int] = {}

        def time_accessor(values: object) -> int:
            """One input accessor per distinct schedule."""
            times = np.asarray(values, dtype="<f4")
            payload = times.tobytes()
            found = time_accessors.get(payload)
            if found is None:
                found = time_accessors[payload] = accessor({
                    "bufferView": view(payload), "byteOffset": 0, "componentType": _FLOAT,
                    "count": len(times), "type": "SCALAR",
                    # Required on a sampler input: a loader reads the clip's duration off them.
                    "min": [float(times[0])], "max": [float(times[-1])],
                })
            return found

        def animate(target: int, times_accessor: int, path: str, output: int) -> None:
            samplers.append({"input": times_accessor, "output": output, "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": target, "path": path}})

        offsets: list[int] = []  # each pivot's -pivot node, which carries its parts
        for ordinal, pivot in enumerate(animation.pivots):
            members = []
            for member in pivot.members:
                target = node_index.get(str(member))
                if target is None:
                    raise ValueError(f"animation pivot {ordinal} carries {member!r}, which no primitive declared")
                members.append(target)
                roots.discard(target)
            nodes.append({"name": f"pivot {ordinal} offset", "translation": [float(c) for c in pivot.child_translation],
                          "children": members})
            offset = len(nodes) - 1
            nodes.append({"name": f"pivot {ordinal}", "translation": [float(c) for c in pivot.rest_translation],
                          "rotation": [float(c) for c in pivot.rest_rotation], "children": [offset]})
            roots.add(len(nodes) - 1)
            offsets.append(offset)
            times = time_accessor(pivot.times)
            for path, values, kind in (("translation", pivot.translations, "VEC3"), ("rotation", pivot.rotations, "VEC4")):
                data = np.asarray(values, dtype="<f4")
                animate(len(nodes) - 1, times, path, accessor({
                    "bufferView": view(data.tobytes()), "byteOffset": 0, "componentType": _FLOAT,
                    "count": len(pivot.times), "type": kind,
                }))
        for ordinal, skin in enumerate(animation.skins):
            count, keys = skin.translations.shape[1], len(skin.times)
            first_joint = len(nodes)
            for joint in range(count):
                nodes.append({"name": f"tube {ordinal} joint {joint}",
                              "translation": [float(c) for c in skin.translations[0, joint]],
                              "rotation": [float(c) for c in skin.rotations[0, joint]]})
            joints = list(range(first_joint, first_joint + count))
            if skin.parent is None:
                roots.update(joints)
            else:
                nodes[offsets[skin.parent]]["children"] += joints
            skins.append({"name": f"tube {ordinal}", "joints": joints, "inverseBindMatrices": accessor({
                "bufferView": view(np.asarray(skin.inverse_binds, dtype="<f4").tobytes()), "byteOffset": 0,
                "componentType": _FLOAT, "count": count, "type": "MAT4",
            })})
            times = time_accessor(skin.times)
            # Every joint's keys contiguous, so each joint's output is one slice of a view.
            for path, values, width, kind in (("translation", skin.translations, 3, "VEC3"),
                                              ("rotation", skin.rotations, 4, "VEC4")):
                data = np.ascontiguousarray(np.transpose(np.asarray(values, dtype="<f4"), (1, 0, 2)))
                shared = view(data.tobytes())
                for joint in range(count):
                    animate(first_joint + joint, times, path, accessor({
                        "bufferView": shared, "byteOffset": joint * keys * width * 4, "componentType": _FLOAT,
                        "count": keys, "type": kind,
                    }))
        animations.append({"name": sanitize_name(animation.name or "clip", "clip"),
                           "samplers": samplers, "channels": channels})

    gltf: dict[str, Any] = {
        "asset": {"version": "2.0", "generator": "cadgen"},
        "scene": 0,
        "scenes": [{"nodes": sorted(roots)}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": materials,
        "bufferViews": buffer_views,
        "accessors": accessors,
    }
    if skins:
        gltf["skins"] = skins
    if animations:
        gltf["animations"] = animations
    if any("KHR_materials_clearcoat" in (material.get("extensions") or {}) for material in materials):
        # USED, never required: a loader without it draws the right part without the coat.
        gltf["extensionsUsed"] = ["KHR_materials_clearcoat"]
    chunk = b"".join(binary)
    chunk += b"\0" * (-len(chunk) % 4)
    gltf["buffers"] = [{"byteLength": len(chunk)}]
    text = json.dumps(gltf, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    text += b" " * (-len(text) % 4)
    total = 12 + 8 + len(text) + 8 + len(chunk)
    return b"".join([
        struct.pack("<III", 0x46546C67, 2, total),
        struct.pack("<II", len(text), 0x4E4F534A), text,
        struct.pack("<II", len(chunk), 0x004E4942), chunk,
    ])
