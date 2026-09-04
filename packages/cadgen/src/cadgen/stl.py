"""The public ``stl`` format namespace: the ``@stl`` decorator and its verbs.

``@stl`` DECLARES a serialization of a ``@step`` model; ``stl.build(...)``
PRODUCES one. They are the same object — this module is callable (see
:mod:`cadgen._internal.format_namespace`) — so a format stays one table row:
decorator, verbs, and generated CLI together (design/format-doors.md).

``cadgen stl build`` is this module's ``build`` with a parser derived from its
signature, so the flags cannot drift from the function. The body is
:func:`cadgen._internal.mesh_door.mesh_build`, shared with the 3MF and GLB
doors, which is itself a thin wrapper over the ONE mesh engine a model-script
run uses — a door and a script run cannot produce different bytes.

Import discipline: nothing here may pull in OCP/build123d at module scope (see
:mod:`cadgen.step`).
"""

from __future__ import annotations

from pathlib import Path

from cadgen._internal.format_namespace import callable_namespace
from cadgen._internal.snapshot_door import mesh_snapshot_verb
from cadgen.results import MeshExportResult

__all__ = ["build", "snapshot"]

#: ``cadgen stl snapshot``'s verb: render an STL mesh. The mesh half of what
#: ``step snapshot`` used to carry, now behind the door that writes the format.
snapshot = mesh_snapshot_verb("stl")


def build(
    target: Path,
    out: Path | None = None,
    *,
    mesh_tolerance: float | None = None,
    mesh_angular_tolerance: float | None = None,
    force: bool = False,
    verbose: bool = False,
) -> MeshExportResult:
    """Produce STL output(s) for TARGET through the shared mesh engine.

    target: the STEP/STP document to export.
    out: destination .stl path. Omitted, the document's declared @stl variants
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
        "stl",
        target,
        out,
        mesh_tolerance=mesh_tolerance,
        mesh_angular_tolerance=mesh_angular_tolerance,
        force=force,
        verbose=verbose,
    )


callable_namespace(__name__, "stl")
