"""The part a job machines, read once: exact faces from ``read_step``/``read_xbf`` and one tessellation.

:func:`read_part` returns a :class:`Part`:

* ``vertices`` (V, 3) and ``triangles`` (T, 3) in part mm: one tessellation of the occurrence at
  ``deflection_mm`` (OCCT's incremental mesher, linear and angular deflection), wound outward; and
  ``face_of_triangle`` (T,) with each triangle's face ordinal (the ``N`` of ``face N``);
* ``faces``: one :class:`FaceInfo` per face ordinal (surface type, area, centre, plane normal or cylinder axis,
  whether a cylinder is a hole), read from the exact B-rep;
* :meth:`Part.face` resolves a job's face ref to its :class:`FaceInfo` with a teaching error for a ref that is not on
  this part; :meth:`Part.ocp_face` hands back the exact ``TopoDS_Face`` (world placement).

Stdlib at import; numpy and OCP inside.

A ref is the engine's (``cadgen.engine.refs``, what ``cadgen inspect`` answers and the CAD Viewer copies): ``face 12``
on a document of one part, ``bracket/face 12`` or ``kit/arm/face 12`` under the part's occurrence, an element's name
(``bracket/f:bracket.body.3``) where the file names its faces, optionally after the document (``bracket.step#face
12``). It is resolved in the document as it is read here, never through the engine: CAM reads a file, not a model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cadgen._internal.cam.job_errors import CamJobError

__all__ = ["PART_SUFFIXES", "FaceInfo", "Part", "read_part"]

#: The documents a part is read from: a STEP, or an engine document (a model's ``@xbf``, or ``cadgen export ID
#: part.xbf``).
PART_SUFFIXES = (".step", ".stp", ".xbf")
#: The default tessellation: fine enough that sections and checks are good to a few hundredths of a millimetre.
DEFAULT_DEFLECTION_MM = 0.01
ANGULAR_DEFLECTION = 0.15
#: The kinds an element name's codes stand for, as the reader keeps them (``kernel/imported.py``).
_NAME_KINDS = (("vertex", 0), ("edge", 1), ("face", 2))


class _Document:
    """A read document's occurrence tree as the engine's refs resolve it (``refs.resolve_structure``): an assembly by
    its components, a part by its element names; each part's entry holds its node of the build123d tree."""

    def __init__(self, path: Path, tree) -> None:
        self.path = path
        self.prototypes: list[dict] = []
        self.parts: list[dict] = []
        root = self._entry(tree)
        if not root["name"]:
            root["name"] = path.stem  # several roots, or one unnamed: the document's name
        self.structure = {"tree": root, "prototypes": self.prototypes}

    def _entry(self, node) -> dict:
        children = list(getattr(node, "children", ()) or ())
        if children:
            return {"name": node.label or "", "children": [self._entry(child) for child in children]}
        from cadgen.engine.kernel.imported import ELEMENT_NAMES

        names = node.__dict__.get(ELEMENT_NAMES) or {}
        self.prototypes.append({f"{kind}Names": {str(o): text for o, text in (names.get(code) or {}).items()}
                                for kind, code in _NAME_KINDS})
        entry = {"name": node.label or "", "prototype": len(self.prototypes) - 1, "node": node}
        self.parts.append(entry)
        return entry

    def resolve(self, ref: str):
        """The one thing ``ref`` names (a ``refs.Hit``); ValueError where it names nothing, or several things."""
        from cadgen.engine.refs import resolve_structure

        hits = resolve_structure(self.structure, ref, self.path)
        if len(hits) != 1:
            raise ValueError(f"it names {len(hits)} things; give each its own entry")
        return hits[0]

@dataclass(frozen=True)
class FaceInfo:
    ref: str
    ordinal: int
    #: plane, cylinder, cone, sphere, torus, bspline, bezier, revolution, extrusion, offset, other
    surface: str
    area_mm2: float
    center_mm: tuple[float, float, float]
    #: A plane's outward normal (face orientation applied).
    normal: tuple[float, float, float] | None = None
    #: A cylinder's or a cone's axis direction and a point on it.
    axis: tuple[float, float, float] | None = None
    axis_point: tuple[float, float, float] | None = None
    radius_mm: float | None = None
    #: A cylinder whose material is outside it (a hole wall); False for a boss; None for anything else.
    hole: bool | None = None
    #: The face's tessellated bounds in part mm.
    bounds: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None


@dataclass
class Part:
    document: Path
    occurrence: str
    vertices: Any                   # (V, 3) float
    triangles: Any                  # (T, 3) int
    face_of_triangle: Any           # (T,) int, face ordinal
    faces: dict[int, FaceInfo]
    deflection_mm: float
    shape: Any = None               # build123d Shape (world placement)
    _document: Any = None
    #: The occurrence's path from the document's root: the identity a ref's part is checked against.
    _path: str = ""
    _face_map: Any = None
    _ordinals: Any = None

    @property
    def bbox(self):
        import numpy as np

        return np.asarray(self.vertices).min(axis=0), np.asarray(self.vertices).max(axis=0)

    def face(self, ref: str, where: str = "faces") -> FaceInfo:
        """The face a job names, or the teaching error."""
        try:
            hit = self._document.resolve(ref)
        except ValueError as exc:
            raise CamJobError(f"{where}: {ref} is not a face of this part ({exc}); cadgen cam features lists them"
                              ) from None
        if hit.kind != "face":
            raise CamJobError(f"{where}: {ref} is {'a part' if hit.kind is None else f'a {hit.kind}'} reference; "
                              "name faces (face 12)")
        if hit.path != self._path:
            raise CamJobError(f"{where}: {ref} is on {hit.path}, but the job machines {self.occurrence}")
        if not 1 <= hit.ordinal <= len(self.faces):
            raise CamJobError(f"{where}: {ref} is not a face of this part (it has {len(self.faces)}); cadgen cam "
                              "features lists them")
        return self.faces[hit.ordinal]

    def ordinal(self, ref: str) -> int:
        """The ordinal of a face by its canonical ref (a :class:`FaceInfo`'s ``ref``, as ``cam features`` lists it)."""
        if self._ordinals is None:
            self._ordinals = {info.ref: ordinal for ordinal, info in self.faces.items()}
        return self._ordinals[ref]

    def classify(self, points) -> Any:
        """For each part point, whether it is inside the solid (exact, OCCT's classifier)."""
        import numpy as np
        from OCP.BRepClass3d import BRepClass3d_SolidClassifier
        from OCP.gp import gp_Pnt
        from OCP.TopAbs import TopAbs_IN

        classifier = BRepClass3d_SolidClassifier(self.shape.wrapped)
        out = []
        for p in np.asarray(points, dtype=float):
            classifier.Perform(gp_Pnt(float(p[0]), float(p[1]), float(p[2])), 1e-6)
            out.append(classifier.State() == TopAbs_IN)
        return np.array(out, dtype=bool)

    def ocp_face(self, ordinal: int):
        """The exact ``TopoDS_Face`` of a face ordinal, in part coordinates."""
        from OCP.TopoDS import TopoDS

        return TopoDS.Face(self._face_map.FindKey(ordinal))



def read_part(document: Path, *, occurrence: str | None = None, deflection_mm: float | None = None) -> Part:
    """Read a STEP or xbf occurrence and tessellate it once."""
    document = Path(document)
    suffix = document.suffix.lower()
    if suffix not in PART_SUFFIXES:
        raise CamJobError(f"this command takes a {'/'.join(PART_SUFFIXES)} document: {document}")
    what = "xbf" if suffix == ".xbf" else "STEP"
    if not document.is_file():
        raise CamJobError(f"no {what} at {document}")
    from cadgen.engine.model import read_step, read_xbf

    try:
        tree = (read_xbf if suffix == ".xbf" else read_step)(document)
    except (RuntimeError, ValueError, OSError) as exc:
        # An empty, truncated or foreign file: the reader's first line says why.
        why = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
        raise CamJobError(f"{document.name} is not {'an' if what == 'xbf' else 'a'} {what} that can be read "
                          f"({why[:200]}); export it again from the CAD tool") from None
    read = _Document(document, tree)
    if occurrence:
        try:
            hit = read.resolve(occurrence)
        except ValueError as exc:
            raise CamJobError(f"occurrence {occurrence}: {exc}") from None
        if hit.kind is not None or "prototype" not in hit.node.payload:
            raise CamJobError(f"{occurrence} is not a part occurrence of {document.name}; the parts are "
                              f"{', '.join(_part_paths(read))}")
    else:
        if len(read.parts) != 1:
            raise CamJobError(f"the document has {len(read.parts)} parts; CAM machines one part: pass --occurrence "
                              f"{' or '.join(_part_paths(read)[:4])}")
        hit = read.resolve(_part_paths(read)[0])
    node = hit.node.payload["node"]
    return _tessellate(document, read, hit, node.located(node.global_location), deflection_mm or DEFAULT_DEFLECTION_MM)


def _part_paths(read: _Document) -> list[str]:
    from cadgen.engine.refs import path_text, structure_tree

    root = structure_tree(read.structure)
    return [path_text(root, part) for part in root.parts()]


#: The largest part (mm on any axis) CAM reads: ten metres, past any machine bed (job.MAX_STOCK_MM). A bigger one is
#: a units slip (a drawing in metres read as mm), and meshing it to a hundredth of a millimetre would fill the memory.
MAX_PART_MM = 10_000.0


def _check_size(what: str, box) -> None:
    """Refuse a part (a build123d BoundBox, or ``(low, high)`` points) bigger than :data:`MAX_PART_MM`, or with no
    extent at all, before it is meshed."""
    if hasattr(box, "size"):
        size = (box.size.X, box.size.Y, box.size.Z)
    else:
        size = tuple(float(h) - float(l) for l, h in zip(*box))
    if not all(math.isfinite(v) for v in size):
        raise CamJobError(f"{what} has no finite size; export it again from the CAD tool")
    if max(size) > MAX_PART_MM:
        raise CamJobError(f"{what} is {max(size) / 1000:,.1f} m across; CAM machines parts up to "
                          f"{MAX_PART_MM / 1000:g} m: check the units (cadgen reads mm)")


def _surface_name(adaptor) -> str:
    from OCP.GeomAbs import GeomAbs_SurfaceType

    names = {
        GeomAbs_SurfaceType.GeomAbs_Plane: "plane", GeomAbs_SurfaceType.GeomAbs_Cylinder: "cylinder",
        GeomAbs_SurfaceType.GeomAbs_Cone: "cone", GeomAbs_SurfaceType.GeomAbs_Sphere: "sphere",
        GeomAbs_SurfaceType.GeomAbs_Torus: "torus", GeomAbs_SurfaceType.GeomAbs_BSplineSurface: "bspline",
        GeomAbs_SurfaceType.GeomAbs_BezierSurface: "bezier",
        GeomAbs_SurfaceType.GeomAbs_SurfaceOfRevolution: "revolution",
        GeomAbs_SurfaceType.GeomAbs_SurfaceOfExtrusion: "extrusion",
        GeomAbs_SurfaceType.GeomAbs_OffsetSurface: "offset",
    }
    return names.get(adaptor.GetType(), "other")


def _tessellate(path: Path, read: _Document, hit, shape, deflection: float) -> Part:
    import numpy as np
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_REVERSED
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher

    ref = hit.ref
    wrapped = shape.wrapped
    _check_size(f"{ref} of {path.name}", shape.bounding_box())
    BRepMesh_IncrementalMesh(wrapped, deflection, False, ANGULAR_DEFLECTION, True)
    # Ordinals as the engine numbers a part's elements: TopExp.MapShapes over its shape.
    face_map = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
    TopExp.MapShapes_s(wrapped, TopAbs_FACE, face_map)
    # A face's canonical ref: its name where the file gives it one, else its ordinal, under its owner as ``inspect``
    # spells it (the document's name for a document of one part).
    names = {int(o): text for o, text in read.prototypes[hit.node.payload["prototype"]]["faceNames"].items()}
    owner = read.resolve(f"{hit.path}/face 1").ref.rpartition("/")[0] if face_map.Extent() else ref
    vertices: list = []
    triangles: list = []
    owners: list = []
    faces: dict[int, FaceInfo] = {}
    offset = 0
    for ordinal in range(1, face_map.Extent() + 1):
        face = TopoDS.Face(face_map.FindKey(ordinal))
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        reversed_ = face.Orientation() == TopAbs_REVERSED
        bounds = None
        if triangulation is not None and triangulation.NbTriangles():
            transform = location.Transformation()
            nodes = np.empty((triangulation.NbNodes(), 3))
            for i in range(1, triangulation.NbNodes() + 1):
                p = triangulation.Node(i).Transformed(transform)
                nodes[i - 1] = (p.X(), p.Y(), p.Z())
            tris = np.empty((triangulation.NbTriangles(), 3), dtype=np.int64)
            for i in range(1, triangulation.NbTriangles() + 1):
                a, b, c = triangulation.Triangle(i).Get()
                tris[i - 1] = (a - 1, c - 1, b - 1) if reversed_ else (a - 1, b - 1, c - 1)
            vertices.append(nodes)
            triangles.append(tris + offset)
            owners.append(np.full(len(tris), ordinal, dtype=np.int64))
            offset += len(nodes)
            bounds = (tuple(float(v) for v in nodes.min(axis=0)), tuple(float(v) for v in nodes.max(axis=0)))
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        centre = props.CentreOfMass()
        adaptor = BRepAdaptor_Surface(face)
        surface = _surface_name(adaptor)
        normal = axis = axis_point = radius = hole = None
        if surface == "plane":
            direction = adaptor.Plane().Axis().Direction()
            n = (direction.X(), direction.Y(), direction.Z())
            normal = tuple(-v for v in n) if reversed_ else n
            normal = tuple(round(float(v), 9) + 0.0 for v in normal)
        elif surface in ("cylinder", "cone"):
            ax = (adaptor.Cylinder() if surface == "cylinder" else adaptor.Cone()).Axis()
            d, p = ax.Direction(), ax.Location()
            axis = tuple(round(float(v), 9) + 0.0 for v in (d.X(), d.Y(), d.Z()))
            axis_point = (float(p.X()), float(p.Y()), float(p.Z()))
            if surface == "cylinder":
                radius = float(adaptor.Cylinder().Radius())
                # A hole's surface normal points at its axis: material is outside the cylinder.
                u = 0.5 * (adaptor.FirstUParameter() + adaptor.LastUParameter())
                v = 0.5 * (adaptor.FirstVParameter() + adaptor.LastVParameter())
                from OCP.gp import gp_Pnt, gp_Vec

                point, du, dv = gp_Pnt(), gp_Vec(), gp_Vec()
                adaptor.D1(u, v, point, du, dv)
                outward = du.Crossed(dv)
                if reversed_:
                    outward.Reverse()
                radial = gp_Vec(point.X() - p.X(), point.Y() - p.Y(), point.Z() - p.Z())
                axial = gp_Vec(d.X(), d.Y(), d.Z())
                radial = radial.Subtracted(axial.Multiplied(radial.Dot(axial)))
                hole = bool(outward.Dot(radial) < 0)
        element = names.get(ordinal) or f"face {ordinal}"
        faces[ordinal] = FaceInfo(
            ref=f"{owner}/{element}" if owner else element, ordinal=ordinal, surface=surface, area_mm2=float(props.Mass()),
            center_mm=(float(centre.X()), float(centre.Y()), float(centre.Z())), normal=normal, axis=axis,
            axis_point=axis_point, radius_mm=radius, hole=hole, bounds=bounds,
        )
    if not triangles:
        raise CamJobError(f"{ref} of {path.name} has no surface to machine")
    return Part(document=path, occurrence=ref, vertices=np.vstack(vertices),
                triangles=np.vstack(triangles), face_of_triangle=np.concatenate(owners), faces=faces,
                deflection_mm=deflection, shape=shape, _document=read, _path=hit.path, _face_map=face_map)
