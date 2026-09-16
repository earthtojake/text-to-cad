from cadgen import build123d as bd

# mm. Same 80 x 60 x 25 envelope; bottom mounting datum Z=0.
WIDTH, DEPTH, HEIGHT = 80, 60, 25
HOLE_RADIUS = 2.25
HOLE_CENTERS = [(x,y) for x in (-25,25) for y in (-18,18)]

def box(x,y,z,at=(0,0,0)):
    return bd.Pos(*at) * bd.Box(x,y,z,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))

def tray(kind):
    if kind == 'injection':
        from math import tan, radians
        slope=tan(radians(1))
        floor=2.4
        # Both mold sides release along Z; nominal base wall 2.4 mm tapers.
        outer=bd.loft([bd.Plane.XY*bd.Rectangle(80,60),
                       bd.Plane.XY.offset(25)*bd.Rectangle(80-50*slope,60-50*slope)])
        cavity=bd.loft([bd.Plane.XY.offset(floor)*bd.Rectangle(75.2,64),
                        bd.Plane.XY.offset(26)*bd.Rectangle(75.2+2*(26-floor)*slope,64)])
        part=outer-cavity
        for sign in (-1,1):
            for y in (-24,24):
                # Gusset side faces taper 1 degree per side; tip overlaps the wall.
                x=sign*37.6
                profile=bd.Plane.XZ*bd.Polygon((x+sign*.15,floor),(x-sign*8,floor),(x+sign*.15,floor+8),align=None)
                rib=bd.Pos(0,y,0)*bd.extrude(profile,amount=.6,both=True)
                taper=bd.loft([bd.Plane.XY.offset(floor)*bd.Rectangle(82,1.2),
                               bd.Plane.XY.offset(floor+8)*bd.Rectangle(82,1.2-16*slope)])
                part += rib & (bd.Pos(0,y,0)*taper)
    elif kind == 'sheet':
        t,r=1.5,2.0
        c=WIDTH/2-t-r
        part=box(2*c,DEPTH,t)
        for sign in (-1,1):
            # Quarter-annulus bend, axis along Y, tangent to flat base and flange.
            ring=bd.Cylinder(r+t,DEPTH,rotation=(90,0,0))-bd.Cylinder(r,DEPTH+2,rotation=(90,0,0))
            ring=bd.Pos(sign*c,0,r+t)*ring
            quadrant=box(r+t,DEPTH,r+t,(sign*(c+(r+t)/2),0,0))
            bend=ring & quadrant
            wall=box(t,DEPTH,HEIGHT-r-t,(sign*(WIDTH/2-t/2),0,r+t))
            part=part+bend+wall
    else:
        t={'baseline':0.8,'fdm':2.4,'cnc':3.0}[kind]
        floor={'baseline':3.0,'fdm':2.4,'cnc':3.0}[kind]
        part=box(WIDTH,DEPTH,floor)
        for sign in (-1,1):
            part += box(t,DEPTH,HEIGHT-floor,(sign*(WIDTH/2-t/2),0,floor))
        if kind=='cnc':
            edges=[e for e in part.edges() if abs(e.length-DEPTH)<1e-5 and abs(e.center().Z-floor)<1e-5 and abs(abs(e.center().X)-(WIDTH/2-t))<1e-5]
            assert len(edges)==2
            part=bd.fillet(edges,3)
        if kind=='fdm':
            for sign in (-1,1):
                for y in (-25,25):
                    x=sign*(WIDTH/2-t)
                    profile=bd.Plane.XZ*bd.Polygon((x,floor),(x-sign*8,floor),(x,floor+8),align=None)
                    rib=bd.extrude(profile,amount=2.4,both=True)
                    part+=bd.Pos(0,y,0)*rib
    for x,y in HOLE_CENTERS:
        if kind == 'injection':
            # Fixed Ø4.5 at mounting datum, 1-degree draft opens toward +Z.
            part-=bd.Pos(x,y,0)*bd.Cone(HOLE_RADIUS,HOLE_RADIUS+8*slope,8,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))
        else:
            part-=bd.Pos(x,y,-1)*bd.Cylinder(HOLE_RADIUS,8,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))
    part.label=f'{kind}_mounting_tray'
    assert part.is_valid and len(part.solids())==1
    return part
