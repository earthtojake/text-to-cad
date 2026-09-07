import sys,importlib.util
from pathlib import Path
p=Path(__file__).resolve();sys.path.insert(0,str(p.parents[2]/'src/anthropomorphic_hand'))
from cadgen import build123d as bd
spec=importlib.util.spec_from_file_location('baseline',p.with_name('phalanx_pre_beauty_baseline.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
s=bd.import_step(str(p.parents[2]/'STEP/anthropomorphic_hand/phalanx_beauty_native/little_middle_frame.step'))
print('new',s.volume,s.is_valid,len(s.solids()),flush=True)
b=m.make_phalanx(21,14,label='old')
print('old',b.volume,b.is_valid,len(b.solids()),'difference',b.volume-s.volume,flush=True)
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.TopTools import TopTools_ListOfShape
for fuzzy in (1e-7,1e-6):
    aa=TopTools_ListOfShape();aa.Append(b.wrapped);bb=TopTools_ListOfShape();bb.Append(s.wrapped)
    op=BRepAlgoAPI_Common();op.SetArguments(aa);op.SetTools(bb);op.SetNonDestructive(True);op.SetFuzzyValue(fuzzy);op.Build()
    p=GProp_GProps();BRepGProp.VolumeProperties_s(op.Shape(),p)
    print('common_fuzzy',fuzzy,op.IsDone(),p.Mass(),BRepCheck_Analyzer(op.Shape()).IsValid(),'error_vs_new',p.Mass()-s.volume,flush=True)
