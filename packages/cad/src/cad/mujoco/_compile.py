"""Compiling an MJCF with MuJoCo, for ``cad mjcf validate --compile``.

MuJoCo's compiler is the one reader that knows every rule of the format: a mesh too small to hull, a
body with no inertia to move, a name used twice across an include, a default class that does not exist.
``compile_model`` loads the file as MuJoCo's own tools do (``MjModel.from_xml_path``: the includes, the
assets and the defaults resolved by the compiler itself, the mesh files read from disk) and collects the
warnings it issues meanwhile (``mju_user_warning``, the hook MuJoCo prints its warnings through, set for
the duration of the call and restored). ``compile_findings`` turns that into findings. No renderer and
no window: a headless core (``mujoco-core``) is all this imports.

The codes, one line each:

- ``compiled`` (info): MuJoCo compiled the model; its version and counts.
- ``compile_failed`` (error): MuJoCo refused the model, in its words (the element and the line).
- ``compile_warning`` (warning): a warning MuJoCo issued while compiling, in its words.
- ``compile_skipped`` (info): not compiled, mujoco is not installed here and the mode is ``auto``.
- ``compile_unavailable`` (error): not compiled, mujoco is not installed here and the mode is ``required``.

Then the model-health checks of MuJoCo's modelling guide ("Model tuning"), on the compiled model at
``qpos0`` and at the key named ``home`` (``cad.mujoco._health``, which keeps the thresholds):

- ``contacts_at_rest`` (warning): geoms of two bodies intersect at rest, deeper than 0.1 mm (1 mm for a
  free-floating tree resting on a static geom); the deepest pairs by name and depth.
- ``visual_geoms_collide`` (warning): a geom in groups 0-2 collides on a body that has group-3 collision geoms.
- ``inertia_from_visuals`` (warning): a body with no ``<inertial>`` takes mass from visual and collision geoms both.
- ``scale_suspect`` (warning): the moving geometry spans over 50 m or under 5 mm, or a mesh over 100 units.
- ``joint_limits_at_rest`` (warning): a limited hinge or slide lies outside its range at qpos0 or at home.
- ``defaults_not_recommended`` (info): Euler, a pyramidal cone, the default solref, or a long timestep with contacts.
- ``home_key`` (info): no key named home, the Menagerie convention.
- ``mass_summary`` (info): moving mass, moving bodies, nv, nu and the extents, one line.
- ``check_unavailable`` (info): a check failed inside and was skipped; it names the check.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cad._internal.findings import FindingsReport

__all__ = ["compile_findings", "compile_model", "installed"]

EXTRA = "cad[mujoco]"


def installed() -> bool:
    """Whether this process's environment holds mujoco (found, not loaded)."""
    import importlib.util

    try:
        return importlib.util.find_spec("mujoco") is not None
    except (ImportError, ValueError):
        return False


def compile_model(path: Path) -> tuple[Any, list[str]]:
    """``path`` compiled by MuJoCo: ``(MjModel, warnings)``. MuJoCo's ``ValueError`` for a model it refuses;
    ``ModuleNotFoundError`` naming the extra where mujoco is not installed."""
    try:
        import mujoco
    except ModuleNotFoundError as error:
        raise ModuleNotFoundError(f"mujoco comes with cad's mujoco integration: install {EXTRA}, or run the script "
                                  f"with cad run (add `{EXTRA}` to its header)", name=error.name) from None
    warnings: list[str] = []
    previous = mujoco.get_mju_user_warning()
    mujoco.set_mju_user_warning(lambda message: warnings.append(str(message)))
    try:
        model = mujoco.MjModel.from_xml_path(str(path))
    finally:
        mujoco.set_mju_user_warning(previous)
    return model, warnings


def compile_findings(path: Path, *, mode: str = "auto") -> FindingsReport:
    """Findings from compiling ``path`` with MuJoCo (see the package docstring)."""
    from cad._internal.xml_common import display_path

    findings = FindingsReport()
    where = display_path(path)
    if mode == "never":
        return findings
    if not installed():
        if mode == "required":
            findings.add("error", "compile_unavailable", f"MuJoCo is not installed here, and --compile required asks "
                                                         f"for it", path=where,
                         hint=f"install {EXTRA} in this environment; the cad command makes an environment of it "
                              f"on first need")
        else:
            findings.add("info", "compile_skipped", f"not compiled with MuJoCo: {EXTRA} is not installed here "
                                                    f"(--compile required makes that environment)", path=where)
        return findings
    try:
        model, warnings = compile_model(path)
    except ValueError as error:
        # MuJoCo's message names the element and the line in the file it read.
        findings.add("error", "compile_failed", f"MuJoCo refused the model: {_one_line(str(error))}", path=where)
        return findings
    for message in warnings:
        findings.add("warning", "compile_warning", f"MuJoCo warns: {_one_line(message)}", path=where)
    findings.add("info", "compiled", f"compiled by MuJoCo {_version()}: {model.nbody - 1} bodies, {model.njnt} joints, "
                                     f"{model.ngeom} geoms, {model.nmesh} meshes, {model.nkey} keyframes", path=where)
    try:
        from cad.mujoco._health import health_findings

        findings.extend(health_findings(model, path, where))
    except Exception as error:  # noqa: BLE001 - the health checks never stop a validation
        findings.add("info", "check_unavailable", f"the model-health checks could not run: "
                                                  f"{type(error).__name__}: {error}", path=where)
    return findings


def _one_line(text: str) -> str:
    return " ".join(piece.strip() for piece in str(text).strip().splitlines() if piece.strip())


def _version() -> str:
    try:
        import mujoco

        return str(mujoco.__version__)
    except Exception:  # noqa: BLE001 - the version is decoration on a finding
        return ""
