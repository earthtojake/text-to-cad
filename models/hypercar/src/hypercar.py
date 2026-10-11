"""Mid-engine hypercar -- full assembly.

Body panels are cut from one master surface (see ``lib/surfaces.py``), so
highlight lines cross every shutline without a kink and every panel gap is a
real constant-width gap.

Assembly tree is grouped BY SYSTEM — thirteen sibling models under ``src/``,
composed here by CALLING them — which is also the occurrence order the
``ANIMATION`` clips target:

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

import math

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

# Order here IS the occurrence order (o1.1, o1.2, ...) and the ANIMATION
# clips' targets depend on it -- do not reorder without updating them
# below. Each entry is a sibling MODEL (src/<system>.py): calling it
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
# Choreography (explode sequences, the tour) is NOT here: it is the
# ANIMATION clips, declared below.
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


# ---------------------------------------------------------------------------
# Animation: clips sampled to keyframes when the model builds.
#
# The split (see the $cad skill's kinematics reference): the DOOR MECHANISM is
# the typed mates above, because it is a real tree-structured articulation and
# belongs on the viewer's pose slider. Everything here is choreography --
# staged explodes, timing, easing -- which mates cannot and should not express.
#
#   showcase  the cinematic tour: skin off, interior out, engine back and then
#             apart, running gear off, then everything back together
#   doors     both doors through the full synchro-helix and shut again
#   explode   the whole car apart and back
#
# Every clip is an exact loop: each is built from window functions that are
# identically zero at its start and its end, so the last frame equals the
# first and there is no jump on repeat.
#
# The doors clip re-describes the helix rather than reading the mates
# (animation knows nothing of kinematics), from the SAME lib/hinge.py constants
# the mates are built from.
# ---------------------------------------------------------------------------

# --- easing ----------------------------------------------------------------


def _smooth(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3.0 - 2.0 * x)


def _window(p: float, a: float, b: float, c: float, d: float) -> float:
    """Rise a..b, hold b..c, fall c..d, zero outside. Every tour window ends
    its fall before the tour does, which is what makes the loop exact."""
    if p <= a or p >= d:
        return 0.0
    if p < b:
        return _smooth((p - a) / (b - a))
    if p <= c:
        return 1.0
    return 1.0 - _smooth((p - c) / (d - c))


def _bump(p: float) -> float:
    """Raised cosine: 0 at both ends, 1 in the middle, and its derivative is 0
    at the seam too, so the repeat has no visible kick."""
    return 0.5 - 0.5 * math.cos(math.tau * p)


# --- explode ---------------------------------------------------------------
#
# Each group leaves along one vector, scaled by its 0..1 explode step:
#
#   _radial   away from the car's long axis -- each group leaves along its own
#             normal, so the shell opens like a flower instead of every panel
#             sliding the same way
#   _lateral  straight out in +/-Y by which side the group sits on
#   (x, y, z) along that vector
#   (the chassis appears nowhere: it is the spine everything else leaves)
#
# A centre is the group's REST-POSE centre, measured off the built package and
# pinned here, because a clip moves parts and never measures them. They are
# geometry, not choreography -- re-measure them if the car's proportions move.
#
# A group's tour is the window it occupies in the showcase. The order -- skin,
# then glass and trim, then interior, then powertrain, then running gear -- is
# a strip-down: you always remove what is on top of the thing you want to see
# next, so the car never hides the part being shown.

_CAR_AXIS_Z = 560.0

_SKIN_TOUR = (0.1, 0.22, 0.86, 0.97)
_GLASS_TOUR = (0.11, 0.23, 0.86, 0.97)
_TRIM_TOUR = (0.12, 0.24, 0.86, 0.97)
_INTERIOR_TOUR = (0.24, 0.36, 0.86, 0.97)
_POWERTRAIN_TOUR = (0.38, 0.5, 0.86, 0.97)
_SUSPENSION_TOUR = (0.66, 0.78, 0.84, 0.95)
_WHEEL_TOUR = (0.68, 0.8, 0.84, 0.95)
_BRAKE_TOUR = (0.7, 0.81, 0.84, 0.95)


def _ids(parent: str, *children: int) -> tuple[str, ...]:
    """Targets for children of the occurrence ``parent``, by child number."""
    return tuple(f"#{parent}.{child}" for child in children)


def _unit_times(d, gain: float) -> tuple[float, float, float]:
    m = math.hypot(*d)
    if m < 1e-3:
        return (0.0, 0.0, gain)
    return (d[0] / m * gain, d[1] / m * gain, d[2] / m * gain)


def _radial(centre, gain: float) -> tuple[float, float, float]:
    return _unit_times((0.0, centre[1], centre[2] - _CAR_AXIS_Z), gain)


def _lateral(centre, gain: float) -> tuple[float, float, float]:
    return (0.0, gain if centre[1] >= 0.0 else -gain, 0.0)


# (targets, explode vector, showcase tour)
_GROUPS = (
    # body: the flanks swing out sideways, the upper skins lift, the ends draw
    # fore and aft, the floor drops away
    (_ids("o1.1", 3, 4, 5, 6, 18, 20, 22), _radial((-82.5, 772.8, 567.1), 1500), _SKIN_TOUR),
    (_ids("o1.1", 7, 8, 9, 10, 19, 21, 23), _radial((-82.5, -772.8, 567.1), 1500), _SKIN_TOUR),
    (_ids("o1.1", 2, 11, 13, 14, 15, 17), _radial((-82.5, 0.0, 849.1), 1500), _SKIN_TOUR),
    (_ids("o1.1", 1, 24, 25, 26), (1500, 0, 150), _SKIN_TOUR),
    (_ids("o1.1", 16), (-1500, 0, 150), _SKIN_TOUR),
    (_ids("o1.1", 12), (0, 0, -900), _SKIN_TOUR),
    # glazing: side glass follows its own door's flank, screens lift, lenses
    # leave with the lamps they cover
    (_ids("o1.2", 2), _radial((-237.9, 513.6, 943.9), 2150), _GLASS_TOUR),
    (_ids("o1.2", 3), _radial((-237.9, -513.6, 943.9), 2150), _GLASS_TOUR),
    (_ids("o1.2", 1, 4), _radial((-230.0, 0.0, 947.9), 2150), _GLASS_TOUR),
    (_ids("o1.2", 5, 6), (1750, 0, 300), _GLASS_TOUR),
    (_ids("o1.2", 7), (-1750, 0, 300), _GLASS_TOUR),
    # lighting: head and tail units leave out of their own ends
    (_ids("o1.3", *range(1, 49)), (1750, 0, 560), _TRIM_TOUR),
    (_ids("o1.3", *range(49, 93)), (-1750, 0, 560), _TRIM_TOUR),
    # chassis holds still -- no entry.
    # suspension: each corner straight out, the steering rack and ARBs along the
    # car so they stay legible between the corners
    (_ids("o1.5", 1), _lateral((1242.1, 437.2, 448.9), 1150), _SUSPENSION_TOUR),
    (_ids("o1.5", 2), _lateral((1242.1, -437.2, 448.9), 1150), _SUSPENSION_TOUR),
    (_ids("o1.5", 3, 4), (900, 0, 700), _SUSPENSION_TOUR),
    (_ids("o1.6", *range(1, 49)), _lateral((-1453.2, 546.9, 490.3), 1150), _SUSPENSION_TOUR),
    (_ids("o1.6", *range(49, 97)), _lateral((-1453.2, -546.9, 490.0), 1150), _SUSPENSION_TOUR),
    (_ids("o1.6", *range(97, 102)), (-900, 0, 700), _SUSPENSION_TOUR),
    # wheels and brakes: off their own hubs, one corner at a time in space
    (_ids("o1.7", 1, 5), _lateral((1326.9, 855.3, 403.1), 2400), _WHEEL_TOUR),
    (_ids("o1.7", 2, 6), _lateral((1326.9, -855.3, 403.1), 2400), _WHEEL_TOUR),
    (_ids("o1.7", 3, 7), _lateral((-1351.6, 835.2, 424.4), 2400), _WHEEL_TOUR),
    (_ids("o1.7", 4, 8), _lateral((-1351.6, -835.2, 424.4), 2400), _WHEEL_TOUR),
    (_ids("o1.8", 1, 2), _lateral((1350.0, 852.7, 397.0), 1750), _BRAKE_TOUR),
    (_ids("o1.8", 3, 4), _lateral((1347.7, -847.3, 388.1), 1750), _BRAKE_TOUR),
    (_ids("o1.8", 5, 6), _lateral((-1350.0, 830.0, 407.2), 1750), _BRAKE_TOUR),
    (_ids("o1.8", 7, 8), _lateral((-1350.0, -830.0, 417.4), 1750), _BRAKE_TOUR),
    # powertrain out of the back as one unit; it comes apart later, on its own
    (("#o1.9",), (-2350, 0, 320), _POWERTRAIN_TOUR),
    # interior lifts straight out of the tub
    (("#o1.10",), (140, 0, 1950), _INTERIOR_TOUR),
    # aero: front furniture forward and down, floor and diffuser back and down,
    # wing back and up -- each leaves the way it was fitted
    (_ids("o1.11", *range(1, 12)), (1900, 0, -200), _TRIM_TOUR),
    (_ids("o1.11", *range(12, 19)), (-1400, 0, -800), _TRIM_TOUR),
    (_ids("o1.11", *range(19, 25)), (-1200, 0, 900), _TRIM_TOUR),
    # door mechanism: outboard with its own flank
    (_ids("o1.12", 1), _lateral((798.5, 821.4, 529.0), 1400), _TRIM_TOUR),
    (_ids("o1.12", 2), _lateral((798.5, -821.4, 529.0), 1400), _TRIM_TOUR),
    # details: side jewellery out with its flank, badges and filler straight up
    (_ids("o1.13", *range(1, 38)), _radial((-64.7, 652.5, 691.5), 2500), _SKIN_TOUR),
    (_ids("o1.13", *range(38, 75)), _radial((-64.7, -652.5, 691.5), 2500), _SKIN_TOUR),
    (_ids("o1.13", *range(75, 85)), (0, 0, 1400), _SKIN_TOUR),
)

# --- engine sub-explode ----------------------------------------------------
#
# The powertrain gets a second, nested stage: once the whole unit has moved
# clear of the car it comes apart on its own, around the block. Directions are
# derived from each part's rest-pose centre relative to the block, so heads and
# cam covers leave along their real bank angle rather than a hand-picked
# vector. A plain vector stands in where a fixed direction reads better (the
# plenum straight up, the transaxle straight back).

_ENGINE_ANCHOR = (-1500.0, 0.0, 478.6)  # engine_block:v12
_ENGINE_TOUR = (0.52, 0.62, 0.8, 0.9)


def _off_block(centre, gain: float) -> tuple[float, float, float]:
    return _unit_times(tuple(c - a for c, a in zip(centre, _ENGINE_ANCHOR)), gain)


_ENGINE_PARTS = (
    (_ids("o1.9", 2), _off_block((-1343.7, 0.0, 626.6), 520)),  # head, front bank
    (_ids("o1.9", 4), _off_block((-1656.3, 0.0, 626.6), 520)),  # head, rear bank
    (_ids("o1.9", 3), _off_block((-1310.9, 0.0, 685.6), 980)),  # cam cover, front
    (_ids("o1.9", 5), _off_block((-1689.1, 0.0, 685.6), 980)),  # cam cover, rear
    (_ids("o1.9", 6), _off_block((-1500.0, 388.0, 468.0), 760)),
    (_ids("o1.9", 8), _off_block((-1500.0, -388.0, 468.0), 760)),
    (_ids("o1.9", 7, 9), _off_block((-1500.0, 0.0, 884.0), 760)),
    (_ids("o1.9", 10), (0, 0, 1250)),  # intake plenum
    (_ids("o1.9", 11), _off_block((-1800.2, 0.2, 526.1), 900)),  # exhaust
    (_ids("o1.9", 12), (-1150, 0, 60)),  # transaxle
)

# --- the moves -------------------------------------------------------------


def _scaled(v, k: float) -> tuple[float, float, float]:
    return (v[0] * k, v[1] * k, v[2] * k)


def _explode_group(m, targets: tuple[str, ...], vector, k: float) -> None:
    """One group's explode step, k in 0..1."""
    if k > 0.0:
        m.get(*targets).translate(_scaled(vector, k))


def _explode_engine(m, k: float) -> None:
    """The engine's own stage. It accumulates ON TOP of the powertrain's
    translation (transforms premultiply), so the V12 comes apart where it
    already stands instead of dragging itself back across the car."""
    if k > 0.0:
        for targets, vector in _ENGINE_PARTS:
            m.get(*targets).translate(_scaled(vector, k))


def _open_doors(m, u: float) -> None:
    """Both doors through the synchro-helix at u = 0..1, with everything that
    rides them. Rotation and axial travel share one axis, so the door rotates
    outward while sweeping up and forward along the same line: a true helix,
    not a scissor, butterfly or gullwing."""
    if u <= 0.0:
        return
    for side in ("left", "right"):
        axis = hinge_lib.HELIX_AXIS_DIR[side]
        turn = hinge_lib.DOOR_SWEEP_SIGN[side] * u * hinge_lib.DOOR_SWEEP_DEG
        door = m.get(f"#door:{side}", *(f"#{rider}:{side}" for rider in DOOR_RIDERS))
        door.rotate(axis, turn, hinge_lib.HELIX_AXIS_ORIGIN[side])
        door.translate(_scaled(axis, u * hinge_lib.CARRIER_TRAVEL))


# --- the clips -------------------------------------------------------------


def _showcase(t: float, m) -> None:
    """Skin away, interior out, engine back and then apart, running gear off,
    then reassembled. Doors stay shut.

    Long enough to dwell on each system rather than flicking past it: the
    staged strip-down needs time to read, especially the engine's own
    sub-explode. The tour tells the eye where to look by TIMING alone -- the
    retired sidecar also lifted the emissive of the featured system, but a clip
    moves, fades and hides parts only, and fading systems in a dark scene just
    makes it muddy."""
    p = t / 48.0
    for targets, vector, tour in _GROUPS:
        _explode_group(m, targets, vector, _window(p, *tour))
    _explode_engine(m, _window(p, *_ENGINE_TOUR))


def _doors(t: float, m) -> None:
    """Both doors through the full synchro-helix and back."""
    _open_doors(m, _bump(t / 7.0))


def _explode(t: float, m) -> None:
    """The whole car apart and back together."""
    k = _bump(t / 10.0)
    for targets, vector, _tour in _GROUPS:
        _explode_group(m, targets, vector, k)
    # The engine comes apart too, so its sub-explode is not only reachable
    # through the tour.
    _explode_engine(m, k)


ANIMATION = {
    "showcase": cadgen.clip(_showcase, duration=48, label="Showcase tour"),
    "doors": cadgen.clip(_doors, duration=7, label="Doors"),
    "explode": cadgen.clip(_explode, duration=10, label="Explode"),
}


@step(out="../STEP/hypercar.step", kinematics=KINEMATICS, animation=ANIMATION)
def hypercar():
    groups = [system() for system in SYSTEMS]      # thirteen builds, in parallel
    return bd.Compound(children=groups, label="mid_engine_hypercar")


if __name__ == "__main__":
    hypercar()
