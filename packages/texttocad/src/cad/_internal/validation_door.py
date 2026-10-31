"""What the ``urdf``/``srdf``/``sdf`` ``validate`` verbs share.

The checkers all answer with :class:`cad.findings.FindingsReport` — an
accumulator of Findings split by severity — and the public verbs all answer with
:class:`cad.results.ValidationResult`, the typed line protocol every door
returns. That conversion, and the one rule that decides ``ok``, live here so the
three verbs cannot come to disagree about what "valid" means.

The two used to share the name ``ValidationResult``, which made every grep for
either one return both and every ``from ... import ValidationResult`` a question
about which module was meant. The internal accumulator is the one that got
renamed: the public name is the line protocol callers import.
"""

from __future__ import annotations

from pathlib import Path

from cad.results import ValidationIssue, ValidationResult

# Stdlib only, like cad.results: a robot validator must not wake the CAD
# kernel, and these namespaces are imported to reach one small function.


def issues_from_findings(findings) -> tuple[ValidationIssue, ...]:
    """Every finding, errors first, as the public issue type."""
    return tuple(
        ValidationIssue(
            severity=str(finding.severity),
            message=finding.message,
            element=finding.path,
            code=finding.code,
            hint=finding.hint,
        )
        for finding in findings.all_findings()
    )


def blocks(findings, *, strict: bool) -> bool:
    """The one rule that decides valid/invalid.

    ``strict`` is the only knob: warnings block under it and are advisory
    without it. Errors always block.
    """
    return bool(findings.errors or (strict and findings.warnings))


def result_from_findings(
    path: Path, findings, *, strict: bool, summary: str = ""
) -> ValidationResult:
    """One checker's findings as the verb's answer."""
    blocking = blocks(findings, strict=strict)
    return ValidationResult(
        ok=not blocking,
        path=path,
        issues=issues_from_findings(findings),
        summary=summary if not blocking else "",
    )


def failed(path: Path, message: str, *, code: str = "invalid_target") -> ValidationResult:
    """A precheck failure — wrong suffix, missing file, unreadable — as a result.

    These never reach a checker, so they have no findings to convert; the shape
    a caller sees has to be the same either way.
    """
    return ValidationResult(
        ok=False,
        path=path,
        issues=(ValidationIssue(severity="error", message=message, code=code),),
    )


def display_path(path: Path) -> str:
    """Cwd-relative where that is meaningful, else absolute. Messages only."""
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except (OSError, ValueError):
        return path.resolve().as_posix()


def resolved_target(target: Path, *, label: str) -> Path:
    """The absolute path of a validation target, or raise for a non-path."""
    value = str(target or "").strip()
    if not value:
        raise ValueError(f"{label} target must be a non-empty path")
    path = Path(value).expanduser()
    path = path.resolve() if path.is_absolute() else (Path.cwd() / path).resolve()
    return path
