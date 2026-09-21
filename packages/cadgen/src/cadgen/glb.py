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
    animation: str | dict | None = None,
    force: bool = False,
    verbose: bool = False,
) -> MeshExportResult:
    """Produce one GLB output for TARGET through the shared mesh engine.

    target: the STEP/STP document to export.
    out: destination .glb path. Omitted, writes one sibling .glb beside
        TARGET. Model output declarations are not read.
    mesh_tolerance: chord deflection RELATIVE to each component's bounding
        diagonal (default 1.5e-3), for this export only.
    mesh_angular_tolerance: max normal spread across a triangle edge in
        radians (default 0.35), for this export only.
    animation: carry a clip of the document's embedded animation source
        into the file as glTF animation, instead of exporting it static. A clip
        name, or a {clip, fps, seconds, start, drop, deform} object; `fps` is
        the sampling rate of the baked keyframes (default 30). Rotation and
        translation are supported; opacity, visibility and tube deformation are
        refused by name unless `drop`/`deform` says what to do with them. GLB
        only; an animated export requires an explicit output path.
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
        animation=animation,
        force=force,
        verbose=verbose,
    )


callable_namespace(__name__, "glb")
