from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cadgen._internal.glb_topology import normalize_step_edge_render_visibility_classes
from cadgen._internal.step_scene import LoadedStepScene
from cadgen._internal.step_scene import SelectorOptions
from cadgen.catalog import CadSource
from cadgen.cli_logging import CliLogger
from cadgen.cli_progress import cli_progress_line
from cadgen.metadata import GeneratorMetadata
from cadgen.render import relative_to_cwd


@dataclass(frozen=True)
class EntrySpec:
    source_ref: str
    cad_ref: str
    source_path: Path
    display_name: str
    source: str
    step_path: Path | None = None
    script_path: Path | None = None
    generator_metadata: GeneratorMetadata | None = None
    dxf_path: Path | None = None
    # Declared mesh serializations, resolved to absolute paths. A tolerance
    # ``None`` is the display tolerance.
    mesh_exports: "tuple[ResolvedMeshExport, ...]" = ()
    # False for a mesh-only model: ``step_path`` stays the LOGICAL document the
    # store keys by, but it is never written and is not among the outputs.
    step_output: bool = True

    @property
    def entry_path(self) -> Path | None:
        # The on-disk file the tree is keyed by. Library-first models key by the
        # ARTIFACT: the tree must ride beside the .step wherever out= routed it,
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
    tree: str | None = None
    # The key the result is stored under (store/results.py): the record's.
    key: str | None = None


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


# ONE cwd-relative display helper (cadgen.render); the name is what this
# pipeline's modules import.
_display_path = relative_to_cwd


def _entry_spec_from_source(source: CadSource) -> EntrySpec:
    generator_metadata = source.generator_metadata
    script_path = source.script_path
    step_path = source.step_path
    display_path = step_path if step_path is not None else source.source_path

    return EntrySpec(
        source_ref=source.source_ref,
        cad_ref=source.cad_ref,
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
        mesh_exports=_resolve_mesh_exports(
            getattr(generator_metadata, "mesh_exports", ()) or (),
            script_path=script_path,
            step_path=step_path,
        ),
        step_output=bool(getattr(generator_metadata, "step_output", True)),
    )


def _selector_options_for_part(spec: EntrySpec) -> SelectorOptions:
    """The render options a compiled document's tree is read with: the default edge
    classes, which ``store.build.build_document_tree`` fixes for every compile. A
    result's tree classifies its own edges from the topology it is built from
    (``store.build``). Mesh tolerances are absent on purpose: a declared export's
    reach its EXPORT job (``MeshExportJob``), which has its own content gate; a
    tree is tessellation-free."""
    del spec
    return SelectorOptions(edge_visibility_classes=normalize_step_edge_render_visibility_classes(None))
