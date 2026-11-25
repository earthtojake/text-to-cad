"""Assembly kit: finished parts, placed prototypes, frames, groups and the left/right mirror.

Every unique part is built where it stands, in world coordinates, on the robot's LEFT
side. A prototype (a screw, an actuator housing) is built once in its own frame,
symmetric about its local YZ plane, and placed many times with `inst`; `mirror_tree`
then makes the right side: unique parts are mirrored, prototypes are placed again at
the mirrored placement, so both sides share one prototype.
"""

import build123d as bd

from .finish import apply


def frame(origin, z_dir=(0.0, 0.0, 1.0), x_dir=None):
    """A placement whose local Z runs along `z_dir` and whose local X is `x_dir` (made
    perpendicular to Z), or a stable default: local Y up for a horizontal axis."""
    z = bd.Vector(*z_dir).normalized()
    if x_dir is None:
        ref = bd.Vector(0, 0, 1) if abs(z.Z) < 0.9 else bd.Vector(1, 0, 0)
        x = ref.cross(z).normalized()
    else:
        x = bd.Vector(*x_dir)
        x = (x - z * x.dot(z)).normalized()
    return bd.Plane(origin=tuple(origin), x_dir=(x.X, x.Y, x.Z), z_dir=(z.X, z.Y, z.Z)).location


def part(shape, label, finish):
    """A unique part: labelled and finished, standing where it was built."""
    shape.label = label
    return apply(shape, finish)


def proto(shape, finish, stood=None):
    """A prototype to place with `inst`: finished, and marked as one part for both sides of the robot.
    Its frame is symmetric about its local YZ plane, in what matters to its neighbours (a screw wholly,
    a drive in its mounting holes). `stood` is the location the shape already carries inside that
    frame (a maker's file stood in an actuator's frame), which a mirrored placement has to keep."""
    apply(shape, finish)
    shape._sym = True
    shape._stood = stood
    return shape


def inst(prototype, loc, label):
    """One placement of a prototype; it shares the prototype's shape."""
    placed = loc * prototype
    placed.label = label
    return placed


def _flatten(items):
    for item in items:
        if item is None:
            continue
        if isinstance(item, (list, tuple)):
            yield from _flatten(item)
        else:
            yield item


def group(label, *children):
    """An assembly node: a labelled compound of parts and sub-groups (lists are flattened)."""
    return bd.Compound(children=list(_flatten(children)), label=label)


def mirror_loc(loc):
    """The placement that puts a YZ-symmetric prototype where the mirror image of `loc` puts it."""
    plane = bd.Plane(loc)
    o, x, z = plane.origin, plane.x_dir, plane.z_dir
    return bd.Plane(origin=(-o.X, o.Y, o.Z), x_dir=(x.X, -x.Y, -x.Z), z_dir=(-z.X, z.Y, z.Z)).location


def mirror_tree(node, label=None):
    """The right-hand twin of a left-hand tree, mirrored in the world YZ plane."""
    if node.children:
        return bd.Compound(children=[mirror_tree(child) for child in node.children], label=label or node.label)
    if getattr(node, "_sym", False):
        stood = getattr(node, "_stood", None)
        if stood is None:
            twin = node.located(mirror_loc(node.location))
        else:                                          # mirror the frame the shape stands in, then stand it there again
            twin = node.located(mirror_loc(node.location * stood.inverse()) * stood)
    else:
        twin = bd.mirror(node, about=bd.Plane.YZ)
        if node.material is not None:
            twin.material = node.material
    twin.label = label or node.label
    return twin


def side_label(side, name):
    return f"{side}_{name}"
