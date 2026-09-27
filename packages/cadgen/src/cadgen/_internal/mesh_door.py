"""What ``stl.build`` / ``threemf.build`` / ``glb.build`` all are.

The three public mesh doors differ only in a format string, so their bodies
live here and the namespaces keep exactly the thin, fully-annotated signature
their CLIs are generated from. Anything richer in those modules would be a
second implementation to drift.

The engine is unchanged: :func:`cadgen.step_export_target.export_cad_target`
is the one entry, so a door and a model-script run cannot produce different
bytes (design/format-doors.md).

The doors take DOCUMENTS: the mesh is the document's tree, tessellated. A door
never moves geometry — a posed export is authored geometry or another model.
"""

from __future__ import annotations

from pathlib import Path

from cadgen.results import MeshExportFile, MeshExportResult


def mesh_build(
    fmt: str,
    target: Path,
    out: Path | None,
    *,
    mesh_tolerance: float | None,
    mesh_angular_tolerance: float | None,
    animation: str | dict | None = None,
    force: bool,
    verbose: bool,
) -> MeshExportResult:
    """One format door's ``build``, typed.

    ``out`` None writes one sibling file beside the document with this format's
    extension. An explicit ``out`` selects its destination. Neither reads model
    output declarations; the shared ledger gates the write.

    ``animation`` is GLB's alone. It is a parameter of the SHARED body rather
    than of one door because that is where a clip could otherwise be dropped
    without anyone noticing: STL is triangles and 3MF is a build plate, and
    neither has anywhere to put a clip, so both refuse it by name. Only the CLI's
    ``glb build`` grows the flag (the parser is generated from that signature),
    so the other two doors reject ``--animation`` as an unknown option; this
    refusal is what a direct Python call gets.
    """
    if animation is not None and fmt != "glb":
        raise ValueError(
            f"{fmt} carries no animation: only `cadgen glb build --animation` writes a clip "
            "into a file — the other mesh formats have nowhere to put one. Export the clip "
            "as .glb, or render it with `cadgen step snapshot --animation --video`"
        )
    if animation is not None and out is None:
        # Omitted OUT is reserved for the static sibling export. A clip changes
        # the artifact's structure and initial pose, so require a chosen path.
        raise ValueError(
            "an animated export is ad hoc: name an OUT path. Omitting OUT writes a static "
            "sibling .glb beside the document; choose a destination for the animated file"
        )
    from cadgen.cli_logging import CliLogger
    from cadgen.step_export_target import export_cad_target

    # The engine validates TARGET (once: doors.document_target) and reads the tree
    # behind the document's BYTES (a compile job when the store has none); it
    # never refuses a document or runs its script.
    payload = export_cad_target(
        target,
        [(fmt, None if out is None else Path(out).expanduser())],
        mesh_tolerance=mesh_tolerance,
        mesh_angular_tolerance=mesh_angular_tolerance,
        animation=animation,
        force=force,
        verbose=verbose,
        logger=CliLogger(f"cadgen {fmt} build", verbose=verbose),
    )
    files = tuple(
        MeshExportFile(
            path=Path(str(entry["path"])),
            fmt=str(entry["format"]),
            skipped=bool(entry.get("skipped")),
            mesh_tolerance=entry.get("meshTolerance"),  # type: ignore[arg-type]
            mesh_angular_tolerance=entry.get("meshAngularTolerance"),  # type: ignore[arg-type]
            animation=entry.get("animation"),  # type: ignore[arg-type]
        )
        for entry in payload["files"]  # type: ignore[union-attr]
    )
    return MeshExportResult(
        ok=bool(payload.get("ok", True)),
        files=files,
        warnings=tuple(str(text) for text in (payload.get("warnings") or ())),
    )
