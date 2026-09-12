"""All225 poses, every pair touching a replaced or newly integrated body.

This is a compositional delta only. It cannot pass the whole assembly without
the complete baseline all-pair gate, filtered solely for actually removed parts.
"""
import sys,json,multiprocessing,hashlib
from pathlib import Path
HERE=Path(__file__).parent
sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from lib.native_integration import integrated_native_bodies
from lib.assembly import posed_bodies
from check_assembly_interference import audit
from check_full_route_bodies import placed_bounds
BODIES=None;SAMPLES=None;CHANGED=None

def partition(index):
    cache={};rows=[]
    for sample in SAMPLES[index::8]:
        report=audit(posed_bodies(BODIES,sample['pose']),HERE/f'final_rigid_delta_live_{index}.json',cache,CHANGED)
        report.update(sample=sample['label'],pose=sample['pose']);rows.append(report)
        (HERE/f'final_rigid_delta_partition_{index}.json').write_text(json.dumps({'rows':rows,'complete':len(rows)==len(SAMPLES[index::8]),'pass':all(x['pass'] for x in rows)},indent=2)+'\n')
    return rows

if __name__=='__main__':
    BODIES=[b for b in integrated_native_bodies() if b.frame!='variable']
    baseline=json.loads((HERE/'integration_native_base_frames.json').read_text());old={r['name'] for r in baseline if r['frame']!='variable'}
    base_sha=json.loads((HERE/'integration_native_base_certificate.json').read_text())['step_sha256']
    CHANGED={b.name for b in BODIES if b.name not in old or b.source_sha256!=base_sha}
    inputs={b.source_path:b.source_sha256 for b in BODIES}
    for path in [HERE/'static_route_packet_manifest.json',HERE/'integration_native_base_frames.json',HERE.parents[1]/'src/anthropomorphic_hand/lib/layout.py']:
        inputs[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    removed=old-{b.name for b in BODIES}
    SAMPLES=json.loads((HERE/'static_route_packet_manifest.json').read_text())['rows'];assert len(SAMPLES)==225
    placed_bounds(BODIES)
    print('DELTA',len(BODIES),'bodies',len(CHANGED),'changed',len(removed),'removed',flush=True)
    with multiprocessing.get_context('fork').Pool(8) as pool:parts=pool.map(partition,range(8))
    rows=[r for p in parts for r in p];assert len(rows)==225
    changed_inputs=[p for p,sha in inputs.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=sha]
    report={'scope':'delta only; baseline all-pair certificate also required','input_sha256':inputs,'changed_during_audit':changed_inputs,'body_names':sorted(b.name for b in BODIES),'body_revisions':{b.name:{'step_sha256':b.source_sha256,'frame':b.frame} for b in BODIES},'changed_names':sorted(CHANGED),'removed_names':sorted(removed),'sample_count':225,'rows':rows,'pass':not changed_inputs and all(r['pass'] for r in rows)}
    (HERE/'final_rigid_delta_gate.json').write_text(json.dumps(report,indent=2)+'\n');assert report['pass']
