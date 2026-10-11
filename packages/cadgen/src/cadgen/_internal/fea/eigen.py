"""Generalized symmetric eigenproblems: the modes of a vibration study and the shapes of a buckling one.

One question, :func:`solve_generalized`: the ``k`` eigenpairs at one end of the
spectrum of ``A φ = μ B φ``, ``A`` symmetric and ``B`` symmetric positive
definite. Two ways to answer it:

- ``"arpack"``: Lanczos (scipy's ``eigsh``) on ``B⁻¹A``, with ``B`` factorised
  once (SuperLU) or solved by an operator the caller passes (``solve_B``). A
  buckling study asks it with ``A = -Kg`` and ``B = K`` for the largest
  ``μ = 1/λ``: the shift-invert form, whose largest values are the lowest
  load factors.
- ``"lobpcg"``: preconditioned block conjugate gradients (scipy's ``lobpcg``)
  with an algebraic multigrid preconditioner and no factorisation at all, for
  when one does not fit (the ladder's iterative rung). A vibration study asks
  it with ``A = K + sM`` and ``B = M`` for the smallest ``ω² + s``.

:func:`shift_invert` is the vibration study's direct path: the modes of
``K φ = ω² M φ`` nearest a shift σ, through ``(K - σM)⁻¹M`` in the ``M`` inner
product. σ = -s below the spectrum gives the lowest modes, even of a part free
in space (its rigid-body modes at ω² = 0 included); σ at the bottom of a
frequency window, where ``K - σM`` is indefinite, gives the window's. ``M`` is
well conditioned, which keeps the modes of a nearly singular ``K`` orthogonal.

Every vector comes back ``B``-normalised. Units are whatever the operators are
in; nothing here knows about frequencies. Numeric imports live inside the
functions.
"""

from __future__ import annotations

import math
import warnings as warnings_module
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

__all__ = ["DENSE_BELOW", "EigenResult", "amg_preconditioner", "factorized", "shift_invert", "solve_generalized"]

#: Below this many unknowns the problem is solved densely (exact, and Lanczos needs room above k).
DENSE_BELOW = 400
#: Extra vectors LOBPCG carries beyond the k it is asked for: the block converges faster with a guard.
_GUARD = 4


@dataclass
class EigenResult:
    """The eigenpairs found: ``values`` in the order asked (largest first for ``LA``), ``vectors`` (n, k)."""

    values: "np.ndarray"
    vectors: "np.ndarray"
    #: How it was solved, for the sidecar: "arpack (superlu)", "lobpcg + amg (38 iterations)", "dense".
    how: str
    #: Plain sentences about anything short of converged.
    warnings: list[str] = field(default_factory=list)


def factorized(B):
    """``B⁻¹`` as a ``LinearOperator``: one SuperLU factorisation, reused for every solve."""
    import scipy.sparse.linalg as spla

    lu = spla.splu(B.tocsc())
    return spla.LinearOperator(B.shape, matvec=lu.solve, dtype=float)


def amg_preconditioner(B, locations: "np.ndarray | None" = None, component: "np.ndarray | None" = None):
    """An approximate ``B⁻¹`` (one smoothed-aggregation V-cycle) for LOBPCG; elasticity's rigid-body
    modes are its near-nullspace when ``locations`` and ``component`` (of the same rows) are given."""
    import pyamg

    from cadgen._internal.fea.operators import rigid_body_modes

    near = None if locations is None else rigid_body_modes(locations, component)
    ml = pyamg.smoothed_aggregation_solver(
        B.tocsr(), B=near, symmetry="symmetric", strength="symmetric", smooth="energy", max_coarse=500
    )
    return ml.aspreconditioner(cycle="V")


def _dense(A, B, k: int, which: str, constraints: "np.ndarray | None" = None) -> EigenResult:
    import numpy as np
    import scipy.linalg

    dense = (lambda m: m.toarray() if hasattr(m, "toarray") else np.asarray(m))
    Bd = dense(B)
    values, vectors = scipy.linalg.eigh(dense(A), Bd)
    order = np.argsort(-values if which == "LA" else -np.abs(values) if which == "LM" else values)
    if constraints is not None and constraints.shape[1]:
        # Leave out the pairs that lie in the constraints' span (B-orthogonal to them is what LOBPCG keeps).
        Y = np.asarray(constraints, dtype=float)
        basis = Y @ np.linalg.inv(np.linalg.cholesky(Y.T @ Bd @ Y)).T
        inside = np.linalg.norm(basis.T @ Bd @ vectors, axis=0)
        order = order[inside[order] < 0.5]
    order = order[:k]
    return EigenResult(values[order], vectors[:, order], "dense")


def _normalised(vectors: "np.ndarray", B) -> "np.ndarray":
    import numpy as np

    norms = np.sqrt(np.einsum("ij,ij->j", vectors, B @ vectors))
    return vectors / np.where(norms > 0, norms, 1.0)


def solve_generalized(
    A,
    B_spd,
    k: int,
    *,
    solve_B=None,
    precond=None,
    which: str = "LA",
    method: str | None = None,
    tol: float | None = None,
    maxiter: int | None = None,
    seed: int = 0,
    constraints: "np.ndarray | None" = None,
) -> EigenResult:
    """The ``k`` eigenpairs of ``A φ = μ B φ`` with the largest (``which="LA"``), smallest (``"SA"``) or
    largest in magnitude (``"LM"``, ARPACK only; returned largest first) ``μ``.

    ``B_spd`` must be symmetric positive definite; ``A`` symmetric. ``method``
    is ``"arpack"`` (``solve_B`` an operator for ``B⁻¹``, else ``B`` is
    factorised here) or ``"lobpcg"`` (``precond`` an approximate inverse of the
    matrix whose smallest eigenvalues are wanted, ``A`` for ``SA`` and ``B``
    for ``LA``; built by AMG here when not given; ``constraints``, columns the
    vectors are kept ``B``-orthogonal to, such as known rigid-body modes). ``None`` takes LOBPCG when a
    preconditioner is passed and no ``solve_B``, else ARPACK. A small problem
    is solved densely whatever the method. Vectors are ``B``-normalised.
    """
    import numpy as np
    import scipy.sparse.linalg as spla

    if which not in ("LA", "SA", "LM"):
        raise ValueError(f"which: 'LA', 'SA' or 'LM', got {which!r}")
    if which == "LM" and method == "lobpcg":
        raise ValueError("LOBPCG finds one end of the spectrum: which 'LA' or 'SA'")
    n = A.shape[0]
    k = int(k)
    if not 1 <= k < n:
        raise ValueError(f"asked for {k} eigenpairs of a problem with {n} unknowns")
    if n < DENSE_BELOW or k >= n // 3:
        return _dense(A, B_spd, k, which, constraints)
    if method is None:
        method = "lobpcg" if precond is not None and solve_B is None else "arpack"

    if method == "arpack":
        how = "arpack" + ("" if solve_B is not None else " (superlu)")
        inverse = solve_B if solve_B is not None else factorized(B_spd)
        found: list[str] = []
        # A fixed start, so a run repeats exactly: ARPACK's own is random, and a pair of equal modes then turns.
        start = np.random.default_rng(seed).standard_normal(n)
        try:
            values, vectors = spla.eigsh(A, k=k, M=B_spd, Minv=inverse, which=which, ncv=min(n, max(2 * k + 1, 20)),
                                         tol=tol or 0.0, maxiter=maxiter or 2000, v0=start)
        except spla.ArpackNoConvergence:
            # A wider Krylov space converges where a tight one stalled (clustered or repeated values).
            how += ", widened"
            try:
                values, vectors = spla.eigsh(A, k=k, M=B_spd, Minv=inverse, which=which, ncv=min(n, 4 * k + 40),
                                             tol=tol or 0.0, maxiter=maxiter or 5000, v0=start)
            except spla.ArpackNoConvergence as exc:
                values, vectors = exc.eigenvalues, exc.eigenvectors
                found.append(f"the eigen solve converged {len(values)} of the {k} pairs it looked for")
        order = np.argsort(-values if which in ("LA", "LM") else values)
        return EigenResult(values[order], _normalised(vectors[:, order], B_spd), how, found)

    if method != "lobpcg":
        raise ValueError(f"method: 'arpack' or 'lobpcg', got {method!r}")
    if precond is None:
        precond = amg_preconditioner(A if which == "SA" else B_spd)
    block = min(k + _GUARD, n // 5)
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n, block))
    limit = maxiter or 400
    target = tol or 1e-6
    # Scaled to unit diagonals, so the numbers are of one size whatever the units. LOBPCG stops on an
    # absolute residual, so a pass that stops short of `target` relative to its eigenvalues is run again
    # from where it stopped, with the tolerance scaled down to them. A preconditioner's scale does not matter.
    a = float(np.abs(A.diagonal()).mean()) or 1.0
    b = float(np.abs(B_spd.diagonal()).mean()) or 1.0
    As, Bs = A / a, B_spd / b
    absolute, iterations, worst = target, 0, math.inf
    for _ in range(3):
        with warnings_module.catch_warnings():
            warnings_module.simplefilter("ignore", UserWarning)
            values, X, history = spla.lobpcg(As, X, B=Bs, M=precond, Y=constraints, tol=absolute, maxiter=limit,
                                             largest=which == "LA", retResidualNormsHistory=True)
        iterations += len(history)
        order = np.argsort(-values if which == "LA" else values)[:k]
        chosen, vectors = values[order], _normalised(X[:, order], Bs)
        residual = np.linalg.norm(As @ vectors - (Bs @ vectors) * chosen, axis=0)
        worst = float((residual / np.maximum(np.abs(chosen) * np.linalg.norm(Bs @ vectors, axis=0), 1e-300)).max())
        if worst <= target:
            break
        absolute = target * float(np.abs(chosen).min())
    found: list[str] = []
    if worst > 1e3 * target:
        found.append(f"the iterative eigen solve stopped {worst:.1e} short of converged after {iterations} iterations; "
                     "its last digits may be off")
    return EigenResult(chosen * (a / b), _normalised(vectors, B_spd), f"lobpcg + amg ({iterations} iterations)", found)


def shift_invert(K, M, k: int, sigma: float) -> EigenResult:
    """The ``k`` eigenpairs of ``K φ = ω² M φ`` with ``ω²`` nearest ``sigma``, ascending; ``M``-normalised.

    ``K - sigma M`` is factorised once (SuperLU); it may be indefinite, so a
    shift inside the spectrum (the bottom of a frequency window) is fine.
    """
    import numpy as np
    import scipy.sparse.linalg as spla

    n = K.shape[0]
    if n < DENSE_BELOW or k >= n // 3:
        found = _dense(K, M, n, "SA")
        order = np.argsort(np.abs(found.values - sigma))[:k]
        order = order[np.argsort(found.values[order])]
        return EigenResult(found.values[order], found.vectors[:, order], "dense")
    # A fixed start, so a run repeats exactly (ARPACK's own is random).
    values, vectors = spla.eigsh(K, k=k, M=M, sigma=sigma, which="LM", ncv=min(n, max(2 * k + 1, 20)),
                                 v0=np.random.default_rng(0).standard_normal(n))
    order = np.argsort(values)
    return EigenResult(values[order], _normalised(vectors[:, order], M), "arpack shift-invert (superlu)")
