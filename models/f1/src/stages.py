"""The car's build stages: each a `@memo` function building a group of children.

A stage is a group of the car's children that share builder code, and the groups
that share a builder's cache must be one stage: the corners' `lib/wheels.py`
builds each axle's left corner once and mirrors it for the right, and the
sidepods' `lib/sidepods.py` its left panel. A stage returns its children by
name; `f1.py` calls each in its body, and an edit that does not reach a stage's
code replays it from the worker's memory. `power_unit`, `drivetrain`,
`suspension_rear` and `details` are stages of one child, marked in their own files.
"""

from cadgen import memo

from airbox import airbox
from beam_wing import beam_wing
from cockpit import cockpit
from cooling import cooling
from corner_fl import corner_fl
from corner_fr import corner_fr
from corner_rl import corner_rl
from corner_rr import corner_rr
from diffuser import diffuser
from drs_actuator import drs_actuator
from drs_flap import drs_flap
from engine_cover import engine_cover
from floor import floor
from front_wing import front_wing
from halo import halo
from monocoque import monocoque
from nose import nose
from rear_wing import rear_wing
from sidepod_left import sidepod_left
from sidepod_right import sidepod_right
from steering_rack import steering_rack
from suspension_front import suspension_front
from track_rod_left import track_rod_left
from track_rod_right import track_rod_right


@memo
def front_end():
    parts = {"front_wing": front_wing(), "nose": nose()}
    return parts


@memo
def survival_cell():
    parts = {"monocoque": monocoque(), "halo": halo(), "cockpit": cockpit()}
    return parts


@memo
def sidepods():
    parts = {"sidepod_left": sidepod_left(), "sidepod_right": sidepod_right(), "cooling": cooling()}
    return parts


@memo
def engine_bodywork():
    parts = {"engine_cover": engine_cover(), "airbox": airbox()}
    return parts


@memo
def underbody():
    parts = {"floor": floor(), "diffuser": diffuser()}
    return parts


@memo
def rear_aero():
    parts = {"rear_wing": rear_wing(), "drs_flap": drs_flap(), "drs_actuator": drs_actuator(),
             "beam_wing": beam_wing()}
    return parts


@memo
def front_suspension():
    parts = {"suspension_front": suspension_front(), "steering_rack": steering_rack(),
             "track_rod_left": track_rod_left(), "track_rod_right": track_rod_right()}
    return parts


@memo
def corners():
    parts = {"corner_fl": corner_fl(), "corner_fr": corner_fr(), "corner_rl": corner_rl(),
             "corner_rr": corner_rr()}
    return parts
