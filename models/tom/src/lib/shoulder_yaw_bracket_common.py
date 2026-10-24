"""Shared datums for the two-piece shoulder-yaw bracket.

The single-piece shoulder_yaw_yoke is being split in two: a TOP bracket off servo 1's upper horn
and a BOTTOM bracket off its lower horn, each folding round to grab servo 2's case on both sides.
Two simpler parts instead of one part that has to be everything at once.

Everything here is read from shoulder_yaw_yoke rather than restated, so the two pieces stay on the
datums the single-piece version was validated against: the horn axis and bolt circle, the sheet
gauge and bend radius, the spine and cheek planes, and servo 2's own mount holes.
"""

from __future__ import annotations

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
# 2mm tree, and this file is a level deeper again -- its parent IS the 2mm root, which is what
# wants to be on sys.path. Unlike the files directly in 2mm/, this one needed no change.
REPO_ROOT = SRC_DIR.parent

import build123d

from lib.booleans import as_single_shape  # noqa: E402


# The twin-bolt yoke's sheet datums (a sibling model file, imported for its constants; importing
# binds its model, never builds).
import shoulder_yaw_yoke_twin_bolt as yoke  # noqa: E402

SHEET_THICKNESS_MM = yoke.SHEET_THICKNESS_MM
# The two radii a real fold has: the inside of the bend and the outside, one sheet thickness apart.
# Modelling folds as sharp butt joints is what made every corner on these brackets a square step.
BEND_INNER_RADIUS_MM = yoke.BEND_INNER_RADIUS_MM
BEND_OUTER_RADIUS_MM = yoke.BEND_OUTER_RADIUS_MM
ARM_WEB_HALF_Z_MM = yoke.ARM_WEB_HALF_Z_MM

# Servo 1's horn: both brackets bolt to it with the same 4-bolt circle plus the centre clearance.
HORN_AXIS_X_MM = yoke.HORN_AXIS_X_MM
HORN_AXIS_Z_MM = yoke.HORN_AXIS_Z_MM
ARM_CAP_RADIUS_MM = yoke.ARM_CAP_RADIUS_MM
M3_CLEARANCE_RADIUS_MM = yoke.M3_CLEARANCE_RADIUS_MM
M2_CLEARANCE_RADIUS_MM = yoke.M2_CLEARANCE_RADIUS_MM
# The horn's own hub boss, not an M3 bolt: it stands proud of the horn face, so the arm needs a
# 6.496 bore at the axis. Clearing only M3 there buries the boss 0.800 mm into the arm.
HORN_CENTER_CLEARANCE_RADIUS_MM = yoke.HORN_CENTER_CLEARANCE_RADIUS_MM
HORN_BOLTS_XZ_MM = tuple(yoke._horn_bolt_centers_xz())

TOP_ARM_INNER_Y_MM = yoke.TOP_ARM_INNER_Y_MM
TOP_ARM_OUTER_Y_MM = yoke.TOP_ARM_OUTER_Y_MM
BOTTOM_ARM_INNER_Y_MM = yoke.BOTTOM_ARM_INNER_Y_MM
BOTTOM_ARM_OUTER_Y_MM = yoke.BOTTOM_ARM_OUTER_Y_MM

SPINE_OUTER_X_MM = yoke.SPINE_OUTER_X_MM
SPINE_INNER_X_MM = yoke.SPINE_INNER_X_MM
CHEEK_INNER_Z_MM = yoke.CHEEK_INNER_Z_POS_MM
CHEEK_OUTER_Z_MM = CHEEK_INNER_Z_MM + SHEET_THICKNESS_MM
CHEEK_TIP_X_MM = yoke.CHEEK_TIP_X_MM

# SendCutSend forming rules, on the yoke's own conventions: flange length is measured from the bend
# TANGENT to the free edge, and hole-to-bend from the hole's EDGE to that tangent -- not centres.
MIN_FLANGE_FORMED_MM = yoke.SENDCUTSEND_MIN_FLANGE_FORMED_MM
MIN_HOLE_TO_BEND_MM = yoke.MIN_HOLE_TO_BEND_MM
ARM_TIP_X_MM = yoke.ARM_TIP_X_MM
CASE_WALL_TOUCH_RADIUS_MM = yoke.CASE_WALL_TOUCH_RADIUS_MM

# The cheek PATTERN, read across from the yoke rather than re-derived. These are what the split
# brackets lost when their cheeks became plain rectangles: the tip margin that sets hole-to-edge, the
# -z side's relief for servo 2's case rib, the notch between the two hole ears that clears the tip
# bosses, and the swept y-max tip corner.
CHEEK_TIP_MARGIN_MM = yoke.CHEEK_TIP_MARGIN_MM
CHEEK_NOTCH_DEPTH_MM = yoke.CHEEK_NOTCH_DEPTH_MM
CHEEK_EAR_HALF_WIDTH_MM = yoke.CHEEK_EAR_HALF_WIDTH_MM
CHEEK_SWEEP_RADIUS_MM = yoke.CHEEK_SWEEP_RADIUS_MM
CHEEK_SWEEP_LEG_X_MM = yoke.CHEEK_SWEEP_LEG_X_MM
CHEEK_SWEEP_LEG_Y_MM = yoke.CHEEK_SWEEP_LEG_Y_MM
SERVO2_TIP_RIB_RELIEF_MM = yoke.SERVO2_TIP_RIB_RELIEF_MM
TAB_EDGE_MARGIN_MM = yoke.TAB_EDGE_MARGIN_MM

# Servo 2 moves UP so its front face clears the top bracket's arm. Measured in the joint assembly:
# its #o1.5.3.f30 sat 18.110 mm below the arm's outer face (#o1.4.f39), so that is the minimum.
# Rounded up to 20.000 for a little daylight; the exact value is not fixed yet.
SERVO2_LIFT_Y_MM = 20.0

# Flat run the wall keeps at its fold before it starts widening, so the outer bend fillet has
# somewhere square to die into. One outer bend radius, rounded up.
WALL_TAPER_ROOT_RUN_MM = 2.0

# Servo 2's eight case mount holes, in ITS OWN local frame, resolved off the import rather than
# restated. Four per case face; the two faces are not mirror images (case-bottom's outboard hole is
# at x +7.250, case-top's at +3.500), which is why the pattern is written out per face.
SERVO2_CASE_HOLES_LOCAL_MM: tuple[tuple[float, float, float], ...] = tuple(
    (lx, ly, lz)
    for ly, lxs in ((-25.6, (-17.2, 7.25)), (6.4, (-17.2, 3.5)))
    for lx in lxs
    for lz in (-10.25, 10.25)
)


def _servo2_hole_in_yoke(local: tuple[float, float, float]) -> tuple[float, float, float]:
    """One servo-2 hole in the yoke frame, through servo 2's own placement plus the lift.

    servo2_in_yoke maps local x -> yoke -y, local y -> yoke -z, local z -> yoke +x.
    """
    lx, ly, lz = local
    return (
        lz + yoke.SERVO2_PLACEMENT_TX_MM,
        -lx + yoke.SERVO2_PLACEMENT_TY_MM + SERVO2_LIFT_Y_MM,
        -ly + yoke.SERVO2_PLACEMENT_TZ_MM,
    )


# The split is by SIDE, not by height. Each bracket takes the four holes on one z side of the servo
# -- two on each of its case faces, so two per cheek -- and the two sides sit at different yoke x:
# the near side at -52.813 for the top bracket, the far side at -73.313 for the bottom, which is
# what makes the bottom bracket reach round servo 2 at all.
NEAR_SIDE_LOCAL_Z_MM = 10.25


def holes_on_side(local_z: float) -> tuple[tuple[float, float, float], ...]:
    return tuple(
        _servo2_hole_in_yoke(h)
        for h in SERVO2_CASE_HOLES_LOCAL_MM
        if abs(h[2] - local_z) < 1e-6
    )


def top_bracket_holes() -> tuple[tuple[float, float, float], ...]:
    """#o1.6.2.e344/e345 + #o1.6.1.e368/e369 -- the near-side four."""
    return holes_on_side(NEAR_SIDE_LOCAL_Z_MM)


# Primitives come from link_geometry rather than being hand-rolled: build123d's make_box takes a
# Plane, not a Location, and getting that wrong fails deep inside OCCT rather than at the call.
from lib import link_geometry as _lg  # noqa: E402

BRACKET_COLOR = _lg.BRACKET_COLOR


def box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> build123d.Shape:
    return _lg.make_box(
        x_min=min(x0, x1), x_max=max(x0, x1),
        y_min=min(y0, y1), y_max=max(y0, y1),
        z_min=min(z0, z1), z_max=max(z0, z1),
    )


def y_cylinder(x: float, z: float, radius: float, y0: float, y1: float) -> build123d.Shape:
    return _lg.make_y_cylinder(x=x, z=z, radius=radius, y_min=min(y0, y1), y_max=max(y0, y1))


def z_cylinder(x: float, y: float, radius: float, z0: float, z1: float) -> build123d.Shape:
    return _lg.make_z_cylinder(x=x, y=y, radius=radius, z_min=min(z0, z1), z_max=max(z0, z1))


def patterned_cheek(
    *,
    root_x: float,
    material_sign: float,
    holes: tuple[tuple[float, float, float], ...],
    z_sign: float,
) -> build123d.Shape:
    """One cheek carrying the yoke's own two-hole pattern off #o1.1.f28 / #o1.1.f32.

    `root_x` is the fold end; `material_sign` is the direction from tip to root (+1 for the top
    bracket, whose cheeks reach out in -x and fold back at high x; -1 for the bottom bracket, whose
    cheeks come from the far side and fold at low x). The two holes are this cheek's own -- the pair
    the original yoke put on the matching case face -- so the ears, notch and sweep land where they
    did there.
    """
    if len(holes) != 2:
        raise RuntimeError(f"a cheek takes exactly 2 holes, got {len(holes)}")

    z0 = z_sign * CHEEK_INNER_Z_MM
    z1 = z_sign * CHEEK_OUTER_Z_MM
    zlo, zhi = min(z0, z1), max(z0, z1)

    hole_x = holes[0][0]
    ys = sorted(h[1] for h in holes)
    # Tip margin runs AWAY from the root; the -z side is pulled back toward it for the case rib.
    tip_x = hole_x - material_sign * CHEEK_TIP_MARGIN_MM
    if z_sign < 0.0:
        tip_x += material_sign * SERVO2_TIP_RIB_RELIEF_MM

    y_min = ys[0] - (M2_CLEARANCE_RADIUS_MM + TAB_EDGE_MARGIN_MM)
    y_max = ys[1] + (M2_CLEARANCE_RADIUS_MM + TAB_EDGE_MARGIN_MM)

    plate = box(tip_x, root_x, y_min, y_max, zlo, zhi)

    # Notch the free tip edge back between the two hole ears -- the servo's tip bosses live here.
    n_lo = ys[0] + CHEEK_EAR_HALF_WIDTH_MM
    n_hi = ys[1] - CHEEK_EAR_HALF_WIDTH_MM
    if n_hi > n_lo:
        plate = plate.cut(
            box(tip_x - material_sign * 1.0, tip_x + material_sign * CHEEK_NOTCH_DEPTH_MM,
                n_lo, n_hi, zlo - 0.5, zhi + 0.5)
        )

    # The r=11.0 sweep off the y-max tip corner.
    cx, cy = yoke._sweep_center(
        tip_x, y_max,
        material_sign * CHEEK_SWEEP_LEG_X_MM, CHEEK_SWEEP_LEG_Y_MM, CHEEK_SWEEP_RADIUS_MM,
    )
    plate = plate.cut(
        z_cylinder(cx, cy, CHEEK_SWEEP_RADIUS_MM, zlo - 0.5, zhi + 0.5)
    )

    for hole in holes:
        plate = plate.cut(
            z_cylinder(hole[0], hole[1], M2_CLEARANCE_RADIUS_MM, zlo - 2.0, zhi + 2.0)
        )
    return plate


# The yoke gives its two arms DIFFERENT profiles, and they are not interchangeable:
#   top arm     straight taper -- a triangle, widest at the fold and narrowing on a line tangent to
#               the cap. This is the V.
#   bottom arm  indent profile -- parallel-sided at the indent's half width out to the interior-cut
#               vertex, then the same tangent leg on to the cap.
# The split brackets inherit one each, matching the horn each bolts to.
TOP_ARM_FOLD_HALF_Z_MM = yoke.TOP_ARM_FOLD_HALF_Z_MM
TOP_ARM_TAPER_ROOT_RUN_MM = yoke.TOP_ARM_TAPER_ROOT_RUN_MM

# Where the cheek bend's axis sits, and so where the wall's FLAT material stops: one outer radius in
# from the cheek's outer face. It comes out at 15.111, which is both the yoke's own top-arm fold width
# and its SPINE_FLAT_Z_MAX -- the same number, because it is the same bend.
CHEEK_BEND_AXIS_Z_MM = CHEEK_OUTER_Z_MM - BEND_OUTER_RADIUS_MM


def arm_fold_half_z(fold_x: float, *, straight_taper: bool = False) -> float:
    """Half width of the arm where it meets its fold -- also the wall's own width there.

    In taper mode this is the yoke's own top-arm fold width. The wall matches it at the fold and
    widens to the cheek fold line only over the cheek band -- an ear, as the yoke has. Running the
    wall full-width past the cheeks instead leaves the outer bend fillet with nothing to die into.
    """
    if straight_taper:
        return CHEEK_BEND_AXIS_Z_MM
    _ext, vertex = yoke._interior_cut_points(fold_x, yoke._ARM_WEB_NOMINAL_HALF_Z_MM)
    return vertex[1]


def tapered_arm(y0: float, y1: float, fold_x: float, *,
                straight_taper: bool = False) -> build123d.Shape:
    """The horn arm on the yoke's own profile: capped disc, then either the V or the indent.

    Replaces the plain box+cap, whose square shoulder at the cap was the biggest of the unnecessary
    steps. `straight_taper` picks the TOP arm's V; the default is the BOTTOM arm's interior cut.
    """
    if straight_taper:
        # Widest at the fold, narrowing to the cap on a line tangent to it, so the taper peels off
        # the arc without a kink. The taper starts a short run off the fold, not at it: the arm's
        # bend fillet has to terminate against parallel-sided web.
        half_z = arm_fold_half_z(fold_x, straight_taper=True)
        root_x = fold_x + TOP_ARM_TAPER_ROOT_RUN_MM
        upper = [
            (fold_x, half_z),
            (root_x, half_z),
            yoke._cap_tangent_point(root_x, half_z),
        ]
    else:
        ext_point, vertex = yoke._interior_cut_points(fold_x, yoke._ARM_WEB_NOMINAL_HALF_Z_MM)
        upper = [(fold_x, vertex[1]), vertex, ext_point]
    profile = tuple(upper) + tuple((px, -pz) for px, pz in reversed(upper))

    mid_y = 0.5 * (y0 + y1)
    wire = build123d.Polyline(*[(x, mid_y, z) for x, z in profile], close=True)
    web = build123d.extrude(build123d.make_face(wire), amount=0.5 * abs(y1 - y0), both=True)
    arm = as_single_shape(as_single_shape(web).fuse(
        y_cylinder(HORN_AXIS_X_MM, HORN_AXIS_Z_MM, ARM_CAP_RADIUS_MM, y0, y1)
    ))

    lo, hi = min(y0, y1), max(y0, y1)
    for bolt_x, bolt_z in HORN_BOLTS_XZ_MM:
        arm = as_single_shape(arm.cut(
            y_cylinder(bolt_x, bolt_z, M3_CLEARANCE_RADIUS_MM, lo - 2.0, hi + 2.0)
        ))
    return as_single_shape(arm.cut(
        y_cylinder(HORN_AXIS_X_MM, HORN_AXIS_Z_MM, HORN_CENTER_CLEARANCE_RADIUS_MM,
                   lo - 2.0, hi + 2.0)
    ))


def bend_z_corner(shape: build123d.Shape, x: float, y: float, radius: float) -> build123d.Shape:
    """The arm-to-wall fold: a radius on the z-parallel corner edge."""
    return yoke._fillet_z_corner(shape, x, y, radius)


def tapered_wall(
    *, x_out: float, x_in: float, y_root: float, half_z_root: float,
    band_y_lo: float, band_y_hi: float,
) -> build123d.Shape:
    """The wall between the arm fold and the cheek folds, as one tapered plate.

    Parallel-sided for WALL_TAPER_ROOT_RUN_MM off the fold before the taper starts: the arm fold's
    outer fillet has to terminate against flat side faces, and taken straight off a tapering wall it
    fails the same way the yoke's own arm taper does without its root run.

    Narrow at the arm end -- exactly the arm's own fold width, so that edge is flush rather than a
    step -- and widening to the cheek fold line, where it must be CONSTANT: a fold line has to be
    straight, so the taper stops at the bottom of the cheek band and runs parallel through it.
    """
    if abs(half_z_root - CHEEK_BEND_AXIS_Z_MM) < 1e-6:
        # Arm fold and cheek fold line are the same width: a plain parallel-sided wall, no taper and
        # so no step anywhere along it.
        return box(x_out, x_in, y_root, band_y_hi, -CHEEK_BEND_AXIS_Z_MM, CHEEK_BEND_AXIS_Z_MM)

    taper_start = y_root + WALL_TAPER_ROOT_RUN_MM
    if band_y_lo <= taper_start:
        raise RuntimeError(
            f"wall band starts at {band_y_lo:.3f}, at or below the taper root run end "
            f"{taper_start:.3f}: the profile would double back on itself"
        )
    profile = [
        (y_root, half_z_root),
        (taper_start, half_z_root),
        (band_y_lo, CHEEK_BEND_AXIS_Z_MM),
        (band_y_hi, CHEEK_BEND_AXIS_Z_MM),
        (band_y_hi, -CHEEK_BEND_AXIS_Z_MM),
        (band_y_lo, -CHEEK_BEND_AXIS_Z_MM),
        (taper_start, -half_z_root),
        (y_root, -half_z_root),
    ]
    x_mid = 0.5 * (x_out + x_in)
    wire = build123d.Polyline(*[(x_mid, y, z) for y, z in profile], close=True)
    return as_single_shape(
        build123d.extrude(build123d.make_face(wire), amount=0.5 * abs(x_in - x_out), both=True)
    )


def cheek_y_band(holes: tuple[tuple[float, float, float], ...]) -> tuple[float, float]:
    """The y span a cheek needs for its two bolts -- the wall's constant-width band matches it."""
    ys = sorted(h[1] for h in holes)
    margin = M2_CLEARANCE_RADIUS_MM + TAB_EDGE_MARGIN_MM
    return ys[0] - margin, ys[-1] + margin


def cheek_bend_axis_x(wall_face_x: float, *, runs_neg_x: bool) -> float:
    """X of the cheek bend's axis -- also where the cheek's own flat material starts."""
    return wall_face_x + (-1.0 if runs_neg_x else 1.0) * BEND_OUTER_RADIUS_MM


def cheek_bend(*, wall_face_x: float, runs_neg_x: bool, z_sign: float,
               y_lo: float, y_hi: float) -> build123d.Shape:
    """The wall-to-cheek fold, built as a quarter annulus rather than filleted.

    OCCT will not put the true 2.4892 outer radius on this corner: the fillet's tangent line lands
    exactly on the wall's own edge, because the wall's flat width IS the tangent by construction, and
    it fails rather than degenerating. Building the bend directly sidesteps that and gives the exact
    pair of radii -- 0.889 inside, one sheet thickness to 2.4892 outside -- the same way the angled
    horn bracket's 45-degree fold is built.
    """
    off = -1.0 if runs_neg_x else 1.0
    cx = cheek_bend_axis_x(wall_face_x, runs_neg_x=runs_neg_x)
    cz = z_sign * CHEEK_BEND_AXIS_Z_MM
    quadrant = box(cx, cx - off * BEND_OUTER_RADIUS_MM, y_lo, y_hi,
                   cz, cz + z_sign * BEND_OUTER_RADIUS_MM)
    ring = y_cylinder(cx, cz, BEND_OUTER_RADIUS_MM, y_lo, y_hi).cut(
        y_cylinder(cx, cz, BEND_INNER_RADIUS_MM, y_lo, y_hi)
    )
    return as_single_shape(ring.intersect(quadrant))


def _wall_inner_x_limits() -> tuple[float, float, dict[str, float]]:
    """How far in x the top bracket's wall may sit: (tightest to servo 1, loosest, why).

    The wall's position was inherited from the yoke (SPINE_INNER_X = horn axis - the yoke's own spine
    radius) and answers to nothing here, which is why the arm ran long. It has limits on both sides:

      toward servo 1   the horn bolts approach the arm's bend, the arm's flange shortens, and the
                       wall closes on servo 1's case sweep
      away from it     the cheeks' bolts approach the CHEEK bend, and the cheek flange shortens
    """
    nearest_bolt_x = min(x for x, _z in HORN_BOLTS_XZ_MM)
    tight = {
        "horn bolt to arm bend":
            (nearest_bolt_x - M3_CLEARANCE_RADIUS_MM - MIN_HOLE_TO_BEND_MM) - BEND_INNER_RADIUS_MM,
        "arm flange length":
            (ARM_TIP_X_MM - MIN_FLANGE_FORMED_MM) - BEND_INNER_RADIUS_MM,
        "servo 1 case sweep":
            HORN_AXIS_X_MM - CASE_WALL_TOUCH_RADIUS_MM,
    }
    hole_x = top_bracket_holes()[0][0]
    tip_x = hole_x - CHEEK_TIP_MARGIN_MM
    loose = {
        "cheek bolt to cheek bend":
            (hole_x + M2_CLEARANCE_RADIUS_MM + MIN_HOLE_TO_BEND_MM) + BEND_OUTER_RADIUS_MM,
        "cheek flange length":
            (tip_x + MIN_FLANGE_FORMED_MM) + BEND_OUTER_RADIUS_MM,
    }
    return min(tight.values()), max(loose.values()), {**tight, **loose}


def wall_inner_x() -> float:
    """The top bracket's wall, as tight to servo 1 as every rule allows."""
    tight, loose, why = _wall_inner_x_limits()
    if tight < loose:
        raise RuntimeError(
            f"no wall position satisfies both sides: tightest allowed {tight:.3f} is inboard of the "
            f"loosest required {loose:.3f}. Limits: "
            + ", ".join(f"{k} {v:.3f}" for k, v in why.items())
        )
    return tight


def check_forming_rules(part: str, checks: tuple[tuple[str, float, float], ...]) -> None:
    """Backstop for the derived positions: raise if any formed-sheet rule is broken.

    The wall's x and the riser's clearance are now SOLVED from these minimums, so a violation here
    means an input moved (servo placement, hole pattern, bend radius) and the solve needs revisiting
    -- not that a number wants nudging.
    """
    broken = [
        f"{name} {value:.3f} mm is under the {minimum:.3f} mm minimum by {minimum - value:.3f}"
        for name, value, minimum in checks
        if value < minimum - 1e-6
    ]
    if broken:
        raise RuntimeError(f"{part}: " + "; ".join(broken))
