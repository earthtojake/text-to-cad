"""``check``: a MuJoCo model (an MJCF) compiled by MuJoCo and checked, as ``cad mujoco check FILE`` does.

An MJCF is MuJoCo's own file, and no document type: cad writes one (``cad model export ID robot.xml``, a
MuJoCo function's ``save``) and never shows one -- MuJoCo Studio does (``cad run mujoco-studio --model FILE``).
What cad does with one is ask MuJoCo: ``check`` compiles the file with MuJoCo's own compiler, the one reader
that knows every rule of the format, and answers a check's result (``cad.results.CheckResult``):

- what MuJoCo refused (``compile_failed``, an error, in its words) or warned of (``compile_warning``);
- the model-health checks (``_health``: geoms intersecting at rest, visual geoms that collide, inertia from
  the wrong geoms, a scale mismatch, a joint outside its range at rest, the engine's unfortunate defaults);
- what the model collides as (``collisions``, an info: the collision geoms by kind and by body, and the
  moving bodies that collide as nothing) and its contact excludes with how the two bodies of each stand at
  rest (``excludes``, an info): the two facts a MuJoCo function's choices change (``_report``). Every geom
  and every exclude is a row of ``measurements`` (``--json``).

Errors always block; under ``strict`` warnings do too. It needs MuJoCo: called where the integration is
missing it says which extra to add, and the ``cad`` command runs it in that extra's environment.
"""

from __future__ import annotations

from pathlib import Path

from cad.results import CheckResult

__all__ = ["SUFFIXES", "check"]

#: The files a MuJoCo model is written as (``cad.registry``: the integration's ``files``).
SUFFIXES = (".xml", ".mjcf")


def check(path: Path, *, strict: bool = False, verbose: bool = False) -> CheckResult:
    """Compile one MuJoCo model with MuJoCo and check it.

    MuJoCo's own compiler reads the model, so what it refuses or warns of is said in its words. Then
    the model-health checks of MuJoCo's modelling guide run on the compiled model, and two facts are
    said of it: what collides as what, body by body, and each contact exclude with how its two bodies
    stand at rest. Errors always block; under ``strict`` warnings do too.

    path: the .xml or .mjcf file to check.
    strict: treat warnings as blocking.
    verbose: narrate the target on stderr.
    """
    import sys

    from cad._internal.validation_door import blocks, display_path, failed, resolved_target, result_from_findings
    from cad.mujoco._compile import EXTRA, compile_findings, installed

    target = resolved_target(path, label="mujoco")
    if verbose:
        print(f"[mujoco] checking {target}", file=sys.stderr)
    if target.suffix.lower() not in SUFFIXES:
        return failed(target, f"target must be a {' or '.join(SUFFIXES)} file")
    if not target.is_file():
        return failed(target, "file not found")
    if not installed():
        raise ModuleNotFoundError(f"mujoco comes with cad's mujoco integration: install {EXTRA}, or run the script "
                                  f"with cad run (add `{EXTRA}` to its header)", name="mujoco")
    findings = compile_findings(target, mode="required")
    measurements: dict = {}
    summary = ""
    if not findings.errors:
        measurements, counts = _measured(target, findings, display_path(target))
        if not blocks(findings, strict=strict):
            summary = f"OK {display_path(target)}: {counts}"
    result = result_from_findings(target, findings.deduplicated(), strict=strict, summary=summary)
    return CheckResult(ok=result.ok, path=result.path, findings=result.findings, summary=result.summary,
                       measurements=measurements)


def _measured(target: Path, findings, where: str) -> tuple[dict, str]:
    """The compiled model's collisions and excludes, added to ``findings`` as two infos: the rows, and the
    summary's counts."""
    import mujoco

    from cad.mujoco._compile import compile_model
    from cad.mujoco._report import collisions, collisions_said, excludes, excludes_said

    model, _warnings = compile_model(target)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    colliding = collisions(mujoco, model)
    excluded = excludes(mujoco, model, data)
    findings.add("info", "collisions", collisions_said(colliding), path=where)
    findings.add("info", "excludes", excludes_said(excluded), path=where)
    try:  # a model's name is the spec's: the compiled model keeps none
        name = mujoco.MjSpec.from_file(str(target)).modelname
    except Exception:  # noqa: BLE001 - the name is decoration on the summary
        name = ""
    counts = (f"MuJoCo model {name!r}, " if name else "MuJoCo model, ") + (
        f"{model.nbody - 1} bod{'ies' if model.nbody != 2 else 'y'}, {model.njnt} joint{'s' if model.njnt != 1 else ''}, "
        f"{model.nu} actuator{'s' if model.nu != 1 else ''}, {colliding['geoms']} collision "
        f"geom{'s' if colliding['geoms'] != 1 else ''}, {model.nmesh} mesh{'es' if model.nmesh != 1 else ''}, "
        f"{model.nkey} key{'s' if model.nkey != 1 else ''}")
    return {"collisions": colliding, "excludes": excluded}, counts
