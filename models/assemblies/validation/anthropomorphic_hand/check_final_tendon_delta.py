"""All full static tendon packets against every changed native rigid body.

Combined with the immutable baseline certificate this covers every current body;
only baseline failures belonging to actually replaced or removed bodies may be
superseded. This script never infers a whole-hand pass from the delta alone.
"""
import sys,json,hashlib,multiprocessing
from pathlib import Path
HERE=Path(__file__).parent
sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
import check_static_tendon_solids as gate
from lib.native_integration import integrated_native_bodies
from lib.layout import TENDONS
if __name__=='__main__':
    all_bodies=[b for b in integrated_native_bodies() if b.frame!='variable']
    base=json.loads((HERE/'static_tendon_solids_baseline_gate.json').read_text())
    base_sha=json.loads((HERE/'integration_native_base_certificate.json').read_text())['step_sha256']
    gate.BODIES=[b for b in all_bodies if b.source_sha256!=base_sha]
    gate.PREFIX='final_tendon_delta'
    gate.MANIFEST=json.loads((HERE/'static_route_packet_manifest.json').read_text())
    assert base['source_sha256']==gate.MANIFEST['source_sha256'] and len(base['rows'])==225
    inputs={b.source_path:b.source_sha256 for b in all_bodies}
    revisions={b.name:{'sha256':b.source_sha256,'frame':b.frame} for b in all_bodies}
    (HERE/'final_tendon_delta_inputs.json').write_text(json.dumps({'inputs':inputs,'body_revisions':revisions},indent=2)+'\n')
    print('DELTA',len(gate.BODIES),'of',len(all_bodies),flush=True)
    gate.placed_bounds(gate.BODIES)
    with multiprocessing.get_context('fork').Pool(4) as pool:files=pool.map(gate.run_partition,range(8))
    parts=[json.loads(Path(f).read_text()) for f in files]
    assert all(p['complete'] and len(p['rows'])==225 for p in parts)
    unchanged={b.name for b in all_bodies if b.source_sha256==base_sha}
    rows=[]
    for i,s in enumerate(gate.MANIFEST['rows']):
        prior=base['rows'][i];assert prior['sample']==s['label']
        items=[p['rows'][i] for p in parts];assert all(x['sample']==s['label'] for x in items)
        table=[r for x in items for r in x['tendon_table']]
        assert len(table)==48 and {r['tendon'] for r in table}=={t['name'] for t in TENDONS}
        old_hits=[c for c in prior['collisions'] if c['body'] in unchanged]
        collisions=old_hits+[c for x in items for c in x['collisions']]
        for r in table:
            r['collisions'] += [c for c in old_hits if c['tendon']==r['tendon']]
            r['clear']=not r['collisions']
        rows.append({'sample':s['label'],'pose':s['pose'],'tendon_table':table,'collisions':collisions,'pass':not collisions})
    changed=[p for p,sha in inputs.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=sha]
    report={'scope':'complete current rigid assembly, compositional baseline plus exact changed-body delta','body_count':len(all_bodies),'changed_body_count':len(gate.BODIES),'sample_count':225,'tendon_count':48,'source_sha256':gate.MANIFEST['source_sha256'],'body_revisions':revisions,'inputs':inputs,'changed_during_audit':changed,'baseline_certificate_sha256':hashlib.sha256((HERE/'static_tendon_solids_baseline_gate.json').read_bytes()).hexdigest(),'rows':rows,'pass':not changed and all(r['pass'] for r in rows)}
    (HERE/'final_static_tendon_solids_gate.json').write_text(json.dumps(report,indent=2)+'\n');assert report['pass']
