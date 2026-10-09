"""What an engineer checks on a stress result, as findings in plain words.

The KiCad findings' shape (``check``, ``severity``, ``type``, ``summary``,
``description``, ``items``), so the viewer's alert card and the agent read FEA
the way they read a board. Errors are what make the part unfit to use; the
rest are suggestions. Stdlib only: nothing here needs the solver.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = ["CONVERGED_WITHIN", "GAUSS_RATIO", "LARGE_DISPLACEMENT", "RESOLVE_BELOW", "Solved", "findings", "needs_finer", "safety_factor"]

#: Re-solve finer only when the safety factor is this close to failing.
RESOLVE_BELOW = 3.0
#: A finer mesh moving the peak more than this share: not converged.
CONVERGED_WITHIN = 0.10
#: Displacement over this share of the part's size is a large displacement.
LARGE_DISPLACEMENT = 0.01
#: A Gauss-point peak over the nodal peak by this factor: an unresolved concentration.
GAUSS_RATIO = 1.5


@dataclass(frozen=True)
class Solved:
    """The numbers of one solved study the checks read."""

    material_name: str
    yield_MPa: float
    #: Peak von Mises stress recovered at the nodes.
    peak_MPa: float
    #: Peak von Mises stress at the Gauss points, before smoothing.
    peak_gauss_MPa: float
    peak_at: tuple[float, float, float]
    #: The ``#o1.fN`` face the peak sits on, when it sits on one.
    peak_face: str | None
    fixed_faces: tuple[str, ...]
    max_displacement_mm: float
    displacement_at: tuple[float, float, float]
    bbox_diagonal_mm: float
    #: The study's required safety factor.
    margin: float
    #: The first, coarser solve's nodal peak, when the written solve is a finer
    #: re-solve; ``None`` when the part was solved once. Only convergence reads it.
    coarser_peak_MPa: float | None
    part: str


def safety_factor(solved: Solved) -> float | None:
    """Yield over the written solve's peak stress, or ``None`` when no load reaches the part."""
    return solved.yield_MPa / solved.peak_MPa if solved.peak_MPa > 0 else None


def needs_finer(safety_factor: float | None) -> bool:
    """Whether the safety factor is close enough to failing to justify a finer solve."""
    return safety_factor is not None and safety_factor < RESOLVE_BELOW


def _number(value: float, extra: int = 0) -> str:
    """Three significant figures, whole numbers from 100 up; ``extra`` adds decimals."""
    return f"{value:.{3 + extra}g}" if value < 100 else f"{value:.{extra}f}"


def _distinct(low: float, high: float) -> tuple[str, str]:
    """Both numbers printed with enough decimals that they never read as equal."""
    for extra in range(3):
        if _number(low, extra) != _number(high, extra):
            break
    return _number(low, extra), _number(high, extra)


def _item(text: str, ref: str | None, at: tuple[float, float, float]) -> dict:
    return {"text": text, "ref": ref, "at": [round(c, 3) for c in at]}


def findings(solved: Solved) -> list[dict]:
    """The findings for one solved study, errors first."""
    found: list[dict] = []
    peak = _item("the peak stress", solved.peak_face, solved.peak_at)
    factor = safety_factor(solved)
    peak_MPa = solved.peak_MPa

    def add(severity: str, kind: str, summary: str, description: str, items: list[dict]) -> None:
        found.append(
            {
                "check": "fea",
                "severity": severity,
                "type": kind,
                "summary": summary,
                "description": description,
                "items": items,
            }
        )

    if factor is None:
        add(
            "warning",
            "no_load",
            "No load reaches the part: check the loads are on faces connected to the fixed ones",
            "the peak stress is zero",
            [],
        )

    # Peak findings matter only while the part is short of its margin.
    on_fixture = solved.peak_face in solved.fixed_faces
    spike = solved.peak_gauss_MPa > GAUSS_RATIO * solved.peak_MPa
    qualifier = ""
    peak_finding = None
    if factor is not None and factor < solved.margin and (on_fixture or spike):
        if on_fixture:
            qualifier = " (the peak sits at the fixed face)"
            peak_finding = (
                "peak_at_fixture",
                "The peak sits where the part is held, where the model can exaggerate it: "
                "check the stress a little away from the fixed face before redesigning",
                f"nodal peak {_number(solved.peak_MPa)} MPa, Gauss-point peak {_number(solved.peak_gauss_MPa)} MPa",
                [peak],
            )
        else:
            qualifier = " (the peak is a local spike)"
            peak_finding = (
                "peak_concentration",
                "The peak is a sharp local spike the mesh can't resolve (a sharp corner or a concentrated load): "
                "a fillet or a finer mesh there would show the real value",
                f"nodal peak {_number(solved.peak_MPa)} MPa, Gauss-point peak {_number(solved.peak_gauss_MPa)} MPa",
                [peak],
            )

    if factor is not None and factor < 1:
        shown_peak, shown_yield = _distinct(peak_MPa, solved.yield_MPa)
        add(
            "error",
            "yields",
            f"The {solved.part} yields: peak stress {shown_peak} MPa is above "
            f"{solved.material_name}'s {shown_yield} MPa yield strength{qualifier}",
            f"safety factor {factor:.2f}",
            [peak],
        )
    elif factor is not None and factor < solved.margin:
        floored = math.floor(factor * 10 + 1e-9) / 10  # never reads as equal to the margin
        add(
            "warning",
            "low_margin",
            f"It holds, but only {floored:.1f}× the load: under the {solved.margin:g}× margin{qualifier}",
            f"safety factor {factor:.2f}, margin {solved.margin:g}",
            [peak],
        )

    if peak_finding is not None:
        add("warning", *peak_finding)

    if solved.coarser_peak_MPa is not None and solved.coarser_peak_MPa > 0:
        moved = abs(solved.peak_MPa - solved.coarser_peak_MPa) / solved.coarser_peak_MPa
        if moved > CONVERGED_WITHIN:
            before, after = _number(solved.coarser_peak_MPa), _number(solved.peak_MPa)
            if solved.peak_MPa > solved.coarser_peak_MPa:
                summary = (
                    f"The peak kept rising on a finer mesh ({before} to {after} MPa), which usually means "
                    "a sharp corner or the fixed edge: fillet it or judge the stress a little away from it"
                )
            else:
                summary = (
                    f"The peak changed {moved:.0%} on a finer mesh ({before} to {after} MPa): "
                    "use a smaller mesh size (mesh.size_mm) before trusting the safety factor"
                )
            add("warning", "mesh_not_converged", summary, f"half the mesh size moved the nodal peak {moved:.1%}", [peak])

    if solved.bbox_diagonal_mm > 0 and solved.max_displacement_mm > LARGE_DISPLACEMENT * solved.bbox_diagonal_mm:
        share = solved.max_displacement_mm / solved.bbox_diagonal_mm
        add(
            "warning",
            "large_displacement",
            f"It moves {_number(solved.max_displacement_mm)} mm, about {share:.0%} of its size: "
            "check the fit if it mates with another part",
            f"maximum displacement {solved.max_displacement_mm:.4g} mm, "
            f"bounding-box diagonal {solved.bbox_diagonal_mm:.4g} mm",
            [_item("the largest displacement", None, solved.displacement_at)],
        )

    return sorted(found, key=lambda finding: finding["severity"] != "error")
