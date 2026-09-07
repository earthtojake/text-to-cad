"""Test a splayed neutral datum without changing any authored joint range."""
from pathlib import Path
import json,sys,itertools
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'models/assemblies/src/anthropomorphic_hand'))
from cadgen._internal.step_scene_loader import load_step_scene
from cadgen.interference import occurrences_from_scene
from lib.layout import FINGERS,rotation_matrix
from lib.assembly import matrix_location
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

FAN={'index':20.,'middle':5.,'ring':-5.,'little':-25.}
scene=load_step_scene(ROOT/'models/assemblies/STEP/anthropomorphic_hand/integration_review.step')
parts=[p for p in occurrences_from_scene(scene) if p.name.endswith('_frame') and not p.name.startswith('thumb')]

def bounds(shape):
    b=Bnd_Box();BRepBndLib.AddOptimal_s(shape,b,False,False);return b.Get()

def test(selected,angle):
    posed=[]
    for p in parts:
        f=next(f for f in FINGERS if p.name.startswith(f.name+'_'))
        q=FAN[f.name]+(angle if f.name==selected else 0)
        m=matrix_location(rotation_matrix((0,0,1),q,(f.x,f.base_y,0))).wrapped
        shape=p.shape.Moved(m);posed.append((p.name,f.name,shape,bounds(shape)))
    failures=[];checked=0
    for a,b in itertools.combinations(posed,2):
        if a[1]==b[1]:continue
        if any(a[3][i+3]<b[3][i] or b[3][i+3]<a[3][i] for i in range(3)):continue
        checked+=1
        c=BRepAlgoAPI_Common(a[2],b[2]);c.Build()
        if not c.IsDone():raise RuntimeError('Boolean failed')
        g=GProp_GProps();BRepGProp.VolumeProperties_s(c.Shape(),g)
        if g.Mass()>1e-6:failures.append({'a':a[0],'b':b[0],'volume':g.Mass()})
    return {'joint':selected,'angle':angle,'exact_pairs':checked,'failures':failures,'clear':not failures}

rows=[test('',0)]
for f in FINGERS:
    angles=sorted(set([f.abduction[0],f.abduction[1],0]+list(range(int(f.abduction[0]),int(f.abduction[1])+1,10))))
    for q in angles:
        row=test(f.name,q);rows.append(row);print(row,flush=True)
out=ROOT/'models/assemblies/validation/anthropomorphic_hand/neutral_fan_precheck.json'
out.write_text(json.dumps({'scope':'Phalanx-to-phalanx independent abduction sweeps only. All original joint ranges preserved.','neutral_angles':FAN,'rows':rows},indent=2))
print('ALL CLEAR',all(r['clear'] for r in rows),flush=True)
