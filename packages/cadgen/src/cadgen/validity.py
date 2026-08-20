"""Per-solid geometric validity checking.

Nothing else in the toolchain answers "is this solid actually sound?".
``inspect refs --facts`` reports counts and bounds and sets ``"ok"`` from
*ref-resolution* errors only, so a five-face open box and an inverted solid both
come back ``"ok": true``. ``inspect interfere`` answers a different question
(does part A overlap part B), which says nothing about a single body.

This checks each leaf occurrence directly:

* **topology** -- ``BRepCheck_Analyzer``;
* **closure** -- a shell with free (naked) edges is not watertight;
* **orientation** -- ``BRepCheck_Analyzer`` returns True for a reversed solid,
  so validity alone cannot catch a body that renders as a hole in the world.
  Only the sign of the volume can.

Two things this deliberately does *not* do:

* It never reads a compound's aggregate volume. An inverted member cancels
  against a good one and the defect disappears; every solid is measured
  individually.
* It never triangulates. ``UseTriangulation`` is left False so the shared
  TShape is not mutated, which would break content-addressed component dedup
  elsewhere.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

# A solid at or below this signed volume is reported. Zero is the meaningful
# threshold: negative means inverted, exactly zero means degenerate.
DEFAULT_MIN_VOLUME_MM3 = 0.0

REASON_INVALID_TOPOLOGY = "invalidTopology"
REASON_OPEN_SHELL = "openShell"
REASON_NON_POSITIVE_VOLUME = "nonPositiveVolume"
REASON_NO_SOLID = "noSolid"
REASON_SELF_INTERSECTING = "selfIntersecting"


def _solids(wrapped: Any) -> list[Any]:
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    out: list[Any] = []
    explorer = TopExp_Explorer(wrapped, TopAbs_ShapeEnum.TopAbs_SOLID)
    while explorer.More():
        out.append(TopoDS.Solid_s(explorer.Current()))
        explorer.Next()
    return out


def _shells(wrapped: Any) -> list[Any]:
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    out: list[Any] = []
    explorer = TopExp_Explorer(wrapped, TopAbs_ShapeEnum.TopAbs_SHELL)
    while explorer.More():
        out.append(TopoDS.Shell_s(explorer.Current()))
        explorer.Next()
    return out


def _signed_volume(solid: Any) -> float:
    """Signed volume of one solid.

    UseTriangulation is False so this reads the exact BRep and does not mutate
    the shared TShape. The sign is load-bearing -- do not wrap this in abs().
    """
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid, props, False, False, False)
    return float(props.Mass())


def _has_free_edges(shell: Any) -> bool:
    from OCP.ShapeAnalysis import ShapeAnalysis_Shell

    analyzer = ShapeAnalysis_Shell()
    analyzer.LoadShells(shell)
    # alsofree=True is required: it defaults to False, in which case free edges
    # are never collected and HasFreeEdges() is always False -- an open shell
    # would silently pass.
    analyzer.CheckOrientedShells(shell, True)
    return bool(analyzer.HasFreeEdges())


def _is_self_intersecting(wrapped: Any) -> bool | None:
    """True/False, or None when the checker could not run.

    None is distinct from False on purpose: "we did not establish this" must not
    be reported as "this passed".

    Keyed on the BOPAlgo_SelfIntersect status specifically, not on
    ``IsValid()``. ``IsValid()`` is False for several unrelated BOP faults
    (bad type, too-small edge, invalid curve-on-surface), so using it directly
    would report those as self-intersections.
    """
    try:
        from OCP.BOPAlgo import BOPAlgo_CheckStatus
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Check

        checker = BRepAlgoAPI_Check(wrapped, True, True)
        checker.Perform()
        if checker.IsValid():
            return False
        return any(
            result.GetCheckStatus() == BOPAlgo_CheckStatus.BOPAlgo_SelfIntersect
            for result in checker.Result()
        )
    except Exception:  # noqa: BLE001 - checker unavailable or failed to run
        return None


def check_occurrence_shape(
    wrapped: Any,
    *,
    allow_open: bool = False,
    min_volume: float = DEFAULT_MIN_VOLUME_MM3,
    check_self_intersection: bool = True,
) -> dict[str, object]:
    """Check one placed shape. Pure: no file IO, no scene loading.

    Returns ``{"solidCount", "volumes", "reasons"}``. ``reasons`` is empty when
    the shape is sound.
    """
    from OCP.BRepCheck import BRepCheck_Analyzer

    reasons: list[str] = []

    if not BRepCheck_Analyzer(wrapped, True).IsValid():
        reasons.append(REASON_INVALID_TOPOLOGY)

    solids = _solids(wrapped)
    volumes = [_signed_volume(solid) for solid in solids]

    if solids and any(volume <= min_volume for volume in volumes):
        # Measured per solid, never aggregated: an inverted member inside a
        # compound would otherwise cancel against a good one and vanish.
        reasons.append(REASON_NON_POSITIVE_VOLUME)

    if not allow_open:
        # `allow_open` means "surface geometry is intended here", so it
        # suppresses both the open-shell and the no-solid findings. Reporting
        # noSolid while honouring allow_open would make the flag useless.
        shells = _shells(wrapped)
        if shells and any(_has_free_edges(shell) for shell in shells):
            reasons.append(REASON_OPEN_SHELL)
        if not solids:
            reasons.append(REASON_NO_SOLID)

    if check_self_intersection and _is_self_intersecting(wrapped) is True:
        reasons.append(REASON_SELF_INTERSECTING)

    return {
        "solidCount": len(solids),
        "volumes": volumes,
        "reasons": reasons,
    }


def inspect_validity(
    entry: str,
    *,
    refs: Iterable[str] | None = None,
    allow_open: bool = False,
    min_volume: float = DEFAULT_MIN_VOLUME_MM3,
    check_self_intersection: bool = True,
) -> dict[str, object]:
    """Public entry point used by ``inspect validate``."""
    from cadgen.cli_logging import CliLogger
    from cadgen.interference import _selected, occurrences_from_scene, scene_label_rows
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

    parts: list[dict[str, object]] = []
    failures = 0
    for occurrence in occurrences:
        result = check_occurrence_shape(
            occurrence.shape,
            allow_open=allow_open,
            min_volume=min_volume,
            check_self_intersection=check_self_intersection,
        )
        reasons = result["reasons"]
        if reasons:
            failures += 1
            parts.append(
                {
                    "ref": occurrence.ref,
                    "name": occurrence.name,
                    "reasons": reasons,
                    "solidCount": result["solidCount"],
                    "volumes": result["volumes"],
                }
            )

    return {
        "ok": failures == 0,
        "entry": target.cad_path,
        "occurrenceCount": len(occurrences),
        "failureCount": failures,
        "parts": parts,
        "errors": [],
    }
