"""Conservative full-hardware bounding boxes against the saved CMC sweeps."""
from pathlib import Path
import json,numpy as np
out=Path('models/assemblies/validation/anthropomorphic_hand')
boxes=[(f'palm_contact_{i+1}',np.array([x,y,12.7]),np.array([2.7,2.7,2.0])) for i,(x,y) in enumerate([(-24,55),(15,53),(-4,66)])]
boxes += [(f'palm_wrist_{side}',np.array([x,14,-11.1]),np.array([2.2,2.2,3.9])) for x,side in [(-24,'radial'),(24,'ulnar')]]
rows=[]
for file,reserve in [('palm_cmc_guide_envelope_points',1.1),('palm_cmc_metacarpal_envelope_points',1.5)]:
 cloud=np.load(out/(file+'.npz'))['points']
 for name,c,half in boxes:
  d=float('inf')
  for start in range(0,len(cloud),100000):
   q=cloud[start:start+100000];d=min(d,float(np.linalg.norm(np.maximum(np.abs(q-c)-half,0),axis=1).min()))
  row={'hardware_group':name,'swept_body':file,'conservative_gap_mm':d-reserve};rows.append(row);print(row,flush=True)
result={'scope':'Complete bounding boxes of all15 hardware bodies against both5751-pose swept CMC surface clouds. Full global1.1/1.5mm conservative interpolation/surface reserves.','rows':rows,'failures':[r for r in rows if r['conservative_gap_mm']<0]}
(out/'palm_hardware_cmc_envelope.json').write_text(json.dumps(result,indent=2))
