"""Linear-elastic modal analysis of a STEP part via Netgen + ngsolve.

Importing this module pulls in build123d, netgen, and ngsolve. Keep it out of
the CLI's module-level imports (load it inside the handler) so ``fea --help``
and the material table work without the solver stack installed.

Pipeline (battle-tested on flexure / orthoplanar-spring designs):
  1. Load STEP with build123d, export to a temp BREP.
     (Direct shape passing between build123d's and netgen's OCCT wrappers does
     not work; BREP file interchange is the reliable bridge.)
  2. Import BREP into netgen, tag the clamped face(s) as "fixed".
  3. Mesh, scale mm -> m.
  4. Assemble linear-elastic stiffness K and mass M on a vector H1 space.
  5. Solve K phi = lambda M phi for the lowest modes (PINVIT).
  6. Report f_i = sqrt(lambda_i)/(2 pi) and classify each mode by projecting
     it onto rigid-body translations/rotations of the moving body.

Gotcha encoded here: netgen's ``faces.Nearest(point)`` compares to face
*centres*, and a cylinder reports its axis centre, so concentric cylinders tie
and the wrong face gets clamped. Faces are selected by bounding box / area /
plane membership instead.
"""
from __future__ import annotations

import math
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from .materials import Material


class ModalError(Exception):
    """User-facing modal-analysis failure."""


# ---------------------------------------------------------------- face picking


def _face_bbox(face: Any) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    lo, hi = face.bounding_box
    return (float(lo[0]), float(lo[1]), float(lo[2])), (float(hi[0]), float(hi[1]), float(hi[2]))


def select_fixed_faces(ng_shape: Any, strategy: str) -> list[Any]:
    """Return the face(s) to clamp, chosen by an explicit strategy.

    strategies:
      bottom / top   largest planar face lying in the global min/max Z plane
      outer          face spanning the full XY extent (e.g. an outer ring/wall)
      largest        single largest-area face (fallback)
      auto           bottom if one exists, else largest
    """
    faces = list(ng_shape.faces)
    if not faces:
        raise ModalError("Imported geometry has no faces.")

    gmin = [math.inf, math.inf, math.inf]
    gmax = [-math.inf, -math.inf, -math.inf]
    for f in faces:
        lo, hi = _face_bbox(f)
        for i in range(3):
            gmin[i] = min(gmin[i], lo[i])
            gmax[i] = max(gmax[i], hi[i])
    extent = [gmax[i] - gmin[i] for i in range(3)]
    tol = 1e-6 + 1e-3 * max(extent)

    def planar_at_z(target_z: float) -> list[Any]:
        hits = []
        for f in faces:
            lo, hi = _face_bbox(f)
            if abs(hi[2] - lo[2]) <= tol and abs(lo[2] - target_z) <= tol:
                hits.append(f)
        return hits

    def largest(candidates: list[Any]) -> Any:
        return max(candidates, key=lambda f: float(f.mass))

    strategy = strategy.lower()
    if strategy in {"bottom", "top"}:
        target = gmin[2] if strategy == "bottom" else gmax[2]
        hits = planar_at_z(target)
        if not hits:
            raise ModalError(f"No planar face found at the {strategy} (Z={target:.3f}).")
        return [largest(hits)]
    if strategy == "outer":
        # An outer wall spans the full XY extent AND the full Z (thickness),
        # which distinguishes it from the large flat top/bottom faces that also
        # span XY but are flat in Z. Without the Z test, "outer" would clamp the
        # whole disk face and report wildly stiff (high) frequencies.
        hits = []
        for f in faces:
            lo, hi = _face_bbox(f)
            spans_xy = abs((hi[0] - lo[0]) - extent[0]) <= tol and abs((hi[1] - lo[1]) - extent[1]) <= tol
            spans_z = abs((hi[2] - lo[2]) - extent[2]) <= tol
            if spans_xy and spans_z:
                hits.append(f)
        if not hits:
            raise ModalError("No outer wall face spans the full XYZ extent (try --fixed bottom).")
        return [largest(hits)]
    if strategy == "largest":
        return [largest(faces)]
    if strategy == "auto":
        bottom = planar_at_z(gmin[2])
        return [largest(bottom)] if bottom else [largest(faces)]
    raise ModalError(f"Unknown fixed-face strategy '{strategy}'.")


# ----------------------------------------------------------------- mode labels


def _classify_mode(mesh: Any, fes: Any, vec: Any, center: np.ndarray) -> dict:
    import ngsolve as ngs

    gfu = ngs.GridFunction(fes)
    gfu.vec.data = vec
    pts, disp = [], []
    for v in mesh.vertices:
        p = v.point
        pts.append(p)
        disp.append(np.asarray(gfu(mesh(*p))))
    pts = np.asarray(pts)
    disp = np.asarray(disp)
    rel = pts - center

    fields = {
        "Tx": np.tile([1.0, 0, 0], (len(pts), 1)),
        "Ty": np.tile([0, 1.0, 0], (len(pts), 1)),
        "Tz": np.tile([0, 0, 1.0], (len(pts), 1)),
        "Rx": np.cross(np.array([1.0, 0, 0]), rel),
        "Ry": np.cross(np.array([0, 1.0, 0]), rel),
        "Rz": np.cross(np.array([0, 0, 1.0]), rel),
    }
    proj = {}
    for key, field in fields.items():
        norm = np.linalg.norm(field)
        if norm > 0:
            proj[key] = float(abs(np.sum(disp * (field / norm))))
    label = max(proj, key=proj.get) if proj else "?"
    pretty = {
        "Tx": "x-translation", "Ty": "y-translation", "Tz": "z-translation",
        "Rx": "rocking about x", "Ry": "rocking about y", "Rz": "z-rotation (torsion)",
    }
    return {"dominant": label, "description": pretty.get(label, label)}


# --------------------------------------------------------------------- solve


def run_modal(
    step_path: str,
    material: Material,
    *,
    fixed: str = "auto",
    num_modes: int = 6,
    maxh: float = 0.0,
    units_mm: bool = True,
    order: int = 2,
) -> dict:
    import build123d as bd
    import ngsolve as ngs
    from netgen.occ import OCCGeometry

    path = Path(step_path)
    if not path.exists():
        raise ModalError(f"STEP file not found: {path}")
    try:
        part = bd.import_step(str(path))
    except Exception as exc:  # noqa: BLE001
        raise ModalError(f"Failed to import STEP '{path}': {exc}") from exc
    if part is None or part.volume <= 0:
        raise ModalError(f"STEP '{path}' has no positive-volume solid.")

    scale = 1e-3 if units_mm else 1.0
    bb = part.bounding_box()
    model_span = max(bb.size.X, bb.size.Y, bb.size.Z)
    if maxh <= 0:
        maxh = model_span / 18.0  # ~18 elements across the largest dimension

    with tempfile.NamedTemporaryFile(suffix=".brep", delete=False) as tmp:
        bd.export_brep(part, tmp.name)
        brep_path = tmp.name

    geo = OCCGeometry(brep_path)
    ng_shape = geo.shape
    fixed_faces = select_fixed_faces(ng_shape, fixed)
    fixed_area = 0.0
    for f in fixed_faces:
        f.name = "fixed"
        fixed_area += float(f.mass)

    geo = OCCGeometry(ng_shape)
    ngmesh = geo.GenerateMesh(maxh=maxh)
    ngmesh.Scale(scale)
    mesh = ngs.Mesh(ngmesh)

    if "fixed" not in set(mesh.GetBoundaries()):
        raise ModalError("Failed to tag a 'fixed' boundary; try a different --fixed strategy.")

    lam, mu = material.lame()
    fes = ngs.VectorH1(mesh, order=order, dirichlet="fixed")
    u, v = fes.TnT()

    def strain(w):
        return 0.5 * (ngs.Grad(w) + ngs.Grad(w).trans)

    def stress(w):
        eps = strain(w)
        return 2 * mu * eps + lam * ngs.Trace(eps) * ngs.Id(3)

    a = ngs.BilinearForm(fes, symmetric=True)
    a += ngs.InnerProduct(stress(u), strain(v)) * ngs.dx
    m = ngs.BilinearForm(fes, symmetric=True)
    m += material.rho * (u * v) * ngs.dx

    pre = ngs.Preconditioner(a, "direct", inverse="sparsecholesky")
    with ngs.TaskManager():
        a.Assemble()
        m.Assemble()
        lams, evecs = ngs.solvers.PINVIT(
            a.mat, m.mat, pre, num=num_modes, maxit=200, printrates=False
        )

    com = part.center()
    center = np.array([com.X * scale, com.Y * scale, com.Z * scale])

    modes = []
    for i in range(len(lams)):
        lam_i = max(float(lams[i]), 0.0)
        freq = math.sqrt(lam_i) / (2 * math.pi)
        label = _classify_mode(mesh, fes, evecs[i], center)
        modes.append({
            "index": i + 1,
            "frequencyHz": round(freq, 4),
            "eigenvalue": lam_i,
            **label,
        })

    return {
        "ok": True,
        "target": str(path),
        "material": {"name": material.name, "E": material.E, "nu": material.nu, "rho": material.rho},
        "fixed": {"strategy": fixed, "faceCount": len(fixed_faces), "areaMm2": round(fixed_area, 4)},
        "mesh": {"elements": mesh.ne, "vertices": mesh.nv, "maxh": round(maxh, 4), "order": order},
        "units": "mm" if units_mm else "m",
        "modes": modes,
    }
