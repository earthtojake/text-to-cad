"""Native rigid-pair supplement for physically rotating forearm actuators.

Every pair with a rotating actuator endpoint is tested. The separate native
hand-frame gates cover all pairs unaffected by payout at the same225 poses.
Only components receiving the identical authored isometry share a cache frame.
Output parts and input parts keep separate per-actuator frame identities.
"""
import argparse,gzip,json,multiprocessing
from pathlib import Path
from native_hand_registry import native_current_bodies,sha,HERE
from check_native_assembly_interference import audit
from check_full_route_bodies import placed_bounds
from lib.assembly import posed_bodies
from lib.actuator_kinematics import apply_actuator_motion,body_actuator_motion,OUTPUT_ROLES,INPUT_ROLES
import numpy as np
from lib.layout import TENDONS
BODIES=MANIFEST=INPUTS=None
PREFIX='native_payout_rigid_grouped'
def tuples(x):return tuple(tuples(v) for v in x) if isinstance(x,list) else x

def partition(index):
    selected=MANIFEST['rows'][index::8];rows=[];cache={};checkpoint=HERE/f'{PREFIX}_checkpoint_{index}.json.gz'
    if checkpoint.exists():
        old=json.loads(gzip.decompress(checkpoint.read_bytes()))
        if old['input_sha256']==INPUTS:rows=old['rows'];cache={tuples(k):v for k,v in old['cache']}
    for i,row in enumerate(rows):assert (row['sample'],row['pose'])==(selected[i]['label'],selected[i]['pose'])
    def save(cache):
        tmp=checkpoint.with_suffix('.tmp');tmp.write_bytes(gzip.compress(json.dumps(dict(input_sha256=INPUTS,rows=rows,cache=list(cache.items())),separators=(',',':')).encode()));tmp.replace(checkpoint)
    for sample in selected[len(rows):]:
        path=Path(sample['file']);assert sha(path)==sample['file_sha256']
        packet=json.loads(gzip.decompress(path.read_bytes()));assert packet['pose']==sample['pose'] and packet['source_sha256']==sample['source_sha256']
        angles=packet['actuator_angles_rad'];assert len(angles)==48
        bodies,aliases,active=apply_actuator_motion(posed_bodies(BODIES,sample['pose']),TENDONS,angles)
        group_matrices={}
        for body in bodies:
            if body.name not in aliases:continue
            tendon=next(t for t in TENDONS if body.name.startswith(t['actuator']+'_'))
            role=body.name[len(tendon['actuator'])+1:]
            group='output' if role in OUTPUT_ROLES or role.startswith('gearbox_planet_pin_') else 'input' if role in INPUT_ROLES else role
            frame='physical_actuator:'+tendon['actuator']+':'+group
            matrix=body_actuator_motion(body.name,TENDONS,angles)
            if frame in group_matrices:assert np.array_equal(matrix,group_matrices[frame]),('nonrigid cache group',frame,body.name)
            group_matrices[frame]=matrix;body.frame=frame
        if active:
            result=audit(bodies,HERE/f'{PREFIX}_live_{index}.json',cache=cache,changed_names=active,on_progress=save)
        else:result=dict(body_count=len(bodies),complete=True,pass_=True,collisions=[],pair_scope='No nonzero actuator rotation; covered by the hand-frame native gates.');result['pass']=result.pop('pass_')
        result.update(sample=sample['label'],pose=sample['pose'],actuator_angles_rad=angles,moving_bodies=sorted(active));rows.append(result);save(cache)
        (HERE/f'{PREFIX}_partition_{index}.json').write_text(json.dumps(dict(rows=rows,complete=len(rows)==len(selected),pass_=all(r['pass'] for r in rows)),indent=2)+'\n')
        print('PAYOUT RIGIDS',sample['label'],result['pass'],len(active),flush=True)
    return rows

def main():
    global BODIES,MANIFEST,INPUTS,PREFIX
    parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,default=4);parser.add_argument('--sample');args=parser.parse_args()
    BODIES,INPUTS=native_current_bodies(include_reliefs=True)
    manifest_path=HERE/'payout_static_route_packet_manifest.json';MANIFEST=json.loads(manifest_path.read_text());assert MANIFEST['complete'] and len(MANIFEST['rows'])==225
    assert all(sha(p)==h for p,h in MANIFEST['input_sha256'].items())
    INPUTS.update(MANIFEST['input_sha256'])
    if args.sample:
        MANIFEST['rows']=[r for r in MANIFEST['rows'] if r['label']==args.sample];assert len(MANIFEST['rows'])==1
        PREFIX=f'native_payout_rigid_grouped_probe_{args.sample}'
    lib=HERE.parents[1]/'src/anthropomorphic_hand/lib'
    paths=[Path(__file__),manifest_path,HERE/'check_native_assembly_interference.py',HERE/'rigid_separation_filter.py',HERE/'rigid_pose_cache.py',HERE/'check_full_route_bodies.py',*[lib/n for n in ('assembly.py','layout.py','actuator_kinematics.py')]]
    INPUTS.update({str(p):sha(p) for p in paths})
    revisions={b.name:dict(step_sha256=b.source_sha256,frame=b.frame) for b in BODIES}
    placed_bounds(BODIES)
    with multiprocessing.get_context('fork').Pool(args.workers) as pool:partitions=pool.map(partition,range(8))
    rows=[r for part in partitions for r in part];assert len(rows)==len(MANIFEST['rows'])
    changed=[p for p,h in INPUTS.items() if sha(p)!=h]
    report=dict(scope=__doc__,input_sha256=INPUTS,body_revisions=revisions,sample_count=len(rows),full_static_coverage=len(rows)==225,rows=rows,changed_during_audit=changed,complete=not changed,pass_=not changed and all(r['pass'] for r in rows))
    report['pass']=report.pop('pass_');(HERE/f'{PREFIX}_gate.json').write_text(json.dumps(report,indent=2)+'\n');assert report['pass']
if __name__=='__main__':main()
