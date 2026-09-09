"""Every final rigid pair outside the retained native all-pair certificate."""
import argparse,gzip,hashlib,json,multiprocessing
from pathlib import Path
from native_hand_registry import native_current_bodies,sha,HERE
from check_native_assembly_interference import audit
from check_full_route_bodies import placed_bounds
from lib.assembly import posed_bodies
BODIES=SAMPLES=INPUTS=CHANGED=GEOMETRY=None
PREFIX='native_replacement_final'
def tuples(x):return tuple(tuples(v) for v in x) if isinstance(x,list) else x

def partition(index):
    path=HERE/f'{PREFIX}_checkpoint_{index}.json.gz';cache={};rows=[]
    if path.exists():
        saved=json.loads(gzip.decompress(path.read_bytes()))
        if saved['geometry_sha256']==GEOMETRY:
            cache={tuples(k):v for k,v in saved['cache']}
            if saved['input_sha256']==INPUTS:rows=saved['rows']
    selected=SAMPLES[index::8]
    for i,r in enumerate(rows):assert (r['sample'],r['pose'])==(selected[i]['label'],selected[i]['pose'])
    def save(cache):
        tmp=path.with_suffix('.tmp');tmp.write_bytes(gzip.compress(json.dumps(dict(geometry_sha256=GEOMETRY,input_sha256=INPUTS,rows=rows,cache=list(cache.items())),separators=(',',':')).encode()));tmp.replace(path)
    for sample in selected[len(rows):]:
        r=audit(posed_bodies(BODIES,sample['pose']),HERE/f'{PREFIX}_live_{index}.json',cache=cache,changed_names=CHANGED,pose=sample['pose'],on_progress=save)
        r.update(sample=sample['label'],pose=sample['pose']);rows.append(r);save(cache)
        (HERE/f'{PREFIX}_partition_{index}.json').write_text(json.dumps(dict(rows=rows,complete=len(rows)==len(selected),pass_=all(r['pass'] for r in rows)),indent=2)+'\n')
    return rows

def main():
    global BODIES,SAMPLES,INPUTS,CHANGED,GEOMETRY
    parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,default=4);args=parser.parse_args()
    BODIES,INPUTS=native_current_bodies(include_reliefs=True)
    retained_path=HERE/'retained_rigid_manifest.json';retained=json.loads(retained_path.read_text())
    revisions={b.name:dict(step_sha256=b.source_sha256,frame=b.frame) for b in BODIES}
    identical={n for n,r in retained['body_revisions'].items() if revisions.get(n)==r}
    CHANGED=set(revisions)-identical
    source=HERE.parents[1]/'src/anthropomorphic_hand/lib'
    for p in (Path(__file__),HERE/'check_native_assembly_interference.py',HERE/'rigid_separation_filter.py',HERE/'rigid_pose_cache.py',HERE/'check_full_route_bodies.py',source/'layout.py',source/'assembly.py',retained_path):INPUTS[str(p)]=sha(p)
    GEOMETRY=hashlib.sha256(json.dumps({'inputs':INPUTS,'revisions':revisions,'changed_names':sorted(CHANGED)},sort_keys=True).encode()).hexdigest()
    manifest_path=HERE/'final_static_route_packet_manifest.json';INPUTS[str(manifest_path)]=sha(manifest_path)
    SAMPLES=json.loads(manifest_path.read_text())['rows'];assert len(SAMPLES)==225
    placed_bounds(BODIES);print('REPLACEMENT DELTA',len(BODIES),len(CHANGED),'changed',flush=True)
    with multiprocessing.get_context('fork').Pool(args.workers) as pool:parts=pool.map(partition,range(8))
    rows=[r for p in parts for r in p];assert len(rows)==225
    changed=[p for p,h in INPUTS.items() if sha(p)!=h]
    report=dict(scope=__doc__,geometry_sha256=GEOMETRY,input_sha256=INPUTS,body_revisions=revisions,retained_names=sorted(identical),changed_names=sorted(CHANGED),sample_count=225,rows=rows,changed_during_audit=changed,complete=not changed,pass_=not changed and all(r['pass'] for r in rows))
    report['pass']=report.pop('pass_')
    (HERE/f'{PREFIX}_gate.json').write_text(json.dumps(report,indent=2)+'\n');assert report['pass']
if __name__=='__main__':main()
