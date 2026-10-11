"""Density-based topology optimisation (SIMP) on a linear tetrahedral design mesh, in-house.

The numerics behind ``analysis: "topology"`` ("Lighten it"):

- **Element stiffness.** Every linear (4-node) tetrahedron's 12 x 12 stiffness at the full material,
  ``vol B^T D B``, computed once (:func:`tet_stiffness`); an iteration scales each by its density's
  stiffness, SIMP's ``E(rho) = Emin + rho^p (E - Emin)``, and assembles in one COO pass.
- **The density filter.** A Helmholtz PDE filter (Lazarov and Sigmund 2011) on the mesh's nodes:
  ``(r^2 grad.grad + 1) rho_f = rho`` with ``r = r_min / (2 sqrt 3)``, factorised once
  (:class:`HelmholtzFilter`). Element values are the mean of their four nodes.
- **Projection.** A smoothed Heaviside step at ``eta`` with sharpness ``beta`` (Wang, Lazarov and Sigmund
  2011), stepped up by continuation so the design ends nearly 0/1.
- **The update.** Optimality Criteria with a move limit; its Lagrange multiplier is found by bisection on
  the volume of the *projected* design, so the final volume is the target.
- **Manufacturing and symmetry constraints.** Mirror pairs and extrusion columns: sensitivities and
  densities averaged over each group (:class:`DesignMap`), so the design is symmetric or prismatic.
- **Solving.** SuperLU for small systems; otherwise AMG-preconditioned CG warm-started from the last
  displacement, the hierarchy reused while it still converges quickly (the ladder's ``iterative`` rung).

Plus the outputs: the iso-surface of the final design at rho = 0.5 by marching tetrahedra, closed by the
part's own surface where the design is solid (:func:`iso_surface`), Taubin smoothing (:func:`smooth`),
and a binary STL writer (:func:`write_stl`). Numeric imports live inside the functions.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

__all__ = [
    "DesignMap", "EMIN", "HelmholtzFilter", "History", "Schedule", "TopologyProblem", "filter_radius", "heaviside",
    "evaluate", "heaviside_slope", "iso_surface", "optimise", "smooth", "tet_geometry", "tet_stiffness", "write_stl",
]

#: The void's stiffness as a share of the material's: soft enough to be nothing, stiff enough to solve.
EMIN = 1e-6
#: The projection's threshold: the design is solid above it.
ETA = 0.5
#: Below this many free DOF the direct solver wins.
DIRECT_BELOW = 20_000


# -- elements --------------------------------------------------------------------------------------------


def tet_geometry(points: "np.ndarray", tets: "np.ndarray"):
    """Each linear tetrahedron's volume (E,) and shape-function gradients (E, 4, 3)."""
    import numpy as np

    corners = points[tets]                                       # (E, 4, 3)
    A = np.concatenate([np.ones((len(tets), 4, 1)), corners], axis=2)
    det = np.linalg.det(A)
    inverse = np.linalg.inv(A)                                   # columns are the shape functions' coefficients
    gradients = np.transpose(inverse[:, 1:4, :], (0, 2, 1))      # (E, 4 nodes, 3)
    return np.abs(det) / 6.0, gradients


def strain_matrix(gradients: "np.ndarray") -> "np.ndarray":
    """(E, 6, 12) Voigt strain (11, 22, 33, 23, 13, 12; engineering shear) of the 12 local DOF (node-major)."""
    import numpy as np

    E = len(gradients)
    B = np.zeros((E, 6, 12))
    for a in range(4):
        gx, gy, gz = gradients[:, a, 0], gradients[:, a, 1], gradients[:, a, 2]
        c = 3 * a
        B[:, 0, c] = gx
        B[:, 1, c + 1] = gy
        B[:, 2, c + 2] = gz
        B[:, 3, c + 1], B[:, 3, c + 2] = gz, gy
        B[:, 4, c], B[:, 4, c + 2] = gz, gx
        B[:, 5, c], B[:, 5, c + 1] = gy, gx
    return B


def tet_stiffness(points: "np.ndarray", tets: "np.ndarray", D: "np.ndarray"):
    """Each tetrahedron's full-material stiffness (E, 12, 12), its volume (E,) and shape gradients (E, 4, 3)."""
    import numpy as np

    volume, gradients = tet_geometry(points, tets)
    B = strain_matrix(gradients)
    Ke = np.einsum("e,eki,kl,elj->eij", volume, B, D, B, optimize=True)
    return Ke, volume, gradients


# -- the filter and the projection ------------------------------------------------------------------------


def filter_radius(min_member_mm: float) -> float:
    """The Helmholtz filter's length r for a minimum member of this size: a classic filter of radius
    r_min = min_member / 2 is matched by r = r_min / (2 sqrt 3) (Lazarov and Sigmund 2011)."""
    return 0.5 * min_member_mm / (2.0 * math.sqrt(3.0))


class HelmholtzFilter:
    """``rho_f = A (r^2 K + M)^-1 T rho``: element densities to smoothed element densities through the nodes."""

    def __init__(self, tets: "np.ndarray", volume: "np.ndarray", gradients: "np.ndarray", nodes: int, radius: float):
        import numpy as np
        import scipy.sparse as sparse
        import scipy.sparse.linalg as spla

        E = len(tets)
        rows = np.repeat(tets, 4, axis=1).ravel()
        cols = np.tile(tets, (1, 4)).ravel()
        laplace = np.einsum("e,eak,ebk->eab", volume, gradients, gradients)
        mass = (volume / 20.0)[:, None, None] * (np.ones((4, 4)) + np.eye(4))[None]
        matrix = sparse.coo_matrix(((radius ** 2 * laplace + mass).ravel(), (rows, cols)), shape=(nodes, nodes)).tocsc()
        self._lu = spla.splu(matrix)
        #: (N, E): an element's density as a nodal load, ∫ rho psi = rho vol / 4 on each corner.
        self.T = sparse.coo_matrix((np.repeat(volume / 4.0, 4), (tets.ravel(), np.repeat(np.arange(E), 4))),
                                   shape=(nodes, E)).tocsr()
        #: (E, N): an element's value as the mean of its corners.
        self.A = sparse.coo_matrix((np.full(4 * E, 0.25), (np.repeat(np.arange(E), 4), tets.ravel())),
                                   shape=(E, nodes)).tocsr()

    def nodal(self, rho: "np.ndarray") -> "np.ndarray":
        return self._lu.solve(self.T @ rho)

    def apply(self, rho: "np.ndarray") -> tuple["np.ndarray", "np.ndarray"]:
        """(nodal, element) filtered densities."""
        nodal = self.nodal(rho)
        return nodal, self.A @ nodal

    def adjoint(self, element_gradient: "np.ndarray") -> "np.ndarray":
        """d/d rho of a function whose gradient on the filtered element densities is given (the filter is symmetric)."""
        return self.T.T @ self._lu.solve(self.A.T @ element_gradient)


def heaviside(x: "np.ndarray", beta: float, eta: float = ETA) -> "np.ndarray":
    import numpy as np

    return (np.tanh(beta * eta) + np.tanh(beta * (x - eta))) / (np.tanh(beta * eta) + np.tanh(beta * (1.0 - eta)))


def heaviside_slope(x: "np.ndarray", beta: float, eta: float = ETA) -> "np.ndarray":
    import numpy as np

    return beta * (1.0 - np.tanh(beta * (x - eta)) ** 2) / (np.tanh(beta * eta) + np.tanh(beta * (1.0 - eta)))


# -- symmetry and extrusion ------------------------------------------------------------------------------


class DesignMap:
    """Groups of elements that must share one density: mirror pairs (symmetry planes) and extrusion columns.

    :meth:`apply` averages a per-element array over each group: on the sensitivities before the update and
    on the densities after it, so the design stays symmetric or prismatic. Empty: the identity."""

    def __init__(self, count: int):
        self.count = count
        self._steps: list[tuple[str, Any]] = []

    @property
    def active(self) -> bool:
        return bool(self._steps)

    def add_mirror(self, centroids: "np.ndarray", axis: int, offset: float, size: float) -> float:
        """Pair each element with the one nearest its mirror image about ``axis = offset``; returns the mean
        distance from a mirror image to the element it was paired with (a symmetric mesh: a small share of ``size``)."""
        import numpy as np
        from scipy.spatial import cKDTree

        mirrored = centroids.copy()
        mirrored[:, axis] = 2.0 * offset - mirrored[:, axis]
        distance, partner = cKDTree(centroids).query(mirrored)
        self._steps.append(("mirror", partner))
        return float(np.mean(distance)) / max(size, 1e-300)

    def add_extrusion(self, centroids: "np.ndarray", direction: "np.ndarray", size: float) -> int:
        """Columns of elements along ``direction``: centroids binned on the plane across it at the element size."""
        import numpy as np

        d = np.asarray(direction, dtype=float)
        d = d / np.linalg.norm(d)
        helper = np.eye(3)[int(np.argmin(np.abs(d)))]
        u = np.cross(d, helper)
        u /= np.linalg.norm(u)
        v = np.cross(d, u)
        cells = np.floor(np.stack([centroids @ u, centroids @ v], axis=1) / size).astype(np.int64)
        _, column = np.unique(cells, axis=0, return_inverse=True)
        column = column.ravel()
        self._steps.append(("columns", column))
        return int(column.max()) + 1

    def apply(self, values: "np.ndarray", weights: "np.ndarray | None" = None) -> "np.ndarray":
        import numpy as np

        out = np.asarray(values, dtype=float)
        for kind, data in self._steps:
            if kind == "mirror":
                out = 0.5 * (out + out[data])
            else:
                w = np.ones(self.count) if weights is None else weights
                sums = np.bincount(data, weights=out * w)
                totals = np.bincount(data, weights=w)
                out = sums[data] / totals[data]
        if any(kind == "columns" for kind, _ in self._steps) and any(kind == "mirror" for kind, _ in self._steps):
            for kind, data in self._steps:  # a mirror pair split over two columns: once more round
                if kind == "mirror":
                    out = 0.5 * (out + out[data])
        return out


# -- the problem and its solve ---------------------------------------------------------------------------


@dataclass
class TopologyProblem:
    """What one optimisation needs: the design mesh, the full-material element stiffness, the DOF, the loads."""

    points: "np.ndarray"              # (N, 3) mm
    tets: "np.ndarray"                # (E, 4)
    Ke: "np.ndarray"                  # (E, 12, 12) at the full material
    volume: "np.ndarray"              # (E,)
    gradients: "np.ndarray"           # (E, 4, 3)
    element_dofs: "np.ndarray"        # (E, 12) global vector DOF, node-major
    ndof: int
    loads: "np.ndarray"               # (ndof, cases)
    free: "np.ndarray"                # free DOF (in the supports' frame)
    keep: "np.ndarray"                # (E,) bool: frozen solid
    frame: Any = None                 # supports.Supports when some node is turned (a sloped roller), else None
    near_nullspace: Any = None        # (ndof, 6) rigid-body modes for AMG

    def assemble(self, scale: "np.ndarray"):
        import numpy as np
        import scipy.sparse as sparse

        rows = np.repeat(self.element_dofs, 12, axis=1).ravel()
        cols = np.tile(self.element_dofs, (1, 12)).ravel()
        data = (self.Ke * scale[:, None, None]).ravel()
        return sparse.coo_matrix((data, (rows, cols)), shape=(self.ndof, self.ndof)).tocsr()

    def energies(self, u: "np.ndarray") -> "np.ndarray":
        """Each element's u_e^T Ke u_e at the full material, summed over the load cases (columns of ``u``)."""
        import numpy as np

        ue = u[self.element_dofs]                                   # (E, 12, cases)
        return np.einsum("eic,eij,ejc->e", ue, self.Ke, ue, optimize=True)


class LinearSolver:
    """K u = F on the free DOF for a stiffness that changes a little each iteration: SuperLU for small
    systems (``method`` "direct"), else AMG-preconditioned CG warm-started from the last u, the hierarchy
    rebuilt only when CG slows down."""

    def __init__(self, problem: TopologyProblem, method: str):
        self.problem = problem
        n = len(problem.free)
        self.method = "direct" if method == "direct" or (method == "auto" and n < DIRECT_BELOW) else "iterative"
        self._previous = None
        self._ml = None
        self._fresh_iterations = None
        self.iterations = 0
        self.rebuilds = 0

    def solve(self, K) -> "np.ndarray":
        import numpy as np
        import scipy.sparse.linalg as spla

        p = self.problem
        frame = p.frame
        if frame is not None:
            K = frame.local(K)
            F = frame.local_vector(p.loads)
        else:
            F = p.loads
        Kff = K[p.free][:, p.free].tocsr()
        Ff = F[p.free]
        U = np.zeros((p.ndof, F.shape[1]))
        if self.method == "direct":
            lu = spla.splu(Kff.tocsc())
            U[p.free] = lu.solve(np.asarray(Ff))
        else:
            U[p.free] = self._iterative(Kff, np.asarray(Ff))
        return frame.global_vector(U) if frame is not None else U

    def _iterative(self, Kff, Ff):
        import numpy as np
        import pyamg
        import scipy.sparse.linalg as spla

        if self._ml is None:
            self._build(Kff)
        out = np.zeros_like(Ff)
        worst = 0
        for c in range(Ff.shape[1]):
            x0 = None if self._previous is None else self._previous[:, c]
            count = 0

            def tick(_):
                nonlocal count
                count += 1

            norm = float(np.linalg.norm(Ff[:, c])) or 1.0
            x, info = spla.cg(Kff, Ff[:, c], x0=x0, rtol=1e-8, atol=0.0, M=self._ml.aspreconditioner(cycle="V"),
                              maxiter=500, callback=tick)
            if info != 0 or float(np.linalg.norm(Ff[:, c] - Kff @ x)) > 1e-6 * norm:
                self._build(Kff)
                count = 0
                x, info = spla.cg(Kff, Ff[:, c], x0=x, rtol=1e-8, atol=0.0, M=self._ml.aspreconditioner(cycle="V"),
                                  maxiter=2000, callback=tick)
                if info != 0:
                    x = spla.spsolve(Kff.tocsc(), Ff[:, c])
            out[:, c] = x
            worst = max(worst, count)
        self.iterations += worst
        if self._fresh_iterations is None:
            self._fresh_iterations = max(worst, 1)
        elif worst > 2 * self._fresh_iterations + 10:
            self._ml = None  # stale: the next solve builds a hierarchy for the design as it is now
        self._previous = out
        _ = pyamg
        return out

    def _build(self, Kff):
        import pyamg

        p = self.problem
        B = None if p.near_nullspace is None else p.near_nullspace[p.free]
        self._ml = pyamg.smoothed_aggregation_solver(Kff, B=B, symmetry="symmetric", strength="symmetric", smooth="energy",
                                                     max_coarse=500)
        self._fresh_iterations = None
        self.rebuilds += 1


# -- the optimisation ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Schedule:
    """The continuation: the penalty climbs from 1 to ``penalty`` (stiffness of grey material falls), then the
    projection sharpens (``betas``); each stage runs until its design changes less than ``tolerance`` or
    ``per_stage`` iterations, the last until converged or ``max_iterations`` in all."""

    penalty: float = 3.0
    betas: tuple[float, ...] = (1.0, 2.0, 4.0, 8.0, 16.0)
    per_stage: int | None = None      # None: the iterations shared out, the last stage taking twice a share and the rest
    max_iterations: int = 200
    tolerance: float = 0.01
    move: float = 0.2

    def stages(self) -> list[tuple[float, float]]:
        penalties = [p for p in (1.0, 2.0) if p < self.penalty] + [self.penalty]
        stages = [(p, self.betas[0]) for p in penalties]
        stages += [(self.penalty, beta) for beta in self.betas[1:]]
        return stages


@dataclass
class History:
    """What the optimisation did, iteration by iteration (the curves and the frames)."""

    compliance: list[float] = field(default_factory=list)       # N mm, at each iteration's design (penalised)
    volume: list[float] = field(default_factory=list)           # projected volume fraction
    change: list[float] = field(default_factory=list)
    penalty: list[float] = field(default_factory=list)
    beta: list[float] = field(default_factory=list)
    grey: list[float] = field(default_factory=list)             # 4 Σ rho(1-rho) vol / V: 0 for a crisp 0/1 design
    frames: dict[int, "np.ndarray"] = field(default_factory=dict)  # iteration -> nodal projected density (float32)
    final_stage_start: int = 0
    converged: bool = False
    seconds: float = 0.0
    solver: str = ""
    final_nodal: Any = None                                     # the final design's nodal projected density


def evaluate(problem: TopologyProblem, filt: HelmholtzFilter, solver: "LinearSolver", x: "np.ndarray", penalty: float,
             beta: float):
    """The compliance of design ``x`` (summed over the load cases) and its gradient, and the volume fraction's
    gradient, both with respect to the design variables through the projection and the filter. Returns
    (compliance, dc/dx, dV/dx, nodal filtered density, projected element density)."""
    p = problem
    nodal, element = filt.apply(x)
    projected = heaviside(element, beta)
    projected[p.keep] = 1.0
    stiffness = EMIN + projected ** penalty * (1.0 - EMIN)
    U = solver.solve(p.assemble(stiffness))
    energy = p.energies(U)
    compliance = float((stiffness * energy).sum())
    d_projected = -penalty * projected ** (penalty - 1.0) * (1.0 - EMIN) * energy
    d_projected[p.keep] = 0.0
    slope = heaviside_slope(element, beta)
    dc = filt.adjoint(d_projected * slope)
    dv = filt.adjoint(p.volume / float(p.volume.sum()) * slope * (~p.keep))
    return compliance, dc, dv, nodal, projected


def optimise(problem: TopologyProblem, target: float, schedule: Schedule, *, radius: float, design_map: DesignMap,
             method: str = "auto", start: "np.ndarray | None" = None, keep_frames: int = 24,
             log: Callable[[str], None] | None = None) -> tuple["np.ndarray", "np.ndarray", History, LinearSolver]:
    """Minimum compliance at volume fraction ``target`` (of the whole design domain, the kept elements included).

    Returns (design variables, projected element densities, history, the solver used). ``start`` warm-starts
    the design (``lightest``'s next volume)."""
    import numpy as np

    started = time.perf_counter()
    p = problem
    E = len(p.tets)
    total = float(p.volume.sum())
    share = p.volume / total
    filt = HelmholtzFilter(p.tets, p.volume, p.gradients, len(p.points), radius)
    solver = LinearSolver(p, method)
    keep = p.keep
    x = np.full(E, target) if start is None else np.clip(np.asarray(start, dtype=float), 0.0, 1.0)
    x[keep] = 1.0
    x = design_map.apply(x, p.volume)
    x[keep] = 1.0
    history = History()

    def physical(design, beta):
        nodal, element = filt.apply(design)
        projected = heaviside(element, beta)
        projected[keep] = 1.0
        return nodal, element, projected

    def nodal_frame(nodal, beta):
        values = heaviside(np.clip(nodal, 0.0, 1.0), beta)
        values[np.unique(p.tets[keep])] = 1.0
        return values.astype(np.float32)

    stages = schedule.stages()
    per_stage = schedule.per_stage or max(4, schedule.max_iterations // (len(stages) + 2))
    iteration = 0
    stride = 1
    for index, (penalty, beta) in enumerate(stages):
        last = index == len(stages) - 1
        if last:
            history.final_stage_start = iteration
        # A sharper projection takes smaller steps: OC overshoots where a small change in rho moves the projection a lot.
        move = schedule.move if beta <= 2 else max(0.05, schedule.move / math.sqrt(beta / 2.0))
        in_stage = 0
        while True:
            if iteration >= schedule.max_iterations:
                break
            compliance, dc, dv, nodal, projected = evaluate(p, filt, solver, x, penalty, beta)
            dc = design_map.apply(dc)
            dv = design_map.apply(dv)
            dc = np.minimum(dc, 0.0)
            dv = np.maximum(dv, 1e-30)
            scale = max(float(-dc.min()), 1e-300)
            low, high = x - move, x + move

            def update(lam):
                factor = np.sqrt(-dc / scale / (lam * dv))
                new = np.clip(np.clip(x * factor, low, high), 0.0, 1.0)
                new[keep] = 1.0
                new = design_map.apply(new, p.volume)
                new[keep] = 1.0
                return new

            def volume_of(design):
                return float(share @ physical(design, beta)[2])

            l1, l2 = 1e-9, 1e9
            new = x
            for _ in range(80):
                mid = math.sqrt(l1 * l2)
                new = update(mid)
                if volume_of(new) > target:
                    l1 = mid
                else:
                    l2 = mid
                if l2 / l1 < 1.0 + 1e-6:
                    break
            change = float(np.abs(new - x).max())
            x = new
            iteration += 1
            in_stage += 1
            history.compliance.append(compliance)
            history.volume.append(float(share @ projected))
            history.change.append(change)
            history.penalty.append(penalty)
            history.beta.append(beta)
            history.grey.append(float(4.0 * (share * projected * (1.0 - projected)).sum()))
            if iteration % stride == 0:
                history.frames[iteration] = nodal_frame(nodal, beta)
                if len(history.frames) > 2 * keep_frames:
                    stride *= 2
                    history.frames = {k: v for k, v in history.frames.items() if k % stride == 0}
            if log and (iteration % 10 == 0 or iteration == 1):
                log(f"topology iteration {iteration}: compliance {compliance:.6g} N mm, volume {history.volume[-1]:.4f}, "
                    f"change {change:.3f}, p {penalty:g}, beta {beta:g}")
            if not last:
                if change < 2.0 * schedule.tolerance or in_stage >= per_stage:
                    break
                continue
            # Settled: the design barely moves, or the compliance has held within 0.1 % for five iterations while
            # only a few elements still flip (OC at a sharp projection keeps nudging single elements).
            recent = history.compliance[-5:]
            steady = in_stage >= 5 and (max(recent) - min(recent)) <= 1e-3 * recent[-1]
            if (change < schedule.tolerance and in_stage >= 3) or (steady and change < 10.0 * schedule.tolerance):
                history.converged = True
                break
        if iteration >= schedule.max_iterations:
            if not last:
                history.final_stage_start = iteration
            break
    # The design as it ends: its own state, analysed once more so the last compliance is the final design's.
    penalty, beta = stages[-1]
    nodal, element, projected = physical(x, beta)
    stiffness = EMIN + projected ** penalty * (1.0 - EMIN)
    U = solver.solve(p.assemble(stiffness))
    history.compliance.append(float((stiffness * p.energies(U)).sum()))
    history.volume.append(float(share @ projected))
    history.change.append(0.0)
    history.penalty.append(penalty)
    history.beta.append(beta)
    history.grey.append(float(4.0 * (share * projected * (1.0 - projected)).sum()))
    history.frames[iteration + 1] = nodal_frame(nodal, beta)
    history.final_nodal = nodal_frame(nodal, beta)
    history.seconds = time.perf_counter() - started
    history.solver = ("superlu" if solver.method == "direct"
                      else f"amg+cg, warm-started ({solver.iterations} CG iterations, {solver.rebuilds} AMG builds)")
    return x, projected, history, solver


def frames_to_keep(history: History, count: int) -> list[int]:
    """At most ``count`` iterations of the recorded frames, spread evenly, the last always among them."""
    keys = sorted(history.frames)
    if len(keys) <= count:
        return keys
    import numpy as np

    picks = np.unique(np.round(np.linspace(0, len(keys) - 1, count)).astype(int))
    return [keys[i] for i in picks]


# -- the design's surface --------------------------------------------------------------------------------

_TET_FACES = ((1, 2, 3), (0, 3, 2), (0, 1, 3), (0, 2, 1))


def iso_surface(points: "np.ndarray", tets: "np.ndarray", values: "np.ndarray", boundary: "np.ndarray",
                level: float = 0.5):
    """The closed surface of ``values >= level``: marching tetrahedra inside, the part's own boundary triangles
    clipped where the design is solid. Returns (vertices (V, 3), triangles (T, 3), fixed (V,) bool: on the
    part's boundary), triangles wound outward."""
    import numpy as np

    n = len(points)
    v = np.asarray(values, dtype=float)
    # A node exactly at the level would put the surface through it twice (a cap node and an edge point): nudge it in.
    v = np.where(np.abs(v - level) <= 1e-12, level + 1e-9, v)
    corners = tets[:, :4]
    inside = v[corners] >= level
    count = inside.sum(axis=1)
    keys: list[np.ndarray] = []
    tris: list[np.ndarray] = []
    outward: list[np.ndarray] = []

    def edge_key(a, b):
        lo, hi = np.minimum(a, b), np.maximum(a, b)
        return n + lo * n + hi

    _, gradients = tet_geometry(points, corners)
    grad = np.einsum("ea,eak->ek", v[corners], gradients)

    # One inside or one outside corner: a triangle across the three edges at that corner.
    for k in (1, 3):
        rows = np.flatnonzero(count == k)
        if not len(rows):
            continue
        lone = np.argmax(inside[rows] if k == 1 else ~inside[rows], axis=1)
        others = np.array([[j for j in range(4) if j != i] for i in range(4)])[lone]
        a = corners[rows, lone]
        b = corners[rows[:, None], others]
        tris.append(np.stack([edge_key(a, b[:, j]) for j in range(3)], axis=1))
        outward.append(-grad[rows])
    # Two inside, two outside: a quad, two triangles.
    rows = np.flatnonzero(count == 2)
    if len(rows):
        order = np.argsort(~inside[rows], axis=1, kind="stable")  # inside first
        a, b, c, d = (corners[rows, order[:, j]] for j in range(4))
        ac, ad, bd, bc = edge_key(a, c), edge_key(a, d), edge_key(b, d), edge_key(b, c)
        tris.append(np.stack([ac, ad, bd], axis=1))
        tris.append(np.stack([ac, bd, bc], axis=1))
        outward += [-grad[rows], -grad[rows]]

    # The part's own surface where the design is solid, clipped at the level.
    surface = boundary[:, :3]
    tri_in = v[surface] >= level
    k = tri_in.sum(axis=1)
    normal_out = _boundary_outward(points, corners, surface)
    full = np.flatnonzero(k == 3)
    tris.append(surface[full])
    outward.append(normal_out[full])
    rows = np.flatnonzero(k == 1)
    if len(rows):
        lone = np.argmax(tri_in[rows], axis=1)
        a = surface[rows, lone]
        b = surface[rows, (lone + 1) % 3]
        c = surface[rows, (lone + 2) % 3]
        tris.append(np.stack([a, edge_key(a, b), edge_key(a, c)], axis=1))
        outward.append(normal_out[rows])
    rows = np.flatnonzero(k == 2)
    if len(rows):
        out = np.argmin(tri_in[rows], axis=1)
        c = surface[rows, out]
        a = surface[rows, (out + 1) % 3]
        b = surface[rows, (out + 2) % 3]
        tris.append(np.stack([a, b, edge_key(b, c)], axis=1))
        tris.append(np.stack([a, edge_key(b, c), edge_key(a, c)], axis=1))
        outward += [normal_out[rows], normal_out[rows]]
    if not tris:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), np.zeros(0, dtype=bool)
    triangles = np.concatenate(tris)
    wanted = np.concatenate(outward)
    unique, inverse = np.unique(triangles.ravel(), return_inverse=True)
    triangles = inverse.reshape(-1, 3)
    vertices = np.zeros((len(unique), 3))
    nodes = unique < n
    vertices[nodes] = points[unique[nodes]]
    edges = unique[~nodes] - n
    lo, hi = edges // n, edges % n
    t = (level - v[lo]) / np.where(np.abs(v[hi] - v[lo]) > 1e-12, v[hi] - v[lo], 1e-12)
    t = np.clip(t, 0.0, 1.0)
    vertices[~nodes] = points[lo] + t[:, None] * (points[hi] - points[lo])
    on_boundary = np.zeros(n, dtype=bool)
    on_boundary[surface.ravel()] = True
    fixed = np.zeros(len(unique), dtype=bool)
    fixed[nodes] = True
    # On the part's surface: a point on one of its edges, or one that falls on a surface node (a node at the level).
    fixed[~nodes] = ((on_boundary[lo] & on_boundary[hi] & _boundary_edge(surface, lo, hi, n))
                     | ((t <= 1e-6) & on_boundary[lo]) | ((t >= 1.0 - 1e-6) & on_boundary[hi]))
    # Wind each triangle outward.
    e1 = vertices[triangles[:, 1]] - vertices[triangles[:, 0]]
    e2 = vertices[triangles[:, 2]] - vertices[triangles[:, 0]]
    normals = np.cross(e1, e2)
    flip = np.einsum("ij,ij->i", normals, wanted) < 0
    triangles[flip] = triangles[flip][:, [0, 2, 1]]
    area = 0.5 * np.linalg.norm(normals, axis=1)
    keep = area > 1e-14 * max(float(area.max()), 1e-300)
    return vertices, triangles[keep], fixed


def _boundary_edge(surface, lo, hi, n) -> "np.ndarray":
    import numpy as np

    pairs = np.concatenate([surface[:, [0, 1]], surface[:, [1, 2]], surface[:, [0, 2]]])
    a, b = np.minimum(pairs[:, 0], pairs[:, 1]), np.maximum(pairs[:, 0], pairs[:, 1])
    known = np.unique(a.astype(np.int64) * n + b)
    return np.isin(np.minimum(lo, hi).astype(np.int64) * n + np.maximum(lo, hi), known)


def _boundary_outward(points, corners, surface) -> "np.ndarray":
    """The outward normal (unnormalised) of each boundary triangle: away from its tetrahedron's fourth corner."""
    import numpy as np

    n = len(points)
    faces = np.concatenate([corners[:, list(f)] for f in _TET_FACES])
    opposite = np.concatenate([corners[:, i] for i in range(4)])
    s = np.sort(faces, axis=1).astype(np.int64)
    key = (s[:, 0] * n + s[:, 1]) * n + s[:, 2]
    order = np.argsort(key)
    sk = np.sort(surface, axis=1).astype(np.int64)
    want = (sk[:, 0] * n + sk[:, 1]) * n + sk[:, 2]
    where = order[np.clip(np.searchsorted(key[order], want), 0, len(key) - 1)]
    p0, p1, p2 = points[surface[:, 0]], points[surface[:, 1]], points[surface[:, 2]]
    normal = np.cross(p1 - p0, p2 - p0)
    inward = points[opposite[where]] - p0
    flip = np.einsum("ij,ij->i", normal, inward) > 0
    normal[flip] *= -1.0
    return normal


def smooth(vertices: "np.ndarray", triangles: "np.ndarray", fixed: "np.ndarray", *, rounds: int = 10,
           lam: float = 0.5, mu: float = -0.53) -> "np.ndarray":
    """Taubin's lambda/mu smoothing (no shrinking) of the free vertices; ``fixed`` ones (on the part's own
    surface) stay where they are, so the design keeps the faces it shares with the part."""
    import numpy as np
    import scipy.sparse as sparse

    if not len(triangles):
        return vertices
    m = len(vertices)
    a = np.concatenate([triangles[:, 0], triangles[:, 1], triangles[:, 2]])
    b = np.concatenate([triangles[:, 1], triangles[:, 2], triangles[:, 0]])
    adjacency = sparse.coo_matrix((np.ones(2 * len(a)), (np.concatenate([a, b]), np.concatenate([b, a]))), shape=(m, m)).tocsr()
    adjacency.data[:] = 1.0
    degree = np.asarray(adjacency.sum(axis=1)).ravel()
    degree[degree == 0] = 1.0
    out = vertices.copy()
    free = ~fixed
    for _ in range(rounds):
        for factor in (lam, mu):
            delta = (adjacency @ out) / degree[:, None] - out
            out[free] += factor * delta[free]
    return out


def write_stl(path: Path, vertices: "np.ndarray", triangles: "np.ndarray", name: str = "cadgen topology") -> None:
    """A binary STL of the triangles (mm)."""
    import numpy as np

    p = vertices[triangles]
    normals = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    length = np.linalg.norm(normals, axis=1)
    normals = normals / np.where(length > 0, length, 1.0)[:, None]
    record = np.zeros(len(triangles), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    record["n"] = normals
    record["v"] = p
    header = name.encode("ascii", "replace")[:80].ljust(80, b" ")
    with open(path, "wb") as handle:
        handle.write(header)
        handle.write(np.uint32(len(triangles)).tobytes())
        handle.write(record.tobytes())


def enclosed_volume(vertices: "np.ndarray", triangles: "np.ndarray") -> float:
    """The volume a closed, outward-wound triangle surface encloses (mm^3)."""
    import numpy as np

    p = vertices[triangles]
    return float(np.einsum("ij,ij->i", p[:, 0], np.cross(p[:, 1], p[:, 2])).sum() / 6.0)
