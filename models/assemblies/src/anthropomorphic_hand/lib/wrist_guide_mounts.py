"""Six proximal joint-drive liner mouths anchored to their rigid wrist frames."""
from cadgen import build123d as bd
from lib.thumb_remaining_mounts import _attached
from lib.thumb_cmc_mounts import _comb
from lib.wrist import make_wrist_fixed_fork,make_wrist_yaw_carrier
from lib.palm_frame import make_palm_frame_bodies
from lib.finish import finish


def wrist_guide_mounts():
 fixed=make_wrist_fixed_fork();yaw=make_wrist_yaw_carrier()
 palm=next(p for p in make_palm_frame_bodies() if p.label=='palm_metacarpal_truss');out=[]
 import json
 from pathlib import Path
 plans=json.loads(Path(__file__).with_name('wrist_support_paths.json').read_text())
 for target in ('abduction','flexion','cup'):
  for sign in (-1,1):
   label=('palm_cup' if target=='cup' else 'wrist_'+target)+'_drive_mouth_'+str(sign)
   if target=='abduction':point=(-sign*11,-15,sign*5.5);query=(-sign*8,-20,sign*9);host=fixed;frame='forearm';side=-sign
   elif target=='flexion':point=(sign*14,-6,sign*11);query=(sign*17,-4,sign*5);host=yaw;frame='wrist_abduction';side=sign
   else:point=(2,45 if sign>0 else 47,sign*7);query=(15,53,sign*11.5);host=palm;frame='wrist_flexion';side=1
   lower,cap,screws,ears,cutters=_comb([(0,0,0)],(0,1,0),label,ear_sides=(side,))
   place=bd.Pos(*point)*(bd.Rot(0,0,-90) if target=='cup' else bd.Rot(0,0,0))
   lower=place*lower;cap=place*cap;screws=[place*p for p in screws];cutters=[place*p for p in cutters]
   if target=='abduction':
    import numpy as np
    from lib.guide_mounts import _finish
    c=np.array([point[0]+side*1.05,point[1],point[2]]);axis=c+[sign*.20,0,0]
    bore=bd.Pos(*axis)*bd.Cylinder(.22,4)
    lower=lower.fuse(bd.Pos(*(c+[0,0,-.30]))*bd.Cylinder(.33,.48))-bore
    cap=cap.fuse(bd.Pos(*(c+[0,0,.30]))*bd.Cylinder(.33,.48))-bore
    cutters[-1]=bore
    shank=bd.Pos(*axis)*bd.Cylinder(.20,1.08)
    head=bd.Pos(*(axis+[0,0,.74]))*bd.fillet(bd.Cylinder(.40,.40).edges(),.045)
    socket=bd.Pos(*(axis+[0,0,.94]))*bd.extrude(bd.RegularPolygon(.17,6),amount=-.23)
    screw=shank.fuse(head)-socket
    flip=bd.Pos(*axis)*bd.Rot(180,0,0)*bd.Pos(*(-axis))
    screws=[_finish(flip*screw if sign<0 else screw,label+'_liner_'+f'{side:+d}'+'_M0p4_screw')]
   root=(point[0],point[1]-side*1.37,point[2]-.36) if target=='cup' else (point[0]+side*1.37,point[1],point[2]-.36)
   plan=plans.get('cup_positive' if target=='cup' and sign>0 else 'cup_negative' if target=='cup' else 'yaw_positive' if target=='abduction' and sign>0 else '')
   if plan:query=plan['query']
   if target=='abduction' and sign>0:
    # Carry the upper liner jaw from above the moving flex-drive envelope.
    lower,cap=cap,lower;root=plan['root']
   parts=_attached(host,lower,cap,screws,root,query,label,side=side,cutters=cutters,controls=plan['controls'] if plan else None,anchor=plan['host_point'] if plan else None,host_width=4.2 if target=='cup' else 3.8)
   if target=='abduction' and sign>0:
    from lib.neutral_routes import NEUTRAL_ROUTES
    from lib.guide_mounts import _sweep
    from lib.thumb_remaining_mounts import _split
    route=next(r for r in NEUTRAL_ROUTES if r['name']=='wrist_abduction_positive')
    group=next(g for g in route['groups'] if g['label']=='wrist_abduction_positive_wrist_guide')
    tools=[_sweep(seg['points'],.49) for seg in group['path'] if seg['kind']=='bezier']
    cut=[]
    for p in parts:
     cut.extend([p] if 'screw' in p.label else _split(p.cut(*tools),p.label))
    parts=cut
   if target=='flexion':
    from lib.wrist import make_wrist_bushings
    from lib.thumb_remaining_mounts import _split
    bushing=next(p for f,p in make_wrist_bushings() if p.label=='wrist_flex_bushing_'+str(sign))
    parts=[q for p in parts for q in (_split(p-bushing,p.label) if 'screw' not in p.label else [p])]
   if target=='abduction':
    from lib.layout import JOINT_BY_NAME,transforms
    from lib.assembly import joint_location,matrix_location
    from lib.thumb_remaining_mounts import _split
    place=joint_location(JOINT_BY_NAME['wrist_flexion'])*bd.Pos(0,0,-sign*14)
    envelopes=[matrix_location(transforms({'wrist_abduction':angle})['wrist_flexion'])*place*bd.Cylinder(11.7,1.7) for angle in(-20,-10,0,10,20)]
    parts=[q for p in parts for q in (_split(p.cut(*envelopes),p.label) if p.label in (label+'_structural',label+'_liner_cap') else [p])]
   for p in parts:
    if 'screw' in p.label:finish(p,'steel',p.label)
    out.append((p,frame,'palm' if target=='cup' else 'wrist','fastener' if 'screw' in p.label else 'guide_mount'))
 # Both cup drive mouths share the same real palmar rib clamp.
 cup=[p for p,fr,sy,k in out if p.label.startswith('palm_cup_')]
 structural=[p for p in cup if 'structural' in p.label]
 keep=[p for p in cup if 'structural' not in p.label and not (p.label.startswith('palm_cup_drive_mouth_-1_') and ('host_cap' in p.label or 'host_M0p6' in p.label))]
 from lib.thumb_remaining_mounts import _split
 foot=plans['cup_positive']['host_point'];foot=(foot[0]+1.98,foot[1],foot[2]-.85)
 node=(bd.Pos(*foot)*bd.Sphere(.36))-palm
 raw=[s for p in structural for s in p.solids()];body=raw[0].fuse(*raw[1:],node);body=body.cut(*keep)
 out=[entry for entry in out if not entry[0].label.startswith('palm_cup_')]
 for p in [*_split(body,'palm_cup_shared_drive_mouth_structural'),*keep]:out.append((p,'wrist_flexion','palm','fastener' if 'screw' in p.label else 'guide_mount'))
 return out
