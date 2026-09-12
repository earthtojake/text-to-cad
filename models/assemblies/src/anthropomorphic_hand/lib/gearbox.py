"""Miniature 4:1 planetary reducer; native motor datum and output axis +Z.

All parts occupy motor-local Z18.05..33.2; the gearbox shell ends Z26.
12/12/36 involute teeth, module .25, 20 degree pressure angle. Three planets
run on carrier pins at radius3.00. Gear face width2.40. Nominal backlash is
.025 mm per flank. No strength or lifetime claim is made at this scale.
"""
from math import sin, cos, pi, sqrt, acos, tan, radians
from cadgen import build123d as bd
from .finish import finish


def _cyl(r,h,z=0):
    return bd.Pos(0,0,z)*bd.Cylinder(r,h,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))


def _check(s,label,material='steel'):
    if len(s.solids())!=1 or not s.is_valid or s.volume<=0:
        raise ValueError(f'{label}: requires one positive valid solid')
    return finish(s,material,label)


def _tooth_face(n,internal_void=False,phase=0):
    m=.25; rp=m*n/2; rb=rp*cos(radians(20))
    root=rp-m if internal_void else rp-1.25*m
    tip=rp+1.25*m if internal_void else rp+m
    half=pi/(2*n) + (.025/rp if internal_void else -.025/rp)
    invp=tan(radians(20))-radians(20)
    def invol(r):
        if r<=rb: return 0
        alpha=acos(rb/r); return tan(alpha)-alpha
    def half_at(r):
        return half-(invol(r)-invp)
    def p(r,a): return (r*cos(a),r*sin(a),0)
    edges=[]
    flankstart=max(root,rb)
    for k in range(n):
        a=phase+2*pi*k/n
        hs=half_at(flankstart); ht=half_at(tip)
        low=p(root,a-hs); start=p(flankstart,a-hs)
        if flankstart>root+1e-8: edges.append(bd.Edge.make_line(low,start))
        points=[p(flankstart+(tip-flankstart)*i/12,a-half_at(flankstart+(tip-flankstart)*i/12)) for i in range(13)]
        edges.append(bd.Edge.make_spline(points))
        edges.append(bd.Edge.make_three_point_arc(points[-1],p(tip,a),p(tip,a+ht)))
        points=[p(tip-(tip-flankstart)*i/12,a+half_at(tip-(tip-flankstart)*i/12)) for i in range(13)]
        edges.append(bd.Edge.make_spline(points))
        end=p(root,a+hs)
        if flankstart>root+1e-8: edges.append(bd.Edge.make_line(points[-1],end))
        nexta=a+2*pi/n-hs
        edges.append(bd.Edge.make_three_point_arc(end,p(root,(a+hs+nexta)/2),p(root,nexta)))
    return bd.Face(bd.Wire(edges))


def _gear_round(s):
    # Small but real edge breaks: roots/flank junctions, then both tooth faces.
    s=bd.fillet(s.edges().filter_by(bd.Axis.Z),.015)
    return bd.fillet(s.edges().filter_by(bd.Axis.Z,reverse=True),.008)


def make_gearbox_housing(label='gearbox_dark_housing'):
    s=_cyl(6.8,7.95,18.05)
    s=bd.fillet(s.edges(),.18)
    s=s-_cyl(5.2,5.0,18.0)-_cyl(2.34,3.3,22.9)
    for z in (18.55,22.5,25.35): s=s-bd.Pos(0,0,z)*bd.Torus(6.8,.085)
    for angle in (60,180,300):
        pocket=bd.Pos(5.02,-.29,18.60)*bd.Box(.34,.58,1.70,align=(bd.Align.MIN,bd.Align.MIN,bd.Align.MIN))
        s=s-bd.Rot(0,0,angle)*pocket
    for angle in (0,120,240):
        a=radians(angle); x,y=5.7*cos(a),5.7*sin(a)
        s=s-bd.Pos(x,y,18.0)*_cyl(.54,8.2)
        s=s-bd.Pos(x,y,25.5)*_cyl(.82,.6)
    return _check(s,label,'dark')


def make_gearbox_ring(label='gearbox_stationary_internal_ring'):
    s=_cyl(5.14,2.4,18.25)
    cutter=bd.Pos(0,0,18.2)*bd.extrude(_tooth_face(36,True,pi/36),amount=2.5)
    s=_gear_round(s-cutter)
    for angle in (60,180,300):
        key=bd.Pos(5.00,-.25,18.65)*bd.Box(.30,.50,1.60,align=(bd.Align.MIN,bd.Align.MIN,bd.Align.MIN))
        key=bd.fillet(key.edges(),.04)
        s=s+bd.Rot(0,0,angle)*key
    return _check(s,label)


def make_gearbox_sun(label='gearbox_input_sun'):
    s=_gear_round(bd.Pos(0,0,18.25)*bd.extrude(_tooth_face(12),amount=2.4))
    bore=_cyl(1.04,2.6,18.15)-bd.Pos(.90,-2,18.35)*bd.Box(2,4,3,align=(bd.Align.MIN,bd.Align.MIN,bd.Align.MIN))
    s=s-bore
    return _check(s,label)


def make_gearbox_planet(index=0,label=None):
    a=radians(index*120)
    s=bd.Pos(0,0,18.25)*bd.extrude(_tooth_face(12,False,pi/12),amount=2.4)
    s=s-_cyl(.49,2.6,18.15)
    s=bd.Pos(3*cos(a),3*sin(a),0)*_gear_round(s)
    return _check(s,label or f'gearbox_planet_{index+1}')


def make_gearbox_carrier(label='gearbox_output_carrier'):
    s=_cyl(4.75,1.0,21.0)
    s=bd.fillet(s.edges(),.1)
    # Three crescent windows expose the planet faces during an exploded review.
    for angle in (60,180,300):
        a=radians(angle)
        s=s-bd.Pos(2.75*cos(a),2.75*sin(a),20.9)*_cyl(1.15,1.2)
    bore=_cyl(1.04,1.2,20.9)-bd.Pos(.78,-2,20.8)*bd.Box(2,4,1.5,align=(bd.Align.MIN,bd.Align.MIN,bd.Align.MIN))
    s=s-bore
    for angle in (0,120,240):
        a=radians(angle)
        s=s-bd.Pos(3*cos(a),3*sin(a),20.9)*_cyl(.47,1.2)
    return _check(s,label)


def make_gearbox_pin(index=0,label=None):
    a=radians(index*120)
    s=_cyl(.45,3.75,18.15)
    s=bd.fillet(s.edges(),.04)
    return _check(bd.Pos(3*cos(a),3*sin(a),0)*s,label or f'gearbox_planet_pin_{index+1}')


def make_gearbox_bearing(label='gearbox_output_bearing'):
    s=_cyl(2.3,2.3,23.35)-_cyl(1.04,2.5,23.25)
    s=bd.fillet(s.edges(),.07)
    s=s-bd.Pos(0,0,25.65)*bd.Torus(1.73,.045)
    return _check(s,label)


def make_gearbox_spindle(label='gearbox_keyed_output_spindle'):
    s=_cyl(1.0,12.15,21.05)
    s=bd.fillet(s.edges(),.045)
    s=s-bd.Pos(.75,-2,25.85)*bd.Box(2,4,7.7,align=(bd.Align.MIN,bd.Align.MIN,bd.Align.MIN))
    s=s-bd.Pos(.75,-2,21.0)*bd.Box(2,4,1.1,align=(bd.Align.MIN,bd.Align.MIN,bd.Align.MIN))
    # Output bearing shoulder has .04 axial clearance below the bearing.
    s=s+_cyl(1.5,.35,22.96)
    s=s-_cyl(.54,1.65,31.65)
    return _check(s,label)


def make_gearbox_parts(prefix='gearbox'):
    parts=[make_gearbox_housing(prefix+'_housing'),make_gearbox_ring(prefix+'_ring'),
           make_gearbox_sun(prefix+'_sun'),make_gearbox_carrier(prefix+'_carrier'),
           make_gearbox_bearing(prefix+'_bearing'),make_gearbox_spindle(prefix+'_spindle')]
    for i in range(3):
        parts.extend([make_gearbox_planet(i,prefix+f'_planet_{i+1}'),make_gearbox_pin(i,prefix+f'_planet_pin_{i+1}')])
    return parts
