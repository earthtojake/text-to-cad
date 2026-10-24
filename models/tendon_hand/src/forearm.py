"""The tendon hand's forearm: the open frame, its 96 guide mouths, the housing and
the actuator fasteners, alone and around the actual actuator pack.

Each model was its own script in `models/tendon_hand/src/`. `forearm_mount_system_review`
called the frame and guide-bank models, and `forearm_housing_context` read their STEP
and the fasteners'. Here the frame and the guide banks are `@memo` stages (about 40 s
of kernel work each, 3,100 and 5,300 calls), which every model that shows them places,
so a build makes each once. The housing and the fasteners (2.4 s and 0.9 s) are plain
functions: each model that shows them makes its own.
"""

import copy

from cadgen import memo, model

import build123d as bd

from lib.actuator_fasteners import actuator_fasteners
from lib.capstan import make_capstan, make_terminal_ferrule
from lib.forearm_frame import make_forearm_frame_bodies
from lib.forearm_guide_mounts import make_forearm_guide_mount_bodies
from lib.forearm_housing import forearm_housing_bodies
from lib.gearbox import make_gearbox_parts
from lib.layout import TENDONS
from lib.motor import make_motor_case, make_motor_endcap, make_motor_shaft
from lib.tension_cartridge import make_tension_cartridge


@memo
def forearm_frame():
    """The two native dark forearm frame bodies, in neutral assembly coordinates."""
    frame = bd.Compound(label="open_forearm_frame", children=make_forearm_frame_bodies())
    return frame


@memo
def forearm_guide_banks():
    """The 96 forearm guide mouths and their mounts."""
    banks = bd.Compound(label="96_forearm_guide_mouths", children=make_forearm_guide_mount_bodies())
    return banks


def forearm_housing():
    """The individually removable open side frames and wiring hardware."""
    return [s for s, *_ in forearm_housing_bodies()]


def fasteners():
    """Every assembled actuator and reaction-frame fastener occurrence."""
    return [p for p, frame, system, kind in actuator_fasteners()]


def _leaves(node):
    return [leaf for child in node.children for leaf in _leaves(child)] if node.children else [node]


@model
def forearm_frame_review():
    """Two native dark forearm frame bodies, in neutral assembly coordinates."""
    return forearm_frame()


@model
def forearm_guide_banks_review():
    """The 96 forearm guide mouths."""
    return forearm_guide_banks()


@model
def forearm_mount_system_review():
    """Open forearm chassis with every fixed forearm liner reaction mount."""
    return bd.Compound(label="open_forearm_frame_with_96_mouth_supports", children=[forearm_frame(), forearm_guide_banks()])


@model
def forearm_housing_review():
    """Individually removable open forearm side frames and wiring hardware."""
    return bd.Compound(label="forearm_open_housing_and_wiring_provisions", children=forearm_housing())


@model
def actuator_fasteners_review():
    """All assembled actuator and reaction-frame fastener occurrences."""
    return bd.Compound(label="all_actuator_and_frame_fasteners", children=fasteners())


@model
def forearm_housing_context():
    """Open housing around the actual actuator pack and forearm guide banks.

    The original read the mount system's and the fasteners' STEP for their bodies;
    here it places the frame and guide-bank stages the mount system shows (a placement
    of each body: the stages' own compounds keep theirs) and makes the fasteners."""
    parts = forearm_housing()
    parts += [copy.copy(s) for s in _leaves(forearm_frame()) + _leaves(forearm_guide_banks())]
    parts += fasteners()
    motor = [make_motor_case(), make_motor_endcap(), make_motor_shaft()]
    gear = make_gearbox_parts()
    cap = [make_capstan(), make_terminal_ferrule()]
    cartridge = make_tension_cartridge()
    for t in TENDONS:
        x, y, _ = t["actuator_center"]
        sign = t["sign"]
        turn = bd.Rot(0, 180 if sign < 0 else 0, 0)
        for i, p in enumerate(cartridge):
            s = bd.Pos(x, y, 0) * turn * p
            s.label = t["actuator"] + f"_context_cartridge_{i}"
            parts.append(s)
        for i, p in enumerate(motor + gear):
            s = bd.Pos(x, y, sign * 4) * turn * p
            s.label = t["actuator"] + f"_context_motor_gear_{i}"
            parts.append(s)
        for i, p in enumerate(cap):
            s = bd.Pos(x, y, sign * 4) * turn * bd.Pos(0, 0, 29) * p
            s.label = t["actuator"] + f"_context_capstan_{i}"
            parts.append(s)
    return bd.Compound(label="open_forearm_housing_actual_actuator_context", children=parts)


if __name__ == "__main__":
    forearm_frame_review()
    forearm_guide_banks_review()
    forearm_mount_system_review()
    forearm_housing_review()
    actuator_fasteners_review()
    forearm_housing_context()
