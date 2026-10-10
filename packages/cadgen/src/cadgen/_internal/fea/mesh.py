"""One STEP occurrence, or an assembly's glued parts -> quadratic (or linear) tetrahedra, faces kept under their cadgen ordinal.

The mesher is netgen (LGPL-2.1, the ``netgen-mesher`` wheel with its own
OpenCascade). It cannot take an OCP shape object directly -- two pybind11 OCC
builds are foreign to each other -- so the placed occurrence is written to a
BREP file, which netgen reads. Both sides walk the B-rep in explorer order, so
netgen's face ``i`` is cadgen's face ordinal ``i+1`` in practice; that is an
implementation property, not a contract, so every face a study names is
VERIFIED by area and centre of mass against the OCP face the scene resolved,
and matched geometrically when the order differs.

An assembly (:func:`mesh_assembly`) is glued first (:mod:`.assembly`), so
the order no longer holds: gluing splits a face where another part sits on
it. Each part's face is then followed through the glue's history to the
faces it became, and those are matched to netgen's by area and centre.

Import order matters on Linux: netgen loads its OpenCascade with RTLD_GLOBAL,
so the CAD kernel (OCP) is imported first, here, before netgen ever is.
"""

from __future__ import annotations

import itertools
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.assembly import Contact
    from cadgen.step_scene import Occurrence, StepScene

__all__ = ["FaceFingerprint", "VolumeMesh", "default_mesh_size", "face_area_center", "mesh_assembly", "mesh_occurrence", "occurrence_fingerprints", "require_fea_stack", "small_feature_mm"]


def require_fea_stack() -> None:
    """Fail with the install hint when the ``fea`` extra is missing."""
    missing = []
    for module in ("numpy", "scipy", "netgen", "skfem", "pyamg"):
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    if missing:
        from cadgen import __version__

        raise RuntimeError(
            f"cadgen's fea extra is not installed (missing {', '.join(missing)}): "
            f"pip install 'cadgen[fea]=={__version__}'"
        )


@dataclass(frozen=True)
class FaceFingerprint:
    """What identifies a B-rep face across two OpenCascade builds."""

    #: The viewer's selector for this face (``#o1.f17``).
    ref: str
    #: 1-based cadgen ordinal.
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
    #: every face of every part by its ref (``#o1.2.f6``), parts in order.
    faces: "dict[int, FaceFingerprint] | dict[str, FaceFingerprint]"
    max_h: float
    bbox_diagonal: float
    seconds: float
    #: (E,) for an assembly, the part each element belongs to (an index into
    #: the part refs meshed); ``None`` for one occurrence.
    domain: "np.ndarray | None" = None
    #: For an assembly, the refs of faces that are (partly) a bonded joint.
    interface_faces: set[str] = field(default_factory=set)
    #: For an assembly, the triangles of each bonded joint, keyed by the two part
    #: indices (low, high): (T, 6) node ids like ``boundary``. They are interior,
    #: so they are in no face's ``boundary`` rows.
    interface_triangles: "dict[tuple[int, int], np.ndarray]" = field(default_factory=dict)
    #: For an assembly, the face refs of each bonded joint, keyed like ``interface_triangles``,
    #: both parts' sides together.
    joint_faces: "dict[tuple[int, int], set[str]]" = field(default_factory=dict)
    #: For an assembly, the fuzzy value the glue closed gaps with (0 = none).
    fuzzy_mm: float = 0.0


# netgen's defaults (curvature safety 2, grading 0.3) refine to a fillet's or
# chamfer's own size, however large the element size asked for: the 4-part rover
# cut came to 155k tets at any ``mesh.size_mm``. Grading 0.5 lets the size grow
# faster away from small features, and a curvature safety of 1.5 keeps elements
# under about a radius: 1 put one element across a 6 mm rod's radius at the
# default size and read its bending stress 20% high (test_fea.DefaultSizeAccuracy).
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

    An element of a mesh that max_h governs has edges near max_h. Where the mean
    element's edge is under half of it, small features (thin walls, fillets,
    chamfers) forced the refinement, and a larger ``mesh.size_mm`` will not
    coarsen it much.
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
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    return _area_center(face.wrapped)


def _area_center(shape) -> tuple[float, tuple[float, float, float]]:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, props)
    centre = props.CentreOfMass()
    return float(props.Mass()), (centre.X(), centre.Y(), centre.Z())


def occurrence_fingerprints(occurrence: "Occurrence") -> list[FaceFingerprint]:
    """Area and centre of mass of every face, by the scene's own ordinals."""
    out = []
    for selection in occurrence.entities("face"):
        area, centre = face_area_center(selection.shape())
        out.append(FaceFingerprint(selection.ref, int(selection._ordinal), area, centre))
    return out


def _write_brep(shape, path: Path) -> None:
    from OCP.BRepTools import BRepTools

    if not BRepTools.Write_s(shape, str(path)):
        raise RuntimeError(f"could not write the BREP the mesher reads: {path}")


def _match_faces(fingerprints: list[FaceFingerprint], ng_faces, scale: float) -> dict[int, int]:
    """``{netgen face index (0-based): cadgen ordinal}`` for EVERY face, verified.

    Order is the fast path (netgen face i <-> ordinal i+1); a face that does
    not agree there is matched by area and centre against all of netgen's
    faces, and an ambiguous or missing match is an error rather than a guess.
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


def _require_ten_node_tets(e3) -> None:
    """Refuse a mesh that is not all 10-node tetrahedra (``SecondOrder`` not applied).

    netgen's ``nodes`` field is only as wide as the element order: 4 columns on a
    first-order mesh. Older builds padded it with zeros instead; node numbers are
    1-based, so a zero in the first ten is the same signal.
    """
    nodes = e3["nodes"]
    if nodes.shape[1] < 10 or not (nodes[:, :10] > 0).all():
        raise RuntimeError("the mesher produced elements that are not 10-node tetrahedra")


def _require_elements(e3, order: int) -> None:
    if order == 2:
        _require_ten_node_tets(e3)
    elif e3["nodes"].shape[1] < 4 or not (e3["nodes"][:, :4] > 0).all():
        raise RuntimeError("the mesher produced elements that are not 4-node tetrahedra")


def _generate(geometry, ngocc, h: float, refine: float, order: int, size_field: dict | None, keys_of_face: dict[int, list]):
    """netgen's mesh at size ``h``; ``size_field`` adds local sizes, ``order`` 2 adds the mid-edge nodes.

    ``size_field`` is ``{"faces": {key: size_mm}, "points": [[x, y, z, size_mm], ...], "radius_mm": r}``:
    a face's key is what ``keys_of_face`` lists for its netgen index (a cadgen
    ordinal for one part, a face ref for an assembly); a point holds its size
    within ``radius_mm`` of it (its centre and six points at that distance,
    netgen grading the rest). With none, the call is today's.
    """
    import netgen.meshing as ngmesh

    if not size_field:
        mesh = geometry.GenerateMesh(maxh=h, **_meshing(refine))
    else:
        sizes = {key: float(size) for key, size in (size_field.get("faces") or {}).items()}
        if sizes:
            shape = geometry.shape
            for index, face in enumerate(shape.faces):
                wanted = [sizes[key] for key in keys_of_face.get(index, ()) if key in sizes]
                if wanted:
                    face.maxh = min(wanted)
            geometry = ngocc.OCCGeometry(shape)
        parameters = ngmesh.MeshingParameters(maxh=h, **_meshing(refine))
        radius = float(size_field.get("radius_mm") or 0.0)
        offsets = [(0.0, 0.0, 0.0)] + ([] if radius <= 0 else [
            tuple(radius * sign if axis == k else 0.0 for k in range(3)) for axis in range(3) for sign in (-1.0, 1.0)
        ])
        for x, y, z, size in size_field.get("points") or ():
            for dx, dy, dz in offsets:
                parameters.RestrictH(x=float(x) + dx, y=float(y) + dy, z=float(z) + dz, h=float(size))
        mesh = geometry.GenerateMesh(mp=parameters)
    if order == 2:
        mesh.SecondOrder()
    return mesh


def mesh_occurrence(
    occurrence: "Occurrence", *, max_h: float | None = None, refine: float = 1.0, order: int = 2,
    size_field: dict | None = None,
) -> VolumeMesh:
    """Mesh one placed occurrence with second-order tetrahedra (``order=1``: first-order, 4 nodes).

    ``refine`` also shrinks the elements at curved features by that ratio (:func:`_meshing`).
    ``size_field`` sets local sizes, faces by cadgen ordinal (:func:`_generate`).
    """
    require_fea_stack()
    import numpy as np

    from cadgen._internal.step_scene_loader import kernel_messages_on_stderr

    shape = occurrence.shape()
    fingerprints = occurrence_fingerprints(occurrence)
    diagonal = float(shape.bounding_box().diagonal)
    if not diagonal > 0:
        raise RuntimeError(f"{occurrence.ref} has no volume to mesh")
    h = float(max_h) if max_h else default_mesh_size(diagonal)

    started = time.perf_counter()
    import netgen.meshing as ngmesh
    import netgen.occ as ngocc

    with tempfile.TemporaryDirectory(prefix="cadgen-fea-") as tmp:
        brep = Path(tmp) / "occurrence.brep"
        _write_brep(shape.wrapped, brep)
        # netgen's C++ side prints to fd 1, the JSON result channel of every door.
        with kernel_messages_on_stderr():
            ngmesh.SetMessageImportance(0)
            geometry = ngocc.OCCGeometry(str(brep))
            mapping = _match_faces(fingerprints, list(geometry.faces), diagonal)
            mesh = _generate(geometry, ngocc, h, refine, order, size_field,
                             {index: [ordinal] for index, ordinal in mapping.items()})
            # Copies, deliberately: netgen hands out views into the mesh
            # object's own memory, and the mesh does not outlive this block.
            coordinates = np.array(mesh.Coordinates(), dtype=float, copy=True)
            e3 = mesh.Elements3D().NumPy().copy()
            e2 = mesh.Elements2D().NumPy().copy()
            del mesh, geometry

    if len(e3) == 0:
        raise RuntimeError(f"the mesher produced no volume elements for {occurrence.ref}; is it a closed solid?")
    _require_elements(e3, order)
    width = 10 if order == 2 else 4
    ordinal_of = np.zeros(int(e2["index"].max()) + 1, dtype=np.int64)
    for index, ordinal in mapping.items():
        ordinal_of[index + 1] = ordinal

    return VolumeMesh(
        nodes=coordinates,
        tets=np.ascontiguousarray(e3["nodes"][:, :width].astype(np.int64) - 1),
        boundary=np.ascontiguousarray(e2["nodes"][:, :6 if order == 2 else 3].astype(np.int64) - 1),
        boundary_ordinal=ordinal_of[e2["index"].astype(np.int64)],
        faces={fp.ordinal: fp for fp in fingerprints},
        max_h=h,
        bbox_diagonal=diagonal,
        seconds=time.perf_counter() - started,
    )


def _bbox_diagonal(shape) -> float:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return float(((xmax - xmin) ** 2 + (ymax - ymin) ** 2 + (zmax - zmin) ** 2) ** 0.5)


# Keast's 5-point rule for a tetrahedron, exact to degree 3: barycentric points and weights (of the unit tet's 1/6).
_KEAST = (
    ((0.25, 0.25, 0.25, 0.25), -2.0 / 15.0),
    *((tuple(0.5 if k == n else 1.0 / 6.0 for k in range(4)), 3.0 / 40.0) for n in range(4)),
)
_EDGES = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))


def curved_volumes(nodes, tets):
    """Each 10-node tet's volume (mm^3), its mid-edge nodes counted: the curved element, not its corners' straight one.

    The corner tets of a mesh of a round part sit inside the surface, so they
    sum to a few percent short of the B-rep; the curved elements do not.
    """
    import numpy as np

    points = nodes[tets]  # (E, 10, 3)
    total = np.zeros(len(tets))
    for bary, weight in _KEAST:
        # d(shape function)/d(barycentric coordinate), (4 coordinates, 10 nodes)
        slope = np.zeros((4, 10))
        for i in range(4):
            slope[i, i] = 4.0 * bary[i] - 1.0
        for n, (i, j) in enumerate(_EDGES, 4):
            slope[i, n], slope[j, n] = 4.0 * bary[j], 4.0 * bary[i]
        # x depends on three free coordinates (L0 = 1 - L1 - L2 - L3)
        jacobian = np.einsum("ka,eki->eai", (slope[1:] - slope[:1]).T, points)
        total += weight * np.abs(np.linalg.det(jacobian))
    return total


def check_domains(nodes, tets, domain, parts) -> None:
    """Raise unless each domain is the part it is taken to be.

    The mesher's volume numbers follow the solids' order in the glued shape; a
    mapping that drifted would give every element another part's material. Each
    domain's volume (summed over the curved elements) must match its part's
    within 5%, and its centroid must lie in its part's bounding box.
    """
    import numpy as np

    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

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
        low, high = np.array(box.Get()[:3]), np.array(box.Get()[3:])
        centroid = (corners[rows].mean(axis=1) * volumes[rows, None]).sum(axis=0) / volumes[rows].sum()
        if ((centroid < low - 1e-6) | (centroid > high + 1e-6)).any():
            raise RuntimeError(f"the mesh's volume {index} lies outside part {part.ref}; the mesher's volumes do not follow the parts")


def mesh_assembly(
    scene: "StepScene",
    part_refs: list[str],
    bonded: "list[Contact]",
    tolerance_mm: float,
    max_h: float | None = None,
    log=None,
    refine: float = 1.0,
    order: int = 2,
    size_field: dict | None = None,
) -> VolumeMesh:
    """Mesh the parts ``part_refs`` as one conforming mesh, bonded parts sharing nodes.

    ``bonded`` are the contacts to glue; parts not in any of them stay apart.
    The mesh's ``domain`` is the index into ``part_refs`` of each element's
    part, and ``faces`` holds every face of every part under its own ref, so a
    study's ``#o2.f6`` means the same face it does in the viewer. ``log``
    is told when gluing and meshing start; ``refine``, ``order`` and
    ``size_field`` are :func:`mesh_occurrence`'s, a size field's faces keyed by ref.
    """
    require_fea_stack()
    import numpy as np

    from cadgen._internal.fea.assembly import SharedSolid, display_names, glue, list_parts, part_faces
    from cadgen._internal.fea.checks import quoted
    from cadgen._internal.step_scene_loader import kernel_messages_on_stderr
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    by_ref = {part.ref: part for part in list_parts(scene)}
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
    diagonal = _bbox_diagonal(glued.shape)
    if not diagonal > 0:
        raise RuntimeError("the assembly has no volume to mesh")
    h = float(max_h) if max_h else default_mesh_size(diagonal)

    # Every face of every part, under its own ref; positions are 1-based.
    faces: dict[str, FaceFingerprint] = {}
    position_of: dict[tuple[int, int], int] = {}
    for i, part in enumerate(parts):
        for ordinal, face in enumerate(part_faces(part.shape), 1):
            area, centre = _area_center(face)
            ref = f"{part.ref}.f{ordinal}"
            faces[ref] = FaceFingerprint(ref, ordinal, area, centre)
            position_of[(i, ordinal)] = len(faces)
    refs = list(faces)

    # Which part faces each face of the glued shape came from.
    glued_faces = TopTools_IndexedMapOfShape()
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
        area, centre = _area_center(glued_faces.FindKey(k))
        glued_prints.append(FaceFingerprint(f"face {k} of the glued shape", k, area, centre))

    started = time.perf_counter()
    import netgen.meshing as ngmesh
    import netgen.occ as ngocc

    if log:
        log(f"meshing the glued shape at {h:.3g} mm")
    with tempfile.TemporaryDirectory(prefix="cadgen-fea-") as tmp:
        brep = Path(tmp) / "assembly.brep"
        _write_brep(glued.shape, brep)
        with kernel_messages_on_stderr():
            ngmesh.SetMessageImportance(0)
            geometry = ngocc.OCCGeometry(str(brep))
            mapping = _match_faces(glued_prints, list(geometry.faces), diagonal)
            mesh = _generate(geometry, ngocc, h, refine, order, size_field,
                             {index: [refs[position - 1] for position in sources.get(image, ())] for index, image in mapping.items()})
            coordinates = np.array(mesh.Coordinates(), dtype=float, copy=True)
            e3 = mesh.Elements3D().NumPy().copy()
            e2 = mesh.Elements2D().NumPy().copy()
            domains = int(mesh.GetNDomains()) if hasattr(mesh, "GetNDomains") else int(e3["index"].max())
            del mesh, geometry

    if len(e3) == 0:
        raise RuntimeError("the mesher produced no volume elements for the assembly; is every part a closed solid?")
    if domains != len(glued.solid_part):
        raise RuntimeError(f"the mesher made {domains} volumes from {len(glued.solid_part)} solids")
    _require_elements(e3, order)
    width = 10 if order == 2 else 4

    solid_part = np.array(glued.solid_part, dtype=np.int64)
    domain = solid_part[e3["index"].astype(np.int64) - 1]
    tets = np.ascontiguousarray(e3["nodes"][:, :width].astype(np.int64) - 1)
    check_domains(coordinates, tets, domain, parts)

    # netgen keeps the faces where parts are glued as surface elements, but they
    # are interior: they go to ``interface_triangles`` under the parts they join,
    # and every other triangle belongs to one part's face.
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
    surface = np.ascontiguousarray(e2["nodes"][:, :6 if order == 2 else 3].astype(np.int64) - 1)
    surface_index = e2["index"].astype(np.int64)
    outer = np.isin(surface_index, list(joint_of_glued), invert=True)
    interface_triangles: dict[tuple[int, int], np.ndarray] = {}
    for netgen_index, joint in joint_of_glued.items():
        rows = surface[surface_index == netgen_index]
        # A joint face can be listed once per side; keep one triangle each.
        _, first = np.unique(np.sort(rows[:, :3], axis=1), axis=0, return_index=True)
        interface_triangles[joint] = np.concatenate([interface_triangles[joint], rows[first]]) if joint in interface_triangles else rows[first]

    return VolumeMesh(
        nodes=coordinates,
        tets=tets,
        boundary=np.ascontiguousarray(surface[outer]),
        boundary_ordinal=position_of_glued[surface_index[outer]],
        faces=faces,
        max_h=h,
        bbox_diagonal=diagonal,
        seconds=time.perf_counter() - started,
        domain=domain,
        interface_faces=interface_faces,
        interface_triangles=interface_triangles,
        joint_faces=joint_faces,
        fuzzy_mm=glued.fuzzy_mm,
    )
