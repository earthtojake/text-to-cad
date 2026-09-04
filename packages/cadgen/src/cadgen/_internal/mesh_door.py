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

STEP_SUFFIXES = (".step", ".stp")


def mesh_build(
    fmt: str,
    target: Path,
    out: Path | None,
    *,
    mesh_tolerance: float | None,
    mesh_angular_tolerance: float | None,
    force: bool,
    verbose: bool,
) -> MeshExportResult:
    """One format door's ``build``, typed.

    ``out`` None means the DOCUMENT's declarations — every declared variant of
    this format, read from its sidecar. An explicit ``out`` is one ad-hoc
    export at that path. Either way the shared ledger gates the write.
    """
    from cadgen._internal.doors import document_target
    from cadgen.cli_logging import CliLogger
    from cadgen.step_export_target import export_cad_target

    # The door reads the tree behind the document's BYTES (a compile job when the
    # store has none); it never refuses a document or runs its script.
    document = document_target(target, suffixes=STEP_SUFFIXES)
    payload = export_cad_target(
        document,
        [(fmt, None if out is None else Path(out).expanduser())],
        mesh_tolerance=mesh_tolerance,
        mesh_angular_tolerance=mesh_angular_tolerance,
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
        )
        for entry in payload["files"]  # type: ignore[union-attr]
    )
    return MeshExportResult(ok=bool(payload.get("ok", True)), files=files)
