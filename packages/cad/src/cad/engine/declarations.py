"""What a part declares for a simulator, beside its material: its collision and its named frames.

``collision(part, kind)`` says what a simulator collides the part as (``description.COLLISIONS``):
the mesh itself (the default a description is made with), a ``box``, a ``sphere``, a ``cylinder``
or a ``capsule`` the kernel fits to the part, or ``none``. On an assembly it is every part's below
it that declares none, as a material is. ``frame(part, name, location)`` names a frame on a part --
a tool tip, a camera mount, a sensor -- for a writer's sites or fixed frames.

Both are attributes of the object, as a material is, and travel as build123d moves it: a copy,
``moved`` and ``located`` keep them. A frame is given in the part's OWN frame, the one its geometry
is in before its placement (``part.location`` not applied: ``bd.Box(240, 40, 50)`` is centred on
it), so it moves with the part however a joint or a placement moves it::

    arm = bd.Box(240, 40, 50, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    collision(arm, "capsule")
    frame(arm, "tool", bd.Pos(240, 0, 25))

The document carries both on the part's prototype (``document.collect``): a part that declares
another collision or other frames is a prototype of its own. Set them on finished parts, after the
last operation, as a material is.
"""

from __future__ import annotations

from typing import Any

from cad.engine.description import COLLISIONS

__all__ = ["collision", "frame"]

# The attributes the declarations are kept in on a shape (``document.collect`` reads them).
COLLISION = "_collision"
FRAMES = "_frames"


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
