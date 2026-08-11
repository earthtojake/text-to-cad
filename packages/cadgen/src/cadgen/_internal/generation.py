from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterator, Sequence, TextIO

from cadgen.catalog import (
    CadSource,
    StepImportOptions,
    cad_ref_from_dxf_path,
    cad_ref_from_step_path,
    render_package_dir,
    find_source_by_path,
    iter_cad_sources,
    normalize_cad_ref,
    normalize_source_ref,
    source_from_path,
)
from cadgen.cli_logging import CliLogger
from cadgen._internal.cli_locking import lock_wait_notice
from cadgen._internal.file_metadata import text_to_cad_identity_metadata, write_dxf_text_to_cad_metadata
from cadgen._internal.package_freshness import (
    ASSEMBLY_PACKAGE_SCHEMA_VERSION,
    bake_hash_matches,
    schema_version_matches,
)
from cadgen._internal.glb import build_step_topology_index_manifest
from cadgen._internal.glb import read_step_topology_manifest_from_glb
from cadgen._internal.glb_topology import (
    STEP_EDGE_VISIBILITY_CLASSES,
    normalize_step_edge_render_visibility_classes,
)
from cadgen.coordination import (
    DRAWING_PACKAGE,
    PHASE_GENERATE,
    STEP_PACKAGE,
    ProgressEvent,
    artifact_build,
    generator_busy,
    render_progress_bar,
    resolve as resolve_progress,
)
from cadgen.coordination.lock import exclusive
from cadgen.coordination.paths import write_lock_path
from cadgen.metadata import (
    DEFAULT_MESH_ANGULAR_TOLERANCE,
    DEFAULT_MESH_TOLERANCE,
    GeneratorMetadata,
    resolve_mesh_settings,
)
from cadgen.render import (
    relative_to_file,
    relative_to_cwd,
)
from cadgen._internal.source_hash import (
    PythonSourceClosure,
    PythonSourceHash,
    capture_runtime_closure,
    closure_hash_matches,
    evict_first_party_modules,
    python_source_hash,
    record_first_party_execution,
)
from cadgen.step_export import build_build123d_step_scene
from cadgen._internal.step_scene import (
    load_step_scene_cached,
    LoadedStepScene,
    SelectorBundle,
    SelectorOptions,
    adaptive_mesh_resolution_from_hints,
    adaptive_mesh_resolution_for_scene,
    step_file_hash,
)

GIT_LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1\n"


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
    mesh_tolerance: float = DEFAULT_MESH_TOLERANCE
    mesh_angular_tolerance: float = DEFAULT_MESH_ANGULAR_TOLERANCE
    mesh_tolerance_explicit: bool = False
    mesh_angular_tolerance_explicit: bool = False
    color: tuple[float, float, float, float] | None = None

    @property
    def entry_path(self) -> Path | None:
        # The actual on-disk ENTRY file the render cache is keyed by: the `.step.py` generator for
        # a generated model, or the `.step`/`.stp` itself for an imported one. So a generated
        # `<name>.step.py` and an imported `<name>.step` get distinct cache packages.
        return self.script_path if self.script_path is not None else self.step_path


@dataclass
class GeneratedStepResult:
    spec: EntrySpec
    scene: LoadedStepScene | None
    selector_bundle: SelectorBundle | None = None


@dataclass(frozen=True)
class _CliTargetSpec:
    target: str
    output_path: Path | None = None


class InlineProgressLine:
    """A single self-erasing progress line for one model's build.

    Repaints in place with ``\\r`` and erases itself when the build ends, so the only
    durable output is still the logger's own lines -- the bar is transient status, not
    a log record. Disabled (and completely silent) when the stream is not a tty: a
    redirected log wants the logger's lines, not a bar smeared over hundreds of writes.

    Goes to STDERR, with the rest of the narration. A sibling class used to paint a
    persistent per-model board on STDOUT with cursor-movement escapes, for callers that ran
    without a logger; there were none, and stdout is the CLIs' result channel."""

    def __init__(self, *, stream: TextIO | None = None, enabled: bool = True) -> None:
        self._stream = stream if stream is not None else sys.stderr
        self._enabled = bool(enabled) and getattr(self._stream, "isatty", lambda: False)()
        self._width = 0

    def update(self, text: str) -> None:
        if not self._enabled:
            return
        # Pad to the previous width so a shorter line cannot leave the tail of a longer
        # one behind it.
        padding = max(0, self._width - len(text))
        self._width = len(text)
        print(f"\r{text}{' ' * padding}", end="", file=self._stream, flush=True)

    def clear(self) -> None:
        if not self._enabled or not self._width:
            return
        print(f"\r{' ' * self._width}\r", end="", file=self._stream, flush=True)
        self._width = 0


@contextlib.contextmanager
def cli_progress_line(
    label: str,
    *,
    logger: CliLogger,
    fallback: str,
) -> Iterator[Callable[[ProgressEvent], None] | None]:
    """The same one-line build progress `gen` paints, for any caller with a label.

    `scripts/artifact` builds exactly what `scripts/gen` builds and reported nothing while
    doing it -- the sidecar record went to the viewer, and a terminal caller watched a
    silent process. Sharing this is what stops the two disagreeing about whether a build is
    worth narrating."""
    if logger.verbose:
        yield None
        return
    line = InlineProgressLine(stream=logger.stream)

    def paint(event: ProgressEvent) -> None:
        if event.finished:
            return
        line.update(f"{label}  {_progress_status_text(event, fallback=fallback)}")

    try:
        yield paint
    finally:
        line.clear()


@contextlib.contextmanager
def _cli_progress_line(
    spec: EntrySpec,
    *,
    logger: CliLogger,
    fallback: str,
) -> Iterator[Callable[[ProgressEvent], None] | None]:
    """Yield a progress sink that paints ``spec``'s build onto one tty line.

    Yields None -- reporting nothing -- under ``--verbose``, where the logger is already
    narrating every stage and a bar repainting between its lines would fight with them.
    The sidecar is written regardless, so an open CAD Viewer still tracks the build."""
    if logger.verbose:
        yield None
        return
    line = InlineProgressLine(stream=logger.stream)

    def paint(event: ProgressEvent) -> None:
        # The terminal event exists to record the run's stage times in the sidecar;
        # painting it would flash a completed bar onto a line about to be erased.
        if event.finished:
            return
        line.update(f"{spec.source_ref}  {_progress_status_text(event, fallback=fallback)}")

    try:
        yield paint
    finally:
        line.clear()


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
    if "\\" in value:
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
        mesh_tolerance_explicit=spec.mesh_tolerance_explicit or step_options.mesh_tolerance is not None,
        mesh_angular_tolerance_explicit=(
            spec.mesh_angular_tolerance_explicit or step_options.mesh_angular_tolerance is not None
        ),
    )


def _spec_requests_extra_outputs(spec: EntrySpec) -> bool:
    """True when the target asks for an on-demand output beyond the render package
    (`scripts/gen --write-step`). An explicitly requested output must be produced
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
                # A STEP output path is now a STEP *export* request (gen_step writes no STEP
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
                # A DXF output path is a DXF *export* request (gen_dxf builds the drawing
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
    mesh_settings = resolve_mesh_settings(
        cad_ref=source.cad_ref,
        generator_metadata=generator_metadata,
        mesh_tolerance=source.mesh_tolerance,
        mesh_angular_tolerance=source.mesh_angular_tolerance,
    )
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
        mesh_tolerance=mesh_settings.tolerance,
        mesh_angular_tolerance=mesh_settings.angular_tolerance,
        mesh_tolerance_explicit=source.mesh_tolerance is not None,
        mesh_angular_tolerance_explicit=source.mesh_angular_tolerance is not None,
        color=source.color,
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


def _mesh_tolerance_is_explicit(spec: EntrySpec) -> bool:
    return bool(spec.mesh_tolerance_explicit) or not math.isclose(
        float(spec.mesh_tolerance),
        float(DEFAULT_MESH_TOLERANCE),
        rel_tol=1e-12,
        abs_tol=1e-12,
    )


def _mesh_angular_tolerance_is_explicit(spec: EntrySpec) -> bool:
    return bool(spec.mesh_angular_tolerance_explicit) or not math.isclose(
        float(spec.mesh_angular_tolerance),
        float(DEFAULT_MESH_ANGULAR_TOLERANCE),
        rel_tol=1e-12,
        abs_tol=1e-12,
    )


# How much finer than the adaptive floor an explicit tolerance has to be before
# it is almost certainly a mistake rather than a deliberate choice.
_TOLERANCE_WARN_RATIO = 8.0


def _warn_if_tolerance_defeats_scale_floor(spec: EntrySpec, adaptive: object) -> None:
    """Say something when ``--mesh-tolerance`` silently defeats the size floor.

    For anything larger than desk scale the adaptive resolver floors the linear
    deflection proportionally to the model diagonal, because meshing a metre-scale
    part at micron-class chord error costs minutes and hundreds of megabytes. An
    explicit ``--mesh-tolerance`` overrides that floor completely — which is
    correct, but silent, and 0.02 looks like a safe "default" value to pass. On a
    5.4 m car it is 80x finer than the floor and turns a 15-second build into a
    six-minute one with nothing in the output to explain why.
    """
    settings = getattr(adaptive, "settings", None)
    floor = float(getattr(settings, "tolerance", 0.0) or 0.0)
    requested = float(spec.mesh_tolerance)
    if floor <= 0.0 or requested <= 0.0 or requested >= floor / _TOLERANCE_WARN_RATIO:
        return
    hints = getattr(adaptive, "hints", None)
    diagonal = 0.0
    if isinstance(hints, Mapping):
        raw = hints.get("bboxDiag")
        diagonal = float(raw) if isinstance(raw, (int, float)) else 0.0
    print(
        f"[cadgen] warning: --mesh-tolerance {requested:g} mm is "
        f"{floor / requested:.0f}x finer than the {floor:g} mm this model's size "
        f"({diagonal:.0f} mm diagonal) would otherwise use. Meshing will be much "
        f"slower and the package much larger. Omit --mesh-tolerance to let it scale.",
        file=sys.stderr,
        flush=True,
    )


def _selector_options_for_part(spec: EntrySpec, *, scene: LoadedStepScene | None = None) -> SelectorOptions:
    defaults = SelectorOptions()
    linear_deflection = spec.mesh_tolerance
    angular_deflection = spec.mesh_angular_tolerance
    resolution: dict[str, object] = {
        "mode": "explicit",
        "profile": "custom",
        "linearExplicit": True,
        "angularExplicit": True,
    }
    linear_explicit = _mesh_tolerance_is_explicit(spec)
    angular_explicit = _mesh_angular_tolerance_is_explicit(spec)
    edge_visibility_classes = normalize_step_edge_render_visibility_classes(None)
    if isinstance(scene, LoadedStepScene):
        adaptive = adaptive_mesh_resolution_for_scene(scene)
        if not linear_explicit:
            linear_deflection = adaptive.settings.tolerance
        else:
            _warn_if_tolerance_defeats_scale_floor(spec, adaptive)
        if not angular_explicit:
            angular_deflection = adaptive.settings.angular_tolerance
        edge_visibility_classes = _edge_visibility_classes_for_resolution(adaptive.profile, adaptive.hints)
        resolution = {
            "mode": "auto",
            "profile": adaptive.profile,
            "linearExplicit": linear_explicit,
            "angularExplicit": angular_explicit,
            "hints": adaptive.hints,
        }
    return SelectorOptions(
        linear_deflection=linear_deflection,
        angular_deflection=angular_deflection,
        relative=defaults.relative,
        edge_deflection=defaults.edge_deflection,
        edge_deflection_ratio=defaults.edge_deflection_ratio,
        max_edge_points=defaults.max_edge_points,
        digits=defaults.digits,
        mesh_resolution=resolution,
        edge_visibility_classes=edge_visibility_classes,
    )


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


def _load_generator_module(script_path: Path) -> object:
    resolved_script_path = script_path.resolve()
    module_name = (
        "_cad_tool_"
        + _display_path(resolved_script_path).replace("/", "_").replace("\\", "_").replace("-", "_").replace(".", "_")
    )
    module_spec = importlib.util.spec_from_file_location(module_name, resolved_script_path)
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError(f"Failed to load generator module from {_display_path(resolved_script_path)}")

    module = importlib.util.module_from_spec(module_spec)
    original_sys_path = list(sys.path)
    # Seed sys.path so the generator's module-top imports (its sibling/shared packages such as
    # robot_common / STEP) resolve. Derive everything from the generator script's OWN location —
    # its folder, plus any ancestor that is a package root (contains a STEP/ or robot_common/
    # package) — so resolution is independent of the process working directory. Deliberately NOT
    # seeding the repo root or skills/cad/scripts: a generator must not depend on the repository's
    # skills/ being importable (AGENTS.md skill isolation).
    search_paths = [str(resolved_script_path.parent)]
    for parent in resolved_script_path.parents:
        if (
            (parent / "STEP" / "__init__.py").is_file()
            or (parent / "robot_common" / "__init__.py").is_file()
        ):
            search_paths.append(str(parent))
    for candidate in reversed(search_paths):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)

    try:
        sys.modules[module_name] = module
        module_spec.loader.exec_module(module)
    finally:
        sys.path[:] = original_sys_path

    return module


def _resolve_params_sidecar(params: object, *, script_path: Path) -> Path:
    """Resolve the optional gen_step() ``params`` value — a filepath to a hand-authored
    JS sidecar (the step-module manifest: parameters/features/animations/update) — to an
    absolute path. A relative path is resolved against the generator file's directory.
    The sidecar is hand-authored source, so it must already exist on disk."""
    if not isinstance(params, (str, Path)):
        raise TypeError(
            f"{_display_path(script_path)} gen_step() envelope field 'params' must be a "
            f"filepath string, got {type(params).__name__}"
        )
    candidate = Path(params)
    resolved = (candidate if candidate.is_absolute() else script_path.parent / candidate).resolve()
    if not resolved.is_file():
        raise FileNotFoundError(
            f"{_display_path(script_path)} gen_step() params sidecar not found: {params}"
        )
    return resolved


def _normalize_step_payload(
    result: object,
    *,
    script_path: Path,
) -> dict[str, object]:
    from build123d import Shape as Build123dShape

    if isinstance(result, Build123dShape):
        return {"shape": result}
    if isinstance(result, dict):
        # stl / 3mf / mesh_tolerance / mesh_angular_tolerance are consumed via the static
        # metadata path (per-generator STL/3MF outputs + mesh tolerances); keep allowing them.
        allowed_fields = {"shape", "params", "stl", "3mf", "mesh_tolerance", "mesh_angular_tolerance"}
        extra_fields = sorted(str(key) for key in result if key not in allowed_fields)
        if extra_fields:
            joined = ", ".join(extra_fields)
            raise TypeError(f"{_display_path(script_path)} gen_step() envelope has unsupported field(s): {joined}")
        if "shape" not in result:
            raise TypeError(
                f"{_display_path(script_path)} gen_step() envelope must define 'shape'"
            )
        envelope: dict[str, object] = {"shape": result["shape"]}
        params = result.get("params")
        if params is not None:
            envelope["params"] = _resolve_params_sidecar(params, script_path=script_path)
        return envelope
    raise TypeError(
        f"{_display_path(script_path)} gen_step() must return a build123d Shape "
        "or a {'shape': ..., 'params': ...} envelope"
    )


def _normalize_dxf_payload(result: object, *, script_path: Path) -> dict[str, object]:
    if isinstance(result, dict):
        allowed_fields = {"document"}
        extra_fields = sorted(str(key) for key in result if key not in allowed_fields)
        if extra_fields:
            joined = ", ".join(extra_fields)
            raise TypeError(f"{_display_path(script_path)} gen_dxf() envelope has unsupported field(s): {joined}")
        if "document" not in result:
            raise TypeError(f"{_display_path(script_path)} gen_dxf() envelope must define 'document'")
        return {"document": result["document"]}
    return {"document": result}


def _shape_payload_entry_kind(shape: object, *, fallback: str) -> str:
    if fallback not in {"part", "assembly"}:
        raise RuntimeError(f"Unsupported generated STEP kind: {fallback}")
    if (
        fallback == "assembly"
        or _shape_has_explicit_children(shape)
        or _shape_is_multi_child_compound(shape)
    ):
        return "assembly"
    return "part"


def _shape_has_explicit_children(shape: object) -> bool:
    try:
        from build123d import Shape as Build123dShape
    except Exception:
        return False
    if not isinstance(shape, Build123dShape):
        return False
    try:
        return bool(tuple(getattr(shape, "children", ()) or ()))
    except TypeError:
        return False


def _shape_is_multi_child_compound(shape: object) -> bool:
    try:
        from OCP.TopAbs import TopAbs_COMPOUND
        from OCP.TopoDS import TopoDS_Iterator
        from build123d import Shape as Build123dShape
    except Exception:
        return False
    if not isinstance(shape, Build123dShape):
        return False
    wrapped = getattr(shape, "wrapped", None)
    if wrapped is None:
        return False
    try:
        if wrapped.ShapeType() != TopAbs_COMPOUND:
            return False
    except Exception:
        return False
    iterator = TopoDS_Iterator(wrapped)
    count = 0
    while iterator.More():
        count += 1
        if count > 1:
            return True
        iterator.Next()
    return False


def _mark_scene_step_payload(
    scene: LoadedStepScene,
    *,
    entry_kind: str,
    payload_kind: str,
) -> LoadedStepScene:
    if isinstance(scene, LoadedStepScene):
        scene.text_to_cad_entry_kind = entry_kind
        scene.step_payload_kind = payload_kind
    return scene


def _scene_entry_kind(scene: LoadedStepScene | None) -> str | None:
    if scene is None:
        return None
    entry_kind = str(getattr(scene, "text_to_cad_entry_kind", "") or "").strip().lower()
    return entry_kind if entry_kind in {"part", "assembly"} else None


def _effective_step_spec_for_scene(spec: EntrySpec, scene: LoadedStepScene | None) -> EntrySpec:
    entry_kind = _scene_entry_kind(scene)
    if entry_kind is None or entry_kind == spec.kind:
        return spec
    return replace(spec, kind=entry_kind)


def _write_shape_step_payload(
    envelope: dict[str, object],
    *,
    output_path: Path,
    script_path: Path,
    logger: CliLogger,
    entry_kind: str,
) -> LoadedStepScene:
    shape = envelope.get("shape")
    from build123d import Shape as Build123dShape

    if not isinstance(shape, Build123dShape):
        raise TypeError(
            f"{_display_path(script_path)} gen_step() envelope field 'shape' must be a build123d Shape, "
            f"got {type(shape).__name__}"
        )
    # gen_step builds the render scene in memory and does NOT write a text STEP — STEP is
    # written on demand from scene.source_compound (`scripts/gen --write-step`, or the
    # Viewer's Save-dialog export). The scene is built straight from the XCAF doc, never
    # via a STEP round-trip.
    source_identity = python_source_hash(script_path)
    scene = build_build123d_step_scene(
        shape,
        output_path,
        source_kind="python",
        source_hash=source_identity.source_hash,
    )
    _mark_scene_python_backed(scene, source_identity=source_identity, source_path=script_path)
    _mark_scene_step_payload(scene, entry_kind=entry_kind, payload_kind="shape")
    # Stash the pre-bake compound: the component-package emit job introspects its located
    # children (occurrence transforms + dedup), and the STEP export serializes it.
    scene.source_compound = shape
    params_abs = envelope.get("params")
    if params_abs is not None:
        # Record the hand-authored JS sidecar model-folder-relative, like sourcePath, so the
        # descriptor stays portable. The viewer reads this back from assembly.json.
        scene.params_path = relative_to_file(Path(params_abs), scene.step_path)
    logger.debug(f"built render scene (no STEP written): {_display_path(output_path)}")
    return scene


def _mark_scene_python_backed(
    scene: LoadedStepScene,
    *,
    source_identity: PythonSourceHash,
    source_path: Path,
) -> LoadedStepScene:
    if not isinstance(scene, LoadedStepScene):
        return scene
    scene.source_kind = "python"
    scene.source_hash = source_identity.source_hash
    scene.source_path = relative_to_file(source_path, scene.step_path)
    return scene


def _write_dxf_payload(
    envelope: dict[str, object],
    *,
    output_path: Path,
    script_path: Path,
    logger: CliLogger,
) -> None:
    document = envelope.get("document")
    saveas = getattr(document, "saveas", None)
    if not callable(saveas):
        raise TypeError(
            f"{_display_path(script_path)} gen_dxf() envelope field 'document' must be a DXF document, "
            f"got {type(document).__name__}"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    saveas(str(output_path))
    source_identity = python_source_hash(script_path)
    write_dxf_text_to_cad_metadata(
        output_path,
        text_to_cad_identity_metadata(
            source_path=relative_to_file(script_path, output_path),
            source_hash=source_identity.source_hash,
        ),
    )
    logger.debug(f"wrote DXF: {_display_path(output_path)}")


def run_script_generator(
    spec: EntrySpec,
    generator_name: str,
    *,
    logger: CliLogger | None = None,
    force: bool = False,
    reset_runtime_closure: bool = False,
    progress: object | None = None,
    lock_intent: str = "write",
) -> LoadedStepScene | None:
    """Run a generator's ``gen_step``/``gen_dxf`` and return its scene.

    ``lock_intent`` says whether this run will rewrite the model's render package
    (``"write"``, the default) or merely occupy its generator (``"generate"`` -- an export,
    a topology extraction, an interference check). See :func:`_track_spec_generation`:
    getting this wrong makes an export look like a build to the CAD Viewer.

    Closure capture is deterministic in every process shape: first-party modules
    are evicted from ``sys.modules`` BEFORE the generator loads (so its full
    dependency closure is freshly imported on every run — warm worker, multi-target
    CLI loop, or cold process alike, and regardless of earlier failed builds), and
    every first-party file EXECUTED during the run is recorded via the ``exec``
    audit event (so dependencies survive even when a generator unloads modules
    from ``sys.modules`` mid-run). Only first-party ``.py`` modules are evicted
    (see :func:`repo_local_loaded_modules`); the running runtime (cadgen, the CLI
    launcher) and C extensions / site-packages (numpy, OCP, build123d) are never
    touched — they cannot reload, must stay warm, and are not freshness inputs.

    ``reset_runtime_closure`` is retained for API compatibility (the warm worker
    passes it) but is now a no-op: the pre-run eviction supersedes it.
    """
    logger = logger or CliLogger("cad")
    if generator_name not in {"gen_step", "gen_dxf"}:
        raise RuntimeError(f"Unsupported generator: {generator_name}")
    if spec.script_path is None or spec.generator_metadata is None:
        raise ValueError(f"{spec.source_ref} is not a generated Python CAD source")
    # Opaque by nature: the generator is arbitrary user code with no unit of work to
    # count, so this reports a phase, not a fraction. Readers estimate it against the
    # duration the model's previous build recorded.
    resolve_progress(progress).phase(PHASE_GENERATE)
    with _track_spec_generation(spec, generator_name, intent=lock_intent, logger=logger):
        return _run_script_generator_inner(
            spec,
            generator_name,
            logger=logger,
            force=force,
            reset_runtime_closure=reset_runtime_closure,
            progress=progress,
        )


def _run_script_generator_inner(
    spec: EntrySpec,
    generator_name: str,
    *,
    logger: CliLogger,
    force: bool = False,
    reset_runtime_closure: bool = False,
    progress: object | None = None,
) -> LoadedStepScene | None:
    del reset_runtime_closure  # superseded by the pre-run eviction below; kept for API compat
    generated_scene: LoadedStepScene | None = None
    # Deterministic closure capture (see run_script_generator's docstring): start from a
    # clean first-party module space, then record every first-party file executed while
    # the generator loads and runs. The recorded set is complete even if the generator
    # unloads modules mid-run; the sys.modules delta stays as a belt-and-braces union.
    evict_first_party_modules()
    modules_before_load = set(sys.modules)
    with record_first_party_execution() as executed_files:
        with logger.timed(f"load generator {spec.source_ref}"):
            module = _load_generator_module(spec.script_path)
        generator = getattr(module, generator_name, None)
        if not callable(generator):
            raise RuntimeError(f"{_display_path(spec.script_path)} does not define callable {generator_name}()")
        with logger.timed(f"run {generator_name} {spec.source_ref}"):
            raw_payload = generator()

    source_closure: PythonSourceClosure | None = None
    if generator_name == "gen_step":
        envelope = _normalize_step_payload(raw_payload, script_path=spec.script_path)
        if spec.step_path is None:
            raise RuntimeError(f"{spec.source_ref} has no configured STEP output")
        # Record paths relative to the model folder so the descriptor stays portable.
        source_closure = capture_runtime_closure(
            modules_before_load,
            spec.script_path,
            base=spec.step_path.parent,
            executed_files=executed_files,
        )
        generated_scene = _write_shape_step_payload(
            envelope,
            output_path=spec.step_path,
            script_path=spec.script_path,
            logger=logger,
            entry_kind=_shape_payload_entry_kind(envelope.get("shape"), fallback=spec.kind),
        )
    elif generator_name == "gen_dxf":
        from cadgen._internal.drawing_package import write_drawing_package
        from cadgen.drawing_checks import raise_on_error_findings, validate_drawing_document

        envelope = _normalize_dxf_payload(raw_payload, script_path=spec.script_path)
        if spec.dxf_path is None:
            raise RuntimeError(f"{spec.source_ref} has no configured DXF output")
        # Validation happens IN generation: the in-memory document is checked once,
        # gating the drawing package and every export alike. Fail closed — anything
        # that is not a real drawing document is rejected rather than skipped.
        document = envelope.get("document")
        if not (hasattr(document, "modelspace") and hasattr(document, "header")):
            raise TypeError(
                f"{_display_path(spec.script_path)} gen_dxf() must return an ezdxf "
                f"document, got {type(document).__name__}"
            )
        findings = validate_drawing_document(document)
        for finding in findings:
            if finding.severity != "error":
                logger.info(f"{spec.source_ref} {finding.render()}")
        raise_on_error_findings(findings, label=_display_path(spec.script_path))
        # Mirror gen_step: capture the generator's closure (relative to the model
        # folder) so the drawing package records the freshness inputs the viewer's
        # staleness gate reads. Code reuse is the freshness link: a drawing that
        # path-loads its .step.py records it (and its imports) here. Non-Python inputs
        # (e.g. an imported vendor .step) are intentionally NOT tracked — like a
        # gen_step that composes imported STEPs, the drawing does not rebuild when
        # they change. Then the default build product is the drawing package; the
        # sibling/exported .dxf is written on demand only.
        source_closure = capture_runtime_closure(
            modules_before_load,
            spec.script_path,
            base=spec.script_path.parent,
            executed_files=executed_files,
        )
        # `progress` is the BuildRun holding this package's lock. It is threaded down here
        # because writing the package now includes baking preview.glb in a Node child, and
        # that child reports its phases -- and proves its run id against the lock sentinel --
        # through the very run that is holding the lock (design §4.3, §7.4.2).
        write_drawing_package(
            envelope.get("document"),
            script_path=spec.script_path,
            source_closure=source_closure,
            run=progress,
        )
        logger.debug(
            f"wrote drawing package: {_display_path(render_package_dir(spec.script_path))}"
        )
        if spec.dxf_export_path is not None:
            _write_dxf_payload(
                envelope, output_path=spec.dxf_export_path, script_path=spec.script_path, logger=logger
            )
    if generated_scene is not None and source_closure is not None:
        generated_scene.source_closure_hash = source_closure.closure_hash
        generated_scene.source_closure_files = source_closure.files
    if (
        generator_name == "gen_dxf"
        and spec.dxf_export_path is not None
        and not spec.dxf_export_path.exists()
    ):
        raise RuntimeError(
            f"{_display_path(spec.script_path)} did not write {_display_path(spec.dxf_export_path)}"
        )
    return generated_scene if generator_name == "gen_step" else None


def _is_git_lfs_pointer(step_path: Path) -> bool:
    try:
        with step_path.open("rb") as handle:
            return handle.read(len(GIT_LFS_POINTER_PREFIX)) == GIT_LFS_POINTER_PREFIX
    except OSError:
        return False


def _ensure_step_ready(step_path: Path) -> None:
    if not step_path.exists():
        raise FileNotFoundError(f"STEP file is missing: {_display_path(step_path)}")
    if _is_git_lfs_pointer(step_path):
        raise RuntimeError(
            f"{_display_path(step_path)} is a Git LFS pointer, not the real STEP file.\n"
            "Fetch Git LFS objects before generating CAD artifacts.\n"
            "For Vercel Git deployments, enable Git LFS in Project Settings > Git and redeploy."
        )


@dataclass(frozen=True)
class _ArtifactJob:
    name: str
    run: Callable[[], object]


def _run_artifact_jobs(
    jobs: Sequence[_ArtifactJob],
    *,
    logger: CliLogger | None = None,
) -> dict[str, object]:
    results: dict[str, object] = {}
    for job in jobs:
        if logger is not None:
            with logger.timed(f"write {job.name}"):
                results[job.name] = job.run()
        else:
            results[job.name] = job.run()
    return results


def _mesh_values_match(
    mesh: Mapping[str, object],
    *,
    linear_deflection: float,
    angular_deflection: float,
    relative: bool,
) -> bool:
    try:
        artifact_linear = float(mesh.get("linearDeflection"))
        artifact_angular = float(mesh.get("angularDeflection"))
    except (TypeError, ValueError):
        return False
    return (
        math.isclose(artifact_linear, float(linear_deflection), rel_tol=1e-9, abs_tol=1e-12)
        and math.isclose(artifact_angular, float(angular_deflection), rel_tol=1e-9, abs_tol=1e-12)
        and bool(mesh.get("relative", True)) == bool(relative)
    )


def _selector_options_from_topology_manifest(spec: EntrySpec, manifest: Mapping[str, object]) -> SelectorOptions | None:
    mesh = manifest.get("mesh")
    if not isinstance(mesh, Mapping):
        return None

    defaults = SelectorOptions()
    linear_explicit = _mesh_tolerance_is_explicit(spec)
    angular_explicit = _mesh_angular_tolerance_is_explicit(spec)
    linear_deflection = spec.mesh_tolerance
    angular_deflection = spec.mesh_angular_tolerance

    if not linear_explicit or not angular_explicit:
        resolution = mesh.get("resolution")
        hints = resolution.get("hints") if isinstance(resolution, Mapping) else None
        if not isinstance(hints, dict):
            return None
        adaptive = adaptive_mesh_resolution_from_hints(hints)
        if not linear_explicit:
            linear_deflection = adaptive.settings.tolerance
        if not angular_explicit:
            angular_deflection = adaptive.settings.angular_tolerance

    return SelectorOptions(
        linear_deflection=linear_deflection,
        angular_deflection=angular_deflection,
        relative=bool(mesh.get("relative", defaults.relative)),
        edge_deflection=defaults.edge_deflection,
        edge_deflection_ratio=defaults.edge_deflection_ratio,
        max_edge_points=defaults.max_edge_points,
        digits=defaults.digits,
        mesh_resolution=mesh.get("resolution") if isinstance(mesh.get("resolution"), dict) else None,
        edge_visibility_classes=_edge_visibility_classes_from_topology_manifest(manifest),
    )


def _edge_visibility_classes_from_topology_manifest(manifest: Mapping[str, object]) -> tuple[str, ...]:
    edge_rendering = manifest.get("edgeRendering")
    if isinstance(edge_rendering, Mapping):
        classes = edge_rendering.get("visibilityClasses")
        if classes is not None:
            return normalize_step_edge_render_visibility_classes(classes)
    mesh = manifest.get("mesh")
    resolution = mesh.get("resolution") if isinstance(mesh, Mapping) else None
    hints = resolution.get("hints") if isinstance(resolution, Mapping) else None
    profile = resolution.get("profile") if isinstance(resolution, Mapping) else ""
    if isinstance(hints, Mapping):
        return _edge_visibility_classes_for_resolution(str(profile or ""), hints)
    return normalize_step_edge_render_visibility_classes(None)


def _edge_visibility_classes_match_manifest(
    manifest: Mapping[str, object],
    selector_options: SelectorOptions,
) -> bool:
    edge_rendering = manifest.get("edgeRendering")
    if not isinstance(edge_rendering, Mapping):
        return False
    return tuple(edge_rendering.get("visibilityClasses") or ()) == tuple(selector_options.edge_visibility_classes)


def _artifact_source_kind_matches_spec(spec: EntrySpec, manifest: Mapping[str, object]) -> bool:
    source_kind = str(manifest.get("sourceKind") or "step").strip().lower()
    if spec.source != "generated" and spec.step_path is not None and spec.step_path.is_file():
        if source_kind == "python":
            return bool(str(manifest.get("stepHash") or "").strip())
        return source_kind == "step"
    expected = "python" if spec.source == "generated" and spec.script_path is not None else "step"
    return source_kind == expected


def _artifact_step_hash_matches_spec(spec: EntrySpec, manifest: Mapping[str, object]) -> bool:
    if spec.step_path is None or not spec.step_path.is_file():
        return True
    expected_hash = step_file_hash(spec.step_path)
    return str(manifest.get("stepHash") or "").strip() == expected_hash


def _package_descriptor_matches_spec(
    spec: EntrySpec,
    selector_options: SelectorOptions | None = None,
) -> bool | None:
    """Descriptor-based freshness for a component-GLB package directory.

    Returns None when the entry's artifact is not a package (caller falls back
    to the monolith-GLB validator). Packages carry no embedded selector/edge
    views (selector topology is extracted on demand), so routing them through
    the monolith validator always failed and every build re-ran gen_step plus
    the full-scene mesh; validate against the package descriptor instead.

    The schema-version and bake gates below mirror the viewer's validator
    (``viewer/server_py/artifact.py``) exactly. A check on only one side is worse than
    no check at all: the viewer would report stale, this predicate would report current,
    the build would no-op, and the request would settle ``ready`` on the stale package.
    The imported-STEP digest gate is already fail-closed here
    (``_artifact_step_hash_matches_spec``: a descriptor recording no ``stepHash`` cannot
    equal the file's real hash), which is the behaviour the viewer now matches.
    """
    from cadgen._internal.component_package import is_assembly_package, read_package_descriptor

    package_dir = render_package_dir(spec.entry_path)
    if not is_assembly_package(package_dir):
        return None
    manifest = read_package_descriptor(package_dir)
    if not isinstance(manifest, dict):
        return False
    if not schema_version_matches(manifest, ASSEMBLY_PACKAGE_SCHEMA_VERSION):
        return False
    # The assembly package bakes no format settings into its payload (components are pure
    # geometry at recorded mesh tolerances, and those are compared below), so the expected
    # bake is None -- and a descriptor that records one did not come from this producer.
    if not bake_hash_matches(manifest, None):
        return False
    if not _artifact_source_kind_matches_spec(spec, manifest):
        return False
    if not _artifact_step_hash_matches_spec(spec, manifest):
        return False
    mesh = manifest.get("mesh")
    if not isinstance(mesh, Mapping):
        return False
    if selector_options is None:
        selector_options = _selector_options_from_topology_manifest(spec, manifest)
    if selector_options is None:
        return False
    return (
        _mesh_values_match(
            mesh,
            linear_deflection=selector_options.linear_deflection,
            angular_deflection=selector_options.angular_deflection,
            relative=selector_options.relative,
        )
        and _edge_visibility_classes_match_manifest(manifest, selector_options)
    )


def _existing_topology_artifact_matches_spec_without_scene(
    spec: EntrySpec,
    *,
    require_selector: bool = True,
) -> bool:
    if spec.step_path is None or spec.kind not in {"part", "assembly"}:
        return False
    package_match = _package_descriptor_matches_spec(spec)
    if package_match is not None:
        return package_match
    from cadgen.step_targets import (
        ResolvedStepTarget,
        StepTopologyArtifactError,
        validate_step_topology_artifact,
    )

    try:
        artifact = validate_step_topology_artifact(
            ResolvedStepTarget(
                cad_path=spec.cad_ref,
                kind=spec.kind,
                source_path=spec.source_path,
                step_path=spec.step_path,
            ),
            artifact_path=render_package_dir(spec.entry_path),
            require_selector=require_selector,
        )
    except StepTopologyArtifactError:
        return False
    if not _artifact_source_kind_matches_spec(spec, artifact.manifest):
        return False
    if not _artifact_step_hash_matches_spec(spec, artifact.manifest):
        return False
    mesh = artifact.manifest.get("mesh")
    if not isinstance(mesh, Mapping):
        return False
    selector_options = _selector_options_from_topology_manifest(spec, artifact.manifest)
    if selector_options is None:
        return False
    return (
        _mesh_values_match(
            mesh,
            linear_deflection=selector_options.linear_deflection,
            angular_deflection=selector_options.angular_deflection,
            relative=selector_options.relative,
        )
        and _edge_visibility_classes_match_manifest(artifact.manifest, selector_options)
    )


def _existing_topology_artifact_matches_options(spec: EntrySpec, selector_options: SelectorOptions) -> bool:
    if spec.step_path is None or spec.kind not in {"part", "assembly"}:
        return False
    package_match = _package_descriptor_matches_spec(spec, selector_options)
    if package_match is not None:
        return package_match
    from cadgen.step_targets import (
        ResolvedStepTarget,
        StepTopologyArtifactError,
        validate_step_topology_artifact,
    )

    try:
        artifact = validate_step_topology_artifact(
            ResolvedStepTarget(
                cad_path=spec.cad_ref,
                kind=spec.kind,
                source_path=spec.source_path,
                step_path=spec.step_path,
            ),
            artifact_path=render_package_dir(spec.entry_path),
            require_selector=False,
        )
    except StepTopologyArtifactError:
        return False
    if not _artifact_source_kind_matches_spec(spec, artifact.manifest):
        return False
    if not _artifact_step_hash_matches_spec(spec, artifact.manifest):
        return False
    mesh = artifact.manifest.get("mesh")
    if not isinstance(mesh, Mapping):
        return False
    return (
        _mesh_values_match(
            mesh,
            linear_deflection=selector_options.linear_deflection,
            angular_deflection=selector_options.angular_deflection,
            relative=selector_options.relative,
        )
        and _edge_visibility_classes_match_manifest(artifact.manifest, selector_options)
    )


def _assembly_provenance_manifest(
    scene: LoadedStepScene,
    *,
    selector_options: SelectorOptions,
    step_path: Path,
    entry_kind: str,
) -> dict[str, object]:
    """The index-manifest provenance an assembly package descriptor carries, mirroring
    the monolithic GLB's embedded STEP_topology index — but WITHOUT the expensive
    selector extraction. Sourced from the scene (sourceKind/closure), the mesh options,
    and the STEP hash, so the build freshness gates can read it from assembly.json
    exactly as they read the monolithic manifest.
    """
    import os
    from datetime import datetime, timezone

    from cadgen._internal.glb_topology import step_topology_capabilities

    source_kind = str(getattr(scene, "source_kind", "step") or "step").strip().lower()
    if source_kind not in {"step", "python"}:
        source_kind = "step"
    mesh: dict[str, object] = {
        "linearDeflection": float(selector_options.linear_deflection),
        "angularDeflection": float(selector_options.angular_deflection),
        "relative": bool(selector_options.relative),
    }
    if isinstance(getattr(selector_options, "mesh_resolution", None), dict):
        mesh["resolution"] = selector_options.mesh_resolution
    minimal: dict[str, object] = {
        "sourceKind": source_kind,
        "capabilities": step_topology_capabilities(selector_options.edge_visibility_classes),
        "edgeRendering": {"visibilityClasses": list(selector_options.edge_visibility_classes)},
        "mesh": mesh,
        "stepPath": os.path.relpath(step_path, step_path.parent),
    }
    source_path = str(getattr(scene, "source_path", "") or "")
    if source_path:
        minimal["sourcePath"] = source_path
    params_path = str(getattr(scene, "params_path", "") or "")
    if params_path:
        minimal["paramsPath"] = params_path
    if source_kind == "python":
        source_hash = str(getattr(scene, "source_hash", "") or "").strip()
        if source_hash:
            minimal["sourceHash"] = source_hash
        closure_hash = str(getattr(scene, "source_closure_hash", "") or "").strip()
        closure_files = getattr(scene, "source_closure_files", ()) or ()
        if closure_hash and closure_files:
            minimal["sourceClosureHash"] = closure_hash
            minimal["sourceClosureFiles"] = list(closure_files)
        minimal["generatedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    step_hash = (
        step_file_hash(step_path)
        if step_path.is_file()
        else str(getattr(scene, "step_hash", "") or "").strip()
    )
    if step_hash:
        minimal["stepHash"] = step_hash
    return build_step_topology_index_manifest(minimal, entry_kind=entry_kind)


def _generate_part_outputs(
    spec: EntrySpec,
    *,
    entries_by_step_path: dict[Path, EntrySpec],
    preloaded_scene: LoadedStepScene | None = None,
    require_step_file: bool = True,
    force: bool = False,
    logger: CliLogger | None = None,
    progress: object | None = None,
) -> GeneratedStepResult:
    logger = logger or CliLogger("cad")
    progress = resolve_progress(progress)
    if spec.kind not in {"part", "assembly"} or spec.step_path is None:
        return GeneratedStepResult(spec=spec, scene=None)
    if require_step_file:
        _ensure_step_ready(spec.step_path)
    if preloaded_scene is not None:
        if preloaded_scene.step_path != spec.step_path.expanduser().resolve():
            raise RuntimeError(
                f"Preloaded STEP scene path {preloaded_scene.step_path} does not match {_display_path(spec.step_path)}"
            )

    # Any on-demand output (mesh sidecar or --step export) must be produced even when the
    # render package is current, so its presence defeats the reuse fast paths.
    has_extra_outputs = _spec_requests_extra_outputs(spec)
    package_current = (
        spec.source != "generated"
        or _assembly_glb_package_current(spec)
    )
    if (
        preloaded_scene is None
        and not has_extra_outputs
        and not force
        and package_current
        and _existing_topology_artifact_matches_spec_without_scene(spec)
    ):
        logger.debug(f"reused current GLB/topology: {_display_path(render_package_dir(spec.entry_path))}")
        return GeneratedStepResult(spec=spec, scene=None)

    if preloaded_scene is not None:
        scene = preloaded_scene
    else:
        # An imported STEP's parse is this path's equivalent of running a generator:
        # opaque, and often seconds for a large vendor file.
        progress.phase(PHASE_GENERATE)
        with logger.timed(f"load STEP {spec.cad_ref}"):
            # Cross-run binary BREP scene cache: warm rebuilds of imported
            # STEP entries skip the text-STEP parse (seconds to ~10s+ for
            # large vendor files) and deserialize cached geometry instead.
            scene = load_step_scene_cached(spec.step_path)
        if spec.source == "generated" and spec.script_path is not None:
            _mark_scene_python_backed(
                scene,
                source_identity=python_source_hash(spec.script_path),
                source_path=spec.script_path,
            )
    spec = _effective_step_spec_for_scene(spec, scene)
    entries_by_step_path = {
        **entries_by_step_path,
        spec.step_path.resolve(): spec,
    }
    selector_options = _selector_options_for_part(spec, scene=scene)
    if (
        not has_extra_outputs
        and not force
        and package_current
        and _existing_topology_artifact_matches_options(spec, selector_options)
        and _generated_assembly_glb_closure_current(spec)
    ):
        logger.debug(f"reused current GLB/topology: {_display_path(render_package_dir(spec.entry_path))}")
        return GeneratedStepResult(spec=spec, scene=scene)

    jobs: list[_ArtifactJob] = []

    artifact_results: dict[str, object] = {}

    if spec.step_export_path is not None:
        def step_export_job() -> Path:
            # On-demand text STEP (--step). gen_step never writes a STEP, so serialize the
            # in-memory compound the generator produced; for an imported source the .step
            # already exists, so copy it to the requested path.
            from cadgen.step_export import export_build123d_step_file

            target = spec.step_export_path
            target.parent.mkdir(parents=True, exist_ok=True)
            source_compound = getattr(scene, "source_compound", None)
            if source_compound is not None:
                export_build123d_step_file(
                    source_compound,
                    target,
                    text_to_cad_entry_kind=spec.kind,
                    source_path=(str(getattr(scene, "source_path", "") or "") or None),
                    source_hash=(str(getattr(scene, "source_hash", "") or "") or None),
                )
            elif spec.step_path is not None and spec.step_path.is_file() and spec.step_path.resolve() != target.resolve():
                shutil.copyfile(spec.step_path, target)
            return target

        jobs.append(_ArtifactJob("STEP", step_export_job))

    # UNIFIED render artifact: every model — part or assembly, generated or imported — is
    # a component-GLB PACKAGE (a directory at __cadgen__/models/<entry>: assembly.json
    # descriptor + content-addressed components). An assembly introspects its
    # placed children as occurrences; a part is one occurrence/one component. The
    # part/assembly choice is the *authored* kind (spec.kind, from generator metadata or STEP
    # inference) — never guessed from geometry — and is recorded as entryKind on the
    # descriptor. There is no monolithic GLB and no file-vs-dir split.
    source_compound = getattr(scene, "source_compound", None)
    single_component = spec.kind != "assembly"
    package_provenance = _assembly_provenance_manifest(
        scene, selector_options=selector_options, step_path=spec.step_path, entry_kind=spec.kind
    )

    def component_package_job() -> dict[str, object]:
        # Lazy import: component_package imports from this module, so a top-level
        # import would cycle.
        from cadgen._internal.component_package import build_package_from_compound

        shape = source_compound
        if shape is None:
            # Imported STEP (no generator compound): package its geometry directly. An
            # imported assembly re-imports to a compound of placed solids; a part is one.
            from build123d import import_step

            shape = import_step(spec.step_path)
        return build_package_from_compound(
            shape,
            package_dir=render_package_dir(spec.entry_path),
            # The descriptor's rootName is a plain model name, not a repo path (which would leak
            # the arbitrary `models/` root into a bundle meant to be hosted/relocated anywhere).
            root_name=spec.step_path.stem,
            single_component=single_component,
            force=force,
            provenance=package_provenance,
            linear_deflection=selector_options.linear_deflection,
            angular_deflection=selector_options.angular_deflection,
            progress=progress,
        )

    jobs.append(_ArtifactJob("GLB package", component_package_job))

    artifact_results.update(_run_artifact_jobs(jobs, logger=logger))
    # The render artifact is the component-GLB package; whole-model selector topology is
    # extracted on demand by ensure_step_topology_artifact (inspect/selection renders), so
    # generation no longer returns a selector bundle.
    return GeneratedStepResult(spec=spec, scene=scene, selector_bundle=None)


def _generate_step_outputs(
    spec: EntrySpec,
    *,
    entries_by_step_path: dict[Path, EntrySpec],
    force: bool = False,
    logger: CliLogger | None = None,
    progress: object | None = None,
) -> GeneratedStepResult:
    preloaded_scene: LoadedStepScene | None = None
    # An on-demand output (mesh sidecar or --step export) must run even when the package is
    # current, so its presence defeats the reuse fast path.
    has_extra_outputs = _spec_requests_extra_outputs(spec)
    # Reuse fast path: skip the build when the component-GLB package is already present and
    # current and nothing forces a run. A generated model's freshness rides on its recorded
    # source closure; an imported/committed STEP's freshness rides on the STEP hash recorded in
    # the package (verified inside the artifact-matches gate), so it needs no closure check.
    if (
        not force
        and not has_extra_outputs
        and _assembly_glb_package_current(spec)
        and _existing_topology_artifact_matches_spec_without_scene(spec)
        and (spec.source != "generated" or _generated_assembly_glb_closure_current(spec))
    ):
        if logger is not None:
            logger.debug(f"reused current GLB/topology: {_display_path(render_package_dir(spec.entry_path))}")
        return GeneratedStepResult(spec=spec, scene=None)
    output_kwargs: dict[str, object] = {
        "entries_by_step_path": entries_by_step_path,
        "force": force,
        "progress": progress,
    }
    if logger is not None:
        output_kwargs["logger"] = logger
    if spec.source == "generated":
        preloaded_scene = run_script_generator(
            spec,
            "gen_step",
            logger=logger,
            force=force,
            progress=progress,
        )
        spec = _effective_step_spec_for_scene(spec, preloaded_scene)
        if spec.step_path is not None:
            output_kwargs["entries_by_step_path"] = {
                **entries_by_step_path,
                spec.step_path.resolve(): spec,
            }
        output_kwargs["preloaded_scene"] = preloaded_scene
        # gen_step never writes a STEP, so the artifact pipeline must not require one.
        output_kwargs["require_step_file"] = False
    else:
        # Imported/committed STEP target (kind supplied by the caller or inferred upstream):
        # _generate_part_outputs loads + meshes the on-disk STEP and emits the same flat
        # component-GLB package. Without this branch the function fell off the end and silently
        # returned None — no package written — while the CLI still reported success.
        output_kwargs["require_step_file"] = True
    return _generate_part_outputs(spec, **output_kwargs)


def _generate_step_outputs_for_cli(
    spec: EntrySpec,
    *,
    entries_by_step_path: dict[Path, EntrySpec],
    logger: CliLogger,
    force: bool = False,
    progress: object | None = None,
) -> GeneratedStepResult:
    kwargs: dict[str, object] = {
        "entries_by_step_path": entries_by_step_path,
        "progress": progress,
    }
    if force:
        kwargs["force"] = True
    if logger.verbose:
        kwargs["logger"] = logger
    return _generate_step_outputs(spec, **kwargs)


def _selected_specs_for_targets(
    targets: Sequence[str],
    *,
    step_options: StepImportOptions | None = None,
    expected_output_suffixes: tuple[str, ...] | None = None,
    tool_name: str = "CAD",
    include_output_paths: bool = False,
) -> tuple[list[EntrySpec], list[EntrySpec]] | tuple[list[EntrySpec], list[EntrySpec], list[Path | None]]:
    step_options = step_options or StepImportOptions()
    target_specs = (
        _parse_cli_target_specs(
            targets,
            expected_suffixes=expected_output_suffixes,
            tool_name=tool_name,
        )
        if expected_output_suffixes is not None
        else [_CliTargetSpec(target=str(target or "").strip()) for target in targets]
    )
    explicit_specs: list[EntrySpec] = []
    output_paths: list[Path | None] = []
    unresolved_targets: list[str] = []
    for target_spec in target_specs:
        target_text = target_spec.target
        target_path = Path(target_text)
        resolved = target_path.resolve() if target_path.is_absolute() else (Path.cwd() / target_path).resolve()
        source = (
            source_from_path(resolved, step_options=step_options)
            if resolved.exists()
            else None
        )
        if source is None:
            unresolved_targets.append(target_text)
            continue
        explicit_specs.append(_apply_step_options_to_spec(_entry_spec_from_source(source), step_options))
        output_paths.append(target_spec.output_path)

    if not unresolved_targets:
        expanded_specs = _expand_specs_with_file_dependencies(explicit_specs)
        if include_output_paths:
            return expanded_specs, explicit_specs, output_paths
        return expanded_specs, explicit_specs

    unresolved = ", ".join(unresolved_targets)
    raise FileNotFoundError(
        "CAD target path not found or not a supported source file: "
        f"{unresolved}. Pass a Python generator or STEP/STP file path."
    )


def _expand_specs_with_file_dependencies(specs: Sequence[EntrySpec]) -> list[EntrySpec]:
    # Shape-only generators don't expose a static recipe to walk for dependency
    # expansion. The Python source-closure capture in run_script_generator picks
    # up generator-side .py changes; child STEP changes require --force.
    return list(specs)


def _entries_by_step_path(specs: Sequence[EntrySpec]) -> dict[Path, EntrySpec]:
    return {
        spec.step_path.resolve(): spec
        for spec in specs
        if spec.step_path is not None
    }


def _validate_step_target(spec: EntrySpec, *, tool_name: str) -> None:
    if spec.step_path is None:
        raise ValueError(f"{tool_name} target has no STEP path: {spec.source_ref}")
    if spec.source == "generated":
        metadata = spec.generator_metadata
        if metadata is None or not metadata.has_gen_step:
            raise ValueError(f"{tool_name} target does not define gen_step(): {spec.source_ref}")
        return
    raise ValueError(
        f"{tool_name} builds gen_step() Python sources only: {spec.source_ref}. "
        "Imported STEP/STP files get render artifacts on demand (inspect, snapshot, CAD Viewer)."
    )


def _validate_dxf_target(spec: EntrySpec) -> None:
    metadata = spec.generator_metadata
    if spec.source != "generated" or spec.script_path is None or metadata is None:
        raise ValueError(f"dxf expected a generated Python source target: {spec.source_ref}")
    if not metadata.has_gen_dxf:
        raise ValueError(f"dxf target does not define gen_dxf(): {spec.source_ref}")
    if spec.dxf_path is None:
        raise ValueError(f"dxf target has no configured DXF output: {spec.source_ref}")


def _generated_output_summary(spec: EntrySpec) -> str:
    if spec.step_path is not None:
        return f"generated {spec.kind} STEP: {_display_path(spec.step_path)}"
    return f"processed: {spec.source_ref}"


def _generated_python_glb_summary(spec: EntrySpec) -> str:
    if spec.step_path is not None:
        return f"generated {spec.kind} GLB/topology artifact: {_display_path(render_package_dir(spec.entry_path))}"
    return f"processed: {spec.source_ref}"


def _generated_dxf_summary(spec: EntrySpec) -> str:
    if spec.dxf_export_path is not None:
        return f"generated DXF: {_display_path(spec.dxf_export_path)}"
    if spec.script_path is not None:
        return (
            "generated DXF drawing package: "
            f"{_display_path(render_package_dir(spec.script_path))}"
        )
    return f"processed: {spec.source_ref}"


class _SkippedGeneration:
    """Marker: the lock holder ahead of us had already produced a current package."""

    __slots__ = ("spec",)

    def __init__(self, spec: EntrySpec) -> None:
        self.spec = spec


def _spec_output_dir(spec: EntrySpec, generator_name: str) -> Path | None:
    """The coordinated output directory for this spec's generator, if it has one."""
    if generator_name == "gen_step" and spec.step_path is not None:
        return render_package_dir(spec.entry_path)
    if generator_name == "gen_dxf" and spec.script_path is not None:
        return render_package_dir(spec.script_path)
    return None


def _track_spec_generation(
    spec: EntrySpec,
    generator_name: str,
    *,
    intent: str = "write",
    logger: CliLogger | None = None,
) -> contextlib.AbstractContextManager[object]:
    """Coordinate a generator run against the model's render package.

    ``intent`` picks the SENTINEL, and the distinction is the whole point of there being
    two. A run that will rewrite the package takes the writer lock, which makes a reader
    hide the artifact and show a build. A run that merely OCCUPIES the generator and
    writes the package nothing -- an export, an on-demand topology extraction, an
    interference check -- takes the generator lock instead. Taking the writer lock for
    those made a fully-current model report `generating` with an empty bar for the whole
    length of an export.

    The two sentinels are different files, so they do NOT exclude each other: a build and
    an export of one model each run its ``gen_step()``, concurrently, in separate
    processes. That is duplicated work rather than a hazard (no shared in-process state,
    different outputs), and it is the price of letting a reader tell "being rewritten"
    from "generator busy" -- see :func:`cadgen.coordination.generator_busy`.
    """
    output_dir = _spec_output_dir(spec, generator_name)
    if output_dir is None:
        return contextlib.nullcontext()
    on_wait = lock_wait_notice(logger, spec.source_ref)
    if intent == "generate":
        return generator_busy(STEP_PACKAGE, output_dir, on_wait=on_wait)
    return exclusive(write_lock_path(output_dir), on_wait=on_wait)


def _run_with_spec_generation_status(
    spec: EntrySpec,
    generator_name: str,
    action: Callable[..., object],
    *,
    skip_if_current: Callable[[EntrySpec], bool] | None = None,
    progress_sink: object | None = None,
    logger: CliLogger | None = None,
) -> object:
    """Run ``action`` while holding the model's build lock, reporting its progress.

    Delegates to :func:`cadgen.coordination.artifact_build`, which is the SAME primitive
    ``cadgen.step_artifact`` uses. That shared implementation is the point: the lock, the
    status record and the post-lock currency re-check used to be assembled by hand at each
    producer, and the two producers had drifted -- this one re-checked under the lock,
    step_artifact's did not, so a queued viewer build redid a peer's whole generator+mesh.

    ``skip_if_current`` is re-evaluated AFTER the lock is acquired. The pre-lock fast path
    cannot cover the concurrent case: it ran before the other build existed.

    ``action`` is called as ``action(spec, run)``; ``run`` is the progress reporter.
    """
    kind = DRAWING_PACKAGE if generator_name == "gen_dxf" else STEP_PACKAGE
    # No output dir means no lock, so there is nothing to wait on and no ref to name in a
    # notice -- and a spec that never reaches a lock is not required to have one.
    output_dir = _spec_output_dir(spec, generator_name)
    with artifact_build(
        kind,
        output_dir,
        is_current=(lambda: bool(skip_if_current(spec))) if skip_if_current is not None else None,
        sink=progress_sink,
        on_wait=lock_wait_notice(logger, spec.source_ref) if output_dir is not None else None,
    ) as run:
        if run.skipped:
            return _SkippedGeneration(spec)
        return action(spec, run)


def _progress_status_text(event: ProgressEvent, *, fallback: str) -> str:
    """One status-board row for a build in flight.

    A determinate phase reports its real count (``31/50``); an opaque one reports only
    which phase is running, with the bar sitting wherever the phase weighting puts it.
    Nothing here invents a denominator the build does not have."""
    if event.finished:
        return fallback
    label = (event.label or fallback).lower()
    bar = f"{render_progress_bar(event.ratio)} {int(event.ratio * 100):>3d}%"
    if event.determinate and event.total:
        return f"{bar}  {label} {event.done}/{event.total}"
    return f"{bar}  {label}"


def _run_selected_specs(
    selected_specs: Sequence[EntrySpec],
    *,
    action_status: str = "Generating...",
    done_status: str = "Generated",
    action: Callable[..., object],
    logger: CliLogger,
    success_message: Callable[[EntrySpec], str] | None = _generated_output_summary,
) -> list[object]:
    """Run ``action`` for each spec, narrating to ``logger`` and painting one progress line.

    A generator's own prints go straight through to stdout: the CLIs reserve stdout for the
    result (``--json``) and put every log line on stderr, so there is nothing to protect it
    from. Progress is a transient tty line that erases itself — see
    :func:`_cli_progress_line`, which stays silent under ``--verbose`` where the logger is
    already narrating every stage. The sidecar is written either way, so an open CAD Viewer
    tracks the build regardless of what this prints.
    """
    results: list[object] = []
    for spec in selected_specs:
        logger.debug(f"{action_status} {spec.source_ref}")
        with _cli_progress_line(spec, logger=logger, fallback=action_status) as progress_sink:
            with logger.timed(f"{done_status.lower()} {spec.source_ref}"):
                result = action(spec, progress_sink)
        results.append(result)
        if isinstance(result, _SkippedGeneration):
            logger.info(f"{spec.cad_ref} was built by a concurrent run; skipped")
        elif success_message is not None:
            message_spec = result.spec if isinstance(result, GeneratedStepResult) else spec
            logger.info(success_message(message_spec))
    return results


def _manifest_source_closure_unchanged(manifest: Mapping[str, object], base: Path) -> bool:
    """Whether a topology manifest's recorded source closure re-hashes unchanged.

    The closure is the generator's Python import reach, so a changed generator or
    shared helper invalidates it — and so does a composed child when it is composed
    the documented way, by importing its ``.step.py``. A child read as a raw ``.step``
    file is data, not a closure input; ``_rebuild_stale_assembly_children`` keeps
    generated children current instead. ``base`` is the model folder the recorded
    closure paths are relative to. Returns False when no usable closure was recorded."""
    recorded_hash = str(manifest.get("sourceClosureHash") or "").strip()
    recorded_files = manifest.get("sourceClosureFiles")
    if not recorded_hash or not isinstance(recorded_files, list) or not recorded_files:
        return False
    return closure_hash_matches(recorded_hash, recorded_files, base=base)


def _assembly_is_current(spec: EntrySpec) -> bool:
    """Whether a generated model's render package is already up to date, so
    regeneration (gen_step + mesh + emit) can be skipped entirely.

    gen_step no longer writes a STEP, so freshness rides on the package
    descriptor's recorded source closure (the generator's Python import reach)
    re-hashing unchanged — not an on-disk STEP hash. Parts and assemblies are
    both packages and share this gate.
    """
    if spec.source != "generated" or spec.step_path is None:
        return False
    return _generated_assembly_glb_closure_current(spec)


def _generated_assembly_glb_closure_current(spec: EntrySpec) -> bool:
    """Whether a generated model's existing render package still matches its
    source closure (the generator's Python import reach). Imported models have no
    closure and are unaffected (return True; their stepHash gate handles freshness).

    Reads the closure from the package descriptor (assembly.json), which the
    dir-aware manifest reader returns. A changed generator or shared helper
    invalidates the closure; see :func:`_manifest_source_closure_unchanged` for how
    composed children are covered."""
    if spec.source != "generated":
        return True
    if spec.step_path is None:
        return False
    artifact_path = render_package_dir(spec.entry_path)
    if not artifact_path.exists():
        return False
    manifest = read_step_topology_manifest_from_glb(artifact_path)
    if not isinstance(manifest, dict):
        return False
    return _manifest_source_closure_unchanged(manifest, spec.step_path.parent)


def _assembly_glb_package_current(spec: EntrySpec) -> bool:
    """Whether the sibling component-GLB package exists with every referenced
    component present. Paired with the closure gate (which detects source
    changes), so this only guards the package's own existence — a missing/partial
    package forces the emit job to run. Every generated model is a package."""
    if spec.step_path is None:
        return False
    from cadgen._internal.component_package import assembly_package_current

    # The render package is keyed by the ENTRY filename (`<name>.step.py` for a
    # generated model), not the logical step path — keying by step_path checked
    # a directory that never exists and forced a rebuild on every run.
    return assembly_package_current(spec.entry_path)


def _generated_child_is_stale(child_spec: EntrySpec, *, force: bool) -> bool:
    """Whether a generated child part must be rebuilt before composing a parent.

    Detection order:
    1. force, or a missing/unhydrated STEP -> stale.
    2. Recorded import closure (sound, incl. transitive sys.path-loaded deps):
       re-hash the recorded closure files and compare. This is the precise path.
    3. Fallback when no closure was recorded (artifacts predating this feature,
       or minimal fixtures): compare the script's own-file source hash to the
       sourceHash recorded with the STEP. Catches own-file edits; transitive-dep
       detection resumes once the child is regenerated with a closure.
    4. If nothing was recorded, do not rebuild blindly (avoid mass rebuilds and
       false positives on artifacts that carry no provenance).
    """
    if child_spec.source != "generated" or child_spec.script_path is None or child_spec.step_path is None:
        return False
    if force:
        return True
    # gen_step writes no STEP — the render GLB/package is the artifact, so freshness keys
    # on it. A missing/unhydrated artifact (file GLB or package directory) is stale.
    artifact_path = render_package_dir(child_spec.entry_path)
    if not artifact_path.exists() or _is_git_lfs_pointer(artifact_path):
        return True
    manifest = read_step_topology_manifest_from_glb(artifact_path)
    if isinstance(manifest, dict):
        recorded_hash = str(manifest.get("sourceClosureHash") or "").strip()
        recorded_files = manifest.get("sourceClosureFiles")
        if recorded_hash and isinstance(recorded_files, list) and recorded_files:
            return not closure_hash_matches(
                recorded_hash, recorded_files, base=child_spec.step_path.parent
            )
        recorded_source_hash = str(manifest.get("sourceHash") or "").strip()
        if recorded_source_hash:
            return python_source_hash(child_spec.script_path).source_hash != recorded_source_hash
    return False


def _rebuild_child_in_subprocess(child_spec: EntrySpec) -> None:
    """Rebuild one stale child in a clean subprocess.

    A fresh interpreter is required so the child's runtime import closure is
    captured accurately: the current process has already imported the part
    modules (the parent generator imports them), which would make an in-process
    sys.modules delta miss shared dependencies."""
    bootstrap = (
        "import sys\n"
        "from cadgen._internal.generation import generate_step_targets\n"
        "sys.exit(generate_step_targets([sys.argv[1]], force=True))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", bootstrap, str(child_spec.script_path)],
        cwd=str(Path.cwd()),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            f"Failed to rebuild stale subcomponent {child_spec.source_ref}:\n{detail}"
        )


def _timed_rebuild(child: EntrySpec, *, logger: CliLogger | None) -> None:
    if logger is not None:
        with logger.timed(f"rebuild stale subcomponent {child.source_ref}"):
            _rebuild_child_in_subprocess(child)
    else:
        _rebuild_child_in_subprocess(child)


def _rebuild_children_parallel(
    children: Sequence[EntrySpec],
    *,
    logger: CliLogger | None,
) -> list[str]:
    """Rebuild independent leaf children concurrently in bounded subprocesses.

    Each rebuilds in its own clean interpreter (sound closure capture), so they
    share no in-process state and parallelize freely. Their build123d imports
    overlap, which is what removes the sequential per-child import overhead.
    Errors are collected so one failure doesn't mask the others. Returns the
    source refs in the input order (deterministic), regardless of finish order."""
    if len(children) <= 1:
        for child in children:
            _timed_rebuild(child, logger=logger)
        return [child.source_ref for child in children]

    max_workers = min(len(children), max(1, (os.cpu_count() or 2) - 1))
    if logger is not None:
        logger.debug(f"rebuilding {len(children)} stale subcomponents (up to {max_workers} parallel)")

    def run_one(child: EntrySpec) -> tuple[str, float, Exception | None]:
        started = time.perf_counter()
        try:
            _rebuild_child_in_subprocess(child)
            return child.source_ref, time.perf_counter() - started, None
        except Exception as exc:  # aggregated and re-raised below
            return child.source_ref, time.perf_counter() - started, exc

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(run_one, children))

    rebuilt: list[str] = []
    errors: list[tuple[str, Exception]] = []
    for source_ref, elapsed, exc in results:
        if exc is not None:
            errors.append((source_ref, exc))
            continue
        rebuilt.append(source_ref)
        if logger is not None:
            logger.debug(f"rebuilt subcomponent {source_ref} in {elapsed:.2f}s")
    if errors:
        joined = "\n".join(f"  {source_ref}: {exc}" for source_ref, exc in errors)
        raise RuntimeError(f"Failed to rebuild {len(errors)} stale subcomponent(s):\n{joined}")
    return rebuilt


def _rebuild_stale_assembly_children(
    all_specs: Sequence[EntrySpec],
    selected_specs: Sequence[EntrySpec],
    *,
    force: bool,
    logger: CliLogger | None,
) -> list[str]:
    """Rebuild generated child parts of selected assemblies whose source changed.

    Reuses the already-expanded ``all_specs`` (no extra source discovery).
    Independent leaf parts rebuild concurrently; sub-assembly children rebuild
    sequentially afterward in leaf-first (deepest-first) order, since each
    composes from its own children and its subprocess force-rebuilds that
    subtree. Returns the source refs that were rebuilt."""
    has_assembly_target = any(
        spec.kind == "assembly" and spec.source == "generated" for spec in selected_specs
    )
    if not has_assembly_target:
        return []
    selected_refs = {spec.source_ref for spec in selected_specs}
    seen: set[str] = set()
    stale_leaves: list[EntrySpec] = []
    stale_assemblies: list[EntrySpec] = []
    # all_specs lists parents before dependencies; reversing yields leaf-first.
    for child in reversed(list(all_specs)):
        if child.source_ref in selected_refs or child.source_ref in seen:
            continue
        seen.add(child.source_ref)
        if not _generated_child_is_stale(child, force=force):
            continue
        if child.kind == "assembly":
            stale_assemblies.append(child)
        else:
            stale_leaves.append(child)
    if not stale_leaves and not stale_assemblies:
        return []

    rebuilt = _rebuild_children_parallel(stale_leaves, logger=logger)
    for child in stale_assemblies:
        _timed_rebuild(child, logger=logger)
        rebuilt.append(child.source_ref)

    if rebuilt and logger is not None:
        logger.info(f"rebuilt {len(rebuilt)} stale subcomponent(s): {', '.join(rebuilt)}")
    return rebuilt


def generate_step_targets(
    targets: Sequence[str],
    *,
    step_options: StepImportOptions | None = None,
    force: bool = False,
    verbose: bool = False,
    json_output: bool = False,
) -> int:
    """Build render packages for ``targets``. Returns the process exit code.

    ``json_output`` additionally prints one JSON line per target to STDOUT. The exit code
    alone cannot say WHICH targets were rebuilt and which were already current, and the
    logger's prose goes to stderr by design -- so without this a caller reading the streams
    apart had no machine-readable result at all.
    """
    tool_name = "scripts/gen"
    logger = CliLogger("scripts/gen", verbose=verbose)
    reported: list[dict[str, object]] = []

    def _emit(spec: EntrySpec, outcome: str) -> None:
        reported.append(
            {
                "ok": True,
                "sourceRef": spec.source_ref,
                "cadPath": spec.cad_ref,
                "kind": spec.kind,
                "outcome": outcome,
                "packagePath": _display_path(render_package_dir(spec.entry_path)),
            }
        )

    def _flush() -> None:
        # STDOUT IS THE RESULT, on every CLI. `gen` used to print nothing there at all --
        # its only output was the logger's prose on stderr -- so a caller reading the two
        # streams apart got an exit code and nothing else, while export, snapshot, validate
        # and inspect all answered on stdout. One line per target, `outcome path`, upgraded
        # to JSON by --json.
        for entry in reported:
            if json_output:
                print(json.dumps(entry, separators=(",", ":")))
            else:
                print(f"{entry['outcome']} {entry['packagePath']}")
    all_specs, selected_specs, target_output_paths = _selected_specs_for_targets(
        targets,
        step_options=step_options,
        expected_output_suffixes=(".step",),
        tool_name=tool_name,
        include_output_paths=True,
    )
    for spec in selected_specs:
        _validate_step_target(spec, tool_name=tool_name)
    selected_specs = _apply_step_output_overrides(
        selected_specs,
        output_paths=target_output_paths,
        all_specs=all_specs,
        tool_name=tool_name,
    )
    if step_options is not None and step_options.has_metadata:
        selected_specs = [_apply_step_options_to_spec(spec, step_options) for spec in selected_specs]
    _rebuild_stale_assembly_children(all_specs, selected_specs, force=force, logger=logger)
    # No-op fast path: skip recomposing a generated assembly whose source closure
    # (the generator's Python import reach) is unchanged. Runs after the
    # child rebuild so a just-rebuilt child correctly invalidates the closure. Only
    # for plain in-place regeneration (no --force or output overrides).
    no_output_override = not any(path is not None for path in target_output_paths)
    if not force and no_output_override:
        current_specs = [
            spec
            for spec in selected_specs
            # An explicit STEP export (--write-step) must be written even when the
            # compose is current, so it keeps the spec in the run.
            if not _spec_requests_extra_outputs(spec)
            and _assembly_is_current(spec)
            and _assembly_glb_package_current(spec)
        ]
        if current_specs:
            for spec in current_specs:
                logger.info(f"{spec.cad_ref} is current; skipped recompose")
                _emit(spec, "current")
            current_refs = {spec.source_ref for spec in current_specs}
            selected_specs = [spec for spec in selected_specs if spec.source_ref not in current_refs]
            if not selected_specs:
                logger.total()
                _flush()
                return 0
    entries_by_step_path = _entries_by_step_path([*all_specs, *selected_specs])

    # Same condition as the pre-lock fast path above, re-checked once the lock is held
    # so a run that queued behind a concurrent build of this model no-ops instead of
    # rebuilding it. --force and explicit extra outputs always do the work.
    def _built_by_a_peer(spec: EntrySpec) -> bool:
        if force or not no_output_override or _spec_requests_extra_outputs(spec):
            return False
        return _assembly_is_current(spec) and _assembly_glb_package_current(spec)

    def generate_step(spec: EntrySpec, progress_sink: object | None = None) -> object:
        # The lock and the progress record are now one thing, keyed by the same package
        # dir, so a CAD Viewer polling this model's artifact status picks up exactly the
        # run that is holding the lock -- and cannot pick up a previous run's leftovers.
        def build(tracked_spec: EntrySpec, reporter: object) -> object:
            return _generate_step_outputs_for_cli(
                tracked_spec,
                entries_by_step_path=entries_by_step_path,
                logger=logger,
                force=force,
                progress=reporter,
            )

        return _run_with_spec_generation_status(
            spec,
            "gen_step",
            build,
            skip_if_current=_built_by_a_peer,
            progress_sink=progress_sink,
            logger=logger,
        )

    results = _run_selected_specs(
        selected_specs,
        action=generate_step,
        logger=logger,
        success_message=_generated_python_glb_summary,
    )
    for spec, result in zip(selected_specs, results):
        _emit(spec, "skipped-peer" if isinstance(result, _SkippedGeneration) else "built")
    logger.total()
    _flush()
    return 0


def generate_dxf_targets(
    targets: Sequence[str],
    *,
    output: str | Path | None = None,
    write_dxf: bool = False,
    force: bool = False,
    verbose: bool = False,
) -> int:
    from cadgen._internal.drawing_package import drawing_package_current

    tool_name = "dxf"
    logger = CliLogger("scripts/gen", verbose=verbose)
    if output is not None and targets_include_output_pairs(targets):
        raise ValueError(f"{tool_name} --output cannot be combined with SOURCE=OUTPUT targets")
    output_path = _resolve_cli_output_path(output, expected_suffixes=(".dxf",), tool_name=tool_name)
    all_specs, selected_specs, target_output_paths = _selected_specs_for_targets(
        targets,
        expected_output_suffixes=(".dxf",),
        tool_name=tool_name,
        include_output_paths=True,
    )
    for spec in selected_specs:
        _validate_dxf_target(spec)
    selected_specs = _apply_dxf_output_override(
        selected_specs,
        output_path=output_path,
        all_specs=all_specs,
        tool_name=tool_name,
    )
    selected_specs = _apply_dxf_output_overrides(
        selected_specs,
        output_paths=target_output_paths,
        all_specs=all_specs,
        tool_name=tool_name,
    )
    if write_dxf:
        # The sibling `<name>.dxf` is written on demand only (mirror of `--step`); the
        # default build product is the drawing package under __cadgen__/models/.
        selected_specs = [
            spec if spec.dxf_export_path is not None else replace(spec, dxf_export_path=spec.dxf_path)
            for spec in selected_specs
        ]
    # No-op fast path: skip regenerating a drawing whose source closure is unchanged.
    # An export request on a current package is satisfied from the cache (copy +
    # identity re-point) instead of re-running the generator.
    if not force:
        current_specs = [
            spec
            for spec in selected_specs
            if spec.script_path is not None and drawing_package_current(spec.script_path)
        ]
        if current_specs:
            from cadgen._internal.drawing_package import export_drawing_dxf

            for spec in current_specs:
                if spec.dxf_export_path is not None:
                    export_drawing_dxf(spec.script_path, spec.dxf_export_path)
                    logger.info(
                        f"{spec.cad_ref} is current; exported cached DXF: "
                        f"{_display_path(spec.dxf_export_path)}"
                    )
                else:
                    logger.info(f"{spec.cad_ref} is current; skipped regeneration")
            current_refs = {spec.source_ref for spec in current_specs}
            selected_specs = [spec for spec in selected_specs if spec.source_ref not in current_refs]
    if selected_specs:
        # Re-checked under the lock, like the STEP path: a run that queued behind a
        # concurrent build of this drawing must not regenerate it. An export request
        # still has to write its file, so it never skips.
        def _built_by_a_peer(spec: EntrySpec) -> bool:
            if force or spec.dxf_export_path is not None or spec.script_path is None:
                return False
            return drawing_package_current(spec.script_path)

        _run_selected_specs(
            selected_specs,
            # A drawing build DOES have countable stages -- DRAWING_PACKAGE declares
            # parse/mesh/write, reported by the Node child while this process holds the
            # lock -- so the sink is threaded through rather than dropped. It was dropped
            # on the belief that a drawing is "one opaque generator run", which was true
            # only of the Python half.
            action=lambda spec, progress_sink=None: _run_with_spec_generation_status(
                spec,
                "gen_dxf",
                lambda tracked_spec, reporter: run_script_generator(
                    tracked_spec, "gen_dxf", logger=logger, progress=reporter
                ),
                skip_if_current=_built_by_a_peer,
                progress_sink=progress_sink,
                logger=logger,
            ),
            logger=logger,
            success_message=_generated_dxf_summary,
        )
    logger.total()
    return 0


def run_tool_cli(
    argv: Sequence[str] | None,
    *,
    prog: str,
    description: str,
    action: Callable[..., int],
    target_help: str | None = None,
    output_help: str | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog=prog, description=description)
    parser.add_argument(
        "targets",
        nargs="+",
        help=target_help or "Explicit Python generator or STEP/STP file path to generate.",
    )
    if output_help is not None:
        parser.add_argument("-o", "--output", metavar="PATH", help=output_help)
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed progress and timing information.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    if output_help is not None:
        if args.output is not None:
            if targets_include_output_pairs(args.targets):
                parser.error("--output cannot be combined with SOURCE=OUTPUT targets")
            if len(args.targets) != 1:
                parser.error("--output can only be used with exactly one target")
        return action(args.targets, output=args.output, verbose=bool(args.verbose))
    return action(args.targets, verbose=bool(args.verbose))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CAD generation support library.")
    parser.parse_args(list(argv) if argv is not None else None)
    parser.error("cadgen.generation is a library module.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
