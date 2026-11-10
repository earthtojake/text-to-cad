"""Exact geometry for the manufacturing checks: a document's parts, their faces and edges, read and measured
on the B-rep (OCP), never on a mesh.

**The parts.** A STEP or an xbf is read by the engine's own loader (``cad.engine.document.Loaded``), so a
part, its faces and their ordinals are the ones ``cad <type> inspect`` names: a finding's location is a ref
in its grammar (``plate/face 7``; ``bracket/face 3`` in a document of one part, under its name), which
``cad xbf inspect DOC REF`` resolves to the very face. A check the engine runs is measured in one of its
checks processes (``of_source``): a STEP's or an xbf's file, or the bytes of a document the engine holds (a
model's), each as its reader read it -- nothing exported or written. A live shape
(``cad.build123d.cnc(shape)``) is read by its labels, as the engine would name its document.

**Every occurrence as it stands.** A part used several times is one ``Part`` for each way it stands
(``_Standing``): the occurrences turned alike -- moved apart, never turned against each other -- are one
``Part``, placed where the first of them stands, the others counted (``occurrences``), named (``paths``) and
placed (``placements``: how far each lies from the first); an occurrence turned another way is a ``Part`` of
its own, at its own refs, measured as it stands. So what depends on how a part stands -- a print's overhangs,
a molding's draft against the pull -- is judged for every occurrence, what does not is measured once per
geometry by the processes that read it so (``copies``), and a total counts ``occurrences``
(``Document.facts``); a print, whose parts stand among each other on one plate, measures every occurrence
where it stands (``every_occurrence``). A live shape's leaves that share one geometry are read the same way (``parts_of``).

**Never the held shapes themselves.** A check meshes faces (``BRepMesh``), which writes a triangulation
into the shape it meshes: on the document the engine holds, the next check would find the last one's
mesh (a finer one is kept, not made again) and measure otherwise than a fresh read does. So each part is
measured on a copy that shares nothing with the held document: its geometry and whatever mesh it was read
with (``BRepBuilderAPI_Copy``), so a second process checked finds the document as it was read.

**The measures.** A face's surface (``surface``: a plane's normal, a cylinder's or a cone's axis and
radius, which way the material lies); an edge between two faces (``edges``: concave or convex, the angle
inside the material, smooth where the faces are tangent); exact rays (``Rays``: the first hit, or every
crossing of a line); points sampled on a face with their outward normals (``samples``); the wall
thickness under a point (``Rays.thickness``); a point's place inside or outside a solid (``inside``).
Lengths are millimetres, angles degrees.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from cad._internal.dfm import Unmeasured

__all__ = ["Document", "Edge", "Part", "Rays", "Sample", "Surface", "edges", "inside", "of_source", "parts_of", "read",
           "samples", "surface"]

# Two faces meeting at an edge within this many degrees of each other are tangent: a fillet's join.
SMOOTH_DEG = 1.0
#: A line passes a face along it -- a tangent touch, no crossing -- where its direction lies within this of
#: the surface's plane there (the cosine of its angle to the normal: about 6e-5 degrees).
TANGENT = 1e-6


@dataclass
class Part:
    """One part of a document as it stands one way: its geometry placed where the first occurrence that stands
    so does, its canonical owner (the ref's text before ``/face N``) and its faces in their ordinals' order
    (1-based). ``occurrences`` counts the occurrences that stand so (turned alike, moved apart), ``paths``
    names each and ``placements`` says how far each lies from the first (millimetres; the first's is zero)."""

    name: str
    owner: str
    shape: Any                       # a build123d Shape, placed
    occurrences: int = 1
    paths: tuple[str, ...] = ()
    placements: tuple[tuple[float, float, float], ...] = ((0.0, 0.0, 0.0),)
    face_names: dict[int, str] = field(default_factory=dict)
    material: Any = None             # the part's declared material (a bd_materials FinishedMaterial), or None
    _faces: list[Any] | None = field(default=None, repr=False)
    _edges: list[Any] | None = field(default=None, repr=False)
    _face_map: Any = field(default=None, repr=False)
    _edge_map: Any = field(default=None, repr=False)
    # Each edge's kernel adaptors for ``edge_angles``, made once: a curved edge's least angle is searched with
    # dozens of calls, each of which walked the face's every edge and copied both surfaces' adaptors again.
    _edge_context: dict[int, Any] = field(default_factory=dict, repr=False)

    def ref(self, kind: str, ordinal: int) -> str:
        """The ref of one element: ``plate/face 7`` (``face 7`` where the part is an unlabelled root)."""
        element = f"{kind} {ordinal}"
        return f"{self.owner}/{element}" if self.owner else element

    def _maps(self) -> None:
        if self._face_map is not None:
            return
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
        from OCP.TopExp import TopExp
        from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape

        faces, edges = TopTools_IndexedMapOfShape(), TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(self.shape.wrapped, TopAbs_FACE, faces)
        TopExp.MapShapes_s(self.shape.wrapped, TopAbs_EDGE, edges)
        self._face_map, self._edge_map = faces, edges

    def faces(self) -> list[Any]:
        """Its faces as build123d ``Face``s, ``faces()[n - 1]`` the face ``face n`` names."""
        if self._faces is None:
            import build123d as bd
            from OCP.TopoDS import TopoDS

            self._maps()
            self._faces = [bd.Face(TopoDS.Face(self._face_map.FindKey(index)))
                           for index in range(1, self._face_map.Extent() + 1)]
        return self._faces

    def edges(self) -> list[Any]:
        """Its edges as build123d ``Edge``s, ``edges()[n - 1]`` the edge ``edge n`` names."""
        if self._edges is None:
            import build123d as bd
            from OCP.TopoDS import TopoDS

            self._maps()
            self._edges = [bd.Edge(TopoDS.Edge(self._edge_map.FindKey(index)))
                           for index in range(1, self._edge_map.Extent() + 1)]
        return self._edges

    def face_ordinal(self, face: Any) -> int:
        """The ordinal of a face of this part (a build123d ``Face`` or a ``TopoDS_Face``), 0 for none."""
        self._maps()
        return int(self._face_map.FindIndex(getattr(face, "wrapped", face)))

    def edge_ordinal(self, edge: Any) -> int:
        self._maps()
        return int(self._edge_map.FindIndex(getattr(edge, "wrapped", edge)))

    def solids(self) -> list[Any]:
        return list(self.shape.solids())

    def facts(self) -> dict[str, Any]:
        """What a report says of the part itself: its name, its ref's owner, its declared material and the
        process it declares (its route: ``machined``, ``fdm``), its box, volume and counts."""
        from cad._internal.dfm import materials, processes

        box = self.shape.bounding_box()
        declared = getattr(self.material, "name", None)
        return {"name": self.name, "owner": self.owner, "occurrences": self.occurrences,
                "paths": list(self.paths), "placements_mm": [rounded(shift, 4) for shift in self.placements],
                "material": str(declared) if declared else None, "material_table": materials.declared(self.material),
                "process": processes.route(getattr(self.material, "process", None)),
                "bbox_mm": [round(box.size.X, 4), round(box.size.Y, 4), round(box.size.Z, 4)],
                "bbox_min_mm": [round(box.min.X, 4), round(box.min.Y, 4), round(box.min.Z, 4)],
                "volume_mm3": round(float(self.shape.volume), 4), "area_mm2": round(float(self.shape.area), 4),
                "solid_count": len(self.solids()), "face_count": len(self.faces()),
                "edge_count": len(self.edges())}


@dataclass
class Document:
    """A document's parts, as the engine reads it."""

    name: str
    parts: list[Part]
    source: str | None = None
    #: The owners of parts that hold no face (an empty label a STEP's exporter left): never measured.
    empty: list[str] = field(default_factory=list)

    def facts(self) -> dict[str, Any]:
        """What a report says of the whole document: ``part_count`` the parts measured (one for each way a
        geometry stands), and its totals over every occurrence -- ``occurrence_count``, ``solid_count``,
        ``volume_mm3``: a part used four times is four parts' material."""
        return {"name": self.name, "part_count": len(self.parts),
                "occurrence_count": sum(part.occurrences for part in self.parts),
                "solid_count": sum(part.occurrences * len(part.solids()) for part in self.parts),
                "volume_mm3": round(sum(part.occurrences * float(part.shape.volume) for part in self.parts), 4),
                "units": "mm", "empty_parts": list(self.empty)}


# --- reading ---------------------------------------------------------------------------------------------


def _trsf(matrix: list[float]) -> Any:
    """A column-major 4x4 matrix (``Instance.matrix``) as a ``TopLoc_Location``."""
    from OCP.gp import gp_Trsf
    from OCP.TopLoc import TopLoc_Location

    m = [[matrix[column * 4 + row] for column in range(4)] for row in range(4)]
    trsf = gp_Trsf()
    trsf.SetValues(m[0][0], m[0][1], m[0][2], m[0][3], m[1][0], m[1][1], m[1][2], m[1][3],
                   m[2][0], m[2][1], m[2][2], m[2][3])
    return TopLoc_Location(trsf)


def _copied(shape: Any) -> Any:
    """A read part's shape to measure: its geometry and the mesh it was read with, sharing nothing with
    the document the engine holds (the module's **Never the held shapes themselves**)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy

    return BRepBuilderAPI_Copy(shape, True, True).Shape()


#: Two occurrences stand alike when their rotations agree to this, entry for entry (about 6e-8 degrees): any
#: more and the second is measured as it stands -- an occurrence tilted a twentieth of a degree is another.
SAME_ORIENTATION = 1e-9


def _placement(matrix: Any) -> tuple[np.ndarray, np.ndarray]:
    """The rotation (3 x 3, any mirror or scale with it) and the shift of a column-major 4x4 matrix
    (``Instance.matrix``)."""
    m = np.asarray(matrix, dtype=float).reshape(4, 4).T
    return m[:3, :3].copy(), m[:3, 3].copy()


def _placement_of(shape: Any) -> tuple[np.ndarray, np.ndarray]:
    """The rotation and the shift a ``TopoDS_Shape`` is placed by (its location's)."""
    trsf = shape.Location().Transformation()
    return (np.array([[trsf.Value(row, column) for column in (1, 2, 3)] for row in (1, 2, 3)]),
            np.array([trsf.Value(row, 4) for row in (1, 2, 3)]))


class _Standing:
    """A document's parts as they stand (the module's **Every occurrence as it stands**): one ``Part`` for each
    way a geometry stands, in the order their first occurrences come."""

    def __init__(self) -> None:
        self.parts: list[Part] = []
        self._stood: dict[Any, list[tuple[np.ndarray, np.ndarray, Part]]] = {}

    def add(self, geometry: Any, rotation: np.ndarray, shift: np.ndarray, path: str, make: Any) -> None:
        """One occurrence of ``geometry`` (a key its occurrences share), placed by ``rotation`` and ``shift``:
        counted on the part that stands so already, else a part of its own (``make()``)."""
        for stood, first, part in self._stood.get(geometry, ()):
            if np.allclose(rotation, stood, rtol=0.0, atol=SAME_ORIENTATION):
                part.occurrences += 1
                part.paths += (path,)
                part.placements += (tuple(float(v) for v in shift - first),)
                return
        part = make()
        self._stood.setdefault(geometry, []).append((rotation, shift, part))
        self.parts.append(part)

    def document(self, name: str, source: str | None = None) -> Document:
        empty = [part.owner or part.name for part in self.parts if not part.faces()]
        return Document(name=name, parts=[part for part in self.parts if part.faces()], source=source, empty=empty)


def _loaded(loaded: Any, copy: bool = False) -> Document:
    import build123d as bd

    from cad.engine import refs

    structure = loaded.structure()
    root = refs.structure_tree(structure)
    standing = _Standing()
    for node in root.parts():
        payload = node.payload
        prototype = int(payload["prototype"])
        path = refs.path_text(root, node)
        proto = loaded.prototypes[prototype]
        instance = loaded.instances[int(payload["instance"])]

        def make(proto: Any = proto, instance: Any = instance, node: Any = node, path: str = path) -> Part:
            placed = bd.Shape.cast((_copied(proto.shape) if copy else proto.shape).Moved(_trsf(instance.matrix)))
            return Part(name=proto.name, owner=refs.owner_text(root, node), shape=placed, paths=(path,),
                        face_names=dict(proto.face_names), material=getattr(proto, "material", None))

        standing.add(prototype, *_placement(instance.matrix), path, make)
    return standing.document(loaded.name, str(loaded.path))


def read(document_type: str, source: Any) -> Document:
    """The parts of a STEP or an xbf read in this process (a path), as the engine's loader reads it --
    a check's path where no engine can be reached; a check through the engine reads the document the
    engine holds instead (``of_source``). ``Unmeasured`` for one that does not read."""
    from cad.engine.document import Loaded

    path = Path(os.fspath(source)).expanduser().resolve()
    try:
        return _loaded(Loaded(path))
    except Exception as error:  # noqa: BLE001 - a file that does not read is the check's answer
        raise Unmeasured("document_unreadable", f"failed to read {path.name}: {error}") from None


def of_source(source: Any) -> Document:
    """The parts of a document one of the engine's checks processes holds (an ``export.Source`` its reader
    read: a STEP's or an xbf's file, a held document's bytes), as that reader read it (``source.loaded``), which
    is what ``read`` reads -- each part a copy, never the held shapes themselves (the module's docstring).
    ``Unmeasured`` for a source no reader read: a mesh, which holds no B-rep."""
    if source.loaded is None:
        raise Unmeasured("document_unreadable", f"{source.name} holds no B-rep to measure")
    return _loaded(source.loaded, copy=True)


def parts_of(shape: Any, name: str | None = None) -> Document:
    """A live build123d shape's parts, read by its labels as the engine would name its document: each leaf
    of its compound tree a part, placed where it stands -- and, as a document's occurrences are, the leaves
    that share one geometry (one shape placed several times, ``Pos(...) * part``) and one material one part
    for each way they stand, the rest counted (``_Standing``)."""
    import build123d as bd

    from cad.engine import refs

    leaves: list[tuple[Any, Any]] = []

    def visit(node: Any) -> dict[str, Any]:
        children = list(getattr(node, "children", ()) or ())
        entry: dict[str, Any] = {"name": str(getattr(node, "label", "") or "")}
        if children:
            entry["children"] = [visit(child) for child in children]
        else:
            entry["prototype"] = len(leaves)
            leaves.append((node, getattr(node, "global_location", None)))
        return entry

    tree = visit(shape)
    if not tree["name"]:
        tree["name"] = name or ""
    root = refs.structure_tree({"tree": tree})
    standing = _Standing()
    shared: list[tuple[Any, Any]] = []  # each geometry seen, with its material: a leaf's key is its index
    for node in root.parts():
        leaf, where = leaves[int(node.payload["prototype"])]
        placed = leaf if where is None or node is root else bd.Shape.cast(leaf.wrapped.Located(where.wrapped))
        material = getattr(leaf, "material", None)
        geometry = next((index for index, (other, its) in enumerate(shared)
                         if its is material and placed.wrapped.IsPartner(other)), len(shared))
        if geometry == len(shared):
            shared.append((placed.wrapped, material))
        path = refs.path_text(root, node)

        def make(placed: Any = placed, node: Any = node, path: str = path, material: Any = material) -> Part:
            return Part(name=node.label, owner=refs.owner_text(root, node), shape=placed, paths=(path,),
                        material=material)

        standing.add(geometry, *_placement_of(placed.wrapped), path, make)
    return standing.document(tree["name"])


def every_occurrence(document: Document) -> Document:
    """``document`` with a part for every occurrence, each placed where it stands and named by its own path
    (which is its ref's owner): for a process whose measures depend on where the parts stand among each other
    and on the plate -- a print's clearances, its support, its bed, its build volume -- which the occurrences
    turned alike do not share. The first occurrence is the part itself; each other its shape moved, sharing
    its geometry."""
    import dataclasses

    import build123d as bd
    from OCP.gp import gp_Trsf, gp_Vec
    from OCP.TopLoc import TopLoc_Location

    parts: list[Part] = []
    for part in document.parts:
        if part.occurrences == 1:
            parts.append(part)
            continue
        for index, (path, shift) in enumerate(zip(part.paths, part.placements)):
            if index == 0:
                parts.append(dataclasses.replace(part, occurrences=1, paths=(path,), placements=((0.0, 0.0, 0.0),)))
                continue
            trsf = gp_Trsf()
            trsf.SetTranslation(gp_Vec(*(float(value) for value in shift)))
            moved = bd.Shape.cast(part.shape.wrapped.Moved(TopLoc_Location(trsf)))
            parts.append(Part(name=part.name, owner=path, shape=moved, paths=(path,),
                              face_names=dict(part.face_names), material=part.material))
    return Document(name=document.name, parts=parts, source=document.source, empty=list(document.empty))


# --- copies ----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Copy:
    """A part that is another's geometry moved: ``of`` the index of the first part with that geometry, and the
    motion that takes a point of that part onto this one (``rotation @ point + shift``; ``proper`` False where it
    mirrors). Their faces, edges and vertices correspond ordinal for ordinal."""

    of: int
    rotation: np.ndarray
    shift: np.ndarray
    proper: bool

    def point(self, xyz: Any) -> list[float]:
        return [float(v) for v in self.rotation @ np.asarray(xyz, dtype=float) + self.shift]

    def direction(self, xyz: Any) -> list[float]:
        return [float(v) for v in self.rotation @ np.asarray(xyz, dtype=float)]


def _signature(part: Part) -> tuple[Any, ...]:
    """What a part's copies share, read cheaply: its counts, and each face's kind and edge count in order."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer

    kinds = []
    for face in part.faces():
        explorer, edges = TopExp_Explorer(face.wrapped, TopAbs_EDGE), 0
        while explorer.More():
            edges += 1
            explorer.Next()
        kinds.append((int(BRepAdaptor_Surface(face.wrapped, False).GetType()), edges))
    return (len(part.solids()), len(part.edges()), tuple(kinds))


#: Where along each edge's and each face's parameters a probe stands (``_probes``): its middle and its quarters,
#: so two curves that share their ends and middles -- a Bezier's middle poles moved symmetrically -- differ.
PROBE_AT = (0.25, 0.5, 0.75)


def _probes(part: Part) -> np.ndarray:
    """Points a part's moved copy has moved alike, ordinal for ordinal: every vertex, each edge at its middle and
    quarters, and each face's surface at the middle and quarters of its parameters (both ways)."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.TopAbs import TopAbs_VERTEX
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape

    vertices = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(part.shape.wrapped, TopAbs_VERTEX, vertices)
    points = [_xyz(BRep_Tool.Pnt_s(TopoDS.Vertex(vertices.FindKey(i)))) for i in range(1, vertices.Extent() + 1)]
    for edge in part.edges():
        if BRep_Tool.Degenerated_s(edge.wrapped):
            continue
        curve = BRepAdaptor_Curve(edge.wrapped)
        a, b = curve.FirstParameter(), curve.LastParameter()
        points += [_xyz(curve.Value(a + f * (b - a))) for f in PROBE_AT]
    for face in part.faces():
        surface = BRepAdaptor_Surface(face.wrapped)
        u0, u1 = surface.FirstUParameter(), surface.LastUParameter()
        v0, v1 = surface.FirstVParameter(), surface.LastVParameter()
        points += [_xyz(surface.Value(u0 + f * (u1 - u0), v0 + g * (v1 - v0))) for f in PROBE_AT for g in PROBE_AT]
    return np.array(points).reshape(-1, 3)


#: The fields of a report's items that name the part an item is of (``moved``).
NAMED = frozenset({"part", "name"})


def moved(value: Any, copy: Copy, first: Part, part: Part, places: frozenset[str], directions: frozenset[str],
          key: str | None = None) -> Any:
    """``value`` -- a report's item, or what it holds, of ``first``, the part ``copy`` is of -- as it lies in
    ``part``, the copy: the refs at the first's owner at the copy's, its name (under a key of ``NAMED``) the
    copy's, the points under a key of ``places`` and the vectors under one of ``directions`` moved (at any depth:
    a list of points, of lines), the rest as it is. Keys starting ``_`` are a measurement's own and kept."""
    if isinstance(value, dict):
        return {name: (found if name.startswith("_") else moved(found, copy, first, part, places, directions, name))
                for name, found in value.items()}
    if isinstance(value, str):
        was = f"{first.owner}/"
        if value.startswith(was):
            return f"{part.owner}/" + value[len(was):]
        return part.name if key in NAMED and value == first.name else value
    if key in places or key in directions:
        if isinstance(value, (list, tuple)) and len(value) == 3 and all(isinstance(v, (int, float)) for v in value):
            return rounded(copy.point(value) if key in places else copy.direction(value), 4 if key in places else 6)
    if isinstance(value, (list, tuple)):
        return [moved(found, copy, first, part, places, directions, key) for found in value]
    return value


#: A copy's probes lie within this share of its size of the first's moved (the kernel's own precision is 1e-7).
COPY_TOLERANCE = 1e-7
#: A copy's volume and area are its first's within this share (the kernel's integration of a moved shape).
COPY_MEASURES = 1e-6


def copies(parts: list[Part], mirrored: bool = True) -> dict[int, Copy]:
    """The parts that are an earlier part's geometry moved -- turned and shifted, mirrored too where
    ``mirrored`` -- by their index: what a check measures once and says at every copy. A part is a copy when its
    counts and faces' kinds match and every probe (``_probes``: its vertices, edges' and faces' middles, ordinal
    for ordinal) lies where the first's moved (the best rigid motion of the probes, ``COPY_TOLERANCE`` of the
    size), and its volume and area are the first's (``COPY_MEASURES``): the same geometry, moved, its faces in the
    same order. Probes that lie in one plane leave a turn and its mirror alike: such a part is no copy. Instances of
    one shape are one part already."""
    groups: dict[tuple[Any, ...], list[int]] = {}
    for index, part in enumerate(parts):
        try:
            groups.setdefault(_signature(part), []).append(index)
        except Exception:  # noqa: BLE001 - a part the kernel cannot read so is measured on its own
            continue
    found: dict[int, Copy] = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        firsts: list[tuple[int, np.ndarray, tuple[float, float]]] = []
        for index in members:
            try:
                probes = _probes(parts[index])
                shape = parts[index].shape
                measures = (float(shape.volume), float(shape.area))
            except Exception:  # noqa: BLE001
                continue
            for first, theirs, sizes in firsts:
                # its volume and area its first's too: a copy is the same geometry, not one that shares its probes
                if any(abs(m - n) > COPY_MEASURES * max(abs(n), 1e-9) for m, n in zip(measures, sizes)):
                    continue
                copy = _moved(theirs, probes, mirrored)
                if copy is not None:
                    found[index] = Copy(first, *copy)
                    break
            else:
                firsts.append((index, probes, measures))
    return found


def _moved(a: np.ndarray, b: np.ndarray, mirrored: bool) -> tuple[np.ndarray, np.ndarray, bool] | None:
    """The rigid motion taking the points ``a`` onto ``b`` (ordinal for ordinal), or None where none does."""
    if a.shape != b.shape or len(a) < 3:
        return None
    ca, cb = a.mean(axis=0), b.mean(axis=0)
    spread = np.linalg.svd(a - ca, compute_uv=False)
    if spread[-1] <= 1e-9 * max(float(spread[0]), 1e-300):
        return None  # probes in one plane (or line): a turn and its mirror fit alike, so which it is is unknown
    u, _, vt = np.linalg.svd((a - ca).T @ (b - cb))
    proper = float(np.linalg.det(vt.T @ u.T)) > 0.0
    if not proper and not mirrored:
        return None
    rotation = vt.T @ np.diag([1.0, 1.0, 1.0 if proper else -1.0]) @ u.T
    shift = cb - rotation @ ca
    size = float(np.ptp(a, axis=0).max()) or 1.0
    if float(np.abs(a @ rotation.T + shift - b).max()) > COPY_TOLERANCE * max(size, 1.0):
        return None
    return rotation, shift, proper


# --- surfaces --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Surface:
    """A face's surface. ``kind``: plane, cylinder, cone, sphere, torus, bspline, revolution, extrusion,
    offset or other. A plane's ``normal`` is the outward one (the face's orientation applied); a
    cylinder's, cone's, sphere's or torus's ``axis`` (a unit vector) and ``origin``, ``radius`` (a cone's
    at ``origin``), ``half_angle_deg`` (a cone's semi-angle as the kernel signs it: the radius at a height h
    along the axis is ``radius + h tan(half_angle_deg)``, so a cone narrowing along its axis reads negative --
    a reported angle takes its magnitude), ``minor_radius`` (a torus's) and ``concave``: True where
    the material lies outside the surface -- a hole, an internal fillet -- False where it lies inside -- a
    boss, an outside round -- None where it cannot be told."""

    kind: str
    normal: tuple[float, float, float] | None = None
    origin: tuple[float, float, float] | None = None
    axis: tuple[float, float, float] | None = None
    radius: float | None = None
    half_angle_deg: float | None = None
    minor_radius: float | None = None
    concave: bool | None = None

    def as_data(self) -> dict[str, Any]:
        return {key: (list(value) if isinstance(value, tuple) else value) for key, value in self.__dict__.items()
                if value is not None}


def _xyz(value: Any) -> tuple[float, float, float]:
    return (float(value.X()), float(value.Y()), float(value.Z()))


def _kinds() -> dict[Any, str]:
    from OCP.GeomAbs import (GeomAbs_BezierSurface, GeomAbs_BSplineSurface, GeomAbs_Cone, GeomAbs_Cylinder,
                             GeomAbs_OffsetSurface, GeomAbs_Plane, GeomAbs_Sphere, GeomAbs_SurfaceOfExtrusion,
                             GeomAbs_SurfaceOfRevolution, GeomAbs_Torus)

    return {GeomAbs_Plane: "plane", GeomAbs_Cylinder: "cylinder", GeomAbs_Cone: "cone", GeomAbs_Sphere: "sphere",
            GeomAbs_Torus: "torus", GeomAbs_BSplineSurface: "bspline", GeomAbs_BezierSurface: "bspline",
            GeomAbs_SurfaceOfRevolution: "revolution", GeomAbs_SurfaceOfExtrusion: "extrusion",
            GeomAbs_OffsetSurface: "offset"}


def _mid_uv(face: Any) -> tuple[float, float]:
    from OCP.BRepTools import BRepTools

    umin, umax, vmin, vmax = BRepTools.UVBounds_s(face.wrapped)
    return (umin + umax) / 2.0, (vmin + vmax) / 2.0


def point_normal(face: Any, u: float, v: float, props: Any = None) -> tuple[np.ndarray, np.ndarray]:
    """The point at ``(u, v)`` of ``face`` and its outward unit normal (the face's orientation applied).
    ``props``: the face's ``BRepGProp_Face``, made once by a caller that asks many points of one face."""
    from OCP.BRepGProp import BRepGProp_Face
    from OCP.gp import gp_Pnt, gp_Vec

    props = props if props is not None else BRepGProp_Face(face.wrapped)
    point, normal = gp_Pnt(), gp_Vec()
    props.Normal(u, v, point, normal)
    length = normal.Magnitude()
    n = np.array(_xyz(normal)) / length if length > 1e-300 else np.zeros(3)
    return np.array(_xyz(point)), n


def surface(face: Any) -> Surface:
    """The surface of a face (see ``Surface``). A B-spline or Bezier face that IS a plane, cylinder, cone,
    sphere or torus within a tight tolerance (``_canonical``) is read as that surface: ``extrude(taper=)``,
    a loft, a fillet between such faces and many STEP exporters write analytic geometry as splines."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface

    adaptor = BRepAdaptor_Surface(face.wrapped, True)
    kind = _kinds().get(adaptor.GetType(), "other")
    geometry = None
    if kind == "plane":
        geometry = adaptor.Plane()
    elif kind in ("cylinder", "cone", "sphere", "torus"):
        geometry = {"cylinder": adaptor.Cylinder, "cone": adaptor.Cone, "sphere": adaptor.Sphere,
                    "torus": adaptor.Torus}[kind]()
    elif kind == "bspline":
        found = _canonical(face)
        if found is not None:
            kind, geometry = found
    if geometry is None:
        return Surface(kind)
    if kind == "plane":
        u, v = _mid_uv(face)
        _, normal = point_normal(face, u, v)
        origin = _xyz(geometry.Location())
        return Surface("plane", normal=tuple(float(value) for value in normal), origin=origin)  # type: ignore[arg-type]
    if kind == "sphere":
        origin = _xyz(geometry.Location())
        axis = _xyz(geometry.Position().Direction())
    else:
        origin = _xyz(geometry.Axis().Location())
        axis = _xyz(geometry.Axis().Direction())
    radius = float(geometry.MajorRadius() if kind == "torus" else geometry.Radius() if kind != "cone"
                   else geometry.RefRadius())
    u, v = _mid_uv(face)
    point, normal = point_normal(face, u, v)
    o, a = np.array(origin), np.array(axis)
    if kind == "sphere":
        radial = point - o
    elif kind == "torus":
        along = point - o
        ring = along - a * float(along @ a)
        ring = ring / (np.linalg.norm(ring) or 1.0) * radius
        radial = point - (o + ring)
    else:
        along = point - o
        radial = along - a * float(along @ a)
    size = float(np.linalg.norm(radial))
    concave = None if size < 1e-12 else bool(float(normal @ (radial / size)) < 0.0)
    return Surface(kind, origin=origin, axis=axis, radius=radius,
                   half_angle_deg=math.degrees(geometry.SemiAngle()) if kind == "cone" else None,
                   minor_radius=float(geometry.MinorRadius()) if kind == "torus" else None, concave=concave)


#: A spline face within this share of its own size (its box's diagonal) of an analytic surface, and never
#: more than ``_CANONICAL_MM``, is read as that surface.
_CANONICAL_SHARE = 1e-6
_CANONICAL_MM = 1e-4


def _canonical(face: Any) -> tuple[str, Any] | None:
    """The analytic surface a spline face lies on, if it lies on one within the tolerance: OCCT's canonical
    recognition (``ShapeAnalysis_CanonicalRecognition``) for a plane, cylinder, cone or sphere, a fit of its
    points for a torus. None for a free-form face."""
    from OCP.gp import gp_Cone, gp_Cylinder, gp_Pln, gp_Sphere
    from OCP.ShapeAnalysis import ShapeAnalysis_CanonicalRecognition

    box = face.bounding_box()
    tolerance = min(_CANONICAL_MM, max(1e-7, _CANONICAL_SHARE * float(box.diagonal)))
    for kind, made, test in (("plane", gp_Pln, "IsPlane"), ("cylinder", gp_Cylinder, "IsCylinder"),
                             ("cone", gp_Cone, "IsCone"), ("sphere", gp_Sphere, "IsSphere")):
        try:
            recognizer = ShapeAnalysis_CanonicalRecognition(face.wrapped)
            geometry = made()
            if getattr(recognizer, test)(tolerance, geometry) and 0.0 <= recognizer.GetGap() <= tolerance:
                return kind, geometry
        except Exception:  # noqa: BLE001 - a face the recognizer declines is free-form
            continue
    torus = _torus(face, tolerance)
    return ("torus", torus) if torus is not None else None


def _torus(face: Any, tolerance: float) -> Any:
    """The torus a spline face lies on (a ``gp_Torus``), or None: its minor radius from the face's principal
    curvature, the centres of its points' tubes on one circle (the spine), every point checked against the
    torus they make."""
    from OCP.BRepGProp import BRepGProp_Face
    from OCP.BRepLProp import BRepLProp_SLProps
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepTools import BRepTools
    from OCP.gp import gp_Ax3, gp_Dir, gp_Pnt, gp_Torus

    umin, umax, vmin, vmax = BRepTools.UVBounds_s(face.wrapped)
    props = BRepGProp_Face(face.wrapped)
    points, normals = [], []
    for u in np.linspace(umin, umax, 6):
        for v in np.linspace(vmin, vmax, 6):
            point, normal = point_normal(face, float(u), float(v), props)
            points.append(point)
            normals.append(normal)
    points, normals = np.array(points), np.array(normals)
    curvature = BRepLProp_SLProps(BRepAdaptor_Surface(face.wrapped, True), (umin + umax) / 2, (vmin + vmax) / 2, 2,
                                  1e-9)
    if not curvature.IsCurvatureDefined():
        return None
    bend = max(abs(curvature.MaxCurvature()), abs(curvature.MinCurvature()))
    if bend <= 1e-12:
        return None
    minor = 1.0 / bend
    for side in (1.0, -1.0):
        centres = points - side * minor * normals
        middle = centres.mean(axis=0)
        _, spread, frame = np.linalg.svd(centres - middle)
        axis = frame[2]
        if spread[1] <= 1e-9:
            continue
        flat = (centres - middle) @ np.stack([frame[0], frame[1]], axis=1)
        # The circle through the centres (least squares): x^2 + y^2 = 2 a x + 2 b y + c.
        system = np.column_stack([2 * flat, np.ones(len(flat))])
        (a, b, c), *_ = np.linalg.lstsq(system, (flat ** 2).sum(axis=1), rcond=None)
        major = math.sqrt(max(c + a * a + b * b, 0.0))
        origin = middle + a * frame[0] + b * frame[1]
        if major <= minor * 1e-6:
            continue
        rel = points - origin
        height = rel @ axis
        ring = np.linalg.norm(rel - np.outer(height, axis), axis=1)
        if float(np.max(np.abs(np.hypot(ring - major, height) - minor))) <= tolerance:
            frame3 = gp_Ax3(gp_Pnt(*map(float, origin)), gp_Dir(*map(float, axis)))
            return gp_Torus(frame3, major, minor)
    return None


# --- edges -----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Edge:
    """An edge between two faces of a part: their ordinals, whether the material's angle there is over 180
    degrees (``concave``: an internal corner) or under (convex: an outside one), that angle, and
    ``smooth`` where the faces are tangent (a fillet's join: neither corner)."""

    ordinal: int
    faces: tuple[int, int]
    concave: bool
    smooth: bool
    angle_deg: float          # the material's angle: 90 at a box's edge, 270 at a pocket's corner
    length: float
    midpoint: tuple[float, float, float]
    tangent: tuple[float, float, float]


def _orientations(face: Any) -> list[tuple[Any, Any]]:
    """The edges of a face as it bounds them, each with its orientation in the face."""
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer

    found = []
    explorer = TopExp_Explorer(face.wrapped, TopAbs_EDGE)
    while explorer.More():
        current = explorer.Current()
        found.append((current, current.Orientation()))
        explorer.Next()
    return found


def _in_face_orientation(face: Any, edge: Any, walked: list[tuple[Any, Any]] | None = None) -> Any:
    """The orientation of ``edge`` in ``face`` (``walked``: the face's ``_orientations``, made once)."""
    for current, orientation in walked if walked is not None else _orientations(face):
        if current.IsSame(edge.wrapped):
            return orientation
    return None


def _edge_point(edge: Any) -> tuple[float, np.ndarray, np.ndarray]:
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.gp import gp_Pnt, gp_Vec

    curve = BRepAdaptor_Curve(edge.wrapped)
    t = (curve.FirstParameter() + curve.LastParameter()) / 2.0
    point, tangent = gp_Pnt(), gp_Vec()
    curve.D1(t, point, tangent)
    size = tangent.Magnitude()
    return t, np.array(_xyz(point)), (np.array(_xyz(tangent)) / size if size > 1e-300 else np.zeros(3))


def _normal_on(face: Any, edge: Any, t: float) -> np.ndarray:
    from OCP.BRepAdaptor import BRepAdaptor_Curve2d

    uv = BRepAdaptor_Curve2d(edge.wrapped, face.wrapped).Value(t)
    return point_normal(face, uv.X(), uv.Y())[1]


def edges(part: Part) -> list[Edge]:
    """Every edge of ``part`` that two of its faces share (a seam, which one face meets twice, is none)."""
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp
    from OCP.collections import (
        IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedDataMapOfShapeListOfShape)

    import build123d as bd

    ancestry = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(part.shape.wrapped, TopAbs_EDGE, TopAbs_FACE, ancestry)
    found: list[Edge] = []
    walked: dict[int, list[tuple[Any, Any]]] = {}  # each face's edges walked once, not once an edge
    for index in range(1, ancestry.Extent() + 1):
        listed = ancestry.FindFromIndex(index)  # iterating an OCCT list from Python costs milliseconds an item
        owners = ([] if listed.Size() == 0 else [listed.First()] if listed.Size() == 1
                  else [listed.First(), listed.Last()] if listed.Size() == 2 else list(listed))
        distinct: list[Any] = []
        for owner in owners:
            if not any(owner.IsSame(other) for other in distinct):
                distinct.append(owner)
        if len(distinct) != 2:
            continue
        edge = bd.Edge(ancestry.FindKey(index))
        if edge.length < 1e-9:
            continue
        a, b = (bd.Face(face) for face in distinct)
        try:
            t, point, tangent = _edge_point(edge)
            na, nb = _normal_on(a, edge, t), _normal_on(b, edge, t)
        except Exception:  # noqa: BLE001 - a degenerate edge has no angle to give
            continue
        key = part.face_ordinal(a)
        if key not in walked:
            walked[key] = _orientations(a)
        orientation = _in_face_orientation(a, edge, walked[key])
        along = -tangent if orientation == TopAbs_REVERSED else tangent
        into_a = np.cross(na, along)  # the material of a face lies to the left of its edges, seen from outside
        between = math.degrees(math.acos(max(-1.0, min(1.0, float(na @ nb)))))
        smooth = between < SMOOTH_DEG
        concave = (not smooth) and float(nb @ into_a) > 0.0
        angle = 180.0 + between if concave else 180.0 - between
        found.append(Edge(part.edge_ordinal(edge), (part.face_ordinal(a), part.face_ordinal(b)), concave, smooth,
                          angle, float(edge.length), tuple(float(x) for x in point),  # type: ignore[arg-type]
                          tuple(float(x) for x in tangent)))  # type: ignore[arg-type]
    return found


def edge_angles(part: Part, edge: Edge, fractions: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The material's angle along ``edge`` (as ``Edge.angle_deg`` reads it at its middle) at each of
    ``fractions`` of its length: the points, and the angle there (NaN where a face has no normal: a cone's
    apex). An edge between two planes keeps one angle along its length; one of a curved face turns (an edge
    where a cone meets a sphere runs from 63 to 42 degrees)."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Curve2d, BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.GCPnts import GCPnts_AbscissaPoint
    from OCP.TopAbs import TopAbs_REVERSED
    from OCP.gp import gp_Pnt, gp_Vec

    context = part._edge_context.get(edge.ordinal)
    if context is None:
        from OCP.BRepGProp import BRepGProp_Face

        shape = part.edges()[edge.ordinal - 1]
        a, b = (part.faces()[ordinal - 1] for ordinal in edge.faces)
        curve = BRepAdaptor_Curve(shape.wrapped)
        planar = all(BRepAdaptor_Surface(f.wrapped).GetType() == GeomAbs_Plane for f in (a, b))
        context = (curve, planar) if planar else (
            curve, planar, _in_face_orientation(a, shape), BRepAdaptor_Curve2d(shape.wrapped, a.wrapped),
            BRepAdaptor_Curve2d(shape.wrapped, b.wrapped), BRepGProp_Face(a.wrapped), BRepGProp_Face(b.wrapped))
        part._edge_context[edge.ordinal] = context
    curve, planar = context[0], context[1]
    first, last = curve.FirstParameter(), curve.LastParameter()
    length = float(edge.length)
    params = []
    for fraction in np.asarray(fractions, dtype=float):
        try:
            at = GCPnts_AbscissaPoint(curve, float(fraction) * length, first)
            params.append(at.Parameter() if at.IsDone() else first + float(fraction) * (last - first))
        except Exception:  # noqa: BLE001 - a curve the kernel cannot measure along is read by its parameter
            params.append(first + float(fraction) * (last - first))
    points = np.zeros((len(params), 3))
    for k, t in enumerate(params):
        point = gp_Pnt()
        curve.D0(t, point)
        points[k] = _xyz(point)
    if planar:
        return points, np.full(len(params), float(edge.angle_deg))
    orientation, on_a, on_b = context[2], context[3], context[4]
    props = (context[5], context[6])
    angles = np.full(len(params), np.nan)
    for k, t in enumerate(params):
        point, tangent = gp_Pnt(), gp_Vec()
        curve.D1(t, point, tangent)
        size = tangent.Magnitude()
        normals = []
        for adaptor, prop in zip((on_a, on_b), props):
            uv = adaptor.Value(t)
            normals.append(point_normal(None, uv.X(), uv.Y(), prop)[1])
        na, nb = normals
        if size < 1e-300 or not np.linalg.norm(na) > 0.5 or not np.linalg.norm(nb) > 0.5:
            continue
        along = np.array(_xyz(tangent)) / size
        along = -along if orientation == TopAbs_REVERSED else along
        between = math.degrees(math.acos(max(-1.0, min(1.0, float(na @ nb)))))
        concave = between >= SMOOTH_DEG and float(nb @ np.cross(na, along)) > 0.0
        angles[k] = 180.0 + between if concave else 180.0 - between
    return points, angles


# --- rays and points -------------------------------------------------------------------------------------


#: Triangles of a face's own triangulation per box of the ray screen (``Screen``).
SCREEN_CHUNK = 16
#: A face's surface lies within its triangulation's deflection of its triangles; the screen widens each box by
#: this many deflections (and the face's tolerance), so no ray that crosses the face misses its boxes.
SCREEN_SLACK = 3.0
#: The screen's mesh deflection, a share of the part's size: its boxes are as loose as this.
SCREEN_SHARE = 2e-3
#: The face boundary's polylines (``Intersector``) are walked to this share of the part's size.
BOUNDARY_SHARE = 2e-5
#: Box tests a screen runs at once, at most (its arrays are this many rows).
_SCREEN_BLOCK = 1 << 18


def freeform(face: Any) -> bool:
    """Whether a face (a ``TopoDS_Face``) is free-form: its surface no plane, cylinder, cone, sphere or torus."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Plane, GeomAbs_Sphere, GeomAbs_Torus

    return BRepAdaptor_Surface(face, False).GetType() not in (GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone,
                                                               GeomAbs_Sphere, GeomAbs_Torus)


#: A free-form face of this many edges or more is heavy (``heavy``), and a B-spline of this many control points.
HEAVY_EDGES = 48
HEAVY_POLES = 4000


def heavy(face: Any) -> bool:
    """Whether a face's exact intersection is costly: a free-form face of many edges (``HEAVY_EDGES``), or a
    B-spline of many control points (``HEAVY_POLES``). The kernel's intersector costs microseconds a ray on most
    faces, and a millisecond or more on such a face: classifying a crossing against its many edges' curves -- 6 ms
    a ray its line meets the surface beyond the trim, on a 526-edge face, against 4 to 20 microseconds on a face of
    under 20 edges -- or searching a large surface's polyhedron for a line that misses it (an F1 monocoque's
    panels: 0.4 ms a ray)."""
    if not freeform(face):
        return False
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_BSplineSurface
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer

    surface = BRepAdaptor_Surface(face, False)
    if surface.GetType() == GeomAbs_BSplineSurface:
        spline = surface.BSpline()
        if spline.NbUPoles() * spline.NbVPoles() >= HEAVY_POLES:
            return True
    explorer, edges = TopExp_Explorer(face, TopAbs_EDGE), 0
    while explorer.More() and edges < HEAVY_EDGES:
        edges += 1
        explorer.Next()
    return edges >= HEAVY_EDGES


class Screen:
    """Which faces a ray can cross, read from each face's own triangulation (the one its samples were laid on), or
    a copy of the face meshed finer where that is coarser than ``SCREEN_SHARE`` (the face itself is never meshed
    here): the face's triangles in chunks of ``SCREEN_CHUNK`` along a space-filling curve,
    each chunk's box widened by ``SCREEN_SLACK`` deflections and the face's tolerance. The surface over a
    triangle lies within the deflection of it, so a ray that meets none of a face's boxes does not cross the
    face, and is never intersected with it exactly: on a free-form face a miss costs the exact intersection a
    millisecond or more (nine in ten of a large part's), its boxes microseconds. Where a ray can cross, where it
    enters the face's nearest box bounds the crossing, a tighter bound than the face's own box. A face is read
    once, when a ray first asks of it; one whose triangulation cannot be read (none, even meshed on a copy, or a
    boundary it does not follow) is not screened: every ray its box admits is intersected, by the full
    intersector on the whole ray."""

    def __init__(self, faces: list[Any], size: float) -> None:
        self.faces = faces
        self.size = float(size) or 1.0
        count = len(faces)
        # Only a heavy face is screened (``heavy``): any other's exact intersection costs less than its boxes
        # (tested in batches too, every face's: measured a loss on every part tried).
        self.heavy = np.array([heavy(face) for face in faces], dtype=bool)
        self._read = np.zeros(count, dtype=bool)
        self.boundaries: dict[int, tuple[np.ndarray, np.ndarray, float] | None] = {}
        #: Per face index, the rays the kernel failed to intersect with it (``Intersector``).
        self.failed: dict[int, int] = {}
        self.first = np.zeros(count, dtype=np.int64)
        self.count = np.zeros(count, dtype=np.int64)
        self.lo = np.zeros((0, 3))
        self.hi = np.zeros((0, 3))

    def _chunks(self, face: Any) -> tuple[np.ndarray, np.ndarray, Any] | None:
        from OCP.BRep import BRep_Tool
        from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
        from OCP.GCPnts import GCPnts_TangentialDeflection
        from OCP.TopAbs import TopAbs_EDGE
        from OCP.TopExp import TopExp, TopExp_Explorer
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopoDS import TopoDS

        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        fine = SCREEN_SHARE * self.size
        if triangulation is None or not triangulation.Deflection() <= fine:
            # Its own mesh is missing or coarser than the screen's: a copy of the face meshed finely (nothing
            # is written into the face itself, whose mesh its samples are laid on).
            from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
            from OCP.BRepMesh import BRepMesh_IncrementalMesh

            face = TopoDS.Face(BRepBuilderAPI_Copy(face, True, False).Shape())
            BRepMesh_IncrementalMesh(face, fine, False, 0.5, False)
            location = TopLoc_Location()
            triangulation = BRep_Tool.Triangulation_s(face, location)
        if triangulation is None or triangulation.NbTriangles() == 0:
            return None
        # The surface's deflection, and its boundary's: a plane's triangles lie on it exactly, but its round
        # edges' chords cut inside them by their own deflection.
        deflection = float(triangulation.Deflection())
        trsf = location.Transformation()
        nodes = np.array([_xyz(triangulation.Node(i).Transformed(trsf)) for i in range(1, triangulation.NbNodes() + 1)])
        # The boundary as the triangulation's polylines (``Intersector``): each edge's, and each vertex's point.
        starts, ends, tolerance, unknown = [], [], 0.0, False
        edge_deflection = max(BOUNDARY_SHARE * self.size, 1e-6)
        explorer = TopExp_Explorer(face, TopAbs_EDGE)
        while explorer.More():
            edge = TopoDS.Edge(explorer.Current())
            explorer.Next()
            tolerance = max(tolerance, float(BRep_Tool.Tolerance_s(edge)))
            if BRep_Tool.Degenerated_s(edge):
                continue
            polygon = BRep_Tool.PolygonOnTriangulation_s(edge, triangulation, location)
            if polygon is None:
                return None  # a boundary the triangulation does not say how near it keeps: not screened
            deflection = max(deflection, float(polygon.Deflection()))
            try:
                curve = BRepAdaptor_Curve(edge)
                walked = GCPnts_TangentialDeflection(curve, 0.1, edge_deflection)
                line = np.array([_xyz(walked.Value(i)) for i in range(1, walked.NbPoints() + 1)])
            except Exception:  # noqa: BLE001 - an edge the kernel cannot walk: its boundary is unknown
                line = np.zeros((0, 3))
            if len(line) < 2:
                unknown = True
                continue
            starts.extend(line[:-1])
            ends.extend(line[1:])
        if not (math.isfinite(deflection) and deflection > 0.0):
            return None
        tris = np.array([triangulation.Triangle(i).Get() for i in range(1, triangulation.NbTriangles() + 1)]) - 1
        corners = nodes[tris]                                   # (t, 3, 3)
        low, high = corners.min(axis=1), corners.max(axis=1)
        middle = corners.mean(axis=1)
        span = np.maximum(middle.max(axis=0) - middle.min(axis=0), 1e-300)
        cells = np.clip(((middle - middle.min(axis=0)) / span * 1023).astype(np.int64), 0, 1023)
        code = np.zeros(len(cells), dtype=np.int64)
        for bit in range(10):  # a Morton code: neighbouring triangles land in one chunk
            for axis in range(3):
                code |= ((cells[:, axis] >> bit) & 1) << (3 * bit + axis)
        order = np.argsort(code, kind="stable")
        low, high = low[order], high[order]
        cuts = np.arange(0, len(order), SCREEN_CHUNK)
        # The full intersector accepts a crossing its classifier puts within a tolerance of the boundary in
        # (u, v) (``IntCurvesFace_Intersector::InternalCall``): the larger of its own (1e-7) and the edges'
        # largest 3D tolerance at the surface's coarser resolution, a (u, v) distance that is longest in
        # millimetres along the surface's finer direction -- on a long, thin B-spline many times the edges'
        # tolerance -- or within an edge's tolerance of its curve. Twice each, and the polylines' own deflection,
        # is the reach.
        try:
            surface = BRepAdaptor_Surface(face, False)
            resolutions = (float(surface.UResolution(1.0)), float(surface.VResolution(1.0)))
            finer, coarser = min(resolutions), max(resolutions)
            ok = finer > 0.0 and math.isfinite(finer) and math.isfinite(coarser)
            uv = max(1e-7, coarser * tolerance) / finer if ok else math.inf
        except Exception:  # noqa: BLE001 - a surface the kernel cannot resolve: its boundary unknown
            uv = math.inf
        if not math.isfinite(uv):
            unknown = True
        reach = 2.0 * (tolerance + float(BRep_Tool.Tolerance_s(face)) + uv) + SCREEN_SLACK * edge_deflection + 1e-7
        if not math.isfinite(reach):
            return None  # how far beyond its trim the kernel accepts a crossing is unknown: not screened
        # The boxes hold the surface over each triangle (its deflection), the boundary's nodes an edge's tolerance
        # off the trim, and every crossing the full intersector accepts beyond the trim (the reach).
        margin = SCREEN_SLACK * deflection + reach + 1e-9 * self.size
        boundary = None if unknown else (np.array(starts).reshape(-1, 3), np.array(ends).reshape(-1, 3), reach)
        return (np.minimum.reduceat(low, cuts, axis=0) - margin, np.maximum.reduceat(high, cuts, axis=0) + margin,
                boundary)

    def _load(self, faces: np.ndarray) -> None:
        """Read the faces not yet read whose triangulation is there now."""
        pending = np.unique(faces[~self._read[faces]])
        if not len(pending):
            return
        lows, highs = [self.lo], [self.hi]
        at = len(self.lo)
        for index in pending:
            self._read[index] = True  # read once: a face its triangulation fails on is not meshed again each ray
            found = self._chunks(self.faces[int(index)])
            if found is None:
                # not screened: every ray its box admits is intersected, by the full intersector on its whole
                # length (no boundary known)
                self.boundaries[int(index)] = None
                continue
            self.boundaries[int(index)] = found[2]
            self.first[index], self.count[index] = at, len(found[0])
            lows.append(found[0])
            highs.append(found[1])
            at += len(found[0])
        if len(lows) > 1:
            self.lo, self.hi = np.vstack(lows), np.vstack(highs)

    def pairs(self, origins: np.ndarray, directions: np.ndarray, ray: np.ndarray, face: np.ndarray,
              start: Any, end: Any) -> tuple[np.ndarray, np.ndarray]:
        """For (ray, face) pairs (``ray`` indexes ``origins`` and ``directions``, unit; ``face`` the faces'
        indices): whether the ray can cross the face between ``start`` and ``end`` (each a number, or one per
        pair), and the least distance it can cross it at (NaN for a face not screened, which can always be
        crossed)."""
        ray = np.asarray(ray, dtype=np.int64)
        face = np.asarray(face, dtype=np.int64)
        keep = np.ones(len(face), dtype=bool)
        entry = np.full(len(face), np.nan)
        if not len(face):
            return keep, entry
        self._load(face[self.heavy[face]])
        starts = np.broadcast_to(np.asarray(start, dtype=float), face.shape)
        ends = np.broadcast_to(np.asarray(end, dtype=float), face.shape)
        screened = np.flatnonzero(self.count[face] > 0)
        counts = self.count[face[screened]]
        bounds = np.concatenate([[0], np.cumsum(counts)])
        begin = 0
        while begin < len(screened):
            # as many pairs as keep the box tests under _SCREEN_BLOCK
            stop = int(np.searchsorted(bounds, bounds[begin] + _SCREEN_BLOCK, side="right")) - 1
            stop = max(stop, begin + 1)
            pick = screened[begin:stop]
            n = counts[begin:stop]
            pair = np.repeat(np.arange(len(pick)), n)
            chunk = np.repeat(self.first[face[pick]], n) + (np.arange(int(n.sum())) - np.repeat(np.cumsum(n) - n, n))
            o, d = origins[ray[pick]][pair], directions[ray[pick]][pair]
            lows, highs = self.lo[chunk], self.hi[chunk]
            flat = np.abs(d) <= 1e-300
            with np.errstate(divide="ignore", invalid="ignore"):
                inverse = np.where(flat, 0.0, 1.0 / np.where(flat, 1.0, d))
                t1, t2 = (lows - o) * inverse, (highs - o) * inverse
            lo = np.where(flat, -np.inf, np.minimum(t1, t2)).max(axis=1)
            hi = np.where(flat, np.inf, np.maximum(t1, t2)).min(axis=1)
            across = np.all(~flat | ((lows <= o) & (o <= highs)), axis=1)
            s, e = starts[pick][pair], ends[pick][pair]
            ok = across & (lo <= hi) & (hi >= s) & (lo <= e)
            near = np.where(ok, np.maximum(lo, s), np.inf)
            least = np.minimum.reduceat(near, np.concatenate([[0], np.cumsum(n)[:-1]]))
            keep[pick] = np.isfinite(least)
            entry[pick] = least
            begin = stop
        return keep, entry

    def order(self, origin: np.ndarray, direction: np.ndarray, candidates: np.ndarray, entries: np.ndarray,
              start: float, end: float) -> tuple[np.ndarray, np.ndarray]:
        """One ray's candidate faces (by their boxes, with where it enters each) less those it cannot cross,
        nearest first by the tighter bound."""
        if not len(candidates) or not self.heavy[candidates].any():
            return candidates, entries
        keep, entry = self.pairs(origin[None, :], direction[None, :], np.zeros(len(candidates), dtype=np.int64),
                                 candidates, start, end)
        entries = np.where(np.isnan(entry), entries, np.maximum(entries, np.where(np.isnan(entry), 0.0, entry)))
        candidates, entries = candidates[keep], entries[keep]
        order = np.argsort(entries, kind="stable")
        return candidates[order], entries[order]



class Intersector:
    """``IntCurvesFace_Intersector`` of one face, as exact, at a fraction of its cost on a free-form face.

    The kernel's intersector, asked to accept a crossing within its boundary's tolerance (``UseBToler``, as every
    check casts), classifies a crossing its fast classifier finds outside the face again with a classifier it
    builds anew each call: on a large free-form face, 30 ms a ray whose line meets the surface beyond the face's
    trim, most of a part's rays. The same intersector without it answers every crossing inside the face alike;
    the two differ only on a crossing within the boundary's tolerance, whose line passes that near the face's
    edges. So a ray is cast with the fast one, and with the full one too where its line passes within reach of the
    edges' polylines (``Screen.boundaries``: the triangulation's, widened by its deflection and every edge's and
    vertex's tolerance), whose crossings the fast one lacks are added (``Perform``); a face with no polylines to
    read is always cast with the full one."""

    def __init__(self, face: Any, tolerance: float, screen: "Screen | None" = None, index: int = -1) -> None:
        from OCP.IntCurvesFace import IntCurvesFace_Intersector

        self.face = face
        self.tolerance = tolerance
        self._screen = screen
        self._index = index
        free = screen is not None and bool(screen.heavy[index])
        self._fast = IntCurvesFace_Intersector(face, tolerance) if free else None
        if self._fast is not None:
            self._fast.SetUseBoundToler(False)
        self._full: Any = None if free else IntCurvesFace_Intersector(face, tolerance)
        self._points: list[tuple[float, float, float]] = []
        self._done = False
        from OCP.Standard import Standard_Failure

        self._failure = Standard_Failure  # read once: a ray's import of it cost a fifth of a cast

    def _near_boundary(self, line: Any, start: float, end: float) -> list[tuple[float, float]]:
        """The stretches of the ray -- the line between ``start`` and ``end`` -- that pass within reach of the
        face's boundary (its polylines, ``Screen.boundaries``), apart and in order: only there can the full
        intersector accept a crossing the fast one does not. The whole ray where the boundary is unknown."""
        screen = self._screen
        assert screen is not None
        screen._load(np.array([self._index]))
        found = screen.boundaries.get(self._index)
        if found is None:
            return [(start, end)]
        starts, ends, reach = found
        if not len(starts):
            return [(start, end)]
        location, direction = line.Location(), line.Direction()
        o = np.array([location.X(), location.Y(), location.Z()])
        d = np.array([direction.X(), direction.Y(), direction.Z()])
        # the ray clipped to the boundary's box (widened by the reach): beyond it no point is near it
        low = np.minimum(starts.min(axis=0), ends.min(axis=0)) - reach
        high = np.maximum(starts.max(axis=0), ends.max(axis=0)) + reach
        flat = np.abs(d) <= 1e-300
        with np.errstate(divide="ignore", invalid="ignore"):
            inverse = np.where(flat, 0.0, 1.0 / np.where(flat, 1.0, d))
            t1, t2 = (low - o) * inverse, (high - o) * inverse
        if np.any(flat & ((o < low) | (o > high))):
            return []
        enter = max(float(np.where(flat, -np.inf, np.minimum(t1, t2)).max()), start - reach)
        leave = min(float(np.where(flat, np.inf, np.maximum(t1, t2)).min()), end + reach)
        if enter > leave:
            return []
        # the least distance between the ray's stretch [enter, leave] and each boundary segment (both clamped)
        p1 = o + enter * d
        span = leave - enter
        e2 = ends - starts
        r = p1 - starts
        b = e2 @ d
        c = r @ d
        e = np.einsum("ij,ij->i", e2, e2)
        f = np.einsum("ij,ij->i", e2, r)
        denominator = e - b * b  # the ray's direction is a unit: its own a = 1
        with np.errstate(divide="ignore", invalid="ignore"):
            s_ray = np.where(denominator > 1e-300, np.clip((b * f - c * e) / np.where(denominator > 1e-300, denominator, 1.0),
                                                           0.0, span), 0.0)
            t_seg = np.where(e > 1e-300, (b * s_ray + f) / np.where(e > 1e-300, e, 1.0), 0.0)
        below, above = t_seg < 0.0, t_seg > 1.0
        t_seg = np.clip(t_seg, 0.0, 1.0)
        s_ray = np.where(below, np.clip(-c, 0.0, span), np.where(above, np.clip(b - c, 0.0, span), s_ray))
        gap = (p1 + s_ray[:, None] * d) - (starts + t_seg[:, None] * e2)
        near = np.einsum("ij,ij->i", gap, gap) <= reach * reach
        if not near.any():
            return []
        # every point within reach of a near segment lies, along the ray, within reach of that segment's shadow:
        # the shadows, merged where they overlap
        a, b = (starts[near] - o) @ d, (ends[near] - o) @ d
        lows, highs = np.maximum(np.minimum(a, b) - reach, start), np.minimum(np.maximum(a, b) + reach, end)
        merged: list[list[float]] = []
        for low, high in sorted(zip(lows.tolist(), highs.tolist())):
            if low > high:
                continue
            if merged and low <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], high)
            else:
                merged.append([low, high])
        return [(low, high) for low, high in merged]

    def Perform(self, line: Any, start: float, end: float) -> None:  # noqa: N802 - the kernel's name
        """Every crossing of the ray with the face: the fast intersector's over the whole ray (each inside the
        face), and the full one's on each stretch near the boundary that the fast one does not already hold -- the
        full intersector answers differently on different ranges, so neither's crossings are dropped for the
        other's. Where the fast one fails or does not finish, the full one over the whole ray answers. A
        stretch the kernel fails on (``Standard_Failure``, a degenerate patch of its surface) or does not finish
        loses its own crossings only, never the rest of the ray's; it is counted against the face
        (``Screen.failed``), which the check says, never a family lost to it."""
        Standard_Failure = self._failure  # noqa: N806 - the kernel's name
        self._points: list[tuple[float, float, float]] = []
        self._done = False
        if self._fast is None:
            # any face but a heavy one: the kernel's intersector alone, as it answers
            full = self._full
            try:
                full.Perform(line, start, end)
            except Standard_Failure:
                if self._screen is not None:
                    self._screen.failed[self._index] = self._screen.failed.get(self._index, 0) + 1
                return
            if full.IsDone():
                self._done = True
                self._points = [(float(full.WParameter(k)), float(full.UParameter(k)), float(full.VParameter(k)))
                                for k in range(1, full.NbPnt() + 1)]
                if len(self._points) > 1:
                    self._points.sort()
            return
        try:
            self._fast.Perform(line, start, end)
            fast = self._fast.IsDone()
        except Standard_Failure:
            fast = False
        if fast:
            self._done = True
            self._take(self._fast)
            stretches = self._near_boundary(line, start, end)
        else:
            stretches = [(start, end)]  # the full intersector answers for the whole ray
        if not stretches:
            return
        if self._full is None:
            from OCP.IntCurvesFace import IntCurvesFace_Intersector

            self._full = IntCurvesFace_Intersector(self.face, self.tolerance)
        have = [w for w, _, _ in self._points]
        lost = 0
        for low, high in stretches:
            try:
                self._full.Perform(line, low, high)
            except Standard_Failure:
                lost += 1
                continue
            if not self._full.IsDone():
                # a stretch near the boundary (the fast one done) not finished is a crossing that may be lost
                lost += int(self._done)
                continue
            if (low, high) == (start, end):
                self._done = True
            self._take(self._full, within=(low, high), besides=have)
        if lost and self._screen is not None:
            self._screen.failed[self._index] = self._screen.failed.get(self._index, 0) + lost
        self._points.sort()

    def _take(self, intersector: Any, within: tuple[float, float] | None = None,
              besides: list[float] | None = None) -> None:
        """The intersector's crossings (it is done), those ``within`` a stretch alone, and none ``besides`` a
        crossing already taken (the same crossing found by the other intersector, within its tolerance)."""
        for k in range(1, intersector.NbPnt() + 1):
            w = float(intersector.WParameter(k))
            if within is not None and not within[0] <= w <= within[1]:
                continue
            if besides and any(abs(w - h) <= self.tolerance + 1e-9 * abs(w) for h in besides):
                continue
            self._points.append((w, float(intersector.UParameter(k)), float(intersector.VParameter(k))))

    def IsDone(self) -> bool:  # noqa: N802
        return self._done

    def NbPnt(self) -> int:  # noqa: N802
        return len(self._points)

    def WParameter(self, k: int) -> float:  # noqa: N802
        return self._points[k - 1][0]

    def UParameter(self, k: int) -> float:  # noqa: N802
        return self._points[k - 1][1]

    def VParameter(self, k: int) -> float:  # noqa: N802
        return self._points[k - 1][2]


def failures(screens: Iterable["Screen"]) -> list[dict[int, int]]:
    """Each screen's count of rays the kernel failed to intersect, per face index, as it stands: what a family's
    own failures are read against (``failed_refs``)."""
    return [dict(screen.failed) for screen in screens]


def failed_ordinals(part: Part, screens: Iterable["Screen"], faces: Iterable[list[Any]],
                    before: list[dict[int, int]] | None = None) -> dict[int, int]:
    """The part's faces the kernel failed to intersect a ray with (``Screen.failed``), by ordinal, with how many
    rays -- since ``before`` (``failures``) where given: the faces a family's figures are not measured at. A
    copy's are the same ordinals (``copies``)."""
    found: dict[int, int] = {}
    for k, (screen, listed) in enumerate(zip(screens, faces)):
        was = before[k] if before is not None and k < len(before) else {}
        for index, count in screen.failed.items():
            if count > was.get(index, 0):
                ordinal = part.face_ordinal(listed[index])
                if ordinal:
                    found[ordinal] = found.get(ordinal, 0) + count - was.get(index, 0)
    return found


def unintersected(part: Part, screens: Iterable["Screen"], faces: Iterable[list[Any]]) -> dict[str, Any] | None:
    """The finding that says the kernel failed to intersect rays with some of the part's faces (``Screen.failed``:
    each a crossing not found, so what those rays reach is not measured there), naming the faces; None where
    every ray was intersected."""
    return unintersected_said(part, failed_ordinals(part, screens, faces))


def unintersected_said(part: Part, counts: dict[int, int]) -> dict[str, Any] | None:
    """``unintersected``'s finding from the counts per face ordinal (``failed_ordinals``): a copy's said at its
    own faces."""
    if not counts:
        return None
    refs = [part.ref("face", ordinal) for ordinal in sorted(counts)]
    shown = ", ".join(refs[:8]) + (f" and {len(refs) - 8} more" if len(refs) > 8 else "")
    return {"severity": "warning", "code": "rays_unintersected", "location": refs[0],
            "message": f"the kernel failed to intersect {sum(counts.values())} ray(s) with {len(refs)} face(s) of "
                       f"{part.owner or part.name or 'the part'} ({shown}): a crossing of those faces was not found, "
                       "so a wall, gap or reach measured across them is not measured there",
            "hint": "rebuild the faulty face (its surface has a degenerate patch the kernel cannot intersect), then "
                    "check again"}


class Rays:
    """Exact rays against a shape: the first face a ray hits, every crossing of a line, the wall under a
    point. Each face the ray's line could cross, by its bounding box (a slab test over every box at once),
    is intersected exactly (``IntCurvesFace_Intersector``), nearest box first, until no nearer crossing can
    follow -- a ray costs the faces near it, not the shape's every face. A crossing is its distance and the
    ``TopoDS_Face`` crossed; ``ordinal`` is that face's in the shape (``TopExp.MapShapes``' order)."""

    def __init__(self, shape: Any, tolerance: float = 1e-7) -> None:
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib
        from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as FaceMap
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp
        from OCP.TopoDS import TopoDS

        self.shape = shape
        self._tolerance = tolerance
        faces = FaceMap()
        TopExp.MapShapes_s(shape.wrapped, TopAbs_FACE, faces)
        self._map = faces
        self.faces = [TopoDS.Face(faces.FindKey(index)) for index in range(1, faces.Extent() + 1)]
        whole = Bnd_Box()
        BRepBndLib.Add_s(shape.wrapped, whole, False)
        size = float(np.sqrt(whole.SquareExtent())) if not whole.IsVoid() else 1.0
        self.boxes = np.zeros((len(self.faces), 6))
        for index, face in enumerate(self.faces):
            box = Bnd_Box()
            BRepBndLib.Add_s(face, box, False)
            box.Enlarge(1e-4 * size + 1e-6)
            low, high = box.CornerMin(), box.CornerMax()
            self.boxes[index] = (low.X(), low.Y(), low.Z(), high.X(), high.Y(), high.Z())
        self._intersectors: dict[int, Any] = {}
        self._props: dict[int, Any] = {}
        #: The lines whose crossings ``intervals`` could not pair into stretches of material (it answered None).
        self.unpaired = 0
        self.screen = Screen(self.faces, size)

    def _candidates(self, o: np.ndarray, d: np.ndarray, start: float, end: float) -> tuple[np.ndarray, np.ndarray]:
        """The faces whose boxes the ray meets between ``start`` and ``end``, nearest first, and where it
        enters each."""
        lows, highs = self.boxes[:, :3], self.boxes[:, 3:]
        flat = np.abs(d) <= 1e-300
        with np.errstate(divide="ignore", invalid="ignore"):
            inverse = np.where(flat, 0.0, 1.0 / np.where(flat, 1.0, d))
            t1, t2 = (lows - o) * inverse, (highs - o) * inverse
        lo = np.where(flat, -np.inf, np.minimum(t1, t2))
        hi = np.where(flat, np.inf, np.maximum(t1, t2))
        across = np.all(~flat | ((lows <= o) & (o <= highs)), axis=1)
        enter, leave = lo.max(axis=1), hi.min(axis=1)
        mask = across & (enter <= leave) & (leave >= start) & (enter <= end)
        index = np.flatnonzero(mask)
        entries = np.maximum(enter[index], start)
        order = np.argsort(entries)
        return index[order], entries[order]

    def _intersector(self, index: int) -> Any:
        found = self._intersectors.get(index)
        if found is None:
            found = self._intersectors[index] = Intersector(self.faces[index], self._tolerance, self.screen, index)
        return found

    def _crossings(self, origin: Iterable[float], direction: Iterable[float], start: float, end: float,
                   nearest: bool, senses: list[int] | None = None) -> list[tuple[float, int]]:
        """Every crossing between ``start`` and ``end`` (``nearest``: the first alone), nearest first: its
        distance and its face's index. ``senses``, a list given empty, is filled with which way the line
        passes each (``_sense``), in the same order."""
        from OCP.gp import gp_Dir, gp_Lin, gp_Pnt


        o = np.asarray(list(origin), dtype=float)
        d = np.asarray(list(direction), dtype=float)
        d = d / (np.linalg.norm(d) or 1.0)
        candidates, entries = self._candidates(o, d, start, end)
        candidates, entries = self.screen.order(o, d, candidates, entries, start, end)
        if not len(candidates):
            return []
        line = gp_Lin(gp_Pnt(*o), gp_Dir(*d))
        found: list[tuple[float, int]] = []
        passed: dict[tuple[float, int], int] = {}
        for index, entry in zip(candidates, entries):
            if nearest and found and entry > found[0][0]:
                break
            intersector = self._intersector(int(index))
            intersector.Perform(line, start, found[0][0] if nearest and found else end)
            if not intersector.IsDone():
                continue
            for k in range(1, intersector.NbPnt() + 1):
                w = float(intersector.WParameter(k))
                if start <= w <= end:
                    found.append((w, int(index)))
                    if senses is not None:
                        passed[found[-1]] = self._sense(int(index), d, float(intersector.UParameter(k)),
                                                        float(intersector.VParameter(k)))
            if nearest and found:
                found = [min(found)]
        found.sort()
        if senses is not None:
            senses.extend(passed[crossing] for crossing in found)
        return found

    def _sense(self, index: int, direction: np.ndarray, u: float, v: float) -> int:
        """Which way a line along ``direction`` passes the face ``index`` at ``(u, v)``: 1 into the material
        (against the face's outward normal), -1 out of it, 0 along it -- a tangent touch, within
        ``TANGENT`` of the surface's own plane there. A point where the surface has no normal (a cone's
        apex, a sphere's pole) is read a millionth of the face's parameters toward its middle."""
        from OCP.BRepGProp import BRepGProp_Face
        from OCP.BRepTools import BRepTools
        from OCP.gp import gp_Pnt, gp_Vec

        props = self._props.get(index)
        if props is None:
            props = self._props[index] = BRepGProp_Face(self.faces[index])
        point, normal = gp_Pnt(), gp_Vec()
        props.Normal(u, v, point, normal)
        if normal.Magnitude() <= 1e-12:
            u0, u1, v0, v1 = BRepTools.UVBounds_s(self.faces[index])
            props.Normal(u + 1e-6 * ((u0 + u1) / 2.0 - u), v + 1e-6 * ((v0 + v1) / 2.0 - v), point, normal)
            if normal.Magnitude() <= 1e-12:
                return 0
        along = float(np.dot(direction, _xyz(normal))) / normal.Magnitude()
        return 0 if abs(along) <= TANGENT else (-1 if along > 0.0 else 1)

    def hits(self, origin: Iterable[float], direction: Iterable[float], start: float = 0.0,
             end: float = 1e9) -> list[tuple[float, Any]]:
        """Every crossing of the ray from ``origin`` along ``direction`` between ``start`` and ``end``: its
        distance and the ``TopoDS_Face`` it crosses, nearest first."""
        return [(w, self.faces[index]) for w, index in self._crossings(origin, direction, start, end, False)]

    def first(self, origin: Iterable[float], direction: Iterable[float], skip: float = 1e-5,
              end: float = 1e9) -> tuple[float, Any] | None:
        """The nearest crossing beyond ``skip``, or None."""
        found = self._crossings(origin, direction, skip, end, True)
        return (found[0][0], self.faces[found[0][1]]) if found else None

    def ordinal(self, face: Any) -> int:
        """The ordinal (1-based) of a face a crossing names, 0 for none of this shape's."""
        return int(self._map.FindIndex(face))

    def thickness(self, point: Iterable[float], normal: Iterable[float], skip: float = 1e-5) -> float | None:
        """The wall under ``point`` of a face whose outward normal there is ``normal``: the distance, into the
        material, to the next face the ray crosses; None where it crosses none (an open shell)."""
        n = np.asarray(list(normal), dtype=float)
        hit = self.first(np.asarray(list(point), dtype=float), -n, skip=skip)
        return None if hit is None else hit[0]

    def intervals(self, origin: Iterable[float], direction: Iterable[float], tolerance: float = 1e-6
                  ) -> list[tuple[float, float]] | None:
        """The stretches of the whole line through ``origin`` along ``direction`` that lie in the material of
        a closed solid, as distances from ``origin`` -- or None where they cannot be told.

        Each crossing is told by which way the line passes the face there (``_sense``): into the material,
        out of it, or along the surface -- a tangent touch, which is no crossing: a line that grazes a
        torus's top passes no material, and one that grazes its inner equator from inside stays inside.
        Crossings within ``tolerance`` of each other are one place (an edge's two faces, a vertex's three):
        one entry where every face there is passed inward, one exit where outward, and nothing where the
        faces disagree -- the line touches the edge and stays on its side, outside or inside. The stretches
        are those from an entry to the exit after it. Where the places do not alternate so -- two entries
        running, a line that ends inside (an open shell, a crossing the kernel lost), a place where the
        kernel finds the line along one face while it crosses another -- the answer is None, counted in
        ``unpaired``: unknown, never a guess a wall or a gap is measured from. A line that lies in a face's
        own surface, where the kernel finds no crossing of that face, is read by the faces it does cross."""
        senses: list[int] = []
        crossings = self._crossings(origin, direction, -1e9, 1e9, False, senses)
        places: list[tuple[float, list[int]]] = []
        for (distance, _), sense in zip(crossings, senses):
            if places and distance - places[-1][0] <= tolerance:
                places[-1][1].append(sense)
            else:
                places.append((distance, [sense]))
        found: list[tuple[float, float]] = []
        entered: float | None = None
        for distance, passed in places:
            crossed = {sense for sense in passed if sense}
            if not crossed:
                continue  # a tangent touch alone: the line stays on its side
            if len(crossed) == 2:
                continue  # an edge or a vertex touched: faces passed both ways, the line stays on its side
            if 0 in passed:
                self.unpaired += 1
                return None  # it crosses one face where it runs along another: on the boundary
            if (1 in crossed) == (entered is not None):
                self.unpaired += 1
                return None  # two entries, or two exits, running: a crossing is missing
            if entered is None:
                entered = distance
            else:
                found.append((entered, distance))
                entered = None
        if entered is not None:
            self.unpaired += 1
            return None
        return found


def least_edge_angle(part: Part, edge: Edge, fractions: np.ndarray, angles: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """``fractions`` and ``angles`` with the edge's least angle added where it lies: a golden-section search of
    ``edge_angles`` between the samples either side of the least sampled one -- at an end, between it and its
    neighbour (the least may lie between them, or be the end's own)."""
    finite = np.isfinite(angles)
    k = int(np.nanargmin(angles))
    last = len(fractions) - 1
    lo_k, hi_k = max(k - 1, 0), min(k + 1, last)
    if lo_k == hi_k or not (finite[lo_k] and finite[hi_k]):
        return fractions, angles

    def at(fraction: float) -> float:
        value = float(edge_angles(part, edge, np.array([fraction]))[1][0])
        return value if math.isfinite(value) else math.inf

    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    lo, hi = float(fractions[lo_k]), float(fractions[hi_k])
    a, b = hi - ratio * (hi - lo), lo + ratio * (hi - lo)
    fa, fb = at(a), at(b)
    for _ in range(60):
        if hi - lo < 1e-9:
            break
        if fa <= fb:
            hi, b, fb = b, a, fa
            a = hi - ratio * (hi - lo)
            fa = at(a)
        else:
            lo, a, fa = a, b, fb
            b = lo + ratio * (hi - lo)
            fb = at(b)
    best, value = (a, fa) if fa <= fb else (b, fb)
    if not value < float(angles[k]):
        return fractions, angles
    order = int(np.searchsorted(fractions, best))
    return np.insert(fractions, order, best), np.insert(angles, order, value)


def inside(solid: Any, points: Iterable[Iterable[float]], tolerance: float = 1e-6) -> list[bool]:
    """Whether each point lies inside ``solid`` (on its boundary is not inside)."""
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_IN

    classifier = BRepClass3d_SolidClassifier(solid.wrapped)
    found = []
    for point in points:
        classifier.Perform(gp_Pnt(*[float(value) for value in point]), tolerance)
        found.append(classifier.State() == TopAbs_IN)
    return found


@dataclass(frozen=True)
class Sample:
    """A point on a face, its outward normal there and the area it stands for."""

    point: np.ndarray
    normal: np.ndarray
    area: float


def _triangulated(shape: Any, deflection: float, angular: float = 0.5) -> None:
    from OCP.BRepMesh import BRepMesh_IncrementalMesh

    BRepMesh_IncrementalMesh(shape.wrapped, deflection, False, angular, True)


def face_size(face: Any) -> float:
    """The face's largest extent in its own frame (its oriented box's longest side, ``Bnd_OBB``): a size that
    turns with the face, so a mesh tolerance taken from it -- and every sample laid on that mesh -- is the same
    however the part is turned (a world box's longest side grows by up to 1.7 times as a face turns off the
    axes). The world box's where the oriented box cannot be made."""
    from OCP.Bnd import Bnd_OBB
    from OCP.BRepBndLib import BRepBndLib

    try:
        box = Bnd_OBB()
        BRepBndLib.AddOBB_s(face.wrapped, box, False, False, False)
        size = 2.0 * max(box.XHSize(), box.YHSize(), box.ZHSize())
        if math.isfinite(size) and size > 0.0:
            return float(size)
    except Exception:  # noqa: BLE001 - a face the oriented box fails on takes the world box
        pass
    world = face.bounding_box(optimal=False)
    return float(max(world.size.X, world.size.Y, world.size.Z))


def deflection_for(face: Any) -> float:
    """The mesh tolerance a face's samples are laid on: a fiftieth of its size (``face_size``), 1e-3 mm at
    least."""
    return max(1e-3, 0.02 * face_size(face))


def samples(face: Any, count: int = 64, deflection: float | None = None) -> list[Sample]:
    """About ``count`` points spread evenly over ``face`` by area, each on the surface itself: the face's
    triangulation (made with ``deflection``, ``deflection_for``'s by default: a fiftieth of the face's own size,
    the same however the part is turned) cut into triangles
    of about equal area, each sample the surface at one's middle, with its outward normal and its share
    of the face's area."""
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location

    if deflection is None:
        deflection = deflection_for(face)
    _triangulated(face, deflection)
    location = TopLoc_Location()
    triangulation = BRep_Tool.Triangulation_s(face.wrapped, location)
    if triangulation is None or triangulation.NbTriangles() == 0:
        return []
    trsf = location.Transformation()
    nodes = np.array([_xyz(triangulation.Node(i).Transformed(trsf)) for i in range(1, triangulation.NbNodes() + 1)])
    uvs = (np.array([(triangulation.UVNode(i).X(), triangulation.UVNode(i).Y())
                     for i in range(1, triangulation.NbNodes() + 1)]) if triangulation.HasUVNodes() else None)
    corners = [tuple(value - 1 for value in triangulation.Triangle(index).Get())
               for index in range(1, triangulation.NbTriangles() + 1)]
    areas = [0.5 * float(np.linalg.norm(np.cross(nodes[b] - nodes[a], nodes[c] - nodes[a]))) for a, b, c in corners]
    total = sum(areas)
    if total <= 0.0:
        return []
    target = total / max(1, count)
    from OCP.BRepGProp import BRepGProp_Face

    props = BRepGProp_Face(face.wrapped)
    found: list[Sample] = []
    for (a, b, c), area in zip(corners, areas):
        if area <= 0.0:
            continue
        cuts = max(1, int(math.ceil(math.sqrt(area / target))))
        share = area / (cuts * cuts)
        for i in range(cuts):
            for j in range(cuts - i):
                # the sub-triangles of a triangle cut ``cuts`` times along each side, by their middles
                for wa, wb in (((i + 1 / 3) / cuts, (j + 1 / 3) / cuts), ((i + 2 / 3) / cuts, (j + 2 / 3) / cuts)):
                    if wa + wb > 1.0 + 1e-12:
                        continue
                    wc = 1.0 - wa - wb
                    if uvs is not None:
                        u, v = wa * uvs[a] + wb * uvs[b] + wc * uvs[c]
                        point, normal = point_normal(face, float(u), float(v), props)
                    else:
                        point = wa * nodes[a] + wb * nodes[b] + wc * nodes[c]
                        normal = np.cross(nodes[b] - nodes[a], nodes[c] - nodes[a])
                        normal = normal / (np.linalg.norm(normal) or 1.0)
                    found.append(Sample(point, normal, share))
    return found


def triangles(shape: Any, deflection: float, angular: float = 0.5) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The shape triangulated: vertices (n, 3), triangles (m, 3) as vertex indices, and the ordinal of the
    face each triangle lies on (``TopExp.MapShapes``' order, 1-based) -- a mesh whose every triangle names its
    face, for the measures a mesh answers best (a projection, a voxel field)."""
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape

    _triangulated(shape, deflection, angular)
    faces = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape.wrapped, TopAbs_FACE, faces)
    vertices: list[np.ndarray] = []
    tris: list[np.ndarray] = []
    owners: list[np.ndarray] = []
    offset = 0
    for ordinal in range(1, faces.Extent() + 1):
        face = TopoDS.Face(faces.FindKey(ordinal))
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        if triangulation is None:
            continue
        trsf = location.Transformation()
        nodes = np.array([_xyz(triangulation.Node(i).Transformed(trsf))
                          for i in range(1, triangulation.NbNodes() + 1)])
        tri = np.array([triangulation.Triangle(i).Get() for i in range(1, triangulation.NbTriangles() + 1)]) - 1
        if face.Orientation() == TopAbs_REVERSED:
            tri = tri[:, ::-1]
        vertices.append(nodes)
        tris.append(tri + offset)
        owners.append(np.full(len(tri), ordinal))
        offset += len(nodes)
    if not tris:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=int), np.zeros(0, dtype=int)
    return np.vstack(vertices), np.vstack(tris).astype(int), np.concatenate(owners).astype(int)


def least_segments(face: Any, across: Any, whole_across: bool = False) -> list[tuple[float, np.ndarray, np.ndarray,
                                                                                   np.ndarray, np.ndarray]]:
    """The least distance between two faces (``BRepExtrema_DistShapeShape``), each of its solutions as
    (length, point on ``face``, point on ``across``, the outward normals there), shortest first. With
    ``whole_across`` the face across is its surface over its (u, v) box, four edges: a face of many edges
    (a web around many holes) costs with its edges, and a least found where it is trimmed away (in a hole)
    fails the caller's checks. Each wall and gap check keeps the solutions that pass its own (the segment's
    way, the faces' turn, a ray along it), and refines its sampled figure with the first."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.Extrema import Extrema_ExtFlag_MIN
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf

    target = across.wrapped
    if whole_across:
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
        from OCP.BRepTools import BRepTools

        umin, umax, vmin, vmax = BRepTools.UVBounds_s(target)
        made = BRepBuilderAPI_MakeFace(BRep_Tool.Surface_s(target), umin, umax, vmin, vmax, 1e-7)
        if not made.IsDone():
            return []
        target = made.Face()
    dist = BRepExtrema_DistShapeShape(face.wrapped, target, Extrema_ExtFlag_MIN)
    if not dist.IsDone() or dist.NbSolution() == 0:
        return []
    found = []
    for k in range(1, dist.NbSolution() + 1):
        a, b = dist.PointOnShape1(k), dist.PointOnShape2(k)
        pa, pb = np.array([a.X(), a.Y(), a.Z()]), np.array([b.X(), b.Y(), b.Z()])
        length = float(np.linalg.norm(pb - pa))
        if length <= 1e-9:
            continue
        here = GeomAPI_ProjectPointOnSurf(a, BRep_Tool.Surface_s(face.wrapped))
        there = GeomAPI_ProjectPointOnSurf(b, BRep_Tool.Surface_s(across.wrapped))
        if here.NbPoints() == 0 or there.NbPoints() == 0:
            continue
        _, normal = point_normal(face, *here.LowerDistanceParameters())
        _, other = point_normal(across, *there.LowerDistanceParameters())
        found.append((length, pa, pb, normal, other))
    found.sort(key=lambda row: row[0])
    return found


def rounded(values: Iterable[float], digits: int = 4) -> list[float]:
    return [round(float(value), digits) for value in values]
