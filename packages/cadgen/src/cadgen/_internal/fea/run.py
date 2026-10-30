"""What the ``cadgen.fea`` verbs do, end to end."""

from __future__ import annotations

import dataclasses
import math
import os
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from cadgen._internal.atomic_replace import replace_atomic, temp_suffix
from cadgen._internal.fea.checks import finding, quoted
from cadgen.results import FeaFace, FeaFacesResult, FeaPair, FeaPart, FeaPartsResult, FeaResult

if TYPE_CHECKING:
    from cadgen._internal.fea.document import Document, Occurrence, Selection

__all__ = ["list_assembly_parts", "list_faces", "progress_log", "solve_study"]

_AXES = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}


@dataclasses.dataclass
class Narration:
    """What a verb says on stderr as it works (``[fea] ...``), never on stdout, where its result is: ``info``
    always, ``debug`` with ``verbose``."""

    verbose: bool = False

    def info(self, message: str) -> None:
        print(f"[fea] {message}", file=sys.stderr)

    def debug(self, message: str) -> None:
        if self.verbose:
            self.info(message)


def _open(target: Path) -> "Document":
    from cadgen._internal.fea.document import read_document

    return read_document(target)


def _resolve_one(document: "Document", ref: str) -> "Selection":
    """The one face or part ``ref`` names. A study names one per entry: a line the viewer copies with
    several (``bracket/face 1,face 2``) is refused with the entries to write instead."""
    found = document.resolve(ref)
    if len(found) != 1:
        entries = ", ".join(f'"{selection.ref}"' for selection in found)
        raise ValueError(f"{ref} names {len(found)} references; give each its own entry in the study's list: {entries}")
    return found[0]


def _resolve_faces(document: "Document", refs: "tuple[str, ...]") -> tuple[dict[str, "Selection"], set[str]]:
    """Each face ref resolved, and the occurrences they belong to."""
    resolved: dict[str, Selection] = {}
    owners: set[str] = set()
    for ref in refs:
        selection = _resolve_one(document, ref)
        if selection.kind != "face":
            raise ValueError(f"{ref} names a part; fixtures, loads and checks take faces ({selection.ref}/face 17)")
        resolved[ref] = selection
        owners.add(selection.occurrence_ref)
    return resolved, owners


def _refuse_held_loads(study, resolved: dict[str, "Selection"]) -> None:
    """A load on a face a ``fixed`` fixture holds goes straight into the support, as does a pressure on a ``roller`` face
    (along its normal, the one way a roller holds): none of it reaches the part, so the study is refused, whichever way
    each names the face."""
    held: dict[str, tuple[int, str]] = {}  # each held face's canonical ref: the fixture holding it, a fixed one first
    for index, fixture in sorted(enumerate(study.fixtures), key=lambda item: item[1].type != "fixed"):
        for ref in fixture.faces:
            held.setdefault(resolved[ref].ref, (index, fixture.type))
    for index, load in enumerate(study.loads):
        for ref in load.faces:
            fixture, kind = held.get(resolved[ref].ref, (None, None))
            if kind == "fixed" or (kind == "roller" and load.type == "pressure"):
                how = "holds it still" if kind == "fixed" else "holds it along its normal, which a pressure pushes along"
                raise ValueError(
                    f"loads[{index}]: {ref} is held by fixtures[{fixture}] ({kind}), which {how}, so the load goes into the "
                    "support and never reaches the part; load a face that is not held"
                )


def _single_occurrence(document: "Document", owners: set[str]) -> "Occurrence":
    """The one part occurrence every face ref belongs to (a study always names faces: its fixtures)."""
    if len(owners) > 1:
        raise ValueError(
            f"the study's faces span {len(owners)} occurrences ({', '.join(sorted(owners))}); "
            "a study solves one part, so every face must be on the same occurrence"
        )
    chosen = next(iter(owners))
    return next(leaf for leaf in document.leaves() if leaf.ref == chosen)


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

    logger = Narration(verbose=verbose)
    document = _open(Path(target))
    if occurrence:
        owner = _resolve_one(document, occurrence)
        if owner.kind != "occurrence":
            raise ValueError(f"{occurrence} names a face, not a part")
    else:
        leaves = document.leaves()
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


def _detect_pairs(parts: list, tolerance: float, reach: float, logger: Narration) -> tuple[list, list, int]:
    """The pairs within ``reach`` and the interferences within ``tolerance``, in part order; the overlaps; how many
    pairs are within ``reach``."""
    from cadgen._internal.fea.assembly import detect_contacts, detect_overlaps, interferences

    shared = detect_overlaps(parts, log=logger.info)
    # An overlap no thicker than the tolerance is an interference: contact, bonded like a gap.
    pressed, overlaps = interferences(shared, tolerance)
    logger.info(f"found {len(overlaps)} overlapping pairs" + (f" and {len(pressed)} interferences within the tolerance" if pressed else ""))
    found = detect_contacts(parts, reach, skip={frozenset((o.a, o.b)) for o in shared}, log=logger.info)
    order = {part.ref: i for i, part in enumerate(parts)}
    return sorted(found + pressed, key=lambda c: sorted((order[c.a], order[c.b]))), overlaps, len(found)


def list_assembly_parts(target: Path, *, verbose: bool = False) -> FeaPartsResult:
    """The parts and the pairs that touch within the default tolerance a study bonds by; a study that bonds wider gaps
    sets its own (``contact_tolerance_mm``), and the gaps listed are what it decides by."""
    # Contact detection is OCP, numpy and scipy: no solver needed.
    from cadgen._internal.fea.assembly import display_names, list_parts
    from cadgen._internal.fea.study import CONTACT_TOLERANCE_MM as contact_tolerance_mm

    logger = Narration(verbose=verbose)
    logger.info("reading the parts")
    parts = list_parts(_open(Path(target)))
    logger.info(f"read {len(parts)} parts; looking for pairs within {max(contact_tolerance_mm, _NEAR_MISS_MM)} mm")
    name = dict(zip((part.ref for part in parts), display_names(parts)))
    found, overlaps, near = _detect_pairs(parts, contact_tolerance_mm, max(contact_tolerance_mm, _NEAR_MISS_MM), logger)
    logger.info(f"found {near} touching or near pairs")
    pairs = [
        FeaPair(between=(name[c.a], name[c.b]), refs=(c.a, c.b), area_mm2=round(c.area_mm2, 4), gap_mm=round(c.gap_mm, 6),
                type="bonded" if c.gap_mm <= contact_tolerance_mm * (1 + 1e-6) else "not_connected",
                interference_mm=round(c.interference_mm, 6))
        for c in found
    ] + [
        FeaPair(between=(name[o.a], name[o.b]), refs=(o.a, o.b), area_mm2=0.0, gap_mm=0.0, type="overlapping",
                overlap_mm3=round(o.volume_mm3, 4))
        for o in overlaps
    ]
    return FeaPartsResult(
        ok=True, document=Path(target), contact_tolerance_mm=contact_tolerance_mm, pairs=tuple(pairs),
        parts=tuple(FeaPart(ref=p.ref, name=p.name, volume_mm3=round(p.volume_mm3, 4)) for p in parts),
    )


@dataclasses.dataclass
class _Plan:
    """What an assembly study asks for, once its parts and connections are resolved."""

    parts: list
    #: Per part, the occurrence's name (its ref when it has none).
    names: list[str]
    #: Per part, what it is solved with: the study's numbers for it, else the study's own material, else the model's.
    materials: list
    #: Every pair in contact within the tolerance, and the ones that get bonded.
    contacts: list
    bonded: list
    #: Every pair of parts whose solids overlap (never bonded), and the ones the study marks free.
    overlaps: list
    freed_overlaps: set
    #: Per part, the group of parts bonded to it (directly or through others).
    group_of: list[int]
    #: The document the parts are of: a part named by a ref other than its canonical one is resolved in it.
    document: "Document | None" = None


def find_part(parts: list, names: list[str], key: str, where: str, document: "Document | None" = None) -> int:
    """The part a study names by its ref or by its name; ``names`` are the display names, for the error. A ref
    other than the part's canonical one (``bar.2`` for ``kit/bar.2``) is resolved in ``document``."""
    for index, part in enumerate(parts):
        if key == part.ref:
            return index
    named = [index for index, part in enumerate(parts) if part.name == key]
    if len(named) > 1:
        raise ValueError(f"{where}: {key!r} names {len(named)} parts ({', '.join(parts[i].ref for i in named)}); use a ref")
    if not named and document is not None:
        try:
            found = document.resolve(key)
        except ValueError:
            found = ()
        refs = [selection.ref for selection in found if selection.kind == "occurrence"]
        if len(refs) == 1:
            for index, part in enumerate(parts):
                if part.ref == refs[0]:
                    return index
    if not named:
        raise ValueError(f"{where}: no part named {key!r}; the parts are {', '.join(quoted(name) for name in names)}")
    return named[0]


def _model_material(occurrence, name: str, parsed):
    """The model's own material of a part, as its document holds it (``materials.material_from_document``), with the
    density a body load needs."""
    from cadgen._internal.fea.materials import material_from_document

    material = material_from_document(occurrence._prototype().material, quoted(name))
    if any(load.body for load in parsed.loads) and not material.density > 0:
        raise ValueError(f"{quoted(name)}'s material {material.name} gives no density, which a gravity or acceleration "
                         "load needs; give the study its own material with density_t_per_mm3")
    return material


def _plan_assembly(doc: "Document", parsed, logger: Narration) -> _Plan:
    from cadgen._internal.fea.assembly import display_names, joined_groups, list_parts

    logger.info("reading the parts")
    parts = list_parts(doc)
    logger.info(f"read {len(parts)} parts; looking for contacts within {parsed.contact_tolerance_mm:g} mm")
    names = display_names(parts)
    index_of = {part.ref: i for i, part in enumerate(parts)}

    materials: list = [parsed.material] * len(parts)
    given: set[int] = set()
    for key, material in parsed.parts.items():
        index = find_part(parts, names, key, f"parts[{key!r}]", doc)
        if index in given:
            raise ValueError(f"parts[{key!r}]: {quoted(names[index])} is named twice in 'parts'")
        given.add(index)
        materials[index] = material
    leaves = doc.leaves()  # list_parts' order: part i is leaf i
    materials = [material if material is not None else _model_material(leaves[i], names[i], parsed)
                 for i, material in enumerate(materials)]

    contacts, overlaps, _ = _detect_pairs(parts, parsed.contact_tolerance_mm, parsed.contact_tolerance_mm, logger)
    logger.info(f"found {len(contacts)} touching pairs")
    overlap_of = {frozenset((index_of[o.a], index_of[o.b])): o for o in overlaps}
    pair_of = {frozenset((index_of[c.a], index_of[c.b])) for c in contacts}
    freed: set[frozenset[int]] = set()
    freed_overlaps: set[frozenset[int]] = set()
    seen: set[frozenset[int]] = set()
    for n, connection in enumerate(parsed.connections):
        where = f"connections[{n}]"
        i, j = (find_part(parts, names, key, f"{where}.between", doc) for key in connection.between)
        pair = frozenset((i, j))
        if i == j:
            raise ValueError(f"{where}.between: both names are {quoted(names[i])}")
        if pair in seen:
            raise ValueError(f"{where}: {quoted(names[i])} and {quoted(names[j])} are connected twice")
        seen.add(pair)
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
        if connection.type == "free" and pair in pair_of:
            freed.add(pair)
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
    return _Plan(parts, names, materials, contacts, bonded, overlaps, freed_overlaps, group_of, doc)


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


def _not_connected(plan: _Plan, unheld: list[list[int]], logger: Narration) -> list[dict]:
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
        found.append(finding(
            "error", "not_connected",
            f"{members} {'isn' if len(group) == 1 else 'aren'}'t connected to anything that is held{where}",
            "no chain of bonded parts joins it to a fixed face, so the solve was not run",
            [{"text": f"{quoted(plan.names[i])}", "ref": plan.parts[i].ref,
              "at": [round(c, 3) for c in part_centre(plan.parts[i])]} for i in group],
        ))
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
    """The detected pairs and what the study did with each, for the result.

    ``faces`` are the interface faces on both sides of a bonded joint, as the
    GLB's ``faces`` name them; a free pair has none.
    """
    name_of = {part.ref: plan.names[i] for i, part in enumerate(plan.parts)}
    index_of = {part.ref: i for i, part in enumerate(plan.parts)}
    # Faces in the mesh's order: part by part, each part's by ordinal.
    order = {fp.ref: position for position, fp in volume.faces.items()}
    bonded = {(c.a, c.b) for c in plan.bonded}
    return [
        {
            "between": [name_of[c.a], name_of[c.b]],
            "refs": [c.a, c.b],
            "type": "bonded" if (c.a, c.b) in bonded else "free",
            "area_mm2": round(c.area_mm2, 4),
            "gap_mm": round(c.gap_mm, 6),
            "interference_mm": round(c.interference_mm, 6),
            "faces": sorted(volume.joint_faces.get(tuple(sorted((index_of[c.a], index_of[c.b]))), ()), key=order.__getitem__),
        }
        for c in plan.contacts
    ]


class _NotConnected(Exception):
    """The mesh left parts apart from every fixed face; ``groups`` are the parts, each as its own group."""

    def __init__(self, groups: list[list[int]]):
        super().__init__("parts not connected to a fixed face")
        self.groups = groups


def _unsolved(document: Path, occurrence_ref: str, findings: list[dict]) -> FeaResult:
    """The result of a study that was stopped before the solve, by errors a person fixes in the study."""
    return FeaResult(ok=False, document=document, occurrence=occurrence_ref, glb=None, findings=tuple(findings))


def _mesh_assembly(mesh_assembly, doc, plan: _Plan, parsed, resolved, ordinal_of: dict[str, int], max_h: float | None, log, refine: float = 1.0, **mesh_options):
    """The glued, meshed assembly with its faces numbered by position, and the study's checks on it.

    Raises ``ValueError`` for a fixture or load on a face that is wholly a bonded joint, and :class:`_NotConnected`
    when the glue left a part apart from every fixed face.
    """
    volume = mesh_assembly(doc, [part.ref for part in plan.parts], plan.bonded, parsed.contact_tolerance_mm, max_h, log, refine=refine, **mesh_options)
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
    held = {ordinal_of[ref] for ref in parsed.fixed_refs}
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

    The DOF count grows with the cube of the size ratio (the mesher refines curved features by the same ratio, so they
    grow too), so the budget is spent from the first solve's: under ``DOF_WARN`` when that leaves a meaningfully finer
    mesh, otherwise under ``DOF_LIMIT`` (with a tenth of headroom for the estimate's error). ``None`` when even that
    leaves none.
    """
    from cadgen._internal.fea.solve import DOF_LIMIT, DOF_WARN

    for budget in (DOF_WARN, 0.9 * DOF_LIMIT):
        ratio = min(2.0, (budget / dofs) ** (1 / 3))
        if ratio >= 1.1:
            return size_mm / ratio
    return None


#: The fields a result carries, for the viewer's field switch: its GLB attribute, name, units, the summary's
#: maximum, and the scale that turns the stored value into those units (a vector is stored in glTF metres).
FIELDS = (
    ("_VON_MISES", "von Mises stress", "MPa", "max_von_mises_MPa", 1.0),
    ("_DISPLACEMENT", "displacement", "mm", "max_displacement_mm", 1000.0),
)


#: A long solve says how far it has got at most this often, seconds (the CLI prints it without --verbose too).
PROGRESS_S = 10.0


def progress_log(logger: Narration):
    """What the solver's log (and the meshing lines) print: with --verbose every line; without, a line only once
    nine tenths of :data:`PROGRESS_S` have passed since the last one printed (the run's start the first), so a
    long solve says how far it has got about every ten seconds and a short one stays quiet."""
    if logger.verbose:
        return logger.debug
    import time

    said = [time.perf_counter()]

    def log(message: str) -> None:
        now = time.perf_counter()
        if now - said[0] >= 0.9 * PROGRESS_S:
            said[0] = now
            logger.info(message)

    return log


def solve_study(target: Path, out: Path, *, study, vtu: bool = False, verbose: bool = False) -> FeaResult:
    """Mesh, solve and check one study, then write its GLB at ``out`` (and, with ``vtu``, a VTU beside it); every
    number the result reports is in the :class:`FeaResult` returned, and no other file is written.

    The physics is :mod:`.static`'s: its solve, checks and summary; this is the orchestration.

    When the safety factor is close to failing (:func:`checks.needs_finer`)
    the part is meshed again at half the element size (:func:`finer_mesh_size` keeps that under the DOF budget),
    finer by the same ratio at curved features, and solved again. When that succeeds its numbers are the ones
    written, reported and checked (the first solve's peak is kept for convergence only); when it fails the GLB
    stays the first solve's and the result carries one warning saying why.
    """
    return _solve_study(Path(target), Path(out), study, vtu, verbose)


def _solve_study(document: Path, glb_path: Path, study, vtu: bool, verbose: bool) -> FeaResult:
    from cadgen._internal.fea.study import parse_study

    parsed = parse_study(study)  # stdlib, before any heavy import
    logger = Narration(verbose=verbose)
    progress = progress_log(logger)
    if glb_path.suffix.lower() != ".glb":
        raise ValueError(f"OUT names the result GLB and must end in .glb: {glb_path}")
    vtu_path = glb_path.with_suffix(".vtu") if vtu else None

    from cadgen._internal.fea import checks
    from cadgen._internal.fea.mesh import mesh_assembly, mesh_occurrence, require_fea_stack, small_feature_mm

    require_fea_stack()
    doc = _open(document)
    resolved, owners = _resolve_faces(doc, tuple(dict.fromkeys((*parsed.face_refs, *parsed.check_faces))))
    _refuse_held_loads(parsed, resolved)
    # A document of several parts is an assembly, whichever faces the study names; one part's study keeps the one-part path.
    plan = None
    if len(doc.leaves()) > 1 or parsed.parts or parsed.connections:
        plan = _plan_assembly(doc, parsed, logger)
    ordinal_of: dict[str, int] = {}
    if plan is None:
        occurrence = _single_occurrence(doc, owners)
        occurrence_ref = occurrence.ref
        if parsed.material is None:
            parsed = dataclasses.replace(parsed, material=_model_material(occurrence, occurrence.label or occurrence.ref,
                                                                          parsed))
        ordinal_of.update({ref: int(selection.ordinal) for ref, selection in resolved.items()})
    else:
        occurrence_ref = doc.name
        part_index = {part.ref: i for i, part in enumerate(plan.parts)}
        held = {part_index[resolved[ref].occurrence_ref] for ref in parsed.fixed_refs}
        if unheld := _unheld_groups(plan, held):
            return _unsolved(document, occurrence_ref, _not_connected(plan, unheld, logger))

    import numpy as np

    from cadgen._internal.fea import solve, static
    from cadgen._internal.fea.outputs import RAMP, auto_deformation_scale, write_glb, write_vtu
    from cadgen._internal.fea.study import refine_points

    requested = parsed.mesh_size

    def mesh(max_h: float | None, refine: float = 1.0, size_field: dict | None = None):
        options: dict = {"size_field": size_field} if size_field else {}
        progress(f"meshing {occurrence_ref}")
        if plan is None:
            volume = mesh_occurrence(occurrence, max_h=max_h, refine=refine, **options)
        else:
            volume = _mesh_assembly(mesh_assembly, doc, plan, parsed, resolved, ordinal_of, max_h, logger.info, refine, **options)
        progress(f"meshed: {len(volume.tets)} tets ({volume.straightened} straightened), {len(volume.nodes)} nodes, "
                 f"size {volume.max_h:.3g} mm in {volume.seconds:.1f}s")
        return volume

    def solve_on(volume, automatic: bool = False):
        return static.solve(volume, parsed, plan, ordinal_of, part_name=document.stem, log=progress, automatic=automatic)

    # The study's own finer balls (mesh.refine), kept through every pass.
    study_points = refine_points(parsed.mesh_refine)
    study_field = {"points": study_points, "radius_mm": 0.0} if study_points else None
    try:
        volume = mesh(requested, size_field=study_field)
        result = solve_on(volume)
    except _NotConnected as exc:
        return _unsolved(document, occurrence_ref, _not_connected(plan, exc.groups, logger))
    finer_failure = None
    finer_size = None
    finer_written = False
    refined = None
    if checks.needs_finer(checks.safety_factor(static.weakest(result))):
        finer_size = finer_mesh_size(volume.max_h, result.outcome.dofs)
        if finer_size is None:
            finer_failure = (
                f"the part's {result.outcome.dofs:,} degrees of freedom at {volume.max_h:g} mm leave no room under the "
                f"{solve.DOF_LIMIT:,} limit for a finer solve; its convergence is unchecked"
            )
    if finer_size is not None:
        refined = static.refined_record(result, volume.max_h, finer_size, assembly=plan is not None)
        logger.debug(f"close to the limit: solving again at {finer_size:.3g} mm")
        try:
            first, first_small = result, small_feature_mm(volume)
            # Finer at fillets and holes too, by the same ratio: there the curvature, not the size, sets the mesh.
            finer_volume = mesh(finer_size, volume.max_h / finer_size, size_field=study_field)
            finer_result = solve_on(finer_volume, automatic=True)
        except RuntimeError as exc:  # the mesher or CalculiX failed: a second opinion, so the first answer stands
            # without it. Anything else is a fault of cadgen's, and fails the solve as the first one would.
            finer_failure = (
                f"the finer solve at {refined['size_mm']:g} mm failed ({exc}); "
                "the result is the first solve's, and its convergence is unchecked"
            )
        else:
            # The checks describe the solve that is written, so every number a
            # finding quotes and every point it names is on the GLB shown.
            volume = finer_volume
            result = static.merge_finer(first, finer_result, refined)
            finer_written = True
            if first.outcome.dofs > solve.DOF_WARN:  # the person's own size was already large
                result.outcome.warnings.insert(0, solve.dof_warning(first.outcome.dofs, automatic=False, small_feature_mm=first_small))
    outcome = result.outcome

    # Each check of the study judged on the written solve, in the study's order.
    check_results = [static.judge(check, index, volume, ordinal_of, result) for index, check in enumerate(parsed.checks)]
    findings = checks.findings(static.weakest(result)) if plan is None else checks.assembly_findings(result.solved)
    if plan is not None:
        name_of = {part.ref: plan.names[i] for i, part in enumerate(plan.parts)}
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

    if check_found := checks.check_findings(check_results, assembly=plan is not None):
        findings = sorted(findings + check_found, key=lambda finding: finding["severity"] != "error")
    material = parsed.material
    magnitude = np.linalg.norm(outcome.displacement, axis=1)
    scale = parsed.deformation_scale if parsed.deformation_scale is not None else auto_deformation_scale(
        float(magnitude.max()), volume.bbox_diagonal)
    # The summary is the one place the numbers are rounded; everything else
    # (the GLB's extras, the result) is derived from it.
    summary = static.summary(result, check_results, scale=scale,
                             part_refs=None if plan is None else [part.ref for part in plan.parts])

    warnings = list(outcome.warnings)
    if finer_failure:
        warnings.append(finer_failure)

    fields = [{"attribute": attribute, "name": name, "units": units, "min": 0.0, "max": summary[peak], "attribute_scale": factor}
              for attribute, name, units, peak, factor in FIELDS]
    extras = {
        "name": f"{document.stem} von Mises",
        "generator": "cadgen fea",
        # Where the STEP is from the GLB's own folder, so a viewer can find it.
        "document": _document_ref(document, glb_path),
        "occurrence": occurrence_ref,
        "deformation_scale": scale,
        # The summary's safety factor, for the viewer's plain line.
        "safety_factor": summary["safety_factor"],
        # One entry per raw attribute the GLB carries, for a viewer's field switch.
        "fields": fields,
        "ramp": [[stop, list(colour)] for stop, colour in RAMP],
        # What an engineer would say about the result (checks.py), errors first.
        "findings": findings,
        # Each check judged (`kind`, `label`, `value`, `limit`, `unit`, `ratio`, `close_at`, `status`, `where`): the verdict's.
        "checks": check_results,
    }
    if plan is not None:
        # What the viewer reads for an assembly (`_PART` indexes `parts`): the weakest part's line.
        extras.update({
            "weakest_part": summary["weakest_part"],
            "weakest_part_peak_MPa": summary["weakest_part_peak_MPa"],
            "max_displacement_mm": summary["max_displacement_mm"],
            "parts": [
                {key: part[key] for key in ("ref", "name", "material", "yield_MPa", "peak_MPa", "safety_factor", "max_displacement_mm")}
                for part in summary["parts"]
            ],
        })
        connections = _connections(plan, volume)
        extras["connections"] = [
            {"between": c["refs"], "names": c["between"], "type": c["type"], "area_mm2": c["area_mm2"],
             "gap_mm": c["gap_mm"], "faces": c["faces"]}
            for c in connections
        ]
    # Every boundary face of the occurrence in ordinal order; `_FACE` indexes it.
    face_ordinals = sorted(volume.faces)
    face_index = {ordinal: index for index, ordinal in enumerate(face_ordinals)}
    face_of_triangle = np.array([face_index.get(int(o), -1) for o in volume.boundary_ordinal], dtype=np.int64)

    if plan is not None:
        # Each surface triangle's part: a face is one part's.
        part_of_ref = {ref: i for i, part in enumerate(plan.parts) for ref in part.face_refs}
        owner = {position: part_of_ref[fp.ref] for position, fp in volume.faces.items()}
        part_of_triangle = np.array([owner[int(o)] for o in volume.boundary_ordinal], dtype=np.int64)

    def bare(refs):  # the canonical refs, whatever form the study named them in
        return [volume.faces[ordinal_of[ref]].ref for ref in refs]

    extras["faces"] = [volume.faces[ordinal].ref for ordinal in face_ordinals]
    extras["study"] = {
        "material": None if material is None else {"name": material.name, "yield_MPa": material.yield_strength,
                                                    "youngs_GPa": round(material.E / 1000.0, 6), "poisson": material.nu},
        **static.study_echo(parsed, bare),
        "mesh": {"size_mm": round(volume.max_h, 4), "order": 2, "elements": int(len(volume.tets)),
                 "straightened": volume.straightened, "refined_from_mm": refined["from_size_mm"] if finer_written else None},
        "margin": parsed.margin,
    }

    mesh_info = {"elements": int(len(volume.tets)), "straightened": volume.straightened, "nodes": int(len(volume.nodes)),
                 "dofs": outcome.dofs, "size_mm": round(volume.max_h, 4), "order": 2, "mesher": "netgen",
                 "solver": outcome.solver}
    timings = {"mesh_s": round(volume.seconds, 3), **{k: round(v, 3) for k, v in outcome.timings.items()}}
    # What the GLB's extras do not carry, for the result: the study as given, its material, each face it named,
    # each fixture's reaction, an assembly's joints and overlaps, and the first solve when there was a finer one.
    reported = {
        "study": parsed.source,
        # One part's material; an assembly's are each part's, in the summary's parts.
        "material": None if material is None else material.as_dict(),
        "faces": {ref: dataclasses.asdict(volume.faces[ordinal]) for ref, ordinal in ordinal_of.items()},
        "fixtures": tuple(
            {"faces": list(fixture.faces), "type": fixture.type,
             **({"reaction_N": [round(x, 4) for x in outcome.reactions[n]]} if n < len(outcome.reactions) else {})}
            for n, fixture in enumerate(parsed.fixtures)
        ),
        "connections": () if plan is None else tuple(connections),
        "overlaps": () if plan is None else tuple(
            {"between": [name_of[o.a], name_of[o.b]], "refs": [o.a, o.b], "volume_mm3": round(o.volume_mm3, 4)}
            for o in plan.overlaps
        ),
        "refined": refined,
    }
    # Von Mises colours the surface (each part's own stress in an assembly), deformed by the displacement.
    by_part = outcome.von_mises_parts
    # Each file is written beside its target under a temporary name and replaced into place once every one is written.
    # Each earlier file is kept under another name (a hard link, else a copy) until every rename is done, so a failure
    # anywhere puts every earlier file back byte for byte and leaves none this run wrote.
    suffix = temp_suffix()
    temporary = {path: path.with_name(f".{path.name}{suffix}") for path in (glb_path, vtu_path) if path is not None}
    kept = {path: path.with_name(f".{path.name}{suffix}.old") for path in temporary if path.exists()}
    placed: list[Path] = []
    try:
        write_glb(
            temporary[glb_path], positions=outcome.dof_locations, displacement=outcome.displacement, values=outcome.von_mises,
            triangles6=outcome.boundary_quadratic,
            face_of_triangle=face_of_triangle, scale=scale if scale is not None else 1.0,
            value_range=(0.0, summary["max_von_mises_MPa"]), extras=extras,
            **({} if plan is None or by_part is None else {"values_by_part": by_part, "part_of_triangle": part_of_triangle}),
        )
        if vtu_path is not None:
            vertex_count = outcome.vertices
            write_vtu(temporary[vtu_path], positions=outcome.dof_locations[:vertex_count], tets=outcome.tets,
                      displacement=outcome.displacement[:vertex_count], values=outcome.von_mises[:vertex_count])
        for path, old in kept.items():
            try:
                os.link(path, old)
            except OSError:
                shutil.copy2(path, old)
        for final, held in temporary.items():
            replace_atomic(held, final)
            placed.append(final)
    except BaseException:
        for final in placed:
            if final in kept:
                replace_atomic(kept[final], final)
            else:
                final.unlink(missing_ok=True)
        raise
    finally:
        for held in (*temporary.values(), *kept.values()):
            held.unlink(missing_ok=True)
    logger.debug(f"wrote {glb_path.name}" + (f", {vtu_path.name}" if vtu_path else ""))
    # ok is the validators' one rule: an error blocks. A part that yields, or misses a check, is a correct result of a
    # part unfit to use: its GLB is written, and the command exits 1 (README, "Finite element analysis").
    ok = not any(finding["severity"] == "error" for finding in findings)
    return FeaResult(ok=ok, document=document, occurrence=occurrence_ref, glb=glb_path, vtu=vtu_path,
                     summary=summary, mesh=mesh_info, timings=timings, warnings=tuple(warnings), findings=tuple(findings),
                     **reported)
