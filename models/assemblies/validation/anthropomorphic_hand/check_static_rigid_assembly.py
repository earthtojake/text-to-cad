"""Every rigid occurrence at all225 static poses, native STEP Booleans.

Congruent prototype/relative placements reuse exact completed intersection
proofs. Each worker retains those proofs across its sequence of poses.
"""
import sys,json,hashlib,multiprocessing,argparse
from pathlib import Path
HERE=Path(__file__).parent
sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from cadgen import read_step
from lib.assembly import Body,posed_bodies
from check_assembly_interference import audit
from check_full_route_bodies import placed_bounds
BODIES=None;SAMPLES=None;PREFIX='static_rigid'

def run_partition(index):
 cache={};rows=[]
 for sample in SAMPLES[index::8]:
  temporary=HERE/f'{PREFIX}_live_{index}.json'
  result=audit(posed_bodies(BODIES,sample['pose']),temporary,cache=cache,pose=sample['pose'])
  result.update(sample=sample['label'],pose=sample['pose']);rows.append(result)
  (HERE/f'{PREFIX}_partition_{index}.json').write_text(json.dumps({'rows':rows,'complete':len(rows)==len(SAMPLES[index::8]),'pass':all(r['pass'] for r in rows)},indent=2)+'\n')
 return rows

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--baseline',action='store_true');parser.add_argument('--workers',type=int,default=8);parser.add_argument('--native',action='store_true');args=parser.parse_args()
 step=HERE.parents[1]/'STEP/anthropomorphic_hand/hand_progress_review.step'
 meta=HERE/'hand_progress_body_frames.json'
 if args.baseline:
  step=step.parent/'imported/integration_native_base.step';meta=HERE/'integration_native_base_frames.json';PREFIX='static_rigid_baseline'
 inputs={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [step,meta]}
 mapping={r['name']:r for r in json.loads(meta.read_text())}
 def leaves(n):return [s for c in n.children for s in leaves(c)] if n.children else [n]
 if args.native:
  from check_native_reported_contacts import native_shapes
  native=list(native_shapes(step).values());PREFIX=PREFIX.replace('static_rigid','static_native_rigid')
 else:native=leaves(read_step(step))
 assert len(native)==len(mapping) and {s.label for s in native}==set(mapping)
 BODIES=[Body(s,**{k:mapping[s.label][k] for k in ['frame','system','kind']}) for s in native if mapping[s.label]['frame']!='variable']
 manifest=json.loads((HERE/'static_route_packet_manifest.json').read_text());SAMPLES=manifest['rows'];assert len(SAMPLES)==225
 for path in [HERE/'static_route_packet_manifest.json',Path(__file__),HERE/'check_assembly_interference.py',HERE/'rigid_pose_cache.py',HERE.parents[1]/'src/anthropomorphic_hand/lib/layout.py']:
  inputs[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
 placed_bounds(BODIES)
 print('FROZEN',len(BODIES),'native rigid bodies',flush=True)
 with multiprocessing.get_context('fork').Pool(args.workers) as pool:parts=pool.map(run_partition,range(8))
 rows=[r for part in parts for r in part]
 assert len(rows)==225 and all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==v for p,v in inputs.items())
 result={'sample_count':225,'body_count':len(BODIES),'input_sha256':inputs,'rows':rows,'pass':all(r['pass'] for r in rows)}
 (HERE/f'{PREFIX}_assembly_gate.json').write_text(json.dumps(result,indent=2)+'\n')
 assert result['pass']
