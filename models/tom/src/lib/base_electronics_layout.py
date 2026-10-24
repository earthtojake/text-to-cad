"""One full-width desk clamp, with interchangeable Pi/HAT and adapter stacks.

Dimensions below are in the robot's base frame (top plate underside Z=0).
Only the final assembly helper converts to the recovered base STEP frame.
PCB datums are measured from the supplied STEP files, not component bounds.
The deep C section needs SCS tooling review; do not mark this base release
approved merely because its local hole and bend distances pass.
"""
import build123d as bd
from base.legacy.base_clamp import (
    PLATE_THICKNESS_MM as T,
)

from hardware.m2_mf_standoff_10mm import m2_mf_standoff_10mm
from lib.materials import STANDOFF_COLOR
from purchased.raspberry_pi_5 import raspberry_pi_5
from purchased.bus_servo_driver_hat_a import bus_servo_driver_hat_a
from purchased.bus_servo_adapter_a import bus_servo_adapter_a

DESK_OPENING_MM = 65.0
CORNER_RADIUS_MM = 4.0
STANDOFF_HEIGHT_MM = 10.0  # same existing M2 F/F 4 AF body at both levels
PI_CENTER_X_MM = 82.0
# The supplied Pi model seats its board bottom on y=0; the layout keeps Raspberry Pi's
# published 1.4 mm board, so this model's 1.6 mm board overlaps the spacer above by 0.2 mm.
PI_PCB_BOTTOM_LOCAL_MM = 0.0
PI_PCB_THICKNESS_MM = 1.4
HAT_PCB_THICKNESS_MM = 1.59999934
ADAPTER_PCB_THICKNESS_MM = 1.59999934
PCB_BOTTOM_Z_MM = T + STANDOFF_HEIGHT_MM
PI_TOP_Z_MM = PCB_BOTTOM_Z_MM + PI_PCB_THICKNESS_MM
HAT_TOP_Z_MM = PI_TOP_Z_MM + STANDOFF_HEIGHT_MM + HAT_PCB_THICKNESS_MM
# Pi native +X is the USB/Ethernet edge. Aim it toward the clamp wall
# (world +X); rotate the HAT by the same quarter-turn to retain GPIO mating.
# Pi native Y is PCB normal and Z is its short edge.
def pi_location():
    return bd.Pos(PI_CENTER_X_MM, 0, PCB_BOTTOM_Z_MM-PI_PCB_BOTTOM_LOCAL_MM) * bd.Rot(X=90)
# HAT GPIO local X=52.5 meets Pi native Z=-24.5 at world Y=+24.5.
# HAT power sockets consequently face sideways, world -Y.
def hat_location():
    return bd.Pos(PI_CENTER_X_MM+22.5, -28, HAT_TOP_Z_MM) * bd.Rot(Z=90)
# Adapter local -Y carries DC and USB-C: +90 degrees aims both at +X.
def adapter_location():
    return bd.Pos(PI_CENTER_X_MM+16.5, -21, PCB_BOTTOM_Z_MM+ADAPTER_PCB_THICKNESS_MM) * bd.Rot(Z=90)
PI_MOUNT_XY = tuple((PI_CENTER_X_MM+x, -z) for x in (-39.,19.) for z in (-24.5,24.5))
# Preserve the 0.012 mm asymmetry in the supplied adapter model.
ADAPTER_HOLES_LOCAL_XY = ((2.49998738,2.49998738),(39.49998958,2.49998738),
                        (2.49998738,30.49999234),(39.51198854,30.49999234))
ADAPTER_MOUNT_XY = tuple((PI_CENTER_X_MM+16.5-y,-21+x) for x,y in ADAPTER_HOLES_LOCAL_XY)
SERVO_MOUNT_XY = tuple((x,y) for y in (10.25,-10.25) for x in (8.3,29.0))


def top_screw_z(configuration):
    return HAT_TOP_Z_MM if configuration == 'pi_hat' else PCB_BOTTOM_Z_MM+ADAPTER_PCB_THICKNESS_MM


def electronics(configuration):
    """PCB stack and interlevel hardware; lower four supports are siblings."""
    children=[]
    if configuration=='pi_hat':
        pi=raspberry_pi_5().moved(pi_location());pi.label='raspberry_pi_5'
        hat=bus_servo_driver_hat_a().moved(hat_location());hat.label='bus_servo_driver_hat_a'
        children.extend((pi,hat))
        # Male-female post: its own 3 mm stud passes through the Pi's mounting
        # hole into the post below, so the level needs no separate joiner. The
        # Pi's 1.4 mm board leaves 1.6 mm of that stud engaged.
        post=m2_mf_standoff_10mm()
        for i,(x,y) in enumerate(PI_MOUNT_XY,1):
            upper=post.moved(bd.Pos(x,y,PI_TOP_Z_MM));upper.label=f'm2_pi_standoff_{i}'
            upper.color=STANDOFF_COLOR
            children.append(upper)
    elif configuration=='adapter':
        adapter=bus_servo_adapter_a().moved(adapter_location())
        adapter.label='bus_servo_adapter_a';children.append(adapter)
    else:raise ValueError(configuration)
    return bd.Compound(children=children,label=f'electronics_{configuration}')
