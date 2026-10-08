"""A model's articulation: how its written geometry moves, resolved for a player.

cadgen declares, validates and resolves a STEP's kinematics (``cadgen.kinematics``,
``_internal.kinematics_resolve``). This module turns the resolved block, against the
document's flattened tree, into ONE artifact a page plays with closed-form arithmetic and
nothing else: no name resolution, no defaults, no ownership decisions, no limit guesses.
Every fact a person or a job can name -- a control id, a limit, a named pose, which
occurrences a joint moves -- is minted here, once.

The artifact::

    {
      "schemaVersion": 1,
      "controls": [{"id", "label", "unit", "min", "max", "default"}],
      "joints":   [{"id", "parent", "kind", "origin", "axis",
                    "turn": {"bias", "terms"}, "travel": {"bias", "terms"}}],
      "carries":  {joint id: [occurrence id, ...]},
      "handles":  [{"id", "joint", "dof", "control", "weight", "label", "unit", "min", "max"}],
      "poses":    {name: {control id: value}},
      "opening":  {control id: value},
    }

- ``controls`` are what a person or a job sets, in declaration order. A STEP's are its DOF
  ids exactly as ``kinematics_dof_ids`` mints them (``<mate>``, ``<mate>.turn``,
  ``<mate>.travel``, ``<coupling>``); the ``--kinematics`` keys, the named poses and a
  stored pose all name them. A revolute control is in degrees, a slider's in model units,
  a coupling's a plain number. ``min``/``max`` are the declared limits (``null`` means
  unbounded, which a continuous robot joint is); ``default`` is the control's rest value.
- ``joints`` are listed parents first. A joint's ``origin`` and ``axis`` (unit) are in the
  model's REST space -- the model as written: a STEP at every control 0 -- and its motion is
  displacement about that axis from rest, carried by its parent joint's motion. ``turn``
  (degrees) and ``travel`` (model units) are affine rows over the controls:
  ``bias + sum(weight * control)``, with every unit conversion folded into the weights.
  A STEP coupling (own value plus ratio times the coupling) and a robot's mimic (multiplier
  times the leader plus an offset) are the same row. A ``fixed`` joint has no row: it only
  carries its parent's motion. ``kind`` is ``revolute``, ``slider``, ``cylindrical`` or
  ``fixed``.
- ``carries`` names the leaf occurrences each joint moves. Occurrences a deeper joint also
  names belong to the deeper joint (a horn inside a servo group, fastened to the jaw beside
  it, rides the jaw once, never the group's motion on top), so every occurrence appears
  under exactly one joint.
- ``handles`` are what a drag gesture takes hold of: one per movable joint row, naming the
  control the gesture writes (``control``) and that control's weight in the row (a member
  geared by exactly one coupling writes THROUGH the coupling, so dragging a sun gear turns the
  train; a member geared by two couplings writes itself, since the inverse is
  underdetermined). ``min``/``max`` are the row's own declared range.
- ``poses`` are the declared presets, each a full configuration over the controls it names
  (every other control is at its ``default``); ``opening`` is the configuration a view
  opens with.

The evaluator at the bottom is the reference the page's player is compared against: joint
values from controls by dot products, each joint's world delta from its parent's and its
own displacement.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

from cadgen.kinematics import kinematics_dof_ids, kinematics_dof_limits

__all__ = [
    "ARTICULATION_SCHEMA_VERSION",
    "step_articulation",
    "articulation_control_values",
    "joint_values",
    "joint_matrices",
]

ARTICULATION_SCHEMA_VERSION = 1

_CYLINDRICAL_ROWS = (("turn", "deg"), ("travel", "mm"))


def _fail(message: str) -> ValueError:
    return ValueError(f"kinematics: {message}")


def _strip(ref: object) -> str:
    return str(ref or "").strip().lstrip("#")


def _unit(vector: object, *, mate: str) -> list[float]:
    try:
        x, y, z = (float(v) for v in vector)  # type: ignore[union-attr]
    except (TypeError, ValueError):
        raise _fail(f"mate {mate!r}: axis is not resolved to numbers") from None
    length = math.hypot(x, y, z)
    if not math.isfinite(length) or length < 1e-12:
        raise _fail(f"mate {mate!r}: axis direction must be non-zero")
    return [x / length, y / length, z / length]


def _point(vector: object, *, mate: str) -> list[float]:
    try:
        return [float(v) for v in vector]  # type: ignore[union-attr]
    except (TypeError, ValueError):
        raise _fail(f"mate {mate!r}: axis is not resolved to numbers") from None


def _mates_in_tree_order(mates: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Parents before children, declaration order otherwise. The declaration is a tree
    (``normalize_kinematics`` refuses a second parent and a cycle), so this terminates."""
    by_child = {str(mate.get("child")): mate for mate in mates}
    ordered: list[Mapping[str, Any]] = []
    placed: set[str] = set()

    def place(mate: Mapping[str, Any]) -> None:
        child = str(mate.get("child"))
        if child in placed:
            return
        parent = by_child.get(str(mate.get("parent")))
        if parent is not None and str(parent.get("child")) not in placed:
            place(parent)
        placed.add(child)
        ordered.append(mate)

    for mate in mates:
        place(mate)
    return ordered


def _tree_members(descriptor: Mapping[str, Any]) -> tuple[dict[str, list[str]], list[tuple[str, str]]]:
    """Every instance-tree node's leaf members (a leaf's are itself), and the leaves with
    their names: the occurrence namespace a mate's end resolves in."""
    leaves = [(str(item.get("id") or "").strip(), str(item.get("name") or "").strip())
              for item in descriptor.get("occurrences") or [] if isinstance(item, Mapping)]
    leaf_ids = {leaf_id for leaf_id, _name in leaves if leaf_id}
    members: dict[str, list[str]] = {}

    def visit(node: object) -> list[str]:
        if not isinstance(node, Mapping):
            return []
        node_id = str(node.get("id") or "").strip()
        found = [node_id] if node_id in leaf_ids else []
        for child in node.get("children") or []:
            found.extend(visit(child))
        if node_id:
            members[node_id] = found
        return found

    assembly = descriptor.get("assembly")
    visit(assembly.get("root") if isinstance(assembly, Mapping) else None)
    for leaf_id in leaf_ids:
        members.setdefault(leaf_id, [leaf_id])
    return members, leaves


def _occurrences_for_end(
    descriptor_members: tuple[dict[str, list[str]], list[tuple[str, str]]], mate: Mapping[str, Any], key: str,
) -> list[str]:
    """The leaves a mate's end names: the subtree of the node the build resolved
    (``<key>Id``), else the occurrences the authored label names by id or by name."""
    members, leaves = descriptor_members
    node_id = _strip(mate.get(f"{key}Id"))
    if node_id and node_id in members:
        return list(members[node_id])
    label = _strip(mate.get(key))
    if label in members:
        return list(members[label])
    return [leaf_id for leaf_id, name in leaves if leaf_id and (name == label or leaf_id == label)]


def _drivers(block: Mapping[str, Any]) -> dict[str, tuple[str, float]]:
    """``{mate DOF: (coupling, ratio)}`` for every DOF exactly ONE coupling gears with a
    nonzero ratio: the additive gearing is then invertible, so a gesture on the member can be
    written as a value of the coupling. A DOF two couplings gear stays its own control."""
    drivers: dict[str, tuple[str, float]] = {}
    contested: set[str] = set()
    for coupling in block.get("couplings") or []:
        name = str(coupling.get("name") or "")
        for dof, raw in (coupling.get("gears") or {}).items():
            ratio = float(raw or 0)
            if not name or not ratio:
                continue
            if dof in drivers:
                contested.add(str(dof))
            else:
                drivers[str(dof)] = (name, ratio)
    return {dof: driver for dof, driver in drivers.items() if dof not in contested}


def _row(dof: str, block: Mapping[str, Any]) -> dict[str, Any]:
    terms: list[list[Any]] = [[dof, 1.0]]
    for coupling in block.get("couplings") or []:
        ratio = float((coupling.get("gears") or {}).get(dof, 0) or 0)
        if ratio:
            terms.append([str(coupling.get("name")), ratio])
    return {"bias": 0.0, "terms": terms}


def step_articulation(descriptor: Mapping[str, Any], kinematics: object) -> dict[str, Any] | None:
    """The articulation of a STEP from its resolved kinematics block, against the document's
    flattened tree. ``None`` when the block declares no mates (nothing to pose). A block this
    cadgen cannot read raises ``ValueError`` naming what is wrong."""
    if not isinstance(kinematics, Mapping):
        return None
    mates = [mate for mate in kinematics.get("mates") or [] if isinstance(mate, Mapping)]
    if not mates:
        return None
    for mate in mates:
        if not str(mate.get("name") or "").strip():
            raise _fail("a mate has no name")
        if str(mate.get("kind")) not in ("revolute", "slider", "cylindrical", "fastened"):
            raise _fail(f"mate {mate.get('name')!r} has unknown kind {mate.get('kind')!r}")

    limits = kinematics_dof_limits(kinematics)
    controls = [
        {"id": dof, "label": dof, "unit": limits[dof][2], "min": limits[dof][0], "max": limits[dof][1], "default": 0.0}
        for dof in kinematics_dof_ids(kinematics)
    ]
    drivers = _drivers(kinematics)
    members = _tree_members(descriptor)
    by_child = {str(mate.get("child")): str(mate.get("name")) for mate in mates}

    joints: list[dict[str, Any]] = []
    handles: list[dict[str, Any]] = []
    named: list[tuple[str, list[str]]] = []
    for mate in _mates_in_tree_order(mates):
        name = str(mate.get("name"))
        kind = str(mate.get("kind"))
        joint: dict[str, Any] = {
            "id": name,
            "parent": by_child.get(str(mate.get("parent"))),
            "kind": "fixed" if kind == "fastened" else kind,
        }
        if kind != "fastened":
            axis = mate.get("axis") if isinstance(mate.get("axis"), Mapping) else {}
            if "origin" not in axis or "dir" not in axis:
                raise _fail(f"mate {name!r}: axis is not resolved to numbers")
            joint["origin"] = _point(axis["origin"], mate=name)
            joint["axis"] = _unit(axis["dir"], mate=name)
            rows = [("turn", "deg"), ("travel", "mm")] if kind == "cylindrical" else [
                ("turn", "deg") if kind == "revolute" else ("travel", "mm")]
            for row, unit in rows:
                dof = f"{name}.{row}" if kind == "cylindrical" else name
                joint[row] = _row(dof, kinematics)
                control, weight = drivers.get(dof, (dof, 1.0))
                handles.append({
                    "id": dof, "joint": name, "dof": row, "control": control, "weight": weight,
                    "label": dof, "unit": unit, "min": limits[dof][0], "max": limits[dof][1],
                })
        joints.append(joint)
        named.append((name, _occurrences_for_end(members, mate, "child")))

    # Ownership: an occurrence under several joints' ends goes to the one naming the fewest
    # (the deepest); equal sets take the later declaration, which keeps it deterministic.
    owner: dict[str, tuple[int, str]] = {}
    for joint_id, occurrences in named:
        for occurrence in occurrences:
            held = owner.get(occurrence)
            if held is None or len(occurrences) <= held[0]:
                owner[occurrence] = (len(occurrences), joint_id)
    carries: dict[str, list[str]] = {joint["id"]: [] for joint in joints}
    for occurrence, (_size, joint_id) in owner.items():
        carries[joint_id].append(occurrence)
    for occurrences in carries.values():
        occurrences.sort()

    opening = {control["id"]: 0.0 for control in controls}
    poses = kinematics.get("poses") if isinstance(kinematics.get("poses"), Mapping) else {}
    return {
        "schemaVersion": ARTICULATION_SCHEMA_VERSION,
        "controls": controls,
        "joints": joints,
        "carries": carries,
        "handles": handles,
        "poses": {str(name): {str(dof): float(value) for dof, value in (values or {}).items()}
                  for name, values in poses.items()},
        "opening": opening,
    }


def articulation_control_values(articulation: Mapping[str, Any], request: object) -> dict[str, float]:
    """The full control vector a request means: ``None`` is the opening, a string a named
    pose, a mapping the values it carries -- every control it does not name at its default.
    The request was validated at the door (``snapshot_cli.check_step_pose_and_clip_names``):
    an unknown pose or control is a programming error here, not a user error."""
    values = {str(control["id"]): float(control.get("default") or 0.0) for control in articulation.get("controls") or []}
    if request is None:
        return values
    if isinstance(request, str):
        preset = (articulation.get("poses") or {}).get(request.strip())
        if not isinstance(preset, Mapping):
            raise KeyError(f"articulation declares no pose {request!r}")
        request = preset
    if not isinstance(request, Mapping):
        raise TypeError(f"a control vector is a mapping or a pose name, not {type(request).__name__}")
    for control, value in request.items():
        if str(control) not in values:
            raise KeyError(f"articulation declares no control {control!r}")
        values[str(control)] = float(value)
    return values


# --- the reference evaluator ---------------------------------------------------------


def _row_value(row: Mapping[str, Any] | None, values: Mapping[str, float]) -> float:
    if not row:
        return 0.0
    return float(row.get("bias") or 0.0) + sum(
        float(weight) * float(values.get(str(control), 0.0)) for control, weight in row.get("terms") or [])


def joint_values(articulation: Mapping[str, Any], values: Mapping[str, float]) -> dict[str, dict[str, float]]:
    """Every joint's ``{"turn": degrees, "travel": units}`` at a control vector: the rows'
    dot products, nothing else."""
    return {
        str(joint["id"]): {"turn": _row_value(joint.get("turn"), values), "travel": _row_value(joint.get("travel"), values)}
        for joint in articulation.get("joints") or []
    }


def _multiply(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _motion(origin: list[float], axis: list[float], turn_deg: float, travel: float) -> list[list[float]]:
    """D(axis, q) in rest space: the turn about the axis line, then the travel along it
    (the two commute, both being about one axis)."""
    x, y, z = axis
    c = math.cos(math.radians(turn_deg))
    s = math.sin(math.radians(turn_deg))
    t = 1.0 - c
    r = [[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
         [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
         [t * x * z - s * y, t * y * z + s * x, t * z * z + c]]
    ox, oy, oz = origin
    # T(o) R T(-o) T(axis * travel): translation column = o - R o + axis * travel.
    translation = [ox - (r[0][0] * ox + r[0][1] * oy + r[0][2] * oz) + x * travel,
                   oy - (r[1][0] * ox + r[1][1] * oy + r[1][2] * oz) + y * travel,
                   oz - (r[2][0] * ox + r[2][1] * oy + r[2][2] * oz) + z * travel]
    return [[*r[0], translation[0]], [*r[1], translation[1]], [*r[2], translation[2]], [0.0, 0.0, 0.0, 1.0]]


def joint_matrices(articulation: Mapping[str, Any], values: Mapping[str, float]) -> dict[str, list[list[float]]]:
    """Every joint's world delta (row-major 4x4) at a control vector: its parent's delta
    times its own displacement. Applied as ``delta @ rest_placement`` to each occurrence
    the joint carries, this is the pose."""
    rows = joint_values(articulation, values)
    identity = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
    deltas: dict[str, list[list[float]]] = {}
    for joint in articulation.get("joints") or []:
        joint_id = str(joint["id"])
        parent = deltas.get(str(joint.get("parent") or ""), identity)
        if joint.get("kind") == "fixed" or "axis" not in joint:
            deltas[joint_id] = parent
            continue
        own = rows[joint_id]
        deltas[joint_id] = _multiply(parent, _motion(joint["origin"], joint["axis"], own["turn"], own["travel"]))
    return deltas
