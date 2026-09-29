"""The radial's frame and every shared number. Everything downstream inherits these.

FRAME (engine frame, millimetres)
  Y   crank axis. +Y = REAR (accessory section), -Y = FRONT (propeller).
  Z   up. Cylinder 1 points straight up.
  X   completes a right-handed frame; seen from the FRONT (camera on -Y looking
      +Y) +X is to the viewer's right.
  Crank rotation is CLOCKWISE seen from the rear (US practice), i.e. a
  right-handed rotation about ROT_AXIS = (0, -1, 0). Cylinders are numbered in
  the same sense, so cylinder 2 is 40 deg from cylinder 1 toward -X.

IN-PLANE ANGLES
  An in-plane angle b is measured about ROT_AXIS from +Z: the unit vector at b is
  (-sin b, 0, cos b). Cylinder k sits at ALPHA(k) = 40 (k-1). The crank angle
  THETA is the in-plane angle of the crankpin; theta = 0 puts the pin on
  cylinder 1's axis: cylinder 1 at FIRING TDC. THE MODEL IS AUTHORED AT THETA = 0.

CYLINDER-LOCAL FRAME (author per-cylinder parts once, for cylinder 1)
  h  along the cylinder axis, measured from the crank axis   (cyl 1: +Z)
  y  along the crank axis, +rear                              (cyl 1: +Y)
  t  tangential = Y x u                                        (cyl 1: +X)
  `cyl_rotation(k)` maps the cylinder-1 frame onto cylinder k (a rotation of
  ALPHA(k) about ROT_AXIS through the origin). `t` points toward cylinder k-1.

SOURCES: see SOURCES below and the research notes; figures marked (design)
are layout choices made for beauty/clearance within the real envelope.
"""

from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# Architecture (sourced — see SOURCES)
# ---------------------------------------------------------------------------
N_CYL = 9
CYL_PITCH_DEG = 40.0
BORE = 146.0                 # 5.75 in (P&W R-1340 Wasp)
STROKE = 146.0               # 5.75 in
R_CRANK = STROKE / 2.0
FIRING_ORDER = (1, 3, 5, 7, 9, 2, 4, 6, 8)
FIRING_INTERVAL_DEG = 720.0 / N_CYL          # 80 deg
ROT_AXIS = (0.0, -1.0, 0.0)                  # right-handed crank rotation axis

# Cam ring: 4 lobes per track, two tracks (intake, exhaust), 1/8 crank speed,
# turning OPPOSITE the crank (the (n-1)/2-lobe solution for n = 9).
CAM_LOBES = 4
CAM_RATIO = -1.0 / 8.0

# Propeller reduction: planetary, ring (bell) gear driven by the crank, sun
# fixed to the nose case, planet carrier = propeller shaft. prop/crank = R/(R+S).
RED_RING_T = 72
RED_SUN_T = 36
RED_PLANET_T = 18
RED_PLANETS = 6
RED_RATIO = RED_RING_T / (RED_RING_T + RED_SUN_T)        # 2/3: prop turns with the crank
# (sourced: enginehistory.org R-1535 - crank-driven internal 'bell' gear, fixed sun, 6 pinions; R-1340 -G variants 3:2)

# Supercharger impeller gear ratio (impeller / crank), same sense as the crank.
BLOWER_RATIO = 10.0

SOURCES = {
    "reduction": "3:2 planetary: crank-driven internal bell gear, fixed sun, six pinions on a carrier splined to the prop shaft (enginehistory.org R-1340 / R-1535 pages)",
    "blower": "gear-driven centrifugal, 10:1 step-up, coaxial with the crank (Wikipedia R-1340; enginehistory.org)",
    "rotation": "clockwise viewed from the rear (US right-hand convention)",
    "rings": "six rings: 3 compression, 2 oil control, 1 scraper (enginehistory.org R-1340)",
    "bore_stroke_diameter": "R-1340 Wasp: 5.75 x 5.75 in, 1344 cu in, 51.75 in diameter "
                            "(Wikipedia 'Pratt & Whitney R-1340 Wasp'; FAA TCDS)",
    "firing_order": "9-cyl single-row four-stroke: every other cylinder, 1-3-5-7-9-2-4-6-8 "
                    "(FAA-H-8083-32 Powerplant Handbook, reciprocating engines)",
    "cam_ring": "(n-1)/2 = 4 lobes at 1/8 crank speed against the crank, or (n+1)/2 = 5 at 1/10 with it "
                "(FAA-H-8083-32); the Wasp's ring turns opposite the crank at 1/8 (enginehistory.org R-1340)",
}

# ---------------------------------------------------------------------------
# Crank train (design within the real envelope)
# ---------------------------------------------------------------------------
L_MASTER = 265.0             # master rod, crankpin centre to wrist pin centre
RHO_KNUCKLE = 62.0           # knuckle-pin circle radius about the crankpin
L_ART = L_MASTER - RHO_KNUCKLE   # articulating rod, knuckle pin to wrist pin (203)
# Knuckle-pin angle on the master-rod flange, measured from the master rod axis
# in the same sense as ALPHA. Equal to the cylinder angle (no compensation):
# the resulting per-cylinder stroke/TDC asymmetry is real and deliberate.
def KNUCKLE_ANGLE(k: int) -> float:
    return CYL_PITCH_DEG * (k - 1)

CRANKPIN_D = 70.0
CRANKPIN_LEN = 84.0          # between cheek faces, y in [-42, 42]
MAIN_JOURNAL_D = 80.0
CHEEK_Y = (42.0, 64.0)       # |y| span of each crank cheek (front cheek at -y)
COUNTERWEIGHT_R = 110.0      # max counterweight radius (piston skirts at BDC reach h ~124)

MASTER_BIG_END_W = 82.0      # |y| <= 41
MASTER_FLANGE_Y = (12.0, 26.0)   # the two flange plates occupy |y| in this span
KNUCKLE_PIN_D = 22.0
ART_ROD_EYE_W = 23.0         # articulating-rod knuckle eye, |y| <= 11.5
WRIST_PIN_D = 38.0

# ---------------------------------------------------------------------------
# Piston (design)
# ---------------------------------------------------------------------------
PISTON_COMPRESSION_H = 58.0  # wrist-pin centre to crown flat
PISTON_DOME = 4.0            # crown dome rise at the centre
PISTON_SKIRT_BELOW_PIN = 64.0
PISTON_LENGTH = PISTON_COMPRESSION_H + PISTON_SKIRT_BELOW_PIN

# ---------------------------------------------------------------------------
# Cylinder stations along h (design)
# ---------------------------------------------------------------------------
H_PAD = 282.0                # crankcase cylinder-pad face (barrel flange seat)
H_BARREL_SKIRT = 205.0       # barrel skirt bottom (inside the crankcase), trimmed to the cylinder wedge (geo.wedge_trim) so the ring belt stays in the bore at BDC
H_FLANGE_TOP = 294.0         # barrel hold-down flange top face
H_BORE_TOP = 402.0           # top of the parallel bore = base of the combustion chamber
BARREL_WALL_OD = 160.0
BARREL_FIN_PITCH = 6.0
BARREL_FIN_OD_BOTTOM = 186.0     # fins grow from the flange up
BARREL_FIN_OD_TOP = 204.0
HOLD_DOWN_STUDS = 12
HOLD_DOWN_PCD = 170.0

# ---------------------------------------------------------------------------
# Valvetrain (design). Both valves lie in the CYLINDER-ROW plane (the h-t plane,
# y = 0): intake on +t, exhaust on -t, hemispherical chamber, rockers on shafts
# running fore-aft (along y) in two side-by-side rocker boxes at the head top.
# Pushrods rise in front of each cylinder in a V from the nose-case tappets to
# the front ends of the rockers. Local cylinder-1 coordinates (h, y, t).
# ---------------------------------------------------------------------------
VALVE_INCLINE_DEG = 36.0          # each valve axis from the cylinder axis (72 deg included)
VALVE_SEAT_H = 440.0              # seat-face centre height
VALVE_SEAT_T = 37.0               # |t| of the seat centres
VALVE_LENGTH = 150.0              # seat face to stem tip
VALVE_HEAD_D = {"I": 60.0, "E": 55.0}
VALVE_STEM_D = 12.0
ROCKER_PIVOT = (576.0, 88.0)      # (h, |t|) of the rocker shaft axis (shaft runs along y)
ROCKER_SHAFT_Y = (-112.0, 14.0)   # shaft span (both boxes)
PUSHROD_SOCKET = (588.0, -100.0, 60.0)   # (h, y, |t|) pushrod-top ball centre on the rocker
TAPPET_DELTA_DEG = 4.0            # tappet in-plane offset from the cylinder axis (exhaust +, intake -)
TAPPET_SOCKET_R = 205.0           # pushrod-bottom ball centre radius, tappet on the base circle
# The whole nose section (cam, reduction, prop) sits NOSE_SHIFT forward of its
# first layout, joined to the crankcase by a slim neck, so the crankcase front
# window can be seen past it from a front three-quarter view.
NOSE_SHIFT = -130.0
NOSE_NECK_Y = (-112.0, -240.0)    # slim neck: crankcase front face -> cam section
NOSE_NECK_R = 115.0               # neck outer radius (the window shows outside it)
TAPPET_Y = {"I": -178.0 + NOSE_SHIFT, "E": -152.0 + NOSE_SHIFT}    # cam-track stations (tappet axes)
TAPPET_ROLLER_R = 12.5              # 150/12.5 = 12: the roller turns exactly 3 times per 720 deg cycle (seamless loop)
CAM_BASE_R = 150.0                # cam-ring base-circle radius (roller contact)
TAPPET_LIFT = {"I": 8.9, "E": 8.8}       # max tappet (pushrod) lift -> ~13.6 / ~13.4 valve lift
PUSHROD_D = 12.0
# Pushrod-tube ends, measured along the pushrod's rest axis: the tube's lower
# packing nut seats on the nose-case tappet-guide boss face at PUSHROD_TUBE_START
# from the bottom ball; its upper packing nut seats on the rocker-box inlet boss
# face PUSHROD_TUBE_END_FROM_TOP below the top ball.
PUSHROD_TUBE_START = 16.0
PUSHROD_TUBE_END_FROM_TOP = 34.0
# Rod small ends fit between the piston's pin bosses.
ROD_SMALL_END_HALF_W = 17.0
PISTON_PIN_BOSS_INNER_Y = 19.0
# Crank interfaces for gears other builders own.
CRANK_NOSE_FLANGE_Y = -256.0 + NOSE_SHIFT     # front face of the crank-nose flange the bell gear bolts to (Ø150, 8 bolts on PCD 125)
CRANK_NOSE_D = 60.0              # nose shaft; cam gear seat y (-140..-116) + NOSE_SHIFT
CRANK_REAR_D = 60.0              # rear shaft to y 146; blower gear seat y 129..143
PUSHROD_TUBE_OD = 24.0
# Valve timing, crank degrees (R-1340-class values): events relative to the
# cylinder's FIRING TDC.
VALVE_OPEN = {"E": 110.0, "I": 340.0}    # exhaust opens 70 BBDC, intake opens 20 BTDC
VALVE_DURATION = {"E": 270.0, "I": 260.0}  # exhaust closes 20 ATDC, intake closes 60 ABDC

# Cam-ring drive (inside the ring): crank gear -> fixed compound idler -> ring
# internal gear. (32/48) x (15/80) = 1/8; the external mesh reverses, the
# internal mesh keeps the idler's sense, so the ring turns AGAINST the crank.
CAM_CRANK_GEAR = (32, 2.5)             # (teeth, module) on the crank nose
CAM_IDLER = ((48, 2.5), (15, 100.0 / 32.5))   # big (meshes crank gear), small (meshes ring)
CAM_RING_GEAR = (80, 100.0 / 32.5)     # internal teeth on the cam ring, pitch r 123.1
CAM_IDLER_R = 100.0                    # idler axis radius (both meshes' centre distance)
CAM_IDLER_ANGLE = -30.0                # in-plane angle of the idler axis (inside the nose cutaway)
CAM_IDLER_Y = {"big": -128.0 + NOSE_SHIFT, "small": -150.0 + NOSE_SHIFT}   # gear face centres
CAM_RING_Y = (-192.0 + NOSE_SHIFT, -138.0 + NOSE_SHIFT)          # cam-ring axial extent (two lobe tracks + gear)

# Propeller reduction (planetary, see RED_* above): module 3, ring pitch r 108,
# sun r 54 (fixed), planets r 27 on a carrier at r 81 = the propeller shaft.
RED_MODULE = 3.0
RED_FACE_Y = (-300.0 + NOSE_SHIFT, -262.0 + NOSE_SHIFT)          # gear face span
RED_PLANET_R = RED_MODULE * (RED_SUN_T + RED_PLANET_T) / 2.0

# Supercharger drive (rear): crank gear -> three compound intermediates -> impeller pinion.
# (60/20) x (40/12) = 10; two external meshes -> impeller turns WITH the crank.
BLOWER_CRANK_GEAR = (60, 2.0)          # on the crank's rear extension
BLOWER_INTERMEDIATE = ((20, 2.0), (40, 80.0 / 26.0))
BLOWER_PINION = (12, 80.0 / 26.0)      # on the impeller shaft
BLOWER_INTERMEDIATE_R = 80.0
BLOWER_INTERMEDIATE_ANGLES = (60.0, 180.0, 300.0)
BLOWER_GEAR_Y = {"crank": 136.0, "pinion": 158.0}
IMPELLER_D = 280.0

# Crankcase (design)
CRANKCASE_Y = (-112.0, 112.0)    # power-section axial extent at the pads
CRANKCASE_R_BETWEEN = 262.0      # outer radius between pads

# Axial stations of the other sections (design, frame Y)
NOSE_Y = (-112.0, -395.0 + NOSE_SHIFT)        # nose section: crankcase front face -> thrust-bearing nose
REDUCTION_Y = (-250.0 + NOSE_SHIFT, -330.0 + NOSE_SHIFT)
PROP_HUB_Y = -470.0 + NOSE_SHIFT
BLOWER_Y = (112.0, 262.0)
ACCESSORY_Y = (262.0, 420.0)
IMPELLER_Y = 185.0


def ALPHA(k: int) -> float:
    return CYL_PITCH_DEG * (k - 1)


def inplane(b_deg: float, r: float = 1.0, y: float = 0.0):
    """Point at in-plane angle b (deg about ROT_AXIS from +Z), radius r, station y."""
    b = math.radians(b_deg)
    return (-r * math.sin(b), y, r * math.cos(b))


def cyl_u(k: int):
    return inplane(ALPHA(k))


def cyl_t(k: int):
    a = math.radians(ALPHA(k))
    return (math.cos(a), 0.0, math.sin(a))


def cyl_point(k: int, h: float, y: float = 0.0, t: float = 0.0):
    """Engine-frame point from cylinder-k local (h, y, t)."""
    u, tt = cyl_u(k), cyl_t(k)
    return (h * u[0] + t * tt[0], y, h * u[2] + t * tt[2])


def firing_tdc(k: int) -> float:
    """Crank angle (0..720) of cylinder k's firing TDC."""
    return ALPHA(k) + (360.0 if k % 2 == 0 else 0.0)


def check_spec() -> None:
    # every cylinder fires exactly once per 720 deg, 80 deg apart, in FIRING_ORDER
    events = sorted((firing_tdc(k) % 720.0, k) for k in range(1, N_CYL + 1))
    order = tuple(k for _, k in events)
    assert order == FIRING_ORDER, order
    gaps = {round(events[(i + 1) % N_CYL][0] - events[i][0]) % 720 for i in range(N_CYL)}
    assert gaps == {80}, gaps
    # cam ring: a lobe count / ratio pair that serves every cylinder once per cycle
    assert abs(abs(1.0 / CAM_RATIO) - 2 * CAM_LOBES) < 1e-9
    assert CAM_LOBES in ((N_CYL - 1) // 2, (N_CYL + 1) // 2)
    assert (CAM_RATIO < 0) == (CAM_LOBES == (N_CYL - 1) // 2)
    # gear trains close exactly
    (zc, _), ((zi1, _), (zi2, _)), (zr, _) = CAM_CRANK_GEAR, CAM_IDLER, CAM_RING_GEAR
    assert abs((zc / zi1) * (zi2 / zr) - abs(CAM_RATIO)) < 1e-12
    assert abs(CAM_CRANK_GEAR[0] * CAM_CRANK_GEAR[1] / 2 + CAM_IDLER[0][0] * CAM_IDLER[0][1] / 2 - CAM_IDLER_R) < 1e-9
    assert abs(CAM_RING_GEAR[0] * CAM_RING_GEAR[1] / 2 - CAM_IDLER[1][0] * CAM_IDLER[1][1] / 2 - CAM_IDLER_R) < 1e-9
    (bc, _), ((b1, _), (b2, _)), (bp, _) = BLOWER_CRANK_GEAR, BLOWER_INTERMEDIATE, BLOWER_PINION
    assert abs((bc / b1) * (b2 / bp) - BLOWER_RATIO) < 1e-12
    assert abs(bc * 2.0 / 2 + b1 * 2.0 / 2 - BLOWER_INTERMEDIATE_R) < 1e-9
    assert abs((b2 + bp) * BLOWER_PINION[1] / 2 - BLOWER_INTERMEDIATE_R) < 1e-9
    assert bc % 3 == 0 and bp % 3 == 0
    # planetary: ring = sun + 2 planet; planets assemble evenly
    assert RED_RING_T == RED_SUN_T + 2 * RED_PLANET_T
    assert (RED_RING_T + RED_SUN_T) % RED_PLANETS == 0


check_spec()
