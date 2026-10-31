"""The checkers' internal finding accumulator.

:class:`FindingsReport` is what a validator BUILDS while it walks a document:
findings split by severity, extended across checkers, deduplicated at the end.
It is not what a caller receives — :class:`cad.results.ValidationResult` is
the typed line protocol every ``validate`` verb answers with, and
:mod:`cad._internal.validation_door` converts one into the other.

Both classes were called ``ValidationResult``, which is why this one is not any
more: two classes sharing a name means every grep returns both and every import
line has to be read for its module before it can be read for its meaning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class Finding:
    severity: Severity
    code: str
    message: str
    path: str | None = None
    hint: str | None = None

    def format(self) -> str:
        location = f" at {self.path}" if self.path else ""
        hint = f" Hint: {self.hint}" if self.hint else ""
        return f"{self.severity}: {self.code}{location}: {self.message}{hint}"


@dataclass
class FindingsReport:
    errors: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)
    infos: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(
        self,
        severity: Severity,
        code: str,
        message: str,
        *,
        path: str | None = None,
        hint: str | None = None,
    ) -> Finding:
        finding = Finding(severity=severity, code=code, message=message, path=path, hint=hint)
        if severity == "error":
            self.errors.append(finding)
        elif severity == "warning":
            self.warnings.append(finding)
        else:
            self.infos.append(finding)
        return finding

    def extend(self, other: FindingsReport) -> None:
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        self.infos.extend(other.infos)

    def all_findings(self) -> list[Finding]:
        return [*self.errors, *self.warnings, *self.infos]

    def deduplicated(self) -> FindingsReport:
        deduped = FindingsReport()
        seen: set[tuple[str, str, str, str]] = set()
        for finding in self.all_findings():
            key = (str(finding.severity), finding.code, finding.message, finding.path or "")
            if key in seen:
                continue
            seen.add(key)
            deduped.add(
                finding.severity,
                finding.code,
                finding.message,
                path=finding.path,
                hint=finding.hint,
            )
        return deduped


def format_findings(findings: list[Finding]) -> str:
    return "\n".join(finding.format() for finding in findings)
