"""Master dimensional spec for the retro scooter motorbike package.

An original, unbranded interpretation of the reference image
(`ref/motorbike.png` — Honda Giorno-style step-through scooter model kit,
cream body, brown saddle, black frame, silver engine). No logos, no badges,
no wordmarks. Dimensions are real-scooter scale taken from public Giorno-class
figures (wheelbase ~1190, seat height ~735, 10 in wheels) and treated as
design intent, not a dimensional contract.

Coordinate conventions:

- BIKE assembly frame: +X forward (front wheel), +Y rider left, +Z up.
  z = 0 is the ground plane; x = 0 at mid-wheelbase.
- Every part module authors its geometry DIRECTLY in the bike frame from the
  hardpoints in this file (moonwatch/f1 package pattern), so the assembly
  composes children at identity and still records the functional relationships
  (steering, wheel spin, engine swing) as native joints on world-coincident
  datum frames. See `motorbike.step.py`.
- Steering axis: through the FRONT_AXLE, tilted RAKE back from vertical,
  parameterized as FRONT_AXLE + t * STEER_DIR with t in mm along the axis.

Modeling rules (repo memory):
- No 3D fillet after large booleans (OCC segfault risk); use rounded 2D
  profiles, lofts, and chamfers.
- Accumulate boolean tools into one `base - [tools]` / `base + [tools]` call;
  never accumulate pairwise.
"""

from math import cos, sin, radians

# ---------------------------------------------------------------------------
# Palette (linear RGBA). Theme does not override source colors.
# ---------------------------------------------------------------------------

CREAM = (0.925, 0.895, 0.815, 1.0)        # body panels, retro ivory
CREAM_DEEP = (0.880, 0.845, 0.750, 1.0)   # under-seat body, inner covers
SEAT_BROWN = (0.400, 0.235, 0.115, 1.0)   # saddle
FRAME_BLACK = (0.075, 0.075, 0.085, 1.0)  # frame, fork, stand, bar
RUBBER = (0.055, 0.055, 0.060, 1.0)       # tires, grips
RIM_SILVER = (0.700, 0.710, 0.725, 1.0)   # cast wheels, brake disc
ENGINE_SILVER = (0.640, 0.650, 0.650, 1.0)  # crankcase, cylinder barrel
ENGINE_DARK = (0.330, 0.340, 0.345, 1.0)  # CVT / alternator covers
CHROME = (0.800, 0.820, 0.850, 1.0)       # headlight shell, muffler, mirrors
SHOCK_BODY = (0.120, 0.120, 0.130, 1.0)   # damper body
SPRING_YELLOW = (0.900, 0.700, 0.090, 1.0)
AMBER = (0.960, 0.520, 0.070, 0.95)       # turn-signal lenses
RED_LENS = (0.720, 0.055, 0.060, 0.95)    # tail-light lens
LENS_CLEAR = (0.930, 0.950, 0.960, 0.30)  # headlight lens
STEEL = (0.600, 0.610, 0.630, 1.0)        # axles, fasteners, pipes

# ---------------------------------------------------------------------------
# Wheels / axles
# ---------------------------------------------------------------------------

WHEELBASE = 1190.0

TIRE_OD_FRONT = 410.0        # 90/90-10 class
TIRE_OD_REAR = 426.0         # 100/90-10 class
TIRE_WIDTH_FRONT = 90.0
TIRE_WIDTH_REAR = 100.0
RIM_DIAMETER = 254.0         # 10 in bead seat
SPOKE_COUNT = 5              # cast five-spoke (reference shows cast wheels)

FRONT_AXLE = (595.0, 0.0, TIRE_OD_FRONT / 2)          # (595, 0, 205)
REAR_AXLE = (-595.0, 0.0, TIRE_OD_REAR / 2)           # (-595, 0, 213)
AXLE_DIAMETER = 12.0
BRAKE_DISC_DIAMETER = 185.0  # front only; rear is a drum in the hub

# ---------------------------------------------------------------------------
# Steering / front fork
# ---------------------------------------------------------------------------

RAKE = 27.0                                     # degrees from vertical
STEER_DIR = (-sin(radians(RAKE)), 0.0, cos(radians(RAKE)))  # up-backward


def steer_point(t: float) -> tuple[float, float, float]:
    """Point on the steering axis, t mm up-axis from the front axle."""
    return (
        FRONT_AXLE[0] + t * STEER_DIR[0],
        0.0,
        FRONT_AXLE[2] + t * STEER_DIR[2],
    )


HEAD_TUBE_BOT_T = 520.0    # head tube span along the steering axis
HEAD_TUBE_TOP_T = 640.0
STEM_TOP_T = 690.0         # handlebar clamp stem top

HEAD_TUBE_OD = 60.0
HEAD_TUBE_BORE = 40.0

FORK_LEG_OFFSET_Y = 62.0   # stanchion/sliders flank the tire
STANCHION_OD = 31.0        # upper tubes
SLIDER_OD = 27.0           # lower tubes
SLIDER_LEN_T = 300.0       # axle to stanchion pick-up along the axis
STANCHION_TOP_T = 620.0

# ---------------------------------------------------------------------------
# Handlebar
# ---------------------------------------------------------------------------

BAR_TUBE_OD = 25.0
BAR_HALF_WIDTH = 330.0
GRIP_LEN = 115.0
GRIP_OD = 32.0

# ---------------------------------------------------------------------------
# Frame hardpoints (underbone)
# ---------------------------------------------------------------------------

DOWNTUBE_OD = 26.0
DOWNTUBE_PATH = (           # (x, y, z) spline, head tube to floor pan
    (368.0, 32.0, 630.0),
    (340.0, 55.0, 540.0),
    (300.0, 70.0, 420.0),
    (230.0, 70.0, 310.0),
    (150.0, 70.0, 280.0),
)

FLOOR_X_FRONT = 250.0       # steel step-through floor pan
FLOOR_X_REAR = -70.0
FLOOR_HALF_WIDTH = 165.0
FLOOR_TOP_Z = 282.0
FLOOR_BOTTOM_Z = 250.0

SPINE_TUBE_OD = 30.0        # seat spine tubes to the tail
SPINE_Y = 40.0
SPINE_PATH = (              # (x, z), floor pan rear up to seat rails
    (-60.0, 270.0),
    (-150.0, 400.0),
    (-280.0, 500.0),
    (-480.0, 565.0),
    (-700.0, 555.0),
    (-750.0, 545.0),
)
CROSS_TUBES = (             # lateral braces between the spine tubes
    (-120.0, 345.0),
    (-720.0, 550.0),
)

ENGINE_PIVOT = (-300.0, 0.0, 430.0)      # swing-engine bolt, axis along Y
PIVOT_PLATE_Y = 85.0
PIVOT_PLATE_Z = 445.0                    # plate center z (spans 380..510)
PIVOT_PLATE_SIZE = (100.0, 12.0, 130.0)  # x, y, z
PIVOT_BORE_D = 20.0
WHEEL_ARCH_R_OUT = 218.0                 # engine-side wheel clearance notch
WHEEL_ARCH_R_IN = 126.0
WHEEL_ARCH_HALF_Y = 52.0

# ---------------------------------------------------------------------------
# Engine (unit powertrain doubles as the swingarm; rear wheel on its hub)
# ---------------------------------------------------------------------------

CASE_CENTER = (-380.0, 0.0, 370.0)
CASE_SIZE = (170.0, 120.0, 190.0)        # x, y, z
CASE_CORNER = 24.0

CYL_BASE = (-450.0, 0.0, 355.0)          # barrel base circle center
CYL_TILT = 12.0                          # degrees up from horizontal, forward
CYL_DIR = (cos(radians(CYL_TILT)), 0.0, sin(radians(CYL_TILT)))
CYL_BARREL_LEN = 135.0                   # base to head deck
CYL_BARREL_OD = 96.0
FIN_OD = 116.0
FIN_COUNT = 5
FIN_TH = 5.0
FIN_GAP = 7.0
HEAD_DEPTH = 42.0                        # head deck forward
HEAD_OD = 116.0

CVT_COVER_CENTER = (-390.0, 0.0, 310.0)  # rider-left pulley drum (low, ahead
CVT_COVER_OD = 156.0                     # of the shock; clearances sampled)
CVT_COVER_Y0 = 62.0                       # inner face
CVT_COVER_Y1 = 92.0                       # outer face
CVT_PLATE_OD = 164.0                      # inner cover plate
CVT_PLATE_T = 10.0

CRANK_COVER_CENTER = (-390.0, 0.0, 318.0)  # rider-right flywheel cover, low
CRANK_COVER_OD = 116.0                     # below the pivot plates
CRANK_COVER_Y0 = -62.0
CRANK_COVER_Y1 = -90.0

# Rear wheel carrier: left-side swingarm plate + hub flange meeting the wheel
HUB_ARM_X0 = -595.0
HUB_ARM_X1 = -465.0
HUB_ARM_Y0 = 54.0
HUB_ARM_Y1 = 80.0
HUB_ARM_Z0 = 190.0
HUB_ARM_Z1 = 270.0
HUB_FLANGE_OD = 88.0
HUB_FLANGE_Y0 = 33.0                     # meets the wheel hub face
HUB_FLANGE_Y1 = 56.0
HUB_OD = 90.0
HUB_LEN_Y = 70.0

# Shock lower boss on the case rear, rider left, outside the CVT drum
SHOCK_BOSS_CENTER = (-470.0, 100.0, 355.0)
SHOCK_BOSS_SIZE = (50.0, 20.0, 60.0)

EXHAUST_FLANGE = (-255.0, -38.0, 396.0)   # cylinder-head exit
PIPE_OD = 33.0
PIPE_PATH = (
    (-262.0, -48.0, 390.0),
    (-282.0, -70.0, 318.0),
    (-320.0, -98.0, 268.0),
    (-400.0, -114.0, 258.0),
    (-470.0, -118.0, 264.0),
)
MUFFLER_R = 40.0
MUFFLER_X0 = -740.0
MUFFLER_X1 = -470.0
MUFFLER_Y = -118.0
MUFFLER_Z = 262.0

# ---------------------------------------------------------------------------
# Rear suspension
# ---------------------------------------------------------------------------

SHOCK_UPPER = (-320.0, 95.0, 520.0)       # frame lug (rider left)
SHOCK_LOWER = (-480.0, 100.0, 360.0)      # engine boss behind the CVT drum
SHOCK_LUG_SIZE = (56.0, 72.0, 16.0)       # frame-side lug, y span 44..116
SHOCK_EYE_D = 11.0
SHOCK_EYE_OD = 30.0
SHOCK_EYE_W = 22.0
SHOCK_BODY_OD = 52.0
SHOCK_SPRING_MEAN_D = 88.0
SHOCK_SPRING_WIRE_D = 14.0
SHOCK_SPRING_TURNS = 3.5

# ---------------------------------------------------------------------------
# Bodywork
# ---------------------------------------------------------------------------

# Leg shield: lofted apron, sections (x, z, half-width) top to bottom.
LEG_SHIELD_SECTIONS = (
    (312.0, 690.0, 140.0),
    (348.0, 560.0, 185.0),
    (330.0, 440.0, 185.0),
    (270.0, 340.0, 175.0),
    (235.0, 295.0, 160.0),
)
LEG_SHIELD_TH = 22.0
LEG_SHIELD_CORNER = 10.0

# Inner front cover: head tube shroud above the apron.
FRONT_COVER_SECTIONS = (
    (312.0, 700.0, 145.0),
    (322.0, 745.0, 130.0),
    (330.0, 772.0, 108.0),
)
FRONT_COVER_TH = 20.0

# Under-seat rear body: lofted sections (x, half-width, z_bottom, z_top).
REAR_BODY_SECTIONS = (
    (-140.0, 150.0, 470.0, 680.0),
    (-330.0, 185.0, 470.0, 700.0),
    (-560.0, 185.0, 470.0, 690.0),
    (-760.0, 125.0, 495.0, 665.0),
)
REAR_BODY_CORNER = 40.0

# Seat: lofted saddle sections (x, half-width, z_bottom, z_top).
SEAT_SECTIONS = (
    (-350.0, 150.0, 695.0, 740.0),
    (-480.0, 178.0, 700.0, 752.0),
    (-640.0, 172.0, 698.0, 748.0),
    (-755.0, 128.0, 692.0, 738.0),
)
SEAT_CORNER = 26.0

# Fenders: annular sectors around their wheel axles (radius band, angle span).
FRONT_FENDER_R0 = 222.0
FRONT_FENDER_R1 = 234.0
FRONT_FENDER_HALF_WIDTH = 46.0   # clears the fork sliders (inner edge y 48.5)
FRONT_FENDER_ANGLES = (30.0, 150.0)      # degrees in the XZ plane from +X

REAR_FENDER_R0 = 237.0
REAR_FENDER_R1 = 251.0
REAR_FENDER_HALF_WIDTH = 70.0
REAR_FENDER_ANGLES = (66.0, 130.0)   # clears the CVT drum and shock spring

# ---------------------------------------------------------------------------
# Trim: lights, mirrors, stand
# ---------------------------------------------------------------------------

HEADLIGHT_CENTER = (365.0, 0.0, 640.0)   # apron-mounted, faces +X
HEADLIGHT_OD = 140.0
HEADLIGHT_DEPTH = 55.0

TAILLIGHT_CENTER = (-775.0, 0.0, 580.0)  # on the tail, faces -X
TAILLIGHT_OD = 84.0
TAILLIGHT_DEPTH = 26.0

SIGNAL_LENS_OD = 54.0
SIGNAL_STALK_LEN = 35.0
FRONT_SIGNAL_POS = (270.0, 198.0, 600.0)   # per side, y from |y|
REAR_SIGNAL_POS = (-740.0, 193.0, 545.0)

MIRROR_STALK_OD = 10.0
MIRROR_HEAD_RX = 40.0
MIRROR_HEAD_RZ = 28.0
MIRROR_HEAD_T = 18.0

STAND_TUBE_OD = 19.0
STAND_PIVOT = (-140.0, 142.0, 240.0)      # per side, under the floor pan rear
STAND_ELBOW = (-260.0, 142.0, 236.0)
STAND_FOOT = (-390.0, 142.0, 252.0)       # folded-up pose, clears the exhaust
STAND_CROSS = (-300.0, 0.0, 246.0)        # ahead of the rear tire front edge
