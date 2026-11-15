"""KiCad's design rule check of a saved board: ``cad.kicad_pcb.drc`` and ``cad kicad_pcb drc``.

``kicad-cli pcb drc`` (kicode's, or the one ``CAD_KICAD_CLI`` names: ``_program``) runs against the saved
board and the ``.kicad_pro`` beside it, with no display to reach and every KiCad home (settings,
documents, cache, temp) in a temporary folder of its own (``_program.private_run``): it opens no window
and never reads, writes or locks anything of the person's KiCad. The JSON report is temporary and the
board is not rewritten.

What the check adds to KiCad's own line (``kicad-cli pcb drc board.kicad_pcb``), which judges a board by the
fills it was saved with, against no schematic, and exits 0 either way:

* the zones are refilled in memory first (``--refill-zones``, never ``--save-board``), so a pour an edit left
  stale neither hides an unconnected pad nor reports a clearance the refill gives way to; the file keeps
  the fills it was saved with, which are what a Gerber plots, so an edit still refills and saves;
* the board is held to its schematic (``--schematic-parity``) when ``<board>.kicad_sch`` is beside it: a pad on
  another net than the schematic gives it (``net_conflict``), a part the schematic lacks or the board lacks
  (``extra_footprint``, ``missing_footprint``), a footprint or a value that is not the symbol's
  (``footprint_symbol_mismatch``). With no schematic there, the result says so (``no_schematic``), since
  KiCad's report reads the same as a board that matches;
* the verdict (``fails``): an error, an unconnected item and a parity finding each fail the board, whatever
  severity the project gives the last two; one the designer excluded in the project (its DRC exclusions)
  fails nothing and is listed as excluded, with its comment.

The result is a ``CheckResult`` whose ``measurements["drc"]`` is every finding as KiCad reported it (its
severity KiCad's, ``excluded`` and ``comment`` the project's exclusion), each item with its uuid and its
position in board millimetres, and what the board says that uuid is (``_located``): its kind, layers, net and
the board reference that names it. Each finding carries the same items; its severity is the check's:
``error`` for one that fails the board, ``info`` for an excluded one. A copper sliver, which KiCad reports
with no item and no position, is found again in the saved copper of its layer, and says so; where it cannot
be, the finding says that instead.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from cad.results import CheckFinding, CheckResult

from ._program import KicadMissingError, KicadRunError, private_run, project_as_found, ready
from ._program import quiet as _quiet

__all__ = ["Finding", "KicadRunError", "check", "command", "fails", "issues", "run_drc"]

_TIMEOUT_SECONDS = 600
#: The checks whose every finding fails the board, whatever severity the project gives it: copper that is not
#: joined, and a board that is not its schematic's.
_FAILING = ("unconnected", "parity")


def _schematic(board: Path) -> Path:
    """The schematic a board is held to: the one its BOM is read from (``_export.schematic_of``)."""
    from ._export import schematic_of  # here, not above: ``_export`` imports this module

    return schematic_of(board)


@dataclass(frozen=True)
class Finding:
    """One DRC finding, as KiCad reports it."""

    check: str  # "violation", "unconnected" or "parity"
    severity: str  # KiCad's: "error" or "warning" (an excluded one keeps its rule's)
    type: str  # KiCad's rule name: "clearance", "track_dangling", "unconnected_items"...
    description: str
    #: What each item names, in KiCad's words ("Track [GND] on F.Cu, length 2.0 mm").
    items: tuple[str, ...]
    #: Where the first item is, in millimetres from the board's origin.
    at: tuple[float, float] | None
    #: Each item as KiCad named it: ``{"uuid", "description", "pos": [x, y]}`` (mm), for a page to find it by,
    #: with what the board says it is (``with_board``): ``kind``, ``layers``, ``net``, ``ref``, ``part``.
    located: tuple[dict, ...] = field(default=(), compare=False)
    #: The layer KiCad marked it on, as its description ends with it (``Copper sliver (F.Cu)``), by the
    #: board file's name for it; ``None`` where the description names none.
    layer: str | None = field(default=None, compare=False)
    #: Where ``at`` came from: ``"kicad"`` (its report's first item), ``"board"`` (found in the saved board: a
    #: copper sliver), or ``None`` (no position); ``note`` says why for any but KiCad's.
    at_source: str | None = field(default=None, compare=False)
    note: str | None = field(default=None, compare=False)
    #: Whether the designer excluded it in the project (its DRC exclusions), and the comment the exclusion
    #: carries: listed, counted as neither an error nor a warning, and it fails nothing.
    excluded: bool = False
    comment: str | None = None

    def as_data(self) -> dict:
        return {"check": self.check, "severity": self.severity, "type": self.type, "description": self.description,
                "items": [dict(item) for item in self.located], "at": list(self.at) if self.at else None,
                "layer": self.layer, "at_source": self.at_source if self.at else None, "note": self.note,
                "excluded": self.excluded, "comment": self.comment}


def fails(finding: Finding) -> bool:
    """Whether ``finding`` fails its board: an error-severity violation, an unconnected item or a difference
    from the schematic (the last two whatever severity the project gives them), unless the project excludes
    it. The one rule ``check`` fails a board by and an export of fabrication files warns by (``_export``)."""
    return not finding.excluded and (finding.severity == "error" or finding.check in _FAILING)


def _severity(finding: Finding) -> str:
    """The check's severity of a finding: ``error`` for one that fails the board (``fails``), ``info`` for one
    the project excludes, else KiCad's."""
    return "info" if finding.excluded else "error" if fails(finding) else finding.severity


def issues(findings) -> tuple[CheckFinding, ...]:
    """Every finding as the line protocol's issue, the ones that fail the board first (each an ``error``), the
    excluded ones last (each an ``info`` that says so, with its comment), then by check and rule:
    the one text a finding is printed as, by the build and by ``cad kicad_pcb drc``."""
    rank = {"error": 0, "info": 2}
    order = sorted(findings, key=lambda finding: (rank.get(_severity(finding), 1), finding.check, finding.type))
    return tuple(
        CheckFinding(
            severity=_severity(finding),
            code=finding.type,
            message=finding.description + (": " + "; ".join(finding.items) if finding.items else "")
            + (f" ({finding.note})" if finding.note else "")
            + (f" (excluded in the project{f': {finding.comment}' if finding.comment else ''})" if finding.excluded else ""),
            location=f"({finding.at[0]:g}, {finding.at[1]:g}) mm" if finding.at else None,
            items=[dict(item) for item in finding.located],
        )
        for finding in order
    )


def with_board(findings: list[Finding], board: Path) -> list[Finding]:
    """``findings`` with what the saved ``board`` says of them (``_located``): each item's kind, layers, net,
    reference and part by its uuid, each finding's layer from its description, and each copper sliver's place
    found in that layer's copper -- paired with KiCad's slivers of the layer in reading order when the board
    shows as many, else listed as ``candidates`` with a note. A board that cannot be read leaves them as KiCad
    said them."""
    from dataclasses import replace

    from ._located import LAYER_SUFFIX, PAD_WORDS, board_items, slivers

    try:
        known, names = board_items(board)
    except (OSError, ValueError, UnicodeDecodeError):
        return findings
    blank = {"kind": None, "layers": [], "net": None, "ref": None, "part": None}
    out: list[Finding] = []
    for finding in findings:
        suffix = LAYER_SUFFIX.search(finding.description)
        layer = names.get(suffix.group(1)) if suffix else None
        def what(item: dict) -> dict:
            found = known.get(str(item.get("uuid") or "").lower())
            words = PAD_WORDS.search(str(item.get("description") or "")) if found is None else None
            return (found or (known.get(f"pad:{words.group(2)}.{words.group(1)}") if words else None)) or blank

        located = tuple({**item, **what(item)} for item in finding.located)
        out.append(replace(finding, located=located, layer=layer, at_source="kicad" if finding.at else None))
    by_layer: dict[str | None, list[int]] = {}
    for number, finding in enumerate(out):
        if finding.type == "copper_sliver" and finding.at is None:
            by_layer.setdefault(finding.layer, []).append(number)
    for layer, numbers in by_layer.items():
        unsaid = "KiCad's report gives a copper sliver no position"
        if layer is None:
            for number in numbers:
                out[number] = replace(out[number], note=f"{unsaid}, and names no layer for this one")
            continue
        try:
            found = slivers(board, layer)
        except (OSError, ValueError, UnicodeDecodeError) as error:
            found, failed = [], f": the board could not be read ({error})"
        else:
            failed = ""
        if found and len(found) == len(numbers):
            for number, point in zip(numbers, found):
                out[number] = replace(out[number], at=point, at_source="board", note=(
                    f"{unsaid}; found at a corner sharper than 20 degrees in {layer}'s saved copper"
                    + (f", paired with KiCad's {len(numbers)} on {layer} top to bottom" if len(numbers) > 1 else "")))
            continue
        said = (f"{unsaid}; {layer}'s saved copper has {len(found)} corner(s) sharper than 20 degrees for "
                f"KiCad's {len(numbers)}: {', '.join(f'({x:g}, {y:g})' for x, y in found)} mm") if found else (
                f"{unsaid}, and none was found in {layer}'s saved copper"
                f"{failed or ' (the check refills the zones: refill them, save, and check again)'}")
        for number in numbers:
            out[number] = replace(out[number], note=said)
    return out


def _findings(report: dict) -> list[Finding]:
    """Violations, unconnected items and parity issues, each once (a through-hole
    pad's violation fires per copper layer). One the project excludes says so: KiCad reports it at its rule's
    severity with ``"excluded": true`` and the exclusion's comment (an older kicad-cli, as severity ``exclusion``)."""
    found: list[Finding] = []
    for key, check in (("violations", "violation"), ("unconnected_items", "unconnected"), ("schematic_parity", "parity")):
        for entry in report.get(key) or []:
            items = entry.get("items") or []
            positions = [item.get("pos") for item in items if isinstance(item.get("pos"), dict)]
            excluded = entry.get("excluded") is True or entry.get("severity") == "exclusion"
            found.append(
                Finding(
                    check=check,
                    severity=str(entry.get("severity", "error")),
                    type=str(entry.get("type", "")),
                    description=str(entry.get("description", "")),
                    items=tuple(str(item.get("description", "")) for item in items),
                    at=(float(positions[0].get("x", 0.0)), float(positions[0].get("y", 0.0))) if positions else None,
                    located=tuple(_item(item) for item in items),
                    excluded=excluded,
                    comment=(str(entry.get("comment") or "").strip() or None) if excluded else None,
                )
            )
    return list(dict.fromkeys(found))


def _item(item: dict) -> dict:
    pos = item.get("pos") if isinstance(item.get("pos"), dict) else None
    return {"uuid": str(item.get("uuid") or ""), "description": str(item.get("description", "")),
            "pos": [float(pos.get("x", 0.0)), float(pos.get("y", 0.0))] if pos else None}


def command(cli: Path, board: Path, report: Path) -> list[str]:
    """The ``kicad-cli`` command line that checks ``board`` into ``report``: every severity, the zones refilled
    in memory (never ``--save-board``: the file stays as saved), and the board held to its schematic when
    ``<board>.kicad_sch`` is beside it."""
    parity = ["--schematic-parity"] if _schematic(board).is_file() else []
    return [str(cli), "pcb", "drc", "--format", "json", "--severity-all", "--refill-zones", *parity,
            "-o", str(report), str(board)]


def run_drc(cli: Path, board: Path, *, timeout: float = _TIMEOUT_SECONDS) -> list[Finding]:
    """KiCad's DRC of ``board`` (``command``), every severity included. Raises :class:`KicadRunError`
    when ``kicad-cli`` cannot run, refuses the board, or could not read the schematic it was to hold it to."""
    with private_run("cad-drc-", cli) as (scratch, env), project_as_found(board):
        report = scratch / "drc.json"
        line = command(cli, board, report)
        try:
            completed = subprocess.run(line, env=env, capture_output=True, text=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            raise KicadRunError(f"kicad-cli pcb drc did not finish in {timeout:g} s") from None
        except OSError as error:
            raise KicadRunError(f"kicad-cli could not be started ({error})") from None
        # kicad-cli exits 5 for violations only when asked to (--exit-code-violations); the
        # report is read instead, so any other non-zero exit is a failure of the run.
        if completed.returncode not in (0, 5) or not report.is_file():
            said = _quiet(completed.stderr) or _quiet(completed.stdout) or f"exit status {completed.returncode}"
            raise KicadRunError(f"kicad-cli pcb drc failed on {board}: {said}")
        # A schematic kicad-cli could not take a netlist from is said on stderr alone, at exit 0, the report's
        # parity list empty as a matching board's is: never read as one.
        if "--schematic-parity" in line and "parity tests" in (completed.stderr or ""):
            raise KicadRunError(f"kicad-cli pcb drc could not check {board.name} against {_schematic(board).name}: "
                                f"{' '.join(_quiet(completed.stderr).split())}")
        return with_board(_findings(json.loads(report.read_text(encoding="utf-8"))), board)


def check(board: Path) -> CheckResult:
    """Check the KiCad board BOARD with KiCad's design rule check.

    Runs ``kicad-cli pcb drc`` on the saved file with every severity reported,
    its zones refilled in memory first (the file is not rewritten), and lists
    each violation, unconnected item and difference from the schematic with
    where it is (millimetres from the board's origin). The board fails when any
    error-severity violation, any unconnected item or any difference from its
    schematic exists; warnings are reported and do not fail it, and neither
    does a finding the project excludes, which is listed as excluded.

    board: the .kicad_pcb to check (its .kicad_pro beside it carries the rules,
        its .kicad_sch beside it the parts and nets the board is held to).
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
    if not _schematic(target).is_file():
        # KiCad's report of a board with no schematic to read is a matching board's: an empty parity list.
        found += (CheckFinding(severity="info", code="no_schematic",
                               message=f"no {_schematic(target).name} beside the board: not checked against a "
                                       f"schematic (its parts, footprints, values and nets)"),)
    failing = any(fails(finding) for finding in findings)
    # What the result lists as a warning, the check's own included (``no_project``); an excluded one is neither.
    warnings = sum(1 for finding in found if finding.severity == "warning")
    excluded = sum(1 for finding in findings if finding.excluded)
    counted = f"{warnings} warning(s)" + (f", {excluded} excluded" if excluded else "")
    return CheckResult(
        ok=not failing,
        path=target,
        findings=found,
        summary="" if failing else f"OK {display_path(target)}: DRC clean ({counted})",
        measurements={"drc": [finding.as_data() for finding in findings]},
    )
