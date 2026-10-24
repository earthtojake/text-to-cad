"""Local gripper edits for the recovered tom assembly; no part export side effects.

The two recovered claws use different native coordinate systems. Tip tooling
uses (u=length toward root, d=flange depth, v=width across the gripping face)
so the same dimensions and manufacturing rules control both tips.
"""
import build123d as bd
import math
from lib.booleans import as_single_shape
from lib import sheet_rule_scs as scs
from lib.corner_rules import OUTLINE_CORNER_R_MM
from lib.servo_fit import SERVO
from lib.servo_case_flange import (
    case_flange, CASE_UPPER_INNER_EDGE_MM, CASE_LOWER_INNER_EDGE_MM, FIXED_FLANGE_X_BOUNDS_MM,
    CASE_BACK_EDGE_MM, CASE_LOWER_RECESS_DEPTH_MM,
    CASE_LOWER_RECESS_HALF_WIDTH_MM,
)
from lib.link_assembly import location_from_transform
from lib.gripper_frame_layout import GRIPPER_PINCH_CENTER_IN_CLAW_Y_MM
from lib.horn_cap import (
    apply_narrow_horn_fork, NARROW_HORN_FORK_PATTERN, ArcBreakBendHornForkPattern,
    apply_horn_fork, FRAME_HORN_CAP_DIAMETER_MM, FRAME_HORN_FORK_PATTERN,
)
from lib.materials import ALUMINUM_5052_COLOR

CLAW_FACE_LENGTH_MM = 60.0  # Finishing length comes from the attachment ends.
CLAW_TIP_WIDTH_MM = 7.0
TIP_TAPER_ANGLE_DEG = 45.0  # Gripping-face nose cuts, relative to the finger axis.
FLANGE_ENVELOPE_CORNER_R_MM = 3.0  # Matches elbow-yoke o1.5.1.e134.
MOUNT_OUTER_CORNER_R_MM = 3.0  # Outer tab and horn-transition corners only.
CLAW_NOSE_CORNER_R_MM = 1.0  # Small free-edge rounds beside the bend-end land.
RELIEF_WIDTH_MM = 1.2  # > t/2 for ALU-080
RELIEF_DEPTH_MM = max(scs.BEND_RELIEF_DEPTH_IN * 25.4,
                      scs.THICKNESS_MM + scs.EFFECTIVE_BEND_RADIUS_MM + .508)
RELIEF_FLAT_INSET_MM = RELIEF_DEPTH_MM - scs.BEND_ALLOWANCE_90_MM / 2
# Smallest straight land satisfying both published flat and formed flange
# minima. Measured from the tangent, excluding the curved bend itself.
TIP_MIN_FLAT_LAND_MM = max(
    scs.MIN_FLANGE_BEFORE_BEND_IN*25.4-scs.BEND_ALLOWANCE_90_MM/2,
    scs.MIN_FLANGE_AFTER_BEND_IN*25.4
    -scs.EFFECTIVE_BEND_RADIUS_MM-scs.THICKNESS_MM)
# Keep the bend flush with the nose shoulder. The flange diagonal retains
# the full minimum straight forming land at that common endpoint.
TIP_FLANGE_SUPPORT_MARGIN_MM = 0.25
TIP_TAPER_FLAT_LAND_MM = TIP_MIN_FLAT_LAND_MM + TIP_FLANGE_SUPPORT_MARGIN_MM

FIXED_WEB_HALF_WIDTH_MM = 16.0-scs.EFFECTIVE_BEND_RADIUS_MM
FIXED_CASE_HOLE_X_MM = -73.3126
# Measured envelope of the imported servo casing (o1.12.2.1.3), excluding
# horn disks. Keep the edge straight beside this envelope before slanting.
FIXED_CASE_BODY_HALF_WIDTH_MM = 12.3625766945
FIXED_UNDERSIDE_HOLES_Y_MM = (18.8002, 39.5002)
CASE_HOLE_RADIUS_MM = 1.1
# Vendor servo coordinates mapped into the recovered fixed claw. Derive this
# from the existing mounting holes so the standard flange retains their axes.
FIXED_SERVO_ORIGIN_X_MM = FIXED_CASE_HOLE_X_MM + SERVO.case_hole_z_mm
FIXED_SERVO_ORIGIN_Y_MM = FIXED_UNDERSIDE_HOLES_Y_MM[0] + max(SERVO.case_upper_hole_x_mm)
TAB_END_Y_MM = FIXED_SERVO_ORIGIN_Y_MM - FIXED_FLANGE_X_BOUNDS_MM[0]
OUTLINE_RADIUS_MM = OUTLINE_CORNER_R_MM

MOVING_ORIGINAL_ROOT_Z_MM = 9.450142
MOVING_FOLD_X_MM = 10.0
MOVING_WEB_HALF_WIDTH_MM = 18.3-scs.EFFECTIVE_BEND_RADIUS_MM
MOVING_WEB_CENTER_Y_MM = -9.1
MOVING_HORN_CENTER_Z_MM = 26.5
MOVING_HORN_RADIUS_MM = 10.0
MOVING_HORN_BANDS_Y_MM = ((-27.4-scs.THICKNESS_MM, -27.4), (9.2, 9.2+scs.THICKNESS_MM))
# The shared side-entry fork retains the near, upper and far horn screws.
# Its open side is the bend side; carry the complete web to that new edge.
MOVING_NARROW_FOLD_X_MM = NARROW_HORN_FORK_PATTERN.stem_edge_mm
CLAW_FLANGE_DEPTH_MM = MOVING_HORN_RADIUS_MM + MOVING_NARROW_FOLD_X_MM
# Full flat stem width, flush with the +3.5 mm horn-connector edge.
# This is flange depth, not sheet gauge; both claws share it.
CLAW_STRAIGHT_FLANGE_WIDTH_MM = CLAW_FLANGE_DEPTH_MM
# Restore the slim 13.5 mm flanges; finishing size comes from claw length.
FIXED_FLANGE_EXTRA_DEPTH_MM = 0.0
MOVING_FLANGE_EXTRA_DEPTH_MM = 0.0
MOVING_WIDE_HORN_PATTERN = ArcBreakBendHornForkPattern(
    arc_sweep_deg=45.0,bend_corner_radius_mm=MOUNT_OUTER_CORNER_R_MM)
GRIPPER_PARALLEL_CLEARANCE_MM = 15.0  # Both gripping surfaces facing forward.
GRIPPER_SHAFT_X_MM = -63.0626
GRIPPER_SHAFT_Y_MM = 47.8002
FIXED_SLANT_DEPARTURE_X_MM = GRIPPER_SHAFT_X_MM-FIXED_CASE_BODY_HALF_WIDTH_MM
# Set both face roots forward enough that the fixed case-mounting beam clears
# the developed gripping web. Face length remains 60 mm; only the roots grow.
# The historic 15 mm datum below locates the unchanged horn interface.
CLAW_ROOT_ADVANCE_MM = -2.0
_previous_tip_dx = MOVING_ORIGINAL_ROOT_Z_MM-1.5-CLAW_FACE_LENGTH_MM-26.5
_inner_dy = -(CLAW_FLANGE_DEPTH_MM-MOVING_HORN_RADIUS_MM
              +scs.EFFECTIVE_BEND_RADIUS_MM+scs.THICKNESS_MM)
_closed_dy = _inner_dy-GRIPPER_PARALLEL_CLEARANCE_MM
_previous_closed_dx = -math.sqrt(_previous_tip_dx**2+_inner_dy**2-_closed_dy**2)
_revised_tip_dx = -math.sqrt((_previous_closed_dx+CLAW_ROOT_ADVANCE_MM)**2
                            +_closed_dy**2-_inner_dy**2)
MOVING_ROOT_SETBACK_MM = (MOVING_ORIGINAL_ROOT_Z_MM-CLAW_FACE_LENGTH_MM
                         -26.5-_revised_tip_dx)
MOVING_BEND_ROOT_Z_MM = MOVING_ORIGINAL_ROOT_Z_MM-MOVING_ROOT_SETBACK_MM
MOVING_TIP_Z_MM = MOVING_BEND_ROOT_Z_MM-CLAW_FACE_LENGTH_MM
MOVING_INNER_TIP_X_MM = GRIPPER_SHAFT_X_MM + MOVING_TIP_Z_MM-MOVING_HORN_CENTER_Z_MM
# Center both noses on the fixed gripping web. The moving web's mounting
# bands are offset by 0.5 mm in this common frame; compensate in its native
# coordinates, instead of offsetting the contact strip within either nose.
FIXED_PINCH_CENTER_Z_MM = 0.0
MOVING_NOSE_CENTER_V_MM = -9.6-MOVING_WEB_CENTER_Y_MM-FIXED_PINCH_CENTER_Z_MM
MOVING_FLANGE_STRAIGHT_DEPTH_MM = CLAW_STRAIGHT_FLANGE_WIDTH_MM
MOVING_FLANGE_OUTSIDE_DEPTH_MM = (MOVING_FLANGE_STRAIGHT_DEPTH_MM
    + scs.EFFECTIVE_BEND_RADIUS_MM+scs.THICKNESS_MM)
MOVING_REVISED_FOLD_X_MM = -MOVING_HORN_RADIUS_MM+MOVING_FLANGE_STRAIGHT_DEPTH_MM
# Extend each bend to the first nose taper. The folded lip retains the
# full SCS minimum land perpendicular to its bend at this endpoint.
CLAW_NOSE_RUN_MM = ((FIXED_WEB_HALF_WIDTH_MM-CLAW_TIP_WIDTH_MM/2)
                   /math.tan(math.radians(TIP_TAPER_ANGLE_DEG)))
CLAW_UNBENT_FACE_LENGTH_MM = CLAW_NOSE_RUN_MM
MOVING_BEND_TIP_Z_MM = MOVING_TIP_Z_MM+CLAW_UNBENT_FACE_LENGTH_MM
MOVING_TAPER_SLOPE = math.tan(math.radians(TIP_TAPER_ANGLE_DEG))
MOVING_REVISED_INNER_Y_MM = GRIPPER_SHAFT_Y_MM-(MOVING_REVISED_FOLD_X_MM
    + scs.EFFECTIVE_BEND_RADIUS_MM+scs.THICKNESS_MM)
# Translate the complete static finger; extend the far mounting flange to it.
# The case bores and case-facing clearance profiles retain their datums.
# Keep the exposed top mounting tab's edge at its established servo datum.
# It must not follow the tilted finger inward through its M2 mounting hole.
FIXED_TOP_TAB_EDGE_Y_MM = (GRIPPER_PINCH_CENTER_IN_CLAW_Y_MM
    - CASE_LOWER_RECESS_HALF_WIDTH_MM)
_tip_dx = MOVING_INNER_TIP_X_MM-GRIPPER_SHAFT_X_MM
_revised_tip_dy = MOVING_REVISED_INNER_Y_MM-GRIPPER_SHAFT_Y_MM


def _tip_contact():
    """Close equal-length fingers symmetrically on the camera-foot centerline.

    The circular moving-tip path fixes contact and the closed joint limit.
    The static root takes the reflected angle, retaining its face length.
    """
    root_to_tip = CLAW_FACE_LENGTH_MM+RELIEF_WIDTH_MM
    def moving_tip(angle):
        return (GRIPPER_SHAFT_X_MM+_tip_dx*math.cos(angle)
                -_revised_tip_dy*math.sin(angle),
                GRIPPER_SHAFT_Y_MM+_tip_dx*math.sin(angle)
                +_revised_tip_dy*math.cos(angle))
    def residual(angle):
        return moving_tip(angle)[1]-GRIPPER_PINCH_CENTER_IN_CLAW_Y_MM
    low,high=0.0,math.radians(30.0)
    if not residual(low)>0>residual(high):
        raise ValueError('Tip contact is outside the design range')
    for _ in range(64):
        mid=(low+high)/2
        if residual(mid)>0:low=mid
        else:high=mid
    angle=(low+high)/2
    x,y=moving_tip(angle)
    # Equal and opposite face angles about the connecting-bracket centerline.
    static_angle=angle
    return (math.degrees(angle),x+root_to_tip*math.cos(static_angle),
            y-root_to_tip*math.sin(static_angle))


(GRIPPER_CLOSE_ANGLE_DEG,FIXED_BEND_ROOT_X_MM,
 FIXED_INNER_ROOT_Y_MM)=_tip_contact()
FIXED_SLANT_ANGLE_DEG = GRIPPER_CLOSE_ANGLE_DEG
FIXED_HEADER_INNER_U_MM = FIXED_BEND_ROOT_X_MM
FIXED_FORMED_ROOT_U_MM = FIXED_HEADER_INNER_U_MM-RELIEF_WIDTH_MM
FIXED_PINCH_TIP_X_MM = FIXED_FORMED_ROOT_U_MM-CLAW_FACE_LENGTH_MM
FIXED_BEND_TIP_X_MM = FIXED_PINCH_TIP_X_MM+CLAW_UNBENT_FACE_LENGTH_MM
# Continue the tilted outer flange into a level, widened mounting header.
# This intersection is derived from the finger, not from the old 0-degree gap.
_static_angle=math.radians(FIXED_SLANT_ANGLE_DEG)
_static_outer_root_x=FIXED_BEND_ROOT_X_MM-MOVING_FLANGE_OUTSIDE_DEPTH_MM*math.sin(_static_angle)
_static_outer_root_y=FIXED_INNER_ROOT_Y_MM-MOVING_FLANGE_OUTSIDE_DEPTH_MM*math.cos(_static_angle)
FIXED_FREE_EDGE_Y_MM=(_static_outer_root_y
    -(FIXED_SLANT_DEPARTURE_X_MM-_static_outer_root_x)*math.tan(_static_angle))
FIXED_CASE_OUTER_EXTENSION_MM=(FIXED_SERVO_ORIGIN_Y_MM
    -FIXED_FLANGE_X_BOUNDS_MM[1]-FIXED_FREE_EDGE_Y_MM)

FIXED_TAPER_SLOPE = MOVING_TAPER_SLOPE


def _prism(vertices, direction):
    return bd.Solid.extrude(bd.Face(bd.Wire.make_polygon(vertices, close=True)), direction)


def _box(lo, hi):
    return bd.Solid.make_box(*(b-a for a,b in zip(lo, hi)), bd.Plane(origin=lo))


def _cut(shape, tool):
    return as_single_shape(shape.cut(tool)).clean()


def _flange_envelope(bend_tip, root, depth):
    """Long taper with an R3 root; keep the bend-end forming land square."""
    radius = FLANGE_ENVELOPE_CORNER_R_MM
    run = root-bend_tip
    if run <= 0 or depth <= TIP_TAPER_FLAT_LAND_MM+radius:
        raise ValueError('Insufficient flange span for the rounded envelope')
    low,high=0.0,math.pi/4
    for _ in range(64):
        angle=(low+high)/2
        nose_depth=TIP_TAPER_FLAT_LAND_MM
        root_corner=root-radius*math.tan(angle/2)
        residual=math.tan(angle)*(root_corner-bend_tip)-(depth-nose_depth)
        if residual>0:high=angle
        else:low=angle
    angle=(low+high)/2
    return dict(slope=math.tan(angle),angle_deg=math.degrees(angle),
                nose_depth=TIP_TAPER_FLAT_LAND_MM,
                root_corner=root-radius*math.tan(angle/2))


def _tip(shape, tip, fold, half_width, point, *, root, tip_center=0.0, bend_end=None, taper_slope=None, nose_half_width=None, nose_center=0.0, flange_depth_mm=None):
    """Recess lips, terminate unsupported bends, then cut the centered nose."""
    import math
    slope = taper_slope if taper_slope is not None else math.tan(math.radians(TIP_TAPER_ANGLE_DEG))
    run = (half_width - CLAW_TIP_WIDTH_MM / 2) / slope
    if run <= 0:
        raise ValueError('Tip must be narrower than the gripping face')
    bend_tip = tip+CLAW_UNBENT_FACE_LENGTH_MM if bend_end is None else bend_end
    flange_depth = CLAW_STRAIGHT_FLANGE_WIDTH_MM if flange_depth_mm is None else flange_depth_mm
    envelope = _flange_envelope(bend_tip,root,flange_depth)
    # The web keeps its nose angle. The side-flange envelope spans the whole
    # wall. Its square nose retains the complete bend-end forming land.
    flange_slope = envelope['slope']
    ramp_tip = bend_tip-envelope['nose_depth']/flange_slope
    vertices = [(tip-20, fold-60), (ramp_tip+60/flange_slope, fold-60),
                (ramp_tip, fold), (tip-20, fold)]
    tool = _prism([point(u,d,-60) for u,d in vertices],
                  bd.Vector(point(0,0,120))-bd.Vector(point(0,0,0)))
    shape = _cut(shape, tool)
    for side in (-1, 1):
        # Open the end relief into the perimeter. The lip, quarter bend and
        # shoulder of the flat nose all stop at one station: no thin tongues,
        # residual curved strips or narrow slots beside the tip.
        edge_v = nose_center+side*(half_width if nose_half_width is None else nose_half_width)
        verts = [point(tip-20,fold-60,edge_v),
                 point(bend_tip,fold-60,edge_v),
                 point(bend_tip,fold-60,side*60),
                 point(tip-20,fold-60,side*60)]
        shape = _cut(shape, _prism(verts,
                     bd.Vector(point(0,100,0))-bd.Vector(point(0,0,0))))
        # Both diagonal cuts start exactly at the flange/bend endpoint.
        # An offset between nose_center and tip_center used to leave a 1 mm
        # ledge on one side and a visibly mismatched top/bottom envelope.
        side_slope = slope
        taper_start = tip+(side*(edge_v-tip_center)-CLAW_TIP_WIDTH_MM/2)/side_slope
        if not tip<taper_start or abs(taper_start-bend_tip)>1e-8:
            raise ValueError('Both nose tapers must meet their flange endpoints')
        verts = [point(tip-20,fold-60,tip_center+side*(CLAW_TIP_WIDTH_MM/2-20*side_slope)),
                 point(taper_start,fold-60,edge_v),
                 point(taper_start,fold-60,side*60),
                 point(tip-20,fold-60,side*60)]
        shape = _cut(shape, _prism(verts,
                     bd.Vector(point(0,100,0))-bd.Vector(point(0,0,0))))
    # Round the outer root transition on each flange. Do not round the nose
    # corner beside the bend: that would cut into the forming support land.
    flange_corners=[point(u,d,
                         side*(half_width+scs.EFFECTIVE_BEND_RADIUS_MM+scs.THICKNESS_MM/2))
                    for side in (-1,1)
                    for u,d in ((envelope['root_corner'],fold-flange_depth),)]
    edges=[e for e in shape.edges()if e.geom_type==bd.GeomType.LINE
           and abs(e.length-scs.THICKNESS_MM)<1e-5
           and any((e.center()-bd.Vector(p)).length<1e-5 for p in flange_corners)]
    if len(edges)!=2:
        raise ValueError(f'Expected two flange envelope root corners, got {len(edges)}')
    shape=shape.fillet(FLANGE_ENVELOPE_CORNER_R_MM,edges).clean()
    return shape


def _finish(original, native):
    if not native.is_valid or len(native.solids()) != 1:
        raise ValueError('Claw refinement must produce one valid sheet solid')
    result = native.moved(original.location)
    # Sheet part: it takes the ordered finish, not the recovered import's colour.
    result.label, result.color = original.label, ALUMINUM_5052_COLOR
    return result


# Angled finger and matching outer flange edge; mounting-hole axes stay fixed.


def _fixed_claw_core(original):
    t = scs.THICKNESS_MM
    ri = scs.EFFECTIVE_BEND_RADIUS_MM
    ro = ri+t
    root, tip = FIXED_BEND_ROOT_X_MM, FIXED_PINCH_TIP_X_MM
    half = FIXED_WEB_HALF_WIDTH_MM
    fold = FIXED_INNER_ROOT_Y_MM-ro
    flange_depth = CLAW_STRAIGHT_FLANGE_WIDTH_MM + FIXED_FLANGE_EXTRA_DEPTH_MM
    free = fold-flange_depth
    back = 0.0  # Deliberately oversized; the shared servo outline trims it exactly.
    def point(u,d,v):
        return (u,d,v)
    # Planar gripping web, with actual quarter-circle sheet bends.
    web = _box((tip,fold+ri,-half),(FIXED_FORMED_ROOT_U_MM,fold+ro,half))
    bends=[]
    for sign in (-1,1):
        def arcpoint(radius,theta):
            return (tip,fold+radius*math.cos(theta),
                    sign*(half+radius*math.sin(theta)))
        out=[arcpoint(ro,v)for v in (0,math.pi/4,math.pi/2)]
        inn=[arcpoint(ri,v)for v in (0,math.pi/4,math.pi/2)]
        wire=bd.Wire([bd.Edge.make_three_point_arc(*out),
                      bd.Edge.make_line(out[2],inn[2]),
                      bd.Edge.make_three_point_arc(*reversed(inn)),
                      bd.Edge.make_line(inn[0],out[0])])
        bends.append(bd.Solid.extrude(bd.Face(wire),(FIXED_FORMED_ROOT_U_MM-tip,0,0)))
    fingers=[_box((tip,free,z),(back,fold,z+t))for z in (-16.0-t,16.0)]
    bend_stock=as_single_shape(web.fuse(*bends)).clean()
    shape=as_single_shape(bend_stock.fuse(*fingers)).clean()
    shape=_tip(shape,tip,fold,half,lambda u,d,v:(u,d,v),
               root=FIXED_FORMED_ROOT_U_MM,tip_center=FIXED_PINCH_CENTER_Z_MM,
               bend_end=FIXED_BEND_TIP_X_MM,taper_slope=FIXED_TAPER_SLOPE,
               flange_depth_mm=flange_depth)
    # Open reliefs clear each bend end back past the tangent into the flange.
    # Measured from the flat bend center, BA/2 + inset is 2.9972 mm.
    shape=_cut(shape,_box((FIXED_FORMED_ROOT_U_MM,fold-RELIEF_FLAT_INSET_MM,-60),
                         (FIXED_HEADER_INNER_U_MM,100,60)))
    # End all remaining finger stock on the header's diagonal plane. The
    # header below supplies the root connection, avoiding a tiny outer ledge.
    shape=_cut(shape,_box((FIXED_HEADER_INNER_U_MM,-100,-60),(100,100,60)))
    # No cross-flange crosses the upper bend end. Continue its flat lip through
    # the relief width, in the finger's own frame, before applying the tilt.
    top_relief_fill=_box((FIXED_FORMED_ROOT_U_MM,fold-RELIEF_FLAT_INSET_MM,16.0),
                         (FIXED_HEADER_INNER_U_MM,fold,16.0+t))
    shape=as_single_shape(shape.fuse(top_relief_fill)).clean()
    # The finger, both true quarter bends, and constant-width flat strips
    # share one angled frame. Only the short root lands widen into the square
    # mounting headers; the headers themselves keep their original geometry.
    shape=shape.rotate(bd.Axis((root,FIXED_INNER_ROOT_Y_MM,0),(0,0,1)),
                       -FIXED_SLANT_ANGLE_DEG)
    bend_stock=bend_stock.rotate(bd.Axis((root,FIXED_INNER_ROOT_Y_MM,0),(0,0,1)),
                                 -FIXED_SLANT_ANGLE_DEG)
    mount=location_from_transform([
        0,0,1,FIXED_SERVO_ORIGIN_X_MM,
        -1,0,0,FIXED_SERVO_ORIGIN_Y_MM,
        0,-1,0,-16.0+SERVO.case_upper_y_mm,
        0,0,0,1])
    # A broad, straight cross-member joins each finger flange to the two case
    # screws. The case-facing edge uses the same profile as the link feet.
    header_corners=[]
    for side,z in (('upper',-16.0-t),('lower',16.0)):
        # Carry the header to the same diagonal normal as the bend end.
        # Screw holes, case-facing profile and outer mounting ends stay fixed.
        angle=math.radians(FIXED_SLANT_ANGLE_DEG)
        du,dv=FIXED_HEADER_INNER_U_MM-root,free-FIXED_INNER_ROOT_Y_MM
        inner_free=(root+du*math.cos(angle)+dv*math.sin(angle),
                    FIXED_INNER_ROOT_Y_MM-du*math.sin(angle)+dv*math.cos(angle))
        # Construct the shallow outside R1 in the planar outline. An
        # explicit tangent arc remains stable as the pinch angle decreases.
        radius=OUTLINE_RADIUS_MM
        setback=radius*math.tan(angle/2)
        departure=FIXED_SLANT_DEPARTURE_X_MM
        arc_start=(departure-setback*math.cos(angle),
                   FIXED_FREE_EDGE_Y_MM+setback*math.sin(angle))
        arc_end=(departure+setback,FIXED_FREE_EDGE_Y_MM)
        arc_mid=(departure+setback-radius*math.sin(angle/2),
                 FIXED_FREE_EDGE_Y_MM+radius-radius*math.cos(angle/2))
        top_y=FIXED_TOP_TAB_EDGE_Y_MM if z>0 else TAB_END_Y_MM
        if z>0:
            # Leave the finger's bend-end lip intact, then blend directly to
            # the servo recess. Do not grow a projection beyond that recess.
            header_top=(root-ro*math.sin(angle),FIXED_INNER_ROOT_Y_MM-ro*math.cos(angle))
        else:
            header_top=(inner_free[0]+(top_y-inner_free[1])*math.tan(angle),top_y)
        header_corners.append(bd.Vector(*header_top,z+t/2))
        def hp(p):return point(*p,z)
        # Straight beside the servo, then a short diagonal along the relief
        # floor. Keep the full root relief rather than closing a forming notch.
        relief_d=fold-RELIEF_FLAT_INSET_MM
        relief_corner=(root+(relief_d-FIXED_INNER_ROOT_Y_MM)*math.sin(angle),
                       FIXED_INNER_ROOT_Y_MM+(relief_d-FIXED_INNER_ROOT_Y_MM)*math.cos(angle))
        square_corner_y=(FIXED_INNER_ROOT_Y_MM
            +(relief_d-FIXED_INNER_ROOT_Y_MM)/math.cos(angle)
            -(header_top[0]-root)*math.tan(angle))
        tail=(arc_end,(back,FIXED_FREE_EDGE_Y_MM),(back,top_y),header_top,
              (header_top[0],square_corner_y),relief_corner,inner_free)
        if z>0:
            # Only the original near mounting tab remains on this side. The
            # short upper lip meets this diagonal root without a cross-flange.
            tail=(arc_end,(back,FIXED_FREE_EDGE_Y_MM),(back,top_y),
                  (FIXED_SERVO_ORIGIN_X_MM+CASE_LOWER_RECESS_DEPTH_MM,top_y),
                  header_top,inner_free)
        if abs(angle)<1e-9:
            # Restore full header depth. Only the approaching side is cut
            # diagonally below; the screw-supporting cross-member stays broad.
            header_wire=bd.Wire.make_polygon([hp(p)for p in (
                inner_free,(back,free),(back,top_y),header_top)],close=True)
        else:
            header_wire=bd.Wire([
                bd.Edge.make_line(hp(inner_free),hp(arc_start)),
                bd.Edge.make_three_point_arc(hp(arc_start),hp(arc_mid),hp(arc_end)),
                *[bd.Edge.make_line(hp(a),hp(b))for a,b in zip(tail,tail[1:])]])
        header=bd.Solid.extrude(bd.Face(header_wire),(0,0,t))
        shape=as_single_shape(shape.fuse(header)).clean()
        profile=case_flange(side,z_sign=-1,reversible=False,
                            thickness_mm=t,
                            outer_extension_mm=(FIXED_CASE_OUTER_EXTENSION_MM
                                                +FIXED_FLANGE_EXTRA_DEPTH_MM)).moved(mount)
        # Limit only the case-facing side of the stock. Its forward extension
        # is continuous with the straight finger and both mounting feet.
        back_x=FIXED_SERVO_ORIGIN_X_MM+CASE_BACK_EDGE_MM
        zone=_box((back_x,-100,z-.01),(1,100,z+t+.01))
        # Clip the flat mounting stock only. The small overshoot used for
        # Boolean robustness must not shave a 0.01 mm step into either bend.
        tool=as_single_shape(zone.cut(profile))
        tool=as_single_shape(tool.cut(bend_stock))
        shape=_cut(shape,tool)
    # Compact R1 corner on both header outlines after the root advances.
    # The top cross-flange is removed below; its far tab remains.
    x0=FIXED_HEADER_INNER_U_MM
    radius=OUTLINE_RADIUS_MM
    if radius<=0:
        raise ValueError('Header root must extend past the servo case end')
    edges=[e for e in shape.edges()if e.geom_type==bd.GeomType.LINE
           and abs(e.length-t)<1e-6
           and any((e.center()-corner).length<1e-6 for corner in header_corners)]
    # At the steeper symmetric angle the fitted case outline already removes
    # one corner. Round the remaining exposed corner, without inventing stock.
    if not 1<=len(edges)<=2:
        raise ValueError(f'Expected exposed outer header corners, got {len(edges)}')
    shape=shape.fillet(radius,edges).clean()
    top_tab_corner=[e for e in shape.edges()
        if e.geom_type==bd.GeomType.LINE and abs(e.length-t)<1e-6
        and abs(e.center().Y-FIXED_TOP_TAB_EDGE_Y_MM)<1e-6
        and abs(e.center().Z-(16.0+t/2))<1e-6
        and abs(e.center().X-(FIXED_SERVO_ORIGIN_X_MM+CASE_LOWER_RECESS_DEPTH_MM))<1e-6]
    if len(top_tab_corner)!=1:
        raise ValueError('Expected one exposed corner on the trimmed top tab')
    shape=shape.fillet(OUTLINE_RADIUS_MM,top_tab_corner).clean()
    # Enlarge only the two outer mounting-tab rounds. The shared case profile
    # still controls the mating edge, bores and inner recess corners.
    radius=MOUNT_OUTER_CORNER_R_MM
    for inner,z in ((CASE_UPPER_INNER_EDGE_MM,-16.0-t),
                    (CASE_LOWER_INNER_EDGE_MM,16.0)):
        x=FIXED_SERVO_ORIGIN_X_MM+inner
        corner=_box((x-radius,FIXED_FREE_EDGE_Y_MM,z),(x,FIXED_FREE_EDGE_Y_MM+radius,z+t))
        keep=bd.Solid.make_cylinder(radius,t,
            bd.Plane(origin=(x-radius,FIXED_FREE_EDGE_Y_MM+radius,z)))
        shape=_cut(shape,as_single_shape(corner.cut(keep)))
    return _finish(original,shape.clean())


def _moving_claw_core(original):
    shape = original.moved(original.location.inverse())
    # Rebuild the gripping web and quarter bends at the shared face length.
    # The imported horn cheeks retain their original mounting positions.
    ri,t=scs.EFFECTIVE_BEND_RADIUS_MM,scs.THICKNESS_MM
    ro=ri+t
    tip,root=MOVING_TIP_Z_MM,MOVING_BEND_ROOT_Z_MM
    fold,half,center=MOVING_REVISED_FOLD_X_MM,MOVING_WEB_HALF_WIDTH_MM,MOVING_WEB_CENTER_Y_MM
    web=_box((fold+ri,center-half,tip),(fold+ro,center+half,root))
    bends=[]
    for sign in (-1,1):
        def arcpoint(radius,theta):
            return (fold+radius*math.cos(theta),
                    center+sign*(half+radius*math.sin(theta)),tip)
        out=[arcpoint(ro,v)for v in (0,math.pi/4,math.pi/2)]
        inn=[arcpoint(ri,v)for v in (0,math.pi/4,math.pi/2)]
        wire=bd.Wire([bd.Edge.make_three_point_arc(*out),
                      bd.Edge.make_line(out[2],inn[2]),
                      bd.Edge.make_three_point_arc(*reversed(inn)),
                      bd.Edge.make_line(inn[0],out[0])])
        bends.append(bd.Solid.extrude(bd.Face(wire),(0,0,root-tip)))
    web=as_single_shape(web.fuse(*bends)).clean()
    cheeks = []
    closed_side = MOVING_HORN_RADIUS_MM+MOVING_FLANGE_EXTRA_DEPTH_MM
    for lo,hi in MOVING_HORN_BANDS_Y_MM:
        cheek = as_single_shape(shape.intersect(_box(
            (-50,lo,-100), (MOVING_FOLD_X_MM,hi,100))))
        # Reconstitute the closed cap before selecting the other three holes;
        # the recovered source already has the old forward fork cut into it.
        stock = bd.Solid.make_cylinder(MOVING_HORN_RADIUS_MM, hi-lo,
            bd.Plane(origin=(0,lo,MOVING_HORN_CENTER_Z_MM), z_dir=(0,1,0)))
        extra_stem = _box((-closed_side,lo,MOVING_TIP_Z_MM),
                          (0,hi,MOVING_HORN_CENTER_Z_MM))
        cheek = as_single_shape(cheek.fuse(stock,extra_stem)).clean()
        cheek = apply_narrow_horn_fork(cheek,
            center=(0,(lo+hi)/2,MOVING_HORN_CENTER_Z_MM),
            across=(1,0,0), outboard=(0,0,1), normal=(0,1,0),
            thickness_mm=hi-lo, half_width_mm=MOVING_HORN_RADIUS_MM,
            pattern=MOVING_WIDE_HORN_PATTERN,closed_side_mm=closed_side,
            bend_return_outboard_mm=MOVING_BEND_ROOT_Z_MM-MOVING_HORN_CENTER_Z_MM)
        # Carry the shallower stem to the existing circular cap, preserving
        # the complete three-hole horn connection.
        tool=_box((MOVING_REVISED_FOLD_X_MM,lo-.01,-100),(50,hi+.01,MOVING_HORN_CENTER_Z_MM))
        lug_radius=NARROW_HORN_FORK_PATTERN.tip_radius_mm(MOVING_HORN_RADIUS_MM)
        lug_center_z=MOVING_HORN_CENTER_Z_MM-(MOVING_HORN_RADIUS_MM
            + NARROW_HORN_FORK_PATTERN.opening_radius_mm)/2
        cap_keep=bd.Solid.make_cylinder(lug_radius,hi-lo+.04,
            bd.Plane(origin=(0,lo-.02,lug_center_z),z_dir=(0,1,0)))
        cheek=_cut(cheek,as_single_shape(tool.cut(cap_keep)))
        # Rebuild the flange under the extended bend: the imported cheek's
        # old nose chamfer otherwise clips the new supporting sheet to zero.
        support=_box((-closed_side,lo,MOVING_TIP_Z_MM),
            (MOVING_REVISED_FOLD_X_MM,hi,MOVING_BEND_ROOT_Z_MM))
        cheek=as_single_shape(cheek.fuse(support)).clean()
        cheeks.append(cheek)
    shape = as_single_shape(web.fuse(*cheeks)).clean()
    shape = _tip(shape, MOVING_TIP_Z_MM,MOVING_REVISED_FOLD_X_MM,
                 MOVING_WEB_HALF_WIDTH_MM,
                 lambda u,d,v:(d,v+MOVING_WEB_CENTER_Y_MM,u),root=MOVING_BEND_ROOT_Z_MM,
                 bend_end=MOVING_BEND_TIP_Z_MM,taper_slope=MOVING_TAPER_SLOPE,
                 nose_half_width=FIXED_WEB_HALF_WIDTH_MM,
                 nose_center=MOVING_NOSE_CENTER_V_MM,
                 tip_center=MOVING_NOSE_CENTER_V_MM,
                 flange_depth_mm=CLAW_STRAIGHT_FLANGE_WIDTH_MM+MOVING_FLANGE_EXTRA_DEPTH_MM)
    return _finish(original, shape)


# Clean attachment ends are drawn in the CLOSED frame. The gripping faces,
# quarter bends, and pinch solve above do not depend on their outlines.
CLAW_ROOT_OUTER_Y_MM = 2*GRIPPER_PINCH_CENTER_IN_CLAW_Y_MM-(GRIPPER_SHAFT_Y_MM+9.5)
STATIC_MOUNT_REAR_X_MM = GRIPPER_SHAFT_X_MM+4.0
STATIC_MOUNT_FRONT_X_MM = GRIPPER_SHAFT_X_MM-FIXED_CASE_BODY_HALF_WIDTH_MM
STATIC_MOUNT_BOTTOM_Y_MM = (2*GRIPPER_PINCH_CENTER_IN_CLAW_Y_MM
    -GRIPPER_SHAFT_Y_MM-FRAME_HORN_CAP_DIAMETER_MM/2)
# Both envelope tapers begin at the frontmost plane of the fitted servo case.
CLAW_ENVELOPE_DEPARTURE_X_MM = GRIPPER_SHAFT_X_MM-FIXED_CASE_BODY_HALF_WIDTH_MM
STATIC_BEAM_FORWARD_EXTENSION_MM = 0.0
STATIC_BEAM_END_CORNER_R_MM = 1.0


def _moving_to_common():
    """Native moving-finger coordinates into the static-claw/servo frame."""
    return location_from_transform([
        0,0,1,GRIPPER_SHAFT_X_MM-MOVING_HORN_CENTER_Z_MM,
        -1,0,0,GRIPPER_SHAFT_Y_MM,
        0,-1,0,-9.6,
        0,0,0,1])


def _gripping_flange_datums():
    a=math.radians(FIXED_SLANT_ANGLE_DEG)
    ro=scs.EFFECTIVE_BEND_RADIUS_MM+scs.THICKNESS_MM
    fold=FIXED_INNER_ROOT_Y_MM-ro
    def p(u,d):
        dx,dy=u-FIXED_BEND_ROOT_X_MM,d-FIXED_INNER_ROOT_Y_MM
        return (FIXED_BEND_ROOT_X_MM+dx*math.cos(a)+dy*math.sin(a),
                FIXED_INNER_ROOT_Y_MM-dx*math.sin(a)+dy*math.cos(a))
    root=p(FIXED_FORMED_ROOT_U_MM,fold)
    # Add the round's allowance outside the minimum forming land.
    return (p(FIXED_BEND_TIP_X_MM,fold-TIP_TAPER_FLAT_LAND_MM-CLAW_NOSE_CORNER_R_MM),
            (root[0],CLAW_ROOT_OUTER_Y_MM),root,
            p(FIXED_BEND_TIP_X_MM,fold))


def _round_profile(solid,points,radius,z):
    corners=[bd.Vector(x,y,z+scs.THICKNESS_MM/2)for x,y in points]
    edges=[e for e in solid.edges()if e.geom_type==bd.GeomType.LINE
           and abs(e.length-scs.THICKNESS_MM)<1e-6
           and any((e.center()-q).length<1e-6 for q in corners)]
    if len(edges)!=len(points):raise ValueError('Attachment outline corner missing')
    return solid.fillet(radius,edges).clean()


def _static_beam_front_x():
    # Match the upper return to the fitted case envelope.
    return STATIC_MOUNT_FRONT_X_MM-STATIC_BEAM_FORWARD_EXTENSION_MM


def _closed_flange_profile(z, *, moving=False):
    """Compact case ear or standard circular fork, joined to the same finger."""
    nose,outside,root,nose_fold=_gripping_flange_datums()
    t=scs.THICKNESS_MM
    if moving:
        def reflect(p):return(p[0],2*GRIPPER_PINCH_CENTER_IN_CLAW_Y_MM-p[1])
        nose,outside,root,nose_fold=map(reflect,(nose,outside,root,nose_fold))
        cx,cy=GRIPPER_SHAFT_X_MM,GRIPPER_SHAFT_Y_MM
        radius=FRAME_HORN_CAP_DIAMETER_MM/2
        pattern=FRAME_HORN_FORK_PATTERN
        # Continue the long taper to a horizontal tangent at the cap's top.
        top_y=cy+radius
        knee=(CLAW_ENVELOPE_DEPARTURE_X_MM,top_y)
        # The inner edge runs directly from the bend root to the forward
        # fork-tip semicircle. Solve its lower tangent, avoiding a neck notch.
        tip_r=pattern.tip_radius_mm(radius)
        tip_c=(cx-pattern.opening_radius_mm-tip_r,cy-pattern.straight_mm)
        vx,vy=root[0]-tip_c[0],root[1]-tip_c[1]
        dd=vx*vx+vy*vy
        k=tip_r*math.sqrt(dd-tip_r*tip_r)/dd
        base=(tip_c[0]+tip_r*tip_r*vx/dd,tip_c[1]+tip_r*tip_r*vy/dd)
        tangent=min(((base[0]-k*vy,base[1]+k*vx),
                     (base[0]+k*vy,base[1]-k*vx)),key=lambda p:p[1])
        # Join through the lug center so the bridge remains inside its arc.
        # A direct diagonal from the shaft center would leave a flat at the tip.
        bridge=_prism([(x,y,z)for x,y in(nose,knee,(cx,top_y),(cx,cy),tip_c,tangent,root,nose_fold)],(0,0,t))
        bridge=_round_profile(bridge,(knee,),MOUNT_OUTER_CORNER_R_MM,z)
        bridge=_round_profile(bridge,(nose,),CLAW_NOSE_CORNER_R_MM,z)
        cap=bd.Solid.make_cylinder(radius,t,bd.Plane(origin=(cx,cy,z)))
        cap=apply_horn_fork(cap,center=(cx,cy,z+t/2),
            across=(1,0,0),outboard=(0,-1,0),normal=(0,0,1),
            thickness_mm=t,half_width_mm=radius,pattern=pattern)
        solid=as_single_shape(bridge.fuse(cap,tol=1e-7)).clean()
        # Restore the shared bores and center opening after joining the bridge.
        r=pattern.opening_radius_mm
        cuts=[bd.Solid.make_cylinder(r,t+.02,bd.Plane(origin=(cx,cy,z-.01))),
              _box((cx-r,cy-100,z-.01),(cx+r,cy,z+t+.01))]
        cuts.extend(bd.Solid.make_cylinder(hr,t+.02,
            bd.Plane(origin=(cx+a,cy-b,z-.01)))for a,b,hr in pattern.holes)
        return as_single_shape(solid.cut(*cuts)).clean()
    # Mirror the moving finger's long taper and flat outer mounting edge.
    # The fixed interface terminates as a rounded rectangle around its M2 tab.
    knee=(CLAW_ENVELOPE_DEPARTURE_X_MM,STATIC_MOUNT_BOTTOM_Y_MM)
    inner_y=FIXED_TOP_TAB_EDGE_Y_MM if z>0 else 12.3
    # Match the rear rectangular envelope on both sides of the static claw.
    rear_x=STATIC_MOUNT_REAR_X_MM
    rear_low=(rear_x,STATIC_MOUNT_BOTTOM_Y_MM)
    rear_high=(rear_x,inner_y)
    front_x=STATIC_MOUNT_FRONT_X_MM if z>0 else _static_beam_front_x()
    front_high=(front_x,inner_y)
    # Continue the gripping fold's straight line to the case tab before
    # turning across to the mounting edge, removing the triangular shoulder.
    front_return=(front_x,
        root[1]-(front_x-root[0])*math.tan(math.radians(FIXED_SLANT_ANGLE_DEG)))
    points=(nose,knee,rear_low,rear_high,front_high,front_return,root,nose_fold)
    solid=_prism([(x,y,z)for x,y in points],(0,0,t))
    solid=_round_profile(solid,(knee,),MOUNT_OUTER_CORNER_R_MM,z)
    solid=_round_profile(solid,(nose,),CLAW_NOSE_CORNER_R_MM,z)
    if z>0:
        solid=_round_profile(solid,(rear_low,rear_high),3.0,z)
        solid=_round_profile(solid,(front_high,),1.0,z)
    else:
        solid=_round_profile(solid,(rear_low,rear_high),3.0,z)
    return solid


def fixed_claw(original):
    core=_fixed_claw_core(original)
    native=core.moved(core.location.inverse())
    # Replace the old cheeks rather than unioning outlines: leftover header
    # triangles otherwise protrude into the new square mounting step.
    axis=bd.Axis((FIXED_BEND_ROOT_X_MM,FIXED_INNER_ROOT_Y_MM,0),(0,0,1))
    native=native.rotate(axis,FIXED_SLANT_ANGLE_DEG)
    fold=FIXED_INNER_ROOT_Y_MM-scs.EFFECTIVE_BEND_RADIUS_MM-scs.THICKNESS_MM
    for z in(-16-scs.THICKNESS_MM,16):
        native=_cut(native,_box((-200,-100,z),(100,fold,z+scs.THICKNESS_MM)))
        native=_cut(native,_box((FIXED_FORMED_ROOT_U_MM,-100,z),(100,100,z+scs.THICKNESS_MM)))
    native=native.rotate(axis,-FIXED_SLANT_ANGLE_DEG)
    profiles=[_closed_flange_profile(z)for z in(-16-scs.THICKNESS_MM,16)]
    native=as_single_shape(native.fuse(*profiles)).clean()
    # Keep the underside's two-hole case beam independent of the finger's
    # inclined root plane. Its front edge clears the actual bend termination.
    mount=location_from_transform([
        0,0,1,FIXED_SERVO_ORIGIN_X_MM,
        -1,0,0,FIXED_SERVO_ORIGIN_Y_MM,
        0,-1,0,-16.0+SERVO.case_upper_y_mm,
        0,0,0,1])
    beam=case_flange('upper',z_sign=-1,reversible=False,
        thickness_mm=scs.THICKNESS_MM,
        outer_extension_mm=FIXED_CASE_OUTER_EXTENSION_MM).moved(mount)
    # Remove the former rectangular tail below the compact ear. The overlap
    # up to the rib-clearance edge joins the beam without a dangling tongue.
    beam=as_single_shape(beam.intersect(_box(
        (_static_beam_front_x(),STATIC_MOUNT_BOTTOM_Y_MM,-30),(10,100,0))))
    native=as_single_shape(native.fuse(beam)).clean()
    native=_round_profile(native,((_static_beam_front_x(),TAB_END_Y_MM),),
        STATIC_BEAM_END_CORNER_R_MM,-16-scs.THICKNESS_MM)
    for y in FIXED_UNDERSIDE_HOLES_Y_MM:
        native=_cut(native,bd.Solid.make_cylinder(CASE_HOLE_RADIUS_MM,scs.THICKNESS_MM+.02,
            bd.Plane(origin=(FIXED_CASE_HOLE_X_MM,y,-16-scs.THICKNESS_MM-.01))))
    top_hole_y=FIXED_SERVO_ORIGIN_Y_MM-max(SERVO.case_lower_hole_x_mm)
    native=_cut(native,bd.Solid.make_cylinder(CASE_HOLE_RADIUS_MM,scs.THICKNESS_MM+.02,
        bd.Plane(origin=(FIXED_CASE_HOLE_X_MM,top_hole_y,16-.01))))
    return _finish(original,native)


def moving_claw(original):
    core=_moving_claw_core(original)
    native=core.moved(core.location.inverse())
    # Replace the old circular cheeks, retaining the gripping web and the
    # exact quarter bends. Otherwise the old cap can protrude beyond the
    # clearance-controlled rectangle's new corner rounds.
    for lo,hi in MOVING_HORN_BANDS_Y_MM:
        native=_cut(native,_box((-100,lo,-200),(MOVING_REVISED_FOLD_X_MM,hi,100)))
        native=_cut(native,_box((-100,lo,MOVING_BEND_ROOT_Z_MM),(100,hi,100)))
    loc=_moving_to_common()
    axis=bd.Axis((GRIPPER_SHAFT_X_MM,GRIPPER_SHAFT_Y_MM,0),(0,0,1))
    closed=native.moved(loc).rotate(axis,GRIPPER_CLOSE_ANGLE_DEG)
    zs=tuple(-9.6-hi for lo,hi in MOVING_HORN_BANDS_Y_MM)
    closed=as_single_shape(closed.fuse(*[_closed_flange_profile(z,moving=True)for z in zs])).clean()
    native=closed.rotate(axis,-GRIPPER_CLOSE_ANGLE_DEG).moved(loc.inverse())
    # Heal coincident bend/profile seams after the closed-frame boolean.
    # Kernel validation can otherwise depend on the imported STEP tolerances.
    if not native.is_valid:
        native=native.fix()
    return _finish(original,native)
