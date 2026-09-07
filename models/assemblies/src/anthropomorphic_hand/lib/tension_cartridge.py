"""Three-arm monolithic torsional reaction mount and three bonded gauge chips.

Native station axes are world axes: the palmar cartridge is Z .40..3.95;
rotate 180 degrees about Y for the dorsal bank. The lower outer fastening
annulus is connected to the upper motor annulus only by three planar scroll
flexures and the inner riser. This is an authored compliant geometry, not a
calibrated force transducer. Strain calibration/strength remain unspecified.
"""
from math import cos, sin, radians
from cadgen import build123d as bd
from .finish import finish

CARTRIDGE_RADIUS = 8.20
CARTRIDGE_Z_MIN = .40
CARTRIDGE_Z_MAX = 3.95
MOTOR_MOUNT_RADIUS = 5.70
FRAME_MOUNT_RADIUS = 7.55
MOTOR_MOUNT_ANGLES = (0.,120.,240.)
FRAME_MOUNT_ANGLES = (60.,180.,300.)
MOUNT_BORE_RADIUS = .54


def _cylinder(radius,height,z):
    return bd.Pos(0,0,z)*bd.Cylinder(radius,height,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))


def _annulus(outer,inner,z,height,edge_break):
    s=_cylinder(outer,height,z)-_cylinder(inner,height+.2,z-.1)
    return bd.fillet(s.edges(),edge_break)


def _polar(r,a):
    return (r*cos(radians(a)),r*sin(radians(a)))


def _scroll_arm(angle):
    # Spline-sided strip with generous buried ends; round, uninterrupted
    # curvature is authored in the profile rather than fragile 3D blends.
    stations=((4.95,-7),(5.60,12),(6.00,35),(6.30,57),(6.72,76),(7.38,88))
    left=[(*_polar(r+.29,a+angle),0) for r,a in stations]
    right=[(*_polar(r-.29,a+angle),0) for r,a in stations]
    outline=bd.Wire([bd.Spline(*left),bd.Line(left[-1],right[-1]),bd.Spline(*reversed(right)),bd.Line(right[0],left[0])])
    return bd.Pos(0,0,1.10)*bd.extrude(bd.Face(outline),amount=.65)


def make_tension_spring(label='tension_cartridge_monolithic_stainless_scroll_spring'):
    """One connected closed spring body; no cosmetic springs or hidden ties."""
    outer=_annulus(8.20,6.90,.40,1.35,.075)
    riser=_annulus(5.40,4.60,1.10,2.85,.065)
    # Three generous open scallops admit captive nuts beneath the motor land.
    # The remaining riser is three axial crescent pillars on the inner hoop.
    for angle in MOTOR_MOUNT_ANGLES:
        x,y=_polar(5.70,angle)
        riser=riser-bd.Pos(x,y,0)*_cylinder(1.15,1.20,1.90)
    motor=_annulus(6.80,4.60,3.05,.90,.075)
    spring=outer.fuse(riser,motor,*[_scroll_arm(a) for a in MOTOR_MOUNT_ANGLES])
    for radius,angles,z,h in ((5.7,MOTOR_MOUNT_ANGLES,2.95,1.1),(7.55,FRAME_MOUNT_ANGLES,.3,1.55)):
        for angle in angles:
            x,y=_polar(radius,angle)
            spring=spring-bd.Pos(x,y,0)*_cylinder(.54,h,z)
    if len(spring.solids())!=1 or not spring.is_valid or spring.volume<=0:
        raise ValueError('torsional cartridge must remain one closed positive spring body')
    return finish(spring,'steel',label)


def make_tension_gauges(prefix='tension_cartridge'):
    """Three separate bonded dark sensor chips on the horizontal flexure faces.

    The .24 x .68 mm chips have real rounded substrates and shallow parallel
    trenches suggesting the active foil grid without adding decorative bodies.
    Their undersides coincide with the arm top Z1.75.
    """
    result=[]
    for i,angle in enumerate(MOTOR_MOUNT_ANGLES):
        chip=bd.Box(.24,.68,.11,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))
        chip=bd.fillet(chip.edges().filter_by(bd.Axis.Z),.035)
        for x in (-.06,0,.06):
            chip=chip-bd.Pos(x,0,.095)*bd.Box(.018,.49,.025,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))
        # At a35 degrees the spline passes r6.00; the chip's long axis follows
        # the arm tangent, offset slightly radially to follow the spiral.
        a=35+angle
        x,y=_polar(6.00,a)
        chip=bd.Pos(x,y,1.75)*bd.Rot(0,0,a-9)*chip
        if len(chip.solids())!=1 or not chip.is_valid or chip.volume<=0:
            raise ValueError('gauge must be a single closed bonded chip')
        result.append(finish(chip,'dark',f'{prefix}_bonded_strain_gauge_{i+1}'))
    return result


def make_tension_cartridge(prefix='tension_cartridge'):
    """Return spring followed by three separately labelled gauge solids."""
    return [make_tension_spring(f'{prefix}_monolithic_stainless_scroll_spring'),*make_tension_gauges(prefix)]


def tension_cartridge_mounts():
    """Native bore/seat datums; all axis vectors point toward the motor."""
    return {
        'motor':tuple({'name':f'motor_mount_{i+1}','center':(*_polar(5.7,a),3.95),'axis':(0,0,1),'diameter':1.08,'bore_bottom':3.05} for i,a in enumerate(MOTOR_MOUNT_ANGLES)),
        'captive_nut_clearance':tuple({'center':(*_polar(5.7,a),2.25),'radius':.85,'z_min':2.25,'z_max':3.05} for a in MOTOR_MOUNT_ANGLES),
        'frame':tuple({'name':f'frame_mount_{i+1}','center':(*_polar(7.55,a),.40),'axis':(0,0,1),'diameter':1.08,'bore_top':1.75} for i,a in enumerate(FRAME_MOUNT_ANGLES)),
    }
