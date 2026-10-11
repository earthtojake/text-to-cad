"""Full watch assembly: case + dial/hands + movement + bracelet.

Children are sibling models, composed by FUNCTION: calling a child inside
this body builds it if stale (on its own worker, in parallel with its
siblings) or loads it. Each child already authors its parts in the WATCH frame (see
`lib/spec.py`), so placements are identity — except the movement, which is
cased via the documented flip about X + MOVT_Z_OFFSET lift.

Articulation is split the way cadgen splits it: typed mates in `KINEMATICS`
below (the watch's real degrees of freedom — hands, going train, escapement,
chronograph, crown, pushers — plus the gear ratios that tie them together),
and choreography in the `ANIMATION` clips below, baked to keyframes when the
watch builds (exploded reveals, the sinusoidal balance swing and the escape
wheel's per-beat snap, which are not linear gearings and so are not mates).
"""

import math

import bracelet
import cadgen
import case
import dial
import movement
from cadgen import build123d as bd
from cadgen import step

from lib import spec as S


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


# ---------------------------------------------------------------------------
# Animation — clips sampled to keyframes when the model builds
# ---------------------------------------------------------------------------
# The motion that is NOT kinematics: staged explodes, the sinusoidal balance
# swing and the escape wheel's per-beat snap (neither is a linear gearing, so
# neither is a mate), and the movement's lift-and-flip out of the case. Clips
# know nothing of the mates, so they restate the motion in a few lines of
# ratio math, about the same wheel centers the mates turn on.
#
#   running    — one seamless escapement loop, slow-motion macro pacing:
#                4 balance oscillations, 8 beats. The escape wheel advances
#                one half-tooth-pitch step per beat (8 x 12 deg = 96 deg =
#                exactly 4 tooth pitches of the 15-tooth wheel, so the loop
#                is seamless), the pallet fork snaps between banking
#                positions at each beat, the fourth/third wheels creep
#                spoke-symmetric increments, and the chronograph runs.
#   reveal     — staged partial explode: the caseback stack fans downward,
#                the movement ring drops clear, the box crystal and gasket
#                lift off the dial, the bracelet straps slide apart, and the
#                movement rises into the case mouth and flips bridge-side-up.
#   showcase   — full explode timeline: the dial, bezel stack and crystal fan
#                out to the sides, the caseback stack and bracelet spread
#                away, then the movement rises straight up the middle, flips,
#                and its own subassembly fans open in tiers. The second half
#                mirrors the first, so the watch reassembles and the loop
#                closes.
#   grand_tour — reveal opens and dwells with the escapement running, then
#                the movement's tiers fan open while the floating face stack
#                lifts for headroom; everything mirrors closed again.
#
# All run rotations are about watch +Z through each wheel center. Every
# target is emitted as ONE chain, rotations BEFORE the summed translation, and
# successive handle calls PREMULTIPLY: a part turns about its rest pivot, then
# translates, and the movement's flip and rise wrap everything inside it last.

_X_AXIS = (1.0, 0.0, 0.0)

# Escapement pacing, per run loop.
_OSCILLATIONS = 4                                    # balance swings per loop
_BEATS = _OSCILLATIONS * 2                           # escape steps per loop
_BALANCE_AMPLITUDE_DEG = 75.0
_ESCAPE_STEP_DEG = 360.0 / S.ESCAPE_WHEEL_TEETH / 2  # half a tooth pitch: 12 deg
_PALLET_BANK_DEG = 8.0
_STEP_FRACTION = 0.25                                # fraction of a beat spent mid-snap


def _smooth(t: float) -> float:
    x = min(1.0, max(0.0, t))
    return x * x * (3.0 - 2.0 * x)


def _stage(t: float, a: float, b: float) -> float:
    """Staged smoothstep: 0 before a, 1 after b."""
    return _smooth((t - a) / (b - a))


def _snap(fraction: float) -> float:
    """Quick snap easing inside one beat: completes in _STEP_FRACTION of it."""
    return _smooth(fraction / _STEP_FRACTION)


# Parts and groups are targeted by label. The movement-base parts the showcase
# tiers fan but nothing else names are targeted by occurrence id: the base is
# the movement's first child, and the movement the watch's fourth.
_MOVEMENT_BASE = "#o1.4.1"


def _base(first: int, last: int) -> list[str]:
    """Movement-base children first..last, by occurrence id."""
    return [f"{_MOVEMENT_BASE}.{index}" for index in range(first, last + 1)]


_BALANCE_GROUP = (
    "#balance_wheel", "#balance_staff", "#impulse_jewel",
    *(f"#timing_screw:{i}" for i in range(16)),
)
_PALLET_GROUP = ("#pallet_fork", "#pallet_stone:entry", "#pallet_stone:exit", "#pallet_arbor")

# Staged reveal translations: (target, direction, distance, start, end). The
# bezel stack and crystal lift clear first, then the dial floats up so the
# face (hands running) and the movement (flipped bridge-side-up in the case
# mouth, escapement beating) are BOTH visible, vertically separated.
_REVEAL_MOVES = (
    ("#caseback_o_ring", (0, 0, -1), 9.0, 0.0, 0.35),
    ("#caseback_retaining_ring", (0, 0, -1), 13.0, 0.03, 0.38),
    ("#caseback", (0, 0, -1), 18.0, 0.06, 0.42),
    ("#caseback_sapphire", (0, 0, -1), 24.0, 0.09, 0.45),
    ("#movement_ring", (0, 0, -1), 5.5, 0.0, 0.3),
    ("#bezel_ring", (0, 0, 1), 34.0, 0.05, 0.45),
    ("#case_polish:bezel", (0, 0, 1), 34.0, 0.05, 0.45),
    ("#bezel_insert", (0, 0, 1), 37.0, 0.05, 0.45),
    ("#tachymeter_scale", (0, 0, 1), 40.0, 0.05, 0.45),
    ("#crystal", (0, 0, 1), 48.0, 0.05, 0.45),
    ("#crystal_gasket", (0, 0, 1), 43.0, 0.05, 0.45),
    ("#dial_and_hands", (0, 0, 1), 26.0, 0.25, 0.6),
    ("#strap_12", (0, 1, 0), 9.0, 0.1, 0.5),
    ("#strap_6", (0, -1, 0), 9.0, 0.1, 0.5),
    ("#clasp", (0, -1, 0), 9.0, 0.1, 0.5),
)

# Reveal movement lift-and-flip: once the caseback stack is away and the dial
# is rising, the movement climbs into the case mouth and turns
# bridge-side-up so the beating escapement faces the same camera as the
# floating dial.
_REVEAL_RISE = 16.0


def _reveal_stages(r: float) -> tuple[float, float]:
    """(rise, flip) of the movement at reveal openness r."""
    return _stage(r, 0.45, 0.85), _stage(r, 0.55, 0.92)


# Grand tour timeline: reveal opens and dwells with the escapement running,
# then the movement's tiers fan open showcase-style while the floating face
# stack rises further to make room; everything mirrors closed again so the
# loop is seamless.
_TOUR_HEADROOM = 32.0  # extra face-stack lift while the tiers are open
_TOUR_HEADROOM_TARGETS = (
    "#dial_and_hands", "#crystal", "#crystal_gasket", "#bezel_ring",
    "#case_polish:bezel", "#bezel_insert", "#tachymeter_scale",
)


def _tour_stages(t: float) -> tuple[float, float]:
    """(r, f) at tour progress t: r is the reveal openness (a trapezoid, open
    by 0.20 and closing from 0.83), f the gear-tier fan (open 0.45..0.55,
    closed again by 0.83)."""
    return (
        min(_stage(t, 0.0, 0.2), _stage(1 - t, 0.0, 0.17)),
        min(_stage(t, 0.45, 0.55), _stage(1 - t, 0.17, 0.25)),
    )


# --- showcase choreography ---------------------------------------------------
# The dial, bezel stack and crystal clear out to the SIDES so the movement can
# rise straight up the middle; the caseback stack and bracelet spread away.
# Lateral offsets keep every disc's center at least (disc radius + movement
# radius) from the rise corridor. Pushers sit at 2 and 4 o'clock and spread
# out along their own axes.
_P2, _P4 = (tuple(-c for c in _pusher_direction(angle)) for angle in S.PUSHER_ANGLES)

# (target, offset at full lateral stage).
_SHOWCASE_LATERALS = (
    ("#dial_and_hands", (-40, 0, 12)),
    ("#bezel_ring", (-48, 0, 14)),
    ("#case_polish:bezel", (-48, 0, 14)),
    ("#bezel_insert", (-52, 0, 16)),
    ("#tachymeter_scale", (-56, 0, 18)),
    ("#crystal", (40, 0, 12)),
    ("#crystal_gasket", (35, 0, 9)),
    ("#crown", (13, 0, 0)),
    ("#crown_tube", (9, 0, 0)),
    ("#crown_o_ring", (6, 0, 0)),
    ("#pusher_cap:2oclock", (_P2[0] * 11, _P2[1] * 11, 0)),
    ("#pusher_tube:2oclock", (_P2[0] * 8, _P2[1] * 8, 0)),
    ("#pusher_spring:2oclock", (_P2[0] * 5.5, _P2[1] * 5.5, 0)),
    ("#pusher_o_ring:2oclock", (_P2[0] * 3.5, _P2[1] * 3.5, 0)),
    ("#pusher_cap:4oclock", (_P4[0] * 11, _P4[1] * 11, 0)),
    ("#pusher_tube:4oclock", (_P4[0] * 8, _P4[1] * 8, 0)),
    ("#pusher_spring:4oclock", (_P4[0] * 5.5, _P4[1] * 5.5, 0)),
    ("#pusher_o_ring:4oclock", (_P4[0] * 3.5, _P4[1] * 3.5, 0)),
)

# (target, offset at full spread stage): the caseback stack and bracelet.
_SHOWCASE_SPREADS = (
    ("#movement_ring", (0, 0, -7)),
    ("#caseback_o_ring", (0, 0, -12)),
    ("#caseback_retaining_ring", (0, 0, -17)),
    ("#caseback", (0, 0, -23)),
    ("#caseback_sapphire", (0, 0, -30)),
    ("#spring_bar:12", (0, 4, 0)),
    ("#spring_bar:6", (0, -4, 0)),
    ("#strap_12", (0, 14, 0)),
    ("#strap_6", (0, -14, 0)),
    ("#clasp", (0, -21, 0)),
)

# Movement subassembly tiers, (targets, pre-flip z offset; negative = bridge
# side, so after the 180 deg flip these tiers stack UPWARD with the
# chronograph works on top). Applied with the fan sub-stage, in the movement's
# pre-parent frame so the group flip + rise carries them.
_MOVEMENT_TIERS = (
    (("#keyless_works",), 7.0),
    ((*_base(14, 20), *_base(63, 67)), -5.0),   # going train + escapement
    (_base(10, 13), -8.0),                      # barrel
    (_base(68, 74), -11.5),                     # pallet bridge
    ((*_base(34, 47), *_base(51, 53)), -15.5),  # train bridge
    ((*_base(21, 33), *_base(48, 50)), -15.5),  # barrel bridge
    (_base(54, 62), -19.0),                     # ratchet, crown wheel, click
    (_base(75, 105), -24.0),                    # balance + cock + shock
    (("#chronograph_works",), -30.0),
)

_MOVEMENT_RISE = 30.0
_MOVEMENT_CENTER = (0.0, 0.0, 1.7)


def _showcase_stages(s: float) -> tuple[float, float, float, float, float]:
    """(lateral, spread, rise, flip, fan) at showcase progress s, keyed on
    min(s, 1 - s) so the reassembly half mirrors the expansion half exactly
    and the loop is seamless."""
    u = min(s, 1 - s)
    return (
        _stage(u, 0.02, 0.17),
        _stage(u, 0.05, 0.25),
        _stage(u, 0.17, 0.34),
        _stage(u, 0.3, 0.38),
        _stage(u, 0.36, 0.42),
    )


# --- the one choreography routine -------------------------------------------
def _choreograph(m, *, run: float = 0.0, reveal: float = 0.0, showcase: float = 0.0, tour: float = 0.0) -> None:
    """Pose the watch on its four timelines: `reveal`, `showcase` and `tour`
    run 0..1, and `run` counts escapement loops. Each clip below drives them."""
    s = min(1.0, max(0.0, showcase))
    tour_open, tour_fan = _tour_stages(min(1.0, max(0.0, tour)))
    # The tour timeline reuses the reveal choreography for its open/close.
    rv = max(reveal, tour_open)
    # Three escapement loops per tour cycle: run + 2 * tour sweeps 0..3 when
    # the grand tour drives both with the same progress, and is plain `run`
    # whenever tour is 0. The count runs on rather than wrapping each loop: a
    # clip is baked to keyframes, and a wheel snapped back a whole loop would
    # spin backwards between two of them.
    run = run + 2 * tour
    lateral, spread, rise, flip, fan = _showcase_stages(s)

    # Per-target accumulators: rotations happen first (about the original
    # pivots), then one summed translation. Each target gets one m.get chain.
    rotations: dict[str, list[tuple[tuple, float]]] = {}
    offsets: dict[str, list[float]] = {}

    def add_rot(target: str, pivot: tuple, deg: float) -> None:
        rotations.setdefault(target, []).append((pivot, deg))

    def add_move(target: str, vector: tuple, scale: float) -> None:
        if not scale:
            return
        offset = offsets.setdefault(target, [0.0, 0.0, 0.0])
        for axis in range(3):
            offset[axis] += vector[axis] * scale

    # --- reveal ---------------------------------------------------------------
    for target, direction, distance, a, b in _REVEAL_MOVES:
        add_move(target, direction, distance * _stage(rv, a, b))

    # --- showcase -------------------------------------------------------------
    if s > 0:
        for target, vector in _SHOWCASE_LATERALS:
            add_move(target, vector, lateral)
        for target, vector in _SHOWCASE_SPREADS:
            add_move(target, vector, spread)
        for targets, dz in _MOVEMENT_TIERS:
            for target in targets:
                add_move(target, (0, 0, dz), fan)

    # --- grand tour: fan the movement tiers in the reveal pose -----------------
    if tour_fan > 0:
        for targets, dz in _MOVEMENT_TIERS:
            for target in targets:
                add_move(target, (0, 0, dz), tour_fan)
        for target in _TOUR_HEADROOM_TARGETS:
            add_move(target, (0, 0, 1), _TOUR_HEADROOM * tour_fan)

    # --- escapement -----------------------------------------------------------
    beats = run * _BEATS
    beat = math.floor(beats)
    beat_fraction = beats - beat

    # Balance: sinusoidal oscillation; beats land on its zero crossings.
    balance_deg = _BALANCE_AMPLITUDE_DEG * math.sin(math.tau * _OSCILLATIONS * run)
    for target in _BALANCE_GROUP:
        add_rot(target, _W_BALANCE, balance_deg)

    # Pallet fork: snaps between banking positions once per beat.
    from_bank = _PALLET_BANK_DEG if beat % 2 == 0 else -_PALLET_BANK_DEG
    pallet_deg = from_bank * (1 - 2 * _snap(beat_fraction))
    for target in _PALLET_GROUP:
        add_rot(target, _W_PALLET, pallet_deg)

    # Escape wheel: one crisp half-tooth step per beat, released as the pallet
    # snaps. 8 steps x 12 deg = 4 whole tooth pitches per loop.
    escape_deg = _ESCAPE_STEP_DEG * (beat + _snap(beat_fraction))
    for target in ("#escape_wheel", "#escape_pinion"):
        add_rot(target, _W_ESCAPE, escape_deg)

    # Going train creeps against the escape wheel: alternating directions,
    # spoke-and-tooth-symmetric 144 deg per loop so the seam is invisible.
    train_deg = 144 * run
    for target in ("#fourth_wheel", "#fourth_pinion"):
        add_rot(target, _W_FOURTH, -train_deg)
    for target in ("#third_wheel", "#third_pinion"):
        add_rot(target, _W_THIRD, train_deg)

    # Small seconds hand rides the fourth-wheel arbor (clockwise from dial).
    add_rot("#hand:sub_seconds", _W_FOURTH, -train_deg)

    # Chronograph shown running: the center runner sweeps one full turn per loop
    # (full revolutions are always seam-free), the coupling wheel counter-
    # rotates, and the chrono seconds hand rides the runner arbor.
    runner_deg = -360 * run
    for target in (
        "#chrono_runner_wheel", "#chrono_runner_heart_cam", "#chrono_runner_arbor",
        "#hand:chrono_seconds", "#hand:chrono_cap",
    ):
        add_rot(target, _W_CENTER, runner_deg)
    add_rot("#coupling_wheel", _W_COUPLING, 360 * run)

    # --- emit ------------------------------------------------------------------
    for target in dict.fromkeys([*rotations, *offsets]):
        handle = m.get(target)
        for pivot, deg in rotations.get(target, ()):
            handle.rotate(_UP, deg, pivot)
        if target in offsets:
            handle.translate(offsets[target])

    # Movement group: flip in place about its own center (child tiers and gear
    # pivots compose in pre-parent space), then rise out of the case. Reveal and
    # showcase both drive this; their contributions add (in practice one is
    # active at a time).
    reveal_rise, reveal_flip = _reveal_stages(rv)
    movement_flip = min(1.0, flip + reveal_flip)
    movement_rise = _MOVEMENT_RISE * rise + _REVEAL_RISE * reveal_rise
    if movement_flip > 0 or movement_rise > 0:
        m.get("#movement").rotate(_X_AXIS, 180 * movement_flip, _MOVEMENT_CENTER).translate((0, 0, movement_rise))


def _running(t: float, m) -> None:
    _choreograph(m, run=t / 6)


def _reveal(t: float, m) -> None:
    progress = t / 12
    # Trapezoid timeline: open, hold with the face and escapement both running
    # in view, then close — so the loop is seamless.
    if progress < 0.35:
        r = _smooth(progress / 0.35)
    elif progress < 0.65:
        r = 1.0
    else:
        r = _smooth((1 - progress) / 0.35)
    _choreograph(m, reveal=r, run=progress)


def _showcase(t: float, m) -> None:
    progress = t / 12
    _choreograph(m, showcase=progress, run=progress)


def _grand_tour(t: float, m) -> None:
    progress = t / 24
    _choreograph(m, tour=progress, run=progress)


ANIMATION = {
    "running": cadgen.clip(_running, duration=6, label="Escapement running"),
    "reveal": cadgen.clip(_reveal, duration=12, label="Reveal movement"),
    "showcase": cadgen.clip(_showcase, duration=12, label="Showcase explode"),
    "grand_tour": cadgen.clip(_grand_tour, duration=24, label="Grand tour"),
}


@step(out="../STEP/moonwatch.step", kinematics=KINEMATICS, animation=ANIMATION)
def moonwatch():
    children = []

    case_parts = case.case()
    case_parts.label = "case"
    children.append(case_parts)

    dial_parts = dial.dial()
    dial_parts.label = "dial_and_hands"
    children.append(dial_parts)

    bracelet_parts = bracelet.bracelet()
    bracelet_parts.label = "bracelet"
    children.append(bracelet_parts)

    movement_parts = movement.movement()
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
    return compound


if __name__ == "__main__":
    moonwatch()
