"""A ``@harness`` model's build: its harness checked, then written as one WireViz document.

The model runner (``cadgen._internal.generation_runner``) calls :func:`write_harness`
with what the model returned; everything a harness's build decides -- its last
checks, which files it writes -- is here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from cadgen.metadata import DocumentWritten

__all__ = ["write_harness"]


def write_harness(
    result: object,
    *,
    output_path: Path,
    script_path: Path,
    logger,
    progress: object | None = None,
    fab_exports: Sequence[object] = (),
) -> DocumentWritten:
    """Check a ``@harness`` return and write its WireViz document, or write nothing.

    The checks are the harness's own (``cadgen.wireviz.design``): most ran as
    the script connected it, and the last -- something connected, every
    connector and cable used -- run here. A declared ``bom=`` is WireViz's list
    of the document's parts, made from the document's bytes before either file
    is written, so a build that cannot list them writes neither.
    """
    from cadgen._internal.atomic_replace import write_bytes_atomic
    from cadgen.coordination import resolve as resolve_progress
    from cadgen.coordination.kinds import PHASE_WRITE
    from cadgen.metadata import fab_output_path
    from cadgen.render import relative_to_cwd as display
    from cadgen.wireviz.bom import harness_bom
    from cadgen.wireviz.design import Harness, HarnessError
    from cadgen.wireviz.document import harness_document

    label = display(script_path)
    if not isinstance(result, Harness):
        raise TypeError(f"{label} @harness must return a harness.Harness, got {type(result).__name__}")
    try:
        document = harness_document(result).encode("utf-8")
    except HarnessError as error:
        raise HarnessError(f"{label}: {error}") from None
    output_path = Path(output_path)
    files: list[tuple[Path, bytes]] = [(output_path, document)]
    resolve_progress(progress).phase(PHASE_WRITE)
    for decl in fab_exports:
        # Only a BOM: the decorators refuse a harness any other export.
        files.append((fab_output_path(script_path, decl, output_path.resolve()), harness_bom(document, label=output_path.name)))
    for target, data in files:
        target.parent.mkdir(parents=True, exist_ok=True)
        write_bytes_atomic(target, data)
    logger.debug(f"wrote harness: {display(output_path)}")
    for target, _data in files[1:]:
        logger.info(f"wrote BOM: {display(target)}")
    return DocumentWritten(paths=tuple(target for target, _data in files))
