"""The public ``sdf`` namespace: the verbs that operate on SDFormat documents.

No decorator, for the reason :mod:`cadgen.urdf` gives: a world or model
description is authored, not generated. ``cadgen sdf validate`` is a generated
MIRROR of :func:`validate` (README law 6).
"""

from __future__ import annotations

from pathlib import Path

from cadgen._internal.snapshot_door import robot_snapshot_verb
from cadgen.results import ValidationResult

__all__ = ["snapshot", "validate"]

SUFFIX = ".sdf"

#: ``cadgen sdf snapshot``'s verb: render the robot the browser assembles from
#: this description's link meshes.
snapshot = robot_snapshot_verb("sdf")

#: What `gz sdf --check` may be asked to do. Not a parser `choices=` list: a
#: generated parser derives types, not enumerations, so the verb validates its
#: own argument and the CLI reports the error.
GZ_CHECK_MODES = ("auto", "required", "never")


def validate(
    path: Path,
    *,
    strict: bool = False,
    gz_check: str = "auto",
    verbose: bool = False,
) -> ValidationResult:
    """Check one SDFormat world or model for conformance.

    The bundled checks are dependency-light and catch common structural errors;
    they are not a replacement for libsdformat or a target simulator. Errors
    always block; under ``strict`` warnings do too.

    path: the .sdf file to validate.
    strict: treat warnings as blocking.
    gz_check: run `gz sdf --check` as external validation — auto (when the tool
        is installed), required (fail without it), or never.
    verbose: narrate the target on stderr.
    """
    import sys

    from cadgen._internal.validation_door import (
        blocks,
        failed,
        resolved_target,
        result_from_findings,
    )

    if gz_check not in GZ_CHECK_MODES:
        raise ValueError(f"gz_check must be one of {', '.join(GZ_CHECK_MODES)}, got {gz_check!r}")
    target = resolved_target(path, label="sdf")
    if verbose:
        print(f"[sdf] validating {target}", file=sys.stderr)
    if target.suffix.lower() != SUFFIX:
        return failed(target, f"target must be a {SUFFIX} file")
    if not target.is_file():
        return failed(target, "file not found")
    try:
        xml_text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return failed(target, str(exc))

    from cadgen.sdf_external import run_gz_sdf_check
    from cadgen.sdf_source import SdfSourceError, parse_sdf_xml
    from cadgen.sdf_validation import validate_sdf_xml

    findings = validate_sdf_xml(xml_text, source_path=target, base_dir=target.parent)
    findings.extend(run_gz_sdf_check(xml_text, output_path=target, mode=gz_check))
    findings = findings.deduplicated()
    summary = ""
    if not blocks(findings, strict=strict):
        try:
            summary = _summary(target, parse_sdf_xml(xml_text, source_path=target, base_dir=target.parent))
        except SdfSourceError as exc:
            # The checks passed but the document will not load: that IS a
            # failure, and it has to be reported as one finding rather than a
            # clean result with an empty summary.
            findings.add("error", "unparsable_sdf", str(exc), path=str(target))
    return result_from_findings(target, findings, strict=strict, summary=summary)


def _summary(path: Path, source) -> str:
    from cadgen._internal.validation_door import display_path

    scope = []
    if source.world_names:
        scope.append(f"worlds {list(source.world_names)!r}")
    if source.model_names:
        scope.append(f"models {list(source.model_names)!r}")
    scope_text = ", ".join(scope) if scope else "no models or worlds"
    return (
        f"OK {display_path(path)}: SDF {source.version}, {scope_text}, "
        f"{len(source.links)} links, {len(source.joints)} joints, "
        f"{len(source.mesh_paths)} resolved mesh references"
    )
