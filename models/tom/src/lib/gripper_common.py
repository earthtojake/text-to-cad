"""Shared geometry helpers for the gripper parts.

Kept local to gripper on purpose: these edits must not reach tmp/shoulder_yaw_top_bracket.step.py,
which the other gripper still builds on.
"""

from __future__ import annotations

from lib.diag import say

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
# 2mm tree: SRC_DIR is this folder, so its parent is STEP -- the 1.6002 mm ORIGINALS. Putting
# that on sys.path ahead of this folder silently rebuilds the thin part (it did: the frame came
# out 1.6002 and byte-identical). The repo root is one further up.
REPO_ROOT = SRC_DIR.parent


import build123d

from lib import shoulder_yaw_bracket_common as sb  # noqa: E402

# The two cheeks do not start at the same y: the +z one runs from 12.516, the -z one only from
# 16.2662, because the servo's two case faces are not mirror images. Extending the short one to the
# wall's own end makes them flush.
SHORT_CHEEK_Y_MM = 16.2662
WALL_END_Y_MM = 12.516
FACE_TOL_MM = 1e-3


def extend_short_cheek(
    body: build123d.Shape,
    part_name: str,
    *,
    short_cheek_y: float | None = None,
    wall_end_y: float | None = None,
) -> build123d.Shape:
    """Carry the short cheek's end down to the wall's end, re-extruding its own cross-section.

    Takes the faces sitting on the short cheek's end plane and extrudes them, rather than fusing a
    box: the bend is curved there, and a box would square it off.
    """
    # Both default to the family's own numbers. gripper_frame slides its cheek band along the wall
    # and passes the pair moved by the same amount -- the point is still "extend the short cheek to
    # where the long one starts", it is just that both ends have moved.
    # 2mm tree: SHORT_CHEEK_Y_MM / WALL_END_Y_MM are 1.6002-era literals and the cheeks move with
    # sheet thickness, so a fixed plane finds no faces at 2.0320. Read both off the body instead --
    # the two cheeks start at different y (the servo's case faces are not mirror images), and the job
    # is simply "extend the later one back to where the earlier one starts".
    if short_cheek_y is None or wall_end_y is None:
        starts = []
        for z_sign in (1.0, -1.0):
            zs = [f for f in body.faces()
                  if f.geom_type == build123d.GeomType.PLANE and abs(f.normal_at().Z) > 0.99
                  and f.bounding_box().min.Z * z_sign > 0]
            if zs:
                starts.append(min(f.bounding_box().min.Y for f in zs))
        if len(starts) == 2 and abs(starts[0] - starts[1]) > 1e-6:
            derived_end, derived_short = min(starts), max(starts)
            short_cheek_y = derived_short if short_cheek_y is None else short_cheek_y
            wall_end_y = derived_end if wall_end_y is None else wall_end_y
    short_y = SHORT_CHEEK_Y_MM if short_cheek_y is None else short_cheek_y
    end_y = WALL_END_Y_MM if wall_end_y is None else wall_end_y
    drop = short_y - end_y
    ends = [f for f in body.faces()
            if f.geom_type == build123d.GeomType.PLANE and abs(f.normal_at().Y) > 0.99]
    faces = [f for f in ends if abs(f.center().Y - short_y) < FACE_TOL_MM]
    if not faces and ends:
        # 2mm tree: short_y is a 1.6002-era literal (or one derived from it), and every cheek plane
        # moves with sheet thickness, so an exact match finds nothing at 2.0320. Snap to the nearest
        # real end plane and say so, rather than failing on a number that was only ever a snapshot.
        near = min(ends, key=lambda f: abs(f.center().Y - short_y))
        if abs(near.center().Y - short_y) < 6.0:
            snapped = round(near.center().Y, 4)
            say(f"{part_name}: short cheek plane snapped {short_y:.4f} -> {snapped:.4f} "
                  f"(sheet is {sb.SHEET_THICKNESS_MM:.4f}, the literal was set at 1.6002)")
            # RE-DERIVE the drop, do not patch it (fixed 2026-08-23). This was
            # `drop += short_y - snapped`, which adjusts in the WRONG DIRECTION: drop was already
            # short_y_stale - end_y, so the correction has to SUBTRACT the snap, not add it. Adding
            # it overshot and the extrusion did not land flush on the wall's end plane, leaving a
            # 0.0762 mm ledge along the cheek -- @cad[tom#o1.24.e66] bounded it. Since drop is only
            # ever "how far from the short cheek's plane down to the wall's end", computing it from
            # the snapped value is unambiguous and cannot pick up a sign again.
            short_y = snapped
            drop = short_y - end_y
            faces = [f for f in ends if abs(f.center().Y - short_y) < FACE_TOL_MM]
    if not faces:
        raise RuntimeError(
            f"{part_name}: no faces on the short cheek's end plane y {short_y}; "
            "the cheek moved and this extension needs re-aiming."
        )
    # amount is POSITIVE: extrude() runs along the face normal, which here points -y (out of the
    # part). A negative amount pushed the extrusion back into existing material and added nothing.
    for f in faces:
        body = sb.as_single_shape(body.fuse(
            sb.as_single_shape(build123d.extrude(f, amount=drop))
        ))
    return _carry_corner_round(body, part_name, end_y=end_y, short_y=short_y)


CORNER_ROUND_R_MM = 1.0


def _carry_corner_round(
    body: build123d.Shape, part_name: str, *, end_y: float | None = None,
    short_y: float | None = None,
) -> build123d.Shape:
    """Carry the cheek's r1.000 corner round out to the extended end.

    The cheek's END face starts 1.000 inboard of its SIDE face, because the round occupies that
    strip. Extruding the end face alone therefore leaves a 1.000 step and strands the round 3.750
    inboard. This fills the strip over the extension, then cuts the same round at the new corner.
    """
    r = CORNER_ROUND_R_MM
    short = SHORT_CHEEK_Y_MM if short_y is None else short_y
    wall_end = WALL_END_Y_MM if end_y is None else end_y
    rounds = [
        f for f in body.faces()
        if f.geom_type == build123d.GeomType.CYLINDER
        and abs(f.radius - r) < 1e-6
        and abs(f.bounding_box().min.Y - short) < 1e-3
    ]
    if not rounds:
        raise RuntimeError(f"{part_name}: no r{r} corner round at y {short}")
    for f in rounds:
        bb, mid = f.bounding_box(), f.center()
        # A quarter round's arc centre is the bbox corner FARTHEST from its centroid; the SIDE face
        # is tangent at the other x. (Face has no arc_center, so this is read off the geometry.)
        centre_x = bb.min.X if abs(mid.X - bb.min.X) > abs(mid.X - bb.max.X) else bb.max.X
        side_x = bb.max.X if centre_x == bb.min.X else bb.min.X
        inward = 1.0 if side_x < centre_x else -1.0
        z0, z1 = bb.min.Z, bb.max.Z
        # Up to SHORT_CHEEK + r, not just SHORT_CHEEK: the old round is a notch in the side ABOVE
        # the old end face, so a fill that stops at the end face leaves it open as a scallop.
        y_lo, y_hi = wall_end, short + r
        strip = build123d.Box(r, y_hi - y_lo, z1 - z0).locate(
            build123d.Location((side_x + inward * 0.5 * r, 0.5 * (y_lo + y_hi), 0.5 * (z0 + z1)))
        )
        body = sb.as_single_shape(body.fuse(strip))
        corner = build123d.Box(r, r, z1 - z0).locate(build123d.Location(
            (side_x + inward * 0.5 * r, wall_end + 0.5 * r, 0.5 * (z0 + z1))
        ))
        keep = build123d.Cylinder(r, z1 - z0).locate(build123d.Location(
            (side_x + inward * r, wall_end + r, 0.5 * (z0 + z1))
        ))
        body = sb.as_single_shape(body.cut(sb.as_single_shape(corner.cut(keep))))
    return body


CONNECTOR_RECESS_ROUND_R_MM = CORNER_ROUND_R_MM


def fill_connector_recess(
    body: build123d.Shape, part_name: str, side: str | None = None
) -> build123d.Shape:
    """Fill the servo connector notch in each cheek's outboard edge, corner rounds and all.

    The notch comes from the bracket family, which cut it to clear the servo's connector shroud. On
    the gripper's parts the cheek sits outboard of the case and it clears nothing, so the sheet is
    better solid -- but only where that has been measured against the built assembly, hence the
    per-part switch rather than doing it in the family.

    Found by shape, not by coordinate: a notch is a constant-x WALL standing strictly inside the
    cheek's own y range, with a LIP at each end running the same distance to the same x, and an
    r1.000 break carrying each lip out to the edge. Matching both lips is what keeps this off the
    part's other constant-x edges -- a tip, a step, the back of a block -- which have no such pair.

    `side` names the z cheek to do, "min" or "max"; None does both, which is only right when both
    notches are known dead.
    """
    r = CONNECTOR_RECESS_ROUND_R_MM
    bb = body.bounding_box()
    if side not in (None, "min", "max"):
        raise ValueError(f"{part_name}: side={side!r} must be None, 'min' or 'max'")
    # Which cheeks to touch. The two are independent: on this frame only the -z one's notch is dead,
    # because the +z cheek is the side the servo's connector actually comes out of.
    z_sides = {"min": (bb.min.Z,), "max": (bb.max.Z,)}.get(side, (bb.min.Z, bb.max.Z))
    filled = 0
    for z_out in z_sides:
        z_in = z_out - (sb.SHEET_THICKNESS_MM if z_out > 0 else -sb.SHEET_THICKNESS_MM)
        faces = [
            f for f in body.faces()
            if f.geom_type == build123d.GeomType.PLANE
            and abs(f.normal_at().Z) > 0.99
            and abs(f.bounding_box().min.Z - z_out) < 1e-4
            and abs(f.bounding_box().max.Z - z_out) < 1e-4
        ]
        if not faces:
            continue
        face = max(faces, key=lambda f: f.area)
        found = _connector_notch(face)
        if found is None:
            continue
        wall, lip_x = found
        x_out = lip_x + (r if lip_x > wall.min.X else -r)
        body = sb.as_single_shape(body.fuse(sb.box(
            min(wall.min.X, x_out), max(wall.min.X, x_out),
            wall.min.Y - r, wall.max.Y + r,
            min(z_in, z_out), max(z_in, z_out),
        )))
        filled += 1
    say(f"{part_name}: {filled} connector recess(es) filled; the cheek's outboard edge runs straight")
    return body


def _connector_notch(face):
    """The notch's (wall bbox, lip far x) on this cheek face, or None if it has none."""
    fb = face.bounding_box()
    edges = face.outer_wire().edges()
    walls = [
        e for e in edges
        if e.geom_type == build123d.GeomType.LINE
        and e.bounding_box().size.X < 1e-6
        and e.bounding_box().min.Y > fb.min.Y + 1e-6
        and e.bounding_box().max.Y < fb.max.Y - 1e-6
    ]
    for wall in walls:
        wb = wall.bounding_box()
        lips = [
            e for e in edges
            if e.geom_type == build123d.GeomType.LINE
            and e.bounding_box().size.Y < 1e-6
            and e.bounding_box().size.X > 1e-6
            and (abs(e.bounding_box().min.Y - wb.min.Y) < 1e-6
                 or abs(e.bounding_box().min.Y - wb.max.Y) < 1e-6)
            and min(abs(e.bounding_box().min.X - wb.min.X),
                    abs(e.bounding_box().max.X - wb.min.X)) < 1e-6
        ]
        if len(lips) != 2:
            continue
        far = [
            (eb.max.X if abs(eb.min.X - wb.min.X) < 1e-6 else eb.min.X)
            for eb in (e.bounding_box() for e in lips)
        ]
        if abs(far[0] - far[1]) > 1e-6:
            continue          # the two lips do not land together, so this is not a notch
        return wb, far[0]
    return None


# --- The jaw-edge crown and its relief slots, ONE solve for both claws ----------------------------
# Both claws carry the same crowned free edge: one shallow arc springing tangentially off r10.0
# corner circles. The MOVING claw's edge is the canonical one (its corner span is set by the jaw
# reach); the FIXED claw's edge is 4.39 shorter, so to carry the IDENTICAL curve its far corner
# cannot be a corner at all -- the crown runs past where its end face is, and an r10.0 quarter
# springs off the (lengthened) end face tangent onto the crown. That quarter is the binding
# constraint on the relief slots, so the slots are solved against it FOR BOTH CLAWS -- identical
# pattern, identical curve, despite the different edge lengths.
#
# The relief slots exist to make the crown weight-neutral: their total area is solved so the sheet
# they remove equals the sheet the crown adds (the moving claw's canonical added area). Everything
# is a function of the one knob CROWN_HEIGHT_MM, so a taller crown grows its own relief.
# 0.0 IS OFF: both claws skip the crown entirely and the free edges run straight between their
# quarter circles, which is the shape the experiment started from. The machinery below stays for the
# next time a crown is tried -- set a height and both claws grow the same curve again.
CROWN_HEIGHT_MM = 0.0
