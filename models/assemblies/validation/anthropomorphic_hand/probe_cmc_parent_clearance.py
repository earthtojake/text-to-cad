import sys,json
from pathlib import Path
HERE=Path(__file__).parent;sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from cadgen import read_step,build123d as bd
from check_guide_mount_mutual import leaves
from lib.neutral_routes import NEUTRAL_ROUTES
from lib.guide_mounts import _sweep
r=next(r for r in NEUTRAL_ROUTES if r['name']=='thumb_cmc_abduction_negative');g=next(g for g in r['groups'] if g['label']=='thumb_cmc_abduction_negative_wrist_guide');ts=[_sweep(s['points'],.49) for s in g['path']]
p=next(p for p in leaves(read_step(HERE.parents[1]/'STEP/anthropomorphic_hand/thumb_cmc_mounts_review.step')) if p.label=='thumb_cmc_parent_inlet_comb_structural_jaw')
print('original',p.volume,len(p.solids()),flush=True)
for tool in ts:
 c=p&tool
 if c is not None:print('intersection',c.volume,c.bounding_box(),flush=True)
q=p.cut(*ts);print('after',[(s.volume,s.bounding_box()) for s in q.solids()],flush=True)
