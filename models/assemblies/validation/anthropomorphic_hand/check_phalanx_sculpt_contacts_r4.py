import json
from pathlib import Path
from cadgen import build123d as bd
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
p=Path('models/assemblies/STEP/anthropomorphic_hand')
a=bd.import_step(p/'phalanx_beauty_native/middle_proximal_frame.step');b=bd.import_step(p/'phalanx_sculpt_early_probe_r4.step')
def cut(x,y):
 op=BRepAlgoAPI_Cut(x.wrapped,y.wrapped);op.Build();s=bd.Compound(op.Shape());return {'done':op.IsDone(),'solids':len(s.solids()),'volume':s.volume}
r={'protected_bands':[]}
for lo,hi in [(-4,4.3),(11.5,13.),(29.25,33.5),(37.25,49.)]:
 box=bd.Pos(0,(lo+hi)/2,0)*bd.Box(24,hi-lo,20)
 aa=a & box;bb=b & box
 row={'y_min':lo,'y_max':hi,'new_minus_old':cut(bb,aa),'old_minus_new':cut(aa,bb)};r['protected_bands'].append(row)
 print(row,flush=True)
 Path('models/assemblies/validation/anthropomorphic_hand/phalanx_sculpt_contacts_r4.json').write_text(json.dumps(r,indent=2))
r['complete']=True;r['pass']=all(max(x['old_minus_new']['volume'],x['new_minus_old']['volume'])<1e-7 for x in r['protected_bands'])
Path('models/assemblies/validation/anthropomorphic_hand/phalanx_sculpt_contacts_r4.json').write_text(json.dumps(r,indent=2))
