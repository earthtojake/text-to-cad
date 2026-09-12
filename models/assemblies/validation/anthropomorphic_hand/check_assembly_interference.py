"""Neutral all-body intersection gate with exact congruent prototype reuse."""
import json,itertools,time
from pathlib import Path
import numpy as np
from OCP.TopLoc import TopLoc_Location
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopTools import TopTools_ListOfShape
from check_full_route_bodies import integration_hardware,placed_bounds
from rigid_pose_cache import relative_pose_key

def audit(bodies,out,cache=None,changed_names=None,pose=None):
    boxes=placed_bounds(bodies);protos=[];records=[]
    for body in bodies:
        w=body.shape.wrapped;local=w.Located(TopLoc_Location())
        p=next((i for i,s in enumerate(protos) if s.IsSame(local)),None)
        if p is None:p=len(protos);protos.append(local)
        tr=w.Location().Transformation();m=np.eye(4)
        m[:3,:]=[[tr.Value(r,c) for c in range(1,5)] for r in range(1,4)]
        records.append((body,p,m))
    ordered=sorted(records,key=lambda r:boxes[r[0].name].min.X)
    active=[];cache={} if cache is None else cache;checks=0;reused=0;failures=[];rows=[]
    for number,a in enumerate(ordered):
        ba=boxes[a[0].name];active=[b for b in active if boxes[b[0].name].max.X>=ba.min.X-1e-8]
        for b in active:
            if changed_names is not None and a[0].name not in changed_names and b[0].name not in changed_names:continue
            bb=boxes[b[0].name]
            if any(getattr(ba.max,k)<getattr(bb.min,k)-1e-8 or getattr(bb.max,k)<getattr(ba.min,k)-1e-8 for k in ('Y','Z')):continue
            relative=np.linalg.inv(a[2])@b[2]
            geometric_key=('exact_prototype_placement',a[1],b[1],tuple(float(x).hex() for x in relative.ravel()))
            key=geometric_key
            if pose is not None:
                key=relative_pose_key(a[0].name,a[0].frame,b[0].name,b[0].frame,pose)
            # Equal authored rigid frames undergo the same isometry at every
            # pose. Reuse their completed exact pair proof without introducing
            # floating-point inverse noise from the common global transform.
            elif a[0].frame==b[0].frame:
                key=('same_rigid_frame',*sorted((a[0].name,b[0].name)))
            if key in cache:volume=cache[key];reused+=1
            elif geometric_key in cache:
                volume=cache[geometric_key];cache[key]=volume;reused+=1
            else:
                arguments=TopTools_ListOfShape();arguments.Append(a[0].shape.wrapped)
                tools=TopTools_ListOfShape();tools.Append(b[0].shape.wrapped)
                op=BRepAlgoAPI_Common();op.SetArguments(arguments);op.SetTools(tools)
                op.SetNonDestructive(True);op.Build()
                if not op.IsDone():raise RuntimeError(f'Boolean failed:{a[0].name}/{b[0].name}')
                props=GProp_GProps();BRepGProp.VolumeProperties_s(op.Shape(),props);volume=float(props.Mass());cache[key]=volume;cache[geometric_key]=volume;checks+=1
            if volume>1e-7:
                row={'a':a[0].name,'b':b[0].name,'intersection_mm3':volume};failures.append(row);print('COLLISION',row,flush=True)
        active.append(a)
        if number%25==0 or number+1==len(ordered):
            report={'body_count':len(bodies),'processed':number+1,'exact_booleans':checks,'congruent_proof_reuse':reused,'collisions':failures,'complete':number+1==len(ordered),'pass':number+1==len(ordered) and not failures}
            if changed_names is not None:report['pair_scope']={'any_endpoint_in':sorted(changed_names),'unchanged_pair_gate':'separate frozen baseline certificate required'}
            out.write_text(json.dumps(report,indent=2)+'\n');print('INTERFERENCE',number+1,len(bodies),checks,reused,len(failures),flush=True)
    return report

if __name__=='__main__':
    bodies,evidence=integration_hardware();out=Path(__file__).with_name('assembly_neutral_interference.json')
    report=audit(bodies,out);report['input_sha256']=evidence;out.write_text(json.dumps(report,indent=2)+'\n')
    if not report['pass']:raise SystemExit(1)
