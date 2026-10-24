"""Re-form the recovered frame at the selected stock using fitted outlines.

Case seats Z=+/-16 and horn seats Y=11.232/47.832 are fixed mounting datums.
The wall's positive-X face also stays fixed. Free sheet faces and all four
quarter-circle bends are rebuilt at the selected stock gauge and radius.
"""
import build123d as bd
from lib import sheet_rule_scs as scs
from lib.booleans import as_single_shape
from lib.frame_horn_taper import taper_horn_arms
from lib.horn_cap import (
    apply_y_normal_caps, FRAME_HORN_FORK_PATTERN, FRAME_HORN_CAP_DIAMETER_MM,
)
from lib.horn_neck import circle_neck_outline
from lib.servo_case_flange import (
    case_flange, CASE_MIRROR_X_MM, REVERSIBLE_FLANGE_HALF_WIDTH_MM,
    CASE_BACK_EDGE_MM,
)
from lib.servo_fit import SERVO
from lib.link_assembly import location_from_transform

# Vendor servo to recovered frame. Mounting datums remain fixed.
CASE_SERVO_ORIGIN_MM = (-63.0626,32.2074,SERVO.case_mid_y_mm)
CASE_SERVO_TO_FRAME = (
    0,0,-1,CASE_SERVO_ORIGIN_MM[0],
    1,0,0,CASE_SERVO_ORIGIN_MM[1],
    0,-1,0,CASE_SERVO_ORIGIN_MM[2],
    0,0,0,1)

CASE_SEAT_Z_MM = SERVO.case_span_mm/2
WALL_FACE_X_MM = -41.5596
CASE_BAND_Y_MM = tuple(CASE_SERVO_ORIGIN_MM[1]+CASE_MIRROR_X_MM
    +sign*REVERSIBLE_FLANGE_HALF_WIDTH_MM for sign in (-1,1))
HORN_SEATS_Y_MM = (11.232,47.832)
ARM_HALF_WIDTH_MM = 10.0
SOURCE_CASE_TANGENT_X_MM = CASE_SERVO_ORIGIN_MM[0]-CASE_BACK_EDGE_MM
SOURCE_HORN_TANGENT_X_MM = -40.5944
SOURCE_WALL_HALF_Z_MM = 15.0348
SOURCE_HORN_TANGENTS_Y_MM = (12.1972,46.8668)


def _box(lo,hi):
    return bd.Solid.make_box(*(b-a for a,b in zip(lo,hi)),bd.Plane(origin=lo))


def with_sheet_stock(original):
    q=original.moved(original.location.inverse())
    t,ri=scs.THICKNESS_MM,scs.EFFECTIVE_BEND_RADIUS_MM
    ro=ri+t
    def face(axis,value):
        candidates=[f for f in q.faces()if f.geom_type==bd.GeomType.PLANE
                    and abs(tuple(f.normal_at())[axis])>.999
                    and abs(tuple(f.center())[axis]-value)<1e-6]
        return max(candidates,key=lambda f:f.area)
    def extend_face(f,vector):return bd.Solid.extrude(f,vector)
    pieces=[]
    cy0,cy1=CASE_BAND_Y_MM
    case_cx=WALL_FACE_X_MM-ro
    case_cz=CASE_SEAT_Z_MM-ri
    # Shared case profiles and bores, extended to the current bend tangent.
    for sign in (-1,1):
        side = 'lower' if sign > 0 else 'upper'
        pieces.append(case_flange(side,z_sign=-1,reversible=True,
            thickness_mm=t).moved(location_from_transform(CASE_SERVO_TO_FRAME)))
        z0,z1=sorted((sign*CASE_SEAT_Z_MM,sign*(CASE_SEAT_Z_MM+t)))
        if case_cx > SOURCE_CASE_TANGENT_X_MM+1e-7:
            pieces.append(_box((SOURCE_CASE_TANGENT_X_MM,cy0,z0),(case_cx,cy1,z1)))
        center=(case_cx,cy0,sign*case_cz)
        plane=bd.Plane(origin=center,z_dir=(0,1,0))
        ring=bd.Solid.make_cylinder(ro,cy1-cy0,plane).cut(
            bd.Solid.make_cylinder(ri,cy1-cy0,plane))
        bz0,bz1=sorted((sign*case_cz,sign*(case_cz+ro)))
        pieces.append(as_single_shape(ring.intersect(
            _box((case_cx,cy0,bz0),(case_cx+ro,cy1,bz1)))))
    # Central sheet wall, extended only to meet the new bend tangencies.
    pieces.append(extend_face(face(0,WALL_FACE_X_MM),(-t,0,0)))
    for sign in (-1,1):
        z0,z1=sorted((sign*SOURCE_WALL_HALF_Z_MM,sign*case_cz))
        if z1-z0 > 1e-7:
            pieces.append(_box((WALL_FACE_X_MM-t,cy0,z0),(WALL_FACE_X_MM,cy1,z1)))
    horn_cx=WALL_FACE_X_MM+ri
    for seat,old_tangent,sign in zip(HORN_SEATS_Y_MM,SOURCE_HORN_TANGENTS_Y_MM,(-1,1)):
        tangent=seat-sign*ri
        # Rebuild the horn-sheet blank rather than reusing the recovered
        # smaller cap. The bend tangent and seating plane remain fixed;
        # the shared neck trim finishes its inboard edges after forming.
        outline=circle_neck_outline(
            center=(SERVO.horn_axis_x_mm,seat,0),
            radius_mm=FRAME_HORN_CAP_DIAMETER_MM/2,
            neck_width_mm=2*ARM_HALF_WIDTH_MM,
            neck_start_mm=horn_cx-SERVO.horn_axis_x_mm,
            along=(1,0,0),across=(0,0,1))
        pieces.append(bd.Solid.extrude(bd.Face(outline),(0,sign*t,0)))
        y0,y1=sorted((seat,seat+sign*t))
        if SOURCE_HORN_TANGENT_X_MM-horn_cx > 1e-7:
            pieces.append(_box((horn_cx,y0,-ARM_HALF_WIDTH_MM),
                               (SOURCE_HORN_TANGENT_X_MM,y1,ARM_HALF_WIDTH_MM)))
        wy0,wy1=sorted((old_tangent,tangent))
        if wy1-wy0 > 1e-7:
            pieces.append(_box((WALL_FACE_X_MM-t,wy0,-ARM_HALF_WIDTH_MM),
                               (WALL_FACE_X_MM,wy1,ARM_HALF_WIDTH_MM)))
        plane=bd.Plane(origin=(horn_cx,tangent,-ARM_HALF_WIDTH_MM))
        ring=bd.Solid.make_cylinder(ro,2*ARM_HALF_WIDTH_MM,plane).cut(
            bd.Solid.make_cylinder(ri,2*ARM_HALF_WIDTH_MM,plane))
        by0,by1=sorted((tangent,tangent+sign*ro))
        pieces.append(as_single_shape(ring.intersect(
            _box((horn_cx-ro,by0,-ARM_HALF_WIDTH_MM),
                 (horn_cx,by1,ARM_HALF_WIDTH_MM)))))
    result=as_single_shape(pieces[0].fuse(*pieces[1:])).clean()
    if not result.is_valid or len(result.solids())!=1:
        raise ValueError('Re-formed frame must be one valid sheet solid')
    result=taper_horn_arms(result)
    # The recovered outline contains a historical center opening. Reapply
    # the shared interface so yaw and gripper copies follow head-clearance
    # changes while their seating planes and mounting-hole axes stay fixed.
    result=apply_y_normal_caps(result,
        center_xz=(SERVO.horn_axis_x_mm,0),
        bands=((HORN_SEATS_Y_MM[0]-t,HORN_SEATS_Y_MM[0]),
               (HORN_SEATS_Y_MM[1],HORN_SEATS_Y_MM[1]+t)),
        half_width_mm=FRAME_HORN_CAP_DIAMETER_MM/2,outboard_axis='x',
        pattern=FRAME_HORN_FORK_PATTERN).clean()
    result=result.moved(original.location)
    result.label,result.color=original.label,original.color
    return result
