"""All225 final static samples with solved payout against actual native solids.

Each worker owns six tendons and covers all bodies and poses. Individual solids
are passed to OCCT so a one-solid compound cannot hide full containment.
Spools, terminations and reducer parts take their physical payout positions.
"""
import argparse,gzip,hashlib,json,multiprocessing,sys
from pathlib import Path
from native_hand_registry import native_current_bodies,sha,HERE
from check_full_route_bodies import audit,placed_bounds
from lib.layout import TENDONS
from lib.actuator_kinematics import apply_actuator_motion
BODIES=MANIFEST=INPUTS=None
PREFIX='all_native_tendon_solids'
def tuples(x):return tuple(tuples(v) for v in x) if isinstance(x,list) else x

class PayoutCache(dict):
    salt=()
    def _key(self,key):
        # The original congruent-spool proof must additionally identify the
        # exact rotations of the physical solids in this payout sample.
        return ('payout_stored_rope',self.salt,*key[1:]) if key[0]=='actual_stored_rope' else key
    def __contains__(self,key):return super().__contains__(self._key(key))
    def __getitem__(self,key):return super().__getitem__(self._key(key))
    def __setitem__(self,key,value):return super().__setitem__(self._key(key),value)

def partition(index):
    names={t['name'] for i,t in enumerate(TENDONS) if i%8==index}
    checkpoint=HERE/f'{PREFIX}_checkpoint_{index}.json.gz';cache=PayoutCache();rows=[]
    log_path=HERE.parents[3]/f'tmp/anthropomorphic_hand/{PREFIX}_{index}.log'
    with log_path.open('w',buffering=1) as log:
        sys.stdout=log;sys.stderr=log
        if checkpoint.exists():
            saved=json.loads(gzip.decompress(checkpoint.read_bytes()))
            if saved['input_sha256']==INPUTS:rows=saved['rows'];cache=PayoutCache({tuples(k):v for k,v in saved['cache']})
        for i,r in enumerate(rows):assert (r['sample'],r['pose'])==(MANIFEST['rows'][i]['label'],MANIFEST['rows'][i]['pose'])
        for sample in MANIFEST['rows'][len(rows):]:
            path=Path(sample['file']);assert sha(path)==sample['file_sha256']
            packet=json.loads(gzip.decompress(path.read_bytes()))
            assert packet['source_sha256']==sample['source_sha256'] and packet['pose']==sample['pose']
            routes=[r for r in packet['routes'] if r['name'] in names];assert len(routes)==6
            angles=packet['actuator_angles_rad'];assert len(angles)==48
            moved,aliases,active=apply_actuator_motion(BODIES,TENDONS,angles,cache_aliases=True)
            cache.salt=tuple((name,float(angles[name]).hex()) for name in sorted(names))
            r=audit(routes,moved,sample['pose'],cache=cache)
            for items in (r['collisions'],r['stored_rope_solid_proofs'],*[row['collisions'] for row in r['tendon_table']]):
                for item in items:
                    if item.get('body') in aliases:item['body']=aliases[item['body']]
            r.update(sample=sample['label'],actuator_angles_rad=angles);rows.append(r)
            tmp=checkpoint.with_suffix('.tmp');tmp.write_bytes(gzip.compress(json.dumps(dict(input_sha256=INPUTS,rows=rows,cache=list(cache.items())),separators=(',',':')).encode()));tmp.replace(checkpoint)
            (HERE/f'{PREFIX}_partition_{index}.json').write_text(json.dumps(dict(rows=rows,complete=len(rows)==len(MANIFEST['rows']),pass_=all(r['pass'] for r in rows)),indent=2)+'\n')
            print('POSE COMPLETE',len(rows),sample['label'],r['pass'],'cache',len(cache),flush=True)
    return rows

def main():
    global BODIES,MANIFEST,INPUTS,PREFIX
    parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,default=4);parser.add_argument('--sample');args=parser.parse_args()
    BODIES,INPUTS=native_current_bodies(include_reliefs=True)
    for b in BODIES:
        name=b.name;solids=b.shape.solids();assert len(solids)==1,name
        b.shape=solids[0];b.shape.label=name
    manifest_path=HERE/'payout_static_route_packet_manifest.json';MANIFEST=json.loads(manifest_path.read_text());assert len(MANIFEST['rows'])==225 and MANIFEST['complete']
    assert all(sha(p)==h for p,h in MANIFEST['input_sha256'].items())
    INPUTS.update(MANIFEST['input_sha256'])
    if args.sample:
        MANIFEST['rows']=[r for r in MANIFEST['rows'] if r['label']==args.sample];assert len(MANIFEST['rows'])==1,args.sample
        PREFIX=f'all_native_payout_probe_{args.sample}'
    lib=HERE.parents[1]/'src/anthropomorphic_hand/lib'
    paths=[Path(__file__),manifest_path,HERE/'check_full_route_bodies.py',HERE/'path_solid_clearance.py',HERE/'check_hand_route_pairs.py',HERE/'check_middle_hardware_paths.py',*[lib/n for n in ('assembly.py','layout.py','finger_routing.py','transport_guide.py','path_analysis.py','actuator_kinematics.py')]]
    INPUTS.update({str(p):sha(p) for p in paths})
    revisions={b.name:dict(step_sha256=b.source_sha256,frame=b.frame) for b in BODIES}
    placed_bounds(BODIES);print('ALL NATIVE TENDONS',len(BODIES),'bodies,',len(MANIFEST['rows']),'poses',flush=True)
    with multiprocessing.get_context('fork').Pool(args.workers) as pool:parts=pool.map(partition,range(8))
    rows=[]
    for i,sample in enumerate(MANIFEST['rows']):
        items=[p[i] for p in parts];table=[r for item in items for r in item['tendon_table']]
        assert len(table)==48 and {r['tendon'] for r in table}=={t['name'] for t in TENDONS}
        assert all(r['sample']==sample['label'] and r['pose']==sample['pose'] for r in items)
        collisions=[c for r in items for c in r['collisions']]
        rows.append(dict(sample=sample['label'],pose=sample['pose'],tendon_table=table,collisions=collisions,pass_=not collisions))
    changed=[p for p,h in INPUTS.items() if sha(p)!=h]
    report=dict(scope=__doc__,input_sha256=INPUTS,body_revisions=revisions,sample_count=len(rows),tendon_count=48,full_static_coverage=len(rows)==225,rows=rows,changed_during_audit=changed,complete=not changed,pass_=not changed and all(r['pass_'] for r in rows))
    report['pass']=report.pop('pass_');(HERE/f'{PREFIX}_gate.json').write_text(json.dumps(report,indent=2)+'\n');print('NATIVE TENDON GATE',report['pass'],flush=True);assert report['pass']
if __name__=='__main__':main()
