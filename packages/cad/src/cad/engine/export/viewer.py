"""Read-only viewer exports of a specified document, never a source build.

Only the worker imports this module's helpers. The HTTP job declares one output in managed
temporary storage; nothing is inspected before it: a format the document cannot be written in
is refused by its writer.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


def fingerprint(structure: dict) -> str:
    """Content identity of a live document, independent of its served address/version."""
    fields = ("name", "units", "prototypes", "instances", "tree", "kinematics")
    return hashlib.sha256(json.dumps({k: structure.get(k) for k in fields},
                                    sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def check(source, expected: dict) -> None:
    from cad.engine.export import ExportRefused

    if "digest" in expected:
        matches = fingerprint(source.structure) == expected["digest"]
    else:
        path = source.path
        stat = path.stat() if path else None
        matches = (stat is not None and f"{stat.st_mtime_ns}-{stat.st_size}" == expected.get("version")
                   and source.structure.get("version") == expected.get("version"))
    if not matches:
        raise ExportRefused("The source changed. Open Export again to use the displayed revision.")


def original(source, target: Path, expected: dict) -> int:
    from cad.engine.export import ExportRefused

    if "version" not in expected or source.path is None or source.path.suffix.lower() != ".xbf":
        raise ExportRefused("Only an existing XBF has original XBF bytes to download.")
    check(source, expected)
    try:
        shutil.copyfile(source.path, target)
        check(source, expected)
        return target.stat().st_size
    except BaseException:
        target.unlink(missing_ok=True)
        raise
