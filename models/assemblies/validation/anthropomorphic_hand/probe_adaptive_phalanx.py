import json,sys
from pathlib import Path
from cadgen import build123d as bd
from cadgen.store.objects import object_path
from cadgen._internal.component_package import _build123d_shape_from_brep_bytes
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut,BRepAlgoAPI_Common
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopTools import TopTools_ListOfShape
from OCP.BRepCheck import BRepCheck_Analyzer
record=json.load(open('tmp/anthropomorphic_hand/progress_viewer_store.json'))
name=sys.argv[1] if len(sys.argv)>1 else 'little_middle_frame'
o=next(o for o in record['occurrences'] if o['name']==name);c=record['components'][o['component']]
a=_build123d_shape_from_brep_bytes(object_path(c['brepObject']).read_bytes())
b=bd.import_step('models/assemblies/STEP/anthropomorphic_hand/phalanx_beauty_native/'+name+'.step')
def vol(s):
 p=GProp_GProps();err=BRepGProp.VolumeProperties_s(s,p,1e-10,True,False);return p.Mass(),err
print('volumes',name,vol(a.wrapped),vol(b.wrapped),flush=True)
for role,cls,x,y in [('added',BRepAlgoAPI_Cut,b,a),('common',BRepAlgoAPI_Common,a,b),('removed',BRepAlgoAPI_Cut,a,b)]:
 aa=TopTools_ListOfShape();aa.Append(x.wrapped);bb=TopTools_ListOfShape();bb.Append(y.wrapped)
 op=cls();op.SetArguments(aa);op.SetTools(bb);op.SetNonDestructive(True);op.Build()
 print(role,op.IsDone(),BRepCheck_Analyzer(op.Shape()).IsValid(),vol(op.Shape()),flush=True)
