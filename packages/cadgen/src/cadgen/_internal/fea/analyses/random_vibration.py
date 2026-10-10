"""Random vibration: the part's response to a random shake given as a PSD, at 1σ and 3σ.

The study (spec 5.9) holds the part at its ``fixtures`` and shakes them
together along ``psd.direction`` with a random acceleration whose power
spectral density is ``psd.table``: rows of ``[Hz, g²/Hz]``, interpolated
log-log between rows (straight lines on the log-log plot every vibration spec
is drawn on) and zero outside the table. A transport or MIL-STD profile is
written as it is printed.

The answer is built by modal superposition (:mod:`cadgen._internal.fea.superposition`)
from every mode up to 1.5 × the table's top, with modal damping
``damping_ratio`` (default 0.02):

- each mode's motion relative to the base answers the shake through
  ``qᵢ = −Γᵢ Hᵢ(ω) a``, so the modal coordinates' cross-spectral density is
  ``S_qq(f) = (Γ⊙H)(Γ⊙H)ᴴ S_a(f)``;
- that is integrated over a log grid that puts 40 points across every mode's
  half-power bandwidth (2ζf) into one m × m covariance ``C = ∫ S_qq df``;
- a nodal displacement's variance is ``φᵀ C φ`` (summed over X, Y, Z), so
  ``displacement_rms`` is the RMS size of the motion;
- von Mises RMS is Segalman's quadratic form: with ``A`` the 6 × 6 matrix that
  makes ``σ_vm² = σᵀ A σ`` and ``S_σσ`` the stress's cross-spectral density,
  ``σ_vm,rms = sqrt(∫ tr(A S_σσ) df) = sqrt(Σᵢⱼ Cᵢⱼ ψᵢᵀ A ψⱼ)``, ψ each mode's
  stress (D. J. Segalman et al., "An efficient method for calculating RMS von
  Mises stress in a random vibration environment", J. Sound Vib. 230(2), 2000);
- the expected rate of up-crossings ν0+ = sqrt(m2/m0) comes from the same form
  with the covariance weighted by f² (``zero_crossing_Hz``, which fatigue reads).

Both fields are one standard deviation (1σ). The checks judge ``sigma`` times
them (default 3σ, a level a Gaussian response passes about 0.3 % of the time):
``stress`` (labelled "Random vibration") and ``displacement``.

The ladder's own rungs are ``reduce_modes`` (the fewest modes holding 90 % of
the mass moving along the shake) and ``frequency_grid``, a coarser frequency
grid (10 points per half-power bandwidth instead of 40), whose accuracy cost is
measured on a single resonance. The mesh rungs are the shared ones. Stdlib only
at import.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import AnalysisResult, FieldSpec, Inputs, SolveContext
from cadgen._internal.fea.analyses.harmonic import axis_words
from cadgen._internal.fea.analyses.modal import (
    align_degenerate, apply_eigen_rung, eigen_estimate, fixed_dofs, hz_text, materials_of, solver_method,
)
from cadgen._internal.fea.study import Fixture, parse_fixtures

if TYPE_CHECKING:
    import numpy as np

__all__ = [
    "RandomVibrationAnalysis", "RandomVibrationInputs", "grid_error", "grms", "modal_covariance", "psd_at",
    "response_grid", "rms_displacement", "rms_von_mises", "von_mises_form",
]

G0_MM_S2 = 9806.65
#: Modes are found up to this multiple of the PSD table's top.
TOP_FACTOR = 1.5
#: reduce_modes keeps the fewest modes holding this share of the mass moving along the shake.
KEEP_SHARE = 0.9
#: Under this share of the mass along the shake, the modes found may miss part of the response: a finding.
MASS_WARNING = 0.8
#: Points across each mode's half-power bandwidth (2ζf): the grid's density, and after the coarser-grid rung.
POINTS_PER_BANDWIDTH = 40
COARSE_POINTS = 10
#: Whatever the damping, the grid has at least this many points over the table.
MIN_POINTS = 200
#: The number of modes the ladder assumes before the solve has found them, and after reduce_modes.
GUESS_MODES = 20
REDUCED_GUESS = 6
#: Frequencies whose modal transfer is formed at once, while integrating.
CHUNK = 2048
#: The most points a response curve in the sidecar keeps (the grid thinned evenly).
CURVE_POINTS = 600
SIGMAS = (1, 3)
_TWO_PI = 2.0 * math.pi
_AXES = "XYZ"


def von_mises_form():
    """A: σ_vm² = σᵀ A σ for σ stored (xx, yy, zz, xy, yz, xz)."""
    import numpy as np

    A = np.zeros((6, 6))
    A[:3, :3] = -0.5
    A[[0, 1, 2], [0, 1, 2]] = 1.0
    A[[3, 4, 5], [3, 4, 5]] = 3.0
    return A


@dataclass(frozen=True)
class RandomVibrationInputs(Inputs):
    fixtures: tuple[Fixture, ...] = ()
    #: The shake's direction, a unit vector.
    direction: tuple[float, float, float] = (0.0, 0.0, 1.0)
    #: Rows of (Hz, g²/Hz), frequencies rising.
    table: tuple[tuple[float, float], ...] = ()
    damping_ratio: float = 0.02
    #: The level the checks judge at: 1 or 3 standard deviations.
    sigma: int = 3

    @property
    def band_Hz(self) -> tuple[float, float]:
        return self.table[0][0], self.table[-1][0]

    @property
    def top_Hz(self) -> float:
        """The highest mode the response is built from: 1.5 × the table's top."""
        return TOP_FACTOR * self.table[-1][0]

    @property
    def grms(self) -> float:
        return grms(self.table)


# -- the PSD -----------------------------------------------------------------------------------------

def _slopes(table) -> list[float]:
    return [math.log(p1 / p0) / math.log(f1 / f0) for (f0, p0), (f1, p1) in zip(table, table[1:])]


def grms(table) -> float:
    """The input's RMS acceleration in g: the square root of the PSD's area, each log-log segment integrated
    exactly (S = S0 (f/f0)^s has area S0 f0 ((f1/f0)^(s+1) − 1)/(s + 1), or S0 f0 ln(f1/f0) at s = −1)."""
    area = 0.0
    for ((f0, p0), (f1, _)), s in zip(zip(table, table[1:]), _slopes(table)):
        log_ratio = math.log(f1 / f0)
        e = s + 1.0
        area += p0 * f0 * (log_ratio if abs(e * log_ratio) < 1e-12 else math.expm1(e * log_ratio) / e)
    return math.sqrt(area)


def psd_at(table, f_Hz) -> "np.ndarray":
    """The PSD (g²/Hz) at frequencies ``f_Hz``: log-log between the table's rows, zero outside it."""
    import numpy as np

    f = np.atleast_1d(np.asarray(f_Hz, dtype=float))
    freqs = np.array([row[0] for row in table])
    logs = np.log(np.array([row[1] for row in table]))
    out = np.zeros_like(f)
    # The ends within rounding are on the table (a log grid's exp(log 20) may be a hair under 20).
    inside = (f >= freqs[0] * (1 - 1e-12)) & (f <= freqs[-1] * (1 + 1e-12))
    out[inside] = np.exp(np.interp(np.log(f[inside]), np.log(freqs), logs))
    return out


def response_grid(table, zeta: float, points: int = POINTS_PER_BANDWIDTH) -> "np.ndarray":
    """Frequencies (Hz) the response PSD is integrated over: log-spaced across the table, ``points`` per
    half-power bandwidth (a mode's 2ζf is the same width, 2ζ, on a log axis, so every mode gets the same
    count), at least :data:`MIN_POINTS`, with every row of the table on it."""
    import numpy as np

    low, high = table[0][0], table[-1][0]
    span = math.log(high / low)
    step = min(2.0 * zeta / points, span / MIN_POINTS)
    count = int(math.ceil(span / step)) + 1
    grid = np.unique(np.concatenate([np.exp(np.linspace(math.log(low), math.log(high), count)), [row[0] for row in table]]))
    # A row that falls on a grid point within rounding is that point.
    return grid[np.concatenate([[True], np.diff(np.log(grid)) > 1e-9])]


def trapezoid_weights(f: "np.ndarray") -> "np.ndarray":
    """Weights w with Σ w g(f) the trapezoid rule's ∫ g df over the points ``f``."""
    import numpy as np

    w = np.zeros(len(f))
    if len(f) > 1:
        d = np.diff(f)
        w[:-1] += 0.5 * d
        w[1:] += 0.5 * d
    return w


def grid_error(zeta: float, points: int) -> float:
    """The trapezoid rule's relative error on a grid of ``points`` per half-power bandwidth, for one resonance
    under a flat PSD: ∫ |H|² df on that grid against the same integral on a grid ten times finer, measured."""
    import numpy as np

    f_n = 1.0
    span = 60.0 * zeta  # ±30 bandwidths around the mode, in log
    f = np.exp(np.arange(-span, span, 2.0 * zeta / points))
    w = _TWO_PI * f
    H2 = 1.0 / np.abs((_TWO_PI * f_n) ** 2 - w ** 2 + 2j * zeta * _TWO_PI * f_n * w) ** 2
    reference = np.exp(np.arange(-span, span, 2.0 * zeta / (10 * points)))
    wr = _TWO_PI * reference
    H2r = 1.0 / np.abs((_TWO_PI * f_n) ** 2 - wr ** 2 + 2j * zeta * _TWO_PI * f_n * wr) ** 2
    coarse = float(trapezoid_weights(f) @ H2)
    fine = float(trapezoid_weights(reference) @ H2r)
    return abs(coarse - fine) / fine


# -- modal superposition of a PSD --------------------------------------------------------------------

def modal_covariance(omega_modes: "np.ndarray", gamma: "np.ndarray", grid_Hz: "np.ndarray", psd_mm2_s4_Hz: "np.ndarray",
                     zeta: float, *, chunk: int = CHUNK) -> tuple["np.ndarray", "np.ndarray"]:
    """(C0, C2), each (m, m) real: the modal coordinates' covariance ∫ S_qq df and its second moment
    ∫ f² S_qq df, for a base shaken with acceleration PSD ``psd_mm2_s4_Hz`` ((mm/s²)²/Hz) on ``grid_Hz``.
    S_qq(f) = (Γ⊙H)(Γ⊙H)ᴴ S_a(f); its real part is what a real response reads (the imaginary part is odd)."""
    import numpy as np

    from cadgen._internal.fea import superposition as sp

    m = len(omega_modes)
    weights = trapezoid_weights(grid_Hz) * psd_mm2_s4_Hz
    C0 = np.zeros((m, m), dtype=complex)
    C2 = np.zeros((m, m), dtype=complex)
    for start in range(0, len(grid_Hz), chunk):
        stop = min(start + chunk, len(grid_Hz))
        G = sp.transfer(omega_modes, _TWO_PI * grid_Hz[start:stop], zeta) * gamma[None, :]   # (n, m)
        w = weights[start:stop]
        C0 += (G.conj().T * w[None, :]) @ G
        C2 += (G.conj().T * (w * grid_Hz[start:stop] ** 2)[None, :]) @ G
    return C0.real.copy(), C2.real.copy()


def rms_displacement(shapes: "np.ndarray", C: "np.ndarray") -> "np.ndarray":
    """(nodes,): the RMS size of each node's motion, sqrt(Σ_c φ_cᵀ C φ_c), ``shapes`` (m, nodes, 3) the modes per node."""
    import numpy as np

    if len(shapes) == 0:
        return np.zeros(shapes.shape[1])
    T = np.tensordot(C, shapes, axes=(1, 0))
    return np.sqrt(np.maximum(np.einsum("inc,inc->n", T, shapes), 0.0))


def rms_von_mises(stresses: "np.ndarray", C: "np.ndarray") -> "np.ndarray":
    """(nodes,): Segalman's RMS von Mises, sqrt(tr(A S_σσ)) = sqrt(Σᵢⱼ Cᵢⱼ ψᵢᵀ A ψⱼ), ``stresses`` (m, 6, nodes)."""
    import numpy as np

    if len(stresses) == 0:
        return np.zeros(stresses.shape[2])
    A = von_mises_form()
    AS = np.einsum("kl,iln->ikn", A, stresses)
    T = np.tensordot(C, stresses, axes=(1, 0))
    return np.sqrt(np.maximum(np.einsum("ikn,ikn->n", T, AS), 0.0))


def _thin(values, count: int) -> list[int]:
    n = len(values)
    if n <= count:
        return list(range(n))
    step = int(math.ceil(n / count))
    keep = list(range(0, n, step))
    if keep[-1] != n - 1:
        keep.append(n - 1)
    return keep


def _sigma_text(value: float, unit: str, sigma: int) -> str:
    return f"{value:.3g} {unit} at {sigma}σ"


class RandomVibrationAnalysis:
    name: ClassVar[str] = "random_vibration"
    tier: ClassVar[int] = 1
    word: ClassVar[str] = "Random vibration"
    estimate_only: ClassVar[bool] = False
    limits: ClassVar[tuple[str, ...]] = ()
    study_keys: ClassVar[frozenset[str]] = frozenset({"fixtures", "psd", "damping_ratio", "sigma"})
    material_needs: ClassVar[frozenset[str]] = frozenset({"density"})
    mesh_orders: ClassVar[tuple[int, ...]] = (2,)
    connection_types: ClassVar[tuple[str, ...]] = ("bonded", "free")
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec("von_mises_rms", "_VON_MISES_RMS", "von Mises stress (RMS, 1σ)", "MPa"),
        FieldSpec("displacement_rms", "_DISPLACEMENT_RMS", "displacement (RMS, 1σ, relative to the base)", "mm"),
    )
    checks: ClassVar[tuple] = (kinds.STRESS, kinds.DISPLACEMENT)
    default_checks: ClassVar[tuple[dict, ...]] = ({"kind": "stress"},)
    drives: ClassVar[tuple[str, ...]] = ("field", "load_scale", "threshold", "sigma")
    default_controls: ClassVar[dict[str, dict]] = {
        "field": {"drives": "field", "type": "enum", "options": ["von_mises_rms", "displacement_rms"]},
        "sigma": {"drives": "sigma", "type": "enum", "options": [1, 3], "default": 3},
    }
    upstream: ClassVar[tuple[str, ...]] = ()
    ladder: ClassVar[tuple[str, ...]] = (
        "reduce_modes", "frequency_grid", "iterative", "local_refine", "defeature", "linear_elements", "symmetry",
    )
    noun: ClassVar[str] = "this shake"
    governing_word: ClassVar[str] = "RMS stress"
    stress_label: ClassVar[str] = "Random vibration"

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> RandomVibrationInputs:
        fixtures = parse_fixtures(document)
        raw = document.get("psd")
        if not isinstance(raw, dict):
            raise ValueError('psd: the random shake, like {"direction": [0, 0, 1], "table": [[20, 0.01], [80, 0.04], '
                             '[350, 0.04], [2000, 0.007]]} (Hz against g²/Hz)')
        unknown = set(raw) - {"direction", "table"}
        if unknown:
            raise ValueError(f"psd: unknown keys {sorted(unknown)}; a psd takes direction and table")
        direction = raw.get("direction")
        if not isinstance(direction, list) or len(direction) != 3:
            raise ValueError("psd.direction: the direction it is shaken along as [x, y, z], like [0, 0, 1] for Z")
        values = [kinds.number(v, where="psd.direction") for v in direction]
        size = math.sqrt(sum(v * v for v in values))
        if size == 0:
            raise ValueError("psd.direction: the direction is zero; give the axis it is shaken along, like [0, 0, 1]")
        unit = tuple(v / size for v in values)
        table = raw.get("table")
        if not isinstance(table, list) or len(table) < 2:
            raise ValueError("psd.table: at least two rows of [Hz, g²/Hz], like [[20, 0.01], [2000, 0.01]]")
        rows: list[tuple[float, float]] = []
        for index, row in enumerate(table):
            where = f"psd.table[{index}]"
            if not isinstance(row, list) or len(row) != 2:
                raise ValueError(f"{where}: a row is [Hz, g²/Hz], like [80, 0.04]")
            f = kinds.number(row[0], where=f"{where}[0]", positive=True)
            p = kinds.number(row[1], where=f"{where}[1]", positive=True)
            if rows and not f > rows[-1][0]:
                raise ValueError(f"{where}: frequencies must rise from row to row; {f:g} Hz follows {rows[-1][0]:g} Hz")
            rows.append((f, p))
        zeta = kinds.number(document.get("damping_ratio", 0.02), where="damping_ratio", positive=True)
        if zeta >= 1:
            raise ValueError(f"damping_ratio: a share of critical damping, like 0.02 for 2 %; must be under 1, got {zeta:g}")
        sigma = document.get("sigma", 3)
        if isinstance(sigma, bool) or sigma not in SIGMAS:
            raise ValueError(f"sigma: the level the checks judge at, 1 or 3 (standard deviations), got {kinds.json_text(sigma)}")
        refs = tuple(dict.fromkeys(ref for fixture in fixtures for ref in fixture.faces))
        return RandomVibrationInputs(refs, refs, True, fixtures=fixtures, direction=unit, table=tuple(rows),
                                     damping_ratio=zeta, sigma=int(sigma))

    # -- the ladder (fit.py drives these) -------------------------------------------------------------

    def _grid_points(self, ctx, inputs: RandomVibrationInputs) -> int:
        plan = getattr(ctx, "plan", None)
        per = COARSE_POINTS if getattr(plan, "frequency_grid", False) else POINTS_PER_BANDWIDTH
        low, high = inputs.band_Hz
        span = math.log(high / low)
        return int(span / min(2.0 * inputs.damping_ratio / per, span / MIN_POINTS)) + 1

    def estimate(self, ctx: SolveContext, inputs: RandomVibrationInputs):
        """Finding the modes (:func:`modal.eigen_estimate`), each kept mode's stress (six components per node)
        and shape, the frequency grid's m × m covariance, and the two quadratic forms over every node."""
        from cadgen._internal.fea import fit

        plan = getattr(ctx, "plan", None)
        modes = int(getattr(plan, "modes", None) or GUESS_MODES)
        base = eigen_estimate(ctx, modes)
        nodes = base.dofs / 3.0
        grid = self._grid_points(ctx, inputs)
        memory = base.memory_bytes + 8.0 * 9 * nodes * modes * 2 + 16.0 * min(grid, CHUNK) * modes * 2 + 8.0 * 4 * nodes
        seconds = base.seconds + modes * fit.SECONDS_PER_ELEMENT.get(getattr(plan, "order", 2), 2.5e-4) * nodes / 1.7 \
            + 2e-8 * grid * modes * modes + 4e-9 * 2 * 9 * modes * modes * nodes
        return fit.Estimate(dofs=base.dofs, memory_bytes=int(memory), seconds=float(seconds))

    def apply(self, rung, ctx: SolveContext, inputs: RandomVibrationInputs):
        """``reduce_modes``: keep only the fewest modes holding 90 % of the mass moving along the shake.
        ``frequency_grid``: a coarser frequency grid, its accuracy measured on one resonance. ``iterative``:
        LOBPCG instead of factorising. The mesh rungs the shared way; ``symmetry`` and ``idealise`` are not
        taken for a modal response yet."""
        from cadgen._internal.fea import fit

        plan = ctx.plan
        if rung == "reduce_modes":
            if plan.modes is not None and plan.modes <= REDUCED_GUESS:
                return None
            plan.modes = REDUCED_GUESS
            step = fit.Step("reduce_modes", f"Kept only the fewest modes holding {KEEP_SHARE * 100:.0f}% of the mass moving "
                            f"along {axis_words(inputs.direction)}, to fit", None, None, detail={"keep_share": KEEP_SHARE})
            return step
        if rung == "frequency_grid":
            if plan.frequency_grid:
                return None
            plan.frequency_grid = True
            error = grid_error(inputs.damping_ratio, COARSE_POINTS) * 100.0
            moved = "under 0.1%" if error < 0.1 else f"about {error:.2g}%"
            return fit.Step(
                "frequency_grid",
                f"Integrated the response on a coarser frequency grid, {COARSE_POINTS} points across each resonance "
                f"instead of {POINTS_PER_BANDWIDTH}, to fit",
                f"a single resonance's RMS moves {moved} on the coarser grid", error,
                detail={"points_per_bandwidth": COARSE_POINTS, "from_points_per_bandwidth": POINTS_PER_BANDWIDTH},
            )
        return apply_eigen_rung(self, rung, ctx, inputs, words="Found the modes with an iterative solver (LOBPCG with "
                                "multigrid) instead of factorising the stiffness")

    def governing(self, result: AnalysisResult) -> tuple["np.ndarray", float]:
        """local_refine keeps the mesh fine where the RMS stress is highest; two passes compare that peak."""
        field = result.fields["von_mises_rms"]
        return field, float(field.max())

    # -- solve ---------------------------------------------------------------------------------------

    def solve(self, ctx: SolveContext, inputs: RandomVibrationInputs) -> AnalysisResult:
        import time

        import numpy as np

        from cadgen._internal.fea import operators
        from cadgen._internal.fea import superposition as sp

        space = ctx.space
        plan = getattr(ctx, "plan", None)
        timings: dict[str, float] = {}
        warnings: list[str] = []
        started = time.perf_counter()
        materials = materials_of(ctx)
        K = operators.stiffness(space, materials)
        M = operators.mass(space, materials)
        fixed = fixed_dofs(space, inputs.fixtures, ctx.ordinal_of)
        zeta = inputs.damping_ratio
        direction = np.asarray(inputs.direction, dtype=float)
        r = sp.rigid_translation(space.component, direction)
        Mr = M @ r
        total_along = float(r @ Mr)
        timings["assemble_s"] = time.perf_counter() - started

        reduce = "reduce_modes" in (getattr(plan, "taken", None) or ())
        enough = None
        if reduce and total_along > 0:
            def enough(omega2, vectors, free):
                return float(((vectors.T @ Mr[free]) ** 2).sum()) / total_along >= KEEP_SHARE

        started = time.perf_counter()
        method = solver_method(ctx, space.dofs - len(fixed))
        found = sp.find_modes(K, M, fixed, inputs.top_Hz, method=method, locations=space.locations,
                              component=space.component, enough=enough)
        warnings.extend(found.warnings)
        found.vectors = align_degenerate(found.vectors, M, found.frequencies_Hz, space.component)
        timings["eigen_s"] = time.perf_counter() - started
        if ctx.log:
            ctx.log(f"random_vibration: {len(found)} modes up to {found.frequencies_Hz[-1]:.4g} Hz ({found.how})")

        fractions = sp.mass_fractions(found, M, space.component)
        gamma_all = sp.participation(found, M, r)
        masses = gamma_all ** 2
        along_share = float(masses.sum() / total_along) if total_along > 0 else None
        kept = np.arange(len(found))
        kept_share = None
        reduce_step = None
        if reduce:
            kept, kept_share = sp.fewest_modes(masses, total_along, KEEP_SHARE)
            reduce_step = self._reduce_step(inputs, found, kept, kept_share)
        used = found.take(kept)
        gamma = gamma_all[kept]

        started = time.perf_counter()
        shapes = sp.nodal_shapes(space, used)
        stresses = sp.modal_stresses(space, materials, used)
        timings["stress_s"] = time.perf_counter() - started

        started = time.perf_counter()
        per = COARSE_POINTS if getattr(plan, "frequency_grid", False) else POINTS_PER_BANDWIDTH
        grid = response_grid(inputs.table, zeta, per)
        S_a = psd_at(inputs.table, grid) * G0_MM_S2 ** 2
        C0, C2 = modal_covariance(used.omega, gamma, grid, S_a, zeta)
        displacement = rms_displacement(shapes, C0)
        von_mises = rms_von_mises(stresses, C0)
        with np.errstate(divide="ignore", invalid="ignore"):
            nu_stress = np.sqrt(np.where(von_mises > 0, rms_von_mises(stresses, C2) ** 2 / np.maximum(von_mises, 1e-300) ** 2, 0.0))
        s_node = int(von_mises.argmax())
        d_node = int(displacement.argmax())
        nu_disp_num = float(rms_displacement(shapes[:, d_node:d_node + 1], C2)[0])
        nu_disp = nu_disp_num / float(displacement[d_node]) if displacement[d_node] > 0 else 0.0
        # Each mode's own share of the RMS stress at the peak (the diagonal terms; cross terms are shared).
        A = von_mises_form()
        psi = stresses[:, :, s_node]                                                       # (m, 6)
        diagonal = np.diag(C0) * np.einsum("ik,kl,il->i", psi, A, psi)
        stress_share = diagonal / diagonal.sum() if diagonal.sum() > 0 else np.zeros(len(used))
        timings["psd_s"] = time.perf_counter() - started

        curves = self._curves(inputs, used, gamma, grid, S_a, stresses[:, :, s_node], shapes[:, d_node, :], zeta)
        in_band = [i for i, f in enumerate(found.frequencies_Hz) if inputs.band_Hz[0] <= f <= inputs.band_Hz[1]]
        return AnalysisResult(
            dof_locations=space.dof_locations,
            vertices=space.vertices,
            tets=space.tets,
            boundary_quadratic=space.boundary_quadratic,
            element_dofs=space.element_dofs,
            fields={"von_mises_rms": von_mises, "displacement_rms": displacement},
            deformation=None,
            curves=curves,
            scalars={
                "frequencies_Hz": [float(f) for f in found.frequencies_Hz],
                "effective_mass_fractions": fractions.tolist(),
                "participation": [float(g) for g in gamma_all],
                "stress_share": {int(i): float(s) for i, s in zip(kept, stress_share)},
                "used_modes": [int(i) for i in kept],
                "modes_in_band": in_band,
                "kept_share": kept_share,
                "reduce_step": reduce_step,
                "along_share": along_share,
                "direction": [float(c) for c in direction],
                "searched_Hz": found.searched_Hz,
                "total_mass_kg": float(sum(M @ (space.component == 0).astype(float))) * 1000.0,
                "grid_points": int(len(grid)),
                "points_per_bandwidth": per,
                "stress_node": s_node,
                "displacement_node": d_node,
                "zero_crossing_Hz": float(nu_stress[s_node]),
                "displacement_zero_crossing_Hz": nu_disp,
                "stress_zero_crossing_Hz": nu_stress,
                "analysis_warnings": [],
                "study_checks": tuple(getattr(ctx.study, "checks", ()) or ()),
                "margin": float(getattr(ctx.study, "margin", 2.0) or 2.0),
                "parts": None if ctx.assembly is None else [
                    {"ref": part.ref, "name": name, "material": material.name}
                    for part, name, material in zip(ctx.assembly.parts, ctx.assembly.names, ctx.assembly.materials)
                ],
                "yields": [m.yield_strength for m in ctx.materials],
                "node_domain": _node_domain(space),
            },
            dofs=int(space.dofs),
            solver=f"{found.how}; modal superposition of {len(used)} mode{'s' if len(used) != 1 else ''} "
                   f"over {len(grid)} frequencies",
            timings=timings,
            warnings=warnings,
        )

    @staticmethod
    def _curves(inputs, used, gamma, grid, S_a, psi, phi, zeta) -> dict:
        """The input PSD and the response PSDs at the peaks (von Mises's equivalent tr(A S_σσ), and the
        displacement's size), on the grid thinned to at most :data:`CURVE_POINTS`."""
        import numpy as np

        from cadgen._internal.fea import superposition as sp

        keep = _thin(grid, CURVE_POINTS)
        f = grid[keep]
        G = sp.transfer(used.omega, _TWO_PI * f, zeta) * gamma[None, :]                 # (n, m)
        A = von_mises_form()
        Z = G @ psi                                                                      # (n, 6)
        stress = np.einsum("nk,kl,nl->n", Z.conj(), A, Z).real * S_a[keep]
        U = G @ phi                                                                      # (n, 3)
        moved = np.einsum("nc,nc->n", U.conj(), U).real * S_a[keep]
        x = [round(float(v), 6) for v in f]
        return {
            "input_psd_g2_Hz": {"x": x, "x_unit": "Hz", "y": [float(f"{v:.6g}") for v in S_a[keep] / G0_MM_S2 ** 2],
                                "y_unit": "g²/Hz"},
            "stress_psd_MPa2_Hz": {"x": x, "x_unit": "Hz", "y": [float(f"{v:.6g}") for v in stress], "y_unit": "MPa²/Hz"},
            "displacement_psd_mm2_Hz": {"x": x, "x_unit": "Hz", "y": [float(f"{v:.6g}") for v in moved], "y_unit": "mm²/Hz"},
        }

    @staticmethod
    def _reduce_step(inputs: RandomVibrationInputs, found, kept, share: float | None) -> dict:
        """reduce_modes' words once the modes are found, for :meth:`settle_steps`."""
        words = (f"Kept {len(kept)} of the {len(found)} modes up to {hz_text(found.searched_Hz)}, the ones holding "
                 f"{(share or 0.0) * 100:.0f}% of the mass moving along {axis_words(inputs.direction)}, to fit")
        return {"words": words,
                "detail": {"kept_modes": len(kept), "found_modes": len(found), "kept_share": round(share or 0.0, 4)}}

    def settle_steps(self, result: AnalysisResult, steps: list) -> list:
        """reduce_modes' step said again once the modes are found: how many it kept and the share they hold
        (run.py calls this after the solve, before writing; the solve leaves the words in ``reduce_step``)."""
        from cadgen._internal.fea import fit

        return fit.settle_step(steps, "reduce_modes", result.scalars.get("reduce_step"), marker="keep_share")

    # -- checks, findings ----------------------------------------------------------------------------

    def _yield_at(self, result: AnalysisResult, node: int) -> float:
        domains = result.scalars["node_domain"]
        yields = result.scalars["yields"]
        if domains is None or len(yields) == 1:
            return yields[0]
        return yields[int(domains[node])]

    def needs_finer(self, result: AnalysisResult, inputs: RandomVibrationInputs, check_results: list[dict]) -> bool:
        """Solve once more finer when the stress check is close: sigma × the RMS peak between yield over the margin and yield."""
        if check_results:
            return any(check["status"] == "close" for check in check_results)
        if not any(check.get("kind") == "stress" for check in result.scalars["study_checks"]):
            return False
        node = result.scalars["stress_node"]
        ratio = inputs.sigma * float(result.fields["von_mises_rms"][node]) / self._yield_at(result, node)
        return 1.0 / result.scalars["margin"] < ratio <= 1.0

    def refined_record(self, result: AnalysisResult, size_mm: float, finer_mm: float, *, assembly: bool) -> dict:
        return {"from_size_mm": round(size_mm, 4), "from_max_von_mises_rms_MPa": round(float(result.fields["von_mises_rms"].max()), 4),
                "size_mm": round(finer_mm, 4), "max_von_mises_rms_MPa": None}

    def merge_finer(self, coarse: AnalysisResult, finer: AnalysisResult, refined: dict) -> AnalysisResult:
        refined["max_von_mises_rms_MPa"] = round(float(finer.fields["von_mises_rms"].max()), 4)
        finer.scalars["coarser_peak_MPa"] = float(coarse.fields["von_mises_rms"].max())
        return finer

    def judge(self, check: dict, index: int, ctx: SolveContext, result: AnalysisResult,
              inputs: RandomVibrationInputs) -> dict:
        from cadgen._internal.fea import checks
        from cadgen._internal.fea.analyses.static import _peak_face

        sigma = inputs.sigma
        if check["kind"] == "stress":
            node = result.scalars["stress_node"]
            peak = sigma * float(result.fields["von_mises_rms"][node])
            fixed = {ctx.ordinal_of[ref] for fixture in inputs.fixtures for ref in fixture.faces}
            at = tuple(float(c) for c in result.dof_locations[node])
            solved = checks.Solved(
                material_name="", yield_MPa=self._yield_at(result, node), peak_MPa=peak, peak_gauss_MPa=peak, peak_at=at,
                peak_face=_peak_face(ctx.volume, result, node, fixed), fixed_faces=(), max_displacement_mm=0.0,
                displacement_at=at, bbox_diagonal_mm=0.0, margin=result.scalars["margin"], coarser_peak_MPa=None, part="",
            )
            return checks.stress_check(solved, label=check.get("label") or self.stress_label)
        peak = kinds.field_max_over(
            sigma * result.fields["displacement_rms"], tuple(check.get("faces", ())), boundary=result.boundary_quadratic,
            boundary_ordinal=ctx.volume.boundary_ordinal, locations=result.dof_locations, face_ref=ctx.volume.faces,
            ordinal_of=ctx.ordinal_of, where=f"view.checks[{index}]",
        )
        return checks.displacement_check(peak.value, check["limit_mm"], at=peak.at, ref=peak.ref, faces=peak.faces,
                                         label=check.get("label"))

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: RandomVibrationInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        from cadgen._internal.fea.analyses.modal import finding

        scalars = result.scalars
        whole = "the assembly" if assembly else "the part"
        sigma = inputs.sigma
        shaken = f"Shaken at random at {inputs.grms:.3g} g rms along {axis_words(inputs.direction)}"
        found: list[dict] = []
        for check in check_results:
            status = check["status"]
            if status not in ("fails", "close"):
                continue
            severity = "error" if status == "fails" else "warning"
            item = [{"text": check["label"], **check["where"]}]
            if check["kind"] == "stress":
                if status == "fails":
                    sentence = (f"{shaken}, {whole} reaches {check['value']:.3g} MPa at {sigma}σ, over its "
                                f"{check['limit']:g} MPa yield ({check['label']})")
                else:
                    sentence = (f"{shaken}, {whole} reaches {check['value']:.3g} MPa at {sigma}σ, inside the "
                                f"{check['margin']:g}× margin under its {check['limit']:g} MPa yield ({check['label']})")
                found.append(finding(severity, "random_yields" if status == "fails" else "random_close_to_yield", sentence,
                                     f"von Mises RMS {check['value'] / sigma:.4g} MPa, times {sigma} for {sigma}σ "
                                     f"(a Gaussian response stays under {sigma}σ {'68.3' if sigma == 1 else '99.7'}% of the time)",
                                     item))
            elif check["kind"] == "displacement" and status == "close":
                found.append(finding("warning", "displacement_close",
                                     f"{shaken}, it moves {check['value']:.3g} mm at {sigma}σ, close to the {check['limit']:g} mm "
                                     f"allowed ({check['label']})", "the displacement is relative to where it is held", item))
        node = scalars["stress_node"]
        stress_rms = float(result.fields["von_mises_rms"][node])
        moved_rms = float(result.fields["displacement_rms"].max())
        shares = scalars["stress_share"]
        frequencies = scalars["frequencies_Hz"]
        dominant = max(shares, key=shares.get) if shares else None
        mode_words = ""
        if dominant is not None and shares[dominant] > 0:
            mode_words = (f"; mode {dominant + 1} at {hz_text(frequencies[dominant])} carries "
                          f"{shares[dominant] * 100:.0f}% of the stress")
        found.append(finding(
            "info", "random_response",
            f"{shaken}, its stress is {stress_rms:.3g} MPa rms ({_sigma_text(sigma * stress_rms, 'MPa', sigma)}) and it moves "
            f"{moved_rms:.3g} mm rms ({_sigma_text(sigma * moved_rms, 'mm', sigma)}){mode_words}",
            f"the stress swings through zero about {scalars['zero_crossing_Hz']:.3g} times a second at its peak "
            "(the rate fatigue counts cycles at)",
            [{"text": "stressed most here", "ref": None, "at": [round(float(c), 3) for c in result.dof_locations[node]]}],
        ))
        low, high = inputs.band_Hz
        if not scalars["modes_in_band"]:
            found.append(finding(
                "info", "no_resonance_in_band",
                f"No natural frequency lies between {low:g} and {high:g} Hz: {whole} follows the shake without resonating"
                + (f"; its first mode is {hz_text(frequencies[0])}" if frequencies else ""),
                "the response stays near its static value under the PSD", [],
            ))
        share = scalars["along_share"]
        if share is not None and share < MASS_WARNING:
            along = axis_words(scalars["direction"])
            found.append(finding(
                "warning", "modes_missing_mass",
                f"The modes up to {hz_text(scalars['searched_Hz'])} move only {share * 100:.0f}% of the mass along {along}: "
                f"the rest answers above them, so the response may read a little low",
                f"effective mass of the modes found {share:.3f} of the total along {along}; "
                "a fixed face's own mass never moves, and modes above 1.5× the PSD's top are left out", [],
            ))
        coarser = scalars.get("coarser_peak_MPa")
        if coarser:
            peak = float(result.fields["von_mises_rms"].max())
            moved = abs(peak - coarser) / coarser if coarser > 0 else 0.0
            found.append(finding(
                "warning" if moved > 0.1 else "info", "mesh_not_converged" if moved > 0.1 else "mesh_converged",
                f"The RMS stress moved {moved * 100:.1f} % on a finer mesh ({coarser:.3g} to {peak:.3g} MPa)",
                "a check was close, so the part was solved again finer; the finer answer is the one reported", [],
            ))
        return sorted(found, key=lambda item: {"error": 0, "warning": 1, "info": 2}[item["severity"]])

    # -- what is written -----------------------------------------------------------------------------

    def deformation_scale(self, result: AnalysisResult, bbox_diagonal: float, requested: float | None) -> float | None:
        # An RMS has no sign or phase to deform by: the model is drawn as it is.
        return None

    def summary(self, result: AnalysisResult, inputs: RandomVibrationInputs, check_results: list[dict]) -> dict:
        scalars = result.scalars
        sigma = inputs.sigma
        s_node = scalars["stress_node"]
        d_node = scalars["displacement_node"]
        stress_rms = float(result.fields["von_mises_rms"][s_node])
        moved_rms = float(result.fields["displacement_rms"][d_node])
        yield_MPa = self._yield_at(result, s_node)
        factor = yield_MPa / (sigma * stress_rms) if stress_rms > 0 else None
        used = set(scalars["used_modes"])
        direction = scalars["direction"]
        axis = max(range(3), key=lambda c: abs(direction[c]))
        shares = scalars["stress_share"]
        grms_input = inputs.grms
        summary: dict[str, Any] = {
            "psd": {"direction": list(inputs.direction), "table": [list(row) for row in inputs.table],
                    "band_Hz": list(inputs.band_Hz)},
            "grms_input": round(grms_input, 6),
            "damping_ratio": inputs.damping_ratio,
            "sigma": sigma,
            "max_von_mises_rms_MPa": round(stress_rms, 4),
            "max_von_mises_MPa": round(sigma * stress_rms, 4),
            "max_von_mises_at_mm": [round(float(c), 3) for c in result.dof_locations[s_node]],
            "yield_MPa": yield_MPa,
            "safety_factor": None if factor is None else math.floor(factor * 1000) / 1000,
            "max_displacement_rms_mm": round(moved_rms, 6),
            "max_displacement_mm": round(sigma * moved_rms, 6),
            "max_displacement_at_mm": [round(float(c), 3) for c in result.dof_locations[d_node]],
            "zero_crossing_Hz": round(scalars["zero_crossing_Hz"], 4),
            "displacement_zero_crossing_Hz": round(scalars["displacement_zero_crossing_Hz"], 4),
            "modes": [
                {"mode": i + 1, "frequency_Hz": round(f, 4), "effective_mass_fraction": [round(x, 4) for x in share],
                 "participation_factor": round(scalars["participation"][i] * math.sqrt(1000.0), 6),
                 "stress_share": round(shares.get(i, 0.0), 4), "used": i in used}
                for i, (f, share) in enumerate(zip(scalars["frequencies_Hz"], scalars["effective_mass_fractions"]))
            ],
            "modes_used": len(used),
            "modes_up_to_Hz": round(inputs.top_Hz, 4),
            "effective_mass_fraction": None if scalars["along_share"] is None else round(scalars["along_share"], 4),
            "effective_mass_axis": _AXES[axis],
            "total_mass_kg": round(scalars["total_mass_kg"], 6),
            "frequency_points": scalars["grid_points"],
            "points_per_bandwidth": scalars["points_per_bandwidth"],
            "deformation_scale": scalars["deformation_scale"],
        }
        if scalars["kept_share"] is not None:
            summary["kept_share"] = round(scalars["kept_share"], 4)
        if scalars.get("parts"):
            summary["parts"] = scalars["parts"]
        summary["checks"] = check_results
        return summary

    def extras_name(self, stem: str) -> str:
        return f"{stem} random vibration"

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        return {"von_mises_rms": (0.0, summary["max_von_mises_rms_MPa"]),
                "displacement_rms": (0.0, summary["max_displacement_rms_mm"])}

    def extras_head(self, summary: dict) -> dict:
        return {"safety_factor": summary["safety_factor"], "grms_input": summary["grms_input"],
                "zero_crossing_Hz": summary["zero_crossing_Hz"]}

    def extras_assembly(self, summary: dict) -> dict:
        return {"parts": summary.get("parts", [])}

    def study_echo(self, inputs: RandomVibrationInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        return {
            "fixtures": [{"type": fixture.type, "faces": bare(fixture.faces)} for fixture in inputs.fixtures],
            "psd": {"direction": list(inputs.direction), "table": [list(row) for row in inputs.table],
                    "grms": round(inputs.grms, 6)},
            "damping_ratio": inputs.damping_ratio,
            "sigma": inputs.sigma,
        }

    def human_lines(self, summary: dict) -> list[str]:
        psd = summary["psd"]
        low, high = psd["band_Hz"]
        sigma = summary["sigma"]
        lines = [
            f"shaken at random, {summary['grms_input']:.3g} g rms along {axis_words(psd['direction'])} from {low:g} to "
            f"{high:g} Hz, {summary['damping_ratio'] * 100:g}% damping; judged at {sigma}σ",
            f"stress {summary['max_von_mises_rms_MPa']:.4g} MPa rms ({summary['max_von_mises_MPa']:.4g} MPa at {sigma}σ); "
            f"moves {summary['max_displacement_rms_mm']:.4g} mm rms ({summary['max_displacement_mm']:.4g} mm at {sigma}σ); "
            f"about {summary['zero_crossing_Hz']:.4g} stress cycles a second",
        ]
        modes = f"{summary['modes_used']} mode{'s' if summary['modes_used'] != 1 else ''} up to {hz_text(summary['modes_up_to_Hz'])}"
        if summary.get("effective_mass_fraction") is not None:
            modes += f", holding {summary['effective_mass_fraction'] * 100:.0f}% of the mass along {summary['effective_mass_axis']}"
        lines.append(modes)
        return lines


def _node_domain(space) -> "np.ndarray | None":
    """Each node's part (the domain of an element it belongs to), for an assembly; None for one part."""
    import numpy as np

    if space.domain is None:
        return None
    out = np.zeros(space.scalar_count, dtype=np.int64)
    out[space.scalar.element_dofs] = np.asarray(space.domain)[None, :]
    return out
