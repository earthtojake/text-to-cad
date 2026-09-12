"""Resumable native STEP audit, retaining exact pair proofs at checkpoints."""
import argparse,gzip,hashlib,json,multiprocessing,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from check_native_reported_contacts import native_shapes
from check_native_assembly_interference import audit
from check_full_route_bodies import placed_bounds
from lib.assembly import Body,posed_bodies

BODIES=SAMPLES=INPUTS=PREFIX=None
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def tuples(value):return tuple(tuples(v) for v in value) if isinstance(value,list) else value

def partition(index):
    checkpoint=HERE/f'{PREFIX}_checkpoint_{index}.json.gz'
    rows=[];cache={}
    if checkpoint.exists():
        saved=json.loads(gzip.decompress(checkpoint.read_bytes()))
        if saved['input_sha256']==INPUTS:
            rows=saved['rows'];cache={tuples(k):v for k,v in saved['cache']}
    def save(cache):
        payload={'input_sha256':INPUTS,'rows':rows,'cache':list(cache.items())}
        temporary=checkpoint.with_suffix('.tmp');temporary.write_bytes(gzip.compress(json.dumps(payload,separators=(',',':')).encode()));temporary.replace(checkpoint)
    selected=SAMPLES[index::8]
    assert len(rows)<=len(selected)
    for i,row in enumerate(rows):assert row['sample']==selected[i]['label']
    for sample in selected[len(rows):]:
        report=audit(posed_bodies(BODIES,sample['pose']),HERE/f'{PREFIX}_live_{index}.json',cache=cache,pose=sample['pose'],on_progress=save)
        report.update(sample=sample['label'],pose=sample['pose']);rows.append(report);save(cache)
        (HERE/f'{PREFIX}_partition_{index}.json').write_text(json.dumps({'rows':rows,'complete':len(rows)==len(selected),'pass':all(r['pass'] for r in rows)},indent=2)+'\n')
    return rows

def main():
    global BODIES,SAMPLES,INPUTS,PREFIX
    parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,default=4);args=parser.parse_args()
    PREFIX='native_verified_baseline'
    step=HERE.parents[1]/'STEP/anthropomorphic_hand/imported/integration_native_base.step'
    meta=HERE/'integration_native_base_frames.json';manifest=HERE/'static_route_packet_manifest.json'
    paths=[step,meta,manifest,Path(__file__),HERE/'check_native_assembly_interference.py',HERE/'rigid_separation_filter.py',HERE/'rigid_separation_filter_check.json',HERE/'rigid_pose_cache.py',HERE.parents[1]/'src/anthropomorphic_hand/lib/layout.py']
    INPUTS={str(p):sha(p) for p in paths}
    filter_check=json.loads((HERE/'rigid_separation_filter_check.json').read_text());assert filter_check['pass']
    assert filter_check['input_sha256'][str(HERE/'rigid_separation_filter.py')]==sha(HERE/'rigid_separation_filter.py')
    mapping={r['name']:r for r in json.loads(meta.read_text())};native=native_shapes(step)
    assert set(native)==set(mapping)
    BODIES=[Body(shape,**{k:mapping[name][k] for k in ('frame','system','kind')}) for name,shape in sorted(native.items()) if mapping[name]['frame']!='variable']
    SAMPLES=json.loads(manifest.read_text())['rows'];assert len(SAMPLES)==225
    placed_bounds(BODIES);print('NATIVE AUDIT',len(BODIES),flush=True)
    with multiprocessing.get_context('fork').Pool(args.workers) as pool:parts=pool.map(partition,range(8))
    rows=[r for part in parts for r in part];assert len(rows)==225
    assert all(sha(p)==h for p,h in INPUTS.items())
    result={'sample_count':225,'body_count':len(BODIES),'input_sha256':INPUTS,'rows':rows,'pass':all(r['pass'] for r in rows)}
    (HERE/f'{PREFIX}_assembly_gate.json').write_text(json.dumps(result,indent=2)+'\n')
    assert result['pass']

if __name__=='__main__':main()
