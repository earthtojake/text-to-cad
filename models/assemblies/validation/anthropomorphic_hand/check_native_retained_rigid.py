"""Native all-pair proof for final retained bodies, complementary to replacements.

Every excluded body must be covered by the final replacement delta. This gate
alone never certifies the whole assembly. Exact named pair proofs from the
superseded baseline are reused only after verifying their geometry and engine.
"""
import argparse,ast,gzip,hashlib,json,multiprocessing,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;SRC=HERE.parents[1]/'src/anthropomorphic_hand'
sys.path.insert(0,str(SRC))
from check_native_reported_contacts import native_shapes
from check_native_assembly_interference import audit
from check_full_route_bodies import placed_bounds
from lib.assembly import Body,posed_bodies
BODIES=SAMPLES=INPUTS=GEOMETRY=SEED=None
PREFIX='native_retained_final'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def tuples(x):return tuple(tuples(v) for v in x) if isinstance(x,list) else x

def partition(index):
    path=HERE/f'{PREFIX}_checkpoint_{index}.json.gz';cache=dict(SEED);rows=[]
    if path.exists():
        saved=json.loads(gzip.decompress(path.read_bytes()))
        if saved['geometry_sha256']==GEOMETRY:
            cache.update({tuples(k):v for k,v in saved['cache']})
            if saved['input_sha256']==INPUTS:rows=saved['rows']
    selected=SAMPLES[index::8]
    for i,row in enumerate(rows):assert (row['sample'],row['pose'])==(selected[i]['label'],selected[i]['pose'])
    def save(cache):
        payload=dict(geometry_sha256=GEOMETRY,input_sha256=INPUTS,rows=rows,cache=list(cache.items()))
        tmp=path.with_suffix('.tmp');tmp.write_bytes(gzip.compress(json.dumps(payload,separators=(',',':')).encode()));tmp.replace(path)
    for sample in selected[len(rows):]:
        r=audit(posed_bodies(BODIES,sample['pose']),HERE/f'{PREFIX}_live_{index}.json',cache=cache,pose=sample['pose'],on_progress=save)
        r.update(sample=sample['label'],pose=sample['pose']);rows.append(r);save(cache)
        (HERE/f'{PREFIX}_partition_{index}.json').write_text(json.dumps(dict(rows=rows,complete=len(rows)==len(selected),pass_=all(r['pass'] for r in rows)),indent=2)+'\n')
    return rows

def main():
    global BODIES,SAMPLES,INPUTS,GEOMETRY,SEED
    parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,default=4);args=parser.parse_args()
    base_path=HERE/'integration_native_base_certificate.json';base=json.loads(base_path.read_text())
    revision_path=HERE/'final_rigid_delta_gate.json';revisions=json.loads(revision_path.read_text())['body_revisions']
    meta_path=HERE/'integration_native_base_frames.json';meta={r['name']:r for r in json.loads(meta_path.read_text())}
    step=HERE.parents[1]/'STEP/anthropomorphic_hand/imported/integration_native_base.step';assert sha(step)==base['step_sha256']
    retained={n for n,r in revisions.items() if r['step_sha256']==base['step_sha256']}
    reserved=set()
    frame_paths=[HERE/f'{family}_export_repair_frames.json' for family in ('fingertip_pad','fingernail')]
    for path in frame_paths:reserved.update(r['name'] for r in json.loads(path.read_text()))
    relief_path=SRC/'lib/static_clearance_relief.py'
    pairs=next(ast.literal_eval(n.value) for n in ast.parse(relief_path.read_text()).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PAIRS' for t in n.targets))
    reserved.update(a for a,b in pairs)
    # The pending continuous-waist design may replace these support families.
    # Reserving them here is conservative: the final delta must check them
    # whether or not the visual candidate is ultimately selected.
    reserved.update(n for n in retained if n=='middle_proximal_frame' or n.startswith(('middle_mcp_outlet_comb','middle_pip_inlet_comb','middle_pip_drive_guide')))
    retained-=reserved
    engine_paths=[Path(__file__),HERE/'check_native_assembly_interference.py',HERE/'rigid_separation_filter.py',HERE/'rigid_pose_cache.py',HERE/'check_full_route_bodies.py',SRC/'lib/layout.py',SRC/'lib/assembly.py']
    geometry_inputs={str(p):sha(p) for p in [step,meta_path,*engine_paths]}
    GEOMETRY=hashlib.sha256(json.dumps({'inputs':geometry_inputs,'body_names':sorted(retained)},sort_keys=True).encode()).hexdigest()
    manifest_path=HERE/'final_static_route_packet_manifest.json'
    INPUTS={**geometry_inputs,**{str(p):sha(p) for p in [base_path,revision_path,manifest_path,*frame_paths]}}
    SAMPLES=json.loads(manifest_path.read_text())['rows'];assert len(SAMPLES)==225
    SEED={};seed_sources={}
    for path in sorted(HERE.glob('native_verified_baseline_checkpoint_*.json.gz')):
        saved=json.loads(gzip.decompress(path.read_bytes()));old=saved['input_sha256']
        required=[step,meta_path,HERE/'check_native_assembly_interference.py',HERE/'rigid_separation_filter.py',HERE/'rigid_pose_cache.py',SRC/'lib/layout.py']
        assert all(old.get(str(p))==sha(p) for p in required)
        assert all(sha(p)==h for p,h in old.items()),'superseded proof input changed'
        seed_sources[str(path)]=sha(path)
        for raw,value in saved['cache']:
            key=tuples(raw)
            if key[0]=='authored_relative_pose' and key[1] in retained and key[2] in retained:
                if key in SEED:assert abs(SEED[key]-value)<1e-7,(key,SEED[key],value)
                SEED[key]=value
    INPUTS.update(seed_sources)
    native=native_shapes(step);assert set(meta)==set(native)
    BODIES=[Body(native[n],**{k:meta[n][k] for k in ('frame','system','kind')}) for n in sorted(retained)]
    identity={'scope':__doc__,'geometry_sha256':GEOMETRY,'body_revisions':{n:revisions[n] for n in sorted(retained)},'reserved_for_delta':sorted(reserved),'seed_pair_proofs':len(SEED),'input_sha256':INPUTS}
    (HERE/'retained_rigid_manifest.json').write_text(json.dumps(identity,indent=2)+'\n')
    placed_bounds(BODIES);print('RETAINED',len(BODIES),'SEED EXACT PAIRS',len(SEED),flush=True)
    with multiprocessing.get_context('fork').Pool(args.workers) as pool:parts=pool.map(partition,range(8))
    rows=[r for p in parts for r in p];assert len(rows)==225
    changed=[p for p,h in INPUTS.items() if sha(p)!=h]
    report={**identity,'sample_count':225,'rows':rows,'changed_during_audit':changed,'complete':not changed,'pass':not changed and all(r['pass'] for r in rows)}
    (HERE/f'{PREFIX}_gate.json').write_text(json.dumps(report,indent=2)+'\n');assert report['pass']
if __name__=='__main__':main()
