"""Dial + hands builder for the moonwatch chronograph.

Exposes `build_dial_parts()` returning labeled, colored parts in the WATCH
frame (`_spec.py` header): +Z through the crystal, 12 o'clock at +Y, crown
at +X, dial top surface at `S.DIAL_Z`.

Anatomy (matched to Speedmaster-professional macro references):

- step dial: main lacquer surface at DIAL_Z, outer minute-track ring dropped
  by a crisp step; three registers sunk 0.5 below the surface behind a bright
  45-degree chamfered rim step, each floored by a slightly darker snailed disc
  (the classic tri-compax depth read)
- applied hour indices: polished-steel picture-frame batons — 45-degree
  chamfered outer top edges and an inner bevel falling into the pocket, both
  built constructively with tapered extrudes — around a recessed off-white
  lume fill (lume top 0.05 below the frame rim); doubled baton at 12 with two
  lume dots outboard on the track ring
- printed minute track: 60 minute ticks + 4 fine subdivisions between each
  (300 ticks, exact 1.2 degree pitch)
- printed register tracks + numerals (30-min: 10/20/30, 12-h: 3/6/9/12,
  small seconds: 20/40/60) — no brand text anywhere
- hands set to 10:09:38, chronograph zeroed, recorders at zero
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import spec as S
from lib import finishing as F

# ---------------------------------------------------------------------------
# Derived frame constants (all from _spec; local values are dial-anatomy only)
# ---------------------------------------------------------------------------

DIAL_R = S.DIAL_DIAMETER / 2.0          # 18.6
DIAL_TOP = S.DIAL_Z                     # 8.35
DIAL_BOT = DIAL_TOP - S.DIAL_THICKNESS  # 7.7 — movement seat plane (unchanged)

STEP_R = 16.35                          # step-dial shoulder radius
STEP_DROP = 0.12
STEP_TOP = DIAL_TOP - STEP_DROP         # minute-track ring surface

RECESS_R = S.SUBDIAL_DIAMETER / 2.0     # 4.1
RECESS_FLOOR = DIAL_TOP - S.SUBDIAL_RECESS  # 7.85 — visible snailed floor
FLOOR_THICK = 0.05                      # darker floor disc set into the pocket
POCKET_FLOOR = RECESS_FLOOR - FLOOR_THICK   # 7.80 plate pocket under the disc
RIM_CHAMFER = 0.15                      # 45-deg bright rim step at each recess

TRACK_OUTER_R = 18.1                    # minute-track tick outer radius
PRINT_RAISE = 0.02                      # printed features stand this proud
PRINT_EMBED = 0.04                      # printed bodies sink into the dial

INDEX_R_IN = 12.4                       # hour baton radial span
INDEX_R_OUT = 16.1
INDEX_R_MID = (INDEX_R_IN + INDEX_R_OUT) / 2.0
INDEX_LEN = INDEX_R_OUT - INDEX_R_IN
INDEX_RAISE = 0.18                      # applied-index relief height
INDEX_EMBED = 0.06
INDEX_CHAMFER = 0.08                    # 45-deg bevel on the frame's outer top edges
INDEX_RIM_BEVEL = 0.05                  # 45-deg inner bevel falling into the lume pocket
INDEX_LUME_DROP = 0.05                  # lume fill sits this far below the frame rim

# registers: role -> center in watch frame
REGISTERS = {
    "minutes30": (S.SUBDIAL_RADIUS, 0.0),    # 3 o'clock, 30-min recorder
    "hours12": (0.0, -S.SUBDIAL_RADIUS),     # 6 o'clock, 12-hour recorder
    "seconds": (-S.SUBDIAL_RADIUS, 0.0),     # 9 o'clock, small seconds
}

# displayed time 10:09:38 — angles clockwise from 12 (+Y)
HOUR_ANGLE = (10.0 + (9.0 + 38.0 / 60.0) / 60.0) * 30.0   # 304.82
MINUTE_ANGLE = (9.0 + 38.0 / 60.0) * 6.0                  # 57.8
CHRONO_ANGLE = 0.0                                        # zeroed at 12
SMALL_SECONDS_ANGLE = 38.0 * 6.0                          # 228.0
RECORDER_ANGLE = 0.0                                      # recorders at zero


def _cw(angle_deg: float, radius: float):
    """Point at `radius`, `angle_deg` clockwise from 12 o'clock (+Y)."""
    a = math.radians(angle_deg)
    return (radius * math.sin(a), radius * math.cos(a))


def _fuse(shapes):
    return shapes[0] + shapes[1:] if len(shapes) > 1 else shapes[0]


# ---------------------------------------------------------------------------
# Dial plate
# ---------------------------------------------------------------------------

def build_dial_plate():
    base = bd.Pos(0, 0, (DIAL_TOP + DIAL_BOT) / 2.0) * bd.Cylinder(
        DIAL_R, S.DIAL_THICKNESS
    )

    cutters = []

    # outer step: drop the minute-track ring below the main lacquer surface
    annulus = bd.Cylinder(DIAL_R + 1.0, 1.0) - bd.Cylinder(STEP_R, 1.2)
    cutters.append(bd.Pos(0, 0, STEP_TOP + 0.5) * annulus)

    # subdial recesses: one revolved-step cut per register — a 45-degree
    # chamfered rim (the bright ring that telegraphs depth head-on), a
    # straight wall, and a pocket floor that receives the darker snailed
    # floor disc (build_register_floors); plus the hand hole
    for cx, cy in REGISTERS.values():
        cutters.append(
            bd.Pos(cx, cy, DIAL_TOP - RIM_CHAMFER / 2.0)
            * bd.Cone(RECESS_R, RECESS_R + RIM_CHAMFER, RIM_CHAMFER)
        )
        cutters.append(
            bd.Pos(cx, cy, DIAL_TOP + 0.25) * bd.Cylinder(RECESS_R + RIM_CHAMFER, 0.5)
        )
        cutters.append(bd.Pos(cx, cy, POCKET_FLOOR + 0.5) * bd.Cylinder(RECESS_R, 1.0))
        cutters.append(bd.Pos(cx, cy, DIAL_TOP - 0.3) * bd.Cylinder(0.25, 2.0))

    # center post hole (cannon pinion / chrono staff)
    cutters.append(bd.Pos(0, 0, DIAL_TOP - 0.3) * bd.Cylinder(0.75, 2.0))

    dial = base - cutters
    dial.label = "dial_plate"
    dial.color = bd.Color(*S.DIAL_BLACK)
    return dial


def build_register_floors():
    """Snailed counter floors: thin discs set into the plate pockets so they
    can carry their own tone — ~12% darker than DIAL_BLACK (inline color),
    the tri-compax floor contrast that reads as depth even head-on."""
    snail = F.snailing_cutter(
        S.SUBDIAL_DIAMETER, inner_diameter=0.7, pitch=0.3, groove_depth=0.015
    )
    floors = []
    for role, (cx, cy) in REGISTERS.items():
        disc = bd.Pos(cx, cy, (POCKET_FLOOR + RECESS_FLOOR) / 2.0) * bd.Cylinder(
            RECESS_R + 0.03, FLOOR_THICK  # 0.03 embeds into the pocket wall
        )
        disc = disc - [
            bd.Pos(cx, cy, RECESS_FLOOR) * snail,
            bd.Pos(cx, cy, RECESS_FLOOR - 0.5) * bd.Cylinder(0.25, 2.0),
        ]
        disc.label = f"subdial_floor:{role}"
        disc.color = bd.Color(0.033, 0.033, 0.039, 1.0)  # ~12% under DIAL_BLACK
        floors.append(disc)
    return floors


def build_dial_feet():
    feet = []
    for name, angle in (("upper", 45.0), ("lower", 225.0)):
        x, y = _cw(angle, 12.9)
        foot = bd.Pos(x, y, DIAL_BOT - 0.7) * bd.Cylinder(0.5, 1.4)
        foot.label = f"dial_foot:{name}"
        foot.color = bd.Color(*S.BRASS_MOVEMENT)
        feet.append(foot)
    return feet


# ---------------------------------------------------------------------------
# Applied indices + lume
# ---------------------------------------------------------------------------

def build_indices():
    frame_out, frame_in, lume_in = [], [], []

    for h in range(1, 12):  # single batons at 1..11
        if h in (3, 6, 9):
            # truncated at the register recesses (period-correct): the sunken
            # counters reach r = 14.45, so these batons start outboard of the
            # rim instead of overhanging the pits
            r_in = 14.75
        else:
            r_in = INDEX_R_IN
        r_mid = (r_in + INDEX_R_OUT) / 2.0
        length = INDEX_R_OUT - r_in
        loc = bd.Rot(0, 0, -h * 30.0) * bd.Pos(0, r_mid)
        frame_out.append(loc * bd.Rectangle(1.05, length))
        frame_in.append(loc * bd.Rectangle(0.67, length - 0.38))
        lume_in.append(loc * bd.Rectangle(0.61, length - 0.44))

    for dx in (-0.72, 0.72):  # doubled baton at 12
        loc = bd.Pos(dx, INDEX_R_MID)
        frame_out.append(loc * bd.Rectangle(0.85, INDEX_LEN))
        frame_in.append(loc * bd.Rectangle(0.49, INDEX_LEN - 0.38))
        lume_in.append(loc * bd.Rectangle(0.43, INDEX_LEN - 0.44))

    # polished-steel picture-frame batons, bevels built constructively:
    # - straight prism up to (rim - chamfer)
    # - tapered cap extrude (+45 deg shrinks) = chamfered outer top edges
    # - tapered cavity cutter (-45 deg flares) = inner bevel into the pocket
    # leaving a narrow flat top land between two light-catching facets
    z0 = DIAL_TOP - INDEX_EMBED
    rim = DIAL_TOP + INDEX_RAISE
    outer_sk = _fuse(frame_out)
    inner_sk = _fuse(frame_in)
    body = bd.Pos(0, 0, z0) * bd.extrude(
        outer_sk, INDEX_EMBED + INDEX_RAISE - INDEX_CHAMFER
    )
    cap = bd.Pos(0, 0, rim - INDEX_CHAMFER) * bd.extrude(
        outer_sk, INDEX_CHAMFER, taper=45
    )
    pocket = bd.Pos(0, 0, z0 - 0.1) * bd.extrude(
        inner_sk, INDEX_EMBED + INDEX_RAISE + 0.2
    )
    rim_bevel = bd.Pos(0, 0, rim - INDEX_RIM_BEVEL) * bd.extrude(
        inner_sk, INDEX_RIM_BEVEL + 0.05, taper=-45
    )
    frames = (body + cap) - [pocket, rim_bevel]
    frames.label = "index_frame:batons"
    frames.color = bd.Color(*S.STEEL_BRIGHT)

    lume_sk = _fuse(lume_in)
    lume = bd.Pos(0, 0, z0) * bd.extrude(
        lume_sk, INDEX_EMBED + INDEX_RAISE - INDEX_LUME_DROP
    )

    # two lume dots outboard of the doubled 12 baton, on the track ring
    dot_sk = _fuse([bd.Pos(dx, 16.85) * bd.Circle(0.38) for dx in (-0.72, 0.72)])
    dots = bd.Pos(0, 0, STEP_TOP - INDEX_EMBED) * bd.extrude(
        dot_sk, INDEX_EMBED + INDEX_RAISE + 0.02
    )
    lume = lume + dots
    lume.label = "index_lume"
    lume.color = bd.Color(*S.LUME)
    return [frames, lume]


# ---------------------------------------------------------------------------
# Printed minute track (exact 1.2-degree pitch, 300 ticks)
# ---------------------------------------------------------------------------

def build_minute_track():
    ticks = []
    for k in range(300):
        a = k * 1.2
        if k % 5 == 0:  # minute tick
            w, length = 0.14, 1.5
        else:  # 1/5 subdivision tick
            w, length = 0.085, 0.75
        ticks.append(
            bd.Rot(0, 0, -a)
            * bd.Pos(0, TRACK_OUTER_R - length / 2.0)
            * bd.Rectangle(w, length)
        )
    sk = _fuse(ticks)
    track = bd.Pos(0, 0, STEP_TOP - PRINT_EMBED) * bd.extrude(
        sk, PRINT_EMBED + PRINT_RAISE
    )
    track.label = "minute_track"
    track.color = bd.Color(*S.DIAL_PRINT)
    return track


# ---------------------------------------------------------------------------
# Register print (ticks + numerals) on the snailed floors
# ---------------------------------------------------------------------------

_REGISTER_NUMERALS = {
    "minutes30": (("10", 120.0), ("20", 240.0), ("30", 0.0)),
    "hours12": (("3", 90.0), ("6", 180.0), ("9", 270.0), ("12", 0.0)),
    "seconds": (("20", 120.0), ("40", 240.0), ("60", 0.0)),
}


def build_register_print(role: str):
    if role == "hours12":
        n, pitch, long_every = 12, 30.0, 3
    else:
        n, pitch, long_every = 30, 12.0, 5

    shapes = []
    for i in range(n):
        a = i * pitch
        if i % long_every == 0:
            w, length, r_mid = 0.10, 0.85, 3.425
        else:
            w, length, r_mid = 0.065, 0.50, 3.60
        shapes.append(bd.Rot(0, 0, -a) * bd.Pos(0, r_mid) * bd.Rectangle(w, length))

    for txt, a in _REGISTER_NUMERALS[role]:
        x, y = _cw(a, 2.3)
        shapes.append(bd.Pos(x, y) * bd.Text(txt, font_size=1.5, font="Arial"))

    cx, cy = REGISTERS[role]
    body = bd.Pos(cx, cy, RECESS_FLOOR - PRINT_EMBED) * bd.extrude(
        _fuse(shapes), PRINT_EMBED + PRINT_RAISE
    )
    body.label = f"subdial_print:{role}"
    body.color = bd.Color(*S.DIAL_PRINT)
    return body


# ---------------------------------------------------------------------------
# Hands
# ---------------------------------------------------------------------------

def _roof(half_width: float, ridge_height: float, length: float = 25.0):
    """Gable prism running along Y: apex ridge at x=0, z=ridge_height,
    falling to z=0 at |x|=half_width. Intersect with a plan extrusion to
    give a hand blade its diamond section — two beveled facets meeting in
    a longitudinal ridge, thin knife edges at the sides."""
    profile = bd.Plane.XZ * bd.Polygon(
        (-half_width, 0.0), (half_width, 0.0), (0.0, ridge_height), align=None
    )
    return bd.extrude(profile, amount=length, both=True)


def _faceted_blade(plan_sk, roof_half: float, ridge_h: float, z0: float):
    """Extrude a plan sketch and intersect with the facet roof; base at z0."""
    return bd.Pos(0, 0, z0) * (bd.extrude(plan_sk, ridge_h) & _roof(roof_half, ridge_h))


def _domed_cap(radius: float, z_bottom: float, z_shoulder: float, dome_r: float):
    """Turned polished cap: cylinder with a spherical dome that meets the
    cylindrical wall exactly at z_shoulder (screw-head dome construction)."""
    h = z_shoulder - z_bottom
    cyl = bd.Pos(0, 0, z_bottom + h / 2.0) * bd.Cylinder(radius, h)
    center_z = z_shoulder - math.sqrt(dome_r**2 - radius**2)
    return cyl & (bd.Pos(0, 0, center_z) * bd.Sphere(dome_r))


def build_hands():
    parts = []

    # ---- hour hand: thin tapered diamond-section blade, lume window ----
    hour_plan = bd.Polygon(
        (-0.60, -2.4), (0.60, -2.4), (0.60, 1.6),
        (0.32, 11.2), (0.14, S.HAND_HOUR_LENGTH),        # 12.0 reach
        (-0.14, S.HAND_HOUR_LENGTH), (-0.32, 11.2), (-0.60, 1.6),
        align=None,
    )
    hour_window = bd.Pos(0, 7.1) * bd.Rectangle(0.52, 5.4)     # y 4.4..9.8
    hour = _faceted_blade(hour_plan - hour_window, 0.75, 0.22, 8.45)
    hour = bd.Rot(0, 0, -HOUR_ANGLE) * hour
    # polished-steel blade: the facet ridge splits it into two mirror bevels
    # and the through-cut lume window leaves raised rails either side of the
    # recessed fill (rail tops ~0.14 above base vs 0.10 lume)
    hour.label = "hand:hour"
    hour.color = bd.Color(*S.DIAL_PRINT)

    hour_lume = bd.Pos(0, 0, 8.45) * bd.extrude(bd.Pos(0, 7.1) * bd.Rectangle(0.46, 5.34), 0.10)
    hour_lume = bd.Rot(0, 0, -HOUR_ANGLE) * hour_lume
    hour_lume.label = "hand:hour_lume"
    hour_lume.color = bd.Color(*S.LUME)

    hour_hub = bd.Pos(0, 0, 8.47) * bd.Cylinder(1.15, 0.20) + bd.Pos(0, 0, 8.63) * bd.Cylinder(
        0.72, 0.12
    )
    hour_hub.label = "hub:hour"
    hour_hub.color = bd.Color(*S.STEEL_BRIGHT)
    parts += [hour, hour_lume, hour_hub]

    # ---- minute hand: longer, slimmer blade above the hour hand ----
    minute_plan = bd.Polygon(
        (-0.52, -2.6), (0.52, -2.6), (0.52, 1.6),
        (0.26, 15.6), (0.11, S.HAND_MINUTE_LENGTH),      # 16.6 reach
        (-0.11, S.HAND_MINUTE_LENGTH), (-0.26, 15.6), (-0.52, 1.6),
        align=None,
    )
    minute_window = bd.Pos(0, 9.6) * bd.Rectangle(0.38, 8.4)   # y 5.4..13.8
    minute = _faceted_blade(minute_plan - minute_window, 0.65, 0.20, 8.73)
    minute = bd.Rot(0, 0, -MINUTE_ANGLE) * minute
    minute.label = "hand:minute"
    minute.color = bd.Color(*S.DIAL_PRINT)

    minute_lume = bd.Pos(0, 0, 8.73) * bd.extrude(
        bd.Pos(0, 9.6) * bd.Rectangle(0.32, 8.34), 0.08
    )
    minute_lume = bd.Rot(0, 0, -MINUTE_ANGLE) * minute_lume
    minute_lume.label = "hand:minute_lume"
    minute_lume.color = bd.Color(*S.LUME)

    # cannon-pinion cap under the chrono hand: turned two-step collar
    minute_hub = bd.Pos(0, 0, 8.79) * bd.Cylinder(0.95, 0.16) + bd.Pos(0, 0, 8.915) * bd.Cylinder(
        0.55, 0.09
    )
    minute_hub.label = "hub:minute"
    minute_hub.color = bd.Color(*S.STEEL_BRIGHT)
    parts += [minute, minute_lume, minute_hub]

    # ---- chronograph seconds: needle blade + tapered teardrop tail ----
    needle = bd.Polygon(
        (0.17, -1.2), (0.13, 0.0),
        (0.045, S.HAND_CHRONO_LENGTH - 0.3),             # 18.0 reach
        (0.018, S.HAND_CHRONO_LENGTH), (-0.018, S.HAND_CHRONO_LENGTH),
        (-0.045, S.HAND_CHRONO_LENGTH - 0.3),
        (-0.13, 0.0), (-0.17, -1.2),
        align=None,
    )
    teardrop = bd.Polygon(
        (-0.42, -3.5), (0.42, -3.5), (0.135, -0.8), (-0.135, -0.8), align=None
    ) + bd.Pos(0, -3.85) * bd.Circle(0.5)
    chrono = _faceted_blade(needle + teardrop, 0.62, 0.16, 8.99)
    chrono = bd.Rot(0, 0, -CHRONO_ANGLE) * chrono
    chrono.label = "hand:chrono_seconds"
    chrono.color = bd.Color(*S.DIAL_PRINT)
    parts.append(chrono)

    # polished domed cap over the chrono staff — top of the center stack
    cap = _domed_cap(0.72, 8.97, 9.13, 2.0)
    cap.label = "hand:chrono_cap"
    cap.color = bd.Color(*S.STEEL_BRIGHT)
    parts.append(cap)

    # ---- register hands: tiny faceted blades on turned hubs ----
    register_angles = {
        "minutes30": RECORDER_ANGLE,
        "hours12": RECORDER_ANGLE,
        "seconds": SMALL_SECONDS_ANGLE,
    }
    for role, angle in register_angles.items():
        plan = bd.Polygon(
            (0.10, -0.9), (0.075, 0.0),
            (0.03, S.HAND_SUBDIAL_LENGTH),               # 3.6 reach
            (-0.03, S.HAND_SUBDIAL_LENGTH),
            (-0.075, 0.0), (-0.10, -0.9),
            align=None,
        )
        # dropped with the deepened counters: ride just above the 7.85 floors
        # (floor print tops at 7.87), still well below the 8.35 main surface
        blade = _faceted_blade(plan, 0.13, 0.10, 7.95)
        hub = bd.Pos(0, 0, 7.97) * bd.Cylinder(0.40, 0.16)
        hand = blade + hub
        cx, cy = REGISTERS[role]
        hand = bd.Pos(cx, cy, 0) * (bd.Rot(0, 0, -angle) * hand)
        hand.label = f"hand:sub_{role}"
        hand.color = bd.Color(*S.DIAL_PRINT)
        parts.append(hand)

    return parts


# ---------------------------------------------------------------------------
# Entry aggregation
# ---------------------------------------------------------------------------

def build_dial_parts():
    parts = [build_dial_plate()]
    parts += build_register_floors()
    parts += build_dial_feet()
    parts += build_indices()
    parts.append(build_minute_track())
    for role in REGISTERS:
        parts.append(build_register_print(role))
    parts += build_hands()
    return parts
