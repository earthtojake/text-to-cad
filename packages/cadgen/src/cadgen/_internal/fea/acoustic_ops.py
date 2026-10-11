"""Linear acoustics on the engine's meshes: the Helmholtz equation for sound in air or another fluid.

The sound pressure p (complex amplitude, time dependence e^{iωt}) obeys

    ∇²p + k² p = 0,   k = ω / c,

in the air, with what each boundary does to it in the weak form

    ∫ ∇p·∇q - k²(1 - iη) ∫ p q + ik Σ β ∫_Γ p q + ∫_Σ (ik + 1/r)(n·r̂) p q = iωρ ∫_S V q + iωρ Q q(x₀):

- a rigid wall: nothing (∂p/∂n = 0, natural);
- an absorbing face: a normal-incidence specific admittance β = ρc / Z (from an absorption
  coefficient α of a resistive face, Z = ρc (1 + √(1-α)) / (1 - √(1-α)));
- an open face (``p = 0``, the open end of a pipe): held at zero;
- the outer box of open air: a first-order absorbing (Sommerfeld) boundary with the spherical
  spreading term about the part's centre, ∂p/∂n = -(ik + 1/r)(n·r̂) p. It is exact for sound that
  spreads from the centre (a monopole) and an approximation for any other: the rest reflects a little;
- a vibrating face moving into the air at V (m/s, its normal velocity amplitude), and a point
  source of volume velocity Q (m³/s);
- the air's own loss: a loss factor η (k² becomes k²(1 - iη)).

The units inside are SI (m, Pa, kg/m³, m/s): the meshes are in mm, so each matrix is scaled once
as it is assembled. :class:`AirRegion` is the air the sound is solved in: the part itself (the
solid is the air volume, a duct or a room), the air closed inside the part (an OCP boolean of its
bounding box minus the part, keeping the solids that touch no side of the box) or the air around
it (a box around the part minus the part, each box side absorbing). Numeric imports live inside
the functions.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.femspace import FemSpace
    from cadgen._internal.fea.mesh import VolumeMesh

__all__ = [
    "AIR_DOMAINS", "AirRegion", "FLUIDS", "Fluid", "Operators", "absorption_admittance", "assemble", "build_air",
    "cavity_modes", "face_mass", "frequency_error", "from_part_surface", "level_dB", "part_region", "probe_matrix",
    "solve_frequency", "system_at", "to_part_surface", "wall_normals",
]

#: Fluids by name at 20 °C: density kg/m³, speed of sound m/s, and the reference pressure its levels are in (Pa).
FLUIDS = {"air": (1.204, 343.2, 20e-6), "water": (998.2, 1482.0, 1e-6)}
#: Where the air is: the part itself, closed inside the part, or around it out to an absorbing box.
AIR_DOMAINS = ("part", "inside", "outside")
#: The inside air's box stands off the part by this share of its diagonal (only the closed cavities are kept).
STANDOFF = 0.1
#: mm -> m: lengths, areas and volumes.
MM, MM2, MM3 = 1e-3, 1e-6, 1e-9


@dataclass(frozen=True)
class Fluid:
    name: str
    density_kg_m3: float
    speed_m_s: float
    #: The pressure 0 dB is: 20 µPa in air (and for a fluid given by its numbers), 1 µPa in water.
    reference_Pa: float = 20e-6

    def k(self, f_Hz: float) -> float:
        """The wavenumber at ``f_Hz``, 1/m."""
        return 2.0 * math.pi * f_Hz / self.speed_m_s

    def wavelength_mm(self, f_Hz: float) -> float:
        return 1000.0 * self.speed_m_s / f_Hz


def level_dB(amplitude_Pa, reference_Pa: float = 20e-6):
    """Sound pressure level of a pressure amplitude (its RMS is amplitude / √2), dB re ``reference_Pa``;
    floored at 0 dB, which a quiet or a silent point reads."""
    import numpy as np

    rms = np.asarray(amplitude_Pa, dtype=float) / math.sqrt(2.0)
    return np.maximum(20.0 * np.log10(np.maximum(rms, 1e-300) / reference_Pa), 0.0)


def absorption_admittance(alpha: float) -> float:
    """β = ρc / Z of a resistive face that absorbs ``alpha`` of the sound striking it head on (0 < α ≤ 1)."""
    r = math.sqrt(max(0.0, 1.0 - alpha))
    return (1.0 - r) / (1.0 + r)


# -- the air region ---------------------------------------------------------------------------------


@dataclass
class AirRegion:
    """The air the sound is solved in, and how its boundary rows map onto the part's faces."""

    kind: str                       # "part", "inside" or "outside"
    space: "FemSpace"
    volume: "VolumeMesh"
    #: Per boundary row, the part face's cadgen ordinal it lies on (0: not one of the part's faces).
    row_ordinal: "np.ndarray"
    #: Per boundary row, whether it is the outer box's (absorbing) side.
    row_far: "np.ndarray"
    #: The centre spreading is measured from (the part's bounding-box centre), mm.
    centre_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    #: The outer box (low, high) mm, for open air; ``None`` otherwise.
    box: "tuple[tuple[float, float, float], tuple[float, float, float]] | None" = None
    volume_mm3: float = 0.0
    seconds: float = 0.0
    #: Part face ordinals the air touches.
    wetted: set[int] = field(default_factory=set)

    def rows_on(self, ordinals) -> "np.ndarray":
        import numpy as np

        return np.isin(self.row_ordinal, list(ordinals))


def part_region(space: "FemSpace", volume: "VolumeMesh", centre_mm) -> AirRegion:
    """The part itself as the air: its own space, every boundary row on its own face."""
    import numpy as np

    ordinals = np.asarray(volume.boundary_ordinal, dtype=np.int64)
    return AirRegion("part", space, volume, ordinals, np.zeros(len(ordinals), bool), tuple(centre_mm),
                     wetted=set(int(o) for o in np.unique(ordinals) if o))


def _bounds(shape):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return [xmin, ymin, zmin], [xmax, ymax, zmax]


def _shapes_of(shape, kind):
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    found = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_SOLID if kind == "solid" else TopAbs_FACE, found)
    return found


def _properties(shape, volume: bool):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    (BRepGProp.VolumeProperties_s if volume else BRepGProp.SurfaceProperties_s)(shape, props)
    centre = props.CentreOfMass()
    return float(props.Mass()), (centre.X(), centre.Y(), centre.Z())


def _on_box(face, low, high, tol: float) -> bool:
    """Whether a face lies flat on a side of the box."""
    f_low, f_high = _bounds(face)
    for axis in range(3):
        if f_high[axis] - f_low[axis] <= tol and (abs(f_low[axis] - low[axis]) <= tol or abs(f_high[axis] - high[axis]) <= tol):
            return True
    return False


def build_air(shape, kind: str, refs: dict[int, str], *, pad_mm: float, wall_mm: float, far_mm: float | None = None) -> AirRegion:
    """The air inside (``kind="inside"``) or around (``"outside"``, out to a box ``pad_mm`` past the part
    on every side) an OCP part, meshed by netgen with quadratic tetrahedra: ``wall_mm`` at the part's
    faces, up to ``far_mm`` away from them. ``refs`` names the part's faces by cadgen ordinal. ValueError
    for a part with no air closed inside it."""
    import numpy as np
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt

    from cadgen._internal.entity_ordinals import entity_map
    from cadgen._internal.fea import fluid_domain
    from cadgen._internal.fea.femspace import FemSpace

    started = time.perf_counter()
    low, high = _bounds(shape)
    diagonal = math.dist(low, high)
    tol = 1e-6 * max(diagonal, 1.0)
    reach = STANDOFF * diagonal if kind == "inside" else pad_mm
    box_low = [c - reach for c in low]
    box_high = [c + reach for c in high]
    cut = BRepAlgoAPI_Cut(BRepPrimAPI_MakeBox(gp_Pnt(*box_low), gp_Pnt(*box_high)).Shape(), shape)
    if not cut.IsDone():
        raise RuntimeError("the boolean that makes the air from the part failed")
    solids_map = _shapes_of(cut.Shape(), "solid")
    solids = [solids_map.FindKey(i) for i in range(1, solids_map.Extent() + 1)]

    def touches_box(solid) -> bool:
        faces = _shapes_of(solid, "face")
        return any(_on_box(faces.FindKey(i), box_low, box_high, tol) for i in range(1, faces.Extent() + 1))

    keep = [s for s in solids if touches_box(s) == (kind == "outside")]
    if not keep:
        if kind == "inside":
            raise ValueError("domain: the part closes no air inside it (no space walled in on every side); use "
                             "\"domain\": \"part\" when the part's own solid is the air, or \"outside\" for the air around it")
        raise RuntimeError("the boolean that makes the air around the part left no air")
    if len(keep) == 1:
        air = keep[0]
    else:
        from OCP.BRep import BRep_Builder
        from OCP.TopoDS import TopoDS_Compound

        air = TopoDS_Compound()
        builder = BRep_Builder()
        builder.MakeCompound(air)
        for solid in keep:
            builder.Add(air, solid)

    # Each face of the air: an image of one of the part's faces (its ordinal), or a box side.
    part_faces = entity_map(shape, "face")
    image_of = []
    for ordinal in range(1, part_faces.Extent() + 1):
        face = part_faces.FindKey(ordinal)
        modified = list(cut.Modified(face))
        if modified:
            image_of += [(image, ordinal) for image in modified]
        elif not cut.IsDeleted(face):
            image_of.append((face, ordinal))
    air_faces = _shapes_of(air, "face")
    wall_of: dict[int, int] = {}
    for image, ordinal in image_of:
        index = air_faces.FindIndex(image)
        if index > 0:
            wall_of[index] = ordinal
    faces = []
    for index in range(1, air_faces.Extent() + 1):
        face = air_faces.FindKey(index)
        area, centre = _properties(face, False)
        if index in wall_of:
            faces.append(fluid_domain.FluidFace(index, "wall", area, 0.0, centre, wall_of[index], refs.get(wall_of[index])))
        elif kind == "outside" and _on_box(face, box_low, box_high, tol):
            faces.append(fluid_domain.FluidFace(index, "side", area, 0.0, centre))
        else:
            faces.append(fluid_domain.FluidFace(index, "wall", area, 0.0, centre))
    volume_mm3 = sum(_properties(solid, True)[0] for solid in keep)
    domain = fluid_domain.FluidDomain(
        shape=air, kind="external" if kind == "outside" else "internal", faces=faces, volume_mm3=volume_mm3,
        part_box=(tuple(low), tuple(high)), box=(tuple(box_low), tuple(box_high)), length_mm=max(h - l for l, h in zip(low, high)),
    )
    mesh = fluid_domain.mesh_fluid(domain, wall_mm, far_mm if kind == "outside" else None)
    space = FemSpace.build(mesh, 2)
    face_of = {face.index: face for face in faces}
    rows = np.asarray(mesh.boundary_ordinal, dtype=np.int64)
    row_ordinal = np.array([face_of[int(o)].ordinal if int(o) in face_of else 0 for o in rows], dtype=np.int64)
    row_far = np.array([int(o) in face_of and face_of[int(o)].kind == "side" for o in rows], dtype=bool)
    centre = tuple(0.5 * (a + b) for a, b in zip(low, high))
    return AirRegion(kind, space, mesh, row_ordinal, row_far, centre,
                     (tuple(box_low), tuple(box_high)) if kind == "outside" else None, volume_mm3,
                     time.perf_counter() - started, set(int(o) for o in np.unique(row_ordinal) if o))


# -- assembly ---------------------------------------------------------------------------------------


@dataclass
class Operators:
    """The air's matrices, SI: K = ∫∇p·∇q (m), M = ∫ p q (m³), and each boundary term (m², m)."""

    K: Any
    M: Any
    #: Absorbing faces: (admittance β, ∫_Γ p q in m²) per group.
    absorbers: list = field(default_factory=list)
    #: The open-air box: ∫ (n·r̂) p q (m²) and ∫ (n·r̂)/r p q (m).
    far: Any = None
    far_spread: Any = None
    #: Scalar DOF held at p = 0 (open faces).
    open_dofs: "np.ndarray | None" = None
    #: Right-hand side per unit iωρ: ∫_S V q (m³/s) from the vibrating faces and Q q(x₀) from point sources.
    source: "np.ndarray | None" = None

    @property
    def size(self) -> int:
        return int(self.K.shape[0])


def _facet_basis(space, rows):
    return space.scalar.boundary(space.facets_of_rows(rows))


def face_mass(space, rows):
    """∫_Γ p q over boundary rows ``rows`` (a mask), m²."""
    from skfem import BilinearForm, asm

    @BilinearForm
    def form(u, v, w):
        return u * v

    return asm(form, _facet_basis(space, rows)).tocsr() * MM2


def assemble(region: AirRegion, *, absorbers=(), open_rows=None, sources=(), points=(), far: bool = False) -> Operators:
    """The air's operators: ``absorbers`` (rows mask, β), ``open_rows`` (a mask held at p = 0), ``sources``
    (rows mask, normal velocity in m/s, or a per-scalar-DOF array of it), ``points`` ((x, y, z) mm,
    Q m³/s), and, with ``far``, the absorbing outer box."""
    import numpy as np
    from skfem import BilinearForm, LinearForm, asm

    space = region.space

    @BilinearForm
    def laplace(u, v, w):
        return u.grad[0] * v.grad[0] + u.grad[1] * v.grad[1] + u.grad[2] * v.grad[2]

    @BilinearForm
    def mass(u, v, w):
        return u * v

    ops = Operators(K=asm(laplace, space.scalar).tocsr() * MM, M=asm(mass, space.scalar).tocsr() * MM3)
    for rows, beta in absorbers:
        if rows.any():
            ops.absorbers.append((float(beta), face_mass(space, rows)))
    if far and region.row_far.any():
        centre = np.asarray(region.centre_mm, dtype=float)

        def radial(w):
            r = np.stack([w.x[i] - centre[i] for i in range(3)])
            length = np.sqrt((r ** 2).sum(axis=0))
            cos = (r * w.n).sum(axis=0) / np.maximum(length, 1e-12)
            return cos, length * MM

        @BilinearForm
        def outgoing(u, v, w):
            return radial(w)[0] * u * v

        @BilinearForm
        def spreading(u, v, w):
            cos, r = radial(w)
            return cos / r * u * v

        basis = _facet_basis(space, region.row_far)
        ops.far = asm(outgoing, basis).tocsr() * MM2
        ops.far_spread = asm(spreading, basis).tocsr() * MM2
    if open_rows is not None and open_rows.any():
        ops.open_dofs = np.unique(space.boundary_quadratic[open_rows].ravel())
    f = np.zeros(space.scalar_count, dtype=complex)
    for rows, velocity in sources:
        if not rows.any():
            continue
        if np.ndim(velocity) == 0:
            @LinearForm
            def unit(v, w):
                return v

            f += float(velocity) * asm(unit, _facet_basis(space, rows)) * MM2
        else:
            f += face_mass(space, rows) @ np.asarray(velocity)
    if points:
        P, inside = probe_matrix(space, np.array([p for p, _ in points], dtype=float))
        if not inside.all():
            raise ValueError(f"sources: the point source at {list(points[int(np.flatnonzero(~inside)[0])][0])} mm is not in the air")
        f += P.T @ np.array([q for _, q in points], dtype=float)
    ops.source = f
    return ops


def probe_matrix(space, points: "np.ndarray"):
    """(P × scalar DOF sparse matrix, inside mask): the quadratic field's value at each point, through the
    element holding it (found on the straight-sided corners). A point outside the mesh has an empty row."""
    import numpy as np
    import scipy.sparse as sparse
    from skfem import MeshTet

    corners = space.mesh.t[:4]
    linear = MeshTet(np.ascontiguousarray(space.mesh.p[:, : space.vertices]), np.ascontiguousarray(corners))
    finder = linear.element_finder()
    rows, cols, vals = [], [], []
    inside = np.zeros(len(points), bool)
    element_dofs = space.scalar.element_dofs
    for i, p in enumerate(points):
        try:
            e = int(finder(np.array([p[0]]), np.array([p[1]]), np.array([p[2]]))[0])
        except ValueError:
            continue
        X = linear.p[:, corners[:, e]]
        T = np.column_stack([X[:, 1] - X[:, 0], X[:, 2] - X[:, 0], X[:, 3] - X[:, 0]])
        b = np.linalg.solve(T, np.asarray(p) - X[:, 0])
        lam = np.array([1.0 - b.sum(), *b])
        if space.order == 2:
            pairs = ((0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3))
            shape = [lam[j] * (2 * lam[j] - 1) for j in range(4)] + [4 * lam[a] * lam[c] for a, c in pairs]
        else:
            shape = list(lam)
        rows += [i] * len(shape)
        cols += list(element_dofs[: len(shape), e])
        vals += shape
        inside[i] = True
    return sparse.csr_matrix((vals, (rows, cols)), shape=(len(points), space.scalar_count)), inside


# -- solving ----------------------------------------------------------------------------------------


def cavity_modes(ops: Operators, count: int, *, iterative: bool = False):
    """The ``count`` lowest (k², pressure shape) of K p = k² M p, open faces held at zero; the uniform
    mode of a closed cavity (k = 0) included. Returns (k² ascending, vectors over every DOF, how)."""
    import numpy as np

    from cadgen._internal.fea import eigen

    n = ops.size
    free = np.setdiff1d(np.arange(n), ops.open_dofs if ops.open_dofs is not None else [])
    K, M = ops.K[free][:, free].tocsr(), ops.M[free][:, free].tocsr()
    k = min(count, len(free) - 2)
    scale = float(K.diagonal().sum() / M.diagonal().sum())
    shift = 1e-6 * scale
    if iterative:
        A = (K + shift * M).tocsr()
        found = eigen.solve_generalized(A, M, k, precond=eigen.amg_preconditioner(A), which="SA", method="lobpcg")
        values = found.values - shift
    else:
        found = eigen.shift_invert(K, M, k, -shift)
        values = found.values
    order = np.argsort(values)
    vectors = np.zeros((n, len(order)))
    vectors[free] = found.vectors[:, order]
    return np.maximum(values[order], 0.0), vectors, found.how


def system_at(ops: Operators, k: float, loss: float):
    """A(k) = K - k²(1 - iη) M + ik Σ β B + ik B_far + B_spread, complex CSC."""
    A = (ops.K - (k * k) * (1.0 - 1j * loss) * ops.M).astype(complex)
    for beta, B in ops.absorbers:
        A = A + (1j * k * beta) * B
    if ops.far is not None:
        A = A + (1j * k) * ops.far + ops.far_spread
    return A.tocsc()


def solve_frequency(ops: Operators, fluid: Fluid, f_Hz: float, loss: float, *, rhs=None, iterative: bool = False,
                    warnings: list[str] | None = None):
    """The complex pressure amplitude (Pa) at every scalar DOF at ``f_Hz``: A(k) p = iωρ f, open DOF at zero."""
    import numpy as np
    import scipy.sparse.linalg as spla

    k = fluid.k(f_Hz)
    omega = 2.0 * math.pi * f_Hz
    A = system_at(ops, k, loss)
    b = 1j * omega * fluid.density_kg_m3 * (ops.source if rhs is None else rhs)
    n = ops.size
    free = np.setdiff1d(np.arange(n), ops.open_dofs if ops.open_dofs is not None else [])
    Aff = A[free][:, free].tocsc()
    p = np.zeros(n, dtype=complex)
    if not iterative:
        p[free] = spla.splu(Aff).solve(b[free])
        return p
    # GMRES, preconditioned by multigrid on the positive-shifted Laplacian K + k² M (real, SPD).
    import pyamg

    P = (ops.K + (k * k) * ops.M)[free][:, free].tocsr()
    ml = pyamg.smoothed_aggregation_solver(P, symmetry="symmetric", max_coarse=500)
    real = ml.aspreconditioner(cycle="V")
    M = spla.LinearOperator(Aff.shape, matvec=lambda x: real @ x.real + 1j * (real @ x.imag), dtype=complex)
    x, info = spla.gmres(Aff, b[free], M=M, rtol=1e-8, restart=80, maxiter=40)
    if info != 0:
        if warnings is not None:
            warnings.append(f"the iterative solve at {f_Hz:.4g} Hz did not converge; solved it directly instead")
        x = spla.splu(Aff).solve(b[free])
    p[free] = x
    return p


# -- the mesh's own accuracy ------------------------------------------------------------------------


def frequency_error(elements_per_wavelength: float, order: int = 2) -> float:
    """The relative error in a wave's frequency on elements of this size (quadratic by default), measured
    on a uniform 1D mesh of the same elements: what the mesh alone costs at that resolution (positive:
    the mesh reads frequencies high)."""
    import numpy as np
    import scipy.linalg

    per = max(float(elements_per_wavelength), 1.0)
    elements = 48
    mode = max(1, round(2 * elements / per))
    h = 1.0 / elements
    if order == 2:
        Ke = np.array([[7, 1, -8], [1, 7, -8], [-8, -8, 16]]) / (3 * h)
        Me = np.array([[4, -1, 2], [-1, 4, 2], [2, 2, 16]]) * h / 30
        n = 2 * elements + 1
        local = [(2 * e, 2 * e + 2, 2 * e + 1) for e in range(elements)]
    else:
        Ke = np.array([[1, -1], [-1, 1]]) / h
        Me = np.array([[2, 1], [1, 2]]) * h / 6
        n = elements + 1
        local = [(e, e + 1) for e in range(elements)]
    K, M = np.zeros((n, n)), np.zeros((n, n))
    for dofs in local:
        K[np.ix_(dofs, dofs)] += Ke
        M[np.ix_(dofs, dofs)] += Me
    values = np.sort(scipy.linalg.eigh(K, M, eigvals_only=True))
    if mode >= len(values):
        return 1.0
    exact = mode * math.pi
    return float(math.sqrt(max(values[mode], 0.0)) / exact - 1.0)


# -- onto the part ----------------------------------------------------------------------------------


def to_part_surface(region: AirRegion, part_space, part_volume, values: "np.ndarray") -> tuple["np.ndarray", "np.ndarray"]:
    """Air nodal ``values`` carried onto the part's surface nodes, face by face (nearest air node on the
    same face); (values on the part's scalar DOF, the part nodes the air wets). A dry face reads 0."""
    import numpy as np
    from scipy.spatial import cKDTree

    out = np.zeros(part_space.scalar_count, dtype=np.asarray(values).dtype)
    air_boundary = region.space.boundary_quadratic
    locations = region.space.dof_locations
    wet = []
    for ordinal in sorted(region.wetted):
        source = np.unique(air_boundary[region.row_ordinal == ordinal])
        target = np.unique(part_space.boundary_quadratic[part_volume.boundary_ordinal == ordinal])
        if len(source) == 0 or len(target) == 0:
            continue
        _, nearest = cKDTree(locations[source]).query(part_space.dof_locations[target])
        out[target] = np.asarray(values)[source[nearest]]
        wet.append(target)
    return out, (np.unique(np.concatenate(wet)) if wet else np.zeros(0, dtype=np.int64))


def from_part_surface(region: AirRegion, part_space, part_volume, vectors: "np.ndarray") -> "np.ndarray":
    """A vector field on the part's nodes (scalar_count, 3) carried onto the air's wall nodes, face by face."""
    import numpy as np
    from scipy.spatial import cKDTree

    out = np.zeros((region.space.scalar_count, 3), dtype=np.asarray(vectors).dtype)
    air_boundary = region.space.boundary_quadratic
    for ordinal in sorted(region.wetted):
        target = np.unique(air_boundary[region.row_ordinal == ordinal])
        source = np.unique(part_space.boundary_quadratic[part_volume.boundary_ordinal == ordinal])
        if len(source) == 0 or len(target) == 0:
            continue
        _, nearest = cKDTree(part_space.dof_locations[source]).query(region.space.dof_locations[target])
        out[target] = np.asarray(vectors)[source[nearest]]
    return out


def wall_normals(region: AirRegion, rows: "np.ndarray") -> "np.ndarray":
    """(scalar_count, 3): each wall node's unit normal pointing out of the air (into the part), area-averaged."""
    import numpy as np

    space = region.space
    triangles = space.boundary_quadratic[rows]
    corners = space.dof_locations[triangles[:, :3]]
    cross = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    element = space.mesh.f2t[0, space.facets_of_rows(rows)]
    inside = space.mesh.p[:, space.mesh.t[:, element]].mean(axis=1).T
    flip = np.einsum("ij,ij->i", cross, inside - corners[:, 0]) > 0
    cross[flip] *= -1.0
    normal = np.zeros((space.scalar_count, 3))
    np.add.at(normal, triangles.ravel(), np.repeat(cross, triangles.shape[1], axis=0))
    length = np.linalg.norm(normal, axis=1)
    return normal / np.where(length > 0, length, 1.0)[:, None]
