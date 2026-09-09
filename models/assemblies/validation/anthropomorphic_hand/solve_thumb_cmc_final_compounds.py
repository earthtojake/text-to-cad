import sys,json,time,numpy as np
from pathlib import Path
from scipy.spatial.transform import Rotation
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from lib.thumb_cmc_transport import solve
root=Path('models/assemblies/validation/anthropomorphic_hand');out=[]
def packet(previous,f,y):
 oldR=Rotation.from_euler('z',previous['yaw'],degrees=True).as_matrix()@Rotation.from_euler('x',previous['flex'],degrees=True).as_matrix();newR=Rotation.from_euler('z',y,degrees=True).as_matrix()@Rotation.from_euler('x',f,degrees=True).as_matrix();R=Rotation.from_rotvec(Rotation.from_matrix(newR@oldR.T).as_rotvec()*.5).as_matrix();others=[];rows=[];t=time.time()
 for row in previous['rows']:
  seed=np.array(row['params'])
  for i in range(2,len(seed),3):seed[i:i+3]=R@seed[i:i+3]
  cs,v=solve(f,y,row['lane'],others,length=row['length'],initials_extra=[seed,row['params']],only_extra=True,outlet_y=16,span_count=4 if abs(row['lane'])==3 else 3);others.append(cs);rows.append({'lane':row['lane'],'length':row['length'],'params':v.tolist(),'curves':cs.tolist()});print('PASS',f,y,row['lane'],flush=True)
 result={'flex':f,'yaw':y,'outlet_y':16,'rows':rows};out.append(result);(root/'thumb_cmc_final_compounds_candidates.json').write_text(json.dumps(out,indent=2));print('POSE',f,y,round(time.time()-t,2),flush=True);return result
axes=json.loads((root/'thumb_cmc_final_axes_candidates.json').read_text())
for f in(-15.,39.17):
 start=min((p for p in axes if p['yaw']==0),key=lambda p:abs(p['flex']-f))
 if start['flex']!=f:start=packet(start,f,0.)
 for seq in ((-5.,-10.,-15.,-20.,-25.),(5.,10.,15.,20.,25.,30.,35.,40.,45.)) if f==-15 else ((-5.,-10.,-15.,-20.,-25.),):
  previous=start
  for y in seq:previous=packet(previous,f,y)
