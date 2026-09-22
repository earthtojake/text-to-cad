"""Where a part exported from the viewer is written.

The viewer hands out paths rather than bytes, because the same client runs in a
browser, in the desktop shell and in an editor, and a browser download only
means something in the first of those. So an exported part is SAVED INTO THE
PROJECT and its path reported: the file tree shows it, the agent can reference
it, and it sits beside the assembly it came from instead of in a downloads
folder that is not versioned with the work.

The bytes are built by the client from the mesh it already has on screen, so
nothing here loads the CAD kernel or generates geometry -- this writes what it
was handed, which is why it does not cross the rule that the viewer's render
path runs no generators.
"""

from __future__ import annotations

import os
import re

from .backend import ForbiddenAssetError, require_contained

__all__ = ["EXPORT_DIRECTORY", "resolve_export_target", "safe_export_name"]

#: Exports land beside the project's other format folders (STEP/, DXF/, 3MF/),
#: which is where a CAD project already keeps its outputs.
EXPORT_DIRECTORY = "STL"

_ALLOWED = re.compile(r"[^A-Za-z0-9._-]+")


def safe_export_name(name: str) -> str:
    """A single filename, never a path.

    A part is named by whoever authored the STEP, so the name arriving here is
    untrusted text: separators, ``..`` and leading dots are stripped rather than
    escaped, because a name is a name and anything that looks like traversal is
    a bug or an attack, not a filename to preserve.
    """
    stem = os.path.basename(str(name or "").strip())
    stem = _ALLOWED.sub("_", stem).strip("._-")
    stem = re.sub(r"_{2,}", "_", stem)
    if stem.lower().endswith(".stl"):
        stem = stem[:-4].rstrip("._-")
    if not stem:
        stem = "part"
    return f"{stem}.stl"


def resolve_export_target(root_path: str, name: str) -> tuple[str, str]:
    """``(absolute path, path relative to the root)`` for an exported part.

    Contained against the served root by the same check every asset route uses,
    so a crafted name cannot write outside the project even though the name
    itself has already been reduced to a bare filename.
    """
    if not root_path:
        raise ForbiddenAssetError()
    root = os.path.realpath(root_path)
    filename = safe_export_name(name)
    directory = os.path.join(root, EXPORT_DIRECTORY)
    # An existing STL/ is checked through its REAL path: a directory that is a
    # symlink out of the project would otherwise be a legal-looking way to write
    # anywhere. One that does not exist yet is checked as written, since there is
    # no link to follow and realpath would just echo it back.
    resolved_directory = os.path.realpath(directory) if os.path.isdir(directory) else directory
    require_contained(root, resolved_directory)
    target = os.path.join(directory, filename)
    require_contained(root, target)
    return target, os.path.join(EXPORT_DIRECTORY, filename)
