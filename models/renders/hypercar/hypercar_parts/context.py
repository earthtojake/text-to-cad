"""Shared helpers every part module uses.

Keeps the part modules short and makes sure everyone builds groups the same
way, so the assembly tree and the explode grouping stay predictable.
"""

from __future__ import annotations

from build123d import Compound, Location, Plane, Pos, Rot

from hypercar_parts.palette import srgb, style  # noqa: F401  (re-export)


def group(label, children):
    """A labelled sub-assembly node.

    NOTE: colour on a group is ignored by the render package -- only leaves
    carry colour -- so always ``style()`` the leaves, never the group.
    """
    kids = [c for c in children if c is not None]
    if not kids:
        raise RuntimeError(f"group {label!r} has no children")
    return Compound(children=kids, label=label)


def mirror_pair(build_one, label_base, sides=(1, -1)):
    """Build the same part for both sides.

    ``build_one(side)`` must return a FRESH shape each call: build123d
    ``children=`` reparents, so the same object cannot live in two compounds.
    """
    out = []
    for side in sides:
        shape = build_one(side)
        name = "left" if side > 0 else "right"
        if isinstance(shape, Compound) and shape.children:
            shape.label = f"{label_base}:{name}"
        else:
            shape.label = f"{label_base}:{name}"
        out.append(shape)
    return out


def place(shape, x=0.0, y=0.0, z=0.0, rx=0.0, ry=0.0, rz=0.0):
    return Location((x, y, z), (rx, ry, rz)) * shape
