"""What a part declares for a simulator, beside its material: its collision, its named frames, whether it
is a body of its own, what it does not collide with, how its joints are driven, what it weighs, how
it grips, whether it floats and what its link is named.

``collision(part, kind)`` says what a simulator collides the part as (``description.COLLISIONS``):
the mesh itself (the default a description is made with), a ``box``, a ``sphere``, a ``cylinder``
or a ``capsule`` the kernel fits to the part, ``decomposed`` (convex hulls CoACD cuts the part's mesh
into, the coacd integration's, its visual whole: ``max_hulls``, 16 by default, and ``threshold`` bound it), or
``none``. On an assembly it is every part's below it that declares none, as a material is, its
options with it. ``frame(part, name, location)`` names a frame on a part --
a tool tip, a camera mount, a sensor -- for a writer's sites or fixed frames.

``body(part, name=None)`` keeps a part a body of its own, fixed to the link it would have merged
into (a camera mount, a fingertip a simulator addresses): its mass, visuals, collision and frames go
with it. ``exclude(a, b)`` says two parts, or what they are part of, never collide (a hull pair that
touches at rest); ``b`` is a part, an assembly or the label of one, which names every part at or
below it. ``limits(assembly, joint, effort=, velocity=)`` bounds the drive of every revolute or
linear joint of that label on the assembly or below it: its effort in N*m (a revolute joint) or N
(a linear one), its speed in rad/s or m/s, SI as the description is. ISO 10303-105 names which
values a pair is driven in (``actuated_kinematic_pair``) and no bound on the drive, so the limits
are a simulator's, as a collision is, and no fact of the mechanism (the package's law 13). Beside its
bounds, ``limits`` gives the joint's own dynamics, each a fact of the hardware a simulator reads off
the joint: ``armature`` (the rotor's inertia reflected through the gearbox, kg*m^2 for a turn, kg for
a slide), ``damping`` (N*m*s/rad, N*s/m) and ``friction`` (the drive's dry friction, N*m or N:
MuJoCo's ``frictionloss``). An actuator, its gains and the contact's tuning are the scene's.

**Mass.** ``mass(shape, grams)`` says what a part or an assembly weighs, all of it: its solids keep
the density ratios their materials give them and are scaled alike until they, with every point mass
below it, weigh ``grams``, so the centre of mass and the shape of the inertia come from the geometry
and the total from the scale. Where no part below it has a density, every solid is taken at one.
Declarations nest: an inner one (on a part or an assembly below) fixes what is below it, and an outer
one scales only the solids no inner one holds, to make up its total less what the inner ones and the
point masses outside them weigh; an outer total that leaves its own solids nothing (or less), or that
the inner ones do not make up where it holds no solid of its own, is refused when the robot is
described. ``point_mass(part, grams, at, name=, inertia=)`` is a lump the CAD leaves out -- a motor
inside a filled housing -- at ``at`` in the part's own frame (a frame's frame), with no inertia of its
own unless ``inertia`` gives its diagonal (kg*m^2, in ``at``'s axes); it goes into the part's link
exactly, the parallel-axis theorem moving it to the link's centre. A point mass counts towards every
``mass`` total above it: the total is what the hardware weighs, the lumps are fixed, and the solids
are scaled to make up the rest.

**Friction.** ``friction(shape, coefficient)`` is the contact friction of a part's surface -- a
rubber pad's, an aluminium finger's -- set where its material is and inherited as one is, the part's
own over its assembly's: a sliding coefficient, or MuJoCo's three (sliding, torsional, rolling). It
is the surface's, which the material's library does not carry, so it is declared beside it. No
material's friction is assumed: where none is declared, a simulator uses its own default.

**The base and the links' names.** ``free(shape)`` says that what ``shape`` holds is not bolted to
the world: the link a robot description hangs from the world that holds a part at or below it -- on
the top assembly, the robot's base (its ground link) -- floats (a humanoid, a quadruped, a mobile base,
a part dropped on a table). Bolted is the default. It is a simulator's, as ``limits`` is: AP242's
mechanism has a ground and no word for a ground that floats. ``link(shape, name)`` names the link the
parts at or below ``shape`` make, instead of its first part's (or a jointed assembly's) label; a
declaration on a part or an assembly below names its own links over it. Both are declared on a node of
the tree and kept, as ``mass`` is, on every part below it with how many levels above the part it was
declared, so the document carries them on the parts' prototypes and gives them back to the node.

Each is an attribute of the object, as a material is, and travels as build123d moves it: a copy,
``moved`` and ``located`` keep them. ``limits`` is kept on the node that holds the joint -- a part, or
an assembly (a link of several parts), which the document keeps on every part below it with how many
levels above the part it is, as ``mass`` -- so it is declared after the joint is made. A frame is given in the part's OWN frame, the one its geometry
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

__all__ = ["body", "collision", "exclude", "frame", "free", "friction", "limits", "link", "mass", "point_mass"]

# The attributes the declarations are kept in on a shape (``document.collect`` reads them).
COLLISION = "_collision"
DECOMPOSITION = "_decomposition"  # a decomposed collision's options: {"maxHulls"?, "threshold"?}, those given
FRAMES = "_frames"
BODY = "_body"  # the body's name, "" for the part's own
EXCLUDE = "_exclude"  # the labels it does not collide with, sorted
DRIVES = "_drives"  # {joint label: {"effort": ..., "velocity": ..., ...}}, the keys it declares (``DRIVE``)
MASS = "_mass"  # grams, the part's or the assembly's whole
POINTS = "_points"  # {name: (grams, Location in the part's own frame, (ixx, iyy, izz) kg*m^2 or None)}
FRICTION = "_friction"  # (sliding,) or (sliding, torsional, rolling)
FREE = "_free"  # True: what the node holds floats (``free``)
LINK = "_link"  # the name of the link the node's parts make (``link``)
#: What ``limits`` declares of a joint, by its keyword: the drive's bounds, then the joint's dynamics.
DRIVE = ("effort", "velocity", "armature", "damping", "friction")
# The joints a drive bounds, by build123d's class, and the ones it refuses: a bound of one value.
DRIVEN = ("RevoluteJoint", "LinearJoint")
UNDRIVEN = ("CylindricalJoint", "BallJoint")


def _shape(part: Any, said: str) -> Any:
    import build123d as bd

    if not isinstance(part, bd.Shape):
        raise TypeError(f"{said}: a build123d shape, not {type(part).__name__}")
    return part


#: The most hulls a decomposed collision is cut into where it gives no ``max_hulls``: onshape-to-robot's default,
#: which keeps a simulator's collision checks cheap (MuJoCo tests each hull as a geom of its own).
MAX_HULLS = 16
#: The concavity threshold CoACD takes: its own range (its default, 0.05, where none is given).
THRESHOLD = (0.01, 1.0)


def collision(part: Any, kind: str, *, max_hulls: int | None = MAX_HULLS, threshold: float | None = None) -> Any:
    """Say what a simulator collides ``part`` as: one of ``mesh``, ``box``, ``sphere``,
    ``cylinder``, ``capsule``, ``decomposed`` or ``none`` (the primitives fitted by the kernel to the
    part's oriented bounding box, a cylinder's and a capsule's axis its longest side). ``decomposed``
    is a set of convex hulls cut from the part's mesh by CoACD (the coacd integration, ``cad[coacd]``,
    where the robot is described), its visual left whole: ``max_hulls`` at most that many (CoACD's
    ``max_convex_hull``; ``MAX_HULLS``, 16, by default, None for no limit), ``threshold`` its concavity
    threshold, 0.01 to 1, a smaller one cutting finer (CoACD's 0.05 where None); no other kind takes
    either (``max_hulls`` left at its default is none given). On an assembly, every part below it that
    declares none. Returns ``part``."""
    _shape(part, "collision")
    if kind not in COLLISIONS:
        raise ValueError(f"collision {kind!r} is none of {', '.join(COLLISIONS)}")
    options: dict[str, Any] = {}
    if max_hulls == MAX_HULLS and kind != "decomposed" and not isinstance(max_hulls, bool):
        max_hulls = None  # the default bounds a decomposed collision alone: another kind is given none
    if max_hulls is not None:
        if isinstance(max_hulls, bool) or not isinstance(max_hulls, int) or max_hulls < 1:
            raise ValueError(f"max_hulls is a whole number of hulls, at least 1, not {max_hulls!r}")
        options["maxHulls"] = int(max_hulls)
    if threshold is not None:
        if (isinstance(threshold, bool) or not isinstance(threshold, (int, float))
                or not THRESHOLD[0] <= threshold <= THRESHOLD[1]):
            raise ValueError(f"threshold is CoACD's concavity threshold, {THRESHOLD[0]:g} to {THRESHOLD[1]:g}, "
                             f"not {threshold!r}")
        options["threshold"] = float(threshold)
    if options and kind != "decomposed":
        given = " or ".join(name for name, value in (("max_hulls", max_hulls), ("threshold", threshold))
                            if value is not None)
        raise ValueError(f"collision {kind!r} takes no {given}: they bound a decomposed one")
    part.__dict__[COLLISION] = kind
    if options:
        part.__dict__[DECOMPOSITION] = options
    else:
        part.__dict__.pop(DECOMPOSITION, None)
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
    """Say that ``a`` never collides with ``b``: each a part or an assembly (every part below it), or
    the label of one -- a part's label names its link too -- in either order, one of the two a shape:
    the declaration is kept on it, as every declaration is, and names the other by its label. A
    simulator that filters contacts by pair is told so (MJCF's ``<contact><exclude>``). Returns the
    shape that keeps it."""
    import build123d as bd

    if not isinstance(a, bd.Shape) and isinstance(b, bd.Shape):
        a, b = b, a  # the pair is either way round: the shape keeps it
    if not isinstance(a, bd.Shape):
        if isinstance(a, str) and isinstance(b, str):
            raise TypeError(f"exclude({a!r}, {b!r}): one of the two is the part or the assembly itself, which keeps "
                            f"the declaration, and the other may be its label: exclude(part, {b!r})")
        _shape(a, "exclude")
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


def _number(value: Any, said: str, *, zero: bool = False) -> float:
    """``value`` as a finite float above zero (or at it, where ``zero``), else refused as ``said``."""
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            or value < 0 or (value == 0 and not zero)):
        raise ValueError(f"{said} is a {'non-negative' if zero else 'positive'} number, not {value!r}")
    return float(value)


def limits(assembly: Any, joint: str, *, effort: float | None = None, velocity: float | None = None,
           armature: float | None = None, damping: float | None = None, friction: float | None = None) -> Any:
    """Bound the drive of every revolute or linear joint labelled ``joint`` on ``assembly`` or below
    it, and give its dynamics: ``effort`` in N*m for a revolute joint and N for a linear one,
    ``velocity`` in rad/s or m/s (URDF's ``<limit effort velocity>``, MJCF's
    ``actuatorfrcrange``; MJCF bounds no speed), each positive; ``armature``, the rotor's inertia
    reflected through its gearbox, in kg*m^2 or kg (MJCF's ``armature``; URDF has
    none), ``damping`` in N*m*s/rad or N*s/m and ``friction``, the drive's dry friction, in N*m or N
    (MJCF's ``damping`` and ``frictionloss``, URDF's ``<dynamics damping friction>``), each zero or more; each None where the model gives none. A cylindrical or
    a ball joint, of two and three values, is refused. A second declaration for one joint replaces
    the first. Declare it after the joint is made: it is kept on the part that holds it. Returns
    ``assembly``."""
    _shape(assembly, "limits")
    if not isinstance(joint, str) or not joint:
        raise ValueError(f"limits: a joint's label, a non-empty string, not {joint!r}")
    given = dict(zip(DRIVE, (effort, velocity, armature, damping, friction)))
    bounds = {key: _number(value, f"limits {joint!r}: {key}", zero=key not in ("effort", "velocity"))
              for key, value in given.items() if value is not None}
    if not bounds:
        raise ValueError(f"limits {joint!r}: give effort, velocity, armature, damping or friction")
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
        shape.__dict__[DRIVES] = {**(shape.__dict__.get(DRIVES) or {}), joint: dict(bounds)}
    return assembly


def mass(shape: Any, grams: float) -> Any:
    """Say that ``shape``, a part or an assembly, weighs ``grams`` in all, its point masses included:
    its solids keep their densities' ratios and are scaled alike to make up the rest (the module's
    **Mass**, where nested declarations are). A second declaration replaces the first. Returns
    ``shape``."""
    _shape(shape, "mass")
    shape.__dict__[MASS] = _number(grams, f"mass of {shape.label or 'the shape'}: grams")
    return shape


def point_mass(part: Any, grams: float, at: Any, *, name: str | None = None,
               inertia: tuple[float, float, float] | None = None) -> Any:
    """Add ``grams`` to ``part`` at ``at`` (a build123d ``Location`` or ``Plane``) in its own frame, the
    one its geometry is in before ``part.location``, as a frame is: a lump its solids leave out. It has
    no inertia of its own unless ``inertia`` gives its diagonal, ``(ixx, iyy, izz)`` in kg*m^2 about
    the point in ``at``'s axes. ``name`` tells several apart (``point1``, ``point2`` where None); a
    second of one name replaces the first. A part's, not an assembly's. Returns ``part``."""
    import build123d as bd

    _shape(part, "point_mass")
    held = dict(part.__dict__.get(POINTS) or {})
    if name is None:
        count = len(held) + 1
        while f"point{count}" in held:
            count += 1
        name = f"point{count}"
    if not isinstance(name, str) or not name:
        raise ValueError(f"a point mass's name is a non-empty string, not {name!r}")
    if _assembly(part):
        raise ValueError(f"point_mass {name!r}: {part.label or 'the shape'} is an assembly; put the point mass on "
                         "the part it is in")
    weight = _number(grams, f"point_mass {name!r}: grams")
    if isinstance(at, bd.Plane):
        at = bd.Location(at)
    elif not isinstance(at, bd.Location):
        raise TypeError(f"point_mass {name!r}: at is a build123d Location (Pos, Rot) or Plane, not "
                        f"{type(at).__name__}")
    moments = None
    if inertia is not None:
        if isinstance(inertia, (str, bytes)) or not hasattr(inertia, "__len__") or len(inertia) != 3:
            raise ValueError(f"point_mass {name!r}: inertia is (ixx, iyy, izz) in kg*m^2, not {inertia!r}")
        moments = tuple(_number(value, f"point_mass {name!r}: inertia", zero=True) for value in inertia)
        for index in range(3):
            if moments[index] > moments[(index + 1) % 3] + moments[(index + 2) % 3] * (1 + 1e-9):
                raise ValueError(f"point_mass {name!r}: inertia {moments!r} is no body's: each moment is at most "
                                 "the other two's sum")
    # A dict of its own each time, as a frame's: a copy of the part shares the one it held.
    part.__dict__[POINTS] = {**held, name: (weight, bd.Location(at.wrapped), moments)}
    return part


def free(shape: Any) -> Any:
    """Say that ``shape``, a part or an assembly, is not bolted to the world: the link a robot
    description hangs from the world that holds a part at or below it floats (MJCF's ``<freejoint>``;
    a URDF's root, which floats already). On the top assembly, the robot's base. Returns ``shape``."""
    _shape(shape, "free")
    shape.__dict__[FREE] = True
    return shape


def link(shape: Any, name: str) -> Any:
    """Name ``name`` the link the parts at or below ``shape`` make in a robot description, instead of
    its first part's label: one link, so ``shape``'s parts must all be one link's, and no other link may
    take the name (both refused when the robot is described). A part declared a body is named by its
    ``body`` declaration. A second declaration replaces the first. Returns ``shape``."""
    _shape(shape, "link")
    if not isinstance(name, str) or not name:
        raise ValueError(f"a link's name is a non-empty string, not {name!r}")
    shape.__dict__[LINK] = name
    return shape


def friction(shape: Any, coefficient: float | tuple[float, float, float]) -> Any:
    """Give ``shape``'s surface its contact friction: a sliding coefficient, or MuJoCo's three
    (sliding, torsional, rolling), each zero or more. On an assembly, every part below it that
    declares none, as a material is (the module's **Friction**). Returns ``shape``."""
    _shape(shape, "friction")
    said = f"friction of {shape.label or 'the shape'}"
    if isinstance(coefficient, (tuple, list)):
        if len(coefficient) != 3:
            raise ValueError(f"{said}: one coefficient, or three (sliding, torsional, rolling), not {coefficient!r}")
        values = tuple(_number(value, said, zero=True) for value in coefficient)
    else:
        values = (_number(coefficient, said, zero=True),)
    shape.__dict__[FRICTION] = values
    return shape
