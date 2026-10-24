"""Read-only viewer exports of a specified document, never a source build.

Only the worker imports this module's geometry helpers. The HTTP job declares one
output in managed temporary storage; capabilities inspect geometry without writing.
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
    from cadgen.engine.export import ExportRefused

    if "digest" in expected:
        matches = fingerprint(source.structure) == expected["digest"]
    else:
        path = source.path
        stat = path.stat() if path else None
        matches = (stat is not None and f"{stat.st_mtime_ns}-{stat.st_size}" == expected.get("version")
                   and source.structure.get("version") == expected.get("version"))
    if not matches:
        raise ExportRefused("The source changed. Open Export again to use the displayed revision.")


def options(source, *, original_allowed=True) -> list[dict]:
    from cadgen.engine.export import ExportRefused
    from cadgen.engine.export.dxf import dxf_bytes

    rows = [{"format": kind, "label": label, "extension": extension, "reason": None}
            for kind, label, extension in (("step", "STEP", ".step"), ("glb", "GLB", ".glb"),
                                           ("stl", "STL", ".stl"), ("threemf", "3MF", ".3mf"),
                                           ("dxf", "DXF", ".dxf"), ("xbf", "XBF", ".xbf"))]
    if source.mesh:
        # A mesh file's page offers the other two mesh kinds, and nothing else.
        return [row for row in rows if row["format"] in ("glb", "stl", "threemf") and row["format"] != source.mesh]
    view = source.view()
    for row in rows:
        if row["format"] == "dxf":
            try:
                dxf_bytes(view)
            except ExportRefused as error:
                row["reason"] = str(error)
        if row["format"] == "xbf" and source.path and source.path.suffix.lower() == ".xbf" and not source.foreign:
            row["reason"] = "Use Download original XBF."
    if original_allowed and source.path and source.path.suffix.lower() == ".xbf":
        rows.append({"format": "original", "label": "Download original XBF", "extension": ".xbf", "reason": None})
    return rows


def original(source, target: Path, expected: dict) -> int:
    from cadgen.engine.export import ExportRefused

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
