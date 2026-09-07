import sys,importlib.util
from pathlib import Path
p=Path(__file__).resolve();sys.path.insert(0,str(p.parents[2]/'src/anthropomorphic_hand'))
from cadgen import build123d as bd
spec=importlib.util.spec_from_file_location('baseline',p.with_name('phalanx_pre_beauty_baseline.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
s=bd.import_step(str(p.parents[2]/'STEP/anthropomorphic_hand/phalanx_beauty_native/little_middle_frame.step'))
print('new',s.volume,s.is_valid,len(s.solids()),flush=True)
b=m.make_phalanx(21,14,label='old')
print('old',b.volume,b.is_valid,len(b.solids()),'difference',b.volume-s.volume,flush=True)
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.BRepCheck import BRepCheck_Analyzer
for name,a,c in [('added',s,b),('removed',b,s)]:
    op=BRepAlgoAPI_Cut(a.wrapped,c.wrapped)
    props=GProp_GProps();BRepGProp.VolumeProperties_s(op.Shape(),props)
    print(name,'raw',op.IsDone(),props.Mass(),BRepCheck_Analyzer(op.Shape()).IsValid(),flush=True)
