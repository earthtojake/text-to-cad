"""The operations' shared result types: what every type's ``check`` returns, typed.

Every ``check`` (``cad.urdf.check``, ``cad.sdf.check``, ``cad.srdf.check``, ...) answers with a
``CheckResult`` -- whether it passed, the file, and its findings, each with a severity, a code and a
location -- rather than a loose dict, so the library call and the CLI carry the SAME shape:
``cad <type> check --json`` is ``dataclasses.asdict`` of the value the library returned.
``ValidationResult`` and ``ValidationIssue``, their 0.10 names, are aliases that take the 0.10 call shapes
(``ValidationIssue(severity, message, element=, code=, hint=)``, ``ValidationResult(ok, path, issues=,
summary=)``) and make these.

Stdlib only, on purpose: importing a result type must never pull in the CAD kernel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["CheckFinding", "CheckResult"]


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
    """One finding of a ``check``.

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
    """The outcome of one ``check``."""

    ok: bool
    path: Path
    findings: tuple[CheckFinding, ...] = field(default_factory=tuple)
    #: One line describing what was validated (link/joint counts and so on).
    #: Empty when the document did not parse far enough to describe.
    summary: str = ""

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
