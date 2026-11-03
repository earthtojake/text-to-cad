"""KiCad's design rule check of a saved board: ``cad.kicad_pcb.check`` and ``cad kicad_pcb check``.

``kicad-cli pcb drc`` (kicode's, or the one ``CAD_KICAD_CLI`` names: ``_program``) runs against the saved
board and the ``.kicad_pro`` beside it, with no display to reach and every KiCad home (settings,
documents, cache, temp) in a temporary folder of its own (``_program.private_run``): it opens no window
and never reads, writes or locks anything of the person's KiCad. The JSON report is temporary and the
board is not rewritten. The result is a ``CheckResult`` whose ``measurements["drc"]`` is every finding as
KiCad reported it, each item with its uuid and its position in board millimetres.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from cad.results import CheckFinding, CheckResult

from ._program import KicadMissingError, KicadRunError, private_run, project_as_found, ready
from ._program import quiet as _quiet

__all__ = ["Finding", "KicadRunError", "check", "issues", "run_drc"]

_TIMEOUT_SECONDS = 600



@dataclass(frozen=True)
class Finding:
    """One DRC finding, as KiCad reports it."""

    check: str  # "violation", "unconnected" or "parity"
    severity: str  # "error", "warning", "exclusion"
    type: str  # KiCad's rule name: "clearance", "track_dangling", "unconnected_items"...
    description: str
    #: What each item names, in KiCad's words ("Track [GND] on F.Cu, length 2.0 mm").
    items: tuple[str, ...]
    #: Where the first item is, in millimetres from the board's origin.
    at: tuple[float, float] | None
    #: Each item as KiCad named it: ``{"uuid", "description", "pos": [x, y]}`` (mm), for a page to find it by.
    located: tuple[dict, ...] = field(default=(), compare=False)

    def as_data(self) -> dict:
        return {"check": self.check, "severity": self.severity, "type": self.type, "description": self.description,
                "items": [dict(item) for item in self.located], "at": list(self.at) if self.at else None}


def issues(findings) -> tuple[CheckFinding, ...]:
    """Every finding as the line protocol's issue, errors first, then by check and rule:
    the one text a finding is printed as, by the build and by ``cad kicad_pcb check``."""
    order = sorted(findings, key=lambda finding: (finding.severity != "error", finding.check, finding.type))
    return tuple(
        CheckFinding(
            severity=finding.severity,
            code=finding.type,
            message=finding.description + (": " + "; ".join(finding.items) if finding.items else ""),
            location=f"({finding.at[0]:g}, {finding.at[1]:g}) mm" if finding.at else None,
        )
        for finding in order
    )


def _findings(report: dict) -> list[Finding]:
    """Violations, unconnected items and parity issues, each once (a through-hole
    pad's violation fires per copper layer)."""
    found: list[Finding] = []
    for key, check in (("violations", "violation"), ("unconnected_items", "unconnected"), ("schematic_parity", "parity")):
        for entry in report.get(key) or []:
            items = entry.get("items") or []
            positions = [item.get("pos") for item in items if isinstance(item.get("pos"), dict)]
            found.append(
                Finding(
                    check=check,
                    severity=str(entry.get("severity", "error")),
                    type=str(entry.get("type", "")),
                    description=str(entry.get("description", "")),
                    items=tuple(str(item.get("description", "")) for item in items),
                    at=(float(positions[0].get("x", 0.0)), float(positions[0].get("y", 0.0))) if positions else None,
                    located=tuple(_item(item) for item in items),
                )
            )
    return list(dict.fromkeys(found))


def _item(item: dict) -> dict:
    pos = item.get("pos") if isinstance(item.get("pos"), dict) else None
    return {"uuid": str(item.get("uuid") or ""), "description": str(item.get("description", "")),
            "pos": [float(pos.get("x", 0.0)), float(pos.get("y", 0.0))] if pos else None}


def run_drc(cli: Path, board: Path, *, timeout: float = _TIMEOUT_SECONDS) -> list[Finding]:
    """KiCad's DRC of ``board``, every severity included. Raises :class:`KicadRunError`
    when ``kicad-cli`` cannot run or refuses the board."""
    with private_run("cad-drc-", cli) as (scratch, env), project_as_found(board):
        report = scratch / "drc.json"
        command = [str(cli), "pcb", "drc", "--format", "json", "--severity-all", "-o", str(report), str(board)]
        try:
            completed = subprocess.run(command, env=env, capture_output=True, text=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            raise KicadRunError(f"kicad-cli pcb drc did not finish in {timeout:g} s") from None
        except OSError as error:
            raise KicadRunError(f"kicad-cli could not be started ({error})") from None
        # kicad-cli exits 5 for violations only when asked to (--exit-code-violations); the
        # report is read instead, so any other non-zero exit is a failure of the run.
        if completed.returncode not in (0, 5) or not report.is_file():
            said = _quiet(completed.stderr) or _quiet(completed.stdout) or f"exit status {completed.returncode}"
            raise KicadRunError(f"kicad-cli pcb drc failed on {board}: {said}")
        return _findings(json.loads(report.read_text(encoding="utf-8")))


def check(board: Path) -> CheckResult:
    """Check the KiCad board BOARD with KiCad's design rule check.

    Runs ``kicad-cli pcb drc`` on the saved file with every severity reported
    and lists each violation and unconnected item with where it is (millimetres
    from the board's origin). The board fails when any error-severity violation
    or any unconnected item exists; warnings are reported and do not fail it.

    board: the .kicad_pcb to check (its .kicad_pro beside it carries the rules).
    """
    from cad._internal.validation_door import display_path, failed, resolved_target

    target = resolved_target(board, label="kicad_pcb")
    if target.suffix.lower() != ".kicad_pcb":
        return failed(target, "target must be a KiCad board (.kicad_pcb)")
    if not target.is_file():
        return failed(target, "file not found")
    try:
        cli = ready()
    except KicadMissingError as error:
        return failed(target, str(error), code="kicad_missing")
    try:
        findings = run_drc(cli, target)
    except KicadRunError as error:  # KiCad refused the board (a newer format, a broken file): its own words
        return failed(target, str(error), code="kicad_failed")
    found = issues(findings)
    if not target.with_suffix(".kicad_pro").is_file():
        # The rules (clearances, track widths, net classes) live in the project: without it KiCad checks
        # against its defaults, which can pass or fail a board its own project would not.
        found += (CheckFinding(severity="warning", code="no_project",
                               message=f"no {target.with_suffix('.kicad_pro').name} beside the board: checked against "
                                       f"KiCad's default rules, not the board's own"),)
    errors = sum(1 for finding in findings if finding.severity == "error")
    unconnected = sum(1 for finding in findings if finding.check == "unconnected")
    warnings = sum(1 for finding in findings if finding.severity == "warning")
    return CheckResult(
        ok=not (errors or unconnected),
        path=target,
        findings=found,
        summary="" if errors or unconnected else f"OK {display_path(target)}: DRC clean ({warnings} warning(s))",
        measurements={"drc": [finding.as_data() for finding in findings]},
    )
