import sys,json,gzip,hashlib,numpy as np
from pathlib import Path
ROOT=Path(__file__).resolve().parent;SRC=ROOT.parents[1]/'src/anthropomorphic_hand';STEP=ROOT.parents[1]/'STEP/anthropomorphic_hand'
sys.path.insert(0,str(SRC))
from cadgen import build123d as bd
from lib.assembly import Body,posed_bodies
from check_full_route_bodies import audit,placed_bounds
from check_hand_route_pairs import group_radius
from check_assembly_interference import audit as rigid_audit
bodies=[];evidence={}
for stem in ('positive_yaw_bushing','compact_cmc_yaw'):
 p=STEP/(stem+'_review.step');evidence[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();parts={p.label:p for p in bd.import_step(str(p)).children}
 for row in json.loads((ROOT/(stem+'_frames.json')).read_text()):bodies.append(Body(parts[row['name']],row['frame'],row['system'],row['kind']))
rigid=rigid_audit(bodies,ROOT/'positive_yaw_hardware_mutual.json')
manifest=json.loads((ROOT/'static_route_packet_manifest.json').read_text());cache={};rows=[]
for sample in manifest['rows']:
 packet=json.loads(gzip.decompress(Path(sample['file']).read_bytes()))
 boxes=placed_bounds(posed_bodies(bodies,sample['pose']));lows=np.array([tuple(b.min) for b in boxes.values()]);highs=np.array([tuple(b.max) for b in boxes.values()]);filtered=[];rejected=0
 for route in packet['routes']:
  groups=[]
  for g in route['groups']:
   points=[]
   for seg in g['path']:
    if seg['kind']=='bezier':points.extend(seg['points'])
    elif seg['kind']=='line':points.extend([seg['start'],seg['end']])
    else:
     c=np.asarray(seg['center']);rr=np.linalg.norm(np.asarray(seg['start'])-c);points.extend([c-rr,c+rr])
   a=np.asarray(points);lo=a.min(0);hi=a.max(0);gap=np.linalg.norm(np.maximum(np.maximum(lo-highs,lows-hi),0),axis=1)
   if gap.min()>group_radius(g)+1e-6:rejected+=1
   else:groups.append(g)
  filtered.append({**route,'groups':groups})
 r=audit(filtered,bodies,sample['pose'],cache);r['sample']=sample['label'];r['groups_proven_clear_by_control_hull_AABB']=rejected;rows.append(r)
 report={'body_count':len(bodies),'input_sha256':evidence,'sample_count':len(rows),'complete':len(rows)==225,'mutual':rigid,'rows':rows,'pass':len(rows)==225 and rigid['pass'] and all(r['pass'] for r in rows)}
 (ROOT/'positive_yaw_hardware_routes.json').write_text(json.dumps(report,indent=2)+'\n')
 print('SAMPLE',sample['label'],r['pass'],flush=True)
if not report['pass']:raise SystemExit(1)
