"""All225 required static poses: every full tendon against all current native bodies.

Workers partition tendons only; every worker samples every pose and every body.
The final certificate requires all48 tendon names in every one of225 rows.
"""
import sys,json,gzip,hashlib,multiprocessing,argparse,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/anthropomorphic_hand'))
from check_full_route_bodies import integration_hardware,audit,placed_bounds
from lib.layout import TENDONS
ROOT=Path(__file__).parent
BODIES=None;MANIFEST=None;PREFIX='static_tendon_solids'

def run_partition(index):
    names={t['name'] for i,t in enumerate(TENDONS) if i%8==index}
    cache={};rows=[];file=ROOT/f'{PREFIX}_partition_{index}.json'
    log=open(ROOT/f'{PREFIX}_partition_{index}.log','w',buffering=1)
    sys.stdout=log;sys.stderr=log
    for sample in MANIFEST['rows']:
        packet=json.loads(gzip.decompress(Path(sample['file']).read_bytes()))
        assert packet['source_sha256']==MANIFEST['source_sha256']
        routes=[r for r in packet['routes'] if r['name'] in names]
        assert len(routes)==6
        result=audit(routes,BODIES,sample['pose'],cache)
        result.update(sample=sample['label']);rows.append(result)
        report={'partition':index,'tendons':sorted(names),'complete':len(rows)==225,'rows':rows,'pass':len(rows)==225 and all(r['pass'] for r in rows)}
        file.write_text(json.dumps(report,indent=2)+'\n')
        print('COMPLETE POSE',sample['label'],result['pass'],'cache',len(cache),flush=True)
    return str(file)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,default=8);parser.add_argument('--baseline',action='store_true');args=parser.parse_args()
    MANIFEST=json.loads((ROOT/'static_route_packet_manifest.json').read_text());assert MANIFEST['complete'] and len(MANIFEST['rows'])==225
    print('FREEZING ALL NATIVE HARDWARE',flush=True)
    if args.baseline:
        from lib.native_integration import frozen_bodies
        BODIES=frozen_bodies(include_variable=False);PREFIX='static_tendon_solids_baseline'
        inputs=[ROOT.parents[1]/'STEP/anthropomorphic_hand/imported/integration_native_base.step',ROOT/'integration_native_base_frames.json']
        evidence={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    else:BODIES,evidence=integration_hardware()
    placed_bounds(BODIES)  # Exact prototype bounds are inherited by forked workers.
    source=ROOT.parents[1]/'src/anthropomorphic_hand'
    if not args.baseline:
        for p in sorted(source.rglob('*.py')):evidence[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    step=ROOT.parents[1]/'STEP/anthropomorphic_hand'
    if not args.baseline:
        for p in sorted(step.glob('*.step')):evidence[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    print('FROZEN',len(BODIES),'bodies',flush=True)
    with multiprocessing.get_context('fork').Pool(args.workers) as pool:files=pool.map(run_partition,range(8))
    parts=[json.loads(Path(p).read_text()) for p in files];rows=[]
    for i,sample in enumerate(MANIFEST['rows']):
        items=[p['rows'][i] for p in parts];table=[r for item in items for r in item['tendon_table']]
        assert {r['tendon'] for r in table}=={t['name'] for t in TENDONS} and len(table)==48
        assert all(item['sample']==sample['label'] for item in items)
        rows.append({'sample':sample['label'],'pose':sample['pose'],'tendon_table':table,'exact_checks':sum(item['exact_distances_tested'] for item in items),'collisions':[c for item in items for c in item['collisions']],'pass':all(item['pass'] for item in items)})
    changed=[p for p,sha in evidence.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=sha]
    report={'body_count':len(BODIES),'sample_count':225,'tendon_count':48,'source_sha256':MANIFEST['source_sha256'],'input_sha256':evidence,'changed_during_audit':changed,'rows':rows,'pass':not changed and all(r['pass'] for r in rows)}
    (ROOT/f'{PREFIX}_gate.json').write_text(json.dumps(report,indent=2)+'\n')
    print('STATIC ALL TENDON SOLIDS',report['pass'],flush=True)
    if not report['pass']:raise SystemExit(1)
