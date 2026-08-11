"""F-14D -- the two F110-GE-400 convergent-divergent exhaust nozzles.

Everything here is a body of revolution, or a SECTOR of one, about the engine
axis at ``(y = +-G.Y_NACELLE, z = G.nacelle(x)[3] == 0)``.  Building the petals
as revolved sectors rather than lofted plates is what keeps them exactly
conformal to the nozzle cone: every petal, seal and liner shares one meridional
radius law, so the ring closes on itself with no gaps and no lofting artefacts,
and the only thing that distinguishes a petal from the seal beside it is its
angular width and its radial offset.

State: PARKED, engines off.  With hydraulic pressure gone the F110 nozzle
relaxes to the fully OPEN position, so the external petals lie almost parallel
to the axis -- a shallow 6-8 deg cone with a knuckle just aft of the hinge --
rather than the steep cone of a nozzle at mil power.  That is what makes a
parked Tomcat's exhausts read as two big open holes.

The ring is flaps AND seals, not 18 plates butted edge to edge.  18 external
flaps at 13.6 deg of the 20 deg pitch leave a 6.4 deg gap; an external SEAL,
dropped 32 mm radially inboard, bridges each gap and tucks 6.6 deg UNDER the
flap edge on both sides.  That is the real overlap, and it is what turns the
nozzle into a scalloped ring of overlapping plates instead of a cone.  The
divergent ring inside is built the same way, so the throat reads as an iris of
individual plates too.

Depth is built, not painted.  Looking in you pass the external flap lip, the
seal shell, the 18 divergent flaps flaring out of the throat, the throat
itself, and then 0.8 m of afterburner interior -- liner, flameholder ring,
radial gutters -- going to black.
"""

from __future__ import annotations

from build123d import (Axis, Box, Line, Location, Plane, Solid, Spline, Vector,
                       Wire, make_face)

from cadgen import compound_from_instances

from f14_parts import geometry as G
from f14_parts import sections as SEC
from f14_parts.airframe import stance
from f14_parts.context import group
from f14_parts import palette as P

M = G.M
Y_NAC = G.Y_NACELLE
X_SKIN = SEC.X_SKIN_AFT                 # 18.300 m -- where the one-piece skin stops
X_EXIT = G.LENGTH                       # 19.110 m -- the exit plane
PITCH = 360.0 / G.NOZZLE_PETALS         # 20 deg

# ---------------------------------------------------------------------------
# the meridional radius laws
# ---------------------------------------------------------------------------

# External flap OUTER surface.  Anchored at both ends on numbers that are not
# mine to choose: it leaves the shroud at the nacelle's own radius and lands on
# G.nacelle(LENGTH) = 0.585 m at the exit plane, so the aft silhouette is still
# the one geometry.py publishes.  The interior spacing is the OPEN position:
# steepest immediately aft of the hinge (the knuckle), then flattening to under
# 6 deg at the lip.  Its inner face lands on G.NOZZLE_R_EXIT.
PETAL_R = [
    (18620.0, 654.0), (18680.0, 641.0), (18780.0, 626.0),
    (18900.0, 611.0), (19010.0, 598.0), (19110.0, 588.0),
]
PETAL_T = 28.0                          # flap thickness; exit inner face = 560 mm

# The seal is 19.6 deg of the 20 deg pitch, not the 10 deg the gap needs, and it
# does two jobs for it.  From OUTSIDE it is the dark strip in each 6.4 deg gap,
# tucked 6.6 deg under both neighbouring flaps -- the overlap.  From INSIDE the
# eighteen of them close up into a near-continuous dark shell that hides the
# flaps' lit inner faces, which is what a nozzle's cooling cavity actually looks
# like.  A 10 deg seal left that cavity open, and a cream-lit wall 300 mm inside
# the lip destroys the depth the whole part is built for.
SEAL_ARC = 19.6
SEAL_DROP = 32.0                        # seal outer face below the flap outer
SEAL_T = 16.0

X_HINGE = 18620.0                       # external flaps pick up here
X_TIP_SPLICE = 19008.0                  # flap tip section (heat-darkened)
X_SEAL_0 = 18664.0                      # seals start clear of the shroud lip
X_SEAL_1 = 19088.0                      # ... and stop short, so the lip scallops

PETAL_ARC = 13.6                        # deg of the 20 deg pitch

# Divergent (inner) flaps, by their OUTER surface, which is held just inside the
# seal shell so the cooling cavity stays a slot rather than a room.  The gas side
# is 16 mm in: convergent to a throat at 18.93 m, then the shallow flare of a
# fully open nozzle.  The aft edge stops 30 mm short of the external lip, so the
# lip overhangs it and the eye gets a hard depth cue.
DIV_R = [
    (18660.0, 578.0), (18790.0, 522.0), (18900.0, 478.0),
    (18980.0, 494.0), (19086.0, 528.0),
]
DIV_T = 20.0
DIV_ARC = 17.2
DIV_SEAL_ARC = 8.0

# Convergent primary-flap liner: out of the engine bay to the divergent flaps.
# Its OUTER surface is deliberately fatter than the shroud's bore so the two
# interpenetrate and leave no annulus for light to get into.
LINER_R = [
    (18305.0, 596.0), (18450.0, 590.0), (18560.0, 582.0), (18680.0, 570.0),
]
LINER_T = 24.0

X_SHROUD_0 = 18330.0
X_SHROUD_1 = 18660.0
SHROUD_BORE = [(18330.0, 610.0), (18660.0, 588.0)]

X_JOINT_0 = 18255.0
X_JOINT_1 = 18345.0
R_JOINT = 653.0                         # ~14 mm proud of the skin at the break

X_SYNC_0 = 18578.0
X_SYNC_1 = 18672.0
R_SYNC = 669.0

R_ACT = 676.0                           # hydraulic actuator centreline radius
ACT_AZ = (45.0, 135.0, 225.0, 315.0)


def _lin(a, b, n):
    return [a + (b - a) * i / (n - 1) for i in range(n)]


def _petal_r(x):
    return G._curve(PETAL_R, x)


def _div_r(x):
    return G._curve(DIV_R, x)


def _liner_r(x):
    return G._curve(LINER_R, x)


def _nac_r(x):
    """Outer radius of the nacelle at x -- the surface the nozzle leaves."""
    return G.nacelle(x)[1]


# ---------------------------------------------------------------------------
# revolution helpers.  Profiles are (x, r) in the meridional half-plane and are
# revolved about Axis.X; the caller then translates onto the nacelle axis.
# ---------------------------------------------------------------------------


def _profile_face(outer, inner):
    """Closed meridional profile from an OUTER and an INNER contour.

    Both contours run forward -> aft; the ends are closed with straight radial
    lines, which is what gives the flaps their crisp blunt lip.  Contours of
    three points or more become a Spline so the revolved surface has no facets
    and the edge overlay has nothing spurious to draw.
    """
    def contour(pts):
        vs = [Vector(x, 0.0, r) for x, r in pts]
        return (Spline(*vs).edge() if len(vs) > 2 else Line(vs[0], vs[-1]).edge()), vs

    e_out, vo = contour(outer)
    e_in, vi = contour(inner)
    # A contour that closes ON the axis (a cone, a capped plug) meets its
    # partner at a point, and asking for that zero-length closing line is a
    # BRep_API failure, not a degenerate-but-valid edge.  Skip it; the wire is
    # already closed there.
    edges = [e_out]
    if (vo[-1] - vi[-1]).length > 1e-6:
        edges.append(Line(vo[-1], vi[-1]).edge())
    edges.append(e_in)
    if (vi[0] - vo[0]).length > 1e-6:
        edges.append(Line(vi[0], vo[0]).edge())
    return make_face(Wire(edges))


def _revolve(outer, inner, arc=360.0):
    """Solid of revolution, or a sector CENTRED on the +Z meridian."""
    solid = Solid.revolve(_profile_face(outer, inner), arc, Axis.X)
    if arc < 359.9:
        solid = Location((0, 0, 0), (-0.5 * arc, 0, 0)) * solid
    return solid


def _band(x0, x1, r_out, r_in):
    """A plain rectangular-section ring."""
    return _revolve([(x0, r_out), (x1, r_out)], [(x0, r_in), (x1, r_in)])


def _rod(p0, p1, radius):
    """A cylinder between two meridional points (x, r), in the +Z meridian."""
    a = Vector(p0[0], 0.0, p0[1])
    b = Vector(p1[0], 0.0, p1[1])
    d = b - a
    return Solid.make_cylinder(radius, d.length,
                               Plane(origin=a, z_dir=d.normalized()))


# ---------------------------------------------------------------------------
# the parts
# ---------------------------------------------------------------------------


def _joint_ring():
    """The nozzle-to-nacelle attach collar, standing proud where the skin ends.

    It is deliberately fatter than the shroud behind it: the collar is the
    structural break -- the shroud is bolted to the engine bay, not lofted with
    the fuselage -- and a ring proud of the skin is what a Tomcat has there.
    Its bore also caps the skin loft's flat aft face, which would otherwise be a
    grey disc visible straight down the nozzle.
    """
    outer = [(X_JOINT_0, 630.0), (X_JOINT_0 + 18.0, R_JOINT),
             (X_JOINT_1 - 16.0, R_JOINT), (X_JOINT_1, 632.0)]
    inner = [(X_JOINT_0, 598.0), (X_JOINT_1, 598.0)]
    return _revolve(outer, inner)


def _shroud():
    """The fixed shroud: nacelle radius at the collar, tapering to the hinge."""
    xs = _lin(X_SHROUD_0, X_SHROUD_1, 7)
    outer = [(x, _nac_r(x)) for x in xs]
    return _revolve(outer, SHROUD_BORE)


def _sync_ring():
    """The actuator/synchronising ring the external-flap links hang off."""
    outer = [(X_SYNC_0, 650.0), (X_SYNC_0 + 16.0, R_SYNC),
             (X_SYNC_1 - 16.0, R_SYNC), (X_SYNC_1, 648.0)]
    inner = [(X_SYNC_0, 614.0), (X_SYNC_1, 610.0)]
    return _revolve(outer, inner)


def _liner():
    """Convergent primary-flap liner, engine bay down to the divergent flaps."""
    xs = _lin(LINER_R[0][0], LINER_R[-1][0], 7)
    inner = [(x, _liner_r(x)) for x in xs]
    outer = [(x, r + LINER_T) for x, r in inner]
    return _revolve(outer, inner)


def _engine_dark():
    """The black the nozzle bottoms out in, 0.8 m down from the exit plane.

    Also the cap over the skin loft's flat aft face, which is grey and which
    the throat looks straight at.
    """
    return _band(18296.0, 18368.0, 604.0, 0.0)


def _flame_ring(x0, r_in, r_out):
    """One flameholder gutter ring.

    There are two, at different stations AND different radii, because two
    circles seen at two depths read as a tunnel while one circle reads as a
    target.  Both are small and well back: a big crisp circle at one station is
    a clock face at whole-aircraft scale, and a clock face inside the exhaust
    destroys the depth this whole part exists to build.
    """
    return _band(x0, x0 + 30.0, r_out, r_in)


def _petal(x0=X_HINGE, x1=X_TIP_SPLICE):
    """One external flap: a tapered sector plate on the open-nozzle cone."""
    xs = _lin(x0, x1, 8)
    outer = [(x, _petal_r(x)) for x in xs]
    inner = [(x, _petal_r(x) - PETAL_T) for x in xs]
    return _revolve(outer, inner, PETAL_ARC)


def _petal_tip():
    """The last 100 mm of each flap, as its own body so it can carry the burn.

    A nozzle is not one tone: the flap tips run hundreds of degrees hotter than
    their roots and come back from a cruise noticeably darker and browner.  A
    separate tip body gets that for the price of one more instance ring, and
    the splice line it leaves across each flap is a real one.
    """
    return _petal(X_TIP_SPLICE - 4.0, X_EXIT)


def _petal_seal():
    """One external seal: dropped 32 mm, tucked 6.6 deg under both flaps."""
    xs = _lin(X_SEAL_0, X_SEAL_1, 7)
    outer = [(x, _petal_r(x) - SEAL_DROP) for x in xs]
    inner = [(x, _petal_r(x) - SEAL_DROP - SEAL_T) for x in xs]
    return _revolve(outer, inner, SEAL_ARC)


def _div_flap():
    xs = _lin(DIV_R[0][0], DIV_R[-1][0], 6)
    outer = [(x, _div_r(x)) for x in xs]
    inner = [(x, r - DIV_T) for x, r in outer]
    return _revolve(outer, inner, DIV_ARC)


def _div_seal():
    """Sits just OUTBOARD of the divergent flaps, so the throat reads as 18
    lit plates separated by hairline shadow, not as a plain cone."""
    xs = _lin(DIV_R[0][0] + 20.0, DIV_R[-1][0], 6)
    inner = [(x, _div_r(x) - 4.0) for x in xs]
    outer = [(x, r + 12.0) for x, r in inner]
    return _revolve(outer, inner, DIV_SEAL_ARC)


def _drive_link():
    """Sync ring -> external flap: a rod with a clevis at the flap end.

    Short.  A link that runs most of the flap's length reads as a stiffening
    rib and turns the petal ring into a radiator; the real one picks up just
    aft of the hinge.  Fused rather than left as separate bodies so the
    prototype is ONE leaf and the instance ring stays one occurrence per link.
    """
    rod = _rod((18664.0, 660.0), (18856.0, 630.0), 9.0)
    aft = Location((18854.0, 0.0, 620.0)) * Box(36.0, 20.0, 34.0)
    return rod + aft


def _actuator_body():
    return _rod((18368.0, R_ACT), (18540.0, R_ACT), 44.0)


def _actuator_rod():
    """Piston out of the actuator into the sync ring, plus its trunnion."""
    piston = _rod((18534.0, R_ACT), (18628.0, 664.0), 16.0)
    lug = Location((18624.0, 0.0, 664.0)) * Box(38.0, 26.0, 44.0)
    return piston + lug


def _fastener():
    return _rod((18300.0, R_JOINT - 6.0), (18300.0, R_JOINT + 4.0), 7.0)


def _turbine_strut():
    """One turbine rear-frame strut, right against the back wall.

    24 fine ones, not 12 fat ones.  At whole-aircraft scale the nozzle is about
    110 px across, so a dozen chunky radials land as clock ticks; two dozen thin
    ones fall below the spacing the eye resolves and read as texture in shadow,
    which is what an engine 0.75 m down a black hole should look like.  They
    stop short of the axis so there is no hub.
    """
    return Location((18382.0, 0.0, 212.0)) * Box(14.0, 11.0, 188.0)


# ---------------------------------------------------------------------------
# placement
# ---------------------------------------------------------------------------

SIDES = ((1, "port"), (-1, "stbd"))


def _both(make, role, colour):
    """One fresh body of revolution per nacelle.

    ``make`` must build a NEW shape each call: ``Compound(children=...)``
    reparents, so one object cannot live on both sides.
    """
    out = []
    for side, tag in SIDES:
        shape = Location((0.0, side * Y_NAC, 0.0)) * make()
        out.append(P.style(shape, f"{role}:{tag}", colour))
    return out


def _ring(proto, role, colour, angles, name=None):
    """One instanced ring of ``proto``, both nacelles, sharing the prototype.

    Every angle set used here is closed under negation (k*PITCH and
    (k+0.5)*PITCH both are), so placing the SAME prototype at +Y and -Y with the
    same rotation gives two rings that are exact mirror images.
    """
    P.style(proto, role, colour)
    items = []
    for side, tag in SIDES:
        base = Location((0.0, side * Y_NAC, 0.0))
        for i, a in enumerate(angles):
            items.append((proto, base * Location((0, 0, 0), (a, 0.0, 0.0)),
                          f"{role}:{tag}_{i:02d}"))
    return compound_from_instances(name or f"{role}_ring", items)


def build():
    """Return ONE labelled group Compound, already in world position."""
    petal_az = [i * PITCH for i in range(G.NOZZLE_PETALS)]
    seal_az = [(i + 0.5) * PITCH for i in range(G.NOZZLE_PETALS)]

    kids = []
    # --- structure, forward to aft ---------------------------------------
    # Every tone here is DARKER and warmer than the airframe's FS 36320
    # blue-grey.  The nozzle is the one place on a Tomcat where the metal is
    # bare and heat-tinted, and painting it airframe-grey is what makes a model
    # look like it has plastic exhausts.
    kids += _both(_joint_ring, "nozzle_joint_ring", P.STEEL_BURN)
    kids += _both(_shroud, "nozzle_shroud", P.STEEL_BURN)
    kids += _both(_sync_ring, "nozzle_sync_ring", P.STEEL_DARK)
    kids.append(_ring(_fastener(), "nozzle_joint_bolt", P.STEEL_DARK,
                      [i * 10.0 for i in range(36)]))

    # --- actuation --------------------------------------------------------
    kids.append(_ring(_actuator_body(), "nozzle_actuator", P.HYDRAULIC, ACT_AZ))
    kids.append(_ring(_actuator_rod(), "nozzle_actuator_rod", P.OLEO_CHROME, ACT_AZ))
    kids.append(_ring(_drive_link(), "nozzle_petal_link", P.STEEL_DARK, petal_az))

    # --- the petal ring ---------------------------------------------------
    kids.append(_ring(_petal(), "nozzle_petal", P.NOZZLE_PETAL, petal_az))
    kids.append(_ring(_petal_tip(), "nozzle_petal_tip", P.STEEL_BURN, petal_az))
    kids.append(_ring(_petal_seal(), "nozzle_petal_seal", P.EXHAUST_SOOT, seal_az))

    # --- what you see down the hole --------------------------------------
    kids.append(_ring(_div_flap(), "nozzle_inner_petal", P.NOZZLE_INNER, petal_az))
    kids.append(_ring(_div_seal(), "nozzle_inner_seal", P.EXHAUST_SOOT, seal_az))
    kids += _both(_liner, "nozzle_liner", P.EXHAUST_SOOT)
    kids += _both(lambda: _flame_ring(18540.0, 398.0, 422.0),
                  "flameholder_aft", P.ENGINE_HOT)
    kids += _both(lambda: _flame_ring(18398.0, 268.0, 290.0),
                  "flameholder_fwd", P.ENGINE_HOT)
    kids.append(_ring(_turbine_strut(), "turbine_strut", P.ENGINE_HOT,
                      [i * 15.0 for i in range(24)]))
    kids += _both(_engine_dark, "engine_interior", P.ENGINE_HOT)

    return stance(group("nozzles", kids))


if __name__ == "__main__":
    import time

    t0 = time.time()
    grp = build()
    print(f"build {time.time() - t0:5.2f}s   children {len(grp.children)}")
    bb = grp.bounding_box()
    print(f"bbox x {bb.min.X/M:7.3f}..{bb.max.X/M:7.3f}  "
          f"y {bb.min.Y/M:7.3f}..{bb.max.Y/M:7.3f}  "
          f"z {bb.min.Z/M:7.3f}..{bb.max.Z/M:7.3f}")
    for x in (X_HINGE, 18800.0, X_EXIT):
        print(f"  petal r @ {x/M:6.3f} = {_petal_r(x):6.1f}   "
              f"nacelle r = {_nac_r(x):6.1f}")
