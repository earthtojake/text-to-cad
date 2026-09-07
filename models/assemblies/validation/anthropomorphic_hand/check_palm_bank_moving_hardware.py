import sys,json,hashlib
from pathlib import Path
import numpy as np
HERE=Path(__file__).parent;ROOT=HERE.parents[1];sys.path.insert(0,str(ROOT/'src/anthropomorphic_hand'))
from cadgen import read_step
from lib.layout import transforms
from lib.assembly import matrix_location
from lib.cup_guide_mounts import _cup_host
from check_guide_mount_mutual import leaves
from check_guide_combs import common_volume
from check_middle_hardware_paths import bbox_gap
parts=leaves(read_step(ROOT/'STEP/anthropomorphic_hand/palm_guide_mounts_review.step'));moving=leaves(read_step(ROOT/'STEP/anthropomorphic_hand/phalanx_comb_clearance_review.step'));mapping={r['name']:r['frame'] for r in json.loads((HERE/'phalanx_comb_clearance_frames.json').read_text())};little=leaves(read_step(ROOT/'STEP/anthropomorphic_hand/palm_little_comb_rom_review.step'))[0];moving.append(little);mapping[little.label]='palm_cup'
for p in leaves(read_step(ROOT/'STEP/anthropomorphic_hand/palm_hardware_review.step')):moving.append(p);mapping[p.label]='wrist_flexion'
def corners(p):
 b=p.bounding_box();return np.array([[x,y,z,1] for x in(b.min.X,b.max.X) for y in(b.min.Y,b.max.Y) for z in(b.min.Z,b.max.Z)])
boxes=np.array([corners(p) for p in parts]);lo=boxes[:,:,:3].min(axis=1);hi=boxes[:,:,:3].max(axis=1);mbs=[corners(p) for p in moving];cache={};rows=[];manifest=json.loads((HERE/'static_route_packet_manifest.json').read_text());hashes={n:hashlib.sha256((ROOT/'STEP/anthropomorphic_hand'/n).read_bytes()).hexdigest() for n in('palm_guide_mounts_review.step','phalanx_comb_clearance_review.step','palm_little_comb_rom_review.step','palm_hardware_review.step')}
for entry in manifest['rows']:
 fk=transforms(entry['pose']);inv=np.linalg.inv(fk['wrist_flexion']);rel={f:inv@fk[f] for f in set(mapping.values())};hits=[];tested=0
 for j,p in enumerate(moving):
  mat=rel[mapping[p.label]];bb=mbs[j]@mat.T;l=bb[:,:3].min(0);h=bb[:,:3].max(0);gap=np.maximum(0,np.maximum(lo-h,l-hi));indices=np.where((gap*gap).sum(axis=1)<1e-10)[0]
  if not len(indices):continue
  shape=matrix_location(mat)*p
  for i in indices:
   key=(int(i),j,tuple(np.round(mat.ravel(),7)))
   if key not in cache:cache[key]=0. if parts[i].distance_to(shape)>1e-6 else common_volume(parts[i],shape);tested+=1
   if cache[key]>1e-7:hits.append({'bank':parts[i].label,'moving_body':p.label,'volume_mm3':cache[key]})
 rows.append({'label':entry['label'],'pose':entry['pose'],'interferences':hits,'new_exact_pairs':tested});r={'pass':not any(row['interferences'] for row in rows),'bank_count':len(parts),'moving_count':len(moving),'pose_count':len(rows),'step_sha256':hashes,'rows':rows};(HERE/'palm_bank_moving_hardware.json').write_text(json.dumps(r,indent=2)+'\n');print(entry['label'],'pairs',tested,'hits',len(hits),flush=True)
assert r['pass']
