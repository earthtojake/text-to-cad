"""``cad kicad_pcb check``'s function: KiCad's design rule check of a saved board, the ``kicad``
integration's. The .kicad_pcb is the source of truth.

Reading a board is the document type's (:func:`cad.kicad_pcb.read_board`, which a script run with ``cad
run`` imports); drawing one is ``cad kicad_pcb snapshot``'s. DRC runs KiCad's own command line, a program
the server finds but never installs (:mod:`cad_server.kicad.install`), so it is a command, and the
server's.
"""

from __future__ import annotations

from pathlib import Path

from cad.results import CheckResult

__all__ = ["check"]


def check(board: Path) -> CheckResult:
    """Check the KiCad board BOARD with KiCad's design rule check.

    Runs ``kicad-cli pcb drc`` on the saved file with every severity reported
    and lists each violation and unconnected item with where it is (millimetres
    from the board's origin). The board fails when any error-severity violation
    or any unconnected item exists; warnings are reported and do not fail it.

    board: the .kicad_pcb to check (its .kicad_pro beside it carries the rules).
    """
    from cad._internal.validation_door import display_path, failed, resolved_target
    from cad_server.kicad.cli import KicadRunError, issues, run_drc
    from cad_server.kicad.install import KicadMissingError, check_version, find_kicad_cli, kicad_version

    target = resolved_target(board, label="kicad_pcb")
    if target.suffix.lower() != ".kicad_pcb":
        return failed(target, "target must be a KiCad board (.kicad_pcb)")
    if not target.is_file():
        return failed(target, "file not found")
    try:
        cli = find_kicad_cli()
        check_version(cli, kicad_version(cli))
    except KicadMissingError as error:
        return failed(target, str(error), code="kicad_missing")
    try:
        findings = run_drc(cli, target)
    except KicadRunError as error:  # KiCad refused the board (a newer format, a broken file): its own words
        return failed(target, str(error), code="kicad_failed")
    errors = sum(1 for finding in findings if finding.severity == "error")
    unconnected = sum(1 for finding in findings if finding.check == "unconnected")
    warnings = sum(1 for finding in findings if finding.severity == "warning")
    return CheckResult(
        ok=not (errors or unconnected),
        path=target,
        findings=issues(findings),
        summary="" if errors or unconnected else f"OK {display_path(target)}: DRC clean ({warnings} warning(s))",
    )
