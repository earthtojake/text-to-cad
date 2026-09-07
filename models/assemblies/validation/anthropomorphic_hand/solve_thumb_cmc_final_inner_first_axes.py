import sys,json,time,numpy as np
from pathlib import Path
from scipy.spatial.transform import Rotation
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from lib.thumb_cmc_transport import solve
root=Path('models/assemblies/validation/anthropomorphic_hand')
start=json.loads((root/'thumb_cmc_top_inner_first.json').read_text())[0]
oldbank={(p['flex'],p['yaw']):p for p in json.loads((root/'thumb_cmc_dorsal_bank.json').read_text())}
out=[start]
def packet(previous,f,y):
 oldR=Rotation.from_euler('z',previous['yaw'],degrees=True).as_matrix()@Rotation.from_euler('x',previous['flex'],degrees=True).as_matrix();newR=Rotation.from_euler('z',y,degrees=True).as_matrix()@Rotation.from_euler('x',f,degrees=True).as_matrix();R=Rotation.from_rotvec(Rotation.from_matrix(newR@oldR.T).as_rotvec()*.5).as_matrix();others=[];rows=[];t=time.time()
 for row in previous['rows']:
  seed=np.array(row['params'])
  for i in range(2,len(seed),3):seed[i:i+3]=R@seed[i:i+3]
  seeds=[seed,row['params']]
  cs,v=solve(f,y,row['lane'],others,length=row['length'],initials_extra=seeds,only_extra=True,outlet_y=16,span_count=4 if abs(row['lane'])==3 else 3);others.append(cs);rows.append({'lane':row['lane'],'length':row['length'],'params':v.tolist(),'curves':cs.tolist()});print('PASS',f,y,row['lane'],flush=True)
 result={'flex':f,'yaw':y,'outlet_y':16,'rows':rows};out.append(result);(root/'thumb_cmc_final_inner_first_axes.json').write_text(json.dumps(out,indent=2));print('POSE',f,y,round(time.time()-t,2),flush=True);return result
previous=start
for f in range(60,-16,-5):previous=packet(previous,float(f),0.)
neutral=next(p for p in out if p['flex']==0 and p['yaw']==0)
for sequence in(range(-5,-26,-5),range(5,46,5)):
 previous=neutral
 for y in sequence:previous=packet(previous,0.,float(y))
