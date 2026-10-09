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

Meshes are cut from the tree behind the document's BYTES — the store's mesh of
each component, derived in the build pool where it is missing — with no generator
run and no STEP load. A document the store has no tree for is COMPILED from those
bytes (a job in the build pool). One engine call serializes every requested
format from the same stored meshes, so all formats come from identical geometry,
and nothing is written beside the model but the files that were asked for.
"""

from __future__ import annotations

from pathlib import Path

from cadgen.cli_logging import CliLogger
from cadgen._internal.doors import STEP_SUFFIXES
from cadgen._internal.generation import EntrySpec
from cadgen._internal.mesh_animation import AnimationSnapshot
from cadgen._internal.mesh_export import (
    MESH_EXPORT_FORMATS,
    MESH_FORMAT_SUFFIX,
    MeshExportJob,
    MeshSource,
    document_mesh_current,
    record_document_mesh,
    run_mesh_exporter,
)
from cadgen.metadata import normalize_mesh_numeric
from cadgen.store.meshes import DEFAULT_ANGLE, DEFAULT_CHORD
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
    feeds the exporter as its default colour is sRGB (the GLB writer decodes it
    back to a linear ``baseColorFactor``, and 3MF's ``displaycolor`` is spec'd sRGB).
    """
    try:
        red, green, blue = (_linear_channel_to_srgb_byte(float(c)) for c in tuple(color)[:3])
    except (TypeError, ValueError):
        return None
    return f"#{red:02x}{green:02x}{blue:02x}"


def _mesh_package(repo_root: Path, step_path: Path) -> "tuple[EntrySpec, MeshSource]":
    """What a mesh export cuts its meshes from: ``(spec, source)``.

    The DOCUMENT's bytes select a tree, and that tree's components are what the
    store meshes -- no generator run, no STEP load. A miss is a compile of those
    bytes (a job in the pool: ``cadgen._internal.doors.document_snapshot``, the one
    door operation that is one), never a script run: content-hash keying cannot go
    stale, so there is nothing for source to settle here. The selected document
    rides with its tree: a later read of the path may name another revision, and
    must not rekey this geometry's export ledger."""
    from cadgen._internal.doors import document_snapshot

    spec = _build_entry_spec(repo_root, step_path)
    document_hash, tree = document_snapshot(step_path)
    return spec, MeshSource(tree, document_hash)


def _export_mesh_jobs(
    spec: EntrySpec,
    source: MeshSource,
    jobs: "list[MeshExportJob]",
    *,
    logger: CliLogger,
    force: bool = False,
    animation_source: AnimationSnapshot | None = None,
) -> "tuple[frozenset[Path], dict[Path, dict], dict[Path, list[str]]]":
    """Export every requested mesh job from the document's tree, in one engine call
    (the GLB is Y-up glTF for external tools: (x, y, z) -> (x, z, -y), mm -> m).

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
    document_hash = str(source.document_hash or "")
    if len(document_hash) != 64 or any(c not in "0123456789abcdef" for c in document_hash):
        raise RuntimeError("mesh export source is missing its selected STEP document digest")
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
            # An animated GLB is a function of the clip and its keyframes as
            # well as the bytes, so it is its own variant: a static file at the
            # same path can never satisfy it, and a rebaked animation makes the
            # ledgered one a miss.
            animation_key=job.animation_key,
            appearance_key=appearance_key,
        )

    pending = [
        job for job in jobs
        if force or not document_mesh_current(job.out, document_hash=document_hash, **_variant(job))
    ]
    if not pending:
        return frozenset(), {}, {}
    for job in pending:
        job.out.parent.mkdir(parents=True, exist_ok=True)
    payload = run_mesh_exporter(
        source, pending, name=spec.step_path.stem, default_color=_color_hex(spec.color),
        logger=logger, animation_source=animation_source, appearance=appearance,
    )
    for job in pending:
        record_document_mesh(job.out, document_hash=document_hash, **_variant(job))
    return frozenset(job.out for job in pending), _baked_animations(payload), _file_warnings(payload)


def _baked_animations(payload: dict) -> "dict[Path, dict]":
    """The engine's per-output ``animation`` block, keyed by the path it wrote.

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


def _file_warnings(payload: dict) -> "dict[Path, list[str]]":
    """Each written file's own warnings, keyed by its path: the faces no mesher could
    cover, which the file leaves open (``mesh_export.run_mesh_exporter``)."""
    return {Path(str(entry["path"])): [str(text) for text in entry["warnings"]]
            for entry in payload.get("files") or [] if entry.get("warnings")}


def _ledgered_animation(job: "MeshExportJob") -> "dict | None":
    """What a SKIPPED animated GLB carries, read off the request that wrote it.

    A job the ledger satisfied was never rewritten, so the engine's summary does
    not exist — but the file at that path is the one this request produced, and
    reporting ``None`` for it would say "static export" (what a null animation
    means, results.MeshExportFile) about a file with a clip baked into it. The
    counts stay absent because nothing on this side knows them; the clip and
    the span are the request's own."""
    if job.animation is None:
        return None
    return {
        "clip": job.animation.get("clip"),
        "seconds": job.animation.get("seconds"),
        "start": job.animation.get("start"),
        "pivots": None,
        "skins": None,
        "joints": None,
    }


def _bakes_effects_static(job: "MeshExportJob") -> bool:
    """Whether this request told the export to FREEZE something -- the only case
    where a skipped export has warnings it is not repeating: ``drop`` bakes an
    effect's value at start, leaving named occurrences standing still in a file that
    otherwise moves."""
    return bool((job.animation or {}).get("drop"))


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
    run, no source — and one engine call serializes every requested format from
    the same stored meshes, so all formats come from identical geometry.
    ``outputs`` pairs a format name with an explicit output path, or ``None`` for the
    sibling default beside the document. ``force`` re-exports past the ledger. Nothing here moves geometry: a mesh is the
    document's tree, tessellated — with ONE exception, ``animation``, which does
    not move it either: it writes the clip the document's sidecar animation declares
    into the GLB as glTF node animation, so a reader moves the geometry itself.

    Writes no ``.step`` and no beside-source artifacts; a document missing its tree
    or its meshes has them derived into the SHARED store (content keyed — the same
    ones every later view or export of those bytes reuses). Each returned file carries whether the
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

    # The clip name and the sidecar's keyframes are resolved BEFORE any tessellation:
    # a typo must fail as a clean CLI error naming the clips the model has, not
    # after a minute of meshing. The token it returns is what keeps a rebaked
    # animation from being served out of the ledger. The sampler gets the same
    # captured keyframes, so edits during preparation cannot rekey it.
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
        # store's mesh default. Model output declarations are not read, and
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

    spec, source = _mesh_package(repo_root, step_path)
    written, baked, noted = _export_mesh_jobs(
        spec, source, resolved, logger=logger, force=force,
        animation_source=animation_source,
    )
    files = []
    warnings: list[str] = []
    for job in resolved:
        skipped = job.out not in written
        summary = baked.get(job.out)
        warnings.extend(noted.get(job.out, ()))
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
                    "rewrites nothing, so the occurrences its drop froze are not "
                    "named again — re-run with --force to hear them"
                )
        files.append(
            {
                "format": job.fmt,
                "path": str(job.out),
                "skipped": skipped,
                # The EFFECTIVE pair: an omitted tolerance is the store's mesh
                # default, and the result says which number that was. (The ledger
                # keeps keying an omitted tolerance as "default", so a changed
                # default re-exports rather than reading as current.)
                "meshTolerance": job.mesh_tolerance if job.mesh_tolerance is not None else DEFAULT_CHORD,
                "meshAngularTolerance": (
                    job.mesh_angular_tolerance if job.mesh_angular_tolerance is not None else DEFAULT_ANGLE
                ),
                "animation": summary,
            }
        )
    logger.total()
    return {"ok": True, "files": files, "warnings": warnings}
