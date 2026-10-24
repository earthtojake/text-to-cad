"""5052-H32 ALU-125 yokes, 3.175 mm stock and 3.175 mm inside bends.

SendCutSend catalog/specification snapshot: analysis/yokes_3mm_20261009.
Keep the existing horn contact planes and 13.6 mm axis-to-tangent lands.
The wider formed web increases orthogonal axis spacing by 5.5626 mm.
"""
import build123d as bd
from lib.booleans import as_single_shape as one
from lib.tom2_link_profiles import _unify
from lib.horn_cap import apply_horn_fork,CIRCULAR_HORN_FORK_PATTERN
from lib.materials import ALUMINUM_5052_COLOR
from lib import sheet_rule_scs as sheet
from math import ceil
T=3.175
RI=3.175
RO=T+RI
PITCH=(-51.5,0,21.3152)
# Compact manufacturing-only experiment. The nearest 3.2 mm mounting bore
# remains outside half the die width, with 0.381 mm forming + 0.127 mm cut
# allowance. Motion/plate-contact envelopes intentionally do not size this.
BEND_FEATURE_MARGIN=.508
HALF_DIE_WIDTH=16.002/2
BEND_ALLOWANCE_90=__import__('math').pi/2*(RI+.44*T)
MIN_AXIS_TO_TANGENT=7+1.6+HALF_DIE_WIDTH+BEND_FEATURE_MARGIN-BEND_ALLOWANCE_90/2
AXIS_TO_TANGENT=ceil(MIN_AXIS_TO_TANGENT*10)/10
# Equal length on all four collars. The web sits midway between the two
# horn axes, including sheet gauge and the two opposing inside bend radii.
WEB_X=PITCH[0]+AXIS_TO_TANGENT+T+RI
ROLL=(WEB_X+RI+AXIS_TO_TANGENT,0,PITCH[2])
AXIS_SPACING_REDUCTION=-13.9-ROLL[0]
NECK=11.0
AXIS_OFFSET=7.3598
# Stop the diagonal at the mating plate's nearer inside wall. Short straight
# runs at both ends preserve the full neck width and all four collar bends.
DIAGONAL_END_RELIEF=1.8348


def box(x0,x1,y0,y1,z0,z1):
    return bd.Solid.make_box(x1-x0,y1-y0,z1-z0,bd.Plane(origin=(x0,y0,z0)))


def make_yoke(*,collar_extension=0.0):
    """Equal extension on all four collars; both horn seats stay symmetric."""
    web_x=WEB_X+collar_extension
    roll_x=ROLL[0]+2*collar_extension
    x,_,z=PITCH;h=18.3-RI;n=NECK/2
    d=DIAGONAL_END_RELIEF
    outline=[(-h,-n),(-h+d,-n),(-n,-h+d),(-n,-h),
             (n,-h),(n,-h+d),(h-d,-n),(h,-n),
             (h,n),(h-d,n),(n,h-d),(n,h),
             (-n,h),(-n,h-d),(-h+d,n),(-h,n)]
    web=bd.Solid.extrude(bd.Face(bd.Wire.make_polygon(
        [(web_x-T,y,z+dz) for y,dz in outline],close=True)),(T,0,0))
    pieces=[web]
    for sign in (-1,1):
        # Side-three pitch attachment: two opposite screws and the stem-side screw.
        cx=web_x-T-RI;y=sign*18.3;ya,yb=sorted((y,y+sign*T))
        cap=box(x,cx,ya,yb,z-n,z+n)
        cap=apply_horn_fork(cap,center=(x,y+sign*T/2,z),across=(0,0,1),
            outboard=(-1,0,0),normal=(0,1,0),thickness_mm=T,half_width_mm=9.975,
            pattern=CIRCULAR_HORN_FORK_PATTERN)
        roots=[e for e in cap.edges().filter_by(bd.Axis.Y)
               if x+1<e.center().X<cx-1 and abs(abs(e.center().Z-z)-n)<1e-5]
        if roots:cap=cap.fillet(.6,roots).clean()
        pl=bd.Plane(origin=(cx,sign*h,z-n),z_dir=(0,0,1))
        ring=one(bd.Solid.make_cylinder(RO,NECK,pl).cut(bd.Solid.make_cylinder(RI,NECK,pl)))
        low,high=sorted((sign*h,sign*(h+RO)))
        bend=one(ring.intersect(box(cx,cx+RO,low,high,z-n,z+n)))
        pieces.extend((cap,bend))
        # Identical narrow neck treatment on the perpendicular roll collar.
        cx=web_x+RI;seat=z+sign*18.3;za,zb=sorted((seat,seat+sign*T))
        cap=box(cx,roll_x,-n,n,za,zb)
        cap=apply_horn_fork(cap,center=(roll_x,0,seat+sign*T/2),across=(0,1,0),
            outboard=(1,0,0),normal=(0,0,1),thickness_mm=T,half_width_mm=9.975,
            pattern=CIRCULAR_HORN_FORK_PATTERN)
        roots=[e for e in cap.edges().filter_by(bd.Axis.Z)
               if cx+1<e.center().X<roll_x-1 and abs(abs(e.center().Y)-n)<1e-5]
        if roots:cap=cap.fillet(.6,roots).clean()
        pl=bd.Plane(origin=(cx,-n,z+sign*h),z_dir=(0,1,0))
        ring=one(bd.Solid.make_cylinder(RO,NECK,pl).cut(bd.Solid.make_cylinder(RI,NECK,pl)))
        low,high=sorted((z+sign*h,z+sign*(h+RO)))
        bend=one(ring.intersect(box(cx-RO,cx,-n,n,low,high)))
        pieces.extend((cap,bend))
    result=_unify(one(pieces[0].fuse(*pieces[1:])).clean())
    assert result.is_valid and len(result.solids())==1
    result.color=ALUMINUM_5052_COLOR;result.label='symmetric_horn_yoke'
    return result
