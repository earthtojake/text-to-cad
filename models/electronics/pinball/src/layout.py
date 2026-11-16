"""SHORT CIRCUIT's playfield layout: every place and size the board, the art and the mechanics share.

Frame (the "playfield frame"): millimetres, x across the board from its left edge, y up the playfield from
the board's front edge (the player's end), z up from the board's top face (the playfield surface). The
board's bottom face is z = -BOARD_T. KiCad's frame is x, (BOARD_L - y) with y down: `to_kicad`.

Plain numbers only (no kernel objects at module level): the board scripts, the art and the CAD import it.
"""
from __future__ import annotations

import math

# --------------------------------------------------------------------------------------------- the ball
BALL_D = 8.0                       # chrome steel (AISI 52100), G25
BALL_R = BALL_D / 2
TILT_DEG = 6.5                     # playfield pitch, degrees (real machines: 6 to 7)

# --------------------------------------------------------------------------------------------- the board
BOARD_W, BOARD_L, BOARD_T = 112.0, 236.0, 1.6
BOARD_CORNER = 4.0
RAIL_W = 6.0                       # the side rails sit on the board's edge strips
RAIL_H = 11.2                      # rail top above the playfield: the glass rests on it
GLASS_Z, GLASS_T = 11.2, 2.0       # the glass's underside, its thickness (2 mm cast acrylic)
LOCKDOWN_D = 9.0                   # the lockdown bar's depth at the front
BACKBOX_Y = 202.0                  # the backbox's front face (the playfield ends here)
BACKBOX_D, BACKBOX_H = 34.0, 124.0  # the head's depth (backglass face to its back), the backglass's top above the board
BACKGLASS_W, BACKGLASS_H = 112.0, 120.0   # the backglass: a bare board on four brass standoffs
STANDOFF_L = 10.0                  # M3 brass standoffs between the backglass and the tray

# lanes (ball 8 mm: a lane is 11 mm, a guide 2 mm)
LANE = 11.0
GUIDE = 2.0
WALL = 1.6                         # the shooter lane's wall

FIELD_X0 = RAIL_W                  # the main field, left to right
OUTLANE_L = (FIELD_X0, FIELD_X0 + LANE)
GUIDE_L = (OUTLANE_L[1], OUTLANE_L[1] + GUIDE)
INLANE_L = (GUIDE_L[1], GUIDE_L[1] + LANE)

# --------------------------------------------------------------------------------------------- flippers
FLIPPER_L = 20.0                   # pivot to tip centre
FLIPPER_RB, FLIPPER_RT = 4.2, 1.8  # base and tip radius (bat outline, the rubber outside it)
RUBBER_CS = 1.6                    # the flipper rubber's cross-section (an O-ring in a groove)
FLIPPER_H = 6.6                    # bat height: z 0.4 .. 7.0 (the ball's equator is at z = 4)
FLIPPER_Z0 = 0.4
FLIPPER_REST, FLIPPER_UP = -30.0, 25.0   # left bat's angle from +x, at rest and energised (stroke 55)
FLIPPER_GAP = 11.0                 # between the tips' rubber at rest (1.4 balls)
FLIPPER_Y = 42.0
_tip_dx = FLIPPER_L * math.cos(math.radians(-FLIPPER_REST))
PIVOT_L_X = (INLANE_L[0] + INLANE_L[1]) / 2 - 1.0
CENTER_X = PIVOT_L_X + _tip_dx + FLIPPER_RT + RUBBER_CS + FLIPPER_GAP / 2
PIVOT_R_X = 2 * CENTER_X - PIVOT_L_X
PIVOTS = {"left": (PIVOT_L_X, FLIPPER_Y), "right": (PIVOT_R_X, FLIPPER_Y)}


def mirror_x(x: float) -> float:
    """Across the main field's centre line (the flippers' axis of symmetry)."""
    return 2 * CENTER_X - x


INLANE_R = (mirror_x(INLANE_L[1]), mirror_x(INLANE_L[0]))
GUIDE_R = (mirror_x(GUIDE_L[1]), mirror_x(GUIDE_L[0]))
OUTLANE_R = (mirror_x(OUTLANE_L[1]), mirror_x(OUTLANE_L[0]))
FIELD_X1 = OUTLANE_R[1]
SHOOTER_WALL = (FIELD_X1, FIELD_X1 + WALL)
SHOOTER_LANE = (SHOOTER_WALL[1], BOARD_W - RAIL_W)
SHOOTER_X = (SHOOTER_LANE[0] + SHOOTER_LANE[1]) / 2
PLUNGER_REST_Y = LOCKDOWN_D + 2.0          # the plunger tip's face at rest
BALL_READY_Y = PLUNGER_REST_Y + BALL_R     # the ball's centre resting on it

# --------------------------------------------------------------------------------------------- lower field
APRON_Y = (LOCKDOWN_D, 28.0)               # the apron bridges the return channel under it
LANE_BOTTOM_Y = 58.0                       # inlane / outlane guides end here (a post at the end)
LANE_TOP_Y = 84.0                          # ... and start here (low enough that the ball reaches the left
                                           # outlane past the targets, and the inlanes past the slings' tops)
GUIDE_LOW_Y = 49.0                         # below it the guide steps outboard of the flipper's base
SLING_POSTS = ((INLANE_L[1] + 4.4, 91.0),  # left sling: top, bottom-outer, bottom-inner posts (clear of the
               (INLANE_L[1] + 4.4, 66.0),  # bat's energised sweep; the inlane 1 mm wider than the ball needs)
               (INLANE_L[1] + 10.0, 61.5))   # the bottom-inner posts 19.4 mm apart: the ball passes between
POST_R = 2.2                               # brass posts: 4 mm hex standoffs (circumradius 2.3)
POST_RUBBER = 0.9                          # mini O-ring cross-section radius over a post
POST_HEX_R = 4.0 / 3 ** 0.5                # the 4 mm hex's circumradius: rubbers ride on its corners

# --------------------------------------------------------------------------------------------- upper field
BUMPER_R = 6.5                             # cap radius; the O-ring sits proud of it
BUMPERS = {"C1": (CENTER_X - 13.0, 131.0), "C2": (CENTER_X + 13.0, 131.0), "C3": (CENTER_X, 108.5)}
BUMPER_POST_R, BUMPER_ORING_CS = 5.6, 1.6        # the O-ring round the post: the ball touches r = 7.2
TOP_LANES = {"G": CENTER_X - 13.0, "N": CENTER_X, "D": CENTER_X + 13.0}   # lane centres
TOP_LANE_Y = (150.0, 170.0)
TARGETS = {"V": 120.0, "C": 109.0, "C2": 98.0}   # left bank, target centres along y, faces to +x
TARGET_W, TARGET_H, TARGET_T = 9.0, 8.4, 1.6   # an FR-4 card, its face ENIG
TARGET_FACE_X = FIELD_X0 + 4.5            # the targets' faces
RETURN_GUIDE = ((FIELD_X0 + 2.0, 25.5), (SHOOTER_LANE[0] - 0.2, 12.5))   # under the apron, down to the lane

# The top arch: from the shooter lane's top round to the left rail, the ball's way into the field.
ARCH_Y0 = 168.0                            # where the arch leaves the straight rails
ARCH_R = 30.0                              # the arch's two corner radii (inner face)
ARCH_TOP = BACKBOX_Y - 4.0                 # its highest point (inner face)
ARCH_WALL = 2.0

# --------------------------------------------------------------------------------------------- inserts (lit)
INSERT_R = 2.0                             # FR-4 window radius (the LED's 3.4 x 2.8 mm opening fits under it)
BONUS_INSERTS = [(CENTER_X, 68.0 + 6.0 * i) for i in range(5)]       # x1 .. x5, up the centre
BONUS_R = 1.6
SHOOT_AGAIN = (CENTER_X, 36.5)
LANE_INSERTS = {k: (x, TOP_LANE_Y[0] - 4.0) for k, x in TOP_LANES.items()}
TARGET_INSERTS = {k: (TARGET_FACE_X + 11.5, y) for k, y in TARGETS.items()}
SKILL_INSERT = (SHOOTER_X, 150.0)
LANE_LAMPS = {k: ((a + b) / 2, 80.6) for k, (a, b) in (("OUT_L", OUTLANE_L), ("IN_L", INLANE_L), ("IN_R", INLANE_R),
                                                         ("OUT_R", OUTLANE_R))}
ORBIT_LAMP = (FIELD_X0 + 6.0, 136.0)
FIDUCIALS = ((14.5, 186.5), (97.5, 186.5), (88.0, 92.0))
# Every sensor is a switch on the schematic: its designator, printed beside it ("the ball is the switch").
SWITCHES = {"LANE_G": "S1", "LANE_N": "S2", "LANE_D": "S3", "OUT_L": "S4", "IN_L": "S5", "IN_R": "S6", "OUT_R": "S7",
            "BUMPER_C1": "S8", "BUMPER_C2": "S9", "BUMPER_C3": "S10", "TARGET_V": "S11", "TARGET_C": "S12",
            "TARGET_C2": "S13", "SLING_L": "S14", "SLING_R": "S15", "ORBIT": "S16", "SHOOTER": "S17", "DRAIN": "S18"}
SHOOTER_WALL_Y = (22.0, 158.0)            # the shooter wall: open below (the ball returns) and above

# --------------------------------------------------------------------------------------------- cabinet
# The board is the cabinet's top: four 3 mm smoked acrylic panels hang from it (the classic trapezoid in side
# view, the engine room seen through them), a black-anodised aluminium floor plate under them, brass corner
# plates at its corners, four legs under those.
PANEL_T = 3.0                              # smoked cast acrylic
FLOOR_T = 3.0                              # aluminium plate
ENGINE_DEPTH = 38.0                        # the board's underside, at its front edge, to the floor plate's top
LEG_H = 76.0                               # desk to the floor plate's underside (1.4 x the body's front, as a real cabinet)
LEG = 12.0                                 # straight square aluminium tube
LEG_INSET = 8.0                            # the legs' centres in from the cabinet's outer corners
Z_FRONT = LEG_H + FLOOR_T + ENGINE_DEPTH   # desk to the board's underside at its front edge (world)


def to_kicad(x: float, y: float, origin=(40.0, 30.0)) -> tuple[float, float]:
    """The playfield frame's (x, y) as KiCad board coordinates (y down), the board's back edge at origin's y."""
    return (origin[0] + x, origin[1] + (BOARD_L - y))


def flipper_tip(side: str, angle: float | None = None) -> tuple[float, float]:
    px, py = PIVOTS[side]
    a = FLIPPER_REST if angle is None else angle
    if side == "right":
        a = 180.0 - a
    return (px + FLIPPER_L * math.cos(math.radians(a)), py + FLIPPER_L * math.sin(math.radians(a)))
