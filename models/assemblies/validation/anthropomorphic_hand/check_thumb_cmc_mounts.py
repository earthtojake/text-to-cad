"""Independent mount/route clearances and neutral mating checks."""
import sys,json,itertools
from pathlib import Path
import numpy as np
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from cadgen import build123d as bd
from lib.thumb_cmc_mounts import thumb_cmc_mounts
from lib.thumb_routing import thumb_routes
from lib.neutral_routes import NEUTRAL_ROUTES
from lib.transport_guide import path_wire
from lib.layout import transforms
from lib.assembly import matrix_location
from lib.palm_frame import make_palm_frame_bodies
from check_thumb_full import thumb_hardware
from check_middle_hardware_paths import bbox_gap,rounded_data
from lib.finger_routing import transform_path
root=Path('models/assemblies/validation/anthropomorphic_hand')
if '--step' in sys.argv:
 from cadgen import read_step
 assembly=read_step('models/assemblies/STEP/anthropomorphic_hand/thumb_cmc_mounts_review.step')
 mounts=[(p,'wrist_flexion' if p.label.startswith('thumb_cmc_parent_') else 'thumb_cmc_flexion','thumb','guide_mount') for p in assembly.children]
elif '--parent-only' in sys.argv:
 from lib.thumb_cmc_mounts import make_cmc_parent_comb
 mounts=[(bd.Pos(-35,36,0)*bd.Rot(0,0,45)*p,'wrist_flexion','thumb','guide_mount') for p in make_cmc_parent_comb()]
else:mounts=thumb_cmc_mounts()
all_mounts=list(mounts)
if '--modified-only' in sys.argv:mounts=[m for m in mounts if m[0].label=='thumb_cmc_child_four_liner_comb_structural_jaw']
print('BUILT',len(mounts),flush=True)

others=[r for r in NEUTRAL_ROUTES if not r['name'].startswith('thumb_')]
certificate=json.loads((root/'thumb_cmc_final_certificate.json').read_text());poses=[r['pose'] for r in certificate['static_rows']]
poses.sort(key=lambda p:0 if not any(p.values()) else 1 if p.get('thumb_cmc_flexion')==65 and p.get('thumb_cmc_abduction')==45 else 2)
if '--neutral-only' in sys.argv:poses=[{}]
if '--pinch' in sys.argv:
 poses=[json.loads((root/'pinch_contact_candidate.json').read_text())['pose']];others=[]
hardware=[] if '--routes-only' in sys.argv else thumb_hardware()+([] if '--thumb-only' in sys.argv else [(p.label,'wrist_flexion',p) for p in make_palm_frame_bodies()])
if '--modified-only' in sys.argv and '--routes-only' not in sys.argv:hardware += [(p.label,f,p) for p,f,s,k in all_mounts if p.label!='thumb_cmc_child_four_liner_comb_structural_jaw']
route_cache={};solid_cache={};mount_pair_cache={}
report={'scope':'twelve CMC endpoint mounts versus all48tendons at25CMCposes, thumb hardware and palm-frame solids','body_count':len(mounts),'rows':[],'pass':False};out=root/('thumb_cmc_parent_mounts_neutral_report.json' if '--parent-only' in sys.argv else 'thumb_cmc_mounts_neutral_report.json' if '--neutral-only' in sys.argv else 'thumb_cmc_mounts_report.json')
def numeric_bounds(path):
 points=[]
 for seg in path:
  if seg['kind']=='bezier':points.extend(seg['points'])
  elif seg['kind']=='line':points.extend([seg['start'],seg['end']])
  elif seg['kind']=='arc':
   c=np.asarray(seg['center']);r=np.linalg.norm(np.asarray(seg['start'])-c);points.extend([c-r,c+r])
  else:raise ValueError(seg['kind'])
 a=np.asarray(points);return a.min(axis=0),a.max(axis=0)
def numeric_gap(bounds,box):
 lo,hi=bounds;bmin=np.array(tuple(box.min));bmax=np.array(tuple(box.max));return float(np.linalg.norm(np.maximum(0,np.maximum(lo-bmax,bmin-hi))))
if '--pinch' in sys.argv:
 out=root/'thumb_cmc_mounts_final_pinch_report.json';report['scope']='exact final pinch thumb routes against CMC mounts, thumb hardware and palm solids'
if '--routes-only' in sys.argv:
 out=root/('thumb_cmc_mounts_pinch_routes_report.json' if '--pinch' in sys.argv else 'thumb_cmc_mounts_routes_report.json');report['scope']='actual tendon-to-mount distances only; assembled-body overlaps checked separately'
if '--bodies-only' in sys.argv:
 out=root/'thumb_cmc_mounts_bodies_report.json';report['scope']='assembled mount/body overlap checks only; tendon clearances checked separately'
if '--thumb-only' in sys.argv:
 out=root/('thumb_cmc_mounts_pinch_thumb_bodies_report.json' if '--pinch' in sys.argv else 'thumb_cmc_mounts_thumb_bodies_report.json');report['scope']='CMC mounts versus moving thumb hardware and each other; palm host certificate explicitly pending palm rebuild'
if '--modified-only' in sys.argv:
 out=root/('thumb_cmc_changed_strut_routes_report.json' if '--routes-only' in sys.argv else 'thumb_cmc_changed_strut_pinch_report.json' if '--pinch' in sys.argv else 'thumb_cmc_changed_strut_body_report.json');report['scope']='changed child four-liner structural jaw only; other bodies verified separately; palm host pending'
for pose in poses:
 fk=transforms(pose);parts=[(matrix_location(fk[f])*p,f) for p,f,s,k in mounts];bb=[p.bounding_box() for p,f in parts];routes=[] if '--bodies-only' in sys.argv else others+thumb_routes(pose);bad=[];checks=0
 for route in routes:
  for group in route['groups']:
   radius=.45 if group.get('guide') in('snug_reaction_liner','fixed_curved_guide','compliant_wrist_guide') else .3
   bounds=numeric_bounds(group['path'])
   if all(numeric_gap(bounds,pb)>radius+.01 for pb in bb):continue
   wire=path_wire(group['path']);wb=wire.bounding_box()
   for (p,f),pb in zip(parts,bb):
    if bbox_gap(wb,pb)>radius+.01:continue
    local=rounded_data(transform_path(group["path"],np.linalg.inv(fk[f])));key=(p.label,json.dumps(local,sort_keys=True))
    if key not in route_cache:route_cache[key]=path_wire(local).distance_to(next(q for q,ff,ss,kk in mounts if q.label==p.label))-2e-6
    distance=route_cache[key];checks+=1
    if distance<radius-1e-7:bad.append({'mount':p.label,'tendon':route['name'],'group':group['label'],'centerline_distance':distance,'radius':radius})
 solid_bad=[];contacts=[]
 print('ROUTE_GATE',pose,checks,bad,flush=True)
 for (p,f),pb in zip(parts,bb):
  for name,frame,original in hardware:
   s=matrix_location(fk[frame])*original
   if bbox_gap(pb,s.bounding_box())>.001:continue
   key=(p.label,name,tuple(np.round((np.linalg.inv(fk[f])@fk[frame]).ravel(),8)))
   if key not in solid_cache:
    print("SOLID_CHECK",p.label,name,flush=True);common=p&s;solid_cache[key]=sum(b.volume for b in common.solids()) if common else 0.
   v=solid_cache[key]
   if v>1e-7:
    conflict={'mount':p.label,'hardware':name,'overlap_volume_mm3':v};solid_bad.append(conflict);print('SOLID_CONFLICT',conflict,flush=True)
   elif (('structural_jaw' in p.label or '_rail_' in p.label or '_palm_rib_cap' in p.label) and name==('palm_metacarpal_truss' if p.label.startswith('thumb_cmc_parent_') else 'frame_0')) and p.distance_to(s)<1e-6:contacts.append({'mount':p.label,'hardware':name})
 for i,j in ([] if '--routes-only' in sys.argv else itertools.combinations(range(len(parts)),2)):
  if bbox_gap(bb[i],bb[j])>.001:continue
  key=(parts[i][0].label,parts[j][0].label,tuple(np.round((np.linalg.inv(fk[parts[i][1]])@fk[parts[j][1]]).ravel(),8)))
  if key not in mount_pair_cache:
   print("MOUNT_PAIR",parts[i][0].label,parts[j][0].label,flush=True);common=parts[i][0]&parts[j][0];mount_pair_cache[key]=sum(b.volume for b in common.solids()) if common else 0.
  v=mount_pair_cache[key]
  if v>1e-7:solid_bad.append({'mount':parts[i][0].label,'other_mount':parts[j][0].label,'overlap_volume_mm3':v})
 row={'pose':pose,'route_distance_checks':checks,'route_conflicts':bad,'solid_conflicts':solid_bad,'host_contacts':contacts,'pass':not bad and not solid_bad};report['rows'].append(row);out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(row),flush=True)
 if not row['pass']:raise SystemExit(1)
report['pass']=all(r['pass'] for r in report['rows']);out.write_text(json.dumps(report,indent=2)+'\n');raise SystemExit(0 if report['pass'] else 1)
