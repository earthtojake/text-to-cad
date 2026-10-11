"""Norton creep at the quadrature points: the creep strain rate A σ^n t^m, integrated by backward Euler.

The state at every quadrature point of the vector basis is the creep strain
tensor (deviatoric: creep keeps the volume), the accumulated equivalent creep
strain p, and the von Mises stress the last converged step left there. Over a
time step from t₀ to t₁ the equivalent creep strain grows by

    Δp = Δτ A q₁ⁿ,    Δτ = ∫ t^m dt = (t₁^(m+1) − t₀^(m+1)) / (m + 1),

with q₁ the von Mises stress at the END of the step (backward Euler: stable at
any step, however stiff the creep), along the Prandtl-Reuss direction
(3/2) s/q. With the elastic trial stress q_tr = √(3/2)|2G (e − ε_c)| this is
one scalar equation per point,

    g(Δp) = Δp − Δτ A (q_tr − 3G Δp)ⁿ = 0,

increasing and concave on [0, q_tr / 3G], solved by Newton's method from 0
(which never overshoots on a concave increasing function). The stress follows
by the same radial return as J2 plasticity (:mod:`.plasticity`), and so does
its consistent tangent, with the creep's own "hardening" h = Δτ A n q^(n−1):

    C = K 1⊗1 + 2G θ (I_sym − 1/3 1⊗1) − 2G θ̄ n̂⊗n̂,
    θ = q / q_tr,   θ̄ = 3G h / (1 + 3G h) − (1 − θ).

The time is in hours; A is converted from per second when the material gives
it so. A domain with no creep block has A = 0 and stays elastic. Each update
also carries the step's local error estimate, the gap between the backward
and the forward Euler increment, Δτ A |q₁ⁿ − q₀ⁿ| / 2, as a share of the
stress there, which the analysis keeps under a tolerance by cutting the step.
Numeric imports live inside the functions.
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
    "CreepParams", "CreepState", "CreepUpdate", "SECONDS_PER_HOUR", "creep_params", "hardening_time", "norton_rate_per_hour",
    "norton_update",
]

SECONDS_PER_HOUR = 3600.0
#: sqrt(3/2): a deviatoric norm to the von Mises (equivalent) stress.
ROOT_THREE_HALVES = math.sqrt(1.5)
#: The point-wise Newton solve for Δp: at most this many iterations, to this relative tolerance.
POINT_ITERATIONS, POINT_TOLERANCE = 200, 1e-12


def norton_rate_per_hour(creep: dict) -> float:
    """A creep block's A for a time in hours: A_h = A_s · 3600^(m+1) when it is given per second."""
    A, m = float(creep["A"]), float(creep.get("m", 0.0))
    if creep.get("units", "MPa, hours") == "MPa, seconds":
        return A * SECONDS_PER_HOUR ** (m + 1.0)
    return A


def hardening_time(t0: float, t1: float, m: Any) -> Any:
    """Δτ = ∫ t^m dt from t0 to t1, (t1^(m+1) - t0^(m+1)) / (m+1): t1 - t0 for steady creep (m = 0)."""
    import numpy as np

    m = np.asarray(m, dtype=float)
    power = m + 1.0
    return (t1 ** power - t0 ** power) / power


@dataclass(frozen=True)
class CreepParams:
    """Bulk and shear moduli, and the Norton constants (A per hour, n, m): (elements, points) arrays per domain."""

    bulk: Any
    shear: Any
    A: Any
    n: Any
    m: Any


def creep_params(space: "FemSpace", materials: "list[Material]") -> CreepParams:
    """Each material's K, G and Norton constants on the space's quadrature points; A = 0 where it has no creep block."""
    from cadgen._internal.fea.operators import domain_values

    bulk = [m.E / (3.0 * (1.0 - 2.0 * m.nu)) for m in materials]
    shear = [m.E / (2.0 * (1.0 + m.nu)) for m in materials]
    A = [norton_rate_per_hour(m.creep) if m.creep else 0.0 for m in materials]
    n = [float(m.creep["n"]) if m.creep else 1.0 for m in materials]
    exponent = [float(m.creep.get("m", 0.0)) if m.creep else 0.0 for m in materials]
    return CreepParams(*(domain_values(space, values) for values in (bulk, shear, A, n, exponent)))


@dataclass
class CreepState:
    """The committed creep state at every quadrature point."""

    creep_strain: "np.ndarray"     # (3, 3, elements, points), deviatoric
    equivalent: "np.ndarray"       # (elements, points), p: the accumulated equivalent creep strain
    von_mises: "np.ndarray"        # (elements, points), the stress the last converged step left (MPa)

    @classmethod
    def zeros(cls, shape: tuple[int, int]) -> "CreepState":
        import numpy as np

        return cls(np.zeros((3, 3, *shape)), np.zeros(shape), np.zeros(shape))


@dataclass
class CreepUpdate:
    """One trial update from a committed state over a time step: stress, the state it would commit, the tangent."""

    stress: "np.ndarray"           # (3, 3, elements, points) MPa
    state: CreepState
    increment: "np.ndarray"        # (elements, points) Δp over the step
    error: "np.ndarray"            # (elements, points) the local error estimate, as a share of the stress there
    tangent: "np.ndarray | None"   # (3, 3, 3, 3, elements, points) MPa


def _increment(q_trial, dtau, A, n, G):
    """Δp solving Δp = dtau A (q_trial - 3G Δp)^n at every point (Newton from 0; the bracket [0, q_trial/3G] holds it)."""
    import numpy as np

    c = np.broadcast_to(dtau * A, q_trial.shape)
    n = np.broadcast_to(np.asarray(n, dtype=float), q_trial.shape)
    G = np.broadcast_to(np.asarray(G, dtype=float), q_trial.shape)
    dp = np.zeros(q_trial.shape)
    active = (c > 0) & (q_trial > 0)
    if not active.any():
        return dp
    ceiling = q_trial / (3.0 * G)
    for _ in range(POINT_ITERATIONS):
        q = np.maximum(q_trial - 3.0 * G * dp, 0.0)
        g = dp - c * q ** n
        slope = 1.0 + 3.0 * G * c * n * np.where(q > 0, q ** (n - 1.0), 0.0)
        step = np.where(active, -g / slope, 0.0)
        dp = np.clip(dp + step, 0.0, ceiling)
        if not np.any(np.abs(step) > POINT_TOLERANCE * np.maximum(dp, 1e-300)):
            break
    return dp


def norton_update(strain: "np.ndarray", state: CreepState, params: CreepParams, t0: float, t1: float, *,
                  tangent: bool = True) -> CreepUpdate:
    """The stress at total small strain ``strain`` at the end of the time step t0 -> t1 (hours), from ``state``.

    ``strain`` is (3, 3, elements, points). Nothing is committed: the update carries the state a converged
    step would keep. A step of no time (t1 = t0) is elastic: the instant the load goes on.
    """
    import numpy as np

    from cadgen._internal.fea.plasticity import identities, elastic_tensor

    delta, _, _ = identities()
    shape = strain.shape[2:]
    K, G, A, n = params.bulk, params.shear, params.A, params.n
    dtau = hardening_time(t0, t1, params.m) if t1 > t0 else np.zeros(np.shape(params.m))
    volumetric = strain[0, 0] + strain[1, 1] + strain[2, 2]
    deviator = strain - (volumetric / 3.0) * delta[..., None, None]
    trial = 2.0 * G * (deviator - state.creep_strain)
    norm = np.sqrt(np.einsum("ij...,ij...->...", trial, trial))
    q_trial = ROOT_THREE_HALVES * norm
    dp = _increment(q_trial, dtau, A, n, G)
    q = np.maximum(q_trial - 3.0 * G * dp, 0.0)
    safe = np.where(q_trial > 0, q_trial, 1.0)
    theta = np.where(q_trial > 0, q / safe, 1.0)
    direction = trial / np.where(norm > 0, norm, 1.0)
    stress = theta * trial + (K * volumetric) * delta[..., None, None]
    committed = CreepState(state.creep_strain + ROOT_THREE_HALVES * dp * direction, state.equivalent + dp, q)
    # The local error: backward Euler's increment against the forward one, Δτ A |q1^n - q0^n| / 2, as a stress share.
    forward = dtau * A * state.von_mises ** n
    error = 1.5 * G * np.abs(dp - forward) / np.maximum(np.maximum(q, state.von_mises), 1e-300)
    C = None
    if tangent:
        h = np.where(q > 0, dtau * A * n * np.where(q > 0, q, 1.0) ** (n - 1.0), 0.0)
        theta_bar = np.where(dp > 0, 3.0 * G * h / (1.0 + 3.0 * G * h) - (1.0 - theta), 0.0)
        C = elastic_tensor(K, G * theta, shape)
        C -= (2.0 * G * theta_bar) * np.einsum("ij...,kl...->ijkl...", direction, direction)
    return CreepUpdate(stress=stress, state=committed, increment=dp, error=error, tangent=C)
