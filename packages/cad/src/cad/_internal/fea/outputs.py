"""The files a solve writes into its folder: the coloured surface (``result.glb``), the volume's fields
(``result.vtu``) and a picture of each field.

``result.glb`` is a binary glTF of the deformed boundary surface, coloured by the value ramp as a texture -- a one-row
PNG of :data:`RAMP` -- read at ``TEXCOORD_0``, the stress normalised to the ramp's range, so OCCT's stills, three.js
and any other glTF viewer colour it the same, and a contour stays sharp across a triangle where vertex colours would
blur it. The raw fields ride along as attributes (``_VON_MISES``, ``_DISPLACEMENT`` in glTF metres and axes, unscaled;
``_FACE``; :func:`write_glb`), and the mesh's ``extras`` say what each is, with the ramp, the face refs, the study and
its checks. Written by hand (glTF 2.0 is a JSON header and one binary buffer; a PNG is zlib and four chunks) so the
result path adds no dependency the solver did not already need.

``result.vtu`` is VTK's unstructured grid, binary: the volume's linear tetrahedra with the displacement vector and von
Mises at each node (and each element's part, for an assembly), which meshio, PyVista and ParaView read as they are.

The pictures are the engine's stills of the GLB (``cad.engine.api.snapshot``), one per field, each with a colour bar
under it giving the field, its units and its range (:func:`draw_pictures`).
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

__all__ = ["RAMP", "RAMP_PIXELS", "auto_deformation_scale", "colour_bar", "draw_pictures", "ramp", "ramp_png",
           "write_glb", "write_vtu"]

#: Blue -> cyan -> green -> yellow -> red: the ramp every FEA post-processor uses, so a reader's eye already knows which
#: end is hot. Written into the GLB's extras, so a reader that recolours by another field draws the same ramp.
RAMP = ((0.0, (0.05, 0.10, 0.90)), (0.25, (0.05, 0.85, 0.95)), (0.5, (0.10, 0.85, 0.15)),
        (0.75, (0.98, 0.90, 0.10)), (1.0, (0.90, 0.08, 0.05)))

# netgen's 6-node triangle lists the three corners, then the mid-edge nodes of edges (1,2) (0,2) (0,1), in that order.
_TRIG6_MID_OF_EDGE = {(1, 2): 3, (0, 2): 4, (0, 1): 5}

# Face indices share one int64 key with the node id: room for 2**20 faces, offset by one so -1 fits.
_FACE_SLOTS = 1 << 20


def ramp(t: "np.ndarray") -> "np.ndarray":
    """(n, 3) RGB in [0, 1] for values t in [0, 1]."""
    import numpy as np

    t = np.clip(np.asarray(t, dtype=float), 0.0, 1.0)
    stops = np.array([s for s, _ in RAMP])
    colours = np.array([c for _, c in RAMP])
    return np.stack([np.interp(t, stops, colours[:, channel]) for channel in range(3)], axis=1)


#: The ramp texture's width: one pixel per step of the ramp, sampled linearly between them.
RAMP_PIXELS = 256


def ramp_png() -> bytes:
    """:data:`RAMP` as a PNG one row of :data:`RAMP_PIXELS` RGB pixels high: the texture a result GLB is coloured by."""
    import zlib

    import numpy as np

    row = (ramp(np.linspace(0.0, 1.0, RAMP_PIXELS)) * 255).round().astype(np.uint8)
    raw = b"\0" + row.tobytes()  # filter type 0, then the row

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", RAMP_PIXELS, 1, 8, 2, 0, 0, 0)  # 8-bit RGB, no interlace
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def ramp_coordinates(t: "np.ndarray") -> "np.ndarray":
    """(n, 2) texture coordinates of values ``t`` in [0, 1] on the ramp texture: each at its pixel's centre, so the
    ends never sample past the ramp."""
    import numpy as np

    t = np.clip(np.asarray(t, dtype=np.float32), 0.0, 1.0)
    u = (0.5 + t * (RAMP_PIXELS - 1)) / RAMP_PIXELS
    return np.column_stack([u, np.full_like(u, 0.5)]).astype(np.float32)


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
    """CAD (x, y, z) mm -> glTF (x, z, -y) metres: the convention cad's own
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


def write_glb(path: Path, *, positions: "np.ndarray", displacement: "np.ndarray", values: "np.ndarray",
              triangles6: "np.ndarray", face_of_triangle: "np.ndarray", scale: float,
              value_range: tuple[float, float], extras: dict,
              values_by_part: "np.ndarray | None" = None, part_of_triangle: "np.ndarray | None" = None) -> None:
    """A binary glTF of the deformed boundary surface coloured by the value ramp's texture.

    ``positions``, ``displacement`` and ``values`` are per node (corner and mid-edge alike); ``triangles6`` are the
    mesher's boundary triangles in those node ids, wound consistently, which is kept -- flipped as a whole only when the
    surface encloses negative volume. ``face_of_triangle`` is the index into ``extras["faces"]`` of the face each of
    those triangles lies on (-1 for none): it becomes ``_FACE``, one value per vertex. For an assembly,
    ``values_by_part`` (parts, nodes) holds each part's own field and ``part_of_triangle`` the part each triangle
    belongs to: a vertex takes the value of its face's part, so a joint's two sides keep their own stress.
    ``part_of_triangle`` also becomes ``_PART`` (float, an index into ``extras["parts"]``), one value per vertex; a
    single part has no ``_PART``.

    ``values`` (von Mises) colour the surface and are written as ``_VON_MISES``.
    """
    import numpy as np

    triangles = _split_quadratic(np.asarray(triangles6))
    face_of = np.tile(np.asarray(face_of_triangle, dtype=np.int64), 4)  # _split_quadratic's four blocks
    if _signed_volume(positions, triangles) < 0:
        triangles = triangles[:, [0, 2, 1]]
    # One vertex per (node, face): a node on an edge between faces is written once for each.
    pairs = triangles.astype(np.int64) * _FACE_SLOTS + (face_of[:, None] + 1)
    unique_pairs, compact = np.unique(pairs, return_inverse=True)
    used = unique_pairs // _FACE_SLOTS
    face = ((unique_pairs % _FACE_SLOTS) - 1).astype(np.float32)
    tris = compact.reshape(triangles.shape).astype(np.uint32)
    pos = _gltf_space(positions[used] + scale * displacement[used])
    vertex_part = None
    if part_of_triangle is not None:
        vertex_part = np.zeros(len(unique_pairs), dtype=np.int64)
        vertex_part[compact] = np.tile(np.asarray(part_of_triangle, dtype=np.int64), 4)[:, None]
    if values_by_part is None:
        vals = values[used].astype(np.float32)
    else:
        vals = values_by_part[vertex_part, used].astype(np.float32)
    disp = _gltf_space(displacement[used])
    lo, hi = value_range
    t = (vals - lo) / (hi - lo) if hi > lo else np.zeros_like(vals)
    normals = _vertex_normals(pos.astype(float), tris).astype(np.float32)

    blobs: list[bytes] = []
    views: list[dict] = []
    accessors: list[dict] = []

    def place(data: bytes) -> int:
        offset = sum(len(b) for b in blobs)
        blobs.append(data + b"\0" * (-len(data) % 4))
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(data)})
        return len(views) - 1

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
    FLOAT, UINT = 5126, 5125
    LINEAR, CLAMP = 9729, 33071
    attributes = {
        "POSITION": add(pos, target=ARRAY, kind="VEC3", component=FLOAT, bounds=True),
        "NORMAL": add(normals, target=ARRAY, kind="VEC3", component=FLOAT),
        "TEXCOORD_0": add(ramp_coordinates(t), target=ARRAY, kind="VEC2", component=FLOAT),
    }
    attributes["_VON_MISES"] = add(vals.reshape(-1, 1), target=ARRAY, kind="SCALAR", component=FLOAT)
    attributes["_DISPLACEMENT"] = add(disp, target=ARRAY, kind="VEC3", component=FLOAT)
    # Float: a 2-byte scalar would need padding to the 4-byte vertex alignment glTF asks of attributes.
    attributes["_FACE"] = add(face.reshape(-1, 1), target=ARRAY, kind="SCALAR", component=FLOAT)
    if vertex_part is not None:
        attributes["_PART"] = add(vertex_part.astype(np.float32).reshape(-1, 1), target=ARRAY, kind="SCALAR", component=FLOAT)
    name = extras.get("name", "fea result")
    image = place(ramp_png())
    gltf = {
        "asset": {"version": "2.0", "generator": "cad solve"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": name}],
        "meshes": [{
            "name": name,
            "extras": extras,
            "primitives": [{
                "attributes": attributes,
                "indices": add(tris.reshape(-1, 1), target=ELEMENT, kind="SCALAR", component=UINT),
                "material": 0,
                "mode": 4,
            }],
        }],
        "materials": [{
            "name": "fea ramp",
            "doubleSided": True,
            "pbrMetallicRoughness": {"baseColorFactor": [1.0, 1.0, 1.0, 1.0], "baseColorTexture": {"index": 0},
                                     "metallicFactor": 0.0, "roughnessFactor": 0.85},
        }],
        "textures": [{"sampler": 0, "source": 0, "name": "fea ramp"}],
        "samplers": [{"magFilter": LINEAR, "minFilter": LINEAR, "wrapS": CLAMP, "wrapT": CLAMP}],
        "images": [{"bufferView": image, "mimeType": "image/png", "name": "fea ramp"}],
        "buffers": [{"byteLength": sum(len(b) for b in blobs)}],
        "bufferViews": views,
        "accessors": accessors,
    }
    header = json.dumps(gltf, separators=(",", ":"), allow_nan=False).encode("utf-8")
    header += b" " * (-len(header) % 4)
    binary = b"".join(blobs)
    total = 12 + 8 + len(header) + 8 + len(binary)
    path.parent.mkdir(parents=True, exist_ok=True)
    from cad.engine.export.glb import BIN_CHUNK, JSON_CHUNK, MAGIC, VERSION

    with open(path, "wb") as handle:
        handle.write(struct.pack("<III", MAGIC, VERSION, total))
        handle.write(struct.pack("<II", len(header), JSON_CHUNK))
        handle.write(header)
        handle.write(struct.pack("<II", len(binary), BIN_CHUNK))
        handle.write(binary)


def write_vtu(path: Path, *, positions: "np.ndarray", tets: "np.ndarray", displacement: "np.ndarray",
              values: "np.ndarray", part_of_tet: "np.ndarray | None" = None) -> None:
    """A binary VTK unstructured grid (XML, each array base64 after its byte count) of linear tetrahedra: the
    displacement (mm) and von Mises (MPa) at each node, and each element's part where ``part_of_tet`` is given."""
    import base64

    import numpy as np

    def array(name: str, data: "np.ndarray", kind: str, components: int = 1) -> str:
        raw = np.ascontiguousarray(data).tobytes()
        encoded = base64.b64encode(struct.pack("<Q", len(raw)) + raw).decode("ascii")
        named = f' Name="{name}"' if name else ""
        count = f' NumberOfComponents="{components}"' if components > 1 else ""
        return f'<DataArray type="{kind}"{named}{count} format="binary">{encoded}</DataArray>'

    tets = np.asarray(tets, dtype=np.int64)[:, :4]
    n_points, n_cells = len(positions), len(tets)
    cell_data = "" if part_of_tet is None else (
        f'<CellData Scalars="part">{array("part", np.asarray(part_of_tet, dtype=np.int32), "Int32")}</CellData>')
    text = "\n".join([
        '<?xml version="1.0"?>',
        '<VTKFile type="UnstructuredGrid" version="1.0" byte_order="LittleEndian" header_type="UInt64">',
        "<UnstructuredGrid>",
        f'<Piece NumberOfPoints="{n_points}" NumberOfCells="{n_cells}">',
        f'<Points>{array("", np.asarray(positions, dtype=np.float64), "Float64", 3)}</Points>',
        "<Cells>",
        array("connectivity", tets.reshape(-1), "Int64"),
        array("offsets", np.arange(4, 4 * n_cells + 1, 4, dtype=np.int64), "Int64"),
        array("types", np.full(n_cells, 10, dtype=np.uint8), "UInt8"),
        "</Cells>",
        f'<PointData Scalars="von_mises" Vectors="displacement">'
        f'{array("von_mises", np.asarray(values, dtype=np.float64), "Float64")}'
        f'{array("displacement", np.asarray(displacement, dtype=np.float64), "Float64", 3)}</PointData>',
        cell_data,
        "</Piece>",
        "</UnstructuredGrid>",
        "</VTKFile>",
        "",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def draw_pictures(folder: Path, *, glb: Path, stress_png: str, displacement_png: str, surface: dict,
                  max_von_mises_mpa: float, max_displacement_mm: float) -> str | None:
    """``stress_png``, the engine's still of ``glb``, and ``displacement_png``, of the same surface coloured by how far
    each point moved, both into ``folder``, each with its colour bar under it (:func:`colour_bar`). None when both are
    drawn; else why none could be (no display to draw on, the stills' renderer missing), in a line, and neither is left
    behind."""
    import numpy as np

    try:
        from cad.engine.api import snapshot

        moved = folder / "displacement.glb"
        magnitude = np.linalg.norm(np.asarray(surface["displacement"]), axis=1)
        write_glb(moved, values=magnitude, value_range=(0.0, float(max_displacement_mm)),
                  extras={"name": "displacement", "generator": "cad solve"}, **surface)
        for source, picture, field, top in ((glb, stress_png, "von Mises stress (MPa)", max_von_mises_mpa),
                                            (moved, displacement_png, "displacement (mm)", max_displacement_mm)):
            snapshot(source, folder / picture, daemon=False, progress=False)
            colour_bar(folder / picture, field, float(top))
        moved.unlink(missing_ok=True)
        return None
    except Exception as error:  # noqa: BLE001 - a still that cannot be drawn is said, never the solve's failure
        for picture in (stress_png, displacement_png):
            (folder / picture).unlink(missing_ok=True)
        return str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__


def _figure(value: float) -> str:
    """A bar's end in three significant figures, as a person reads one: 212, 1.39, 0.000412."""
    return "0" if value == 0 else f"{value:.3g}"


def colour_bar(picture: Path, field: str, top: float) -> None:
    """The picture with a band under it saying what its colours mean: the field and its units, the ramp, 0 at its
    left end and ``top`` (the field's peak, which the ramp's red end is) at its right, on the picture's own
    background. Pillow, which the kernel's extra carries beside the stills."""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.open(picture).convert("RGB")
    width, height = image.size
    scale = width / 1600
    band = round(120 * scale)
    canvas = Image.new("RGB", (width, height + band), image.getpixel((2, 2)))
    canvas.paste(image, (0, 0))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=max(12, round(26 * scale)))
    left, right = round(width * 0.25), round(width * 0.75)
    top_y, bar = height + round(44 * scale), max(6, round(22 * scale))
    colours = ramp(_linspace(right - left))
    for x, colour in enumerate(colours):
        draw.line([(left + x, top_y), (left + x, top_y + bar)], fill=tuple(int(round(c * 255)) for c in colour))
    ink = (40, 40, 46)
    draw.rectangle([left, top_y, right, top_y + bar], outline=ink, width=1)
    draw.text(((left + right) / 2, top_y - round(8 * scale)), field, fill=ink, font=font, anchor="ms")
    below = top_y + bar + round(8 * scale)
    draw.text((left, below), "0", fill=ink, font=font, anchor="mt")
    draw.text((right, below), _figure(top), fill=ink, font=font, anchor="mt")
    canvas.save(picture, optimize=True)


def _linspace(count: int) -> "np.ndarray":
    import numpy as np

    return np.linspace(0.0, 1.0, max(2, count))
