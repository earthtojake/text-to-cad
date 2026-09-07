"""Exact inter-phalange interference at full independent ranges and named poses.

Reads the actual assembled STEP, including its fixed neutral ray fan. This is
one gate, not a substitute for tendon, hardware, or animated-frame checks.
"""
import argparse,hashlib,itertools,json
from pathlib import Path
import numpy as np
from cadgen._internal.step_scene_loader import load_step_scene
from cadgen.interference import occurrences_from_scene
from lib.layout import JOINTS,FINGERS,NEUTRAL_FINGER_FAN,assembled_transforms,upstream_joints
from lib.assembly import matrix_location
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps


def frame_for(name):
    for f in FINGERS:
        for role,joint in zip(('proximal','middle','distal'),('mcp_flexion','pip','dip')):
            if name==f'{f.name}_{role}_frame':return f'{f.name}_{joint}'
    for role,joint in zip(('metacarpal','proximal','distal'),('cmc_flexion','mcp_flexion','ip')):
        if name==f'thumb_{role}_frame':return f'thumb_{joint}'
    return None


def bounds(shape):
    b=Bnd_Box();BRepBndLib.AddOptimal_s(shape,b,False,False);return b.Get()


def named_poses():
    fist={}
    for f in FINGERS:
        fist.update({f'{f.name}_mcp_abduction':-NEUTRAL_FINGER_FAN[f.name],f'{f.name}_mcp_flexion':90.,f'{f.name}_pip':110.,f'{f.name}_dip':80.})
    fist.update(thumb_cmc_abduction=-20.,thumb_cmc_flexion=45.,thumb_mcp_abduction=-10.,thumb_mcp_flexion=55.,thumb_ip=60.)
    pinch=json.loads(Path(__file__).with_name('pinch_contact_candidate.json').read_text())['pose']
    return [('flat_open',{}),('full_fist_candidate',fist),('precision_pinch_candidate',pinch)]


PAIR_CACHE={}
def pair_key(a,b,pose):
    ca=(*upstream_joints(a[1]),a[1]);cb=(*upstream_joints(b[1]),b[1]);common=0
    while common<min(len(ca),len(cb)) and ca[common]==cb[common]:common+=1
    # The common parent transformation is rigid and cancels exactly. Only
    # downstream joint values can change these two bodies' interference.
    return (a[0].name,b[0].name,tuple((j,float(pose.get(j,0.))) for j in ca[common:]),tuple((j,float(pose.get(j,0.))) for j in cb[common:]))

def audit(parts,label,pose):
    fk=assembled_transforms(pose);posed=[]
    for part,frame in parts:
        transform=fk[frame];shape=part.shape.Moved(matrix_location(transform).wrapped)
        corners=np.array([[*xyz,1.] for xyz in itertools.product(*[(part.bbox[j],part.bbox[j+3]) for j in range(3)])])
        points=(corners@transform.T)[:,:3]
        placed_box=tuple(points.min(axis=0))+tuple(points.max(axis=0))
        posed.append((part.name,shape,placed_box))
    checked=0;failures=[];reused=0
    for ia,ib in itertools.combinations(range(len(parts)),2):
        a,b=posed[ia],posed[ib];key=pair_key(parts[ia],parts[ib],pose)
        if key in PAIR_CACHE:
            reused+=1
            if PAIR_CACHE[key]:failures.append(PAIR_CACHE[key])
            continue
        if any(a[2][i+3]<b[2][i]-1e-8 or b[2][i+3]<a[2][i]-1e-8 for i in range(3)):
            PAIR_CACHE[key]=None;continue
        checked+=1;common=BRepAlgoAPI_Common(a[1],b[1])
        if not common.IsDone():raise RuntimeError(f'Boolean failed: {a[0]} / {b[0]}')
        props=GProp_GProps();BRepGProp.VolumeProperties_s(common.Shape(),props)
        failure={'a':a[0],'b':b[0],'intersection_mm3':props.Mass()} if props.Mass()>1e-7 else None
        PAIR_CACHE[key]=failure
        if failure:failures.append(failure)
    return {'sample':label,'pose':pose,'exact_pairs':checked,'unchanged_relative_pair_certificates_reused':reused,'collisions':failures,'clear':not failures}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--input',default='models/assemblies/STEP/anthropomorphic_hand/routing_layout_review.step');parser.add_argument('--out',default='models/assemblies/validation/anthropomorphic_hand/global_phalanx_sweeps.json');args=parser.parse_args()
    source=Path(args.input);source_hash=hashlib.sha256(source.read_bytes()).hexdigest();scene=load_step_scene(source)
    parts=[(p,frame_for(p.name)) for p in occurrences_from_scene(scene) if frame_for(p.name)]
    if len(parts)!=15:raise ValueError(f'Expected15 real phalanges, found{len(parts)}')
    prior=Path(args.out)
    if prior.exists():
        saved=json.loads(prior.read_text())
        if saved.get('sha256')==source_hash:
            for row in saved['rows']:
                failures={(f['a'],f['b']):f for f in row['collisions']}
                for a,b in itertools.combinations(parts,2):PAIR_CACHE[pair_key(a,b,row['pose'])]=failures.get((a[0].name,b[0].name))
    samples=named_poses()
    for joint in JOINTS:
        lo,hi=joint.limits
        samples.extend((f'{joint.name}_{q:g}',{joint.name:float(q)}) for q in sorted(set([lo,hi,0.]+list(np.arange(lo,hi+1e-8,10.)))))
    rows=[]
    for label,pose in samples:
        row=audit(parts,label,pose);rows.append(row);print(label,row['clear'],row['collisions'],flush=True)
        report={'input':str(source),'sha256':source_hash,'part_count':15,'sample_count':len(rows),'complete':len(rows)==len(samples),'pass':len(rows)==len(samples) and all(r['clear'] for r in rows),'rows':rows,'scope':'Exact intersections of every pair of15 STEP phalanges; exact joint-chain relative-state equality reuses proven pair results. Pinch/fist are candidates pending pad contact and complete routing checks.'}
        Path(args.out).write_text(json.dumps(report,indent=2)+'\n')
    if not report['pass']:raise SystemExit(1)
