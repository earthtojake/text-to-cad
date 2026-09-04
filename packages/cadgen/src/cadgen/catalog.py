from __future__ import annotations

import os
import sys
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

from .metadata import GeneratorMetadata, normalize_mesh_numeric, parse_generator_metadata


STEP_SUFFIXES = (".step", ".stp")
# Discovery skips EVERY dot-directory (matching the CAD Viewer's catalog scan),
# plus these well-known build/dependency dirs. An enumerated dot-list rotted
# here once: `.claude/worktrees/` checkouts carrying pre-rename sources
# poisoned every scan run from a repo root.
IGNORED_DISCOVERY_DIR_NAMES = {
    "__pycache__",
    "build",
    "dist",
    "env",
    "node_modules",
    "site-packages",
    "venv",
}
# Cheap byte sniff before the AST parse: a decorated model script imports cadgen.
GENERATOR_NAME_MARKERS = (b"cadgen",)


class CadSourceError(ValueError):
    pass


@dataclass(frozen=True)
class StepImportOptions:
    # Render-package mesh settings only. Standalone STEP/STL/3MF/GLB files are not
    # configured here — they are one-off exports owned by cadgen.step_export_target
    # (the `cadgen stl|3mf|glb build` doors), which builds and meshes the scene itself.
    mesh_tolerance: float | None = None
    mesh_angular_tolerance: float | None = None

    @property
    def has_metadata(self) -> bool:
        return any(
            (
                self.mesh_tolerance is not None,
                self.mesh_angular_tolerance is not None,
            )
        )


@dataclass(frozen=True)
class CadSource:
    source_ref: str
    cad_ref: str
    kind: str
    source_path: Path
    source: str
    origin_path: Path
    script_path: Path | None = None
    generator_metadata: GeneratorMetadata | None = None
    step_path: Path | None = None
    dxf_path: Path | None = None
    mesh_tolerance: float | None = None
    mesh_angular_tolerance: float | None = None
    color: tuple[float, float, float, float] | None = None

    @property
    def entry_path(self) -> Path | None:
        # The actual on-disk ENTRY file the render package is keyed by: the `.step.py` generator
        # for a generated model, or the `.step`/`.stp` itself for an imported one.
        return self.script_path if self.script_path is not None else self.step_path

    @property
    def generated_paths(self) -> tuple[Path, ...]:
        # FILE outputs only — the store package dir is deliberately absent:
        # two same-content documents legally SHARE one content-keyed package,
        # so it can never be a duplicate-output identity.
        paths: list[Path] = []
        if self.source == "generated":
            if self.step_path is not None:
                paths.append(self.step_path)
            if self.dxf_path is not None:
                paths.append(self.dxf_path)
        return tuple(path.resolve() for path in paths)


def iter_cad_sources(root: Path | None = None) -> tuple[CadSource, ...]:
    # Discovery scans `root`; callers on the build path pass it explicitly. When omitted (catalog
    # listing/tooling) default to the live cwd rather than a frozen import-time root.
    root = Path.cwd().resolve() if root is None else root
    resolved_root = root.resolve()
    python_sources = _iter_python_sources(resolved_root)
    generated_step_paths = {
        source.step_path.resolve()
        for source in python_sources
        if source.step_path is not None
    }
    sources = [
        *python_sources,
        *_iter_step_sources(resolved_root, excluded_step_paths=generated_step_paths),
    ]
    by_cad_ref: dict[str, CadSource] = {}
    by_source_ref: dict[str, CadSource] = {}
    by_step_path: dict[Path, CadSource] = {}
    by_generated_path: dict[Path, CadSource] = {}
    for source in sources:
        existing = by_cad_ref.get(source.cad_ref)
        if existing is not None:
            raise CadSourceError(
                "Duplicate CAD STEP ref "
                f"{source.cad_ref!r}: {_source_label(existing)} and {_source_label(source)}"
            )
        by_cad_ref[source.cad_ref] = source
        existing_source = by_source_ref.get(source.source_ref)
        if existing_source is not None:
            raise CadSourceError(
                "Duplicate CAD source ref "
                f"{source.source_ref!r}: {_source_label(existing_source)} and {_source_label(source)}"
            )
        by_source_ref[source.source_ref] = source
        if source.step_path is not None:
            existing_step = by_step_path.get(source.step_path.resolve())
            if existing_step is not None:
                raise CadSourceError(
                    "Duplicate CAD STEP source "
                    f"{_display_path(source.step_path)}: {_source_label(existing_step)} and {_source_label(source)}"
            )
            by_step_path[source.step_path.resolve()] = source
        for generated_path in source.generated_paths:
            resolved_generated_path = generated_path.resolve()
            existing_generated = by_generated_path.get(resolved_generated_path)
            if existing_generated is not None and existing_generated.source_ref != source.source_ref:
                raise CadSourceError(
                    "Duplicate CAD generated output "
                    f"{_display_path(generated_path)}: "
                    f"{_source_label(existing_generated)} and {_source_label(source)}"
                )
            by_generated_path[resolved_generated_path] = source
    return tuple(sorted(by_cad_ref.values(), key=lambda source: source.source_ref))


def source_from_path(
    path: Path,
    *,
    step_kind: str = "part",
    step_options: StepImportOptions | None = None,
) -> CadSource | None:
    resolved = Path(path).expanduser().resolve()
    if resolved.suffix.lower() == ".py":
        return _read_python_source(resolved, allow_dxf_only=True)
    if resolved.suffix.lower() in STEP_SUFFIXES:
        return _read_step_source(resolved, kind=step_kind, options=step_options)
    return None


def source_by_cad_ref(root: Path | None = None) -> dict[str, CadSource]:
    return {source.cad_ref: source for source in iter_cad_sources(root)}


def find_source_by_cad_ref(cad_ref: str, root: Path | None = None) -> CadSource | None:
    normalized = normalize_cad_ref(cad_ref)
    return source_by_cad_ref(root).get(normalized or "")


def find_source_by_source_ref(source_ref: str, root: Path | None = None) -> CadSource | None:
    normalized = normalize_source_ref(source_ref)
    if not normalized:
        return None
    for source in iter_cad_sources(root):
        if source.source_ref == normalized:
            return source
    return None


def find_source_by_path(path: Path, root: Path | None = None) -> CadSource | None:
    resolved_path = path.resolve()
    for source in iter_cad_sources(root):
        paths = [
            source.source_path,
            source.step_path,
            source.script_path,
            source.dxf_path,
            *source.generated_paths,
        ]
        if any(candidate is not None and candidate.resolve() == resolved_path for candidate in paths):
            return source
    return None


def source_ref_from_path(path: Path) -> str:
    # Entry-identity string (sourceRef), relative to the live cwd. Has no descriptor readers and
    # is consistent within a build; the persisted model-folder-relative paths come from elsewhere.
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(Path.cwd().resolve())
    except ValueError:
        return resolved.as_posix()
    return relative.as_posix()


def cad_ref_from_step_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(Path.cwd().resolve())
    except ValueError:
        relative = PurePosixPath(resolved.as_posix())
    name = relative.name
    suffix = relative.suffix.lower()
    if suffix in STEP_SUFFIXES:
        return relative.with_suffix("").as_posix()
    raise CadSourceError(f"{_display_path(path)} is not a CAD STEP source")


def cad_ref_from_dxf_path(path: Path) -> str:
    # DXF refs KEEP the `.dxf` suffix so a `<name>.dxf.py` drawing and a `<name>.step.py`
    # model in the same folder never collide on cad_ref.
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(Path.cwd().resolve())
    except ValueError:
        relative = PurePosixPath(resolved.as_posix())
    if relative.suffix.lower() != ".dxf":
        raise CadSourceError(f"{_display_path(path)} is not a CAD DXF output path")
    return relative.as_posix()


def normalize_source_ref(raw_ref: str) -> str | None:
    normalized = str(raw_ref or "").replace("\\", "/").strip().strip("/")
    if not normalized:
        return None
    parts = normalized.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        return None
    return "/".join(parts)


def normalize_cad_ref(raw_ref: str) -> str | None:
    normalized = normalize_source_ref(raw_ref)
    if not normalized:
        return None
    suffix = PurePosixPath(normalized).suffix.lower()
    if suffix in {".py", *STEP_SUFFIXES}:
        normalized = str(PurePosixPath(normalized).with_suffix(""))
    return normalized


def artifact_path_key(entry_path: Path) -> str:
    """The model-path identity for progress records and unbuilt views:
    sha256 of the resolved artifact path, truncated. Path-keyed on purpose —
    a build's progress must be findable while the content hash it will produce
    is still unknown.

    A path that cannot be resolved (an embedded NUL, a symlink loop) keys on
    its lexical absolute form rather than raising: the viewer server derives
    this key for whatever a request names, and an odd path must be a "no
    package" answer there, not a 500."""
    import hashlib

    try:
        resolved = str(Path(entry_path).expanduser().resolve())
    except (OSError, ValueError, RuntimeError):
        resolved = os.path.abspath(str(entry_path))
    return hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:24]


# Content-hash memo for artifact files, keyed by (path, mtime_ns, size): a
# catalog scan or status poll re-asks for the same file's hash constantly,
# and rereading megabytes each time would turn polling into IO. A stale hit
# requires an edit that preserves BOTH mtime_ns and size — not a real editor.
#
# Bounded and locked: the viewer server shares this memo across request
# threads for the life of the process, and a large corpus would otherwise
# grow it without limit.
_ARTIFACT_HASH_MEMO: dict[str, tuple[int, int, str]] = {}
_ARTIFACT_HASH_MEMO_LIMIT = 4096
_ARTIFACT_HASH_MEMO_LOCK = threading.Lock()


def _remember_artifact_hash(key: str, mtime_ns: int, size: int, digest: str) -> None:
    with _ARTIFACT_HASH_MEMO_LOCK:
        if len(_ARTIFACT_HASH_MEMO) >= _ARTIFACT_HASH_MEMO_LIMIT:
            _ARTIFACT_HASH_MEMO.clear()
        _ARTIFACT_HASH_MEMO[key] = (mtime_ns, size, digest)


def artifact_file_hash(entry_path: Path) -> str | None:
    """sha256 of the artifact file's bytes, memoized; None when unreadable.

    Streamed in 1 MiB chunks: a status poll must not materialize a
    multi-hundred-MB STEP in memory to learn its key."""
    import hashlib

    try:
        resolved = Path(entry_path).expanduser().resolve()
        stat = resolved.stat()
    except (OSError, ValueError, RuntimeError):
        return None
    key = str(resolved)
    with _ARTIFACT_HASH_MEMO_LOCK:
        cached = _ARTIFACT_HASH_MEMO.get(key)
    if cached is not None and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
        return cached[2]
    digest = hashlib.sha256()
    try:
        with open(resolved, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError:
        return None
    hexdigest = digest.hexdigest()
    _remember_artifact_hash(key, stat.st_mtime_ns, stat.st_size, hexdigest)
    return hexdigest


def seed_artifact_hash(entry_path: Path, digest: str) -> None:
    """Prime the content-hash memo for a file the caller JUST wrote and
    hashed (generation's export). Saves the full-file re-read the first
    post-build resolution would otherwise pay — linear in document size."""
    resolved = Path(entry_path).expanduser().resolve()
    try:
        stat = resolved.stat()
    except OSError:
        return
    _remember_artifact_hash(str(resolved), stat.st_mtime_ns, stat.st_size, digest)


def result_tree_for(entry_path: Path) -> str | None:
    """The current tree hash behind a CAD artifact on disk, or None.

    A generated document maps to its model through the sidecar; an imported
    document is its own source (``cadgen.store.records.record_for_document``).
    The tree's flattened view (``cadgen.store.trees.flatten``) is what every
    reader that used to open a package directory reads now."""
    from cadgen.store.records import record_for_document

    record = record_for_document(Path(entry_path))
    if record is None:
        return None
    tree = str(record.get("tree") or "").strip()
    return tree or None


def result_descriptor_for(entry_path: Path) -> dict | None:
    """The flattened descriptor (legacy shape, component refs as object hashes)
    behind a CAD artifact on disk, or None when it has no current tree."""
    from cadgen.store.trees import flatten

    tree = result_tree_for(entry_path)
    return flatten(tree) if tree else None


def result_view_dir(entry_path: Path) -> Path:
    """A package-shaped VIEW (a per-process temporary directory) of the tree
    behind a CAD artifact, for consumers that need files on disk — the Node
    exporters, the selector-index composer, the snapshot page. When the artifact
    has no current tree, a deterministic never-created path, so existence checks
    answer "no result" without special cases. The store itself holds no result
    directories (``cadgen.store.view``)."""
    from cadgen.store.view import view_dir_for, views_root

    tree = result_tree_for(entry_path)
    if tree is None:
        return views_root() / f"unbuilt-{artifact_path_key(entry_path)}"
    return view_dir_for(tree)


def build_scope(entry_path: Path) -> str:
    """The progress scope for builds of this model: a path-keyed NAME (never a
    directory). ``cadgen.coordination.paths`` derives the advisory progress
    record from it; the CAD Viewer derives the same name to find that record."""
    return artifact_path_key(entry_path)


def _iter_python_sources(root: Path) -> tuple[CadSource, ...]:
    from cadgen.metadata import InvalidModelScriptError

    sources: list[CadSource] = []
    for script_path in _iter_paths(root, "*.py"):
        if not _looks_like_generator_script(script_path):
            continue
        try:
            source = _read_python_source(script_path)
        except (CadSourceError, InvalidModelScriptError, RuntimeError) as exc:
            # Directory discovery is resilient: an unparseable script or a
            # malformed model DECLARATION must not abort catalog-wide operations
            # on unrelated targets. A single model's contract violations (a dict
            # return, bad decorator args) still raise: an explicitly
            # authored model that cannot build must fail loudly everywhere.
            print(f"[cadgen] skipping invalid CAD source: {exc}", file=sys.stderr)
            continue
        if source is not None:
            sources.append(source)
    return tuple(sources)


def _dxf_generator_source(resolved_script_path: Path, metadata: GeneratorMetadata) -> CadSource:
    from cadgen.metadata import resolve_model_output_path

    dxf_path = resolve_model_output_path(
        resolved_script_path, fmt="dxf", explicit_out=metadata.out_target
    )
    return CadSource(
        source_ref=source_ref_from_path(resolved_script_path),
        cad_ref=cad_ref_from_dxf_path(dxf_path),
        kind="dxf",
        source_path=resolved_script_path,
        source="generated",
        origin_path=resolved_script_path,
        script_path=resolved_script_path,
        generator_metadata=metadata,
        step_path=None,
        dxf_path=dxf_path,
        mesh_tolerance=None,
        mesh_angular_tolerance=None,
    )


def _read_python_source(script_path: Path, *, allow_dxf_only: bool = False) -> CadSource | None:
    resolved_script_path = script_path.resolve()
    metadata = parse_generator_metadata(resolved_script_path)
    if metadata is None:
        return None
    if metadata.format == "dxf":
        return _dxf_generator_source(resolved_script_path, metadata)
    if metadata.kind not in {"part", "assembly"}:
        raise CadSourceError(
            f"{_display_path(resolved_script_path)} must declare a part or assembly @step model"
        )
    from cadgen.metadata import resolve_model_output_path

    step_path = resolve_model_output_path(
        resolved_script_path, fmt="step", explicit_out=metadata.out_target
    )
    return CadSource(
        source_ref=source_ref_from_path(resolved_script_path),
        cad_ref=cad_ref_from_step_path(step_path),
        kind=metadata.kind,
        source_path=resolved_script_path,
        source="generated",
        origin_path=resolved_script_path,
        script_path=resolved_script_path,
        generator_metadata=metadata,
        step_path=step_path,
        dxf_path=None,
        mesh_tolerance=metadata.mesh_tolerance,
        mesh_angular_tolerance=metadata.mesh_angular_tolerance,
    )


def _iter_step_sources(root: Path, *, excluded_step_paths: set[Path]) -> tuple[CadSource, ...]:
    sources: list[CadSource] = []
    for pattern in ("*.step", "*.stp"):
        for step_path in _iter_paths(root, pattern):
            if step_path.resolve() in excluded_step_paths:
                continue
            sources.append(_read_step_source(step_path, kind="part"))
    return tuple(sorted(sources, key=lambda source: source.source_ref))


def _read_step_source(
    step_path: Path,
    *,
    kind: str,
    options: StepImportOptions | None = None,
) -> CadSource:
    resolved_step_path = step_path.resolve()
    options = options or StepImportOptions()
    if kind not in {"part", "assembly"}:
        raise CadSourceError(f"{_display_path(resolved_step_path)} kind must be 'part' or 'assembly'")
    if resolved_step_path.suffix.lower() not in STEP_SUFFIXES:
        raise CadSourceError(f"{_display_path(resolved_step_path)} source must end in .step or .stp")
    if not resolved_step_path.is_file():
        raise CadSourceError(
            f"{_display_path(resolved_step_path)} source does not exist"
        )
    cad_ref = cad_ref_from_step_path(resolved_step_path)

    return CadSource(
        source_ref=source_ref_from_path(resolved_step_path),
        cad_ref=cad_ref,
        kind=str(kind),
        source_path=resolved_step_path,
        source="imported",
        origin_path=resolved_step_path,
        step_path=resolved_step_path,
        mesh_tolerance=normalize_step_numeric(
            options.mesh_tolerance,
            base_path=resolved_step_path,
            field_name="mesh_tolerance",
        ),
        mesh_angular_tolerance=normalize_step_numeric(
            options.mesh_angular_tolerance,
            base_path=resolved_step_path,
            field_name="mesh_angular_tolerance",
        ),
    )


def _iter_paths(root: Path, pattern: str) -> tuple[Path, ...]:
    paths: list[Path] = []
    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            dirname
            for dirname in dirnames
            if not dirname.startswith(".") and dirname not in IGNORED_DISCOVERY_DIR_NAMES
        )
        for filename in sorted(filenames):
            if not fnmatch(filename, pattern):
                continue
            path = (Path(current_root) / filename).resolve()
            if path.is_file():
                paths.append(path)
    return tuple(paths)


def _looks_like_generator_script(script_path: Path) -> bool:
    try:
        source_bytes = script_path.read_bytes()
    except OSError:
        return False
    return any(marker in source_bytes for marker in GENERATOR_NAME_MARKERS)


def normalize_step_numeric(raw_value: object, *, base_path: Path, field_name: str) -> float | None:
    try:
        return normalize_mesh_numeric(raw_value, field_name=field_name)
    except ValueError as exc:
        raise CadSourceError(f"{_display_path(base_path)} {exc}") from exc


def normalize_step_color(
    raw_value: object,
    *,
    base_path: Path,
    field_name: str,
) -> tuple[float, float, float, float] | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, str):
        value = raw_value.strip()
        if value.startswith("#"):
            value = value[1:]
        if len(value) not in {6, 8}:
            raise CadSourceError(f"{_display_path(base_path)} {field_name} must be #RRGGBB or #RRGGBBAA")
        try:
            components = [int(value[index : index + 2], 16) / 255.0 for index in range(0, len(value), 2)]
        except ValueError as exc:
            raise CadSourceError(f"{_display_path(base_path)} {field_name} must be valid hex") from exc
    elif (
        isinstance(raw_value, Sequence)
        and not isinstance(raw_value, (bytes, bytearray))
        and len(raw_value) in {3, 4}
    ):
        components = []
        for component in raw_value:
            try:
                number = float(component)
            except (TypeError, ValueError) as exc:
                raise CadSourceError(
                    f"{_display_path(base_path)} {field_name} components must be numeric"
                ) from exc
            if not 0.0 <= number <= 1.0:
                raise CadSourceError(
                    f"{_display_path(base_path)} {field_name} components must be between 0 and 1"
                )
            components.append(number)
    else:
        raise CadSourceError(f"{_display_path(base_path)} {field_name} must be an RGB/RGBA array or hex string")
    if len(components) == 3:
        components.append(1.0)
    return (float(components[0]), float(components[1]), float(components[2]), float(components[3]))


def _source_label(source: CadSource) -> str:
    if source.script_path is not None:
        return _display_path(source.script_path)
    return _display_path(source.source_path)


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()
