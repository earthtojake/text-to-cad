"""What the ``cadgen.fea`` verbs do, end to end."""

from __future__ import annotations

import dataclasses
import json
import math
import os
from pathlib import Path
from typing import TYPE_CHECKING

from cadgen._internal.fea.checks import quoted
from cadgen.cli_logging import CliLogger
from cadgen.results import FeaFace, FeaFacesResult, FeaPair, FeaPart, FeaPartsResult, FeaResult

if TYPE_CHECKING:
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
            raise ValueError(f"{ref} is a {selection.kind} reference; fixtures, loads and checks take faces (#o1.f17)")
        resolved[ref] = selection
        owners.add(selection.occurrence_ref)
    return resolved, owners


def _single_occurrence(
    scene: "StepScene", resolved: dict[str, "Selection"], owners: set[str], chosen: str | None = None
) -> tuple["Occurrence", dict[str, "Selection"]]:
    """The one leaf occurrence every face ref belongs to, and each ref resolved.

    A study that names no face (a free-free modal study) solves ``chosen`` (``--occurrence``), else
    the document's only part."""
    if len(owners) > 1:
        raise ValueError(
            f"the study's faces span {len(owners)} occurrences ({', '.join(sorted(owners))}); "
            "a study solves one part, so every face must be on the same occurrence"
        )
    if not owners:
        if chosen is None:
            leaves = list(scene.leaves())
            if len(leaves) != 1:
                raise ValueError(f"the study names no face and the document has {len(leaves)} parts; "
                                 "choose one with --occurrence")
            chosen = leaves[0].ref
        return scene.resolve(chosen), resolved  # type: ignore[return-value]
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
    # Contact detection is OCP, numpy and scipy, all base dependencies: no fea extra needed.
    from cadgen._internal.fea.assembly import detect_contacts, detect_overlaps, display_names, interferences, list_parts

    if not contact_tolerance_mm >= 0:
        raise ValueError("contact_tolerance_mm must be zero or more")
    logger = CliLogger("fea", verbose=verbose)
    logger.info("reading the parts")
    scene = _open(Path(target))
    parts = list_parts(scene)
    logger.info(f"read {len(parts)} parts; looking for pairs within {max(contact_tolerance_mm, _NEAR_MISS_MM)} mm")
    name = dict(zip((part.ref for part in parts), display_names(parts)))
    shared = detect_overlaps(parts, log=logger.info)
    pressed, overlaps = interferences(shared, contact_tolerance_mm)
    logger.info(f"found {len(overlaps)} overlapping pairs" + (f" and {len(pressed)} interferences within the tolerance" if pressed else ""))
    found = detect_contacts(
        parts, max(contact_tolerance_mm, _NEAR_MISS_MM), skip={frozenset((o.a, o.b)) for o in shared}, log=logger.info
    )
    logger.info(f"found {len(found)} touching or near pairs")
    order = {part.ref: i for i, part in enumerate(parts)}
    pairs = [
        FeaPair(
            between=(name[c.a], name[c.b]),
            refs=(c.a, c.b),
            area_mm2=round(c.area_mm2, 4),
            gap_mm=round(c.gap_mm, 6),
            type="bonded" if c.gap_mm <= contact_tolerance_mm * (1 + 1e-6) else "not_connected",
            interference_mm=round(c.interference_mm, 6),
        )
        for c in sorted(found + pressed, key=lambda c: sorted((order[c.a], order[c.b])))
    ] + [
        FeaPair(between=(name[o.a], name[o.b]), refs=(o.a, o.b), area_mm2=0.0, gap_mm=0.0, type="overlapping",
                overlap_mm3=round(o.volume_mm3, 4))
        for o in overlaps
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
    #: Every pair of parts whose solids overlap (never bonded), and the ones the study marks free.
    overlaps: list
    freed_overlaps: set
    #: Per part, the group of parts bonded to it (directly or through others).
    group_of: list[int]
    #: The pairs (part indices) a contact or bolt study's ``contact`` and ``bolt`` connections name: meshed apart, like free ones.
    contact: set = dataclasses.field(default_factory=set)


def find_part(parts: list, names: list[str], key: str, where: str) -> int:
    """The part a study names by occurrence ref or by name; ``names`` are the display names, for the error."""
    for index, part in enumerate(parts):
        if key in (part.ref, f"#{key}"):
            return index
    named = [index for index, part in enumerate(parts) if part.name == key]
    if len(named) > 1:
        raise ValueError(f"{where}: {key!r} names {len(named)} parts ({', '.join(parts[i].ref for i in named)}); use a ref")
    if not named:
        raise ValueError(f"{where}: no part named {key!r}; the parts are {', '.join(quoted(name) for name in names)}")
    return named[0]


def _plan_assembly(scene: "StepScene", parsed, logger: CliLogger) -> _Plan:
    from cadgen._internal.fea.assembly import joined_groups, detect_contacts, detect_overlaps, display_names, interferences, list_parts

    logger.info("reading the parts")
    parts = list_parts(scene)
    logger.info(f"read {len(parts)} parts; looking for contacts within {parsed.contact_tolerance_mm:g} mm")
    names = display_names(parts)
    index_of = {part.ref: i for i, part in enumerate(parts)}

    materials = [parsed.material] * len(parts)
    given: set[int] = set()
    for key, material in parsed.parts.items():
        index = find_part(parts, names, key, f"parts[{key!r}]")
        if index in given:
            raise ValueError(f"parts[{key!r}]: {quoted(names[index])} is named twice in 'parts'")
        given.add(index)
        materials[index] = material

    shared = detect_overlaps(parts, log=logger.info)
    # An overlap no thicker than the tolerance is an interference: contact, bonded like a gap.
    pressed, overlaps = interferences(shared, parsed.contact_tolerance_mm)
    logger.info(f"found {len(overlaps)} overlapping pairs" + (f" and {len(pressed)} interferences within the tolerance" if pressed else ""))
    overlap_of = {frozenset((index_of[o.a], index_of[o.b])): o for o in overlaps}
    contacts = detect_contacts(
        parts, parsed.contact_tolerance_mm, skip={frozenset((o.a, o.b)) for o in shared}, log=logger.info
    )
    contacts = sorted(contacts + pressed, key=lambda c: sorted((index_of[c.a], index_of[c.b])))
    logger.info(f"found {len(contacts)} touching pairs")
    pair_of = {frozenset((index_of[c.a], index_of[c.b])) for c in contacts}
    freed: set[frozenset[int]] = set()
    freed_overlaps: set[frozenset[int]] = set()
    contact: set[frozenset[int]] = set()
    seen: set[frozenset[int]] = set()
    bolted: set[frozenset[int]] = set()
    for n, connection in enumerate(parsed.connections):
        where = f"connections[{n}]"
        i, j = (find_part(parts, names, key, f"{where}.between") for key in connection.between)
        pair = frozenset((i, j))
        if i == j:
            raise ValueError(f"{where}.between: both names are {quoted(names[i])}")
        # Several bolts may clamp the same two parts (a bolt study meshes them apart and presses them together).
        if pair in seen and not (connection.type == "bolt" and pair in bolted):
            raise ValueError(f"{where}: {quoted(names[i])} and {quoted(names[j])} are connected twice")
        seen.add(pair)
        if connection.type == "bolt":
            bolted.add(pair)
        if connection.type == "bonded" and pair in overlap_of:
            raise ValueError(
                f"{where}: {quoted(names[i])} and {quoted(names[j])} overlap by {overlap_of[pair].volume_mm3:.3g} mm³, "
                "so they can't be bonded; fix the geometry"
            )
        if connection.type == "bonded" and pair not in pair_of:
            raise ValueError(
                f"{where}: {quoted(names[i])} and {quoted(names[j])} don't touch within {parsed.contact_tolerance_mm:g} mm, "
                "so they can't be bonded; raise contact_tolerance_mm or move them together"
            )
        if connection.type in ("free", "contact", "bolt") and pair in pair_of:
            freed.add(pair)
        if connection.type in ("contact", "bolt"):
            contact.add(pair)
        if connection.type == "free" and pair in overlap_of:
            freed_overlaps.add(pair)

    bonded = [c for c in contacts if frozenset((index_of[c.a], index_of[c.b])) not in freed]
    group_of = [0] * len(parts)
    for number, group in enumerate(joined_groups(len(parts), [(index_of[c.a], index_of[c.b]) for c in bonded])):
        for index in group:
            group_of[index] = number
    for o in overlaps:
        i, j = index_of[o.a], index_of[o.b]
        if group_of[i] == group_of[j]:
            through = _joined_through([(index_of[c.a], index_of[c.b]) for c in bonded], i, j)
            raise ValueError(
                f"{quoted(names[i])} and {quoted(names[j])} overlap by {o.volume_mm3:.3g} mm³ and are joined through "
                f"{' and '.join(quoted(names[k]) for k in through)}, so gluing would fuse them: fix the geometry"
            )
    for pair in freed:
        i, j = sorted(pair)
        if group_of[i] == group_of[j]:
            raise ValueError(
                f"connections: {quoted(names[i])} and {quoted(names[j])} are also joined through other bonded parts, so one joint "
                "between them can't be freed on its own (not yet supported); free the parts' other connections too"
            )
    return _Plan(parts, names, materials, sorted(set(range(len(parts))) - given), contacts, bonded, overlaps, freed_overlaps, group_of,
                 contact)


def _joined_through(pairs: list[tuple[int, int]], start: int, end: int) -> list[int]:
    """The parts on a shortest chain of bonded pairs from ``start`` to ``end``, not counting either."""
    near: dict[int, list[int]] = {}
    for a, b in pairs:
        near.setdefault(a, []).append(b)
        near.setdefault(b, []).append(a)
    came: dict[int, int | None] = {start: None}
    queue = [start]
    for node in queue:
        for other in near.get(node, ()):
            if other not in came:
                came[other] = node
                queue.append(other)
    chain, node = [], came[end]
    while node is not None and node != start:
        chain.append(node)
        node = came[node]
    return chain[::-1]


def _not_connected(plan: _Plan, unheld: list[list[int]], logger: CliLogger) -> list[dict]:
    """One error per group of parts nothing holds: which parts, and the nearest part that is not among them.

    The nearest part is found nearest-box first: the exact distance is only
    taken to parts whose box is nearer than the best found, not to every part.
    """
    from cadgen._internal.fea.assembly import bounding_box, part_centre, part_gap

    logger.info(f"{len(unheld)} groups of parts are not connected to a fixed part; finding the nearest part to each")
    boxes = [bounding_box(part.shape, 0.0) for part in plan.parts]
    index_of = {part.ref: i for i, part in enumerate(plan.parts)}
    found = []
    for group in unheld:
        members = ", ".join(quoted(plan.names[i]) for i in group)
        refs = {plan.parts[i].ref for i in group}
        overlapped = max(
            (o for o in plan.overlaps if (o.a in refs) != (o.b in refs)), key=lambda o: o.volume_mm3, default=None
        )
        nearest = None
        if overlapped is None:
            by_box = sorted(
                (min(boxes[i].Distance(boxes[other]) for i in group), other)
                for other in range(len(plan.parts)) if other not in group
            )
            for lower, other in by_box:
                if nearest is not None and lower >= nearest[0]:
                    break
                for i in group:
                    gap = part_gap(plan.parts[i], plan.parts[other])
                    if gap is not None and (nearest is None or gap < nearest[0]):
                        nearest = (gap, other)
        if overlapped is not None:
            other = overlapped.b if overlapped.a in refs else overlapped.a
            where = (
                f": it overlaps {quoted(plan.names[index_of[other]])} by {overlapped.volume_mm3:.3g} mm³ instead of touching it, "
                "so it isn't bonded to it; fix the geometry or move them apart"
            )
        elif nearest is None:
            where = ""
        elif nearest[0] <= 1e-6:
            where = f": it touches {quoted(plan.names[nearest[1]])} but isn't bonded to it"
        else:
            where = f": nearest part {quoted(plan.names[nearest[1]])} is {nearest[0]:.3g} mm away"
        found.append({
            "check": "fea",
            "severity": "error",
            "type": "not_connected",
            "summary": f"{members} {'isn' if len(group) == 1 else 'aren'}'t connected to anything that is held{where}",
            "description": "no chain of bonded parts joins it to a fixed face, so the solve was not run",
            "items": [
                {"text": f"{quoted(plan.names[i])}", "ref": plan.parts[i].ref,
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
            "type": "bonded" if (c.a, c.b) in bonded else "contact" if frozenset((index_of[c.a], index_of[c.b])) in plan.contact else "free",
            "area_mm2": round(c.area_mm2, 4),
            "gap_mm": round(c.gap_mm, 6),
            "interference_mm": round(c.interference_mm, 6),
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


def _mesh_assembly(mesh_assembly, scene, plan: _Plan, parsed, resolved, ordinal_of: dict[str, int], max_h: float | None, log, refine: float = 1.0, **mesh_options):
    """The glued, meshed assembly with its faces numbered by position, and the study's checks on it.

    Raises ``ValueError`` for a fixture or load on a face that is wholly a bonded joint, and :class:`_NotConnected`
    when the glue left a part apart from every fixed face.
    """
    volume = mesh_assembly(scene, [part.ref for part in plan.parts], plan.bonded, parsed.contact_tolerance_mm, max_h, log, refine=refine, **mesh_options)
    # Boundary triangles carry a face's 1-based position; `faces` is keyed by it, as for one occurrence.
    position = {ref: n for n, ref in enumerate(volume.faces, 1)}
    volume = dataclasses.replace(volume, faces={position[ref]: fp for ref, fp in volume.faces.items()})
    ordinal_of.update({ref: position[selection.ref] for ref, selection in resolved.items()})
    index_of = {part.ref: i for i, part in enumerate(plan.parts)}
    for ref, selection in resolved.items():
        if ref not in parsed.face_refs:  # a check's face: the check says when there is nothing of it to judge
            continue
        # A face only partly covered by a joint has outer triangles: it holds or loads its exposed area.
        exposed = (volume.boundary_ordinal == position[selection.ref]).any()
        if selection.ref in volume.interface_faces and not exposed:
            owner = index_of[selection.occurrence_ref]
            partners = sorted({
                plan.names[index_of[c.b if index_of[c.a] == owner else c.a]]
                for c in plan.bonded if owner in (index_of[c.a], index_of[c.b])
            })
            joined = " and ".join(quoted(name) for name in partners)
            raise ValueError(
                f"{ref} is where {quoted(plan.names[owner])} is bonded to {joined}: "
                "a fixture or load can't sit on a joint; choose a face, or part of one, that is not covered by another part"
            )
    held = {ordinal_of[ref] for ref in parsed.inputs.anchor_refs}
    if parsed.inputs.requires_anchor and (unheld := _unheld_after_meshing(volume, held, len(plan.parts))):
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

    The DOF count grows with the cube of the size ratio (the mesher refines
    curved features by the same ratio, so they grow too), so the budget is
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




#: The analyses whose GLB, extras and sidecar are today's exactly: nothing analysis-specific is added for them.
_STATIC = "static"


def _field_entry(spec, low: float, high: float, capped: dict | None = None, *, static: bool) -> dict:
    """One ``extras.fields`` entry: today's keys; a non-static analysis also says the view name, signed and per-frame,
    and, where its colours stop below the field's peak (``capped``: ``{"quantile", "peak"}``), where and the peak."""
    entry = {"attribute": spec.attribute, "name": spec.title, "units": spec.units, "min": low, "max": high,
             "attribute_scale": spec.attribute_scale}
    if capped and not static:
        entry["capped"] = dict(capped)
    if not static:
        entry["field"] = spec.name
        if spec.signed:
            entry["signed"] = True
        if spec.per_frame:
            entry["per_frame"] = True
    return entry


def _series_extras(series) -> dict:
    return {
        "kind": series.kind, "unit": series.unit, "default": series.default,
        "frames": [{"value": frame.value, "label": frame.label, "attributes": dict(frame.attributes)} for frame in series.frames],
    }


def _analysis_extras(analysis, result) -> dict:
    """``extras.analysis`` for a non-static analysis: what it is, its tier, its limits and its warnings."""
    return {
        "type": analysis.name,
        "tier": analysis.tier,
        "word": analysis.word,
        "estimate": bool(analysis.estimate_only),
        "limits": list(analysis.limits),
        "noun": getattr(analysis, "noun", "this load"),
        "reference_C": result.scalars.get("reference_C"),
        "warnings": list(result.scalars.get("analysis_warnings", ())),
        # Structured facts an analysis adds for the viewer (cfd's Reynolds number and its limit).
        **result.scalars.get("analysis_extras", {}),
    }


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

    The study names its analysis (static by default; ``analyses.get_analysis``)
    and the analysis does the physics: its ``parse``, ``solve``, checks,
    findings and summary. This is the orchestration every analysis shares:
    resolve the faces, plan an assembly, mesh, build the element space once,
    solve each upstream analysis on it first, re-solve finer when the analysis
    asks, judge, and write the GLB (with the analysis's fields and series) and
    the sidecar.

    ``occurrence`` solves that one part alone through the single-part path,
    even in a document of several parts; every face of the study must be on it.

    When the analysis says the answer is close to failing (static: the safety
    factor, :func:`checks.needs_finer`) the part is meshed again at half the
    element size (:func:`finer_mesh_size` keeps that under the DOF budget),
    finer by the same ratio at curved features, and solved again. The finer
    solve is the more trustworthy one, so when it succeeds its numbers are the
    ones written, reported and checked; the first solve's peak is kept for
    convergence only. When it fails the written GLB stays the first solve's,
    the result carries one warning saying why, and no convergence finding is made.
    """
    from cadgen._internal.fea.analyses import get_analysis
    from cadgen._internal.fea.study import parse_study

    parsed = parse_study(study)  # stdlib, before any heavy import
    analysis = get_analysis(parsed.analysis)
    inputs = parsed.inputs
    static = parsed.analysis == _STATIC
    logger = CliLogger("fea", verbose=verbose)
    document = Path(target)
    glb_path = Path(out) if out is not None else document.with_name(f"{document.stem}.fea.glb")
    if glb_path.suffix.lower() != ".glb":
        raise ValueError(f"OUT names the result GLB and must end in .glb: {out}")
    sidecar_path = glb_path.with_suffix(".json")
    vtu_path = glb_path.with_suffix(".vtu") if vtu else None

    from cadgen._internal.fea import checks
    from cadgen._internal.fea.mesh import default_mesh_size, mesh_assembly, mesh_occurrence, require_fea_stack, small_feature_mm

    require_fea_stack()
    scene = _open(document)
    resolved, owners = _resolve_faces(scene, tuple(dict.fromkeys((*parsed.face_refs, *parsed.check_faces))))
    # A document of several parts is an assembly, whichever faces the study names; one part's study keeps the one-part path.
    plan = None
    if occurrence is None and (len(list(scene.leaves())) > 1 or parsed.parts or parsed.connections):
        plan = _plan_assembly(scene, parsed, logger)
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
        occurrence, resolved = _single_occurrence(scene, resolved, owners, chosen.ref if occurrence is not None else None)
        occurrence_ref = occurrence.ref
        ordinal_of.update({ref: int(selection.ordinal) for ref, selection in resolved.items()})
    else:
        roots = scene.roots
        occurrence_ref = roots[0].ref if len(roots) == 1 else ", ".join(part.ref for part in plan.parts)
        part_index = {part.ref: i for i, part in enumerate(plan.parts)}
        held = {part_index[resolved[ref].occurrence_ref] for ref in inputs.anchor_refs}
        if inputs.requires_anchor and (unheld := _unheld_groups(plan, held)):
            return _unsolved(document, occurrence_ref, _not_connected(plan, unheld, logger))

    import time

    import numpy as np

    from cadgen._internal.fea import solve
    from cadgen._internal.fea.analyses.base import SolveContext
    from cadgen._internal.fea.femspace import FemSpace
    from cadgen._internal.fea.outputs import RAMP, write_glb, write_vtu

    from cadgen._internal.fea import fit

    materials = (parsed.material,) if plan is None else tuple(plan.materials)
    requested = mesh_size or parsed.mesh_size

    # The fit-the-budget ladder, before meshing: targets from the study's `fit`, the part's geometry to estimate from.
    budget = fit.default_budget(parsed.fit)
    fit_plan = fit.FitPlan(
        size_mm=requested, order=parsed.mesh_order,
        allow=None if not parsed.fit or "allow" not in parsed.fit else tuple(parsed.fit["allow"]),
    )
    if plan is None:
        part_shape = occurrence.shape()
        geometry = fit.geometry_of(part_shape.wrapped, occurrence.ref)
        geometry.bbox_diagonal_mm = float(part_shape.bounding_box().diagonal)
    else:
        geometry = fit.merge_geometry([fit.geometry_of(part.shape, part.ref, keep_shape=False) for part in plan.parts])
    fit_plan.requested_mm = requested or default_mesh_size(geometry.bbox_diagonal_mm)

    def context(volume, *, space=None, automatic=False, meshed=None):
        return SolveContext(
            volume=volume, materials=materials, ordinal_of=ordinal_of, space=space, log=logger.debug,
            automatic=automatic, upstream={}, budget=budget, plan=fit_plan,
            study=parsed, assembly=plan, part_name=document.stem, geometry=geometry, meshed_plan=meshed,
        )

    def ladder(ctx, *, tail: bool) -> list:
        try:
            return fit.fit_budget(analysis, ctx, inputs, tail=tail)
        except NotImplementedError:  # an analysis that cannot estimate yet takes no rung
            return []

    steps = ladder(context(None), tail=False)

    def mesh(max_h: float | None, refine: float = 1.0, size_field: dict | None = None):
        # Only what differs from the default reaches the mesher, so a study the ladder left alone meshes as before.
        options: dict = {} if fit_plan.order == 2 else {"order": fit_plan.order}
        if size_field:
            options["size_field"] = size_field
        logger.debug(f"meshing {occurrence_ref}")
        if plan is None:
            if fit_plan.prepared is not None:
                options["prepared"] = fit_plan.prepared
            volume = mesh_occurrence(occurrence, max_h=max_h, refine=refine, **options)
        else:
            volume = _mesh_assembly(mesh_assembly, scene, plan, parsed, resolved, ordinal_of, max_h, logger.info, refine, **options)
        logger.debug(f"meshed: {len(volume.tets)} tets, {len(volume.nodes)} nodes, size {volume.max_h:.3g} mm in {volume.seconds:.1f}s")
        return volume

    def solve_on(volume, automatic: bool = False):
        started = time.perf_counter()
        space = FemSpace.build(volume, fit_plan.order)
        built = time.perf_counter() - started
        ctx = context(volume, space=space, automatic=automatic, meshed=fit.mesh_key(fit_plan))
        # Each upstream analysis on the same element space first, from the same study document
        # (an analysis whose source the study names, fatigue's `from`, says which: `upstream_for(inputs)`).
        for name in (analysis.upstream_for(inputs) if hasattr(analysis, "upstream_for") else analysis.upstream):
            upstream = get_analysis(name)
            ctx.upstream[name] = upstream.solve(ctx, upstream.parse(parsed.source))
        result = analysis.solve(ctx, inputs)
        result.timings["mesh_to_fem_s"] = result.timings.get("mesh_to_fem_s", 0.0) + built
        # The analysis may hand back a different mesh (a symmetric half mirrored into the whole part).
        return ctx.volume, ctx, result

    def mesh_and_solve(max_h: float | None, automatic: bool = False, refine: float = 1.0):
        return solve_on(mesh(max_h, refine, size_field=study_field), automatic)

    # The study's own finer balls (mesh.refine), kept through every pass.
    from cadgen._internal.fea.study import refine_points

    study_points = refine_points(getattr(parsed, "mesh_refine", ()))
    study_field = {"points": study_points, "radius_mm": 0.0} if study_points else None
    try:
        volume = mesh(fit_plan.size_mm, size_field=study_field)
        # The ladder again, on the mesh's own counts: a mesh the geometry under-guessed may still take a rung.
        key = fit.mesh_key(fit_plan)
        steps += ladder(context(volume, meshed=key), tail=True)
        if fit.mesh_key(fit_plan) != key:
            volume = mesh(fit_plan.size_mm, size_field=study_field)
        volume, ctx, result = solve_on(volume)
    except _NotConnected as exc:
        return _unsolved(document, occurrence_ref, _not_connected(plan, exc.groups, logger))
    refined = None
    finer_failure = None
    finer_size = None
    finer_written = False
    if fit_plan.two_pass:
        # local_refine's second pass: fine where the coarse pass peaked, coarse away from it.
        first = result
        _, first_value = fit.governing(analysis, first)

        def estimate_with(field):
            saved, fit_plan.size_field = fit_plan.size_field, field
            try:
                return analysis.estimate(context(None), inputs)
            finally:
                fit_plan.size_field = saved

        field = fit.refine_field(analysis, ctx, inputs, first, budget, estimate_with)
        fit_plan.size_field = field
        refined = analysis.refined_record(first, volume.max_h, fit_plan.refine_to_mm, assembly=plan is not None) \
            if hasattr(analysis, "refined_record") else None
        logger.debug(f"local refine: solving again at {fit_plan.refine_to_mm:.3g} mm near the peak")
        if study_points:
            field = {**field, "points": [*study_points, *field.get("points", [])]}
        volume, ctx, result = solve_on(mesh(fit_plan.size_mm, size_field=field))
        _, second_value = fit.governing(analysis, result)
        if refined is not None:
            result = analysis.merge_finer(first, result, refined)
            finer_written = True
        word = getattr(analysis, "governing_word", "the peak")
        kept = tuple(volume.faces[o].ref for o in sorted(field.get("faces", {})) if o in volume.faces)
        steps = [dataclasses.replace(fit.pass_step(s, first_value, second_value, word), faces=kept) if s.rung == "local_refine" else s
                 for s in steps]
    elif analysis.needs_finer(result, inputs, []):
        finer_size = finer_mesh_size(volume.max_h, result.dofs)
        if finer_size is None:
            finer_failure = (
                f"the part's {result.dofs:,} degrees of freedom at {volume.max_h:g} mm leave no room under the "
                f"{solve.DOF_LIMIT:,} limit for a finer solve; its convergence is unchecked"
            )
        elif steps:
            # A model the ladder adapted re-solves finer only when that, too, fits the budget.
            saved = fit_plan.size_mm
            fit_plan.size_mm = finer_size
            try:
                finer_estimate = analysis.estimate(context(None), inputs)
            finally:
                fit_plan.size_mm = saved
            if not finer_estimate.fits(budget):
                steps.append(fit.Step(
                    fit.TAIL, "Did not re-solve finer to stay in budget, so the peak's convergence is unchecked",
                    "a finer mesh may still move the peak by 10% or more", None,
                    detail={"finer_size_mm": round(finer_size, 4)},
                ))
                finer_size = None
    if finer_size is not None:
        refined = analysis.refined_record(result, volume.max_h, finer_size, assembly=plan is not None)
        logger.debug(f"close to the limit: solving again at {finer_size:.3g} mm")
        try:
            first, first_small = result, small_feature_mm(volume)
            # Finer at fillets and holes too, by the same ratio: there the curvature, not the size, sets the mesh.
            finer_volume, finer_ctx, finer_result = mesh_and_solve(finer_size, automatic=True, refine=volume.max_h / finer_size)
        except Exception as exc:  # a finer solve is a second opinion; the first answer stands without it
            finer_failure = (
                f"the finer solve at {refined['size_mm']:g} mm failed ({exc}); "
                "the result is the first solve's, and its convergence is unchecked"
            )
        else:
            # The checks describe the solve that is written, so every number a
            # finding quotes and every point it names is on the GLB shown.
            volume, ctx = finer_volume, finer_ctx
            result = analysis.merge_finer(first, finer_result, refined)
            finer_written = True
            if first.dofs > solve.DOF_WARN:  # the person's own size was already large
                result.warnings.insert(0, solve.dof_warning(first.dofs, automatic=False, small_feature_mm=first_small))
    if fit_plan.order == 1 and any(s.rung == "linear_elements" for s in steps):
        steps = [fit.measure_linear(analysis, s, budget, geometry, fit_plan, mesh, solve_on, context, inputs)
                 if s.rung == "linear_elements" else s for s in steps]
    # An analysis may say a step again once its solve knows what it did (reduce_modes: the modes it kept).
    # Optional: `settle_steps(result, steps) -> steps`, returning new steps, never changing one in place.
    if hasattr(analysis, "settle_steps"):
        steps = list(analysis.settle_steps(result, steps))
    result.steps = list(steps)

    # Each check of the study (`Study.checks`) judged on the written solve, in the study's order,
    # before the findings: an analysis's own check findings (thermal's temperature_over_limit) read them.
    check_results = [analysis.judge(check, index, ctx, result, inputs) for index, check in enumerate(parsed.checks)]
    findings = analysis.findings(ctx, result, inputs, check_results, assembly=plan is not None)
    if plan is not None:
        name_of = {part.ref: plan.names[i] for i, part in enumerate(plan.parts)}
        findings += [checks.default_material(plan.names[i], plan.materials[i].name) for i in plan.defaulted]
        findings += [checks.gap_closed(name_of[c.a], name_of[c.b], c.gap_mm) for c in plan.bonded if c.gap_mm > 0]
        findings += [
            checks.gap_closed(name_of[c.a], name_of[c.b], c.interference_mm, interference=True)
            for c in plan.bonded if c.interference_mm > 0
        ]
        index_of = {part.ref: i for i, part in enumerate(plan.parts)}
        findings += [
            checks.overlapping_parts(name_of[o.a], name_of[o.b], o.volume_mm3)
            for o in plan.overlaps if frozenset((index_of[o.a], index_of[o.b])) not in plan.freed_overlaps
        ]
        findings.sort(key=lambda finding: finding["severity"] != "error")

    # Each ladder step is an info finding for the agent, after everything an engineer would say.
    findings += [step.finding() for step in steps]

    if check_found := checks.check_findings(check_results, assembly=plan is not None):
        findings = sorted(findings + check_found, key=lambda finding: finding["severity"] != "error")
    material = parsed.material
    scale = analysis.deformation_scale(result, volume.bbox_diagonal, parsed.deformation_scale)
    result.scalars.setdefault("deformation_scale", scale)
    result.scalars.setdefault("yield_MPa", material.yield_strength if material is not None else None)
    # The summary is the one place the numbers are rounded; everything else
    # (the GLB's extras, the sidecar) is derived from it.
    summary = analysis.summary(result, inputs, check_results)

    warnings = list(result.warnings)
    if ignored_note:
        warnings.insert(0, ignored_note)
    if finer_failure:
        warnings.append(finer_failure)
    if result.reactions:
        reaction_total = tuple(sum(r[c] for r in result.reactions) for c in range(3))
        balance = max(abs(a + r) for a, r in zip(result.applied, reaction_total))
        if balance > 1e-3 * max(1.0, max(abs(a) for a in result.applied)):
            warnings.append(f"reactions do not balance the applied load (mismatch {balance:.3g} N)")

    ranges = analysis.field_ranges(summary, result)
    fields = [_field_entry(spec, *ranges[spec.name], static=static) for spec in analysis.fields if spec.name in ranges]
    # The field the surface is coloured by: the first scalar field, else the first field's magnitude (a mode shape).
    primary = next((spec for spec in analysis.fields if spec.components == 1), analysis.fields[0])
    extras = {
        "name": analysis.extras_name(document.stem),
        "generator": "cadgen fea",
        # Where the STEP is from the GLB's own folder, so a viewer can find it.
        "document": _document_ref(document, glb_path),
        "occurrence": occurrence_ref,
        "deformation_scale": scale,
        **analysis.extras_head(summary),
        # One entry per raw attribute the GLB carries, for a viewer's field
        # switch. `attribute_scale` turns the stored value into the units named:
        # a vector is stored in glTF metres.
        "fields": fields,
        "ramp": [[stop, list(colour)] for stop, colour in RAMP],
        # What an engineer would say about the result (checks.py), errors first.
        "findings": findings,
        # Each check judged (`kind`, `label`, `value`, `limit`, `unit`, `ratio`, `close_at`, `status`, `where`): the verdict's.
        "checks": check_results,
    }
    if plan is not None:
        extras.update(analysis.extras_assembly(summary))
        if not extras.get("parts"):
            # An analysis with no per-part results of its own still says what each part is and is made of, so the
            # viewer names a face's part ("coil · face 3") and lists each part's material, not the study's alone.
            extras["parts"] = [{"ref": part.ref, "name": name, "material": material.name, "yield_MPa": material.yield_strength}
                               for part, name, material in zip(plan.parts, plan.names, plan.materials)]
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
    echo = {}
    if material is not None:
        echo["material"] = {
            "name": material.name,
            "yield_MPa": material.yield_strength,
            "youngs_GPa": round(material.E / 1000.0, 6),
            "poisson": material.nu,
        }
    echo.update(analysis.study_echo(inputs, bare))
    echo["mesh"] = {
        "size_mm": round(volume.max_h, 4),
        "order": fit_plan.order,
        "elements": int(len(volume.tets)),
        "refined_from_mm": refined["from_size_mm"] if finer_written else None,
    }
    if any(spec.kind == "stress" for spec in analysis.checks):
        echo["margin"] = parsed.margin
    extras["study"] = echo
    if parsed.view is not None:
        # The agent's controls, presets and markers for the result, as the study checked them.
        extras["view"] = parsed.view
    fit_steps = [step.as_dict() for step in steps]
    if fit_steps:
        # What the fit-the-budget ladder did to make this run fit, in order; omitted when it did nothing.
        extras["fit"] = fit_steps
    if not static:
        extras["analysis"] = _analysis_extras(analysis, result)
        if result.series is not None:
            extras["series"] = _series_extras(result.series)

    # The primary field colours the surface. Its values go into `_VON_MISES` only when that is its own
    # attribute (static and the stress family, each part's own stress in an assembly); every field rides
    # along under its own attribute, so a temperature or a life carries no mislabelled stress copy.
    colour = result.fields[primary.name]
    if primary.components == 3:
        colour = np.linalg.norm(colour, axis=1)
    stress_coloured = primary.attribute == "_VON_MISES"
    # The colour values go under _VON_MISES only when they are von Mises; a von Mises field that is
    # not the colouring one (cfd's mapped structure) is written like any other listed field.
    written = {"_DISPLACEMENT"} | ({"_VON_MISES"} if stress_coloured else set())
    extra_attributes = {}
    if not static:
        for spec in analysis.fields:
            if spec.attribute not in written and spec.name in result.fields:
                extra_attributes[spec.attribute] = result.fields[spec.name]
    frames = []
    if result.series is not None:
        for index, frame in enumerate(result.series.frames):
            frames.append({
                attribute: result.frame_fields[name][index]
                for name, attribute in frame.attributes.items()
                if name in result.frame_fields and attribute not in written and attribute not in extra_attributes
            })
    deformation = result.deformation if result.deformation is not None else np.zeros_like(result.dof_locations)
    by_part = result.fields_by_part.get(primary.name) if primary.components == 1 else None
    surface = result.boundary_quadratic
    if (shown_faces := result.scalars.get("shown_faces")) is not None:
        # An analysis that shows some of the faces alone (the air closed inside a part: the faces it wets).
        keep = np.isin(np.asarray(volume.boundary_ordinal), np.asarray(shown_faces, dtype=np.int64))
        surface, face_of_triangle = surface[keep], face_of_triangle[keep]
        if plan is not None:
            part_of_triangle = part_of_triangle[keep]
    write_glb(
        glb_path,
        positions=result.dof_locations,
        displacement=deformation,
        values=colour,
        values_attribute="_VON_MISES" if stress_coloured else None,
        triangles6=surface,
        face_of_triangle=face_of_triangle,
        scale=scale if scale is not None else 1.0,
        value_range=tuple(ranges[primary.name][:2]),
        extras=extras,
        **({} if plan is None or by_part is None else {
            "values_by_part": by_part,
            "part_of_triangle": part_of_triangle,
        }),
        **({} if not extra_attributes else {"extra_attributes": extra_attributes}),
        **({} if not any(frames) else {"series": frames}),
    )
    if vtu_path is not None:
        vertex_count = result.vertices
        write_vtu(
            vtu_path,
            positions=result.dof_locations[:vertex_count],
            tets=result.tets,
            displacement=deformation[:vertex_count],
            values=colour[:vertex_count],
        )
    # Files an analysis writes beside the GLB (topology's design surface); it may add their names to its summary.
    extra_files = analysis.write_files(result, summary, glb_path) if hasattr(analysis, "write_files") else {}

    mesh_info = {
        "elements": int(len(volume.tets)),
        "nodes": int(len(volume.nodes)),
        "dofs": result.dofs,
        "size_mm": round(volume.max_h, 4),
        "order": fit_plan.order,
        "mesher": "netgen",
        "solver": result.solver,
    }
    timings = {"mesh_s": round(volume.seconds, 3), **{k: round(v, 3) for k, v in result.timings.items()}}
    fixtures = getattr(inputs, "fixtures", None)
    sidecar = {
        "generator": "cadgen fea",
        "document": str(document),
        "occurrence": occurrence_ref,
        **({} if static else {"analysis": analysis.name}),
        "study": parsed.source,
        **({} if material is None else {"material": material.as_dict()}),
        "faces": {ref: dataclasses.asdict(volume.faces[ordinal]) for ref, ordinal in ordinal_of.items()},
        "summary": summary,
        **({} if fixtures is None else {"fixtures": [
            {"faces": list(fixture.faces), "type": fixture.type,
             **({"reaction_N": [round(x, 4) for x in result.reactions[n]]} if n < len(result.reactions) else {})}
            for n, fixture in enumerate(fixtures)
        ]}),
        "fields": extras["fields"],
        "mesh": mesh_info,
        "timings": timings,
        "warnings": warnings,
        "findings": findings,
        # An assembly: how its parts are joined (the parts' own results are in the summary).
        **({} if plan is None else {"connections": _connections(plan, volume)}),
        # An assembly: the pairs of parts whose solids overlap (never bonded).
        **({} if plan is None else {"overlaps": [
            {"between": [name_of[o.a], name_of[o.b]], "refs": [o.a, o.b], "volume_mm3": round(o.volume_mm3, 4)}
            for o in plan.overlaps
        ]}),
        # The first and the finer solve's size and peak, when the part was solved twice.
        "refined": refined,
        "files": {"glb": glb_path.name, "vtu": vtu_path.name if vtu_path else None, **extra_files},
        **({} if parsed.view is None else {"view": parsed.view}),
        **({} if not fit_steps else {"fit": fit_steps}),
    }
    if not static:
        sidecar.update({
            "curves": result.curves,
            "series": None if result.series is None else _series_extras(result.series),
            "limits": list(analysis.limits),
            "estimate": bool(analysis.estimate_only),
            "upstream": {name: getattr(upstream, "scalars", {}).get("summary") for name, upstream in ctx.upstream.items()},
        })
    sidecar_path.write_text(json.dumps(sidecar, indent=2, allow_nan=False), encoding="utf-8")
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
        analysis=analysis.name,
        fit=tuple(fit_steps),
    )
