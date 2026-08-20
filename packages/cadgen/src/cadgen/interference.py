"""Part-vs-part interference checking.

Nothing else in the toolchain answers "do any two parts occupy the same space?".
``inspect refs`` reports per-shape facts and ``snapshot`` renders pictures, and
the documented workflow is to eyeball a transparent render and then "convert
visual concerns into measurements" -- which cannot establish the *absence* of a
clash, and misses anything hidden inside the assembly entirely.

This computes it directly: the boolean intersection volume of every candidate
pair of leaf occurrences.

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
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    # useTriangulation=False: triangulating here would mutate the shared TShape
    # and break content-addressed component dedup elsewhere.
    BRepBndLib.Add_s(shape, box, False)
    if box.IsVoid():
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    return box.Get()


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


def occurrences_from_scene(scene: Any) -> list[Occurrence]:
    """Flatten a LoadedStepScene into placed leaf occurrences."""
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS_Shape

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


def _selected(
    occurrences: list[Occurrence],
    refs: Iterable[str] | None,
    *,
    label_rows: list[dict[str, str]] | None = None,
    entry_target: str = "",
) -> list[Occurrence]:
    wanted = [
        stripped
        for stripped in (
            _strip_ref_file_prefix(ref, entry_target) for ref in (refs or []) if str(ref).strip()
        )
        if stripped
    ]
    if not wanted:
        return occurrences
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
    wanted = [str(resolved).lstrip("#") for resolved in resolve_label_selectors(wanted, alias_map)]
    keep: list[Occurrence] = []
    for occurrence in occurrences:
        for ref in wanted:
            # prefix match, so `--refs o1.7` selects a whole subassembly
            if occurrence.ref == ref or occurrence.ref.startswith(f"{ref}."):
                keep.append(occurrence)
                break
    return keep


def find_clashes(
    occurrences: list[Occurrence],
    *,
    tolerance: float = DEFAULT_TOLERANCE_MM3,
    max_pairs: int | None = None,
) -> tuple[list[Clash], dict[str, int]]:
    """Pairwise interference over already-placed occurrences.

    Returns the clashes plus counters, so a caller can tell "nothing overlapped"
    apart from "we never actually tested anything".
    """
    clashes: list[Clash] = []
    stats = {
        "occurrences": len(occurrences),
        "pairs_total": 0,
        "pairs_tested": 0,
        "pairs_skipped_bbox": 0,
        "pairs_truncated": 0,
    }
    count = len(occurrences)
    for i in range(count):
        first = occurrences[i]
        for j in range(i + 1, count):
            second = occurrences[j]
            stats["pairs_total"] += 1
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
                        bbox=_shape_bbox(common),
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
    _spec, scene = _resolve_spec_and_scene(
        repo_root,
        target.step_path,
        source_path,
        mesh_tolerance=None,
        mesh_angular_tolerance=None,
        logger=logger,
    )

    occurrences = _selected(
        occurrences_from_scene(scene), refs, label_rows=scene_label_rows(scene), entry_target=str(entry)
    )
    clashes, stats = find_clashes(occurrences, tolerance=tolerance, max_pairs=max_pairs)
    return {
        "ok": not clashes,
        "entry": target.cad_path,
        "tolerance": tolerance,
        "stats": stats,
        "clashCount": len(clashes),
        "clashes": [clash.as_dict() for clash in clashes],
        "errors": [],
    }
