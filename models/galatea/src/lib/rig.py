"""The mechanism, written on the assembled links: joints, couplings, named poses, motions.

Every joint is a build123d `RevoluteJoint` on the parent link's group and a `RigidJoint`
of the same label on the child's, both at the joint's place in the world at the zero
pose; the server pairs them by label.
"""

import build123d as bd
from cad.build123d import configuration_sequence, gear_pair, mechanism_state

from . import kin, show
from .poses import MOTIONS, POSES


def revolute(label, parent, child, origin, direction, limits):
    axis = bd.Axis(tuple(origin), tuple(direction))
    bd.RevoluteJoint(label, parent, axis=axis, angular_range=tuple(limits))
    bd.RigidJoint(label, child, bd.Plane(origin=axis.position, z_dir=axis.direction).location)


def articulate(nodes):
    """Write every joint on the link groups in `nodes` (link name -> group)."""
    for label, (parent, child, origin, direction, limits) in kin.all_joints().items():
        revolute(label, nodes[parent], nodes[child], origin, direction, limits)


def couple(robot):
    """The couplings: the knee and ankle linkages, the fingers' tendons."""
    for name, ratios in kin.couplings().items():
        gear_pair(robot, name, **ratios)
    return robot


def animate(robot):
    """Mechanism states and configuration sequences on the assembled, coupled robot."""
    for name, pose in POSES.items():
        mechanism_state(robot, name, **pose)
    for name, waypoints, ease in MOTIONS:
        configuration_sequence(robot, name, waypoints, ease=ease)
    return show.explode(robot)                       # and, for its GLB alone, the exploded view


def location(transform):
    """A `kin` transform as a build123d Location."""
    r, p = transform
    return bd.Plane(origin=p, x_dir=(r[0][0], r[1][0], r[2][0]), z_dir=(r[0][2], r[1][2], r[2][2])).location
