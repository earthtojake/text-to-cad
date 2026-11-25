"""``cad.urdf``: the URDF document type (``cad.registry``), a robot description.

It has no decorator: a robot description is an AUTHORED file, not a document a model makes.
``urdf.validate`` is ``cad urdf validate``; ``urdf.snapshot`` is ``cad urdf snapshot``
(``cad.engine.snapshot``).

``cad urdf validate`` is an ADAPTER over :func:`validate` rather than a generated mirror:
``--packages NAME=PATH`` is repeatable, and a repeatable key/value map is outside the
annotation set a parser can be derived from. It still answers with the same
:class:`~cad.results.CheckResult` every validation does.
"""

from __future__ import annotations

from pathlib import Path

from cad.results import CheckResult

__all__ = ["validate"]

SUFFIX = ".urdf"


def validate(
    path: Path,
    *,
    strict: bool = False,
    packages: "dict[str, Path] | None" = None,
    verbose: bool = False,
) -> CheckResult:
    """Check one URDF robot description for conformance.

    Collects every finding in one pass — structure, joints, inertials, mesh
    references — rather than stopping at the first. Errors always block; under
    ``strict`` warnings do too.

    path: the .urdf file to check.
    strict: treat warnings as blocking.
    packages: ``package://NAME/...`` mesh URI roots, name -> directory.
    verbose: narrate the target on stderr.
    """
    import sys

    from cad._internal.validation_door import failed, resolved_target, result_from_findings

    target = resolved_target(path, label="urdf")
    if verbose:
        # Narration goes to stderr so it never changes what a caller parses.
        print(f"[urdf] validating {target}", file=sys.stderr)
    if target.suffix.lower() != SUFFIX:
        return failed(target, f"target must be a {SUFFIX} file")
    if not target.is_file():
        return failed(target, "file not found")

    from cad.urdf._source import validate_urdf_file

    source, findings = validate_urdf_file(target, package_map=packages)
    findings = findings.deduplicated()
    return result_from_findings(
        target,
        findings,
        strict=strict,
        summary=_summary(target, source) if source is not None else "",
    )


def _summary(path: Path, source) -> str:
    from cad._internal.validation_door import display_path

    movable = sum(1 for joint in source.joints if joint.joint_type != "fixed")
    mass = f", total mass {source.total_mass:.4g} kg" if source.total_mass > 0 else ""
    return (
        f"OK {display_path(path)}: robot {source.robot_name!r}, root {source.root_link!r}, "
        f"{len(source.links)} links, {len(source.joints)} joints ({movable} movable), "
        f"{len(source.mesh_paths)} resolved mesh references{mass}"
    )


from cad._internal.document_type import bind as _bind  # noqa: E402

_bind(__name__)
