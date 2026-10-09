"""What an engineer checks on a stress result, as findings in plain words.

The KiCad findings' shape (``check``, ``severity``, ``type``, ``summary``,
``description``, ``items``), so the viewer's alert card and the agent read FEA
the way they read a board. Errors are what make the part unfit to use; the
rest are suggestions. An assembly's findings come from one :class:`Solved` per
part (:func:`assembly_findings`) and name the part. Stdlib only: nothing here
needs the solver.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

__all__ = ["CONVERGED_WITHIN", "GAUSS_RATIO", "MATERIALLY_FINER", "LARGE_DISPLACEMENT", "RESOLVE_BELOW", "Solved", "assembly_findings", "default_material", "findings", "gap_closed", "needs_finer", "safety_factor", "safety_factor_text"]

#: Re-solve finer only when the safety factor is this close to failing.
RESOLVE_BELOW = 3.0
#: A finer mesh moving the peak more than this share: not converged.
CONVERGED_WITHIN = 0.10
#: A re-solve counts as finer only with this many times the first solve's degrees
#: of freedom: the mesher's size is an upper bound, so "half the size" can be +3%.
MATERIALLY_FINER = 1.3
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
    #: The ``#o1.fN`` face the peak sits on, when it sits on one; the fixed face
    #: when the peak touches one or lies within half an element of its edge.
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
    #: Degrees of freedom of the written solve and of the first, coarser one;
    #: only whether the re-solve was materially finer reads them.
    dofs: int = 0
    coarser_dofs: int | None = None
    #: One part of an assembly: its findings say which part they are about.
    assembly: bool = False
    #: The part across the bonded joint whose edge the peak sits on, when it does.
    joint_with: str | None = None


def safety_factor(solved: Solved) -> float | None:
    """Yield over the written solve's peak stress, or ``None`` when no load reaches the part."""
    return solved.yield_MPa / solved.peak_MPa if solved.peak_MPa > 0 else None


def needs_finer(safety_factor: float | None) -> bool:
    """Whether the safety factor is close enough to failing to justify a finer solve."""
    return safety_factor is not None and safety_factor < RESOLVE_BELOW


def safety_factor_text(factor: float) -> str:
    """A safety factor as a person reads it: floored to one decimal under 10, to a whole number from 10.

    Floored, never rounded, so a factor just under a threshold never reads as reaching it.
    """
    if factor >= 10:
        return str(math.floor(factor + 1e-9))
    return f"{math.floor(factor * 10 + 1e-9) / 10:.1f}"


def _number(value: float, extra: int = 0) -> str:
    """Three significant figures, whole numbers from 100 up; ``extra`` adds decimals."""
    return f"{value:.{3 + extra}g}" if value < 100 else f"{value:.{extra}f}"


def _distinct(low: float, high: float) -> tuple[str, str]:
    """Both numbers printed with enough decimals that they never read as equal."""
    for extra in range(3):
        if _number(low, extra) != _number(high, extra):
            break
    return _number(low, extra), _number(high, extra)


def quoted(name: str) -> str:
    """A part's name for a sentence: ``'bar'``, or ``'bar' (#o1.3)`` when the name is shared and carries its ref."""
    shared = re.fullmatch(r"(.*) \((#o[\d.]+)\)", name)
    return f"'{shared.group(1)}' ({shared.group(2)})" if shared else f"'{name}'"


def _item(text: str, ref: str | None, at: tuple[float, float, float]) -> dict:
    return {"text": text, "ref": ref, "at": [round(c, 3) for c in at]}


def _finding(severity: str, kind: str, summary: str, description: str, items: list[dict]) -> dict:
    return {
        "check": "fea",
        "severity": severity,
        "type": kind,
        "summary": summary,
        "description": description,
        "items": items,
    }


def default_material(part: str, material_name: str) -> dict:
    """A part the study gave no material of its own: it got the default, which may not be what it is made of."""
    return _finding(
        "warning",
        "default_material",
        f"{quoted(part)} uses the default material ({material_name}): is that right?",
        f"the study's parts name no material for {quoted(part)}",
        [],
    )


def gap_closed(first: str, second: str, gap_mm: float, *, interference: bool = False) -> dict:
    """Two parts a little apart, or a little into each other (``interference``), that were bonded
    anyway by moving geometry up to that far."""
    if interference:
        # Two figures: the depth is estimated from the shared solid's volume and area, not measured.
        return _finding(
            "warning",
            "gap_closed",
            f"Closed a {gap_mm:.2g} mm interference between {quoted(first)} and {quoted(second)} to bond them",
            f"the parts overlapped by {gap_mm:.4g} mm, within the contact tolerance",
            [],
        )
    return _finding(
        "warning",
        "gap_closed",
        f"Closed a {_number(gap_mm)} mm gap between {quoted(first)} and {quoted(second)} to bond them",
        f"the parts were {gap_mm:.4g} mm apart, within the contact tolerance",
        [],
    )


def overlapping_parts(first: str, second: str, volume_mm3: float) -> dict:
    """Two parts whose solids overlap: not bonded, and real parts can't overlap."""
    return _finding(
        "warning",
        "overlapping_parts",
        f"{quoted(first)} and {quoted(second)} overlap by {_number(volume_mm3)} mm³: real parts can't, "
        "so the model may be wrong; fix the geometry or mark them free",
        "overlapping parts are not bonded to each other, so no load passes between them",
        [],
    )


def findings(solved: Solved) -> list[dict]:
    """The findings for one solved study, errors first."""
    found: list[dict] = []
    peak = _item(f"the peak stress in {quoted(solved.part)}" if solved.assembly else "the peak stress", solved.peak_face, solved.peak_at)
    factor = safety_factor(solved)
    peak_MPa = solved.peak_MPa
    # An assembly's sentences name the part; "The post yields" already does.
    it = quoted(solved.part) if solved.assembly else "It"

    def about(summary: str) -> str:
        return f"In {quoted(solved.part)}: {summary[0].lower()}{summary[1:]}" if solved.assembly else summary

    def add(severity: str, kind: str, summary: str, description: str, items: list[dict]) -> None:
        found.append(_finding(severity, kind, summary, description, items))

    if factor is None and not solved.assembly:
        add(
            "warning",
            "no_load",
            "No load reaches the part: check the loads are on faces connected to the fixed ones",
            "the peak stress is zero",
            [],
        )

    # A materially finer solve that agreed with the first resolved the peak: it is not a singularity.
    moved = None
    if solved.coarser_peak_MPa is not None and solved.coarser_peak_MPa > 0:
        moved = abs(solved.peak_MPa - solved.coarser_peak_MPa) / solved.coarser_peak_MPa
    finer = solved.coarser_dofs is not None and solved.dofs >= MATERIALLY_FINER * solved.coarser_dofs
    resolved = moved is not None and moved <= CONVERGED_WITHIN and finer
    rising = moved is not None and moved > CONVERGED_WITHIN and solved.peak_MPa > solved.coarser_peak_MPa

    # Peak findings matter only while the part is short of its margin.
    on_fixture = solved.peak_face in solved.fixed_faces
    spike = solved.peak_gauss_MPa > GAUSS_RATIO * solved.peak_MPa
    qualifier = ""
    peak_finding = None
    if factor is not None and factor < solved.margin and not resolved and (on_fixture or spike):
        if on_fixture:
            qualifier = " (the peak sits at the fixed face)"
            peak_finding = (
                "peak_at_fixture",
                about(
                    "Check the stress a little away from the fixed face before redesigning: "
                    "the model exaggerates peaks where a part is held"
                ),
                f"nodal peak {_number(solved.peak_MPa)} MPa, Gauss-point peak {_number(solved.peak_gauss_MPa)} MPa",
                [peak],
            )
        else:
            qualifier = " (the peak is a local spike)"
            peak_finding = (
                "peak_concentration",
                about(
                    "The peak is a sharp local spike the mesh can't resolve (a sharp corner or a concentrated load): "
                    "a fillet or a finer mesh there would show the real value"
                ),
                f"nodal peak {_number(solved.peak_MPa)} MPa, Gauss-point peak {_number(solved.peak_gauss_MPa)} MPa",
                [peak],
            )
    if rising and (on_fixture or spike):
        # One clause is enough. A rising peak at a smooth spot is a real concentration: no "lower" claim.
        qualifier = ", but this peak kept rising on a finer mesh, so the real stress is likely lower"

    if factor is not None and factor < 1:
        shown_peak, shown_yield = _distinct(peak_MPa, solved.yield_MPa)
        add(
            "error",
            "yields",
            f"The {solved.part} yields: peak stress {shown_peak} MPa is above "
            f"the {shown_yield} MPa yield strength of {solved.material_name}{qualifier}",
            f"safety factor {safety_factor_text(factor)}",
            [peak],
        )
    elif factor is not None and factor < solved.margin:
        add(
            "warning",
            "low_margin",
            f"{it} holds, but only {safety_factor_text(factor)}× the load: under the {solved.margin:g}× margin{qualifier}",
            f"safety factor {safety_factor_text(factor)}, margin {solved.margin:g}",
            [peak],
        )

    if peak_finding is not None:
        add("warning", *peak_finding)

    # A bonded joint is perfectly rigid where it meets the free surface, which a real joint is not.
    if (
        solved.joint_with is not None
        and factor is not None
        and factor < solved.margin
        and not resolved
        and peak_finding is None
    ):
        add(
            "warning",
            "bonded_edge_peak",
            f"In {quoted(solved.part)}: the peak sits on the edge of the bonded joint with {quoted(solved.joint_with)}, "
            "where a bonded model exaggerates stress: check the stress a little away from the joint before redesigning",
            f"nodal peak {_number(solved.peak_MPa)} MPa, Gauss-point peak {_number(solved.peak_gauss_MPa)} MPa",
            [peak],
        )

    # In an assembly only the weakest part decided the re-solve; another part far from
    # failing that moved is no reason to distrust the answer.
    unsettled = moved is not None and moved > CONVERGED_WITHIN
    if unsettled and solved.assembly and not needs_finer(factor):
        unsettled = False
    if unsettled:
        before, after = _number(solved.coarser_peak_MPa), _number(solved.peak_MPa)
        if rising:
            summary = about(
                f"The peak kept rising on a finer mesh ({before} to {after} MPa), which usually means "
                "a sharp corner or the fixed edge: fillet it or judge the stress a little away from it"
            )
        else:
            summary = about(
                f"The peak changed {moved:.0%} on a finer mesh ({before} to {after} MPa): "
                "use a smaller mesh size (mesh.size_mm) before trusting the safety factor"
            )
        add("warning", "mesh_not_converged", summary, f"half the mesh size moved the nodal peak {moved:.1%}", [peak])

    if solved.bbox_diagonal_mm > 0 and solved.max_displacement_mm > LARGE_DISPLACEMENT * solved.bbox_diagonal_mm:
        share = solved.max_displacement_mm / solved.bbox_diagonal_mm
        add(
            "warning",
            "large_displacement",
            f"{it} moves {_number(solved.max_displacement_mm)} mm, about {share:.0%} of its size: "
            "check the fit if it mates with another part",
            f"maximum displacement {solved.max_displacement_mm:.4g} mm, "
            f"bounding-box diagonal {solved.bbox_diagonal_mm:.4g} mm",
            [_item("the largest displacement", None, solved.displacement_at)],
        )

    return sorted(found, key=lambda finding: finding["severity"] != "error")


def assembly_findings(parts: list[Solved]) -> list[dict]:
    """The findings of every part of one solved assembly, errors first.

    A part no load reaches is nothing to report on its own; only when none of
    them is loaded does the study say so.
    """
    found = [finding for solved in parts for finding in findings(solved)]
    if all(safety_factor(solved) is None for solved in parts):
        found.append(
            _finding(
                "warning",
                "no_load",
                "No load reaches the parts: check the loads are on faces connected to the fixed ones",
                "the peak stress is zero in every part",
                [],
            )
        )
    return sorted(found, key=lambda finding: finding["severity"] != "error")
