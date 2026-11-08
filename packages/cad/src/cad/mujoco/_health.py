"""The model-health checks ``cad mjcf validate --compile`` runs on a model MuJoCo compiled.

MuJoCo's modelling guide ("Model tuning") lists what to rule out before tuning anything: geoms that
intersect at ``t = 0``, visual geoms that collide, inertias computed from the wrong geoms, a unit or
scale mismatch, the engine's unfortunate defaults, and targets past joint limits. Each check here reads
the compiled ``MjModel`` and one ``MjData`` after ``mj_forward`` at ``qpos0`` (and at the key named
``home`` where there is one, saying which), and the authored ``MjSpec`` where only the authored facts
answer. Each is milliseconds, and none raises: a check that fails inside becomes one ``check_unavailable``
info naming it. The thresholds are heuristics and say so; they are tuned to be sure rather than complete.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable

from cad._internal.findings import FindingsReport

__all__ = ["health_findings"]

#: Penetration (metres) beyond which two geoms intersect at rest: MuJoCo's own ``dist < -1e-4``.
INTERSECTING = 1e-4
#: Penetration a free-floating tree may rest with on a static geom (a floor, a table): 1 mm is the soft
#: contact settling, not an authoring mistake.
RESTING = 1e-3
#: How many pairs, geoms or joints a message names before it says how many more.
SHOWN = 5
#: Moving geometry spanning more than this (metres) is likely authored in millimetres.
EXTENT_MAX = 50.0
#: Moving geometry spanning less than this (metres) is likely authored in metres where it meant millimetres.
EXTENT_MIN = 0.005
#: A mesh spanning more than this (model units) after its ``scale``: likely millimetres read as metres.
MESH_EXTENT_MAX = 100.0
#: The solref MuJoCo puts on a contact nobody tuned.
DEFAULT_SOLREF = (0.02, 1.0)
#: The largest timestep the guide suggests for a model with contacts (5 ms; 0.5-2 ms for manipulation).
TIMESTEP_MAX = 0.005
#: Group 3 is the collision group by MuJoCo's (and the Menagerie's) convention; 0-2 are visual.
COLLISION_GROUP = 3


def health_findings(model: Any, path: Path, where: str) -> FindingsReport:
    """The health findings of ``model`` (compiled from ``path``), each attributed to ``where``."""
    import mujoco

    findings = FindingsReport()
    poses = _poses(mujoco, model)
    checks: list[tuple[str, Callable[[], None]]] = [
        ("contacts_at_rest", lambda: _contacts_at_rest(mujoco, model, poses, findings, where)),
        ("visual_geoms_collide", lambda: _visual_geoms_collide(model, findings, where)),
        ("inertia_from_visuals", lambda: _inertia_from_visuals(mujoco, path, findings, where)),
        ("scale_suspect", lambda: _scale_suspect(mujoco, model, poses, findings, where)),
        ("joint_limits_at_rest", lambda: _joint_limits_at_rest(mujoco, model, poses, findings, where)),
        ("defaults_not_recommended", lambda: _defaults_not_recommended(mujoco, model, findings, where)),
        ("home_key", lambda: _home_key(model, findings, where)),
        ("mass_summary", lambda: _mass_summary(model, poses, findings, where)),
    ]
    for name, check in checks:
        try:
            check()
        except Exception as error:  # noqa: BLE001 - a check that fails inside is a note, never a crash
            findings.add("info", "check_unavailable", f"the {name} check could not run: "
                                                      f"{type(error).__name__}: {error}", path=where)
    return findings


# --- poses -----------------------------------------------------------------------------------------------


def _poses(mujoco: Any, model: Any) -> list[tuple[str, Any, Any]]:
    """``(label, qpos, data)`` at qpos0, and at the key named ``home`` where there is one, each forwarded."""
    poses = []
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    poses.append(("at qpos0", data.qpos.copy(), data))
    home = _key_id(model, "home")
    if home >= 0:
        keyed = mujoco.MjData(model)
        mujoco.mj_resetDataKeyframe(model, keyed, home)
        mujoco.mj_forward(model, keyed)
        poses.append(("at key 'home'", keyed.qpos.copy(), keyed))
    return poses


def _key_id(model: Any, name: str) -> int:
    for index in range(model.nkey):
        if model.key(index).name == name:
            return index
    return -1


# --- names -----------------------------------------------------------------------------------------------


def _body(model: Any, index: int) -> str:
    name = model.body(index).name
    return f"body {name!r}" if name else f"body #{index}"


def _geom(model: Any, index: int) -> str:
    name = model.geom(index).name
    return f"geom {name!r}" if name else f"geom #{index} of {_body(model, int(model.geom_bodyid[index]))}"


def _joint(model: Any, index: int) -> str:
    name = model.joint(index).name
    return f"joint {name!r}" if name else f"joint #{index} of {_body(model, int(model.jnt_bodyid[index]))}"


def _listed(items: list[str]) -> str:
    shown = ", ".join(items[:SHOWN])
    return shown if len(items) <= SHOWN else f"{shown} and {len(items) - SHOWN} more"


def _moving(model: Any, body: int) -> bool:
    """Whether ``body`` moves: it is not welded to the world."""
    return int(model.body_weldid[body]) != 0


def _floating(mujoco: Any, model: Any, body: int) -> bool:
    """Whether ``body``'s kinematic tree hangs from a free joint (an object dropped into the scene)."""
    root = int(model.body_rootid[body])
    first = int(model.body_jntadr[root])
    return root != 0 and first >= 0 and int(model.jnt_type[first]) == mujoco.mjtJoint.mjJNT_FREE


def _colliding(model: Any, geom: int) -> bool:
    return bool(model.geom_contype[geom]) or bool(model.geom_conaffinity[geom])


# --- the checks ------------------------------------------------------------------------------------------


def _contacts_at_rest(mujoco: Any, model: Any, poses: list, findings: FindingsReport, where: str) -> None:
    for label, _qpos, data in poses:
        pairs: list[tuple[float, str]] = []
        for index in range(data.ncon):
            contact = data.contact[index]
            first, second = int(contact.geom1), int(contact.geom2)
            body1, body2 = int(model.geom_bodyid[first]), int(model.geom_bodyid[second])
            if body1 == body2:
                continue
            depth = -float(contact.dist)
            static_vs_floating = ((not _moving(model, body1) and _floating(mujoco, model, body2))
                                  or (not _moving(model, body2) and _floating(mujoco, model, body1)))
            if depth <= (RESTING if static_vs_floating else INTERSECTING):
                continue
            pairs.append((depth, f"{_geom(model, first)} and {_geom(model, second)} by {depth * 1000:.3g} mm"))
        if not pairs:
            continue
        pairs.sort(key=lambda pair: -pair[0])
        findings.add("warning", "contacts_at_rest",
                     f"{len(pairs)} geom pair(s) intersect {label}, deepest first: "
                     f"{_listed([text for _depth, text in pairs])}", path=where,
                     hint="move the geoms apart, exclude the pair (<contact><exclude>), or give the visual geom "
                          "contype=\"0\" conaffinity=\"0\"; stiffening contacts to hide an intersection makes "
                          "the model chatter or diverge")


def _visual_geoms_collide(model: Any, findings: FindingsReport, where: str) -> None:
    has_collision = {int(model.geom_bodyid[geom]) for geom in range(model.ngeom)
                     if int(model.geom_group[geom]) == COLLISION_GROUP}
    offending = [geom for geom in range(model.ngeom)
                 if int(model.geom_bodyid[geom]) in has_collision and 0 <= int(model.geom_group[geom]) <= 2
                 and _colliding(model, geom)]
    if not offending:
        return
    bodies = sorted({int(model.geom_bodyid[geom]) for geom in offending})
    findings.add("warning", "visual_geoms_collide",
                 f"{len(offending)} visual geom(s) in groups 0-2 collide on {len(bodies)} body(ies) that have "
                 f"group-3 collision geoms: {_listed([_geom(model, geom) for geom in offending])}", path=where,
                 hint="give the visual geoms (or their default class) contype=\"0\" conaffinity=\"0\" so only "
                      "the collision geoms make contacts")


def _inertia_from_visuals(mujoco: Any, path: Path, findings: FindingsReport, where: str) -> None:
    spec = mujoco.MjSpec.from_file(str(path))
    from_geom = spec.compiler.inertiafromgeom
    if from_geom == mujoco.mjtInertiaFromGeom.mjINERTIAFROMGEOM_FALSE:
        return  # the geoms never count: every body's inertia is its <inertial>
    low, high = (int(value) for value in spec.compiler.inertiagrouprange)
    doubled: list[str] = []
    for body in spec.bodies:
        if body.name == "world":
            continue
        if body.explicitinertial and from_geom != mujoco.mjtInertiaFromGeom.mjINERTIAFROMGEOM_TRUE:
            continue
        weighed = [geom for geom in body.geoms if low <= int(geom.group) <= high and _carries_mass(geom)]
        visual = [geom for geom in weighed if not geom.contype and not geom.conaffinity]
        colliding = [geom for geom in weighed if geom.contype or geom.conaffinity]
        groups = {int(geom.group) for geom in weighed}
        both_groups = COLLISION_GROUP in groups and bool(groups - {COLLISION_GROUP})
        if not ((visual and colliding) or both_groups):
            continue
        named = body.name and f"body {body.name!r}" or "an unnamed body"
        doubled.append(f"{named} (geoms in groups {', '.join(str(group) for group in sorted(groups))})")
    if doubled:
        findings.add("warning", "inertia_from_visuals",
                     f"{len(doubled)} body(ies) with no <inertial> take mass from both visual and collision geoms, "
                     f"so their mass and inertia count the shape twice: {_listed(doubled)}", path=where,
                     hint="give the visual geoms (or their default class) mass=\"0\" or density=\"0\", or give "
                          "the body an explicit <inertial>")


def _carries_mass(geom: Any) -> bool:
    mass = float(geom.mass)
    if not math.isnan(mass):
        return mass > 0
    return float(geom.density) > 0


def _geometry_extents(mujoco: Any, model: Any, data: Any) -> tuple[list[float], bool] | None:
    """The world-axis extents (metres) of the moving bodies' geoms in ``data``'s pose (all non-plane geoms
    where nothing moves), and whether they are the moving ones; None with no such geom."""
    import numpy

    geoms = [geom for geom in range(model.ngeom) if int(model.geom_type[geom]) != mujoco.mjtGeom.mjGEOM_PLANE]
    moving = [geom for geom in geoms if _moving(model, int(model.geom_bodyid[geom]))]
    chosen = moving or geoms
    if not chosen:
        return None
    signs = numpy.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], dtype=float)
    low = numpy.full(3, numpy.inf)
    high = numpy.full(3, -numpy.inf)
    for geom in chosen:
        center, half = model.geom_aabb[geom][:3], model.geom_aabb[geom][3:]
        rotation = data.geom_xmat[geom].reshape(3, 3)
        corners = data.geom_xpos[geom] + (center + signs * half) @ rotation.T
        low = numpy.minimum(low, corners.min(axis=0))
        high = numpy.maximum(high, corners.max(axis=0))
    return [float(value) for value in high - low], bool(moving)


def _scale_suspect(mujoco: Any, model: Any, poses: list, findings: FindingsReport, where: str) -> None:
    import numpy

    reasons: list[str] = []
    measured = _geometry_extents(mujoco, model, poses[0][2])
    if measured is not None:
        extents, moving = measured
        what = "the moving geometry" if moving else "the geometry"
        largest = max(extents)
        if largest > EXTENT_MAX:
            reasons.append(f"{what} spans {_extents(extents)} at qpos0, more than {EXTENT_MAX:g} m")
        elif largest < EXTENT_MIN:
            reasons.append(f"{what} spans {_extents(extents)} at qpos0, less than {EXTENT_MIN * 1000:g} mm")
    for mesh in range(model.nmesh):
        start, count = int(model.mesh_vertadr[mesh]), int(model.mesh_vertnum[mesh])
        if count == 0:
            continue
        vertices = model.mesh_vert[start:start + count]
        spans = [float(value) for value in vertices.max(axis=0) - vertices.min(axis=0)]
        if max(spans) > MESH_EXTENT_MAX:
            name = model.mesh(mesh).name or f"#{mesh}"
            reasons.append(f"mesh {name!r} spans {_extents(spans)} after its scale")
    if not reasons:
        return
    total = float(numpy.sum([model.body_mass[body] for body in range(model.nbody) if _moving(model, body)]))
    findings.add("warning", "scale_suspect",
                 f"the model's scale looks wrong (moving mass {total:.4g} kg): {'; '.join(reasons[:SHOWN])}"
                 + ("" if len(reasons) <= SHOWN else f" and {len(reasons) - SHOWN} more"), path=where,
                 hint="MuJoCo reads lengths in metres: a mesh exported in millimetres needs scale=\"0.001 0.001 "
                      "0.001\" on its <mesh>; these thresholds are heuristics, so ignore this for a model that "
                      "really is that large or small")


def _extents(spans: list[float]) -> str:
    return " x ".join(f"{value:.3g}" for value in spans) + " m"


def _joint_limits_at_rest(mujoco: Any, model: Any, poses: list, findings: FindingsReport, where: str) -> None:
    angular = {int(mujoco.mjtJoint.mjJNT_HINGE)}
    scalar = angular | {int(mujoco.mjtJoint.mjJNT_SLIDE)}
    for label, qpos, _data in poses:
        outside: list[str] = []
        for joint in range(model.njnt):
            kind = int(model.jnt_type[joint])
            if kind not in scalar or not bool(model.jnt_limited[joint]):
                continue
            low, high = (float(value) for value in model.jnt_range[joint])
            value = float(qpos[int(model.jnt_qposadr[joint])])
            if low - 1e-9 <= value <= high + 1e-9:
                continue
            unit = "rad" if kind in angular else "m"
            text = f"{_joint(model, joint)} is {value:.4g} {unit}, range [{low:.4g}, {high:.4g}] {unit}"
            if kind in angular:
                text += f" ([{math.degrees(low):.4g}, {math.degrees(high):.4g}] deg)"
            outside.append(text)
        if outside:
            findings.add("warning", "joint_limits_at_rest",
                         f"{len(outside)} joint(s) lie outside their range {label}: {_listed(outside)}", path=where,
                         hint="the limit pushes the joint back on the first step: set the joint's ref inside its "
                              "range, or start from a key named home whose qpos respects every range (check "
                              "<compiler angle> if the range looks like radians read as degrees)")


def _defaults_not_recommended(mujoco: Any, model: Any, findings: FindingsReport, where: str) -> None:
    notes: list[str] = []
    if int(model.opt.integrator) == int(mujoco.mjtIntegrator.mjINT_EULER):
        notes.append("integrator is Euler (the guide recommends implicitfast)")
    colliding = [geom for geom in range(model.ngeom) if _colliding(model, geom)]
    if colliding:
        timestep = float(model.opt.timestep)
        if int(model.opt.cone) == int(mujoco.mjtCone.mjCONE_PYRAMIDAL):
            notes.append("cone is pyramidal (the guide recommends elliptic with impratio 10 for manipulation)")
        solrefs = {tuple(round(float(value), 9) for value in model.geom_solref[geom]) for geom in colliding}
        if solrefs == {DEFAULT_SOLREF} and model.npair == 0:
            notes.append("every contact keeps the default solref 0.02 1 (the guide recommends solref[0] of "
                         "0.004-0.01)")
        soft = sorted({ref[0] for ref in solrefs if 0 < ref[0] < 2 * timestep})
        if soft:
            notes.append(f"solref[0] {_listed([f'{value:g}' for value in soft])} is below 2 x timestep "
                         f"({2 * timestep:g} s), so MuJoCo clamps it")
        if timestep > TIMESTEP_MAX:
            notes.append(f"timestep {timestep:g} s is above {TIMESTEP_MAX:g} s for a model with contacts (the "
                         f"guide suggests 0.5-2 ms for contact-rich manipulation)")
    if notes:
        findings.add("info", "defaults_not_recommended",
                     f"MuJoCo defaults the modelling guide advises against: {'; '.join(notes)}", path=where,
                     hint="set them once in <option> and the top-level <default> (MuJoCo's modelling guide, "
                          "\"Tuning defaults\")")


def _home_key(model: Any, findings: FindingsReport, where: str) -> None:
    if _key_id(model, "home") < 0:
        findings.add("info", "home_key", f"no key named home ({model.nkey} keyframes): the Menagerie convention "
                                         f"is a <key name=\"home\"> a simulation starts from", path=where)


def _mass_summary(model: Any, poses: list, findings: FindingsReport, where: str) -> None:
    import mujoco

    moving = [body for body in range(model.nbody) if _moving(model, body)]
    total = float(sum(float(model.body_mass[body]) for body in moving))
    text = (f"moving mass {total:.4g} kg in {len(moving)} moving bodies, {model.nv} degrees of freedom (nv), "
            f"{model.nu} actuators (nu)")
    measured = _geometry_extents(mujoco, model, poses[0][2])
    if measured is not None:
        extents, is_moving = measured
        text += f"; {'moving ' if is_moving else ''}geometry spans {_extents(extents)} at qpos0"
    findings.add("info", "mass_summary", text, path=where)
