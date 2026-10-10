"""Electric and magnetic fields on a meshed study: the region they are solved in, and the solves.

Three static (DC) problems and one time-harmonic (AC) one, each linear:

- **electrostatics**: div(eps grad phi) = 0 with faces held at a voltage. A part
  whose material conducts (resistivity under :data:`CONDUCTOR_BELOW_OHM_M`) is
  an equipotential: all its nodes are one unknown, held when any of its faces
  is held, floating (zero net charge) otherwise. Every other part is a
  dielectric with its relative permittivity; the air around the parts, when the
  study asks for it, has air's.
- **steady current**: div(sigma grad V) = 0 with faces held at a voltage and
  currents put in through faces. A part above :data:`INSULATOR_ABOVE_OHM_M`
  carries no current.
- **magnetostatics**: curl(nu curl A) = J on lowest-order Nédélec elements, the
  source a coil's current spread evenly over its cross-section and wound around
  its axis, nu = 1 / (mu0 mu_r) per part, tangential A = 0 on the air box. The
  curl-curl matrix is singular on gradients; a tiny mass term (1e-8 of it)
  gauges it, and every number read from the answer goes through B = curl A,
  which the gauge does not touch (the energy is (1/2) integral nu |B|^2, not
  (1/2) integral A.J).
- **AC magnetics** (:func:`ac_solve`): curl(nu curl A) + sigma (j omega A +
  grad phi) = J_s at one frequency, A complex on the same Nédélec elements and
  the conductors' voltage phi on P2 elements, so the eddy current
  -sigma (j omega A + grad phi) is complete to first order in each element.

The region is either the run's own part mesh (no air: a dielectric between
electrodes, a conductor carrying current) or the parts and a box of air around
them, glued by an OCP general fuse into one conforming netgen mesh
(:func:`build_region`), fine at the parts' faces and coarser out in the air.

Units: mm, V, A. eps0 is in F/mm, mu0 in H/mm, so a capacitance is in F, a
charge in C, an energy in J, B = curl A in Wb/mm^2 (x 1e6 is tesla) and a force
from J x B or the Maxwell stress x 1e3 is in newtons. Numeric imports live
inside the functions.
"""

from __future__ import annotations

import math
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

__all__ = [
    "ACSolve", "AIR_EPS_R", "AIR_MU_R", "CONDUCTOR_BELOW_OHM_M", "EPS0", "Fed", "INSULATOR_ABOVE_OHM_M", "MU0", "Region",
    "ac_solve", "air_box", "build_region", "coil_source", "curl_curl", "element_at", "face_area", "face_dofs_p2", "face_mean",
    "flux_load", "lorentz_force", "magnetic_force", "node_gradients", "part_region", "scalar_solve", "skin_depth_mm",
    "stiffness", "to_part_mesh", "volume_load",
]

#: Vacuum permittivity, F/mm (NIST CODATA 2022: 8.8541878188e-12 F/m).
EPS0 = 8.8541878188e-15
#: Vacuum permeability, H/mm (NIST CODATA 2022: 1.25663706127e-6 N/A^2).
MU0 = 1.25663706127e-9
#: Dry air at one atmosphere (HyperPhysics dielectric table: 1.00059; Engineering Toolbox: 1.00000037 for mu_r).
AIR_EPS_R = 1.00059
AIR_MU_R = 1.00000037
#: A material under this resistivity (ohm m) is a conductor: an equipotential in electrostatics.
CONDUCTOR_BELOW_OHM_M = 1.0
#: A material over this resistivity (ohm m) is an insulator: it carries no current in a DC study.
INSULATOR_ABOVE_OHM_M = 1.0e3
#: The gauge: the mass term's share of the curl-curl diagonal.
GAUGE = 1e-8


@dataclass
class Region:
    """Where a field is solved: a scalar element space, each element's part, and each named face's DOF."""

    space: Any                       # FemSpace (its scalar basis carries the potential)
    domain: "np.ndarray"             # (E,) the part each element is in; ``parts`` for the air
    parts: int
    air: bool
    #: (part, ordinal) -> the boundary rows (into ``space.boundary_quadratic``) on that part's face.
    face_rows: dict[tuple[int, int], "np.ndarray"] = field(default_factory=dict)
    #: The mesh it was made from (the run's for a part region; its own for an air region).
    volume: Any = None
    seconds: float = 0.0
    #: Element size at the parts and out in the air, mm (an air region).
    size_mm: float = 0.0
    far_mm: float = 0.0
    #: The box of air (low, high), mm.
    box: tuple | None = None

    _hcurl: Any = field(default=None, repr=False)
    _p2: Any = field(default=None, repr=False)

    @property
    def AIR(self) -> int:
        return self.parts

    @property
    def space_hcurl(self):
        """Lowest-order Nédélec elements on the region's (linear) mesh: the vector potential's space."""
        if self._hcurl is None:
            from skfem import Basis, ElementTetN0

            self._hcurl = Basis(self.space.mesh, ElementTetN0())
        return self._hcurl

    def face_dofs(self, part: int, ordinal: int) -> "np.ndarray":
        import numpy as np

        rows = self.face_rows.get((part, ordinal))
        if rows is None or len(rows) == 0:
            return np.zeros(0, dtype=np.int64)
        return np.unique(self.space.boundary_quadratic[rows])

    def part_dofs(self, part: int) -> "np.ndarray":
        import numpy as np

        return np.unique(self.space.element_dofs[self.domain == part])


# -- the region ----------------------------------------------------------------------------------------


def part_region(space, volume, face_keys: dict[tuple[int, int], int], parts: int) -> Region:
    """The run's own part mesh as a region: ``face_keys`` maps (part, ordinal) to the mesh's boundary ordinal."""
    import numpy as np

    domain = np.zeros(len(space.tets), dtype=np.int64) if volume.domain is None else np.asarray(volume.domain, dtype=np.int64)
    rows = {key: np.flatnonzero(volume.boundary_ordinal == ordinal) for key, ordinal in face_keys.items()}
    return Region(space=space, domain=domain, parts=parts, air=False, face_rows=rows, volume=volume,
                  size_mm=float(volume.max_h), far_mm=float(volume.max_h))


def _bounds(shapes) -> tuple[list[float], list[float]]:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    for shape in shapes:
        BRepBndLib.AddOptimal_s(shape, box, False, False)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return [xmin, ymin, zmin], [xmax, ymax, zmax]


def air_box(shapes, around_mm) -> tuple[list[float], list[float]]:
    """The box of air: the parts' bounding box grown by ``around_mm`` on every side, or by
    ``(low, high)`` per side (each [x, y, z]; 0 leaves that wall flush with the parts)."""
    low, high = _bounds(shapes)
    if isinstance(around_mm, (int, float)):
        below = above = [float(around_mm)] * 3
    else:
        below, above = around_mm
    return [c - d for c, d in zip(low, below)], [c + d for c, d in zip(high, above)]


def build_region(shapes: list, *, around_mm, size_mm: float, far_mm: float, order: int = 2,
                 points: list | None = None, radius_mm: float = 0.0, part_sizes: dict[int, float] | None = None) -> Region:
    """The parts and a box of air around them as one conforming mesh.

    ``shapes`` are the parts' placed OCP solids, in part order; the air is the
    box (:func:`air_box`) minus them. The parts and the air are glued by a
    general fuse (faces they share are meshed once), then netgen meshes the lot:
    ``size_mm`` on every face of every part, growing to ``far_mm`` in the air.
    ``points`` ([x, y, z, size], within ``radius_mm``) hold a size anywhere
    (the centre of a coil); ``part_sizes`` (part index -> mm) mesh one part's
    faces finer than ``size_mm`` (a conductor's skin). ``around_mm`` is as
    :func:`air_box` takes it. Each element's ``domain`` is its part's index, the
    air ``len(shapes)``.
    """
    import numpy as np
    from OCP.BRep import BRep_Builder
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS_Compound
    from OCP.TopTools import TopTools_IndexedMapOfShape

    from cadgen._internal.fea import mesh as part_mesh
    from cadgen._internal.fea.assembly import SharedSolid, glue
    from cadgen._internal.fea.mesh import FaceFingerprint, VolumeMesh, _area_center, require_fea_stack
    from cadgen._internal.fea.femspace import FemSpace
    from cadgen._internal.step_scene_loader import kernel_messages_on_stderr

    require_fea_stack()
    started = time.perf_counter()
    low, high = air_box(shapes, around_mm)
    box = BRepPrimAPI_MakeBox(gp_Pnt(*low), gp_Pnt(*high)).Shape()
    tool = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(tool)
    for shape in shapes:
        builder.Add(tool, shape)
    cut = BRepAlgoAPI_Cut(box, tool)
    if not cut.IsDone():
        raise RuntimeError("the boolean that makes the air around the parts failed")
    air = cut.Shape()
    n = len(shapes)
    try:
        glued = glue([*shapes, air], [(i, n, 0.0) for i in range(n)], 0.1)
    except SharedSolid as fused:
        raise ValueError(f"parts {fused.first + 1} and {fused.second + 1} overlap; an electric or magnetic study needs "
                         "parts that touch at most: fix the geometry") from None

    faces = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(glued.shape, TopAbs_FACE, faces)
    prints = []
    for k in range(1, faces.Extent() + 1):
        area, centre = _area_center(faces.FindKey(k))
        prints.append(FaceFingerprint(f"face {k} of the region", k, area, centre))
    # Which part face each glued face is an image of; the air's own faces belong to no part.
    source: dict[int, list[tuple[int, int]]] = {}
    for i in range(n):
        for ordinal, images in enumerate(glued.face_images[i], 1):
            for image in images:
                source.setdefault(image, []).append((i, ordinal))
    diagonal = float(np.linalg.norm(np.subtract(high, low)))
    far = max(float(far_mm), float(size_mm))
    finer = part_sizes or {}
    size_field = {"faces": {k: min([float(size_mm), *(float(finer[i]) for i, _ in source[k] if i in finer)]) for k in source}}
    if points:
        size_field["points"] = [list(map(float, p)) for p in points]
        size_field["radius_mm"] = float(radius_mm)

    import netgen.meshing as ngmesh
    import netgen.occ as ngocc

    with tempfile.TemporaryDirectory(prefix="cadgen-em-") as tmp:
        brep = Path(tmp) / "region.brep"
        part_mesh._write_brep(glued.shape, brep)
        with kernel_messages_on_stderr():
            ngmesh.SetMessageImportance(0)
            geometry = ngocc.OCCGeometry(str(brep))
            mapping = part_mesh._match_faces(prints, list(geometry.faces), diagonal)
            keys = {index: [k] for index, k in mapping.items()}
            mesh = part_mesh._generate(geometry, ngocc, far, 1.0, order, size_field, keys)
            coordinates = np.array(mesh.Coordinates(), dtype=float, copy=True)
            e3 = mesh.Elements3D().NumPy().copy()
            e2 = mesh.Elements2D().NumPy().copy()
            del mesh, geometry
    if len(e3) == 0:
        raise RuntimeError("the mesher produced no elements for the parts and the air")
    part_mesh._require_elements(e3, order)
    width = 10 if order == 2 else 4
    solid_part = np.array(glued.solid_part, dtype=np.int64)
    domain = solid_part[e3["index"].astype(np.int64) - 1]
    glued_of = np.zeros(int(e2["index"].max()) + 1, dtype=np.int64)
    for index, k in mapping.items():
        if index + 1 < len(glued_of):
            glued_of[index + 1] = k
    surface = np.ascontiguousarray(e2["nodes"][:, :6 if order == 2 else 3].astype(np.int64) - 1)
    # A face shared by two solids may be listed once per side: keep one triangle each.
    _, first = np.unique(np.sort(surface[:, :3], axis=1), axis=0, return_index=True)
    first = np.sort(first)
    surface = surface[first]
    ordinal = glued_of[e2["index"].astype(np.int64)][first]
    volume = VolumeMesh(
        nodes=coordinates, tets=np.ascontiguousarray(e3["nodes"][:, :width].astype(np.int64) - 1),
        boundary=surface, boundary_ordinal=ordinal, faces={}, max_h=far, bbox_diagonal=diagonal,
        seconds=time.perf_counter() - started, domain=domain,
    )
    space = FemSpace.build(volume, order)
    rows: dict[tuple[int, int], list] = {}
    for k, owners in source.items():
        at = np.flatnonzero(ordinal == k)
        for owner in owners:
            rows.setdefault(owner, []).append(at)
    face_rows = {key: np.concatenate(value) for key, value in rows.items()}
    return Region(space=space, domain=domain, parts=n, air=True, face_rows=face_rows, volume=volume,
                  seconds=time.perf_counter() - started, size_mm=float(size_mm), far_mm=far,
                  box=(tuple(low), tuple(high)))


# -- scalar potentials ---------------------------------------------------------------------------------


def coefficient(region: Region, per_domain: list[float]):
    """One value per domain (parts, then the air) at the scalar basis's quadrature points."""
    import numpy as np

    values = np.asarray(per_domain, dtype=float)[region.domain]
    return np.repeat(values[:, None], region.space.scalar.X.shape[1], axis=1)


def stiffness(region: Region, per_domain: list[float]):
    """∫ c ∇u·∇v on the scalar basis, c per domain."""
    from skfem import BilinearForm, asm

    @BilinearForm
    def form(u, v, w):
        return w["c"] * (u.grad[0] * v.grad[0] + u.grad[1] * v.grad[1] + u.grad[2] * v.grad[2])

    return asm(form, region.space.scalar, c=coefficient(region, per_domain)).tocsr()


@dataclass
class Solved:
    x: "np.ndarray"                  # the potential at every scalar DOF
    residual: "np.ndarray"           # K x - f: what each held DOF takes in (a charge / eps0, a current)
    how: str
    #: The reduced system, to solve again with other held values (a capacitance's unit solve).
    resolve: Any = None


def scalar_solve(K, n: int, held: list[tuple["np.ndarray", float]], ties: list["np.ndarray"], f: "np.ndarray | None",
                 *, fixed_zero: "np.ndarray | None" = None, solver: str | None = None) -> Solved:
    """K x = f with each group of DOF in ``held`` at its value and each group in ``ties`` one unknown.

    A tied group that is also held is held whole. ``fixed_zero`` DOF (no
    element of theirs conducts) are set to 0. Direct (superlu) unless the
    plan's ``solver`` is iterative, then AMG + CG. The returned ``resolve``
    takes new held values (in the order of ``held``) and solves again on the
    same factorisation.
    """
    import numpy as np
    import scipy.sparse as sparse
    import scipy.sparse.linalg as spla

    rep = np.arange(n)
    for group in ties:
        group = np.asarray(group, dtype=np.int64)
        if len(group):
            rep[group] = group[0]
    unique, reduced_of = np.unique(rep, return_inverse=True)
    m = len(unique)
    P = sparse.csr_matrix((np.ones(n), (np.arange(n), reduced_of)), shape=(n, m))
    Kr = (P.T @ K @ P).tocsr()
    f = np.zeros(n) if f is None else f
    fr = P.T @ f
    held_r = [np.unique(reduced_of[np.asarray(dofs, dtype=np.int64)]) for dofs, _ in held]
    zero_r = np.unique(reduced_of[fixed_zero]) if fixed_zero is not None and len(fixed_zero) else np.zeros(0, dtype=np.int64)
    fixed = np.unique(np.concatenate([*held_r, zero_r])) if held_r or len(zero_r) else np.zeros(0, dtype=np.int64)
    free = np.setdiff1d(np.arange(m), fixed)
    Kff = Kr[free][:, free].tocsc()
    iterative = solver in ("iterative", "matrix_free")
    if iterative:
        import pyamg

        ml = pyamg.smoothed_aggregation_solver(Kff.tocsr(), symmetry="symmetric", strength="symmetric", smooth="energy",
                                               max_coarse=500)

        def solve(rhs):
            return ml.solve(rhs, tol=1e-10, accel="cg", maxiter=600)

        how = "amg+cg"
    else:
        lu = spla.splu(Kff)
        solve = lu.solve
        how = "superlu"

    def run(values: list[float]) -> tuple["np.ndarray", "np.ndarray"]:
        xr = np.zeros(m)
        for dofs, value in zip(held_r, values):
            xr[dofs] = value
        xr[zero_r] = 0.0
        if len(free):
            xr[free] = solve(fr[free] - Kr[free][:, fixed] @ xr[fixed]) if len(fixed) else solve(fr[free])
        x = P @ xr
        return x, K @ x - f

    x, residual = run([value for _, value in held])
    return Solved(x, residual, how, resolve=lambda values: run(values)[0])


def node_gradients(region: Region, x: "np.ndarray", elements: "np.ndarray | None" = None,
                   scale: "np.ndarray | None" = None):
    """∇x at each element's own nodes, and its magnitude (times ``scale`` per element, when given) averaged at
    every scalar DOF over ``elements`` (a mask; all by default): ((E, nodes, 3) gradient, (DOF,) mean magnitude,
    (E, nodes) magnitude)."""
    import numpy as np
    from skfem import CellBasis

    space = region.space
    element = space.scalar.elem
    points = np.ascontiguousarray(element.doflocs.T)
    basis = CellBasis(space.mesh, element, quadrature=(points, np.full(points.shape[1], 1.0 / points.shape[1])))
    grad = np.moveaxis(basis.interpolate(x).grad, 0, 2)          # (E, nodes, 3)
    magnitude = np.linalg.norm(grad, axis=2)
    if scale is not None:
        magnitude = magnitude * np.asarray(scale, dtype=float)[:, None]
    mask = np.ones(len(grad), dtype=bool) if elements is None else np.asarray(elements, dtype=bool)
    dofs = space.scalar.element_dofs.T                           # (E, nodes), the element's node order
    total = np.zeros(space.scalar_count)
    count = np.zeros(space.scalar_count)
    np.add.at(total, dofs[mask].ravel(), magnitude[mask].ravel())
    np.add.at(count, dofs[mask].ravel(), 1.0)
    return grad, total / np.maximum(count, 1.0), magnitude


def face_mean(region: Region, rows: "np.ndarray", values: "np.ndarray") -> float:
    """The area-weighted mean of a nodal field over boundary rows (each triangle's corner mean, flat)."""
    import numpy as np

    triangles = region.space.boundary_quadratic[rows]
    corners = region.space.dof_locations[triangles[:, :3]]
    area = 0.5 * np.linalg.norm(np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1)
    nodes = triangles[:, 3:] if triangles.shape[1] == 6 else triangles[:, :3]
    return float((area * values[nodes].mean(axis=1)).sum() / area.sum())


def face_area(region: Region, rows: "np.ndarray") -> float:
    import numpy as np

    triangles = region.space.boundary_quadratic[rows]
    corners = region.space.dof_locations[triangles[:, :3]]
    return float(0.5 * np.linalg.norm(np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1).sum())


def flux_load(region: Region, rows: "np.ndarray", total: float) -> "np.ndarray":
    """∫ (total / area) v over the faces of ``rows``: a current spread evenly over its faces."""
    from skfem import LinearForm, asm

    facets = region.space.facets_of_rows(rows)
    boundary = region.space.scalar.boundary(facets)
    area = float(boundary.dx.sum())
    density = total / area

    @LinearForm
    def form(v, w):
        return density * v

    return asm(form, boundary)


def volume_load(region: Region, density) -> "np.ndarray":
    """∫ q v over every element, q at the scalar basis's quadrature points."""
    from skfem import LinearForm, asm

    @LinearForm
    def form(v, w):
        return w["q"] * v

    return asm(form, region.space.scalar, q=density)


# -- moving fields onto the run's part mesh -------------------------------------------------------------


def to_part_mesh(region: Region, values: "np.ndarray", target_space, target_domain: "np.ndarray | None") -> "np.ndarray":
    """A nodal field of an air region carried onto the run's part mesh: each part's nodes take the value of
    the nearest node of the same part in the region (both meshes put a node on every corner of a face)."""
    import numpy as np
    from scipy.spatial import cKDTree

    out = np.zeros(target_space.scalar_count)
    target_elements = target_space.element_dofs
    domain = np.zeros(len(target_elements), dtype=np.int64) if target_domain is None else np.asarray(target_domain)
    source_locations = region.space.dof_locations
    for part in range(region.parts):
        source = np.unique(region.space.element_dofs[region.domain == part])
        target = np.unique(target_elements[domain == part])
        if len(source) == 0 or len(target) == 0:
            continue
        _, nearest = cKDTree(source_locations[source]).query(target_space.dof_locations[target])
        out[target] = values[source[nearest]]
    return out


# -- magnetostatics ------------------------------------------------------------------------------------


def coil_source(region: Region, part: int, turns: float, amps: float, point, direction) -> tuple["np.ndarray", float, float]:
    """The current density of a coil wound on ``part``: turns x amps spread evenly over its cross-section,
    flowing around the axis (``point``, ``direction``, right-handed). Returns (J at the Nédélec basis's
    quadrature points as (3, E, Q) A/mm², the cross-section in mm², the smallest radius in mm).

    The cross-section is (1 / 2 pi) ∫ dV / r over the part, exact for a ring of any section."""
    import numpy as np

    basis = region.space_hcurl
    axis = np.asarray(direction, dtype=float)
    axis = axis / np.linalg.norm(axis)
    origin = np.asarray(point, dtype=float)
    X = basis.mapping.F(basis.quadrature[0])                      # (3, E, Q)
    rel = X - origin[:, None, None]
    along = np.einsum("i,ieq->eq", axis, rel)
    radial = rel - axis[:, None, None] * along[None]
    r = np.linalg.norm(radial, axis=0)
    inside = region.domain == part
    if not inside.any():
        raise ValueError("the coil's part has no elements in the mesh")
    r_in = r[inside]
    smallest = float(r_in.min())
    section = float((basis.dx[inside] / np.maximum(r_in, 1e-12)).sum() / (2.0 * math.pi))
    density = turns * amps / section
    tangent = np.cross(axis[:, None, None], radial, axis=0) / np.maximum(r, 1e-12)[None]
    J = np.where(inside[None, :, None], density * tangent, 0.0)
    return J, section, smallest


@dataclass
class MagneticSolve:
    A: "np.ndarray"
    B: "np.ndarray"                  # (E, 3) Wb/mm² per element (x 1e6: tesla)
    energy_J: float
    how: str
    dofs: int


def curl_curl(region: Region, mu_r: list[float], J, *, solver: str | None = None) -> MagneticSolve:
    """curl(nu curl A) = J, tangential A = 0 on the box, nu = 1 / (mu0 mu_r) per domain, gauged by a tiny mass term."""
    import numpy as np
    import scipy.sparse.linalg as spla
    from skfem import BilinearForm, LinearForm, asm
    from skfem.helpers import curl, dot

    basis = region.space_hcurl
    nu = np.repeat((1.0 / (MU0 * np.asarray(mu_r, dtype=float)))[region.domain][:, None], basis.X.shape[1], axis=1)

    @BilinearForm
    def stiff(u, v, w):
        return w["nu"] * dot(curl(u), curl(v))

    @BilinearForm
    def mass(u, v, w):
        return dot(u, v)

    @LinearForm
    def source(v, w):
        return dot(w["J"], v)

    K = asm(stiff, basis, nu=nu)
    M = asm(mass, basis)
    f = asm(source, basis, J=J)
    delta = GAUGE * float(K.diagonal().mean()) / float(M.diagonal().mean())
    A_matrix = (K + delta * M).tocsr()
    held = basis.get_dofs(region.space.mesh.boundary_facets()).all()
    free = np.setdiff1d(np.arange(basis.N), held)
    Aff = A_matrix[free][:, free]
    x = np.zeros(basis.N)
    how = "superlu"
    if solver in ("iterative", "matrix_free"):
        import pyamg

        residuals: list[float] = []
        ml = pyamg.smoothed_aggregation_solver(Aff, symmetry="symmetric", max_coarse=500)
        x[free] = ml.solve(f[free], tol=1e-10, accel="cg", maxiter=2000, residuals=residuals)
        how = f"amg+cg ({len(residuals)} iterations)"
        if not residuals or residuals[-1] > 1e-6 * max(residuals[0], 1e-300):
            x[free] = spla.spsolve(Aff.tocsc(), f[free])
            how = "superlu (after amg)"
    else:
        x[free] = spla.spsolve(Aff.tocsc(), f[free])
    curl_q = curl(basis.interpolate(x))                           # (3, E, Q), constant per element
    B = np.ascontiguousarray((curl_q * basis.dx[None]).sum(axis=2).T / basis.dx.sum(axis=1)[:, None])
    volume = basis.dx.sum(axis=1)
    nu_e = 1.0 / (MU0 * np.asarray(mu_r, dtype=float)[region.domain])
    energy = float(0.5 * (nu_e * (B ** 2).sum(axis=1) * volume).sum())
    return MagneticSolve(x, B, energy, how, int(basis.N))


def element_volumes(region: Region) -> "np.ndarray":
    return region.space_hcurl.dx.sum(axis=1)


def lorentz_force(region: Region, J, B: "np.ndarray", part: int) -> "np.ndarray":
    """∫ J x B over ``part``, newtons."""
    import numpy as np

    basis = region.space_hcurl
    inside = region.domain == part
    Jm = (J * basis.dx[None]).sum(axis=2)                         # (3, E): ∫ J over each element
    force = np.cross(Jm.T[inside], B[inside]).sum(axis=0)
    return force * 1e3


def magnetic_force(region: Region, B: "np.ndarray", part: int) -> "np.ndarray":
    """The Maxwell stress force on a part, newtons, read the eggshell way: F = -∫ T ∇w dV over what surrounds it,
    T = nu0 (B Bᵀ - |B|²/2 I), w = 1 on the part's nodes falling to 0 one element out (linear). A volume
    average over the elements touching the part, steadier than the stress on its faces alone with fields
    that are constant per element."""
    import numpy as np
    from skfem import Basis, ElementTetP1

    mesh = region.space.mesh
    basis = Basis(mesh, ElementTetP1())
    w = np.zeros(basis.N)
    w[np.unique(mesh.t[:, region.domain == part])] = 1.0
    grad = basis.interpolate(w).grad.mean(axis=2).T             # (E, 3), constant per element
    outside = region.domain != part
    volume = basis.dx.sum(axis=1)
    Bo = B[outside]
    g = grad[outside]
    nu0 = 1.0 / MU0
    Tg = nu0 * (Bo * np.einsum("ij,ij->i", Bo, g)[:, None] - 0.5 * (Bo ** 2).sum(axis=1)[:, None] * g)
    return -(Tg * volume[outside][:, None]).sum(axis=0) * 1e3


def element_at(region: Region, points: "np.ndarray") -> "np.ndarray":
    """The element holding each point (-1 for one outside the mesh), on the region's linear mesh."""
    import numpy as np

    mesh = region.space.mesh
    finder = mesh.element_finder()
    out = np.full(len(points), -1, dtype=np.int64)
    for i, p in enumerate(points):
        try:
            out[i] = int(finder(np.array([p[0]]), np.array([p[1]]), np.array([p[2]]))[0])
        except ValueError:
            out[i] = -1
    return out


# -- time-harmonic (AC) magnetics ----------------------------------------------------------------------


def skin_depth_mm(resistivity_ohm_m: float, mu_r: float, frequency_Hz: float) -> float:
    """delta = sqrt(rho / (pi f mu0 mu_r)), mm: the depth a current at this frequency crowds into."""
    if not frequency_Hz > 0:
        return math.inf
    return math.sqrt(resistivity_ohm_m / (math.pi * frequency_Hz * MU0 * 1e3 * mu_r)) * 1e3


@dataclass
class Fed:
    """A conductor fed a current through faces on the box's walls: its input face is one voltage, its current
    ``amps`` (amplitude); the return face is held at 0 V."""

    into: "np.ndarray"               # the input face's P2 DOF
    amps: float


@dataclass
class ACSolve:
    A: "np.ndarray"                  # complex Nédélec DOF, Wb/mm
    phi: "np.ndarray"                # complex P2 DOF (0 off the conductors), V
    B: "np.ndarray"                  # (E, 3) complex amplitude per element, Wb/mm² (x 1e6: tesla)
    J: "np.ndarray"                  # (3, E, Q) complex current density induced or fed in the conductors, A/mm²
    loss: "np.ndarray"               # (E, Q) time-averaged Joule loss density |J|² / (2 sigma), W/mm³
    loss_by_domain: "np.ndarray"     # (domains,) W
    energy_J: float                  # time-averaged magnetic energy (1/4) ∫ nu |B|², J
    how: str
    dofs: int
    vertex_J: "np.ndarray" = None    # (E, 4) |J| amplitude at each element's corners, A/mm²
    fed_V: list = field(default_factory=list)   # each fed conductor's input voltage (complex amplitude), V
    basis_p2: Any = None


def _corner_basis(mesh, element):
    """A basis on ``mesh`` whose quadrature points are each element's four corners."""
    import numpy as np
    from skfem import CellBasis

    corners = np.array([[0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]])
    return CellBasis(mesh, element, quadrature=(corners, np.full(4, 0.25 / 6.0)))


def _components(edges: "np.ndarray", count: int) -> tuple[int, "np.ndarray"]:
    """The connected bodies of a set of mesh edges, by node: (count, each node's body)."""
    import numpy as np
    import scipy.sparse as sparse
    from scipy.sparse.csgraph import connected_components

    graph = sparse.coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(count, count))
    return connected_components(graph, directed=False)


def ac_solve(region: Region, mu_r: list[float], sigma: list[float], omega: float, *, J_s=None,
             fed: list[Fed] | None = None, grounds: list["np.ndarray"] | None = None,
             applied_B: "np.ndarray | None" = None, solver: str | None = None) -> ACSolve:
    """curl(nu curl A) + sigma (j omega A + grad phi) = J_s, div(sigma (j omega A + grad phi)) = 0 in the conductors.

    A on lowest-order Nédélec elements everywhere (tangential A held on the box:
    0, or ``applied_B``'s uniform field A0 = B0 x (x - c) / 2), phi on P2
    elements in the conductors only (sigma per domain, S/mm), so the current
    ``J = -sigma (j omega A + grad phi)`` is complete to first order in each
    element. A fed conductor's input face is one unknown voltage taking its
    current; ``grounds`` (P2 DOF) are held at 0 V; a conductor with neither
    floats (its voltage pinned at one node: it carries eddy currents only). The
    complex system is assembled from its real blocks and solved directly
    (superlu), or by multigrid GMRES on the iterative rung, falling back to the
    direct solve when that does not converge. At omega = 0 it is the
    magnetostatic solve (with a DC current in a fed conductor).
    """
    import numpy as np
    import scipy.sparse as sparse
    import scipy.sparse.linalg as spla
    from skfem import Basis, BilinearForm, ElementTetN0, ElementTetP2, LinearForm, asm
    from skfem.helpers import curl, dot

    fed = fed or []
    grounds = grounds or []
    mesh = region.space.mesh
    hcurl = region.space_hcurl
    if region._p2 is None:
        region._p2 = Basis(mesh, ElementTetP2(), quadrature=hcurl.quadrature)
    p2 = region._p2
    Q = hcurl.X.shape[1]
    domain = region.domain
    nu = np.repeat((1.0 / (MU0 * np.asarray(mu_r, dtype=float)))[domain][:, None], Q, axis=1)
    sig_e = np.asarray(sigma, dtype=float)[domain]
    sig = np.repeat(sig_e[:, None], Q, axis=1)

    @BilinearForm
    def stiff(u, v, w):
        return w["nu"] * dot(curl(u), curl(v))

    @BilinearForm
    def mass(u, v, w):
        return w["s"] * dot(u, v)

    @BilinearForm
    def coupling(u, v, w):                       # u: phi (P2), v: the Nédélec test function
        return w["s"] * dot(u.grad, v)

    @BilinearForm
    def conduction(u, v, w):
        return w["s"] * dot(u.grad, v.grad)

    @LinearForm
    def source(v, w):
        return dot(w["J"], v)

    K = asm(stiff, hcurl, nu=nu).tocsr()
    M = asm(mass, hcurl, s=np.ones_like(sig)).tocsr()
    Ms = asm(mass, hcurl, s=sig).tocsr()
    C = asm(coupling, p2, hcurl, s=sig).tocsr()          # (edges, P2)
    L = asm(conduction, p2, s=sig).tocsr()
    f = asm(source, hcurl, J=J_s) if J_s is not None else np.zeros(hcurl.N)
    delta = GAUGE * float(K.diagonal().mean()) / float(M.diagonal().mean())
    n_a, n_p = hcurl.N, p2.N

    # phi lives on the conductors' P2 DOF only; each fed input face is one unknown; each floating body is pinned.
    conducting = sig_e > 0
    live = np.unique(p2.element_dofs[:, conducting]) if conducting.any() else np.zeros(0, dtype=np.int64)
    rep = np.arange(n_p)
    for entry in fed:
        rep[entry.into] = entry.into[0]
    held_phi = np.unique(np.concatenate(grounds)) if grounds else np.zeros(0, dtype=np.int64)
    pinned: list[int] = []
    if len(live):
        corners = mesh.t[:, conducting]
        edges = np.concatenate([corners[[a, b]].T for a in range(4) for b in range(a + 1, 4)])
        count, label = _components(edges, mesh.p.shape[1])
        anchored = set(label[held_phi[held_phi < mesh.p.shape[1]]].tolist())
        for entry in fed:
            body = label[entry.into[entry.into < mesh.p.shape[1]][0]]
            if body not in anchored:
                raise ValueError("a conductor fed a current needs its return: hold a face of the same conductor at 0 V")
        for body in np.unique(label[np.unique(corners)]):
            if body not in anchored:
                pinned.append(int(np.flatnonzero(label == body)[0]))
    # The unknowns: free Nédélec DOF, then the reduced phi DOF.
    held_a = hcurl.get_dofs(mesh.boundary_facets()).all()
    a_values = np.zeros(n_a, dtype=complex)
    if applied_B is not None:
        centre = 0.5 * (np.asarray(region.box[0]) + np.asarray(region.box[1]))
        B0 = np.asarray(applied_B, dtype=float)
        # A0 = B0 x (x - c) / 2 is linear, so its edge DOF (the tangential integral along each edge, first node to
        # second) is its value at the edge's midpoint along the edge, exactly.
        start, end = mesh.p[:, mesh.edges[0]], mesh.p[:, mesh.edges[1]]
        along = 0.5 * np.cross(B0, 0.5 * (start + end).T - centre) * (end - start).T
        A0 = np.zeros(n_a)
        A0[hcurl.edge_dofs[0]] = along.sum(axis=1)
        a_values[held_a] = A0[held_a]
    free_a = np.setdiff1d(np.arange(n_a), held_a)
    phi_fixed = np.unique(np.concatenate([held_phi, np.asarray(pinned, dtype=np.int64)])) if len(held_phi) or pinned \
        else np.zeros(0, dtype=np.int64)
    phi_keep = np.setdiff1d(live, phi_fixed)
    reps, reduced_of = np.unique(rep[phi_keep], return_inverse=True)
    m = len(reps)
    P_phi = sparse.csr_matrix((np.ones(len(phi_keep)), (phi_keep, reduced_of)), shape=(n_p, m))
    jw = 1j * omega
    Aaa = (K + delta * M + jw * Ms).tocsr()
    top = sparse.hstack([Aaa[free_a][:, free_a], (C @ P_phi)[free_a]])
    bottom = sparse.hstack([jw * (P_phi.T @ C.T)[:, free_a], P_phi.T @ L @ P_phi])
    system = sparse.vstack([top, bottom]).tocsc()
    rhs_a = f[free_a] - (Aaa @ a_values)[free_a]
    rhs_p = -(jw * (P_phi.T @ (C.T @ a_values)))
    for entry in fed:
        rhs_p[reduced_of[np.searchsorted(phi_keep, entry.into[0])]] += entry.amps
    rhs = np.concatenate([rhs_a, rhs_p]).astype(complex)
    how = "superlu"
    x = None
    if solver in ("iterative", "matrix_free"):
        import pyamg

        try:
            residuals: list[float] = []
            ml = pyamg.smoothed_aggregation_solver(system.tocsr(), symmetry="nonsymmetric", max_coarse=500)
            x = ml.solve(rhs, tol=1e-10, accel="gmres", maxiter=400, residuals=residuals)
            how = f"amg+gmres ({len(residuals)} iterations)"
            if not residuals or residuals[-1] > 1e-6 * max(residuals[0], 1e-300):
                x = None
        except Exception:  # noqa: BLE001  (a hierarchy that cannot be built: solve directly)
            x = None
        if x is None:
            how = "superlu (after amg)"
    if x is None:
        x = spla.splu(system).solve(rhs)
    A = a_values.copy()
    A[free_a] = x[:len(free_a)]
    phi = np.zeros(n_p, dtype=complex)
    phi[phi_keep] = x[len(free_a):][reduced_of]
    # The fields: B = curl A (constant per element), J = -sigma (j omega A + grad phi) at the quadrature points.
    curl_q = curl(hcurl.interpolate(A.real)) + 1j * curl(hcurl.interpolate(A.imag))
    volume = hcurl.dx.sum(axis=1)
    B = np.ascontiguousarray((curl_q * hcurl.dx[None]).sum(axis=2).T / volume[:, None])
    nu_e = 1.0 / (MU0 * np.asarray(mu_r, dtype=float)[domain])
    energy = float(0.25 * (nu_e * (np.abs(B) ** 2).sum(axis=1) * volume).sum())

    def current(basis_a, basis_p):
        Aq = basis_a.interpolate(A.real).value + 1j * basis_a.interpolate(A.imag).value
        gq = basis_p.interpolate(phi.real).grad + 1j * basis_p.interpolate(phi.imag).grad
        return -sig_e[None, :, None] * (jw * Aq + gq)

    J = current(hcurl, p2)
    with np.errstate(divide="ignore", invalid="ignore"):
        loss = np.where(sig > 0, (np.abs(J) ** 2).sum(axis=0) / (2.0 * np.where(sig > 0, sig, 1.0)), 0.0)
    by_domain = np.bincount(domain, weights=(loss * hcurl.dx).sum(axis=1), minlength=len(mu_r))
    corner_J = current(_corner_basis(mesh, ElementTetN0()), _corner_basis(mesh, ElementTetP2()))
    vertex_J = np.sqrt((np.abs(corner_J) ** 2).sum(axis=0))
    fed_V = [complex(phi[entry.into[0]]) for entry in fed]
    return ACSolve(A, phi, B, J, loss, by_domain, energy, how, int(len(free_a) + m), vertex_J, fed_V, p2)


def face_dofs_p2(region: Region, rows: "np.ndarray") -> "np.ndarray":
    """The P2 DOF (corners and mid-edges) of the region's boundary triangles ``rows``, as :func:`ac_solve` numbers them."""
    from skfem import Basis, ElementTetP2

    if region._p2 is None:
        region._p2 = Basis(region.space.mesh, ElementTetP2(), quadrature=region.space_hcurl.quadrature)
    return region._p2.get_dofs(region.space.facets_of_rows(rows)).all()
