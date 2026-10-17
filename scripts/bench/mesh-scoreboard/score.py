"""The mesh scoreboard: one mesher scored over the solids of STEP files, one JSON row per solid.

    ./.venv/bin/python scripts/bench/mesh-scoreboard/score.py --mesher cadgen \
        --out tmp/mesh-scoreboard/branch-cadgen.jsonl models/examples/STEP/*.step

The mesher under test is whichever cadgen `PYTHONPATH` names (this checkout's, or another
worktree's, so `main` and a branch are scored by the same script); `--mesher occt` scores OCCT's
BRepMesh alone, the baseline every mesher is measured against. Both run at cadgen's display
tolerance (`cadgen.tessellation_policy.DISPLAY_TESSELLATION`), on one core.

Per solid, the row names the file, the solid's index in it, its face count, how many of the BREP's
own edges bound one face (its own open boundary, which every mesher shares), the absolute
deflection (the chord tolerance times the bounding diagonal), and the mesher's:

- `seconds`, `triangles`;
- `open`: edges of the mesh, welded where its float32 vertices coincide, that an odd number of
  triangles use -- cracks, holes and T-junctions; `widest`: the widest such crack, from each open
  edge's midpoint to the nearest open edge of another face, in deflections (`d`);
- `empty`: faces at least a deflection squared in area that got no triangle, silently (not
  named by the body as unmeshed); `named`: the faces the body does name;
- `area_off`: faces whose triangles' area is off the exact face area by more than the chord
  error along the face's boundary allows (its perimeter times the deflection), and by over 1%;
- `volume_error`: the relative error of the mesh's signed volume against the solid's, for a
  solid with no open boundary of its own (else null);
- `dev_off`, `dev_worst`: from each face's 24 longest triangles (their centroid, edge
  midpoints and an interior point of each projected onto the face's exact surface), the faces
  further than two deflections off and the worst distance in deflections;
- `folded`: among those sampled triangles, the ones whose facet points against the surface's
  normal where they sit (past the rounding of a sliver seen edge-on); `needles`: triangles with an
  angle under 0.5 degrees, skinny but not a fault in themselves.

A mesher that raises on a solid gets an `error` row instead. `summarize.py` turns the rows into
the table a pull request carries. Output goes under `tmp/`; nothing here is committed.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

from OCP.BRep import BRep_Tool
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepTools import BRepTools
from OCP.Bnd import Bnd_Box
from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
from OCP.GeomLProp import GeomLProp_SLProps
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.IMeshTools import IMeshTools_Parameters
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED, TopAbs_SOLID
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape, TopTools_IndexedMapOfShape
from OCP.gp import gp_Pnt

SAMPLE = 24
NEEDLE_RADIANS = math.radians(0.5)
MAX_OPEN_MEASURED = 4000
# A sampled triangle is folded when its facet points against the surface's normal by more than the
# rounding of a sliver seen edge-on: the cosine between them below this (the contract test's bound).
FOLDED_COSINE = -1e-3


def solids(path: str):
    """Each distinct solid of a STEP file, unlocated."""
    reader = STEPControl_Reader()
    if reader.ReadFile(path) != IFSelect_RetDone:
        raise SystemExit(f"cannot read {path}")
    reader.TransferRoots()
    shape = reader.OneShape()
    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    seen = TopTools_IndexedMapOfShape()
    while explorer.More():
        seen.Add(explorer.Current().Located(TopLoc_Location()))
        explorer.Next()
    for index in range(1, seen.Extent() + 1):
        yield seen.FindKey(index)


def diagonal(shape) -> float:
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, False)
    if box.IsVoid():
        return 0.0
    x0, y0, z0, x1, y1, z1 = box.Get()
    return math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2)


def free_edges(solid) -> int:
    """Edges of the BREP that bound one face only, not as its seam: the solid's own open boundary."""
    owners = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(solid, TopAbs_EDGE, TopAbs_FACE, owners)
    free = 0
    for i in range(1, owners.Extent() + 1):
        edge = TopoDS.Edge_s(owners.FindKey(i))
        faces = owners.FindFromIndex(i)
        if BRep_Tool.Degenerated_s(edge):
            continue
        if faces.Size() == 1 and not BRep_Tool.IsClosed_s(edge, TopoDS.Face_s(faces.First())):
            free += 1
    return free


def welded(positions, triangles, face_of):
    """The mesh with coincident float32 vertices made one, degenerate triangles dropped."""
    positions = np.ascontiguousarray(positions, np.float32)
    _, label = np.unique(positions.view(np.dtype((np.void, 12))).ravel(), return_inverse=True)
    label = label.ravel()
    points = np.zeros((int(label.max()) + 1, 3))
    points[label] = positions
    w = label[triangles]
    keep = (w[:, 0] != w[:, 1]) & (w[:, 1] != w[:, 2]) & (w[:, 2] != w[:, 0])
    return points, w[keep], face_of[keep], int(label.max()) + 1


def cracks(positions, triangles, face_of) -> tuple[int, float]:
    """Open edges of the welded mesh, and the widest crack between faces in millimetres."""
    if not len(triangles):
        return 0, 0.0
    points, w, owner, n = welded(positions, triangles, face_of)
    edges = np.sort(np.concatenate([w[:, [0, 1]], w[:, [1, 2]], w[:, [2, 0]]]), axis=1)
    owners = np.concatenate([owner] * 3)
    keys = edges[:, 0] * n + edges[:, 1]
    _u, inverse, counts = np.unique(keys, return_inverse=True, return_counts=True)
    odd = np.nonzero(counts[inverse] % 2 == 1)[0]
    if not len(odd):
        return 0, 0.0
    a, b, own = points[edges[odd, 0]], points[edges[odd, 1]], owners[odd]
    mid = (a + b) / 2
    widest = 0.0
    for k in range(min(len(odd), MAX_OPEN_MEASURED)):
        other = own != own[k]
        if not other.any():
            continue
        pa, pb = a[other], b[other]
        d = pb - pa
        t = np.clip(np.einsum("ij,ij->i", mid[k] - pa, d) / np.maximum(np.einsum("ij,ij->i", d, d), 1e-300), 0, 1)
        widest = max(widest, float(np.min(np.linalg.norm(pa + t[:, None] * d - mid[k], axis=1))))
    return int(len(odd)), widest


def needles(positions, triangles) -> int:
    """Triangles with an angle under half a degree."""
    if not len(triangles):
        return 0
    a, b, c = (positions[triangles[:, k]] for k in range(3))
    count = 0
    for p, q, r in ((a, b, c), (b, c, a), (c, a, b)):
        u, v = q - p, r - p
        cosine = np.einsum("ij,ij->i", u, v) / np.maximum(np.linalg.norm(u, axis=1) * np.linalg.norm(v, axis=1), 1e-300)
        count += int(np.count_nonzero(np.arccos(np.clip(cosine, -1, 1)) < NEEDLE_RADIANS))
    return count


def surface_check(face_map, positions, triangles, faces, deflection) -> tuple[int, int, float, int]:
    """Faces further than two deflections off their surface, the worst distance (in deflections) and
    the sampled triangles folded against the surface, over each face's longest triangles."""
    measured = off = folded = 0
    worst = 0.0
    for ordinal, first, count in faces:
        if not count:
            continue
        face = TopoDS.Face_s(face_map.FindKey(ordinal))
        location = TopLoc_Location()
        surface = BRep_Tool.Surface_s(face, location)
        transform = location.Transformation()
        inverse = transform.Inverted()
        reversed_face = face.Orientation() == TopAbs_REVERSED
        t = triangles[first:first + count]
        a, b, c = (positions[t[:, k]] for k in range(3))
        longest = np.maximum(np.maximum(np.linalg.norm(b - a, axis=1), np.linalg.norm(c - b, axis=1)),
                             np.linalg.norm(a - c, axis=1))
        # One projector and one local-properties evaluator per face, initialised once over the
        # surface: initialising per point is what made this pass cost hours over a corpus.
        projector = GeomAPI_ProjectPointOnSurf()
        projector.Init(surface, *surface.Bounds(), 1e-9)
        props = GeomLProp_SLProps(surface, 1, 1e-9)
        face_worst = 0.0
        for k in np.argsort(-longest)[:SAMPLE].tolist():
            facet = np.cross(b[k] - a[k], c[k] - a[k])
            samples = ((a[k] + b[k] + c[k]) / 3, (a[k] + b[k]) / 2, (b[k] + c[k]) / 2, (c[k] + a[k]) / 2,
                       0.6 * a[k] + 0.25 * b[k] + 0.15 * c[k])
            for index, point in enumerate(samples):
                projector.Perform(gp_Pnt(*point.tolist()).Transformed(inverse))
                if not projector.NbPoints():
                    continue
                face_worst = max(face_worst, projector.LowerDistance())
                if index == 0 and np.linalg.norm(facet) > 0:
                    u, v = projector.LowerDistanceParameters()
                    props.SetParameters(u, v)
                    if props.IsNormalDefined():
                        normal = props.Normal().Transformed(transform)
                        n = np.array([normal.X(), normal.Y(), normal.Z()])
                        if reversed_face:
                            n = -n
                        folded += int(np.dot(facet, n) / (np.linalg.norm(facet) * np.linalg.norm(n)) < FOLDED_COSINE)
        measured += 1
        off += face_worst > 2 * deflection
        worst = max(worst, face_worst)
    return measured, off, worst / deflection if deflection else 0.0, folded


def occt_mesh(solid, face_map, deflection: float, angle: float):
    """OCCT's BRepMesh alone: (positions, triangles, [(ordinal, first, count)], seconds)."""
    BRepTools.Clean_s(solid)
    params = IMeshTools_Parameters()
    params.Deflection = deflection
    params.Angle = angle
    params.InParallel = False
    start = time.perf_counter()
    BRepMesh_IncrementalMesh(solid, params)
    seconds = time.perf_counter() - start
    positions, triangles, faces = [], [], []
    base = first = 0
    for ordinal in range(1, face_map.Extent() + 1):
        face = TopoDS.Face_s(face_map.FindKey(ordinal))
        location = TopLoc_Location()
        poly = BRep_Tool.Triangulation_s(face, location)
        if poly is None or poly.NbTriangles() == 0:
            faces.append((ordinal, first, 0))
            continue
        transform = location.Transformation()
        for i in range(1, poly.NbNodes() + 1):
            p = poly.Node(i).Transformed(transform)
            positions.append((p.X(), p.Y(), p.Z()))
        flip = face.Orientation() == TopAbs_REVERSED
        for i in range(1, poly.NbTriangles() + 1):
            n1, n2, n3 = poly.Triangle(i).Get()
            triangles.append((base + n1 - 1, base + n3 - 1, base + n2 - 1) if flip else
                             (base + n1 - 1, base + n2 - 1, base + n3 - 1))
        faces.append((ordinal, first, poly.NbTriangles()))
        base += poly.NbNodes()
        first += poly.NbTriangles()
    return (np.array(positions or np.zeros((0, 3)), np.float64), np.array(triangles or np.zeros((0, 3)), np.int64),
            faces, seconds, [])


def cadgen_mesh(solid, face_map, chord: float, angle: float):
    """cadgen's display mesh of the solid, through the store's mesher, from its topology facts."""
    from cadgen._internal.tessellate import mesh_component
    from cadgen._internal.topology_extract import extract_topology_facts
    from cadgen.store.meshes import decode_payload
    from cadgen.store.parts import PART_VERSION

    facts = extract_topology_facts(solid)
    start = time.perf_counter()
    body = mesh_component(solid, facts, {}, part="0" * 64 + f"-v{PART_VERSION}", chord=chord, angle=angle).body
    seconds = time.perf_counter() - start
    mesh = decode_payload(body)
    faces = [(o, s // 3, c // 3) for o, s, c, _colour in mesh.faces.tolist()]
    return (np.asarray(mesh.positions, np.float64), np.asarray(mesh.indices, np.int64).reshape(-1, 3), faces, seconds,
            list(mesh.unmeshed_faces))


def score_solid(solid, *, mesher: str, chord: float, angle: float) -> dict:
    face_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(solid, TopAbs_FACE, face_map)
    exact, perimeter = {}, {}
    for ordinal in range(1, face_map.Extent() + 1):
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face_map.FindKey(ordinal), props)
        exact[ordinal] = props.Mass()
        props = GProp_GProps()
        BRepGProp.LinearProperties_s(face_map.FindKey(ordinal), props)
        perimeter[ordinal] = props.Mass()
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid, props)
    free = free_edges(solid)
    deflection = chord * diagonal(solid)
    row = {"faces": face_map.Extent(), "free": free, "deflection": deflection}
    try:
        if mesher == "occt":
            positions, triangles, faces, row["seconds"], named = occt_mesh(solid, face_map, deflection, angle)
        else:
            positions, triangles, faces, row["seconds"], named = cadgen_mesh(solid, face_map, chord, angle)
    except Exception as error:  # noqa: BLE001 - the mesher's failure is the row
        row["error"] = f"{type(error).__name__}: {error}"
        return row
    face_of = np.zeros(len(triangles), np.int64)
    for o, first, count in faces:
        face_of[first:first + count] = o
    row["triangles"] = int(len(triangles))
    row["open"], widest = cracks(positions, triangles, face_of)
    row["widest"] = widest / deflection if deflection else 0.0
    if len(triangles):
        a, b, c = (positions[triangles[:, k]] for k in range(3))
        areas = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2
        volume = float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6)
    else:
        areas, volume = np.zeros(0), 0.0
    row["named"] = len(named)
    row["empty"] = sum(1 for o, _f, c in faces if c == 0 and o not in named and exact.get(o, 0) >= deflection ** 2)
    row["area_off"] = sum(1 for o, f, c in faces if c and exact.get(o, 0) >= deflection ** 2
                          and abs(float(areas[f:f + c].sum()) - exact[o])
                          > max(0.01 * exact[o], perimeter.get(o, 0.0) * deflection))
    row["volume_error"] = abs(volume / props.Mass() - 1) if free == 0 and props.Mass() > 0 else None
    row["needles"] = needles(positions, triangles)
    row["dev_faces"], row["dev_off"], row["dev_worst"], row["folded"] = surface_check(
        face_map, positions, triangles, faces, deflection)
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--mesher", choices=("cadgen", "occt"), required=True,
                        help="cadgen: the display mesher of the cadgen PYTHONPATH names; occt: BRepMesh alone")
    parser.add_argument("--out", required=True, type=Path, help="the JSONL to write, under tmp/")
    parser.add_argument("steps", nargs="+", help="STEP files to score, solid by solid")
    args = parser.parse_args(argv)

    from cadgen.tessellation_policy import DISPLAY_TESSELLATION

    chord, angle = DISPLAY_TESSELLATION["chordTolerance"], DISPLAY_TESSELLATION["angleTolerance"]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    sys.setrecursionlimit(10000)
    with args.out.open("w", encoding="utf-8") as out:
        for path in args.steps:
            name = Path(path).name
            for index, solid in enumerate(solids(path)):
                row = {"file": name, "solid": index, **score_solid(solid, mesher=args.mesher, chord=chord, angle=angle)}
                out.write(json.dumps(row) + "\n")
                out.flush()
                print(f"{name} #{index}: " + (f"error {row['error']}" if "error" in row else
                      f"{row['triangles']} triangles, {row['seconds']:.2f} s, open {row['open']}, "
                      f"empty {row['empty']}, dev_off {row['dev_off']}"), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
