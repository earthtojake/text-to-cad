"""What a part declares for a simulator, beside its material: its collision, its named frames, whether it
is a body of its own, what it does not collide with, and how hard and fast its joints are driven.

``collision(part, kind)`` says what a simulator collides the part as (``description.COLLISIONS``):
the mesh itself (the default a description is made with), a ``box``, a ``sphere``, a ``cylinder``
or a ``capsule`` the kernel fits to the part, or ``none``. On an assembly it is every part's below
it that declares none, as a material is. ``frame(part, name, location)`` names a frame on a part --
a tool tip, a camera mount, a sensor -- for a writer's sites or fixed frames.

``body(part, name=None)`` keeps a part a body of its own, fixed to the link it would have merged
into (a camera mount, a fingertip a simulator addresses): its mass, visuals, collision and frames go
with it. ``exclude(a, b)`` says two parts, or what they are part of, never collide (a hull pair that
touches at rest); ``b`` is a part, an assembly or the label of one, which names every part at or
below it. ``limits(assembly, joint, effort=, velocity=)`` bounds the drive of every revolute or
linear joint of that label on the assembly or below it: its effort in N*m (a revolute joint) or N
(a linear one), its speed in rad/s or m/s, SI as the description is. ISO 10303-105 names which
values a pair is driven in (``actuated_kinematic_pair``) and no bound on the drive, so the limits
are a simulator's, as a collision is, and no fact of the mechanism (the package's law 13).

Each is an attribute of the object, as a material is, and travels as build123d moves it: a copy,
``moved`` and ``located`` keep them. ``limits`` is kept on the part that holds the joint, so it is
declared after the joint is made. A frame is given in the part's OWN frame, the one its geometry
is in before its placement (``part.location`` not applied: ``bd.Box(240, 40, 50)`` is centred on
it), so it moves with the part however a joint or a placement moves it::

    arm = bd.Box(240, 40, 50, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    collision(arm, "capsule")
    frame(arm, "tool", bd.Pos(240, 0, 25))

The document carries them on the part's prototype (``document.collect``): a part that declares
something else is a prototype of its own. Set them on finished parts, after the
last operation, as a material is.
"""

from __future__ import annotations

import math
from typing import Any

from cad.engine.description import COLLISIONS

__all__ = ["body", "collision", "exclude", "frame", "limits"]

# The attributes the declarations are kept in on a shape (``document.collect`` reads them).
COLLISION = "_collision"
FRAMES = "_frames"
BODY = "_body"  # the body's name, "" for the part's own
EXCLUDE = "_exclude"  # the labels it does not collide with, sorted
DRIVES = "_drives"  # {joint label: (effort, velocity)}, each None where not bounded
# The joints a drive bounds, by build123d's class, and the ones it refuses: a bound of one value.
DRIVEN = ("RevoluteJoint", "LinearJoint")
UNDRIVEN = ("CylindricalJoint", "BallJoint")


def _shape(part: Any, said: str) -> Any:
    import build123d as bd

    if not isinstance(part, bd.Shape):
        raise TypeError(f"{said}: a build123d shape, not {type(part).__name__}")
    return part


def collision(part: Any, kind: str) -> Any:
    """Say what a simulator collides ``part`` as: one of ``mesh``, ``box``, ``sphere``,
    ``cylinder``, ``capsule`` or ``none`` (the primitives fitted by the kernel to the part's
    oriented bounding box, a cylinder's and a capsule's axis its longest side). On an assembly,
    every part below it that declares none. Returns ``part``."""
    _shape(part, "collision")
    if kind not in COLLISIONS:
        raise ValueError(f"collision {kind!r} is none of {', '.join(COLLISIONS)}")
    part.__dict__[COLLISION] = kind
    return part


def frame(part: Any, name: str, location: Any) -> Any:
    """Name a frame on ``part``: ``location`` (a build123d ``Location`` -- ``Pos``, ``Rot`` -- or a
    ``Plane``) in the part's own frame, the one its geometry is in before ``part.location``. A
    second frame of one name replaces the first. A frame is a part's, not an assembly's: put it
    on the part it stands on. Returns ``part``."""
    import build123d as bd

    _shape(part, "frame")
    if not isinstance(name, str) or not name:
        raise ValueError(f"a frame's name is a non-empty string, not {name!r}")
    if part.__dict__.get("_NodeMixin__children"):
        raise ValueError(f"frame {name!r}: {part.label or 'the shape'} is an assembly; name the frame on the part it "
                         "stands on")
    if isinstance(location, bd.Plane):
        location = bd.Location(location)
    elif not isinstance(location, bd.Location):
        raise TypeError(f"frame {name!r}: a build123d Location (Pos, Rot) or Plane, not {type(location).__name__}")
    # A dict of its own each time: a copy of the part (``moved``) shares the one it held.
    part.__dict__[FRAMES] = {**(part.__dict__.get(FRAMES) or {}), name: bd.Location(location.wrapped)}
    return part


def _assembly(part: Any) -> bool:
    return bool(part.__dict__.get("_NodeMixin__children"))


def body(part: Any, name: str | None = None) -> Any:
    """Keep ``part`` a body of its own, rigidly fixed to the link it would have merged into, named
    ``name`` (the part's label where None): its mass, visuals, collision and frames go with it, not
    into that link's. A part that is all of its link is a body already. A part's, not an
    assembly's. Returns ``part``."""
    _shape(part, "body")
    if name is not None and (not isinstance(name, str) or not name):
        raise ValueError(f"a body's name is a non-empty string, not {name!r}")
    if _assembly(part):
        raise ValueError(f"body: {part.label or 'the shape'} is an assembly; declare the body on a part")
    part.__dict__[BODY] = name or ""
    return part


def exclude(a: Any, b: Any) -> Any:
    """Say that ``a`` never collides with ``b``: a part or an assembly (every part below it), and
    another, or the label of one -- a part's label names its link too. A simulator that filters
    contacts by pair is told so (MJCF's ``<contact><exclude>``). Returns ``a``."""
    _shape(a, "exclude")
    import build123d as bd

    if isinstance(b, bd.Shape):
        other = b.label
        if not isinstance(other, str) or not other:
            raise ValueError("exclude: the other part has no label, and the exclusion names it by its label")
    elif isinstance(b, str) and b:
        other = b
    else:
        raise TypeError(f"exclude: a build123d shape or a part's label, not {b!r}")
    if other == a.label:
        raise ValueError(f"exclude: {other!r} with itself; a body never collides with itself")
    a.__dict__[EXCLUDE] = tuple(sorted({*(a.__dict__.get(EXCLUDE) or ()), other}))
    return a


def _bound(value: Any, what: str, joint: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"limits {joint!r}: {what} is a positive number, not {value!r}")
    return float(value)


def limits(assembly: Any, joint: str, *, effort: float | None = None, velocity: float | None = None) -> Any:
    """Bound the drive of every revolute or linear joint labelled ``joint`` on ``assembly`` or below
    it: ``effort`` in N*m for a revolute joint and N for a linear one, ``velocity`` in rad/s or m/s,
    either None where it is not bounded (URDF's ``<limit effort velocity>``, SDFormat's, MJCF's
    ``actuatorfrcrange``; MJCF bounds no speed). A cylindrical or a ball joint, of two and three
    values, is refused. A second declaration for one joint replaces the first. Declare it after the
    joint is made: it is kept on the part that holds it. Returns ``assembly``."""
    _shape(assembly, "limits")
    if not isinstance(joint, str) or not joint:
        raise ValueError(f"limits: a joint's label, a non-empty string, not {joint!r}")
    bounds = (_bound(effort, "effort", joint), _bound(velocity, "velocity", joint))
    if bounds == (None, None):
        raise ValueError(f"limits {joint!r}: give effort, velocity or both")
    found = []
    pending = [assembly]
    while pending:
        shape = pending.pop(0)
        held = (shape.__dict__.get("joints") or {}).get(joint)
        kind = type(held).__name__
        if kind in UNDRIVEN:
            raise ValueError(f"limits {joint!r}: a {kind} moves two values or three, and a drive limit bounds one")
        if kind in DRIVEN:
            found.append(shape)
        pending.extend(shape.__dict__.get("_NodeMixin__children") or ())
    if not found:
        raise ValueError(f"limits: no revolute or linear joint {joint!r} on {assembly.label or 'the shape'} or "
                         "below it (declare the limits after the joint is made)")
    for shape in found:
        shape.__dict__[DRIVES] = {**(shape.__dict__.get(DRIVES) or {}), joint: bounds}
    return assembly
