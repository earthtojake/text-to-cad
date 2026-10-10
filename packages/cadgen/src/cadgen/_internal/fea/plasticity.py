"""J2 plasticity: small strain, von Mises yield, bilinear isotropic hardening, at the quadrature points.

The state lives at every quadrature point of the vector basis: the plastic
strain tensor and the accumulated equivalent plastic strain α. A load step
updates it by the radial return of Simo and Hughes (Computational
Inelasticity, box 3.1): an elastic trial stress, and where its deviator lies
outside the yield surface ``sqrt(2/3) (σy + H α)``, a return along its own
direction. The consistent (algorithmic) tangent of that return,

    C = K 1⊗1 + 2G θ (I_sym - 1/3 1⊗1) - 2G θ̄ n⊗n,
    θ = 1 - 2G Δγ / |s_trial|,  θ̄ = 1 / (1 + H / 3G) - (1 - θ),

is a (3, 3, 3, 3, elements, points) array, assembled into the stiffness
``∫ ε(v) : C : ε(u)`` that Newton's method needs for its quadratic convergence.

Plastic flow keeps the volume, and quadratic tetrahedra that must keep it at
every quadrature point lock: a bending collapse comes out 10-20 % strong. So
the volumetric strain is each element's mean (mean dilatation, a B-bar with a
constant pressure per element, P2/P0): :func:`mean_dilatation_strain` and
:meth:`ElementOps.volumetric_matrix`. The internal force keeps its form, since
the pressure is constant over each element. A bilinear material is E up to yield and ``tangent_MPa`` past
it: the plastic modulus is ``H = E Et / (E - Et)``; Et = 0 is perfectly
plastic.

:class:`ElementOps` is the vectorised element loop both this and
:mod:`.hyperelastic` assemble with: an internal force ``∫ T : ∇v`` and a
tangent ``∫ ∇v : A : ∇u`` from quadrature-point arrays, element chunk by
element chunk. It computes what :func:`tangent_form` (the same integral as a
scikit-fem ``BilinearForm``) computes, about eight times faster, which is
what a Newton iteration per load step affords. Numeric imports live inside the
functions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.femspace import FemSpace
    from cadgen._internal.fea.materials import Material

__all__ = [
    "CHUNK_ELEMENTS", "ElementOps", "J2Params", "J2State", "J2Update", "elastic_tensor", "hardening_modulus",
    "j2_params", "mean_dilatation_strain", "radial_return", "tangent_form",
]

#: Elements per chunk of the vectorised element loop (a chunk's gradients: about 25 kB an element).
CHUNK_ELEMENTS = 2000
#: sqrt(2/3): a deviatoric norm to the uniaxial (equivalent) measure.
ROOT_TWO_THIRDS = math.sqrt(2.0 / 3.0)


def hardening_modulus(E: float, tangent: float) -> float:
    """The plastic modulus H of a bilinear curve whose slope past yield is ``tangent``: E Et / (E - Et)."""
    return E * tangent / (E - tangent)


@dataclass(frozen=True)
class J2Params:
    """Bulk and shear moduli, yield and plastic modulus: numbers for one part, (elements, points) arrays per domain.

    A part with no plasticity of its own has an infinite yield: it stays elastic."""

    bulk: Any
    shear: Any
    yield_MPa: Any
    hardening: Any


def j2_params(space: "FemSpace", materials: "list[Material]") -> J2Params:
    """Each material's K, G, yield and H on the space's quadrature points (operators.domain_values)."""
    from cadgen._internal.fea.operators import domain_values

    bulk = [m.E / (3.0 * (1.0 - 2.0 * m.nu)) for m in materials]
    shear = [m.E / (2.0 * (1.0 + m.nu)) for m in materials]
    plastic = [m.tangent is not None and m.yield_strength is not None for m in materials]
    yields = [float(m.yield_strength) if p else math.inf for m, p in zip(materials, plastic)]
    hardening = [hardening_modulus(m.E, m.tangent) if p else 0.0 for m, p in zip(materials, plastic)]
    return J2Params(*(domain_values(space, values) for values in (bulk, shear, yields, hardening)))


@dataclass
class J2State:
    """The committed plastic state at every quadrature point."""

    plastic_strain: "np.ndarray"   # (3, 3, elements, points), deviatoric
    equivalent: "np.ndarray"       # (elements, points), α: the accumulated equivalent plastic strain

    @classmethod
    def zeros(cls, shape: tuple[int, int]) -> "J2State":
        import numpy as np

        return cls(np.zeros((3, 3, *shape)), np.zeros(shape))


@dataclass
class J2Update:
    """One trial update from a committed state: stress, the state it would commit, and the tangent."""

    stress: "np.ndarray"           # (3, 3, elements, points) MPa
    state: J2State
    yielding: "np.ndarray"         # (elements, points) bool
    tangent: "np.ndarray | None"   # (3, 3, 3, 3, elements, points) MPa


def identities():
    import numpy as np

    delta = np.eye(3)
    one = np.einsum("ij,kl->ijkl", delta, delta)
    symmetric = 0.5 * (np.einsum("ik,jl->ijkl", delta, delta) + np.einsum("il,jk->ijkl", delta, delta))
    return delta, one, symmetric


def elastic_tensor(bulk, shear, shape: tuple[int, int]) -> "np.ndarray":
    """Isotropic C = K 1⊗1 + 2G (I_sym - 1/3 1⊗1) at every point, (3, 3, 3, 3, elements, points)."""
    import numpy as np

    _, one, symmetric = identities()
    bulk = np.broadcast_to(np.asarray(bulk, dtype=float), shape)
    shear = np.broadcast_to(np.asarray(shear, dtype=float), shape)
    return one[..., None, None] * bulk + 2.0 * (symmetric - one / 3.0)[..., None, None] * shear


def mean_dilatation_strain(grad: "np.ndarray", ops: "ElementOps") -> "np.ndarray":
    """The small strain of ``grad`` (3, 3, elements, points) with its volumetric part replaced by the element's mean."""
    import numpy as np

    strain = 0.5 * (grad + np.transpose(grad, (1, 0, 2, 3)))
    trace = strain[0, 0] + strain[1, 1] + strain[2, 2]
    correction = (ops.mean_dilatation(grad)[:, None] - trace) / 3.0
    for i in range(3):
        strain[i, i] = strain[i, i] + correction
    return strain


def radial_return(strain: "np.ndarray", state: J2State, params: J2Params, *, tangent: bool = True) -> J2Update:
    """The stress at total small strain ``strain`` from the committed ``state``, by radial return.

    ``strain`` is (3, 3, elements, points). Nothing is committed: the update
    carries the state a converged step would keep.
    """
    import numpy as np

    delta, one, symmetric = identities()
    shape = strain.shape[2:]
    K, G, H = params.bulk, params.shear, params.hardening
    volumetric = strain[0, 0] + strain[1, 1] + strain[2, 2]
    deviator = strain - (volumetric / 3.0) * delta[..., None, None]
    trial = 2.0 * G * (deviator - state.plastic_strain)
    norm = np.sqrt(np.einsum("ij...,ij...->...", trial, trial))
    radius = ROOT_TWO_THIRDS * (params.yield_MPa + H * state.equivalent)
    excess = norm - radius
    yielding = excess > 1e-12 * np.maximum(radius, 1.0)
    gamma = np.where(yielding, excess / (2.0 * G + (2.0 / 3.0) * H), 0.0)
    safe = np.where(norm > 0, norm, 1.0)
    direction = trial / safe
    deviatoric_stress = trial - 2.0 * G * gamma * direction
    stress = deviatoric_stress + (K * volumetric) * delta[..., None, None]
    committed = J2State(state.plastic_strain + gamma * direction, state.equivalent + ROOT_TWO_THIRDS * gamma)
    C = None
    if tangent:
        theta = 1.0 - 2.0 * G * gamma / safe
        theta_bar = np.where(yielding, 1.0 / (1.0 + H / (3.0 * G)) - (1.0 - theta), 0.0)
        C = elastic_tensor(K, G * theta, shape)
        C -= (2.0 * G * theta_bar) * np.einsum("ij...,kl...->ijkl...", direction, direction)
    return J2Update(stress=stress, state=committed, yielding=yielding, tangent=C)


class ElementOps:
    """The element loop of a nonlinear solve on a vector basis, vectorised over element chunks.

    ``force(T)`` is ``∫ T : ∇v`` (T a stress, symmetric or not: the first
    Piola-Kirchhoff in a total Lagrangian solve) and ``matrix(A)`` is
    ``∫ ∇v : A : ∇u``, both from (3, 3[, 3, 3], elements, points) arrays at the
    basis's own quadrature points. A J2 tangent has the minor symmetries, so
    ``∇`` and the symmetric gradient give the same stiffness.
    """

    def __init__(self, basis, *, chunk: int = CHUNK_ELEMENTS):
        import numpy as np

        self.basis = basis
        self.N = int(basis.N)
        self.dofs = np.asarray(basis.element_dofs)            # (local, elements)
        self.local, self.elements = self.dofs.shape
        self.dx = np.asarray(basis.dx)                        # (elements, points)
        self.points = self.dx.shape[1]
        self.chunk = max(int(chunk), 1)

    @property
    def volumes(self) -> "np.ndarray":
        """(elements,) each element's volume."""
        return self.dx.sum(axis=1)

    def mean_dilatation(self, grad: "np.ndarray") -> "np.ndarray":
        """(elements,) each element's mean volumetric strain, ∫ tr ∇u / V."""
        trace = grad[0, 0] + grad[1, 1] + grad[2, 2]
        return (trace * self.dx).sum(axis=1) / self.volumes

    def volumetric_matrix(self, bulk: "np.ndarray"):
        """Σ_e K_e (∫_e div v)(∫_e div u) / V_e: mean dilatation's volumetric stiffness, ``bulk`` (elements,)."""
        import numpy as np
        import scipy.sparse as sparse

        if getattr(self, "_divergence", None) is None:
            g = np.zeros((self.local, self.elements))
            for a in range(self.local):
                grad = self.basis.basis[a][0].grad
                g[a] = ((grad[0, 0] + grad[1, 1] + grad[2, 2]) * self.dx).sum(axis=1)
            self._divergence = g
        g = self._divergence
        element = (np.asarray(bulk, dtype=float) / self.volumes)[:, None, None] * np.einsum("ae,be->eab", g, g)
        dofs = self.dofs.T
        rows = np.repeat(dofs, self.local, axis=1).ravel()
        cols = np.tile(dofs, (1, self.local)).ravel()
        return sparse.coo_matrix((element.ravel(), (rows, cols)), shape=(self.N, self.N)).tocsr()

    def gradient(self, u: "np.ndarray") -> "np.ndarray":
        """∇u at the quadrature points, (3, 3, elements, points): ``[i, j]`` is ∂u_i/∂x_j."""
        import numpy as np

        return np.asarray(self.basis.interpolate(u).grad)

    def _rows(self):
        for start in range(0, self.elements, self.chunk):
            yield slice(start, min(start + self.chunk, self.elements))

    def _grads(self, rows: slice) -> "np.ndarray":
        """(local, 9, chunk, points): each local shape function's gradient over the chunk."""
        import numpy as np

        return np.stack([self.basis.basis[a][0].grad[:, :, rows].reshape(9, -1, self.points) for a in range(self.local)])

    def force(self, T: "np.ndarray") -> "np.ndarray":
        """∫ T : ∇v over every element, as a global vector."""
        import numpy as np

        out = np.zeros(self.N)
        for rows in self._rows():
            weighted = T[:, :, rows].reshape(9, -1, self.points) * self.dx[rows]
            local = np.einsum("aieq,ieq->ae", self._grads(rows), weighted, optimize=True)
            out += np.bincount(self.dofs[:, rows].ravel(), weights=local.ravel(), minlength=self.N)
        return out

    def matrix(self, A: "np.ndarray"):
        """∫ ∇v : A : ∇u, as a CSR matrix (``A`` is (3, 3, 3, 3, elements, points))."""
        import numpy as np
        import scipy.sparse as sparse

        data, rows_out, cols_out = [], [], []
        for rows in self._rows():
            grads = self._grads(rows)                                          # (a, I, e, q)
            count = grads.shape[2]
            Am = A[:, :, :, :, rows].reshape(9, 9, count, self.points)
            pushed = np.einsum("IJeq,bJeq->bIeq", Am, grads, optimize=True)  # A : ∇φ_b
            left = (grads * self.dx[rows]).transpose(2, 0, 1, 3).reshape(count, self.local, 9 * self.points)
            right = pushed.transpose(2, 1, 3, 0).reshape(count, 9 * self.points, self.local)
            element = np.matmul(left, right)                                     # (e, a, b)
            dofs = self.dofs[:, rows].T                                          # (e, a)
            data.append(element.ravel())
            rows_out.append(np.repeat(dofs, self.local, axis=1).ravel())
            cols_out.append(np.tile(dofs, (1, self.local)).ravel())
        matrix = sparse.coo_matrix(
            (np.concatenate(data), (np.concatenate(rows_out), np.concatenate(cols_out))), shape=(self.N, self.N)
        )
        return matrix.tocsr()


def tangent_form():
    """The tangent ``∫ ∇v : A : ∇u`` as a scikit-fem BilinearForm, ``A`` passed as the keyword ``C``.

    The reference :meth:`ElementOps.matrix` is checked against: ``asm(tangent_form(), basis, C=A)``.
    """
    import numpy as np
    from skfem import BilinearForm

    @BilinearForm
    def form(u, v, w):
        return np.einsum("ij...,ij...->...", np.einsum("ijkl...,kl...->ij...", w["C"], u.grad), v.grad)

    return form
