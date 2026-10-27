"""Operations on saved KiCad boards. The .kicad_pcb is the source of truth."""
from pathlib import Path
from cadgen.results import ValidationResult
from cadgen.kicad.cli import issues
from cadgen.engine.formats.kicad.board_index import read_board

__all__ = ["read_board", "drc", "snapshot"]

def drc(board: Path) -> ValidationResult:
    """Check the KiCad board BOARD with KiCad's design rule check.

    Runs ``kicad-cli pcb drc`` on the saved file with every severity reported
    and lists each violation and unconnected item with where it is (millimetres
    from the board's origin). The board fails when any error-severity violation
    or any unconnected item exists; warnings are reported and do not fail it.

    board: the .kicad_pcb to check (its .kicad_pro beside it carries the rules).
    """
    from cadgen._internal.validation_door import display_path, failed, resolved_target
    from cadgen.kicad.cli import run_drc
    from cadgen.kicad.install import KicadMissingError, check_version, find_kicad_cli, kicad_version

    target = resolved_target(board, label="pcb")
    if target.suffix.lower() != ".kicad_pcb":
        return failed(target, "target must be a KiCad board (.kicad_pcb)")
    if not target.is_file():
        return failed(target, "file not found")
    try:
        cli = find_kicad_cli()
        check_version(cli, kicad_version(cli))
    except KicadMissingError as error:
        return failed(target, str(error), code="kicad_missing")
    findings = run_drc(cli, target)
    errors = sum(1 for finding in findings if finding.severity == "error")
    unconnected = sum(1 for finding in findings if finding.check == "unconnected")
    warnings = sum(1 for finding in findings if finding.severity == "warning")
    return ValidationResult(
        ok=not (errors or unconnected),
        path=target,
        issues=issues(findings),
        summary="" if errors or unconnected else f"OK {display_path(target)}: DRC clean ({warnings} warning(s))",
    )


def snapshot(source=None, out=None, **options):
    """Render an existing board or board Quick Edit packet, without running authoring code."""
    if source is not None and Path(source).suffix.lower() != ".kicad_pcb":
        raise ValueError("pcb snapshot requires a .kicad_pcb file")
    from cadgen.engine.api import snapshot as draw
    return draw(source, out, **options)
