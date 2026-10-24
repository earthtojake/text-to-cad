"""Full watch assembly: case + dial/hands + movement + bracelet, one document.

Composed by FUNCTION in this one body: the case, the dial and the bracelet are
plain functions (`lib/watch.py`, what `case.py`, `dial.py` and `bracelet.py`
declare), the movement the three `@memo` layers `movement.py` composes. Each
authors its parts in the WATCH frame (see `lib/spec.py`), so placements are
identity -- except the movement, which is cased by the documented flip about
X + MOVT_Z_OFFSET lift.

Articulation is build123d's joints, placed where the parts stand and paired by
label (no `connect_to`, which cannot place a part in a nested assembly), each rigid
half where its moving joint holds it at 0 (`_held`):

- the watch's real degrees of freedom, the old `KINEMATICS` mates: the hands
  on the dial, the going train, escapement and chronograph in the movement,
  the crown (turn and travel) and the two pushers on the case middle, each
  wheel's pinion and each hand's lume and hub fastened by rigid-joint pairs;
- its gear trains, the old couplings, as `gear_pair`s: `running` (seconds of time)
  and `chrono` (seconds of chronograph running), each a constraint its wheels and
  hands move only through, and its poses as `mechanism_state`s;
and nothing else: the exploded clips move no joint.

The four old clips keep their names: `running` (the escapement's 8 beats) is a
motion, a function of time over the escapement and the two trains; `reveal`,
`showcase` and `grand_tour`, which take the watch apart while the escapement runs,
are GLB animations (`cadgen.gltf`): the escapement and the trains posed at every
key, each part or group the old clips moved translated along its own vector, the
movement's tiers fanned, carried by its flip, and the movement rising out of the case
and flipping bridge-side-up about its own centre. A GLB of the watch carries all
four as clips. A player repeats a clip (neither has a loop): every part ends where
it started but the going train and the chronograph's recorders, which keep the
watch's time, so a repeat steps them back to as built (1.6 s of `running` a 6 s
clip: the small seconds 9.6 deg, the minute hand 0.16 deg).
"""

import math

import build123d as bd
from cadgen import model
from cadgen.ap242 import configuration_sequence, gear_pair, mechanism_state
from cadgen.gltf import animation

import chrono_works
import keyless_works
import movement_base
from lib import materials as M
from lib import spec as S
from lib import watch


# ---------------------------------------------------------------------------
# Frames
# ---------------------------------------------------------------------------
# The dial and the case are in the WATCH frame: +Z through the crystal, crown at
# +X. The movement's joints are authored in its own frame (bridge side up, see
# `lib/spec.py`) about local -Z, which the casing flip turns to watch +Z, so a
# positive angle is anticlockwise seen dial-up in both and the ratios read as
# the watch's.

_UP = (0.0, 0.0, 1.0)
_DOWN = (0.0, 0.0, -1.0)
_SUB_SECONDS = (-S.SUBDIAL_RADIUS, 0.0, 0.0)    # small seconds at 9 o'clock
_SUB_MINUTES = (S.SUBDIAL_RADIUS, 0.0, 0.0)     # 30-minute recorder at 3
_SUB_HOURS = (0.0, -S.SUBDIAL_RADIUS, 0.0)      # 12-hour recorder at 6
_PUSHER_AXIS_ORIGIN = (0.0, 0.0, S.PUSHER_Z)    # the pushers' axes cross the case axis here
_MOVEMENT_CENTER = (0.0, 0.0, 1.7)              # the cased movement's flip centre (watch frame)


def _local(pos) -> tuple[float, float, float]:
    return (float(pos[0]), float(pos[1]), 0.0)


def _pusher_direction(angle_deg: float) -> tuple[float, float, float]:
    """Inward along a pusher's axis, which sits ``angle_deg`` from +X."""
    radians = math.radians(angle_deg)
    return (-math.cos(radians), -math.sin(radians), 0.0)


# ---------------------------------------------------------------------------
# Finding parts by label
# ---------------------------------------------------------------------------

def _labelled(root) -> dict[str, object]:
    """Every node below ``root`` by its label (each label the watch uses is unique)."""
    found = {}
    stack = [root]
    while stack:
        node = stack.pop()
        if node.label:
            found.setdefault(node.label, node)
        stack.extend(getattr(node, "children", ()) or ())
    return found


class _Parts:
    def __init__(self, root):
        self.by_label = _labelled(root)

    def __getitem__(self, label: str):
        try:
            return self.by_label[label.lstrip("#")]
        except KeyError:
            raise KeyError(f"no part of the watch is labelled {label!r}") from None


def _rides(label: str, carrier, rider) -> None:
    """``rider`` fastened to ``carrier``: a pair of rigid joints of one label where they stand."""
    here = bd.Location()
    bd.RigidJoint(label, carrier, here)
    bd.RigidJoint(label, rider, here)


def _held(base, joint) -> bd.Location:
    """Where the rigid half of ``joint`` (on ``base``) stands at value 0, as the engine reads a
    pair: a revolute's or cylindrical's frame is its axis's; a linear joint slides a frame that
    keeps the part's axes, at the axis's origin."""
    if isinstance(joint, bd.LinearJoint):
        return base.location * bd.Location(joint.relative_axis.position)
    return joint.location


# ---------------------------------------------------------------------------
# The mates: hands, going train, escapement, chronograph, crown and pushers
# ---------------------------------------------------------------------------

_HANDS = (
    # label, hand, axis origin (watch frame), range in degrees
    ("hour", "#hand:hour", (0.0, 0.0, 0.0), (-720.0, 720.0)),
    ("minute", "#hand:minute", (0.0, 0.0, 0.0), (-4320.0, 4320.0)),
    ("chrono_seconds", "#hand:chrono_seconds", (0.0, 0.0, 0.0), (-10800.0, 10800.0)),
    ("sub_seconds", "#hand:sub_seconds", _SUB_SECONDS, (-21600.0, 21600.0)),
    ("chrono_minutes", "#hand:sub_minutes30", _SUB_MINUTES, (-360.0, 360.0)),
    ("chrono_hours", "#hand:sub_hours12", _SUB_HOURS, (-360.0, 360.0)),
)
_HAND_RIDERS = (
    ("hour_lume_rides", "#hand:hour", "#hand:hour_lume"),
    ("hour_hub_rides", "#hand:hour", "#hub:hour"),
    ("minute_lume_rides", "#hand:minute", "#hand:minute_lume"),
    ("minute_hub_rides", "#hand:minute", "#hub:minute"),
    ("chrono_cap_rides", "#hand:chrono_seconds", "#hand:chrono_cap"),
)

# The movement's turning parts, each about its arbor along local -Z. The going train is a
# gear train, so its wheels move only through the `running` coupling (a revolute each).
# The pallet fork banks on its arbor and the balance swings on its staff (a revolute
# each). label, part, position, range.
_TRAIN = (
    ("center", "#center_wheel", S.CENTER_WHEEL_POS, (-4320.0, 4320.0)),
    ("third", "#third_wheel", S.THIRD_WHEEL_POS, (-3600.0, 3600.0)),
    ("fourth", "#fourth_wheel", S.FOURTH_WHEEL_POS, (-21600.0, 21600.0)),
    ("escape", "#escape_wheel", S.ESCAPE_WHEEL_POS, (-216000.0, 216000.0)),
    ("pallet", "#pallet_fork", S.PALLET_FORK_POS, (-12.0, 12.0)),
)
_BALANCE = ("balance", "#balance_wheel", S.BALANCE_POS, (-330.0, 330.0))
_WHEEL_RIDERS = (
    ("center_pinion_rides", "#center_wheel", "#center_pinion"),
    ("third_pinion_rides", "#third_wheel", "#third_pinion"),
    ("fourth_pinion_rides", "#fourth_wheel", "#fourth_pinion"),
    ("escape_pinion_rides", "#escape_wheel", "#escape_pinion"),
    ("pallet_entry_rides", "#pallet_fork", "#pallet_stone:entry"),
    ("pallet_exit_rides", "#pallet_fork", "#pallet_stone:exit"),
    ("pallet_arbor_rides", "#pallet_fork", "#pallet_arbor"),
    ("balance_staff_rides", "#balance_wheel", "#balance_staff"),
    ("impulse_jewel_rides", "#balance_wheel", "#impulse_jewel"),
    *((f"timing_screw_{i}_rides", "#balance_wheel", f"#timing_screw:{i}") for i in range(16)),
)
# The chronograph's wheels turn in the chronograph works, which fan as one tier.
_CHRONO_WHEELS = (
    ("chrono_runner", "#chrono_runner_wheel", S.CENTER_WHEEL_POS, (-10800.0, 10800.0)),
    ("coupling", "#coupling_wheel", S.COUPLING_WHEEL_POS, (-10800.0, 10800.0)),
)
_CHRONO_RIDERS = (
    ("runner_heart_rides", "#chrono_runner_wheel", "#chrono_runner_heart_cam"),
    ("runner_arbor_rides", "#chrono_runner_wheel", "#chrono_runner_arbor"),
)

def _hands(parts: _Parts, dial) -> None:
    for label, hand, origin, limits in _HANDS:
        axis = bd.Axis(origin, _UP)
        joint = bd.RevoluteJoint(label, dial, axis=axis, angular_range=limits)
        bd.RigidJoint(label, parts[hand], joint.location)
    for label, carrier, rider in _HAND_RIDERS:
        _rides(label, parts[carrier], parts[rider])


def _train(parts: _Parts, caliber, chrono) -> None:
    for label, wheel, pos, limits in _TRAIN:
        axis = bd.Axis(_local(pos), _DOWN)
        joint = bd.RevoluteJoint(label, caliber, axis=axis, angular_range=limits)
        bd.RigidJoint(label, parts[wheel], joint.location)
    label, wheel, pos, limits = _BALANCE
    axis = bd.Axis(_local(pos), _DOWN)
    joint = bd.RevoluteJoint(label, caliber, axis=axis, angular_range=limits)
    bd.RigidJoint(label, parts[wheel], joint.location)
    for label, carrier, rider in _WHEEL_RIDERS:
        _rides(label, parts[carrier], parts[rider])
    for label, wheel, pos, limits in _CHRONO_WHEELS:
        axis = bd.Axis(_local(pos), _DOWN)
        joint = bd.RevoluteJoint(label, chrono, axis=axis, angular_range=limits)
        bd.RigidJoint(label, parts[wheel], joint.location)
    for label, carrier, rider in _CHRONO_RIDERS:
        _rides(label, parts[carrier], parts[rider])


def _crown_and_pushers(parts: _Parts) -> None:
    middle = parts["#case_middle"]
    # Winding turns the crown; setting pulls it out: a cylindrical joint, turn then travel.
    crown = bd.Axis((0.0, 0.0, S.CROWN_Z), (1.0, 0.0, 0.0))
    joint = bd.CylindricalJoint("crown", middle, axis=crown, angular_range=(-3600.0, 3600.0), linear_range=(0.0, 1.6))
    bd.RigidJoint("crown", parts["#crown"], joint.location)
    for label, cap, angle in (("pusher_start", "#pusher_cap:2oclock", S.PUSHER_ANGLES[0]),
                              ("pusher_reset", "#pusher_cap:4oclock", S.PUSHER_ANGLES[1])):
        axis = bd.Axis(_PUSHER_AXIS_ORIGIN, _pusher_direction(angle))
        joint = bd.LinearJoint(label, middle, axis=axis, linear_range=(0.0, 1.1))
        bd.RigidJoint(label, parts[cap], _held(middle, joint))


# ---------------------------------------------------------------------------
# What the exploded clips move
# ---------------------------------------------------------------------------
# Each part or group the old clips translated, by its label in the watch, and its one
# direction (in the watch frame).
_LIFTS = {
    "caseback_o_ring": _DOWN, "caseback_retaining_ring": _DOWN, "caseback": _DOWN, "caseback_sapphire": _DOWN,
    "movement_ring": _DOWN, "bezel_ring": _UP, "case_polish:bezel": _UP, "bezel_insert": _UP,
    "tachymeter_scale": _UP, "crystal": _UP, "crystal_gasket": _UP, "dial_and_hands": _UP,
    "strap_12": (0.0, 1.0, 0.0), "strap_6": (0.0, -1.0, 0.0), "clasp": (0.0, -1.0, 0.0),
    "spring_bar:12": (0.0, 1.0, 0.0), "spring_bar:6": (0.0, -1.0, 0.0),
}

# Movement tiers, as the old showcase fanned them: each group's z offset in the CASED
# watch frame, where the old clip applied it (negative is the bridge side, toward the
# caseback, which the movement's flip turns upward; the keyless works, on the dial side,
# goes the other way). Each is a translation inside the movement, so its flip carries it.
_PALLET_BRIDGE = ("pallet_bridge", "pallet_bridge:stripe_shadow:0", "pallet_bridge:stripe_shadow:1",
                  "pallet_bridge:anglage", "bridge_jewel:pallet", "chaton:pallet", "screw:pallet_bridge")
_TRAIN_BRIDGE = (
    "train_bridge", *(f"train_bridge:stripe_shadow:{i}" for i in range(3)),
    *(f"train_bridge:anglage:{i}" for i in range(2)),
    *(f"{kind}:{wheel}" for wheel in ("center", "third", "fourth", "escape") for kind in ("bridge_jewel", "chaton")),
    "screw:train_bridge:foot", "screw:train_bridge:fourth", "screw:train_bridge:center",
)
_BARREL_BRIDGE = (
    "barrel_bridge", *(f"barrel_bridge:stripe_shadow:{i}" for i in range(6)),
    *(f"barrel_bridge:anglage:{i}" for i in range(5)), "bridge_jewel:barrel",
    "screw:barrel_bridge:left", "screw:barrel_bridge:right", "screw:barrel_bridge:top",
)
_GOING_TRAIN = ("center_wheel", "center_pinion", "third_wheel", "third_pinion", "fourth_wheel", "fourth_pinion",
                "escape_pinion", "escape_wheel", "pallet_fork", "pallet_stone:entry", "pallet_stone:exit",
                "pallet_arbor")
_BALANCE_TIER = ("balance_cock", "hairspring", "hairspring_stud", "balance_cock:stripe_shadow:0",
                 "balance_cock:stripe_shadow:1", "screw:balance_cock", "stud_holder", "screw:stud_holder",
                 "shock_bezel", "shock_chaton", "shock_cap_jewel", "shock_lyre_spring", "balance_wheel",
                 "balance_staff", "impulse_jewel", *(f"timing_screw:{i}" for i in range(16)))
_TIERS = (
    (("keyless_works",), 7.0),
    (_GOING_TRAIN, -5.0),
    (("barrel_drum", "barrel_lid", "mainspring", "barrel_arbor"), -8.0),
    (_PALLET_BRIDGE, -11.5),
    (_TRAIN_BRIDGE, -15.5),
    (_BARREL_BRIDGE, -15.5),
    (("ratchet_wheel", "screw:ratchet", "crown_wheel", "crown_wheel_core", "screw:crown_wheel", "click",
      "screw:click", "click_spring", "screw:click_spring"), -19.0),
    (_BALANCE_TIER, -24.0),
    (("chronograph_works",), -30.0),
)


# ---------------------------------------------------------------------------
# Gear ratios and poses
# ---------------------------------------------------------------------------
# Gear trains are ratio arithmetic. `running` is SECONDS of elapsed time; `chrono` is
# SECONDS of chronograph running (the clutch engaged).
#
#   18,000 vph / 2 vibrations per tooth / 15 teeth = 600 escape rev/h = 60 deg/s
#   fourth wheel  1 rev/min  =   6 deg/s (carries the small seconds)
#   third wheel   8 rev/h    = 0.8 deg/s (conventional 2310-family ratio)
#   center wheel  1 rev/h    = 0.1 deg/s (the minute arbor)
# Hands run CLOCKWISE seen dial-up, i.e. negative about watch +Z; meshing wheels
# alternate sense. Each coupling is a constraint: its joints move only through it, and
# its range is what their limits allow (one hour of `running`, half an hour of `chrono`,
# either way).

_ESCAPE_DEG_PER_S = 60.0     # the escape wheel's turn per second of `running`


def _couplings_and_poses(watch_root) -> None:
    gear_pair(watch_root, "running", minute=-0.1, hour=-1.0 / 120.0, sub_seconds=-6.0,
           center=-0.1, third=0.8, fourth=-6.0, escape=_ESCAPE_DEG_PER_S)
    gear_pair(watch_root, "chrono",
           chrono_seconds=-6.0, chrono_runner=-6.0, chrono_minutes=-0.2, chrono_hours=-1.0 / 120.0, coupling=6.0)
    # ZERO IS THE ARTIFACT AS WRITTEN: the watch as built reads 10:09:38 with the
    # chronograph reset, so every configuration is a departure from that.
    mechanism_state(watch_root, "one_minute", running=60.0)
    mechanism_state(watch_root, "half_hour", running=1800.0)
    mechanism_state(watch_root, "chrono_at_10min", chrono=600.0)
    mechanism_state(watch_root, "start_pressed", pusher_start=1.0)
    mechanism_state(watch_root, "reset_pressed", pusher_reset=1.0)
    mechanism_state(watch_root, "winding", crown=(1080.0, 0.0))
    mechanism_state(watch_root, "setting", crown=(180.0, 1.6))


# ---------------------------------------------------------------------------
# The clips
# ---------------------------------------------------------------------------
#   running    -- a motion: the escapement in slow-motion macro pacing, 4 balance
#                 oscillations, 8 beats. The escape wheel advances one half-tooth-pitch step
#                 per beat (8 x 12 deg = 96 deg = exactly 4 tooth pitches of the 15-tooth
#                 wheel), the pallet fork snaps between banking positions at each beat, the
#                 going train steps with the escape wheel through `running` at its ratios
#                 (the old clip crept the fourth and third wheels 144 deg a loop instead),
#                 and the chronograph runs (its runner and seconds hand one whole turn).
#   reveal     -- an animation: staged partial explode, the caseback stack fans downward,
#                 the movement ring drops clear, the crystal and bezel stack lift off, the
#                 dial floats up, the bracelet straps slide apart, and the movement rises
#                 into the case mouth and flips bridge-side-up.
#   showcase   -- an animation: full explode, the dial, bezel stack and crystal clear out to
#                 the SIDES so the movement can rise straight up the middle, the crown and
#                 pushers draw out, the caseback stack and bracelet spread away, the
#                 movement rises, flips, and its tiers fan open; the second half mirrors the
#                 first, so the loop closes.
#   grand_tour -- an animation: reveal opens and dwells with the escapement running, then
#                 the movement's tiers fan open while the floating face stack lifts for
#                 headroom; everything mirrors closed again.
# The three animations run the escapement as `running` does, posed at every key.

_OSCILLATIONS = 4                                    # balance swings per loop
_BEATS = _OSCILLATIONS * 2                           # escape steps per loop
_BALANCE_AMPLITUDE_DEG = 75.0
_ESCAPE_STEP_DEG = 360.0 / S.ESCAPE_WHEEL_TEETH / 2  # half a tooth pitch: 12 deg
_PALLET_BANK_DEG = 8.0
_STEP_FRACTION = 0.25                                # fraction of a beat spent mid-snap
_KEY_STEP = 0.02                                     # s between an animation's sampled keys


def _smooth(t: float) -> float:
    x = min(1.0, max(0.0, t))
    return x * x * (3.0 - 2.0 * x)


def _stage(t: float, a: float, b: float) -> float:
    """Staged smoothstep: 0 before a, 1 after b."""
    return _smooth((t - a) / (b - a))


def _snap(fraction: float) -> float:
    """Quick snap easing inside one beat: completes in _STEP_FRACTION of it."""
    return _smooth(fraction / _STEP_FRACTION)


# Staged reveal: (part, distance along its direction, start, end). The bezel stack and
# crystal lift clear first, then the dial floats up so the face (hands running) and the
# movement (flipped bridge-side-up in the case mouth, escapement beating) are BOTH visible.
_REVEAL_MOVES = (
    ("caseback_o_ring", 9.0, 0.0, 0.35),
    ("caseback_retaining_ring", 13.0, 0.03, 0.38),
    ("caseback", 18.0, 0.06, 0.42),
    ("caseback_sapphire", 24.0, 0.09, 0.45),
    ("movement_ring", 5.5, 0.0, 0.3),
    ("bezel_ring", 34.0, 0.05, 0.45),
    ("case_polish:bezel", 34.0, 0.05, 0.45),
    ("bezel_insert", 37.0, 0.05, 0.45),
    ("tachymeter_scale", 40.0, 0.05, 0.45),
    ("crystal", 48.0, 0.05, 0.45),
    ("crystal_gasket", 43.0, 0.05, 0.45),
    ("dial_and_hands", 26.0, 0.25, 0.6),
    ("strap_12", 9.0, 0.1, 0.5),
    ("strap_6", 9.0, 0.1, 0.5),
    ("clasp", 9.0, 0.1, 0.5),
)
_REVEAL_RISE = 16.0

# Grand tour: extra face-stack lift while the tiers are open.
_TOUR_HEADROOM = 32.0
_TOUR_HEADROOM_PARTS = ("dial_and_hands", "crystal", "crystal_gasket", "bezel_ring", "case_polish:bezel",
                        "bezel_insert", "tachymeter_scale")

# Showcase: the face stack clears out to the sides, the crown and pushers draw out along
# their axes (the pushers sit at 2 and 4 o'clock), each by its offset at full lateral...
_P2, _P4 = (0.866, 0.5, 0.0), (0.866, -0.5, 0.0)
_SHOWCASE_LATERALS = (
    ("dial_and_hands", (-40.0, 0.0, 12.0)), ("bezel_ring", (-48.0, 0.0, 14.0)),
    ("case_polish:bezel", (-48.0, 0.0, 14.0)), ("bezel_insert", (-52.0, 0.0, 16.0)),
    ("tachymeter_scale", (-56.0, 0.0, 18.0)), ("crystal", (40.0, 0.0, 12.0)), ("crystal_gasket", (35.0, 0.0, 9.0)),
    ("crown", (13.0, 0.0, 0.0)), ("crown_tube", (9.0, 0.0, 0.0)), ("crown_o_ring", (6.0, 0.0, 0.0)),
    *((f"pusher_{kind}:{clock}", tuple(c * reach for c in axis))
      for clock, axis in (("2oclock", _P2), ("4oclock", _P4))
      for kind, reach in (("cap", 11.0), ("tube", 8.0), ("spring", 5.5), ("o_ring", 3.5))),
)
# ... and the caseback stack and bracelet spread away, each along its direction.
_SHOWCASE_SPREADS = (
    ("movement_ring", 7.0), ("caseback_o_ring", 12.0), ("caseback_retaining_ring", 17.0),
    ("caseback", 23.0), ("caseback_sapphire", 30.0), ("spring_bar:12", 4.0),
    ("spring_bar:6", 4.0), ("strap_12", 14.0), ("strap_6", 14.0), ("clasp", 21.0),
)
_MOVEMENT_RISE = 30.0


def _reveal_stages(r: float) -> tuple[float, float]:
    """(rise, flip) of the movement at reveal openness r."""
    return _stage(r, 0.45, 0.85), _stage(r, 0.55, 0.92)


def _tour_stages(t: float) -> tuple[float, float]:
    """(r, f) at tour progress t: r the reveal openness (a trapezoid, open by 0.20 and
    closing from 0.83), f the tier fan (open 0.45..0.55, closed again by 0.83)."""
    return (
        min(_stage(t, 0.0, 0.2), _stage(1 - t, 0.0, 0.17)),
        min(_stage(t, 0.45, 0.55), _stage(1 - t, 0.17, 0.25)),
    )


def _showcase_stages(s: float) -> tuple[float, float, float, float, float]:
    """(lateral, spread, rise, flip, fan) at showcase progress s, keyed on min(s, 1 - s) so
    the reassembly half mirrors the expansion half and the loop is seamless."""
    u = min(s, 1 - s)
    return (
        _stage(u, 0.02, 0.17),
        _stage(u, 0.05, 0.25),
        _stage(u, 0.17, 0.34),
        _stage(u, 0.3, 0.38),
        _stage(u, 0.36, 0.42),
    )


def _escapement(run: float) -> dict:
    """The escapement and the two trains, ``run`` escapement loops in: the balance swings
    sinusoidally and beats on its zero crossings, the pallet fork snaps between banking
    positions once per beat, and each beat the escape wheel takes one crisp half-tooth step
    (12 deg, 0.2 s of the watch's time), the whole going train, the hands and the small
    seconds stepping with it through `running`; the chronograph runs through `chrono`, its
    runner and seconds hand one turn a loop."""
    beats = run * _BEATS
    beat = math.floor(beats)
    fraction = beats - beat
    return {
        "balance": _BALANCE_AMPLITUDE_DEG * math.sin(math.tau * _OSCILLATIONS * run),
        "pallet": (_PALLET_BANK_DEG if beat % 2 == 0 else -_PALLET_BANK_DEG) * (1 - 2 * _snap(fraction)),
        "running": _ESCAPE_STEP_DEG * (beat + _snap(fraction)) / _ESCAPE_DEG_PER_S,
        "chrono": 60.0 * run,
    }


def _choreograph(*, run: float = 0.0, reveal: float = 0.0, showcase: float = 0.0, tour: float = 0.0):
    """The watch on its four timelines (``reveal``, ``showcase`` and ``tour`` run 0..1, and
    ``run`` counts escapement loops): the escapement's values, each moved part's offset (mm,
    watch frame), the movement's rise (mm) and its flip (deg)."""
    s = min(1.0, max(0.0, showcase))
    tour_open, tour_fan = _tour_stages(min(1.0, max(0.0, tour)))
    rv = max(reveal, tour_open)          # the tour reuses the reveal for its open and close
    run = run + 2 * tour                 # three escapement loops per tour, counting on
    lateral, spread, rise, flip, fan = _showcase_stages(s)
    fan = max(fan, tour_fan)

    offsets: dict[str, list[float]] = {}

    def move(part: str, vector, amount: float) -> None:
        offset = offsets.setdefault(part, [0.0, 0.0, 0.0])
        for axis in range(3):
            offset[axis] += vector[axis] * amount

    for part, distance, a, b in _REVEAL_MOVES:
        move(part, _LIFTS[part], distance * _stage(rv, a, b))
    if s > 0:
        for part, vector in _SHOWCASE_LATERALS:
            move(part, vector, lateral)
        for part, distance in _SHOWCASE_SPREADS:
            move(part, _LIFTS[part], distance * spread)
    if tour_fan > 0:
        for part in _TOUR_HEADROOM_PARTS:
            move(part, _UP, _TOUR_HEADROOM * tour_fan)
    for parts, dz in _TIERS:
        for part in parts:
            move(part, _UP, dz * fan)

    # The movement rises out of the case and flips in place about its own centre.
    reveal_rise, reveal_flip = _reveal_stages(rv)
    return (_escapement(run), offsets, _MOVEMENT_RISE * rise + _REVEAL_RISE * reveal_rise,
            180.0 * min(1.0, flip + reveal_flip))


def _running(t: float) -> dict:
    return _escapement(t / 6)


def _reveal(t: float):
    progress = t / 12
    # A trapezoid: open, hold with the face and escapement both running in view, close.
    if progress < 0.35:
        r = _smooth(progress / 0.35)
    elif progress < 0.65:
        r = 1.0
    else:
        r = _smooth((1 - progress) / 0.35)
    return _choreograph(reveal=r, run=progress)


def _showcase(t: float):
    progress = t / 12
    return _choreograph(showcase=progress, run=progress)


def _grand_tour(t: float):
    progress = t / 24
    return _choreograph(tour=progress, run=progress)


def _held_keys(times: list[float], values: list) -> list[tuple[float, object]]:
    """``values`` at ``times`` as keys, dropping a key whose neighbours hold its value."""
    last = len(times) - 1
    return [(times[i], values[i]) for i in range(len(times))
            if i in (0, last) or not values[i - 1] == values[i] == values[i + 1]]


def _exploded_clip(root, name: str, duration: float, timeline) -> None:
    """The GLB animation ``name``: ``timeline(t)`` sampled every ``_KEY_STEP`` as LINEAR keys,
    the escapement posed at each, every moved part translated, and the movement rising and
    turning about X through its own centre. The tiers' translations are inside the movement,
    so its flip carries them, as the old clip composed them."""
    show = animation(root, name, duration=duration)
    count = round(duration / _KEY_STEP)
    times = [duration * i / count for i in range(count + 1)]
    frames = [timeline(t) for t in times]
    show.pose(at={t: frame[0] for t, frame in zip(times, frames)}, interpolation="LINEAR")
    for part in sorted({part for frame in frames for part in frame[1]}):
        offsets = [tuple(frame[1].get(part, (0.0, 0.0, 0.0))) for frame in frames]
        if any(any(offset) for offset in offsets):
            show.channel(part, path="translation", keys=_held_keys(times, offsets), interpolation="LINEAR")
    rises = [(0.0, 0.0, frame[2]) for frame in frames]
    turns = [(math.sin(math.radians(frame[3]) / 2), 0.0, 0.0, math.cos(math.radians(frame[3]) / 2)) for frame in frames]
    show.channel("movement", path="translation", keys=_held_keys(times, rises), interpolation="LINEAR")
    show.channel("movement", path="rotation", keys=_held_keys(times, turns), about=_MOVEMENT_CENTER,
                 interpolation="LINEAR")


# ---------------------------------------------------------------------------
# The watch
# ---------------------------------------------------------------------------

def _movement():
    """The cased movement: its three layers (the `@memo` layers `movement.py` composes) in
    `caliber`, flipped about X and lifted into the case, inside `movement`, which rises."""
    base = movement_base.movement_base()
    base.label = "movement_base"
    keyless = keyless_works.keyless_works()
    keyless.label = "keyless_works"
    chrono = chrono_works.chrono_works()
    chrono.label = "chronograph_works"
    return bd.Compound(children=[base, keyless, chrono], label="caliber"), chrono


def _movement_ring():
    """Fills the annulus between the movement OD and the case interior, so the caseback window
    shows metal, not void. The cut over/under-shoots to avoid coplanar-face booleans; the
    cased movement spans watch z 0.96..7.7."""
    ring = bd.Pos(0, 0, 1.0) * bd.Cylinder(15.6, 6.7, align=(None, None, None)) - bd.Pos(0, 0, 0.9) * bd.Cylinder(
        S.MOVEMENT_DIAMETER / 2 + 0.05, 7.0, align=(None, None, None))
    ring.color = bd.Color(S.STEEL_DARK)
    ring.label = "movement_ring"
    ring.material = M.FINISHES["satin_steel"]
    return ring


@model
def moonwatch():
    case = watch.case()

    dial = watch.dial()
    dial.label = "dial_and_hands"

    bracelet = watch.bracelet()

    caliber, chrono = _movement()
    # The movement's own joints, authored in its frame before it is cased.
    caliber_parts = _Parts(caliber)
    _train(caliber_parts, caliber, chrono)
    # cased: local (x, y, z) -> watch (x, -y, MOVT_Z_OFFSET - z)
    caliber.location = bd.Location((0, 0, S.MOVT_Z_OFFSET), (1, 0, 0), 180)
    movement = bd.Compound(children=[caliber], label="movement")

    root = bd.Compound(children=[case, dial, bracelet, movement, _movement_ring()], label="moonwatch")
    parts = _Parts(root)
    _hands(parts, dial)
    _crown_and_pushers(parts)

    _couplings_and_poses(root)
    # Each clip ends on the pose it starts from; a player repeats it (neither a motion nor
    # an animation has a loop).
    configuration_sequence(root, "running", _running, duration=6)
    _exploded_clip(root, "reveal", 12, _reveal)
    _exploded_clip(root, "showcase", 12, _showcase)
    _exploded_clip(root, "grand_tour", 24, _grand_tour)
    return root


if __name__ == "__main__":
    moonwatch()
