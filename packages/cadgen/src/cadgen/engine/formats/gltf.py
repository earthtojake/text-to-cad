"""A GLB read with numpy alone, no kernel: its scene's mesh nodes, each mesh's triangles and the
materials its primitives wear, in the viewer's frame. What a conversion reads a GLB as
(``export/mesh_source.py``); the stills read one through OCCT (``glb.py``).

- **Frame**: as the viewer places a GLB (``glbMeshData.js``): a node's placement is the product of
  the nodes' down the scene, its numbers glTF's Y-up metres turned Z up and times 1000, so
  millimetres; a file whose nodes declare ``extras.cadUpAxis: "z"`` is read Z up. The uniform
  scale every placement of a mesh shares is moved into its points, so its placements are rigid
  and its points millimetres.
- **Meshes**: a mesh's triangle primitives (``TRIANGLES``, strips and fans unrolled; points and
  lines are no surface, and are left out), their positions, normals where every primitive has
  them, and indices; primitives on the same attributes share their vertices. A primitive is a
  face of its mesh (from 1, in the file's order).
- **Materials**: a primitive's material is the structure's: its base colour (linear; its alpha a
  ``BLEND`` material's, else opaque), metallic, roughness, emission and name, and the engine's KHR
  extensions (``look_extensions``). Textures are not read.

Accessors are read as the spec has them -- any component type, normalized, strided, sparse.
Compressed geometry (``KHR_draco_mesh_compression``, ``EXT_meshopt_compression``) and buffers
outside the file are refused by name: their numbers are not in what is read."""

from __future__ import annotations

import base64
import json
import math
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

# The container's constants as the engine's GLB writer declares them.
from cadgen.engine.export.glb import BIN_CHUNK, JSON_CHUNK, MAGIC

__all__ = ["GltfError", "Part", "Read", "look_extensions", "material_of", "read_gltf"]

_COMPONENTS = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}
_COMPRESSED = ("KHR_draco_mesh_compression", "EXT_meshopt_compression")
# glTF's Y up as the CAD's Z up, (x, y, z) -> (x, -z, y): the viewer's ``cadVectorFromGlbVector``.
_Z_UP = np.array([[1.0, 0, 0, 0], [0, 0, -1.0, 0], [0, 1.0, 0, 0], [0, 0, 0, 1.0]])
# glTF's metres as millimetres: the viewer's ``GLB_CAD_UNIT_SCALE``.
_MILLIMETRES = np.diag([1000.0, 1000.0, 1000.0, 1.0])


class GltfError(ValueError):
    """A file that does not read as a GLB, said by name."""


@dataclass
class Part:
    """A glTF mesh: its name, its points (millimetres, once read), triangles (M, 3), normals (or
    None), each triangle's face (its primitive, from 1) and each face's material (None: none)."""

    name: str
    points: np.ndarray
    triangles: np.ndarray
    normals: np.ndarray | None
    faces: np.ndarray
    materials: list[dict[str, Any] | None] = field(default_factory=list)


@dataclass
class Read:
    """A GLB: its parts, and each placement of one -- (part, 4x4 in millimetres acting on columns,
    the node's name)."""

    parts: list[Part]
    placed: list[tuple[int, np.ndarray, str]]


def _chunks(path: Path) -> tuple[dict[str, Any], bytes]:
    data = path.read_bytes()
    if len(data) < 20 or struct.unpack_from("<I", data)[0] != MAGIC:
        raise GltfError(f"{path.name} is not a GLB (binary glTF): it does not begin with glTF")
    at, document, binary = 12, None, b""
    while at + 8 <= len(data):
        length, kind = struct.unpack_from("<II", data, at)
        body = data[at + 8:at + 8 + length]
        if kind == JSON_CHUNK and document is None:
            try:
                document = json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise GltfError(f"{path.name}: its JSON does not read ({error})") from None
        elif kind == BIN_CHUNK and not binary:
            binary = body
        at += 8 + length + (-length % 4)
    if not isinstance(document, dict):
        raise GltfError(f"{path.name}: a GLB's first chunk is its JSON")
    return document, binary


def _buffers(path: Path, gltf: dict[str, Any], binary: bytes) -> list[bytes]:
    found = []
    for index, buffer in enumerate(gltf.get("buffers") or []):
        uri = (buffer or {}).get("uri")
        if uri is None:
            found.append(binary)
        elif uri.startswith("data:") and ";base64," in uri:
            found.append(base64.b64decode(uri.partition(";base64,")[2]))
        else:
            raise GltfError(f"{path.name}: buffer {index} is a file beside it ({uri}); a GLB is read whole from itself")
    return found


def _dtype(component: int) -> np.dtype:
    return np.dtype(_COMPONENTS[component]).newbyteorder("<")


def _view(gltf: dict[str, Any], buffers: list[bytes], view_index: int, offset: int, dtype: np.dtype, count: int,
          width: int) -> np.ndarray:
    view = gltf["bufferViews"][view_index]
    data = buffers[view.get("buffer", 0)]
    begin = int(view.get("byteOffset", 0))
    length = int(view.get("byteLength", len(data) - begin))
    start = begin + offset
    element = dtype.itemsize * width
    stride = int(view.get("byteStride") or element)
    # Every byte the elements span must lie inside the buffer view, which must lie inside its
    # buffer: glTF's own bounds. np.lib.stride_tricks.as_strided checks nothing, so without
    # this a view could read bytes past the buffer the file holds.
    if (min(begin, length, offset, count) < 0 or stride < element or begin + length > len(data)
            or (count and start + (count - 1) * stride + element > begin + length)):
        raise GltfError(f"buffer view {view_index} does not hold the {count} elements an accessor reads")
    if stride == element:
        return np.frombuffer(data, dtype, count * width, start).reshape(count, width)
    rows = np.lib.stride_tricks.as_strided(np.frombuffer(data, np.uint8, begin + length - start, start),
                                           (count, element), (stride, 1))
    return np.ascontiguousarray(rows).view(dtype).reshape(count, width)


def _accessor(gltf: dict[str, Any], buffers: list[bytes], index: int) -> np.ndarray:
    """An accessor's values, (count, width): floats as float64 (normalized integers as their
    fractions), integers as int64."""
    accessor = gltf["accessors"][index]
    dtype = _dtype(accessor["componentType"])
    width = _WIDTHS[accessor["type"]]
    count = int(accessor["count"])
    if "bufferView" in accessor:
        raw = _view(gltf, buffers, accessor["bufferView"], int(accessor.get("byteOffset", 0)), dtype, count, width)
    else:
        # Zeros, backed by no bytes: never more elements than the file as a whole could hold.
        if not 0 <= count <= sum(len(data) for data in buffers):
            raise GltfError(f"accessor {index} names {count} elements its file has no room for")
        raw = np.zeros((count, width), dtype)
    sparse = accessor.get("sparse")
    if sparse:
        indices, values = sparse["indices"], sparse["values"]
        if not 0 <= int(sparse["count"]) <= count:
            raise GltfError(f"accessor {index} replaces {sparse['count']} of its {count} elements")
        at = _view(gltf, buffers, indices["bufferView"], int(indices.get("byteOffset", 0)),
                   _dtype(indices["componentType"]), int(sparse["count"]), 1).reshape(-1).astype(np.int64)
        raw = raw.copy()
        raw[at] = _view(gltf, buffers, values["bufferView"], int(values.get("byteOffset", 0)), dtype,
                        int(sparse["count"]), width)
    if dtype.kind == "f":
        return raw.astype(np.float64)
    if accessor.get("normalized"):
        return np.maximum(raw.astype(np.float64) / float(np.iinfo(dtype).max), -1.0)
    return raw.astype(np.int64)


def _local(node: dict[str, Any]) -> np.ndarray:
    """A node's own transform, 4x4 acting on columns."""
    if "matrix" in node:
        return np.array(node["matrix"], float).reshape(4, 4).T
    x, y, z, w = (float(value) for value in node.get("rotation", (0, 0, 0, 1)))
    rotation = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    matrix = np.eye(4)
    matrix[:3, :3] = rotation * np.array([float(value) for value in node.get("scale", (1, 1, 1))])
    matrix[:3, 3] = [float(value) for value in node.get("translation", (0, 0, 0))]
    return matrix


def _triangles(mode: int, corners: np.ndarray) -> np.ndarray:
    """A primitive's indices as triangles: a list (4), a strip (5) or a fan (6)."""
    if mode == 4:
        return corners[:len(corners) // 3 * 3].reshape(-1, 3)
    if len(corners) < 3:
        return np.zeros((0, 3), np.int64)
    if mode == 5:  # every other triangle of a strip is wound the other way
        rows = np.stack([corners[:-2], corners[1:-1], corners[2:]], 1)
        rows[1::2] = rows[1::2][:, [1, 0, 2]]
        return rows
    return np.stack([np.full(len(corners) - 2, corners[0]), corners[1:-1], corners[2:]], 1)


def look_extensions(extensions: dict[str, Any]) -> dict[str, Any]:
    """What a glTF material's extensions say of its look, as the structure's material says it: the
    engine's GLB writes them (``export/glb.py``), and both of the engine's GLB readers read them."""
    found: dict[str, Any] = {}
    if "KHR_materials_ior" in extensions:
        found["ior"] = float(extensions["KHR_materials_ior"].get("ior", 1.5))
    if "KHR_materials_transmission" in extensions:
        found["transmission"] = float(extensions["KHR_materials_transmission"].get("transmissionFactor", 0.0))
        volume = extensions.get("KHR_materials_volume") or {}
        if volume.get("attenuationColor"):
            found["transmissionColor"] = [float(c) for c in volume["attenuationColor"]]
    if "KHR_materials_clearcoat" in extensions:
        coat = extensions["KHR_materials_clearcoat"]
        found["coat"] = float(coat.get("clearcoatFactor", 0.0))
        found["coatRoughness"] = float(coat.get("clearcoatRoughnessFactor", 0.0))
    if "KHR_materials_anisotropy" in extensions:
        found["anisotropy"] = float(extensions["KHR_materials_anisotropy"].get("anisotropyStrength", 0.0))
    if "KHR_materials_emissive_strength" in extensions:
        found["emissiveStrength"] = float(extensions["KHR_materials_emissive_strength"].get("emissiveStrength", 1.0))
    return found


def material_of(entry: dict[str, Any]) -> dict[str, Any]:
    """A glTF material as the structure's material, glTF's defaults where it says nothing."""
    pbr = entry.get("pbrMetallicRoughness") or {}
    color = [float(value) for value in pbr.get("baseColorFactor", (1.0, 1.0, 1.0, 1.0))]
    if str(entry.get("alphaMode") or "OPAQUE") != "BLEND":
        color[3] = 1.0
    found: dict[str, Any] = {"name": str(entry.get("name") or "") or "glTF material",
                             "color": [round(value, 6) for value in color],
                             "metallic": float(pbr.get("metallicFactor", 1.0)),
                             "roughness": float(pbr.get("roughnessFactor", 1.0)), "ior": 1.5,
                             "emissive": [float(value) for value in entry.get("emissiveFactor", (0.0, 0.0, 0.0))]}
    found.update(look_extensions(entry.get("extensions") or {}))
    return found


def read_gltf(path: Path) -> Read:
    """The GLB at ``path`` (see the module docstring)."""
    path = Path(path)
    gltf, binary = _chunks(path)
    compressed = [name for name in gltf.get("extensionsUsed") or [] if name in _COMPRESSED]
    if compressed:
        raise GltfError(f"{path.name} is compressed ({', '.join(compressed)}): its numbers are not read")
    try:
        return _read(path, gltf, _buffers(path, gltf, binary))
    except GltfError:
        raise
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise GltfError(f"{path.name}: its glTF does not read ({type(error).__name__}: {error})") from None


def _read(path: Path, gltf: dict[str, Any], buffers: list[bytes]) -> Read:
    nodes = gltf.get("nodes") or []
    meshes = gltf.get("meshes") or []
    materials = [material_of(entry or {}) for entry in gltf.get("materials") or []]
    z_up = any(str(((node or {}).get("extras") or {}).get("cadUpAxis") or "").lower() == "z" for node in nodes)
    frame = _MILLIMETRES if z_up else _Z_UP @ _MILLIMETRES
    scenes = gltf.get("scenes") or []
    if scenes:
        roots = list((scenes[int(gltf.get("scene", 0))] or {}).get("nodes") or [])
    else:
        children = {child for node in nodes for child in (node or {}).get("children") or []}
        roots = [index for index in range(len(nodes)) if index not in children]
    part_of: dict[int, int] = {}  # mesh index -> part
    parts: list[Part] = []
    placed: list[tuple[int, np.ndarray, str]] = []

    def part(index: int) -> int:
        if index in part_of:
            return part_of[index]
        mesh = meshes[index] or {}
        points, normals, triangles, faces, looks = [], [], [], [], []
        shared: dict[tuple, tuple[int, int]] = {}  # (POSITION, NORMAL) accessors -> (first vertex, count)
        base = 0
        for primitive in mesh.get("primitives") or []:
            mode = int(primitive.get("mode", 4))
            attributes = primitive.get("attributes") or {}
            if mode not in (4, 5, 6) or "POSITION" not in attributes:
                continue
            key = (attributes["POSITION"], attributes.get("NORMAL"))
            if key not in shared:
                found = _accessor(gltf, buffers, attributes["POSITION"])
                shared[key] = (base, len(found))
                points.append(found)
                normals.append(None if key[1] is None else _accessor(gltf, buffers, key[1]))
                base += len(found)
            first, count = shared[key]
            corners = _accessor(gltf, buffers, primitive["indices"]).reshape(-1) if "indices" in primitive \
                else np.arange(count, dtype=np.int64)
            rows = _triangles(mode, corners)
            if len(rows) and (rows.min() < 0 or rows.max() >= count):
                raise GltfError(f"{path.name}: mesh {index} has a triangle naming a vertex it lacks")
            looks.append(materials[primitive["material"]] if "material" in primitive else None)
            triangles.append(rows + first)
            faces.append(np.full(len(rows), len(looks), np.int64))
        parts.append(Part(str(mesh.get("name") or "") or f"mesh{index + 1}",
                          np.concatenate(points) if points else np.zeros((0, 3)),
                          np.concatenate(triangles) if triangles else np.zeros((0, 3), np.int64),
                          np.concatenate(normals) if normals and all(item is not None for item in normals) else None,
                          np.concatenate(faces) if faces else np.zeros(0, np.int64), looks))
        part_of[index] = len(parts) - 1
        return part_of[index]

    # A node listed by several parents (or one parent several times) is placed once for each, so
    # a small file can name an exponential tree: bounded as a document's assembly is.
    from cadgen.engine.document import MAX_ASSEMBLY_DEPTH, MAX_OCCURRENCES

    visited = 0

    def visit(index: int, parent: np.ndarray, trail: tuple[int, ...]) -> None:
        nonlocal visited
        if index in trail:
            raise GltfError(f"{path.name}: node {index} holds itself")
        if len(trail) >= MAX_ASSEMBLY_DEPTH:
            raise GltfError(f"{path.name}: its node tree is deeper than {MAX_ASSEMBLY_DEPTH} levels")
        visited += 1
        if visited > MAX_OCCURRENCES:
            raise GltfError(f"{path.name}: its node tree names more than {MAX_OCCURRENCES} occurrences")
        node = nodes[index] or {}
        world = parent @ _local(node)
        if "mesh" in node:
            mesh = int(node["mesh"])
            name = str(node.get("name") or "") or str((meshes[mesh] or {}).get("name") or "") or f"node{index}"
            placed.append((part(mesh), world, name))
        for child in node.get("children") or []:
            visit(int(child), world, (*trail, index))

    for root in roots:
        visit(int(root), frame, ())
    # Each part's scale, when every placement of it shares one: moved into its points.
    scales: dict[int, float] = {}
    for index, matrix, _name in placed:
        scale = float(np.cbrt(abs(np.linalg.det(matrix[:3, :3])))) or 1.0
        held = scales.get(index, scale)
        scales[index] = scale if math.isclose(held, scale, rel_tol=1e-9) else math.nan
    rigid = []
    for index, matrix, name in placed:
        matrix = matrix.copy()
        if not math.isnan(scales[index]):
            matrix[:3, :3] /= scales[index]
        rigid.append((index, matrix, name))
    for index, scale in scales.items():
        if not math.isnan(scale):
            parts[index].points = parts[index].points * scale
    return Read(parts, rigid)
