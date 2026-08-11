"""Carbon-ceramic brake package: discs, hats, hubs and monobloc calipers.

These sit INSIDE the rim and are read through the spokes, so everything here is
built for the view from outboard: a light friction band drilled over a
near-black vane pattern, bronze bobbins around the hat, and one big bronze
monobloc caliper per corner.

Sizing rule: FILL THE RIM.
--------------------------
A wheel reads as big and planted only if its interior is full.  A disc that
leaves a wide empty annulus inside the barrel makes the whole corner read as a
small bright coin hanging in a dark hole, and at thumbnail size that drains the
car's stance -- the wheels stop anchoring the silhouette.  So the discs are
sized off the RIM, not off a brake catalogue: ``_axle_geometry`` takes each
rim's barrel bore (``wheels._Spec.bore_r - 9``) and works inward through the
caliper crown, the bleed nipple and a small clearance to land the disc OD.
That puts a 440 mm disc inside the 21 in front rim and a 456 mm disc inside the
22 in rear, both ~85 % of the barrel bore.

The ``_backing_shroud`` closes the corner from behind.  It is the other half of
the same idea: without it the drillings and the vane gaps show pale background
through the disc, which makes the disc read as lace instead of as a solid
machined mass, and the annulus between the disc OD and the barrel stays open to
daylight.  The shroud is carried in the CALIPER prototype, not the rotor, so
its angular gap always stays parked under the caliper wherever that is clocked.

Local build frame (per corner, before placement)
------------------------------------------------
    +Z  outboard (along the wheel axis, away from the car centreline)
    +X  car forward
     0  the wheel centre plane / disc mid-plane

Placement maps local +X -> global +X on both sides and local +Z -> outboard,
so the clock angle of the caliper has to be negated for the left-hand corners
(see ``_corner_locations``).  The disc/hat/hub assembly is rotationally
symmetric, so one prototype per axle serves both sides; the caliper assembly is
built centred at local theta = 0 and rotated into its clock position when it is
placed.  Both go through ``compound_from_instances`` so the four corners share
geometry instead of deep-copying it.
"""

from __future__ import annotations

import math

from build123d import (
    Axis,
    Box,
    Circle,
    Cone,
    Compound,
    Cylinder,
    Location,
    Plane,
    Polyline,
    Pos,
    Rot,
    extrude,
    fillet,
    make_face,
    revolve,
)

from cadgen import compound_from_instances

from hypercar_parts import surfaces as S
from hypercar_parts import palette as P
from hypercar_parts.palette import style


# ---------------------------------------------------------------------------
# axle specifications
# ---------------------------------------------------------------------------


class Axle:
    """Every number for one axle's brake corner, in the local frame above."""

    def __init__(
        self,
        name,
        barrel_r,
        disc_r,
        disc_ir,
        disc_t,
        plate_t,
        n_vane,
        streaks,
        hub_face_z,
        cal_arc,
        cal_windows,
        pistons,
        clock_deg,
    ):
        self.name = name
        self.barrel_r = barrel_r            # rim barrel bore -- the hard limit
        self.R = disc_r                     # friction OD radius
        self.Ri = disc_ir                   # friction ID radius
        self.T = disc_t                     # total (vented) thickness
        self.PT = plate_t                   # one friction plate
        self.n_vane = n_vane                # long vanes; short ones interleave
        self.streaks = streaks              # (groups, per_group, sweep_deg)
        self.hub_face_z = hub_face_z        # wheel mounting face
        self.cal_arc = cal_arc              # caliper angular length
        self.cal_windows = cal_windows      # (centre_deg, width_deg) per window
        self.pistons = pistons              # (theta_deg, bore_radius) per side
        self.clock = clock_deg              # global clock angle of the caliper

        # -- derived -------------------------------------------------------
        self.gap = disc_t - 2 * plate_t     # vane channel height
        self.hat_or = disc_ir + 18          # hat flange overlaps the disc ID
        self.bobbin_r = disc_ir + 10
        self.hat_wall_o = disc_ir - 16
        self.hat_wall_i = self.hat_wall_o - 10
        self.hat_bore = 60.0
        self.carrier_r = 78.0               # clears the inside of the hat cup

        self.pad_t = 8.5                    # friction block
        self.back_t = 6.0                   # pad backing plate
        self.mouth = disc_t / 2 + self.pad_t + self.back_t + 1.5
        self.half_w = self.mouth + 14.0     # caliper half width
        self.cal_ro = disc_r + 18.0
        self.cal_rb = disc_r + 6.0          # bridge inner face
        self.cal_ri = self.hat_or + 4.0     # clears the hat flange
        self.pad_ro = disc_r - 8.0
        self.pad_ri = self.cal_ri + 4.0
        # the friction band the pads actually sweep; the unswept rings inboard
        # and outboard of it are what give the disc its two-tone read
        self.swept_ri = self.pad_ri - 4.0
        self.swept_ro = self.pad_ro
        self.taper_deg = cal_arc * 0.36     # where the caliper starts to neck
        self.pad_arc = min(cal_arc * 0.80, 2 * self.taper_deg + 7.0)
        self.ear_ang = cal_arc / 2.0 - 7.0
        self.ear_r = disc_r - 9.0
        self.ear_z0 = -self.half_w
        self.ear_z1 = -self.half_w - 13.0
        self.brk_z1 = self.ear_z1
        self.brk_z0 = self.ear_z1 - 16.0

        # -- backing shroud ------------------------------------------------
        # Inboard of the disc, so it never fights the friction band; its outer
        # flange runs out into the annulus the disc cannot reach and stops just
        # short of the barrel, closing the corner to daylight.
        self.shr_z = -disc_t / 2.0 - 8.0
        self.shr_ri = self.hat_or + 6.0     # clears the hat flange + bobbins
        self.shr_rm = disc_r - 4.0          # dish rolls over under the disc OD
        self.shr_ro = barrel_r - 9.0        # flange, held off the barrel wall
        # Only the caliper BODY reaches the shroud's depth (the bracket and the
        # banjo are much further inboard), so the sector can close right up to
        # the caliper: a wide notch would read as a broken ring.
        self.shr_gap = 8.0
        self.shr_arc = 360.0 - cal_arc - 2 * self.shr_gap

        # Nothing may touch the rim barrel: the bleed cap is the outermost
        # thing on the caliper, the flange the outermost thing on the shroud.
        reach = max(self.cal_ro + 8.0, self.shr_ro)
        if reach > barrel_r - 3.0:
            raise ValueError(
                f"{name} brake reaches r={reach:.1f} inside a barrel bore of "
                f"{barrel_r:.1f} -- it would foul the rim"
            )


# Barrel bores come straight off the rim specs in ``wheels.py``
# (``bore_r - 9`` is the narrowest point of each barrel): 251.7 front, 264.4
# rear.  They are written out rather than imported so the brake package never
# depends on a sibling part module.
FRONT_BARREL_R = 251.7                      # 21 in rim
REAR_BARREL_R = 264.4                       # 22 in rim


FRONT = Axle(
    name="front",
    barrel_r=FRONT_BARREL_R,
    disc_r=220.0,                           # 440 mm: 87 % of the barrel bore
    disc_ir=124.0,
    disc_t=38.0,
    plate_t=10.0,
    n_vane=30,
    streaks=(20, 6, 10.0),
    hub_face_z=46.0,
    cal_arc=86.0,
    cal_windows=((-26.0, 16.0), (26.0, 16.0)),
    pistons=((-27.0, 19.5), (-9.0, 22.5), (9.0, 22.5), (27.0, 20.0)),
    clock_deg=148.0,
)

REAR = Axle(
    name="rear",
    barrel_r=REAR_BARREL_R,
    disc_r=228.0,                           # 456 mm: 86 % of the barrel bore
    disc_ir=128.0,
    disc_t=34.0,
    plate_t=9.0,
    n_vane=28,
    streaks=(18, 5, 9.0),
    hub_face_z=44.0,
    cal_arc=70.0,
    cal_windows=((-21.0, 14.0), (21.0, 14.0)),
    pistons=((-21.0, 21.0), (0.0, 23.0), (21.0, 21.5)),
    clock_deg=36.0,
)


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def _cyl(radius, z0, z1, x=0.0, y=0.0):
    """Cylinder spanning z0..z1 (``Cylinder`` itself is centred on its origin)."""
    return Pos(x, y, (z0 + z1) / 2.0) * Cylinder(radius=radius, height=abs(z1 - z0))


def _ring(r_out, r_in, z0, z1):
    """Annular slab between two Z planes."""
    return Pos(0, 0, z0) * extrude(Circle(r_out) - Circle(r_in), amount=z1 - z0)


def _polar(r, deg):
    a = math.radians(deg)
    return r * math.cos(a), r * math.sin(a)


def _radial_cyl(radius, r0, r1, z, deg):
    """Cylinder whose axis runs radially outward at ``deg``, from r0 to r1."""
    body = Location(((r0 + r1) / 2.0, 0, z), (0, 90, 0)) * Cylinder(
        radius=radius, height=abs(r1 - r0)
    )
    return Rot(0, 0, deg) * body


def _half_space(p1, p2, keep, size=700.0):
    """Solid filling the side of the line p1-p2 that ``keep`` is NOT on.

    Used to neck the caliper's ends: a straight cut in the disc plane, through
    the caliper's full width.
    """
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length
    if (keep[0] - p1[0]) * nx + (keep[1] - p1[1]) * ny < 0:
        nx, ny = -nx, -ny
    cx = (p1[0] + p2[0]) / 2.0 - nx * size / 2.0
    cy = (p1[1] + p2[1]) / 2.0 - ny * size / 2.0
    deg = math.degrees(math.atan2(ny, nx))
    return Location((cx, cy, 0), (0, 0, deg)) * Box(size, size, 500.0)


def _try_fillet(sketch, radius):
    try:
        return fillet(sketch.vertices(), radius)
    except Exception:  # pragma: no cover - kernel dependent
        return sketch


def _arc_solid(r_in, r_out, z0, z1, arc, centre_deg=0.0):
    """Sector of an annulus: revolve a rectangle in (r, z) about the axis."""
    return _arc_profile(
        [(r_in, z0), (r_out, z0), (r_out, z1), (r_in, z1)], arc, centre_deg
    )


def _arc_profile(points, arc, centre_deg=0.0):
    """Sector swept from an arbitrary closed (r, z) profile."""
    face = make_face(Polyline(*points, close=True))
    solid = revolve(Plane.XZ * face, axis=Axis.Z, revolution_arc=arc)
    return Rot(0, 0, centre_deg - arc / 2.0) * solid


# ---------------------------------------------------------------------------
# the disc
# ---------------------------------------------------------------------------


def _drill_cutter(ax):
    """Every cross-drilled hole, cut in a single boolean.

    Real carbon-ceramic discs are not drilled on a uniform polar grid -- the
    holes run in short swept groups with clean friction band between them.
    That grouping is what stops the pattern reading as polka dots, so the holes
    are laid out as ``groups`` streaks of ``per`` holes, each streak sweeping
    tangentially as it climbs the band.
    """
    groups, per, sweep = ax.streaks
    r0, r1 = ax.swept_ri + 5.5, ax.swept_ro - 5.5
    tools = []
    depth = ax.T + 10.0
    for g in range(groups):
        base = g * 360.0 / groups
        for k in range(per):
            t = k / (per - 1.0)
            x, y = _polar(r0 + (r1 - r0) * t, base + sweep * (t - 0.5))
            tools.append(Pos(x, y, 0) * Cylinder(radius=3.9, height=depth))
    return tools


def _edge_chamfer(ax):
    """45 deg break on both outboard corners of the disc's OD."""
    half = ax.T / 2.0
    out = []
    for sign in (1, -1):
        z_face = sign * (half + 0.6)
        z_back = sign * (half - 2.6)
        face = make_face(
            Polyline(
                (ax.R - 2.6, z_face),
                (ax.R + 3.0, z_face),
                (ax.R + 3.0, z_back),
                close=True,
            )
        )
        out.append(revolve(Plane.XZ * face, axis=Axis.Z, revolution_arc=360))
    return out


def _vane(ax, r0, half_in, half_out):
    face = make_face(
        Polyline(
            (r0, -half_in),
            (ax.R, -half_out),
            (ax.R, half_out),
            (r0, half_in),
            close=True,
        )
    )
    return Pos(0, 0, -ax.gap / 2.0) * extrude(face, amount=ax.gap)


def _band(ax, r_in, r_out):
    """Both friction plates of one radial band, as a single leaf shape."""
    half = ax.T / 2.0
    return _ring(r_out, r_in, half - ax.PT, half) + _ring(
        r_out, r_in, -half, -half + ax.PT
    )


def _disc_leaves(ax):
    """Three radial bands (the middle one drilled) plus the vane pattern.

    Splitting the plate into a swept band and two unswept rings is what a used
    carbon-ceramic disc actually looks like, and it gives the disc a graphic
    read through the spokes: bright polished band, dark rim, dark inner ring
    carrying the bronze bobbins.
    """
    chamfer = _edge_chamfer(ax)
    swept = _band(ax, ax.swept_ri, ax.swept_ro) - _drill_cutter(ax)
    leaves = [
        # the swept band is the brightest thing inside the wheel: a wide pale
        # ring on a dark disc is what makes the wheel read big at thumbnail
        style(swept, f"brake_disc:{ax.name}", P.DISC_FACE),
        style(
            _band(ax, ax.swept_ro, ax.R) - chamfer,
            f"disc_rim:{ax.name}",
            P.CARBON_GLOSS,
        ),
        style(
            _band(ax, ax.Ri, ax.swept_ri), f"disc_inner:{ax.name}", P.CARBON_GLOSS
        ),
    ]

    pitch = 360.0 / ax.n_vane
    long_proto = _vane(ax, ax.Ri + 3.0, 3.6, 2.5)
    short_proto = _vane(ax, (ax.Ri + ax.R) / 2.0, 3.2, 2.4)
    for k in range(ax.n_vane):
        a = k * pitch
        leaves.append(
            style(
                Rot(0, 0, a) * long_proto,
                f"disc_vane_long:{ax.name}_{k:02d}",
                P.CARBON,
            )
        )
        leaves.append(
            style(
                Rot(0, 0, a + pitch / 2.0) * short_proto,
                f"disc_vane_short:{ax.name}_{k:02d}",
                P.CARBON,
            )
        )
    return leaves


# ---------------------------------------------------------------------------
# the hat (bell) and its bobbins
# ---------------------------------------------------------------------------


def _hat(ax):
    z_face = ax.hub_face_z
    z_in = z_face - 10.0                    # inboard side of the mounting flange
    z_d0 = -ax.T / 2.0                      # against the disc's inboard plate
    z_d1 = z_d0 - 9.0

    profile = make_face(
        Polyline(
            (ax.hat_bore, z_face),
            (ax.hat_wall_o, z_face),
            (ax.hat_wall_o, z_d0),
            (ax.hat_or, z_d0),
            (ax.hat_or, z_d1),
            (ax.hat_wall_i, z_d1),
            (ax.hat_wall_i, z_in),
            (ax.hat_bore, z_in),
            close=True,
        )
    )
    profile = _try_fillet(profile, 4.0)
    hat = revolve(Plane.XZ * profile, axis=Axis.Z, revolution_arc=360)

    z_mid = (z_d0 + z_in) / 2.0
    cuts = [
        _radial_cyl(8.0, ax.hat_wall_i - 8.0, ax.hat_wall_o + 8.0, z_mid, k * 36.0)
        for k in range(10)
    ]
    # scalloped relief between the drive pegs -- the hat face is the one big
    # flat area the eye reaches through the wheel centre, so it gets machined
    cuts += [
        _cyl(11.0, z_face - 4.5, z_face + 2.0, *_polar(82.0, 54.0 + k * 72.0))
        for k in range(5)
    ]
    hat = hat - cuts
    # Deliberately darker than the friction band.  The swept ring has to be the
    # ONE bright thing inside the wheel; a bright hat as well gives the centre a
    # second pale mass that competes with it and shrinks the ring's read.
    return style(hat, f"brake_hat:{ax.name}", P.ALUMINIUM_DARK)


def _bobbins(ax):
    """Bronze drive bobbins clamping the disc to the hat flange."""
    out = []
    z_lo = -ax.T / 2.0 - 12.0
    z_hi = ax.T / 2.0 + 1.0
    shank = _cyl(6.5, z_lo, z_hi)
    head = _cyl(9.0, ax.T / 2.0 + 0.5, ax.T / 2.0 + 5.5)
    for k in range(12):
        x, y = _polar(ax.bobbin_r, 15.0 + k * 30.0)
        out.append(
            style(Pos(x, y, 0) * shank, f"disc_bobbin:{ax.name}_{k:02d}", P.BRONZE)
        )
        out.append(
            style(
                Pos(x, y, 0) * head,
                f"disc_bobbin_head:{ax.name}_{k:02d}",
                P.BRONZE_DARK,
            )
        )
    return out


# ---------------------------------------------------------------------------
# hub carrier / centre-lock spigot
# ---------------------------------------------------------------------------


def _hub(ax):
    z_face = ax.hub_face_z - 10.0           # the hat's inner flange seats here
    profile = make_face(
        Polyline(
            (26.0, z_face),
            (ax.carrier_r, z_face),
            (ax.carrier_r, -30.0),
            (98.0, -44.0),
            (98.0, -72.0),
            (74.0, -84.0),
            (26.0, -84.0),
            close=True,
        )
    )
    profile = _try_fillet(profile, 5.0)
    carrier = revolve(Plane.XZ * profile, axis=Axis.Z, revolution_arc=360)

    leaves = [
        style(carrier, f"hub_carrier:{ax.name}", P.ALUMINIUM_DARK),
        style(
            _cyl(58.0, z_face, ax.hub_face_z + 16.0),
            f"hub_spigot:{ax.name}",
            P.ALUMINIUM_DARK,
        ),
        style(
            _cyl(30.0, z_face, ax.hub_face_z + 26.0),
            f"hub_centre_lock:{ax.name}",
            P.TITANIUM,
        ),
    ]
    for k in range(5):
        x, y = _polar(72.0, 18.0 + k * 72.0)
        leaves.append(
            style(
                _cyl(6.5, ax.hub_face_z, ax.hub_face_z + 14.0, x, y),
                f"hub_drive_peg:{ax.name}_{k}",
                P.TITANIUM,
            )
        )
    return leaves


# ---------------------------------------------------------------------------
# monobloc caliper (built centred at local theta = 0)
# ---------------------------------------------------------------------------


def _caliper(ax):
    a, b = ax.half_w, ax.mouth
    profile = make_face(
        Polyline(
            (ax.cal_ri, -a),
            (ax.cal_ro, -a),
            (ax.cal_ro, a),
            (ax.cal_ri, a),
            (ax.cal_ri, b),
            (ax.cal_rb, b),
            (ax.cal_rb, -b),
            (ax.cal_ri, -b),
            close=True,
        )
    )
    profile = _try_fillet(profile, 4.0)
    body = revolve(Plane.XZ * profile, axis=Axis.Z, revolution_arc=ax.cal_arc)
    body = Rot(0, 0, -ax.cal_arc / 2.0) * body

    # piston bosses standing proud of each leg (fused before the ends are
    # necked, so a bore that reaches past the taper gets trimmed flush)
    r_boss = (ax.pad_ri + ax.pad_ro) / 2.0
    bosses = []
    for theta, bore in ax.pistons:
        x, y = _polar(r_boss, theta)
        for sign in (1, -1):
            bosses.append(
                Pos(x, y, sign * (a + 1.0))
                * Cone(
                    bottom_radius=bore if sign > 0 else bore - 3.5,
                    top_radius=bore - 3.5 if sign > 0 else bore,
                    height=6.0,
                )
            )
    body = body + bosses

    # bridge windows -- stopped short of the crown so a continuous outer rail
    # holds the silhouette together instead of the ends reading as broken teeth
    body = body - [
        _arc_solid(ax.cal_rb - 4.0, ax.cal_ro - 7.0, -a - 2.0, a + 2.0, w, c)
        for c, w in ax.cal_windows
    ]

    # neck the two ends in: a constant-depth sector reads as a lump of metal,
    # a caliper that tapers toward its mounts reads as a machined monobloc
    keep = _polar((ax.cal_ri + ax.cal_ro) / 2.0, 0.0)
    body = body - [
        _half_space(
            _polar(ax.cal_ri - 1.0, sign * ax.taper_deg),
            _polar(ax.cal_ro - 46.0, sign * (ax.cal_arc / 2.0 + 1.0)),
            keep,
        )
        for sign in (1, -1)
    ]

    # nameplate pocket in the crown, and the inboard mount ears
    add = [
        _cyl(16.0, ax.ear_z0, ax.ear_z1, *_polar(ax.ear_r, sign * ax.ear_ang))
        for sign in (1, -1)
    ]
    body = body + add
    body = body - _arc_solid(
        ax.cal_ro - 2.0, ax.cal_ro + 8.0, -a * 0.34, a * 0.34, ax.cal_arc * 0.30
    )

    leaves = [style(body, f"caliper:{ax.name}", P.CALIPER)]

    # pads, seen through the bridge windows
    pad_arc = ax.pad_arc
    for sign in (1, -1):
        z0 = sign * (ax.T / 2.0 + 1.0)
        z1 = z0 + sign * ax.pad_t
        z2 = z1 + sign * ax.back_t
        tag = "out" if sign > 0 else "in"
        leaves.append(
            style(
                _arc_solid(ax.pad_ri, ax.pad_ro, min(z0, z1), max(z0, z1), pad_arc),
                f"brake_pad:{ax.name}_{tag}",
                P.CARBON_GLOSS,
            )
        )
        leaves.append(
            style(
                _arc_solid(
                    ax.pad_ri + 4.0, ax.pad_ro - 3.0, min(z1, z2), max(z1, z2), pad_arc
                ),
                f"pad_backing:{ax.name}_{tag}",
                P.STEEL_DARK,
            )
        )

    # bleed nipple, off the crown centre so it clears the nameplate pocket
    bleed_at = ax.cal_arc * 0.34
    leaves.append(
        style(
            _radial_cyl(6.0, ax.cal_ro - 12.0, ax.cal_ro + 3.0, 0.0, bleed_at),
            f"caliper_bleed:{ax.name}",
            P.BRONZE_DARK,
        )
    )
    leaves.append(
        style(
            _radial_cyl(4.0, ax.cal_ro + 3.0, ax.cal_ro + 8.0, 0.0, bleed_at),
            f"caliper_bleed_cap:{ax.name}",
            P.TITANIUM,
        )
    )

    # brake line, inboard, clear of the bracket arms
    bx, by = _polar(ax.cal_ro - 32.0, -6.0)
    leaves.append(
        style(_cyl(9.0, -a + 2.0, -a - 14.0, bx, by), f"caliper_banjo:{ax.name}", P.BRONZE_DARK)
    )
    leaves.append(
        style(_cyl(5.0, -a - 12.0, -a - 44.0, bx, by), f"brake_hose:{ax.name}", P.CARBON)
    )

    leaves.extend(_caliper_bracket(ax))
    leaves.extend(_backing_shroud(ax))
    return leaves


def _backing_shroud(ax):
    """Carbon air guide closing the corner behind the disc.

    Two jobs, both of them about how the wheel READS rather than about brake
    cooling.  Radially it runs past the disc OD into the annulus the disc
    cannot reach, so the gap between disc and rim barrel stops being open
    daylight.  Axially it sits a few mm inboard of the disc's back plate, so
    the cross-drillings and the vane channels look into dark carbon instead of
    into background -- the difference between a disc that reads as a solid
    machined mass and one that reads as lace.

    Built in the CALIPER's local frame (caliper on centre at theta = 0), so the
    sector runs the long way round and the gap parks under the caliper.
    """
    z, ri, rm, ro = ax.shr_z, ax.shr_ri, ax.shr_rm, ax.shr_ro
    shell = 4.0

    # One closed (r, z) loop: dish outward and inboard under the disc, then
    # turn the outer flange back up toward the rim.  That turned lip is what
    # keeps the shroud from reading as a flat hole -- it catches a single thin
    # highlight right at the edge of the dark field.
    profile = [
        (ri, z),
        (rm, z - 9.0),
        (ro - 4.0, z - 4.0),
        (ro, z + 2.0),                      # flange tip, turned toward the rim
        (ro, z - 2.0),
        (ro - 4.0, z - 4.0 - shell),
        (rm, z - 9.0 - shell),
        (ri, z - shell),
    ]
    dish = _arc_profile(profile, ax.shr_arc, 180.0)
    return [style(dish, f"brake_shroud:{ax.name}", P.CARBON)]


def _caliper_bracket(ax):
    """Machined arm tying the caliper ears back to the hub carrier."""
    sketch = Circle(86.0)
    for sign in (1, -1):
        ea = sign * ax.ear_ang
        n = (-math.sin(math.radians(ea)), math.cos(math.radians(ea)))
        ex, ey = _polar(ax.ear_r, ea)
        p_a = _polar(84.0, ea - 26.0)
        p_b = _polar(84.0, ea + 26.0)
        p_c = (ex + 22.0 * n[0], ey + 22.0 * n[1])
        p_d = (ex - 22.0 * n[0], ey - 22.0 * n[1])
        sketch = sketch + make_face(Polyline(p_a, p_d, p_c, p_b, close=True))
        sketch = sketch + Pos(ex, ey) * Circle(21.0)

    plate = Pos(0, 0, ax.brk_z0) * extrude(sketch, amount=ax.brk_z1 - ax.brk_z0)
    leaves = [style(plate, f"caliper_bracket:{ax.name}", P.ALUMINIUM_DARK)]
    for sign in (1, -1):
        x, y = _polar(ax.ear_r, sign * ax.ear_ang)
        leaves.append(
            style(
                _cyl(9.0, ax.brk_z0 - 4.0, ax.brk_z0 + 1.0, x, y),
                f"caliper_bolt:{ax.name}_{'a' if sign > 0 else 'b'}",
                P.TITANIUM,
            )
        )
    return leaves


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------


def _rotor_prototype(ax):
    kids = _disc_leaves(ax) + [_hat(ax)] + _bobbins(ax) + _hub(ax)
    return Compound(children=kids, label=f"brake_rotor_{ax.name}")


def _caliper_prototype(ax):
    return Compound(children=_caliper(ax), label=f"brake_caliper_{ax.name}")


def _corner_locations():
    """(axle, corner_name, rotor_location, caliper_location) per corner.

    ``Rot(-90, 0, 0)`` sends local +Z to global +Y and ``Rot(90, 0, 0)`` sends
    it to global -Y, so local +Z is outboard on both sides while local +X stays
    car-forward.  That makes local +Y point DOWN on the left and UP on the
    right, so a caliper wanted at global clock angle ``phi`` (measured from +X
    toward +Z) is built at local ``-phi`` on the left and ``+phi`` on the right.
    """
    out = []
    for x, y, z, _tr, _tw, _rd in S.wheel_centres():
        front = x > 0
        ax = FRONT if front else REAR
        side = 1 if y > 0 else -1
        name = "{}_{}".format(
            "front" if front else "rear", "left" if side > 0 else "right"
        )
        base = Location((x, y, z), (-90 if side > 0 else 90, 0, 0))
        clock = -ax.clock if side > 0 else ax.clock
        out.append((ax, name, base, base * Rot(0, 0, clock)))
    return out


def build():
    protos = {}
    instances = []
    for ax, name, rotor_loc, cal_loc in _corner_locations():
        if ax.name not in protos:
            protos[ax.name] = (_rotor_prototype(ax), _caliper_prototype(ax))
        rotor, caliper = protos[ax.name]
        instances.append((rotor, rotor_loc, f"brake_rotor:{name}"))
        instances.append((caliper, cal_loc, f"brake_caliper:{name}"))
    return compound_from_instances("brakes", instances)
