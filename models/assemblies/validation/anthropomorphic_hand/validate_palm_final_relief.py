import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from cadgen import build123d as bd,read_step
v=Path('models/assemblies/validation/anthropomorphic_hand'); path=Path('models/assemblies/STEP/anthropomorphic_hand/palm_frame_candidate_review.step'); main=read_step(path)
def leaves(x):return [p for c in x.children for p in leaves(c)] if x.children else[x]
screw=next(p for p in leaves(read_step('models/assemblies/STEP/anthropomorphic_hand/thumb_cmc_mounts_review.step')) if p.label=='thumb_cmc_parent_inlet_comb_host_M0p6_screw')
hit=main&screw;vol=sum(s.volume for s in hit.solids()) if hit else 0.;gap=main.distance_to(screw)
print('SCREW',vol,gap,flush=True)
d=json.loads((v/'palm_rebuilt_local_motion_fits.json').read_text())
for r in d['rows']:
 if r['name']==screw.label:
  r['intersection_mm3']=vol;r['distance_mm']=gap;r.pop('intersection_bounds',None);r['method']='exact native Boolean after final 0.05 mm head-clearance subtraction'
d['failures']=[r for r in d['rows'] if r['intersection_mm3']>1e-7]
d['final_change']='Only a radius0.55 mm, height4 mm cylindrical subtraction around the fixed CMC clamp screw. Prior zero-overlap checks are preserved by this monotone removal; the one failing screw pair is explicitly retested.'
d['step_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
(v/'palm_rebuilt_local_motion_fits.json').write_text(json.dumps(d,indent=2))
for x in(-24,24):
 ring=bd.Pos(x,14,-10.2)*(bd.Cylinder(1.85,3.2)-bd.Cylinder(1.65,4));missing=ring-main;vol=sum(s.volume for s in missing.solids()) if missing else 0
 print('SEAT',x,vol,flush=True)
assert not d['failures']
