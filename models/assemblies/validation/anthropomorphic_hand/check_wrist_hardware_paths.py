"""Exact complete-curve radius clearance against real wrist hardware."""
import sys,json
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/anthropomorphic_hand'))
from cadgen import build123d as bd
from lib.wrist import make_wrist_fixed_fork,make_wrist_yaw_carrier,make_wrist_palm_cradle,make_wrist_bushings
from lib.pulley import make_pulley
from lib.layout import transforms
from lib.assembly import matrix_location
from lib.transport_guide import path_wire

def prototypes():
    result=[('forearm',make_wrist_fixed_fork()),('wrist_abduction',make_wrist_yaw_carrier()),('wrist_flexion',make_wrist_palm_cradle())]
    result += [('forearm' if frame=='fixed' else 'wrist_abduction',shape) for frame,shape in make_wrist_bushings()]
    for sign in (-1,1):
        result.append(('wrist_abduction',bd.Pos(0,-9,sign*5.5)*make_pulley(11,bore_radius=3.03,label=f'wrist_yaw_drive_{sign}')))
        result.append(('wrist_flexion',bd.Pos(sign*14,0,0)*bd.Rot(0,90,0)*make_pulley(11,bore_radius=3.03,label=f'wrist_flex_drive_{sign}')))
    yaw=bd.Pos(0,-9,0)*bd.Cylinder(3,25);yaw.label='yaw_shaft_radius_envelope'
    flex=bd.Cylinder(3,46,rotation=(0,90,0));flex.label='flex_shaft_radius_envelope'
    result += [('wrist_abduction',yaw),('wrist_flexion',flex)]
    return result

def bbox_gap(a,b):
    return sum(max(0,getattr(a.min,k)-getattr(b.max,k),getattr(b.min,k)-getattr(a.max,k))**2 for k in ('X','Y','Z'))**.5

root=Path(__file__).parent;shapes=prototypes()
if '--all' in sys.argv:samples=json.loads((root/'wrist_motion_routes.json').read_text())['samples']
else:samples=[{'pose':{},'routes':json.loads((root/'wrist_transport_neutral.json').read_text())['routes']}]
rows=[]
for sample in samples:
    fk=transforms(sample['pose']);placed=[matrix_location(fk[frame])*shape for frame,shape in shapes]
    bounds=[s.bounding_box() for s in placed];failures=[];count=0;minimum=float('inf')
    for route in sample['routes']:
        wire=path_wire(route['path']);wb=wire.bounding_box()
        for shape,sb in zip(placed,bounds):
            if bbox_gap(wb,sb)>.55:continue
            distance=wire.distance_to(shape)-1e-6;count+=1;minimum=min(minimum,distance-.45)
            if distance<.45:
                failures.append({'tendon':route['name'],'body':shape.label,'centerline_distance_mm':distance,'required_mm':.45})
    row={'pose':sample['pose'],'exact_distances':count,'minimum_checked_clearance_mm':minimum,'collisions':failures,'clear':not failures}
    rows.append(row);print(row,flush=True)
    (root/'wrist_hardware_paths.json').write_text(json.dumps({'scope':'Complete wire radius-envelope check against13 wrist frames/bushings/pulleys/shaft envelopes; palm and final shaft hardware pending','samples':rows},indent=2))
assert all(r['clear'] for r in rows)
