"""Evaluate full paths for every required static10-degree and named pose."""
import sys,json,gzip,hashlib,copy
from pathlib import Path
from functools import lru_cache
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/anthropomorphic_hand'))
from lib import assembled_routing,hand_routing,thumb_routing
from lib.layout import JOINTS
from check_guide_combs import cached_routes
from check_global_phalanges import named_poses
root=Path(__file__).parent;dest=root/'static_route_packets';dest.mkdir(exist_ok=True)
finger_original=assembled_routing.finger_routes
@lru_cache(maxsize=256)
def cached_finger(name,items):return cached_routes(name,dict(items))
assembled_routing.finger_routes=lambda name,pose=None:copy.deepcopy(cached_finger(name,tuple(sorted((pose or {}).items()))))
thumb_original=hand_routing.thumb_routes
@lru_cache(maxsize=128)
def cached_thumb(items):return thumb_original(dict(items))
hand_routing.thumb_routes=lambda pose=None,cmc_packet=None:copy.deepcopy(cached_thumb(tuple(sorted((k,v) for k,v in(pose or {}).items() if k.startswith(('thumb_','wrist_')))))) if cmc_packet is None else thumb_original(pose,cmc_packet)
sources=['hand_routing.py','assembled_routing.py','finger_routing.py','thumb_routing.py','thumb_downstream.py','thumb_cmc_transport.py','thumb_cmc_atlas.py','cup_transport.py','cup_atlas.py','forearm_routing.py','layout.py','bowden_mcp.py','yaw_transport.py','pip_transport.py']
libroot=root.parents[1]/'src/anthropomorphic_hand/lib'
wristfile=root/'wrist_mount_repaired_packets.json';wrists=json.loads(wristfile.read_text())['samples']
assert len(wrists)==18
fingerprint=hashlib.sha256(b''.join((libroot/n).read_bytes() for n in sources)+wristfile.read_bytes()).hexdigest()
packets={json.dumps(r['pose'],sort_keys=True):r['routes'] for r in wrists};neutral=packets['{}']
samples=named_poses()
for joint in JOINTS:
    lo,hi=joint.limits
    samples.extend((f'{joint.name}_{q:g}',{joint.name:float(q)}) for q in sorted(set([lo,hi,0.]+list(np.arange(lo,hi+1e-8,10.)))))
rows=[]
for label,pose in samples:
    key=json.dumps(pose,sort_keys=True);code=hashlib.sha256(key.encode()).hexdigest()[:16];file=dest/(code+'.json.gz')
    saved=json.loads(gzip.decompress(file.read_bytes())) if file.exists() else {}
    if saved.get('source_sha256')!=fingerprint:
        wp={k:v for k,v in pose.items() if k.startswith('wrist_') and v!=0}
        packet=packets.get(json.dumps(wp,sort_keys=True),neutral)
        print('EVALUATE',label,pose,flush=True)
        routes=hand_routing.full_tendon_routes(packet,pose)
        saved={'source_sha256':fingerprint,'pose':pose,'routes':routes}
        file.write_bytes(gzip.compress(json.dumps(saved,separators=(',',':')).encode()))
    assert len(saved['routes'])==48
    rows.append({'label':label,'pose':pose,'file':str(file),'tendon_count':48})
    (root/'static_route_packet_manifest.json').write_text(json.dumps({'source_sha256':fingerprint,'sample_count':len(rows),'complete':len(rows)==len(samples),'rows':rows},indent=2)+'\n')
    print('PACKET',len(rows),len(samples),label,flush=True)
