"""A mesh file as a document of its own kind: triangles, with the parts, names, colours and
placements its format carries -- what ``export.translate`` writes a mesh file from.

An ``.stl`` is one part, its corners welded where they are the same point, its numbers
millimetres; a ``.3mf`` its objects placed by its build, their triangles' colours and display
properties, its numbers in its declared unit made millimetres; a ``.glb`` its scene's mesh nodes
placed as the viewer places them (glTF's Y-up metres as Z-up millimetres), a mesh a part and its
primitives' materials its looks (``formats/gltf.py``). Each reader is numpy and the standard
library alone: a conversion between mesh files loads no CAD kernel.

The document is the structure a B-rep document's is (``document.Loaded.structure``: prototypes,
instances, a tree), each prototype's mesh held beside it (``Source.meshes``) in place of a shape
to tessellate, so the GLB, STL and 3MF writers write it as they write any document. A mesh holds
no B-rep: no xbf, STEP or DXF is made from one (``export.translate``)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np

from cadgen.engine.mesh_format import Mesh

__all__ = ["read"]

_KINDS = {".stl": "stl", ".3mf": "threemf", ".glb": "glb"}


def mesh_of(points: Any, triangles: Any, faces: Any = None, normals: Any = None) -> Mesh:
    """A part's buffer from a mesh file's numbers: ``points`` (V, 3) millimetres, ``triangles``
    (M, 3), each triangle's face ordinal (from 1; one face when None) and ``normals`` (V, 3) or
    None (a format that carries none). Its triangles are ordered by face, a face a range of them."""
    triangles = np.asarray(triangles, np.int64).reshape(-1, 3)
    ordinals = np.ones(len(triangles), np.int64) if faces is None else np.asarray(faces, np.int64).reshape(-1)
    order = np.argsort(ordinals, kind="stable")
    triangles, ordinals = triangles[order], ordinals[order]
    present, first, counts = np.unique(ordinals, return_index=True, return_counts=True)
    table = np.stack([present, first * 3, counts * 3], 1).astype(np.uint32) if len(present) \
        else np.array([[1, 0, 0]], np.uint32)
    shading = None
    if normals is not None:
        shading = np.asarray(normals, np.float64).reshape(-1, 3)
        length = np.linalg.norm(shading, axis=1, keepdims=True)
        shading = np.where(length > 1e-12, shading / np.where(length > 1e-12, length, 1), (0.0, 0.0, 1.0))
        shading = shading.astype(np.float32)
    return Mesh(np.asarray(points, np.float64).reshape(-1, 3).astype(np.float32), shading,
                triangles.astype(np.uint32).reshape(-1), table, np.zeros((0, 4), np.uint32),
                np.zeros((0, 3), np.float32), np.zeros((0, 4), np.float32))


def _column_major(matrix: Any) -> list[float]:
    return [float(value) for value in np.asarray(matrix, float).T.reshape(-1)]


def _prototype(index: int, name: str, mesh: Mesh, color: Any, face_colors: dict[int, Any], material: Any,
               face_materials: dict[int, Any]) -> dict[str, Any]:
    key = f"mesh-{index}-{hashlib.blake2b(mesh.positions.tobytes() + mesh.indices.tobytes(), digest_size=10).hexdigest()}"
    return {"index": index, "key": key, "name": name, "color": None if color is None else [float(c) for c in color],
            "faceNames": {}, "edgeNames": {}, "vertexNames": {},
            "faceColors": {str(ordinal): [float(c) for c in rgba] for ordinal, rgba in sorted(face_colors.items())},
            "material": material,
            "faceMaterials": {str(ordinal): value for ordinal, value in sorted(face_materials.items())}}


def _stl(path: Path) -> tuple[list[tuple], list[tuple], dict[str, Any]]:
    from cadgen.engine.formats.stl import read_stl
    from cadgen.engine.reader import _welded

    points, triangles = _welded(read_stl(path))
    part = (path.stem, mesh_of(points, triangles), None, {}, None, {})
    return [part], [(0, np.eye(4), f"{path.stem}/{path.stem}")], {"name": path.stem, "prototype": 0, "instance": 0}


def _threemf(path: Path) -> tuple[list[tuple], list[tuple], dict[str, Any]]:
    from cadgen.engine.formats.meshes import build_of, painted
    from cadgen.engine.formats.threemf import read_3mf

    model = read_3mf(path)
    parts = []
    for part in model.parts:
        faces, color, face_colors, material, face_materials = painted(len(part.triangles), part.paints, model.paints)
        parts.append((part.name, mesh_of(np.asarray(part.points, np.float64) * model.unit, part.triangles, faces),
                      color, face_colors, material, face_materials))
    placed, tree = build_of(path, model)
    return parts, [(item.part, item.matrix, item.path) for item in placed], tree


def _glb(path: Path) -> tuple[list[tuple], list[tuple], dict[str, Any]]:
    from cadgen.engine.formats.gltf import read_gltf

    read = read_gltf(path)
    parts = []
    for part in read.parts:
        looks = part.materials
        if len(looks) <= 1 or all(look == looks[0] for look in looks):
            # One look for every primitive: the part's own.
            own = looks[0] if looks else None
            parts.append((part.name, mesh_of(part.points, part.triangles, None, part.normals),
                          None if own is None else tuple(own["color"]), {}, own, {}))
            continue
        face_colors = {at: tuple(look["color"]) for at, look in enumerate(looks, 1) if look is not None}
        face_materials = {at: look for at, look in enumerate(looks, 1) if look is not None}
        parts.append((part.name, mesh_of(part.points, part.triangles, part.faces, part.normals), None, face_colors,
                      None, face_materials))
    placed = [(index, matrix, f"{path.stem}/{name}") for index, matrix, name in read.placed]
    leaves = [{"name": name, "prototype": index, "instance": at} for at, (index, _matrix, name) in enumerate(read.placed)]
    tree = leaves[0] if len(leaves) == 1 else {"name": path.stem, "children": leaves}
    return parts, placed, tree


def read(path: Any) -> Any:
    """The mesh file at ``path`` (``.stl``, ``.3mf``, ``.glb``) as an ``export.Source`` (see the
    module docstring). A file that does not read as its suffix says, or holds no triangle, is
    refused by name (``ExportRefused``)."""
    from cadgen.engine.export import ExportRefused, Source
    from cadgen.engine.formats.gltf import GltfError
    from cadgen.engine.formats.stl import StlError
    from cadgen.engine.formats.threemf import ThreeMfError

    path = Path(path)
    kind = _KINDS[path.suffix.lower()]
    if not path.is_file():
        raise ExportRefused(f"no mesh {path}")
    stat = path.stat()
    try:
        parts, placed, tree = {"stl": _stl, "threemf": _threemf, "glb": _glb}[kind](path)
    except (StlError, ThreeMfError, GltfError) as error:
        raise ExportRefused(str(error)) from None
    if not any(mesh.triangles for _name, mesh, *_look in parts):
        raise ExportRefused(f"{path.name} holds no triangles")
    prototypes = [_prototype(index, *part) for index, part in enumerate(parts)]
    instances = [{"prototype": part, "path": where, "matrix": _column_major(matrix), "color": None}
                 for part, matrix, where in placed]
    structure = {"name": path.stem, "path": str(path), "version": f"{stat.st_mtime_ns}-{stat.st_size}", "units": "mm",
                 "kind": kind, "prototypes": prototypes, "instances": instances, "tree": tree}
    meshes = {prototype["key"]: part[1] for prototype, part in zip(prototypes, parts)}
    return Source(structure, {}, live=False, path=path, meshes=meshes, mesh=kind)
