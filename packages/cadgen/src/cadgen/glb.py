"""The public ``glb`` format namespace: the ``@glb`` decorator and its verbs.

The GLB door's twin of :mod:`cadgen.stl` — same contract, same shared body,
different format string. See that module for the whole story.
"""

from __future__ import annotations

from pathlib import Path

from cadgen._internal.format_namespace import callable_namespace
from cadgen._internal.snapshot_door import mesh_snapshot_verb
from cadgen.results import MeshExportResult

__all__ = ["build", "snapshot"]

#: ``cadgen glb snapshot``'s verb: render a GLB mesh.
snapshot = mesh_snapshot_verb("glb")


def build(
    target: Path,
    out: Path | None = None,
    *,
    mesh_tolerance: float | None = None,
    mesh_angular_tolerance: float | None = None,
    force: bool = False,
    verbose: bool = False,
) -> MeshExportResult:
    """Produce GLB output(s) for TARGET through the shared mesh engine.

    target: the STEP/STP document to export.
    out: destination .glb path. Omitted, the document's declared @glb variants
        are produced instead — every one of them.
    mesh_tolerance: chord deflection RELATIVE to each component's bounding
        diagonal, overriding what the document declares.
    mesh_angular_tolerance: max normal spread across a triangle edge in
        radians, overriding what the document declares.
    force: re-export even where the ledger says the output is current. Never
        rebuilds the model itself — run `python <script>` for that.
    verbose: show detailed progress and timing on stderr.
    """
    from cadgen._internal.mesh_door import mesh_build

    return mesh_build(
        "glb",
        target,
        out,
        mesh_tolerance=mesh_tolerance,
        mesh_angular_tolerance=mesh_angular_tolerance,
        force=force,
        verbose=verbose,
    )


callable_namespace(__name__, "glb")
