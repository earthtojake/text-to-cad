"""225 native-route and all-rigid-body delta checks for two new PIP collars."""
import sys,json,gzip,hashlib,time,multiprocessing
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;SRC=HERE.parents[1]/'src/anthropomorphic_hand';sys.path.insert(0,str(SRC));sys.path.insert(0,str(HERE))
from cadgen import build123d as bd
from lib.native_integration import integrated_native_bodies,leaves
from lib.pulley_hub_extension import representative_bodies
from lib.assembly import posed_bodies,Body
from check_full_route_bodies import audit as route_audit
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from types import SimpleNamespace

def placed_bounds(bodies):
    result={}
    for b in bodies:
        box=Bnd_Box();BRepBndLib.Add_s(b.shape.wrapped,box,False);v=box.Get()
        result[b.name]=SimpleNamespace(min=bd.Vector(*v[:3]),max=bd.Vector(*v[3:]))
    return result
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from lib.layout import assembled_transforms
from contextlib import redirect_stdout

STEP=HERE.parents[1]/'STEP/anthropomorphic_hand/pulley_hub_review.step'
new=representative_bodies();frames={b.name:b for b in new}
new=[Body(s,frames[s.label].frame,frames[s.label].system,frames[s.label].kind) for s in leaves(bd.import_step(STEP))]
print('loading final native context',flush=True)
base=[b for b in integrated_native_bodies() if b.frame!='variable'];allb=base+new
inputs={b.source_path:b.source_sha256 for b in base};inputs[str(STEP)]=hashlib.sha256(STEP.read_bytes()).hexdigest()
manifest=HERE/'static_route_packet_manifest.json';inputs[str(manifest)]=hashlib.sha256(manifest.read_bytes()).hexdigest()
samples=json.loads(manifest.read_text())['rows']
def partition(index):
    route_cache={};rigid_cache={};rows=[]
    for i in range(index,len(samples),4):
        sample=samples[i]
        with gzip.open(sample['file'],'rt') as f:packet=json.load(f)
        routes=packet['routes'] if isinstance(packet,dict) else packet
        with (HERE/f'pulley_hub_route_detail_{index}.log').open('a') as log,redirect_stdout(log):
            rr=route_audit(routes,new,sample['pose'],route_cache)
            placed=posed_bodies(allb,sample['pose']);boxes=placed_bounds(placed)
        bb={b.name:b for b in placed};fails=[];checks=0;fk=assembled_transforms(sample['pose'])
        for nb in new:
            a=bb[nb.name];box=boxes[a.name];lo=np.array(tuple(box.min));hi=np.array(tuple(box.max))
            for original in allb:
                if original.name==a.name:continue
                b=bb[original.name];bbo=boxes[b.name]
                if any(getattr(box.max,k)<getattr(bbo.min,k)-1e-8 or getattr(bbo.max,k)<getattr(box.min,k)-1e-8 for k in ('X','Y','Z')):continue
                rel=np.linalg.inv(fk[a.frame])@fk[b.frame]
                key=(a.name,b.name,'same_frame' if a.frame==b.frame else tuple(float(x).hex() for x in rel.ravel()))
                if key not in rigid_cache:
                    op=BRepAlgoAPI_Common(a.shape.wrapped,b.shape.wrapped);assert op.IsDone()
                    props=GProp_GProps();BRepGProp.VolumeProperties_s(op.Shape(),props);rigid_cache[key]=float(props.Mass());checks+=1
                volume=rigid_cache[key]
                if volume>1e-7:fails.append(dict(a=a.name,b=b.name,intersection_mm3=volume))
        row=dict(label=sample['label'],pose=sample['pose'],route=rr,rigid_collisions=fails,exact_rigid_checks=checks,pass_=rr['pass'] and not fails)
        rows.append(row)
        report=dict(input_sha256=inputs,scope='Two new native PIP collars against every one of 48 full routes and every rigid native assembly body at each of 225 static poses',body_count=len(allb),sample_count=len(rows),complete=len(rows)==len(range(index,len(samples),4)),rows=rows,passed=all(r['pass_'] for r in rows))
        (HERE/f'pulley_hub_gate_partition_{index}.json').write_text(json.dumps(report,indent=2)+'\n')
        print(i+1,sample['label'],'route failures',len(rr['collisions']),'rigid failures',fails,'new exact',checks,flush=True)
        if not row['pass_']:break
    return rows

if __name__=='__main__':
    with multiprocessing.get_context('fork').Pool(4) as pool:parts=pool.map(partition,range(4))
    rows=[r for batch in parts for r in batch]
    changed=[path for path,sha in inputs.items() if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha]
    report=dict(input_sha256=inputs,changed_inputs=changed,scope='Two new native PIP collars against every one of 48 full routes and every rigid native assembly body at each of 225 static poses',body_count=len(allb),sample_count=len(rows),complete=len(rows)==225,rows=rows,passed=len(rows)==225 and not changed and all(r['pass_'] for r in rows))
    (HERE/'pulley_hub_gate.json').write_text(json.dumps(report,indent=2)+'\n')
    print('FINAL',report['passed'],len(rows),flush=True)
    assert report['passed']
