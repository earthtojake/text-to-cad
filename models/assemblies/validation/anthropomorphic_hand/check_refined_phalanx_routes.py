"""All225 authoritative full-tendon packets versus four actual refined bodies."""
import sys,json,gzip,hashlib,contextlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent;SRC=ROOT/'models/assemblies/src/anthropomorphic_hand'
sys.path[:0]=[str(SRC),str(HERE)]
from cadgen import read_step
from lib.assembly import Body
from phalanx_beauty_review import leaves,REFINED
from check_full_route_bodies import audit
step=ROOT/'models/assemblies/STEP/anthropomorphic_hand/phalanx_beauty_review.step'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
step_sha=sha(step);mapping={r['name']:r for r in json.loads((HERE/'phalanx_beauty_frames.json').read_text())}
bodies=[]
for s in leaves(read_step(step)):
 if s.label in REFINED:
  row=mapping[s.label];bodies.append(Body(s,row['frame'],row['system'],'phalanx'))
assert len(bodies)==4
manifest=HERE/'static_route_packet_manifest.json';manifest_sha=sha(manifest);data=json.loads(manifest.read_text());assert data['complete'] and data['sample_count']==225
cache={};rows=[]
for packet in data['rows']:
 item=json.load(gzip.open(packet['file'],'rt'))
 with (HERE/'phalanx_beauty_route_detail.log').open('a') as log,contextlib.redirect_stdout(log):r=audit(item['routes'],bodies,item['pose'],cache)
 r['sample']=packet['label'];r['packet_sha256']=sha(Path(packet['file']));rows.append(r)
 report={'step_sha256':step_sha,'manifest_sha256':manifest_sha,'body_names':[b.name for b in bodies],'sample_count':len(rows),'complete':len(rows)==225,'pass':len(rows)==225 and all(v['pass'] for v in rows),'rows':rows,'scope':'All48 full routed tendons and liners against each of four changed native phalanx bodies, across all225 static prescribed joint/named poses. Exact OCCT wire/solid distances include the same1e-6mm reserve as the root tendon gate.'}
 (HERE/'phalanx_beauty_225_tendon_gate.json').write_text(json.dumps(report,indent=2)+'\n')
 print(packet['label'],r['pass'],len(r['collisions']),flush=True)
assert sha(step)==step_sha and sha(manifest)==manifest_sha
if not report['pass']:raise SystemExit(1)
