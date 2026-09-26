"""Export one CAD DOCUMENT to standalone STL/3MF/GLB files.

The engine behind the per-format doors — ``cadgen.stl.build`` /
``cadgen.threemf.build`` / ``cadgen.glb.build`` and their ``cadgen <format>
build`` CLIs — via :func:`export_cad_target`. Mesh formats only
(:data:`MESH_EXPORT_FORMATS`): a model's ``.step`` is written by its script
(``python <model>.py``) or by ``cadgen step build``.

It takes a DOCUMENT — an on-disk ``.step``/``.stp``, generated or imported alike —
and nothing else. No model script is accepted, parsed or run here, no model
output declaration is read, and no export rebuilds a model: whether a document
is behind the script that wrote it is that model's record's question, answered
by ``cadgen store why`` and never by an export (README law 1; law 7: scripts are
programs, ``python <model>.py`` is their one door).

Meshes tessellate from the tree behind the document's BYTES, which already
holds the exact surf geometry the exporter consumes — no generator run, no STEP
load, no extraction. A document the store has no tree for is COMPILED from those
bytes (a job in the build pool), which is also the one cache effect this module
has. One Node invocation serializes every requested format from one tessellation,
so all formats come from identical geometry, and nothing is written beside the
model but the files that were asked for.
"""

from __future__ import annotations

import contextlib
import json
import shutil
from collections.abc import Iterator
from pathlib import Path

from cadgen.cli_logging import CliLogger
from cadgen._internal.doors import STEP_SUFFIXES
from cadgen._internal.generation import EntrySpec
from cadgen._internal.mesh_animation import AnimationSnapshot
from cadgen._internal.mesh_export import (
    MESH_EXPORT_FORMATS,
    MESH_FORMAT_SUFFIX,
    MeshExportJob,
    document_mesh_current,
    record_document_mesh,
    run_mesh_exporter,
)
from cadgen._internal.tessellation import (
    TESSELLATOR_ANGLE_TOLERANCE,
    TESSELLATOR_CHORD_TOLERANCE,
)
from cadgen.metadata import normalize_mesh_numeric
from cadgen.step_artifact_cli import _build_entry_spec

# :data:`MESH_EXPORT_FORMATS` (cadgen._internal.mesh_export) is what
# :func:`export_cad_target` — the per-format doors — offers. STEP is
# deliberately absent: a format door writes only its own format, so a generated
# model writes its `.step` through its model script run, a re-emit through
# `cadgen step build`, and an imported model's STEP is already the file on disk.


def _linear_channel_to_srgb_byte(channel: float) -> int:
    """One LINEAR channel (0..1) to the 0..255 byte an sRGB hex carries.

    The mirror of ``linearChannelToSrgbByte`` in ``packages/core/src/lib/color.js``
    -- see that module for why the boundary exists.
    """
    clamped = max(0.0, min(1.0, channel))
    srgb = clamped * 12.92 if clamped <= 0.0031308 else 1.055 * clamped ** (1 / 2.4) - 0.055
    return max(0, min(255, round(srgb * 255)))


def _color_hex(color) -> str | None:
    """LINEAR RGBA floats (0..1) -> sRGB ``#rrggbb``, or None when there is no
    usable color.

    A build123d ``Color`` / OCCT ``Quantity_Color`` is linear; the hex this
    feeds to ``--default-color`` is sRGB (the mesh exporter decodes it back to a
    linear glTF ``baseColorFactor``, and 3MF's ``displaycolor`` is spec'd sRGB).
    """
    try:
        red, green, blue = (_linear_channel_to_srgb_byte(float(c)) for c in tuple(color)[:3])
    except (TypeError, ValueError):
        return None
    return f"#{red:02x}{green:02x}{blue:02x}"


@contextlib.contextmanager
def _view_for_tree(tree_hash: str, *, document_hash: str) -> Iterator[Path]:
    """A view directory (assembly.json + components/) of a tree for the Node
    exporter — the store holds no result directories. The view is OWNED by this
    context and removed when it closes, whether the export wrote, skipped or
    raised. Never ``atexit``: doors run in daemon pool workers, which the pool
    recycles and kills without running exit handlers, so every export used to
    leave one ``cadgen-view-*`` directory behind in the temp dir."""
    from cadgen.store.view import export_view

    view_dir = export_view(tree_hash, document_hash=document_hash)
    try:
        # This is an owned, temporary export input, not a persistent tree. Carry
        # the exact document selection with its view; a later path read may name
        # a different revision and must not rekey this geometry's export ledger.
        manifest_path = view_dir / "assembly.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["documentHash"] = document_hash
        manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        yield view_dir
    finally:
        shutil.rmtree(view_dir, ignore_errors=True)


@contextlib.contextmanager
def _mesh_package(repo_root: Path, step_path: Path) -> "Iterator[tuple[EntrySpec, Path]]":
    """What a mesh export tessellates from: ``(spec, view_dir)``, the view removed
    on exit (:func:`_view_for_tree`).

    The DOCUMENT's bytes select a tree, and that tree already holds the exact
    surf geometry the exporter consumes — no generator run, no STEP load, no
    extraction. A miss is a compile of those bytes (a job in the pool:
    ``cadgen._internal.doors.document_snapshot``, the one door operation that is
    one), never a script run: content-hash keying cannot go stale, so there is
    nothing for source to settle here."""
    from cadgen._internal.doors import document_snapshot

    spec = _build_entry_spec(repo_root, step_path)
    document_hash, tree = document_snapshot(step_path)
    with _view_for_tree(tree, document_hash=document_hash) as view_dir:
        yield spec, view_dir


def _export_mesh_jobs(
    spec: EntrySpec,
    package_dir: Path,
    jobs: "list[MeshExportJob]",
    *,
    logger: CliLogger,
    force: bool = False,
    animation_source: AnimationSnapshot | None = None,
) -> "tuple[frozenset[Path], dict[Path, dict]]":
    """Export every requested mesh job from ONE view of the document's tree.
    OCCT meshes nothing (the GLB is Y-up glTF for external tools:
    (x, y, z) -> (x, z, -y), mm -> m).

    Jobs are gated and recorded in the ARTIFACT-side mesh ledger — the document's
    own index entry, keyed by its bytes, never by which script wrote it (STORE.md
    §2, the law: a reader never opens a record). A model's script run notes the
    same ledger for the meshes it declares, so the two front doors never redo
    each other's work. ``force`` ignores that gate and re-exports; it never
    rebuilds the MODEL, which is its script's job.

    RETURNS the outputs this call actually wrote, so a caller can report which
    of its jobs the ledger had already satisfied, and what the builder BAKED for
    each of them -- the clip and the sample count of an animated GLB, which is
    derived (a clip states its own duration) and therefore worth reporting back
    the way a video reports its frame count."""
    manifest = json.loads((package_dir / "assembly.json").read_text(encoding="utf-8"))
    document_hash = str(manifest.get("documentHash") or "")
    if len(document_hash) != 64 or any(c not in "0123456789abcdef" for c in document_hash):
        raise RuntimeError("mesh export view is missing its selected STEP document digest")
    from cadgen._internal.source_sidecar import appearance_digest, read_source_sidecar

    if animation_source is not None:
        if animation_source.document_hash != document_hash:
            raise RuntimeError("STEP changed after its animation was selected; retry the export")
        appearance = animation_source.appearance
    else:
        sidecar = read_source_sidecar(spec.entry_path, document_hash=document_hash) if spec.entry_path is not None else None
        appearance = (sidecar or {}).get("appearance")
    appearance_key = appearance_digest(appearance)

    def _variant(job: "MeshExportJob") -> dict:
        return dict(
            fmt=job.fmt,
            mesh_tolerance=job.mesh_tolerance,
            mesh_angular_tolerance=job.mesh_angular_tolerance,
            # An animated GLB is a function of the clip and the render module as
            # well as the bytes, so it is its own variant: a static file at the
            # same path can never satisfy it, and an edited animation source
            # makes the ledgered one a miss.
            animation_key=job.animation_key,
            appearance_key=appearance_key,
        )

    pending = [
        job for job in jobs
        if force or not document_mesh_current(job.out, document_hash=document_hash, **_variant(job))
    ]
    if not pending:
        return frozenset(), {}
    for job in pending:
        job.out.parent.mkdir(parents=True, exist_ok=True)
    payload = run_mesh_exporter(
        package_dir, pending, name=spec.step_path.stem, default_color=_color_hex(spec.color),
        logger=logger, animation_source=animation_source, appearance=appearance,
    )
    for job in pending:
        record_document_mesh(job.out, document_hash=document_hash, **_variant(job))
    return frozenset(job.out for job in pending), _baked_animations(payload)


def _baked_animations(payload: dict) -> "dict[Path, dict]":
    """The builder's per-output ``animation`` block, keyed by the path it wrote.

    Only an animated GLB has one. It arrives WHOLE, warnings included: what the
    sampling could not carry is the caller's answer, not a log line, and
    ``export_cad_target`` lifts it out of here into the result so ``--json``
    hears it too."""
    baked: dict[Path, dict] = {}
    for entry in payload.get("files") or []:
        summary = entry.get("animation")
        if isinstance(summary, dict):
            baked[Path(str(entry["path"]))] = dict(summary)
    return baked


def _ledgered_animation(job: "MeshExportJob") -> "dict | None":
    """What a SKIPPED animated GLB carries, read off the request that wrote it.

    A job the ledger satisfied was never sampled, so the builder's summary does
    not exist — but the file at that path is the one this request produced, and
    reporting ``None`` for it would say "static export" (what a null animation
    means, results.MeshExportFile) about a file with a clip baked into it. The
    sample and moving counts stay absent because nothing on this side knows
    them; the clip and the schedule are the request's own."""
    if job.animation is None:
        return None
    return {
        "clip": job.animation.get("clip"),
        "fps": job.animation.get("fps"),
        "samples": None,
        "seconds": job.animation.get("seconds"),
        "start": job.animation.get("start"),
        "channels": None,
    }


def _bakes_effects_static(job: "MeshExportJob") -> bool:
    """Whether this request told the sampler to FREEZE something — the only case
    where a skipped export has warnings it is not repeating.

    ``drop`` bakes an effect's value at start; ``deform: "rest"`` ships a moving
    tube at its rest shape. Both leave named occurrences standing still in a file
    that otherwise moves. ``deform: "morph"`` freezes nothing — it bakes the
    deformation as morph targets, which is why it exists — and ``refuse`` never
    produced a file at all."""
    request = job.animation or {}
    return bool(request.get("drop")) or request.get("deform") == "rest"


def _resolve_export_output(fmt: str, raw: str | Path | None, *, document: Path) -> Path:
    """Resolve one requested mesh output. Model output declarations are not
    read: ``None`` is the sibling default, ``<name>.<ext>`` beside the document.

    An explicit OUT is a one-shot ad-hoc export and is NEVER persisted, so it
    takes NATIVE path semantics like every other cadgen path argument: absolute
    as given, ``~`` expanded, and a relative path resolved against the process's
    working directory. The persisted, portable form is the DECORATOR declaration
    (``@stl(out=...)``), which is script-anchored and honoured by the model's own
    run, never by a door."""
    suffix = MESH_FORMAT_SUFFIX[fmt]
    if raw is None:
        return document.with_suffix(suffix).resolve()
    out = Path(raw).expanduser().resolve()
    if out.suffix.lower() != suffix:
        raise ValueError(f"{fmt} OUT must end with {suffix}: {raw}")
    return out


def export_cad_target(
    target: str | Path,
    outputs: "list[tuple[str, str | Path | None]]",
    *,
    repo_root: Path | None = None,
    mesh_tolerance: float | None = None,
    mesh_angular_tolerance: float | None = None,
    animation: str | dict | None = None,
    force: bool = False,
    verbose: bool = False,
    logger: CliLogger | None = None,
) -> dict[str, object]:
    """Export one CAD DOCUMENT to one or more of :data:`MESH_EXPORT_FORMATS`
    in a single run.

    The shared engine entry behind the per-format doors (``cadgen.stl.build`` and
    friends). Geometry comes from the document's store tree — no generator
    run, no source, no extraction — and one Node invocation serializes every requested
    format from one tessellation, so all formats come from identical geometry.
    ``outputs`` pairs a format name with an explicit output path, or ``None`` for the
    sibling default beside the document. ``force`` re-exports past the ledger. Nothing here moves geometry: a mesh is the
    document's tree, tessellated — with ONE exception, ``animation``, which does
    not move it either: it writes the clip the document's sidecar animation declares
    into the GLB as glTF node animation, so a reader moves the geometry itself.

    Writes no ``.step`` and no beside-source artifacts; a document missing its render
    package compiles one into the SHARED store (content keyed — the same package every
    later view or export of those bytes reuses). Each returned file carries whether the
    ledger had already satisfied it and the effective tolerance pair it was written
    at."""
    if logger is None:
        logger = CliLogger("cadgen mesh export", verbose=verbose)
    if not outputs:
        raise ValueError("No export formats requested")
    for fmt, _ in outputs:
        if fmt not in MESH_EXPORT_FORMATS:
            raise ValueError(
                f"Unsupported export format: {fmt}. "
                f"Supported formats: {', '.join(MESH_EXPORT_FORMATS)}."
            )
        # Not a door-level guard duplicated: this is the ENGINE, and a caller
        # reaching it with a clip and a format that has nowhere to put one must
        # not have the clip silently dropped on the way to the builder.
        if animation is not None and fmt != "glb":
            raise ValueError(
                f"{fmt} carries no animation: only `cadgen glb build --animation` writes a "
                "clip into a file — the other mesh formats have nowhere to put one"
            )
    # Omitted output is reserved for the static export; a clip needs an explicit
    # destination because it changes the artifact's structure and initial pose.
    if animation is not None and any(raw is None for _, raw in outputs):
        raise ValueError(
            "an animated export is ad hoc: name an output path. Omitting the output writes "
            "a static sibling .glb beside the document; choose a destination for the animated file"
        )
    repo_root = Path(repo_root).expanduser().resolve() if repo_root else Path.cwd()
    mesh_tolerance = normalize_mesh_numeric(mesh_tolerance, field_name="mesh_tolerance")
    mesh_angular_tolerance = normalize_mesh_numeric(
        mesh_angular_tolerance, field_name="mesh_angular_tolerance"
    )
    # THE one validation of TARGET for a mesh build, door or direct call: a
    # `.py` is refused by naming the run, any other suffix by naming what this
    # takes, a missing file by saying so (cadgen._internal.doors).
    from cadgen._internal.doors import document_target

    step_path = document_target(target, suffixes=STEP_SUFFIXES)

    # The clip name and embedded animation source are resolved BEFORE any tessellation:
    # a typo must fail as a clean CLI error naming the clips the model has, not
    # after a minute of meshing. The token it returns is what keeps an edited
    # animation source from being served out of the ledger. Carry the
    # same captured text to Node so edits during preparation cannot rekey it.
    animation_source: AnimationSnapshot | None = None
    animation_request: dict[str, object] | None = None
    animation_key: str | None = None
    if animation is not None:
        from cadgen._internal.mesh_animation import parse_animation_option, resolve_animation

        animation_request = parse_animation_option(animation)
        animation_source, animation_key = resolve_animation(step_path, animation_request)

    resolved: list[MeshExportJob] = []
    seen: dict[Path, str] = {}
    for fmt, raw in outputs:
        # A door writes the mesh it was asked for: the sibling default beside the
        # document or the explicit OUT, at the requested tolerance or the
        # tessellator's default. Model output declarations are not read, and
        # nothing is looked up in a sidecar but the document's own appearance.
        out = _resolve_export_output(fmt, raw, document=step_path)
        if out in seen:
            raise ValueError(f"{seen[out]} and {fmt} resolve to the same output path: {out}")
        seen[out] = fmt
        resolved.append(
            MeshExportJob(
                fmt=fmt,
                out=out,
                mesh_tolerance=mesh_tolerance,
                mesh_angular_tolerance=mesh_angular_tolerance,
                animation=animation_request,
                animation_key=animation_key,
            )
        )

    with _mesh_package(repo_root, step_path) as (spec, package_dir):
        written, baked = _export_mesh_jobs(
            spec, package_dir, resolved, logger=logger, force=force,
            animation_source=animation_source,
        )
    files = []
    warnings: list[str] = []
    for job in resolved:
        skipped = job.out not in written
        summary = baked.get(job.out)
        if summary is not None:
            # The warnings ride OUT of the per-file block and into the run's own,
            # so one place answers "what did this export not carry" whether the
            # caller reads human lines or --json.
            warnings.extend(str(text) for text in (summary.pop("warnings", None) or ()))
        elif skipped:
            summary = _ledgered_animation(job)
            if summary is not None and _bakes_effects_static(job):
                warnings.append(
                    f"{job.out.name} is current for clip {summary['clip']}: a skipped export "
                    "re-samples nothing, so the occurrences its drop/deform froze are not "
                    "named again — re-run with --force to hear them"
                )
        files.append(
            {
                "format": job.fmt,
                "path": str(job.out),
                "skipped": skipped,
                # The EFFECTIVE pair: an omitted tolerance is the tessellator's
                # default, and the result says which number that was. (The ledger
                # keeps keying an omitted tolerance as "default", so a changed
                # default re-exports rather than reading as current.)
                "meshTolerance": (
                    job.mesh_tolerance if job.mesh_tolerance is not None else TESSELLATOR_CHORD_TOLERANCE
                ),
                "meshAngularTolerance": (
                    job.mesh_angular_tolerance
                    if job.mesh_angular_tolerance is not None
                    else TESSELLATOR_ANGLE_TOLERANCE
                ),
                "animation": summary,
            }
        )
    logger.total()
    return {"ok": True, "files": files, "warnings": warnings}
