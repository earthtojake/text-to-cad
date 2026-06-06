from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cadpy.assembly_spec import REPO_ROOT, find_step_path, resolve_cad_source_path
from cadpy.cad_ref_syntax import normalize_cad_path, parse_cad_tokens
from cadpy.catalog import find_source_by_cad_ref
from cadpy.glb_topology import (
    STEP_EDGE_BARYCENTRIC_ATTRIBUTE,
    STEP_EDGE_CLASS_ATTRIBUTE,
    STEP_EDGE_VISIBILITY_CLASSES,
    STEP_TOPOLOGY_SCHEMA_VERSION,
    glb_primitives_have_surface_edge_attributes,
    glb_surface_edge_class_has_nonzero_values,
    normalize_step_edge_render_visibility_classes,
    read_step_display_edge_manifest_from_glb,
    read_step_topology_bundle_from_glb,
    read_step_topology_manifest_from_glb,
)
from cadpy.render import existing_part_glb_path, part_glb_path
from cadpy.selector_types import SelectorBundle
from cadpy.step_hash import step_file_hash


STEP_SUFFIXES = (".step", ".stp")
REGENERATE_STEP_COMMAND = "python scripts/step"
REGENERATE_STEP_PROMPT = "Regenerate STEP artifacts with the following command using the CAD skill:"


class CadRefError(RuntimeError):
    pass


@dataclass(frozen=True)
class EntryTarget:
    cad_path: str
    selectors: tuple[str, ...] = ()

    @property
    def token(self) -> str:
        from cadpy.cad_ref_syntax import build_cad_token

        if not self.selectors:
            return build_cad_token(self.cad_path)
        return build_cad_token(self.cad_path, ",".join(self.selectors))


@dataclass(frozen=True)
class ResolvedStepTarget:
    cad_path: str
    kind: str
    source_path: Path
    step_path: Path


@dataclass(frozen=True)
class StepTopologyArtifact:
    cad_path: str
    kind: str
    source_path: Path
    step_path: Path
    glb_path: Path
    manifest: dict[str, object]
    selector_bundle: SelectorBundle | None = None


class StepTopologyArtifactError(CadRefError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        cad_path: str,
        step_path: Path,
        glb_path: Path,
        regenerate_command: str,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.cad_path = cad_path
        self.step_path = step_path
        self.glb_path = glb_path
        self.regenerate_command = regenerate_command

    def to_error(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": str(self),
            "cadPath": self.cad_path,
            "stepPath": _relative_to_repo(self.step_path),
            "glbPath": _relative_to_repo(self.glb_path),
            "regenerateCommand": self.regenerate_command,
        }


def cad_ref_error_payload(exc: CadRefError) -> dict[str, object]:
    if isinstance(exc, StepTopologyArtifactError):
        return exc.to_error()
    return {"message": str(exc)}


def cad_path_from_target(target: str) -> str:
    return entry_target_from_target(target).cad_path


def entry_target_from_target(target: str) -> EntryTarget:
    parsed_tokens = parse_cad_tokens(target)
    if parsed_tokens:
        raise CadRefError("Selector refs require an explicit STEP target argument.")
    raw_target = str(target or "").strip()
    if _raw_step_path(raw_target) is not None:
        normalized = normalize_cad_path(raw_target)
        if normalized is not None:
            return EntryTarget(normalized)
    normalized = normalize_cad_path(target)
    if normalized is None:
        raise CadRefError(f"Invalid CAD entry target: {target}")
    return EntryTarget(normalized)


def step_path_from_target(target: str) -> Path:
    raw_step_path = _raw_step_path(str(target or "").strip())
    if raw_step_path is not None:
        return raw_step_path

    entry_target = entry_target_from_target(target)
    lookup_cad_path = _lookup_cad_path(entry_target.cad_path)
    step_path = find_step_path(lookup_cad_path)
    if step_path is not None:
        return step_path

    direct_step_path = _direct_step_path(entry_target.cad_path)
    if direct_step_path is not None:
        return direct_step_path

    raise CadRefError(f"STEP file not found for target '{target}'.")


def resolve_step_target(target: str) -> ResolvedStepTarget:
    entry_target = entry_target_from_target(target)
    cad_path = entry_target.cad_path
    raw_step_path = _raw_step_path(str(target or "").strip())
    if raw_step_path is not None:
        lookup_cad_path = _lookup_cad_path(cad_path)
        source = find_source_by_cad_ref(lookup_cad_path)
        resolved_step_path = source.step_path if source is not None else None
        if source is not None and resolved_step_path is not None and resolved_step_path.resolve() == raw_step_path.resolve():
            return ResolvedStepTarget(
                cad_path=cad_path,
                kind=source.kind,
                source_path=source.source_path,
                step_path=raw_step_path,
            )
        return ResolvedStepTarget(
            cad_path=cad_path,
            kind="part",
            source_path=raw_step_path,
            step_path=raw_step_path,
        )

    lookup_cad_path = _lookup_cad_path(cad_path)
    source = find_source_by_cad_ref(lookup_cad_path)
    if source is not None and source.kind in {"part", "assembly"}:
        if source.step_path is None:
            raise CadRefError(f"STEP file not found for ref '{cad_path}'.")
        return ResolvedStepTarget(
            cad_path=cad_path,
            kind=source.kind,
            source_path=source.source_path,
            step_path=source.step_path.resolve(),
        )
    if source is not None:
        raise CadRefError(f"CAD target '{cad_path}' is not STEP-backed.")

    direct_step_path = _direct_step_path(cad_path)
    if direct_step_path is not None:
        return ResolvedStepTarget(
            cad_path=cad_path,
            kind="part",
            source_path=direct_step_path,
            step_path=direct_step_path,
        )

    raise CadRefError(f"CAD STEP ref not found for '{cad_path}'.")


def validate_step_topology_artifact(
    target: ResolvedStepTarget,
    *,
    glb_path: Path | None = None,
    require_selector: bool = False,
) -> StepTopologyArtifact:
    resolved_glb_path = glb_path or existing_part_glb_path(target.step_path) or part_glb_path(target.step_path)
    if not resolved_glb_path.is_file():
        raise _topology_artifact_error(
            code="missing_glb",
            reason="STEP topology validation requires the generated GLB artifact, but it is missing",
            cad_path=target.cad_path,
            kind=target.kind,
            source_path=target.source_path,
            step_path=target.step_path,
            glb_path=resolved_glb_path,
        )

    manifest = read_step_topology_manifest_from_glb(resolved_glb_path)
    if manifest is None:
        raise _topology_artifact_error(
            code="missing_step_topology",
            reason="STEP topology validation requires readable STEP_topology indexView in the GLB",
            cad_path=target.cad_path,
            kind=target.kind,
            source_path=target.source_path,
            step_path=target.step_path,
            glb_path=resolved_glb_path,
        )
    try:
        schema_version = int(manifest.get("schemaVersion") or 0)
    except (TypeError, ValueError):
        schema_version = 0
    if schema_version != STEP_TOPOLOGY_SCHEMA_VERSION:
        raise _topology_artifact_error(
            code="unsupported_step_topology",
            reason=f"STEP topology validation requires STEP_topology schemaVersion {STEP_TOPOLOGY_SCHEMA_VERSION} in the GLB",
            cad_path=target.cad_path,
            kind=target.kind,
            source_path=target.source_path,
            step_path=target.step_path,
            glb_path=resolved_glb_path,
        )
    source_kind = str(manifest.get("sourceKind") or "step").strip().lower()
    manifest_source_path = _source_path_from_manifest(manifest, glb_path=resolved_glb_path)
    if manifest_source_path is None:
        raise _topology_artifact_error(
            code="missing_source_path",
            reason="GLB STEP_topology is missing required sourcePath identity",
            cad_path=target.cad_path,
            kind=target.kind,
            source_path=target.source_path,
            step_path=target.step_path,
            glb_path=resolved_glb_path,
        )
    if source_kind == "python":
        if manifest_source_path.suffix.lower() != ".py":
            raise _topology_artifact_error(
                code="missing_source_path",
                reason="GLB STEP_topology Python sourcePath must point at a Python generator",
                cad_path=target.cad_path,
                kind=target.kind,
                source_path=target.source_path,
                step_path=target.step_path,
                glb_path=resolved_glb_path,
            )
    step_hash = str(manifest.get("stepHash") or "").strip()
    if target.step_path.is_file():
        if not step_hash:
            raise _topology_artifact_error(
                code="missing_step_hash",
                reason="GLB STEP_topology is missing STEP file identity",
                cad_path=target.cad_path,
                kind=target.kind,
                source_path=target.source_path,
                step_path=target.step_path,
                glb_path=resolved_glb_path,
            )
        current_step_hash = step_file_hash(target.step_path)
        if step_hash != current_step_hash:
            raise _topology_artifact_error(
                code="stale_step_artifact",
                reason="Generated GLB doesn't match the hash of the STEP file",
                cad_path=target.cad_path,
                kind=target.kind,
                source_path=target.source_path,
                step_path=target.step_path,
                glb_path=resolved_glb_path,
            )

    edge_manifest = read_step_display_edge_manifest_from_glb(resolved_glb_path)
    if edge_manifest is None:
        raise _topology_artifact_error(
            code="missing_edge_topology",
            reason="STEP topology validation requires readable STEP_topology edgeView in the GLB",
            cad_path=target.cad_path,
            kind=target.kind,
            source_path=target.source_path,
            step_path=target.step_path,
            glb_path=resolved_glb_path,
        )
    try:
        edge_schema_version = int(edge_manifest.get("schemaVersion") or 0)
    except (TypeError, ValueError):
        edge_schema_version = 0
    primitive_attributes = edge_manifest.get("primitiveAttributes")
    edge_rendering = edge_manifest.get("edgeRendering")
    index_edge_rendering = manifest.get("edgeRendering")
    edge_visibility_classes = (
        normalize_step_edge_render_visibility_classes(edge_rendering.get("visibilityClasses"))
        if isinstance(edge_rendering, dict)
        else ()
    )
    index_edge_visibility_classes = (
        normalize_step_edge_render_visibility_classes(index_edge_rendering.get("visibilityClasses"))
        if isinstance(index_edge_rendering, dict)
        else ()
    )
    edge_matches_source = (
        not step_hash
        or str(edge_manifest.get("stepHash") or "").strip() == step_hash
    )
    if (
        edge_schema_version != STEP_TOPOLOGY_SCHEMA_VERSION
        or edge_manifest.get("profile") != "surface-edges"
        or str(edge_manifest.get("sourcePath") or "").strip() != str(manifest.get("sourcePath") or "").strip()
        or not edge_matches_source
        or not edge_visibility_classes
        or edge_visibility_classes != index_edge_visibility_classes
        or STEP_EDGE_VISIBILITY_CLASSES["FEATURE"] not in edge_visibility_classes
        or not isinstance(edge_manifest.get("buffers"), dict)
        or not isinstance(edge_manifest.get("buffers", {}).get("views"), dict)
        or "surfaceHalfEdges" not in edge_manifest.get("buffers", {}).get("views", {})
    ):
        raise _topology_artifact_error(
            code="missing_edge_topology",
            reason=f"STEP topology validation requires STEP_topology edgeView schemaVersion {STEP_TOPOLOGY_SCHEMA_VERSION} in the GLB",
            cad_path=target.cad_path,
            kind=target.kind,
            source_path=target.source_path,
            step_path=target.step_path,
            glb_path=resolved_glb_path,
        )
    if not (
        isinstance(primitive_attributes, dict)
        and primitive_attributes.get("barycentric") == STEP_EDGE_BARYCENTRIC_ATTRIBUTE
        and primitive_attributes.get("class") == STEP_EDGE_CLASS_ATTRIBUTE
        and glb_primitives_have_surface_edge_attributes(resolved_glb_path)
    ):
        raise _topology_artifact_error(
            code="missing_surface_edge_attributes",
            reason=f"STEP topology validation requires {STEP_EDGE_BARYCENTRIC_ATTRIBUTE} and {STEP_EDGE_CLASS_ATTRIBUTE} on STEP mesh primitives",
            cad_path=target.cad_path,
            kind=target.kind,
            source_path=target.source_path,
            step_path=target.step_path,
            glb_path=resolved_glb_path,
        )
    edge_stats = edge_manifest.get("stats")
    surface_half_edge_count = (
        int(edge_stats.get("surfaceHalfEdgeCount") or 0)
        if isinstance(edge_stats, dict)
        else 0
    )
    generated_counts = (
        edge_rendering.get("generatedVisibilityClassCounts")
        if isinstance(edge_rendering, dict) and isinstance(edge_rendering.get("generatedVisibilityClassCounts"), dict)
        else {}
    )
    expects_surface_edge_classes = surface_half_edge_count > 0 or any(
        int(value or 0) > 0 for value in generated_counts.values()
    )
    if expects_surface_edge_classes and not glb_surface_edge_class_has_nonzero_values(resolved_glb_path):
        raise _topology_artifact_error(
            code="missing_surface_edge_attributes",
            reason=f"STEP topology validation requires nonzero {STEP_EDGE_CLASS_ATTRIBUTE} values for generated surface edges",
            cad_path=target.cad_path,
            kind=target.kind,
            source_path=target.source_path,
            step_path=target.step_path,
            glb_path=resolved_glb_path,
        )

    selector_bundle = None
    if require_selector:
        selector_bundle = read_step_topology_bundle_from_glb(resolved_glb_path)
        if selector_bundle is None:
            raise _topology_artifact_error(
                code="missing_selector_topology",
                reason="STEP topology validation requires readable STEP_topology selectorView in the GLB",
                cad_path=target.cad_path,
                kind=target.kind,
                source_path=target.source_path,
                step_path=target.step_path,
                glb_path=resolved_glb_path,
            )

    return StepTopologyArtifact(
        cad_path=target.cad_path,
        kind=target.kind,
        source_path=target.source_path,
        step_path=target.step_path,
        glb_path=resolved_glb_path,
        manifest=manifest,
        selector_bundle=selector_bundle,
    )


def _direct_step_path(cad_path: str) -> Path | None:
    for suffix in STEP_SUFFIXES:
        candidate = (REPO_ROOT / f"{cad_path}{suffix}").resolve()
        if candidate.is_file():
            return candidate
    return None


def _raw_step_path(target: str) -> Path | None:
    if not target:
        return None
    path = Path(target).expanduser()
    if path.suffix.lower() not in STEP_SUFFIXES:
        return None
    resolved = path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()
    return resolved if resolved.is_file() else None


def _source_path_from_manifest(manifest: dict[str, object] | None, *, glb_path: Path) -> Path | None:
    raw_path = str((manifest or {}).get("sourcePath") or "").strip()
    if not raw_path:
        return None
    return _resolved_manifest_path(raw_path, base_dir=glb_path.parent)


def _resolved_manifest_path(raw_path: str, *, base_dir: Path) -> Path | None:
    if not raw_path:
        return None
    candidates = (
        _resolve_manifest_path_from_base(raw_path, base_dir),
        _resolve_manifest_path_from_base(raw_path, REPO_ROOT),
    )
    existing = next((candidate for candidate in candidates if candidate is not None and candidate.is_file()), None)
    if existing is not None:
        return existing
    return next((candidate for candidate in candidates if candidate is not None), None)


def _resolve_manifest_path_from_base(raw_path: str, base_dir: Path) -> Path | None:
    path = Path(str(raw_path).replace("\\", "/"))
    resolved = path.resolve() if path.is_absolute() else (base_dir / path).resolve()
    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError:
        return None
    return resolved


def _topology_artifact_error(
    *,
    code: str,
    reason: str,
    cad_path: str,
    kind: str,
    source_path: Path,
    step_path: Path,
    glb_path: Path,
) -> StepTopologyArtifactError:
    return StepTopologyArtifactError(
        code=code,
        cad_path=cad_path,
        step_path=step_path,
        glb_path=glb_path,
        regenerate_command=REGENERATE_STEP_COMMAND,
        message=(
            f"{reason}: {_relative_to_repo(glb_path)}.\n"
            f"{REGENERATE_STEP_PROMPT}"
        ),
    )


def _cad_path_lookup_candidates(cad_path: str) -> tuple[str, ...]:
    return (cad_path,) if cad_path else ()


def _lookup_cad_path(cad_path: str) -> str:
    for candidate in _cad_path_lookup_candidates(cad_path):
        if resolve_cad_source_path(candidate) is not None:
            return candidate
    return cad_path


def _relative_to_repo(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()
