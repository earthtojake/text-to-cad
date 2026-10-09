"""What an engineer checks on a stress result, as findings in plain words.

The KiCad findings' shape (``check``, ``severity``, ``type``, ``summary``,
``description``, ``items``), so the viewer's alert card and the agent read FEA
the way they read a board. Errors are what make the part unfit to use; the
rest are suggestions. Stdlib only: nothing here needs the solver.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["CONVERGED_WITHIN", "GAUSS_RATIO", "LARGE_BEND", "RESOLVE_BELOW", "Solved", "findings", "needs_finer", "safety_factor"]

#: Re-solve finer only when the safety factor is this close to failing.
RESOLVE_BELOW = 3.0
#: A finer mesh moving the peak more than this share: not converged.
CONVERGED_WITHIN = 0.10
#: Displacement over this share of the part's size is a large bend.
LARGE_BEND = 0.01
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
    #: The nodal peak on a finer mesh, when one was solved.
    finer_peak_MPa: float | None
    part: str


def safety_factor(solved: Solved) -> float | None:
    """Yield over peak stress, or ``None`` when no load reaches the part."""
    return solved.yield_MPa / solved.peak_MPa if solved.peak_MPa > 0 else None


def needs_finer(safety_factor: float | None) -> bool:
    """Whether the safety factor is close enough to failing to justify a finer solve."""
    return safety_factor is not None and safety_factor < RESOLVE_BELOW


def _number(value: float) -> str:
    return f"{value:.3g}" if value < 100 else f"{value:.0f}"


def _item(text: str, ref: str | None, at: tuple[float, float, float]) -> dict:
    return {"text": text, "ref": ref, "at": [round(c, 3) for c in at]}


def findings(solved: Solved) -> list[dict]:
    """The findings for one solved study, errors first."""
    found: list[dict] = []
    peak = _item("the peak stress", solved.peak_face, solved.peak_at)
    factor = safety_factor(solved)

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

    if factor is not None and factor < 1:
        add(
            "error",
            "yields",
            f"The {solved.part} yields: peak stress {_number(solved.peak_MPa)} MPa is above "
            f"{solved.material_name}'s {_number(solved.yield_MPa)} MPa yield strength",
            f"safety factor {factor:.2f}",
            [peak],
        )
    elif factor is not None and factor < solved.margin:
        add(
            "warning",
            "low_margin",
            f"It holds, but only {factor:.1f}× the load: under the {solved.margin:g}× margin",
            f"safety factor {factor:.2f}, margin {solved.margin:g}",
            [peak],
        )

    on_fixture = solved.peak_face in solved.fixed_faces
    if solved.peak_MPa > 0 and (on_fixture or solved.peak_gauss_MPa > GAUSS_RATIO * solved.peak_MPa):
        if on_fixture:
            summary = (
                "The peak at the fixed face is likely exaggerated by the model; "
                "a fillet or a softer support would show the real value"
            )
        else:
            summary = "The peak at a sharp corner is likely exaggerated by the model; a fillet there would show the real value"
        add(
            "warning",
            "peak_at_fixture",
            summary,
            f"nodal peak {_number(solved.peak_MPa)} MPa, Gauss-point peak {_number(solved.peak_gauss_MPa)} MPa",
            [peak],
        )

    if solved.finer_peak_MPa is not None and solved.peak_MPa > 0:
        moved = abs(solved.finer_peak_MPa - solved.peak_MPa) / solved.peak_MPa
        if moved > CONVERGED_WITHIN:
            add(
                "warning",
                "mesh_not_converged",
                f"The peak moved {moved:.0%} on a finer mesh ({_number(solved.peak_MPa)} to "
                f"{_number(solved.finer_peak_MPa)} MPa): refine before trusting the safety factor",
                f"half the mesh size moved the nodal peak {moved:.1%}",
                [peak],
            )

    if solved.bbox_diagonal_mm > 0 and solved.max_displacement_mm > LARGE_BEND * solved.bbox_diagonal_mm:
        share = solved.max_displacement_mm / solved.bbox_diagonal_mm
        add(
            "warning",
            "large_bend",
            f"It bends {_number(solved.max_displacement_mm)} mm, about {share:.0%} of its size: "
            "check the fit if it mates with another part",
            f"maximum displacement {solved.max_displacement_mm:.4g} mm, "
            f"bounding-box diagonal {solved.bbox_diagonal_mm:.4g} mm",
            [_item("the largest displacement", None, solved.displacement_at)],
        )

    return sorted(found, key=lambda finding: finding["severity"] != "error")
