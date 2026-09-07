"""All native neighbours of the two rerouted CMC supports at225 static poses.

This focused gate diagnoses new support contacts while the complete replacement
audit runs. It is not a substitute for that all-replacement certificate.
"""
import argparse,gzip,json,multiprocessing,re
from pathlib import Path
from native_hand_registry import native_current_bodies,sha,HERE
from check_native_reported_contacts import native_shapes
from check_native_assembly_interference import audit
from check_full_route_bodies import placed_bounds
from lib.assembly import Body,posed_bodies
NAMES={'thumb_cmc_negative_yaw_outlet_structural_jaw_1','thumb_radial_shared_guide_bank_structural'}
BODIES=MANIFEST=INPUTS=None;PREFIX='native_reroute_supports_r10'
def tuples(x):return tuple(tuples(v) for v in x) if isinstance(x,list) else x

def partition(index):
    selected=MANIFEST['rows'][index::4];path=HERE/f'{PREFIX}_checkpoint_{index}.json.gz';cache={};rows=[]
    if path.exists():
        old=json.loads(gzip.decompress(path.read_bytes()))
        if old['input_sha256']==INPUTS:rows=old['rows'];cache={tuples(k):v for k,v in old['cache']}
    def save(cache):
        tmp=path.with_suffix('.tmp');tmp.write_bytes(gzip.compress(json.dumps(dict(input_sha256=INPUTS,rows=rows,cache=list(cache.items())),separators=(',',':')).encode()));tmp.replace(path)
    for sample in selected[len(rows):]:
        result=audit(posed_bodies(BODIES,sample['pose']),HERE/f'{PREFIX}_live_{index}.json',cache=cache,changed_names=NAMES,pose=sample['pose'],on_progress=save)
        result.update(sample=sample['label'],pose=sample['pose']);rows.append(result);save(cache)
        (HERE/f'{PREFIX}_partition_{index}.json').write_text(json.dumps(dict(rows=rows,complete=len(rows)==len(selected)),indent=2)+'\n')
        print('REROUTE SUPPORTS',sample['label'],result['pass'],len(result['collisions']),flush=True)
    return rows

def main():
    global BODIES,MANIFEST,INPUTS,PREFIX
    parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,default=2);parser.add_argument('--prefix',default=PREFIX);parser.add_argument('--jaw-step');parser.add_argument('--bank-step');args=parser.parse_args()
    assert re.fullmatch('[a-zA-Z0-9_]+',args.prefix);PREFIX=args.prefix
    BODIES,INPUTS=native_current_bodies(include_reliefs=True)
    for name,filename in [('thumb_cmc_negative_yaw_outlet_structural_jaw_1',args.jaw_step),('thumb_radial_shared_guide_bank_structural',args.bank_step)]:
        if filename:
            path=Path(filename).resolve();native=native_shapes(path);assert name in native
            for i,body in enumerate(BODIES):
                if body.name==name:
                    new=Body(native[name],body.frame,body.system,body.kind);new.source_sha256=sha(path);new.source_path=str(path);BODIES[i]=new;break
            else:raise AssertionError(name)
            INPUTS[str(path)]=sha(path)
    manifest_path=HERE/'final_static_route_packet_manifest.json';MANIFEST=json.loads(manifest_path.read_text());assert MANIFEST['complete'] and len(MANIFEST['rows'])==225
    lib=HERE.parents[1]/'src/anthropomorphic_hand/lib'
    paths=[Path(__file__),manifest_path,HERE/'check_native_assembly_interference.py',HERE/'rigid_separation_filter.py',HERE/'rigid_pose_cache.py',HERE/'check_full_route_bodies.py',lib/'assembly.py',lib/'layout.py']
    INPUTS.update({str(p):sha(p) for p in paths});placed_bounds(BODIES)
    revisions={b.name:dict(step_sha256=b.source_sha256,frame=b.frame) for b in BODIES}
    with multiprocessing.get_context('fork').Pool(args.workers) as pool:parts=pool.map(partition,range(4))
    rows=[r for p in parts for r in p];assert len(rows)==225
    changed=[p for p,h in INPUTS.items() if sha(p)!=h]
    report=dict(scope=__doc__,input_sha256=INPUTS,body_revisions=revisions,changed_names=sorted(NAMES),rows=rows,sample_count=225,complete=not changed,changed_during_audit=changed,pass_=not changed and all(r['pass'] for r in rows));report['pass']=report.pop('pass_')
    (HERE/f'{PREFIX}_gate.json').write_text(json.dumps(report,indent=2)+'\n');assert report['pass']
if __name__=='__main__':main()
