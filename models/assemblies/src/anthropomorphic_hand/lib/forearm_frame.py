"""Open actuator reaction chassis, machined rear flange and wrist adapter.

All dimensions millimetres, already in the forearm frame. Twenty-four paired
stations accept the independently modelled torque cartridges with .05 mm face
clearance. Side beams and deep inter-row ribs provide a load path around the
open rotor and tendon corridors. No actuator or route coordinate is changed.
"""
from math import cos, sin, radians, atan2, degrees, hypot
from cadgen import build123d as bd, report
from .finish import finish

STATION_X=(-27.,-9.,9.,27.)
STATION_Y=(-252.,-211.,-170.,-129.,-88.,-47.)
SEAT_OUTER_RADIUS=8.70
SEAT_INNER_RADIUS=6.90
SEAT_HALF_THICKNESS=.35
FRAME_FASTENER_RADIUS=7.55
FRAME_FASTENER_BORE=.54
SIDE_RAIL_X=38.
SIDE_RAIL_WIDTH=3.4
SIDE_RAIL_LENGTH=243.
SIDE_RAIL_HEIGHT=12.
SIDE_RAIL_CENTER_Y=-154.5
SIDE_RAIL_FILLET=1.50
WRIST_FRAME_EYES=tuple((x,-33.10,z) for x in (-10.,10.) for z in (-9.,9.))
REAR_FLANGE_BORES=tuple((x,-278.,z) for x,z in ((-40,-27),(-40,27),(40,-27),(40,27),(-23,-45),(23,-45),(-23,45),(23,45)))


def _rounded_box(x,y,z,r):
    s=bd.Box(x,y,z)
    return bd.fillet(s.edges(),r)


def _capsule(a,b,width,depth):
    """Planar capsule web; continuous rounded profile with no buried square ends."""
    dx,dy=b[0]-a[0],b[1]-a[1]
    length=hypot(dx,dy)
    s=bd.extrude(bd.SlotOverall(length+width,width),amount=depth/2,both=True)
    return bd.Pos((a[0]+b[0])/2,(a[1]+b[1])/2,0)*bd.Rot(0,0,degrees(atan2(dy,dx)))*s


def _rib(points,radius):
    e=bd.Edge.make_bezier(*points)
    return bd.sweep(bd.Plane(origin=e.position_at(0),z_dir=e.tangent_at(0))*bd.Circle(radius),path=e)


def _validate(s,label):
    if len(s.solids())!=1 or not s.is_valid or s.volume<=0:
        raise ValueError(f'{label}: expected one valid connected positive solid; got {len(s.solids())}')
    return finish(s,'dark',label)


def _ladder(x):
    seats=[]
    for y in STATION_Y:
        ring=bd.Cylinder(SEAT_OUTER_RADIUS,.70)-bd.Cylinder(SEAT_INNER_RADIUS,1.0)
        # A minute broken rim catches the light while preserving the seat plane.
        ring=bd.fillet(ring.edges(),.055)
        for a in range(0,360,60):
            ring=ring-bd.Pos(FRAME_FASTENER_RADIUS*cos(radians(a)),FRAME_FASTENER_RADIUS*sin(radians(a)),0)*bd.Cylinder(FRAME_FASTENER_BORE,1.2)
        seats.append(bd.Pos(x,y,0)*ring)
    web=[];deep=[]
    for y0,y1 in zip(STATION_Y,STATION_Y[1:]):
        ym=(y0+y1)/2
        # Two gently converging web strips leave each annular seat on a tangent.
        for sign in (-1,1):
            web += [_capsule((x+sign*4.8,y0+6.8),(x+sign*2.1,ym),1.65,.70),
                    _capsule((x+sign*2.1,ym),(x+sign*4.8,y1-6.8),1.65,.70)]
        web.append(_capsule((x,y0+7.7),(x,y1-7.7),2.8,.70))
        deep.append(bd.Pos(x,ym,0)*_rounded_box(2.50,22.0,5.8,1.15))
    for y,end in ((STATION_Y[0],-274.),(STATION_Y[-1],-35.)):
        web.append(_capsule((x,y+(-7.7 if end<y else 7.7)),(x,end),2.8,.70))
    s=seats[0].fuse(*seats[1:],*web,*deep)
    # All ladder branches are rounded in profile before joining; the broad
    # open windows expose the sensor flexures and are functional access bays.
    return _validate(s,f'forearm_column_{int(x):+d}_six_station_reaction_ladder')


def make_rear_flange():
    """Removable rounded rectangular rim with eight through mounting bores."""
    outside=bd.extrude(bd.RectangleRounded(84,94,14),amount=2,both=True)
    inside=bd.extrude(bd.RectangleRounded(76,86,11),amount=3,both=True)
    ring=outside-inside
    ring=bd.fillet(ring.edges(),.60)
    ring=bd.Pos(0,-278,0)*bd.Rot(90,0,0)*ring
    for x,y,z in REAR_FLANGE_BORES:
        ring=ring-bd.Pos(x,y,z)*bd.Cylinder(1.65,6,rotation=(90,0,0))
    for x in (-39.,39.):
        for z in (-3.3,3.3):
            ring=ring-bd.Pos(x,-278,z)*bd.Cylinder(.90,6,rotation=(90,0,0))
    return _validate(ring,'forearm_rear_eight_bolt_sculpted_mounting_flange')


def make_forearm_chassis():
    """One fused skeletal reaction frame, including its four wrist fixing eyes."""
    report('24 sensor seats and four open ladders')
    ladders=[_ladder(x) for x in STATION_X]
    report('longerons and transverse load paths')
    rails=[bd.Pos(x,SIDE_RAIL_CENTER_Y,0)*_rounded_box(SIDE_RAIL_WIDTH,SIDE_RAIL_LENGTH,SIDE_RAIL_HEIGHT,SIDE_RAIL_FILLET) for x in (-38,38)]
    # Rear/distal crossmembers and five vaulted transverse braces. They sit
    # between actuator rows, so the motor/sensor envelope remains unobstructed.
    rails += [bd.Pos(x,-272,0)*_rounded_box(4,8,11,.50) for x in (-39,39)]
    cross=[bd.Pos(0,y,0)*_rounded_box(76,2.8,5.8,1.25) for y in (-274,-35)]
    for y0,y1 in zip(STATION_Y,STATION_Y[1:]):
        ym=(y0+y1)/2
        cross.append(bd.Pos(0,ym,0)*_rounded_box(76,2.25,3.4,1.0))
    report('wrist mounting branches')
    eyes=[];branches=[]
    for x,y,z in WRIST_FRAME_EYES:
        eye=bd.Pos(x,y,z)*bd.Cylinder(3.2,3,rotation=(90,0,0))
        eye=bd.fillet(eye.edges(),.25)
        eyes.append(eye)
        branches.append(_rib([(x*1.7,-35,0),(x*1.6,-35,z*.38),(x*1.26,-33.1,z*.6),(x*1.26,-33.1,z)],1.25))
    s=ladders[0].fuse(*ladders[1:],*rails,*cross,*eyes,*branches)
    for x,y,z in WRIST_FRAME_EYES:
        s=s-bd.Pos(x,y,z)*bd.Cylinder(1.65,6,rotation=(90,0,0))
    # Finish-ream all six staggered bores after the web branches are united.
    sensor_cutters=[bd.Pos(x+7.55*cos(radians(a)),y+7.55*sin(radians(a)),0)*bd.Cylinder(.54,1.2) for x in STATION_X for y in STATION_Y for a in range(0,360,60)]
    s=s.cut(*sensor_cutters)
    # Opposing guide-bank feet share an axis but have separate short screws.
    guide_cutters=[bd.Pos(x,y,0)*bd.Cylinder(.54,16) for x in (-38.,38.) for y in (-223.,-182.,-141.,-100.,-59.,-36.)]
    s=s.cut(*guide_cutters)
    # Four axial rear attachment bores receive the flange fasteners. There is
    # deliberate unthreaded geometry: final thread sizing is a drawing issue.
    for x in (-39.,39.):
        for z in (-3.3,3.3):
            s=s-bd.Pos(x,-271,z)*bd.Cylinder(.85,12,rotation=(90,0,0))
            # Side-entry captive nut pocket: preserve a .65 mm rear bearing
            # ledge so tightening pulls the actual chassis against the rim.
            pocket=bd.Pos(x,-275.35,z)*bd.Rot(90,0,0)*bd.extrude(bd.RegularPolygon(1.50,6),amount=-1.50)
            access=bd.Pos(40.55 if x>0 else -40.55,-274.60,z)*bd.Box(3.10,1.50,2.70)
            s=s-pocket-access
    # The fixed wrist fork's two bowed tie members return behind the mating
    # eye faces. Sculpt a0.06mm clearance saddle into the outer eye rims;
    # the M3 bores and their complete bearing bands remain untouched.
    for x in (-10.,10.):
        s=s-_rib([(x,-30,-6.5),(x,-34,-4),(x,-34,4),(x,-30,6.5)],.96)
    relief_edges=[e for e in s.edges() if e.geom_type==bd.GeomType.BSPLINE
                  and abs(abs(e.center().X)-10.)<1.2
                  and -34.2<e.center().Y<-31.5 and 5.5<abs(e.center().Z)<7.0]
    if relief_edges:s=bd.fillet(relief_edges,.025)
    return _validate(s,'forearm_monolithic_24_seat_open_reaction_chassis')


def make_forearm_frame_bodies():
    """Named native solids in assembled coordinates; flange is independently removable."""
    return [make_forearm_chassis(),make_rear_flange()]


def forearm_frame_mounts():
    return {'sensor_seats':tuple({'center':(x,y,0),'outer_radius':8.7,'inner_radius':6.9,'faces':(-.35,.35),'bores':tuple((x+7.55*cos(radians(a)),y+7.55*sin(radians(a)),0) for a in range(0,360,60))} for x in STATION_X for y in STATION_Y),
            'wrist':WRIST_FRAME_EYES,'rear_flange':REAR_FLANGE_BORES}
