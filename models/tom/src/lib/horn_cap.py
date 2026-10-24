"""Shared three-hole, open-end pattern for sheet-metal servo-horn caps.

Tom2 uses CIRCULAR_HORN_FORK_PATTERN and its side-entry counterpart. The
older patterns remain available for the pinned and legacy designs.
Coordinates are (across,
outboard), relative to the horn axis: the opening faces +outboard and the
retained inboard screw is at -outboard. Each caller supplies only its frame,
sheet thickness and existing half-width; assembly datums never depend on
the shortened cap's bounding box.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import build123d as bd
from lib import servo_horn_interface as shi
from lib.booleans import as_single_shape


@dataclass(frozen=True)
class HornForkPattern:
    opening_radius_mm: float = shi.HORN_CENTER_CLEARANCE_RADIUS_MM
    bolt_circle_radius_mm: float = shi.HORN_BOLT_CIRCLE_RADIUS_MM
    hole_radius_mm: float = shi.HORN_BOLT_CLEARANCE_RADIUS_MM
    # The two side screws and the inboard screw; no screw beyond the axis.
    hole_directions: tuple[tuple[float, float], ...] = ((-1, 0), (0, -1), (1, 0))

    @property
    def holes(self) -> tuple[tuple[float, float, float], ...]:
        return tuple((u*self.bolt_circle_radius_mm, v*self.bolt_circle_radius_mm,
                      self.hole_radius_mm) for u, v in self.hole_directions)

    def tip_radius_mm(self, half_width_mm: float) -> float:
        return (half_width_mm-self.opening_radius_mm)/2


HORN_FORK_PATTERN = HornForkPattern()
_CUT_PAD_MM = 0.01


@dataclass(frozen=True)
class ExtendedHornForkPattern(HornForkPattern):
    """Horn semicircle, short parallel extension, then semicircular tips."""
    straight_mm: float = 1.5


# Shared yaw/gripper frame and shoulder/elbow rear collars: overhang the
# 19.95 mm horn with a 21.5 mm circle, then a short straight before each
# semicircular fork tip. Final selected straight length: 1.0 mm.
FRAME_HORN_CAP_DIAMETER_MM = 21.5
FRAME_HORN_FORK_PATTERN = ExtendedHornForkPattern(straight_mm=1.0)


@dataclass(frozen=True)
class CircularHornForkPattern(HornForkPattern):
    """Approved horn-diameter profile with compact, tangent circular caps."""
    opening_radius_mm: float = 3.5
    outer_radius_mm: float = 9.975
    tip_extension_mm: float = 4.5

    @property
    def cap_geometry(self):
        a, R, extension = self.opening_radius_mm, self.outer_radius_mm, self.tip_extension_mm
        k = a - extension + R
        radius = -k + math.sqrt(k*k-a*a-extension*extension+R*R)
        c, h = a+radius, extension-radius
        return radius, c, h, c*R/(R-radius), h*R/(R-radius)


CIRCULAR_HORN_FORK_PATTERN = CircularHornForkPattern()


@dataclass(frozen=True)
class NarrowHornForkPattern(HornForkPattern):
    """Side-entry alternative: inboard, opposite-side and far-end screws.

    Coordinates use +across for the open side and +outboard for the far
    screw. The straight flange ends at +3.5 mm, giving a 13.5 mm stem on
    a 20 mm cap. The independently sized throat clears the center screw/shaft.
    """
    hole_directions: tuple[tuple[float, float], ...] = ((0, -1), (-1, 0), (0, 1))
    stem_edge_mm: float = shi.HORN_SIDE_ENTRY_STEM_EDGE_MM
    entry_corner_radius_mm: float = 2.0
    # None retains the rounded far lug; a width makes its open edge straight.
    far_lug_open_side_mm: float | None = None
    far_lug_corner_radius_mm: float = 0.0


NARROW_HORN_FORK_PATTERN = NarrowHornForkPattern()


@dataclass(frozen=True)
class SquareSideEntryHornForkPattern(NarrowHornForkPattern):
    """Three side-entry screws with a straight, raised closed-side edge.

    The cap's far edge stays at the horn radius. Its opposite edge follows
    the caller's flange height, with this small outside corner rounding.
    """
    outer_corner_radius_mm: float = 1.0


@dataclass(frozen=True)
class RoundReturnHornForkPattern(NarrowHornForkPattern):
    """Follow the horn circumference, then return square to the bend.

    The circular back and its tangent stem use the horn's existing radius.
    The caller supplies the wider bend edge and the station where it starts.
    """


@dataclass(frozen=True)
class TangentBendHornForkPattern(RoundReturnHornForkPattern):
    """Keep the horn circle and run its tangent directly to the bend.

    A single tapered edge replaces the transverse return step. Its tangent
    point is solved from the horn radius and the caller's bend endpoint.
    """


@dataclass(frozen=True)
class ArcBreakBendHornForkPattern(RoundReturnHornForkPattern):
    """Leave the horn arc at a fixed angle, then meet a parallel bend edge."""
    arc_sweep_deg: float = 45.0
    bend_corner_radius_mm: float = 2.0


@dataclass(frozen=True)
class CircularSideEntryHornForkPattern(ArcBreakBendHornForkPattern):
    """Same circular cap, opening sideways into the existing broad gusset."""
    opening_radius_mm: float = 3.5
    entry_corner_radius_mm: float = 0.6
    straight_back: bool = False


@dataclass(frozen=True)
class FacetedHornForkPattern(RoundReturnHornForkPattern):
    """Flat far lug and 45-degree back, echoing the opposite gusset.

    The end stays at the horn radius. The diagonal meets the long closed
    edge at the shaft station, keeping the extra material near the horn.
    The central U opening and three mounting holes retain their datums.
    """
    far_lug_open_side_mm: float = 3.0
    diagonal_knee_outboard_mm: float = 0.0


def apply_narrow_horn_fork(shape, *, center, across, outboard, normal,
                           thickness_mm, half_width_mm,
                           pattern=NARROW_HORN_FORK_PATTERN,
                           closed_side_mm=None, bend_return_outboard_mm=None):
    """Narrow one flange and give its cap the selected side-entry outline.

    The cutter is confined to the specified sheet band. It trims the free
    edge back through the gusset while preserving the bend-side edge and
    every mounting datum. Apply to closed stock, before the ordinary fork.
    """
    c, u, v, n = (bd.Vector(x) for x in (center, across, outboard, normal))
    if any(abs(a.length-1) > 1e-8 for a in (u,v,n)) or any(
        abs(a.dot(b)) > 1e-8 for a,b in ((u,v),(u,n),(v,n))
    ):
        raise ValueError("Horn cap frame must be orthonormal")
    r, edge, corner = (pattern.opening_radius_mm, pattern.stem_edge_mm,
                       pattern.entry_corner_radius_mm)
    tip_r = pattern.tip_radius_mm(half_width_mm)
    if not (0 < corner <= edge <= half_width_mm and 0 < r < half_width_mm
            and thickness_mm > 0 and tip_r > pattern.hole_radius_mm):
        raise ValueError("Invalid narrow horn fork dimensions")
    square = isinstance(pattern, SquareSideEntryHornForkPattern)
    faceted = isinstance(pattern, FacetedHornForkPattern)
    straight_lug = pattern.far_lug_open_side_mm
    lug_corner = pattern.far_lug_corner_radius_mm
    if lug_corner < 0 or (lug_corner and (
            straight_lug is None or faceted or lug_corner >= straight_lug
            or 2*lug_corner >= half_width_mm-r)):
        raise ValueError("Far lug radii must leave straight entry, wall and end segments")
    if straight_lug is not None and not (
            pattern.hole_radius_mm < straight_lug <= edge
            and half_width_mm > pattern.bolt_circle_radius_mm+pattern.hole_radius_mm):
        raise ValueError("The straight far lug must retain material around its screw")
    bend_return = isinstance(pattern, RoundReturnHornForkPattern)
    closed = half_width_mm if closed_side_mm is None else closed_side_mm
    if closed < half_width_mm or (not (square or bend_return) and closed != half_width_mm):
        raise ValueError("An extended edge requires a square or bend-return cap pattern")
    if square and not (0 < pattern.outer_corner_radius_mm < min(closed, half_width_mm)):
        raise ValueError("Invalid square cap corner radius")
    if bend_return and (bend_return_outboard_mm is None or bend_return_outboard_mm >= 0):
        raise ValueError("The horn cap return must meet a bend inboard of the shaft")
    if faceted:
        lug = pattern.far_lug_open_side_mm
        knee_v = pattern.diagonal_knee_outboard_mm
        end_u = -closed+half_width_mm-knee_v
        if not (pattern.hole_radius_mm < lug <= edge and end_u < 0
                and bend_return_outboard_mm < knee_v < half_width_mm
                and half_width_mm > pattern.bolt_circle_radius_mm+pattern.hole_radius_mm
                and (closed+knee_v-pattern.bolt_circle_radius_mm)/math.sqrt(2)
                    > pattern.hole_radius_mm):
            raise ValueError("Faceted cap must retain all three bores and a bend approach")
    # Extend beyond the whole source flange; its triangular root is clipped
    # only on the free side. No bounding-box value is an assembly datum.
    reach = shape.bounding_box().diagonal + 2.0
    depth = -thickness_mm/2-_CUT_PAD_MM

    def p(a,b,d=depth):
        return c+u*a+v*b+n*d

    def bore(a,b,radius,pad):
        disk = bd.Face(bd.Wire.make_circle(radius, bd.Plane(
            origin=p(a,b,-thickness_mm/2-pad), z_dir=n)))
        return bd.extrude(disk, amount=thickness_mm+2*pad, dir=n)

    stock_r = shi.HORN_BOLT_CIRCLE_RADIUS_MM
    stock = [(0,0,shi.HORN_CENTER_CLEARANCE_RADIUS_MM)] + [
        (a*stock_r,b*stock_r,shi.HORN_BOLT_CLEARANCE_RADIUS_MM)
        for a,b in ((-1,0),(0,-1),(1,0),(0,1))]
    filled = as_single_shape(shape.fuse(*(bore(a,b,hr,0) for a,b,hr in stock)))
    q = 2**-.5
    if straight_lug is not None or square or isinstance(pattern, (TangentBendHornForkPattern, ArcBreakBendHornForkPattern,
                                      FacetedHornForkPattern)):
        # Add stock beyond the circular cap before clipping the new edge.
        # A true tangent also lies just outside the circle near its join;
        # cutting the old disk alone would leave a tiny ledge there.
        stock_open_u = straight_lug if straight_lug is not None else 0
        extension = bd.Face(bd.Wire(bd.Polyline(
            p(-closed,0, -thickness_mm/2), p(stock_open_u,0, -thickness_mm/2),
            p(stock_open_u,half_width_mm, -thickness_mm/2),
            p(-closed,half_width_mm, -thickness_mm/2), close=True).edges()))
        filled = as_single_shape(filled.fuse(bd.extrude(extension, amount=thickness_mm, dir=n)))
    far_lug_edges = [bd.ThreePointArc(p(0,r),p(tip_r,r+tip_r),p(0,half_width_mm))]
    circular_side = isinstance(pattern, CircularSideEntryHornForkPattern)
    if circular_side:
        spec = CircularHornForkPattern(opening_radius_mm=r, outer_radius_mm=half_width_mm)
        cap_r, cap_c, cap_h, cap_tx, cap_ty = spec.cap_geometry
        far_lug_edges = [bd.Edge.make_line(p(0,r),p(cap_h,r)),
            bd.ThreePointArc(p(cap_h,r),p(spec.tip_extension_mm,cap_c),p(cap_ty,cap_tx))]
    if straight_lug is not None:
        if lug_corner:
            inset_u = straight_lug-lug_corner
            far_lug_edges = [
                bd.Edge.make_line(p(0,r),p(inset_u,r)),
                bd.ThreePointArc(p(inset_u,r),
                    p(inset_u+lug_corner*q,r+lug_corner-lug_corner*q),
                    p(straight_lug,r+lug_corner)),
                bd.Edge.make_line(p(straight_lug,r+lug_corner),
                                  p(straight_lug,half_width_mm-lug_corner)),
                bd.ThreePointArc(p(straight_lug,half_width_mm-lug_corner),
                    p(inset_u+lug_corner*q,half_width_mm-lug_corner+lug_corner*q),
                    p(inset_u,half_width_mm)),
                bd.Edge.make_line(p(inset_u,half_width_mm),p(0,half_width_mm)),
            ]
        else:
            far_lug_edges = list(bd.Polyline(p(0,r),p(straight_lug,r),
                p(straight_lug,half_width_mm),p(0,half_width_mm)).edges())
    if faceted:
        far_lug_edges = list(bd.Polyline(p(0,r),p(lug,r),p(lug,half_width_mm)).edges())
        back_edges = list(bd.Polyline(p(lug,half_width_mm),p(end_u,half_width_mm),
            p(-closed,knee_v),p(-closed,-reach)).edges())
    elif square:
        rc = pattern.outer_corner_radius_mm
        back_edges = [
            bd.Edge.make_line(p(0,half_width_mm), p(-closed+rc,half_width_mm)),
            bd.ThreePointArc(p(-closed+rc,half_width_mm),
                p(-closed+rc-rc*q,half_width_mm-rc+rc*q), p(-closed,half_width_mm-rc)),
            bd.Edge.make_line(p(-closed,half_width_mm-rc),p(-closed,-reach)),
        ]
    elif isinstance(pattern, TangentBendHornForkPattern):
        # Select the tangent on the closed side of the horn. The other
        # tangent would cross the open shaft slot and the retained screws.
        bu, bv = -closed, bend_return_outboard_mm
        rr = half_width_mm**2
        dd = bu*bu+bv*bv
        k = half_width_mm*math.sqrt(dd-rr)/dd
        tu, tv = rr*bu/dd+k*bv, rr*bv/dd-k*bu
        mid_angle = (math.pi/2+math.atan2(tv,tu))/2
        back_edges = [
            bd.ThreePointArc(p(0,half_width_mm),
                p(half_width_mm*math.cos(mid_angle),half_width_mm*math.sin(mid_angle)),
                p(tu,tv)),
            *bd.Polyline(p(tu,tv),p(bu,bv),p(-closed,-reach)).edges(),
        ]
    elif circular_side and pattern.straight_back:
        back_edges = [
            bd.ThreePointArc(p(cap_ty,cap_tx),p(-half_width_mm*q,half_width_mm*q),
                            p(-half_width_mm,0)),
            bd.Edge.make_line(p(-half_width_mm,0),p(-half_width_mm,-reach)),
        ]
    elif isinstance(pattern, ArcBreakBendHornForkPattern):
        if not 0 < pattern.arc_sweep_deg < 90:
            raise ValueError("The horn arc must break between 0 and 90 degrees")
        angle = math.radians(pattern.arc_sweep_deg)
        tu, tv = -half_width_mm*math.sin(angle), half_width_mm*math.cos(angle)
        knee_v = tv+(-closed-tu)*math.tan(angle)
        if knee_v <= bend_return_outboard_mm:
            raise ValueError("The diagonal must meet the parallel edge before the bend")
        radius = pattern.bend_corner_radius_mm
        if radius < 0:
            raise ValueError("The bend-side corner radius must be nonnegative")
        if radius:
            turn = math.pi/2-angle
            setback = radius*math.tan(turn/2)
            diagonal_length = (closed+tu)/math.cos(angle)
            if setback >= min(diagonal_length,knee_v-bend_return_outboard_mm):
                raise ValueError("The corner radius consumes the diagonal or the bend approach")
            a = (-closed+setback*math.cos(angle),knee_v+setback*math.sin(angle))
            b = (-closed,knee_v-setback)
            center_u, center_v = -closed+radius, b[1]
            mid_angle = (math.pi/2+angle+math.pi)/2
            corner_edges = [
                bd.Edge.make_line(p(tu,tv),p(*a)),
                bd.ThreePointArc(p(*a),p(center_u+radius*math.cos(mid_angle),
                                        center_v+radius*math.sin(mid_angle)),p(*b)),
                bd.Edge.make_line(p(*b),p(-closed,-reach)),
            ]
        else:
            corner_edges = list(bd.Polyline(p(tu,tv),p(-closed,knee_v),
                                           p(-closed,-reach)).edges())
        back_edges = [
            bd.ThreePointArc(p(cap_ty,cap_tx) if circular_side else p(0,half_width_mm),
                p(-half_width_mm*math.sin(angle/2),half_width_mm*math.cos(angle/2)),
                p(tu,tv)),
            *corner_edges,
        ]
    elif bend_return:
        back_edges = [
            bd.ThreePointArc(p(0,half_width_mm),
                p(-half_width_mm*q,half_width_mm*q),p(-half_width_mm,0)),
            *bd.Polyline(p(-half_width_mm,0),
                         p(-half_width_mm,bend_return_outboard_mm),
                         p(-closed,bend_return_outboard_mm),
                         p(-closed,-reach)).edges(),
        ]
    else:
        back_edges = [
            bd.ThreePointArc(p(0,half_width_mm),
                p(-half_width_mm*q,half_width_mm*q),p(-half_width_mm,0)),
            bd.Edge.make_line(p(-half_width_mm,0),p(-half_width_mm,-reach)),
        ]
    boundary = bd.Wire([
        *bd.Polyline(p(-closed,-reach), p(edge,-reach),
                     p(edge,-r-corner)).edges(),
        bd.ThreePointArc(p(edge,-r-corner),
            p(edge-corner+corner*q,-r-corner+corner*q), p(edge-corner,-r)),
        bd.Edge.make_line(p(edge-corner,-r),p(0,-r)),
        bd.ThreePointArc(p(0,-r),p(-r,0),p(0,r)),
        *far_lug_edges,
        *back_edges,
    ])
    window = bd.Wire(bd.Polyline(
        p(-closed,-reach),p(reach,-reach),p(reach,reach),
        p(-closed,reach),close=True).edges())
    keep = bd.extrude(bd.Face(boundary),amount=thickness_mm+2*_CUT_PAD_MM,dir=n)
    region = bd.extrude(bd.Face(window),amount=thickness_mm+2*_CUT_PAD_MM,dir=n)
    result = as_single_shape(filled.cut(region.cut(keep),
        *(bore(a,b,hr,_CUT_PAD_MM) for a,b,hr in pattern.holes)))
    result.label, result.color = shape.label, shape.color
    return result


def apply_horn_fork(shape, *, center, across, outboard, normal, thickness_mm,
                    half_width_mm, pattern=HORN_FORK_PATTERN):
    """Finish a standard closed horn cap with the shared outline and holes.

    `center` lies halfway through the sheet on the horn axis. The stock
    generators carry the standard five-opening interface. Close those holes
    before applying this pattern, so its hole positions, diameters and center
    clearance can all be edited here, including making the opening smaller.
    This operation is bounded to the supplied plate's thickness and cap.
    """
    c, u, v, n = (bd.Vector(x) for x in (center, across, outboard, normal))
    if any(abs(a.length-1) > 1e-8 for a in (u, v, n)) or any(
        abs(a.dot(b)) > 1e-8 for a, b in ((u,v), (u,n), (v,n))
    ):
        raise ValueError("Horn cap frame must be orthonormal")
    r = pattern.opening_radius_mm
    tip_r = pattern.tip_radius_mm(half_width_mm)
    if r <= 0 or tip_r <= 0 or thickness_mm <= 0:
        raise ValueError("Horn cap opening, tip radius and sheet thickness must be positive")

    def p(a, b, depth=0):
        return c + u*a + v*b + n*depth

    def bore(a, b, radius, pad):
        plane = bd.Plane(origin=p(a, b, -thickness_mm/2-pad), z_dir=n)
        disk = bd.Face(bd.Wire.make_circle(radius, plane))
        return bd.extrude(disk, amount=thickness_mm+2*pad, dir=n)

    old_r = shi.HORN_BOLT_CIRCLE_RADIUS_MM
    stock = [(0, 0, shi.HORN_CENTER_CLEARANCE_RADIUS_MM)] + [
        (a*old_r, b*old_r, shi.HORN_BOLT_CLEARANCE_RADIUS_MM)
        for a,b in ((-1,0), (0,-1), (1,0), (0,1))
    ]
    filled = as_single_shape(shape.fuse(*(bore(a,b,hr,0) for a,b,hr in stock)))
    d = -thickness_mm/2-_CUT_PAD_MM
    tip_center = r+tip_r
    reach = half_width_mm+2
    boundary_edges = [
        bd.Edge.make_line(p(-reach,0,d), p(-half_width_mm,0,d)),
        bd.ThreePointArc(p(-half_width_mm,0,d), p(-tip_center,tip_r,d), p(-r,0,d)),
        bd.ThreePointArc(p(-r,0,d), p(0,-r,d), p(r,0,d)),
        bd.ThreePointArc(p(r,0,d), p(tip_center,tip_r,d), p(half_width_mm,0,d)),
        *bd.Polyline(p(half_width_mm,0,d), p(reach,0,d), p(reach,reach,d),
                     p(-reach,reach,d), p(-reach,0,d)).edges(),
    ]
    if isinstance(pattern, CircularHornForkPattern):
        radius = pattern.outer_radius_mm
        cap_r, cap_c, cap_h, tx, ty = pattern.cap_geometry
        theta = math.atan2(ty,tx)
        def lug(sign):
            def q(a,b): return p(sign*a,b,d)
            return [
                bd.ThreePointArc(q(radius,0),q(radius*math.cos(theta/2),radius*math.sin(theta/2)),q(tx,ty)),
                bd.ThreePointArc(q(tx,ty),q(cap_c,pattern.tip_extension_mm),q(r,cap_h)),
                bd.Edge.make_line(q(r,cap_h),q(r,0))]
        boundary_edges = [bd.Edge.make_line(p(-reach,0,d),p(-radius,0,d)),
            *lug(-1),bd.ThreePointArc(p(-r,0,d),p(0,-r,d),p(r,0,d)),
            *(e.reversed() for e in reversed(lug(1))),
            *bd.Polyline(p(radius,0,d),p(reach,0,d),p(reach,reach,d),
                         p(-reach,reach,d),p(-reach,0,d)).edges()]
        filled=as_single_shape(filled.fuse(bore(0,0,radius,0)))
    elif isinstance(pattern, ExtendedHornForkPattern):
        straight = pattern.straight_mm
        radius = half_width_mm
        assert straight > 0
        def lug(sign):
            def q(a,b):return p(sign*a,b,d)
            return [bd.Edge.make_line(q(radius,0),q(radius,straight)),
                bd.Edge.make_three_point_arc(q(radius,straight),
                    q(tip_center,straight+tip_r),q(r,straight)),
                bd.Edge.make_line(q(r,straight),q(r,0))]
        boundary_edges = [bd.Edge.make_line(p(-reach,0,d),p(-radius,0,d)),
            *lug(-1),bd.ThreePointArc(p(-r,0,d),p(0,-r,d),p(r,0,d)),
            *(e.reversed() for e in reversed(lug(1))),
            *bd.Polyline(p(radius,0,d),p(reach,0,d),p(reach,reach,d),
                         p(-reach,reach,d),p(-reach,0,d)).edges()]
        # The existing short fork must be filled before cutting the longer
        # capsule ends. Their straight sections intentionally project beyond
        # the horn circle; the circular neck trim only acts inboard.
        cap = bd.Wire.make_polygon([p(-radius,0,-thickness_mm/2),
            p(radius,0,-thickness_mm/2),p(radius,straight+tip_r,-thickness_mm/2),
            p(-radius,straight+tip_r,-thickness_mm/2)],close=True)
        filled=as_single_shape(filled.fuse(bd.extrude(bd.Face(cap),amount=thickness_mm,dir=n)))
    boundary = bd.Wire(boundary_edges)
    end_cut = bd.extrude(bd.Face(boundary), amount=thickness_mm+2*_CUT_PAD_MM, dir=n)
    result = as_single_shape(filled.cut(end_cut, *(bore(a,b,hr,_CUT_PAD_MM)
                                                  for a,b,hr in pattern.holes)))
    result.label, result.color = shape.label, shape.color
    return result


def apply_y_normal_caps(shape, *, center_xz, bands, half_width_mm, outboard_axis="x",
                        pattern=HORN_FORK_PATTERN):
    """Place the pattern on an explicit pair of Y-normal horn mounting plates."""
    across, outboard = ((0,0,1), (1,0,0)) if outboard_axis == "x" else ((1,0,0), (0,0,1))
    if outboard_axis not in ("x", "z"):
        raise ValueError("Y-normal horn caps must open along +x or +z")
    x, z = center_xz
    for lo, hi in bands:
        shape = apply_horn_fork(
            shape, center=(x,(lo+hi)/2,z), across=across, outboard=outboard,
            normal=(0,1,0), thickness_mm=hi-lo, half_width_mm=half_width_mm,
            pattern=pattern,
        )
    return shape
