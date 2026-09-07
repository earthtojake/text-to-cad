"""Actual pad/mount/fastener CAD pair checks and exact wire clearances."""
import hashlib,itertools,json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from cadgen import build123d as bd
from cadgen._internal.step_scene_loader import load_step_scene
from cadgen.interference import occurrences_from_scene
from lib.fingertip_pad import fingertip_pad_bodies,make_fingertip_pad,PAD_BOND_PLANE_Z
from lib.phalanx import make_phalanx
from lib.layout import JOINTS,FINGERS,assembled_transforms,finger_fan_matrix,THUMB_CMC,THUMB_LENGTHS
from lib.assembly import matrix_location
from lib.assembled_routing import assembled_finger_routes
from lib.thumb_routing import thumb_routes
from lib.transport_guide import path_wire
from check_global_phalanges import named_poses,frame_for,bounds,pair_key
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

OUT=Path(__file__).with_name('fingertip_pad_report.json')
CACHE={}
PAD_BOUNDS={}

def common_volume(a,b):
    common=BRepAlgoAPI_Common(a,b)
    if not common.IsDone():raise RuntimeError('Exact common failed')
    props=GProp_GProps();BRepGProp.VolumeProperties_s(common.Shape(),props)
    return props.Mass()

def overlap_boxes(a,b,margin=0):
    return all(a[i]<=b[i+3]+margin and b[i]<=a[i+3]+margin for i in range(3))

def transformed_box(box,matrix):
    points=np.array([[*v,1.] for v in itertools.product(*[(box[i],box[i+3]) for i in range(3)])])@matrix.T
    return tuple(points[:,:3].min(axis=0))+tuple(points[:,:3].max(axis=0))

def collision_check(parts,label,pose):
    fk=assembled_transforms(pose)
    placed=[(p.name,p.shape.Moved(matrix_location(fk[f]).wrapped)) for p,f in parts]
    boxes=[transformed_box(p.bbox,fk[f]) for p,f in parts];failures=[];exact=0;reuse=0
    for i in range(len(parts)-15):
        for j in range(i+1,len(parts)):
            key=pair_key(parts[i],parts[j],pose)
            if key in CACHE:
                reuse+=1
                if CACHE[key]:failures.append(CACHE[key])
                continue
            if not overlap_boxes(boxes[i],boxes[j]):CACHE[key]=None;continue
            exact+=1;volume=common_volume(placed[i][1],placed[j][1])
            failure={'a':placed[i][0],'b':placed[j][0],'intersection_mm3':volume} if volume>1e-7 else None
            CACHE[key]=failure
            if failure:failures.append(failure)
    return {'label':label,'pose':pose,'exact_pairs':exact,'reused_pairs':reuse,'collisions':failures,'pass':not failures}

def route_check(pads,label,pose,systems):
    fk=assembled_transforms(pose);solids=[]
    for p,frame,system,kind in pads:
        s=matrix_location(fk[frame])*p
        if p.label not in PAD_BOUNDS:PAD_BOUNDS[p.label]=bounds(p.wrapped)
        solids.append((p.label,s,transformed_box(PAD_BOUNDS[p.label],fk[frame])))
    rows=[];tested=0;minimum=999.
    for system in systems:
        routes=thumb_routes(pose) if system=='thumb' else assembled_finger_routes(system,pose)
        for route in routes:
            for group in route['groups']:
                r=.45 if group['guide'] in ('snug_reaction_liner','fixed_curved_guide') else .30
                wire=path_wire(group['path']);box=bounds(wire.wrapped)
                for name,solid,sbox in solids:
                    if not overlap_boxes(box,sbox,r+.5):continue
                    tested+=1;gap=wire.distance_to(solid)-r-1e-6;minimum=min(minimum,gap)
                    if gap < -1e-7:rows.append({'tendon':route['name'],'group':group['label'],'body':name,'gap_mm':gap})
    return {'label':label,'pose':pose,'exact_wire_distances':tested,'minimum_nearby_clearance_mm':None if minimum==999 else minimum,'collisions':rows,'pass':not rows}

if __name__=='__main__':
    pads=fingertip_pad_bodies()
    print('built',len(pads),'pad bodies',flush=True)
    parts=[(SimpleNamespace(name=p.label,shape=p.wrapped,bbox=bounds(p.wrapped)),f) for p,f,s,k in pads]
    # Identical source factories and native placement contract as assembly.py,
    # without parsing the entire routed STEP merely to extract fifteen hosts.
    from lib.thumb_metacarpal import make_thumb_metacarpal
    hostparts=[]
    for finger in FINGERS:
        for i,(length,width) in enumerate(zip(finger.lengths,finger.widths)):
            label=finger.name+'_'+('proximal','middle','distal')[i]+'_frame'
            place=matrix_location(finger_fan_matrix(finger))*bd.Pos(finger.x,finger.base_y+sum(finger.lengths[:i]),0)
            s=place*make_phalanx(length,width,i==2,label)
            hostparts.append((SimpleNamespace(name=label,shape=s.wrapped,bbox=bounds(s.wrapped)),frame_for(label)))
    for i,(length,width) in enumerate(zip(THUMB_LENGTHS,(19.,16.,13.))):
        label='thumb_'+('metacarpal','proximal','distal')[i]+'_frame'
        s=make_thumb_metacarpal(label=label) if i==0 else make_phalanx(length,width,i==2,label)
        s=bd.Pos(*THUMB_CMC)*bd.Rot(0,0,45)*bd.Pos(0,sum(THUMB_LENGTHS[:i]),0)*s
        hostparts.append((SimpleNamespace(name=label,shape=s.wrapped,bbox=bounds(s.wrapped)),frame_for(label)))
    assert len(hostparts)==15
    parts+=hostparts
    root=Path('models/assemblies/src/anthropomorphic_hand/lib')
    report={'pass':False,'source_sha256':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ('fingertip_pad.py','phalanx.py','thumb_metacarpal.py','layout.py')},'body_count':len(pads),'host_phalanges':15,'mounts':[],'body_rows':[],'route_rows':[]}
    prior=json.loads(OUT.read_text()) if OUT.exists() else {}
    if prior.get('source_sha256')==report['source_sha256'] and prior.get('body_count')==len(pads):
        report['mounts']=prior.get('mounts',[])
        report['body_rows']=prior.get('body_rows',[])
        for row in report['body_rows']:
            failures={(r['a'],r['b']):r for r in row['collisions']}
            for i in range(len(pads)):
                for j in range(i+1,len(parts)):
                    CACHE[pair_key(parts[i],parts[j],row['pose'])]=failures.get((parts[i][0].name,parts[j][0].name))
        print('resuming',len(report['body_rows']),'proven body poses',flush=True)
    for name,length,width in [(f.name,f.lengths[2],f.widths[2]) for f in FINGERS]+[('thumb',21.,13.)]:
        if any(r['name']==name and r['pass'] for r in report['mounts']):continue
        local=make_fingertip_pad(name,length,width);host=make_phalanx(length,width,True)
        print('mount',name,'contacts',flush=True)
        row={'name':name,'bridge_host_gap_mm':local[1].distance_to(host),'pad_bridge_gap_mm':local[0].distance_to(local[1]),'screw_head_seat_gap_mm':[s.distance_to(local[1]) for s in local[2:4]],'insert_host_gap_mm':[s.distance_to(host) for s in local[4:]],'screw_insert_gap_mm':[local[i+2].distance_to(local[i+4]) for i in range(2)],'pair_overlap_mm3':[]}
        print('mount',name,'pair overlaps',flush=True)
        for a,b in itertools.combinations([host,*local],2):
            row['pair_overlap_mm3'].append(common_volume(a.wrapped,b.wrapped))
        row['pass']=max(row['bridge_host_gap_mm'],row['pad_bridge_gap_mm'],*row['screw_head_seat_gap_mm'],*row['insert_host_gap_mm'],*row['screw_insert_gap_mm'])<1e-6 and max(row['pair_overlap_mm3'])<1e-7
        report['mounts'].append(row)
    samples=named_poses()
    for joint in JOINTS:
        lo,hi=joint.limits
        samples.extend((f'{joint.name}_{q:g}',{joint.name:float(q)}) for q in sorted(set([lo,hi,0.]+list(np.arange(lo,hi+1e-8,10.)))))
    for label,pose in samples:
        if any(r['label']==label for r in report['body_rows']):continue
        row=collision_check(parts,label,pose);report['body_rows'].append(row)
        OUT.write_text(json.dumps(report,indent=2)+'\n');print('bodies',label,row['pass'],row['collisions'],flush=True)
    pinch=named_poses()[2][1];fk=assembled_transforms(pinch)
    a=next(matrix_location(fk[f])*p for p,f,s,k in pads if s=='index' and k=='fingertip_pad')
    b=next(matrix_location(fk[f])*p for p,f,s,k in pads if s=='thumb' and k=='fingertip_pad')
    report['precision_pinch']={'exact_native_pad_gap_mm':a.distance_to(b),'intersection_mm3':common_volume(a.wrapped,b.wrapped),'silicone_lower_trim_z_mm':PAD_BOND_PLANE_Z}
    for label,pose in samples:
        if len(pose)>1 or not pose:systems=[f.name for f in FINGERS]+['thumb']
        else:
            system=next(j.system for j in JOINTS if j.name==next(iter(pose)))
            if system not in [f.name for f in FINGERS]+['thumb']:continue
            systems=[system]
        row=route_check(pads,label,pose,systems);report['route_rows'].append(row)
        OUT.write_text(json.dumps(report,indent=2)+'\n');print('routes',label,row['pass'],row['collisions'],flush=True)
    report['scope']='Thirty real pad/mount/screw/insert bodies against each other and all fifteen native assembled phalanges; full independent range samples every10 degrees plus endpoints, neutral, full fist and solved precision pinch. Exact swept-wire radius clearance against all30 bodies for every moving-system route, all42 hand routes in named poses. No claim of all-joint Cartesian-product exhaustive sweep.'
    report['pass']=all(r['pass'] for k in ('mounts','body_rows','route_rows') for r in report[k]) and report['precision_pinch']['intersection_mm3']<1e-7 and report['precision_pinch']['exact_native_pad_gap_mm']<.001
    OUT.write_text(json.dumps(report,indent=2)+'\n')
    if not report['pass']:raise SystemExit(1)
