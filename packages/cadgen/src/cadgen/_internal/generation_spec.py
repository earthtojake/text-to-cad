from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import replace
import os
from pathlib import Path
from typing import Sequence

from cadgen._internal.glb_topology import STEP_EDGE_VISIBILITY_CLASSES
from cadgen._internal.glb_topology import normalize_step_edge_render_visibility_classes
from cadgen._internal.step_scene import LoadedStepScene
from cadgen._internal.step_scene import SelectorBundle
from cadgen._internal.step_scene import SelectorOptions
from cadgen._internal.step_scene import adaptive_mesh_resolution_for_scene
from cadgen.catalog import CadSource
from cadgen.catalog import StepImportOptions
from cadgen.catalog import cad_ref_from_dxf_path
from cadgen.catalog import cad_ref_from_step_path
from cadgen.catalog import find_source_by_path
from cadgen.catalog import iter_cad_sources
from cadgen.catalog import normalize_cad_ref
from cadgen.catalog import normalize_source_ref
from cadgen.catalog import render_package_dir
from cadgen.cli_logging import CliLogger
from cadgen.cli_progress import cli_progress_line
from cadgen.metadata import GeneratorMetadata
from cadgen.render import relative_to_cwd



@dataclass(frozen=True)
class EntrySpec:
    source_ref: str
    cad_ref: str
    kind: str
    source_path: Path
    display_name: str
    source: str
    step_path: Path | None = None
    script_path: Path | None = None
    generator_metadata: GeneratorMetadata | None = None
    dxf_path: Path | None = None
    step_export_path: Path | None = None
    dxf_export_path: Path | None = None
    # ``None`` means "the caller specified nothing" — the adaptive resolver
    # supplies the value. A number is the caller's explicit choice, and
    # ``is not None`` IS the explicitness test; there is no separate flag and
    # no default sentinel to compare against.
    mesh_tolerance: float | None = None
    mesh_angular_tolerance: float | None = None
    color: tuple[float, float, float, float] | None = None
    # Declared mesh serializations, resolved to absolute paths. Tolerances
    # ``None`` inherit the model's policy at export time.
    mesh_exports: "tuple[ResolvedMeshExport, ...]" = ()

    @property
    def entry_path(self) -> Path | None:
        # The on-disk file the render package is keyed by. Library-first models
        # (design/library-first-generation.md) key by the ARTIFACT: the package
        # must ride beside the .step wherever out= routed it,
        # so the viewer (artifacts-only catalog) finds it, and so provenance —
        # not filenames — links artifact to source. Imported STEP entries and
        # DXF drawings keep their own keying.
        if (
            self.generator_metadata is not None
            and getattr(self.generator_metadata, "is_decorated", False)
            and self.step_path is not None
        ):
            return self.step_path
        return self.script_path if self.script_path is not None else self.step_path


@dataclass(frozen=True)
class ResolvedMeshExport:
    """One declared mesh export with its destination resolved: `@stl` and
    friends carry script-relative ``out=`` targets (or None for the sibling
    of the logical STEP artifact); the spec carries the final answer."""

    fmt: str
    path: Path
    mesh_tolerance: float | None = None
    mesh_angular_tolerance: float | None = None


def _resolve_mesh_exports(
    declarations,
    *,
    script_path: Path | None,
    step_path: Path | None,
) -> "tuple[ResolvedMeshExport, ...]":
    from cadgen.metadata import resolve_model_output_path
    from cadgen._internal.mesh_export import MESH_FORMAT_SUFFIX

    if not declarations or step_path is None:
        return ()
    resolved: list[ResolvedMeshExport] = []
    for decl in declarations:
        suffix = MESH_FORMAT_SUFFIX[decl.fmt]
        if decl.out is not None and script_path is not None:
            path = resolve_model_output_path(
                script_path, fmt=decl.fmt, explicit_out=decl.out
            )
        else:
            # Bare declaration: sibling of the STEP artifact, wherever out=
            # routed it — exports follow the artifact they derive from.
            path = step_path.with_suffix(suffix)
        resolved.append(
            ResolvedMeshExport(
                fmt=decl.fmt,
                path=path.expanduser().resolve(),
                mesh_tolerance=decl.mesh_tolerance,
                mesh_angular_tolerance=decl.mesh_angular_tolerance,
            )
        )
    seen_paths: set[Path] = set()
    for export in resolved:
        if export.path in seen_paths:
            raise ValueError(
                f"two mesh export declarations resolve to the same target: {export.path}"
            )
        seen_paths.add(export.path)
    return tuple(resolved)


@dataclass
class GeneratedStepResult:
    spec: EntrySpec
    scene: LoadedStepScene | None
    selector_bundle: SelectorBundle | None = None


@dataclass(frozen=True)
class _CliTargetSpec:
    target: str
    output_path: Path | None = None


def _cli_progress_line(
    spec: EntrySpec,
    *,
    logger: CliLogger,
    fallback: str,
) -> "contextlib.AbstractContextManager[Callable[[ProgressEvent], None] | None]":
    """:func:`cli_progress_line` keyed to a spec's source ref."""
    return cli_progress_line(spec.source_ref, logger=logger, fallback=fallback)


def _display_name_for_path(path: Path) -> str:
    return path.stem


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _resolve_cli_output_path(
    raw_output: str | Path | None,
    *,
    expected_suffixes: tuple[str, ...],
    tool_name: str,
    option_label: str = "--output",
) -> Path | None:
    if raw_output is None:
        return None
    value = str(raw_output).strip()
    if not value:
        raise ValueError(f"{tool_name} {option_label} must be a non-empty path")
    # A backslash is the native separator on Windows and a legal FILENAME character on POSIX,
    # so this guard has to be platform-specific. On POSIX it catches a Windows-shaped path
    # typed on the wrong machine, which would otherwise silently create a file named
    # ``C:\out.step`` in the working directory. On Windows it must not fire at all: this is a
    # path the user typed for their own filesystem, and ``str(Path(...))`` produces
    # backslashes there, so the absolute rule rejected EVERY native path given to --output or
    # to a SOURCE=OUTPUT target.
    #
    # The same wording in ``cadgen.metadata`` is absolute on purpose and must stay that way:
    # that one validates the ``out=`` path written into a checked-in ``@step`` decorator, which is
    # read on every platform, so POSIX separators are the portable form there. One rule is
    # about a user's disk, the other about a file in the repository.
    if os.name != "nt" and "\\" in value:
        raise ValueError(f"{tool_name} {option_label} must use POSIX '/' separators")
    output_path = Path(value).expanduser()
    resolved = output_path.resolve() if output_path.is_absolute() else (Path.cwd() / output_path).resolve()
    if resolved.suffix.lower() not in expected_suffixes:
        joined = " or ".join(expected_suffixes)
        raise ValueError(f"{tool_name} {option_label} must end in {joined}")
    return resolved


def targets_include_output_pairs(targets: Sequence[str]) -> bool:
    return any("=" in str(target or "") for target in targets)


def _parse_cli_target_specs(
    targets: Sequence[str],
    *,
    expected_suffixes: tuple[str, ...],
    tool_name: str,
) -> list[_CliTargetSpec]:
    specs: list[_CliTargetSpec] = []
    for target in targets:
        target_text = str(target or "").strip()
        if "=" not in target_text:
            specs.append(_CliTargetSpec(target=target_text))
            continue
        raw_source, raw_output = target_text.split("=", 1)
        source = raw_source.strip()
        if not source:
            raise ValueError(f"{tool_name} output pair must use SOURCE=OUTPUT")
        output_path = _resolve_cli_output_path(
            raw_output,
            expected_suffixes=expected_suffixes,
            tool_name=tool_name,
            option_label="output pair",
        )
        if output_path is None:
            raise ValueError(f"{tool_name} output pair must use SOURCE=OUTPUT")
        specs.append(_CliTargetSpec(target=source, output_path=output_path))
    return specs


def _apply_step_options_to_spec(spec: EntrySpec, step_options: StepImportOptions) -> EntrySpec:
    if not step_options.has_metadata or spec.step_path is None:
        return spec
    return replace(
        spec,
        mesh_tolerance=step_options.mesh_tolerance if step_options.mesh_tolerance is not None else spec.mesh_tolerance,
        mesh_angular_tolerance=(
            step_options.mesh_angular_tolerance
            if step_options.mesh_angular_tolerance is not None
            else spec.mesh_angular_tolerance
        ),
    )


def _spec_requests_extra_outputs(spec: EntrySpec) -> bool:
    """True when the target asks for an on-demand output beyond the render package
    (an explicit ``out=`` on the model). An explicitly requested output must be produced
    even when the compose is current, so it defeats every no-op and reuse fast
    path."""
    return spec.step_export_path is not None


def _spec_output_paths(spec: EntrySpec) -> tuple[Path, ...]:
    paths: list[Path] = []
    if spec.step_path is not None:
        paths.append(spec.step_path)
        paths.append(render_package_dir(spec.entry_path))
    for path in (spec.dxf_path,):
        if path is not None:
            paths.append(path)
    return tuple(path.resolve() for path in paths)


def _validate_cli_output_override(
    spec: EntrySpec,
    *,
    output_path: Path,
    all_specs: Sequence[EntrySpec],
    tool_name: str,
) -> None:
    resolved_output = output_path.resolve()
    for candidate in all_specs:
        if candidate.source_ref == spec.source_ref:
            continue
        if resolved_output in _spec_output_paths(candidate):
            raise ValueError(
                f"{tool_name} --output would overwrite another CAD output: "
                f"{_display_path(output_path)} belongs to {candidate.source_ref}"
            )


def _validate_duplicate_cli_output_overrides(
    output_paths: Sequence[Path | None],
    *,
    tool_name: str,
) -> None:
    seen: dict[Path, Path] = {}
    for output_path in output_paths:
        if output_path is None:
            continue
        resolved = output_path.resolve()
        previous = seen.get(resolved)
        if previous is not None:
            raise ValueError(f"{tool_name} output path is used more than once: {_display_path(output_path)}")
        seen[resolved] = output_path


def _apply_step_output_overrides(
    selected_specs: Sequence[EntrySpec],
    *,
    output_paths: Sequence[Path | None],
    all_specs: Sequence[EntrySpec],
    tool_name: str,
) -> list[EntrySpec]:
    if not any(output_path is not None for output_path in output_paths):
        return list(selected_specs)
    if len(output_paths) != len(selected_specs):
        raise ValueError(f"{tool_name} output override count must match target count")
    _validate_duplicate_cli_output_overrides(output_paths, tool_name=tool_name)
    updated_specs: list[EntrySpec] = []
    for spec, output_path in zip(selected_specs, output_paths, strict=True):
        if output_path is None:
            updated_specs.append(spec)
            continue
        if spec.source != "generated":
            raise ValueError(f"{tool_name} output pairs can only be used with generated Python targets")
        _validate_cli_output_override(spec, output_path=output_path, all_specs=all_specs, tool_name=tool_name)
        updated_specs.append(
            replace(
                spec,
                cad_ref=cad_ref_from_step_path(output_path),
                display_name=_display_name_for_path(output_path),
                step_path=output_path,
                # A STEP output path is now a STEP *export* request (@step writes no STEP
                # by default): write it on demand to the requested path.
                step_export_path=output_path,
            )
        )
    return updated_specs


def _apply_dxf_output_overrides(
    selected_specs: Sequence[EntrySpec],
    *,
    output_paths: Sequence[Path | None],
    all_specs: Sequence[EntrySpec],
    tool_name: str,
) -> list[EntrySpec]:
    if not any(output_path is not None for output_path in output_paths):
        return list(selected_specs)
    if len(output_paths) != len(selected_specs):
        raise ValueError(f"{tool_name} output override count must match target count")
    _validate_duplicate_cli_output_overrides(output_paths, tool_name=tool_name)
    updated_specs: list[EntrySpec] = []
    for spec, output_path in zip(selected_specs, output_paths, strict=True):
        if output_path is None:
            updated_specs.append(spec)
            continue
        if spec.source != "generated":
            raise ValueError(f"{tool_name} output pairs can only be used with generated Python targets")
        _validate_cli_output_override(spec, output_path=output_path, all_specs=all_specs, tool_name=tool_name)
        updated_specs.append(
            replace(
                spec,
                cad_ref=cad_ref_from_dxf_path(output_path),
                display_name=_display_name_for_path(output_path),
                # A DXF output path is a DXF *export* request (@dxf builds the drawing
                # package by default): write it on demand to the requested path.
                dxf_path=output_path,
                dxf_export_path=output_path,
            )
        )
    return updated_specs


def _apply_dxf_output_override(
    selected_specs: Sequence[EntrySpec],
    *,
    output_path: Path | None,
    all_specs: Sequence[EntrySpec],
    tool_name: str,
) -> list[EntrySpec]:
    if output_path is None:
        return list(selected_specs)
    if len(selected_specs) != 1:
        raise ValueError(f"{tool_name} --output can only be used with exactly one target")
    spec = selected_specs[0]
    if spec.source != "generated":
        raise ValueError(f"{tool_name} --output can only be used with generated Python targets")
    return _apply_dxf_output_overrides(
        selected_specs,
        output_paths=[output_path],
        all_specs=all_specs,
        tool_name=tool_name,
    )


def _resolve_discovery_root(root: Path | str) -> Path:
    candidate = Path(root)
    resolved = candidate.resolve() if candidate.is_absolute() else (Path.cwd() / candidate).resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"CAD discovery directory does not exist: {relative_to_cwd(resolved)}")
    if not resolved.is_dir():
        raise NotADirectoryError(f"CAD discovery path is not a directory: {relative_to_cwd(resolved)}")
    return resolved


def list_entry_specs(root: Path | None = None) -> list[EntrySpec]:
    root = Path.cwd().resolve() if root is None else root
    specs = [_entry_spec_from_source(source) for source in iter_cad_sources(_resolve_discovery_root(root))]
    return sorted(specs, key=lambda spec: spec.source_ref)


def _entry_spec_from_source(source: CadSource) -> EntrySpec:
    generator_metadata = source.generator_metadata
    script_path = source.script_path
    kind = source.kind
    step_path = source.step_path
    display_path = step_path if step_path is not None else source.source_path

    return EntrySpec(
        source_ref=source.source_ref,
        cad_ref=source.cad_ref,
        kind=kind,
        source_path=source.source_path,
        display_name=(
            generator_metadata.display_name
            if generator_metadata is not None and generator_metadata.display_name
            else _display_name_for_path(display_path)
        ),
        source=source.source,
        step_path=step_path,
        script_path=script_path,
        generator_metadata=generator_metadata,
        dxf_path=source.dxf_path,
        mesh_tolerance=source.mesh_tolerance,
        mesh_angular_tolerance=source.mesh_angular_tolerance,
        color=source.color,
        mesh_exports=_resolve_mesh_exports(
            getattr(generator_metadata, "mesh_exports", ()) or (),
            script_path=script_path,
            step_path=step_path,
        ),
    )


def selected_entry_specs(all_specs: Sequence[EntrySpec], source_refs: Sequence[str]) -> list[EntrySpec]:
    if not source_refs:
        raise ValueError("At least one CAD target is required")
    by_source = {spec.source_ref: spec for spec in all_specs}
    by_cad_ref = {spec.cad_ref: spec for spec in all_specs}
    by_step_path = {
        spec.step_path.resolve(): spec
        for spec in all_specs
        if spec.step_path is not None
    }
    selected: list[EntrySpec] = []
    for source_ref in source_refs:
        spec = _spec_for_source_ref(source_ref, by_source=by_source, by_cad_ref=by_cad_ref, by_step_path=by_step_path)
        if spec is None:
            raise FileNotFoundError(f"CAD source not found: {source_ref}")
        selected.append(spec)
    return selected


def _spec_for_source_ref(
    raw_ref: str,
    *,
    by_source: dict[str, EntrySpec],
    by_cad_ref: dict[str, EntrySpec],
    by_step_path: dict[Path, EntrySpec],
) -> EntrySpec | None:
    source_ref = normalize_source_ref(raw_ref)
    if source_ref and source_ref in by_source:
        return by_source[source_ref]
    cad_ref = normalize_cad_ref(raw_ref)
    if cad_ref and cad_ref in by_cad_ref:
        return by_cad_ref[cad_ref]
    candidate = Path(str(raw_ref or "").strip())
    if candidate:
        resolved = candidate.resolve() if candidate.is_absolute() else (
            Path.cwd() / candidate
        )
        resolved = resolved.resolve()
        if resolved in by_step_path:
            return by_step_path[resolved]
        source = find_source_by_path(resolved)
        if source is not None:
            return by_source.get(source.source_ref)
    return None


def _selector_options_for_part(spec: EntrySpec, *, scene: LoadedStepScene | None = None) -> SelectorOptions:
    """The render options a build extracts topology with.

    Only the edge-visibility class set varies, and it varies with the SCENE:
    the adaptive resolver classifies the topology and
    ``_edge_visibility_classes_for_resolution`` turns that classification into
    the classes. Without a scene there is nothing to classify, so the default
    set stands. Mesh tolerances are absent on purpose — ``--mesh-tolerance``
    reaches the mesh EXPORT jobs (``MeshExportJob``), which have their own
    content gate; a render package is tessellation-free.
    """
    edge_visibility_classes = normalize_step_edge_render_visibility_classes(None)
    if isinstance(scene, LoadedStepScene):
        adaptive = adaptive_mesh_resolution_for_scene(scene)
        edge_visibility_classes = _edge_visibility_classes_for_resolution(adaptive.profile, adaptive.hints)
    return SelectorOptions(edge_visibility_classes=edge_visibility_classes)


def _edge_visibility_classes_for_resolution(profile: str, hints: Mapping[str, object] | None) -> tuple[str, ...]:
    normalized_profile = str(profile or "").strip().lower()
    hint_values = hints if isinstance(hints, Mapping) else {}
    occurrence_edge_count = _hint_int(hint_values.get("occurrenceEdgeCount"))
    feature_only = (
        normalized_profile in {"large-topology", "coarse-assembly"}
        or occurrence_edge_count >= 8000
    )
    if feature_only:
        return (STEP_EDGE_VISIBILITY_CLASSES["FEATURE"],)
    return normalize_step_edge_render_visibility_classes(None)


def _hint_float(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _hint_int(value: object) -> int:
    return int(_hint_float(value))


