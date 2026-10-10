"""A spinning rotor as a line of Timoshenko shaft elements: its whirl, critical speeds and unbalance response.

The rotor is a line along its spin axis ``a``, at stations ``s`` (mm, the
coordinate along ``a``). Each node carries four DOF: the deflection ``u``
along the first transverse axis ``e1`` and its rotation ``βu`` (the slope
du/ds for a slender shaft), then ``v`` and ``βv`` along ``e2``; ``(e1, e2, a)``
is right-handed and the spin ``Ω`` is positive about ``a``. Its equations of
motion are

    M q'' + (C + Ω G) q' + (K + Kb) q = F

with ``M`` the shaft's translational and rotary inertia plus the lumped discs,
``G`` the skew gyroscopic matrix (the polar inertia), ``K`` the shaft's
Timoshenko bending stiffness and ``Kb``, ``C`` the bearings' springs and
dampers (each may change with speed). A rigid bearing holds ``u`` and ``v``; a
clamped one holds the rotations too.

What it answers:

- :func:`whirl`: the damped whirl modes at one speed, by the state-space
  eigenproblem: each mode's frequency, log decrement and whirl direction
  (forward with the spin, or backward against it);
- :func:`campbell`: those frequencies against speed, forward and backward;
- :func:`critical_speeds`: where a forward (or backward) whirl crosses an
  order line ``k·Ω``, refined by a root find on the speed;
- :func:`unbalance_response`: the steady orbit the unbalances drive, at each
  speed, as each node's largest orbit radius and the phase it lags its force by.

Units are the engine's: mm, N, tonne, s, so a frequency comes out in rad/s.
Everything is dense (a rotor line has a few hundred DOF) and uses numpy and
scipy, imported inside the functions; the module is stdlib at import.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

__all__ = [
    "Bearing", "Campbell", "Critical", "DISC_RATIO", "Disc", "Element", "FoundDisc", "Frame", "Line", "Matrices", "Response",
    "Rotor", "Slab", "System", "Whirl", "assemble", "bearing_matrices", "build_line", "campbell", "coefficient_at",
    "critical_speeds", "disc_runs", "element_matrices", "frame_of", "interpolate", "merge_stations", "modal_basis",
    "orbit_radius", "rpm_of", "slab_of", "unbalance_response", "whirl", "whirl_direction",
]

DOF_PER_NODE = 4
_TWO_PI = 2.0 * math.pi
#: A whirl mode slower than this share of the sweep's top frequency scale is a rigid-body motion (a free tilt).
RIGID_SHARE = 1e-6
#: An eigenvalue past this size is the infinite one a massless DOF gives.
_INFINITE = 1e12


def rpm_of(omega: float) -> float:
    """rad/s as rpm."""
    return omega * 60.0 / _TWO_PI


# -- the model -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Element:
    """One shaft element between two stations: its section's sums over the parts it cuts."""

    length: float          # mm
    EI: float              # bending stiffness, N mm^2
    kGA: float             # shear stiffness κGA, N; math.inf for no shear deformation (Euler-Bernoulli)
    mass: float            # mass per length, t/mm
    diametral: float       # rotary inertia per length about a diameter (ρI), t mm
    polar: float           # polar inertia per length (ρIp), t mm

    @property
    def phi(self) -> float:
        """Timoshenko's shear parameter Φ = 12 EI / (κGA L²): 0 for a slender shaft."""
        if not math.isfinite(self.kGA) or self.kGA <= 0:
            return 0.0
        return 12.0 * self.EI / (self.kGA * self.length ** 2)


@dataclass(frozen=True)
class Disc:
    """A rigid disc lumped at a node: mass (t), diametral and polar inertia (t mm^2)."""

    node: int
    mass: float
    diametral: float
    polar: float


#: A bearing coefficient: a number, or a table of (rpm, value) pairs read linearly between its rows.
Coefficient = float | tuple[tuple[float, float], ...]


def coefficient_at(value: Coefficient, rpm: float) -> float:
    """A coefficient at a speed: its number, or its table read linearly (held flat past either end)."""
    if isinstance(value, (int, float)):
        return float(value)
    xs = [row[0] for row in value]
    ys = [row[1] for row in value]
    if rpm <= xs[0]:
        return float(ys[0])
    if rpm >= xs[-1]:
        return float(ys[-1])
    for i in range(1, len(xs)):
        if rpm <= xs[i]:
            t = (rpm - xs[i - 1]) / (xs[i] - xs[i - 1])
            return float(ys[i - 1] + t * (ys[i] - ys[i - 1]))
    return float(ys[-1])


@dataclass(frozen=True)
class Bearing:
    """A bearing at a node: springs (N/mm) and dampers (N s/mm) along e1 (x) and e2 (y), cross terms included."""

    node: int
    kxx: Coefficient = 0.0
    kyy: Coefficient = 0.0
    kxy: Coefficient = 0.0
    kyx: Coefficient = 0.0
    cxx: Coefficient = 0.0
    cyy: Coefficient = 0.0
    cxy: Coefficient = 0.0
    cyx: Coefficient = 0.0
    #: Holds u and v (no spring): a stiff ball bearing on a stiff housing.
    rigid: bool = False
    #: Holds the rotations too: a long sleeve, or a pair of bearings close together.
    clamped: bool = False

    @property
    def speed_dependent(self) -> bool:
        return any(not isinstance(getattr(self, name), (int, float))
                   for name in ("kxx", "kyy", "kxy", "kyx", "cxx", "cyy", "cxy", "cyx"))

    def matrices(self, rpm: float) -> tuple[list[list[float]], list[list[float]]]:
        """The 2 x 2 stiffness and damping on (u, v) at ``rpm``."""
        k = [[coefficient_at(self.kxx, rpm), coefficient_at(self.kxy, rpm)],
             [coefficient_at(self.kyx, rpm), coefficient_at(self.kyy, rpm)]]
        c = [[coefficient_at(self.cxx, rpm), coefficient_at(self.cxy, rpm)],
             [coefficient_at(self.cyx, rpm), coefficient_at(self.cyy, rpm)]]
        return k, c


@dataclass(frozen=True)
class Rotor:
    """The rotor line: its stations (mm along the axis), the elements between them, its discs and bearings."""

    stations: tuple[float, ...]
    elements: tuple[Element, ...]
    discs: tuple[Disc, ...] = ()
    bearings: tuple[Bearing, ...] = ()

    def __post_init__(self):
        if len(self.elements) != len(self.stations) - 1:
            raise ValueError("a rotor has one element between each pair of stations")

    @property
    def nodes(self) -> int:
        return len(self.stations)

    @property
    def dofs(self) -> int:
        return DOF_PER_NODE * self.nodes

    @property
    def speed_dependent(self) -> bool:
        return any(bearing.speed_dependent for bearing in self.bearings)

    def held(self) -> "np.ndarray":
        """The DOF the rigid and clamped bearings hold."""
        import numpy as np

        held: set[int] = set()
        for bearing in self.bearings:
            base = DOF_PER_NODE * bearing.node
            if bearing.rigid or bearing.clamped:
                held |= {base, base + 2}
            if bearing.clamped:
                held |= {base + 1, base + 3}
        return np.array(sorted(held), dtype=int)

    def free(self) -> "np.ndarray":
        import numpy as np

        return np.setdiff1d(np.arange(self.dofs), self.held())

    @property
    def mass(self) -> float:
        """The rotor's mass, t."""
        return sum(e.mass * e.length for e in self.elements) + sum(d.mass for d in self.discs)


def element_matrices(e: Element) -> tuple["np.ndarray", "np.ndarray", "np.ndarray", "np.ndarray"]:
    """One plane's 4 x 4 matrices on (w1, β1, w2, β2): stiffness, translational mass, rotary mass, and the rotary
    matrix with the polar inertia (the gyroscopic block). Timoshenko's, with Φ the shear parameter (Friswell et al.,
    Dynamics of Rotating Machines, 2010, section 5.4); Φ = 0 gives Euler-Bernoulli's."""
    import numpy as np

    L, phi = e.length, e.phi
    d = 1.0 + phi
    K = e.EI / (d * L ** 3) * np.array([
        [12.0, 6 * L, -12.0, 6 * L],
        [6 * L, (4 + phi) * L * L, -6 * L, (2 - phi) * L * L],
        [-12.0, -6 * L, 12.0, -6 * L],
        [6 * L, (2 - phi) * L * L, -6 * L, (4 + phi) * L * L],
    ])
    m1 = 13 / 35 + 7 * phi / 10 + phi ** 2 / 3
    m2 = 11 / 210 + 11 * phi / 120 + phi ** 2 / 24
    m3 = 9 / 70 + 3 * phi / 10 + phi ** 2 / 6
    m4 = 13 / 420 + 3 * phi / 40 + phi ** 2 / 24
    m5 = 1 / 105 + phi / 60 + phi ** 2 / 120
    m6 = 1 / 140 + phi / 60 + phi ** 2 / 120
    MT = e.mass * L / d ** 2 * np.array([
        [m1, m2 * L, m3, -m4 * L],
        [m2 * L, m5 * L * L, m4 * L, -m6 * L * L],
        [m3, m4 * L, m1, -m2 * L],
        [-m4 * L, -m6 * L * L, -m2 * L, m5 * L * L],
    ])
    r1, r2 = 6 / 5, 1 / 10 - phi / 2
    r3, r4 = 2 / 15 + phi / 6 + phi ** 2 / 3, -1 / 30 - phi / 6 + phi ** 2 / 6
    shape = np.array([
        [r1, r2 * L, -r1, r2 * L],
        [r2 * L, r3 * L * L, -r2 * L, r4 * L * L],
        [-r1, -r2 * L, r1, -r2 * L],
        [r2 * L, r4 * L * L, -r2 * L, r3 * L * L],
    ]) / (d ** 2 * L)
    return K, MT, e.diametral * shape, e.polar * shape


@dataclass
class Matrices:
    """The rotor's assembled matrices on every DOF (dense)."""

    M: "np.ndarray"
    K: "np.ndarray"
    G: "np.ndarray"


def assemble(rotor: Rotor) -> Matrices:
    """M, K and G of the shaft and its discs (the bearings are speed-dependent: :func:`bearing_matrices`)."""
    import numpy as np

    n = rotor.dofs
    M, K, G = np.zeros((n, n)), np.zeros((n, n)), np.zeros((n, n))
    for i, element in enumerate(rotor.elements):
        k, mt, mr, gp = element_matrices(element)
        x = np.array([4 * i, 4 * i + 1, 4 * i + 4, 4 * i + 5])
        y = x + 2
        for plane in (x, y):
            K[np.ix_(plane, plane)] += k
            M[np.ix_(plane, plane)] += mt + mr
        # Ip Ω couples the two planes' rotations: +gp from y into the x rows, -gp from x into the y rows.
        G[np.ix_(x, y)] += gp
        G[np.ix_(y, x)] -= gp
    for disc in rotor.discs:
        base = 4 * disc.node
        M[base, base] += disc.mass
        M[base + 2, base + 2] += disc.mass
        M[base + 1, base + 1] += disc.diametral
        M[base + 3, base + 3] += disc.diametral
        G[base + 1, base + 3] += disc.polar
        G[base + 3, base + 1] -= disc.polar
    return Matrices(M, K, G)


def bearing_matrices(rotor: Rotor, rpm: float) -> tuple["np.ndarray", "np.ndarray"]:
    """Kb and C of the bearings at ``rpm`` (a rigid or clamped bearing adds none: its DOF are held)."""
    import numpy as np

    n = rotor.dofs
    Kb, C = np.zeros((n, n)), np.zeros((n, n))
    for bearing in rotor.bearings:
        if bearing.rigid or bearing.clamped:
            continue
        k, c = bearing.matrices(rpm)
        index = np.array([4 * bearing.node, 4 * bearing.node + 2])
        Kb[np.ix_(index, index)] += np.array(k)
        C[np.ix_(index, index)] += np.array(c)
    return Kb, C


@dataclass
class System:
    """The rotor's matrices on its free DOF, or projected on a basis of its lowest modes (``basis``)."""

    rotor: Rotor
    matrices: Matrices
    free: "np.ndarray"
    #: (free, m) the modal basis the ladder's reduce_modes projects on, or None for the full model.
    basis: "np.ndarray | None" = None
    #: M and G projected, once; K + Kb and C projected, by speed (once when no bearing changes with speed).
    _inertia: tuple | None = field(default=None, repr=False)
    _bearings: dict = field(default_factory=dict, repr=False)
    _inverse: tuple | None = field(default=None, repr=False)

    @classmethod
    def of(cls, rotor: Rotor, basis: "np.ndarray | None" = None) -> "System":
        return cls(rotor, assemble(rotor), rotor.free(), basis)

    def _project(self, A: "np.ndarray") -> "np.ndarray":
        import numpy as np

        A = A[np.ix_(self.free, self.free)]
        return A if self.basis is None else self.basis.T @ A @ self.basis

    def at(self, rpm: float) -> tuple["np.ndarray", "np.ndarray", "np.ndarray", "np.ndarray"]:
        """(M, K + Kb, C, G) at ``rpm``, on the free DOF (or projected)."""
        key = round(rpm, 9) if self.rotor.speed_dependent else 0.0
        if key not in self._bearings:
            Kb, C = bearing_matrices(self.rotor, rpm)
            if len(self._bearings) >= 256:
                self._bearings.pop(next(iter(self._bearings)))
            self._bearings[key] = (self._project(self.matrices.K + Kb), self._project(C))
        if self._inertia is None:
            self._inertia = (self._project(self.matrices.M), self._project(self.matrices.G))
        K, C = self._bearings[key]
        M, G = self._inertia
        return M, K, C, G

    def mass_inverse(self) -> "np.ndarray | None":
        """M⁻¹ on the free DOF (or modal coordinates), or None when M is singular (a massless shaft)."""
        import numpy as np

        if self._inverse is None:
            M = self.at(0.0)[0]
            try:
                factor = np.linalg.cholesky(M)
                self._inverse = (np.linalg.inv(factor).T @ np.linalg.inv(factor),)
            except np.linalg.LinAlgError:
                self._inverse = (None,)
        return self._inverse[0]

    def expand(self, q: "np.ndarray") -> "np.ndarray":
        """A vector (or columns) on the free DOF (or modal coordinates) as one on every DOF, held DOF zero."""
        import numpy as np

        if self.basis is not None:
            q = self.basis @ q
        full = np.zeros((self.rotor.dofs,) + q.shape[1:], dtype=q.dtype)
        full[self.free] = q
        return full


# -- whirl ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Whirl:
    """One damped whirl mode at one speed."""

    omega: float           # damped natural frequency, rad/s (> 0)
    sigma: float           # real part of the eigenvalue, 1/s (negative: it dies away)
    forward: bool          # whirls with the spin
    shape: "np.ndarray"    # complex, every DOF, its largest translation 1 and real

    @property
    def frequency_Hz(self) -> float:
        return self.omega / _TWO_PI

    @property
    def log_decrement(self) -> float:
        """δ = -2πσ/ω_d: positive dies away, negative grows (unstable)."""
        return -_TWO_PI * self.sigma / self.omega


def whirl_direction(shape: "np.ndarray") -> float:
    """Σ Im(conj(u) v) over the nodes, over Σ |u|² + |v|²: -1 a forward circle, +1 a backward one, 0 a line."""
    import numpy as np

    u, v = shape[0::4], shape[2::4]
    size = float(np.sum(np.abs(u) ** 2 + np.abs(v) ** 2))
    if size <= 0:
        return 0.0
    return float(np.sum(np.imag(np.conj(u) * v))) / size * 2.0


def _normalised(shape: "np.ndarray") -> "np.ndarray":
    """The shape scaled so its largest translation is 1 and real (so a run repeats exactly)."""
    import numpy as np

    translations = np.concatenate([shape[0::4], shape[2::4]])
    peak = translations[int(np.argmax(np.abs(translations)))] if len(translations) else 1.0
    if abs(peak) == 0:
        rotations = np.concatenate([shape[1::4], shape[3::4]])
        peak = rotations[int(np.argmax(np.abs(rotations)))]
    return shape / peak if abs(peak) > 0 else shape


def _circular(shapes: "np.ndarray") -> "np.ndarray":
    """A cluster of equal-frequency shapes (columns, every DOF) recombined into the forward and backward circles.

    A round rotor whose discs do not tilt in a mode (a disc at mid-span) whirls forward and backward at one
    frequency at every speed, and the solver hands over any mix of the two. The mix that whirls most one way,
    then the other, is the eigenvectors of the whirl form ``Σ Im(conj(u) v)`` against the size ``Σ |u|² + |v|²``.
    """
    import numpy as np
    import scipy.linalg as la

    n = shapes.shape[0]
    u, v = np.arange(0, n, 4), np.arange(2, n, 4)
    Su, Sv = shapes[u], shapes[v]
    H = (Su.conj().T @ Sv - Sv.conj().T @ Su) / 2j          # Hermitian: x^H H x = Σ Im(conj(u) v)
    S = Su.conj().T @ Su + Sv.conj().T @ Sv
    S = 0.5 * (S + S.conj().T) + 1e-14 * np.trace(S).real * np.eye(len(S))
    _, x = la.eigh(0.5 * (H + H.conj().T), S)
    return shapes @ x


def whirl(system: System, omega_spin: float, *, scale: float | None = None) -> list[Whirl]:
    """Every whirl mode at spin ``omega_spin`` (rad/s), slowest first: the state-space eigenproblem
    ``[[I, 0], [0, M]] z' = [[0, I], [-K, -(C + ΩG)]] z``. A massless DOF's infinite eigenvalue, and a
    rigid-body motion's zero one (a tilt nothing holds), are left out: a whirl slower than a millionth of ``scale``
    (rad/s; the sweep's top speed), else of the fastest whirl found."""
    import numpy as np
    import scipy.linalg as la

    rpm = rpm_of(omega_spin)
    M, K, C, G = system.at(rpm)
    n = M.shape[0]
    if n == 0:
        return []
    D = C + omega_spin * G
    inverse = system.mass_inverse()
    if inverse is not None:
        # M positive definite (every rotor with mass along it): the standard problem, several times faster.
        A = np.block([[np.zeros((n, n)), np.eye(n)], [-(inverse @ K), -(inverse @ D)]])
        values, vectors = la.eig(A, check_finite=False)
    else:
        A = np.block([[np.zeros((n, n)), np.eye(n)], [-K, -D]])
        B = np.block([[np.eye(n), np.zeros((n, n))], [np.zeros((n, n)), M]])
        values, vectors = la.eig(A, B, check_finite=False)
    finite = np.isfinite(values) & (np.abs(values) < _INFINITE)
    zero = RIGID_SHARE * (scale if scale else max(1.0, float(np.max(np.abs(values[finite]), initial=1.0))))
    chosen = np.flatnonzero(finite & (values.imag > zero))
    chosen = chosen[np.argsort(values[chosen].imag)]
    lams = values[chosen]
    shapes = system.expand(vectors[:n, chosen]) if len(chosen) else np.zeros((system.rotor.dofs, 0), dtype=complex)
    # Equal eigenvalues (to 1e-8): their shapes recombined into the two whirl directions.
    start = 0
    while start < len(lams):
        end = start + 1
        while end < len(lams) and abs(lams[end] - lams[start]) <= 1e-8 * abs(lams[start]):
            end += 1
        if end - start > 1:
            shapes[:, start:end] = _circular(shapes[:, start:end])
        start = end
    found = []
    for k, lam in enumerate(lams):
        shape = _normalised(shapes[:, k])
        found.append(Whirl(float(lam.imag), float(lam.real), whirl_direction(shape) < 0, shape))
    found.sort(key=lambda w: (w.omega, not w.forward))
    return found


@dataclass
class Campbell:
    """Whirl frequencies against speed: ``forward[i, j]`` the j-th slowest forward whirl at ``speeds[i]`` (rad/s),
    NaN where fewer were found; log decrements alike."""

    speeds: "np.ndarray"
    forward: "np.ndarray"
    backward: "np.ndarray"
    forward_log_dec: "np.ndarray"
    backward_log_dec: "np.ndarray"

    def curve(self, forward: bool, j: int) -> "np.ndarray":
        return (self.forward if forward else self.backward)[:, j]


def _split(modes: list[Whirl], count: int):
    import numpy as np

    out = []
    for direction in (True, False):
        chosen = [w for w in modes if w.forward == direction][:count]
        freq = np.full(count, np.nan)
        dec = np.full(count, np.nan)
        for j, w in enumerate(chosen):
            freq[j], dec[j] = w.omega, w.log_decrement
        out.append((freq, dec))
    return out


def campbell(system: System, speeds: Sequence[float], count: int, *, scale: float | None = None) -> Campbell:
    """The ``count`` slowest forward and backward whirls at each speed (rad/s). At zero speed a round rotor's
    forward and backward whirls are one frequency, which no direction tells apart: it is solved a hair above zero."""
    import numpy as np

    speeds = np.asarray(speeds, dtype=float)
    F, B = np.full((len(speeds), count), np.nan), np.full((len(speeds), count), np.nan)
    Fd, Bd = np.full((len(speeds), count), np.nan), np.full((len(speeds), count), np.nan)
    top = float(speeds.max()) if len(speeds) else 1.0
    for i, speed in enumerate(speeds):
        at = speed if speed > 0 else 1e-6 * max(top, 1.0)
        (f, fd), (b, bd) = _split(whirl(system, at, scale=scale), count)
        F[i], Fd[i], B[i], Bd[i] = f, fd, b, bd
    return Campbell(speeds, F, B, Fd, Bd)


@dataclass(frozen=True)
class Critical:
    """A speed where a whirl's frequency meets an order line (k × the spin)."""

    omega: float           # spin, rad/s
    order: float           # 1 for once per revolution
    forward: bool
    mode: int              # 1-based among its direction's whirls at that speed
    whirl: Whirl

    @property
    def rpm(self) -> float:
        return rpm_of(self.omega)


def critical_speeds(system: System, chart: Campbell, orders: Sequence[float] = (1.0,), *, backward: bool = True,
                    scale: float | None = None) -> list[Critical]:
    """Every crossing of a whirl curve with an order line inside the chart's speeds, slowest first: bracketed on
    the chart, then found to a part in 10^9 of the speed by Brent's method on the whirl at each trial speed."""
    import numpy as np
    from scipy.optimize import brentq

    found: list[Critical] = []
    speeds = chart.speeds
    for forward in ((True, False) if backward else (True,)):
        table = chart.forward if forward else chart.backward
        for j in range(table.shape[1]):
            for order in orders:
                gap = table[:, j] - order * speeds
                for i in range(len(speeds) - 1):
                    a, b = gap[i], gap[i + 1]
                    if not (np.isfinite(a) and np.isfinite(b)) or a * b > 0 or a == b == 0:
                        continue
                    if a == 0 and i > 0:
                        continue  # counted as the previous bracket's end

                    def g(speed, j=j, order=order, forward=forward):
                        modes = [w for w in whirl(system, max(speed, 1e-9), scale=scale) if w.forward == forward]
                        if j >= len(modes):
                            return float("nan")
                        return modes[j].omega - order * speed

                    lo, hi = float(speeds[i]), float(speeds[i + 1])
                    try:
                        glo, ghi = g(max(lo, 1e-9)), g(hi)
                        if not (np.isfinite(glo) and np.isfinite(ghi)) or glo * ghi > 0:
                            root = lo + (hi - lo) * a / (a - b)
                        else:
                            root = brentq(g, max(lo, 1e-9), hi, xtol=1e-12, rtol=1e-10, maxiter=60)
                    except (ValueError, RuntimeError):
                        root = lo + (hi - lo) * a / (a - b)
                    modes = [w for w in whirl(system, max(root, 1e-9), scale=scale) if w.forward == forward]
                    if j < len(modes):
                        found.append(Critical(float(root), float(order), forward, j + 1, modes[j]))
    found.sort(key=lambda c: (c.omega, not c.forward))
    # One crossing found twice (two curves swapping near it) is kept once.
    unique: list[Critical] = []
    for critical in found:
        if not any(abs(critical.omega - other.omega) <= 1e-6 * max(critical.omega, 1.0) and critical.forward == other.forward
                   and critical.order == other.order for other in unique):
            unique.append(critical)
    return unique


# -- unbalance -----------------------------------------------------------------------------------------


def orbit_radius(u: "np.ndarray", v: "np.ndarray") -> "np.ndarray":
    """The largest radius of the elliptical orbit Re((u, v) e^{iΩt}): its major semi-axis."""
    import numpy as np

    return np.sqrt(0.5 * (np.abs(u) ** 2 + np.abs(v) ** 2) + 0.5 * np.abs(u * u + v * v))


@dataclass
class Response:
    """The steady unbalance response at each speed: ``amplitude[i, node]`` (mm, the orbit's largest radius),
    ``phase[i, node]`` (degrees the u motion lags the first unbalance's force), and the complex DOF (``Q``)."""

    speeds: "np.ndarray"
    amplitude: "np.ndarray"
    phase: "np.ndarray"
    Q: "np.ndarray"


def unbalance_response(system: System, unbalances: Sequence[tuple[int, float, float]], speeds: Sequence[float]) -> Response:
    """The orbit ``unbalances`` drive at each speed (rad/s): each ``(node, U t·mm, phase rad)`` is a force
    U Ω² turning with the rotor, (cos, sin)(Ωt + phase) along (e1, e2). Solves
    ``(K + Kb - Ω²M + iΩ(C + ΩG)) Q = F`` for the complex amplitude Q."""
    import numpy as np

    speeds = np.asarray(speeds, dtype=float)
    rotor = system.rotor
    nodes = rotor.nodes
    amplitude = np.zeros((len(speeds), nodes))
    phase = np.zeros((len(speeds), nodes))
    Q = np.zeros((len(speeds), rotor.dofs), dtype=complex)
    lead = unbalances[0][2] if unbalances else 0.0
    for i, speed in enumerate(speeds):
        M, K, C, G = system.at(rpm_of(speed))
        F = np.zeros(rotor.dofs, dtype=complex)
        for node, U, angle in unbalances:
            force = U * speed ** 2 * np.exp(1j * angle)
            F[4 * node] += force
            F[4 * node + 2] += -1j * force
        f = F[system.free]
        if system.basis is not None:
            f = system.basis.T @ f
        Z = K - speed ** 2 * M + 1j * speed * (C + speed * G)
        try:
            q = np.linalg.solve(Z, f)
        except np.linalg.LinAlgError:
            q = np.linalg.lstsq(Z, f, rcond=None)[0]
        full = system.expand(q)
        Q[i] = full
        u, v = full[0::4], full[2::4]
        amplitude[i] = orbit_radius(u, v)
        # How far the motion lags its force: the force's angle less the motion's, 0 to 360.
        phase[i] = np.degrees(np.mod(lead - np.angle(u), _TWO_PI))
    return Response(speeds, amplitude, phase, Q)


# -- the ladder's reduce_modes ---------------------------------------------------------------------------


def modal_basis(rotor: Rotor, count: int, *, rpm: float = 0.0) -> "np.ndarray | None":
    """The ``count`` slowest undamped, non-spinning modes on the free DOF (bearings at ``rpm``, their direct
    springs only), mass-normalised: the basis reduce_modes projects the rotor on. ``None`` when the mass matrix is
    singular (a massless shaft) or the rotor is no larger than the basis."""
    import numpy as np
    import scipy.linalg as la

    matrices = assemble(rotor)
    Kb, _ = bearing_matrices(rotor, rpm)
    free = rotor.free()
    if count >= len(free):
        return None
    M = matrices.M[np.ix_(free, free)]
    K = (matrices.K + 0.5 * (Kb + Kb.T))[np.ix_(free, free)]
    try:
        np.linalg.cholesky(M)
    except np.linalg.LinAlgError:
        return None
    _, vectors = la.eigh(K, M, subset_by_index=[0, count - 1])
    return vectors


def interpolate(stations: Sequence[float], values: "np.ndarray", s: "np.ndarray") -> "np.ndarray":
    """Per-node ``values`` (nodes, ...) read at axial positions ``s`` linearly, held flat past either end."""
    import numpy as np

    stations = np.asarray(stations, dtype=float)
    values = np.asarray(values)
    flat = values.reshape(len(stations), -1)
    out = np.stack([np.interp(s, stations, flat[:, c].real) + (1j * np.interp(s, stations, flat[:, c].imag)
                                                              if np.iscomplexobj(flat) else 0.0)
                    for c in range(flat.shape[1])], axis=-1)
    return out.reshape((len(s),) + values.shape[1:])



# -- the rotor line from the CAD -------------------------------------------------------------------------

#: A run of sections is a disc when it is this many times as stiff-wide (the radius of the solid circle with its
#: bending inertia) as the shaft either side of it, and shorter than its own diameter.
DISC_RATIO = 1.5
#: Stations closer than this share of the rotor's length are one station.
MERGE_SHARE = 2e-3


@dataclass(frozen=True)
class Frame:
    """The spin axis ``a`` through ``origin``, and the transverse axes ``e1``, ``e2`` (``(e1, e2, a)`` right-handed)."""

    origin: tuple[float, float, float]
    a: tuple[float, float, float]
    e1: tuple[float, float, float]
    e2: tuple[float, float, float]

    def s(self, point) -> float:
        """A point's position along the axis: its coordinate along ``a`` (Z for a Z axis)."""
        return float(sum(p * c for p, c in zip(point, self.a)))

    def on_axis(self, s: float) -> tuple[float, float, float]:
        shift = s - self.s(self.origin)
        return tuple(o + shift * c for o, c in zip(self.origin, self.a))  # type: ignore[return-value]


def frame_of(axis: tuple[float, float, float], origin: tuple[float, float, float]) -> Frame:
    """The frame of a spin axis: X spins with (Y, Z) across it, Y with (Z, X), Z with (X, Y); any other axis with
    the global axis least along it, made square to it, as e1."""
    named = {(1.0, 0.0, 0.0): ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)), (0.0, 1.0, 0.0): ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
             (0.0, 0.0, 1.0): ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))}
    a = tuple(float(c) for c in axis)
    key = tuple(round(c, 12) + 0.0 for c in a)
    if key in named:
        e1, e2 = named[key]
        return Frame(tuple(origin), a, e1, e2)  # type: ignore[arg-type]
    pick = min(range(3), key=lambda c: abs(a[c]))
    ref = [0.0, 0.0, 0.0]
    ref[pick] = 1.0
    dot = sum(r * c for r, c in zip(ref, a))
    e1 = [r - dot * c for r, c in zip(ref, a)]
    size = math.sqrt(sum(c * c for c in e1))
    e1 = [c / size for c in e1]
    e2 = [a[1] * e1[2] - a[2] * e1[1], a[2] * e1[0] - a[0] * e1[2], a[0] * e1[1] - a[1] * e1[0]]
    return Frame(tuple(origin), a, tuple(e1), tuple(e2))  # type: ignore[arg-type]


@dataclass(frozen=True)
class Slab:
    """What the CAD holds between two stations: the sums a rotor element is made of."""

    s0: float
    s1: float
    volume: float          # mm^3
    mass: float            # t
    centre: float          # the mass's axial position, mm
    EI: float              # N mm^2 (each part's E times its second moment about the slab's stiffness centre)
    kGA: float             # N
    inertia: float         # geometric bending second moment of area, mm^4 (stiff-width test)
    diametral: float       # mass moment about a diameter through the axis, per the slab: ρ∫x1² dV, t mm^2
    polar: float           # ρ∫(x1² + x2²) dV, t mm^2
    axial: float           # ρ∫(s - centre)² dV, t mm^2 (a lumped disc's own axial spread)

    @property
    def length(self) -> float:
        return self.s1 - self.s0

    @property
    def area(self) -> float:
        return self.volume / self.length if self.length > 0 else 0.0

    @property
    def stiff_radius(self) -> float:
        """The radius of the solid circle with this slab's bending inertia."""
        I = self.inertia / self.length if self.length > 0 else 0.0
        return (4.0 * I / math.pi) ** 0.25 if I > 0 else 0.0

    @property
    def outer_radius(self) -> float:
        """sqrt(2 Ip / A): a solid circle's radius, about an annulus's mean."""
        if self.mass <= 0:
            return self.stiff_radius
        return math.sqrt(max(self.polar / self.mass, 0.0) * 2.0) if self.polar > 0 else 0.0

    def element(self) -> Element:
        L = self.length
        return Element(L, self.EI, self.kGA, self.mass / L, self.diametral / L, self.polar / L)


def _volume_props(shape):
    """(volume, centre, 3x3 inertia tensor about the centre for unit density) of an OCP shape; None when empty."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    volume = float(props.Mass())
    if not volume > 0:
        return None
    centre = props.CentreOfMass()
    matrix = props.MatrixOfInertia()
    J = [[matrix.Value(i, j) for j in (1, 2, 3)] for i in (1, 2, 3)]
    return volume, (centre.X(), centre.Y(), centre.Z()), J


def slab_of(parts, frame: Frame, s0: float, s1: float, radius: float) -> Slab:
    """The parts' material between stations ``s0`` and ``s1``: a box ``2 radius`` across, cut from each part
    (OCP's Boolean common) and integrated exactly (``BRepGProp``). ``parts`` are ``(OCP shape, Material)``."""
    import numpy as np
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    from cadgen._internal.fea.beam import shear_factor

    a, e1, e2 = (np.array(v, dtype=float) for v in (frame.a, frame.e1, frame.e2))
    corner = np.array(frame.on_axis(s0)) - radius * e1 - radius * e2
    box = BRepPrimAPI_MakeBox(gp_Ax2(gp_Pnt(*corner), gp_Dir(*a), gp_Dir(*e1)), 2 * radius, 2 * radius, s1 - s0).Shape()
    pieces = []
    for shape, material in parts:
        common = BRepAlgoAPI_Common(shape, box)
        if not common.IsDone():
            raise RuntimeError(f"could not cut the rotor between {s0:.4g} and {s1:.4g} mm along its axis")
        found = _volume_props(common.Shape())
        if found is not None:
            volume, centre, J = found
            pieces.append((volume, np.array(centre), np.array(J), material))
    if not pieces:
        return Slab(s0, s1, 0.0, 0.0, 0.5 * (s0 + s1), 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    L = s1 - s0
    mass = sum(volume * material.density for volume, _, _, material in pieces)
    weights = [volume * (material.density if mass > 0 else 1.0) for volume, _, _, material in pieces]
    centre_point = sum(w * c for w, (_, c, _, _) in zip(weights, pieces)) / sum(weights)
    centre = float(centre_point @ a)
    stiff_weights = [volume * material.E for volume, _, _, material in pieces]
    stiff_centre = sum(w * c for w, (_, c, _, _) in zip(stiff_weights, pieces)) / sum(stiff_weights)
    axis_point = np.array(frame.on_axis(centre))
    EI = kGA = inertia = diametral = polar = axial = 0.0
    for volume, c, J, material in pieces:
        S = 0.5 * np.trace(J) * np.eye(3) - J                 # ∫ r rᵀ dV about the piece's own centre
        about = lambda point: S + volume * np.outer(c - point, c - point)  # noqa: E731
        Ss = about(stiff_centre)
        Sa = about(axis_point)
        bend = 0.5 * (e1 @ Ss @ e1 + e2 @ Ss @ e2)
        EI += material.E * bend / L
        inertia += bend
        G = material.E / (2.0 * (1.0 + material.nu))
        kGA += shear_factor(True, material.nu) * G * volume / L
        across = e1 @ Sa @ e1 + e2 @ Sa @ e2
        diametral += material.density * 0.5 * across
        polar += material.density * across
        axial += material.density * float(a @ Sa @ a)
    return Slab(s0, s1, sum(p[0] for p in pieces), mass, centre, EI, kGA, inertia, diametral, polar, axial)


@dataclass(frozen=True)
class FoundDisc:
    """A disc found in the CAD (a run of sections much wider than the shaft either side), or added by the study."""

    s0: float
    s1: float
    centre: float
    mass: float            # t
    diametral: float       # about its own centre, t mm^2
    polar: float           # t mm^2
    source: str            # "cad" or "study"
    outer_radius: float = 0.0


def disc_runs(slabs: Sequence[Slab]) -> list[tuple[int, int]]:
    """The runs of slabs (first, last index) that are discs: each slab of the run stiff-wider than
    :data:`DISC_RATIO` times the shaft just outside it (on each side it has one), the run shorter than its
    diameter. The longest runs win where candidates overlap; a run that is the whole rotor is no disc."""
    n = len(slabs)
    radius = [slab.stiff_radius for slab in slabs]
    candidates = []
    for i in range(n):
        for j in range(i, n):
            outside = [radius[k] for k in (i - 1, j + 1) if 0 <= k < n]
            if not outside:
                continue
            if min(radius[i:j + 1]) <= DISC_RATIO * max(outside):
                continue
            length = slabs[j].s1 - slabs[i].s0
            if length >= 2.0 * max(slab.outer_radius for slab in slabs[i:j + 1]):
                continue
            candidates.append((i, j))
    candidates.sort(key=lambda run: (-(slabs[run[1]].s1 - slabs[run[0]].s0), run[0]))
    chosen: list[tuple[int, int]] = []
    for i, j in candidates:
        if all(j < a or i > b for a, b in chosen):
            chosen.append((i, j))
    return sorted(chosen)


def merge_stations(points: Sequence[float], keep: Sequence[float], tolerance: float) -> list[float]:
    """The stations sorted, any within ``tolerance`` of a kept one (or of each other) merged into it."""
    kept = sorted(set(float(k) for k in keep))
    out = list(kept)
    for p in sorted(points):
        if all(abs(p - q) > tolerance for q in out):
            out.append(float(p))
    return sorted(out)


@dataclass
class Line:
    """The rotor line built from the CAD: the rotor, its stations' sources, the discs found and lumped."""

    rotor: Rotor
    frame: Frame
    discs: list[FoundDisc]
    slabs: list[Slab]
    #: Each lumped (rigid) disc's run [s0, s1]: the elements inside carry the shaft's stiffness, no mass.
    lumped: list[tuple[float, float]]

    def node_at(self, s: float) -> int:
        stations = self.rotor.stations
        return min(range(len(stations)), key=lambda i: abs(stations[i] - s))


def build_line(parts, frame: Frame, extent: tuple[float, float], radius: float, *, breakpoints: Sequence[float],
               stations: Sequence[float], elements: int, disc_model: str = "rigid",
               added: Sequence[FoundDisc] = (), log=None) -> Line:
    """The rotor line of ``parts`` along ``frame``: stations at every breakpoint (where the CAD's sections change)
    and at every station the study needs (bearings, unbalances, added discs), each segment cut into elements of
    at most ``length / elements``; each element's section sliced from the CAD exactly. Discs are found
    (:func:`disc_runs`); a ``rigid`` disc is lumped at its mass centre (mass, diametral and polar inertia) with
    the shaft's stiffness through it, a ``flexible`` one keeps its own sections."""
    lo, hi = extent
    L = hi - lo
    tolerance = MERGE_SHARE * L
    keep = [lo, hi, *[s for s in stations if lo - tolerance <= s <= hi + tolerance]]
    keep = [min(max(s, lo), hi) for s in keep]
    points = merge_stations([p for p in breakpoints if lo < p < hi], keep, tolerance)
    segments = [slab_of(parts, frame, a, b, radius) for a, b in zip(points[:-1], points[1:])]
    for slab in segments:
        if slab.volume <= 1e-9 * max(L, 1.0) ** 3 or slab.EI <= 0:
            raise ValueError(f"the rotor has no material between {slab.s0:.4g} and {slab.s1:.4g} mm along its axis; "
                             "a rotor must be one unbroken line of material along the spin axis (check spin.axis)")
    runs = disc_runs(segments)
    found = []
    for i, j in runs:
        whole = slab_of(parts, frame, segments[i].s0, segments[j].s1, radius)
        found.append(FoundDisc(whole.s0, whole.s1, whole.centre, whole.mass, whole.diametral + whole.axial, whole.polar,
                               "cad", max(segments[k].outer_radius for k in range(i, j + 1))))
    lumped = [(d.s0, d.s1) for d in found] if disc_model == "rigid" else []
    in_run = {k for i, j in runs for k in range(i, j + 1)} if lumped else set()
    # Stations: a lumped disc's run is one element each side of its centre; the rest cut to the element size.
    target = L / max(int(elements), 1)
    nodes: list[float] = [points[0]]
    for k, slab in enumerate(segments):
        if k in in_run:
            continue
        count = max(1, math.ceil(slab.length / target - 1e-9))
        nodes += [slab.s0 + slab.length * (q / count) for q in range(1, count + 1)]
    for disc in found if lumped else ():
        nodes += [disc.s0, disc.centre, disc.s1]
    nodes += [d.centre for d in added if lo <= d.centre <= hi]
    nodes = merge_stations(nodes, keep + ([d.centre for d in found] if lumped else []), tolerance * 0.25)
    slabs = [slab_of(parts, frame, a, b, radius) for a, b in zip(nodes[:-1], nodes[1:])]
    elements_out = []
    for slab in slabs:
        element = slab.element()
        if any(a - 1e-9 <= 0.5 * (slab.s0 + slab.s1) <= b + 1e-9 for a, b in lumped):
            element = Element(slab.length, 0.0, element.kGA, 0.0, 0.0, 0.0)
        elements_out.append(element)
    # The shaft through a lumped disc bends like the stiffer-shaft neighbour's less stiff side: the smaller of the
    # elements just outside the run.
    for a, b in lumped:
        inside = [k for k, slab in enumerate(slabs) if a - 1e-9 <= 0.5 * (slab.s0 + slab.s1) <= b + 1e-9]
        outside = [k for k in (min(inside) - 1, max(inside) + 1) if 0 <= k < len(slabs) and k not in inside]
        EI = min(elements_out[k].EI for k in outside)
        kGA = min(elements_out[k].kGA for k in outside)
        for k in inside:
            elements_out[k] = Element(slabs[k].length, EI, kGA, 0.0, 0.0, 0.0)
    rotor_nodes = tuple(nodes)
    near = lambda s: min(range(len(rotor_nodes)), key=lambda i: abs(rotor_nodes[i] - s))  # noqa: E731
    discs = [Disc(near(d.centre), d.mass, d.diametral, d.polar) for d in found] if lumped else []
    discs += [Disc(near(d.centre), d.mass, d.diametral, d.polar) for d in added]
    if log:
        log(f"rotordynamics: rotor line of {len(elements_out)} elements, {len(found)} disc{'s' if len(found) != 1 else ''} found")
    line = Line(Rotor(rotor_nodes, tuple(elements_out), tuple(discs)), frame, [*found, *added], slabs, lumped)
    return line
