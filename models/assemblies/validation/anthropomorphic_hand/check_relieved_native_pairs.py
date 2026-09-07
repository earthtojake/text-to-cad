"""Native post-export checks of the explicit support repair pairs at all225 poses."""
import hashlib,json
from pathlib import Path
from check_native_reported_contacts import native_shapes,sha,HERE
from lib.static_clearance_relief import PAIRS
from lib.phalanx_r5_boolean import common
from lib.assembly import matrix_location
from lib.layout import assembled_transforms
from rigid_pose_cache import relative_pose_key

def main():
    manifest_path=HERE/'rigid_clearance_inputs.json';manifest=json.loads(manifest_path.read_text())
    build_path=HERE/'static_clearance_relief_build.json';build=json.loads(build_path.read_text());assert build['pass']
    step=HERE.parents[1]/'STEP/anthropomorphic_hand/static_clearance_relief_review.step'
    base=Path(manifest['step']);assert sha(base)==manifest['step_sha256']
    poses_path=HERE/'final_static_route_packet_manifest.json';samples=json.loads(poses_path.read_text())['rows'];assert len(samples)==225
    frames={n:r['frame'] for n,r in manifest['bodies'].items()}
    parts=native_shapes(base);changed=native_shapes(step);assert set(changed)==set(build['body_frames'])
    for n,p in changed.items():assert len(p.solids())==1 and p.is_valid and p.volume>0,n
    parts.update(changed)
    source=HERE.parents[1]/'src/anthropomorphic_hand/lib'
    inputs={str(p):sha(p) for p in (Path(__file__),manifest_path,build_path,step,base,poses_path,source/'layout.py',source/'static_clearance_relief.py',source/'phalanx_r5_boolean.py',HERE/'rigid_pose_cache.py')}
    cache={};rows=[]
    for sample in samples:
        fk=assembled_transforms(sample['pose']);hits=[]
        for a,b in PAIRS:
            key=relative_pose_key(a,frames[a],b,frames[b],sample['pose'])
            if key not in cache:
                sa=matrix_location(fk[frames[a]])*parts[a];sb=matrix_location(fk[frames[b]])*parts[b]
                cache[key]=sum(s.volume for s in common(sa,sb).solids())
            v=cache[key]
            if v>1e-7:hits.append(dict(a=a,b=b,intersection_mm3=v))
        rows.append(dict(sample=sample['label'],pose=sample['pose'],collisions=hits,pass_=not hits))
        if hits:print('CONTACTS',sample['label'],hits,flush=True)
        if len(rows)%25==0:print('NATIVE REPAIRS',len(rows),'poses',len(cache),'exact relative pairs',flush=True)
    changed_inputs=[p for p,h in inputs.items() if sha(p)!=h]
    report=dict(scope=__doc__,input_sha256=inputs,body_frames=build['body_frames'],step_sha256=sha(step),sample_count=225,exact_relative_pairs=len(cache),rows=rows,changed_during_audit=changed_inputs,complete=not changed_inputs,pass_=not changed_inputs and all(r['pass_'] for r in rows))
    report['pass']=report.pop('pass_');(HERE/'relieved_native_pair_gate.json').write_text(json.dumps(report,indent=2)+'\n')
    print('REPAIRED PAIR GATE',report['pass'],flush=True);assert report['pass']
if __name__=='__main__':main()
