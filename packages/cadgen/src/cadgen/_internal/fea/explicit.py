"""Explicit dynamics for a part dropped onto a rigid floor: central difference on linear tets.

The part is meshed with constant-strain (4-node) tetrahedra. Each element's
shape-function gradients (its B matrix) and volume are computed once and kept
as arrays over every element, so the internal force is a handful of numpy
products per chunk of elements (:data:`CHUNK_ELEMENTS`, which keeps memory
bounded): no stiffness matrix is assembled or stored. The mass is lumped
(row-sum: a quarter of each element's mass on each of its corners), so the
central-difference update is a division per node:

    v(n+1/2) = v(n-1/2) + dt (f_ext - f_int(u(n))) / m,    u(n+1) = u(n) + dt v(n+1/2).

**Stable step.** Each element alone is stable below 2 / ω_e, where ω_e² is the
largest eigenvalue of its lumped-mass stiffness (computed for every element,
batched). That is its characteristic length over its dilatational wave speed,
l_e / c_d, and by Irons' element eigenvalue bound the whole mesh is stable below
the smallest of them: dt = 0.9 · min(l_e / c_d).

**The floor.** A rigid plane through the part's lowest point along the drop
direction, met at t = 0 with every node moving at the impact speed
v = √(2 g h). A boundary node that passes it is pushed back by a penalty spring
k_p = 10 E A_node / h_min (``A_node`` its share of the surface, ``h_min`` the
smallest characteristic length of the elements at that node), taken implicitly along the floor's normal
(the spring's own stiffness then never limits the step). Optional regularised
Coulomb friction acts along the floor, never more than stops the node's sliding
in one step.

**Plasticity.** Optional bilinear J2 (von Mises yield, linear isotropic
hardening of plastic modulus H = E Et / (E - Et)) by radial return per element.

**Fitting the budget** (the ladder rungs this module carries out):
- *window*: stop when the first contact pulse ends, plus 20 % of it;
- *subcycling*: the elements with a small stable step (and their neighbours)
  are integrated at dt, the rest at n dt (a nodal partition after Belytschko,
  Yen and Mullen; the coarse nodes' displacement is interpolated linearly
  through the substeps);
- *mass scaling*: the smallest elements are made heavier until their stable
  step reaches a target, capped at a share of the part's mass (5 %).

Numeric imports live inside the functions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    import numpy as np

__all__ = [
    "CHUNK_ELEMENTS", "Drop", "MASS_SCALE_CAP", "Model", "Plastic", "Run", "SAFETY", "build_model", "mass_scaling",
    "max_mass_scaling", "simulate", "subcycle_partition", "best_subcycle",
]

#: Elements per chunk of the force loop (a chunk's temporaries: about 1 kB an element).
CHUNK_ELEMENTS = 20_000
#: The step is this share of the smallest element's stable step.
SAFETY = 0.9
#: The floor's penalty: k_p = PENALTY_FACTOR · E · A_node / h_min.
PENALTY_FACTOR = 10.0
#: Mass scaling never adds more than this share of the part's mass.
MASS_SCALE_CAP = 0.05
#: The floor's spring is damped at this share of its critical damping, so a node that lands stays down rather than
#: bouncing on the spring (contact damping, as explicit codes add).
CONTACT_DAMPING = 0.2
#: The window rung stops this share of the first pulse after it ends.
WINDOW_TAIL = 0.2
#: The first pulse has ended when the floor pushes with less than this share of its peak.
PULSE_END_SHARE = 0.01
#: ... once the part's centre of mass moves toward the floor at no more than this share of the impact speed.
STOPPED_SHARE = 0.05
#: Subcycling: at most this many substeps per step, and taken only when it saves this share of the work.
MAX_SUBCYCLE, SUBCYCLE_SAVING = 16, 0.2
#: Regularised Coulomb friction: sliding slower than this share of the impact speed is resisted in proportion.
FRICTION_REGULARISATION = 1e-3
#: Linear bulk viscosity (a share of critical damping in the highest mode): damps the ringing a sharp wave front
#: makes in a coarse mesh, as every explicit code does; inside the step's 0.9 safety.
BULK_VISCOSITY = 0.06
#: The reported stress and floor push are low-pass filtered (first order) with a time constant of this many element
#: transits (l_e / c_d, the median by volume, unscaled): ringing faster than that is the mesh's, not the part's, like a crash test's channel filter.
FILTER_TRANSITS = 4.0
#: Mass-scaling bisection.
_BISECTIONS = 40


# -- the model ---------------------------------------------------------------------------------------


@dataclass
class Model:
    """A linear tet mesh's precomputed element arrays, lumped mass and floor-contact data."""

    nodes: "np.ndarray"            # (N, 3) mm
    tets: "np.ndarray"             # (E, 4) corner node ids
    grads: "np.ndarray"            # (E, 4, 3) shape-function gradients, 1/mm
    volume: "np.ndarray"           # (E,) mm^3
    lam: "np.ndarray"              # (E,) Lamé λ, MPa
    mu: "np.ndarray"               # (E,) shear modulus, MPa
    rho: "np.ndarray"              # (E,) t/mm^3
    youngs: "np.ndarray"           # (E,) MPa
    #: (E,) each element's own stable step, s (2 / ω_e with its lumped mass).
    element_dt: "np.ndarray"
    #: (E,) dilatational wave speed, mm/s.
    wave_speed: "np.ndarray"
    #: (B, 3) boundary triangles, node ids.
    boundary: "np.ndarray"
    #: (N,) each node's share of the boundary area, mm^2 (0 inside).
    node_area: "np.ndarray"
    #: Node-from-element averaging (N x E sparse, rows sum to 1, volume-weighted).
    averaging: Any

    @property
    def count(self) -> int:
        return int(len(self.nodes))

    @property
    def elements(self) -> int:
        return int(len(self.tets))

    @property
    def lengths(self) -> "np.ndarray":
        """(E,) characteristic lengths l_e = c_d · dt_e, mm."""
        return self.element_dt * self.wave_speed

    def node_mass(self, added_rho: "np.ndarray | None" = None) -> "np.ndarray":
        """Lumped (row-sum) mass: a quarter of each element's mass on each corner, tonne."""
        import numpy as np

        rho = self.rho if added_rho is None else self.rho + added_rho
        share = np.repeat(rho * self.volume / 4.0, 4)
        return np.bincount(self.tets.ravel(), weights=share, minlength=self.count)

    def nodal(self, element_values: "np.ndarray") -> "np.ndarray":
        """Element values averaged to the nodes, weighted by volume."""
        return self.averaging @ element_values


def _gradients(nodes: "np.ndarray", tets: "np.ndarray"):
    """Shape-function gradients (E, 4, 3) and volumes (E,) of linear tets."""
    import numpy as np

    x = nodes[tets]                                    # (E, 4, 3)
    J = np.stack([x[:, 1] - x[:, 0], x[:, 2] - x[:, 0], x[:, 3] - x[:, 0]], axis=2)  # columns are edges
    det = np.linalg.det(J)
    inv = np.linalg.inv(J)                             # rows: gradients of N1, N2, N3
    grads = np.empty((len(tets), 4, 3))
    grads[:, 1:] = inv
    grads[:, 0] = -inv.sum(axis=1)
    return grads, np.abs(det) / 6.0


def _element_dt(grads, volume, lam, mu, rho, chunk: int) -> "np.ndarray":
    """Each element's stable step 2 / sqrt(λ_max(M_e⁻¹ K_e)), with its lumped mass ρ V / 4 per corner."""
    import numpy as np

    out = np.empty(len(volume))
    eye = np.eye(3)
    for start in range(0, len(volume), chunk):
        s = slice(start, start + chunk)
        g = grads[s]                                   # (e, 4, 3)
        # K_e[a i, b j] = V (λ g_ai g_bj + μ (δ_ij g_a·g_b + g_aj g_bi))
        dots = np.einsum("eak,ebk->eab", g, g)
        K = (lam[s, None, None, None, None] * np.einsum("eai,ebj->eaibj", g, g)
             + mu[s, None, None, None, None] * (np.einsum("eab,ij->eaibj", dots, eye) + np.einsum("eaj,ebi->eaibj", g, g)))
        K = K.reshape(-1, 12, 12) * volume[s, None, None]
        top = np.linalg.eigvalsh(K)[:, -1]
        omega2 = top / (rho[s] * volume[s] / 4.0)
        out[s] = 2.0 / np.sqrt(np.maximum(omega2, 1e-300))
    return out


def build_model(nodes, tets, boundary, *, youngs, poisson, density, chunk: int = CHUNK_ELEMENTS) -> Model:
    """The element arrays of a linear tet mesh. ``youngs``, ``poisson``, ``density``: a number, or one per element."""
    import numpy as np
    import scipy.sparse as sparse

    nodes = np.ascontiguousarray(nodes, dtype=float)
    tets = np.ascontiguousarray(tets[:, :4], dtype=np.int64)
    count, elements = len(nodes), len(tets)
    E = np.broadcast_to(np.asarray(youngs, dtype=float), (elements,)).copy()
    nu = np.broadcast_to(np.asarray(poisson, dtype=float), (elements,)).copy()
    rho = np.broadcast_to(np.asarray(density, dtype=float), (elements,)).copy()
    lam = E * nu / ((1 + nu) * (1 - 2 * nu))
    mu = E / (2 * (1 + nu))
    grads, volume = _gradients(nodes, tets)
    element_dt = _element_dt(grads, volume, lam, mu, rho, chunk)
    wave_speed = np.sqrt((lam + 2 * mu) / rho)
    boundary = np.ascontiguousarray(boundary[:, :3], dtype=np.int64)
    a, b, c = (nodes[boundary[:, i]] for i in range(3))
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    node_area = np.bincount(boundary.ravel(), weights=np.repeat(area / 3.0, 3), minlength=count)
    weights = np.repeat(volume, 4)
    incidence = sparse.csr_matrix((weights, (tets.ravel(), np.repeat(np.arange(elements), 4))), shape=(count, elements))
    totals = np.asarray(incidence.sum(axis=1)).ravel()
    averaging = sparse.diags(1.0 / np.where(totals > 0, totals, 1.0)) @ incidence
    return Model(nodes, tets, grads, volume, lam, mu, rho, E, element_dt, wave_speed, boundary, node_area,
                 averaging.tocsr())


# -- mass scaling and subcycling --------------------------------------------------------------------


def mass_scaling(model: Model, target_dt: float) -> tuple["np.ndarray", float]:
    """The density each element gains so its stable step reaches ``target_dt`` (ω ∝ 1/√ρ), and the share of the
    part's mass that adds."""
    import numpy as np

    ratio = np.maximum(target_dt / model.element_dt, 1.0)
    added = model.rho * (ratio ** 2 - 1.0)
    total = float((model.rho * model.volume).sum())
    return added, float((added * model.volume).sum()) / total


def max_mass_scaling(model: Model, cap: float = MASS_SCALE_CAP, wanted_dt: float | None = None) -> tuple[float, float]:
    """The largest element step (at most ``wanted_dt``) mass scaling reaches while adding at most ``cap`` of the mass:
    (target element step, added share)."""
    low = float(model.element_dt.min())
    high = float(model.element_dt.max()) if wanted_dt is None else max(float(wanted_dt), low)
    if mass_scaling(model, high)[1] <= cap:
        return high, mass_scaling(model, high)[1]
    for _ in range(_BISECTIONS):
        middle = 0.5 * (low + high)
        if mass_scaling(model, middle)[1] <= cap:
            low = middle
        else:
            high = middle
    return low, mass_scaling(model, low)[1]


def subcycle_partition(element_dt: "np.ndarray", tets: "np.ndarray", count: int, n: int):
    """The nodal partition for ``n`` substeps per step: (fine elements' mask, the elements touching a fine node, the fine
    nodes' mask, the step δ, the step Δ = n δ). An element whose own step is under Δ / SAFETY is fine; its nodes are fine
    nodes; every element touching a fine node is evaluated each substep."""
    import numpy as np

    small = SAFETY * float(element_dt.min())
    big = n * small
    fine = SAFETY * element_dt < big
    fine_nodes = np.zeros(count, dtype=bool)
    fine_nodes[tets[fine].ravel()] = True
    touching = fine_nodes[tets].any(axis=1)
    return fine, touching, fine_nodes, small, big


def subcycle_work(element_dt: "np.ndarray", tets: "np.ndarray", count: int, n: int) -> float:
    """The force-loop work per unit time with ``n`` substeps, as a share of every element at the smallest step."""
    _, touching, _, _, _ = subcycle_partition(element_dt, tets, count, n)
    inside = int(touching.sum())
    return (inside + (len(tets) - inside) / n) / len(tets)


def best_subcycle(element_dt: "np.ndarray", tets: "np.ndarray", count: int, max_n: int = MAX_SUBCYCLE) -> tuple[int, float]:
    """The substep count that saves the most work, and its work share; (1, 1.0) when none saves SUBCYCLE_SAVING."""
    best = (1, 1.0)
    for n in range(2, max_n + 1):
        share = subcycle_work(element_dt, tets, count, n)
        if share < best[1] - 1e-9:
            best = (n, share)
    return best if best[1] <= 1.0 - SUBCYCLE_SAVING else (1, 1.0)


# -- the run -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Drop:
    """How the part meets the floor."""

    direction: tuple[float, float, float]   # unit, the way it falls
    speed: float                            # mm/s at impact
    friction: float = 0.0                   # Coulomb coefficient along the floor
    gravity: float = 9806.65                # mm/s^2 along the fall, through the window


@dataclass(frozen=True)
class Plastic:
    """Bilinear J2: yield (MPa) and plastic modulus H (MPa), one per element or a number."""

    yield_MPa: Any
    hardening: Any


@dataclass
class Run:
    """What a simulated drop gives: frames, curves, envelopes and the numbers the summary reads."""

    frame_t: list[float]
    frame_u: list["np.ndarray"]           # (N, 3) relative to the centre of mass's travel
    frame_vm: list["np.ndarray"]          # (E,) element von Mises, MPa
    vm_peak: "np.ndarray"                 # (E,) the most each element reached
    vm_peak_t: "np.ndarray"               # (E,) when
    u_peak: "np.ndarray"                  # (N,) the largest relative displacement each node reached
    u_peak_t: "np.ndarray"
    plastic: "np.ndarray | None"          # (E,) equivalent plastic strain at the end
    curve_t: list[float]
    curve_force: list[float]              # N, the floor's push
    steps: int                            # steps of the smallest kind (substeps when subcycling)
    big_steps: int
    dt: float
    end_s: float
    planned_end_s: float
    pulse_end_s: float | None             # when the first contact pulse ended (None: still in contact)
    stopped_early: bool
    touched: "np.ndarray"                 # (N,) nodes that met the floor
    seconds: float
    #: The low-pass filter's time constant on the reported stress and force, s.
    filter_s: float = 0.0
    #: The unfiltered peaks: element von Mises (MPa) and floor push (N).
    raw_peak_vm: float = 0.0
    raw_peak_force: float = 0.0
    #: The filtered floor push's peak (N) and when (s).
    peak_force: float = 0.0
    peak_force_t: float = 0.0
    #: When the stress peaked (its frame is among the frames).
    peak_t: float | None = None
    #: Substeps per step (1: none), and the share of elements stepped at the small step.
    subcycle: int = 1
    fine_share: float = 0.0
    #: Each watched group's peak deceleration along the fall (mm/s², filtered) and when.
    watched: dict = field(default_factory=dict)
    energy: dict = field(default_factory=dict)
    #: The run went on past its planned end because the first contact pulse had not ended (``extend_to_s``).
    extended: bool = False


class _Elements:
    """A set of elements' arrays and state, evaluated chunk by chunk."""

    def __init__(self, model: Model, index, plastic: Plastic | None, chunk: int):
        import numpy as np

        self.index = np.asarray(index)
        self.tets = model.tets[self.index]
        self.grads = model.grads[self.index]
        self.volume = model.volume[self.index]
        self.lam = model.lam[self.index]
        self.mu = model.mu[self.index]
        self.count = model.count
        self.chunk = chunk
        size = len(self.index)
        self.vm = np.zeros(size)
        self.plastic = plastic is not None
        if self.plastic:
            self.yield_MPa = np.broadcast_to(np.asarray(plastic.yield_MPa, dtype=float), (model.elements,))[self.index]
            self.hardening = np.broadcast_to(np.asarray(plastic.hardening, dtype=float), (model.elements,))[self.index]
            self.eps_p = np.zeros((size, 3, 3))
            self.alpha = np.zeros(size)
        self.viscosity = BULK_VISCOSITY
        # ρ l_e c_d: the linear bulk viscosity's pressure per unit volumetric strain rate.
        self.impedance = (model.rho * model.lengths * model.wave_speed)[self.index]
        self.flat = (self.tets[:, :, None] * 3 + np.arange(3)[None, None, :]).reshape(len(self.tets), 12)

    def __len__(self) -> int:
        return len(self.index)

    def forces(self, u: "np.ndarray", v: "np.ndarray | None" = None) -> "np.ndarray":
        """The internal force (3N,) of these elements at displacement ``u`` (N, 3) and velocity ``v`` (the bulk
        viscosity's strain rate); updates their von Mises and state."""
        import numpy as np

        out = np.zeros(3 * self.count)
        eye = np.eye(3)
        for start in range(0, len(self.index), self.chunk):
            s = slice(start, start + self.chunk)
            g = self.grads[s]
            U = u[self.tets[s]]                                       # (e, 4, 3)
            H = np.einsum("eai,eaj->eij", U, g)
            strain = 0.5 * (H + H.transpose(0, 2, 1))
            trace = strain[:, 0, 0] + strain[:, 1, 1] + strain[:, 2, 2]
            lam, mu = self.lam[s], self.mu[s]
            if self.plastic:
                deviator = strain - (trace / 3.0)[:, None, None] * eye
                trial = 2.0 * mu[:, None, None] * (deviator - self.eps_p[s])
                q = np.sqrt(1.5 * np.einsum("eij,eij->e", trial, trial))
                radius = self.yield_MPa[s] + self.hardening[s] * self.alpha[s]
                over = q - radius
                yielding = over > 1e-12 * np.maximum(radius, 1.0)
                if yielding.any():
                    rows = np.flatnonzero(yielding)
                    gamma = over[rows] / (3.0 * mu[rows] + self.hardening[s][rows])
                    direction = 1.5 * trial[rows] / q[rows, None, None]
                    eps_p = self.eps_p[s]
                    eps_p[rows] += gamma[:, None, None] * direction
                    self.eps_p[s] = eps_p
                    alpha = self.alpha[s]
                    alpha[rows] += gamma
                    self.alpha[s] = alpha
                    trial[rows] *= (1.0 - 3.0 * mu[rows] * gamma / q[rows])[:, None, None]
                    q[rows] -= 3.0 * mu[rows] * gamma
                bulk = lam + 2.0 * mu / 3.0
                stress = trial + (bulk * trace)[:, None, None] * eye
                self.vm[s] = q
            else:
                stress = 2.0 * mu[:, None, None] * strain + (lam * trace)[:, None, None] * eye
                deviator = stress - (stress[:, 0, 0] + stress[:, 1, 1] + stress[:, 2, 2])[:, None, None] / 3.0 * eye
                self.vm[s] = np.sqrt(1.5 * np.einsum("eij,eij->e", deviator, deviator))
            if v is not None and self.viscosity > 0:
                rate = np.einsum("eai,eai->e", v[self.tets[s]], g)          # the volumetric strain rate
                stress = stress + (self.viscosity * self.impedance[s] * rate)[:, None, None] * eye
            fe = np.einsum("eij,eaj->eai", stress, g) * self.volume[s, None, None]
            out += np.bincount(self.flat[s].ravel(), weights=fe.ravel(), minlength=3 * self.count)
        return out


def simulate(
    model: Model,
    drop: Drop,
    *,
    end_s: float,
    stop_after_pulse: bool = False,
    subcycle: int = 1,
    added_rho: "np.ndarray | None" = None,
    plastic: Plastic | None = None,
    frames: int = 24,
    chunk: int = CHUNK_ELEMENTS,
    log: Callable[[str], None] | None = None,
    curve_points: int = 4000,
    watch: "dict[str, np.ndarray] | None" = None,
    extend_to_s: float | None = None,
) -> Run:
    """The drop, followed from first contact for ``end_s`` (or, with ``stop_after_pulse``, until the first contact pulse
    ends, plus 20 % of it). ``extend_to_s``: a window that is only a guess (the automatic one) is not ended while the
    part is still on the floor: the run goes on, up to ``extend_to_s``, until the first pulse ends, plus 20 % of it. ``frames`` snapshots, evenly spaced, plus the moment of the peak stress. ``watch``: groups of
    nodes whose mass-weighted mean acceleration along the fall is followed (filtered like the floor's push)."""
    import time

    import numpy as np

    started = time.perf_counter()
    count = model.count
    d = np.asarray(drop.direction, dtype=float)
    d = d / np.linalg.norm(d)
    element_dt = model.element_dt if added_rho is None else model.element_dt * np.sqrt((model.rho + added_rho) / model.rho)
    mass = model.node_mass(added_rho)
    physical_mass = float((model.rho * model.volume).sum())
    fine_mask, touching, fine_nodes, small, big = subcycle_partition(element_dt, model.tets, count, max(1, int(subcycle)))
    n = max(1, int(subcycle))
    if n > 1 and touching.all():
        n, big = 1, small
    if n == 1:
        sets = {"all": _Elements(model, np.arange(model.elements), plastic, chunk)}
        fine_nodes = np.zeros(count, dtype=bool)
    else:
        sets = {"coarse": _Elements(model, np.flatnonzero(~touching), plastic, chunk),
                "fine": _Elements(model, np.flatnonzero(touching), plastic, chunk)}
    coarse_nodes = ~fine_nodes

    # The floor: through the lowest point along the fall; penalty springs on the boundary nodes.
    height = model.nodes @ d
    floor = float(height.max())
    # h_min at a node: the smallest characteristic length of the elements meeting there (the floor's spring is as stiff
    # as the part's own surface layer there, ten times over, wherever the mesh is finer elsewhere).
    h_min = np.full(count, np.inf)
    np.minimum.at(h_min, model.tets.ravel(), np.repeat(model.lengths, 4))
    E_node = np.zeros(count)
    np.maximum.at(E_node, model.tets.ravel(), np.repeat(model.youngs, 4))
    k_pen = PENALTY_FACTOR * E_node * model.node_area / np.where(np.isfinite(h_min), h_min, 1.0)
    candidates = np.flatnonzero(model.node_area > 0)
    regularise = FRICTION_REGULARISATION * max(drop.speed, 1e-9)

    u = np.zeros((count, 3))
    v = np.tile(drop.speed * d, (count, 1))
    gravity = drop.gravity * d
    touched = np.zeros(count, dtype=bool)

    # Snapshots: evenly spaced over the planned end (twice as dense when the window may stop early), the peak kept.
    planned = float(end_s)
    stride_frames = max(2, frames - 1) * (2 if stop_after_pulse else 1)
    snap_times = list(np.linspace(0.0, planned, stride_frames + 1))
    snaps: list[tuple[float, np.ndarray, np.ndarray]] = []
    peak_snap: tuple[float, np.ndarray, np.ndarray] | None = None
    peak_vm = -1.0
    vm_peak = np.zeros(model.elements)
    vm_peak_t = np.zeros(model.elements)
    u_peak = np.zeros(count)
    u_peak_t = np.zeros(count)
    curve_t: list[float] = []
    curve_f: list[float] = []
    total_mass = float(mass.sum())
    # What is reported is low-pass filtered at the mesh's own resolution: a few element transits.
    tau = FILTER_TRANSITS * weighted_median(model.element_dt, model.volume)
    vm_f = np.zeros(model.elements)
    raw = {"vm": 0.0, "force": 0.0, "force_f": 0.0, "peak_f": 0.0, "peak_t": 0.0}
    groups = {name: np.asarray(nodes, dtype=np.int64) for name, nodes in (watch or {}).items()}
    group_mass = {name: float(mass[nodes].sum()) for name, nodes in groups.items()}
    group_v = {name: float((mass[nodes] @ v[nodes]) @ d) / group_mass[name] for name, nodes in groups.items()}
    group_a = dict.fromkeys(groups, 0.0)
    group_peak = {name: (0.0, 0.0) for name in groups}

    def element_vm() -> np.ndarray:
        out = np.empty(model.elements)
        for each in sets.values():
            out[each.index] = each.vm
        return out

    def contact(nodes_mask_rows: np.ndarray, v_trial: np.ndarray, step: float) -> float:
        """Implicit normal penalty and explicit friction on boundary nodes ``rows`` over ``step``: updates ``v_trial``
        in place and returns the floor's push (N)."""
        rows = nodes_mask_rows
        if len(rows) == 0:
            return 0.0
        pen = (model.nodes[rows] + u[rows]) @ d - floor
        vn = v_trial[rows] @ d
        ahead = pen + step * vn
        active = ahead > 0
        if not active.any():
            return 0.0
        r = rows[active]
        m, k = mass[r], k_pen[r]
        c = 2.0 * CONTACT_DAMPING * np.sqrt(k * m)
        a = step * step * k / m
        before = vn[active] - step * k * pen[active] / m
        vn_new = before / (1.0 + a + step * c / m)
        p_new = pen[active] + step * vn_new
        normal_force = k * p_new + c * vn_new
        # The damper only slows the pressing: where it would pull the node back down, the spring acts alone.
        pulls = normal_force < 0
        if pulls.any():
            vn_new[pulls] = before[pulls] / (1.0 + a[pulls])
            p_new[pulls] = pen[active][pulls] + step * vn_new[pulls]
            normal_force[pulls] = k[pulls] * p_new[pulls]
        on = (p_new > 0) & (normal_force > 0)
        r, m, vn_new, normal_force = r[on], m[on], vn_new[on], normal_force[on]
        if len(r) == 0:
            return 0.0
        v_t = v_trial[r] - np.outer(v_trial[r] @ d, d)
        v_trial[r] += np.outer(vn_new - v_trial[r] @ d, d)
        if drop.friction > 0:
            speed_t = np.linalg.norm(v_t, axis=1)
            push = drop.friction * normal_force * speed_t / np.sqrt(speed_t ** 2 + regularise ** 2)
            push = np.minimum(push, m * speed_t / step)            # never more than stops the sliding
            scale = np.where(speed_t > 0, push / np.maximum(speed_t, 1e-300), 0.0)
            v_trial[r] -= (step * scale / m)[:, None] * v_t
        touched[r] = True
        return float(normal_force.sum())

    coarse_rows = candidates[coarse_nodes[candidates]]
    fine_rows = candidates[fine_nodes[candidates]]
    m3 = mass[:, None]

    t = 0.0
    big_steps = 0
    small_steps = 0
    pulse_end = None
    started_contact = False
    peak_force = 0.0
    stop_at = planned
    stopped_early = False
    extended = False
    extend_to = float(extend_to_s) if extend_to_s is not None and extend_to_s > planned else None
    curve_every = max(1, int(math.ceil(planned / big / curve_points)))
    eps = 1e-12 * planned

    def record(time_now: float, force: float, step: float) -> float:
        """Envelopes, snapshots and the filtered force after a step of ``step``; returns the filtered force."""
        nonlocal peak_vm, peak_snap
        rel = u - (mass[:, None] * u).sum(axis=0) / total_mass
        size = np.linalg.norm(rel, axis=1)
        higher = size > u_peak
        u_peak[higher] = size[higher]
        u_peak_t[higher] = time_now
        current = element_vm()
        raw["vm"] = max(raw["vm"], float(current.max()))
        raw["force"] = max(raw["force"], force)
        share = min(1.0, step / tau) if step > 0 else 0.0
        vm_f[:] += share * (current - vm_f)
        raw["force_f"] += share * (force - raw["force_f"])
        if raw["force_f"] > raw["peak_f"]:
            raw["peak_f"], raw["peak_t"] = raw["force_f"], time_now
        for name, nodes in groups.items():
            speed = float((mass[nodes] @ v[nodes]) @ d) / group_mass[name]
            if step > 0:
                group_a[name] += share * ((group_v[name] - speed) / step - group_a[name])
                if abs(group_a[name]) > abs(group_peak[name][0]):
                    group_peak[name] = (group_a[name], time_now)
            group_v[name] = speed
        vm = vm_f
        up = vm > vm_peak
        vm_peak[up] = vm[up]
        vm_peak_t[up] = time_now
        top = float(vm.max())
        if top > peak_vm:
            peak_vm = top
            peak_snap = (time_now, rel.astype(np.float32), vm.astype(np.float32))
        while snap_times and time_now >= snap_times[0] - eps:
            snaps.append((time_now, rel.astype(np.float32), vm.astype(np.float32)))
            snap_times.pop(0)
        return raw["force_f"]

    # Forces at t = 0 (no strain yet): the first record.
    f_int = sets["all" if n == 1 else "fine"].forces(u, v).reshape(count, 3)
    record(0.0, 0.0, 0.0)
    curve_t.append(0.0)
    curve_f.append(0.0)
    while t < stop_at - eps:
        step_big = min(big, stop_at - t) if n == 1 else big
        if n == 1:
            accel = gravity - f_int / m3
            v += step_big * accel
            force = contact(candidates, v, step_big)
            u += step_big * v
            small_steps += 1
            f_int = sets["all"].forces(u, v).reshape(count, 3)
        else:
            coarse_f = sets["coarse"].forces(u, v).reshape(count, 3)
            # Coarse nodes: one big step with every force on them at t (the fine set's last evaluation included).
            v[coarse_nodes] += big * (gravity - (coarse_f[coarse_nodes] + f_int[coarse_nodes]) / m3[coarse_nodes])
            force = contact(coarse_rows, v, big)
            u_start = u[coarse_nodes].copy()
            fine_force = 0.0
            for k in range(n):
                if k > 0:
                    u[coarse_nodes] = u_start + (k * small) * v[coarse_nodes]
                    f_int = sets["fine"].forces(u, v).reshape(count, 3)
                v[fine_nodes] += small * (gravity - f_int[fine_nodes] / m3[fine_nodes])
                fine_force += contact(fine_rows, v, small)
                u[fine_nodes] += small * v[fine_nodes]
                small_steps += 1
            u[coarse_nodes] = u_start + big * v[coarse_nodes]
            force += fine_force / n
            f_int = sets["fine"].forces(u, v).reshape(count, 3)
        t += step_big
        big_steps += 1
        filtered = record(t, force, step_big)
        if big_steps % curve_every == 0 or filtered > peak_force:
            curve_t.append(t)
            curve_f.append(filtered)
        peak_force = max(peak_force, filtered)
        if force > 0:
            started_contact = True
        # The pulse ends when the floor's own (unfiltered) push has fallen away and the part has stopped or turned back
        # (a node bouncing on the penalty spring in the first steps is not the end).
        if (started_contact and pulse_end is None and force <= PULSE_END_SHARE * raw["force"]
                and float((mass @ v) @ d) / total_mass <= STOPPED_SHARE * drop.speed):
            pulse_end = t
            if stop_after_pulse:
                stop_at = min(planned, t * (1.0 + WINDOW_TAIL))
                stopped_early = stop_at < planned - eps
            elif extended:
                stop_at = min(extend_to, max(t * (1.0 + WINDOW_TAIL), planned))
        # The planned end came with the part still on the floor: go on (snapshots at the same spacing) until it lifts.
        if (extend_to is not None and not extended and started_contact and pulse_end is None and t >= stop_at - eps
                and not stop_after_pulse):
            extended = True
            spacing = planned / stride_frames
            snap_times.extend(float(x) for x in np.arange(planned + spacing, extend_to + 0.5 * spacing, spacing))
            stop_at = extend_to
        if log and big_steps % 2000 == 0:
            log(f"impact: {t * 1e6:.1f} of {stop_at * 1e6:.1f} µs")
    if curve_t[-1] != t:
        curve_t.append(t)
        curve_f.append(raw["force_f"])
    # The frames: evenly spaced over the window that ran, the peak among them, at most ``frames``.
    end = t
    kept = [snap for snap in snaps if snap[0] <= end + eps]
    if not kept or kept[-1][0] < end - eps:
        rel = u - (mass[:, None] * u).sum(axis=0) / total_mass
        kept.append((end, rel.astype(np.float32), vm_f.astype(np.float32)))
    chosen = _choose_frames([s[0] for s in kept], frames - 1, end)
    picked = [kept[i] for i in chosen]
    if peak_snap is not None and all(abs(s[0] - peak_snap[0]) > eps for s in picked):
        picked.append(peak_snap)
        picked.sort(key=lambda s: s[0])
        while len(picked) > frames:
            # Drop an even frame next to another, never the peak, the start or the end.
            for i in range(1, len(picked) - 1):
                if abs(picked[i][0] - peak_snap[0]) > eps:
                    picked.pop(i)
                    break
            else:
                break
    kinetic = 0.5 * float((mass * (v * v).sum(axis=1)).sum())
    return Run(
        frame_t=[float(s[0]) for s in picked],
        frame_u=[s[1].astype(float) for s in picked],
        frame_vm=[s[2].astype(float) for s in picked],
        vm_peak=vm_peak, vm_peak_t=vm_peak_t, u_peak=u_peak, u_peak_t=u_peak_t,
        plastic=None if plastic is None else element_alpha(sets, model.elements),
        curve_t=curve_t, curve_force=curve_f, steps=small_steps, big_steps=big_steps, dt=small, end_s=end,
        planned_end_s=planned, pulse_end_s=pulse_end, stopped_early=stopped_early, touched=touched, extended=extended,
        seconds=time.perf_counter() - started,
        filter_s=tau, raw_peak_vm=raw["vm"], raw_peak_force=raw["force"], peak_force=raw["peak_f"],
        peak_force_t=raw["peak_t"], watched={name: (abs(a), t_at) for name, (a, t_at) in group_peak.items()},
        peak_t=None if peak_snap is None else float(peak_snap[0]),
        subcycle=n, fine_share=float(touching.mean()) if n > 1 else 0.0,
        energy={"kinetic_start_J": 0.5 * total_mass * drop.speed ** 2 * 1e-3, "kinetic_end_J": kinetic * 1e-3,
                "centre_velocity_end_mm_s": float((mass @ v) @ d) / total_mass,
                "mass_t": total_mass, "physical_mass_t": physical_mass},
    )


def weighted_median(values: "np.ndarray", weights: "np.ndarray") -> float:
    """The value half the weight lies under: the median element step by volume, the part's bulk, not its fine corners."""
    import numpy as np

    order = np.argsort(values)
    cumulative = np.cumsum(weights[order])
    return float(values[order][np.searchsorted(cumulative, 0.5 * cumulative[-1])])


def element_alpha(sets: dict, elements: int) -> "np.ndarray":
    import numpy as np

    out = np.zeros(elements)
    for each in sets.values():
        out[each.index] = each.alpha
    return out


def _choose_frames(times: list[float], even: int, end: float) -> list[int]:
    """Indices of ``times`` nearest ``even + 1`` evenly spaced moments from 0 to ``end``, each once, in order."""
    import numpy as np

    values = np.asarray(times)
    chosen = sorted({int(np.argmin(np.abs(values - target))) for target in np.linspace(0.0, end, max(even, 1) + 1)})
    return chosen
