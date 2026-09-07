"""Four independent native-body partitions of the complete225-pose tendon gate."""
import sys,json,gzip,hashlib,contextlib,concurrent.futures
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent;SRC=ROOT/'models/assemblies/src/anthropomorphic_hand'
sys.path[:0]=[str(SRC),str(HERE)]
from cadgen import read_step
from lib.assembly import Body
from phalanx_beauty_review import leaves,REFINED
from check_full_route_bodies import audit
STEP=ROOT/'models/assemblies/STEP/anthropomorphic_hand/phalanx_beauty_review.step'
MANIFEST=HERE/'static_route_packet_manifest.json'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def worker(name):
 step_sha=sha(STEP);manifest_sha=sha(MANIFEST)
 mapping={r['name']:r for r in json.loads((HERE/'phalanx_beauty_frames.json').read_text())};row=mapping[name]
 shape=next(s for s in leaves(read_step(STEP)) if s.label==name)
 body=Body(shape,row['frame'],row['system'],'phalanx')
 packets=json.loads(MANIFEST.read_text());assert packets['complete'] and packets['sample_count']==225
 rows=[];cache={}
 for packet in packets['rows']:
  item=json.load(gzip.open(packet['file'],'rt'))
  with (HERE/(name+'_225_route_detail.log')).open('a') as log,contextlib.redirect_stdout(log):r=audit(item['routes'],[body],item['pose'],cache)
  r['sample']=packet['label'];r['packet_sha256']=sha(Path(packet['file']));rows.append(r)
  report={'body':name,'step_sha256':step_sha,'manifest_sha256':manifest_sha,'sample_count':len(rows),'complete':len(rows)==225,'pass':len(rows)==225 and all(v['pass'] for v in rows),'rows':rows}
  (HERE/(name+'_225_tendon_gate.json')).write_text(json.dumps(report,indent=2)+'\n')
  if len(rows)%10==0 or not r['pass']:print(name,len(rows),r['pass'],len(r['collisions']),flush=True)
 assert sha(STEP)==step_sha and sha(MANIFEST)==manifest_sha
 return report
if __name__=='__main__':
 with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:reports=list(pool.map(worker,sorted(REFINED)))
 assert len(reports)==4 and {r['body'] for r in reports}==REFINED
 result={'pass':all(r['pass'] for r in reports),'complete':all(r['complete'] for r in reports),'body_count':4,'pose_count':225,'tendons_per_pose':48,'step_sha256':sha(STEP),'manifest_sha256':sha(MANIFEST),'partitions':reports,'scope':'Exact full-route/liner to native-solid clearance, every48 tendons against each of four changed bodies in all225 prescribed static poses; original1e-6mm numeric reserve retained.'}
 (HERE/'phalanx_beauty_225_tendon_gate.json').write_text(json.dumps(result,indent=2)+'\n')
 print('COMPLETE',result['pass'],flush=True)
 if not result['pass']:raise SystemExit(1)
