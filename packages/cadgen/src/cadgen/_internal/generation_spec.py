from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import replace
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
from cadgen.catalog import find_source_by_path
from cadgen.catalog import iter_cad_sources
from cadgen.catalog import normalize_cad_ref
from cadgen.catalog import normalize_source_ref
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
    # False for a mesh-only model: ``step_path`` stays the LOGICAL document the
    # store keys by, but it is never written and is not among the outputs.
    step_output: bool = True

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
    (a re-emitted document: ``cadgen step build IN OUT`` sets ``step_export_path``;
    a model's own ``out=`` is its document, not an extra). Such an output must be produced
    even when the compose is current, so it defeats every no-op and reuse fast
    path."""
    return spec.step_export_path is not None


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
        step_output=bool(getattr(generator_metadata, "step_output", True)),
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


