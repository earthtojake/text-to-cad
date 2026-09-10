"""Sculpted open phalanx frames. Local finger axis +Y; pin axes +X.

Each factory returns ONE skeletal aluminum body. Proximal eyes are keyed
drive connections; distal eyes house the next joint bearings. Both sides are tied by bowed dorsal ribs outside the central
longitudinal tendon lanes. `distal=True` replaces the outboard joint with a
rounded tip bridge and two bored pad/nail seats.
"""
from math import sqrt

from cadgen import build123d as bd, srgb


def _swept_rib(points, radius=.66):
    path = bd.Edge.make_bezier(*points)
    # Ribbon section: full width across the finger axis, shallow thickness
    # within the rail. This seats completely on the rounded thin-wall root.
    section = bd.Plane(origin=path.position_at(0), x_dir=(0,1,0),
                       z_dir=path.tangent_at(0)) * bd.Ellipse(radius,.32)
    return bd.sweep(section, path=path)


def _outline(length,r0,r1,bow):
    edges=[bd.Edge.make_bezier((0,r0,0),(length*.30,bow,0),(length*.70,bow,0),(length,r1,0)),
           bd.Edge.make_three_point_arc((length,r1,0),(length+r1,0,0),(length,-r1,0)),
           bd.Edge.make_bezier((length,-r1,0),(length*.70,-bow,0),(length*.30,-bow,0),(0,-r0,0)),
           bd.Edge.make_three_point_arc((0,-r0,0),(-r0,0,0),(0,r0,0))]
    return bd.Wire(edges)

def _window(length,inset,bow):
    return bd.Wire([
        bd.Edge.make_bezier((inset,0,0),(inset,bow,0),(length-inset,bow,0),(length-inset,0,0)),
        bd.Edge.make_bezier((length-inset,0,0),(length-inset,-bow,0),(inset,-bow,0),(inset,0,0)),
    ])

def _drive_bore(radius, flat):
    """Exact D profile in native sketch XY, flat normal +sketch X.

    After the frame transform this normal is finger +Y; the bore axis is X.
    The arc has radius `radius`, while the shared torque-contact plane stays
    exactly at `flat`, including for shafts with circumference clearance.
    """
    chord_half=sqrt(radius*radius-flat*flat)
    top=(flat,chord_half,0)
    bottom=(flat,-chord_half,0)
    wire=bd.Wire([bd.Edge.make_three_point_arc(top,(-radius,0,0),bottom),
                  bd.Edge.make_line(bottom,top)])
    return bd.Pos(0,0,-1)*bd.extrude(bd.Face(wire),amount=3.45,dir=(0,0,1))


def make_phalanx(length=45., width=18., distal=False, label='skeletal_proximal_phalanx',
                 bearing_radius=2.53, eye_radius=3.55,
                 drive_bore_radius=1.03, drive_bore_flat=.75):
    """Closed watertight frame; y=0 and y=length are joint datums.

    Outside nominal width = width; eye center x=±(width/2−0.725).
    Ring axial thickness 1.45, O.D.7.1. The y=0 eye has an integral D bore:
    radius 1.03, flat at y=+0.75 (normal +Y), axis X. Native sketch +X maps
    to finger +Y and native sketch +Y maps to finger +Z. The y=length eye
    retains the circular Ø5.06 bearing seat. End rims have a 0.10 fillet;
    the keyed flat has 1.25 mm of full contact length across each 1.45 mm eye.
    For terminal links, tip bridge center y=length−1.6 and no distal axis.
    """
    if length < 14 or width < 11:
        raise ValueError(f'{label}: phalanx family requires length≥14 and width≥11 mm')
    if not 0 < drive_bore_flat < drive_bore_radius < eye_radius:
        raise ValueError(f'{label}: drive bore requires 0 < flat < radius < eye radius')
    x = width/2-.725
    pieces=[]
    for sign in (-1,1):
        sx=sign*x
        if distal:
            outer=_outline(length-1.6,eye_radius,2.1,4.15)
            inner=_window(length-1.6,3.55,3.45)
        else:
            outer=_outline(length,eye_radius,eye_radius,4.85)
            inner=_window(length,3.8,4.35)
        plate=bd.extrude(bd.Face(outer,[inner]),amount=1.45,dir=(0,0,1))
        # Finish the established circular frame first. Key the proximal eye
        # only after the peripheral root blends, avoiding a kernel-dependent
        # change in the remote blend's face splitting caused by the D corners.
        for cy in ([0] if distal else [0,length]):
            plate=plate-(bd.Pos(cy,0,.725)*bd.Cylinder(bearing_radius,4))
        plate=bd.fillet(plate.edges(),.20)
        # Sketch XY => phalanx YZ, extrusion => X.
        plate=bd.Pos(sx-.725,0,0)*bd.Rot(0,0,90)*bd.Rot(90,0,0)*plate
        pieces.append(plate)
    # Dorsal arches join the side load paths. They sit below the tendon lanes,
    # their bowed cross section remaining visually light from both sides.
    for fraction in ((.56,) if distal else (.32,.70)):
        y=length*fraction
        zside=-3.12 if distal else -3.80
        # Meet the rail normal to its planar inner face. The earlier near-
        # vertical entry grazed the rounded rail rim, creating sliver edges on
        # narrower variants that no practical root fillet could follow.
        zcontrol=(-6.55-.375*zside)/.625
        pieces.append(_swept_rib([(-x+.1,y,zside),(-x+1.15,y,zside),
                                 (-x+1.8,y,zcontrol),(x-1.8,y,zcontrol),
                                 (x-1.15,y,zside),(x-.1,y,zside)],.54))
    # Discrete mounting seats, bored through their thickness, lie peripherally.
    if distal:
        for sign in (-1,1):
            bx=sign*(x-.10)
            seat=bd.Cylinder(1.30,1.45)-bd.Cylinder(.56,3.45)
            seat=bd.fillet(seat.edges(),.13)
            pieces.append(bd.Pos(bx,length*.71,2.6)*seat)
    shape=pieces[0]
    for piece in pieces[1:]:
        shape=shape.fuse(piece)
    if len(shape.solids()) != 1:
        raise ValueError(f'{label}: frame must be one solid, found {len(shape.solids())}; bounds={[str(s.bounding_box()) for s in shape.solids()]}')
    # Root fillets turn each dorsal arch smoothly into the peripheral rails.
    roots=[e for e in shape.edges()
           if e.geom_type in (bd.GeomType.BSPLINE,bd.GeomType.ELLIPSE)
           and .7<e.length<5 and abs(e.center().X)>x-1.0
           and e.center().Z < -2.5
           and any(abs(e.center().Y-length*f)<.8
                   for f in ((.56,) if distal else (.32,.70)))]
    if not roots:
        raise ValueError(f'{label}: no dorsal-arch root edges found for blending')
    root_radius=.06 if distal else .12
    try:
        shape=bd.fillet(roots,root_radius)
    except ValueError as exc:
        raise ValueError(f'{label}: dorsal-arch root blend failed '
                         f'(length={length}, width={width}, distal={distal}, '
                         f'edge_count={len(roots)}): {exc}') from exc
    if distal:
        # Continue the same pad-bore axes dorsally for the nail inserts.
        # Re-open the mounting bores through both the boss and rail after the
        # union; subtracting from the boss alone would leave the rail as a plug.
        for sign in (-1,1):
            shape=shape-(bd.Pos(sign*(x-.10),length*.71,2.6)*bd.Cylinder(.56,16.5))
    # These cores fuse into the parent body, producing an integral aluminum
    # eye, not a separate bearing or sleeve. Cover the old bore's entry round
    # entirely while leaving every external eye and rail surface unchanged.
    for sign in (-1,1):
        placement=bd.Pos(sign*x-.725,0,0)*bd.Rot(0,0,90)*bd.Rot(90,0,0)
        core=bd.Pos(0,0,.725)*bd.Cylinder(bearing_radius+.25,1.45)
        shape=shape.fuse(placement*core)
        shape=shape-(placement*_drive_bore(drive_bore_radius,drive_bore_flat))
    # Round only entry rims, retaining the exact torque-contact flat and the
    # longitudinal D corners through the full working contact band.
    bore_rims=[e for e in shape.edges()
               if e.bounding_box().size.X < 1e-6
               and abs(e.center().Y)<drive_bore_radius+.01
               and abs(e.center().Z)<drive_bore_radius+.01
               and e.length<2*3.141593*drive_bore_radius]
    if len(bore_rims)!=8:
        raise ValueError(f'{label}: expected eight D-bore rim edges, found {len(bore_rims)}')
    try:
        shape=bd.fillet(bore_rims,.10)
    except ValueError as exc:
        raise ValueError(f'{label}: D-bore entry rim fillet failed: {exc}') from exc
    shape.label=label
    shape.color=srgb('#a9b7c1')
    shape.cad_material={'roughness':.34,'metalness':.86,'clearcoat':.12}
    if not shape.is_valid or shape.volume <=0:
        raise ValueError(f'{label}: invalid or nonpositive frame')
    return shape
