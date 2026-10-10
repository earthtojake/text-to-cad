"""A ``@pcb`` model's build: its board checked by KiCad, then written as a KiCad project.

The model runner (``cadgen._internal.generation_runner``) calls :func:`write_board`
with what the model returned, for a board alone and for a board with a 3D export
alike; everything a board's build decides -- what counts as an error, when a board
is a draft, which files it writes -- is here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from cadgen.metadata import DocumentWritten

__all__ = ["BoardWritten", "write_board"]


@dataclass(frozen=True)
class BoardWritten(DocumentWritten):
    """What a @pcb build wrote: the project's files, and how much is left to route."""

    unrouted: int = 0

    @property
    def facts(self) -> dict[Path, dict[str, object]]:
        # The board file's record entry carries the unrouted count a door reports.
        return {path: {"unrouted": self.unrouted} for path in self.paths if path.suffix == ".kicad_pcb"}


def write_board(
    result: object,
    *,
    output_path: Path,
    script_path: Path,
    logger,
    progress: object | None = None,
    fab_exports: Sequence[object] = (),
) -> BoardWritten:
    """Check a ``@pcb`` return with KiCad and write its project, or write nothing.

    KiCad fills the zones and runs ERC and DRC (with the schematic-to-board
    parity check) on a staged copy first. Any error fails the build before a
    byte reaches the output folder; warnings and unrouted connections are
    reported, and a board with unrouted connections is written as a draft --
    unless it declares a manufacturing export (``@pcb(gerber=, pos=)``), which a
    draft cannot have: then the build fails, naming what is left to route.
    The declared exports are written after the project, from the files just
    written.
    """
    from cadgen._internal.atomic_replace import write_bytes_atomic
    from cadgen.coordination import PHASE_CHECK_BOARD, resolve as resolve_progress
    from cadgen.coordination.kinds import PHASE_WRITE
    from cadgen.kicad.check import build_board, fixes
    from cadgen.kicad.design import Board
    from cadgen.kicad.fab import MANUFACTURING, export
    from cadgen.metadata import fab_output_path
    from cadgen.render import relative_to_cwd as display

    label = display(script_path)
    if not isinstance(result, Board):
        raise TypeError(f"{label} @pcb must return a pcb.Board, got {type(result).__name__}")
    output_path = Path(output_path)
    resolve_progress(progress).phase(PHASE_CHECK_BOARD)
    built = build_board(result, name=output_path.stem, script_root=Path(script_path).resolve().parent)
    errors = built.errors
    if errors:
        # Only the errors: warnings and the unrouted list come back once these are fixed.
        later = [
            f"{count} {noun}"
            for count, noun in ((built.unrouted, "unrouted connection(s)"), (len(built.warnings), "warning(s)"))
            if count
        ]
        listed = "\n  ".join(finding.render() for finding in errors)
        how = "".join(f"\n  {line}" for line in fixes(errors))
        raise RuntimeError(
            f"{label}: KiCad found {len(errors)} error(s), so nothing was written"
            + (f" ({' and '.join(later)} reported once they are fixed)" if later else "")
            + f":\n  {listed}"
            + (f"\nHow to fix:{how}" if how else "")
        )
    for finding in built.warnings:
        logger.info(f"{label} {finding.render()}")
    if built.unrouted:
        logger.info(f"{label} has {built.unrouted} unrouted connection(s); the board is a draft until they are routed:")
        for finding in built.findings:
            if finding.check == "unconnected":
                logger.info(f"  {finding.render()}")
    manufacturing = sorted({decl.fmt for decl in fab_exports} & MANUFACTURING)
    if manufacturing and built.unrouted:
        listed = "\n  ".join(finding.render() for finding in built.findings if finding.check == "unconnected")
        raise RuntimeError(
            f"{label}: the board has {built.unrouted} unrouted connection(s), so nothing was written: "
            f"@pcb({', '.join(fmt + '=' for fmt in manufacturing)}) write manufacturing files only for a finished "
            f"board. Route these, or leave {' and '.join(fmt + '=' for fmt in manufacturing)} off while the board is "
            f"a draft:\n  {listed}"
        )
    resolve_progress(progress).phase(PHASE_WRITE)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    written = []
    for suffix, text in ((".kicad_pro", built.pro), (".kicad_sch", built.sch), (".kicad_pcb", built.pcb), (".kicad_dru", built.dru)):
        target = output_path.with_suffix(suffix)
        write_bytes_atomic(target, text.encode("utf-8"))
        written.append(target)
    logger.debug(f"wrote KiCad project: {display(output_path)}")
    for decl in fab_exports:
        target = fab_output_path(script_path, decl, output_path.resolve())
        target.parent.mkdir(parents=True, exist_ok=True)
        write_bytes_atomic(target, export(decl.fmt, output_path))
        written.append(target)
        logger.info(f"wrote {decl.fmt.upper()}: {display(target)}")
    return BoardWritten(paths=tuple(written), unrouted=built.unrouted)
