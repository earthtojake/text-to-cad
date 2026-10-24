"""Top half of the split shoulder-yaw bracket: servo 1's UPPER horn to both sides of servo 2.

Rev3 datums and helpers the rev4 stages still read; the standalone part model is in git history.

Three panels, three folds:

    arm     bolts to servo 1's upper horn on the same cap and bolt circle the single-piece yoke
            uses, with the yoke's TOP-arm profile: the straight taper -- a V, widest at the fold,
            narrowing on a line tangent to the cap. (The bottom bracket gets the other one, the
            indent profile, because that is what the yoke's bottom arm has.)
    fold 1  UP, into a wall that starts at the arm's own width and widens to the cheek fold lines
    fold 2  OUT to both sides, into two cheeks on the yoke's +/-16.000 seating planes

The cheeks take servo 2's four NEAR-side holes, two each, on the yoke's own #o1.1.f28 / #o1.1.f32
pattern. Servo 2 is lifted so its front face clears this arm -- see SERVO2_LIFT_Y_MM.

Every fold carries the real SendCutSend radii (0.889 inside, 2.489 outside), so the corners are bends
rather than butt joints.
"""

from __future__ import annotations

from lib import servo_fit as fit
from lib import horn_cap

from lib.diag import say


from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
REPO_ROOT = SRC_DIR.parent
# 2mm tree, and this file is a level deeper again -- its parent IS the 2mm root, which is what
# wants to be on sys.path. Unlike the files directly in 2mm/, this one needed no change.
VENDOR_DIR = REPO_ROOT / "STEP" / "imported"

import build123d

from lib import shoulder_yaw_bracket_common as sb  # noqa: E402

PART_NAME = "shoulder_yaw_top_bracket.step"  # pinned: the label these parts shipped with, when the source was shoulder_yaw_top_bracket.step.py
DISPLAY_NAME = "Shoulder Yaw Top Bracket"

# The second arm flange, mirrored off the first so the part grips BOTH of a servo's horns instead of
# one. The plane is not chosen for looks: the arm's contact face is y 10.800 against one horn, and
# the opposite horn's own contact face lands at y 47.250, so the plane halfway between them is
#
#     0.5 * (10.800 + 47.250) = 29.025
#
# which is the servo's horn-to-horn midplane expressed in this part's frame -- the same -9.025 that
# WRIST_BRACKET_HORN_MIDPLANE_Y_MM names in the servo's own. Mirroring here therefore lands the new
# flange on the opposite horn by construction rather than by a fitted offset.
#
# It is applied to the arm + wall + fold-1 stage, BEFORE the cheeks: the mirrored wall spans
# 16.016..48.850 against the original's 9.200..42.034, so the two overlap and fuse into one
# continuous plate carrying an arm at each end. Mirroring after the cheeks would duplicate those too,
# and the part only wants the two it has.
# DERIVED, not 29.025. The arm is mirrored about this plane, and what has to land on the servo's far
# horn disc is the mirrored arm's INNER face -- which sits one sheet thickness inboard of its outer.
# Hardcoding the plane worked only at 1.6002: at 2.032 the far arm's inner face slides 0.432 off the
# disc, because the arm got thicker while the plane stayed put.
#
#   P = (near inner face + far inner face + sheet) / 2
#   1.6002 -> (9.2000 + 47.2498 + 1.6002)/2 = 29.0250   (the old literal, recovered)
#   2.0320 -> (9.2000 + 47.2498 + 2.0320)/2 = 29.2409
ARM_FAR_HORN_FACE_Y_MM = sb.TOP_ARM_OUTER_Y_MM + fit.SERVO.horn_span_mm + 2 * fit.HORN_MOUNT_GAP_MM
ARM_MIRROR_PLANE_Y_MM = (
    sb.TOP_ARM_INNER_Y_MM + ARM_FAR_HORN_FACE_Y_MM + sb.SHEET_THICKNESS_MM
) / 2.0

# Rounding on the cheek tips. The radius is NOT picked for looks -- it is the one the elbow-roll link
# plates already use (#o1.22.e22 measures r 1.000), so the two parts that sit next to each other on
# the wrist read as one family.
CHEEK_TIP_FILLET_RADIUS_MM = 1.0

# The six corners, by position rather than by index, because an index moves the moment the outline
# does. Each is a sheet-thickness edge running along z at a cheek's outermost x -- the corners of the
# tab itself. Each cheek has FOUR such corners; the fourth, at y 40.483, is deliberately left square:
# it is the one that runs into the angled top edge back to the wall at y 42.034, and rounding it
# would eat that transition. The two cheeks are not mirror images -- their tips sit at x -55.347 and
# -54.883 and their tabs start at different y -- which is inherited from servo 2's own case, whose
# two faces put their outboard hole at different x.
# The z here is the CHEEK'S MID-PLANE, which moves with sheet thickness -- inner face 16.0000 plus
# half a sheet. Hardcoding 16.8001 pinned it to 1.6002 and the search came back empty at 2.0320,
# which is what the "outline moved" error above is for. x and y are genuine outline coordinates and
# do not scale, so only z is derived.
_CHEEK_MID_Z_MM = sb.CHEEK_INNER_Z_MM + 0.5 * sb.SHEET_THICKNESS_MM
CHEEK_TIP_FILLET_XYZ_MM: tuple[tuple[float, float, float], ...] = tuple(
    (x, y, sign * _CHEEK_MID_Z_MM)
    for x, y, sign in (
        (-55.3466, 12.5162, 1.0),
        (-55.3466, 17.6502, 1.0),
        (-55.3466, 36.9002, 1.0),
        (-54.8826, 16.2662, -1.0),
        (-54.8826, 21.4002, -1.0),
        (-54.8826, 36.9002, -1.0),
    )
)


def _round_cheek_tips(body: build123d.Shape) -> build123d.Shape:
    """Fillet the cheek-tip tab corners, found BY SHAPE rather than by coordinate.

    The original matched six hardcoded (x, y, z) centres. Every one of those coordinates moves with
    sheet thickness -- the z is the cheek's mid-plane, and the x and y shift with the tabs -- so at
    2.0320 the list matched nothing and the build failed telling us to "re-read the corners from the
    model". This does that: a tab corner is a z-parallel edge exactly one sheet long, standing at the
    outermost x of its own cheek plane.

    The FOURTH corner on each cheek, the high-y one, is deliberately left square -- the r11 sweep runs
    into it and a fillet would eat that transition -- so the highest-y edge per cheek is dropped.
    """
    sheet = sb.SHEET_THICKNESS_MM
    picked = []
    for z_sign in (1.0, -1.0):
        mid = z_sign * (sb.CHEEK_INNER_Z_MM + 0.5 * sheet)
        edges = [
            e for e in body.edges()
            if e.geom_type == build123d.GeomType.LINE
            and e.bounding_box().size.X < 1e-6 and e.bounding_box().size.Y < 1e-6
            and abs(e.length - sheet) < 1e-3
            and abs(e.center().Z - mid) < 1e-3
        ]
        if not edges:
            raise RuntimeError(f"{PART_NAME}: no cheek-tip corners found at z {mid:.4f}")
        tip_x = min(e.center().X for e in edges)
        tips = [e for e in edges if abs(e.center().X - tip_x) < 0.5]
        tips.sort(key=lambda e: e.center().Y)
        picked.extend(tips[:-1] if len(tips) > 1 else tips)
    if not picked:
        raise RuntimeError(f"{PART_NAME}: found no cheek-tip corners to break")
    say(f"{PART_NAME}: {len(picked)} cheek-tip corners broken r{CHEEK_TIP_FILLET_RADIUS_MM}")
    return sb.as_single_shape(build123d.fillet(picked, CHEEK_TIP_FILLET_RADIUS_MM))


def build_bracket() -> build123d.Shape:
    # The wall's x is DERIVED, not inherited. It used to be the yoke's own spine radius off the horn
    # axis, which answers to nothing on this part, and left the arm 2.210 mm longer than it needs to
    # be while the cheeks' bolts sat 1.064 mm inside the half-die minimum to their own bend.
    wall_in = sb.wall_inner_x()
    wall_out = wall_in - sb.SHEET_THICKNESS_MM
    # The near-side four: two on each cheek, spanning both of servo 2's case faces.
    holes = sb.top_bracket_holes()
    band_lo, band_hi = sb.cheek_y_band(holes)
    # The arm runs through to the wall's OUTER face, so the fold's outside surface is one
    # continuous face rather than two coplanar faces meeting at a seam the fillet cannot cross.
    fold_half_z = sb.arm_fold_half_z(wall_out, straight_taper=True)

    arm = sb.tapered_arm(sb.TOP_ARM_INNER_Y_MM, sb.TOP_ARM_OUTER_Y_MM, wall_out,
                         straight_taper=True)
    wall = sb.tapered_wall(
        x_out=wall_out, x_in=wall_in,
        y_root=sb.TOP_ARM_INNER_Y_MM, half_z_root=fold_half_z,
        band_y_lo=band_lo, band_y_hi=band_hi,
    )
    body = sb.as_single_shape(arm.fuse(wall))

    # Fold 1, while the wall is still a plain plate: the arm folds off the wall's LOWER end, so the
    # inside of the bend is (wall inner face, arm outer face) -- the mirror of the single-piece
    # yoke's top arm, which folds off the top of its spine instead.
    body = sb.bend_z_corner(body, wall_in, sb.TOP_ARM_OUTER_Y_MM,
                            sb.BEND_INNER_RADIUS_MM)
    body = sb.bend_z_corner(body, wall_out, sb.TOP_ARM_INNER_Y_MM,
                            sb.BEND_OUTER_RADIUS_MM)

    # The mirrored arm, folding off the far end of the same wall -- see ARM_MIRROR_PLANE_Y_MM.
    body = sb.as_single_shape(body.fuse(
        body.mirror(build123d.Plane(origin=(0, ARM_MIRROR_PLANE_Y_MM, 0), z_dir=(0, 1, 0)))
    ))

    # Fold 2: out to both sides, each cheek carrying that side's two holes. The cheek's flat starts
    # at the bend axis, and the bend itself is an explicit quarter annulus between them.
    cheek_root_x = sb.cheek_bend_axis_x(wall_in, runs_neg_x=True)
    for z_sign in (-1.0, 1.0):
        side = tuple(h for h in holes if (h[2] > 0) == (z_sign > 0))
        s_lo, s_hi = sb.cheek_y_band(side)
        body = sb.as_single_shape(body.fuse(
            sb.patterned_cheek(root_x=cheek_root_x, material_sign=1.0,
                               holes=side, z_sign=z_sign)
        ))
        body = sb.as_single_shape(body.fuse(
            sb.cheek_bend(wall_face_x=wall_in, runs_neg_x=True,
                          z_sign=z_sign, y_lo=s_lo, y_hi=s_hi)
        ))

    body = _round_cheek_tips(body)

    tan_x = wall_in + sb.BEND_INNER_RADIUS_MM
    nearest_bolt_x = min(x for x, _z in sb.HORN_BOLTS_XZ_MM)
    cheek_tip_x = holes[0][0] - sb.CHEEK_TIP_MARGIN_MM
    sb.check_forming_rules(PART_NAME, (
        ("arm flange", sb.ARM_TIP_X_MM - tan_x, sb.MIN_FLANGE_FORMED_MM),
        ("horn bolt to arm bend",
         (nearest_bolt_x - sb.M3_CLEARANCE_RADIUS_MM) - tan_x, sb.MIN_HOLE_TO_BEND_MM),
        ("cheek flange", abs(cheek_tip_x - cheek_root_x), sb.MIN_FLANGE_FORMED_MM),
        ("cheek bolt to cheek bend",
         abs(holes[0][0] - cheek_root_x) - sb.M2_CLEARANCE_RADIUS_MM, sb.MIN_HOLE_TO_BEND_MM),
        ("wall flange",
         band_hi - (sb.TOP_ARM_OUTER_Y_MM + sb.BEND_INNER_RADIUS_MM), sb.MIN_FLANGE_FORMED_MM),
        ("wall to servo 1 case sweep",
         sb.HORN_AXIS_X_MM - wall_in, sb.CASE_WALL_TOUCH_RADIUS_MM),
    ))

    solids = body.solids()
    bracket = solids[0] if len(solids) == 1 else body
    bracket.label = PART_NAME
    bracket.color = sb.BRACKET_COLOR

    bb = bracket.bounding_box()
    say(
        f"{PART_NAME}: arm y {sb.TOP_ARM_INNER_Y_MM:.3f}..{sb.TOP_ARM_OUTER_Y_MM:.3f} "
        f"folding at half-z {fold_half_z:.3f}; wall x {wall_out:.3f}.."
        f"{wall_in:.3f} widening to the cheek band y {band_lo:.3f}..{band_hi:.3f}; "
        f"bends r{sb.BEND_INNER_RADIUS_MM:.3f}/{sb.BEND_OUTER_RADIUS_MM:.3f}; "
        f"solids {len(solids)}; envelope X={bb.size.X:.3f} Y={bb.size.Y:.3f} Z={bb.size.Z:.3f}"
    )
    return bracket


def finish_horn_caps(shape):
    return horn_cap.apply_y_normal_caps(
        shape, center_xz=(sb.HORN_AXIS_X_MM, sb.HORN_AXIS_Z_MM),
        bands=((sb.TOP_ARM_INNER_Y_MM, sb.TOP_ARM_OUTER_Y_MM),
               (2*ARM_MIRROR_PLANE_Y_MM-sb.TOP_ARM_OUTER_Y_MM,
                2*ARM_MIRROR_PLANE_Y_MM-sb.TOP_ARM_INNER_Y_MM)),
        half_width_mm=sb.ARM_CAP_RADIUS_MM,
    )


def build_step() -> build123d.Shape:
    return finish_horn_caps(build_bracket())
