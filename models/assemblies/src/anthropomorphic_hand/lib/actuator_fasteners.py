"""Seated polished fasteners for all48 actuators and the reaction chassis.

Socket screws are smooth nominal thread envelopes; helical threads are not
modelled. Each captive nut/insert has a matching nominal bore. Three miniature
M0.8 flanged steel inserts occupy each face's staggered frame holes; their
0.05mm flanges bridge the specified cartridge/frame seat gaps. All copies
share factory-built prototypes. No shaft, route or actuator datum is changed.
"""
from math import sin,cos,radians
from cadgen import build123d as bd
from .finish import finish
from .layout import TENDONS
from .forearm_frame import WRIST_FRAME_EYES,REAR_FLANGE_BORES


def _cyl(radius,height,z=0):
    return bd.Pos(0,0,z)*bd.Cylinder(radius,height,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))


def _done(shape,label):
    if len(shape.solids())!=1 or not shape.is_valid or shape.volume<=0:
        raise ValueError(f'{label}: expected one valid positive solid')
    return finish(shape,'steel',label)


def socket_screw(radius,length,head_radius,head_height,label='polished_socket_screw'):
    """Head seats at Z0, tip at -length, six-sided recessed socket at top."""
    head=_cyl(head_radius,head_height)
    head=bd.fillet(head.edges(),min(.08,head_height*.12))
    shaft=_cyl(radius,length+.04,-length)
    shaft=bd.fillet(shaft.edges().sort_by(bd.Axis.Z)[:1],min(.045,radius*.08))
    body=head.fuse(shaft)
    socket=bd.Pos(0,0,head_height+.01)*bd.extrude(bd.RegularPolygon(head_radius*.46,6),amount=-head_height*.64)
    return _done(body-socket,label)


def hex_nut(radius,bore,height,label='polished_hex_nut'):
    body=bd.extrude(bd.RegularPolygon(radius,6),amount=height)
    body=bd.chamfer(body.edges().filter_by(bd.Axis.Z,reverse=True),min(.065,height*.10))
    body=body-_cyl(bore,height+.2,-.1)
    # Actual machined lead-ins; keep the load-bearing faces planar.
    circles=body.edges().filter_by(bd.GeomType.CIRCLE)
    body=bd.chamfer(circles,min(.025,height*.05))
    return _done(body,label)


def washer(radius,bore,height,label='polished_seat_washer'):
    return _done(_cyl(radius,height)-_cyl(bore,height+.2,-.1),label)


def frame_insert():
    # Z+.35..+.40 flange is the actual seat shim. R.54 is the existing reamed
    # frame bore; a nominal zero-clearance fit records the insert contact.
    body=_cyl(.54,.70,-.35).fuse(_cyl(.65,.05,.35))
    return _done(body-_cyl(.40,.95,-.45),'M0p8_flanged_frame_insert')


def wrist_insert():
    # Captive thin-wall M3 thread insert remains inside the existing3.3mm
    # eye bore. Its rear flange bridges the0.10mm frame/fork interface gap.
    body=_cyl(1.65,2.90,-2.90).fuse(_cyl(2.50,.10))
    return _done(body-_cyl(1.50,3.20,-3.),'M3_wrist_captive_flanged_thread_insert')


def actuator_fastener_prototypes():
    return {
        'motor_tie_screw':socket_screw(.50,27.15,.80,.55),
        'motor_captive_nut':hex_nut(.85,.50,.80),
        'motor_seat_shim':washer(.80,.54,.05),
        'cartridge_clamp_screw':socket_screw(.40,2.05,.75,.60),
        'cartridge_frame_insert':frame_insert(),
        'capstan_retainer_screw':socket_screw(.50,1.50,1.65,.80),
        'wrist_mount_screw':socket_screw(1.50,6.10,2.70,2.20),
        'M3_nut':hex_nut(2.85,1.50,2.20),
        'M3_washer':washer(2.70,1.56,.20),
        'wrist_threaded_insert':wrist_insert(),
        'rear_flange_screw':socket_screw(1.50,7.60,2.70,2.20),
        'rear_chassis_screw':socket_screw(.80,6.80,1.40,1.20),
        'rear_chassis_nut':hex_nut(1.45,.80,1.40),
        'rear_chassis_washer':washer(1.40,.85,.20),
    }


def actuator_fasteners():
    """Return (named body, forearm frame, forearm system, kind) occurrences."""
    prototypes=actuator_fastener_prototypes();bodies=[]
    def add(key,loc,name,kind='fastener'):
        body=loc*prototypes[key];body.label=name
        bodies.append((body,'forearm','forearm',kind))
    for tendon in TENDONS:
        x,y,_=tendon['actuator_center'];sign=tendon['sign']
        station=bd.Pos(x,y,0)*bd.Rot(0,180 if sign<0 else 0,0)
        name=tendon['actuator']
        for i,angle in enumerate((0,120,240),1):
            radial=bd.Pos(5.7*cos(radians(angle)),5.7*sin(radians(angle)),0)
            add('motor_tie_screw',station*radial*bd.Pos(0,0,29.50),name+f'_motor_tie_screw_{i}')
            add('motor_captive_nut',station*radial*bd.Pos(0,0,2.25),name+f'_motor_captive_nut_{i}')
            add('motor_seat_shim',station*radial*bd.Pos(0,0,3.95),name+f'_motor_seat_shim_{i}','spacer')
        for i,angle in enumerate((60,180,300),1):
            radial=bd.Pos(7.55*cos(radians(angle)),7.55*sin(radians(angle)),0)
            add('cartridge_clamp_screw',station*radial*bd.Pos(0,0,1.75),name+f'_cartridge_clamp_screw_{i}')
            add('cartridge_frame_insert',station*radial,name+f'_cartridge_frame_insert_{i}','threaded_insert')
        add('capstan_retainer_screw',station*bd.Pos(0,0,37.25),name+'_capstan_retainer_screw')
    # Native screw +Z points to the rear; its shank runs forward along +Y.
    orient=bd.Rot(90,0,0)
    for i,(x,y,z) in enumerate(WRIST_FRAME_EYES,1):
        base=bd.Pos(x,-34.80,z)*orient
        add('wrist_mount_screw',base,f'wrist_frame_mount_{i}_M3_socket_screw')
        add('M3_washer',bd.Pos(x,-34.60,z)*orient,f'wrist_frame_mount_{i}_rear_washer','spacer')
        add('wrist_threaded_insert',bd.Pos(x,-31.50,z)*orient,f'wrist_frame_mount_{i}_M3_captive_flanged_insert','threaded_insert')
    for i,(x,y,z) in enumerate(REAR_FLANGE_BORES,1):
        add('rear_flange_screw',bd.Pos(x,-280.20,z)*orient,f'rear_external_mount_{i}_M3_socket_screw')
        add('M3_washer',bd.Pos(x,-280.,z)*orient,f'rear_external_mount_{i}_rear_washer','spacer')
        add('M3_washer',bd.Pos(x,-275.80,z)*orient,f'rear_external_mount_{i}_front_washer','spacer')
        add('M3_nut',bd.Pos(x,-273.60,z)*orient,f'rear_external_mount_{i}_M3_nut')
    for i,(x,z) in enumerate(((x,z) for x in (-39.,39.) for z in (-3.3,3.3)),1):
        add('rear_chassis_screw',bd.Pos(x,-280.20,z)*orient,f'rear_chassis_mount_{i}_M1p6_socket_screw')
        add('rear_chassis_washer',bd.Pos(x,-280.,z)*orient,f'rear_chassis_mount_{i}_rear_washer','spacer')
        add('rear_chassis_nut',bd.Pos(x,-273.95,z)*orient,f'rear_chassis_mount_{i}_M1p6_captive_nut')
    return bodies
