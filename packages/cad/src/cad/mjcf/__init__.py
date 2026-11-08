"""``cad.mjcf``: the MJCF document type (``cad.registry``), a MuJoCo model.

No decorator, for the reason :mod:`cad.urdf` gives: a model description is authored, not generated.
``cad mjcf validate`` is a generated MIRROR of :func:`validate`; ``cad mjcf snapshot`` draws one
(``cad.engine.snapshot``). ``COMPILE_MODES`` is the vocabulary of its ``compile`` option.

The reader is the type's own (``cad.mjcf._source``, the standard library alone); compiling the model
is the ``mujoco`` integration's (``cad.mujoco``), used where it is installed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, get_args

from cad.results import CheckResult

__all__ = ["validate"]

SUFFIXES = (".xml", ".mjcf")

#: What MuJoCo's compiler may be asked to do: ``compile``'s type, an enumeration, so the command's generated
#: parser takes these alone (``--compile``'s choices) and refuses any other by its flag.
Compile = Literal["auto", "required", "never"]
COMPILE_MODES: tuple[str, ...] = get_args(Compile)


def validate(
    path: Path,
    *,
    strict: bool = False,
    compile: Compile = "auto",
    verbose: bool = False,
) -> CheckResult:
    """Check one MJCF model for conformance.

    The bundled checks read the model as the viewer does -- structure, includes, defaults, assets,
    bodies, joints, geoms and mesh references -- and say what the viewer draws as less than MuJoCo
    makes of it. Compiling it with MuJoCo is the one check that knows every rule, and it runs where
    the mujoco integration is installed. Errors always block; under ``strict`` warnings do too.

    path: the .xml or .mjcf file to check.
    strict: treat warnings as blocking.
    compile: compile the model with MuJoCo as well -- auto (where cad[mujoco] is installed), required
        (fail without it: the cad command makes that environment first) or never.
    verbose: narrate the target on stderr.
    """
    import sys

    from cad._internal.validation_door import blocks, failed, resolved_target, result_from_findings

    if compile not in COMPILE_MODES:
        from cad._internal.refused import ArgumentRefused

        raise ArgumentRefused(f"compile must be one of {', '.join(COMPILE_MODES)}, got {compile!r}")
    target = resolved_target(path, label="mjcf")
    if verbose:
        print(f"[mjcf] validating {target}", file=sys.stderr)
    if target.suffix.lower() not in SUFFIXES:
        return failed(target, f"target must be a {' or '.join(SUFFIXES)} file")
    if not target.is_file():
        return failed(target, "file not found")

    from cad.mjcf._source import articulate, read_mjcf

    model, findings = read_mjcf(target)
    if compile != "never":
        from cad.mujoco._compile import compile_findings

        findings.extend(compile_findings(target, mode=compile))
    findings = findings.deduplicated()
    summary = ""
    if model is not None and not blocks(findings, strict=strict):
        articulation = articulate(model)
        controls = [joint for joint in articulation.joints if joint.type != "fixed" and joint.mimic is None]
        visuals = sum(len(found) for found in articulation.visuals.values())
        summary = (f"OK {_display(target)}: MJCF {model.name!r}, {len(model.bodies) - 1} bodies, "
                   f"{len(controls)} controls, {visuals} visuals, {len(model.mesh_files())} mesh files, "
                   f"{len(model.keyframes)} keyframes")
    return result_from_findings(target, findings, strict=strict, summary=summary)


def _display(path: Path) -> str:
    from cad._internal.validation_door import display_path

    return display_path(path)


from cad._internal.document_type import bind as _bind  # noqa: E402

_bind(__name__)
