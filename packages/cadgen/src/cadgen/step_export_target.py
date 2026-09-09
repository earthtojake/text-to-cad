"""Export one CAD model to standalone STEP/STL/3MF/GLB files.

Two callers share this module, and they offer different formats:

* The CAD Viewer's "Export model" backend — one format to an arbitrary ``--out``
  destination picked from a native Save dialog, via ``main()``/
  :func:`export_model_to_path`. Offers every :data:`FORMAT_SUFFIX` format, STEP included,
  because "Download STEP" is a Viewer menu item. This is a machine ABI, not a public
  verb: it gets no generated CLI (design/format-doors.md, decision 4).
* The per-format doors — ``cadgen.stl.build`` / ``.threemf`` / ``.glb`` and their
  ``cadgen <format> build`` CLIs — via :func:`export_cad_target`. Mesh formats only
  (:data:`MESH_EXPORT_FORMATS`); a model's ``.step`` file is written by ``step.build``
  or the model script (``python <model>.py``) instead.

Both take a DOCUMENT — an on-disk ``.step``/``.stp``, generated or imported alike —
and nothing else. No model script is accepted, parsed or run here, and no export
rebuilds a model: whether a document is behind the script that wrote it is that
model's record's question, answered by ``cadgen store why`` and never by an export
(README law 1; law 7: scripts are programs, ``python <model>.py`` is their one door).

Mesh formats tessellate from the tree behind the document's BYTES, which already
holds the exact surf geometry the exporter consumes — no generator run, no STEP
load, no extraction. A document the store has no tree for is COMPILED from those
bytes (a job in the build pool), which is also the one cache effect this module
has. One Node invocation serializes every requested format from one tessellation,
so all formats come from identical geometry, and nothing is written beside the
model.

Emits a single final JSON line on stdout: ``{"ok": true, "path": ..., "filename": ...}``
or ``{"ok": false, "error": ...}`` (the Node spawner parses the last stdout JSON line).
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import NamedTuple

from cadgen.cli_logging import CliLogger
from cadgen._internal.generation import EntrySpec
from cadgen.metadata import normalize_mesh_numeric
from cadgen._internal.mesh_animation import AnimationSnapshot
from cadgen.step_artifact_cli import _build_entry_spec, _cad_ref_for_step
from cadgen.step_export import export_build123d_step_file
from cadgen._internal.step_scene import (
    LoadedStepScene,
    load_step_scene,
)

# Logical format name -> conventional file suffix (informational; the caller owns `--out`).
FORMAT_SUFFIX = {"step": ".step", "stl": ".stl", "3mf": ".3mf", "glb": ".glb"}

# Formats :func:`export_cad_target` — the per-format doors — offer. STEP is
# deliberately absent: a format door writes only its own format, so a generated
# model writes its `.step` through `cadgen step build` or its model script run,
# and an imported model's STEP is already the file on disk. The Viewer's
# Save-dialog export still offers STEP (a machine ABI, not a door).
MESH_EXPORT_FORMATS = ("stl", "3mf", "glb")


class ResolvedScene(NamedTuple):
    """What :func:`_resolve_spec_and_scene` hands back: the spec and the
    in-memory scene, both read from the document on disk."""

    spec: EntrySpec
    scene: LoadedStepScene


def _resolve_spec_and_scene(
    repo_root: Path,
    step_path: Path | None,
    *,
    mesh_tolerance: float | None,
    mesh_angular_tolerance: float | None,
    logger: CliLogger,
) -> ResolvedScene:
    """Build the entry spec + an in-memory scene for the DOCUMENT.

    There is one input and one behaviour: load the STEP on disk, and read its
    tree's kind off the tree once built rather than classifying it up front.
    Generated and imported documents are the same thing here — a door takes
    bytes, and whether a script has moved on is that model's business, answered
    by ``cadgen store why`` and never by this path (README law 1, STORE.md §2).
    """
    if step_path is None:
        raise ValueError("step_path is required for imported STEP/STP models")
    if not step_path.is_file():
        raise FileNotFoundError(f"STEP file does not exist: {step_path}")
    with logger.timed(f"load STEP {step_path.name}"):
        scene = load_step_scene(step_path)
    spec = _build_entry_spec(
        repo_root,
        step_path,
        scene,
        mesh_tolerance=mesh_tolerance,
        mesh_angular_tolerance=mesh_angular_tolerance,
    )
    return ResolvedScene(spec, scene)


def _display_name_for(path: Path) -> str:
    try:
        return path.name
    except Exception:  # noqa: BLE001 - a message must never be the thing that fails
        return str(path)


# The shared mesh engine: one implementation behind the CLI and the
# @stl/@glb/@threemf declarations (cadgen._internal.mesh_export).
from cadgen._internal.mesh_export import (  # noqa: E402
    MeshExportJob,
    document_mesh_current,
    mesh_export_current,
    record_document_mesh,
    record_mesh_export,
    run_mesh_exporter,
)


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


def _effective_export_tolerances(
    spec: EntrySpec,
    fmt: str,
    *,
    cli_mesh_tolerance: float | None,
    cli_mesh_angular_tolerance: float | None,
) -> tuple[float | None, float | None]:
    """One precedence rule, both front doors: CLI run-level flag > declared
    format-level (@stl/@glb/@threemf) > @step model-level explicit >
    tessellator default (None).

    At a DOCUMENT door there are no declarations to read — a door tessellates
    the document's tree at the tolerance it was asked for, or the default."""
    matches = [d for d in spec.mesh_exports if d.fmt == fmt]
    # With VARIANTS declared, an ad-hoc explicit-out export is ambiguous about
    # which declaration it means — fall back to the model policy rather than
    # guess. A single declaration is unambiguous and applies.
    declared = matches[0] if len(matches) == 1 else None
    chord = cli_mesh_tolerance
    if chord is None and declared is not None:
        chord = declared.mesh_tolerance
    if chord is None:
        chord = spec.mesh_tolerance
    angle = cli_mesh_angular_tolerance
    if angle is None and declared is not None:
        angle = declared.mesh_angular_tolerance
    if angle is None:
        angle = spec.mesh_angular_tolerance
    return chord, angle


def _view_for_tree(tree_hash: str, *, document_hash: str) -> Path:
    """A view directory (assembly.json + components/) of a tree for the Node exporter (the store holds
    no result directories). Temporary; removed at interpreter exit."""
    import atexit
    import shutil

    from cadgen.store.view import export_view

    view_dir = export_view(tree_hash, document_hash=document_hash)
    # This is an owned, temporary export input, not a persistent tree. Carry
    # the exact document selection with its view; a later path read may name
    # a different revision and must not rekey this geometry's export ledger.
    import json

    manifest_path = view_dir / "assembly.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["documentHash"] = document_hash
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    atexit.register(shutil.rmtree, view_dir, True)
    return view_dir


def _view_for_document(step_path: Path) -> Path:
    """A view of the tree behind a document's BYTES, compiled if the store has
    none (``cadgen._internal.doors.document_tree``: a job in the pool, the one
    door operation that is one; the door itself never runs kernel work)."""
    from cadgen._internal.doors import document_snapshot

    document_hash, tree = document_snapshot(step_path)
    return _view_for_tree(tree, document_hash=document_hash)


def _export_scene(
    fmt: str,
    spec: EntrySpec,
    scene: LoadedStepScene,
    out: Path,
    *,
    mesh_tolerance: float | None = None,
    mesh_angular_tolerance: float | None = None,
    logger: CliLogger,
    from_current_document: bool = False,
) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "step":
        # A @step entry writes no STEP, so serialize the generator's in-memory compound; an
        # imported source already has a text STEP on disk, so copy it to the destination.
        source_compound = getattr(scene, "source_compound", None)
        if source_compound is not None:
            export_build123d_step_file(source_compound, out)
            return out
        if spec.step_path is not None and spec.step_path.is_file():
            # Only an IMPORTED source may be copied. A generated entry's step_path is its own
            # previous output, so copying it here rewrites <name>.step with the geometry the
            # last run produced while the caller reports outcome:built -- the failure in #308,
            # where an edited generator kept exporting the old part and validate, snapshot and
            # the Viewer all inherited it without a single error. A generated entry reaches
            # this line only when the scene arrived without source_compound, and the answer
            # to that is to say so, not to copy -- UNLESS the resolver loaded the scene from
            # the document because the freshness authority called it current, in which case
            # the file on disk IS this build and copying it is the export.
            if spec.source == "generated" and not from_current_document:
                raise RuntimeError(
                    f"{spec.source_ref}: refusing to export a generated model from its own "
                    f"{_display_name_for(spec.step_path)} -- the scene carries no generator "
                    "output to serialize, so the file on disk is the PREVIOUS build. Rerun "
                    "with a fresh generation (run `cadgen store gc` if this "
                    "persists) rather than trusting this export."
                )
            if spec.step_path.resolve() != out.resolve():
                shutil.copyfile(spec.step_path, out)
            return out
        raise RuntimeError("No STEP geometry available to export")

    raise ValueError(f"Unsupported export format: {fmt}")


def _resolve_mesh_package(
    repo_root: Path,
    step_path: Path | None,
    *,
    logger: CliLogger,
) -> tuple[EntrySpec, Path]:
    """Resolve what a mesh export tessellates from: ``(spec, package_dir)``.

    The DOCUMENT's bytes select a tree, and that tree already holds the exact
    surf geometry the exporter consumes — no generator run, no STEP load, no
    extraction. A miss is a compile of those bytes (a job in the pool), never a
    script run: content-hash keying cannot go stale, so there is nothing for
    source to settle here."""
    if step_path is None:
        raise ValueError("step_path is required for imported STEP/STP models")
    if not step_path.is_file():
        raise FileNotFoundError(f"STEP file does not exist: {step_path}")
    from cadgen.step_artifact_cli import _relative_to_base

    spec = EntrySpec(
        source_ref=_relative_to_base(repo_root, step_path),
        cad_ref=_cad_ref_for_step(repo_root, step_path),
        source_path=step_path,
        display_name=step_path.stem,
        source="imported",
        step_path=step_path,
    )
    return spec, _view_for_document(step_path)


def _export_mesh_jobs(
    spec: EntrySpec,
    package_dir: Path | None,
    jobs: "list[MeshExportJob]",
    *,
    logger: CliLogger,
    force: bool = False,
    animation_source: AnimationSnapshot | None = None,
) -> "tuple[frozenset[Path], dict[Path, dict]]":
    """Export every requested mesh job from ONE view of the document's tree.
    OCCT meshes nothing (the GLB is Y-up glTF for external tools:
    (x, y, z) -> (x, z, -y), mm -> m).

    Jobs against a STORE package are gated and recorded in the shared
    mesh-export ledger — the same one `@stl`/`@glb`/`@threemf` script runs
    read — so the two front doors never redo each other's work. ``force``
    ignores that gate and re-exports; it never rebuilds the MODEL, which is
    `step build`'s job (design/format-doors.md, decision 5).

    RETURNS the outputs this call actually wrote, so a caller can report which
    of its jobs the ledger had already satisfied, and what the builder BAKED for
    each of them -- the clip and the sample count of an animated GLB, which is
    derived (a clip states its own duration) and therefore worth reporting back
    the way a video reports its frame count."""
    name = spec.step_path.stem
    default_color = _color_hex(spec.color)
    if package_dir is not None:
        import json

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
        # A script run (`@stl` beside `@step`) ledgers on the MODEL's record; a
        # document at a bare door ledgers on the DOCUMENT's own index entry, by
        # its bytes — never by which script wrote it (STORE.md §2, the law: a
        # reader never opens a record).
        model = spec.script_path if spec.source == "generated" and spec.script_path is not None else None

        def _current(job: "MeshExportJob") -> bool:
            if not document_hash:
                return False
            variant = dict(
                mesh_tolerance=job.mesh_tolerance,
                mesh_angular_tolerance=job.mesh_angular_tolerance,
                # An animated GLB is a function of the clip and the render
                # module as well as the bytes, so it is its own variant: a
                # static file at the same path can never satisfy it, and an
                # edited animation source makes the ledgered one a miss.
                animation_key=job.animation_key,
                appearance_key=appearance_key,
            )
            by_document = document_mesh_current(job.out, document_hash=document_hash, fmt=job.fmt, **variant)
            if model is None:
                return by_document
            # A script run also honours what a bare door already cut from these
            # bytes (and notes it in its record so clause 5 sees the output).
            if by_document and not mesh_export_current(job.out, model=model, document_hash=document_hash, **variant):
                record_mesh_export(job.out, model=model, document_hash=document_hash, fmt=job.fmt, **variant)
            return by_document or mesh_export_current(job.out, model=model, document_hash=document_hash, **variant)

        pending = [job for job in jobs if force or not _current(job)]
        if not pending:
            return frozenset(), {}
        for job in pending:
            job.out.parent.mkdir(parents=True, exist_ok=True)
        payload = run_mesh_exporter(
            package_dir, pending, name=name, default_color=default_color, logger=logger,
            animation_source=animation_source,
            appearance=appearance,
        )
        if document_hash:
            for job in pending:
                variant = dict(
                    fmt=job.fmt,
                    mesh_tolerance=job.mesh_tolerance,
                    mesh_angular_tolerance=job.mesh_angular_tolerance,
                    animation_key=job.animation_key,
                    appearance_key=appearance_key,
                )
                # A script run ledgers on its record (which also notes the document
                # entry); a bare door ledgers on the document entry alone.
                if model is not None:
                    record_mesh_export(job.out, model=model, document_hash=document_hash, **variant)
                else:
                    record_document_mesh(job.out, document_hash=document_hash, **variant)
        return frozenset(job.out for job in pending), _baked_animations(payload)
    # A document always resolves to a view (`_view_for_document` compiles a miss),
    # so there is no second source of geometry to fall back to -- and law 10 says
    # a door that cannot answer says so rather than inventing one.
    raise RuntimeError(f"no tree in the store for {name}: nothing to export")


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m cadgen.step_export_target",
        description="Export one CAD model to STEP/3MF/STL/GLB at an explicit destination path.",
    )
    parser.add_argument("--repo-root", required=True, help="Repository/workspace root for relative metadata.")
    parser.add_argument("--step", required=True, help="The on-disk STEP/STP document to export.")
    parser.add_argument("--format", required=True, choices=tuple(FORMAT_SUFFIX), help="Output format.")
    parser.add_argument("--out", required=True, help="Destination file path for the exported model.")
    parser.add_argument(
        "--mesh-tolerance",
        type=float,
        help="Chord tolerance RELATIVE to each component's bounding diagonal (default 1.5e-3).",
    )
    parser.add_argument(
        "--mesh-angular-tolerance",
        type=float,
        help="Max normal spread across a triangle edge, radians (default 0.35).",
    )
    parser.add_argument("--verbose", action="store_true", help="Show detailed timing on stderr.")
    return parser


def export_model_to_path(
    *,
    repo_root: Path,
    step: Path,
    fmt: str,
    out: Path,
    mesh_tolerance: float | None = None,
    mesh_angular_tolerance: float | None = None,
    logger: CliLogger | None = None,
) -> dict[str, object]:
    """Export one CAD model to STEP/STL/3MF/GLB at ``out`` and RETURN
    {ok, path, filename, format}. Single source of truth, callable in-process by a
    warm-OCCT worker AND wrapped by main(); it RAISES on error so callers map their
    own protocol (the CLI shell keeps the {ok:false,error} JSON envelope)."""
    if logger is None:
        logger = CliLogger("step-export", verbose=False)
    repo_root = Path(repo_root).expanduser().resolve()
    step_path = Path(step).expanduser().resolve()
    out = Path(out).expanduser().resolve()
    mesh_tolerance = normalize_mesh_numeric(mesh_tolerance, field_name="mesh_tolerance")
    mesh_angular_tolerance = normalize_mesh_numeric(mesh_angular_tolerance, field_name="mesh_angular_tolerance")
    if fmt in MESH_EXPORT_FORMATS:
        spec, package_dir = _resolve_mesh_package(repo_root, step_path, logger=logger)
        chord, angle = _effective_export_tolerances(
            spec,
            fmt,
            cli_mesh_tolerance=mesh_tolerance,
            cli_mesh_angular_tolerance=mesh_angular_tolerance,
        )
        _export_mesh_jobs(
            spec,
            package_dir,
            [MeshExportJob(fmt=fmt, out=out, mesh_tolerance=chord, mesh_angular_tolerance=angle)],
            logger=logger,
        )
        return {"ok": True, "path": str(out), "filename": out.name, "format": fmt}
    spec, scene = _resolve_spec_and_scene(
        repo_root,
        step_path,
        mesh_tolerance=mesh_tolerance,
        mesh_angular_tolerance=mesh_angular_tolerance,
        logger=logger,
    )
    written = _export_scene(
        fmt,
        spec,
        scene,
        out,
        mesh_tolerance=mesh_tolerance,
        mesh_angular_tolerance=mesh_angular_tolerance,
        logger=logger,
        # The scene is always the document on disk now, which IS this build.
        from_current_document=True,
    )
    return {"ok": True, "path": str(written), "filename": written.name, "format": fmt}


def _is_step_suffix(path: Path) -> bool:
    return path.suffix.lower() in {".step", ".stp"}


def _resolve_export_output(
    fmt: str,
    raw: str | Path | None,
    *,
    logical_step: Path,
    spec: EntrySpec | None = None,
) -> Path:
    """Resolve one requested mesh export output. ``None`` means the model's
    DECLARED path when `@stl`/`@glb`/`@threemf` declares one — both front
    doors converge on the same artifact — else the default sibling path
    (``<name>.<ext>`` beside the logical STEP).

    An explicit OUT is a one-shot ad-hoc export and is NEVER persisted, so it
    takes NATIVE path semantics like every other cadgen path argument: absolute
    as given, ``~`` expanded, and a relative path resolved against the process's
    working directory. The persisted, portable form is the DECORATOR
    declaration (``@stl(out=...)``), which is script-anchored and reached
    through ``spec.mesh_exports`` above."""
    if raw is None and spec is not None:
        declared = next((d for d in spec.mesh_exports if d.fmt == fmt), None)
        if declared is not None:
            return declared.path
    if raw is None:
        return logical_step.with_suffix(FORMAT_SUFFIX[fmt]).resolve()
    out = Path(raw).expanduser().resolve()
    if out.suffix.lower() != FORMAT_SUFFIX[fmt]:
        raise ValueError(f"{fmt} OUT must end with {FORMAT_SUFFIX[fmt]}: {raw}")
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
    # Same reason, for the other half of the request: a None output resolves to
    # the model's DECLARED artifact below, and an animated file written there
    # silently replaces the model's static output at a committed path.
    if animation is not None and any(raw is None for _, raw in outputs):
        raise ValueError(
            "an animated export is ad hoc: name an output path. A None output is the model's "
            "DECLARED artifact, which is its static one"
        )
    repo_root = Path(repo_root).expanduser().resolve() if repo_root else Path.cwd()
    target_path = Path(target).expanduser().resolve()
    mesh_tolerance = normalize_mesh_numeric(mesh_tolerance, field_name="mesh_tolerance")
    mesh_angular_tolerance = normalize_mesh_numeric(
        mesh_angular_tolerance, field_name="mesh_angular_tolerance"
    )

    if not _is_step_suffix(target_path):
        from cadgen._internal.doors import script_target_message

        if target_path.suffix.lower() == ".py":
            raise ValueError(script_target_message(target_path))
        raise ValueError(f"Export target must be a .step/.stp document: {target}")
    step_path: Path = target_path

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

    spec, package_dir = _resolve_mesh_package(repo_root, step_path, logger=logger)

    resolved: list[MeshExportJob] = []
    seen: dict[Path, str] = {}

    def _add(
        fmt: str,
        out: Path,
        chord: float | None,
        angle: float | None,
    ) -> None:
        if out in seen:
            raise ValueError(f"{seen[out]} and {fmt} resolve to the same output path: {out}")
        seen[out] = fmt
        resolved.append(
            MeshExportJob(
                fmt=fmt,
                out=out,
                mesh_tolerance=chord,
                mesh_angular_tolerance=angle,
                animation=animation_request,
                animation_key=animation_key,
            )
        )

    for fmt, raw in outputs:
        # A bare door writes ONE mesh: the sibling default beside the document
        # (or the model's declared path when the run knows it), at the requested
        # tolerance or the default. Nothing is looked up in a sidecar — the
        # document's tree is tessellated as it is.
        out = _resolve_export_output(fmt, raw, logical_step=spec.step_path, spec=spec)
        chord, angle = _effective_export_tolerances(
            spec,
            fmt,
            cli_mesh_tolerance=mesh_tolerance,
            cli_mesh_angular_tolerance=mesh_angular_tolerance,
        )
        _add(fmt, out, chord, angle)

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
                "meshTolerance": job.mesh_tolerance,
                "meshAngularTolerance": job.mesh_angular_tolerance,
                "animation": summary,
            }
        )
    logger.total()
    return {"ok": True, "files": files, "warnings": warnings}


def run_cli_payload(argv: list[str] | None = None) -> dict[str, object]:
    """Parse CLI ``argv`` and run :func:`export_model_to_path`, RETURNING its
    ``{ok:true,...}`` payload (no printing). RAISES on error — callers own the error
    envelope. The in-process primitive shared by ``main()`` and the CAD Viewer's warm
    worker."""
    args = build_parser().parse_args(argv)
    logger = CliLogger("step-export", verbose=bool(args.verbose))
    payload = export_model_to_path(
        repo_root=Path(args.repo_root),
        step=Path(args.step),
        fmt=args.format,
        out=Path(args.out),
        mesh_tolerance=args.mesh_tolerance,
        mesh_angular_tolerance=args.mesh_angular_tolerance,
        logger=logger,
    )
    logger.total()
    return payload


def main(argv: list[str] | None = None) -> int:
    try:
        payload = run_cli_payload(argv)
    except Exception as exc:  # noqa: BLE001 — surface a clean JSON error to the CLI caller.
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":")))
        return 1
    print(json.dumps(payload, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
