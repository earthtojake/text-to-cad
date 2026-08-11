"""Master dimensional spec for the hand-wound column-wheel chronograph.

Every builder module imports from here; no builder restates a shared
dimension. Scale verified against public references (2026-08-06):

- Case: 42.0 mm diameter, ~13.5 mm thick, 20 mm lug width — modern
  moonwatch-archetype professional case.
- Movement: caliber 321 lineage (Lemania 2310 base) — 27.0 mm diameter,
  6.74 mm tall, 18,000 vph (2.5 Hz), column wheel with lateral clutch
  (watchbase.com/omega/caliber/321, watch-wiki.net Lemania 2310).
- Column wheel: 7 columns (macro photography of the cal. 321 movement).

Coordinate conventions:

- WATCH assembly frame: +Z through the crystal ("dial up"), crown at +X
  (3 o'clock), 12 o'clock at +Y. z = 0 at the case-middle / caseback
  joint plane.
- MOVEMENT local frame: bridge side up (+Z toward the caseback viewer),
  z = 0 at the main plate's bridge-side surface. The dial side lies at
  negative z. Cased transform (moonwatch.step.py): rotate 180 about X,
  then lift — local (x, y, z) -> watch (x, -y, MOVT_Z_OFFSET - z). The
  stem/crown at local +X stays at watch +X (3 o'clock); local +Y maps to
  watch -Y, so a dial-side register that must land at watch 6 o'clock
  sits at local +Y.
"""

# ---------------------------------------------------------------------------
# Shared colors (linear RGB + alpha, matched to the presentation theme's
# neutral grade — the theme does not override source colors).
# ---------------------------------------------------------------------------

STEEL = (0.620, 0.630, 0.660, 1.0)          # polished/brushed stainless
STEEL_BRIGHT = (0.800, 0.810, 0.840, 1.0)   # mirror bevels, hands
STEEL_DARK = (0.520, 0.530, 0.555, 1.0)     # recessed steel, springs
STEEL_LEVER = (0.700, 0.705, 0.720, 1.0)    # straight-grained chrono levers
COPPER_GOLD = (0.555, 0.305, 0.195, 1.0)    # salmon copper-gold bridges/plate
COPPER_GOLD_DEEP = (0.430, 0.230, 0.140, 1.0)  # striping groove shadow
GILT = (0.735, 0.650, 0.380, 1.0)           # pale champagne train wheels
BLUED = (0.022, 0.038, 0.120, 1.0)          # flame-blued screws (near-black, blue flash)
RUBY = (0.560, 0.070, 0.210, 1.0)           # jewels (deep ruby)
RUBY_BRIGHT = (0.540, 0.070, 0.230, 1.0)    # cap jewels
DIAL_BLACK = (0.038, 0.038, 0.044, 1.0)     # step dial lacquer
DIAL_PRINT = (0.930, 0.930, 0.915, 1.0)     # white print / indices
LUME = (0.820, 0.850, 0.660, 1.0)           # aged-neutral luminous plots
BEZEL_BLACK = (0.045, 0.045, 0.050, 1.0)    # anodized tachymeter insert
BEZEL_FILL = (0.920, 0.920, 0.910, 1.0)     # filled tachymeter engraving
CRYSTAL = (0.760, 0.800, 0.830, 0.11)       # domed crystal (transparent)
SAPPHIRE = (0.780, 0.810, 0.850, 0.05)      # display back glass (AR-coated read)
GASKET = (0.080, 0.080, 0.085, 1.0)         # black nitrile
BRACELET_OUTER = (0.580, 0.595, 0.630, 1.0) # brushed outer links (darker)
BRACELET_CENTER = (0.850, 0.855, 0.870, 1.0)  # polished center links
BRASS_MOVEMENT = (0.700, 0.560, 0.330, 1.0) # unplated brass small parts

# ---------------------------------------------------------------------------
# Case
# ---------------------------------------------------------------------------

CASE_DIAMETER = 42.0            # bezel outer diameter
CASE_MIDDLE_DIAMETER = 41.0     # case band below the bezel
CASE_THICKNESS = 13.5           # caseback dome to crystal apex
LUG_WIDTH = 20.0                # spring-bar span between lug tips
LUG_TO_LUG = 48.0
LUG_THICKNESS = 4.4             # vertical thickness at the lug root

# z = 0 at case-middle/caseback joint plane (watch frame)
CASEBACK_DEPTH = 2.6            # caseback extends z in [-CASEBACK_DEPTH, 0]
CASE_MIDDLE_HEIGHT = 7.0        # case middle occupies z in [0, 7.0]
BEZEL_HEIGHT = 2.2              # bezel sits on the case middle
CRYSTAL_DOME_RISE = 1.7         # crystal apex above bezel top
# 2.6 + 7.0 + 2.2 + 1.7 = 13.5 = CASE_THICKNESS

BEZEL_INNER_DIAMETER = 37.6     # opening over the dial
CRYSTAL_DIAMETER = 38.4
CASEBACK_SAPPHIRE_DIAMETER = 30.0
CASEBACK_THREAD_DIAMETER = 36.0

CROWN_DIAMETER = 5.8
CROWN_THICKNESS = 3.4
CROWN_Z = 3.6                   # crown axis height above z=0 (case frame)
PUSHER_DIAMETER = 4.6
PUSHER_ANGLES = (35.0, -35.0)   # degrees from +X (2 and 4 o'clock)
PUSHER_Z = 3.6

# ---------------------------------------------------------------------------
# Dial and hands
# ---------------------------------------------------------------------------

DIAL_DIAMETER = 37.2
DIAL_THICKNESS = 0.65           # thickened upward: underside stays at 7.7
DIAL_Z = 8.35                   # dial top surface z in the watch frame
#   (DIAL_Z - DIAL_THICKNESS = 7.7 — the movement seat plane is unchanged;
#    the extra 0.15 keeps a solid floor under the deep register recesses)
SUBDIAL_RADIUS = 10.2           # center offset of the three registers
SUBDIAL_DIAMETER = 8.2
SUBDIAL_RECESS = 0.5            # visible counter depth below the dial top
# registers: 3 o'clock (+X) = 30-min recorder, 6 (-Y) = 12-hour recorder,
# 9 (-X) = small seconds; chronograph seconds from the center post.

HAND_HOUR_LENGTH = 12.0
HAND_MINUTE_LENGTH = 16.6
HAND_CHRONO_LENGTH = 18.0
HAND_SUBDIAL_LENGTH = 3.6

# ---------------------------------------------------------------------------
# Movement global
# ---------------------------------------------------------------------------

MOVEMENT_DIAMETER = 27.0
MOVEMENT_HEIGHT = 6.74
BEAT_RATE_VPH = 18000           # 2.5 Hz

# Movement local z-stack (bridge side up, z=0 = plate bridge-side surface)
PLATE_THICKNESS = 1.5           # main plate z in [-1.5, 0]
DIAL_SIDE_DEPTH = 1.14          # keyless/motion works below the plate
TRAIN_AXIS_Z = 0.9              # mid-height of the going-train wheels
BRIDGE_SEAT_Z = 1.8             # underside of barrel/train bridges
BRIDGE_THICKNESS = 1.05
CHRONO_LAYER_Z = 2.85           # chronograph works ride above the bridges
CHRONO_LAYER_TOP = 4.1
BALANCE_COCK_TOP = 3.4
# dial side 1.14 + plate 1.5 + train/bridges 2.85 + chrono 1.25 = 6.74

# Movement layout (movement local XY, bridge-side view, +X = 3 o'clock):
BARREL_POS = (-1.6, 8.0)
BARREL_DIAMETER = 12.0
RATCHET_WHEEL_DIAMETER = 10.0
CROWN_WHEEL_POS = (6.9, 8.3)
CROWN_WHEEL_DIAMETER = 6.4
CENTER_WHEEL_POS = (0.0, 0.0)
THIRD_WHEEL_POS = (-5.0, -2.6)
FOURTH_WHEEL_POS = (-10.2, 0.0)     # small seconds at 9
ESCAPE_WHEEL_POS = (-7.6, -5.2)
PALLET_FORK_POS = (-4.9, -7.2)
BALANCE_POS = (-0.4, -7.6)          # balance lower-center-left
BALANCE_DIAMETER = 9.6
COLUMN_WHEEL_POS = (8.3, 3.6)
COLUMN_WHEEL_DIAMETER = 4.6
COLUMN_COUNT = 7
MINUTE_RECORDER_POS = (10.2, 0.0)   # 30-min register at 3
HOUR_RECORDER_POS = (0.0, 10.2)    # 12-hour register: local +Y = watch 6
#   (the movement flips about X when cased: local (x,y,z) -> watch (x,-y,-z),
#   so dial-side features that must land at watch 6 o'clock sit at local +Y)
COUPLING_WHEEL_POS = (5.6, -4.6)    # swinging intermediate wheel

STEM_AXIS_Z_LOCAL = -0.55           # stem axis below plate top (dial side)

# Cased movement placement (watch frame): watch_z = MOVT_Z_OFFSET - local_z.
# Derivation: dial underside (DIAL_Z - DIAL_THICKNESS = 7.7) seats on the
# movement's dial-side extreme (local z = -(PLATE_THICKNESS + DIAL_SIDE_DEPTH)
# = -2.64), so MOVT_Z_OFFSET = 7.7 - 2.64 = 5.06.
MOVT_Z_OFFSET = 5.06

# ---------------------------------------------------------------------------
# Going train tooth counts (ratios stated + verified in the assembly)
# ---------------------------------------------------------------------------

BARREL_TEETH = 80
CENTER_PINION_LEAVES = 12       # barrel -> center: 80/12 (~6.7 h/barrel rev)
CENTER_WHEEL_TEETH = 64
THIRD_PINION_LEAVES = 8         # center -> third: 64/8 = 8
THIRD_WHEEL_TEETH = 60
FOURTH_PINION_LEAVES = 8        # third -> fourth: 60/8 = 7.5 (8 x 7.5 = 60)
FOURTH_WHEEL_TEETH = 70
ESCAPE_PINION_LEAVES = 7        # fourth -> escape: 70/7 = 10
ESCAPE_WHEEL_TEETH = 15         # 15 teeth * 2 beats = 30 beats/rev = 6 s/rev
# 18,000 vph = 5 beats/s -> escape 10 rpm, fourth 1 rpm, center 1 rph.

CANNON_PINION_LEAVES = 12
MINUTE_WHEEL_TEETH = 36         # cannon -> minute wheel: 3.0
MINUTE_WHEEL_PINION = 10
HOUR_WHEEL_TEETH = 40           # minute pinion -> hour wheel: 4.0 (12:1 total)

MINUTE_RECORDER_TEETH = 30      # 30-minute register
HOUR_RECORDER_TEETH = 24        # advanced twice per hour by finger -> 12 h

# ---------------------------------------------------------------------------
# Finishing vocabulary
# ---------------------------------------------------------------------------

ANGLAGE_WIDTH = 0.22            # 45-degree polished bevel on bridges/levers
ANGLAGE_WIDTH_SMALL = 0.14      # small levers/springs
JEWEL_DIAMETER = 1.5
JEWEL_COUNTERSINK_DIAMETER = 2.7
JEWEL_COUNTERSINK_DEPTH = 0.22
SCREW_HEAD_DIAMETER = 1.3
SCREW_SLOT_WIDTH = 0.24
SCREW_SLOT_DEPTH = 0.18
GENEVA_STRIPE_PITCH = 1.9       # circular striping pitch on bridges
PERLAGE_DIAMETER = 1.6          # main plate perlage stamp
SNAIL_PITCH = 0.35              # ratchet wheel / subdial snailing pitch

# ---------------------------------------------------------------------------
# Bracelet
# ---------------------------------------------------------------------------

BRACELET_WIDTH_AT_LUG = 20.0
BRACELET_WIDTH_AT_CLASP = 16.0
LINK_PITCH = 7.6                # one row of links along the strap
LINK_THICKNESS = 3.0
LINKS_PER_SIDE_12 = 6           # rows on the 12 o'clock strap
LINKS_PER_SIDE_6 = 5            # rows on the 6 o'clock strap (clasp side)
CLASP_LENGTH = 38.0
CLASP_WIDTH = 17.0

# Shared case/bracelet interface (watch frame)
SPRING_BAR_Y = 21.8             # spring-bar axis distance from case center
SPRING_BAR_Z = 3.2              # spring-bar axis height
SPRING_BAR_DIAMETER = 1.5
END_LINK_SEAT_Y = 20.6          # end link nose clears the 20.5 case band
