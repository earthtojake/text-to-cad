"""What the robot validators and CAM return: the JSON line protocol, typed.

Every ``validate`` verb (``cadgen.urdf``, ``cadgen.sdf``, ``cadgen.srdf``) and every ``cadgen.cam`` verb
answers with one of these frozen dataclasses rather than a loose dict, so the library call and the generated
CLI carry the SAME shape -- ``--json`` is just ``dataclasses.asdict`` of the value the
library already returned.

Stdlib only, on purpose: importing a result type must never pull in the CAD kernel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["CamFeaturesResult", "CamPlanResult", "ValidationIssue", "ValidationResult"]


def _display(path: Path | None) -> str:
    """Cwd-relative where that is meaningful, else as given. Messages only."""
    if path is None:
        return "-"
    try:
        return str(Path(path).resolve().relative_to(Path.cwd().resolve()))
    except (OSError, ValueError):
        return str(path)


@dataclass(frozen=True)
class ValidationIssue:
    """One conformance finding against a robot description.

    ``code`` and ``hint`` carry what the checkers already produce: the skills
    teach fixing findings BY CODE, so dropping the code at the result boundary
    would make the typed result less useful than the dict it replaced.
    """

    severity: str  # "error" | "warning" | "info"
    message: str
    #: The offending element or reference, when the checker knows it.
    element: str | None = None
    #: The checker's stable identifier for this class of finding.
    code: str | None = None
    #: How to fix it, when the checker has something specific to say.
    hint: str | None = None

    def human_line(self) -> str:
        code = f"{self.code}" if self.code else ""
        element = f" at {self.element}" if self.element else ""
        hint = f" Hint: {self.hint}" if self.hint else ""
        return f"{self.severity}: {code}{element}: {self.message}{hint}"


@dataclass(frozen=True)
class ValidationResult:
    """The outcome of one ``validate`` verb."""

    ok: bool
    path: Path
    issues: tuple[ValidationIssue, ...] = field(default_factory=tuple)
    #: One line describing what was validated (link/joint counts and so on).
    #: Empty when the document did not parse far enough to describe.
    summary: str = ""

    def human_lines(self) -> list[str]:
        lines = [issue.human_line() for issue in self.issues]
        if self.ok:
            lines.append(self.summary or f"OK {_display(self.path)}")
        else:
            blocking = sum(1 for issue in self.issues if issue.severity == "error")
            lines.append(f"FAILED {_display(self.path)}: {blocking or len(self.issues)} blocking finding(s)")
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


def _finding_lines(findings: tuple[dict, ...]) -> list[str]:
    return [f"{finding['severity']}: {finding['summary']}" for finding in findings]


@dataclass(frozen=True)
class CamFeaturesResult:
    """What ``cadgen cam features`` read off a part: what a CAM job can name.

    ``faces`` carries one dict per face (``ref``, ``surface``, ``reading``, ``area_mm2``, ``center_mm``, and for a
    flat face its ``normal`` and ``z_mm``; for a cylinder its ``axis``, ``diameter_mm`` and whether it is a hole).
    ``holes`` groups the faces that make one hole (``faces``: its walls first, then a counterbore's wall and
    shoulder, a drawn point's cone and a blind floor, any of which names the hole; ``diameter_mm``, ``depth_mm``,
    ``axis``, ``center_mm``, ``through``, ``reach``: the directions that reach it, and when it has them
    ``counterbore`` and ``point_mm``, a drawn drill point's length). ``floors`` are the flat faces facing an axis (``ref``, ``z_mm``, ``normal``,
    ``kind``: top, floor or bottom).
    """

    ok: bool
    document: Path
    occurrence: str = ""
    #: ``{"min": [x, y, z], "max": [x, y, z], "size": [dx, dy, dz]}`` in mm, part coordinates.
    bbox_mm: dict = field(default_factory=dict)
    faces: tuple[dict, ...] = ()
    holes: tuple[dict, ...] = ()
    floors: tuple[dict, ...] = ()
    findings: tuple[dict, ...] = ()
    warnings: tuple[str, ...] = ()

    def human_lines(self) -> list[str]:
        if not self.ok:
            return [f"not read: {_display(self.document)}"] + _finding_lines(self.findings)
        size = self.bbox_mm.get("size") or []
        lines = [f"{self.occurrence or 'part'} of {_display(self.document)}: "
                 + " x ".join(f"{value:g}" for value in size) + " mm"]
        lines += [f"{face['ref']}  {face['reading']}" for face in self.faces]
        lines += [f"hole {', '.join(hole['faces'])}: {hole['reading']}" for hole in self.holes]
        lines += _finding_lines(self.findings)
        lines += [f"warning: {warning}" for warning in self.warnings]
        return lines


@dataclass(frozen=True)
class CamPlanResult:
    """The outcome of ``cadgen cam plan``: the verdict, what was written, and the numbers per operation.

    ``verdict`` is the status (``status`` ready or fix, ``headline`` "Ready to cut · 42 min · 3 tools", ``errors``,
    ``warnings``). ``operations`` has one dict per planned operation in program order (``setup``, ``index``, ``op``,
    ``plain``, ``tool``, ``tool_plain``, ``rpm``, ``feed_mm_min``, ``time_s``, ``summary``). ``posts`` has
    one ``{setup, file, post, tool}`` per posted file: one per setup, or one per tool where the post splits a setup
    by tool (``tool`` its id, else None). ``findings`` are the checks' findings, errors first, each a dict of
    ``check``, ``severity``, ``type``, ``summary``, ``description`` and ``items``. ``assumed`` lists every value
    the plan took that the job does not state (``key``, ``value``, ``why``: a tool's catalogue flute length, the rapid
    rate the cycle time is worked out at). A job that cannot run has ``ok`` false, a finding that says what to change,
    and wrote nothing.
    """

    ok: bool
    document: Path
    #: ``None`` when the plan stopped before writing (``ok`` is false; ``findings`` say why).
    glb: Path | None = None
    posts: tuple[dict, ...] = ()
    verdict: dict = field(default_factory=dict)
    #: Totals: ``duration_s``, ``tools``, ``tool_changes`` (``count``, ``order``), ``setups``, ``operations``,
    #: ``post``, ``material``, ``planner``.
    summary: dict = field(default_factory=dict)
    operations: tuple[dict, ...] = ()
    findings: tuple[dict, ...] = ()
    warnings: tuple[str, ...] = ()
    timings: dict = field(default_factory=dict)
    assumed: tuple[dict, ...] = ()

    def human_lines(self) -> list[str]:
        if not self.ok:
            return [f"not planned: {_display(self.document)}"] + _finding_lines(self.findings)
        lines = [str(self.verdict.get("headline", ""))]
        for op in self.operations:
            line = f"{op['setup']} {op['index'] + 1}. {op['summary']}"
            if op.get("rpm"):
                line += f" · {op['rpm']:g} rpm · {op['feed_mm_min']:g} mm/min"
            lines.append(line)
        changes = self.summary.get("tool_changes") or {}
        if changes.get("count"):
            count = changes["count"]
            lines.append(f"{count} tool change{'s' if count != 1 else ''}: {' then '.join(changes['order'])}")
        if self.glb is not None:
            lines.append(f"wrote GLB: {_display(self.glb)}")
        lines += [f"posted {post['setup']}: {_display(Path(post['file']))} ({post['post']})" for post in self.posts]
        lines += [f"assumed: {entry['key']} {_assumed_value(entry['value'])} ({entry['why']})" for entry in self.assumed]
        lines += _finding_lines(self.findings)
        lines += [f"warning: {warning}" for warning in self.warnings]
        lines.append("safety: the G-code is not proven on a machine; air-cut or single-block it first, "
                     "and check the work offset and every tool length")
        return lines
