"""Identical 3.175 mm 5052 base/carrier plates with explicit mount patterns.

69 x 57.2 mm body; continuous mirrored side flanges finish flush at the rear,
expanding the envelope to 69 x 83 mm. Pi/HAT pitch is 58 x 49. Independent
crosswise mounts share the plate center X36.5: Pi Zero 23 x 58,
adapter A 28 x 37. Extended shoulders begin at X21, with R3 corners.
Electronics mounting holes are M2.5 clearance.
The spare patterns are alternative installations, not simultaneous boards.
Rearward mounting ears avoid adding material to the moving shoulder area.
No additional electronics or surface-mount hardware is installed here.
"""
import build123d as b
from lib.booleans import as_single_shape as one
from lib.corner_rules import SMALL, LARGE
from lib.materials import ALUMINUM_5052_COLOR
from lib.reach600_geometry import MOUNT_XY as ORIGINAL_MOUNT_XY
from lib.common_base_plate import CLAMP_ATTACH_XY

THICKNESS = 3.175  # SendCutSend ALU-125, matching the three yokes.
LENGTH = 69.0
WIDTH = 57.2
FRONT_X = 2.0
OUTER_RADIUS = LARGE
SERVO_SHIFT_X = 13.5
MOUNT_XY = tuple((x+SERVO_SHIFT_X,y) for x,y in ORIGINAL_MOUNT_XY)
BOARD_XY = tuple((x, y) for x in (8.0, 66.0) for y in (-24.5, 24.5))
SUPPORT_XY = BOARD_XY
CENTER_X = FRONT_X + LENGTH/2
SERVO_NOTCH_BACK_X = 31.4  # Native servo-to-wall gap 1.03 mm; old X30.8 was .47.
FLANGE_FRONT_X = 21.0
REAR_X = FRONT_X + LENGTH
# Keep interface datums fixed when trimming the outline.
REAR_CENTER_X = 51.7
ADAPTER_CENTER_X = CENTER_X
PI_ZERO_CENTER_X = CENTER_X
ADAPTER_XY = tuple((ADAPTER_CENTER_X+x, y) for x in (-14.0, 14.0) for y in (-18.5, 18.5))
PI_ZERO_XY = tuple((PI_ZERO_CENTER_X+x, y) for x in (-11.5, 11.5) for y in (-29.0, 29.0))
SURFACE_XY = tuple((x, y) for x in (30.0,62.0) for y in (-36.0,36.0))
SURFACE_ROUND_XY = tuple((46.0,y) for y in (-36.0,36.0))
# M3 clamp mounts share one datum table with the clamp and its screws.
OUTER_HALF_WIDTH = 41.5


def common_base_plate(*,board_xy=BOARD_XY,flange_front_x=FLANGE_FRONT_X,clamp_attach_xy=CLAMP_ATTACH_XY,servo_offset_x=0.0,continuous_servo_connection=False):
    p = b.Solid.make_box(LENGTH, WIDTH, THICKNESS,
                         b.Plane(origin=(FRONT_X, -WIDTH/2, 0)))
    # Tighten the Pi rims by 1 mm and mounting flange rims by 0.5 mm.
    # The front edge is retained: the servo holes already have a small margin.
    tabs = []
    for y0 in (26.0,-OUTER_HALF_WIDTH):
        tabs.append(b.Solid.make_box(REAR_X-flange_front_x,OUTER_HALF_WIDTH-26,THICKNESS,
                                    b.Plane(origin=(flange_front_x,y0,0))))
    p = one(p.fuse(*tabs)).clean()
    p = p.fillet(OUTER_RADIUS,[e for e in p.edges()
                              if abs(e.length-THICKNESS)<1e-6]).clean()
    def bore(radius, x, y):
        return b.Solid.make_cylinder(radius, THICKNESS, b.Plane(origin=(x, y, 0)))
    def slot(length,width,x,y):
        return b.extrude(b.Pos(x,y)*b.SlotOverall(length,width),amount=THICKNESS)
    holes = [bore(1.35, x, y) for x, y in (*board_xy,*ADAPTER_XY,*PI_ZERO_XY)]
    holes += [bore(1.1, x+servo_offset_x, y) for x, y in MOUNT_XY]
    holes += [slot(12,4.5,x,y) for x,y in SURFACE_XY]
    holes += [bore(2.25,x,y) for x,y in SURFACE_ROUND_XY]
    holes += [bore(1.65,x,y) for x,y in clamp_attach_xy]
    # Extend the clearance root before rounding so the complete old
    # rectangular servo keep-out remains empty. Hole/seat datums stay fixed.
    x0=-12+SERVO_SHIFT_X  # Keep clearance open to the unchanged front edge.
    xr=SERVO_NOTCH_BACK_X+SMALL+servo_offset_x
    # A coupon's rounded end is only a free corner on the coupon. On the base
    # plate that edge continues into parent stock: construct one uninterrupted
    # opening using the approved A connection's functional clearance datums.
    from lib.servo_case_flange import CASE_UPPER_INNER_EDGE_MM, HORN_CLEARANCE_RADIUS_MM
    half_gap=-CASE_UPPER_INNER_EDGE_MM if continuous_servo_connection else 7.35
    notch=b.Face(b.Wire.make_polygon([(x0,-.5-half_gap,0),(xr,-.5-half_gap,0),
                                    (xr,-.5+half_gap,0),(x0,-.5+half_gap,0)],close=True))
    notch=notch.fillet_2d(SMALL,[v for v in notch.vertices() if v.center().X>xr-1e-6])
    horn_radius=HORN_CLEARANCE_RADIUS_MM if continuous_servo_connection else 10.6
    holes += [bore(horn_radius, -17.5+SERVO_SHIFT_X+servo_offset_x, -.5),b.Solid.extrude(notch,(0,0,THICKNESS))]
    p = one(p.cut(*holes)).clean()
    if continuous_servo_connection:
        # Round the two actual exposed corners where the open horn relief
        # reaches the front perimeter, rather than the former coupon joins.
        es=[e for e in p.edges() if e.geom_type==b.GeomType.LINE
            and abs(e.length-THICKNESS)<1e-6 and abs(e.center().X-FRONT_X)<1e-6
            and abs(e.center().Y+.5)<horn_radius+.01]
        assert len(es)==2,('Base servo relief front corners',len(es))
        p=p.fillet(SMALL,es).clean()
        from lib.horn_relief_finish import finish_horn_junctions
        p=finish_horn_junctions(p)
    assert p.is_valid and len(p.solids()) == 1
    p.label = 'common_base_plate_5052_3p175mm'
    p.color = ALUMINUM_5052_COLOR
    return p
