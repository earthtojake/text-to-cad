"""The public ``srdf`` namespace: the verbs that operate on MoveIt2 SRDFs.

No decorator, for the reason :mod:`cadgen.urdf` gives. ``cadgen srdf validate``
is a generated MIRROR of :func:`validate` (README law 6).

An SRDF is only meaningful against its URDF, and that context is resolved rather
than passed: the paired URDF is found from the SRDF's robot name and directory,
and a missing pairing is itself a finding.
"""

from __future__ import annotations

from pathlib import Path

from cadgen.results import ValidationResult

__all__ = ["validate"]

SUFFIX = ".srdf"


def validate(
    path: Path,
    *,
    strict: bool = False,
    verbose: bool = False,
) -> ValidationResult:
    """Check one SRDF against its paired URDF.

    Cross-validates every name, chain, state and disabled pair the SRDF declares
    against the robot the URDF actually describes. Errors always block; under
    ``strict`` warnings do too.

    path: the .srdf file to validate.
    strict: treat warnings as blocking.
    verbose: narrate the target on stderr.
    """
    import sys

    from cadgen._internal.validation_door import failed, resolved_target, result_from_findings

    target = resolved_target(path, label="srdf")
    if verbose:
        print(f"[srdf] validating {target}", file=sys.stderr)
    if target.suffix.lower() != SUFFIX:
        return failed(target, f"target must be a {SUFFIX} file")
    if not target.is_file():
        return failed(target, "file not found")

    from cadgen.srdf_source import parse_srdf_file
    from cadgen.srdf_validation import (
        read_urdf_robot,
        resolve_paired_urdf,
        validate_srdf_against_urdf,
    )

    source, findings = parse_srdf_file(target)
    urdf_path: Path | None = None
    if source is not None:
        urdf_path = resolve_paired_urdf(
            source.robot_name, srdf_dir=target.parent, result=findings
        )
        if urdf_path is not None:
            robot = read_urdf_robot(urdf_path, findings)
            if robot is not None:
                validate_srdf_against_urdf(source, urdf_robot=robot, result=findings)
    findings = findings.deduplicated()
    summary = _summary(target, source, urdf_path) if source is not None and urdf_path else ""
    return result_from_findings(target, findings, strict=strict, summary=summary)


def _summary(path: Path, source, urdf_path: Path) -> str:
    from cadgen.srdf_validation import display_path

    return (
        f"OK {display_path(path)}: robot {source.robot_name!r}, urdf {display_path(urdf_path)}, "
        f"{len(source.planning_groups)} groups, {len(source.end_effectors)} end effectors, "
        f"{len(source.group_states)} group states, "
        f"{len(source.disabled_collision_pairs)} disabled collision pairs, "
        f"{len(source.virtual_joints)} virtual joints"
    )
