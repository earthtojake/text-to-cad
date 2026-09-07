import sys,json,time,numpy as np
from pathlib import Path
from scipy.spatial.transform import Rotation
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from lib.thumb_cmc_transport import solve
root=Path('models/assemblies/validation/anthropomorphic_hand');previous=json.loads((root/'thumb_cmc_dorsal_bank_fourspan.json').read_text())[-1];out=[previous]
for f in(56,57,58,59,60,61,62,63,64,65):
 R=Rotation.from_euler('x',(f-previous['flex'])/2,degrees=True).as_matrix();rows=[];others=[]
 for row in previous['rows']:
  seed=np.array(row['params'])
  for i in range(2,len(seed),3):seed[i:i+3]=R@seed[i:i+3]
  t=time.time();cs,v=solve(f,0,row['lane'],others,length=row['length'],initials_extra=[seed,row['params']],outlet_y=16,only_extra=True,span_count=4 if abs(row['lane'])==3 else 3);others.append(cs);rows.append({'lane':row['lane'],'length':row['length'],'params':v.tolist(),'curves':cs.tolist()});print('PASS',f,row['lane'],round(time.time()-t,2),flush=True)
 previous={'flex':f,'yaw':0.,'outlet_y':16,'rows':rows};out.append(previous);(root/'thumb_cmc_dorsal_bank_top_fine.json').write_text(json.dumps(out,indent=2))
