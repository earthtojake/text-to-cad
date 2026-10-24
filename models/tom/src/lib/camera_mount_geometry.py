"""Raised 28-degree camera frame with a full-width collar flush to its foot."""
import math
import build123d as bd
from lib.camera_mount_interface import (
    T,RI,polygon,
)
from lib import camera_bends as profile
from lib import sheet_rule_scs as scs

ROOT_LIFT_MM=10.0
PANEL_LENGTH=40.0
PANEL_CENTER_S=PANEL_LENGTH/2
LATERAL_SHIFT_MM=0.0
# Place the grasp region near the image centre while retaining forward context.
# Add 4 mm toward the claws relative to the accepted raised mount.
# This leaves only the servo case edge visible in the 103-degree-HFOV feed.
CAMERA_PITCH_DEG=28.0
LENS_FORWARD_OFFSET_MM=8.0
PANEL_HEADING=math.radians(90-CAMERA_PITCH_DEG)
# Preserve the lens height while solving the plate and neck around one common
# center for both patterns. The 12.5 mm lens datum matches
# the current authored Innomaker reference model.
LENS_FROM_PANEL_MM=12.5-T
REFERENCE_CAMERA_CENTER=profile.add(profile.datums(ROOT_LIFT_MM)[-1],(LATERAL_SHIFT_MM,0,0))
LOCKED_LENS_LOCAL=profile.add(
    profile.add(REFERENCE_CAMERA_CENTER,profile.normal(profile.PANEL_HEADING),LENS_FROM_PANEL_MM),
    (0,LENS_FORWARD_OFFSET_MM,0))
CAMERA_CENTER=profile.add(LOCKED_LENS_LOCAL,profile.normal(PANEL_HEADING),-LENS_FROM_PANEL_MM)
# The collar spans the entire mounting foot, eliminating its sideways step.
# The panel and its optical center share the collar's lateral centerline.
COLLAR_CENTER_X=0.0
# Both remaining bends turn in the same sense. Their radius offsets cancel
# at the shared support, so its direction and length solve directly between
# the fixed foot and accepted camera-panel tangent points.
FOOT_END=profile.add(profile.datums(ROOT_LIFT_MM)[0],(COLLAR_CENTER_X,0,0))
PANEL_START=profile.add(CAMERA_CENTER,profile.direction(PANEL_HEADING),-PANEL_CENTER_S)
COLLAR_PANEL_TANGENT=(COLLAR_CENTER_X,*PANEL_START[1:])
SUPPORT_VECTOR=tuple(p-f-RI*(n0-n1) for p,f,n0,n1 in zip(
    COLLAR_PANEL_TANGENT,FOOT_END,profile.normal(math.pi),profile.normal(PANEL_HEADING)))
RISER_HEADING=math.atan2(SUPPORT_VECTOR[2],SUPPORT_VECTOR[1])
RISER_LENGTH=math.hypot(SUPPORT_VECTOR[1],SUPPORT_VECTOR[2])
ROOT_LENGTH=0.0
CAMERA_HOLE_PITCH=27.0
CAMERA_MOUNT_HOLE_DIAMETER=2.2
CAMERA_PATTERNS=((27.0,PANEL_CENTER_S),(33.75,PANEL_CENTER_S))
TIE_SLOT_WIDTH=2.2
TIE_SLOT_LENGTH=8.0
TIE_SLOT_X=16.75
TIE_SLOT_CORNER_CLIP=0.5
# Maximize the opening within the retained slots and M2 clearance holes. Reserve
# both opposing cut tolerances instead of drawing exactly at the SCS floor.
# ALU-080 SKU: 0.030 in cut bridge, 0.024 in tap/hole-to-edge;
# refreshed 2026-09-13, .cad-retired/references/camera-mount/max-opening/scs-selected.json.
WINDOW_EDGE_ALLOWANCE_MM=2*scs.CUT_TOLERANCE_MM
WINDOW_SLOT_WEB_MM=scs.MIN_BRIDGE_SIZE_MM+WINDOW_EDGE_ALLOWANCE_MM
WINDOW_HOLE_EDGE_MM=scs.MIN_HOLE_TO_EDGE_MM+WINDOW_EDGE_ALLOWANCE_MM
WINDOW_DIMENSION_INCREMENT_MM=0.01
WINDOW_SIZE=math.floor(2*(TIE_SLOT_X-TIE_SLOT_WIDTH/2-WINDOW_SLOT_WEB_MM)
                       /WINDOW_DIMENSION_INCREMENT_MM)*WINDOW_DIMENSION_INCREMENT_MM
# The four diagonal lines are equally distant from the inner square hole
# pattern. Leave the full edge allowance around the Ø2.2 through bores.
WINDOW_CORNER_CLIP=math.ceil((WINDOW_SIZE-CAMERA_HOLE_PITCH+math.sqrt(2)*(
    CAMERA_MOUNT_HOLE_DIAMETER/2+WINDOW_HOLE_EDGE_MM))
    /WINDOW_DIMENSION_INCREMENT_MM)*WINDOW_DIMENSION_INCREMENT_MM


def clipped_rectangle(width,height,clip):
    """Square-ended opening with four straight 45-degree corner cuts."""
    assert 0<clip<min(width,height)/2
    x,y=width/2,height/2
    return polygon([(-x+clip,-y),(x-clip,-y),(x,-y+clip),(x,y-clip),
                    (x-clip,y),(-x+clip,y),(-x,y-clip),(-x,-y+clip)])

def panel_cuts():
    cuts=[clipped_rectangle(WINDOW_SIZE,WINDOW_SIZE,WINDOW_CORNER_CLIP).moved(
        bd.Location((0,PANEL_CENTER_S,0)))]
    cuts.extend(bd.Circle(CAMERA_MOUNT_HOLE_DIAMETER/2).moved(
        bd.Location((x,center+y,0))) for pitch,center in CAMERA_PATTERNS
        for x in (-pitch/2,pitch/2) for y in (-pitch/2,pitch/2))
    for x,y,angle in ((-TIE_SLOT_X,0,0),(TIE_SLOT_X,0,0),
                      (0,-TIE_SLOT_X,90),(0,TIE_SLOT_X,90)):
        cuts.append(clipped_rectangle(TIE_SLOT_WIDTH,TIE_SLOT_LENGTH,TIE_SLOT_CORNER_CLIP)
                    .rotate(bd.Axis.Z,angle).moved(bd.Location((x,PANEL_CENTER_S+y,0))))
    return cuts


def camera_plane():
    return bd.Plane(origin=CAMERA_CENTER,x_dir=(1,0,0),z_dir=profile.normal(PANEL_HEADING))
