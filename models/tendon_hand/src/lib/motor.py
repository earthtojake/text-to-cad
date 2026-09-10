"""Unbranded 13.6 mm miniature motor, native output axis +Z.

Case: Z=0..17.25, maximum radius 6.8. Endcap seating face Z=17.30,
finished face Z=18; recessed pilot Z=16.30..17.30. Shaft Z=.80..20.
The .05 case/endcap reveal is deliberate. Three M1 clearance/counterbore
locations on radius 5.70 at 0/120/240 degrees are shared with the gearbox.
The rotor/stator electromagnetic internals are enclosed, not represented as
cosmetic solids. Gearbox can start at Z=18.05 without case interference.
"""
from math import cos, sin, radians
from cadgen import build123d as bd
from .finish import finish

MOTOR_RADIUS=6.8
MOTOR_LENGTH=18.0
MOTOR_SCREW_RADIUS=5.7
MOTOR_SCREW_ANGLES=(0,120,240)


def _cyl(r,h,z=0):
    return bd.Pos(0,0,z)*bd.Cylinder(r,h,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))


def _check(s,label,material):
    if len(s.solids())!=1 or not s.is_valid or s.volume<=0:
        raise ValueError(f'{label}: requires one positive valid solid')
    return finish(s,material,label)


def make_motor_case(label='motor_dark_anodized_case'):
    """Closed rear cup with turned edge breaks, cooling scallops and screw land."""
    s=_cyl(6.8,17.25)
    s=bd.fillet(s.edges(),.22)
    # Main rotor cavity stops at a .85 mm rear web. The forward screw land is
    # a structural annulus, not three fragile pillars in a cosmetic shell.
    s=s-_cyl(6.05,14.95,.85)-_cyl(4.6,2.0,15.8)-_cyl(1.04,1.0,-.05)
    # Continuous radiused witness grooves are actual turned geometry.
    for z in (1.85,15.35):
        s=s-bd.Pos(0,0,z)*bd.Torus(6.8,.11)
    # Six softly capped shallow longitudinal cooling scallops.
    for angle in range(0,360,60):
        a=radians(angle+30)
        x,y=7.45*cos(a),7.45*sin(a)
        cutter=bd.Pos(x,y,4.0)*bd.Cylinder(.78,9.0,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))
        cutter=cutter+bd.Pos(x,y,4.0)*bd.Sphere(.78)+bd.Pos(x,y,13.0)*bd.Sphere(.78)
        s=s-cutter
    # The three tie bolts run from the gearbox head seats to cartridge nuts.
    # Ream through the rear web and the thin wall beside the rotor cavity.
    for angle in MOTOR_SCREW_ANGLES:
        a=radians(angle)
        s=s-bd.Pos(5.7*cos(a),5.7*sin(a),-.05)*bd.Cylinder(.54,17.5,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))
    return _check(s,label,'dark')


def make_motor_endcap(label='motor_polished_front_endcap'):
    """Separate bright turned endcap with recessed three-point screw pattern."""
    s=_cyl(6.74,.7,17.3)
    s=bd.fillet(s.edges(),.10)
    pilot=_cyl(4.55,1.1,16.3)
    pilot=bd.fillet(pilot.edges(),.08)
    s=s+pilot
    # Output sleeve projects only within the declared 18 mm envelope.
    s=s-_cyl(1.04,2.0,16.2)
    for angle in MOTOR_SCREW_ANGLES:
        a=radians(angle)
        x,y=5.7*cos(a),5.7*sin(a)
        s=s-bd.Pos(x,y,17.2)*bd.Cylinder(.54,1.0,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))
        s=s-bd.Pos(x,y,17.65)*bd.Cylinder(.82,.45,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))
    # A fine continuous lathe ring gives the cap a readable bearing register.
    s=s-bd.Pos(0,0,18.015)*bd.Torus(2.6,.055)
    return _check(s,label,'steel')


def make_motor_shaft(label='motor_polished_output_shaft'):
    """Separate 2 mm output spindle, with a shallow D-flat at Z=18.3..20."""
    s=_cyl(1.0,19.2,.8)
    s=bd.fillet(s.edges(),.06)
    s=s-bd.Pos(.87,-2,18.3)*bd.Box(2,4,2,align=(bd.Align.MIN,bd.Align.MIN,bd.Align.MIN))
    return _check(s,label,'steel')
