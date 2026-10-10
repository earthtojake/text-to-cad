"""A file's type, read from its name: one extension, or a compound one, and the format it names.

The CAD Viewer's content types (``cadgen.viewer.content_types``), snapshots, plots,
telemetry and the model formats all read a file's type here.
"""

from __future__ import annotations

import posixpath

__all__ = ["COMPOUND_EXTENSIONS", "extension_of", "format_of"]


# A document whose type is two suffixes, and the format it names: `cable.harness.yml` is a
# wiring harness, while a plain `.yml` is no CAD file at all. Each is ONE extension to
# everything below, and to every reader of a file's type in cadgen.
COMPOUND_EXTENSIONS = {".harness.yml": "harness"}


def extension_of(file_path) -> str:
    """``path.extname(...).toLowerCase()`` -- except that a name ending in one of
    :data:`COMPOUND_EXTENSIONS` answers all of it (``.harness.yml``, not ``.yml``).

    Node's semantics, which ``os.path.splitext`` does not share for leading-dot
    names: ``extname(".step")`` is ``""`` while ``splitext`` answers ``".step"``.
    """
    name = posixpath.basename(str(file_path or "").replace("\\", "/"))
    lowered = name.lower()
    for compound in COMPOUND_EXTENSIONS:
        if lowered.endswith(compound) and len(lowered) > len(compound):
            return compound
    dot = name.rfind(".")
    if dot <= 0:
        return ""
    return name[dot:].lower()


def format_of(file_path, extension=None) -> str:
    r"""A file's format: ``extension.toLowerCase().replace(/^\./, "")``, ONE leading dot,
    except that a compound extension names its own (``.harness.yml`` is a ``harness``).
    ``extension`` is the file's extension when the caller already has it."""
    ext = (extension_of(file_path) if extension is None else extension).lower()
    if ext in COMPOUND_EXTENSIONS:
        return COMPOUND_EXTENSIONS[ext]
    return ext[1:] if ext.startswith(".") else ext
