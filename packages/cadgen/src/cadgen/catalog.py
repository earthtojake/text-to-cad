from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

from .metadata import GeneratorMetadata, normalize_mesh_numeric, parse_generator_metadata


STEP_SUFFIXES = (".step", ".stp")
# The per-folder generated-artifact home for cadgen outputs (render packages, scene
# caches, generation locks), living beside the CAD sources it derives from. Gitignored.
CADGEN_DIRNAME = "__cadgen__"
CADGEN_MODELS_DIRNAME = "models"
IGNORED_DISCOVERY_DIR_NAMES = {
    CADGEN_DIRNAME,
    "__pycache__",
    ".cache",
    ".eggs",
    ".env",
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tox",
    ".venv",
    "build",
    "dist",
    "env",
    "node_modules",
    "site-packages",
    "venv",
}
GENERATOR_NAME_MARKERS = (b"gen_step", b"gen_dxf")
DXF_GENERATOR_SUFFIX = ".dxf.py"


class CadSourceError(ValueError):
    pass


@dataclass(frozen=True)
class StepImportOptions:
    # Render-package mesh settings only. Standalone STEP/STL/3MF/GLB files are not
    # configured here — they are one-off exports owned by cadgen.step_export_target
    # (`scripts/export`), which builds and meshes the scene itself.
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
    def render_package_path(self) -> Path | None:
        if self.kind == "dxf" or self.entry_path is None:
            return None
        return render_package_dir(self.entry_path)

    @property
    def generated_paths(self) -> tuple[Path, ...]:
        paths: list[Path] = []
        if self.source == "generated":
            if self.step_path is not None:
                paths.append(self.step_path)
            if self.dxf_path is not None:
                paths.append(self.dxf_path)
        if self.render_package_path is not None:
            paths.append(self.render_package_path)
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
    resolved = path.resolve()
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


def render_package_dir(entry_path: Path) -> Path:
    # The render-artifact package directory for a CAD entry file. Every package lives
    # INSIDE the per-folder __cadgen__ directory, keyed by the ENTRY filename (the on-disk
    # file the viewer lists: `<name>.step`, `<name>.step.py`, `<name>.dxf.py`, ...), so
    # distinct entry files always get distinct packages and model folders hold only source.
    # A STEP entry's package is a self-contained component-GLB directory (assembly.json
    # descriptor + components/<hash>.glb); a `.dxf.py` entry's package is a drawing
    # directory (drawing.json descriptor + drawing.dxf).
    base = entry_path.resolve()
    return (base.parent / CADGEN_DIRNAME / CADGEN_MODELS_DIRNAME / base.name).resolve()


def _iter_python_sources(root: Path) -> tuple[CadSource, ...]:
    sources: list[CadSource] = []
    for script_path in _iter_paths(root, "*.py"):
        if not _looks_like_generator_script(script_path):
            continue
        try:
            source = _read_python_source(script_path)
        except CadSourceError as exc:
            # Directory discovery is resilient: one invalid generator (e.g. an
            # unmigrated gen_dxf() beside gen_step()) must not abort catalog-wide
            # operations on unrelated targets. Explicitly targeting the file
            # (source_from_path) still raises the pointed error.
            print(f"[cadgen] skipping invalid CAD source: {exc}", file=sys.stderr)
            continue
        if source is not None:
            sources.append(source)
    return tuple(sources)


def _generator_part_stem(script_path: Path) -> str:
    """The part name a generator script produces, independent of the source extension.

    A ``<name>.step.py`` entry generator and the legacy ``<name>.py`` both produce the logical
    STEP ``<name>.step``; a ``<name>.dxf.py`` drawing generator produces the logical
    ``<name>.dxf``. The derived artifact paths key off ``<name>`` either way —
    ``.with_suffix('.step')`` would wrongly yield ``<name>.step.step`` for a ``.step.py``
    source (and likewise for ``.dxf.py``).
    """
    name = script_path.name
    if name.endswith(".step.py"):
        return name[: -len(".step.py")]
    if name.endswith(DXF_GENERATOR_SUFFIX):
        return name[: -len(DXF_GENERATOR_SUFFIX)]
    if name.endswith(".py"):
        return name[: -len(".py")]
    return script_path.stem


def is_dxf_generator_path(script_path: Path | str) -> bool:
    return str(script_path).lower().endswith(DXF_GENERATOR_SUFFIX)


def _generator_sibling(script_path: Path, suffix: str) -> Path:
    return script_path.with_name(_generator_part_stem(script_path) + suffix)


def _dxf_generator_source(resolved_script_path: Path, metadata: GeneratorMetadata) -> CadSource:
    dxf_path = _generator_sibling(resolved_script_path, ".dxf")
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
    if is_dxf_generator_path(resolved_script_path):
        # `<name>.dxf.py` is a first-class drawing entry (mirror of `<name>.step.py`).
        if metadata.has_gen_step:
            raise CadSourceError(
                f"{_display_path(resolved_script_path)} is a .dxf.py drawing generator and must "
                "not define gen_step(); keep gen_step() in a .step.py entry"
            )
        if not metadata.has_gen_dxf:
            raise CadSourceError(
                f"{_display_path(resolved_script_path)} is a .dxf.py drawing generator and must "
                "define gen_dxf()"
            )
        return _dxf_generator_source(resolved_script_path, metadata)
    if metadata.has_gen_step and metadata.has_gen_dxf:
        raise CadSourceError(
            f"{_display_path(resolved_script_path)} defines both gen_step() and gen_dxf(); "
            "move gen_dxf() into a dedicated <name>.dxf.py drawing generator"
        )
    if not metadata.has_gen_step:
        # Plain `<name>.py` defining only gen_dxf(): the CLI stays naming-agnostic, so it is
        # still valid as an EXPLICIT gen_dxf target, but only `.dxf.py` sources are catalog
        # entries — directory catalogs skip it.
        if not allow_dxf_only:
            return None
        return _dxf_generator_source(resolved_script_path, metadata)
    if metadata.kind not in {"part", "assembly"}:
        raise CadSourceError(
            f"{_display_path(resolved_script_path)} must define a part or assembly gen_step() entry"
        )
    step_path = _generator_sibling(resolved_script_path, ".step")
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
        mesh_tolerance=None,
        mesh_angular_tolerance=None,
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
            if dirname not in IGNORED_DISCOVERY_DIR_NAMES
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
