import sys,json,numpy as np,hashlib
from pathlib import Path
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from cadgen import build123d as bd,read_step
from lib.layout import assembled_transforms
from lib.assembly import matrix_location
V=Path('models/assemblies/validation/anthropomorphic_hand');B=Path('models/assemblies/STEP/anthropomorphic_hand');manifest=json.loads((V/'static_route_packet_manifest.json').read_text())
def leaves(s):return [p for c in s.children for p in leaves(c)] if s.children else [s]
meta={r['name']:r for r in json.loads((V/'phalanx_comb_clearance_frames.json').read_text())};parts=[s for s in leaves(read_step(B/'phalanx_comb_clearance_review.step')) if 'mcp_outlet' in s.label];print('PARTS',len(parts),flush=True)
which=sys.argv[1];host=read_step(B/('palm_main_final_rom_review.step' if which=='main' else 'palm_little_comb_rom_review.step'));hb=host.bounding_box(optimal=False);cache=set();rows=[]
checkpoint=V/f'palm_{which}_final_comb_225_gate.json'
old=json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
start=old.get('sample_count',0);rows=old.get('rows',[])
for i,s in enumerate(manifest['rows']):
 fk=assembled_transforms(s['pose']);parent='wrist_flexion' if which=='main' else 'palm_cup';inv=np.linalg.inv(fk[parent])
 for part in parts:
  if ('little_' in part.label)!=(which=='little'):continue
  m=inv@fk[meta[part.label]['frame']];key=(part.label,tuple(np.round(m.flatten(),7)))
  if key in cache:continue
  cache.add(key)
  if i<start:continue
  placed=bd.Compound.cast(part.wrapped.Moved(matrix_location(m).wrapped));bb=placed.bounding_box(optimal=False)
  if any(hb.max.to_tuple()[a]<bb.min.to_tuple()[a] or bb.max.to_tuple()[a]<hb.min.to_tuple()[a] for a in range(3)):continue
  c=host&placed;volume=sum(x.volume for x in c.solids()) if c else 0
  if volume>1e-7:
   row={'sample':s['label'],'part':part.label,'volume':volume};rows.append(row);print(row,flush=True)
 if i<start:continue
 report={'complete':i==224,'sample_count':i+1,'unique_body_poses':len(cache),'method':'direct native solid Boolean after conservative bounds; completed checkpoint results retained','rows':rows,'pass':all(r['volume']<1e-7 for r in rows)};(V/f'palm_{which}_final_comb_225_gate.json').write_text(json.dumps(report,indent=2))
print('DONE',which,len(cache),report['pass'],flush=True)
