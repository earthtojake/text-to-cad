from cadgen import read_step
from pathlib import Path
import json
b=Path('models/assemblies/STEP/anthropomorphic_hand')
def leaves(s):return [p for c in s.children for p in leaves(c)] if s.children else[s]
h=read_step(b/'imported/palm_frame_integration.step');rows=[]
for p in leaves(read_step(b/'wrist_guide_mounts_review.step')):
 if not p.label.startswith('palm_cup_'):continue
 s=p&h;v=sum(q.volume for q in s.solids()) if s else 0;d=p.distance_to(h);r={'name':p.label,'intersection_mm3':v,'distance_mm':d};rows.append(r);print(r,flush=True)
Path('models/assemblies/validation/anthropomorphic_hand/palm_wrist_guide_host_fit.json').write_text(json.dumps({'rows':rows},indent=2))
