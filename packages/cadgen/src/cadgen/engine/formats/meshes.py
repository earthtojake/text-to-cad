"""An STL and a 3MF as the stills hold them (``formats.Foreign``): each mesh object a part in
the look's fill or the colours its file gives its triangles, placed as the file places it, in
millimetres, with the viewer's normals and feature edges (``buffer.py``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from cadgen.engine.formats import Foreign, FormatError, Part, Placed, assemble, files_of
from cadgen.engine.formats.buffer import buffer

__all__ = ["build_of", "mesh_part", "painted", "stl_file", "threemf_file"]


def mesh_part(name: str, points: np.ndarray, triangles: np.ndarray, *, scale: float = 1.0, paints: np.ndarray | None = None,
              palette: list[tuple[tuple, dict | None]] | None = None, unit: float = 1.0) -> Part:
    """A mesh object as a part: its points times ``scale`` (millimetres), one face per paint it
    uses (``paints``: each triangle's index into ``palette``, -1 for none), its colour the one
    paint every triangle wears. ``unit`` is the millimetres one of the mesh's own numbers is
    drawn as, which sets three's rounding steps."""
    points = np.asarray(points, np.float64) * scale
    triangles = np.asarray(triangles, np.int64).reshape(-1, 3)
    faces, color, face_colors, material, face_materials = painted(len(triangles), paints, palette)
    step = scale * unit
    mesh, _uv = buffer(points, triangles, faces=faces, weld=1e-4 * step, hashed=1e-2 * step)
    return Part(name, mesh, color, face_colors, material, face_materials)


def painted(count: int, paints: np.ndarray | None, palette: list[tuple[tuple, dict | None]] | None
            ) -> tuple[np.ndarray | None, tuple | None, dict[int, tuple], dict | None, dict[int, dict]]:
    """A mesh object's paints as a part's look: each triangle's face ordinal (None: one face), the
    part's colour and material (the one paint every triangle wears), and each face's colour and
    material (a face per paint, from 1, where the triangles wear several)."""
    faces = None
    color = material = None
    face_colors: dict[int, tuple] = {}
    face_materials: dict[int, dict] = {}
    if paints is not None and palette and count:
        used = sorted(set(int(value) for value in np.unique(paints)))
        if used == [-1]:
            pass
        elif len(used) == 1:
            color, finish = palette[used[0]]
            material = _material(color, finish)
        else:
            ordinal = {paint: at for at, paint in enumerate(used, 1)}
            faces = np.array([ordinal[int(value)] for value in paints], np.int64) if len(paints) < 4096 \
                else np.searchsorted(np.array(used), paints) + 1
            for paint, at in ordinal.items():
                if paint >= 0:
                    face_colors[at] = palette[paint][0]
                    if palette[paint][1]:
                        face_materials[at] = _material(palette[paint][0], palette[paint][1])
    return faces, color, face_colors, material, face_materials


def _material(rgba: tuple, finish: dict | None) -> dict[str, Any] | None:
    """A 3MF display property (``pbmetallic``) as the structure's material: the finish over its colour."""
    if not finish:
        return None
    from cadgen.engine.formats.gltf import material_of

    return material_of({"name": "3MF display properties", "alphaMode": "BLEND" if rgba[3] < 1 else "OPAQUE",
                        "pbrMetallicRoughness": {"baseColorFactor": rgba, "metallicFactor": finish.get("metallic", 0.0),
                                                "roughnessFactor": finish.get("roughness", 0.5)}})


def stl_file(path: Path) -> Foreign:
    from cadgen.engine.formats.stl import StlError, read_stl

    try:
        corners = read_stl(path)
    except StlError as error:
        raise FormatError(str(error)) from None
    if not len(corners):
        raise FormatError(f"{path.name} holds no triangles to draw")
    points = corners.reshape(-1, 3)
    part = mesh_part(path.stem, points, np.arange(len(points)).reshape(-1, 3))
    return assemble("stl", path, path.stem, [part], [Placed(0, np.eye(4), path.stem)],
                    {"name": path.stem, "prototype": 0, "instance": 0}, files_of([path]))


def threemf_file(path: Path) -> Foreign:
    from cadgen.engine.formats.threemf import ThreeMfError, read_3mf

    try:
        model = read_3mf(path)
    except ThreeMfError as error:
        raise FormatError(str(error)) from None
    parts = [mesh_part(part.name, part.points, part.triangles, scale=model.unit, paints=part.paints,
                       palette=model.paints) for part in model.parts]
    if not any(part.mesh.triangles for part in parts):
        raise FormatError(f"{path.name} holds no triangles to draw")
    placed, tree = build_of(path, model)
    # A length of the file is in its declared unit, which the viewer draws unscaled: its scene is that unit too.
    return assemble("3mf", path, path.stem, parts, placed, tree, files_of([path]), unit=model.unit)


def build_of(path: Path, model: Any) -> tuple[list[Placed], dict[str, Any]]:
    """A 3MF's build (``threemf.Model``) as placements, in millimetres as its parts' points are
    (``model.unit`` times its numbers), and the tree of them (``_tree``)."""
    placed, leaves = [], []
    for index, (part, matrix, at) in enumerate(model.placed):
        matrix = np.asarray(matrix, float).copy()
        matrix[:3, 3] *= model.unit  # the placement's numbers in millimetres, as the part's points are
        name = model.parts[part].name
        placed.append(Placed(part, matrix, f"{path.stem}/{name}", palette=index))
        leaves.append((at, {"name": name, "prototype": part, "instance": index}))
    return placed, _tree(path.stem, leaves)


def _tree(name: str, leaves: list[tuple[tuple[int, ...], dict[str, Any]]]) -> dict[str, Any]:
    """The build as a tree: a node per build item (and per component object down it), the parts
    at its leaves, in the build's order."""
    if len(leaves) == 1 and len(leaves[0][0]) == 1:
        return leaves[0][1]
    root: dict[str, Any] = {"name": name, "children": []}
    nodes: dict[tuple[int, ...], dict[str, Any]] = {(): root}
    for at, leaf in leaves:
        for depth in range(1, len(at)):
            key = at[:depth]
            if key not in nodes:
                nodes[key] = {"name": f"Object {'.'.join(map(str, key))}", "children": []}
                nodes[key[:-1]]["children"].append(nodes[key])
        nodes[at[:-1]]["children"].append(leaf)
    return root
