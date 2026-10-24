"""Production Pi/HAT base and compact standalone-adapter alternative.

The PCBs are sandwiched in the structural post columns in this concept;
this is a load-path concern, not a qualified robot-arm support.
"""
import math
import build123d as bd
from lib import base_electronics_layout as old
from lib.booleans import as_single_shape
from lib.materials import ALUMINUM_5052_COLOR
from lib import sheet_rule_scs as scs
from base.legacy.base_clamp import BEND_INNER_RADIUS_MM as RI

T = old.T
CARRIER_T = scs.THICKNESS_MM
# Choose the throat independently of screw length: 80 mm clear gives about
# 75 mm tabletop capacity with a 5 mm protective pad. The existing M8x90
# still reaches a thin tabletop with its knob below the lower jaw.
DESK_OPENING_MM = 80.0
ADAPTER_STACK_CENTER_X = -27.0
ADAPTER_CLAMP_DEPTH_MM = 62.0
ADAPTER_SCREW_FRONT_MARGIN_MM = 15.0
CLAMP_M2_TAP_DIAMETER = 1.66
CLAMP_M8_TAP_DIAMETER = 6.96
LOWER_POST_HEIGHT = 10.0
CARRIER_WIDTH = 57.0
PI_CARRIER_END_EXTENSION_MM = 5.1
PI_CARRIER_SIDE_EXTENSION_MM = 5.1
# Clamp front/sides share the carrier outline. The bend stays beyond its rear
# edge so all four corner supports retain a flat mounting seat.
WIDTH = CARRIER_WIDTH
CLAMP_BEND_HALF_DIE = 25.4*0.630/2
CLAMP_BEND_K = 0.44
CLAMP_HALF_BEND_ALLOWANCE = math.pi/4*(RI+CLAMP_BEND_K*T)
SERVO_POST_HEIGHT = 10.0
UPPER_POST_HEIGHT = 20.0
SERVO_PATTERN_CENTER_X = sum(x for x,y in old.SERVO_MOUNT_XY)/4
# Center the measured case envelope (-10.1126..35.1126 from shaft) on the plate.
# Both electronics variants can support the carrier on their own hole pattern.
SERVO_FORWARD_OFFSET = -12.5+SERVO_PATTERN_CENTER_X
SERVO_XY = tuple((x-SERVO_PATTERN_CENTER_X+SERVO_FORWARD_OFFSET,y) for x,y in old.SERVO_MOUNT_XY)
PI_CENTER = sum(x for x,y in old.PI_MOUNT_XY)/4
ADAPTER_CENTER = sum(x for x,y in old.ADAPTER_MOUNT_XY)/4
PI_XY = tuple((x-PI_CENTER,y) for x,y in old.PI_MOUNT_XY)
ADAPTER_XY = tuple((x-ADAPTER_CENTER,y) for x,y in old.ADAPTER_MOUNT_XY)
HORN_CENTER_X = -SERVO_PATTERN_CENTER_X+SERVO_FORWARD_OFFSET

def carrier_bounds(configuration):
    """Free edge, wall edge, width; adapter corners track the PCB posts."""
    if configuration == 'pi_hat':
        return (-33.0-PI_CARRIER_END_EXTENSION_MM,
                33.0+PI_CARRIER_END_EXTENSION_MM,
                CARRIER_WIDTH+2*PI_CARRIER_SIDE_EXTENSION_MM)
    if configuration == 'adapter': return (ADAPTER_STACK_CENTER_X-18.0, ADAPTER_STACK_CENTER_X+18.0, 45.0)
    raise ValueError(configuration)

def servo_shift_x(configuration):
    # A centered rectangular pattern avoids an end-for-end plate ambiguity.
    front, rear, _ = carrier_bounds(configuration)
    return (front+rear)/2 - sum(x for x,y in SERVO_XY)/len(SERVO_XY)

def horn_center_x(configuration):
    return HORN_CENTER_X + servo_shift_x(configuration)

def servo_xy(configuration):
    return tuple((x + servo_shift_x(configuration), y) for x, y in SERVO_XY)

def clamp_screw_x(configuration):
    if configuration == 'adapter':
        return carrier_bounds(configuration)[0] + ADAPTER_SCREW_FRONT_MARGIN_MM
    return horn_center_x(configuration)

def rear_flat_x(configuration):
    if configuration == 'adapter':
        return carrier_bounds(configuration)[0] + ADAPTER_CLAMP_DEPTH_MM - RI - T
    # Thread major radius, not the smaller laser pilot, clears the die zone.
    rear_hole = max(x for x, y in mount_xy(configuration))
    required = rear_hole + 1.0 + CLAMP_BEND_HALF_DIE - CLAMP_HALF_BEND_ALLOWANCE
    return math.ceil(required * 100) / 100


def mount_xy(configuration):
    if configuration=='pi_hat': return PI_XY
    if configuration=='adapter': return tuple((x+ADAPTER_STACK_CENTER_X,y) for x,y in ADAPTER_XY)
    raise ValueError(configuration)


def carrier_bottom_z(configuration):
    return old.top_screw_z(configuration)+(LOWER_POST_HEIGHT-old.STANDOFF_HEIGHT_MM)+UPPER_POST_HEIGHT

def carrier_top_z(configuration):
    return carrier_bottom_z(configuration)+CARRIER_T

def servo_mount_z(configuration):
    return carrier_top_z(configuration)+SERVO_POST_HEIGHT

def cylinder(r,h,x,y,z=0):
    return bd.Solid.make_cylinder(r,h,bd.Plane(origin=(x,y,z)))

def rounded_panel(x0,x1,z,front_only=False,*,width=WIDTH,thickness=T):
    s=bd.Solid.make_box(x1-x0,width,thickness,bd.Plane(origin=(x0,-width/2,z)))
    es=[e for e in s.edges() if abs(e.length-thickness)<1e-6
        and (not front_only or abs(e.center().X-x0)<1e-6)]
    return s.fillet(old.CORNER_RADIUS_MM,es)

def quarter_bend(cx,cz,upper,width=WIDTH):
    ro=RI+T
    plane=bd.Plane(origin=(cx,-width/2,cz),z_dir=(0,1,0))
    ring=bd.Solid.make_cylinder(ro,width,plane).cut(bd.Solid.make_cylinder(RI,width,plane))
    clip=bd.Solid.make_box(ro,width,ro,
        bd.Plane(origin=(cx,-width/2,cz if upper else cz-ro)))
    return as_single_shape(ring.intersect(clip))

def make_clamp(configuration='pi_hat'):
    front, _, width = carrier_bounds(configuration)
    tangent = rear_flat_x(configuration)
    outer_wall = tangent + RI + T
    ztop=-RI; zbottom=-DESK_OPENING_MM+RI
    top=rounded_panel(front,tangent,0,True,width=width)
    bottom=rounded_panel(front,tangent,-DESK_OPENING_MM-T,True,width=width)
    wall=bd.Solid.make_box(T,width,ztop-zbottom,
        bd.Plane(origin=(outer_wall-T,-width/2,zbottom)))
    s=as_single_shape(top.fuse(bottom,wall,quarter_bend(tangent,ztop,True,width),
                              quarter_bend(tangent,zbottom,False,width)))
    cuts=[cylinder(CLAMP_M2_TAP_DIAMETER/2,T,x,y) for x,y in mount_xy(configuration)]
    cuts.append(cylinder(CLAMP_M8_TAP_DIAMETER/2,T,clamp_screw_x(configuration),0,
                         -DESK_OPENING_MM-T))
    s=as_single_shape(s.cut(*cuts)).clean()
    assert s.is_valid and len(s.solids())==1
    s.label='short_stack_clamp' if configuration=='pi_hat' else 'adapter_stack_clamp'
    s.color=ALUMINUM_5052_COLOR
    return s


