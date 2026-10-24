"""Kinematics: an assembly's mechanism, as the document holds it, and its poses.

Authoring is build123d's joints and nothing else. A model puts ``RevoluteJoint``,
``LinearJoint``, ``CylindricalJoint``, ``BallJoint`` and ``RigidJoint`` on its parts and
places them with ``connect_to(..., angle=, position=, angles=)``; the values it connects
them at are the **as-built state**. ``mechanism_state(assembly, name, **values)`` names
another one (AP242's ``mechanism_state_representation``). At document time the engine
harvests every joint on every part of the result (``harvest``) and pairs them two ways: by
``connect_to``, where the author used it; and, for every joint no ``connect_to`` joined, by
label -- a moving joint and a ``RigidJoint`` of the same label on another part are a pair (the nearest in the tree, a tie refused), and so are two
rigid joints of one label each the other's nearest. ``connect_to`` wins: a joint it joined is
never matched by label. build123d's ``connect_to`` composes locations in each part's own
compound, so in a nested assembly it cannot place a part; there a model authors both joints
where the parts stand and lets the label pair them. Either way the document places nothing:
every value, the as-built one included, is computed from where the two frames stand in the
built tree. The pairs make a mechanism in ISO 10303-105's terms, the kinematics of STEP AP242:

- **Links** are sets of occurrences moving as one rigid body: two parts whose rigid joints
  are connected are one link. The **ground** link is every link no ``connect_to`` moved
  (the joint whose ``connect_to`` was called stays put; the other's part moves), with every
  part placed by no joint; a part below a jointed sub-assembly moves with it, the one
  holding an inner pair's moving joint (its base) too (``_enclose``).
- **Pairs** join two links: a revolute joint is a ``REVOLUTE_PAIR``, a linear one a
  ``PRISMATIC_PAIR``, a cylindrical one a ``CYLINDRICAL_PAIR``, a ball a ``SPHERICAL_PAIR``,
  each ``_WITH_RANGE`` where the joint has finite limits. A pair is named by its moving
  joint's label (a label two pairs share is qualified with the path of the part that holds
  it: ``hand/left:knuckle``). Its two frames (``transform_item_1`` on link 1, the part
  holding the moving joint, ``transform_item_2`` on link 2, the part holding the rigid
  one) are AXIS2_PLACEMENT_3Ds in their links' frames, and coincide at value 0. Link 2's
  placement at value ``v`` is ``link_1 * item_1 * M(v) * item_2^-1``, with ``M`` a turn
  about Z (revolute), a slide along Z (prismatic), both (cylindrical: angle, then
  distance) or build123d's intrinsic X-Y-Z rotation (spherical: three angles). Angles are
  degrees, distances millimetres.
- A **coupling** is a constraint, never a control, made by the function named after the pair
  it is written as: ``gear_pair(assembly, name, **joints)`` (revolute joints),
  ``rack_and_pinion_pair(...)`` (a revolute joint and prismatic ones, or a prismatic joint and
  revolute ones) or ``screw_pair(assembly, name, joint=pitch)`` (one cylindrical joint, its
  value the turn); a joint of another kind is refused at document time (``_fits``). Its joints
  move together, each by its ratio, and only through it. Its value ``c`` is the
  displacement that puts each joint at its as-built value plus its ratio times ``c`` (a pair of
  several values takes a ratio per value), so ``c = 0`` is as built and a coupling never moves
  the build; its range is derived, never given: the tightest interval in which every joint
  stays within its own limits (a joint with no limits bounds nothing). Its name poses wherever a
  joint's does -- mechanism states, configuration sequences and ``--pose`` -- which resolve it
  to pair values at document time; a pose setting one of its joints alone is refused. In the
  document a coupling is the standard's coupler: AP242 edition 4's
  ``KinematicPairWithMotionCoupling`` between pairs, of kind ``gear_pair`` (two revolute rotations) or ``rack_and_pinion_pair`` (a
  revolute rotation and a prismatic translation), each holding ``s1 * d1 + s2 * d2 = 0`` over
  the two values' displacements from the as-built state (``s1 = r2``, ``s2 = -r1``, so the
  ratios read back as written); and Part 105's ``SCREW_PAIR`` (``pitch``, travel per 360
  degrees of turn) for one cylindrical pair's turn and travel. A coupling of more than two values is a chain of them from its first-named
  value. No coupling drives a spherical pair (no coupler relates its three angles), and a
  joint takes at most one coupling.

A link's frame is its first member occurrence's placement as built (the ground's, the
world's when it has none). A pair the built tree contradicts -- its two joints on one rigid
link, or its rigid joint's frame not one motion of the pair from its moving joint's -- is
refused at document time, by name. A loop's pairs are kept and not posed (no solver), and a
non-linear relation (a function coupling, a cam) is no part of the mechanism: a configuration
sequence says it.

**Configuration sequences** (``configuration_sequence(assembly, name, ...)``, AP242's
``interpolated_configuration_sequence``; the structure and the viewer call them motions) are
definitions, kept beside the mechanism states: waypoints -- each a time and a mechanism state's
name or joint values, the rest as built -- and an
ease between them, AP242's ``interpolation`` on each segment: ``linear``
(``linear_interpolation_type``, constant speed) or ``cubic``
(``synchronous_interpolation_type``: each step eased in and out, every pair arriving together),
the last segment ``discontinuous_interpolation_type``: a sequence is a finite clip, and a player
repeats it. A sweep is two waypoints. A function of time is stored as its samples, linear, at
times chosen until the samples' linear interpolation stays within the tolerance of the function
at every check point between them: 1e-3 radian for an angle, 1e-3 of the model's size (its
bounding box's diagonal, from the B-rep's geometry) for a distance. So the document holds poses
and sequence definitions, never baked frames or clips; a GLB export bakes each into a clip
(``export/motion.py``) from the same nodes.

In the document the mechanism is a subtree under ``Main():100``, marked by a
``TDataStd_UAttribute`` of ``GUID`` and read by that GUID, of standard attributes only
(``TDataStd_Name``, ``TDataStd_NamedData`` for an entity's AP242 name and attributes,
``TDataStd_ReferenceList``, ``TDataStd_RealArray``, ``TDataStd_IntegerArray``,
``XCAFDoc_AssemblyItemRef`` for an occurrence). Every entity and attribute in it is AP242's (Part
21's, or edition 4's domain model's where Part 21 has none); the root's three container
attributes say the schema and the units; cadgen stores no kinematic fact the standard cannot
name (``test_kinematics``' conformance test holds it):

    0:1:100 "Kinematics"       UAttribute(GUID), NamedData{schema, angle_unit, length_unit}
      :1 <name>                NamedData{entity: MECHANISM_REPRESENTATION}, ReferenceList[ground link]
        :1 "links"
          :k <name>            NamedData{entity: KINEMATIC_LINK}
            :i                 AssemblyItemRef(occurrence: its component labels from the root)
        :2 "pairs"
          :j <label>           NamedData{entity, transform_item_1[9], transform_item_2[9],
                                         lower_/upper_limit_...}, ReferenceList[link 1, link 2]
        :3 "as built"          NamedData{entity: MECHANISM_STATE_REPRESENTATION},
                               ReferenceList[pair per value], RealArray[values], IntegerArray[dof per value]
        :4 "configurations"
          :s <name>            as "as built"
        :5 "motions"
          :m <name>            NamedData{entity: INTERPOLATED_CONFIGURATION_SEQUENCE}
            :k                 NamedData{entity: INTERPOLATED_CONFIGURATION_SEGMENT, t_parameter, interpolation},
                               and its state: ReferenceList[the configuration it names], or as "as built"
        :6 "couplings"
          :c <name>            the coupling
            :k                 NamedData{entity: KinematicPairWithMotionCoupling, Kind,
                                         CouplingRatios[2], CouplingTypes}, ReferenceList[pair, pair]
                               | NamedData{entity: SCREW_PAIR, pitch}, ReferenceList[the cylindrical pair]

STEP carries none of it: OCCT parses AP242 kinematics into its STEP model and maps none into a
document, and cadgen's OCP reaches neither.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

__all__ = ["CONFIGURATIONS", "COUPLINGS", "GUID", "MOTIONS", "Coupling", "KinematicsError", "Link", "LinkWorlds", "Mechanism",
           "Motion", "Pair", "Timeline", "block", "configuration_sequence", "gear_pair", "harvest", "mechanism_state",
           "posed", "posed_structure", "rack_and_pinion_pair", "read", "resolve", "screw_pair", "write"]

GUID = "5b0e7a64-3c1d-4f8e-a2b9-6d4c1e7f9a20"
TAG = 100  # Main():100, clear of XCAFDoc_DocumentTool's tool labels (1..10)
SCHEMA = "cadgen.kinematics/2"
# The attribute ``mechanism_state`` keeps a shape's named states in, ``configuration_sequence`` its
# sequences and ``gear_pair``, ``rack_and_pinion_pair`` and ``screw_pair`` its couplings (each its kind
# and its ratios).
CONFIGURATIONS = "xbf_configurations"
MOTIONS = "xbf_motions"
COUPLINGS = "xbf_couplings"
# A motion's ease, as AP242's segment ``interpolation``; the last segment's says the clip ends.
INTERPOLATIONS = {"linear": "linear_interpolation_type", "cubic": "synchronous_interpolation_type"}
EASES = tuple(INTERPOLATIONS)
_EASE_OF = {entity: ease for ease, entity in INTERPOLATIONS.items()}
LAST_INTERPOLATION = "discontinuous_interpolation_type"
# A coupling's couplers: edition 4's coupler between two pairs' values, and Part 105's screw.
COUPLER = "KinematicPairWithMotionCoupling"
SCREW = "SCREW_PAIR"
# How near a motion's stored samples (a function's) and a GLB's baked curves keep to the truth:
# an angle within ANGULAR_TOLERANCE radians, a distance within LINEAR_TOLERANCE of the size.
ANGULAR_TOLERANCE = 1e-3
LINEAR_TOLERANCE = 1e-3
# At most this many samples of a function, or keys of a baked clip.
MOST_KEYS = 4097

ROTATION = ("deg", "lower_limit_actual_rotation", "upper_limit_actual_rotation")
TRANSLATION = ("mm", "lower_limit_actual_translation", "upper_limit_actual_translation")
# A pair's kind: its AP242 entity and its values, each with its unit and limit names.
KINDS: dict[str, tuple[str, tuple]] = {
    "revolute": ("REVOLUTE_PAIR", (ROTATION,)),
    "prismatic": ("PRISMATIC_PAIR", (TRANSLATION,)),
    "cylindrical": ("CYLINDRICAL_PAIR", (ROTATION, TRANSLATION)),
    "spherical": ("SPHERICAL_PAIR", (("deg", "lower_limit_roll", "upper_limit_roll"),
                                     ("deg", "lower_limit_pitch", "upper_limit_pitch"),
                                     ("deg", "lower_limit_yaw", "upper_limit_yaw"))),
}
_BY_ENTITY = {entity: kind for kind, (entity, _dofs) in KINDS.items()}
_STRING_KEYS = ("schema", "angle_unit", "length_unit", "entity")


class KinematicsError(ValueError):
    """A mechanism the engine will not keep or pose, said by name."""


@dataclass
class Link:
    name: str
    members: list[tuple[int, ...]]  # occurrences, as component indices from the root


@dataclass
class Pair:
    label: str
    kind: str
    links: tuple[int, int]
    frames: tuple[tuple[float, ...], tuple[float, ...]] | None  # two AXIS2_PLACEMENT_3Ds: origin, Z, X
    limits: tuple[tuple[float | None, float | None], ...]

    @property
    def dofs(self) -> int:
        return len(KINDS[self.kind][1])


@dataclass
class Motion:
    """A motion's definition: its keys, each a time (seconds, the first 0, increasing) and a
    configuration's name or pair values (by pair label, the rest as built), and the ease
    between them (``linear`` or ``cubic``)."""

    name: str
    keys: list[tuple[float, str | None, dict[str, tuple[float, ...]]]]
    ease: str = "cubic"

    @property
    def duration(self) -> float:
        return self.keys[-1][0]

    def labels(self) -> set[str]:
        return {label for _t, _name, values in self.keys for label in values}

    def signature(self) -> tuple:
        return (self.name, tuple((t, name, tuple(sorted(values.items()))) for t, name, values in self.keys),
                self.ease)


@dataclass
class Coupling:
    """A constraint among pairs: at value ``c`` each pair it names stands at its as-built
    values plus ``ratios[pair]`` (one per value of the pair) times ``c``, its first-named pair
    first; its joints move only through it. Its range is derived from its joints' limits
    (``_derived_range``)."""

    name: str
    ratios: dict[str, tuple[float, ...]]

    def signature(self) -> tuple:
        return (self.name, tuple(self.ratios.items()))


@dataclass
class Mechanism:
    name: str
    links: list[Link]
    ground: int
    pairs: list[Pair]
    as_built: dict[str, tuple[float, ...]]
    configurations: dict[str, dict[str, tuple[float, ...]]] = field(default_factory=dict)
    # What the harvest left out, each said by name: the build's report, never the document.
    warnings: list[str] = field(default_factory=list)
    motions: dict[str, Motion] = field(default_factory=dict)
    couplings: dict[str, Coupling] = field(default_factory=dict)

    def signature(self) -> tuple:
        return (self.name, tuple((link.name, tuple(link.members)) for link in self.links), self.ground,
                tuple((p.label, p.kind, p.links, p.frames, p.limits) for p in self.pairs),
                tuple(sorted(self.as_built.items())),
                tuple((name, tuple(sorted(values.items()))) for name, values in sorted(self.configurations.items())),
                tuple(self.warnings), tuple(motion.signature() for _name, motion in sorted(self.motions.items())),
                tuple(coupling.signature() for _name, coupling in sorted(self.couplings.items())))


# --- matrices ------------------------------------------------------------------------------


def _numpy(location: Any) -> np.ndarray:
    """A TopLoc_Location, a gp_Trsf or a build123d Location as a 4x4 matrix."""
    if hasattr(location, "wrapped"):
        location = location.wrapped
    trsf = location.Transformation() if hasattr(location, "Transformation") else location
    found = np.eye(4)
    for row in range(3):
        for column in range(4):
            found[row, column] = trsf.Value(row + 1, column + 1)
    return found


def _ax2(matrix: np.ndarray) -> tuple[float, ...]:
    """An AXIS2_PLACEMENT_3D of a rigid placement: location, axis (Z), ref_direction (X)."""
    return tuple(float(value) for value in (*matrix[:3, 3], *matrix[:3, 2], *matrix[:3, 0]))


def frame_matrix(ax2: tuple[float, ...] | list[float]) -> np.ndarray:
    """The placement an AXIS2_PLACEMENT_3D stands for, as AP242 builds it: Z its axis, X its
    ref_direction made normal to Z, Y their cross product."""
    origin, z, x = np.array(ax2[0:3], float), np.array(ax2[3:6], float), np.array(ax2[6:9], float)
    z = z / np.linalg.norm(z)
    x = x - np.dot(x, z) * z
    x = x / np.linalg.norm(x)
    found = np.eye(4)
    found[:3, 0], found[:3, 1], found[:3, 2], found[:3, 3] = x, np.cross(z, x), z, origin
    return found


def _rotation(axis: int, degrees: float) -> np.ndarray:
    angle = math.radians(degrees)
    c, s = math.cos(angle), math.sin(angle)
    found = np.eye(4)
    i, j = [(1, 2), (2, 0), (0, 1)][axis]
    found[i, i], found[i, j], found[j, i], found[j, j] = c, -s, s, c
    return found


def pair_motion(kind: str, values: tuple[float, ...] | list[float]) -> np.ndarray:
    """``M(v)``: what a pair's value does between its two frames."""
    if kind == "revolute":
        return _rotation(2, values[0])
    if kind == "prismatic":
        found = np.eye(4)
        found[2, 3] = values[0]
        return found
    if kind == "cylindrical":
        found = _rotation(2, values[0])
        found[2, 3] = values[1]
        return found
    if kind == "spherical":
        return _rotation(0, values[0]) @ _rotation(1, values[1]) @ _rotation(2, values[2])
    raise KinematicsError(f"a {kind} pair has no value")


def _column(matrix: np.ndarray) -> list[float]:
    return [float(value) for value in matrix.T.ravel()]


def _from_column(values: list[float]) -> np.ndarray:
    return np.array(values, dtype=float).reshape(4, 4).T


# --- authoring ---------------------------------------------------------------------------


def _number_values(values: Any) -> tuple[float, ...] | None:
    if isinstance(values, bool):
        return None
    if isinstance(values, (int, float)):
        return (float(values),)
    try:
        found = tuple(values)
    except TypeError:
        return None
    if not found or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in found):
        return None
    return tuple(float(value) for value in found)


def mechanism_state(assembly: Any, name: str, **values: Any) -> Any:
    """A named state of ``assembly``'s mechanism, AP242's ``mechanism_state_representation``: a
    value for each joint it names, by the joint's label -- a number, or for a joint of several
    values a sequence of them (a cylindrical joint's angle and position, a ball joint's three
    angles). A joint it does not name stays as built. Kept in the document beside the as-built
    state, offered by the viewer as a preset and by ``--pose NAME``. A label names the joint in
    each placement of a sub-assembly placed several times. Returns ``assembly``."""
    import build123d as bd

    if not isinstance(assembly, bd.Shape):
        raise TypeError(f"mechanism_state() takes the assembly whose joints it sets, not {type(assembly).__name__}")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("a mechanism state's name is a non-empty string")
    checked = {}
    for label, value in values.items():
        found = _number_values(value)
        if found is None or not all(math.isfinite(v) for v in found):
            raise TypeError(f"mechanism state {name!r}: joint {label!r} takes a number, or a sequence of numbers "
                            f"for a joint of several values, not {value!r}")
        checked[label] = found
    if not checked:
        raise ValueError(f"mechanism state {name!r} sets no joint")
    held = dict(assembly.__dict__.get(CONFIGURATIONS) or {})
    held[name] = checked
    assembly.__dict__[CONFIGURATIONS] = held
    return assembly


# A coupling's kind, as the function that makes it is named: the AP242 pair it is written as.
GEAR_KIND = "gear_pair"
RACK_KIND = "rack_and_pinion_pair"
SCREW_KIND = "screw_pair"
_KIND_NAMES = {GEAR_KIND: "gear pair", RACK_KIND: "rack and pinion pair", SCREW_KIND: "screw pair"}


def _coupling(kind: str, assembly: Any, name: str, joints: dict[str, Any]) -> Any:
    """``gear_pair``, ``rack_and_pinion_pair`` and ``screw_pair``: what the three check alike, and
    the coupling kept on ``assembly`` with its kind, as each joint's ratios (a screw's pitch made
    its turn's 1 and its travel's ``pitch / 360``). The joints' kinds are checked at document
    time, where the labels are pairs (``_fits``)."""
    import build123d as bd

    if not isinstance(assembly, bd.Shape):
        raise TypeError(f"{kind}() takes the assembly whose joints it drives, not {type(assembly).__name__}")
    what = _KIND_NAMES[kind]
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"a {what}'s name is a non-empty string")
    where = f"{what} {name!r}"
    ratios = {}
    for label, value in joints.items():
        found = _number_values(value)
        if found is None or len(found) != 1 or not math.isfinite(found[0]):
            taken = "its pitch, the millimetres it travels per turn" if kind == SCREW_KIND else "a ratio"
            raise TypeError(f"{where}: joint {label!r} takes {taken}, a number, not {value!r}")
        if not found[0]:
            raise ValueError(f"{where}: joint {label!r} has {'a pitch' if kind == SCREW_KIND else 'no ratio but'} 0, "
                             "which no constraint relates")
        ratios[label] = (1.0, found[0] / 360.0) if kind == SCREW_KIND else found
    if not ratios:
        raise ValueError(f"{where} drives no joint")
    if kind == SCREW_KIND and len(ratios) != 1:
        raise TypeError(f"{where} drives one cylindrical joint, not {', '.join(map(repr, ratios))}")
    if kind != SCREW_KIND and len(ratios) < 2:
        raise ValueError(f"{where} drives {next(iter(ratios))!r} alone; it relates two joints or more")
    held = dict(assembly.__dict__.get(COUPLINGS) or {})
    held[name] = (kind, ratios)
    assembly.__dict__[COUPLINGS] = held
    return assembly


def gear_pair(assembly: Any, name: str, **joints: Any) -> Any:
    """A gear train of ``assembly``'s mechanism, ``name``: revolute joints, by label, each turning
    by its ratio (degrees per unit of the coupling's value) and only through it -- written as
    AP242's ``gear_pair`` couplers, from the first-named joint to each other one. At value ``c``
    each joint stands at its as-built angle plus its ratio times ``c``: ``c = 0`` is as built, so
    it never moves the build. Its range is its joints' limits: the tightest interval in which each
    stays within its own. Its name poses wherever a joint's does: ``mechanism_state(..., drive=90)``,
    a configuration sequence's waypoints and sweeps, and ``--pose``; its joints alone are not posed.
    A joint that is not revolute is refused when the document is made; a label names the joint
    in each placement of a sub-assembly placed several times. Returns ``assembly``."""
    return _coupling(GEAR_KIND, assembly, name, joints)


def rack_and_pinion_pair(assembly: Any, name: str, **joints: Any) -> Any:
    """A rack and pinion of ``assembly``'s mechanism, ``name``: the first-named joint, by label,
    on one side -- a revolute joint (the pinion) or a prismatic one (the rack) -- and every other
    joint of the other kind, each moving by its ratio (degrees or millimetres per unit of the
    coupling's value) and only through it; written as AP242's ``rack_and_pinion_pair`` couplers,
    from the first-named joint to each other one. Its value, range and naming are a gear pair's
    (``gear_pair``). A joint of the wrong kind is refused when the document is made. Returns
    ``assembly``."""
    return _coupling(RACK_KIND, assembly, name, joints)


def screw_pair(assembly: Any, name: str, **joints: Any) -> Any:
    """A screw of ``assembly``'s mechanism, ``name``: one cylindrical joint, by label, given its
    pitch, ``lead=1.5`` (the millimetres it travels per 360 degrees of turn, negative for a left
    hand) -- Part 105's ``SCREW_PAIR``, which holds the pitch and nothing else. The coupling's value
    is the joint's turn from as built, in degrees; its travel follows. Its range and naming are a
    gear pair's (``gear_pair``). A joint that is not cylindrical is refused when the document is
    made. Returns ``assembly``."""
    return _coupling(SCREW_KIND, assembly, name, joints)


def configuration_sequence(assembly: Any, name: str, waypoints_or_fn: Any = None, *, sweep: Any = None,
                           duration: Any = None, ease: str = "cubic", **removed: Any) -> Any:
    """A named configuration sequence of ``assembly``'s mechanism, AP242's
    ``interpolated_configuration_sequence``, one of:

    - waypoints, ``[(t, pose), ...]``: ``t`` in seconds (the first 0, then increasing), ``pose``
      a mechanism state's name or ``{joint: value}`` (the rest as built); the duration is the
      last waypoint's time;
    - ``sweep={joint: (from, to)}`` with ``duration``: the two waypoints ``(0, from)`` and
      ``(duration, to)``;
    - a function of time, ``t -> {joint: value}``, with ``duration``: stored as its samples
      (see the module docstring); ``ease`` does not apply, the function is its own timing.

    ``ease`` is ``cubic`` (each step eased in and out, resting at every waypoint: AP242's
    ``synchronous_interpolation_type``) or ``linear`` (constant speed:
    ``linear_interpolation_type``). A sequence is a finite clip; a player repeats it. Kept in the
    document beside the mechanism states, as a definition; a GLB export bakes it into a clip of
    the same name. Returns ``assembly``."""
    import build123d as bd

    if not isinstance(assembly, bd.Shape):
        raise TypeError(f"configuration_sequence() takes the assembly whose joints it moves, not "
                        f"{type(assembly).__name__}")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("a configuration sequence's name is a non-empty string")
    where = f"configuration sequence {name!r}"
    if "loop" in removed:
        raise TypeError(f"{where}: loop= is gone: a configuration sequence is a finite clip, and a player repeats it")
    if removed:
        raise TypeError(f"configuration_sequence() takes no {', '.join(sorted(removed))}")
    if ease == "spline":
        raise ValueError(f"{where}: ease 'spline' is gone: AP242 interpolates a configuration sequence linearly "
                         "or synchronously, ease 'linear' or 'cubic'")
    if ease not in EASES:
        raise ValueError(f"{where}: ease is one of {', '.join(EASES)}, not {ease!r}")
    if (waypoints_or_fn is None) == (sweep is None):
        raise TypeError(f"{where} takes waypoints, a function of time, or sweep=: one of them")

    def seconds(value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{where}: duration is a number of seconds above 0, not {value!r}")
        return float(value)

    def joints(values: Any, at: str) -> dict[str, tuple[float, ...]]:
        if not isinstance(values, dict) or not values:
            raise TypeError(f"{where}: {at} is a mechanism state's name or a dict of joint values, not {values!r}")
        found = {}
        for label, value in values.items():
            numbers = _number_values(value)
            if not isinstance(label, str) or numbers is None or not all(math.isfinite(v) for v in numbers):
                raise TypeError(f"{where}: {at}: joint {label!r} takes a number, or a sequence of numbers for a "
                                f"joint of several values, not {value!r}")
            found[label] = numbers
        return found

    if callable(waypoints_or_fn):
        if duration is None:
            raise TypeError(f"{where}: a function of time takes duration=")
        held: Any = ("function", waypoints_or_fn, seconds(duration))
    elif sweep is not None:
        if duration is None:
            raise TypeError(f"{where}: sweep= takes duration=")
        if not isinstance(sweep, dict) or not sweep:
            raise TypeError(f"{where}: sweep is {{joint: (from, to)}}, not {sweep!r}")
        ends: list[dict[str, Any]] = [{}, {}]
        for label, span in sweep.items():
            if not isinstance(span, (tuple, list)) or len(span) != 2:
                raise TypeError(f"{where}: sweep joint {label!r} takes (from, to), not {span!r}")
            ends[0][label], ends[1][label] = span
        held = ("keys", [(0.0, None, joints(ends[0], "the sweep's start")),
                         (seconds(duration), None, joints(ends[1], "the sweep's end"))])
    else:
        if duration is not None:
            raise TypeError(f"{where}: waypoints give their own times; duration= is a sweep's or a function's")
        try:
            rows = list(waypoints_or_fn)
        except TypeError:
            raise TypeError(f"{where}: waypoints are [(t, pose), ...], not {waypoints_or_fn!r}") from None
        if len(rows) < 2:
            raise ValueError(f"{where} takes at least two waypoints")
        keys = []
        for at, row in enumerate(rows):
            if not isinstance(row, (tuple, list)) or len(row) != 2:
                raise TypeError(f"{where}: waypoint {at} is (t, pose), not {row!r}")
            t, pose = row
            if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t):
                raise TypeError(f"{where}: waypoint {at}'s time is a number of seconds, not {t!r}")
            if at == 0 and t != 0:
                raise ValueError(f"{where}: the first waypoint is at 0 s, not {t!r}")
            if at and t <= keys[-1][0]:
                raise ValueError(f"{where}: waypoint {at} at {t!r} s is not after the one before it")
            if isinstance(pose, str):
                keys.append((float(t), pose, {}))
            else:
                keys.append((float(t), None, joints(pose, f"waypoint {at}")))
        held = ("keys", keys)
    motions = dict(assembly.__dict__.get(MOTIONS) or {})
    motions[name] = (*held, ease)
    assembly.__dict__[MOTIONS] = motions
    return assembly


# --- harvest -----------------------------------------------------------------------------


def posed(assembly: Any, state: Any) -> Any:
    """A copy of ``assembly`` with every part where ``state`` puts it: a mechanism state's name, or
    ``{joint label or coupling name: value}`` (the values ``mechanism_state`` takes, the rest as
    built). The parts move by the forward kinematics the viewer and the snapshot use
    (``link_worlds``): each link's placement at the asked values over its placement as built,
    applied to that link's parts. The copy shares the geometry, and keeps the joints, couplings,
    mechanism states and configuration sequences, the asked values its as-built state. An unknown
    state, joint or coupling, or a value out of range, is refused by name (``resolve``). A posed
    file is this, a function in the model's code: ``return posed(arm().shape, "folded")``."""
    from collections.abc import Mapping

    import build123d as bd
    from build123d.topology.shape_core import _make_topods_compound_from_shapes, downcast
    from OCP.gp import gp_Trsf
    from OCP.TopAbs import TopAbs_COMPOUND
    from OCP.TopLoc import TopLoc_Location

    from cadgen.engine import document
    from cadgen.engine.model import instance

    if not isinstance(assembly, bd.Shape):
        hint = ": a model call returns its document, whose .shape is the assembly" if hasattr(assembly, "shape") else ""
        raise TypeError(f"posed() takes the assembly whose joints it sets, not {type(assembly).__name__}{hint}")
    if isinstance(state, Mapping):
        pose: Any = dict(state)
    elif isinstance(state, str):
        pose = state
    else:
        raise TypeError("posed() takes a mechanism state's name or a mapping of joint labels to values, "
                        f"not {type(state).__name__}")
    made = instance(assembly)
    tree = document.collect(made, made.__dict__.get("label") or "posed")
    children = made.__dict__.get("_NodeMixin__children") or ()
    whole = (children and int(made.wrapped.ShapeType()) == int(TopAbs_COMPOUND)
             and len(document._children(made.wrapped)) == len(children))
    root_path = () if whole and made.wrapped.Location().IsIdentity() else (0,)
    kinematics = None if tree.mechanism is None else block(
        tree.mechanism, [], lambda at: _column(_numpy(_occurrence(tree, at)[0])))
    values, _named = resolve(kinematics, pose)
    if kinematics is None:
        return made
    now = link_worlds(kinematics, values)
    then = link_worlds(kinematics, {label: _as_tuple(value) for label, value in kinematics["asBuilt"].items()})
    moved = {tuple(path): now[at] @ np.linalg.inv(then[at])
             for at, link in enumerate(tree.mechanism.links) for path in link.members}

    def located(matrix: np.ndarray) -> Any:
        trsf = gp_Trsf()
        trsf.SetValues(*(float(matrix[row, column]) for row in range(3) for column in range(4)))
        return TopLoc_Location(trsf)

    # Every node from the root down: where it stood, where it stands now, its place in its parent.
    objects = sorted(_objects(made, root_path), key=lambda item: len(item[1]))
    built = {path: _numpy(_occurrence(tree, path)[0]) if path else np.eye(4) for _obj, path in objects}
    worlds: dict[tuple[int, ...], np.ndarray] = {}
    changed: set[tuple[int, ...]] = set()
    for obj, path in objects:
        above = path[:-1] if path != root_path else None
        parent_then = built[above] if above is not None else np.eye(4)
        parent_now = worlds[above] if above is not None else np.eye(4)
        local = np.linalg.inv(parent_then) @ built[path]
        if path in moved:
            worlds[path] = moved[path] @ built[path]
            local_now = np.linalg.inv(parent_now) @ worlds[path]
        else:
            local_now = local
            worlds[path] = parent_now @ local
        if not np.allclose(local_now, local, rtol=0, atol=1e-12):
            obj.__dict__["_wrapped"] = downcast(obj.wrapped.Located(located(local_now)))
            changed.add(path)
    # Each compound holding a moved node is made again around its children, where it stood.
    for obj, path in reversed(objects):
        held = obj.__dict__.get("_NodeMixin__children") or ()
        if held and any(path + (at,) in changed for at in range(len(held))):
            own = obj.wrapped
            compound = _make_topods_compound_from_shapes([child.wrapped for child in held]).Located(own.Location())
            compound.Orientation(own.Orientation())
            obj.__dict__["_wrapped"] = downcast(compound)
            changed.add(path)
    # The joints say the values they now stand at, as ``connect_to`` would have left them.
    naming = {path: "/".join(_occurrence(tree, path)[1]) for _obj, path in objects}
    for obj, path in objects:
        for joint in (obj.__dict__.get("joints") or {}).values():
            kind = _joint_kind(joint)
            label = next((key for key in (joint.label, f"{naming[path]}:{joint.label}") if key in values), None)
            if label is None or kind in (None, "rigid", "spherical"):
                continue
            value = values[label]
            if kind == "revolute":
                joint._angle = value[0]
            elif kind == "prismatic":
                joint.position = value[0]
            else:
                joint.angle, joint.position = value
    return made


def _objects(result: Any, root_path: tuple[int, ...]) -> list[tuple[Any, tuple[int, ...]]]:
    """Every node of a result with its occurrence path, as ``document.collect`` reads the
    tree: a node's children are components where its compound holds as many."""
    from OCP.TopAbs import TopAbs_COMPOUND

    from cadgen.engine.document import _children, _identity

    found = []
    stack = [(result, result.wrapped.Located(_identity()), root_path)]
    while stack:
        obj, topods, path = stack.pop()
        found.append((obj, path))
        state = obj.__dict__
        children = state.get("_NodeMixin__children") or ()
        held = _children(topods) if children and int(topods.ShapeType()) == int(TopAbs_COMPOUND) else []
        if children and len(held) == len(children):
            for at in reversed(range(len(children))):
                stack.append((children[at], held[at].Located(_identity()), path + (at,)))
    return found


def _occurrence(tree: Any, path: tuple[int, ...]) -> tuple[Any, list[str]]:
    """An occurrence's placement in the root's frame (composed as the document's reader
    composes it) and its names from the root down."""
    from cadgen.engine.document import _identity

    node, location, names = tree.root, _identity(), [tree.root.name]
    for at in path:
        component = node.components[at]
        location = location.Multiplied(component.location)
        names.append(component.name or component.prototype.name)
        node = component.prototype
    return location, names


def _common(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    count = 0
    for a, b in zip(left, right):
        if a != b:
            break
        count += 1
    return count


def _joint_kind(joint: Any) -> str | None:
    import build123d as bd

    for cls, kind in ((bd.RigidJoint, "rigid"), (bd.RevoluteJoint, "revolute"), (bd.LinearJoint, "prismatic"),
                      (bd.CylindricalJoint, "cylindrical"), (bd.BallJoint, "spherical")):
        if isinstance(joint, cls):
            return kind
    return None


def _local_frames(kind: str, moving: Any, rigid: Any) -> tuple[np.ndarray, np.ndarray, tuple | None]:
    """A pair's two frames in the parts that hold its joints, as build123d's
    ``relative_to`` places one part on the other, and the value the joint holds."""
    import build123d as bd

    other = _numpy(rigid.relative_location)
    if kind == "revolute":
        held = getattr(moving, "_angle", None)
        return _numpy(moving.relative_axis.location), other, None if held is None else (float(held),)
    if kind == "prismatic":
        frame = _numpy(moving.relative_axis.location)
        turn = frame.copy()
        turn[:3, 3] = 0.0
        held = moving.position
        return frame, other @ turn, None if held is None else (float(held),)
    if kind == "cylindrical":
        axis = moving.relative_axis
        frame = _numpy(bd.Location(bd.Plane(origin=axis.position, x_dir=moving.angle_reference, z_dir=axis.direction)))
        held = None if moving.angle is None or moving.position is None else (float(moving.angle), float(moving.position))
        return frame, other, held
    # spherical: the joint's reference plane turns with the angles, on the rigid side.
    return _numpy(moving.relative_location), other @ np.linalg.inv(_numpy(moving.angle_reference.location)), None


def _limits(kind: str, joint: Any) -> tuple[tuple[float | None, float | None], ...]:
    def finite(pair: Any) -> tuple[float | None, float | None]:
        lower, upper = (float(value) for value in pair)
        return (lower if math.isfinite(lower) else None, upper if math.isfinite(upper) else None)

    if kind == "revolute":
        return (finite(joint.angular_range),)
    if kind == "prismatic":
        return (finite(joint.linear_range),)
    if kind == "cylindrical":
        return (finite(joint.angular_range), finite(joint.linear_range))
    return tuple(finite(pair) for pair in joint.angular_range)


def _within(value: float, limits: tuple[float | None, float | None], slack: float = 1e-9) -> bool:
    lower, upper = limits
    return (lower is None or value >= lower - slack) and (upper is None or value <= upper + slack)


def _angle_in(value: float, hint: float | None, limits: tuple[float | None, float | None]) -> float | None:
    """The angle ``value`` stands for (any turn of it): the joint's own when it is one of
    them, else one within the limits, nearest zero."""
    if hint is not None and abs((hint - value + 180.0) % 360.0 - 180.0) < 1e-6:
        return hint
    candidates = sorted((value + 360.0 * turn for turn in range(-3, 4)), key=abs)
    for candidate in candidates:
        if _within(candidate, limits):
            return candidate
    return None


def _extract(pair: Pair, relative: np.ndarray, hint: tuple | None, scale: float) -> tuple[float, ...] | None:
    """The value of a pair whose link 2 stands at ``relative`` from link 1's frame, item
    to item: None where no value of the pair puts it there, or none within its limits."""
    kind, limits = pair.kind, pair.limits
    rotation = relative[:3, :3]
    if kind in ("revolute", "cylindrical"):
        turned = _angle_in(math.degrees(math.atan2(rotation[1, 0], rotation[0, 0])), hint[0] if hint else None,
                           limits[0])
        if turned is None:
            return None
        found = (turned,) if kind == "revolute" else (turned, float(relative[2, 3]))
    elif kind == "prismatic":
        found = (float(relative[2, 3]),)
    else:
        pitch = math.degrees(math.asin(max(-1.0, min(1.0, rotation[0, 2]))))
        roll = math.degrees(math.atan2(-rotation[1, 2], rotation[2, 2]))
        yaw = math.degrees(math.atan2(-rotation[0, 1], rotation[0, 0]))
        found = None
        for branch in ((roll, pitch, yaw), (roll + 180.0, 180.0 - pitch, yaw + 180.0)):
            angles = [_angle_in(angle, None, limit) for angle, limit in zip(branch, limits)]
            if all(angle is not None for angle in angles):
                found = tuple(angles)
                break
        if found is None:
            return None
    if not all(_within(value, limit, 1e-6 * max(1.0, scale)) for value, limit in zip(found, limits)):
        return None
    if np.abs(pair_motion(kind, found) - relative).max() > 1e-6 * max(1.0, scale):
        return None
    return found


def _by_label(jointed: list, used: set[int], tree: Any, warnings: list[str]) -> list[tuple]:
    """The pairings of joints no ``connect_to`` joined, by their labels: a moving joint and a
    ``RigidJoint`` of the same label on another part are its pair (the moving joint's part stays,
    the rigid one's is placed on it), and two rigid joints of one label fasten their parts. Of
    several candidates, the nearest in the tree is taken (what a placement of a sub-assembly
    holds pairs within it); a moving joint with two equally near is no pair, and a warning,
    rigid joints with two equally near are no pair. A joint that matches nothing is no pair."""
    rows: dict[str, list[tuple[tuple[int, ...], Any]]] = {}
    for path, joint in jointed:
        if id(joint) not in used and _joint_kind(joint) is not None:
            rows.setdefault(joint.label, []).append((path, joint))
    found = []

    def nearest(path: tuple[int, ...], label: str, candidates: list, strict: bool = True) -> Any:
        best = max(_common(path, other) for other, _joint in candidates)
        ties = [row for row in candidates if _common(path, row[0]) == best]
        if len(ties) > 1 and not strict:
            return None
        if len(ties) > 1:
            names = " and ".join("/".join(_occurrence(tree, other)[1]) for other, _joint in ties[:2])
            warnings.append(f"joint {label!r} on {'/'.join(_occurrence(tree, path)[1])} matches the rigid joints "
                            f"{label!r} on {names} alike, so it pairs with neither: give each pair a label of its "
                            "own, or connect it with connect_to")
            return None
        return ties[0]

    for label, held in rows.items():
        rigid = [row for row in held if _joint_kind(row[1]) == "rigid"]
        for path, joint in [row for row in held if _joint_kind(row[1]) != "rigid"]:
            candidates = [row for row in rigid if row[0] != path]
            other = nearest(path, label, candidates) if candidates else None
            if other is not None:
                rigid.remove(other)
                found.append((path, joint, other[0], other[1]))
        # Rigid joints alone fasten only where one is nearest: a datum a part carries in each of
        # its placements (three pegs' `base`) is no fastening.
        mates = {}
        for at, (path, _joint) in enumerate(rigid):
            candidates = [row for row in rigid if row[0] != path]
            other = nearest(path, label, candidates, strict=False) if candidates else None
            mates[at] = None if other is None else next(index for index, row in enumerate(rigid) if row is other)
        for at, other in mates.items():
            if other is not None and other > at and mates.get(other) == at:  # each the other's one nearest
                found.append((*rigid[at], *rigid[other]))
    return found


def _enclose(parent: dict, find: Callable[[tuple[int, ...]], tuple[int, ...]], moving_pairs: list) -> None:
    """A class of joint-holding parts no pair moves, standing below a part of another class in
    the tree, moves with that class: a sub-assembly mounted on a joint carries every part of
    it, the one holding an inner pair's moving joint (its base) too, not only those a pair
    moves. Each such class joins the class of its members' nearest joint-holding ancestor,
    deepest first, when every member has the same one; a class whose members stand under
    different ones, or under none, keeps its own place."""
    while True:
        moved = {find(moves) for _moving, held_by, _rigid, rigid_by, moves in moving_pairs
                 if find(held_by) != find(rigid_by)}
        classes: dict[tuple[int, ...], list[tuple[int, ...]]] = {}
        for path in sorted(parent):
            classes.setdefault(find(path), []).append(path)
        joined = False
        for root, members in sorted(classes.items(), key=lambda item: -max(len(path) for path in item[1])):
            if root in moved:
                continue
            enclosing = set()
            for path in members:
                ancestor = next((path[:depth] for depth in range(len(path) - 1, -1, -1) if path[:depth] in parent), None)
                enclosing.add(None if ancestor is None else find(ancestor))
            if len(enclosing) == 1 and None not in enclosing and root not in enclosing:
                parent[root] = enclosing.pop()
                joined = True
                break
        if not joined:
            return


def harvest(result: Any, tree: Any, root_path: tuple[int, ...]) -> Mechanism | None:
    """The mechanism of a model's result (see the module docstring), or None for one with no
    connected joint. ``root_path`` is the result's own occurrence in ``tree`` (``()``, or
    ``(0,)`` where the document holds it in a component of its own)."""
    objects = _objects(result, root_path)
    holders: dict[int, list[tuple[int, ...]]] = {}
    jointed: list[tuple[tuple[int, ...], Any]] = []
    configured: list[tuple[tuple[int, ...], Any, dict]] = []
    motioned: list[tuple[tuple[int, ...], Any, dict]] = []
    coupled: list[tuple[tuple[int, ...], Any, dict]] = []
    for obj, path in objects:
        joints = obj.__dict__.get("joints") or {}
        for joint in list(joints.values()):
            holders.setdefault(id(joint), []).append(path)
            jointed.append((path, joint))
        held = obj.__dict__.get(CONFIGURATIONS)
        if held:
            configured.append((path, obj, held))
        held = obj.__dict__.get(MOTIONS)
        if held:
            motioned.append((path, obj, held))
        held = obj.__dict__.get(COUPLINGS)
        if held:
            coupled.append((path, obj, held))

    # Every connect_to: (the joint called and its part, which stays; the other and its part, which moves).
    seen: set = set()
    pairings = []
    for path, joint in jointed:
        other = getattr(joint, "connected_to", None)
        candidates = holders.get(id(other)) if other is not None else None
        if not candidates:
            continue
        moved = max(candidates, key=lambda candidate: _common(path, candidate))
        key = frozenset([(path, id(joint)), (moved, id(other))])
        if key in seen:
            continue
        seen.add(key)
        pairings.append((path, joint, moved, other))
    warnings: list[str] = []
    pairings.extend(_by_label(jointed, {id(joint) for row in pairings for joint in (row[1], row[3])}, tree, warnings))

    def name_of(path: tuple[int, ...]) -> str:
        return "/".join(_occurrence(tree, path)[1])

    def labels_below(path: tuple[int, ...]) -> set[str]:
        return {joint.label for holder, joint in jointed if holder[:len(path)] == path}

    def controls_below(path: tuple[int, ...]) -> set[str]:
        return {name for holder, _obj, held in coupled if holder[:len(path)] == path for name in held}

    def unknown(key: str, labels: set[str], controls: set[str] = frozenset()) -> bool:
        return not any(key == known or key.endswith(f":{known}") for known in (*labels, *controls))

    def known(labels: set[str], controls: set[str]) -> str:
        found = f"its joints are {', '.join(sorted(labels))}" if labels else "it holds no joint"
        return found + (f"; its couplings are {', '.join(sorted(controls))}" if controls else "")

    # A mechanism state, a configuration sequence or a coupling naming a joint no part of its assembly holds means
    # nothing, nor does a coupling named as a joint is (a pose could not tell them apart): the
    # harvest's errors, as is a pair the built tree contradicts (below); a value no pair can take is warned.
    for path, _obj, held in configured:
        labels, controls = labels_below(path), controls_below(path)
        for name, values in held.items():
            for key in values:
                if unknown(key, labels, controls):
                    raise KinematicsError(f"mechanism state {name!r} of {name_of(path)} names no joint {key!r}; "
                                          + known(labels, controls))
    for path, _obj, held in motioned:
        labels, controls = labels_below(path), controls_below(path)
        for name, spec in held.items():
            for key in (label for _t, _name, values in (spec[1] if spec[0] == "keys" else ()) for label in values):
                if unknown(key, labels, controls):
                    raise KinematicsError(f"configuration sequence {name!r} of {name_of(path)} names no joint "
                                          f"{key!r}; "
                                          + known(labels, controls))
    for path, _obj, held in coupled:
        labels = labels_below(path)
        for name, (kind, ratios) in held.items():
            if not unknown(name, labels):
                raise KinematicsError(f"{_KIND_NAMES[kind]} {name!r} of {name_of(path)} has a joint's name, which a "
                                      "pose could not tell from it: give it a name of its own")
            for key in ratios:
                if unknown(key, labels):
                    raise KinematicsError(f"{_KIND_NAMES[kind]} {name!r} of {name_of(path)} names no joint {key!r}; "
                                          + known(labels, set()))
    if not pairings:
        if configured or motioned or coupled:
            warnings.append("the mechanism states, couplings or configuration sequences name joints, and no "
                            "joint is paired with another")
        return Mechanism(tree.root.name, [], 0, [], {}, {}, warnings) if warnings else None

    parent: dict[tuple[int, ...], tuple[int, ...]] = {}

    def find(path: tuple[int, ...]) -> tuple[int, ...]:
        parent.setdefault(path, path)
        while parent[path] != path:
            parent[path] = parent[parent[path]]
            path = parent[path]
        return path

    moving_pairs = []
    for stays, joint, moves, other in pairings:
        kinds = (_joint_kind(joint), _joint_kind(other))
        find(stays), find(moves)
        if kinds == ("rigid", "rigid"):
            parent[find(moves)] = find(stays)
            continue
        if None in kinds:
            continue
        if "rigid" not in kinds:
            warnings.append(
                f"joint {joint.label!r} ({type(joint).__name__}) on {name_of(stays)} is connected to {other.label!r} "
                f"({type(other).__name__}) on {name_of(moves)}: a pin in a slot, which no AP242 lower pair is, so it "
                "is no pair. Connect each moving joint to a RigidJoint")
            continue
        if kinds[0] == "rigid":
            moving, held_by, rigid, rigid_by = other, moves, joint, stays
        else:
            moving, held_by, rigid, rigid_by = joint, stays, other, moves
        moving_pairs.append((moving, held_by, rigid, rigid_by, moves))
    if not moving_pairs:
        if configured or motioned or coupled:
            warnings.append("the mechanism states, couplings or configuration sequences name joints, and no moving "
                            "joint is paired")
        return Mechanism(tree.root.name, [], 0, [], {}, {}, warnings) if warnings else None

    _enclose(parent, find, moving_pairs)
    classes: dict[tuple[int, ...], list[tuple[int, ...]]] = {}
    for path in sorted(parent):
        classes.setdefault(find(path), []).append(path)
    # A pair moves the class its moving side is in; one inside a single rigid body moves nothing.
    moved_classes = {find(moves) for _moving, held_by, _rigid, rigid_by, moves in moving_pairs
                     if find(held_by) != find(rigid_by)}
    ground_members = sorted(path for root, members in classes.items() if root not in moved_classes for path in members)
    links = [Link("", ground_members)]
    link_of: dict[tuple[int, ...], int] = {path: 0 for path in ground_members}
    for root, members in sorted(classes.items(), key=lambda item: item[1][0]):
        if root in moved_classes:
            for path in members:
                link_of[path] = len(links)
            links.append(Link("", sorted(members)))
    for link in links:
        link.name = _occurrence(tree, link.members[0])[1][-1] if link.members else tree.root.name
    worlds = {path: _numpy(_occurrence(tree, path)[0]) for path in parent}
    frames = [worlds[link.members[0]] if link.members else np.eye(4) for link in links]
    scale = max([1.0] + [float(np.abs(matrix[:3, 3]).max()) for matrix in worlds.values()])

    # The pairs, named by their moving joints' labels; a label two share takes its part's path.
    counts: dict[str, int] = {}
    for moving, *_rest in moving_pairs:
        counts[moving.label] = counts.get(moving.label, 0) + 1
    pairs: list[Pair] = []
    as_built: dict[str, tuple[float, ...]] = {}
    joint_labels: list[tuple[str, tuple[int, ...]]] = []
    for moving, held_by, rigid, rigid_by, _moves in moving_pairs:
        kind = _joint_kind(moving)
        assert kind is not None and kind != "rigid"
        first, second = link_of[held_by], link_of[rigid_by]
        label = moving.label if counts[moving.label] == 1 else f"{name_of(held_by)}:{moving.label}"
        while any(pair.label == label for pair in pairs):
            label += "'"
        item_1, item_2, held = _local_frames(kind, moving, rigid)
        ax2_1 = _ax2(np.linalg.inv(frames[first]) @ worlds[held_by] @ item_1)
        ax2_2 = _ax2(np.linalg.inv(frames[second]) @ worlds[rigid_by] @ item_2)
        pair = Pair(label, kind, (first, second), (ax2_1, ax2_2), _limits(kind, moving))
        # A pair the built tree contradicts has no value AP242 can hold: refused, by name.
        if first == second:
            together = len(links[first].members)
            raise KinematicsError(
                f"joint {label!r} cannot be kept: it joins {name_of(held_by)} to {name_of(rigid_by)}, which rigid "
                f"joints make one link{f' with {together - 2} other parts' if together > 2 else ''}"
                f"{' (the unmoved ground)' if first == 0 else ''}: the pair cannot move")
        relative = (np.linalg.inv(frame_matrix(ax2_1)) @ np.linalg.inv(frames[first]) @ frames[second]
                    @ frame_matrix(ax2_2))
        value = _extract(pair, relative, held, scale)
        if value is None:
            raise KinematicsError(
                f"joint {label!r} cannot be kept: {name_of(rigid_by)} is not where it can put it"
                f"{'' if held is None else f' (it was connected at {_shown(held)})'}: its rigid joint's frame and "
                f"the {kind} joint's are not one {kind} motion apart within its range (a part moved after "
                "connect_to, or connected after the compound holding it was made, or a rigid joint off the "
                "joint's axis)")
        as_built[label] = value
        pairs.append(pair)
        joint_labels.append((moving.label, held_by))

    couplings, controls = _couplings(coupled, pairs, joint_labels, name_of, warnings, as_built)
    found = Mechanism(tree.root.name, links, 0, pairs, as_built, {}, warnings, couplings=couplings)
    found.configurations = _configurations(configured, found, joint_labels, controls, name_of)
    if motioned:
        functions = any(spec[0] == "function" for _path, _obj, held in motioned for spec in held.values())
        found.motions = _motions(motioned, found, joint_labels, controls, name_of, _size(result) if functions else 1.0)
    return found


class _Unfit(KinematicsError):
    """A configuration sequence's value its pair cannot take: the sequence is left out, and warned."""


def _matching(path: tuple[int, ...], key: str, pairs: list[Pair], joint_labels: list) -> list[Pair]:
    """The pairs a joint label set on the assembly at ``path`` names: by the pair's label or
    its moving joint's, among the joints below the assembly."""
    return [pair for pair, (raw, holder) in zip(pairs, joint_labels)
            if holder[:len(path)] == path and key in (pair.label, raw)]


def _couplings(coupled: list, pairs: list[Pair], joint_labels: list, name_of: Callable, warnings: list[str],
               as_built: dict[str, tuple[float, ...]]) -> tuple[dict[str, Coupling], list[tuple[tuple[int, ...], str, str]]]:
    """Each coupling, by name, its joints made pairs: a joint label names the pair of every joint
    below its assembly so labelled (each placement's, for a sub-assembly placed several times).
    A name two couplings share takes the path of the assembly holding each (``hand/index:curl``),
    as a label two pairs share does. A joint in no pair is left out of the coupling, and warned; a
    coupling left with no joint is left out. A coupling named as a pair is, one driving a pair its
    kind does not relate (``_fits``) is, one whose joints' limits leave it no range holding 0 is,
    and a joint two couplings drive is: they fail the harvest. Returns the couplings and, for each,
    its assembly's path, its own name and the name it is kept by (what a mechanism state or a
    configuration sequence may call it)."""
    counts: dict[str, int] = {}
    for _path, _obj, held in coupled:
        for name in held:
            counts[name] = counts.get(name, 0) + 1
    labels = {pair.label for pair in pairs}
    by_label = {pair.label: pair for pair in pairs}
    found: dict[str, Coupling] = {}
    controls: list[tuple[tuple[int, ...], str, str]] = []
    for path, _obj, held in coupled:
        for name, (kind, given) in held.items():
            kept = name if counts[name] == 1 else f"{name_of(path)}:{name}"
            where = f"{_KIND_NAMES[kind]} {name!r} of {name_of(path)}"
            if kept in labels:
                raise KinematicsError(f"{where} is named {kept!r}, as a joint is, which a pose could not tell from it: "
                                      "give it a name of its own")
            ratios: dict[str, tuple[float, ...]] = {}
            driven: list[Pair] = []
            for key, value in given.items():
                matches = _matching(path, key, pairs, joint_labels)
                if not matches:
                    warnings.append(f"{where} drives joint {key!r}, which is in no pair: the joint is left out of it")
                for pair in matches:
                    _fits(kind, where, pair, driven)
                    driven.append(pair)
                    ratios[pair.label] = tuple(float(ratio) for ratio in value)
            if not ratios:
                warnings.append(f"{where} drives no pair: it is left out")
                continue
            if sum(1 for values in ratios.values() for ratio in values if ratio) < 2:
                raise KinematicsError(f"{where} moves one value alone; a coupling relates two or more")
            coupling = Coupling(kept, ratios)
            lower, upper = _derived_range(coupling, by_label, as_built)
            if lower is not None and upper is not None and not lower < upper:
                raise KinematicsError(f"{where}: its joints' limits leave it no range around as built "
                                      f"([{lower:g}, {upper:g}])")
            found[kept] = coupling
            controls.append((path, name, kept))
    drivers: dict[str, list[str]] = {}
    for kept in sorted(found):
        for label in found[kept].ratios:
            drivers.setdefault(label, []).append(kept)
    for label, names in drivers.items():
        if len(names) > 1:
            raise KinematicsError(f"joint {label!r} is driven by the couplings {names[0]!r} and {names[1]!r}: a "
                                  "coupling is a constraint, its joints' only way to move")
    return {name: found[name] for name in sorted(found)}, controls


def _fits(kind: str, where: str, pair: Pair, before: list[Pair]) -> None:
    """Refuses ``pair`` in a coupling of ``kind`` after the pairs ``before`` it: a gear pair turns
    revolute pairs; a rack and pinion pair takes a revolute or a prismatic pair first and every
    other of the other kind (each coupler is from the first to another); a screw pair is one
    cylindrical pair's turn and travel."""
    if kind == GEAR_KIND and pair.kind != "revolute":
        raise KinematicsError(f"{where} drives the {pair.kind} joint {pair.label!r}: a gear pair turns revolute "
                              "joints")
    if kind == RACK_KIND:
        if pair.kind not in ("revolute", "prismatic"):
            raise KinematicsError(f"{where} drives the {pair.kind} joint {pair.label!r}: a rack and pinion pair "
                                  "relates a revolute joint and a prismatic one")
        if before and (pair.kind == before[0].kind):
            raise KinematicsError(f"{where} drives {before[0].label!r} and {pair.label!r}, both {pair.kind}: a rack "
                                  f"and pinion pair relates its first joint, {before[0].label!r}, to joints of the "
                                  "other kind")
    if kind == SCREW_KIND:
        if pair.kind != "cylindrical":
            raise KinematicsError(f"{where} drives the {pair.kind} joint {pair.label!r}: a screw pair is a "
                                  "cylindrical joint's turn and travel")
        if before:
            raise KinematicsError(f"{where} drives {before[0].label!r} and {pair.label!r}: a screw pair drives one "
                                  "cylindrical joint")


def _derived_range(coupling: Coupling, pairs: dict[str, Any], as_built: dict[str, Any]) -> tuple[Any, Any]:
    """A coupling's range: the tightest interval of its value in which every joint it drives
    stays within its own limits (None for a side nothing bounds). ``pairs`` by label, each a
    ``Pair`` or the structure's entry; ``as_built`` the pairs' values as built."""
    lower, upper = -math.inf, math.inf
    for label, ratios in coupling.ratios.items():
        pair = pairs[label]
        limits = pair.limits if isinstance(pair, Pair) else [tuple(limit) for limit in pair.get("limits") or ()]
        built = _as_tuple(as_built.get(label, (0.0,) * len(ratios)))
        for index, ratio in enumerate(ratios):
            if not ratio or index >= len(limits):
                continue
            low, high = limits[index]
            ends = [None if bound is None else (bound - built[index]) / ratio for bound in (low, high)]
            if ratio < 0:
                ends.reverse()
            if ends[0] is not None:
                lower = max(lower, ends[0])
            if ends[1] is not None:
                upper = min(upper, ends[1])
    # As built is read from the frames: an end within a rounding of it is it (and never -0).
    return tuple(None if math.isinf(end) else 0.0 if abs(end) < 1e-9 else end for end in (lower, upper))


def _coupling_json(coupling: Coupling, pairs: list[Pair], as_built: dict[str, Any] | None = None) -> dict[str, Any]:
    """A coupling as the structure's ``kinematics.couplings`` holds it: its range (derived from
    its joints' limits; null on a side nothing bounds) and its terms, ``[pair, value index,
    ratio]`` in the pairs' order. Its joints move only through it."""
    by_label = {pair.label: pair for pair in pairs}
    lower, upper = _derived_range(coupling, by_label, as_built or {})
    return {"range": [lower, upper],
            "terms": [[pair.label, index, float(ratio)] for pair in pairs if pair.label in coupling.ratios
                      for index, ratio in enumerate(coupling.ratios[pair.label])]}


def _locked(couplings: dict[str, Any]) -> dict[str, str]:
    """Each pair a coupling drives (``kinematics.couplings``), which moves only through it: the
    coupling's name."""
    return {label: name for name, coupling in couplings.items() for label, _index, _ratio in coupling["terms"]}


def _bound(value: Any, sign: str) -> str:
    return f"{sign}inf" if value is None else f"{value:g}"


def _coupled(given: dict[str, Any], couplings: dict[str, Any], as_built: dict[str, tuple[float, ...]],
             checked: Callable[[str, tuple[float, ...], str], tuple[float, ...]],
             where: str) -> dict[str, tuple[float, ...]]:
    """The pair values couplings put their joints at: ``given`` is each coupling's value by name,
    ``couplings`` the structure's. Each joint stands at its as-built values plus each coupling's
    ratio times its value (couplings sharing a joint add). A value that is no number or is outside
    its coupling's range, and one putting a joint past its limits (``checked``), are refused by
    name."""
    moved: dict[str, list[float]] = {}
    by: dict[str, dict[str, None]] = {}
    for name, value in given.items():
        coupling = couplings[name]
        found = _number_values(value)
        if found is None or len(found) != 1 or not math.isfinite(found[0]):
            raise KinematicsError(f"{where}: coupling {name!r} takes a number, not {value!r}")
        lower, upper = coupling["range"]
        if not _within(found[0], (lower, upper)):
            raise KinematicsError(f"{where}: coupling {name!r} at {found[0]:g} is outside its range "
                                  f"[{_bound(lower, '-')}, {_bound(upper, '')}]")
        for label, index, ratio in coupling["terms"]:
            row = moved.setdefault(label, list(as_built[label]))
            row[index] += ratio * found[0]
            by.setdefault(label, {})[f"{name!r} at {found[0]:g}"] = None
    return {label: checked(label, tuple(row), f"{where}: coupling{'s' if len(by[label]) > 1 else ''} "
                                              f"{', '.join(by[label])}")
            for label, row in moved.items()}


def _converted(path: tuple[int, ...], values: dict[str, Any], mechanism: Mechanism, joint_labels: list,
               controls: list, where: str) -> tuple[dict[str, tuple[float, ...]], list[str]]:
    """``values`` as :func:`_converter`'s pair values, and what could not be taken."""
    return _converter(path, mechanism, joint_labels, controls)(values, where)


def _converter(path: tuple[int, ...], mechanism: Mechanism, joint_labels: list,
               controls: list) -> Callable[[dict[str, Any], str], tuple[dict[str, tuple[float, ...]], list[str]]]:
    """For the assembly at ``path``: ``values`` -- joints by label and couplings by name, as it
    sets them -- as the pair values they put the pairs at, and what could not be taken, each said by name:
    a joint in no pair, a value its pair cannot take, a locked coupling's joint set alone, a
    coupling set with one of its joints, a coupling's value outside its range or putting a joint
    past its limits. What a configuration and a motion name is made pair values here, at
    document time. What the mechanism holds is read once, here: a motion's function converts
    every sample through the one converter, each key a lookup."""
    pairs = mechanism.pairs
    by_label = {pair.label: pair for pair in pairs}
    couplings = {name: _coupling_json(coupling, pairs, mechanism.as_built)
                 for name, coupling in mechanism.couplings.items()}
    locked = _locked(couplings)
    # The couplings (by kept name) and pairs each key names, in their order, as the scans found them.
    naming: dict[str, list[str]] = {}
    for holder, own, kept in controls:
        if holder[:len(path)] == path:
            for key in {own, kept}:
                naming.setdefault(key, []).append(kept)
    matching: dict[str, list[Pair]] = {}
    for pair, (raw, holder) in zip(pairs, joint_labels):
        if holder[:len(path)] == path:
            for key in {pair.label, raw}:
                matching.setdefault(key, []).append(pair)
    as_built = mechanism.as_built
    checked = lambda label, row, at: _checked(by_label[label], row, at)  # noqa: E731
    return lambda values, where: _convert(values, where, mechanism, naming, matching, couplings, locked, as_built,
                                          checked)


def _convert(values: dict[str, Any], where: str, mechanism: Mechanism, naming: dict[str, list[str]],
             matching: dict[str, list[Pair]], couplings: dict[str, Any], locked: dict[str, str],
             as_built: dict[str, tuple[float, ...]],
             checked: Callable) -> tuple[dict[str, tuple[float, ...]], list[str]]:
    found: dict[str, tuple[float, ...]] = {}
    problems: list[str] = []
    driving: dict[str, Any] = {}
    for key, value in values.items():
        named = naming.get(key)
        if named:
            driving.update(dict.fromkeys(named, value))
            continue
        matches = matching.get(key, [])
        if not matches:
            problems.append(f"{where} sets joint {key!r}, which is in no pair")
        for pair in matches:
            if pair.label in locked:
                problems.append(f"{where}: joint {pair.label!r} moves only with its coupling "
                                f"{locked[pair.label]!r}; set {locked[pair.label]!r}")
                continue
            try:
                found[pair.label] = _checked(pair, value, where)
            except KinematicsError as error:
                problems.append(str(error))
    for name in list(driving):
        clash = [label for label in mechanism.couplings[name].ratios if label in found]
        problem = f"{where} sets coupling {name!r} and its joint {clash[0]!r}: set one of them" if clash else None
        if problem is None:
            try:
                _coupled({name: driving[name]}, couplings, as_built, checked, where)
            except KinematicsError as error:
                problem = str(error)
        if problem is not None:
            problems.append(problem)
            del driving[name]
    if driving:
        try:
            found.update(_coupled(driving, couplings, as_built, checked, where))
        except KinematicsError as error:  # each alone within the limits, together past them
            problems.append(str(error))
    return {pair.label: found[pair.label] for pair in mechanism.pairs if pair.label in found}, problems


def _size(result: Any) -> float:
    """A model's size: its bounding box's diagonal, from its geometry (never a mesh), at least 1 mm."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(result.wrapped, box, False)
    if box.IsVoid():
        return 1.0
    low, high = box.CornerMin(), box.CornerMax()
    return max(1.0, math.dist((low.X(), low.Y(), low.Z()), (high.X(), high.Y(), high.Z())))


def _motions(motioned: list, mechanism: Mechanism, joint_labels: list, controls: list, name_of: Callable,
             size: float) -> dict[str, Motion]:
    """Each motion as the document keeps it, by name: its keys in pair labels (a function's
    sampled, a coupling's value made its joints'), a shallower assembly's motion over a deeper
    one's of the same name. A motion naming a configuration the mechanism has not, or a joint
    its assembly has not, is the harvest's error; one setting a value its pair cannot take, or
    moving a pair that closes a loop, is left out, and warned."""
    pairs, warnings = mechanism.pairs, mechanism.warnings
    _reached, loop = _tree(mechanism)
    blocked = {label: f"pairs {', '.join(loop)} close a loop" for label in loop or ()}
    tolerances = {pair.label: [math.degrees(ANGULAR_TOLERANCE) if unit == "deg" else LINEAR_TOLERANCE * size
                               for unit, *_names in KINDS[pair.kind][1]] for pair in pairs}
    found: dict[str, Motion] = {}
    for path, _obj, held in sorted(motioned, key=lambda item: -len(item[0])):
        for name, spec in held.items():
            where = f"configuration sequence {name!r} of {name_of(path)}"
            converter = _converter(path, mechanism, joint_labels, controls)

            def convert(values: dict[str, Any], at: str) -> dict[str, tuple[float, ...]]:
                converted, problems = converter(values, f"{where}: {at}")
                if problems:
                    raise _Unfit(problems[0])
                return converted

            try:
                if spec[0] == "function":
                    from cadgen.engine.kernel import memo

                    _kind, function, duration, _ease = spec
                    # The files the function opens are the model's inputs (``memo.listened``).
                    keys = memo.listened(lambda: _sampled(function, duration, convert, tolerances, where, path,
                                                          joint_labels, controls))
                    ease = "linear"
                else:
                    _kind, rows, ease = spec
                    keys = []
                    for t, configuration, values in rows:
                        if configuration is not None:
                            if configuration not in mechanism.configurations:
                                known = ", ".join(sorted(mechanism.configurations)) or "none"
                                raise KinematicsError(f"{where}: the waypoint at {t:g} s names no mechanism state "
                                                      f"{configuration!r}; the mechanism states: {known}")
                            keys.append((t, configuration, {}))
                        else:
                            keys.append((t, None, convert(values, f"the waypoint at {t:g} s")))
                motion = Motion(name, keys, ease)
                stopped = sorted({label for label in motion.labels() | {label for _t, configuration, _v in keys
                                                                        if configuration is not None
                                                                        for label in mechanism.configurations[configuration]}
                                  if label in blocked})
                if stopped:
                    raise _Unfit(f"{where} moves joint {stopped[0]!r}, which cannot be posed: {blocked[stopped[0]]}")
            except _Unfit as error:
                warnings.append(f"{error}: the configuration sequence is left out")
                found.pop(name, None)
                continue
            found[name] = motion
    return {name: found[name] for name in sorted(found)}


def _flat(values: dict[str, tuple[float, ...]], labels: list[str]) -> np.ndarray:
    return np.array([value for label in labels for value in values[label]], dtype=float)


def _sampled(function: Callable, duration: float, convert: Callable, tolerances: dict[str, list[float]],
             where: str, path: tuple[int, ...], joint_labels: list, controls: list) -> list:
    """A function of time's samples: eight equal steps over its duration, each step split while
    the samples' linear interpolation (AP242's, which a reader of the document and the GLB baker
    both apply) strays from the function, at any eighth of it, by more than half the tolerance
    (``ANGULAR_TOLERANCE``, ``LINEAR_TOLERANCE``), until none does. A step is split where it
    strays most, not at its middle: a kink (where straight runs meet) is the error's peak, between
    two check points, so the split closes in on it and the runs either side are then held
    exactly; and the half tolerance at the checks keeps the peak between them within the whole
    one. A function of the code: the same function samples at the same times."""
    held: dict[float, dict[str, tuple[float, ...]]] = {}
    names = {name for holder, own, kept in controls if holder[:len(path)] == path for name in (own, kept)}
    # The joints under ``path``, once: a key names one by its raw label, or ends ``:<raw label>``.
    raws = {raw for raw, holder in joint_labels if holder[:len(path)] == path}

    def known(key: str) -> bool:
        return key in names or key in raws or any(key[colon + 1:] in raws
                                                  for colon, char in enumerate(key) if char == ":")

    def at(t: float) -> dict[str, tuple[float, ...]]:
        found = held.get(t)
        if found is None:
            try:
                given = function(t)
            except Exception as error:  # noqa: BLE001 - the model's function, said by name
                raise KinematicsError(f"{where}: the function raised at {t:g} s: {error!r}") from None
            if not isinstance(given, dict) or not given:
                raise KinematicsError(f"{where}: the function returns {{joint: value}}, not {given!r} (at {t:g} s)")
            for key in given:
                if not known(key):
                    labels = sorted(raws)
                    raise KinematicsError(f"{where} names no joint {key!r}; its joints are {', '.join(labels)}"
                                          + (f"; its couplings are {', '.join(sorted(names))}" if names else ""))
            found = held[t] = convert(given, f"the function at {t:g} s")
        return found

    first = at(0.0)
    labels = sorted(first)
    tolerance = np.array([value for label in labels for value in tolerances[label]], dtype=float)
    times = [duration * step / 8 for step in range(9)]
    while True:
        rows = []
        for t in times:
            values = at(t)
            if sorted(values) != labels:
                raise KinematicsError(f"{where}: the function sets {', '.join(sorted(values))} at {t:g} s and "
                                      f"{', '.join(labels)} at 0 s: it sets the same joints at every time")
            rows.append(_flat(values, labels))
        grid, table = np.array(times), np.array(rows)
        split = []
        for a, b in zip(times, times[1:]):
            # The step's worst check against the tolerance, and where it is.
            worst, there = 0.0, None
            for eighth in range(1, 8):
                t = a + (b - a) * eighth / 8
                strayed = float(np.max(np.abs(_interpolated(grid, table, "linear", t) - _flat(at(t), labels))
                                       / tolerance))
                if strayed > worst:
                    worst, there = strayed, t
            if worst > 0.5:
                split.append(there)
        if not split:
            return [(t, None, at(t)) for t in times]
        times = sorted(set(times) | set(split))
        if len(times) > MOST_KEYS:
            raise KinematicsError(f"{where}: the function does not settle within the tolerance in {MOST_KEYS} samples")


def _interpolated(times: np.ndarray, values: np.ndarray, ease: str, t: float) -> np.ndarray:
    """Values at ``t`` between keys: ``linear`` or ``cubic`` (each step eased in and out)."""
    if t <= times[0]:
        return values[0].copy()
    if t >= times[-1]:
        return values[-1].copy()
    at = min(int(np.searchsorted(times, t, side="right")) - 1, len(times) - 2)
    span = times[at + 1] - times[at]
    s = (t - times[at]) / span
    if ease == "linear":
        return values[at] + s * (values[at + 1] - values[at])
    return values[at] + s * s * (3.0 - 2.0 * s) * (values[at + 1] - values[at])


def _shown(values: tuple[float, ...] | list[float]) -> str:
    text = [f"{value:g}" for value in values]
    return text[0] if len(text) == 1 else "(" + ", ".join(text) + ")"


def _configurations(configured: list, mechanism: Mechanism, joint_labels: list, controls: list,
                    name_of: Callable) -> dict:
    """Each named configuration as pair values (a coupling's value made its joints'), every
    assembly's that names it merged, a deeper one's values first and a shallower one's over
    them. What a value cannot be taken for (``_converted``) is left out, and warned."""
    merged: dict[str, dict[str, tuple[float, ...]]] = {}
    for path, _obj, held in sorted(configured, key=lambda item: -len(item[0])):
        for name, values in held.items():
            found, problems = _converted(path, values, mechanism, joint_labels, controls,
                                         f"mechanism state {name!r} of {name_of(path)}")
            mechanism.warnings.extend(f"{problem}: the value is left out" for problem in problems)
            merged.setdefault(name, {}).update(found)
    return {name: merged[name] for name in sorted(merged)}


def _checked(pair: Pair, value: Any, where: str) -> tuple[float, ...]:
    """A value for ``pair``: as many numbers as it has values, each within its limits."""
    found = _number_values(value)
    if found is None or len(found) != pair.dofs or not all(math.isfinite(v) for v in found):
        need = "a number" if pair.dofs == 1 else f"{pair.dofs} numbers ({', '.join(_dof_names(pair.kind))})"
        raise KinematicsError(f"{where}: joint {pair.label!r} ({pair.kind}) takes {need}, not {value!r}")
    for value_at, limits, (unit, *_names) in zip(found, pair.limits, KINDS[pair.kind][1]):
        if not _within(value_at, limits):
            lower = "-inf" if limits[0] is None else f"{limits[0]:g}"
            upper = "inf" if limits[1] is None else f"{limits[1]:g}"
            raise KinematicsError(f"{where}: joint {pair.label!r} at {value_at:g} {unit} is outside its range "
                                  f"[{lower}, {upper}] {unit}")
    return found


def _dof_names(kind: str) -> tuple[str, ...]:
    return {"cylindrical": ("angle", "position"), "spherical": ("x", "y", "z angles")}.get(kind, ("value",))


# --- the document --------------------------------------------------------------------------


def _text(value: str) -> Any:
    from OCP.TCollection import TCollection_ExtendedString

    return TCollection_ExtendedString(value, True)


def _label(parent: Any, tag: int, name: str, entity: str | None = None) -> Any:
    from OCP.TDataStd import TDataStd_NamedData

    from cadgen.engine.document import _name

    label = parent.FindChild(tag, True)
    _name(label, name)
    if entity is not None:
        TDataStd_NamedData.Set_s(label).SetString(_text("entity"), _text(entity))
    return label


def _reals(values: Any) -> Any:
    from OCP.TColStd import TColStd_HArray1OfReal

    array = TColStd_HArray1OfReal(1, len(values))
    for at, value in enumerate(values, 1):
        array.SetValue(at, float(value))
    return array


def _state(label: Any, pair_labels: list, values: dict[str, tuple[float, ...]], pairs: list[Pair]) -> None:
    from OCP.TDataStd import TDataStd_IntegerArray, TDataStd_RealArray, TDataStd_ReferenceList

    rows = [(at, dof, value) for at, pair in enumerate(pairs) if pair.label in values
            for dof, value in enumerate(values[pair.label])]
    if not rows:
        return
    references = TDataStd_ReferenceList.Set_s(label)
    reals = TDataStd_RealArray.Set_s(label, 1, len(rows))
    dofs = TDataStd_IntegerArray.Set_s(label, 1, len(rows))
    for row, (at, dof, value) in enumerate(rows, 1):
        references.Append(pair_labels[at])
        reals.SetValue(row, float(value))
        dofs.SetValue(row, dof)


def write(doc: Any, mechanism: Mechanism, occurrence: Callable[[tuple[int, ...]], list]) -> None:
    """The mechanism's subtree in ``doc`` (see the module docstring). ``occurrence(path)``
    is an occurrence's labels: the root's, then each component's down to it."""
    from OCP.Standard import Standard_GUID
    from OCP.TCollection import TCollection_AsciiString
    from OCP.TColStd import TColStd_ListOfAsciiString
    from OCP.TDataStd import TDataStd_NamedData, TDataStd_ReferenceList, TDataStd_UAttribute
    from OCP.XCAFDoc import XCAFDoc_AssemblyItemId, XCAFDoc_AssemblyItemRef

    from cadgen.engine.document import _entry

    root = _label(doc.Main(), TAG, "Kinematics")
    TDataStd_UAttribute.Set_s(root, Standard_GUID(GUID))
    data = TDataStd_NamedData.Set_s(root)
    data.SetString(_text("schema"), _text(SCHEMA))
    data.SetString(_text("angle_unit"), _text("deg"))
    data.SetString(_text("length_unit"), _text("mm"))
    top = _label(root, 1, mechanism.name, "MECHANISM_REPRESENTATION")
    links_label = _label(top, 1, "links")
    pairs_label = _label(top, 2, "pairs")
    link_labels = []
    for at, link in enumerate(mechanism.links, 1):
        label = _label(links_label, at, link.name, "KINEMATIC_LINK")
        for member_at, path in enumerate(link.members, 1):
            entries = TColStd_ListOfAsciiString()
            for step in occurrence(path):
                entries.Append(TCollection_AsciiString(_entry(step)))
            XCAFDoc_AssemblyItemRef.Set_s(label.FindChild(member_at, True), XCAFDoc_AssemblyItemId(entries))
        link_labels.append(label)
    # MECHANISM_REPRESENTATION's base: the link that does not move.
    if link_labels:
        TDataStd_ReferenceList.Set_s(top).Append(link_labels[mechanism.ground])
    pair_labels = []
    for at, pair in enumerate(mechanism.pairs, 1):
        entity, dofs = KINDS[pair.kind]
        ranged = any(limit is not None for limits in pair.limits for limit in limits)
        label = _label(pairs_label, at, pair.label, entity + ("_WITH_RANGE" if ranged else ""))
        data = TDataStd_NamedData.Set_s(label)
        if pair.frames is not None:
            data.SetArrayOfReals(_text("transform_item_1"), _reals(pair.frames[0]))
            data.SetArrayOfReals(_text("transform_item_2"), _reals(pair.frames[1]))
        for (_unit, lower_name, upper_name), (lower, upper) in zip(dofs, pair.limits):
            if lower is not None:
                data.SetReal(_text(lower_name), float(lower))
            if upper is not None:
                data.SetReal(_text(upper_name), float(upper))
        references = TDataStd_ReferenceList.Set_s(label)
        references.Append(link_labels[pair.links[0]])  # KINEMATIC_JOINT.edge_start: link 1
        references.Append(link_labels[pair.links[1]])  # edge_end: link 2
        pair_labels.append(label)
    _state(_label(top, 3, "as built", "MECHANISM_STATE_REPRESENTATION"), pair_labels, mechanism.as_built,
           mechanism.pairs)
    configurations = _label(top, 4, "configurations")
    configuration_labels = {}
    for at, (name, values) in enumerate(mechanism.configurations.items(), 1):
        label = configuration_labels[name] = _label(configurations, at, name, "MECHANISM_STATE_REPRESENTATION")
        _state(label, pair_labels, values, mechanism.pairs)
    if mechanism.motions:
        # Each motion as AP242's interpolated configuration sequence: its segments' times and states.
        motions = _label(top, 5, "motions")
        for at, (name, motion) in enumerate(mechanism.motions.items(), 1):
            label = _label(motions, at, name, "INTERPOLATED_CONFIGURATION_SEQUENCE")
            for key_at, (t, configuration, values) in enumerate(motion.keys, 1):
                segment = _label(label, key_at, repr(float(t)), "INTERPOLATED_CONFIGURATION_SEGMENT")
                data = TDataStd_NamedData.Set_s(segment)
                data.SetReal(_text("t_parameter"), float(t))
                # The interpolation to the next segment; the last's says the clip ends there.
                last = key_at == len(motion.keys)
                data.SetString(_text("interpolation"),
                               _text(LAST_INTERPOLATION if last else INTERPOLATIONS[motion.ease]))
                if configuration is not None:
                    TDataStd_ReferenceList.Set_s(segment).Append(configuration_labels[configuration])
                else:
                    _state(segment, pair_labels, values, mechanism.pairs)
    if mechanism.couplings:
        # Each coupling as the standard's couplers, chained from its first-named value (``_couplers``).
        couplings = _label(top, 6, "couplings")
        pair_label = {pair.label: label for pair, label in zip(mechanism.pairs, pair_labels)}
        by_label = {pair.label: pair for pair in mechanism.pairs}
        for at, (name, coupling) in enumerate(mechanism.couplings.items(), 1):
            holder = _label(couplings, at, name)
            for coupler_at, (entity, attributes, ends) in enumerate(_couplers(coupling, by_label), 1):
                label = _label(holder, coupler_at, f"{name}.{coupler_at}", entity)
                data = TDataStd_NamedData.Set_s(label)
                for key, value in attributes.items():
                    if isinstance(value, str):
                        data.SetString(_text(key), _text(value))
                    elif isinstance(value, tuple):
                        data.SetArrayOfReals(_text(key), _reals(value))
                    else:
                        data.SetReal(_text(key), float(value))
                references = TDataStd_ReferenceList.Set_s(label)
                for end in ends:
                    references.Append(pair_label[end])


def _value_type(pair: Pair, index: int) -> str:
    """A pair's value as a coupler names it: ``rotation`` or ``translation``."""
    return "translation" if pair.kind == "prismatic" or (pair.kind == "cylindrical" and index == 1) else "rotation"


def _value_index(kind: str, value_type: str) -> int:
    return 1 if kind == "cylindrical" and value_type == "translation" else 0


def _couplers(coupling: Coupling, pairs: dict[str, Pair]) -> list[tuple[str, dict[str, Any], list[str]]]:
    """A coupling as AP242's couplers: ``(entity, attributes, pair labels)`` each, chained from
    its first-named value. Between that value ``1`` and each other ``k`` (``r`` their ratios): a
    cylindrical pair's turn and travel are a ``SCREW_PAIR`` (``pitch``: travel per 360 degrees);
    two revolute rotations a ``gear_pair``, a revolute rotation and a prismatic translation a
    ``rack_and_pinion_pair``, each ``CouplingRatios`` (``_fits`` admits no other two);
    ``CouplingTypes`` says which value of each pair, in the pairs' order. Over the two values' displacements from as built, ``s_a d_a
    + s_b d_b = 0``, written ``s_a = r_b``, ``s_b = -r_a``."""
    terms = [(label, index, ratio) for label, ratios in coupling.ratios.items()
             for index, ratio in enumerate(ratios) if ratio]
    (hub_label, hub_index, hub_ratio), others = terms[0], terms[1:]
    found = []
    for label, index, ratio in others:
        ends = [(hub_label, hub_index, hub_ratio), (label, index, ratio)]
        if label == hub_label and pairs[label].kind == "cylindrical":
            turn, travel = sorted(ends, key=lambda end: end[1])
            found.append((SCREW, {"pitch": 360.0 * travel[2] / turn[2]}, [label]))
            continue
        kinds = [(pairs[end[0]].kind, _value_type(pairs[end[0]], end[1])) for end in ends]
        if all(kind == ("revolute", "rotation") for kind in kinds):
            kind = GEAR_KIND
        else:
            assert sorted(kinds) == [("prismatic", "translation"), ("revolute", "rotation")], kinds
            kind = RACK_KIND
        (a, a_index, a_ratio), (b, b_index, b_ratio) = ends
        found.append((COUPLER, {"Kind": kind, "CouplingRatios": (b_ratio, -a_ratio),
                                "CouplingTypes": ",".join(_value_type(pairs[end[0]], end[1]) for end in ends)},
                      [a, b]))
    return found


def _read_couplers(name: str, label: Any, pair_at: dict[str, int], pairs: list[Pair]) -> Coupling | None:
    """A coupling read back from its couplers (``_couplers``): each value's ratio, the first-named
    value's first. A screw alone gives its turn the ratio 1."""
    relations: list[tuple[tuple[str, int], tuple[str, int], float, float]] = []  # a, b, r_a, r_b
    screws: list[tuple[str, float]] = []
    for coupler in _children_of(label):
        data = _named(coupler)
        entity = _string(data, "entity")
        ends = [pairs[pair_at[entry]] for entry in _references(coupler) if entry in pair_at]
        if entity == SCREW and len(ends) == 1 and _real(data, "pitch") is not None:
            screws.append((ends[0].label, _real(data, "pitch")))
            continue
        if entity != COUPLER or len(ends) != 2:
            continue
        scales = _array(data, "CouplingRatios")
        types = (_string(data, "CouplingTypes") or "").split(",")
        if scales is None or len(scales) != 2 or len(types) != 2:
            continue
        a = (ends[0].label, _value_index(ends[0].kind, types[0]))
        b = (ends[1].label, _value_index(ends[1].kind, types[1]))
        relations.append((a, b, -scales[1], scales[0]))
    ratios: dict[tuple[str, int], float] = {}
    for a, b, r_a, r_b in relations:
        ratios.setdefault(a, r_a)
        ratios.setdefault(b, r_b)
    for screw_label, pitch in screws:
        turn = ratios.setdefault((screw_label, 0), 1.0)
        ratios[(screw_label, 1)] = turn * pitch / 360.0
    if not ratios:
        return None
    by_pair: dict[str, list[float]] = {}
    for (pair_label, index), ratio in ratios.items():
        pair = next(p for p in pairs if p.label == pair_label)
        by_pair.setdefault(pair_label, [0.0] * pair.dofs)[index] = ratio
    return Coupling(name, {label_: tuple(values) for label_, values in by_pair.items()})


def _children_of(label: Any) -> list:
    from OCP.TDF import TDF_ChildIterator

    found = []
    iterator = TDF_ChildIterator(label, False)
    while iterator.More():
        found.append(iterator.Value())
        iterator.Next()
    return found


def _named(label: Any) -> Any:
    from OCP.TDataStd import TDataStd_NamedData

    from cadgen.engine.document import _find

    data = TDataStd_NamedData()
    if not _find(label, data, TDataStd_NamedData.GetID_s()):
        return None
    data.LoadDeferredData()
    return data


def _string(data: Any, key: str) -> str | None:
    return data.GetString(_text(key)).ToExtString() if data is not None and data.HasString(_text(key)) else None


def _real(data: Any, key: str) -> float | None:
    return data.GetReal(_text(key)) if data is not None and data.HasReal(_text(key)) else None


def _array(data: Any, key: str) -> tuple[float, ...] | None:
    if data is None or not data.HasArrayOfReals(_text(key)):
        return None
    array = data.GetArrayOfReals(_text(key))
    return tuple(array.Value(at) for at in range(array.Lower(), array.Upper() + 1))


def _references(label: Any) -> list[str]:
    """The label's reference list as entries, in order. Read off a copy with ``First``/
    ``RemoveFirst``: the bound list's Python iterator ends in a C++ exception, about 3 ms a
    list, which over a large mechanism's thousands of lists was most of a read."""
    from OCP.TDataStd import TDataStd_ReferenceList
    from OCP.TDF import TDF_LabelList

    from cadgen.engine.document import _entry, _find

    found = TDataStd_ReferenceList()
    if not _find(label, found, TDataStd_ReferenceList.GetID_s()):
        return []
    rest = TDF_LabelList()
    rest.Assign(found.List())
    entries = []
    while not rest.IsEmpty():
        entries.append(_entry(rest.First()))
        rest.RemoveFirst()
    return entries


def _read_state(label: Any, references: list[str], pair_at: dict[str, int],
                pairs: list[Pair]) -> dict[str, tuple[float, ...]]:
    """A state held on ``label``: its values, one row per entry of ``references`` (its own
    reference list, read once by the caller)."""
    from OCP.TDataStd import TDataStd_IntegerArray, TDataStd_RealArray

    from cadgen.engine.document import _find

    reals, dofs = TDataStd_RealArray(), TDataStd_IntegerArray()
    if not references or not _find(label, reals, TDataStd_RealArray.GetID_s()) \
            or not _find(label, dofs, TDataStd_IntegerArray.GetID_s()):
        return {}
    rows: dict[str, list[float]] = {}
    for row, entry in enumerate(references):
        pair = pairs[pair_at[entry]]
        values = rows.setdefault(pair.label, [0.0] * pair.dofs)
        values[dofs.Value(dofs.Lower() + row)] = reals.Value(reals.Lower() + row)
    return {label_: tuple(values) for label_, values in rows.items()}


def read(doc: Any, occurrences: dict[str, tuple[int, ...]]) -> Mechanism | None:
    """The mechanism a document holds, or None. ``occurrences`` maps an occurrence's label
    entries, ``/``-joined from the root, to its component indices."""
    from OCP.Standard import Standard_GUID
    from OCP.XCAFDoc import XCAFDoc_AssemblyItemRef

    from cadgen.engine.document import _entry, _find, _label_name

    marker = Standard_GUID(GUID)
    root = next((label for label in _children_of(doc.Main()) if label.IsAttribute(marker)), None)
    if root is None:
        return None
    top = root.FindChild(1, False)
    links_label, pairs_label = top.FindChild(1, False), top.FindChild(2, False)
    links, link_at = [], {}
    for label in _children_of(links_label):
        members = []
        for member in _children_of(label):
            item = XCAFDoc_AssemblyItemRef()
            if _find(member, item, XCAFDoc_AssemblyItemRef.GetID_s()):
                path = occurrences.get(item.GetItem().ToString().ToCString())
                if path is not None:
                    members.append(path)
        link_at[_entry(label)] = len(links)
        links.append(Link(_label_name(label), members))
    pairs, pair_at = [], {}
    for label in _children_of(pairs_label):
        data = _named(label)
        entity = _string(data, "entity") or ""
        kind = _BY_ENTITY.get(entity.removesuffix("_WITH_RANGE"))
        ends = [link_at.get(entry) for entry in _references(label)]
        if kind is None or len(ends) != 2 or None in ends:
            continue
        first, second = _array(data, "transform_item_1"), _array(data, "transform_item_2")
        limits = tuple((_real(data, lower), _real(data, upper)) for _unit, lower, upper in KINDS[kind][1])
        pair_at[_entry(label)] = len(pairs)
        pairs.append(Pair(_label_name(label), kind, (ends[0], ends[1]),
                          (first, second) if first is not None and second is not None else None, limits))
    ground = link_at.get(next(iter(_references(top)), ""), 0)
    held_state = top.FindChild(3, False)
    as_built = _read_state(held_state, _references(held_state), pair_at, pairs)
    configuration_labels = _children_of(top.FindChild(4, False))
    configurations = {_label_name(label): _read_state(label, _references(label), pair_at, pairs)
                      for label in configuration_labels}
    named = {_entry(label): _label_name(label) for label in configuration_labels}
    motions = {}
    held_motions = top.FindChild(5, False)
    for label in ([] if held_motions.IsNull() else _children_of(held_motions)):
        keys, ease = [], "cubic"
        for at, segment in enumerate(_children_of(label)):
            references = _references(segment)
            segment_data = _named(segment)
            t = _real(segment_data, "t_parameter") or 0.0
            if at == 0:
                ease = _EASE_OF.get(_string(segment_data, "interpolation") or "", "cubic")
            if references and references[0] in named:
                keys.append((t, named[references[0]], {}))
            else:
                keys.append((t, None, _read_state(segment, references, pair_at, pairs)))
        motions[_label_name(label)] = Motion(_label_name(label), keys, ease)
    couplings = {}
    held_couplings = top.FindChild(6, False)
    for label in ([] if held_couplings.IsNull() else _children_of(held_couplings)):
        coupling = _read_couplers(_label_name(label), label, pair_at, pairs)
        if coupling is not None:
            couplings[coupling.name] = coupling
    return Mechanism(_label_name(top), links, ground, pairs, as_built, configurations, [], motions, couplings)


# --- what the page reads -------------------------------------------------------------------


def _json_value(values: tuple[float, ...] | list[float]) -> Any:
    return float(values[0]) if len(values) == 1 else [float(value) for value in values]


def _tree(mechanism: Mechanism) -> tuple[dict[int, int], list[str] | None]:
    """Each link reached from the ground, by the pair that reaches it, and a loop's pairs where
    the pairs close one."""
    reached: dict[int, int] = {mechanism.ground: -1}
    via: dict[int, int | None] = {mechanism.ground: None}
    queue = [mechanism.ground]
    loop = None
    used: set[int] = set()
    while queue:
        link = queue.pop(0)
        for at, pair in enumerate(mechanism.pairs):
            if at in used or link not in pair.links or pair.links[0] == pair.links[1]:
                continue
            used.add(at)
            other = pair.links[1] if pair.links[0] == link else pair.links[0]
            if other in reached:
                if loop is None:
                    loop = _loop(mechanism, via, link, other, at)
                continue
            reached[other] = at
            via[other] = at
            queue.append(other)
    return reached, loop


def _loop(mechanism: Mechanism, via: dict, a: int, b: int, closing: int) -> list[str]:
    def chain(link: int) -> list[int]:
        found = []
        while via.get(link) is not None:
            found.append(via[link])
            pair = mechanism.pairs[via[link]]
            link = pair.links[0] if pair.links[1] == link else pair.links[1]
        return found

    left, right = chain(a), chain(b)
    while left and right and left[-1] == right[-1]:
        left.pop()
        right.pop()
    return [mechanism.pairs[at].label for at in [*left, closing, *reversed(right)]]


def block(mechanism: Mechanism, instance_paths: list[tuple[int, ...]],
          world: Callable[[tuple[int, ...]], list[float]]) -> dict[str, Any]:
    """The structure's ``kinematics``: what a page needs to pose the document's instances.
    ``world(path)`` is an occurrence's placement as built (4x4, column-major)."""
    owner: dict[tuple[int, ...], int] = {path: at for at, link in enumerate(mechanism.links) for path in link.members}
    members: list[list[int]] = [[] for _ in mechanism.links]
    for index, path in enumerate(instance_paths if mechanism.links else ()):
        # The deepest link holding the instance; none, the ground.
        found = mechanism.ground
        for depth in range(len(path), -1, -1):
            if path[:depth] in owner:
                found = owner[path[:depth]]
                break
        members[found].append(index)
    _reached, loop = _tree(mechanism)
    pairs = []
    for pair in mechanism.pairs:
        pairs.append({"label": pair.label, "type": pair.kind, "links": list(pair.links),
                      "frames": [_column(frame_matrix(frame)) for frame in pair.frames] if pair.frames else None,
                      "limits": [list(limits) for limits in pair.limits],
                      "units": [unit for unit, *_names in KINDS[pair.kind][1]]})
    links = [{"name": link.name, "instances": members[at],
              "matrix": world(link.members[0]) if link.members else _column(np.eye(4))}
             for at, link in enumerate(mechanism.links)]
    warnings = list(mechanism.warnings)
    if loop:
        warnings.append(f"pairs {', '.join(loop)} close a loop, which has no pose without a solver: posing them is "
                        "refused")
    return {"schema": SCHEMA, "name": mechanism.name, "ground": mechanism.ground, "links": links, "pairs": pairs,
            "asBuilt": {label: _json_value(values) for label, values in mechanism.as_built.items()},
            "configurations": {name: {label: _json_value(values) for label, values in values_.items()}
                               for name, values_ in mechanism.configurations.items()},
            "couplings": {name: _coupling_json(coupling, mechanism.pairs, mechanism.as_built)
                          for name, coupling in mechanism.couplings.items()},
            "motions": {name: _motion_json(motion) for name, motion in mechanism.motions.items()},
            "loop": loop, "warnings": warnings}


def _motion_json(motion: Motion) -> dict[str, Any]:
    keys = [{"t": t, "configuration": configuration} if configuration is not None
            else {"t": t, "values": {label: _json_value(value) for label, value in values.items()}}
            for t, configuration, values in motion.keys]
    return {"duration": motion.duration, "ease": motion.ease, "keys": keys}



# --- motions over time -----------------------------------------------------------------------


class Timeline:
    """A motion of the structure's ``kinematics`` over time: ``values(t)`` the pair values
    at ``t`` seconds of its clip, every pair the motion does not move as built. A clip is the
    motion's duration, once; ``breaks`` are the times its keys fall at, where its speed may
    jump."""

    def __init__(self, kinematics: dict[str, Any], name: str) -> None:
        motions = kinematics.get("motions") or {}
        if name not in motions:
            raise KinematicsError(f"the document has no motion {name!r}; its motions: "
                                  f"{', '.join(sorted(motions)) or 'none'}")
        entry = motions[name]
        self.kinematics, self.name = kinematics, name
        self.ease = entry["ease"]
        keys = entry["keys"]
        self.times = np.array([float(key["t"]) for key in keys])
        self.duration = self.period = float(self.times[-1])
        configurations = kinematics.get("configurations") or {}
        moving: set[str] = set()
        poses = []
        for key in keys:
            if "configuration" in key:
                moving |= set(configurations[key["configuration"]])
                poses.append(resolve(kinematics, key["configuration"])[0])
            else:
                moving |= set(key["values"])
                poses.append(resolve(kinematics, key["values"], own=True)[0])
        self.labels = sorted(moving)
        self.sizes = [len(poses[0][label]) for label in self.labels]
        self.table = np.array([[value for label in self.labels for value in pose[label]] for pose in poses],
                              dtype=float).reshape(len(poses), sum(self.sizes))
        pairs = _block_pairs(kinematics)
        limits = [limit for label in self.labels for limit in (pairs[label].get("limits") or ())]
        self.lower = np.array([-math.inf if low is None else low for low, _high in limits], dtype=float)
        self.upper = np.array([math.inf if high is None else high for _low, high in limits], dtype=float)

    def joints(self, t: float) -> dict[str, tuple[float, ...]]:
        flat = np.clip(_interpolated(self.times, self.table, self.ease, t), self.lower, self.upper)
        found, at = {}, 0
        for label, size in zip(self.labels, self.sizes):
            found[label] = tuple(float(value) for value in flat[at:at + size])
            at += size
        return found

    def values(self, t: float) -> dict[str, tuple[float, ...]]:
        return resolve(self.kinematics, self.joints(t), own=True)[0]

    @property
    def breaks(self) -> list[float]:
        return [float(t) for t in self.times]


# --- poses -------------------------------------------------------------------------------


def _block_pairs(kinematics: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {pair["label"]: pair for pair in kinematics["pairs"]}


def _as_tuple(value: Any) -> tuple[float, ...]:
    return (float(value),) if isinstance(value, (int, float)) else tuple(float(item) for item in value)


def _block_checked(pair: dict[str, Any], value: Any, where: str) -> tuple[float, ...]:
    as_pair = Pair(pair["label"], pair["type"], tuple(pair["links"]), None,
                   tuple(tuple(limit) for limit in pair.get("limits") or ()))
    return _checked(as_pair, value, where)


def resolve(kinematics: dict[str, Any] | None, pose: Any, *,
            own: bool = False) -> tuple[dict[str, tuple[float, ...]], str | None]:
    """The values a pose sets every pair to, and the configuration it names: ``pose`` is
    None (as built), a configuration's name, or ``{joint label or coupling name: value}``
    (the rest as built; a coupling at ``c`` puts each of its joints at its as-built values
    plus its ratio times ``c``). An unknown name or joint, a value out of range, a coupling's
    joint set alone and a coupling set with one of its joints are refused by name. ``own``: the
    values are the document's own (a motion's keys), which set a coupling's joints."""
    if kinematics is None:
        if pose is None:
            return {}, None
        raise KinematicsError("the document has no joints to pose")
    as_built = {label: _as_tuple(value) for label, value in kinematics["asBuilt"].items()}
    values = dict(as_built)
    pairs = _block_pairs(kinematics)
    couplings = kinematics.get("couplings") or {}
    locked = _locked(couplings)
    loop = kinematics.get("loop") or ()
    named = None
    if isinstance(pose, str):
        configurations = kinematics.get("configurations") or {}
        if pose not in configurations:
            known = ", ".join(sorted(configurations)) or "none"
            raise KinematicsError(f"the document has no configuration {pose!r}; its configurations: {known}")
        named, given, where = pose, configurations[pose], f"configuration {pose!r}"
    elif isinstance(pose, dict):
        given, where = pose, "the pose"
    elif pose is None:
        given, where = {}, ""
    else:
        raise KinematicsError("a pose is a configuration's name or an object of joint values")

    def unposable(label: str) -> str | None:
        """Why the pair cannot be posed, or None."""
        if label in loop:
            return f"pairs {', '.join(loop)} close a loop, which has no pose without a solver"
        return None

    controls = {}
    for label, value in given.items():
        pair = pairs.get(label)
        if pair is None and label in couplings:
            controls[label] = value
            continue
        if pair is None:
            movable = ", ".join(sorted(pairs)) or "none"
            raise KinematicsError(f"{where} names no joint {label!r}; the document's joints: {movable}"
                                  + (f"; its couplings: {', '.join(sorted(couplings))}" if couplings else ""))
        why = unposable(label)
        if why:
            raise KinematicsError(f"{where}: joint {label!r} cannot be posed: {why}")
        if label in locked and not named and not own:
            raise KinematicsError(f"{where}: joint {label!r} moves only with its coupling {locked[label]!r}; "
                                  f"set {locked[label]!r}")
        values[label] = _block_checked(pair, value, where)
    for name in controls:
        for label, _index, _ratio in couplings[name]["terms"]:
            if label in given:
                raise KinematicsError(f"{where} sets coupling {name!r} and its joint {label!r}: set one of them")
            why = unposable(label)
            if why:
                raise KinematicsError(f"{where}: coupling {name!r} cannot be posed: its joint {label!r} cannot be: "
                                      f"{why}")
    values.update(_coupled(controls, couplings, as_built,
                           lambda label, row, at: _block_checked(pairs[label], row, at), where))
    return values, named


def link_worlds(kinematics: dict[str, Any], values: dict[str, tuple[float, ...]]) -> list[np.ndarray]:
    """Each link's placement at ``values``: the ground where it is, every other link by its
    pairs from the ground down (a pair that closes a loop is not followed; a pair with no value
    holds its links as built)."""
    return LinkWorlds(kinematics)(values)


class LinkWorlds:
    """``link_worlds`` of one kinematics, asked again and again (a motion's every sample): its
    frames, their inverses and the order its pairs are followed in are worked out once, so a call
    is each pair's motion and the products along the chain, the same arithmetic in the same order."""

    def __init__(self, kinematics: dict[str, Any]) -> None:
        links = kinematics["links"]
        self.count = len(links)
        self.ground = kinematics.get("ground")
        self.built = [_from_column(link["matrix"]) for link in links]
        self.pairs = [pair for pair in kinematics["pairs"] if pair.get("frames")]
        self.eye = np.eye(4)
        # Per pair: its frames (item_1, item_2) and their inverses, with a value and without one
        # (the two links as they stand: the second's placement as built over the first's).
        self.posed: list[tuple[np.ndarray, ...]] = []
        self.held: list[tuple[np.ndarray, ...]] = []
        for pair in self.pairs:
            first, second = pair["links"]
            item_1, item_2 = (_from_column(frame) for frame in pair["frames"])
            self.posed.append((item_1, np.linalg.inv(item_2), item_2, np.linalg.inv(item_1)))
            item_1, item_2 = np.linalg.inv(self.built[first]), np.linalg.inv(self.built[second])
            self.held.append((item_1, np.linalg.inv(item_2), item_2, np.linalg.inv(item_1)))
        self.orders: dict[frozenset, list[tuple[int, bool, bool]]] = {}

    def _order(self, valued: frozenset) -> list[tuple[int, bool, bool]]:
        """The pairs in the order ``link_worlds`` follows them, given which carry a value: each
        ``(pair, forward, valued)``, forward from its first link to its second."""
        found = [False] * self.count
        found[self.ground] = True
        pending = list(range(len(self.pairs)))
        steps: list[tuple[int, bool, bool]] = []
        progress = True
        while pending and progress:
            progress = False
            for at in list(pending):
                first, second = self.pairs[at]["links"]
                if found[first] and not found[second]:
                    steps.append((at, True, self.pairs[at]["label"] in valued))
                    found[second] = True
                elif found[second] and not found[first]:
                    steps.append((at, False, self.pairs[at]["label"] in valued))
                    found[first] = True
                elif not found[first]:
                    continue
                pending.remove(at)
                progress = True
        return steps

    def __call__(self, values: dict[str, tuple[float, ...]]) -> list[np.ndarray]:
        if not self.count:
            return []
        valued = frozenset(pair["label"] for pair in self.pairs if pair["label"] in values)
        steps = self.orders.get(valued)
        if steps is None:
            steps = self.orders[valued] = self._order(valued)
        found: list[np.ndarray | None] = [None] * self.count
        found[self.ground] = self.built[self.ground].copy()
        for at, forward, posed in steps:
            pair = self.pairs[at]
            first, second = pair["links"]
            item_1, unitem_2, item_2, unitem_1 = (self.posed if posed else self.held)[at]
            moved = pair_motion(pair["type"], values[pair["label"]]) if posed else self.eye
            if forward:
                found[second] = found[first] @ item_1 @ moved @ unitem_2
            else:
                found[first] = found[second] @ item_2 @ np.linalg.inv(moved) @ unitem_1
        return [matrix if matrix is not None else self.built[at].copy() for at, matrix in enumerate(found)]


def posed_instances(structure: dict[str, Any], values: dict[str, tuple[float, ...]]) -> list[list[float]]:
    """Every instance's world matrix (column-major) with the mechanism at ``values``."""
    kinematics = structure["kinematics"]
    reference = kinematics.get("pose", {}).get("values") or kinematics["asBuilt"]
    at = link_worlds(kinematics, values)
    rest = link_worlds(kinematics, {label: _as_tuple(value) for label, value in reference.items()})
    matrices = [list(instance["matrix"]) for instance in structure["instances"]]
    for link, (now, then) in enumerate(zip(at, rest)):
        delta = now @ np.linalg.inv(then)
        if np.allclose(delta, np.eye(4), rtol=0, atol=1e-12):
            continue
        for index in kinematics["links"][link]["instances"]:
            matrices[index] = _column(delta @ _from_column(matrices[index]))
    return matrices


def posed_structure(structure: dict[str, Any], pose: Any) -> dict[str, Any]:
    """The structure with its instances where ``pose`` places them, its kinematics saying
    which pose that is (``pose``: the values and the configuration named)."""
    kinematics = structure.get("kinematics")
    values, named = resolve(kinematics, pose)
    if kinematics is None:
        return structure
    matrices = posed_instances(structure, values)
    found = dict(structure)
    found["instances"] = [{**instance, "matrix": matrix} for instance, matrix in zip(structure["instances"], matrices)]
    found["kinematics"] = {**kinematics, "pose": {"values": {label: _json_value(value) for label, value in values.items()},
                                                  "configuration": named}}
    return found
