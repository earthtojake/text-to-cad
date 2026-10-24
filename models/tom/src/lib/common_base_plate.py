"""Identical 2 mm 5052 base/carrier plates with explicit mount patterns.

69 x 57.2 mm body; continuous mirrored side flanges finish flush at the rear,
expanding the envelope to 69 x 83 mm. Pi/HAT pitch is 58 x 49. Independent
crosswise mounts share the plate center X36.5: Pi Zero 23 x 58,
adapter A 28 x 37. Extended shoulders begin at X21, with R3 corners.
Electronics mounting holes are M2.5 clearance.
The spare patterns are alternative installations, not simultaneous boards.
Rearward mounting ears avoid adding material to the moving shoulder area.
No additional electronics or surface-mount hardware is installed here.
"""
from lib.corner_rules import LARGE
import build123d as b
from lib.booleans import as_single_shape as one
from lib.materials import ALUMINUM_5052_COLOR
from lib.reach600_geometry import MOUNT_XY as ORIGINAL_MOUNT_XY

THICKNESS = 2.0  # User-selected nominal 2 mm aluminum; confirm supplier stock at ordering.
LENGTH = 69.0
WIDTH = 57.2
FRONT_X = 2.0
OUTER_RADIUS = LARGE
SERVO_FORWARD = 12.0  # Sideways folded case retains approximately 1 mm plate clearance.
SERVO_SHIFT_X = 13.5-SERVO_FORWARD
MOUNT_XY = tuple((x+SERVO_SHIFT_X,y) for x,y in ORIGINAL_MOUNT_XY)
BOARD_XY = tuple((x, y) for x in (8.0, 66.0) for y in (-24.5, 24.5))
SUPPORT_XY = BOARD_XY
CENTER_X = FRONT_X + LENGTH/2
SERVO_NOTCH_BACK_X = 31.4-SERVO_FORWARD
SERVO_FINGER_HALF_WIDTH = 13.5  # Narrow tips clear the rotating yoke/collar; gauge stays 2 mm.
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
# Shared clamp interface: symmetric inset from the four Pi reliefs and side edges.
# Keep the independent small-driver pattern above unchanged in both plates.
CLAMP_ATTACH_XY = tuple((x,y) for x in (17.2,56.8) for y in (-23.9,23.9))
OUTER_HALF_WIDTH = 41.5


def common_base_plate(*,board_xy=BOARD_XY,flange_front_x=FLANGE_FRONT_X,clamp_attach_xy=CLAMP_ATTACH_XY,
                      servo_forward=SERVO_FORWARD,finger_half_width=SERVO_FINGER_HALF_WIDTH):
    servo_shift_x = 13.5-servo_forward
    mount_xy = tuple((x+servo_shift_x,y) for x,y in ORIGINAL_MOUNT_XY)
    p = b.Solid.make_box(LENGTH, WIDTH, THICKNESS,
                         b.Plane(origin=(FRONT_X, -WIDTH/2, 0)))
    # Tighten the Pi rims by 1 mm and mounting flange rims by 0.5 mm.
    # The front edge is retained: the servo holes already have a small margin.
    tabs = []
    # Extend only the narrow servo lands. The wider plate stays behind the
    # shoulder horn/link plane when the yaw joint is turned sideways.
    # Round the outer perimeter before cutting the central servo relief.
    # A continuous nose avoids overlapping fillets on the narrow fingers.
    tabs.append(b.Solid.make_box(servo_forward+2,2*finger_half_width,THICKNESS,
        b.Plane(origin=(FRONT_X-servo_forward-2,-finger_half_width,0))))
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
    holes += [bore(1.1, x, y) for x, y in mount_xy]
    holes += [slot(12,4.5,x,y) for x,y in SURFACE_XY]
    holes += [bore(2.25,x,y) for x,y in SURFACE_ROUND_XY]
    holes += [bore(1.65,x,y) for x,y in clamp_attach_xy]
    holes += [bore(10.6, -17.5+servo_shift_x, -.5),
              b.Solid.make_box(31.4-servo_forward-(-12+servo_shift_x), 14.7, THICKNESS,
                  b.Plane(origin=(-12+servo_shift_x, -7.85, 0)))]
    p = one(p.cut(*holes)).clean()
    assert p.is_valid and len(p.solids()) == 1
    p.label = 'common_base_plate_5052_2mm'
    p.color = ALUMINUM_5052_COLOR
    return p
