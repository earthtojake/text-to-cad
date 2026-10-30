"""A STEP or ``.xbf`` document as the solvers read it: its parts placed where they stand, and each face by
the engine's own refs.

The document is the engine's (``cadgen.engine.document.load``: read once and held while its file is
unchanged), and a study's refs are resolved in its structure as ``cadgen inspect`` and the CAD Viewer resolve
them (``cadgen.engine.refs``): ``bracket/face 17``, ``hand/finger.2/face 7``, an element's name
(``bracket/f:plate.relief.3``), or any of those after the document's path and ``#``. So a face a person
picks in the viewer and copies is the face a study names, and a face is numbered as the engine numbers it
(``TopExp.MapShapes``, its ``face N``). Every ref this module hands out is the canonical one (``refs.Hit.ref``):
what ``cadgen fea faces`` prints and the result names.

An occurrence here is a part where it stands in the document: its prototype's geometry moved by its instance's
placement. A part placed twice is two occurrences with the same faces, each named under its own path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    from cadgen.engine.refs import Node

__all__ = ["SUFFIXES", "Document", "Occurrence", "Selection", "face_map", "read_document"]

#: The documents a study solves: a STEP the engine reads, or an engine document.
SUFFIXES = (".step", ".stp", ".xbf")


def face_map(shape):
    """A shape's faces by the engine's ordinals (``TopExp.MapShapes``: ``face N`` is ``FindKey(N)``)."""
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher

    faces = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
    TopExp.MapShapes_s(shape, TopAbs_FACE, faces)
    return faces


def _owned(shape: Any) -> Any:
    """A copy of an OCP shape, as a build123d shape: changing it changes nothing the engine holds."""
    from build123d import Compound
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy

    copier = BRepBuilderAPI_Copy(shape, True, False)
    if not copier.IsDone() or copier.Shape().IsNull():
        raise RuntimeError("could not copy the part's geometry")
    return Compound.cast(copier.Shape())


def read_document(target: Path | str) -> "Document":
    """The document at ``target`` (``.step``, ``.stp`` or ``.xbf``), or the error that says why not."""
    path = Path(target).expanduser()
    if path.suffix.lower() == ".py":
        raise ValueError(f"{target} is a model script, not a document: run it (python {path.name}) and solve the "
                         "STEP or .xbf it writes")
    if path.suffix.lower() not in SUFFIXES:
        raise ValueError(f"this command takes a {'/'.join(SUFFIXES)} document: {target}")
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"document does not exist: {target}")
    return Document(resolved)


@dataclass(frozen=True, eq=False)
class Selection:
    """One thing a ref names: a part occurrence (``kind`` ``"occurrence"``) or one of its faces."""

    occurrence: "Occurrence"
    kind: str
    ordinal: int | None
    ref: str

    @property
    def occurrence_ref(self) -> str:
        return self.occurrence.ref

    def shape(self) -> Any:
        """The face, placed where its occurrence stands, as a build123d shape the caller owns."""
        if self.kind == "occurrence":
            return self.occurrence.shape()
        return _owned(self.occurrence.placed(self.occurrence.faces().FindKey(self.ordinal)))


@dataclass(frozen=True, eq=False)
class Occurrence(Selection):
    """A part where it stands: its node in the document's tree, its label, and its faces."""

    document: "Document" = field(default=None, repr=False)  # type: ignore[assignment]
    node: "Node" = field(default=None, repr=False)  # type: ignore[assignment]

    @property
    def label(self) -> str:
        return self.node.label

    @property
    def occurrence_ref(self) -> str:
        return self.ref

    def _prototype(self) -> Any:
        return self.document.loaded.prototypes[self.node.payload["prototype"]]

    def faces(self) -> Any:
        """The prototype's faces by ordinal, at the prototype's own placement (the identity)."""
        return self.document.faces_of(self.node.payload["prototype"])

    def placed(self, shape: Any) -> Any:
        """``shape`` (of this part's prototype) moved to where this occurrence stands."""
        from OCP.gp import gp_Trsf
        from OCP.TopLoc import TopLoc_Location

        m = self.document.loaded.instances[self.node.payload["instance"]].matrix  # 4x4, column-major
        if [round(value, 12) for value in m] == [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]:
            return shape
        trsf = gp_Trsf()
        trsf.SetValues(m[0], m[4], m[8], m[12], m[1], m[5], m[9], m[13], m[2], m[6], m[10], m[14])
        return shape.Moved(TopLoc_Location(trsf))

    def shape(self) -> Any:
        """The part placed where it stands, as a build123d shape the caller owns (a copy of the document's)."""
        result = _owned(self.placed(self._prototype().shape))
        result.label = self.label
        return result

    def face_count(self) -> int:
        return self.faces().Extent()

    def face_ref(self, ordinal: int) -> str:
        """The canonical ref of face ``ordinal``: its name where the document names it, else ``face N``."""
        return self.document.face_ref(self.node, ordinal)

    def face_refs(self) -> tuple[str, ...]:
        """Every face's canonical ref, by ordinal (index 0 is face 1)."""
        return tuple(self.face_ref(ordinal) for ordinal in range(1, self.face_count() + 1))

    def entities(self, kind: str) -> Iterator[Selection]:
        """Every face of the part, in ordinal order."""
        if kind != "face":
            raise ValueError(f"a study names faces, not {kind}s")
        for ordinal in range(1, self.face_count() + 1):
            yield Selection(self, "face", ordinal, self.face_ref(ordinal))


class Document:
    """A document read by the engine (``document.load``) with its tree of occurrences (``refs.structure_tree``)."""

    def __init__(self, path: Path) -> None:
        from cadgen.engine import document, refs
        from cadgen.engine.refs import path_text

        self.path = path
        self.loaded = document.load(path)
        self.structure = self.loaded.structure()
        self.root = refs.structure_tree(self.structure)
        self._parts = self.root.parts()
        self._one_part = len(self._parts) == 1
        # By path from the root: ``resolve_structure`` reads its own tree of the same structure, and a path names
        # the same occurrence in both.
        self._occurrences = {path_text(self.root, node): self._occurrence(node) for node in self.root.walk()}
        self._faces: dict[int, Any] = {}

    def _owner(self, node: "Node") -> str:
        from cadgen.engine.refs import owner_text

        return owner_text(self.root, node)

    def _occurrence(self, node: "Node") -> Occurrence:
        return Occurrence(None, "occurrence", None, self._owner(node), document=self, node=node)  # type: ignore[arg-type]

    def faces_of(self, prototype: int) -> Any:
        if prototype not in self._faces:
            self._faces[prototype] = face_map(self.loaded.prototypes[prototype].shape)
        return self._faces[prototype]

    def face_ref(self, node: "Node", ordinal: int) -> str:
        """``refs``' canonical ref of a part's face: under the document's one part, or the part's own owner."""
        name = self.loaded.prototypes[node.payload["prototype"]].face_names.get(ordinal)
        owner = self._owner(self.root if self._one_part else node)
        element = name or f"face {ordinal}"
        return f"{owner}/{element}" if owner else element

    @property
    def name(self) -> str:
        """The document's name: its root occurrence's canonical owner (the one part's, for a part)."""
        return self._owner(self.root) or self.loaded.name

    def leaves(self) -> list[Occurrence]:
        """Every part occurrence, in the document's order."""
        return [self._occurrences[self._path(node)] for node in self._parts]

    def _path(self, node: "Node") -> str:
        from cadgen.engine.refs import path_text

        return path_text(self.root, node)

    def resolve(self, ref: str) -> tuple[Selection, ...]:
        """What ``ref`` names (``refs.resolve_structure``), each a part occurrence or a face of one, in order.

        A ref that names an edge or a vertex, an assembly of several parts, or a face number past the part's last
        face raises ``ValueError`` saying so.
        """
        from cadgen.engine import refs
        from cadgen.engine.refs import path_text

        try:
            hits = refs.resolve_structure(self.structure, ref, self.path)
        except refs.RefError as error:
            raise ValueError(str(error)) from None
        found: list[Selection] = []
        for hit in hits:
            occurrence = self._occurrences[hit.path]
            if hit.kind is None:
                if not hit.node.part:
                    parts = [self._occurrences[path_text(hit.root, node)].ref for node in hit.node.parts()]
                    raise ValueError(f"{ref} names an assembly of {len(parts)} parts ({', '.join(parts)}); "
                                     "name one part, or one face of it")
                found.append(occurrence)
                continue
            if hit.kind != "face":
                raise ValueError(f"{ref} names a {hit.kind}; a study names faces (bracket/face 17) or parts")
            assert hit.ordinal is not None
            count = occurrence.face_count()
            if hit.ordinal > count:
                raise ValueError(f"{occurrence.ref} has no face {hit.ordinal} (it has {count})")
            found.append(Selection(occurrence, "face", hit.ordinal, hit.ref))
        return tuple(found)
