import json
from pathlib import Path
from cadgen import build123d as bd
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Common
p=Path('models/assemblies/STEP/anthropomorphic_hand')
a=bd.import_step(p/'phalanx_beauty_native/middle_proximal_frame.step');b=bd.import_step(p/'phalanx_sculpt_early_probe_r4.step')
def vol(s):
 from OCP.GProp import GProp_GProps
 from OCP.BRepGProp import BRepGProp
 g=GProp_GProps();BRepGProp.VolumeProperties_s(s.wrapped,g,1e-6,False,False);return g.Mass()
def cut(a,b):
 op=BRepAlgoAPI_Cut(a.wrapped,b.wrapped);op.Build();s=bd.Compound(op.Shape());return {'done':op.IsDone(),'valid':s.is_valid,'solids':len(s.solids()),'volume':vol(s)}
r={'old_volume':a.volume,'new_volume':b.volume,'new_minus_old':cut(b,a),'protected_bands':[]}
print('global',r,flush=True)
for lo,hi in [(-4,4.3),(11.5,13.),(29.25,33.5),(37.25,49.)]:
 box=bd.Pos(0,(lo+hi)/2,0)*bd.Box(24,hi-lo,20)
 aa=a & box;bb=b & box
 r['protected_bands'].append({'y_min':lo,'y_max':hi,'new_minus_old':cut(bb,aa),'old_minus_new':cut(aa,bb)})
 print(r['protected_bands'][-1],flush=True)
r['pass']=r['new_minus_old']['volume']<1e-7 and all(max(x['old_minus_new']['volume'],x['new_minus_old']['volume'])<1e-7 for x in r['protected_bands'])
Path('models/assemblies/validation/anthropomorphic_hand/phalanx_sculpt_representative_r4_certificate.json').write_text(json.dumps(r,indent=2));print(r,flush=True)
