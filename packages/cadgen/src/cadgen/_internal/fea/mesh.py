"""One part occurrence, or an assembly's glued parts -> quadratic tetrahedra, faces kept under their ordinal.

The mesher is netgen (LGPL-2.1, the ``netgen-mesher`` wheel with its own OpenCascade). It cannot take an OCP shape
object directly -- two pybind11 OCC builds are foreign to each other -- so the placed occurrence is written to a BREP
file, which netgen reads in a process of its own (:mod:`.mesher`). Both sides walk the B-rep in explorer order, so netgen's face ``i`` is the engine's face ordinal
``i+1`` in practice; that is an implementation property, not a contract, so every face a study names is VERIFIED by area
and centre of mass against the OCP face the document resolved, and matched geometrically when the order differs.

An assembly (:func:`mesh_assembly`) is glued first (:mod:`.assembly`), so the order no longer holds: gluing splits a
face where another part sits on it. Each part's face is then followed through the glue's history to the faces it became,
and those are matched to netgen's by area and centre.

netgen is never imported in this process: its OpenCascade (7.8) and OCP's (8) cannot share one
(:mod:`.mesher`). ``match_faces`` and ``generate_mesh`` run in the mesher's process, on netgen's objects. Back here,
an element netgen's curving turned inside out is made straight (:func:`straighten_inverted`) before anything reads it.
"""

from __future__ import annotations

import contextlib
import itertools
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.assembly import Contact
    from cadgen._internal.fea.document import Document, Occurrence

__all__ = ["NETGEN_PLATFORMS", "FaceFingerprint", "VolumeMesh", "default_mesh_size", "face_area_center", "kernel_messages_on_stderr", "mesh_assembly",
           "mesh_occurrence", "occurrence_fingerprints", "require_fea_stack", "small_feature_mm"]


@contextlib.contextmanager
def kernel_messages_on_stderr() -> Iterator[None]:
    """netgen's C++ messages to stderr while it reads and meshes: it prints to file descriptor 1, which is where a
    command's result belongs (``--json``'s line). The redirect is at the descriptor, as the kernel does not write
    through Python's ``sys.stdout``."""
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        saved = os.dup(1)
    except OSError:
        yield
        return
    try:
        os.dup2(2, 1)
        yield
    finally:
        sys.stdout.flush()
        os.dup2(saved, 1)
        os.close(saved)


#: Where netgen publishes wheels, and so where cadgen installs it (its marker in ``pyproject.toml``).
NETGEN_PLATFORMS = "macOS, Linux x86_64 and Windows x86_64"


def require_fea_stack() -> None:
    """Fail before anything is meshed when netgen or CalculiX is missing: netgen, which meshes, is a dependency of every
    install where it has wheels (:data:`NETGEN_PLATFORMS`), and is looked for, never imported, in this process
    (:mod:`.mesher`); the solver is the one program the person installs, and the error says how."""
    import importlib.util
    import platform

    from cadgen._internal.fea import calculix

    if importlib.util.find_spec("netgen") is None:
        raise RuntimeError(
            f"cadgen fea solve needs netgen, which meshes, and it is not installed: cadgen installs it only where netgen "
            f"publishes wheels ({NETGEN_PLATFORMS}), and this is {platform.system()} {platform.machine()}"
        )
    try:
        calculix.find_ccx()
    except calculix.CalculixMissingError as error:
        raise RuntimeError(str(error)) from error


@dataclass(frozen=True)
class FaceFingerprint:
    """What identifies a B-rep face across two OpenCascade builds."""

    #: The face's canonical ref (``bracket/face 17``), as the viewer copies it.
    ref: str
    #: 1-based ordinal in its part (the engine's ``face N``).
    ordinal: int
    area: float
    center: tuple[float, float, float]


@dataclass
class VolumeMesh:
    #: (N, 3) mm, every node including mid-edge nodes.
    nodes: "np.ndarray"
    #: (E, 10) 0-based node ids: four corners, then six mid-edge nodes in netgen's order.
    tets: "np.ndarray"
    #: (B, 6) 0-based node ids of the boundary triangles: three corners, three mid-edge.
    boundary: "np.ndarray"
    #: (B,) the cadgen face ORDINAL each boundary triangle lies on (0 = unmatched).
    #: For an assembly, the 1-based position of its face in ``faces`` instead.
    boundary_ordinal: "np.ndarray"
    #: Every face fingerprint of the occurrence, by ordinal. For an assembly,
    #: every face of every part by its ref (``arm/face 6``), parts in order.
    faces: "dict[int, FaceFingerprint] | dict[str, FaceFingerprint]"
    max_h: float
    bbox_diagonal: float
    seconds: float
    #: The elements :func:`straighten_inverted` made straight, so CalculiX takes them.
    straightened: int
    #: (E,) for an assembly, the part each element belongs to (an index into
    #: the part refs meshed); ``None`` for one occurrence.
    domain: "np.ndarray | None" = None
    #: For an assembly, the refs of faces that are (partly) a bonded joint.
    interface_faces: set[str] = field(default_factory=set)
    #: For an assembly, the triangles of each bonded joint, keyed by the two part indices (low, high): (T, 6) node ids
    #: like ``boundary``. They are interior, so they are in no face's ``boundary`` rows.
    interface_triangles: "dict[tuple[int, int], np.ndarray]" = field(default_factory=dict)
    #: For an assembly, the face refs of each bonded joint, keyed like ``interface_triangles``,
    #: both parts' sides together.
    joint_faces: "dict[tuple[int, int], set[str]]" = field(default_factory=dict)


# netgen's defaults (curvature safety 2, grading 0.3) refine to a fillet's or chamfer's own size, however large the
# element size asked for: the 4-part rover cut came to 155k tets at any ``mesh.size_mm``. Grading 0.5 lets the size grow
# faster away from small features, and a curvature safety of 1.5 keeps elements under about a radius: 1 put one element
# across a 6 mm rod's radius at the default size and read its bending stress 20% high (test_fea.DefaultSizeAccuracy).
_MESHING = {"curvaturesafety": 1.5, "grading": 0.5}


def _meshing(refine: float) -> dict:
    """netgen's settings for a mesh ``refine`` times finer than the default at curved features.

    ``maxh`` alone does not refine a fillet or a hole: there the curvature safety
    sets the size, so a finer solve scales it with the ratio it shrinks ``maxh`` by.
    """
    return {**_MESHING, "curvaturesafety": _MESHING["curvaturesafety"] * max(refine, 1.0)}


def default_mesh_size(bbox_diagonal: float) -> float:
    """The element size a study gets when it names none: a fortieth of the
    bounding diagonal, which lands a typical part at 30-100k DOF."""
    return max(bbox_diagonal / 40.0, 1e-3)


def small_feature_mm(volume: "VolumeMesh") -> float | None:
    """The shortest element edge (mm) when small features, not ``max_h``, set the mesh; else ``None``.

    An element of a mesh that max_h governs has edges near max_h. Where the mean element's edge is under half of it,
    small features (thin walls, fillets, chamfers) forced the refinement, and a larger ``mesh.size_mm`` will not coarsen
    it much.
    """
    import numpy as np

    corners = volume.nodes[volume.tets[:, :4]]
    edges = corners[:, 1:] - corners[:, :1]
    total = float(np.abs(np.einsum("ij,ij->i", edges[:, 0], np.cross(edges[:, 1], edges[:, 2]))).sum()) / 6.0
    mean_edge = (6.0 * 2**0.5 * total / len(corners)) ** (1.0 / 3.0)
    if mean_edge >= 0.5 * volume.max_h:
        return None
    pairs = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
    return float(min(np.linalg.norm(corners[:, a] - corners[:, b], axis=1).min() for a, b in pairs))


def face_area_center(face) -> tuple[float, tuple[float, float, float]]:
    """Area (mm^2) and centre of mass (mm) of one build123d face."""
    return area_center(face.wrapped)


def area_center(shape) -> tuple[float, tuple[float, float, float]]:
    from cadgen._internal.fea.assembly import gprops

    props = gprops(shape)
    centre = props.CentreOfMass()
    return float(props.Mass()), (centre.X(), centre.Y(), centre.Z())


def occurrence_fingerprints(occurrence: "Occurrence") -> list[FaceFingerprint]:
    """Area and centre of mass of every face, by the document's own ordinals."""
    out = []
    for selection in occurrence.entities("face"):
        area, centre = face_area_center(selection.shape())
        out.append(FaceFingerprint(selection.ref, int(selection.ordinal), area, centre))
    return out


def write_brep(shape, path: Path) -> None:
    from OCP.BRepTools import BRepTools

    if not BRepTools.Write_s(shape, str(path)):
        raise RuntimeError(f"could not write the BREP the mesher reads: {path}")


def match_faces(fingerprints: list[FaceFingerprint], ng_faces, scale: float) -> dict[int, int]:
    """``{netgen face index (0-based): cadgen ordinal}`` for EVERY face, verified.

    Order is the fast path (netgen face i <-> ordinal i+1); a face that does not agree there is matched by area and
    centre against all of netgen's faces, and an ambiguous or missing match is an error rather than a guess.
    """
    import numpy as np

    ng = [(float(f.mass), np.array([f.center.x, f.center.y, f.center.z], dtype=float)) for f in ng_faces]
    if len(ng) != len(fingerprints):
        raise RuntimeError(
            f"the mesher sees {len(ng)} faces but the document has {len(fingerprints)}; "
            "the geometry did not survive the BREP hand-off intact"
        )
    area_tol = 1e-4
    centre_tol = 1e-4 * max(scale, 1.0)

    def agrees(fp: FaceFingerprint, index: int) -> bool:
        area, centre = ng[index]
        return abs(area - fp.area) <= area_tol * max(fp.area, 1.0) and np.linalg.norm(centre - fp.center) <= centre_tol

    mapping: dict[int, int] = {}
    unresolved = []
    for fp in fingerprints:
        index = fp.ordinal - 1
        if 0 <= index < len(ng) and agrees(fp, index):
            mapping[index] = fp.ordinal
        else:
            unresolved.append(fp)
    for fp in unresolved:
        candidates = [i for i in range(len(ng)) if i not in mapping and agrees(fp, i)]
        if len(candidates) != 1:
            raise RuntimeError(
                f"face {fp.ref} (area {fp.area:.4g} mm^2 at {tuple(round(c, 3) for c in fp.center)}) has "
                f"{len(candidates)} geometric matches in the mesher's faces; cannot place loads on it"
            )
        mapping[candidates[0]] = fp.ordinal
    return mapping


def require_elements(e3) -> None:
    """Refuse a mesh that is not all 10-node tetrahedra (``SecondOrder`` applied).

    netgen's ``nodes`` field is only as wide as the element order: 4 columns on a first-order mesh. Older builds padded
    it with zeros instead; node numbers are 1-based, so a zero in the first ten is the same signal.
    """
    nodes = e3["nodes"]
    if nodes.shape[1] < 10 or not (nodes[:, :10] > 0).all():
        raise RuntimeError("the mesher produced elements that are not 10-node tetrahedra")


def _offsets(radius: float) -> list[tuple[float, float, float]]:
    """The six points ``radius`` from a centre along the axes."""
    return [tuple(radius * sign if axis == k else 0.0 for k in range(3)) for axis in range(3) for sign in (-1.0, 1.0)]


def generate_mesh(geometry, h: float, refine: float, size_field: dict | None):
    """netgen's second-order mesh at size ``h``; ``size_field`` adds local sizes.

    ``size_field`` is ``{"points": [[x, y, z, size_mm], ...], "radius_mm": r}``: a point holds its size within
    ``radius_mm`` of it (its centre and six points at that distance, netgen grading the rest).
    """
    import netgen.meshing as ngmesh

    if not size_field:
        mesh = geometry.GenerateMesh(maxh=h, **_meshing(refine))
    else:
        parameters = ngmesh.MeshingParameters(maxh=h, **_meshing(refine))
        radius = float(size_field.get("radius_mm") or 0.0)
        offsets = [(0.0, 0.0, 0.0)] + ([] if radius <= 0 else _offsets(radius))
        for x, y, z, size in size_field.get("points") or ():
            for dx, dy, dz in offsets:
                parameters.RestrictH(x=float(x) + dx, y=float(y) + dy, z=float(z) + dz, h=float(size))
        mesh = geometry.GenerateMesh(mp=parameters)
    mesh.SecondOrder()
    return mesh


def _netgen(shape, name: str, prints: list[FaceFingerprint], diagonal: float, h: float, refine: float,
            size_field: dict | None, *, count_domains: bool = False):
    """netgen's mesh of an OCP shape, through a BREP file and the mesher's process (:func:`.mesher.volume`): the
    verified face mapping, the nodes, the volume and surface elements, and (``count_domains``) the number of volumes."""
    from cadgen._internal.fea import mesher

    with tempfile.TemporaryDirectory(prefix="cadgen-fea-") as tmp:
        brep = Path(tmp) / name
        write_brep(shape, brep)
        return mesher.volume(brep, prints, diagonal, h, refine, size_field, count_domains=count_domains)


def mesh_occurrence(
    occurrence: "Occurrence", *, max_h: float | None = None, refine: float = 1.0, size_field: dict | None = None,
) -> VolumeMesh:
    """Mesh one placed occurrence with second-order tetrahedra.

    ``refine`` also shrinks the elements at curved features by that ratio (:func:`_meshing`).
    ``size_field`` sets local sizes (:func:`generate_mesh`).
    """
    require_fea_stack()
    import numpy as np

    shape = occurrence.shape()
    fingerprints = occurrence_fingerprints(occurrence)
    diagonal = float(shape.bounding_box().diagonal)
    if not diagonal > 0:
        raise RuntimeError(f"{occurrence.ref} has no volume to mesh")
    h = float(max_h) if max_h else default_mesh_size(diagonal)

    started = time.perf_counter()
    mapping, coordinates, e3, e2, _ = _netgen(shape.wrapped, "occurrence.brep", fingerprints, diagonal, h, refine, size_field)

    if len(e3) == 0:
        raise RuntimeError(f"the mesher produced no volume elements for {occurrence.ref}; is it a closed solid?")
    require_elements(e3)
    tets = np.ascontiguousarray(e3["nodes"][:, :10].astype(np.int64) - 1)
    straightened = straighten_inverted(coordinates, tets)
    ordinal_of = np.zeros(int(e2["index"].max()) + 1, dtype=np.int64)
    for index, ordinal in mapping.items():
        ordinal_of[index + 1] = ordinal

    return VolumeMesh(
        nodes=coordinates, tets=tets, boundary=np.ascontiguousarray(e2["nodes"][:, :6].astype(np.int64) - 1),
        boundary_ordinal=ordinal_of[e2["index"].astype(np.int64)],
        faces={fp.ordinal: fp for fp in fingerprints},
        max_h=h, bbox_diagonal=diagonal, seconds=time.perf_counter() - started, straightened=straightened,
    )


def shape_diagonal(shape) -> float:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from cadgen.engine.kernel.bounds import box_limits

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    xmin, ymin, zmin, xmax, ymax, zmax = box_limits(box)
    return float(((xmax - xmin) ** 2 + (ymax - ymin) ** 2 + (zmax - zmin) ** 2) ** 0.5)


# Keast's 5-point rule for a tetrahedron, exact to degree 3: barycentric points and weights (of the unit tet's 1/6).
_KEAST = (
    ((0.25, 0.25, 0.25, 0.25), -2.0 / 15.0),
    *((tuple(0.5 if k == n else 1.0 / 6.0 for k in range(4)), 3.0 / 40.0) for n in range(4)),
)


def jacobians(points, edges, at) -> "np.ndarray":
    """(E, P) the Jacobian determinant of each 10-node tet at each barycentric point of ``at``: ``points`` (E, 10, 3)
    are its corners, then its mid-edge nodes on ``edges``' corner pairs."""
    import numpy as np

    out = np.empty((len(points), len(at)))
    for p, bary in enumerate(at):
        # d(shape function)/d(barycentric coordinate), (4 coordinates, 10 nodes)
        slope = np.zeros((4, 10))
        for i in range(4):
            slope[i, i] = 4.0 * bary[i] - 1.0
        for n, (i, j) in enumerate(edges, 4):
            slope[i, n], slope[j, n] = 4.0 * bary[j], 4.0 * bary[i]
        # x depends on three free coordinates (L0 = 1 - L1 - L2 - L3)
        out[:, p] = np.linalg.det(np.einsum("ka,eki->eai", (slope[1:] - slope[:1]).T, points))
    return out


def curved_volumes(nodes, tets):
    """Each 10-node tet's volume (mm^3), its mid-edge nodes counted: the curved element, not its corners' straight one.

    The corner tets of a mesh of a round part sit inside the surface, so they
    sum to a few percent short of the B-rep; the curved elements do not.
    """
    import numpy as np

    from cadgen._internal.fea.calculix import NETGEN_EDGES

    determinants = jacobians(nodes[tets], NETGEN_EDGES, [bary for bary, _ in _KEAST])
    return np.abs(determinants) @ np.array([weight for _, weight in _KEAST])


def straighten_inverted(nodes, tets) -> int:
    """Make straight every element turned inside out, moving ``nodes`` in place; the number of elements straightened.

    netgen's ``SecondOrder`` moves each mid-edge node on the surface onto the curved face it lies on. In an element thin
    across a fillet or a small hole, that node can pass the element's opposite face, and the element turns inside out:
    at an integration point CalculiX refuses the whole mesh (``nonpositive jacobian``); at one of its nodes alone it
    solves it, folded, and its stress and displacement there are wrong. So an element is checked at both, CalculiX's
    four points (:data:`.calculix.C3D10_POINTS`) and its ten nodes, and one inside out at any is made straight: its six mid-edge nodes
    go back to their edges' straight midpoints, where an element of sound corners is valid everywhere; its neighbours
    share those nodes, so the check repeats until no element is inverted. The surface there is drawn and solved as the
    straight element's, a little less curved. An element still inverted when straight has corners that enclose no
    volume, and the mesh is refused rather than handed to CalculiX.
    """
    import numpy as np

    from cadgen._internal.fea.calculix import C3D10_EDGES, C3D10_POINTS, NETGEN_EDGES, SMALLEST_JACOBIAN, c3d10_elements

    elements = c3d10_elements(nodes, tets)  # corners turned as CalculiX takes them, so a sound element is positive
    # CalculiX's integration points, then the element's corners and mid-edge nodes (C3D10's order) as barycentric points.
    checked = (*C3D10_POINTS, *(tuple(float(k == n) for k in range(4)) for n in range(4)),
               *(tuple(0.5 if k in edge else 0.0 for k in range(4)) for edge in C3D10_EDGES))
    straightened = np.zeros(len(tets), dtype=bool)
    while True:
        inverted = (jacobians(nodes[elements], C3D10_EDGES, checked) < SMALLEST_JACOBIAN).any(axis=1)
        if not inverted.any():
            return int(straightened.sum())
        if (flat := np.flatnonzero(inverted & straightened)).size:
            corners = "; ".join(f"({x:.4g}, {y:.4g}, {z:.4g})" for x, y, z in nodes[tets[flat[0], :4]].tolist())
            raise RuntimeError(
                f"the mesher made {flat.size} element(s) whose corners enclose no volume, the first at {corners} mm; "
                "CalculiX cannot solve them"
            )
        rows = tets[inverted]
        for k, (i, j) in enumerate(NETGEN_EDGES, 4):
            nodes[rows[:, k]] = 0.5 * (nodes[rows[:, i]] + nodes[rows[:, j]])
        straightened |= inverted


def check_domains(nodes, tets, domain, parts) -> None:
    """Raise unless each domain is the part it is taken to be.

    The mesher's volume numbers follow the solids' order in the glued shape; a mapping that drifted would give every
    element another part's material. Each domain's volume (summed over the curved elements) must match its part's within
    5%, and its centroid must lie in its part's bounding box.
    """
    import numpy as np

    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from cadgen.engine.kernel.bounds import box_limits

    corners = nodes[tets[:, :4]]
    volumes = curved_volumes(nodes, tets)
    for index, part in enumerate(parts):
        rows = domain == index
        meshed = float(volumes[rows].sum())
        if abs(meshed - part.volume_mm3) > 0.05 * part.volume_mm3:
            raise RuntimeError(
                f"the mesh's volume {index} holds {meshed:.4g} mm^3 but part {part.ref} is {part.volume_mm3:.4g} mm^3; "
                "the mesher's volumes do not follow the parts"
            )
        box = Bnd_Box()
        BRepBndLib.Add_s(part.shape, box)
        low, high = np.array(box_limits(box)[:3]), np.array(box_limits(box)[3:])
        centroid = (corners[rows].mean(axis=1) * volumes[rows, None]).sum(axis=0) / volumes[rows].sum()
        if ((centroid < low - 1e-6) | (centroid > high + 1e-6)).any():
            raise RuntimeError(f"the mesh's volume {index} lies outside part {part.ref}; the mesher's volumes do not follow the parts")


def mesh_assembly(document: "Document", part_refs: list[str], bonded: "list[Contact]", tolerance_mm: float,
                  max_h: float | None = None, log=None, refine: float = 1.0,
                  size_field: dict | None = None) -> VolumeMesh:
    """Mesh the parts ``part_refs`` as one conforming mesh, bonded parts sharing nodes.

    ``bonded`` are the contacts to glue; parts not in any of them stay apart. The mesh's ``domain`` is the index into
    ``part_refs`` of each element's part, and ``faces`` holds every face of every part under its own ref, so a study's
    ``arm/face 6`` means the same face it does in the viewer. ``log`` is told when gluing and meshing start; ``refine``
    and ``size_field`` are :func:`mesh_occurrence`'s.
    """
    require_fea_stack()
    import numpy as np

    from cadgen._internal.fea.assembly import SharedSolid, display_names, glue, list_parts, part_faces
    from cadgen._internal.fea.checks import quoted
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher

    by_ref = {part.ref: part for part in list_parts(document)}
    missing = [ref for ref in part_refs if ref not in by_ref]
    if missing:
        raise ValueError(f"not a part of this document: {', '.join(missing)}")
    parts = [by_ref[ref] for ref in part_refs]
    index_of = {ref: i for i, ref in enumerate(part_refs)}
    if log:
        log(f"gluing {len(bonded)} bonded pairs of {len(parts)} parts")
    try:
        glued = glue(
            [part.shape for part in parts],
            [(index_of[c.a], index_of[c.b], max(c.gap_mm, c.interference_mm)) for c in bonded if c.a in index_of and c.b in index_of],
            tolerance_mm,
        )
    except SharedSolid as fused:
        names = display_names(parts)
        raise ValueError(
            f"{quoted(names[fused.first])} and {quoted(names[fused.second])} share a solid after gluing: they overlap, "
            "and bonding them would fuse them into one part; fix the geometry or mark them free"
        ) from None
    diagonal = shape_diagonal(glued.shape)
    if not diagonal > 0:
        raise RuntimeError("the assembly has no volume to mesh")
    h = float(max_h) if max_h else default_mesh_size(diagonal)

    # Every face of every part, under its own ref; positions are 1-based.
    faces: dict[str, FaceFingerprint] = {}
    position_of: dict[tuple[int, int], int] = {}
    for i, part in enumerate(parts):
        for ordinal, face in enumerate(part_faces(part.shape), 1):
            area, centre = area_center(face)
            ref = part.face_refs[ordinal - 1]
            faces[ref] = FaceFingerprint(ref, ordinal, area, centre)
            position_of[(i, ordinal)] = len(faces)
    refs = list(faces)

    # Which part faces each face of the glued shape came from.
    glued_faces = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
    TopExp.MapShapes_s(glued.shape, TopAbs_FACE, glued_faces)
    sources: dict[int, list[int]] = {}
    parts_on: dict[int, set[int]] = {}
    for i, per_face in enumerate(glued.face_images):
        for ordinal, images in enumerate(per_face, 1):
            for image in images:
                sources.setdefault(image, []).append(position_of[(i, ordinal)])
                parts_on.setdefault(image, set()).add(i)
    interface_faces = {
        refs[position - 1]
        for image, owners in sources.items()
        if len(parts_on[image]) > 1
        for position in owners
    }
    part_of_position = {position: i for (i, _), position in position_of.items()}
    joint_faces: dict[tuple[int, int], set[str]] = {}
    for image, owners in sources.items():
        for pair in itertools.combinations(sorted(parts_on[image]), 2):
            joint_faces.setdefault(pair, set()).update(
                refs[position - 1] for position in owners if part_of_position[position] in pair
            )
    glued_prints = []
    for k in range(1, glued_faces.Extent() + 1):
        area, centre = area_center(glued_faces.FindKey(k))
        glued_prints.append(FaceFingerprint(f"face {k} of the glued shape", k, area, centre))

    started = time.perf_counter()
    if log:
        log(f"meshing the glued shape at {h:.3g} mm")
    mapping, coordinates, e3, e2, domains = _netgen(
        glued.shape, "assembly.brep", glued_prints, diagonal, h, refine, size_field, count_domains=True,
    )

    if len(e3) == 0:
        raise RuntimeError("the mesher produced no volume elements for the assembly; is every part a closed solid?")
    if domains != len(glued.solid_part):
        raise RuntimeError(f"the mesher made {domains} volumes from {len(glued.solid_part)} solids")
    require_elements(e3)

    solid_part = np.array(glued.solid_part, dtype=np.int64)
    domain = solid_part[e3["index"].astype(np.int64) - 1]
    tets = np.ascontiguousarray(e3["nodes"][:, :10].astype(np.int64) - 1)
    straightened = straighten_inverted(coordinates, tets)
    check_domains(coordinates, tets, domain, parts)

    # netgen keeps the faces where parts are glued as surface elements, but they are interior: they go to
    # ``interface_triangles`` under the parts they join, and every other triangle belongs to one part's face.
    size = int(e2["index"].max()) + 1
    position_of_glued = np.zeros(size, dtype=np.int64)
    joint_of_glued: dict[int, tuple[int, int]] = {}
    for index, glued_index in mapping.items():
        if index + 1 >= size or not sources.get(glued_index):
            continue
        owners = parts_on[glued_index]
        if len(owners) > 1:
            joint_of_glued[index + 1] = (min(owners), max(owners))
        else:
            position_of_glued[index + 1] = sources[glued_index][0]
    surface = np.ascontiguousarray(e2["nodes"][:, :6].astype(np.int64) - 1)
    surface_index = e2["index"].astype(np.int64)
    outer = np.isin(surface_index, list(joint_of_glued), invert=True)
    interface_triangles: dict[tuple[int, int], np.ndarray] = {}
    for netgen_index, joint in joint_of_glued.items():
        rows = surface[surface_index == netgen_index]
        # A joint face can be listed once per side; keep one triangle each.
        _, first = np.unique(np.sort(rows[:, :3], axis=1), axis=0, return_index=True)
        interface_triangles[joint] = np.concatenate([interface_triangles[joint], rows[first]]) if joint in interface_triangles else rows[first]

    return VolumeMesh(
        nodes=coordinates, tets=tets, boundary=np.ascontiguousarray(surface[outer]),
        boundary_ordinal=position_of_glued[surface_index[outer]], faces=faces, max_h=h, bbox_diagonal=diagonal,
        seconds=time.perf_counter() - started, straightened=straightened, domain=domain, interface_faces=interface_faces,
        interface_triangles=interface_triangles, joint_faces=joint_faces,
    )
