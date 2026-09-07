"""Removable palm contact pads and seated palm-to-wrist mounting hardware.

Smooth nominal thread envelopes represent M1.6 pad screws and M3 wrist screws.
All bodies use the palm/wrist-flexion frame; mounting datums stay unchanged.
"""
from pathlib import Path
from cadgen import build123d as bd,read_step
from .finish import finish
from .actuator_fasteners import socket_screw,washer
from .palm_frame import PALM_PAD_MOUNTS,PALM_MOUNT_CENTERS


def _check(s,label,material):
    if not s.is_valid or len(s.solids())!=1 or s.volume<=0:
        raise ValueError((label,s.is_valid,len(s.solids()),s.volume))
    return finish(s,material,label)


def make_palm_hardware():
    """Return individually named native pad, carrier and fastener bodies.

    M3 screws seat at Z−8.6. Steel thread inserts seat below the cradle shoe
    at Z−14.6; annular 0.4 mm spacers bridge shoe and palm foot. Each pad has
    a carrier on the existing Ø1.6 threaded palm bore. Its M1.6 screw is
    accessible after removing the replaceable silicone cap. A blind underside
    head pocket preserves a continuous contact face. Carrier top/bond plane
    is Z13.4, pad crown is Z14.7.
    """
    path=Path(__file__).resolve().parents[3]/'STEP/anthropomorphic_hand/imported/palm_frame_integration.step'
    host=read_step(path)
    cradle=read_step(path.parent.parent/'palm_cradle_clearance_review.step')
    parts=[]
    for i,(x,y,z) in enumerate(PALM_PAD_MOUNTS):
        label=f'palm_contact_{i+1}'
        plate=bd.Pos(x,y,13.0)*bd.Cylinder(2.30,.80)
        plate=bd.fillet(plate.edges(),.08)
        carrier=plate-(bd.Pos(x,y,13.0)*bd.Cylinder(.83,1.2))
        carrier=carrier-host
        # Exact rational ellipsoid with its parameter seam on the underside.
        sphere=bd.Rot(90,0,0)*bd.Rot(0,0,-90)*bd.Sphere(1)
        ellipsoid=sphere.transform_geometry(bd.Matrix([[2.7,0,0,0],[0,2.7,0,0],[0,0,1.4,0],[0,0,0,1]]))
        pad=bd.Pos(x,y,13.3)*ellipsoid
        pad=pad-(bd.Pos(x,y,3.4)*bd.Box(10,10,20))
        pad=pad-(bd.Pos(x,y,13.7)*bd.Cylinder(1.20,.80))
        screw=bd.Pos(x,y,13.4)*socket_screw(.80,2.70,1.15,.60)
        parts.extend([_check(pad,label+'_silicone_pad','pad'),_check(carrier,label+'_carrier','dark'),_check(screw,label+'_M1p6_top_socket_screw','steel')])
    for x,y,z in PALM_MOUNT_CENTERS:
        side='radial' if x<0 else 'ulnar';prefix=f'palm_wrist_{side}'
        screw=bd.Pos(x,y,-8.6)*socket_screw(1.50,6.20,2.20,1.40)
        spacer=bd.Pos(x,y,-12.2)*washer(1.85,1.55,.4)
        sleeve=bd.Pos(x,y,-13.4)*bd.Cylinder(1.65,2.4)
        # The ulnar little-finger wrist liner crosses beside the lower flange
        # during flexion. Keep its complete seat lip within the proven R1.85
        # envelope; the sleeve and threaded engagement remain unchanged.
        flange_height=.20 if x>0 else .40
        flange=bd.Pos(x,y,-14.6-flange_height/2)*bd.Cylinder(1.85 if x>0 else 2.20,flange_height)
        insert=sleeve.fuse(flange)-(bd.Pos(x,y,-13.6)*bd.Cylinder(1.50,3.2))
        insert=insert-cradle
        parts.extend([_check(screw,prefix+'_M3_low_head_socket_screw','steel'),_check(spacer,prefix+'_0p4mm_seat_spacer','steel'),_check(insert,prefix+'_M3_flanged_thread_insert','steel')])
    return parts


def palm_hardware_bodies():
    """Use the accepted declared native placements in whole-hand builds."""
    path=Path(__file__).resolve().parents[3]/'STEP/anthropomorphic_hand/palm_hardware_review.step'
    parts=list(read_step(path).children)
    if len(parts)!=15 or any(len(p.solids())!=1 for p in parts):
        raise ValueError('Expected 15 individually named palm pad/mount bodies')
    return [(p,'wrist_flexion','palm','palm_pad' if p.label.endswith('silicone_pad') else 'pad_mount' if p.label.endswith('carrier') else 'fastener') for p in parts]
