"""The alternative to ``shapes.py``, measured against it: a pool process meshes a part exactly
as ``mesh.mesh_shape`` does (the same bytes, FreeCAD's deflection, the same knob) but hands back
the meshed B-rep itself (``BinTools`` with its triangulations), and the renderer attaches each
face's triangulation and each edge's polygon to the document's own faces and edges
(``BRep_Builder.UpdateFace`` / ``UpdateEdge``), matched by ``TopExp.MapShapes`` ordinal. The
document's shapes are then drawn with OCCT's own presentation (faces, and face boundaries as
the edges) with auto-triangulation off, so OCCT meshes nothing.

The pool's job is the engine's mesh with a different output; the attach is a Python loop per
face and per edge, which is what this measures."""

from __future__ import annotations

import io
import time
from typing import Any


def triangulated(data: bytes) -> tuple[bytes, float]:
    """A pool process's job: the part's shape bytes meshed as ``mesh.mesh_shape`` meshes them,
    returned as BinTools bytes with the triangulations (and normals) on."""
    from OCP.BinTools import BinTools, BinTools_FormatVersion_VERSION_4
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.IMeshTools import IMeshTools_Parameters

    from cadgen.engine.mesh import ANGULAR, deflection, read_shape

    started = time.perf_counter()
    local = read_shape(data)
    parameters = IMeshTools_Parameters()
    parameters.Deflection, parameters.Angle, parameters.Relative, parameters.InParallel = deflection(local), ANGULAR, False, True
    parameters.EnableControlSurfaceDeflectionAllSurfaces = True
    BRepMesh_IncrementalMesh(local, parameters)
    stream = io.BytesIO()
    BinTools.Write_s(local, stream, True, True, BinTools_FormatVersion_VERSION_4)
    return stream.getvalue(), time.perf_counter() - started


def _ready() -> bool:
    import cadgen.engine.mesh  # noqa: F401

    return True


def pool_mesh(jobs: dict[str, bytes], workers: int | None = None) -> tuple[dict[str, bytes], float]:
    """Every part meshed in a spawned pool, largest first: key -> triangulated bytes."""
    import concurrent.futures
    import multiprocessing
    import os

    count = workers or os.cpu_count() or 2
    with concurrent.futures.ProcessPoolExecutor(count, mp_context=multiprocessing.get_context("spawn")) as pool:
        for warm in [pool.submit(_ready) for _ in range(count)]:
            warm.result()  # a warm pool, as the engine's is: its start is not the meshing's
        started = time.perf_counter()
        futures = {key: pool.submit(triangulated, data) for key, data in sorted(jobs.items(), key=lambda kv: -len(kv[1]))}
        found = {key: future.result()[0] for key, future in futures.items()}
        seconds = time.perf_counter() - started
    return found, seconds


def attach(target: Any, data: bytes) -> tuple[int, int]:
    """Put the meshed copy's triangulations on ``target``'s faces and its polygons on
    ``target``'s edges, by ordinal. Returns (faces, edges) attached."""
    from OCP.BRep import BRep_Builder, BRep_Tool
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape, TopTools_IndexedMapOfShape

    from cadgen.engine.mesh import read_shape

    meshed = read_shape(data)
    builder = BRep_Builder()
    source_faces, target_faces = TopTools_IndexedMapOfShape(), TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(meshed, TopAbs_FACE, source_faces)
    TopExp.MapShapes_s(target, TopAbs_FACE, target_faces)
    done = set()
    triangulation_of = {}
    faces = 0
    for ordinal in range(1, source_faces.Extent() + 1):
        face = TopoDS.Face_s(source_faces.FindKey(ordinal))
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        if triangulation is None:
            continue
        mine = TopoDS.Face_s(target_faces.FindKey(ordinal))
        triangulation_of[ordinal] = (triangulation, location)
        if mine.TShape() in done:
            continue
        done.add(mine.TShape())
        builder.UpdateFace(mine, triangulation)
        faces += 1
    source_edges, target_edges = TopTools_IndexedMapOfShape(), TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(meshed, TopAbs_EDGE, source_edges)
    TopExp.MapShapes_s(target, TopAbs_EDGE, target_edges)
    owners = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(meshed, TopAbs_EDGE, TopAbs_FACE, owners)
    edges = 0
    for ordinal in range(1, source_edges.Extent() + 1):
        edge = TopoDS.Edge_s(source_edges.FindKey(ordinal))
        at = owners.FindIndex(edge)
        if not at:
            continue
        mine = TopoDS.Edge_s(target_edges.FindKey(ordinal))
        listed = owners.FindFromIndex(at)
        for face in (listed.First(), listed.Last()) if listed.Size() else ():
            index = source_faces.FindIndex(face)
            held = triangulation_of.get(index)
            if held is None:
                continue
            triangulation, location = held
            polygon = BRep_Tool.PolygonOnTriangulation_s(edge, triangulation, location)
            if polygon is not None:
                builder.UpdateEdge(mine, polygon, triangulation, location)
                edges += 1
    return faces, edges
