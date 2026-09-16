from cadgen import build123d as bd

# mm. Same 80 x 60 x 25 envelope; bottom mounting datum Z=0.
WIDTH, DEPTH, HEIGHT = 80, 60, 25
HOLE_RADIUS = 2.25
HOLE_CENTERS = [(x,y) for x in (-25,25) for y in (-18,18)]

def box(x,y,z,at=(0,0,0)):
    return bd.Pos(*at) * bd.Box(x,y,z,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))

def tray(kind):
    if kind == 'sheet':
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
        part-=bd.Pos(x,y,-1)*bd.Cylinder(HOLE_RADIUS,8,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))
    part.label=f'{kind}_mounting_tray'
    assert part.is_valid and len(part.solids())==1
    return part
