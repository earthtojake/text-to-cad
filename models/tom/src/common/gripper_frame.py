"""The canonical gripper frame: one centered part at both the gripper and the
shoulder-yaw mount. Supersedes the end-for-end template in end_effector/."""
import build123d as bd
from cadgen import memo, read_step
from lib import sheet_rule_scs as scs
from lib.materials import ALUMINUM_5052_COLOR
from lib.booleans import as_single_shape
from lib.legacy_base_support import INPUTS
from lib.restored_gripper import mirrored_frame
from lib.restored_frame_gauge import (
    CASE_BAND_Y_MM, CASE_SERVO_ORIGIN_MM, CASE_SEAT_Z_MM,
    WALL_FACE_X_MM, HORN_SEATS_Y_MM,
    CASE_SERVO_TO_FRAME,
)
from lib.gripper_frame_layout import GRIPPER_ENVELOPE_SHIFT_Y_MM
from lib.servo_case_flange import CASE_MIRROR_X_MM
from lib.servo_fit import SERVO
from lib.yoke_design_rules import COLLAR_NECK_WIDTH_MM
from lib.gripper_case_outline import gripper_case_outline
from lib.link_assembly import location_from_transform


def _box(lo, hi):
    return bd.Solid.make_box(*(b-a for a,b in zip(lo,hi)), bd.Plane(origin=lo))


def centered_frame(legacy):
    """Keep the wrist horn interface; center the case band and its payload.

    Retain only the case holes occupied in the flipped jaw-servo orientation.
    The external case flange profiles still derive from the common interface.
    """
    t, ri = scs.THICKNESS_MM, scs.EFFECTIVE_BEND_RADIUS_MM
    ro = ri+t
    shift = GRIPPER_ENVELOPE_SHIFT_Y_MM
    cy0, cy1 = (v+shift for v in CASE_BAND_Y_MM)
    hy0, hy1 = HORN_SEATS_Y_MM[0]+ri, HORN_SEATS_Y_MM[1]-ri
    cx, cz = WALL_FACE_X_MM-ro, CASE_SEAT_Z_MM-ri
    pieces = [as_single_shape(legacy.intersect(_box((-100,-100,-100),(0,hy0,100)))),
              as_single_shape(legacy.intersect(_box((-100,hy1,-100),(0,100,100))))]
    for sign in (-1,1):
        faces = [f for f in legacy.faces() if f.geom_type == bd.GeomType.PLANE
                 and abs(f.normal_at().Z) > .999
                 and abs(f.center().Z-sign*CASE_SEAT_Z_MM) < 1e-6]
        face = max(faces, key=lambda f:f.area)
        holes = list(face.inner_wires())
        if sign < 0:
            occupied_y = [CASE_SERVO_ORIGIN_MM[1]+2*CASE_MIRROR_X_MM-x
                          for x in SERVO.case_upper_hole_x_mm]
            holes = [w for w in holes if any(abs(w.edges()[0].arc_center.Y-y)<1e-6 for y in occupied_y)]
        if len(holes) != 2:
            raise ValueError('Expected two occupied holes per jaw case face')
        side = 'lower' if sign > 0 else 'upper'
        seat = SERVO.case_lower_y_mm if side == 'lower' else SERVO.case_upper_y_mm
        edges = []
        for kind, *coords in gripper_case_outline(side):
            pts = [(x, seat, y) for x,y in coords]
            edges.append(bd.Edge.make_line(*pts) if kind == 'line'
                         else bd.Edge.make_three_point_arc(*pts))
        outline = bd.Wire(edges).moved(location_from_transform(CASE_SERVO_TO_FRAME))
        flat = bd.Face(outline, holes)
        pieces.append(bd.Solid.extrude(flat,(0,0,sign*t)).moved(bd.Pos(0,shift,0)))
        ring = bd.Solid.make_cylinder(ro,cy1-cy0,bd.Plane(origin=(cx,cy0,sign*cz),z_dir=(0,1,0))).cut(
            bd.Solid.make_cylinder(ri,cy1-cy0,bd.Plane(origin=(cx,cy0,sign*cz),z_dir=(0,1,0))))
        z0,z1 = sorted((sign*cz,sign*(cz+ro)))
        pieces.append(as_single_shape(ring.intersect(_box((cx,cy0,z0),(cx+ro,cy1,z1)))))
    # A centered cross: full case band joined to the unchanged wrist neck.
    pieces.append(_box((WALL_FACE_X_MM-t,cy0,-cz),(WALL_FACE_X_MM,cy1,cz)))
    half_neck = COLLAR_NECK_WIDTH_MM/2
    pieces.append(_box((WALL_FACE_X_MM-t,hy0,-half_neck),(WALL_FACE_X_MM,hy1,half_neck)))
    result = as_single_shape(pieces[0].fuse(*pieces[1:])).clean()
    if not result.is_valid or len(result.solids()) != 1:
        raise ValueError('Centered gripper frame must be one valid sheet solid')
    result.label, result.color = 'gripper_frame', ALUMINUM_5052_COLOR
    return result


@memo
def gripper_frame():
    return centered_frame(mirrored_frame(read_step(INPUTS/'gripper.step').children[0]))
