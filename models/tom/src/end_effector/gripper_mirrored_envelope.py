"""The bracket's envelope, mirrored across the servo -- gripper's opposite-hand grip.

Rev3 datums and helpers the rev4 stages still read; the standalone part model is in git history.

Envelope means gripper#o1.1.f19 (the wall) plus gripper#o1.1.f5 / .f46 (the two cheeks). The arms
are not part of it and are cut away.

MIRRORED ABOUT x -63.0626, the servo's own centre plane in the bracket's frame: servo-local z maps to
bracket x, so its near case holes sit at -52.8126 and its far ones at -73.3126, and -63.0626 is the
midpoint. Mirroring there takes the near grip onto the far holes exactly --

    gripper#o1.2.3.e146/.e147   z +16, 24.450 apart
    gripper#o1.2.2.e25/.e26     z -16, 20.700 apart

-- and carries the cap shapes with it, so the two grips are true opposite hands rather than copies.
The two rows are different pitches because the servo's two case faces are not mirror images of each
other; the mirror preserves that, which is why the caps come out correct without separate handling.
"""

from __future__ import annotations

from lib.diag import say


from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
# 2mm tree: SRC_DIR is this folder, so its parent is STEP -- the 1.6002 mm ORIGINALS. Putting
# that on sys.path ahead of this folder silently rebuilds the thin part (it did: the frame came
# out 1.6002 and byte-identical). The repo root is one further up.
REPO_ROOT = SRC_DIR.parents[1]
VENDOR_DIR = REPO_ROOT / "STEP" / "imported"

import math  # noqa: E402

import build123d

from lib import shoulder_yaw_bracket_common as sb  # noqa: E402
from lib.gripper_common import extend_short_cheek, fill_connector_recess  # noqa: E402
from lib import corner_rules as cr  # noqa: E402

PART_NAME = "gripper_mirrored_envelope.step"  # pinned: the label these parts shipped with, when the source was gripper_mirrored_envelope.step.py

MIRROR_X_MM = -63.0626
CHEEK_BAND_Y_MM = (12.516, 42.034)   # the envelope; everything outside is arm
OVERSIZE_MM = 300.0

from dataclasses import dataclass  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import shoulder_yaw_top_bracket as bracket  # noqa: E402  the parent bracket's layout + build_step (a module edge)


@dataclass(frozen=True)
class ClawSpec:
    """The claw envelope's knobs. One spec, one configuration; ``family(spec)`` is the factory.

    Every field used to be a ``TOM_V2_CLAW_*`` environment variable set before re-executing this
    module. The defaults ARE this model (gripper_mirrored_envelope.step); gripper_left_claw.py builds
    its fixed jaw from the same factory with its own spec.
    """

    flange_length_mm: float = 48.5208
    cheek_width_mm: float = 20.0
    lead_in_r_mm: float | None = None           # None: half the cheek width
    jaw_root_extension_mm: float = 0.0
    cheek_band_out_mm: float = 0.0
    drop_grip_cheek: str = ""                   # "" | max | min | both
    grip_block_back_margin_mm: float = 0.0
    grip_block_corner_r_mm: float = 0.0
    cheek_gusset_run_mm: float = 0.0
    cheek_gusset_side: str = "max"
    cheek_gusset_end_mm: float = 0.0
    cheek_gusset_bolt_xyr: str = ""             # "x,y,r" for one extra hole, one knob not three
    cheek_keep_bolt: str = ""
    jaw_root_x_mm: float = 0.0
    jaw_fold_run_mm: float = 0.0
    jaw_angle_deg: float = 0.0
    fill_connector_recess: bool = False


def family(spec: ClawSpec = ClawSpec()) -> SimpleNamespace:
    """Every constant and function of the envelope, solved for ``spec``; ``.build_step()`` builds it."""
    # The wall folds at its OUTER low-y edge (gripper#o1.4.e65) and runs away from the servo. Length
    # is measured from the wall's outer face, so it is the free reach of the flange, not a tangent-to-tip
    # figure. Well clear of SendCutSend's 7.6962 minimum formed flange.
    FLANGE_LENGTH_MM = spec.flange_length_mm
                                 # 48.5208 = 70.0 from the claw's horn axis. The MOVING claw was longer
                                 # (73.3047) so the two tip edges meet at the closed pose -- it swings, so it
                                 # needs the extra reach to get there. The tips no longer line up in the open
                                 # pose, and that is the trade.
    # The flange's tip is left SQUARE, to match the claw jaw it closes against. Set a radius to put the
    # corner rounds back.
    TIP_ROUND_R_MM = 0.0

    # The cheeks get the claw's own lead-in at their tip: a 45 deg diagonal that tapers them to nothing at
    # the end, so the two jaws read as a matched pair. 45 deg makes the run equal the height, exactly as
    # the claw's gusset does, so there is no second number to keep in step.
    CHEEK_TIP_RAMP = True
    # The tip lead-in, as a RUN rather than "taper to nothing": 45 deg, so this is both how far in it
    # starts and how much flange it takes off. It used to run the flange out to zero, which is what failed
    # SendCutSend -- the last 5.207 mm of a 47.632 mm bend had less flange than the brake will form.
    #
    # 5.000 is chosen against two things. The flange left at the tip must clear 0.303 in = 7.6962 as the
    # OUTSIDE dimension, which caps the run at 10.7878 + 2.4892 - 7.6962 = 5.5808, less the laser's own
    # +/-0.005 in = 0.1270, so 5.4538. And it has to be the SAME on both jaws or the two tip cuts stop
    # matching (tom_v2#o1.24.e31 against #o1.25.e8, which are meant to be the same size). 5.000 satisfies
    # both with 0.454 mm left over. Change it in BOTH files together.
    TIP_RAMP_RUN_MM = 5.0
    # FULL-BAND SQUARE DIAGONAL at the cheeks' tip (2026-08-25, owner): the r10 quarter round
    # (@cad[tom#o1.24.e37]) is replaced by a 45 deg cut whose apex lands exactly on the jaw fold edge
    # at the claw's tip (@cad[tom#o1.24.e1]'s far end) and whose foot spans the whole band -- the same
    # diagonal-to-the-fold-tangent motif as the link plates, the elbow gusset and the yaw yoke cheeks.
    # Overrides the quarter for section 5 ONLY; the cheek gusset's quarter profile is untouched.
    CHEEK_TIP_FULL_DIAGONAL = True
    # SMALL STANDARD ROUND ON THE EX-QUARTER (2026-08-25, owner): the gusset's r10 lead-in corner at
    # (x_end, band_lo) drops to the family's r1.0 outline round -- the quarter's pattern (the tip
    # lead-in) is a square diagonal now, and the corner joins the same small-round family as every
    # other touchable free corner. True = family r; the old r10 is what False restores.
    GUSSET_QUARTER_SQUARE = True
    # ...and since 2026-08-23 it is not a chamfer at all. Both of this part's lead-ins -- the cheeks' tip
    # corner and the cheek gusset's hypotenuse -- close on a QUARTER CIRCLE whose radius is the jaw cap's,
    # which is half the band by construction (the cap is drawn on the band's own diameter). The moving
    # claw carries the same arc at both ends of its jaw; this puts the fixed one on the same radius, so
    # the pair reads as one family rather than two.
    #
    # The radius supersedes TIP_RAMP_RUN_MM above wherever it applies -- 10.0000 against that 5.0000 --
    # and it is the run as well as the radius, so the flange left standing at the tip goes 15.0000 ->
    # 10.0000 out of the 20.0000 band. Still 2.3038 clear of SendCutSend's 7.6962 minimum formed flange.
    QUARTER_ROUND_LEAD_IN = True

    # HOW WIDE THE CHEEKS RUN beside the jaw, and therefore where the fold sits. Three values have been
    # used, and each moves the jaw plate with it, because the plate hangs off that fold:
    #
    #     29.518   the bracket's own band, untouched (set CHEEK_WIDTH_MM = 0)
    #     20.000   RESTORED 2026-08-21 -- matches the moving claw's silhouette width; jaws rest 9.518 apart
    #     10.7878  matches the moving claw's fold-to-edge (its gusset base, #o1.25.e4 to e7); rest 18.7302
    #
    # 20.000 is the chunkier of the two narrowed forms and the one in service. The 10.7878 version is kept,
    # not deleted -- gripper_mirrored_envelope_narrow.step.py builds it through the env hook below.
    #
    # ONLY THE EXTENSION NARROWS. Inboard of jaw_in_x -- the bracket's own cheeks, where the M2 case bolts
    # go into the claw servo -- the full 29.518 band stays, so the silhouette is an L rather than a strip.
    # The band alone could hold neither bolt: they sit 20.700 apart (the servo's case hole pitch) and a
    # 20.000 band needs 23.916 to carry both. The fold has no business there anyway: it only runs the jaw's
    # own 47.632 mm.
    CHEEK_WIDTH_MM = spec.cheek_width_mm
    # The lead-in radius. It USED to be 0.5 * CHEEK_WIDTH_MM, on the premise that the jaw's end cap is
    # drawn on the band's own diameter -- true while this part's band matched the moving claw's 20.0000.
    # It does not any more (gripper_left_claw widened its band to back the servo), and half a 24.2500 band
    # would have quietly taken both lead-ins from r10.0000 to r12.1250. The radius belongs to the CAP, so
    # the caller states it and the default keeps the old behaviour for anything that does not.
    LEAD_IN_R_MM = (0.5 * CHEEK_WIDTH_MM if spec.lead_in_r_mm is None else spec.lead_in_r_mm)

    # HOW FAR THE JAW PLATE RUNS ON PAST THE WALL'S OUTER FACE, in +x, toward the servo it folds around.
    # 0 stops it where the wall was, which is where the family leaves it: the plate ends at x_out and its
    # end face (gripper#o1.4.f35, tom#o1.24.f35) stands in mid-air, 10.0065 mm short of the claw servo's
    # own case face. Running it on gives the fold a backing plate the whole way to the servo instead of a
    # free edge. Set from the assembly -- gripper_left_claw solves it against what it reaches -- because
    # the part is drawn standalone and has no servo in front of it.
    #
    # The TIP DOES NOT MOVE: far_x is set from x_out and FLANGE_LENGTH_MM before this is applied, and
    # this only fuses material on the inboard side of x_out.
    JAW_ROOT_EXTENSION_MM = spec.jaw_root_extension_mm

    # HOW FAR THE BAND SITS OUT from the bracket's own low-y edge, positive = away from the servo. Width
    # and position are separate knobs on purpose: CHEEK_WIDTH_MM alone can only eat the band from the fold
    # side, which moves the jaw plate by thinning the flange. This slides the whole band -- low edge, fold,
    # bend and jaw plate together -- so the plate moves with the flange intact.
    #
    # The band's low edge leaves the bracket's envelope when this is non-zero: CHEEK_BAND_Y_MM is where
    # the bracket has material, and the extension is fused on afterwards, so the cheeks simply run out
    # past the servo's own edge. Nothing is there to hit -- the claw servo starts at y 12.690 -- but that
    # overhang is the visible consequence, not a side effect to fix.
    #
    # Only meaningful with CHEEK_WIDTH_MM > 0: at 0 the fold is the bracket's own and there is no
    # extension band to slide.
    CHEEK_BAND_OUT_MM = spec.cheek_band_out_mm

    # WHICH GRIP CHEEK IS DROPPED, if either. "max" or "min" names the z side whose INBOARD BLOCK is cut
    # away -- everything above the fold on that cheek, which is the part that reaches over the claw servo,
    # carries its two case bolts and is notched for its connector recess. That side is then the bare band:
    # jaw, bend and cheek strip all still there, just nothing standing up over the servo. "" keeps both.
    #
    # It halves the fastening. The two blocks are how this jaw takes the servo's far-side M2s, one pair
    # each, so dropping one leaves the jaw held on a single side and the joint relying on that side's pair
    # plus the channel's own stiffness. Deliberate when set; not a saving to take by accident.
    #
    # "both" takes them ALL, and then the blocks are carrying nothing at all -- whatever holds the jaw to
    # the servo has to be somewhere else by then. On gripper_left_claw that somewhere is the cheek gusset,
    # run out to back the case and carrying its own bolt. Read that file's CHEEK_GUSSET_* before setting
    # this, because "both" on a part without such a tab leaves the jaw fastened by nothing.
    DROP_GRIP_CHEEK = spec.drop_grip_cheek
    DROP_GRIP_CHEEK_SIDES = ("", "max", "min", "both")
    if DROP_GRIP_CHEEK not in DROP_GRIP_CHEEK_SIDES:
        raise ValueError(
            f"ClawSpec.drop_grip_cheek={DROP_GRIP_CHEEK!r} must be one of {DROP_GRIP_CHEEK_SIDES}"
        )

    # HOW MUCH SHEET IS LEFT BEHIND THE GRIP BLOCK'S CASE BOLTS, measured from the hole's EDGE to the
    # block's back wall. 0 leaves the block at the bracket's own width.
    #
    # The block is a strap standing off the band with the servo's two case bolts in a line up it, and
    # everything behind those bolts is dead weight -- the load goes hole to band, not hole to back edge.
    # Pulling the wall in toward the outboard edge is therefore free until the sheet round the holes runs
    # out, and TWO numbers bound it:
    #
    #   0.9700   SendCutSend's hole-to-edge floor for this material, and already what the OUTBOARD side
    #            of these same holes carries -- 2.0700 centre to edge, less the 1.1000 hole. So the joint
    #            is ALREADY governed by a 0.9700 ligament, and a back margin below that would make the
    #            back the weaker side rather than merely matching it.
    #   3.2004   2 x sheet, the default here. Twice the floor, and it keeps the one side that still has
    #            margin from being cut down to the same edge as the side that has none.
    #
    # The rule floor would allow 2.2302 mm more; that is the whole distance between these two numbers, and
    # it buys nothing but a narrower strap.
    GRIP_BLOCK_BACK_MARGIN_MM = spec.grip_block_back_margin_mm

    # The RADIUS on the grip block's back-top corner (gripper#o1.4.e68), 0 to leave it square. The
    # strap's two free corners are the only sharp ones left on the part once the band's own breaks are in,
    # and 1.0 is the family's own corner break, so this matches rather than introduces a radius.
    GRIP_BLOCK_CORNER_R_MM = spec.grip_block_corner_r_mm

    # The TRIANGULAR GUSSET off the bare cheek's outboard edge (gripper#o1.4.e49): how far it runs in +x,
    # and which z cheek gets it. It is full band height where it leaves that edge and tapers to a point at
    # the far end -- the cheek that lost its grip block has nothing standing up over the servo, and this
    # puts sheet back along the line the load actually runs.
    #
    # 0 leaves the edge alone. The run is a plain length rather than a target x because the part is drawn
    # standalone; gripper_left_claw.step.py is where it is solved against what it reaches.
    CHEEK_GUSSET_RUN_MM = spec.cheek_gusset_run_mm
    CHEEK_GUSSET_SIDE = spec.cheek_gusset_side
    # How tall the tab's far end is. 0 runs it out to a point; anything else gives it a straight end, cut
    # back from the fold line, with the diagonal running from the foot of that end to the band's low edge.
    CHEEK_GUSSET_END_MM = spec.cheek_gusset_end_mm
    # ONE EXTRA BOLT HOLE through the tab, as "x,y,r" in this part's frame; empty cuts none. The tab is
    # run out to reach a case bolt the cheek did not previously cover, and a tab over a bolt hole with no
    # hole in it is half a job -- but WHICH bolt is an assembly fact, so the caller names it.
    CHEEK_GUSSET_BOLT_XYR = spec.cheek_gusset_bolt_xyr

    # A LUG LEFT STANDING ON A DROPPED CHEEK, as "side,x,y,r" -- which z side, and the bolt it is there
    # to carry. Empty keeps none. Dropping a grip block takes its case bolts with it, and sometimes one
    # of them is the only thing holding that side: this leaves just enough sheet above the fold to keep
    # it, instead of the whole block.
    CHEEK_KEEP_BOLT = spec.cheek_keep_bolt
    # Hole edge to lug edge. Generous against SendCutSend's 0.6096 floor on purpose -- this lug is the
    # fastening, so it gets a real ligament, and it leaves room for the corner breaks below.
    CHEEK_KEEP_BOLT_MARGIN_MM = 2.0

    # WHERE THE FOLD'S ROOT SITS, absolute part-frame x, 0 to leave it where the family puts it (one bend
    # inner radius in from the wall's outer face). This is the x the turn starts at -- gripper#o1.4.e1 --
    # and moving it inboard lengthens the turned flange without moving the tip. What stops it is
    # SendCutSend: the fold is a brake bend, the die contacts material within half its width, and the
    # cheeks' M2 case bolts sit just off the fold line. gripper_left_claw.step.py solves the limit.
    JAW_ROOT_X_MM = spec.jaw_root_x_mm

    # HOW FAR THE FOLD RUNS from that root to the tip, 0 to derive it from FLANGE_LENGTH_MM as before.
    # Set together with the root and the angle -- the three of them place the tip, and the tip is what is
    # actually constrained.
    JAW_FOLD_RUN_MM = spec.jaw_fold_run_mm

    # THE FIXED JAW'S ANGLE, degrees, turning about the fold's root so the tip swings AWAY from the moving
    # jaw. 0 leaves it parallel to the arm, which is how the family draws it.
    #
    # It turns the jaw, both bends and both cheeks' top edges together. The fold lines stay straight -- one
    # brake bend each, the flat pattern simply has them at an angle -- but they are no longer parallel to
    # the part's x, so anything that reads the cheek's top edge as a constant y is wrong once this is set.
    JAW_ANGLE_DEG = spec.jaw_angle_deg

    # Whether the servo's CONNECTOR RECESS is filled back in. It is a notch in the cheek's outboard edge,
    # inherited from the bracket family, where that bracket had to clear the servo's connector shroud. On
    # this jaw the cheek sits outboard of the case and the notch clears nothing, so filling it puts the
    # edge back to one straight run and returns the sheet the notch took out. Measured clear of the servo
    # after the fill, not assumed -- see the assembly note in gripper_left_claw.step.py.
    FILL_CONNECTOR_RECESS = spec.fill_connector_recess

    # Whether the bracket's OWN cheek follows the slid band down. On, the claw's low edge is one straight
    # run from the tip to the corner break; off, the extension steps down at its start and the inboard
    # cheek keeps the bracket's edge. Only reads when CHEEK_BAND_OUT_MM is non-zero.
    CARRY_INBOARD_LOW_EDGE = True

    # ONE lightening window per cheek, the cheek's own trapezium shrunk by a border: parallel top and
    # bottom, the tip ramp's 45 deg on the front, square on the back where the case bolts are. The top
    # border is not the border -- it is MIN_HOLE_TO_BEND, because the fold runs along that edge and the
    # rule there is larger than any border worth leaving.
    # One number all round: the fold's own MIN_HOLE_TO_BEND. It has to be that at the top anyway,
    # and 4.0 left the other three edges visibly thinner than it.
    LIGHTENING_BORDER_MM = 6.4944
    LIGHTENING_CORNER_R_MM = cr.INTERIOR_CORNER_R_MM

    # The cheeks' two case-bolt holes per side are FILLED. They came in from the bracket family, where
    # they take the claw servo's far-side M2s; this part no longer uses them. Filled after the window is
    # cut, not before: _lighten_cheeks places the window's back edge off the outboard bolt, so it needs
    # them to still be there when it runs.
    # The cheeks' two case-bolt holes per side STAY: they are how this jaw takes the claw servo's
    # far-side M2s, and filling them left the part with no fastener path at all.
    PLUG_CASE_BOLTS = False
    CASE_BOLT_R_MM = 1.1
    CASE_BOLT_R_TOL_MM = 0.05
    CASE_BOLTS_EXPECTED = 4


    def _plug_case_bolts(body: build123d.Shape) -> build123d.Shape:
        """Fill the cheeks' case-bolt holes, leaving the lightening window alone."""
        bb = body.bounding_box()
        sheet = sb.SHEET_THICKNESS_MM
        filled = 0
        for z_out in (bb.min.Z, bb.max.Z):
            z_in = z_out - (sheet if z_out > 0 else -sheet)
            face = max(
                (f for f in body.faces()
                 if f.geom_type == build123d.GeomType.PLANE
                 and abs(f.normal_at().Z) > 0.99
                 and abs(f.bounding_box().min.Z - z_out) < 1e-4
                 and abs(f.bounding_box().max.Z - z_out) < 1e-4),
                key=lambda f: f.area,
            )
            for wire in face.inner_wires():
                wb = wire.bounding_box()
                r = 0.5 * wb.size.X
                if abs(r - CASE_BOLT_R_MM) > CASE_BOLT_R_TOL_MM:
                    continue          # the window, not a bolt hole
                body = sb.as_single_shape(body.fuse(sb.z_cylinder(
                    0.5 * (wb.min.X + wb.max.X), 0.5 * (wb.min.Y + wb.max.Y), r,
                    min(z_in, z_out), max(z_in, z_out),
                )))
                filled += 1
        if filled != CASE_BOLTS_EXPECTED:
            raise RuntimeError(
                f"{PART_NAME}: filled {filled} case-bolt holes, expected {CASE_BOLTS_EXPECTED} "
                f"(r{CASE_BOLT_R_MM} +/- {CASE_BOLT_R_TOL_MM})"
            )
        say(f"{PART_NAME}: {filled} case-bolt holes filled; the cheeks carry the window only")
        return body


    LIGHTENING_WINDOWS = False    # the trapezoidal cuts: removed 2026-08-20, solve kept


    def _lighten_cheeks(body: build123d.Shape) -> build123d.Shape:
        """Cut one trapezoidal window in each cheek, following the cheek's shape."""
        border = LIGHTENING_BORDER_MM
        band_lo, band_hi = CHEEK_BAND_Y_MM
        bb = body.bounding_box()
        sheet = sb.SHEET_THICKNESS_MM

        y_top = band_hi - sb.MIN_HOLE_TO_BEND_MM     # the fold rule sets the top, not the border
        y_bot = band_lo + border
        if y_top - y_bot < 2.0 * LIGHTENING_CORNER_R_MM:
            raise RuntimeError(
                f"{PART_NAME}: the cheek's usable band is only {y_top - y_bot:.3f} tall, too little for a "
                f"window with r{LIGHTENING_CORNER_R_MM} corners"
            )

        # The tip ramp is x + y = ramp_c; the window's front edge is that line moved in by the border.
        ramp_c = bb.min.X + band_hi + border * math.sqrt(2.0)

        cut = 0
        for z_out in (bb.min.Z, bb.max.Z):
            z_in = z_out - (sheet if z_out > 0 else -sheet)
            face = max(
                (f for f in body.faces()
                 if f.geom_type == build123d.GeomType.PLANE
                 and abs(f.normal_at().Z) > 0.99
                 and abs(f.bounding_box().min.Z - z_out) < 1e-4
                 and abs(f.bounding_box().max.Z - z_out) < 1e-4),
                key=lambda f: f.area,
            )
            bolts = [
                (0.5 * (w.bounding_box().min.X + w.bounding_box().max.X), 0.5 * w.bounding_box().size.X)
                for w in face.inner_wires()
            ]
            if not bolts:
                raise RuntimeError(f"{PART_NAME}: no case bolts on the cheek at z {z_out:.4f} to clear")
            bolt_x, bolt_r = min(bolts, key=lambda b: b[0])
            x_back = bolt_x - bolt_r - border

            corners = [
                (ramp_c - y_top, y_top),      # front top, on the ramp
                (x_back, y_top),              # back top
                (x_back, y_bot),              # back bottom
                (ramp_c - y_bot, y_bot),      # front bottom, on the ramp
            ]
            if corners[1][0] - corners[0][0] < 4.0 * LIGHTENING_CORNER_R_MM:
                raise RuntimeError(f"{PART_NAME}: window came out {corners[1][0] - corners[0][0]:.3f} long")

            window = build123d.fillet(
                build123d.make_face(build123d.Polyline(
                    *[(x, y, 0.0) for x, y in corners], close=True
                )).vertices(),
                radius=LIGHTENING_CORNER_R_MM,
            )
            depth = abs(z_out - z_in) + 2.0
            prism = build123d.extrude(window.faces()[0], amount=depth).moved(
                build123d.Location((0.0, 0.0, min(z_in, z_out) - 1.0))
            )
            body = sb.as_single_shape(body.cut(sb.as_single_shape(prism)))
            cut += 1
        say(f"{PART_NAME}: {cut} trapezoidal lightening windows, {border:.1f} border "
              f"({sb.MIN_HOLE_TO_BEND_MM:.4f} at the fold), r{LIGHTENING_CORNER_R_MM} corners")
        return body


    def _x_cylinder(y: float, z: float, radius: float, x0: float, x1: float) -> build123d.Shape:
        """A cylinder on an x-parallel axis -- sb has the y and z ones, not this."""
        return build123d.Cylinder(radius, x1 - x0).rotate(build123d.Axis.Y, 90.0).moved(
            build123d.Location((0.5 * (x0 + x1), y, z))
        )


    CHEEK_CORNER_ROUND_R_MM = 1.0   # the bracket family's own corner break; see gripper_common


    def _carry_band_out(body, band_lo, cheeks):
        """Run each cheek's INBOARD low edge out to the slid band's, and re-cut the corner round there.

        CHEEK_BAND_OUT_MM slides the EXTENSION only -- the strip fused past the bracket's own cheek --
        so on its own it leaves a step where the two meet (gripper#o1.4.e83 standing above #o1.4.e81).
        This carries the inboard edge down to the same line, so the claw's whole low edge is one straight
        run, and moves the r1.000 corner break down to the new corner with it.

        Filled to the OLD round's top, not to the old edge: the round is a notch in the side face above
        that edge, and a fill stopping at the edge leaves it open as a scallop -- the same trap
        gripper_common._carry_corner_round documents.
        """
        r = CHEEK_CORNER_ROUND_R_MM
        carried = 0
        for z_out, z_in, x0, x1 in cheeks:
            z_lo, z_hi = min(z_in, z_out), max(z_in, z_out)
            rounds = [
                f for f in body.faces()
                if f.geom_type == build123d.GeomType.CYLINDER
                and abs(f.radius - r) < 1e-6
                and abs(f.bounding_box().min.Z - z_lo) < 1e-4
                and abs(f.bounding_box().max.Z - z_hi) < 1e-4
                and abs(f.bounding_box().max.X - x1) < 1e-4
            ]
            if not rounds:
                raise RuntimeError(
                    f"{PART_NAME}: no r{r} corner round on the cheek at z {z_out:.4f} to carry out"
                )
            old_low = min(f.bounding_box().min.Y for f in rounds)
            if old_low <= band_lo + 1e-9:
                continue                      # the band already reaches, nothing to carry
            body = sb.as_single_shape(body.fuse(sb.box(x0, x1, band_lo, old_low + r, z_lo, z_hi)))
            corner = sb.box(x1 - r, x1, band_lo, band_lo + r, z_lo, z_hi)
            keep = sb.z_cylinder(x1 - r, band_lo + r, r, z_lo, z_hi)
            body = sb.as_single_shape(body.cut(sb.as_single_shape(corner.cut(keep))))
            carried += 1
        say(f"{PART_NAME}: {carried} cheek low edges carried out to y {band_lo:.4f}, r{r} corner moved")
        return body


    def _trim_grip_block(body, cheeks, y_fold):
        """Pull each grip block's back wall in to GRIP_BLOCK_BACK_MARGIN_MM behind its case bolts."""
        margin = GRIP_BLOCK_BACK_MARGIN_MM
        trimmed = 0
        for z_out, z_in, x0, _x1 in cheeks:
            z_lo, z_hi = min(z_in, z_out), max(z_in, z_out)
            face = max(
                (f for f in body.faces()
                 if f.geom_type == build123d.GeomType.PLANE
                 and abs(f.normal_at().Z) > 0.99
                 and abs(f.bounding_box().min.Z - z_out) < 1e-4
                 and abs(f.bounding_box().max.Z - z_out) < 1e-4),
                key=lambda f: f.area,
            )
            fb = face.bounding_box()
            bolts = [
                w.bounding_box() for w in face.inner_wires()
                if w.bounding_box().min.Y > y_fold + 1e-6 and w.bounding_box().min.X >= x0 - 1e-6
            ]
            if not bolts:
                continue                      # no block on this side, or none with bolts in it to keep
            # From the hole EDGE, and from the BACKMOST hole, so a pattern that is not a single column
            # still leaves the margin on every one of them.
            x_back = min(b.min.X for b in bolts) - margin
            if x_back <= fb.min.X + 1e-6:
                continue                      # already tighter than asked; leave it alone
            # Bounded at x0, the block's own back wall, NOT at -OVERSIZE. Above y_fold and inside this
            # cheek's z there is also the BEND, which runs the jaw's whole length out past x0 -- an
            # unbounded cut takes it off and the jaw falls away as a second solid.
            body = sb.as_single_shape(body.cut(sb.box(
                x0, x_back, y_fold, OVERSIZE_MM, z_lo, z_hi
            )))
            trimmed += 1
            say(f"{PART_NAME}: grip block back wall at x {x_back:.4f}, {margin:.4f} behind the case "
                  f"bolts ({fb.max.X - x_back:.4f} wide, was {fb.max.X - x0:.4f})")
        return body


    def _block_back_wall_x(face, y_fold, x0):
        """X of the grip block's back wall on this cheek face, or None if it has no block.

        Bounded at x0, the cheek's own inboard start: with a TILTED fold the cheek also carries material
        above y_fold out along the jaw, and its edges out there are constant-x lines that would otherwise
        win the min() below and put the back wall at the jaw's tip.
        """
        walls = [
            e.bounding_box().min.X for e in face.outer_wire().edges()
            if e.geom_type == build123d.GeomType.LINE
            and e.bounding_box().size.X < 1e-6
            and e.bounding_box().min.X >= x0 - 1e-6
            # max.Y, not min.Y: the wall STARTS on the fold line, so a min.Y test excludes the very edge
            # it is looking for and the search comes back empty.
            and e.bounding_box().max.Y > y_fold + 1e-6
        ]
        return min(walls) if walls else None


    def _round_block_corner(body, cheeks, y_fold, radius):
        """Break the grip block's back-TOP corner -- the strap's one remaining sharp outside corner."""
        rounded = 0
        for z_out, z_in, x0, _x1 in cheeks:
            z_lo, z_hi = min(z_in, z_out), max(z_in, z_out)
            face = max(
                (f for f in body.faces()
                 if f.geom_type == build123d.GeomType.PLANE
                 and abs(f.normal_at().Z) > 0.99
                 and abs(f.bounding_box().min.Z - z_out) < 1e-4
                 and abs(f.bounding_box().max.Z - z_out) < 1e-4),
                key=lambda f: f.area,
            )
            back_x = _block_back_wall_x(face, y_fold, x0)
            if back_x is None:
                continue
            top_y = face.bounding_box().max.Y
            # CUT the corner rather than fillet() it. build123d refuses this edge at every radius down to
            # 0.3 -- the back wall is a boolean cut face and the top a survivor of the family's own build,
            # and OCCT will not blend the two -- so this uses the same corner-box-minus-cylinder the
            # family's other breaks use (gripper_common._carry_corner_round), which is exact and cannot
            # fail on face history. Material is at x > back_x, y < top_y, so the round centres inboard of
            # both.
            corner = sb.box(back_x, back_x + radius, top_y - radius, top_y, z_lo, z_hi)
            keep = sb.z_cylinder(back_x + radius, top_y - radius, radius, z_lo, z_hi)
            body = sb.as_single_shape(body.cut(sb.as_single_shape(corner.cut(keep))))
            rounded += 1
        say(f"{PART_NAME}: {rounded} grip block corner(s) broken r{radius}")
        return body


    def scs_min_hole_to_edge() -> float:
        """SendCutSend's hole-to-edge floor, from the sheet rule rather than restated here."""
        from lib import sheet_rule_scs as _scs
        return _scs.MIN_HOLE_TO_EDGE_MM


    def _kept_lug_extent(y_fold: float):
        """(outboard x, top y) of the lug CHEEK_KEEP_BOLT stands up, or None if it stands none.

        One place answers this, because two used to: the lug builder and the jaw-root cap that has to
        stay clear of it. Widen the band until the bolt falls below the fold and the lug stops existing --
        then the cap has nothing to clear, and a cap computed from the bolt alone would still be shrinking
        the run for a feature that is not there.
        """
        if not CHEEK_KEEP_BOLT:
            return None
        from lib import sheet_rule_scs as _scs
        _side, bx, by, br = CHEEK_KEEP_BOLT.split(",")
        bx, by, br = float(bx), float(by), float(br)
        # WHETHER A LUG IS NEEDED is a SendCutSend question, not a cosmetic one: the band carries the bolt
        # as long as it leaves the hole-to-edge floor above it. CHEEK_KEEP_BOLT_MARGIN_MM is how much
        # ligament a lug gets when one has to be built -- reading it as the threshold too made a 0.5762 mm
        # lug appear the moment the fold dropped to 21.3240, with a 1.0000 corner break that cannot fit in
        # it, when the band was in fact leaving 1.4238 of ligament: 2.3 times the floor.
        if by + br + _scs.MIN_HOLE_TO_EDGE_MM <= y_fold + 1e-6:
            return None
        top = by + br + CHEEK_KEEP_BOLT_MARGIN_MM
        return bx - (br + CHEEK_KEEP_BOLT_MARGIN_MM), top


    def _keep_bolt_lug(
        body: build123d.Shape, z_in: float, z_out: float, y_fold: float,
        bx: float, by: float, br: float,
    ) -> build123d.Shape:
        """Stand a lug back up on a dropped cheek, around one bolt, and cut that bolt through it."""
        z_lo, z_hi = min(z_in, z_out), max(z_in, z_out)
        m = CHEEK_KEEP_BOLT_MARGIN_MM
        half, top = br + m, by + br + m
        # ONE test decides this, in _kept_lug_extent, so the lug and the jaw-root cap that clears it
        # cannot disagree about whether it exists.
        if _kept_lug_extent(y_fold) is None:
            # ALREADY IN THE BAND, so there is nothing to stand up: the sheet is there, and all the bolt
            # needs is its hole. This is the case once the band is widened to swallow what used to be a
            # lug -- one surface with a hole in it instead of an extrusion fused onto one.
            #
            # FILL FIRST. The band the fold used to clip carries the bracket's OWN hole for this bolt, and
            # it is 0.5080 off the servo it is meant to line up with (0.0762 in y as well) -- the same
            # gauge-era offset that shows on the other inherited holes. Widening the band stops clipping
            # it, so it and the correctly placed one overlap into one figure-of-eight opening. Plug every
            # hole that would run into this one, then drill the right one.
            cheek = max(
                (f for f in body.faces()
                 if f.geom_type == build123d.GeomType.PLANE
                 and abs(f.normal_at().Z) > 0.99
                 and abs(f.bounding_box().min.Z - z_out) < 1e-4
                 and abs(f.bounding_box().max.Z - z_out) < 1e-4),
                key=lambda f: f.area,
            )
            plugged = 0
            for wire in cheek.inner_wires():
                wb = wire.bounding_box()
                wx, wy, wr = 0.5 * (wb.min.X + wb.max.X), 0.5 * (wb.min.Y + wb.max.Y), 0.5 * wb.size.X
                if (wx - bx) ** 2 + (wy - by) ** 2 > (br + wr) ** 2:
                    continue
                if abs(wx - bx) < 1e-6 and abs(wy - by) < 1e-6 and abs(wr - br) < 1e-6:
                    continue                      # already exactly the hole we want
                body = sb.as_single_shape(body.fuse(sb.as_single_shape(
                    sb.z_cylinder(wx, wy, wr, z_lo, z_hi)
                )))
                plugged += 1
            if plugged:
                say(f"{PART_NAME}: {plugged} inherited hole(s) plugged where they ran into the kept "
                      f"bolt at ({bx:.4f}, {by:.4f})")
            body = sb.as_single_shape(body.cut(sb.z_cylinder(bx, by, br, z_lo - 1.0, z_hi + 1.0)))
            say(f"{PART_NAME}: bolt at ({bx:.4f}, {by:.4f}) r{br:.4f} drilled straight into the "
                  f"{'max' if z_out > 0 else 'min'}-z band -- it sits {y_fold - top:.4f} below the fold, "
                  "so no lug is needed")
            return body
        # CLIPPED TO THE CHEEK'S OWN END, not symmetric about the bolt. The margin is what the bolt wants
        # on each side, but the band it stands on stops somewhere, and a lug that overhangs that end by
        # 0.5220 is sheet cantilevered off nothing -- @cad[tom#o1.24.e61] against @cad[tom#o1.24.e63].
        # Read off the cheek face BEFORE the fuse, so it is the band's own edge and not the lug's.
        cheek = max(
            (f for f in body.faces()
             if f.geom_type == build123d.GeomType.PLANE
             and abs(f.normal_at().Z) > 0.99
             and abs(f.bounding_box().min.Z - z_out) < 1e-4
             and abs(f.bounding_box().max.Z - z_out) < 1e-4),
            key=lambda f: f.area,
        )
        x_lo, x_hi = bx - half, min(bx + half, cheek.bounding_box().max.X)
        if x_hi - (bx + br) < scs_min_hole_to_edge() - 1e-6:
            raise ValueError(
                f"{PART_NAME}: clipping the lug to the cheek's end at x {x_hi:.4f} leaves only "
                f"{x_hi - (bx + br):.4f} mm to the bolt at {bx:.4f}; the band has to reach further"
            )
        body = sb.as_single_shape(body.fuse(sb.as_single_shape(
            sb.box(x_lo, x_hi, y_fold, top, z_lo, z_hi)
        )))
        r = min(cr.OUTLINE_CORNER_R_MM, m)
        if r > 0.0:
            want = ((x_lo, top), (x_hi, top))
            targets = [
                e for e in body.edges().filter_by(build123d.Axis.Z)
                if z_lo - 1e-6 < e.center().Z < z_hi + 1e-6
                and any(abs(e.center().X - wx) < 1e-6 and abs(e.center().Y - wy) < 1e-6
                        for wx, wy in want)
            ]
            if len(targets) != 2:
                raise RuntimeError(
                    f"{PART_NAME}: expected 2 lug corners to break at r{r:.3f}, found {len(targets)}"
                )
            body = sb.as_single_shape(body.fillet(r, targets))
        body = sb.as_single_shape(body.cut(sb.z_cylinder(bx, by, br, z_lo - 1.0, z_hi + 1.0)))
        say(f"{PART_NAME}: lug kept on the {'max' if z_out > 0 else 'min'}-z cheek for the bolt at "
              f"({bx:.4f}, {by:.4f}) r{br:.4f} -- x {x_lo:.4f}..{x_hi:.4f} ({x_hi - x_lo:.4f} wide, "
              f"clipped to the cheek's end), up to y {top:.4f}, corners r{r:.3f}")
        return body


    def _level_dropped_cheek(
        body: build123d.Shape, z_in: float, z_out: float, y_fold: float, *, max_dip_mm: float = 0.5,
    ) -> build123d.Shape:
        """Fill any shallow dip in the dropped cheek's top edge back up to the fold line.

        The drop cut is flat at y_fold, so it cannot MAKE a dip -- but it exposes one. Inboard of the
        band strip this side is the bracket's OWN cheek, and its top edge is not everywhere at y_fold:
        a 2.0560 mm stretch of it sits 0.0762 below, which the grip block used to bury and which the drop
        leaves as a notch in what should read as one straight edge (@cad[tom#o1.24.e17,o1.24.e61] against
        @cad[tom#o1.24.e15,o1.24.e19]).

        Filled by MEASURING the edge rather than by a hardcoded window: every horizontal edge on the
        cheek's outer face that sits just below y_fold gets a slab up to it. max_dip_mm keeps that to
        shallow steps -- the band's own low edge, the bolt holes and anything else a long way down are
        untouched.
        """
        z_lo, z_hi = min(z_in, z_out), max(z_in, z_out)
        # z_out, NOT z_hi: the cheek's OUTER face is the high z on the +z side and the LOW z on the -z
        # one, and reading the high one on the -z side finds the inner face, whose outline is the band's
        # but whose edges are not the ones that show.
        faces = [
            f for f in body.faces()
            if f.geom_type == build123d.GeomType.PLANE
            and abs(f.normal_at().Z) > 0.99
            and abs(f.bounding_box().min.Z - z_out) < 1e-4
            and abs(f.bounding_box().max.Z - z_out) < 1e-4
        ]
        if not faces:
            return body
        face = max(faces, key=lambda f: f.area)
        filled = []
        for e in face.edges():
            b = e.bounding_box()
            if b.size.X < 1e-6:
                continue
            # ANY edge that dips below the fold and stays there, not just a flat one. Dropping the block
            # can clip a bolt hole as well as a step: the old +z hole left a 0.4807 mm ARC 0.0262 deep in
            # the edge, which a line-only test walked straight past. The test is the edge's own y BAND --
            # entirely below the fold, and only just -- so a flat step and a clipped hole both match, and
            # a real hole further down does not.
            if b.max.Y > y_fold + 1e-6:
                continue
            if not (y_fold - max_dip_mm < b.min.Y < y_fold - 1e-6):
                continue
            body = sb.as_single_shape(body.fuse(sb.as_single_shape(
                sb.box(b.min.X, b.max.X, b.min.Y, y_fold, z_lo, z_hi)
            )))
            # The fuse leaves its seam behind as coplanar edges in the face -- the outline is straight,
            # but the flat reads with a rectangle drawn on it. build123d's clean() will not merge them
            # (tried, measured, no change), so they stay. They are topology, not a step: nothing is proud
            # or sunk, and a flat pattern taken off the outline never sees them.
            filled.append((b.max.X - b.min.X, y_fold - b.min.Y))
        if filled:
            say(f"{PART_NAME}: dropped cheek's top edge levelled to the fold at y {y_fold:.4f} -- "
                  + ", ".join(f"{w:.4f} long x {d:.4f} deep" for w, d in filled))
        return body


    def _cheek_gusset(body, cheeks, y_fold, band_lo, run):
        """A tab off the bare cheek's outboard edge: full band height at its root, a straight far end.

        The far end is what makes it useful rather than decorative -- it lands flush on the frame's own
        cheek, which is coplanar with this one, instead of running out to a knife point in mid-air. Its
        two corners carry the family's r1.000 break; the tab's ROOT corners deliberately do not, because
        the profile is drawn 2r back INTO the plate so those two vertices, rounds and all, are buried in
        material that is already there. That also swallows the cheek's old outboard corner breaks, which
        would otherwise be left as notches part way along the new edge.
        """
        r = CHEEK_CORNER_ROUND_R_MM
        z_out, z_in, _x0, _x1 = (max if CHEEK_GUSSET_SIDE == "max" else min)(cheeks, key=lambda c: c[0])
        z_lo, z_hi = min(z_in, z_out), max(z_in, z_out)
        face = max(
            (f for f in body.faces()
             if f.geom_type == build123d.GeomType.PLANE
             and abs(f.normal_at().Z) > 0.99
             and abs(f.bounding_box().min.Z - z_out) < 1e-4
             and abs(f.bounding_box().max.Z - z_out) < 1e-4),
            key=lambda f: f.area,
        )
        x_edge = face.bounding_box().max.X
        x_end = x_edge + run
        y_end = y_fold - CHEEK_GUSSET_END_MM
        if y_end <= band_lo + 1e-6:
            raise ValueError(
                f"CHEEK_GUSSET_END_MM={CHEEK_GUSSET_END_MM} is the whole {y_fold - band_lo:.4f} band; "
                "the tab would be a rectangle, not a gusset"
            )
        root = x_edge - 2.0 * r

        def _pick(profile, cx, cy):
            return [v for v in profile.vertices()
                    if abs(v.X - cx) < 1e-6 and abs(v.Y - cy) < 1e-6]

        if QUARTER_ROUND_LEAD_IN:
            # THE HYPOTENUSE IS A QUARTER CIRCLE, and the far end runs down to meet it. Drawn as a plain
            # rectangle and then broken twice: the family's r at the top corner as before, and
            # LEAD_IN_R_MM at the bottom one, which IS the quarter round. The end face at x_end is no
            # longer cut back to CHEEK_GUSSET_END_MM -- it runs on down as flat sheet to the arc's own
            # tangent at band_lo + LEAD_IN_R_MM, which is what closes the two into one continuous edge.
            #
            # This ADDS sheet against the old diagonal rather than taking it, which is the right
            # direction for a gusset: it is here to carry load, and the corner it fills is the corner the
            # load turns through.
            if root >= x_end - LEAD_IN_R_MM:
                raise ValueError(
                    f"the r{LEAD_IN_R_MM:.4f} lead-in reaches x {x_end - LEAD_IN_R_MM:.4f}, back past the "
                    f"tab's own root at {root:.4f}; the gusset would fold over itself"
                )
            corners = (
                (root, y_fold),          # buried in the plate
                (x_end, y_fold),         # broken r{CHEEK_CORNER_ROUND_R_MM}
                (x_end, band_lo),        # broken r{LEAD_IN_R_MM} -- the quarter round
                (root, band_lo),         # buried in the plate
            )
            profile = build123d.make_face(build123d.Polyline(
                *[(x, y, z_lo) for x, y in corners], close=True
            ))
            profile = build123d.fillet(_pick(profile, x_end, y_fold), radius=r)
            profile = build123d.fillet(
                _pick(profile, x_end, band_lo),
                radius=(r if GUSSET_QUARTER_SQUARE else LEAD_IN_R_MM),
            )
        else:
            corners = (
                (root, y_fold),          # buried in the plate
                (x_end, y_fold),         # broken
                (x_end, y_end),          # broken
                (x_edge, band_lo),       # the diagonal's foot, on the band's own edge
                (root, band_lo),         # buried in the plate
            )
            profile = build123d.make_face(build123d.Polyline(
                *[(x, y, z_lo) for x, y in corners], close=True
            ))
            broken = [
                v for v in profile.vertices()
                if min(abs(v.X - c[0]) + abs(v.Y - c[1]) for c in corners[1:3]) < 1e-6
            ]
            if len(broken) != 2:
                raise RuntimeError(f"{PART_NAME}: found {len(broken)} far-end corners to break, expected 2")
            profile = build123d.fillet(broken, radius=r)
        tab = build123d.extrude(profile.faces()[0], amount=z_hi - z_lo).moved(
            build123d.Location((0.0, 0.0, 0.0))
        )
        # The root reaches 2r back into the plate, which is far enough to swallow a case bolt sitting near
        # the cheek's outboard edge -- it took 0.5660 off this one and left the hole as an arc. Read the
        # holes off the face BEFORE the fuse and put them back after; re-cutting one the tab never touched
        # is a no-op, so this needs no test for which.
        bolts = [
            (0.5 * (b.min.X + b.max.X), 0.5 * (b.min.Y + b.max.Y), 0.5 * b.size.X)
            for b in (w.bounding_box() for w in face.inner_wires())
        ]
        body = sb.as_single_shape(body.fuse(sb.as_single_shape(tab)))
        if CHEEK_GUSSET_BOLT_XYR:
            try:
                bx, by, br = (float(v) for v in CHEEK_GUSSET_BOLT_XYR.split(","))
            except ValueError as exc:
                raise ValueError(
                    f'{PART_NAME}: CHEEK_GUSSET_BOLT_XYR must read "x,y,r"; got '
                    f"{CHEEK_GUSSET_BOLT_XYR!r}"
                ) from exc
            # The hole has to fit the tab it is cut in, with the laser's own hole-to-edge floor left on
            # every side. Checked rather than assumed: the run is solved against this bolt upstream, so a
            # mismatch here means the two have drifted apart and the part would ship with a hole broken
            # out of its edge.
            floor = sb.MM_PER_IN * 0.024 if hasattr(sb, "MM_PER_IN") else 0.6096
            room = min(x_end - (bx + br), (bx - br) - root, y_fold - (by + br), (by - br) - band_lo)
            if room < floor - 1e-6:
                raise ValueError(
                    f"{PART_NAME}: the gusset bolt at ({bx:.4f}, {by:.4f}) r{br:.4f} leaves {room:.4f} mm "
                    f"to the tab's nearest edge, under the {floor:.4f} mm hole-to-edge floor; the tab has "
                    "to reach further or the hole has to move"
                )
            bolts = list(bolts) + [(bx, by, br)]
            say(f"{PART_NAME}: gusset carries a bolt hole at ({bx:.4f}, {by:.4f}) r{br:.4f}, "
                  f"{room:.4f} mm to the nearest edge")
        for cx, cy, radius in bolts:
            body = sb.as_single_shape(body.cut(
                sb.z_cylinder(cx, cy, radius, z_lo - 1.0, z_hi + 1.0)
            ))
        say(f"{PART_NAME}: cheek gusset on the {CHEEK_GUSSET_SIDE}-z side, {run:.4f} run from "
              f"x {x_edge:.4f} to {x_end:.4f}, {y_fold - band_lo:.4f} tall at its root and "
              f"{CHEEK_GUSSET_END_MM:.4f} at its end, r{r} on both end corners; "
              f"{len(bolts)} case bolt(s) re-cut through it")
        return body


    def _band_profile(far_x, jaw_in_x, inboard_x, band_lo, y_fold, angle_deg):
        """The cheek band's outline in plan: two equal-width strips MITRED at the fold's root.

        The claw's flange turns as a rigid strip -- same 20.000 across, tip end square to its own fold --
        and the inboard strip that bolts to the servo does not move at all. Two strips of equal width
        meeting at an angle join on the BISECTOR, so the seam runs from the fold's root (gripper#o1.4.e1's
        x) down to where the two low edges cross, which is a little further out than the root. Rotating a
        box instead of building this leaves the seam open at the low side -- the turned strip's low corner
        lands above the flat one's edge -- which is what went wrong the first time.

        Returned tip-first so the tip ramp and the bends can be built in the same frame.
        """
        width = y_fold - band_lo
        a = math.radians(angle_deg)
        # Toward the tip, and from the low edge to the fold -- both are the IMAGES of the flat band's own
        # (-1, 0) and (0, 1) under the same rotation the jaw takes, so the strip stays rigid and the two
        # stay perpendicular. The signs follow build123d's CCW-positive rotate(), which is why a negative
        # angle is the one that lifts a tip sitting at -x. At angle 0 they collapse to (-1, 0) and (0, 1)
        # and every point below returns the plain rectangle the family has always drawn.
        ux, uy = -math.cos(a), -math.sin(a)
        nx, ny = -math.sin(a), math.cos(a)
        reach = jaw_in_x - far_x
        fold_root = (jaw_in_x, y_fold)
        tip_fold = (fold_root[0] + reach * ux, fold_root[1] + reach * uy)
        tip_low = (tip_fold[0] - width * nx, tip_fold[1] - width * ny)
        # Where the turned low edge crosses the flat one. At angle 0 it is the root's own x.
        low_root = (fold_root[0] - width * nx, fold_root[1] - width * ny)
        if abs(uy) < 1e-12:
            seam_low = (jaw_in_x, band_lo)
        else:
            t = (band_lo - low_root[1]) / uy
            seam_low = (low_root[0] + t * ux, band_lo)
        return [
            fold_root, tip_fold, tip_low, seam_low, (inboard_x, band_lo), (inboard_x, y_fold),
        ]


    def _channel_jaw(body: build123d.Shape) -> build123d.Shape:
        """Turn the U into a CHANNEL: jaw plate as the web, the two cheeks as its flanges, two bends.

        Was three bends -- cheek/wall, wall/cheek and wall/jaw -- with the jaw hanging off the wall's
        y-high edge. The wall is gone; the cheeks run the jaw's full length and fold straight into it, so
        the part has the same two-bend structure as the claw it closes against (gripper#o1.5).

        Nothing had to be re-dimensioned for it. The cheeks' outer faces at z +/-17.6002 and the jaw's two
        faces are exactly r_out apart from a common arc centre on the fold line (y_fold, z +/-15.111), so
        the family's own r0.889/2.4892 bend is tangent to all four faces -- and that holds wherever the fold
        sits, which is what lets CHEEK_WIDTH_MM move it without re-solving the bend.
        """
        sheet = sb.SHEET_THICKNESS_MM
        r_in, r_out = sb.BEND_INNER_RADIUS_MM, sb.BEND_OUTER_RADIUS_MM
        bb = body.bounding_box()
        x_out = bb.min.X                       # the wall's outer face -- the datum, even though it goes
        outer = [
            f for f in body.faces()
            if f.geom_type == build123d.GeomType.PLANE
            and abs(f.normal_at().X) > 0.99
            and abs(f.bounding_box().min.X - x_out) < 1e-4
        ]
        if not outer:
            raise RuntimeError(f"{PART_NAME}: no outer wall face at x {x_out:.4f} to measure from")
        wb = max(outer, key=lambda f: f.area).bounding_box()
        z0, z1 = wb.min.Z, wb.max.Z
        band_lo, band_hi = CHEEK_BAND_Y_MM
        bracket_fold = wb.max.Y                         # the bracket's own fold line
        y_fold = bracket_fold
        if CHEEK_WIDTH_MM > 0.0:
            if not (0.0 < CHEEK_WIDTH_MM <= band_hi - band_lo):
                raise ValueError(
                    f"CHEEK_WIDTH_MM={CHEEK_WIDTH_MM} must be positive and no wider than the bracket's "
                    f"own cheek band ({band_hi - band_lo:.4f} mm) -- this narrows the band, it cannot "
                    "widen it"
                )
            y_fold = band_lo + CHEEK_WIDTH_MM
            band_hi = y_fold                            # the cheek EXTENSION only; see step 1
            if CHEEK_BAND_OUT_MM:
                # Slide the whole band, not one edge: low edge, fold, bend and jaw plate all move together
                # and the flange keeps its CHEEK_WIDTH_MM. Applied AFTER the width check above, which is
                # about how much of the bracket's band is kept, not about where it ends up.
                band_lo -= CHEEK_BAND_OUT_MM
                y_fold -= CHEEK_BAND_OUT_MM
                band_hi = y_fold
        elif CHEEK_BAND_OUT_MM:
            raise ValueError(
                f"CHEEK_BAND_OUT_MM={CHEEK_BAND_OUT_MM} needs a narrowed band to slide: at "
                "CHEEK_WIDTH_MM=0 the fold is the bracket's own and there is no extension band"
            )
        y_lo, y_hi = y_fold + r_in, y_fold + r_out      # the jaw's two faces, the bend's two tangents
        far_x = x_out - FLANGE_LENGTH_MM                # the jaw tip
        jaw_in_x = x_out - r_in                         # its inner end, where the old wall fold sat
        if JAW_ROOT_X_MM:
            jaw_in_x = JAW_ROOT_X_MM
        if JAW_FOLD_RUN_MM:
            far_x = jaw_in_x - JAW_FOLD_RUN_MM
        if far_x >= jaw_in_x:
            raise ValueError(
                f"the fold runs from {jaw_in_x:.4f} out to {far_x:.4f}, which is backwards or nothing"
            )

        if y_fold < bracket_fold - 1e-9:
            # Everything above the new fold, out to where the cheeks' own fold into the (removed) wall
            # BEGINS: x_out + sheet + r_in, that fold's tangent on the cheek. Two things go with it -- the
            # wall's top strip, which step 4's cut no longer reaches, and the fold's r_out arc, which would
            # otherwise be left as a curved lip standing on the cheek's edge across the narrowed band
            # (tom_v2#o1.24.f21 / f31). Cutting to the tangent leaves that step square.
            #
            # BEFORE the jaw and its bends are built, deliberately: they sit above this fold too, and this
            # cut spans the cheeks' own z, so run it later and it would take them off.
            body = sb.as_single_shape(body.cut(sb.box(
                -OVERSIZE_MM, x_out + sheet + r_in,
                y_fold, OVERSIZE_MM,
                -OVERSIZE_MM, OVERSIZE_MM,
            )))

        # 1. The cheeks run out to the tip. Each stops at its own plate's start, short of the holes.
        cheeks = []
        for z_out in (bb.min.Z, bb.max.Z):
            z_in = z_out - (sheet if z_out > 0 else -sheet)
            face = max(
                (f for f in body.faces()
                 if f.geom_type == build123d.GeomType.PLANE
                 and abs(f.normal_at().Z) > 0.99
                 and abs(f.bounding_box().min.Z - z_out) < 1e-4
                 and abs(f.bounding_box().max.Z - z_out) < 1e-4),
                key=lambda f: f.area,
            )
            fb = face.bounding_box()
            cheeks.append((z_out, z_in, fb.min.X, fb.max.X))
            z_lo, z_hi = min(z_in, z_out), max(z_in, z_out)
            # Inboard end of the profile: normally the bracket's own cheek start, because that cheek
            # already carries the band from there in. But the fold's ROOT can be pulled inboard PAST that
            # start, and then the flat run has negative length and the polygon folds back on itself --
            # so the root wins when it is the inner of the two.
            corners = _band_profile(
                far_x, jaw_in_x, max(fb.min.X, jaw_in_x), band_lo, band_hi, JAW_ANGLE_DEG
            )
            strip = build123d.extrude(
                build123d.make_face(build123d.Polyline(
                    *[(x, y, z_lo) for x, y in corners], close=True
                )),
                amount=z_hi - z_lo,
            )
            body = sb.as_single_shape(body.fuse(sb.as_single_shape(strip)))

        # 1b. And the bracket's own cheek follows the slid band down, so the low edge is one straight run
        #     rather than a step at the extension's start.
        if CHEEK_BAND_OUT_MM and CARRY_INBOARD_LOW_EDGE:
            body = _carry_band_out(body, band_lo, cheeks)

        # 2. And the wall goes, along with the two folds that used to carry it into the cheeks: everything
        #    inboard of the cheeks and below the jaw's fold line.
        #
        #    BEFORE the jaw, not after, which is the order it used to run in. At JAW_ANGLE_DEG = 0 the jaw
        #    sits wholly above y_fold and the two never meet, so the order did not matter; tilt it and the
        #    jaw dips below that line toward the tip, and this cut -- which spans the wall's whole z, wider
        #    than the jaw's -- slices the tip clean off.
        body = sb.as_single_shape(body.cut(sb.box(
            far_x - OVERSIZE_MM, OVERSIZE_MM,
            band_lo - OVERSIZE_MM, y_fold,
            bb.min.Z + sheet, bb.max.Z - sheet,
        )))

        # 2b. One grip cheek's inboard block dropped, if asked. Everything above the fold on that side goes:
        #    the band, the bend and the jaw all sit at or below y_fold, and inboard of the cheek's own
        #    start there is nothing else up there, so the cut takes the block and only the block.
        dropped = []
        if DROP_GRIP_CHEEK == "both":
            dropped = list(cheeks)
        elif DROP_GRIP_CHEEK:
            dropped = [(max if DROP_GRIP_CHEEK == "max" else min)(cheeks, key=lambda c: c[0])]
        for z_out, z_in, x0, _x1 in dropped:
            # The cut follows the FOLD LINE, not a flat y_fold. Two bounds are both wrong: starting it at
            # the cheek's own x leaves a 0.1371 step in the BEND LINE where the turned flange rises above
            # y_fold before reaching the root -- a nick in a brake bend, not a cosmetic one -- and starting
            # it at the root instead leaves a 1.2332 tab of the block standing. Following the line does
            # both jobs, and at angle 0 it is the same flat cut it always was.
            drop = math.tan(math.radians(JAW_ANGLE_DEG))
            x_far = far_x - OVERSIZE_MM
            above = build123d.extrude(
                build123d.make_face(build123d.Polyline(
                    (x_far, y_fold + drop * (x_far - jaw_in_x), 0.0),
                    (jaw_in_x, y_fold, 0.0),
                    (OVERSIZE_MM, y_fold, 0.0),
                    (OVERSIZE_MM, y_fold + OVERSIZE_MM, 0.0),
                    (x_far, y_fold + OVERSIZE_MM, 0.0),
                    close=True,
                )),
                amount=max(z_in, z_out) - min(z_in, z_out),
            ).moved(build123d.Location((0.0, 0.0, min(z_in, z_out))))
            body = sb.as_single_shape(body.cut(sb.as_single_shape(above)))
            say(f"{PART_NAME}: the {'max' if z_out > 0 else 'min'}-z grip cheek dropped above the "
                  f"fold (z {min(z_in, z_out):.4f}..{max(z_in, z_out):.4f}); that side is now the bare "
                  f"band [DROP_GRIP_CHEEK={DROP_GRIP_CHEEK!r}]")
            body = _level_dropped_cheek(body, z_in, z_out, y_fold)
            if CHEEK_KEEP_BOLT:
                keep_side, keep_x, keep_y, keep_r = CHEEK_KEEP_BOLT.split(",")
                if keep_side.strip() == ("max" if z_out > 0 else "min"):
                    body = _keep_bolt_lug(body, z_in, z_out, y_fold,
                                          float(keep_x), float(keep_y), float(keep_r))


        # 3. THE ANGLE. The jaw and its two bends turn about the z axis through the fold's ROOT
        #    (jaw_in_x, y_fold), so the root end of the gripping face stays put and the tip swings out.
        #    Both fold lines turn with it -- they stay straight, so each is still one brake bend, the flat
        #    pattern just has its bend lines at an angle.
        angle = JAW_ANGLE_DEG
        pivot = build123d.Axis((jaw_in_x, y_fold, 0.0), (0.0, 0.0, 1.0))

        def _tilt(shape):
            return shape if not angle else sb.as_single_shape(shape.rotate(pivot, angle))

        # 4. The jaw itself, and a bend along each of its long edges (gripper#o1.4.e66 / .e105), both
        #    turned through the angle as one piece.
        body = sb.as_single_shape(body.fuse(_tilt(sb.box(far_x, jaw_in_x, y_lo, y_hi, z0, z1))))
        for z_side, sign in ((z0, -1.0), (z1, 1.0)):
            ring = sb.as_single_shape(
                _x_cylinder(y_fold, z_side, r_out, far_x, jaw_in_x)
                .cut(_x_cylinder(y_fold, z_side, r_in, far_x - 1.0, jaw_in_x + 1.0))
            )
            quadrant = sb.box(
                far_x, jaw_in_x, y_fold, y_hi,
                min(z_side, z_side + sign * r_out), max(z_side, z_side + sign * r_out),
            )
            body = sb.as_single_shape(body.fuse(_tilt(sb.as_single_shape(ring.intersect(quadrant)))))

        # 5. And the claw's own 45 deg lead-in at the cheeks' tip corner (gripper#o1.4.e66 / .e67), cut
        #    through both cheeks at once -- the jaw and its bends sit above y_fold, so they are untouched.
        if CHEEK_TIP_RAMP:
            z_lo, z_hi = bb.min.Z - 1.0, bb.max.Z + 1.0
            if QUARTER_ROUND_LEAD_IN and not CHEEK_TIP_FULL_DIAGONAL:
                # A QUARTER CIRCLE on LEAD_IN_R_MM, tangent to the tip end at far_x and to the band's low
                # edge, so the corner turns through 90 deg instead of being cut off at 45. Everything in
                # the corner square that is outside the disc goes -- the same box-minus-cylinder tool the
                # claw's own lead-in uses, and the only one that works here: an arc keeps MORE material
                # than the chamfer it replaces, so it cannot be cut out of the chamfered outline.
                r = min(LEAD_IN_R_MM, y_fold - band_lo)
                tool = sb.as_single_shape(
                    sb.box(far_x, far_x + r, band_lo, band_lo + r, z_lo, z_hi).cut(
                        sb.z_cylinder(far_x + r, band_lo + r, r, z_lo, z_hi)
                    )
                )
            else:
                run = ((y_fold - band_lo) if CHEEK_TIP_FULL_DIAGONAL
                       else min(TIP_RAMP_RUN_MM, y_fold - band_lo))   # 45 deg
                keep = (y_fold - band_lo) - run                   # flange left standing at the tip
                tool = sb.as_single_shape(build123d.extrude(
                    build123d.make_face(build123d.Polyline(
                        (far_x, y_fold - keep, z_lo),
                        (far_x, band_lo, z_lo),
                        (far_x + run, band_lo, z_lo),
                        close=True,
                    )),
                    amount=z_hi - z_lo,
                    dir=build123d.Vector(0.0, 0.0, 1.0),
                ))
            body = sb.as_single_shape(body.cut(_tilt(tool)))

        # 7. And the connector notch in whatever grip cheek is left -- which is none, if both were
        #    dropped. Steps 7, 8 and 9 all read a block that is no longer there.
        if FILL_CONNECTOR_RECESS and DROP_GRIP_CHEEK != "both":
            body = fill_connector_recess(body, PART_NAME)

        # 8. Last, because it reads the filled edge and the bolts through it: the block's back wall in.
        if GRIP_BLOCK_BACK_MARGIN_MM > 0.0 and DROP_GRIP_CHEEK != "both":
            body = _trim_grip_block(body, cheeks, y_fold)

        # 9. The strap's corner break, after its back wall is where it finally sits.
        if GRIP_BLOCK_CORNER_R_MM > 0.0 and DROP_GRIP_CHEEK != "both":
            body = _round_block_corner(body, cheeks, y_fold, GRIP_BLOCK_CORNER_R_MM)

        # 10. And the gusset off the bare cheek, which has no block to break the corner of.
        if CHEEK_GUSSET_RUN_MM > 0.0:
            body = _cheek_gusset(body, cheeks, y_fold, band_lo, CHEEK_GUSSET_RUN_MM)

        # 11. The jaw plate carried on past the wall's outer face, toward the servo.
        #
        #     LAST, and that is not cosmetic ordering: the plate runs above y_fold, which is exactly the
        #     band step 2b's DROP_GRIP_CHEEK cut clears out, and it reaches inboard of the cheeks' own
        #     start, which is where step 8 trims the block back to. Fused before either of those and it
        #     would be cut straight off again.
        if JAW_ROOT_EXTENSION_MM > 0.0:
            # THE WHOLE END CROSS-SECTION IS EXTRUDED, not a slab of plate. The end of this run is not
            # one rectangle: the flat plate's own face (gripper#o1.4.f35) is the big one, but the FOLD
            # carries a corner beside each cheek (#o1.4.f3 and its mirror), and a slab drawn on the
            # plate's y band alone leaves both of those standing where they were -- the bend stops short
            # of the plate it turns into. Sweeping every face that ends the run carries the plate, the
            # bend and both corners together, and needs to know nothing about their shapes.
            #
            # Same reason gripper_right_claw._extend_jaw sweeps its end faces rather than rebuilding
            # them, and the same datum: the run ends at the fold's ROOT, one inner bend radius outboard
            # of the wall face.
            if abs(JAW_ANGLE_DEG) > 1e-9:
                raise ValueError(
                    f"JAW_ROOT_EXTENSION_MM needs the jaw straight; it is tilted {JAW_ANGLE_DEG:.4f} deg, "
                    "and the end faces no longer sit square to x"
                )
            # THE RUN STOPS BEFORE THE LUG, and this is a manufacturability cap, not a preference.
            # Carrying the plate inboard carries its FOLD with it, and the fold turns the cheek band into
            # the plate. Where a kept lug stands, the band does not turn -- it continues straight up out
            # of its own plane -- so the fold cannot reach that x at all: the two would be one flange
            # folded and unfolded at the same place, which no flat pattern can express. Ran past it once
            # (0.8613 into the lug, over @cad[tom#o1.24.e59]) before this cap existed.
            #
            # The bend therefore ENDS beside the lug, and a bend that ends inside a panel wants corner
            # relief: SendCutSend's MIN_CORNER_RELIEF_FROM_BEND, 0.037 in = 0.9398 mm, is the gap left.
            run = JAW_ROOT_EXTENSION_MM
            lug = _kept_lug_extent(y_fold)
            if lug is not None:
                from lib import sheet_rule_scs as _scs
                lug_lo, _lug_top = lug
                cap = (lug_lo - _scs.MIN_CORNER_RELIEF_FROM_BEND_MM) - jaw_in_x
                if cap <= 0.0:
                    raise ValueError(
                        f"{PART_NAME}: the kept lug starts at x {lug_lo:.4f}, at or behind the fold root "
                        f"{jaw_in_x:.4f}; there is no room to carry the jaw root at all"
                    )
                if run > cap:
                    say(f"{PART_NAME}: jaw-root run capped {JAW_ROOT_EXTENSION_MM:.4f} -> {cap:.4f} "
                          f"-- the fold has to end {_scs.MIN_CORNER_RELIEF_FROM_BEND_MM:.4f} clear of the "
                          f"lug at x {lug_lo:.4f}")
                    run = cap
            ends = [
                f for f in body.faces()
                if f.geom_type == build123d.GeomType.PLANE
                and abs(f.normal_at().X) > 0.99
                and abs(f.bounding_box().min.X - jaw_in_x) < 1e-4
                and abs(f.bounding_box().max.X - jaw_in_x) < 1e-4
            ]
            if not ends:
                raise RuntimeError(
                    f"{PART_NAME}: no end face at x {jaw_in_x:.4f} to carry the jaw root on from"
                )
            for face in ends:
                body = sb.as_single_shape(body.fuse(sb.as_single_shape(
                    build123d.extrude(face, amount=run, dir=build123d.Vector(1.0, 0.0, 0.0))
                )))
            if len(body.solids()) != 1:
                raise RuntimeError(
                    f"{PART_NAME}: the jaw-root extension came away as {len(body.solids())} solids; "
                    f"it starts at x {jaw_in_x:.4f} and has to land on the plate's end face"
                )
            say(f"{PART_NAME}: jaw root carried {run:.4f} on from x {jaw_in_x:.4f} "
                  f"out to {jaw_in_x + run:.4f}, over {len(ends)} end face(s) "
                  f"-- the plate and the fold's corner on both sides")
        return body


    def build_step() -> build123d.Shape:
        body = bracket.build_step()
        lo, hi = CHEEK_BAND_Y_MM
        for centre_y in (lo - 0.5 * OVERSIZE_MM, hi + 0.5 * OVERSIZE_MM):
            body = sb.as_single_shape(body.cut(
                build123d.Box(OVERSIZE_MM, OVERSIZE_MM, OVERSIZE_MM).locate(
                    build123d.Location((0.0, centre_y, 0.0))
                )
            ))
        body = extend_short_cheek(body, PART_NAME)
        body = sb.as_single_shape(body.mirror(
            build123d.Plane(origin=(MIRROR_X_MM, 0, 0), z_dir=(1, 0, 0))
        ))
        body = _channel_jaw(body)   # after the mirror: the channel is symmetric, no handing
        if LIGHTENING_WINDOWS:
            body = _lighten_cheeks(body)
        if PLUG_CASE_BOLTS:
            body = _plug_case_bolts(body)
        solids = body.solids()
        if len(solids) != 1:
            raise RuntimeError(
                f"{PART_NAME}: envelope came out as {len(solids)} solids -- the cheek band "
                f"{CHEEK_BAND_Y_MM} does not hold the wall and both cheeks together."
            )
        out = solids[0]
        out.label = PART_NAME
        out.color = sb.BRACKET_COLOR
        bb = out.bounding_box()
        say(f"{PART_NAME}: envelope mirrored about x {MIRROR_X_MM}; "
              f"channel: jaw {FLANGE_LENGTH_MM:.1f} clear, cheeks folded straight into it, 2 bends; "
              f"x {bb.min.X:.3f}..{bb.max.X:.3f}; solids {len(solids)}")
        return out


    return SimpleNamespace(**locals())
