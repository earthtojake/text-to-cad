"""Part-vs-part interference checking.

Nothing else in the toolchain answers "do any two parts occupy the same space?".
``inspect refs`` reports per-shape facts and ``snapshot`` renders pictures, and
the documented workflow is to eyeball a transparent render and then "convert
visual concerns into measurements" -- which cannot establish the *absence* of a
clash, and misses anything hidden inside the assembly entirely.

This computes it directly: the boolean intersection volume of every candidate
pair of leaf occurrences (bodies).

The unit of the VERDICT is the part, not the body. A part is a direct component
of the selection's root — the document root by default, or the ref named with
``--refs`` (the common ancestor when several are named). A purchased servo is a
sub-assembly whose motor sits inside its case by construction; a weldment is
several solids in one product. Their bodies overlap and always will, and a
STEP document cannot say "these bodies are one purchased unit" — the vendor
sub-assembly and an authored one look identical in XCAF. So pairs INSIDE one
part are tested too, but reported separately (``intraPartOverlaps``) and never
fail the check; the clashes that drive the verdict are between DIFFERENT
parts. To test one part's bodies against each other, name that part alone.

Two things make an O(n^2) pairwise test tractable on a 1400-occurrence assembly:

* a world-space AABB reject runs first, and solids that do not overlap even as
  boxes never reach the (expensive) boolean;
* touching is not overlapping. Neighbouring panels share a face by design, and
  OCC returns hairline slivers for those, so a volume tolerance separates a real
  interpenetration from contact.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

# A shared face between two touching solids can yield a sliver of a few cubic
# millimetres. Real interpenetrations on parts of this size are orders larger.
DEFAULT_TOLERANCE_MM3 = 1.0

# Boxes are grown by this much before the overlap test so that solids which only
# touch still become candidates (and are then correctly rejected by volume),
# rather than being silently skipped by floating-point luck.
_BBOX_EPSILON = 1e-6


@dataclass(frozen=True)
class Occurrence:
    """One leaf occurrence: its selector id, label, solid, and world AABB."""

    ref: str
    name: str
    shape: Any
    bbox: tuple[float, float, float, float, float, float]


@dataclass(frozen=True)
class Clash:
    a_ref: str
    a_name: str
    b_ref: str
    b_name: str
    volume: float
    bbox: tuple[float, float, float, float, float, float]
    # The part both bodies belong to, when they belong to the same one; None
    # for a clash between two different parts (the kind that fails the check).
    part: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "a": {"ref": self.a_ref, "name": self.a_name},
            "b": {"ref": self.b_ref, "name": self.b_name},
            "volume": self.volume,
            "bounds": {
                "min": [self.bbox[0], self.bbox[1], self.bbox[2]],
                "max": [self.bbox[3], self.bbox[4], self.bbox[5]],
            },
        }


def _shape_bbox(shape: Any) -> tuple[float, float, float, float, float, float]:
    """A BROAD-PHASE box: loose is safe here (a box that overstates its body
    only proposes a pair the narrow phase then rejects) and this runs once per
    occurrence, so it stays the cheap control-polygon bound.
    ``useTriangulation=False``: triangulating here would mutate the shared
    TShape and break content-addressed component dedup elsewhere."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, False)
    if box.IsVoid():
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    return box.Get()


def _reported_bbox(shape: Any) -> tuple[float, float, float, float, float, float]:
    """The box of a clash as the REPORT states it -- where the overlap is, and
    therefore tight: a control-polygon bound would place a rounded clash up to
    8% outside itself (PR #370 bug record 004). One clash, one measurement."""
    from cadgen._internal.component_package import optimal_box

    box = optimal_box(shape)
    if box is None:
        return _shape_bbox(shape)
    return tuple(box)


def _boxes_overlap(a, b, epsilon: float = _BBOX_EPSILON) -> bool:
    return (
        a[0] - epsilon <= b[3]
        and b[0] - epsilon <= a[3]
        and a[1] - epsilon <= b[4]
        and b[1] - epsilon <= a[4]
        and a[2] - epsilon <= b[5]
        and b[2] - epsilon <= a[5]
    )


def _solid_volume(shape: Any) -> float:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props, False, False, True)
    return float(props.Mass())


def _intersection(a: Any, b: Any) -> Any | None:
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common

    algo = BRepAlgoAPI_Common(a, b)
    if not algo.IsDone():
        return None
    return algo.Shape()


def _occurrences_from_instance_tree(tree: dict) -> list[Occurrence]:
    """Placed leaf occurrences from a ``compound_from_instances`` occurrence tree.

    A generator built around ``compound_from_instances`` places instances at the
    OCCT level, so the in-memory scene's XCAF walk sees ONE childless leaf — a
    26-instance arm came back as a single occurrence, zero pairs were tested,
    and the check passed green. The explicit occurrence tree carries what the
    packager (and the on-disk STEP) use: leaf shapes plus accumulated world
    locations, in the same ``o1.N`` namespace ``inspect refs`` resolves.
    """
    from OCP.TopLoc import TopLoc_Location

    out: list[Occurrence] = []

    def walk(node: dict) -> None:
        if node.get("leaf"):
            shape_obj = node.get("shape")
            wrapped = getattr(shape_obj, "wrapped", shape_obj)
            if wrapped is None:
                return
            # world_loc already accumulates the prototype's own location
            # (instances._occurrence_subtree), so apply it to the UNLOCATED
            # shape — the same convention the packager's transform uses.
            placed = wrapped.Located(TopLoc_Location())
            world = node.get("world_loc")
            loc = world if isinstance(world, TopLoc_Location) else getattr(world, "wrapped", None)
            if loc is not None:
                placed = placed.Moved(loc)
            ref = str(node.get("id") or "")
            name = str(node.get("name") or ref)
            out.append(Occurrence(ref=ref, name=name, shape=placed, bbox=_shape_bbox(placed)))
            return
        for child in node.get("children") or []:
            walk(child)

    walk(tree)
    return out


def occurrences_from_scene(scene: Any) -> list[Occurrence]:
    """Flatten a LoadedStepScene into placed leaf occurrences."""
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS_Shape

    instance_tree = getattr(scene, "instance_occurrence_tree", None)
    if instance_tree is not None:
        return _occurrences_from_instance_tree(instance_tree)

    out: list[Occurrence] = []

    def walk(node: Any, path: tuple[int, ...]) -> None:
        children = list(getattr(node, "children", []) or [])
        if children:
            for index, child in enumerate(children, start=1):
                walk(child, path + (index,))
            return
        key = getattr(node, "prototype_key", None)
        if key is None:
            return
        prototype = scene.prototype_shapes.get(key)
        if prototype is None:
            return
        location = getattr(node, "location", None)
        shape: TopoDS_Shape = prototype
        if location is not None:
            loc = location if isinstance(location, TopLoc_Location) else getattr(location, "wrapped", None)
            if loc is not None:
                shape = prototype.Moved(loc)
        ref = "o" + ".".join(str(part) for part in path)
        name = str(getattr(node, "name", None) or getattr(node, "source_name", None) or ref)
        out.append(Occurrence(ref=ref, name=name, shape=shape, bbox=_shape_bbox(shape)))

    for root_index, root in enumerate(scene.roots, start=1):
        walk(root, (root_index,))
    return out


def scene_label_rows(scene: Any) -> list[dict[str, str]]:
    """``{id, name}`` for EVERY node in the scene, groups included.

    ``occurrences_from_scene`` returns only leaves, because only leaves carry a solid to test.
    Label resolution needs more than that: a subassembly label like ``damper_body`` resolves
    fine through the selector index (``snapshot --focus``, ``inspect refs``), so it has to
    resolve here too or the same ref works on four CLIs and fails on two.
    """
    rows: list[dict[str, str]] = []

    instance_tree = getattr(scene, "instance_occurrence_tree", None)
    if instance_tree is not None:
        # Same tree the occurrence flatten uses — the two namespaces must
        # agree or a label resolves to a ref no occurrence carries.
        def walk_tree(node: dict) -> None:
            ref = str(node.get("id") or "")
            name = str(node.get("name") or "")
            if ref and name:
                rows.append({"id": ref, "name": name})
            for child in node.get("children") or []:
                walk_tree(child)

        walk_tree(instance_tree)
        return rows

    def walk(node: Any, path: tuple[int, ...]) -> None:
        ref = "o" + ".".join(str(part) for part in path)
        name = str(getattr(node, "name", None) or getattr(node, "source_name", None) or "")
        if name:
            rows.append({"id": ref, "name": name})
        for index, child in enumerate(list(getattr(node, "children", []) or []), start=1):
            walk(child, path + (index,))

    for root_index, root in enumerate(getattr(scene, "roots", []) or [], start=1):
        walk(root, (root_index,))
    return rows


def _strip_ref_file_prefix(ref: str, entry_target: str) -> str:
    """Drop a `<file>#` prefix that names this entry; raise when it names another.

    `validate --refs` and `interfere --refs` take refs a user may have copied from the viewer,
    which now carry a file prefix. Ignoring a foreign prefix would select nothing and report a
    clean run over zero occurrences -- the silent no-op this module's callers were already
    burned by once.
    """
    from cadgen.cad_ref_syntax import ensure_ref_file_matches

    text = str(ref).strip()
    if "#" not in text:
        return text.lstrip("#")
    prefix, _, remainder = text.partition("#")
    ensure_ref_file_matches(prefix, entry_target, source_label=f"ref {text!r}")
    return remainder.strip()


def _resolve_selection(
    occurrences: list[Occurrence],
    refs: Iterable[str] | None,
    *,
    label_rows: list[dict[str, str]] | None = None,
    entry_target: str = "",
) -> list[str]:
    """The requested refs as numeric occurrence refs (labels resolved, file
    prefixes checked and dropped). Empty when nothing was requested."""
    wanted = [
        stripped
        for stripped in (
            _strip_ref_file_prefix(ref, entry_target) for ref in (refs or []) if str(ref).strip()
        )
        if stripped
    ]
    if not wanted:
        return []
    # `validate` and `interfere` select against the build123d scene rather than the selector
    # index, so they need labels resolved here too. Without this a label ref matches nothing
    # and both report a clean run over zero occurrences -- a silent no-op, which is worse than
    # an error. An unknown or ambiguous label raises, and the CLIs turn that into ok:false.
    from cadgen.label_refs import build_label_aliases, resolve_label_selectors

    alias_map = build_label_aliases(
        label_rows
        if label_rows is not None
        else [{"id": occurrence.ref, "name": occurrence.name} for occurrence in occurrences]
    )
    return [str(resolved).lstrip("#") for resolved in resolve_label_selectors(wanted, alias_map)]


def _filter_selected(occurrences: list[Occurrence], wanted: list[str]) -> list[Occurrence]:
    if not wanted:
        return occurrences
    keep: list[Occurrence] = []
    for occurrence in occurrences:
        for ref in wanted:
            # prefix match, so `--refs o1.7` selects a whole subassembly
            if occurrence.ref == ref or occurrence.ref.startswith(f"{ref}."):
                keep.append(occurrence)
                break
    return keep


def _selected(
    occurrences: list[Occurrence],
    refs: Iterable[str] | None,
    *,
    label_rows: list[dict[str, str]] | None = None,
    entry_target: str = "",
) -> list[Occurrence]:
    return _filter_selected(
        occurrences,
        _resolve_selection(occurrences, refs, label_rows=label_rows, entry_target=entry_target),
    )


def selection_root(wanted: list[str], occurrences: list[Occurrence]) -> str:
    """The node whose direct components are the PARTS of this check.

    Nothing named: the document root (``o1``), or ``""`` when the document has
    several roots (each root is then a part). Refs named: their deepest common
    ancestor — one ref IS the root, so ``--refs o1.7`` tests the components of
    ``o1.7`` against each other, while ``--refs o1.3,o1.9`` tests the two named
    parts as wholes.
    """
    if not wanted:
        tops = sorted({occurrence.ref.split(".")[0] for occurrence in occurrences})
        return tops[0] if len(tops) == 1 else ""
    segments = [ref.split(".") for ref in wanted]
    common: list[str] = []
    for column in zip(*segments):
        if any(segment != column[0] for segment in column):
            break
        common.append(column[0])
    return ".".join(common)


def part_of(ref: str, root: str) -> str:
    """The part ``ref`` belongs to: the direct component of ``root`` above it
    (``ref`` itself when it IS that component, or lies outside ``root``)."""
    if not root:
        return ref.split(".")[0]
    if ref == root or not ref.startswith(f"{root}."):
        return ref
    return f"{root}.{ref[len(root) + 1:].split('.')[0]}"


def part_assignments(occurrences: list[Occurrence], root: str) -> dict[str, str]:
    """``{body ref: part ref}`` for every occurrence, relative to ``root``."""
    return {occurrence.ref: part_of(occurrence.ref, root) for occurrence in occurrences}


def find_clashes(
    occurrences: list[Occurrence],
    *,
    tolerance: float = DEFAULT_TOLERANCE_MM3,
    max_pairs: int | None = None,
    parts: dict[str, str] | None = None,
) -> tuple[list[Clash], dict[str, int]]:
    """Pairwise interference over already-placed occurrences.

    Returns the overlaps plus counters, so a caller can tell "nothing overlapped"
    apart from "we never actually tested anything". ``parts`` maps each body's
    ref to its part (see :func:`part_assignments`); an overlap between two
    bodies of one part comes back with ``Clash.part`` set so the caller can
    keep it off the verdict. Without ``parts`` every body is its own part.
    Cross-part pairs are tested FIRST, so a ``max_pairs`` budget is spent on
    the pairs that can fail the check before the ones that cannot.
    """
    clashes: list[Clash] = []
    part_map = parts or {}

    def part_ref(occurrence: Occurrence) -> str:
        return part_map.get(occurrence.ref, occurrence.ref)

    stats = {
        "occurrences": len(occurrences),
        "parts": len({part_ref(occurrence) for occurrence in occurrences}),
        "pairs_total": 0,
        "pairs_intra_part": 0,
        "pairs_tested": 0,
        "pairs_skipped_bbox": 0,
        "pairs_truncated": 0,
    }
    count = len(occurrences)
    cross_pairs: list[tuple[Occurrence, Occurrence, str | None]] = []
    intra_pairs: list[tuple[Occurrence, Occurrence, str | None]] = []
    for i in range(count):
        first = occurrences[i]
        for j in range(i + 1, count):
            second = occurrences[j]
            stats["pairs_total"] += 1
            shared = part_ref(first) if part_ref(first) == part_ref(second) else None
            if shared is None:
                cross_pairs.append((first, second, None))
            else:
                stats["pairs_intra_part"] += 1
                intra_pairs.append((first, second, shared))
    for first, second, shared in (*cross_pairs, *intra_pairs):
        if not _boxes_overlap(first.bbox, second.bbox):
            stats["pairs_skipped_bbox"] += 1
            continue
        if max_pairs is not None and stats["pairs_tested"] >= max_pairs:
            stats["pairs_truncated"] += 1
            continue
        stats["pairs_tested"] += 1
        common = _intersection(first.shape, second.shape)
        if common is None:
            continue
        try:
            volume = abs(_solid_volume(common))
        except Exception:  # noqa: BLE001 - a degenerate common shape is not a clash
            continue
        if volume > tolerance:
            clashes.append(
                Clash(
                    a_ref=first.ref,
                    a_name=first.name,
                    b_ref=second.ref,
                    b_name=second.name,
                    volume=volume,
                    bbox=_reported_bbox(common),
                    part=shared,
                )
            )
    clashes.sort(key=lambda clash: clash.volume, reverse=True)
    return clashes, stats


def inspect_interference(
    entry: str,
    *,
    refs: Iterable[str] | None = None,
    tolerance: float = DEFAULT_TOLERANCE_MM3,
    max_pairs: int | None = None,
) -> dict[str, object]:
    """Public entry point used by ``inspect interfere``."""
    from cadgen.cli_logging import CliLogger
    from cadgen.step_export_target import _resolve_spec_and_scene
    from cadgen.step_targets import resolve_step_target

    target = resolve_step_target(entry)
    logger = CliLogger("cad")
    repo_root = Path.cwd()
    source_path = target.source_path if str(target.source_path).endswith(".py") else None
    scene = _resolve_spec_and_scene(
        repo_root,
        target.step_path,
        source_path,
        mesh_tolerance=None,
        mesh_angular_tolerance=None,
        logger=logger,
        door="inspect interfere",
        verb="checking interference",
    ).scene

    all_occurrences = occurrences_from_scene(scene)
    label_rows = scene_label_rows(scene)
    names = {row["id"]: row["name"] for row in label_rows}
    wanted = _resolve_selection(all_occurrences, refs, label_rows=label_rows, entry_target=str(entry))
    occurrences = _filter_selected(all_occurrences, wanted)
    root = selection_root(wanted, occurrences)
    parts = part_assignments(occurrences, root)
    clashes, stats = find_clashes(
        occurrences, tolerance=tolerance, max_pairs=max_pairs, parts=parts
    )
    # A part's own bodies overlapping is the part's own business (a motor
    # modelled inside its case); only a clash between two DIFFERENT parts fails
    # the check. Intra-part overlaps are still reported, separately.
    cross_part = [clash for clash in clashes if clash.part is None]
    intra_part = [clash for clash in clashes if clash.part is not None]
    bodies_per_part: dict[str, int] = {}
    for part in parts.values():
        bodies_per_part[part] = bodies_per_part.get(part, 0) + 1
    # Zero pairs is not a pass: it means nothing was compared. Fewer than two
    # occurrences leaves no pair to test, so the result is INCONCLUSIVE — a
    # safety check must not render "we tested nothing" in the same green as
    # "we tested everything and found nothing". `ok` goes false so callers
    # (and exit codes) cannot mistake the two. One PART is the same story at
    # the level the verdict is drawn: every pair is intra-part, none can fail.
    inconclusive_reason: str | None = None
    if len(occurrences) < 2:
        if refs and len(occurrences) < len(all_occurrences):
            inconclusive_reason = (
                f"--refs selected {len(occurrences)} of {len(all_occurrences)} occurrence(s); "
                "at least two are needed to test a pair"
            )
        else:
            inconclusive_reason = (
                f"the document presents {len(occurrences)} leaf occurrence(s); "
                "at least two are needed to test a pair"
            )
    elif len(bodies_per_part) < 2:
        (only_part,) = bodies_per_part
        inconclusive_reason = (
            f"all {len(occurrences)} bodies belong to one part ({only_part}); interfere tests "
            f"parts against each other — pass --refs {only_part} to test its components "
            "against one another"
        )
    return {
        "ok": not cross_part and inconclusive_reason is None,
        "entry": target.cad_path,
        "tolerance": tolerance,
        "root": {"ref": root, "name": names.get(root, "")},
        "parts": [
            {"ref": part, "name": names.get(part, part), "bodies": bodies}
            for part, bodies in sorted(bodies_per_part.items(), key=lambda item: _ref_sort_key(item[0]))
        ],
        "stats": stats,
        "conclusive": inconclusive_reason is None,
        **({"inconclusiveReason": inconclusive_reason} if inconclusive_reason else {}),
        "clashCount": len(cross_part),
        "clashes": [clash.as_dict() for clash in cross_part],
        "intraPartOverlapCount": len(intra_part),
        "intraPartOverlaps": [
            {**clash.as_dict(), "part": {"ref": clash.part, "name": names.get(clash.part, clash.part)}}
            for clash in intra_part
        ],
        "errors": [],
    }


def _ref_sort_key(ref: str) -> tuple:
    return tuple(int(part) if part.isdigit() else part for part in ref.lstrip("o").split("."))
