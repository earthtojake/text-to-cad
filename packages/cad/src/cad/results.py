"""The operations' shared result types: what every check returns, typed.

Every check -- ``dfm``, ``drc``, ``erc`` and ``validate`` (``cad.urdf.validate``, ``cad.stl.dfm``, ``cad.kicad_pcb.drc``, ...) --
answers with a ``CheckResult`` (a CAM job's, ``CamResult``, one with what a job can name and the files its plan
wrote) -- whether it passed, the file, its findings, each with a severity, a code
and a location, and what it measured, where it measures -- rather than a loose dict, so the library call
and the CLI carry the SAME shape: ``cad <type> dfm --json`` is ``dataclasses.asdict`` of the value the library returned.
``ValidationResult`` and ``ValidationIssue``, their 0.10 names, are aliases that take the 0.10 call shapes
(``ValidationIssue(severity, message, element=, code=, hint=)``, ``ValidationResult(ok, path, issues=,
summary=)``) and make these.

Stdlib only, on purpose: importing a result type must never pull in the CAD kernel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["CamResult", "CheckFinding", "CheckResult", "ExportResult"]


def _display(path: Path | None) -> str:
    """Cwd-relative where that is meaningful, else as given. Messages only."""
    if path is None:
        return "-"
    try:
        return str(Path(path).resolve().relative_to(Path.cwd().resolve()))
    except (OSError, ValueError):
        return str(path)


@dataclass(frozen=True)
class CheckFinding:
    """One finding of a check (``dfm``, ``drc``, ``erc``, ``validate``).

    ``code`` and ``hint`` carry what the checkers already produce: the skills
    teach fixing findings BY CODE, so dropping the code at the result boundary
    would make the typed result less useful than the dict it replaced.
    """

    severity: str  # "error" | "warning" | "info"
    #: The checker's stable identifier for this class of finding.
    code: str | None
    message: str
    #: Where in the file: the offending element or reference, when the checker knows it.
    location: str | None = None
    #: How to fix it, when the checker has something specific to say.
    hint: str | None = None

    @property
    def element(self) -> str | None:
        """Its location, by the name it had before checks shared one shape."""
        return self.location

    def human_line(self) -> str:
        code = f"{self.code}" if self.code else ""
        element = f" at {self.location}" if self.location else ""
        hint = f" Hint: {self.hint}" if self.hint else ""
        return f"{self.severity}: {code}{element}: {self.message}{hint}"


@dataclass(frozen=True)
class CheckResult:
    """The outcome of one check (``dfm``, ``drc``, ``erc``, ``validate``)."""

    ok: bool
    path: Path
    findings: tuple[CheckFinding, ...] = field(default_factory=tuple)
    #: One line describing what was validated (link/joint counts and so on).
    #: Empty when the document did not parse far enough to describe.
    summary: str = ""
    #: What the check measured, by family, as plain data (a manufacturing check's draft, undercuts,
    #: walls, ...); empty for a check that measures nothing.
    measurements: dict[str, Any] = field(default_factory=dict)

    @property
    def issues(self) -> tuple[CheckFinding, ...]:
        """Its findings, by the name they had before checks shared one shape."""
        return self.findings

    def human_lines(self) -> list[str]:
        lines = [finding.human_line() for finding in self.findings]
        if self.ok:
            lines.append(self.summary or f"OK {_display(self.path)}")
        else:
            blocking = sum(1 for finding in self.findings if finding.severity == "error")
            lines.append(f"FAILED {_display(self.path)}: {blocking or len(self.findings)} blocking finding(s)")
        return lines


def _assumed_value(value: object) -> str:
    """An assumed value as a line says it: ``fanuc``, ``8000``, ``false``, ``[300, 200, 80]``."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_assumed_value(v) for v in value) + "]"
    return str(value)


@dataclass(frozen=True)
class CamResult(CheckResult):
    """The outcome of a CAM job (``cad.<type>.plan``, ``cad <type> plan``; ``result.json`` in the folder a plan writes
    holds it): a check, so ``ok``, the document (``path``), its findings and ``measurements`` are every check's, and
    ``--json`` is this whole result.

    With no job it is what a job can name on the part, which writes nothing, each with the ref a job names it by:
    ``faces`` one dict per face (``ref``, ``surface``, ``reading``, ``area_mm2``, ``center_mm``, and for a flat face
    its ``normal`` and ``z_mm``; for a cylinder its ``axis``, ``diameter_mm`` and whether it is a hole), ``holes`` the
    faces that make one hole (``faces``: its walls first, then a counterbore's wall and shoulder, a drawn point's cone
    and a blind floor, any of which names the hole; ``diameter_mm``, ``depth_mm``, ``axis``, ``center_mm``, ``through``,
    ``reach``: the directions that reach it, and when it has them ``counterbore`` and ``point_mm``, a drawn drill
    point's length), ``floors`` the flat faces facing an axis (``ref``, ``z_mm``, ``normal``, ``kind``: top, floor or
    bottom), and ``measurements["bbox_mm"]`` the part's box (``min``, ``max``, ``size``, part coordinates).

    With a job it is the plan: ``written`` the files it wrote into its folder (``result.json``, ``result.glb``, then
    each G-code file), and ``measurements`` the numbers: the ``verdict`` (``status`` ready or fix, ``headline`` "Ready to
    cut · 42 min · 3 tools", ``errors``, ``warnings``, and where no G-code was written, ``gcode`` saying so), the totals
    (``duration_s``, ``tools``, ``tool_changes`` with its ``count`` and ``order``, ``post``, ``machine``,
    ``material``, ``planner``), ``stock_mm`` the stock's box (``min``, ``max``, part coordinates), ``setups`` one row
    per setup (``id``, ``orientation``, ``origin``, ``origin_part_mm`` its work zero, ``matrix`` part to work
    coordinates, ``time_s``, ``t0``, ``t1``), ``operations`` one row per operation in program order (``setup``,
    ``index``, ``op``, ``plain``, ``tool``, ``tool_plain``, ``rpm``, ``feed_mm_min``, ``time_s``, ``t0``, ``t1``,
    ``summary``), ``posts`` one ``{setup, file, post, tool}`` per posted file (``tool`` its id where the post splits a
    setup by tool, else None), ``assumed`` every value the plan took that the job does not state (``key``, ``value``,
    ``why``), the ``safety`` sentence each program starts with, and ``timings``. ``ok`` is the validators' rule: false
    when any finding is an error -- a check refused the plan, whose ``result.json`` and ``result.glb`` are written all
    the same since they show what is wrong and where, and no G-code is -- or the job could not run, which wrote nothing.
    """

    #: The part read, by its occurrence's path.
    occurrence: str = ""
    #: The files the plan wrote into its folder: ``result.json``, ``result.glb``, then each posted file; none with no
    #: job, or a job that stopped.
    written: tuple[Path, ...] = field(default_factory=tuple)
    faces: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    holes: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    floors: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def _written(self, name: str) -> Path | None:
        return next((Path(path) for path in self.written if Path(path).name == name), None)

    @property
    def folder(self) -> Path | None:
        """The folder the plan wrote its results into, or None (no job, or a job that stopped)."""
        found = self._written("result.json")
        return None if found is None else found.parent

    @property
    def glb(self) -> Path | None:
        """``result.glb``: the part, the stock and the toolpaths, which any viewer opens."""
        return self._written("result.glb")

    @property
    def gcode(self) -> tuple[Path, ...]:
        """The G-code the plan posted, one file a setup (or a setup's tool); none when a finding is an error."""
        return tuple(Path(path) for path in self.written if Path(path).name not in ("result.json", "result.glb"))

    def as_data(self) -> dict[str, Any]:
        """The result as plain data, as ``--json`` prints it and ``result.json`` holds it: paths as text, tuples as
        lists. :meth:`from_data` reads it back."""
        import dataclasses

        def plain(value: Any) -> Any:
            if isinstance(value, Path):
                return str(value)
            if isinstance(value, dict):
                return {str(key): plain(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [plain(item) for item in value]
            return value

        return plain(dataclasses.asdict(self))

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "CamResult":
        """The result again from its data (``dataclasses.asdict`` of one, as ``--json`` and the runner of one operation
        carry it)."""
        return cls(ok=bool(data["ok"]), path=Path(data["path"]),
                   findings=tuple(CheckFinding(**finding) for finding in data.get("findings") or ()),
                   summary=str(data.get("summary") or ""), measurements=dict(data.get("measurements") or {}),
                   occurrence=str(data.get("occurrence") or ""),
                   written=tuple(Path(path) for path in data.get("written") or ()),
                   faces=tuple(data.get("faces") or ()), holes=tuple(data.get("holes") or ()),
                   floors=tuple(data.get("floors") or ()))

    def human_lines(self) -> list[str]:
        planned = self.folder is not None
        lines = self._plan_lines() if planned else self._part_lines()
        lines += [finding.human_line() for finding in self.findings]
        if not self.ok:
            blocking = sum(1 for finding in self.findings if finding.severity == "error")
            lines.append(f"FAILED {_display(self.path)}: {blocking or len(self.findings)} blocking finding(s)")
        if planned:
            lines.append("safety: the G-code is not proven on a machine; air-cut or single-block it first, "
                         "and check the work offset and every tool length")
        return lines

    def _part_lines(self) -> list[str]:
        size = (self.measurements.get("bbox_mm") or {}).get("size")
        if not size:
            return [f"not planned: {_display(self.path)}"]
        lines = [f"{self.occurrence or 'part'} of {_display(self.path)}: " + " x ".join(f"{value:g}" for value in size) + " mm"]
        lines += [f"{face['ref']}  {face['reading']}" for face in self.faces]
        lines += [f"hole {', '.join(hole['faces'])}: {hole['reading']}" for hole in self.holes]
        return lines

    def _plan_lines(self) -> list[str]:
        numbers = self.measurements
        verdict = numbers.get("verdict") or {}
        lines = [str(verdict.get("headline", ""))]
        for op in numbers.get("operations") or ():
            line = f"{op['setup']} {op['index'] + 1}. {op['summary']}"
            if op.get("rpm"):
                line += f" · {op['rpm']:g} rpm · {op['feed_mm_min']:g} mm/min"
            lines.append(line)
        changes = numbers.get("tool_changes") or {}
        if changes.get("count"):
            count = changes["count"]
            lines.append(f"{count} tool change{'s' if count != 1 else ''}: {' then '.join(changes['order'])}")
        lines.append(f"wrote {', '.join(Path(path).name for path in self.written)} into {_display(self.folder)}")
        lines += [f"posted {post['setup']}: {_display(Path(post['file']))} ({post['post']})"
                  for post in numbers.get("posts") or ()]
        lines += [f"assumed: {entry['key']} {_assumed_value(entry['value'])} ({entry['why']})"
                  for entry in numbers.get("assumed") or ()]
        if verdict.get("gcode"):
            lines.append(str(verdict["gcode"]))
        return lines


@dataclass(frozen=True)
class ExportResult:
    """The outcome of an ``export`` that writes files of its own kinds (``cad.kicad_pcb.export``): the
    source, what it was exported as, the files written, and what was said beside (a part without its 3D
    model), one line each."""

    path: Path
    to: str
    written: tuple[Path, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def human_lines(self) -> list[str]:
        return [*(f"warning: {line}" for line in self.warnings), *(f"wrote {path}" for path in self.written)]


class _ValidationIssue(CheckFinding):
    """``ValidationIssue``, 0.10's name and call shape for a finding: ``(severity, message, element=None,
    code=None, hint=None)``, its location read as ``element`` as ever."""

    def __init__(self, severity: str, message: str, element: str | None = None, code: str | None = None,
                 hint: str | None = None) -> None:
        super().__init__(severity, code, message, element, hint)


class _ValidationResult(CheckResult):
    """``ValidationResult``, 0.10's name and call shape for a result: ``(ok, path, issues=(), summary="")``, its
    findings read as ``issues`` as ever."""

    def __init__(self, ok: bool, path: Path, issues: tuple[CheckFinding, ...] = (), summary: str = "") -> None:
        super().__init__(ok, path, tuple(issues), summary)


def __getattr__(name: str):
    from cad._internal.aliases import lookup

    return lookup(__name__, name)
