"""Exact native CMC addition versus actual frozen carrier/metacarpal and24 guide bodies."""
import sys,json,numpy as np,hashlib
from pathlib import Path
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from cadgen import build123d as bd,read_step
from lib.palm_cmc_seat_relief import swept
from lib.layout import assembled_transforms
from lib.assembly import matrix_location
V=Path(__file__).parent;B=V.parents[1]/'STEP/anthropomorphic_hand'
data=json.loads(Path('models/assemblies/src/anthropomorphic_hand/lib/palm_cmc_connection_path.json').read_text())
s=swept(data['segments'],data['radius']);s=s.fuse(bd.Pos(*data['segments'][0][0])*bd.Sphere(.95),bd.Pos(-35,36,9.3)*bd.Cylinder(1.85,1.4));s=s-(bd.Pos(-35,36,9.3)*bd.Cylinder(1.58,3.4));bb=s.bounding_box(optimal=False)
def leaves(n):return [x for c in n.children for x in leaves(c)] if n.children else [n]
parts=[(p,'thumb_cmc_abduction' if p.label=='thumb_cmc_carrier' else 'thumb_cmc_flexion') for p in leaves(read_step(B/'imported/integration_native_base.step')) if p.label in('thumb_cmc_carrier','thumb_metacarpal_frame')]
meta={r['name']:r for r in json.loads((V/'thumb_cmc_frames.json').read_text())['bodies']}
parts.extend((p,meta[p.label]['frame']) for p in leaves(read_step(B/'thumb_cmc_mounts_review.step')));print('PARTS',len(parts),flush=True);assert len(parts)==26
cache=set();rows=[];tests=0
M=json.loads((V/'static_route_packet_manifest.json').read_text())['rows']
for i,row in enumerate(M):
 fk=assembled_transforms(row['pose']);inv=np.linalg.inv(fk['wrist_flexion'])
 for p,frame in parts:
  m=inv@fk[frame];key=(p.label,tuple(np.round(m.flatten(),7)))
  if key in cache:continue
  cache.add(key);part=bd.Compound.cast(p.wrapped.Moved(matrix_location(m).wrapped));b=part.bounding_box(optimal=False)
  if any(bb.max.to_tuple()[a]<b.min.to_tuple()[a] or b.max.to_tuple()[a]<bb.min.to_tuple()[a] for a in range(3)):continue
  c=s&part;volume=sum(x.volume for x in c.solids()) if c else 0.;tests+=1
  if volume>1e-7:rows.append({'sample':row['label'],'part':p.label,'volume':volume});print('HIT',rows[-1],flush=True)
 report={'complete':i==224,'sample_count':i+1,'body_count':26,'unique_body_poses':len(cache),'native_intersections':tests,'failures':rows,'pass':i==224 and not rows};(V/'palm_cmc_added_rib_225_gate.json').write_text(json.dumps(report,indent=2))
 if i%25==0:print('POSE',i,'native',tests,flush=True)
print('DONE',report,flush=True)
