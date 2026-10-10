"""Linear piezoelectricity on a :class:`~cadgen._internal.fea.femspace.FemSpace`: displacement and voltage, coupled.

The stress-charge form, per part, in the part's axes::

    T = c^E S - e^T E        D = e S + eps^S E        E = -grad(phi)

with S the strain (Voigt 11, 22, 33, 23, 13, 12, engineering shears). A
material's ``piezo`` block (materials.piezo_block) gives c^E, e and eps^S in
its own axes, 3 along the poling; :func:`global_constants` turns them into the
part's axes. Units are the engine's, with the voltage in volts: c in MPa,
e in mC/mm² (C/m² x 1e-3), eps in mC/(V mm) (numerically F/m), so a volt
times a millicoulomb is a millijoule, one N mm. Charge comes out in mC.

The weak form gives one symmetric, indefinite system on the displacement u (the
vector basis) and the voltage phi (the scalar basis on the same nodes)::

    [ Kuu    G   ] [u  ]   [f       ]
    [ G^T  -Kpp  ] [phi] = [-q      ]

Kuu = ∫ ε(v)ᵀ c ε(u), G = ∫ ε(v)ᵀ eᵀ ∇phi, Kpp = ∫ ∇ψ · eps ∇phi, and q the
charge put on the nodes. :class:`System` holds it with the study's supports
(fixed faces, rollers, a symmetry plane's held component) and electrodes:
a held electrode is a Dirichlet group at its voltage, an open (floating) one
one unknown for all its nodes (an equipotential carrying no net charge), and a
conducting part one equipotential with its electrode or floating. The voltage
is scaled (``alpha``) so the two blocks are of one size. It solves a static
load (direct, or MINRES with a block multigrid preconditioner), the modes
(shift-invert Lanczos on the displacement, the voltage condensed through the
factorisation) and a driven sweep (direct per frequency, or by modes with the
static correction). Numeric imports live inside the functions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

__all__ = [
    "EPS0_F_M", "Electrode", "PartConstants", "Response", "System", "global_constants", "one_d_constants", "poling_frame",
    "thickness_kt",
]

#: The permittivity of free space, F/m (CODATA 2018).
EPS0_F_M = 8.8541878128e-12
#: Below this many reduced unknowns the modes are found densely.
DENSE_BELOW = 600
#: Voigt pairs, the engine's order.
VOIGT = ((0, 0), (1, 1), (2, 2), (1, 2), (0, 2), (0, 1))


# -- constants --------------------------------------------------------------------------------------


def poling_frame(poling) -> "np.ndarray":
    """Rows a1, a2, a3 of the material's axes in the part's: a3 along the poling, a1 the global axis least along it
    (X for a ceramic poled along Z), a2 = a3 x a1. Orthonormal."""
    import numpy as np

    p = np.asarray(poling, dtype=float)
    p = p / np.linalg.norm(p)
    axis = np.eye(3)[int(np.argmin(np.abs(p)))]
    a1 = axis - (axis @ p) * p
    a1 /= np.linalg.norm(a1)
    a2 = np.cross(p, a1)
    return np.array([a1, a2, p])


def _rotate_e(e: "np.ndarray", R: "np.ndarray") -> "np.ndarray":
    """A 3 x 6 coupling given in axes whose rows are ``R`` (global coordinates), in global axes."""
    import numpy as np

    tensor = np.zeros((3, 3, 3))
    for J, (j, k) in enumerate(VOIGT):
        tensor[:, j, k] = e[:, J]
        tensor[:, k, j] = e[:, J]
    turned = np.einsum("ai,bj,ck,abc->ijk", R, R, R, tensor)
    return np.array([[turned[i, j, k] for (j, k) in VOIGT] for i in range(3)])


def global_constants(block: dict) -> tuple["np.ndarray", "np.ndarray", "np.ndarray"]:
    """(c 6x6 MPa, e 3x6 mC/mm², eps 3x3 mC/(V mm)) of a ``piezo`` block in the part's axes."""
    import numpy as np

    from cadgen._internal.fea.operators import rotate_voigt

    c = np.asarray(block["cE_GPa"], dtype=float) * 1e3
    e = np.asarray(block["e_C_m2"], dtype=float) * 1e-3
    eps = np.asarray(block["epsS_rel"], dtype=float) * EPS0_F_M
    R = poling_frame(block["poling"])
    if np.allclose(R, np.eye(3), atol=1e-15):
        return c, e, eps
    return rotate_voigt(c, R), _rotate_e(e, R), R.T @ eps @ R


def one_d_constants(block: dict) -> dict:
    """The derived constants a hand check uses, SI, in the material's own axes (3 the poling): the compliance
    s^E, d = e s^E, the free permittivity eps^T = eps^S + d e^T, c33^D, the thickness coupling k_t and k33."""
    import numpy as np

    c = np.asarray(block["cE_GPa"], dtype=float) * 1e9
    e = np.asarray(block["e_C_m2"], dtype=float)
    epsS = np.asarray(block["epsS_rel"], dtype=float) * EPS0_F_M
    s = np.linalg.inv(c)
    d = e @ s
    epsT = epsS + d @ e.T
    c33D = c[2, 2] + e[2, 2] ** 2 / epsS[2, 2]
    kt2 = e[2, 2] ** 2 / (c33D * epsS[2, 2])
    k33_2 = d[2, 2] ** 2 / (s[2, 2] * epsT[2, 2])
    k31_2 = d[2, 0] ** 2 / (s[0, 0] * epsT[2, 2])
    return {"sE": s, "d": d, "epsT": epsT, "epsS": epsS, "c33D": c33D, "kt": math.sqrt(kt2), "k33": math.sqrt(k33_2),
            "k31": math.sqrt(k31_2), "d33": d[2, 2], "d31": d[2, 0], "s33E": s[2, 2], "s11E": s[0, 0],
            "g33": d[2, 2] / epsT[2, 2]}


def thickness_kt(fr: float, fa: float) -> float:
    """k_t of a thickness-mode plate from its resonance and anti-resonance (IEEE Std 176):
    k_t² = (π/2)(fr/fa) tan((π/2)(fa − fr)/fa)."""
    ratio = fr / fa
    return math.sqrt(max(0.5 * math.pi * ratio * math.tan(0.5 * math.pi * (1.0 - ratio)), 0.0))


@dataclass(frozen=True)
class PartConstants:
    """One part (domain) as the solve sees it: a piezo ceramic (c, e, eps), a dielectric (c, eps), a conductor (c;
    one voltage throughout) or electrically inert (c only)."""

    kind: str                          # "piezo", "dielectric", "conductor", "inert"
    c: Any                             # 6 x 6 MPa
    density: float                     # tonne/mm³
    e: Any = None                      # 3 x 6 mC/mm²
    eps: Any = None                    # 3 x 3 mC/(V mm)


@dataclass(frozen=True)
class Electrode:
    """Scalar DOF held at ``volts``, or (``volts`` None) floating: one voltage, no net charge."""

    name: str
    dofs: Any
    volts: float | None


# -- assembly ---------------------------------------------------------------------------------------


def _voigt_strain(grad) -> list:
    return [grad[0, 0], grad[1, 1], grad[2, 2], grad[1, 2] + grad[2, 1], grad[0, 2] + grad[2, 0], grad[0, 1] + grad[1, 0]]


def _part_bases(space, parts: list[PartConstants]):
    """Per part: (index, element rows, vector basis, scalar basis) on those elements alone, the space's quadrature."""
    import numpy as np
    from skfem import Basis

    elements = space.mesh.t.shape[1]
    domain = np.zeros(elements, dtype=np.int64) if space.domain is None or len(parts) == 1 else np.asarray(space.domain)
    for index in range(len(parts)):
        rows = np.flatnonzero(domain == index)
        if not len(rows):
            continue
        vector = Basis(space.mesh, space.basis.elem, elements=rows, quadrature=space.basis.quadrature)
        scalar = Basis(space.mesh, space.scalar.elem, elements=rows, quadrature=space.basis.quadrature)
        yield index, rows, vector, scalar


def assemble(space, parts: list[PartConstants]):
    """(Kuu, G, Kpp, M) on the whole space, each part with its own constants."""
    import numpy as np
    import scipy.sparse as sparse
    from skfem import BilinearForm, asm

    n_u, n_p = space.basis.N, space.scalar.N
    Kuu = sparse.csr_matrix((n_u, n_u))
    G = sparse.csr_matrix((n_u, n_p))
    Kpp = sparse.csr_matrix((n_p, n_p))
    M = sparse.csr_matrix((n_u, n_u))
    for index, _, vector, scalar in _part_bases(space, parts):
        part = parts[index]
        c = np.asarray(part.c, dtype=float)

        @BilinearForm
        def elastic(u, v, w, c=c):
            eu, ev = _voigt_strain(u.grad), _voigt_strain(v.grad)
            return sum(ev[i] * sum(c[i, j] * eu[j] for j in range(6) if c[i, j] != 0.0) for i in range(6))

        @BilinearForm
        def inertia(u, v, w, rho=float(part.density)):
            return rho * (u[0] * v[0] + u[1] * v[1] + u[2] * v[2])

        Kuu = Kuu + asm(elastic, vector)
        M = M + asm(inertia, vector)
        if part.kind == "piezo":
            e = np.asarray(part.e, dtype=float)

            @BilinearForm
            def coupling(phi, v, w, e=e):
                ev = _voigt_strain(v.grad)
                return sum(ev[I] * sum(e[k, I] * phi.grad[k] for k in range(3) if e[k, I] != 0.0) for I in range(6))

            G = G + asm(coupling, scalar, vector)
        if part.kind in ("piezo", "dielectric"):
            eps = np.asarray(part.eps, dtype=float)

            @BilinearForm
            def dielectric(phi, psi, w, eps=eps):
                return sum(psi.grad[i] * sum(eps[i, j] * phi.grad[j] for j in range(3) if eps[i, j] != 0.0) for i in range(3))

            Kpp = Kpp + asm(dielectric, scalar)
    return Kuu.tocsr(), G.tocsr(), Kpp.tocsr(), M.tocsr()


def surface_loads(space, loads, ordinal_of: dict[str, int], share: float = 1.0) -> "np.ndarray":
    """The force vector of a static study's surface loads (a force spread as a uniform traction, a pressure along
    the inward normal), a force times ``share`` (a symmetric half carries half of it)."""
    import numpy as np
    from skfem import LinearForm, asm

    f = np.zeros(space.basis.N)
    for load in loads:
        facets = space.basis.boundary(space.facets_of(load.faces, ordinal_of))
        if load.type == "force":
            traction = share * np.asarray(load.vector, dtype=float) / float(facets.dx.sum())

            @LinearForm
            def form(v, w, traction=traction):
                return traction[0] * v[0] + traction[1] * v[1] + traction[2] * v[2]
        else:
            pressure = float(load.pressure)

            @LinearForm
            def form(v, w, pressure=pressure):
                return -pressure * (w.n[0] * v[0] + w.n[1] * v[1] + w.n[2] * v[2])
        f += asm(form, facets)
    return f


# -- the reduced system ------------------------------------------------------------------------------


@dataclass
class Response:
    """A solve's answer on the whole space: ``u`` (vector DOF, global axes), ``phi`` (scalar DOF, volts), each
    electrode group's charge (mC; complex in a sweep) and voltage, in the electrodes' order."""

    u: Any
    phi: Any
    charges: list
    volts: list
    reactions: list = field(default_factory=list)


class System:
    """The coupled system on one space, with its supports and electrodes, reduced to its unknowns.

    ``supports`` is a :class:`~cadgen._internal.fea.supports.Supports`; ``electrodes`` the study's, with conductor
    parts' DOF as more floating groups (``conductors``). An electrode or conductor sharing nodes with another is one
    group; two held at different voltages there is a ValueError naming them. Voltage DOF no dielectric or piezo
    element touches carry no field: held at 0 and left out.
    """

    def __init__(self, space, matrices, supports, electrodes: list[Electrode], conductors: list = ()):
        import numpy as np
        import scipy.sparse as sparse

        Kuu, G, Kpp, M = matrices
        self.space = space
        self.n_u, self.n_p = Kuu.shape[0], Kpp.shape[0]
        self.supports = supports
        self.Kuu, self.G, self.Kpp, self.M = Kuu, G, Kpp, M
        # Groups: each electrode, each conducting part; merged where they share a node.
        groups = [(e.name, np.unique(np.asarray(e.dofs, dtype=np.int64)), e.volts, k) for k, e in enumerate(electrodes)]
        groups += [(f"conductor {k + 1}", np.unique(np.asarray(dofs, dtype=np.int64)), None, None)
                   for k, dofs in enumerate(conductors)]
        merged: list[list] = []
        for name, dofs, volts, index in groups:
            joined = [m for m in merged if np.intersect1d(m[1], dofs, assume_unique=True).size]
            entry = [[name], dofs, volts, [index] if index is not None else []]
            for other in joined:
                if other[2] is not None and entry[2] is not None and abs(other[2] - entry[2]) > 1e-12 * max(1.0, abs(entry[2])):
                    raise ValueError(f"electrodes: {other[0][0]} and {name} touch (or one conducting part joins them) but "
                                     f"are held at {other[2]:g} V and {entry[2]:g} V; they would short")
                entry = [other[0] + entry[0], np.union1d(other[1], entry[1]), entry[2] if entry[2] is not None else other[2],
                         other[3] + entry[3]]
                merged.remove(other)
            merged.append(entry)
        # The electrodes' groups in the electrodes' order (a conductor's group is not reported unless an electrode is in it).
        self.group_of_electrode = [next(i for i, m in enumerate(merged) if k in m[3]) for k in range(len(electrodes))]
        self.groups = merged
        active = np.zeros(self.n_p, dtype=bool)
        touched = np.unique(sparse.find(Kpp)[0])
        active[touched] = True
        column = np.full(self.n_p, -1, dtype=np.int64)
        phi0 = np.zeros(self.n_p)
        in_group = np.zeros(self.n_p, dtype=bool)
        count = 0
        self.group_column: list[int | None] = []
        for _, dofs, volts, _ in merged:
            in_group[dofs] = True
            if volts is not None:
                phi0[dofs] = volts
                self.group_column.append(None)
            elif active[dofs].any():
                column[dofs] = count
                self.group_column.append(count)
                count += 1
            else:
                self.group_column.append(None)
        free_p = np.flatnonzero(active & ~in_group)
        column[free_p] = count + np.arange(len(free_p))
        self.m_p = count + len(free_p)
        rows = np.flatnonzero(column >= 0)
        self.P = sparse.csr_matrix((np.ones(len(rows)), (rows, column[rows])), shape=(self.n_p, self.m_p))
        self.phi0 = phi0
        self.held_any = any(m[2] is not None for m in merged)
        # Displacement: the free DOF in the supports' frame.
        self.free_u = supports.free(self.n_u)
        self.m_u = len(self.free_u)
        self.S = sparse.csr_matrix((np.ones(self.m_u), (self.free_u, np.arange(self.m_u))), shape=(self.n_u, self.m_u))
        Kl, Ml, Gl = supports.local(Kuu), supports.local(M), (G if supports.frame is None else (supports.frame.T @ G).tocsr())
        self.Kl, self.Ml, self.Gl = Kl, Ml, Gl
        Kr = (self.S.T @ Kl @ self.S).tocsr()
        Gr = (self.S.T @ Gl @ self.P).tocsr()
        Pr = (self.P.T @ Kpp @ self.P).tocsr()
        # The voltage's scale: both diagonal blocks of one size.
        ku = float(np.abs(Kr.diagonal()).mean()) if self.m_u else 1.0
        kp = float(np.abs(Pr.diagonal()).mean()) if self.m_p else 1.0
        self.alpha = math.sqrt(ku / kp) if kp > 0 else 1.0
        a = self.alpha
        self.Kr, self.Gr, self.Pr = Kr, Gr, Pr
        self.A = sparse.bmat([[Kr, a * Gr], [a * Gr.T, -a * a * Pr]], format="csc")
        self.Mr = (self.S.T @ Ml @ self.S).tocsr()

    # -- pieces ---------------------------------------------------------------------------------------

    @property
    def size(self) -> int:
        return self.m_u + self.m_p

    def rhs(self, f_u: "np.ndarray"):
        """The scaled reduced right-hand side of a mechanical load ``f_u`` (global) with the held voltages."""
        import numpy as np

        f_l = self.supports.local_vector(f_u)
        lifted_u = self.Gl @ self.phi0              # Kuu u0 = 0 (held displacements are zero)
        lifted_p = -(self.Kpp @ self.phi0)          # the second row's held part: -Kpp phi0
        b_u = self.S.T @ (f_l - lifted_u)
        b_p = self.P.T @ (0.0 - lifted_p)
        return np.concatenate([b_u, self.alpha * b_p])

    def expand(self, y: "np.ndarray") -> tuple["np.ndarray", "np.ndarray"]:
        """(u global, phi) of a scaled reduced solution ``y`` (real or complex), the held voltages added."""
        import numpy as np

        u_l = self.S @ y[:self.m_u]
        phi = self.P @ (self.alpha * y[self.m_u:]) + self.phi0
        u = self.supports.global_vector(u_l) if self.supports.frame is not None else u_l
        return np.asarray(u), np.asarray(phi)

    def charges(self, u: "np.ndarray", phi: "np.ndarray") -> list:
        """Each merged group's charge (mC): minus the second row's residual summed over its nodes."""
        u_l = self.supports.local_vector(u)
        residual = self.Gl.T @ u_l - self.Kpp @ phi
        return [-complex(residual[dofs].sum()) if residual.dtype.kind == "c" else -float(residual[dofs].sum())
                for _, dofs, _, _ in self.groups]

    def response(self, y, f_u=None) -> Response:
        import numpy as np

        u, phi = self.expand(y)
        charges = self.charges(u, phi)
        volts = [phi[dofs].mean() for _, dofs, _, _ in self.groups]
        reactions = []
        if f_u is not None and np.isrealobj(u):
            residual = self.Kuu @ u + self.G @ phi - f_u
            component = self.space.component
            reactions = [tuple(float(residual[dofs][component[dofs] == c].sum()) for c in range(3))
                         for dofs in self.supports.per_fixture]
        return Response(u, phi, [charges[g] for g in self.group_of_electrode], [volts[g] for g in self.group_of_electrode],
                        reactions)

    def blocked_charges(self) -> list:
        """Each electrode's charge (mC) with the displacement held at zero (the clamped, or blocked, state): the held
        voltages alone, the floating groups settling to no net charge."""
        import numpy as np
        import scipy.sparse.linalg as spla

        b = -(self.P.T @ (self.Kpp @ self.phi0))
        phi_r = spla.spsolve(self.Pr.tocsc(), b) if self.m_p else np.zeros(0)
        phi = self.P @ np.atleast_1d(phi_r) + self.phi0
        charges = self.charges(np.zeros(self.n_u), phi)
        return [charges[g] for g in self.group_of_electrode]

    # -- static ---------------------------------------------------------------------------------------

    def solve_static(self, f_u: "np.ndarray", *, iterative: bool = False, warnings: list | None = None):
        """The static answer to a mechanical load and the held voltages: (Response, how)."""
        import numpy as np
        import scipy.sparse.linalg as spla

        b = self.rhs(f_u)
        if not iterative:
            y = spla.spsolve(self.A, b)
            return self.response(np.asarray(y), f_u), "superlu (coupled)"
        y, how = self._minres(b, warnings if warnings is not None else [])
        return self.response(y, f_u), how

    def _minres(self, b: "np.ndarray", warnings: list):
        """MINRES with a block-diagonal multigrid preconditioner: elasticity's AMG on the displacement, a scalar
        AMG on the (scaled) dielectric block; both blocks positive definite, so the preconditioner is."""
        import numpy as np
        import pyamg
        import scipy.sparse.linalg as spla

        from cadgen._internal.fea.operators import rigid_body_modes

        locations = self.space.locations[self.free_u] if self.supports.frame is None else None
        near = rigid_body_modes(locations, self.space.component[self.free_u]) if locations is not None else None
        mu = pyamg.smoothed_aggregation_solver(self.Kr, B=near, symmetry="symmetric", strength="symmetric", smooth="energy",
                                               max_coarse=500)
        P = (self.alpha ** 2 * self.Pr).tocsr()
        mp = pyamg.smoothed_aggregation_solver(P, symmetry="symmetric", strength="symmetric", smooth="energy", max_coarse=500)
        pu, pp = mu.aspreconditioner(cycle="V"), mp.aspreconditioner(cycle="V")
        m = self.m_u

        def apply(x):
            return np.concatenate([pu @ x[:m], pp @ x[m:]])

        preconditioner = spla.LinearOperator(self.A.shape, matvec=apply)
        count = 0

        def tick(_):
            nonlocal count
            count += 1

        y, info = spla.minres(self.A, b, M=preconditioner, rtol=1e-10, maxiter=5000, callback=tick)
        if info != 0:
            warnings.append(f"the iterative coupled solve stopped after {count} iterations short of its tolerance; "
                            "solved directly instead")
            return spla.spsolve(self.A, b), "superlu (after minres)"
        return y, f"minres + block amg ({count} iterations)"

    # -- modes ----------------------------------------------------------------------------------------

    def modes(self, count: int, *, shift: float | None = None):
        """The ``count`` lowest (ω², y) of the coupled system, y scaled reduced vectors with uᵀ M u = 1, rigid-body
        modes included; ``how``. The voltage is condensed: shift-invert on the displacement, each solve one with the
        factorised coupled matrix."""
        import numpy as np
        import scipy.linalg
        import scipy.sparse as sparse
        import scipy.sparse.linalg as spla

        m = self.m_u
        Mfull = sparse.bmat([[self.Mr, None], [None, sparse.csr_matrix((self.m_p, self.m_p))]], format="csc")
        if m < DENSE_BELOW:
            A = self.A.toarray()
            Auu, Aup, App = A[:m, :m], A[:m, m:], A[m:, m:]
            K = Auu - (Aup @ np.linalg.solve(App, Aup.T) if self.m_p else 0.0)
            values, vectors = scipy.linalg.eigh(0.5 * (K + K.T), self.Mr.toarray())
            values, vectors = values[:count], vectors[:, :count]
            how = "dense (coupled, condensed)"
        else:
            if shift is None:
                shift = -1e-4 * float(np.abs(self.Kr.diagonal()).mean() / max(np.abs(self.Mr.diagonal()).mean(), 1e-300))
            lu = spla.splu((self.A - shift * Mfull).tocsc())
            zeros = np.zeros(self.m_p)
            op = spla.LinearOperator((m, m), matvec=lambda x: lu.solve(np.concatenate([np.ravel(x), zeros]))[:m], dtype=float)
            dummy = spla.LinearOperator((m, m), matvec=lambda x: x, dtype=float)
            k = min(count, m - 2)
            values, vectors = spla.eigsh(dummy, k=k, M=self.Mr, sigma=shift, which="LM", OPinv=op,
                                         ncv=min(m, max(2 * k + 1, 20)), v0=np.random.default_rng(0).standard_normal(m))
            order = np.argsort(values)
            values, vectors = values[order], vectors[:, order]
            how = "arpack shift-invert (coupled, superlu)"
        norms = np.sqrt(np.einsum("ij,ij->j", vectors, self.Mr @ vectors))
        vectors = vectors / np.where(norms > 0, norms, 1.0)
        return values, self.complete(vectors), how

    def complete(self, u_red: "np.ndarray") -> "np.ndarray":
        """Reduced displacement columns with their condensed voltage: (size, k) scaled reduced vectors."""
        import numpy as np
        import scipy.sparse.linalg as spla

        m = self.m_u
        if not self.m_p:
            return u_red
        App = self.A[m:, m:].tocsc()
        Apu = self.A[m:, :m]
        lu = spla.splu(App)
        phis = np.column_stack([lu.solve(-(Apu @ u_red[:, j])) for j in range(u_red.shape[1])]) if u_red.shape[1] else \
            np.zeros((self.m_p, 0))
        return np.vstack([u_red, phis])

    # -- a driven sweep -------------------------------------------------------------------------------

    def sweep_direct(self, b: "np.ndarray", omegas, loss: float):
        """The scaled reduced complex answers at each ω (rad/s): (K(1 + iη) - ω² M) on the displacement."""
        import numpy as np
        import scipy.sparse as sparse
        import scipy.sparse.linalg as spla

        m = self.m_u
        damp = sparse.bmat([[self.Kr, None], [None, sparse.csr_matrix((self.m_p, self.m_p))]], format="csc")
        Mfull = sparse.bmat([[self.Mr, None], [None, sparse.csr_matrix((self.m_p, self.m_p))]], format="csc")
        A = self.A.astype(complex)
        out = []
        for omega in omegas:
            system = (A + 1j * loss * damp - omega ** 2 * Mfull).tocsc()
            out.append(spla.spsolve(system, b.astype(complex)))
        del m
        return out

    def sweep_modal(self, b: "np.ndarray", omegas, loss: float, values: "np.ndarray", vectors: "np.ndarray"):
        """The same by modes with the static correction (mode acceleration): y(ω) = A⁻¹b + Σ y_i (y_iᵀ b)
        [1/(λ_i(1 + iη) − ω²) − 1/λ_i]; exact as the modes kept reach past the sweep."""
        import numpy as np
        import scipy.sparse.linalg as spla

        static = spla.spsolve(self.A, b)
        weights = vectors.T @ b
        # The loss acts on the elastic stiffness alone (as the direct sweep's), so each mode's share of it is the
        # elastic part of its stiffness: uᵀ K u / λ (the rest is the field's, which is lossless here).
        u = vectors[:self.m_u]
        elastic = np.einsum("ij,ij->j", u, self.Kr @ u) / np.where(values > 0, values, 1.0)
        out = []
        for omega in omegas:
            factor = 1.0 / (values * (1.0 + 1j * loss * elastic) - omega ** 2) - 1.0 / values
            out.append(static + vectors @ (weights * factor))
        return out


def pair_modes(short: "np.ndarray", open_: "np.ndarray", M) -> list[int]:
    """For each short-circuit mode (columns, displacement part), the open-circuit mode most like it (largest |uᵀ M u|),
    each taken once."""
    import numpy as np

    mac = np.abs(short.T @ (M @ open_))
    taken: set[int] = set()
    out = []
    for i in range(mac.shape[0]):
        order = [j for j in np.argsort(-mac[i]) if j not in taken]
        out.append(int(order[0]) if order else -1)
        if order:
            taken.add(int(order[0]))
    return out


def field_recovery(space, parts: list[PartConstants], u: "np.ndarray", phi: "np.ndarray"):
    """(von Mises MPa, |E| V/mm) at the quadrature points, (elements, quadrature): σ = c ε(u) + eᵀ ∇phi."""
    import numpy as np

    elements = space.mesh.t.shape[1]
    quadrature = space.basis.X.shape[1]
    vm = np.zeros((elements, quadrature))
    field_strength = np.zeros((elements, quadrature))
    for index, rows, vector, scalar in _part_bases(space, parts):
        part = parts[index]
        grad = vector.interpolate(u).grad
        strain = np.stack(_voigt_strain(grad))
        stress = np.einsum("ij,j...->i...", np.asarray(part.c, dtype=float), strain)
        g = scalar.interpolate(phi).grad
        if part.kind == "piezo":
            stress = stress + np.einsum("ki,k...->i...", np.asarray(part.e, dtype=float), g)
        s11, s22, s33, s23, s13, s12 = stress
        vm[rows] = np.sqrt(np.maximum(0.5 * ((s11 - s22) ** 2 + (s22 - s33) ** 2 + (s33 - s11) ** 2)
                                      + 3.0 * (s12 ** 2 + s23 ** 2 + s13 ** 2), 0.0))
        if part.kind in ("piezo", "dielectric"):
            field_strength[rows] = np.sqrt((g ** 2).sum(axis=0))
    return vm, field_strength
