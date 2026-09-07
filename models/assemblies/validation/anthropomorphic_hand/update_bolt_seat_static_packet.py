"""Exact single-packet replacement with unchanged-path proof reuse for224 poses."""
import json,gzip,hashlib
from pathlib import Path
from check_static_route_packets import audit
root=Path(__file__).parent
manifestfile=root/'static_route_packet_manifest.json';manifest=json.loads(manifestfile.read_text())
gatefile=root/'static_full_tendon_curve_gate.json';oldbytes=gatefile.read_bytes();gate=json.loads(oldbytes)
assert gate['pass'] and gate['complete'] and gate['sample_count']==225
repair=json.loads((root/'wrist_bolt_seat_repair.json').read_text());name=repair['replacement']['name']
source=hashlib.sha256(manifest['source_sha256'].encode()+(root/'wrist_bolt_seat_repair.json').read_bytes()).hexdigest()
proof=[];replacement_result=None
for row in manifest['rows']:
    file=Path(row['file']);packet=json.loads(gzip.decompress(file.read_bytes()))
    assert packet['source_sha256']==manifest['source_sha256']
    old_routes=hashlib.sha256(json.dumps(packet['routes'],sort_keys=True).encode()).hexdigest()
    if row['pose']==repair['pose']:
        route=next(r for r in packet['routes'] if r['name']==name)
        group=next(g for g in route['groups'] if g['label']==name+'_wrist_guide')
        assert group['path']==repair['old']['path']
        group['path']=repair['replacement']['path'];route['path']=[s for g in route['groups'] for s in g['path']]
        print('RECHECK',row['label'],flush=True)
        replacement_result=audit(packet['routes']);replacement_result.update(sample=row['label'],pose=row['pose'])
        assert replacement_result['pass'],replacement_result['conflicts']
        gate['rows'][next(i for i,r in enumerate(gate['rows']) if r['sample']==row['label'])]=replacement_result
    new_routes=hashlib.sha256(json.dumps(packet['routes'],sort_keys=True).encode()).hexdigest()
    proof.append({'sample':row['label'],'previous_paths_sha256':old_routes,'new_paths_sha256':new_routes,'identical_paths_proof_reused':old_routes==new_routes})
    packet['source_sha256']=source;file.write_bytes(gzip.compress(json.dumps(packet,separators=(',',':')).encode()))
assert replacement_result is not None and sum(r['identical_paths_proof_reused'] for r in proof)==224
manifest['source_sha256']=source;manifestfile.write_text(json.dumps(manifest,indent=2)+'\n')
gate['source_sha256']=source;gate['incremental_proof']={'previous_complete_gate_sha256':hashlib.sha256(oldbytes).hexdigest(),'replacement':'wrist_bolt_seat_repair.json','rows':proof};gate['pass']=all(r['pass'] for r in gate['rows']);gatefile.write_text(json.dumps(gate,indent=2)+'\n')
print('225POSE CURVE GATE',gate['pass'],'224exactlyunchanged;1fullyrechecked',flush=True)
