"""Exports: a document translated to a file. One writer, one document, two triggers.

``translate(document, kind, path)`` writes one
file of ``kind`` (``KINDS``: ``xbf``, ``step``, ``glb``, ``stl``, ``threemf``, ``dxf``) from a
document: a ``Source`` -- the document a build made, held in the worker's memory
(``Source.built``), or one read from an ``.xbf`` or a ``.step`` (``Source.read``), or a mesh
file's triangles (``.glb``, ``.stl``, ``.3mf``: ``export/mesh_file.py``). A
derived file a decorator declares and a file ``cadgen export`` asks for are the same
call, so the same document writes the same bytes.

The file holds the document as its code built it: every part, placed where the document
places it, in its colours, with its motion. No translation selects a part or a state: a
posed or partial file is a function in the model's code. A mesh file is a source of the other
two mesh kinds, holding what its format carries (``README``, **Translation formats**), and of
nothing else: there is no B-rep in it, so no xbf, STEP or DXF; nor is a mesh file written from one
of its own kind. An xbf is written from a STEP (read into a document first); an xbf is
never written from another, which already is the document. A GLB carries every configuration sequence the document defines as a glTF
animation of the same name, baked by forward kinematics (``export/motion.py``), and every
``animation()`` its code made (``export/animation.py``), from a build's tree or from the record of
them the xbf carries, so a GLB exported from the xbf is the build's own. STEP, STL and 3MF ignore both. A
DXF is drawn from a planar document alone (``export/dxf.py``): a 3D one is refused.

Every file is written to a temporary file beside its target and moved over it; a DXF only
when its bytes change.

Importing this package imports no kernel: a kind's writer loads on its first use.
"""

from __future__ import annotations

import importlib
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from cadgen.engine.atomic_replace import replace_atomic, staging

__all__ = ["KINDS", "ExportRefused", "Kind", "Source", "View", "kind_of", "refused", "translate"]


class ExportRefused(ValueError):
    """An export the engine will not write, said by name before anything is written."""


@dataclass(frozen=True)
class Kind:
    """One file kind: its name, the suffixes its files end in (the first is its own), the
    writer (``module:function``, loaded on first use: ``write(view, path)``), and whether
    the kind is written atomically here (an xbf saves itself atomically)."""

    name: str
    suffixes: tuple[str, ...]
    writer: str
    atomic: bool = True

    @property
    def suffix(self) -> str:
        return self.suffixes[0]

    def write(self, view: "View", path: Path) -> None:
        module, _sep, function = self.writer.partition(":")
        getattr(importlib.import_module(module), function)(view, path)


KINDS: dict[str, Kind] = {
    "xbf": Kind("xbf", (".xbf",), "cadgen.engine.export.tree:write_xbf", atomic=False),
    "step": Kind("step", (".step", ".stp"), "cadgen.engine.export.step:write"),
    "glb": Kind("glb", (".glb",), "cadgen.engine.export.glb:write"),
    "stl": Kind("stl", (".stl",), "cadgen.engine.export.stl:write"),
    "threemf": Kind("threemf", (".3mf",), "cadgen.engine.export.threemf:write"),
    # A drawing replaces its file itself, and only when its bytes change.
    "dxf": Kind("dxf", (".dxf",), "cadgen.engine.export.dxf:write", atomic=False),
}
# What a source file is read as: a document, or a mesh file's triangles.
SOURCES = (".xbf", ".step", ".stp")
MESHES = (".glb", ".stl", ".3mf")
# A kind's name in a sentence.
LABELS = {"xbf": "xbf", "step": "STEP", "glb": "GLB", "stl": "STL", "threemf": "3MF", "dxf": "DXF"}
# The date of every entry of a zip the package writes (a 3MF): a file is a function of
# what it holds, never of the clock it was written by (zipfile stamps each entry with the time).
ZIP_DATE = (1980, 1, 1, 0, 0, 0)


def refused(source: Any, destination: Any) -> str | None:
    """Why the file at ``source`` (a path) is never translated to ``destination``, by their
    suffixes alone, or None: a mesh holds no B-rep, so no xbf, STEP or DXF is made from one, and
    a mesh file is not written from one of its own kind."""
    source, kind = Path(source), kind_of(destination)
    if source.suffix.lower() not in MESHES:
        return None
    if kind in ("xbf", "step", "dxf"):
        return f"{source.name} is a mesh: it has no B-rep, and no {LABELS[kind]} export is made from one"
    if kind == kind_of(source):
        article = "an" if kind == "stl" else "a"
        return f"{article} {LABELS[kind]} is not written from another {LABELS[kind]}: the file already is one"
    return None


def kind_of(path: Any) -> str:
    """The kind a destination's suffix names; an unknown suffix is refused by name."""
    suffix = Path(path).suffix.lower()
    for kind in KINDS.values():
        if suffix in kind.suffixes:
            return kind.name
    known = ", ".join(suffix for kind in KINDS.values() for suffix in kind.suffixes)
    raise ExportRefused(f"{Path(path).name}: an export is one of {known}")


# --- a document to translate ---------------------------------------------------------------


class Source:
    """A document to translate: its structure (``document.Loaded.structure``'s shape: the
    prototypes with names, colours, materials and element names, the instances with world
    matrices, the tree, the mechanism as ``kinematics``), each part's shape by its key, the
    XCAF document when one is held, each assembly occurrence's placement, and the
    mechanism itself. ``live`` shapes are a build's (written and read once to be meshed,
    as saving their document does: ``mesh.shape_bytes``); the others were read from a file
    and are meshed from their bytes as read. A mesh file's source (``mesh``: its kind) has no
    shapes: each part's mesh is held as the file has it (``meshes``, by key)."""

    def __init__(self, structure: dict[str, Any], shapes: dict[str, Any], *, live: bool, xcaf: Any = None,
                 world: Callable[[tuple[int, ...]], Any] | None = None, mechanism: Any = None,
                 foreign: bool = False, path: Path | None = None, animations: Any = None,
                 meshes: dict[str, Any] | None = None, mesh: str | None = None) -> None:
        self.structure = structure
        self.shapes = shapes
        self.live = live
        self.xcaf = xcaf
        self._world = world
        self.mechanism = mechanism
        # The animations the build's code made (``animations.harvest``): a built source's from its
        # tree, a read one's from the document's record of them (``document.Loaded.animations``). A
        # GLB bakes them (``export/animation.py``); no other export reads them.
        self.animations = animations
        # A document this engine did not write (a foreign STEP): its keys are its reader's,
        # made again from the geometry before an xbf holds them.
        self.foreign = foreign
        self.path = path
        self.meshes = meshes
        self.mesh = mesh
        self._bytes: dict[str, bytes] = {}
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return self.structure["name"]

    @classmethod
    def read(cls, path: Any) -> "Source":
        """A document read from its file (``document.load``: held while the file stays as it
        was): an ``.xbf``, or a ``.step``/``.stp`` read into a document first; or a mesh file's
        triangles (``mesh_file.read``: no kernel)."""
        path = Path(path)
        suffix = path.suffix.lower()
        if suffix in MESHES:
            from cadgen.engine.export.mesh_file import read

            return read(path)
        if suffix not in SOURCES:
            raise ExportRefused(f"{path.name} is no document: an export reads an .xbf, a .step or a mesh "
                                f"({', '.join(MESHES)})")
        from cadgen.engine import document

        if not path.is_file():
            raise ExportRefused(f"no document {path}")
        loaded = document.load(path)
        return cls(loaded.structure(), {p.key: p.shape for p in loaded.prototypes}, live=False, xcaf=loaded.doc,
                   world=lambda occurrence: loaded.worlds.get(occurrence), mechanism=loaded.mechanism,
                   foreign=loaded.writer is None, path=loaded.path, animations=loaded.animations)

    @classmethod
    def built(cls, doc: Any, tree: Any, path: Path | None) -> "Source":
        """The document a build made, in memory: its XCAF document and the tree it was
        made from; ``path`` the xbf it was saved as, if any (its version)."""
        from cadgen.engine import mechanism as kinematics

        structure = structure_of(tree, path)
        shapes: dict[str, Any] = {}
        for part in tree.parts:
            shapes.setdefault(part.key, part.shape)
        return cls(structure, shapes, live=True, xcaf=doc,
                   world=lambda occurrence: kinematics._occurrence(tree, occurrence)[0],
                   mechanism=tree.mechanism, path=None if path is None else Path(path),
                   animations=getattr(tree, "animations", None))

    def world(self, occurrence: tuple[int, ...]) -> Any:
        """An occurrence's placement as built, a 4x4 matrix (numpy), or None."""
        import numpy as np

        from cadgen.engine.mechanism import _numpy

        if self._world is None:
            return None
        found = self._world(tuple(occurrence))
        return None if found is None else np.asarray(_numpy(found), dtype=float)

    def shape_data(self, key: str) -> bytes:
        """A part's shape bytes, the canonical form it is meshed from (``mesh.shape_bytes``)."""
        with self._lock:
            found = self._bytes.get(key)
        if found is None:
            from cadgen.engine.mesh import shape_bytes

            shape = self.shapes[key]
            found = bytes(shape) if isinstance(shape, (bytes, bytearray)) else shape_bytes(shape, read=not self.live)
            with self._lock:
                self._bytes[key] = found
        return found

    def view(self) -> "View":
        return View.of(self)

    def shape(self) -> Any:
        """The document as a build123d compound tree: an assembly node a ``Compound`` of its
        components, a part a shape of its own on the prototype's geometry, placed where the
        document places it, labelled, coloured and given its material."""
        import numpy as np
        from build123d import Compound, Location
        from build123d.importers import topods_lut
        from build123d.topology.shape_core import downcast
        from OCP.gp import gp_Trsf
        from OCP.TopLoc import TopLoc_Location

        from cadgen.engine.colors import color as as_color
        from cadgen.engine.export.tree import _material
        from cadgen.engine.mesh import read_shape

        instances = self.structure["instances"]

        def node(tree: dict[str, Any]) -> Any:
            if "children" in tree:
                return Compound(children=[node(child) for child in tree["children"]], label=tree["name"])
            prototype = self.structure["prototypes"][tree["prototype"]]
            instance = instances[tree["instance"]]
            shape = self.shapes[prototype["key"]]
            topods = downcast(read_shape(shape) if isinstance(shape, (bytes, bytearray)) else shape)
            made = topods_lut[type(topods)](topods)
            made.label = tree["name"]
            rgba = instance.get("color") or prototype.get("color")
            made.color = as_color(rgba) if rgba else None
            material = _material(prototype.get("material"))
            if material is not None:
                made.material = material
            matrix = np.array(instance["matrix"], dtype=float).reshape(4, 4).T
            trsf = gp_Trsf()
            trsf.SetValues(*(float(matrix[row, column]) for row in range(3) for column in range(4)))
            made.move(Location(TopLoc_Location(trsf)))
            return made

        return node(self.structure["tree"])


_STRUCTURES: dict[int, tuple[Any, Any, dict[str, Any]]] = {}


def structure_of(tree: Any, path: Path | None) -> dict[str, Any]:
    """The structure of a build's tree (``document.tree_structure``), made once per tree
    and path: the worker's patch and the build's exports share it."""
    from cadgen.engine import document

    held = _STRUCTURES.get(id(tree))
    if held is not None and held[0] is tree and held[1] == path:
        return held[2]
    found = document.tree_structure(tree, Path(path) if path is not None else None)
    _STRUCTURES.clear()  # one build's tree at a time
    _STRUCTURES[id(tree)] = (tree, path, found)
    return found


# --- what a translation writes ---------------------------------------------------------------


@dataclass
class Placed:
    """One placed part: the prototype's index in the structure, its world matrix (4x4,
    numpy, row-major), its names from the root down, its instance's own colour, and its
    instance's index in the structure."""

    prototype: int
    matrix: Any
    path: list[str]
    color: tuple | None
    instance: int = -1


@dataclass
class View:
    """A document as one translation writes it: as it is. ``tree`` is the structure's tree
    (its nodes' ``instance`` indices the structure's)."""

    source: Source
    name: str
    placements: list[Placed]
    tree: dict[str, Any]
    matrices: list[Any]  # every instance's world matrix, by instance index

    @property
    def prototypes(self) -> list[dict[str, Any]]:
        return self.source.structure["prototypes"]

    def used(self) -> list[int]:
        """The prototypes the view places, each once, in the order first placed."""
        found: dict[int, None] = {}
        for placed in self.placements:
            found.setdefault(placed.prototype, None)
        return list(found)

    @classmethod
    def of(cls, source: Source) -> "View":
        import numpy as np

        structure = source.structure
        instances = structure["instances"]
        matrices = [np.array(instance["matrix"], dtype=float).reshape(4, 4).T for instance in instances]
        tree = structure["tree"]
        placements = []
        for index in _instances(tree):
            instance = instances[index]
            placements.append(Placed(instance["prototype"], matrices[index], instance["path"].split("/"),
                                     tuple(instance["color"]) if instance.get("color") else None, index))
        return cls(source, structure["name"], placements, tree, matrices)


def _instances(node: dict[str, Any]) -> list[int]:
    if "children" not in node:
        return [node["instance"]]
    return [index for child in node["children"] for index in _instances(child)]


# --- the one call ------------------------------------------------------------------------------


def translate(document: Any, kind: str | None, path: Any) -> int:
    """Write ``document`` (a ``Source``, or the path of an ``.xbf``/``.step`` or a mesh file) to ``path``
    as ``kind`` (from the suffix when None); returns the file's size."""
    path = Path(path)
    kind = kind or kind_of(path)
    if kind not in KINDS:
        raise ExportRefused(f"no export {kind!r}; the kinds are {', '.join(KINDS)}")
    if path.suffix.lower() not in KINDS[kind].suffixes:
        raise ExportRefused(f"{path.name}: a {kind} export ends in {' or '.join(KINDS[kind].suffixes)}")
    if not isinstance(document, Source):
        why = refused(document, path)
        if why:
            raise ExportRefused(why)
    source = document if isinstance(document, Source) else Source.read(document)
    why = refused(source.path, path) if source.mesh and source.path is not None else None
    if why:
        raise ExportRefused(why)
    if kind == "xbf" and not source.foreign and source.path is not None and source.path.suffix.lower() == ".xbf":
        raise ExportRefused("an xbf is not written from another xbf: the document already is one")
    view = source.view()
    path.parent.mkdir(parents=True, exist_ok=True)
    spec = KINDS[kind]
    if not spec.atomic:
        spec.write(view, path)
        return path.stat().st_size
    with staging(path) as temporary:
        spec.write(view, temporary)
        size = temporary.stat().st_size
        replace_atomic(temporary, path)
    return size
