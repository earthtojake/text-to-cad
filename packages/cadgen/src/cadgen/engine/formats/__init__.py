"""The files the stills draw that are not documents: each read here into what a document is to
the renderer -- a structure (prototypes, instances, a tree) and a part buffer per prototype
(``mesh.Mesh``, XBM2) -- so a mesh file or a robot is drawn by the documents' own path
(``render/service.py``'s ``Held``): the look, the modes, the camera fit, the grid, clip,
Explode, Preview, the annotation and the size are theirs. A DXF is a drawing, read here and
drawn by ``render/drawing.py``.

The structure's numbers are millimetres whatever the file's unit, and each reader says what one of
the file's units is in them (``millimetresPerUnit``: a robot's and a GLB's metre 1000, a 3MF's
declared unit, an STL's bare numbers 1), because a length a person reads or writes of the file --
where ``display.clip.at`` stands -- is in the FILE's unit, in the viewer (core's
``lib/viewer/sceneUnits.js``) and in a still alike (``render/clip.py``). Each says too what one of the
viewer's scene coordinates is in them (``millimetresPerSceneUnit``): the file's unit, but a GLB's
millimetre, the viewer drawing glTF's metres as millimetres (core's ``lib/render/glbScene.js``). A Quick
Edit packet's camera, Measure's points and the ink are in those coordinates, as the viewer had them,
and a still reads them through it (``render/occt.py`` ``camera_in_millimetres``, ``annotate``,
``measure``).

| suffix | reader | what it is |
| --- | --- | --- |
| ``.stl`` | ``stl.py`` (numpy) | one part, its numbers as millimetres |
| ``.3mf`` | ``threemf.py`` (zip + XML) | its objects placed by its build, each triangle's colour, its unit |
| ``.glb`` | ``glb.py`` (OCCT's ``RWGltf_CafReader``) | its node tree, meshes, materials and textures |
| ``.urdf``, ``.sdf``, ``.srdf`` | ``robot.py`` (XML) | the link meshes placed by forward kinematics |
| ``.dxf`` | ``dxf.py`` (text) | lines, arcs, circles, polylines, splines, ellipses, solids |

A conversion reads a mesh file with these readers' numpy halves and no kernel
(``export/mesh_file.py``): a GLB through ``gltf.py``, not OCCT's reader.

Nothing is written, nothing is cached on disk: a reader's answer lives in the process that drew
it (the daemon's render process for the file keeps it, warm, until a file it read changes:
``Foreign.files``)."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import numpy as np

if TYPE_CHECKING:  # a reader's module loads no kernel until it reads (the viewer resolves a robot's meshes here)
    from cadgen.engine.mesh_format import Mesh

__all__ = ["DRAWING", "Foreign", "FormatError", "KINDS", "MESHES", "Part", "Placed", "ROBOTS", "assemble", "files_of",
           "read", "stale"]

KINDS = {".stl": "stl", ".3mf": "3mf", ".glb": "glb", ".urdf": "urdf", ".sdf": "sdf", ".srdf": "srdf", ".dxf": "dxf", ".kicad_pcb": "kicad_pcb"}
MESHES = (".stl", ".3mf", ".glb")
ROBOTS = (".urdf", ".sdf", ".srdf")
DRAWING = ".dxf"


class FormatError(ValueError):
    """A file its reader cannot read as what its suffix says, said by name before anything is drawn."""


@dataclass
class Part:
    """A prototype: its name, its buffer (millimetres, its own frame), its colour (linear RGBA, or
    None for the look's fill), its faces' colours and materials, and -- a GLB's -- each vertex's
    texture coordinates and each paint's texture (an OCCT texture set, by the face group it paints)."""

    name: str
    mesh: Mesh
    color: tuple | None = None
    face_colors: dict[int, tuple] = field(default_factory=dict)
    material: dict[str, Any] | None = None
    face_materials: dict[int, dict[str, Any]] = field(default_factory=dict)
    uvs: np.ndarray | None = None
    textures: dict[Any, Any] = field(default_factory=dict)


@dataclass
class Placed:
    """An instance: its part, its placement (4x4, millimetres, acting on columns), its path, a
    colour over its part's, the place it takes in the Parts palette (its index when None), and --
    a robot's -- the viewer's id of the visual it draws (``link:v1``) and its place among that
    visual's objects when the visual draws several (the viewer's ``link:v1/object/0``)."""

    part: int
    matrix: np.ndarray
    path: str
    color: tuple | None = None
    palette: int | None = None
    visual: str | None = None
    object: int | None = None


@dataclass
class Foreign:
    """A file read for the stills: what a renderer holds of it (``structure`` and ``buffers``, and
    the shapes made for parts a buffer cannot carry: a GLB's textured faces), every file read with
    its ``(mtime_ns, size)``, how it poses (a robot's forward kinematics: the structure at a pose)
    and what was not drawn as the file has it (``warnings``)."""

    kind: str
    path: Path
    structure: dict[str, Any]
    buffers: dict[str, bytes]
    shapes: dict[str, Any] = field(default_factory=dict)
    files: dict[str, tuple[int, int]] = field(default_factory=dict)
    pose: Callable[[dict[str, Any], Any], dict[str, Any]] | None = None
    warnings: list[str] = field(default_factory=list)


def files_of(paths: Any) -> dict[str, tuple[int, int]]:
    """Each file's ``(mtime_ns, size)``, by its path."""
    found = {}
    for path in paths:
        stat = os.stat(path)
        found[str(path)] = (stat.st_mtime_ns, stat.st_size)
    return found


def stale(files: dict[str, Any]) -> bool:
    """Whether any file read has changed (or gone) since."""
    try:
        return any(tuple(files_of([path])[path]) != tuple(seen) for path, seen in files.items())
    except OSError:
        return True


def _column_major(matrix: np.ndarray) -> list[float]:
    return [float(value) for value in np.asarray(matrix, float).T.reshape(-1)]


def assemble(kind: str, path: Path, name: str, parts: list[Part], placed: list[Placed], tree: dict[str, Any],
             files: dict[str, tuple[int, int]], *, pose: Callable | None = None,
             warnings: list[str] | None = None, unit: float = 1.0, scene_unit: float | None = None) -> Foreign:
    """The file as a renderer holds it: the structure ``Loaded.structure()`` would give a document
    of these parts, instances and tree, each part's buffer by a key of its bytes, and the shapes of
    the parts a buffer does not carry whole (texture coordinates and textures). ``unit`` is the
    millimetres one of the file's units is (the structure's ``millimetresPerUnit``), the unit
    ``display.clip.at`` is read in: 1 where the file's numbers are the millimetres drawn. ``scene_unit``
    is the millimetres one of the viewer's scene coordinates is (``millimetresPerSceneUnit``), what a
    packet's camera, Measure's points and the ink are in: the file's unit unless given (a GLB's 1, the
    viewer drawing glTF's metres as millimetres)."""
    from cadgen.engine.render.shapes import part_shapes

    buffers: dict[str, bytes] = {}
    prototypes = []
    shapes: dict[str, Any] = {}
    for index, part in enumerate(parts):
        data = part.mesh.to_bytes()
        key = f"{kind}-{index}-{hashlib.blake2b(data, digest_size=10).hexdigest()}"
        buffers[key] = data
        prototypes.append({
            "index": index, "key": key, "name": part.name, "color": None if part.color is None else list(part.color),
            "faceNames": {}, "edgeNames": {}, "vertexNames": {},
            "faceColors": {str(ordinal): list(rgba) for ordinal, rgba in sorted(part.face_colors.items())},
            "material": part.material,
            "faceMaterials": {str(ordinal): value for ordinal, value in sorted(part.face_materials.items())},
        })
        if part.uvs is not None:
            groups = {int(ordinal): tuple(rgba) for ordinal, rgba in part.face_colors.items()}
            made = part_shapes(part.mesh, groups, None, uvs=part.uvs)
            made.textures = dict(part.textures)
            shapes[key] = made
    instances = [{"prototype": item.part, "path": item.path, "matrix": _column_major(item.matrix),
                  "color": None if item.color is None else list(item.color),
                  **({} if item.palette is None else {"palette": item.palette}),
                  **({} if item.visual is None else {"visual": item.visual}),
                  **({} if item.object is None else {"object": item.object})} for item in placed]
    version = hashlib.blake2b(repr(sorted(files.items())).encode(), digest_size=8).hexdigest()
    structure = {"name": name, "path": str(path), "version": version, "units": "mm", "millimetresPerUnit": float(unit),
                 "millimetresPerSceneUnit": float(unit if scene_unit is None else scene_unit),
                 "kind": kind, "prototypes": prototypes, "instances": instances, "tree": tree}
    return Foreign(kind, Path(path), structure, buffers, shapes, files, pose, list(warnings or []))


def read(path: Path) -> Any:
    """The file at ``path`` read by its suffix's reader: a ``Foreign`` (a mesh file, a robot), or a
    ``dxf.Drawing``. Raises ``FormatError`` naming what it cannot read."""
    path = Path(path).resolve()
    suffix = path.suffix.lower()
    if suffix not in KINDS:
        raise FormatError(f"{path.name}: the stills read {', '.join(KINDS)} files, not {suffix or 'this'}")
    if not path.is_file():
        raise FormatError(f"no file {path}")
    if suffix == ".stl":
        from cadgen.engine.formats.meshes import stl_file

        return stl_file(path)
    if suffix == ".3mf":
        from cadgen.engine.formats.meshes import threemf_file

        return threemf_file(path)
    if suffix == ".glb":
        from cadgen.engine.formats.glb import glb_file

        return glb_file(path)
    if suffix in ROBOTS:
        from cadgen.engine.formats.robot import robot_file

        return robot_file(path)
    from cadgen.engine.formats.dxf import read_dxf

    return read_dxf(path)
