"""Galatea posed: each named pose as a model of its own, standing on the ground.

The robot's mechanism holds the pelvis still, so a pose lifts or tilts the feet. Each
model here is the robot at one pose, moved as a whole until it stands: lowered, level,
onto its lowest sole point, or (for a pose that tips the pelvis) set down flat on one foot.
"""

from cad import model
from cad.build123d import posed

from galatea import assemble
from lib import kin
from lib.poses import POSES
from lib.rig import location


def standing(name, foot=None):
    """The robot posed and set on the ground. It keeps its joints and couplings, the pose its
    as-built state; the named poses and motions belong to `galatea`, whose zero they count from."""
    pose = POSES[name]
    transform = kin.stance(pose, foot) if foot else kin.settle(pose)
    return location(transform) * posed(assemble(), pose)


@model
def galatea_ready():
    return standing("ready")


@model
def galatea_stride():
    return standing("stride")


@model
def galatea_contrapposto():
    return standing("contrapposto")


@model
def galatea_reach():
    return standing("reach")


@model
def galatea_wave():
    return standing("wave")


@model
def galatea_present():
    return standing("present")


@model
def galatea_poise():
    return standing("poise")


@model
def galatea_crouch():
    return standing("crouch", foot="l_foot")


@model
def galatea_bow():
    return standing("bow", foot="l_foot")


if __name__ == "__main__":
    galatea_ready()
    galatea_stride()
    galatea_contrapposto()
    galatea_reach()
    galatea_wave()
    galatea_present()
    galatea_poise()
    galatea_crouch()
    galatea_bow()
