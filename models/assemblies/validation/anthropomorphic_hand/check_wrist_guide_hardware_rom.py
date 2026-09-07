import sys,json,hashlib,io
from pathlib import Path
import numpy as np
HERE=Path(__file__).parent;ROOT=HERE.parents[1];sys.path.insert(0,str(ROOT/'src/anthropomorphic_hand'))
from cadgen import read_step,build123d as bd
from lib.wrist import make_wrist_fixed_fork,make_wrist_yaw_carrier,make_wrist_palm_cradle,make_wrist_bushings
from lib.layout import JOINT_BY_NAME,transforms
from lib.assembly import matrix_location
from check_guide_mount_mutual import leaves
from check_remaining_guide_routes import frame
from check_guide_combs import common_volume
from check_middle_hardware_paths import bbox_gap
from native_face_bounds import NativeFaceBounds

ENVELOPE_PARTS={}
def hardware():
 out=[(make_wrist_fixed_fork(),'forearm'),(make_wrist_yaw_carrier(),'wrist_abduction'),(make_wrist_palm_cradle(),'wrist_flexion')]
 out += [(p,'forearm' if f=='fixed' else 'wrist_abduction') for f,p in make_wrist_bushings()]
 for file in ('joint_hardware_review.step','drive_terminal_placements.step'):
  for p in leaves(read_step(ROOT/'STEP/anthropomorphic_hand'/file)):
   if not p.label.startswith(('wrist_abduction_','wrist_flexion_')):continue
   j=JOINT_BY_NAME['wrist_abduction' if p.label.startswith('wrist_abduction_') else 'wrist_flexion']
   fr=j.parent if p.label.endswith('_bushing') else j.name;out.append((p,fr))
 from lib.drive_terminal import terminal_placements
 envelopes={};proofs=[]
 for row in terminal_placements():
  if row['name'].startswith('wrist_'):
   e=row['placement']*bd.Cylinder(11.7,1.7);e.label=row['name']+'_proven_hardware_envelope';envelopes[row['name']]=(e,row['joint'].name)
 kept=[]
 for p,fr in out:
  key=next((k for k in envelopes if p.label.startswith(k+'_')),None)
  if key is None:kept.append((p,fr));continue
  diff=p-envelopes[key][0];v=0 if diff is None else abs(diff.volume)
  ENVELOPE_PARTS.setdefault(envelopes[key][0].label,[]).append((p,fr))
  proofs.append({'part':p.label,'outside_envelope_mm3':v});assert v<1e-7,(p.label,v)
 (HERE/'wrist_hardware_envelope_containment.json').write_text(json.dumps({'pass':True,'proofs':proofs},indent=2)+'\n')
 return kept+list(envelopes.values())
if __name__=='__main__':
 guides=leaves(read_step(ROOT/'STEP/anthropomorphic_hand/wrist_guide_mounts_review.step'));unchanged=[]
 if 'changed' in sys.argv:
  old=leaves(read_step(ROOT/'STEP/anthropomorphic_hand/imported/wrist_guide_pre_mirror.step'))
  def fingerprint(p):
   stream=io.BytesIO();bd.export_brep(p,stream);return hashlib.sha256(stream.getvalue()).hexdigest()
  old_hash={p.label:fingerprint(p) for p in old};unchanged=[{'name':p.label,'brep_sha256':fingerprint(p)} for p in guides if fingerprint(p)==old_hash.get(p.label)];same={r['name'] for r in unchanged};guides=[p for p in guides if p.label not in same]
 hw=hardware();cache={};rows=[];gb=[NativeFaceBounds(p) for p in guides];hb=[NativeFaceBounds(p) for p,f in hw];actual_bounds={p.label:NativeFaceBounds(p) for entries in ENVELOPE_PARTS.values() for p,f in entries};guide_digest=hashlib.sha256((ROOT/'STEP/anthropomorphic_hand/wrist_guide_mounts_review.step').read_bytes()).hexdigest()
 yaw_values=(int(sys.argv[1]),) if len(sys.argv)>1 and sys.argv[1]!='all' else (-20,-10,0,10,20)
 poses=[{'wrist_abduction':a,'wrist_flexion':b} for a in yaw_values for b in(-45,-35,-25,-15,-5,0,5,15,25,35,45,55,60)]
 for pose in poses:
  fk=transforms(pose);gs=[matrix_location(fk[frame(p.label)])*p for p in guides];hs=[matrix_location(fk[f])*p for p,f in hw];gbs=[p.bounding_box() for p in gs];hbs=[p.bounding_box() for p in hs];hits=[];tested=0
  for i,g in enumerate(gs):
   for j,h in enumerate(hs):
    if bbox_gap(gbs[i],hbs[j])>1e-5:continue
    rel=np.linalg.inv(fk[frame(guides[i].label)])@fk[hw[j][1]];key=(i,j,tuple(np.round(rel.ravel(),7)))
    if h.label.endswith('_proven_hardware_envelope'):
     from lib.layout import JOINT_BY_NAME
     axis=np.array(JOINT_BY_NAME[hw[j][1]].axis);axis=rel[:3,:3]@axis;origin=np.array(tuple(hw[j][0].center()));center=rel[:3,:3]@origin+rel[:3,3];key=(i,j,tuple(np.round(np.r_[center,axis],7)))
    if key not in cache:cache[key]=0. if gb[i].disjoint(hb[j],rel) else common_volume(g,h);tested+=1
    v=cache[key]
    if v>1e-7:
     if h.label.endswith('_proven_hardware_envelope'):
      for actual,af in ENVELOPE_PARTS[h.label]:
       ah=matrix_location(fk[af])*actual
       if bbox_gap(gbs[i],ah.bounding_box())>1e-5:continue
       ak=(i,actual.label,tuple(np.round(rel.ravel(),7)))
       if ak not in cache:cache[ak]=0. if gb[i].disjoint(actual_bounds[actual.label],rel) else common_volume(g,ah);tested+=1
       if cache[ak]>1e-7:hits.append({'guide':guides[i].label,'hardware':actual.label,'volume_mm3':cache[ak]})
     else:hits.append({'guide':guides[i].label,'hardware':hw[j][0].label,'volume_mm3':v})
  rows.append({'pose':pose,'interferences':hits,'new_exact_pairs':tested});r={'pass':not any(row['interferences'] for row in rows),'guide_step_sha256':guide_digest,'guide_count':len(guides),'unchanged_native_bodies':unchanged,'hardware_count':len(hw),'poses':len(rows),'rows':rows};(HERE/('wrist_guide_hardware_rom'+('_changed' if 'changed' in sys.argv else '')+('_'+sys.argv[1] if len(sys.argv)>1 else '')+'.json')).write_text(json.dumps(r,indent=2)+'\n');print(pose,'pairs',tested,'hits',len(hits),flush=True)
 assert r['pass']
