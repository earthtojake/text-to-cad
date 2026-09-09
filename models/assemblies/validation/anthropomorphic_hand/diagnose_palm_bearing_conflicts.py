import sys,json,gzip
from pathlib import Path
import numpy as np
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from cadgen import read_step,build123d as bd
from lib.layout import assembled_transforms
from lib.finger_routing import transform_path
from lib.transport_guide import path_wire
V=Path('models/assemblies/validation/anthropomorphic_hand');M=json.loads((V/'static_route_packet_manifest.json').read_text());main=read_step('models/assemblies/STEP/anthropomorphic_hand/imported/palm_frame_integration.step');little=read_step('models/assemblies/STEP/anthropomorphic_hand/palm_little_review.step');rows=[]
for sample in M['rows'][1:3]:
 packet=json.loads(gzip.decompress(Path(sample['file']).read_bytes()));fk=assembled_transforms(sample['pose'])
 for r in packet['routes']:
  if not (r['name'].endswith(('pip_positive','pip_negative','dip_negative')) or r['name']=='thumb_mcp_flexion_positive'):continue
  f=r['name'].split('_')[0]
  for g in r['groups']:
   if not (g['label'].endswith(('mcp_reaction','proximal_guide')) or g['label']=='thumb_mcp_flexion_positive_cmc_reaction'):continue
   frame='palm_cup' if f=='little' else 'wrist_flexion';path=transform_path(g['path'],np.linalg.inv(fk[frame]));wire=path_wire(path);shape=little if f=='little' else main;d=wire.distance_to(shape)
   if d>.50:continue
   xy={'index':(-36,101),'middle':(-12,105),'ring':(12,100),'little':(36,89),'thumb':(-35,36)}[f];planes=(14,-18) if f=='thumb' else(12.5,-16.5)
   bands=[]
   for z in planes:
    for radius in (3.1,2.9,2.7):
     ring=bd.Pos(*xy,z)*(bd.Cylinder(radius,2)-bd.Cylinder(2.53,3));gap=wire.distance_to(ring)-.45
     bands.append({'z':z,'outer_radius':radius,'liner_gap':gap})
   row={'sample':sample['label'],'tendon':r['name'],'group':g['label'],'frame':frame,'path':path,'native_gap':d-.45,'closest':[tuple(q) for q in wire.closest_points(shape)],'bands':bands};rows.append(row);print(json.dumps({k:v for k,v in row.items() if k!='path'}),flush=True)
(V/'palm_fist_immutable_diagnostic.json').write_text(json.dumps(rows,indent=2))
