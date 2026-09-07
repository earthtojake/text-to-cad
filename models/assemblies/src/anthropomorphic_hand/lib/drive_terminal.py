"""Curved blind terminals captured in the actual driven pulley, dimensions mm.

The final 0.8 mm of the unchanged circular tendon lies inside a steel sleeve.
Its 0.92 OD is held behind a 0.72 inlet lip in a closed, curved aluminum ear.
The ear stays within the pulley cheek's axial envelope. A flush cover closes
the axial insertion opening and is retained by a recessed M0.4 socket screw.
Each pulley has a
inclined socket grub screw bearing on the continuous D-shaft flat: loosen the
screw before withdrawing the shaft. Thread envelopes are nominal, not helical.
"""
from math import atan2, cos, sin, degrees, radians, sqrt
from cadgen import build123d as bd
from lib.pulley import make_pulley
from lib.finish import finish

FERRULE_LENGTH = .8
FERRULE_OUTER_RADIUS = .46
FERRULE_INNER_RADIUS = .31
FERRULE_CAP_LENGTH = .10
CAPTURE_OUTER_RADIUS = .64
CAPTURE_POCKET_RADIUS = .49
CAPTURE_INLET_RADIUS = .36


def arc_point(radius, distance, angle=0., direction=1):
    a=radians(angle)+direction*distance/radius
    return (radius*cos(a),radius*sin(a),0.)


def arc_tube(radius, section_radius, start, end, angle=0., direction=1):
    """Exact analytic circular sweep, signed distances measured from rope tip."""
    p=arc_point(radius,start,angle,direction)
    a=radians(angle)+direction*start/radius
    tangent=(-direction*sin(a),direction*cos(a),0.)
    edge=bd.Edge.make_three_point_arc(p,arc_point(radius,(start+end)/2,angle,direction),arc_point(radius,end,angle,direction))
    return bd.sweep(bd.Plane(origin=p,z_dir=tangent)*bd.Circle(section_radius),path=edge,is_frenet=False)


def tip_plane(radius,angle,direction):
    a=radians(angle)
    return bd.Plane(origin=arc_point(radius,0,angle,direction),z_dir=(-direction*sin(a),direction*cos(a),0.))


def make_driven_ferrule(radius=3.5,angle=-60.,direction=-1,label='driven_tendon_blind_ferrule'):
    outer=arc_tube(radius,FERRULE_OUTER_RADIUS,-FERRULE_LENGTH,0.,angle,direction)
    inner=arc_tube(radius,FERRULE_INNER_RADIUS,-FERRULE_LENGTH,0.,angle,direction)
    cap=tip_plane(radius,angle,direction)*bd.Cylinder(FERRULE_OUTER_RADIUS,FERRULE_CAP_LENGTH,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))
    # The closed cap starts exactly at the rope's flat endpoint plane.
    cap=bd.fillet(cap.edges().filter_by(bd.GeomType.CIRCLE),.025)
    body=outer-inner+cap
    if len(body.solids())!=1 or not body.is_valid:raise ValueError('invalid curved driven ferrule')
    return finish(body,'steel',label)


def make_driven_bond_line(radius=3.5,angle=-60.,direction=-1):
    """Real 0.01 mm annular resin bond between braided rope and steel sleeve."""
    body=arc_tube(radius,.31,-FERRULE_LENGTH,0.,angle,direction)-arc_tube(radius,.30,-FERRULE_LENGTH,0.,angle,direction)
    if not body.is_valid or len(body.solids())!=1:raise ValueError('invalid driven resin bond line')
    body=finish(body,'dark','drive_terminal_bond_line')
    body.cad_material={'metalness':0.,'roughness':.44,'clearcoat':.12}
    return body


def grub_screw_plane(bore_radius=1.03,side=1):
    return bd.Plane(origin=(.75*(bore_radius-.03),0.,0.),x_dir=(0.,1.,0.),z_dir=(1.,0.,float(side)))


def make_pulley_grub_screw(bore_radius=1.03,label='driven_pulley_inclined_socket_grub_screw',*,side=1):
    """M0.5 cone-point socket screw touching the D flat, exiting at 45 degrees.

    A +Z/-Z outboard orientation lets each antagonist leave the dished hub
    without crossing its rim or the other pulley. Installed height is .7284.
    """
    cone=bd.Cone(0.,.25,.36,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))
    shank=bd.Pos(0,0,.36)*bd.Cylinder(.25,.42,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))
    screw=cone+shank
    end=[e for e in screw.edges().filter_by(bd.GeomType.CIRCLE) if abs(e.center().Z-.78)<1e-6]
    screw=bd.chamfer(end,.02)
    socket=bd.Pos(0,0,.61)*bd.extrude(bd.RegularPolygon(.26/sqrt(3),6),amount=.22)
    screw=screw-socket
    if len(screw.solids())!=1 or not screw.is_valid:raise ValueError('invalid pulley grub screw')
    return finish(grub_screw_plane(bore_radius,side)*screw,'steel',label)


def make_terminal_pulley(radius=3.5,bore_radius=1.03,angle=-60.,direction=-1,label='captured_terminal_drive_pulley'):
    body=make_pulley(radius,bore_radius=bore_radius)
    ear=arc_tube(radius,CAPTURE_OUTER_RADIUS,-1.,.35,angle,direction)
    pocket=arc_tube(radius,CAPTURE_POCKET_RADIUS,-.82,0.,angle,direction)
    pocket=pocket+tip_plane(radius,angle,direction)*bd.Cylinder(CAPTURE_POCKET_RADIUS,.14,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))
    inlet=arc_tube(radius,CAPTURE_INLET_RADIUS,-1.30,-.82,angle,direction)
    body=(body+ear)-pocket-inlet
    # Inclined threaded hole opens through the dished hub face into the D flat.
    screw_hole=grub_screw_plane(bore_radius,-direction)*bd.Cylinder(.26,2.0,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))
    body=body-screw_hole
    if len(body.solids())!=1 or not body.is_valid:raise ValueError('invalid captured terminal pulley')
    return finish(body,'aluminum',label)


def cover_screw_location(radius,angle,direction):
    a=radians(angle)-direction*.3/radius
    return bd.Pos((radius-.74)*cos(a),(radius-.74)*sin(a),0.)


def make_cover_screw(radius=3.5,angle=-60.,direction=-1):
    """Nominal M0.4 recessed socket screw; shoulder Z+.25, tip Z-.20."""
    shank=bd.Pos(0,0,-.20)*bd.Cylinder(.20,.45,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))
    head=bd.Pos(0,0,.25)*bd.Cylinder(.34,.22,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))
    head=bd.fillet(head.edges().filter_by(bd.GeomType.CIRCLE),.025)
    screw=shank+head
    socket=bd.Pos(0,0,.34)*bd.extrude(bd.RegularPolygon(.28/sqrt(3),6),amount=.20)
    screw=screw-socket
    if not screw.is_valid or len(screw.solids())!=1:raise ValueError('invalid terminal cover socket screw')
    return finish(cover_screw_location(radius,angle,direction)*screw,'steel','drive_terminal_cover_screw')


def make_terminal_pulley_parts(radius=3.5,bore_radius=1.03,angle=-60.,direction=-1):
    """Axially removable flush cover, with an actual counterbored screw seat.

    Cover removal follows the screw in +Z; ferrule then lifts through the
    straight-sided port. No staking, weld or trapped undercut is required.
    """
    assembled=make_terminal_pulley(radius,bore_radius,angle,direction)
    amin=radians(angle)+direction*(-1.15/radius)
    amax=radians(angle)+direction*(.55/radius)
    def p(r,a):return(r*cos(a),r*sin(a),0.)
    inner=radius-1.25;outer=radius+.85;middle=(amin+amax)/2
    edges=[bd.Edge.make_three_point_arc(p(inner,amin),p(inner,middle),p(inner,amax)),
           bd.Edge.make_line(p(inner,amax),p(outer,amax)),
           bd.Edge.make_three_point_arc(p(outer,amax),p(outer,middle),p(outer,amin)),
           bd.Edge.make_line(p(outer,amin),p(inner,amin))]
    access=bd.extrude(bd.Face(bd.Wire(edges)),amount=2.,dir=(0,0,1))
    location=cover_screw_location(radius,angle,direction)
    threaded=location*bd.Pos(0,0,-.25)*bd.Cylinder(.21,1.25,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))
    counterbore=location*bd.Pos(0,0,.25)*bd.Cylinder(.35,1.,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))
    assembled=assembled-threaded-counterbore
    cover=assembled & access
    wheel=assembled-access
    for part in (wheel,cover):
        if len(part.solids())!=1 or not part.is_valid:raise ValueError('invalid terminal insertion-cover split')
    return (finish(wheel,'aluminum','drive_pulley'),
            finish(cover,'aluminum','drive_terminal_cover'))


def terminal_placements():
    """Route-derived native phase and already fanned assembly location."""
    from lib.assembly import joint_location,matrix_location
    from lib.layout import JOINT_BY_NAME,FINGERS,drive_pulley_offset,finger_fan_matrix
    from lib.neutral_routes import NEUTRAL_ROUTES
    from lib.axis_transport import point_at
    fan={f.name:matrix_location(finger_fan_matrix(f)) for f in FINGERS}
    rows=[]
    for route in NEUTRAL_ROUTES:
        j=JOINT_BY_NAME[route['joint']];sign=route['sign']
        placement=joint_location(j)*bd.Pos(0,0,drive_pulley_offset(j,sign))
        if j.system in fan:placement=fan[j.system]*placement
        arc=route['path'][-1]
        # Location applied to a Vertex gives a reliable point transform and
        # keeps axes in the same build123d placement contract as the assembly.
        local=(placement.inverse()*bd.Vertex(*point_at(arc,1))).center()
        angle=round(degrees(atan2(local.Y,local.X)),8)
        radius=j.drive_radius
        if abs(sqrt(local.X**2+local.Y**2)-radius)>1e-6 or abs(local.Z)>1e-6:
            raise ValueError(f'{route["name"]}: route endpoint misses driven groove')
        rows.append(dict(name=route['name'],joint=j,placement=placement,radius=radius,
            bore_radius=3.03 if j.system=='wrist' else 1.03,angle=angle,direction=-sign,route=route))
    return rows


def drive_terminal_bodies():
    """288 individually named pulleys, covers, ferrules, bonds and retaining screws.

    Append AFTER assembly finger fan processing; remove its original pulley
    loop. Every body attaches to the corresponding child joint frame.
    """
    out=[];cache={}
    for row in terminal_placements():
        j=row['joint'];args=(row['radius'],row['bore_radius'],row['angle'],row['direction'])
        if ('pulley',*args) not in cache:
            wheel,cover=make_terminal_pulley_parts(*args)
            cache[('pulley',*args)]=wheel
            cache[('cover',*args)]=cover
        for kind,key,factory in (
            ('drive_pulley',('pulley',*args),lambda:make_terminal_pulley_parts(*args)[0]),
            ('drive_terminal_cover',('cover',*args),lambda:make_terminal_pulley_parts(*args)[1]),
            ('drive_terminal_cover_screw',('cover_screw',args[0],args[2],args[3]),lambda:make_cover_screw(args[0],args[2],args[3])),
            ('drive_terminal_bond_line',('bond',args[0],args[2],args[3]),lambda:make_driven_bond_line(args[0],args[2],args[3])),
            ('drive_terminal_ferrule',('ferrule',args[0],args[2],args[3]),lambda:make_driven_ferrule(args[0],args[2],args[3])),
            ('drive_pulley_grub_screw',('screw',args[1],-args[3]),lambda:make_pulley_grub_screw(args[1],side=-args[3]))):
            if key not in cache:cache[key]=factory()
            body=row['placement']*cache[key]
            body.label=row['name']+'_'+kind
            out.append((body,j.name,j.system,kind))
    return out


def drive_terminal_release_directions():
    """Neutral-world release vectors for staged, collision-free disassembly.

    First withdraw the inclined grub and remove the joint shaft as specified
    by its own hardware sequence. Separate the pulley outboard before lifting
    its cover screw and cover. Withdraw the tendon tip, then lift ferrule
    and resin sleeve. Vectors do not encode stage timing.
    """
    result={}
    for row in terminal_placements():
        placement=row['placement'];origin=(placement*bd.Vertex(0,0,0)).center()
        def world(vector):
            v=(placement*bd.Vertex(*vector)).center()-origin
            return tuple(v)
        z=world((0,0,1));outboard=world((0,0,-row['direction']))
        inclined=world((1/sqrt(2),0,-row['direction']/sqrt(2)))
        for kind in ('drive_terminal_cover_screw','drive_terminal_cover','drive_terminal_ferrule','drive_terminal_bond_line'):
            result[row['name']+'_'+kind]=z
        result[row['name']+'_drive_pulley_grub_screw']=inclined
        result[row['name']+'_drive_pulley']=outboard
    return result


def make_capstan_bond_line():
    """Real resin sleeve on the exact first 0.8 mm of the capstan helix."""
    from lib.capstan import sweep_round
    from lib.capstan_path import full_groove_path,prefix_length
    path=prefix_length(full_groove_path(),.8)
    body=sweep_round(path,.31)-sweep_round(path,.30)
    if not body.is_valid or len(body.solids())!=1:raise ValueError('invalid capstan resin bond line')
    body=finish(body,'dark','capstan_terminal_bond_line')
    body.cad_material={'metalness':0.,'roughness':.44,'clearcoat':.12}
    return body


def capstan_bond_bodies():
    """48 forearm occurrences, matching the existing capstan/ferrule placement."""
    from lib.layout import TENDONS
    prototype=make_capstan_bond_line();bodies=[]
    for tendon in TENDONS:
        x,y,_=tendon['actuator_center'];sign=tendon['sign']
        placement=bd.Pos(x,y,sign*4.)*(bd.Rot(0,0,0) if sign==1 else bd.Rot(0,180,0))*bd.Pos(0,0,29)
        body=placement*prototype;body.label=tendon['actuator']+'_capstan_terminal_bond_line'
        bodies.append((body,'forearm','forearm','capstan_terminal_bond_line'))
    return bodies


def capstan_bond_release_directions():
    """Forearm-side sleeve extraction, after tendon and ferrule removal."""
    from lib.layout import TENDONS
    return {t['actuator']+'_capstan_terminal_bond_line':(0.,0.,float(t['sign'])) for t in TENDONS}


def tendon_end_release_contract():
    """Arc-length release before ferrules/resin are separated from rope ends."""
    from lib.layout import TENDONS,JOINT_BY_NAME
    return {t['name']:{'driven_end_retraction_mm':.85,
            'driven_sweep_delta_deg':t['sign']*degrees(.85/JOINT_BY_NAME[t['joint']].drive_radius),
            'capstan_start_advance_mm':.85,'minimum_sleeve_clearance_mm':.05,
            'blind_cap_extra_travel_mm':0.,'blind_cap_reason':'both tips move away from the cap'}
            for t in TENDONS}
