"""Add an independently checked fist packet without changing frozen evidence."""
import ast,copy,gzip,hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
LIB=HERE.parents[1]/'src/anthropomorphic_hand/lib'
sys.path.insert(0,str(LIB.parent))
from lib.hand_routing import full_tendon_routes
from lib.actuator_payout import solve_rotation,neutral_forearm_length,_BY_NAME
from lib.forearm_routing import forearm_route
from lib.path_analysis import path_length
from check_static_route_packets import audit
from check_tendon_self_spacing import check_route

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def route_dependencies():
    """Fingerprint the transitive routing imports, excluding unrelated solids."""
    pending=['hand_routing','actuator_payout','path_analysis'];seen=set()
    while pending:
        name=pending.pop()
        if name in seen:continue
        path=LIB/(name+'.py')
        assert path.exists(),path
        seen.add(name)
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node,ast.ImportFrom):
                module=node.module or ''
                if module.startswith('lib.'):
                    pending.append(module.split('.')[1])
                elif node.level and module:
                    pending.append(module.split('.')[0])
            elif isinstance(node,ast.Import):
                pending.extend(a.name.split('.')[1] for a in node.names if a.name.startswith('lib.'))
    return [LIB/(name+'.py') for name in sorted(seen)]

def main():
    baseline_path=HERE/'static_route_packet_manifest.json';base=json.loads(baseline_path.read_text())
    candidate_path=HERE/'final_fist_candidate.json';candidate=json.loads(candidate_path.read_text())
    neutral=json.loads(gzip.decompress(Path(base['rows'][0]['file']).read_bytes()))['routes']
    assert base['rows'][0]['pose']=={}
    wrist=[dict(name=r['name'],path=copy.deepcopy(next(g['path'] for g in r['groups'] if g['label']==r['name']+'_wrist_guide'))) for r in neutral]
    inputs={str(p):sha(p) for p in [baseline_path,candidate_path,Path(__file__),HERE/'check_static_route_packets.py',HERE/'check_tendon_self_spacing.py',*route_dependencies(),*sorted(LIB.glob('*.json'))]}
    fingerprint=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()
    pose_hash=hashlib.sha256(json.dumps(candidate['pose'],sort_keys=True).encode()).hexdigest()[:16]
    packet_path=HERE/f'static_route_packets/anatomical_fist_{pose_hash}.json.gz'
    saved=json.loads(gzip.decompress(packet_path.read_bytes())) if packet_path.exists() else {}
    if saved.get('source_sha256')!=fingerprint:
        print('GENERATE',candidate['pose'],flush=True)
        routes=full_tendon_routes(wrist,candidate['pose'])
        saved={'source_sha256':fingerprint,'input_sha256':inputs,'pose':candidate['pose'],'routes':routes}
        packet_path.write_bytes(gzip.compress(json.dumps(saved,separators=(',',':')).encode()))
    routes=saved['routes'];assert len(routes)==48
    print('CHECK CURVES',flush=True);curves=audit(routes)
    print('CHECK SELF SPACING',flush=True);self_spacing=[check_route(r) for r in routes]
    lengths={r['name']:path_length(r['path']) for r in neutral};payout=[]
    for r in routes:
        name=r['name'];delta=path_length(r['path'])-lengths[name];q=solve_rotation(name,delta)
        residual=path_length(forearm_route(_BY_NAME[name],q)['path'])-neutral_forearm_length(name)+delta
        payout.append(dict(tendon=name,downstream_change_mm=delta,capstan_rotation_rad=q,total_length_residual_mm=residual,pass_=abs(residual)<1e-7))
    report={'scope':'Fist route geometry, self-spacing and payout only; body collisions remain a separate gate.','packet_sha256':sha(packet_path),'curve_gate':curves,'self_spacing':self_spacing,'payout':payout,'pass':curves['pass'] and all(r['pass'] for r in self_spacing) and all(r['pass_'] for r in payout)}
    (HERE/'final_fist_route_gate.json').write_text(json.dumps(report,indent=2)+'\n')
    assert report['pass']
    rows=[]
    for row in base['rows']:
        if row['label']=='full_fist_candidate':
            rows.append(dict(label=candidate['label'],pose=candidate['pose'],file=str(packet_path),file_sha256=sha(packet_path),source_sha256=fingerprint,tendon_count=48))
        else:rows.append({**row,'file_sha256':sha(row['file']),'source_sha256':base['source_sha256']})
    assert len(rows)==225
    final={'scope':'224 immutable original samples plus the independently generated fist candidate. No joint ranges changed.','baseline_manifest_sha256':sha(baseline_path),'sample_count':225,'complete':True,'rows':rows}
    final['source_sha256']=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()
    (HERE/'final_static_route_packet_manifest.json').write_text(json.dumps(final,indent=2)+'\n')
    print('FINAL FIST ROUTE GATE',report['pass'],flush=True)

if __name__=='__main__':main()
