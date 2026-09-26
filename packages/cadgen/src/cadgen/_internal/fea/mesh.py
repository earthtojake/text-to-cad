"""One STEP occurrence -> quadratic tetrahedra, faces kept under their cadgen ordinal.

The mesher is netgen (LGPL-2.1, the ``netgen-mesher`` wheel with its own
OpenCascade). It cannot take an OCP shape object directly -- two pybind11 OCC
builds are foreign to each other -- so the placed occurrence is written to a
BREP file, which netgen reads. Both sides walk the B-rep in explorer order, so
netgen's face ``i`` is cadgen's face ordinal ``i+1`` in practice; that is an
implementation property, not a contract, so every face a study names is
VERIFIED by area and centre of mass against the OCP face the scene resolved,
and matched geometrically when the order differs.

Import order matters on Linux: netgen loads its OpenCascade with RTLD_GLOBAL,
so the CAD kernel (OCP) is imported first, here, before netgen ever is.
"""

from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

    from cadgen.step_scene import Occurrence

__all__ = ["FaceFingerprint", "VolumeMesh", "default_mesh_size", "face_area_center", "mesh_occurrence", "occurrence_fingerprints", "require_fea_stack"]


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
    boundary_ordinal: "np.ndarray"
    #: Every face fingerprint of the occurrence, by ordinal.
    faces: dict[int, FaceFingerprint]
    max_h: float
    bbox_diagonal: float
    seconds: float


def default_mesh_size(bbox_diagonal: float) -> float:
    """The element size a study gets when it names none: a fortieth of the
    bounding diagonal, which lands a typical part at 30-100k DOF."""
    return max(bbox_diagonal / 40.0, 1e-3)


def face_area_center(face) -> tuple[float, tuple[float, float, float]]:
    """Area (mm^2) and centre of mass (mm) of one build123d face."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face.wrapped, props)
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
    if not np.all(e3["np"] == 10):
        raise RuntimeError("the mesher produced elements that are not 10-node tetrahedra")
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
