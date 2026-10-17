"""One component's display mesh: OCCT's mesher on the exact BREP, as a GLB body.

cadgen's tessellator. ``BRepMesh_IncrementalMesh`` -- the mesher build123d's
own exporters use -- triangulates the component's exact faces at a chord
tolerance RELATIVE to the component's bounding diagonal and an angular one in
radians, discretizing every edge once so the faces either side share its
vertices. What it writes is one GLB body (``cadgen.store.meshes``): one triangle
primitive whose triangles run face by face, smooth normals from the exact
surfaces, and one polyline per model edge lying exactly on the mesh boundary.
The viewer, snapshots and mesh exports all draw these same bytes.

Face and edge ordinals are ``TopExp.MapShapes`` order on the unlocated
component -- the order its selector table and every selector use -- and the
mesher reads what the triangles do not say from the component's topology facts
(``topology_extract``: each face's surface type, each edge's display class) and
its intrinsic face colours: the one input a display mesh and a mesh
export at another tolerance are both made from (``cadgen.store.parts``). Beside
the body it gives back each face's box, its triangles', and each edge's, its
polyline's, which a part's selector table records (``selector_table``).

Every pass is checked for what OCCT gets
wrong, and a face it gets wrong is faulty. OCCT drops the odd tiny face at one
deflection and meshes it at the next. It can leave a gap inside a face (the radial
engine's cylinder head lost a sixth of a B-spline around its pole; the W16's and the
hand's had gaps OCCT said nothing of): the faces of a pass whose status says it went
wrong, or whose mesh has an open edge, are looked at for outer edges of their
triangles that are no part of their own edges. It grids a cylinder, cone, sphere or
torus by formula without measuring it: across a thin round swept along a long arc
(the motorbike's fender) the grid can skip the round's inner rows and span it five
times the deflection off its surface, so each of those faces is measured exactly.
And it measures a freeform face as it meshes it, yet left some (an F1 floor panel,
the hand's palm, a Juno forearm) up to 48 times the deflection off, where main's
tessellator held them: a screen of each freeform face's triangles, from their
corners' exact normals, picks the ones that are measured exactly. A component with
a faulty face is meshed again, whole and finer, in a fixed order -- unless its first
pass took seconds (an F1 floor's B-spline), when a finer whole pass would cost it
far more than its faulty faces are worth and its freeform faces go unmeasured. A
face no whole pass meshes
is one OCCT refuses -- it reads the face's boundary as crossing itself or open, what
a boolean's leftovers do to a valid face -- and no setting or repair of OCCT's
meshes it, so it is tessellated over its own parameters as cadgen's earlier
tessellator did (``face_fallback``), against the meshed neighbours, and kept when
its triangles cover the face's own area; so is any face still faulty, on the pass
that left the fewest open edges, where its new triangles lie on its surface, fold no
neighbour out, and leave the mesh no more open than it was. Every component is meshed from no triangles, whatever its stored BREP
carries. Last, a needle OCCT's Delaunay folds over its neighbour across a B-spline,
facing away from all three of its corners' normals, is unfolded by flipping the edge
the two share. A face that still has none is left out of the
component, which is drawn without it, and the body names it (``unmeshedFaces``,
``cadgen.store.meshes``): one face no mesher covers never fails a view, a list or
an export of the whole document, and each of them says which faces of which part
it does not draw or write. A face smaller than the mesh can resolve -- its area
under the square of the chord tolerance, inside the error every triangle may
carry -- may have none and is not named, and such a face earns no finer pass. Its
area is the first pass's triangles' where they cover at least that much of it, and
measured exactly (GProps) only where they do not: a face the pass left empty, or all
but empty. Any
failure inside OCCT is the component's error. A component with no faces meshes
nothing: its edges are sampled from their own curves.

The arrays leave OCCT through its own glTF writer (``RWGltf_CafWriter``, one
primitive per face), not one Python call per vertex: that is what keeps a large
component's extraction in milliseconds. A component whose faces cannot be
matched to the writer's primitives one for one (a face its explorer meets
twice, for instance) is read face by face instead, which is slower and the same:
both read normals OCCT computed onto the triangulation beforehand.
"""

from __future__ import annotations

import json
import math
import struct
import tempfile
import time
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np

# Two points closer than this, relative to the component's diagonal, are one
# point: the floor under the scale of a component with no extent.
_SCALE_FLOOR = 1e-6
# The deflections, as multiples of the component's, at which a component whose
# pass left a face empty or off its surface is meshed again, whole: the first that
# leaves none wins.
_RETRY_SCALES = (0.5, 0.25)
# How far a face's triangles may lie from its exact surface, as a multiple of the
# deflection the face can be held to, before it counts as off its surface.
_STRAY_FACTOR = 2.0
# The surfaces OCCT grids by formula without measuring, by the selector table's names:
# only their faces are measured against their surfaces after a pass.
_GRIDDED = frozenset({"cylinder", "cone", "sphere", "torus"})
# OCCT's status bits for a pass that did not mesh every face as it was asked to
# (IMeshData_OpenWire, _SelfIntersectingWire, _Failure): such a pass's faces are looked
# at for a gap inside them, as are a pass's whose mesh has an open edge.
_TROUBLED_PASS = 0x1 | 0x2 | 0x4
# The triangles of a freeform face its screen ranks worst, which are measured exactly.
_FREEFORM_SAMPLES = 16
# A component whose first pass takes longer than this -- an F1 floor's B-spline of 3,919
# by 38 poles took ten seconds and a gigabyte -- is not meshed again whole, which would
# cost it four times over: its faulty faces go straight to the tessellator.
_RETRY_SECONDS = 2.0
# The triangles the needle check takes at a time, to bound its memory on a huge part.
_NEEDLE_CHUNK = 1 << 18
# A face OCCT refuses is tessellated over its own parameters; its triangles are kept
# when they cover the face's own area to this share -- a chord across a curved
# boundary takes area off a small face, nothing near this much.
_FALLBACK_AREA_TOLERANCE = 0.25


class MeshProductionError(ValueError):
    """A component OCCT could not mesh completely."""


class MeshedComponent(NamedTuple):
    """One component meshed: its GLB ``body``, and ``boxes`` -- ``{"faces": {ordinal: box},
    "edges": {ordinal: box}}``, each box ``[xmin, ymin, zmin, xmax, ymax, zmax]`` -- a face's
    from its triangles (from its edges' polylines when it has none), an edge's from its
    polyline; an element with neither has no box."""

    body: bytes
    boxes: dict[str, dict[int, list[float]]]


def _bounding_diagonal(topods) -> float:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(topods, box, False)
    if box.IsVoid():
        return _SCALE_FLOOR
    x0, y0, z0, x1, y1, z1 = box.Get()
    diagonal = math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2)
    return diagonal if math.isfinite(diagonal) and diagonal > _SCALE_FLOOR else _SCALE_FLOOR


def _maps(topods):
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    faces, edges = TopTools_IndexedMapOfShape(), TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(topods, TopAbs_FACE, faces)
    TopExp.MapShapes_s(topods, TopAbs_EDGE, edges)
    return faces, edges


def _faulty(faces: dict, face_map, required: list[int], kinds: dict[int, str], deflection: float,
            gaps: bool, freeform: bool) -> list[int]:
    """Those of ``required`` the pass left without triangles; with a gap inside them, when
    ``gaps`` says the pass may have left one (``_holed``); or off their surface: a cylinder,
    cone, sphere or torus by its closed form (``_surface_distance``), and -- when
    ``freeform`` -- any other curved face where a screen of its triangles finds they may be
    (``_freeform_distance``). ``kinds`` is each face's surface type, as the selector table
    names it."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepMesh import BRepMesh_ShapeTool
    from OCP.TopoDS import TopoDS

    holed = (_holed(faces, face_map, [ordinal for ordinal in required if ordinal in faces], deflection)
             if gaps else set())
    # The part's freeform faces are screened together; only those it cannot clear are looked at alone.
    suspects = (_screened(faces, [ordinal for ordinal in required if ordinal in faces and ordinal not in holed
                                  and kinds.get(ordinal) not in (None, "plane", *_GRIDDED)],
                          _STRAY_FACTOR * deflection) if freeform else set())
    faulty = []
    for ordinal in required:
        if ordinal not in faces or ordinal in holed:
            faulty.append(ordinal)
            continue
        kind = kinds.get(ordinal)
        if kind not in _GRIDDED and ordinal not in suspects:
            continue
        face = TopoDS.Face_s(face_map.FindKey(ordinal))
        positions, normals, triangles = faces[ordinal]

        # A face is held to the component's deflection, or to what no pass can do better than
        # where that is coarser: OCCT's floor of twice the face's own tolerance (radial's
        # boolean-cut sphere, its edges 0.16 mm loose, at a 0.08 mm deflection), and the
        # spacing of the single-precision positions it is read from (a part a kilometre from
        # its origin rounds to 0.06 mm).
        def limit() -> float:
            return _STRAY_FACTOR * max(deflection, 2.0 * BRepMesh_ShapeTool.MaxFaceTolerance_s(face),
                                       float(np.spacing(np.abs(positions).max())))

        if kind in _GRIDDED:
            distance = _surface_distance(BRepAdaptor_Surface(face, False), positions, triangles)
            if distance is not None and distance > _STRAY_FACTOR * deflection and distance > limit():
                faulty.append(ordinal)
        else:
            bound = limit()
            distance = _freeform_distance(face, positions, normals, triangles, bound)
            if distance is not None and distance > bound:
                faulty.append(ordinal)
    return faulty


def _holed(faces: dict, face_map, ordinals: list[int], deflection: float) -> set[int]:
    """Those of ``ordinals`` whose triangles leave a gap inside the face: outer edges of
    theirs, longer than the deflection together, that are no segment of the discretization
    of the face's own edges (either way round a seam). OCCT reports a failure when it leaves
    one -- the radial engine's cylinder head lost a sixth of a B-spline face around its pole
    at every deflection -- so a pass is looked at only when it does."""
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    holed = set()
    for ordinal in ordinals:
        positions, _normals, triangles = faces[ordinal]
        face = TopoDS.Face_s(face_map.FindKey(ordinal))
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        size = len(positions)
        corners = triangles.astype(np.int64)
        pairs = np.sort(np.concatenate([corners[:, [0, 1]], corners[:, [1, 2]], corners[:, [2, 0]]]), axis=1)
        keys, counts = np.unique(pairs[:, 0] * size + pairs[:, 1], return_counts=True)
        segments = set()
        explorer = TopExp_Explorer(face, TopAbs_EDGE)
        while explorer.More():
            edge = TopoDS.Edge_s(explorer.Current())
            for way in (edge, TopoDS.Edge_s(edge.Reversed())):
                polygon = BRep_Tool.PolygonOnTriangulation_s(way, triangulation, location)
                if polygon is not None:
                    nodes = polygon.Nodes()
                    run = [nodes.Value(k) - 1 for k in range(nodes.Lower(), nodes.Upper() + 1)]
                    segments.update(min(a, b) * size + max(a, b) for a, b in zip(run, run[1:]))
            explorer.Next()
        gaps = np.array([key for key in keys[counts == 1].tolist() if key not in segments], np.int64)
        if len(gaps):
            ends = positions.astype(np.float64)
            if np.linalg.norm(ends[gaps // size] - ends[gaps % size], axis=1).sum() > deflection:
                holed.add(ordinal)
    return holed


def _surface_distance(surface, positions: np.ndarray, triangles: np.ndarray) -> float | None:
    """How far the triangles' centres and edge midpoints lie from ``surface`` at most, when
    it is the cylinder, cone, sphere or torus OCCT grids without measuring: their closed
    forms measure it exactly. None for any other surface, which OCCT measures itself."""
    from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Sphere, GeomAbs_Torus

    kind = surface.GetType()
    if kind not in (GeomAbs_Cylinder, GeomAbs_Cone, GeomAbs_Sphere, GeomAbs_Torus) or not len(triangles):
        return None
    corners = positions.astype(np.float64)[triangles]
    points = np.concatenate([corners.mean(axis=1), ((corners + np.roll(corners, 1, axis=1)) / 2).reshape(-1, 3)])

    def about(axis, origin: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Each point's height along ``axis`` from ``origin``, and its distance from the axis."""
        direction = _xyz(axis.Direction())
        offset = points - origin
        height = offset @ direction
        return height, np.linalg.norm(offset - np.outer(height, direction), axis=1)

    if kind == GeomAbs_Sphere:
        sphere = surface.Sphere()
        gap = np.linalg.norm(points - _xyz(sphere.Location()), axis=1) - sphere.Radius()
    elif kind == GeomAbs_Cylinder:
        cylinder = surface.Cylinder()
        gap = about(cylinder.Axis(), _xyz(cylinder.Location()))[1] - cylinder.Radius()
    elif kind == GeomAbs_Torus:
        torus = surface.Torus()
        height, radial = about(torus.Axis(), _xyz(torus.Location()))
        gap = np.hypot(radial - torus.MajorRadius(), height) - torus.MinorRadius()
    else:
        # In each point's plane through the axis, the distance from the line through the apex.
        cone = surface.Cone()
        height, radial = about(cone.Axis(), _xyz(cone.Apex()))
        slope = abs(cone.SemiAngle())
        gap = radial * math.cos(slope) - np.abs(height) * math.sin(slope)
    return float(np.abs(gap).max())


def _xyz(point) -> np.ndarray:
    return np.array([point.X(), point.Y(), point.Z()])


def _edge_sags(points: np.ndarray, normals: np.ndarray, corners: np.ndarray) -> np.ndarray:
    """Each triangle edge's sag as its ends' normals tell it -- its length times the angle
    between them, over eight, as a circle's -- the triangles' first edges, then their
    second, then their third."""
    ends = np.concatenate([corners[:, [0, 1]], corners[:, [1, 2]], corners[:, [2, 0]]])
    first, second = normals[ends[:, 0]], normals[ends[:, 1]]
    lengths = np.linalg.norm(first, axis=1) * np.linalg.norm(second, axis=1)
    cosines = np.clip((first * second).sum(axis=1) / np.maximum(lengths, 1e-30), -1.0, 1.0)
    return np.linalg.norm(points[ends[:, 0]] - points[ends[:, 1]], axis=1) * np.arccos(cosines) / 8


def _screened(faces: dict, ordinals: list[int], limit: float) -> set[int]:
    """Those of ``ordinals`` with an edge the screen says sags more than ``limit``, the
    faces screened together in one pass over their joined triangles."""
    blocks = [faces[ordinal] for ordinal in ordinals if len(faces[ordinal][2])]
    kept = [ordinal for ordinal in ordinals if len(faces[ordinal][2])]
    if not blocks:
        return set()
    starts = np.cumsum([0] + [len(block[0]) for block in blocks])[:-1]
    points = np.concatenate([block[0] for block in blocks]).astype(np.float64)
    normals = np.concatenate([block[1] for block in blocks]).astype(np.float64)
    corners = np.concatenate([block[2].astype(np.int64) + start for block, start in zip(blocks, starts)])
    worst = _edge_sags(points, normals, corners).reshape(3, -1).max(axis=0)
    firsts = np.cumsum([0] + [len(block[2]) for block in blocks])[:-1]
    return {ordinal for ordinal, sag in zip(kept, np.maximum.reduceat(worst, firsts)) if sag > limit}


def _freeform_distance(face, positions: np.ndarray, normals: np.ndarray, triangles: np.ndarray,
                       bound: float) -> float | None:
    """How far a freeform face's triangles lie from its surface at most, where a screen says
    some may lie further than ``bound``; None where it says none can. OCCT holds a freeform
    face's triangles to the deflection as it meshes it, but on some B-splines -- an F1 floor
    panel, the hand's palm, a Juno forearm -- it left them up to 48 times the deflection off,
    where main's tessellator held them. The screen reads each edge's sag from its ends'
    normals, which OCCT takes from the exact surface: its length times the angle between them
    over eight, as a circle's. The triangles it ranks worst are measured exactly, each
    centre and edge midpoint projected onto the surface from its own parameters."""
    from OCP.BRep import BRep_Tool
    from OCP.ShapeAnalysis import ShapeAnalysis_Surface
    from OCP.TopLoc import TopLoc_Location
    from OCP.gp import gp_Pnt, gp_Pnt2d

    corners = triangles.astype(np.int64)
    points = positions.astype(np.float64)
    sags = _edge_sags(points, normals.astype(np.float64), corners)
    if not len(sags) or sags.max() <= bound:
        return None
    location = TopLoc_Location()
    triangulation = BRep_Tool.Triangulation_s(face, location)
    if triangulation is None or not triangulation.HasUVNodes():
        return None
    worst = corners[np.argsort(-sags.reshape(3, -1).max(axis=0))[:_FREEFORM_SAMPLES]]
    uv = {node: triangulation.UVNode(node + 1) for node in np.unique(worst).tolist()}
    surface = BRep_Tool.Surface_s(face, TopLoc_Location())
    to_surface = location.Transformation().Inverted()
    projector = ShapeAnalysis_Surface(surface)
    precision = bound * 1e-4
    farthest = 0.0
    for a, b, c in worst.tolist():
        for nodes in ((a, b, c), (a, b), (b, c), (c, a)):
            point = gp_Pnt(*points[list(nodes)].mean(axis=0)).Transformed(to_surface)
            seed = gp_Pnt2d(sum(uv[n].X() for n in nodes) / len(nodes), sum(uv[n].Y() for n in nodes) / len(nodes))
            projector.NextValueOfUV(seed, point, precision, bound)
            farthest = max(farthest, projector.Gap())
    return farthest


def _triangle_area(positions: np.ndarray, triangles: np.ndarray) -> float:
    corners = positions[triangles].astype(np.float64)
    return float(0.5 * np.linalg.norm(np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]),
                                      axis=1).sum())


def _required(faces: dict, count: int, deflection: float, exact_area) -> list[int]:
    """The faces of ``count`` that must have triangles: those the mesh can resolve, their area
    at least the square of the deflection -- a face's triangles' (``faces``, a pass read back)
    where they cover that much, else its exact area (``exact_area(ordinal)``), measured only
    for a face the pass left empty or all but empty. A smaller face may have none, and earns no
    finer pass: a watch case's 0.002 mm² sliver left a 1,529-face case meshed three times
    over, fifteen times as long, for a face under what the mesh can resolve."""
    floor = deflection * deflection
    return [ordinal for ordinal in range(1, count + 1)
            if (ordinal in faces and _triangle_area(faces[ordinal][0], faces[ordinal][2]) >= floor)
            or exact_area(ordinal) >= floor]


def _mesh(topods, face_map, kinds: dict[int, str], deflection: float,
          angle: float) -> tuple[dict[int, tuple], list[int]]:
    """Mesh the component and read its faces back -- and the faces that must have triangles,
    as its first pass decides (``_required``) -- and while one of those is faulty
    (``_faulty``: empty, holed, or off its surface), mesh it all again, cleaned, at the retry
    deflections -- unless its first pass took over ``_RETRY_SECONDS``, when its freeform
    faces go unmeasured too. A face no whole pass gets right -- one OCCT refuses, or keeps
    meshing wrong -- is tessellated over its own parameters against its meshed neighbours, on
    the pass with the fewest open edges, then the fewest faulty faces, then the coarsest: a
    finer pass can close a gap the component's own deflection leaves (an actuator's 32 open
    edges at a quarter of it, 443 at its own). Each face's exact area is measured once, when
    first asked for."""
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRepTools import BRepTools
    from OCP.GProp import GProp_GProps
    from OCP.Precision import Precision
    from OCP.TopoDS import TopoDS

    faces: dict = {}
    required: list[int] = []
    passes: list[tuple[int, int, float]] = []
    quick = True
    areas: dict[int, float] = {}

    def exact_area(ordinal: int) -> float:
        if ordinal not in areas:
            props = GProp_GProps()
            try:
                BRepGProp.SurfaceProperties_s(TopoDS.Face_s(face_map.FindKey(ordinal)), props)
                areas[ordinal] = float(props.Mass())
            except Exception:  # noqa: BLE001 - a face the kernel cannot measure is held to nothing
                areas[ordinal] = 0.0
        return areas[ordinal]

    def mesh(scale: float) -> list[int]:
        nonlocal faces, quick, required
        started = time.perf_counter()
        # OCCT refuses a deflection under its confusion tolerance.
        status = BRepMesh_IncrementalMesh(topods, max(deflection * scale, Precision.Confusion_s()),
                                          False, angle, True).GetStatusFlags()
        if not passes:
            quick = time.perf_counter() - started <= _RETRY_SECONDS
        faces = _read_faces(topods, face_map)
        if not passes:
            required = _required(faces, face_map.Extent(), deflection, exact_area)
        opened = _open_edges(faces)
        faulty = _faulty(faces, face_map, required, kinds, deflection, bool(status & _TROUBLED_PASS) or opened > 0,
                         quick)
        passes.append((opened, len(faulty), -scale))
        return faulty

    # A stored BREP can carry triangles some earlier tool made: OCCT keeps those it deems fine,
    # whatever they are, so every component is meshed from none.
    BRepTools.Clean_s(topods)
    faulty = mesh(1.0)
    retries = _RETRY_SCALES if quick else ()
    for scale in retries:
        if not faulty:
            return faces, required
        BRepTools.Clean_s(topods)
        faulty = mesh(scale)
    if not faulty:
        return faces, required
    best = -min(passes)[2]
    if best != -passes[-1][2]:
        BRepTools.Clean_s(topods)
        faulty = mesh(best)
    _tessellate(topods, face_map, faulty, kinds, deflection, angle, exact_area)
    return _read_faces(topods, face_map), required


def _read_faces(topods, face_map) -> dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Each meshed face's (positions, normals, local triangles), by ordinal."""
    triangulated = _triangulated_faces(topods, face_map)
    if not triangulated:
        return {}
    faces = _faces_from_gltf(topods, triangulated)
    return _faces_one_by_one(triangulated) if faces is None else faces


def _tessellate(topods, face_map, ordinals: list[int], kinds: dict[int, str], deflection: float, angle: float,
                exact_area) -> None:
    """Give each face of ``ordinals`` the triangles ``face_fallback`` builds over its
    parameters, when they cover its own area (``exact_area(ordinal)``) to
    ``_FALLBACK_AREA_TOLERANCE``; a face
    left without keeps what OCCT gave it -- none, for a face it refuses, which the body
    names. The faces OCCT refused go first, then the ones it meshed wrong, each group
    together, and a group keeps its triangles only if they did no harm: the tessellator
    splits its neighbours' triangles to meet its own (and refuses where a split would fold
    a neighbour out), and where a split goes wrong the faces part (an airframe skin forced
    through it opened 884 edges). So a group whose triangles lie off their surface, or --
    for faces OCCT did mesh -- leave the part with more open edges, is undone, every split
    with it, and its faces keep what OCCT gave them. The part is read twice a group,
    however many faces it has."""
    from cadgen._internal import face_fallback
    from OCP.BRep import BRep_Builder, BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    def tessellated(ordinal: int, face):
        area = exact_area(ordinal)
        return face_fallback.tessellate_face(
            topods, face, deflection, angle, lambda covered: abs(covered - area) <= _FALLBACK_AREA_TOLERANCE * area)

    def group(members: list[tuple[int, Any, Any]], may_open: bool) -> None:
        opened = None if may_open else _open_edges(_read_faces(topods, face_map))
        taken = []
        for ordinal, face, previous in members:
            if (result := tessellated(ordinal, face)) is not None:
                BRep_Builder().UpdateFace(face, result[0])
                taken.append((ordinal, face, previous, result[1]))
        if not taken:
            return
        after = _read_faces(topods, face_map)
        # A tessellated face has no discretization on its edges for ``_holed`` to read.
        harmed = (_faulty(after, face_map, [ordinal for ordinal, *_rest in taken], kinds, deflection, False, True)
                  or (opened is not None and _open_edges(after) > opened))
        if harmed:
            # Last split first: a later face may have split an earlier one's triangles.
            for _ordinal, face, previous, undo in reversed(taken):
                undo()
                BRep_Builder().UpdateFace(face, previous)

    members = [(ordinal, face, BRep_Tool.Triangulation_s(face, TopLoc_Location()))
               for ordinal, face in ((ordinal, TopoDS.Face_s(face_map.FindKey(ordinal))) for ordinal in ordinals)]
    for refused, may_open in ((True, True), (False, False)):
        chosen = [member for member in members if (member[2] is None) == refused]
        if chosen:
            group(chosen, may_open)



def _facing(positions: np.ndarray, normals: np.ndarray, triangles) -> np.ndarray:
    """Per triangle, each corner's normal dotted with the triangle's facet, (n, 3)."""
    corners = positions[triangles].astype(np.float64)
    facets = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    return np.einsum("tj,tkj->tk", facets, normals[triangles].astype(np.float64))


def _unfold_needles(positions: np.ndarray, normals: np.ndarray, triangles: np.ndarray) -> None:
    """Unfold, in place, each triangle that faces away from all three of its corners'
    normals. OCCT's Delaunay leaves the odd needle across a B-spline whose corners lie in a
    line in its parameters folded over its neighbour -- a bracelet link's five, half a
    deflection wide and a thousand long -- and a two-sided material draws it dark. The edge
    it shares with the triangle across its longest side is flipped, the two becoming the two
    halves of the quad their four corners make, where both halves then face their corners'
    normals. (Wound the other way instead, its edges would run the way its neighbours' do,
    which a mesh export's orientation checks refuse.)"""
    folded = np.concatenate([np.flatnonzero((_facing(positions, normals, triangles[start:start + _NEEDLE_CHUNK]) < 0)
                                            .all(axis=1)) + start
                             for start in range(0, len(triangles), _NEEDLE_CHUNK)] or [np.zeros(0, np.int64)])
    if not len(folded):
        return
    # Every directed edge, by the triangle that runs it: the one across a needle's side runs it back.
    size = len(positions)
    corners = triangles.astype(np.int64)
    keys = np.concatenate([corners[:, 0] * size + corners[:, 1], corners[:, 1] * size + corners[:, 2],
                           corners[:, 2] * size + corners[:, 0]])
    order = np.argsort(keys, kind="stable")
    keys, owners = keys[order], np.tile(np.arange(len(corners)), 3)[order]
    changed: set[int] = set()
    for needle in folded.tolist():
        if needle in changed:
            continue
        a, b, c = (int(n) for n in triangles[needle])
        points = positions[[a, b, c]].astype(np.float64)
        longest = int(np.argmax(np.linalg.norm(points - np.roll(points, -1, axis=0), axis=1)))
        a, b, c = [(a, b, c), (b, c, a), (c, a, b)][longest]
        at = int(np.searchsorted(keys, b * size + a))
        if at == len(keys) or keys[at] != b * size + a:
            continue
        across = int(owners[at])
        if across in changed or across == needle:
            continue
        d = next(int(n) for n in triangles[across] if int(n) not in (a, b))
        halves = np.array([[a, d, c], [d, b, c]], triangles.dtype)
        if (_facing(positions, normals, halves) > 0).all():
            triangles[needle], triangles[across] = halves
            changed.update((needle, across))


def _open_edges(faces: dict) -> int:
    """How many edges of the part's mesh, its faces welded where their vertices are one
    point, only one triangle has: where a closed part is cracked or holed."""
    if not faces:
        return 0
    blocks = list(faces.values())
    # Adding zero makes a negative zero positive: one point, one welded vertex.
    positions = np.ascontiguousarray(np.concatenate([block[0] for block in blocks]).astype(np.float32) + np.float32(0))
    starts = np.cumsum([0] + [len(block[0]) for block in blocks])[:-1]
    triangles = np.concatenate([block[2].astype(np.int64) + start for block, start in zip(blocks, starts)])
    _, welded = np.unique(positions.view(np.dtype((np.void, 12))).ravel(), return_inverse=True)
    corners = welded.ravel()[triangles]
    pairs = np.sort(np.concatenate([corners[:, [0, 1]], corners[:, [1, 2]], corners[:, [2, 0]]]), axis=1)
    pairs = pairs[pairs[:, 0] != pairs[:, 1]]  # a pole's run of vertices is one point
    _, counts = np.unique(pairs[:, 0] * (int(welded.max()) + 1) + pairs[:, 1], return_counts=True)
    return int((counts == 1).sum())


def _triangulated_faces(topods, face_map) -> list[tuple[int, Any, Any, Any]]:
    """(ordinal, face, triangulation, location) in explorer order, as the glTF writer meets them.

    Each triangulation gets OCCT's normals first, from the exact surface where it
    has one and from the triangles around a node where it does not (a cone's apex,
    a revolved profile's pole): left to the writer, such a node's normal is a
    fixed axis, often pointing into the solid."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepLib import BRepLib_ToolTriangulatedShape
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    found = []
    explorer = TopExp_Explorer(topods, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        if triangulation is not None and triangulation.NbTriangles() > 0:
            if not triangulation.HasNormals():
                BRepLib_ToolTriangulatedShape.ComputeNormals_s(face, triangulation)
            found.append((face_map.FindIndex(face), face, triangulation, location))
        explorer.Next()
    return found


def _faces_from_gltf(topods, triangulated) -> dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] | None:
    """Each face's (positions, normals, local triangles), written by OCCT's glTF writer.

    None when the writer's primitives cannot be matched to ``triangulated`` one
    for one; the caller then reads the faces itself."""
    from OCP.Message import Message_ProgressRange
    from OCP.RWGltf import RWGltf_CafWriter
    from OCP.RWMesh import RWMesh_CoordinateSystem
    from OCP.TColStd import TColStd_IndexedDataMapOfStringString
    from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    document = TDocStd_Document(TCollection_ExtendedString("cadgen-mesh"))
    XCAFDoc_DocumentTool.ShapeTool_s(document.Main()).AddShape(topods, False)
    with tempfile.TemporaryDirectory(prefix="cadgen-mesh-") as folder:
        path = Path(folder) / "component.glb"
        writer = RWGltf_CafWriter(TCollection_AsciiString(str(path)), True)
        writer.SetMergeFaces(False)
        converter = writer.ChangeCoordinateSystemConverter()
        converter.SetInputCoordinateSystem(RWMesh_CoordinateSystem.RWMesh_CoordinateSystem_Zup)
        converter.SetOutputCoordinateSystem(RWMesh_CoordinateSystem.RWMesh_CoordinateSystem_Zup)
        if not writer.Perform(document, TColStd_IndexedDataMapOfStringString(), Message_ProgressRange()):
            return None
        data = path.read_bytes()
    json_length = struct.unpack_from("<I", data, 12)[0]
    gltf = json.loads(data[20:20 + json_length])
    binary = memoryview(data)[20 + json_length + 8:]

    def view(accessor_index: int, dtype, width: int) -> np.ndarray:
        accessor = gltf["accessors"][accessor_index]
        buffer_view = gltf["bufferViews"][accessor["bufferView"]]
        offset = buffer_view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        return np.frombuffer(binary, dtype, accessor["count"] * width, offset)

    # The writer puts a component's free edges and vertices beside its faces, as
    # LINES and POINTS primitives: the faces are its TRIANGLES (mode 4, the default).
    primitives = [primitive for mesh in gltf.get("meshes", []) for primitive in mesh["primitives"]
                  if primitive.get("mode", 4) == 4]
    if len(primitives) != len(triangulated):
        return None
    # The writer places a located shape with a node transform; the component is
    # unlocated, so every node must be the identity for the arrays to be its own.
    for node in gltf.get("nodes", []):
        if any(name in node for name in ("matrix", "translation", "rotation", "scale")):
            matrix = node.get("matrix")
            if matrix is None or not np.allclose(matrix, np.eye(4).ravel()):
                return None
    faces = {}
    for (ordinal, _face, triangulation, _location), primitive in zip(triangulated, primitives):
        positions = view(primitive["attributes"]["POSITION"], np.float32, 3).reshape(-1, 3)
        normals = view(primitive["attributes"]["NORMAL"], np.float32, 3).reshape(-1, 3)
        index_accessor = gltf["accessors"][primitive["indices"]]
        dtype = {5121: np.uint8, 5123: np.uint16, 5125: np.uint32}[index_accessor["componentType"]]
        triangles = view(primitive["indices"], dtype, 1).astype(np.uint32).reshape(-1, 3)
        if (len(positions) != triangulation.NbNodes() or len(triangles) != triangulation.NbTriangles()
                or ordinal in faces):
            return None
        faces[ordinal] = (positions, normals, triangles)
    return faces


def _faces_one_by_one(triangulated) -> dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """The same arrays read face by face: placed positions, normals turned to the face's
    orientation, and triangles wound to it -- and turned once more by a mirroring
    placement, which carries the normals itself, as the glTF writer does."""
    from OCP.TopAbs import TopAbs_REVERSED

    faces = {}
    for ordinal, face, triangulation, location in triangulated:
        if ordinal in faces:
            continue
        transform = location.Transformation()
        count = triangulation.NbNodes()
        positions = np.empty((count, 3), np.float32)
        normals = np.empty((count, 3), np.float32)
        flip = -1.0 if face.Orientation() == TopAbs_REVERSED else 1.0
        turn = (flip < 0) != (transform.VectorialPart().Determinant() < 0)
        for node in range(1, count + 1):
            point = triangulation.Node(node).Transformed(transform)
            normal = triangulation.Normal(node).Transformed(transform)
            positions[node - 1] = (point.X(), point.Y(), point.Z())
            normals[node - 1] = (flip * normal.X(), flip * normal.Y(), flip * normal.Z())
        triangles = np.empty((triangulation.NbTriangles(), 3), np.uint32)
        for index in range(1, triangulation.NbTriangles() + 1):
            a, b, c = triangulation.Triangle(index).Get()
            triangles[index - 1] = (a - 1, c - 1, b - 1) if turn else (a - 1, b - 1, c - 1)
        faces[ordinal] = (positions, normals, triangles)
    return faces


def _edge_faces(topods, face_map, edge_map) -> list[list[int]]:
    """Each edge's adjacent face ordinals, deduplicated (a seam meets its face twice)."""
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer

    adjacent: list[list[int]] = [[] for _ in range(edge_map.Extent() + 1)]
    for face_ordinal in range(1, face_map.Extent() + 1):
        explorer = TopExp_Explorer(face_map.FindKey(face_ordinal), TopAbs_EDGE)
        while explorer.More():
            edge_ordinal = edge_map.FindIndex(explorer.Current())
            if edge_ordinal and face_ordinal not in adjacent[edge_ordinal]:
                adjacent[edge_ordinal].append(face_ordinal)
            explorer.Next()
    return adjacent


def _edge_polyline(edge, adjacent: list[int], face_map, faces, deflection: float, angle: float) -> np.ndarray | None:
    """The edge's points: its discretization on an adjacent face's mesh, else its own curve."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_TangentialDeflection
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    if BRep_Tool.Degenerated_s(edge):
        return None
    for face_ordinal in adjacent:
        if face_ordinal not in faces:
            continue
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(TopoDS.Face_s(face_map.FindKey(face_ordinal)), location)
        polygon = BRep_Tool.PolygonOnTriangulation_s(edge, triangulation, location) if triangulation is not None else None
        if polygon is None:
            continue
        nodes = polygon.Nodes()
        indices = np.fromiter((nodes.Value(k) - 1 for k in range(nodes.Lower(), nodes.Upper() + 1)),
                              np.int64, nodes.Length())
        return faces[face_ordinal][0][indices]
    # A free edge, or one no face meshed along: sample its own exact curve.
    curve = BRepAdaptor_Curve(edge)
    sampler = GCPnts_TangentialDeflection(curve, angle, deflection)
    if sampler.NbPoints() < 2:
        return None
    return np.array([[(point := sampler.Value(k)).X(), point.Y(), point.Z()]
                     for k in range(1, sampler.NbPoints() + 1)], np.float32)


def mesh_component(topods, facts: dict, face_colors: dict, *, part: str, chord: float,
                   angle: float) -> MeshedComponent:
    """Mesh one unlocated component: its GLB body, which names ``part``, and its faces' and
    edges' boxes (:class:`MeshedComponent`).

    ``topods`` is a private decode of the component's BREP: meshing stores its
    triangulation on the shape, so it must not be a shape anything else holds.
    ``facts`` are the component's topology facts (its faces' surface types, its edges'
    classes) and ``face_colors`` its intrinsic face colours by ordinal, in the same
    ordinals. A failure inside OCCT is the component's ``MeshProductionError``.
    """
    try:
        return _mesh_component(topods, facts, face_colors, part=part, chord=chord, angle=angle)
    except Exception as error:  # noqa: BLE001 - OCCT's own, told apart below
        # OCP raises OCCT's exception classes, whose Python bases differ between
        # platform wheels (Standard_ConstructionError is no Standard_Failure): one is
        # known by the module its class comes from.
        if not type(error).__module__.startswith("OCP"):
            raise
        raise MeshProductionError(f"OCCT failed on the component: {type(error).__name__}: {error}") from error


def _box(points: np.ndarray) -> list[float]:
    low, high = points.min(axis=0), points.max(axis=0)
    return [float(low[0]), float(low[1]), float(low[2]), float(high[0]), float(high[1]), float(high[2])]


def _boxes(faces: dict, edges: list, adjacent: list[list[int]]) -> dict[str, dict[int, list[float]]]:
    """Each meshed face's box (its triangles'), each edge's (its polyline's), and each face a
    pass left without triangles boxed by its edges' polylines."""
    face_boxes = {ordinal: _box(block[0]) for ordinal, block in faces.items() if len(block[0])}
    edge_boxes = {ordinal: _box(polyline) for ordinal, _visibility, polyline in edges}
    bounding: dict[int, list[list[float]]] = {}
    for edge_ordinal, face_ordinals in enumerate(adjacent):
        box = edge_boxes.get(edge_ordinal)
        if box is None:
            continue
        for face_ordinal in face_ordinals:
            if face_ordinal not in face_boxes:
                bounding.setdefault(face_ordinal, []).append(box)
    for face_ordinal, found in bounding.items():
        face_boxes[face_ordinal] = [min(box[axis] for box in found) for axis in range(3)] + \
                                   [max(box[axis] for box in found) for axis in range(3, 6)]
    return {"faces": face_boxes, "edges": edge_boxes}


def _mesh_component(topods, facts: dict, face_colors: dict, *, part: str, chord: float,
                    angle: float) -> MeshedComponent:
    from cadgen._internal.glb_topology import STEP_EDGE_VISIBILITY_CLASSES
    from cadgen.store.meshes import encode_payload
    from OCP.Precision import Precision
    from OCP.TopoDS import TopoDS

    face_map, edge_map = _maps(topods)
    table_faces = [int(face["ord"]) for face in facts["faces"]]
    # An edge's display class as its selector table names it (``visibilityClass``).
    table_edges = [(int(edge["ord"]), str(edge.get("class") or STEP_EDGE_VISIBILITY_CLASSES["FEATURE"]))
                   for edge in facts["edges"]]
    if len(table_faces) != face_map.Extent() or len(table_edges) != edge_map.Extent():
        raise MeshProductionError(
            f"the component's BREP has {face_map.Extent()} faces and {edge_map.Extent()} edges, "
            f"its topology facts {len(table_faces)} and {len(table_edges)}"
        )
    diagonal = _bounding_diagonal(topods)
    # OCCT refuses a deflection under its confusion tolerance, which a component of
    # next to no extent (a lone vertex) would otherwise ask for.
    deflection = max(chord * diagonal, Precision.Confusion_s())
    kinds = {int(face["ord"]): str(face.get("surfaceType") or "") for face in facts["faces"]}
    # Every face the mesh can resolve must have triangles; a smaller one may have none.
    faces, required = _mesh(topods, face_map, kinds, deflection, angle) if face_map.Extent() else ({}, [])
    # A face no mesher covered is left out, and the body names it: every reader says so.
    unmeshed = [ordinal for ordinal in required if ordinal not in faces]

    position_parts, normal_parts, index_parts, face_ranges = [], [], [], []
    vertex_base = index_start = 0
    for ordinal in table_faces:
        positions, normals, triangles = faces.get(ordinal, (np.zeros((0, 3), np.float32),) * 2 + (np.zeros((0, 3), np.uint32),))
        position_parts.append(positions)
        normal_parts.append(normals)
        index_parts.append(triangles.reshape(-1) + np.uint32(vertex_base))
        color = face_colors.get(ordinal)
        face_ranges.append({"ord": ordinal, "color": [float(c) for c in color] if color else None,
                            "indexStart": index_start, "indexCount": int(triangles.size)})
        vertex_base += len(positions)
        index_start += int(triangles.size)
    positions = np.concatenate(position_parts).astype("<f4") if position_parts else np.zeros((0, 3), "<f4")
    normals = np.concatenate(normal_parts).astype("<f4") if normal_parts else np.zeros((0, 3), "<f4")
    indices = np.concatenate(index_parts).astype("<u4") if index_parts else np.zeros(0, "<u4")
    _unfold_needles(positions, normals, indices.reshape(-1, 3))

    adjacent = _edge_faces(topods, face_map, edge_map)
    edges = []
    for ordinal, visibility in table_edges:
        polyline = _edge_polyline(TopoDS.Edge_s(edge_map.FindKey(ordinal)), adjacent[ordinal],
                                  face_map, faces, deflection, angle)
        if polyline is not None and len(polyline) >= 2:
            edges.append((ordinal, str(visibility or "none"), np.ascontiguousarray(polyline, "<f4").reshape(-1, 3)))

    if len(positions):
        low, high = positions.min(axis=0), positions.max(axis=0)
    elif edges:
        points = np.concatenate([polyline for _, _, polyline in edges])
        low, high = points.min(axis=0), points.max(axis=0)
    else:
        low = high = np.zeros(3, np.float32)
    bounds = {"min": [float(v) for v in low], "max": [float(v) for v in high]}
    body = encode_payload(part=part, positions=positions, normals=normals, indices=indices, face_ranges=face_ranges,
                          edges=edges, bounds=bounds, unmeshed_faces=unmeshed)
    return MeshedComponent(body, _boxes(faces, edges, adjacent))
