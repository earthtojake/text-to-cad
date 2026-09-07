import sys,json,time,numpy as np
from pathlib import Path
from scipy.spatial.transform import Rotation
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from lib.thumb_cmc_transport import solve
root=Path('models/assemblies/validation/anthropomorphic_hand')
previous=next(p for p in json.loads((root/'thumb_cmc_outlet16_axes.json').read_text()) if p['flex']==40)
out=[]
for f,y in [(39.17,float(y)) for y in(0,-5,-10,-15,-20,-25)]:
 oldR=Rotation.from_euler('z',previous['yaw'],degrees=True).as_matrix()@Rotation.from_euler('x',previous['flex'],degrees=True).as_matrix();newR=Rotation.from_euler('z',y,degrees=True).as_matrix()@Rotation.from_euler('x',f,degrees=True).as_matrix();R=Rotation.from_rotvec(Rotation.from_matrix(newR@oldR.T).as_rotvec()*.5).as_matrix();rows=[];others=[];t=time.time()
 for row in previous['rows']:
  seed=np.array(row['params'])
  for i in range(2,len(seed),3):seed[i:i+3]=R@seed[i:i+3]
  cs,v=solve(f,y,row['lane'],others,length=row['length'],initials_extra=[seed,row['params']],only_extra=True,outlet_y=16);others.append(cs);rows.append({'lane':row['lane'],'length':row['length'],'params':v.tolist(),'curves':cs.tolist()});print('PASS',f,y,row['lane'],flush=True)
 previous={'flex':f,'yaw':y,'outlet_y':16,'rows':rows};out.append(previous);(root/'thumb_cmc_outlet16_pinch.json').write_text(json.dumps(out,indent=2));print('POSE',f,y,round(time.time()-t,2),flush=True)
