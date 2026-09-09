import sys,json,gzip,hashlib
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];SRC=ROOT/'models/assemblies/src/anthropomorphic_hand'
sys.path[:0]=[str(SRC),str(HERE)]
from cadgen import build123d as bd
read_step=bd.import_step
from lib.assembly import Body
from check_full_route_bodies import audit
import check_guide_mount_mutual
check_guide_mount_mutual.read_step=bd.import_step
from check_guide_mount_mutual import check,leaves
STEP=ROOT/'models/assemblies/STEP/anthropomorphic_hand/phalanx_continuous_representative_r5.step'
item=json.load(gzip.open(json.loads((HERE/'static_route_packet_manifest.json').read_text())['rows'][0]['file'],'rt'))
parts=leaves(read_step(STEP));bodies=[Body(p,'middle_mcp_flexion','middle','phalanx' if p.label=='middle_proximal_frame' else 'guide_mount') for p in parts]
r={'step_sha256':hashlib.sha256(STEP.read_bytes()).hexdigest(),'body_count':len(parts),'mutual':check([STEP])};print('mutual',r['mutual'],flush=True)
(HERE/'phalanx_continuous_r5_neutral.json').write_text(json.dumps(r,indent=2))
r['routes']=audit(item['routes'],bodies,{})
r['complete']=True;r['pass']=r['mutual']['pass'] and r['routes']['pass']
(HERE/'phalanx_continuous_r5_neutral.json').write_text(json.dumps(r,indent=2));print('COMPLETE',r['pass'],flush=True)
