"""KiCad's electrical rules check of a saved schematic and its outputs, by KiCad's own command line,
headless, in private homes: ``cad.kicad_sch.check`` and ``export``, and the commands ``cad kicad_sch check``
and ``cad kicad_sch export``, which run them here or in the environment of ``cad[kicad]``.

Reading a schematic is the document type's (:func:`cad.kicad_sch.read_schematic`, the standard library
alone); drawing one is ``cad kicad_sch snapshot``'s. ``kicad-cli`` is kicode's, or the one
``CAD_KICAD_CLI`` names (``_program``), found and run as the board's DRC and exports are: every run gets
homes of its own, opens no window, and leaves the project's folder as it found it. The schematic is
read, never rewritten.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from cad.results import CheckFinding, CheckResult

from ._program import KicadMissingError, KicadRunError, private_run, ready
from ._program import quiet as _quiet

__all__ = ["EXPORTS", "ErcFinding", "check", "commands", "export", "run_erc"]

#: What a schematic is exported as, in the order they are listed to a person.
EXPORTS = ("pdf", "svg", "netlist", "bom")
_TIMEOUT_SECONDS = 600
# The fields a BOM lists, and its columns' names: one line per value, footprint and part number.
_BOM_FIELDS = "Reference,Value,Footprint,MPN,${QUANTITY},${DNP}"
_BOM_LABELS = "Refs,Value,Footprint,MPN,Qty,DNP"
_BOM_GROUPS = "Value,Footprint,MPN"
# The project files kicad-cli makes beside a schematic it only reads, when they are missing.
_PROJECT_FILES = (".kicad_prl", ".kicad_pro")


@dataclass(frozen=True)
class ErcFinding:
    """One ERC finding, as KiCad reports it: its severity, its rule, its words, the sheet it is on,
    what it names and where (mm on that sheet's page)."""

    severity: str  # "error", "warning", "exclusion"
    type: str  # KiCad's rule: "pin_not_connected", "power_pin_not_driven", "label_dangling"...
    description: str
    sheet: str  # the sheet's path: "/", "/Power/"
    items: tuple[str, ...]
    at: tuple[float, float] | None


def _findings(report: dict) -> list[ErcFinding]:
    found: list[ErcFinding] = []
    for sheet in report.get("sheets") or []:
        for entry in sheet.get("violations") or []:
            items = entry.get("items") or []
            positions = [item.get("pos") for item in items if isinstance(item.get("pos"), dict)]
            found.append(ErcFinding(
                severity=str(entry.get("severity", "error")), type=str(entry.get("type", "")),
                description=str(entry.get("description", "")), sheet=str(sheet.get("path", "/")),
                items=tuple(str(item.get("description", "")) for item in items),
                at=(float(positions[0].get("x", 0.0)), float(positions[0].get("y", 0.0))) if positions else None))
    return list(dict.fromkeys(found))


def _project_of(schematic: Path) -> Path:
    """The schematic kicad-cli is run on: the project's root sheet, so a check or an export reads the
    whole hierarchy (a child sheet alone has no parent to name its hierarchical labels)."""
    from cad.engine.formats.kicad.schematic import root_of

    return root_of(schematic)


class _AsFound:
    """The project files a kicad-cli read makes beside the root sheet, removed after it when it made them."""

    def __init__(self, schematic: Path):
        self.made = [schematic.with_suffix(suffix) for suffix in _PROJECT_FILES if not schematic.with_suffix(suffix).exists()]

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        for path in self.made:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def run_erc(cli: Path, schematic: Path, *, timeout: float = _TIMEOUT_SECONDS) -> list[ErcFinding]:
    """KiCad's ERC of ``schematic``'s hierarchy, every severity included. Raises
    :class:`~cad.kicad._program.KicadRunError` when ``kicad-cli`` cannot run or refuses the schematic."""
    root = _project_of(schematic)
    with private_run("cad-erc-", cli) as (scratch, env), _AsFound(root):
        report = scratch / "erc.json"
        command = [str(cli), "sch", "erc", "--format", "json", "--units", "mm", "--severity-all", "-o", str(report),
                   str(root)]
        try:
            completed = subprocess.run(command, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                       timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            raise KicadRunError(f"kicad-cli sch erc did not finish in {timeout:g} s") from None
        except OSError as error:
            raise KicadRunError(f"kicad-cli could not be started ({error})") from None
        # kicad-cli exits 5 for violations only when asked to (--exit-code-violations): the report is read.
        if completed.returncode not in (0, 5) or not report.is_file():
            said = _quiet(completed.stderr) or _quiet(completed.stdout) or f"exit status {completed.returncode}"
            raise KicadRunError(f"kicad-cli sch erc failed on {root}: {said}")
        return _findings(json.loads(report.read_text(encoding="utf-8")))


# What KiCad says of a library it cannot see: kicad-cli runs in homes of its own, so the person's global
# symbol and footprint library tables are not there (a project's own sym-lib-table and fp-lib-table are).
_UNSEEN_LIBRARY = "does not include the"


def _unseen(finding: ErcFinding) -> bool:
    return finding.type in ("lib_symbol_issues", "footprint_link_issues") and _UNSEEN_LIBRARY in finding.description


def issues(findings) -> tuple[CheckFinding, ...]:
    """Every finding as the line protocol's issue, errors first, then by sheet and rule; the library
    checks KiCad could not make (a global library it cannot see from its private homes) as one note."""
    shown = [finding for finding in findings if finding.severity != "exclusion" and not _unseen(finding)]
    order = sorted(shown, key=lambda finding: (finding.severity != "error", finding.sheet, finding.type))
    found = tuple(
        CheckFinding(
            severity=finding.severity, code=finding.type,
            message=finding.description + (": " + "; ".join(finding.items) if finding.items else ""),
            location=f"{finding.sheet} ({finding.at[0]:g}, {finding.at[1]:g}) mm" if finding.at else finding.sheet)
        for finding in order)
    unseen = sum(1 for finding in findings if _unseen(finding))
    if unseen:
        found += (CheckFinding(
            severity="info", code="libraries_not_checked",
            message=f"{unseen} symbol or footprint library check(s) not made: KiCad runs here without your global "
                    f"library tables (a project's own sym-lib-table and fp-lib-table are read)"),)
    return found


def check(schematic: Path) -> CheckResult:
    """Check the KiCad schematic SCHEMATIC with KiCad's electrical rules check.

    Runs ``kicad-cli sch erc`` on the saved hierarchy (from its project's root sheet) with every
    severity reported, and lists each violation with its sheet and where it is (millimetres on that
    sheet's page). The schematic fails when any error-severity violation exists; warnings are reported
    and do not fail it.

    schematic: the .kicad_sch to check (any sheet of its project: the check reads the whole hierarchy).
    """
    from cad._internal.validation_door import display_path, failed, resolved_target

    target = resolved_target(schematic, label="kicad_sch")
    if target.suffix.lower() != ".kicad_sch":
        return failed(target, "target must be a KiCad schematic (.kicad_sch)")
    if not target.is_file():
        return failed(target, "file not found")
    try:
        cli = ready()
    except KicadMissingError as error:
        return failed(target, str(error), code="kicad_missing")
    try:
        findings = run_erc(cli, target)
    except KicadRunError as error:  # KiCad refused the schematic (a newer format, a broken file): its own words
        return failed(target, str(error), code="kicad_failed")
    errors = sum(1 for finding in findings if finding.severity == "error")
    warnings = sum(1 for finding in findings if finding.severity == "warning")
    return CheckResult(ok=not errors, path=target, findings=issues(findings),
                       summary="" if errors else f"OK {display_path(target)}: ERC clean ({warnings} warning(s))")


def commands(cli: Path, schematic: Path, to: str, out_dir: Path) -> list[list[str]]:
    """The ``kicad-cli`` command line that exports ``schematic`` (its project's root) as ``to`` into ``out_dir``.

    - ``pdf``: every sheet, one page each, ``out_dir/<root>.pdf``.
    - ``svg``: one SVG per sheet, into ``out_dir``.
    - ``netlist``: KiCad's own netlist (the s-expression one a board imports), ``out_dir/<root>.net``.
    - ``bom``: the bill of materials as CSV, a line per value, footprint and part number (``MPN``),
      ``out_dir/<root>-bom.csv``.
    """
    if to not in EXPORTS:
        raise ValueError(f"cannot export {to!r}: choose one of {', '.join(EXPORTS)}")
    head = [str(cli), "sch", "export", to]
    stem = schematic.stem
    if to == "pdf":
        return [[*head, "-o", str(out_dir / f"{stem}.pdf"), str(schematic)]]
    if to == "svg":
        return [[*head, "-o", os.path.join(out_dir, ""), str(schematic)]]
    if to == "netlist":
        return [[*head, "--format", "kicadsexpr", "-o", str(out_dir / f"{stem}.net"), str(schematic)]]
    return [[*head, "--fields", _BOM_FIELDS, "--labels", _BOM_LABELS, "--group-by", _BOM_GROUPS,
             "-o", str(out_dir / f"{stem}-bom.csv"), str(schematic)]]


def _listing(out_dir: Path) -> dict[Path, tuple[int, int]]:
    stamps = {}
    for path in out_dir.rglob("*"):
        if path.is_file():
            info = path.stat()
            stamps[path] = (info.st_mtime_ns, info.st_size)
    return stamps


def export(schematic: Path, to: str, out_dir: Path, *, cli: Path | None = None,
           timeout: float = _TIMEOUT_SECONDS) -> list[Path]:
    """Export the saved ``schematic``'s hierarchy as ``to`` (one of :data:`EXPORTS`) into ``out_dir``,
    made if missing, and return the files the run wrote or changed there, sorted. Raises
    :class:`~cad.kicad._program.KicadRunError` when ``kicad-cli`` cannot run or refuses the schematic,
    and :class:`~cad.kicad._program.KicadMissingError` when there is none."""
    if to not in EXPORTS:
        raise ValueError(f"cannot export {to!r}: choose one of {', '.join(EXPORTS)}")
    schematic = Path(schematic).resolve()
    if schematic.suffix.lower() != ".kicad_sch" or not schematic.is_file():
        raise KicadRunError(f"{schematic} is not a saved KiCad schematic (.kicad_sch)")
    root = _project_of(schematic)
    out_dir = Path(out_dir).resolve()
    if cli is None:
        cli = ready()
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise KicadRunError(f"cannot write the {to} into {out_dir}: {error.strerror or error}") from None
    before = _listing(out_dir)
    with private_run("cad-sch-export-", cli) as (_scratch, env), _AsFound(root):
        for command in commands(cli, root, to, out_dir):
            try:
                completed = subprocess.run(command, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                           timeout=timeout, check=False)
            except subprocess.TimeoutExpired:
                raise KicadRunError(f"kicad-cli sch export {to} did not finish in {timeout:g} s") from None
            except OSError as error:
                raise KicadRunError(f"kicad-cli could not be started ({error})") from None
            if completed.returncode != 0:
                said = _quiet(completed.stderr) or _quiet(completed.stdout) or f"exit status {completed.returncode}"
                raise KicadRunError(f"kicad-cli sch export {to} failed on {root}: {said}")
    written = sorted(path for path, stamp in _listing(out_dir).items() if before.get(path) != stamp)
    if not written:
        raise KicadRunError(f"kicad-cli sch export {to} wrote no file for {root}")
    return written
