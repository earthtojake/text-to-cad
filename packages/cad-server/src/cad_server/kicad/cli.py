"""Run KiCad's DRC against the saved board and sibling project, headless, in private homes.

``kicad-cli`` runs with no display to reach and every KiCad home (settings, documents, cache, temp)
in a temporary folder of its own (``cad.kicad._program.private_run``): it opens no window and never reads,
writes or locks anything of the person's KiCad.
The JSON report is temporary; the board source is not rewritten and no report is cached.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from cad.results import CheckFinding

from cad.kicad._program import KicadRunError, private_run
from cad.kicad._program import quiet as _quiet

__all__ = ["Finding", "KicadRunError", "issues", "run_drc"]

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
                )
            )
    return list(dict.fromkeys(found))


def run_drc(cli: Path, board: Path, *, timeout: float = _TIMEOUT_SECONDS) -> list[Finding]:
    """KiCad's DRC of ``board``, every severity included. Raises :class:`KicadRunError`
    when ``kicad-cli`` cannot run or refuses the board."""
    with private_run("cad-drc-") as (scratch, env):
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
