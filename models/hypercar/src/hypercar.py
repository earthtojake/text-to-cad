"""Mid-engine hypercar -- full assembly.

Body panels are cut from one master surface (see ``lib/surfaces.py``), so
highlight lines cross every shutline without a kink and every panel gap is a
real constant-width gap.

Assembly tree is grouped BY SYSTEM — thirteen sibling models under ``src/``,
composed here by CALLING them — which is also the occurrence order the
``hypercar.anim.js`` choreography targets:

    o1.1  body              painted panels, pillars, aero skins
    o1.2  glazing           DLO glass + lamp lenses
    o1.3  lighting          lamp internals + light signature
    o1.4  chassis           monocoque tub, subframes, crash structures
    o1.5  suspension_front  wishbones, uprights, pushrods, rockers, coilovers
    o1.6  suspension_rear   ditto, rear
    o1.7  wheels            rims, tyres
    o1.8  brakes            discs, calipers, hubs
    o1.9  powertrain        engine, intake, exhaust, transaxle, driveshafts
    o1.10 interior          seats, wheel, dash, console, pedals, door cards
    o1.11 aero              splitter, diffuser, wing
    o1.12 hinge             dihedral synchro-helix door mechanism
    o1.13 details           mirrors, badges, filler, vents, fasteners
"""

from __future__ import annotations

import cadgen
from cadgen import build123d as bd
from cadgen import step

from aero import aero
from body import body
from brakes import brakes
from chassis import chassis
from details import details
from glazing import glazing
from hinge import hinge
from interior import interior
from lighting import lighting
from powertrain import powertrain
from suspension_front import suspension_front
from suspension_rear import suspension_rear
from wheels import wheels

from lib import hinge as hinge_lib

# Order here IS the occurrence order (o1.1, o1.2, ...) and the animation
# module's refs depend on it -- do not reorder without updating
# hypercar.anim.js. Each entry is a sibling MODEL (src/<system>.py): calling it
# inside the body builds it if stale, on its own worker, or loads it, and the
# car links its tree.
SYSTEMS = [
    body,
    glazing,
    lighting,
    chassis,
    suspension_front,
    suspension_rear,
    wheels,
    brakes,
    powertrain,
    interior,
    aero,
    hinge,
    details,
]


# ---------------------------------------------------------------------------
# Kinematics: the dihedral synchro-helix doors.
#
# One CYLINDRICAL mate per door -- rotation and axial travel about the SAME
# tower axis is exactly what a cylindrical joint is -- geared by the "doors"
# coupling so a single 0..1 slider drives both sides through the mechanism's
# own lead: 62 deg of rotation while sweeping 310 mm along the axis (299 up,
# 80 forward). The numbers come straight from lib/hinge.py, so changing the
# tower changes the mates with it.
#
# The door skin is the mated child; everything that rides the door -- glass,
# trim, mirror, and the two mechanism parts bolted to it -- is FASTENED to it,
# because those occurrences are siblings in the instance tree (they live in
# other system groups) and so do not ride for free.
#
# Choreography (explode sequences, the tour) is NOT here: it is
# hypercar.anim.js, declared below.
# ---------------------------------------------------------------------------

DOOR_RIDERS = [
    "side_glass",
    "door_card_upper",
    "door_card_lower",
    "door_pull",
    "mirror_housing",
    "mirror_bezel",
    "mirror_glass",
    "mirror_stalk",
    "mirror_base",
    "door_bracket",
    "door_lug_lower",
]


def _door_mates():
    mates = []
    for side in ("left", "right"):
        name = f"door_{side}"
        sweep = hinge_lib.DOOR_SWEEP_DEG * hinge_lib.DOOR_SWEEP_SIGN[side]
        mates.append(cadgen.cylindrical(
            name,
            parent="#chassis",
            child=f"#door:{side}",
            origin=hinge_lib.HELIX_AXIS_ORIGIN[side],
            direction=hinge_lib.HELIX_AXIS_DIR[side],
            limits={
                "turn": (min(0.0, sweep), max(0.0, sweep)),
                "travel": (0.0, hinge_lib.CARRIER_TRAVEL),
            },
        ))
        for rider in DOOR_RIDERS:
            mates.append(cadgen.fastened(
                f"{name}_{rider}",
                parent=f"#door:{side}",
                child=f"#{rider}:{side}",
            ))
    return mates


KINEMATICS = {
    "mates": _door_mates(),
    "couplings": [
        cadgen.couple("doors", {
            f"door_{side}.{dof}": value
            for side in ("left", "right")
            for dof, value in (
                ("turn", hinge_lib.DOOR_SWEEP_DEG * hinge_lib.DOOR_SWEEP_SIGN[side]),
                ("travel", hinge_lib.CARRIER_TRAVEL),
            )
        }),
    ],
    "poses": {"shut": {"doors": 0.0}, "open": {"doors": 1.0}},
}


@step(out="../STEP/hypercar.step", kinematics=KINEMATICS,
      animation="hypercar.anim.js")
def hypercar():
    groups = [system() for system in SYSTEMS]      # thirteen builds, in parallel
    return bd.Compound(children=groups, label="mid_engine_hypercar")


if __name__ == "__main__":
    hypercar()
