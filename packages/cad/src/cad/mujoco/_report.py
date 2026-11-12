"""What a compiled MuJoCo model collides as, and the contact excludes it holds: facts, as data.

A MuJoCo function chooses each part's collision, and the question after it is what the model now collides
as. A picture answers it badly (translucent boxes inside meshes); a table answers it exactly. ``collisions``
reads the compiled ``MjModel``: every geom that collides (a ``contype`` or a ``conaffinity`` not 0), by the
body it is on, with its kind and its size as MuJoCo holds them (a mesh's: the half extents of the box
MuJoCo fits to it). ``excludes`` reads each ``<contact><exclude>`` pair with how far apart the two bodies'
collision geoms are at ``qpos0`` (``mj_geomDistance``, negative where they overlap): an exclude is between
two BODIES, so it stops every geom of one from colliding with every geom of the other, and a pair that is
apart at rest is either meant (two hulls that meet in some pose) or left over from a collision since
removed. Neither judges: ``check`` says them as two lines and keeps the rows in its ``measurements``.
"""

from __future__ import annotations

from typing import Any

__all__ = ["collisions", "collisions_said", "excludes", "excludes_said"]

#: How far (metres) the distance between two geoms is looked for: past it they are "over 1 m apart".
REACH = 1.0
#: Two bodies whose collision geoms are within this (metres) touch at rest: MuJoCo's own contact margin of 0
#: and the 0.1 mm the health checks call an intersection.
TOUCHING = 1e-4
#: The geom pairs of one exclude measured before it is said unmeasured: a pair of hundred-geom bodies is not
#: worth seconds of a check.
PAIRS = 2000
#: The bodies and the excludes a line names before it says how many more (``--json`` has every row).
SHOWN = 12


def _kinds(mujoco: Any) -> dict[int, str]:
    return {int(value): name[len("mjGEOM_"):].lower() for name, value in mujoco.mjtGeom.__members__.items()
            if name.startswith("mjGEOM_")}


def _body_name(model: Any, body: int) -> str:
    return "world" if body == 0 else (model.body(body).name or f"#{body}")


def _collides(model: Any, geom: int) -> bool:
    return bool(model.geom_contype[geom]) or bool(model.geom_conaffinity[geom])


def collisions(mujoco: Any, model: Any) -> dict[str, Any]:
    """The model's collision geoms: ``geoms`` (how many), ``by_kind`` (kind to count, most first) and ``bodies``,
    each ``{"body", "geoms": [{"name", "kind", "size"}]}`` in body order, a body that collides as nothing
    left out and counted in ``silent`` (the moving bodies with no collision geom, by name)."""
    kinds = _kinds(mujoco)
    by_body: dict[int, list[dict[str, Any]]] = {}
    by_kind: dict[str, int] = {}
    for geom in range(model.ngeom):
        if not _collides(model, geom):
            continue
        kind = kinds.get(int(model.geom_type[geom]), "geom")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        by_body.setdefault(int(model.geom_bodyid[geom]), []).append(
            {"name": model.geom(geom).name or f"#{geom}", "kind": kind,
             "size": [round(float(value), 6) for value in model.geom_size[geom]]})
    silent = [_body_name(model, body) for body in range(1, model.nbody)
              if body not in by_body and int(model.body_weldid[body]) != 0]
    return {"geoms": sum(by_kind.values()),
            "by_kind": dict(sorted(by_kind.items(), key=lambda item: (-item[1], item[0]))),
            "bodies": [{"body": _body_name(model, body), "geoms": found} for body, found in sorted(by_body.items())],
            "silent": silent}


def _counted(kinds: dict[str, int]) -> str:
    return ", ".join(f"{kind} {count}" for kind, count in kinds.items())


def collisions_said(found: dict[str, Any]) -> str:
    """``collisions`` as one line: the count by kind, each body's, and the moving bodies that collide as nothing."""
    if not found["geoms"]:
        return "no geom collides (every geom has contype and conaffinity 0)"
    rows = []
    for row in found["bodies"][:SHOWN]:
        kinds: dict[str, int] = {}
        for geom in row["geoms"]:
            kinds[geom["kind"]] = kinds.get(geom["kind"], 0) + 1
        rows.append(f"{row['body']} {len(row['geoms'])} ({_counted(kinds)})")
    more = len(found["bodies"]) - SHOWN
    text = (f"{found['geoms']} collision geom{'s' if found['geoms'] != 1 else ''} ({_counted(found['by_kind'])}) on "
            f"{len(found['bodies'])} bod{'ies' if len(found['bodies']) != 1 else 'y'}: " + "; ".join(rows)
            + (f"; and {more} more" if more > 0 else ""))
    if found["silent"]:
        shown = ", ".join(found["silent"][:SHOWN])
        rest = len(found["silent"]) - SHOWN
        text += f". Moving bodies that collide as nothing: {shown}" + (f" and {rest} more" if rest > 0 else "")
    return text


def excludes(mujoco: Any, model: Any, data: Any) -> list[dict[str, Any]]:
    """Each contact exclude: ``{"bodies": [a, b], "distance_mm", "state"}``, the distance between the two bodies'
    collision geoms at ``data``'s pose in millimetres (negative: overlapping; None where it was not measured) and
    ``state`` one of ``touching`` (within 0.1 mm, or overlapping), ``apart``, ``far`` (over ``REACH``),
    ``no_collision`` (one of the two has no collision geom) and ``unmeasured`` (more geom pairs than ``PAIRS``)."""
    geoms: dict[int, list[int]] = {}
    for geom in range(model.ngeom):
        if _collides(model, geom):
            geoms.setdefault(int(model.geom_bodyid[geom]), []).append(geom)
    rows = []
    for signature in model.exclude_signature:
        first, second = int(signature) >> 16, int(signature) & 0xFFFF
        row: dict[str, Any] = {"bodies": [_body_name(model, first), _body_name(model, second)], "distance_mm": None}
        ours, theirs = geoms.get(first, []), geoms.get(second, [])
        if not ours or not theirs:
            row["state"] = "no_collision"
        elif len(ours) * len(theirs) > PAIRS:
            row["state"] = "unmeasured"
        else:
            nearest = min(float(mujoco.mj_geomDistance(model, data, a, b, REACH, None)) for a in ours for b in theirs)
            if nearest >= REACH:
                row["state"] = "far"
            else:
                row["distance_mm"] = round(nearest * 1000.0, 3)
                row["state"] = "touching" if nearest <= TOUCHING else "apart"
        rows.append(row)
    return rows


def excludes_said(rows: list[dict[str, Any]]) -> str:
    """``excludes`` as one line: each pair and how its two bodies stand at rest."""
    if not rows:
        return "no contact exclude"

    def said(row: dict[str, Any]) -> str:
        pair = " and ".join(row["bodies"])  # never "/": a prefixed body's name holds one (panda/link0)
        state = row["state"]
        if state == "touching":
            return f"{pair} touching at rest"
        if state == "apart":
            return f"{pair} {row['distance_mm']:g} mm apart at rest"
        if state == "far":
            return f"{pair} over {REACH:g} m apart at rest"
        if state == "no_collision":
            return f"{pair}, where one has no collision geom"
        return f"{pair} (not measured: too many geoms)"

    more = len(rows) - SHOWN
    return (f"{len(rows)} contact exclude{'s' if len(rows) != 1 else ''}, each between two bodies whole: "
            + "; ".join(said(row) for row in rows[:SHOWN]) + (f"; and {more} more" if more > 0 else ""))
