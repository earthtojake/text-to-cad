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

Both accept an imported ``.step``/``.stp`` or a generated ``@step`` Python source;
exports can never be stale: a model either passes the canonical freshness gate (closure
included) and exports from its store render package, or it rebuilds from source.

Mesh formats tessellate from a render package — the STORE package when the model is
current (the fast path: no generator run, no STEP load, no extraction), else a one-shot
temporary package extracted from the freshly built scene. Geometry is extracted at most
once per run and one Node invocation serializes every requested format from one
tessellation, so all formats come from identical geometry. The module writes no
beside-source artifacts; the one cache effect is that an imported model missing its
package warms the SHARED store via the same build ``cadgen step build`` runs.

Emits a single final JSON line on stdout: ``{"ok": true, "path": ..., "filename": ...}``
or ``{"ok": false, "error": ...}`` (the Node spawner parses the last stdout JSON line).
"""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import NamedTuple

from cadgen.catalog import source_from_path
from cadgen.cli_logging import CliLogger
from cadgen._internal.generation import (
    EntrySpec,
    _entry_spec_from_source,
    run_script_generator,
)
from cadgen.metadata import normalize_mesh_numeric
from cadgen.step_artifact_cli import _build_entry_spec, _cad_ref_for_step, infer_entry_kind
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


def _apply_mesh_overrides(
    spec: EntrySpec,
    mesh_tolerance: float | None,
    mesh_angular_tolerance: float | None,
) -> EntrySpec:
    if mesh_tolerance is None and mesh_angular_tolerance is None:
        return spec
    return replace(
        spec,
        mesh_tolerance=mesh_tolerance if mesh_tolerance is not None else spec.mesh_tolerance,
        mesh_angular_tolerance=(
            mesh_angular_tolerance
            if mesh_angular_tolerance is not None
            else spec.mesh_angular_tolerance
        ),
    )


class ResolvedScene(NamedTuple):
    """What :func:`_resolve_spec_and_scene` hands back: the spec, the in-memory
    scene, and whether that scene came from RUNNING THE GENERATOR (``True``) or
    from loading the document on disk (``False``)."""

    spec: EntrySpec
    scene: LoadedStepScene
    from_source: bool


def _resolve_spec_and_scene(
    repo_root: Path,
    step_path: Path | None,
    source_path: Path | None,
    *,
    mesh_tolerance: float | None,
    mesh_angular_tolerance: float | None,
    logger: CliLogger,
    door: str,
    verb: str,
) -> ResolvedScene:
    """Build the entry spec + an in-memory scene for the model.

    Imported model (no ``source_path``): load the existing STEP and classify it via
    :func:`cadgen.step_artifact_cli.infer_entry_kind`.

    Generated model (``source_path`` given): the DOCUMENT on disk is the truth and is
    loaded exactly like an import, running no Python at all -- a door never rebuilds
    a model, current or not (STORE.md §9). Only a MISSING document runs the ``@step``
    entry in-process (a caller handed the script and there is nothing else to read),
    and that decision is ANNOUNCED on stderr through
    :func:`cadgen._internal.doors.announce_rebuild` before the generator starts, naming
    ``door`` (the command deciding) and ``verb`` (what it will do afterwards).
    """
    if source_path is not None:
        from cadgen._internal.doors import announce_rebuild

        source = source_from_path(source_path)
        if source is None:
            raise RuntimeError(f"Python generator is not a @step CAD source: {source_path}")
        spec = _entry_spec_from_source(source)
        if spec.step_path is None:
            raise RuntimeError(f"Generator defines no STEP output: {source_path}")
        # Align the logical STEP path/name when the caller passed an explicit --step that the
        # generator does not itself resolve to (mirrors cadgen.step_artifact_cli).
        if step_path is not None and spec.step_path.resolve() != step_path.resolve():
            spec = replace(
                spec,
                cad_ref=_cad_ref_for_step(repo_root, step_path),
                display_name=step_path.stem,
                step_path=step_path,
            )
        spec = _apply_mesh_overrides(spec, mesh_tolerance, mesh_angular_tolerance)
        document = spec.step_path
        if document.is_file():
            # The document AS WRITTEN is what a door measures (STORE.md §9): no
            # staleness check, no rebuild -- a source that has moved on is the
            # model's business. Load it exactly like an import.
            with logger.timed(f"load STEP {document.name}"):
                scene = load_step_scene(document)
            return ResolvedScene(spec, scene, False)
        # No document at all: nothing to read. Only a caller that handed a SCRIPT
        # (the viewer's export ABI) reaches this, and it runs the generator, saying so.
        announce_rebuild(
            door, document, reason="no document on disk", source=spec.script_path or source_path, verb=verb
        )
        # An export runs the generator but writes the render package NOTHING -- its output
        # is a STEP/STL/3MF/GLB file somewhere else entirely. Reporting it as a build made
        # a fully-current model show `generating` with an empty bar for the whole length
        # of the export.
        scene = run_script_generator(
            spec,
            "step",
            logger=logger,
            force=True,
            intent="generate",
        )
        if scene is None:
            raise RuntimeError(f"Generator did not produce a STEP scene: {spec.source_ref}")
        return ResolvedScene(spec, scene, True)

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
        kind=infer_entry_kind(step_path, scene),
        mesh_tolerance=mesh_tolerance,
        mesh_angular_tolerance=mesh_angular_tolerance,
    )
    return ResolvedScene(spec, scene, False)


def _display_name_for(path: Path) -> str:
    try:
        return path.name
    except Exception:  # noqa: BLE001 - a message must never be the thing that fails
        return str(path)


# The shared mesh engine: one implementation behind the CLI and the
# @stl/@glb/@threemf declarations (cadgen._internal.mesh_export).
from cadgen._internal.mesh_export import (  # noqa: E402
    MeshExportJob,
    mesh_export_current,
    record_mesh_export,
    run_mesh_exporter,
)


def _linear_channel_to_srgb_byte(channel: float) -> int:
    """One LINEAR channel (0..1) to the 0..255 byte an sRGB hex carries.

    The mirror of ``linearChannelToSrgbByte`` in ``packages/cadgen-js/src/lib/color.js``
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


def _build_export_package_from_scene(
    spec: EntrySpec,
    scene: LoadedStepScene,
    package_dir: Path,
    *,
    logger: CliLogger,
) -> None:
    """Extract the scene's exact geometry into a tree (surf extraction only —
    no OCCT meshing) and lay a view of it at ``package_dir``. Run at most ONCE
    per export run: every requested format tessellates from this one view."""
    from cadgen.store.build import build_tree_from_compound
    from cadgen.store.view import export_view

    compound = getattr(scene, "source_compound", None)
    if compound is None:
        from cadgen._internal.step_scene_mesh import scene_to_build123d_compound

        compound = scene_to_build123d_compound(scene)

    with logger.timed("extract exact geometry"):
        tree_hash, _tree, _stats = build_tree_from_compound(
            compound,
            root_name=spec.step_path.stem,
            entry_kind=spec.kind,
            single_component=spec.kind != "assembly",
        )
    export_view(tree_hash, package_dir)


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

    At a DOCUMENT door the declarations come from the sidecar, where the run
    that wrote the document already folded its model-level policy in; the spec
    supplies the policy only for the Viewer's spec-driven export path."""
    matches = list(spec.mesh_exports)
    if not matches and spec.step_path is not None:
        matches = list(_sidecar_declarations(spec.step_path, fmt))
    matches = [d for d in matches if d.fmt == fmt]
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


def _current_store_package(spec: EntrySpec) -> Path | None:
    """The store render package for a CURRENT model, or None.

    This is the export fast path: when the canonical freshness gate — the same
    one `python <model>.py` and the artifact CLI use, closure included — says
    the model is current, its store package holds exactly the surf geometry the
    mesh exporter consumes, and extraction is pure waste. A stale or unbuilt
    model returns None and the caller builds from source, so exports can never
    serve stale geometry (the #308 class)."""
    from cadgen.catalog import result_tree_for
    from cadgen.step_artifact_cli import _current_artifact_for_spec

    if spec.entry_path is None:
        return None
    if _current_artifact_for_spec(spec) is None:
        return None
    tree = result_tree_for(spec.entry_path)
    return _view_for_tree(tree) if tree else None


def _view_for_tree(tree_hash: str) -> Path:
    """A package-shaped VIEW of a tree for the Node exporter (the store holds
    no result directories). Temporary; removed at interpreter exit."""
    import atexit
    import shutil

    from cadgen.store.view import export_view

    view_dir = export_view(tree_hash)
    atexit.register(shutil.rmtree, view_dir, True)
    return view_dir


def _view_for_document(step_path: Path) -> Path:
    """A view of the tree behind a document's BYTES, compiled if the store has
    none (``cadgen._internal.doors.document_tree``: a job in the pool, the one
    door operation that is one; the door itself never runs kernel work)."""
    from cadgen._internal.doors import document_tree

    return _view_for_tree(document_tree(step_path))


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
    source_path: Path | None,
    *,
    logger: CliLogger,
    door: str = "step export",
    verb: str = "exporting",
) -> tuple[EntrySpec, Path | None, LoadedStepScene | None]:
    """Resolve what a mesh export tessellates from: ``(spec, package_dir, scene)``.

    A CURRENT model resolves to its store render package — no generator run, no
    STEP load, no extraction; the package already holds the exact surf geometry
    the exporter consumes. An imported model can only miss (content-hash keying
    cannot go stale), and a miss builds the shared store package via the
    ``cadgen step build`` path. Only a STALE generated model still pays for source:
    its generator runs in-memory and the scene comes back for a one-shot
    temporary package (``package_dir`` None)."""
    if source_path is not None:
        source = source_from_path(source_path)
        if source is None:
            raise RuntimeError(f"Python generator is not a @step CAD source: {source_path}")
        spec = _entry_spec_from_source(source)
        if spec.step_path is None:
            raise RuntimeError(f"Generator defines no STEP output: {source_path}")
        if step_path is not None and spec.step_path.resolve() != step_path.resolve():
            spec = replace(
                spec,
                cad_ref=_cad_ref_for_step(repo_root, step_path),
                display_name=step_path.stem,
                step_path=step_path,
            )
        package_dir = _current_store_package(spec)
        if package_dir is not None:
            logger.debug(f"reusing current render package: {package_dir.name}")
            return spec, package_dir, None
        # No tree for the document's bytes: a door never runs the script. The
        # document on disk is compiled from its bytes, like an import (a job in
        # the pool), and the door reads that tree.
        if spec.step_path.is_file():
            return spec, _view_for_document(spec.step_path), None
        # No document at all: a caller handed the SCRIPT (the export ABI); there is
        # nothing to read, so the generator runs, saying so. See _resolve_spec_and_scene
        # on intent: an export must not report as a build.
        from cadgen._internal.doors import announce_rebuild

        announce_rebuild(
            door, spec.step_path, reason="no document on disk",
            source=spec.script_path or source_path, verb=verb,
        )
        scene = run_script_generator(spec, "step", logger=logger, force=True, intent="generate")
        if scene is None:
            raise RuntimeError(f"Generator did not produce a STEP scene: {spec.source_ref}")
        return spec, None, scene

    if step_path is None:
        raise ValueError("step_path is required for imported STEP/STP models")
    if not step_path.is_file():
        raise FileNotFoundError(f"STEP file does not exist: {step_path}")
    from cadgen.step_artifact_cli import _relative_to_base

    spec = EntrySpec(
        source_ref=_relative_to_base(repo_root, step_path),
        cad_ref=_cad_ref_for_step(repo_root, step_path),
        kind="part",
        source_path=step_path,
        display_name=step_path.stem,
        source="imported",
        step_path=step_path,
    )
    package_dir = _view_for_document(step_path)
    return spec, package_dir, None


def _export_mesh_jobs(
    spec: EntrySpec,
    package_dir: Path | None,
    scene: LoadedStepScene | None,
    jobs: "list[MeshExportJob]",
    *,
    logger: CliLogger,
    force: bool = False,
) -> "frozenset[Path]":
    """Export every requested mesh job from ONE package: the store package
    when the model resolved current, else a one-shot temp package extracted
    from the scene. OCCT meshes nothing on either path (the GLB is Y-up glTF
    for external tools: (x, y, z) -> (x, z, -y), mm -> m).

    Jobs against a STORE package are gated and recorded in the shared
    mesh-export ledger — the same one `@stl`/`@glb`/`@threemf` script runs
    read — so the two front doors never redo each other's work. ``force``
    ignores that gate and re-exports; it never rebuilds the MODEL, which is
    `step build`'s job (design/format-doors.md, decision 5).

    RETURNS the outputs this call actually wrote, so a caller can report which
    of its jobs the ledger had already satisfied."""
    name = spec.step_path.stem
    default_color = _color_hex(spec.color)
    if package_dir is not None:
        from cadgen.catalog import artifact_file_hash

        document_hash = (
            artifact_file_hash(spec.entry_path) if spec.entry_path is not None else None
        )
        if spec.source == "generated" and spec.script_path is not None:
            model = spec.script_path
        else:
            # A document at a bare door: the store remembers which script wrote
            # it (a generated document) or it is its own source (an import).
            from cadgen.store.records import source_for_document

            model = source_for_document(spec.entry_path) if spec.entry_path is not None else None
        pending = [
            job
            for job in jobs
            if force
            or model is None
            or not mesh_export_current(
                job.out,
                model=model,
                document_hash=document_hash,
                mesh_tolerance=job.mesh_tolerance,
                mesh_angular_tolerance=job.mesh_angular_tolerance,
                pose_values=job.pose_values,
            )
        ]
        if not pending:
            return frozenset()
        for job in pending:
            job.out.parent.mkdir(parents=True, exist_ok=True)
        run_mesh_exporter(
            package_dir, pending, name=name, default_color=default_color, logger=logger
        )
        if document_hash and model is not None:
            for job in pending:
                record_mesh_export(
                    job.out,
                    model=model,
                    document_hash=document_hash,
                    fmt=job.fmt,
                    mesh_tolerance=job.mesh_tolerance,
                    mesh_angular_tolerance=job.mesh_angular_tolerance,
                    pose_values=job.pose_values,
                )
        return frozenset(job.out for job in pending)
    import tempfile

    if scene is None:
        raise RuntimeError(f"no render package and no scene to extract for {name}")
    for job in jobs:
        job.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cadgen-mesh-export-") as tmp:
        temp_package = Path(tmp) / "package"
        _build_export_package_from_scene(spec, scene, temp_package, logger=logger)
        run_mesh_exporter(
            temp_package, jobs, name=name, default_color=default_color, logger=logger
        )
    # A one-shot package has no document identity to key a ledger record on, so
    # nothing here is gated and everything is written.
    return frozenset(job.out for job in jobs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m cadgen.step_export_target",
        description="Export one CAD model to STEP/3MF/STL/GLB at an explicit destination path.",
    )
    parser.add_argument("--repo-root", required=True, help="Repository/workspace root for relative metadata.")
    parser.add_argument("--step", required=True, help="Logical STEP path (generated) or on-disk STEP/STP (imported).")
    parser.add_argument("--source-path", help="Python @step model script for a generated model.")
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
    source_path: Path | None = None,
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
    source_path = Path(source_path).expanduser().resolve() if source_path else None
    out = Path(out).expanduser().resolve()
    mesh_tolerance = normalize_mesh_numeric(mesh_tolerance, field_name="mesh_tolerance")
    mesh_angular_tolerance = normalize_mesh_numeric(mesh_angular_tolerance, field_name="mesh_angular_tolerance")
    if fmt in MESH_EXPORT_FORMATS:
        spec, package_dir, scene = _resolve_mesh_package(
            repo_root, step_path, source_path, logger=logger,
            door="step export", verb=f"exporting {fmt}",
        )
        chord, angle = _effective_export_tolerances(
            spec,
            fmt,
            cli_mesh_tolerance=mesh_tolerance,
            cli_mesh_angular_tolerance=mesh_angular_tolerance,
        )
        _export_mesh_jobs(
            spec,
            package_dir,
            scene,
            [MeshExportJob(fmt=fmt, out=out, mesh_tolerance=chord, mesh_angular_tolerance=angle)],
            logger=logger,
        )
        return {"ok": True, "path": str(out), "filename": out.name, "format": fmt}
    spec, scene, from_source = _resolve_spec_and_scene(
        repo_root,
        step_path,
        source_path,
        mesh_tolerance=mesh_tolerance,
        mesh_angular_tolerance=mesh_angular_tolerance,
        logger=logger,
        door="step export",
        verb=f"exporting {fmt}",
    )
    written = _export_scene(
        fmt,
        spec,
        scene,
        out,
        mesh_tolerance=mesh_tolerance,
        mesh_angular_tolerance=mesh_angular_tolerance,
        logger=logger,
        from_current_document=not from_source,
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
    declaration (``@stl(out=...)``), which is script-anchored, written into the
    sidecar's ``meshExports`` and re-read relative to the document — that path
    is reached through ``spec.mesh_exports`` above and is untouched here."""
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


def _sidecar_declarations(step_path: Path, fmt: str) -> "tuple":
    """The document's declared variants of ``fmt``, from its sidecar.

    DOCUMENTS-ONLY: a door never imports a model module and never reads the
    Python registry. What the model declared was recorded into the sidecar's
    ``meshExports`` section by the script run that wrote the document, so the
    door reads a file (design/pose-animation-split.md, CLI/doors follow-on).
    """
    from cadgen._internal.source_sidecar import sidecar_mesh_exports

    return tuple(entry for entry in sidecar_mesh_exports(step_path) if entry.fmt == fmt)


def _no_declarations_error(step_path: Path, fmt: str) -> ValueError:
    decorator = {"stl": "@stl", "3mf": "@threemf", "glb": "@glb"}[fmt]
    return ValueError(
        f"{step_path.name} declares no {fmt.upper()} exports: declare "
        f"{decorator} on the model and run python <script>, or name an "
        f"explicit OUT"
    )


def _bake_point_values(
    kinematics: object, step_path: Path, *, where: str
) -> "dict[str, float] | None":
    """An ad-hoc ``kinematics=`` bake point, resolved against the DOCUMENT.

    The point is a preset NAME or a ``{dof: value}`` mapping — the same two
    spellings snapshot's ``--kinematics`` takes — and it is validated against
    the kinematics block in the document's own sidecar, which is the only
    declaration a door can see.
    """
    if kinematics is None:
        return None
    from cadgen._internal.source_sidecar import read_source_sidecar
    from cadgen.kinematics import resolve_kinematics_at

    block = (read_source_sidecar(step_path) or {}).get("kinematics")
    if not isinstance(block, dict) or not block.get("mates"):
        raise ValueError(
            f"{step_path.name} declares no kinematics, so there is no bake point "
            "to name: declare kinematics= on the model and run python <script>"
        )
    point: object = kinematics
    if isinstance(point, str):
        text = point.strip()
        if text.startswith("{"):
            point = json.loads(text)
        elif not text:
            return None
    return resolve_kinematics_at(block, point, where=where)


def _sidecar_pose_deltas(
    pose_values: "dict[str, float]", *, step_path: Path, package_dir: Path | None
) -> "dict[str, list[float]] | None":
    """FK deltas for a bake point, evaluated from the SIDECAR's block.

    The sidecar's mates are already axis-resolved (world numbers) and carry the
    ``parentId``/``childId`` the subtree expansion needs, so a door evaluates
    forward kinematics with no selector index and no OCCT at all.
    """
    if not pose_values or package_dir is None:
        return None
    from cadgen._internal.kinematics_resolve import resolved_block_pose_deltas
    from cadgen._internal.source_sidecar import read_source_sidecar

    block = (read_source_sidecar(step_path) or {}).get("kinematics")
    if not isinstance(block, dict):
        return None
    return resolved_block_pose_deltas(block, pose_values, package_dir=package_dir)


def export_cad_target(
    target: str | Path,
    outputs: "list[tuple[str, str | Path | None]]",
    *,
    repo_root: Path | None = None,
    kinematics: object = None,
    mesh_tolerance: float | None = None,
    mesh_angular_tolerance: float | None = None,
    force: bool = False,
    verbose: bool = False,
    logger: CliLogger | None = None,
) -> dict[str, object]:
    """Export one CAD DOCUMENT to one or more of :data:`MESH_EXPORT_FORMATS`
    in a single run.

    The shared engine entry behind the per-format doors (``cadgen.stl.build`` and
    friends). Geometry comes from the document's store render package — no generator
    run, no source, no extraction — and one Node invocation serializes every requested
    format from one tessellation, so all formats come from identical geometry.
    ``outputs`` pairs a format name with an explicit output path, or ``None`` for the
    DOCUMENT's declarations (all variants, read from its sidecar). ``kinematics`` is an
    ad-hoc bake point for an explicit OUT, resolved against the document's own
    kinematics block. ``force`` re-exports past the ledger.

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

    spec, package_dir, scene = _resolve_mesh_package(
        repo_root,
        step_path,
        None,
        logger=logger,
    )

    resolved: list[MeshExportJob] = []
    seen: dict[Path, str] = {}
    ad_hoc_pose = _bake_point_values(kinematics, step_path, where="kinematics=")

    def _add(
        fmt: str,
        out: Path,
        chord: float | None,
        angle: float | None,
        pose_values: "dict[str, float] | None" = None,
    ) -> None:
        if out in seen:
            raise ValueError(f"{seen[out]} and {fmt} resolve to the same output path: {out}")
        seen[out] = fmt
        pose_deltas = (
            _sidecar_pose_deltas(pose_values, step_path=step_path, package_dir=package_dir)
            if pose_values
            else None
        )
        resolved.append(
            MeshExportJob(
                fmt=fmt,
                out=out,
                mesh_tolerance=chord,
                mesh_angular_tolerance=angle,
                pose_deltas=pose_deltas,
                pose_values=pose_values,
            )
        )

    for fmt, raw in outputs:
        if raw is None:
            # A bare door means the DOCUMENT's declarations — ALL variants of
            # this format, exactly as the script run produced them, read from
            # the sidecar. Run-level tolerance arguments override each
            # variant's own.
            declared = _sidecar_declarations(step_path, fmt)
            if not declared:
                raise _no_declarations_error(step_path, fmt)
            for decl in declared:
                chord = mesh_tolerance if mesh_tolerance is not None else decl.mesh_tolerance
                angle = (
                    mesh_angular_tolerance
                    if mesh_angular_tolerance is not None
                    else decl.mesh_angular_tolerance
                )
                _add(fmt, decl.path, chord, angle, decl.at)
            continue
        out = _resolve_export_output(fmt, raw, logical_step=spec.step_path, spec=spec)
        chord, angle = _effective_export_tolerances(
            spec,
            fmt,
            cli_mesh_tolerance=mesh_tolerance,
            cli_mesh_angular_tolerance=mesh_angular_tolerance,
        )
        _add(fmt, out, chord, angle, ad_hoc_pose)

    written = _export_mesh_jobs(spec, package_dir, scene, resolved, logger=logger, force=force)
    files = [
        {
            "format": job.fmt,
            "path": str(job.out),
            "skipped": job.out not in written,
            "meshTolerance": job.mesh_tolerance,
            "meshAngularTolerance": job.mesh_angular_tolerance,
        }
        for job in resolved
    ]
    logger.total()
    return {"ok": True, "files": files}


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
        source_path=Path(args.source_path) if args.source_path else None,
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
