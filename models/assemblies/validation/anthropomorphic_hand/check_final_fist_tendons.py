"""All 48 corrected-fist routes against the actual exported rigid solids."""
import gzip,json
from pathlib import Path
from native_hand_registry import native_current_bodies,sha,HERE
from check_full_route_bodies import audit

def main():
    bodies,inputs=native_current_bodies()
    manifest_path=HERE/'final_static_route_packet_manifest.json'
    route_gate_path=HERE/'final_fist_route_gate.json'
    candidate_path=HERE/'final_fist_candidate.json'
    manifest=json.loads(manifest_path.read_text())
    candidate=json.loads(candidate_path.read_text())
    row=next(r for r in manifest['rows'] if r['label']==candidate['label'])
    packet_path=Path(row['file']);packet=json.loads(gzip.decompress(packet_path.read_bytes()))
    gate=json.loads(route_gate_path.read_text())
    assert gate['pass'] and gate['packet_sha256']==row['file_sha256']==sha(packet_path)
    assert packet['source_sha256']==row['source_sha256'] and packet['pose']==candidate['pose']
    for path in (Path(__file__),manifest_path,route_gate_path,candidate_path,packet_path,HERE/'check_full_route_bodies.py',HERE/'path_solid_clearance.py'):
        inputs[str(path)]=sha(path)
    # DistShapeShape must receive a solid, not a one-solid compound: the
    # latter can miss containment and report a positive boundary distance.
    for body in bodies:
        name=body.name;solids=body.shape.solids();assert len(solids)==1,name
        body.shape=solids[0];body.shape.label=name
    report=audit(packet['routes'],bodies,packet['pose'])
    report.update(scope=__doc__,input_sha256=inputs,packet_sha256=sha(packet_path))
    report['changed_during_audit']=[p for p,h in inputs.items() if sha(p)!=h]
    report['pass'] &= not report['changed_during_audit']
    (HERE/'final_fist_tendon_solids.json').write_text(json.dumps(report,indent=2)+'\n')
    print('FINAL FIST TENDON SOLIDS',report['pass'],len(report['collisions']),flush=True)
    assert report['pass']

if __name__=='__main__':main()
