"""Modal superposition: a held part's steady response to a shake, built from its natural modes.

A part held at its fixtures and shaken (its fixtures moved together, a "base"
excitation) or pushed by forces that swing at one frequency answers, in each
mode ``i``, like a single mass on a spring with modal damping ζ:

- mode shapes are mass-normalised (φᵢᵀ M φᵢ = 1) and zero on held DOF;
- base excitation: the participation factor Γᵢ = φᵢᵀ M r, r the part moved
  rigidly by a unit translation along the shake, gives the motion relative to
  the base qᵢ = −Γᵢ a Hᵢ(ω) for a base acceleration of amplitude a (mm/s²);
- force excitation: the modal force pᵢ = φᵢᵀ F gives qᵢ = pᵢ Hᵢ(ω);
- Hᵢ(ω) = 1 / (ωᵢ² − ω² + 2iζωᵢω), the receptance of mode i;
- the effective mass of mode i along r is Γᵢ² (tonnes); all modes together hold
  rᵀ M r, so a few modes holding most of it are enough to shake the part.

The response is complex: the motion is Re(U e^{iωt}) = Re U cos ωt − Im U sin ωt.
A vector's largest size over a cycle is exact (:func:`vector_peak`); von Mises
is not linear in the phase, so its peak is sampled at :data:`PHASES` phases
over half a cycle (σ at θ + π is −σ at θ, the same von Mises).

Every function here is what the dynamic analyses share: ``harmonic`` (sine
sweep), ``random_vibration`` (PSD), ``shock`` (response spectrum) and
``transient`` (modal method). Units are the engine's: mm, N, tonne, s, MPa;
frequencies in rad/s unless a name says Hz. Numeric imports live inside the
functions, so importing this module stays instant.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.femspace import FemSpace
    from cadgen._internal.fea.materials import Material
    from cadgen._internal.fea.study import Load

__all__ = [
    "G0_MM_S2", "MAX_MODES", "Modes", "PHASES", "STRESS_COMPONENTS", "base_coordinates", "combine", "effective_mass",
    "fewest_modes", "find_modes", "force_coordinates", "load_vector", "mass_fractions", "modal_loads", "modal_stresses",
    "nodal_shapes", "participation", "phase_angles", "response_maxima", "rigid_translation", "transfer", "vector_peak",
    "von_mises_of", "von_mises_peak",
]

#: Standard gravity, mm/s²: an amplitude in g times this is mm/s².
G0_MM_S2 = 9806.65
#: Phases a von Mises peak is sampled at, over half a cycle (spec 5.8: 12 per frequency).
PHASES = 12
#: The most modes a search finds; past it the search says what it left out.
MAX_MODES = 60
#: The first search asks for this many modes and doubles until it reaches the top frequency.
START_MODES = 8
#: The order the six nodal stress components are stored in, per mode.
STRESS_COMPONENTS = ("xx", "yy", "zz", "xy", "yz", "xz")
_TWO_PI = 2.0 * math.pi


@dataclass
class Modes:
    """Natural modes of a held part, lowest first."""

    #: (m,) circular frequencies, rad/s, ascending.
    omega: "np.ndarray"
    #: (dofs, m) shapes on every vector DOF, mass-normalised (φᵀMφ = 1), zero on held DOF.
    vectors: "np.ndarray"
    #: How they were found, for the sidecar: "arpack shift-invert (superlu)", "lobpcg + amg (38 iterations)".
    how: str = ""
    #: Plain sentences about a search that stopped short.
    warnings: list[str] = field(default_factory=list)
    #: The highest frequency the search reached, Hz (at least the top asked for when ``complete``).
    searched_Hz: float = 0.0
    #: Whether every mode up to the top asked for was found (False: stopped at ``MAX_MODES`` or by ``enough``).
    complete: bool = True

    @property
    def frequencies_Hz(self) -> "np.ndarray":
        return self.omega / _TWO_PI

    def __len__(self) -> int:
        return int(len(self.omega))

    def take(self, indices) -> "Modes":
        """These modes only (indices into this set, kept in their order)."""
        import numpy as np

        indices = np.asarray(indices, dtype=np.int64)
        return Modes(self.omega[indices], self.vectors[:, indices], self.how, list(self.warnings), self.searched_Hz,
                     self.complete)


# -- finding the modes -------------------------------------------------------------------------------

def find_modes(
    K,
    M,
    fixed: "np.ndarray",
    top_Hz: float,
    *,
    method: str = "arpack",
    locations: "np.ndarray | None" = None,
    component: "np.ndarray | None" = None,
    start: int = START_MODES,
    cap: int = MAX_MODES,
    enough: "Callable[[np.ndarray, np.ndarray, np.ndarray], bool] | None" = None,
) -> Modes:
    """Every mode of ``K φ = ω² M φ`` (held DOF ``fixed`` removed) up to ``top_Hz``, at least one.

    The search asks for ``start`` modes and doubles until the highest found
    passes ``top_Hz``, until ``cap`` modes, or until ``enough(omega2, vectors,
    free)`` says the modes so far are enough (the ladder's reduce_modes: they
    hold the share of the mass it keeps). ``method`` ``"arpack"`` factorises
    ``K`` (shift-invert at 0); ``"lobpcg"`` uses a multigrid preconditioner
    (``locations`` and ``component`` of the free DOF help it) and no
    factorisation. The part must be held: with nothing held, ``K`` is singular.
    """
    import numpy as np

    from cadgen._internal.fea import eigen

    n_all = K.shape[0]
    free = np.setdiff1d(np.arange(n_all), np.asarray(fixed, dtype=np.int64))
    Kff = K[free][:, free].tocsr()
    Mff = M[free][:, free].tocsr()
    n = Kff.shape[0]
    top_omega2 = (_TWO_PI * top_Hz) ** 2
    # A small problem is solved densely (every pair); ARPACK and LOBPCG find fewer than all.
    cap = max(1, min(cap, n if method != "lobpcg" and n < eigen.DENSE_BELOW else n - 1))
    count = max(1, min(start, cap))
    precond = None
    stopped = False
    while True:
        if method == "lobpcg":
            if precond is None:
                precond = eigen.amg_preconditioner(
                    Kff, None if locations is None else locations[free], None if component is None else component[free])
            found = eigen.solve_generalized(Kff, Mff, count, precond=precond, which="SA", method="lobpcg")
        else:
            found = eigen.shift_invert(Kff, Mff, count, 0.0)
        order = np.argsort(found.values)
        omega2, vectors = found.values[order], found.vectors[:, order]
        if omega2[-1] >= top_omega2 or count >= cap:
            break
        if enough is not None and enough(omega2, vectors, free):
            stopped = True
            break
        count = min(2 * count, cap)
    warnings = list(found.warnings)
    keep = omega2 <= top_omega2
    keep[0] = True
    # Complete when the search passed the top, or found every mode the part has.
    complete = bool(omega2[-1] >= top_omega2 or len(omega2) == n)
    # Every mode up to the top is found when the search passed it; else it reached its highest.
    searched = top_Hz if complete else math.sqrt(max(float(omega2[-1]), 0.0)) / _TWO_PI
    if not complete and not stopped:
        warnings.append(f"found the lowest {len(omega2)} modes, up to {searched:.4g} Hz; "
                        f"modes from there to {top_Hz:.4g} Hz were left out")
    full = np.zeros((n_all, int(keep.sum())))
    full[free] = vectors[:, keep]
    # Mass-normalised on the whole matrix (the held rows are zero, so this is the free one's).
    norms = np.sqrt(np.einsum("ij,ij->j", full, M @ full))
    full /= np.where(norms > 0, norms, 1.0)
    omega = np.sqrt(np.maximum(omega2[keep], 0.0))
    return Modes(omega, full, found.how, warnings, searched, complete)


# -- how a shake reaches each mode -------------------------------------------------------------------

def rigid_translation(component: "np.ndarray", direction: Sequence[float]) -> "np.ndarray":
    """r: every vector DOF moved by a unit translation along ``direction`` (normalised here)."""
    import numpy as np

    d = np.asarray(direction, dtype=float)
    d = d / np.linalg.norm(d)
    return d[np.asarray(component, dtype=np.int64)]


def participation(modes: Modes, M, r: "np.ndarray") -> "np.ndarray":
    """Γᵢ = φᵢᵀ M r, (m,): how strongly a rigid shake along ``r`` drives each mode (sqrt tonnes)."""
    return modes.vectors.T @ (M @ r)


def modal_loads(modes: Modes, F: "np.ndarray") -> "np.ndarray":
    """pᵢ = φᵢᵀ F, (m,): each mode's share of a force vector."""
    return modes.vectors.T @ F


def effective_mass(modes: Modes, M, r: "np.ndarray") -> tuple["np.ndarray", float]:
    """(Γᵢ² per mode in tonnes, the total rᵀ M r): the mass each mode moves along ``r``, and the whole part's."""
    gamma = participation(modes, M, r)
    return gamma ** 2, float(r @ (M @ r))


def mass_fractions(modes: Modes, M, component: "np.ndarray") -> "np.ndarray":
    """(m, 3): the share of the part's mass each mode moves along X, Y and Z."""
    import numpy as np

    out = np.zeros((len(modes), 3))
    for c in range(3):
        masses, total = effective_mass(modes, M, (np.asarray(component) == c).astype(float))
        out[:, c] = masses / total if total > 0 else 0.0
    return out


def fewest_modes(weights: "np.ndarray", total: float, share: float = 0.9) -> tuple["np.ndarray", float]:
    """(indices ascending, the share of ``total`` they hold): the fewest modes whose ``weights`` (an
    effective mass, or any non-negative contribution) reach ``share`` of ``total``. When all of them
    together do not, every mode that carries any weight is kept."""
    import numpy as np

    weights = np.asarray(weights, dtype=float)
    if len(weights) == 0 or total <= 0:
        return np.arange(len(weights)), 0.0
    order = np.argsort(-weights, kind="stable")
    held = np.cumsum(weights[order])
    reach = np.flatnonzero(held >= share * total)
    if len(reach):
        chosen = order[:int(reach[0]) + 1]
    else:
        chosen = order[weights[order] > 1e-9 * max(float(weights.max()), 1e-300)]
        if len(chosen) == 0:
            chosen = order[:1]
    chosen = np.sort(chosen)
    return chosen, float(weights[chosen].sum() / total)


def load_vector(space: "FemSpace", loads: "Sequence[Load]", ordinal_of: dict[str, int]) -> "np.ndarray":
    """F on every vector DOF from face loads (``force``: a total vector in N spread evenly over the faces'
    area; ``pressure``: MPa pushing in), as the static solve builds it."""
    import numpy as np
    from skfem import LinearForm, asm

    basis = space.basis
    f = np.zeros(basis.N)
    for load in loads:
        facet_basis = basis.boundary(space.facets_of(load.faces, ordinal_of))
        if load.type == "force":
            traction = np.asarray(load.vector, dtype=float) / float(facet_basis.dx.sum())

            @LinearForm
            def form(v, w, traction=traction):
                return traction[0] * v[0] + traction[1] * v[1] + traction[2] * v[2]

        elif load.type == "pressure":
            pressure = float(load.pressure)

            @LinearForm
            def form(v, w, pressure=pressure):
                return -pressure * (w.n[0] * v[0] + w.n[1] * v[1] + w.n[2] * v[2])

        else:
            raise ValueError(f"a {load.type} load has no faces to swing on; shake the part with a base excitation instead")
        f += asm(form, facet_basis)
    return f


# -- frequency response ------------------------------------------------------------------------------

def transfer(omega_modes: "np.ndarray", omega: "np.ndarray", zeta) -> "np.ndarray":
    """Hᵢ(ω) = 1 / (ωᵢ² − ω² + 2iζᵢωᵢω), (frequencies, modes): each mode's receptance. ``zeta`` is one
    damping ratio or one per mode."""
    import numpy as np

    wi = np.asarray(omega_modes, dtype=float)[None, :]
    w = np.atleast_1d(np.asarray(omega, dtype=float))[:, None]
    z = np.broadcast_to(np.asarray(zeta, dtype=float), wi.shape[1:])[None, :]
    return 1.0 / (wi ** 2 - w ** 2 + 2j * z * wi * w)


def base_coordinates(omega_modes: "np.ndarray", gamma: "np.ndarray", omega: "np.ndarray", zeta,
                     acceleration_mm_s2: float) -> "np.ndarray":
    """qᵢ(ω) = −Γᵢ a Hᵢ(ω), (frequencies, modes): the modal motion relative to a base shaken at ``a`` mm/s²."""
    return -(acceleration_mm_s2 * transfer(omega_modes, omega, zeta)) * gamma[None, :]


def force_coordinates(omega_modes: "np.ndarray", p: "np.ndarray", omega: "np.ndarray", zeta) -> "np.ndarray":
    """qᵢ(ω) = pᵢ Hᵢ(ω), (frequencies, modes): the modal motion under forces of amplitude F (pᵢ = φᵢᵀF)."""
    return transfer(omega_modes, omega, zeta) * p[None, :]


def nodal_shapes(space: "FemSpace", modes: Modes) -> "np.ndarray":
    """(m, nodes, 3): each mode's shape per node (corner and mid-edge), mm per unit modal coordinate."""
    import numpy as np

    return np.stack([space.nodal(column) for column in modes.vectors.T]) if len(modes) else np.zeros((0, space.scalar_count, 3))


def combine(per_mode: "np.ndarray", q: "np.ndarray") -> "np.ndarray":
    """Σᵢ qᵢ Xᵢ for per-mode arrays ``per_mode`` (m, ...) and complex coordinates ``q`` (m,): the complex field."""
    import numpy as np

    return np.tensordot(np.asarray(q), per_mode, axes=(0, 0))


def vector_peak(Z: "np.ndarray") -> "np.ndarray":
    """The largest size over a cycle of each complex vector (n, 3), exactly: max over θ of |Re Z cos θ − Im Z sin θ|."""
    import numpy as np

    x, y = Z.real, Z.imag
    xx = np.einsum("...i,...i->...", x, x)
    yy = np.einsum("...i,...i->...", y, y)
    xy = np.einsum("...i,...i->...", x, y)
    mean = 0.5 * (xx + yy)
    return np.sqrt(np.maximum(mean + np.sqrt((0.5 * (xx - yy)) ** 2 + xy ** 2), 0.0))


def phase_angles(count: int = PHASES) -> "np.ndarray":
    """``count`` phases over half a cycle, [0, π): von Mises repeats every half cycle."""
    import numpy as np

    return np.arange(count) * (math.pi / count)


def von_mises_of(s: "np.ndarray") -> "np.ndarray":
    """Von Mises of stresses stored as (6, ...) in :data:`STRESS_COMPONENTS` order."""
    import numpy as np

    xx, yy, zz, xy, yz, xz = s
    return np.sqrt(np.maximum(0.5 * ((xx - yy) ** 2 + (yy - zz) ** 2 + (zz - xx) ** 2) + 3.0 * (xy ** 2 + yz ** 2 + xz ** 2), 0.0))


def von_mises_peak(S: "np.ndarray", phases: int = PHASES) -> "np.ndarray":
    """The largest von Mises over a cycle of a complex stress (6, n), sampled at ``phases`` phases."""
    import numpy as np

    peak = np.zeros(S.shape[1:])
    for theta in phase_angles(phases):
        np.maximum(peak, von_mises_of(S.real * math.cos(theta) - S.imag * math.sin(theta)), out=peak)
    return peak


def modal_stresses(space: "FemSpace", materials: "Material | Sequence[Material]", modes: Modes) -> "np.ndarray":
    """(m, 6, nodes): each mode's stress, its six components (:data:`STRESS_COMPONENTS`) recovered once and
    projected onto the nodes (one L2 projection, its mass matrix factorised once), MPa per unit modal coordinate."""
    import numpy as np
    import scipy.sparse as sparse
    import scipy.sparse.linalg as spla
    from skfem import BilinearForm, asm

    from cadgen._internal.fea import operators

    scalar = space.scalar
    count = len(modes)
    if count == 0:
        return np.zeros((0, 6, scalar.N))

    @BilinearForm
    def mass(u, v, w):
        return u * v

    lu = spla.splu(asm(mass, scalar).tocsc())
    # The projection's right-hand side as one matrix: node j of element e collects φ_j dx at e's points.
    elements, points = scalar.dx.shape
    phi = np.stack([scalar.basis[j][0].value for j in range(scalar.Nbfun)])           # (Nbfun, E, Q)
    rows = np.repeat(scalar.element_dofs[:, :, None], points, axis=2)
    cols = np.broadcast_to(np.arange(elements * points).reshape(1, elements, points), rows.shape)
    P = sparse.csr_matrix(((phi * scalar.dx[None]).ravel(), (rows.ravel(), cols.ravel())), shape=(scalar.N, elements * points))
    pairs = ((0, 0), (1, 1), (2, 2), (0, 1), (1, 2), (0, 2))
    out = np.zeros((count, 6, scalar.N))
    for i in range(count):
        s = operators.stress(space, materials, modes.vectors[:, i])
        rhs = np.stack([s[a, b].ravel() for a, b in pairs], axis=1)                     # (E*Q, 6)
        out[i] = lu.solve(np.asarray(P @ rhs)).T
    return out


def response_maxima(shapes: "np.ndarray", Q: "np.ndarray", omega: "np.ndarray", *,
                    base: "np.ndarray | None" = None, chunk: int = 16) -> tuple["np.ndarray", "np.ndarray"]:
    """(largest displacement, largest acceleration) over every node at each frequency, peak over phase:
    mm and mm/s². ``Q`` (frequencies, m) are the modal coordinates, ``shapes`` (m, nodes, 3) the modes per
    node. The displacement is the modes' (relative to a shaken base); the acceleration is absolute,
    −ω²U plus the base's own ``base`` (3,) mm/s² when the part is shaken at its fixtures."""
    import numpy as np

    m, nodes, _ = shapes.shape
    flat = shapes.reshape(m, nodes * 3)
    displacement = np.zeros(len(omega))
    acceleration = np.zeros(len(omega))
    for start in range(0, len(omega), chunk):
        stop = min(start + chunk, len(omega))
        U = (Q[start:stop] @ flat).reshape(stop - start, nodes, 3)
        displacement[start:stop] = vector_peak(U).max(axis=1)
        A = -(omega[start:stop] ** 2)[:, None, None] * U
        if base is not None:
            A = A + np.asarray(base, dtype=float)[None, None, :]
        acceleration[start:stop] = vector_peak(A).max(axis=1)
    return displacement, acceleration
