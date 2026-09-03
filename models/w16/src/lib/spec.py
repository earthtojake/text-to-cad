"""W16 master spec — the single source of truth for every shared number.

ENGINE FRAME (all builders author directly in this frame, in mm)
  X   crank axis. +X = FRONT (timing drive, damper/pulley). -X = rear (flywheel,
      bell-housing face).
  Z   up.  Y lateral: +Y = bank 1 (cylinders 1-8), -Y = bank 2 (cylinders 9-16).
  Crank angle theta: right-hand rotation about +X. A radial direction at
  "angle a" is p(a) = (0, -sin a, cos a): a is measured from +Z toward -Y, so it
  INCREASES with theta.  Bank 1 sits at negative a, bank 2 at positive a.

ARCHITECTURE (settled against public references — see README):
  8.0 L (7993 cc), 86 x 86 mm, two narrow-angle VR8 banks (15 deg within a bank,
  rows at +/-7.5 deg from the bank centreline) set 90 deg apart on one crank.
  8 crankpins, each shared by one bank-1 rod and one bank-2 rod (cylinder i and
  i+8). Rows alternate along each bank (VR fashion) and the two rods on a pin
  belong to OPPOSITE rows (inner+outer), which is what makes every pin's two
  cylinders fire exactly 90 deg apart and the whole engine fire evenly at 45 deg.
  Firing order 1-14-9-4-7-12-15-6-13-8-3-16-11-2-5-10 (Bugatti's published order,
  cylinders numbered front to rear, 1-8 bank 1, 9-16 bank 2). The pin phasing is
  DERIVED from that order + even firing; it is not published.
  Cylinder axes are desaxe: each row's axis is offset DESAXE mm from the crank
  axis, away from the bank centreline (the VR6's 12.5 mm trick, which is what
  lets 86 mm bores sit 74 mm apart along the crank).
  Valvetrain: 4 cams (intake + exhaust per bank), each serving BOTH rows of its
  bank through roller finger followers on hydraulic pivots — one cam line cannot
  serve two rows of bucket tappets, and this is how real VR 4-valve heads do it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Bottom end
# ---------------------------------------------------------------------------

BORE = 86.0
STROKE = 86.0
THROW = STROKE / 2.0                 # crank radius
ROD_LEN = 148.0                      # centre to centre
ROD_BIG_END_W = 19.0                 # along X, one rod
ROD_SMALL_END_W = 24.0
PIN_D = 54.0                         # crankpin (rod journal) diameter
PIN_LEN = 40.0                       # two 19 mm rods + clearance
MAIN_D = 70.0                        # main journal diameter
MAIN_LEN = 20.0
WEB_T = 7.0                          # thin web beside a main journal
PIN_PITCH = 74.0                     # every pin, uniform
N_PINS = 8
PIN_X = [259.0 - PIN_PITCH * i for i in range(N_PINS)]   # pin 1 (front) .. pin 8
# Mains: front, between pin pairs (2|3, 4|5, 6|7), rear.
MAIN_X = [296.0, 148.0, 0.0, -148.0, -296.0]
CRANK_NOSE_X = (306.0, 380.0)        # nose journal region (front main .. damper face)
CRANK_FLANGE_X = -320.0              # flywheel flange face
COUNTERWEIGHT_R = 78.0               # outer radius of the counterweights
CRANKCASE_CLEAR_R = 88.0             # nothing static inside this radius over the bays (rods sweep R 86)

ROD_X_OFFSET = 10.0                  # bank-1 rod at pin_x + 10, bank-2 rod at pin_x - 10

# Piston
PISTON_CH = 30.0                     # compression height: pin centre -> crown centre
PISTON_H = 52.0                      # crown centre -> skirt bottom
WRIST_PIN_D = 22.0
WRIST_PIN_LEN = 62.0
RING_GROOVES = [(4.0, 1.2), (7.0, 1.2), (11.0, 2.5)]   # (depth below crown, width)

# ---------------------------------------------------------------------------
# W geometry
# ---------------------------------------------------------------------------

BANK_HALF = 45.0                     # bank centrelines at +/-45 deg from vertical
ROW_HALF = 7.5                       # rows at +/-7.5 deg from the bank centreline
DESAXE = 15.0                        # bore-axis offset from the crank axis
DECK_H = 226.0                       # deck plane distance from crank axis, along the bank centreline
BORE_BOTTOM_S = 62.0                 # bore ends this far along the bore axis from its foot point (opens fully into the R86 tunnel: at 88 a shelf remained that the swinging rods clipped)
CYL_LINER_WALL = 4.5

# Slot in the 16-step firing sequence for each cylinder (0 = fires first).
FIRING_ORDER = [1, 14, 9, 4, 7, 12, 15, 6, 13, 8, 3, 16, 11, 2, 5, 10]
FIRING_INTERVAL = 720.0 / 16.0       # 45 deg


def firing_slot(cyl: int) -> int:
    return FIRING_ORDER.index(cyl)


def bank_of(cyl: int) -> int:
    """1 for cylinders 1-8 (+Y), 2 for 9-16 (-Y)."""
    return 1 if cyl <= 8 else 2


def pin_index(cyl: int) -> int:
    """0-based crankpin index shared by cylinder i and i+8."""
    return (cyl - 1) % 8


def row_of(cyl: int) -> str:
    """'inner' (nearer the engine centre plane) or 'outer'."""
    i = pin_index(cyl) + 1            # 1-based pin number
    if bank_of(cyl) == 1:
        return "inner" if i % 2 == 1 else "outer"
    return "outer" if i % 2 == 1 else "inner"


def bore_angle(cyl: int) -> float:
    """Bore-axis angle a (deg) in the p(a) convention (negative = bank 1 / +Y)."""
    mag = BANK_HALF - ROW_HALF if row_of(cyl) == "inner" else BANK_HALF + ROW_HALF
    return -mag if bank_of(cyl) == 1 else mag


def bank_angle(bank: int) -> float:
    return -BANK_HALF if bank == 1 else BANK_HALF


def tdc_angle(cyl: int) -> float:
    """Crank angle (deg, 0..720) at which the cylinder is at firing TDC."""
    return firing_slot(cyl) * FIRING_INTERVAL


def pin_angle(pin: int) -> float:
    """Crankpin direction angle a at theta = 0 for 0-based pin index (deg, 0..360)."""
    cyl = pin + 1                                   # bank-1 cylinder on this pin
    return (bore_angle(cyl) - tdc_angle(cyl)) % 360.0


def radial(a_deg: float):
    """Unit vector p(a) = (0, -sin a, cos a)."""
    a = math.radians(a_deg)
    return (0.0, -math.sin(a), math.cos(a))


def lateral(a_deg: float):
    """Unit vector perpendicular to p(a) in the YZ plane, = p(a + 90):
    (0, -cos a, -sin a). Rotating p by +90 deg about +X."""
    a = math.radians(a_deg)
    return (0.0, -math.cos(a), -math.sin(a))


def toward_centre(cyl: int):
    """Unit vector perpendicular to the bore axis, pointing toward the engine
    centre plane (y = 0)."""
    lat = lateral(bore_angle(cyl))
    # lateral() for negative a (bank 1, +Y side) has -Y component -> toward centre.
    return lat if bank_of(cyl) == 1 else (0.0, -lat[1], -lat[2])


def cylinder_x(cyl: int) -> float:
    x = PIN_X[pin_index(cyl)]
    return x + ROD_X_OFFSET if bank_of(cyl) == 1 else x - ROD_X_OFFSET


def bore_foot(cyl: int):
    """Point on the bore axis nearest the crank axis (the desaxe offset), in YZ,
    as a 3D point at the cylinder's x."""
    d = DESAXE if row_of(cyl) == "inner" else -DESAXE
    tc = toward_centre(cyl)
    return (cylinder_x(cyl), d * tc[1], d * tc[2])


@dataclass(frozen=True)
class Cylinder:
    number: int
    bank: int
    pin: int                 # 0-based
    row: str
    x: float                 # bore axis x
    angle: float             # bore-axis angle a
    axis: tuple              # unit direction along the bore, away from the crank
    foot: tuple              # point on the bore axis (its desaxe foot)
    toward_centre: tuple     # unit, perpendicular to axis, toward y = 0
    tdc: float               # crank angle of firing TDC (0..720)
    pin_angle: float         # pin direction angle at theta = 0

    def point(self, s: float, lat: float = 0.0):
        """Point on/near the bore axis: s along the axis from the foot, lat toward centre."""
        return (
            self.x,
            self.foot[1] + s * self.axis[1] + lat * self.toward_centre[1],
            self.foot[2] + s * self.axis[2] + lat * self.toward_centre[2],
        )


def cylinder(cyl: int) -> Cylinder:
    return Cylinder(
        number=cyl,
        bank=bank_of(cyl),
        pin=pin_index(cyl),
        row=row_of(cyl),
        x=cylinder_x(cyl),
        angle=bore_angle(cyl),
        axis=radial(bore_angle(cyl)),
        foot=bore_foot(cyl),
        toward_centre=toward_centre(cyl),
        tdc=tdc_angle(cyl),
        pin_angle=pin_angle(pin_index(cyl)),
    )


CYLINDERS = [cylinder(c) for c in range(1, 17)]


# ---------------------------------------------------------------------------
# Bank frame helpers: c = bank centreline (up), m = toward the engine centre.
# ---------------------------------------------------------------------------

def bank_up(bank: int):
    return radial(bank_angle(bank))


def bank_m(bank: int):
    """Unit vector in the deck plane, perpendicular to X, toward the engine centre."""
    lat = lateral(bank_angle(bank))
    return lat if bank == 1 else (0.0, -lat[1], -lat[2])


def bank_point(bank: int, x: float, m: float, h: float):
    """Engine-frame point from bank coordinates: x along the crank, m toward
    centre (in the deck plane), h up the bank centreline from the crank axis."""
    up = bank_up(bank)
    mm = bank_m(bank)
    return (x, m * mm[1] + h * up[1], m * mm[2] + h * up[2])


def bank_of_point_m_h(bank: int, p):
    """Inverse of bank_point for the YZ part: returns (m, h)."""
    up = bank_up(bank)
    mm = bank_m(bank)
    return (p[1] * mm[1] + p[2] * mm[2], p[1] * up[1] + p[2] * up[2])


# ---------------------------------------------------------------------------
# Top end (bank coordinates unless stated)
# ---------------------------------------------------------------------------

HEAD_H = 132.0                       # deck -> head top face (= cam centreline plane), along c
CAM_CAP_H = 28.0                     # cam caps above the head top face
COVER_JOINT_H = 226.0 + 132.0 + 28.0 # cam cover joint plane (h)
HEAD_M_HALF = 130.0                  # head half-width across the bank (m)
CHAMBER_DEPTH = 14.0                 # pent-roof ridge above the deck plane (along c)
# ALL intake valves lean VALVE_LEAN deg from the bank centreline toward the engine
# centre and ALL exhaust valves lean the same amount outboard, whichever row they
# sit in (so the two rows differ in where their valves stand, not how they lean).
# Pent-roof planes are perpendicular to the valve axes.
VALVE_LEAN = 20.0
VALVE_LATERAL = 18.5                 # seat centre offset from the ridge, measured IN the roof plane
VALVE_X_HALF = 19.0                  # the two valves of one type sit at x +/- this
INTAKE_HEAD_D = 30.0
EXHAUST_HEAD_D = 26.0
VALVE_STEM_D = 6.0
VALVE_LEN = 108.0                    # seat plane -> stem tip
SPRING_OD = 30.0
SPRING_WIRE_D = 3.6
SPRING_INSTALLED_H = 40.0
SPRING_SEAT_S = 52.0                 # seat plane -> spring seat, along the valve axis
VALVE_LIFT = 10.0
INTAKE_DURATION = 250.0              # crank deg
EXHAUST_DURATION = 250.0
INTAKE_CENTRE = 470.0                # crank deg after firing TDC (intake stroke, 110 ATDC)
EXHAUST_CENTRE = 250.0               # crank deg after firing TDC (exhaust stroke, 110 BTDC)
CAM_BASE_R = 15.0
CAM_LOBE_W = 12.0
CAM_JOURNAL_D = 28.0
# Cam axes in bank coordinates (m, h): intake toward centre, exhaust outboard.
CAM_M = {"intake": 55.0, "exhaust": -55.0}
CAM_H = DECK_H + 132.0
ROLLER_R = 8.0
ROLLER_W = 9.0
FOLLOWER_T = 8.0                     # finger follower thickness along X
FOLLOWER_H = 9.0                     # follower beam depth
PIVOT_BALL_R = 5.0
# Finger-follower pivot (hydraulic lash adjuster) positions, per (row, type), in m.
# Pivot sits on the far side of the cam from the valve tip.
FOLLOWER_PIVOT_M = {
    ("inner", "intake"): 8.0,
    ("outer", "intake"): 105.0,
    ("inner", "exhaust"): -105.0,
    ("outer", "exhaust"): -8.0,
}
FOLLOWER_H_BAND = DECK_H + 104.0     # h of the pivot balls (valve tips land within ~1 mm of it)
PAD_R = 6.0                          # follower's valve-tip pad radius (cylindrical, axis along X)

# ---------------------------------------------------------------------------
# Cam drive (front of the engine). One chain loop per bank: crank sprocket ->
# exhaust cam sprocket -> intake cam sprocket -> crank, tensioner on the slack run.
# ---------------------------------------------------------------------------

CHAIN_PITCH_NOMINAL = 6.35           # 1/4" timing chain; the solver trims it so each loop closes on whole links
CRANK_SPROCKET_T = 20
CAM_SPROCKET_T = 40
CHAIN_ROLLER_D = 4.0
CHAIN_PIN_D = 2.4
CHAIN_PLATE_T = 1.0
CHAIN_PLATE_H = 5.6                  # plate height across the pitch line
CHAIN_INNER_W = 4.0                  # between inner plates (roller width)
CHAIN_W = 8.4                        # overall link width along X
CHAIN_X = {1: 318.0, 2: 330.0}      # chain centre plane per bank (two crank sprocket rows)
CAM_FRONT_X = 306.0                  # front face of the heads / cam nose start

# ---------------------------------------------------------------------------
# Envelope targets
# ---------------------------------------------------------------------------

ENGINE_LENGTH_TARGET = 710.0
ENGINE_WIDTH_TARGET = 770.0
BLOCK_FRONT_X = 306.0
BLOCK_REAR_X = -318.0
BELL_FACE_X = -345.0
SUMP_RAIL_Z = -95.0                  # block/pan joint plane
SUMP_DEPTH = 55.0                    # shallow dry-sump pan

# The museum section: bank 1 statics are cut away for x > SECTION_X (front of
# cylinder 3's centreline), y > SECTION_Y_MIN (keeps the centre spine), z > SECTION_Z_MIN.
SECTION_BANK = 1
SECTION_X = 121.0                    # = cylinder_x(3)
SECTION_Y_MIN = 12.0
SECTION_Z_MIN = -95.0                # = SUMP_RAIL_Z: the crankcase's +y half is opened down to the pan rail for
                                     # x > SECTION_X, so cylinders 1-2 show piston, rod AND crank throw in profile


def check_spec():
    """Self-consistency checks. Raises on failure; returns a summary dict."""
    # even firing: every 45 deg slot used exactly once
    assert sorted(FIRING_ORDER) == list(range(1, 17))
    # each pin's two cylinders fire 90 deg apart
    for pin in range(8):
        a, b = pin + 1, pin + 9
        diff = (tdc_angle(b) - tdc_angle(a)) % 720.0
        assert diff in (90.0, 450.0), (pin, diff)
        assert {row_of(a), row_of(b)} == {"inner", "outer"}
    # bore spacing at the deck (3D distance between adjacent bore centres on the deck)
    def deck_hit(c: Cylinder):
        up = bank_up(c.bank)
        s = (DECK_H - (c.foot[1] * up[1] + c.foot[2] * up[2])) / (c.axis[1] * up[1] + c.axis[2] * up[2])
        return c.point(s), s
    out = {}
    min_d = 1e9
    for b in (1, 2):
        cyls = [c for c in CYLINDERS if c.bank == b]
        for i in range(len(cyls) - 1):
            p, _ = deck_hit(cyls[i])
            q, _ = deck_hit(cyls[i + 1])
            d = math.dist(p, q)
            min_d = min(min_d, d)
    out["min_deck_bore_spacing"] = min_d
    assert min_d > BORE + 2 * CYL_LINER_WALL - 1e-6, min_d
    out["pin_angles"] = [pin_angle(i) for i in range(8)]
    out["tdc"] = {c: tdc_angle(c) for c in range(1, 17)}
    return out


if __name__ == "__main__":
    import json

    print(json.dumps(check_spec(), indent=1))


# ---------------------------------------------------------------------------
# LAYOUT — interface stations shared between systems (engine frame, mm).
# Builders place their parts against these; change them here, never locally.
# ---------------------------------------------------------------------------

def sign_of_bank(bank: int) -> float:
    return 1.0 if bank == 1 else -1.0


# Exhaust port exits: on each head's OUTER face (m = -HEAD_M_HALF), h = DECK_H + 52,
# one Ø(EXHAUST_HEAD_D - 11) hole per valve at x = cylinder_x +/- VALVE_X_HALF.
EXHAUST_EXIT_M = -HEAD_M_HALF
EXHAUST_EXIT_H = DECK_H + 52.0
# Intake port exits: on each head's INNER face (m = +HEAD_M_HALF), h = DECK_H + 68.
INTAKE_EXIT_M = HEAD_M_HALF
INTAKE_EXIT_H = DECK_H + 68.0

# Turbochargers: two per bank, outboard and low, axes parallel to X. The
# turbine end faces the engine's x-centre (front turbo: turbine at -X end);
# the compressor faces outward along X. Cylinders 1-4 / 9-12 feed the front
# turbos, 5-8 / 13-16 the rear ones.
# Moved outboard/down after the first exhaust pass: with the axis at (400, 70)
# the turbine-inlet flange (axis z + 95) landed on the cam cover's outer bolt
# row (y ~349, z ~167) and left no corridor for Ø42 primaries. At (425, 25)
# the inlet sits at z 120, 45 mm under that row, with a clear run from the
# exhaust ports (y ~292, z ~101).
TURBO_AXIS_Y = 425.0                 # |y| of the turbo axis
TURBO_AXIS_Z = -20.0   # was 25: dropped 45 so the exhaust runners clear the turbine inlet flange under the cam-cover edge
TURBO_X = {"front": 130.0, "rear": -160.0}      # centre-housing x
TURBO_TURBINE_D = 150.0              # turbine housing envelope diameter
TURBO_COMPRESSOR_D = 165.0
TURBO_CENTRE_LEN = 90.0              # bearing housing length along X


def turbo(bank: int, pos: str) -> dict:
    s = sign_of_bank(bank)
    x = TURBO_X[pos]
    tdir = -1.0 if pos == "front" else 1.0        # turbine end direction along X
    return {
        "bank": bank, "pos": pos,
        "centre": (x, s * TURBO_AXIS_Y, TURBO_AXIS_Z),
        "axis": (1.0, 0.0, 0.0),
        "turbine_dir": tdir,                       # turbine wheel at centre + tdir * (CENTRE_LEN/2 + ...)
        "turbine_x": x + tdir * 60.0,
        "compressor_x": x - tdir * 62.0,
        # turbine inlet flange: on top of the turbine scroll, facing +Z, offset inboard
        "turbine_inlet": (x + tdir * 60.0, s * (TURBO_AXIS_Y - 30.0), TURBO_AXIS_Z + 95.0),
        "turbine_inlet_normal": (0.0, 0.0, 1.0),
        # compressor outlet: on top of the compressor scroll, facing +Z
        "compressor_outlet": (x - tdir * 62.0, s * (TURBO_AXIS_Y + 10.0), TURBO_AXIS_Z + 100.0),
        "compressor_outlet_normal": (0.0, 0.0, 1.0),
        # downpipe flange: below the turbine housing, facing -Z
        "downpipe_flange": (x + tdir * 60.0, s * TURBO_AXIS_Y, TURBO_AXIS_Z - 90.0),
    }


TURBOS = [turbo(b, p) for b in (1, 2) for p in ("front", "rear")]


def turbo_for(cyl: int) -> dict:
    pos = "front" if pin_index(cyl) < 4 else "rear"
    return turbo(bank_of(cyl), pos)


# Cam covers: from the cover joint plane (h = COVER_JOINT_H) up COVER_H, m +/- HEAD_M_HALF - 2,
# x from HEAD_REAR .. CAM_FRONT_X. Spark plugs: one per cylinder, axis from the
# chamber ridge to the point (m = 0, h = COVER_JOINT_H + COVER_H) — the two rows'
# plugs converge on the bank centreline, so each cover carries ONE row of 8 coils.
COVER_H = 46.0
PLUG_TOP_M = 0.0
PLUG_TOP_H = COVER_JOINT_H + COVER_H
PLUG_WELL_D = 30.0                   # well tube OD in the cover
PLUG_BORE_D = 16.0                   # hole through the head
HEAD_REAR_X = -300.0


def plug_axis(cyl: int):
    """(bottom_point, top_point) of the spark-plug axis, engine frame."""
    c = CYLINDERS[cyl - 1]
    up = bank_up(c.bank)
    h_ridge = DECK_H + CHAMBER_DEPTH
    s = (h_ridge - (c.foot[1] * up[1] + c.foot[2] * up[2])) / (c.axis[1] * up[1] + c.axis[2] * up[2])
    bottom = c.point(s)
    top = bank_point(c.bank, c.x, PLUG_TOP_M, PLUG_TOP_H)
    return bottom, top


# Induction. Plenums live in the valley, one per bank, hugging the head's inner
# face; intercoolers sit above them side by side; throttle bodies on the front
# end of each plenum; charge pipes climb the outside of the cam covers from the
# compressor outlets to the intercooler end tanks.
PLENUM_Z = (300.0, 400.0)            # z band of the plenum boxes
PLENUM_X = (-280.0, 280.0)
PLENUM_Y_INNER = 20.0                # |y| of the plenum's inner wall (gap between the two)
INTERCOOLER_Z = (412.0, 512.0)
INTERCOOLER_X = (-250.0, 250.0)
INTERCOOLER_Y = (18.0, 200.0)        # |y| band of each core (+ end tanks beyond)
THROTTLE_D = 82.0
THROTTLE_X = PLENUM_X[1] + 2.0       # throttle body sits on the plenum's front face
FUEL_RAIL_M = 156.0                  # outboard of the head's inner face (m = 130): the rail rides the shoulder above the runners
FUEL_RAIL_H = 360.0

# Oil system: dry sump. Pan below the block rail, scavenge/pressure pump stack
# on the bank-2 (-Y) side low at the front, filter housing on the bank-1 side.
PAN_Z = (SUMP_RAIL_Z - SUMP_DEPTH, SUMP_RAIL_Z)
PAN_Y_HALF = 165.0
PAN_X = (BLOCK_REAR_X + 4.0, BLOCK_FRONT_X - 4.0)
OIL_PUMP_CENTRE = (200.0, -240.0, -40.0)     # pump stack axis along X (was 250: the front sections ran into the water pump / hose / idler on the front face)
OIL_PUMP_LEN = 140.0
OIL_FILTER_CENTRE = (200.0, 260.0, -30.0)    # filter axis along Y (canister outboard)

# Front ancillaries, belt plane at x = BELT_X (a rib on the damper).
BELT_X = 372.0
ALTERNATOR = {"centre": (398.0, 262.0, -30.0), "axis": (1.0, 0.0, 0.0), "pulley_d": 62.0}
WATER_PUMP = {1: {"centre": (352.0, 190.0, 0.0), "pulley_d": 110.0},
              2: {"centre": (352.0, -190.0, 0.0), "pulley_d": 110.0}}
BELL_HOUSING_D = 430.0               # transaxle bell-housing face diameter at BELL_FACE_X


# ---------------------------------------------------------------------------
# Sump-pan bolt pattern — shared by the pan (oil_system) and the block's rail
# bosses/tappings, so it lives here (pure numbers; no module imports another).
# ---------------------------------------------------------------------------
PAN_FLANGE_W = 14.0
PAN_X0, PAN_X1 = -314.0, 302.0
PAN_R = 26.0
PAN_BOLT_PITCH = 60.0


def pan_perimeter_points(w, h, r, pitch):
    """Points at even `pitch` around a rounded rectangle in the pan's plan,
    returned as engine (x, y). The pitch is trimmed so the ring closes."""
    cx = (PAN_X0 + PAN_X1) / 2.0
    hw, hh = w / 2.0 - r, h / 2.0 - r
    segs = []

    def straight(p0, p1):
        L = math.dist(p0, p1)
        segs.append((L, lambda t, p0=p0, p1=p1, L=L:
                     (p0[0] + (p1[0] - p0[0]) * t / L,
                      p0[1] + (p1[1] - p0[1]) * t / L)))

    def arc(c, a0, a1):
        L = r * math.radians(a1 - a0)
        segs.append((L, lambda t, c=c, a0=a0, L=L:
                     (c[0] + r * math.cos(math.radians(a0) + t / r),
                      c[1] + r * math.sin(math.radians(a0) + t / r))))

    straight((hw + r, -hh), (hw + r, hh))
    arc((hw, hh), 0, 90)
    straight((hw, hh + r), (-hw, hh + r))
    arc((-hw, hh), 90, 180)
    straight((-hw - r, hh), (-hw - r, -hh))
    arc((-hw, -hh), 180, 270)
    straight((-hw, -hh - r), (hw, -hh - r))
    arc((hw, -hh), 270, 360)

    total = sum(s[0] for s in segs)
    n = max(4, int(round(total / pitch)))
    step = total / n
    out = []
    for i in range(n):
        s = i * step
        for L, fn in segs:
            if s <= L + 1e-9:
                p = fn(min(s, L))
                out.append((cx + p[0], p[1]))
                break
            s -= L
    return out



def pan_bolt_points():
    return pan_perimeter_points(PAN_X1 - PAN_X0 - PAN_FLANGE_W, 2 * PAN_Y_HALF - PAN_FLANGE_W,
                                PAN_R - 7.0, PAN_BOLT_PITCH)
