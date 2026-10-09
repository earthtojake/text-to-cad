"""What the ``cadgen.fea`` verbs do, end to end."""

from __future__ import annotations

import dataclasses
import json
import math
import os
from pathlib import Path
from typing import TYPE_CHECKING

from cadgen.cli_logging import CliLogger
from cadgen.results import FeaFace, FeaFacesResult, FeaPair, FeaPart, FeaPartsResult, FeaResult

if TYPE_CHECKING:
    from cadgen._internal.fea.checks import Solved
    from cadgen.step_scene import Occurrence, Selection, StepScene

__all__ = ["list_assembly_parts", "list_faces", "solve_study"]

_AXES = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}


def _open(target: Path) -> "StepScene":
    from cadgen._internal.doors import STEP_SUFFIXES, document_target
    from cadgen.step_scene import read_scene

    return read_scene(document_target(target, suffixes=STEP_SUFFIXES))


def _resolve_faces(scene: "StepScene", refs: "tuple[str, ...]") -> tuple[dict[str, "Selection"], set[str]]:
    """Each face ref resolved, and the occurrences they belong to."""
    resolved: dict[str, Selection] = {}
    owners: set[str] = set()
    for ref in refs:
        selection = scene.resolve(ref)
        if selection.kind != "face":
            raise ValueError(f"{ref} is a {selection.kind} reference; fixtures and loads take faces (#o1.f17)")
        resolved[ref] = selection
        owners.add(selection.occurrence_ref)
    return resolved, owners


def _single_occurrence(
    scene: "StepScene", resolved: dict[str, "Selection"], owners: set[str]
) -> tuple["Occurrence", dict[str, "Selection"]]:
    """The one leaf occurrence every face ref belongs to, and each ref resolved."""
    if len(owners) > 1:
        raise ValueError(
            f"the study's faces span {len(owners)} occurrences ({', '.join(sorted(owners))}); "
            "a study solves one part, so every face must be on the same occurrence"
        )
    return scene.resolve(next(iter(owners))), resolved  # type: ignore[return-value]


def _axis_word(normal: tuple[float, float, float]) -> str:
    for name, axis in _AXES.items():
        dot = sum(a * b for a, b in zip(normal, axis))
        if dot > math.cos(math.radians(5)):
            return f"+{name}"
        if dot < -math.cos(math.radians(5)):
            return f"-{name}"
    return f"({normal[0]:.2f}, {normal[1]:.2f}, {normal[2]:.2f})"


def _rank_word(rank: int) -> str:
    if rank == 1:
        return "largest"
    suffix = "th" if 10 <= rank % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(rank % 10, "th")
    return f"{rank}{suffix} largest"


def list_faces(target: Path, *, occurrence: str | None = None, verbose: bool = False) -> FeaFacesResult:
    from cadgen._internal.fea.mesh import face_area_center

    logger = CliLogger("fea", verbose=verbose)
    scene = _open(Path(target))
    if occurrence:
        owner = scene.resolve(occurrence)
        if owner.kind != "occurrence":
            raise ValueError(f"{occurrence} is not an occurrence reference")
    else:
        leaves = list(scene.leaves())
        if len(leaves) != 1:
            raise ValueError(
                f"the document has {len(leaves)} part occurrences; pass --occurrence "
                f"{' or '.join(leaf.ref for leaf in leaves[:4])}{' ...' if len(leaves) > 4 else ''}"
            )
        owner = leaves[0]
    logger.debug(f"listing faces of {owner.ref}")

    faces = []
    for selection in owner.entities("face"):
        face = selection.shape()
        area, centre = face_area_center(face)
        surface = str(getattr(face.geom_type, "name", face.geom_type)).lower()
        normal = None
        if surface == "plane":
            n = face.normal_at()
            normal = (round(float(n.X), 6), round(float(n.Y), 6), round(float(n.Z), 6))
        faces.append(FeaFace(
            ref=selection.ref, area_mm2=round(area, 4), center_mm=tuple(round(c, 4) for c in centre),
            surface=surface, normal=normal, hint="",
        ))
    rank = {face.ref: position + 1 for position, face in enumerate(sorted(faces, key=lambda f: -f.area_mm2))}
    faces = [
        dataclasses.replace(face, hint=", ".join(
            [face.surface] + ([f"normal {_axis_word(face.normal)}"] if face.normal else []) + [_rank_word(rank[face.ref])]
        ))
        for face in faces
    ]
    return FeaFacesResult(ok=True, document=Path(target), occurrence=owner.ref, faces=tuple(faces))


# `fea parts` also lists pairs this far apart that the tolerance leaves unbonded,
# so a near miss is something the agent reads rather than something that is missing.
_NEAR_MISS_MM = 1.0


def list_assembly_parts(target: Path, *, contact_tolerance_mm: float = 0.1, verbose: bool = False) -> FeaPartsResult:
    from cadgen._internal.fea.assembly import detect_contacts, list_parts
    from cadgen._internal.fea.mesh import require_fea_stack

    require_fea_stack()
    if not contact_tolerance_mm >= 0:
        raise ValueError("contact_tolerance_mm must be zero or more")
    logger = CliLogger("fea", verbose=verbose)
    scene = _open(Path(target))
    parts = list_parts(scene)
    logger.debug(f"{len(parts)} parts; looking for pairs within {max(contact_tolerance_mm, _NEAR_MISS_MM)} mm")
    name = {part.ref: part.name for part in parts}
    pairs = [
        FeaPair(
            between=(name[c.a], name[c.b]),
            refs=(c.a, c.b),
            area_mm2=round(c.area_mm2, 4),
            gap_mm=round(c.gap_mm, 6),
            type="bonded" if c.gap_mm <= contact_tolerance_mm * (1 + 1e-6) else "not_connected",
        )
        for c in detect_contacts(parts, max(contact_tolerance_mm, _NEAR_MISS_MM))
    ]
    return FeaPartsResult(
        ok=True,
        document=Path(target),
        contact_tolerance_mm=contact_tolerance_mm,
        parts=tuple(FeaPart(ref=p.ref, name=p.name, volume_mm3=round(p.volume_mm3, 4)) for p in parts),
        pairs=tuple(pairs),
    )


@dataclasses.dataclass
class _Plan:
    """What an assembly study asks for, once its parts and connections are resolved."""

    parts: list
    #: Per part, the occurrence's name (its ref when it has none).
    names: list[str]
    materials: list
    #: Indices of the parts the study gave no material of their own.
    defaulted: list[int]
    #: Every pair in contact within the tolerance, and the ones that get bonded.
    contacts: list
    bonded: list
    #: Per part, the group of parts bonded to it (directly or through others).
    group_of: list[int]


def _find_part(parts: list, names: list[str], key: str, where: str) -> int:
    """The part a study names by occurrence ref or by name."""
    for index, part in enumerate(parts):
        if key in (part.ref, f"#{key}"):
            return index
    named = [index for index, name in enumerate(names) if name == key]
    if len(named) > 1:
        raise ValueError(f"{where}: {key!r} names {len(named)} parts ({', '.join(parts[i].ref for i in named)}); use a ref")
    if not named:
        raise ValueError(f"{where}: no part named {key!r}; the parts are {', '.join(repr(name) for name in names)}")
    return named[0]


def _plan_assembly(scene: "StepScene", parsed) -> _Plan:
    from cadgen._internal.fea.assembly import _groups, detect_contacts, list_parts

    parts = list_parts(scene)
    names = [part.name for part in parts]
    index_of = {part.ref: i for i, part in enumerate(parts)}

    materials = [parsed.material] * len(parts)
    given: set[int] = set()
    for key, material in parsed.parts.items():
        index = _find_part(parts, names, key, f"parts[{key!r}]")
        if index in given:
            raise ValueError(f"parts[{key!r}]: '{names[index]}' is named twice in 'parts'")
        given.add(index)
        materials[index] = material

    contacts = detect_contacts(parts, parsed.contact_tolerance_mm)
    pair_of = {frozenset((index_of[c.a], index_of[c.b])) for c in contacts}
    freed: set[frozenset[int]] = set()
    seen: set[frozenset[int]] = set()
    for n, connection in enumerate(parsed.connections):
        where = f"connections[{n}]"
        i, j = (_find_part(parts, names, key, f"{where}.between") for key in connection.between)
        pair = frozenset((i, j))
        if i == j:
            raise ValueError(f"{where}.between: both names are '{names[i]}'")
        if pair in seen:
            raise ValueError(f"{where}: '{names[i]}' and '{names[j]}' are connected twice")
        seen.add(pair)
        if connection.type == "bonded" and pair not in pair_of:
            raise ValueError(
                f"{where}: '{names[i]}' and '{names[j]}' don't touch within {parsed.contact_tolerance_mm:g} mm, "
                "so they can't be bonded; raise contact_tolerance_mm or move them together"
            )
        if connection.type == "free" and pair in pair_of:
            freed.add(pair)

    bonded = [c for c in contacts if frozenset((index_of[c.a], index_of[c.b])) not in freed]
    group_of = [0] * len(parts)
    for number, group in enumerate(_groups(len(parts), [(index_of[c.a], index_of[c.b]) for c in bonded])):
        for index in group:
            group_of[index] = number
    for pair in freed:
        i, j = sorted(pair)
        if group_of[i] == group_of[j]:
            raise ValueError(
                f"connections: '{names[i]}' and '{names[j]}' are also joined through other bonded parts, so one joint "
                "between them can't be freed on its own (not yet supported); free the parts' other connections too"
            )
    return _Plan(parts, names, materials, sorted(set(range(len(parts))) - given), contacts, bonded, group_of)


def _not_connected(plan: _Plan, unheld: list[list[int]]) -> list[dict]:
    """One error per group of parts nothing holds: which parts, and the nearest part that is not among them."""
    from cadgen._internal.fea.assembly import part_centre, part_gap

    found = []
    for group in unheld:
        members = ", ".join(f"'{plan.names[i]}'" for i in group)
        nearest = None
        for other in range(len(plan.parts)):
            if other in group:
                continue
            for i in group:
                gap = part_gap(plan.parts[i], plan.parts[other])
                if gap is not None and (nearest is None or gap < nearest[0]):
                    nearest = (gap, other)
        if nearest is None:
            where = ""
        elif nearest[0] <= 1e-6:
            where = f": it touches '{plan.names[nearest[1]]}' but isn't bonded to it"
        else:
            where = f": nearest part '{plan.names[nearest[1]]}' is {nearest[0]:.3g} mm away"
        found.append({
            "check": "fea",
            "severity": "error",
            "type": "not_connected",
            "summary": f"{members} {'isn' if len(group) == 1 else 'aren'}'t connected to anything that is held{where}",
            "description": "no chain of bonded parts joins it to a fixed face, so the solve was not run",
            "items": [
                {"text": f"'{plan.names[i]}'", "ref": plan.parts[i].ref,
                 "at": [round(c, 3) for c in part_centre(plan.parts[i])]}
                for i in group
            ],
        })
    return found


def _unheld_groups(plan: _Plan, held_parts: set[int]) -> list[list[int]]:
    """The bonded groups none of whose parts is in ``held_parts``, each as its part indices."""
    groups: dict[int, list[int]] = {}
    for index, number in enumerate(plan.group_of):
        groups.setdefault(number, []).append(index)
    return [group for group in groups.values() if not held_parts & set(group)]


def _unheld_after_meshing(volume, held_ordinals: set[int], count: int) -> list[list[int]]:
    """The parts the mesh leaves apart from every fixed face (the glue did not join them), each as its own group."""
    import numpy as np
    import scipy.sparse as sparse
    from scipy.sparse.csgraph import connected_components

    corners = volume.tets[:, :4]
    rows = np.concatenate([corners[:, a] for a in (0, 0, 0, 1, 1, 2)])
    cols = np.concatenate([corners[:, b] for b in (1, 2, 3, 2, 3, 3)])
    nodes = len(volume.nodes)
    graph = sparse.coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(nodes, nodes))
    _, label = connected_components(graph, directed=False)
    fixed = volume.boundary[np.isin(volume.boundary_ordinal, list(held_ordinals))][:, :3]
    held = set(np.unique(label[fixed]).tolist())
    return [
        [index] for index in range(count)
        if not held & set(np.unique(label[corners[volume.domain == index]]).tolist())
    ]


def _peak_face(
    volume, outcome, peak_node: int, fixed_ordinals: set[int], own: set[int] | None = None
) -> str | None:
    """The ``#o1.fN`` face the peak sits on, or ``None`` inside the part and away from every fixed face.

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


def _solved(volume, outcome, parsed, ordinal_of: dict[str, int], part: str) -> "Solved":
    """The numbers of one solve the checks read, faces as bare ``#o1.fN`` refs.

    The study may name a face with a document prefix (``part.step#o1.f17``) or a
    label; both go through the ordinal to the scene's own ref, so a fixture and
    the peak's face compare as the same string.
    """
    import numpy as np

    from cadgen._internal.fea.checks import Solved

    fixed_ordinals = {ordinal_of[ref] for fixture in parsed.fixtures for ref in fixture.faces}
    magnitude = np.linalg.norm(outcome.displacement, axis=1)
    peak_node = int(outcome.von_mises.argmax())
    moved_node = int(magnitude.argmax())
    extent = volume.nodes.max(axis=0) - volume.nodes.min(axis=0)
    return Solved(
        material_name=parsed.material.name,
        yield_MPa=parsed.material.yield_strength,
        peak_MPa=float(outcome.von_mises[peak_node]),
        peak_gauss_MPa=outcome.von_mises_gauss_max,
        peak_at=tuple(float(c) for c in outcome.dof_locations[peak_node]),
        peak_face=_peak_face(volume, outcome, peak_node, fixed_ordinals),
        fixed_faces=tuple(volume.faces[ordinal].ref for ordinal in sorted(fixed_ordinals)),
        max_displacement_mm=float(magnitude[moved_node]),
        displacement_at=tuple(float(c) for c in outcome.dof_locations[moved_node]),
        bbox_diagonal_mm=float(np.linalg.norm(extent)),
        margin=parsed.margin,
        coarser_peak_MPa=None,
        part=part,
        dofs=outcome.dofs,
    )


def _solved_part(volume, outcome, parsed, plan: _Plan, index: int, ordinal_of: dict[str, int]) -> "Solved":
    """One part of a solved assembly, as the checks read it: its own peak, yield and displacement.

    The part's elements pick its share of the fields; faces are those of the part alone.
    """
    import numpy as np

    from cadgen._internal.fea.checks import Solved

    part, material = plan.parts[index], plan.materials[index]
    rows = volume.domain == index
    dofs = np.unique(outcome.element_dofs[rows])
    field = outcome.von_mises_parts[index]  # the part's own stress, not smoothed across a joint
    own = {position for position, fp in volume.faces.items() if fp.ref.startswith(f"{part.ref}.f")}
    fixed_ordinals = {ordinal_of[ref] for fixture in parsed.fixtures for ref in fixture.faces} & own
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
        peak_face=_peak_face(volume, outcome, peak_node, fixed_ordinals, own),
        fixed_faces=tuple(volume.faces[ordinal].ref for ordinal in sorted(fixed_ordinals)),
        max_displacement_mm=float(magnitude.max()),
        displacement_at=tuple(float(c) for c in outcome.dof_locations[moved_node]),
        bbox_diagonal_mm=float(np.linalg.norm(corners.max(axis=0) - corners.min(axis=0))),
        margin=parsed.margin,
        coarser_peak_MPa=None,
        part=plan.names[index],
        dofs=outcome.dofs,
        assembly=True,
        joint_with=joint_with,
    )


def _connections(plan: _Plan, volume) -> list[dict]:
    """The detected pairs and what the study did with each, for the sidecar.

    ``faces`` are the interface faces on both sides of a bonded joint, as the
    GLB's ``faces`` name them; a free pair has none.
    """
    name_of = {part.ref: plan.names[i] for i, part in enumerate(plan.parts)}
    index_of = {part.ref: i for i, part in enumerate(plan.parts)}
    bonded = {(c.a, c.b) for c in plan.bonded}
    return [
        {
            "between": [name_of[c.a], name_of[c.b]],
            "refs": [c.a, c.b],
            "type": "bonded" if (c.a, c.b) in bonded else "free",
            "area_mm2": round(c.area_mm2, 4),
            "gap_mm": round(c.gap_mm, 6),
            "faces": sorted(volume.joint_faces.get(tuple(sorted((index_of[c.a], index_of[c.b]))), ()), key=_face_key),
        }
        for c in plan.contacts
    ]


def _face_key(ref: str) -> tuple:
    """Sorts ``#o1.2.f10`` after ``#o1.2.f9`` and ``#o1.10`` after ``#o1.2``, parts in order."""
    owner, _, face = ref.rpartition(".f")
    return tuple(int(part) for part in owner.removeprefix("#o").split(".")), int(face)


class _NotConnected(Exception):
    """The mesh left parts apart from every fixed face; ``groups`` are the parts, each as its own group."""

    def __init__(self, groups: list[list[int]]):
        super().__init__("parts not connected to a fixed face")
        self.groups = groups


def _unsolved(document: Path, occurrence_ref: str, findings: list[dict]) -> FeaResult:
    """The result of a study that was stopped before the solve, by errors a person fixes in the study."""
    return FeaResult(ok=False, document=document, occurrence=occurrence_ref, glb=None, sidecar=None, findings=tuple(findings))


def _mesh_assembly(mesh_assembly, scene, plan: _Plan, parsed, resolved, ordinal_of: dict[str, int], max_h: float | None):
    """The glued, meshed assembly with its faces numbered by position, and the study's checks on it.

    Raises ``ValueError`` for a fixture or load on a bonded joint, and :class:`_NotConnected`
    when the glue left a part apart from every fixed face.
    """
    volume = mesh_assembly(scene, [part.ref for part in plan.parts], plan.bonded, parsed.contact_tolerance_mm, max_h)
    # Boundary triangles carry a face's 1-based position; `faces` is keyed by it, as for one occurrence.
    position = {ref: n for n, ref in enumerate(volume.faces, 1)}
    volume = dataclasses.replace(volume, faces={position[ref]: fp for ref, fp in volume.faces.items()})
    ordinal_of.update({ref: position[selection.ref] for ref, selection in resolved.items()})
    index_of = {part.ref: i for i, part in enumerate(plan.parts)}
    for ref, selection in resolved.items():
        if selection.ref in volume.interface_faces:
            owner = index_of[selection.occurrence_ref]
            partners = sorted({
                plan.names[index_of[c.b if index_of[c.a] == owner else c.a]]
                for c in plan.bonded if owner in (index_of[c.a], index_of[c.b])
            })
            joined = " and ".join(f"'{name}'" for name in partners)
            raise ValueError(
                f"{ref} is where '{plan.names[owner]}' is bonded to {joined}: "
                "a fixture or load can't sit on a joint; choose a face on the outside of the part"
            )
    held = {ordinal_of[ref] for fixture in parsed.fixtures for ref in fixture.faces}
    if unheld := _unheld_after_meshing(volume, held, len(plan.parts)):
        raise _NotConnected(unheld)
    return volume


def _document_ref(document: Path, glb_path: Path) -> str:
    """The STEP relative to the GLB's folder; absolute when they share no root (another Windows drive)."""
    try:
        return Path(os.path.relpath(document.resolve(), glb_path.resolve().parent)).as_posix()
    except ValueError:
        return document.resolve().as_posix()


def finer_mesh_size(size_mm: float, dofs: int) -> float | None:
    """The element size of the automatic re-solve: half, unless that passes the DOF budget.

    The DOF count grows with the cube of the size ratio, so the budget is
    spent from the first solve's: under ``DOF_WARN`` when that leaves a
    meaningfully finer mesh, otherwise under ``DOF_LIMIT`` (with a tenth of
    headroom for the estimate's error). ``None`` when even that leaves none.
    """
    from cadgen._internal.fea.solve import DOF_LIMIT, DOF_WARN

    for budget in (DOF_WARN, 0.9 * DOF_LIMIT):
        ratio = min(2.0, (budget / dofs) ** (1 / 3))
        if ratio >= 1.1:
            return size_mm / ratio
    return None


def solve_study(
    target: Path,
    out: Path | None,
    *,
    study,
    occurrence: str | None = None,
    mesh_size: float | None = None,
    vtu: bool = False,
    verbose: bool = False,
) -> FeaResult:
    """Mesh, solve and check one study, then write its GLB and sidecar.

    ``occurrence`` solves that one part alone through the single-part path,
    even in a document of several parts; every face of the study must be on it.

    When the safety factor is close to failing (:func:`checks.needs_finer`) the
    part is meshed again at half the element size (:func:`finer_mesh_size`
    keeps that under the DOF budget) and solved again. The finer solve is the
    more trustworthy one, so when it succeeds its numbers are the ones
    written, reported and checked; the checks compare its peak with the
    first's for convergence only.
    When it fails the written GLB stays the first solve's, the result carries
    one warning saying why, and no convergence finding is made.
    """
    from cadgen._internal.fea.study import parse_study

    parsed = parse_study(study)  # stdlib, before any heavy import
    logger = CliLogger("fea", verbose=verbose)
    document = Path(target)
    glb_path = Path(out) if out is not None else document.with_name(f"{document.stem}.fea.glb")
    if glb_path.suffix.lower() != ".glb":
        raise ValueError(f"OUT names the result GLB and must end in .glb: {out}")
    sidecar_path = glb_path.with_suffix(".json")
    vtu_path = glb_path.with_suffix(".vtu") if vtu else None

    from cadgen._internal.fea import checks
    from cadgen._internal.fea.mesh import mesh_assembly, mesh_occurrence, require_fea_stack, small_feature_mm

    require_fea_stack()
    scene = _open(document)
    resolved, owners = _resolve_faces(scene, parsed.face_refs)
    # A document of several parts is an assembly, whichever faces the study names; one part's study keeps the one-part path.
    plan = None
    if occurrence is None and (len(list(scene.leaves())) > 1 or parsed.parts or parsed.connections):
        plan = _plan_assembly(scene, parsed)
    ordinal_of: dict[str, int] = {}
    ignored_note = None
    if plan is None:
        if occurrence is not None:
            if parsed.parts or parsed.connections:
                ignored_note = (
                    f"--occurrence {occurrence} solves that part alone: the study's "
                    f"{' and '.join(k for k, v in (('parts', parsed.parts), ('connections', parsed.connections)) if v)} are ignored"
                )
            chosen = scene.resolve(occurrence)
            if chosen.kind != "occurrence" or chosen.ref not in {leaf.ref for leaf in scene.leaves()}:
                raise ValueError(f"{occurrence} is not a part occurrence of {document.name}")
            if stray := sorted(owners - {chosen.ref}):
                raise ValueError(
                    f"--occurrence {chosen.ref}: the study's faces are also on {', '.join(stray)}; "
                    f"every face must be on {chosen.ref}"
                )
        occurrence, resolved = _single_occurrence(scene, resolved, owners)
        occurrence_ref = occurrence.ref
        ordinal_of.update({ref: int(selection._ordinal) for ref, selection in resolved.items()})
    else:
        roots = scene.roots
        occurrence_ref = roots[0].ref if len(roots) == 1 else ", ".join(part.ref for part in plan.parts)
        part_index = {part.ref: i for i, part in enumerate(plan.parts)}
        held = {part_index[resolved[ref].occurrence_ref] for fixture in parsed.fixtures for ref in fixture.faces}
        if unheld := _unheld_groups(plan, held):
            return _unsolved(document, occurrence_ref, _not_connected(plan, unheld))

    import numpy as np

    from cadgen._internal.fea import solve
    from cadgen._internal.fea.outputs import RAMP, auto_deformation_scale, write_glb, write_vtu

    def mesh_and_solve(max_h: float | None, automatic: bool = False):
        logger.debug(f"meshing {occurrence_ref}")
        if plan is None:
            volume = mesh_occurrence(occurrence, max_h=max_h)
            materials = parsed.material
        else:
            volume = _mesh_assembly(mesh_assembly, scene, plan, parsed, resolved, ordinal_of, max_h)
            materials = plan.materials
        logger.debug(f"meshed: {len(volume.tets)} tets, {len(volume.nodes)} nodes, size {volume.max_h:.3g} mm in {volume.seconds:.1f}s")
        outcome = solve.solve_linear_static(volume, materials, parsed.fixtures, parsed.loads, ordinal_of, log=logger.debug, automatic=automatic)
        return volume, outcome

    def solved_of(volume, outcome) -> "list[Solved]":
        if plan is None:
            return [_solved(volume, outcome, parsed, ordinal_of, document.stem)]
        return [_solved_part(volume, outcome, parsed, plan, index, ordinal_of) for index in range(len(plan.parts))]

    def weakest(parts: "list[Solved]") -> "Solved":
        return min(parts, key=lambda part: math.inf if checks.safety_factor(part) is None else checks.safety_factor(part))

    try:
        volume, outcome = mesh_and_solve(mesh_size or parsed.mesh_size)
    except _NotConnected as exc:
        return _unsolved(document, occurrence_ref, _not_connected(plan, exc.groups))
    all_solved = solved_of(volume, outcome)
    solved = weakest(all_solved)
    weakest_index = next(i for i, part in enumerate(all_solved) if part is solved)
    refined = None
    finer_failure = None
    finer_size = None
    if checks.needs_finer(checks.safety_factor(solved)):
        finer_size = finer_mesh_size(volume.max_h, outcome.dofs)
        if finer_size is None:
            finer_failure = (
                f"the part's {outcome.dofs:,} degrees of freedom at {volume.max_h:g} mm leave no room under the "
                f"{solve.DOF_LIMIT:,} limit for a finer solve; its convergence is unchecked"
            )
    if finer_size is not None:
        refined = {
            "from_size_mm": round(volume.max_h, 4),
            "from_max_von_mises_MPa": round(solved.peak_MPa, 4),
            "size_mm": round(finer_size, 4),
            "max_von_mises_MPa": None,
            **({} if plan is None else {"part": solved.part}),
        }
        logger.debug(f"safety factor under {checks.RESOLVE_BELOW:g}: solving again at {finer_size:.3g} mm")
        try:
            first_outcome, first_small = outcome, small_feature_mm(volume)
            volume, outcome = mesh_and_solve(finer_size, automatic=True)
        except Exception as exc:  # a finer solve is a second opinion; the first answer stands without it
            finer_failure = (
                f"the finer solve at {refined['size_mm']:g} mm failed ({exc}); "
                "the result is the first solve's, and its convergence is unchecked"
            )
        else:
            # The checks describe the solve that is written, so every number a
            # finding quotes and every point it names is on the GLB shown; the
            # first solve's peak rides along for convergence.
            finer_parts = solved_of(volume, outcome)
            # Like with like: the finer peak of the part whose first-solve peak is recorded.
            refined["max_von_mises_MPa"] = round(finer_parts[weakest_index].peak_MPa, 4)
            all_solved = [
                dataclasses.replace(finer, coarser_peak_MPa=coarse.peak_MPa, coarser_dofs=first_outcome.dofs)
                for finer, coarse in zip(finer_parts, all_solved)
            ]
            solved = weakest(all_solved)
            if first_outcome.dofs > solve.DOF_WARN:  # the person's own size was already large
                outcome.warnings.insert(0, solve.dof_warning(first_outcome.dofs, automatic=False, small_feature_mm=first_small))
    if plan is None:
        findings = checks.findings(solved)
    else:
        name_of = {part.ref: plan.names[i] for i, part in enumerate(plan.parts)}
        findings = checks.assembly_findings(all_solved)
        findings += [checks.default_material(plan.names[i], plan.materials[i].name) for i in plan.defaulted]
        findings += [checks.gap_closed(name_of[c.a], name_of[c.b], c.gap_mm) for c in plan.bonded if c.gap_mm > 0]
        findings.sort(key=lambda finding: finding["severity"] != "error")

    # The summary is the one place the numbers are rounded; everything else
    # (the GLB's extras, the sidecar) is derived from it.
    magnitude = np.linalg.norm(outcome.displacement, axis=1)
    max_disp_index = int(magnitude.argmax())
    max_vm_index = int(outcome.von_mises.argmax())
    material = parsed.material
    reaction_total = tuple(sum(r[c] for r in outcome.reactions) for c in range(3))
    scale = parsed.deformation_scale or auto_deformation_scale(float(magnitude.max()), volume.bbox_diagonal)
    summary = {
        "max_von_mises_MPa": round(float(outcome.von_mises[max_vm_index]), 4),
        "max_von_mises_gauss_MPa": round(outcome.von_mises_gauss_max, 4),
        "max_von_mises_at_mm": [round(float(c), 3) for c in outcome.dof_locations[max_vm_index]],
        "yield_MPa": material.yield_strength,
        "max_displacement_mm": round(float(magnitude.max()), 6),
        "max_displacement_at_mm": [round(float(c), 3) for c in outcome.dof_locations[max_disp_index]],
        "applied_force_N": [round(x, 4) for x in outcome.applied],
        "reaction_force_N": [round(x, 4) for x in reaction_total],
        "deformation_scale": scale,
    }
    max_vm = summary["max_von_mises_MPa"]
    # Floored, so a factor just under a threshold is never shown as reaching it.
    factor = checks.safety_factor(solved)
    summary["safety_factor"] = None if factor is None else math.floor(factor * 1000) / 1000
    if plan is not None:
        # The headline is the weakest part: its yield and safety factor; the peak and the colours span the assembly.
        summary["yield_MPa"] = solved.yield_MPa
        summary["weakest_part"] = solved.part
        summary["weakest_part_peak_MPa"] = round(solved.peak_MPa, 4)
        summary["weakest_part_peak_at_mm"] = [round(c, 3) for c in solved.peak_at]
        summary["parts"] = [
            {
                "ref": plan.parts[i].ref,
                "name": part.part,
                "material": part.material_name,
                "yield_MPa": part.yield_MPa,
                "peak_MPa": round(part.peak_MPa, 4),
                "peak_gauss_MPa": round(part.peak_gauss_MPa, 4),
                "peak_at_mm": [round(c, 3) for c in part.peak_at],
                "safety_factor": None if (f := checks.safety_factor(part)) is None else math.floor(f * 1000) / 1000,
                "max_displacement_mm": round(part.max_displacement_mm, 6),
            }
            for i, part in enumerate(all_solved)
        ]

    warnings = list(outcome.warnings)
    if ignored_note:
        warnings.insert(0, ignored_note)
    if finer_failure:
        warnings.append(finer_failure)
    balance = max(abs(a + r) for a, r in zip(outcome.applied, reaction_total))
    if balance > 1e-3 * max(1.0, max(abs(a) for a in outcome.applied)):
        warnings.append(f"reactions do not balance the applied load (mismatch {balance:.3g} N)")

    extras = {
        "name": f"{document.stem} von Mises",
        "generator": "cadgen fea",
        # Where the STEP is from the GLB's own folder, so a viewer can find it.
        "document": _document_ref(document, glb_path),
        "occurrence": occurrence_ref,
        "deformation_scale": scale,
        # The summary's safety factor, for the viewer's plain line; null when there is none.
        "safety_factor": summary["safety_factor"],
        # One entry per raw attribute the GLB carries, for a viewer's field
        # switch. `attribute_scale` turns the stored value into the units named:
        # the displacement vector is stored in glTF metres.
        "fields": [
            {"attribute": "_VON_MISES", "name": "von Mises stress", "units": "MPa", "min": 0.0,
             "max": max_vm, "attribute_scale": 1.0},
            {"attribute": "_DISPLACEMENT", "name": "displacement", "units": "mm", "min": 0.0,
             "max": summary["max_displacement_mm"], "attribute_scale": 1000.0},
        ],
        "ramp": [[stop, list(colour)] for stop, colour in RAMP],
        # What an engineer would say about the result (checks.py), errors first.
        "findings": findings,
    }
    if plan is not None:
        # What the viewer reads for an assembly (`_PART` indexes `parts`): the weakest part's line and each joint.
        extras["weakest_part"] = summary["weakest_part"]
        extras["weakest_part_peak_MPa"] = summary["weakest_part_peak_MPa"]
        extras["max_displacement_mm"] = summary["max_displacement_mm"]
        extras["parts"] = [
            {key: part[key] for key in ("ref", "name", "material", "yield_MPa", "peak_MPa", "safety_factor", "max_displacement_mm")}
            for part in summary["parts"]
        ]
        extras["connections"] = [
            {"between": c["refs"], "names": c["between"], "type": c["type"], "area_mm2": c["area_mm2"],
             "gap_mm": c["gap_mm"], "faces": c["faces"]}
            for c in _connections(plan, volume)
        ]
    # Every boundary face of the occurrence in ordinal order; `_FACE` indexes it.
    face_ordinals = sorted(volume.faces)
    face_index = {ordinal: index for index, ordinal in enumerate(face_ordinals)}
    face_of_triangle = np.array([face_index.get(int(o), -1) for o in volume.boundary_ordinal], dtype=np.int64)

    if plan is not None:
        # Each surface triangle's part: a face is one part's, and the part's ref prefixes the face's.
        owner = {position: next(i for i, part in enumerate(plan.parts) if fp.ref.startswith(f"{part.ref}.f"))
                 for position, fp in volume.faces.items()}
        part_of_triangle = np.array([owner[int(o)] for o in volume.boundary_ordinal], dtype=np.int64)

    def bare(refs):  # the scene's own `#o1.fN`, whatever form the study named them in
        return [volume.faces[ordinal_of[ref]].ref for ref in refs]

    extras["faces"] = [volume.faces[ordinal].ref for ordinal in face_ordinals]
    extras["study"] = {
        "material": {
            "name": material.name,
            "yield_MPa": material.yield_strength,
            "youngs_GPa": round(material.E / 1000.0, 6),
            "poisson": material.nu,
        },
        "fixtures": [{"type": fixture.type, "faces": bare(fixture.faces)} for fixture in parsed.fixtures],
        "loads": [
            {"type": load.type, "faces": bare(load.faces),
             **({"vector_N": [float(c) for c in load.vector]} if load.type == "force" else {"pressure_MPa": load.pressure})}
            for load in parsed.loads
        ],
        "mesh": {
            "size_mm": round(volume.max_h, 4),
            "order": 2,
            "elements": int(len(volume.tets)),
            "refined_from_mm": refined["from_size_mm"] if refined and refined["max_von_mises_MPa"] is not None else None,
        },
        "margin": parsed.margin,
    }
    write_glb(
        glb_path,
        positions=outcome.dof_locations,
        displacement=outcome.displacement,
        values=outcome.von_mises,
        triangles6=outcome.boundary_quadratic,
        face_of_triangle=face_of_triangle,
        scale=scale,
        value_range=(0.0, max_vm),
        extras=extras,
        **({} if plan is None else {
            "values_by_part": outcome.von_mises_parts,
            "part_of_triangle": part_of_triangle,
        }),
    )
    if vtu_path is not None:
        vertex_count = outcome.vertices
        write_vtu(
            vtu_path,
            positions=outcome.dof_locations[:vertex_count],
            tets=outcome.tets,
            displacement=outcome.displacement[:vertex_count],
            values=outcome.von_mises[:vertex_count],
        )

    mesh_info = {
        "elements": int(len(volume.tets)),
        "nodes": int(len(volume.nodes)),
        "dofs": outcome.dofs,
        "size_mm": round(volume.max_h, 4),
        "order": 2,
        "mesher": "netgen",
        "solver": outcome.solver,
    }
    timings = {"mesh_s": round(volume.seconds, 3), **{k: round(v, 3) for k, v in outcome.timings.items()}}
    sidecar = {
        "generator": "cadgen fea",
        "document": str(document),
        "occurrence": occurrence_ref,
        "study": parsed.source,
        "material": material.as_dict(),
        "faces": {ref: dataclasses.asdict(volume.faces[ordinal]) for ref, ordinal in ordinal_of.items()},
        "summary": summary,
        "fixtures": [
            {"faces": list(fixture.faces), "type": fixture.type, "reaction_N": [round(x, 4) for x in reaction]}
            for fixture, reaction in zip(parsed.fixtures, outcome.reactions)
        ],
        "fields": extras["fields"],
        "mesh": mesh_info,
        "timings": timings,
        "warnings": warnings,
        "findings": findings,
        # An assembly: how its parts are joined (the parts' own results are in the summary).
        **({} if plan is None else {"connections": _connections(plan, volume)}),
        # The first and the finer solve's size and peak, when the part was solved twice.
        "refined": refined,
        "files": {"glb": glb_path.name, "vtu": vtu_path.name if vtu_path else None},
    }
    sidecar_path.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
    logger.debug(f"wrote {glb_path.name}, {sidecar_path.name}" + (f", {vtu_path.name}" if vtu_path else ""))
    return FeaResult(
        ok=True,
        document=document,
        occurrence=occurrence_ref,
        glb=glb_path,
        sidecar=sidecar_path,
        vtu=vtu_path,
        summary=summary,
        mesh=mesh_info,
        timings=timings,
        warnings=tuple(warnings),
        findings=tuple(findings),
    )
