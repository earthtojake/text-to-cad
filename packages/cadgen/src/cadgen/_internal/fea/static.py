"""Static: will it hold, and how far does it move. Linear elasticity under fixtures, face loads and body loads.

The solve calls :func:`cadgen._internal.fea.solve.solve_linear_static` through its module, so a test may patch it,
and reads its outcome into one :class:`~cadgen._internal.fea.checks.Solved` per part, which the checks, the findings
and the summary read. Stdlib only at import.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.checks import Solved

__all__ = ["FieldMax", "Static", "field_max_over", "judge", "merge_finer", "peak_face", "refined_record", "require_balance",
           "solve", "study_echo", "summary", "weakest"]


@dataclass
class Static:
    """One solve: the solver's outcome (its fields on the nodes) and what the checks read of it, one record per part."""

    outcome: Any
    solved: list["Solved"]


def xyz(point, digits: int = 3) -> list[float]:
    """A point as the summary writes it: ``[12.5, 0.0, 3.25]``."""
    return [round(float(c), digits) for c in point]


def solved_record(volume, outcome, study, ordinal_of: dict[str, int], part: str) -> "Solved":
    """The numbers of one solve the checks read, faces as their canonical refs.

    The study may name a face with a document prefix (``/work/part.step#part/face 17``)
    or by its name; both go through the ordinal to the document's canonical ref, so a
    fixture and the peak's face compare as the same string.
    """
    import numpy as np

    from cadgen._internal.fea.checks import Solved

    fixed_ordinals = {ordinal_of[ref] for ref in study.fixed_refs}
    magnitude = np.linalg.norm(outcome.displacement, axis=1)
    peak_node = int(outcome.von_mises.argmax())
    moved_node = int(magnitude.argmax())
    extent = volume.nodes.max(axis=0) - volume.nodes.min(axis=0)
    return Solved(
        material_name=study.material.name,
        yield_MPa=study.material.yield_strength,
        peak_MPa=float(outcome.von_mises[peak_node]),
        peak_gauss_MPa=outcome.von_mises_gauss_max,
        peak_at=tuple(float(c) for c in outcome.dof_locations[peak_node]),
        peak_face=peak_face(volume, outcome, peak_node, fixed_ordinals),
        fixed_faces=tuple(volume.faces[ordinal].ref for ordinal in sorted(fixed_ordinals)),
        max_displacement_mm=float(magnitude[moved_node]),
        displacement_at=tuple(float(c) for c in outcome.dof_locations[moved_node]),
        bbox_diagonal_mm=float(np.linalg.norm(extent)),
        margin=study.margin,
        coarser_peak_MPa=None,
        part=part,
        dofs=outcome.dofs,
    )


def solved_part_record(volume, outcome, study, plan, index: int, ordinal_of: dict[str, int]) -> "Solved":
    """One part of a solved assembly, as the checks read it: its own peak, yield and displacement.

    The part's elements pick its share of the fields; faces are those of the part alone.
    """
    import numpy as np

    from cadgen._internal.fea.checks import Solved

    part, material = plan.parts[index], plan.materials[index]
    rows = volume.domain == index
    dofs = np.unique(outcome.element_dofs[rows])
    field = outcome.von_mises_parts[index]  # the part's own stress, not smoothed across a joint
    own_refs = set(part.face_refs)
    own = {position for position, fp in volume.faces.items() if fp.ref in own_refs}
    fixed_ordinals = {ordinal_of[ref] for ref in study.fixed_refs} & own
    magnitude = np.linalg.norm(outcome.displacement[dofs], axis=1)
    peak_node = int(dofs[field[dofs].argmax()])
    moved_node = int(dofs[magnitude.argmax()])
    corners = volume.nodes[np.unique(volume.tets[rows][:, :4])]
    here = outcome.dof_locations[peak_node]
    joint_with, nearest = None, 0.5 * volume.max_h
    rim = np.unique(volume.boundary)
    for pair, triangles in volume.interface_triangles.items():
        if index not in pair:
            continue
        edge = np.intersect1d(np.unique(triangles), rim)
        if len(edge) == 0:
            continue
        gap = float(np.linalg.norm(volume.nodes[edge] - here, axis=1).min())
        if gap <= nearest:
            joint_with, nearest = plan.names[pair[1] if pair[0] == index else pair[0]], gap
    return Solved(
        material_name=material.name,
        yield_MPa=material.yield_strength,
        peak_MPa=float(field[peak_node]),
        peak_gauss_MPa=float(outcome.element_von_mises_gauss[rows].max()),
        peak_at=tuple(float(c) for c in here),
        peak_face=peak_face(volume, outcome, peak_node, fixed_ordinals, own),
        fixed_faces=tuple(volume.faces[ordinal].ref for ordinal in sorted(fixed_ordinals)),
        max_displacement_mm=float(magnitude.max()),
        displacement_at=tuple(float(c) for c in outcome.dof_locations[moved_node]),
        bbox_diagonal_mm=float(np.linalg.norm(corners.max(axis=0) - corners.min(axis=0))),
        margin=study.margin,
        coarser_peak_MPa=None,
        part=plan.names[index],
        dofs=outcome.dofs,
        assembly=True,
        joint_with=joint_with,
    )


def peak_face(
    volume, outcome, peak_node: int, fixed_ordinals: set[int], own: set[int] | None = None
) -> str | None:
    """The face (its canonical ref) the peak sits on, or ``None`` inside the part and away from every fixed face.

    The peak is at a fixture, and names that fixed face, when its node touches a
    fixed face (a node on an edge touches two) or lies within half an element
    of a fixed face's boundary nodes: a peak on a clamp's rim is a peak at the
    clamp, whichever face the mesher gave the rim node. Otherwise the face
    whose boundary triangles hold the node. In an assembly ``own`` limits the
    faces to the part the peak is in: a node on a joint is on both parts' faces."""
    import numpy as np

    rows = (outcome.boundary_quadratic == peak_node).any(axis=1)
    ordinals = sorted({int(o) for o in volume.boundary_ordinal[rows]} - {0})
    if own is not None:
        ordinals = [ordinal for ordinal in ordinals if ordinal in own]
        fixed_ordinals = fixed_ordinals & own
    touched = [ordinal for ordinal in ordinals if ordinal in fixed_ordinals]
    if touched:
        return volume.faces[touched[0]].ref
    here = outcome.dof_locations[peak_node]
    nearest: tuple[float, int] | None = None
    for ordinal in sorted(fixed_ordinals):
        nodes = np.unique(outcome.boundary_quadratic[volume.boundary_ordinal == ordinal])
        if len(nodes) == 0:
            continue
        gap = float(np.linalg.norm(outcome.dof_locations[nodes] - here, axis=1).min())
        if gap <= 0.5 * volume.max_h and (nearest is None or gap < nearest[0]):
            nearest = (gap, ordinal)
    if nearest is not None:
        return volume.faces[nearest[1]].ref
    return volume.faces[ordinals[0]].ref if ordinals else None


@dataclass(frozen=True)
class FieldMax:
    """Where a nodal field is largest over some faces: the node, its value and place, and the face it is on."""

    node: int
    value: float
    at: tuple[float, float, float]
    #: The face the node is on (one of the asked faces), or ``None`` when it is on none of them.
    ref: str | None
    #: The asked faces, as the document names them (canonical refs).
    faces: tuple[str, ...]


def field_max_over(
    values: "np.ndarray",
    refs: tuple[str, ...],
    *,
    boundary: "np.ndarray",
    boundary_ordinal: "np.ndarray",
    locations: "np.ndarray",
    face_ref: dict,
    ordinal_of: dict[str, int],
    where: str,
) -> FieldMax:
    """The largest of nodal ``values`` over the nodes of the surface triangles of faces ``refs``, else over every node.

    ``boundary`` is the boundary triangles in node ids, ``boundary_ordinal`` the
    face of each, ``face_ref`` the scene's ref of each face ordinal. A face
    wholly covered by a bonded joint has no surface: that is a ValueError at
    ``where``, in words the person can act on.
    """
    import numpy as np

    ordinals = sorted({ordinal_of[ref] for ref in refs})
    rows = np.isin(boundary_ordinal, ordinals) if refs else np.ones(len(boundary_ordinal), bool)
    nodes = np.unique(boundary[rows]) if refs else np.arange(len(values))
    if len(nodes) == 0:
        raise ValueError(
            f"{where}: {', '.join(refs)} {'is' if len(refs) == 1 else 'are'} wholly covered by a bonded joint, "
            "so there is no surface of it to judge; choose a face, or part of one, that is not covered by another part"
        )
    node = int(nodes[values[nodes].argmax()])
    on = rows & (boundary == node).any(axis=1)
    ordinal = int(boundary_ordinal[on][0]) if on.any() else 0
    return FieldMax(
        node=node,
        value=float(values[node]),
        at=tuple(float(c) for c in locations[node]),
        ref=face_ref[ordinal].ref if ordinal in face_ref else None,
        faces=tuple(face_ref[o].ref for o in ordinals),
    )


def solve(volume, study, plan, ordinal_of: dict[str, int], *, part_name: str, log=None, automatic: bool = False) -> Static:
    """Solve the study on ``volume``: one part (``plan`` None, named ``part_name``) or an assembly's glued parts."""
    from cadgen._internal.fea import solve as solver

    materials = study.material if plan is None else plan.materials
    outcome = solver.solve_linear_static(volume, materials, study.fixtures, study.surface_loads, ordinal_of,
                                         log=log, automatic=automatic, body_loads=study.body_accelerations)
    require_balance(outcome)
    if plan is None:
        solved = [solved_record(volume, outcome, study, ordinal_of, part_name)]
    else:
        solved = [solved_part_record(volume, outcome, study, plan, index, ordinal_of) for index in range(len(plan.parts))]
    if not any(part.peak_MPa > 0 for part in solved):
        raise ValueError(
            "no load reaches the part: the peak stress is zero everywhere, so there is nothing to judge; put the loads "
            "on faces that are not held, on the part the fixtures hold"
        )
    return Static(outcome, solved)


def require_balance(outcome) -> None:
    """Refuse a solve whose reactions do not balance the applied load: its stresses are not the study's."""
    reaction = tuple(sum(r[c] for r in outcome.reactions) for c in range(3))
    mismatch = max(abs(a + r) for a, r in zip(outcome.applied, reaction))
    if mismatch > 1e-3 * max(1.0, max(abs(a) for a in outcome.applied)):
        raise RuntimeError(f"the reactions do not balance the applied load (mismatch {mismatch:.3g} N), so the solve is "
                           "wrong and nothing was written")


def weakest(result: Static) -> "Solved":
    """The part with the lowest safety factor: the one the headline and the stress check are about."""
    from cadgen._internal.fea import checks

    return min(result.solved, key=lambda part: math.inf if checks.safety_factor(part) is None else checks.safety_factor(part))


# -- the automatic finer solve -------------------------------------------------------------------------------

def refined_record(result: Static, size_mm: float, finer_mm: float, *, assembly: bool) -> dict:
    """The result's ``refined``, before the finer solve: the first solve's size and governing peak."""
    part = weakest(result)
    return {
        "from_size_mm": round(size_mm, 4),
        "from_max_von_mises_MPa": round(part.peak_MPa, 4),
        "size_mm": round(finer_mm, 4),
        "max_von_mises_MPa": None,
        **({"part": part.part} if assembly else {}),
    }


def merge_finer(coarse: Static, finer: Static, refined: dict) -> Static:
    """The finer solve is the one written; the first solve's peak rides along for convergence only."""
    index = next(i for i, part in enumerate(coarse.solved) if part is weakest(coarse))
    # Like with like: the finer peak of the part whose first-solve peak is recorded.
    refined["max_von_mises_MPa"] = round(finer.solved[index].peak_MPa, 4)
    finer.solved = [
        dataclasses.replace(fine, coarser_peak_MPa=first.peak_MPa, coarser_dofs=coarse.outcome.dofs)
        for fine, first in zip(finer.solved, coarse.solved)
    ]
    return finer


# -- judging and what is written -----------------------------------------------------------------------------

def judge(check: dict, index: int, volume, ordinal_of: dict[str, int], result: Static) -> dict:
    """The stress check is the weakest part's. A displacement check takes the largest displacement
    magnitude over the nodes of its faces' surface triangles (faces of several parts alike), else
    over the whole model, and names the face it is on."""
    import numpy as np

    from cadgen._internal.fea import checks

    if check["kind"] == "stress":
        return checks.stress_check(weakest(result), label=check.get("label"))
    outcome = result.outcome
    peak = field_max_over(
        np.linalg.norm(outcome.displacement, axis=1), tuple(check.get("faces", ())), boundary=outcome.boundary_quadratic,
        boundary_ordinal=volume.boundary_ordinal, locations=outcome.dof_locations, face_ref=volume.faces,
        ordinal_of=ordinal_of, where=f"checks[{index}]",
    )
    return checks.displacement_check(
        peak.value, check["limit_mm"], at=peak.at, ref=peak.ref, faces=peak.faces, label=check.get("label"),
    )


def summary(result: Static, check_results: list[dict], *, scale: float | None, part_refs: list[str] | None) -> dict:
    """The one place the numbers are rounded; the GLB's extras and the result are derived from it."""
    import numpy as np

    from cadgen._internal.fea import checks

    outcome = result.outcome
    max_vm_index = int(outcome.von_mises.argmax())
    magnitude = np.linalg.norm(outcome.displacement, axis=1)
    reaction_total = tuple(sum(r[c] for r in outcome.reactions) for c in range(3))
    solved = weakest(result)
    out = {
        "max_von_mises_MPa": round(float(outcome.von_mises[max_vm_index]), 4),
        "max_von_mises_gauss_MPa": round(outcome.von_mises_gauss_max, 4),
        "max_von_mises_at_mm": xyz(outcome.dof_locations[max_vm_index]),
        "yield_MPa": solved.yield_MPa,
        "max_displacement_mm": round(float(magnitude.max()), 6),
        "max_displacement_at_mm": xyz(outcome.dof_locations[int(magnitude.argmax())]),
        "applied_force_N": [round(x, 4) for x in outcome.applied],
        "reaction_force_N": [round(x, 4) for x in reaction_total],
        "deformation_scale": scale,
        "safety_factor": checks.floored_factor(solved),
    }
    if part_refs is not None:
        # The headline is the weakest part: its yield and safety factor; the peak and the colours span the assembly.
        out["weakest_part"] = solved.part
        out["weakest_part_peak_MPa"] = round(solved.peak_MPa, 4)
        out["weakest_part_peak_at_mm"] = [round(c, 3) for c in solved.peak_at]
        out["parts"] = [
            {"ref": part_refs[i], "name": part.part, "material": part.material_name, "yield_MPa": part.yield_MPa,
             "peak_MPa": round(part.peak_MPa, 4), "peak_gauss_MPa": round(part.peak_gauss_MPa, 4),
             "peak_at_mm": [round(c, 3) for c in part.peak_at], "safety_factor": checks.floored_factor(part),
             "max_displacement_mm": round(part.max_displacement_mm, 6)}
            for i, part in enumerate(result.solved)
        ]
    # Each check the study asked for (the stress check alone by default), judged at the load as solved.
    out["checks"] = check_results
    return out


def study_echo(study, bare) -> dict:
    """The study's fixtures and loads as the viewer reads them, faces as the document names them (``bare``)."""
    def load_echo(load) -> dict:
        if load.body:
            return {"type": load.type, "vector_g": [float(c) for c in load.vector_g]}
        return {"type": load.type, "faces": bare(load.faces),
                **({"vector_N": [float(c) for c in load.vector]} if load.type == "force" else {"pressure_MPa": load.pressure})}

    return {
        "fixtures": [{"type": fixture.type, "faces": bare(fixture.faces)} for fixture in study.fixtures],
        "loads": [load_echo(load) for load in study.loads],
    }
