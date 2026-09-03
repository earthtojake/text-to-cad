"""Full watch assembly: case + dial/hands + movement + bracelet.

Children are sibling models, composed by FUNCTION (import links, `memo`
caches). Each child already authors its parts in the WATCH frame (see
`lib/spec.py`), so placements are identity — except the movement, which is
cased via the documented flip about X + MOVT_Z_OFFSET lift.

Articulation is split the way cadgen splits it: typed mates in `KINEMATICS`
below (the watch's real degrees of freedom — hands, going train, escapement,
chronograph, crown, pushers — plus the gear ratios that tie them together),
and choreography in `moonwatch.anim.js` (exploded reveals, the sinusoidal
balance swing and the escape wheel's per-beat snap, which are not linear
gearings and so are not mates).
"""

import bracelet
import cadgen
import case
import dial
import movement
from cadgen import build123d as bd
from cadgen import step
from cadgen.compose import memo

from lib import materials
from lib import spec as S

# Composition seam: `child_entry()` (path-addressed) is retired; a child is
# now its imported model FUNCTION wrapped in `memo`, a cached scope keyed by
# the child's source closure. An edit that does not reach a child's files
# skips that child's Python and kernel work entirely.
_CASE = memo(case.case)
_DIAL = memo(dial.dial)
_BRACELET = memo(bracelet.bracelet)
_MOVEMENT = memo(movement.movement)


# ---------------------------------------------------------------------------
# Kinematics — axes in the WATCH frame (+Z through the crystal, crown at +X)
# ---------------------------------------------------------------------------

_UP = (0.0, 0.0, 1.0)
_CENTER = (0.0, 0.0, 0.0)                       # central hand stack / center wheel
_SUB_SECONDS = (-S.SUBDIAL_RADIUS, 0.0, 0.0)    # small seconds at 9 o'clock
_SUB_MINUTES = (S.SUBDIAL_RADIUS, 0.0, 0.0)     # 30-minute recorder at 3
_SUB_HOURS = (0.0, -S.SUBDIAL_RADIUS, 0.0)      # 12-hour recorder at 6


def _cased(pos):
    """Movement-local (x, y) -> watch-frame axis origin (x, -y, 0).

    The movement is cased by a 180 deg flip about X, so local +Y lands at
    watch -Y; z is free for a +Z axis (any point on the line will do).
    """
    return (float(pos[0]), -float(pos[1]), 0.0)


_W_CENTER = _cased(S.CENTER_WHEEL_POS)
_W_THIRD = _cased(S.THIRD_WHEEL_POS)
_W_FOURTH = _cased(S.FOURTH_WHEEL_POS)
_W_ESCAPE = _cased(S.ESCAPE_WHEEL_POS)
_W_PALLET = _cased(S.PALLET_FORK_POS)
_W_BALANCE = _cased(S.BALANCE_POS)
_W_COUPLING = _cased(S.COUPLING_WHEEL_POS)

# Pushers sit at +/- PUSHER_ANGLES from +X and travel radially INWARD; their
# axis lines pass through the case axis at PUSHER_Z.
_PUSHER_AXIS_ORIGIN = (0.0, 0.0, S.PUSHER_Z)


def _pusher_direction(angle_deg: float):
    import math

    radians = math.radians(angle_deg)
    return (-math.cos(radians), -math.sin(radians), 0.0)


def _spin(name, child, origin, limits, parent="#main_plate"):
    return cadgen.revolute(name, parent=parent, child=child,
                           origin=origin, direction=_UP, limits=limits)


def _rides(name, parent, child):
    return cadgen.fastened(name, parent=parent, child=child)


_MATES = [
    # --- dial-side hand stack (siblings of the dial plate, so each hand's
    # lume/hub must be fastened to it explicitly) ------------------------------
    _spin("hour", "#hand:hour", _CENTER, (-720.0, 720.0), parent="#dial_plate"),
    _rides("hour_lume_rides", "#hand:hour", "#hand:hour_lume"),
    _rides("hour_hub_rides", "#hand:hour", "#hub:hour"),
    _spin("minute", "#hand:minute", _CENTER, (-4320.0, 4320.0), parent="#dial_plate"),
    _rides("minute_lume_rides", "#hand:minute", "#hand:minute_lume"),
    _rides("minute_hub_rides", "#hand:minute", "#hub:minute"),
    _spin("chrono_seconds", "#hand:chrono_seconds", _CENTER, (-10800.0, 10800.0),
          parent="#dial_plate"),
    _rides("chrono_cap_rides", "#hand:chrono_seconds", "#hand:chrono_cap"),
    _spin("sub_seconds", "#hand:sub_seconds", _SUB_SECONDS, (-21600.0, 21600.0),
          parent="#dial_plate"),
    _spin("chrono_minutes", "#hand:sub_minutes30", _SUB_MINUTES, (-360.0, 360.0),
          parent="#dial_plate"),
    _spin("chrono_hours", "#hand:sub_hours12", _SUB_HOURS, (-360.0, 360.0),
          parent="#dial_plate"),

    # --- going train (each wheel + its pinion are siblings on the plate) ------
    _spin("center", "#center_wheel", _W_CENTER, (-4320.0, 4320.0)),
    _rides("center_pinion_rides", "#center_wheel", "#center_pinion"),
    _spin("third", "#third_wheel", _W_THIRD, (-3600.0, 3600.0)),
    _rides("third_pinion_rides", "#third_wheel", "#third_pinion"),
    _spin("fourth", "#fourth_wheel", _W_FOURTH, (-21600.0, 21600.0)),
    _rides("fourth_pinion_rides", "#fourth_wheel", "#fourth_pinion"),

    # --- escapement ----------------------------------------------------------
    _spin("escape", "#escape_wheel", _W_ESCAPE, (-216000.0, 216000.0)),
    _rides("escape_pinion_rides", "#escape_wheel", "#escape_pinion"),
    _spin("pallet", "#pallet_fork", _W_PALLET, (-12.0, 12.0)),
    _rides("pallet_entry_rides", "#pallet_fork", "#pallet_stone:entry"),
    _rides("pallet_exit_rides", "#pallet_fork", "#pallet_stone:exit"),
    _rides("pallet_arbor_rides", "#pallet_fork", "#pallet_arbor"),
    _spin("balance", "#balance_wheel", _W_BALANCE, (-330.0, 330.0)),
    _rides("balance_staff_rides", "#balance_wheel", "#balance_staff"),
    _rides("impulse_jewel_rides", "#balance_wheel", "#impulse_jewel"),

    # --- chronograph ---------------------------------------------------------
    _spin("chrono_runner", "#chrono_runner_wheel", _W_CENTER, (-10800.0, 10800.0)),
    _rides("runner_heart_rides", "#chrono_runner_wheel", "#chrono_runner_heart_cam"),
    _rides("runner_arbor_rides", "#chrono_runner_wheel", "#chrono_runner_arbor"),
    _spin("coupling", "#coupling_wheel", _W_COUPLING, (-10800.0, 10800.0)),

    # --- crown and pushers ---------------------------------------------------
    # Winding turns the crown; setting pulls it out. The stem is a movement
    # part, a sibling of the crown's case parts, so it is fastened on.
    cadgen.cylindrical("crown", parent="#case_middle", child="#crown",
                       origin=(0.0, 0.0, S.CROWN_Z), direction=(1.0, 0.0, 0.0),
                       limits={"turn": (-3600.0, 3600.0), "travel": (0.0, 1.6)}),
    _rides("stem_rides", "#crown", "#stem"),
    cadgen.slider("pusher_start", parent="#case_middle", child="#pusher_cap:2oclock",
                  origin=_PUSHER_AXIS_ORIGIN,
                  direction=_pusher_direction(S.PUSHER_ANGLES[0]),
                  limits=(0.0, 1.1)),
    cadgen.slider("pusher_reset", parent="#case_middle", child="#pusher_cap:4oclock",
                  origin=_PUSHER_AXIS_ORIGIN,
                  direction=_pusher_direction(S.PUSHER_ANGLES[1]),
                  limits=(0.0, 1.1)),
]

# The balance's 16 timing screws are siblings of the rim they are threaded
# into, so each rides it explicitly.
_MATES += [
    _rides(f"timing_screw_{i}_rides", "#balance_wheel", f"#timing_screw:{i}")
    for i in range(16)
]


# Gear trains are ratio arithmetic, not code. `running` is SECONDS of elapsed
# time; `chrono` is SECONDS of chronograph running (the clutch engaged).
#
#   18,000 vph / 2 vibrations per tooth / 15 teeth = 600 escape rev/h = 60 deg/s
#   fourth wheel  1 rev/min  =   6 deg/s (carries the small seconds)
#   third wheel   8 rev/h    = 0.8 deg/s (conventional 2310-family ratio)
#   center wheel  1 rev/h    = 0.1 deg/s (the minute arbor)
# Hands run CLOCKWISE seen dial-up, i.e. negative about watch +Z; meshing
# wheels alternate sense.
_COUPLINGS = [
    cadgen.couple(
        "running",
        {
            "minute": -0.1,
            "hour": -1.0 / 120.0,
            "sub_seconds": -6.0,
            "center": -0.1,
            "third": 0.8,
            "fourth": -6.0,
            "escape": 60.0,
        },
        limits=(0.0, 3600.0),
    ),
    cadgen.couple(
        "chrono",
        {
            "chrono_seconds": -6.0,
            "chrono_runner": -6.0,
            "chrono_minutes": -0.2,
            "chrono_hours": -1.0 / 120.0,
            "coupling": 6.0,
        },
        limits=(0.0, 1800.0),
    ),
]

KINEMATICS = {
    "mates": _MATES,
    "couplings": _COUPLINGS,
    "poses": {
        # ZERO IS THE ARTIFACT AS WRITTEN — the watch as built reads 10:09:38
        # with the chronograph reset, so every preset is a departure from that.
        "rest": {},
        "one_minute": {"running": 60.0},
        "half_hour": {"running": 1800.0},
        "chrono_at_10min": {"chrono": 600.0},
        "start_pressed": {"pusher_start": 1.0},
        "reset_pressed": {"pusher_reset": 1.0},
        "winding": {"crown.turn": 1080.0},
        "setting": {"crown.travel": 1.6, "crown.turn": 180.0},
    },
}


@step(out="../STEP/moonwatch.step", kinematics=KINEMATICS,
      animation="moonwatch.anim.js")
def moonwatch():
    children = []

    case_parts = _CASE()
    case_parts.label = "case"
    children.append(case_parts)

    dial_parts = _DIAL()
    dial_parts.label = "dial_and_hands"
    children.append(dial_parts)

    bracelet_parts = _BRACELET()
    bracelet_parts.label = "bracelet"
    children.append(bracelet_parts)

    movement_parts = _MOVEMENT()
    movement_parts.label = "movement"
    # cased: local (x, y, z) -> watch (x, -y, MOVT_Z_OFFSET - z)
    movement_parts.locate(
        bd.Location((0, 0, S.MOVT_Z_OFFSET), (1, 0, 0), 180) * movement_parts.location
    )
    children.append(movement_parts)

    # movement ring: fills the annulus between the movement OD and the
    # case interior so the caseback window shows metal, not void.
    # align=(None,None,None) leaves the cylinder base at the origin, so
    # Pos sets the ring's bottom; the cut over/under-shoots to avoid
    # coplanar-face booleans. Cased movement spans watch z 0.96..7.7.
    ring = bd.Pos(0, 0, 1.0) * bd.Cylinder(
        15.6, 6.7, align=(None, None, None)
    ) - bd.Pos(0, 0, 0.9) * bd.Cylinder(
        S.MOVEMENT_DIAMETER / 2 + 0.05, 7.0, align=(None, None, None)
    )
    ring.color = bd.Color(*S.STEEL_DARK)
    ring.label = "movement_ring"
    children.append(ring)

    compound = bd.Compound(children=children, label="moonwatch")
    materials.apply(compound)
    return compound


if __name__ == "__main__":
    moonwatch()
