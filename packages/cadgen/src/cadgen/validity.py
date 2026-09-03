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

Scale is the other half of the design. An assembly places the same bolt a
hundred times, and every placed occurrence is ``prototype.Moved(location)`` --
one TShape, many locations. Topology, closure, solid presence and volume are
properties of the TShape, so they are checked ONCE per prototype and the
finding is reported against every occurrence that shares it. The
self-intersection test is different: ``BRepAlgoAPI_Check`` is numeric, and the
same bolt has been seen to self-intersect at 15 and 30 degrees of tilt and
pass at 45 and upright. By default it runs once per prototype, at the
prototype's FIRST placement, and the report says so; ``every_placement`` runs
it on every placed copy. Prototypes are checked across a spawn process pool
(the same shape as the component build), progress paints on stderr, and an
``out`` path receives the report as it accumulates so a killed run leaves a
readable partial document behind.
"""

from __future__ import annotations

import io
import json
import time
from dataclasses import dataclass, field
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

# How the self-intersection test was applied, as the report states it.
SELF_INTERSECTION_FIRST_PLACEMENT = "first-placement"
SELF_INTERSECTION_EVERY_PLACEMENT = "every-placement"
SELF_INTERSECTION_SKIPPED = "skipped"

# Worker-count override for the check pool; sized like the component build
# (``CADGEN_COMPONENT_WORKERS``) when unset.
WORKERS_ENV = "CADGEN_VALIDATE_WORKERS"


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


def check_placements(
    shapes: list[Any],
    *,
    allow_open: bool = False,
    min_volume: float = DEFAULT_MIN_VOLUME_MM3,
    check_self_intersection: bool = True,
) -> list[dict[str, object]]:
    """Check the placed copies of ONE prototype; one result per shape, in order.

    Topology, closure, solid presence and volume are properties of the shared
    TShape, so they are read once, off ``shapes[0]``, and repeated into every
    result. Only the self-intersection test -- the numeric one -- is re-run on
    each further placement. Callers pass one shape for the default mode and
    every placement for ``every_placement``.
    """
    first = check_occurrence_shape(
        shapes[0],
        allow_open=allow_open,
        min_volume=min_volume,
        check_self_intersection=check_self_intersection,
    )
    invariant = [reason for reason in first["reasons"] if reason != REASON_SELF_INTERSECTING]
    results = [first]
    for shape in shapes[1:]:
        reasons = list(invariant)
        if check_self_intersection and _is_self_intersecting(shape) is True:
            reasons.append(REASON_SELF_INTERSECTING)
        results.append(
            {"solidCount": first["solidCount"], "volumes": first["volumes"], "reasons": reasons}
        )
    return results


# --- prototypes ---------------------------------------------------------------------


@dataclass
class PrototypeGroup:
    """Every occurrence sharing one TShape, in tree order; ``[0]`` is the first placement."""

    index: int
    occurrences: list[Any] = field(default_factory=list)

    @property
    def first(self) -> Any:
        return self.occurrences[0]

    @property
    def name(self) -> str:
        return str(self.first.name)


def prototype_groups(occurrences: Iterable[Any]) -> list[PrototypeGroup]:
    """Group placed occurrences by the TShape they share.

    ``interference.occurrences_from_scene`` builds every occurrence as
    ``prototype.Moved(loc)``, so shared TShape identity IS prototype identity:
    ``TopoDS_Shape.IsPartner`` is the kernel's word for it, and the Python handle
    a live ``TShape()`` returns is the same object for the same TShape, so it
    keys a dict as long as it is kept alive -- which the dict does.
    """
    groups: list[PrototypeGroup] = []
    by_tshape: dict[int, tuple[Any, PrototypeGroup]] = {}
    for occurrence in occurrences:
        tshape = occurrence.shape.TShape()
        hit = by_tshape.get(id(tshape))
        group = hit[1] if hit is not None and hit[0] is tshape else None
        if group is None:
            # A fresh handle for a TShape already seen (the binding did not reuse
            # its wrapper): ask the kernel. Only misses pay this scan.
            group = next(
                (g for g in groups if occurrence.shape.IsPartner(g.first.shape)), None
            )
        if group is None:
            group = PrototypeGroup(index=len(groups), occurrences=[occurrence])
            groups.append(group)
        else:
            group.occurrences.append(occurrence)
        by_tshape[id(tshape)] = (tshape, group)
    return groups


def _placed_compound(shapes: list[Any]) -> Any:
    """One compound holding the placed copies to check -- a single TShape with
    N locations, which is exactly what BinTools writes: the geometry once, the
    locations as a table. The worker gets every placement, bit-exact, for the
    cost of one prototype."""
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound

    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    for shape in shapes:
        builder.Add(compound, shape)
    return compound


def _placed_shapes_from_payload(payload: bytes) -> list[Any]:
    from OCP.BinTools import BinTools
    from OCP.TopoDS import TopoDS_Iterator, TopoDS_Shape

    compound = TopoDS_Shape()
    BinTools.Read_s(compound, io.BytesIO(payload))
    if compound.IsNull():
        raise RuntimeError("validate payload deserialized to a null shape")
    shapes: list[Any] = []
    iterator = TopoDS_Iterator(compound)
    while iterator.More():
        shapes.append(iterator.Value())
        iterator.Next()
    if not shapes:
        raise RuntimeError("validate payload carried no placements")
    return shapes


def _check_payload_worker(
    args: tuple[bytes, int, dict[str, object]],
) -> tuple[int, list[dict[str, object]] | None, str | None]:
    """Process-pool entry: check one prototype's placements from a BREP payload.

    Returns ``(group index, results, None)`` or ``(group index, None, error)``
    -- exceptions are flattened so one bad part reports instead of poisoning
    the pool. A payload the worker cannot deserialize reports the
    ``PAYLOAD_UNREADABLE`` marker so the parent checks that prototype in-process.
    """
    from cadgen._internal.component_package import PAYLOAD_UNREADABLE

    payload, index, options = args
    try:
        try:
            shapes = _placed_shapes_from_payload(payload)
        except Exception as exc:  # noqa: BLE001 - marker for the parent retry
            return (index, None, f"{PAYLOAD_UNREADABLE}: {type(exc).__name__}: {exc}")
        return (index, check_placements(shapes, **options), None)
    except Exception as exc:  # noqa: BLE001 - crossing a process boundary
        return (index, None, f"{type(exc).__name__}: {exc}")


def validate_worker_count(prototype_count: int) -> int:
    """Workers for the check pool: ``CADGEN_VALIDATE_WORKERS`` overrides (0/1
    disables), else the component build's sizing -- one process below six
    prototypes, since each worker pays an interpreter + OCP import."""
    from cadgen._internal.component_package import parallel_worker_count

    return parallel_worker_count(prototype_count, env_var=WORKERS_ENV)


# --- the door -----------------------------------------------------------------------


def _self_intersection_mode(check_self_intersection: bool, every_placement: bool) -> str:
    if not check_self_intersection:
        if every_placement:
            raise ValueError(
                "every_placement re-runs the self-intersection test on every placed copy, "
                "and skip_self_intersection turns that test off: pass one or the other"
            )
        return SELF_INTERSECTION_SKIPPED
    return (
        SELF_INTERSECTION_EVERY_PLACEMENT
        if every_placement
        else SELF_INTERSECTION_FIRST_PLACEMENT
    )


def _group_findings(
    group: PrototypeGroup, results: list[dict[str, object]]
) -> list[dict[str, object]]:
    """The report's ``parts`` entries for one prototype.

    One entry per distinct reason list. In the default mode every placement
    shares the first placement's result, so a failing prototype is ONE entry
    naming every occurrence. Under ``every_placement`` the self-intersection
    verdict may split the occurrences, and each split is its own entry.
    ``ref``/``name`` are the first occurrence of the entry -- the placement the
    checks ran on; ``occurrences`` is every placement the finding applies to.
    """
    if len(results) == 1:
        results = results * len(group.occurrences)
    buckets: dict[tuple[str, ...], list[Any]] = {}
    for occurrence, result in zip(group.occurrences, results):
        reasons = tuple(str(reason) for reason in result["reasons"])
        if not reasons:
            continue
        buckets.setdefault(reasons, []).append(occurrence)
    first = results[0]
    return [
        {
            "ref": members[0].ref,
            "name": members[0].name,
            "reasons": list(reasons),
            "solidCount": first["solidCount"],
            "volumes": first["volumes"],
            "occurrences": [{"ref": member.ref, "name": member.name} for member in members],
        }
        for reasons, members in buckets.items()
    ]


class _Report:
    """The accumulating document: identical shape whether it is written mid-run
    (``partial: true``) or returned at the end. Nothing machine-dependent goes
    in it -- two machines validating one file must write one document."""

    def __init__(
        self,
        *,
        entry: str,
        occurrence_count: int,
        groups: list[PrototypeGroup],
        self_intersection: str,
        out: Path | None,
    ) -> None:
        self.entry = entry
        self.occurrence_count = occurrence_count
        self.groups = groups
        self.self_intersection = self_intersection
        self.out = out
        # The first intermediate --out write that could not land, kept so the
        # run can say the on-disk partial is behind rather than leaving the
        # reader to trust a stale checkedPrototypeCount.
        self.dropped_write: OSError | None = None
        self.findings: dict[int, list[dict[str, object]]] = {}
        self.errors: list[dict[str, object]] = []

    def record(
        self,
        group: PrototypeGroup,
        results: list[dict[str, object]] | None,
        error: str | None,
    ) -> None:
        if error is not None:
            self.findings[group.index] = []
            self.errors.append(
                {
                    "ref": group.first.ref,
                    "name": group.name,
                    "occurrences": [{"ref": o.ref, "name": o.name} for o in group.occurrences],
                    "message": f"checking {group.name} [{group.first.ref}] failed: {error}",
                }
            )
        else:
            self.findings[group.index] = _group_findings(group, results or [])
        if self.out is not None:
            # A dropped INTERMEDIATE write must not end the run. On Windows
            # os.replace is refused while anything holds the DESTINATION open,
            # and this feature exists so someone can watch the file -- so the
            # reader would abort the very validate they were following, after
            # it had already run for half an hour. The initial write still
            # rejects an undeliverable --out in the first second, and the final
            # write still fails loudly, so a persistent problem is never quiet.
            try:
                self.write(partial=len(self.findings) < len(self.groups))
            except OSError as error:
                self.dropped_write = error

    def document(self, *, partial: bool) -> dict[str, object]:
        parts: list[dict[str, object]] = []
        for group in self.groups:
            parts.extend(self.findings.get(group.index, ()))
        failures = sum(len(part["occurrences"]) for part in parts)
        document: dict[str, object] = {"ok": failures == 0 and not self.errors and not partial}
        if partial:
            document["partial"] = True
            document["checkedPrototypeCount"] = len(self.findings)
        document.update(
            {
                "entry": self.entry,
                "occurrenceCount": self.occurrence_count,
                "prototypeCount": len(self.groups),
                "selfIntersectionCheck": self.self_intersection,
                "failureCount": failures,
                "parts": parts,
                "errors": list(self.errors),
            }
        )
        return document

    def write(self, *, partial: bool) -> None:
        from cadgen._internal.atomic_replace import write_bytes_atomic

        if self.out is None:
            return
        payload = json.dumps(self.document(partial=partial), separators=(",", ":"))
        write_bytes_atomic(self.out, payload.encode("utf-8"))


def _check_groups(
    groups: list[PrototypeGroup],
    report: _Report,
    *,
    options: dict[str, object],
    every_placement: bool,
    workers: int,
    progress: Any,
    logger: Any,
) -> None:
    """Run every prototype's check -- in-process, or across a spawn pool -- and
    record each into ``report`` as it completes."""
    from cadgen._internal.component_package import PAYLOAD_UNREADABLE, _shape_brep_bytes

    def shapes_of(group: PrototypeGroup) -> list[Any]:
        if every_placement:
            return [occurrence.shape for occurrence in group.occurrences]
        return [group.first.shape]

    def in_process(group: PrototypeGroup) -> tuple[list[dict[str, object]] | None, str | None]:
        try:
            return check_placements(shapes_of(group), **options), None
        except Exception as exc:  # noqa: BLE001 - one bad part is a finding, not a crash
            return None, f"{type(exc).__name__}: {exc}"

    announced_dropped_write = False

    def finished(group: PrototypeGroup, results, error) -> None:
        nonlocal announced_dropped_write
        report.record(group, results, error)
        summary = error or ("FAIL" if report.findings.get(group.index) else "ok")
        logger.debug(
            f"checked {group.name} [{group.first.ref}] x{len(group.occurrences)}: {summary}"
        )
        if report.dropped_write is not None and not announced_dropped_write:
            announced_dropped_write = True
            # Once, not per prototype: the run continues and the final write
            # still has to succeed, but the partial on disk is now behind and
            # nothing else would say so.
            logger.info(
                f"could not update the partial report at {report.out}: {report.dropped_write}. "
                "The run continues; the file on disk is behind until the final write."
            )
        progress.advance(detail=group.name)

    if workers <= 1:
        for group in groups:
            results, error = in_process(group)
            finished(group, results, error)
        return

    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor, as_completed

    payloads = [
        (_shape_brep_bytes(_placed_compound(shapes_of(group))), group.index, options)
        for group in groups
    ]
    pool = ProcessPoolExecutor(
        max_workers=workers, mp_context=multiprocessing.get_context("spawn")
    )
    try:
        futures = {pool.submit(_check_payload_worker, args): args[1] for args in payloads}
        # as_completed rather than map: a progress count taken from map reports
        # the finished PREFIX, and the partial document must carry what is DONE.
        for future in as_completed(futures):
            index, results, error = future.result()
            group = groups[index]
            if error is not None and error.startswith(PAYLOAD_UNREADABLE):
                # BinTools write/read asymmetry on some imported solids: check
                # the original in-process shape instead, as the component build does.
                results, error = in_process(group)
            finished(group, results, error)
    except BaseException:
        # A cancelled run (Ctrl-C) must not wait on the queue: the partial
        # document on disk is what the caller keeps, and it is already written.
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        pool.shutdown(wait=True)


def inspect_validity(
    entry: str,
    *,
    refs: Iterable[str] | None = None,
    allow_open: bool = False,
    min_volume: float = DEFAULT_MIN_VOLUME_MM3,
    check_self_intersection: bool = True,
    every_placement: bool = False,
    out: Path | str | None = None,
) -> dict[str, object]:
    """Public entry point used by ``inspect validate``.

    ``out`` receives the report as JSON while the check runs -- rewritten
    atomically after every prototype, with ``"partial": true`` until the last
    one lands -- so a run that is killed (out of memory, a kernel crash, a lost
    daemon worker) leaves the findings it had reached in a readable document.
    The final write drops ``partial`` and is the returned report. Stdout cannot
    offer this: the CLI's answer is one JSON line whose first field is the
    verdict, and a verdict is not known until the end.
    """
    from cadgen.cli_logging import CliLogger
    from cadgen.cli_progress import cli_progress_line
    from cadgen.coordination import PHASE_CHECK, PHASE_COLLECT, VALIDATION, ProgressReporter
    from cadgen.interference import _selected, occurrences_from_scene, scene_label_rows
    from cadgen.step_export_target import _resolve_spec_and_scene
    from cadgen.step_targets import resolve_step_target

    mode = _self_intersection_mode(check_self_intersection, every_placement)
    out_path = Path(out).expanduser().resolve() if out is not None else None
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
        door="inspect validate",
        verb="validating",
    ).scene

    # The painter opens AFTER the scene is resolved: a stale document's rebuild
    # paints its own line, and two painters on one tty interleave into nonsense.
    with cli_progress_line(target.cad_path, logger=logger, fallback="Validating...") as sink:
        progress = ProgressReporter(
            sinks=[sink] if sink is not None else [],
            phases=VALIDATION.phases,
            labels=VALIDATION.labels,
        )
        progress.phase(PHASE_COLLECT)
        occurrences = _selected(
            occurrences_from_scene(scene),
            refs,
            label_rows=scene_label_rows(scene),
            entry_target=str(entry),
        )
        groups = prototype_groups(occurrences)
        workers = validate_worker_count(len(groups))
        report = _Report(
            entry=target.cad_path,
            occurrence_count=len(occurrences),
            groups=groups,
            self_intersection=mode,
            out=out_path,
        )
        # The worker count is narration, not report: it follows the machine, and
        # the document must not differ between two machines checking one file.
        logger.debug(
            f"{len(occurrences)} occurrence(s) share {len(groups)} prototype(s); "
            f"self-intersection: {mode}; workers: {workers}"
        )
        progress.phase(PHASE_CHECK, total=len(groups))
        started = time.perf_counter()
        if out_path is not None:
            # An empty partial document first, so a run killed before its
            # first prototype completes still leaves something readable.
            report.write(partial=bool(groups))
        _check_groups(
            groups,
            report,
            options={
                "allow_open": allow_open,
                "min_volume": min_volume,
                "check_self_intersection": check_self_intersection,
            },
            every_placement=every_placement,
            workers=workers,
            progress=progress,
            logger=logger,
        )
        progress.finish()
        logger.timing("check prototypes", time.perf_counter() - started)
    if out_path is not None:
        report.write(partial=False)
    return report.document(partial=False)
