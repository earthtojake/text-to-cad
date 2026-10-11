"""The operators every analysis assembles on a :class:`~cadgen._internal.fea.femspace.FemSpace`.

Structural: stiffness (E and nu per domain), mass (density per domain), body
force, the load of an initial (thermal) strain, stress recovery and the
geometric stiffness of a prestress. Thermal: conduction, convection and heat
capacity. Solving: :func:`solve_spd`, a symmetric positive definite system on
its free DOF (direct when small, AMG + CG otherwise), and
:class:`ElementChunkOperator`, the matrix-free stiffness product, element chunk
by element chunk, for when the assembled matrix does not fit.

Materials come as one :class:`~cadgen._internal.fea.materials.Material` or one
per domain (``space.domain`` indexes them). A material with an ``orthotropic``
block, or a laminate's plies (:class:`~cadgen._internal.fea.laminate.LayeredMaterial`,
a stiffness per ply chosen at each quadrature point by its height), takes the
anisotropic path: a 6 x 6 elasticity matrix in global axes (Voigt order 11, 22,
33, 23, 13, 12, engineering shear) per part or ply. Isotropic materials keep
the Lamé path they always took, so their numbers are unchanged to the bit. Units are the engine's: mm, N, MPa,
tonne/mm^3, s; heat in mW (``W x 1000``), conductivity in mW/(mm K) (numerically
W/(m K)). Numeric imports live inside the functions.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.femspace import FemSpace
    from cadgen._internal.fea.materials import Material

__all__ = [
    "AMG_ATTEMPTS", "CHUNK_ELEMENTS", "DIRECT_SOLVE_BELOW", "G0_MM_S2", "ElementChunkOperator", "anisotropic", "body_force",
    "capacity", "conduction", "convection", "domain_values", "elasticity_matrix", "geometric_stiffness",
    "initial_strain_load", "isotropic_matrix", "lame", "mass", "orthotropic_matrix", "project", "rigid_body_modes",
    "rotate_voigt", "solve_spd", "stiffness", "stress", "von_mises",
]

#: Standard gravity, mm/s^2: a study's g in the engine's units.
G0_MM_S2 = 9806.65
#: Multigrid attempts (one random seed each) before the direct solver takes over.
AMG_ATTEMPTS = 3
#: Below this many free DOF the direct solver wins on setup cost.
DIRECT_SOLVE_BELOW = 20_000
#: Elements per chunk of a matrix-free product or a chunked recovery.
CHUNK_ELEMENTS = 20_000


def _materials(materials: "Material | Sequence[Material]") -> list:
    return list(materials) if isinstance(materials, (list, tuple)) else [materials]


def domain_values(space: "FemSpace", values: Sequence[float], basis=None):
    """One value per domain as an (elements, quadrature) array, or the bare number for a single part."""
    import numpy as np

    if space.domain is None or len(values) == 1:
        return float(values[0])
    basis = basis or space.basis
    quadrature = basis.X.shape[1]
    return np.repeat(np.asarray(values, dtype=float)[space.domain][:, None], quadrature, axis=1)


def lame(space: "FemSpace", materials: "Material | Sequence[Material]"):
    """Lamé's lambda and mu: numbers for one part, (elements, quadrature) arrays for an assembly."""
    from skfem.models.elasticity import lame_parameters

    per_part = [lame_parameters(m.E, m.nu) for m in _materials(materials)]
    if space.domain is None:
        return per_part[0]
    return domain_values(space, [p[0] for p in per_part]), domain_values(space, [p[1] for p in per_part])


# -- anisotropic elasticity (orthotropic materials and laminate plies) --------------------------------

#: Voigt's order of the symmetric tensor's components: 11, 22, 33, 23, 13, 12.
VOIGT = ((0, 0), (1, 1), (2, 2), (1, 2), (0, 2), (0, 1))


def anisotropic(materials: "Material | Sequence[Material]") -> bool:
    """Whether any material needs the anisotropic path (an ``orthotropic`` block, or a laminate's plies)."""
    return any(getattr(m, "orthotropic", None) or getattr(m, "layers", None) is not None for m in _materials(materials))


def isotropic_matrix(E: float, nu: float) -> "np.ndarray":
    """The 6 x 6 elasticity matrix of an isotropic material (Voigt, engineering shear)."""
    import numpy as np

    lam, mu = E * nu / ((1.0 + nu) * (1.0 - 2.0 * nu)), E / (2.0 * (1.0 + nu))
    C = np.zeros((6, 6))
    C[:3, :3] = lam
    C[[0, 1, 2], [0, 1, 2]] = lam + 2.0 * mu
    C[[3, 4, 5], [3, 4, 5]] = mu
    return C


def _tensor(C: "np.ndarray") -> "np.ndarray":
    import numpy as np

    T = np.zeros((3, 3, 3, 3))
    for I, (i, j) in enumerate(VOIGT):
        for J, (k, l) in enumerate(VOIGT):
            for a, b in ((i, j), (j, i)):
                for c, d in ((k, l), (l, k)):
                    T[a, b, c, d] = C[I, J]
    return T


def rotate_voigt(C: "np.ndarray", R: "np.ndarray") -> "np.ndarray":
    """A 6 x 6 elasticity matrix given in a material frame whose axes are the rows of ``R`` (global
    coordinates), in global axes: C'_ijkl = R_ai R_bj R_ck R_dl C_abcd."""
    import numpy as np

    T = np.einsum("ai,bj,ck,dl,abcd->ijkl", R, R, R, R, _tensor(C))
    return np.array([[T[i, j, k, l] for (k, l) in VOIGT] for (i, j) in VOIGT])


def orthotropic_compliance(block: dict) -> "np.ndarray":
    """The 6 x 6 compliance in the material's own axes from E1..E3, nu12..nu23 and G12..G23 (nu_ji = nu_ij Ej / Ei)."""
    import numpy as np

    E1, E2, E3 = block["E1_MPa"], block["E2_MPa"], block["E3_MPa"]
    n12, n13, n23 = block["nu12"], block["nu13"], block["nu23"]
    S = np.zeros((6, 6))
    S[0, 0], S[1, 1], S[2, 2] = 1.0 / E1, 1.0 / E2, 1.0 / E3
    S[0, 1] = S[1, 0] = -n12 / E1
    S[0, 2] = S[2, 0] = -n13 / E1
    S[1, 2] = S[2, 1] = -n23 / E2
    S[3, 3], S[4, 4], S[5, 5] = 1.0 / block["G23_MPa"], 1.0 / block["G13_MPa"], 1.0 / block["G12_MPa"]
    return S


def orthotropic_matrix(block: dict) -> "np.ndarray":
    """An ``orthotropic`` block's 6 x 6 elasticity matrix in global axes (its ``axes`` give directions 1 and 2)."""
    import numpy as np

    C = np.linalg.inv(orthotropic_compliance(block))
    C = 0.5 * (C + C.T)
    a1, a2 = (np.asarray(a, dtype=float) for a in block.get("axes", ([1, 0, 0], [0, 1, 0])))
    R = np.array([a1, a2, np.cross(a1, a2)])
    if np.allclose(R, np.eye(3), rtol=0.0, atol=1e-15):
        return C
    return rotate_voigt(C, R)


def elasticity_matrix(material: "Material") -> "np.ndarray":
    """A material's 6 x 6 elasticity matrix in global axes: its orthotropic block's, else isotropic from E and nu."""
    block = getattr(material, "orthotropic", None)
    if block:
        return orthotropic_matrix(block)
    return isotropic_matrix(material.E, material.nu)


def voigt(tensor: "np.ndarray") -> "np.ndarray":
    """A symmetric (3, 3, ...) strain as Voigt's 6-vector with engineering shears (2 e23, 2 e13, 2 e12)."""
    import numpy as np

    return np.stack([tensor[0, 0], tensor[1, 1], tensor[2, 2], 2.0 * tensor[1, 2], 2.0 * tensor[0, 2], 2.0 * tensor[0, 1]])


def _unvoigt(vector: "np.ndarray") -> "np.ndarray":
    """A Voigt 6-vector stress as the (3, 3, ...) tensor."""
    import numpy as np

    out = np.zeros((3, 3, *vector.shape[1:]))
    for I, (i, j) in enumerate(VOIGT):
        out[i, j] = vector[I]
        out[j, i] = vector[I]
    return out


def voigt_parts(space: "FemSpace", materials: "Material | Sequence[Material]", basis=None, rows=None) -> list:
    """The anisotropic stiffness as ``[(C 6x6, weight)]``: each part's (or ply's) matrix with where it acts, an
    (elements, quadrature) 0/1 array at ``basis``'s points (``None``: everywhere). ``rows`` limits the elements
    (a chunk's basis is built on those alone)."""
    import numpy as np

    basis = basis or space.basis
    parts = _materials(materials)
    shape = basis.dx.shape
    out = []
    points = None
    for index, material in enumerate(parts):
        weight = None
        if space.domain is not None and len(parts) > 1:
            domain = np.asarray(space.domain) if rows is None else np.asarray(space.domain)[rows]
            weight = np.repeat((domain == index).astype(float)[:, None], shape[1], axis=1)
        layers = getattr(material, "layers", None)
        if layers is None:
            out.append((elasticity_matrix(material), weight))
            continue
        if points is None:
            points = np.asarray(basis.global_coordinates().value)
        for C, inside in layers.parts(points):
            mask = inside.astype(float)
            out.append((C, mask if weight is None else mask * weight))
    return out


def _anisotropic_stiffness(space: "FemSpace", materials):
    from skfem import BilinearForm, asm
    from skfem.helpers import sym_grad

    parts = voigt_parts(space, materials)
    weights = {f"w{k}": weight for k, (_, weight) in enumerate(parts) if weight is not None}

    @BilinearForm
    def form(u, v, w):
        eu, ev = voigt(sym_grad(u)), voigt(sym_grad(v))
        total = 0.0
        for k, (C, weight) in enumerate(parts):
            energy = sum(ev[i] * sum(C[i, j] * eu[j] for j in range(6) if C[i, j] != 0.0) for i in range(6))
            total = total + (energy if weight is None else w[f"w{k}"] * energy)
        return total

    return asm(form, space.basis, **weights)


def _anisotropic_stress(space: "FemSpace", materials, strain: "np.ndarray") -> "np.ndarray":
    """σ = C ε at the quadrature points, (3, 3, elements, quadrature), from a (3, 3, ...) strain."""
    import numpy as np

    e = voigt(strain)
    s = np.zeros_like(e)
    for C, weight in voigt_parts(space, materials):
        part = np.einsum("ij,j...->i...", C, e)
        s += part if weight is None else part * weight
    return _unvoigt(s)


def stiffness(space: "FemSpace", materials: "Material | Sequence[Material]"):
    """K = ∫ C:ε(u):ε(v), with E and nu per domain (or each part's anisotropic C)."""
    from skfem import BilinearForm, asm
    from skfem.helpers import ddot, sym_grad, trace
    from skfem.models.elasticity import lame_parameters, linear_elasticity

    if anisotropic(materials):
        return _anisotropic_stiffness(space, materials)
    if space.domain is None:
        lam, mu = lame_parameters(_materials(materials)[0].E, _materials(materials)[0].nu)
        return asm(linear_elasticity(lam, mu), space.basis)
    lam, mu = lame(space, materials)

    @BilinearForm
    def form(u, v, w):
        return 2.0 * w["mu"] * ddot(sym_grad(u), sym_grad(v)) + w["lam"] * trace(sym_grad(u)) * trace(sym_grad(v))

    return asm(form, space.basis, lam=lam, mu=mu)


def _density(space: "FemSpace", materials, basis=None):
    return domain_values(space, [m.density for m in _materials(materials)], basis)


def mass(space: "FemSpace", materials: "Material | Sequence[Material]", *, lumped: bool = False):
    """M = ∫ ρ u·v, with ρ per domain; ``lumped`` gives its row sums as a diagonal matrix."""
    import numpy as np
    import scipy.sparse as sparse
    from skfem import BilinearForm, asm

    @BilinearForm
    def form(u, v, w):
        return w["rho"] * (u[0] * v[0] + u[1] * v[1] + u[2] * v[2])

    rho = _density(space, materials)
    M = asm(form, space.basis, rho=rho if not isinstance(rho, float) else np.full(space.basis.dx.shape, rho))
    if lumped:
        return sparse.diags(np.asarray(M.sum(axis=1)).ravel()).tocsr()
    return M


def body_force(space: "FemSpace", materials: "Material | Sequence[Material]", acceleration) -> "np.ndarray":
    """f = ∫ ρ b·v for a uniform body acceleration ``b`` (mm/s^2): gravity is b = g, an accelerated frame b = -a."""
    import numpy as np
    from skfem import LinearForm, asm

    b = np.asarray(acceleration, dtype=float)

    @LinearForm
    def form(v, w):
        return w["rho"] * (b[0] * v[0] + b[1] * v[1] + b[2] * v[2])

    rho = _density(space, materials)
    return asm(form, space.basis, rho=rho if not isinstance(rho, float) else np.full(space.basis.dx.shape, rho))


def _initial_strain_tensor(strain) -> "np.ndarray":
    """A (3, 3, elements, quadrature) strain from an isotropic (elements, quadrature) one or a full tensor."""
    import numpy as np

    strain = np.asarray(strain, dtype=float)
    if strain.ndim == 4:
        return strain
    tensor = np.zeros((3, 3, *strain.shape))
    for i in range(3):
        tensor[i, i] = strain
    return tensor


def initial_strain_load(space: "FemSpace", materials: "Material | Sequence[Material]", strain) -> "np.ndarray":
    """f = ∫ C:ε0 : ε(v): the load that a stress-free strain ε0 (a thermal α ΔT) puts on the part.

    ``strain`` is isotropic, (elements, quadrature) at the vector basis's points, or a full (3, 3, elements, quadrature) tensor.
    """
    import numpy as np
    from skfem import LinearForm, asm
    from skfem.helpers import ddot, sym_grad

    if anisotropic(materials):
        sigma0 = _anisotropic_stress(space, materials, _initial_strain_tensor(strain))

        @LinearForm
        def aniso(v, w):
            return ddot(w["sigma0"], sym_grad(v))

        return asm(aniso, space.basis, sigma0=np.asarray(sigma0))
    lam, mu = lame(space, materials)
    eps0 = _initial_strain_tensor(strain)
    trace = eps0[0, 0] + eps0[1, 1] + eps0[2, 2]
    sigma0 = 2.0 * mu * eps0
    for i in range(3):
        sigma0[i, i] = sigma0[i, i] + lam * trace

    @LinearForm
    def form(v, w):
        return ddot(w["sigma0"], sym_grad(v))

    return asm(form, space.basis, sigma0=np.asarray(sigma0))


def stress(space: "FemSpace", materials: "Material | Sequence[Material]", u: "np.ndarray", initial_strain=None):
    """σ = C:(ε(u) - ε0) at the quadrature points, (3, 3, elements, quadrature) MPa."""
    import numpy as np

    if anisotropic(materials):
        grad = space.basis.interpolate(u).grad
        strain = 0.5 * (grad + np.transpose(grad, (1, 0, 2, 3)))
        if initial_strain is not None:
            strain = strain - _initial_strain_tensor(initial_strain)
        return _anisotropic_stress(space, materials, strain)
    lam, mu = lame(space, materials)
    grad = space.basis.interpolate(u).grad                          # (3, 3, elements, quadrature)
    strain = 0.5 * (grad + np.transpose(grad, (1, 0, 2, 3)))
    if initial_strain is not None:
        strain = strain - _initial_strain_tensor(initial_strain)
    trace = strain[0, 0] + strain[1, 1] + strain[2, 2]
    s = 2.0 * mu * strain
    for i in range(3):
        s[i, i] += lam * trace
    return s


def von_mises(s: "np.ndarray") -> "np.ndarray":
    """Von Mises of a (3, 3, ...) stress, element- and point-wise."""
    import numpy as np

    return np.sqrt(
        0.5 * ((s[0, 0] - s[1, 1]) ** 2 + (s[1, 1] - s[2, 2]) ** 2 + (s[2, 2] - s[0, 0]) ** 2)
        + 3.0 * (s[0, 1] ** 2 + s[1, 2] ** 2 + s[0, 2] ** 2)
    )


def project(space: "FemSpace", values: "np.ndarray") -> "np.ndarray":
    """The L2 projection of a quadrature-point scalar onto the scalar basis."""
    return space.scalar.project(values)


def geometric_stiffness(space: "FemSpace", sigma: "np.ndarray"):
    """Kg = ∫ σ0_ij ∂u_k/∂x_i ∂v_k/∂x_j for a prestress ``sigma`` (3, 3, elements, quadrature): symmetric."""
    import numpy as np
    from skfem import BilinearForm, asm

    @BilinearForm
    def form(u, v, w):
        return np.einsum("ki...,ij...,kj...->...", u.grad, w["sigma"], v.grad)

    return asm(form, space.basis, sigma=np.asarray(sigma))


def conduction(space: "FemSpace", materials: "Material | Sequence[Material]"):
    """K_T = ∫ k ∇T·∇v on the scalar basis, k per domain (W/(m K) is mW/(mm K))."""
    import numpy as np
    from skfem import BilinearForm, asm

    k = domain_values(space, [m.conductivity for m in _materials(materials)], space.scalar)

    @BilinearForm
    def form(u, v, w):
        return w["k"] * (u.grad[0] * v.grad[0] + u.grad[1] * v.grad[1] + u.grad[2] * v.grad[2])

    return asm(form, space.scalar, k=k if not isinstance(k, float) else np.full(space.scalar.dx.shape, k))


def convection(space: "FemSpace", facets: "np.ndarray", h: float, ambient: float):
    """A film on ``facets``: the matrix ∫_Γ h T v and the load ∫_Γ h T∞ v (h in mW/(mm² K))."""
    from skfem import BilinearForm, LinearForm, asm

    boundary = space.scalar.boundary(facets)

    @BilinearForm
    def film(u, v, w):
        return h * u * v

    @LinearForm
    def load(v, w):
        return h * ambient * v

    return asm(film, boundary), asm(load, boundary)


def capacity(space: "FemSpace", materials: "Material | Sequence[Material]"):
    """C = ∫ ρ c T v on the scalar basis (c in J/(kg K) is ×1e6 mm²/(s² K) in the engine's units)."""
    import numpy as np
    from skfem import BilinearForm, asm

    parts = _materials(materials)
    rho_c = domain_values(space, [m.density * m.specific_heat * 1e6 for m in parts], space.scalar)

    @BilinearForm
    def form(u, v, w):
        return w["rc"] * u * v

    return asm(form, space.scalar, rc=rho_c if not isinstance(rho_c, float) else np.full(space.scalar.dx.shape, rho_c))


def rigid_body_modes(locations: "np.ndarray", component: "np.ndarray") -> "np.ndarray":
    """The near-nullspace pyamg needs for elasticity: 3 translations, 3 rotations."""
    import numpy as np

    n = len(component)
    x, y, z = locations[:, 0], locations[:, 1], locations[:, 2]
    B = np.zeros((n, 6))
    for c in range(3):
        B[component == c, c] = 1.0
    # rotation about z: (-y, x, 0); about x: (0, -z, y); about y: (z, 0, -x)
    B[component == 0, 3] = -y[component == 0]
    B[component == 1, 3] = x[component == 1]
    B[component == 1, 4] = -z[component == 1]
    B[component == 2, 4] = y[component == 2]
    B[component == 0, 5] = z[component == 0]
    B[component == 2, 5] = -x[component == 2]
    return B


def solve_spd(K, f, free: "np.ndarray", locations: "np.ndarray | None", component: "np.ndarray | None",
              warnings: list[str], *, method: str | None = None):
    """The solution on the free DOF of a symmetric positive definite system: direct for small systems, AMG+CG otherwise.

    ``K`` is assembled, or a matrix-free ``LinearOperator`` (:class:`ElementChunkOperator`),
    which only CG with a diagonal preconditioner can take. ``locations`` and
    ``component`` give elasticity's rigid-body near-nullspace; ``None`` for a
    scalar (thermal) system. ``method`` forces ``"direct"`` or ``"iterative"``;
    ``None`` chooses by size. Returns ``(u_free, how)``.
    """
    import numpy as np
    import scipy.sparse.linalg as spla

    if isinstance(K, ElementChunkOperator):
        return K.solve(f, free, warnings)
    Kff = K[free][:, free].tocsr()
    ff = f[free]
    if method == "direct" or (method is None and Kff.shape[0] < DIRECT_SOLVE_BELOW):
        return spla.spsolve(Kff.tocsc(), ff), "superlu"
    import pyamg

    B = None if locations is None else rigid_body_modes(locations[free], component[free])
    # pyamg's default (Jacobi) prolongator smoothing scales by a spectral radius it
    # estimates from numpy's global random generator: on a graded mesh a bad estimate
    # made the solve 30% slower or, now and then, diverge. Energy smoothing draws no
    # random numbers (and converges in fewer iterations), so the hierarchy repeats run
    # to run and numpy's global generator is left alone. Still, an attempt that
    # diverges is stopped early and tried again from another start: a small random
    # guess from a generator of the solver's own, seeded by the attempt.

    class Diverged(Exception):
        pass

    start = float(np.linalg.norm(ff))
    for seed in range(AMG_ATTEMPTS):
        ml = pyamg.smoothed_aggregation_solver(
            Kff, B=B, symmetry="symmetric", strength="symmetric", smooth="energy", max_coarse=500
        )
        guess = None
        if seed:
            guess = np.random.default_rng(seed).standard_normal(len(ff))
            guess *= 1e-3 * start / max(float(np.linalg.norm(Kff @ guess)), 1e-300)
        count = 0

        def watch(x):
            nonlocal count
            count += 1
            if count % 25 == 0:
                residual = float(np.linalg.norm(ff - Kff @ x))
                if residual > 10.0 * start or (count >= 150 and residual > 0.5 * start):
                    raise Diverged

        residuals: list[float] = []
        try:
            u = ml.solve(ff, x0=guess, tol=1e-8, accel="cg", maxiter=600, residuals=residuals, callback=watch)
        except Diverged:
            continue
        relative = residuals[-1] / max(residuals[0], 1e-300) if residuals else 1.0
        if relative <= 1e-6:
            return u, f"amg+cg ({len(residuals)} iterations)"
    warnings.append(
        f"the multigrid solve did not converge in {AMG_ATTEMPTS} attempts; falling back to the direct solver "
        "(slower). Check that the fixtures hold the part."
    )
    return spla.spsolve(Kff.tocsc(), ff), "superlu (after amg)"


class ElementChunkOperator:
    """The elastic stiffness product K @ x without K: element chunk by element chunk, in numpy.

    Each product rebuilds every chunk's basis (``chunk`` elements at a time),
    forms the strain of ``x`` at its quadrature points, the stress, and the
    virtual work against every local shape function, then scatters it to the
    global DOF. Memory is one chunk's basis, never the matrix; time is a few
    assemblies per product. :meth:`solve` runs Jacobi-preconditioned CG on the
    free DOF with it.
    """

    def __init__(self, space: "FemSpace", materials: "Material | Sequence[Material]", *, chunk: int = CHUNK_ELEMENTS):
        import numpy as np
        from skfem.models.elasticity import lame_parameters

        self.space = space
        self.chunk = int(chunk)
        parts = _materials(materials)
        #: The anisotropic path: each chunk's parts and weights (voigt_parts) instead of Lamé's numbers.
        self._materials = parts if anisotropic(parts) else None
        per_part = [lame_parameters(m.E, m.nu) for m in parts]
        elements = space.mesh.t.shape[1]
        domain = np.zeros(elements, dtype=np.int64) if space.domain is None else np.asarray(space.domain)
        self._lam = np.array([p[0] for p in per_part])[domain]
        self._mu = np.array([p[1] for p in per_part])[domain]
        self.shape = (space.basis.N, space.basis.N)
        self._diagonal = None

    def _chunks(self):
        import numpy as np
        from skfem import Basis

        elements = self.space.mesh.t.shape[1]
        for start in range(0, elements, self.chunk):
            rows = np.arange(start, min(start + self.chunk, elements))
            basis = Basis(self.space.mesh, self.space.basis.elem, elements=rows, quadrature=self.space.basis.quadrature)
            yield rows, basis

    def matvec(self, x: "np.ndarray") -> "np.ndarray":
        import numpy as np

        x = np.asarray(x, dtype=float).ravel()
        y = np.zeros(self.shape[0])
        for rows, basis in self._chunks():
            dofs = basis.element_dofs                                  # (local, elements)
            local = x[dofs]
            grad = sum(local[i][None, None, :, None] * basis.basis[i][0].grad for i in range(dofs.shape[0]))
            strain = 0.5 * (grad + np.transpose(grad, (1, 0, 2, 3)))
            if self._materials is not None:
                sigma = self._chunk_stress(rows, basis, strain)
            else:
                trace = strain[0, 0] + strain[1, 1] + strain[2, 2]
                lam, mu = self._lam[rows][:, None], self._mu[rows][:, None]
                sigma = 2.0 * mu * strain
                for i in range(3):
                    sigma[i, i] = sigma[i, i] + lam * trace
            weighted = sigma * basis.dx
            work = np.stack([np.einsum("ijeq,ijeq->e", weighted, basis.basis[i][0].grad) for i in range(dofs.shape[0])])
            y += np.bincount(dofs.ravel(), weights=work.ravel(), minlength=self.shape[0])
        return y

    def _chunk_stress(self, rows, basis, strain):
        import numpy as np

        e = voigt(strain)
        s = np.zeros_like(e)
        for C, weight in voigt_parts(self.space, self._materials, basis, rows):
            part = np.einsum("ij,j...->i...", C, e)
            s += part if weight is None else part * weight
        return _unvoigt(s)

    def __matmul__(self, x):
        return self.matvec(x)

    def diagonal(self) -> "np.ndarray":
        """K's diagonal, chunk by chunk (Jacobi's preconditioner)."""
        import numpy as np

        if self._diagonal is None:
            d = np.zeros(self.shape[0])
            for rows, basis in self._chunks():
                dofs = basis.element_dofs
                lam, mu = self._lam[rows][:, None], self._mu[rows][:, None]
                for i in range(dofs.shape[0]):
                    g = basis.basis[i][0].grad
                    strain = 0.5 * (g + np.transpose(g, (1, 0, 2, 3)))
                    if self._materials is not None:
                        energy = np.einsum("ijeq,ijeq->eq", self._chunk_stress(rows, basis, strain), strain)
                    else:
                        trace = strain[0, 0] + strain[1, 1] + strain[2, 2]
                        energy = 2.0 * mu * np.einsum("ijeq,ijeq->eq", strain, strain) + lam * trace * trace
                    d += np.bincount(dofs[i], weights=(energy * basis.dx).sum(axis=1), minlength=self.shape[0])
            self._diagonal = d
        return self._diagonal

    def solve(self, f: "np.ndarray", free: "np.ndarray", warnings: list[str], *, rtol: float = 1e-8, maxiter: int = 20_000):
        """Jacobi-preconditioned CG on the free DOF; the fixed DOF are zero."""
        import numpy as np
        import scipy.sparse.linalg as spla

        n = self.shape[0]
        inverse = 1.0 / self.diagonal()[free]

        def product(v):
            full = np.zeros(n)
            full[free] = v
            return self.matvec(full)[free]

        operator = spla.LinearOperator((len(free), len(free)), matvec=product)
        preconditioner = spla.LinearOperator((len(free), len(free)), matvec=lambda v: inverse * v)
        count = 0

        def tick(_):
            nonlocal count
            count += 1

        u, info = spla.cg(operator, f[free], rtol=rtol, atol=0.0, M=preconditioner, maxiter=maxiter, callback=tick)
        if info != 0:
            warnings.append(f"the matrix-free solve stopped after {count} iterations short of its tolerance")
        return u, f"matrix-free cg ({count} iterations)"
