"""Typed mates: the model's kinematics, declared as pure data.

The ``kinematics=`` kwarg on ``@step``/``@stl``/``@glb``/``@threemf`` takes ONE
dict whose shape mirrors the sidecar's kinematics section exactly
(design/pose-animation-split.md)::

    KINEMATICS = {
        "mates": [
            cadgen.revolute("elbow", parent="#upper_arm", child="#forearm",
                            axis="#forearm.pivot_bore", limits=(0, 150)),
        ],
        "couplings": [cadgen.couple("curl", {"mcp": 50, "pip": 70, "dip": 40})],
        "poses": {"open": {"jaw": 40}, "closed": {"jaw": 0}},
    }

    @step(out="../STEP/arm.step", kinematics=KINEMATICS)
    def arm(): ...

EVERYTHING SAYS KINEMATICS. The bake point is the dict's own ``"at"`` key —
a preset name or ``{dof: value}`` — so one argument name spans the decorator,
the doors and the snapshot flag::

    @step(out="gripper.step", kinematics={**KINEMATICS, "at": "closed"})

Semantics: AUTHORED PLACEMENT IS q=0. A mate declares the one axis its DOF
moves about (a selector ref resolved to numbers at build time, or literal
origin/direction) and measures displacement from wherever the author built the
child. There is no frame snapping and no solver — evaluation is a pure fold
over the mate tree (forward kinematics), identical in the Python exporter and
the viewer runtime. Closed loops are out of scope by design (the same call
URDF made); declaring one is an error here, not a solver invocation.

Each decorator's declaration stands alone: a mesh decorator never reads
@step's kinematics. Sharing happens in the author's source — one module-level
dict referenced from several decorators — never by cross-decorator
inheritance.

This module must import light (no OCP): it runs in the decoration-time
pre-gate window. Axis selector refs are validated as SYNTAX here and resolved
to geometry at build time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

__all__ = [
    "KINEMATICS_KEYS",
    "KinematicsDef",
    "Mate",
    "Coupling",
    "revolute",
    "slider",
    "cylindrical",
    "fastened",
    "couple",
    "normalize_kinematics",
    "kinematics_dof_ids",
]

# The closed section vocabulary of the kinematics dict. ``mates``/``couplings``/
# ``poses`` are the sidecar's kinematics block; ``at`` is authoring-only — it
# selects the BAKE point and never survives into the block, because the artifact
# as written is its own q=0. A new capability adds a key HERE and a sidecar
# schema bump, never a new sidecar file.
KINEMATICS_KEYS = ("mates", "couplings", "poses", "at")

#: The keys that make up the sidecar's kinematics block (``at`` is consumed at
#: build time and re-expressed as the baked descriptor plus ``bakedPose``).
KINEMATICS_BLOCK_KEYS = ("mates", "couplings", "poses")

_MATE_KINDS = {"revolute", "slider", "cylindrical", "fastened"}
# Sub-DOF names of a cylindrical mate: "<name>.turn" rotates, "<name>.travel"
# slides, both about/along the one declared axis.
_CYLINDRICAL_DOFS = ("turn", "travel")


def _fail(message: str) -> ValueError:
    return ValueError(f"kinematics: {message}")


def _occurrence_ref(value: object, *, label: str, mate: str) -> str:
    text = str(value or "").strip()
    if not text.startswith("#") or len(text) < 2:
        raise _fail(
            f"mate {mate!r} {label} must be an occurrence ref like '#carriage' "
            f"(a #-prefixed label), got {value!r}"
        )
    return text


def _vector3(value: object, *, label: str, mate: str) -> tuple[float, float, float]:
    if isinstance(value, (list, tuple)) and len(value) == 3:
        try:
            x, y, z = (float(v) for v in value)
        except (TypeError, ValueError):
            pass
        else:
            return (x, y, z)
    raise _fail(f"mate {mate!r} {label} must be a 3-vector of numbers, got {value!r}")


def _normalize_axis(axis: object, origin: object, direction: object, *, mate: str) -> dict[str, Any]:
    """An axis is EITHER a selector ref (resolved at build) or literal numbers.

    Ref form: ``axis="#forearm.pivot_bore"`` — a cylindrical face / circular
    edge yields its axis, a planar face its center+normal.
    Literal form: ``origin=(x, y, z), direction=(x, y, z)``.
    """
    has_ref = axis is not None
    has_literal = origin is not None or direction is not None
    if has_ref and has_literal:
        raise _fail(f"mate {mate!r} declares both axis= (a ref) and origin=/direction= literals; pick one form")
    if has_ref:
        text = str(axis).strip()
        if not text.startswith("#") or len(text) < 2:
            raise _fail(
                f"mate {mate!r} axis must be a #-prefixed selector ref "
                f"(e.g. '#forearm.pivot_bore') or literal origin=/direction=, got {axis!r}"
            )
        return {"ref": text}
    if origin is None or direction is None:
        raise _fail(f"mate {mate!r} needs an axis: either axis='#<selector>' or both origin= and direction=")
    dir_vec = _vector3(direction, label="direction", mate=mate)
    if all(abs(v) < 1e-12 for v in dir_vec):
        raise _fail(f"mate {mate!r} direction must be non-zero")
    return {"origin": list(_vector3(origin, label="origin", mate=mate)), "dir": list(dir_vec)}


def _normalize_limits(limits: object, *, mate: str, kind: str) -> dict[str, list[float]]:
    if kind == "fastened":
        if limits is not None:
            raise _fail(f"fastened mate {mate!r} takes no limits: it declares no DOF")
        return {}
    """Limits keyed by sub-DOF. Single-DOF mates take a plain ``(lo, hi)``;
    cylindrical takes ``{"turn": (lo, hi), "travel": (lo, hi)}``."""

    def pair(value: object, label: str) -> list[float]:
        if isinstance(value, (list, tuple)) and len(value) == 2:
            try:
                lo, hi = float(value[0]), float(value[1])
            except (TypeError, ValueError):
                pass
            else:
                if hi <= lo:
                    raise _fail(f"mate {mate!r} {label} limits must be (lo, hi) with hi > lo, got {value!r}")
                return [lo, hi]
        raise _fail(f"mate {mate!r} {label} limits must be a (lo, hi) pair, got {value!r}")

    if kind == "cylindrical":
        if not isinstance(limits, Mapping):
            raise _fail(
                f"cylindrical mate {mate!r} limits must be a dict over its sub-DOFs, "
                f"e.g. {{'turn': (0, 360), 'travel': (0, 40)}}"
            )
        unknown = set(limits) - set(_CYLINDRICAL_DOFS)
        if unknown:
            raise _fail(
                f"cylindrical mate {mate!r} limits has unknown sub-DOF "
                f"{sorted(unknown)}; it has exactly: {list(_CYLINDRICAL_DOFS)}"
            )
        return {dof: pair(limits[dof], dof) for dof in _CYLINDRICAL_DOFS if dof in limits}
    if limits is None:
        raise _fail(f"mate {mate!r} needs limits=(lo, hi) — sliders and exports both read the range")
    return {"value": pair(limits, "limits")}


@dataclass(frozen=True)
class Mate:
    """One typed relationship between two occurrences, ready to serialize.

    ``axis`` is either ``{"ref": "#..."}`` (resolved to numbers at build) or
    ``{"origin": [...], "dir": [...]}`` already-literal.
    """

    name: str
    kind: str
    parent: str
    child: str
    axis: dict[str, Any]
    limits: dict[str, list[float]]

    def dof_ids(self) -> tuple[str, ...]:
        if self.kind == "fastened":
            return ()
        if self.kind == "cylindrical":
            return tuple(f"{self.name}.{dof}" for dof in _CYLINDRICAL_DOFS)
        return (self.name,)


@dataclass(frozen=True)
class Coupling:
    """A virtual DOF linearly gearing real ones: pure data, never a function."""

    name: str
    gears: dict[str, float]
    limits: list[float]


def _mate_name(name: object) -> str:
    text = str(name or "").strip()
    if not text or "." in text:
        raise _fail(f"mate name must be a non-empty string without dots, got {name!r}")
    return text


def _mate(
    kind: str,
    name: object,
    *,
    parent: object,
    child: object,
    axis: object = None,
    origin: object = None,
    direction: object = None,
    limits: object = None,
    default: object = None,
) -> Mate:
    mate_name = _mate_name(name)
    if default is not None:
        # ZERO IS THE ARTIFACT: every DOF's rest value is 0 (the placement as
        # written), so a "default" slider value would displace geometry the
        # moment a panel opened — the ambiguity is designed out.
        raise _fail(
            f"mate {mate_name!r}: default= was dropped — 0 is always the "
            "artifact as written; declare a preset under poses or bake the "
            "artifact with kinematics={..., 'at': <preset>} instead"
        )
    if kind == "fastened":
        if axis is not None or origin is not None or direction is not None:
            raise _fail(f"fastened mate {mate_name!r} takes no axis: it declares no DOF")
        normalized_axis: dict[str, Any] = {}
    else:
        normalized_axis = _normalize_axis(axis, origin, direction, mate=mate_name)
    return Mate(
        name=mate_name,
        kind=kind,
        parent=_occurrence_ref(parent, label="parent", mate=mate_name),
        child=_occurrence_ref(child, label="child", mate=mate_name),
        axis=normalized_axis,
        limits=_normalize_limits(limits, mate=mate_name, kind=kind),
    )


def revolute(name, *, parent, child, axis=None, origin=None, direction=None, limits=None, default=None) -> Mate:
    """A 1-DOF rotation about the declared axis; degrees, zero = authored placement."""
    return _mate("revolute", name, parent=parent, child=child, axis=axis,
                 origin=origin, direction=direction, limits=limits, default=default)


def slider(name, *, parent, child, axis=None, origin=None, direction=None, limits=None, default=None) -> Mate:
    """A 1-DOF translation along the declared axis; model units, zero = authored placement."""
    return _mate("slider", name, parent=parent, child=child, axis=axis,
                 origin=origin, direction=direction, limits=limits, default=default)


def cylindrical(name, *, parent, child, axis=None, origin=None, direction=None, limits=None, default=None) -> Mate:
    """Rotation + translation about one axis: sub-DOFs ``<name>.turn`` and ``<name>.travel``."""
    return _mate("cylindrical", name, parent=parent, child=child, axis=axis,
                 origin=origin, direction=direction, limits=limits, default=default)


def fastened(name, *, parent, child) -> Mate:
    """A rigid 0-DOF attachment: the child rides the parent's motion. Needed
    exactly when occurrences are SIBLINGS in the instance tree (a pin that
    orbits with its carrier) — instance-tree children ride for free."""
    return _mate("fastened", name, parent=parent, child=child)


def couple(name, gears, *, limits=None) -> Coupling:
    """A virtual DOF driving real DOFs linearly: ``couple("curl", {"mcp": 50, ...})``
    means setting curl=x sets mcp to 50*x (and so on). Ratios are plain numbers —
    couplings are data, evaluated identically by both FK runtimes."""
    text = _mate_name(name)
    if not isinstance(gears, Mapping) or not gears:
        raise _fail(f"couple {text!r} gears must be a non-empty dict of {{dof: ratio}}")
    normalized: dict[str, float] = {}
    for dof, ratio in gears.items():
        try:
            normalized[str(dof)] = float(ratio)
        except (TypeError, ValueError):
            raise _fail(f"couple {text!r} ratio for {dof!r} must be a number, got {ratio!r}") from None
    if limits is None:
        bounds = [0.0, 1.0]
    else:
        if not (isinstance(limits, (list, tuple)) and len(limits) == 2 and float(limits[1]) > float(limits[0])):
            raise _fail(f"couple {text!r} limits must be a (lo, hi) pair with hi > lo, got {limits!r}")
        bounds = [float(limits[0]), float(limits[1])]
    return Coupling(name=text, gears=normalized, limits=bounds)


# The keys a plain-dict mate / coupling entry may carry. JSON has no
# constructors, so `cadgen step build --kinematics '{"mates": [{...}]}'`
# hands dicts to the SAME validator the Python constructors feed — one
# vocabulary, one set of teaching errors, no second parser to drift.
_MATE_DICT_KEYS = {"name", "kind", "parent", "child", "axis", "origin", "direction", "limits"}
_COUPLING_DICT_KEYS = {"name", "gears", "limits"}


def _mate_from_mapping(entry: Mapping[str, Any], *, where: str) -> Mate:
    unknown = set(entry) - _MATE_DICT_KEYS
    if unknown:
        raise _fail(
            f"{where} mate entry has unknown key(s) {sorted(unknown)}; a mate is "
            f"{sorted(_MATE_DICT_KEYS)}"
        )
    kind = str(entry.get("kind") or "").strip()
    if kind not in _MATE_KINDS:
        raise _fail(
            f"{where} mate {entry.get('name')!r} kind must be one of "
            f"{sorted(_MATE_KINDS)}, got {entry.get('kind')!r}"
        )
    axis = entry.get("axis")
    origin = entry.get("origin")
    direction = entry.get("direction")
    if isinstance(axis, Mapping):
        # The already-resolved literal spelling, the same shape the sidecar
        # carries: {"origin": [...], "dir": [...]}.
        origin = axis.get("origin")
        direction = axis.get("dir", axis.get("direction"))
        axis = None
    limits = entry.get("limits")
    if isinstance(limits, Mapping):
        limits = {str(key): value for key, value in limits.items()}
    return _mate(
        kind,
        entry.get("name"),
        parent=entry.get("parent"),
        child=entry.get("child"),
        axis=axis,
        origin=origin,
        direction=direction,
        limits=limits,
    )


def _coupling_from_mapping(entry: Mapping[str, Any], *, where: str) -> Coupling:
    unknown = set(entry) - _COUPLING_DICT_KEYS
    if unknown:
        raise _fail(
            f"{where} coupling entry has unknown key(s) {sorted(unknown)}; a "
            f"coupling is {sorted(_COUPLING_DICT_KEYS)}"
        )
    return couple(entry.get("name"), entry.get("gears"), limits=entry.get("limits"))


@dataclass(frozen=True)
class KinematicsDef:
    """The validated declaration, carried on a ModelDef / mesh declaration.

    ``block`` is JSON-ready except that mate axes may still be selector refs;
    the build resolves those to numbers before anything serializes. ``at`` is
    the resolved ``{dof: value}`` bake point the declaration's ``"at"`` key
    named, or ``None`` for authored rest.
    """

    block: dict[str, Any]
    at: dict[str, float] | None = None

    def dof_ids(self) -> tuple[str, ...]:
        return kinematics_dof_ids(self.block)

    def at_values(self, at: object, *, where: str) -> dict[str, float]:
        """Resolve an ``"at"`` bake point (preset name or value dict) to
        concrete DOF values, validated against this declaration."""
        return resolve_kinematics_at(self.block, at, where=where)


def resolve_kinematics_at(
    block: Mapping[str, Any], at: object, *, where: str
) -> dict[str, float]:
    """One rule for every ``at`` spelling — the decorator's ``"at"`` key, a mesh
    door's ``kinematics=``, snapshot's ``--kinematics``: a declared preset NAME
    or a ``{dof: value}`` dict, checked against the DOFs this block declares."""
    poses = block.get("poses") or {}
    if isinstance(at, str):
        if at not in poses:
            known = ", ".join(sorted(poses)) or "(none declared)"
            raise _fail(f"{where} 'at' names {at!r}, which is not a declared preset; poses: {known}")
        return dict(poses[at])
    if isinstance(at, Mapping):
        return _validated_pose_values(block, at, where=where)
    raise _fail(
        f"{where} 'at' must be a preset name or a {{dof: value}} dict, got {type(at).__name__}"
    )


def kinematics_dof_ids(block: Mapping[str, Any]) -> tuple[str, ...]:
    ids: list[str] = []
    for mate in block.get("mates", ()):
        if mate.get("kind") == "cylindrical":
            ids.extend(f"{mate['name']}.{dof}" for dof in _CYLINDRICAL_DOFS)
        elif mate.get("kind") == "fastened":
            # A rigid attachment has ZERO degrees of freedom: no slider, no
            # pose key, nothing a value could drive.
            continue
        else:
            ids.append(mate["name"])
    ids.extend(coupling["name"] for coupling in block.get("couplings", ()))
    return tuple(ids)


def _validated_pose_values(block: Mapping[str, Any], values: Mapping[str, Any], *, where: str) -> dict[str, float]:
    known = set(kinematics_dof_ids(block))
    resolved: dict[str, float] = {}
    for dof, value in values.items():
        dof_name = str(dof)
        if dof_name not in known:
            listing = ", ".join(sorted(known)) or "(none)"
            raise _fail(f"{where} names unknown DOF {dof_name!r}; declared DOFs: {listing}")
        try:
            resolved[dof_name] = float(value)
        except (TypeError, ValueError):
            raise _fail(f"{where} value for {dof_name!r} must be a number, got {value!r}") from None
    return resolved


def normalize_kinematics(value: object, *, where: str) -> KinematicsDef:
    """Validate a ``kinematics=`` dict at decoration time.

    Checks everything checkable without geometry: the closed key vocabulary,
    constructor-built mates/couplings, unique DOF names, string-level tree
    rules (one parent mate per child, no cycles — closed loops are an explicit
    deferral), coupling targets, pose presets over declared DOFs, and the
    ``"at"`` bake point against those same DOFs. Selector refs (occurrence
    labels, axis refs) resolve at build time.
    """
    if isinstance(value, KinematicsDef):
        return value
    if not isinstance(value, Mapping):
        raise _fail(f"{where} kinematics must be a dict with keys {list(KINEMATICS_KEYS)}, got {type(value).__name__}")
    if "pose" in value:
        raise _fail(
            f"{where} kinematics has no 'pose' key: pose= folded into the "
            "kinematics dict: kinematics={**K, 'at': 'closed'}"
        )
    unknown = set(value) - set(KINEMATICS_KEYS)
    if unknown:
        raise _fail(
            f"{where} kinematics has unknown key(s) {sorted(unknown)}; "
            f"the vocabulary is closed: {list(KINEMATICS_KEYS)} "
            "(choreography is the render module beside the document, never a kinematics key)"
        )

    raw_mates = value.get("mates", [])
    if not isinstance(raw_mates, (list, tuple)):
        raise _fail(f"{where} kinematics['mates'] must be a list of cadgen.revolute/slider/cylindrical(...)")
    mates: list[Mate] = []
    for entry in raw_mates:
        if isinstance(entry, Mate):
            mates.append(entry)
            continue
        if isinstance(entry, Mapping):
            # The JSON spelling (`cadgen step build --kinematics '{...}'`):
            # same closed vocabulary, same validator, so the two authoring
            # surfaces cannot drift.
            mates.append(_mate_from_mapping(entry, where=where))
            continue
        raise _fail(
            f"{where} kinematics['mates'] entries must be built by "
            f"cadgen.revolute/slider/cylindrical(...) or be plain dicts with "
            f"{sorted(_MATE_DICT_KEYS)}, got {type(entry).__name__}"
        )

    raw_couplings = value.get("couplings", [])
    if not isinstance(raw_couplings, (list, tuple)):
        raise _fail(f"{where} kinematics['couplings'] must be a list of cadgen.couple(...)")
    couplings: list[Coupling] = []
    for entry in raw_couplings:
        if isinstance(entry, Coupling):
            couplings.append(entry)
            continue
        if isinstance(entry, Mapping):
            couplings.append(_coupling_from_mapping(entry, where=where))
            continue
        raise _fail(
            f"{where} kinematics['couplings'] entries must be built by "
            f"cadgen.couple(...) or be plain dicts with {sorted(_COUPLING_DICT_KEYS)}, "
            f"got {type(entry).__name__}"
        )

    raw_poses = value.get("poses", {})
    if not isinstance(raw_poses, Mapping):
        raise _fail(f"{where} kinematics['poses'] must be a dict of {{name: {{dof: value}}}}")

    if not mates and not couplings:
        raise _fail(f"{where} kinematics declares no mates; drop the kwarg or declare at least one mate")

    # Unique DOF names across mates and couplings.
    seen: set[str] = set()
    for mate in mates:
        if mate.name in seen:
            raise _fail(f"{where} duplicate mate/DOF name {mate.name!r}")
        seen.add(mate.name)
    for coupling in couplings:
        if coupling.name in seen:
            raise _fail(f"{where} coupling {coupling.name!r} collides with a mate name")
        seen.add(coupling.name)

    # String-level tree rules over the declared occurrence refs.
    parent_of: dict[str, str] = {}
    for mate in mates:
        if mate.child == mate.parent:
            raise _fail(f"{where} mate {mate.name!r} mates {mate.child!r} to itself")
        if mate.child in parent_of:
            raise _fail(
                f"{where} occurrence {mate.child!r} has more than one parent mate; "
                "the mate graph is a tree (closed loops are deliberately out of "
                "scope — they need a solver, and cadgen evaluates pure FK)"
            )
        parent_of[mate.child] = mate.parent
    for start in parent_of:
        node, hops = start, 0
        while node in parent_of:
            node = parent_of[node]
            hops += 1
            if node == start or hops > len(parent_of):
                raise _fail(
                    f"{where} the mate graph has a cycle through {start!r}; "
                    "closed-loop linkages are deliberately out of scope (FK tree only)"
                )

    # Couplings gear REAL mate DOFs (not other couplings — no chaining).
    mate_dofs = {dof for mate in mates for dof in mate.dof_ids()}
    for coupling in couplings:
        for dof in coupling.gears:
            if dof not in mate_dofs:
                listing = ", ".join(sorted(mate_dofs)) or "(none)"
                raise _fail(
                    f"{where} couple {coupling.name!r} gears unknown DOF {dof!r}; "
                    f"mate DOFs: {listing}"
                )

    block: dict[str, Any] = {
        "mates": [
            {
                "name": mate.name,
                "kind": mate.kind,
                "parent": mate.parent,
                "child": mate.child,
                "axis": dict(mate.axis),
                "limits": {k: list(v) for k, v in mate.limits.items()},
            }
            for mate in mates
        ],
    }
    if couplings:
        block["couplings"] = [
            {"name": c.name, "gears": dict(c.gears), "limits": list(c.limits)} for c in couplings
        ]
    if raw_poses:
        block["poses"] = {
            str(name): _validated_pose_values(block, values, where=f"{where} poses[{name!r}]")
            for name, values in raw_poses.items()
        }
    # ``at`` is the BAKE point. It lives inside the one kinematics space rather
    # than beside it, so a declaration is a single object at every surface.
    raw_at = value.get("at")
    at = None if raw_at is None else resolve_kinematics_at(block, raw_at, where=f"{where} kinematics")
    return KinematicsDef(block=block, at=at)
