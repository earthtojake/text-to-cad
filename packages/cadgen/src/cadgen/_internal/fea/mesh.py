"""One STEP occurrence, or an assembly's glued parts -> quadratic tetrahedra, faces kept under their cadgen ordinal.

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

import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.assembly import Contact
    from cadgen.step_scene import Occurrence, StepScene

__all__ = ["FaceFingerprint", "VolumeMesh", "default_mesh_size", "face_area_center", "mesh_assembly", "mesh_occurrence", "occurrence_fingerprints", "require_fea_stack"]


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
    #: For an assembly, the fuzzy value the glue closed gaps with (0 = none).
    fuzzy_mm: float = 0.0


def default_mesh_size(bbox_diagonal: float) -> float:
    """The element size a study gets when it names none: a fortieth of the
    bounding diagonal, which lands a typical part at 30-100k DOF."""
    return max(bbox_diagonal / 40.0, 1e-3)


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


def mesh_occurrence(occurrence: "Occurrence", *, max_h: float | None = None) -> VolumeMesh:
    """Mesh one placed occurrence with second-order tetrahedra."""
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
            mesh = geometry.GenerateMesh(maxh=h)
            mesh.SecondOrder()
            # Copies, deliberately: netgen hands out views into the mesh
            # object's own memory, and the mesh does not outlive this block.
            coordinates = np.array(mesh.Coordinates(), dtype=float, copy=True)
            e3 = mesh.Elements3D().NumPy().copy()
            e2 = mesh.Elements2D().NumPy().copy()
            del mesh, geometry

    if len(e3) == 0:
        raise RuntimeError(f"the mesher produced no volume elements for {occurrence.ref}; is it a closed solid?")
    _require_ten_node_tets(e3)
    ordinal_of = np.zeros(int(e2["index"].max()) + 1, dtype=np.int64)
    for index, ordinal in mapping.items():
        ordinal_of[index + 1] = ordinal

    return VolumeMesh(
        nodes=coordinates,
        tets=np.ascontiguousarray(e3["nodes"][:, :10].astype(np.int64) - 1),
        boundary=np.ascontiguousarray(e2["nodes"][:, :6].astype(np.int64) - 1),
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


def mesh_assembly(
    scene: "StepScene",
    part_refs: list[str],
    bonded: "list[Contact]",
    tolerance_mm: float,
    max_h: float | None = None,
) -> VolumeMesh:
    """Mesh the parts ``part_refs`` as one conforming mesh, bonded parts sharing nodes.

    ``bonded`` are the contacts to glue; parts not in any of them stay apart.
    The mesh's ``domain`` is the index into ``part_refs`` of each element's
    part, and ``faces`` holds every face of every part under its own ref, so a
    study's ``#o2.f6`` means the same face it does in the viewer.
    """
    require_fea_stack()
    import numpy as np

    from cadgen._internal.fea.assembly import glue, list_parts, part_faces
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
    glued = glue(
        [part.shape for part in parts],
        [(index_of[c.a], index_of[c.b], c.gap_mm) for c in bonded if c.a in index_of and c.b in index_of],
        tolerance_mm,
    )
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
    glued_prints = []
    for k in range(1, glued_faces.Extent() + 1):
        area, centre = _area_center(glued_faces.FindKey(k))
        glued_prints.append(FaceFingerprint(f"face {k} of the glued shape", k, area, centre))

    started = time.perf_counter()
    import netgen.meshing as ngmesh
    import netgen.occ as ngocc

    with tempfile.TemporaryDirectory(prefix="cadgen-fea-") as tmp:
        brep = Path(tmp) / "assembly.brep"
        _write_brep(glued.shape, brep)
        with kernel_messages_on_stderr():
            ngmesh.SetMessageImportance(0)
            geometry = ngocc.OCCGeometry(str(brep))
            mapping = _match_faces(glued_prints, list(geometry.faces), diagonal)
            mesh = geometry.GenerateMesh(maxh=h)
            mesh.SecondOrder()
            coordinates = np.array(mesh.Coordinates(), dtype=float, copy=True)
            e3 = mesh.Elements3D().NumPy().copy()
            e2 = mesh.Elements2D().NumPy().copy()
            domains = int(mesh.GetNDomains()) if hasattr(mesh, "GetNDomains") else int(e3["index"].max())
            del mesh, geometry

    if len(e3) == 0:
        raise RuntimeError("the mesher produced no volume elements for the assembly; is every part a closed solid?")
    if domains != len(glued.solid_part):
        raise RuntimeError(f"the mesher made {domains} volumes from {len(glued.solid_part)} solids")
    _require_ten_node_tets(e3)

    # A face of the glued shape the mesher keeps as a boundary belongs to one
    # part's face (the interface faces it drops are interior).
    position_of_glued = np.zeros(int(e2["index"].max()) + 1, dtype=np.int64)
    for index, glued_index in mapping.items():
        if index + 1 < len(position_of_glued) and sources.get(glued_index):
            position_of_glued[index + 1] = sources[glued_index][0]
    solid_part = np.array(glued.solid_part, dtype=np.int64)

    return VolumeMesh(
        nodes=coordinates,
        tets=np.ascontiguousarray(e3["nodes"][:, :10].astype(np.int64) - 1),
        boundary=np.ascontiguousarray(e2["nodes"][:, :6].astype(np.int64) - 1),
        boundary_ordinal=position_of_glued[e2["index"].astype(np.int64)],
        faces=faces,
        max_h=h,
        bbox_diagonal=diagonal,
        seconds=time.perf_counter() - started,
        domain=solid_part[e3["index"].astype(np.int64) - 1],
        interface_faces=interface_faces,
        fuzzy_mm=glued.fuzzy_mm,
    )
