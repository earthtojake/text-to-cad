"""Which drawings document a model.

A drawing written by ``cadgen.drawing`` names its model in the DXF header
(``CADGEN_SOURCE``, a path relative to the DXF). A part does not know its
drawings, so the link back is found by reading the headers of the DXFs under
the served root. Only the HEADER section is read, as text, so a large drawing
costs a few kilobytes, and ezdxf is not needed for the scan.
"""

from __future__ import annotations

import os
from pathlib import Path

SOURCE_PROPERTY = "CADGEN_SOURCE"
_HEADER_LIMIT = 64 * 1024
_SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".cad-runtime", ".hardcore"}


def dxf_source_model(dxf_path: Path) -> str:
    """The ``CADGEN_SOURCE`` value of a DXF, or "" when it names none."""
    try:
        with open(dxf_path, "r", encoding="utf-8", errors="replace") as handle:
            head = handle.read(_HEADER_LIMIT)
    except OSError:
        return ""
    lines = head.split("\n")
    pending = False
    for index in range(len(lines) - 3):
        code = lines[index].strip()
        value = lines[index + 1].strip()
        if code == "9" and value == "$CUSTOMPROPERTYTAG":
            pending = lines[index + 3].strip() == SOURCE_PROPERTY
        elif code == "9" and value == "$CUSTOMPROPERTY" and pending:
            return lines[index + 3].strip()
        elif code == "2" and value == "ENTITIES":
            break
    return ""


def drawings_of(model_path: str | Path, root: str | Path) -> list[str]:
    """Root-relative paths (forward slashes) of the DXFs under ``root`` whose
    ``CADGEN_SOURCE`` resolves to ``model_path``, sorted."""
    target = os.path.realpath(str(model_path))
    root_path = Path(root).resolve()
    found: list[str] = []
    for directory, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if not name.lower().endswith(".dxf"):
                continue
            dxf = Path(directory) / name
            source = dxf_source_model(dxf)
            if not source:
                continue
            resolved = os.path.realpath(str((dxf.parent / source)))
            if resolved == target:
                found.append(dxf.relative_to(root_path).as_posix())
    return sorted(found)
