import sys,json,time,numpy as np
from pathlib import Path
from scipy.spatial.transform import Rotation
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from lib.thumb_cmc_transport import solve
root=Path('models/assemblies/validation/anthropomorphic_hand')
previous=next(p for p in json.loads((root/'thumb_cmc_outlet16_topflex.json').read_text()) if p['flex']==55)
out=[previous]
for f in range(56,66):
 R=Rotation.from_euler('x',.5,degrees=True).as_matrix();rows=[];others=[];t=time.time()
 for row in previous['rows']:
  seed=np.array(row['params'])
  for i in range(2,len(seed),3):seed[i:i+3]=R@seed[i:i+3]
  try:
   cs,v=solve(f,0,row['lane'],others,length=row['length'],initials_extra=[seed,row['params']],only_extra=True,outlet_y=16)
  except Exception as e:
   (root/'thumb_cmc_top_fine_failure.json').write_text(json.dumps({'flex':f,'lane':row['lane'],'others':rows,'previous':previous,'error':str(e)},indent=2));raise
  others.append(cs);rows.append({'lane':row['lane'],'length':row['length'],'params':v.tolist(),'curves':cs.tolist()})
  print('PASS',f,row['lane'],flush=True)
 previous={'flex':f,'yaw':0.,'outlet_y':16,'rows':rows};out.append(previous);(root/'thumb_cmc_outlet16_top_fine.json').write_text(json.dumps(out,indent=2));print('POSE',f,round(time.time()-t,2),flush=True)
