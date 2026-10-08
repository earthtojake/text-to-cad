"""The public ``urdf`` namespace: the verbs that operate on URDF descriptions.

Unlike ``step``/``dxf``/``stl``, this namespace carries no decorator: a robot
description is an AUTHORED file, not a document cadgen generates, so there is
nothing to declare. It is a plain module.

``cadgen urdf validate`` is an ADAPTER over :func:`validate` rather than a
generated mirror: ``--packages NAME=PATH`` is repeatable, and a repeatable
key/value map is outside the annotation set a parser can be derived from. The
verb still answers with the same :class:`~cadgen.results.ValidationResult` the
other two families' mirrors do.
"""

from __future__ import annotations

from pathlib import Path

from cadgen._internal.snapshot_door import robot_snapshot_verb
from cadgen.results import ValidationResult

__all__ = ["snapshot", "validate"]

SUFFIX = ".urdf"

#: ``cadgen urdf snapshot``'s verb: render the robot the browser assembles from
#: this description's link meshes.
snapshot = robot_snapshot_verb("urdf")


def validate(
    path: Path,
    *,
    strict: bool = False,
    packages: "dict[str, Path] | None" = None,
    verbose: bool = False,
) -> ValidationResult:
    """Check one URDF robot description for conformance.

    Collects every finding in one pass — structure, joints, inertials, mesh
    references — rather than stopping at the first. Errors always block; under
    ``strict`` warnings do too.

    path: the .urdf file to validate.
    strict: treat warnings as blocking.
    packages: ``package://NAME/...`` mesh URI roots, name -> directory.
    verbose: narrate the target on stderr.
    """
    import sys

    from cadgen._internal.validation_door import failed, resolved_target, result_from_findings

    target = resolved_target(path, label="urdf")
    if verbose:
        # Narration goes to stderr so it never changes what a caller parses.
        print(f"[urdf] validating {target}", file=sys.stderr)
    if target.suffix.lower() != SUFFIX:
        return failed(target, f"target must be a {SUFFIX} file")
    if not target.is_file():
        return failed(target, "file not found")

    from cadgen.urdf_source import validate_urdf_file

    source, findings = validate_urdf_file(target, package_map=packages)
    findings = findings.deduplicated()
    return result_from_findings(
        target,
        findings,
        strict=strict,
        summary=_summary(target, source) if source is not None else "",
    )


def _summary(path: Path, source) -> str:
    from cadgen._internal.validation_door import display_path

    movable = sum(1 for joint in source.joints if joint.joint_type != "fixed")
    mass = f", total mass {source.total_mass:.4g} kg" if source.total_mass > 0 else ""
    return (
        f"OK {display_path(path)}: robot {source.robot_name!r}, root {source.root_link!r}, "
        f"{len(source.links)} links, {len(source.joints)} joints ({movable} movable), "
        f"{len(source.mesh_paths)} resolved mesh references{mass}"
    )
