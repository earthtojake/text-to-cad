"""Neo-Hookean rubber: compressible, total Lagrangian, large deformation.

The strain energy is the decoupled compressible Neo-Hookean one,

    W = μ/2 (Ī1 - 3) + κ/2 (J - 1)²,   Ī1 = J^(-2/3) tr(FᵀF),   F = I + ∇u,

with μ the shear modulus and κ the bulk modulus (``mu_MPa``, ``bulk_MPa``).
Everything is on the undeformed part (total Lagrangian): the first
Piola-Kirchhoff stress P = ∂W/∂F is what the internal force ``∫ P : ∇v``
reads, its derivative A = ∂P/∂F (a (3, 3, 3, 3, elements, points) array) the
tangent ``∫ ∇v : A : ∇u``, both through :class:`plasticity.ElementOps`.

    P = μ J^(-2/3) (F - I1/3 F⁻ᵀ) + κ (J - 1) J F⁻ᵀ,   I1 = tr(FᵀF)

A nearly incompressible rubber (κ ≈ 500 μ) stretched uniaxially carries a
nominal stress close to μ (λ - λ⁻²). The stress shown is the true (Cauchy)
stress σ = P Fᵀ / J. A metal part in a rubber study is a Neo-Hookean of the
same small-strain stiffness (μ = G, κ = K from E and ν). Numeric imports live
inside the functions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.femspace import FemSpace
    from cadgen._internal.fea.materials import Material

__all__ = ["NeoHookean", "cauchy", "moduli", "neo_hookean", "neo_hookean_params", "shore_a_estimate"]


@dataclass(frozen=True)
class NeoHookean:
    """μ and κ, MPa: numbers for one part, (elements, points) arrays per domain."""

    shear: Any
    bulk: Any


def moduli(material: "Material") -> tuple[float, float]:
    """(μ, κ) of a material: its Neo-Hookean block, else the small-strain G and K of its E and ν."""
    if material.hyperelastic:
        return float(material.hyperelastic["mu_MPa"]), float(material.hyperelastic["bulk_MPa"])
    return material.E / (2.0 * (1.0 + material.nu)), material.E / (3.0 * (1.0 - 2.0 * material.nu))


def neo_hookean_params(space: "FemSpace", materials: "list[Material]") -> NeoHookean:
    from cadgen._internal.fea.operators import domain_values

    pairs = [moduli(m) for m in materials]
    return NeoHookean(domain_values(space, [p[0] for p in pairs]), domain_values(space, [p[1] for p in pairs]))


def shore_a_estimate(shore_a: float) -> dict:
    """A first guess of a rubber's Neo-Hookean block from its Shore A hardness: an estimate, never data.

    Gent's relation E ≈ 0.0981 (56 + 7.62336 S) / (0.137505 (254 - 2.54 S)) MPa, μ = E/3, κ = 500 μ."""
    if not 0 < shore_a < 100:
        raise ValueError(f"Shore A hardness: between 0 and 100, got {shore_a:g}")
    E = 0.0981 * (56.0 + 7.62336 * shore_a) / (0.137505 * (254.0 - 2.54 * shore_a))
    mu = E / 3.0
    return {"model": "neo_hookean", "mu_MPa": round(mu, 4), "bulk_MPa": round(500.0 * mu, 2)}


def _inverse_and_det(F: "np.ndarray"):
    import numpy as np

    moved = np.moveaxis(F, (0, 1), (-2, -1))       # (..., 3, 3)
    J = np.linalg.det(moved)
    good = J > 0
    safe = np.where(good[..., None, None], moved, np.eye(3))
    inverse = np.linalg.inv(safe)
    return np.moveaxis(inverse, (-2, -1), (0, 1)), J, good


def neo_hookean(F: "np.ndarray", params: NeoHookean, *, tangent: bool = True):
    """(P, A, ok) at deformation gradients ``F`` (3, 3, elements, points).

    ``ok`` is False where an element turned inside out (J ≤ 0): there P is NaN,
    so a Newton step that got there is rejected and the load step is cut.
    """
    import numpy as np

    Finv, J, good = _inverse_and_det(F)
    FiT = np.transpose(Finv, (1, 0, 2, 3))
    Jsafe = np.where(good, J, 1.0)
    mu, kappa = params.shear, params.bulk
    I1 = np.einsum("ij...,ij...->...", F, F)
    a = mu * Jsafe ** (-2.0 / 3.0)
    P = a * (F - (I1 / 3.0) * FiT) + (kappa * (Jsafe - 1.0) * Jsafe) * FiT
    P = np.where(good, P, np.nan)
    A = None
    if tangent:
        delta = np.eye(3)
        A = (-2.0 / 3.0) * a * np.einsum("kl...,ij...->ijkl...", FiT, F - (I1 / 3.0) * FiT)
        A += a * delta[:, None, :, None, None, None] * delta[None, :, None, :, None, None]
        A -= (2.0 / 3.0) * a * np.einsum("kl...,ij...->ijkl...", F, FiT)
        A += (a * I1 / 3.0) * np.einsum("il...,kj...->ijkl...", FiT, FiT)
        A += (kappa * (2.0 * Jsafe * Jsafe - Jsafe)) * np.einsum("kl...,ij...->ijkl...", FiT, FiT)
        A -= (kappa * (Jsafe * Jsafe - Jsafe)) * np.einsum("il...,kj...->ijkl...", FiT, FiT)
    return P, A, bool(good.all())


def cauchy(P: "np.ndarray", F: "np.ndarray") -> "np.ndarray":
    """The true stress σ = P Fᵀ / J, (3, 3, elements, points)."""
    import numpy as np

    J = np.linalg.det(np.moveaxis(F, (0, 1), (-2, -1)))
    return np.einsum("ik...,jk...->ij...", P, F) / np.where(J > 0, J, 1.0)
