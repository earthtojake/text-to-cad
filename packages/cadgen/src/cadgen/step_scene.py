"""Public STEP scene helpers for generator scripts.

The scene engine lives in :mod:`cadgen._internal.step_scene`; this module
re-exports the supported surface used by build123d generator sources that
import or compose existing STEP files. Anything not exported here is private
and may change between releases.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

__all__ = [
    "read_step",
    "load_step_scene",
    "located_shape",
    "occurrence_selector_id",
    "scene_occurrence_shape",
]

# Resolved on first touch, never at import. A model script names these at module
# top, and the freshness gate runs before the model's function body does: eagerly
# importing the scene engine (and OCP with it) would put the ~2.5s kernel import
# in front of every no-op run, which is exactly what `from cadgen import
# build123d as bd` exists to avoid.
_LAZY_EXPORTS = {
    "located_shape": "_located_shape",
    "occurrence_selector_id": "occurrence_selector_id",
    "scene_occurrence_shape": "scene_occurrence_shape",
}


def __getattr__(name: str):
    if name in _LAZY_EXPORTS:
        from cadgen._internal import step_scene as engine

        return getattr(engine, _LAZY_EXPORTS[name])
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if TYPE_CHECKING:  # pragma: no cover - mirrors the lazy exports for type checkers
    from cadgen._internal.step_scene import (
        _located_shape as located_shape,
        occurrence_selector_id,
        scene_occurrence_shape,
    )


def _record_input(step_path: Path | str, *, reader: str) -> Path:
    """Resolve a STEP a model asked for, and declare it a build input.

    Both public readers go through here, because "which cadgen function records
    what it reads" must not be a thing anyone has to remember: they all do. The
    engine's own internal loads go straight to
    :mod:`cadgen._internal.step_scene` and are unaffected — a build must not
    record its own output as its input.
    """
    resolved = Path(step_path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(
            f"{reader}: no STEP file at {resolved}. Check the path — it resolves "
            "relative to the process's working directory, so anchor a model's own "
            "inputs on its file: Path(__file__).parent / '../STEP/part.step'."
        )
    from cadgen._internal.source_hash import note_discovered_input

    note_discovered_input(resolved)
    return resolved


def load_step_scene(step_path: Path | str, **kwargs) -> Any:
    """Load a STEP's full scene (occurrence tree, colors, prototypes), AND record it.

    The scene-level twin of :func:`read_step`: same file, more structure. It
    records for the same reason — a model that walks a vendor STEP's occurrence
    tree depends on that STEP's bytes exactly as much as one that takes its
    shape.
    """
    from cadgen._internal.step_scene import load_step_scene as engine_load

    return engine_load(_record_input(step_path, reader="load_step_scene"), **kwargs)


def read_step(step_path: Path | str, *, label: str | None = None) -> Any:
    """Read a STEP file as build123d geometry, AND record it as a build input.

    Usable in a ``@step`` body (composing a vendor part into an assembly) and in
    a ``@dxf`` body (deriving a cut profile from one) alike. The returned shape
    is topologically identical to ``build123d.import_step``'s — the root itself,
    not a wrapper — with per-occurrence and prototype STEP colors applied, and it
    comes from the store, so a warm read costs tens
    of milliseconds instead of a full text-STEP re-parse.

    **The recording is the point.** Freshness used to follow a model's Python
    import reach only, which is observable: modules announce themselves. A file
    read as data announces nothing, so a model built from a vendor STEP went on
    reporting itself current after that STEP was replaced, and the only way to
    get the truth back was ``--force``. Reading through this function declares
    the file: its path and content hash join the model's closure, and the next
    run's gate re-hashes it (design/dxf-build123d.md).

    A missing file raises here rather than deep inside the importer, because
    "the vendor STEP is not where the model thinks it is" is the whole message.
    """
    from cadgen._internal.step_scene import import_step

    return import_step(_record_input(step_path, reader="read_step"), label=label)
