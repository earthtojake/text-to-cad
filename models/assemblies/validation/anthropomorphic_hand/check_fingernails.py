import faulthandler
faulthandler.enable()
faulthandler.dump_traceback_later(90,repeat=True)
"""Native solids, exact host subset and 225 immutable-route/body pose gates."""
import gzip,hashlib,itertools,json,sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
ROOT=Path(__file__).parent
sys.path.insert(0,str(ROOT.parents[1]/'src/anthropomorphic_hand'))
from cadgen import build123d as bd,read_step
from lib.assembly import matrix_location
from lib.layout import assembled_transforms,FINGERS,THUMB_CMC,THUMB_LENGTHS,finger_fan_matrix
from lib.transport_guide import path_wire
from lib.path_analysis import sample_path
from lib.phalanx import make_phalanx
from lib.thumb_metacarpal import make_thumb_metacarpal
from check_global_phalanges import frame_for,pair_key
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
def bounds(shape):
    box=Bnd_Box();BRepBndLib.Add_s(shape,box,False);return box.Get()
from check_fingertip_pads import common_volume,transformed_box,overlap_boxes
from phalanx_before_nail import make_phalanx as old_phalanx

SOURCE=ROOT.parents[1]/'src/anthropomorphic_hand/lib'
STEP=ROOT.parents[1]/'STEP/anthropomorphic_hand/fingernail_review.step'
OUT=ROOT/'fingernail_acceptance.json'
def leaves(p):return [x for c in p.children for x in leaves(c)] if p.children else [p]
def getframe(p):
    f=frame_for(p.label)
    if f:return f
    name=p.label.split('_')[0]
    return name+('_ip' if name=='thumb' else '_dip')
def numeric_bounds(path):
    pts=[]
    for seg in path:
        if seg['kind']=='bezier':pts.extend(seg['points'])
        elif seg['kind']=='line':pts.extend([seg['start'],seg['end']])
        elif seg['kind']=='arc':
            c=np.asarray(seg['center']);r=np.linalg.norm(np.asarray(seg['start'])-c);pts.extend([c-r,c+r])
        else:raise ValueError(seg['kind'])
    p=np.asarray(pts);return tuple(p.min(axis=0))+tuple(p.max(axis=0))

print("loading native",flush=True)
native=leaves(read_step(STEP));nails=[p for p in native if 'fingernail' in p.label];other=[p for p in native if p not in nails]
print("native loaded",len(native),flush=True)
assert len(nails)==30 and len(native)==74,(len(nails),len(native))
thumb=bd.Pos(*THUMB_CMC)*bd.Rot(0,0,45)*make_thumb_metacarpal(label='thumb_metacarpal_frame');other.append(thumb)
print("thumb made",flush=True)
parts=[(SimpleNamespace(name=p.label,shape=p,bbox=bounds(p.wrapped)),getframe(p)) for p in nails+other]
# Exact source-primitive envelopes stay tight for rational ellipsoids;
# every finishing/counterbore Boolean is subtractive within these boxes.
for part,frame in parts[:len(nails)]:
    name=part.name.split('_')[0]
    if name=='thumb':
        length,width=21.,13.;c=2**-.5
        m=np.array([[c,-c,0,THUMB_CMC[0]-63*c],[c,c,0,THUMB_CMC[1]+63*c],[0,0,1,0],[0,0,0,1]])
    else:
        finger=next(f for f in FINGERS if f.name==name);length,width=finger.lengths[2],finger.widths[2]
        t=np.eye(4);t[:3,3]=[finger.x,finger.base_y+sum(finger.lengths[:2]),0];m=finger_fan_matrix(finger)@t
    y=.71*length;bx=width/2-.825
    if part.name.endswith('dorsal_fingernail'):
        box=(-width*.37,y+.8-length*.27,-4.72,width*.37,y+.8+length*.27,-3.36)
    elif part.name.endswith('saddle'):
        box=(-max(bx+1.05,width*.355),min(y-1.05,y+.8-length*.255),-4.41,max(bx+1.05,width*.355),max(y+1.05,y+.8+length*.255),-2.58)
    else:
        x=(-1 if '_radial_' in part.name else 1)*bx
        radius=.79 if part.name.endswith('screw') else .74
        low,high=(-4.43,1.60) if part.name.endswith('screw') else (-3.65,1.65)
        box=(x-radius,y-radius,low,x+radius,y+radius,high)
    box=tuple(v+(-.001 if i<3 else .001) for i,v in enumerate(box))
    part.bbox=transformed_box(box,m)

print("all bounds ready",flush=True)
report={'pass':False,'native_sha256':hashlib.sha256(STEP.read_bytes()).hexdigest(),'source_sha256':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in ('fingernail.py','phalanx.py','fingertip_pad.py','layout.py')},'new_body_count':len(nails),'native_review_body_count':len(native),'host_subset':[],'mounts':[],'rows':[]}
prior=json.loads(OUT.read_text()) if OUT.exists() else {}
if prior.get('native_sha256')==report['native_sha256'] and prior.get('source_sha256')==report['source_sha256']:
    report=prior
for name,l,w in [(f.name,f.lengths[2],f.widths[2]) for f in FINGERS]+[('thumb',21.,13.)]:
    if any(r['finger']==name and r['pass'] for r in report['mounts']):continue
    new=make_phalanx(l,w,True);old=old_phalanx(l,w,True)
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BOPAlgo import BOPAlgo_GlueEnum
    from OCP.TopTools import TopTools_ListOfShape
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    args=TopTools_ListOfShape();args.Append(new.wrapped)
    tools=TopTools_ListOfShape();tools.Append(old.wrapped)
    cut=BRepAlgoAPI_Cut();cut.SetArguments(args);cut.SetTools(tools)
    cut.SetGlue(BOPAlgo_GlueEnum.BOPAlgo_GlueShift);cut.SetRunParallel(False);cut.Build()
    if not cut.IsDone():raise RuntimeError('host subset Boolean failed')
    props=GProp_GProps();BRepGProp.VolumeProperties_s(cut.Shape(),props);added_v=props.Mass()
    print('subset',name,added_v,flush=True)
    # Verify unchanged pad support region (Z >= 1.95) as exact volume equality.
    region=bd.Pos(0,l/2,11.95)*bd.Box(50,60,20)
    a=new&region;b=old&region
    delta=abs(a.volume-b.volume)
    report['host_subset'].append({'finger':name,'added_material_mm3':added_v,'removed_material_mm3':old.volume-new.volume,'pad_region_volume_difference_mm3':delta,'pass':added_v<1e-7 and delta<1e-7})
    group=[p for p in nails if p.label.startswith(name+'_')];host=next(p for p in native if p.label==name+'_distal_frame');plate=next(p for p in group if p.label.endswith('dorsal_fingernail'));saddle=next(p for p in group if p.label.endswith('saddle'))
    contacts={'nail_saddle_gap':plate.distance_to(saddle),'saddle_host_gap':saddle.distance_to(host)}
    for side in ('radial','ulnar'):
        screw=next(p for p in group if side in p.label and p.label.endswith('screw'));insert=next(p for p in group if side in p.label and p.label.endswith('insert'))
        contacts[side+'_screw_saddle_gap']=screw.distance_to(saddle);contacts[side+'_screw_insert_gap']=screw.distance_to(insert);contacts[side+'_insert_host_gap']=insert.distance_to(host)
    report['mounts'].append({'finger':name,'contacts_mm':contacts,'pass':max(contacts.values())<1e-6})
    print('mount',name,report['host_subset'][-1],report['mounts'][-1],flush=True)
manifest=json.loads((ROOT/'static_route_packet_manifest.json').read_text());assert manifest['complete'] and manifest['sample_count']==225
report['route_source_sha256']=manifest['source_sha256'];cache={};routecache={}
for row in report['rows']:
    pose=next(s['pose'] for s in manifest['rows'] if s['label']==row['sample'])
    failures={(r['a'],r['b']):r['intersection_mm3'] for r in row['body_collisions']}
    for i in range(len(nails)):
        for j in range(i+1,len(parts)):
            cache[pair_key(parts[i],parts[j],pose)]=failures.get((parts[i][0].name,parts[j][0].name),0.)
print('resuming',len(report['rows']),'certified poses',flush=True)
for sample in manifest['rows']:
    if any(r['sample']==sample['label'] for r in report['rows']):continue
    fk=assembled_transforms(sample['pose']);posed=[type(p.shape)(obj=p.shape.wrapped.Moved(matrix_location(fk[f]).wrapped)) for p,f in parts];boxes=[transformed_box(p.bbox,fk[f]) for p,f in parts]
    bad=[];exact=0
    for i in range(len(nails)):
        for j in range(i+1,len(parts)):
            key=pair_key(parts[i],parts[j],sample['pose'])
            if key not in cache:
                if not overlap_boxes(boxes[i],boxes[j]):cache[key]=0.;continue
                cache[key]=common_volume(posed[i].wrapped,posed[j].wrapped);exact+=1
            if cache[key]>1e-7:bad.append({'a':parts[i][0].name,'b':parts[j][0].name,'intersection_mm3':cache[key]})
    packet=json.loads(gzip.decompress(Path(sample['file']).read_bytes()));assert packet['source_sha256']==manifest['source_sha256'] and len(packet['routes'])==48
    routebad=[];wirechecks=0;minimum=999.
    for route in packet['routes']:
        for g in route['groups']:
            radius=.45 if g.get('guide') in ('snug_reaction_liner','fixed_curved_guide','compliant_wrist_guide','open_saddle') else .3
            box=numeric_bounds(g['path']);near=[i for i in range(len(nails)) if overlap_boxes(box,boxes[i],radius+.02)]
            if not near:continue
            # Certified continuous-curve reserve: each point on the exact
            # curve lies within .250001 mm of a .5 mm arclength sample.
            points=sample_path(g['path'],.5)
            near=[i for i in near if float(np.linalg.norm(np.maximum(0,np.maximum(np.asarray(boxes[i][:3])-points,points-np.asarray(boxes[i][3:]))),axis=1).min()) <= radius+.250001]
            if not near:continue
            wire=path_wire(g['path']);wb=bounds(wire.wrapped)
            for i in near:
                if not overlap_boxes(wb,boxes[i],radius+.02):continue
                gap=wire.distance_to(posed[i])-radius-2e-6;wirechecks+=1;minimum=min(minimum,gap)
                if gap< -1e-7:routebad.append({'body':parts[i][0].name,'tendon':route['name'],'group':g['label'],'clearance_mm':gap})
    row={'sample':sample['label'],'exact_body_pairs':exact,'body_collisions':bad,'exact_route_distances':wirechecks,'minimum_nearby_route_gap_mm':None if minimum==999 else minimum,'route_collisions':routebad,'pass':not bad and not routebad};report['rows'].append(row)
    OUT.write_text(json.dumps(report,indent=2)+'\n');print(sample['label'],row,flush=True)
report['sample_count']=len(report['rows']);report['pass']=len(report['rows'])==225 and all(r['pass'] for k in ('host_subset','mounts','rows') for r in report[k]);report['scope']='Thirty native nail-system solids versus each other, all thirty accepted pad-system solids and all fifteen native phalanges, at225 immutable packet poses (independent full ranges and three named whole-hand poses). Exact CAD intersection and OCCT curve-to-solid distance after conservative bounds. Hosts are exact material subsets. No claim about untested joint combinations or other future hardware.'
OUT.write_text(json.dumps(report,indent=2)+'\n')
if not report['pass']:raise SystemExit(1)
