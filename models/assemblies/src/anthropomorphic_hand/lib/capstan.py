"""Six-turn single-layer storage capstan with captured, separately made ferrule.

Axis +Z. R7 working centreline, 0.8 pitch, six turns from Z-2.4 to +2.4.
The original cubic helix is the groove cutter: animated rope remains seated.
A blind end on the terminal ferrule abuts the rope end at its start plane;
its OD is captured in a matching pocket and retained by the lower flange.
"""
from cadgen import build123d as bd
from .finish import finish
from .capstan_path import full_groove_path,stored_path,prefix_length,tangent


def path_wire(path):return bd.Wire([bd.Edge.make_bezier(*s['points']) for s in path])


def sweep_round(path,radius):
    plane=bd.Plane(origin=path[0]['points'][0],z_dir=tangent(path,True))
    return bd.sweep(plane*bd.Circle(radius),path=path_wire(path),is_frenet=False)


def make_capstan(label='six_turn_storage_capstan'):
    # Radiused independent lathe blanks are fused before the helical seat is cut.
    barrel=bd.Pos(0,0,-2.7)*bd.Cylinder(7.12,5.4,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))
    lower=bd.Pos(0,0,-2.9)*bd.Cylinder(7.5,.55,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))
    upper=bd.Pos(0,0,2.35)*bd.Cylinder(7.5,.55,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))
    lower=bd.fillet(lower.edges().filter_by(bd.GeomType.CIRCLE),.07)
    upper=bd.fillet(upper.edges().filter_by(bd.GeomType.CIRCLE),.07)
    hub=bd.Pos(0,0,2.6)*bd.Cylinder(2.,1.65,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))
    hub=bd.fillet(hub.edges().filter_by(bd.GeomType.CIRCLE),.10)
    body=barrel+lower+upper+hub
    # D bore: the flat is +X .75; radial running clearance is .03.
    bore=bd.Cylinder(1.03,10,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.CENTER))
    flat_keep=bd.Pos(-5.25,0,0)*bd.Box(12,12,12)
    body=body-(bore & flat_keep)
    groove=full_groove_path()
    body=body-sweep_round(groove,.35)
    # Shallow counterseat around the first 0.8 mm captures the terminal ferrule.
    terminal_path=prefix_length(groove,.8)
    start=groove[0]['points'][0]; direction=tangent(groove,True)
    pocket=sweep_round(terminal_path,.49)
    pocket=pocket+bd.Plane(origin=start,z_dir=direction)*bd.Cylinder(.49,.14,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MAX))
    body=body-pocket
    # Bowl-shaped upper web reveals the central keyed drive boss.
    recess=bd.Pos(0,0,2.4)*(bd.Cylinder(5.7,1,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))-bd.Cylinder(2.3,1,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN)))
    recess=bd.fillet(recess.edges().filter_by(bd.GeomType.CIRCLE),.12)
    body=body-recess
    # A 0.01 mm finishing radius softens every long exposed helical lip.
    lips=[e for e in body.edges() if e.geom_type==bd.GeomType.BSPLINE and e.length>9]
    body=bd.fillet(lips,.01)
    # Index marks at one angular position, so the drum's rotation is readable.
    #
    # It is worth being explicit about why this is needed, because the geometry
    # actively hides its own motion. The drum turns +-70 degrees at most: 8.5 mm
    # of rope off a R7 capstan, which is 0.19 of a turn. It is a surface of
    # revolution, so that rotation changes nothing about its silhouette. The
    # six-turn rope wound on it is a helix, so rotating it about its own axis
    # slides it along that axis by 0.8 * 70/360 = 0.16 mm and otherwise maps it
    # onto itself. And every part that turns FASTER -- the shaft at 4x, the
    # planets at 2x the carrier -- is sealed inside a static case. Without a
    # mark, the one mechanism this model exists to demonstrate is invisible.
    #
    # Four cuts at a shared angle. None may touch a rope seat: the barrel is
    # R7.12 and the groove's top turn crests at Z 2.75 over R6.65..7.35, so the
    # material free to cut is the drive boss, the flange top inboard of R6.65,
    # and the flange rims outboard of R7.2.
    #
    # The boss carries the loudest of them. It is the top of the whole cartridge
    # stack and nothing occludes it -- and it faces outward on all 48, because
    # the negative-sign bank is placed through Rot(0,180,0).
    body=body-bd.Pos(0,0,4.25)*bd.Box(2.2,.8,.55,align=(bd.Align.MIN,bd.Align.CENTER,bd.Align.MAX))
    body=body-bd.Pos(1.4,0,2.6)*bd.Box(1.2,4,1.75,align=(bd.Align.MIN,bd.Align.CENTER,bd.Align.MIN))
    body=body-bd.Pos(6.6,0,2.5)*bd.Box(.9,1.8,.5,align=(bd.Align.MAX,bd.Align.CENTER,bd.Align.MIN))
    for z in (-2.9,2.35):
        body=body-bd.Pos(7.22,0,z)*bd.Box(.5,6,.55,align=(bd.Align.MIN,bd.Align.CENTER,bd.Align.MIN))
    if len(body.solids())!=1 or not body.is_valid:raise ValueError('capstan failed solid validation')
    return finish(body,'aluminum',label)


def make_terminal_ferrule(label='captured_rope_terminal_ferrule'):
    path=prefix_length(full_groove_path(),.8)
    outer=sweep_round(path,.46);inner=sweep_round(path,.31)
    plane=bd.Plane(origin=path[0]['points'][0],z_dir=tangent(path,True))
    cap=plane*bd.Cylinder(.46,.10,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MAX))
    cap=bd.fillet(cap.edges().filter_by(bd.GeomType.CIRCLE),.025)
    ferrule=(outer-inner)+cap
    if len(ferrule.solids())!=1 or not ferrule.is_valid:raise ValueError('terminal ferrule failed validation')
    return finish(ferrule,'steel',label)


def make_stored_tendon(rotation_rad=0.,label='capstan_stored_tendon'):
    body=sweep_round(stored_path(rotation_rad),.30)
    if len(body.solids())!=1 or not body.is_valid:raise ValueError('stored tendon failed validation')
    return finish(body,'cord_flexion_positive',label)
