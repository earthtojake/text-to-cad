import sys,json
from pathlib import Path
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from cadgen import read_step,build123d as bd
from lib.layout import assembled_transforms
from lib.assembly import matrix_location
base=Path('models/assemblies');v=base/'validation/anthropomorphic_hand';samples=json.loads((v/'static_route_packet_manifest.json').read_text())['rows'][1:3]
def leaves(s):return[p for c in s.children for p in leaves(c)] if s.children else[s]
parts=leaves(read_step(base/'STEP/anthropomorphic_hand/phalanx_guide_mounts_review.step'));rows=[]
for sample in samples:
 fk=assembled_transforms(sample['pose'])
 for p in parts:
  if not p.label.startswith('index_mcp_outlet_comb'):continue
  q=matrix_location(fk['index_mcp_flexion'])*p
  for radius in(3.1,2.9,2.7):
   band=bd.Pos(-36,101,12.5)*(bd.Cylinder(radius,2)-bd.Cylinder(2.53,3));hit=q&band;vol=sum(a.volume for a in hit.solids()) if hit else 0
   if vol>1e-7:
    r={'sample':sample['label'],'body':p.label,'protected_band_R':radius,'intersection_mm3':vol};rows.append(r);print(r,flush=True)
(v/'palm_outlet_seat_diagnostic.json').write_text(json.dumps(rows,indent=2))
