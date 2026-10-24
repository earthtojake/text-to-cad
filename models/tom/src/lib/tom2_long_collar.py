"""Shared long-collar yoke, authored in the production shoulder frame."""
import build123d as bd
from lib.booleans import as_single_shape as one
from lib.tom2_link_profiles import _unify
from lib import horn_cap

EXTENSION=3.6
T=2.032
PITCH=(-51.5,0,21.3152)
CORNER_RADIUS=horn_cap.CIRCULAR_HORN_FORK_PATTERN.cap_geometry[0]
WEB_X=-34.024512259925
COLLAR_TOP_TANGENT=46.0098


def box(x0,x1,y0,y1,z0,z1):
    return bd.Solid.make_box(x1-x0,y1-y0,z1-z0,bd.Plane(origin=(x0,y0,z0)))


def shared_yoke(original):
    result=one(original)
    # Expand only the web's two selected upper diagonals. Their tangents
    # now advance one millimetre in Z for each millimetre in Y.
    additions=[]
    for y0,y1,old_z in ((-6,-15.5,29.08416390585),(5,15.5,28.81914429419)):
        new_z=COLLAR_TOP_TANGENT-abs(y1-y0)
        f=bd.Face(bd.Wire.make_polygon([
            (WEB_X-T,y0,COLLAR_TOP_TANGENT),
            (WEB_X-T,y1,new_z),(WEB_X-T,y1,old_z)],close=True))
        additions.append(bd.Solid.extrude(f,(T,0,0)))
    result=one(result.fuse(*additions)).clean()
    # Match the inside transition radius to the opposite circular horn cap.
    for sign in (-1,1):
        result=horn_cap.apply_narrow_horn_fork(result,
            center=(PITCH[0],sign*(18.3+T/2),PITCH[2]),
            across=(0,0,1),outboard=(-1,0,0),normal=(0,1,0),
            thickness_mm=T,half_width_mm=9.975,
            pattern=horn_cap.CircularSideEntryHornForkPattern(
                straight_back=True,stem_edge_mm=4.5,
                entry_corner_radius_mm=CORNER_RADIUS,
                arc_sweep_deg=45,bend_corner_radius_mm=3),
            closed_side_mm=9.975,bend_return_outboard_mm=PITCH[0]-(WEB_X-2.9972))
    # Split in a constant-width straight section, away from bends and caps.
    split=-30.0
    keep=one(result.intersect(box(-100,split,-50,50,-20,100)))
    tips=one(result.intersect(box(split,0,-50,50,-20,100))).moved(bd.Pos(EXTENSION,0,0))
    bridges=[box(split,split+EXTENSION,-6,5,z,z+T) for z in (8.343,46.975)]
    result=_unify(one(keep.fuse(tips,*bridges)).clean())
    assert result.is_valid and len(result.solids())==1
    result.label=original.label;result.color=original.color
    return result


def filled_upper_link(original):
    # Close the previous high diagonal roll clearance; retain the lower
    # horizontal opening for the horn/case, at 6.5 mm above the roll axis.
    roll_x=155.516116240922;roll_z=79.63268774003745
    right=min(roll_x+23,original.bounding_box().max.X)
    fills=[box(roll_x-23.7002,right,y,y+T,
               roll_z+6.5,roll_z+22.325+.001) for y in (-18.532,15.5)]
    result=_unify(one(original.fuse(*fills)).clean())
    assert result.is_valid and len(result.solids())==1
    result.label=original.label;result.color=original.color
    return result
